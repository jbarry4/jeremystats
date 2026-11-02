# -*- coding: utf-8 -*-
"""Step 4 -- what the extra candidates are, and what removes them.

THREE PARTS

1. A waveform classifier. "Does this candidate look like the IEDs a person
   already confirmed on this recording, across the depth of the probe?"
   Every candidate is aligned on its largest deflection and its space-time
   waveform (every good channel, -200..+300 ms, notch + low-pass 300 Hz) is
   correlated with that recording's average Solid, allowing +/-25 ms of lag.
   Solids are scored LEAVE-ONE-OUT so none is compared with a template it is
   part of. It is validated on the labels before it is trusted: Solids vs
   Garbage, with Sputter and Flag shown for reference. Its threshold is set
   so that every Solid passes -- the user's rule is to lose none -- and what
   that costs in Garbage let through is reported.

2. A shmutz taxonomy. Each candidate gets measured features (how common-mode
   it is, how much of its power is mains, how much is 300-900 Hz, how focal
   it is, amplitude, duration, channel count). A candidate the classifier
   calls not-IED is sorted into the FIRST type whose feature lies beyond
   every Solid on this dataset -- so no real IED could have been put in any
   shmutz bin -- and "other" if none does.

3. Countermeasures. For each pre-filter's best setting that still catches
   every Solid (from step 3b), count the shmutz of each type it produces.
   That is the validation: a countermeasure is a filter or a parameter that
   removes a type of shmutz without losing an IED.

Writes out/shmutz_*.csv and prints the summary.

    python step4_shmutz.py
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

import detector as D
import ied_common as C
from step3_sweep import chan_rows

PRE_S, POST_S = 0.200, 0.300          # snippet
CMP_PRE, CMP_POST = 0.100, 0.200      # part of it the correlation uses
LAG_S, LAG_STEP_S = 0.025, 0.0025


# ---------------------------------------------------------------- features

def snippet(Y, t, rows):
    i = int(round(t * C.FS))
    a, b = i - int(PRE_S * C.FS), i + int(POST_S * C.FS)
    if a < 0 or b > Y.shape[1]:
        return None
    s = np.asarray(Y[rows, a:b], dtype=np.float64)
    base = np.median(s[:, :int(0.1 * C.FS)], axis=1, keepdims=True)
    return s - base


def align_time(Y, on, off, rows):
    """The moment of the largest deflection inside the window."""
    a = max(0, int((on - 0.05) * C.FS))
    b = min(Y.shape[1], int((off + 0.05) * C.FS))
    if b <= a:
        return (on + off) / 2
    seg = np.asarray(Y[rows, a:b], dtype=np.float64)
    seg = seg - np.median(seg, axis=1, keepdims=True)
    return (a + int(np.argmax(np.max(np.abs(seg), axis=0)))) / C.FS


def corr_score(s, T):
    """Best Pearson r between snippet s and template T over small lags."""
    c0 = int((PRE_S - CMP_PRE) * C.FS)
    c1 = int((PRE_S + CMP_POST) * C.FS)
    t = T[:, c0:c1].ravel()
    t = (t - t.mean()) / (t.std() + 1e-12)
    best = -1.0
    step = max(1, int(LAG_STEP_S * C.FS))
    lag = int(LAG_S * C.FS)
    for L in range(-lag, lag + 1, step):
        if c0 + L < 0 or c1 + L > s.shape[1]:
            continue
        v = s[:, c0 + L:c1 + L].ravel()
        v = (v - v.mean()) / (v.std() + 1e-12)
        r = float(np.dot(v, t) / v.size)
        best = max(best, r)
    return best


def raw_features(R, on, off, rows):
    """Features of the raw (2 kHz, unfiltered) window."""
    a = max(0, int((on - 0.05) * C.FS))
    b = min(R.shape[1], int((off + 0.05) * C.FS))
    if b - a < int(0.1 * C.FS):
        mid = (a + b) // 2
        a, b = max(0, mid - int(0.05 * C.FS)), mid + int(0.05 * C.FS)
    x = np.asarray(R[rows, a:b], dtype=np.float64)
    x = x - x.mean(axis=1, keepdims=True)
    m = x.mean(axis=0)
    # common mode: how much of each channel's variance the mean explains
    cm = float(np.var(m) / max(np.mean(np.var(x, axis=1)), 1e-12))
    X = np.abs(np.fft.rfft(x * np.hanning(x.shape[1]), axis=1)) ** 2
    f = np.fft.rfftfreq(x.shape[1], 1 / C.FS)
    P = X.mean(axis=0)
    tot = P[(f >= 1) & (f <= 900)].sum() + 1e-12
    mains = sum(P[(f >= h - 4) & (f <= h + 4)].sum() for h in (60, 120, 180))
    hf = P[(f >= 300) & (f <= 900)].sum()
    rms = np.sqrt(np.mean(x ** 2, axis=1))
    return {"common_mode": cm, "mains_frac": float(mains / tot),
            "hf_frac": float(hf / tot),
            "focal": float(rms.max() / max(np.median(rms), 1e-12)),
            "peak_uv": float(np.max(np.abs(x)))}


# ---------------------------------------------------------------- per rec

def candidates(rec, setting):
    d, meta, X = D.load_rec(rec)
    nums = meta["channels"]
    good = chan_rows(nums, rec["bad"], "all_good")
    evs = D.run_setting(rec, setting, X=X, meta=meta, d=d)
    Y = D.filtered("lfp", X, good)              # shape analysis
    labs = {}
    for lab in ("solid", "sputter", "flag", "garbage", None):
        labs[lab] = np.asarray(sorted(e["t"] for e in rec["events"]
                                      if e["label"] == lab))
    ev_arr = np.asarray([[e["on"], e["off"]] for e in evs]) if evs else \
        np.zeros((0, 2))
    from step3_sweep import vmatch
    label_of = ["unreviewed-new"] * len(evs)   # nobody ever saw these
    for lab in ("garbage", "flag", None, "sputter", "solid"):  # priority up
        m = vmatch(ev_arr, labs[lab])
        for j in m[m >= 0]:
            label_of[j] = lab or "unreviewed"
    out = []
    for e, lab in zip(evs, label_of):
        t = align_time(Y, e["on"], e["off"], good)
        f = raw_features(X, e["on"], e["off"], good)
        out.append(dict(key=rec["key"], on=e["on"], off=e["off"], t=t,
                        dur=e["off"] - e["on"], n=e["n"], label=lab, **f))
    # template from this recording's Solids, leave-one-out for the Solids
    snips = [snippet(Y, c["t"], good) for c in out]
    solid_ix = [i for i, c in enumerate(out)
                if c["label"] == "solid" and snips[i] is not None]
    if len(solid_ix) >= 2:
        S = np.stack([snips[i] for i in solid_ix])
        T_all = S.mean(axis=0)
        for i, c in enumerate(out):
            if snips[i] is None:
                c["score"] = np.nan
                continue
            if i in solid_ix:
                T = (T_all * len(solid_ix) - snips[i]) / (len(solid_ix) - 1)
            else:
                T = T_all
            c["score"] = corr_score(snips[i], T)
    else:
        for c in out:
            c["score"] = np.nan
    return out


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if not len(pos) or not len(neg):
        return np.nan
    r = np.argsort(np.argsort(np.concatenate([pos, neg])))
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) - 1) / 2)
                 / (len(pos) * len(neg)))


FEATURES = ("common_mode", "mains_frac", "hf_frac", "focal", "peak_uv",
            "dur", "n")
# For each feature, which side is shmutz. `n` small = few channels.
SIDE = {"common_mode": +1, "mains_frac": +1, "hf_frac": +1, "focal": +1,
        "peak_uv": +1, "dur": +1, "n": -1}
NAMES = {"common_mode": "common-mode (every channel moves together)",
         "mains_frac": "mains (60 Hz and harmonics)",
         "hf_frac": "high-frequency burst (300-900 Hz: EMG/chewing/MUA)",
         "focal": "single-channel pop (one channel far above the rest)",
         "peak_uv": "very large transient (beyond any Solid)",
         "dur": "long event (longer than any Solid)",
         "n": "too few channels (fewer than any Solid)"}


def taxonomy_limits(cands):
    """Per feature, the bound no Solid crosses."""
    sol = [c for c in cands if c["label"] == "solid"]
    lim = {}
    for f in FEATURES:
        v = np.asarray([c[f] for c in sol], dtype=float)
        v = v[np.isfinite(v)]
        lim[f] = (v.max() if SIDE[f] > 0 else v.min()) if v.size else np.nan
    return lim


def kind_of(c, lim):
    """The first feature on which this candidate is beyond every Solid."""
    best, best_z = None, 0.0
    for f in FEATURES:
        L = lim[f]
        if not np.isfinite(L):
            continue
        v = c[f]
        beyond = (v > L) if SIDE[f] > 0 else (v < L)
        if beyond:
            z = (v / L if SIDE[f] > 0 else L / max(v, 1e-9))
            if z > best_z:
                best, best_z = f, z
    return best or "other"


def main():
    gt = C.load_gt()
    with open(os.path.join(C.OUT, "sweep_frontier.csv"), newline="") as fh:
        front = list(csv.DictReader(fh))
    settings = {}
    for r in front:
        if r.get("llw"):
            settings[r["prefilter"]] = {k: r[k] for k in
                                        ("prefilter", "llw", "chanset", "mode",
                                         "prc", "merge", "min_s")}
    # the original, too
    settings["ORIGINAL"] = {"prefilter": "orig30k", "llw": 0.04,
                            "chanset": "even", "mode": "global", "prc": 99.9,
                            "merge": 0.3, "min_s": 0.025}
    only = set(sys.argv[1:])
    if only:
        settings = {k: v for k, v in settings.items() if k in only}

    results = {}
    for name, s in settings.items():
        C.log("\n=== %s  %s" % (name, s))
        cands = []
        for rec in gt:
            cands.extend(candidates(rec, s))
            C.log("  %s: %d candidates" % (rec["key"],
                                            sum(1 for c in cands
                                                if c["key"] == rec["key"])))
        results[name] = cands
        with open(os.path.join(C.OUT, "shmutz_%s.csv" % name), "w",
                  newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(cands[0].keys()))
            w.writeheader()
            w.writerows(cands)

    # ---- 1. the classifier, validated on the labels ----------------------
    # Validated on the run that keeps every labelled candidate: the setting
    # whose candidates match the most labels is the fairest test set.
    ref = max(results, key=lambda k: sum(1 for c in results[k]
                                         if c["label"] in C.LABELS))
    cands = results[ref]
    by = defaultdict(list)
    for c in cands:
        by[c["label"]].append(c["score"])
    sol = np.asarray(by["solid"], float)
    sol = sol[np.isfinite(sol)]
    thr = float(np.min(sol)) if sol.size else np.nan
    C.log("\n=== waveform classifier, validated on the labels (%s) ===" % ref)
    for lab in ("solid", "sputter", "flag", "garbage", "unreviewed",
                "unreviewed-new"):
        v = np.asarray(by[lab], float)
        v = v[np.isfinite(v)]
        if v.size:
            C.log("  %-15s n=%4d  median r=%.2f  [%.2f .. %.2f]  passes=%d%%"
                  % (lab, v.size, np.median(v), np.min(v), np.max(v),
                     round(100 * np.mean(v >= thr))))
    C.log("  AUC solid vs garbage = %.3f" % auc(by["solid"], by["garbage"]))
    C.log("  threshold that keeps EVERY solid: r >= %.3f" % thr)
    with open(os.path.join(C.OUT, "classifier.json"), "w") as fh:
        json.dump({"threshold": thr, "validated_on": ref,
                   "auc_solid_vs_garbage": auc(by["solid"], by["garbage"])},
                  fh, indent=1)

    # ---- 2 and 3. the taxonomy, and what each setting leaves -----------
    lim = taxonomy_limits(cands)
    C.log("\n=== bounds no Solid crosses ===")
    for f in FEATURES:
        C.log("  %-12s %s %.3g" % (f, ">" if SIDE[f] > 0 else "<", lim[f]))
    table = []
    for name, cs in results.items():
        k = Counter()
        n_ied_like = 0
        for c in cs:
            if c["label"] in ("solid",):
                continue
            if np.isfinite(c["score"]) and c["score"] >= thr:
                n_ied_like += 1
                continue
            k[kind_of(c, lim)] += 1
        row = {"setting": name, "candidates": len(cs),
               "solids": sum(1 for c in cs if c["label"] == "solid"),
               "ied_like_other": n_ied_like,
               "shmutz": sum(k.values())}
        row.update({f: k.get(f, 0) for f in list(FEATURES) + ["other"]})
        table.append(row)
    with open(os.path.join(C.OUT, "shmutz_by_setting.csv"), "w",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)
    C.log("\n=== shmutz by type, per setting ===")
    for r in table:
        C.log(r)


if __name__ == "__main__":
    main()
