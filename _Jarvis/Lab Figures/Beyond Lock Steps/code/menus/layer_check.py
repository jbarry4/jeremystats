"""Layer check (2026-11-25): every menu result that rests on a layer or a position, computed with the old MML / OML
(the average-DS sink, v ranges) and with the tight ones (each DS type's own sink, +-40 um, split at the midpoint;
tight_layers.py), side by side. The Jeremy menu itself is not touched.

  JM_LAYERS=tight python j1_battery.py; JM_LAYERS=tight python j2_freq.py; python layer_check.py
Writes Lab Figures/Layer_Check_112526 (pages, tables, code, merged PDF via miniconda's pymupdf in j_merge style)."""
import json
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
from matplotlib import patches
from matplotlib.lines import Line2D

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import figlib as F  # noqa: E402
import jpages as J  # noqa: E402
import stats_lib as S  # noqa: E402
from pages_a import textcol  # noqa: E402

DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\Layer_Check_112526"
DATE = "2026-11-25"
TLJ = json.load(open(os.path.join(HERE, "tight_layers.json"), encoding="utf-8"))
TL = TLJ["mice"]
LABS, CTL, IEDP, KEYS4 = J.LABS, J.CTL, J.IEDP, J.KEYS4
STATE = {"old": (J.B(), J.FQ()),
         "tight": (pickle.load(open(os.path.join(HERE, "jeremy_battery_tight.pkl"), "rb")),
                   pickle.load(open(os.path.join(HERE, "jeremy_freq_tight.pkl"), "rb")))}
WORD = {"old": "OLD layers (average-DS sink, v 0.7\u20131.3 / 1.3\u20132.0)",
        "tight": "TIGHT layers (DS2 sink = MML, DS1 sink = OML, \u00b140 \u00b5m)"}
C_MML, C_OML = "#fbeadb", "#f6d3b8"
PAGE = [0]


def use(which):
    J._B, J._FQ = STATE[which]


def header(asked, results):
    PAGE[0] += 1
    fig = F.plt.figure(figsize=(8.5, 11))
    F.put(fig, 0.5, 0.42, "LAYER CHECK \u00b7 OLD AGAINST TIGHT MML / OML", 7.5, size=7, color=F.C_POS, weight="bold")
    y = 0.62
    if asked:
        y += F.put(fig, 0.5, y, "Asked: \u201c%s\u201d" % asked, 7.5, size=8.4, color=F.SOFT, style="italic") + 0.06
    y += F.put(fig, 0.5, y, "Results show: " + results, 7.5, size=11.5, weight="bold")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, str(PAGE[0]), fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, "Layer check \u00b7 exploratory, P values uncorrected \u00b7 %s \u00b7 the Jeremy menu is "
             "unchanged" % DATE, fontsize=6.5, color=F.FAINT, ha="left", va="bottom")
    return fig, y + 0.15


def save(fig, name):
    os.makedirs(os.path.join(DEST, "pages"), exist_ok=True)
    F.finish(fig)
    fig.savefig(os.path.join(DEST, "pages", name + ".png"), dpi=300)
    fig.savefig(os.path.join(DEST, "pages", name + ".pdf"), dpi=600)
    F.plt.close(fig)


def row_label(fig, x, y, which, extra=""):
    F.put(fig, x, y, WORD[which] + extra, 7.4, size=6.4, weight="bold", color=F.INK if which == "tight" else F.SOFT)


# ------------------------------------------------------------------ the measures, under whichever state is in use
def lay(key):
    return lambda: J.layer_vals("v6", *key)


def dom(key):
    return lambda: {l: J.whole_of(l, "notch", "DS", key, "csd", 0) for l in LABS}


def cen(key):
    return lambda: {l: J.fast_of(l, "notch", "DS", key, "csd", 0) for l in LABS}


def lgain(key):
    return lambda: {l: J.fast_of(l, "notch", "DS", key, "lfp", 1) for l in LABS}


def c_sink(key):
    return lambda l, k: J.fq(l, "notch", "sink", (k,) + key) / J.ref_reads("notch")


def c_cen(key):
    return lambda l, k: J.fast_of(l, "notch", k, key, "csd", 0)


def c_gain(key):
    return lambda l, k: J.fast_of(l, "notch", k, key, "csd", 1)


def pos_old(blade):
    U = J.UP()
    return {l: U["recs"][("v6", l)]["c_ds1_%s" % blade] - U["recs"][("v6", l)]["c_ds2_%s" % blade] for l in LABS
            if "c_ds1_%s" % blade in U["recs"][("v6", l)] and "c_ds2_%s" % blade in U["recs"][("v6", l)]}


def pos_tight(blade):
    """DS1's sink minus DS2's, in um outward from the cell layer, where the blade separates."""
    out = {}
    for l in LABS:
        b = TL[l]["blades"][blade]
        if b["method"] == "own types":
            out[l] = (b["ds1_sink_row"] - b["ds2_sink_row"]) * b["out"] * TLJ["um_per_contact"]
    return out


def ct(vals_fn, cid):
    def f():
        T = F.contrast_table({l: v for l, v in vals_fn().items() if np.isfinite(v)})
        r = T.get(cid, {})
        return r.get("effect", np.nan), r.get("p", np.nan)
    return f


def paired(get, c1, c0="DS"):
    def f():
        a = np.array([get(l, c1) for l in IEDP], float)
        b = np.array([get(l, c0) for l in IEDP], float)
        return float(np.nanmean(a - b)), J.paired_p(a, b)
    return f


def vs_wt(get, c1):
    def f():
        A = [v for v in (get(l, "DS") for l in CTL) if np.isfinite(v)]
        B = [v for v in (get(l, c1) for l in IEDP) if np.isfinite(v)]
        if len(A) < 3 or len(B) < 3:
            return np.nan, np.nan
        r = S.two(A, B)
        return r["effect"], r["p"]
    return f


def name(key):
    return "%s %s" % (key[0].capitalize(), key[1])


CONTRAST_WORD = {"KO_dose_PTEN": "vs % KO (PTEN \u03c1)", "KO_dose_all": "vs % KO (all mice \u03c1)",
                 "IEDneg_vs_CTL": "IED\u2212 vs control", "IEDpos_vs_CTL": "IED+ vs control", "IEDpos_vs_IEDneg": "IED+ vs IED\u2212"}


def claims():
    """(question, result, what the menu says, fn_old, fn_tight); each fn returns (effect, P) under the state in use."""
    L = []
    for blade in ("upper", "lower"):
        L.append(("Q2", "DS1 minus DS2 sink position, %s blade: IED+ vs IED\u2212" % blade,
                  "DS1 sits nearer DS2 in IED+ mice" if blade == "upper" else "",
                  ct(lambda b=blade: pos_old(b), "IEDpos_vs_IEDneg"), ct(lambda b=blade: pos_tight(b), "IEDpos_vs_IEDneg")))
    for key in KEYS4:
        for cid, says in (("KO_dose_PTEN", "no layer sink follows % KO"), ("IEDneg_vs_CTL",
                          "IED\u2212 weaker" if key[1] == "MML" else "OML unchanged"), ("IEDpos_vs_CTL", "")):
            f = ct(lay(key), cid)
            L.append(("Q3", "%s sink %s" % (name(key), CONTRAST_WORD[cid]), says, f, f))
    for key in KEYS4:
        f = ct(dom(key), "KO_dose_PTEN")
        L.append(("Q4", "%s dominant frequency %s" % (name(key), CONTRAST_WORD["KO_dose_PTEN"]), "does not follow % KO", f, f))
    for key in KEYS4:
        for cid in ("KO_dose_PTEN", "KO_dose_all"):
            f = ct(cen(key), cid)
            L.append(("Q4", "%s fast-power center %s" % (name(key), CONTRAST_WORD[cid]),
                      "moves up with % KO, most in lower MML" if (key == ("lower", "MML")) else "", f, f))
    for key in KEYS4:
        for cid, says in (("IEDneg_vs_CTL", "lower in IED\u2212"), ("IEDpos_vs_CTL", "higher in IED+")):
            f = ct(lgain(key), cid)
            L.append(("Q4", "%s LFP fast gain %s" % (name(key), CONTRAST_WORD[cid]), says, f, f))
    for key in KEYS4:
        mml = key[1] == "MML"
        for lab_, f, says in (("sink: BT vs own DS", paired(c_sink(key), "TZ"), "BT larger" if mml else ""),
                              ("sink: IED class vs own DS", paired(c_sink(key), "IED"), "leans larger" if mml else ""),
                              ("sink: BT vs control DS", vs_wt(c_sink(key), "TZ"), "no larger" if mml else ""),
                              ("fast-power center: BT vs own DS", paired(c_cen(key), "TZ"), "higher in 3 of 4 layers"),
                              ("fast-power center: BT vs control DS", vs_wt(c_cen(key), "TZ"), "higher in 3 of 4 layers"),
                              ("fast gain: BT vs own DS", paired(c_gain(key), "TZ"), "higher in every layer"),
                              ("fast gain: BT vs control DS", vs_wt(c_gain(key), "TZ"), "higher in every layer")):
            L.append(("Q7", "%s %s" % (name(key), lab_), says, f, f))
    return L


def verdict(eo, po, et, pt):
    if not (np.isfinite(po) and np.isfinite(pt)):
        return "n/a"
    so, s1 = po < 0.05, pt < 0.05
    if so and s1:
        return "holds" if np.sign(eo) == np.sign(et) else "reverses"
    if not so and not s1:
        return "holds (n.s.)"
    return "lost" if so else "new"


VCOL = {"holds": "#2e7d32", "holds (n.s.)": F.SOFT, "lost": "#d35400", "new": "#1f5fa8", "reverses": "#c0392b", "n/a": F.FAINT}


def run_claims():
    rows = []
    for q, res, says, fo, ft in claims():
        use("old")
        eo, po = fo()
        use("tight")
        et, pt = ft()
        rows.append({"question": q, "result": res, "menu_says": says, "old_effect": eo, "old_p": po, "tight_effect": et,
                     "tight_p": pt, "verdict": verdict(eo, po, et, pt)})
    use("old")
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ page 1: where the tight layers sit
def page_definition(R):
    import dsdata
    recs = {r.lab: r for r in dsdata.load("v6") if r.lab in LABS}
    n_v = R.verdict.value_counts()
    said = R[R.menu_says != ""]
    sv = said.verdict.value_counts()
    fig, y = header("You know that the DS1 sink is in OML and the DS2 sink is in MML right? Can you reason why this method is "
                    "flawed if the waveform is the average of both DS1 and DS2? We need a tighter definition, and then it would "
                    "be helpful to see how the data changes with the tighter definition",
                    "With each type's own sink as the anchor, %d of the %d layer results keep their verdict, %d lose "
                    "significance, %d become significant and %d reverse; of the %d the menu states in words, %d still "
                    "agree with what it says."
                    % (int(n_v.get("holds", 0) + n_v.get("holds (n.s.)", 0)), len(R), int(n_v.get("lost", 0)),
                       int(n_v.get("new", 0)), int(n_v.get("reverses", 0)), len(said),
                       int(sv.get("holds", 0) + sv.get("holds (n.s.)", 0) + sv.get("new", 0))))
    F.letter(fig, 0.4, y + 0.08, "a", "The tight layers on every recording: each type's mean CSD at the DS peak, the new MML and "
             "OML (fills) and the old ones (gray bars at the right)", width=7.6)
    for i, l in enumerate(LABS):
        r = recs[l]
        t = np.asarray(r.labels["winner"]["types"]) if (r.winner and "winner" in r.labels) else np.zeros(r.n, int)
        allp = dsdata.fill_bad(np.nanmean(r.csd_peak, axis=0), r.bad_rows)
        rows = np.arange(allp.size)
        span = [x for b in ("upper", "lower") for nm in ("MML", "OML") for x in TL[l]["rows"][b][nm] + TL[l]["rows_old"][b][nm]]
        lo_r, hi_r = min(span) - 2, max(span) + 2
        win = (rows >= lo_r) & (rows <= hi_r)
        ref = -np.nanmin(allp[win])
        col, row = i % 8, i // 8
        ax = F.axes_in(fig, 0.55 + col * 0.95, y + 0.55 + row * 1.85, 0.72, 1.45)
        for b in ("upper", "lower"):
            for nm, colr in (("MML", C_MML), ("OML", C_OML)):
                rr = TL[l]["rows"][b][nm]
                if rr:
                    ax.axhspan(min(rr) - 0.5, max(rr) + 0.5, color=colr, lw=0, zorder=0)
                ro = TL[l]["rows_old"][b][nm]
                if ro:
                    ax.plot([1.12, 1.12] if nm == "MML" else [1.22, 1.22], [min(ro) - 0.5, max(ro) + 0.5],
                            color="#9aa1ad" if nm == "MML" else "#5a6273", lw=1.6, solid_capstyle="butt", clip_on=False)
        ax.plot(allp[win] / ref, rows[win], color=F.INK, lw=0.6, ls=":")
        for c, colr in ((2, F.C_DS), (1, F.C_DS1)):
            if (t == c).sum() >= 3:
                pc = dsdata.fill_bad(np.nanmean(r.csd_peak[t == c], axis=0), r.bad_rows)
                ax.plot(pc[win] / ref, rows[win], color=colr, lw=0.9)
        for b in ("upper", "lower"):
            bb = TL[l]["blades"][b]
            ax.plot([-1.25], [bb["mml_row"]], marker=">", color=F.C_DS, ms=3.2, clip_on=False)
            ax.plot([-1.25], [bb["oml_row"]], marker=">", color=F.C_DS1, ms=3.2, clip_on=False)
        ax.axvline(0, color=F.FAINT, lw=0.4)
        ax.set_ylim(hi_r, lo_r)
        ax.set_xlim(-1.25, 1.0)
        ax.set_xticks([])
        ax.tick_params(labelsize=4.8, length=1.5)
        meth = {TL[l]["blades"][b]["method"] for b in ("upper", "lower")}
        tag = "own" if meth == {"own types"} else ("gap" if meth == {"median gap"} else "mixed")
        ax.set_title("%s \u00b7 %s" % (l, tag), fontsize=5.8, pad=2,
                     color=F.color_of(l) if F.subgroup(l) != "IED-" else "#b5508a")
    hs = [Line2D([], [], color=F.C_DS, lw=1.0, label="DS2 mean"), Line2D([], [], color=F.C_DS1, lw=1.0, label="DS1 mean"),
          Line2D([], [], color=F.INK, lw=0.8, ls=":", label="all DS (the old anchor)"),
          patches.Patch(color=C_MML, label="tight MML"), patches.Patch(color=C_OML, label="tight OML"),
          Line2D([], [], color="#9aa1ad", lw=1.6, label="old MML"), Line2D([], [], color="#5a6273", lw=1.6, label="old OML")]
    yb = y + 0.55 + 2 * 1.85 - 0.15
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.55 / 8.5, 1 - yb / 11), ncol=7, frameon=False, fontsize=5.6,
               handlelength=1.4, columnspacing=0.8)
    F.put(fig, 0.55, yb + 0.22, "Titles: own = both blades anchored on the mouse's own DS1 and DS2 sinks; gap = the types do not "
          "separate (question 2's rule), so the MML is the all-DS sink and the OML sits the median DS1\u2013DS2 distance "
          "(%.0f \u00b5m upper, %.0f \u00b5m lower) farther out. Arrows: the MML (blue) and OML (orange) anchors. Rows are "
          "contacts, 20 \u00b5m apart." % (TLJ["median_gap_contacts"]["upper"] * 20, TLJ["median_gap_contacts"]["lower"] * 20),
          7.4, size=5.9, color=F.SOFT)
    # b: per mouse, where the layers moved
    yt = yb + 0.75
    F.letter(fig, 0.4, yt + 0.08, "b", "Where each layer's center moved, in \u00b5m from the cell-layer source (old \u2192 tight)",
             width=7.6)
    yt += 0.42
    cols = [(0.55, "Mouse"), (1.05, "Group"), (1.75, "Split"), (2.35, "Upper MML"), (3.5, "Upper OML"), (4.65, "Lower MML"),
            (5.8, "Lower OML"), (6.95, "DS1\u2013DS2 gap up / lo")]
    for x, w in cols:
        F.put(fig, x, yt, w, 1.2, size=5.9, weight="bold")
    yt += 0.17
    for l in LABS:
        d = TL[l]
        cells = [l, F.subgroup(l).replace("-", "\u2212"), "yes" if d["separable"] else "no"]
        for b in ("upper", "lower"):
            bb = d["blades"][b]
            unit = abs(bb["all_sink_row"] - bb["source_row"]) * 20
            cells.append("%.0f \u2192 %.0f" % (unit, bb["mml_um_from_source"]))
            cells.append("%.0f \u2192 %.0f" % (1.65 * unit, bb["oml_um_from_source"]))
        cells.append("%.0f / %.0f%s" % (d["blades"]["upper"]["anchor_gap_um"], d["blades"]["lower"]["anchor_gap_um"],
                                       "" if d["separable"] else " (median)"))
        for (x, _w), c in zip(cols, cells):
            F.put(fig, x, yt, c, 1.2, size=5.8)
        yt += 0.15
    save(fig, "01_where_the_tight_layers_sit")


# ------------------------------------------------------------------ pages 2-3: the change table
def page_table(R, part, qs, title):
    sub = R[R.question.isin(qs)]
    fig, y = header(None, "%s: %s" % (title, summary_line(sub)))
    cols = [(0.5, 0.35, "Q"), (0.85, 2.95, "Result"), (3.85, 1.55, "The menu says"), (5.45, 0.85, "Old"),
            (6.35, 0.85, "Tight"), (7.25, 0.8, "Verdict")]
    for x, w, t in cols:
        F.put(fig, x, y + 0.05, t, w, size=6.2, weight="bold")
    yy = y + 0.27
    W, H = fig.get_size_inches()
    for _i, r in sub.iterrows():
        if r.menu_says:
            fig.add_artist(patches.Rectangle((0.48 / W, 1 - (yy + 0.125) / H), 7.6 / W, 0.135 / H, facecolor="#fbf3f7",
                                             edgecolor="none", transform=fig.transFigure, zorder=0))

        def st_(e, p):
            if not np.isfinite(p):
                return "\u2014"
            return "%+.2f, %s" % (e, F.pnum(p)) if abs(e) < 100 else "%+.0f, %s" % (e, F.pnum(p))
        vals = [r.question, r.result, r.menu_says, st_(r.old_effect, r.old_p), st_(r.tight_effect, r.tight_p), r.verdict]
        for (x, w, _t), v in zip(cols, vals):
            F.put(fig, x, yy, str(v), w + 0.2, size=5.5, color=VCOL[r.verdict] if v == r.verdict else F.INK,
                  weight="bold" if (v == r.verdict and r.verdict in ("lost", "new", "reverses")) else "normal")
        yy += 0.135
    textcol(fig, yy + 0.2, [
        ("How to read it", "Old = the menu's layers; tight = each type's own sink. Each cell is the effect, then the "
         "generous, uncorrected P. Effect: Spearman \u03c1 against % knockout; Hedges' g for two groups (IED\u2212 or IED+ "
         "against control, IED+ against IED\u2212, BT against control DS); for the paired comparisons within the five IED+ "
         "mice, the mean difference in the measure's own units (sink: control DS = 1; center: Hz; gain: dB). Verdict at P "
         "0.05: holds (significant both ways, same direction), holds (n.s.) (significant neither way), lost, new, reverses. "
         "Shaded rows are the results the menu states in words; question 2's old position is in each blade's own units, "
         "the tight one in \u00b5m, so compare their P and direction, not their size."),
    ], x=0.5, w=7.5)
    save(fig, "0%d_change_table_%s" % (part, "_".join(q.lower() for q in qs)))


# ------------------------------------------------------------------ side-by-side pages
def ko_pair_rows(fig, y, getter, ylabel, title_fn, h=0.85, step=1.95):
    axes = {}
    for j, which in enumerate(("old", "tight")):
        use(which)
        row_label(fig, 0.5, y + j * step, which)
        for i, key in enumerate(KEYS4):
            a, _T = J.ko_panel(fig, 0.95 + i * 1.85, y + j * step + 0.62, 1.3, h, getter(key)(), ylabel if i == 0 else "",
                               title=title_fn(key), names=False, xlabel="% knockout")
            axes.setdefault(key, []).append(a)
    for key, ax in axes.items():
        F.link_y(*ax)
    use("old")
    return y + 2 * step


def ied_pair_rows(fig, y, getter, ylabel, title_fn, keys=KEYS4, h=0.85, step=1.85):
    axes = {}
    for j, which in enumerate(("old", "tight")):
        use(which)
        row_label(fig, 0.5, y + j * step, which)
        for i, key in enumerate(keys):
            vals = getter(key)()
            T = F.contrast_table({l: v for l, v in vals.items() if np.isfinite(v)})
            t = "%s\nIED\u2212 vs Ctl %s; IED+ vs Ctl %s" % (title_fn(key), F.pstr(J.pp(T, "IEDneg_vs_CTL")),
                                                              F.pstr(J.pp(T, "IEDpos_vs_CTL")))
            a, _T = J.ied_panel(fig, 0.95 + i * 1.85, y + j * step + 0.72, 1.3, h, vals, ylabel if i == 0 else "",
                                xl=("Ctl", "IED\u2212", "IED+"))
            a.set_title(t, fontsize=5.6, color=F.SOFT, loc="left", pad=8)
            axes.setdefault(key, []).append(a)
    for key, ax in axes.items():
        F.link_y(*ax)
    use("old")
    return y + 2 * step


def page_q3(R):
    sub = R[R.question == "Q3"]
    fig, y = header(None, "Question 3 with tight layers: %s" % summary_line(sub))
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.5
    F.letter(fig, 0.4, y + 0.08, "a", "Each layer's DS sink against % knockout, old layers above, tight below")
    y = ko_pair_rows(fig, y + 0.35, lay, "Sink (control = 1;\n\u2212 = net source)", name)
    F.letter(fig, 0.4, y + 0.08, "b", "The same sinks by IED group")
    ied_pair_rows(fig, y + 0.35, lay, "Sink (control = 1)", name)
    save(fig, "04_q3_layer_sinks")


def page_q4(R):
    sub = R[(R.question == "Q4") & R.result.str.contains("dominant|center")]
    fig, y = header(None, "Question 4's dominant frequency and fast-power center with tight layers: %s" % summary_line(sub))
    F.legend_mice(fig, 0.55, y)
    y += 0.4
    F.letter(fig, 0.4, y + 0.08, "a", "The DS's own dominant frequency per layer against % knockout")
    y = ko_pair_rows(fig, y + 0.35, dom, "Dominant\nfrequency (Hz)", name)
    F.letter(fig, 0.4, y + 0.08, "b", "Where the added fast power sits per layer against % knockout")
    ko_pair_rows(fig, y + 0.35, cen, "Center of the added\nfast power (Hz)", name)
    save(fig, "05_q4_frequency")


def page_q4b_q2(R):
    sub = R[R.result.str.contains("LFP|position")]
    fig, y = header(None, "Question 4's LFP gain and question 2's sink positions, tight layers: %s" % summary_line(sub))
    F.legend_mice(fig, 0.55, y)
    F.bracket_note(fig, 0.62, y + 0.2)
    y += 0.5
    F.letter(fig, 0.4, y + 0.08, "a", "LFP fast (250\u2013500 Hz) gain per layer by IED group")
    y = ied_pair_rows(fig, y + 0.35, lgain, "LFP fast gain (dB)", name)
    F.letter(fig, 0.4, y + 0.08, "b", "Question 2: how far DS1's sink sits beyond DS2's. Old: in each blade's v units (the "
             "average-sink axis); tight: in \u00b5m, only blades whose types separate", width=7.6)
    yb = y + 0.5
    for j, (which, fn, yl) in enumerate((("old", pos_old, "DS1 minus DS2\n(v units)"), ("tight", pos_tight, "DS1 minus DS2\n(\u00b5m)"))):
        row_label(fig, 0.5 + j * 3.75, yb, which)
        for i, blade in enumerate(("upper", "lower")):
            vals = fn(blade)
            T = F.contrast_table(vals)
            a, _T = J.ied_panel(fig, 0.95 + j * 3.75 + i * 1.75, yb + 0.6, 1.2, 0.9, vals, yl if i == 0 else "",
                                xl=("Ctl", "IED\u2212", "IED+"))
            a.set_title("%s blade (n %d)\nIED+ vs IED\u2212 %s" % (blade.capitalize(), len(vals), F.pstr(J.pp(T, "IEDpos_vs_IEDneg"))),
                        fontsize=5.6, color=F.SOFT, loc="left", pad=3)
            a.axhline(0, color=F.FAINT, lw=0.5)
    save(fig, "06_q4_lfp_gain_and_q2_position")


def q5_grid():
    rows, Pm, Em = [], [], []

    def add(label, fn, cid):
        rows.append(label)
        pr, er = [], []
        for _w, es, band in J.BAND_SETS:
            vals = fn(es, band)
            if vals is None or len([v for v in vals.values() if np.isfinite(v)]) < 6:
                pr.append(np.nan)
                er.append(np.nan)
                continue
            T = F.contrast_table({l: v for l, v in vals.items() if np.isfinite(v)})
            pr.append(J.pp(T, cid))
            er.append(J.ef(T, cid))
        Pm.append(pr)
        Em.append(er)
    for blade in ("upper", "lower"):
        add("%s MML sink, IED\u2212 vs control" % blade.capitalize(), lambda es, band, blade=blade: J.layer_vals(es, blade, "MML"),
            "IEDneg_vs_CTL")
    for blade, layer in KEYS4:
        add("%s %s sink vs %% KO (PTEN)" % (blade.capitalize(), layer), lambda es, band, b=blade, ly=layer: J.layer_vals(es, b, ly),
            "KO_dose_PTEN")
    for key in KEYS4:
        add("%s dominant frequency vs %% KO (PTEN)" % name(key),
            lambda es, band, key=key: {l: J.whole_of(l, band, "DS", key, "csd", 0) for l in LABS}, "KO_dose_PTEN")
    for key in KEYS4:
        def fn(es, band, key=key):
            r = J.fast_range(band)
            if r is None:
                return None
            return {l: J.fast_of(l, band, "DS", key, "csd", 0, r[0], r[1], r[2]) for l in LABS}
        add("%s fast-power center vs %% KO (all)" % name(key), fn, "KO_dose_all")
    return rows, Pm, Em


def q8_grid():
    rows, Pm, Em = [], [], []

    def add(label, fn):
        rows.append(label)
        pr, er = [], []
        for _w, _es, band in J.BAND_SETS:
            try:
                p, e = fn(band)
            except Exception:  # noqa: BLE001
                p, e = np.nan, np.nan
            pr.append(p)
            er.append(e)
        Pm.append(pr)
        Em.append(er)

    def pr_(get, c1="TZ", c0="DS"):
        def f(band):
            a = np.array([get(l, band, c1) for l in IEDP], float)
            b = np.array([get(l, band, c0) for l in IEDP], float)
            return J.paired_p(a, b), float(np.nanmean(a - b))
        return f

    def wt_(get, c1="TZ"):
        def f(band):
            A_ = [v for v in (get(l, band, "DS") for l in CTL) if np.isfinite(v)]
            B_ = [v for v in (get(l, band, c1) for l in IEDP) if np.isfinite(v)]
            if len(A_) < 3 or len(B_) < 3:
                return np.nan, np.nan
            r = S.two(A_, B_)
            return r["p"], r["effect"]
        return f
    for blade in ("upper", "lower"):
        sk = lambda l, band, k, blade=blade: float(J.fq(l, band, "sink", (k, blade, "MML"))) / J.ref_reads(band)  # noqa: E731
        add("%s MML sink: BT vs own DS" % blade.capitalize(), pr_(sk))
        add("%s MML sink: BT vs WT DS" % blade.capitalize(), wt_(sk))

    def fc(l, band, k, which=0):
        r = J.fast_range(band)
        if r is None:
            return np.nan
        return J.fast_of(l, band, k, ("lower", "MML"), "csd", which, r[0], r[1], r[2])
    add("Lower MML fast-power center: BT vs own DS", pr_(fc))
    add("Lower MML fast-power center: BT vs WT DS", wt_(fc))
    add("Lower MML fast gain: BT vs own DS", pr_(lambda l, band, k: fc(l, band, k, 1)))
    add("Lower MML fast gain: BT vs WT DS", wt_(lambda l, band, k: fc(l, band, k, 1)))
    return rows, Pm, Em


def grid_page(gridfn, qname, fname, note):
    out = {}
    for which in ("old", "tight"):
        use(which)
        out[which] = gridfn()
    use("old")
    rows = out["old"][0]
    flips = []
    for i, lab_ in enumerate(rows):
        so = sum(1 for p in out["old"][1][i] if np.isfinite(p) and p < 0.05)
        s1 = sum(1 for p in out["tight"][1][i] if np.isfinite(p) and p < 0.05)
        nb = sum(1 for p in out["old"][1][i] if np.isfinite(p))
        flips.append((lab_, so, s1, nb))
    changed = [f for f in flips if f[1] != f[2]]
    fig, y = header(None, "%s on every filter band with tight layers: %d of %d rows have the same number of significant bands%s"
                    % (qname, len(rows) - len(changed), len(rows),
                       "" if not changed else "; changed: " + "; ".join("%s %d \u2192 %d of %d" % (a, b, c, d)
                                                                       for a, b, c, d in changed)))
    yy = y + 0.75
    for which in ("old", "tight"):
        row_label(fig, 0.5, yy - 0.55, which)
        J.p_grid(fig, 0.45, yy, 7.5, rows, [w for w, _es, _b in J.BAND_SETS], out[which][1], out[which][2], "",
                 cell_h=0.17, label_w=2.6)
        yy += 0.17 * len(rows) + 1.0
    textcol(fig, yy - 0.3, [("How to read it", note)], x=0.5, w=7.5)
    save(fig, fname)
    return out


def class_block(fig, y, letter, title, getter, ylabel):
    """Old row above tight row; the four layers as columns (named once, above the old row); room above each row for
    the brackets."""
    F.letter(fig, 0.4, y + 0.08, letter, title, width=7.6)
    W, H = fig.get_size_inches()
    for i, key in enumerate(KEYS4):
        fig.text((0.95 + i * 1.85) / W, 1 - (y + 0.42) / H, name(key), fontsize=6.6, weight="bold", color=F.INK, va="top")
    axes = {}
    for j, which in enumerate(("old", "tight")):
        use(which)
        top = y + 0.62 + j * 1.6
        row_label(fig, 0.5, top, which)
        for i, key in enumerate(KEYS4):
            a, _v, _p = J.class_panel(fig, 0.95 + i * 1.85, top + 0.45, 1.3, 0.85, getter(key), ylabel if i == 0 else "", "")
            axes.setdefault(key, []).append(a)
    for key, ax in axes.items():
        F.link_y(*ax)
    use("old")
    return y + 0.62 + 2 * 1.6 + 0.1


def page_q7(R):
    sub = R[R.question == "Q7"]
    part = sub[sub.result.str.contains("sink|center")]
    fig, y = header(None, "Question 7's currents and fast-power center with tight layers: %s" % summary_line(part, names=False))
    F.put(fig, 0.5, y, "Columns: control DS | IED+ DS | BT | IED class; lines join one IED+ mouse; brackets: BT and IED against "
          "control DS (unpaired) and against the same mice's DS (paired).", 7.5, size=6.2, color=F.SOFT)
    y += 0.3
    y = class_block(fig, y, "a", "Sink at the DS peak per layer", c_sink, "Sink\n(control DS = 1)")
    class_block(fig, y, "b", "Where the added fast power sits per layer", c_cen, "Center of the added\nfast power (Hz)")
    save(fig, "08_q7_currents_and_center")
    part = sub[sub.result.str.contains("gain")]
    if (part.verdict == "holds").all():
        hd = ("The tight layers leave question 7's fast gain as it was: in every layer BTs add more 250–500 Hz power "
              "than their own DS and than a control DS (all %d comparisons significant both ways)." % len(part))
    else:
        hd = "Question 7's fast gain with tight layers: %s" % summary_line(part, names=False)
    fig, y = header(None, hd)
    y += 0.1
    class_block(fig, y, "c", "How much fast power is added per layer (250\u2013500 Hz, dB over the moment before)", c_gain,
                "Fast gain\n(dB over before)")
    save(fig, "09_q7_fast_gain")


def page_reading(R, g8):
    """What moved each changed result: the mice whose layers moved most, with their own numbers."""
    rows8, P8 = g8["tight"][0], g8["tight"][1]
    p_up_main = P8[rows8.index("Upper MML sink: BT vs own DS")][0]
    def row(res):
        r = R[R.result == res].iloc[0]
        return r

    def pv(res, which):
        return F.pnum(row(res)["%s_p" % which])
    said = R[R.menu_says != ""]
    sv = said.verdict.value_counts()
    flips = said[(np.sign(said.old_effect) != np.sign(said.tight_effect)) & ((said.old_p < 0.05) | (said.tight_p < 0.05))]
    moved = [l for l in LABS if TL[l]["separable"] and TL[l]["n1"] > TL[l]["n2"]]
    mv = "; ".join("%s %.0f \u2192 %.0f \u00b5m upper, %.0f \u2192 %.0f \u00b5m lower" % (
        l, abs(TL[l]["blades"]["upper"]["all_sink_row"] - TL[l]["blades"]["upper"]["source_row"]) * 20,
        TL[l]["blades"]["upper"]["mml_um_from_source"],
        abs(TL[l]["blades"]["lower"]["all_sink_row"] - TL[l]["blades"]["lower"]["source_row"]) * 20,
        TL[l]["blades"]["lower"]["mml_um_from_source"]) for l in moved)
    same = [l for l in LABS if TL[l]["separable"] and TL[l]["n1"] <= TL[l]["n2"]]
    gapm = [l for l in LABS if not TL[l]["separable"]]
    sk = {}
    for which in ("old", "tight"):
        use(which)
        sk[which] = {b: J.layer_vals("v6", b, "MML") for b in ("upper", "lower")}
    use("old")
    ctl_moves = [(l, b, sk["old"][b][l], sk["tight"][b][l]) for l in CTL for b in ("upper", "lower")
                 if abs(sk["tight"][b][l] - sk["old"][b][l]) >= 0.1]
    gm = {b: {g: float(np.median([v for l, v in sk["tight"][b].items() if F.subgroup(l) == g])) for g in ("CTL", "IED-", "IED+")}
          for b in ("upper", "lower")}
    cen = {}
    for which in ("old", "tight"):
        use(which)
        g = c_cen(("upper", "MML"))
        cen[which] = {l: g(l, "TZ") - g(l, "DS") for l in IEDP}
    use("old")
    fig, y = header(None, "Of the %d results the menu states, %d still agree with it, %d lose significance and %d change direction; the "
                          "changes come from the mice whose DS1 is the larger type, whose MML moved inward, and from the "
                          "narrower spans."
                    % (len(said), int(sv.get("holds", 0) + sv.get("holds (n.s.)", 0) + sv.get("new", 0)),
                       int(sv.get("lost", 0)), len(flips)))
    textcol(fig, y + 0.1, [
        ("Where the layers moved", "%d mice separate with DS2 as the larger type (%s): their tight MML sits on the DS2 sink, "
         "within a few \u00b5m of the old anchor, and their OML moves onto DS1's own sink. %d mice separate with DS1 as the "
         "larger type (%s): the battery names types by position, so their tight MML moves inward onto the smaller DS2 "
         "(%s), and their OML lands where the old MML was. %d mice do not separate (%s): their MML stays on the all-DS sink "
         "but narrows to \u00b140 \u00b5m, and their OML sits the median DS1\u2013DS2 distance beyond it."
         % (len(same), ", ".join(same), len(moved), ", ".join(moved), mv, len(gapm), ", ".join(gapm))),
        ("Question 3: the IED\u2212 mice's weaker MML", "The IED\u2212 mice's own MML values hardly move; the control "
         "values do: %s. With smaller control MML sinks the gap to IED\u2212 narrows (upper P %s \u2192 %s, lower %s \u2192 "
         "%s). The direction stays: tight medians, control %.2f, IED\u2212 %.2f, IED+ %.2f (upper) and %.2f, %.2f, %.2f "
         "(lower)."
         % ("; ".join("%s %s %.2f \u2192 %.2f" % (l, b, o, t) for l, b, o, t in ctl_moves),
            pv("Upper MML sink IED\u2212 vs control", "old"), pv("Upper MML sink IED\u2212 vs control", "tight"),
            pv("Lower MML sink IED\u2212 vs control", "old"), pv("Lower MML sink IED\u2212 vs control", "tight"),
            gm["upper"]["CTL"], gm["upper"]["IED-"], gm["upper"]["IED+"], gm["lower"]["CTL"], gm["lower"]["IED-"],
            gm["lower"]["IED+"])),
        ("Questions 4 and 7: the upper MML's fast-power center", "Per IED+ mouse, the BT-minus-DS center in the upper MML "
         "goes from %s (old) to %s Hz (tight): m28 turns negative and m34, whose MML moved inward, shrinks; the BT lead "
         "there is lost (P %s \u2192 %s). The all-mice dose trend in the upper MML weakens the same way (P %s \u2192 %s). "
         "The lower MML, where the menu's dose claim sits, holds and strengthens (PTEN \u03c1 P %s \u2192 %s)."
         % (", ".join("%s %+.0f" % (l, cen["old"][l]) for l in IEDP), ", ".join("%s %+.0f" % (l, cen["tight"][l]) for l in IEDP),
            pv("Upper MML fast-power center: BT vs own DS", "old"), pv("Upper MML fast-power center: BT vs own DS", "tight"),
            pv("Upper MML fast-power center vs % KO (all mice \u03c1)", "old"),
            pv("Upper MML fast-power center vs % KO (all mice \u03c1)", "tight"),
            pv("Lower MML fast-power center vs % KO (PTEN \u03c1)", "old"), pv("Lower MML fast-power center vs % KO (PTEN \u03c1)",
                                                                                 "tight"))),
        ("What becomes significant", "The tight OML sits on DS1's own sink instead of past it, so it now carries sink current: "
         "BTs and IED-class events carry more lower-OML current than the same mice's DS (P %s and %s; old %s and %s). The "
         "BTs' fast-power center in the upper OML now sits above a control DS's (P %s; old %s). The DS1-to-DS2 distance is "
         "also shorter in IED+ than IED\u2212 mice in the lower blade (P %s; old %s), matching the upper blade."
         % (pv("Lower OML sink: BT vs own DS", "tight"), pv("Lower OML sink: IED class vs own DS", "tight"),
            pv("Lower OML sink: BT vs own DS", "old"), pv("Lower OML sink: IED class vs own DS", "old"),
            pv("Upper OML fast-power center: BT vs control DS", "tight"),
            pv("Upper OML fast-power center: BT vs control DS", "old"),
            pv("DS1 minus DS2 sink position, lower blade: IED+ vs IED\u2212", "tight"),
            pv("DS1 minus DS2 sink position, lower blade: IED+ vs IED\u2212", "old"))),
        ("What holds", "No layer sink follows %% knockout; the DS's own dominant frequency stays flat in every layer; the "
         "lower MML's fast-power center rises with knockout; the LFP fast gain is lower in IED\u2212 and higher in IED+ mice "
         "in every layer; BTs carry more MML current than the same mice's DS (upper P %s, lower %s on the notch band) and "
         "no more than a control DS; their fast gain is above both in every layer."
         % (pv("Upper MML sink: BT vs own DS", "tight"), pv("Lower MML sink: BT vs own DS", "tight"))),
        ("Caveats", "Part of each change comes from the mice whose larger type is DS1 (their MML moved inward) and part from "
         "narrowing every span to \u00b140 \u00b5m; which reading of those mice is right is the open question, and it can be "
         "checked by rerunning with only that rule changed. On the 5\u2013100 Hz main band the upper blade's BT-over-DS "
         "current is at %s with tight layers (page 10), so that half of the claim is borderline. Sinks 20\u201340 \u00b5m apart "
         "are one or two contacts, near what the CSD resolves." % F.pstr(p_up_main)),
    ], x=0.5, w=7.5)
    save(fig, "11_what_moved_the_results")


def summary_line(sub, names=True):
    vc = sub.verdict.value_counts()
    keep = int(vc.get("holds", 0) + vc.get("holds (n.s.)", 0))
    parts = ["%d of %d results keep their verdict" % (keep, len(sub))]
    if not names:
        return parts[0] + "; %d lost, %d new and %d reversed, named in the change table (page 3)." % (
            int(vc.get("lost", 0)), int(vc.get("new", 0)), int(vc.get("reverses", 0)))
    for v in ("lost", "new", "reverses"):
        rr = sub[sub.verdict == v]
        if len(rr):
            names = rr.result.tolist()
            parts.append("%s: %s%s" % (v.capitalize(), "; ".join(names[:3]),
                                       "" if len(names) <= 3 else " and %d more" % (len(names) - 3)))
    return ". ".join(parts) + "."


def main():
    os.makedirs(os.path.join(DEST, "tables"), exist_ok=True)
    R = run_claims()
    R.to_csv(os.path.join(DEST, "tables", "old_vs_tight_every_layer_result.csv"), index=False)
    rows = []
    for l in LABS:
        d = TL[l]
        for b in ("upper", "lower"):
            bb = d["blades"][b]
            rows.append({"mouse": l, "group": F.subgroup(l), "knockout_pct": F.ko(l), "separates": d["separable"], "blade": b,
                         "method": bb["method"], "mml_um_from_source": bb["mml_um_from_source"],
                         "oml_um_from_source": bb["oml_um_from_source"], "ds1_ds2_gap_um": bb["anchor_gap_um"],
                         "old_mml_center_um": abs(bb["all_sink_row"] - bb["source_row"]) * 20,
                         "tight_mml_contacts": " ".join(map(str, d["rows"][b]["MML"])),
                         "tight_oml_contacts": " ".join(map(str, d["rows"][b]["OML"])),
                         "old_mml_contacts": " ".join(map(str, d["rows_old"][b]["MML"])),
                         "old_oml_contacts": " ".join(map(str, d["rows_old"][b]["OML"]))})
    pd.DataFrame(rows).to_csv(os.path.join(DEST, "tables", "tight_layers_per_mouse.csv"), index=False)
    page_definition(R)
    page_table(R, 2, ["Q2", "Q3", "Q4"], "Questions 2, 3 and 4")
    page_table(R, 3, ["Q7"], "Question 7")
    page_q3(R)
    page_q4(R)
    page_q4b_q2(R)
    g5 = grid_page(q5_grid, "Question 5 (questions 3 and 4)", "07_q5_every_band",
                   "Generous P per result (row) and filter band (column), old layers above, tight below; red = up, blue = down, "
                   "darker = smaller P, bold = P < 0.05, \u2014 = the band cannot carry the measure.")
    page_q7(R)
    g8 = grid_page(q8_grid, "Question 8 (question 7)", "10_q8_every_band",
                   "Paired within the five IED+ mice, or against the control mice's DS; red = BT higher. Old layers above, "
                   "tight below.")
    page_reading(R, g8)
    for nm, g in (("q5", g5), ("q8", g8)):
        recs = []
        for which in ("old", "tight"):
            rws, Pm, Em = g[which]
            for i, r in enumerate(rws):
                for j, (w, _es, band) in enumerate(J.BAND_SETS):
                    recs.append({"layers": which, "result": r, "band": band, "p": Pm[i][j], "effect": Em[i][j]})
        pd.DataFrame(recs).to_csv(os.path.join(DEST, "tables", "%s_every_band_old_vs_tight.csv" % nm), index=False)
    print(R.verdict.value_counts())
    print(R[R.verdict.isin(["lost", "new", "reverses"])][["question", "result", "old_p", "tight_p", "verdict"]].to_string())


if __name__ == "__main__":
    main()
