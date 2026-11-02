# -*- coding: utf-8 -*-
"""One detector setting, run on one recording, with everything kept.

The sweep (step 3) only counts. This returns the events themselves -- window,
which channels took part, and the moment of the largest deflection -- so the
shmutz analysis (step 4) can look at each one.

A setting is a dict with the sweep's columns:
    prefilter  'orig30k' or a name from ied_common.PREFILTERS
    llw        seconds
    chanset    'even' | 'even_good' | 'all_good'
    mode       'global' | 'perchan'
    prc, merge, min_s
"""
import json
import os

import numpy as np

import ied_common as C
from step3_sweep import SUB, _after_car, chan_rows, thresholds_from_hist


def load_rec(rec):
    d = os.path.join(C.DATA, rec["key"])
    meta = json.load(open(os.path.join(d, "meta.json")))
    X = np.load(os.path.join(d, "sig2k.npy"), mmap_mode="r")
    return d, meta, X


def filtered(name, X, good_rows):
    """All channels through one pre-filter, float32 (rows x samples)."""
    fn = dict((n, f) for n, _d, f in C.PREFILTERS)[name]
    out = np.zeros(X.shape, np.float32)
    ref = None
    if name.startswith("car"):
        ref = np.mean(np.asarray(X[good_rows], dtype=np.float64), axis=0)
    for i in range(X.shape[0]):
        x = np.asarray(X[i], dtype=np.float64)
        y = _after_car(name, x - ref) if ref is not None else fn(x[None], [0])[0]
        out[i] = y.astype(np.float32)
    return out


def run_setting(rec, s, X=None, meta=None, d=None):
    """[{on, off, rows[], peak_t, n}] for one setting on one recording."""
    if X is None:
        d, meta, X = load_rec(rec)
    nums = meta["channels"]
    rows = chan_rows(nums, rec["bad"], s["chanset"])
    llw = float(s["llw"])
    prcs = [float(s["prc"])]
    if s["prefilter"] == "orig30k":
        P = np.load(os.path.join(d, "ll30k_pool.npy"), mmap_mode="r")
        hist = np.load(os.path.join(d, "ll30k_hist.npy"))
        lo, hi, nb = meta["hist"]
        if s["mode"] == "global":
            thr = thresholds_from_hist(hist, rows, prcs, lo, hi, nb)[0]
        else:
            thr = np.array([thresholds_from_hist(hist, [r], prcs, lo, hi, nb)[0]
                            for r in rows])
        Pr = np.asarray(P[rows])
    else:
        Y = filtered(s["prefilter"], X, chan_rows(nums, rec["bad"], "all_good"))
        w = int(round(llw * C.FS))
        Pr, S = [], []
        for r in rows:
            L = C.linelength(Y[r][None], w)
            Pr.append(C.pool_max(L, C.POOL)[0])
            S.append(np.nan_to_num(L[0, ::SUB], nan=0.0))
        Pr, S = np.asarray(Pr), np.asarray(S)
        if s["mode"] == "global":
            thr = np.percentile(S.ravel(), prcs)[0]
        else:
            thr = np.percentile(S, prcs, axis=1)[0]
        del Y, S
    Li = Pr > (thr if np.ndim(thr) == 0 else np.asarray(thr)[:, None])
    ev = C.events_from_mask(Li, C.FS_POOL, llw, float(s["merge"]),
                            float(s["min_s"]))
    out = []
    # which rows took part, recomputed per event from the mask
    for on, off, n in ev:
        b0 = max(0, int((on - llw / 2) * C.FS_POOL))
        b1 = min(Li.shape[1], int(np.ceil((off - llw / 2) * C.FS_POOL)) + 1)
        part = [rows[i] for i in np.flatnonzero(Li[:, b0:b1].any(axis=1))]
        out.append({"on": float(on), "off": float(off),
                    "rows": part, "n": int(n)})
    return out
