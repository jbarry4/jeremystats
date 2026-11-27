"""Hom f-I curves, read off Shore et al. 2020 (Cell Rep 33:108303; author manuscript nihms-1642113.pdf, Figure 4 B4 and C4):
AP frequency (mean +- SEM) per current step for WT and Kcnt1 Y777H homozygous (m/m) cultured cortical neurons, fast-spiking
(FS, PV-like) and non-fast-spiking (NFS, SST-like) GABAergic.

How: the figure is one 300 dpi JPEG (pdfwork/cellrep2020_fig4.png, the PDF's own image). Axes from the axis lines and tick
marks (B4: 0-1500 pA, 0-75 Hz; C4: 0-600 pA, 0-30 Hz). The steps, as the markers sit: B4 at 0 pA then 40 to 1480 pA every 60 pA (26), C4 every 20 pA from 0 to 600 (31).
Markers: at each step, the WT marker (grey fill) and the Hom marker (blue / green fill) are the best match of a 5-px disk to
that colour within +-6 px of the step's column (the black fit line and the whiskers cross the markers, a disk still fits
best at the centre). SEM: the error bar's cap (a short dark horizontal bar centred on the step) nearest the marker on the
side away from the other group (WT above, Hom below: WT sits above Hom at every step past rheobase). Output:
data/cellrep_fI.json (Hz, at each step)."""
import os, json
import numpy as np
from PIL import Image
from scipy.ndimage import convolve

HERE = os.path.dirname(os.path.abspath(__file__))
A = np.asarray(Image.open(os.path.join(HERE, "pdfwork", "cellrep2020_fig4.png")).convert("RGB")).astype(int)
MX, MN = A.max(2), A.min(2)
SAT = MX - MN
DARK = MX < 90
GREY = ((SAT < 22) & (MX > 95) & (MX < 185)).astype(float)
r = 5
yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
DISK = ((xx ** 2 + yy ** 2) <= r * r).astype(float)
DISK /= DISK.sum()
PANELS = {  # name: (x of 0 pA, px per pA, y of 0 Hz, px per Hz, step pA, n, Hom colour, top of the data area by current)
    "FS": (519.5, (879 - 519.5) / 1500, 1737.0, (1737 - 1497) / 75, 50, 31,
           ((A[..., 2] > A[..., 0] + 60) & (MX > 90)).astype(float), lambda p: 1565 if p <= 700 else 1470),
    "NFS": (973.5, (1333 - 973.5) / 600, 1737.5, (1737.5 - 1497.5) / 30, 20, 31,
            ((A[..., 1] > A[..., 0] + 50) & (A[..., 1] >= A[..., 2] - 10) & (MX > 90)).astype(float), lambda p: 1565 if p <= 260 else 1470),
}
SCORE = {"grey": convolve(GREY, DISK, mode="constant")}

out = {"source": "Shore AN, Colombo S, Tobin WF, et al. (2020) Cell Rep 33:108303, Figure 4 B4 (FS GABAergic) and C4 (NFS GABAergic); "
                 "WT vs Kcnt1 Y777H homozygous cultured cortical neurons; digitized from the author manuscript's figure (nihms-1642113.pdf), "
                 "about +-0.5 Hz (FS) and +-0.2 Hz (NFS)",
       "stats": {"FS": "I50 p = 0.017, f-I slope p = 0.34", "NFS": "I50 p = 0.0002, f-I slope p = 0.004"}}
for name, (x0, kx, y0, ky, step, nst, homm, ytop) in PANELS.items():
    hs = convolve(homm, DISK, mode="constant")
    pa = np.r_[0, 40 + 60 * np.arange(25)] if name == "FS" else np.arange(nst) * step
    res = {"WT": [], "Hom": []}
    for p in pa:
        xc = int(round(x0 + p * kx))
        ya = ytop(p)
        for g, sc in (("WT", SCORE["grey"]), ("Hom", hs)):
            hw = 4 if name == "FS" else 6                      # FS steps are 14 px apart: stay on the step
            win = sc[ya:1742, xc - hw:xc + hw + 1]
            j, i = np.unravel_index(np.argmax(win), win.shape)
            if win[j, i] < 0.35:
                res[g].append([np.nan, np.nan, np.nan]); continue
            # refine: centroid of the colour inside the disk at the best match
            yb, xb = ya + j, xc - hw + i
            m = (GREY if g == "WT" else homm)[yb - 6:yb + 7, xb - 6:xb + 7] * (np.hypot(*np.mgrid[-6:7, -6:7]) <= 6.5)
            cy = yb - 6 + (m.sum(1) * np.arange(13)).sum() / max(m.sum(), 1e-9)
            res[g].append([cy, xb, win[j, i]])
    out[name] = {"pa": pa.tolist()}
    for g in ("WT", "Hom"):
        hz, sem = [], []
        for (cy, xb, s), p in zip(res[g], pa):
            if not np.isfinite(cy):
                hz.append(None); sem.append(None); continue
            xc = int(round(x0 + p * kx))
            cap = (DARK[:, xc - 3:xc + 4].sum(1) >= 7) & ~DARK[:, xc - 9] & ~DARK[:, xc + 9]   # a cap: dark across the step only
            ys = np.flatnonzero(cap)
            if g == "WT":
                c = ys[(ys < cy - 7) & (ys > cy - 60)]
                e = (cy - c.max()) if c.size else np.nan
            else:
                c = ys[(ys > cy + 7) & (ys < min(cy + 60, y0 - 3))]
                e = (c.min() - cy) if c.size else np.nan
            hz.append(round((y0 - cy) / ky, 2))
            sem.append(round(e / ky, 2) if np.isfinite(e) else None)
        out[name][g + "_hz"], out[name][g + "_sem"] = hz, sem
    print(name)
    for g in ("WT", "Hom"):
        print("  ", g, "Hz ", [None if v is None else round(v, 1) for v in out[name][g + "_hz"]])
        print("  ", g, "SEM", [None if v is None else round(v, 1) for v in out[name][g + "_sem"]])
json.dump(out, open(os.path.join(HERE, "data", "cellrep_fI.json"), "w"), indent=1)
