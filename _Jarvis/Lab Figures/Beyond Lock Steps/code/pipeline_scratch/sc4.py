import sys
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import numpy as np
import dsdata


def width_um(p, row):
    """Half-max width (um) of the sink lobe of profile p around row."""
    s = -p
    h = s[row] / 2
    lo = hi = row
    while lo - 1 >= 0 and s[lo - 1] > h:
        lo -= 1
    while hi + 1 < s.size and s[hi + 1] > h:
        hi += 1
    return (hi - lo + 1) * 50.0


for r in dsdata.load("v6"):
    if not r.ok:
        continue
    c = r.used
    s = r.ds3_score.get(c)
    t = r.types(c)
    if s is None:
        print(r.lab, "unscorable")
        continue
    s = np.asarray(s, float)
    cat = np.where(~np.isfinite(s), 0, np.where(s > 0.5, 1, np.where(s < -0.5, 2, 3)))
    M = np.zeros((2, 4), int)
    for a in (1, 2):
        for b in range(4):
            M[a - 1, b] = ((t == a) & (cat == b)).sum()
    m = r.mean_csd_peak
    k = r.landmarks
    print("%-4s %-16s gap %s um | class DS1: score DS1 %3d DS2 %3d DS3 %3d unsc %3d | class DS2: score DS1 %3d DS2 %3d DS3 %3d unsc %3d | mean sink width upper %3.0f lower %3.0f um | median |score| %.2f" % (
        r.lab, c, r.ds3_gap_um.get(c), M[0, 1], M[0, 2], M[0, 3], M[0, 0], M[1, 1], M[1, 2], M[1, 3], M[1, 0],
        width_um(m, k["rowU"]), width_um(m, k["rowL"]), np.nanmedian(np.abs(s))))
