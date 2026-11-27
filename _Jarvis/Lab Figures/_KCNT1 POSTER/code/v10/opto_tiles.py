"""Re-read Fig. 7's spectrograms from the PDF's own image tiles (no tick marks or other vector overlays drawn into them), then
read the colors back to dB through each panel's colorbar, as opto_extract.py does. Overwrites the |spec arrays in opto_fig7.npz."""
import os, numpy as np, fitz
from PIL import Image
from scipy.spatial import cKDTree
SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\FinalKcnt1_Dylan 1.pdf"
NPZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "opto_fig7.npz")
doc = fitz.open(SRC); page = doc[0]
P = 3456 / 2212.0
IMGS = [(fitz.Rect(i["bbox"]), i) for i in page.get_image_info(xrefs=True)]
D = dict(np.load(NPZ, allow_pickle=True))
PANELS = {"Baseline": (1100, 487, 1460, 690), "5 Hz A": (1470, 487, 1830, 690), "5 Hz B": (1830, 487, 2212, 690),
          "7 Hz": (1470, 715, 1830, 920), "12 Hz A": (1470, 948, 1830, 1152), "12 Hz B": (1830, 948, 2212, 1152)}

def rgb(xref):
    pix = fitz.Pixmap(doc, xref)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.colorspace is None or pix.colorspace.n != 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

for name, box in PANELS.items():
    R = fitz.Rect(box[0] * P, box[1] * P, box[2] * P, box[3] * P)
    ext = D[name + "|spec_extent"]
    allt = sorted([(r, i) for r, i in IMGS if r.intersects(R) and r.height > 5], key=lambda t: t[0].x0)
    # split into the spectrogram block and the colorbar by the gap between them along x
    groups, cur = [], [allt[0]]
    for t_ in allt[1:]:
        if t_[0].x0 > max(q[0].x1 for q in cur) + 8:
            groups.append(cur); cur = [t_]
        else:
            cur.append(t_)
    groups.append(cur)
    tiles = max(groups, key=len)
    cbt = [t_ for g in groups if g is not tiles for t_ in g if t_[0].x0 > tiles[-1][0].x0]
    # keep the big block: tiles whose x lies inside the block of wide tiles
    xs0 = min(r.x0 for r, i in tiles); ys0 = min(r.y0 for r, i in tiles)
    xs1 = max(r.x1 for r, i in tiles); ys1 = max(r.y1 for r, i in tiles)
    t0 = tiles[0]
    sx = t0[1]["width"] / t0[0].width; sy = t0[1]["height"] / t0[0].height
    W, H = int(round((xs1 - xs0) * sx)), int(round((ys1 - ys0) * sy))
    canvas = Image.new("RGB", (W, H), "white")
    for r, i in tiles:
        im = rgb(i["xref"])
        x, y = int(round((r.x0 - xs0) * sx)), int(round((r.y0 - ys0) * sy))
        w, h = max(1, int(round(r.width * sx))), max(1, int(round(r.height * sy)))
        canvas.paste(im.resize((w, h), Image.NEAREST), (x, y))
    A = np.asarray(canvas, np.float32)
    # the colorbar: tiles right of the spectrogram, narrow
    cbt.sort(key=lambda t: t[0].y0)
    col = np.concatenate([np.median(np.asarray(rgb(i["xref"]), np.float32)[:, :, :], axis=1) for r, i in cbt], axis=0)   # top -> bottom
    cb_top, cb_bot = cbt[0][0].y0, cbt[-1][0].y1
    lo, hi = D[name + "|cb_range"]          # values at the colorbar's bottom and top, from opto_extract.py
    v = hi + (lo - hi) * (np.arange(len(col)) + 0.5) / len(col)
    tree = cKDTree(col[2:-2])
    dist, idx = tree.query(A.reshape(-1, 3))
    dB = v[2:-2][idx].reshape(A.shape[:2]).astype(np.float32)
    print("%-8s %d tiles -> %s px, block %.1f-%.1f x %.1f-%.1f pt (was extent %s); colorbar %d tiles, %d colors; fit %.2f; dB %.0f-%.0f" % (
        name, len(tiles), A.shape[:2], xs0, xs1, ys0, ys1, np.round(ext, 2), len(cbt), len(col), np.median(dist), *np.percentile(dB, [1, 99])))
    D[name + "|spec"] = dB
np.savez_compressed(NPZ, **D)
print("updated", NPZ)
