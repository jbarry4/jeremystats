"""KCNT1 AA supplement (2026-11-24): what can be rescued despite the floor-speed confound, with the age question in
front. Seven pages -> out_resc/, packaged to Lab Figures/KCNT1_AA_Rescue_112426."""
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
OUT = os.path.join(F.HERE, "out_resc")
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1_AA_Rescue_112426"
F.FOOT = X.FOOT_RESC
CR, PM, OMR, F24 = X.CR, X.PM, X.OMR, X.F24
ML = X.ML
G6 = ["WT young", "WT old", "Het young", "Het old", "Hom young", "Hom old"]
BANDS = [("slow", 0, 4.0), ("medium", 4.0, 4.8), ("fast", 4.8, 99)]
R1, R2, R3, R4, MMC = CR["R1"], CR["R2"], CR["R3"], CR["R4"], CR["MMC"]
OLD24 = lambda m: X.grp(m) == "WT old" and m in F24  # noqa: E731
OLDH = lambda m: X.grp(m) == "Hom old"  # noqa: E731


def r1(meas, sk):
    return R1[(R1.measure == meas) & (R1.summary == sk)].iloc[0]


def r2(meas, sk):
    return R2[(R2.measure == meas) & (R2.summary == sk)].iloc[0]


def pair_dots(ax, v, title, a=OLD24, b=OLDH, labels=("WT old\n2024 floor", "Hom old"), red=False):
    rs = np.random.RandomState(5)
    va = {m: v[m] for m in ML if a(m) and np.isfinite(v.get(m, np.nan))}
    vb = {m: v[m] for m in ML if b(m) and np.isfinite(v.get(m, np.nan))}
    for j, d in enumerate((va, vb)):
        ax.plot([j - 0.28, j + 0.28], [np.median(list(d.values()))] * 2, color=F.INK, lw=1.2)
        for m, x in d.items():
            F.scatter_mouse(ax, j + (rs.rand() - 0.5) * 0.35, x, m, size=16)
    p = S.two(list(va.values()), list(vb.values()))["p"]
    F.brackets(ax, [(0, 1, p)], max(list(va.values()) + list(vb.values())))
    ax.set_xticks([0, 1])
    ax.set_xticklabels(labels, fontsize=5.6)
    ax.set_xlim(-0.6, 1.6)
    ax.tick_params(axis="x", length=0)
    ax.set_title("%s\n%s" % (title, F.pstr(p)), fontsize=5.8, loc="left")
    if red:
        X.red(ax, "")
    return p


# ============================================================================ page 2: what can still be compared
def page_map():
    fig, y = F.page("What can still be compared: old Hom against old WT on one floor; young against old only per turn or by "
                    "extrapolating", "RESCUE · 1 · THE MAP", number=2)
    y += 0.3
    F.letter(fig, 0.4, y, "a", "Every old Hom ran on the 2024 floor (4.8-5.5 deg/s) next to 10 old WT; no young Hom shares a floor "
                               "speed with any young WT or any old mouse", width=7.6)
    ax = F.axes_in(fig, 0.75, y + 0.3, 3.4, 2.1)
    ax.axis("off")
    cols = ["Group", "slow\n< 4.0", "medium\n4.0-4.8", "fast\n>= 4.8", "range (deg/s)"]
    cx = [0, 0.3, 0.47, 0.64, 0.8]
    for j, c in enumerate(cols):
        ax.text(cx[j], 1, c, fontsize=6.2, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, g in enumerate(G6):
        yy = 0.78 - i * 0.13
        v = CR["groups"][g]
        ax.text(0, yy, g, fontsize=6.6, va="top", transform=ax.transAxes, color=F.GCOL[g.split()[0]], weight="bold")
        for j, (nm, lo, hi) in enumerate(BANDS):
            n = sum(1 for x in v if lo <= x < hi)
            if n:
                ax.add_patch(plt.Rectangle((cx[j + 1] - 0.01, yy - 0.1), 0.13, 0.11, transform=ax.transAxes,
                                           color=F.GCOL[g.split()[0]], alpha=0.18, lw=0))
            ax.text(cx[j + 1] + 0.05, yy, str(n) if n else "-", fontsize=6.6, va="top", ha="center", transform=ax.transAxes)
        ax.text(cx[4], yy, "%.1f-%.1f" % (min(v), max(v)), fontsize=6.4, va="top", transform=ax.transAxes)
    F.put(fig, 4.5, y + 0.35,
          "Mice per genotype x age group in each floor-speed band (refined reading; a mouse's speed is the median of its 17 "
          "sessions). The fast band holds every old Hom and the 2024 old WT (5.2 deg/s on average for both), so that one "
          "comparison needs no correction at all. Young Hom sit alone in the slow band; young WT and young Het (bar one) "
          "alone in the fast band after the October 2026 repair.", 3.3, size=6.3, color=F.SOFT)
    # b: the routes
    yb = y + 2.75
    F.letter(fig, 0.4, yb, "b", "Five routes, and what each can and cannot answer", width=7.6)
    rows = [("1  Same floor", "Compare only mice that ran at the same speed: old Hom vs the 2024 old WT (page 4).",
             "Old Hom vs old WT", False),
            ("2  Per turn", "Divide counts by the floor turns in the session. Speed-free within WT and within mice (page 3); "
                            "lets young and old be compared (page 5).", "Young vs old, all genotypes", True),
            ("3  Age within adults", "Age 19-46 weeks among old mice on the one 2024 floor (page 6).", "Does the Hom gap grow with age?",
             False),
            ("4  Extrapolate", "Move each mouse to one speed along a fitted slope (the story menu's way), with three slopes "
                               "(page 6).", "Raw counts, young vs old", True),
            ("5  Replay", "Move each mouse's own walking to another floor speed. Fails: avoidance is timed to the room "
                          "(confound supplement, page 6).", "nothing", True)]
    ax = F.axes_in(fig, 0.6, yb + 0.2, 7.3, 2.3)
    ax.axis("off")
    hx = [0, 0.2, 0.72]
    for j, h in enumerate(["Route", "How", "Answers"]):
        ax.text(hx[j], 1, h, fontsize=6.4, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    yy = 0.88
    for lab, how, ans, red in rows:
        t = F.wrap(how, 3.6, 6.4)
        nl = t.count("\n") + 1
        if red:
            ax.add_patch(plt.Rectangle((hx[2] - 0.01, yy - 0.045 * nl - 0.02), 0.28, 0.045 * nl + 0.04, transform=ax.transAxes,
                                       color=X.RED_BG, lw=0))
        ax.text(hx[0], yy, lab, fontsize=6.6, weight="bold", va="top", transform=ax.transAxes)
        ax.text(hx[1], yy, t, fontsize=6.4, va="top", transform=ax.transAxes)
        ax.text(hx[2], yy, F.wrap(ans, 1.9, 6.4), fontsize=6.4, va="top", transform=ax.transAxes)
        yy -= 0.05 * max(nl, 1) + 0.075
    X.red_legend(fig, 0.75, yb + 2.55)
    # c: coverage
    yc = yb + 3.15
    cv = CR["coverage"]
    F.letter(fig, 0.4, yc, "c", "Every session got a floor speed, but not always from its own mouse: %d of %d had rides of their "
                                "own, and the rest borrowed from mice running within the half hour" % (cv["own_any"], cv["sessions"]),
             width=7.6)
    ax = F.axes_in(fig, 1.55, yc + 0.35, 2.4, 1.3)
    cats = [("5+ rides of its own", cv["own_5"]), ("1-4 of its own", cv["own_any"] - cv["own_5"]),
            ("none of its own", cv["sessions"] - cv["own_any"])]
    ax.barh(range(3), [c[1] for c in cats], color=[F.KICK, "#7fb1c4", F.FAINT], height=0.6)
    for i, (lab, n) in enumerate(cats):
        ax.text(n + 8, i, "%d" % n, va="center", fontsize=6)
    ax.set_yticks(range(3))
    ax.set_yticklabels([c[0] for c in cats], fontsize=6.2)
    ax.invert_yaxis()
    ax.set_xlabel("Training and habituation sessions")
    F.put(fig, 4.3, yc + 0.4,
          "A session's speed is read from every ride of every mouse on the floor within 30 minutes of it (%d of %d sessions "
          "had at least 15 such readings); the rest take the 15 readings nearest in time. Mice run three or four at a time, "
          "interleaved, so the floor is sampled every few minutes even when one mouse never sits still. The speeds are those "
          "of the stage speed check (refined reading)." % (cv["halfhour"], cv["sessions"]), 3.4, size=6.3, color=F.SOFT)
    F.save(fig, OUT, "02_map")


# ============================================================================ page 3: entrances per turn
def page_per_turn():
    fig, y = F.page("Raw entrances rise with floor speed; entrances per turn of the floor do not",
                    "RESCUE · 2 · A COUNT THAT IGNORES FLOOR SPEED", number=3)
    y += 0.3
    W = CR["WTC"]
    FE = CR["FE"]
    F.letter(fig, 0.4, y, "a", "Entrances per turn show no link to floor speed in WT (rho %.2f) or inside a mouse (%s); raw "
                               "entrances do (same mouse %+.1f per deg/s, %s)" % (
                                   W[(W.measure == "epr") & (W.summary == "d1") & (W.scope == "WT")].rho.iloc[0],
                                   F.pstr(FE["epr"][1]), FE["entrances"][0], F.pstr(FE["entrances"][1])), width=7.6)
    for r_, sk in enumerate(("d1", "d2")):
        for c_, (meas, lab) in enumerate((("entrances", "Entrances a session"), ("epr", "Entrances per turn"))):
            ax = F.axes_in(fig, 0.75 + c_ * 3.7, y + 0.4 + r_ * 2.15, 2.8, 1.6)
            v = PM["%s|%s" % (meas, sk)]
            for m in ML:
                F.scatter_mouse(ax, OMR[m], v[m], m, size=14)
            for g in ("WT", "Het", "Hom"):
                ms = [m for m in ML if F.geno(m) == g]
                b, a_ = np.polyfit([OMR[m] for m in ms], [v[m] for m in ms], 1)
                xx = np.array([min(OMR[m] for m in ms), max(OMR[m] for m in ms)])
                ax.plot(xx, a_ + b * xx, color=F.GCOL[g], lw=0.9, ls="--" if g == "Hom" else "-")
            ttl = []
            for g in ("WT", "Het", "Hom"):
                ms = [m for m in ML if F.geno(m) == g]
                rr = st.spearmanr([OMR[m] for m in ms], [v[m] for m in ms])
                ttl.append("%s %+.2f%s" % (g, rr[0], F.stars(rr[1])))
            ax.set_title("%s, day %s · rho %s" % (lab, sk[1], ", ".join(ttl)), fontsize=5.8, loc="left")
            ax.set_xlabel("Floor speed (deg/s)")
            ax.set_ylabel(lab)
    F.legend_mice(fig, 0.75, y + 4.6, extra=True, speed=False)
    F.put(fig, 0.75, y + 4.9,
          "One dot per mouse; lines: straight fits per genotype. The Hom line is dashed because inside Hom, floor speed and age "
          "are the same thing (young Hom slow, old Hom fast), so their slope mixes the two. WT and Het span the speeds within "
          "an age group, and they show the floor's own effect: raw entrances up, per-turn entrances flat.", 7.0, size=6.2,
          color=F.SOFT)
    # b: which measures are speed-free
    yb = y + 5.6
    F.letter(fig, 0.4, yb, "b", "Speed-free: entrances and shocks per turn, turns to the first entrance, and every day-2 minus day-1 "
                                "change; raw counts, time in the zone and path are not", width=7.6)
    rows = [("entrances", "Entrances"), ("shocks", "Shocks"), ("path_m", "Path in the room"), ("time_in_zone_pct", "Time in the zone"),
            ("epr", "Entrances per turn"), ("spr", "Shocks per turn"), ("lat_turns", "Turns to first entrance"),
            ("maxav_turns", "Longest avoidance (turns)")]
    ax = F.axes_in(fig, 0.6, yb + 0.25, 7.3, 2.1)
    ax.axis("off")
    hx = [0, 0.25, 0.39, 0.53, 0.67, 0.82]
    for j, h in enumerate(["Measure", "WT rho, day 1", "WT rho, day 2", "WT rho, day 2 - 1", "Same mouse, per deg/s", "Speed-free?"]):
        ax.text(hx[j], 1, h, fontsize=6.0, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, (meas, lab) in enumerate(rows):
        yy = 0.86 - i * 0.105
        rr = [W[(W.measure == meas) & (W.summary == sk) & (W.scope == "WT")].iloc[0] for sk in ("d1", "d2", "imp")]
        fe = FE.get(meas, (np.nan, np.nan))
        free = all(x.p >= 0.05 for x in rr[:2]) and (not np.isfinite(fe[1]) or fe[1] >= 0.05)
        cells = [lab] + ["%+.2f%s" % (x.rho, (" " + F.stars(x.p)) if x.p < 0.05 else "") for x in rr] + [
            "%+.2f, %s" % (fe[0], F.pstr(fe[1])), "yes" if free else "no"]
        for j, c in enumerate(cells):
            col = F.INK
            if j == 5:
                col = F.KICK if free else X.RED_TX
            ax.text(hx[j], yy, c, fontsize=6.3, va="top", transform=ax.transAxes, color=col, weight="bold" if j == 5 else "normal")
    F.save(fig, OUT, "03_per_turn")


# ============================================================================ page 4: route 1, the same floor
def page_same_floor():
    fig, y = F.page("Same floor: old Hom start as well as old WT but do not improve from day 1 to day 2",
                    "RESCUE · 3 · OLD HOM AGAINST OLD WT, ONE FLOOR SPEED", number=4)
    y += 0.3
    e, s_ = r1("epr", "imp"), r1("shocks", "imp")
    F.letter(fig, 0.4, y, "a", "On the 2024 floor (5.2 deg/s for both groups), old Hom started at least as well; old WT cut their entrances per turn by %.2f from day "
                               "1 to day 2 and old Hom by %.2f (%s); shocks fell by %.1f against %.1f (%s)" % (
                                   -e.mean_WT, -e.mean_Hom, F.pstr(e.p), -s_.mean_WT, -s_.mean_Hom, F.pstr(s_.p)), width=7.6)
    panels = [("epr|d1", "Entrances per turn, day 1"), ("epr|d2", "Entrances per turn, day 2"), ("epr|imp", "Per turn, day 2 - day 1"),
              ("shocks|d1", "Shocks, day 1"), ("shocks|d2", "Shocks, day 2"), ("shocks|imp", "Shocks, day 2 - day 1")]
    for k, (meas, lab) in enumerate(panels):
        r, c = divmod(k, 3)
        ax = F.axes_in(fig, 0.75 + c * 2.45, y + 0.45 + r * 2.05, 1.6, 1.45)
        pair_dots(ax, PM[meas], lab)
    X.genotype_legend(fig, 0.75, y + 4.4)
    # b: curves
    yb = y + 4.95
    F.letter(fig, 0.4, yb, "b", "Across the 16 sessions, old WT's entrances per turn fall and old Hom's stay flat (per-mouse "
                                "learning slopes %s)" % F.pstr(MMC["epr_slope_tests"]["p_old24"]), width=7.6)
    ax = F.axes_in(fig, 0.75, yb + 0.35, 3.4, 1.7)
    TR = CR["TR"]
    for lab, pred, col in (("WT old, 2024 floor", OLD24, F.GCOL["WT"]), ("Hom old", OLDH, F.GCOL["Hom"])):
        d = TR[TR.mouse.map(pred)].groupby("session").epr.agg(["mean", "sem"])
        ax.plot(d.index, d["mean"], color=col, lw=1.3, marker="o", ms=2.5, label=lab)
        ax.fill_between(d.index, d["mean"] - d["sem"], d["mean"] + d["sem"], color=col, alpha=0.15, lw=0)
    ax.axvline(8.5, color=F.FAINT, lw=0.5)
    ax.set_xticks([1, 4, 8, 9, 12, 16])
    ax.set_xlabel("Session")
    ax.set_ylabel("Entrances per turn")
    ax.legend(frameon=False, fontsize=5.8, loc="upper right")
    # c: other ways to test it
    yc = yb + 0.35
    rows = [("entrances", "Entrances"), ("shocks", "Shocks"), ("time_in_zone_pct", "Time in the zone"), ("epr", "Entrances per turn"),
            ("spr", "Shocks per turn"), ("maxav_turns", "Longest avoidance (turns)")]
    pairs = CR["pairs"]
    ax = F.axes_in(fig, 4.55, yc, 3.4, 1.9)
    ax.axis("off")
    hx = [0, 0.4, 0.6, 0.8]
    for j, h in enumerate(["Day 2 - day 1", "all mice", "same cohort", "6 pairs"]):
        ax.text(hx[j], 1, h, fontsize=6.0, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, (meas, lab) in enumerate(rows):
        r = r1(meas, "imp")
        v = PM[meas + "|imp"]
        same_dir = sum(1 for h, w in pairs if (v[h] - v[w]) * np.sign(r.mean_Hom - r.mean_WT) > 0)
        yy = 0.84 - i * 0.125
        for j, c in enumerate([lab, F.pstr(r.p), F.pstr(r.p_cohort), "%d of 6" % same_dir]):
            ax.text(hx[j], yy, c, fontsize=6.1, va="top", transform=ax.transAxes,
                    color=F.INK if (j == 0 or j == 3 or (j == 1 and r.p < 0.05) or (j == 2 and r.p_cohort < 0.05)) else F.FAINT)
    crit = R1[R1.measure == "criterion"].iloc[0]
    F.put(fig, 0.75, yc + 2.15,
          "'Same cohort': van Elteren test inside the four 2024 cohorts that had both genotypes (Mar, May, Jul, Oct). '6 pairs': "
          "each old Hom against the old WT nearest in floor speed (same cohort first); six pairs cannot reach P < 0.05 unless "
          "all six agree, so the count of pairs leaning the menu's way is shown. Time to criterion on this floor: old Hom "
          "reached it sooner (%s), because their day 1 was already good. Old Hom also differ from these WT in nothing measured "
          "but genotype: same year, floor, weeks and no injections." % F.pstr(crit.p), 7.2, size=6.2, color=F.SOFT)
    F.save(fig, OUT, "04_same_floor")


# ============================================================================ page 5: route 2, per turn across ages
def page_age():
    st_e, st_s = MMC["epr_slope_tests"], MMC["spr_slope_tests"]
    fig, y = F.page("Per turn, the Hom learning deficit belongs to the old Hom: young Hom learn like young WT",
                    "RESCUE · 4 · YOUNG AND OLD, PER TURN", number=5)
    y += 0.3
    e = r2("epr", "imp")
    F.letter(fig, 0.4, y, "a", "Day 2 minus day 1, per turn: young Hom improved as much as young WT (%s), old Hom far less than old "
                               "WT (%s); the difference between the two gaps, %s" % (
                                   F.pstr(e.p_young), F.pstr(e.p_old), F.pstr(e.p_boot)), width=7.6)
    for k, (meas, lab) in enumerate((("epr|imp", "Entrances per turn, day 2 - day 1"), ("spr|imp", "Shocks per turn, day 2 - day 1"))):
        ax = F.axes_in(fig, 0.75 + k * 3.7, y + 0.45, 2.9, 1.8)
        X.group_dots(ax, PM[meas], pairs=((0, 1), (2, 3)), ylabel=lab)
        ax.axhline(0, color=F.FAINT, lw=0.5, zorder=0)
        rr = r2(*meas.split("|"))
        ax.set_title("young pair %s · old pair %s\nthe two gaps differ by %.2f (95%% CI %.2f to %.2f), %s" % (
            F.pstr(rr.p_young), F.pstr(rr.p_old), rr.did, rr.did_lo, rr.did_hi, F.pstr(rr.p_boot)), fontsize=5.6, loc="left")
        X.red(ax, "young and old ran at different floor speeds")
    X.genotype_legend(fig, 0.75, y + 2.75)
    X.red_legend(fig, 0.75, y + 3.0)
    # b: curves
    yb = y + 3.65
    F.letter(fig, 0.4, yb, "b", "Learning curves per turn: the two young groups fall together; old WT fall, old Hom do not", width=7.6)
    cur = MMC["epr_curves"]
    for k, age in enumerate(("young", "old")):
        ax = F.axes_in(fig, 0.75 + k * 3.7, yb + 0.35, 2.9, 1.55)
        for g in ("WT", "Hom"):
            d = cur[(cur.geno == g) & (cur.age == age)]
            if age == "old" and g == "WT":
                TR = CR["TR"]
                d2 = TR[TR.mouse.map(OLD24)].groupby("session").epr.agg(["mean", "sem"]).reset_index()
                ax.plot(d2.session, d2["mean"], color=F.GCOL[g], lw=0.8, ls=":", label="WT old, 2024 floor only")
            ax.plot(d.session, d["mean"], color=F.GCOL[g], lw=1.3, marker="o", ms=2.5, label="%s %s" % (g, age))
            ax.fill_between(d.session, d["mean"] - d["sem"], d["mean"] + d["sem"], color=F.GCOL[g], alpha=0.15, lw=0)
        ax.axvline(8.5, color=F.FAINT, lw=0.5)
        ax.set_ylim(0, 2.6)
        ax.set_xticks([1, 4, 8, 9, 12, 16])
        ax.set_xlabel("Session")
        ax.set_ylabel("Entrances per turn")
        ax.legend(frameon=False, fontsize=5.6, loc="upper right")
        ax.set_title("Young mice" if age == "young" else "Old mice", fontsize=6.3, loc="left")
    # c: slopes and models
    yc = yb + 2.7
    mm_e, mm_s = MMC["epr"]["hom:old:sc"], MMC["spr"]["hom:old:sc"]
    F.letter(fig, 0.4, yc, "c", "Learning slopes per turn: old Hom against old WT %s, young Hom against young WT %s; Hom x age %s "
                                "(entrances per turn) and %s (shocks per turn)" % (
                                    F.pstr(st_e["p_old"]), F.pstr(st_e["p_young"]), F.pstr(st_e["p_int"]), F.pstr(st_s["p_int"])),
             width=7.6)
    ax = F.axes_in(fig, 0.75, yc + 0.4, 2.9, 1.75)
    sl = {m: v * 7.5 for m, v in MMC["epr_slopes"].items()}
    X.group_dots(ax, sl, pairs=((0, 1), (2, 3)), ylabel="Change in entrances per turn\nfrom s1 to s16 (fitted)")
    ax.axhline(0, color=F.FAINT, lw=0.5, zorder=0)
    X.red(ax, "young and old ran at different floor speeds")
    ax = F.axes_in(fig, 4.45, yc + 0.35, 3.45, 1.9)
    ax.axis("off")
    rows = [("Entrances per turn", "slopes per mouse", st_e["p_young"], st_e["p_old"], st_e["p_int"]),
            ("", "mixed model, s1-s16", np.nan, np.nan, mm_e[1]),
            ("Shocks per turn", "slopes per mouse", st_s["p_young"], st_s["p_old"], st_s["p_int"]),
            ("", "mixed model, s1-s16", np.nan, np.nan, mm_s[1]),
            ("Entrances (raw)", "slopes per mouse", MMC["entrances_slope_tests"]["p_young"], MMC["entrances_slope_tests"]["p_old"],
             MMC["entrances_slope_tests"]["p_int"])]
    hx = [0, 0.3, 0.58, 0.73, 0.88]
    for j, h in enumerate(["Measure", "Test", "young\nHom-WT", "old\nHom-WT", "Hom x\nage"]):
        ax.text(hx[j], 1, h, fontsize=5.8, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, row in enumerate(rows):
        yy = 0.76 - i * 0.13
        for j, c in enumerate(row):
            txt = c if j < 2 else ("" if not np.isfinite(c) else F.pstr(c).replace("P ", ""))
            col = F.INK if (j < 2 or (np.isfinite(c) and c < 0.05)) else F.FAINT
            ax.text(hx[j], yy, txt, fontsize=6.0, va="top", transform=ax.transAxes, color=col)
    F.put(fig, 4.45, yc + 2.0,
          "Slopes: each mouse's straight-line fit over s1-s16. Mixed model: hom x old x session with a random intercept and "
          "slope per mouse. Per turn removes the floor's effect (page 3), but young and old still differ in year and "
          "injection (8 of 9 young Hom injected).", 3.45, size=5.9, color=F.SOFT)
    F.save(fig, OUT, "05_young_and_old")


# ============================================================================ page 6: routes 3 and 4
def page_adults_extrap():
    fig, y = F.page("Two more routes: age within adults on one floor shows nothing; extrapolating raw counts gives a Hom age "
                    "effect only on improvement", "RESCUE · 5 · AGE WITHIN ADULTS, AND EXTRAPOLATION", number=6)
    y += 0.3
    r = R3[(R3.measure == "epr") & (R3.summary == "imp")].iloc[0]
    F.letter(fig, 0.4, y, "a", "Among old mice on the 2024 floor (19-46 weeks), older age did not widen the Hom deficit (Hom x age "
                               "in weeks %s)" % F.pstr(r.p_int), width=7.6)
    for k, (meas, lab) in enumerate((("epr|imp", "Entrances per turn, day 2 - day 1"), ("epr|d2", "Entrances per turn, day 2"))):
        ax = F.axes_in(fig, 0.75 + k * 3.7, y + 0.4, 2.9, 1.7)
        v = PM[meas]
        for g, pred in (("WT", OLD24), ("Hom", OLDH)):
            ms = [m for m in ML if pred(m)]
            for m in ms:
                F.scatter_mouse(ax, F.MICE[m]["age_wk"], v[m], m, size=18)
                ax.text(F.MICE[m]["age_wk"] + 0.4, v[m], m, fontsize=4.6, color=F.SOFT, va="center")
            b, a_ = np.polyfit([F.MICE[m]["age_wk"] for m in ms], [v[m] for m in ms], 1)
            xx = np.array([18, 47])
            ax.plot(xx, a_ + b * xx, color=F.GCOL[g], lw=0.9)
        rr = R3[(R3.measure == meas.split("|")[0]) & (R3.summary == meas.split("|")[1])].iloc[0]
        ax.set_title("%s · Hom x age %s" % (lab, F.pstr(rr.p_int)), fontsize=5.8, loc="left")
        ax.set_xlabel("Age at AA (weeks)")
        ax.set_ylabel(lab.split(",")[0])
    F.put(fig, 0.75, y + 2.5,
          "Old WT on the 2024 floor (gray) and old Hom (purple), one floor speed, no injections. Ages cluster by cohort (the "
          "May 2024 cohort is 35-46 weeks), so this tests cohorts as much as age; six Hom cannot carry a slope.",
          7.0, size=6.2, color=F.SOFT)
    # b: extrapolation (red)
    yb = y + 3.15
    d2p = R4[(R4.measure == "shocks") & (R4.summary == "d2")].p_young_vs_old_Hom
    imp = R4[(R4.measure == "shocks") & (R4.summary == "imp")].p_young_vs_old_Hom
    F.letter(fig, 0.4, yb, "b", "Extrapolating raw counts to one floor speed: old Hom take no more day-2 shocks than young Hom "
                                "(P %.2f-%.2f); on improvement they trail young Hom (P %.3f-%.3f across the three slopes)" % (
                                    d2p.min(), d2p.max(), imp.min(), imp.max()), width=7.6)
    ax = F.axes_in(fig, 0.75, yb + 0.4, 2.4, 1.9)
    ex = CR["extrap"]
    rs = np.random.RandomState(3)
    for k, g in enumerate(G6):
        ms = [m for m in ML if X.grp(m) == g]
        for m in ms:
            F.scatter_mouse(ax, k + (rs.rand() - 0.5) * 0.35, ex[m], m, size=14)
    ax.axhline(0, color=F.INK, lw=0.6)
    wy = CR["groups"]["WT young"]
    ax.axhspan(min(wy) - np.median(list(OMR.values())), max(wy) - np.median(list(OMR.values())), color=F.GCOL["WT"], alpha=0.12, lw=0)
    ax.set_xticks(range(6))
    ax.set_xticklabels([g.replace(" ", "\n") for g in G6], fontsize=5.6)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Distance moved to one speed (deg/s)")
    ax.set_title("How far each mouse is moved", fontsize=6.0, loc="left")
    X.red(ax, "")
    ax = F.axes_in(fig, 3.6, yb + 0.35, 4.3, 2.1)
    ax.axis("off")
    hx = [0, 0.3, 0.6, 0.8]
    for j, h in enumerate(["Measure", "Slope from", "old vs young\nHom", "Hom x age"]):
        ax.text(hx[j], 1, h, fontsize=5.9, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    sub = R4[R4.measure.isin(["shocks", "entrances"]) & R4.summary.isin(["d2", "imp"])]
    for i, rr in enumerate(sub.itertuples()):
        yy = 0.8 - i * 0.068
        lab = ("%s, %s" % ("Shocks" if rr.measure == "shocks" else "Entrances", "day 2" if rr.summary == "d2" else "day 2 - day 1")
               if i % 3 == 0 else "")
        for j, c in enumerate([lab, rr.slope_source, F.pstr(rr.p_young_vs_old_Hom), F.pstr(rr.p_int)]):
            p = rr.p_young_vs_old_Hom if j == 2 else (rr.p_int if j == 3 else 0)
            ax.text(hx[j], yy, c, fontsize=5.8, va="top", transform=ax.transAxes, color=F.INK if (j < 2 or p < 0.05) else F.FAINT)
    ax.add_patch(plt.Rectangle((0.58, 0.0), 0.42, 0.84, transform=ax.transAxes, color=X.RED_BG, lw=0, zorder=0))
    F.put(fig, 0.75, yb + 2.75,
          "Each mouse moved to %.1f deg/s (the median) along a slope: shared by the genotypes across mice (the story menu's), "
          "WT mice only, or the same-mouse slope across sessions (page 3 of the confound supplement; zero for day-2 minus day-1 "
          "changes, which are within-mouse already). Left: how far each mouse is moved; the band marks where young WT actually "
          "ran. Young Hom are moved 1.3-2.0 deg/s through a range no young mouse of another genotype covered, so every number "
          "in red rests on the slope being right out there." % np.median(list(OMR.values())), 7.2, size=6.2, color=F.SOFT)
    F.save(fig, OUT, "06_adults_and_extrapolation")


# ============================================================================ page 7: the scoreboard
def page_score():
    fig, y = F.page("Scoreboard: old Hom fail to improve, on the same floor and per turn; nothing shows old Hom performing "
                    "worse outright", "RESCUE · 6 · SCOREBOARD", number=7)
    y += 0.3
    st_e, st_s = MMC["epr_slope_tests"], MMC["spr_slope_tests"]
    F.letter(fig, 0.4, y, "a", "Each age claim, route by route (P values; red cells = groups on different floor speeds)", width=7.6)

    def r4(meas, sk, src):
        s = R4[(R4.measure == meas) & (R4.summary == sk) & (R4.slope_source == src)]
        return s.iloc[0]
    cols = ["Same floor\n(2024, old only)", "Same cohort", "Per turn,\nall mice", "Per-turn\nslopes / model", "Extrapolated\n(menu's slope)"]
    red_cols = {2, 3, 4}
    claims = [
        ("Old Hom improve less than old WT\n(day 2 - day 1)", [r1("epr", "imp").p, r1("epr", "imp").p_cohort, r2("epr", "imp").p_old,
                                                                st_e["p_old"], np.nan], [0, 0, 0, 1, 0]),
        ("Old Hom improve less than old WT\n(shocks)", [r1("shocks", "imp").p, r1("shocks", "imp").p_cohort, r2("spr", "imp").p_old,
                                                        st_s["p_old"], np.nan], [0, 0, 0, 1, 0]),
        ("Hom deficit larger in old than in young\n(Hom x age)", [np.nan, np.nan, r2("epr", "imp").p_boot,
                                                                  min(st_e["p_int"], MMC["epr"]["hom:old:sc"][1]),
                                                                  r4("entrances", "imp", "shared by the genotypes").p_int], [0, 0, 1, 1, 1]),
        ("Young Hom differ from young WT", [np.nan, np.nan, r2("epr", "imp").p_young, st_e["p_young"],
                                            np.nan], [0, 0, 1, 1, 0]),
        ("Old Hom worse than old WT on day 2", [r1("epr", "d2").p, r1("epr", "d2").p_cohort, r2("epr", "d2").p_old, np.nan,
                                                np.nan], [0, 0, 0, 0, 0]),
        ("Old Hom more day-2 shocks than young Hom", [np.nan, np.nan,
                                                      S.two([PM["spr|d2"][m] for m in ML if X.grp(m) == "Hom young"],
                                                            [PM["spr|d2"][m] for m in ML if X.grp(m) == "Hom old"])["p"], np.nan,
                                                      r4("shocks", "d2", "shared by the genotypes").p_young_vs_old_Hom], [0, 0, 1, 0, 1]),
        ("Old Hom reach criterion sooner than old WT", [R1[R1.measure == "criterion"].p.iloc[0], np.nan, np.nan, np.nan, np.nan],
         [0, 0, 0, 0, 0]),
    ]
    ax = F.axes_in(fig, 0.5, y + 0.25, 7.5, 4.2)
    ax.axis("off")
    cx = [0, 0.4, 0.52, 0.64, 0.76, 0.88]
    for j, c in enumerate(cols):
        ax.text(cx[j + 1], 1, c, fontsize=6.0, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, (lab, ps, _flag) in enumerate(claims):
        yy = 0.86 - i * 0.12
        ax.text(0, yy, lab, fontsize=6.4, va="top", transform=ax.transAxes, linespacing=1.15)
        for j, p in enumerate(ps):
            if j in red_cols and np.isfinite(p):
                ax.add_patch(plt.Rectangle((cx[j + 1] - 0.01, yy - 0.06), 0.115, 0.075, transform=ax.transAxes, color=X.RED_BG, lw=0))
            txt = "-" if not np.isfinite(p) else (F.pstr(p).replace("P ", "") + (" " + F.stars(p) if p < 0.05 else ""))
            ax.text(cx[j + 1], yy, txt, fontsize=6.4, va="top", transform=ax.transAxes,
                    color=F.INK if (np.isfinite(p) and p < 0.05) else F.FAINT, weight="bold" if (np.isfinite(p) and p < 0.05) else "normal")
    X.red_legend(fig, 0.75, y + 4.55)
    yb = y + 5.05
    IP = [r2("epr", "imp").p_boot, r2("spr", "imp").p_boot, st_e["p_int"], st_s["p_int"], MMC["epr"]["hom:old:sc"][1],
          MMC["spr"]["hom:old:sc"][1]]
    F.letter(fig, 0.4, yb, "b", "What can be said, and what it would take to say more", width=7.6)
    F.put(fig, 0.75, yb + 0.25,
          "Can be said, without any correction for floor speed: on the same floor, in the same 2024 cohorts, old Hom improved "
          "far less from day 1 to day 2 than old WT on entrances, shocks, time in the zone and longest avoidance, raw or per "
          "turn (P 0.02-0.05; same-cohort test P 0.01-0.03), and they reached criterion sooner only because their day 1 was "
          "already good. Per turn of the floor, young Hom improved exactly as young WT did, so the Hom learning deficit is an "
          "old-Hom deficit; the gap between the age groups is P %.2f-%.2f depending on the measure and test. That is the aging "
          "effect this data set supports: old Hom fail to improve.\n\n"
          "Cannot be said: that old Hom perform worse than old WT outright (day 2, P 0.4), or that old Hom are worse than young "
          "Hom on raw day-2 shocks once speed is handled (P 0.16-0.36). The young-vs-old comparison also carries year and "
          "injection (young Hom 2026 and mostly injected; old Hom 2024, none injected), which no reanalysis can separate.\n\n"
          "To settle it: young and old Hom and WT littermates run in the same weeks on a floor checked to turn at one speed "
          "(timed with a stopwatch before and after each run day), none injected within two weeks of AA. With the effect sizes "
          "here (old Hom vs old WT improvement, g about 1.1), 14-15 mice per group would give 80%% power at P < 0.05."
          % (min(IP), max(IP)), 7.2, size=6.6)
    F.save(fig, OUT, "07_scoreboard")



# ============================================================================ page 8: without the cooked sessions
COOKED = {("527", 2), ("598", 6), ("1663", 3), ("1663", 16)}
MEDIUM = {("528", 1), ("576", 3), ("531", 1), ("1665", 2), ("1633", 1), ("1633", 3), ("597", 1), ("597", 6)}
MEDIUM_MICE = {"520", "1667", "1644"}          # flagged for every session (s0-s16)


def cleaned(col, drop_sessions, drop_mice):
    TR = CR["TR"]
    keep = ~TR.apply(lambda r: (r.mouse, int(r.session)) in drop_sessions or r.mouse in drop_mice, axis=1)
    d = TR[keep]
    d1 = d[d.session <= 8].groupby("mouse")[col].mean()
    d2 = d[d.session >= 9].groupby("mouse")[col].mean()
    return (d2 - d1).dropna().to_dict(), int((~keep).sum())


def did_test(v, seed=7):
    rng = np.random.RandomState(seed)
    cells = {(g, a): np.array([v[m] for m in ML if X.grp(m) == "%s %s" % (g, a) and m in v]) for g in ("WT", "Hom") for a in ("young", "old")}
    mm = {k: x.mean() for k, x in cells.items()}
    did = (mm[("Hom", "old")] - mm[("WT", "old")]) - (mm[("Hom", "young")] - mm[("WT", "young")])
    boots = []
    for _ in range(4000):
        b = {k: x[rng.randint(0, x.size, x.size)].mean() for k, x in cells.items()}
        boots.append((b[("Hom", "old")] - b[("WT", "old")]) - (b[("Hom", "young")] - b[("WT", "young")]))
    boots = np.array(boots)
    return did, np.percentile(boots, 2.5), np.percentile(boots, 97.5), min(1.0, 2 * min((boots <= 0).mean(), (boots >= 0).mean()))


def page_cooked():
    fig, y = F.page("Without the flagged sessions: the old-Hom improvement deficit holds; the young pair still shows nothing",
                    "RESCUE · 7 · WITHOUT THE FLAGGED SESSIONS", number=8)
    y += 0.3
    sets = [("All sessions", set(), set()),
            ("Without the cooked sessions", COOKED, set()),
            ("Without cooked and medium-cooked", COOKED | MEDIUM, MEDIUM_MICE)]
    res = []
    for col in ("spr", "epr"):
        for lab, ds, dm in sets:
            v, n = cleaned(col, ds, dm)
            pyo = S.two([v[m] for m in ML if X.grp(m) == "WT young" and m in v], [v[m] for m in ML if X.grp(m) == "Hom young" and m in v])["p"]
            pol = S.two([v[m] for m in ML if X.grp(m) == "WT old" and m in v], [v[m] for m in ML if X.grp(m) == "Hom old" and m in v])["p"]
            p24 = S.two([v[m] for m in ML if OLD24(m) and m in v], [v[m] for m in ML if OLDH(m) and m in v])["p"]
            res.append(dict(col=col, set=lab, v=v, n_dropped=n, p_young=pyo, p_old=pol, p_old24=p24, did=did_test(v),
                            n_mice=len(v)))
    R = [r for r in res if r["col"] == "spr"]
    F.letter(fig, 0.4, y, "a", "Shocks per turn, day 2 minus day 1: old pair %s, %s and %s; young pair %s, %s and %s" % (
        F.pstr(R[0]["p_old"]), F.pstr(R[1]["p_old"]), F.pstr(R[2]["p_old"]), F.pstr(R[0]["p_young"]), F.pstr(R[1]["p_young"]),
        F.pstr(R[2]["p_young"])), width=7.6)
    for k, r in enumerate(R):
        ax = F.axes_in(fig, 0.75 + k * 2.45, y + 0.75, 2.05, 2.3)
        X.group_dots(ax, r["v"], pairs=((0, 1), (2, 3)), ylabel="Shocks per turn, day 2 - day 1" if k == 0 else "", size=13)
        ax.axhline(0, color=F.FAINT, lw=0.5, zorder=0)
        ax.set_ylim(-1.9, 1.6)
        d = r["did"]
        ax.set_title("%s\n%d sessions out, %d mice left\nyoung pair %s · old pair %s\ngaps differ by %.2f (95%% CI %.2f to %.2f), %s" % (
            r["set"], r["n_dropped"], r["n_mice"], F.pstr(r["p_young"]), F.pstr(r["p_old"]), d[0], d[1], d[2], F.pstr(d[3])),
            fontsize=5.5, loc="left", linespacing=1.2)
        X.red(ax, "")
    X.genotype_legend(fig, 0.75, y + 3.45)
    X.red_legend(fig, 0.75, y + 3.7)
    yb = y + 4.25
    F.letter(fig, 0.4, yb, "b", "The same three ways for entrances per turn, and for old Hom against the 2024 old WT only (same floor)",
             width=7.6)
    ax = F.axes_in(fig, 0.6, yb + 0.2, 7.3, 1.6)
    ax.axis("off")
    hx = [0, 0.2, 0.47, 0.6, 0.73, 0.86]
    for j, h in enumerate(["Measure", "Sessions used", "young pair", "old pair", "old Hom vs\n2024 old WT", "Hom x age\n(gaps differ)"]):
        ax.text(hx[j], 1, h, fontsize=6.0, weight="bold", color=F.SOFT, va="top", transform=ax.transAxes)
    for i, r in enumerate(res):
        yy = 0.76 - i * 0.12
        cells = ["Shocks per turn" if r["col"] == "spr" else "Entrances per turn", r["set"], r["p_young"], r["p_old"], r["p_old24"], r["did"][3]]
        for j, c in enumerate(cells):
            if j < 2:
                txt, col = (c if (j == 1 or i % 3 == 0) else ""), F.INK
            else:
                txt, col = F.pstr(c) + (" " + F.stars(c) if c < 0.05 else ""), (F.INK if c < 0.05 else F.FAINT)
            ax.text(hx[j], yy, txt, fontsize=6.1, va="top", transform=ax.transAxes, color=col)
    F.put(fig, 0.6, yb + 2.0,
          "From 'active avoidance outlier session notes.xlsx'. Cooked (yellow): 527 s2 (dropped before s2, no reaction), 598 s6 "
          "(shocker not delivering), 1663 s3 and s16 (battery pins out). Medium: 528 s1, 576 s3, 531 s1, 1665 s2, 1633 s1 and "
          "s3, 597 s1 and s6 (shocker off or doubtful), and every session of 520, 1667 and 1644 (very jumpy). Only the flagged "
          "sessions come out; a mouse's day means come from its other sessions, and the three whole-run mice leave the "
          "analysis. 520, 597 and 1644 are Het, so they never appear in this WT-and-Hom plot. Tests as on page 5: generous two-group tests; gaps differ = bootstrap of (old Hom - old WT) "
          "- (young Hom - young WT).", 7.3, size=6.1, color=F.SOFT)
    F.save(fig, OUT, "08_without_flagged_sessions")
    pd.DataFrame([{k: v for k, v in r.items() if k not in ("v", "did")} | dict(did=r["did"][0], did_lo=r["did"][1], did_hi=r["did"][2],
                                                                            p_did=r["did"][3]) for r in res]).to_csv(
        os.path.join(OUT, "without_flagged_sessions.csv"), index=False)

# ============================================================================ page 1: the menu
def page_front():
    fig = plt.figure(figsize=(8.5, 11))
    e, s_ = r1("epr", "imp"), r1("shocks", "imp")
    st_e, st_s = MMC["epr_slope_tests"], MMC["spr_slope_tests"]
    F.put(fig, 0.7, 0.8, "BARRY LAB · KCNT1 ACTIVE AVOIDANCE · WHAT CAN BE RESCUED, 2026-11-24", 7.2, size=7.2, color=F.KICK,
          weight="bold")
    F.put(fig, 0.7, 1.05, "What can be rescued, and the age question", 7.2, size=17, weight="bold")
    F.put(fig, 0.7, 1.5, "A supplement to the KCNT1 AA story menu and its companion 'Floor speed is a confounder'. Which comparisons "
                         "survive the floor-speed confound, and whether anything shows Hom mice doing worse than WT with age.",
          7.2, size=8, color=F.SOFT)
    F.put(fig, 0.72, 2.3, "The short version", 7.2, size=7.5, weight="bold")
    F.put(fig, 0.72, 2.55,
          "Two things can be rescued. First, every old Hom ran on the same 2024 floor as ten old WT (5.2 deg/s each, same "
          "cohorts, no injections), so that comparison needs no correction: old Hom started day 1 as well as old WT but barely "
          "improved by day 2 (entrances per turn fell %.2f against %.2f, %s; shocks %s; same-cohort test %s). Second, "
          "entrances per turn of the floor do not move with floor speed (within WT, within a mouse), so young and old can be "
          "compared on them: young Hom improved exactly like young WT (%s), and the deficit appears only in the old Hom; the "
          "gap between ages is P %.2f-%.2f depending on the test. So the age effect the data supports is 'old Hom fail to "
          "improve', not 'old Hom perform worse': on day 2 old Hom and old WT do not differ. What cannot be rescued: any raw "
          "young-vs-old count (young Hom never shared a floor speed with anyone), and the year and injection differences that "
          "travel with age here. Moving each mouse's own walking to another floor speed does not work either: avoidance is "
          "timed to the room."
          % (-e.mean_WT, -e.mean_Hom, F.pstr(e.p), F.pstr(s_.p), F.pstr(e.p_cohort), F.pstr(st_e["p_young"]),
             min(st_s["p_int"], MMC["spr"]["hom:old:sc"][1]), max(st_e["p_int"], r2("epr", "imp").p_boot)), 7.0, size=7.3)
    F.put(fig, 0.72, 4.45, "The pages", 7.2, size=7.5, weight="bold")
    rows = [("2", "The map", "Who ran at which speed; the five routes; how every session got a speed.", "old Hom and 2024 old WT share a floor"),
            ("3", "A speed-free count", "Raw entrances against floor speed vs entrances per turn; which measures are speed-free.",
             "per turn: WT rho %.2f" % CR["WTC"][(CR["WTC"].measure == "epr") & (CR["WTC"].summary == "d1") &
                                                 (CR["WTC"].scope == "WT")].rho.iloc[0]),
            ("4", "Same floor", "Old Hom vs old WT on the 2024 floor: day 1, day 2, improvement, curves.", "improvement %s" % F.pstr(e.p)),
            ("5", "Young and old, per turn", "Improvement and learning slopes per turn in the four genotype x age groups.",
             "young pair %s, old pair %s" % (F.pstr(st_e["p_young"]), F.pstr(st_e["p_old"]))),
            ("6", "Adults; extrapolation", "Age 19-46 weeks on one floor; raw counts moved along three slopes.", "no age-within-adults effect"),
            ("7", "Scoreboard", "Every age claim by every route; what it would take to settle it.", "old Hom fail to improve"),
            ("8", "Without flagged sessions", "Page 5's shocks-per-turn plot without the cooked, then without cooked and medium-cooked sessions.",
             "old pair P 0.028 / 0.037 / 0.041")]
    ax = F.axes_in(fig, 0.7, 4.7, 7.3, 3.9)
    ax.axis("off")
    hx = [0, 0.05, 0.27, 0.68]
    for j, h in enumerate(["Page", "Story", "What it shows", "Best number"]):
        ax.text(hx[j], 1, h, fontsize=6.6, weight="bold", va="top", color=F.SOFT, transform=ax.transAxes)
    yy = 0.89
    for r in rows:
        cells = [r[0], F.wrap(r[1], 1.4, 6.8), F.wrap(r[2], 2.9, 6.8), F.wrap(r[3], 2.2, 6.8)]
        nl = max(c.count("\n") + 1 for c in cells)
        for j, c in enumerate(cells):
            ax.text(hx[j], yy, c, fontsize=6.8, va="top", weight="bold" if j == 1 else "normal", transform=ax.transAxes)
        yy -= 0.036 * nl + 0.04
        ax.plot([0, 1], [yy + 0.02, yy + 0.02], color=F.GRID, lw=0.6, transform=ax.transAxes)
    F.put(fig, 0.72, 8.85,
          "Floor speed: the refined reading of the stage speed check. Per turn = divided by the floor turns in the session. Red "
          "background on a panel or cell = the groups compared ran at different floor speeds. Day 2 - day 1 = each mouse's "
          "day-2 mean minus its day-1 mean. Exploratory: P values uncorrected. * P < 0.05, ** P < 0.01, *** P < 0.001.",
          7.2, size=6.6, color=F.SOFT)
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
    if os.path.exists(os.path.join(OUT, "without_flagged_sessions.csv")):
        pass
    doc = pymupdf.open()
    for f in pdfs:
        doc.insert_pdf(pymupdf.open(f))
    doc.save(os.path.join(DEST, "KCNT1_AA_Rescue_112426.pdf"))
    tab = os.path.join(DEST, "tables")
    R1.to_csv(os.path.join(tab, "route1_old_Hom_vs_old_WT_same_floor.csv"), index=False)
    shutil.copy2(os.path.join(OUT, "without_flagged_sessions.csv"), tab)
    R2.to_csv(os.path.join(tab, "route2_genotype_x_age_per_turn.csv"), index=False)
    R3.to_csv(os.path.join(tab, "route3_age_within_adults.csv"), index=False)
    R4.to_csv(os.path.join(tab, "route4_extrapolation_three_slopes.csv"), index=False)
    pm = pd.DataFrame({k: pd.Series(v) for k, v in PM.items()})
    pm.index.name = "mouse"
    pm.insert(0, "floor_speed_refined", [OMR.get(m, np.nan) for m in pm.index])
    pm.insert(0, "age_group", [F.MICE[m]["age_group"] for m in pm.index])
    pm.insert(0, "genotype", [F.geno(m) for m in pm.index])
    pm.to_csv(os.path.join(tab, "per_mouse_values_per_turn_and_raw.csv"))
    rows = []
    for c in ("epr", "spr", "entrances", "shocks"):
        for k, (b, p) in MMC[c].items():
            rows.append(dict(measure=c, term=k, coef=b, p=p))
        rows.append(dict(measure=c, term="per-mouse slopes", **{"p_" + k: v for k, v in MMC[c + "_slope_tests"].items()}))
    pd.DataFrame(rows).to_csv(os.path.join(tab, "learning_slopes_and_mixed_models.csv"), index=False)
    for f in ("e1_confound_rescue.py", "crfig.py", "s4_rescue_pages.py"):
        shutil.copy2(os.path.join(F.HERE, f), os.path.join(DEST, "code"))
    print("packaged", DEST)


if __name__ == "__main__":
    import sys
    fns = {"1": page_front, "2": page_map, "3": page_per_turn, "4": page_same_floor, "5": page_age, "6": page_adults_extrap,
           "7": page_score, "8": page_cooked, "pkg": package}
    for w in (sys.argv[1:] or ["1", "2", "3", "4", "5", "6", "7", "8", "pkg"]):
        fns[w]()
        print("done", w)
