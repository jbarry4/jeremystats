"""Fig. 7 of Dylan Marchand's 2024 poster (Poster Resources/FinalKcnt1_Dylan 1.pdf), taken back to numbers from the PDF's own
vector paths and images, so the poster can redraw it: per panel the raw LFP (its drawn path, as a min/max envelope in uV), the
spectrogram (the PDF's image, colors read back to dB through the panel's own colorbar), and the SST unit's spikes (the x of each
orange tick). Axes are calibrated on the panel's own tick labels."""
import os, re, json
import numpy as np
import fitz
from scipy.spatial import cKDTree
from PIL import Image

SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\FinalKcnt1_Dylan 1.pdf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "opto_fig7.npz")
P = 3456 / 2212.0
page = fitz.open(SRC)[0]
DRAW = page.get_drawings()
TEXT = [(s["text"].strip(), fitz.Rect(s["bbox"]), s["size"]) for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
IMGS = [(fitz.Rect(i["bbox"]), i) for i in page.get_image_info(xrefs=True)]
BLUE, ORANGE = (0.0, 0.528, 0.789), (0.888, 0.411, 0.119)
PANELS = {"Baseline": (1100, 487, 1460, 690), "5 Hz A": (1470, 487, 1830, 690), "5 Hz B": (1830, 487, 2212, 690),
          "7 Hz": (1470, 715, 1830, 920), "10 Hz": (1830, 715, 2212, 920), "12 Hz A": (1470, 948, 1830, 1152),
          "12 Hz B": (1830, 948, 2212, 1152)}
num = re.compile(r"^-?\d+(\.\d+)?$")
close = lambda c, ref: c is not None and max(abs(a - b) for a, b in zip(c, ref)) < 0.01


def fit(pairs):
    a, b = np.polyfit([p for p, _ in pairs], [v for _, v in pairs], 1)
    return lambda x: a * np.asarray(x) + b, a, b


out = {}
for name, box in PANELS.items():
    R = fitz.Rect(box[0] * P, box[1] * P, box[2] * P, box[3] * P)
    dr = [d for d in DRAW if fitz.Rect(d["rect"]).intersects(R)]
    lfp = max((d for d in dr if close(d.get("fill"), BLUE)), key=lambda d: len(d["items"]))
    L = fitz.Rect(lfp["rect"])
    spk = [d for d in dr if close(d.get("fill"), ORANGE)]
    raster = [fitz.Rect(d["rect"]) for d in dr if close(d.get("fill"), (0, 0, 0)) and fitz.Rect(d["rect"]).width > 100]
    rb = raster[0]
    for r_ in raster[1:]:
        rb |= r_
    nums = [(t, r) for t, r, s in TEXT if num.match(t) and r.intersects(R)]
    # time: the tick labels under the raster
    bottom = [(t, r) for t, r in nums if r.y0 > rb.y1 - 2 and r.y0 < rb.y1 + 20]
    ft, at, bt = fit([((r.x0 + r.x1) / 2, float(t)) for t, r in bottom])
    # LFP voltage: labels left of the LFP box, between its top and the spectrogram
    left = [(t, r) for t, r in nums if r.x1 < L.x0 + 2 and r.x1 > L.x0 - 40]
    volt = [(t, r) for t, r in left if r.y0 > L.y0 - 30 and r.y1 < L.y1 + 40 and abs(float(t)) >= 0 and (abs(float(t)) % 500 == 0) and r.y1 < rb.y0 - 90]
    # spectrogram images (not the colorbar): inside the LFP's x span
    sim = [r for r, i in IMGS if r.intersects(R) and r.x0 >= L.x0 - 2 and r.x1 <= L.x1 + 2 and r.y0 > L.y1 - 5 and r.y1 < rb.y0 + 5]
    S = sim[0]
    for r_ in sim[1:]:
        S |= r_
    cbi = [r for r, i in IMGS if r.intersects(R) and r.x0 >= L.x1 - 1 and r.x1 > L.x1 + 2 and r.y0 > L.y1 - 5 and r.y1 < rb.y0 + 5 and r.width < 12]
    CB = cbi[0]
    for r_ in cbi[1:]:
        CB |= r_
    # voltage labels: the ones whose rows sit beside the LFP box (above the spectrogram's top)
    volt = [(t, r) for t, r in left if (r.y0 + r.y1) / 2 < S.y0 - 3]
    fv, av, bv = fit([((r.y0 + r.y1) / 2, float(t)) for t, r in volt])
    freq = [(t, r) for t, r in left if (r.y0 + r.y1) / 2 >= S.y0 - 3 and (r.y0 + r.y1) / 2 < S.y1 + 6]
    ff, af, bf = fit([((r.y0 + r.y1) / 2, float(t)) for t, r in freq])
    cbl = [(t, r) for t, r in nums if r.x0 > CB.x1 and r.x0 < CB.x1 + 12 and (r.y0 + r.y1) / 2 > CB.y0 - 6 and (r.y0 + r.y1) / 2 < CB.y1 + 6]
    fc, ac, bc = fit([((r.y0 + r.y1) / 2, float(t)) for t, r in cbl])
    # the LFP path as points, then a min/max envelope in 4000 bins
    pts = []
    for it in lfp["items"]:
        if it[0] == "l":
            pts.append((it[1].x, it[1].y)); pts.append((it[2].x, it[2].y))
    pts = np.array(pts)
    tx, uv = ft(pts[:, 0]), fv(pts[:, 1])
    t0, t1 = ft(L.x0), ft(L.x1)
    nb = 4000
    edges = np.linspace(t0, t1, nb + 1)
    k = np.clip(np.digitize(tx, edges) - 1, 0, nb - 1)
    lo = np.full(nb, np.nan); hi = np.full(nb, np.nan)
    np.minimum.at(lo, k, uv) if False else None
    lo = np.array([np.nan] * nb); hi = np.array([np.nan] * nb)
    order = np.argsort(k)
    ks, us = k[order], uv[order]
    br = np.flatnonzero(np.diff(ks)) + 1
    for seg_k, seg_u in zip(np.split(ks, br), np.split(us, br)):
        lo[seg_k[0]] = seg_u.min(); hi[seg_k[0]] = seg_u.max()
    # line half-width: the path is the outline of a stroked line, so trim half the stroke from each side
    # spikes
    spikes = np.sort([ft((fitz.Rect(d["rect"]).x0 + fitz.Rect(d["rect"]).x1) / 2) for d in spk])
    # spectrogram pixels -> dB through the colorbar
    z = 600 / 72.0
    pim = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=S, alpha=False)
    A = np.frombuffer(pim.samples, np.uint8).reshape(pim.height, pim.width, 3).astype(np.float32)
    pcb = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=CB, alpha=False)
    CBA = np.frombuffer(pcb.samples, np.uint8).reshape(pcb.height, pcb.width, 3).astype(np.float32)
    col = np.median(CBA[:, CBA.shape[1] // 3: 2 * CBA.shape[1] // 3], axis=1)     # top -> bottom
    ycb = CB.y0 + (np.arange(len(col)) + 0.5) / len(col) * CB.height
    vcb = fc(ycb)
    keep = slice(2, len(col) - 2)
    tree = cKDTree(col[keep])
    dist, idx = tree.query(A.reshape(-1, 3))
    dB = vcb[keep][idx].reshape(A.shape[:2])
    spec_extent = [float(ft(S.x0)), float(ft(S.x1)), float(ff(S.y1)), float(ff(S.y0))]
    out[name] = dict(t0=float(t0), t1=float(t1), env_t=(edges[:-1] + edges[1:]) / 2, env_lo=lo, env_hi=hi, spikes=np.array(spikes),
                     spec=dB.astype(np.float32), spec_extent=spec_extent, cb_range=[float(fc(CB.y1)), float(fc(CB.y0))],
                     fit_err=float(np.median(dist)))
    print("%-8s t %.2f-%.2f s | LFP %d pts, %.0f..%.0f uV | spec %s %.2f-%.2f s %.1f-%.1f Hz, dB %.0f-%.0f (cb %.0f-%.0f), color fit %.1f | %d spikes (%.1f/s)" % (
        name, t0, t1, len(pts), np.nanmin(lo), np.nanmax(hi), dB.shape, *spec_extent, np.percentile(dB, 1), np.percentile(dB, 99),
        *out[name]["cb_range"], np.median(dist), len(spikes), len(spikes) / (t1 - t0)))
    print("   scale: %.3f s/pt, %.2f uV/pt (labels %s), %.3f Hz/pt" % (at, av, [t for t, _ in volt], af))
np.savez_compressed(OUT, **{f"{n}|{k}": v for n, d in out.items() for k, v in d.items()})
print("wrote", OUT)
