# -*- coding: utf-8 -*-
"""Step 3 -- sweep the detector's parameters and pre-filters.

Every setting is one specification applied to all ten recordings, with the
threshold taken PER RECORDING the way LLspikedetector takes it (a percentile
of that recording's own line-length distribution). For each setting and
recording this records how many hand-sorted Solids fall inside a detection,
how many detections there were, and which of the other labelled candidates
(sputter, flag, garbage, unreviewed) were caught as well.

The baseline is the original detector exactly as the lab ran it -- raw
30 kHz, 40 ms window, even channels, one pooled percentile -- computed from
the 30 kHz line length step 2 kept, not from the 2 kHz copy.

Writes out/sweep/<key>.csv, one row per setting.

    python step3_sweep.py              all recordings, 3 at a time
    python step3_sweep.py m5_s7
"""
import csv
import itertools
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import ied_common as C

LLWS = (0.020, 0.040, 0.080)
PRCS = (97.0, 98.0, 99.0, 99.5, 99.7, 99.8, 99.9, 99.95, 99.98, 99.99)
MERGES = (0.1, 0.3)
MINS = (0.0125, 0.025)
CHANSETS = ("even", "even_good", "all_good")
MODES = ("global", "perchan")
SUB = 10            # thresholds from every 10th line-length value

SWEEP_DIR = os.path.join(C.OUT, "sweep")
os.makedirs(SWEEP_DIR, exist_ok=True)

FIELDS = ["key", "prefilter", "llw", "chanset", "mode", "prc", "merge",
          "min_s", "n_det", "solid_hit", "solid_n", "sputter_hit",
          "sputter_n", "flag_hit", "flag_n", "garbage_hit", "garbage_n",
          "unrev_hit", "unrev_n", "det_with_solid", "det_seconds"]


def chan_rows(nums, bad, which):
    badset = set(bad)
    if which == "even":
        return [i for i, n in enumerate(nums) if n % 2 == 0]
    if which == "even_good":
        return [i for i, n in enumerate(nums) if n % 2 == 0 and n not in badset]
    return [i for i, n in enumerate(nums) if n not in badset]


def vmatch(ev, times, tol=C.MATCH_S):
    """Vectorised `C.match`: index of the detection covering each time."""
    out = np.full(len(times), -1, dtype=np.int64)
    if not len(ev) or not len(times):
        return out
    lo = ev[:, 0] - tol
    hi = ev[:, 1] + tol
    t = np.asarray(times)
    j = np.searchsorted(lo, t, side="right") - 1
    for jj in (j, j - 1):
        ok = (out < 0) & (jj >= 0)
        jc = np.clip(jj, 0, len(ev) - 1)
        ok &= (lo[jc] <= t) & (t <= hi[jc])
        out[ok] = jc[ok]
    return out


def events(mask_any, fs_pool, llw, merge_s, min_s):
    """LLspikedetector's event logic on an any-channel mask (no participation)."""
    a = mask_any
    if not a.any():
        return np.zeros((0, 2))
    da = np.diff(a.astype(np.int8))
    on = np.flatnonzero(da == 1) + 1
    off = np.flatnonzero(da == -1)
    if a[0]:
        on = np.concatenate([[0], on])
    if a[-1]:
        off = np.concatenate([off, [a.size - 1]])
    ets = np.stack([on / fs_pool + llw / 2, (off + 1) / fs_pool + llw / 2], 1)
    if len(ets) > 1:
        # Sequential merge, vectorised: a gap shorter than merge_s joins the
        # event to the one before it, and a chain of short gaps joins them
        # all onto the first -- exactly what the mutating loop does.
        gap = ets[1:, 0] - ets[:-1, 1]
        start_new = np.concatenate([[True], gap >= merge_s])
        grp = np.cumsum(start_new) - 1
        first = np.flatnonzero(start_new)
        last = np.concatenate([first[1:] - 1, [len(ets) - 1]])
        ets = np.stack([ets[first, 0], ets[last, 1]], 1)
    keep = (ets[:, 1] - ets[:, 0]) >= min_s
    return ets[keep]


def score(key, gt_ev, ev):
    row = {"n_det": len(ev),
           "det_seconds": round(float(np.sum(ev[:, 1] - ev[:, 0])), 2)
           if len(ev) else 0.0}
    covered = np.zeros(len(ev), bool)
    for lab in ("solid", "sputter", "flag", "garbage", None):
        ts = gt_ev.get(lab, np.zeros(0))
        m = vmatch(ev, ts)
        name = "unrev" if lab is None else lab
        row[name + "_hit"] = int((m >= 0).sum())
        row[name + "_n"] = int(len(ts))
        if lab == "solid" and len(ev):
            covered[m[m >= 0]] = True
    row["det_with_solid"] = int(covered.sum())
    return row


def thresholds_from_hist(hist, rows, prcs, lo, hi, nb):
    """Percentiles of the pooled distribution of `rows`, from histograms."""
    edges = np.linspace(lo, hi, nb + 1)
    h = hist[rows].sum(axis=0).astype(np.float64)
    c = np.cumsum(h)
    tot = c[-1]
    out = []
    for p in prcs:
        k = p / 100.0 * tot
        i = int(np.searchsorted(c, k))
        i = min(i, nb - 1)
        prev = c[i - 1] if i else 0.0
        frac = (k - prev) / max(h[i], 1.0)
        out.append(10 ** (edges[i] + frac * (edges[i + 1] - edges[i])))
    return np.asarray(out)


def sweep_pooled(key, P, thr_fn, nums, bad, gt_ev, prefilter, llw, writer):
    """All chanset x mode x prc x merge x min settings on one pooled LL."""
    n = 0
    for chanset in CHANSETS:
        rows = chan_rows(nums, bad, chanset)
        for mode in MODES:
            thr = thr_fn(rows, mode)          # (len(PRCS),) or (len(PRCS), rows)
            for pi, prc in enumerate(PRCS):
                if mode == "global":
                    mask = (P[rows] > thr[pi]).any(axis=0)
                else:
                    mask = (P[rows] > thr[pi][:, None]).any(axis=0)
                for merge, mn in itertools.product(MERGES, MINS):
                    ev = events(mask, C.FS_POOL, llw, merge, mn)
                    r = score(key, gt_ev, ev)
                    r.update(key=key, prefilter=prefilter, llw=llw,
                             chanset=chanset, mode=mode, prc=prc,
                             merge=merge, min_s=mn)
                    writer.writerow(r)
                    n += 1
    return n


def run(rec):
    key = rec["key"]
    out_p = os.path.join(SWEEP_DIR, key + ".csv")
    if os.path.exists(out_p):
        return key, "done already"
    d = os.path.join(C.DATA, key)
    meta = json.load(open(os.path.join(d, "meta.json")))
    nums = meta["channels"]
    bad = rec["bad"]
    gt_ev = {}
    for lab in ("solid", "sputter", "flag", "garbage", None):
        gt_ev[lab] = np.asarray(sorted(e["t"] for e in rec["events"]
                                       if e["label"] == lab))
    t0 = time.time()
    tmp = out_p + ".part"
    fh = open(tmp, "w", newline="")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    count = 0

    # ---- baseline: the original, at 30 kHz ---------------------------------
    P = np.load(os.path.join(d, "ll30k_pool.npy"))
    hist = np.load(os.path.join(d, "ll30k_hist.npy"))
    lo, hi, nb = meta["hist"]

    def thr30(rows, mode):
        if mode == "global":
            return thresholds_from_hist(hist, rows, PRCS, lo, hi, nb)
        return np.stack([np.array([thresholds_from_hist(hist, [r], [p],
                                                        lo, hi, nb)[0]
                                   for r in rows]) for p in PRCS])
    count += sweep_pooled(key, P, thr30, nums, bad, gt_ev, "orig30k",
                          meta["llw_orig"], w)
    del P, hist

    # ---- the 2 kHz sweep -----------------------------------------------------
    X = np.load(os.path.join(d, "sig2k.npy"), mmap_mode="r")
    good_rows = chan_rows(nums, bad, "all_good")
    # NOTCHED ONCE. Six of the seven pre-filters start with the same notch,
    # and the notch was most of the time this step took -- six identical
    # passes per channel. Both the notch and the common average reference
    # are linear, so notching first and referencing after is the same
    # signal as the other order; the reference is the mean of the GOOD
    # channels, because a bad channel in it would put its noise into every
    # other one.
    N = np.zeros(X.shape, np.float32)
    for i in range(X.shape[0]):
        N[i] = C.notch(np.asarray(X[i], dtype=np.float64)).astype(np.float32)
    refN = np.mean(N[good_rows].astype(np.float64), axis=0)

    def prefiltered(name, i):
        if name == "raw":
            return np.asarray(X[i], dtype=np.float64)
        n = N[i].astype(np.float64)
        if name == "notch":
            return n
        if name == "lfp":
            return C.band(n, None, 300)
        if name == "ied":
            return C.band(n, 1, 70)
        if name == "sharp":
            return C.band(n, 10, 300)
        if name == "car_lfp":
            return C.band(n - refN, None, 300)
        if name == "car_sharp":
            return C.band(n - refN, 10, 300)
        raise ValueError(name)

    for name, _desc, fn in C.PREFILTERS:
        pooled = {llw: None for llw in LLWS}
        subs = {llw: None for llw in LLWS}
        for i in range(X.shape[0]):
            y = prefiltered(name, i)
            for llw in LLWS:
                L = C.linelength(y[None, :], int(round(llw * C.FS)))
                Pp = C.pool_max(L, C.POOL)[0]
                if pooled[llw] is None:
                    pooled[llw] = np.zeros((X.shape[0], Pp.size), np.float32)
                    subs[llw] = np.zeros((X.shape[0],
                                          (L.shape[1] + SUB - 1) // SUB),
                                         np.float32)
                pooled[llw][i] = Pp
                s = L[0, ::SUB]
                subs[llw][i, :s.size] = np.nan_to_num(s, nan=0.0)
        for llw in LLWS:
            S = subs[llw]

            def thr2(rows, mode, S=S):
                if mode == "global":
                    v = S[rows].ravel()
                    return np.percentile(v, PRCS)
                return np.percentile(S[rows], PRCS, axis=1)
            count += sweep_pooled(key, pooled[llw], thr2, nums, bad, gt_ev,
                                  name, llw, w)
        del pooled, subs
        fh.flush()
    fh.close()
    os.replace(tmp, out_p)
    return key, "%d settings in %.0f s" % (count, time.time() - t0)


def _after_car(name, x):
    """The CAR prefilters' filtering, once the reference is already off."""
    if name == "car_lfp":
        return C.band(C.notch(x), None, 300)
    if name == "car_sharp":
        return C.band(C.notch(x), 10, 300)
    raise ValueError(name)


def main():
    gt = C.load_gt()
    want = set(sys.argv[1:])
    recs = [r for r in gt if (not want or r["key"] in want)
            and os.path.exists(os.path.join(C.DATA, r["key"], "meta.json"))]
    # biggest first, so the long one is not left running alone at the end
    recs.sort(key=lambda r: -(r.get("duration_s") or 0))
    with ProcessPoolExecutor(max_workers=3) as ex:
        for key, msg in ex.map(run, recs):
            C.log(key, msg)


if __name__ == "__main__":
    main()
