"""Methods figures (poster v6), each at its print size. (M_laminar and M_events: fig_m_laminar.py, fig_m_events.py.)
  M_headfixed  the NBH'25 poster's head-fixed mouse illustration (its own image, with its transparency) and a probe drawn here
  M_histology  Dylan Marchand's 2024 SST/NeuN image of the dentate (his Fig. 6C, 20x; the PDF's own tiles), framed on the hilus
               between the two granule cell layers, the layers named on the image, two SST cells marked, channels in a key
  M_arena      the rotating arena, drawn: the floor seen from above, the shock zone as in Figure A (the same 60 degree red
               wedge), the floor's rotation, the room's cues and a mouse (replaces the low-resolution photo)"""
import os, sys, json
import numpy as np
import fitz
from PIL import Image
from matplotlib.patches import FancyArrowPatch, Polygon, FancyBboxPatch, Wedge, Rectangle, ConnectionPatch
import style as S

HERE = os.path.dirname(os.path.abspath(__file__))
RES = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources"
NBH = fitz.open(os.path.join(RES, "FinalNBH'25 1.pdf"))
DYL = fitz.open(os.path.join(RES, "FinalKcnt1_Dylan 1.pdf"))
LIGHT = "#2F86D6"
R = S.REGION


def pix_rgba(doc, xref):
    p = fitz.Pixmap(doc, xref)
    smask = doc.xref_get_key(xref, "SMask")
    if p.colorspace is None or p.colorspace.n != 3:
        p = fitz.Pixmap(fitz.csRGB, p)
    rgb = np.frombuffer(p.samples, np.uint8).reshape(p.height, p.width, p.n)[:, :, :3]
    if smask[0] == "xref":
        m = fitz.Pixmap(doc, int(smask[1].split()[0]))
        a = np.frombuffer(m.samples, np.uint8).reshape(m.height, m.width)
        return np.dstack([rgb, a])
    return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])


# ===================================================================== head-fixed
fig = S.figure(5.0, 3.65)
S.title(fig, 0.0, 0.0, "Head-fixed recording", size=S.LABEL)
mouse = pix_rgba(NBH, 1042)
ma = S.ax_at(fig, 0.0, 1.5, 3.2, 3.2 * mouse.shape[0] / mouse.shape[1])
ma.imshow(mouse, interpolation="bilinear"); ma.axis("off")
# head bar and the probe going in (in the mouse image's pixels)
H, W = mouse.shape[:2]
hx, hy = 0.452 * W, 0.255 * H                 # the head window
ma.add_patch(FancyBboxPatch((0.08 * W, -0.42 * H), 0.86 * W, 0.09 * H, boxstyle="round,pad=0,rounding_size=20", fc="#4A5260", ec="none",
                            clip_on=False, zorder=3))
ma.add_patch(FancyBboxPatch((0.37 * W, -0.33 * H), 0.12 * W, 0.14 * H, boxstyle="round,pad=0,rounding_size=12", fc="#4A5260", ec="none",
                            clip_on=False, zorder=3))
ma.plot([hx - 6, hx - 6], [-0.19 * H, hy], c=S.INK, lw=1.4, clip_on=False, zorder=4)
ma.plot([hx + 7, hx + 7], [-0.19 * H, hy], c=LIGHT, lw=1.4, clip_on=False, zorder=4)
ma.text(0.5 * W, -0.46 * H, "head bar", ha="center", va="bottom", fontsize=S.NOTE, color=S.SOFT)
# the probe, drawn
pa = S.ax_at(fig, 3.3, 0.42, 1.65, 3.15)
pa.set_xlim(-0.05, 1); pa.set_ylim(1.08, -0.06); pa.axis("off")
shank = Polygon([[0.14, -0.02], [0.32, -0.02], [0.32, 0.92], [0.23, 1.0], [0.14, 0.92]], closed=True, fc="#D5DAE0", ec="#8A94A0", lw=0.8)
pa.add_patch(shank)
for i in range(64):
    yy = 0.06 + i * (0.86 / 63)
    pa.add_patch(Rectangle((0.2, yy - 0.004), 0.06, 0.008, fc=S.INK, ec="none"))
pa.plot([0.07, 0.07], [-0.02, 0.84], c=LIGHT, lw=2.6, solid_capstyle="butt")
pa.add_patch(Polygon([[0.07, 0.84], [-0.03, 1.03], [0.17, 1.03]], closed=True, fc=LIGHT, alpha=0.28, ec="none"))
pa.plot([0.39, 0.39], [0.06, 0.92], c=S.INK, lw=1.0)
pa.plot([0.36, 0.42], [0.06, 0.06], c=S.INK, lw=1.0); pa.plot([0.36, 0.42], [0.92, 0.92], c=S.INK, lw=1.0)
pa.text(0.45, 0.49, "64 contacts\n20 µm apart\n1.28 mm", ha="left", va="center", fontsize=S.SMALL, color=S.INK, linespacing=1.05)
pa.text(0.07, -0.04, "fiber", ha="center", va="bottom", fontsize=S.SMALL, color=LIGHT, fontweight="bold")
pa.text(0.23, -0.04, "probe", ha="left", va="bottom", fontsize=S.SMALL, color=S.INK, fontweight="bold")
for ya in (0.0, 1.0):
    fig.add_artist(ConnectionPatch(xyA=(hx + 12, hy - 0.05 * H if ya == 0 else hy + 0.02 * H), coordsA=ma.transData,
                                   xyB=(0.0, -0.02 if ya == 0 else 1.03), coordsB=pa.transData, color=S.FAINT, lw=0.9, ls=(0, (3, 2))))
S.save(fig, os.path.join(HERE, "out", "M_headfixed.png"))
print("M_headfixed")

# ===================================================================== histology, framed on the hilus
from matplotlib.patches import FancyBboxPatch as FBP, Circle as Circ  # noqa: E402
HC = np.asarray(Image.open(os.path.join(HERE, "pdfwork", "dyl_hist_C.png")).convert("RGB"))
crop = HC[110:1250, 120:1380]                       # both granule cell layers and the hilus between them
fig = S.figure(2.85, 3.22)
S.title(fig, 0.0, 0.0, "SST cells in the hilus", size=S.NOTE + 1)
ax = S.ax_at(fig, 0.0, 0.3, 2.85, 2.85 * crop.shape[0] / crop.shape[1])
im = ax.imshow(crop, interpolation="bilinear")
clip = FBP((0, 0), crop.shape[1], crop.shape[0], boxstyle="round,pad=0,rounding_size=60", transform=ax.transData)
im.set_clip_path(clip)
ax.set_xlim(0, crop.shape[1]); ax.set_ylim(crop.shape[0], 0); ax.axis("off")
lab = dict(fontsize=S.NOTE, fontweight="bold", color="white")
ax.text(40, 290 - 110, "GCL", va="center", **lab)
ax.text(40, 1080 - 110, "GCL", va="center", **lab)
ax.text(1240 - 120, 760 - 110, "Hilus", ha="right", va="center", **lab)
for (cx, cy) in ((562, 624), (626, 744)):                 # two SST cells (SST and NeuN together: yellow)
    x, y = cx - 120, cy - 110
    ax.annotate("", xy=(x - 28, y + 18), xytext=(x - 150, y + 95), arrowprops=dict(arrowstyle="-|>", color="white", lw=1.4, mutation_scale=11))
yk = 0.3 + 2.85 * crop.shape[0] / crop.shape[1] + 0.1
for k, (nm, col) in enumerate((("SST", "#5BE34A"), ("NeuN", "#FF5A3C"))):
    x = 0.05 + k * 0.85
    S.text_at(fig, x, yk, "\u25CF", fontsize=S.NOTE + 2, color=col)
    S.text_at(fig, x + 0.2, yk + 0.02, nm, fontsize=S.NOTE, color=S.INK)
S.save(fig, os.path.join(HERE, "out", "M_histology.png"))
print("M_histology", crop.shape)

# ===================================================================== the rotating arena, drawn
from matplotlib.patches import Wedge as Wdg, Ellipse as Ell, FancyArrowPatch as FAP, Rectangle as Rect, Polygon as Poly  # noqa: E402
ZONE = "#D62728"                                    # Figure A's shock-zone red
fig = S.figure(2.85, 2.85)
S.title(fig, 0.0, 0.0, "The rotating arena", size=S.NOTE + 1)
ax = S.ax_at(fig, 0.0, 0.28, 2.85, 2.57)
ax.set_xlim(-1.42, 1.43); ax.set_ylim(-1.25, 1.32); ax.set_aspect("equal"); ax.axis("off")
# the room and its cues on the walls
ax.add_patch(FBP((-1.36, -1.2), 2.72, 2.45, boxstyle="round,pad=0,rounding_size=0.08", fc="#F7F8FA", ec="#C9CFD7", lw=1.0, zorder=0))
ax.add_patch(Rect((-0.28, 1.12), 0.56, 0.1, fc="#3A4250", ec="none", zorder=1))                       # a dark card, north
for i in range(5):
    ax.add_patch(Rect((1.17, -0.45 + i * 0.18), 0.09, 0.09, fc="#3A4250", ec="none", zorder=1))      # a dotted card, east
ax.add_patch(Poly([[-1.27, -0.2], [-1.16, 0.0], [-1.27, 0.2]], closed=True, fc="#3A4250", ec="none", zorder=1))  # a triangle, west
ax.text(0.0, -1.14, "cues on the room's walls", ha="center", va="bottom", fontsize=S.SMALL, color=S.SOFT, zorder=2)
# the floor, from above, and the shock zone fixed in the room (Figure A's wedge)
R = 0.86
ax.add_patch(Circ((0, 0), R, fc="#E9ECF0", ec="#8E99A6", lw=1.2, zorder=2))
for rr in (0.3, 0.58):
    ax.add_patch(Circ((0, 0), rr, fc="none", ec="#D5DAE0", lw=0.7, zorder=2))
ax.add_patch(Wdg((0, 0), R, 15, 75, fc=ZONE, alpha=0.22, ec="none", zorder=3))
ax.add_patch(Wdg((0, 0), R, 15, 75, fc="none", ec=ZONE, lw=1.2, zorder=3))
ax.text(0.62, 0.98, "shock\nzone", ha="left", va="center", fontsize=S.SMALL + 0.5, color=ZONE, fontweight="bold", linespacing=0.95, zorder=4)
# the floor turns under it
ax.add_patch(FAP((R * 1.13 * np.cos(np.radians(110)), R * 1.13 * np.sin(np.radians(110))),
                 (R * 1.13 * np.cos(np.radians(200)), R * 1.13 * np.sin(np.radians(200))), connectionstyle="arc3,rad=0.42",
                 arrowstyle="-|>", mutation_scale=12, lw=1.8, color=S.INK, zorder=4))
ax.text(-1.1, 0.78, "floor\nturns", ha="center", va="center", fontsize=S.SMALL + 0.5, color=S.INK, linespacing=0.95, zorder=4)
# a mouse, from above
mx, my, ang = -0.18, -0.36, 35
t = np.radians(ang)
rot = lambda u, v: (mx + u * np.cos(t) - v * np.sin(t), my + u * np.sin(t) + v * np.cos(t))   # noqa: E731
ax.add_patch(Ell(rot(0, 0), 0.34, 0.2, angle=ang, fc="#6B7280", ec="none", zorder=5))
ax.add_patch(Ell(rot(0.2, 0), 0.16, 0.12, angle=ang, fc="#6B7280", ec="none", zorder=5))
for s_ in (-1, 1):
    ax.add_patch(Circ(rot(0.17, s_ * 0.075), 0.035, fc="#9AA1AD", ec="none", zorder=6))
tl = np.array([rot(-0.17 - 0.3 * k, 0.06 * np.sin(k * 3.2)) for k in np.linspace(0, 1, 20)])
ax.plot(tl[:, 0], tl[:, 1], c="#6B7280", lw=1.3, zorder=5, solid_capstyle="round")
S.save(fig, os.path.join(HERE, "out", "M_arena.png"))
print("M_arena")
