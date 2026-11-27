import sys
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import numpy as np
import dsdata

for es in ("v6", "v8"):
    recs = dsdata.load(es)
    from collections import Counter
    cnt = Counter(v["verdict"] for r in recs if r.ok for c, v in r.naming.items() if r.eligible(c))
    print(es, dict(cnt))
    if es != "v6":
        continue
    for r in recs:
        if not r.ok and not r.excluded:
            continue
        c = r.used
        t = r.types(c)
        nc = r.naming[c]
        w = r.ds3w[c]
        cj = r.ds3_category(c, which="jarvis")
        cw = r.ds3_category(c)
        def tab(cat):
            if cat is None:
                return "not scorable"
            return "DS1 %3d DS2 %3d DS3 %3d unsc %3d" % tuple(((t == a) & (cat == b)).sum() for a, b in ((1, 1), (2, 2), (0, 3), (0, 0))) if False else \
                "score: outer %3d middle %3d DS3 %3d unscored %3d" % tuple((cat == b).sum() for b in (1, 2, 3, 0))
        print("%-4s%s %-16s si %.2f names %-15s diff %s | n DS1 %3d DS2 %3d | jarvis %s gap %s | widened %s gap %s blade %s" % (
            r.lab, "(EXCL)" if r.excluded else "", c, r.si(c), nc["verdict"], np.round(nc["diff"], 0), (t == 1).sum(), (t == 2).sum(),
            tab(cj), r.ds3_gap_um_jarvis.get(c), tab(cw), w.get("gap_um"), w.get("blade") or w.get("why")))
