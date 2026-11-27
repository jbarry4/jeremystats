"""Fig. 4 of the NBH'25 poster (Poster Resources/FinalNBH'25 1.pdf), taken back to numbers so the poster can redraw it.

A  the IED's CSD: the PDF's own image (MATLAB jet, 38.25-38.55 s, CSC 2-64 axis), colors read back to values through the
   image's own colorbar (calibrated on the colorbar labels the PDF prints), and the three 30 kHz LFP traces drawn over it
   (vector paths; 2 mV = the printed scale bar, 19.44 pt). Depth labels at the y of the probe-track labels beside it.
B  the probe track: the PDF's grayscale histology image.
C  the pre-spike LFP spectra (vector paths; axes 0-200 Hz across the axes box, y from the printed tick labels).
D  the 300-6000 Hz traces (vector paths; +-200 uV and time from the printed tick labels).
E/F the two-dentate-spike discharge (38.38-38.42 s) and a KCNT1 dentate spike (69.99-70.02 s): LFP traces, CSD images
   (tiles, read back to values through their colorbar), the LFP drawn over the CSD, the mean-CSD depth profiles and the
   arrow times.
Everything is in data/nbh_fig4.npz; the numbers are only as good as the PDF's drawing (sub-point)."""
import os, re, json
import numpy as np
import fitz
from scipy.spatial import cKDTree

SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\FinalNBH'25 1.pdf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nbh_fig4.npz")
doc = fitz.open(SRC)
page = doc[0]
DR = page.get_drawings()
TX = [(s["text"].strip(), fitz.Rect(s["bbox"])) for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
IM = [(fitz.Rect(i["bbox"]), i) for i in page.get_image_info(xrefs=True)]
num = re.compile(r"^-?\d*\.?\d+$")
cx = lambda r: (r.x0 + r.x1) / 2
cy = lambda r: (r.y0 + r.y1) / 2
out = {}


def rgb(xref):
    p = fitz.Pixmap(doc, xref)
    if p.alpha:
        p = fitz.Pixmap(p, 0)
    if p.colorspace is None or p.colorspace.n != 3:
        p = fitz.Pixmap(fitz.csRGB, p)
    return np.frombuffer(p.samples, np.uint8).reshape(p.height, p.width, 3).copy()


def labels(rect):
    return [(float(t), r) for t, r in TX if num.match(t) and rect.contains(fitz.Point(cx(r), cy(r)))]


def lin(pairs):
    a, b = np.polyfit([p for p, _ in pairs], [v for _, v in pairs], 1)
    return lambda x: a * np.asarray(x, float) + b


def polyline(d):
    its = [it for it in d["items"] if it[0] == "l"]
    return np.array([(it[1].x, it[1].y) for it in its] + [(its[-1][2].x, its[-1][2].y)])


def decode(img, lut_rgb, lut_val):
    tree = cKDTree(lut_rgb.astype(float))
    dist, idx = tree.query(img.reshape(-1, 3).astype(float))
    return lut_val[idx].reshape(img.shape[:2]), float(np.median(dist))


def find(color, rect, kind="s", min_items=50):
    res = []
    for d in DR:
        c = d.get("color") if kind == "s" else d.get("fill")
        if d["type"].startswith(kind[0]) and c and max(abs(a - b) for a, b in zip(c, color)) < 0.02 and fitz.Rect(d["rect"]).intersects(rect) \
                and len(d["items"]) >= min_items:
            res.append(d)
    return res


# ------------------------------------------------------------------ A: the IED's CSD
A = np.vstack([rgb(72), rgb(64)])
y0_pt, y1_pt = 1721.0, 2085.0
spp = A.shape[0] / (y1_pt - y0_pt)                 # image px per pt
X0_PT = 9.0
px_x = lambda x_pt: (x_pt - X0_PT) * spp
pt_y = lambda py: y0_pt + py / spp
heat = A[282:2831, 287:1961]
cb_col = A[250:2909, 2105:2122].astype(float).mean(1)
cbl = [(v, r) for v, r in labels(fitz.Rect(268, 1740, 290, 2080))]
fcb = lin([(cy(r), v) for v, r in cbl])           # pt y -> value
cb_val = fcb(pt_y(np.arange(250, 2909) + 0.5))
Cval, fit = decode(heat, cb_col[3:-3], cb_val[3:-3])
ftime = lin([(cx(r), v) for v, r in labels(fitz.Rect(30, 2075, 260, 2090))])
frame_top, frame_bot = 246.0, 2912.5                 # CSC2 and CSC64 (the image's own axis)
ch = lambda py: 2 + (py - frame_top) / (frame_bot - frame_top) * 62
out["A_csd"] = Cval.astype(np.float32)
out["A_extent"] = np.array([float(ftime(X0_PT + 287 / spp)), float(ftime(X0_PT + 1961 / spp)), ch(2831), ch(282)])  # t0, t1, ch bottom, ch top
print("A: CSD %s, %.3f-%.3f s, CSC %.2f-%.2f, values %.3f..%.3f (colour fit %.1f)" % (Cval.shape, *out["A_extent"][:2], out["A_extent"][3],
                                                                                    out["A_extent"][2], Cval.min(), Cval.max(), fit))
MV = 19.44                                            # pt per 2 mV (the printed bar)
tr = sorted([d for d in DR if d["type"] == "s" and len(d["items"]) > 5000 and fitz.Rect(d["rect"]).intersects(fitz.Rect(40, 1740, 250, 2020))],
            key=lambda d: d["rect"][1])
for k, d in enumerate(tr):
    P = polyline(d)
    base = np.median(P[:, 1])
    out["A_tr%d_t" % k] = ftime(P[:, 0]).astype(np.float32)
    out["A_tr%d_mv" % k] = (-(P[:, 1] - base) / MV * 2).astype(np.float32)
    out["A_tr%d_ch" % k] = np.array(ch((base - y0_pt) * spp))
    print("   trace %d: %d pts, at CSC %.1f, %.2f..%.2f mV" % (k, len(P), out["A_tr%d_ch" % k], out["A_tr%d_mv" % k].min(), out["A_tr%d_mv" % k].max()))
LAY = {}
for t, r in TX:
    if t in ("Ctx", "Pyr", "SLM", "OML", "DGC", "Hil") and 290 < r.x0 < 350 and 1740 < r.y0 < 2000:
        LAY[t] = float(ch((cy(r) - y0_pt) * spp))
out["A_layers"] = json.dumps(LAY)
out["A_spike_t"] = np.array(float(ftime(141.45)))
out["A_prespike_tip"] = np.array([float(ftime(112.0)), float(ch((2007.6 - y0_pt) * spp))])
print("   layers (CSC):", {k: round(v, 1) for k, v in LAY.items()}, "spike at %.4f s" % out["A_spike_t"])

# ------------------------------------------------------------------ B: the probe track
B = np.vstack([rgb(80), rgb(76)])[:, :, 0]
out["B_img"] = B
out["B_extent_pt"] = np.array([289.1, 410.0, 1748.0, 2085.0])
print("B: histology %s" % (B.shape,))

# ------------------------------------------------------------------ C: spectra
for name, color, box, ybox in (("pyr", (0, 0, 1), fitz.Rect(47, 2130, 142, 2245), fitz.Rect(20, 2120, 46, 2250)),
                               ("hil", (1, 0, 0), fitz.Rect(47, 2265, 142, 2370), fitz.Rect(20, 2245, 46, 2376))):
    d = [d for d in find(color, box, "s", 100) if d.get("width") and d["width"] > 0.5][0]
    P = polyline(d)
    fy = lin([(cy(r), v) for v, r in labels(ybox)])
    f = (P[:, 0] - 47.5) / (141.0 - 47.5) * 200
    out["C_%s_f" % name] = f.astype(np.float32)
    out["C_%s_y" % name] = fy(P[:, 1]).astype(np.float32)
    print("C %s: %d pts, %.0f-%.0f Hz, max %.0f" % (name, len(P), f.min(), f.max(), out["C_%s_y" % name].max()))

# ------------------------------------------------------------------ D: 300-6000 Hz traces
fdt = lin([(cx(r), v) for v, r in labels(fitz.Rect(195, 2370, 425, 2383))])
traces = sorted([d for d in DR if d["type"] == "s" and len(d["items"]) > 5000 and fitz.Rect(d["rect"]).intersects(fitz.Rect(186, 2130, 425, 2370))],
                key=lambda d: d["rect"][1])
uv_per_pt = 200 / 9.15
names = []
for k, d in enumerate(traces):
    P = polyline(d)
    base = np.median(P[:, 1])
    c = d["color"]
    nm = "Ctx" if c == (0.0, 0.0, 0.0) else ("CA1" if c[2] > 0.5 else "Hilus")
    names.append(nm)
    out["D_tr%d_t" % k] = fdt(P[:, 0]).astype(np.float32)
    out["D_tr%d_uv" % k] = (-(P[:, 1] - base) * uv_per_pt).astype(np.float32)
    print("D trace %d (%s): %d pts, %.3f-%.3f s, %.0f..%.0f uV" % (k, nm, len(P), out["D_tr%d_t" % k][0], out["D_tr%d_t" % k][-1],
                                                                     out["D_tr%d_uv" % k].min(), out["D_tr%d_uv" % k].max()))
out["D_names"] = json.dumps(names)
np.savez_compressed(OUT, **out)
print("wrote", OUT)
