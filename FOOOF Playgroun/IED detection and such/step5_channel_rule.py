# -*- coding: utf-8 -*-
"""Step 5 -- the detector together with a channel-count rule.

The lab's real pipeline was never the detector alone. After LLspikedetector,
only events that showed up on 5-10 EVEN channels were rendered and sorted;
everything else was set aside unseen (95% of the 2,760 "unreviewed"
candidates sit outside 5-10). So the fair comparison is detector + rule.

This re-runs the strongest pre-filters from the sweep and, for every event,
counts the channels that took part, then applies a channel-count rule:
  k_min   at least this many channels        1 .. 10
  k_max   at most this many                  none, 10, 12, 16
and finds, per pre-filter, the cheapest setting that still catches every
reachable Solid.

Channel counts are over the setting's own channel set. For `even` and
`even_good` that is the lab's even-channel count; `all_good` is reported but
its counts are over twice as many channels and the 5-10 rule does not
translate.

Writes out/rule/<key>.csv and out/rule_ranked.csv.

    python step5_channel_rule.py
"""
import csv
import itertools
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import ied_common as C
from step3_sweep import (SUB, chan_rows, thresholds_from_hist, vmatch)

COMBOS = [("car_sharp", 0.02), ("car_lfp", 0.02), ("car_sharp", 0.04),
          ("car_lfp", 0.04), ("lfp", 0.04), ("sharp", 0.04), ("raw", 0.02),
          ("orig30k", 0.04)]
CHANSETS = ("even", "even_good")
MODES = ("global", "perchan")
PRCS = (98.0, 99.0, 99.5, 99.7, 99.8, 99.9, 99.95, 99.98)
MERGES = (0.3,)
MINS = (0.0125, 0.025)
KMIN = tuple(range(1, 11))
KMAX = (None, 10, 12, 16)

RULE_DIR = os.path.join(C.OUT, "rule")
os.makedirs(RULE_DIR, exist_ok=True)
FIELDS = ["key", "prefilter", "llw", "chanset", "mode", "prc", "merge",
          "min_s", "kmin", "kmax", "n_det", "solid_hit", "solid_n",
          "garbage_hit", "unrev_hit", "sputter_hit", "flag_hit"]


def events_part(Li, llw, merge, mn):
    """Events and how many rows took part in each (merged, as the .m does)."""
    a = Li.any(axis=0)
    if not a.any():
        return np.zeros((0, 2)), np.zeros(0, int)
    da = np.diff(a.astype(np.int8))
    on = np.flatnonzero(da == 1) + 1
    off = np.flatnonzero(da == -1)
    if a[0]:
        on = np.concatenate([[0], on])
    if a[-1]:
        off = np.concatenate([off, [a.size - 1]])
    cs = np.zeros((Li.shape[0], Li.shape[1] + 1), np.int32)
    np.cumsum(Li, axis=1, out=cs[:, 1:])
    part = (cs[:, off + 1] - cs[:, on]) > 0            # rows x events
    del cs
    ets = np.stack([on / C.FS_POOL + llw / 2, (off + 1) / C.FS_POOL + llw / 2], 1)
    if len(ets) > 1:
        gap = ets[1:, 0] - ets[:-1, 1]
        start = np.concatenate([[True], gap >= merge])
        grp = np.cumsum(start) - 1
        first = np.flatnonzero(start)
        last = np.concatenate([first[1:] - 1, [len(ets) - 1]])
        ets = np.stack([ets[first, 0], ets[last, 1]], 1)
        # participation of a merged event = OR over its members
        part = np.logical_or.reduceat(part, first, axis=1) if part.size else part
    keep = (ets[:, 1] - ets[:, 0]) >= mn
    return ets[keep], part[:, keep].sum(axis=0)


def run(rec):
    key = rec["key"]
    out_p = os.path.join(RULE_DIR, key + ".csv")
    if os.path.exists(out_p):
        return key, "done already"
    d = os.path.join(C.DATA, key)
    meta = json.load(open(os.path.join(d, "meta.json")))
    nums = meta["channels"]
    bad = rec["bad"]
    seconds = meta["seconds"]
    gt = {lab: np.asarray(sorted(e["t"] for e in rec["events"]
                                 if e["label"] == lab and e["t"] <= seconds))
          for lab in ("solid", "garbage", "sputter", "flag", None)}
    X = np.load(os.path.join(d, "sig2k.npy"), mmap_mode="r")
    good = chan_rows(nums, bad, "all_good")
    N = refN = None
    fh = open(out_p + ".part", "w", newline="")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    for pf, llw in COMBOS:
        if pf == "orig30k":
            P = np.asarray(np.load(os.path.join(d, "ll30k_pool.npy"),
                                   mmap_mode="r"))
            hist = np.load(os.path.join(d, "ll30k_hist.npy"))
            lo, hi, nb = meta["hist"]

            def thr_fn(rows, mode):
                if mode == "global":
                    return thresholds_from_hist(hist, rows, PRCS, lo, hi, nb)
                return np.stack([[thresholds_from_hist(hist, [r], [p], lo, hi,
                                                       nb)[0] for r in rows]
                                 for p in PRCS])
        else:
            if N is None:
                N = np.zeros(X.shape, np.float32)
                for i in range(X.shape[0]):
                    N[i] = C.notch(np.asarray(X[i], np.float64))
                refN = N[good].astype(np.float64).mean(axis=0)
            P, S = [], []
            wl = int(round(llw * C.FS))
            for i in range(X.shape[0]):
                n = N[i].astype(np.float64)
                y = {"raw": lambda: np.asarray(X[i], np.float64),
                     "lfp": lambda: C.band(n, None, 300),
                     "sharp": lambda: C.band(n, 10, 300),
                     "car_lfp": lambda: C.band(n - refN, None, 300),
                     "car_sharp": lambda: C.band(n - refN, 10, 300)}[pf]()
                L = C.linelength(y[None], wl)
                P.append(C.pool_max(L, C.POOL)[0])
                S.append(np.nan_to_num(L[0, ::SUB], nan=0.0))
            P, S = np.asarray(P), np.asarray(S)

            def thr_fn(rows, mode, S=S):
                if mode == "global":
                    return np.percentile(S[rows].ravel(), PRCS)
                return np.percentile(S[rows], PRCS, axis=1)
        for chanset in CHANSETS:
            rows = chan_rows(nums, bad, chanset)
            for mode in MODES:
                thr = thr_fn(rows, mode)
                for pi, prc in enumerate(PRCS):
                    t_ = thr[pi] if mode == "global" else thr[pi][:, None]
                    Li = P[rows] > t_
                    for merge, mn in itertools.product(MERGES, MINS):
                        ev, cnt = events_part(Li, llw, merge, mn)
                        for kmin, kmax in itertools.product(KMIN, KMAX):
                            sel = cnt >= kmin
                            if kmax is not None:
                                sel &= cnt <= kmax
                            e2 = ev[sel]
                            r = {"key": key, "prefilter": pf, "llw": llw,
                                 "chanset": chanset, "mode": mode, "prc": prc,
                                 "merge": merge, "min_s": mn, "kmin": kmin,
                                 "kmax": kmax if kmax else "",
                                 "n_det": len(e2),
                                 "solid_n": len(gt["solid"])}
                            for lab, name in (("solid", "solid_hit"),
                                              ("garbage", "garbage_hit"),
                                              ("sputter", "sputter_hit"),
                                              ("flag", "flag_hit"),
                                              (None, "unrev_hit")):
                                r[name] = int((vmatch(e2, gt[lab]) >= 0).sum())
                            w.writerow(r)
                    del Li
        fh.flush()
        del P
    fh.close()
    os.replace(out_p + ".part", out_p)
    return key, "done"


def rank():
    rows = []
    for k in os.listdir(RULE_DIR):
        if k.endswith(".csv"):
            rows.extend(csv.DictReader(open(os.path.join(RULE_DIR, k))))
    keys = ("prefilter", "llw", "chanset", "mode", "prc", "merge", "min_s",
            "kmin", "kmax")
    agg = defaultdict(lambda: defaultdict(int))
    recs = defaultdict(set)
    for r in rows:
        k = tuple(r[x] for x in keys)
        recs[k].add(r["key"])
        for f in ("n_det", "solid_hit", "solid_n", "garbage_hit", "unrev_hit",
                  "sputter_hit", "flag_hit"):
            agg[k][f] += int(r[f])
    nrec = len({r["key"] for r in rows})
    out = []
    for k, v in agg.items():
        if len(recs[k]) != nrec:
            continue
        d = dict(zip(keys, k))
        d.update(v)
        out.append(d)
    full = sorted([d for d in out if d["solid_hit"] >= d["solid_n"]],
                  key=lambda d: d["n_det"])
    with open(os.path.join(C.OUT, "rule_ranked.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(keys) + ["n_det", "solid_hit",
                                                        "solid_n", "garbage_hit",
                                                        "unrev_hit", "sputter_hit",
                                                        "flag_hit"])
        w.writeheader()
        w.writerows(full)
    C.log("settings + rule that keep every reachable Solid: %d" % len(full))
    for d in full[:20]:
        C.log(d)
    C.log("\nbest per pre-filter, with and without a channel rule:")
    for pf, _ in COMBOS:
        mine = [d for d in full if d["prefilter"] == pf]
        norule = [d for d in mine if d["kmin"] == "1" and d["kmax"] == ""]
        if mine:
            C.log("  %-10s with rule:    %s" % (pf, mine[0]))
        if norule:
            C.log("  %-10s without rule: %s" % (pf, norule[0]))
        if not mine:
            C.log("  %-10s never keeps every Solid" % pf)


def main():
    if "--rank" in sys.argv:
        rank()
        return
    gt = C.load_gt()
    recs = sorted(gt, key=lambda r: -(r.get("duration_s") or 0))
    with ProcessPoolExecutor(max_workers=4) as ex:
        for key, msg in ex.map(run, recs):
            C.log(key, msg)
    rank()


if __name__ == "__main__":
    main()
