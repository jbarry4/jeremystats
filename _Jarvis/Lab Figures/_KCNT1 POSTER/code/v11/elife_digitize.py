"""Shore et al. 2024 (eLife 92915), Fig. 4C2/C3 f-I curves read off the article's page raster (page 9, image xref 212) by colour:
WT black, YH-HET blue (SST) or orange (PV). Axes calibrated on the figure's own tick marks. For each genotype the mean is the
middle of the coloured line in each pixel column (the fitted curve the figure draws through its points), and the +-SEM band is
the extent of the coloured error bars at each plotted point. Approximate by construction (a few % of full scale)."""
import os, json, numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
A = np.asarray(Image.open(os.path.join(HERE, "pdfwork", "elife_4C.png")).convert("RGB")).astype(int)
R_, G_, B_ = A[:, :, 0], A[:, :, 1], A[:, :, 2]
black = (A.max(2) < 110)
blue = (B_ > R_ + 45) & (B_ > G_ + 30) & (B_ > 120)
orange = (R_ > 170) & (G_ > 90) & (G_ < 200) & (B_ < 120) & (R_ - B_ > 90)
PANELS = {"SST": dict(x0=140, xpa=(682 - 140) / 900, y0=993, yhz=(993 - 633) / 60, cols=(141, 684), rows=(600, 991), het=blue,
                      box=(330, 470, 625, 675), steps=np.arange(0, 901, 20)),
          "PV": dict(x0=858, xpa=(1399 - 858) / 1200, y0=992, yhz=(992 - 631) / 80, cols=(860, 1401), rows=(600, 990), het=orange,
                     box=(1060, 1190, 625, 675), steps=np.arange(0, 1201, 25))}
out = {}
for name, p in PANELS.items():
    res = {}
    for g, mask in (("WT", black), ("Het", p["het"])):
        M = mask.copy()
        bx0, bx1, by0, by1 = p["box"]
        M[by0:by1, bx0:bx1] = False
        c0, c1 = p["cols"]; c0 += 2; r0, r1 = p["rows"]
        xs, mid = [], []
        for c in range(c0, c1):
            rr = np.flatnonzero(M[r0:r1, c]) + r0
            if len(rr) >= 2:
                xs.append(c); mid.append(np.median(rr))
        xs = np.array(xs); mid = np.array(mid)
        # SEM at each plotted point: the coloured extent in a 3-px column band at the point's x
        sem_lo, sem_hi, px = [], [], []
        for I in p["steps"]:
            c = int(round(p["x0"] + I * p["xpa"]))
            band = M[r0:r1, max(c0, c - 1):min(c1, c + 2)].any(1)
            rr = np.flatnonzero(band) + r0
            if len(rr):
                px.append(I); sem_lo.append(rr.max()); sem_hi.append(rr.min())
        to_pa = lambda c: (np.asarray(c) - p["x0"]) / p["xpa"]
        to_hz = lambda r: (p["y0"] - np.asarray(r, float)) / p["yhz"]
        res[g] = dict(curve_pa=to_pa(xs).tolist(), curve_hz=to_hz(mid).tolist(), pts_pa=[float(v) for v in px],
                      lo_hz=to_hz(sem_lo).tolist(), hi_hz=to_hz(sem_hi).tolist())
        print(name, g, "curve %d cols, %.0f-%.0f pA, max %.1f Hz; %d points" % (len(xs), to_pa(xs).min(), to_pa(xs).max(), to_hz(mid).max(), len(px)))
    out[name] = res
json.dump(out, open(os.path.join(HERE, "data", "elife_fI.json"), "w"))
# overlay for checking
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 10.5)); ax.imshow(A.astype(np.uint8))
for name, p in PANELS.items():
    for g, colr in (("WT", "magenta"), ("Het", "lime")):
        d = out[name][g]
        ax.plot(p["x0"] + np.array(d["curve_pa"]) * p["xpa"], p["y0"] - np.array(d["curve_hz"]) * p["yhz"], c=colr, lw=0.8)
        for I, lo, hi in zip(d["pts_pa"], d["lo_hz"], d["hi_hz"]):
            x = p["x0"] + I * p["xpa"]
            ax.plot([x, x], [p["y0"] - lo * p["yhz"], p["y0"] - hi * p["yhz"]], c=colr, lw=0.6)
ax.set_xlim(100, 1450); ax.set_ylim(1010, 600)
fig.savefig(os.path.join(HERE, "pdfwork", "elife_check.png"), dpi=110)
