# -*- coding: utf-8 -*-
"""Tight-layer edition of the Jeremy menu: its supplement pages. Supplement A (how the layers are defined) is redrawn for
the tight layers; supplements B and C are the same pages drawn from the tight data.

  python jtight_supp.py            (sets JM_LAYERS=tight itself; writes into outj_tight)
"""
import os
import sys

os.environ["JM_LAYERS"] = "tight"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import numpy as np  # noqa: E402
from matplotlib import patches  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import figlib as F  # noqa: E402
import jpages as J  # noqa: E402
import jfollow as JF  # noqa: E402

C_MML, C_OML = "#fbeadb", "#f6d3b8"


def page_layers_tight():
    import dsdata
    T = J.tight_layers()
    TL = T["mice"]
    LABS = J.LABS
    recs = {r.lab: r for r in dsdata.load("v6") if r.lab in LABS}
    fig, y = JF.header(4, "", "Each blade's layers now come from the two DS types themselves: the MML is centered on DS2's sink "
                              "and the OML on DS1's sink, \u00b140 \u00b5m each, split at the midpoint where the sinks are under "
                              "80 \u00b5m apart; where the types do not separate, the MML is the average DS sink and the OML sits "
                              "the median DS1\u2013DS2 distance beyond it.")
    J._box(fig, 0.42, 0.55, 8.08, y - 0.17, J.C_UPD)
    F.letter(fig, 0.4, y + 0.08, "a", "The tight layers on all 16 recordings: each type's mean CSD at the DS peak, the new MML and "
             "OML (fills) and the first menu's layers (gray bars at the right)", width=7.6)
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
          Line2D([], [], color=F.INK, lw=0.8, ls=":", label="all DS (the first menu's anchor)"),
          patches.Patch(color=C_MML, label="tight MML"), patches.Patch(color=C_OML, label="tight OML"),
          Line2D([], [], color="#9aa1ad", lw=1.6, label="first-menu MML"), Line2D([], [], color="#5a6273", lw=1.6, label="first-menu OML")]
    yb = y + 0.55 + 2 * 1.85 - 0.15
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.55 / 8.5, 1 - yb / 11), ncol=7, frameon=False, fontsize=5.6,
               handlelength=1.4, columnspacing=0.8)
    yb += 0.25
    steps = ("How the tight layers are set, per recording and per blade. 1. Each DS type's mean CSD at the DS peak (\u00b13 ms), "
             "bad contacts filled. 2. Each type's sink: the centroid of its deepest sink lobe on the far side of that blade's "
             "cell-layer source. DS1 is the type whose sink sits farther out (the battery checks this and swaps names that "
             "disagree), so DS1 anchors the OML and DS2 the MML. 3. Each layer = the anchor contact \u00b12 contacts (\u00b140 "
             "\u00b5m; contacts are 20 \u00b5m apart); where the two anchors are under 80 \u00b5m apart each contact goes to the "
             "nearer one, so no contact is in both. 4. Where the types do not separate (question 2's rule; titles 'gap'), the MML "
             "is the all-DS sink and the OML sits the median DS1\u2013DS2 distance (%.0f \u00b5m upper, %.0f \u00b5m lower) "
             "farther out. Only good contacts are used, and the same contacts on every filter band. Why the first rule was "
             "replaced: it anchored v = 1 on the average DS sink, which sits on whichever type is the majority, so in mice where "
             "DS1 is the larger type (m22, m60, m34) its 'MML' was really DS1's layer."
             % (T["median_gap_contacts"]["upper"] * 20, T["median_gap_contacts"]["lower"] * 20))
    yb += F.put(fig, 0.55, yb, steps, 7.4, size=6.2, color=F.INK) + 0.25
    F.letter(fig, 0.4, yb + 0.08, "b", "Where each layer's center sits, in \u00b5m from the cell-layer source (first menu \u2192 tight)",
             width=7.6)
    yt = yb + 0.38
    cols = [(0.55, "Mouse"), (1.05, "Group"), (1.75, "Split"), (2.35, "Upper MML"), (3.5, "Upper OML"), (4.65, "Lower MML"),
            (5.8, "Lower OML"), (6.95, "DS1\u2013DS2 gap up / lo")]
    for x, w in cols:
        F.put(fig, x, yt, w, 1.2, size=5.9, weight="bold")
    yt += 0.16
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
            F.put(fig, x, yt, c, 1.2, size=5.7)
        yt += 0.14
    JF.save(fig, "04_how_the_layers_are_defined")


if __name__ == "__main__":
    JF.page_layers = page_layers_tight
    JF.supplements()
    print("supplements written to", J.OUT)
