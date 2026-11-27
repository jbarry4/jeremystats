import sys
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import numpy as np
import dsdata
import normcurves as N

for es in ("v6", "v8"):
    tot = agree = swap = undec = 0
    rows = []
    for r in dsdata.load(es):
        if not r.ok:
            continue
        k = r.landmarks
        d_um = [(k["GU"] - k["U"]) * 50, (k["L"] - k["GL"]) * 50]
        for c in dsdata.CLASSIFIERS:
            if not (r.has(c) and r.eligible(c)):
                continue
            ty = N.typed(r, c)
            c1, c2 = np.array(ty["cen"][1]), np.array(ty["cen"][2])
            diff = (c1 - c2) * np.array(d_um)          # um, + = DS1 farther out
            s = np.nansum(diff)
            tot += 1
            if abs(s) < 25:
                undec += 1
                tag = "same place"
            elif s > 0:
                agree += 1
                tag = "ok"
            else:
                swap += 1
                tag = "SWAPPED"
            if c == r.used or tag == "SWAPPED":
                rows.append("%s %-4s %-16s %-10s diff upper %+5.0f lower %+5.0f um  n1 %d n2 %d%s" % (es, r.lab, c, tag, diff[0], diff[1], (r.types(c) == 1).sum(), (r.types(c) == 2).sum(), "  <- used" if c == r.used else ""))
    print(es, "total", tot, "agree", agree, "swapped", swap, "same place", undec)
    if es == "v6":
        print("\n".join(rows))
