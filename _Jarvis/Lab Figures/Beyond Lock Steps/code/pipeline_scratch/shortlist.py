import sys
import pandas as pd
import numpy as np
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 70)
B = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
T = pd.read_pickle(B + r"\merged\tests.pkl")
print(T.columns.tolist())
print(T.sort_values("q_all").head(5)[["id", "contrast", "p", "q_all", "q_contrast", "q_family", "p_maxT", "effect"]])
# shortlist: v6, raw p<0.01, same sign other set & other-set p<0.05, no strong confound
c = T[(T["p"] < 0.01) & (T["id"].str.contains(r"\|v6\|")) & (T["contrast"] != "variance_PTEN_vs_CTL")].copy()
c = c[(c["p_other_set"] < 0.05) & (c["same_sign_other_set"] == 1)]
M = pd.read_pickle(B + r"\merged\measures.pkl").set_index("id")
c["rho_year"] = c["id"].map(M["rho_year"])
c["rho_ev"] = c["id"].map(M["rho_log_events"])
c["fam"] = c["id"].str.split("|").str[0]
c["name"] = c["id"].str.split("|").str[1]
c["var"] = c["id"].str.split("|").str[4]
c = c.sort_values("p")
mode = sys.argv[1] if len(sys.argv) > 1 else "all"
if mode == "all":
    sub = c[c["var"].isin(["all", ""]) | (c["id"].str.split("|").str[3] == "")]
else:
    sub = c[~(c["var"].isin(["all", ""]))]
g = sub.groupby("name").head(1).head(60)
print(g[["id", "contrast", "p", "p_other_set", "effect", "share_same_sign", "share_p05", "n_variants", "rho_year", "rho_ev"]].to_string())
