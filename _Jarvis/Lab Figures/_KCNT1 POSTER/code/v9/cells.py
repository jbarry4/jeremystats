"""The cells on every figure of the poster (v7).

1. The lab's own drawings (Opening4paperAndPoster.pdf, the PTEN opening figure, panel D; cells_extract.py): green CA1
   pyramidal cells and pink granule cells, as the vector paths they are drawn with.
     group(ax, kind, x, y_soma, y_end, ...)   kind 'pyr', 'gc_up' (upper blade: somata below, dendrites up) or 'gc_down'
                                               (lower blade): somata on y_soma, dendrites to y_end, any axis direction
     group_arc(ax, kind, centre, r_soma, r_end, th0, th1)   the same group bent along a blade (polar)
2. SST and PV interneurons drawn the same way (thin, slightly wandering, tapering dendrites as filled shapes; a solid soma),
   each after its real form:
     sst(...)  a hilar SST cell (HIPP): a multipolar soma in the hilus, long spiny dendrites that stay in the hilus, and
               (where a figure draws it) an axon that climbs to the outer molecular layer and spreads along it
     pv(...)   a PV basket cell: a pyramid-shaped soma at the granule layer's hilar border, smooth dendrites up through the
               granule and molecular layers and down into the hilus, an axon that wraps the granule cells' somata
   They are generated once from fixed seeds, so every figure gets the same two cells.

Coordinates: a cell is drawn in its own frame (soma at 0, 0; +y = toward the molecular layer; one unit = the soma's width)
and placed with `frame(origin, up, right)`: origin in data units, `up` and `right` the data-space vectors one unit of the
cell's y and x become. That works on any axes, including depth axes that run downward."""
import os
import numpy as np
from matplotlib.path import Path
from matplotlib.patches import PathPatch, Polygon
import style as S

HERE = os.path.dirname(os.path.abspath(__file__))
_D = np.load(os.path.join(HERE, "data", "cells_open.npz"))
GREEN = "#009C00"                     # the drawings' own colours, (0, 0.61, 0) and (1, 0.43, 0.405)
PINK = "#FF6E67"
SST_C = "#E29A00"                     # the interneurons, as saturated as the lab's cells: amber and blue
PV_C = "#3D63D6"
COL = {"pyr": GREEN, "gc_up": PINK, "gc_down": PINK}


# ============================================================================== the lab's drawings
def _src(kind):
    v, c, bb = _D[kind + "_v"], _D[kind + "_c"], _D[kind + "_bbox"]
    soma = float(_D[kind + "_soma"])
    top, bot = _D[kind + "_ends"]
    end = float(top) if kind == "gc_up" else float(bot)      # where the dendrites end: up for gc_up, down for the others
    return v, c, bb, soma, end


def _patch(ax, verts, codes, color, z, alpha=1.0, clip=False):
    p = PathPatch(Path(verts, codes), fc=color, ec="none", lw=0, zorder=z, alpha=alpha)
    p.set_clip_on(clip)
    ax.add_patch(p)
    return p


def group(ax, kind, x, y_soma, y_end, width=None, color=None, z=5, alpha=1.0, flipx=False, xscale=None, clip=False):
    """The lab's group of cells with somata on y_soma and dendrite tips at y_end (data units, either direction).
    width: the group's width in x data units; default keeps its proportions, for axes whose x and y units are the same on
    paper (or give xscale = data-x units per data-y unit)."""
    v, c, bb, soma, end = _src(kind)
    sy = (y_end - y_soma) / (end - soma)
    cx = (bb[0] + bb[2]) / 2
    if width is not None:
        sx = width / (bb[2] - bb[0])
    else:
        sx = abs(sy) * (xscale if xscale else 1.0)
    X = x + (v[:, 0] - cx) * sx * (-1 if flipx else 1)
    Y = y_soma + (v[:, 1] - soma) * sy
    return _patch(ax, np.column_stack([X, Y]), c, color or COL[kind], z, alpha, clip=clip)


def group_arc(ax, kind, centre, r_soma, r_end, th0, th1=None, color=None, z=5, alpha=1.0, flipx=False):
    """The group bent along a blade: somata on the circle r_soma (data units, around centre), dendrite tips at r_end,
    spread from angle th0 to th1 (degrees; default: the drawing's own proportions at r_soma)."""
    v, c, bb, soma, end = _src(kind)
    k = (r_end - r_soma) / (end - soma)                      # data units per pt, radially
    if th1 is None:
        th1 = th0 + np.degrees(abs(k) * (bb[2] - bb[0]) / r_soma)
    u = (v[:, 0] - bb[0]) / (bb[2] - bb[0])
    if flipx:
        u = 1 - u
    th = np.radians(th0 + u * (th1 - th0))
    r = r_soma + (v[:, 1] - soma) * k
    P = np.column_stack([centre[0] + r * np.cos(th), centre[1] + r * np.sin(th)])
    return _patch(ax, P, c, color or COL[kind], z, alpha), th1


def soma_xs(kind):
    """where the group's somata sit across its width (0-1), from its drawing: the lowest (gc_up) / highest points' x."""
    v, c, bb, soma, end = _src(kind)
    near = np.abs(v[:, 1] - soma) < 2.2
    xs = np.sort(v[near, 0])
    groups_, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] > 1.0:
            groups_.append(np.mean(cur)); cur = [x]
        else:
            cur.append(x)
    groups_.append(np.mean(cur))
    return (np.array(groups_) - bb[0]) / (bb[2] - bb[0])


# ============================================================================== SST and PV, in the same hand
def frame(origin, up, right):
    """a cell frame: local (x, y) -> origin + x * right + y * up (all in data units)."""
    o, u, r = (np.asarray(a, float) for a in (origin, up, right))
    return lambda P: o + np.asarray(P)[..., :1] * r + np.asarray(P)[..., 1:2] * u


def _line(p0, ang, L, rng, n=40, wig=0.05, bend=0.0):
    """a dendrite's centre line: from p0 heading `ang` (deg), length L, wandering a little (smooth, seeded)."""
    s = np.linspace(0, 1, n)
    f1, f2 = rng.uniform(1.2, 2.2), rng.uniform(2.8, 4.5)
    ph1, ph2 = rng.uniform(0, 2 * np.pi, 2)
    lat = wig * L * (0.65 * np.sin(2 * np.pi * f1 * s + ph1) + 0.35 * np.sin(2 * np.pi * f2 * s + ph2))
    lat -= lat[0]
    a = np.radians(ang + bend * s)                            # a slow curve
    d = np.column_stack([np.cos(a), np.sin(a)])
    steps = d * (L / (n - 1))
    cl = np.vstack([[0, 0], np.cumsum(steps[:-1], 0)]) + np.asarray(p0, float)
    nrm = np.column_stack([-d[:, 1], d[:, 0]])
    return cl + nrm * lat[:, None]


def _ribbon(cl, w0, w1):
    """the filled shape of a tapering neurite along centre line cl."""
    d = np.gradient(cl, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
    nrm = np.column_stack([-d[:, 1], d[:, 0]])
    w = np.linspace(w0, w1, len(cl))[:, None] / 2
    return np.vstack([cl + nrm * w, (cl - nrm * w)[::-1]])


def _tree(p0, ang, L, w0, rng, depth=0, spec=None, spines=0.0, out=None, wig=0.05, bend=0.0):
    """a dendrite with its branches: spec = list of (fraction along, angle offset, length fraction) for this segment."""
    out = out if out is not None else {"poly": [], "spines": []}
    cl = _line(p0, ang, L, rng, wig=wig, bend=bend)
    w1 = max(w0 * 0.28, 0.05)
    out["poly"].append(_ribbon(cl, w0, w1))
    if spines:
        n = int(L / spines)
        for k in range(2, n):
            i = int(k / n * (len(cl) - 1))
            d = cl[min(i + 1, len(cl) - 1)] - cl[max(i - 1, 0)]
            d /= np.linalg.norm(d) + 1e-12
            nrm = np.array([-d[1], d[0]]) * (1 if k % 2 else -1)
            wloc = w0 + (w1 - w0) * i / (len(cl) - 1)
            ln = rng.uniform(0.10, 0.17)
            a = cl[i] + nrm * wloc * 0.4
            out["spines"].append(np.array([a, a + nrm * ln + d * rng.uniform(-0.04, 0.04)]))
    for (f, da, lf) in (spec or []):
        i = int(f * (len(cl) - 1))
        d = cl[min(i + 1, len(cl) - 1)] - cl[i]
        a0 = np.degrees(np.arctan2(d[1], d[0]))
        wb = (w0 + (w1 - w0) * f) * 0.75
        _tree(cl[i], a0 + da, L * lf, wb, rng, depth + 1, None, spines, out, wig, bend * 0.5)
    return out


def _soma(rx, ry, lobes, rng, n=90, tri=0.0):
    """a soma outline: an ellipse with a few gentle lobes where dendrites leave; tri > 0 pulls it into a pyramid."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = np.ones_like(t)
    for (ang, amp) in lobes:
        r += amp * np.exp(-((np.angle(np.exp(1j * (t - np.radians(ang))))) / 0.45) ** 2)
    P = np.column_stack([rx * r * np.cos(t), ry * r * np.sin(t)])
    if tri:
        P[:, 0] *= 1 - tri * (P[:, 1] / ry + 1) / 2 * 0.75     # narrower toward the top: a pyramid
    return P


def _build_sst(seed=7):
    rng = np.random.default_rng(seed)
    soma = _soma(0.62, 0.44, [(10, 0.25), (172, 0.25), (250, 0.18), (300, 0.15), (115, 0.12)], rng)
    out = {"poly": [], "spines": []}
    for (p0, ang, L, w0, spec, bend) in (
            ((0.6, 0.05), 6, 6.2, 0.30, [(0.38, -30, 0.38), (0.66, 26, 0.32)], -10),
            ((-0.6, 0.06), 176, 5.8, 0.30, [(0.42, 28, 0.36), (0.72, -24, 0.28)], 12),
            ((-0.22, -0.4), 246, 2.9, 0.24, [(0.55, 30, 0.42)], 0),
            ((0.25, -0.38), 298, 2.5, 0.22, [(0.6, -26, 0.4)], 0),
            ((-0.05, 0.42), 112, 1.9, 0.2, [], 0)):
        _tree(p0, ang, L, w0, rng, spec=spec, spines=0.38, out=out, wig=0.045, bend=bend)
    return soma, out


def _build_pv(seed=11, slim=1.0):
    rng = np.random.default_rng(seed)
    soma = _soma(0.56, 0.62, [(90, 0.32), (235, 0.15), (305, 0.15)], rng, tri=0.55)
    out = {"poly": [], "spines": []}
    for (p0, ang, L, w0, spec, bend) in (
            ((-0.06, 0.62), 98, 8.6, 0.30, [(0.42, 18, 0.45), (0.7, -16, 0.3)], -4),
            ((0.08, 0.6), 80, 8.2, 0.27, [(0.5, -20, 0.4)], 6),
            ((-0.36, -0.45), 238, 3.4, 0.22, [(0.55, -28, 0.4)], 0),
            ((0.36, -0.45), 302, 3.1, 0.22, [(0.5, 26, 0.45)], 0)):
        _tree(p0, ang, L, w0 * slim, rng, spec=spec, spines=0.0, out=out, wig=0.035, bend=bend)
    return soma, out


_SST, _PV = _build_sst(), _build_pv()
_PV_SLIM = {}


def _draw(ax, built, T, color, z, alpha=1.0, spines=True, spine_lw=0.5):
    soma, out = built
    for poly in out["poly"]:
        ax.add_patch(Polygon(T(poly), closed=True, fc=color, ec="none", lw=0, zorder=z, alpha=alpha))
    if spines and out["spines"]:
        from matplotlib.collections import LineCollection
        ax.add_collection(LineCollection([T(s) for s in out["spines"]], colors=color, linewidths=spine_lw, zorder=z, alpha=alpha,
                                         capstyle="round"))
    ax.add_patch(Polygon(T(soma), closed=True, fc=color, ec="none", lw=0, zorder=z + 0.1, alpha=alpha))


def sst(ax, T, color=SST_C, z=6, alpha=1.0, spines=True, spine_lw=0.5):
    """a hilar SST (HIPP) cell, soma and spiny dendrites, in frame T (see frame)."""
    _draw(ax, _SST, T, color, z, alpha, spines, spine_lw)


def pv(ax, T, color=PV_C, z=6, alpha=1.0, slim=1.0):
    """a PV basket cell, soma and smooth dendrites, in frame T. slim < 1 thins the dendrites (v9: the depth columns, where
    the cell is drawn tall, so its dendrites stay in proportion to the granule cells')."""
    if slim != 1.0 and slim not in _PV_SLIM:
        _PV_SLIM[slim] = _build_pv(slim=slim)
    _draw(ax, _PV if slim == 1.0 else _PV_SLIM[slim], T, color, z, alpha, spines=False)


def axon(ax, pts, color, lw=0.8, z=5, wig=0.0, seed=0, alpha=1.0, ls="-"):
    """a thin axon along the given points (data units), smoothed, optionally wandering a little."""
    pts = np.asarray(pts, float)
    t = np.linspace(0, 1, len(pts))
    tt = np.linspace(0, 1, 200)
    from scipy.interpolate import CubicSpline
    P = np.column_stack([CubicSpline(t, pts[:, 0])(tt), CubicSpline(t, pts[:, 1])(tt)])
    if wig:
        rng = np.random.default_rng(seed)
        d = np.gradient(P, axis=0)
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
        nrm = np.column_stack([-d[:, 1], d[:, 0]])
        f, ph = rng.uniform(5, 9), rng.uniform(0, 2 * np.pi)
        P = P + nrm * (wig * np.sin(2 * np.pi * f * tt + ph))[:, None]
    ax.plot(P[:, 0], P[:, 1], c=color, lw=lw, zorder=z, alpha=alpha, solid_capstyle="round", ls=ls)
    return P


def extent(kind):
    """a built interneuron's extent in its own frame: (xmin, xmax, ymin, ymax)."""
    soma, out = _SST if kind == "sst" else _PV
    P = np.vstack([soma] + out["poly"])
    return P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max()


# ============================================================================== v9: the dentate gyrus on a depth axis
# One set of rules for every depth column on the poster, after Seahorse's knowledge base (kb.py) and its 3D model:
#   granule cells  both blades drawn the SAME size (one scale, k), the lower blade the upper's mirror image
#   PV basket      soma at each granule layer's hilar border (Seahorse puts its traced basket cell in the lower blade's
#                  layer, gcl2), dendrites out through the granule and molecular layers and a few into the hilus, axon a
#                  basket around the granule cells' bodies
#   SST (HIPP)     soma and spiny dendrites in the hilus; where drawn, its axon climbs to the outer third of the molecular
#                  layer of both blades and spreads along it
GC_TIP, GC_BODY = 23.0, 5.4          # the lab's granule-cell drawing, in its own pt: soma line to tips; length of the bodies
GC_BODY_X = {"gc_up": [0.216, 0.37, 0.503, 0.628, 0.717], "gc_down": [0.284, 0.372, 0.497, 0.63, 0.787]}
PV_TOP, PV_SOMA = 9.18, 0.2           # the PV drawing: its apical tips (cell units); its soma centre this far into the hilus


def blade_k(gcl, tip):
    """the scale (data units per pt of the drawing) that puts the bodies' centres on gcl and the tips on tip."""
    return abs(tip - gcl) / (GC_TIP + GC_BODY / 2)


def blade(ax, kind, x, gcl, toward, k, xscale=1.0, z=5, alpha=1.0, flipx=False, clip=False):
    """one blade's granule cells on a depth axis: bodies centred on gcl, dendrites `toward` (+1/-1 in data y) its molecular
    layer, at scale k (give both blades the same k). Returns where things landed."""
    s = float(np.sign(toward))
    soma_line = gcl + s * k * GC_BODY / 2
    tip = soma_line + s * k * GC_TIP
    group(ax, kind, x, soma_line, tip, xscale=xscale, z=z, alpha=alpha, flipx=flipx, clip=clip)
    v, c, bb, soma, end = _src(kind)
    wpt = bb[2] - bb[0]
    us = GC_BODY_X[kind] if not flipx else [1 - u for u in GC_BODY_X[kind]]
    return dict(k=k, s=s, gcl=gcl, tip=tip, edge=gcl - s * k * GC_BODY / 2, half_w=0.5 * wpt * k * xscale,
                bodies=[x + (u - 0.5) * wpt * k * xscale for u in us], body_hw=0.8 * k * xscale, body_hh=1.2 * k,
                bulb=gcl - s * 0.6 * k)                 # the bodies' round ends (the drawing's somata), toward the hilus


def pv_basket(ax, b, x, z=6, mirror=False, cups=3, lw=0.75, alpha=1.0, slim=0.6):
    """a PV basket cell for blade b (from blade()): soma at the granule layer's hilar edge, apical dendrites out to the
    granule cells' tips, its axon cupping the `cups` granule-cell bodies nearest it."""
    s = b["s"]
    pu = abs(b["tip"] - b["edge"]) / (PV_TOP - PV_SOMA)
    y0 = b["edge"] - s * PV_SOMA * pu
    pv(ax, frame((x, y0), (0, s * pu), (-pu if mirror else pu, 0)), z=z, alpha=alpha, slim=slim)
    if cups:
        near = sorted(b["bodies"], key=lambda bx: abs(bx - x))[:cups + 1]
        w, h = b["body_hw"], b["body_hh"]
        n = 0
        for bx in near:
            if abs(bx - x) < 1.2 * w or n == cups:     # the one it sits under is wrapped by the soma itself
                continue
            n += 1
            ph = np.radians(np.linspace(-35, 215, 40))          # a basket: a cup around the body's round end
            P = np.column_stack([bx + 1.55 * w * np.cos(ph), b["bulb"] - s * 1.5 * h * np.sin(ph)])
            ax.plot(P[:, 0], P[:, 1], c=PV_C, lw=lw * 1.25, zorder=z + 0.2, alpha=alpha, solid_capstyle="round")
            bot = (bx, b["bulb"] - s * 1.5 * h)
            axon(ax, [(x, y0), ((x + bx) / 2, bot[1] - s * 0.6 * h), bot], PV_C, lw=lw * 0.8, z=z + 0.1, alpha=alpha)
    return dict(pu=pu, y=y0)


def sst_axon(ax, x0, y0, b, xs, z=4.5, lw=0.7, alpha=0.95, seed=3):
    """the hilar SST cell's axon (soma at x0, y0) up through blade b's granule layer to its outer molecular layer, then along
    it from xs[0] to xs[1] (data x): where the lateral entorhinal input lands."""
    s, k = b["s"], b["k"]
    oml = b["tip"] - s * k * GC_TIP / 6.0             # the middle of the outer third
    xm = x0 + 0.35 * (xs[1] - x0)
    axon(ax, [(x0, y0), (x0 + 0.3 * (xm - x0), (y0 + b["edge"]) / 2), (xm, b["gcl"]), (xm + 0.02 * (xs[1] - xs[0]), oml)],
         SST_C, lw=lw, z=z, alpha=alpha)
    rng = np.random.default_rng(seed)
    for dy, w_ in ((0.0, lw), (0.45, lw * 0.75), (-0.45, lw * 0.75)):
        xx = np.linspace(xs[0], xs[1], 120)
        ph = rng.uniform(0, 2 * np.pi)
        yy = oml + s * dy * k * 2.2 + 0.35 * k * np.sin(np.linspace(0, 7 * np.pi, 120) + ph)
        ax.plot(xx, yy, c=SST_C, lw=w_, zorder=z, alpha=alpha * (1 if dy == 0 else 0.8), solid_capstyle="round")
    return oml
