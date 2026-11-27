"""Primer and stories 0-2 (arena speed; H1 Hom learning; learning across days). Round 2 (2026-11-23 evening):
habituation (s0) left out of every curve, significance brackets and per-session stars, the criterion as cumulative curves,
and panel headings that state the finding."""
import datetime
import os

import matplotlib.dates as mdates
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, Wedge
from matplotlib.transforms import blended_transform_factory

import figlib_aa as F
import menu_data as D
import stats_lib as S

OUT = os.path.join(F.HERE, "out")
G3 = ["WT", "Het", "Hom"]
TRAIN = range(1, 17)
MARKS_GENO = [("WT", "Het", F.GCOL["Het"]), ("WT", "Hom", F.GCOL["Hom"])]
CRIT = "criterion|sessions_to_criterion"


def session_marks(ax, pivots, marks, fs=8.0):
    """One row of stars above the axes per pair (a, b, color): a star over every session where b differs from a
    (generous P < 0.05, one value per mouse). pivots: {group: mouse x session table}."""
    tr = blended_transform_factory(ax.transData, ax.transAxes)
    for row, (a, b, col) in enumerate(marks):
        pa, pb = pivots[a], pivots[b]
        for k in TRAIN:
            if k not in pa.columns or k not in pb.columns:
                continue
            p = S.two(pa[k].dropna().values, pb[k].dropna().values)["p"]
            if np.isfinite(p) and p < 0.05:
                ax.text(k, 1.0 + 0.075 * row, "*", transform=tr, ha="center", va="bottom", fontsize=fs, color=col,
                        weight="bold", clip_on=False)


def curves(ax, measure, ylabel, groups=None, sem=True, legend=False, colors=None, marks=None):
    """Mean of the mice per training session (s1-s16; habituation s0 is left out: the shock is off there)."""
    groups = groups or {g: D.by(g=g) for g in G3}
    piv = {}
    for g, ms in groups.items():
        col = (colors or {}).get(g, F.GCOL.get(g.split()[0], F.INK))
        ks, m, se, p = D.curve(measure, ms, TRAIN)
        piv[g] = p
        for seg in (ks <= 8, ks >= 9):
            ax.plot(ks[seg], m[seg], color=col, lw=1.3, marker="o", ms=2.2, label=g if seg[0] else None,
                    ls="--" if "old" in g else "-")
            if sem:
                ax.fill_between(ks[seg], (m - se)[seg], (m + se)[seg], color=col, alpha=0.13, lw=0)
    ax.axvline(8.5, color=F.FAINT, lw=0.6, ls="--")
    ax.set_xticks([1, 4, 8, 9, 12, 16])
    ax.set_xlim(0.4, 16.6)
    ax.set_xlabel("Training session")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color=F.GRID, lw=0.5)
    ax.set_axisbelow(True)
    if legend:
        ax.legend(frameon=False, fontsize=5.6, loc="upper right", handlelength=1.6)
    if marks is None and set(groups) == set(G3):
        marks = MARKS_GENO
    if marks:
        session_marks(ax, piv, marks)
    return piv


def speed_bands(ax, mid, ylabel, bands=("slow", "fast"), size=11):
    items, top = [], -np.inf
    for k, b in enumerate(bands):
        for g in G3:
            ms = D.by(g=g, rot=b)
            vv = [F.VALS_RAW[mid][m] for m in ms]
            x0 = k + (G3.index(g) - 1) * 0.27
            for m, val in zip(ms, vv):
                F.scatter_mouse(ax, x0 + (int(m) % 5 - 2) * 0.03, val, m, size=size)
            if vv:
                ax.plot([x0 - 0.11, x0 + 0.11], [np.median(vv)] * 2, color=F.INK, lw=1)
                top = max(top, max(vv))
        for c, a, bb in F.GENO_PAIRS:
            items.append((k + (a - 1) * 0.27, k + (bb - 1) * 0.27, F.P(mid, "%s_%s" % (c, b))))
    ax.set_xticks(range(len(bands)))
    ax.set_xticklabels(["%s floor" % b for b in bands])
    ax.set_xlim(-0.55, len(bands) - 0.45)
    ax.set_ylabel(ylabel)
    F.brackets(ax, items, top, gap=0.02)


def vbrackets(ax, items, x0, dx=1.0, fs=7.0):
    """Vertical brackets at the right end of curves: items (y1, y2, p); stars for P < 0.05."""
    sig = sorted([it for it in items if np.isfinite(it[2]) and it[2] < 0.05], key=lambda it: abs(it[1] - it[0]))
    for k, (y1, y2, p) in enumerate(sig):
        x = x0 + k * dx
        ax.plot([x - 0.25, x, x, x - 0.25], [y1, y1, y2, y2], color=F.INK, lw=0.6, clip_on=False, zorder=7)
        ax.text(x + 0.12, (y1 + y2) / 2, F.stars(p), rotation=90, ha="left", va="center", fontsize=fs, weight="bold",
                color=F.INK, clip_on=False)


def criterion_panel(ax):
    """Share of mice that have reached the criterion (a session with at most one entrance) by each session."""
    v = F.VALS["criterion|sessions_to_criterion"]
    ks = np.arange(0, 17)
    ends = {}
    for g in G3:
        ms = D.by(g=g)
        t = np.array([min(v[m], 16.0) for m in ms])
        e = np.array([1 if v[m] <= 16 else 0 for m in ms])
        cr = 100 * S.cum_reached(t, e, ks)
        ax.step(np.r_[ks, 16.6], np.r_[cr, cr[-1]], where="post", color=F.GCOL[g], lw=1.4,
                label="%s: %d of %d" % (g, e.sum(), len(ms)))
        ends[g] = cr[-1]
    ax.axvline(8.5, color=F.FAINT, lw=0.6, ls="--")
    ax.set_xlim(0.4, 16.6)
    ax.set_ylim(0, 100)
    ax.set_xticks([1, 4, 8, 9, 12, 16])
    ax.set_xlabel("Training session")
    ax.set_ylabel("Mice that reached it (%)")
    ax.grid(axis="y", color=F.GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=5.5, loc="lower right", handlelength=1.4, title="reached by s16", title_fontsize=5.5)
    c = "criterion|sessions_to_criterion"
    vbrackets(ax, [(ends["WT"], ends["Het"], F.P(c, "Het_vs_WT")), (ends["WT"], ends["Hom"], F.P(c, "Hom_vs_WT")),
                   (ends["Het"], ends["Hom"], F.P(c, "Hom_vs_Het"))], x0=17.3)
    ax.set_title("First session with at most one entrance\n(tests include floor speed)\nHom vs WT %s · Hom vs Het %s · Het vs WT %s" % (
        F.pstr(F.P(c, "Hom_vs_WT")), F.pstr(F.P(c, "Hom_vs_Het")), F.pstr(F.P(c, "Het_vs_WT"))),
        fontsize=6.0, loc="left", linespacing=1.15)


def corr_title(ax, head, mid, contrast="rot_corr_all", size=6.1):
    r = F.res(mid, contrast)
    ax.set_title("%s\nρ %+.2f, %s" % (head, r["effect"], F.pstars(r["p"])), fontsize=size, loc="left")


# ============================================================================ primer
def primer():
    fig, y = F.page("The task, the mice and the words used on every page", "PRIMER", number=2)
    F.letter(fig, 0.4, y + 0.12, "a", "The floor turns but the zone stays put: a mouse that stops walking is carried into the zone")
    ax = F.axes_in(fig, 0.55, y + 0.25, 2.45, 2.45)
    F.arena(ax)
    c = F.SECTOR[0]
    for ang in (c - 90, c + 90, c + 180):
        ax.add_patch(Wedge((0, 0), F.R_ARENA, ang - 30, ang + 30, fill=False, ec="#c9ccd3", lw=0.5, ls="--"))
    for ang, lab, col in ((c, "shock zone\n(60°, fixed\nin the room)", F.ZONE), (c - 90, "pre-shock\nquadrant", F.INK),
                          (c + 180, "opposite\nquadrant", F.INK), (c + 90, "post-shock\nquadrant", F.INK)):
        r = 25
        ax.text(r * np.cos(np.radians(ang)), r * np.sin(np.radians(ang)), lab, ha="center", va="center", fontsize=5.7, color=col)
    F.rot_arrow(ax, a0=180, a1=235)
    ax.text(F.R_ARENA * 1.22 * np.cos(np.radians(207)), F.R_ARENA * 1.22 * np.sin(np.radians(207)), "floor\nturns", fontsize=5.6,
            ha="center", va="center", color=F.INK)
    F.put(fig, 3.2, y + 0.4,
          "The floor turns counter-clockwise on screen (measured, page 3). A mouse that sits still is carried from the "
          "opposite quadrant, through the pre-shock quadrant, into the shock zone, which stays fixed in the room. To avoid "
          "shocks it has to keep walking away from the zone, against the turn. 79% of all 6,036 entrances came in from the "
          "pre-shock side.", 2.45, size=6.6)
    yb = y + 2.95
    F.letter(fig, 0.4, yb, "b", "One habituation session with the shock off (s0), then 16 training sessions over two days")
    ax = F.axes_in(fig, 0.6, yb + 0.12, 4.9, 0.55)
    ax.set_xlim(-1, 17)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for k in range(17):
        col = "#eeeeee" if k == 0 else ("#c6dbef" if k <= 8 else "#9ecae1")
        ax.add_patch(Rectangle((k - 0.45, 0.35), 0.9, 0.45, color=col, lw=0))
        ax.text(k, 0.575, "s%d" % k, ha="center", va="center", fontsize=5.6, color=F.SOFT if k == 0 else F.INK)
    ax.text(0, 0.1, "habituation\n(shock off)", ha="center", va="center", fontsize=5.4, color=F.SOFT)
    ax.text(4.5, 0.12, "day 1: training", ha="center", va="center", fontsize=6, color=F.SOFT)
    ax.text(12.5, 0.12, "day 2: training", ha="center", va="center", fontsize=6, color=F.SOFT)
    ax.plot([8.5, 8.5], [0.3, 0.85], color=F.INK, lw=0.6, ls="--")
    ax.text(8.5, 0.93, "overnight", ha="center", fontsize=5.4, color=F.SOFT)
    yc = yb + 0.95
    F.letter(fig, 0.4, yc, "c", "The 56 mice span 7-46 weeks, and every young Hom ran on the slow floor")
    ax = F.axes_in(fig, 1.75, yc + 0.22, 3.75, 1.5)
    for k, g in enumerate(G3):
        for m in D.by(g=g):
            d = F.MICE[m]
            jit = (int(m) % 7 - 3) * 0.07
            ax.scatter([d["age_wk"]], [k + jit], s=20, marker=F.marker_of(m), color=F.ROTC[d["rot_bin"]],
                       edgecolor=F.INK if m in F.FLAG else "white", linewidth=0.8 if m in F.FLAG else 0.4, zorder=3)
    ax.set_yticks(range(3))
    ax.set_yticklabels(["%s  n = %d\n(%d young, %d old)" % (g, len(D.by(g=g)), len(D.by(g=g, age="young")), len(D.by(g=g, age="old")))
                        for g in G3], fontsize=6)
    for t, g in zip(ax.get_yticklabels(), G3):
        t.set_color(F.GCOL[g])
        t.set_weight("bold")
    ax.axvline(18, color=F.FAINT, lw=0.6, ls=":")
    ax.text(18.4, 2.5, "18 wk: young | old", fontsize=5.3, color=F.FAINT)
    ax.set_ylim(-0.6, 2.7)
    ax.set_xlim(0, 47)
    ax.set_xlabel("Age at session 1 (weeks)")
    hs = [Line2D([], [], ls="", marker="o", ms=4, mfc=F.ROTC[b], mec="white", label=lab) for b, lab in
          (("fast", "fast floor (4.8-5.8 deg/s)"), ("medium", "medium (4.3-4.7)"), ("slow", "slow (2.2-3.7)"))]
    hs += [Line2D([], [], ls="", marker="o", ms=4, mfc="white", mec=F.INK, mew=0.9, label="flagged"),
           Line2D([], [], ls="", marker="s", ms=3.6, mfc="white", mec=F.SOFT, label="square = old")]
    W, H = fig.get_size_inches()
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.75 / W, 1 - (yc + 2.2) / H), ncol=5, frameon=False, fontsize=5.7,
               handletextpad=0.3, columnspacing=0.9)
    yd = yc + 2.6
    sess = (1, 8, 9, 16)
    nsh = {s: len(D.track("1652", s)[2]) for s in sess}
    F.letter(fig, 0.4, yd, "d", "A WT mouse (1652, 8 weeks) learns to wait across from the zone: %d shocks in s1, %s in s16"
             % (nsh[1], "none" if nsh[16] == 0 else str(nsh[16])))
    for j, s in enumerate(sess):
        ax = F.axes_in(fig, 0.6 + j * 1.25, yd + 0.25, 1.12, 1.12)
        F.arena(ax)
        x, yy, sh, en = D.track("1652", s)
        ax.plot(x, yy, color="#7d8590", lw=0.25, rasterized=True)
        ax.scatter(x[sh], yy[sh], s=5, color=F.ZONE, zorder=3, lw=0)
        ax.set_title("s%d · %d %s" % (s, len(sh), "shock" if len(sh) == 1 else "shocks"), fontsize=5.8, color=F.INK)
    F.put(fig, 0.6, yd + 1.5, "Gray: the path in the room. Red dots: shocks. s1 and s8 open and close day 1; s9 and s16 open "
                              "and close day 2.", 4.9, size=6.2, color=F.SOFT)
    F.textcol(fig, y + 0.05, [
        ("What was measured", "Everything comes straight from the 952 tracker files (56 mice x 17 sessions), not from "
                              "TrackAnalysis, so the Sep 2024 folder, 894 and 1667's last sessions are in. Page 11 checks "
                              "the numbers against TrackAnalysis."),
        ("Habituation (s0)", "The first session runs with the shock voltage off; the tracker still logs a 'shock' at every "
                             "entry, but nothing is delivered (checked on page 7). Its shock, entrance and zone numbers mean "
                             "nothing, so no curve or test uses them; only how the mice explore is read from it (story 4)."),
        ("Words", "Shock: one 500-ms pulse (another every 2 s while the mouse stays in).\n"
                  "Entrance: an entry into the zone that drew a shock.\n"
                  "Entrances per turn: entrances divided by the number of full turns the floor made; a mouse that never "
                  "walks gets about one per turn, so this does not depend on the floor's speed.\n"
                  "Time in zone: % of the session inside the 60° zone (chance 16.7%).\n"
                  "Strategy score: opposite-quadrant time / (opposite + pre-shock). 1 = waits far away; 0 = waits just "
                  "upstream of the zone.\n"
                  "Criterion: the first session with at most one entrance."),
        ("Groups", "Young = under 18 weeks at session 1 (7-16 wk); old = 19-46 wk. One number per mouse in every test, "
                   "for example the day-2 mean of s9-s16."),
        ("Flagged mice", "461 and 462 (a scrapped July run with shocks came first), 457 (Lab Ops: 'excluded from Dylan's "
                         "study for behavior'), and the seven Hom virus-injected 2-7 days before AA (598, 1603, 1604, 1629, "
                         "1633, 1634, 1637). Kept everywhere; page 11 shows each headline without them."),
        ("Stats", "Generous and uncorrected: every applicable test is run (Mann-Whitney, Welch, Student; Spearman, Pearson, "
                  "Kendall; ANOVA, Kruskal-Wallis, ordered trend) and the smallest P is shown. Floor speed: in stories "
                  "1-7 every value is moved to one floor speed (%.1f deg/s) along the slope speed has across all mice, "
                  "and a Wilcoxon test inside speed bands joins every comparison (page 3). Brackets: * P < 0.05, "
                  "** P < 0.01, *** P < 0.001. A star over a session in a curve: that genotype differs from WT in that "
                  "session. The criterion is compared as curves (Cox with speed; log-rank inside speed bands)." % F.REF),
    ])
    F.save(fig, OUT, "02_primer")


# ============================================================================ story 0: the arena
def story0():
    fig, y = F.page("The arena did not turn at one speed, and its speed moves the raw numbers",
                    "STORY 0 · THE APPARATUS · READ THIS FIRST", number=3)
    F.legend_mice(fig, 0.55, y + 0.02, speed=False)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "Floor speed ranged 2.2-5.8 deg/s across cohorts although the motor setting never changed")
    days = sorted(D.ROTDAY["omega"])
    for j, lab in enumerate(("2024", "2026")):
        ds = [d for d in days if d.startswith(lab)]
        ax = F.axes_in(fig, 0.75 + j * 2.45, y + 0.3, 2.25, 1.45)
        xs = [datetime.date.fromisoformat(d) for d in ds]
        for dd, x in zip(ds, xs):
            ms = [m for m in D.MLIST if F.MICE[m]["s0"] == dd or F.MICE[m]["s1"] == dd]
            ax.scatter([x], [D.ROTDAY["omega"][dd]], s=14, color=F.INK, zorder=3)
            for k, m in enumerate(sorted(ms, key=lambda m: G3.index(F.geno(m)))):
                ax.scatter([x], [1.35 - 0.17 * k], s=6, color=F.GCOL[F.geno(m)], marker=F.marker_of(m), lw=0, zorder=3)
        ax.axhline(6.0, color=F.FAINT, lw=0.6, ls=":")
        ax.text(xs[0], 6.08, "1 turn per minute", fontsize=5, color=F.FAINT)
        ax.set_ylim(0.2, 6.5)
        ax.set_yticks([2, 3, 4, 5, 6])
        ax.set_title(lab, fontsize=6.5, loc="left")
        ax.tick_params(axis="x", labelsize=5.3, rotation=40)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        if j == 0:
            ax.set_ylabel("Floor speed (deg/s)")
        else:
            ax.annotate("motor broke 10/21;\nrunning again 10/28", xy=(datetime.date(2026, 10, 20), 4.3), fontsize=5.2, color=F.SOFT, ha="center")
    F.put(fig, 0.75, y + 2.1, "Black dot: the day's speed. Small marks at the bottom: the mice that ran that day (genotype color, "
                              "circle young, square old).", 4.75, size=5.8, color=F.SOFT)
    yb = y + 2.5
    F.letter(fig, 0.4, yb, "b", "Every young Hom ran on the slow floor, and faster floors gave more shocks")
    ax = F.axes_in(fig, 0.75, yb + 0.3, 2.05, 1.4)
    grp = {m: "%s %s" % (F.geno(m), F.MICE[m]["age_group"]) for m in D.MLIST}
    order = ["WT young", "WT old", "Het young", "Het old", "Hom young", "Hom old"]
    om = {m: F.MICE[m]["omega"] for m in D.MLIST}
    top = F.dots(ax, om, grp, order, xlabels=["WT\nyoung", "WT\nold", "Het\nyoung", "Het\nold", "Hom\nyoung", "Hom\nold"],
                 ylabel="Floor speed during the run (deg/s)", names=None)
    items = []
    for k, g in enumerate(G3):
        r = S.two([om[m] for m in D.by(g=g, age="old")], [om[m] for m in D.by(g=g, age="young")])
        items.append((2 * k, 2 * k + 1, r["p"]))
    F.brackets(ax, items, top)
    ax.set_title("Young vs old inside each genotype", fontsize=6.0, loc="left")
    ax1 = F.axes_in(fig, 3.35, yb + 0.3, 2.15, 1.4)
    v = F.VALS_RAW["shocks|total"]
    for m in D.MLIST:
        F.scatter_mouse(ax1, F.MICE[m]["omega"], v[m], m)
    xx, yy, lo, hi = F.theil([F.MICE[m]["omega"] for m in D.MLIST], [v[m] for m in D.MLIST])
    ax1.fill_between(xx, lo, hi, color=F.KICK, alpha=0.1, lw=0)
    ax1.plot(xx, yy, color=F.KICK, lw=1)
    corr_title(ax1, "Total shocks against floor speed", "shocks|total")
    ax1.set_xlabel("Floor speed (deg/s)")
    ax1.set_ylabel("Shocks, s1-s16")
    yc = yb + 2.45
    rr = F.res("entrances_per_rev|d2", "rot_corr_all")
    F.letter(fig, 0.4, yc, "c", "Entrances per turn do not change with floor speed (%s), so they compare cohorts fairly" % F.pstr(rr["p"]))
    ax2 = F.axes_in(fig, 0.75, yc + 0.42, 2.05, 1.35)
    v2 = F.VALS_RAW["entrances_per_rev|d2"]
    for m in D.MLIST:
        F.scatter_mouse(ax2, F.MICE[m]["omega"], v2[m], m)
    corr_title(ax2, "Day-2 entrances per turn against floor speed", "entrances_per_rev|d2")
    ax2.set_xlabel("Floor speed (deg/s)")
    ax2.set_ylabel("Day-2 entrances per turn")
    ax3 = F.axes_in(fig, 3.35, yc + 0.42, 2.15, 1.35)
    speed_bands(ax3, "shocks|d1", "Day-1 shocks per session", bands=("slow", "medium", "fast"), size=12)
    ax3.set_title("Or compare only mice that got the same\nspeed (WT | Het | Hom inside each band)", fontsize=6.1, loc="left")
    yd = yc + 2.35
    F.letter(fig, 0.4, yd, "d", "Floor speed read from mice riding still agreed with a direct measurement within 6%")
    F.put(fig, 0.75, yd + 0.15,
          "A mouse sitting still rides the floor: its angle in the room grows at exactly the floor's speed. Every stretch of "
          "4 s at a constant distance from the center (< 0.4 cm change per s) and a constant angular speed (s.d. < 0.25 "
          "deg/s) is one reading; each day's speed is the median of 55-1,033 readings. Check: on 10/7/2025 the tracker "
          "saved one session in both the room and the arena frame; their angles drift apart at 4.32 deg/s, the floor's "
          "true speed that day, and the ride method reads 4.58 deg/s from the room track alone (10 rides; 6% high). The "
          "MotorState column says 4 on every day, so the motor was always asked for the same speed; it did not deliver it.",
          4.75, size=6.4)
    F.textcol(fig, 1.35, [
        ("The claim", "The floor turned at about 5.0-5.6 deg/s in spring 2024, 4.3-4.5 in October 2024, 2.2-3.7 from March "
                      "to September 2026, and 5.3-5.8 after the motor was repaired in late October 2026 (1 turn per minute "
                      "= 6 deg/s). A faster floor carries a resting mouse into the zone sooner, so raw shocks, entrances, "
                      "path and speed all rise with it."),
        ("Why it matters here", "It lines up with the groups we want to compare. Every young Hom ran on the slow floor "
                                "(median 3.1 deg/s); every young WT and four of five young Het ran on the fast one (5.5). "
                                "Old Hom ran fast (5.0); old WT and Het ran on all three. So 'young Hom shock less' can be "
                                "the floor, not the mouse. And the 18 mice virus-injected before AA are all slow-floor "
                                "mice (18 of the 20), so in these data the floor and the injection cannot be told apart."),
        ("How the menu handles it", "Stories 1-7 compare every value at one floor speed, %.1f deg/s (the median of the 56 "
                                    "mice): each mouse's number is moved along the slope floor speed has across all mice "
                                    "(story 1, c shows how), and every comparison also includes a Wilcoxon test inside the "
                                    "speed bands (c, right). This page alone shows raw numbers. The speed supplement shows "
                                    "every headline before and after." % F.REF),
        ("What it shows", "Total shocks rise with speed (%s), day-1 shocks too (%s); entrances per turn do not (%s). Path in "
                          "the room rises steeply (ρ +0.61, P 6e-08) because a passive mouse is carried farther."
                          % (F.pstr(F.P("shocks|total", "rot_corr_all")), F.pstr(F.P("shocks|d1", "rot_corr_all")),
                             F.pstr(F.P("entrances_per_rev|d2", "rot_corr_all")))),
        ("To fix", "Measure the floor speed before each run (a mark and a stopwatch, or the arena-frame file) and log it. "
                   "Run genotypes and ages side by side on the same days."),
    ])
    F.save(fig, OUT, "03_story0_arena_speed")


# ============================================================================ story 1: H1
def speed_slope_panel(ax, mid, ylabel):
    """How the adjustment works: raw values against floor speed, one line per genotype with the shared slope; each mouse
    is moved along its line to the reference speed."""
    raw, adj = F.VALS_RAW[mid], F.VALS[mid]
    b, pb = F.B["SLOPE"][mid]
    for m in D.MLIST:
        F.scatter_mouse(ax, F.MICE[m]["omega"], raw[m], m, size=11)
    for g in ("Het", "Hom", "WT"):     # WT last and dashed, so it shows where it runs on top of Het
        ms = D.by(g=g)
        xs = np.array([F.MICE[m]["omega"] for m in ms])
        mu = np.mean([adj[m] for m in ms])
        xx = np.linspace(xs.min(), xs.max(), 10)
        ax.plot(xx, mu + b * (xx - F.REF), color=F.GCOL[g], lw=1.0 if g == "WT" else 1.2, ls=(0, (3, 2)) if g == "WT" else "-",
                zorder=5 if g == "WT" else 4)
        ax.scatter([F.REF], [mu], s=22, color=F.GCOL[g], edgecolor=F.INK, lw=0.6, zorder=6, marker="D")
    ax.axvline(F.REF, color=F.FAINT, lw=0.6, ls=":")
    ax.set_xlabel("Floor speed (deg/s)")
    ax.set_ylabel(ylabel)
    ax.set_title("Shared slope %+.1f per deg/s (%s);\ndiamonds: group means at %.1f deg/s" % (b, F.pstr(pb), F.REF),
                 fontsize=5.6, loc="left", color=F.SOFT)


def story1():
    d1 = F.res("shocks|d1", "Hom_vs_WT")
    d1h = F.res("shocks|d1", "Hom_vs_Het")
    d1r = F.res("shocks|d1", "Hom_vs_WT", raw=True)
    pcr = F.res(CRIT, "Hom_vs_WT")
    pch = F.res(CRIT, "Hom_vs_Het")
    pd2 = F.res("shocks|d2", "Hom_vs_WT")
    pe2 = F.res("entrances_per_rev|d2", "Hom_vs_WT")
    mi = F.mm("entrances_per_rev", "geno_x_session", "[T.Hom]:sc")
    b1, pb1 = F.B["SLOPE"]["shocks|d1"]
    nslow = {g: len(D.by(g=g, rot="slow")) for g in G3}
    fig, y = F.page("Hypothesis 1, Hom learn worse: not in these data. At one floor speed Hom take as many shocks as WT, "
                    "reach criterion sooner, and finish day 2 where WT do", "STORY 1 · HYPOTHESIS 1 · HOM LEARNING", number=4)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "At one floor speed the genotypes learned alike; fewer Hom shocks than WT only in s2 and s4")
    for j, (meas, lab) in enumerate((("shocks", "Shocks per session"), ("entrances_per_rev", "Entrances per turn"),
                                     ("time_in_zone_pct", "Time in the zone (%)"))):
        ax = F.axes_in(fig, 0.75 + j * 1.68, y + 0.42, 1.25, 1.2)
        curves(ax, meas, lab, legend=(j == 0))
    F.put(fig, 0.75, y + 1.98, "Mean ± s.e.m. of the mice at one floor speed. Stars over a session: Het (orange) or Hom (purple) "
                               "differ from WT in that session (P < 0.05). Habituation (s0) is not shown: the shock was off.",
          4.9, size=5.8, color=F.SOFT)
    yb = y + 2.55
    F.letter(fig, 0.4, yb, "b", "Hom reached criterion sooner than WT (%s); their shocks matched WT's on both days"
             % F.pstr(pcr["p"]))
    specs = [("shocks|d1", "Shocks per session", "Day 1 (s1-s8)"),
             ("shocks|d2", "Shocks per session", "Day 2 (s9-s16)"),
             ("entrances_per_rev|d2", "Entrances per turn", "Day 2, entrances per turn")]
    axs = F.grid(fig, 0.75, yb + 0.65, 2, 2, 1.9, 1.15, gx=0.75, gy=1.0)
    for ax, (mid, ylab, t) in zip(axs[:3], specs):
        F.geno_dots(ax, mid, ylab, title=t, names=None)
    criterion_panel(axs[3])
    yc = yb + 4.45
    F.letter(fig, 0.4, yc, "c", "Raw, Hom took fewer day-1 shocks than WT (%s); the slow floor most of them ran on explains it"
             % F.pstr(d1r["p"]))
    ax = F.axes_in(fig, 0.75, yc + 0.5, 1.25, 1.1)
    F.geno_dots(ax, "shocks|d1", "Day-1 shocks (raw)", title="Before the adjustment", names=None, raw=True)
    ax = F.axes_in(fig, 0.75 + 1.68, yc + 0.5, 1.25, 1.1)
    speed_bands(ax, "shocks|d1", "Day-1 shocks (raw)")
    ax.set_title("Raw, inside one speed band\nHom vs WT: slow %s · fast %s" % (F.pstr(F.P("shocks|d1", "Hom_vs_WT_slow")),
                                                                         F.pstr(F.P("shocks|d1", "Hom_vs_WT_fast"))),
                 fontsize=5.6, loc="left", color=F.SOFT)
    ax = F.axes_in(fig, 0.75 + 2 * 1.68, yc + 0.5, 1.25, 1.1)
    speed_slope_panel(ax, "shocks|d1", "Day-1 shocks (raw)")
    F.textcol(fig, 1.6, [
        ("The claim", "Hypothesis 1 said Hom would take more shocks and spend more time in the zone. They do not. At one "
                      "floor speed Hom take as many shocks as WT on both days and reach the one-entrance criterion sooner. "
                      "Raw, Hom even look better on day 1, but that comes from the slow floor most of them ran on (c). What "
                      "Hom do show is a flatter curve (story 2)."),
        ("How to read it", "a: session values averaged per genotype at one floor speed (s.e.m. band); the dashed line is the "
                           "night between the days. b: one dot per mouse at one floor speed; circles young, squares old, "
                           "ringed = flagged; line = median; brackets mark pairs that differ. b, last: the share of each "
                           "genotype that has had a session with at most one entrance; mice that never did stay below the "
                           "top (tests with floor speed: Cox model, and log-rank inside speed bands). c: day-1 shocks before "
                           "the adjustment, inside speed bands, and how the adjustment moves each mouse along the shared "
                           "speed slope."),
        ("What it shows", "Day-1 shocks at %.1f deg/s: Hom %.1f vs WT %.1f (%s) and Het %.1f (%s). Raw: Hom %.1f vs WT %.1f "
                          "(%s). Criterion: %d of 15 Hom reached it, half of the Hom by s%d; %d of 21 WT, half of the WT by "
                          "s%d (%s; Hom vs Het %s). Day 2: Hom %.1f vs WT %.1f shocks (%s); entrances per turn %.2f vs %.2f "
                          "(%s)." % (F.REF, d1["mean_b"], d1["mean_a"], F.pstr(d1["p"]), d1h["mean_a"], F.pstr(d1h["p"]),
                                     d1r["mean_b"], d1r["mean_a"], F.pstr(d1r["p"]), round(pcr["reached_b"] * 15),
                                     pcr["km_median_b"], round(pcr["reached_a"] * 21), pcr["km_median_a"], F.pstr(pcr["p"]),
                                     F.pstr(pch["p"]), pd2["mean_b"], pd2["mean_a"], F.pstr(pd2["p"]), pe2["mean_b"],
                                     pe2["mean_a"], F.pstr(pe2["p"]))),
        ("Why the raw day-1 gap goes", "Day-1 shocks rise by %.1f per session for every deg/s of floor speed (%s), and %d of "
                                       "15 Hom ran on the slow floor against %d of 21 WT. Inside one speed band (c) Hom and "
                                       "WT overlap. The slow-floor mice are also the virus-injected ones, so injection could "
                                       "do the same." % (b1, F.pstr(pb1), nslow["Hom"], nslow["WT"])),
        ("Verdict", "Not backed up: no sign that Hom avoid worse. They reach criterion sooner, and the Hom difference that "
                    "holds is the shape of the curve: across sessions Hom improve less (entrances per turn, Hom x session "
                    "%s with floor speed in the model)." % F.pstr(mi[0])),
        ("To replicate", "Hom and WT littermates, same age, same days, same measured floor speed; s1 to s16."),
    ])
    F.save(fig, OUT, "04_story1_hom_learning")


# ============================================================================ story 2: improvement
def story2():
    het = F.res("entrances|d2_minus_d1", "Het_vs_WT")
    hom = F.res("entrances|d2_minus_d1", "Hom_vs_WT")
    mut = F.res("entrances|d2_minus_d1", "Mut_vs_WT")
    mhet = F.mm("entrances_per_rev", "geno_x_session", "[T.Het]:sc")[0]
    mhom = F.mm("entrances_per_rev", "geno_x_session", "[T.Hom]:sc")[0]
    fig, y = F.page("Both mutants improve less across the two days than WT; WT gain the most from day 1 to day 2",
                    "STORY 2 · HYPOTHESIS 1, REFINED · HOW MUCH THEY IMPROVE", number=5)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "WT cut their entrances more from day 1 to day 2 than Het (%s) and Hom (%s)"
             % (F.pstr(het["p"]), F.pstr(hom["p"])))
    specs = [("entrances|d2_minus_d1", "Entrances per session"), ("entrances_per_rev|d2_minus_d1", "Entrances per turn"),
             ("shocks|d2_minus_d1", "Shocks per session"), ("time_in_zone_pct|d2_minus_d1", "Time in the zone (%)")]
    axs = F.grid(fig, 0.75, y + 0.68, 2, 2, 1.9, 1.15, gx=0.75, gy=1.0)
    for ax, (mid, lab) in zip(axs, specs):
        F.geno_dots(ax, mid, "Day 2 - day 1", title=lab, names=None)
        ax.axhline(0, color=F.FAINT, lw=0.6)
    yb = y + 4.45
    F.letter(fig, 0.4, yb, "b", "Against their own day 1, Het and Hom improved more slowly than WT (%s, %s)"
             % (F.pstr(mhet), F.pstr(mhom)))
    ax = F.axes_in(fig, 0.75, yb + 0.4, 2.3, 1.3)
    piv = {}
    for g in G3:
        p = D.U[D.U.mouse.isin(D.by(g=g))].pivot_table(index="mouse", columns="session", values="entrances_per_rev")
        base = p.loc[:, 1:8].mean(axis=1)
        rel = p.loc[:, 1:16].div(base.replace(0, np.nan), axis=0)
        piv[g] = rel
        mu = rel.mean()
        se = rel.std(ddof=1) / np.sqrt(rel.notna().sum())
        ks = np.arange(1, 17)
        for seg in (ks <= 8, ks >= 9):
            ax.plot(ks[seg], mu.values[seg], color=F.GCOL[g], lw=1.3, marker="o", ms=2.2, label=g if seg[0] else None)
            ax.fill_between(ks[seg], (mu - se).values[seg], (mu + se).values[seg], color=F.GCOL[g], alpha=0.13, lw=0)
    ax.axhline(1, color=F.FAINT, lw=0.6)
    ax.axvline(8.5, color=F.FAINT, lw=0.6, ls="--")
    ax.set_xticks([1, 4, 8, 9, 12, 16])
    ax.set_xlim(0.4, 16.6)
    ax.set_xlabel("Training session")
    ax.set_ylabel("Entrances per turn,\nrelative to the mouse's day 1")
    ax.legend(frameon=False, fontsize=5.8)
    session_marks(ax, piv, MARKS_GENO)
    ax = F.axes_in(fig, 3.3, yb + 0.4, 2.35, 1.2)
    ax.axis("off")
    hdr = ["Session values", "Het x\nsession", "Hom x\nsession", "Het x\nday 2", "Hom x\nday 2"]
    xs = [0.0, 0.47, 0.62, 0.77, 0.92]
    for j, c in enumerate(hdr):
        ax.text(xs[j], 1.0, c, fontsize=5.0, weight="bold", ha="left" if j == 0 else "center", va="top", transform=ax.transAxes)
    rows = []
    for meas, lab in (("entrances_per_rev", "Entrances per turn"), ("entrances", "Entrances (log)"), ("shocks", "Shocks (log)"),
                      ("time_in_zone_pct", "Time in the zone"), ("strategy_score", "Strategy score"), ("R", "Concentration R")):
        rows.append((lab,) + tuple(F.mm(meas, mdl, term)[0] for mdl, term in (
            ("geno_x_session", "[T.Het]:sc"), ("geno_x_session", "[T.Hom]:sc"), ("geno_x_day", "[T.Het]:C(day)"),
            ("geno_x_day", "[T.Hom]:C(day)"))))
    for i, r in enumerate(rows, 1):
        for j, c in enumerate(r):
            txt = c if j == 0 else ("%s %s" % (F.pstr(c).replace("P ", ""), F.stars(c))).strip()
            ax.text(xs[j], 1.0 - 0.13 - i * 0.135, txt, fontsize=5.2, ha="left" if j == 0 else "center", va="top",
                    color=F.INK if (j == 0 or c < 0.05) else F.FAINT, transform=ax.transAxes)
    F.put(fig, 3.3, yb + 1.7, "P of the genotype x session (or x day) term in mixed models over s1-s16, with the mouse as a "
                              "random effect and floor speed (and speed x session) in the model; gray = P ≥ 0.05. Strategy score and R belong to story 6. Stars in the curve: "
                              "Het (orange) or Hom (purple) differ from WT in that session.", 2.35, size=5.2, color=F.SOFT)
    yc = yb + 2.35
    F.letter(fig, 0.4, yc, "c", "No single step carried it: within-day and overnight changes were alike across genotypes")
    for j, (mid, lab) in enumerate((("entrances_per_rev|d1_change", "Within day 1: s7-8 minus s1-2"),
                                     ("entrances_per_rev|overnight", "Overnight: s9 minus s8"),
                                     ("entrances_per_rev|slope", "Slope over s1-s16"))):
        ax = F.axes_in(fig, 0.75 + j * 1.68, yc + 0.62, 1.25, 1.1)
        F.geno_dots(ax, mid, "Entrances per turn" if j < 2 else "Per session", title=lab, names=None)
        ax.axhline(0, color=F.FAINT, lw=0.6)
    F.textcol(fig, 1.6, [
        ("The claim", "WT improve the most between day 1 and day 2. Het and Hom improve less: their curves flatten earlier. "
                      "Het and WT ran on the same mix of floor speeds, so for Het this is not the floor."),
        ("How to read it", "a: day-2 mean minus day-1 mean, one dot per mouse; lower = more improvement; brackets mark pairs "
                           "that differ. b, left: each mouse's sessions divided by its own day-1 mean, so mice that start low "
                           "or high share one scale. b, right: P of the genotype x session (and x day) terms of mixed "
                           "models, which test whether the curves have different slopes. c: the same split into within-day "
                           "and overnight change."),
        ("What it shows", "Entrances, day 2 - day 1: WT %.1f, Het %.1f (%s), Hom %.1f (%s); both mutants together %s. With "
                          "age in the model as well Het stays at %s. In the mixed models (floor speed and speed x session "
                          "included) entrances per turn fall more slowly in Het (%s) and Hom (%s) than in WT." % (
                              het["mean_a"], het["mean_b"], F.pstr(het["p"]), hom["mean_b"], F.pstr(hom["p"]), F.pstr(mut["p"]),
                              F.pstr(F.P("entrances|d2_minus_d1", "Het_vs_WT_adj_age")), F.pstr(mhet), F.pstr(mhom))),
        ("Caveats", "Hom start lower (story 1), so part of their smaller gain is less room to improve. Per-mouse slopes (c, "
                    "right) point the same way (mutants vs WT %s). Neither the within-day nor the overnight "
                    "piece differs on its own; the gap builds up over day 2." % F.pstr(F.P("entrances_per_rev|slope", "Mut_vs_WT"))),
        ("Verdict", "Partly backed up, in a different form: not more shocks, but less improvement across training, in both "
                    "Het and Hom."),
        ("To replicate", "A third day, or a retention test a week later, would show whether the mutants plateau or are just "
                         "slower."),
    ])
    F.save(fig, OUT, "05_story2_improvement")


if __name__ == "__main__":
    primer()
    story0()
    story1()
    story2()
