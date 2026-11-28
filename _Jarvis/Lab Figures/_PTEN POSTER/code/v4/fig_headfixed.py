"""PTEN poster v4: the KCNT1 poster's head-fixed figure (v11) without the optical fiber (PTEN recordings use the probe
only). Methods figures (KCNT1 poster v6), each at its print size. (M_laminar and M_events: fig_m_laminar.py, fig_m_events.py.)
  M_headfixed  the NBH'25 poster's head-fixed mouse illustration (its own image, with its transparency), and drawn here the
               micromanipulator that holds the probe and fiber (v7: arm, vertical drive, micrometer knob, clamp) and the probe
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
# v7: the bar over the mouse is the micromanipulator that holds the probe, drawn as one: an arm from the stand, the
# vertical drive with its fine-adjust knob, and the clamp; the head plate is the one in the illustration, now named.
FW_, FH_ = 5.0, 4.65
fig = S.figure(FW_, FH_)
# PTEN v4: no figure title (the poster's legend names it)
mouse = pix_rgba(NBH, 1042)
MW = 3.55
MH = MW * mouse.shape[0] / mouse.shape[1]
MX, MY = 0.0, FH_ - MH - 0.05
ma = S.ax_at(fig, MX, MY, MW, MH)
ma.imshow(mouse, interpolation="bilinear"); ma.axis("off")
H_, W_ = mouse.shape[:2]
win = (MX + 0.428 * MW, MY + 0.262 * MH)          # the head window (inches, from the top left)
ov = S.ax_at(fig, 0, 0, FW_, FH_); ov.set_xlim(0, FW_); ov.set_ylim(FH_, 0); ov.axis("off")
from matplotlib.patches import FancyBboxPatch as _FB, Circle as _Ci  # noqa: E402
DK, MD, LT, HI = "#2F353E", "#4A5361", "#6B7685", "#8D97A5"
rb = lambda x, y, w, h, fc, r=0.035, z=5, ec="none", lw=0: ov.add_patch(_FB((x, y), w, h, boxstyle="round,pad=0,rounding_size=%g" % r,  # noqa: E731
                                                                     fc=fc, ec=ec, lw=lw, zorder=z))
px = win[0] - 0.01                                 # the probe's line
D0 = 0.32                                          # the whole instrument, this far below v6's
# the arm, from the stand (off to the left)
rb(-0.1, D0 + 0.62, px + 0.38, 0.17, MD, 0.05)
rb(-0.1, D0 + 0.62, px + 0.38, 0.045, HI, 0.02, z=5.1)
for xx in (0.2, 0.55, 0.9):
    ov.add_patch(_Ci((xx, D0 + 0.705), 0.022, fc=DK, ec="none", zorder=5.2))
# the vertical drive: a carriage on a rail, a micrometer knob on top
rb(px - 0.2, D0 + 0.79, 0.4, 0.66, LT, 0.04)
rb(px - 0.2, D0 + 0.79, 0.07, 0.66, HI, 0.02, z=5.1)
ov.plot([px + 0.1, px + 0.1], [D0 + 0.84, D0 + 1.4], c=DK, lw=1.2, zorder=5.2)
rb(px - 0.09, D0 + 0.36, 0.18, 0.26, MD, 0.03)
for yy in np.linspace(D0 + 0.40, D0 + 0.58, 6):
    ov.plot([px - 0.085, px + 0.085], [yy, yy], c=HI, lw=0.8, zorder=5.2)
rb(px - 0.13, D0 + 0.30, 0.26, 0.07, DK, 0.03)
# the clamp, and the probe with the fiber beside it, down into the head window
rb(px - 0.11, D0 + 1.45, 0.22, 0.17, DK, 0.025)
ov.plot([px - 0.015, px - 0.015], [D0 + 1.62, win[1] + 0.02], c=S.INK, lw=1.5, zorder=6, solid_capstyle="butt")
ov.text(px - 0.37, D0 + 1.14, "micro-\nmanipulator", fontsize=S.NOTE, color=S.SOFT, va="center", ha="right", linespacing=0.95)
ov.plot([px - 0.34, px - 0.22], [D0 + 1.14, D0 + 1.14], c=S.FAINT, lw=0.8)
ov.text(0.02, MY - 0.02, "head plate", fontsize=S.NOTE, color=S.SOFT, va="center", ha="left")
ov.plot([0.5, MX + 0.29 * MW], [MY + 0.07, MY + 0.25 * MH], c=S.FAINT, lw=0.8, zorder=6)
# the probe, drawn
pa = S.ax_at(fig, 3.3, 0.42, 1.65, FH_ - 0.55)
pa.set_xlim(-0.05, 1); pa.set_ylim(1.08, -0.06); pa.axis("off")
shank = Polygon([[0.14, -0.02], [0.32, -0.02], [0.32, 0.92], [0.23, 1.0], [0.14, 0.92]], closed=True, fc="#D5DAE0", ec="#8A94A0", lw=0.8)
pa.add_patch(shank)
for i in range(64):
    yy = 0.06 + i * (0.86 / 63)
    pa.add_patch(Rectangle((0.2, yy - 0.004), 0.06, 0.008, fc=S.INK, ec="none"))
pa.plot([0.39, 0.39], [0.06, 0.92], c=S.INK, lw=1.0)
pa.plot([0.36, 0.42], [0.06, 0.06], c=S.INK, lw=1.0); pa.plot([0.36, 0.42], [0.92, 0.92], c=S.INK, lw=1.0)
pa.text(0.45, 0.49, "64 contacts\n20 µm apart\n1.28 mm", ha="left", va="center", fontsize=S.SMALL, color=S.INK, linespacing=1.05)
pa.text(0.23, -0.04, "probe", ha="center", va="bottom", fontsize=S.SMALL, color=S.INK, fontweight="bold")
for ya in (0.0, 1.0):
    fig.add_artist(ConnectionPatch(xyA=(win[0] + 0.06, win[1] - 0.02 if ya == 0 else win[1] + 0.05), coordsA=ov.transData,
                                   xyB=(0.0, -0.02 if ya == 0 else 1.03), coordsB=pa.transData, color=S.FAINT, lw=0.9, ls=(0, (3, 2))))
S.save(fig, os.path.join(HERE, "out", "M_headfixed.png"))
print("M_headfixed")

