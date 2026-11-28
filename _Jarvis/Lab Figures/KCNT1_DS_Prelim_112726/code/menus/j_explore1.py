import os
import pickle
import sys
import warnings

import numpy as np
from scipy import stats as st

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402

B = pickle.load(open(os.path.join(HERE, "jeremy_battery.pkl"), "rb"))
LABS = F.LABS
PT = [l for l in LABS if F.META[l]["group"] != "CTL"]


def show(name, vals):
    T = F.contrast_table(vals)
    keys = ["KO_dose_PTEN", "KO_dose_all", "IEDneg_vs_CTL", "IEDpos_vs_CTL", "highKO_vs_CTL", "lowKO_vs_CTL"]
    print("%-34s " % name + "  ".join("%s %s(%+.2f)" % (k.replace("_vs_", "/").replace("KO_dose_", "ko:"), F.pnum(T[k]["p"]), T[k]["effect"])
                                       for k in keys if k in T))


def es_fit(lab, sel=None):
    e = B["events_v6"][lab]
    ref = B["ref"]["v6"]
    x = np.log2(e["sink"] / ref)
    y = e["hf"]
    ok = np.isfinite(x) & np.isfinite(y) & (e["sink"] > 0)
    if sel is not None:
        ok &= sel
    if ok.sum() < 8:
        return np.nan, np.nan
    sl, ic, _a, _b = st.theilslopes(y[ok], x[ok])
    return ic, sl


for es in ("v6",):
    P = B["per"][es]
    ref = B["ref"][es]
    print("== Q1 strength and output (set %s, control ref %.3f)" % (es, ref))
    for typ in ("all", "ds1", "ds2"):
        for q in ("sink", "slope", "rise", "peak"):
            v = {l: P[l][typ][q] / (ref if q in ("sink", "slope", "peak") else 1) for l in LABS if typ in P[l] and np.isfinite(P[l][typ][q])}
            show("%s %s" % (typ, q), v)
    for typ, k in (("all", None), ("ds1", 1), ("ds2", 2)):
        ics, sls = {}, {}
        for l in LABS:
            sel = None if k is None else (B["events_v6"][l]["types"] == k)
            ic, sl = es_fit(l, sel)
            if np.isfinite(ic):
                ics[l], sls[l] = ic, sl
        show("%s fast power at standard sink" % typ, ics)
        show("%s dB per doubling of sink" % typ, sls)
    print("== Q2 DS1/DS2")
    both = {}
    for l in LABS:
        d = P[l]
        n1, n2, n = d["n1"], d["n2"], d["n"]
        ok = d["si"] is not None and min(n1, n2) >= max(5, 0.05 * n) and d["si"] >= 0.45
        both[l] = ok
        print("  %-4s %-4s si %s n1 %3d n2 %3d share %.2f makes both: %s" % (l, d["subgroup"], "%.2f" % d["si"] if d["si"] else "none", n1, n2,
                                                                      n1 / max(n1 + n2, 1), ok))
    for g in ("CTL", "IED-", "IED+"):
        labs = [l for l in LABS if F.subgroup(l) == g]
        print("  ", g, "makes both", sum(both[l] for l in labs), "of", len(labs))
    show("DS1 per minute", {l: P[l]["n1"] / P[l]["dur_min"] for l in LABS if P[l]["si"] is not None})
    show("DS2 per minute", {l: P[l]["n2"] / P[l]["dur_min"] for l in LABS if P[l]["si"] is not None})
    show("DS1 share", {l: P[l]["n1"] / max(P[l]["n1"] + P[l]["n2"], 1) for l in LABS if P[l]["si"] is not None})
    show("separation index", {l: P[l]["si"] for l in LABS if P[l]["si"] is not None})
    for q in ("sink", "rise", "decay", "slope"):
        v = {l: (P[l]["ds1"][q] - P[l]["ds2"][q]) / (ref if q in ("sink", "slope") else 1) for l in LABS if "ds1" in P[l] and "ds2" in P[l]}
        show("DS1 minus DS2 %s" % q, v)
print("== Q3 layers (v6)")
for es in B["sets"]:
    P = B["per"][es]
    ref = B["ref"][es]
    print("-- set", es)
    for blade in ("upper", "lower"):
        for lay in ("MML", "OML"):
            v = {l: P[l]["all"]["layers"][(blade, lay)] / ref for l in LABS}
            show("%s %s sink" % (blade, lay), v)
        v = {l: P[l]["all"]["layers"][(blade, "OML")] / (P[l]["all"]["layers"][(blade, "OML")] + P[l]["all"]["layers"][(blade, "MML")]) for l in LABS}
        show("%s OML share" % blade, v)
