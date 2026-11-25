"""Poster panel: confirmed IEDs per minute in the 2022 KCNT1 urethane recordings, by genotype.

Sessions and genotypes are the analysis set in KCNt14Shahriar.xlsx (Het M19s4, M22; Control M5s2, M6s4, M10s2,
M11s6, M13s3; Hom M2s2, M4s2, M7s3, M8s3, M9s3, M12s4, M14s2, M15s6). Counts are the 'Solid IEDs' (detected, then
kept in review) of KCNT1_urethane_sessions.csv; M22's two valid sessions (s2, s3) are pooled into one mouse.
usage: python -I urethane_plot.py OUT.png
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as st  # noqa: E402

CSV = (r"C:\Users\Z390\Desktop\jeremystats\Barry Playground\KCNT1 Spreadsheets"
       r"\GitHub__jeremystats__KCNT1_urethane_sessions.csv")
SET = {"WT": [(5, 2), (6, 4), (10, 2), (11, 6), (13, 3)],
       "Het": [(19, 4), (22, 2), (22, 3)],
       "Hom": [(2, 2), (4, 2), (7, 3), (8, 3), (9, 3), (12, 4), (14, 2), (15, 6)]}
GC = {"WT": "#8c8c8c", "Het": "#e08a2c", "Hom": "#7b2d8e"}
INK, SOFT, LINE = "#1d2433", "#5a6273", "#9aa1ad"

d = pd.read_csv(CSV)
d["key"] = list(zip(d.m, d.s))
rows = []
for g, keys in SET.items():
    for k in keys:
        r = d[d.key == k]
        assert len(r) == 1, k
        r = r.iloc[0]
        rows.append(dict(geno=g, mouse=int(r.m), session=int(r.s), solid=int(r["Solid IEDs"]),
                         minutes=float(r["Duration (s)"]) / 60.0))
R = pd.DataFrame(rows)
M = R.groupby(["geno", "mouse"]).agg(solid=("solid", "sum"), minutes=("minutes", "sum")).reset_index()
M["rate"] = M.solid / M.minutes
print(R.to_string())
print(M.to_string())
wt, hom, het = (M[M.geno == g].rate.values for g in ("WT", "Hom", "Het"))
p = st.mannwhitneyu(hom, wt, alternative="two-sided", method="exact").pvalue
print("Hom vs WT Mann-Whitney exact P = %.4f; medians WT %.2f Hom %.2f Het %.2f" % (p, np.median(wt), np.median(hom),
                                                                                    np.median(het)))

FS = 17
plt.rcParams.update({"font.family": ["Helvetica", "Arial"], "font.size": FS, "axes.labelsize": FS,
                     "xtick.labelsize": FS, "ytick.labelsize": FS - 2, "axes.linewidth": 1.4,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "text.color": INK, "axes.labelcolor": INK,
                     "xtick.major.width": 1.4, "ytick.major.width": 1.4, "pdf.fonttype": 42})
fig, ax = plt.subplots(figsize=(5.2, 4.3))
rs = np.random.RandomState(3)
for i, g in enumerate(("WT", "Het", "Hom")):
    v = M[M.geno == g].rate.values
    x = i + (rs.rand(v.size) - 0.5) * 0.28
    ax.scatter(x, v, s=110, color=GC[g], edgecolors="white", linewidths=1.2, zorder=3)
    ax.plot([i - 0.26, i + 0.26], [np.median(v)] * 2, color=INK, lw=2.6, zorder=4, solid_capstyle="butt")
ax.set_xticks([0, 1, 2])
ax.set_xticklabels(["WT\n(n = %d)" % wt.size, "Het\n(n = %d)" % het.size, "Hom\n(n = %d)" % hom.size])
ax.tick_params(axis="x", length=0)
ax.set_ylabel("Confirmed IEDs per minute")
ax.set_xlim(-0.6, 2.6)
top = M.rate.max()
ax.set_ylim(-0.12, top * 1.32)
y = top * 1.12
ax.plot([0, 0, 2, 2], [y - top * 0.04, y, y, y - top * 0.04], color=INK, lw=1.6)
stars = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))
ax.text(1, y + top * 0.02, "%s (P = %.3f)" % (stars, p), ha="center", va="bottom", fontsize=FS - 2)
fig.tight_layout()
fig.savefig(sys.argv[1], dpi=400, facecolor="white")
print("wrote", sys.argv[1])
