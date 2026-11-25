"""KCNT1 AA supplement (2026-11-24): floor speed as a confound, the evidence. Six pages -> out_conf/, packaged to
Lab Figures/KCNT1_AA_Speed_Confound_112426."""
import glob
import os
import shutil
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pymupdf
from matplotlib.lines import Line2D
from scipy import stats as st

import crfig as X
import figlib_aa as F
import stats_lib as S

warnings.filterwarnings("ignore")
OUT = os.path.join(F.HERE, "out_conf")
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1_AA_Speed_Confound_112426"
F.FOOT = X.FOOT_CONF
CR, PM, OMR = X.CR, X.PM, X.OMR
ML = X.ML
G6 = ["WT young", "WT old", "Het young", "Het old", "Hom young", "Hom old"]


def rng_of(g):
    v = CR["groups"][g]
    return min(v), max(v)


# ============================================================================ page 2: who ran at what speed
def page_who():
    fig, y = F.page("Floor speed was set by when a cohort ran, and it lines up with genotype, age, year and injection",
                    "SPEED AS A CONFOUND · 1 · DIFFERENT GROUPS, DIFFERENT FLOORS", number=2)
    y += 0.3
    yh, yw = rng_of("Hom young"), rng_of("WT young")
    F.letter(fig, 0.4, y, "a", "Young Hom ran on a floor turning about half as fast as young WT's, and their speeds never overlap "
                               "(%.1f-%.1f against %.1f-%.1f deg/s)" % (yh[0], yh[1], yw[0], yw[1]), width=7.6)
    ax = F.axes_in(fig, 0.75, y + 0.35, 4.2, 2.1)
    rs = np.random.RandomState(2)
    for k, g in enumerate(G6):
        ms = [m for m in ML if X.grp(m) == g]
        lo, hi = rng_of(g)
        ax.add_patch(plt.Rectangle((k - 0.32, lo), 0.64, hi - lo, color=F.GCOL[g.split()[0]], alpha=0.12, lw=0))
        for m in ms:
            F.scatter_mouse(ax, k + (rs.rand() - 0.5) * 0.4, OMR[m], m, size=18)
    for v in (4.0, 4.8):
        ax.axhline(v, color=F.GRID, lw=0.6, zorder=0)
    ax.set_xticks(range(6))
    ax.set_xticklabels([g.replace(" ", "\n") for g in G6])
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.6, 5.6)
    ax.set_ylim(2.0, 6.5)
    ax.set_ylabel("Floor speed (deg/s)")
    ax.annotate("", xy=(4, yh[1] + 0.15), xytext=(0, yw[0] - 0.15), arrowprops=dict(arrowstyle="<->", color=X.RED_TX, lw=0.7))
    ax.text(2.0, 4.45, "no overlap", fontsize=6, color=X.RED_TX, ha="center", style="italic")
    X.genotype_legend(fig, 0.75, y + 2.85)
    F.put(fig, 5.25, y + 0.45,
          "One dot per mouse: its floor speed (refined reading of the stage speed check, the median of its 17 sessions). "
          "Shaded: each group's range. Kruskal-Wallis across the six groups %s. Old Hom (%.1f-%.1f) and the 2024 old WT "
          "ran on the same floor; every young group except Het ran on one floor only." % (
              F.pstr(CR["kw_speed"]), rng_of("Hom old")[0], rng_of("Hom old")[1]), 2.6, size=6.3, color=F.SOFT)
    # b: what travels with speed
    yb = y + 3.4
    W_ = CR["web"]
    P_ = CR["web_p"]
    F.letter(fig, 0.4, yb, "b", "Slow floors went with injection (rho %.2f), the 2026 runs and young Hom; age itself did not "
                                "track speed" % W_.loc["floor speed", "injected before AA"], width=7.6)
    ax = F.axes_in(fig, 1.85, yb + 0.35, 2.4, 2.4)
    names = list(W_.columns)
    Wv = W_.values.copy()
    np.fill_diagonal(Wv, np.nan)
    im = ax.imshow(Wv, cmap="RdBu_r", vmin=-1, vmax=1)
    for i in range(len(names)):
        for j in range(len(names)):
            if i != j:
                ax.text(j, i, "%.2f%s" % (W_.values[i, j], F.stars(P_.values[i, j])), ha="center", va="center", fontsize=5.2,
                        color="white" if abs(W_.values[i, j]) > 0.55 else F.INK)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=40, ha="right", fontsize=5.8)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=5.8)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    F.put(fig, 4.75, yb + 0.4,
          "Spearman rho between mouse-level factors (56 mice; Hom, young Hom, run in 2026 and injected are 0/1). Stars: "
          "P < 0.05 / 0.01 / 0.001. These factors travel together, so no comparison across cohorts can say which of them "
          "made a difference. What singles out the floor speed is the next two pages: it changes the counts inside the same "
          "mouse and inside one genotype.", 3.1, size=6.3, color=F.SOFT)
    # c: which comparisons share speeds
    yc = yb + 3.55
    F.letter(fig, 0.4, yc, "c", "Of the menu's comparisons, only old Hom against old WT, and Het against WT, have mice on the same "
                                "floor speeds", width=7.6)
    comps = [("Young Hom vs young WT", "Hom young", "WT young"), ("Young Hom vs young Het", "Hom young", "Het young"),
             ("Old vs young Hom", "Hom old", "Hom young"), ("Old vs young WT", "WT old", "WT young"),
             ("Old Hom vs old WT", "Hom old", "WT old"), ("Old Het vs old WT", "Het old", "WT old")]
    ax = F.axes_in(fig, 0.75, yc + 0.2, 7.0, 1.5)
    ax.axis("off")
    hx = [0, 0.27, 0.45, 0.63, 0.82]
    for j, h in enumerate(["Comparison", "Group A speeds", "Group B speeds", "Mice of A inside B's range", "Status"]):
        ax.text(hx[j], 1, h, fontsize=6.2, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, (lab, a, b) in enumerate(comps):
        va, vb = CR["groups"][a], CR["groups"][b]
        inside = sum(1 for x in va if min(vb) <= x <= max(vb))
        ok = inside >= 3
        status = "shares speeds" if ok else ("one mouse" if inside == 1 else "no overlap")
        yy = 0.8 - i * 0.14
        for j, c in enumerate([lab, "%.1f-%.1f (n %d)" % (min(va), max(va), len(va)), "%.1f-%.1f (n %d)" % (min(vb), max(vb), len(vb)),
                               "%d of %d" % (inside, len(va)), status]):
            ax.text(hx[j], yy, c, fontsize=6.3, va="top", transform=ax.transAxes, color=(X.RED_TX if (j == 4 and not ok) else F.INK))
    F.save(fig, OUT, "02_different_floors")


# ============================================================================ page 3: the same mouse on a faster floor
def page_same_mouse():
    fig, y = F.page("The same mouse, on a faster floor, enters the zone more often", "SPEED AS A CONFOUND · 2 · INSIDE ONE MOUSE",
                    number=3)
    y += 0.3
    FE = CR["FE"]
    F.letter(fig, 0.4, y, "a", "Within each mouse, every extra deg/s of floor speed adds %.1f entrances to a session (%s); counted "
                               "per turn of the floor it adds nothing (%s)" % (FE["entrances"][0], F.pstr(FE["entrances"][1]),
                                                                              F.pstr(FE["epr"][1])), width=7.6)
    pts = CR["fe_points"]
    bins = np.arange(-0.9, 0.91, 0.2)
    for k, (col, lab, key) in enumerate((("entrances_res", "Entrances, against the mouse's\nown average (per session)", "entrances"),
                                         ("epr_res", "Entrances per turn, against the\nmouse's own average", "epr"))):
        ax = F.axes_in(fig, 0.75 + k * 3.7, y + 0.35, 2.9, 1.7)
        b = pd.cut(pts.om_dev, bins)
        g = pts.groupby(b)[col].agg(["mean", "sem", "size"])
        xc = (bins[:-1] + bins[1:]) / 2
        ok = g["size"].values >= 8
        ax.scatter(pts.om_dev, pts[col], s=2, color=F.FAINT, alpha=0.35, lw=0, rasterized=True)
        ax.errorbar(xc[ok], g["mean"].values[ok], yerr=g["sem"].values[ok], fmt="o", ms=3.5, color=F.KICK, lw=0.8, capsize=0)
        xx = np.array([-0.9, 0.9])
        ax.plot(xx, FE[key][0] * xx, color=F.ZONE if FE[key][1] < 0.05 else F.SOFT, lw=1.0)
        ax.axhline(0, color=F.FAINT, lw=0.5)
        ax.set_xlim(-0.95, 0.95)
        lim = 6 if key == "entrances" else 1.0
        ax.set_ylim(-lim, lim)
        ax.set_xlabel("Session's floor speed minus the mouse's average (deg/s)")
        ax.set_ylabel(lab)
        ax.set_title("%+.2f per deg/s, %s" % (FE[key][0], F.pstr(FE[key][1])), fontsize=6.2, loc="left")
    F.put(fig, 0.75, y + 2.55,
          "Each session's count against its mouse's own average and its session number's average (a model with each mouse "
          "and each session as its own term), plotted against how far that session's floor ran from the mouse's usual speed "
          "(s.d. %.2f deg/s; %d sessions more than 0.3 off). Gray: sessions; blue: means in 0.2-deg/s bins with s.e.; line: the "
          "fitted slope. The same holds for shocks (%+.1f per deg/s, %s), time in the zone (%s) and path (%s)."
          % (CR["within_sd"], CR["within_n03"], FE["shocks"][0], F.pstr(FE["shocks"][1]), F.pstr(FE["time_in_zone_pct"][1]),
             F.pstr(FE["path_m"][1])), 7.0, size=6.2, color=F.SOFT)
    # b: 8/12/2026
    yb = y + 3.4
    N = CR["NAT"]
    tri = N["s4s5_trio"]
    F.letter(fig, 0.4, yb, "b", "On 8/12/2026 the floor sped up by 1 deg/s between s4 and s5: the three young Hom gained %d, %d and "
                                "%d entrances while the other mice lost %.1f on average (%s)" % (
                                    tri["1629"], tri["1633"], tri["1634"], -np.mean(N["s4s5_other"]), F.pstr(N["s4s5_p"])), width=7.6)
    ax = F.axes_in(fig, 0.75, yb + 0.35, 3.3, 1.75)
    aug = N["aug12"]
    cols = {"1629": "#7b2d8e", "1633": "#a564b8", "1634": "#4b1a57"}
    for m, g in aug.groupby("mouse"):
        g = g[g.session.between(1, 8)]
        ax.plot(g.session, g.entrances, color=cols[m], marker="o", ms=3, lw=1, label=m)
    ax.axvspan(4.5, 8.5, color="#f3e6c4", alpha=0.5, lw=0, zorder=0)
    ax.text(2.5, ax.get_ylim()[1] * 0.95, "floor about 2.3 deg/s", fontsize=5.8, ha="center", va="top", color=F.SOFT)
    ax.text(6.5, ax.get_ylim()[1] * 0.95, "about 3.4 deg/s", fontsize=5.8, ha="center", va="top", color="#8a6d1f")
    ax.set_xlabel("Session (day 1)")
    ax.set_ylabel("Entrances")
    ax.set_xticks(range(1, 9))
    ax.legend(frameon=False, fontsize=5.6, loc="center right", title="young Hom", title_fontsize=5.6)
    ax = F.axes_in(fig, 4.75, yb + 0.35, 2.9, 1.75)
    oth = N["s4s5_other"]
    ax.hist(oth, bins=np.arange(-15.5, 16, 1), color=F.FAINT, lw=0)
    for m, vv in tri.items():
        ax.axvline(vv, color=cols[m], lw=1.4)
        ax.text(vv + 0.3, ax.get_ylim()[1] * 0.9, m, fontsize=5.6, color=cols[m], rotation=90, va="top")
    ax.set_xlabel("Change in entrances from s4 to s5")
    ax.set_ylabel("Other mice")
    ax.set_title("The usual s4-to-s5 change, every other mouse", fontsize=6.0, loc="left")
    # c: 1649
    yc = yb + 2.85
    m9 = N["m1649"].set_index("session")
    tr1649 = CR["TR"][CR["TR"].mouse == "1649"].set_index("session")
    F.letter(fig, 0.4, yc, "c", "Mouse 1649 ran most of its s7 with the motor at 7 instead of 4 (about %.1f deg/s): %d entrances, its "
                                "most in any training session (s6 %d, s8 %d)" % (N["motor7_speed"], m9.loc[7, "entrances"],
                                                                                   m9.loc[6, "entrances"], m9.loc[8, "entrances"]),
             width=7.6)
    m9 = tr1649
    ax = F.axes_in(fig, 0.75, yc + 0.35, 3.3, 1.45)
    ax.bar(m9.index, m9.entrances, color=[F.ZONE if s == 7 else F.FAINT for s in m9.index], width=0.65)
    ax.set_xticks(list(m9.index))
    ax.set_xlabel("Session (1649, WT young)")
    ax.set_ylabel("Entrances")
    F.put(fig, 4.75, yc + 0.4,
          "The tracker logged the motor at 7 for 8 of the 10 minutes of 1649's s7 (stage speed check, page 3); the menu "
          "counted that session at the day's 5.3 deg/s. This mouse's entrances also climbed through day 1 before it, so one "
          "session of one mouse is an anecdote that agrees with (a) and (b), not proof on its own.",
          2.9, size=6.3, color=F.SOFT)
    F.save(fig, OUT, "03_same_mouse")


# ============================================================================ page 4: within one genotype
def page_within_wt():
    fig, y = F.page("Within one genotype, the floor speed alone moves the raw counts; per turn of the floor it does not",
                    "SPEED AS A CONFOUND · 3 · INSIDE ONE GENOTYPE", number=4)
    y += 0.3
    W = CR["WTC"]

    def wrho(meas, sk, scope="old WT"):
        r = W[(W.measure == meas) & (W.summary == sk) & (W.scope == scope)].iloc[0]
        return r.rho, r.p
    r1 = wrho("entrances", "d1")
    r2 = wrho("epr", "d1")
    F.letter(fig, 0.4, y, "a", "Among old WT alone, faster floors meant more day-1 entrances (rho %.2f, %s); per turn there is no "
                               "trend (rho %.2f, %s)" % (r1[0], F.pstr(r1[1]), r2[0], F.pstr(r2[1])), width=7.6)
    for k, (meas, lab) in enumerate((("entrances|d1", "Entrances a session, day 1"), ("epr|d1", "Entrances per turn, day 1"))):
        ax = F.axes_in(fig, 0.75 + k * 3.7, y + 0.35, 2.8, 1.8)
        v = PM[meas]
        ms = [m for m in ML if F.geno(m) == "WT"]
        for m in ms:
            F.scatter_mouse(ax, OMR[m], v[m], m, size=20)
        old = [m for m in ms if not F.young(m)]
        xx, yy, lo, hi = F.theil([OMR[m] for m in old], [v[m] for m in old])
        ax.plot(xx, yy, color=F.INK, lw=0.9)
        ax.fill_between(xx, lo, hi, color=F.INK, alpha=0.08, lw=0)
        ax.set_xlabel("Floor speed (deg/s)")
        ax.set_ylabel(lab)
        sk = meas.split("|")
        rr = wrho(sk[0], sk[1])
        ra = wrho(sk[0], sk[1], "WT")
        ax.set_title("old WT rho %+.2f, %s · all WT rho %+.2f, %s" % (rr[0], F.pstr(rr[1]), ra[0], F.pstr(ra[1])), fontsize=5.8,
                     loc="left")
    F.put(fig, 0.75, y + 2.6, "WT only: circles young (all on the fast floor of Oct-Nov 2026), squares old (slow 2026 floor and "
                              "fast 2024 floor). Line and band: Theil-Sen fit to the old WT with a bootstrap 95% band.",
          7.0, size=6.2, color=F.SOFT)
    # b: WT against WT
    yb = y + 3.15
    T = CR["WTWT"]
    t1 = T[(T.measure == "entrances") & (T.summary == "d1")].iloc[0]
    t2 = T[(T.measure == "epr") & (T.summary == "d1")].iloc[0]
    F.letter(fig, 0.4, yb, "b", "WT against WT: old WT on the fast 2024 floor had %.1f day-1 entrances, old WT on the slow 2026 "
                                "floor %.1f (%s), a gap as big as any genotype effect in the menu; per turn, %s" % (
                                    t1.mean_fast, t1.mean_slow, F.pstr(t1.p), F.pstr(t2.p)), width=7.6)
    oldwt = {m: ("fast" if m in X.F24 else "slow") for m in ML if F.geno(m) == "WT" and not F.young(m)}
    for k, (meas, lab, conf) in enumerate((("entrances|d1", "Entrances, day 1", True), ("shocks|d1", "Shocks, day 1", True),
                                           ("epr|d1", "Entrances per turn, day 1", False), ("spr|d1", "Shocks per turn, day 1", False))):
        ax = F.axes_in(fig, 0.75 + k * 1.82, yb + 0.4, 1.4, 1.65)
        v = PM[meas]
        rs = np.random.RandomState(k)
        for j, band in enumerate(("fast", "slow")):
            ms = [m for m in oldwt if oldwt[m] == band]
            ax.plot([j - 0.28, j + 0.28], [np.median([v[m] for m in ms])] * 2, color=F.INK, lw=1.2)
            for m in ms:
                F.scatter_mouse(ax, j + (rs.rand() - 0.5) * 0.35, v[m], m, size=16)
        p = S.two([v[m] for m in oldwt if oldwt[m] == "fast"], [v[m] for m in oldwt if oldwt[m] == "slow"])["p"]
        F.brackets(ax, [(0, 1, p)], max(v[m] for m in oldwt))
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["2024\n5.2 deg/s", "2026\n3.1 deg/s"], fontsize=5.6)
        ax.set_xlim(-0.6, 1.6)
        ax.tick_params(axis="x", length=0)
        ax.set_title("%s · %s" % (lab, F.pstr(p)), fontsize=5.8, loc="left")
        if conf:
            X.red(ax, "")
    X.red_legend(fig, 0.75, yb + 2.6)
    F.put(fig, 0.75, yb + 2.85, "Old WT only (2024: 10 mice; 2026: 5 mice, all virus-injected). The 2026 WT also differ in year "
                                "and injection, so this panel alone cannot name the floor; with (a) and page 3 it can.",
          7.0, size=6.2, color=F.SOFT)
    # c: the forest of within-WT correlations
    yc = yb + 3.45
    F.letter(fig, 0.4, yc, "c", "Across measures, raw counts and path rise with floor speed inside WT; per-turn measures do not",
             width=7.6)
    rows = [("entrances", "Entrances"), ("shocks", "Shocks"), ("time_in_zone_pct", "Time in the zone"), ("path_m", "Path in the room"),
            ("latency_first_entrance_s", "Time to first entrance (s)"), ("epr", "Entrances per turn"), ("spr", "Shocks per turn"),
            ("lat_turns", "Turns to first entrance")]
    ax = F.axes_in(fig, 2.6, yc + 0.35, 3.2, 1.75)
    for i, (meas, lab) in enumerate(rows):
        for j, (sk, mk) in enumerate((("d1", "o"), ("d2", "s"))):
            rr = W[(W.measure == meas) & (W.summary == sk) & (W.scope == "WT")].iloc[0]
            col = F.ZONE if rr.p < 0.05 else (F.KICK if CR["MEAS"][meas][2] == "per turn" else F.SOFT)
            ax.scatter(rr.rho, i + (j - 0.5) * 0.3, marker=mk, s=16, color=col, zorder=3)
        ax.text(-1.05, i, lab, fontsize=6.0, ha="right", va="center")
    ax.axvline(0, color=F.FAINT, lw=0.6)
    ax.set_xlim(-1, 1)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Spearman rho with floor speed, all 21 WT")
    ax.legend(handles=[Line2D([], [], ls="", marker="o", ms=4, color=F.SOFT, label="day 1"),
                       Line2D([], [], ls="", marker="s", ms=4, color=F.SOFT, label="day 2"),
                       Line2D([], [], ls="", marker="o", ms=4, color=F.ZONE, label="P < 0.05")],
              frameon=False, fontsize=5.6, loc="lower right")
    F.save(fig, OUT, "04_within_genotype")


# ============================================================================ page 5: young Hom 'beat' young WT
def page_young():
    fig, y = F.page("Young Hom 'beat' young WT on raw counts only because their floor turned about half as fast",
                    "SPEED AS A CONFOUND · 4 · THE YOUNG COMPARISON", number=5)
    y += 0.3
    YG = CR["YOUNG"]

    def yp(meas, sk):
        return YG[(YG.measure == meas) & (YG.summary == sk)].iloc[0]
    a1 = yp("shocks", "d1")
    F.letter(fig, 0.4, y, "a", "Raw, young Hom took a third of young WT's day-1 shocks (%.1f against %.1f, %s) and entered less on "
                               "both days" % (a1.mean_Hom, a1.mean_WT, F.pstr(a1.p)), width=7.6)
    young2 = ["WT young", "Hom young"]
    for k, (meas, lab) in enumerate((("shocks|d1", "Shocks, day 1"), ("entrances|d1", "Entrances, day 1"),
                                     ("entrances|d2", "Entrances, day 2"), ("time_in_zone_pct|d1", "Time in the zone, day 1 (%)"))):
        ax = F.axes_in(fig, 0.75 + k * 1.82, y + 0.4, 1.4, 1.65)
        X.group_dots(ax, PM[meas], groups=young2, labels=["WT\nyoung", "Hom\nyoung"], pairs=((0, 1),))
        ax.set_title(lab, fontsize=6.0, loc="left")
        X.red(ax, "")
    X.red_legend(fig, 0.75, y + 2.4)
    yb = y + 2.95
    b1, b2, b3 = yp("epr", "d1"), yp("epr", "d2"), yp("epr", "imp")
    F.letter(fig, 0.4, yb, "b", "Per turn of the floor the gap is gone: entrances per turn %s (day 1), %s (day 2), and both improved "
                                "alike (%s)" % (F.pstr(b1.p), F.pstr(b2.p), F.pstr(b3.p)), width=7.6)
    for k, (meas, lab) in enumerate((("epr|d1", "Entrances per turn, day 1"), ("epr|d2", "Entrances per turn, day 2"),
                                     ("epr|imp", "Per turn, day 2 minus day 1"), ("lat_turns|d1", "Turns to first entrance, day 1"))):
        ax = F.axes_in(fig, 0.75 + k * 1.82, yb + 0.4, 1.4, 1.65)
        X.group_dots(ax, PM[meas], groups=young2, labels=["WT\nyoung", "Hom\nyoung"], pairs=((0, 1),))
        p = S.two([PM[meas][m] for m in ML if X.grp(m) == "WT young"], [PM[meas][m] for m in ML if X.grp(m) == "Hom young"])["p"]
        ax.set_title("%s\n%s" % (lab, F.pstr(p)), fontsize=5.8, loc="left")
    yc = yb + 2.75
    tw = np.median([OMR[m] * 600 / 360 for m in ML if X.grp(m) == "WT young"])
    th = np.median([OMR[m] * 600 / 360 for m in ML if X.grp(m) == "Hom young"])
    F.letter(fig, 0.4, yc, "c", "In a 10-min session the floor carried a young WT around %.1f times and a young Hom %.1f times: "
                                "%.1f times the chances to be carried in" % (tw, th, tw / th), width=7.6)
    ax = F.axes_in(fig, 0.75, yc + 0.35, 3.2, 1.6)
    rs = np.random.RandomState(4)
    for k, g in enumerate(G6):
        ms = [m for m in ML if X.grp(m) == g]
        tv = [OMR[m] * 600 / 360 for m in ms]
        ax.plot([k - 0.3, k + 0.3], [np.median(tv)] * 2, color=F.INK, lw=1.2)
        for m, t_ in zip(ms, tv):
            F.scatter_mouse(ax, k + (rs.rand() - 0.5) * 0.36, t_, m, size=14)
    ax.set_xticks(range(6))
    ax.set_xticklabels([g.replace(" ", "\n") for g in G6], fontsize=5.8)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Floor turns per session")
    F.put(fig, 4.4, yc + 0.4,
          "A mouse that never moved would be carried into the zone once every turn. Real mice avoid, but on a faster floor they "
          "have to keep avoiding more often, and they slip more often (page 3). Dividing by the turns asks how often a mouse "
          "fails per chance, which is what 'learning' should mean when the chances differ. Young Hom still differ from young "
          "WT in year (2026 summer vs Oct-Nov) and injection (8 of 9 injected vs none).", 3.3, size=6.3, color=F.SOFT)
    F.save(fig, OUT, "05_young_comparison")


# ============================================================================ page 6: the verdict
def page_verdict():
    fig, y = F.page("Verdict: floor speed meets every test of a confounder; raw counts cannot be compared across cohorts",
                    "SPEED AS A CONFOUND · 5 · VERDICT", number=6)
    y += 0.3
    FE, N = CR["FE"], CR["NAT"]
    W = CR["WTC"]
    rw = W[(W.measure == "entrances") & (W.summary == "d1") & (W.scope == "old WT")].iloc[0]
    rows = [
        ("1. It differs between the groups compared", "Young Hom %.1f-%.1f vs young WT %.1f-%.1f deg/s, no overlap; six groups %s; "
         "speed travels with injection (rho %.2f) and young Hom (%.2f)" % (rng_of("Hom young") + rng_of("WT young") + (
             F.pstr(CR["kw_speed"]), CR["web"].loc["floor speed", "injected before AA"], CR["web"].loc["floor speed", "young Hom"])),
         "page 2", True),
        ("2. It changes the outcome with genotype held fixed", "Same mouse: %+.1f entrances per deg/s (%s). Old WT alone: rho %.2f "
         "(%s). Mid-day step on 8/12/2026: entrances rose at s5 (%s). 1649's motor-7 session: its worst." % (
             FE["entrances"][0], F.pstr(FE["entrances"][1]), rw.rho, F.pstr(rw.p), F.pstr(N["s4s5_p"])), "pages 3-4", True),
        ("3. Genotype cannot have caused it", "The motor setting logged 4 for every group; the floor's speed changed at the same "
         "clock time for every mouse on the floor (stage speed check, page 6)", "check p. 3, 6", True),
        ("4. Counting per turn removes it", "Same mouse per turn: %+.2f per deg/s (%s); WT rho for entrances per turn %.2f-%.2f"
         % (FE["epr"][0], F.pstr(FE["epr"][1]), W[(W.measure == "epr") & (W.scope == "WT")].rho.min(),
            W[(W.measure == "epr") & (W.scope == "WT")].rho.max()), "pages 3-5", True),
    ]
    F.letter(fig, 0.4, y, "a", "The four tests, and where each is shown", width=7.6)
    ax = F.axes_in(fig, 0.6, y + 0.25, 7.3, 2.4)
    ax.axis("off")
    yy = 0.97
    for lab, ev, where, ok in rows:
        ax.text(0, yy, "YES" if ok else "NO", fontsize=7.2, weight="bold", color=F.KICK if ok else F.ZONE, va="top",
                transform=ax.transAxes)
        ax.text(0.04, yy, F.wrap(lab, 2.3, 6.8), fontsize=6.8, weight="bold", va="top", transform=ax.transAxes)
        txt = F.wrap(ev, 3.9, 6.5)
        ax.text(0.37, yy, txt, fontsize=6.5, va="top", transform=ax.transAxes)
        ax.text(0.92, yy, where, fontsize=6.2, color=F.SOFT, va="top", transform=ax.transAxes)
        yy -= 0.07 * max(txt.count("\n") + 1, 2) + 0.07
    # b: which menu claims it touches
    yb = y + 3.0
    F.letter(fig, 0.4, yb, "b", "What it does to the menu's claims: the Hom shock advantages and the raw Hom age effect do not "
                                "survive counting per turn; the old Hom's failure to improve does", width=7.6)

    def p2(meas, a, b):
        v = PM[meas]
        return S.two([v[m] for m in ML if a(m) and np.isfinite(v.get(m, np.nan))], [v[m] for m in ML if b(m) and np.isfinite(v.get(m, np.nan))])["p"]
    wt = lambda m: F.geno(m) == "WT"  # noqa: E731
    hom = lambda m: F.geno(m) == "Hom"  # noqa: E731
    claims = [
        ("Hom fewer day-1 shocks than WT", "shocks|d1", "spr|d1", wt, hom, True),
        ("Young Hom fewer day-1 entrances than young WT", "entrances|d1", "epr|d1", lambda m: X.grp(m) == "WT young",
         lambda m: X.grp(m) == "Hom young", True),
        ("Old Hom more day-2 shocks than young Hom", "shocks|d2", "spr|d2", lambda m: X.grp(m) == "Hom young",
         lambda m: X.grp(m) == "Hom old", True),
        ("Hom improve less than WT (entrances)", "entrances|imp", "epr|imp", wt, hom, False),
        ("Old Hom improve less than old WT (same 2024 floor)", "entrances|imp", "epr|imp",
         lambda m: X.grp(m) == "WT old" and m in X.F24, lambda m: X.grp(m) == "Hom old", False),
    ]
    ax = F.axes_in(fig, 0.6, yb + 0.25, 7.3, 1.9)
    ax.axis("off")
    hx = [0, 0.42, 0.58, 0.74]
    for j, h in enumerate(["Claim", "Raw counts", "Per turn", "Read"]):
        ax.text(hx[j], 1, h, fontsize=6.4, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, (lab, mr, mt, a, b, conf) in enumerate(claims):
        yy = 0.84 - i * 0.16
        pr, pt = p2(mr, a, b), p2(mt, a, b)
        if pt < 0.05:
            read = "holds per turn"
        elif pr < 0.05:
            read = "gone per turn"
        else:
            read = "neither way"
        if conf:
            ax.add_patch(plt.Rectangle((hx[1] - 0.01, yy - 0.115), 0.15, 0.15, transform=ax.transAxes, color=X.RED_BG, lw=0))
        ax.text(hx[0], yy, lab, fontsize=6.4, va="top", transform=ax.transAxes)
        ax.text(hx[1], yy, F.pstr(pr) + " " + F.stars(pr), fontsize=6.4, va="top", transform=ax.transAxes,
                color=F.INK if pr < 0.05 else F.FAINT)
        ax.text(hx[2], yy, F.pstr(pt) + " " + F.stars(pt), fontsize=6.4, va="top", transform=ax.transAxes,
                color=F.INK if pt < 0.05 else F.FAINT)
        ax.text(hx[3], yy, read, fontsize=6.4, va="top", transform=ax.transAxes, weight="bold",
                color=X.RED_TX if read == "gone per turn" else F.KICK)
    F.put(fig, 0.6, yb + 2.25,
          "Generous two-group tests (Mann-Whitney / Welch / Student, smallest P), raw counts against the same counts divided by "
          "each session's floor turns. Red cell: the groups ran at different floor speeds. Improvement = day-2 minus day-1 "
          "mean of each mouse. Across all ages Hom improve less than WT raw but not per turn, because young Hom improve as "
          "much as young WT per turn; the deficit sits in the old Hom (supplement 'What can be rescued').", 7.3, size=6.1,
          color=F.SOFT)
    # c: replay
    yc = yb + 2.95
    R = CR["replay"]
    F.letter(fig, 0.4, yc, "c", "Avoidance is steered by the room, not the floor: replaying a mouse's own walking on a floor just "
                                "0.25-0.5 deg/s off doubles its entrances", width=7.6)
    ax = F.axes_in(fig, 0.75, yc + 0.35, 3.0, 1.5)
    xl = ["<0.1", "0.1-0.25", "0.25-0.5", "0.5-1", "1-2", "2-4"]
    ax.bar(np.arange(len(R)) - 0.18, R.own, width=0.34, color=F.FAINT, label="as run")
    ax.bar(np.arange(len(R)) + 0.18, R.rep, width=0.34, color=F.KICK, label="replayed")
    ax.set_xticks(range(len(R)))
    ax.set_xticklabels(xl, fontsize=5.8)
    ax.set_xlabel("Replay speed minus the real speed (deg/s)")
    ax.set_ylabel("Entrances a session")
    ax.legend(frameon=False, fontsize=5.8, loc="upper left")
    F.put(fig, 4.2, yc + 0.4,
          "Each session's walking on the floor (its room track turned back by the floor's speed) turned forward again at 2.5, "
          "3.5, 4.9 or 6.0 deg/s and counted with the tracker's rules (the counter matches the tracker's own counts, r %.3f). "
          "Mice time their walking to the room's zone, so moving the floor under the same walking scrambles the timing. "
          "Raw counts therefore cannot be rescaled from one floor speed to another by moving the mice's paths; they have to be "
          "compared per turn, within a speed, or with a fitted slope (supplement 'What can be rescued')." % CR["replay_check"][0],
          3.4, size=6.2, color=F.SOFT)
    F.save(fig, OUT, "06_verdict")


# ============================================================================ page 1: the menu
def page_front():
    fig = plt.figure(figsize=(8.5, 11))
    FE, N = CR["FE"], CR["NAT"]
    YG = CR["YOUNG"]
    a1 = YG[(YG.measure == "shocks") & (YG.summary == "d1")].iloc[0]
    b1 = YG[(YG.measure == "epr") & (YG.summary == "d1")].iloc[0]
    T = CR["WTWT"]
    t1 = T[(T.measure == "entrances") & (T.summary == "d1")].iloc[0]
    F.put(fig, 0.7, 0.8, "BARRY LAB · KCNT1 ACTIVE AVOIDANCE · FLOOR SPEED AS A CONFOUND, 2026-11-24", 7.2, size=7.2, color=F.KICK,
          weight="bold")
    F.put(fig, 0.7, 1.05, "Floor speed is a confounder: the evidence", 7.2, size=17, weight="bold")
    F.put(fig, 0.7, 1.5, "A supplement to the KCNT1 AA story menu. A battery of tests that pins down whether the floor's turning "
                         "speed, rather than genotype or age, made the raw differences. Its companion, 'What can be rescued', says "
                         "which comparisons survive.", 7.2, size=8, color=F.SOFT)
    F.put(fig, 0.72, 2.3, "The short version", 7.2, size=7.5, weight="bold")
    F.put(fig, 0.72, 2.55,
          "Floor speed passes every test of a confounder. It differs between the groups: young Hom ran at %.1f-%.1f deg/s and "
          "young WT at %.1f-%.1f, with no overlap, and slow floors also went with the 2026 runs and the injected mice. It "
          "changes the outcome with genotype held fixed: in the same mouse, each extra deg/s added %.1f entrances to a session "
          "(%s); when the floor sped up by 1 deg/s mid-day on 8/12/2026, the three young Hom running then gained entrances while "
          "every other mouse was improving (%s); and among old WT alone, the fast 2024 floor gave %.1f day-1 entrances against "
          "%.1f on the slow 2026 floor (%s). Genotype cannot have set it: the motor setting was the same for everyone. And "
          "counting entrances per turn of the floor removes it (same mouse: %s). The young Hom's raw advantage over young WT "
          "(day-1 shocks %.1f against %.1f, %s) disappears per turn (%s): they were carried around about half as often."
          % (rng_of("Hom young") + rng_of("WT young") + (FE["entrances"][0], F.pstr(FE["entrances"][1]), F.pstr(N["s4s5_p"]),
             t1.mean_fast, t1.mean_slow, F.pstr(t1.p), F.pstr(FE["epr"][1]), a1.mean_Hom, a1.mean_WT, F.pstr(a1.p), F.pstr(b1.p))),
          7.0, size=7.3)
    F.put(fig, 0.72, 4.65, "The pages", 7.2, size=7.5, weight="bold")
    rows = [("2", "Different floors", "Each mouse's floor speed by group; what travels with it; which comparisons share speeds.",
             "young Hom vs young WT: no overlap"),
            ("3", "Inside one mouse", "Same-mouse speed effect; the 8/12/2026 mid-day step; 1649's motor-7 session.",
             "%+.1f entrances per deg/s, %s" % (FE["entrances"][0], F.pstr(FE["entrances"][1]))),
            ("4", "Inside one genotype", "WT only: counts against speed; WT against WT across floors; every measure.",
             "old WT fast vs slow floor, %s" % F.pstr(t1.p)),
            ("5", "The young comparison", "Young Hom vs young WT raw, per turn, and in floor turns.", "raw %s, per turn %s" % (
                F.pstr(a1.p), F.pstr(b1.p))),
            ("6", "Verdict", "The four tests; the menu claims it touches; why paths cannot be moved to another speed.",
             "Hom shock advantages gone per turn")]
    ax = F.axes_in(fig, 0.7, 4.9, 7.3, 2.8)
    ax.axis("off")
    hx = [0, 0.05, 0.25, 0.68]
    for j, h in enumerate(["Page", "Story", "What it shows", "Best number"]):
        ax.text(hx[j], 1, h, fontsize=6.6, weight="bold", va="top", color=F.SOFT, transform=ax.transAxes)
    yy = 0.89
    for r in rows:
        cells = [r[0], F.wrap(r[1], 1.3, 6.8), F.wrap(r[2], 3.0, 6.8), F.wrap(r[3], 2.2, 6.8)]
        nl = max(c.count("\n") + 1 for c in cells)
        for j, c in enumerate(cells):
            ax.text(hx[j], yy, c, fontsize=6.8, va="top", weight="bold" if j == 1 else "normal", transform=ax.transAxes)
        yy -= 0.055 * nl + 0.06
        ax.plot([0, 1], [yy + 0.03, yy + 0.03], color=F.GRID, lw=0.6, transform=ax.transAxes)
    F.put(fig, 0.72, 7.95,
          "Floor speed throughout: the refined reading of the stage speed check (each session's half-hour reading about that "
          "day's true center of turn; a mouse's speed is the median of its sessions). Per turn = divided by the floor turns in "
          "the session (speed x 600 s / 360). Red background on a panel = the groups compared ran at different floor speeds. "
          "Exploratory: P values uncorrected. * P < 0.05, ** P < 0.01, *** P < 0.001.", 7.2, size=6.6, color=F.SOFT)
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, F.FOOT, fontsize=6.5, color=F.FAINT, ha="left", va="bottom")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "1", fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    F.save(fig, OUT, "01_menu")


def package():
    os.makedirs(DEST, exist_ok=True)
    for sub in ("pages", "tables", "code"):
        p = os.path.join(DEST, sub)
        if os.path.isdir(p):
            shutil.rmtree(p)
        os.makedirs(p)
    pdfs = sorted(glob.glob(os.path.join(OUT, "*.pdf")))
    for f in pdfs + sorted(glob.glob(os.path.join(OUT, "*.png"))):
        shutil.copy2(f, os.path.join(DEST, "pages"))
    doc = pymupdf.open()
    for f in pdfs:
        doc.insert_pdf(pymupdf.open(f))
    doc.save(os.path.join(DEST, "KCNT1_AA_Speed_Confound_112426.pdf"))
    tab = os.path.join(DEST, "tables")
    CR["WTC"].to_csv(os.path.join(tab, "speed_correlations_within_WT.csv"), index=False)
    CR["YOUNG"].to_csv(os.path.join(tab, "young_Hom_vs_young_WT_raw_and_per_turn.csv"), index=False)
    CR["WTWT"].to_csv(os.path.join(tab, "old_WT_fast_vs_slow_floor.csv"), index=False)
    pd.DataFrame([dict(measure=k, per_deg_s=v[0], p=v[1], se=v[2]) for k, v in CR["FE"].items()]).to_csv(
        os.path.join(tab, "same_mouse_speed_effects.csv"), index=False)
    CR["web"].to_csv(os.path.join(tab, "what_travels_with_speed_rho.csv"))
    mt = pd.DataFrame({"genotype": [F.geno(m) for m in ML], "age_group": [F.MICE[m]["age_group"] for m in ML],
                       "floor_speed_refined": [OMR[m] for m in ML], "turns_per_session": [OMR[m] * 600 / 360 for m in ML]}, index=ML)
    mt.index.name = "mouse"
    mt.to_csv(os.path.join(tab, "floor_speed_by_mouse.csv"))
    for f in ("e1_confound_rescue.py", "d1_replay.py", "crfig.py", "s3_confound_pages.py"):
        shutil.copy2(os.path.join(F.HERE, f), os.path.join(DEST, "code"))
    print("packaged", DEST)


if __name__ == "__main__":
    import sys
    fns = {"1": page_front, "2": page_who, "3": page_same_mouse, "4": page_within_wt, "5": page_young, "6": page_verdict,
           "pkg": package}
    for w in (sys.argv[1:] or ["1", "2", "3", "4", "5", "6", "pkg"]):
        fns[w]()
        print("done", w)
