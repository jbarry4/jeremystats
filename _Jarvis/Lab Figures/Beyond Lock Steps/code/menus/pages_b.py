"""Story pages 5-6 of the DS story menu: borderline transients (BTs), and DS vs BT vs IED in the same five IED+
sessions. Round 3, 2026-11-23."""
import json
import os
import pickle
import sys

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patches
from matplotlib.lines import Line2D
from scipy import stats as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import menu_data as D  # noqa: E402
from pages_a import OUT, textcol  # noqa: E402

IEDP = ["m13", "m28", "m3", "m5", "m34"]
PRE = os.path.join(HERE, "out", "prerender")
UP = pickle.load(open(os.path.join(HERE, "uprof.pkl"), "rb"))


# ============================================================================ Story 5
def _hull(name):
    """The applied Root Canal border (grace 5%) as triangles in (log10 amplitude, half-width, fast power)."""
    b = json.load(open(os.path.join(HERE, "rc_borders.json"), encoding="utf-8"))["halo"]["borders"][name]["border"]
    sh = [lv for lv in b["levels"] if abs(lv["grace"] - 0.05) < 1e-9][0]["shape"]
    V = np.asarray(sh["vertices"], float)          # amp, hf, hw
    P = np.column_stack([np.log10(V[:, 0]), V[:, 2], V[:, 1]])
    return [P[list(f)] for f in sh["faces"]]


def _hull_xy(name, i, j):
    """The border's outline in one flat view: the convex hull of its vertices on two of the three numbers
    (columns: 0 = log10 amplitude, 1 = half-width, 2 = fast power)."""
    from scipy.spatial import ConvexHull
    P = np.unique(np.vstack(_hull(name)), axis=0)[:, [i, j]]
    return P[ConvexHull(P).vertices]


def render3d(e, path, w, h, view=(20, -58), hulls=True, big=False):
    """One 3D view drawn in its own figure at its final printed size and saved at 600 dpi (embedded as a picture,
    so the PDF shows exactly this)."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0] if big else [0.0, 0.05, 1.0, 0.95], projection="3d")
    ax.set_proj_type("persp", focal_length=0.65)
    zlo, zhi = -12, 50
    if hulls:
        for name, col, al in (("ds", F.C_DS, 0.07), ("pspike", F.C_IED, 0.11)):
            ax.add_collection3d(Poly3DCollection(_hull(name), facecolor=col, edgecolor="none", linewidths=0, alpha=al))
    for kind, s, al in (("DS", 2.4 if big else 1.4, 0.28), ("far", 7 if big else 3.5, 0.85), ("TZ", 13 if big else 5, 0.95),
                        ("IED", 13 if big else 5, 0.95)):
        q = e[e.kind == kind]
        q = q[np.isfinite(q.amp) & np.isfinite(q.hw) & np.isfinite(q.hf) & (q.hw <= 30)]
        ax.scatter(np.log10(q.amp), q.hw, q.hf, s=s, c=F.KIND_COLOR[kind], alpha=al, linewidths=0, depthshade=False)
        if kind in ("TZ", "IED"):
            ax.scatter(np.log10(q.amp), q.hw, np.full(len(q), zlo), s=2.2 if big else 1.2, c=F.KIND_COLOR[kind], alpha=0.25,
                       linewidths=0, depthshade=False)
    ax.set_xlim(2.0, 3.7)
    ax.set_ylim(2, 30)
    ax.set_zlim(zlo, zhi)
    fs = 6.0 if big else 4.8
    ax.set_xticks([2, 2.5, 3, 3.5] if big else [2, 3])
    ax.set_xticklabels(["100", "316", "1000", "3162"] if big else ["100", "1000"])
    ax.set_yticks([5, 10, 20, 30] if big else [10, 30])
    ax.set_zticks([-10, 0, 10, 20, 30, 40, 50] if big else [0, 25, 50])
    ax.tick_params(labelsize=fs, pad=-1 if big else -3)
    if big:
        ax.set_xlabel("Largest amplitude (µV)", fontsize=6.6, labelpad=-3)
        ax.set_ylabel("Half-width (ms)", fontsize=6.6, labelpad=-3)
        ax.set_zlabel("Fast power (dB)", fontsize=6.6, labelpad=-4)
    else:
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_zlabel("")
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_pane_color((0.975, 0.976, 0.984, 1.0))
        axis._axinfo["grid"]["color"] = (0.86, 0.87, 0.9, 1)
        axis._axinfo["grid"]["linewidth"] = 0.4
    ax.view_init(elev=view[0], azim=view[1])
    ax.set_box_aspect((1.25, 1.0, 0.92), zoom=0.93 if big else 0.9)
    fig.savefig(path, dpi=600, facecolor="white")
    plt.close(fig)


def frame(fig, x, y, w, h, head, sub=""):
    """A light frame with a header naming what the panel shows (in inches from the page's top-left)."""
    W, H = fig.get_size_inches()
    fig.add_artist(patches.FancyBboxPatch((x / W, 1 - (y + h) / H), w / W, h / H, boxstyle="round,pad=0,rounding_size=0.006",
                                          transform=fig.transFigure, facecolor="none", edgecolor="#d5d9e0", lw=0.7, zorder=0))
    fig.text((x + 0.08) / W, 1 - (y + 0.07) / H, head, fontsize=6.6, weight="bold", color=F.INK, va="top", ha="left")
    if sub:
        fig.text((x + 0.08) / W, 1 - (y + 0.21) / H, sub, fontsize=5.7, color=F.SOFT, va="top", ha="left")


def counts(e):
    return "{:,} DS · {:,} BT · {:,} IED".format(int((e.kind == "DS").sum()), int((e.kind == "TZ").sum()), int((e.kind == "IED").sum()))


def story_e():
    fig, y = F.page("Borderline transients (BTs): an in-between kind of event, rare in every control and common in every IED+ mouse",
                    "STORY 5 · FROM DS TOWARD IED · BORDERLINE TRANSIENTS", number=7)
    F.legend_mice(fig, 0.55, y + 0.02)
    F.bracket_note(fig, 0.62, y + 0.22)
    y += 0.58
    os.makedirs(PRE, exist_ok=True)
    rc = D.rc()
    h = rc[(rc.wf == "halo") & (~rc.lab.isin(["m6", "m51"]))]
    grp = {g: h[h.lab.isin([l for l in F.LABS if F.subgroup(l) == g])] for g in ("CTL", "IED-", "IED+")}
    F.letter(fig, 0.4, y + 0.08, "a", "BTs fill the gap between the DS and IED borders, and they appear almost only in IED+ mice")
    ya = y + 0.25
    # a1: the IED+ cloud, large
    render3d(grp["IED+"], os.path.join(PRE, "s5_a1.png"), 3.25, 2.3, big=True)
    frame(fig, 0.42, ya, 3.4, 2.68, "a1   PTEN IED+ mice (5 mice)", counts(grp["IED+"]))
    F.embed_png(fig, 0.5, ya + 0.33, 3.25, 2.3, os.path.join(PRE, "s5_a1.png"))
    # a2, a3: the IED- and control clouds, each in its own frame
    small = [("a2   PTEN IED− mice (4 mice)", counts(grp["IED-"]) + "; axes as in a1", grp["IED-"], "s5_a2.png"),
             ("a3   Control mice (7 mice)", counts(grp["CTL"]) + "; axes as in a1", grp["CTL"], "s5_a3.png")]
    for i, (head, sub, e, fn) in enumerate(small):
        yy = ya + i * 1.37
        render3d(e, os.path.join(PRE, fn), 1.62, 1.0, view=(20, -58), hulls=True)
        frame(fig, 3.95, yy, 1.72, 1.31, head, sub)
        F.embed_png(fig, 4.0, yy + 0.29, 1.62, 1.0, os.path.join(PRE, fn))
    W, H = fig.get_size_inches()
    hs = [Line2D([], [], ls="", marker="o", ms=4, mfc=F.KIND_COLOR[k], mec="none", label=F.KIND_WORD[k]) for k in ("DS", "TZ", "IED", "far")]
    hs += [patches.Patch(facecolor=F.C_DS, alpha=0.25, label="DS border"), patches.Patch(facecolor=F.C_IED, alpha=0.3, label="IED border")]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.5 / W, 1 - (ya + 2.72) / H), ncol=6, frameon=False, fontsize=6.2,
               handletextpad=0.3, columnspacing=1.1)
    # a4-a6: the IED+ cloud flat, two numbers at a time
    yf = ya + 2.98
    frame(fig, 0.42, yf, 5.25, 1.36, "a4–a6   PTEN IED+ mice, the same events seen flat (two numbers at a time; outlines: the borders)")
    e = grp["IED+"]
    cols = {"amp": np.log10(e.amp), "hw": e.hw, "hf": e.hf}
    views = [("amp", "hf", 0, 2, "Largest amplitude (µV)", "Fast power (dB)"),
             ("amp", "hw", 0, 1, "Largest amplitude (µV)", "Half-width (ms)"),
             ("hw", "hf", 1, 2, "Half-width (ms)", "Fast power (dB)")]
    lims = {"amp": (2.0, 3.7), "hw": (2, 30), "hf": (-12, 50)}
    for k, (xa, ya_, i, j, xl, yl) in enumerate(views):
        a = F.axes_in(fig, 0.85 + k * 1.68, yf + 0.28, 1.2, 0.72)
        for name, col, al in (("ds", F.C_DS, 0.10), ("pspike", F.C_IED, 0.14)):
            poly = _hull_xy(name, i, j)
            a.fill(poly[:, 0], poly[:, 1], color=col, alpha=al, lw=0)
            a.plot(np.r_[poly[:, 0], poly[:1, 0]], np.r_[poly[:, 1], poly[:1, 1]], color=col, lw=0.5, alpha=0.7)
        for kind, s_, al in (("DS", 1.3, 0.3), ("TZ", 4.0, 0.9), ("IED", 4.0, 0.9)):
            sel = (e.kind == kind).to_numpy()
            a.scatter(cols[xa][sel], cols[ya_][sel], s=s_, color=F.KIND_COLOR[kind], alpha=al, lw=0, rasterized=True)
        a.set_xlim(*lims[xa])
        a.set_ylim(*lims[ya_])
        if xa == "amp":
            a.set_xticks([2, 2.5, 3, 3.5])
            a.set_xticklabels(["100", "316", "1000", "3162"])
        a.set_xlabel(xl, fontsize=6)
        a.set_ylabel(yl, fontsize=6)
        a.tick_params(labelsize=5.5)
    # b: BTs per minute
    tz = "rootcanal|tz_rate|v6||"
    yb = yf + 1.58
    vtz = D.values("rootcanal|tz_rate|v6||")
    ratio = min(vtz[l] for l in IEDP) / max(vtz[l] for l in F.LABS if l not in IEDP)
    F.letter(fig, 0.4, yb + 0.08, "b", "Every IED+ mouse makes BTs at least %d times as often as any other mouse" % int(np.floor(ratio)))
    F.three_ways(fig, 0.8, yb + 0.5, 4.6, 0.85, D.values(tz), "BTs per minute", names_ied=IEDP)
    # c: BT vs IED share, with its fitted line
    yc = yb + 1.86
    F.letter(fig, 0.4, yc + 0.08, "c", "Mice with more IEDs make more BTs", width=2.4)
    a = F.axes_in(fig, 0.8, yc + 0.42, 1.75, 0.8)
    vt = D.values("rootcanal|tz_share|v6||")
    vi = D.values("rootcanal|ied_share|v6||")
    labs = [l for l in F.LABS if l in vt and l in vi]
    x_ = np.array([vi[l] for l in labs])
    y_ = np.array([vt[l] for l in labs])
    F.fit_line(a, x_, y_, color=F.C_PDS)
    for l in labs:
        F.mouse_dot(a, vi[l], vt[l], l)
    F.defer_labels(a, [(vi[l], vt[l]) for l in IEDP], IEDP)
    r_all = st.pearsonr(x_, y_)
    rho = st.spearmanr(x_, y_)
    a.set_xlabel("IED-class events (% of all events)")
    a.set_ylabel("BTs (% of all events)")
    a.set_title("16 mice: Pearson r %.2f, %s (line: least squares, 95%% band)" % (r_all[0], F.pstr(r_all[1])), fontsize=5.6,
                color=F.SOFT, loc="left")
    a.set_xlim(-0.8, max(x_) * 1.12)
    a.set_ylim(-0.8, max(y_) * 1.15)
    # d: the remaining DS lean toward / away from the IED border
    gb = "rootcanal|ds_gb_median|v6||"
    F.letter(fig, 2.95, yc + 0.08, "d", "The remaining DS sit nearer the IED border in IED+ mice, farther in IED− mice",
             width=2.75)
    b = F.axes_in(fig, 3.35, yc + 0.42, 2.05, 0.8)
    v = D.values(gb)
    g3 = {l: F.subgroup(l) for l in v}
    F.dots(b, v, g3, ["CTL", "IED-", "IED+"], ylabel="Border sizes", xlabels=["Control", "IED−", "IED+"])
    F.defer_brackets(b, F.group_pairs(v, g3, ["CTL", "IED-", "IED+"], F.IED_PAIRS))
    pr, p3 = D.p(tz, "IEDpos_vs_CTL"), D.p(tz, "IED3")
    pg1, pg2 = D.p(gb, "IEDpos_vs_CTL"), D.p(gb, "IEDneg_vs_CTL")
    textcol(fig, 1.55, [
        ("What a BT is", "A borderline transient: an event that passed DS detection but falls between the two Root Canal "
                         "borders, inside both the DS border (drawn around 2,148 control DS) and the IED border (drawn "
                         "around the hand-sorted IEDs), or in the halo zone near both. Formerly the Twilight Zone class. "
                         "Like a borderline blood-pressure reading, one means little; a steady rate of them means "
                         "something. BTs are left out of the Halo and Strict DS sets."),
        ("How to read it", "a: one dot per event in the space of the three numbers the borders use: largest amplitude "
                           "(10–150 Hz, log scale), half-width, and fast power (240–420 Hz over its own "
                           "baseline). Each frame names its mice; the shaded solids are the borders as applied (5% "
                           "grace), and BTs and IEDs cast a faint shadow on the floor. a4–a6 show the a1 events "
                           "flat. b: BTs per minute, one dot per mouse, three groupings. c: BT and IED-class shares per "
                           "mouse with the least-squares line and its 95% band. d: for the DS that remain, how far each "
                           "sits from the IED border in units of that border's own size; median per mouse."),
        ("What it shows", "BTs: 0.56 to 1.89 per minute in every IED+ mouse; at most 0.075 in any control or IED− "
                          "mouse, and none in m7 (IED+ against control %s; three IED groups %s). In a, BTs fill the gap "
                          "where the two borders meet: shorter half-width and higher fast power than DS; the IED− and "
                          "control clouds (a2, a3) barely reach it. BTs and IEDs rise together across mice (c; Spearman "
                          "ρ %.2f). The remaining DS of IED+ mice sit nearer the IED border (%s) and those of "
                          "IED− mice farther from it (%s)."
                          % (F.pstr(pr[0]), F.pstr(p3[0]), rho[0], F.pstr(pg1[0]), F.pstr(pg2[0]))),
        ("Why it matters", "Controls have a handful; every IED+ mouse has at least seven times the highest control rate. "
                           "Between DS and IEDs there is a third group that is common only where IEDs exist, which is what "
                           "a continuum from DS to IED would look like, and it makes the BT rate a candidate marker for an "
                           "IED-prone network."),
        ("Caveats", "The borders were drawn on these same recordings (controls for the DS border, IED+ mice for the "
                    "IED border), so BT counts are defined by them. Per-mouse rates rest on 12 to 59 events."),
        ("To replicate", "Apply the same two borders, frozen, to new mice and count BTs per minute blind to genotype."),
    ])
    F.save(fig, OUT, "07_story5_borderline_transients")


# ============================================================================ Story 6
def paired_p(a, b):
    """Generous paired P: the smaller of the paired t-test and Wilcoxon's signed-rank test."""
    ps = [st.ttest_rel(a, b).pvalue]
    try:
        ps.append(st.wilcoxon(a, b).pvalue)
    except ValueError:
        pass
    return float(np.nanmin(ps))


def story_f():
    fig, y = F.page("Same session, same depths: BTs have the footprint of a dentate spike and the speed and fast power of an IED",
                    "STORY 6 · DS, BTs AND IEDs IN THE SAME FIVE IED+ RECORDINGS", number=8)
    S = D.dsied()
    G, R = S["UGRID"], S["regions"]
    y += 0.2
    ylo, yhi = -1.0, 1.85
    kinds = [("DS", "Dentate spikes"), ("TZ", "Borderline transients"), ("IED", "IEDs")]
    # a: grand-average CSD, depth registered on each mouse's own DS
    F.letter(fig, 0.4, y + 0.08, "a", "BTs and IEDs put their current at the same depths as dentate spikes, only stronger")
    T = S["m13"]["t_ms"]
    tw = (T >= -25) & (T <= 25)
    grand = {k: np.nanmean([S[l]["classes"][k]["u_wide"][:, tw] for l in IEDP if k in S[l]["classes"]], axis=0) for k, _w in kinds}
    inr = (G >= ylo) & (G <= yhi)
    vmax = np.nanpercentile(np.abs(np.concatenate([g[inr].ravel() for g in grand.values()])), 98)
    for j, (k, word) in enumerate(kinds):
        a = F.axes_in(fig, 1.55 + j * 1.2, y + 0.5, 1.05, 2.05)
        im = a.imshow(grand[k], aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax, origin="upper",
                      extent=[T[tw][0], T[tw][-1], G[-1], G[0]], interpolation="bilinear")
        a.set_ylim(yhi, ylo)
        F.shade_regions(a, R, labels=(j == 0), lines=False, shade=False)
        for v_ in (R["top"], 0.0, R["gu"], R["gl"], 1.0, R["bot"]):
            a.axhline(v_, color="white", lw=0.5, alpha=0.8)
        a.set_xlabel("Time from the peak (ms)")
        n_ev = sum(S[l]["classes"][k]["n"] for l in IEDP if k in S[l]["classes"])
        a.set_title("%s\n(%s events)" % (word, "{:,}".format(n_ev)), fontsize=6.4, loc="left", color=F.KIND_COLOR[k])
    cb = F.axes_in(fig, 5.2, y + 0.7, 0.07, 1.4)
    c = plt.colorbar(im, cax=cb)
    c.ax.tick_params(labelsize=5.3)
    c.set_label("CSD over the mouse's DS\ndeepest sink (blue sink, red source)", fontsize=5.3)
    # b: profile at the peak
    yb = y + 3.3
    F.letter(fig, 0.4, yb + 0.08, "b", "At the peak all three share the DS depth profile; BTs and IEDs are larger", width=2.35)
    a = F.axes_in(fig, 1.55, yb + 0.45, 1.15, 1.95)
    a.set_ylim(yhi, ylo)
    F.shade_regions(a, R, labels=True)
    for k, word in kinds:
        stack = np.array([S[l]["classes"][k]["u_peak"] for l in IEDP if k in S[l]["classes"]])
        m = np.nanmean(stack, axis=0)
        se = np.nanstd(stack, axis=0, ddof=1) / np.sqrt(np.sum(np.isfinite(stack), axis=0))
        a.fill_betweenx(G, m - se, m + se, color=F.KIND_COLOR[k], alpha=0.16, lw=0, zorder=3)
        a.plot(m, G, color=F.KIND_COLOR[k], lw=1.3, label=F.KIND_WORD[k], zorder=4)
    a.axvline(0, color=F.FAINT, lw=0.5)
    a.set_ylim(yhi, ylo)
    a.set_xlabel("CSD (−1 = the mouse's\nDS deepest sink)")
    a.legend(frameon=False, fontsize=5.6, loc="lower left")
    # c: fast power along the same depth axis
    F.letter(fig, 2.85, yb + 0.08, "c", "Fast power: DS < BT < IED at every depth", width=1.3)
    b = F.axes_in(fig, 2.95, yb + 0.45, 1.0, 1.95)
    b.set_ylim(yhi, ylo)
    F.shade_regions(b, R, labels=False)
    for k, word in kinds:
        stack = np.array([S[l]["classes"][k]["u_hf"] for l in IEDP if k in S[l]["classes"]])
        m = np.nanmean(stack, axis=0)
        se = np.nanstd(stack, axis=0, ddof=1) / np.sqrt(np.sum(np.isfinite(stack), axis=0))
        b.fill_betweenx(G, m - se, m + se, color=F.KIND_COLOR[k], alpha=0.16, lw=0, zorder=3)
        b.plot(m, G, color=F.KIND_COLOR[k], lw=1.3, zorder=4)
    b.set_ylim(yhi, ylo)
    b.set_xlabel("240–420 Hz power\n(dB over 100 ms before)")
    # d: per-mouse medians DS -> BT -> IED, paired brackets
    F.letter(fig, 4.2, yb + 0.08, "d", "In every mouse, BT fast power lies between DS and IED", width=1.5)
    feats = [("hf_rc", "Fast power (dB)"), ("hw", "Half-width (ms)"), ("sink_rel", "Deepest sink\n(DS mean = 1)")]
    stats_txt = []
    for j, (col, word) in enumerate(feats):
        a = F.axes_in(fig, 4.6, yb + 0.45 + j * 0.74, 0.95, 0.58)
        M = np.array([[S[lab]["events"][S[lab]["events"].kind == k][col].median() for k in ("DS", "TZ", "IED")] for lab in IEDP])
        for row in M:
            a.plot([0, 1, 2], row, color=F.C_POS, lw=0.6, alpha=0.55, marker="o", ms=1.8, zorder=2)
        mu = M.mean(axis=0)
        se = M.std(axis=0, ddof=1) / np.sqrt(M.shape[0])
        a.fill_between([0, 1, 2], mu - se, mu + se, color=F.INK, alpha=0.12, lw=0, zorder=1)
        a.plot([0, 1, 2], mu, color=F.INK, lw=1.3, zorder=3)
        F.note_y(a, M)
        pairs = [(0, 1, paired_p(M[:, 1], M[:, 0])), (1, 2, paired_p(M[:, 2], M[:, 1])), (0, 2, paired_p(M[:, 2], M[:, 0]))]
        F.defer_brackets(a, pairs)
        stats_txt.append((word.split("\n")[0], M, pairs))
        a.set_xticks([0, 1, 2])
        a.set_xticklabels(["DS", "BT", "IED"] if j == 2 else ["", "", ""], fontsize=6)
        a.set_xlim(-0.35, 2.35)
        a.set_ylabel(word, fontsize=5.6)
        a.tick_params(labelsize=5.5)
    # e: timing against IEDs
    TM = pickle.load(open(os.path.join(HERE, "timing.pkl"), "rb"))
    Wn = TM["windows"]
    ye = yb + 2.95
    F.letter(fig, 0.4, ye + 0.08, "e", "DS and BTs gather in the seconds around IEDs, more than chance timing would give")
    for j, (k, word) in enumerate((("DS", "Dentate spikes"), ("TZ", "Borderline transients"))):
        a = F.axes_in(fig, 0.8 + j * 2.45, ye + 0.5, 2.05, 1.3)
        P = TM["pooled"][k]
        a.fill_between(Wn, P["chance_lo"], P["chance_hi"], color="#b9bec8", alpha=0.45, lw=0, zorder=1)
        a.fill_between(Wn, P["boot_lo"], P["boot_hi"], color=F.KIND_COLOR[k], alpha=0.18, lw=0, zorder=3)
        a.plot(Wn, P["ratio"], color=F.KIND_COLOR[k], lw=1.8, marker="o", ms=3, zorder=4)
        a.axhline(1, color=F.INK, lw=0.6, ls="--", zorder=2)
        F.sig_bar_x(a, Wn, P["p"] < 0.05, 0.96, F.KIND_COLOR[k], lw=3.0, log=True)
        a.set_xscale("log")
        a.set_xticks([0.25, 1, 5, 20, 60])
        a.set_xticklabels(["0.25", "1", "5", "20", "60"])
        a.set_xlim(0.2, 80)
        a.set_ylim(0, 3.5)
        a.set_xlabel("Window around the nearest IED (s)")
        a.set_ylabel("Observed / chance" if j == 0 else "")
        a.set_title("%s (%s events)" % (word, "{:,}".format(P["n"])), fontsize=6.4, loc="left", color=F.KIND_COLOR[k], pad=8)
    W, H = fig.get_size_inches()
    hs = [Line2D([], [], color=F.SOFT, lw=1.8, marker="o", ms=3, label="all five mice (band: 95%, mice drawn again)"),
          patches.Patch(facecolor="#b9bec8", alpha=0.6, label="chance: 95% of 1,000 random shifts"),
          Line2D([], [], color=F.SOFT, lw=3.0, label="bar: P < 0.05, all five mice")]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.75 / W, 1 - (ye + 2.3) / H), ncol=3, frameon=False, fontsize=5.8,
               handletextpad=0.4, columnspacing=1.2)
    hf, hw = stats_txt[0], stats_txt[1]
    Pd, Pt = TM["pooled"]["DS"], TM["pooled"]["TZ"]
    sig_d = Wn[Pd["p"] < 0.05]
    sig_t = Wn[Pt["p"] < 0.05]
    textcol(fig, 1.55, [
        ("The claim", "Read through one pipeline in the same five sessions, BTs put their current at the same depths as "
                      "dentate spikes and as IEDs, but they are as brief and as large as IEDs, and their fast power sits "
                      "between the two. DS and BTs both come more often in the seconds around IEDs."),
        ("How to read it", "a: the average current source density of each class. Depth comes from each mouse's own DS "
                           "(0 = its upper-blade sink peak, 1 = its lower-blade sink peak; regions as in Story 3), and "
                           "every class of a mouse is divided by the same number, that mouse's DS deepest sink, before "
                           "the five mice are averaged; 20 µm contacts. b and c: the same at the peak, and the "
                           "240–420 Hz power by depth (mean ± SEM over the five mice). d: the median per mouse "
                           "for each class; thin lines join one mouse, the thick line is their mean (± SEM); "
                           "brackets are paired tests over the five mice. e: how many events fall within a window of the "
                           "nearest IED, over how many would at random times in the same session (1,000 shifts)."),
        ("What it shows", "Fast power: DS %.0f–%.0f dB, BT %.0f–%.0f, IED %.0f–%.0f (BT vs DS %s; IED vs "
                          "BT %s). Half-width: BTs as brief as IEDs (BT vs DS %s). The depth pattern (b) is shared by all "
                          "three. In time (e), DS are %.1f to %.1f times as common as chance within %s to %s s of an IED "
                          "(P ≤ %s); BTs %.1f to %.1f times within %s to %s s (P %s to %s). m28's 44 BTs have none "
                          "within 1 s of an IED (1.7 expected) but 29 within 20 s (21 expected)."
                          % (np.min(hf[1][:, 0]), np.max(hf[1][:, 0]), np.min(hf[1][:, 1]), np.max(hf[1][:, 1]),
                             np.min(hf[1][:, 2]), np.max(hf[1][:, 2]), F.pstr(hf[2][0][2]), F.pstr(hf[2][1][2]),
                             F.pstr(hw[2][0][2]), np.min(Pd["ratio"][Pd["p"] < 0.05]), np.max(Pd["ratio"][Pd["p"] < 0.05]),
                             "%g" % sig_d.min(), "%g" % sig_d.max(), F.pnum(np.max(Pd["p"][Pd["p"] < 0.05])),
                             np.min(Pt["ratio"][Pt["p"] < 0.05]), np.max(Pt["ratio"][Pt["p"] < 0.05]), "%g" % sig_t.min(),
                             "%g" % sig_t.max(), F.pnum(np.min(Pt["p"][Pt["p"] < 0.05])), F.pnum(np.max(Pt["p"][Pt["p"] < 0.05])))),
        ("Why it matters", "This is the lab's 'dentate spike versus IED' question in the same sessions. BTs look like "
                           "dentate spikes in where their current goes and like IEDs in how fast and how high-frequency it "
                           "is: an exaggerated DS, rather than a separate generator, is the simpler reading here."),
        ("Caveats", "Windows are aligned on each event's 5–100 Hz current peak, which blurs the first millisecond "
                    "where the old IED analysis saw initiation at the hilus and lower blade. Five mice; m3's IED class has "
                    "7 events. BT timing rests on 174 events, so short windows are noisy."),
        ("To replicate", "Align on the broadband onset and repeat in new IED+ mice; add CNO sessions (already read "
                         "in Desktop\\IED DATA)."),
    ])
    F.save(fig, OUT, "08_story6_DS_BT_IED_same_session")


if __name__ == "__main__":
    which = sys.argv[1:] or ["e", "f"]
    for w in which:
        {"e": story_e, "f": story_f}[w]()
