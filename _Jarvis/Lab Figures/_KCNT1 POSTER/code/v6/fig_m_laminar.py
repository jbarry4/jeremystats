"""Methods: the laminar recording (poster v6). The NBH'25 poster's H3 laminar recording (a control mouse; its 64 traces as
drawn, read from the PDF's own vector paths) with its printed layer labels, and, as in that poster, the cells beside them:
the lab's CA1 pyramidal cell from stratum pyramidale to lacunosum-moleculare and a granule cell from the granule layer to
the fissure (icons.py)."""
import os, json
import numpy as np
import fitz
import style as S
import icons as I

HERE = os.path.dirname(os.path.abspath(__file__))
RES = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources"
L = np.load(os.path.join(HERE, "data", "nbh_laminar.npz"), allow_pickle=True)
UV = float(L["uv_pt"])
lay = json.loads(str(L["layers"]))
SRCPDF = fitz.open(os.path.join(RES, "FinalNBH'25 1.pdf"))[0]
P = SRCPDF.rect.width / 2212.0
Rr = fitz.Rect(338 * P, 514 * P, 848 * P, 742 * P)
paths = [d for d in SRCPDF.get_drawings() if fitz.Rect(d["rect"]).intersects(Rr) and d["type"] == "s"]
xmin = min(fitz.Rect(d["rect"]).x0 for d in paths)
SEC = float(L["sec_pt"])

W, H = 8.6, 3.65
fig = S.figure(W, H)
YT, YB = 852, 1140
AX, AY, AW, AH = 2.12, 0.36, 6.02, 2.98
ax = S.ax_at(fig, AX, AY, AW, AH)
for d in paths:
    its = [it for it in d["items"] if it[0] == "l"]
    pts = np.array([(it[1].x, it[1].y) for it in its] + [(its[-1][2].x, its[-1][2].y)])
    ax.plot((pts[:, 0] - xmin) / SEC, pts[:, 1], c=S.INK, lw=0.32)
ax.set_xlim(0, 7.15); ax.set_ylim(YB, YT); S.bare(ax)
FIS = (lay["SLM"] + lay["OML"]) / 2 + 4                    # the hippocampal fissure, between SLM and OML
ax.axhline(FIS, c=S.FAINT, lw=0.8, ls=(0, (3, 3)), zorder=0)
# the cells, between the layer names and the traces
ia = I.icon_axes(fig, 1.42, AY, 0.62, AH, (YB, YT))
xi = 0.5 * ia.get_xlim()[1]
I.pyramidal(ia, xi, lay["SP"] + 2, FIS - 2, width=21)
I.granule(ia, xi, lay["GCL"], FIS + 3, width=20)
# layer names and the two regions
for key, txt in (("SP", "SP"), ("SR", "SR"), ("SLM", "SLM"), ("OML", "OML"), ("MML", "MML"), ("GCL", "GCL"), ("HILUS", "Hilus")):
    S.text_at(fig, 1.40, AY + AH * (lay[key] - YT) / (YB - YT), txt, ha="right", va="center", fontsize=S.NOTE + 0.5, color=S.SOFT)
for nm, a0, a1, col in (("CA1", YT + 4, FIS - 3, S.PYR), ("DG", FIS + 3, YB - 2, S.GC)):
    ya, yb = AY + AH * (a0 - YT) / (YB - YT), AY + AH * (a1 - YT) / (YB - YT)
    bx = S.ax_at(fig, 0.62, ya, 0.06, yb - ya); bx.set_xlim(0, 1); bx.set_ylim(1, 0); bx.axis("off")
    bx.plot([0.5, 0.5], [0, 1], c=col, lw=2.0, solid_capstyle="butt")
    S.text_at(fig, 0.42, (ya + yb) / 2, nm, rotation=90, ha="center", va="center", fontsize=S.LABEL, fontweight="bold", color=col)
# scale bars
ax.plot([6.15, 7.15], [YB + 6, YB + 6], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(6.65, YB + 9, "1 s", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
ax.plot([7.25, 7.25], [YB - 2, YB - 2 - UV], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(7.32, YB - 2 - UV / 2, "500 µV", rotation=90, ha="left", va="center", fontsize=S.NOTE, color=S.INK)
S.title(fig, 0.0, 0.0, "Laminar recording, CA1 to dentate gyrus (64 contacts)", size=S.LABEL)
S.save(fig, os.path.join(HERE, "out", "M_laminar.png"))
print("M_laminar")
