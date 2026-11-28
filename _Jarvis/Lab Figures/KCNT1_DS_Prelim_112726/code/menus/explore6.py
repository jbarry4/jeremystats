import os
import json, os, glob, collections
import numpy as np
RUNS = os.environ.get("KRUNS", "/gpfs2/scratch/sakhava1/kcnt1_prelim/er2runs")
L = json.load(open(os.path.join(RUNS, "r006", "leaderboard.json")))
mi = L["most_important"]
print(type(mi), (list(mi.keys())[:10] if isinstance(mi, dict) else len(mi)))
s = json.dumps(mi)[:2500]
print(s)
print("bar", L["bar"])
res = [json.load(open(f)) for f in glob.glob(os.path.join(RUNS, "r006", "results", "*.json"))]
for target in ("iedpos_vs_iedneg", "low_vs_high"):
    rr = [r for r in res if r["target"] == target and r.get("passes")]
    print(target, len(rr), [(r["view"], r["model"], round(r["score"]["main"], 3)) for r in rr])
    per = collections.defaultdict(list)
    for r in rr:
        for c in r["calls"]:
            per[c["lab"]].append(c["call"])
    for lab, v in per.items():
        v = np.array(v)
        print("   %-4s mean %.2f  q25 %.2f q75 %.2f  min %.2f max %.2f  n %d" % (lab, v.mean(), np.percentile(v, 25), np.percentile(v, 75), v.min(), v.max(), v.size))
