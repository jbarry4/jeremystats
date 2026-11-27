"""The dorsal hippocampus as it really is at the probe: a coronal section through Jarvis Seahorse's 10 um laminae
(Allen CCFv3 2017 annotation, with the layers Seahorse derives inside it: kb.json 'lamina'), at AP -1.90 mm, the section
the m459 probe went down (64 contacts at ML 1.4 mm: CA1, the upper blade, the hilus, the lower blade).

v7: drawn as smooth vector shapes, not an upsampled label image. Each layer group's 10 um mask is cleaned (specks under
0.004 mm2 dropped, pinholes filled), blurred by 16 um (the tissue's outer edge by 22 um), upsampled 5x (cubic), and the
group is filled wherever it leads all the others: matplotlib's contourf of (this group - the best other group) at 0, so
neighbouring layers share one smooth border and print crisp at any size.

draw(ax, active, new, unit) paints it in the poster's colours: tissue at rest in greys, each active region in its own
colour (CA1 green, the blades pink, the hilus amber), the region that just joined outlined, the probe, and the hilar
interneuron firing or silent."""
import os
import numpy as np
from scipy.ndimage import gaussian_filter, zoom, label, binary_fill_holes
from matplotlib.patches import Polygon, Circle
import style as S

HERE = os.path.dirname(os.path.abspath(__file__))
_Z = np.load(os.path.join(HERE, "data", "atlas_section.npz"))
LAB = _Z["labels"]
UM = int(_Z["um"])
DV0, ML0 = int(_Z["origin_dv_um"]), int(_Z["origin_ml_um"])
PROBE_ML = 7100            # um (CCF): ML +1.4 mm

GROUP = {                  # lamina codes (kb.json) -> what the drawing colours
    "ca1_f": [10, 12, 13], "ca1_sp": [11], "ca23_f": [14, 16, 17, 18, 20, 21, 22], "ca23_sp": [15, 19],
    "ml1": [1, 2, 3], "gcl1": [4], "hil": [5], "gcl2": [6], "ml2": [7, 8, 9], "other": [23, 24, 25, 26, 27, 28]}
NAMES = list(GROUP)
REST = {"ca1_f": "#EEF1F4", "ca1_sp": "#BFC7D1", "ca23_f": "#EEF1F4", "ca23_sp": "#BFC7D1", "ml1": "#EEF1F4", "gcl1": "#BFC7D1",
        "hil": "#E2E6EB", "gcl2": "#BFC7D1", "ml2": "#EEF1F4", "other": "#F4F5F7"}
REGION_PARTS = {"CA1": ("ca1_f", "ca1_sp"), "Supra blade": ("ml1", "gcl1"), "Hilus": ("hil",), "Infra blade": ("ml2", "gcl2")}
SIGMA, UP = 1.6, 5          # the tissue's outer edge is smoothed 1.4x more (it carries the atlas's 10 um steps)


def tint(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(int(round(255 - (255 - v) * a)) for v in (r, g, b))


_CACHE = {}


def fields(crop):
    """per group: a smooth field that is > 0 exactly where the group leads (5x the atlas grid), and the grid in mm."""
    if crop in _CACHE:
        return _CACHE[crop]
    ml0, ml1, dv0, dv1 = crop
    j0, j1 = (dv0 - DV0) // UM, (dv1 - DV0) // UM
    k0, k1 = (ml0 - ML0) // UM, (ml1 - ML0) // UM
    L = LAB[j0:j1, k0:k1]
    masks = {"out": L == 0}
    for n in NAMES:
        m = np.isin(L, GROUP[n])
        lab_, nlab = label(m)
        if nlab:
            sizes = np.bincount(lab_.ravel())[1:]
            m = np.isin(lab_, 1 + np.flatnonzero(sizes >= 40))          # specks under 40 px (0.004 mm2) go
        holes = binary_fill_holes(m) & ~m
        hl, nh = label(holes)
        if nh:
            hs = np.bincount(hl.ravel())[1:]
            m = m | np.isin(hl, 1 + np.flatnonzero(hs < 12))            # pinholes filled
        masks[n] = m
    keys = list(masks)
    B = np.stack([zoom(gaussian_filter(masks[k].astype(float), SIGMA * (1.4 if k == "out" else 1.0)), UP, order=3) for k in keys])
    F = {}
    for k in keys:
        F[k] = union_field(B, keys, (k,))
    for r, parts in REGION_PARTS.items():
        F["region:" + r] = union_field(B, keys, parts)                 # a whole region (its parts together)
    ny, nx = B.shape[1:]
    X = (ml0 + (np.arange(nx) + 0.5) * UM / UP - PROBE_ML) / 1000.0
    Y = (dv0 + (np.arange(ny) + 0.5) * UM / UP) / 1000.0
    _CACHE[crop] = (F, X, Y)
    return _CACHE[crop]


def union_field(B, keys, parts):
    """> 0 where the best of `parts` beats the best of every other group."""
    inn = [i for i, k in enumerate(keys) if k in parts]
    out = [i for i, k in enumerate(keys) if k not in parts]
    return B[inn].max(0) - B[out].max(0)


def draw(ax, active=(), new=None, unit=None, crop=(5760, 8860, 1330, 2960), probe=True, labels=False, unit_xy=(7015, 2392),
         outline_new=True, scale=1.0):
    """active: regions in colour; new: the one that just joined (outlined); unit: 'firing', 'silent' or None."""
    F, X, Y = fields(crop)
    cols = {n: REST[n] for n in NAMES}
    for r in active:
        for part in REGION_PARTS[r]:
            strong = part in ("ca1_sp", "gcl1", "gcl2")
            cols[part] = S.REGION[r] if strong else (S.REGION_FILL[r] if part == "hil" else tint(S.REGION_FILL[r], 0.55))
    big = 10.0
    # the tissue first (one silhouette, so no seams show between layers), then every layer group on top
    ax.contourf(X, Y, -F["out"], levels=[0, big], colors=["#F4F5F7"], antialiased=True, zorder=1)
    for n in NAMES:
        cs = ax.contourf(X, Y, F[n], levels=[0, big], colors=[cols[n]], antialiased=True, zorder=1.5)
        cs.set_edgecolor(cols[n]); cs.set_linewidth(0.35 * scale)
    ax.contour(X, Y, F["out"], levels=[0], colors=["#8E99A6"], linewidths=[0.8 * scale], zorder=2)
    if new is not None and outline_new:            # the region that just joined: its own border, its parts together
        ax.contour(X, Y, F["region:" + new], levels=[0], colors=[S.REGION[new]], linewidths=[1.6 * scale], zorder=3)
    ext = [X[0], X[-1], Y[-1], Y[0]]
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")
    ax.axis("off")
    ml0, ml1, dv0, dv1 = crop
    if probe:
        top, tip = dv0 / 1000 - 0.08, 2.78
        ax.plot([0, 0], [top, tip], c=S.INK, lw=1.5 * scale, zorder=8, solid_capstyle="butt")
        ax.add_patch(Polygon([[-0.028, tip], [0.028, tip], [0, tip + 0.07]], closed=True, fc=S.INK, ec="none", zorder=8))
    if unit:
        ux, uy = (unit_xy[0] - PROBE_ML) / 1000, unit_xy[1] / 1000
        r = 0.068
        if unit == "firing":
            ax.add_patch(Circle((ux, uy), r, fc=S.SST_FILL, ec=S.INK, lw=0.8 * scale, zorder=9))
            for ang in (110, 160, 210):
                a = np.deg2rad(ang)
                ax.plot([ux + 1.55 * r * np.cos(a), ux + 2.5 * r * np.cos(a)], [uy - 1.55 * r * np.sin(a), uy - 2.5 * r * np.sin(a)],
                        c=S.SST_FILL, lw=1.3 * scale, solid_capstyle="round", zorder=9)
        else:
            ax.add_patch(Circle((ux, uy), r, fc="white", ec="#6F7A87", lw=0.9 * scale, zorder=9))
            d = r * 0.62
            ax.plot([ux - d, ux + d], [uy - d, uy + d], c="#4A5260", lw=1.1 * scale, zorder=10)
            ax.plot([ux - d, ux + d], [uy + d, uy - d], c="#4A5260", lw=1.1 * scale, zorder=10)
    if labels:
        ax.text(-1.05, 1.62, "CA1", fontsize=S.NOTE, color=S.SOFT, fontweight="bold", ha="center", va="center", zorder=11)
        ax.text(-0.95, 2.78, "DG", fontsize=S.NOTE, color=S.SOFT, fontweight="bold", ha="center", va="center", zorder=11)
        ax.text(1.55, 2.86, "CA3", fontsize=S.NOTE, color=S.SOFT, fontweight="bold", ha="center", va="center", zorder=11)
    return ext
