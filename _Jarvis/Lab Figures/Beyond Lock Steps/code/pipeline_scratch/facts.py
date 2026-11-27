import pandas as pd
import numpy as np
B = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
T = pd.read_pickle(B + r"\merged\tests.pkl")
M = pd.read_pickle(B + r"\merged\measures.pkl").set_index("id")
labs = [c for c in M.columns if c.startswith("m") and c[1:].isdigit()]
G = {"CTL": ["m2", "m21", "m22", "m26", "m59", "m60", "m61"], "IED-": ["m8", "m33", "m1", "m7"], "IED+": ["m13", "m28", "m3", "m5", "m34"]}
L = [l.split() for l in open(__file__.replace("facts.py", "picks.txt")).read().strip().splitlines()]
for i, c in L:
    if i not in M.index:
        print("MISSING", i)
        continue
    r = T[(T.id == i) & (T.contrast == c)].iloc[0]
    rr = T[T.id == i].set_index("contrast")
    print("\n", i, c, "| p %.4g other %.3g eff %+.2f same %.2f p05 %.2f/%d | q_fam %.2f maxT %s | yr %+.2f ev %+.2f" % (
        r.p, r.p_other_set, r.effect, r.share_same_sign, r.share_p05, r.n_variants, r.q_family, r.p_maxT, r.rho_year, r.rho_log_events))
    v = M.loc[i][labs]
    for g, ls in G.items():
        x = [(l, v[l]) for l in ls if pd.notna(v[l])]
        print("   %-4s " % g + " ".join("%s:%.3g" % t for t in x))
    print("   " + " | ".join("%s %.3f(%+.2f)" % (k, a, b) for k, a, b in zip(rr.index, rr.p, rr.effect)))
    print("   " + M.loc[i]["desc"])
