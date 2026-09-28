# -*- coding: utf-8 -*-
"""Does Drift's arithmetic say what it claims to?

backend/drift.py pools each side of a comparison by DerSimonian-Laird
random-effects meta-analysis of RECORDINGS (cue pairs nested within them),
then tests the delta and corrects by Benjamini-Hochberg per panel. This
checks it three ways:

  1. REFERENCE. An independent re-derivation of DL tau^2, the weights, the
     pooled mean and SE -- plain Python loops, nothing imported from
     drift.py -- on small hand-made cases (including a recording that must
     borrow the pooled SD), asserted to 1e-12. Then the published BCG
     vaccine meta-analysis (13 trials, log risk ratios; the standard
     worked example of the R package metafor, `rma(..., method="DL")`):
     tau^2 = 0.3088, estimate = -0.7141, SE = 0.1787, Q = 152.23.
     statsmodels is not installed on this machine, so the published example
     is the external cross-check.
  2. BEHAVIOUR. Identical groups; a shifted copy; n = 1 vs n = 8 weighting;
     inflated n (every pair duplicated) with pair-pooled and nested p side by
     side; BH against a hand list; grey regions and absent cells; k = 1;
     nothing to borrow; refusals naming the field; strict JSON.
  3. NEGATIVE CONTROLS. `--break tau0` forces tau^2 = 0 (fixed effect);
     `--break pairs` pools pairs across recordings as if independent;
     `--break bh` reports q = p; `--break vid` pins by version number only
     (forgets version_id); `--break kindparams` compares every window
     parameter whatever the kind. Each must make the relevant checks FAIL.
     The breaks are monkeypatches in this process only -- drift.py on disk
     is never touched, so "restore" is simply running without --break.

Run (PowerShell):  python tools\\check_drift.py [--break tau0|pairs|bh]
Exit code 1 if anything failed.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scipy import stats                                   # noqa: E402

from backend import drift as D                            # noqa: E402

FAILED = []


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           ("   [%s]" % detail) if detail else ""))
    if not ok:
        FAILED.append(name)


def close(a, b, tol=1e-12):
    return a is not None and b is not None and abs(a - b) <= tol


# ---------------------------------------------------------------------------
# Synthetic circuits, built to contract section 3 to the letter.
# ---------------------------------------------------------------------------

ORDER = ["Right ACC", "Right OFC", "Right DHC", "Right RSC", "Right PER",
         "Right POR", "Left POR", "Left PER", "Left RSC", "Left DHC",
         "Left OFC", "Left ACC"]
STATE = ["pre", "cue1", "cue2", "post"]
METHODS = ["coherence", "raw_cc", "amp_cc"]
PARAMS = {"low": 4.0, "high": 12.0, "summary_hz": 8.0, "max_lag_ms": 500.0,
          "notch_hz": 60.0, "pad_s": 10.0, "analysis_fs": 1000.0,
          "channel_rule": "lowest-numbered usable wire", "kind": "state",
          "before_s": 1.0, "after_s": 2.0}
DEV8 = [-0.12, -0.08, -0.04, 0.0, 0.02, 0.05, 0.07, 0.10]   # per-pair scatter


def _sd(xs):
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _offset(w, m, a, b):
    """A fixed, cell-specific offset so cells are not all the same."""
    h = sum(ord(c) for c in w + m + a + b)
    return (h % 17) / 100.0


def circuit(gid, level, grey=(), n_pairs=8, per_pair=None, rep=1,
            params=None, kind="state", windows=None, cue_type="HighTone_LowTone",
            methods=None, usable=None, raw_cells=None, effect=None):
    """One recording's circuit payload.

    Cell value for pair j = level + offset(cell) + per_pair[j] (repeated
    `rep` times -- rep > 1 duplicates every pair to inflate n). `usable`
    limits how many pairs each cell has. `raw_cells` overrides cells with
    {(w, m, key): [values]}.
    """
    windows = windows or STATE
    methods = methods or METHODS
    per_pair = list(DEV8 if per_pair is None else per_pair)
    grey = set(grey)
    regions = [{"region": r, "slot": r.replace(" ", "_"), "label": r,
                "histology": "missed" if r in grey else "intended",
                "status": "grey" if r in grey else "ok",
                "why": ("probe missed %s" % r) if r in grey else "on target"}
               for r in ORDER]
    pairs = [{"pair_id": j + 1, "label": "High tone → Low Tone",
              "opener_t": 100.0 + 60 * j} for j in range(n_pairs * rep)]
    cells = {}
    for w in windows:
        cells[w] = {}
        for m in methods:
            cells[w][m] = {}
            for i, a in enumerate(ORDER):
                for b in ORDER[i + 1:]:
                    if a in grey or b in grey:
                        continue
                    key = "%s|%s" % (a, b)
                    if raw_cells and (w, m, key) in raw_cells:
                        vals = raw_cells[(w, m, key)]
                    else:
                        base = level + _offset(w, m, a, b)
                        if effect:
                            base += effect(w, m, a, b)
                        devs = per_pair[:n_pairs if usable is None else usable]
                        vals = [base + d for d in devs] * rep
                    if not vals:
                        continue
                    n = len(vals)
                    of = n_pairs * rep
                    cells[w][m][key] = {
                        "n": n, "mean": sum(vals) / n, "sd": _sd(vals),
                        "values": [{"pair_id": j + 1, "v": v}
                                   for j, v in enumerate(vals)],
                        "of": of,
                        "warn": ("usable in %d of %d pairs" % (n, of)
                                 if n < of / 2.0 else None)}
    p = dict(PARAMS)
    p["kind"] = kind
    p.update(params or {})
    return {
        "schema": "arc.circuit/1", "kind": kind, "cue_type": cue_type,
        "cue_label": "High tone → Low Tone",
        "windows": list(windows), "methods": list(methods),
        "region_order": list(ORDER), "regions": regions, "pairs": pairs,
        "n_pairs": n_pairs * rep, "cells": cells,
        "region_usable": {w: {r: {"usable": 0 if r in grey else n_pairs,
                                  "of": n_pairs} for r in ORDER}
                          for w in windows},
        "grey": sorted(grey), "params": p,
        "source": {"gid": gid, "session_label": gid, "bank_entry": "e" + gid,
                   "bank_version": 1},
        "computed_on": {"kind": "local"},
    }


def refs(payloads, prefix):
    return [{"artifact_id": "%s%02d" % (prefix, i), "version": 1,
             "digest": "d%s%02d" % (prefix, i),
             "name": p["source"]["gid"]} for i, p in enumerate(payloads)]


def run(L, R, labels=("left", "right")):
    return D.build(L, R, refs(L, "a"), refs(R, "b"), labels)


def safe_build(L, R, lr, rr):
    """build, or None (said) when it refuses -- so a negative control fails
    the checks that depend on it instead of crashing the run."""
    try:
        return D.build(L, R, lr, rr, ("l", "r"))
    except D.DriftError as e:
        print("        (build refused: %s)" % e)
        return None


def cells_of(payload):
    for w, byw in payload["cells"].items():
        for m, panel in byw.items():
            for k, c in panel.items():
                yield w, m, k, c


# ---------------------------------------------------------------------------
# Independent reference (plain loops; shares nothing with drift.py).
# ---------------------------------------------------------------------------

def ref_pool(recs):
    """recs: [(n, mean, sd or None)]. Returns (mean, se, tau2)."""
    num = 0.0
    den = 0
    for n, m, s in recs:
        if s is not None and n >= 2:
            num = num + (n - 1) * s ** 2
            den = den + (n - 1)
    sp = math.sqrt(num / den) if den else None
    ys, vs = [], []
    for n, m, s in recs:
        ys.append(m)
        if s is not None and n >= 2:
            vs.append(s ** 2 / n)
        else:
            vs.append(sp ** 2 / n)
    k = len(ys)
    if k == 1:
        t2 = 0.0
    else:
        W = 0.0
        WY = 0.0
        W2 = 0.0
        for y, v in zip(ys, vs):
            W += 1 / v
            WY += y / v
            W2 += 1 / v ** 2
        yb = WY / W
        Q = 0.0
        for y, v in zip(ys, vs):
            Q += (y - yb) ** 2 / v
        t2 = (Q - (k - 1)) / (W - W2 / W)
        if t2 < 0:
            t2 = 0.0
    S = 0.0
    SY = 0.0
    for y, v in zip(ys, vs):
        S += 1 / (v + t2)
        SY += y / (v + t2)
    return SY / S, math.sqrt(1 / S), t2


def cellish(recs):
    return {"r%d" % i: {"n": n, "mean": m, "sd": s,
                        "warn": None} for i, (n, m, s) in enumerate(recs)}


def pair_pooled(L, R, w, m, key):
    """What pooling every pair as independent would say (the wrong way)."""
    def side(ps):
        xs = []
        for p in ps:
            c = p["cells"][w][m].get(key)
            if c:
                xs.extend(v["v"] for v in c["values"])
        n = len(xs)
        mu = sum(xs) / n
        return mu, _sd(xs) / math.sqrt(n), n
    ml, sl, nl = side(L)
    mr, sr, nr = side(R)
    se = math.sqrt(sl ** 2 + sr ** 2)
    z = (mr - ml) / se
    return mr - ml, z, 2 * stats.norm.sf(abs(z)), nl, nr


# ---------------------------------------------------------------------------
# Negative controls (monkeypatches in this process only).
# ---------------------------------------------------------------------------

def _break(which):
    if which == "tau0":
        orig = D._dl_tau2
        D._dl_tau2 = lambda ys, vs: (0.0, orig(ys, vs)[1])
    elif which == "pairs":
        orig_pool = D.pool

        def pairs_pool(cells_by_recording):
            out = orig_pool(cells_by_recording)
            xs = []
            for _, c in D._as_members(cells_by_recording):
                if c and c.get("values"):
                    xs.extend(v["v"] for v in c["values"])
            if len(xs) >= 2 and out["testable"]:
                n = len(xs)
                mu = sum(xs) / n
                sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
                out.update(mean=mu, se=sd / math.sqrt(n), tau2=0.0, n=n)
            return out
        D.pool = pairs_pool
    elif which == "bh":
        D._bh = lambda ps: list(ps)
    elif which == "vid":
        # Pin by number only: forget the version id.
        orig_get = D._ref_get
        D._ref_get = lambda ref, *keys: (None if keys == ("version_id",)
                                         else orig_get(ref, *keys))
    elif which == "kindparams":
        # Compare every parameter whatever the kind (the old behaviour).
        D.number_params = lambda kind: D.NUMBER_PARAMS
    else:
        raise SystemExit("unknown --break %r" % which)
    print("*** NEGATIVE CONTROL: drift.%s broken (%s) -- checks below "
          "SHOULD fail ***\n" % ({"tau0": "_dl_tau2", "pairs": "pool",
                                  "bh": "_bh", "vid": "_ref_get",
                                  "kindparams": "number_params"}[which],
                                 which))


# ---------------------------------------------------------------------------

def main():
    if "--break" in sys.argv:
        _break(sys.argv[sys.argv.index("--break") + 1])

    print("1. Reference: independent loops vs drift.pool (tol 1e-12)")
    cases = {
        "three recordings, heterogeneous":
            [(8, 0.31, 0.08), (6, 0.42, 0.10), (7, 0.25, 0.05)],
        "five recordings, homogeneous (tau2 -> 0)":
            [(8, 0.300, 0.08), (8, 0.302, 0.08), (8, 0.299, 0.08),
             (8, 0.301, 0.08), (8, 0.300, 0.08)],
        "one recording with n = 1 borrows the pooled SD":
            [(8, 0.31, 0.08), (1, 0.60, None), (5, 0.28, 0.12),
             (3, 0.35, 0.02)],
        "k = 1": [(6, 0.40, 0.09)],
        "k = 2": [(8, 0.10, 0.20), (2, 0.90, 0.05)],
    }
    for name, recs in cases.items():
        rm, rse, rt2 = ref_pool(recs)
        got = D.pool(cellish(recs))
        ck("%s: mean %.6f se %.6f tau2 %.6g" % (name, rm, rse, rt2),
           close(got["mean"], rm) and close(got["se"], rse)
           and close(got["tau2"], rt2),
           "drift: mean %r se %r tau2 %r" % (got["mean"], got["se"],
                                             got["tau2"]))

    # BCG vaccine trials (Colditz et al. 1994), metafor's dat.bcg.
    bcg = [(4, 119, 11, 128), (6, 300, 29, 274), (3, 228, 11, 209),
           (62, 13536, 248, 12619), (33, 5036, 47, 5761),
           (180, 1361, 372, 1079), (8, 2537, 10, 619),
           (505, 87886, 499, 87892), (29, 7470, 45, 7232),
           (17, 1699, 65, 1600), (186, 50448, 141, 27197),
           (5, 2493, 3, 2338), (27, 16886, 29, 17825)]
    recs = []
    for tp, tn, cp, cn in bcg:
        yi = math.log((tp / (tp + tn)) / (cp / (cp + cn)))
        vi = 1 / tp - 1 / (tp + tn) + 1 / cp - 1 / (cp + cn)
        # a cell with n = 2 and sd = sqrt(2 v) has se^2 = v exactly
        recs.append((2, yi, math.sqrt(2 * vi)))
    got = D.pool(cellish(recs))
    ck("published BCG example (metafor DL): tau2 %.4f  est %.4f  se %.4f  "
       "Q %.2f   [published 0.3088 / -0.7141 / 0.1787 / 152.23]"
       % (got["tau2"], got["mean"], got["se"], got["q_het"]),
       round(got["tau2"], 4) == 0.3088 and round(got["mean"], 4) == -0.7141
       and round(got["se"], 4) == 0.1787 and round(got["q_het"], 2) == 152.23)

    print("\n2. Behaviour")
    lv = [0.25, 0.30, 0.35, 0.28, 0.32]
    rv = [0.29, 0.36, 0.33, 0.40, 0.31]
    L = [circuit("L%d" % i, v) for i, v in enumerate(lv)]
    R = [circuit("R%d" % i, v) for i, v in enumerate(rv)]

    same = run(L, [circuit("S%d" % i, v) for i, v in enumerate(lv)])
    worst = max(abs(c["delta"]) for *_, c in cells_of(same))
    minp = min(c["p"] for *_, c in cells_of(same))
    ck("identical groups: max |delta| %.3g, min p %.6f" % (worst, minp),
       worst < 1e-12 and minp > 0.999999)

    shift = 0.1
    sh = run(L, [circuit("S%d" % i, v + shift) for i, v in enumerate(lv)])
    err = max(abs(c["delta"] - shift) for *_, c in cells_of(sh))
    t2 = max(abs(c["left"]["tau2"] - c["right"]["tau2"])
             for *_, c in cells_of(sh))
    ck("shifted copy (+0.1): max |delta - 0.1| %.3g, tau2 unchanged (%.3g)"
       % (err, t2), err < 1e-12 and t2 < 1e-12)

    base = [circuit("B%d" % i, v) for i, v in
            enumerate([0.30, 0.31, 0.29, 0.30])]
    one = circuit("X1", 0.50, usable=1)
    eight = circuit("X8", 0.50)
    key, w, m = "Right ACC|Right OFC", "pre", "coherence"

    def side_mean(ps):
        return D.pool({p["source"]["gid"]: p["cells"][w][m].get(key)
                       for p in ps})
    b0 = side_mean(base)
    b1 = side_mean(base + [one])
    b8 = side_mean(base + [eight])
    wt1 = [x for x in b1["members"] if x["member"] == "X1"][0]["weight"]
    wt8 = [x for x in b8["members"] if x["member"] == "X8"][0]["weight"]
    ck("adding an offset recording: n=1 moves the mean %.4f (weight %.3f), "
       "n=8 moves it %.4f (weight %.3f)"
       % (b1["mean"] - b0["mean"], wt1, b8["mean"] - b0["mean"], wt8),
       0 < b1["mean"] - b0["mean"] < b8["mean"] - b0["mean"] and wt1 < wt8)
    ck("the n=1 recording is used, with a borrowed-SD warning",
       b1["k"] == 5 and any("borrowed" in s for s in
                            [x for x in D.pool({"X1": one["cells"][w][m][key],
                                                "B": base[0]["cells"][w][m][key]}
                                               )["warn"]]))

    print("\n   inflated n: every pair duplicated 10x within its recording")
    # Recordings differ in spread and in usable pairs, so the weights are
    # unequal (with equal se_r, DL's v + tau2 equals the variance of the
    # means exactly and the invariance would be a special-case identity).
    scale = [0.6, 1.0, 1.4, 0.8, 1.2]
    use = [8, 6, 8, 5, 7]

    def fx(w, m, a, b):
        # a cell-specific true change on the right, so a panel's p differ
        # and BH has something to reorder
        return ((sum(ord(c) for c in a + b + m + w) * 7) % 11) / 100.0

    def grp(prefix, levels, rep, effect=None):
        return [circuit("%s%d" % (prefix, i), v, rep=rep, usable=use[i],
                        per_pair=[d * scale[i] for d in DEV8], effect=effect)
                for i, v in enumerate(levels)]
    L, R = grp("L", lv, 1), grp("R", rv, 1, fx)
    Ld, Rd = grp("L", lv, 10), grp("R", rv, 10, fx)
    a = run(L, R)
    b = run(Ld, Rd)
    print("   %-22s %8s %12s %12s %12s %12s"
          % ("cell", "delta", "nested p", "nested p x10",
             "pair-pool p", "pair-pool x10"))
    ratios_n, ratios_p = [], []
    shown = 0
    for (w_, m_, k_, c) in cells_of(a):
        cd = b["cells"][w_][m_][k_]
        _, _, pp, _, _ = pair_pooled(L, R, w_, m_, k_)
        _, _, ppd, nl, nr = pair_pooled(Ld, Rd, w_, m_, k_)
        ratios_n.append(cd["p"] / c["p"])
        ratios_p.append(ppd / pp)
        if shown < 4 and m_ == "coherence" and w_ == "pre":
            print("   %-22s %8.4f %12.4g %12.4g %12.4g %12.4g"
                  % (k_, c["delta"], c["p"], cd["p"], pp, ppd))
            shown += 1
    rn = sorted(ratios_n)[len(ratios_n) // 2]
    rp = sorted(ratios_p)[len(ratios_p) // 2]
    print("   (pairs per side: %d -> %d; median p ratio x10/x1: nested %.3f, "
          "pair-pooled %.3g)" % (sum(use), 10 * sum(use), rn, rp))
    # One-sided on purpose. Nested p may RISE with inflated n: as every
    # se_r -> 0, DL weights tend to 1/tau2 (equal), so the pooled mean moves
    # from precision-weighted towards the plain mean of recordings. What it
    # must never do is fall towards significance because pairs multiplied.
    ck("nested p is not pushed down by inflated n (median ratio %.3f >= 0.5)"
       % rn, rn >= 0.5)
    ck("nested p stays within an order of magnitude (%.3f in 0.1-10)" % rn,
       0.1 <= rn <= 10)
    ck("pair-pooling WOULD be driven by it (median ratio %.3g < 0.01) -- "
       "the reference comparator, not drift" % rp, rp < 0.01)

    print("\n   Benjamini-Hochberg")
    hand_p = [0.01, 0.04, 0.03, 0.005, 0.5]
    hand_q = [0.025, 0.05, 0.05, 0.025, 0.5]         # worked by hand
    got_q = D._bh(hand_p)
    ck("BH on %s -> %s (hand: %s)" % (hand_p, [round(q, 6) for q in got_q],
                                      hand_q),
       all(close(g, h) for g, h in zip(got_q, hand_q)))
    ck("BH passes None through and counts only real tests",
       D._bh([None, 0.02, None, 0.01]) == [None, 0.02, None, 0.02])
    qs = [(c["p"], c["q"]) for *_, c in cells_of(a)]
    ck("q >= p in every cell of a real build (%d cells)" % len(qs),
       all(q >= p - 1e-15 for p, q in qs))
    ck("... and q > p somewhere (the correction did something: %d of %d)"
       % (sum(1 for p, q in qs if q > p * (1 + 1e-9)), len(qs)),
       any(q > p * (1 + 1e-9) for p, q in qs))
    # q recomputed by hand for one panel
    panel = a["cells"]["cue1"]["raw_cc"]
    ps = [c["p"] for c in panel.values()]
    mm = len(ps)
    srt = sorted(range(mm), key=lambda i: ps[i])
    hq = [0.0] * mm
    run_min = 1.0
    for r in range(mm, 0, -1):
        run_min = min(run_min, ps[srt[r - 1]] * mm / r)
        hq[srt[r - 1]] = min(1.0, run_min)
    ck("q of panel cue1/raw_cc matches a hand BH over its %d cells" % mm,
       all(close(c["q"], h) for c, h in zip(panel.values(), hq)))

    print("\n   grey regions, absent cells, k = 1, nothing to borrow")
    Lg = [circuit("L0", 0.3, grey=["Left POR"]), circuit("L1", 0.32),
          circuit("L2", 0.28)]
    Rg = [circuit("R0", 0.35, grey=["Left POR"]), circuit("R1", 0.33,
                                                          grey=["Left POR"])]
    g = run(Lg, Rg)
    kk = "Right ACC|Left POR"
    ck("'grey' lists Left POR, with the members it was grey in (%s)"
       % ", ".join(d["member"] for d in g["grey_detail"]["Left POR"]),
       g["grey"] == ["Left POR"]
       and len(g["grey_detail"]["Left POR"]) == 3)
    ck("grey on EVERY right member: cell absent (not zero), with a reason",
       kk in g["absent"]["pre"]["coherence"]
       and "grey" in g["absent"]["pre"]["coherence"][kk],
       g["absent"]["pre"]["coherence"].get(kk))
    Rg2 = [circuit("R0", 0.35, grey=["Left POR"]), circuit("R1", 0.33)]
    g2 = run(Lg, Rg2)
    c2 = g2["cells"]["pre"]["coherence"][kk]
    ck("grey in one of two right members: k left %d, right %d, warn says so"
       % (c2["left"]["k"], c2["right"]["k"]),
       c2["left"]["k"] == 2 and c2["right"]["k"] == 1
       and any("pooled over" in s for s in c2["warn"]))

    k1 = run(L, [circuit("R0", 0.4)])
    c = k1["cells"]["pre"]["coherence"]["Right ACC|Right OFC"]
    ck("k = 1 side: tau2 %.3g, warned" % c["right"]["tau2"],
       c["right"]["tau2"] == 0.0 and c["right"]["k"] == 1
       and any("k = 1" in s for s in c["warn"]))

    thin = run(L, [circuit("R0", 0.4, usable=1), circuit("R1", 0.5, usable=1)])
    c = thin["cells"]["pre"]["coherence"]["Right ACC|Right OFC"]
    ck("no right recording has n >= 2: mean %.3f reported, p None, why given"
       % c["right"]["mean"],
       c["p"] is None and c["q"] is None and not c["testable"]
       and c["right"]["mean"] is not None
       and any("test impossible" in s for s in c["warn"]))
    ck("... and the untestable cells are left out of BH's m (%d tests)"
       % thin["panels"]["pre"]["coherence"]["tests"],
       thin["panels"]["pre"]["coherence"]["tests"] == 0)

    print("\n   refusals")

    def refused(Lx, Rx, field, lrefs=None, rrefs=None):
        ok, why = D.compatible(Lx, Rx, lrefs or refs(Lx, "a"),
                               rrefs or refs(Rx, "b"))
        hit = [s for s in why if field in s]
        return (not ok) and bool(hit), (hit or why or ["accepted"])[0]

    tests = [
        ("notch_hz across sides", L, [circuit("R0", .3,
                                               params={"notch_hz": None})],
         "notch_hz"),
        ("low within left", L[:2] + [circuit("L9", .3, params={"low": 6.0})],
         R, "low"),
        ("pad_s on state circuits", [circuit("L0", .3, params={"pad_s": 5.0})],
         R, "pad_s"),
        ("before_s on transition circuits",
         [circuit("L0", .3, kind="transition",
                  windows=["onset", "switch", "offset"],
                  params={"before_s": 0.5})],
         [circuit("R0", .3, kind="transition",
                  windows=["onset", "switch", "offset"])], "before_s"),
        ("analysis_fs", L, [circuit("R0", .3,
                                    params={"analysis_fs": 500.0})],
         "analysis_fs"),
        ("kind", L, [circuit("R0", .3, kind="transition",
                             windows=["onset", "switch", "offset"])], "kind"),
        ("cue_type", L, [circuit("R0", .3, cue_type="Click_Noise")],
         "cue_type"),
        ("windows", L, [circuit("R0", .3, windows=["pre", "cue1"])],
         "windows"),
        ("methods", L, [circuit("R0", .3, methods=["coherence"])], "methods"),
        ("empty side", [], R, "empty"),
    ]
    for name, Lx, Rx, field in tests:
        ok, s = refused(Lx, Rx, field)
        ck("refuses %s: %s" % (name, s), ok)
    ok, s = refused(L, R, "both sides", refs(L, "a"), refs(R, "a"))
    ck("refuses the same (artifact, version) on both sides: %s" % s, ok)
    ok, s = refused(L + [L[0]], R, "more than once")
    ck("refuses one recording twice in a side: %s" % s, ok)
    ok, _ = D.compatible(L, R, refs(L, "a"), refs(R, "b"))
    ck("accepts a compatible pair of groups", ok)

    print("\n   parameters are compared only where the kind reads them")
    # Spark writes before/after as None on a state entry; a state circuit
    # never reads them, so a difference there must not refuse.
    st_none = [circuit("L0", .3, params={"before_s": None, "after_s": None})]
    st_set = [circuit("R0", .3, params={"before_s": 1.0, "after_s": 2.0})]
    ok, why = D.compatible(st_none, st_set, refs(st_none, "a"),
                           refs(st_set, "b"))
    ck("state: before/after None vs 1/2 is ACCEPTED (not read by state)",
       ok, "; ".join(why))
    tw = ["onset", "switch", "offset"]
    tr_a = [circuit("L0", .3, kind="transition", windows=tw,
                    params={"pad_s": 10.0})]
    tr_b = [circuit("R0", .3, kind="transition", windows=tw,
                    params={"pad_s": None})]
    ok, why = D.compatible(tr_a, tr_b, refs(tr_a, "a"), refs(tr_b, "b"))
    ck("transition: pad_s 10 vs None is ACCEPTED (not read by transition)",
       ok, "; ".join(why))
    b1 = safe_build(st_none, st_set, refs(st_none, "a"), refs(st_set, "b"))
    ck("a state drift's params carry pad_s and not before/after",
       b1 is not None and "pad_s" in b1["params"]
       and "before_s" not in b1["params"]
       and "after_s" not in b1["params"], b1 and sorted(b1["params"]))

    print("\n   pinned by version_id")
    one = [circuit("L0", .3)]
    two = [circuit("R0", .3)]
    ra = [{"artifact_id": "X", "version": 2, "version_id": "vidA",
           "digest": "d1", "name": "L0"}]
    rb = [{"artifact_id": "X", "version": 3, "version_id": "vidA",
           "digest": "d1", "name": "R0"}]
    ok, why = D.compatible(one, two, ra, rb)
    ck("the same version_id on both sides is refused even when the numbers "
       "differ (numbers clash across machines): %s"
       % ((why or ["accepted"])[0]), not ok and any("both sides" in s
                                                   for s in why))
    rc = [{"artifact_id": "X", "version": 2, "version_id": "vidB",
           "digest": "d2", "name": "R0"}]
    ok, why = D.compatible(one, two, ra, rc)
    ck("the same number with a different version_id is two versions, "
       "not a duplicate", ok, "; ".join(why))
    b2 = safe_build(one, two, ra, rc)
    ck("members carry version_id", b2 is not None
       and b2["left"]["members"][0]["version_id"]
       == "vidA" and b2["right"]["members"][0]["version_id"] == "vidB")

    print("\n   cue types are counterbalanced: refuse, or a recorded choice")
    cl = [circuit("L%d" % i, .3, cue_type="Click_HighTone") for i in range(2)]
    for c_ in cl:
        c_["cue_label"] = "Click → High tone"
    cr = [circuit("R%d" % i, .3, cue_type="HighTone_Noise") for i in range(2)]
    for c_ in cr:
        c_["cue_label"] = "High tone → Noise"
    ok, why = D.compatible(cl, cr, refs(cl, "a"), refs(cr, "b"))
    s = next((x for x in why if "cue_type" in x), "")
    ck("different pairings are refused with a sentence naming both",
       not ok and "Click → High tone" in s and "High tone → Noise" in s, s)
    eq = [{"from": "HighTone_Noise", "to": "Click_HighTone",
           "by": "harness", "at": "2026-09-28T00:00:00+00:00"},
          {"from": "LowTone_Click", "to": "Noise_LowTone", "by": "h",
           "at": "x"}]
    ok, why = D.compatible(cl, cr, refs(cl, "a"), refs(cr, "b"), eq)
    ck("with the equivalence recorded, they are compared", ok, "; ".join(why))
    be = D.build(cl, cr, refs(cl, "a"), refs(cr, "b"), ("l", "r"),
                 cue_equivalence=eq)
    ck("the payload records the choice (from/to sorted, by, at) and only "
       "the one that was used: %s" % be["cue_equivalence"],
       be["cue_equivalence"] == [{"from": "Click_HighTone",
                                  "to": "HighTone_Noise", "by": "harness",
                                  "at": "2026-09-28T00:00:00+00:00"}])
    ck("and names both pairings: cue_types %s, label %r"
       % (be["cue_types"], be["cue_label"]),
       be["cue_types"] == ["Click_HighTone", "HighTone_Noise"]
       and "≡" in be["cue_label"])
    ck("an equivalence is transitive (A=B, B=C joins A and C)",
       len(set(D.cue_classes([{"from": "A", "to": "B"},
                              {"from": "B", "to": "C"}]).values())) == 1)
    try:
        D.build(cl, cr, refs(cl, "a"), refs(cr, "b"), ("l", "r"),
                cue_equivalence=[{"from": "Click_HighTone"}])
        ck("a malformed equivalence is refused", False)
    except D.DriftError as e:
        ck("a malformed equivalence is refused: %s" % e, True)

    print("\n   the weaknesses are said, not hidden")
    k1 = D.build(L, [circuit("R0", .4)], refs(L, "a"), refs([R[0]], "b"),
                 ("l", "r"))
    ck("a k = 1 side is flagged (right.one_recording) and said at the top",
       k1["right"]["one_recording"] and not k1["left"]["one_recording"]
       and any(D.K1_SAY in s for s in k1["warn"]))
    c = k1["cells"]["pre"]["coherence"]["Right ACC|Right OFC"]
    ck("  and on every cell, in those words",
       any(D.K1_SAY in s for s in c["warn"]))
    ck("the z-test note is on the result", D.Z_NOTE in k1["notes"])
    ck("the test is named on the result (%s)" % k1["test"],
       k1["test"]["name"] == "z_test")

    def half(lp, rp):
        return {"se": 1.0, "stat": 0.0, "p": 0.5}
    half.label = "constant"
    sw = D.build(L, R, refs(L, "a"), refs(R, "b"), ("l", "r"), test=half)
    ck("the test is one swappable function: every p is the stand-in's 0.5",
       all(c["p"] == 0.5 for *_, c in cells_of(sw))
       and sw["test"]["name"] == "half")
    seen_prog = []
    D.build(L, R, refs(L, "a"), refs(R, "b"), ("l", "r"),
            progress=lambda d, o: seen_prog.append((d, o)))
    ck("progress reports each panel, ending at the total (%s)"
       % (seen_prog[-1:],),
       len(seen_prog) == 12 and seen_prog[-1][0] == seen_prog[-1][1])
    sm = D.summary(a)
    ck("summary counts the groups and the tests (%s)" % sm,
       sm["left_k"] == 5 and sm["right_k"] == 5 and sm["tests"] > 0)
    try:
        D.build(L, [circuit("R0", .3, params={"notch_hz": None})],
                refs(L, "a"), [None], ("l", "r"))
        ck("build raises DriftError when refused", False)
    except D.DriftError as e:
        ck("build raises DriftError when refused", "notch_hz" in str(e))

    try:
        s = json.dumps(a, allow_nan=False)
        ck("payload is strict JSON (%d kB, %d cells)"
           % (len(s) // 1024, sum(1 for _ in cells_of(a))), True)
        s = json.dumps(thin, allow_nan=False)
        ck("untestable payload is strict JSON", True)
    except ValueError as e:
        ck("payload is strict JSON", False, str(e))

    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), "; ".join(FAILED)))
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
