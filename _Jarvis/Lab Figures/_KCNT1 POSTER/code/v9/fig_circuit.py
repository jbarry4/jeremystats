"""I_circuit (poster v7): the dentate gate, laid out as Jarvis Seahorse's dentate plate (seahorse_schem.js 'dentate': the
dentate by layer, every connection ending in the layer where it synapses), now drawn with real-looking cells (cells.py):
  granule cells  the lab's own drawing (the PTEN opening figure), bent along both blades: somata in the granule layer,
                 dendrites out through the inner, middle and outer molecular layers
  SST (HIPP)     a hilar SST cell: multipolar soma and long spiny dendrites in the hilus; its axon climbs through the
                 granule layer and spreads along the outer molecular layer of both blades, where the LEC input lands
  PV basket      a PV basket cell at the granule layer's hilar border: smooth dendrites up through the granule and
                 molecular layers and down into the hilus; its axon wraps the granule cells' somata (the basket)
  inputs         LEC into the outer third, MEC into the middle third, of both blades; a mossy fibre out to CA3
Schematic where it has to be (layer bands, arrows for excitation, bars for inhibition), realistic where it can be.
v8: the same drawing 1.24x larger (K), on a canvas trimmed to it."""
import os
import numpy as np
from matplotlib.patches import FancyArrowPatch, Wedge, FancyBboxPatch, Arc
import style as S
import cells as Ce

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 5.9, 5.28
K = 1.24                                           # v8: everything in the dentate drawn this much larger than v7
fig = S.figure(W, H)
ax = S.ax_at(fig, 0, 0, W, H)
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_aspect("equal"); ax.axis("off")
S.title(fig, 0.0, 0.0, "The dentate gate", size=S.LABEL)
CX, CY = 3.07, 2.64
A0, A1 = 60, 300                                   # the C opens to the right, toward CA3
R_H, R_G, R_I, R_M, R_O = (K * r for r in (0.70, 0.96, 1.16, 1.45, 1.78))     # outer radii: hilus, GCL, IML, MML, OML
RING = [("Hilus", 0.0, R_H), ("GCL", R_H, R_G), ("IML", R_G, R_I), ("MML", R_I, R_M), ("OML", R_M, R_O)]
FILL = {"Hilus": "#FBEBC4", "GCL": "#FBE1E0", "IML": "#F4F6F8", "MML": "#EBEFF3", "OML": "#F4F6F8"}
P = lambda r, th: np.array([CX + r * np.cos(np.radians(th)), CY + r * np.sin(np.radians(th))])   # noqa: E731
U = lambda th: np.array([np.cos(np.radians(th)), np.sin(np.radians(th))])                          # noqa: E731
for nm, r0, r1 in RING:
    ax.add_patch(Wedge((CX, CY), r1, A0, A1, width=r1 - r0 if r0 > 0 else None, fc=FILL[nm], ec="none", zorder=1))
ax.add_patch(Wedge((CX, CY), R_O, A0, A1, fc="none", ec="#A9B2BD", lw=0.9, zorder=2))

# ------------------------------------------------------------------ granule cells along both blades (the lab's drawing)
R_SOMA = R_H + 0.11 * K
tiles = []
# v9 (the user: "reduce the number of granule cells to make it less busy"): six groups that no longer overlap, 24 cells
# instead of 40, evenly spread along both blades
for i, th in enumerate(np.linspace(A0 + 1.5, A1 - 1.5 - 34, 6)):
    _, th1 = Ce.group_arc(ax, "gc_up", (CX, CY), R_SOMA, R_O - 0.03, th, th + 34, z=3, flipx=i % 2 == 1, alpha=0.82)
    tiles.append((th, th1))
GC_SOMA = []                                       # where the drawn somata sit (for the basket; v9: mirrored tiles too)
for i, (t0, t1) in enumerate(tiles):
    for u in Ce.GC_BODY_X["gc_up"]:
        GC_SOMA.append(t0 + ((1 - u) if i % 2 == 1 else u) * (t1 - t0))
GC_SOMA = np.array(sorted(GC_SOMA))

# layer names, on the upper blade's open end
for nm, r0, r1 in RING[1:]:
    p = P((r0 + r1) / 2, 64.5)
    ax.text(p[0], p[1], nm, ha="center", va="center", rotation=-25.5, fontsize=S.SMALL, color=S.GC if nm == "GCL" else S.SOFT,
            fontweight="bold" if nm == "GCL" else "normal", zorder=9,
            bbox=dict(boxstyle="round,pad=0.12", fc=FILL[nm], ec="none", alpha=0.85))
p = P(0.38 * K, 270)
ax.text(p[0], p[1], "Hilus", ha="center", va="center", fontsize=S.SMALL + 1, color=S.REGION["Hilus"], fontweight="bold", zorder=9)

# ------------------------------------------------------------------ entorhinal inputs: LEC to the outer, MEC to the middle third
UPPER_END, LOWER_END = A0 + 6, A1 - 6
for nm, y, r, col in (("LEC", CY + 0.66 * K, (R_M + R_O) / 2, S.INK), ("MEC", CY - 0.66 * K, (R_I + R_M) / 2, "#5D6672")):
    ax.add_patch(FancyBboxPatch((0.04, y - 0.2), 0.72, 0.4, boxstyle="round,pad=0,rounding_size=0.08", fc="white", ec=col, lw=1.3, zorder=8))
    ax.text(0.40, y, nm, ha="center", va="center", fontsize=S.NOTE + 0.5, fontweight="bold", color=col, zorder=9)
    e = P(r, 180)
    ax.plot([0.76, e[0]], [y, e[1]], c=col, lw=1.7, zorder=7, solid_capstyle="round")
    for t_end in (UPPER_END, LOWER_END):
        thv = np.linspace(180, t_end, 120)
        pts = np.array([P(r, t) for t in thv])
        ax.plot(pts[:, 0], pts[:, 1], c=col, lw=1.7, zorder=7)
        ax.add_patch(FancyArrowPatch(tuple(pts[-4]), tuple(pts[-1]), arrowstyle="-|>", mutation_scale=10, lw=1.7, color=col, zorder=7))

# ------------------------------------------------------------------ the hilar SST (HIPP) cell and its axon in the outer third
SS = 0.072 * K                                        # one unit of the cell's frame, inches
sth = 196                                         # it sits in the hilus, dendrites along the blades (tangential)
s0 = P(0.36 * K, sth)
tang = np.array([-np.sin(np.radians(sth)), np.cos(np.radians(sth))])
Ce.sst(ax, Ce.frame(s0, U(sth) * SS, tang * SS), z=6, spine_lw=0.45)
R_AX = R_M + 0.17 * K                                 # the outer third, beside the LEC fibres
for t_in, t_lo, t_hi in ((150, A0 + 8, 168), (238, 208, A1 - 8)):
    a = P(R_AX, t_in)
    Ce.axon(ax, [s0, P(0.62 * K, (sth + t_in) / 2), P(R_G + 0.05 * K, t_in + (6 if t_in < 180 else -6)), a], Ce.SST_C, lw=1.0, z=6)
    for dr, ph in ((0.0, 0), (0.07 * K, 1), (-0.06 * K, 2)):           # a plexus: three strands along the outer third
        thv = np.linspace(t_lo, t_hi, 90)
        rr = R_AX + dr + 0.018 * K * np.sin(np.radians(thv) * 9 + ph)
        pts = np.column_stack([CX + rr * np.cos(np.radians(thv)), CY + rr * np.sin(np.radians(thv))])
        ax.plot(pts[:, 0], pts[:, 1], c=Ce.SST_C, lw=0.9 if dr == 0 else 0.6, zorder=6, alpha=1 if dr == 0 else 0.8)
    for t in np.linspace(t_lo + 6, t_hi - 6, 4):                  # inhibitory terminals on the granule cells' outer dendrites
        q = P(R_AX, t)
        b = q - U(t) * 0.075 * K
        n = np.array([-U(t)[1], U(t)[0]]) * 0.05 * K
        ax.plot([q[0], b[0]], [q[1], b[1]], c=Ce.SST_C, lw=1.4, zorder=6)
        ax.plot([b[0] - n[0], b[0] + n[0]], [b[1] - n[1], b[1] + n[1]], c=Ce.SST_C, lw=2.4, solid_capstyle="butt", zorder=6)

# ------------------------------------------------------------------ the PV basket cell and its basket around granule somata
PS = 0.105 * K
pth = 122
p0 = P(R_H - 0.04 * K, pth)
tang = np.array([-np.sin(np.radians(pth)), np.cos(np.radians(pth))])
Ce.pv(ax, Ce.frame(p0, U(pth) * PS, -tang * PS), z=6)
import matplotlib.patheffects as pe  # noqa: E402
near = []                                         # v9: three granule cells beside it, at least 7 deg apart, so the cups
for t in GC_SOMA[np.argsort(np.abs(GC_SOMA - pth))]:   # around their bodies don't pile up (the somata sit ~4 deg apart)
    if abs(t - pth) > 4 and all(abs(t - u) >= 7 for u in near):
        near.append(float(t))
    if len(near) == 3:
        break
for t in near:
    c = P(R_SOMA + 0.015 * K, t)
    Ce.axon(ax, [p0 + U(pth) * 0.04 * K, P(R_H + 0.0, (t + pth) / 2), P(R_SOMA - 0.06 * K, t)], Ce.PV_C, lw=0.9, z=6.5)
    ax.add_patch(Arc(tuple(c), 0.13 * K, 0.13 * K, angle=t, theta1=95, theta2=265, color=Ce.PV_C, lw=1.8, zorder=7,
                     path_effects=[pe.withStroke(linewidth=3.2, foreground="white", alpha=0.9)]))

# ------------------------------------------------------------------ a mossy fibre: a granule cell's axon through the hilus to CA3
MF_TH = float(GC_SOMA[np.argmin(np.abs(GC_SOMA - 141))])       # v9: from a granule cell that is drawn
mf = np.array([P(R_SOMA - 0.02 * K, MF_TH), P(0.5 * K, 120), (CX + 0.12 * K, CY + 0.15 * K), (CX + 0.9 * K, CY + 0.12 * K),
               (CX + 1.52 * K, CY + 0.12 * K)])
Ce.axon(ax, mf, S.GC, lw=1.4, z=4, ls=(0, (3, 2)))
ax.add_patch(FancyArrowPatch(tuple(mf[-2] + [0.45, 0]), tuple(mf[-1] + [0.04, 0]), arrowstyle="-|>", mutation_scale=10, lw=1.4,
                             color=S.GC, zorder=4))
ax.text(CX + 1.52 * K + 0.1, CY + 0.12 * K, "CA3", ha="left", va="center", fontsize=S.NOTE + 0.5, fontweight="bold", color=S.SOFT)

# ------------------------------------------------------------------ names, and what KCNT1 gain of function does to each (I_fI)
LX = CX + 1.0 * K
pv_lab = p0 + U(pth) * 0.02
ax.plot([pv_lab[0] + 0.09, LX - 0.06], [pv_lab[1] + 0.02, CY + 0.78 * K], c=Ce.PV_C, lw=0.8, zorder=3)
ax.text(LX, CY + 0.78 * K, "PV basket cell", ha="left", va="bottom", fontsize=S.NOTE + 0.5, fontweight="bold", color=S.PV)
ax.text(LX, CY + 0.78 * K - 0.03, "fires more in Het,\nless in Hom", ha="left", va="top", fontsize=S.SMALL + 0.5, color=S.PV, linespacing=1.0)
ax.plot([s0[0] + 0.12, LX - 0.06], [s0[1] - 0.06, CY - 0.5 * K], c=S.SST, lw=0.8, zorder=3)
ax.text(LX, CY - 0.5 * K, "SST (HIPP) cell", ha="left", va="bottom", fontsize=S.NOTE + 0.5, fontweight="bold", color=S.SST)
ax.text(LX, CY - 0.5 * K - 0.03, "fires less in\nHet and Hom", ha="left", va="top", fontsize=S.SMALL + 0.5, color=S.SST, linespacing=1.0)
g = P(R_O + 0.12, 238)
ax.text(g[0], g[1], "granule cells", ha="right", va="top", fontsize=S.NOTE, fontweight="bold", color=S.GC)
# legend: excites, inhibits
lx, ly = 0.1, 0.16
ax.add_patch(FancyArrowPatch((lx, ly), (lx + 0.36, ly), arrowstyle="-|>", mutation_scale=9, lw=1.4, color=S.INK))
ax.text(lx + 0.44, ly, "excites", va="center", fontsize=S.SMALL + 0.5, color=S.SOFT)
ax.plot([lx + 1.12, lx + 1.42], [ly, ly], c=S.INK, lw=1.4)
ax.plot([lx + 1.42, lx + 1.42], [ly - 0.05, ly + 0.05], c=S.INK, lw=2.4, solid_capstyle="butt")
ax.text(lx + 1.5, ly, "inhibits", va="center", fontsize=S.SMALL + 0.5, color=S.SOFT)
S.save(fig, os.path.join(HERE, "out", "I_circuit.png"))
print("I_circuit: %d granule-cell tiles, %d somata drawn" % (len(tiles), len(GC_SOMA)))
