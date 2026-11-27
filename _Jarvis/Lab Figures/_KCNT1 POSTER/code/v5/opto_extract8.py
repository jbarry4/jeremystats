"""Fig. 8 of Dylan Marchand's 2024 poster (FinalKcnt1_Dylan 1.pdf) back to numbers: per light condition the SST unit's spike
autocorrelogram (bar heights, read off the PDF's own bar rectangles and y tick labels) with its fitted curve, the spectrum of
that autocorrelogram (its drawn curve; peak frequency and amplitude as printed), and the mean firing rate per run (panel C's
polyline at each run's category)."""
import os, re, json
import numpy as np
import fitz

SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\KCNT1 POSTER\Poster Resources\FinalKcnt1_Dylan 1.pdf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "opto_fig8.json")
P = 3456 / 2212.0
page = fitz.open(SRC)[0]
REG = fitz.Rect(1205 * P, 722 * P, 1483 * P, 1224 * P)
DR = [d for d in page.get_drawings() if fitz.Rect(d["rect"]).intersects(REG)]
TX = [(s["text"].strip(), fitz.Rect(s["bbox"]), s["size"]) for b in page.get_text("dict", clip=REG)["blocks"] for l in b.get("lines", []) for s in l["spans"]]
num = re.compile(r"^-?\d+(\.\d+)?$")
close = lambda c, ref: c is not None and max(abs(a - b) for a, b in zip(c, ref)) < 0.01
cy = lambda r: (r.y0 + r.y1) / 2
cx = lambda r: (r.x0 + r.x1) / 2


def fit(pairs):
    a, b = np.polyfit([p for p, _ in pairs], [v for _, v in pairs], 1)
    return lambda x: a * np.asarray(x, float) + b


def points(d):
    pts = []
    for it in d["items"]:
        if it[0] == "l":
            pts += [(it[1].x, it[1].y), (it[2].x, it[2].y)]
        elif it[0] == "c":
            pts += [(it[1].x, it[1].y), (it[4].x, it[4].y)]
        elif it[0] == "re":
            r = it[1]; pts += [(r.x0, r.y0), (r.x1, r.y1)]
    return np.array(pts)


def centerline(pts, xs, half=0.6):
    out = []
    for x in xs:
        m = np.abs(pts[:, 0] - x) < half
        out.append((pts[m, 1].min() + pts[m, 1].max()) / 2 if m.any() else np.nan)
    return np.array(out)


axes = sorted([fitz.Rect(d["rect"]) for d in DR if close(d.get("fill"), (1, 1, 1)) and fitz.Rect(d["rect"]).width > 40], key=lambda r: (r.y0, r.x0))
ac_axes = [r for r in axes if abs(r.x0 - 1961.6) < 3]
sp_axes = [r for r in axes if r.x0 > 2200 and r.y1 < 1745]
print("axes:", len(axes), "autocorr", len(ac_axes), "spectrum", len(sp_axes))
for r in axes:
    print("  ", [round(v, 1) for v in r])
ROWS = ["Baseline", "5 Hz (run 1)", "5 Hz (run 2)", "7 Hz", "10 Hz (run 1)", "10 Hz (run 2)", "12 Hz"]
xlab = [(float(t), cx(r)) for t, r, s in TX if num.match(t) and abs(r.y0 - 1731.1) < 1 and r.x0 < 2190]
fx = fit([(x, v) for v, x in xlab])
sxl = [(float(t), cx(r)) for t, r, s in TX if num.match(t) and abs(r.y0 - 1731.7) < 1 and r.x0 > 2200]
fsx = fit([(x, v) for v, x in sxl])
peaks = [(t, r) for t, r, s in TX if t.startswith("Peak frequency")]
amps = [(t, r) for t, r, s in TX if t.startswith("Peak Amp")]
res = dict(rows=[])
for k, (ax, sx) in enumerate(zip(ac_axes, sp_axes)):
    yl = [(float(t), cy(r)) for t, r, s in TX if num.match(t) and r.x1 < ax.x0 and r.x1 > ax.x0 - 20 and ax.y0 - 4 < cy(r) < ax.y1 + 4]
    fy = fit([(y, v) for v, y in yl])
    bars = [d for d in DR if close(d.get("fill"), (0.263, 0.325, 1.0)) and fitz.Rect(d["rect"]).intersects(ax)][0]
    B = []
    its = [it for it in bars["items"] if it[0] == "l"]
    for i in range(0, len(its) - 3, 4):
        xs = [p.x for it in its[i:i + 4] for p in (it[1], it[2])]
        ys = [p.y for it in its[i:i + 4] for p in (it[1], it[2])]
        B.append((float(fx((min(xs) + max(xs)) / 2)), float(fx(max(xs)) - fx(min(xs))), float(fy(min(ys)))))
    B.sort()
    red = [d for d in DR if close(d.get("fill"), (1.0, 0.149, 0.0)) and fitz.Rect(d["rect"]).intersects(ax)][0]
    rp = points(red)
    gx = np.linspace(ax.x0 + 0.5, ax.x1 - 0.5, 300)
    fit_y = fy(centerline(rp, gx))
    # spectrum: the black path with the most items inside its axes
    blk = max((d for d in DR if close(d.get("fill"), (0, 0, 0)) and fitz.Rect(d["rect"]).intersects(sx) and len(d["items"]) > 20), key=lambda d: len(d["items"]))
    sp = points(blk)
    syl = [(float(t), cy(r)) for t, r, s in TX if num.match(t) and r.x1 < sx.x0 + 1 and r.x1 > sx.x0 - 20 and sx.y0 - 4 < cy(r) < sx.y1 + 4]
    fsy = fit([(y, v) for v, y in syl])
    gsx = np.linspace(sp[:, 0].min() + 0.3, sp[:, 0].max() - 0.3, 200)
    spec_y = fsy(centerline(sp, gsx, 0.35))
    pk = min(peaks, key=lambda p: abs(cy(p[1]) - sx.y0))[0]
    am = min(amps, key=lambda p: abs(cy(p[1]) - sx.y0))[0]
    row = dict(name=ROWS[k], bins=[b[0] for b in B], width=float(np.median([b[1] for b in B])), counts=[max(0.0, b[2]) for b in B],
               fit_lag=[float(v) for v in fx(gx)], fit=[float(v) for v in fit_y],
               spec_f=[float(v) for v in fsx(gsx)], spec=[float(v) for v in spec_y],
               peak_hz=float(re.findall(r"[\d.]+", pk)[0]), peak_amp=float(re.findall(r"[\d.]+", am)[0]))
    res["rows"].append(row)
    print("%-14s %3d bars of %.4f s, max %.0f | fit max %.0f | spectrum %.1f-%.1f Hz | %s | %s" % (
        row["name"], len(B), row["width"], max(row["counts"]), np.nanmax(fit_y), row["spec_f"][0], row["spec_f"][-1], pk, am))
# panel C: mean firing rate per run
cax = [r for r in axes if r.y0 > 1745 and r.x0 > 2120]
print("C axes", cax)
C = cax[0]
cyl = [(float(t), cy(r)) for t, r, s in TX if num.match(t) and r.x1 < C.x0 + 9 and r.x0 > C.x0 - 15 and C.y0 - 4 < cy(r) < C.y1 + 4]
fcy = fit([(y, v) for v, y in cyl])
cats = sorted([cx(r) for t, r, s in TX if num.match(t) and abs(r.y0 - 1871.1) < 0.5 and r.x0 > C.x0])
blkC = max((d for d in DR if close(d.get("color") or d.get("fill"), (0, 0, 0)) and fitz.Rect(d["rect"]).intersects(C) and fitz.Rect(d["rect"]).width > 50), key=lambda d: len(d["items"]))
segs = []
for it in blkC["items"]:
    if it[0] == "l":
        segs.append((it[1].x, it[1].y, it[2].x, it[2].y))
def cross(x):
    ys = [y1 + (y2 - y1) * (x - x1) / (x2 - x1) for x1, y1, x2, y2 in segs if min(x1, x2) <= x <= max(x1, x2) and x2 != x1]
    return (min(ys) + max(ys)) / 2 if ys else np.nan
rate = fcy([cross(c) for c in cats])
res["rate_hz"] = [float(v) for v in rate]
res["rate_runs"] = ROWS
print("C labels", [v for v, _ in cyl], "categories", [round(c, 1) for c in cats], "rate", np.round(rate, 2), "path type", blkC["type"], len(blkC["items"]))
json.dump(res, open(OUT, "w"), indent=1)
print("wrote", OUT)
