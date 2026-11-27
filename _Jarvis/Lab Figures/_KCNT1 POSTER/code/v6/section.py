"""The dorsal hippocampus as it really is at the probe: a coronal section through Jarvis Seahorse's 10 um laminae
(Allen CCFv3 2017 annotation, with the layers Seahorse derives inside it: kb.json 'lamina'), at AP -1.90 mm, the section
the m459 probe went down (64 contacts at ML 1.4 mm: CA1, the upper blade, the hilus, the lower blade).

draw(ax, active, new, unit) paints it in the poster's colours: tissue at rest in greys, each active region in its own
colour (CA1 green, the blades pink, the hilus amber), the region that just joined outlined, the probe, and the hilar
interneuron firing or silent."""
import os, json
import numpy as np
from scipy.ndimage import gaussian_filter, zoom, label
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


def tint(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(int(round(255 - (255 - v) * a)) for v in (r, g, b))


def _rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


_CACHE = {}


def labels_up(crop, up=6):
    """The section's group labels, smoothed and upsampled `up` times (one-hot, blurred 10 um, argmax): smooth borders."""
    key = (crop, up)
    if key in _CACHE:
        return _CACHE[key]
    ml0, ml1, dv0, dv1 = crop
    j0, j1 = (dv0 - DV0) // UM, (dv1 - DV0) // UM
    k0, k1 = (ml0 - ML0) // UM, (ml1 - ML0) // UM
    L = LAB[j0:j1, k0:k1]
    chans = [(L == 0).astype(float)] + [np.isin(L, GROUP[n]).astype(float) for n in NAMES]
    stack = np.stack([zoom(gaussian_filter(c, 1.0), up, order=1) for c in chans])
    g = stack.argmax(0)                       # 0 = outside, 1.. = NAMES
    _CACHE[key] = g
    return g


def draw(ax, active=(), new=None, unit=None, crop=(5760, 8860, 1330, 2960), probe=True, labels=False, unit_xy=(7015, 2392),
         outline_new=True, scale=1.0):
    """active: regions in colour; new: the one that just joined (outlined); unit: 'firing', 'silent' or None."""
    g = labels_up(crop)
    cols = {n: REST[n] for n in NAMES}
    for r in active:
        for part in REGION_PARTS[r]:
            strong = part in ("ca1_sp", "gcl1", "gcl2")
            cols[part] = S.REGION[r] if strong else (S.REGION_FILL[r] if part == "hil" else tint(S.REGION_FILL[r], 0.55))
    lut = np.vstack([_rgb("#FFFFFF")] + [_rgb(cols[n]) for n in NAMES])
    ml0, ml1, dv0, dv1 = crop
    ext = [(ml0 - PROBE_ML) / 1000, (ml1 - PROBE_ML) / 1000, dv1 / 1000, dv0 / 1000]    # mm, x = 0 at the probe, depth down
    ax.imshow(lut[g], extent=ext, interpolation="bilinear", zorder=1)
    # outlines: the tissue's edge, and the cell layers' edges
    ny, nx = g.shape
    X = np.linspace(ext[0], ext[1], nx)
    Y = np.linspace(ext[3], ext[2], ny)
    ax.contour(X, Y, (g > 0).astype(float), levels=[0.5], colors=["#8E99A6"], linewidths=[0.7 * scale], zorder=2)
    if new is not None and outline_new:
        idx = [NAMES.index(p) + 1 for p in REGION_PARTS[new]]
        m, n = label(np.isin(g, idx))
        if n > 1:                                   # keep the region itself, not the specks the smoothing leaves
            sizes = np.bincount(m.ravel())[1:]
            m = np.isin(m, 1 + np.flatnonzero(sizes >= 0.05 * sizes.max()))
        ax.contour(X, Y, (m > 0).astype(float), levels=[0.5], colors=[S.REGION[new]], linewidths=[1.5 * scale], zorder=3)
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")
    ax.axis("off")
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
