# -*- coding: utf-8 -*-
"""Rank detector + channel-rule settings on a SUBSET of recordings.

The ten recordings hold two kinds of hand-sorted Solids:
  sorted   m5 s2, m5 s7, m13 s2, m13 s17, m28 s2, m34 s5, m34 s8 -- found by
           the original detector, filtered to 5-10 even channels, sorted
  confirmed  m3 s2, m3 s7, m28 s7 -- a later, separate, solid-only pass
The original pipeline catches 90/92 of the first and 9/77 of the second, so
"catch every Solid" means different things depending on which is required.

    python rank_subsets.py
"""
import csv, glob, os
from collections import defaultdict
import ied_common as C

SORTED = ["m5_s2", "m5_s7", "m13_s2", "m13_s17", "m28_s2", "m34_s5", "m34_s8"]
CONFIRMED = ["m3_s2", "m3_s7", "m28_s7"]
KEYS = ("prefilter", "llw", "chanset", "mode", "prc", "merge", "min_s", "kmin", "kmax")


def rank(recs, label, top=8):
    agg = defaultdict(lambda: defaultdict(int))
    seen = defaultdict(set)
    for f in glob.glob(os.path.join(C.OUT, "rule", "*.csv")):
        for r in csv.DictReader(open(f)):
            if r["key"] not in recs:
                continue
            k = tuple(r[x] for x in KEYS)
            seen[k].add(r["key"])
            for c in ("n_det", "solid_hit", "solid_n", "garbage_hit", "unrev_hit"):
                agg[k][c] += int(r[c])
    full = [dict(zip(KEYS, k), **v) for k, v in agg.items()
            if len(seen[k]) == len(recs) and v["solid_hit"] >= v["solid_n"]]
    full.sort(key=lambda d: d["n_det"])
    print("\n=== %s: %d recordings, every Solid kept by %d settings" % (label, len(recs), len(full)))
    for d in full[:top]:
        print("  %-9s %4s %-9s %-7s %5s  min %-6s  ch>=%-2s %-3s | dets %5d  solids %d/%d  garbage %d  unrev %d"
              % (d["prefilter"], d["llw"], d["chanset"], d["mode"], d["prc"], d["min_s"],
                 d["kmin"], ("<=" + d["kmax"]) if d["kmax"] else "", d["n_det"],
                 d["solid_hit"], d["solid_n"], d["garbage_hit"], d["unrev_hit"]))
    for pf in ("orig30k", "raw", "lfp", "sharp", "car_lfp", "car_sharp"):
        m = [d for d in full if d["prefilter"] == pf]
        if m:
            d = m[0]
            print("  best %-9s: %5d dets (%s %s %s %s ch>=%s%s)" % (pf, d["n_det"], d["llw"], d["chanset"], d["mode"], d["prc"], d["kmin"], ("<=" + d["kmax"]) if d["kmax"] else ""))
        else:
            print("  best %-9s: never keeps every Solid" % pf)


rank(SORTED, "the 5-10-sorted recordings (92 Solids)")
rank(CONFIRMED, "the 'confirmed' recordings (77 Solids)")
rank(SORTED + CONFIRMED, "all ten (169 reachable Solids)", top=4)
