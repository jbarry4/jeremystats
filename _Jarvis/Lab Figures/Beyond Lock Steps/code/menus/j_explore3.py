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
LABS = F.LABS
CTL = [l for l in LABS if F.subgroup(l) == "CTL"]
IEDP = ["m13", "m28", "m3", "m5", "m34"]
KEYS = [(b, n) for b in ("upper", "lower") for n in ("MML", "OML")]
fr = M["m2"]["freqs"]


def fast_metrics(db, lo=100, hi=500, glo=250):
    m = (fr >= lo) & (fr <= hi)
    ex = np.clip(10 ** (db[m] / 10.0) - 1, 0, None)
    cen = float((ex * fr[m]).sum() / ex.sum()) if ex.sum() > 0 else np.nan
    g = (fr >= glo) & (fr <= hi)
    return cen, float(np.mean(db[g]))


def show(name, vals):
    T = {r["contrast"]: r for r in S.contrasts(vals)}
    keys = ["KO_dose_PTEN", "KO_dose_all", "IEDneg_vs_CTL", "IEDpos_vs_CTL", "IEDpos_vs_IEDneg", "highKO_vs_CTL"]
    print("%-44s " % name + "  ".join("%s %s(%+.2f)" % (k.replace("_vs_", "/").replace("KO_dose_", "ko:"), F.pnum(T[k]["p"]), T[k]["effect"])
                                       for k in keys if k in T))


for sig in ("csd", "lfp"):
    for key in KEYS:
        kk = ("DS",) + key + (sig,)
        wp = {l: M[l]["bands"]["notch"]["whole"][kk][0] for l in LABS}
        wc = {l: M[l]["bands"]["notch"]["whole"][kk][1] for l in LABS}
        fc = {l: fast_metrics(M[l]["bands"]["notch"]["fast_spec"][kk])[0] for l in LABS}
        fg = {l: fast_metrics(M[l]["bands"]["notch"]["fast_spec"][kk])[1] for l in LABS}
        show("whole peak %s %s %s" % (sig, *key), wp)
        show("whole centroid %s %s %s" % (sig, *key), wc)
        show("fast centroid %s %s %s" % (sig, *key), fc)
        show("fast gain 250-500 %s %s %s" % (sig, *key), fg)
    print()
print("== by band: whole centroid csd upper MML / fast centroid 100-300")
for band in Q["bands"]:
    kk = ("DS", "upper", "MML", "csd")
    wc = {l: M[l]["bands"][band]["whole"][kk][1] for l in LABS}
    show("whole centroid %s" % band, wc)
    if kk in M["m2"]["bands"][band]["fast_spec"]:
        fc = {l: fast_metrics(M[l]["bands"][band]["fast_spec"][kk], 100, 300, 200)[0] for l in LABS}
        fg = {l: fast_metrics(M[l]["bands"][band]["fast_spec"][kk], 100, 300, 200)[1] for l in LABS}
        show("fast centroid 100-300 %s" % band, fc)
        show("fast gain 200-300 %s" % band, fg)
print("== Q7 classes: fast centroid and gain (notch, csd)")
for key in KEYS:
    for k in ("DS", "TZ", "IED"):
        c = [fast_metrics(M[l]["bands"]["notch"]["fast_spec"][(k,) + key + ("csd",)])[0] if (k,) + key + ("csd",) in M[l]["bands"]["notch"]["fast_spec"] else np.nan for l in IEDP]
        g = [fast_metrics(M[l]["bands"]["notch"]["fast_spec"][(k,) + key + ("csd",)])[1] if (k,) + key + ("csd",) in M[l]["bands"]["notch"]["fast_spec"] else np.nan for l in IEDP]
        print("  %s %s %-3s centroid %s gain %s" % (key[0], key[1], k, np.round(c), np.round(g, 1)))
    c = [fast_metrics(M[l]["bands"]["notch"]["fast_spec"][("DS",) + key + ("csd",)])[0] for l in CTL]
    g = [fast_metrics(M[l]["bands"]["notch"]["fast_spec"][("DS",) + key + ("csd",)])[1] for l in CTL]
    print("  %s %s WT  centroid %s gain %s" % (key[0], key[1], np.round(c), np.round(g, 1)))
ref = np.mean([M[l]["bands"]["notch"]["deep"]["DS"] for l in CTL])
for key in KEYS:
    for k in ("DS", "TZ", "IED"):
        v = [M[l]["bands"]["notch"]["sink"].get((k,) + key, np.nan) / ref for l in IEDP]
        print("  sink %s %s %-3s %s" % (key[0], key[1], k, np.round(v, 2)))
    print("  sink %s %s WT  %s" % (key[0], key[1], np.round([M[l]["bands"]["notch"]["sink"][("DS",) + key] / ref for l in CTL], 2)))
