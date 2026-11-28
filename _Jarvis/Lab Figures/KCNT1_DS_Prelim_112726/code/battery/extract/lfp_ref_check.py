import os
"""Is the 'where the LFP is largest' result a reference effect? Same measure
with the LFP as recorded and with a common-median reference (each event's
median over the good contacts subtracted from every contact, which removes
anything every contact shares, the reference included)."""
import sys
import numpy as np
from scipy import stats as st
sys.path.insert(0, os.environ.get("KBAT", "/gpfs2/scratch/sakhava1/kcnt1_prelim/battery"))
import dsdata

for es in ("v6", "v8"):
    rows = []
    for r in dsdata.load(es):
        if not r.ok or r.landmarks is None:
            continue
        k = r.landmarks
        good = r.good(np.arange(64))
        L = r.lfp_peak.copy()
        cmr = L - np.median(L[:, good], axis=1, keepdims=True)
        lo, hi = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)
        sel = r.good(np.arange(lo, hi + 1))
        src = r.good(np.arange(int(k["rowGU"]), int(k["rowGL"]) + 1))
        out = {"lab": r.lab, "g": r.group, "sg": r.subgroup}
        for nm, X in (("raw", L), ("cmr", cmr)):
            pos = r.u(sel[X[:, sel].argmax(axis=1)])
            out[nm + "_pos_u"] = float(np.median(pos))
            out[nm + "_src_uv"] = float(np.median(X[:, src].mean(axis=1)))
            out[nm + "_common_uv"] = float(np.median(np.median(X[:, good], axis=1)))
        rows.append(out)
    print("\n==", es, "(per recording: median over events)")
    print("%-4s %-4s | as recorded: LFP at the source %7s uV, shared by all contacts %7s uV, largest at u %6s | common-median reference: source %7s uV, largest at u %6s" % (
        "", "", "", "", "", "", ""))
    for o in rows:
        print("%-4s %-4s | as recorded: %+7.0f %+7.0f %+6.2f | common-median: %+7.0f %+6.2f" % (o["lab"], o["sg"], o["raw_src_uv"], o["raw_common_uv"], o["raw_pos_u"], o["cmr_src_uv"], o["cmr_pos_u"]))
    for nm in ("raw", "cmr"):
        a = np.array([o[nm + "_pos_u"] for o in rows if o["g"] == "CTL"])
        b = np.array([o[nm + "_pos_u"] for o in rows if o["g"] == "PTEN"])
        bf = st.levene(a, b, center="median")
        mw = st.mannwhitneyu(a, b)
        print("%s: where the LFP is largest (u): CTL SD %.2f, PTEN SD %.2f | spread (Brown-Forsythe) P = %.3f | level (Mann-Whitney) P = %.3f" % (
            {"raw": "As recorded", "cmr": "Common-median reference"}[nm], a.std(), b.std(), bf.pvalue, mw.pvalue))
    s = np.array([o["raw_src_uv"] for o in rows]); c = np.array([o["raw_common_uv"] for o in rows])
    print("as recorded, LFP at the source against the part all contacts share: Spearman rho %.2f" % st.spearmanr(s, c).correlation)
