# -*- coding: utf-8 -*-
"""Step 9 -- push past the edges of step 7's grid, and count honestly.

Two things step 7 left open:

1. Every setting it liked used the SHORTEST window it tried (15 ms) and the
   LONGEST merge (500 ms). A best point on the edge of a grid is not known to
   be the best point; this tries 10 and 12.5 ms, and 750 ms.

2. Its hit count lets one detection "catch" several Solids. A long merged
   event that covers two hand-sorted IEDs gives the reviewer ONE candidate
   with ONE stamp, so the second is not really caught. Here every Solid must
   get a detection of its own (`solid_own`); the old count is kept beside it
   (`solid_hit`) so the two can be compared.

Then it chooses the way step 8 showed is honest: every Solid kept on its
own, AND both stricter neighbours (next percentile up, one more channel)
still keep every Solid -- a setting with room on both sides -- and checks
that choice by leaving each recording out in turn.

    python step9_edges.py            (then: python step9_edges.py --rank)

WHAT IT FOUND: no setting at all gives every Solid a candidate of its own.
The hand-sorts hold a duplicate stamp 2 ms from another, and doublets closer
than 300 ms -- which the lab's own merge calls one event. So the choice is
made in step10_choose.py, at the lab's 300 ms event definition, using this
grid together with step 7's.
"""
import csv
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import ied_common as C
from step3_sweep import SUB, chan_rows, vmatch
from step5_channel_rule import events_part

BANDS = [("car_20_300", 20, 300), ("car_10_300", 10, 300), ("car_lp300", None, 300)]
LLWS = (0.010, 0.0125, 0.015)
PRCS = (99.85, 99.88, 99.9, 99.92, 99.95, 99.97)
MERGES = (0.3, 0.5, 0.75)
MIN_S = 0.0125
KMIN = tuple(range(4, 11))
CHANSET = "even_good"

OUT = os.path.join(C.OUT, "edges")
os.makedirs(OUT, exist_ok=True)
FIELDS = ["key", "band", "llw", "prc", "merge", "kmin", "n_det", "solid_hit",
          "solid_own", "solid_n", "garbage_hit", "unrev_hit", "multi"]
KEYS = ("band", "llw", "prc", "merge", "kmin")


def own(ev, t, tol=C.MATCH_S):
    """Solids that get a detection of their own: each detection may stand for
    at most one Solid (earliest unused detection that covers it)."""
    if not len(ev) or not len(t):
        return 0, 0
    lo, hi = ev[:, 0] - tol, ev[:, 1] + tol
    used = np.zeros(len(ev), bool)
    per = np.zeros(len(ev), int)
    n = 0
    for x in t:
        j = int(np.searchsorted(lo, x, side="right"))   # lo[:j] <= x
        cand = [k for k in range(max(0, j - 3), j) if hi[k] >= x]
        for k in cand:
            per[k] += 1
        free = [k for k in cand if not used[k]]
        if free:
            used[free[0]] = True
            n += 1
    return n, int((per >= 2).sum())


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
                        o, multi = own(e2, gt["solid"])
                        w.writerow({
                            "key": key, "band": name, "llw": llw, "prc": prc,
                            "merge": merge, "kmin": kmin, "n_det": len(e2),
                            "solid_n": len(gt["solid"]),
                            "solid_hit": int((vmatch(e2, gt["solid"]) >= 0).sum()),
                            "solid_own": o, "multi": multi,
                            "garbage_hit": int((vmatch(e2, gt["garbage"]) >= 0).sum()),
                            "unrev_hit": int((vmatch(e2, gt[None]) >= 0).sum())})
            del P, S
        del Ys
        fh.flush()
    fh.close()
    os.replace(out_p + ".part", out_p)
    return key, "done"


# ------------------------------------------------------------------ choosing
def load():
    per = defaultdict(dict)
    for f in os.listdir(OUT):
        if f.endswith(".csv"):
            for r in csv.DictReader(open(os.path.join(OUT, f))):
                per[tuple(r[k] for k in KEYS)][r["key"]] = r
    return per


def stricter(s):
    band, llw, prc, merge, kmin = s
    ps = ["%g" % p for p in PRCS]
    out = [(band, llw, prc, merge, str(int(kmin) + 1))]
    i = ps.index("%g" % float(prc))
    if i + 1 < len(ps):
        out.append((band, llw, str(PRCS[i + 1]), merge, kmin))
    return out


def full(per, s, keys, col="solid_own"):
    rows = per.get(s)
    if not rows or any(k not in rows for k in keys):
        return False
    return all(int(rows[k][col]) >= int(rows[k]["solid_n"]) for k in keys)


def robust(per, s, keys):
    return full(per, s, keys) and all(full(per, n, keys) for n in stricter(s))


def total(per, s, keys, col):
    return sum(int(per[s][k][col]) for k in keys)


def rank():
    per = load()
    recs = sorted({k for v in per.values() for k in v})
    C.log("%d settings x %d recordings" % (len(per), len(recs)))
    ok = sorted([s for s in per if full(per, s, recs)],
                key=lambda s: total(per, s, recs, "n_det"))
    rb = [s for s in ok if robust(per, s, recs)]
    C.log("every Solid on its own detection: %d settings; with room on both "
          "sides: %d" % (len(ok), len(rb)))

    def show(s):
        return ("%-11s llw %-6s prc %-6s merge %-4s >=%-2s  %5d dets  garbage %3d"
                "  unreviewed %4d  multi %d" % (s + (
                    total(per, s, recs, "n_det"), total(per, s, recs, "garbage_hit"),
                    total(per, s, recs, "unrev_hit"), total(per, s, recs, "multi"))))
    C.log("\ncheapest that keep every Solid on its own:")
    for s in ok[:8]:
        C.log("  " + show(s) + ("   (room both sides)" if s in rb else ""))
    C.log("\ncheapest WITH room on both sides:")
    for s in rb[:8]:
        C.log("  " + show(s))
    # leave one recording out
    lost, dets, picks = 0, 0, []
    for held in recs:
        train = [k for k in recs if k != held]
        cand = [s for s in per if robust(per, s, train)]
        if not cand:
            C.log("  no setting gives every Solid its own candidate -- see "
                  "step10_choose.py, which is where the choice is made")
            break
        best = min(cand, key=lambda s: total(per, s, train, "n_det"))
        r = per[best][held]
        miss = int(r["solid_n"]) - int(r["solid_own"])
        lost += miss
        dets += int(r["n_det"])
        picks.append((held, best, miss, int(r["n_det"])))
        C.log("  held out %-8s chose %s -> missed %d, %d dets" % (held, best, miss,
                                                                  int(r["n_det"])))
    C.log("leave-one-out: %d of 169 Solids missed on recordings never chosen on; "
          "%d detections" % (lost, dets))
    with open(os.path.join(C.OUT, "edges_ranked.json"), "w") as fh:
        json.dump({"ok": [dict(zip(KEYS, s), n_det=total(per, s, recs, "n_det"),
                               robust=s in rb) for s in ok[:200]],
                   "holdout": {"lost": lost, "dets": dets, "picks": picks}},
                  fh, indent=1)


def main():
    if "--rank" in sys.argv:
        rank()
        return
    gt = sorted(C.load_gt(), key=lambda r: -(r.get("duration_s") or 0))
    workers = int(os.environ.get("WORKERS", "4"))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for key, msg in ex.map(run, gt):
            C.log(key, msg)
    rank()


if __name__ == "__main__":
    main()
