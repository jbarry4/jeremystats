"""Check: what share of each mouse's undecided events are wider than the mouse's median DS half-width."""
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jpages as J  # noqa: E402
import menu_data as D  # noqa: E402

rc = D.rc()
s = rc[(rc.wf == "strict") & rc.lab.isin(J.ORDER)]
tot_w, tot = 0, 0
for l in J.ORDER:
    e = s[s.lab == l]
    d = e[e.cls == "ds"]
    u = e[e.cls.isin(["both", "neither"])]
    q90 = np.percentile(d.hw, 90)
    w = int((u.hw > d.hw.median()).sum())
    w90 = int((u.hw > q90).sum())
    tot_w += w
    tot += len(u)
    print("%-4s und %3d wider than DS median %3d (%.0f%%), wider than DS 90th pct %3d (%.0f%%)" % (
        l, len(u), w, 100.0 * w / len(u), w90, 100.0 * w90 / len(u)))
print("all: %d of %d (%.0f%%)" % (tot_w, tot, 100.0 * tot_w / tot))
