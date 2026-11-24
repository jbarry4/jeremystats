"""Stories 6-7 (H3 numbers, path shape), validation, what next, and the menu. Round 2: the habituation-to-day-2
occupancy progression (story 6a), brackets and per-session stars, headings that state the finding."""
import os

import numpy as np
from matplotlib.patches import FancyBboxPatch
from statsmodels.stats.power import TTestIndPower

import figlib_aa as F
import menu_data as D
import stats_lib as S
from pages_a import curves, G3

OUT = os.path.join(F.HERE, "out")
CRIT = "criterion|sessions_to_criterion"


def adj(mid, g="Het"):
    return F.pstr(F.P(mid, "%s_vs_WT_adj_age" % g))


def robust_out(v):
    """Mice more than 3.5 robust s.d. (1.4826 x MAD) from their genotype's median (same rule as the analysis)."""
    out = set()
    for g in G3:
        ms = [m for m in v if F.geno(m) == g and np.isfinite(v[m])]
        x = np.array([v[m] for m in ms])
        if x.size < 4:
            continue
        med = np.median(x)
        mad = 1.4826 * np.median(np.abs(x - med))
        if mad > 0:
            out |= {m for m, xx in zip(ms, x) if abs(xx - med) / mad > 3.5}
    return out


def crit_p(vv, con, raw):
    """Criterion, b against WT: unstratified survival tests (raw) or Cox with floor speed + log-rank inside speed bands."""
    from statsmodels.duration.hazard_regression import PHReg
    from statsmodels.duration.survfunc import survdiff
    g = con.split("_")[0]
    ms = [m for m in vv if F.geno(m) in ("WT", g)]
    t = np.array([min(vv[m], 16.0) for m in ms])
    e = np.array([1 if vv[m] <= 16 else 0 for m in ms])
    isb = np.array([1.0 if F.geno(m) == g else 0.0 for m in ms])
    if raw:
        return S.surv_two(t[isb == 0], e[isb == 0], t[isb == 1], e[isb == 1])["p"]
    om = np.array([F.MICE[m]["omega"] for m in ms])
    band = np.array([F.MICE[m]["rot_bin"] for m in ms])
    ps = []
    try:
        fit = PHReg(t, np.c_[isb, om], status=e, ties="efron").fit()
        ps.append(float(np.asarray(fit.pvalues)[0]))
    except Exception:  # noqa: BLE001
        pass
    for wt in (None, "gb"):
        try:
            ps.append(float(survdiff(t, e, isb, strata=band, weight_type=wt)[1]))
        except Exception:  # noqa: BLE001
            pass
    ps = [x for x in ps if np.isfinite(x)]
    return min(ps) if ps else np.nan


def sens_p(mid, con, drop, raw=False):
    """Generous P of one headline contrast after leaving out a set of mice; at one floor speed unless raw."""
    import pandas as pd
    import statsmodels.formula.api as smf
    v = (F.VALS_RAW if raw else F.VALS)[mid]
    sets = {"none": set(), "461, 462, 457": {"461", "462", "457"},
            "injected within 7 days": {m for m in D.MLIST if F.MICE[m]["injected_7d"]},
            "all injected before AA": {m for m in D.MLIST if F.MICE[m]["injected_before"]},
            "2024 mice only": {m for m in D.MLIST if F.MICE[m]["year"] != 2024},
            "2026 mice only": {m for m in D.MLIST if F.MICE[m]["year"] != 2026}}
    if mid == CRIT and drop == "robust outliers":
        return np.nan          # no outlier rule for a time-to-criterion measure
    dset = robust_out(v) if drop == "robust outliers" else sets[drop]
    vv = {m: x for m, x in v.items() if m not in dset and np.isfinite(x)}
    if mid == CRIT and con in ("Het_vs_WT", "Hom_vs_WT"):
        return crit_p(vv, con, raw)
    if con in ("Het_vs_WT", "Hom_vs_WT"):
        g = con.split("_")[0]
        return S.two([x for m, x in vv.items() if F.geno(m) == "WT"], [x for m, x in vv.items() if F.geno(m) == g])["p"]
    if con == "young_vs_old_Hom":
        return S.two([x for m, x in vv.items() if F.geno(m) == "Hom" and not F.young(m)],
                     [x for m, x in vv.items() if F.geno(m) == "Hom" and F.young(m)])["p"]
    if con == "int_age_group_Hom":
        df = pd.DataFrame({"v": list(vv.values()), "yh": [F.geno(m) for m in vv], "ag": [F.MICE[m]["age_group"] for m in vv]})
        if df.ag.nunique() < 2 or (df[df.yh == "Hom"].ag.nunique() < 2):
            return np.nan
        fit = smf.ols("v ~ C(yh, Treatment('WT')) * C(ag, Treatment('old'))", df).fit()
        return float(fit.pvalues.get("C(yh, Treatment('WT'))[T.Hom]:C(ag, Treatment('old'))[T.young]", np.nan))
    return np.nan


def progression(fig, x0, y0, sessions, size=0.58, gapx=0.1, gapy=0.06):
    """Story-4a style lobes across training: mean share of time per 10 deg around the arena (room frame), one row per
    genotype, one column per session, all on one radial scale."""
    th = np.radians(np.arange(-175, 180, 10) + F.SECTOR[0])
    occs = {(g, s): np.mean([D.occ(m, [s]) for m in D.by(g=g)], axis=0) for g in G3 for s in sessions}
    vmax = max(float(o.max()) for o in occs.values()) * 1.04
    W, H = fig.get_size_inches()
    xs = []
    for j, s in enumerate(sessions):
        xs.append(x0 + j * (size + gapx) + (0.14 if j > 0 and sessions[0] == 0 else 0))
    for i, g in enumerate(G3):
        yy = y0 + i * (size + gapy)
        fig.text((x0 - 0.12) / W, 1 - (yy + size / 2) / H, g, fontsize=7, weight="bold", color=F.GCOL[g], ha="right", va="center")
        for j, s in enumerate(sessions):
            ax = F.axes_in(fig, xs[j], yy, size, size, projection="polar")
            occ = occs[(g, s)]
            col = F.GCOL[g]
            ax.bar(np.radians(F.SECTOR[0]), vmax, width=np.radians(60), color=F.ZONE, alpha=0.13, lw=0)
            ax.plot(np.linspace(0, 2 * np.pi, 100), np.full(100, 1 / 36), color=F.FAINT, lw=0.5, ls=":")
            ax.fill(np.r_[th, th[0]], np.r_[occ, occ[0]], color=col, alpha=0.22 if s else 0.12, lw=0)
            ax.plot(np.r_[th, th[0]], np.r_[occ, occ[0]], color=col, lw=1.0 if s else 0.8, alpha=1 if s else 0.7)
            ax.set_ylim(0, vmax)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.spines["polar"].set_color("#c9ccd3")
            ax.spines["polar"].set_linewidth(0.6)
            if i == 0:
                ax.set_title("habituation" if s == 0 else "s%d" % s, fontsize=6, pad=2, color=F.SOFT if s == 0 else F.INK)
    top = y0 - 0.33
    d1 = [x for x, s in zip(xs, sessions) if 1 <= s <= 8]
    d2 = [x for x, s in zip(xs, sessions) if s >= 9]
    for xx, lab in ((d1, "day 1"), (d2, "day 2")):
        if xx:
            ax = F.axes_in(fig, xx[0], top, xx[-1] + size - xx[0], 0.1)
            ax.axis("off")
            ax.plot([0, 1], [0.2, 0.2], color=F.FAINT, lw=0.6, transform=ax.transAxes)
            ax.text(0.5, 0.45, lab, ha="center", va="bottom", fontsize=5.8, color=F.SOFT, transform=ax.transAxes)
    return y0 + 3 * size + 2 * gapy


# ============================================================================ story 6: H3 numbers
def story6():
    st_ = F.res("strategy_score|d2", "Het_vs_WT")
    br = F.res("brake_share|d2", "Het_vs_WT")
    fig, y = F.page("Hypothesis 3: Het are not more scattered. They wait farther from the zone than WT, turn back less "
                    "at its edge, and move their safe spot more on day 1",
                    "STORY 6 · HYPOTHESIS 3 · WHERE THEY WAIT", number=9)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "Every genotype learns to wait across from the zone; by day 2 Het sit farthest from it")
    yend = progression(fig, 0.95, y + 0.55, [0, 1, 4, 8, 9, 12, 16])
    F.put(fig, 0.75, yend + 0.08, "Mean share of time per 10° around the arena (room frame), all panels on one scale; red = the "
                                  "shock zone; dotted circle = an even spread. Habituation (shock off) is drawn faint, for the "
                                  "shape before training.", 4.9, size=5.8, color=F.SOFT)
    yb = yend + 0.62
    F.letter(fig, 0.4, yb, "b", "From the end of day 1, Het left the pre-shock quadrant and waited farther from the zone than WT")
    for j, (meas, lab) in enumerate((("strategy_score", "Strategy score\n(1 = waits opposite)"), ("zone_CW", "Share of time in the\npre-shock quadrant"),
                                     ("brake_share", "Close approaches\nthat turned back"))):
        ax = F.axes_in(fig, 0.75 + j * 1.68, yb + 0.42, 1.25, 1.1)
        curves(ax, meas, lab, legend=False)
    yc = yb + 2.05
    F.letter(fig, 0.4, yc, "c", "Het waited farther from the zone and turned back less at its edge, but were not more scattered")
    specs = [("strategy_score|d2", "Strategy score", "Day 2: waiting opposite"),
             ("zone_CW|d2", "Share of quadrant time", "Day 2: pre-shock quadrant"),
             ("brake_share|d2", "Share of close approaches", "Day 2: turned back at the edge"),
             ("consistency|pref_sd_d1", "Wander between sessions (deg)", "Day 1: safe spot moves"),
             ("R|d2", "Concentration (0-1)", "Day 2: scatter (concentration)"),
             ("entropy|d2", "Entropy (0-1)", "Day 2: scatter (entropy)")]
    axs = F.grid(fig, 0.75, yc + 0.62, 3, 2, 1.25, 1.0, gx=0.43, gy=0.95)
    for ax, (mid, ylab, t) in zip(axs, specs):
        F.geno_dots(ax, mid, ylab, title=t, names=None,
                    contrasts=(("Het_vs_WT", "Het vs WT"), ("Het_vs_WT_adj_age", "+ age")))
    pdir = F.A["CIRC"]
    pdir = pdir[pdir.group == "Het_vs_WT"].iloc[0]
    cw = F.res("zone_CW|d2", "Het_vs_WT")
    wd = F.res("consistency|pref_sd_d1", "Het_vs_WT")
    w2 = F.res("consistency|pref_sd_d2", "Het_vs_WT")
    rr = F.res("R|d2", "Het_vs_WT")
    F.textcol(fig, 1.6, [
        ("The claim", "Hypothesis 3 pictured WT keeping steadily away from the zone and Het scattered. Het are not more "
                      "scattered, by any of four measures. The genotypes differ in where they wait: WT sit closer to the "
                      "zone's upstream edge and step away when the floor brings them close; Het park farther round, near "
                      "the opposite quadrant, and when they do come close they turn back less often. On day 1 the Het "
                      "safe spot also moves more from session to session."),
        ("How to read it", "a: the average mouse of each genotype, session by session, drawn as in story 4: a round shape "
                           "= time spread evenly; a lobe = time spent on one side. b: how the strategy score, the pre-shock "
                           "share and the share of close approaches that turned back develop (mean ± s.e.m.; stars over a "
                           "session: Het, orange, or Hom, purple, differ from WT there). c: one dot per mouse; brackets mark "
                           "pairs that differ; '+ age' = Het vs WT with age in the model too. b and c at one floor speed. Each mouse's "
                           "preferred direction is drawn on page 8."),
        ("What it shows", "At one floor speed. Strategy score: Het %.2f vs WT %.2f (%s; + age %s); it grows faster over training in Het (mixed "
                          "model %s). Pre-shock quadrant: %.2f vs %.2f (%s). Turned back at the edge: %.2f vs %.2f (%s). Day-1 "
                          "wander of the safe spot: %.0f vs %.0f deg (%s; day 2 %s). Mean direction differs by %.0f deg "
                          "(permutation inside speed bands %s). Scatter: concentration %.2f vs %.2f (%s)." % (
                              st_["mean_b"], st_["mean_a"], F.pstr(st_["p"]), adj("strategy_score|d2"),
                              F.pstr(F.mm("strategy_score", "geno_x_session", "[T.Het]:sc")[0]),
                              cw["mean_b"], cw["mean_a"], F.pstr(cw["p"]), br["mean_b"], br["mean_a"], F.pstr(br["p"]),
                              wd["mean_b"], wd["mean_a"], F.pstr(wd["p"]), F.pstr(w2["p"]), pdir.diff_deg, F.pstr(F.circ_p("Het_vs_WT")),
                              rr["mean_b"], rr["mean_a"], F.pstr(rr["p"]))),
        ("Caveats", "All three Het results are carried by the 2026 mice (2026 alone: %s, %s, %s; 2024 alone: %s, %s, %s; "
                    "page 11). Het and WT ran on the same mix of floor speeds, so it is not the floor."
                    % tuple(F.pstr(sens_p(mid, "Het_vs_WT", d)) for d in ("2026 mice only", "2024 mice only")
                            for mid in ("strategy_score|d2", "brake_share|d2", "consistency|pref_sd_d1"))),
        ("Verdict", "Partly backed up, and turned around: Het paths are not scattered, and Het do not stay away less; "
                    "they stay away from farther off, with less fine control at the edge and a less settled spot on day 1."),
        ("To replicate", "The same measures from the arena-frame track, which shows the walking itself; and a probe "
                         "session with the shock off after day 2 to see where each mouse goes by memory."),
    ])
    F.save(fig, OUT, "09_story6_where_they_wait")


# ============================================================================ story 7: path shape
def story7():
    fig, y = F.page("How they move: Hom stay off the rim and walk less straight; Het move like WT", "STORY 7 · PATH SHAPE",
                    number=10)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.3
    three = (("Hom_vs_WT", "Hom vs WT"), ("Het_vs_WT", "Het vs WT"), ("Hom_vs_WT_adj_age", "Hom + age"))
    F.letter(fig, 0.4, y + 0.08, "a", "On day 2 Hom spent less time at the rim and walked a little less straight; Het moved like WT")
    specs = [("rim_pct|d2", "% of time", "At the rim (outer ring)"),
             ("straightness|d2", "Net / path over 5 s", "Straightness of walking"),
             ("walk_speed_cm_s|d2", "cm per s", "Walking speed on the floor"),
             ("immobile_pct|d2", "% of seconds", "Still on the floor (< 2 cm/s)"),
             ("walk_m|d2", "m per session", "Distance walked on the floor"),
             ("mean_r_cm|d2", "cm", "Mean distance from the center")]
    axs = F.grid(fig, 0.75, y + 0.7, 3, 2, 1.25, 1.05, gx=0.43, gy=1.0)
    for ax, (mid, ylab, t) in zip(axs, specs):
        F.geno_dots(ax, mid, ylab, title=t, names=None, contrasts=three)
    F.put(fig, 0.75, y + 3.98, "Walking is measured on the floor itself, with the floor's rotation taken out of the track.",
          4.9, size=5.8, color=F.SOFT)
    yb = y + 4.45
    ws1 = F.res("walk_speed_cm_s|d1", "Het_vs_WT")
    wh1 = F.res("walk_speed_cm_s|d1", "Hom_vs_WT")
    im1 = F.res("immobile_pct|d1", "Hom_vs_WT")
    F.letter(fig, 0.4, yb, "b", "On day 1, at one floor speed, Hom walked faster and sat still less than WT; Het walked more slowly")
    specs = [("rim_pct|d1", "% of time", "Day 1: at the rim"), ("walk_speed_cm_s|d1", "cm per s", "Day 1: walking speed"),
             ("immobile_pct|d1", "% of seconds", "Day 1: still on the floor")]
    for j, (mid, ylab, t) in enumerate(specs):
        ax = F.axes_in(fig, 0.75 + j * 1.68, yb + 0.72, 1.25, 1.05)
        F.geno_dots(ax, mid, ylab, title=t, names=None, contrasts=three)
    yc = yb + 2.3
    rp = F.res("path_m|d2", "rot_corr_all")
    rw = F.res("walk_m|d2", "rot_corr_all")
    F.letter(fig, 0.4, yc, "c", "Path in the room and walking on the floor both rise with floor speed (ρ %+.2f, %+.2f)"
             % (rp["effect"], rw["effect"]))
    ax = F.axes_in(fig, 0.75, yc + 0.42, 2.1, 1.25)
    v = F.VALS_RAW["path_m|d2"]
    for m in D.MLIST:
        F.scatter_mouse(ax, F.MICE[m]["omega"], v[m], m)
    ax.set_title("Day-2 path in the room against floor speed\nρ %+.2f, %s" % (rp["effect"], F.pstars(rp["p"])), fontsize=6, loc="left")
    ax.set_xlabel("Floor speed (deg/s)")
    ax.set_ylabel("Path in the room (m per session)")
    ax2 = F.axes_in(fig, 3.35, yc + 0.42, 2.1, 1.25)
    v = F.VALS_RAW["walk_m|d2"]
    for m in D.MLIST:
        F.scatter_mouse(ax2, F.MICE[m]["omega"], v[m], m)
    ax2.set_title("Distance walked on the floor against speed\nρ %+.2f, %s" % (rw["effect"], F.pstars(rw["p"])), fontsize=6, loc="left")
    ax2.set_xlabel("Floor speed (deg/s)")
    ax2.set_ylabel("Walked on the floor (m per session)")
    rim = F.res("rim_pct|d2", "Hom_vs_WT")
    stt = F.res("straightness|d2", "Hom_vs_WT")
    F.textcol(fig, 1.35, [
        ("The claim", "Hom spend less of day 2 at the rim and their walking bouts are a little less straight than WT's. "
                      "On day 1, at one floor speed, Hom walk faster and sit still less than WT, while Het walk more "
                      "slowly. Het move like WT on day 2."),
        ("How to read it", "Walking is measured on the floor itself: the floor's rotation is taken out of the track, so a "
                           "mouse riding still counts as still. Straightness: straight-line distance over path length in "
                           "5-s windows with at least 5 cm walked (1 = a straight line). Brackets mark pairs that differ. "
                           "a, b at one floor speed; c raw, to show the speed. 'Hom + age' = Hom vs WT with age in the "
                           "model too."),
        ("What it shows", "At one floor speed. Rim: Hom %.0f%% vs WT %.0f%% of day 2 (%s; + age %s). Straightness: %.3f vs "
                          "%.3f (%s; + age %s). "
                          "Walking speed on day 1: Het %.2f vs WT %.2f cm/s (%s). Path in the room tracks the floor speed "
                          "closely (c), so room path and room speed say more about the floor than the mouse; walking on "
                          "the floor rises with speed too, because a faster floor makes them walk more to hold their place."
                          % (rim["mean_b"], rim["mean_a"], F.pstr(rim["p"]), adj("rim_pct|d2", "Hom"), stt["mean_b"], stt["mean_a"],
                             F.pstr(stt["p"]), adj("straightness|d2", "Hom"), ws1["mean_b"], ws1["mean_a"], F.pstr(ws1["p"]))),
        ("Caveats", "The day-1 Hom walking differences appear only at one floor speed (raw P %s and %s; at one speed %s "
                    "and %s): most Hom ran on the slow floor, so their values are carried up the speed slope measured "
                    "in all mice. On day 2 mice of every age and genotype are still in about 70%% of the one-second "
                    "steps: they ride the floor and walk back in bursts. The floor-frame numbers depend on each "
                    "day's floor-speed estimate (page 3)." % (F.pstr(F.P("walk_speed_cm_s|d1", "Hom_vs_WT", raw=True)),
                                                            F.pstr(F.P("immobile_pct|d1", "Hom_vs_WT", raw=True)),
                                                            F.pstr(wh1["p"]), F.pstr(im1["p"]))),
        ("Verdict", "A side story: Hom keep in from the wall. Worth one look in an open field."),
    ])
    F.save(fig, OUT, "10_story7_path_shape")


# ============================================================================ validation and checks
def validation():
    fig, y = F.page("Read straight from the tracker files: how our numbers compare with TrackAnalysis, and how the "
                    "headlines move with floor speed and without the flagged mice", "CHECKS · DATA AND ROBUSTNESS", number=11)
    y += 0.1
    F.letter(fig, 0.4, y + 0.08, "a", "Path and zone shares match TrackAnalysis almost exactly; TrackAnalysis counts about a "
                                      "fifth fewer shocks", width=7.6)
    P = D.PAIRS
    pairs = [("ta_shocks", "shocks", "Shocks"), ("ta_entr", "entrances", "Entrances"), ("ta_path", "path_m", "Path (m)"),
             ("ta_pT", "zone_T", "Share of quadrant time\nin the zone")]
    for j, (a, b, lab) in enumerate(pairs):
        ax = F.axes_in(fig, 0.75 + j * 1.27, y + 0.45, 0.95, 0.95)
        for src, col in (("v2 TBL (2026)", F.KICK), ("Eli workbook (2024 + early 2026)", "#b07d2b")):
            g = P[P.src == src]
            ax.scatter(g[a], g[b], s=3, color=col, alpha=0.45, lw=0, rasterized=True)
        lim = [0, max(P[a].max(), P[b].max()) * 1.05]
        ax.plot(lim, lim, color=F.INK, lw=0.6, ls="--")
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel("TrackAnalysis")
        if j == 0:
            ax.set_ylabel("Ours (.dat)")
        ax.set_title(lab, fontsize=6, loc="left")
    F.put(fig, 0.75, y + 1.8, "Blue: Angelina's v2 run (2026 files, 498 sessions). Brown: Eli's workbook (2024 and early 2026, 527 "
                              "sessions). Dashed: equal.", 4.8, size=5.8, color=F.SOFT)
    V = D.VALID
    ax = F.axes_in(fig, 0.75, y + 2.1, 4.8, 1.3)
    ax.axis("off")
    hdr = ["Measure", "Source", "n", "ρ", "median ours - TA", "same value"]
    xs = [0, 0.34, 0.6, 0.67, 0.75, 0.9]
    for j, h in enumerate(hdr):
        ax.text(xs[j], 1, h, fontsize=5.5, weight="bold", va="top", transform=ax.transAxes)
    keep = ["Shocks", "Entrances", "Time to first entrance (s)", "Path (m)", "Share of quadrant time in the zone", "Rayleigh length / R"]
    i = 0
    for meas in keep:
        for src in ("v2 TBL (2026)", "Eli workbook (2024 + early 2026)"):
            r = V[(V.measure == meas) & (V.source == src)]
            if r.empty:
                continue
            r = r.iloc[0]
            i += 1
            vals = [meas if src.startswith("v2") else "", "v2 run" if src.startswith("v2") else "Eli workbook", "%d" % r.n,
                    "%.3f" % r.spearman, "%+.2f" % r.median_ours_minus_TA, "%.0f%%" % (100 * r.exact_share)]
            for j, c in enumerate(vals):
                ax.text(xs[j], 1 - i * 0.075, c, fontsize=5.3, va="top", transform=ax.transAxes)
    yb = y + 3.7
    F.letter(fig, 0.4, yb, "b", "At one floor speed most headlines hold without outliers or flagged mice; the Hom age effect "
                                "and Hom's raw day-1 shock gap do not", width=7.6)
    heads = [("shocks|d1", "Hom_vs_WT", "Hom fewer day-1 shocks than WT (story 1)"),
             ("entrances|d2_minus_d1", "Het_vs_WT", "Het improve less (story 2)"),
             ("entrances|d2_minus_d1", "Hom_vs_WT", "Hom improve less (story 2)"),
             ("shocks|d2", "young_vs_old_Hom", "Old vs young Hom, day-2 shocks (story 3)"),
             ("shocks|d2", "int_age_group_Hom", "Hom x age, day-2 shocks (story 3)"),
             ("strategy_score|d2", "Het_vs_WT", "Het wait opposite (story 6)"),
             ("brake_share|d2", "Het_vs_WT", "Het turn back less (story 6)"),
             ("consistency|pref_sd_d1", "Het_vs_WT", "Het spot wanders, day 1 (story 6)"),
             (CRIT, "Hom_vs_WT", "Hom reach criterion sooner (story 1)")]
    drops = [("raw", "raw, all mice"), ("none", "all mice"), ("robust outliers", "no outliers*"), ("461, 462, 457", "no 461/462/457"),
             ("injected within 7 days", "no injected\n≤ 7 d"), ("all injected before AA", "no injected"),
             ("2024 mice only", "2024 only"), ("2026 mice only", "2026 only")]
    ax = F.axes_in(fig, 0.75, yb + 0.42, 7.0, 2.2)
    ax.axis("off")
    cx = [0, 0.31] + [0.31 + 0.086 * k for k in range(1, 8)]
    ax.plot([cx[2], 0.995], [1.055, 1.055], color=F.KICK, lw=0.6, transform=ax.transAxes, clip_on=False)
    ax.text(cx[2], 1.065, "at one floor speed", fontsize=5.6, color=F.KICK, va="bottom", transform=ax.transAxes, style="italic")
    ax.text(0, 1, "Headline", fontsize=5.6, weight="bold", va="top", transform=ax.transAxes)
    for k, (dk, lab) in enumerate(drops):
        ax.text(cx[k + 1], 1, lab, fontsize=5.4, weight="bold", va="top", transform=ax.transAxes)
    for i, (mid, con, lab) in enumerate(heads, 1):
        ax.text(0, 1 - i * 0.095, lab, fontsize=5.4, va="top", transform=ax.transAxes)
        for k, (dk, _l) in enumerate(drops):
            p = sens_p(mid, con, "none", raw=True) if dk == "raw" else sens_p(mid, con, dk)
            txt = ("%s %s" % (F.pstr(p).replace("P ", ""), F.stars(p))).strip() if np.isfinite(p) else "n/a"
            ax.text(cx[k + 1], 1 - i * 0.095, txt, fontsize=5.4, va="top",
                    transform=ax.transAxes, color=F.INK if (np.isfinite(p) and p < 0.05) else F.FAINT)
    F.put(fig, 0.75, yb + 2.65, "Every column but the first is at one floor speed (%.1f deg/s). * Outliers: mice more than 3.5 "
                               "robust s.d. (1.4826 x MAD) from their genotype's median on that "
                               "measure, dropped for that row only (not used for the criterion, a time-to-event measure). "
                               "Gray = P ≥ 0.05. '2024 only' / '2026 only' halve the mice, and 2024 has no young mice, so age "
                               "contrasts go n/a there. The criterion row uses the time-to-criterion tests of page 4." % F.REF,
          7.0, size=5.8, color=F.SOFT)
    yc = yb + 3.35
    F.letter(fig, 0.4, yc, "c", "TrackAnalysis rebuilds entrances from one position a second and stopped reading at file 507; "
                                "our counts are the shocks the tracker delivered", width=7.6)
    F.put(fig, 0.75, yc + 0.18,
          "Path, zone shares and Rayleigh length match TrackAnalysis closely (ρ 0.98-1.00; TrackAnalysis measures path "
          "on one position per second, and so do we). Shocks and entrances do not: TrackAnalysis counts fewer (about 20% "
          "fewer shocks in the v2 run), and so finds a later first entrance and longer avoidance. It rebuilds entrances from "
          "positions, while we count the tracker's own record of every shock it delivered (the state column), which "
          "includes brief entries a one-per-second check can miss. Our counts are the shocks the mouse received. The .dat "
          "route also brings in what TrackAnalysis never reached: all of the Sep 2024 folder (448, 461, 462, 476-482), "
          "894, and 1667 s5-s16 (the v2 run stopped reading at file 507).", 7.0, size=6.3)
    F.save(fig, OUT, "11_checks")


# ============================================================================ what next
def what_next():
    fig, y = F.page("What each story needs from the next round", "WHAT NEXT", number=12)
    pw = TTestIndPower()

    def n_for(mid, con):
        g = F.res(mid, con).get("hedges_g", np.nan)
        if not np.isfinite(g) or abs(g) < 0.05:
            return "n/a"
        return "%d per group (g %.2f)" % (int(np.ceil(pw.solve_power(effect_size=abs(g), alpha=0.05, power=0.8))), abs(g))
    rows = [
        ("0", "The floor's speed", "Measure and log the rotation before every run; calibrate the motor so every cohort runs at one speed "
                                   "(1 turn per minute = 6 deg/s). Until then, report entrances per turn next to raw counts.", "-"),
        ("1-2", "Hom and Het improve less", "WT, Het and Hom littermates run side by side on the same days and floor speed; add a third "
                                            "day or a one-week retention session.", n_for("entrances|d2_minus_d1", "Het_vs_WT")),
        ("3", "Age hurts Hom", "Old (> 25 wk) and young (< 12 wk) Hom and WT in the same weeks, none injected within two weeks "
                               "of AA.", n_for("entrances_per_rev|d2", "young_vs_old_Hom")),
        ("4", "Hom explore less in habituation", "An open field or a habituation-only session (shock off) in young and old Hom and "
                                                 "WT; write on the run sheet that the voltage was off.",
         n_for("cells_visited|s0", "Hom_vs_WT")),
        ("6", "Het wait farther, brake less", "Keep the arena-frame file for every session; add a shock-off probe after day 2.",
         n_for("strategy_score|d2", "Het_vs_WT")),
        ("6", "Het safe spot wanders on day 1", "Same mice; this one needs no new measure.", n_for("consistency|pref_sd_d1", "Het_vs_WT")),
        ("7", "Hom stay off the rim", "One open-field session would say whether this is AA-specific.", n_for("rim_pct|d2", "Hom_vs_WT")),
    ]
    ax = F.axes_in(fig, 0.5, y + 0.2, 7.5, 3.6)
    ax.axis("off")
    hx = [0, 0.06, 0.27, 0.8]
    for j, h in enumerate(["Story", "Claim", "What to run", "Mice for 80% power at P < 0.05"]):
        ax.text(hx[j], 1, h, fontsize=6.4, weight="bold", va="top", color=F.SOFT, transform=ax.transAxes)
    yy = 0.93
    for r in rows:
        txt = F.wrap(r[2], 3.8, 6.4)
        nl = txt.count("\n") + 1
        ax.text(hx[0], yy, r[0], fontsize=6.4, va="top", transform=ax.transAxes)
        ax.text(hx[1], yy, F.wrap(r[1], 1.45, 6.4), fontsize=6.4, va="top", weight="bold", transform=ax.transAxes)
        ax.text(hx[2], yy, txt, fontsize=6.4, va="top", transform=ax.transAxes)
        ax.text(hx[3], yy, F.wrap(r[3], 1.4, 6.4), fontsize=6.4, va="top", transform=ax.transAxes)
        yy -= 0.045 * max(nl, 2) + 0.03
        ax.plot([0, 1], [yy + 0.015, yy + 0.015], color=F.GRID, lw=0.6, transform=ax.transAxes)
    y2 = y + 4.1
    F.put(fig, 0.5, y2, "For the lab, beyond the stories", 7.5, size=7.5, weight="bold")
    F.put(fig, 0.5, y2 + 0.25,
          "1. Floor speed. The arena turned at 2.2-5.8 deg/s across these runs although the motor setting never changed; "
          "it was slowest from March to September 2026 and jumped after the 10/21/2026 repair. This alone can make a "
          "cohort look better or worse. A once-a-day check takes a minute.\n"
          "2. Mixing designs. All young Hom came from the slow-floor, injected 2026 summer cohorts; all old Hom from 2024. "
          "Every planned comparison should have both of its groups in the same weeks.\n"
          "3. TrackAnalysis batches stop at 506 files ('GetTrackSize returned 0 files' after that); split the 2026 folder "
          "into two batches, or use the .dat numbers here, which need no batching.\n"
          "4. TrackAnalysis counts about a fifth fewer shocks than the tracker delivered; if TrackAnalysis stays the lab's "
          "tool, say so in methods, or switch the shock and entrance counts to the state column.\n"
          "5. Habituation. The tracker logs 'shocks' in s0 even though the voltage is off; leave s0 out of every shock, "
          "entrance and time-in-zone number (this menu does).\n"
          "6. Sex. Lab Ops 2.0 has the wrong sex for 42 mice (v3 map); Eli's workbook inherited five of them for AA mice "
          "(414, 416, 526, 527, 814). This menu uses the cage-card sexes. No headline measure differs by sex at P < 0.05 "
          "(P 0.06-0.91), but fix it before any by-sex plot.\n"
          "7. Injection. The 18 mice virus-injected before AA (some 2 days before) are all on the slow floor, so their "
          "effect cannot be separated from the floor's here. Keep injections at least two weeks before AA, or after it.\n"
          "8. File names. Two 2026 files still carry wrong names (M1564s7_091826 is 1645 s7; M1644s_102926 is 1644 s13); "
          "the 2024 'H1' files are 418's and 419's s0.", 7.4, size=6.5)
    F.save(fig, OUT, "12_what_next")


# ============================================================================ the menu
def menu():
    fig = __import__("matplotlib.pyplot", fromlist=["figure"]).figure(figsize=(8.5, 11))
    F.put(fig, 0.7, 0.8, "BARRY LAB · KCNT1 ACTIVE AVOIDANCE · FIRST ROUND, 2026-11-23", 7.2, size=7.2, color=F.KICK, weight="bold")
    F.put(fig, 0.7, 1.05, "KCNT1 active avoidance: a menu of stories the data support", 7.2, size=17, weight="bold")
    F.put(fig, 0.7, 1.6, "56 mice (21 WT, 20 Het, 15 Hom; 20 young, 36 old), 952 ten-minute sessions read straight from the "
                          "tracker files. Every comparison at one floor speed (%.1f deg/s). Exploratory: one number per "
                          "mouse, generous tests, no correction. Hypotheses 1-3 from the lab; the rest is what the data "
                          "offered." % F.REF, 7.2, size=8, color=F.SOFT)
    F.put(fig, 0.72, 2.55, "The framework the stories hang on: a run from habituation to the end of day 2", 7.2, size=7.5, weight="bold")
    boxes = [("THE FLOOR", "speed sets the\nraw counts", "Story 0"), ("HABITUATION", "s0, shock off", "Story 4"),
             ("LEARNING", "day 1", "Stories 1, 3"), ("IMPROVING", "day 1 → day 2", "Story 2"),
             ("WHERE THEY WAIT", "paths, day 2", "Stories 5-7")]
    cols = ["#d9e7ee", "#e6eef2", "#d7e6ee", "#cfe0ea", "#e3e3ef"]
    ax = F.axes_in(fig, 0.7, 2.75, 7.2, 1.25)
    ax.set_xlim(0, 7.2)
    ax.set_ylim(0, 1.25)
    ax.axis("off")
    bw, gap = 1.25, 0.24
    for k, (t, s, ref) in enumerate(boxes):
        x0 = k * (bw + gap)
        ax.add_patch(FancyBboxPatch((x0, 0.35), bw, 0.75, boxstyle="round,pad=0.0,rounding_size=0.08", fc=cols[k], ec="none"))
        ax.text(x0 + bw / 2, 0.85, t, ha="center", va="center", fontsize=7.2, weight="bold", color=F.INK)
        ax.text(x0 + bw / 2, 0.57, s, ha="center", va="center", fontsize=6.2, color=F.INK)
        ax.text(x0 + bw / 2, 0.15, ref, ha="center", va="center", fontsize=6.4, color=F.KICK, weight="bold")
        if k < len(boxes) - 1:
            ax.annotate("", xy=(x0 + bw + gap - 0.03, 0.72), xytext=(x0 + bw + 0.03, 0.72),
                        arrowprops=dict(arrowstyle="-|>", color=F.SOFT, lw=1))
    F.put(fig, 0.72, 4.15, "The narrative in one paragraph", 7.2, size=7.5, weight="bold")
    hs2 = F.res("entrances|d2_minus_d1", "Het_vs_WT")
    F.put(fig, 0.72, 4.4,
          "None of the three hypotheses comes out as written, and each points somewhere more useful. Every comparison is "
          "made at one floor speed, because the arena turned at very different speeds across cohorts (story 0). At one speed "
          "Hom mice do not avoid worse: they take as many shocks as WT and reach criterion sooner, but they, and Het, improve "
          "less from day 1 to day 2 than WT do (hypothesis 1, refined). Raw, old Hom did worse than young Hom (hypothesis 2), "
          "but at one floor speed the gap is not significant: old and young Hom also ran on different floors, years and "
          "injection schedules. Het paths are not scattered (hypothesis 3): Het wait farther from the zone than WT, turn "
          "back less often at its edge, and move their safe spot more on day 1. In habituation Hom keep to one side and "
          "cover less of the floor.", 7.0, size=7.4)
    F.put(fig, 0.72, 5.75, "The menu", 7.2, size=7.5, weight="bold")
    p = F.P
    pr = (lambda mid, c: F.P(mid, c, raw=True))
    rows = [
        ("0", "Apparatus", "The floor's speed", "Floor speed ranged 2.2-5.8 deg/s; raw shocks and path follow it; young Hom all on the slow floor.",
         "total shocks vs speed ρ +0.32, %s" % F.pstars(p("shocks|total", "rot_corr_all")), "-", "3"),
        ("1", "Hypothesis 1", "Hom learn worse? No", "At one floor speed Hom take as many shocks as WT on both days and reach criterion sooner.",
         "criterion %s; day-1 shocks %s; day 2 %s" % (F.pstars(p(CRIT, "Hom_vs_WT")), F.pstr(p("shocks|d1", "Hom_vs_WT")),
                                                    F.pstr(p("shocks|d2", "Hom_vs_WT"))),
         "day 1 %s" % F.pstr(pr("shocks|d1", "Hom_vs_WT")), "4"),
        ("2", "Hypothesis 1, refined", "Mutants improve less", "Day 1 to day 2, WT improve most; Het and Hom curves are flatter.",
         "Het %s, Hom %s; mixed model %s / %s" % (F.pstars(hs2["p"]), F.pstars(p("entrances|d2_minus_d1", "Hom_vs_WT")),
                                                  F.pstars(F.mm("entrances_per_rev", "geno_x_session", "[T.Het]:sc")[0]),
                                                  F.pstars(F.mm("entrances_per_rev", "geno_x_session", "[T.Hom]:sc")[0])),
         "Het %s, Hom %s" % (F.pstr(pr("entrances|d2_minus_d1", "Het_vs_WT")), F.pstr(pr("entrances|d2_minus_d1", "Hom_vs_WT"))), "5"),
        ("3", "Hypothesis 2", "Age hurts Hom? Not at one speed", "Raw, old Hom took more day-2 shocks than young Hom; at one floor speed the gap is not significant.",
         "old vs young Hom %s; x age %s" % (F.pstr(p("shocks|d2", "young_vs_old_Hom")), F.pstr(p("shocks|d2", "int_age_group_Hom"))),
         "%s; x age %s" % (F.pstr(pr("shocks|d2", "young_vs_old_Hom")), F.pstr(pr("shocks|d2", "int_age_group_Hom"))), "6"),
        ("4", "Habituation", "Hom explore less", "With the shock off (s0), Hom keep to one side and cover less of the floor; old Hom most.",
         "floor covered %s; one side %s" % (F.pstars(p("cells_visited|s0", "Hom_vs_WT")), F.pstars(p("R|s0", "Hom_vs_WT"))),
         "%s; %s" % (F.pstr(pr("cells_visited|s0", "Hom_vs_WT")), F.pstr(pr("R|s0", "Hom_vs_WT"))), "7"),
        ("5", "Hypothesis 3", "The circle diagrams", "Every mouse's day-2 waiting place and last session, sorted by how well it avoided.",
         "direction Het vs WT %s" % F.pstars(F.circ_p("Het_vs_WT")), "-", "8"),
        ("6", "Hypothesis 3", "Het wait farther, brake less", "Not scattered; Het park opposite, turn back less at the edge, wander on day 1.",
         "strategy %s; brake %s; wander %s" % (F.pstars(p("strategy_score|d2", "Het_vs_WT")), F.pstars(p("brake_share|d2", "Het_vs_WT")),
                                             F.pstars(p("consistency|pref_sd_d1", "Het_vs_WT"))),
         "%s; %s; %s" % (F.pstr(pr("strategy_score|d2", "Het_vs_WT")), F.pstr(pr("brake_share|d2", "Het_vs_WT")),
                         F.pstr(pr("consistency|pref_sd_d1", "Het_vs_WT"))), "9"),
        ("7", "Path shape", "Hom stay off the rim", "Hom spend less time at the wall and walk a little less straight; Het like WT.",
         "rim %s; straightness %s" % (F.pstars(p("rim_pct|d2", "Hom_vs_WT")), F.pstars(p("straightness|d2", "Hom_vs_WT"))),
         "%s; %s" % (F.pstr(pr("rim_pct|d2", "Hom_vs_WT")), F.pstr(pr("straightness|d2", "Hom_vs_WT"))), "10"),
    ]
    ax = F.axes_in(fig, 0.7, 6.0, 7.3, 4.2)
    ax.axis("off")
    hx = [0, 0.04, 0.165, 0.35, 0.62, 0.86, 0.975]
    for j, h in enumerate(["#", "Step", "Story", "What we could claim", "Best number, at one floor speed", "Raw, before\nthe speed fix", "Page"]):
        ax.text(hx[j], 1, h, fontsize=6.4, weight="bold", va="top", color=F.SOFT, transform=ax.transAxes)
    yy = 0.92
    for r in rows:
        cells = [r[0], F.wrap(r[1], 0.85, 6.6), F.wrap(r[2], 1.3, 6.6), F.wrap(r[3], 1.95, 6.6), F.wrap(r[4], 1.75, 6.6),
                 F.wrap(r[5], 0.85, 6.0), r[6]]
        nl = max(c.count("\n") + 1 for c in cells)
        for j, c in enumerate(cells):
            ax.text(hx[j], yy, c, fontsize=6.0 if j == 5 else 6.6, va="top", weight="bold" if j == 2 else "normal",
                    transform=ax.transAxes, color=F.SOFT if j == 5 else F.INK)
        yy -= 0.034 * nl + 0.035
        ax.plot([0, 1], [yy + 0.017, yy + 0.017], color=F.GRID, lw=0.6, transform=ax.transAxes)
    F.put(fig, 0.72, 10.35, "Page 2: the task and the words. Page 11: our numbers against TrackAnalysis, and every headline without the "
                            "flagged mice. Page 12: what each story needs next. The speed supplement: every headline before and after the "
                            "speed adjustment. * P < 0.05, ** P < 0.01, *** P < 0.001.", 7.2, size=6.4, color=F.SOFT)
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, F.FOOT, fontsize=6.5, color=F.FAINT, ha="left", va="bottom")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "1", fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    F.save(fig, OUT, "01_menu")


if __name__ == "__main__":
    story6()
    story7()
    validation()
    what_next()
    menu()
