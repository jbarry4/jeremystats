"""GEE (genotype x age x day, old WT day 2 as the comparator) and a per-turn learning criterion, with a summary PDF.
Data: training sessions s1-s16 without the cooked and medium-cooked sessions (and without mice 520, 1644, 1667).
Shocks per turn = shocks / floor turns (refined floor reading)."""
import os
import shutil
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import patsy
import pymupdf
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats as st
from statsmodels.duration.survfunc import survdiff

import crfig as X
import figlib_aa as F
import s4_rescue_pages as R
import stats_lib as S

warnings.filterwarnings("ignore")
OUT = os.path.join(F.HERE, "out_gee")
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1_AA_GEE_Criterion_112426"
F.FOOT = "KCNT1 active avoidance · GEE and learning criterion, a supplement to the story menu · exploratory, P uncorrected · 2026-11-24"
os.makedirs(OUT, exist_ok=True)
G6 = ["WT young", "Het young", "Hom young", "WT old", "Het old", "Hom old"]
GC = {"WT": F.GCOL["WT"], "Het": F.GCOL["Het"], "Hom": F.GCOL["Hom"]}

# ------------------------------------------------------------------ data
TR = X.CR["TR"].copy()
drop = R.COOKED | R.MEDIUM
TR = TR[~TR.apply(lambda r: (r.mouse, int(r.session)) in drop or r.mouse in R.MEDIUM_MICE, axis=1)].copy()
TR = TR[(TR.session >= 1) & (TR.session <= 16) & TR.turns.notna() & (TR.turns > 0)].copy()
TR["day"] = np.where(TR.session <= 8, "d1", "d2")
TR["sw"] = np.where(TR.session <= 8, TR.session, TR.session - 8).astype(int)
TR["grp"] = TR.geno + " " + TR.age
TR["logt"] = np.log(TR.turns)
N_SESS, N_MICE = len(TR), TR.mouse.nunique()
NG = TR.groupby("grp").mouse.nunique().to_dict()

# ------------------------------------------------------------------ task 1: GEE
FORM = "shocks ~ C(geno, Treatment('WT')) * C(age, Treatment('old')) * C(day, Treatment('d2'))"
MODELS = {"A: day": FORM, "B: day + session within day": FORM + " + C(sw)"}
GEE = {}
for name, f in MODELS.items():
    mod = smf.gee(f, "mouse", TR, family=sm.families.Poisson(), cov_struct=sm.cov_struct.Exchangeable(), offset=TR.logt)
    fit = mod.fit()
    try:
        fbr = mod.fit(cov_type="bias_reduced")
        p_br = fbr.pvalues
    except Exception:  # noqa: BLE001
        p_br = pd.Series(np.nan, index=fit.params.index)
    tab = pd.DataFrame({"term": fit.params.index, "coef": fit.params.values, "rate_ratio": np.exp(fit.params.values),
                        "rr_lo": np.exp(fit.conf_int()[0].values), "rr_hi": np.exp(fit.conf_int()[1].values),
                        "p_robust": fit.pvalues.values, "p_bias_reduced": p_br.reindex(fit.params.index).values})
    GEE[name] = dict(fit=fit, tab=tab, rho=float(fit.cov_struct.dep_params))
fitA = GEE["A: day"]["fit"]
# model-based shocks per turn for every group x day (model A), with 95% CIs
cells = pd.DataFrame([dict(geno=g.split()[0], age=g.split()[1], day=d) for g in G6 for d in ("d1", "d2")])
cells["shocks"] = 0
Xc = patsy.build_design_matrices([fitA.model.data.design_info.subset(fitA.model.data.design_info.term_names)
                                  if False else fitA.model.data.orig_exog.design_info], cells)[0] \
    if hasattr(fitA.model.data.orig_exog, "design_info") else None
if Xc is None:
    di = fitA.model.data.design_info
    Xc = np.asarray(patsy.build_design_matrices([di], cells)[0])
Xc = np.asarray(Xc)
eta = Xc @ fitA.params.values
se = np.sqrt(np.einsum("ij,jk,ik->i", Xc, fitA.cov_params().values, Xc))
cells["rate"], cells["lo"], cells["hi"] = np.exp(eta), np.exp(eta - 1.96 * se), np.exp(eta + 1.96 * se)
# day-1 to day-2 change per group (rate ratio d2/d1) and the genotype contrasts on it
cov = fitA.cov_params().values
contr = []
for g in G6:
    r1 = Xc[(cells.geno == g.split()[0]).values & (cells.age == g.split()[1]).values & (cells.day == "d1").values][0]
    r2 = Xc[(cells.geno == g.split()[0]).values & (cells.age == g.split()[1]).values & (cells.day == "d2").values][0]
    L = r2 - r1
    est, s_ = L @ fitA.params.values, np.sqrt(L @ cov @ L)
    contr.append(dict(group=g, d2_over_d1=np.exp(est), lo=np.exp(est - 1.96 * s_), hi=np.exp(est + 1.96 * s_),
                      p=2 * st.norm.sf(abs(est / s_)), L=L))
CON = pd.DataFrame(contr)


def diff_change(ga, gb):
    """Ratio of (d2/d1) between two groups, Wald test."""
    La = CON.set_index("group").loc[ga, "L"]
    Lb = CON.set_index("group").loc[gb, "L"]
    L = Lb - La
    est, s_ = L @ fitA.params.values, np.sqrt(L @ cov @ L)
    return np.exp(est), np.exp(est - 1.96 * s_), np.exp(est + 1.96 * s_), 2 * st.norm.sf(abs(est / s_))


PAIRS = [("WT old", "Hom old"), ("WT old", "Het old"), ("WT young", "Hom young"), ("WT young", "Het young")]
DCH = pd.DataFrame([dict(compare="%s vs %s" % (b, a), ratio=r[0], lo=r[1], hi=r[2], p=r[3])
                    for a, b in PAIRS for r in [diff_change(a, b)]])

# ------------------------------------------------------------------ task 2: per-turn criterion
THR = 5.0 / X.CR["TR"].turns.mean()          # 5 shocks / average turns per session (all sessions)
piv = TR.pivot_table(index="mouse", columns="session", values="spr")
crit, kept, info = {}, {}, {}
for m in piv.index:
    row = piv.loc[m]
    hit = None
    for k in range(1, 16):
        a, b = row.get(k, np.nan), row.get(k + 1, np.nan)
        if np.isfinite(a) and np.isfinite(b) and a <= THR and b <= THR:
            hit = k + 1
            break
    crit[m] = hit
    if hit is not None and hit <= 8:
        s9, s10 = row.get(9, np.nan), row.get(10, np.nan)
        kept[m] = (bool(s9 <= THR and s10 <= THR) if (np.isfinite(s9) and np.isfinite(s10)) else None)
GRP = TR.groupby("mouse").grp.first().to_dict()
CR2 = pd.DataFrame([dict(mouse=m, group=GRP[m], criterion_session=crit[m], reached=crit[m] is not None,
                         reached_day=(None if crit[m] is None else (1 if crit[m] <= 8 else 2)), kept_day2=kept.get(m))
                    for m in piv.index]).sort_values(["group", "criterion_session"])


def surv(ms):
    t = np.array([crit[m] if crit[m] is not None else 16 for m in ms], float)
    e = np.array([1 if crit[m] is not None else 0 for m in ms])
    return t, e


def compare(ga, gb):
    ma = [m for m in piv.index if GRP[m] == ga]
    mb = [m for m in piv.index if GRP[m] == gb]
    ta, ea = surv(ma)
    tb, eb = surv(mb)
    p_lr = float(survdiff(np.r_[ta, tb], np.r_[ea, eb], np.r_[np.zeros(len(ta)), np.ones(len(tb))])[1])
    p_gb = float(survdiff(np.r_[ta, tb], np.r_[ea, eb], np.r_[np.zeros(len(ta)), np.ones(len(tb))], weight_type="gb")[1])
    p_f = st.fisher_exact([[ea.sum(), len(ea) - ea.sum()], [eb.sum(), len(eb) - eb.sum()]])[1]
    ka = [kept[m] for m in ma if kept.get(m) is not None]
    kb = [kept[m] for m in mb if kept.get(m) is not None]
    p_k = (st.fisher_exact([[sum(ka), len(ka) - sum(ka)], [sum(kb), len(kb) - sum(kb)]])[1] if ka and kb else np.nan)
    return dict(compare="%s vs %s" % (gb, ga), reached_a="%d/%d" % (ea.sum(), len(ea)), reached_b="%d/%d" % (eb.sum(), len(eb)),
                median_a=S.km_median(ta, ea), median_b=S.km_median(tb, eb), p_logrank=p_lr, p_gehan=p_gb, p_fisher=p_f,
                kept_a="%d/%d" % (sum(ka), len(ka)), kept_b="%d/%d" % (sum(kb), len(kb)), p_kept=p_k)


CMP = pd.DataFrame([compare(a, b) for a, b in PAIRS + [("Hom young", "Hom old"), ("WT young", "WT old")]])


# ------------------------------------------------------------------ pages
def pf(p):
    return "n/a" if not np.isfinite(p) else F.pstr(p) + (" " + F.stars(p) if p < 0.05 else "")


def label(term):
    t = term.replace("C(geno, Treatment('WT'))[T.", "").replace("C(age, Treatment('old'))[T.", "").replace(
        "C(day, Treatment('d2'))[T.", "").replace("]", "").replace(":", " x ")
    return "Intercept (old WT, day 2)" if t == "Intercept" else t.replace("d1", "day 1")


def page_gee():
    fig, y = F.page("GEE: only old Hom fail to cut their shocks per turn from day 1 to day 2",
                    "1 · GEE, GENOTYPE x AGE x DAY (COMPARATOR: OLD WT, DAY 2)", number=2)
    y += 0.3
    h = CON.set_index("group")
    F.letter(fig, 0.4, y, "a", "Model-based shocks per turn on day 1 and day 2: day 2 divided by day 1 is %.2f for old Hom against "
                               "%.2f for old WT" % (h.loc["Hom old", "d2_over_d1"], h.loc["WT old", "d2_over_d1"]), width=7.6)
    ax = F.axes_in(fig, 0.75, y + 0.35, 4.4, 2.2)
    for k, g in enumerate(G6):
        c = cells[(cells.geno == g.split()[0]) & (cells.age == g.split()[1])].set_index("day")
        xs = [k - 0.15, k + 0.15]
        col = GC[g.split()[0]]
        ax.plot(xs, [c.loc["d1", "rate"], c.loc["d2", "rate"]], color=col, lw=1.2)
        for x_, d in zip(xs, ("d1", "d2")):
            ax.errorbar(x_, c.loc[d, "rate"], yerr=[[c.loc[d, "rate"] - c.loc[d, "lo"]], [c.loc[d, "hi"] - c.loc[d, "rate"]]],
                        fmt="o" if d == "d1" else "s", ms=4, color=col, mfc="white" if d == "d1" else col, ecolor=col, capsize=2,
                        lw=0.9)
    ax.set_xticks(range(6))
    ax.set_xticklabels([g.replace(" ", "\n") + "\n(n %d)" % NG.get(g, 0) for g in G6], fontsize=6)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Shocks per turn (model, 95% CI)")
    ax.set_ylim(0, None)
    ax.text(0.99, 0.97, "open circle: day 1 · filled square: day 2", transform=ax.transAxes, ha="right", va="top", fontsize=6,
            color=F.SOFT)
    # table of day-2 / day-1 ratios
    axt = F.axes_in(fig, 5.45, y + 0.35, 2.5, 2.2)
    axt.axis("off")
    axt.text(0, 1, "Day 2 / day 1 (rate ratio)", fontsize=6.4, weight="bold", va="top", transform=axt.transAxes)
    for i, r in enumerate(CON.itertuples()):
        axt.text(0, 0.86 - i * 0.12, "%s  %.2f (%.2f-%.2f)" % (r.group, r.d2_over_d1, r.lo, r.hi), fontsize=6.2, va="top",
                 transform=axt.transAxes)
        axt.text(0.98, 0.86 - i * 0.12, pf(r.p), fontsize=6.2, va="top", ha="right", transform=axt.transAxes,
                 color=F.INK if r.p < 0.05 else F.FAINT)
    yb = y + 3.15
    hh = DCH.set_index("compare")
    F.letter(fig, 0.4, yb, "b", "Does each genotype's day-1-to-day-2 drop differ from WT's? Old Hom: %s; young Hom: %s" % (
        pf(hh.loc["Hom old vs WT old", "p"]), pf(hh.loc["Hom young vs WT young", "p"])), width=7.6)
    axb = F.axes_in(fig, 0.6, yb + 0.25, 7.3, 1.0)
    axb.axis("off")
    hx = [0, 0.32, 0.62]
    for j, hdr in enumerate(["Comparison of the day 2 / day 1 ratio", "Ratio of ratios (95% CI)", "P (robust Wald)"]):
        axb.text(hx[j], 1, hdr, fontsize=6.2, weight="bold", color=F.SOFT, va="top", transform=axb.transAxes)
    for i, r in enumerate(DCH.itertuples()):
        yy = 0.78 - i * 0.2
        for j, c in enumerate([r.compare, "%.2f (%.2f-%.2f)" % (r.ratio, r.lo, r.hi), pf(r.p)]):
            axb.text(hx[j], yy, c, fontsize=6.4, va="top", transform=axb.transAxes,
                     color=F.INK if (j < 2 or r.p < 0.05) else F.FAINT)
    yc = yb + 1.6
    F.letter(fig, 0.4, yc, "c", "Model terms, two ways of handling time; the genotype x age x day terms test whether the "
                                "genotype gap in the day effect differs between young and old", width=7.6)
    for k, (name, g) in enumerate(GEE.items()):
        axc = F.axes_in(fig, 0.6 + k * 3.75, yc + 0.3, 3.55, 3.4)
        axc.axis("off")
        axc.text(0, 1, "Model %s (rho %.2f)" % (name, g["rho"]), fontsize=6.4, weight="bold", va="top", transform=axc.transAxes)
        axc.text(0.55, 0.955, "rate ratio (95% CI)", fontsize=5.6, color=F.SOFT, va="top", transform=axc.transAxes)
        axc.text(1.0, 0.955, "P", fontsize=5.6, color=F.SOFT, va="top", ha="right", transform=axc.transAxes)
        rows = g["tab"][~g["tab"].term.str.startswith("C(sw)")]
        for i, r in enumerate(rows.itertuples()):
            yy = 0.9 - i * 0.068
            three = r.term.count(":") == 2
            axc.text(0, yy, label(r.term), fontsize=5.6, va="top", transform=axc.transAxes, weight="bold" if three else "normal")
            axc.text(0.55, yy, "%.2f (%.2f-%.2f)" % (r.rate_ratio, r.rr_lo, r.rr_hi), fontsize=5.6, va="top", transform=axc.transAxes)
            axc.text(1.0, yy, pf(r.p_robust).replace("P ", ""), fontsize=5.6, va="top", ha="right", transform=axc.transAxes,
                     color=F.INK if r.p_robust < 0.05 else F.FAINT)
    F.put(fig, 0.6, yc + 3.75,
          "Poisson GEE on each session's shock count with log(floor turns) as an offset, so every term is a ratio of shocks per "
          "turn; sessions grouped by mouse, exchangeable working correlation, robust (sandwich) errors. Reference cell: old WT on "
          "day 2. Model B adds the session's position within its day (1-8) as a factor. %d sessions from %d mice (cooked and "
          "medium-cooked sessions and mice 520, 1644, 1667 removed). Robust errors with this few mice per group can run small; "
          "bias-reduced P values are in the table file." % (N_SESS, N_MICE), 7.3, size=6.0, color=F.SOFT)
    F.save(fig, OUT, "02_gee")


def page_crit():
    fig, y = F.page("Learning criterion (two sessions in a row at or under %.2f shocks per turn): reached, when, and kept "
                    "overnight" % THR, "2 · LEARNING CRITERION, MOUSE BY MOUSE", number=3)
    y += 0.3
    F.letter(fig, 0.4, y, "a", "Every mouse, session by session: filled = at or under %.2f shocks per turn (5 shocks at the average "
                               "%.1f turns); ring = criterion reached; x = session removed" % (THR, X.CR["TR"].turns.mean()),
             width=7.6)
    ms = [m for g in G6 for m in CR2[CR2.group == g].mouse]
    ax = F.axes_in(fig, 1.4, y + 0.3, 5.4, 0.105 * len(ms))
    for i, m in enumerate(ms):
        g = GRP[m]
        col = GC[g.split()[0]]
        for s in range(1, 17):
            val = piv.loc[m].get(s, np.nan)
            if not np.isfinite(val):
                ax.scatter(s, i, marker="x", s=8, color=F.FAINT, lw=0.6)
            else:
                ax.scatter(s, i, s=16, marker="s", color=col if val <= THR else "white", edgecolor=col, lw=0.5)
        if crit[m] is not None:
            ax.scatter(crit[m], i, s=48, facecolor="none", edgecolor=F.INK, lw=0.9, zorder=5)
        ax.text(0.2, i, "%s  %s" % (m, g), fontsize=5.0, ha="right", va="center", color=col)
        k = kept.get(m)
        if k is not None:
            ax.text(16.9, i, "kept" if k else "lost", fontsize=5.0, va="center", color=F.KICK if k else F.ZONE)
    for i in range(1, len(ms)):
        if GRP[ms[i]] != GRP[ms[i - 1]]:
            ax.axhline(i - 0.5, color=F.GRID, lw=0.6)
    ax.axvline(8.5, color=F.FAINT, lw=0.6)
    ax.set_xlim(0.4, 16.6)
    ax.set_ylim(len(ms) - 0.5, -0.5)
    ax.set_yticks([])
    ax.set_xticks(range(1, 17))
    ax.tick_params(axis="x", labelsize=5.5)
    ax.xaxis.tick_top()
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["top"].set_visible(True)
    F.put(fig, 1.4, y + 0.3 + 0.105 * len(ms) + 0.2, "Right of each row: for mice that reached criterion on day 1, whether s9 "
                              "and s10 were both still at or under the threshold (kept) or not (lost). Vertical line: overnight break.",
          6.0, size=6.0, color=F.SOFT)
    F.save(fig, OUT, "03_criterion_mice")
    # page 4: curves and tests
    fig, y = F.page("Who reaches criterion, how fast, and whether they keep it overnight",
                    "2 · LEARNING CRITERION, GROUPS", number=4)
    y += 0.3
    c = CMP.set_index("compare")
    F.letter(fig, 0.4, y, "a", "Share of mice that have reached criterion by each session (survival style; never reached = still "
                               "out at s16)", width=7.6)
    for k, age in enumerate(("young", "old")):
        ax = F.axes_in(fig, 0.75 + k * 3.7, y + 0.35, 3.0, 1.9)
        for g in [x for x in G6 if x.endswith(age)]:
            mm = [m for m in piv.index if GRP[m] == g]
            t, e = surv(mm)
            xs = np.arange(1, 17)
            ys = S.cum_reached(t, e, xs)
            ax.step(xs, ys, where="post", color=GC[g.split()[0]], lw=1.4, label="%s (%d/%d)" % (g, e.sum(), len(e)))
        ax.axvline(8.5, color=F.FAINT, lw=0.5)
        ax.set_ylim(0, 1.02)
        ax.set_xlim(1, 16.3)
        ax.set_xticks([2, 4, 8, 9, 12, 16])
        ax.set_xlabel("Session")
        ax.set_ylabel("Reached criterion")
        ax.legend(frameon=False, fontsize=5.8, loc="lower right")
        ax.set_title("%s mice" % age.capitalize(), fontsize=6.6, loc="left")
    yb = y + 2.85
    F.letter(fig, 0.4, yb, "b", "Hom vs WT: old %s, young %s (log-rank); reached at all: old %s, young %s (Fisher)" % (
        pf(c.loc["Hom old vs WT old", "p_logrank"]), pf(c.loc["Hom young vs WT young", "p_logrank"]),
        pf(c.loc["Hom old vs WT old", "p_fisher"]), pf(c.loc["Hom young vs WT young", "p_fisher"])), width=7.6)
    axb = F.axes_in(fig, 0.5, yb + 0.25, 7.5, 2.0)
    axb.axis("off")
    hx = [0, 0.2, 0.31, 0.42, 0.53, 0.64, 0.74, 0.84, 0.92]
    for j, hdr in enumerate(["Comparison", "reached\n(ref / other)", "", "median session\n(ref / other)", "",
                             "log-rank", "Gehan", "Fisher", ""]):
        axb.text(hx[j], 1, hdr, fontsize=5.8, weight="bold", color=F.SOFT, va="top", transform=axb.transAxes)
    for i, r in enumerate(CMP.itertuples()):
        yy = 0.78 - i * 0.12
        med = lambda x: "-" if not np.isfinite(x) else "s%d" % x  # noqa: E731
        cells_ = [r.compare, r.reached_a, r.reached_b, med(r.median_a), med(r.median_b), pf(r.p_logrank).replace("P ", ""),
                  pf(r.p_gehan).replace("P ", ""), pf(r.p_fisher).replace("P ", "")]
        for j, cc in enumerate(cells_):
            axb.text(hx[j], yy, cc, fontsize=6.0, va="top", transform=axb.transAxes)
    yc = yb + 2.5
    F.letter(fig, 0.4, yc, "c", "Kept it overnight: of the mice that reached criterion on day 1, how many were still at or under "
                                "the threshold in s9 and s10", width=7.6)
    axc = F.axes_in(fig, 0.5, yc + 0.25, 7.5, 1.6)
    axc.axis("off")
    for j, hdr in enumerate(["Group", "reached on day 1", "kept on day 2", "lost on day 2"]):
        axc.text([0, 0.25, 0.45, 0.65][j], 1, hdr, fontsize=6.0, weight="bold", color=F.SOFT, va="top", transform=axc.transAxes)
    for i, g in enumerate(G6):
        mm = [m for m in piv.index if GRP[m] == g]
        d1 = [m for m in mm if crit[m] is not None and crit[m] <= 8]
        kk = [m for m in d1 if kept.get(m)]
        ll = [m for m in d1 if kept.get(m) is False]
        yy = 0.82 - i * 0.13
        for j, cc in enumerate([g, "%d of %d" % (len(d1), len(mm)), "%d %s" % (len(kk), ", ".join(kk)), "%d %s" % (len(ll), ", ".join(ll))]):
            axc.text([0, 0.25, 0.45, 0.65][j], yy, cc, fontsize=6.0, va="top", transform=axc.transAxes,
                     color=GC[g.split()[0]] if j == 0 else F.INK)
    F.put(fig, 0.5, yc + 1.95,
          "Criterion: the first time two consecutive training sessions (s8-s9 counts) both have at most %.3f shocks per turn, "
          "i.e. 5 shocks at the average %.2f floor turns of a 10-min session; the criterion session is the second of the two. "
          "A removed session breaks a pair. Kept/lost Fisher tests: old Hom vs old WT %s; young Hom vs young WT %s."
          % (THR, X.CR["TR"].turns.mean(), pf(c.loc["Hom old vs WT old", "p_kept"]), pf(c.loc["Hom young vs WT young", "p_kept"])),
          7.5, size=6.0, color=F.SOFT)
    F.save(fig, OUT, "04_criterion_groups")


def page_front():
    fig = plt.figure(figsize=(8.5, 11))
    h = CON.set_index("group")
    hh = DCH.set_index("compare")
    c = CMP.set_index("compare")
    tA = GEE["A: day"]["tab"].set_index("term")
    three = [t for t in tA.index if t.count(":") == 2]
    F.put(fig, 0.7, 0.8, "BARRY LAB · KCNT1 ACTIVE AVOIDANCE · GEE AND LEARNING CRITERION, 2026-11-24", 7.2, size=7.2, color=F.KICK,
          weight="bold")
    F.put(fig, 0.7, 1.05, "Genotype x age x day, and a per-turn learning criterion", 7.2, size=17, weight="bold")
    F.put(fig, 0.7, 1.55, "Shocks per turn of the floor, training sessions s1-s16, without the cooked and medium-cooked sessions "
                          "(%d sessions, %d mice)." % (N_SESS, N_MICE), 7.2, size=8, color=F.SOFT)
    F.put(fig, 0.72, 2.2, "Summary", 7.2, size=7.5, weight="bold")
    txt = ("1. GEE (Poisson, log-turns offset, old WT on day 2 as the comparator). Shocks per turn on day 2 relative to day 1: "
           "old WT %.2f, old Hom %.2f, young WT %.2f, young Hom %.2f, old Het %.2f, young Het %.2f (lower = more improvement). "
           "Old Hom's day-1-to-day-2 drop differs from old WT's by a ratio of %.2f (%s); young Hom's from young WT's by %.2f (%s). "
           "Genotype x age x day: %s.\n\n"
           "2. Criterion: two sessions in a row at or under %.2f shocks per turn (5 shocks at the average %.1f turns). Reached by "
           "s16: old WT %s, old Hom %s, young WT %s, young Hom %s. Hom vs WT, time to criterion: old %s, young %s (log-rank). "
           "Kept overnight (day-1 reachers still under threshold in s9-s10): see page 4."
           % (h.loc["WT old", "d2_over_d1"], h.loc["Hom old", "d2_over_d1"], h.loc["WT young", "d2_over_d1"],
              h.loc["Hom young", "d2_over_d1"], h.loc["Het old", "d2_over_d1"], h.loc["Het young", "d2_over_d1"],
              hh.loc["Hom old vs WT old", "ratio"], pf(hh.loc["Hom old vs WT old", "p"]),
              hh.loc["Hom young vs WT young", "ratio"], pf(hh.loc["Hom young vs WT young", "p"]),
              "; ".join("%s rate ratio %.2f, %s" % (label(t), tA.loc[t, "rate_ratio"], pf(tA.loc[t, "p_robust"])) for t in three),
              THR, X.CR["TR"].turns.mean(), c.loc["Hom old vs WT old", "reached_a"], c.loc["Hom old vs WT old", "reached_b"],
              c.loc["Hom young vs WT young", "reached_a"], c.loc["Hom young vs WT young", "reached_b"],
              pf(c.loc["Hom old vs WT old", "p_logrank"]), pf(c.loc["Hom young vs WT young", "p_logrank"])))
    F.put(fig, 0.72, 2.45, txt, 7.0, size=7.3)
    F.put(fig, 0.72, 6.2, "Pages: 2 GEE (model estimates, day-2/day-1 ratios, every term, two time models) · 3 criterion, mouse by "
                          "mouse · 4 criterion by group (curves, tests, overnight retention). Tables in tables/. Exploratory, P "
                          "uncorrected. * P < 0.05, ** P < 0.01, *** P < 0.001.", 7.0, size=6.6, color=F.SOFT)
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, F.FOOT, fontsize=6.5, color=F.FAINT, ha="left", va="bottom")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "1", fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    F.save(fig, OUT, "01_summary")


page_gee()
page_crit()
page_front()
os.makedirs(os.path.join(DEST, "tables"), exist_ok=True)
os.makedirs(os.path.join(DEST, "pages"), exist_ok=True)
doc = pymupdf.open()
for f in sorted(p for p in os.listdir(OUT) if p.endswith(".pdf")):
    doc.insert_pdf(pymupdf.open(os.path.join(OUT, f)))
    shutil.copy2(os.path.join(OUT, f), os.path.join(DEST, "pages"))
    shutil.copy2(os.path.join(OUT, f.replace(".pdf", ".png")), os.path.join(DEST, "pages"))
doc.save(os.path.join(DEST, "KCNT1_AA_GEE_Criterion_112426.pdf"))
for name, g in GEE.items():
    g["tab"].to_csv(os.path.join(DEST, "tables", "gee_terms_%s.csv" % name.split(":")[0]), index=False)
cells.to_csv(os.path.join(DEST, "tables", "gee_model_shocks_per_turn.csv"), index=False)
CON.drop(columns="L").to_csv(os.path.join(DEST, "tables", "gee_day2_over_day1.csv"), index=False)
DCH.to_csv(os.path.join(DEST, "tables", "gee_day_change_vs_WT.csv"), index=False)
CR2.to_csv(os.path.join(DEST, "tables", "criterion_by_mouse.csv"), index=False)
CMP.to_csv(os.path.join(DEST, "tables", "criterion_group_tests.csv"), index=False)
shutil.copy2(__file__, DEST)
pd.set_option("display.width", 220)
print(GEE["A: day"]["tab"].to_string(float_format=lambda x: "%.3f" % x))
print(GEE["B: day + session within day"]["tab"][~GEE["B: day + session within day"]["tab"].term.str.startswith("C(sw)")].to_string(float_format=lambda x: "%.3f" % x))
print(CON.drop(columns="L").to_string(float_format=lambda x: "%.3f" % x))
print(DCH.to_string(float_format=lambda x: "%.3f" % x))
print(CMP.to_string(float_format=lambda x: "%.3f" % x))
print("THR", THR, N_SESS, N_MICE, NG)
