"""Poster figure v2 (2026-11-24; 24 in wide, Nature style), from round 2 (KCNT1_AA_Poster_Figure_112426/poster_fig2.py).
Writes two versions: without the four robust-rule outlier mice (as round 2; 52 mice) and with every mouse (56).
Changes from round 2:
  b    each mouse's shocks per turn as its change from its own day-1 mean. Round 2 plotted group means of the absolute
       values; old Hom sat below old WT there because they started lower, which hid that they do not improve.
  c/d  the per-mouse change plot (was d) and the GEE forest (was c) swap places; letters follow reading order, so
       c = each mouse's change and d = the GEE forest.
  In the version with every mouse, the four flagged mice are ringed in c (MARK_FLAGGED).
The four sessions with documented shock faults ('cooked') are excluded from both versions.
Self-contained: the session table is rebuilt from the story menu's per_session_values (tracker counts) and the stage
speed check's refined floor reading (each session's half-hour reading about the day's true center), as cr.pkl built
it; the paths in a are read straight from the tracker .dat files."""
import logging
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
from matplotlib.patches import Circle, Wedge  # noqa: E402
from scipy import stats as st  # noqa: E402

warnings.filterwarnings("ignore")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # Helvetica falls back to Arial on Windows
HERE = os.path.dirname(os.path.abspath(__file__))
LF = os.environ.get("LAB_FIGURES") or os.path.dirname(HERE)            # ..._Jarvis/Lab Figures
ROOT = os.path.dirname(os.path.dirname(LF))                            # ...JeremyStats
ND = os.path.join(ROOT, "KCNT1 Active Avoidance", "New Data", "active_avoidance_data")
OUTD = os.environ.get("POSTER_OUT") or HERE
FS = 18
plt.rcParams.update({"font.family": ["Helvetica", "Arial"], "font.size": FS, "axes.labelsize": FS, "xtick.labelsize": FS - 2,
                     "ytick.labelsize": FS - 2, "axes.linewidth": 1.4, "xtick.major.width": 1.4, "ytick.major.width": 1.4,
                     "xtick.major.size": 6, "ytick.major.size": 6, "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "legend.fontsize": FS - 3, "axes.edgecolor": "#1d2433", "xtick.color": "#1d2433",
                     "ytick.color": "#1d2433", "text.color": "#1d2433", "axes.labelcolor": "#1d2433"})
INK, SOFT, LINE = "#1d2433", "#5a6273", "#9aa1ad"
GC = {"WT": "#8c8c8c", "Het": "#e08a2c", "Hom": "#7b2d8e"}
ZONE = "#d62728"
G6 = ["WT young", "Het young", "Hom young", "WT old", "Het old", "Hom old"]
COOKED = {("527", 2), ("598", 6), ("1663", 3), ("1663", 16)}
OUTLIERS = {"413", "417", "1665", "1667"}   # robust-rule outlier mice (old Hom 413, 417; young WT 1665, 1667)
OUTLIER_TEXT = "old Hom 413 and 417; young WT 1665 and 1667"
MARK_FLAGGED = True                         # ring the flagged mice in c when they are included

# ------------------------------------------------------------------ sessions (all mice)
PS = pd.read_csv(os.path.join(LF, "KCNT1_AA_Story_Menu_112326", "tables", "per_session_values.csv.gz"), dtype={"mouse": str})
FSB = pd.read_csv(os.path.join(LF, "KCNT1_AA_Stage_Speed_Check_112426", "tables", "floor_speed_by_session.csv"),
                  dtype={"mouse": str}).set_index("key")
S = PS[PS.use].copy()
S["om"] = (S.mouse + "_s" + S.session.astype(int).astype(str)).map(FSB.half_hour_reading_true_center)   # cr.pkl 'local1'
S["turns"] = S.om * S.duration_s / 360.0
S["spr"] = S.shocks / S.turns
S["geno"], S["age"] = S.yh, S.age_group


# ------------------------------------------------------------------ helpers
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
    return "ns" if p >= 0.05 else ("***" if p < 0.001 else ("**" if p < 0.01 else "*"))


def sig(p):
    return "ns" if p >= 0.05 else "%s (%s)" % (stars(p), plab(p))


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


_TRACKS = {}


def track(path):
    """Positions (cm from the arena center, y up, every 2nd frame) and shock onsets, as a1_extract.session:
    lost frames (state 5) carry the last tracked position and state forward."""
    if path not in _TRACKS:
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
        _TRACKS[path] = (X[::2], Y[::2], on // 2, on.size)
    return _TRACKS[path]


# ------------------------------------------------------------------ one version of the figure
def make(tag, drop):
    T = S[(S.session >= 1) & (S.session <= 16) & S.turns.notna() & (S.turns > 0)]
    T = T[~T.apply(lambda r: (r.mouse, int(r.session)) in COOKED or r.mouse in drop, axis=1)].copy()
    T["grp"] = T.geno + " " + T.age
    T["day"] = np.where(T.session <= 8, "d1", "d2")
    T["logt"] = np.log(T.turns)
    GRP = T.groupby("mouse").grp.first()
    D1 = T[T.day == "d1"].groupby("mouse").spr.mean()
    D2 = T[T.day == "d2"].groupby("mouse").spr.mean()
    IMP = (D2 - D1).dropna()
    VALS = {g: IMP[GRP[IMP.index] == g] for g in G6}
    NG = {g: v.size for g, v in VALS.items()}
    flagged = OUTLIERS - set(drop)

    # ---- statistics (as round 2)
    FORM = "shocks ~ C(geno, Treatment('WT')) * C(age, Treatment('old')) * C(day, Treatment('d2'))"
    FIT = smf.gee(FORM, "mouse", T, family=sm.families.Poisson(), cov_struct=sm.cov_struct.Exchangeable(),
                  offset=T.logt).fit()
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
    PAIR_P = {g: st.ttest_ind(VALS["WT " + g.split()[1]].values, VALS[g].values, equal_var=False, trim=0.2).pvalue
              for g in G6 if not g.startswith("WT")}
    ABS = {}                         # absolute levels, old Hom vs old WT (legend: b no longer shows them)
    for dname, v in (("day 1", D1), ("day 2", D2)):
        w_, h_ = v[GRP[v.index] == "WT old"].values, v[GRP[v.index] == "Hom old"].values
        ABS[dname] = dict(WT=w_.mean(), Hom=h_.mean(), p=st.ttest_ind(w_, h_, equal_var=False).pvalue)
    # the panel headings are claims: stop if this version does not support them
    others_c = [p for g, p in PAIR_P.items() if g != "Hom old"]
    others_d = [r["p"] for g, r in GEE.items() if g != "Hom old"]
    if not (PAIR_P["Hom old"] < 0.05 and VALS["Hom old"].mean() > VALS["WT old"].mean() and min(others_c) >= 0.05
            and GEE["Hom old"]["p"] < 0.05 and GEE["Hom old"]["ratio"] > 1 and min(others_d) >= 0.05):
        raise SystemExit("[%s] the panel headings no longer match the statistics; rewrite them first" % tag)

    fig = plt.figure(figsize=(24.0, 15.2))
    FW, FH = fig.get_size_inches()

    def ax_at(x, y, w, h, **kw):
        return fig.add_axes([x / FW, 1 - (y + h) / FH, w / FW, h / FH], **kw)

    def heading(x, y, s, title):
        fig.text(x / FW, 1 - y / FH, s, fontsize=30, weight="bold", va="baseline", ha="left")
        fig.text((x + 0.42) / FW, 1 - y / FH, title, fontsize=20, va="baseline", ha="left")

    # ---------- a: representative paths (unchanged)
    REPS = {g: (VALS[g] - VALS[g].median()).abs().idxmin() for g in G6}
    PATH = T.groupby("mouse").path_m.mean()
    for g in ("Het young",):          # typical on both improvement and how much the mouse moves
        ms = VALS[g].index
        rk = (VALS[g] - VALS[g].median()).abs().rank() + (PATH[ms] - PATH[ms].median()).abs().rank()
        REPS[g] = rk.idxmin()
    heading(0.25, 0.55, "a", "Typical WT, Het and young Hom mice avoid the zone by day 2; old Hom do not")
    kx, ky = 0.45, 7.35
    kax = ax_at(kx, ky - 0.27, 0.34, 0.34)
    kax.add_patch(Wedge((0, 0), 1, 15, 75, color=ZONE, alpha=0.3, lw=0))
    kax.set_xlim(-0.2, 1.0)
    kax.set_ylim(-0.2, 1.0)
    kax.set_aspect("equal")
    kax.axis("off")
    fig.text((kx + 0.4) / FW, 1 - ky / FH, "shock zone (fixed in the room; the floor turns counter-clockwise)",
             fontsize=FS - 3, va="baseline", color=SOFT)
    fig.text((kx + 7.75) / FW, 1 - ky / FH, "×", color=ZONE, fontsize=24, va="baseline", weight="bold")
    fig.text((kx + 8.05) / FW, 1 - ky / FH, "shock", fontsize=FS - 3, va="baseline", color=SOFT)
    AW = 2.0
    for i, g in enumerate(G6):
        m = REPS[g]
        d = T[T.mouse == m]
        best = {dd: d[d.day == dd].sort_values(["spr", "session"]).iloc[0] for dd in ("d1", "d2")}
        col = GC[g.split()[0]]
        r_, c_ = divmod(i, 3)
        x0, y0 = 0.35 + c_ * 4.35, 1.25 + r_ * 3.2
        fig.text((x0 + AW + 0.05) / FW, 1 - (y0 - 0.12) / FH, "%s %s, mouse %s" % (g.split()[0], g.split()[1], m),
                 ha="center", va="baseline", fontsize=FS - 1, color=col)
        for j, dd in enumerate(("d1", "d2")):
            ax = ax_at(x0 + j * (AW + 0.1), y0, AW, AW)
            ax.add_patch(Wedge((0, 0), 41, 15, 75, color=ZONE, alpha=0.15, lw=0, zorder=0))
            ax.add_patch(Circle((0, 0), 41, fill=False, ec=LINE, lw=1.4))
            s = int(best[dd].session)
            xs, ys, sh, n_sh = track(os.path.join(ND, best[dd].folder, best[dd].file))
            assert n_sh == int(best[dd].shocks), (m, s, n_sh, best[dd].shocks)
            ax.plot(xs, ys, color=col, lw=0.6, alpha=0.85, rasterized=True)
            sh = sh[sh < len(xs)]
            ax.scatter(xs[sh], ys[sh], marker="x", s=60, color=ZONE, lw=2.4, zorder=4)
            ax.set_xlim(-43, 43)
            ax.set_ylim(-43, 43)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.text(0, -47, "Day %s (s%d): %.2f/turn" % (dd[1], s, best[dd].spr), ha="center", va="top", fontsize=FS - 3.5)

    # ---------- b: learning curves as each mouse's change from its own day-1 mean, Het and Hom each against WT
    heading(13.75, 0.55, "b", "Against their own day 1, only old Hom do not improve on day 2")
    T["block"] = (T.session - 1) // 2
    BLK = T.groupby(["mouse", "block"]).spr.mean().unstack()
    CHG = BLK.sub(D1, axis=0)                     # each two-session block minus the mouse's own s1-s8 mean
    xs_b = np.arange(8) * 2 + 1.5
    curves = {}
    for g in G6:
        v = CHG.loc[GRP[GRP == g].index]
        curves[g] = pd.DataFrame({"mean": v.mean(), "sem": v.sem(), "n": v.notna().sum()})
    lo = min(float((c["mean"] - c["sem"]).min()) for c in curves.values())
    hi = max(float((c["mean"] + c["sem"]).max()) for c in curves.values())
    yt = np.arange(np.ceil((lo - 0.12) * 2) / 2, np.floor((hi + 0.3) * 2) / 2 + 0.001, 0.5)
    BW, BH, BX0, BY0 = 4.45, 2.55, 14.65, 1.35
    for r_, age in enumerate(("young", "old")):
        for c_, gen in enumerate(("Het", "Hom")):
            ax = ax_at(BX0 + c_ * (BW + 0.35), BY0 + r_ * (BH + 0.62), BW, BH)
            ax.axhline(0, color=LINE, lw=1.4, zorder=0)
            for g, z in (("WT " + age, 2), ("%s %s" % (gen, age), 3)):
                d = curves[g]
                col = GC[g.split()[0]]
                ax.errorbar(xs_b, d["mean"], yerr=d["sem"], color=col, lw=2.6, marker="o", ms=8, mec="white", mew=1.2,
                            elinewidth=1.6, capsize=0, zorder=z, label="%s (n = %d)" % (g.split()[0], NG[g]))
            ax.axvline(8.5, color=LINE, lw=1.2, ls=(0, (4, 3)), zorder=0)
            ax.set_xlim(0.3, 16.7)
            ax.set_ylim(lo - 0.12, hi + 0.62)
            ax.set_yticks(yt)
            ax.set_xticks([1, 4, 8, 9, 12, 16])
            if r_ == 1:
                ax.set_xlabel("Session")
            else:
                ax.set_xticklabels([])
            if c_ == 0:
                ax.set_ylabel("Change in shocks per turn\nfrom own day-1 mean")
                ax.text(0.02, 0.03, "< 0: fewer than on day 1", transform=ax.transAxes, fontsize=FS - 5, color=SOFT,
                        va="bottom", ha="left")
            else:
                ax.set_yticklabels([])
            ax.legend(frameon=False, loc="upper right", handlelength=1.2, borderaxespad=0.1)
            ax.text(0.02, 0.97, "%s %s vs WT" % (age.capitalize(), gen), transform=ax.transAxes, fontsize=FS - 1,
                    weight="bold", va="top", color=GC[gen])
            if r_ == 0:
                ax.text(4.5, 1.02, "day 1", ha="center", va="bottom", fontsize=FS - 4, color=SOFT,
                        transform=ax.get_xaxis_transform())
                ax.text(12.5, 1.02, "day 2", ha="center", va="bottom", fontsize=FS - 4, color=SOFT,
                        transform=ax.get_xaxis_transform())

    # ---------- c: each mouse's day-1-to-day-2 change (was d)
    heading(0.25, 8.6, "c", "Only old Hom fail to improve from day 1 to day 2; no other group differs from WT")
    ax = ax_at(1.45, 9.3, 11.8, 4.95)
    xpos = {"WT young": 0, "Het young": 1, "Hom young": 2, "WT old": 3.7, "Het old": 4.7, "Hom old": 5.7}
    rs = np.random.RandomState(4)
    for g in G6:
        col = GC[g.split()[0]]
        x = xpos[g]
        v = VALS[g]
        ring = np.array([MARK_FLAGGED and m in flagged for m in v.index])
        ax.scatter(x - 0.13 + (rs.rand(v.size) - 0.5) * 0.3, v.values, s=95, color=col, alpha=0.95, zorder=3,
                   edgecolors=np.where(ring, INK, "white"), linewidths=np.where(ring, 2.0, 1.0))
        tm, dvar, h = trim_stats(v.values)
        ci = st.t.ppf(0.975, h - 1) * np.sqrt(dvar)
        ax.errorbar(x + 0.24, tm, yerr=ci, fmt="o", ms=13, color=col, mec=INK, mew=1.8, ecolor=INK, elinewidth=2.6,
                    capsize=8, capthick=2.4, zorder=6)
    ax.axhline(0, color=LINE, lw=1.4, zorder=0)
    if MARK_FLAGGED and flagged:
        ax.scatter([0.015], [0.04], transform=ax.transAxes, s=95, color=LINE, edgecolors=INK, linewidths=2.0, clip_on=False)
        ax.text(0.03, 0.04, "ringed: robust-rule outliers (old Hom 413, 417; young WT 1665, 1667)", transform=ax.transAxes,
                fontsize=FS - 5, color=SOFT, va="center", ha="left")
    top = float(IMP.max())

    def bracket(x1, x2, y, text, hh=0.07, fs=FS - 2):
        ax.plot([x1, x1, x2, x2], [y - hh, y, y, y - hh], color=INK, lw=1.7, clip_on=False)
        ax.text((x1 + x2) / 2, y + 0.035, text, ha="center", va="bottom", fontsize=fs)

    y1 = top + 0.22
    step = 0.42
    bracket(0, 1, y1, sig(PAIR_P["Het young"]), fs=FS - 4)
    bracket(3.7, 4.7, y1, sig(PAIR_P["Het old"]), fs=FS - 4)
    bracket(0, 2, y1 + step, sig(PAIR_P["Hom young"]), fs=FS - 4)
    bracket(3.7, 5.7, y1 + step, sig(PAIR_P["Hom old"]), fs=FS - 4)
    bracket(1, 4.7, y1 + 2 * step + 0.05, "Het × age, GEE: " + sig(INT["Het"]["p"]), fs=FS - 3)
    bracket(2, 5.7, y1 + 3 * step + 0.1, "Hom × age, GEE: " + sig(INT["Hom"]["p"]), fs=FS - 2)
    ax.set_ylim(min(-1.9, float(IMP.min()) - 0.15) - (0.25 if MARK_FLAGGED and flagged else 0), y1 + 4 * step + 0.2)
    ax.set_xlim(-0.55, 6.25)
    ax.set_xticks([xpos[g] for g in G6])
    ax.set_xticklabels(["%s\n(n = %d)" % (g.split()[0], NG[g]) for g in G6])
    ax.tick_params(axis="x", length=0)
    for lab, xc in (("Young", 1.0), ("Old", 4.7)):
        ax.text(xc, -0.175, lab, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=FS + 1, weight="bold")
        ax.plot([xc - 1.15, xc + 1.15], [-0.16, -0.16], transform=ax.get_xaxis_transform(), color=LINE, lw=1.2,
                clip_on=False)
    ax.set_ylabel("Change in shocks per turn\n(day 2 − day 1; < 0 = improved)")

    # ---------- d: GEE forest (was c)
    heading(13.75, 8.6, "d", "GEE: only old Hom improve less than WT")
    ax = ax_at(15.45, 9.3, 6.0, 4.95)
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
    xl = (min(0.3, 0.9 * min(r["lo"] for r in GEE.values())), max(5, 1.1 * max(r["hi"] for r in GEE.values())))
    ax.set_xlim(*xl)
    xt = [t for t in (0.25, 0.5, 1, 2, 4, 8) if xl[0] < t < xl[1]]
    ax.set_xticks(xt)
    ax.set_xticklabels(["%g" % t for t in xt])
    ax.minorticks_off()
    ax.set_yticks(ypos)
    ax.set_yticklabels([lab for _g, lab in rows])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.6, 4.35)
    ax.set_xlabel("Day 2 / day 1, relative to WT (rate ratio, 95% CI)")
    ax.text(0.95, 4.2, "← improves more", ha="right", va="center", fontsize=FS - 4, color=SOFT)
    ax.text(1.05, 4.2, "improves less →", ha="left", va="center", fontsize=FS - 4, color=SOFT)
    ax.text(0.0, 1.02, "Genotype × age × day:  Hom %s (%s)  ·  Het %s (%s)" % (
        stars(INT["Hom"]["p"]), plab(INT["Hom"]["p"]), stars(INT["Het"]["p"]), plab(INT["Het"]["p"])),
        transform=ax.transAxes, fontsize=FS - 3, va="bottom")

    # ---------- outputs
    os.makedirs(OUTD, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(OUTD, "KCNT1_AA_poster_figure_v2_%s.%s" % (tag, ext)), dpi=300, bbox_inches="tight",
                    pad_inches=0.12)
    plt.close(fig)
    pd.DataFrame([dict(group=g, block="s%d-s%d" % (2 * k + 1, 2 * k + 2), n=int(curves[g].loc[k, "n"]),
                       change_from_own_day1_mean=curves[g].loc[k, "mean"], change_sem=curves[g].loc[k, "sem"],
                       absolute_shocks_per_turn=BLK.loc[GRP[GRP == g].index, k].mean(),
                       absolute_sem=BLK.loc[GRP[GRP == g].index, k].sem())
                  for g in G6 for k in range(8)]).to_csv(os.path.join(OUTD, "panel_b_values_%s.csv" % tag), index=False)
    pd.DataFrame([dict(group=g, n=NG[g], trimmed_mean=trim_stats(VALS[g].values)[0], mean=VALS[g].mean(),
                       yuen_p_vs_WT=PAIR_P.get(g, np.nan)) for g in G6]).to_csv(
        os.path.join(OUTD, "panel_c_values_%s.csv" % tag), index=False)
    pd.DataFrame([dict(comparison="%s vs WT %s" % (g, g.split()[1]), **v) for g, v in GEE.items()]).to_csv(
        os.path.join(OUTD, "panel_d_gee_ratio_of_ratios_%s.csv" % tag), index=False)

    # ---------- legend
    a1, a2 = ABS["day 1"], ABS["day 2"]

    def nums(a):
        return "%.2f vs %.2f, Welch %s" % (a["Hom"], a["WT"], plab(a["p"]))
    if a1["p"] >= 0.05 and a2["p"] >= 0.05:
        absolute = "In absolute shocks per turn, old Hom did not differ from old WT on day 1 (%s) or day 2 (%s)." % (
            nums(a1), nums(a2))
    else:
        part = []
        for a, dname in ((a1, "day 1"), (a2, "day 2")):
            part.append("took %s shocks per turn than old WT on %s (%s)" % ("fewer" if a["Hom"] < a["WT"] else "more", dname,
                                                                           nums(a)) if a["p"] < 0.05 else
                        "did not differ from them on %s (%s)" % (dname, nums(a)))
        absolute = "In absolute terms, old Hom %s and %s." % tuple(part)
    if drop:
        who = ("Four sessions with documented shock-delivery faults were excluded, and four outlier mice by a robust rule "
               "(%s); %d mice (n per group in c)." % (OUTLIER_TEXT, sum(NG.values())))
        ring = ""
    elif MARK_FLAGGED:
        who = ("Four sessions with documented shock-delivery faults were excluded; all %d mice are shown (n per group in "
               "c), including the four robust-rule outliers ringed in c." % sum(NG.values()))
        ring = " Ringed dots, the four mice a robust rule flags as outliers (%s)." % OUTLIER_TEXT
    else:
        who = ("Four sessions with documented shock-delivery faults were excluded; all %d mice are shown (n per group in "
               "c), including the four that a robust rule flags as outliers (%s)." % (sum(NG.values()), OUTLIER_TEXT))
        ring = ""
    legend = """Old KCNT1 Hom mice fail to improve across days of active place avoidance; young Hom and Het mice do not differ from WT.

a, Paths of a representative mouse per group in its best session of each day (fewest shocks per floor turn). Each mouse is the one closest to its group's median day-1-to-day-2 change; for young Het, closest to the median on both that change and distance traveled. Line, the mouse's position over the 10-min session; red wedge, shock zone (fixed in the room; the floor turns counter-clockwise); x, shocks.

b, Shocks per turn of the rotating floor across the 16 training sessions, shown as each mouse's change from its own day-1 mean (each pair of sessions minus the mouse's s1-s8 mean; mean +/- s.e.m. across mice), Het (orange) and Hom (purple) each against WT (gray) of the same age. 0, the mouse's own day-1 level; below 0, fewer shocks per turn than on day 1. The day-2 points are the time course of the change summarized in c. Dashed line, overnight break between day 1 (s1-s8) and day 2 (s9-s16). %s

c, Each mouse's change in shocks per turn from day 1 to day 2 (dots); bars, 20%% trimmed mean +/- 95%% CI. Within-age comparisons with WT, Yuen's trimmed-mean t-test (old Hom vs old WT, %s; all others P >= %.2f); genotype x age, GEE interaction from d.%s

d, Poisson generalized estimating equation (GEE) of shocks per session with log(floor turns) as offset; mice as clusters, exchangeable working correlation, robust standard errors; reference, old WT on day 2. Points, each genotype's day-2/day-1 rate ratio relative to WT of the same age, with 95%% CI (> 1, smaller improvement than WT). Old Hom improve less than old WT (rate ratio %.2f, 95%% CI %.2f-%.2f, %s); young Hom and Het of either age do not differ from WT. Genotype x age x day: Hom %s, Het %s.

Shocks are counted per turn of the floor because the floor's speed differed between cohorts (about 2.5 to 6 deg/s). %s Exploratory analysis; P values are not corrected for multiple comparisons. *P < 0.05, **P < 0.01, ***P < 0.001; ns, P >= 0.05.
""" % (absolute, plab(PAIR_P["Hom old"]), np.floor(min(others_c) * 100) / 100, ring, GEE["Hom old"]["ratio"],
       GEE["Hom old"]["lo"], GEE["Hom old"]["hi"], plab(GEE["Hom old"]["p"]), plab(INT["Hom"]["p"]),
       plab(INT["Het"]["p"]), who)
    open(os.path.join(OUTD, "figure_legend_v2_%s.txt" % tag), "w", encoding="utf-8").write(legend)
    print("[%s] mice %d, n %s, reps %s" % (tag, sum(NG.values()), NG, REPS))
    print("   Yuen", {k: round(float(v), 4) for k, v in PAIR_P.items()})
    print("   GEE", {k: {kk: round(float(vv), 3) for kk, vv in v.items()} for k, v in GEE.items()})
    print("   3-way", {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in INT.items()})
    print("   abs", {k: {kk: round(float(vv), 3) for kk, vv in v.items()} for k, v in ABS.items()})


for TAG, DROP in (("without_outliers", OUTLIERS), ("with_outliers", set())):
    make(TAG, DROP)
