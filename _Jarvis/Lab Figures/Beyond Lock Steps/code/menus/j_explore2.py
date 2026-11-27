import os
import pickle
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import stats_lib as S  # noqa: E402

Q = pickle.load(open(os.path.join(HERE, "jeremy_freq.pkl"), "rb"))
M = Q["mice"]
LABS = [l for l in F.LABS if l in M]
CTL = [l for l in LABS if F.subgroup(l) == "CTL"]
IEDP = ["m13", "m28", "m3", "m5", "m34"]
KEYS = [(b, n) for b in ("upper", "lower") for n in ("MML", "OML")]
print("mice", len(LABS), "checks reader vs window r:", {l: round(M[l]["bands"]["5-100"].get("check_reader_vs_window", np.nan), 3) for l in LABS})


def show(name, vals):
    T = {r["contrast"]: r for r in S.contrasts(vals)}
    keys = ["KO_dose_PTEN", "KO_dose_all", "IEDneg_vs_CTL", "IEDpos_vs_CTL", "IEDpos_vs_IEDneg"]
    print("%-40s " % name + "  ".join("%s %s(%+.2f)" % (k.replace("_vs_", "/").replace("KO_dose_", "ko:"), F.pnum(T[k]["p"]), T[k]["effect"])
                                       for k in keys if k in T))


print("== Q4 dominant frequency of the DS (notch)")
for sig in ("csd", "lfp"):
    for key in KEYS:
        v = {l: M[l]["bands"]["notch"]["fast"].get(("DS",) + key + (sig,), (np.nan,))[0] for l in LABS}
        print("   values", sig, key, {l: round(x) for l, x in v.items() if np.isfinite(x)})
        show("fast peak %s %s %s" % (sig, *key), {l: x for l, x in v.items() if np.isfinite(x)})
        g = {l: M[l]["bands"]["notch"]["fast"].get(("DS",) + key + (sig,), (np.nan, np.nan))[1] for l in LABS}
        show("fast gain dB %s %s %s" % (sig, *key), {l: x for l, x in g.items() if np.isfinite(x)})
        w = {l: M[l]["bands"]["notch"]["whole"].get(("DS",) + key + (sig,), (np.nan, np.nan)) for l in LABS}
        show("whole peak %s %s %s" % (sig, *key), {l: x[0] for l, x in w.items() if np.isfinite(x[0])})
        show("whole centroid %s %s %s" % (sig, *key), {l: x[1] for l, x in w.items() if np.isfinite(x[1])})
print("== Q7 classes in IED+ mice (notch), sinks relative to the mouse's DS, and frequencies")
ref = {b: np.mean([M[l]["bands"][b]["deep"]["DS"] for l in CTL]) for b in Q["bands"]}
for key in KEYS:
    for k in ("DS", "TZ", "IED"):
        vals = [M[l]["bands"]["notch"]["sink"].get((k,) + key, np.nan) / ref["notch"] for l in IEDP]
        fr = [M[l]["bands"]["notch"]["fast"].get((k,) + key + ("csd",), (np.nan,))[0] for l in IEDP]
        print("  %s %s %-3s sink(ctl=1) %s  fast peak %s" % (key[0], key[1], k, np.round(vals, 2), np.round(fr)))
    wt = [M[l]["bands"]["notch"]["sink"].get(("DS",) + key, np.nan) / ref["notch"] for l in CTL]
    wf = [M[l]["bands"]["notch"]["fast"].get(("DS",) + key + ("csd",), (np.nan,))[0] for l in CTL]
    print("  %s %s WT DS sink %s  fast %s" % (key[0], key[1], np.round(wt, 2), np.round(wf)))
print("deep sink (ctl=1):", {k: np.round([M[l]["bands"]["notch"]["deep"].get(k, np.nan) / ref["notch"] for l in IEDP], 2) for k in ("DS", "TZ", "IED")},
      "WT", np.round([M[l]["bands"]["notch"]["deep"]["DS"] / ref["notch"] for l in CTL], 2))
