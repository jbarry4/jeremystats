"""The hippocampus drawn once, for every schematic on the poster (seizure stages, intro circuit).

Geometry from the original seizure figure's hpc_schematic.py (Barry Playground/.../Seizure anatomical spread/code), redrawn in the
poster's colors: tissue at rest in two greys, an active region in its own color, a newly recruited region with a soft halo."""
import numpy as np
from matplotlib.patches import Polygon, FancyArrowPatch, Circle
import style as S

REST_LAYER = "#C5CCD5"    # cell layers at rest
REST_FIELD = "#ECEFF3"    # dendritic fields and hilus at rest
UNIT = "#D99A00"          # the hilar interneuron (amber), as in the firing-rate plot


def _bez(p0, p1, p2, p3, n=80):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 3 * np.array(p0) + 3 * (1 - t) ** 2 * t * np.array(p1) + 3 * (1 - t) * t ** 2 * np.array(p2) + t ** 3 * np.array(p3)


def _ribbon_poly(pts, w):
    d = np.gradient(pts, axis=0)
    nrm = np.c_[-d[:, 1], d[:, 0]]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    return np.vstack([pts + nrm * w / 2, (pts - nrm * w / 2)[::-1]])


def ribbon(ax, pts, w, fc, z=1, alpha=1.0, ec="none", lw=0):
    p = Polygon(_ribbon_poly(pts, w), closed=True, fc=fc, ec=ec, lw=lw, zorder=z, alpha=alpha, joinstyle="round", capstyle="round")
    ax.add_patch(p)
    return p


CA = np.vstack([_bez((0.6, 5.4), (1.2, 8.0), (6.5, 8.3), (8.6, 6.7)), _bez((8.6, 6.7), (10.0, 5.6), (9.7, 3.4), (7.1, 3.95))[1:]])
CA1_PART, CA3_PART = CA[:62], CA[61:]
UP = _bez((7.6, 4.95), (5.8, 5.55), (3.1, 5.6), (2.0, 4.2))
LO = _bez((2.0, 4.2), (2.9, 2.75), (5.6, 2.45), (7.6, 3.0))
HIL = np.vstack([UP, LO[1:], _bez((7.6, 3.0), (8.15, 3.45), (8.15, 4.45), (7.6, 4.95))[1:]])
NAMES = {"CA1": "CA1", "Supra blade": "Supra blade", "Hilus": "Hilus", "Infra blade": "Infra blade"}


def tint(hex_color, a):
    """hex color mixed with white (a = share of the color)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(int(round(255 - (255 - v) * a)) for v in (r, g, b))


def draw(ax, active=(), new=None, unit="rest", probe_x=5.6, labels=False, scale=1.0, probe=True):
    """active: regions in color; new: the region that just joined (halo); unit: 'firing', 'silent' or 'rest'."""
    R = S.REGION
    on = lambda r: r in active
    ax.set_xlim(0.1, 10.15)
    ax.set_ylim(1.55, 8.75)
    ax.set_aspect("equal")
    ax.axis("off")
    # halo for the region that just joined
    if new == "Hilus":
        c0 = HIL.mean(0)
        ax.add_patch(Polygon(c0 + (HIL - c0) * [1.07, 1.30], closed=True, fc=tint(R["Hilus"], 0.26), ec="none", zorder=0))
    elif new == "Supra blade":
        ribbon(ax, UP + [0, 0.33], 1.55, tint(R["Supra blade"], 0.28), z=0)
    elif new == "Infra blade":
        ribbon(ax, LO - [0, 0.33], 1.55, tint(R["Infra blade"], 0.28), z=0)
    elif new == "CA1":
        ribbon(ax, CA1_PART, 1.35, tint(R["CA1"], 0.25), z=0)
    # dendritic fields (molecular layers) and the hilus
    ribbon(ax, UP + [0, 0.42], 0.78, tint(R["Supra blade"], 0.30) if on("Supra blade") else REST_FIELD, z=1)
    ribbon(ax, LO - [0, 0.42], 0.78, tint(R["Infra blade"], 0.30) if on("Infra blade") else REST_FIELD, z=1)
    ribbon(ax, CA1_PART + [0, -0.45], 0.62, tint(R["CA1"], 0.22) if on("CA1") else REST_FIELD, z=1)
    ax.add_patch(Polygon(HIL, closed=True, fc=tint(R["Hilus"], 0.55) if on("Hilus") else REST_FIELD, ec="none", zorder=1))
    # cell layers
    ribbon(ax, CA1_PART, 0.40, R["CA1"] if on("CA1") else REST_LAYER, z=2)
    ribbon(ax, CA3_PART, 0.40, REST_LAYER, z=2)
    for pts, r in ((UP, "Supra blade"), (LO, "Infra blade")):
        ribbon(ax, pts, 0.36, R[r] if on(r) else REST_LAYER, z=3)
        for p in pts[5:-3:7]:
            ax.add_patch(Circle(p, 0.075, fc="white", ec="none", alpha=0.8, zorder=4))
    # mossy fibres
    mf = _bez((5.6, 4.35), (6.6, 4.55), (7.6, 4.55), (8.9, 5.0))
    ax.plot(mf[:, 0], mf[:, 1], c="#9AA3AE", lw=1.0 * scale, ls=(0, (2.5, 2)), zorder=2)
    # the hilar interneuron
    ux, uy = 4.45, 3.95
    if unit == "firing":
        ax.plot(ux, uy, "^", ms=11 * scale, mfc=UNIT, mec=S.INK, mew=0.9, zorder=6)
        for ang in (25, 90, 155):
            a = np.deg2rad(ang)
            ax.plot([ux + 0.42 * np.cos(a), ux + 0.62 * np.cos(a)], [uy + 0.42 * np.sin(a) + 0.05, uy + 0.62 * np.sin(a) + 0.05],
                    c=UNIT, lw=1.4 * scale, solid_capstyle="round", zorder=6)
    elif unit == "silent":
        ax.plot(ux, uy, "^", ms=11 * scale, mfc="white", mec="#7A8592", mew=1.0, zorder=6)
        ax.plot(ux, uy + 0.02, "x", ms=6.5 * scale, c="#4A5260", mew=1.4, zorder=7)
    else:
        ax.plot(ux, uy, "^", ms=11 * scale, mfc="#7A8592", mec=S.INK, mew=0.6, zorder=6)
    if probe:
        ax.plot([probe_x, probe_x], [8.7, 1.75], c=S.INK, lw=1.6 * scale, zorder=8, solid_capstyle="butt")
        ax.add_patch(Polygon([[probe_x - 0.13, 1.78], [probe_x + 0.13, 1.78], [probe_x, 1.5]], closed=True, fc=S.INK, ec="none", zorder=8))
    if labels:
        ax.text(1.05, 7.55, "CA1", fontsize=S.NOTE, color=S.SOFT, fontweight="bold", ha="center", zorder=9)
        ax.text(2.15, 2.25, "DG", fontsize=S.NOTE, color=S.SOFT, fontweight="bold", ha="center", zorder=9)
