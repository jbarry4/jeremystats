"""
ied_ds_features.py -- amplitude and half-width of the largest contact, per
event, and the PCA that asks whether they separate IEDs from dentate spikes.

WHAT IS MEASURED, IN ORDER
==========================
  1. centre the event          (v2's method: the peak of the across-contact
                                mean|amp|, searched +-50 ms from the stamp)
  2. find the largest contact  (v4's: max |x - baseline| in the window, over
                                the 62 good contacts)
  3. on THAT contact, measure  amplitude and half-width at half-amplitude,
                                using v1's crossing code unchanged

Step 3 reuses `ied_ampwidth.measure_peak` rather than reimplementing it,
which means v6 inherits the two things v1 got right and the MATLAB did not:
the half-amplitude level is measured from a real baseline rather than from
zero, and a crossing the search never found comes back flagged `unresolved`
instead of silently interpolated at the window edge.

RESOLUTION, HONESTLY
====================
This runs off the 2 kHz store (300 Hz lowpass) that v3 and v4 use, because
that is the band an LFP amplitude belongs in and the cache already exists.
0.5 ms per sample is coarse next to v1's 30 kHz: the crossings are linearly
interpolated so sub-sample precision is real, but a 2 ms half-width spans four
samples and should be read as ~+-0.1 ms, not to two decimals. Half-widths in
the tens of ms -- most of them -- are unaffected.

WHAT PCA CAN AND CANNOT DO WITH TWO FEATURES
============================================
With exactly two features, PCA is a rotation. PC1 and PC2 carry the same
information as the amplitude/half-width scatter, drawn on different axes, and
no separation can appear in the PCA that is not already visible in the
scatter. That is why both are drawn, and why the honest summary statistic is
the AUC of each feature rather than the variance explained by each component:
variance explained says how elongated the cloud is, not whether the classes
sit in different parts of it.

PCA becomes worth running once more features are added -- the extras below --
and it is unsupervised either way: it finds the directions of greatest
VARIANCE, which need not be the directions that separate the classes. An LDA
axis is also reported for exactly that reason; where PC1 and the LDA axis
disagree, the variance is being driven by something other than class.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ied_ampwidth import BASELINES, measure_peak                 # noqa: E402
from ied_ds import BAD_CHANNELS, Probe64, read_ds_bank, read_ied_events  # noqa: E402
from ied_ds_store import DEC_Q, HALF_MS, EventStore              # noqa: E402

# Features. The first two are the ask; the rest are available but off by
# default, because adding a feature to a PCA changes every component.
CORE = ("amp_uV", "hw_ms")
EXTRA = ("peak_ms", "rise_ms", "fall_ms", "asym", "depth_row", "polarity")
# v5's 500-1000 Hz power, available as a feature so the amplitude/half-width
# question can be asked against the measure that already answered it. Kept
# apart because it needs v5's separate 5 kHz cache, which is 193 MB and is not
# loaded unless the feature is actually switched on.
HF_FEATURE = "hf_db"
ALL_FEATURES = CORE + EXTRA


def build_store(probe=None, category="Solid", progress=None, refresh=False):
    p = probe or Probe64()
    st = EventStore.build(p, read_ied_events(category=category),
                          read_ds_bank(), half_ms=HALF_MS, lowpass=300.0,
                          q=DEC_Q, progress=progress, refresh=refresh)
    return p, st


def winning_contact(st, p, i, shift, win_ms):
    """The largest contact, and whether it clipped in-window (v4's rule)."""
    y = st.trace(i)
    c = st.stamp_i + int(shift)
    h = int(round(win_ms * 1e-3 * st.fs))
    lo, hi = max(0, c - h), min(y.shape[0], c + h + 1)
    dev = np.abs(y[lo:hi] - st._base[i])
    per = np.where(p.included, dev.max(axis=0), -np.inf)
    w = int(np.argmax(per))
    railed = bool(st.rail[i, lo:hi, w].any())
    return w, railed


def event_features(st, p, i, shift, win_ms=25.0, cross_ms=50.0,
                   baseline="local", flank_ms=(30.0, 60.0)):
    """Amplitude and half-width of the largest contact, plus shape extras."""
    w, railed = winning_contact(st, p, i, shift, win_ms)
    y = st.trace(i)[:, w]
    anchor = st.stamp_i + int(shift)

    got = {}
    for pol in ("max", "min"):
        m = measure_peak(y, anchor, st.fs, pol, win_ms, cross_ms, baseline,
                         flank_ms, raw=None)
        got[pol] = m
    # The polarity that actually carries the event on this contact.
    def size(m):
        return m["amp_uV"] if (m and m.get("status") == "ok") else -np.inf
    pol = "max" if size(got["max"]) >= size(got["min"]) else "min"
    m = got[pol]
    if m is None or m.get("status") != "ok":
        return None

    rise = m["peak_ms"] - m["left_ms"]
    fall = m["right_ms"] - m["peak_ms"]
    tot = rise + fall
    return {
        "contact_row": w,
        "csc": int(p.numbers[w]),
        "region": p.region.get(int(p.numbers[w]), ""),
        "railed": railed,
        "polarity": 1.0 if pol == "max" else -1.0,
        "amp_uV": float(m["amp_uV"]),
        "hw_ms": float(m["hw_ms"]),
        "peak_ms": float(m["peak_ms"]),
        "rise_ms": float(rise),
        "fall_ms": float(fall),
        # Rise/fall asymmetry in [-1, 1]: 0 is symmetric, positive is a slow
        # rise and fast decay.
        "asym": float((rise - fall) / tot) if tot > 0 else np.nan,
        "depth_row": float(w),
        "unresolved": bool(m["unresolved"]),
    }


def all_features(st, p, shifts, **kw):
    """One row per event. Events with no measurable peak are dropped, counted."""
    rows, dropped = [], 0
    for i in range(len(st)):
        f = event_features(st, p, i, shifts[i], **kw)
        if f is None:
            dropped += 1
            continue
        f.update({"kind": str(st.kinds[i]), "id": int(st.ids[i]),
                  "t_s": float(st.t_s[i]), "idx": i,
                  "shift_ms": shifts[i] / st.fs * 1e3})
        rows.append(f)
    return pd.DataFrame(rows), dropped


def attach_hf(tab, probe, category="Solid", win_ms=25.0, progress=None):
    """Add v5's 500-1000 Hz dB as a column, matched by (kind, id).

    Matched on the event's identity, never on row order: the HF store is built
    from the same two banks but a dropped event or a different category would
    shift the rows, and a silent off-by-one here would mislabel every event
    rather than fail.
    """
    from ied_ds_hf import BASELINE_OFFSET_MS, BASELINE_WIN_MS, HFMeasure, build_hf_store
    p, hst = build_hf_store(probe, category=category, progress=progress)
    shifts, _ = hst.centre_all(np.zeros(len(hst), dtype=int), 50.0,
                               "mean|amp| peak", True)
    hm = HFMeasure(hst, p, win_ms=win_ms,
                   base_offset_ms=BASELINE_OFFSET_MS,
                   base_win_ms=BASELINE_WIN_MS)
    val = {}
    for i in range(len(hst)):
        d, _, _ = hm.measure(i, shifts[i])
        val[(str(hst.kinds[i]), int(hst.ids[i]))] = (
            float(np.nanmax(d)) if np.isfinite(d).any() else np.nan)
    out = tab.copy()
    out[HF_FEATURE] = [val.get((k, i), np.nan)
                       for k, i in zip(out["kind"], out["id"])]
    return out


# --------------------------------------------------------------------------
# PCA and separability
# --------------------------------------------------------------------------
def auc(x, y):
    """Rank AUC of feature `x` separating the two classes in boolean `y`.

    Mann-Whitney U over n1*n2, which is the probability a random positive
    outranks a random negative. Used instead of accuracy because the classes
    here are 13 against 296 and accuracy is 96% for a model that says "DS"
    every time.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=bool)
    ok = np.isfinite(x)
    x, y = x[ok], y[ok]
    if y.sum() == 0 or (~y).sum() == 0:
        return np.nan
    r = pd.Series(x).rank().values
    n1, n0 = int(y.sum()), int((~y).sum())
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def run_pca(tab, features, standardize=True):
    """PCA on the chosen features, plus an LDA axis for comparison.

    Standardised by default: amplitude is in the hundreds of microvolts and
    half-width in single-figure milliseconds, so unstandardised PCA would
    report that amplitude is the first component purely because microvolts are
    a bigger number than milliseconds.
    """
    from sklearn.decomposition import PCA
    X = tab[list(features)].to_numpy(dtype=float)
    keep = np.isfinite(X).all(axis=1)
    X, sub = X[keep], tab[keep]
    if X.shape[0] < 3 or X.shape[1] < 1:
        return None
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd if standardize else X - mu
    n_comp = min(len(features), Z.shape[0])
    pca = PCA(n_components=n_comp)
    scores = pca.fit_transform(Z)
    is_ied = (sub["kind"] == "IED").to_numpy()

    out = {"scores": scores, "table": sub, "is_ied": is_ied,
           "explained": pca.explained_variance_ratio_,
           "loadings": pca.components_, "features": list(features),
           "mu": mu, "sd": sd, "keep": keep}
    out["auc_feature"] = {f: auc(sub[f].to_numpy(), is_ied) for f in features}
    out["auc_pc"] = [auc(scores[:, k], is_ied) for k in range(scores.shape[1])]

    # LDA: the direction that best separates, as against PCA's direction of
    # greatest variance. They coincide only by luck.
    try:
        from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
        lda = LinearDiscriminantAnalysis()
        proj = lda.fit_transform(Z, is_ied).ravel()
        out["lda"] = proj
        out["lda_auc"] = auc(proj, is_ied)
        out["lda_coef"] = lda.coef_.ravel()
    except Exception:
        out["lda"] = None
        out["lda_auc"] = np.nan
        out["lda_coef"] = None
    return out


def _selftest():
    import time
    def prog(i, n, msg):
        if i % 80 == 0 or i >= n - 1:
            print("  [%3d/%3d] %s" % (i, n, msg))
    p, st = build_store(progress=prog)
    shifts, _ = st.centre_all(np.zeros(len(st), dtype=int), 50.0,
                              "mean|amp| peak", True)
    print("store %d events @ %.0f Hz (%.2f ms/sample)"
          % (len(st), st.fs, 1e3 / st.fs))

    for base in BASELINES:
        t = time.time()
        tab, dropped = all_features(st, p, shifts, baseline=base)
        a = tab[tab["kind"] == "IED"]
        d = tab[tab["kind"] == "DS"]
        print("\nbaseline=%-11s  %d events (%d dropped)  %.1f s"
              % (base, len(tab), dropped, time.time() - t))
        for nm, g in (("IED", a), ("DS", d)):
            print("  %-4s n=%3d  amp %7.1f uV   HW %6.2f ms   unresolved %2d  railed %3d"
                  % (nm, len(g), g["amp_uV"].median(), g["hw_ms"].median(),
                     int(g["unresolved"].sum()), int(g["railed"].sum())))
        is_ied = (tab["kind"] == "IED").to_numpy()
        for f in CORE:
            print("  AUC %-8s %.3f" % (f, auc(tab[f].to_numpy(), is_ied)))

    tab, _ = all_features(st, p, shifts, baseline="local")
    print("\n--- PCA on the two core features ---")
    r = run_pca(tab, CORE)
    print("  explained variance: %s"
          % ", ".join("PC%d %.3f" % (k + 1, v) for k, v in enumerate(r["explained"])))
    print("  loadings:")
    for k, row in enumerate(r["loadings"]):
        print("    PC%d  %s" % (k + 1, "  ".join(
            "%s %+.3f" % (f, c) for f, c in zip(r["features"], row))))
    print("  AUC  PC1 %.3f  PC2 %.3f   LDA %.3f"
          % (r["auc_pc"][0], r["auc_pc"][1], r["lda_auc"]))

    print("\n--- PCA with the shape extras added ---")
    r2 = run_pca(tab, ALL_FEATURES)
    print("  explained: %s" % ", ".join("%.3f" % v for v in r2["explained"]))
    print("  AUC per feature: %s"
          % "  ".join("%s %.3f" % (f, v) for f, v in r2["auc_feature"].items()))
    print("  AUC  PC1 %.3f  PC2 %.3f   LDA %.3f"
          % (r2["auc_pc"][0], r2["auc_pc"][1], r2["lda_auc"]))


if __name__ == "__main__":
    _selftest()
