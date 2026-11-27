"""Introduction figures (poster v5).
  I_fI       SST and PV interneurons, WT vs YH-Het: redrawn from Shore et al., eLife 2024, Fig. 4C (CC BY 4.0). f-I curves from
             data/elife_fI.json (elife_digitize.py: read off the article's own page raster, calibrated on its tick marks);
             example traces are the article's own traces (middle current step), recoloured to the poster's genotype colours.
  I_circuit  the hilar SST (HIPP) circuit, drawn here."""
import os, json
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter1d
from matplotlib.patches import FancyArrowPatch, Rectangle, Circle, Polygon
import style as S
import hpc

HERE = os.path.dirname(os.path.abspath(__file__))
F = json.load(open(os.path.join(HERE, "data", "elife_fI.json")))
A = np.asarray(Image.open(os.path.join(HERE, "pdfwork", "elife_4C.png")).convert("RGB")).astype(float)
WT, HET = S.GENO["WT"], S.GENO["Het"]
MV_PX, MS_PX = 48 / 50.0, 37 / 100.0          # the article's own scale bars: 50 mV = 48 px, 100 ms = 37 px


def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


def recolor(block, color, darkest):
    """ink = how far each pixel is from white (relative to the trace's own darkest colour); painted in `color`."""
    ink = np.clip((255 - block.min(2)) / (255 - darkest), 0, 1)
    rgba = np.zeros(block.shape[:2] + (4,))
    rgba[:, :, :3] = hex2rgb(color)
    rgba[:, :, 3] = ink
    return rgba


BLOCKS = {"SST": dict(WT=(128, 388, 240, 380, 0), Het=(433, 697, 240, 380, 90)),
          "PV": dict(WT=(843, 1093, 245, 372, 0), Het=(1178, 1423, 245, 372, 30))}
fig = S.figure(7.4, 5.5)
for k, (name, title, pv) in enumerate((("SST", "SST interneurons", "P = 0.0001"), ("PV", "PV interneurons", "P = 0.017"))):
    x0 = 0.62 + k * 3.55
    S.title(fig, x0 - 0.5, 0.0, title, size=S.LABEL)
    # example traces, one current step
    for j, g in enumerate(("WT", "Het")):
        c0, c1, r0, r1, dk = BLOCKS[name][g]
        blk = A[r0:r1, c0:c1]
        KK = 1.42 / 264.0                                 # one scale for every trace: inches per article pixel
        ta = S.ax_at(fig, x0 - 0.42 + j * 1.6, 0.45 + (140 - (r1 - r0)) * KK / 2, (c1 - c0) * KK, (r1 - r0) * KK)
        ta.imshow(recolor(blk, WT if g == "WT" else HET, 30 if g == "WT" else 60), aspect="auto", interpolation="bilinear")
        ta.axis("off")
        ta.text(0.0, 1.02, "WT" if g == "WT" else "YH Het", transform=ta.transAxes, ha="left", va="bottom", fontsize=S.NOTE,
                fontweight="bold", color=WT if g == "WT" else HET)
    # f-I
    ax = S.ax_at(fig, x0, 1.78, 2.85, 2.95)
    for g, colr in (("WT", WT), ("Het", HET)):
        d = F[name][g]
        pa, lo, hi = np.array(d["pts_pa"]), np.array(d["lo_hz"]), np.array(d["hi_hz"])
        ax.fill_between(pa, uniform_filter1d(lo, 5, mode="nearest"), uniform_filter1d(hi, 5, mode="nearest"), color=colr, alpha=0.22, lw=0)
        cp, ch = np.array(d["curve_pa"]), np.array(d["curve_hz"])
        keep = cp > (2 if g == "WT" else 0)
        ax.plot(cp[keep], uniform_filter1d(ch[keep], 25, mode="nearest"), c=colr, lw=2.2)
    top = 60 if name == "SST" else 80
    ax.set_xlim(0, 900 if name == "SST" else 1200); ax.set_ylim(0, top * 1.05)
    ax.set_xticks([0, 300, 600, 900] if name == "SST" else [0, 400, 800, 1200])
    ax.set_yticks(np.arange(0, top + 1, 20))
    ax.set_xlabel("Current (pA)")
    if k == 0:
        ax.set_ylabel("Spikes/s")
    ax.text(0.04, 0.97, pv, transform=ax.transAxes, ha="left", va="top", fontsize=S.NOTE + 0.5, color=S.INK)
    lab = ("YH Het fire less" if name == "SST" else "YH Het fire more")
    ax.text(0.97, 0.05, lab, transform=ax.transAxes, ha="right", va="bottom", fontsize=S.NOTE + 0.5, color=HET, fontweight="bold")
# trace scale bar (shared: both panels use the article's 50 mV / 100 ms bars)
KK = 1.42 / 264.0
sb = S.ax_at(fig, 6.9, 0.62, 0.35, 0.6); sb.set_xlim(0, 0.35); sb.set_ylim(0, 0.6); sb.axis("off")
sb.plot([0.02, 0.02], [0.1, 0.1 + 48 * KK], c=S.INK, lw=1.6, solid_capstyle="butt")
sb.plot([0.02, 0.02 + 37 * KK], [0.1, 0.1], c=S.INK, lw=1.6, solid_capstyle="butt")
S.text_at(fig, 6.92, 1.18, "50 mV\n100 ms", fontsize=S.SMALL, color=S.INK, linespacing=1.0)
S.save(fig, os.path.join(HERE, "out", "I_fI.png"))
print("I_fI")

# ===================================================================== the hilar SST circuit
fig = S.figure(5.9, 4.25)
S.title(fig, 0.0, 0.0, "The hilar SST circuit", size=S.LABEL)
ax = S.ax_at(fig, 0.0, 0.0, 5.9, 4.25)
ax.set_xlim(0, 5.9); ax.set_ylim(4.25, 0); ax.axis("off")
L = [("OML", 0.55, 1.15, "#EEF2F6"), ("MML", 1.15, 1.75, "#F4F6F9"), ("IML", 1.75, 2.2, "#EEF2F6"), ("GCL", 2.2, 2.75, hpc.tint(S.REGION["Supra blade"], 0.22)),
     ("Hilus", 2.75, 4.05, hpc.tint(S.REGION["Hilus"], 0.12))]
X0, X1 = 1.1, 5.75
for nm, a, b, fc in L:
    ax.add_patch(Rectangle((X0, a), X1 - X0, b - a, fc=fc, ec="none", zorder=0))
    ax.text(X1 - 0.08, (a + b) / 2, nm, ha="right", va="center", fontsize=S.NOTE + 0.5,
            color=S.REGION["Hilus"] if nm == "Hilus" else (S.REGION["Supra blade"] if nm == "GCL" else S.SOFT),
            fontweight="bold" if nm in ("Hilus", "GCL") else "normal")
GC = S.REGION["Supra blade"]
# granule cells with dendrites
for gx in (2.35, 3.35, 4.35):
    ax.add_patch(Circle((gx, 2.47), 0.13, fc=GC, ec="none", zorder=4))
    ax.plot([gx, gx], [2.36, 1.55], c=GC, lw=2.0, zorder=3)
    for dx in (-0.32, 0.0, 0.32):
        ax.plot([gx, gx + dx * 0.6, gx + dx], [1.55, 1.05, 0.62], c=GC, lw=1.4, zorder=3)
    ax.plot([gx, gx + 0.05], [2.6, 3.05], c=GC, lw=1.2, ls=(0, (2, 1.5)), zorder=3)     # mossy fibre into the hilus
# entorhinal inputs
for nm, y in (("LEC", 0.85), ("MEC", 1.45)):
    ax.add_patch(FancyArrowPatch((0.15, y), (X1 - 0.65, y), arrowstyle="-|>", mutation_scale=13, lw=2.0, color=S.INK, zorder=5))
    ax.text(0.15, y - 0.08, nm, ha="left", va="bottom", fontsize=S.NOTE + 1, fontweight="bold", color=S.INK)
# the HIPP (hilar SST) cell: soma in the hilus, axon up to the OML where it inhibits the LEC-contacted dendrites
U = hpc.UNIT
hx, hy = 3.85, 3.5
ax.add_patch(Polygon([[hx - 0.17, hy + 0.13], [hx + 0.17, hy + 0.13], [hx, hy - 0.18]], closed=True, fc=U, ec=S.INK, lw=0.8, zorder=6))
ax.plot([hx, hx], [hy - 0.18, 0.75], c=U, lw=1.8, zorder=5)
ax.plot([1.9, 5.0], [0.75, 0.75], c=U, lw=1.8, zorder=5)
for tx in (2.2, 2.85, 3.5, 4.15, 4.75):
    ax.plot([tx, tx], [0.75, 0.66], c=U, lw=1.8, zorder=5)
    ax.plot([tx - 0.07, tx + 0.07], [0.64, 0.64], c=U, lw=2.4, solid_capstyle="butt", zorder=5)
ax.text(hx - 0.3, hy + 0.08, "hilar SST (HIPP)\ninterneuron", ha="right", va="center", fontsize=S.NOTE + 0.5, color="#9A6C00", fontweight="bold",
        linespacing=0.95)
ax.text(1.2, 2.47, "granule\ncells", ha="left", va="center", fontsize=S.NOTE, color=GC, fontweight="bold", linespacing=0.95)
ax.annotate("", xy=(hx - 0.12, hy - 0.12), xytext=(3.42, 3.12), arrowprops=dict(arrowstyle="-|>", color=GC, lw=1.2, mutation_scale=10))
S.save(fig, os.path.join(HERE, "out", "I_circuit.png"))
print("I_circuit")
