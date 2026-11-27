import sys
import pandas as pd
import numpy as np
pd.set_option("display.width", 260)
pd.set_option("display.max_colwidth", 72)
B = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
T = pd.read_pickle(B + r"\merged\tests.pkl")
T = T[T.contrast != "variance_PTEN_vs_CTL"]
p = T.id.str.split("|", expand=True)
T["fam"], T["nm"], T["es"], T["clf"], T["var"] = p[0], p[1], p[2], p[3], p[4]
noLFP = ~T.nm.str.contains("lfp|profile_v|fold_|det_peak")
cols = ["id", "contrast", "p", "p_other_set", "effect", "share_same_sign", "share_p05", "n_variants", "rho_year", "rho_log_events", "n_finite"]
mode = sys.argv[1]
if mode == "ds3":
    m = (T["var"].isin(["ds3"]) | T.nm.str.contains("ds3|relsink|unscorable|lit_")) & noLFP & (T.es == "v6")
elif mode == "filter":
    m = (T.fam == "filter") & noLFP
elif mode == "v7":
    m = (T.es == "v7") & noLFP & (T["var"].isin(["all", ""]) | (T.clf == ""))
elif mode == "nocut":
    m = T["var"].isin(["ds1n", "ds2n", "ds1nx", "ds2nx", "ds1n_over_ds2n"]) & noLFP & (T.es == "v6")
else:
    m = (T.clf == "") & noLFP & (T.es == "v6") & ~T.fam.isin(["filter"])
x = T[m & (T.p < 0.05)].copy()
if mode not in ("filter",):
    x = x[(x.p_other_set < 0.1) & (x.same_sign_other_set == 1)]
x = x.sort_values("p")
x["key"] = x.nm + "|" + x["var"]
print(x.groupby("key").head(1)[cols].head(int(sys.argv[2]) if len(sys.argv) > 2 else 30).to_string())
