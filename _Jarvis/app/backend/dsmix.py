# -*- coding: utf-8 -*-
"""dsmix.py -- three layers over any DS1/DS2 split (asked 2026-11-13).

1  DS3, THE HYBRID (Tarcsay et al. 2025, bioRxiv 10.1101/2025.10.27.684857).
   Entorhinal inputs do not fire strictly apart: when LEC and MEC fire nearly
   together the event has a sink in both the outer molecular layer (OML, the
   LEC input, DS1's) and the middle molecular layer (MML, the MEC input,
   DS2's). For every event, at the DS peak (the mean CSD over the same +-3 ms
   window the Bite line uses), at ONE contact a layer:

       sink  = max(0, -CSD)                      a source is "no input here"
       score = (OML - MML) / (OML + MML)         +1 pure OML ... -1 pure MML

   |score| <= DS3_CUT (0.5) is DS3; above is DS1-like, below DS2-like. It is
   a threshold on the balance and nothing else: not a third cluster, not a
   distance from a split's line, not "both sinks large" (a DS3's sinks are
   usually the smaller), and no timing rule (the OML-MML peak lag is kept for
   looking at, never used). No neighbour averaging: on a 50 um probe it would
   mix the two layers and push events toward balance.
   WHERE THE LAYERS ARE: OML is the contact where the split's DS1 class-mean
   sink is deepest, MML where its DS2 class-mean sink is deepest in the same
   blade (hump).
   THE FLOOR: two sinks near noise can score as balanced. A matched null --
   the same measure at baseline windows 40 ms before and after every event
   -- gives the 99th percentile of OML + MML sink with no DS there; an event
   under it is UNSCORABLE: counted, shown apart, never DS3.
   As a layer, DS3 takes the balanced events out of DS1 and DS2; the rest
   keep the class their split gave them.

2  THE PROBABILITY TRIM. A two-Gaussian fit on the axis the split itself
   uses (PC1/PC2, the gap, a position, the Bite line's coordinate). An
   event whose more probable Gaussian is under TRIM_CUT (80%) is UNSURE:
   kept and shown grey, out of DS1's and DS2's numbers. The split still
   decides every class; the fit only trims. If a class would be left under
   MIN_CLASS events the trim is refused on that recording, and said.

3  THE MIX-UP, the sanity check for the other two: from the same fit, the
   share of events expected to be in the wrong class (the mean of 1 - the
   probability of an event's own class's Gaussian), with a bootstrap
   interval. Three ways on one yardstick -- as split, with DS3 out, with
   the unsure trimmed -- so what each bought is read off. Against the 10-15%
   that waveform-only classification accepts: up to 10% clean, 10-15%
   within, over 15% mixed.

DS3 and the trim are used one at a time for now (the user: "we will do this
seperately ... We may combine them later").
"""
from __future__ import annotations

import numpy as np

DS3_CUT = 0.5            # |score| at or under this is DS3 (Tarcsay et al. 2025)
NULL_PCT = 99.0          # the floor: this percentile of the baseline's sink
NULL_AT_MS = 40.0        # baseline windows this far before and after the DS
LAG_MS = 10.0            # the OML-MML lag is looked for within this of the DS
TRIM_CUT = 0.80          # the more probable Gaussian under this: unsure
NEAR = 3                 # OML and MML closer than this (contacts): one sink
MIN_CLASS = 5            # a trim leaving a class under this is refused
MIX_CLEAN, MIX_OK = 0.10, 0.15
N_BOOT = 200
MODES = ("plain", "ds3", "trim")
CITE = ("Tarcsay et al. 2025, bioRxiv 10.1101/2025.10.27.684857: DS3 is a "
        "relative-sink score between -0.5 and 0.5.")
C_DS3, C_UNSURE = 3, 4   # class ids beside DS1 (1) and DS2 (2)
NAMES = {3: "DS3", 4: "unsure"}


def _r(v, n=4):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else float("%.*g" % (n, v))


def clean_mode(m):
    """{mode, ds3_cut, trim_cut} as kept: a mode of MODES, cuts in range."""
    m = m if isinstance(m, dict) else {}
    mode = m.get("mode") if m.get("mode") in MODES else "plain"

    def num(k, d, lo, hi):
        try:
            return min(hi, max(lo, float(m.get(k, d))))
        except (TypeError, ValueError):
            return d
    return {"mode": mode, "ds3_cut": round(num("ds3_cut", DS3_CUT, 0.05, 0.95), 3),
            "trim_cut": round(num("trim_cut", TRIM_CUT, 0.5, 0.99), 3)}


# --------------------------------------------------------------------------
# 1  DS3
# --------------------------------------------------------------------------
def relsink(A, types, half_ms=None, surround_ms=50.0):
    """Every event's relative-sink score under a split's classes `types`.

    Returns {"why": ...} when the layers cannot be found, else: oml, mml
    (contacts), score (per event, nan where unscorable), sink (OML + MML),
    floor, unscorable (bool per event), lag_ms (OML peak - MML peak; nan
    where either has no sink)."""
    from . import sinkcut
    half = sinkcut.HALF_MS if half_ms is None else float(half_ms)
    prof, ns = sinkcut.stamp_profiles(A, half, surround_ms)
    t = np.asarray(types, dtype=int)
    n, D = prof.shape
    if not ((t == 1).any() and (t == 2).any()):
        return {"why": "The split has one class here, so there is no DS1 and "
                       "DS2 sink to find OML and MML by."}
    m1, m2 = prof[t == 1].mean(axis=0), prof[t == 2].mean(axis=0)
    # In each blade (hump): where DS1's mean sink is deepest and where
    # DS2's is. The blade taken is the one where the two sit apart and the
    # classes differ most there -- the other blade's sink is often the
    # deepest for BOTH classes, which says nothing about OML against MML.
    cut = sinkcut.hump_cut(prof.mean(axis=0))
    blades = [(0, D)] if cut is None else [(0, cut), (cut, D)]
    best, same = None, None
    for a, b in blades:
        if b - a < 2:
            continue
        oo, mk = a + int(np.argmin(m1[a:b])), a + int(np.argmin(m2[a:b]))
        if not (m1[oo] < 0 and m2[mk] < 0):
            continue
        if oo == mk:
            same = oo
            continue
        gain = (m2[oo] - m1[oo]) + (m1[mk] - m2[mk])
        if best is None or gain > best[0]:
            best = (gain, oo, mk)
    if best is None:
        if same is not None:
            return {"why": "DS1's and DS2's mean sinks are deepest at the same "
                           "contact (%d) in each blade, so OML and MML cannot be "
                           "told apart here." % ns[same]}
        return {"why": "A class's mean has no sink in the band, so OML and "
                       "MML cannot be placed."}
    o, mm = best[1], best[2]
    so, sm = np.maximum(0.0, -prof[:, o]), np.maximum(0.0, -prof[:, mm])
    tot = so + sm
    # The matched null: the same measure where there is no DS.
    disp = np.nan_to_num(np.asarray(A["disp"], dtype=np.float64))
    na = [int(x) for x in A["nums_all"]] or ns
    ro, rm = na.index(ns[o]), na.index(ns[mm])
    T = disp.shape[2]
    tt = np.linspace(-surround_ms, surround_ms, T)
    null = []
    for c in (-NULL_AT_MS, NULL_AT_MS):
        w = np.abs(tt - c) <= half + 1e-9
        if w.any():
            null.append(np.maximum(0.0, -disp[:, ro, w].mean(axis=1))
                        + np.maximum(0.0, -disp[:, rm, w].mean(axis=1)))
    floor = float(np.percentile(np.concatenate(null), NULL_PCT)) if null else 0.0
    bad = ~(tot > max(floor, 0.0))
    score = np.full(n, np.nan)
    ok = ~bad
    score[ok] = (so[ok] - sm[ok]) / tot[ok]
    # The lag, for looking at only: each layer's own deepest sink near the DS.
    w = np.abs(tt) <= LAG_MS
    lag = np.full(n, np.nan)
    if w.any():
        xo, xm = disp[:, ro, :][:, w], disp[:, rm, :][:, w]
        has = (xo.min(axis=1) < 0) & (xm.min(axis=1) < 0)
        lag[has] = tt[w][np.argmin(xo, axis=1)][has] - tt[w][np.argmin(xm, axis=1)][has]
    return {"oml": int(ns[o]), "mml": int(ns[mm]), "score": score, "sink": tot,
            "floor": floor, "unscorable": bad, "lag_ms": lag}


def ds3_layer(rs, types, cut=DS3_CUT):
    """The split's classes with DS3 laid over them: (types with 3 where the
    score is balanced, summary for the page)."""
    t = np.asarray(types, dtype=int)
    if rs.get("why"):
        return t, {"why": rs["why"], "cut": float(cut), "cite": CITE}
    sc = rs["score"]
    is3 = np.isfinite(sc) & (np.abs(sc) <= float(cut))
    out = np.where(is3, C_DS3, t)
    uns = rs["unscorable"]
    lag = rs["lag_ms"][is3 & np.isfinite(rs["lag_ms"])]
    return out, {
        "cut": float(cut), "oml": rs["oml"], "mml": rs["mml"], "cite": CITE,
        # Under NEAR contacts apart the two "layers" are one sink seen twice:
        # the balance then says nothing about OML against MML.
        "gap": abs(int(rs["oml"]) - int(rs["mml"])),
        "near": abs(int(rs["oml"]) - int(rs["mml"])) < NEAR,
        "floor": _r(rs["floor"]), "n": int(t.size),
        "counts": {str(c): int((out == c).sum()) for c in (1, 2, 3)},
        "from": {str(c): int((is3 & (t == c)).sum()) for c in (1, 2)},
        "unscorable": {"n": int(uns.sum()),
                       "1": int((uns & (t == 1)).sum()),
                       "2": int((uns & (t == 2)).sum())},
        "score": [_r(v, 3) for v in sc],
        "lag_ms_median": _r(np.median(lag), 3) if lag.size else None}


# --------------------------------------------------------------------------
# 2 and 3  The two-Gaussian fit: the trim and the mix-up
# --------------------------------------------------------------------------
def axis_of(A, method):
    """The axis a split is made on, events x 1 or 2: PC1/PC2 for a PCA, the
    one number for delta and delta middle, the Bite line's coordinate (not
    its place in the order, which is evenly spaced by construction)."""
    from . import extraction as EX
    base = EX.split_base(method)
    if base == "bite":
        F = A.get("_" + method)
        if F is None:
            if method == "bite":
                EX.bite_view(A)
            else:
                EX.hump_bite_view(A, EX.split_row(method))
            F = A.get("_" + method)
        return np.asarray(F["coord"], dtype=float).reshape(-1, 1)
    x = np.asarray(A["x_" + method], dtype=float)
    if base in ("pca", "pca_gap"):
        return np.column_stack([x, np.asarray(A["y_" + method], dtype=float)])
    return x.reshape(-1, 1)


def posterior(X, types, seed=0):
    """(p_own, p_max) per event from a two-Gaussian fit of X: the
    probability of the Gaussian that goes with the event's own class, and
    of its more probable one. nan for an event with no place on the axis.
    None when it cannot be fitted."""
    from sklearn.mixture import GaussianMixture
    X = np.asarray(X, dtype=float)
    t = np.asarray(types, dtype=int)
    ok = np.isfinite(X).all(axis=1) & np.isin(t, (1, 2))
    if ok.sum() < 8 or len(set(t[ok].tolist())) < 2:
        return None
    Z = X[ok]
    sd = Z.std(axis=0)
    Z = (Z - Z.mean(axis=0)) / np.where(sd > 0, sd, 1.0)
    if not np.ptp(Z, axis=0).any():
        return None
    # Started from the split's own classes, so the two Gaussians are the
    # split's two families where it has two, and the fit is repeatable.
    means = np.vstack([Z[t[ok] == c].mean(axis=0) for c in (1, 2)])
    try:
        g = GaussianMixture(2, covariance_type="full", means_init=means,
                            reg_covar=1e-4, random_state=int(seed)).fit(Z)
        R = g.predict_proba(Z)
    except Exception:                                    # noqa: BLE001
        return None
    is1 = (t[ok] == 1).astype(float)
    k1 = int(np.argmax([(R[:, k] * is1).sum() / max(R[:, k].sum(), 1e-12)
                        for k in (0, 1)]))
    own = np.where(t[ok] == 1, R[:, k1], R[:, 1 - k1])
    p_own, p_max = np.full(t.size, np.nan), np.full(t.size, np.nan)
    p_own[ok], p_max[ok] = own, R.max(axis=1)
    return p_own, p_max


def _mix(p_own, keep, seed=0):
    """The expected mix-up over the events `keep`, with its interval."""
    v = 1.0 - p_own[keep & np.isfinite(p_own)]
    if v.size < 4:
        return None
    rng = np.random.default_rng(seed)
    bs = v[rng.integers(0, v.size, size=(N_BOOT, v.size))].mean(axis=1)
    est = float(v.mean())
    lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
    word = "clean" if est <= MIX_CLEAN else "within" if est <= MIX_OK else "mixed"
    return {"est": _r(est, 3), "lo": _r(lo, 3), "hi": _r(hi, 3), "word": word,
            "n": int(v.size),
            "straddles": bool(any(lo < b < hi for b in (MIX_CLEAN, MIX_OK)))}


def layers(A, method, types, ds3_cut=DS3_CUT, trim_cut=TRIM_CUT):
    """Everything the page needs for one split of one recording:

      ds3    the DS3 layer's summary (ds3_layer), with `types`
      trim   {cut, unsure (n), refused (why or None), p_max per event, types}
      mix    {plain, ds3, trim}: the mix-up as split, with DS3 out, with the
             unsure trimmed -- one fit, the remaining events
    """
    t = np.asarray(types, dtype=int)
    rs = relsink(A, t)
    t3, d3 = ds3_layer(rs, t, ds3_cut)
    d3["types"] = [int(x) for x in t3]
    post = None
    try:
        post = posterior(axis_of(A, method), t)
    except Exception:                                    # noqa: BLE001
        post = None
    trim = {"cut": float(trim_cut), "unsure": 0, "refused": None, "p_max": None,
            "types": [int(x) for x in t]}
    mix = {"plain": None, "ds3": None, "trim": None}
    if post is None:
        trim["refused"] = ("No two-Gaussian fit could be made on this split's "
                           "axis, so nothing is trimmed.")
        return {"ds3": d3, "trim": trim, "mix": mix}
    p_own, p_max = post
    unsure = np.isfinite(p_max) & (p_max < float(trim_cut))
    left = {c: int(((t == c) & ~unsure).sum()) for c in (1, 2)}
    trim["p_max"] = [_r(v, 3) for v in p_max]
    trim["would"] = int(unsure.sum())
    if min(left.values()) < MIN_CLASS:
        small = min(left, key=left.get)
        trim["refused"] = ("Trimming would leave DS%d with %d event%s (under "
                           "%d), so this recording is not trimmed."
                           % (small, left[small], "" if left[small] == 1 else "s",
                              MIN_CLASS))
        kept = np.ones(t.size, dtype=bool)
    else:
        kept = ~unsure
        trim["unsure"] = int(unsure.sum())
        trim["types"] = [int(x) for x in np.where(unsure, C_UNSURE, t)]
    every = np.ones(t.size, dtype=bool)
    mix["plain"] = _mix(p_own, every)
    mix["ds3"] = None if d3.get("why") else _mix(p_own, t3 != C_DS3)
    mix["trim"] = _mix(p_own, kept) if not trim["refused"] else None
    return {"ds3": d3, "trim": trim, "mix": mix}


def types_for(L, mode):
    """The classes a mode gives: the split's, with DS3 laid over, or with the
    unsure taken out."""
    if mode == "ds3" and not L["ds3"].get("why"):
        return np.asarray(L["ds3"]["types"], dtype=int)
    if mode == "trim":
        return np.asarray(L["trim"]["types"], dtype=int)
    return None
