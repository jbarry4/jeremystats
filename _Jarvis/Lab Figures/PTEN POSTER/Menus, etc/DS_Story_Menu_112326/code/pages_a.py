"""Story pages 1-4 of the DS story menu (dose, graded dose, place, synchrony). Round 3, 2026-11-23."""
import os
import pickle
import sys

import numpy as np
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import menu_data as D  # noqa: E402
import outlier as O  # noqa: E402
import stats_lib as S  # noqa: E402

OUT = os.path.join(HERE, "out")
TX = 5.95          # text column x (in)
TW = 2.05          # text column width (in)
UP = pickle.load(open(os.path.join(HERE, "uprof.pkl"), "rb"))
GROUPS3 = ["CTL", "IED-", "IED+"]


def textcol(fig, y, blocks, x=TX, w=TW):
    """Blocks of (heading, body). Returns the y where it ended."""
    for head, body in blocks:
        if head:
            y += F.put(fig, x, y, head, w, size=7.2, weight="bold") + 0.03
        y += F.put(fig, x, y, body, w, size=6.6, color=F.INK) + 0.14
    return y


def group_dots_small(fig, x, y, w, h, mid, ylabel, title, names=(), values=None):
    a = F.axes_in(fig, x, y, w, h)
    v = values if values is not None else D.values(mid)
    g = {l: F.subgroup(l) for l in v}
    F.dots(a, v, g, GROUPS3, ylabel=ylabel, xlabels=["Control", "IED−", "IED+"], names=names)
    F.defer_brackets(a, F.group_pairs(v, g, GROUPS3, F.IED_PAIRS))
    a.set_title(title, fontsize=6.4, loc="left", color=F.INK, pad=4)
    return a


def ecdf_by_group(ax, col, labs_by_group, xlabel, clip):
    """Per-event cumulative distributions: a thin line per mouse, a thick line per group (mice weighted equally)
    with its 95% band from drawing the group's mice again with replacement."""
    rc = D.rc()
    h = rc[(rc.wf == "halo") & (rc.kind == "DS")]
    grid = np.linspace(clip[0], clip[1], 240)
    rng = np.random.RandomState(2)
    m7 = None
    for g, labs in labs_by_group.items():
        curves = []
        for lab in labs:
            x = h[h.lab == lab][col].dropna().to_numpy()
            if x.size < 10:
                continue
            cdf = np.searchsorted(np.sort(x), grid, side="right") / x.size
            curves.append(cdf)
            ax.plot(grid, cdf, color=F.GROUP_COLOR[g], lw=0.9 if lab == "m7" else 0.45, alpha=0.9 if lab == "m7" else 0.5,
                    ls=(0, (3, 1.6)) if lab == "m7" else "-", zorder=2)
            if lab == "m7":
                m7 = cdf
        C = np.array(curves)
        boots = np.array([C[rng.randint(0, len(C), len(C))].mean(axis=0) for _ in range(1000)])
        ax.fill_between(grid, np.percentile(boots, 2.5, axis=0), np.percentile(boots, 97.5, axis=0), color=F.GROUP_COLOR[g],
                        alpha=0.18, lw=0, zorder=1)
        ax.plot(grid, C.mean(axis=0), color=F.GROUP_COLOR[g], lw=1.8, zorder=3)
    if m7 is not None:
        j = int(np.argmin(np.abs(m7 - 0.82)))
        ax.annotate("m7 (dashed)", xy=(grid[j], m7[j]), xytext=(-14, 4), textcoords="offset points", fontsize=5.8, color=F.SOFT,
                    ha="right", va="center", arrowprops=dict(arrowstyle="-", color=F.LEADER, lw=0.5, shrinkA=0, shrinkB=1))
    ax.text(0.97, 0.06, "thick: group mean\n(band: 95%, mice drawn again)\nthin: single mice", transform=ax.transAxes,
            fontsize=5.4, color=F.SOFT, ha="right", va="bottom", linespacing=1.25)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Share of the mouse's DS below x")
    ax.set_ylim(0, 1.01)
    ax.set_xlim(*clip)


# ============================================================================ Story 1
def story_a():
    fig, y = F.page("Two directions from control: below the IED threshold dentate spikes lose fast power; above it they gain it",
                    "STORY 1 · DOSE · HOW MUCH KNOCKOUT", number=3)
    F.legend_mice(fig, 0.55, y + 0.02)
    F.bracket_note(fig, 0.62, y + 0.22)
    y += 0.58
    hf = "rootcanal|ds_hf_median|v6||"
    v = D.values(hf)
    F.letter(fig, 0.4, y + 0.08, "a", "IED+ dentate spikes carry more fast (240–420 Hz) power than every control; "
             "IED− spikes carry less")
    F.three_ways(fig, 0.75, y + 0.62, 4.75, 1.1, v, "Fast power at the DS\n(dB over its own baseline)")
    # b: m7 tested as an outlier
    yb = y + 2.3
    pt = [l for l in F.LABS if F.META[l]["group"] != "CTL"]
    g_neg = O.grubbs({l: v[l] for l in pt if F.subgroup(l) == "IED-"}, "m7")
    g_hi = O.grubbs({l: v[l] for l in pt if F.kogroup(l) == "high KO"}, "m7")
    g_line = O.line_outlier([F.ko(l) for l in pt], [v[l] for l in pt], pt, "m7")
    T1 = F.contrast_table(v)
    T2 = F.contrast_table(v, ("m7",))
    F.letter(fig, 0.4, yb + 0.08, "b", "m7 is an outlier for its knockout level but not for its IED status; left out, high "
             "knockout separates from control (P %s)" % F.pnum(T2["highKO_vs_CTL"]["p"]))
    b1, b2, b3, _T2 = F.three_ways(fig, 0.75, yb + 0.7, 4.75, 1.1, v, "Fast power at the DS\n(dB over its own baseline)",
                                   hollow=("m7",), ko_title=False)

    def ch(cid):
        return "%s → %s" % (F.pnum(T1[cid]["p"]), F.pnum(T2[cid]["p"]))
    b1.set_title("m7 among IED− mice: not an\noutlier (Grubbs P %s)\nIED− vs ctl P %s" % (F.pnum(g_neg["p"]), ch("IEDneg_vs_CTL")),
                 fontsize=5.6, color=F.SOFT, loc="left", pad=3)
    b2.set_title("m7 among high-KO mice: an\noutlier (Grubbs P %s)\nhigh vs ctl P %s" % (F.pnum(g_hi["p"]), ch("highKO_vs_CTL")),
                 fontsize=5.6, color=F.SOFT, loc="left", pad=3)
    b3.set_title("m7 against the PTEN line: an\noutlier (P %s)\nρ %+.2f → %+.2f, P %s" % (
        F.pnum(g_line["p"]), T1["KO_dose_PTEN"]["effect"], T2["KO_dose_PTEN"]["effect"], ch("KO_dose_PTEN")),
        fontsize=5.6, color=F.SOFT, loc="left", pad=3)
    # c: every DS
    yc = yb + 2.55
    F.letter(fig, 0.4, yc + 0.08, "c", "Whole distributions move, not just medians: IED+ mice shift up, IED− mice down, "
             "and m7 sits lowest of all")
    a = F.axes_in(fig, 0.75, yc + 0.3, 2.3, 1.2)
    groups = {"CTL": [l for l in F.LABS if F.subgroup(l) == "CTL"], "IED-": [l for l in F.LABS if F.subgroup(l) == "IED-"],
              "IED+": [l for l in F.LABS if F.subgroup(l) == "IED+"]}
    ecdf_by_group(a, "hf", groups, "Fast power at the DS (dB)", clip=(-8, 36))
    F.put(fig, 3.35, yc + 0.28, "The mouse that separates dose from IEDs", 2.2, size=7, weight="bold")
    F.put(fig, 3.35, yc + 0.48,
          "m7 has 24% knockout, as much as the IED+ mice, but no IEDs. Its dentate spikes carry the least fast power of any "
          "mouse (5.4 dB; controls 11.9 to 14.4; IED+ 16.3 to 18.4; the dashed line in c). It is an outlier for its "
          "knockout level but sits with the IED− mice: fast power follows IED status, not the knockout number.",
          2.15, size=6.4, color=F.INK)
    # d: three more ways the sub-threshold mice differ
    yd = yc + 2.05
    F.letter(fig, 0.4, yd + 0.08, "d", "Below the IED threshold the network differs in three more ways: a quieter slow "
             "background, DS2 tied to theta, and less ripple-band power after each DS")
    sp = "around|power_1-4_pre_near_u+0.5_+1.0|v6||all"
    th = "timing|theta_rho|v6|winner|ds2"
    rp = "around|prepost_100-250_near_u-1.5_-1.0|v6||all"
    group_dots_small(fig, 0.78, yd + 0.62, 1.0, 0.95, sp, "Slow power before the DS\n(log2, over random moments)",
                     "Slow (1–4 Hz) current before\nthe DS, hilus to lower blade")
    group_dots_small(fig, 2.62, yd + 0.62, 1.0, 0.95, th, "DS2 rate vs theta power\n(Spearman ρ, 4 s bins)",
                     "DS2 come with theta")
    group_dots_small(fig, 4.46, yd + 0.62, 1.0, 0.95, rp, "Ripple band after / before\n(log2, toward CA1)",
                     "Ripple band after the DS,\ntoward CA1")
    hfp, hfn = D.p(hf, "IEDpos_vs_CTL"), D.p(hf, "IEDneg_vs_CTL")
    spn, thn, rpn = D.p(sp, "IEDneg_vs_CTL"), D.p(th, "IEDneg_vs_CTL"), D.p(rp, "IEDneg_vs_CTL")
    textcol(fig, 1.55, [
        ("The claim", "The knockout pushes dentate spikes away from control in two opposite directions. Mice with IEDs "
                      "make DS that carry more fast (fast-ripple band) power; mice without IEDs make DS that carry less, "
                      "on a quieter slow background. So the network has already changed below the IED threshold, just "
                      "not toward IEDs."),
        ("How to read it", "Every dot is one mouse (one recording). In a, the same numbers are grouped three ways: by IED "
                           "status, by knockout level, and against % knockout (line and band: Theil–Sen fit over the "
                           "PTEN mice, 95% bootstrap band; dotted line: 15%). b repeats a with m7 tested as an outlier: "
                           "Grubbs' test inside its group, and its distance from the PTEN line (studentized residual); "
                           "both allow for m7 being the most extreme mouse. Fast power is the Root Canal number: "
                           "240–420 Hz power in the 33 ms around the event, in dB over the same contact 150 ms earlier."),
        ("What it shows", "Every IED+ mouse is above every control (%s; Strict set %s) and every IED− mouse below "
                          "every control (%s). m7 is an outlier for its knockout level (Grubbs among high-knockout mice "
                          "%s; off the PTEN line %s) but not for its IED status (among IED− mice %s). Left out, "
                          "high knockout against control goes from P %s to %s and the PTEN knockout correlation from "
                          "ρ %+.2f (P %s) to %+.2f (P %s). Before the DS, slow current is lower in IED− mice "
                          "(%s); DS2 follow theta more (%s); ripple-band power toward CA1 drops after a DS (%s)."
                          % (F.pstr(hfp[0]), F.pstr(hfp[3]), F.pstr(hfn[0]), F.pstr(g_hi["p"]), F.pstr(g_line["p"]),
                             F.pstr(g_neg["p"]), F.pnum(T1["highKO_vs_CTL"]["p"]), F.pnum(T2["highKO_vs_CTL"]["p"]),
                             T1["KO_dose_PTEN"]["effect"], F.pnum(T1["KO_dose_PTEN"]["p"]), T2["KO_dose_PTEN"]["effect"],
                             F.pnum(T2["KO_dose_PTEN"]["p"]), F.pstr(spn[0]), F.pstr(thn[0]), F.pstr(rpn[0]))),
        ("Why it matters", "This answers the question the recordings were set up for: does knockout below the ~15% "
                           "seizure threshold change the network? Here it does, in the IED− mice. And IED status, "
                           "more than the knockout number, sets the direction: m7 fits the IED− mice and breaks the "
                           "knockout line."),
        ("Caveats", "Four IED− mice and five IED+, recorded over the same months (2023–2024); three controls are "
                    "from 2025. Fast power is a ratio to a moment 150 ms earlier, so a busier baseline would also lower it. "
                    "Leaving m7 out (b) shows how much one mouse moves the numbers; a keeps every mouse."),
        ("To replicate", "Fast power at the DS, per mouse, in new IED− and IED+ mice; a second high-knockout mouse "
                         "without IEDs would show whether m7 is a type or a one-off."),
    ])
    F.save(fig, OUT, "03_story1_two_directions")
    return {"g_neg": g_neg, "g_hi": g_hi, "g_line": g_line, "T1": T1, "T2": T2}


# ============================================================================ Story 2
DOSE = [
    ("laminar|profile_v_+0.95|v6||all", "The sink ends more abruptly on its cell-layer side as knockout rises","CSD just inside the main sink\n(units of that sink)", False,
     "How much current is already flowing just inside each blade's main sink (95% of the way out from the cell-layer "
     "source), as a share of the sink itself. It rises toward zero with knockout: the sink ends more abruptly on its "
     "cell-layer side."),
    ("around|locked_30-60_post_near_u+0.5_+1.0|v6|winner|ds1x", "Slow gamma locks more tightly after DS1 as knockout rises","Slow gamma (30–60 Hz)\nlined up after DS1", False,
     "After a DS1, slow-gamma current from the hilus to the lower blade lines up from event to event more than chance, "
     "and more so with knockout (1 = no more than random moments)."),
    ("laminar|net_between_median|v6|winner|ds1", "The return current during DS1 weakens as knockout rises","Net current between the blades\n(+ = source; units of the sink)", False,
     "During a DS1, the return current between the two blades' sinks weakens with knockout. No value for m7: none of "
     "its 15 DS1 has a sink at the main-sink contacts (its DS1 sink sits farther out); likewise m1, m26 and m61."),
    ("timing|iei_median|v6|winner|ds2", "DS2 come farther apart as knockout rises","Median interval between DS2 (s)\n(log scale)", True,
     "DS2 events come farther apart the higher the knockout. Log scale, so every mouse is on the plot (m3: 151 s)."),
    ("waveform|sink_pre_median|v6|winner|ds2x", "The DS2 sink builds later and faster as knockout rises","Sink 30–10 ms before the DS2 peak\n(share of the peak)", False,
     "Less of the DS2 sink has built up 10–30 ms before its peak: the sink rises later and faster with knockout."),
    ("around|prepost_100-250_far_u-0.5_+0.0|v6|winner|ds2x", "Ripple-band current after DS2 grows with knockout","Ripple band (100–250 Hz)\nafter over before DS2 (log2)", False,
     "In the upper blade's outer dendrites, ripple-band current is higher in the half second after a DS2 than before it, "
     "the more so the higher the knockout."),
]


def story_b():
    fig, y = F.page("Inside the PTEN group, six features of the dentate spike scale with the knockout percentage",
                    "STORY 2 · DOSE · GRADED WITH KNOCKOUT", number=4)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.4
    W, H = 2.05, 1.25
    xs = [0.8, 3.55]
    strict = []
    for k, (mid, title, ylab, log, words) in enumerate(DOSE):
        col, row = k % 2, k // 2
        x0 = xs[col]
        y0 = y + row * 2.9
        F.letter(fig, x0 - 0.42, y0 + 0.08, "abcdef"[k], title, width=2.6)
        a = F.axes_in(fig, x0, y0 + 0.42, W, H)
        v = D.values(mid)
        F.ko_scatter(a, v, ylabel=ylab, log=log)
        pp = D.p(mid, "KO_dose_PTEN")
        strict.append(pp[3])
        a.set_title("PTEN ρ %+.2f, %s" % (pp[2], F.pstr(pp[0])), fontsize=6.0, color=F.SOFT, loc="left", pad=3)
        F.put(fig, x0 - 0.2, y0 + 0.42 + H + 0.42, words, W + 0.35, size=6.2, color=F.SOFT)
    textcol(fig, 1.55, [
        ("The claim", "Among the nine PTEN mice, several features of the dentate spike change steadily with the share "
                      "of granule cells knocked out: the sink's inner edge, how the current returns between the blades, "
                      "how often DS2 come, how fast their sink builds, and how fast rhythms line up around them."),
        ("How to read it", "One dot per mouse against its knockout percentage (histology). Controls are drawn at 0 for "
                           "reference; the line and band (Theil–Sen fit, 95% bootstrap band) are over the PTEN mice "
                           "only. ρ is the rank correlation over the PTEN mice; the generous P is the smallest of "
                           "Spearman (exact over every ordering of nine mice), Pearson and Kendall."),
        ("What it shows", "All six also hold on the Strict event set (Strict P %s to %s). The strongest is the sink's inner "
                          "edge (Pearson r 0.95). DS1 and DS2 here are each recording's own classification (the winner); "
                          "DS3 events are left out where the label says DS2x." % (F.pnum(min(strict)), F.pnum(max(strict)))),
        ("Why it matters", "A graded relation is what somatic mosaicism predicts if every knocked-out cell adds its share: "
                           "no threshold is needed for these features. Together with Story 1 it suggests two kinds of "
                           "change: graded ones (here) and IED-linked ones (fast power, borderline transients)."),
        ("Caveats", "Nine mice, in two clusters (3.9–5.2% and 18.9–28.4%) with nothing between, so each line "
                    "is close to a two-group difference. IED+ mice are the high-knockout mice except m7."),
        ("To replicate", "Mice between 5% and 19% knockout would show whether these are lines or steps."),
    ])
    F.save(fig, OUT, "04_story2_graded_with_knockout")


# ============================================================================ Story 3
def per_bin(curves_by_lab, a_labs, b_labs):
    """Generous P at every depth between two groups of mice (one value per mouse per depth)."""
    G = UP["UGRID"]
    p = np.full(G.size, np.nan)
    for j in range(G.size):
        A = [curves_by_lab[l][j] for l in a_labs if np.isfinite(curves_by_lab[l][j])]
        B = [curves_by_lab[l][j] for l in b_labs if np.isfinite(curves_by_lab[l][j])]
        if len(A) >= 3 and len(B) >= 3 and np.ptp(A + B) > 0:
            p[j] = S.two(A, B)["p"]
    return p


def story_c():
    fig, y = F.page("Where it happens: in IED+ mice the dentate spike's balance tips toward the lower (infrapyramidal) blade",
                    "STORY 3 · PLACE · WHICH BLADE", number=5)
    F.legend_mice(fig, 0.55, y + 0.02)
    F.bracket_note(fig, 0.62, y + 0.22)
    y += 0.58
    G, R, ref = UP["UGRID"], UP["regions"], UP["ref_ctl"]
    recs = {lab: UP["recs"][("v6", lab)] for lab in F.LABS}
    cur = {l: recs[l]["u_peak_raw"] / ref for l in F.LABS}
    ylo, yhi = -1.0, 1.85
    inr = (G >= ylo) & (G <= yhi)
    allv = np.concatenate([cur[l][inr] for l in F.LABS])
    xlo, xhi = np.nanmin(allv) - 0.08, np.nanmax(allv) + 0.08
    F.letter(fig, 0.4, y + 0.08, "a", "On one common scale, IED− dentate spikes carry about half the control current, "
             "and IED+ spikes lean on the lower blade")
    labs_g = {g: [l for l in F.LABS if F.subgroup(l) == g] for g in GROUPS3}
    words = {"CTL": "Control", "IED-": "PTEN IED−", "IED+": "PTEN IED+"}
    for k, g in enumerate(GROUPS3):
        a = F.axes_in(fig, 1.5 + k * 0.97, y + 0.52, 0.86, 2.35)
        a.set_ylim(yhi, ylo)
        F.shade_regions(a, R, labels=(k == 0))
        C = np.array([cur[l] for l in labs_g[g]])
        for l, c in zip(labs_g[g], C):
            a.plot(c, G, color=F.color_of(l), lw=0.6, alpha=0.7, ls=(0, (3, 1.5)) if l == "m7" else "-", zorder=2)
        m = np.nanmean(C, axis=0)
        se = np.nanstd(C, axis=0, ddof=1) / np.sqrt(np.sum(np.isfinite(C), axis=0))
        a.fill_betweenx(G, m - se, m + se, color=F.INK, alpha=0.16, lw=0, zorder=3)
        a.plot(m, G, color=F.INK, lw=1.5, zorder=4)
        a.axvline(0, color=F.FAINT, lw=0.5, zorder=1)
        a.set_xlim(xlo, xhi)
        a.set_ylim(yhi, ylo)
        a.set_title("%s (n %d)" % (words[g], len(labs_g[g])), fontsize=6.6, loc="left")
        if k == 1:
            a.set_xlabel("CSD at the DS peak (−1 = the control average's deepest sink)")
    # overlay of the three means, with depth-by-depth tests
    a = F.axes_in(fig, 4.5, y + 0.52, 1.05, 2.35)
    a.set_ylim(yhi, ylo)
    F.shade_regions(a, R, labels=False)
    for g in GROUPS3:
        C = np.array([cur[l] for l in labs_g[g]])
        m = np.nanmean(C, axis=0)
        se = np.nanstd(C, axis=0, ddof=1) / np.sqrt(np.sum(np.isfinite(C), axis=0))
        a.fill_betweenx(G, m - se, m + se, color=F.GROUP_COLOR[g], alpha=0.22, lw=0, zorder=3)
        a.plot(m, G, color=F.GROUP_COLOR[g] if g != "CTL" else "#6b6b6b", lw=1.4, zorder=4)
    a.axvline(0, color=F.FAINT, lw=0.5, zorder=1)
    mlo = min(np.nanmin(np.nanmean([cur[l] for l in labs_g[g]], axis=0)[inr]) for g in GROUPS3)
    mhi = max(np.nanmax(np.nanmean([cur[l] for l in labs_g[g]], axis=0)[inr]) for g in GROUPS3)
    a.set_xlim(mlo - 0.25, mhi + 0.25)
    a.set_ylim(yhi, ylo)
    a.set_title("The three means", fontsize=6.6, loc="left")
    p_neg = per_bin(cur, labs_g["CTL"], labs_g["IED-"])
    p_pos = per_bin(cur, labs_g["CTL"], labs_g["IED+"])
    p_pn = per_bin(cur, labs_g["IED-"], labs_g["IED+"])
    for xf, p, col in ((1.06, p_neg, F.C_NEG), (1.13, p_pos, F.C_POS), (1.20, p_pn, F.INK)):
        F.sig_bar_y(a, G, (p < 0.05) & inr, xf, col, lw=2.4)
    F.put(fig, 4.45, y + 3.13, "Bars: depths where P < 0.05 — IED− vs control (pink), IED+ vs control "
          "(magenta), IED+ vs IED− (black).", 1.45, size=5.5, color=F.SOFT)
    # b: one number per mouse per region, and at the two sink peaks
    yb = y + 3.62
    j0, j1 = int(np.argmin(np.abs(G - 0.0))), int(np.argmin(np.abs(G - 1.0)))
    cells = [("CA1", (G >= ylo) & (G < R["top"])), ("Upper blade, distal", (G >= R["top"]) & (G < 0.0)),
             ("Upper blade, sink peak", j0), ("Upper blade, proximal", (G >= 0.0) & (G < R["gu"])),
             ("Hilus", (G >= R["gu"]) & (G < R["gl"])), ("Lower blade, proximal", (G >= R["gl"]) & (G < 1.0)),
             ("Lower blade, sink peak", j1), ("Lower blade, distal", (G >= 1.0) & (G < R["bot"]))]
    region_p = {}
    for i, (name, sel) in enumerate(cells):
        col, row = i % 4, i // 4
        a = F.axes_in(fig, 0.95 + col * 1.2, yb + 0.5 + row * 1.25, 0.88, 0.72)
        vals = {l: float(cur[l][sel]) if isinstance(sel, int) else float(np.nanmean(cur[l][sel])) for l in F.LABS}
        g3 = {l: F.subgroup(l) for l in vals}
        F.dots(a, vals, g3, GROUPS3, ylabel="CSD (control\ndeepest sink = −1)" if col == 0 else "", xlabels=["Ctl", "IED−", "IED+"])
        pairs = F.group_pairs(vals, g3, GROUPS3, F.IED_PAIRS)
        F.defer_brackets(a, pairs)
        region_p[name] = {cid: p for (cid, _a, _b), (_x1, _x2, p) in zip(F.IED_PAIRS, pairs)}
        a.axhline(0, color=F.FAINT, lw=0.5, zorder=0)
        a.set_title(name, fontsize=6.2, loc="left")
        a.tick_params(axis="x", labelsize=5.8)
    pos_sig = [n for n, d_ in region_p.items() if d_.get("IEDpos_vs_CTL", 1) < 0.05]
    F.letter(fig, 0.4, yb + 0.08, "b", "IED− sinks are smaller than control at both peaks (P %s and %s); %s" % (
        F.pnum(region_p["Upper blade, sink peak"]["IEDneg_vs_CTL"]), F.pnum(region_p["Lower blade, sink peak"]["IEDneg_vs_CTL"]),
        "no single region separates IED+ mice from control" if not pos_sig else "IED+ differ from control in " + ", ".join(pos_sig).lower()))
    # c: blade balance three ways
    bb = "laminar|blade_balance_mean|v6||all"
    yc = yb + 2.85
    F.letter(fig, 0.4, yc + 0.08, "c", "Inside each event, IED+ and high-knockout mice tip the balance toward the lower blade "
             "(balance = (upper sink − lower sink) / (upper + lower))")
    F.three_ways(fig, 0.85, yc + 0.58, 4.6, 1.0, D.values(bb), "Blade balance\n(− = lower blade larger)")
    pb, ph, pk = D.p(bb, "IEDpos_vs_CTL"), D.p(bb, "highKO_vs_CTL"), D.p(bb, "KO_dose_all")
    p3 = D.p("laminar|blade_balance_median|v6|winner|ds3", "PTEN_vs_CTL")
    up, lo = region_p["Upper blade, sink peak"], region_p["Lower blade, sink peak"]
    mean_at = {g: (np.mean([cur[l][j0] for l in labs_g[g]]), np.mean([cur[l][j1] for l in labs_g[g]])) for g in GROUPS3}
    deep = {l: recs[l]["ref"] / ref for l in F.LABS}
    textcol(fig, 1.55, [
        ("The claim", "In IED+ mice the dentate spike's balance tips toward the lower (infrapyramidal) blade, and in "
                      "IED− mice the whole spike is smaller. On one common scale, the IED+ lower-blade sink is the "
                      "largest of the three groups and the upper-blade sink smaller than control; IED− spikes carry "
                      "about half the control current in both blades."),
        ("How to read it", "a: each mouse's mean CSD at the DS peak. Depth comes from the spike itself: 0 is where that "
                           "mouse's upper-blade sink peaks and 1 where its lower-blade sink peaks. No mouse is scaled on "
                           "its own: every curve is divided by one number, the control average's deepest sink, so sizes "
                           "compare across groups. Regions come from the spike too (median over the 16 recordings): "
                           "each blade runs from its cell-layer current source (proximal dendrites) through the sink "
                           "peak to where the sink ends (distal dendrites); the hilus lies between the two blades' "
                           "cell-layer sources. b: a's current averaged over each region, and at each sink peak. "
                           "c: compares the two blades inside each event, so a mouse's overall size drops out."),
        ("What it shows", "At the sink peaks (b), IED− against control: upper %s, lower %s (means %.2f and %.2f "
                          "against %.2f and %.2f). IED+ against control: upper %.2f (%s), lower %.2f (%s): the balance "
                          "shift, but the overall size varies widely between IED+ mice (deepest sink %.1f to %.1f times "
                          "the control average), so neither blade alone is significant. Inside each event the shift is "
                          "clear: blade balance IED+ against control %s, high knockout against control %s, against "
                          "knockout over all mice ρ %+.2f (%s); the Strict set agrees. DS3 events lean on the lower "
                          "blade in every PTEN mouse (%s)."
                          % (F.pstr(up["IEDneg_vs_CTL"]), F.pstr(lo["IEDneg_vs_CTL"]), mean_at["IED-"][0], mean_at["IED-"][1],
                             mean_at["CTL"][0], mean_at["CTL"][1], mean_at["IED+"][0], F.pstr(up["IEDpos_vs_CTL"]),
                             mean_at["IED+"][1], F.pstr(lo["IEDpos_vs_CTL"]), min(deep[l] for l in labs_g["IED+"]),
                             max(deep[l] for l in labs_g["IED+"]), F.pstr(pb[0]), F.pstr(ph[0]), pk[2], F.pstr(pk[0]),
                             F.pstr(p3[0]))),
        ("Why it matters", "The 'place' step: the change sits on the blade that also starts the IEDs (hilus and lower "
                           "blade in the old IED analysis) and holds the most knockout cells. Blade input is asymmetric "
                           "(lateral entorhinal mostly to the upper blade, medial to the lower), so a lower-blade shift "
                           "may also be an input story. Smaller IED− spikes are a second 'two directions' result "
                           "(Story 1)."),
        ("Caveats", "Absolute CSD size also depends on how squarely the probe crosses each blade, on the contacts and on "
                    "the reference; the balance inside each event (c) is free of those. Regions are positions on the "
                    "spike's own axis, not histology."),
        ("To replicate", "Histology of the track and of knockout cells in each blade, in the same mice."),
    ])
    F.save(fig, OUT, "05_story3_lower_blade")


# ============================================================================ Story 4
def story_d():
    fig, y = F.page("Hypersynchrony: dentate spikes grow uniform and the two DS types merge as knockout rises",
                    "STORY 4 · SYNCHRONY", number=6)
    F.legend_mice(fig, 0.55, y + 0.02)
    F.bracket_note(fig, 0.62, y + 0.22)
    y += 0.58
    cv = "waveform|sink_amp_cv|v6||all"
    F.letter(fig, 0.4, y + 0.08, "a", "An IED+ mouse's dentate spikes vary less in size than a control's", width=2.75)
    a = F.axes_in(fig, 0.8, y + 0.45, 2.1, 1.2)
    for lab, col in (("m26", F.C_CTL), ("m34", F.C_POS)):
        s = np.asarray(UP["recs"][("v6", lab)]["sink_ev"], float)
        s = s / np.nanmedian(s)
        a.hist(s, bins=np.linspace(0, 3, 40), density=True, histtype="stepfilled", alpha=0.45, color=col,
               label="%s (%s), CV %.2f" % (lab, "control" if lab == "m26" else "IED+", np.nanstd(s) / np.nanmean(s)))
    a.set_xlabel("Deepest dentate sink per event\n(over the mouse's median)")
    a.set_ylabel("Density")
    a.legend(frameon=False, fontsize=5.8, loc="upper right")
    F.letter(fig, 3.3, y + 0.08, "b", "Every IED+ mouse makes more uniform spikes than every control", width=2.3)
    group_dots_small(fig, 3.7, y + 0.55, 1.75, 1.1, cv, "CV of sink size", "", names=("m33", "m7"))
    oe = "structure|overlap_eig2|v6||overlap"
    F.letter(fig, 0.4, y + 2.3, "c", "The split into two DS types fades as knockout rises; IED+ mice split less cleanly than IED− mice")
    F.three_ways(fig, 0.8, y + 2.85, 4.6, 1.2, D.values(oe), "Second eigenvalue of the\nsink-overlap matrix (1 = clean split)")
    F.note(fig, 0.8, y + 4.55, "m7 has no value here: one of its 125 events shares no sink with any other event, which "
           "leaves the matrix's normalization undefined.", 4.6)
    jt = "waveform|lat_source_minus_sink_sd|v6||all"
    F.letter(fig, 0.4, y + 4.95, "d", "The timing between a spike's sink and its return current loosens as knockout rises")
    F.three_ways(fig, 0.8, y + 5.5, 4.6, 1.2, D.values(jt), "SD over events of source peak\nminus sink peak (ms)")
    F.letter(fig, 0.4, y + 7.3, "e", "IED+ mice make dentate spikes at a steadier pace than IED− mice")
    group_dots_small(fig, 0.8, y + 7.72, 2.0, 0.85, "timing|minute_cv|v6||all", "CV of DS\nper minute",
                     "Minute-to-minute variation in the DS rate")
    F.put(fig, 3.2, y + 7.72, "IED− mice go the other way on sink size (b): the four IED− mice include the two "
          "most variable recordings (m33, m7), while the five IED+ mice all sit at the low end. The same two directions "
          "as fast power in Story 1.", 2.3, size=6.3, color=F.SOFT)
    p1, p2 = D.p(cv, "IEDpos_vs_CTL"), D.p(cv, "IEDpos_vs_IEDneg")
    pe, pe2 = D.p(oe, "KO_dose_PTEN"), D.p(oe, "IEDpos_vs_IEDneg")
    pj, pj2 = D.p(jt, "KO_dose_all"), D.p(jt, "highKO_vs_CTL")
    pm = D.p("timing|minute_cv|v6||all", "IEDpos_vs_IEDneg")
    textcol(fig, 1.55, [
        ("The claim", "As knockout rises, dentate spikes look more alike from one to the next (their size varies less), "
                      "the two DS types blur into one cloud, and the timing between a spike's sink and its return current "
                      "loosens. That is the signature of a network firing more as one (hypersynchrony)."),
        ("How to read it", "a and b: the deepest dentate sink of every event (on the dentate rows found from the spike "
                           "itself), over the mouse's median; its coefficient of variation is one number per mouse. c: "
                           "from the matrix of how much every pair of events' sinks overlap; its second eigenvalue is "
                           "near 1 when the events fall into two clean groups and drops when they form one cloud. d: for "
                           "every event, the peak time of the source between the blades minus the peak time of the sink; "
                           "its spread over events."),
        ("What it shows", "Sink-size spread: every IED+ mouse below every control (%s; Strict %s), IED+ below IED− "
                          "(%s). Split into two kinds: falls with knockout inside PTEN (ρ %+.2f, %s), IED+ below "
                          "IED− (%s). Source–sink timing spread rises with knockout over all mice (ρ %+.2f, "
                          "%s; high knockout against control %s). IED+ mice also make DS at a steadier pace than "
                          "IED− mice (%s)." % (F.pstr(p1[0]), F.pstr(p1[3]), F.pstr(p2[0]), pe[2], F.pstr(pe[0]),
                                                     F.pstr(pe2[0]), pj[2], F.pstr(pj[0]), F.pstr(pj2[0]), F.pstr(pm[0]))),
        ("Why it matters", "The 'synchrony' step: knockout cells fire in bursts, out of phase with their neighbors; at some "
                           "point the neighbors get pulled in. Uniform events and merging DS types are what that would look "
                           "like in the population current."),
        ("Caveats", "Only events inside each recording's detection border are in the set, and a tighter border also "
                    "narrows the spread of sizes. Small events give noisier peak times on their own."),
        ("To replicate", "Recompute the spread on every detected DS with one fixed threshold for every mouse."),
    ])
    F.save(fig, OUT, "06_story4_synchrony")


if __name__ == "__main__":
    which = sys.argv[1:] or ["a", "b", "c", "d"]
    for w in which:
        {"a": story_a, "b": story_b, "c": story_c, "d": story_d}[w]()
