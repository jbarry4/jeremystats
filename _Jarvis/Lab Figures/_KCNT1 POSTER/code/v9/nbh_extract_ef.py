"""NBH'25 Fig. 4 E/F back to numbers (see nbh_extract.py for A-D): the two-dentate-spike discharge (Ei LFP, Eii CSD at
38.38-38.42 s with the LFP over it, mean-CSD profiles at the red and blue arrows) and a KCNT1 dentate spike (Fi, Fii at
69.985-70.025 s, profile). CSD images are the PDF's tiles read back to values through each image's own colorbar (calibrated on
the printed colorbar labels). Time: Eii/Fii from their heat-map boxes and tick labels; Ei/Fi from the printed 200 ms bar
(62.94 pt), anchored at the arrow times. Voltage: Ei's printed 2 mV bar (86.46 pt); Fi has none and is taken on the same scale.
Depth: the PDF's own y (pt), with its layer labels."""
import os, re, json
import numpy as np
import fitz
from PIL import Image
from scipy.spatial import cKDTree

SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\FinalNBH'25 1.pdf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nbh_fig4ef.npz")
doc = fitz.open(SRC)
page = doc[0]
DR = page.get_drawings()
TX = [(s["text"].strip(), fitz.Rect(s["bbox"])) for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
IM = [(fitz.Rect(i["bbox"]), i) for i in page.get_image_info(xrefs=True)]
num = re.compile(r"^-?\d*\.?\d+$")
cx = lambda r: (r.x0 + r.x1) / 2
cy = lambda r: (r.y0 + r.y1) / 2
MS_PT = 62.94 / 200.0          # pt per ms (the printed 200 ms bars)
MV_PT = 86.46 / 2.0            # pt per mV (Ei's printed 2 mV bar)
out = {}


def rgb(xref):
    p = fitz.Pixmap(doc, xref)
    if p.alpha:
        p = fitz.Pixmap(p, 0)
    if p.colorspace is None or p.colorspace.n != 3:
        p = fitz.Pixmap(fitz.csRGB, p)
    return Image.frombytes("RGB", (p.width, p.height), p.samples)


def labels(rect):
    return [(float(t), r) for t, r in TX if num.match(t) and rect.contains(fitz.Point(cx(r), cy(r)))]


def lin(pairs):
    a, b = np.polyfit([p for p, _ in pairs], [v for _, v in pairs], 1)
    return lambda x: a * np.asarray(x, float) + b


def mosaic(R):
    tiles = [(r, i) for r, i in IM if r.intersects(R)]
    big = max(tiles, key=lambda t: t[0].width)
    s = big[1]["width"] / big[0].width                         # px per pt
    x0 = min(r.x0 for r, i in tiles); y0 = min(r.y0 for r, i in tiles)
    x1 = max(r.x1 for r, i in tiles); y1 = max(r.y1 for r, i in tiles)
    can = Image.new("RGB", (int(round((x1 - x0) * s)), int(round((y1 - y0) * s))), "white")
    for r, i in tiles:
        im = rgb(i["xref"]).resize((max(1, int(round(r.width * s))), max(1, int(round(r.height * s)))), Image.NEAREST)
        can.paste(im, (int(round((r.x0 - x0) * s)), int(round((r.y0 - y0) * s))))
    return np.asarray(can).astype(int), x0, y0, s


def boxes(A):
    sat = (A.max(2) - A.min(2)) > 50
    colfrac = sat.mean(0)
    cols = np.flatnonzero(colfrac > 0.5)
    runs = np.split(cols, np.flatnonzero(np.diff(cols) > 3) + 1)
    runs = sorted(runs, key=len, reverse=True)[:2]
    heat, cb = sorted(runs, key=lambda r: r[0])
    rows_h = np.flatnonzero(sat[:, heat[5]:heat[-5]].mean(1) > 0.5)
    rows_c = np.flatnonzero(sat[:, cb[len(cb) // 2]])
    return (heat[0], heat[-1] + 1, rows_h[0], rows_h[-1] + 1), (cb[0], cb[-1] + 1, rows_c[0], rows_c[-1] + 1)


def outline_center(d, axis_vals, along="x", nb=None):
    """centerline of a filled stroke outline: for each position along `along`, the middle of the outline's extent across it"""
    pts = np.array([(p.x, p.y) for it in d["items"] if it[0] == "l" for p in (it[1], it[2])])
    a, b = (0, 1) if along == "x" else (1, 0)
    segs = [((it[1].x, it[1].y), (it[2].x, it[2].y)) for it in d["items"] if it[0] == "l"]
    res = []
    for v in axis_vals:
        hits = []
        for p, q in segs:
            lo, hi = min(p[a], q[a]), max(p[a], q[a])
            if lo <= v <= hi and hi > lo:
                f = (v - p[a]) / (q[a] - p[a])
                hits.append(p[b] + f * (q[b] - p[b]))
        res.append((min(hits) + max(hits)) / 2 if hits else np.nan)
    return np.array(res)


def envelope(d, x_edges):
    pts = np.array([(p.x, p.y) for it in d["items"] if it[0] == "l" for p in (it[1], it[2])])
    k = np.clip(np.digitize(pts[:, 0], x_edges) - 1, 0, len(x_edges) - 2)
    lo = np.full(len(x_edges) - 1, np.nan); hi = lo.copy()
    o = np.argsort(k)
    ks, ys = k[o], pts[o, 1]
    br = np.flatnonzero(np.diff(ks)) + 1
    for kk, yy in zip(np.split(ks, br), np.split(ys, br)):
        lo[kk[0]] = yy.min(); hi[kk[0]] = yy.max()
    return lo, hi                     # in pt (y down)


for key, R, tlab_box, cb_box, t_heat0 in (("E", fitz.Rect(440, 1885, 760, 2106), fitz.Rect(465, 2078, 700, 2095), fitz.Rect(705, 1905, 730, 2082), None),
                                          ("F", fitz.Rect(830, 1885, 1150, 2110), fitz.Rect(880, 2078, 1065, 2095), fitz.Rect(1100, 1905, 1125, 2082), None)):
    A, x0, y0, s = mosaic(R)
    (hx0, hx1, hy0, hy1), (cx0, cx1, cy0, cy1) = boxes(A)
    col = A[cy0:cy1, cx0 + (cx1 - cx0) // 3: cx1 - (cx1 - cx0) // 3].mean(1)
    fcb = lin([(cy(r), v) for v, r in labels(cb_box)])
    vals = fcb(y0 + (np.arange(cy0, cy1) + 0.5) / s)
    tree = cKDTree(col[3:-3])
    dist, idx = tree.query(A[hy0:hy1, hx0:hx1].reshape(-1, 3))
    C = vals[3:-3][idx].reshape(hy1 - hy0, hx1 - hx0)
    ft = lin([(cx(r), v) for v, r in labels(tlab_box)])
    heat_pt = (x0 + hx0 / s, x0 + hx1 / s, y0 + hy0 / s, y0 + hy1 / s)
    out[key + "_csd"] = C.astype(np.float32)
    out[key + "_heat_pt"] = np.array(heat_pt)
    out[key + "_t"] = np.array([float(ft(heat_pt[0])), float(ft(heat_pt[1]))])
    print("%sii: CSD %s, %.4f-%.4f s, box x %.1f-%.1f y %.1f-%.1f pt, values %.3f..%.3f (fit %.1f), colorbar labels %s" % (
        key, C.shape, *out[key + "_t"], *heat_pt, C.min(), C.max(), np.median(dist), [v for v, _ in labels(cb_box)]))
    # the LFP drawn over the heat map
    seg = [d for d in DR if d["type"] == "s" and d.get("color") == (0.0, 0.0, 0.0) and 100 <= len(d["items"]) <= 130
           and fitz.Rect(d["rect"]).intersects(fitz.Rect(*heat_pt[:1], heat_pt[2], heat_pt[1], heat_pt[3]))]
    P = np.array([(p.x, p.y) for d in seg for it in d["items"] if it[0] == "l" for p in (it[1],)])
    P = P[np.argsort(P[:, 0])]
    out[key + "_ov_t"] = ft(P[:, 0]).astype(np.float32)
    out[key + "_ov_y"] = P[:, 1].astype(np.float32)
    print("   overlay: %d segments, %d pts, y %.1f-%.1f" % (len(seg), len(P), P[:, 1].min(), P[:, 1].max()))
    # profiles
    prof_box = fitz.Rect(heat_pt[1] + 40, heat_pt[2] - 5, heat_pt[1] + 200, heat_pt[3] + 5)
    fx = lin([(cx(r), v) for v, r in labels(fitz.Rect(prof_box.x0 - 12, 2080, prof_box.x1 - 10, 2094)) if abs(v) <= 0.3])
    ys = np.linspace(heat_pt[2] + 0.5, heat_pt[3] - 0.5, 160)
    out[key + "_prof_y"] = ys
    for d in DR:
        if d["type"] == "f" and 140 <= len(d["items"]) <= 170 and fitz.Rect(d["rect"]).intersects(prof_box):
            c = d["fill"]
            nm = "red" if c[0] > 0.9 else ("blue" if c[2] > 0.9 else "black")
            out[key + "_prof_" + nm] = fx(outline_center(d, ys, along="y")).astype(np.float32)
            print("   profile %s: %.3f..%.3f" % (nm, np.nanmin(out[key + "_prof_" + nm]), np.nanmax(out[key + "_prof_" + nm])))
    # arrow times (triangles under the heat map)
    arr = {}
    for d in DR:
        r = fitz.Rect(d["rect"])
        if d["type"] == "f" and len(d["items"]) == 3 and r.y0 > heat_pt[3] and r.y1 < heat_pt[3] + 30 and heat_pt[0] < cx(r) < heat_pt[1]:
            c = d["fill"]
            nm = "red" if c[0] > 0.9 else ("blue" if c[2] > 0.9 else "black")
            arr[nm] = float(ft(cx(r)))
    out[key + "_arrows"] = json.dumps(arr)
    print("   arrows:", {k: round(v, 4) for k, v in arr.items()})
    # layer labels (E only)
    lay = {t: float(cy(r)) for t, r in TX if t in ("OML", "MML", "GCL", "Hilus") and r.x0 < heat_pt[0] and r.x1 > heat_pt[0] - 40
           and heat_pt[2] < cy(r) < heat_pt[3]}
    out[key + "_layers"] = json.dumps(lay)

# Ei and Fi: the traces
for key, R in (("E", fitz.Rect(470, 1740, 850, 1902)), ("F", fitz.Rect(865, 1750, 1245, 1850))):
    d = max([d for d in DR if d["type"] == "f" and len(d["items"]) > 50000 and fitz.Rect(d["rect"]).intersects(R)], key=lambda d: len(d["items"]))
    r = fitz.Rect(d["rect"])
    edges = np.linspace(r.x0, r.x1, 2401)
    lo, hi = envelope(d, edges)
    xc = (edges[:-1] + edges[1:]) / 2
    base = np.nanmedian((lo + hi) / 2)
    pk = xc[np.nanargmin(lo)]                       # the highest point of the trace (y down)
    arr = json.loads(out[key + "_arrows"])
    t_pk = arr["blue"] if key == "E" else arr["black"]
    t = t_pk + (xc - pk) / MS_PT / 1000.0
    out[key + "i_t"] = t.astype(np.float32)
    out[key + "i_hi_mv"] = (-(lo - base) / MV_PT).astype(np.float32)        # upper edge of the drawn line
    out[key + "i_lo_mv"] = (-(hi - base) / MV_PT).astype(np.float32)
    print("%si: %.3f-%.3f s (peak anchored at %.4f s), %.2f..%.2f mV" % (key, t[0], t[-1], t_pk, np.nanmin(out[key + "i_lo_mv"]), np.nanmax(out[key + "i_hi_mv"])))
np.savez_compressed(OUT, **out)
print("wrote", OUT)
