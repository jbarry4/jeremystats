# -*- coding: utf-8 -*-
"""Step 10 -- the choice, made the way steps 8 and 9 showed is honest.

Rules, in order:

1. The lab's own event definition stays: discharges closer than 300 ms are
   ONE event (the MATLAB's merge). A longer merge looks cheaper only because
   it folds a doublet into one candidate -- step 9 counted it: at 500 ms two
   hand-sorted pairs (0.46 s and 0.3-0.5 s apart) become one candidate with
   one stamp, so the second IED of each is never offered for review and an
   IED rate would undercount. And no setting at all gives every Solid a
   candidate of its own, because the hand-sorts hold a duplicate stamp 2 ms
   from another and doublets closer than 300 ms, which the lab's rule itself
   calls one event.
2. Every Solid caught (169 of 169) on all ten recordings.
3. Room on both sides: the next percentile up and one more channel required
   must ALSO catch every Solid. Step 8 showed why: the cheapest setting picked
   on nine recordings missed Solids on the tenth four times out of ten; the
   one with room on both sides never did.
4. Then the fewest candidates.

Reads step 7's grid (out/refine) and step 9's (out/edges) together.

    python step10_choose.py
"""
import csv
import glob
import json
import os
from collections import defaultdict

import ied_common as C

KEYS = ("band", "llw", "prc", "merge", "kmin")
PRCS = ["99.8", "99.85", "99.88", "99.9", "99.92", "99.95", "99.97"]
MERGE = "0.3"


def load():
    per = defaultdict(dict)
    for d in ("refine", "edges"):
        for f in glob.glob(os.path.join(C.OUT, d, "*.csv")):
            for r in csv.DictReader(open(f)):
                s = tuple(r[k] for k in KEYS)
                per[s].setdefault(r["key"], r)
    return per


def stricter(s):
    band, llw, prc, merge, kmin = s
    out = [(band, llw, prc, merge, str(int(kmin) + 1))]
    i = PRCS.index(prc)
    if i + 1 < len(PRCS):
        out.append((band, llw, PRCS[i + 1], merge, kmin))
    return out


def full(per, s, keys):
    rows = per.get(s)
    if not rows or any(k not in rows for k in keys):
        return False
    return all(int(rows[k]["solid_hit"]) >= int(rows[k]["solid_n"]) for k in keys)


def robust(per, s, keys):
    return full(per, s, keys) and all(full(per, n, keys) for n in stricter(s))


def total(per, s, keys, col):
    return sum(int(per[s][k][col]) for k in keys)


def main():
    per = load()
    recs = sorted({k for v in per.values() for k in v})
    cand = [s for s in per if s[3] == MERGE]
    ok = sorted([s for s in cand if full(per, s, recs)],
                key=lambda s: total(per, s, recs, "n_det"))
    rb = [s for s in ok if robust(per, s, recs)]
    C.log("%d settings at a %s s merge, %d recordings; every Solid: %d; with "
          "room on both sides: %d" % (len(cand), MERGE, len(recs), len(ok), len(rb)))

    def show(s):
        return ("%-11s llw %-6s prc %-6s >=%-2s %5d candidates  garbage %3d  "
                "unreviewed %4d" % (s[0], s[1], s[2], s[4],
                                    total(per, s, recs, "n_det"),
                                    total(per, s, recs, "garbage_hit"),
                                    total(per, s, recs, "unrev_hit")))
    C.log("\ncheapest catching every Solid:")
    for s in ok[:6]:
        C.log("  " + show(s) + ("   room both sides" if s in rb else ""))
    C.log("\ncheapest with room on both sides:")
    for s in rb[:8]:
        C.log("  " + show(s))
    lost, dets, picks = 0, 0, []
    for held in recs:
        train = [k for k in recs if k != held]
        pool = [s for s in cand if robust(per, s, train)]
        best = min(pool, key=lambda s: total(per, s, train, "n_det"))
        r = per[best][held]
        miss = int(r["solid_n"]) - int(r["solid_hit"])
        lost += miss
        dets += int(r["n_det"])
        picks.append([held, list(best), miss, int(r["n_det"])])
    C.log("\nleave one recording out: %d of 169 Solids missed on recordings the "
          "choice never saw, %d candidates" % (lost, dets))
    for p in picks:
        C.log("  held out %-8s chose %s -> missed %d" % (p[0], tuple(p[1]), p[2]))
    win = rb[0]
    C.log("\nCHOSEN: " + show(win))
    for n in stricter(win):
        C.log("  stricter neighbour " + show(n))
    json.dump({"chosen": dict(zip(KEYS, win)),
               "n_det": total(per, win, recs, "n_det"),
               "garbage_hit": total(per, win, recs, "garbage_hit"),
               "unrev_hit": total(per, win, recs, "unrev_hit"),
               "top_robust": [dict(zip(KEYS, s), n_det=total(per, s, recs, "n_det"))
                              for s in rb[:20]],
               "holdout": {"lost": lost, "dets": dets, "picks": picks}},
              open(os.path.join(C.OUT, "chosen.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
