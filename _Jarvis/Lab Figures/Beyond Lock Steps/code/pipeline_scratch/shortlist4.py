"""Run 4 candidates: raw P < 0.05 on the Halo set, same sign and P < 0.10 on
the No P-spikes set; no absolute distances or amplitudes (2026-11-18).
  python shortlist4.py general|typed|ds3|q [n]"""
import sys
import numpy as np
import pandas as pd
pd.set_option("display.width", 260)
pd.set_option("display.max_colwidth", 70)
B = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
T = pd.read_pickle(B + r"\merged\tests.pkl")
T = T[T.contrast != "variance_PTEN_vs_CTL"]
p = T.id.str.split("|", expand=True)
T["fam"], T["nm"], T["es"], T["clf"], T["var"] = p[0], p[1], p[2], p[3], p[4]
ABS = (T.unit.isin(["um", "uV", "CSD units", "CSD units x ms", "detector units"]) | T.nm.str.contains("_um")) & ~T.nm.str.contains(r"_(cv|skew|p90p10)$")
cols = ["id", "contrast", "test", "p", "p_other_set", "effect", "q_family", "p_maxT", "rho_year", "rho_log_events", "n_finite", "unit"]
mode = sys.argv[1]
if mode == "q":
    print(T.sort_values("q_family").head(15)[cols].to_string())
    sys.exit()
base = (T.es == "v6") & ~ABS & (T.p < 0.05) & (T.p_other_set < 0.10) & (T.same_sign_other_set == 1)
if mode == "general":
    m = base & (T.clf == "")
elif mode == "typed":
    m = base & (T.clf == "winner") & ~T["var"].isin(["ds3"]) & ~T.nm.str.contains("ds3|relsink|unscorable")
else:
    m = base & (T["var"].isin(["ds3"]) | T.nm.str.contains("ds3|relsink|unscorable"))
x = T[m].sort_values("p").copy()
x["key"] = x.nm.str.replace(r"_(median|mean|cv|sd|skew|p90p10|mad)$", "", regex=True) + "|" + x["var"]
print(x.groupby("key").head(1)[cols].head(int(sys.argv[2]) if len(sys.argv) > 2 else 30).to_string())
