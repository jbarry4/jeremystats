"""dev helper: what a source region is made of (spines, ticks, markers, lines), compactly. Not used by the figures."""
import sys, collections, fitz
import numpy as np
import vec as V
pdf, x0, y0, x1, y1 = sys.argv[1], *map(float, sys.argv[2:6])
mode = sys.argv[6] if len(sys.argv) > 6 else "all"
pg = V.page(pdf); C = fitz.Rect(x0, y0, x1, y1)
ps = [p for p in V.paths(pg, C) if C.contains(p["rect"]) or p["rect"].width > 15 or p["rect"].height > 15]
col = lambda c: "-" if c is None else "%.2f,%.2f,%.2f" % tuple(c)
if mode in ("all", "axes"):
    H = sorted({(round(p["rect"].y0, 1), round(p["rect"].x0, 1), round(p["rect"].x1, 1), col(p["stroke"] or p["fill"])) for p in ps if p["rect"].height < 0.9 and p["rect"].width > 15})
    Vv = sorted({(round(p["rect"].x0, 1), round(p["rect"].y0, 1), round(p["rect"].y1, 1), col(p["stroke"] or p["fill"])) for p in ps if p["rect"].width < 0.9 and p["rect"].height > 15})
    print("HLINES", H); print("VLINES", Vv)
    T = [p["rect"] for p in ps if max(p["rect"].width, p["rect"].height) <= 3.5 and min(p["rect"].width, p["rect"].height) <= 0.6 and max(p["rect"].width, p["rect"].height) >= 1.0]
    print("TICKS-v(x)", sorted(round((r.x0 + r.x1) / 2, 1) for r in T if r.height > r.width))
    print("  at y", sorted({round(r.y0, 0) for r in T if r.height > r.width}))
    print("TICKS-h(y)", sorted(round((r.y0 + r.y1) / 2, 1) for r in T if r.width > r.height))
    print("  at x", sorted({round(r.x0, 0) for r in T if r.width > r.height}))
if mode in ("all", "marks"):
    M = V.markers(ps)
    g = collections.defaultdict(list)
    for m in M:
        g[(col(m["fill"]), m["shape"], round(m["w"], 1))].append((round(m["x"], 1), round(m["y"], 1)))
    for k, v in sorted(g.items(), key=lambda t: -len(t[1])):
        print("MARK", k, len(v), "x %.1f-%.1f y %.1f-%.1f" % (min(a for a, b in v), max(a for a, b in v), min(b for a, b in v), max(b for a, b in v)))
    L = collections.Counter()
    for p in ps:
        if p["type"] in ("s", "fs") and p["stroke"] is not None and max(p["rect"].width, p["rect"].height) > 3.5:
            L[(col(p["stroke"]), round(p["width"], 2))] += 1
    for k, v in L.most_common(15):
        print("LINE", k, v)
    F = collections.Counter()
    for p in ps:
        if p["type"] == "f" and p["fill"] is not None and max(p["rect"].width, p["rect"].height) > 9:
            F[(col(p["fill"]), round(p["fop"] or 1, 2))] += 1
    for k, v in F.most_common(10):
        print("FILL", k, v)
