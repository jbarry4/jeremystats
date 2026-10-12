# -*- coding: utf-8 -*-
"""Step 3b -- add the per-recording sweep up, and rank the settings.

The rule the user set: a setting has to catch EVERY hand-sorted Solid (all
170 across the ten recordings), and among those the winner is the one that
produces the fewest other candidates. "Other candidates" is every detection
that does not contain a Solid -- the pile somebody would have to look
through.

Writes
  out/sweep_totals.csv     every setting, summed over the ten recordings
  out/sweep_frontier.csv   for each pre-filter, the best setting at 100%
                           recall, and the best recall it can reach at all
and prints the head of each.

    python step3b_rank.py
"""
import csv
import glob
import os
from collections import defaultdict

import ied_common as C

KEYS = ("prefilter", "llw", "chanset", "mode", "prc", "merge", "min_s")
SUMS = ("n_det", "solid_hit", "solid_n", "sputter_hit", "sputter_n",
        "flag_hit", "flag_n", "garbage_hit", "garbage_n", "unrev_hit",
        "unrev_n", "det_with_solid", "det_seconds")


def load():
    rows = []
    for p in sorted(glob.glob(os.path.join(C.OUT, "sweep", "*.csv"))):
        with open(p, newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def totals(rows, n_recs):
    agg = defaultdict(lambda: defaultdict(float))
    seen = defaultdict(set)
    for r in rows:
        k = tuple(r[x] for x in KEYS)
        seen[k].add(r["key"])
        for s in SUMS:
            agg[k][s] += float(r[s])
    out = []
    for k, v in agg.items():
        if len(seen[k]) != n_recs:
            continue           # a setting not run on every recording
        d = dict(zip(KEYS, k))
        d.update({s: v[s] for s in SUMS})
        d["recall"] = v["solid_hit"] / max(1.0, v["solid_n"])
        d["other"] = v["n_det"] - v["det_with_solid"]
        d["per_solid"] = v["n_det"] / max(1.0, v["solid_hit"])
        out.append(d)
    return out


def main():
    rows = load()
    recs = sorted({r["key"] for r in rows})
    C.log("recordings in the sweep:", len(recs), recs)
    tot = totals(rows, len(recs))
    tot.sort(key=lambda d: (-d["recall"], d["n_det"]))
    with open(os.path.join(C.OUT, "sweep_totals.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(KEYS) + list(SUMS)
                           + ["recall", "other", "per_solid"])
        w.writeheader()
        w.writerows(tot)

    full = [d for d in tot if d["solid_hit"] >= d["solid_n"]]
    C.log("\nsettings that catch every Solid: %d of %d" % (len(full), len(tot)))
    C.log("%-10s %5s %-9s %-7s %6s %5s %6s | %6s %6s %5s %7s %7s"
          % ("prefilter", "llw", "chans", "thr", "prc", "merge", "min",
             "dets", "other", "/IED", "garbage", "unrev"))
    for d in sorted(full, key=lambda d: d["n_det"])[:25]:
        C.log("%-10s %5s %-9s %-7s %6s %5s %6s | %6d %6d %5.1f %4d/%-3d %4d/%-4d"
              % (d["prefilter"], d["llw"], d["chanset"], d["mode"], d["prc"],
                 d["merge"], d["min_s"], d["n_det"], d["other"],
                 d["per_solid"], d["garbage_hit"], d["garbage_n"],
                 d["unrev_hit"], d["unrev_n"]))

    # per pre-filter: best at 100% recall, and the best recall reachable
    front = []
    for pf in sorted({d["prefilter"] for d in tot}):
        mine = [d for d in tot if d["prefilter"] == pf]
        best_rec = max(d["recall"] for d in mine)
        at_full = sorted([d for d in mine if d["recall"] >= 1.0],
                         key=lambda d: d["n_det"])
        row = {"prefilter": pf, "best_recall": round(best_rec, 4)}
        if at_full:
            b = at_full[0]
            row.update({k: b[k] for k in KEYS if k != "prefilter"})
            row.update(n_det=int(b["n_det"]), other=int(b["other"]),
                       per_solid=round(b["per_solid"], 2),
                       garbage_hit=int(b["garbage_hit"]),
                       unrev_hit=int(b["unrev_hit"]))
        front.append(row)
    with open(os.path.join(C.OUT, "sweep_frontier.csv"), "w", newline="") as fh:
        fields = sorted({k for r in front for k in r}, key=lambda k: (
            ["prefilter", "best_recall"] + list(KEYS)).index(k)
            if k in (["prefilter", "best_recall"] + list(KEYS)) else 99)
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(front)
    C.log("\nper pre-filter")
    for r in front:
        C.log(r)

    # the original, as the lab ran it
    orig = [d for d in tot if d["prefilter"] == "orig30k"
            and d["chanset"] == "even" and d["mode"] == "global"
            and float(d["prc"]) == 99.9 and float(d["merge"]) == 0.3
            and float(d["min_s"]) == 0.025]
    if orig:
        o = orig[0]
        C.log("\nthe original detector (30 kHz raw, 40 ms, even, global 99.9):"
              " %d/%d Solids, %d detections, garbage %d/%d, unreviewed %d/%d"
              % (o["solid_hit"], o["solid_n"], o["n_det"], o["garbage_hit"],
                 o["garbage_n"], o["unrev_hit"], o["unrev_n"]))


if __name__ == "__main__":
    main()
