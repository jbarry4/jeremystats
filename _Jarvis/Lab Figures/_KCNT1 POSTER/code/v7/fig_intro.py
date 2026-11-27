"""Introduction figure I_fI (poster v7): how KCNT1 gain of function changes interneuron firing, as a 2 x 2 matrix.
  columns    SST-type | PV-type, each headed by its cell (cells.py, the same cells as the circuit beside it)
  rows       Het (orange band): SST and PV interneurons, Shore et al., eLife 2024, Fig. 4C (CC BY 4.0); data/elife_fI.json
             (elife_digitize.py), example traces the article's own (middle current step), recoloured.
             Hom (purple band): non-fast-spiking (SST-like) and fast-spiking (PV-like) GABAergic neurons, Shore et al., Cell Rep
             2020, Fig. 4 C4 and B4; data/cellrep_fI.json (cellrep_digitize.py), example traces the article's own, recoloured.
  in a cell  the example traces (WT, then the mutant), the f-I curves (mean +- SEM, each against its own WT), the paper's P
             value and the verdict. Every example trace is drawn at one scale (50 mV, 100 ms), from each figure's own bars.
(The dentate circuit beside it: fig_circuit.py.)"""
import os, json
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter1d
from matplotlib.patches import FancyBboxPatch
import style as S
import cells as Ce

HERE = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(HERE, "data", "elife_fI.json")))
C = json.load(open(os.path.join(HERE, "data", "cellrep_fI.json")))
EL = np.asarray(Image.open(os.path.join(HERE, "pdfwork", "elife_4C.png")).convert("RGB")).astype(float)
CR = np.asarray(Image.open(os.path.join(HERE, "pdfwork", "cellrep2020_fig4.png")).convert("RGB")).astype(float)
WT, HET, HOM = S.GENO["WT"], S.GENO["Het"], S.GENO["Hom"]
MV_IN, MS_IN = 0.19 / 50.0, 0.17 / 100.0       # one scale for every example trace: inches per mV and per ms


def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


def recolor(ink, color):
    rgba = np.zeros(ink.shape + (4,))
    rgba[:, :, :3] = hex2rgb(color)
    rgba[:, :, 3] = np.clip(ink, 0, 1)
    return rgba


def ink_dark(blk, darkest):
    return (255 - blk.min(2)) / (255 - darkest)


def ink_hue(blk, hue_mask):
    """a coloured trace's ink: how saturated each pixel is, only where it has the trace's hue (not black text or bars)."""
    sat = blk.max(2) - blk.min(2)
    return np.clip(sat / max(1.0, np.percentile(sat[hue_mask], 98)), 0, 1) * hue_mask


# the example traces: (image, rows, cols, ink, px per mV, px per ms, masks of labels to drop (rows, cols))
def trace(img, r0, r1, c0, c1, kind, color, px_mv, px_ms, drop=()):
    blk = img[r0:r1, c0:c1].copy()
    for (a, b, c, d) in drop:
        blk[a - r0:b - r0, c - c0:d - c0] = 255
    if kind == "dark":
        sat = blk.max(2) - blk.min(2)
        ink = ink_dark(blk, 30) * (sat < 40)
    else:
        ink = ink_hue(blk, kind(blk))
    return recolor(ink, color), (c1 - c0) / px_ms * MS_IN, (r1 - r0) / px_mv * MV_IN


EL_MV, EL_MS = 48 / 50.0, 37 / 100.0           # the eLife figure's own bars: 50 mV = 48 px, 100 ms = 37 px
TR = {
    ("SST", "WT"): trace(EL, 240, 380, 128, 388, "dark", WT, EL_MV, EL_MS),
    ("SST", "Mut"): trace(EL, 240, 380, 433, 697, lambda b: (b[..., 2] > b[..., 0] + 30), HET, EL_MV, EL_MS),
    ("PV", "WT"): trace(EL, 245, 372, 843, 1093, "dark", WT, EL_MV, EL_MS),
    ("PV", "Mut"): trace(EL, 245, 372, 1178, 1423, lambda b: (b[..., 0] > b[..., 2] + 60), HET, EL_MV, EL_MS),
    # Cell Rep 2020 Fig. 4: B4 (FS) 25 mV = 35 px, 50 ms = 40 px; C4 (NFS) 25 mV = 40 px, 50 ms = 34 px
    ("FS", "WT"): trace(CR, 1072, 1245, 478, 822, "dark", WT, 35 / 25.0, 40 / 50.0, drop=((1150, 1200, 805, 870),)),
    ("FS", "Mut"): trace(CR, 1262, 1428, 470, 822, lambda b: (b[..., 2] > b[..., 0] + 50), HOM, 35 / 25.0, 40 / 50.0,
                         drop=((1315, 1350, 790, 940),)),
    ("NFS", "WT"): trace(CR, 1072, 1258, 935, 1345, "dark", WT, 40 / 25.0, 34 / 50.0, drop=((1155, 1192, 1272, 1330),)),
    ("NFS", "Mut"): trace(CR, 1262, 1432, 935, 1345, lambda b: (b[..., 1] > b[..., 0] + 40) & (b[..., 1] >= b[..., 2] - 15), HOM,
                          40 / 25.0, 34 / 50.0, drop=((1318, 1352, 1255, 1365),)),
}


def fill_curve(pa, hz, sem):
    """the 2020 means: missing points (markers hidden behind each other near 0 Hz) interpolated, SEM likewise."""
    pa = np.asarray(pa, float)
    hz = np.array([np.nan if v is None else v for v in hz], float)
    sem = np.array([np.nan if v is None else v for v in sem], float)
    ok = np.isfinite(hz)
    first = np.flatnonzero(ok)[0]
    hz[:first] = 0.0
    ok = np.isfinite(hz)
    hz = np.interp(pa, pa[ok], hz[ok])
    ok = np.isfinite(sem)
    sem = np.interp(pa, pa[ok], sem[ok]) if ok.any() else np.zeros_like(hz)
    sem[hz < 0.5] = np.minimum(sem[hz < 0.5], 0.5)
    return pa, np.clip(hz, 0, None), sem


# ===================================================================== f-I as a 2 x 2 matrix: rows Het | Hom, columns SST | PV
W, H = 7.4, 6.42
fig = S.figure(W, H)
XS = [1.02, 4.5]                                   # each column's f-I axes, left edge
PW, AXH = 2.62, 1.32
ROWS = [  # (top of the row, genotype, colour, tint, [(key, cell name, x range, y top, ticks, P, verdict)])
    (0.64, "Het", HET, "#FDF3E8", [("SST", "SST interneurons", (0, 900), 60, ([0, 300, 600, 900], [0, 20, 40, 60]), "P = 0.0001", "fire less"),
                                   ("PV", "PV interneurons", (0, 1200), 80, ([0, 400, 800, 1200], [0, 40, 80]), "P = 0.017", "fire more")]),
    (3.56, "Hom", HOM, "#F5EEF7", [("NFS", "non-fast-spiking (SST-like)", (0, 600), 30, ([0, 200, 400, 600], [0, 10, 20, 30]), "P = 0.0002", "fire less"),
                                  ("FS", "fast-spiking (PV-like)", (0, 1500), 75, ([0, 500, 1000, 1500], [0, 25, 50, 75]), "P = 0.017", "fire less")]),
]
RH = 2.84                                           # a row's height
bg = S.ax_at(fig, 0, 0, W, H); bg.set_xlim(0, W); bg.set_ylim(H, 0); bg.axis("off"); bg.set_zorder(-5)
# column headers: each cell type, drawn as in the circuit, and its name
for k, (kind, name, colr) in enumerate((("sst", "SST-type", Ce.SST_C), ("pv", "PV-type", Ce.PV_C))):
    cx = XS[k] + PW / 2
    if kind == "sst":
        Ce.sst(bg, Ce.frame((cx - 1.0, 0.31), (0, -0.04), (0.04, 0)), spine_lw=0.4)
    else:
        Ce.pv(bg, Ce.frame((cx - 1.0, 0.4), (0, -0.036), (0.036, 0)))
    S.text_at(fig, cx - 0.5, 0.3, name, fontsize=S.TITLE + 2, fontweight="bold", color=S.SST if kind == "sst" else S.PV, va="center")
for y0, gen, gcol, tint, panels in ROWS:
    bg.add_patch(FancyBboxPatch((0.04, y0), W - 0.08, RH, boxstyle="round,pad=0,rounding_size=0.12", fc=tint, ec="none", zorder=0))
    S.text_at(fig, 0.27, y0 + RH / 2, gen, rotation=90, ha="center", va="center", fontsize=S.TITLE + 4, fontweight="bold", color=gcol)
    for k, (key, cname, xr, top, (xt, yt), ptxt, verdict) in enumerate(panels):
        x0 = XS[k]
        S.text_at(fig, x0 - 0.38, y0 + 0.1, cname, fontsize=S.NOTE + 0.5, color=S.SOFT)
        # example traces, WT then mutant, at the common scale, bottom-aligned
        cx = x0 - 0.3
        for g, gc in (("WT", WT), ("Mut", gcol)):
            img, wi, hi = TR[(key, g)]
            ta = S.ax_at(fig, cx, y0 + 0.46 + 0.5 - hi, wi, hi)
            ta.imshow(img, aspect="auto", interpolation="bilinear"); ta.axis("off")
            ta.text(0.0, 1.0, "WT" if g == "WT" else gen, transform=ta.transAxes, ha="left", va="bottom", fontsize=S.SMALL,
                    fontweight="bold", color=gc)
            cx += wi + 0.12
        # f-I
        ax = S.ax_at(fig, x0, y0 + 1.04, PW, AXH)
        ax.patch.set_alpha(0)
        if gen == "Het":
            for g, colr in (("WT", WT), ("Het", HET)):
                d = F[key][g]
                pa, lo, hi = np.array(d["pts_pa"]), np.array(d["lo_hz"]), np.array(d["hi_hz"])
                ax.fill_between(pa, uniform_filter1d(lo, 5, mode="nearest"), uniform_filter1d(hi, 5, mode="nearest"), color=colr, alpha=0.2, lw=0)
                cp, ch = np.array(d["curve_pa"]), np.array(d["curve_hz"])
                keep = cp > (2 if g == "WT" else 0)
                ax.plot(cp[keep], uniform_filter1d(ch[keep], 25, mode="nearest"), c=colr, lw=2.0)
        else:
            for g, colr in (("WT", WT), ("Hom", HOM)):
                pa, hz, sem = fill_curve(C[key]["pa"], C[key][g + "_hz"], C[key][g + "_sem"])
                ax.fill_between(pa, hz - sem, hz + sem, color=colr, alpha=0.2, lw=0)
                ax.plot(pa, uniform_filter1d(hz, 3, mode="nearest"), c=colr, lw=2.0)
        ax.set_xlim(*xr); ax.set_ylim(0, top * 1.06)
        ax.set_xticks(xt); ax.set_yticks(yt)
        ax.set_xlabel("Current (pA)", labelpad=1, fontsize=S.LABEL - 1)
        ax.set_ylabel("Spikes/s", labelpad=5, fontsize=S.LABEL - 1)
        ax.text(0.03, 0.98, ptxt, transform=ax.transAxes, ha="left", va="top", fontsize=S.NOTE, color=S.SOFT)
        ax.text(0.045, 0.74, gen + " " + verdict, transform=ax.transAxes, ha="left", va="center", fontsize=S.NOTE + 0.5, color="white",
                fontweight="bold", bbox=dict(boxstyle="round,pad=0.28,rounding_size=0.5", fc=gcol, ec="none"))
# one scale bar for every trace, top right
sb = S.ax_at(fig, 6.95, 0.06, 0.4, 0.5); sb.set_xlim(0, 0.4); sb.set_ylim(0, 0.5); sb.axis("off")
sb.plot([0.03, 0.03], [0.05, 0.05 + 50 * MV_IN], c=S.INK, lw=1.5, solid_capstyle="butt")
sb.plot([0.03, 0.03 + 100 * MS_IN], [0.05, 0.05], c=S.INK, lw=1.5, solid_capstyle="butt")
S.text_at(fig, 6.93, 0.05, "50 mV\n100 ms", fontsize=S.SMALL - 0.5, color=S.SOFT, linespacing=1.0, ha="right")
S.save(fig, os.path.join(HERE, "out", "I_fI.png"))
print("I_fI")
