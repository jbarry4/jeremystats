"""The menu's cover, primer, DS1/DS2 story, ML story and closing page. Round 3, 2026-11-23."""
import glob
import json
import os
import pickle
import sys
from collections import defaultdict

import numpy as np
from matplotlib import patches
from matplotlib.lines import Line2D
from scipy import signal
from scipy import stats as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import menu_data as D  # noqa: E402
from pages_a import OUT, textcol  # noqa: E402

RUNS = os.environ.get("KRUNS", "/gpfs2/scratch/sakhava1/kcnt1_prelim/er2runs")
UP = pickle.load(open(os.path.join(HERE, "uprof.pkl"), "rb"))


def paired_p(a, b):
    ps = [st.ttest_rel(a, b).pvalue]
    try:
        ps.append(st.wilcoxon(a, b).pvalue)
    except ValueError:
        pass
    return float(np.nanmin(ps))


# ============================================================================ primer
def schematic(ax):
    """The probe through the dorsal dentate gyrus, as a strip with granule cells and the two entorhinal inputs; the
    regions carry the same names as the data pages (found there from each recording's own dentate spike)."""
    ax.set_xlim(0, 10)
    ax.set_ylim(10.4, -0.6)
    ax.axis("off")
    bands = [("CA1", 0.0, 1.0, "#eef3fb"), ("distal dendrites", 1.0, 2.0, "#fbe3cf"), ("proximal dendrites", 2.0, 3.0, "#fdf0e4"),
             ("cell layer", 3.0, 3.8, "#e6e6e6"), ("hilus", 3.8, 5.6, "#f4f4ef"), ("cell layer", 5.6, 6.4, "#e6e6e6"),
             ("proximal dendrites", 6.4, 7.4, "#fdf0e4"), ("distal dendrites", 7.4, 8.4, "#fbe3cf")]
    for name, a, b, col in bands:
        ax.add_patch(patches.Rectangle((2.2, a), 5.6, b - a, color=col, lw=0))
    rng = np.random.RandomState(4)
    for blade, (ya, yb, sgn) in {"u": (3.0, 3.8, -1), "l": (5.6, 6.4, 1)}.items():
        xs = np.linspace(3.35, 7.45, 11)
        for i, x in enumerate(xs):
            y = (ya + yb) / 2 + rng.uniform(-0.15, 0.15)
            ko = (blade == "l" and i % 3 == 0) or (blade == "u" and i % 5 == 0)
            col = F.C_POS if ko else "#7a8291"
            ax.add_patch(patches.Circle((x, y), 0.13 if not ko else 0.17, color=col, lw=0, zorder=3))
            for dx in (-0.25, 0.0, 0.25):
                ax.plot([x, x + dx], [y, y + sgn * 2.1], color=col, lw=0.5 if not ko else 0.8, alpha=0.8, zorder=2)
    for name, a, b, col in bands:
        ax.text(2.3, (a + b) / 2, name, ha="left", va="center", fontsize=5.3, color=F.INK, weight="bold", zorder=6,
                bbox=dict(facecolor=col, edgecolor="none", pad=0.5, alpha=0.9))
    for yy, word in ((2.0, "depth 0: upper sink peak"), (7.4, "depth 1: lower sink peak")):
        ax.plot([2.2, 7.8], [yy, yy], color=F.SOFT, lw=0.6, ls=":", zorder=5)
        ax.text(7.95, yy, word, fontsize=5.0, color=F.SOFT, va="center")
    ax.text(7.95, 1.0, "upper blade\n(suprapyramidal)", fontsize=5.4, color=F.SOFT, va="center")
    ax.text(7.95, 8.3, "lower blade\n(infrapyramidal)", fontsize=5.4, color=F.SOFT, va="center")
    ax.annotate("", xy=(2.2, 1.4), xytext=(0.4, 1.4), arrowprops=dict(arrowstyle="-|>", color=F.C_DS1, lw=1.2))
    ax.annotate("", xy=(2.2, 8.0), xytext=(0.4, 8.0), arrowprops=dict(arrowstyle="-|>", color=F.C_DS1, lw=1.2))
    ax.annotate("", xy=(2.2, 2.2), xytext=(0.4, 2.2), arrowprops=dict(arrowstyle="-|>", color=F.C_DS, lw=1.2))
    ax.annotate("", xy=(2.2, 7.2), xytext=(0.4, 7.2), arrowprops=dict(arrowstyle="-|>", color=F.C_DS, lw=1.2))
    ax.text(0.05, 1.2, "lateral EC \u2192\ndistal (DS1)", fontsize=5.1, color=F.C_DS1, va="bottom")
    ax.text(0.05, 2.45, "medial EC \u2192\nmiddle (DS2)", fontsize=5.1, color=F.C_DS, va="top")
    ax.add_patch(patches.Rectangle((4.85, -0.5), 0.3, 9.3, color="#d7dbe2", lw=0, zorder=4))
    for k in range(48):
        ax.plot([4.88, 5.12], [-0.4 + k * 0.19] * 2, color="#5a6273", lw=0.4, zorder=5)
    ax.text(5.0, 9.05, "H3 probe: 64 contacts, 20 \u00b5m apart", fontsize=5.6, ha="center", va="top", color=F.SOFT)
    ax.text(5.0, 9.55, "magenta: knockout granule cells (more in the lower blade)", fontsize=5.6, ha="center", va="top", color=F.C_POS)


def primer():
    fig, y = F.page("How to read the menu: one probe through the dentate gyrus, three kinds of event", "PRIMER", number=2)
    y += 0.3
    F.letter(fig, 0.4, y + 0.08, "a", "The probe crosses CA1, both blades of the dentate gyrus and the hilus between them", width=2.75)
    a = F.axes_in(fig, 0.45, y + 0.3, 2.6, 3.2)
    schematic(a)
    # b: a control mouse's dentate spikes, depth from its own spike
    lab = "m61"
    U = UP["recs"][("v6", lab)]
    G = UP["UGRID"]
    R = {"top": U["u_top"], "gu": U["u_gu"], "gl": U["u_gl"], "bot": U["u_bot"]}
    ylo, yhi = -1.0, 1.85
    F.letter(fig, 3.3, y + 0.08, "b", "A control dentate spike: a sink in each blade's dendrites and a source between the blades",
             width=2.65)
    t = U["t_ms"]
    img = U["u_tc_raw"] / U["ref"]
    inr = (G >= ylo) & (G <= yhi)
    vmax = np.nanpercentile(np.abs(img[inr]), 99)
    ax = F.axes_in(fig, 4.2, y + 0.55, 0.85, 2.6)
    ax.imshow(img, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax, origin="upper", extent=[t[0], t[-1], G[-1], G[0]],
              interpolation="bilinear")
    ax.set_ylim(yhi, ylo)
    ax.set_xlim(-30, 30)
    F.shade_regions(ax, R, labels=True, shade=False, lines=False, size=5.3, bracket_x=-0.95)
    for v_ in (0.0, 1.0):
        ax.axhline(v_, color="white", lw=0.5, alpha=0.8)
    ax.set_xlabel("Time from the peak (ms)")
    ax.set_title("All %d DS of %s: CSD\n(blue sink, red source)" % (U["n"], lab), fontsize=5.9, loc="left")
    ax2 = F.axes_in(fig, 5.15, y + 0.55, 0.7, 2.6)
    ax2.set_ylim(yhi, ylo)
    F.shade_regions(ax2, R, labels=False)
    for k, col in ((1, F.C_DS1), (2, F.C_DS)):
        m = U["u_ds%d_raw" % k] / U["ref"]
        se = U["u_ds%d_sem_raw" % k] / U["ref"]
        ax2.fill_betweenx(G, m - se, m + se, color=col, alpha=0.2, lw=0, zorder=3)
        ax2.plot(m, G, color=col, lw=1.2, label="DS%d (%d)" % (k, U["n_ds%d" % k]), zorder=4)
    ax2.axvline(0, color=F.FAINT, lw=0.5)
    ax2.set_ylim(yhi, ylo)
    ax2.set_xlabel("CSD at peak\n(deepest sink = \u22121)")
    ax2.legend(frameon=False, fontsize=5.2, loc="upper right", handlelength=1.4)
    ax2.set_title("separation\nindex %.2f" % U["si"], fontsize=5.6, loc="left", color=F.SOFT)
    # c: example events of the three kinds from one IED+ recording, at a hilus contact found from the spike
    F.letter(fig, 0.4, y + 3.95, "c", "From one IED+ mouse (m28): the BT and the IED are briefer than the DS and carry more fast power")
    z = np.load(os.path.join(HERE, "reads", "m28.npz"), allow_pickle=True)
    U28 = UP["recs"][("v6", "m28")]
    fs = float(z["fs"])
    T = z["notch"].shape[-1]
    tt = (np.arange(T) - T // 2) / fs * 1000
    ru = np.asarray(U28["rows_u"], float)
    good = np.array([i not in U28["bad_rows"] for i in range(ru.size)])
    target = (U28["u_gu"] + U28["u_gl"]) / 2
    hil_row = int(np.where(good)[0][np.argmin(np.abs(ru[good] - target))])
    kind = z["kind"].astype(str)
    b_, a_ = signal.butter(3, [240 / (fs / 2), 420 / (fs / 2)], btype="band")
    import matplotlib.ticker as mt
    for j, k in enumerate(("DS", "TZ", "IED")):
        idx = np.where(kind == k)[0]
        hf = z["hf"][idx]
        pick = idx[np.argmin(np.abs(hf - np.median(hf)))]
        tr = z["notch"][pick, hil_row]
        fast = signal.filtfilt(b_, a_, z["notch"][pick, hil_row])
        ax = F.axes_in(fig, 0.85 + j * 1.6, y + 4.35, 1.3, 0.85)
        ax.plot(tt, tr - np.median(tr), color=F.KIND_COLOR[k], lw=0.9)
        ax.set_xlim(-60, 60)
        ax.set_xticklabels([])
        ax.yaxis.set_major_locator(mt.MaxNLocator(3))
        ax.set_title("%s: %.0f \u00b5V, %.1f ms, %.0f dB" % (F.KIND_WORD[k], z["amp"][pick], z["hw"][pick], z["hf"][pick]), fontsize=5.8,
                     loc="left", color=F.KIND_COLOR[k])
        ax.axvspan(-16.5, 16.5, color="#f2f2f2", zorder=0)
        if j == 0:
            ax.set_ylabel("LFP (\u00b5V)")
        ax2 = F.axes_in(fig, 0.85 + j * 1.6, y + 5.33, 1.3, 0.5)
        ax2.plot(tt, fast, color=F.KIND_COLOR[k], lw=0.6)
        ax2.set_xlim(-60, 60)
        ax2.yaxis.set_major_locator(mt.MaxNLocator(3))
        ax2.axvspan(-16.5, 16.5, color="#f2f2f2", zorder=0)
        ax2.set_xlabel("Time from the peak (ms)")
        if j == 0:
            ax2.set_ylabel("240\u2013420 Hz", fontsize=6)
    # d: the cohort
    F.letter(fig, 0.4, y + 6.45, "d", "Sixteen mice: seven controls, four PTEN mice without IEDs and five with (m6 left out; "
             "m51 too few events)")
    ax = F.axes_in(fig, 0.8, y + 6.85, 4.6, 1.05)
    rows = {"CTL": 2, "IED-": 1, "IED+": 0}
    for lab_ in F.LABS:
        g = F.subgroup(lab_)
        ax.scatter([F.ko(lab_)], [rows[g]], s=40 if lab_ == "m7" else 34, color=F.color_of(lab_), marker=F.marker_of(lab_), edgecolor="white",
                   lw=0.5, zorder=3)
    for g, yv in rows.items():
        labs = [l for l in F.LABS if F.subgroup(l) == g]
        if g == "CTL":
            ax.text(0.9, yv, ", ".join(labs), fontsize=5.3, color=F.SOFT, va="center")
        elif g == "IED-":
            low = sorted([l for l in labs if F.ko(l) < 10], key=F.ko)
            ax.text(6.0, yv, ", ".join("%s %.1f%%" % (l, F.ko(l)) for l in low), fontsize=5.0, color=F.SOFT, va="center")
            ax.text(F.ko("m7"), yv + 0.28, "m7 24.1%", fontsize=5.0, color=F.SOFT, ha="center", va="bottom")
        else:
            labs = sorted(labs, key=F.ko)
            for i, l in enumerate(labs):
                up = i % 2 == 0
                ax.text(F.ko(l), yv + (0.28 if up else -0.3), "%s %.1f%%" % (l, F.ko(l)), fontsize=5.0, color=F.SOFT, ha="center",
                        va="bottom" if up else "top")
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["PTEN IED+ (5)", "PTEN IED\u2212 (4)", "Control (7)"])
    ax.set_xlim(-1.5, 31)
    ax.set_ylim(-0.6, 2.7)
    ax.axvline(15, color=F.FAINT, lw=0.6, ls=":")
    ax.axvspan(-1.5, 10, color="#fbf3f7", zorder=0)
    ax.axvspan(15, 31, color="#f6e3ec", zorder=0)
    ax.text(4.5, 2.55, "low KO", fontsize=5.3, color=F.SOFT, ha="center")
    ax.text(23, 2.55, "high KO", fontsize=5.3, color=F.SOFT, ha="center")
    ax.set_xlabel("PTEN knockout (% of granule cells, histology)")
    ax.tick_params(axis="y", length=0)
    textcol(fig, 1.55, [
        ("Depth", "Every depth axis comes from the recording's own dentate spike, never from the lab's layer labels. "
                  "0 is where the upper blade's DS sink peaks and 1 where the lower blade's does; the current source "
                  "nearest each sink, toward the other blade, marks that blade's cell layer. Proximal dendrites lie "
                  "between the cell layer and the sink peak, distal dendrites beyond it out to where the sink ends; the "
                  "hilus lies between the two cell-layer sources, and CA1 above the upper blade. Depth runs down the "
                  "page as on the probe."),
        ("Current source density (CSD)", "Where current enters cells (a sink, blue) and leaves them (a source, red), "
                                         "from the second difference of the LFP across contacts. When groups are "
                                         "compared, every mouse is divided by the same number."),
        ("Dentate spike (DS)", "A large, brief population event driven by entorhinal input. DS1: sink farther out on "
                               "the dendrites (lateral EC); DS2: sink in the middle (medial EC). Many recordings do "
                               "not split cleanly; the separation index says how cleanly (b)."),
        ("IED and BT", "IED: interictal epileptiform discharge, the hand-sorted ones and those inside the IED border. "
                        "BT (borderline transient): events between the DS and IED borders (Story 5). The Halo and Strict "
                        "DS sets exclude both."),
        ("Root Canal numbers", "Largest amplitude (10\u2013150 Hz), half-width, and fast power: 240\u2013420 Hz power "
                               "in the 33 ms around the event (gray band in c) in dB over the same contact 150 ms "
                               "earlier. c is read at the contact midway between m28's two cell-layer sources (hilus)."),
        ("Groupings and statistics", "IED status (lab sheet; m7 stays IED\u2212), knockout level (control, low 4\u20135%, "
                                     "high 19\u201328%) and % knockout. One number per mouse; every applicable test is "
                                     "run and the smallest P is used (generous, uncorrected, exploratory). Halo is the "
                                     "main set; Strict is the check."),
    ])
    F.save(fig, OUT, "02_primer")


# ============================================================================ Story 7: DS1 / DS2
def _v_axis(ax, upper, labels=True):
    """Shade and name the dendritic axis v (0 = cell-layer source, 1 = the recording's average DS sink); depth runs down
    the page, so the upper blade's distal dendrites are up and the lower blade's are down."""
    ax.axhspan(-0.6, 0.0, color="#f3f3ee", lw=0, zorder=0)
    ax.axhspan(0.0, 1.0, color="#fdf0e4", lw=0, zorder=0)
    ax.axhspan(1.0, 3.0, color="#fbe3cf", lw=0, zorder=0)
    for v_ in (0.0, 1.0):
        ax.axhline(v_, color=F.SOFT, lw=0.45, ls=":", zorder=1)
    ax.set_yticks([0, 1, 2, 3])
    if labels:
        from matplotlib import transforms
        tr = transforms.blended_transform_factory(ax.transAxes, ax.transData)
        for t_, yy in (("distal\ndendrites", 2.0), ("proximal\ndendrites", 0.5), ("cell layer,\nhilus side", -0.3)):
            ax.text(-0.2, yy, t_, transform=tr, ha="right", va="center", fontsize=5.4, color=F.INK, clip_on=False)
    if upper:
        ax.set_ylim(-0.6, 3.0)
    else:
        ax.set_ylim(3.0, -0.6)


def story_g():
    fig, y = F.page("Two entorhinal inputs: DS1 puts its current farther out along the dendrites than DS2, and the split blurs with knockout",
                    "STORY 7 \u00b7 DS1 AND DS2", number=9)
    F.legend_mice(fig, 0.55, y + 0.02)
    F.bracket_note(fig, 0.62, y + 0.22)
    y += 0.58
    V = UP["VGRID"]
    recs = {lab: UP["recs"][("v6", lab)] for lab in F.LABS if ("v6", lab) in UP["recs"]}
    typed = [l for l in recs if "c_ds1_upper" in recs[l] and "c_ds2_upper" in recs[l]]
    ptxt = {}
    for blade in ("upper", "lower"):
        c1a = np.array([recs[l]["c_ds1_%s" % blade] for l in typed])
        c2a = np.array([recs[l]["c_ds2_%s" % blade] for l in typed])
        ok = np.isfinite(c1a) & np.isfinite(c2a)
        ptxt[(blade, "all")] = (paired_p(c1a[ok], c2a[ok]), int((c1a[ok] > c2a[ok]).sum()), int(ok.sum()))
    pu, pl = ptxt[("upper", "all")], ptxt[("lower", "all")]
    F.letter(fig, 0.4, y + 0.08, "a", "DS1 puts its current farther out along the dendrites than DS2, in both blades", width=2.9)
    F.letter(fig, 3.35, y + 0.08, "b", "DS1's sink sits farther out than DS2's in %d of %d recordings (upper) and %d of %d (lower)"
             % (pu[1], pu[2], pl[1], pl[2]), width=2.5)
    words = {"upper": "Upper (suprapyramidal) blade", "lower": "Lower (infrapyramidal) blade"}
    for j, blade in enumerate(("upper", "lower")):
        yy = y + 0.62 + j * 2.1
        a = F.axes_in(fig, 1.3, yy, 1.55, 1.6)
        _v_axis(a, upper=(blade == "upper"))
        S1 = np.array([recs[l]["v_ds1_%s" % blade] for l in typed])
        S2 = np.array([recs[l]["v_ds2_%s" % blade] for l in typed])
        for S_, col, word in ((S2, F.C_DS, "DS2"), (S1, F.C_DS1, "DS1")):
            m = np.nanmean(S_, axis=0)
            se = np.nanstd(S_, axis=0, ddof=1) / np.sqrt(np.sum(np.isfinite(S_), axis=0))
            a.fill_betweenx(V, m - se, m + se, color=col, alpha=0.2, lw=0, zorder=3)
            a.plot(m, V, color=col, lw=1.4, label=word, zorder=4)
        pv = np.full(V.size, np.nan)
        for i in range(V.size):
            ok = np.isfinite(S1[:, i]) & np.isfinite(S2[:, i])
            if ok.sum() >= 6 and np.ptp(S1[ok, i] - S2[ok, i]) > 0:
                pv[i] = paired_p(S1[ok, i], S2[ok, i])
        F.sig_bar_y(a, V, pv < 0.05, 1.05, F.INK, lw=2.4)
        a.axvline(0, color=F.FAINT, lw=0.5, zorder=1)
        a.set_title(words[blade], fontsize=6.4, loc="left")
        if j == 1:
            a.set_xlabel("CSD at the DS peak (\u22121 = the recording's\ndeepest DS sink; same for DS1 and DS2)")
            a.legend(frameon=False, fontsize=5.6, loc="lower right")
        else:
            a.set_xticklabels([])
    F.put(fig, 1.3, y + 2.33, "(hilus between the blades)", 1.6, size=5.4, color=F.SOFT)
    F.put(fig, 0.45, y + 5.0, "Depth axis: 0 = the cell-layer current source, 1 = the recording's average DS sink, larger = "
          "farther out along the dendrites. Black bar at the right: depths where DS1 and DS2 differ (paired over %d "
          "recordings, P < 0.05)." % len(typed), 2.6, size=5.4, color=F.SOFT)
    # b: where each type's sink sits, per recording, with paired tests within each group
    groups = ["CTL", "IED-", "IED+"]
    for j, blade in enumerate(("upper", "lower")):
        yy = y + 0.62 + j * 2.1
        a = F.axes_in(fig, 3.75, yy, 1.75, 1.6)
        if blade == "lower":
            a.invert_yaxis()
        allp, vals = [], []
        for gi, g in enumerate(groups):
            labs = [l for l in typed if F.subgroup(l) == g]
            c2 = np.array([recs[l]["c_ds2_%s" % blade] for l in labs])
            c1 = np.array([recs[l]["c_ds1_%s" % blade] for l in labs])
            for l, v2, v1 in zip(labs, c2, c1):
                a.plot([gi - 0.17, gi + 0.17], [v2, v1], color=F.color_of(l), lw=0.7, alpha=0.8, zorder=2)
                a.scatter([gi - 0.17], [v2], s=14, color=F.C_DS, zorder=3, edgecolor="white", lw=0.3, marker=F.marker_of(l))
                a.scatter([gi + 0.17], [v1], s=14, color=F.C_DS1, zorder=3, edgecolor="white", lw=0.3, marker=F.marker_of(l))
            vals += list(c1) + list(c2)
            ok = np.isfinite(c1) & np.isfinite(c2)
            if ok.sum() >= 3:
                p = paired_p(c1[ok], c2[ok])
                allp.append((gi - 0.17, gi + 0.17, p))
                ptxt[(blade, g)] = p
        F.note_y(a, vals)
        F.defer_brackets(a, allp, show_ns=True)
        a.axhline(1, color=F.SOFT, lw=0.5, ls=":", zorder=0)
        a.set_xticks(range(3))
        a.set_xticklabels(["Control", "IED\u2212", "IED+"] if j == 1 else ["", "", ""])
        a.tick_params(axis="x", length=0)
        a.set_xlim(-0.55, 2.55)
        a.set_ylabel("Sink center (0 = cell layer;\nlarger = more distal)", fontsize=5.6)
        a.set_title("%s blade: %s %s over all" % ("Upper" if blade == "upper" else "Lower", F.stars(ptxt[(blade, "all")][0]),
                                                F.pstr(ptxt[(blade, "all")][0])), fontsize=6.0, loc="left")
    W, H = fig.get_size_inches()
    hs = [Line2D([], [], ls="", marker="o", ms=4, mfc=F.C_DS, mec="white", label="DS2 sink"),
          Line2D([], [], ls="", marker="o", ms=4, mfc=F.C_DS1, mec="white", label="DS1 sink"),
          Line2D([], [], color=F.SOFT, lw=0.7, label="one recording")]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(3.7 / W, 1 - (y + 4.85) / H), ncol=3, frameon=False, fontsize=5.6,
               handletextpad=0.3, columnspacing=0.9)
    # c: the split blurs with knockout; d: held-out models
    oe = "structure|overlap_eig2|v6||overlap"
    yc = y + 5.6
    F.letter(fig, 0.4, yc + 0.08, "c", "The DS1/DS2 split fades with knockout inside the PTEN group", width=2.55)
    a = F.axes_in(fig, 0.85, yc + 0.5, 2.05, 1.2)
    F.ko_scatter(a, D.values(oe), ylabel="Second eigenvalue\n(1 = clean split)")
    pe = D.p(oe, "KO_dose_PTEN")
    a.set_title("PTEN \u03c1 %+.2f, %s" % (pe[2], F.pstr(pe[0])), fontsize=5.8, color=F.SOFT, loc="left")
    L = json.load(open(os.path.join(RUNS, "r008", "leaderboard.json")))
    best = {}
    for r in L["rows"]:
        best[r["view"]] = max(best.get(r["view"], 0), r["main"] or 0)
    views = [("everything", "Everything + raw event", True), ("raw_wave", "Raw CSD and LFP", True), ("shape", "Sink shape", True),
             ("context", "Size, theta, timing", False), ("no_shape", "No shape at all", False), ("spectrogram", "Spectrogram", False),
             ("before_after", "Power before and after", False)]
    F.letter(fig, 3.05, yc + 0.08, "d", "Held-out models tell DS1 from DS2 best when they see the sink's shape", width=2.5)
    ax = F.axes_in(fig, 4.3, yc + 0.5, 1.1, 1.2)
    for i, (v, word, shape) in enumerate(views):
        ax.barh(i, best.get(v, np.nan), color=F.C_DS if shape else F.C_DS1, height=0.62)
        ax.text(best.get(v, 0) + 0.005, i, "%.2f" % best.get(v, np.nan), va="center", fontsize=5.2)
    ax.set_yticks(range(len(views)))
    ax.set_yticklabels([w for _v, w, _s in views], fontsize=5.4)
    ax.invert_yaxis()
    ax.set_xlim(0.5, 0.9)
    ax.set_xticks([0.5, 0.7, 0.9])
    ax.set_xlabel("AUC (0.5 = chance)", fontsize=6)
    gap = D.p("structure|overlap_eig2|v6||overlap", "IEDpos_vs_IEDneg")
    textcol(fig, 1.55, [
        ("The claim", "Where a recording splits, the two DS types are the classical ones: DS1 puts its current farther out "
                      "along the granule cells' dendrites (lateral entorhinal input) and DS2 closer in (medial entorhinal "
                      "input), in both blades. As knockout rises the two kinds blur together."),
        ("How to read it", "No layer labels are used. Each blade's dendritic axis comes from the spike itself: 0 is the "
                           "current source at the cell layer (where the dendrites start), 1 is where that recording's "
                           "average DS sink peaks, larger numbers are farther out (distal). Depth runs down the page, so "
                           "the upper blade's dendrites point up from its cell layer and the lower blade's point down. "
                           "a: mean DS1 and DS2 current (\u00b1 SEM), both divided by the same number per recording. "
                           "b: the center of each type's sink, one pair per recording; brackets are paired tests within "
                           "each group. c: the split into two kinds against knockout. d: models trained on other mice; "
                           "blue bars include the sink's shape, orange do not."),
        ("What it shows", "DS1's sink sits farther out than DS2's in the upper blade in %d of %d recordings (%s) and in the "
                          "lower blade in %d of %d (%s). The gap between them is smaller in IED+ than in IED\u2212 mice "
                          "(P 0.035; three IED groups P 0.047). The split falls with knockout inside PTEN (\u03c1 %+.2f, "
                          "%s). Models reach 0.79 with everything and 0.63\u20130.65 without any shape (DS1 come when "
                          "theta is lower, with less gamma at the peak)."
                          % (pu[1], pu[2], F.pstr(pu[0]), pl[1], pl[2], F.pstr(pl[0]), pe[2], F.pstr(pe[0]))),
        ("Why it matters", "The two inputs map onto the grant's object (lateral EC, outer layer) and place (medial EC, "
                           "middle layer) streams; blurring of DS1 and DS2 with knockout is one concrete way the mosaic "
                           "could degrade input separation."),
        ("Caveats", "The names follow the anatomy by construction (DS1 = the type whose sink is farther out, summed over "
                    "both blades), so b describes the split; that the two blades agree is the informative part. The axis "
                    "unit (the average DS sink) is mostly DS2, the larger group. With a low separation index the names are "
                    "arbitrary. No dendritic-spike or behavior link is claimed."),
    ])
    F.save(fig, OUT, "09_story7_DS1_DS2")


# ============================================================================ Story 8: ML
def calls(rid, target):
    """Per-mouse held-out calls of the models at the bar: {lab: array over models}, truth."""
    per, truth = defaultdict(list), {}
    for f in glob.glob(os.path.join(RUNS, rid, "results", "*.json")):
        r = json.load(open(f))
        if r["target"] != target or not r.get("passes"):
            continue
        for c in r["calls"]:
            per[c["lab"]].append(c["call"])
            truth[c["lab"]] = c["truth"]
    return {l: np.array(v) for l, v in per.items()}, truth


def story_h():
    fig, y = F.page("What held-out models see: dentate spikes carry IED status, and they read m7 as IED\u2212, not as high-knockout",
                    "STORY 8 \u00b7 MACHINE LEARNING (ROOM 2.0)", number=10)
    F.legend_mice(fig, 0.55, y + 0.02)
    y += 0.42
    runs = [("r006", "Halo"), ("r007", "Strict"), ("r016", "Halo + raw"), ("r017", "Strict + raw")]
    qs = [("iedpos_vs_iedneg", "IED+ vs IED\u2212"), ("low_vs_high", "Low vs high KO"), ("pten_vs_ctl", "PTEN vs control"),
          ("ied3", "Control / IED\u2212 / IED+"), ("ko_pct", "Knockout % (\u03c1)")]
    best, nuis = {}, {}
    for rid, _w in runs:
        L = json.load(open(os.path.join(RUNS, rid, "leaderboard.json")))
        for r in L["rows"]:
            k = (rid, r["target"])
            best[k] = max(best.get(k, -1), r["main"] or -1)
            if r["view"] == "nuisance":
                nuis[k] = max(nuis.get(k, -1), r["main"] or -1)
    F.letter(fig, 0.4, y + 0.08, "a", "IED status is the most learnable question; PTEN against control barely beats what the "
             "recording year alone gives")
    ax = F.axes_in(fig, 0.8, y + 0.4, 4.6, 1.55)
    cols = ["#5f87c6", "#2f6db5", "#c99be0", "#8e44ad"]
    for i, (q, qw) in enumerate(qs):
        for j, (rid, rw) in enumerate(runs):
            x = i + (j - 1.5) * 0.19
            ax.bar(x, best.get((rid, q), np.nan), width=0.17, color=cols[j], label=rw if i == 0 else None)
            if (rid, q) in nuis:
                ax.plot([x - 0.08, x + 0.08], [nuis[(rid, q)]] * 2, color=F.INK, lw=1.0)
    ax.axhline(0.8, color=F.C_POS, lw=0.7, ls="--")
    ax.text(4.55, 0.805, "bar 0.80", fontsize=5.5, color=F.C_POS, va="bottom", ha="right")
    ax.set_xticks(range(len(qs)))
    ax.set_xticklabels([w for _q, w in qs], fontsize=6.2)
    ax.set_ylim(0.3, 1.0)
    ax.set_ylabel("Best held-out AUC\n(\u03c1 for knockout %)")
    hs, lb = ax.get_legend_handles_labels()
    hs.append(Line2D([], [], color=F.INK, lw=1.0))
    lb.append("nuisance only (year, length, contacts)")
    ax.legend(hs, lb, frameon=False, fontsize=5.6, ncol=5, loc="lower left", bbox_to_anchor=(0.0, 1.0), handlelength=1.5,
              columnspacing=0.9)
    ax.tick_params(axis="x", length=0)
    # b: IED status per held-out mouse against fast power
    ci, _t = calls("r006", "iedpos_vs_iedneg")
    hf = D.values("rootcanal|ds_hf_median|v6||")
    pt = [l for l in F.LABS if F.META[l]["group"] != "CTL"]
    right = sum((np.mean(ci[l]) > 0.5) == (F.subgroup(l) == "IED+") for l in pt)
    miss = [l for l in pt if (np.mean(ci[l]) > 0.5) != (F.subgroup(l) == "IED+")]
    ctl_max = max(hf[l] for l in F.LABS if F.subgroup(l) == "CTL")
    yb = y + 2.75
    F.letter(fig, 0.4, yb + 0.08, "b", "Models name IED status from dentate spikes in %d of %d held-out mice; fast power "
             "catches the one they miss (%s)" % (right, len(pt), ", ".join(miss)), width=2.75)
    a = F.axes_in(fig, 0.85, yb + 0.5, 2.0, 1.75)
    for xx, yy_, t_, ha in ((0.99, 19.6, "IED+ by both", "right"), (0.01, 19.6, "IED+ by fast\npower only", "left"),
                            (0.01, 4.3, "IED− by both", "left")):
        a.text(xx, yy_, t_, fontsize=5.2, color=F.FAINT, ha=ha, va="top" if yy_ > 10 else "bottom", zorder=1)
    for l in pt:
        v = ci[l]
        a.plot([np.percentile(v, 25), np.percentile(v, 75)], [hf[l], hf[l]], color=F.color_of(l), lw=0.9, alpha=0.7, zorder=2)
        F.mouse_dot(a, np.mean(v), hf[l], l)
    F.defer_labels(a, [(np.mean(ci[l]), hf[l]) for l in pt], pt)
    a.axvline(0.5, color=F.SOFT, lw=0.6, ls="--", zorder=1)
    a.axhline(ctl_max, color=F.SOFT, lw=0.6, ls=":", zorder=1)
    a.text(0.62, ctl_max - 0.3, "highest control", fontsize=5.2, color=F.SOFT, va="top")
    a.set_xlim(-0.05, 1.05)
    a.set_ylim(4, 20)
    a.set_xlabel("Held-out call: P(IED+)\n(mean of %d models; line: middle half)" % len(ci[pt[0]]))
    a.set_ylabel("Fast power at the DS (dB)\n(Story 1; not a model input)")
    # c: knockout level per held-out mouse
    ck, _t2 = calls("r006", "low_vs_high")
    F.letter(fig, 3.3, yb + 0.08, "c", "Asked for the knockout level, models call m7 low: its spikes read like the IED\u2212 mice",
             width=2.4)
    a = F.axes_in(fig, 3.95, yb + 0.5, 1.5, 1.75)
    rows = {l: (1 if F.kogroup(l) == "high KO" else 0) for l in pt}
    pts_c = []
    for r_ in (0, 1):
        members = sorted([l for l in pt if rows[l] == r_], key=lambda l: np.mean(ck[l]))
        offs = np.linspace(-0.3, 0.3, len(members)) if len(members) > 1 else [0.0]
        for l, o in zip(members, offs):
            F.mouse_dot(a, np.mean(ck[l]), r_ + o, l)
            pts_c.append((np.mean(ck[l]), r_ + o))
    pt = [l for r_ in (0, 1) for l in sorted([m for m in pt if rows[m] == r_], key=lambda m: np.mean(ck[m]))]
    F.defer_labels(a, pts_c, pt)
    a.axvline(0.5, color=F.SOFT, lw=0.6, ls="--")
    a.set_yticks([0, 1])
    a.set_yticklabels(["Low KO\n(3.9\u20135.2%)", "High KO\n(18.9\u201328.4%)"], fontsize=5.8)
    a.set_ylim(-0.5, 1.5)
    a.set_xlim(-0.05, 1.05)
    a.set_xlabel("Held-out call: P(high knockout)\n(mean of the %d models at the bar)" % len(ck[pt[0]]))
    # d: what the IED models leaned on, and which story each feature belongs to
    L6 = json.load(open(os.path.join(RUNS, "r006", "leaderboard.json")))
    names = {"cen_um": ("Where the sink sits along the dendrites", "Story 7"), "type_ds2": ("Share of DS2 events", "Story 4"),
             "ba_pow_1-4_post_near_shank": ("Slow (1\u20134 Hz) power after the DS, whole shank", "Story 1"),
             "cen_v_upper": ("Upper-blade sink position", "Stories 3, 7"),
             "ba_pow_1-4_post_far_shank": ("Slow power after the DS, later window", "Story 1"),
             "ba_pow_1-4_post_near_u+0.5_+1.0": ("Slow power after, hilus to lower blade", "Story 1"),
             "sink_amp": ("Sink size", "Stories 3, 4"), "blade_balance": ("Blade balance", "Story 3")}
    feats = [(names[f["item"]][0], names[f["item"]][1], f["points"]) for f in L6["most_important"]["iedpos_vs_iedneg"]["features"]
             if f["item"] in names][:8]
    yd = yb + 2.95
    F.letter(fig, 0.4, yd + 0.08, "d", "The IED models lean on the same features the stories found by hand: sink position, "
             "DS2 share, slow power after the DS, sink size and blade balance")
    a = F.axes_in(fig, 2.6, yd + 0.45, 2.3, 1.55)
    for i, (w, sty, v) in enumerate(feats):
        a.barh(i, v, color=F.C_POS, height=0.6)
        a.text(v + 0.01, i, sty, va="center", fontsize=5.4, color=F.SOFT)
    a.set_yticks(range(len(feats)))
    a.set_yticklabels([w for w, _s, _v in feats], fontsize=5.9)
    a.invert_yaxis()
    a.set_xlim(0, 0.8)
    a.set_xlabel("Importance points, summed over the %d models at the bar" % len(L6["most_important"]["iedpos_vs_iedneg"]["models"]))
    p_m7 = np.mean(ci["m7"])
    k_m7, k_m1 = np.mean(ck["m7"]), np.mean(ck["m1"])
    textcol(fig, 1.55, [
        ("The claim", "Models trained on other mice tell a mouse's IED status from its dentate spikes alone, and they read "
                      "m7 as an IED\u2212 mouse, not as a high-knockout one: the signature in the DS follows IED status, as "
                      "Story 1 found by hand. PTEN against control is barely learnable beyond the recording year."),
        ("How to read it", "Each model is trained without one mouse and then asked about it (held out). a: the best "
                           "of 52 to 59 models per question and event set, against a model given only nuisance numbers "
                           "(year, length, bad contacts). b and c: each PTEN mouse's held-out call, averaged over the "
                           "models that reached the bar of 0.80 (Halo set); b sets it against the mouse's DS fast power, "
                           "which no model saw. d: what the IED models used most, with the story that found it."),
        ("What it shows", "IED+ against IED\u2212 reaches 0.95 on all four event sets. Per mouse, %d of %d land on the "
                          "right side of 0.5; the miss is %s, an IED+ mouse called %.2f, whose fast power (%.1f dB) is "
                          "nonetheless above every control. m7 is called IED\u2212 (%.2f) by the IED models and "
                          "low-knockout (%.2f) by the knockout models, which also call m1 (5.2%% knockout) high (%.2f)."
                          % (right, len(pt), ", ".join(miss), np.mean(ci[miss[0]]) if miss else np.nan,
                             hf[miss[0]] if miss else np.nan, p_m7, k_m7, k_m1)),
        ("Why it matters", "An outside check on the hand-built stories: models that knew nothing of our hypotheses chose "
                           "the same features and sided with IED status over the knockout number. Fast power was never an "
                           "input; adding it is the next run, and %s is the test case." % (", ".join(miss) or "m3")),
        ("Caveats", "Sixteen mice; IED status rests on nine held-out PTEN mice and the knockout question on the two "
                    "models that reached the bar. IED+ mice are the high-knockout mice except m7, so m7 is the only mouse "
                    "that separates the two questions."),
    ])
    F.save(fig, OUT, "10_story8_machine_learning")


# ============================================================================ cover / menu
MENU = [
    ("1", "Dose", "Two directions from control", "IED+ DS gain fast (240\u2013420 Hz) power, IED\u2212 DS lose it; m7 (24% KO, no IEDs) "
     "is an outlier for its knockout level, not its IED status.",
     "every IED+ > every control, P 1.9e\u221205; every IED\u2212 < every control, P 0.003", "yes", 3),
    ("2", "Dose", "Graded with knockout", "Six DS features scale with % knockout inside PTEN (sink edge, DS1 return current, DS2 spacing and onset, gamma locking).",
     "\u03c1 0.85\u20130.95, P 5e\u221205\u20130.006", "yes", 4),
    ("3", "Place", "The lower blade", "In IED+ mice the DS balance tips to the infrapyramidal blade, where IEDs start; on one common scale IED\u2212 spikes are half the control size.",
     "blade balance P 0.002; IED\u2212 sinks P 0.012", "yes", 5),
    ("4", "Synchrony", "Uniform, merging events", "DS sizes vary less in IED+, DS1/DS2 blur with knockout, source-sink timing loosens.",
     "every IED+ < every control, P 0.003; \u03c1 \u22120.83, P 0.007", "yes", 6),
    ("5", "BTs", "Borderline transients", "An in-between class, between the DS and IED borders in all three Root Canal numbers: a handful in controls, common in every IED+ mouse, rising with IEDs.",
     "every IED+ > every other mouse, P 0.001", "yes", 7),
    ("6", "DS vs IED", "Same session, same depths", "BTs share the DS's depth footprint but have an IED's speed and fast power; DS and BTs gather in the seconds around IEDs.",
     "fast power BT vs DS P 0.0005 (paired, 5 mice)", "\u2014", 8),
    ("7", "Inputs", "DS1 and DS2", "DS1 sits farther out along the dendrites than DS2 in both blades; the gap narrows in IED+ mice.",
     "14 of 15 recordings, P 0.0009; IED+ vs IED\u2212 P 0.035", "yes", 9),
    ("8", "Models", "What models see", "Held-out models read IED status from DS alone and call m7 IED\u2212, not high-knockout; fast power catches their one miss.",
     "AUC 0.95; 8 of 9 held-out mice", "yes", 10),
]


def cover():
    fig = F.plt.figure(figsize=(8.5, 11))
    F.put(fig, 0.6, 0.6, "BARRY LAB \u00b7 DS PART OF THE SOMATIC-MOSAICISM NARRATIVE \u00b7 FIRST ROUND, 2026-11-23", 7.3, size=7,
          color=F.C_POS, weight="bold")
    h = F.put(fig, 0.6, 0.85, "Dentate spikes across the mosaic: a menu of stories the data support", 7.3, size=19, weight="bold")
    y = 0.85 + h + 0.1
    y += F.put(fig, 0.6, y, "Sixteen mice, one baseline recording each: 7 controls and 9 sparse PTEN knockouts (4 without IEDs, "
               "5 with). Exploratory: one number per mouse, generous tests, no correction. Halo event set, checked on Strict.",
               7.3, size=8.2, color=F.SOFT) + 0.25
    F.letter(fig, 0.45, y + 0.1, "", "The framework the stories hang on: what pushes a dentate network toward hyperexcitability", width=7.4)
    ax = F.axes_in(fig, 0.6, y + 0.3, 7.3, 1.55)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2.1)
    ax.axis("off")
    steps = [("HOW MUCH", "knockout dose", "Stories 1\u20132", "#f3d9e5"), ("WHERE", "the lower blade", "Story 3", "#ecd3e0"),
             ("HOW SYNCHRONIZED", "uniform, merging events", "Story 4", "#e3c2d4"), ("BTs", "borderline transients", "Stories 5\u20136", "#e2d2ee"),
             ("IEDs", "the hand-sorted discharges", "", "#f6d4d4")]
    for i, (big, small, st_, col) in enumerate(steps):
        x0 = 0.05 + i * 2.0
        ax.add_patch(patches.FancyBboxPatch((x0, 0.75), 1.7, 1.15, boxstyle="round,pad=0.02,rounding_size=0.12", color=col, lw=0))
        ax.text(x0 + 0.85, 1.55, big, ha="center", va="center", fontsize=7.5, weight="bold", color=F.INK)
        ax.text(x0 + 0.85, 1.15, small, ha="center", va="center", fontsize=6.3, color=F.INK)
        if st_:
            ax.text(x0 + 0.85, 0.5, st_, ha="center", va="center", fontsize=6.3, color=F.C_POS, weight="bold")
        if i < len(steps) - 1:
            ax.annotate("", xy=(x0 + 1.98, 1.32), xytext=(x0 + 1.72, 1.32), arrowprops=dict(arrowstyle="-|>", color=F.SOFT, lw=1))
    ax.text(5.0, 0.08, "Stories 7 (DS1 and DS2 inputs) and 8 (machine learning) cut across all steps.", ha="center", fontsize=6.3, color=F.SOFT)
    y += 2.05
    F.letter(fig, 0.45, y + 0.1, "", "The narrative in one paragraph", width=7.4)
    y += 0.2 + F.put(fig, 0.6, y + 0.2,
                     "A sparse PTEN knockout changes the dentate gyrus's own population event, the dentate spike, at every "
                     "dose we have. Below the IED threshold (IED\u2212 mice, 4\u20135% knockout) the spikes get quieter: less "
                     "fast-ripple-band power, about half the current, and a calmer slow background. Inside the PTEN group "
                     "several features scale with knockout. Where IEDs appear, three things go together: the spike's current "
                     "tips toward the lower blade (where IEDs start), spikes become uniform and the DS1/DS2 inputs blur "
                     "(hypersynchrony), and an in-between class appears, borderline transients (BTs), with the depth footprint "
                     "of a DS and the speed and fast power of an IED. m7, the one high-knockout mouse without IEDs, behaves like "
                     "the low-knockout mice (an outlier for its knockout level, not for its IED status), and held-out models "
                     "read it the same way: IED status, not knockout alone, sets the direction.", 7.3, size=7.4, color=F.INK) + 0.25
    F.letter(fig, 0.45, y + 0.1, "", "The menu", width=7.4)
    y += 0.3
    cols = [(0.6, 0.35, "#"), (0.95, 0.85, "Step"), (1.8, 1.55, "Story"), (3.35, 2.55, "What we could claim"), (5.9, 1.65, "Best number (uncorrected)"),
            (7.55, 0.45, "Strict"), (7.95, 0.3, "Page")]
    for x, w, t in cols:
        F.put(fig, x, y, t, w, size=6.6, weight="bold", color=F.SOFT)
    y += 0.25
    for row in MENU:
        hs = []
        for (x, w, _t), val in zip(cols, row):
            hs.append(F.put(fig, x, y, str(val), w, size=6.6, color=F.INK, weight="bold" if x in (0.6, 1.8) else "normal"))
        y += max(hs) + 0.1
        fig.add_artist(Line2D([0.6 / 8.5, 8.25 / 8.5], [1 - (y - 0.04) / 11] * 2, color="#e6e8ec", lw=0.6))
    y += 0.15
    F.put(fig, 0.6, y, "Page 11 lists what each story needs from the next batch of mice and corrections to earlier documents "
          "(contact spacing). Tables of every result (about 85,000 tests over three groupings) are in the tables folder.",
          7.3, size=6.6, color=F.SOFT)
    fig.text(0.6 / 8.5, 1 - 10.72 / 11, "DS story menu \u00b7 exploratory, P values uncorrected \u00b7 2026-11-23", fontsize=6.5, color=F.FAINT)
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "1", fontsize=6.5, color=F.FAINT, ha="right")
    F.save(fig, OUT, "01_menu")


# ============================================================================ closing page
def closing():
    fig, y = F.page("Choosing from the menu, and what the next batch has to show", "WHAT NEXT", number=11)
    y += 0.1
    F.put(fig, 0.6, y, "What each story needs from new mice (one planned test each)", 7.3, size=8.5, weight="bold")
    y += 0.3
    items = [
        ("1  Two directions", "Fast power at the DS per mouse in new IED\u2212 and IED+ mice against controls; measure the event "
                              "and baseline windows separately. A second high-knockout mouse without IEDs would show "
                              "whether m7 is a type or a one-off."),
        ("2  Graded with knockout", "Mice between 5% and 19% knockout, to tell a line from a step; the sink's inner edge is "
                                    "the cleanest single measure (r 0.95)."),
        ("3  The lower blade", "Track histology and knockout counts per blade in the same mice; blade balance per mouse; "
                               "absolute CSD size with matched contacts to test the smaller IED\u2212 spikes."),
        ("4  Synchrony", "Sink-size spread and the DS1/DS2 split on every detected DS with one fixed threshold."),
        ("5  BTs", "Freeze the two Root Canal borders as they are today and count BTs per minute in new mice, blind to "
                   "genotype; BT rate is the most direct candidate marker of an IED-prone network."),
        ("6  DS vs IED", "Align on the broadband onset; repeat in the CNO sessions (already in Desktop\\IED DATA) to ask "
                         "whether silencing knockout cells removes BTs along with theta hypersynchrony."),
        ("7  DS1 and DS2", "Report the separation index per recording and let the split be your call; no behavior claim."),
        ("8  Models", "Add fast power to the inputs (m3 is the test case); a model given only the three Root Canal numbers per "
                      "event is the simplest test of Stories 1 and 5 together."),
    ]
    for head, body in items:
        F.put(fig, 0.6, y, head, 1.9, size=7, weight="bold")
        y += max(F.put(fig, 2.55, y, body, 5.4, size=7, color=F.INK), 0.15) + 0.14
    y += 0.2
    F.put(fig, 0.6, y, "If one story has to lead", 7.3, size=8.5, weight="bold")
    y += 0.3
    y += F.put(fig, 0.6, y,
               "Stories 1, 5 and 6 together are the strongest and the most new: the same three Root Canal numbers the lab "
               "already uses to separate DS from IEDs show that IED+ networks push their dentate spikes toward IEDs (more "
               "fast power, and an in-between BT class with an IED's speed), while sub-threshold networks push them the "
               "other way. Stories 2\u20134 then say how (dose, place, synchrony), and Story 8 is an outside check that sides "
               "with IED status. The numbers are complete separations of small groups; the next batch of mice is where each "
               "gets replicated.", 7.3, size=7.2) + 0.3
    F.put(fig, 0.6, y, "Corrections and notes for anyone reusing earlier documents", 7.3, size=8.5, weight="bold")
    y += 0.3
    notes = [
        "Contact spacing: the earlier DS battery converted contacts to \u00b5m at 50 \u00b5m; these H3 recordings are 20 \u00b5m "
        "apart, so every \u00b5m in the archived DS documents is 2.5 times too large (P values and ratios unchanged). Jarvis's own "
        "H3 probe template (backend/probes.py) also says 50 \u00b5m; CSD magnitudes in Jarvis are therefore 6.25 times too "
        "small for these recordings, shapes unchanged.",
        "The old DS3 explanation ('our probe is coarser than Tarcsay et al.') is wrong for the same reason; both are about 20 \u00b5m.",
        "Depth in this menu comes from each recording's own dentate spike (its two sink peaks and the cell-layer sources), "
        "not from the lab's layer labels; earlier documents used the labels.",
        "When CSDs of groups are compared, every mouse is divided by one number (the control average's deepest sink); "
        "within one mouse, classes and types share that mouse's DS scale.",
        "BTs = the Root Canal classes 'inside both borders' and 'extended ambiguous' of the Halo workflow (6fa7fef7b7a3 v5); "
        "IED class = 'inside the IED border' and 'captured by the IED halo'.",
        "Every P here is uncorrected and the smallest of the applicable tests (Mann\u2013Whitney, Welch and Student t; Spearman, "
        "Pearson, Kendall; ANOVA, Kruskal\u2013Wallis, ordered trend; paired t and Wilcoxon), as asked for this exploratory round.",
    ]
    for n_ in notes:
        y += F.put(fig, 0.75, y, "\u2022 " + n_, 7.1, size=6.8, color=F.INK) + 0.1
    F.save(fig, OUT, "11_what_next")


if __name__ == "__main__":
    which = sys.argv[1:] or ["cover", "primer", "g", "h", "closing"]
    for w in which:
        {"cover": cover, "primer": primer, "g": story_g, "h": story_h, "closing": closing}[w]()
