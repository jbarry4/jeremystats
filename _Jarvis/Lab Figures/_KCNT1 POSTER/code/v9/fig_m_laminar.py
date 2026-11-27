"""Methods: the laminar recording (poster v7). The NBH'25 poster's H3 laminar recording (a control mouse; its 64 traces as
drawn, read from the PDF's own vector paths), with the lab's cells beside it (cells.py: the PTEN opening figure's
drawings): CA1 pyramidal cells from stratum pyramidale to the fissure, and the dentate's two blades facing each other
across the hilus, each blade's granule cells with their dendrites out through its own molecular layer.

Where the dentate's layers sit. The NBH poster printed OML, MML, GCL and HILUS down to the last trace. The recording's own
dentate spikes (the two sharp ones, 3.32 and 5.36 s, 100 ms high-pass; tools/nbh_ds_profile in the v7 notes) say
otherwise: they peak positive at 1020-1062 pt and reverse to negative below 1080 pt, down to the last trace. A dentate
spike is positive in the hilus and negative in the molecular layers (Bragin et al. 1995), and the poster's other dentate
spike panels plot positive up, so the hilus is the middle of the dentate part and the lower blade is the bottom, as the
user said: GCL of the upper blade at the top of the positive plateau (~1012 pt), the lower blade's granule layer at the
reversal (~1080 pt), its molecular layer below. CA1 keeps the poster's SP and SR; SLM and the fissure sit just above the
upper blade's molecular layer (~45 pt, 200 um, deep)."""
import os, json
import numpy as np
import fitz
import style as S
import icons as I
import cells as Ce

HERE = os.path.dirname(os.path.abspath(__file__))
RES = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources"
L = np.load(os.path.join(HERE, "data", "nbh_laminar.npz"), allow_pickle=True)
UV = float(L["uv_pt"])
SRCPDF = fitz.open(os.path.join(RES, "FinalNBH'25 1.pdf"))[0]
P = SRCPDF.rect.width / 2212.0
Rr = fitz.Rect(338 * P, 514 * P, 848 * P, 742 * P)
paths = [d for d in SRCPDF.get_drawings() if fitz.Rect(d["rect"]).intersects(Rr) and d["type"] == "s"]
xmin = min(fitz.Rect(d["rect"]).x0 for d in paths)
SEC = float(L["sec_pt"])

# depths (pt on the NBH page, down): CA1 from the poster; the dentate from its dentate spikes (see above)
SP, SR = 871.4, 920.4
FIS = 966.0
LAY = [("SP", SP), ("SR", SR), ("SLM", 953.0), ("ML", 989.0), ("GCL", 1012.0), ("Hilus", 1046.0), ("GCL", 1080.0), ("ML", 1108.0)]
GCL1, GCL2 = 1012.0, 1080.0

W, H = 8.6, 4.65
fig = S.figure(W, H)
YT, YB = 852, 1140
AX, AY, AW, AH = 2.22, 0.36, 5.92, 3.98             # v9: the traces 0.1 in to the right, so the cells have their own column
ax = S.ax_at(fig, AX, AY, AW, AH)
for d in paths:
    its = [it for it in d["items"] if it[0] == "l"]
    pts = np.array([(it[1].x, it[1].y) for it in its] + [(its[-1][2].x, its[-1][2].y)])
    ax.plot((pts[:, 0] - xmin) / SEC, pts[:, 1], c=S.INK, lw=0.32)
ax.set_xlim(0, 7.15); ax.set_ylim(YB, YT); S.bare(ax)
ax.axhline(FIS, c=S.FAINT, lw=0.8, ls=(0, (3, 3)), zorder=0)
# the cells, between the layer names and the traces (one depth axis, equal units on paper)
ia = I.icon_axes(fig, 1.3, AY, 0.86, AH, (YB, YT))
wd = ia.get_xlim()[1]
xi = 0.5 * wd
v_, c_, bb_, soma_, end_ = Ce._src("pyr")
Ce.group(ia, "pyr", xi, SP - 1.0, FIS - 1.0, xscale=min(1.0, 0.96 * wd / ((bb_[2] - bb_[0]) * (FIS - SP) / abs(end_ - soma_))))
# v9: the two blades the same size (one scale), a PV basket cell at each granule layer's hilar border, the SST cell between
k_ = Ce.blade_k(GCL1, FIS + 2.0)
up = Ce.blade(ia, "gc_up", xi, GCL1, -1, k_)
dn = Ce.blade(ia, "gc_down", xi, GCL2, +1, k_)
hs = wd * 0.8 / 13.4                                       # the hilar SST cell: its dendrites across the column
Ce.sst(ia, Ce.frame((xi - 0.03 * hs, 1046.0), (0, -hs), (hs, 0)), spine_lw=0.4, z=6.5)
Ce.pv_basket(ia, up, xi + 0.25 * wd, z=7)
Ce.pv_basket(ia, dn, xi - 0.25 * wd, z=7, mirror=True)
# layer names and the two regions
for txt, y in LAY:
    col = S.SST if txt == "Hilus" else S.SOFT
    S.text_at(fig, 1.26, AY + AH * (y - YT) / (YB - YT), txt, ha="right", va="center", fontsize=S.NOTE + 0.5, color=col,
              fontweight="bold" if txt == "Hilus" else "normal")
for nm, a0, a1, col in (("CA1", YT + 4, FIS - 3, S.PYR), ("DG", FIS + 3, YB - 2, S.GC)):
    ya, yb = AY + AH * (a0 - YT) / (YB - YT), AY + AH * (a1 - YT) / (YB - YT)
    bx = S.ax_at(fig, 0.56, ya, 0.06, yb - ya); bx.set_xlim(0, 1); bx.set_ylim(1, 0); bx.axis("off")
    bx.plot([0.5, 0.5], [0, 1], c=col, lw=2.0, solid_capstyle="butt")
    S.text_at(fig, 0.36, (ya + yb) / 2, nm, rotation=90, ha="center", va="center", fontsize=S.LABEL, fontweight="bold", color=col)
# scale bars
ax.plot([6.15, 7.15], [YB + 6, YB + 6], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(6.65, YB + 9, "1 s", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
ax.plot([7.25, 7.25], [YB - 2, YB - 2 - UV], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(7.32, YB - 2 - UV / 2, "500 µV", rotation=90, ha="left", va="center", fontsize=S.NOTE, color=S.INK)
S.title(fig, 0.0, 0.0, "Laminar recording, CA1 to both dentate blades (64 contacts)", size=S.LABEL)
S.save(fig, os.path.join(HERE, "out", "M_laminar.png"))
print("M_laminar")
