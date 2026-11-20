"""Rain's figure, versions 1.1 and 2.1 (the engine; run make_rain_figure_v1_1.py
or make_rain_figure_v2_1.py). Same data and events as versions 1 and 2, with
Rain's feedback of 2026-11-19:

  * cell layers beside every depth axis (estimates; sources in LAYER_SOURCE),
  * a tighter layout (less dead space between panels),
  * the probe pitch corrected: the PTEN recordings are on an H3 (64 contacts,
    20 um apart), so the even contacts are 40 um apart, not 100. This rescales
    the CSD values (mV/mm2) by 6.25; the pictures themselves do not change.

Every raster element (CSD images, spectrograms) is written into the PDF at
600 dpi; lines and text stay vector. Each panel is also saved alone (PDF + 600
dpi PNG) under Individual panels/<OUT_STEM>/, with the crop boxes in
_crops.json so make_info_pdf.py can lay the panels into the info PDF.
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402
from matplotlib.transforms import Bbox, ScaledTranslation  # noqa: E402

import make_rain_figure as M  # noqa: E402  (reader, filters, wavelets, the v1 data choices)

HERE = M.HERE
EVEN = M.EVEN
FS = M.FS
PITCH_MM = 0.020            # H3: 64 contacts, 20 um apart
H_MM = 2 * PITCH_MM         # even contacts only -> 40 um
W_MM, H_FIG = 180.0, 193.0
CSD_CMAP = "RdBu_r"
SPEC_CMAP = M.SPEC_CMAP
SPEC_COLORS = M.SPEC_COLORS
OUT_STEM = "Rain_Figure_v1.1"
LAYER_INK = "#444444"

# Cell layers, as (name, first channel, last channel) down the probe (CSC1 = top).
# OML and MML are drawn together as ML; the first GCL/ML below the hilus are the
# upper blade's, the second the lower blade's.
LAYERS = {
    "CTL": [("SO", 1, 12), ("SP", 13, 17), ("SR", 18, 23), ("SLM", 24, 27), ("ML", 28, 41), ("GCL", 42, 49),
            ("HIL", 50, 55), ("GCL", 56, 60), ("ML", 61, 64)],
    "PTEN": [("SO", 1, 11), ("SP", 12, 16), ("SR", 17, 25), ("SLM", 26, 30), ("ML", 31, 40), ("GCL", 41, 44),
             ("HIL", 45, 48), ("GCL", 49, 54), ("ML", 55, 64)],
    "DKO": [("SO", 1, 3), ("SP", 4, 8), ("SR", 9, 17), ("SLM", 18, 22), ("ML", 23, 29), ("GCL", 30, 35),
            ("HIL", 36, 49), ("GCL", 50, 53), ("ML", 54, 64)],
    "ds": [("SO", 1, 1), ("SP", 2, 7), ("SR", 8, 20), ("SLM", 21, 25), ("ML", 26, 32), ("GCL", 33, 38),
           ("HIL", 39, 52), ("GCL", 53, 56), ("ML", 57, 64)],
    "ied": [("SO", 1, 7), ("SP", 8, 12), ("SR", 13, 21), ("SLM", 22, 28), ("ML", 29, 33), ("GCL", 34, 40),
            ("HIL", 41, 44), ("GCL", 45, 51), ("ML", 52, 64)],
}
LAYER_SOURCE = {
    "CTL": "CTL m6 s4: Jarvis layer record, StrataScope-reviewed",
    "PTEN": "PTEN m13 s1: estimated. No record for this session; the lab's labels for m13 s2 (same day, 34 min "
            "later) moved 11 contacts deeper, because the theta profile puts every landmark 10-12 contacts deeper "
            "in s1 than in s2 (fissure theta peak Ch 28 vs 16; hilar peak Ch 50 vs 40)",
    "DKO": "DKO m41 s1: the lab's layer sheet (Jarvis layer record)",
    "ds": "CTL m59 s4: the lab's layer sheet (Jarvis layer record)",
    "ied": "PTEN m34 s5: Jarvis layer record, StrataScope-reviewed",
}
CA1 = {"SO", "SP", "SR", "SLM"}

plt.rcParams.update({"savefig.dpi": 600})


def csd(V):
    """-d2V/dz2 over the even contacts (40 um), ends duplicated (Vaknin et al.
    1988); uV in, mV/mm2 out. Sink < 0."""
    P = np.vstack([V[:1], V, V[-1:]])
    return -(P[2:] - 2 * P[1:-1] + P[:-2]) / H_MM ** 2 / 1000.0


def ax_mm(fig, x, y, w, h):
    return fig.add_axes([x / W_MM, 1 - (y + h) / H_FIG, w / W_MM, h / H_FIG])


def letter(fig, x, y, s):
    return fig.text(x / W_MM, 1 - y / H_FIG, s, fontsize=9, fontweight="bold", va="top", ha="left")


def cbar(fig, im, x, y, w, h, label, ticks=None):
    cb = fig.colorbar(im, cax=ax_mm(fig, x, y, w, h), ticks=ticks)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(width=0.4, length=1.5, labelsize=5.5, pad=1)
    cb.set_label(label, fontsize=6, labelpad=2)
    return cb


def layer_rows(key):
    """[(name, first row, last row)] in even-contact rows (row i = CSC EVEN[i])."""
    out = []
    for name, a, b in LAYERS[key]:
        rows = [i for i, c in enumerate(EVEN) if a <= c <= b]
        if rows:
            out.append((name, rows[0], rows[-1]))
    return out


def layer_at(key, ch):
    return next(n for n, a, b in LAYERS[key] if a <= ch <= b)


def chan_ticks(ax):
    """Even channel numbers next to the depth axis, "Ch" above them."""
    show = [2, 16, 32, 48, 64]
    ax.set_yticks([EVEN.index(c) for c in show])
    ax.set_yticklabels([str(c) for c in show], fontsize=5)
    ax.tick_params(axis="y", length=1.5, pad=0.8, width=0.4)
    ax.spines["left"].set_visible(True)
    ax.text(-0.012, -0.8, "Ch", transform=ax.get_yaxis_transform(), ha="right", va="bottom", fontsize=5)


def draw_layers(fig, ax, key, off_mm):
    """Layer brackets and names left of the axis (off_mm from the spine), with
    CA1 / DG further out. Nothing is drawn over the data."""
    base = ax.get_yaxis_transform()

    def at(dx):
        return base + ScaledTranslation(-dx / 25.4, 0, fig.dpi_scale_trans)
    g = 0.14
    R = layer_rows(key)
    for name, a, b in R:
        ax.plot([0, 0], [a - 0.5 + g, b + 0.5 - g], transform=at(off_mm), color=LAYER_INK, lw=0.6,
                clip_on=False, solid_capstyle="butt")
        ax.text(0, (a + b) / 2.0, name, transform=at(off_mm + 0.5), ha="right", va="center", fontsize=4.8,
                color=LAYER_INK)
    for region, members in (("CA1", [r for r in R if r[0] in CA1]), ("DG", [r for r in R if r[0] not in CA1])):
        if not members:
            continue
        a, b = members[0][1], members[-1][2]
        ax.plot([0, 0], [a - 0.5 + g, b + 0.5 - g], transform=at(off_mm + 4.3), color=LAYER_INK, lw=0.6,
                clip_on=False, solid_capstyle="butt")
        ax.text(0, (a + b) / 2.0, region, transform=at(off_mm + 4.7), ha="right", va="center", fontsize=5.5,
                rotation=90, color=LAYER_INK)


def export_panels(fig, groups, pad_in=0.03):
    out = os.path.join(HERE, "Individual panels", OUT_STEM)
    os.makedirs(out, exist_ok=True)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    crops = []
    for name, arts in groups:               # every crop measured before anything is hidden
        boxes = [a.get_tightbbox(r) if hasattr(a, "get_tightbbox") else a.get_window_extent(r) for a in arts]
        bb = Bbox.union([b for b in boxes if b is not None]).transformed(fig.dpi_scale_trans.inverted())
        crops.append((name, arts, Bbox.from_extents(bb.x0 - pad_in, bb.y0 - pad_in, bb.x1 + pad_in, bb.y1 + pad_in)))
    for name, arts, bb in crops:
        # only this panel's own artists are drawn, so a neighbor's edge or
        # letter never bleeds into the crop and the PDF holds only its images
        for t in list(fig.texts) + list(fig.axes):
            t.set_visible(any(t is a for a in arts))
        for ext, kw in ((".pdf", {}), (".png", {"dpi": 600})):
            fig.savefig(os.path.join(out, name + ext), bbox_inches=bb, **kw)
    for t in list(fig.texts) + list(fig.axes):
        t.set_visible(True)
    w, h = fig.get_size_inches()
    with open(os.path.join(out, "_crops.json"), "w", encoding="utf8") as f:
        json.dump({"figure": OUT_STEM + ".pdf", "fig_in": [w, h],
                   "panels": {n: [bb.x0, bb.y0, bb.x1, bb.y1] for n, _a, bb in crops}}, f, indent=1)
    print("panels:", out, len(groups))


def main():
    fig = plt.figure(figsize=(W_MM / 25.4, H_FIG / 25.4))
    notes, groups = [], []

    # a: theta CSDs ---------------------------------------------------------
    TH = []
    for name, folder, (s0, s1), bad in M.THETA:
        X, t0 = M.read(folder, s0 - M.PAD, s1 + M.PAD)
        V = M.evens(M.band(M.notch(X), 4.0, 12.0), bad)
        C = csd(V)
        t = t0 + np.arange(X.shape[1]) / FS
        w = (t >= s0) & (t < s1)
        TH.append((name, t[w] - s0, V[:, w], C[:, w]))
    clim = np.percentile(np.abs(np.concatenate([c.ravel() for *_x, c in TH])), 99.0)
    vs = np.percentile(np.abs(np.concatenate([v.ravel() for _n, _t, v, _c in TH])), 99.0)
    y_a, h_a, w_a = 7.0, 50.0, 44.0
    xs = [17.0, 69.0, 121.0]
    for (name, tt, V, C), x in zip(TH, xs):
        ax = ax_mm(fig, x, y_a, w_a, h_a)
        im = ax.imshow(C, aspect="auto", cmap=CSD_CMAP, vmin=-clim, vmax=clim, interpolation="bilinear",
                       extent=[tt[0], tt[-1], len(EVEN) - 0.5, -0.5])
        for i in range(len(EVEN)):
            ax.plot(tt, i - 0.9 * V[i] / vs, color="k", lw=0.25)
        ax.set_xlim(0, 6)
        ax.set_ylim(len(EVEN) - 0.5, -1.0)
        ax.set_title(name, fontsize=7.5, fontweight="bold", pad=3)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_xticks(range(7))
        ax.set_xlabel("Time (s)", labelpad=1)
        if x == xs[0]:
            chan_ticks(ax)
            draw_layers(fig, ax, name, 3.4)
        else:
            draw_layers(fig, ax, name, 0.8)
        groups.append(("a_Theta_%s" % name, [ax]))
    th_ticks = [v for v in MaxNLocator(5, symmetric=True, integer=True).tick_values(-clim, clim) if abs(v) <= clim]
    cb = cbar(fig, im, 170.0, y_a + 8, 1.5, h_a - 16, "CSD (mV/mm²)", ticks=th_ticks)
    t1 = fig.text(170.75 / W_MM, 1 - (y_a + 6.8) / H_FIG, "source", fontsize=5.5, ha="center", va="bottom",
                  color="#b2182b")
    t2 = fig.text(170.75 / W_MM, 1 - (y_a + h_a - 7.2) / H_FIG, "sink", fontsize=5.5, ha="center", va="top",
                  color="#2166ac")
    groups.append(("a_Theta_colorbar", [cb.ax, t1, t2]))
    groups.append(("a_Theta_all", [g for _n, gs in groups for g in gs]))
    letter(fig, 2, 2.5, "a")
    notes.append("a  theta 4-12 Hz CSD, shared color scale +-%.3g mV/mm2 (99th percentile of |CSD| over the three "
                 "windows); trace scale: %.0f uV = 0.9 contact spacing" % (clim, vs))

    # b, c: events -----------------------------------------------------------
    freqs = np.geomspace(1.0, 800.0, 90)
    rows = [("b", "Control dentate spike", M.DS, "ds", 75.0),
            ("c", "PTEN interictal epileptiform discharge (IED)", M.IED, "ied", 139.0)]
    for lt, title, E, kind, y0 in rows:
        X, t0 = M.read(E["folder"], E["t"] - M.PAD, E["t"] + M.PAD)
        Xn = M.notch(X)
        t = t0 + np.arange(X.shape[1]) / FS - E["t"]
        w = (t >= -E["half"]) & (t <= E["half"])
        tm = t[w] * 1000.0
        if kind == "ds":
            V = M.evens(M.band(Xn, 5.0, 100.0), E["bad"])[:, w]
            filt_txt = "5–100 Hz, 60 Hz notch"
        else:
            V = M.evens(Xn, E["bad"])[:, w]
            V = V - np.median(V[:, tm < -60], axis=1, keepdims=True)
            filt_txt = "unfiltered, 60 Hz notch"
        C = csd(V)
        h = 46.0
        letter(fig, 2, y0 - 7.0, lt)
        head = fig.text(8 / W_MM, 1 - (y0 - 6.8) / H_FIG, "%s  (%s)" % (title, filt_txt), fontsize=6.5, va="top")

        # voltage: rows line up with the CSD's, so the layer column serves both
        ax = ax_mm(fig, 10, y0, 34, h)
        gain = np.percentile(np.abs(V), 99.5)
        for i in range(len(EVEN)):
            ax.plot(tm, i - 1.6 * V[i] / gain, color="k", lw=0.35, clip_on=False)
        ax.set_xlim(tm[0], tm[-1])
        ax.set_ylim(len(EVEN) - 0.5, -0.5)
        M.bare(ax)
        for c, col in zip(E["spec"], SPEC_COLORS):
            ax.plot(tm[0] - 6, EVEN.index(c), marker=">", ms=3, color=col, clip_on=False, mec="none")
        sb = 1000.0 if kind == "ds" else 2000.0
        x_sb = tm[0] - 16
        y_top = len(EVEN) - 1 - 1.6 * sb / gain
        ax.plot([x_sb, x_sb], [len(EVEN) - 1, y_top], color="k", lw=0.8, clip_on=False)
        ax.text(x_sb - 3, len(EVEN) - 1 - 0.8 * sb / gain, "%g mV" % (sb / 1000), rotation=90, va="center",
                ha="right", fontsize=6)
        ax.plot([tm[-1] - 50, tm[-1]], [len(EVEN) + 0.4] * 2, color="k", lw=0.8, clip_on=False)
        ax.text(tm[-1] - 25, len(EVEN) + 0.9, "50 ms", ha="center", va="top", fontsize=6)
        ax.set_title("Voltage", fontsize=6.5, pad=2)
        groups.append(("%s_%s_Voltage" % (lt, kind.upper()), [ax]))

        # CSD, with channel numbers and the layer column on its left
        ax = ax_mm(fig, 56.5, y0, 38, h)
        cl = np.percentile(np.abs(C), 99.5)
        im = ax.imshow(C, aspect="auto", cmap=CSD_CMAP, vmin=-cl, vmax=cl, interpolation="bilinear",
                       extent=[tm[0], tm[-1], len(EVEN) - 0.5, -0.5])
        ax.set_ylim(len(EVEN) - 0.5, -0.5)
        chan_ticks(ax)
        draw_layers(fig, ax, kind, 3.4)
        ax.set_xticks([-150, -100, -50, 0, 50, 100, 150])
        ax.set_xticklabels(["−150", "", "−50", "0", "50", "", "150"])
        ax.set_xlabel("Time (ms)", labelpad=1)
        ax.set_title("CSD", fontsize=6.5, pad=2)
        cb_ticks = [v for v in MaxNLocator(5, symmetric=True).tick_values(-cl, cl) if abs(v) <= cl]
        cb = cbar(fig, im, 96.0, y0 + 6, 1.5, h - 12, "CSD (mV/mm²)", ticks=cb_ticks)
        groups.append(("%s_%s_CSD" % (lt, kind.upper()), [ax, cb.ax]))

        # spectrograms: 4 contacts, top to bottom in depth order
        raw = M.evens(Xn, E["bad"])
        sh = (h - 3 * 1.2) / 4
        spec_axes = []
        for j, (c, col) in enumerate(zip(E["spec"], SPEC_COLORS)):
            S = M.morlet_db(raw[EVEN.index(c)], freqs, w)
            ax = ax_mm(fig, 116.0, y0 + j * (sh + 1.2), 44.0, sh)
            spec_axes.append(ax)
            im = ax.pcolormesh(tm, freqs, S, cmap=SPEC_CMAP, vmin=-6, vmax=E["db_max"], shading="gouraud",
                               rasterized=True)
            ax.set_yscale("log")
            ax.set_ylim(1, 800)
            ax.set_yticks([1, 10, 100])
            ax.set_yticklabels(["1", "10", "100"], fontsize=5.5)
            ax.tick_params(axis="y", which="minor", length=0)
            ax.text(1.025, 0.5, "Ch %d\n%s" % (c, layer_at(kind, c)), transform=ax.transAxes, ha="left",
                    va="center", fontsize=5.5, color=col, fontweight="bold", linespacing=1.1)
            if j < 3:
                ax.set_xticks([])
                ax.spines["bottom"].set_visible(False)
            else:
                ax.set_xticks([-150, -100, -50, 0, 50, 100, 150])
                ax.set_xticklabels(["−150", "", "", "0", "", "", "150"])
                ax.set_xlabel("Time (ms)", labelpad=1)
            if j == 0:
                ax.set_title("Spectrogram (1–800 Hz, log scale)", fontsize=6.5, pad=2)
        ft = fig.text(109.5 / W_MM, 1 - (y0 + h / 2) / H_FIG, "Frequency (Hz)", rotation=90, ha="center",
                      va="center", fontsize=6.5)
        cb = cbar(fig, im, 168.0, y0 + 6, 1.5, h - 12, "Relative power (dB)",
                  ticks=list(range(-6, E["db_max"] + 1, 6)))
        groups.append(("%s_%s_Spectrogram" % (lt, kind.upper()), spec_axes + [ft, cb.ax]))
        groups.append(("%s_%s_all" % (lt, kind.upper()), [g for n, gs in groups if n.startswith(lt + "_")
                                                          for g in gs] + [head]))
        notes.append("%s  %s: CSD color limit +-%.3g mV/mm2 (99.5th percentile); voltage scale bar %g mV"
                     % (lt, title, cl, sb / 1000))

    out = os.path.join(HERE, OUT_STEM + ".pdf")
    fig.savefig(out)
    fig.savefig(os.path.join(HERE, OUT_STEM + "_preview.png"), dpi=300)
    export_panels(fig, groups)
    plt.close(fig)
    for n in notes:
        print(n)
    print("wrote", out)
