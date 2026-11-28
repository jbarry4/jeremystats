"""The lab's own cell drawings, lifted from the PTEN paper/poster opening figure (Poster Resources/Opening4paperAndPoster.pdf,
panel D's depth labels): the green CA1 pyramidal cells (drawn there as two overlapping copies of one group) and the pink
granule cells, once with their somata at the bottom (the upper blade, dendrites up) and once at the top (the lower blade,
dendrites down). They are vector paths (cubic Beziers, even-odd fill: the small closed loops are the gaps where dendrites
cross); this keeps every control point, so cells.py can draw them at any size, stretched to the layers they span, bent
along a blade, as sharp as the type.

Writes data/cells_open.npz: for each drawing its vertices (pt, y down as in the PDF) and path codes, re-wound so the
nonzero rule matplotlib fills with gives the PDF's even-odd result (outlines one way, the gaps the other), and for each
group where its somata sit and where its dendrites end (rows where the rendered drawing is densest / last inked)."""
import os
import numpy as np
import fitz
from matplotlib.path import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\Opening4paperAndPoster.pdf"
OUT = os.path.join(HERE, "data", "cells_open.npz")
doc = fitz.open(SRC)
page = doc[0]
RD = fitz.Rect(40, 150, 80, 295)                 # panel D's depth labels


def subpaths(d):
    """[(vertices, codes)] per subpath; a new subpath wherever an item does not start where the last one ended."""
    out, verts, codes, last = [], [], [], None
    for it in d["items"]:
        pts = it[1:5] if it[0] == "c" else it[1:3]
        p1 = pts[0]
        if last is None or abs(p1.x - last.x) > 1e-3 or abs(p1.y - last.y) > 1e-3:
            if verts:
                out.append((np.array(verts, float), np.array(codes, np.uint8)))
            verts, codes = [(p1.x, p1.y)], [Path.MOVETO]
        if it[0] == "c":
            verts += [(p.x, p.y) for p in pts[1:]]; codes += [Path.CURVE4] * 3
        elif it[0] == "l":
            verts.append((pts[1].x, pts[1].y)); codes.append(Path.LINETO)
        else:
            raise ValueError(it[0])
        last = pts[-1]
    if verts:
        out.append((np.array(verts, float), np.array(codes, np.uint8)))
    return out


def signed_area(v):
    x, y = v[:, 0], v[:, 1]
    return 0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def rewind(sps):
    """even-odd -> nonzero: a subpath nested inside an odd number of others turns one way, the rest the other."""
    polys = [Path(v) for v, _ in sps]
    out = []
    for i, (v, c) in enumerate(sps):
        probe = v[len(v) // 2] if len(v) > 2 else v[0]
        depth = sum(1 for j, P in enumerate(polys) if j != i and P.contains_point(probe))
        want = 1 if depth % 2 == 0 else -1
        if np.sign(signed_area(v)) != want:          # reverse a Bezier chain: reverse the vertices, keep MOVETO first
            v = v[::-1].copy()
            c = np.concatenate([[Path.MOVETO], c[1:][::-1]])
        out.append((v, c))
    return out


def anchors(rect, color):
    """the rows (pt) where the drawing is densest (its somata) and its first and last inked rows."""
    z = 24
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=rect, alpha=False)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).astype(float)
    ink = np.linalg.norm(a - 255 * np.array(color)[None, None, :], axis=2) < 90
    rows = ink.sum(1)
    ys = rect.y0 + (np.arange(len(rows)) + 0.5) / z
    k = 9
    sm = np.convolve(rows, np.ones(k * z // 6) / (k * z // 6), mode="same")
    inked = np.flatnonzero(rows > 0)
    return float(ys[np.argmax(sm)]), float(ys[inked[0]]), float(ys[inked[-1]])


groups = {"pyr": [], "gc_up": [], "gc_down": []}
for d in page.get_drawings():
    if not d.get("fill") or not RD.intersects(d["rect"]):
        continue
    f = tuple(round(c, 2) for c in d["fill"])
    if f == (0.0, 0.61, 0.0):
        groups["pyr"].append(d)
    elif f[0] == 1.0 and abs(f[1] - 0.43) < 0.01:
        groups["gc_up" if d["rect"].y0 < 250 else "gc_down"].append(d)
out = {}
for k, ds in groups.items():
    V, Cc, idx = [], [], []
    for n, d in enumerate(ds):
        for v, c in rewind(subpaths(d)):
            V.append(v); Cc.append(c); idx.append(np.full(len(v), n))
    v = np.vstack(V)
    out[k + "_v"], out[k + "_c"], out[k + "_copy"] = v, np.concatenate(Cc), np.concatenate(idx).astype(np.int16)
    bb = fitz.Rect(v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max())
    col = ds[0]["fill"]
    soma, top, bot = anchors(bb, col)
    out[k + "_bbox"] = np.array([bb.x0, bb.y0, bb.x1, bb.y1])
    out[k + "_soma"], out[k + "_ends"] = soma, np.array([top, bot])
    print("%-7s %d drawing(s), %5d vertices, bbox %s, densest row (somata) %.2f, inked %.2f-%.2f" %
          (k, len(ds), len(v), np.round(out[k + "_bbox"], 2), soma, top, bot))
out["fill_pyr"] = np.array([0.0, 0.61, 0.0]); out["fill_gc"] = np.array([1.0, 0.43, 0.405])
np.savez_compressed(OUT, **out)
print("wrote", OUT)
