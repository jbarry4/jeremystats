"""Stories 3-5: H2 age, habituation (s0, shock off), the circle path diagrams. Round 2: brackets, habituation renamed and
stripped of its meaningless zone numbers, sharper paths, and headings that state the finding."""
import os

import matplotlib.patheffects as pe
import numpy as np
from scipy import stats as st

import figlib_aa as F
import menu_data as D
from pages_a import curves, G3

OUT = os.path.join(F.HERE, "out")
GA = ["WT young", "WT old", "Het young", "Het old", "Hom young", "Hom old"]
GAL = ["WT\nyoung", "WT\nold", "Het\nyoung", "Het\nold", "Hom\nyoung", "Hom\nold"]


def int_p(mid, drop=(), raw=False):
    """Hom x age-group interaction P (OLS, as in the analysis) after leaving out the given mice; at one floor speed unless raw."""
    import pandas as pd
    import statsmodels.formula.api as smf
    v = {m: x for m, x in (F.VALS_RAW if raw else F.VALS)[mid].items() if m not in drop and np.isfinite(x)}
    df = pd.DataFrame({"v": list(v.values()), "yh": [F.geno(m) for m in v], "ag": [F.MICE[m]["age_group"] for m in v]})
    f = "v ~ C(yh, Treatment('WT')) * C(ag, Treatment('old'))"
    fit = smf.ols(f, df).fit()
    return float(fit.pvalues["C(yh, Treatment('WT'))[T.Hom]:C(ag, Treatment('old'))[T.young]"])


def ga_dots(ax, mid, ylabel, title, marks="age", xlabels=GAL, compact=False):
    """Young and old inside each genotype. Brackets: young vs old inside a genotype; with marks='all' also genotype
    against genotype (both ages; the bar under each end spans the genotype's two columns)."""
    v = F.VALS[mid]
    grp = {m: "%s %s" % (F.geno(m), F.MICE[m]["age_group"]) for m in v}
    top = F.dots(ax, v, grp, GA, xlabels=["y", "o"] * 3 if compact else xlabels, ylabel=ylabel, names=None)
    for k in (1.5, 3.5):
        ax.axvline(k, color=F.GRID, lw=0.6)
    if compact:
        from matplotlib.transforms import blended_transform_factory
        tr = blended_transform_factory(ax.transData, ax.transAxes)
        for k, g in enumerate(G3):
            ax.text(2 * k + 0.5, -0.13, g, transform=tr, ha="center", va="top", fontsize=6.3, color=F.GCOL[g], weight="bold")
    ax.set_title(title, fontsize=5.7, loc="left", linespacing=1.15)
    items = [(2 * k, 2 * k + 1, F.P(mid, "young_vs_old_" + g)) for k, g in enumerate(G3)]
    if marks == "all":
        for c, a, b in F.GENO_PAIRS:
            items.append((2 * a + 0.5, 2 * b + 0.5, F.P(mid, c), ((2 * a - 0.15, 2 * a + 1.15), (2 * b - 0.15, 2 * b + 1.15))))
    F.brackets(ax, items, top, gap=0.05)


def age_scatter(ax, mid, ylabel):
    v = F.VALS[mid]
    for m in D.MLIST:
        F.scatter_mouse(ax, F.MICE[m]["age_wk"], v[m], m, size=16)
    for g in G3:
        ms = D.by(g=g)
        xx, yy, lo, hi = F.theil([F.MICE[m]["age_wk"] for m in ms], [v[m] for m in ms], n_boot=600)
        ax.plot(xx, yy, color=F.GCOL[g], lw=1.1)
        if g == "Hom":
            ax.fill_between(xx, lo, hi, color=F.GCOL[g], alpha=0.08, lw=0)
    for m in D.by(g="Hom"):
        if not F.young(m) or m == "1634":
            ax.text(F.MICE[m]["age_wk"] + 0.6, v[m], m, fontsize=4.6, color=F.GCOL["Hom"], va="center", zorder=8,
                    path_effects=[pe.withStroke(linewidth=1.6, foreground="white")])
    ax.axvline(18, color=F.FAINT, lw=0.6, ls=":")
    ax.set_xlabel("Age at session 1 (weeks)")
    ax.set_ylabel(ylabel)
    ax.set_title("against age: WT ρ %+.2f %s · Het ρ %+.2f %s\nHom ρ %+.2f %s · Hom slope vs WT slope %s" % (
        F.res(mid, "age_corr_WT")["effect"], F.pstars(F.P(mid, "age_corr_WT")), F.res(mid, "age_corr_Het")["effect"],
        F.pstars(F.P(mid, "age_corr_Het")), F.res(mid, "age_corr_Hom")["effect"], F.pstars(F.P(mid, "age_corr_Hom")),
        F.pstars(F.P(mid, "int_age_wk_Hom"))), fontsize=5.6, loc="left", color=F.SOFT, linespacing=1.15)


# ============================================================================ story 3: age
def story3():
    hs = F.res("shocks|d2", "young_vs_old_Hom")
    hsr = F.res("shocks|d2", "young_vs_old_Hom", raw=True)
    ca = F.res("shocks|d2", "age_corr_Hom")
    fig, y = F.page("Hypothesis 2, age hurts Hom: not at one floor speed. Raw, old Hom did worse than young Hom, but the "
                    "gap follows the floor",
                    "STORY 3 · HYPOTHESIS 2 · YOUNG AND OLD", number=6)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "At one floor speed day-2 shocks did not rise with age in any genotype (Hom ρ %+.2f, %s)"
             % (ca["effect"], F.pstr(ca["p"])))
    for j, (mid, lab) in enumerate((("shocks|d2", "Day-2 shocks per session"), ("entrances_per_rev|d2", "Day-2 entrances per turn"))):
        ax = F.axes_in(fig, 0.75 + j * 2.6, y + 0.55, 2.1, 1.45)
        age_scatter(ax, mid, lab)
    yb = y + 2.55
    F.letter(fig, 0.4, yb, "b", "At one floor speed old and young Hom took similar day-2 shocks (%s); so did WT and Het"
             % F.pstr(hs["p"]))
    for j, (mid, lab, t) in enumerate((("shocks|d2", "Shocks per session", "Day-2 shocks"),
                                       ("entrances_per_rev|d2", "Entrances per turn", "Day-2 entrances per turn (speed-free)"))):
        ax = F.axes_in(fig, 0.75 + j * 2.6, yb + 0.66, 2.1, 1.3)
        ga_dots(ax, mid, lab, "%s\nyoung vs old: WT %s · Het %s · Hom %s\ngenotype x age (Hom vs WT) %s" % (
            t, F.pstr(F.P(mid, "young_vs_old_WT")), F.pstr(F.P(mid, "young_vs_old_Het")), F.pstr(F.P(mid, "young_vs_old_Hom")),
            F.pstr(F.P(mid, "int_age_group_Hom"))))
    yc = yb + 2.5
    F.letter(fig, 0.4, yc, "c", "At one floor speed young and old Hom learned alike; old Hom entered a little more only in s11-s12")
    groups = {"Hom young": D.by(g="Hom", age="young"), "Hom old": D.by(g="Hom", age="old"),
              "WT young": D.by(g="WT", age="young"), "WT old": D.by(g="WT", age="old")}
    cols = {"Hom young": F.GCOL["Hom"], "Hom old": F.GCOL["Hom"], "WT young": "#b9b9b9", "WT old": "#b9b9b9"}
    marks = [("Hom old", "Hom young", F.GCOL["Hom"]), ("WT old", "WT young", "#9a9a9a")]
    for j, (meas, lab) in enumerate((("shocks", "Shocks per session"), ("entrances_per_rev", "Entrances per turn"),
                                     ("time_in_zone_pct", "Time in the zone (%)"))):
        ax = F.axes_in(fig, 0.75 + j * 1.68, yc + 0.4, 1.25, 1.15)
        curves(ax, meas, lab, groups=groups, colors=cols, legend=(j == 0), sem=False, marks=marks)
    F.put(fig, 0.75, yc + 1.95, "Solid = young, dashed = old. Stars over a session: young and old Hom (purple) or young and old "
                                "WT (gray) differ in that session (P < 0.05).", 4.9, size=5.8, color=F.SOFT)
    yd = yc + 2.35
    F.letter(fig, 0.4, yd, "d", "Raw, the Hom x age interaction had %s; at one floor speed it has %s"
             % (F.pstr(int_p("shocks|d2", raw=True)), F.pstr(int_p("shocks|d2"))))
    rows = [("", "Hom young (9)", "Hom old (6)")]
    yh = D.by(g="Hom", age="young")
    oh = D.by(g="Hom", age="old")
    rows.append(("Age (weeks)", "%.0f-%.0f" % (min(F.MICE[m]["age_wk"] for m in yh), max(F.MICE[m]["age_wk"] for m in yh)),
                 "%.0f-%.0f" % (min(F.MICE[m]["age_wk"] for m in oh), max(F.MICE[m]["age_wk"] for m in oh))))
    rows.append(("Run", "Jun-Sep 2026", "Mar-Oct 2024"))
    rows.append(("Floor speed (deg/s)", "%.1f (%.1f-%.1f)" % (np.median([F.MICE[m]["omega"] for m in yh]), min(F.MICE[m]["omega"] for m in yh),
                                                              max(F.MICE[m]["omega"] for m in yh)),
                 "%.1f (%.1f-%.1f)" % (np.median([F.MICE[m]["omega"] for m in oh]), min(F.MICE[m]["omega"] for m in oh), max(F.MICE[m]["omega"] for m in oh))))
    rows.append(("Virus injected before AA", "%d of 9 (7 within 7 d)" % sum(F.MICE[m]["injected_before"] for m in yh), "0 of 6"))
    ax = F.axes_in(fig, 0.75, yd + 0.2, 2.3, 1.0)
    ax.axis("off")
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            ax.text([0, 0.47, 0.79][j], 1 - i * 0.19, c, fontsize=5.5, weight="bold" if i == 0 else "normal", va="top",
                    ha="left", transform=ax.transAxes, color=F.INK)
    srow = [("Raw, before the speed adjustment", (), True), ("At one floor speed: all 56 mice", (), False),
            ("  without 417, 418, 827 (the three\n  highest old Hom)", ("417", "418", "827"), False),
            ("  without 461, 462, 457", ("461", "462", "457"), False),
            ("  without the 7 injected within 7 days", tuple(m for m in D.MLIST if F.MICE[m]["injected_7d"]), False)]
    ax = F.axes_in(fig, 3.25, yd + 0.2, 2.3, 1.2)
    ax.axis("off")
    ax.text(0, 1, "Hom: genotype x age group P", fontsize=5.6, weight="bold", va="top", transform=ax.transAxes)
    ax.text(0.7, 1, "day-2\nshocks", fontsize=5.4, weight="bold", va="top", transform=ax.transAxes)
    ax.text(0.87, 1, "time in\nzone", fontsize=5.4, weight="bold", va="top", transform=ax.transAxes)
    rows2 = [(lab, int_p("shocks|d2", dr, rw), int_p("time_in_zone_pct|d2", dr, rw)) for lab, dr, rw in srow]
    for i, (lab, p1, p2) in enumerate(rows2, 1):
        yy = 1 - i * 0.155 - 0.07
        ax.text(0, yy, lab, fontsize=5.3, va="top", transform=ax.transAxes, linespacing=1.05)
        for xx, p in ((0.7, p1), (0.87, p2)):
            ax.text(xx, yy, F.pstars(p).replace("P ", ""), fontsize=5.3, va="top", transform=ax.transAxes,
                    color=F.INK if p < 0.05 else F.FAINT)
    he = F.res("entrances_per_rev|d2", "young_vs_old_Hom")
    ws = F.res("shocks|d2", "young_vs_old_WT")
    hl = F.res("latency_first_entrance_s|d2", "young_vs_old_Hom")
    F.textcol(fig, 1.75, [
        ("The claim", "Hypothesis 2 said age would hurt Hom more than WT. Raw, the direction is there: old Hom took more "
                      "day-2 shocks than young Hom (%.1f vs %.1f, %s) while WT and Het show no age effect. But every old "
                      "Hom ran on a faster floor in 2024 and every young Hom on a slow one in 2026; at one floor speed "
                      "the gap shrinks to %.1f vs %.1f shocks (%s)." % (hsr["mean_a"], hsr["mean_b"], F.pstr(hsr["p"]),
                                                                     hs["mean_a"], hs["mean_b"], F.pstr(hs["p"]))),
        ("How to read it", "Every value at one floor speed except the first row of d. a: every mouse against its age; Hom "
                           "mice are labeled. b: the same split at 18 weeks; brackets "
                           "mark young-old pairs that differ; the genotype x age P asks whether the young-old gap in Hom "
                           "differs from WT's. c: learning curves of the four groups. d, left: what differs between young "
                           "and old Hom besides age; d, right: the age x genotype P under different checks (gray = P ≥ 0.05)."),
        ("What it shows", "At one floor speed, day-2 shocks: old Hom %.1f vs young Hom %.1f per session (%s); WT old %.1f "
                          "vs young %.1f (%s). Entrances per turn: old Hom %.2f vs young %.2f (%s). Old Hom still enter "
                          "sooner on day 2 (first entrance %.0f vs %.0f s, %s)." % (hs["mean_a"], hs["mean_b"], F.pstr(hs["p"]),
                                                                       ws["mean_a"], ws["mean_b"], F.pstr(ws["p"]), he["mean_a"],
                                                                       he["mean_b"], F.pstr(he["p"]), hl["mean_a"], hl["mean_b"],
                                                                       F.pstr(hl["p"]))),
        ("Why it is not settled", "Every old Hom ran on a faster floor in 2024 (4.3-5.5 deg/s); every young Hom ran on a "
                                  "slow floor in 2026 (2.8-3.5 deg/s), seven of them 2-7 days after a virus injection. Age, "
                                  "year, floor speed and injection travel together in these Hom, so even the adjusted "
                                  "numbers lean on the floor-speed slope measured across all mice."),
        ("Verdict", "Not backed up at one floor speed: the raw age gap in Hom shrinks and loses significance once floor "
                    "speed is matched; only the earlier first entrance on day 2 remains. It needs old and young Hom run "
                    "on the same days."),
        ("To replicate", "Old Hom and old WT (> 25 weeks) run on the same days as young ones, with the floor speed "
                         "measured; about 20 per group for the speed-free measure (page 12)."),
    ])
    F.save(fig, OUT, "06_story3_age")


# ============================================================================ story 4: habituation
def story4():
    fig, y = F.page("During habituation (shock off), Hom kept to one part of the arena, old Hom most of all; and the voltage "
                    "really was off", "STORY 4 · HABITUATION (s0, SHOCK OFF)", number=7)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "During habituation Hom, old Hom most, kept to one side of the arena; WT and Het spread out evenly")
    combos = [(g, a) for g in G3 for a in ("young", "old")]
    for j, (g, a) in enumerate(combos):
        ax = F.axes_in(fig, 0.6 + j * 0.82, y + 0.36, 0.76, 0.76, projection="polar")
        ms = D.by(g=g, age=a)
        occ = np.mean([D.occ(m, [0]) for m in ms], axis=0)
        th = np.radians(np.arange(-175, 180, 10) + F.SECTOR[0])
        ax.plot(np.r_[th, th[0]], np.r_[occ, occ[0]], color=F.GCOL[g], lw=1.2)
        ax.fill(np.r_[th, th[0]], np.r_[occ, occ[0]], color=F.GCOL[g], alpha=0.25, lw=0)
        ax.bar(np.radians(F.SECTOR[0]), 0.08, width=np.radians(60), color=F.ZONE, alpha=0.15, lw=0)
        ax.plot(np.linspace(0, 2 * np.pi, 100), np.full(100, 1 / 36), color=F.FAINT, lw=0.5, ls=":")
        ax.set_ylim(0, 0.08)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines["polar"].set_color("#c9ccd3")
        ax.set_title("%s %s (%d)" % (g, a, len(ms)), fontsize=5.6, color=F.GCOL[g], pad=2)
    F.put(fig, 0.6, y + 1.26, "Mean share of time per 10° around the arena in s0, in the room frame; red = where the shock zone "
                              "is during training. Dotted circle: an even spread. A mouse that wanders everywhere draws a "
                              "circle; one that keeps to one side draws a lobe.", 4.9, size=5.8, color=F.SOFT)
    rc = F.res("cells_visited|s0", "Hom_vs_WT")
    rw = F.res("walk_m|s0", "Hom_vs_WT")
    yb = y + 1.85
    F.letter(fig, 0.4, yb, "b", "Hom covered less of the floor than WT (%s) though they walked farther (%s)"
             % (F.pstr(rc["p"]), F.pstr(rw["p"])))
    specs = [("R|s0", "Concentration of position (0-1)", "Keeping to one direction"),
             ("cells_visited|s0", "Share of the floor visited (0-1)", "How much of the floor they covered"),
             ("walk_m|s0", "Distance walked on the floor (m)", "How much they walked")]
    for j, (mid, lab, t) in enumerate(specs):
        ax = F.axes_in(fig, 0.75 + j * 1.68, yb + 0.78, 1.25, 1.25)
        ga_dots(ax, mid, lab, "%s\nHom vs WT %s (+ age %s)\nHom young vs old %s" % (
            t, F.pstr(F.P(mid, "Hom_vs_WT")), F.pstr(F.P(mid, "Hom_vs_WT_adj_age")), F.pstr(F.P(mid, "young_vs_old_Hom"))),
            marks="all", compact=True)
    yc = yb + 2.75
    J = D.SHOCKJ
    piv = J.pivot_table(index="mouse", columns="session", values="jump")
    s0j = piv[0]
    trj = piv.loc[:, 1:16].median(axis=1)
    ok = np.isfinite(s0j) & np.isfinite(trj)
    w = st.wilcoxon(s0j[ok], trj[ok])
    F.letter(fig, 0.4, yc, "c", "The voltage was off: no speed jump at the logged s0 'shocks', unlike at real shocks (%s)"
             % F.pstr(w.pvalue))
    ax = F.axes_in(fig, 0.75, yc + 0.35, 2.0, 1.4)
    for m in piv.index:
        ax.plot([0, 1], [s0j[m], trj[m]], color="#d5d8de", lw=0.5, zorder=1)
        F.scatter_mouse(ax, 0, s0j[m], m, size=12)
        F.scatter_mouse(ax, 1, trj[m], m, size=12)
    ax.axhline(0, color=F.FAINT, lw=0.6)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["habituation\n(logged 'shocks')", "s1-s16\n(median session)"])
    ax.set_xlim(-0.4, 1.4)
    ax.set_ylabel("Speed after minus before\nthe shock onset (cm/s, 0.5 s each)")
    ax.set_title("Median jump: habituation %.1f vs training %.1f cm/s\npaired Wilcoxon %s" % (
        np.nanmedian(s0j), np.nanmedian(trj), F.pstr(w.pvalue)), fontsize=5.8, loc="left")
    F.brackets(ax, [(0, 1, w.pvalue)], float(np.nanmax(np.r_[s0j[ok], trj[ok]])))
    F.put(fig, 3.05, yc + 0.4, "In training, a shock pushes the mouse's speed up by a few cm/s within half a second. In "
                               "habituation the tracker still logs a 'shock' at every entry, but the speed does not change, "
                               "mouse after mouse: nothing was delivered, as the lab runs it (voltage off, tracker on). A "
                               "handful of mice (414, 458, 476, 1629, 1633) show an s0 jump about as large as their training "
                               "jump; with a few dozen events per session that is within the noise, but their run notes are "
                               "worth a look.", 2.45, size=6.3)
    yd = yc + 2.35
    F.letter(fig, 0.4, yd, "d", "Old Hom 417 and 827 explored one side only; 448, a young Hom and WT covered the whole arena")
    picks = [("417", "Hom old"), ("827", "Hom old"), ("448", "Hom old"), ("1603", "Hom young"), ("1652", "WT young"), ("815", "WT old")]
    for j, (m, lab) in enumerate(picks):
        ax = F.axes_in(fig, 0.6 + j * 0.82, yd + 0.3, 0.76, 0.76)
        F.arena(ax)
        x, yy, sh, en = D.track(m, 0)
        ax.plot(x, yy, color=F.GCOL[F.geno(m)], lw=0.22, rasterized=True, solid_joinstyle="round")
        ax.set_title("%s, %s\n%.0f weeks" % (m, lab, F.MICE[m]["age_wk"]), fontsize=5.3, pad=1.5)
    rr = F.res("R|s0", "Hom_vs_WT")
    ry = F.res("R|s0", "young_vs_old_Hom")
    F.textcol(fig, 1.6, [
        ("What habituation is", "Session s0 runs with the shock voltage off. The tracker still logs 'shocks' and entries, but "
                                "they mean nothing, so this page reads only how the mice explore the arena before any training."),
        ("The claim", "During habituation Hom mice keep to one side of the arena more than WT and cover less of the floor, "
                      "although they walk as much or more. Old Hom are the most confined. Young Hom explore much like WT."),
        ("How to read it", "a: the average mouse of each group, drawn around the arena in the room frame. b: one dot per "
                           "mouse at one floor speed; y = young, o = old; short brackets: young vs old inside a genotype; long brackets with "
                           "bars: genotype against genotype (both ages). c: each mouse's speed change at the logged s0 "
                           "'shocks' and at real shocks in training. d: example habituation paths."),
        ("What it shows", "At one floor speed. Concentration: Hom %.2f vs WT %.2f (%s; with age in the model too %s); old Hom %.2f vs "
                          "young Hom %.2f (%s). Share of the floor visited: Hom %.2f vs WT %.2f (%s). Walked on the floor: "
                          "Hom %.0f vs WT %.0f m (%s)." % (
                              rr["mean_b"], rr["mean_a"], F.pstr(rr["p"]), F.pstr(F.P("R|s0", "Hom_vs_WT_adj_age")),
                              ry["mean_a"], ry["mean_b"], F.pstr(ry["p"]), rc["mean_b"], rc["mean_a"], F.pstr(rc["p"]),
                              rw["mean_b"], rw["mean_a"], F.pstr(rw["p"]))),
        ("Why it matters", "A mouse that keeps to one part of the arena from the start can look like a good avoider on day 1 "
                           "without learning anything. It also suggests a way into hypothesis 2: old Hom may be more anxious "
                           "or less exploratory before training (459's SoftMouse note calls it 'extremely anxious')."),
        ("Caveats", "Six old Hom, all from 2024. The side they keep to differs from mouse to mouse (413 stayed near where the "
                    "zone is during training; 417, 448 and 827 across from it), so it is not one room cue. Keeping to one "
                    "side reaches %s only at one floor speed (raw %s), and for this measure the genotypes' speed slopes "
                    "differ (speed supplement, page 3); covering less of the floor holds either way (raw %s)."
                    % (F.pstr(rr["p"]), F.pstr(F.P("R|s0", "Hom_vs_WT", raw=True)), F.pstr(F.P("cells_visited|s0", "Hom_vs_WT", raw=True)))),
        ("To replicate", "An open-field or habituation-only session in young and old Hom and WT, same day, same floor speed."),
    ])
    F.save(fig, OUT, "07_story4_habituation")


# ============================================================================ story 5: circle diagrams
def story5():
    C = F.A["CIRC"]
    cm_ = {g: C[(C.group == g) & (C.test == "circular mean")].iloc[0] for g in G3}
    off = {g: 180 - abs(cm_[g].mean_deg) for g in G3}
    fig, y = F.page("Where each mouse waits by the end of training: the circle diagrams", "STORY 5 · HYPOTHESIS 3 · THE PATHS",
                    number=8)
    F.letter(fig, 0.4, y + 0.2, "a", "By the last session most mice of every genotype wait in the half away from the zone; the "
                                     "poorest avoiders wander everywhere", width=7.6)
    F.put(fig, 0.5, y + 0.3,
          "One circle per mouse, seen from the camera; red wedge = the shock zone, fixed in the room; the floor turns counter-"
          "clockwise. Line: the path in the last session (s16), in the genotype's color. Red dots: its shocks. Outer ring: where "
          "the mouse spent day 2 (s9-s16), darker = more time. Mice are sorted within each genotype from the fewest to the most "
          "day-2 entrances per turn (number under the circle); circle = young, square tag = old; * = flagged.", 7.5, size=6.3,
          color=F.INK)
    y += 0.8
    vmax = 0.25
    order = []
    for g in G3:
        ms = sorted(D.by(g=g), key=lambda m: F.VALS["entrances_per_rev|d2"][m])
        order.append((g, ms))
    per_row, size, gapx, rowh = 10, 0.62, 0.11, 0.9
    W, H = fig.get_size_inches()
    for g, ms in order:
        F.put(fig, 0.5, y, "%s (n = %d)" % (g, len(ms)), 3, size=7.5, color=F.GCOL[g], weight="bold")
        y += 0.2
        for i, m in enumerate(ms):
            r, c = divmod(i, per_row)
            ax = F.axes_in(fig, 0.5 + c * (size + gapx), y + r * rowh, size, size)
            F.arena(ax, ring_color="#cfd3da")
            F.occupancy_ring(ax, D.occ(m, range(9, 17)), cmap="Greys", vmax=vmax)
            x, yy, sh, en = D.track(m, 16)
            ax.plot(x, yy, color=F.GCOL[g] if g != "WT" else "#6f6f6f", lw=0.2, rasterized=True, solid_joinstyle="round",
                    solid_capstyle="round")
            ax.scatter(x[sh], yy[sh], s=2.5, color=F.ZONE, zorder=3, lw=0)
            ax.set_xlim(-F.R_ARENA * 1.2, F.R_ARENA * 1.2)
            ax.set_ylim(-F.R_ARENA * 1.2, F.R_ARENA * 1.2)
            tag = "%s%s %s" % (m, "*" if m in F.FLAG else "", "○" if F.young(m) else "□")
            fig.text((0.5 + c * (size + gapx) + size / 2) / W, 1 - (y + r * rowh + size + 0.02) / H,
                     "%s\n%.0f wk · %.2f/turn" % (tag, F.MICE[m]["age_wk"], F.VALS["entrances_per_rev|d2"][m]),
                     fontsize=4.6, ha="center", va="top", color=F.INK, linespacing=1.1)
        y += (int(np.ceil(len(ms) / per_row))) * rowh + 0.1
    y += 0.12
    F.letter(fig, 0.4, y + 0.05, "b", "WT and Hom wait about %.0f° short of the exact opposite, on the pre-shock side; Het wait "
                                      "nearer the opposite (%s)" % ((off["WT"] + off["Hom"]) / 2, F.pstr(F.circ_p("Het_vs_WT"))),
             width=7.6)
    for j, g in enumerate(G3):
        ax = F.axes_in(fig, 0.6 + j * 1.25, y + 0.42, 0.95, 0.95, projection="polar")
        ax.bar(np.radians(F.SECTOR[0]), 1, width=np.radians(60), color=F.ZONE, alpha=0.12, lw=0)
        for m in D.by(g=g):
            a = np.radians(F.A["CONS"]["d2_dir"][m] + F.SECTOR[0])
            ax.plot([a, a], [0, F.A["CONS"]["d2_R_pooled"][m]], color=F.GCOL[g], lw=0.8, alpha=0.85)
        cm = cm_[g]
        ax.annotate("", xy=(np.radians(cm.mean_deg + F.SECTOR[0]), cm.R), xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-|>", color=F.INK, lw=1.2))
        ax.set_ylim(0, 1)
        ax.set_xticks(np.radians(np.mod([F.SECTOR[0], F.SECTOR[0] - 90, F.SECTOR[0] + 180, F.SECTOR[0] + 90], 360)))
        ax.set_xticklabels(["zone", "pre", "opp", "post"], fontsize=5)
        ax.set_thetalim(0, 2 * np.pi)
        ax.tick_params(axis="x", pad=-3)
        ax.set_yticks([])
        ax.spines["polar"].set_color("#c9ccd3")
        ax.set_title("%s: %.0f° from the zone center" % (g, abs(cm.mean_deg)), fontsize=5.8, pad=6, color=F.GCOL[g])
    F.put(fig, 4.4, y + 0.45,
          "One line per mouse pointing where it spent day 2 (longer = more of the time in that direction); black arrow = the "
          "genotype's mean. Every genotype ends up waiting in the half away from the zone. WT point about %.0f° from the zone "
          "center, toward the pre-shock side; Het about %.0f°, nearer the exact opposite (permutation inside speed bands, Het "
          "vs WT %s; Het vs Hom %s). In the circles, the poor avoiders of every genotype (right-hand end of each row) wander the whole "
          "arena: scatter goes with avoiding badly, not with being Het. Story 6 puts numbers on it."
          % (abs(cm_["WT"].mean_deg), abs(cm_["Het"].mean_deg), F.pstars(F.circ_p("Het_vs_WT")),
             F.pstars(F.circ_p("Hom_vs_Het"))), 3.6, size=6.2, color=F.INK)
    F.save(fig, OUT, "08_story5_circle_paths")


if __name__ == "__main__":
    story3()
    story4()
    story5()
