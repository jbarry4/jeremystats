"""KCNT1 AA speed supplement (2026-11-23): what the arena's floor speed did to the numbers, how the story menu factors it
in, and which headlines stand. Six pages in the story-menu house style; written to out_speed/ and packaged to
Lab Figures/KCNT1_AA_Speed_Supplement_112326."""
import datetime
import glob
import os
import shutil
import warnings

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import pymupdf
import statsmodels.formula.api as smf
from matplotlib.lines import Line2D
from matplotlib.transforms import blended_transform_factory
from statsmodels.stats.anova import anova_lm

import figlib_aa as F
import menu_data as D
import stats_lib as S
from pages_a import G3, curves, speed_bands, speed_slope_panel

warnings.filterwarnings("ignore")
OUT = os.path.join(F.HERE, "out_speed")
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1_AA_Speed_Supplement_112326"
CRIT = "criterion|sessions_to_criterion"
F.FOOT = "KCNT1 active avoidance · speed supplement to the story menu · exploratory, P values uncorrected · 2026-11-23"
OM = {m: F.MICE[m]["omega"] for m in D.MLIST}
HOLD, GOES, NEW = F.KICK, F.ZONE, "#7b2d8e"

MEASURES = [  # (id, plain label, family)
    ("shocks|d1", "Shocks, day 1", "Avoidance"), ("shocks|d2", "Shocks, day 2", "Avoidance"),
    ("entrances|d1", "Entrances, day 1", "Avoidance"), ("entrances|d2", "Entrances, day 2", "Avoidance"),
    ("time_in_zone_pct|d1", "Time in the zone, day 1", "Avoidance"), ("time_in_zone_pct|d2", "Time in the zone, day 2", "Avoidance"),
    ("latency_first_entrance_s|d2", "Time to first entrance, day 2", "Avoidance"),
    ("max_avoid_s|d2", "Longest stretch out of the zone, day 2", "Avoidance"),
    ("entrances_per_rev|d1", "Entrances per turn, day 1", "Avoidance"), ("entrances_per_rev|d2", "Entrances per turn, day 2", "Avoidance"),
    ("entrances|d2_minus_d1", "Entrances, day 2 - day 1", "Improvement"), ("entrances_per_rev|d2_minus_d1", "Entrances per turn, day 2 - day 1", "Improvement"),
    ("strategy_score|d2", "Strategy score, day 2", "Where they wait"), ("zone_CW|d2", "Pre-shock quadrant share, day 2", "Where they wait"),
    ("brake_share|d2", "Turned back at the edge, day 2", "Where they wait"), ("R|d2", "Concentration, day 2", "Where they wait"),
    ("entropy|d2", "Entropy, day 2", "Where they wait"), ("consistency|pref_sd_d1", "Safe spot wander, day 1", "Where they wait"),
    ("path_m|d2", "Path in the room, day 2", "Movement"), ("walk_m|d2", "Walked on the floor, day 2", "Movement"),
    ("walk_speed_cm_s|d2", "Walking speed on the floor, day 2", "Movement"), ("immobile_pct|d2", "Still on the floor, day 2", "Movement"),
    ("rim_pct|d2", "Time at the rim, day 2", "Movement"), ("straightness|d2", "Straightness of walking, day 2", "Movement"),
    ("R|s0", "Concentration, habituation", "Habituation"), ("cells_visited|s0", "Floor covered, habituation", "Habituation"),
    ("walk_m|s0", "Walked on the floor, habituation", "Habituation"),
]
FAMC = {"Avoidance": "#1d2433", "Improvement": "#1f6f8b", "Where they wait": "#e08a2c", "Movement": "#5a6273", "Habituation": "#7b2d8e"}


def speed_fit(mid):
    """Shared slope (value ~ genotype + speed), standardized by the measure's s.d.; and genotype x speed interaction P."""
    v = F.VALS_RAW[mid]
    ms = [m for m in D.MLIST if m in v and np.isfinite(v[m])]
    df = pd.DataFrame({"v": [v[m] for m in ms], "g": [F.geno(m) for m in ms], "om": [OM[m] for m in ms]})
    fit = smf.ols("v ~ C(g) + om", df).fit()
    sd = df.v.std(ddof=1)
    b, se, p = float(fit.params["om"]), float(fit.bse["om"]), float(fit.pvalues["om"])
    full = smf.ols("v ~ C(g) * om", df).fit()
    pint = float(anova_lm(fit, full).iloc[1]["Pr(>F)"])
    slopes = {}
    for g in G3:
        d = df[df.g == g]
        if len(d) >= 5 and np.ptp(d.om) > 0:
            f = smf.ols("v ~ om", d).fit()
            slopes[g] = (float(f.params["om"]), float(f.bse["om"]), float(f.pvalues["om"]))
    return dict(b=b, se=se, p=p, z=b / sd, zlo=(b - 1.96 * se) / sd, zhi=(b + 1.96 * se) / sd, pint=pint, slopes=slopes, sd=sd)


def headline_rows():
    MMr, MMa = F.A["MM"], F.B["MM_ADJ"]

    def mm(M, model, meas, term):
        s = M[(M.measure == meas) & (M.model == model) & (M.term.str.contains(term, regex=False))]
        return float(s.p.iloc[0]) if len(s) else np.nan

    def circ(T, g):
        s = T[T.group == g]
        return float(s.p_direction.iloc[0]) if len(s) else np.nan
    R = []
    for story, items in (
        ("1  Hom learning", [("shocks|d1", "Hom_vs_WT", "Hom fewer day-1 shocks than WT"),
                             ("shocks|d1", "Hom_vs_Het", "Hom fewer day-1 shocks than Het"),
                             ("time_in_zone_pct|d1", "Hom_vs_WT", "Hom less day-1 time in the zone than WT"),
                             (CRIT, "Hom_vs_WT", "Hom reach criterion sooner than WT"),
                             (CRIT, "Hom_vs_Het", "Hom reach criterion sooner than Het")]),
        ("2  Improvement", [("entrances|d2_minus_d1", "Het_vs_WT", "Het improve less (entrances)"),
                            ("entrances|d2_minus_d1", "Hom_vs_WT", "Hom improve less (entrances)"),
                            ("shocks|d2_minus_d1", "Het_vs_WT", "Het improve less (shocks)"),
                            ("shocks|d2_minus_d1", "Hom_vs_WT", "Hom improve less (shocks)"),
                            ("MM", "[T.Het]:sc", "Het curves flatter (mixed model)"),
                            ("MM", "[T.Hom]:sc", "Hom curves flatter (mixed model)")]),
        ("3  Age", [("shocks|d2", "young_vs_old_Hom", "Old Hom more day-2 shocks than young Hom"),
                    ("shocks|d2", "int_age_group_Hom", "Hom x age interaction, day-2 shocks"),
                    ("latency_first_entrance_s|d2", "young_vs_old_Hom", "Old Hom enter sooner on day 2")]),
        ("4  Habituation", [("cells_visited|s0", "Hom_vs_WT", "Hom cover less of the floor"),
                            ("R|s0", "Hom_vs_WT", "Hom keep to one side"),
                            ("walk_m|s0", "Hom_vs_WT", "Hom walk farther")]),
        ("5-6  Where they wait", [("CIRC", "Het_vs_WT", "Het wait nearer the opposite (direction)"),
                                  ("strategy_score|d2", "Het_vs_WT", "Het wait opposite (strategy score)"),
                                  ("zone_CW|d2", "Het_vs_WT", "Het spend less time pre-shock"),
                                  ("brake_share|d2", "Het_vs_WT", "Het turn back less at the edge"),
                                  ("consistency|pref_sd_d1", "Het_vs_WT", "Het safe spot wanders, day 1"),
                                  ("R|d2", "Het_vs_WT", "Het more scattered (concentration)")]),
        ("7  Path shape", [("rim_pct|d2", "Hom_vs_WT", "Hom less at the rim, day 2"),
                           ("straightness|d2", "Hom_vs_WT", "Hom walk less straight, day 2"),
                           ("walk_speed_cm_s|d1", "Hom_vs_WT", "Hom walk faster, day 1"),
                           ("immobile_pct|d1", "Hom_vs_WT", "Hom sit still less, day 1"),
                           ("walk_speed_cm_s|d1", "Het_vs_WT", "Het walk slower, day 1")])):
        for mid, con, lab in items:
            if mid == "MM":
                raw, adj = mm(MMr, "geno_x_session", "entrances_per_rev", con), mm(MMa, "geno_x_session_speed", "entrances_per_rev", con)
            elif mid == "CIRC":
                raw, adj = circ(F.A["CIRC"], con), circ(F.B["CIRC_ADJ"], con)
            else:
                raw, adj = F.P(mid, con, raw=True), F.P(mid, con)
            R.append(dict(story=story, label=lab, raw=raw, adj=adj))
    return pd.DataFrame(R)


def lp(p):
    return -np.log10(max(p, 1e-6))


# ============================================================================ page 2: the floor
def page_floor():
    fig, y = F.page("The floor turned at 2.2-5.8 deg/s, set by when a cohort ran, not by the motor setting",
                    "SPEED SUPPLEMENT · 1 · THE FLOOR", number=2)
    F.legend_mice(fig, 0.55, y + 0.02, speed=False)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "The floor's speed changed between cohorts and jumped after the October 2026 motor repair")
    days = sorted(D.ROTDAY["omega"])
    for j, lab in enumerate(("2024", "2026")):
        ds = [d for d in days if d.startswith(lab)]
        ax = F.axes_in(fig, 0.75 + j * 2.45, y + 0.35, 2.25, 1.4)
        xs = [datetime.date.fromisoformat(d) for d in ds]
        for dd, x in zip(ds, xs):
            n = D.ROTDAY["n"][dd]
            ax.scatter([x], [D.ROTDAY["omega"][dd]], s=6 + 26 * min(n, 1000) / 1000, color=F.INK, zorder=3, alpha=0.85)
            ms = [m for m in D.MLIST if F.MICE[m]["s0"] == dd or F.MICE[m]["s1"] == dd]
            for k, m in enumerate(sorted(ms, key=lambda m: G3.index(F.geno(m)))):
                ax.scatter([x], [1.35 - 0.17 * k], s=6, color=F.GCOL[F.geno(m)], marker=F.marker_of(m), lw=0, zorder=3)
        ax.axhline(F.REF, color=F.KICK, lw=0.6, ls=":")
        ax.text(xs[0], F.REF + 0.12, "%.1f: the menu's one speed" % F.REF, fontsize=5, color=F.KICK, ha="left")
        ax.set_ylim(0.2, 6.5)
        ax.set_yticks([2, 3, 4, 5, 6])
        ax.set_title(lab, fontsize=6.5, loc="left")
        ax.tick_params(axis="x", labelsize=5.3, rotation=40)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        if j == 0:
            ax.set_ylabel("Floor speed (deg/s)")
        else:
            ax.annotate("motor broke 10/21;\nrunning again 10/28", xy=(datetime.date(2026, 10, 20), 3.75), fontsize=5.2,
                        color=F.SOFT, ha="center")
    F.put(fig, 0.75, y + 2.1, "Black dot: the day's speed (median of the ride readings; larger = more readings, 55-1,033). Small "
                              "marks at the bottom: the mice that started that day.", 4.75, size=5.8, color=F.SOFT)
    yb = y + 2.55
    F.letter(fig, 0.4, yb, "b", "Every young Hom and every mouse injected before AA ran on the slow 2026 floor")
    ax = F.axes_in(fig, 0.75, yb + 0.35, 2.3, 1.45)
    grp = {m: "%s %s" % (F.geno(m), F.MICE[m]["age_group"]) for m in D.MLIST}
    order = ["WT young", "WT old", "Het young", "Het old", "Hom young", "Hom old"]
    rng = np.random.RandomState(4)
    for k, g in enumerate(order):
        ms = [m for m in D.MLIST if grp[m] == g]
        for m in ms:
            yr = F.MICE[m]["year"]
            inj = F.MICE[m]["injected_before"]
            ax.scatter([k + (rng.rand() - 0.5) * 0.4], [OM[m]], s=16, marker=F.marker_of(m),
                       color="#c8a24a" if yr == 2026 else "#3d7ea6", edgecolor=F.INK if inj else "white", lw=0.8 if inj else 0.4, zorder=3)
        ax.plot([k - 0.28, k + 0.28], [np.median([OM[m] for m in ms])] * 2, color=F.INK, lw=1.1)
    items = []
    for k, g in enumerate(G3):
        r = S.two([OM[m] for m in D.by(g=g, age="old")], [OM[m] for m in D.by(g=g, age="young")])
        items.append((2 * k, 2 * k + 1, r["p"]))
    top = max(OM.values())
    ax.set_xticks(range(6))
    ax.set_xticklabels(["WT\nyoung", "WT\nold", "Het\nyoung", "Het\nold", "Hom\nyoung", "Hom\nold"])
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.6, 5.6)
    ax.set_ylabel("Floor speed during the run (deg/s)")
    ax.axhline(F.REF, color=F.KICK, lw=0.6, ls=":")
    F.brackets(ax, items, top)
    hs = [Line2D([], [], ls="", marker="o", ms=4, mfc="#3d7ea6", mec="white", label="2024"),
          Line2D([], [], ls="", marker="o", ms=4, mfc="#c8a24a", mec="white", label="2026"),
          Line2D([], [], ls="", marker="o", ms=4, mfc="white", mec=F.INK, mew=0.9, label="injected before AA")]
    W, H = fig.get_size_inches()
    fig.legend(handles=hs, frameon=False, fontsize=5.6, loc="upper left", ncol=3, handletextpad=0.2, columnspacing=0.8,
               bbox_to_anchor=(3.45 / W, 1 - (yb + 1.55) / H))
    T = pd.DataFrame([dict(group=g, n=len([m for m in D.MLIST if grp[m] == g]),
                           slow=sum(1 for m in D.MLIST if grp[m] == g and F.MICE[m]["rot_bin"] == "slow"),
                           y2026=sum(1 for m in D.MLIST if grp[m] == g and F.MICE[m]["year"] == 2026),
                           inj=sum(1 for m in D.MLIST if grp[m] == g and F.MICE[m]["injected_before"])) for g in order])
    ax = F.axes_in(fig, 3.45, yb + 0.35, 2.1, 1.3)
    ax.axis("off")
    for j, h in enumerate(["Group", "n", "slow\nfloor", "run in\n2026", "injected\nbefore AA"]):
        ax.text([0, 0.36, 0.5, 0.67, 0.86][j], 1.0, h, fontsize=5.4, weight="bold", va="top", ha="left" if j == 0 else "center",
                transform=ax.transAxes)
    for i, r in T.iterrows():
        yy = 0.78 - i * 0.13
        for j, c in enumerate([r.group, r.n, r.slow, r.y2026, r.inj]):
            ax.text([0, 0.36, 0.5, 0.67, 0.86][j], yy, str(c), fontsize=5.6, va="top", ha="left" if j == 0 else "center",
                    transform=ax.transAxes, color=F.GCOL[r.group.split()[0]] if j == 0 else F.INK)
    yc = yb + 2.55
    pr = np.load(os.path.join(F.HERE, "pair_1007.npz"))
    sl = np.polyfit(pr["t"], pr["diff"], 1)
    F.letter(fig, 0.4, yc, "c", "One day with both frames: the floor turned at %.2f deg/s; the ride method read %.2f (%.0f%% high)"
             % (sl[0], np.median(pr["rides"]), 100 * (np.median(pr["rides"]) / sl[0] - 1)))
    ax = F.axes_in(fig, 0.75, yc + 0.35, 2.3, 1.3)
    ax.plot(pr["t"], pr["diff"] - pr["diff"][0], color=F.INK, lw=0.8)
    tt = np.array([pr["t"].min(), pr["t"].max()])
    ax.plot(tt, sl[0] * tt + sl[1] - pr["diff"][0], color=F.KICK, lw=0.8, ls="--")
    ax.set_xlabel("Time in the session (s)")
    ax.set_ylabel("Room angle minus floor angle (deg)")
    ax.set_title("Direct: the two frames drift apart at %.2f deg/s" % sl[0], fontsize=6, loc="left")
    ax = F.axes_in(fig, 3.45, yc + 0.35, 2.1, 1.3)
    r = pr["rides"]
    ax.scatter(np.random.RandomState(1).rand(r.size) * 0.3 - 0.15, r, s=14, color=F.SOFT, zorder=3)
    ax.plot([-0.25, 0.25], [np.median(r)] * 2, color=F.INK, lw=1.2)
    ax.axhline(sl[0], color=F.KICK, lw=0.8, ls="--")
    ax.text(0.3, sl[0] + 0.02, "direct %.2f" % sl[0], fontsize=5.4, color=F.KICK, va="bottom")
    ax.text(0.3, np.median(r), "rides %.2f" % np.median(r), fontsize=5.4, color=F.INK, va="center")
    ax.set_xlim(-0.5, 0.9)
    ax.set_xticks([])
    ax.set_ylabel("Ride readings (deg/s)")
    ax.set_title("Ride method on the room track alone\n(%d readings, 4 s each)" % r.size, fontsize=6, loc="left")
    F.textcol(fig, 1.35, [
        ("The claim", "The arena floor did not turn at one speed. It turned at about 5.0-5.6 deg/s in spring 2024, 4.3-4.5 in "
                      "October 2024, 2.2-3.7 from March to September 2026 and 5.3-5.8 after the late-October 2026 repair, "
                      "while the motor setting (MotorState 4) never changed. The speed went with the cohort, and the cohorts "
                      "went with the groups we want to compare."),
        ("How it was read", "A mouse that sits still rides the floor, so its angle in the room grows at the floor's speed. "
                            "Every 4-s stretch at a constant distance from the center and a steady angular speed is one "
                            "reading; each day's speed is the median of that day's readings."),
        ("What it shows", "a: the daily speeds. b: young Hom ran at 2.8-3.5 deg/s and old Hom at 4.3-5.5, with no overlap; "
                          "young WT ran fast; all 18 injected mice are 2026 slow-floor mice. c: on 10/7/2025 the tracker saved "
                          "one session in both frames, which gives the true speed directly. The ride method came out 6%% high "
                          "there, from only %d readings." % r.size),
        ("Caveats", "One check day, and a short session. If the ride method reads a few percent high on every day, the "
                    "differences between cohorts stand, but the absolute speeds are slightly overstated."),
        ("To fix", "Time ten turns of a mark on the floor before each run day and write the speed on the run sheet; or save "
                   "the arena-frame file with every session."),
    ])
    F.save(fig, OUT, "02_the_floor")


# ============================================================================ page 3: what speed does to each measure
def page_effects():
    fits = {mid: speed_fit(mid) for mid, _l, _f in MEASURES}
    fig, y = F.page("What floor speed does to each measure: avoidance counts and movement rise with it; entrances per turn "
                    "and where the mice wait do not", "SPEED SUPPLEMENT · 2 · WHAT SPEED MOVES", number=3)
    F.legend_mice(fig, 0.55, y + 0.02, speed=False)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "Change per 1 deg/s of floor speed, in standard deviations of each measure (shared slope, 95% CI)")
    ax = F.axes_in(fig, 2.55, y + 0.3, 2.9, 4.6)
    ys = np.arange(len(MEASURES))[::-1]
    for yy, (mid, lab, fam) in zip(ys, MEASURES):
        f = fits[mid]
        col = FAMC[fam]
        ax.plot([f["zlo"], f["zhi"]], [yy, yy], color=col, lw=1.0)
        ax.scatter([f["z"]], [yy], s=16, color=col if f["p"] < 0.05 else "white", edgecolor=col, lw=0.9, zorder=3)
        st_ = F.stars(f["p"])
        if st_:
            ax.text(f["zhi"] + 0.04, yy, st_, fontsize=6.2, va="center", color=col, weight="bold")
    ax.axvline(0, color=F.FAINT, lw=0.6)
    ax.set_yticks(ys)
    ax.set_yticklabels([lab for _m, lab, _f in MEASURES], fontsize=5.8)
    for t, (_m, _l, fam) in zip(ax.get_yticklabels(), MEASURES):
        t.set_color(FAMC[fam])
    ax.set_ylim(-0.7, len(MEASURES) - 0.3)
    ax.set_xlabel("s.d. per deg/s of floor speed")
    ax.tick_params(axis="y", length=0)
    hs = [Line2D([], [], color=c, marker="o", ms=4, lw=1, label=f) for f, c in FAMC.items()]
    ax.legend(handles=hs, frameon=False, fontsize=5.4, loc="lower right", handlelength=1.2)
    F.put(fig, 0.75, y + 5.3, "Filled = slope P < 0.05 (stars). Shared slope: value ~ genotype + floor speed, one number per "
                               "mouse, all 56 mice.", 4.8, size=5.8, color=F.SOFT)
    yb = y + 5.75
    F.letter(fig, 0.4, yb, "b", "Faster floors add shocks and path in every genotype; entrances per turn stay flat")
    ex = [("shocks|d1", "Day-1 shocks"), ("entrances_per_rev|d2", "Day-2 entrances per turn"), ("path_m|d2", "Day-2 path in the room (m)"),
          ("strategy_score|d2", "Day-2 strategy score")]
    for j, (mid, lab) in enumerate(ex):
        ax = F.axes_in(fig, 0.75 + j * 1.25, yb + 0.5, 0.95, 1.05)
        speed_slope_panel(ax, mid, lab)
        f = fits[mid]
        ax.set_title("slope %s\ngenotypes differ\nin slope: %s" % (F.pstars(f["p"]), F.pstr(f["pint"])), fontsize=5.3, loc="left",
                     color=F.SOFT)
        ax.xaxis.label.set_size(6)
        ax.yaxis.label.set_size(6)
        ax.tick_params(labelsize=5.6)
    yc = yb + 2.2
    nint = sum(1 for mid, _l, _f in MEASURES if fits[mid]["pint"] < 0.05)
    F.letter(fig, 0.4, yc, "c", "The genotypes share one speed slope for %d of %d measures; the exceptions are listed below"
             % (len(MEASURES) - nint, len(MEASURES)))
    rows = [(lab, fits[mid]["pint"]) for mid, lab, _f in MEASURES if fits[mid]["pint"] < 0.1]
    txt = "; ".join("%s (%s)" % (lab, F.pstr(p)) for lab, p in rows) if rows else "none"
    F.put(fig, 0.75, yc + 0.18, "Genotype x speed interaction (do the genotypes' slopes differ?), P < 0.1: %s. Where it is small the "
                                "adjustment moves every mouse by the same rule; where it is not, the adjusted comparison leans on "
                                "the slope of the genotypes with more speed spread." % txt, 4.8, size=6.2)
    F.textcol(fig, 1.6, [
        ("The claim", "Floor speed moves the raw counts: per 1 deg/s, day-1 shocks rise by %.1f per session and day-2 path in "
                      "the room by %.1f m. It barely moves entrances per turn, where the mice wait (strategy score, pre-shock "
                      "share, turning back) or how scattered they are." % (fits["shocks|d1"]["b"], fits["path_m|d2"]["b"])),
        ("Why", "A mouse that stops walking is carried into the zone once per turn of the floor, so a faster floor brings more "
                "entries per minute and more passive path. Entrances per turn divide that out. Where a mouse waits is a "
                "choice of place, which the floor's speed does not set."),
        ("How to read it", "a: each measure's change per deg/s of floor speed, in units of its own s.d., so measures with "
                           "different units share one axis. b: four examples with raw values; each line is one genotype with "
                           "the shared slope; diamonds mark the group means at %.1f deg/s. c: whether one slope fits all "
                           "three genotypes." % F.REF),
        ("What it means for the menu", "Every comparison in the story menu is made at %.1f deg/s: each mouse's value is "
                                       "moved along the shared slope of its measure. For measures with a flat slope this "
                                       "changes almost nothing." % F.REF),
    ])
    F.save(fig, OUT, "03_what_speed_moves")
    return fits


# ============================================================================ page 4: how the adjustment works
def page_method():
    d1r = F.res("shocks|d1", "Hom_vs_WT", raw=True)
    d1a = F.res("shocks|d1", "Hom_vs_WT")
    fig, y = F.page("How the menu factors speed in: every mouse is moved along its measure's speed slope to %.1f deg/s, and "
                    "every comparison also runs inside speed bands" % F.REF, "SPEED SUPPLEMENT · 3 · THE ADJUSTMENT", number=4)
    F.legend_mice(fig, 0.55, y + 0.02, speed=False)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "Each mouse slides along the shared slope to %.1f deg/s (day-1 shocks)" % F.REF)
    ax = F.axes_in(fig, 0.75, y + 0.45, 2.3, 1.6)
    raw, adj = F.VALS_RAW["shocks|d1"], F.VALS["shocks|d1"]
    b = F.B["SLOPE"]["shocks|d1"][0]
    for m in D.MLIST:
        F.scatter_mouse(ax, OM[m], raw[m], m, size=12, alpha=0.35)
        F.scatter_mouse(ax, F.REF + (int(m) % 9 - 4) * 0.03, adj[m], m, size=12)
    for m in ("1603", "1645", "814", "894", "1652"):
        ax.annotate("", xy=(F.REF, adj[m]), xytext=(OM[m], raw[m]), arrowprops=dict(arrowstyle="-|>", color=F.SOFT, lw=0.6,
                                                                                  shrinkA=2, shrinkB=2))
    ax.axvline(F.REF, color=F.KICK, lw=0.6, ls=":")
    ax.set_xlabel("Floor speed (deg/s)")
    ax.set_ylabel("Day-1 shocks per session")
    ax.set_title("Faint: raw, at the mouse's own speed. Solid: moved to %.1f deg/s\n(slope %+.1f shocks per deg/s; arrows: five examples)"
                 % (F.REF, b), fontsize=5.6, loc="left", color=F.SOFT)
    ax2 = F.axes_in(fig, 3.45, y + 0.45, 2.1, 1.6)
    speed_slope_panel(ax2, "shocks|d1", "Day-1 shocks (raw)")
    yb = y + 2.55
    F.letter(fig, 0.4, yb, "b", "Raw, Hom took fewer day-1 shocks than WT (%s); at %.1f deg/s the gap is %s"
             % (F.pstr(d1r["p"]), F.REF, F.pstr(d1a["p"])))
    ax = F.axes_in(fig, 0.75, yb + 0.7, 1.25, 1.15)
    F.geno_dots(ax, "shocks|d1", "Shocks per session", title="Raw", names=None, raw=True)
    ax = F.axes_in(fig, 0.75 + 1.68, yb + 0.7, 1.25, 1.15)
    F.geno_dots(ax, "shocks|d1", "Shocks per session", title="At %.1f deg/s" % F.REF, names=None)
    ax = F.axes_in(fig, 0.75 + 2 * 1.68, yb + 0.7, 1.25, 1.15)
    speed_bands(ax, "shocks|d1", "Shocks per session (raw)")
    ax.set_title("Inside speed bands (raw)\nvan Elteren, all bands: %s" % F.pstr(F.res("shocks|d1", "Hom_vs_WT").get("p_van Elteren", np.nan)),
                 fontsize=5.8, loc="left", color=F.SOFT)
    yc = yb + 2.45
    F.letter(fig, 0.4, yc, "c", "Young Hom never ran near %.1f deg/s, so their moved values lean on the slope from the other mice" % F.REF)
    ax = F.axes_in(fig, 0.75, yc + 0.35, 4.75, 1.25)
    order = ["WT young", "WT old", "Het young", "Het old", "Hom young", "Hom old"]
    for k, g in enumerate(order):
        ms = D.by(g=g.split()[0], age=g.split()[1])
        w = [OM[m] for m in ms]
        ax.plot([min(w), max(w)], [k, k], color=F.GCOL[g.split()[0]], lw=4, alpha=0.35, solid_capstyle="round")
        for m in ms:
            F.scatter_mouse(ax, OM[m], k, m, size=12)
    ax.axvline(F.REF, color=F.KICK, lw=0.8, ls=":")
    ax.text(F.REF + 0.03, 5.5, "%.1f deg/s" % F.REF, fontsize=5.6, color=F.KICK)
    ax.set_yticks(range(6))
    ax.set_yticklabels(order, fontsize=6)
    ax.set_ylim(-0.6, 5.8)
    ax.invert_yaxis()
    ax.set_xlabel("Floor speed of each mouse's run (deg/s)")
    F.textcol(fig, 1.6, [
        ("The claim", "The menu compares every value at one floor speed, %.1f deg/s, the median of the 56 mice. Raw "
                      "differences that came from the floor disappear (Hom's day-1 shocks), and differences between groups "
                      "that ran on the same mix of speeds stay (Het)." % F.REF),
        ("How it works", "For each measure, one slope for floor speed is fitted across all mice with genotype in the model "
                         "(a). Each mouse's value is moved along that slope from its own speed to %.1f deg/s; the usual tests "
                         "then run on the moved values. Every genotype comparison also gets a van Elteren test: Wilcoxon "
                         "inside the slow, medium and fast bands, combined, with no slope at all (b, right). The menu "
                         "reports the smaller P, the same generous rule as everywhere." % F.REF),
        ("Sessions and models", "Session values move the same way with that day's speed. Mixed models over s1-s16 carry floor "
                                "speed and speed x session; the criterion uses a Cox model with speed and a log-rank test inside "
                                "speed bands; preferred directions use a permutation that swaps labels only within a band."),
        ("What it assumes", "That a faster floor changes a measure by the same amount in every genotype (page 3, c), and that "
                            "a straight line is good enough between 2.2 and 5.8 deg/s. Young Hom sit at one end (c), so their "
                            "moved values depend on WT and Het mice that ran at both ends; the band test does not."),
    ])
    F.save(fig, OUT, "04_the_adjustment")


# ============================================================================ page 5: what survives
def page_survives():
    H = headline_rows()
    H["status"] = np.where((H.raw < 0.05) & (H.adj < 0.05), "holds",
                           np.where((H.raw < 0.05) & (H.adj >= 0.05), "goes", np.where((H.raw >= 0.05) & (H.adj < 0.05), "new", "neither")))
    H.to_csv(os.path.join(OUT, "headlines_raw_vs_one_speed.csv"), index=False)
    nh, ng, nn = (H.status == "holds").sum(), (H.status == "goes").sum(), (H.status == "new").sum()
    fig, y = F.page("What survives: %d of %d headlines hold at one floor speed, %d go, and %d appear only once speed is "
                    "matched" % (nh, len(H), ng, nn), "SPEED SUPPLEMENT · 4 · WHAT SURVIVES", number=5)
    y += 0.1
    F.letter(fig, 0.4, y + 0.08, "a", "Every headline raw (open) and at one floor speed (filled); right of the dashed line = P < 0.05")
    ax = F.axes_in(fig, 2.75, y + 0.5, 2.75, 7.6)
    yy, ticks, labs, cols = 0, [], [], []
    last = None
    for _i, r in H.iterrows():
        if r.story != last:
            if last is not None:
                yy += 0.6
            ax.text(-0.02, -(yy), r.story, transform=blended_transform_factory(ax.transAxes, ax.transData), fontsize=6.2,
                    weight="bold", ha="right", va="center", color=F.KICK)
            yy += 0.9
            last = r.story
        c = {"holds": HOLD, "goes": GOES, "new": NEW, "neither": F.FAINT}[r.status]
        a_, b_ = lp(r.raw), lp(r.adj)
        ax.plot([a_, b_], [-yy, -yy], color=c, lw=1.2, alpha=0.8)
        ax.scatter([a_], [-yy], s=18, facecolor="white", edgecolor=c, lw=1.0, zorder=3)
        ax.scatter([b_], [-yy], s=18, color=c, zorder=4)
        ticks.append(-yy)
        labs.append(r.label)
        cols.append(c)
        yy += 1
    ax.axvline(lp(0.05), color=F.INK, lw=0.7, ls="--")
    ax.set_yticks(ticks)
    ax.set_yticklabels(labs, fontsize=5.9)
    for t, c in zip(ax.get_yticklabels(), cols):
        t.set_color(c if c != F.FAINT else F.SOFT)
    pt = [0.5, 0.1, 0.05, 0.01, 0.001, 0.0001]
    ax.set_xticks([lp(p) for p in pt])
    ax.set_xticklabels(["0.5", "0.1", "0.05", "0.01", "0.001", "0.0001"], fontsize=6)
    ax.set_xlim(0, 4.3)
    ax.set_ylim(-yy + 0.4, 0.6)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_ticks_position("top")
    hs = [Line2D([], [], color=HOLD, marker="o", lw=1.2, label="holds (P < 0.05 both)"),
          Line2D([], [], color=GOES, marker="o", lw=1.2, label="goes at one speed"),
          Line2D([], [], color=NEW, marker="o", lw=1.2, label="new at one speed"),
          Line2D([], [], color=F.FAINT, marker="o", lw=1.2, label="neither")]
    ax.legend(handles=hs, frameon=False, fontsize=5.6, loc="lower right", handlelength=1.4)
    goes = "; ".join("%s (%s to %s)" % (r.label, F.pstr(r.raw).replace("P ", ""), F.pstr(r.adj).replace("P ", ""))
                     for _i, r in H[H.status == "goes"].iterrows())
    new = "; ".join("%s (%s to %s)" % (r.label, F.pstr(r.raw).replace("P ", ""), F.pstr(r.adj).replace("P ", ""))
                    for _i, r in H[H.status == "new"].iterrows())
    F.textcol(fig, 1.25, [
        ("The question", "Does anything survive once floor speed is factored in, and can the menu stay simple? Yes to both: "
                         "most stories hold, and the menu shows the speed-matched numbers in the same figures."),
        ("How to read it", "One row per headline in the menu. Open circle: the generous P before the speed adjustment. "
                           "Filled circle: the same contrast at one floor speed (the menu's number). The farther right, the "
                           "smaller the P; the dashed line is P = 0.05."),
        ("What goes", goes + "."),
        ("What is new", (new + ". The Hom ones rest on moving the slow-floor Hom up to %.1f deg/s (page 4, c), and for "
                         "walking speed, stillness and habituation concentration the genotypes' speed slopes differ "
                         "(page 3, c), so read them as speed-dependent. Het's shock result comes from the test inside "
                         "speed bands." % F.REF) if new else "Nothing."),
        ("Verdict", "Factoring speed in costs the menu two raw stories (four rows), both of which the menu already doubted "
                    "(Hom's day-1 advantage over WT and the Hom age effect), and keeps the rest: mutants improve less, Hom reach criterion "
                    "sooner, Het wait farther from the zone, and Hom explore less in habituation. Raw numbers alone would "
                    "not be safe here, because speed lines up with genotype, age, year and injection."),
    ], w=2.05)
    F.save(fig, OUT, "05_what_survives")
    return H


# ============================================================================ page 6: curves and models
def page_curves():
    fig, y = F.page("Learning curves before and after the speed adjustment, and what to change for the next round",
                    "SPEED SUPPLEMENT · 5 · CURVES, MODELS AND NEXT STEPS", number=6)
    F.legend_mice(fig, 0.55, y + 0.02, speed=False)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "Raw, Hom sat below WT in s1-s4 and s9; at one floor speed only s2 and s4 differ (shocks)")
    for j, (raw, lab) in enumerate(((True, "Raw"), (False, "At %.1f deg/s" % F.REF))):
        ax = F.axes_in(fig, 0.75 + j * 2.45, y + 0.5, 2.0, 1.3)
        groups = {g: D.by(g=g) for g in G3}
        piv = {}
        for g, ms in groups.items():
            ks, m, se, p = D.curve("shocks", ms, range(1, 17), raw=raw)
            piv[g] = p
            for seg in (ks <= 8, ks >= 9):
                ax.plot(ks[seg], m[seg], color=F.GCOL[g], lw=1.3, marker="o", ms=2.2, label=g if seg[0] else None)
                ax.fill_between(ks[seg], (m - se)[seg], (m + se)[seg], color=F.GCOL[g], alpha=0.13, lw=0)
        ax.axvline(8.5, color=F.FAINT, lw=0.6, ls="--")
        ax.set_xticks([1, 4, 8, 9, 12, 16])
        ax.set_xlim(0.4, 16.6)
        ax.set_ylim(0, 20)
        ax.set_xlabel("Training session")
        ax.set_ylabel("Shocks per session")
        ax.set_title(lab, fontsize=6.3, loc="left", pad=22)
        ax.grid(axis="y", color=F.GRID, lw=0.5)
        if j == 0:
            ax.legend(frameon=False, fontsize=5.6, loc="upper right")
        from pages_a import session_marks
        session_marks(ax, piv, [("WT", "Het", F.GCOL["Het"]), ("WT", "Hom", F.GCOL["Hom"])])
    yb = y + 2.4
    F.letter(fig, 0.4, yb, "b", "The flatter mutant curves hold with floor speed in the mixed models")
    ax = F.axes_in(fig, 0.75, yb + 0.25, 4.8, 1.6)
    ax.axis("off")
    rows = []
    for meas, lab in (("entrances_per_rev", "Entrances per turn"), ("entrances", "Entrances (log)"), ("shocks", "Shocks (log)"),
                      ("time_in_zone_pct", "Time in the zone"), ("strategy_score", "Strategy score"), ("R", "Concentration R")):
        rr = [lab]
        for term in ("[T.Het]:sc", "[T.Hom]:sc"):
            rr.append(F.mm(meas, "geno_x_session", term, raw=True)[0])
            rr.append(F.mm(meas, "geno_x_session", term)[0])
        rows.append(rr)
    xs = [0, 0.36, 0.52, 0.68, 0.84]
    for j, h in enumerate(["Session values (s1-s16)", "Het x session\nwithout speed", "Het x session\nwith speed",
                           "Hom x session\nwithout speed", "Hom x session\nwith speed"]):
        ax.text(xs[j], 1.0, h, fontsize=5.6, weight="bold", va="top", ha="left" if j == 0 else "center", transform=ax.transAxes)
    for i, r in enumerate(rows):
        yy = 0.72 - i * 0.12
        for j, c in enumerate(r):
            txt = c if j == 0 else ("%s %s" % (F.pstr(c).replace("P ", ""), F.stars(c))).strip()
            ax.text(xs[j], yy, txt, fontsize=5.8, va="top", ha="left" if j == 0 else "center", transform=ax.transAxes,
                    color=F.INK if (j == 0 or c < 0.05) else F.FAINT)
    F.put(fig, 0.75, yb + 1.95, "P of the genotype x session term (does the curve's slope differ from WT's?) in mixed models over "
                                "s1-s16 with the mouse as a random effect; 'with speed' adds floor speed and speed x session. "
                                "Gray = P ≥ 0.05.", 4.8, size=5.8, color=F.SOFT)
    yc = yb + 2.55
    F.letter(fig, 0.4, yc, "c", "What to change: measure the speed, fix it, and run the groups side by side")
    F.put(fig, 0.75, yc + 0.2,
          "1. Measure it every run day: time ten turns of a mark on the floor (6 deg/s = one turn a minute), or save the "
          "arena-frame file with every session. Write it on the run sheet.\n"
          "2. Fix it: calibrate the motor to one speed and check it after any repair; the October 2026 repair moved it from "
          "about 3 to about 5.5 deg/s.\n"
          "3. Design around it: put both groups of every planned comparison (genotypes, ages, injected or not) in the same "
          "weeks, so speed cannot line up with a group again.\n"
          "4. Analyze with it: report entrances per turn next to raw counts, and keep the floor speed of each day as a "
          "covariate, as the menu now does.\n"
          "5. Until the old runs are repeated, read any young-Hom or injection result as a slow-floor result.", 4.8, size=6.6)
    F.textcol(fig, 1.6, [
        ("The claim", "Session by session, the raw curves show Hom below WT for most of day 1; at one floor speed the "
                      "curves overlap except in s2 and s4. The finding that the mutant curves are flatter than WT's does not "
                      "depend on speed: the mixed models give the same answer with speed in them."),
        ("How to read it", "a: mean ± s.e.m. per genotype; stars over a session: Het (orange) or Hom (purple) differ from "
                           "WT there (P < 0.05). Left raw, right with every session moved to %.1f deg/s using that day's "
                           "measured speed. b: mixed-model P without and with floor speed. c: what would remove the "
                           "problem in the next cohorts." % F.REF),
    ])
    F.save(fig, OUT, "06_curves_models_next")


# ============================================================================ page 1: the menu
def page_menu(H, fits):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(8.5, 11))
    F.put(fig, 0.7, 0.8, "BARRY LAB · KCNT1 ACTIVE AVOIDANCE · SPEED SUPPLEMENT, 2026-11-23", 7.2, size=7.2, color=F.KICK, weight="bold")
    F.put(fig, 0.7, 1.05, "Floor speed in KCNT1 active avoidance", 7.2, size=17, weight="bold")
    F.put(fig, 0.7, 1.5, "A supplement to the KCNT1 AA story menu: what the arena's turning speed did to the numbers, how the "
                         "menu factors it in, and which stories still stand.", 7.2, size=8, color=F.SOFT)
    F.put(fig, 0.72, 2.2, "The short version", 7.2, size=7.5, weight="bold")
    nh, ng, nn = (H.status == "holds").sum(), (H.status == "goes").sum(), (H.status == "new").sum()
    F.put(fig, 0.72, 2.45,
          "The arena floor is supposed to turn at one speed. It did not: from 2.2 to 5.8 deg/s depending on when a cohort ran, "
          "with the motor setting unchanged. A faster floor carries a resting mouse into the zone more often, so raw shocks, "
          "entrances and path rise with it (day-1 shocks by %.1f per session for every deg/s). That would be noise if every "
          "group had run at every speed, but the cohorts lined up with the groups: every young Hom and every injected mouse "
          "ran on the slow 2026 floor, every old Hom on the faster 2024 one. The story menu therefore compares every value at "
          "one floor speed, %.1f deg/s, moving each mouse along its measure's speed slope and adding a test inside speed "
          "bands. Of %d headlines, %d hold, %d go (Hom's raw day-1 advantage and the Hom age effect) and %d appear only once "
          "speed is matched. The fix for the next round is cheap: measure the speed every run day, calibrate the motor, and "
          "run the groups of each comparison in the same weeks."
          % (fits["shocks|d1"]["b"], F.REF, len(H), nh, ng, nn), 7.0, size=7.4)
    F.put(fig, 0.72, 4.15, "The pages", 7.2, size=7.5, weight="bold")
    rows = [
        ("2", "The floor", "Floor speed by day and cohort; who ran at which speed; the one-day check against a direct measurement.",
         "2.2-5.8 deg/s; young Hom 2.8-3.5, old Hom 4.3-5.5"),
        ("3", "What speed moves", "Each measure's change per deg/s; which genotypes share a slope.",
         "day-1 shocks %+.1f per deg/s (%s); entrances per turn %s" % (fits["shocks|d1"]["b"], F.pstr(fits["shocks|d1"]["p"]),
                                                                       F.pstr(fits["entrances_per_rev|d2"]["p"]))),
        ("4", "The adjustment", "How each mouse is moved to one speed; the band test; where the adjustment leans on other mice.",
         "Hom vs WT day-1 shocks: raw %s, one speed %s" % (F.pstr(F.P("shocks|d1", "Hom_vs_WT", raw=True)), F.pstr(F.P("shocks|d1", "Hom_vs_WT")))),
        ("5", "What survives", "Every headline of the menu, raw against one speed.", "%d hold, %d go, %d new" % (nh, ng, nn)),
        ("6", "Curves, models, next steps", "Learning curves raw and at one speed; mixed models with speed; what to change.",
         "Hom x session with speed %s" % F.pstr(F.mm("entrances_per_rev", "geno_x_session", "[T.Hom]:sc")[0])),
    ]
    ax = F.axes_in(fig, 0.7, 4.4, 7.3, 3.2)
    ax.axis("off")
    hx = [0, 0.05, 0.25, 0.68]
    for j, h in enumerate(["Page", "Story", "What it shows", "Best number"]):
        ax.text(hx[j], 1, h, fontsize=6.6, weight="bold", va="top", color=F.SOFT, transform=ax.transAxes)
    yy = 0.9
    for r in rows:
        cells = [r[0], F.wrap(r[1], 1.3, 6.8), F.wrap(r[2], 3.0, 6.8), F.wrap(r[3], 2.2, 6.8)]
        nl = max(c.count("\n") + 1 for c in cells)
        for j, c in enumerate(cells):
            ax.text(hx[j], yy, c, fontsize=6.8, va="top", weight="bold" if j == 1 else "normal", transform=ax.transAxes, color=F.INK)
        yy -= 0.05 * nl + 0.06
        ax.plot([0, 1], [yy + 0.03, yy + 0.03], color=F.GRID, lw=0.6, transform=ax.transAxes)
    F.put(fig, 0.72, 7.85, "Tables: headlines_raw_vs_one_speed.csv (page 5) and floor_speed_slopes.csv (page 3); every result at "
                          "one speed and raw is in the story menu's tables folder. * P < 0.05, ** P < 0.01, *** P < 0.001.",
          7.2, size=6.4, color=F.SOFT)
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, F.FOOT, fontsize=6.5, color=F.FAINT, ha="left", va="bottom")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "1", fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    F.save(fig, OUT, "01_menu")


def package(fits):
    for sub in ("pages", "tables", "code"):
        os.makedirs(os.path.join(DEST, sub), exist_ok=True)
        for f in glob.glob(os.path.join(DEST, sub, "*")):
            os.remove(f)
    pdfs = sorted(glob.glob(os.path.join(OUT, "*.pdf")))
    for f in pdfs + sorted(glob.glob(os.path.join(OUT, "*.png"))):
        shutil.copy2(f, os.path.join(DEST, "pages", os.path.basename(f)))
    doc = pymupdf.open()
    for f in pdfs:
        with pymupdf.open(f) as d:
            doc.insert_pdf(d)
    doc.set_metadata({"title": "Floor speed in KCNT1 active avoidance", "subject": "KCNT1 AA speed supplement, 2026-11-23",
                      "author": "Barry Lab"})
    doc.save(os.path.join(DEST, "KCNT1_AA_Speed_Supplement_112326.pdf"), garbage=3, deflate=True)
    shutil.copy2(os.path.join(OUT, "headlines_raw_vs_one_speed.csv"), os.path.join(DEST, "tables", "headlines_raw_vs_one_speed.csv"))
    pd.DataFrame([dict(id=mid, label=lab, family=fam, slope_per_deg_s=fits[mid]["b"], se=fits[mid]["se"], p=fits[mid]["p"],
                       sd_per_deg_s=fits[mid]["z"], genotype_x_speed_p=fits[mid]["pint"],
                       **{"slope_%s" % g: fits[mid]["slopes"].get(g, (np.nan,))[0] for g in G3})
                  for mid, lab, fam in MEASURES]).to_csv(os.path.join(DEST, "tables", "floor_speed_slopes.csv"), index=False)
    for f in ("s1_speed_supplement.py", "a4_speed.py", "probe_pair.py"):
        shutil.copy2(os.path.join(F.HERE, f), os.path.join(DEST, "code", f))
    print(doc.page_count, "pages ->", DEST)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    page_floor()
    fits = page_effects()
    page_method()
    H = page_survives()
    page_curves()
    page_menu(H, fits)
    package(fits)
