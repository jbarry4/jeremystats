"""Introduction figures (poster v6).
  I_fI       How KCNT1 gain of function changes interneuron firing, Het and Hom: four f-I panels.
             Het (top): SST and PV interneurons, Shore et al., eLife 2024, Fig. 4C (CC BY 4.0); data/elife_fI.json
             (elife_digitize.py), example traces the article's own (middle current step), recoloured.
             Hom (bottom): non-fast-spiking (SST-like) and fast-spiking (PV-like) GABAergic neurons, Shore et al., Cell Rep 2020,
             Fig. 4 C4 and B4; data/cellrep_fI.json (cellrep_digitize.py), example traces the article's own, recoloured.
             Every example trace is drawn at one scale (50 mV, 100 ms), from each figure's own scale bars.
  I_circuit  The dentate gate, after Jarvis Seahorse's dentate plate (seahorse_schem.js 'dentate': the dentate laid out by
             layer, every connection ending in the layer where it synapses): the granule cell layer and its molecular layers
             curving around the hilus, the perforant paths into the outer (LEC) and middle (MEC) thirds, the hilar SST (HIPP)
             cell's axon in the outer third with the LEC input, the PV basket cell's around the granule cells' somata.
             Granule cells pink, as in the lab's other figures."""
import os, json
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter1d
from matplotlib.patches import FancyArrowPatch, Wedge, Arc, FancyBboxPatch, Circle
import style as S
import icons as I

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


# ===================================================================== f-I: Het (2024) on top, Hom (2020) below
W, H = 7.4, 6.45
fig = S.figure(W, H)
XS = [0.98, 4.48]
PW, TRH, AXH = 2.72, 0.58, 1.62
ROWS = [  # (y of the row, genotype, colour, [(panel key, title, x range, y top, ticks, p text, verdict)])
    (0.0, "Het", HET, [("SST", "SST interneurons", (0, 900), 60, ([0, 300, 600, 900], [0, 20, 40, 60]), "P = 0.0001", "fire less"),
                        ("PV", "PV interneurons", (0, 1200), 80, ([0, 400, 800, 1200], [0, 40, 80]), "P = 0.017", "fire more")]),
    (3.2, "Hom", HOM, [("NFS", "Non-fast-spiking (SST-like)", (0, 600), 30, ([0, 200, 400, 600], [0, 10, 20, 30]), "P = 0.0002", "fire less"),
                        ("FS", "Fast-spiking (PV-like)", (0, 1500), 75, ([0, 500, 1000, 1500], [0, 25, 50, 75]), "P = 0.017", "fire less")]),
]
for y0, gen, gcol, panels in ROWS:
    S.text_at(fig, 0.12, y0 + 1.55, "YH " + gen, rotation=90, ha="center", va="center", fontsize=S.LABEL + 1, fontweight="bold", color=gcol)
    for k, (key, title, xr, top, (xt, yt), ptxt, verdict) in enumerate(panels):
        x0 = XS[k]
        S.text_at(fig, x0 - 0.42, y0, title, fontsize=S.LABEL, fontweight="bold", color=S.INK)
        # example traces, WT then mutant, at the common scale, bottom-aligned
        cx = x0 - 0.3
        for g, gc in (("WT", WT), ("Mut", gcol)):
            img, wi, hi = TR[(key, g)]
            ta = S.ax_at(fig, cx, y0 + 0.32 + TRH - hi, wi, hi)
            ta.imshow(img, aspect="auto", interpolation="bilinear"); ta.axis("off")
            ta.text(0.0, 1.0, "WT" if g == "WT" else gen, transform=ta.transAxes, ha="left", va="bottom", fontsize=S.SMALL + 0.5,
                    fontweight="bold", color=gc)
            cx += wi + 0.14
        # f-I
        ax = S.ax_at(fig, x0, y0 + 0.98, PW, AXH)
        if gen == "Het":
            for g, colr in (("WT", WT), ("Het", HET)):
                d = F[key][g]
                pa, lo, hi = np.array(d["pts_pa"]), np.array(d["lo_hz"]), np.array(d["hi_hz"])
                ax.fill_between(pa, uniform_filter1d(lo, 5, mode="nearest"), uniform_filter1d(hi, 5, mode="nearest"), color=colr, alpha=0.22, lw=0)
                cp, ch = np.array(d["curve_pa"]), np.array(d["curve_hz"])
                keep = cp > (2 if g == "WT" else 0)
                ax.plot(cp[keep], uniform_filter1d(ch[keep], 25, mode="nearest"), c=colr, lw=2.2)
        else:
            for g, colr in (("WT", WT), ("Hom", HOM)):
                pa, hz, sem = fill_curve(C[key]["pa"], C[key][g + "_hz"], C[key][g + "_sem"])
                ax.fill_between(pa, hz - sem, hz + sem, color=colr, alpha=0.22, lw=0)
                ax.plot(pa, uniform_filter1d(hz, 3, mode="nearest"), c=colr, lw=2.2)
        ax.set_xlim(*xr); ax.set_ylim(0, top * 1.06)
        ax.set_xticks(xt); ax.set_yticks(yt)
        ax.set_xlabel("Current (pA)", labelpad=2)
        if k == 0:
            ax.set_ylabel("Spikes/s")
        ax.text(0.04, 0.97, ptxt, transform=ax.transAxes, ha="left", va="top", fontsize=S.NOTE, color=S.INK)
        ax.text(0.97, 0.05, gen + " " + verdict, transform=ax.transAxes, ha="right", va="bottom", fontsize=S.NOTE + 0.5, color=gcol,
                fontweight="bold")
# one scale bar for every trace
sb = S.ax_at(fig, 6.76, 0.42, 0.4, 0.5); sb.set_xlim(0, 0.4); sb.set_ylim(0, 0.5); sb.axis("off")
sb.plot([0.03, 0.03], [0.05, 0.05 + 50 * MV_IN], c=S.INK, lw=1.6, solid_capstyle="butt")
sb.plot([0.03, 0.03 + 100 * MS_IN], [0.05, 0.05], c=S.INK, lw=1.6, solid_capstyle="butt")
S.text_at(fig, 6.78, 0.98, "50 mV\n100 ms", fontsize=S.SMALL, color=S.INK, linespacing=1.0)
S.save(fig, os.path.join(HERE, "out", "I_fI.png"))
print("I_fI")

# ===================================================================== the dentate gate (after Seahorse's dentate plate)
W, H = 5.9, 4.85
fig = S.figure(W, H)
ax = S.ax_at(fig, 0, 0, W, H)
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_aspect("equal"); ax.axis("off")
S.title(fig, 0.0, 0.0, "The dentate gate", size=S.LABEL)
CX, CY = 3.05, 2.42
A0, A1 = 62, 298                                  # the C opens to the right, toward CA3
RING = [("Hilus", 0.0, 0.72), ("GCL", 0.72, 0.98), ("IML", 0.98, 1.18), ("MML", 1.18, 1.47), ("OML", 1.47, 1.78)]
FILL = {"Hilus": S.REGION_FILL["Hilus"], "GCL": S.GC_FILL, "IML": "#F1F3F6", "MML": "#E7EBF0", "OML": "#F1F3F6"}
ALPHA = {"Hilus": 0.28, "GCL": 0.42, "IML": 1.0, "MML": 1.0, "OML": 1.0}
P = lambda r, th: np.array([CX + r * np.cos(np.radians(th)), CY + r * np.sin(np.radians(th))])   # noqa: E731
U = lambda th: np.array([np.cos(np.radians(th)), np.sin(np.radians(th))])                          # noqa: E731
for nm, r0, r1 in RING:
    ax.add_patch(Wedge((CX, CY), r1, A0, A1, width=r1 - r0 if r0 > 0 else None, fc=FILL[nm], alpha=ALPHA[nm], ec="none", zorder=1))
ax.add_patch(Wedge((CX, CY), 1.78, A0, A1, fc="none", ec="#9AA4B1", lw=0.9, zorder=2))
for nm, r0, r1 in RING[1:]:
    p = P((r0 + r1) / 2, 71)
    ax.text(p[0], p[1], nm, ha="center", va="center", rotation=-19, fontsize=S.SMALL + 0.5, color=S.GC if nm == "GCL" else S.SOFT,
            fontweight="bold" if nm == "GCL" else "normal", zorder=9)
p = P(0.42, 268)
ax.text(p[0], p[1], "Hilus", ha="center", va="center", fontsize=S.SMALL + 1, color=S.REGION["Hilus"], fontweight="bold", zorder=9)
UPPER, LOWER = (108, 136, 162), (198, 224, 252)
# entorhinal inputs: LEC into the outer third, MEC into the middle third, of both blades
for nm, y, r, col in (("LEC", CY + 0.62, 1.64, S.INK), ("MEC", CY - 0.62, 1.31, "#626B78")):
    ax.add_patch(FancyBboxPatch((0.05, y - 0.2), 0.74, 0.4, boxstyle="round,pad=0,rounding_size=0.08", fc="white", ec=col, lw=1.3, zorder=6))
    ax.text(0.42, y, nm, ha="center", va="center", fontsize=S.NOTE + 0.5, fontweight="bold", color=col, zorder=7)
    e = P(r, 180)
    ax.plot([0.79, e[0]], [y, e[1]], c=col, lw=1.6, zorder=5, solid_capstyle="round")
    for t1 in (UPPER[0] - 8, LOWER[-1] + 8):
        th = np.linspace(180, t1, 80)
        pts = np.array([P(r, t) for t in th])
        ax.plot(pts[:, 0], pts[:, 1], c=col, lw=1.6, zorder=5)
        ax.add_patch(FancyArrowPatch(tuple(pts[-4]), tuple(pts[-1]), arrowstyle="-|>", mutation_scale=10, lw=1.6, color=col, zorder=5))
# granule cells, both blades, dendrites out through the molecular layer
for th in UPPER + LOWER:
    I.granule_toward(ax, P(0.85, th), P(1.76, th), 0.13, z=4, spread=0.6)
# a mossy fibre: a granule cell's axon through the hilus, out to CA3
mf = np.array([P(0.78, 136), P(0.45, 105), (CX + 0.2, CY + 0.12), (CX + 0.95, CY + 0.12), (CX + 1.5, CY + 0.12)])
ax.plot(mf[:, 0], mf[:, 1], c=S.GC, lw=1.4, ls=(0, (3, 2)), zorder=4)
ax.add_patch(FancyArrowPatch(tuple(mf[-2]), tuple(mf[-1]), arrowstyle="-|>", mutation_scale=10, lw=1.4, color=S.GC, zorder=4))
ax.text(CX + 1.58, CY + 0.12, "CA3", ha="left", va="center", fontsize=S.NOTE + 0.5, fontweight="bold", color=S.SOFT)
# the hilar SST (HIPP) cell: soma in the hilus, axon to the outer third of both blades, where it meets the LEC input
sx, sy = CX - 0.3, CY - 0.05
for dx, dy in ((0.2, 0.1), (0.16, -0.18), (-0.06, -0.24)):
    ax.plot([sx, sx + dx], [sy, sy + dy], c=S.SST_FILL, lw=1.3, zorder=6)
RA = 1.53
for t_in, ths in ((150, UPPER), (210, LOWER)):
    a = P(RA, t_in)
    ax.plot([sx, a[0]], [sy, a[1]], c=S.SST_FILL, lw=1.7, zorder=6)
    th = np.linspace(ths[0] - 4, ths[-1] + 4, 60)
    pts = np.array([P(RA, t) for t in th])
    ax.plot(pts[:, 0], pts[:, 1], c=S.SST_FILL, lw=1.7, zorder=6)
    for t in ths:                                  # an inhibitory synapse on each granule cell's outer dendrites
        q = P(RA, t + 4.5)
        b = q + U(t + 4.5) * 0.08
        n = np.array([-U(t + 4.5)[1], U(t + 4.5)[0]]) * 0.05
        ax.plot([q[0], b[0]], [q[1], b[1]], c=S.SST_FILL, lw=1.5, zorder=6)
        ax.plot([b[0] - n[0], b[0] + n[0]], [b[1] - n[1], b[1] + n[1]], c=S.SST_FILL, lw=2.4, solid_capstyle="butt", zorder=6)
I.interneuron(ax, sx, sy, 0.1, S.SST_FILL, z=8)
# the PV basket cell: at the granule layer's hilar border, its axon around the granule cells' somata
pp = P(0.6, 122)
I.interneuron(ax, pp[0], pp[1], 0.095, S.PV_FILL, z=8)
for th in (108, 136):
    c = P(0.85, th)
    ax.plot([pp[0], c[0]], [pp[1], c[1]], c=S.PV_FILL, lw=1.5, zorder=6)
    ax.add_patch(Arc(tuple(c), 0.32, 0.32, angle=th, theta1=95, theta2=265, color=S.PV, lw=1.8, zorder=7))
# names, and what KCNT1 gain of function does to each (I_fI), in the opening beside the CA3 exit
LX = CX + 0.98
ax.plot([pp[0] + 0.1, LX - 0.06], [pp[1] + 0.01, CY + 0.68], c=S.PV, lw=0.8, zorder=3)
ax.text(LX, CY + 0.68, "PV basket cell", ha="left", va="bottom", fontsize=S.NOTE + 0.5, fontweight="bold", color=S.PV)
ax.text(LX, CY + 0.65, "fires more in Het,\nless in Hom", ha="left", va="top", fontsize=S.SMALL + 0.5, color=S.PV, linespacing=1.0)
ax.plot([sx + 0.1, LX - 0.06], [sy - 0.03, CY - 0.38], c=S.SST, lw=0.8, zorder=3)
ax.text(LX, CY - 0.38, "SST (HIPP) cell", ha="left", va="bottom", fontsize=S.NOTE + 0.5, fontweight="bold", color=S.SST)
ax.text(LX, CY - 0.41, "fires less in\nHet and Hom", ha="left", va="top", fontsize=S.SMALL + 0.5, color=S.SST, linespacing=1.0)
g = P(1.95, 236)
ax.text(g[0] - 0.05, g[1] - 0.05, "granule cells", ha="right", va="top", fontsize=S.NOTE, fontweight="bold", color=S.GC)
# legend: excites, inhibits
lx, ly = 0.1, 0.18
ax.add_patch(FancyArrowPatch((lx, ly), (lx + 0.36, ly), arrowstyle="-|>", mutation_scale=9, lw=1.4, color=S.INK))
ax.text(lx + 0.44, ly, "excites", va="center", fontsize=S.SMALL + 0.5, color=S.SOFT)
ax.plot([lx + 1.12, lx + 1.42], [ly, ly], c=S.SST_FILL, lw=1.5)
ax.plot([lx + 1.42, lx + 1.42], [ly - 0.05, ly + 0.05], c=S.SST_FILL, lw=2.4, solid_capstyle="butt")
ax.text(lx + 1.5, ly, "inhibits", va="center", fontsize=S.SMALL + 0.5, color=S.SOFT)
S.save(fig, os.path.join(HERE, "out", "I_circuit.png"))
print("I_circuit")
