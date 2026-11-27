"""The lab's cell icons (the PTEN poster's theta figure and the NBH'25 poster's laminar figure), redrawn as vectors so they
print sharp at any size: a CA1 pyramidal cell (green triangle soma, basal dendrites up, apical trunk down to a tuft in
lacunosum-moleculare) and a dentate granule cell (pink oval soma, three dendrites fanning into the molecular layer).

Every icon is drawn in data units of an axes whose x and y units are the same length on paper (`icon_axes` makes one
that shares a trace or CSD panel's depth axis), so a cell can be stretched to span the layers it really spans."""
import numpy as np
from matplotlib.patches import Polygon, Ellipse
import style as S


def icon_axes(fig, x, y, w, h, ylim):
    """An axes at (x, y, w, h) inches whose y range is `ylim` (top, bottom) and whose x units are as long as its y units."""
    ax = S.ax_at(fig, x, y, w, h)
    span = abs(ylim[1] - ylim[0])
    ax.set_ylim(*ylim)
    ax.set_xlim(0, span * w / h)
    ax.axis("off")
    return ax


def _seg(ax, p0, p1, w, color, z):
    """A straight stroke of width w (data units) from p0 to p1 with square ends."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    n = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1.0) * w / 2
    ax.add_patch(Polygon([p0 + n, p1 + n, p1 - n, p0 - n], closed=True, fc=color, ec=color, lw=0.3, zorder=z, joinstyle="miter"))


def _taper(ax, p0, p1, w0, w1, color, z):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    u = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1.0)
    ax.add_patch(Polygon([p0 + u * w0 / 2, p1 + u * w1 / 2, p1 - u * w1 / 2, p0 - u * w0 / 2], closed=True, fc=color, ec=color, lw=0.3,
                         zorder=z))


def pyramidal(ax, x, y_soma, y_tuft, width=None, color=S.PYR_FILL, z=5, basal=True):
    """CA1 pyramidal cell. Soma centred at y_soma, apical dendrite toward y_tuft (either direction), tuft at its end.
    width: the soma's width (default: a seventh of the cell's height)."""
    s = np.sign(y_tuft - y_soma) or 1.0
    L = abs(y_tuft - y_soma)
    ws = width or L / 5.2
    P = lambda u, v: (x + u * ws, y_soma + s * v * ws)          # noqa: E731  local frame: v toward the tuft
    lw = 0.16 * ws
    top = [P(u, -0.55 - 0.10 * (1 - (2 * u) ** 2)) for u in np.linspace(-0.5, 0.5, 15)]
    ax.add_patch(Polygon(top + [P(0.0, 0.85)], closed=True, fc=color, ec=color, lw=0.3, zorder=z))
    if basal:
        _seg(ax, P(-0.40, -0.55), P(-0.78, -1.45), lw, color, z)
        _seg(ax, P(0.40, -0.55), P(0.78, -1.45), lw, color, z)
    split = L / ws - 1.25
    _taper(ax, P(0, 0.6), P(0, split), lw * 1.5, lw, color, z)
    _seg(ax, P(0, split), P(-0.62, L / ws), lw, color, z)
    _seg(ax, P(0, split), P(0.62, L / ws), lw, color, z)


def granule(ax, x, y_soma, y_tips, width=None, color=S.GC_FILL, z=5):
    """Dentate granule cell: oval soma at y_soma, three dendrites reaching y_tips (up for the upper blade, down for the lower)."""
    s = np.sign(y_tips - y_soma) or 1.0
    L = abs(y_tips - y_soma)
    ws = width or L / 3.1
    P = lambda u, v: (x + u * ws, y_soma + s * v * ws)          # noqa: E731
    ax.add_patch(Ellipse((x, y_soma), ws, 1.30 * ws, fc=color, ec=color, lw=0.3, zorder=z))
    lw = 0.20 * ws
    tip = L / ws
    for u0, u1 in ((-0.16, -0.62), (0.0, 0.0), (0.16, 0.62)):
        _taper(ax, P(u0, 0.45), P(u1, tip), lw * 1.15, lw * 0.85, color, z)


def granule_toward(ax, soma, tip, width, color=S.GC_FILL, z=5, spread=0.62):
    """A granule cell along any direction: soma at `soma`, dendrites fanning toward `tip` (for cells around a curved blade)."""
    soma, tip = np.asarray(soma, float), np.asarray(tip, float)
    d = tip - soma
    L = np.hypot(*d)
    d /= L
    n = np.array([-d[1], d[0]])
    ws = width
    P = lambda u, v: soma + u * ws * n + v * ws * d             # noqa: E731
    ang = np.degrees(np.arctan2(d[1], d[0]))
    ax.add_patch(Ellipse(soma, 1.30 * ws, ws, angle=ang, fc=color, ec=color, lw=0.3, zorder=z))
    lw = 0.20 * ws
    for u0, u1 in ((-0.16, -spread), (0.0, 0.0), (0.16, spread)):
        _taper(ax, P(u0, 0.45), P(u1, L / ws), lw * 1.15, lw * 0.85, color, z)


def interneuron(ax, x, y, r, color, z=6, ec=S.INK, lw=0.9):
    """An interneuron's soma: a round cell with a thin dark rim (the circuit's SST and PV cells)."""
    ax.add_patch(Ellipse((x, y), 2 * r, 2 * r, fc=color, ec=ec, lw=lw, zorder=z))
