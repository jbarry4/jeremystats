# -*- coding: utf-8 -*-
"""Step 7 -- a finer search around the winning specification.

Step 5 found common-average reference -> notch -> 10-300 Hz -> 20 ms line
length -> even good channels -> pooled 99.9th -> merge 300 ms -> >= 6
channels: 169/169 Solids, 2,491 detections. This searches the neighbourhood
of every one of those numbers, to make sure the default Doppler ships with
is the best point and not merely the best point on a coarse grid.

    python step7_refine.py           (then: python step7_refine.py --rank)
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
from step3_sweep import SUB, chan_rows, vmatch
from step5_channel_rule import events_part

# (name, lo, hi): every one after CAR + notch
BANDS = [("car_10_300", 10, 300), ("car_5_300", 5, 300), ("car_20_300", 20, 300),
         ("car_10_200", 10, 200), ("car_lp300", None, 300)]
LLWS = (0.015, 0.020, 0.030)
PRCS = (99.8, 99.85, 99.88, 99.9, 99.92, 99.95, 99.97)
MERGES = (0.2, 0.3, 0.5)
MIN_S = 0.0125
KMIN = tuple(range(3, 11))
CHANSET = "even_good"

OUT = os.path.join(C.OUT, "refine")
os.makedirs(OUT, exist_ok=True)
FIELDS = ["key", "band", "llw", "prc", "merge", "kmin", "n_det", "solid_hit",
          "solid_n", "garbage_hit", "unrev_hit"]


def run(rec):
    key = rec["key"]
    out_p = os.path.join(OUT, key + ".csv")
    if os.path.exists(out_p):
        return key, "done already"
    d = os.path.join(C.DATA, key)
    meta = json.load(open(os.path.join(d, "meta.json")))
    nums, bad, seconds = meta["channels"], rec["bad"], meta["seconds"]
    gt = {lab: np.asarray(sorted(e["t"] for e in rec["events"]
                                 if e["label"] == lab and e["t"] <= seconds))
          for lab in ("solid", "garbage", None)}
    X = np.load(os.path.join(d, "sig2k.npy"), mmap_mode="r")
    good = chan_rows(nums, bad, "all_good")
    rows = chan_rows(nums, bad, CHANSET)
    N = np.zeros(X.shape, np.float32)
    for i in range(X.shape[0]):
        N[i] = C.notch(np.asarray(X[i], np.float64))
    refN = N[good].astype(np.float64).mean(axis=0)
    fh = open(out_p + ".part", "w", newline="")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    for name, lo, hi in BANDS:
        Ys = [C.band(N[r].astype(np.float64) - refN, lo, hi) for r in rows]
        for llw in LLWS:
            wl = int(round(llw * C.FS))
            P, S = [], []
            for y in Ys:
                L = C.linelength(y[None], wl)
                P.append(C.pool_max(L, C.POOL)[0])
                S.append(np.nan_to_num(L[0, ::SUB], nan=0.0))
            P, S = np.asarray(P), np.asarray(S)
            thr = np.percentile(S.ravel(), PRCS)
            for pi, prc in enumerate(PRCS):
                Li = P > thr[pi]
                for merge in MERGES:
                    ev, cnt = events_part(Li, llw, merge, MIN_S)
                    for kmin in KMIN:
                        e2 = ev[cnt >= kmin]
                        r = {"key": key, "band": name, "llw": llw, "prc": prc,
                             "merge": merge, "kmin": kmin, "n_det": len(e2),
                             "solid_n": len(gt["solid"])}
                        r["solid_hit"] = int((vmatch(e2, gt["solid"]) >= 0).sum())
                        r["garbage_hit"] = int((vmatch(e2, gt["garbage"]) >= 0).sum())
                        r["unrev_hit"] = int((vmatch(e2, gt[None]) >= 0).sum())
                        w.writerow(r)
            del P, S
        del Ys
        fh.flush()
    fh.close()
    os.replace(out_p + ".part", out_p)
    return key, "done"


def rank():
    agg = defaultdict(lambda: defaultdict(int))
    seen = defaultdict(set)
    for f in os.listdir(OUT):
        if not f.endswith(".csv"):
            continue
        for r in csv.DictReader(open(os.path.join(OUT, f))):
            k = (r["band"], r["llw"], r["prc"], r["merge"], r["kmin"])
            seen[k].add(r["key"])
            for c in ("n_det", "solid_hit", "solid_n", "garbage_hit", "unrev_hit"):
                agg[k][c] += int(r[c])
    n = max(len(v) for v in seen.values())
    full = [dict(zip(("band", "llw", "prc", "merge", "kmin"), k), **v)
            for k, v in agg.items()
            if len(seen[k]) == n and v["solid_hit"] >= v["solid_n"]]
    full.sort(key=lambda d: d["n_det"])
    with open(os.path.join(C.OUT, "refine_ranked.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(full[0].keys()))
        w.writeheader()
        w.writerows(full)
    print("every Solid kept by %d settings; best 15:" % len(full))
    for d in full[:15]:
        print(d)
    # how sensitive is the winner? its neighbours
    b = full[0]
    print("\nneighbours of the winner (one knob changed):")
    for d in full:
        diff = [k for k in ("band", "llw", "prc", "merge", "kmin") if d[k] != b[k]]
        if len(diff) == 1:
            print("  %-6s %-10s -> %5d dets" % (diff[0], d[diff[0]], d["n_det"]))


def main():
    if "--rank" in sys.argv:
        rank()
        return
    gt = sorted(C.load_gt(), key=lambda r: -(r.get("duration_s") or 0))
    with ProcessPoolExecutor(max_workers=5) as ex:
        for key, msg in ex.map(run, gt):
            C.log(key, msg)
    rank()


if __name__ == "__main__":
    main()
