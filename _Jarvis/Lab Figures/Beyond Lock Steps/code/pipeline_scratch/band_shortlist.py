"""Filter-battery candidates: a group difference that shows under another
filter, is weaker under the DS filter (5-100 Hz), and shows (same sign,
P < 0.10) under a related filter too.  python band_shortlist.py [n]"""
import sys
import numpy as np
import pandas as pd
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 60)
B = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
T = pd.read_pickle(B + r"\merged_filters\tests.pkl")
M = pd.read_pickle(B + r"\merged_filters\measures.pkl").set_index("id")
T = T[T.contrast != "variance_PTEN_vs_CTL"]
p = T.id.str.split("|", expand=True)
T["fam"], T["nm"], T["es"], T["clf"], T["var"] = p[0], p[1], p[2], p[3], p[4]
T["key"] = T.fam + "|" + T.nm + "|" + T.clf + "|" + T["var"] + "|" + T.contrast
REL = {"b_none": ["b_1_300", "b_1_100"], "b_1_300": ["b_none", "b_1_100", "b_5_300"], "b_1_100": ["b_none", "b_1_300"],
       "b_5_300": ["b_1_300", "b_none"], "b_5_50": ["b_10_40"], "b_10_40": ["b_5_50"]}
P = T.pivot_table(index="key", columns="es", values="p", aggfunc="first")
E = T.pivot_table(index="key", columns="es", values="effect", aggfunc="first")
labs = [c for c in M.columns if c.startswith("m") and c[1:].isdigit()]
# measures whose values are the same under every filter (label-only measures) say nothing about filters
same = {}
for k in P.index:
    f, n, c, v, _ = k.split("|")
    ids = ["|".join([f, n, es, c, v]) for es in ("b_ds", "b_none", "b_10_40")]
    vv = [M.loc[i, labs].values.astype(float) for i in ids if i in M.index]
    same[k] = len(vv) == 3 and all(np.allclose(vv[0], x, equal_nan=True) for x in vv[1:])
rows = []
for k in P.index:
    if same[k] or "lfp" in k:
        continue
    pds = P.loc[k].get("b_ds", np.nan)
    for es, rel in REL.items():
        pe = P.loc[k].get(es, np.nan)
        if not (pe < 0.05):
            continue
        se = np.sign(E.loc[k].get(es, np.nan))
        rep = [r for r in rel if P.loc[k].get(r, np.nan) < 0.10 and np.sign(E.loc[k].get(r, np.nan)) == se]
        if not rep:
            continue
        hidden = not (pds < 0.05) or np.sign(E.loc[k].get("b_ds", np.nan)) != se
        rows.append(dict(key=k, band=es, p=pe, p_ds=pds, eff=E.loc[k][es], eff_ds=E.loc[k].get("b_ds", np.nan), rep=",".join(rep), hidden=hidden))
R = pd.DataFrame(rows)
print("candidates", len(R), "hidden under DS", R.hidden.sum())
R = R[R.hidden].sort_values("p")
R["meas"] = R.key.str.split("|").str[1] + "|" + R.key.str.split("|").str[3]
print(R.groupby("meas").head(1).head(int(sys.argv[1]) if len(sys.argv) > 1 else 40).to_string())
# how often a filter reveals something the DS filter does not, against chance
tot = (T.es != "b_ds").sum()
print("\nraw P < 0.05 by filter:", T.groupby("es").apply(lambda d: "%.1f%%" % (100 * (d.p < 0.05).mean())).to_dict())
print("q_all < 0.10:", (T.q_all < 0.10).sum(), "| q_family < 0.10:", (T.q_family < 0.10).sum())
