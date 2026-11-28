"""The Jeremy menu (2026-11-24): Jeremy's eight questions, each answered on its own page that starts with his question
word for word ("Jeremy Asked") and a conclusive statement ("Results show"), then an appendix of every mouse in the
Strict Root Canal workflow with a summary table and an aggregate.

  python jpages.py [cover q1 q2 q3 q4 q5 q6 q7 q8 every table notes]
"""
import json
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
from matplotlib import patches
from matplotlib.lines import Line2D
from scipy import optimize
from scipy import stats as st

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import menu_data as D  # noqa: E402
import stats_lib as S  # noqa: E402
from pages_a import textcol  # noqa: E402

OUT = os.path.join(HERE, "outj")
LABS = F.LABS
PT = [l for l in LABS if F.META[l]["group"] != "CTL"]
CTL = [l for l in LABS if F.META[l]["group"] == "CTL"]
IEDP = ["m13", "m28", "m3", "m5", "m34"]
G3 = ["CTL", "IED-", "IED+"]
RUNS = os.environ.get("KRUNS", "/gpfs2/scratch/sakhava1/kcnt1_prelim/er2runs")
DATE = "2026-11-24"
_B = None
_FQ = None
_UP = None

QUESTIONS = {
    1: "Does the %KO cause changes in synaptic efficacy for dentate spikes",
    2: "Are there group differences in DS1 vs DS2 (do they make both)",
    3: "Are there differences in CSD sink for MML/OML by blade in PTEN animals by % KO",
    4: "Are there differences in dominant frequency for MML/OML by blade in PTEN animals by % KO",
    5: "Do results of 3 and 4 change when you open filters",
    6: "Blob analysis - Can you predict which mice made the abnormal dentate spikes based on %KO",
    7: "Blob analysis - As in 3 or 4, do the results change when you sort the dentate spikes by where they fall in The continuum "
       "(i.e, does a high pten ko mouse with red or pathological Dss produce as much current or high frequency signals as One of "
       "its \"normal\" Dss? More than a WT DS?)",
    8: "Blob analysis - Do the results of 7 change when you open the filter",
}


def B():
    global _B
    if _B is None:
        _B = pickle.load(open(os.path.join(HERE, "jeremy_battery.pkl"), "rb"))
    return _B


def FQ():
    global _FQ
    if _FQ is None:
        _FQ = pickle.load(open(os.path.join(HERE, "jeremy_freq.pkl"), "rb"))
    return _FQ


def UP():
    global _UP
    if _UP is None:
        _UP = pickle.load(open(os.path.join(HERE, "uprof.pkl"), "rb"))
    return _UP


# ============================================================================ page frame
def jpage(num, results, kicker=None, number=None):
    """Kicker, then Jeremy's question word for word, then the conclusive statement."""
    fig = F.plt.figure(figsize=(8.5, 11))
    F.put(fig, 0.5, 0.42, kicker or ("JEREMY MENU \u00b7 QUESTION %d" % num), 7.5, size=7, color=F.C_POS, weight="bold")
    y = 0.62
    if num in QUESTIONS:
        y += F.put(fig, 0.5, y, "Jeremy Asked: \u201c%s\u201d" % QUESTIONS[num], 7.5, size=8.6, color=F.SOFT, style="italic") + 0.06
    y += F.put(fig, 0.5, y, "Results show: " + results, 7.5, size=12, weight="bold")
    fig._hdr_y = max(1.55, y + 0.12)
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "%s" % (number if number is not None else num + 1), fontsize=6.5, color=F.FAINT, ha="right",
             va="bottom")
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, "Jeremy menu \u00b7 exploratory, P values uncorrected \u00b7 %s" % DATE, fontsize=6.5,
             color=F.FAINT, ha="left", va="bottom")
    return fig, y + 0.12


def jtext(fig, blocks):
    """The text column, started below the page's header (a long question pushes it down)."""
    return textcol(fig, getattr(fig, "_hdr_y", 1.55), blocks)


def ko_panel(fig, x, y, w, h, vals, ylabel, title=None, log=False, names=True, xlabel=None):
    a = F.axes_in(fig, x, y, w, h)
    F.ko_scatter(a, vals, ylabel=ylabel, log=log, names=names)
    if xlabel is not None or w < 1.25:
        a.set_xlabel(xlabel if xlabel is not None else "% knockout")
    T = F.contrast_table(vals)
    rp, ra = T.get("KO_dose_PTEN", {}), T.get("KO_dose_all", {})
    a.set_title((title + "\n" if title else "") + "PTEN \u03c1 %+.2f, %s\nall \u03c1 %+.2f, %s" % (
        rp.get("effect", np.nan), F.pstr(rp.get("p", np.nan)), ra.get("effect", np.nan), F.pstr(ra.get("p", np.nan))),
        fontsize=5.8, color=F.SOFT, loc="left", pad=3)
    return a, T


def ied_panel(fig, x, y, w, h, vals, ylabel, title="", names=(), xl=("Control", "IED\u2212", "IED+")):
    a = F.axes_in(fig, x, y, w, h)
    g = {l: F.subgroup(l) for l in vals}
    F.dots(a, vals, g, G3, ylabel=ylabel, xlabels=list(xl), names=names)
    F.defer_brackets(a, F.group_pairs(vals, g, G3, F.IED_PAIRS))
    if title:
        a.set_title(title, fontsize=6.2, loc="left", color=F.INK)
    return a, F.contrast_table(vals)


def pp(T, cid):
    return T.get(cid, {}).get("p", np.nan)


def ef(T, cid):
    return T.get(cid, {}).get("effect", np.nan)


# ============================================================================ question 1
def es_fit(lab, sel=None):
    """Output per input: Theil-Sen fit of each DS's fast power on log2(sink / control average); the fit at the control
    average (log2 = 0) is the fast power for a standard sink; the slope is dB per doubling of the sink."""
    e = B()["events_v6"][lab]
    x = np.log2(e["sink"] / B()["ref"]["v6"])
    yv = e["hf"]
    ok = np.isfinite(x) & np.isfinite(yv) & (e["sink"] > 0)
    if sel is not None:
        ok &= sel
    if ok.sum() < 8:
        return np.nan, np.nan
    sl, ic, _a, _b = st.theilslopes(yv[ok], x[ok])
    return float(ic), float(sl)


def q1():
    P, ref = B()["per"]["v6"], B()["ref"]["v6"]
    sink = {l: P[l]["all"]["sink"] / ref for l in LABS}
    slope = {l: P[l]["all"]["slope"] / ref for l in LABS}
    outp = {l: es_fit(l)[0] for l in LABS}
    out1 = {l: es_fit(l, B()["events_v6"][l]["types"] == 1)[0] for l in LABS}
    out2 = {l: es_fit(l, B()["events_v6"][l]["types"] == 2)[0] for l in LABS}
    out1 = {l: v for l, v in out1.items() if np.isfinite(v)}
    out2 = {l: v for l, v in out2.items() if np.isfinite(v)}
    s1 = {l: P[l]["ds1"]["sink"] / ref for l in LABS if "ds1" in P[l]}
    s2 = {l: P[l]["ds2"]["sink"] / ref for l in LABS if "ds2" in P[l]}
    Ts, To = F.contrast_table(sink), F.contrast_table(outp)
    Tsl = F.contrast_table(slope)
    To1, To2, Ts1, Ts2 = (F.contrast_table(v) for v in (out1, out2, s1, s2))
    fig, y = jpage(1, "% knockout does not change how much synaptic current a dentate spike carries, but it changes what that "
                      "current produces: for the same sink, IED+ mice's DS carry more fast power, and over all mice this output "
                      "rises with knockout.")
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.55
    F.letter(fig, 0.4, y + 0.08, "a", "Synaptic strength does not follow %% knockout (PTEN \u03c1 %+.2f, P %s); only the low-knockout "
             "IED\u2212 mice carry less DS current than controls (P %s)" % (ef(Ts, "KO_dose_PTEN"), F.pnum(pp(Ts, "KO_dose_PTEN")),
                                                                         F.pnum(pp(Ts, "IEDneg_vs_CTL"))))
    F.three_ways(fig, 0.75, y + 0.62, 4.75, 1.05, sink, "DS sink at its peak\n(control average = 1)")
    yb = y + 2.3
    F.letter(fig, 0.4, yb + 0.08, "b", "For the same synaptic current, DS fast power rises with knockout over all mice (\u03c1 %+.2f, "
             "P %s) and is highest in IED+ mice (P %s)" % (ef(To, "KO_dose_all"), F.pnum(pp(To, "KO_dose_all")),
                                                          F.pnum(pp(To, "IEDpos_vs_CTL"))))
    F.three_ways(fig, 0.75, yb + 0.62, 4.75, 1.05, outp, "Fast power for a\nstandard sink (dB)")
    yc = yb + 2.3
    F.letter(fig, 0.4, yc + 0.08, "c", "Output grows with input in every group, from a higher start in IED+ mice", width=2.6)
    a = F.axes_in(fig, 0.85, yc + 0.5, 2.0, 1.3)
    bins = np.arange(-2.5, 2.01, 0.5)
    mids = (bins[:-1] + bins[1:]) / 2
    for g in G3:
        curves = []
        for l in [m for m in LABS if F.subgroup(m) == g]:
            e = B()["events_v6"][l]
            x = np.log2(e["sink"] / ref)
            row = [np.nanmean(e["hf"][(x >= lo) & (x < hi)]) if ((x >= lo) & (x < hi)).sum() >= 5 else np.nan
                   for lo, hi in zip(bins[:-1], bins[1:])]
            curves.append(row)
        C = np.array(curves, float)
        n = np.sum(np.isfinite(C), axis=0)
        m = np.where(n >= 3, np.nanmean(C, axis=0), np.nan)
        se = np.where(n >= 3, np.nanstd(C, axis=0, ddof=1) / np.sqrt(np.maximum(n, 1)), np.nan)
        col = F.GROUP_COLOR[g] if g != "CTL" else "#6b6b6b"
        a.fill_between(mids, m - se, m + se, color=F.GROUP_COLOR[g], alpha=0.2, lw=0)
        a.plot(mids, m, color=col, lw=1.4, marker="o", ms=2.5, label=F.GROUP_WORD[g])
    a.axvline(0, color=F.FAINT, lw=0.6, ls=":")
    a.set_xticks([-2, -1, 0, 1, 2])
    a.set_xticklabels(["\u00bc", "\u00bd", "1", "2", "4"])
    a.set_xlabel("DS sink (control average = 1, log scale)")
    a.set_ylabel("Fast power at the DS (dB)")
    a.legend(frameon=False, fontsize=5.6, loc="upper left")
    F.letter(fig, 3.2, yc + 0.08, "d", "DS1 and DS2 alike: both carry more fast power for the same sink in IED+ mice (P %s and %s)"
             % (F.pnum(pp(To1, "IEDpos_vs_CTL")), F.pnum(pp(To2, "IEDpos_vs_CTL"))), width=2.45)
    ied_panel(fig, 3.65, yc + 0.62, 0.82, 1.18, out1, "Fast power for a\nstandard sink (dB)", title="DS1",
              xl=("Ctl", "IED\u2212", "IED+"))
    ied_panel(fig, 4.68, yc + 0.62, 0.82, 1.18, out2, "", title="DS2", xl=("Ctl", "IED\u2212", "IED+"))
    jtext(fig, [
        ("How it was measured", "Synaptic strength: the perforant-path sink of each DS (the deepest dentate sink at the DS peak, "
                                "\u00b13 ms), median per mouse, every mouse divided by one number so that the control average "
                                "is 1; its 10\u201390%% rise slope gives the same answer (PTEN \u03c1 %+.2f, P %s). Output per "
                                "input: each DS's fast (240\u2013420 Hz) power, the band where spikes show up in the field, "
                                "fitted against its sink within each mouse (Theil\u2013Sen); the fit read at the control-average "
                                "sink is the fast power a standard synaptic current produces."
                                % (ef(Tsl, "KO_dose_PTEN"), F.pnum(pp(Tsl, "KO_dose_PTEN")))),
        ("What it shows", "Sink size: no trend with knockout in PTEN mice (\u03c1 %+.2f, P %s) or over all mice; IED\u2212 "
                          "against control P %s, IED+ against control P %s. Fast power for a standard sink: all mice \u03c1 "
                          "%+.2f (P %s), PTEN only \u03c1 %+.2f (P %s), IED+ against control P %s. By type, neither "
                          "DS1's nor DS2's sink follows knockout (PTEN P %s and %s), each timed at its own sink; for the "
                          "same sink both carry more fast power in IED+ mice (P %s and %s)."
                          % (ef(Ts, "KO_dose_PTEN"), F.pnum(pp(Ts, "KO_dose_PTEN")), F.pnum(pp(Ts, "IEDneg_vs_CTL")),
                             F.pnum(pp(Ts, "IEDpos_vs_CTL")), ef(To, "KO_dose_all"), F.pnum(pp(To, "KO_dose_all")),
                             ef(To, "KO_dose_PTEN"), F.pnum(pp(To, "KO_dose_PTEN")), F.pnum(pp(To, "IEDpos_vs_CTL")),
                             F.pnum(pp(Ts1, "KO_dose_PTEN")), F.pnum(pp(Ts2, "KO_dose_PTEN")),
                             F.pnum(pp(To1, "IEDpos_vs_CTL")), F.pnum(pp(To2, "IEDpos_vs_CTL")))),
        ("Reading", "In slice terms the input (the synaptic current) is unchanged by dose, while the coupling from input to "
                    "output is raised where IEDs appear. The low-knockout mice go the other way on the input: smaller "
                    "sinks, as in Story 3 of the DS menu."),
        ("Caveats", "Fast power is a field measure of spiking, not single units. Absolute sink size also depends on probe "
                    "placement; the output measure compares events within each mouse first."),
    ])
    F.save(fig, OUT, "02_q1_synaptic_efficacy")


# ============================================================================ question 2
def q2():
    P, ref = B()["per"]["v6"], B()["ref"]["v6"]
    U = UP()

    def both(l):
        d = P[l]
        return d["si"] is not None and min(d["n1"], d["n2"]) >= max(5, 0.05 * d["n"]) and d["si"] >= 0.45
    cnt = {g: (sum(both(l) for l in LABS if F.subgroup(l) == g), sum(1 for l in LABS if F.subgroup(l) == g)) for g in G3}
    r1 = {l: P[l]["n1"] / P[l]["dur_min"] for l in LABS if P[l]["si"] is not None}
    r2 = {l: P[l]["n2"] / P[l]["dur_min"] for l in LABS if P[l]["si"] is not None}
    sh = {l: P[l]["n1"] / max(P[l]["n1"] + P[l]["n2"], 1) for l in LABS if P[l]["si"] is not None}
    drise = {l: P[l]["ds1"]["rise"] - P[l]["ds2"]["rise"] for l in LABS if "ds1" in P[l] and "ds2" in P[l]}
    T1, T2, T3, Td = (F.contrast_table(v) for v in (r1, r2, sh, drise))
    oe = D.values("structure|overlap_eig2|v6||overlap")
    To = F.contrast_table(oe)
    fig, y = jpage(2, "Most mice in every group make both DS types; with knockout DS2 become rarer and the two types grow "
                      "harder to tell apart, while their sink timing holds.")
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.55
    F.letter(fig, 0.4, y + 0.08, "a", "Most mice in every group make both types: control %d of %d, IED\u2212 %d of %d, IED+ %d of %d"
             % (cnt["CTL"] + cnt["IED-"] + cnt["IED+"]))
    a = F.axes_in(fig, 0.85, y + 0.5, 2.0, 1.25)
    rng = np.random.RandomState(2)
    for k, g in enumerate(G3):
        for l in [m for m in LABS if F.subgroup(m) == g]:
            si = P[l]["si"]
            xv = k + rng.uniform(-0.15, 0.15)
            if si is None:
                a.scatter([xv], [0.02], marker="x", s=18, color=F.color_of(l), lw=0.9, zorder=4)
                F.defer_labels(a, [(xv, 0.02)], ["%s: no split" % l])
                continue
            F.mouse_dot(a, xv, si, l, hollow=not both(l))
    a.axhline(0.45, color=F.SOFT, lw=0.6, ls="--")
    a.text(2.45, 0.455, "0.45", fontsize=5.3, color=F.SOFT, va="bottom", ha="right")
    a.set_xticks(range(3))
    a.set_xticklabels(["Control", "IED\u2212", "IED+"])
    a.tick_params(axis="x", length=0)
    a.set_xlim(-0.5, 2.5)
    a.set_ylim(0, 1.0)
    a.set_ylabel("Separation index of the\nDS1/DS2 split (winner)")
    F.put(fig, 3.1, y + 0.5, "The call: a mouse makes both when its DS1/DS2 split has a separation "
          "index of at least 0.45 and each type holds at least 5%% of its events (and 5 events), the battery's own rule. "
          "Filled: makes both; open: one cloud. The groups do not differ in how many make both (Fisher's exact test, IED+ "
          "against control P %s)." % F.pnum(st.fisher_exact([[cnt["IED+"][0], cnt["IED+"][1] - cnt["IED+"][0]],
                                                              [cnt["CTL"][0], cnt["CTL"][1] - cnt["CTL"][0]]])[1]),
          2.45, size=6.3, color=F.INK)
    yb = y + 2.25
    F.letter(fig, 0.4, yb + 0.08, "b", "With knockout, DS2 come less often (PTEN \u03c1 %+.2f, P %s) and DS1 make up more of the events"
             % (ef(T2, "KO_dose_PTEN"), F.pnum(pp(T2, "KO_dose_PTEN"))))
    for i, (vals, lab_, tl) in enumerate(((r1, "DS1 per minute", "DS1 rate"), (r2, "DS2 per minute", "DS2 rate"),
                                         (sh, "DS1 share of DS1 + DS2", "Mix"))):
        ko_panel(fig, 0.95 + i * 1.72, yb + 0.8, 1.05, 1.0, vals, lab_, title=tl, log=(i < 2))
    yc = yb + 2.35
    F.letter(fig, 0.4, yc + 0.08, "c", "The split between the types fades with knockout and DS1 sits nearer DS2 in IED+ mice; "
             "their sink timing does not change (P %s)" % F.pnum(pp(Td, "KO_dose_PTEN")))
    ko_panel(fig, 0.95, yc + 0.8, 1.05, 1.0, drise, "DS1 minus DS2 sink\nrise time (ms)", title="Timing")
    ko_panel(fig, 2.67, yc + 0.8, 1.05, 1.0, oe, "Second eigenvalue\n(1 = clean split)", title="How cleanly they split")
    a = F.axes_in(fig, 4.39, yc + 0.8, 1.05, 1.0)
    recs = {l: U["recs"][("v6", l)] for l in LABS}
    gap = {l: recs[l]["c_ds1_upper"] - recs[l]["c_ds2_upper"] for l in LABS if "c_ds1_upper" in recs[l] and "c_ds2_upper" in recs[l]}
    g3 = {l: F.subgroup(l) for l in gap}
    F.dots(a, gap, g3, G3, ylabel="DS1 minus DS2 sink\nposition, upper blade", xlabels=["Ctl", "IED\u2212", "IED+"])
    F.defer_brackets(a, F.group_pairs(gap, g3, G3, F.IED_PAIRS))
    a.set_title("Where they sit", fontsize=5.8, color=F.SOFT, loc="left", pad=3)
    a.axhline(0, color=F.FAINT, lw=0.5)
    jtext(fig, [
        ("How it was measured", "DS1 and DS2 are each recording's own split (the winner from the DS battery: the best "
                                "separation after DS3 events are taken out). Rates are events per minute of recording; the "
                                "mix is DS1 over DS1 + DS2. Shape: each type's sink rise (10\u201390%) timed at that type's "
                                "own deepest contact in each blade, and where its sink sits along the dendrites (0 = cell "
                                "layer, 1 = average DS sink)."),
        ("What it shows", "Makes both: control %d of %d, IED\u2212 %d of %d, IED+ %d of %d. Against knockout in PTEN mice: DS2 "
                          "per minute \u03c1 %+.2f (P %s), DS1 per minute \u03c1 %+.2f (P %s), DS1 share \u03c1 %+.2f (P %s). "
                          "DS1's rise minus DS2's does not change (\u03c1 %+.2f, P %s). The split fades with knockout "
                          "(\u03c1 %+.2f, P %s), and DS1 sits nearer DS2 in IED+ than in IED\u2212 mice (P 0.035 in the DS menu)."
                          % (cnt["CTL"] + cnt["IED-"] + cnt["IED+"] + (ef(T2, "KO_dose_PTEN"), F.pnum(pp(T2, "KO_dose_PTEN")),
                                                                      ef(T1, "KO_dose_PTEN"), F.pnum(pp(T1, "KO_dose_PTEN")),
                                                                      ef(T3, "KO_dose_PTEN"), F.pnum(pp(T3, "KO_dose_PTEN")),
                                                                      ef(Td, "KO_dose_PTEN"), F.pnum(pp(Td, "KO_dose_PTEN")),
                                                                      ef(To, "KO_dose_PTEN"), F.pnum(pp(To, "KO_dose_PTEN"))))),
        ("Caveats", "Where a recording is one cloud the DS1 and DS2 names are arbitrary, and in six recordings the type named "
                    "DS1 (sink farther out) is the larger group, so rates and shares lean on the naming; the 0.45 call and "
                    "the positions do not. m21 has no split."),
    ])
    F.save(fig, OUT, "03_q2_ds1_ds2")


# ============================================================================ question 3
def layer_vals(es, blade, layer, typ="all"):
    P, ref = B()["per"][es], B()["ref"][es]
    return {l: P[l][typ]["layers"][(blade, layer)] / ref for l in LABS if typ in P[l] and np.isfinite(P[l][typ]["layers"][(blade, layer)])}


def q3():
    U = UP()
    V = U["VGRID"]
    fig, y = jpage(3, "Within the PTEN mice, neither the MML nor the OML sink of either blade scales with % knockout; the "
                      "low-knockout (IED\u2212) mice have weaker MML sinks in both blades, and the OML is unchanged.")
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.55
    # a: mean current along each blade, low and high knockout and controls, on one scale; depth on y, blades mirrored
    F.letter(fig, 0.4, y + 0.08, "a", "Along each blade the DS sink peaks in the MML; low-knockout mice carry less there", width=2.3)
    refc = U["ref_ctl"]
    sets = {"Control": (CTL, "#6b6b6b"), "Low KO": ([l for l in PT if F.ko(l) < 10], F.C_NEG), "High KO": ([l for l in PT if F.ko(l) >= 15], F.C_POS)}
    for j, blade in enumerate(("upper", "lower")):
        a = F.axes_in(fig, 1.05, y + 0.5 + j * 1.55, 1.35, 1.3)
        a.axhspan(0.7, 1.3, color="#fdf0e4", lw=0, zorder=0)
        a.axhspan(1.3, 2.0, color="#fbe3cf", lw=0, zorder=0)
        for name, (labs, col) in sets.items():
            C = np.array([U["recs"][("v6", l)]["v_all_" + blade] * U["recs"][("v6", l)]["ref"] / refc for l in labs])
            m = np.nanmean(C, axis=0)
            se = np.nanstd(C, axis=0, ddof=1) / np.sqrt(np.sum(np.isfinite(C), axis=0))
            a.fill_betweenx(V, m - se, m + se, color=col, alpha=0.18, lw=0, zorder=2)
            a.plot(m, V, color=col, lw=1.3, label=name, zorder=3)
        a.axvline(0, color=F.FAINT, lw=0.5)
        if blade == "upper":
            a.set_ylim(-0.3, 2.3)
        else:
            a.set_ylim(2.3, -0.3)
        from matplotlib import transforms
        tr = transforms.blended_transform_factory(a.transAxes, a.transData)
        for t_, yy in (("OML", 1.65), ("MML", 1.0), ("cell\nlayer", 0.0)):
            a.text(-0.3, yy, t_, transform=tr, fontsize=5.6, ha="right", va="center", color=F.INK, clip_on=False)
        a.set_yticks([0, 1, 2])
        a.set_title("%s blade" % ("Upper" if blade == "upper" else "Lower"), fontsize=6.2, loc="left")
        if j == 1:
            a.set_xlabel("CSD at the DS peak\n(\u22121 = control deepest sink)")
        else:
            a.set_xticklabels([])
            a.legend(frameon=False, fontsize=5.4, loc="upper right")
    # b: the four sinks against % knockout
    F.letter(fig, 2.85, y + 0.08, "b", "No layer sink of either blade follows % knockout in PTEN mice", width=2.7)
    Ts = {}
    for i, (blade, layer) in enumerate((("upper", "MML"), ("upper", "OML"), ("lower", "MML"), ("lower", "OML"))):
        col, row = i % 2, i // 2
        _a, Ts[(blade, layer)] = ko_panel(fig, 3.3 + col * 1.25, y + 0.68 + row * 1.62, 1.0, 0.92, layer_vals("v6", blade, layer),
                                          "Sink (control = 1;\n\u2212 = net source)" if col == 0 else "",
                                          title="%s %s" % (blade.capitalize(), layer), names=False)
    yc = y + 4.0
    F.letter(fig, 0.4, yc + 0.08, "c", "Grouped by IED status, the MML sink is smaller in IED\u2212 mice in both blades (P %s upper, "
             "P %s lower); the OML does not differ" % (F.pnum(pp(Ts[("upper", "MML")], "IEDneg_vs_CTL")),
                                                        F.pnum(pp(Ts[("lower", "MML")], "IEDneg_vs_CTL"))))
    for i, (blade, layer) in enumerate((("upper", "MML"), ("upper", "OML"), ("lower", "MML"), ("lower", "OML"))):
        ied_panel(fig, 0.85 + i * 1.22, yc + 0.55, 0.9, 0.85, layer_vals("v6", blade, layer),
                  "Sink (control = 1;\n\u2212 = net source)" if i == 0 else "", title="%s %s" % (blade.capitalize(), layer),
                  xl=("Ctl", "IED\u2212", "IED+"))
    yd = yc + 1.95
    ie = D.values("laminar|profile_v_+0.95|v6||all")
    bb = D.values("laminar|blade_balance_mean|v6||all")
    Tie, Tbb = F.contrast_table(ie), F.contrast_table(bb)
    F.letter(fig, 0.4, yd + 0.08, "d", "From the DS menu: what does follow knockout is the sink's inner edge (\u03c1 %+.2f); the "
             "balance tips to the lower blade in IED+ mice (P %s)" % (ef(Tie, "KO_dose_PTEN"), F.pnum(pp(Tbb, "IEDpos_vs_CTL"))))
    ko_panel(fig, 0.85, yd + 0.62, 1.9, 0.95, ie, "CSD just inside the\nmain sink (units of it)", title="Sink's inner edge (Story 2)")
    ied_panel(fig, 3.45, yd + 0.62, 1.95, 0.95, bb, "Blade balance\n(\u2212 = lower larger)", title="Blade balance (Story 3)")
    jtext(fig, [
        ("How it was measured", "No layer labels. Each blade's dendritic axis comes from the recording's own DS: 0 is the "
                                "cell-layer current source, 1 the average DS sink, which sits in the middle molecular layer "
                                "(MML). MML = 0.7 to 1.3 on that axis, OML = 1.3 to 2.0. Sink = minus the CSD at the DS peak "
                                "(\u00b13 ms) over those contacts, median per mouse, every mouse divided by one number (the "
                                "control average deepest sink = 1). Controls are drawn at 0 knockout for reference. At the "
                                "DS peak the OML mostly carries return current (a net source, below 0), because most DS are "
                                "DS2, whose sink sits in the MML; DS1's own sink is in Question 2."),
        ("What it shows", "Against %% knockout in PTEN mice: upper MML \u03c1 %+.2f (P %s), upper OML %+.2f (P %s), lower MML "
                          "%+.2f (P %s), lower OML %+.2f (P %s). IED\u2212 against control: MML upper P %s, lower P %s; OML "
                          "P %s and %s."
                          % (ef(Ts[("upper", "MML")], "KO_dose_PTEN"), F.pnum(pp(Ts[("upper", "MML")], "KO_dose_PTEN")),
                             ef(Ts[("upper", "OML")], "KO_dose_PTEN"), F.pnum(pp(Ts[("upper", "OML")], "KO_dose_PTEN")),
                             ef(Ts[("lower", "MML")], "KO_dose_PTEN"), F.pnum(pp(Ts[("lower", "MML")], "KO_dose_PTEN")),
                             ef(Ts[("lower", "OML")], "KO_dose_PTEN"), F.pnum(pp(Ts[("lower", "OML")], "KO_dose_PTEN")),
                             F.pnum(pp(Ts[("upper", "MML")], "IEDneg_vs_CTL")), F.pnum(pp(Ts[("lower", "MML")], "IEDneg_vs_CTL")),
                             F.pnum(pp(Ts[("upper", "OML")], "IEDneg_vs_CTL")), F.pnum(pp(Ts[("lower", "OML")], "IEDneg_vs_CTL")))),
        ("Reading", "Dose changes the sink's shape (its inner edge, Story 2 of the DS menu) and the balance between the "
                    "blades (Story 3), not the size of the MML or OML sink; the size change belongs to the low-knockout, "
                    "IED\u2212 mice."),
        ("Caveats", "The MML and OML here are steps along each recording's own DS axis, not histology; the OML range "
                    "reaches past the analyzed band in some recordings."),
    ])
    F.save(fig, OUT, "04_q3_mml_oml_sink")


# ============================================================================ question 6
def calls(rid, target):
    import glob
    from collections import defaultdict
    per = defaultdict(list)
    for f in glob.glob(os.path.join(RUNS, rid, "results", "*.json")):
        r = json.load(open(f))
        if r["target"] != target or not r.get("passes"):
            continue
        for c in r["calls"]:
            per[c["lab"]].append(c["call"])
    return {l: np.array(v) for l, v in per.items()}


def roc(scores, truth):
    """ROC points and AUC (ties count half) for scores where a higher score means positive."""
    s = np.asarray(scores, float)
    t = np.asarray(truth, bool)
    thr = np.r_[np.inf, np.sort(np.unique(s))[::-1], -np.inf]
    fpr = [((s >= th) & ~t).sum() / max((~t).sum(), 1) for th in thr]
    tpr = [((s >= th) & t).sum() / max(t.sum(), 1) for th in thr]
    pos, neg = s[t], s[~t]
    auc = np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg])
    return np.array(fpr), np.array(tpr), float(auc)


def q6():
    hf = D.values("rootcanal|ds_hf_median|v6||")
    bt = D.values("rootcanal|tz_rate|v6||")
    ci = calls("r006", "iedpos_vs_iedneg")
    truth = {l: F.subgroup(l) == "IED+" for l in PT}
    ko_s = {l: F.ko(l) for l in PT}
    ml_s = {l: float(np.mean(ci[l])) for l in PT}
    rocs = {}
    for name, sc in (("% knockout", ko_s), ("DS fast power", {l: hf[l] for l in PT}), ("Held-out models", ml_s)):
        rocs[name] = roc([sc[l] for l in PT], [truth[l] for l in PT])
    auc_all = roc([F.ko(l) for l in LABS], [F.subgroup(l) == "IED+" for l in LABS])[2]
    fig, y = jpage(6, "%% knockout alone picks out the mice that make abnormal dentate spikes with an AUC of %.2f; m7 is the "
                      "one miss. The dentate spikes themselves do better: their fast power separates every mouse, and held-out "
                      "models get %d of 9." % (rocs["% knockout"][2], sum((ml_s[l] > 0.5) == truth[l] for l in PT)))
    F.legend_mice(fig, 0.55, y)
    y += 0.35
    rc = D.rc()
    h = rc[rc.wf == "halo"]
    rate_bt = {l: (h[(h.lab == l)].kind == "TZ").sum() / S.M[l]["dur_min"] for l in LABS}
    rate_ied = {l: (h[(h.lab == l)].kind == "IED").sum() / S.M[l]["dur_min"] for l in LABS}
    abn = {l: rate_bt[l] + rate_ied[l] for l in LABS}
    ctl_max = max(abn[l] for l in CTL)
    F.letter(fig, 0.4, y + 0.08, "a", "The abnormal-DS mice are exactly the five IED+ mice: each makes BTs and red events above "
             "the highest control rate")
    a = F.axes_in(fig, 0.85, y + 0.45, 4.55, 0.95)
    order = sorted(LABS, key=lambda l: (F.ko(l), l))
    xs = np.arange(len(order))
    for i, l in enumerate(order):
        a.bar(i, rate_bt[l], color=F.C_PDS, width=0.7, edgecolor="white", lw=0.4)
        a.bar(i, rate_ied[l], bottom=rate_bt[l], color=F.C_IED, width=0.7, edgecolor="white", lw=0.4)
    a.axhline(ctl_max, color=F.SOFT, lw=0.6, ls=":")
    a.text(-0.4, ctl_max, "highest control", fontsize=5.3, color=F.SOFT, ha="left", va="bottom")
    a.set_xticks(xs)
    a.set_xticklabels(["%s\n%.0f%%" % (l, F.ko(l)) for l in order], fontsize=5.4)
    for tl, l in zip(a.get_xticklabels(), order):
        tl.set_color(F.color_of(l) if l != "m7" else F.C_POS)
        if l == "m7":
            tl.set_fontweight("bold")
    a.set_ylabel("Events per minute")
    a.tick_params(axis="x", length=0)
    a.legend(handles=[patches.Patch(color=F.C_PDS, label="BTs (purple)"), patches.Patch(color=F.C_IED, label="IED class (red)")],
             frameon=False, fontsize=5.6, loc="upper left")
    yb = y + 2.05
    F.letter(fig, 0.4, yb + 0.08, "b", "%% knockout predicts them with AUC %.2f among PTEN mice (%.2f over all 16); DS fast power "
             "alone reaches %.2f" % (rocs["% knockout"][2], auc_all, rocs["DS fast power"][2]), width=2.75)
    a = F.axes_in(fig, 0.85, yb + 0.55, 1.75, 1.6)
    cols = {"% knockout": F.C_HIGH, "DS fast power": F.C_POS, "Held-out models": F.C_DS}
    for name, (fp, tp, auc) in rocs.items():
        a.step(fp, tp, where="post", color=cols[name], lw=1.5, label="%s, AUC %.2f" % (name, auc))
    a.plot([0, 1], [0, 1], color=F.FAINT, lw=0.6, ls="--")
    a.set_xlim(-0.02, 1.02)
    a.set_ylim(-0.02, 1.05)
    a.set_xlabel("False positives (share of IED\u2212 mice)")
    a.set_ylabel("True positives\n(share of IED+ mice)")
    a.legend(frameon=False, fontsize=5.5, loc="lower right")
    F.letter(fig, 3.2, yb + 0.08, "c", "The logistic fit on % knockout puts m7 with the IED+ mice", width=2.4)
    a = F.axes_in(fig, 3.65, yb + 0.55, 1.75, 1.6)
    xk = np.array([F.ko(l) for l in PT])
    yk = np.array([truth[l] for l in PT], float)

    def nll(b):
        z = b[0] + b[1] * xk
        return -np.sum(yk * z - np.log1p(np.exp(z)))
    bfit = optimize.minimize(nll, [0.0, 0.2], method="Nelder-Mead").x
    xx = np.linspace(0, 31, 200)
    a.plot(xx, 1 / (1 + np.exp(-(bfit[0] + bfit[1] * xx))), color=F.C_HIGH, lw=1.4)
    for l in PT:
        F.mouse_dot(a, F.ko(l), float(truth[l]), l)
    F.defer_labels(a, [(F.ko(l), float(truth[l])) for l in PT], PT)
    a.axhline(0.5, color=F.FAINT, lw=0.5, ls=":")
    a.set_yticks([0, 0.5, 1])
    a.set_yticklabels(["no", "0.5", "yes"])
    a.set_xlabel("PTEN knockout (% of granule cells)")
    a.set_ylabel("Makes abnormal DS")
    a.set_xlim(-1, 31)
    a.set_ylim(-0.12, 1.12)
    yc = yb + 2.75
    F.letter(fig, 0.4, yc + 0.08, "d", "From the DS menu (Story 8): models trained on other mice read IED status from DS features; "
             "they call m7 IED\u2212 and miss only m3, which fast power catches")
    a = F.axes_in(fig, 0.85, yc + 0.55, 2.0, 1.55)
    for l in PT:
        v = ci[l]
        a.plot([np.percentile(v, 25), np.percentile(v, 75)], [hf[l], hf[l]], color=F.color_of(l), lw=0.9, alpha=0.7)
        F.mouse_dot(a, np.mean(v), hf[l], l)
    F.defer_labels(a, [(np.mean(ci[l]), hf[l]) for l in PT], PT)
    a.axvline(0.5, color=F.SOFT, lw=0.6, ls="--")
    a.axhline(max(hf[l] for l in CTL), color=F.SOFT, lw=0.6, ls=":")
    a.set_xlim(-0.05, 1.05)
    a.set_xlabel("Held-out call: P(IED+)")
    a.set_ylabel("DS fast power (dB)")
    L = json.load(open(os.path.join(RUNS, "r006", "leaderboard.json")))
    best = {}
    for r in L["rows"]:
        best[r["target"]] = max(best.get(r["target"], 0), r["main"] or 0)
    a2 = F.axes_in(fig, 3.6, yc + 0.55, 1.8, 1.55)
    qs = [("iedpos_vs_iedneg", "IED+ vs IED\u2212"), ("low_vs_high", "Low vs high KO"), ("pten_vs_ctl", "PTEN vs control"),
          ("ied3", "Three IED groups"), ("ko_pct", "Knockout % (\u03c1)")]
    for i, (q, w) in enumerate(qs):
        a2.barh(i, best.get(q, np.nan), color=F.C_DS, height=0.6)
        a2.text(best.get(q, 0) + 0.01, i, "%.2f" % best.get(q, np.nan), va="center", fontsize=5.4)
    a2.set_yticks(range(len(qs)))
    a2.set_yticklabels([w for _q, w in qs], fontsize=5.8)
    a2.invert_yaxis()
    a2.set_xlim(0.5, 1.0)
    a2.axvline(0.8, color=F.C_POS, lw=0.6, ls="--")
    a2.set_xlabel("Best held-out score (Halo set)")
    jtext(fig, [
        ("How it was measured", "'Abnormal DS' are the Root Canal classes between and beyond the DS border: borderline "
                                "transients (purple) and the IED class (red). A mouse makes them when its rate is above the "
                                "highest control's, which picks the five IED+ mice and no other. ROC: each predictor ranks "
                                "the nine PTEN mice; AUC = the chance that an IED+ mouse outranks an IED\u2212 one. Held-out "
                                "models: the 14 IED-status models of the DS menu's Room 2.0 run (r006) that reached 0.80, "
                                "each mouse scored by models that never saw it."),
        ("What it shows", "AUC: %% knockout %.2f, DS fast power %.2f, held-out models %.2f. The logistic fit on %% knockout "
                          "places m7 (24%%, no IEDs) on the abnormal side; a 15%% cut gets 8 of 9 PTEN mice right, and the "
                          "miss is m7." % (rocs["% knockout"][2], rocs["DS fast power"][2], rocs["Held-out models"][2])),
        ("Reading", "Dose predicts the abnormal events well but not perfectly; what the dentate spikes carry (fast power) "
                    "tracks them exactly. m7 is the mouse that separates the two."),
        ("Caveats", "Nine PTEN mice, five of them positive; the same mice defined the borders. Fast power was used to draw the "
                    "borders, so its perfect split is partly built in."),
    ])
    F.save(fig, OUT, "07_q6_predict_abnormal")


# ============================================================================ appendix: every mouse in the Strict workflow
STRICT_NAME = ("Ambiguous PTEN and CTL Baseline (Optimized Paramters/Snap/10% Grace[Extraction Room; No P-spikes])) · v4")
ORDER = ["m2", "m21", "m22", "m26", "m59", "m60", "m61", "m8", "m33", "m1", "m7", "m13", "m28", "m3", "m5", "m34"]


def strict_outline(name):
    from scipy.spatial import ConvexHull
    b = json.load(open(os.path.join(HERE, "rc_borders.json"), encoding="utf-8"))["strict"]["borders"][name]
    lv = [x for x in b["border"]["levels"] if abs(x["grace"] - b["grace"]) < 1e-9][0]
    V = np.asarray(lv["shape"]["vertices"], float)
    P2 = np.column_stack([np.log10(V[:, 0]), V[:, 1]])
    hh = ConvexHull(P2)
    poly = P2[hh.vertices]
    return np.vstack([poly, poly[:1]]), b["grace"]


def strict_table():
    rc = D.rc()
    s = rc[rc.wf == "strict"].copy()
    cen_hf = json.load(open(os.path.join(HERE, "rc_borders.json"), encoding="utf-8"))["strict"]["halo_centres"]["ds"][1]
    rows = []
    for l in ORDER:
        e = s[s.lab == l]
        und = e[e.cls.isin(["both", "neither"])]
        rows.append({"mouse": l, "group": F.subgroup(l), "ko": F.ko(l), "n": len(e), "ds": int((e.cls == "ds").sum()),
                     "ied": int((e.cls == "pspike").sum()), "both": int((e.cls == "both").sum()), "neither": int((e.cls == "neither").sum()),
                     "und": len(und), "pct": 100.0 * len(und) / len(e), "hi": int((und.hf > cen_hf).sum()), "lo": int((und.hf <= cen_hf).sum()),
                     "und_hf": float(und.hf.median()) if len(und) else np.nan})
    return pd.DataFrame(rows), cen_hf


def sig2(x):
    return ("%.2g" % x) if x < 10 else ("%.0f" % x)


def strict_shape():
    """Per mouse, the undecided events against the mouse's own DS: half-width ratio and median fast power of each."""
    rc = D.rc()
    s = rc[(rc.wf == "strict") & rc.lab.isin(ORDER)]
    out = {}
    n_wide = 0
    for l in ORDER:
        e = s[s.lab == l]
        u = e[e.cls.isin(["both", "neither"])]
        d = e[e.cls == "ds"]
        wide = int((u.hw > d.hw.median()).sum())
        n_wide += wide
        out[l] = {"hw_ratio": float(u.hw.median() / d.hw.median()), "und_hf": float(u.hf.median()), "ds_hf": float(d.hf.median()),
                  "wide_pct": 100.0 * wide / max(len(u), 1)}
    n_und = int(s.cls.isin(["both", "neither"]).sum())
    n_both = int((s.cls == "both").sum())
    out["_wide_pct"] = 100.0 * n_wide / max(n_und, 1)
    return out, n_und, n_both


def every():
    rc = D.rc()
    s = rc[rc.wf == "strict"]
    T, cen_hf = strict_table()
    ds_poly, gd = strict_outline("ds")
    ied_poly, gi = strict_outline("pspike")
    m7r = T[T.mouse == "m7"].iloc[0]
    shp, n_und, n_both = strict_shape()
    fig, y = jpage(9, "Every mouse has undecided events, mostly wider than its DS; IED+ mice have more, mostly with more fast "
                      "power than a DS. m7, the one high-knockout mouse without IEDs, has as many (%s%%), but %d of its %d carry "
                      "less." % (sig2(m7r.pct), m7r.lo, m7r.und),
                   kicker="ADDED · EVERY MOUSE IN ROOT CANAL (STRICT WORKFLOW)", number=10)
    F.put(fig, 0.5, y - 0.02, "From " + STRICT_NAME + ", the target's 5,100 events (CTL & PTEN Baseline v2, Optimized parameters, "
          "v4). Each mouse on its own: largest amplitude across, fast power up, the DS border (blue) and the IED border (red) "
          "as applied; under each, how many of its events are undecided (inside both borders, or outside both).", 5.2, size=6.4,
          color=F.SOFT)
    y += 0.5
    W, H = fig.get_size_inches()
    for i, l in enumerate(ORDER):
        col, row = i % 4, i // 4
        x0, y0 = 0.62 + col * 1.3, y + row * 1.62
        a = F.axes_in(fig, x0, y0 + 0.18, 1.12, 0.95)
        e = s[s.lab == l]
        for cls, col_, sz, al in (("ds", F.C_DS, 1.6, 0.45), ("neither", "#b48fd0", 2.4, 0.8), ("both", F.C_PDS, 3.0, 0.95),
                                  ("pspike", F.C_IED, 3.0, 0.95)):
            q = e[e.cls == cls]
            a.scatter(np.log10(q.amp), q.hf, s=sz, color=col_, alpha=al, lw=0, rasterized=True, zorder=3)
        a.plot(ds_poly[:, 0], ds_poly[:, 1], color=F.C_DS, lw=0.8, zorder=2)
        a.plot(ied_poly[:, 0], ied_poly[:, 1], color=F.C_IED, lw=0.8, zorder=2)
        a.set_xlim(1.6, 3.8)
        a.set_ylim(-15, 52)
        a.set_xticks([2, 3])
        a.set_xticklabels(["100", "1000"], fontsize=5.0)
        a.set_yticks([0, 20, 40])
        a.set_yticklabels(["0", "20", "40"] if col == 0 else ["", "", ""], fontsize=5.2)
        if col == 0:
            a.set_ylabel("Fast power (dB)", fontsize=5.6)
        r = T[T.mouse == l].iloc[0]
        head_col = {"CTL": F.INK, "IED-": "#c4579a", "IED+": F.C_POS}[F.subgroup(l)]
        fig.text((x0) / W, 1 - (y0 + 0.14) / H, "%s  %s, %.0f%% KO" % (l, F.GROUP_WORD[F.subgroup(l)].replace("\n", " "), F.ko(l)),
                 fontsize=6.0, weight="bold", color=head_col, va="bottom")
        fig.text((x0) / W, 1 - (y0 + 1.33) / H, "%d undecided of %d · %s%%" % (r.und, r.n, sig2(r.pct)), fontsize=5.8,
                 color=F.INK, va="top")
        if l == "m7":
            fig.add_artist(patches.FancyBboxPatch(((x0 - 0.08) / W, 1 - (y0 + 1.5) / H), 1.26 / W, 1.6 / H,
                                                  boxstyle="round,pad=0,rounding_size=0.008", transform=fig.transFigure,
                                                  facecolor="none", edgecolor=F.C_POS, lw=1.3, zorder=10))
    fig.text((0.62 + 2.6) / W, 1 - (y + 6.47) / H, "Largest amplitude (µV, log scale), every panel", fontsize=6.0, color=F.INK,
             ha="center", va="top")
    hs = [Line2D([], [], ls="", marker="o", ms=4, mfc=F.C_DS, mec="none", label="DS"),
          Line2D([], [], ls="", marker="o", ms=4, mfc=F.C_PDS, mec="none", label="inside both borders"),
          Line2D([], [], ls="", marker="o", ms=4, mfc="#b48fd0", mec="none", label="outside both"),
          Line2D([], [], ls="", marker="o", ms=4, mfc=F.C_IED, mec="none", label="IED class"),
          Line2D([], [], color=F.C_DS, lw=0.9, label="DS border (%d%% grace)" % round(100 * gd)),
          Line2D([], [], color=F.C_IED, lw=0.9, label="IED border (%d%% grace)" % round(100 * gi))]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.55 / W, 1 - (y + 6.72) / H), ncol=3, frameon=False, fontsize=6.0)
    m7 = T[T.mouse == "m7"].iloc[0]
    ratios = [shp[l]["hw_ratio"] for l in ORDER]
    ip_hf = [shp[l]["und_hf"] for l in IEDP]
    jtext(fig, [
        ("What 'undecided' is", "The Strict Root Canal workflow sorts every candidate event by two borders in the space of "
                                "largest amplitude, half-width and fast power: inside the DS border only (DS), inside the IED "
                                "border only (IED class), inside both, or outside both. Undecided = inside both + outside both, "
                                "exactly as Jarvis counts it. The panels show amplitude and fast power only (each outline is "
                                "its border seen from that side), so an undecided event can sit inside a drawn outline and "
                                "still be outside the border in half-width. m6 (left out, the lab's call) and m51 (5 events) "
                                "are not shown."),
        ("The exception (framed)", "m7 has 24%% knockout and no IEDs. %d of its %d events (%s%%) are undecided, as many as an "
                                   "IED+ mouse, but %d of them carry less fast power than a typical DS (%.0f dB, the DS "
                                   "border's center). Their median is %.1f dB, close to m7's own DS (%.1f dB): all of m7's "
                                   "events sit low. The IED+ mice's undecided events sit at %.0f to %.0f dB, toward the IED "
                                   "border."
                                   % (m7.und, m7.n, sig2(m7.pct), m7.lo, cen_hf, m7.und_hf, shp["m7"]["ds_hf"], min(ip_hf), max(ip_hf))),
        ("Reading", "Undecided is not one thing. %d of the %d undecided events are outside both borders, and %.0f%% are wider "
                    "than the mouse's typical DS (%.0f to %.0f%% in the controls, %.0f%% in m7, %.0f to %.0f%% in the IED+ "
                    "mice; median half-width %.1f to %.1f times the DS). In IED+ mice they also carry high fast power, toward "
                    "the IED border; in m7 they carry as little as its own DS, and in the low-knockout mice less than theirs."
                    % (n_und - n_both, n_und, shp["_wide_pct"], min(shp[l]["wide_pct"] for l in CTL),
                       max(shp[l]["wide_pct"] for l in CTL), shp["m7"]["wide_pct"], min(shp[l]["wide_pct"] for l in IEDP),
                       max(shp[l]["wide_pct"] for l in IEDP), min(ratios), max(ratios))),
    ])
    F.save(fig, OUT, "10_every_mouse")


def table():
    T, cen_hf = strict_table()
    rc = D.rc()
    s = rc[rc.wf == "strict"]
    m7r = T[T.mouse == "m7"].iloc[0]
    fig, y = jpage(10, "Pooled, undecided events are twice as common in IED+ mice as in controls and most carry more fast power "
                       "than a DS; in the low-knockout mice and m7 most carry less. m7 matches the IED+ mice in how many it has, and "
                       "the low-knockout mice in where they fall.", kicker="ADDED · SUMMARY TABLE AND AGGREGATE", number=11)
    W, H = fig.get_size_inches()
    shp, _n_und, _n_both = strict_shape()
    y += 0.15
    F.letter(fig, 0.4, y + 0.08, "a", "Every mouse in one table: m7 (highlighted) is the high-knockout mouse with an IED+ share of "
             "undecided events, %d of its %d with less fast power than a DS" % (m7r.lo, m7r.und))
    cols = [("Mouse", 0.55, "left"), ("Group", 1.05, "left"), ("KO %", 1.95, "right"), ("Events", 2.45, "right"), ("DS", 2.85, "right"),
            ("IED class", 3.4, "right"), ("Undecided", 4.0, "right"), ("Undecided %", 4.6, "right"),
            ("Undecided above DS fast power", 5.75, "right")]
    yt = y + 0.32
    for t_, x_, ha in cols:
        F.put(fig, x_, yt, t_, 0.62 if t_ != "Undecided above DS fast power" else 0.9, size=5.8, weight="bold", color=F.SOFT, ha=ha)
    yt += 0.34
    rh = 0.165
    groups_rows = []
    for gname, labs in (("Control", [l for l in ORDER if F.subgroup(l) == "CTL"]), ("IED−", ["m8", "m33", "m1", "m7"]),
                        ("IED+", ["m13", "m28", "m3", "m5", "m34"])):
        for l in labs:
            r = T[T.mouse == l].iloc[0]
            if l == "m7":
                fig.add_artist(patches.Rectangle((0.48 / W, 1 - (yt + rh * 0.5) / H), 5.35 / W, rh / H, transform=fig.transFigure,
                                                 facecolor="#f6e3ec", edgecolor=F.C_POS, lw=0.8, zorder=0))
            vals = [l, F.GROUP_WORD[r.group].replace("\n", " "), "%.1f" % r.ko, "%d" % r.n, "%d" % r.ds, "%d" % r.ied, "%d" % r.und,
                    "%s%%" % sig2(r.pct), "%d of %d" % (r.hi, r.und)]
            for (t_, x_, ha), v in zip(cols, vals):
                fig.text(x_ / W, 1 - yt / H, v, fontsize=6.0, ha=ha, va="center", color=F.INK, weight="bold" if l == "m7" else "normal")
            yt += rh
        groups_rows.append((gname, labs))
        fig.add_artist(Line2D([0.5 / W, 5.8 / W], [1 - (yt - rh * 0.45) / H] * 2, color=F.GRID, lw=0.6))
    # pooled rows
    yt += 0.05
    for gname, labs in (("All controls", [l for l in ORDER if F.subgroup(l) == "CTL"]), ("IED−, low KO", ["m8", "m33", "m1"]),
                        ("m7 alone", ["m7"]), ("All IED+", ["m13", "m28", "m3", "m5", "m34"])):
        sub = T[T.mouse.isin(labs)]
        n, und, hi = int(sub.n.sum()), int(sub.und.sum()), int(sub.hi.sum())
        vals = [gname + ("" if len(labs) == 1 else " (pooled)"), "", "", "%d" % n, "%d" % int(sub.ds.sum()), "%d" % int(sub.ied.sum()), "%d" % und,
                "%s%%" % sig2(100.0 * und / n), "%d of %d" % (hi, und)]
        for (t_, x_, ha), v in zip(cols, vals):
            fig.text(x_ / W, 1 - yt / H, v, fontsize=6.0, ha=ha, va="center", color=F.INK, weight="bold", style="italic")
        yt += rh
    # b: aggregate clouds
    yb = yt + 0.25
    F.letter(fig, 0.4, yb + 0.08, "b", "Aggregated, the IED+ undecided events fill the gap toward the IED border; the low-knockout "
             "mice's and m7's stay low in fast power, at or below their own DS")
    ds_poly, _gd = strict_outline("ds")
    ied_poly, _gi = strict_outline("pspike")
    for k, (name, labs) in enumerate((("Controls (7)", [l for l in ORDER if F.subgroup(l) == "CTL"]), ("IED−, low KO (3)", ["m8", "m33", "m1"]),
                                      ("m7 (24% KO, no IEDs)", ["m7"]), ("IED+ (5)", ["m13", "m28", "m3", "m5", "m34"]))):
        a = F.axes_in(fig, 0.75 + k * 1.22, yb + 0.45, 1.05, 0.95)
        e = s[s.lab.isin(labs)]
        for cls, col_, sz, al in (("ds", F.C_DS, 1.2, 0.3), ("neither", "#b48fd0", 2.0, 0.75), ("both", F.C_PDS, 2.6, 0.95),
                                  ("pspike", F.C_IED, 2.6, 0.95)):
            q = e[e.cls == cls]
            a.scatter(np.log10(q.amp), q.hf, s=sz, color=col_, alpha=al, lw=0, rasterized=True)
        a.plot(ds_poly[:, 0], ds_poly[:, 1], color=F.C_DS, lw=0.8)
        a.plot(ied_poly[:, 0], ied_poly[:, 1], color=F.C_IED, lw=0.8)
        a.set_xlim(1.6, 3.8)
        a.set_ylim(-15, 52)
        a.set_xticks([2, 3])
        a.set_xticklabels(["100", "1000"], fontsize=5.4)
        a.set_yticks([0, 20, 40])
        if k:
            a.set_yticklabels(["", "", ""])
        else:
            a.set_ylabel("Fast power (dB)", fontsize=5.8)
        a.set_xlabel("Amplitude (µV)", fontsize=5.6)
        a.set_title(name, fontsize=6.0, loc="left", color=F.C_POS if name.startswith("m7") else F.INK,
                    weight="bold" if name.startswith("m7") else "normal")
    # c: per-mouse numbers by group
    yc = yb + 1.85
    pct = {l: float(T[T.mouse == l].pct.iloc[0]) for l in ORDER}
    hi_share = {l: 100.0 * float(T[T.mouse == l].hi.iloc[0]) / max(float(T[T.mouse == l].und.iloc[0]), 1) for l in ORDER}
    Tp, Th = F.contrast_table(pct), F.contrast_table(hi_share)
    F.letter(fig, 0.4, yc + 0.08, "c", "Per mouse: IED+ mice have more undecided events than controls (P %s) and more of them above "
             "DS fast power (P %s); the IED− mice's, m7's included, lie mostly below (P %s)"
             % (F.pnum(pp(Tp, "IEDpos_vs_CTL")), F.pnum(pp(Th, "IEDpos_vs_CTL")), F.pnum(pp(Th, "IEDneg_vs_CTL"))))
    ied_panel(fig, 0.85, yc + 0.6, 1.9, 1.0, pct, "Undecided\n(% of events)", names=("m7",))
    a_hi, _T = ied_panel(fig, 3.45, yc + 0.6, 1.9, 1.0, hi_share, "Undecided with more\nfast power than a DS (%)", names=("m7",))
    a_hi.set_yticks([0, 25, 50, 75, 100])
    pooled = {g: T[T.group == g] for g in G3}
    jtext(fig, [
        ("How it was made", "Counts from the Strict Root Canal workflow (" + STRICT_NAME + "), applied to the 5,100 events of "
                            "the target set. Undecided = inside both borders + outside both. 'More fast power than a DS' = "
                            "fast power above the DS border's center (%.0f dB). Pooled rows add the events of the mice in each "
                            "group; the panels in c take one number per mouse." % cen_hf),
        ("What it shows", "Pooled, undecided events are %s%% of control events, %s%% in the low-knockout IED− mice, %s%% in m7 "
                          "and %s%% in IED+ mice. Above DS fast power: %s%% of the IED+ undecided events, %s%% of the "
                          "controls', %s%% of the low-knockout mice's and %d of m7's %d."
                          % (sig2(100.0 * pooled["CTL"].und.sum() / pooled["CTL"].n.sum()),
                             sig2(100.0 * T[T.mouse.isin(["m8", "m33", "m1"])].und.sum() / T[T.mouse.isin(["m8", "m33", "m1"])].n.sum()),
                             sig2(float(T[T.mouse == "m7"].pct.iloc[0])),
                             sig2(100.0 * pooled["IED+"].und.sum() / pooled["IED+"].n.sum()),
                             sig2(100.0 * pooled["IED+"].hi.sum() / max(pooled["IED+"].und.sum(), 1)),
                             sig2(100.0 * pooled["CTL"].hi.sum() / max(pooled["CTL"].und.sum(), 1)),
                             sig2(100.0 * T[T.mouse.isin(["m8", "m33", "m1"])].hi.sum() / max(T[T.mouse.isin(["m8", "m33", "m1"])].und.sum(), 1)),
                             m7r.hi, m7r.und)),
        ("Reading", "The undecided share alone would put m7 with the IED+ mice; where its undecided events fall puts it with the "
                    "low-knockout mice, the same split as fast power (Question 6). m7's undecided events carry about as much "
                    "fast power as its own DS (%.1f against %.1f dB): its whole cloud sits low, so they are wide DS-like events, "
                    "not near-IED ones." % (shp["m7"]["und_hf"], shp["m7"]["ds_hf"])),
    ])
    F.save(fig, OUT, "11_table_and_aggregate")


# ============================================================================ questions 4, 5, 7, 8 (2 kHz reads)
KEYS4 = [("upper", "MML"), ("upper", "OML"), ("lower", "MML"), ("lower", "OML")]
CATS = [("WT", "WT DS", F.C_CTL), ("DS", "DS", F.C_DS), ("TZ", "BT", F.C_PDS), ("IED", "IED", F.C_IED)]


def fq(lab, band, part, key, idx=None):
    m = FQ()["mice"].get(lab)
    if m is None:
        return np.nan
    v = m["bands"][band][part].get(key, np.nan)
    if idx is not None:
        return v[idx] if isinstance(v, tuple) else np.nan
    return v


def ref_reads(band):
    return float(np.mean([FQ()["mice"][l]["bands"][band]["deep"]["DS"] for l in CTL if l in FQ()["mice"]]))


def fast_metrics(db, lo=100, hi=500, glo=250):
    """From a mean event-over-baseline spectrum (dB): the centroid of the added power (power ratio above 1) between lo and
    hi, i.e. where the extra fast power sits; and the mean gain (dB) from glo to hi."""
    fr = FQ()["mice"]["m2"]["freqs"]
    m = (fr >= lo) & (fr <= hi)
    ex = np.clip(10 ** (np.asarray(db, float)[m] / 10.0) - 1, 0, None)
    cen = float((ex * fr[m]).sum() / ex.sum()) if ex.sum() > 0 else np.nan
    g = (fr >= glo) & (fr <= hi)
    return cen, float(np.mean(np.asarray(db, float)[g]))


def fast_of(lab, band, cls, key, sig="csd", which=0, lo=100, hi=500, glo=250):
    spec = FQ()["mice"].get(lab, {}).get("bands", {}).get(band, {}).get("fast_spec", {}).get((cls,) + key + (sig,))
    if spec is None:
        return np.nan
    return fast_metrics(spec, lo, hi, glo)[which]


def whole_of(lab, band, cls, key, sig="csd", which=0):
    v = FQ()["mice"].get(lab, {}).get("bands", {}).get(band, {}).get("whole", {}).get((cls,) + key + (sig,))
    return v[which] if v is not None else np.nan


def p_grid(fig, x, y, w, row_labels, col_labels, Pm, Em, title, cell_h=0.16, label_w=1.75):
    """A grid of generous P values: rows = results, columns = filter bands. Color = direction (red up, blue down), darker =
    smaller P; bold = P < 0.05; a dash where the band cannot carry the measure."""
    nr, nc = len(row_labels), len(col_labels)
    cw = (w - label_w) / nc
    a = F.axes_in(fig, x + label_w, y, cw * nc, cell_h * nr)
    a.set_xlim(0, nc)
    a.set_ylim(nr, 0)
    a.axis("off")
    import matplotlib
    cmap = matplotlib.colormaps["RdBu_r"]
    for i in range(nr):
        for j in range(nc):
            p, e = Pm[i][j], Em[i][j]
            if not np.isfinite(p):
                a.add_patch(patches.Rectangle((j, i), 1, 1, facecolor="#f4f5f7", edgecolor="white", lw=0.8))
                a.text(j + 0.5, i + 0.5, "—", ha="center", va="center", fontsize=5.6, color=F.FAINT)
                continue
            strength = min(-np.log10(max(p, 1e-6)), 4.0) / 4.0
            val = 0.5 + 0.5 * strength * (1 if e > 0 else -1)
            a.add_patch(patches.Rectangle((j, i), 1, 1, facecolor=cmap(val), edgecolor="white", lw=0.8))
            a.text(j + 0.5, i + 0.5, F.pnum(p), ha="center", va="center", fontsize=5.3,
                   color="white" if strength > 0.55 else F.INK, weight="bold" if p < 0.05 else "normal")
    W, H = fig.get_size_inches()
    for i, lab_ in enumerate(row_labels):
        fig.text((x + label_w - 0.06) / W, 1 - (y + (i + 0.5) * cell_h) / H, lab_, fontsize=5.7, ha="right", va="center", color=F.INK)
    for j, lab_ in enumerate(col_labels):
        fig.text((x + label_w + (j + 0.5) * cw) / W, 1 - (y - 0.05) / H, lab_, fontsize=5.7, ha="center", va="bottom", color=F.INK,
                 weight="bold")
    if title:
        F.put(fig, x, y - 0.62, title, w, size=6.0, color=F.SOFT)
    return a


def paired_p(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return np.nan
    ps = [st.ttest_rel(a[ok], b[ok]).pvalue]
    try:
        ps.append(st.wilcoxon(a[ok], b[ok]).pvalue)
    except ValueError:
        pass
    return float(np.nanmin(ps))


def class_panel(fig, x, y, w, h, get, ylabel, title, wt=True):
    """WT DS (control mice) | DS | BT | IED (the five IED+ mice, lines join one mouse). get(lab, cls) -> value.
    Brackets: BT and IED against WT DS (unpaired), BT and IED against the same mice's DS (paired)."""
    a = F.axes_in(fig, x, y, w, h)
    cats = CATS if wt else CATS[1:]
    xs = {c: i for i, (c, _w, _col) in enumerate(cats)}
    vals = {c: {} for c, _w, _col in cats}
    if wt:
        for l in CTL:
            vals["WT"][l] = get(l, "DS")
    for l in IEDP:
        for c in ("DS", "TZ", "IED"):
            vals[c][l] = get(l, c)
    allv = []
    rng = np.random.RandomState(4)
    for c, word, col in cats:
        vs = np.array([v for v in vals[c].values() if np.isfinite(v)])
        if vs.size:
            a.plot([xs[c] - 0.25, xs[c] + 0.25], [np.median(vs)] * 2, color=F.INK, lw=1.1, zorder=3)
        for l, v in vals[c].items():
            if np.isfinite(v):
                a.scatter([xs[c] + rng.uniform(-0.08, 0.08)], [v], s=14, color=col, edgecolor="white", lw=0.4, zorder=4)
                allv.append(v)
    for l in IEDP:
        row = [vals[c].get(l, np.nan) for c in ("DS", "TZ", "IED")]
        a.plot([xs["DS"], xs["TZ"], xs["IED"]], row, color=F.C_POS, lw=0.5, alpha=0.5, zorder=2)
    F.note_y(a, allv)
    pairs = []
    if wt:
        for c in ("TZ", "IED"):
            A_ = [v for v in vals["WT"].values() if np.isfinite(v)]
            B_ = [v for v in vals[c].values() if np.isfinite(v)]
            if len(A_) >= 3 and len(B_) >= 3:
                pairs.append((xs["WT"], xs[c], S.two(A_, B_)["p"]))
    for c in ("TZ", "IED"):
        pairs.append((xs["DS"], xs[c], paired_p([vals[c][l] for l in IEDP], [vals["DS"][l] for l in IEDP])))
    F.defer_brackets(a, pairs)
    a.set_xticks(range(len(cats)))
    a.set_xticklabels([wd for _c, wd, _col in cats], fontsize=5.6)
    for tl, (_c, _w, col) in zip(a.get_xticklabels(), cats):
        tl.set_color(col if col != F.C_CTL else F.INK)
    a.tick_params(axis="x", length=0)
    a.set_xlim(-0.5, len(cats) - 0.5)
    a.set_ylabel(ylabel, fontsize=5.8)
    a.set_title(title, fontsize=6.0, loc="left")
    return a, vals, pairs


def q7():
    rc = D.rc()
    h = rc[rc.wf == "halo"]
    refn = ref_reads("notch")
    med = lambda l, k, col: float(h[(h.lab == l) & (h.kind == k)][col].median())  # noqa: E731
    deep_rel = {(l, k): float(fq(l, "notch", "deep", k)) / refn for l in LABS for k in ("DS", "TZ", "IED")}
    hf_bt = [med(l, "TZ", "hf") for l in IEDP]
    hf_wt = [med(l, "DS", "hf") for l in CTL]
    amp_bt = [med(l, "TZ", "amp") for l in IEDP]
    amp_wt = [med(l, "DS", "amp") for l in CTL]

    def own(get, c1, c0="DS"):
        return paired_p([get(l, c1) for l in IEDP], [get(l, c0) for l in IEDP])
    sink_of = {key: (lambda l, k, key=key: fq(l, "notch", "sink", (k,) + key) / refn) for key in KEYS4}
    fig, y = jpage(7, "Sorted along the continuum, the answer changes: in IED+ mice BTs carry more MML current than the same mice's "
                      "normal DS (red events lean the same way) and both carry far more fast power; against a control DS only "
                      "their fast power is higher.")
    y += 0.27
    F.letter(fig, 0.4, y + 0.08, "a", "Within each IED+ mouse, fast power climbs from DS to BT to IED; amplitude and current rise "
             "from DS to BT, then level off", width=2.6)
    feats = [("hf", "Fast power (dB)", lambda l, k: med(l, k, "hf")), ("amp", "Largest amplitude (µV)", lambda l, k: med(l, k, "amp")),
             ("deep", "Deepest sink\n(control DS = 1)", lambda l, k: deep_rel.get((l, k), np.nan))]
    for j, (key, word, get) in enumerate(feats):
        class_panel(fig, 0.95, y + 0.6 + j * 1.15, 1.75, 0.82, get, word, "", wt=True)
    F.letter(fig, 3.05, y + 0.08, "b", "As in question 3: BTs carry more MML current than the same mice's DS in both blades, but "
             "not more than a WT DS; the OML hardly differs", width=2.5)
    for i, key in enumerate(KEYS4):
        col, row = i % 2, i // 2
        class_panel(fig, 3.45 + col * 1.1, y + 0.7 + row * 1.7, 0.9, 1.1, sink_of[key], "Sink\n(control DS = 1)" if col == 0 else "",
                    "%s %s" % (key[0].capitalize(), key[1]))
    yc = y + 4.1
    F.letter(fig, 0.4, yc + 0.08, "c", "As in question 4: the fast power that BTs add sits higher in frequency than on the same "
             "mice's DS and on a control DS, in three of the four layers")
    for i, key in enumerate(KEYS4):
        class_panel(fig, 0.95 + i * 1.22, yc + 0.62, 0.95, 1.05, lambda l, k, key=key: fast_of(l, "notch", k, key, "csd", 0),
                    "Center of the added\nfast power (Hz)" if i == 0 else "", "%s %s" % (key[0].capitalize(), key[1]))
    yd = yc + 2.1
    F.letter(fig, 0.4, yd + 0.08, "d", "And they add more of it: the 250–500 Hz gain of BTs is above the same mice's DS and a "
             "control DS in every layer")
    for i, key in enumerate(KEYS4):
        class_panel(fig, 0.95 + i * 1.22, yd + 0.62, 0.95, 1.05, lambda l, k, key=key: fast_of(l, "notch", k, key, "csd", 1),
                    "Fast gain, 250–500 Hz\n(dB over before)" if i == 0 else "", "%s %s" % (key[0].capitalize(), key[1]))
    g_hf, g_amp, g_deep = (f[2] for f in feats)
    jtext(fig, [
        ("How it was measured", "Classes are the Root Canal Halo workflow's: DS (blue), borderline transients (BT, purple) and the "
                                "IED class (red). BTs and red events exist almost only in the five IED+ mice, so the comparison "
                                "is within those mice (lines join one mouse; paired tests) and against the control mice's DS "
                                "(WT DS; unpaired). Fast power and amplitude are the Root Canal numbers (panel a recaps the DS "
                                "menu's Story 6); sinks and frequencies come from the 2 kHz reads, every mouse on one scale "
                                "(control DS average deepest sink = 1), MML and OML as in question 3, fast power as in question 4."),
        ("What it shows", "BTs against the same mice's DS: fast power %s, amplitude %s, deepest sink %s, MML sink %s (upper) and "
                          "%s (lower). Red events against the same mice's DS: fast power %s, amplitude %s, deepest sink %s, MML "
                          "sink %s and %s. Red events against BTs: fast power %s, deepest sink %s. Against WT DS: BT fast power "
                          "%s, amplitude %s. Medians: WT DS fast power %.0f dB, BT %.0f dB; WT DS amplitude %.0f µV, BT %.0f µV."
                          % (F.pstr(own(g_hf, "TZ")), F.pstr(own(g_amp, "TZ")), F.pstr(own(g_deep, "TZ")),
                             F.pstr(own(sink_of[KEYS4[0]], "TZ")), F.pstr(own(sink_of[KEYS4[2]], "TZ")),
                             F.pstr(own(g_hf, "IED")), F.pstr(own(g_amp, "IED")), F.pstr(own(g_deep, "IED")),
                             F.pstr(own(sink_of[KEYS4[0]], "IED")), F.pstr(own(sink_of[KEYS4[2]], "IED")),
                             F.pstr(own(g_hf, "IED", "TZ")), F.pstr(own(g_deep, "IED", "TZ")),
                             F.pstr(S.two(hf_wt, hf_bt)["p"]), F.pstr(S.two(amp_wt, amp_bt)["p"]),
                             np.median(hf_wt), np.median(hf_bt), np.median(amp_wt), np.median(amp_bt))),
        ("Reading", "Jeremy's abnormal DS look like stronger versions of the same event: in the MML they carry more current than "
                    "the mouse's own DS, and their fast power is stronger, and in most layers higher in frequency, than the "
                    "mouse's own DS or a control DS. Against a control DS only the fast power stands out."),
        ("Caveats", "Five IED+ mice; m3's IED class has 7 events. Fast power helped define the classes, so its rise across "
                    "classes is partly built in; the sinks and the oscillation frequency were not used to sort events."),
    ])
    F.save(fig, OUT, "08_q7_continuum")


def q4():
    fr = FQ()["mice"]["m2"]["freqs"]
    Twp, Tfc, Tlg = {}, {}, {}
    for key in KEYS4:
        Twp[key] = F.contrast_table({l: whole_of(l, "notch", "DS", key, "csd", 0) for l in LABS})
        Tfc[key] = F.contrast_table({l: fast_of(l, "notch", "DS", key, "csd", 0) for l in LABS})
        Tlg[key] = F.contrast_table({l: fast_of(l, "notch", "DS", key, "lfp", 1) for l in LABS})
    fig, y = jpage(4, "The dentate spike's own dominant frequency (12 to 15 Hz) does not change with knockout in the MML or OML of "
                      "either blade; the fast power riding on it moves to higher frequencies as knockout rises, most in the lower "
                      "blade's MML.")
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.55
    F.letter(fig, 0.4, y + 0.08, "a", "On a DS the added fast power falls smoothly with frequency, with no separate fast peak; IED+ "
             "mice add the most at the top")
    for i, key in enumerate(KEYS4):
        a = F.axes_in(fig, 0.85 + i * 1.22, y + 0.5, 0.98, 0.92)
        sel = (fr >= 60) & (fr <= 500)
        for g in G3:
            Sg = np.array([FQ()["mice"][l]["bands"]["notch"]["fast_spec"][("DS",) + key + ("csd",)] for l in LABS if F.subgroup(l) == g])
            m = Sg.mean(axis=0)
            se = Sg.std(axis=0, ddof=1) / np.sqrt(Sg.shape[0])
            col = F.GROUP_COLOR[g] if g != "CTL" else "#6b6b6b"
            a.fill_between(fr[sel], (m - se)[sel], (m + se)[sel], color=F.GROUP_COLOR[g], alpha=0.2, lw=0)
            a.plot(fr[sel], m[sel], color=col, lw=1.1, label=F.GROUP_WORD[g])
        a.set_xlim(60, 500)
        a.set_xticks([100, 300, 500])
        a.set_xlabel("Frequency (Hz)", fontsize=6)
        a.set_ylabel("DS power over the\nmoment before (dB)" if i == 0 else "", fontsize=6)
        a.set_title("%s %s" % (key[0].capitalize(), key[1]), fontsize=6.2, loc="left")
        if i == 3:
            a.legend(frameon=False, fontsize=5.2, loc="upper right")
    yb = y + 1.95
    F.letter(fig, 0.4, yb + 0.08, "b", "The DS waveform's own dominant frequency does not follow knockout in any layer of either blade "
             "(PTEN P %s to %s)" % (F.pnum(min(pp(Twp[k], "KO_dose_PTEN") for k in KEYS4)), F.pnum(max(pp(Twp[k], "KO_dose_PTEN") for k in KEYS4))))
    for i, key in enumerate(KEYS4):
        ko_panel(fig, 0.95 + i * 1.22, yb + 0.78, 0.95, 0.8, {l: whole_of(l, "notch", "DS", key, "csd", 0) for l in LABS},
                 "Dominant\nfrequency (Hz)" if i == 0 else "", title="%s %s" % (key[0].capitalize(), key[1]), names=False)
    yc = yb + 2.08
    lm = ("lower", "MML")
    F.letter(fig, 0.4, yc + 0.08, "c", "Where the added fast power sits moves up with knockout, most in the lower blade's MML (PTEN "
             "ρ %+.2f, P %s; all mice P %s)" % (ef(Tfc[lm], "KO_dose_PTEN"), F.pnum(pp(Tfc[lm], "KO_dose_PTEN")),
                                                   F.pnum(pp(Tfc[lm], "KO_dose_all"))))
    for i, key in enumerate(KEYS4):
        ko_panel(fig, 0.95 + i * 1.22, yc + 0.78, 0.95, 0.8, {l: fast_of(l, "notch", "DS", key, "csd", 0) for l in LABS},
                 "Center of the added\nfast power (Hz)" if i == 0 else "", title="%s %s" % (key[0].capitalize(), key[1]), names=False)
    yd = yc + 2.08
    F.letter(fig, 0.4, yd + 0.08, "d", "In the LFP the fast (250–500 Hz) gain goes two ways: lower in IED− mice, higher in IED+ "
             "mice, in every layer (as fast power did in the DS menu's Story 1)")
    for i, key in enumerate(KEYS4):
        ied_panel(fig, 0.95 + i * 1.22, yd + 0.55, 0.95, 0.8, {l: fast_of(l, "notch", "DS", key, "lfp", 1) for l in LABS},
                  "LFP fast gain (dB)" if i == 0 else "", title="%s %s" % (key[0].capitalize(), key[1]), xl=("Ctl", "IED−", "IED+"))
    jtext(fig, [
        ("How it was measured", "Every DS of every mouse read again at 2 kHz through Jarvis's X-ray reader (one pipeline for all "
                                "16 mice). MML and OML as in question 3 (steps along each blade's own DS axis), each read as "
                                "CSD and as LFP. Dominant frequency: the peak of the event's own power spectrum over ±50 ms "
                                "(5–300 Hz). Fast power: the event's power (±25 ms) over the same contacts' power 100 to "
                                "50 ms before, per frequency; its center is the power-weighted frequency of what the DS adds "
                                "between 100 and 500 Hz, its gain the mean dB from 250 to 500 Hz."),
        ("What it shows", "Dominant frequency: no layer follows knockout (PTEN P %s to %s). Center of the added fast power "
                          "against knockout, CSD: upper MML ρ %+.2f (all mice P %s), upper OML %+.2f (P %s), lower MML "
                          "%+.2f (P %s; PTEN only P %s), lower OML %+.2f (P %s). LFP fast gain: IED− against control "
                          "P %s to %s (lower), IED+ against control P %s to %s (higher)."
                          % (F.pnum(min(pp(Twp[k], "KO_dose_PTEN") for k in KEYS4)), F.pnum(max(pp(Twp[k], "KO_dose_PTEN") for k in KEYS4)),
                             ef(Tfc[KEYS4[0]], "KO_dose_all"), F.pnum(pp(Tfc[KEYS4[0]], "KO_dose_all")),
                             ef(Tfc[KEYS4[1]], "KO_dose_all"), F.pnum(pp(Tfc[KEYS4[1]], "KO_dose_all")),
                             ef(Tfc[KEYS4[2]], "KO_dose_all"), F.pnum(pp(Tfc[KEYS4[2]], "KO_dose_all")), F.pnum(pp(Tfc[KEYS4[2]], "KO_dose_PTEN")),
                             ef(Tfc[KEYS4[3]], "KO_dose_all"), F.pnum(pp(Tfc[KEYS4[3]], "KO_dose_all")),
                             F.pnum(min(pp(Tlg[k], "IEDneg_vs_CTL") for k in KEYS4)), F.pnum(max(pp(Tlg[k], "IEDneg_vs_CTL") for k in KEYS4)),
                             F.pnum(min(pp(Tlg[k], "IEDpos_vs_CTL") for k in KEYS4)), F.pnum(max(pp(Tlg[k], "IEDpos_vs_CTL") for k in KEYS4)))),
        ("Reading", "No layer of either blade has a fast oscillation of its own at a DS. What knockout changes is the fast "
                    "content the DS carries: shifted upward in frequency with dose, and, in the field, lost below the IED "
                    "threshold and gained above it."),
        ("Caveats", "The fast-power window is 50 ms and the whole-event window 100 ms, so frequencies are resolved to about "
                    "20 and 10 Hz; the 12 to 15 Hz dominant frequency describes the shape of one DS wave, not a sustained "
                    "rhythm. 'All mice' places the controls at 0 knockout."),
    ])
    F.save(fig, OUT, "05_q4_dominant_frequency")


BAND_SETS = [("5–100\n(main)", "v6", "5-100"), ("notch\nonly", "b_none", "notch"), ("1–100", "b_1_100", "1-100"),
             ("1–300", "b_1_300", "1-300"), ("5–300", "b_5_300", "5-300"), ("5–50", "b_5_50", "5-50"), ("10–40", "b_10_40", "10-40")]


def fast_range(band):
    if band == "notch":
        return 100, 500, 250
    if band in ("1-300", "5-300"):
        return 100, 300, 200
    return None


def q5():
    rows, Pm, Em = [], [], []

    def add(label, fn, cid):
        rows.append(label)
        pr, er = [], []
        for _w, es, band in BAND_SETS:
            vals = fn(es, band)
            if vals is None or len([v for v in vals.values() if np.isfinite(v)]) < 6:
                pr.append(np.nan)
                er.append(np.nan)
                continue
            T = F.contrast_table({l: v for l, v in vals.items() if np.isfinite(v)})
            pr.append(pp(T, cid))
            er.append(ef(T, cid))
        Pm.append(pr)
        Em.append(er)
    for blade in ("upper", "lower"):
        add("%s MML sink, IED− vs control" % blade.capitalize(), lambda es, band, blade=blade: layer_vals(es, blade, "MML"), "IEDneg_vs_CTL")
    for blade, layer in KEYS4:
        add("%s %s sink vs %% KO (PTEN)" % (blade.capitalize(), layer), lambda es, band, b=blade, ly=layer: layer_vals(es, b, ly), "KO_dose_PTEN")
    for key in KEYS4:
        add("%s %s dominant frequency vs %% KO (PTEN)" % (key[0].capitalize(), key[1]),
            lambda es, band, key=key: {l: whole_of(l, band, "DS", key, "csd", 0) for l in LABS}, "KO_dose_PTEN")
    for key in KEYS4:
        def fn(es, band, key=key):
            r = fast_range(band)
            if r is None:
                return None
            return {l: fast_of(l, band, "DS", key, "csd", 0, r[0], r[1], r[2]) for l in LABS}
        add("%s %s fast-power center vs %% KO (all)" % (key[0].capitalize(), key[1]), fn, "KO_dose_all")
    sig_main = [Pm[i][0] < 0.05 for i in range(len(rows))]
    keep_q3 = all((Pm[i][j] < 0.05) == sig_main[i] for i in range(6) for j in range(len(BAND_SETS)) if np.isfinite(Pm[i][j]))
    fig, y = jpage(5, "Opening the filters changes neither question 3 nor question 4's dominant frequency on any band; the fast "
                      "power's upward shift with knockout is strongest with no filter, and with a 300 Hz ceiling only the lower "
                      "MML keeps it.")
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.55
    F.letter(fig, 0.4, y + 0.08, "a", "Every result of questions 3 and 4 on every filter band: the sink results never change; the "
             "fast-power shift needs the band above 300 Hz to show in every layer")
    p_grid(fig, 0.45, y + 0.95, 5.25, rows, [w for w, _es, _b in BAND_SETS], Pm, Em,
           "Generous P per result (row) and band (column); red = higher, blue = lower; bold = P < 0.05; — = the band cannot "
           "carry it.", cell_h=0.19, label_w=2.2)
    yb = y + 0.95 + 0.19 * len(rows) + 0.4
    F.letter(fig, 0.4, yb + 0.08, "b", "Key panels: the MML deficit of IED− mice is the same with no filter at all; the lower MML's "
             "fast-power shift weakens when the band stops at 300 Hz")
    ied_panel(fig, 0.95, yb + 0.62, 0.85, 0.85, layer_vals("v6", "upper", "MML"), "Upper MML sink\n(control = 1)", title="5–100 Hz",
              xl=("Ctl", "IED−", "IED+"))
    ied_panel(fig, 2.05, yb + 0.62, 0.85, 0.85, layer_vals("b_none", "upper", "MML"), "", title="notch only", xl=("Ctl", "IED−", "IED+"))
    ko_panel(fig, 3.55, yb + 0.75, 0.85, 0.72, {l: fast_of(l, "notch", "DS", ("lower", "MML"), "csd", 0) for l in LABS},
             "Fast-power\ncenter (Hz)", title="No filter, 100–500 Hz", names=False)
    ko_panel(fig, 4.7, yb + 0.75, 0.85, 0.72, {l: fast_of(l, "1-300", "DS", ("lower", "MML"), "csd", 0, 100, 300, 200) for l in LABS},
             "", title="1–300 Hz band", names=False)
    jtext(fig, [
        ("How it was measured", "Question 3 (sinks) on the DS battery's seven filter sets: the same Halo events and labels, each "
                                "set filtered from the continuous recording (5–100 Hz is the main one; 'notch only' has no "
                                "band-pass, just the 60 Hz notch). Question 4 (frequencies) on the 2 kHz reads with each band "
                                "applied to the ±100 ms windows; the fast-power center needs a band that reaches past "
                                "100 Hz (100–500 Hz with no filter, 100–300 Hz where the band stops at 300)."),
        ("What it shows", "Question 3: the IED− MML deficit is significant on %s and no layer sink follows %% knockout on any "
                          "band. Question 4: the dominant frequency follows knockout on no band. The fast-power center rises with "
                          "knockout in all four layers with no filter (lower MML all mice P %s); on 1–300 and 5–300 Hz only "
                          "the lower MML keeps it (P %s and %s)." % ("every band" if keep_q3 else "most bands", F.pnum(Pm[12][1]),
                                                                    F.pnum(Pm[12][3]), F.pnum(Pm[12][4]))),
        ("Reading", "The sink findings do not depend on the filter. Most of the fast-power shift lives in 300–500 Hz content, "
                    "the fast-ripple range, so a band that stops at 300 Hz shows only part of it."),
        ("Caveats", "Filters with a 1 to 10 Hz low cut act mostly as a baseline removal on 200 ms windows; the sinks come from "
                    "properly filtered continuous data."),
    ])
    F.save(fig, OUT, "06_q5_open_filters")


def q8():
    rows, Pm, Em = [], [], []

    def add(label, fn):
        rows.append(label)
        pr, er = [], []
        for _w, _es, band in BAND_SETS:
            try:
                p, e = fn(band)
            except Exception:  # noqa: BLE001
                p, e = np.nan, np.nan
            pr.append(p)
            er.append(e)
        Pm.append(pr)
        Em.append(er)

    def paired(get, c1="TZ", c0="DS"):
        def f(band):
            a = np.array([get(l, band, c1) for l in IEDP], float)
            b = np.array([get(l, band, c0) for l in IEDP], float)
            return paired_p(a, b), float(np.nanmean(a - b))
        return f

    def vs_wt(get, c1="TZ"):
        def f(band):
            A_ = [get(l, band, "DS") for l in CTL]
            B_ = [get(l, band, c1) for l in IEDP]
            A_ = [v for v in A_ if np.isfinite(v)]
            B_ = [v for v in B_ if np.isfinite(v)]
            if len(A_) < 3 or len(B_) < 3:
                return np.nan, np.nan
            r = S.two(A_, B_)
            return r["p"], r["effect"]
        return f
    deep = lambda l, band, k: float(fq(l, band, "deep", k)) / ref_reads(band)  # noqa: E731
    add("Deepest sink: BT vs own DS", paired(deep))
    add("Deepest sink: IED vs own DS", paired(deep, "IED"))
    add("Deepest sink: BT vs WT DS", vs_wt(deep))
    add("Deepest sink: IED vs WT DS", vs_wt(deep, "IED"))
    for blade in ("upper", "lower"):
        sk = lambda l, band, k, blade=blade: float(fq(l, band, "sink", (k, blade, "MML"))) / ref_reads(band)  # noqa: E731
        add("%s MML sink: BT vs own DS" % blade.capitalize(), paired(sk))
        add("%s MML sink: BT vs WT DS" % blade.capitalize(), vs_wt(sk))

    def fc(l, band, k, which=0):
        r = fast_range(band)
        if r is None:
            return np.nan
        return fast_of(l, band, k, ("lower", "MML"), "csd", which, r[0], r[1], r[2])
    add("Lower MML fast-power center: BT vs own DS", paired(fc))
    add("Lower MML fast-power center: BT vs WT DS", vs_wt(fc))
    add("Lower MML fast gain: BT vs own DS", paired(lambda l, band, k: fc(l, band, k, 1)))
    add("Lower MML fast gain: BT vs WT DS", vs_wt(lambda l, band, k: fc(l, band, k, 1)))
    fig, y = jpage(8, "Opening the filter does not change the current in question 7: on every band BTs carry more than the same "
                      "mice's DS and no more than a control DS. Their fast-power lead over both needs the fully open band and fades "
                      "when the band stops at 300 Hz.")
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.55
    F.letter(fig, 0.4, y + 0.08, "a", "Every comparison of question 7 on every band: the BTs' extra current over their own DS holds "
             "on all seven; the fast-power differences need the band above 300 Hz")
    p_grid(fig, 0.45, y + 0.95, 5.25, rows, [w for w, _es, _b in BAND_SETS], Pm, Em,
           "Generous P (paired within the five IED+ mice, or against the control mice's DS); red = BT or IED higher; bold = P < 0.05; "
           "— = the band cannot carry it.", cell_h=0.19, label_w=2.2)
    yb = y + 0.95 + 0.19 * len(rows) + 0.4
    F.letter(fig, 0.4, yb + 0.08, "b", "The BTs' extra current over their own DS is the same on the main 5–100 Hz band and with no "
             "filter")
    class_panel(fig, 0.95, yb + 0.62, 1.9, 0.95, lambda l, k: float(fq(l, "5-100", "deep", k)) / ref_reads("5-100"),
                "Deepest sink\n(control DS = 1)", "5–100 Hz")
    class_panel(fig, 3.45, yb + 0.62, 1.9, 0.95, lambda l, k: float(fq(l, "notch", "deep", k)) / ref_reads("notch"), "", "notch only")
    yc = yb + 2.0
    F.letter(fig, 0.4, yc + 0.08, "c", "The BTs' fast-power lead in the lower MML is clear with no filter and fades with a 300 Hz "
             "ceiling")
    class_panel(fig, 0.95, yc + 0.62, 1.9, 0.95, lambda l, k: fc(l, "notch", k, 1), "Lower MML fast gain\n(dB over before)",
                "No filter: gain over 250–500 Hz")
    class_panel(fig, 3.45, yc + 0.62, 1.9, 0.95, lambda l, k: fc(l, "1-300", k, 1), "", "1–300 Hz band: gain over 200–300 Hz")
    jtext(fig, [
        ("How it was measured", "The comparisons of question 7 repeated on each band, from the 2 kHz reads with the band applied "
                                "to each window. Paired: within each of the five IED+ mice (paired t-test and Wilcoxon, the "
                                "smaller P). Against WT DS: the five IED+ mice's BT or IED medians against the seven control "
                                "mice's DS medians (Mann–Whitney, Welch and Student t, the smallest P). Every band has its own "
                                "common scale (its control DS average deepest sink = 1)."),
        ("What it shows", "BT against the same mice's DS, deepest sink: P %s to %s across the seven bands. BT against a control "
                          "DS: P %s to %s (never below 0.05). Fast-power center and gain with no filter: BT against own DS P %s "
                          "and %s, against a control DS P %s and %s; with a 300 Hz ceiling P %s to %s."
                          % (F.pnum(np.nanmin(Pm[0])), F.pnum(np.nanmax(Pm[0])), F.pnum(np.nanmin(Pm[2])), F.pnum(np.nanmax(Pm[2])),
                             F.pnum(Pm[8][1]), F.pnum(Pm[10][1]), F.pnum(Pm[9][1]), F.pnum(Pm[11][1]),
                             F.pnum(np.nanmin([Pm[i][3] for i in (8, 9, 10, 11)])), F.pnum(np.nanmax([Pm[i][3] for i in (8, 9, 10, 11)])))),
        ("Reading", "The extra current of BTs is not a filter effect: it holds from a 10–40 Hz band to no filter at all. "
                    "Their fast-power lead sits mostly above 300 Hz, as the dose shift of question 4 does."),
        ("Caveats", "Five IED+ mice; paired tests over five pairs cannot go below P 0.06 with Wilcoxon, so the paired t carries "
                    "most of the small P values."),
    ])
    F.save(fig, OUT, "09_q8_q7_open_filters")


# ============================================================================ cover
def short_answers():
    """One line per page for the cover, worded from each page's 'Results show' (numbers computed, not typed)."""
    T, _cen = strict_table()
    m7r = T[T.mouse == "m7"].iloc[0]
    auc_ko = roc([F.ko(l) for l in PT], [F.subgroup(l) == "IED+" for l in PT])[2]
    ctl = T[T.group == "CTL"]
    ipos = T[T.group == "IED+"]
    ratio = (ipos.und.sum() / ipos.n.sum()) / (ctl.und.sum() / ctl.n.sum())
    return {
        1: "No for the current a DS carries; yes for what it produces: for the same sink, IED+ mice's DS carry more fast power, "
           "and over all mice this output rises with knockout.",
        2: "Yes, most mice in every group make both. With knockout DS2 become rarer and the two types grow harder to tell "
           "apart; their sink timing holds.",
        3: "Not by % knockout: no MML or OML sink of either blade follows it. By group, the low-knockout (IED−) mice have weaker "
           "MML sinks in both blades; the OML is unchanged.",
        4: "Not for the DS's own dominant frequency (12 to 15 Hz), in any layer. The fast power riding on it moves higher with "
           "knockout, most in the lower blade's MML.",
        5: "No for the sinks and the dominant frequency, on every band. The fast power's upward shift is strongest with no "
           "filter; a 300 Hz ceiling leaves it only in the lower MML.",
        6: "Mostly: %% knockout alone gives an AUC of %.2f, and m7 is the one miss. The dentate spikes themselves do better: their "
           "fast power separates every mouse." % auc_ko,
        7: "Yes. In IED+ mice BTs carry more MML current than the same mice's DS (red events lean the same way) and both far "
           "more fast power; against a control DS only the fast power is higher.",
        8: "Not the current: the BTs' extra current over their own DS holds on every band. The fast-power lead needs the fully "
           "open band and fades with a 300 Hz ceiling.",
        "every": "Every mouse has undecided events, mostly wider than its DS; IED+ mice have %.1f times the control share, "
                 "mostly with more fast power than a DS. m7 has as many as an IED+ mouse (%s%%), but %d of its %d carry less."
                 % (ratio, sig2(m7r.pct), m7r.lo, m7r.und),
    }


def cover():
    SHORT = short_answers()
    fig = F.plt.figure(figsize=(8.5, 11))
    W, H = fig.get_size_inches()
    F.put(fig, 0.6, 0.6, "BARRY LAB · JEREMY MENU · %s" % DATE, 7.3, size=7, color=F.C_POS, weight="bold")
    h = F.put(fig, 0.6, 0.85, "Jeremy's questions, answered from the dentate spike data", 7.3, size=17, weight="bold")
    y = 0.85 + h + 0.1
    y += F.put(fig, 0.6, y, "Sixteen mice, one baseline recording each: 7 controls and 9 sparse PTEN knockouts (4 without IEDs, 5 "
               "with). Exploratory: one number per mouse, generous tests, no correction. Every page starts with Jeremy's question "
               "word for word and a one-sentence answer; the panels below it carry the evidence, each heading stating its finding.",
               7.3, size=8.2, color=F.SOFT) + 0.3
    cols = [(0.6, 0.3, "#"), (0.95, 2.6, "Jeremy Asked"), (3.7, 3.95, "Results show"), (7.8, 0.4, "Page")]
    for x, w, t in cols:
        F.put(fig, x, y, t, w, size=6.8, weight="bold", color=F.SOFT)
    y += 0.25
    rows = [(str(k), "“%s”" % QUESTIONS[k], SHORT.get(k, ""), str(k + 1)) for k in range(1, 9)]
    rows += [("+", "Added: every mouse in Root Canal (Strict workflow), with a summary table and an aggregate", SHORT.get("every", ""),
              "10–11")]
    for row in rows:
        hs = []
        for (x, w, _t), val in zip(cols, row):
            hs.append(F.put(fig, x, y, val, w, size=6.7, color=F.INK, style="italic" if x == 0.95 else "normal",
                            weight="bold" if x == 0.6 else "normal"))
        y += max(hs) + 0.12
        fig.add_artist(Line2D([0.6 / W, 8.2 / W], [1 - (y - 0.06) / H] * 2, color=F.GRID, lw=0.6))
    y += 0.15
    y += F.put(fig, 0.6, y, "Built on the DS story menu of 2026-11-23 (Lab Figures, DS_Story_Menu_112326); where a page recaps a "
               "menu result it says so. Depth everywhere comes from each recording's own dentate spike, never the lab's layer "
               "labels; groups are always compared on one common scale. Tables of every number are in the tables folder.",
               7.3, size=6.6, color=F.SOFT) + 0.4
    F.put(fig, 0.6, y, "Words and marks used on every page", 7.3, size=7.6, weight="bold", color=F.INK)
    y += 0.32
    F.legend_mice(fig, 0.65, y)
    y += 0.3
    glossary = [
        ("DS, BT, IED class", "The Root Canal Halo workflow's classes: dentate spikes (blue), borderline transients between the "
                              "DS and IED borders (BT, purple) and the IED class (red)."),
        ("MML and OML", "Found in each recording along each blade's own DS axis (0 at the cell-layer source, 1 at the average DS "
                        "sink): MML = 0.7 to 1.3, OML = 1.3 to 2.0. No lab layer labels."),
        ("Sink scale", "Control DS = 1: the control mice's average deepest DS sink. Every group sits on that one scale."),
        ("Fast power", "Root Canal's fast-power measure: each event's 240 to 420 Hz power, in dB. On questions 4, 5, 7 and 8 "
                       "also read from the 2 kHz reads as the power a DS adds over the moment before it, 100 to 500 Hz."),
        ("% knockout", "PTEN knockout as a share of granule cells; controls sit at 0."),
        ("P values", "Generous and uncorrected: the smallest P of the standard tests. Brackets: * < 0.05, ** < 0.01, "
                     "*** < 0.001; none, P ≥ 0.05."),
    ]
    for term, text in glossary:
        h1 = F.put(fig, 0.6, y, term, 1.4, size=6.6, weight="bold", color=F.INK)
        h2 = F.put(fig, 2.1, y, text, 5.8, size=6.6, color=F.SOFT)
        y += max(h1, h2) + 0.1
    fig.text(0.6 / W, 1 - 10.72 / H, "Jeremy menu · exploratory, P values uncorrected · %s" % DATE, fontsize=6.5, color=F.FAINT)
    fig.text(1 - 0.5 / W, 1 - 10.72 / H, "1", fontsize=6.5, color=F.FAINT, ha="right")
    F.save(fig, OUT, "01_menu")


if __name__ == "__main__":
    which = sys.argv[1:]
    for w in which:
        globals()[w]()
