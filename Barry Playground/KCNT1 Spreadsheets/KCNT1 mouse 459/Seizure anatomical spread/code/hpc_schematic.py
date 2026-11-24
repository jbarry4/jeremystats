import numpy as np
from matplotlib.path import Path
from matplotlib.patches import PathPatch, Polygon, FancyArrowPatch
COL = {"CA1": "#7b3294", "Upper blade": "#1b9e3a", "Hilus": "#d7301f", "Lower blade": "#2166ac"}
TINT = {"Upper blade": "#cfe9d4", "Lower blade": "#cddff0", "CA1": "#e6d6ee"}
GREY, GREY2 = "#c9c9c9", "#ececec"
def _bez(p0, p1, p2, p3, n=80):
    t = np.linspace(0, 1, n)[:, None]
    return (1-t)**3*np.array(p0) + 3*(1-t)**2*t*np.array(p1) + 3*(1-t)*t**2*np.array(p2) + t**3*np.array(p3)
def _ribbon(ax, pts, w, fc, z=1, ec="none"):
    d = np.gradient(pts, axis=0); nrm = np.c_[-d[:, 1], d[:, 0]]; nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    poly = np.vstack([pts + nrm * w / 2, (pts - nrm * w / 2)[::-1]])
    ax.add_patch(Polygon(poly, closed=True, fc=fc, ec=ec, lw=1.2, zorder=z, joinstyle="round"))
# geometry (coordinates 0..10 x 0..8)
CA = np.vstack([_bez((0.6, 5.4), (1.2, 8.0), (6.5, 8.3), (8.6, 6.7)), _bez((8.6, 6.7), (10.0, 5.6), (9.7, 3.4), (7.1, 3.95))[1:]])
CA1_PART = CA[:62]; CA3_PART = CA[61:]
UP = _bez((7.6, 4.95), (5.8, 5.55), (3.1, 5.6), (2.0, 4.2))
LO = _bez((2.0, 4.2), (2.9, 2.75), (5.6, 2.45), (7.6, 3.0))
def draw(ax, active=(), new=None, interneurons="normal", probe_x=5.6, labels=True, ec=True):
    ax.set_xlim(0, 10.2); ax.set_ylim(1.2, 9.0); ax.set_aspect("equal"); ax.axis("off")
    on = lambda r: r in active
    # molecular layers (dendrites) as tinted bands outside each blade
    _ribbon(ax, UP + [0, 0.42], 0.75, TINT["Upper blade"] if on("Upper blade") else GREY2, z=1)
    _ribbon(ax, LO - [0, 0.42], 0.75, TINT["Lower blade"] if on("Lower blade") else GREY2, z=1)
    # hilus fill
    hil = np.vstack([UP, LO[1:], _bez((7.6, 3.0), (8.15, 3.45), (8.15, 4.45), (7.6, 4.95))[1:]])
    ax.add_patch(Polygon(hil, closed=True, fc=(COL["Hilus"] if on("Hilus") else GREY2), alpha=(0.55 if on("Hilus") else 1), ec="none", zorder=1))
    # CA1/CA3 pyramidal layer
    _ribbon(ax, CA1_PART, 0.42, COL["CA1"] if on("CA1") else GREY, z=2)
    _ribbon(ax, CA3_PART, 0.42, GREY, z=2)
    # granule cell layers with cell bodies
    for pts, r in ((UP, "Upper blade"), (LO, "Lower blade")):
        _ribbon(ax, pts, 0.34, COL[r] if on(r) else GREY, z=3)
        for p in pts[4:-2:6]: ax.plot(*p, "o", ms=3.2, mfc="white", mec="none", alpha=.75, zorder=4)
    # crest (shared)
    # mossy fibres (DG -> CA3)
    mf = _bez((5.6, 4.4), (6.6, 4.6), (7.6, 4.6), (8.9, 5.0))
    ax.plot(mf[:, 0], mf[:, 1], c="#8c8c8c", lw=1.3, ls=(0, (3, 2)), zorder=2)
    # hilar interneurons
    for (x, y) in ((3.9, 4.0), (5.0, 3.6), (6.55, 4.25)):
        if interneurons == "active":
            ax.plot(x, y, "^", ms=13, mfc="#ffd23f", mec="k", mew=1.2, zorder=6)
        elif interneurons == "silent":
            ax.plot(x, y, "^", ms=13, mfc="white", mec="#777", mew=1.2, zorder=6); ax.plot(x, y + .02, "x", ms=9, c="#444", mew=2, zorder=7)
        else:
            ax.plot(x, y, "^", ms=13, mfc="#5a5a5a", mec="k", mew=.8, zorder=6)
    # perforant path from EC
    if ec: ax.add_patch(FancyArrowPatch((0.15, 2.0), (3.3, 5.75), connectionstyle="arc3,rad=-0.25", arrowstyle="-|>", mutation_scale=16, lw=1.8, color="#555", zorder=5))
    if ec: ax.add_patch(FancyArrowPatch((0.15, 2.0), (3.6, 1.95), connectionstyle="arc3,rad=0.12", arrowstyle="-|>", mutation_scale=16, lw=1.8, color="#555", zorder=5))
    # probe
    ax.plot([probe_x, probe_x], [8.95, 1.45], c="k", lw=2.2, zorder=8); ax.plot(probe_x, 1.45, "v", c="k", ms=9, zorder=8)
    # new-region emphasis
    if new == "Hilus":
        ax.add_patch(Polygon(hil, closed=True, fc="none", ec=COL["Hilus"], lw=14, alpha=.28, zorder=0, joinstyle="round"))
    if new == "Upper blade": _ribbon(ax, UP + [0, 0.3], 1.6, COL["Upper blade"] + "40", z=0)
    if new == "Lower blade": _ribbon(ax, LO - [0, 0.3], 1.6, COL["Lower blade"] + "40", z=0)
    if new == "CA1": _ribbon(ax, CA1_PART, 1.3, COL["CA1"] + "40", z=0)
    if labels:
        ax.text(1.6, 7.75, "CA1", fontsize=15, color=COL["CA1"] if on("CA1") else "#999", fontweight="bold")
        ax.text(9.65, 5.0, "CA3", fontsize=13, color="#999")
        if ec: ax.text(0.0, 1.35, "EC", fontsize=13, color="#555", fontweight="bold")
