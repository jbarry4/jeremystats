"""Panel A, behavior, rebuilt in the poster style (v5). Same mice, sessions and statistics as the v2 behavior figure
(all 56 mice), redrawn at its print size (15.0 x 9.0 in).
v8: less white space (larger arenas, the learning curves pulled in, c and d raised, d's labels inside the figure) and c's
"Young"/"Old" group names back in view (v5-v7 cut them off at the figure's bottom edge).
usage: python fig_behavior.py OUT.png"""
import os
import sys
import warnings

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf
from matplotlib.patches import Circle, Wedge
from scipy import stats as st

import style as S

warnings.filterwarnings("ignore")
ROOT = r"C:\Users\info\Desktop\JeremyStats"
LF = os.path.join(ROOT, "_Jarvis", "Lab Figures")
_AR = os.path.join(LF, "KCNT1 POSTER", "Poster Resources", "Behavior", "Archive")   # (v11: where the tables moved on 11-27)
if not os.path.isdir(os.path.join(LF, "KCNT1_AA_Story_Menu_112326")) and os.path.isdir(os.path.join(_AR, "KCNT1_AA_Story_Menu_112326")):
    LF = _AR
ND = os.path.join(ROOT, "KCNT1 Active Avoidance", "New Data", "active_avoidance_data")
G6 = ["WT young", "Het young", "Hom young", "WT old", "Het old", "Hom old"]
COOKED = {("527", 2), ("598", 6), ("1663", 3), ("1663", 16)}
OUTLIERS = {"413", "417", "1665", "1667"}
ZONE = "#D62728"

# ----------------------------------------------------------------------------- data and statistics (as v2)
PS = pd.read_csv(os.path.join(LF, "KCNT1_AA_Story_Menu_112326", "tables", "per_session_values.csv.gz"), dtype={"mouse": str})
FSB = pd.read_csv(os.path.join(LF, "KCNT1_AA_Stage_Speed_Check_112426", "tables", "floor_speed_by_session.csv"),
                  dtype={"mouse": str}).set_index("key")
D = PS[PS.use].copy()
D["om"] = (D.mouse + "_s" + D.session.astype(int).astype(str)).map(FSB.half_hour_reading_true_center)
D["turns"] = D.om * D.duration_s / 360.0
D["spr"] = D.shocks / D.turns
D["geno"], D["age"] = D.yh, D.age_group
T = D[(D.session >= 1) & (D.session <= 16) & D.turns.notna() & (D.turns > 0)]
T = T[~T.apply(lambda r: (r.mouse, int(r.session)) in COOKED, axis=1)].copy()
T["grp"] = T.geno + " " + T.age
T["day"] = np.where(T.session <= 8, "d1", "d2")
T["logt"] = np.log(T.turns)
GRP = T.groupby("mouse").grp.first()
D1 = T[T.day == "d1"].groupby("mouse").spr.mean()
D2 = T[T.day == "d2"].groupby("mouse").spr.mean()
IMP = (D2 - D1).dropna()
VALS = {g: IMP[GRP[IMP.index] == g] for g in G6}
NG = {g: v.size for g, v in VALS.items()}

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
INT = {("Het" if "Het" in t else "Hom"): float(FIT.pvalues[t]) for t in FIT.params.index if t.count(":") == 2}
PAIR_P = {g: st.ttest_ind(VALS["WT " + g.split()[1]].values, VALS[g].values, equal_var=False, trim=0.2).pvalue
          for g in G6 if not g.startswith("WT")}


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


def plab(p):
    return "P < 0.001" if p < 0.001 else ("P = %.3f" % p if p < 0.1 else "P = %.2f" % p)


def stars(p):
    return "n.s." if p >= 0.05 else ("***" if p < 0.001 else ("**" if p < 0.01 else "*"))


def read_dat(path):
    hdr, n_head = {}, 0
    with open(path, encoding="latin-1") as f:
        for n_head, line in enumerate(f, 1):
            s = line.strip()
            if s.startswith("%") and "(" in s:
                hdr[s[1:s.index("(")].strip().replace(".0", "")] = s[s.index("(") + 1:s.rindex(")")].strip()
            if s.startswith("%%END_HEADER"):
                break
    d = pd.read_csv(path, sep=r"\s+", skiprows=n_head, header=None, usecols=range(8),
                    names=["frame", "t_ms", "x", "y", "sectors", "state", "current", "motor"], engine="c",
                    encoding="latin-1", comment="%")
    return hdr, d.apply(pd.to_numeric, errors="coerce").dropna(subset=["t_ms"]).reset_index(drop=True)


def track(path):
    h, d = read_dat(path)
    px = float(h["TrackerResolution_PixPerCM"])
    cx, cy = map(float, h["ArenaCenterXY"].split())
    raw = d.state.values.astype(int)
    lost = raw == 5
    x = pd.Series(np.where(lost, np.nan, d.x.values)).ffill().bfill().values
    y = pd.Series(np.where(lost, np.nan, d.y.values)).ffill().bfill().values
    X, Y = (x - cx) / px, -(y - cy) / px
    stt = pd.Series(np.where(lost, np.nan, raw)).ffill().fillna(0).astype(int).values
    on = np.flatnonzero((stt == 2) & (np.r_[-1, stt[:-1]] != 2))
    return X[::2], Y[::2], on // 2


DYB = 0.14                                     # v10: the bottom row 0.14 in lower, for the divider between the rows


def main(out):
    fig = S.figure(15.0, 9.0 + DYB)
    col = lambda g: S.GENO[g.split()[0]]  # noqa: E731

    # ------------------------------------------------------------------ a  paths
    S.text_at(fig, 0.0, 0.0, "a", fontsize=S.TITLE + 2, fontweight="bold")
    S.title(fig, 0.3, 0.02, "A typical mouse per group, best session of each day")
    REPS = {g: (VALS[g] - VALS[g].median()).abs().idxmin() for g in G6}
    PATH = T.groupby("mouse").path_m.mean()
    ms = VALS["Het young"].index
    rk = (VALS["Het young"] - VALS["Het young"].median()).abs().rank() + (PATH[ms] - PATH[ms].median()).abs().rank()
    REPS["Het young"] = rk.idxmin()
    R = 1.05
    x_l, y_t = 0.62, 0.78
    PX, PJ, PR = 2.27, 1.1, 1.96                 # pitch of the genotype pairs, of the two days, of the two ages
    for c_, gen in enumerate(("WT", "Het", "Hom")):
        S.text_at(fig, x_l + c_ * PX + (PJ + R) / 2, y_t - 0.02, gen, fontsize=S.LABEL, fontweight="bold", color=S.GENO[gen], ha="center")
    for r_, age in enumerate(("young", "old")):
        S.text_at(fig, 0.02, y_t + 0.32 + r_ * PR + R / 2, age.capitalize(), fontsize=S.LABEL, fontweight="bold",
                  rotation=90, va="center", ha="left")
        for c_, gen in enumerate(("WT", "Het", "Hom")):
            g = "%s %s" % (gen, age)
            m = REPS[g]
            d = T[T.mouse == m]
            best = {dd: d[d.day == dd].sort_values(["spr", "session"]).iloc[0] for dd in ("d1", "d2")}
            for j, dd in enumerate(("d1", "d2")):
                ax = S.ax_at(fig, x_l + c_ * PX + j * PJ, y_t + 0.32 + r_ * PR, R, R)
                ax.add_patch(Wedge((0, 0), 41, 15, 75, color=ZONE, alpha=0.13, lw=0, zorder=0))
                ax.add_patch(Circle((0, 0), 41, fill=False, ec=S.FAINT, lw=1.0))
                xs, ys, sh = track(os.path.join(ND, best[dd].folder, best[dd].file))
                ax.plot(xs, ys, color=col(g), lw=0.35, alpha=0.9, rasterized=True)
                sh = sh[sh < len(xs)]
                ax.scatter(xs[sh], ys[sh], marker="x", s=22, color=ZONE, lw=1.4, zorder=4)
                ax.set_xlim(-43, 43)
                ax.set_ylim(-43, 43)
                ax.set_aspect("equal")
                S.bare(ax)
                if r_ == 0 and c_ == 0:
                    ax.set_title("Day %s" % dd[1], fontsize=S.NOTE, fontweight="normal", color=S.SOFT, pad=2)
            S.text_at(fig, x_l + c_ * PX + (PJ + R) / 2, y_t + 0.32 + r_ * PR + R + 0.05,
                      "%.2f \u2192 %.2f" % (best["d1"].spr, best["d2"].spr), fontsize=S.SMALL, color=S.SOFT, ha="center")
    S.text_at(fig, x_l, y_t + 0.32 + PR + R + 0.36, "shocks per turn, day 1 \u2192 day 2   \u00b7   \u00d7 shock   \u00b7   red wedge, shock zone",
              fontsize=S.SMALL, color=S.SOFT)

    # ------------------------------------------------------------------ b  learning curves (change from own day 1)
    S.text_at(fig, 7.42, 0.0, "b", fontsize=S.TITLE + 2, fontweight="bold")
    S.title(fig, 7.72, 0.02, "Shocks per turn, each mouse against its own day 1")
    T["block"] = (T.session - 1) // 2
    BLK = T.groupby(["mouse", "block"]).spr.mean().unstack()
    CHG = BLK.sub(D1, axis=0)
    xs_b = np.arange(8) * 2 + 1.5
    curves = {g: (CHG.loc[GRP[GRP == g].index].mean(), CHG.loc[GRP[GRP == g].index].sem()) for g in G6}
    lo = min(float((m - s).min()) for m, s in curves.values())
    hi = max(float((m + s).max()) for m, s in curves.values())
    bw, bh = 3.37, 1.5
    for r_, age in enumerate(("young", "old")):
        for c_, gen in enumerate(("Het", "Hom")):
            ax = S.ax_at(fig, 8.15 + c_ * (bw + 0.15), 0.55 + r_ * (bh + 0.58), bw, bh)
            ax.axhline(0, color=S.FAINT, lw=1.0, zorder=0)
            ax.axvspan(8.5, 16.7, color=S.GRID, lw=0, zorder=-1)
            for g, z in (("WT " + age, 2), ("%s %s" % (gen, age), 3)):
                m, s = curves[g]
                ax.fill_between(xs_b, m - s, m + s, color=col(g), alpha=0.18, lw=0, zorder=z)
                ax.plot(xs_b, m, color=col(g), lw=2.2, marker="o", ms=4.5, mec="white", mew=0.8, zorder=z + 0.5)
            ax.set_xlim(0.3, 16.7)
            ax.set_ylim(lo - 0.1, hi + 0.25)
            ax.set_yticks([-1, 0, 1])
            ax.set_xticks([1, 8, 9, 16])
            if r_ == 0:
                ax.set_xticklabels([])
            else:
                ax.set_xlabel("Session")
            if c_ == 0:
                ax.set_ylabel("\u0394 shocks/turn", labelpad=2)
            else:
                ax.set_yticklabels([])
            ax.text(0.03, 0.96, "%s %s" % (age.capitalize(), gen), transform=ax.transAxes, fontsize=S.NOTE + 1, fontweight="bold",
                    color=S.GENO[gen], va="top")
            ax.text(0.97, 0.96, "%s %d" % (gen, NG["%s %s" % (gen, age)]), transform=ax.transAxes, fontsize=S.SMALL + 0.5,
                    color=S.GENO[gen], va="top", ha="right", fontweight="bold")
            ax.text(0.97, 0.78, "WT %d" % NG["WT " + age], transform=ax.transAxes, fontsize=S.SMALL + 0.5, color=S.GENO["WT"],
                    va="top", ha="right", fontweight="bold")
            if r_ == 0:
                ax.text(4.5, 1.02, "day 1", transform=ax.get_xaxis_transform(), fontsize=S.SMALL, color=S.SOFT, ha="center", va="bottom")
                ax.text(12.5, 1.02, "day 2", transform=ax.get_xaxis_transform(), fontsize=S.SMALL, color=S.SOFT, ha="center", va="bottom")

    # ------------------------------------------------------------------ c  each mouse's change
    S.text_at(fig, 0.0, 4.78 + DYB, "c", fontsize=S.TITLE + 2, fontweight="bold")
    S.title(fig, 0.3, 4.8 + DYB, "Change from day 1 to day 2, each mouse")
    ax = S.ax_at(fig, 0.85, 5.48 + DYB, 8.75, 2.7)
    xpos = {"WT young": 0, "Het young": 1, "Hom young": 2, "WT old": 3.6, "Het old": 4.6, "Hom old": 5.6}
    rs = np.random.RandomState(4)
    for g in G6:
        v = VALS[g]
        x = xpos[g]
        jit = (rs.rand(v.size) - 0.5) * 0.32           # v9: every mouse alike (the user: outliers kept, no note needed)
        ax.scatter(x - 0.12 + jit, v.values, s=34, color=col(g), alpha=0.9, zorder=3, edgecolors="white", linewidths=0.6)
        tm, dvar, h = trim_stats(v.values)
        ci = st.t.ppf(0.975, h - 1) * np.sqrt(dvar)
        ax.errorbar(x + 0.26, tm, yerr=ci, fmt="o", ms=8, color=col(g), mec=S.INK, mew=1.2, ecolor=S.INK, elinewidth=1.6,
                    capsize=5, capthick=1.6, zorder=6)
    ax.axhline(0, color=S.FAINT, lw=1.0, zorder=0)
    top = float(IMP.max())

    def bracket(x1, x2, y, txt, fs=S.NOTE):
        ax.plot([x1, x1, x2, x2], [y - 0.07, y, y, y - 0.07], color=S.INK, lw=1.1, clip_on=False)
        ax.text((x1 + x2) / 2, y + 0.04, txt, ha="center", va="bottom", fontsize=fs)

    y1 = top + 0.18
    bracket(3.6, 5.6, y1, "%s  %s" % (stars(PAIR_P["Hom old"]), plab(PAIR_P["Hom old"])))
    bracket(2, 5.6, y1 + 0.5, "Hom \u00d7 age (GEE)  %s  %s" % (stars(INT["Hom"]), plab(INT["Hom"])))
    ax.set_ylim(float(IMP.min()) - 0.2, y1 + 0.85)
    ax.set_xlim(-0.55, 6.15)
    ax.set_xticks([xpos[g] for g in G6])
    ax.set_xticklabels(["%s\n%d" % (g.split()[0], NG[g]) for g in G6], fontsize=S.TICK)
    ax.tick_params(axis="x", length=0, pad=4)
    for lab, xc in (("Young", 1.0), ("Old", 4.6)):
        ax.text(xc, -0.205, lab, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=S.LABEL, fontweight="bold")
    ax.set_ylabel("\u0394 shocks per turn\n(day 2 \u2212 day 1)")
    S.text_at(fig, 0.3, 5.14 + DYB, "dots, mice  ·  bars, 20% trimmed mean ± 95% CI  ·  "
              "every other group vs its WT: n.s.", fontsize=S.SMALL, color=S.SOFT)

    # ------------------------------------------------------------------ d  GEE forest
    S.text_at(fig, 10.05, 4.78 + DYB, "d", fontsize=S.TITLE + 2, fontweight="bold")
    S.title(fig, 10.35, 4.8 + DYB, "Day-2/day-1 ratio vs WT (GEE)")
    ax = S.ax_at(fig, 11.25, 5.48 + DYB, 2.55, 2.7)
    rows = [("Het young", 3.4), ("Hom young", 2.5), ("Het old", 1.0), ("Hom old", 0.1)]
    for g, yy in rows:
        r = GEE[g]
        ax.plot([r["lo"], r["hi"]], [yy, yy], color=col(g), lw=3.0, solid_capstyle="round")
        ax.scatter(r["ratio"], yy, s=70, color=col(g), edgecolor=S.INK, lw=1.1, zorder=3)
        ax.text(1.04, yy, ("%s %s" % (stars(r["p"]), plab(r["p"]))) if r["p"] < 0.05 else "n.s.", transform=ax.get_yaxis_transform(), va="center",
                fontsize=S.NOTE, fontweight="bold" if r["p"] < 0.05 else "normal", color=S.INK if r["p"] < 0.05 else S.SOFT)
    ax.axvline(1, color=S.FAINT, lw=1.1, ls=(0, (3, 3)), zorder=0)
    ax.axhline(1.75, color=S.GRID, lw=1.0, zorder=0)
    ax.set_xscale("log")
    ax.set_xlim(0.3, 5)
    ax.set_xticks([0.5, 1, 2, 4])
    ax.set_xticklabels(["0.5", "1", "2", "4"])
    ax.minorticks_off()
    ax.set_yticks([y for _g, y in rows])
    ax.set_yticklabels(["%s %s" % (g.split()[0], g.split()[1]) for g, _y in rows])
    for lab in ax.get_yticklabels():
        lab.set_color(S.GENO[lab.get_text().split()[0]])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.5, 4.0)
    ax.set_xlabel("Rate ratio (95% CI)")
    ax.text(0.95, 3.85, "\u2190 improves more", ha="right", va="center", fontsize=S.SMALL, color=S.SOFT)
    ax.text(1.05, 3.85, "improves less \u2192", ha="left", va="center", fontsize=S.SMALL, color=S.SOFT)
    # v10 (the user: "shading or dividers ... where each figure starts and ends ... not noisy"): hairlines between the rows
    # and between c and d, in the poster's divider grey
    dv = S.ax_at(fig, 0, 0, 15.0, 9.0 + DYB, zorder=-10)
    dv.set_xlim(0, 15.0); dv.set_ylim(9.0 + DYB, 0); dv.axis("off")
    dv.plot([0.0, 15.0], [4.64 + DYB / 2, 4.64 + DYB / 2], c="#D5DBE2", lw=1.25, solid_capstyle="butt")
    dv.plot([9.86, 9.86], [4.78 + DYB, 9.0 + DYB], c="#D5DBE2", lw=1.25, solid_capstyle="butt")
    S.save(fig, out)
    print("saved", out, {k: round(v["p"], 4) for k, v in GEE.items()}, INT, NG)


if __name__ == "__main__":
    main(sys.argv[1])
