import os
"""General lead 4 (LFP above the upper blade, share of its largest value):
does it hold once the part every contact shares is taken out?"""
import sys
import numpy as np
from scipy import stats as st
sys.path.insert(0, os.environ.get("KBAT", "/gpfs2/scratch/sakhava1/kcnt1_prelim/battery"))
import dsdata
import normcurves as N

i = int(np.argmin(np.abs(N.GRID_U - (-0.5))))
for es in ("v6", "v8"):
    rows = []
    for r in dsdata.load(es):
        if not r.ok or r.landmarks is None:
            continue
        good = r.good(np.arange(64))
        out = {"lab": r.lab, "g": r.group, "sg": r.subgroup}
        for nm, X in (("raw", r.lfp_peak), ("cmr", r.lfp_peak - np.median(r.lfp_peak[:, good], axis=1, keepdims=True))):
            m = dsdata.fill_bad(X.mean(axis=0), r.bad_rows)
            u = r.on_u(m, N.GRID_U)
            u = u / np.nanmax(np.abs(u))
            out[nm] = float(np.nanmean(u[i - 2:i + 3]))
        rows.append(out)
    for nm in ("raw", "cmr"):
        v = np.array([o[nm] for o in rows])
        g = np.array([o["g"] for o in rows])
        lvl = np.array([{"CTL": 0, "IED-": 1, "IED+": 2}[o["sg"]] for o in rows])
        print(es, nm, "values:", " ".join("%s %+.2f" % (o["lab"], o[nm]) for o in rows))
        print("   PTEN against control P = %.3f | trend CTL, IED-, IED+: Kendall tau %.2f, P = %.3f" % (
            st.mannwhitneyu(v[g == "CTL"], v[g == "PTEN"]).pvalue, *st.kendalltau(lvl, v)))
