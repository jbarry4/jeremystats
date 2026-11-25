"""Check the 10/7/2025 room + arena frame pair: direct floor speed (angle drift between frames) vs the ride method."""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a1_extract import passive_rides, read  # noqa: E402

ROOT = r"C:\Users\Z390\Desktop\jeremystats\KCNT1 Active Avoidance"
hits = {}
for pat in ("M1S0_ArenaTrack_Arena_20251007_114827.dat", "M1S0_RoomTrack_Room_20251007_114827.dat"):
    found = glob.glob(os.path.join(ROOT, "**", pat), recursive=True)
    print(pat, found[:2])
    hits[pat] = found[0]


def xy(path):
    h, d = read(path)
    px = float(h["TrackerResolution_PixPerCM"])
    cx, cy = map(float, h["ArenaCenterXY"].split())
    lost = d.state.values == 5
    x = pd.Series(np.where(lost, np.nan, d.x.values)).ffill().bfill().values
    y = pd.Series(np.where(lost, np.nan, d.y.values)).ffill().bfill().values
    t = (d.t_ms.values - d.t_ms.values[0]) / 1000.0
    return (x - cx) / px, -(y - cy) / px, t, d


xa, ya, ta, da = xy(hits["M1S0_ArenaTrack_Arena_20251007_114827.dat"])
xr, yr, tr, dr = xy(hits["M1S0_RoomTrack_Room_20251007_114827.dat"])
n = min(len(ta), len(tr))
print("samples", len(ta), len(tr), "same frames:", np.array_equal(da.frame.values[:n], dr.frame.values[:n]))
th_r = np.unwrap(np.arctan2(yr[:n], xr[:n]))
th_a = np.unwrap(np.arctan2(ya[:n], xa[:n]))
diff = np.degrees(th_r - th_a)
ok = np.hypot(xr[:n], yr[:n]) > 5
sl = np.polyfit(tr[:n][ok], diff[ok], 1)[0]
print("direct: room angle minus arena angle drifts at %.3f deg/s (sign = direction)" % sl)
rides = passive_rides(xr, yr, tr)
print("ride method on the room track: n %d, median %.3f, IQR %.2f-%.2f" % (len(rides), np.median(rides),
                                                                          np.percentile(rides, 25), np.percentile(rides, 75)))
np.savez(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pair_1007.npz"), t=tr[:n][ok], diff=diff[ok], rides=np.array(rides))
