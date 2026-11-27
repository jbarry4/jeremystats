"""Print one recording's per-contact numbers from camel_diag.json."""
import json
import os
import sys

D = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "camel_diag.json")))
want = sys.argv[1]
lo = int(sys.argv[2]) if len(sys.argv) > 2 else 1
hi = int(sys.argv[3]) if len(sys.argv) > 3 else 64
for r in D:
    if want not in r["label"]:
        continue
    print(r["label"], "band", r["band"], "bad", r["bad"], "camel", r["camel_frac"], r["dip_hist"])
    per = {x["num"]: x for x in r["per"] if x}
    for n in range(lo, hi + 1):
        x = per.get(n)
        mp = r["mean_prof"][n - 1]
        bar = ("#" * int(min(60, max(0, -mp) / max(1e-9, max(-v for v in r["mean_prof"])) * 40)))
        if x:
            print("  %2d  rms %7.1f  g %.3f  a_b %.3f  a_s %.3f  rn %.3f  %s  csd %8.1f %s" % (
                n, r["rms"][n - 1], x["g"], x["a_base"], x["a_stamp"], x["rn"], x["blocks"], mp, bar))
        else:
            print("  %2d  rms %7.1f  (bad or beside one)                                              csd %8.1f %s" % (
                n, r["rms"][n - 1], mp, bar))
