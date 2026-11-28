"""PTEN poster v5: the theta, IED and CNO figures, digitized from their sources so they can be redrawn in the poster's
own look (the user: "rebuild these with the new voltage raster / spectrogram look", "try your best to rerender things
even if you don't have the data... keep the general shape", "as long as the p values and specific stats are good").

  Opening4paperAndPoster.pdf (the lab's opening figure)
    panel D  theta CSD of a WT, an IED- and an IED+ Pten KO mouse: the CSD maps are tiled pictures (jet, -0.2..0.2 a.u.),
             the traces are vector paths -> CSD values on a (channel x time) grid, traces as polylines
    panel E  one Pten KO IED, CSD around its peak (jet picture) -> values; layer lines
    panel F  spectrograms of two contacts (jet pictures, kept as colour) and their white voltage traces
  PTEN behavioral menu (vector pages from the report)
    p.20 b   theta CSD per layer by IED status: baseline, after CNO, change (mean +- SE)
    p.22 a   MML2 + GCL2 ROC (baseline, after CNO) and each mouse's baseline -> CNO
    p.23 b   firing against current, aCSF and CNO (bands and lines)
    p.25 a,b the average IED of the IED+ mice at baseline and after CNO (voltage pictures, jet)
Everything is saved to data/theta_*.npz / .json; fig_theta.py draws from those only."""
import json
import os
import numpy as np
import fitz
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OPEN = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\Opening4paperAndPoster.pdf"
BM = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\PTEN POSTER\Menus, etc\PTEN_Behavioral_Menu\pages"
PXPT = 25 / 6.0                                  # the pictures' own resolution: 4.1667 px per pt (300 px per inch)


def picture_canvas(page, clip):
    """paste every embedded picture inside clip onto one canvas at its own resolution (vector paths left out)."""
    W, H = int(round(clip.width * PXPT)), int(round(clip.height * PXPT))
    can = np.full((H, W, 3), 255, np.uint8)
    got = np.zeros((H, W), bool)
    for im in page.get_images(full=True):
        for r in page.get_image_rects(im[0]):
            if not clip.contains(r):
                continue
            pix = fitz.Pixmap(page.parent, im[0])
            if pix.n - pix.alpha != 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
            x0, y0 = int(round((r.x0 - clip.x0) * PXPT)), int(round((r.y0 - clip.y0) * PXPT))
            x1, y1 = int(round((r.x1 - clip.x0) * PXPT)), int(round((r.y1 - clip.y0) * PXPT))
            if x1 <= x0 or y1 <= y0:
                continue
            a = np.asarray(Image.fromarray(a).resize((x1 - x0, y1 - y0), Image.NEAREST))
            can[y0:y1, x0:x1] = a
            got[y0:y1, x0:x1] = True
    return can, got


def jet_values(rgb, lo, hi):
    """invert MATLAB's jet: nearest of 256 jet colours -> value in [lo, hi]."""
    import matplotlib
    J = (matplotlib.colormaps["jet"](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.float32)
    flat = rgb.reshape(-1, 3).astype(np.float32)
    idx = np.empty(len(flat), np.int32)
    for i in range(0, len(flat), 200000):
        d = ((flat[i:i + 200000, None, :] - J[None]) ** 2).sum(-1)
        idx[i:i + 200000] = d.argmin(1)
    return (lo + (hi - lo) * idx / 255.0).reshape(rgb.shape[:2])


def polylines(page, clip, color=None, width_max=None):
    """every stroked path in clip (optionally of one colour) as an array of points (pt)."""
    out = []
    for g in page.get_drawings():
        if g.get("type") not in ("s", "fs") or not clip.intersects(g["rect"]):
            continue
        c = g.get("color")
        if color is not None and (c is None or max(abs(a - b) for a, b in zip(c, color)) > 0.06):
            continue
        pts = []
        for it in g["items"]:
            if it[0] == "l":
                pts += [(it[1].x, it[1].y), (it[2].x, it[2].y)]
            elif it[0] == "c":
                pts += [(it[1].x, it[1].y), (it[4].x, it[4].y)]
        if len(pts) >= 2:
            p = np.array(pts)
            keep = np.r_[True, (np.abs(np.diff(p, axis=0)).sum(1) > 1e-6)]
            out.append((p[keep], g.get("width", 1), c))
    return out


if __name__ == "__main__":
    import sys
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    doc = fitz.open(OPEN)
    pg = doc[0]
    # ---------------------------------------------------------------- panel D: three theta CSD maps with traces
    clip = fitz.Rect(70, 158, 595, 292)
    can, got = picture_canvas(pg, clip)
    Image.fromarray(can).save(os.path.join(HERE, "data", "theta_D_canvas.png"))
    print("canvas", can.shape)
