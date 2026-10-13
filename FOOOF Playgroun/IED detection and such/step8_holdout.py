# -*- coding: utf-8 -*-
"""Step 8 -- would the chosen setting have caught IEDs it was not chosen on?

Choosing the best of 942 settings on the same 169 Solids it is then scored
on flatters it. This is the honest version: for each recording in turn, the
setting is chosen on the OTHER NINE (every Solid there caught, fewest
detections), and then scored on the held-out one. A setting that only works
because it was fitted to a recording shows up here as a missed Solid.

Done twice: once choosing the cheapest setting, and once choosing the
cheapest setting that is NOT on a cliff -- one whose two stricter neighbours
(next percentile up, one more channel required) also keep every Solid on the
nine. A setting with room on both sides is less likely to have been lucky.

    python step8_holdout.py
"""
import csv
import glob
import json
import os
from collections import defaultdict

import ied_common as C

KEYS = ("band", "llw", "prc", "merge", "kmin")
PRCS = ["99.8", "99.85", "99.88", "99.9", "99.92", "99.95", "99.97"]


def load():
    per = defaultdict(dict)          # setting -> key -> row
    for f in glob.glob(os.path.join(C.OUT, "refine", "*.csv")):
        for r in csv.DictReader(open(f)):
            per[tuple(r[k] for k in KEYS)][r["key"]] = r
    return per


def stricter(s):
    band, llw, prc, merge, kmin = s
    out = []
    i = PRCS.index(prc)
    if i + 1 < len(PRCS):
        out.append((band, llw, PRCS[i + 1], merge, kmin))
    out.append((band, llw, prc, merge, str(int(kmin) + 1)))
    return out


def full(per, s, keys):
    rows = per.get(s)
    if not rows or any(k not in rows for k in keys):
        return False
    return all(int(rows[k]["solid_hit"]) >= int(rows[k]["solid_n"]) for k in keys)


def cost(per, s, keys):
    return sum(int(per[s][k]["n_det"]) for k in keys)


def main():
    per = load()
    recs = sorted({k for v in per.values() for k in v})
    out = {}
    for robust in (False, True):
        lost, dets, picks = 0, 0, []
        for held in recs:
            train = [k for k in recs if k != held]
            ok = [s for s in per if full(per, s, train)]
            if robust:
                ok = [s for s in ok
                      if all(full(per, n, train) for n in stricter(s))]
            best = min(ok, key=lambda s: cost(per, s, train))
            r = per[best][held]
            miss = int(r["solid_n"]) - int(r["solid_hit"])
            lost += miss
            dets += int(r["n_det"])
            picks.append((held, best, miss, int(r["n_det"])))
        name = "robust" if robust else "cheapest"
        out[name] = {"lost": lost, "dets_on_heldout": dets, "picks": picks}
        C.log("\n=== choosing the %s setting on nine, scoring on the tenth" % name)
        for held, best, miss, n in picks:
            C.log("  held out %-8s chose %s -> missed %d Solid(s), %d detections"
                  % (held, best, miss, n))
        C.log("  TOTAL: %d of 169 Solids missed on recordings the setting never "
              "saw; %d detections" % (lost, dets))
    # and the two fixed candidates, scored on all ten
    for name, s in (("study winner", ("car_10_300", "0.02", "99.9", "0.3", "6")),
                    ("refine winner", ("car_lp300", "0.015", "99.92", "0.5", "7"))):
        if s in per:
            C.log("%s %s: %d dets, solids %d/%d; stricter neighbours keep all: %s"
                  % (name, s, cost(per, s, recs),
                     sum(int(per[s][k]["solid_hit"]) for k in recs),
                     sum(int(per[s][k]["solid_n"]) for k in recs),
                     [full(per, n, recs) for n in stricter(s)]))
    json.dump(out, open(os.path.join(C.OUT, "holdout.json"), "w"), indent=1,
              default=str)


if __name__ == "__main__":
    main()
