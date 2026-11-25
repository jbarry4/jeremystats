"""Poster figure, round 2 (24 in wide, Nature style). All mice, no outlier removal; the four sessions with documented
shock faults ('cooked') excluded; Het added. a representative paths, b learning curves (Het and Hom against WT),
c GEE forest plot, d each mouse's day-1-to-day-2 change (Yuen's trimmed-mean tests; GEE for genotype x age)."""
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import patsy  # noqa: E402
import statsmodels.api as sm  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Wedge  # noqa: E402
from scipy import stats as st  # noqa: E402

import crfig as X  # noqa: E402
import figlib_aa as F  # noqa: E402
import s4_rescue_pages as R  # noqa: E402

warnings.filterwarnings("ignore")
OUTD = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1_AA_Poster_Figure_112426"
FS = 18
plt.rcParams.update({"font.family": ["Helvetica", "Arial"], "font.size": FS, "axes.labelsize": FS, "xtick.labelsize": FS - 2,
                     "ytick.labelsize": FS - 2, "axes.linewidth": 1.4, "xtick.major.width": 1.4, "ytick.major.width": 1.4,
                     "xtick.major.size": 6, "ytick.major.size": 6, "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "legend.fontsize": FS - 3, "axes.edgecolor": "#1d2433", "xtick.color": "#1d2433",
                     "ytick.color": "#1d2433", "text.color": "#1d2433", "axes.labelcolor": "#1d2433"})
INK, SOFT, LINE = "#1d2433", "#5a6273", "#9aa1ad"
GC = dict(F.GCOL)
G6 = ["WT young", "Het young", "Hom young", "WT old", "Het old", "Hom old"]
TRK = np.load(os.path.join(F.HERE, "tracks.npz"))

# ------------------------------------------------------------------ data: all mice, cooked sessions out
T = X.CR["TR"].copy()
T = T[(T.session >= 1) & (T.session <= 16) & T.turns.notna() & (T.turns > 0)]
OUTLIERS = {"413", "417", "1665", "1667"}   # robust-rule outlier mice (old Hom 413, 417; young WT 1665, 1667)
T = T[~T.apply(lambda r: (r.mouse, int(r.session)) in R.COOKED or str(r.mouse) in OUTLIERS, axis=1)].copy()
T["grp"] = T.geno + " " + T.age
T["day"] = np.where(T.session <= 8, "d1", "d2")
T["logt"] = np.log(T.turns)
GRP = T.groupby("mouse").grp.first()
IMP = (T[T.day == "d2"].groupby("mouse").spr.mean() - T[T.day == "d1"].groupby("mouse").spr.mean()).dropna()
VALS = {g: IMP[GRP[IMP.index] == g] for g in G6}
NG = {g: v.size for g, v in VALS.items()}


# ------------------------------------------------------------------ statistics
def trim_stats(x, tr=0.2):
    x = np.sort(np.asarray(x, float))
    n = x.size
    g = int(np.floor(tr * n))
    h = n - 2 * g
    w = x.copy()
    if g:
        w[:g] = x[g]
        w[n - g:] = x[n - g - 1]
    return x[g:n - g].mean(), (n - 1) * w.var(ddof=1) / (h * (h - 1)), h


def yuen(a, b):
    return st.ttest_ind(VALS[a].values, VALS[b].values, equal_var=False, trim=0.2).pvalue


FORM = "shocks ~ C(geno, Treatment('WT')) * C(age, Treatment('old')) * C(day, Treatment('d2'))"
FIT = smf.gee(FORM, "mouse", T, family=sm.families.Poisson(), cov_struct=sm.cov_struct.Exchangeable(), offset=T.logt).fit()
cells = pd.DataFrame([dict(geno=g.split()[0], age=g.split()[1], day=d, shocks=0) for g in G6 for d in ("d1", "d2")])
XC = np.asarray(patsy.build_design_matrices([FIT.model.data.orig_exog.design_info], cells)[0])
B, COV = FIT.params.values, FIT.cov_params().values
LG = {}
for g in G6:
    sel = (cells.geno == g.split()[0]) & (cells.age == g.split()[1])
    LG[g] = XC[(sel & (cells.day == "d2")).values][0] - XC[(sel & (cells.day == "d1")).values][0]
GEE = {}
for a, b in (("WT young", "Het young"), ("WT young", "Hom young"), ("WT old", "Het old"), ("WT old", "Hom old")):
    L = LG[b] - LG[a]
    e, s_ = L @ B, np.sqrt(L @ COV @ L)
    GEE[b] = dict(ratio=np.exp(e), lo=np.exp(e - 1.96 * s_), hi=np.exp(e + 1.96 * s_), p=2 * st.norm.sf(abs(e / s_)))
INT = {}
for t in FIT.params.index:
    if t.count(":") == 2:
        INT["Het" if "Het" in t else "Hom"] = dict(rr=float(np.exp(FIT.params[t])), p=float(FIT.pvalues[t]))
PAIR_P = {g: yuen("WT " + g.split()[1], g) for g in G6 if not g.startswith("WT")}


def plab(p):
    return "P < 0.001" if p < 0.001 else ("P = %.3f" % p if p < 0.1 else "P = %.2f" % p)


def stars(p):
    return "ns" if p >= 0.05 else ("***" if p < 0.001 else ("**" if p < 0.01 else "*"))


def sig(p):
    return "ns" if p >= 0.05 else "%s (%s)" % (stars(p), plab(p))


# ------------------------------------------------------------------ figure
FW, FH = 24.0, 15.2
fig = plt.figure(figsize=(FW, FH))


def ax_at(x, y, w, h, **kw):
    return fig.add_axes([x / FW, 1 - (y + h) / FH, w / FW, h / FH], **kw)


def heading(x, y, s, title):
    fig.text(x / FW, 1 - y / FH, s, fontsize=30, weight="bold", va="baseline", ha="left")
    fig.text((x + 0.42) / FW, 1 - y / FH, title, fontsize=20, va="baseline", ha="left")


# ---------- a: representative paths
REPS = {g: (VALS[g] - VALS[g].median()).abs().idxmin() for g in G6}
PATH = T.groupby("mouse").path_m.mean()
for g in ("Het young",):          # typical on both improvement and how much the mouse moves
    ms = VALS[g].index
    rk = (VALS[g] - VALS[g].median()).abs().rank() + (PATH[ms] - PATH[ms].median()).abs().rank()
    REPS[g] = rk.idxmin()
LABEL = {g: "" for g in G6}
heading(0.25, 0.55, "a", "Typical WT, Het and young Hom mice avoid the zone by day 2; old Hom do not")
kx, ky = 0.45, 7.35
kax = ax_at(kx, ky - 0.27, 0.34, 0.34)
kax.add_patch(Wedge((0, 0), 1, 15, 75, color=F.ZONE, alpha=0.3, lw=0))
kax.set_xlim(-0.2, 1.0)
kax.set_ylim(-0.2, 1.0)
kax.set_aspect("equal")
kax.axis("off")
fig.text((kx + 0.4) / FW, 1 - ky / FH, "shock zone (fixed in the room; the floor turns counter-clockwise)", fontsize=FS - 3,
         va="baseline", color=SOFT)
fig.text((kx + 7.75) / FW, 1 - ky / FH, "\u00d7", color=F.ZONE, fontsize=24, va="baseline", weight="bold")
fig.text((kx + 8.05) / FW, 1 - ky / FH, "shock", fontsize=FS - 3, va="baseline", color=SOFT)
AW = 2.0
for i, g in enumerate(G6):
    m = REPS[g]
    d = T[T.mouse == m]
    best = {dd: d[d.day == dd].sort_values(["spr", "session"]).iloc[0] for dd in ("d1", "d2")}
    col = GC[g.split()[0]]
    r_, c_ = divmod(i, 3)
    x0, y0 = 0.35 + c_ * 4.35, 1.25 + r_ * 3.2
    fig.text((x0 + AW + 0.05) / FW, 1 - (y0 - 0.12) / FH, "%s %s, mouse %s%s" % (g.split()[0], g.split()[1], m, LABEL[g]),
             ha="center", va="baseline", fontsize=FS - 1, color=col)
    for j, dd in enumerate(("d1", "d2")):
        ax = ax_at(x0 + j * (AW + 0.1), y0, AW, AW)
        ax.add_patch(Wedge((0, 0), 41, 15, 75, color=F.ZONE, alpha=0.15, lw=0, zorder=0))
        ax.add_patch(Circle((0, 0), 41, fill=False, ec=LINE, lw=1.4))
        s = int(best[dd].session)
        key = "%s_s%d" % (m, s)
        xs, ys = TRK[key + "|x"], TRK[key + "|y"]
        ax.plot(xs, ys, color=col, lw=0.6, alpha=0.85, rasterized=True)
        sh = TRK[key + "|shocks"]
        sh = sh[sh < len(xs)]
        ax.scatter(xs[sh], ys[sh], marker="x", s=60, color=F.ZONE, lw=2.4, zorder=4)
        ax.set_xlim(-43, 43)
        ax.set_ylim(-43, 43)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.text(0, -47, "Day %s (s%d): %.2f/turn" % (dd[1], s, best[dd].spr), ha="center", va="top", fontsize=FS - 3.5)

# ---------- b: learning curves, two-session blocks, Het and Hom each against WT
heading(13.75, 0.55, "b", "Old Hom are the only group whose shocks per turn stay flat")
blk = T.assign(block=((T.session - 1) // 2)).groupby(["mouse", "block"]).spr.mean().reset_index()
blk["grp"] = blk.mouse.map(GRP)
xs_b = np.arange(8) * 2 + 1.5
BW, BH, BX0, BY0 = 4.45, 2.55, 14.65, 1.35
ymax = 0
curves = {}
for g in G6:
    d = blk[blk.grp == g].groupby("block").spr.agg(["mean", "sem"]).reindex(range(8))
    curves[g] = d
    ymax = max(ymax, float((d["mean"] + d["sem"]).max()))
for r_, age in enumerate(("young", "old")):
    for c_, gen in enumerate(("Het", "Hom")):
        ax = ax_at(BX0 + c_ * (BW + 0.35), BY0 + r_ * (BH + 0.62), BW, BH)
        for g, z in (("WT " + age, 2), ("%s %s" % (gen, age), 3)):
            d = curves[g]
            col = GC[g.split()[0]]
            ax.errorbar(xs_b, d["mean"], yerr=d["sem"], color=col, lw=2.6, marker="o", ms=8, mec="white", mew=1.2,
                        elinewidth=1.6, capsize=0, zorder=z, label="%s (n = %d)" % (g.split()[0], NG[g]))
        ax.axvline(8.5, color=LINE, lw=1.2, ls=(0, (4, 3)), zorder=0)
        ax.set_xlim(0.3, 16.7)
        ax.set_ylim(0, ymax * 1.32)
        ax.set_xticks([1, 4, 8, 9, 12, 16])
        if r_ == 1:
            ax.set_xlabel("Session")
        else:
            ax.set_xticklabels([])
        if c_ == 0:
            ax.set_ylabel("Shocks per turn")
        else:
            ax.set_yticklabels([])
        ax.legend(frameon=False, loc="upper right", handlelength=1.2, borderaxespad=0.1)
        ax.text(0.02, 0.97, "%s %s vs WT" % (age.capitalize(), gen), transform=ax.transAxes, fontsize=FS - 1, weight="bold",
                va="top", color=GC[gen])
        if r_ == 0:
            ax.text(4.5, 1.02, "day 1", ha="center", va="bottom", fontsize=FS - 4, color=SOFT, transform=ax.get_xaxis_transform())
            ax.text(12.5, 1.02, "day 2", ha="center", va="bottom", fontsize=FS - 4, color=SOFT, transform=ax.get_xaxis_transform())

# ---------- c: GEE forest
heading(0.25, 8.6, "c", "GEE: only old Hom improve less than WT")
ax = ax_at(2.0, 9.3, 4.6, 4.95)
rows = [("Het young", "Het\nyoung"), ("Hom young", "Hom\nyoung"), ("Het old", "Het\nold"), ("Hom old", "Hom\nold")]
ypos = [3.4, 2.4, 1.0, 0.0]
for (g, lab), yy in zip(rows, ypos):
    r = GEE[g]
    col = GC[g.split()[0]]
    ax.plot([r["lo"], r["hi"]], [yy, yy], color=col, lw=3.2, solid_capstyle="butt")
    ax.scatter(r["ratio"], yy, s=170, color=col, edgecolor=INK, lw=1.6, zorder=3)
    ax.text(1.03, yy, "%s (%s)" % (stars(r["p"]), plab(r["p"])), transform=ax.get_yaxis_transform(), va="center",
            fontsize=FS - 3)
ax.axvline(1, color=LINE, lw=1.4, ls=(0, (4, 3)), zorder=0)
ax.axhline(1.7, color="#e3e6ea", lw=1.2, zorder=0)
ax.set_xscale("log")
ax.set_xlim(0.3, 5)
ax.set_xticks([0.5, 1, 2, 4])
ax.set_xticklabels(["0.5", "1", "2", "4"])
ax.minorticks_off()
ax.set_yticks(ypos)
ax.set_yticklabels([lab for _g, lab in rows])
ax.tick_params(axis="y", length=0)
ax.spines["left"].set_visible(False)
ax.set_ylim(-0.6, 4.35)
ax.set_xlabel("Day 2 / day 1, relative to WT (rate ratio, 95% CI)")
ax.text(0.95, 4.2, "\u2190 improves more", ha="right", va="center", fontsize=FS - 4, color=SOFT)
ax.text(1.05, 4.2, "improves less \u2192", ha="left", va="center", fontsize=FS - 4, color=SOFT)
ax.text(0.0, 1.02, "Genotype \u00d7 age \u00d7 day:  Hom %s (%s)  \u00b7  Het %s (%s)" % (
    stars(INT["Hom"]["p"]), plab(INT["Hom"]["p"]), stars(INT["Het"]["p"]), plab(INT["Het"]["p"])),
    transform=ax.transAxes, fontsize=FS - 3, va="bottom")

# ---------- d: each mouse's day-1-to-day-2 change
heading(9.15, 8.6, "d", "Only old Hom fail to improve from day 1 to day 2; no other group differs from WT")
ax = ax_at(10.35, 9.3, 13.35, 4.95)
xpos = {"WT young": 0, "Het young": 1, "Hom young": 2, "WT old": 3.7, "Het old": 4.7, "Hom old": 5.7}
rs = np.random.RandomState(4)
for g in G6:
    col = GC[g.split()[0]]
    x = xpos[g]
    v = VALS[g].values
    ax.scatter(x - 0.13 + (rs.rand(v.size) - 0.5) * 0.3, v, s=95, color=col, edgecolor="white", lw=1.0, alpha=0.95, zorder=3)
    tm, dvar, h = trim_stats(v)
    ci = st.t.ppf(0.975, h - 1) * np.sqrt(dvar)
    ax.errorbar(x + 0.24, tm, yerr=ci, fmt="o", ms=13, color=col, mec=INK, mew=1.8, ecolor=INK, elinewidth=2.6, capsize=8,
                capthick=2.4, zorder=6)
ax.axhline(0, color=LINE, lw=1.4, zorder=0)
top = float(IMP.max())


def bracket(x1, x2, y, text, h=0.07, fs=FS - 2):
    ax.plot([x1, x1, x2, x2], [y - h, y, y, y - h], color=INK, lw=1.7, clip_on=False)
    ax.text((x1 + x2) / 2, y + 0.035, text, ha="center", va="bottom", fontsize=fs)


y1 = top + 0.22
step = 0.42
bracket(0, 1, y1, sig(PAIR_P["Het young"]), fs=FS - 4)
bracket(3.7, 4.7, y1, sig(PAIR_P["Het old"]), fs=FS - 4)
bracket(0, 2, y1 + step, sig(PAIR_P["Hom young"]), fs=FS - 4)
bracket(3.7, 5.7, y1 + step, sig(PAIR_P["Hom old"]), fs=FS - 4)
bracket(1, 4.7, y1 + 2 * step + 0.05, "Het \u00d7 age, GEE: " + sig(INT["Het"]["p"]), fs=FS - 3)
bracket(2, 5.7, y1 + 3 * step + 0.1, "Hom \u00d7 age, GEE: " + sig(INT["Hom"]["p"]), fs=FS - 2)
ax.set_ylim(min(-1.9, float(IMP.min()) - 0.15), y1 + 4 * step + 0.2)
ax.set_xlim(-0.55, 6.25)
ax.set_xticks([xpos[g] for g in G6])
ax.set_xticklabels(["%s\n(n = %d)" % (g.split()[0], NG[g]) for g in G6])
ax.tick_params(axis="x", length=0)
for lab, xc in (("Young", 1.0), ("Old", 4.7)):
    ax.text(xc, -0.175, lab, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=FS + 1, weight="bold")
    ax.plot([xc - 1.15, xc + 1.15], [-0.16, -0.16], transform=ax.get_xaxis_transform(), color=LINE, lw=1.2, clip_on=False)
ax.set_ylabel("Change in shocks per turn\n(day 2 \u2212 day 1; < 0 = improved)")

out_png = os.path.join(OUTD, "KCNT1_AA_poster_figure.png")
out_pdf = os.path.join(OUTD, "KCNT1_AA_poster_figure.pdf")
for p_, dpi in ((out_png, 300), (out_pdf, 300)):
    try:
        fig.savefig(p_, dpi=dpi, bbox_inches="tight", pad_inches=0.12)
    except OSError:
        fig.savefig(p_.replace("poster_figure", "poster_figure_v2"), dpi=dpi, bbox_inches="tight", pad_inches=0.12)
pd.DataFrame([dict(comparison="%s vs WT %s" % (g, g.split()[1]), **v) for g, v in GEE.items()]).to_csv(
    os.path.join(OUTD, "gee_ratio_of_ratios.csv"), index=False)
pd.DataFrame([dict(group=g, n=NG[g], trimmed_mean=trim_stats(VALS[g].values)[0], mean=VALS[g].mean(),
                   yuen_p_vs_WT=PAIR_P.get(g, np.nan)) for g in G6]).to_csv(os.path.join(OUTD, "panel_d_values.csv"), index=False)
FBR = smf.gee(FORM, "mouse", T, family=sm.families.Poisson(), cov_struct=sm.cov_struct.Exchangeable(),
              offset=T.logt).fit(cov_type="bias_reduced")
print("bias-reduced 3-way P:", {t: round(float(p), 4) for t, p in FBR.pvalues.items() if t.count(":") == 2})
print("reps", REPS)
print("pairs", {k: round(v, 4) for k, v in PAIR_P.items()})
print("gee", {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in GEE.items()})
print("int", INT, "n", NG)
for g in G6:
    d = T[T.mouse == REPS[g]]
    print(g, REPS[g], {dd: (int(d[d.day == dd].sort_values(["spr", "session"]).iloc[0].session),
                            round(float(d[d.day == dd].spr.min()), 2)) for dd in ("d1", "d2")})
