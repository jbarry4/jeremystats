"""PTEN poster v5: reading figures back out of vector PDFs (the menus' pages, the report's figures, the opening figure),
so they can be redrawn in the poster's own look. The user: "try your best to rerender things even if you don't have the
data... keep the general shape and reproduce the graph"; "as long as the p values and specific stats are good".

  page(pdf)                     the first page
  paths(pg, clip)               every vector path that touches clip: type, stroke, fill, width, opacity, points, rect
  glyph_words(pg, clip)         text drawn as glyph outlines (the report's figures), clustered into words: rects
  markers(ps, maxsize)          small closed paths (dots, diamonds, squares) -> centre, size, fill, stroke, shape
  near(c, ref, tol)             colour match
  Axis(p0, v0, p1, v1, log)     page points <-> data values, from two ticks
Every figure script calibrates its axes from tick positions it finds here and the tick values printed on the source."""
import math
import numpy as np
import fitz


def page(pdf):
    return fitz.open(pdf)[0]


def near(c, ref, tol=0.06):
    return c is not None and ref is not None and max(abs(a - b) for a, b in zip(c, ref)) <= tol


def _pts(items):
    pts = []
    for it in items:
        k = it[0]
        if k == "l":
            pts += [(it[1].x, it[1].y), (it[2].x, it[2].y)]
        elif k == "c":
            pts += [(it[1].x, it[1].y), (it[2].x, it[2].y), (it[3].x, it[3].y), (it[4].x, it[4].y)]
        elif k == "re":
            r = it[1]
            pts += [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        elif k == "qu":
            q = it[1]
            pts += [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)]
    out = np.array(pts, float) if pts else np.zeros((0, 2))
    if len(out) > 1:
        keep = np.r_[True, np.abs(np.diff(out, axis=0)).sum(1) > 1e-6]
        out = out[keep]
    return out


def _visible_drawings(pg):
    """the page's paths with their clipping applied: the menu pages draw some report figures several times over, each
    copy clipped to its own panel, so only the paths their clip leaves on the page count."""
    out, stack = [], []
    for g in pg.get_drawings(extended=True):
        lev = g.get("level", 0)
        while stack and stack[-1][0] >= lev:
            stack.pop()
        if g["type"] == "clip":
            stack.append((lev, fitz.Rect(g["scissor"])))
            continue
        if g["type"] == "group":
            continue
        vis = fitz.Rect(g["rect"])
        for _l, sc in stack:
            vis &= sc
        if vis.is_empty and (g["rect"].width > 0 and g["rect"].height > 0):
            continue
        if g["rect"].width == 0 or g["rect"].height == 0:            # a horizontal or vertical line: test against the clip
            ok = all(sc.x0 - 0.5 <= g["rect"].x1 and g["rect"].x0 <= sc.x1 + 0.5 and sc.y0 - 0.5 <= g["rect"].y1 and g["rect"].y0 <= sc.y1 + 0.5
                     for _l, sc in stack)
            if not ok:
                continue
        out.append(g)
    return out


_VIS = {}


def paths(pg, clip, visible=True):
    clip = fitz.Rect(clip)
    out = []
    key = (id(pg), pg.parent.name)
    if visible and key not in _VIS:
        _VIS[key] = _visible_drawings(pg)
    for g in (_VIS[key] if visible else pg.get_drawings()):
        if not clip.intersects(g["rect"]):
            continue
        out.append(dict(type=g.get("type"), stroke=g.get("color"), fill=g.get("fill"), width=g.get("width") or 0,
                        fop=g.get("fill_opacity"), sop=g.get("stroke_opacity"), items=g["items"], rect=g["rect"],
                        pts=_pts(g["items"]), kinds="".join(it[0][0] for it in g["items"]), closed=g.get("closePath")))
    return out


def polyline(p):
    """the path's points in drawing order for a stroked line (curves reduced to their end points)."""
    pts = []
    for it in p["items"]:
        if it[0] == "l":
            pts += [(it[1].x, it[1].y), (it[2].x, it[2].y)]
        elif it[0] == "c":
            pts += [(it[1].x, it[1].y), (it[4].x, it[4].y)]
    a = np.array(pts, float)
    if len(a) > 1:
        a = a[np.r_[True, np.abs(np.diff(a, axis=0)).sum(1) > 1e-6]]
    return a


def markers(ps, maxsize=8.0, minsize=0.8):
    """small filled shapes: dots ('c' curves), diamonds (4 lines), squares ('re'), triangles (3 lines)."""
    out = []
    for p in ps:
        r = p["rect"]
        if p["fill"] is None or not (minsize <= r.width <= maxsize and minsize <= r.height <= maxsize):
            continue
        k = p["kinds"]
        shape = "o" if "c" in k else "s" if k in ("r", "q") else "D" if k.count("l") in (4, 5) and abs(r.width - r.height) < 0.6 * max(r.width, 1e-6) else "^" if k.count("l") == 3 else "?"
        out.append(dict(x=(r.x0 + r.x1) / 2, y=(r.y0 + r.y1) / 2, w=r.width, h=r.height, fill=p["fill"], stroke=p["stroke"], shape=shape,
                        fop=p["fop"]))
    return out


def glyph_words(pg, clip, maxh=9.0, gap=1.6, dark=0.45):
    """the report draws its type as filled glyph outlines; cluster small dark fills into words (rects, left to right)."""
    gl = [p["rect"] for p in paths(pg, clip) if p["type"] == "f" and p["fill"] is not None and max(p["fill"]) <= dark
          and p["rect"].height <= maxh and p["rect"].width <= maxh]
    gl.sort(key=lambda r: (round(r.y1), r.x0))
    words = []
    for r in sorted(gl, key=lambda r: r.x0):
        for w in words:
            if abs((w.y0 + w.y1) / 2 - (r.y0 + r.y1) / 2) < 2.5 and r.x0 - w.x1 < gap and r.x1 > w.x0 - gap:
                w |= r
                break
        else:
            words.append(fitz.Rect(r))
    return sorted(words, key=lambda w: (round(w.y0), w.x0))


class Axis:
    """page coordinate <-> data value, from two (pt, value) ticks; log10 when log."""

    def __init__(self, p0, v0, p1, v1, log=False):
        self.log = log
        f = (lambda v: math.log10(v)) if log else (lambda v: v)
        self.p0, self.p1, self.v0, self.v1 = p0, p1, f(v0), f(v1)

    def __call__(self, p):
        v = self.v0 + (np.asarray(p, float) - self.p0) * (self.v1 - self.v0) / (self.p1 - self.p0)
        return 10 ** v if self.log else v


class Render:
    """a high-resolution render of a source region, for what get_drawings does not report (some of the report's error
    bars, whiskers and gridlines sit in forms PyMuPDF does not walk): colours are read from pixels."""

    def __init__(self, pg, clip, z=8.0):
        self.clip, self.z = fitz.Rect(clip), z
        pix = pg.get_pixmap(clip=self.clip, matrix=fitz.Matrix(z, z), alpha=False)
        self.a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).astype(np.int16)

    def px(self, x, y):
        return int(round((x - self.clip.x0) * self.z)), int(round((y - self.clip.y0) * self.z))

    def pt(self, X, Y):
        return self.clip.x0 + X / self.z, self.clip.y0 + Y / self.z

    def match(self, rgb, tol=45):
        c = np.array([int(v * 255) for v in rgb], np.int16)
        return (np.abs(self.a - c).max(axis=2) <= tol)

    def whisker(self, cx, cy, rgb, tol=45, gap=3, half=0.6, vertical=False):
        """extent of a same-coloured bar through (cx, cy): scan out along the row (or column) until the colour stops."""
        m = self.match(rgb, tol)
        X, Y = self.px(cx, cy)
        hw = max(1, int(half * self.z))
        if vertical:
            band = m[:, max(X - hw, 0):X + hw + 1].any(axis=1)
            i0 = i1 = Y
        else:
            band = m[max(Y - hw, 0):Y + hw + 1, :].any(axis=0)
            i0 = i1 = X
        miss = 0
        while i0 > 0 and miss <= gap:
            i0 -= 1
            miss = 0 if band[i0] else miss + 1
        miss = 0
        while i1 < len(band) - 1 and miss <= gap:
            i1 += 1
            miss = 0 if band[i1] else miss + 1
        lo, hi = i0 + gap + 1, i1 - gap - 1
        if vertical:
            return self.pt(X, lo)[1], self.pt(X, hi)[1]
        return self.pt(lo, Y)[0], self.pt(hi, Y)[0]
