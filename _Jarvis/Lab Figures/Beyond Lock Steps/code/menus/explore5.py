import os, sys, pickle
import numpy as np
sys.path.insert(0, os.getcwd())
import warnings; warnings.filterwarnings("ignore")
import menu_data as D
import stats_lib as S
import figlib as F
import outlier as O
hf = D.values("rootcanal|ds_hf_median|v6||")
print("== m7 outlier tests (fast power)")
print("IED- group", O.grubbs({l: hf[l] for l in ["m8", "m33", "m1", "m7"]}, "m7"))
print("high KO group", O.grubbs({l: hf[l] for l in ["m13", "m28", "m7", "m3", "m5", "m34"]}, "m7"))
print("PTEN group", O.grubbs({l: hf[l] for l in ["m8", "m33", "m1", "m7", "m13", "m28", "m3", "m5", "m34"]}, "m7"))
print("all 16", O.grubbs(hf, "m7"))
pt = ["m8", "m33", "m1", "m7", "m13", "m28", "m3", "m5", "m34"]
print("PTEN line", O.line_outlier([F.ko(l) for l in pt], [hf[l] for l in pt], pt, "m7"))
print("all line", O.line_outlier([F.ko(l) for l in F.LABS], [hf[l] for l in F.LABS], F.LABS, "m7"))
T1 = F.contrast_table(hf)
T2 = F.contrast_table(hf, exclude=("m7",))
for c in ("IEDneg_vs_CTL", "IEDpos_vs_IEDneg", "IED3", "lowKO_vs_CTL", "highKO_vs_CTL", "highKO_vs_lowKO", "KO3", "KO_dose_PTEN", "KO_dose_all", "PTEN_vs_CTL"):
    a, b = T1.get(c, {}), T2.get(c, {})
    print("%-18s with m7 P %-9s %-14s eff %+.2f | without P %-9s %-14s eff %+.2f" % (c, F.pnum(a.get("p", np.nan)), a.get("test"), a.get("effect", np.nan),
          F.pnum(b.get("p", np.nan)), b.get("test"), b.get("effect", np.nan)))
print("== common-scale CSD")
U = pickle.load(open("uprof.pkl", "rb"))
G = U["UGRID"]; R = U["regions"]; ref = U["ref_ctl"]
recs = {l: U["recs"][("v6", l)] for l in F.LABS}
for g in ("CTL", "IED-", "IED+"):
    labs = [l for l in F.LABS if F.subgroup(l) == g]
    refs = [recs[l]["ref"] / ref for l in labs]
    print(g, "deepest sink / control ref:", " ".join("%s %.2f" % (l, r) for l, r in zip(labs, refs)), "| mean %.2f" % np.mean(refs))
regs = [(k, a, b) for k, (n, a, b) in zip(F.REGION_KEYS, F.ds_regions(R)[:6])]
per = {l: {k: float(np.nanmean(recs[l]["u_peak_raw"][(G >= max(a, -1.2)) & (G < b)] / ref)) for k, a, b in regs} for l in F.LABS}
for k, a, b in regs:
    v = {l: per[l][k] for l in F.LABS}
    T = F.contrast_table(v)
    print("%-15s [%.2f, %.2f)" % (k, a, b), " ".join("%s %s(%s)" % (c, F.pnum(T[c]["p"]), "+" if T[c]["effect"] > 0 else "-") for c in ("IEDneg_vs_CTL", "IEDpos_vs_CTL", "IEDpos_vs_IEDneg", "highKO_vs_CTL", "KO_dose_PTEN", "KO_dose_all") if c in T),
          "| means", {g: round(np.mean([v[l] for l in F.LABS if F.subgroup(l) == g]), 3) for g in ("CTL", "IED-", "IED+")})
# deepest sink (ref) itself
v = {l: recs[l]["ref"] / ref for l in F.LABS}
T = F.contrast_table(v)
print("deepest sink", " ".join("%s %s(%s)" % (c, F.pnum(T[c]["p"]), "+" if T[c]["effect"] > 0 else "-") for c in T))
# upper and lower sink peaks separately (the profile at u = 0 and u = 1)
for uu in (0.0, 1.0):
    j = int(np.argmin(np.abs(G - uu)))
    v = {l: recs[l]["u_peak_raw"][j] / ref for l in F.LABS}
    T = F.contrast_table(v)
    print("at u=%.0f" % uu, " ".join("%s %s(%s)" % (c, F.pnum(T[c]["p"]), "+" if T[c]["effect"] > 0 else "-") for c in T),
          {g: round(np.mean([v[l] for l in F.LABS if F.subgroup(l) == g]), 3) for g in ("CTL", "IED-", "IED+")})
# amplitude from the Root Canal (LFP), to compare
amp = D.values("rootcanal|ds_amp_median|v6||")
T = F.contrast_table(amp)
print("RC amplitude", " ".join("%s %s(%s)" % (c, F.pnum(T[c]["p"]), "+" if T[c]["effect"] > 0 else "-") for c in T))
print({g: round(np.mean([amp[l] for l in F.LABS if F.subgroup(l) == g]), 1) for g in ("CTL", "IED-", "IED+")})
