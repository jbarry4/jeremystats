"""PTEN poster v5: the theta and IED pictures, rebuilt in the KCNT1 poster's look (the user on v4: "rebuild these with the
new voltage raster / spectrogram look... can't see anything"; "rebuild with the new CSD raster trace look").

The values come from the sources themselves (digitize_theta.py): each colour map is read back through its own colour bar
into numbers, the traces are the sources' own vector paths, so the shapes are the published ones; only the look changes:
the poster's CSD colours (sinks blue, sources red, white at zero), Aptos, the lab's cell drawings beside the layers.

  T_rasters      theta CSD with its traces, WT / Pten KO IED- / Pten KO IED+ (Opening4 panel D)
  T_ied_example  one Pten KO IED: voltage by layer (VRaster) and the spectrograms of two contacts (Opening4 E, F)
  T_ied_cno      the IED+ mice's average IED at baseline and after CNO, voltage by layer (behavior menu p.25 a, b)"""
import os
import numpy as np
import fitz
import matplotlib
from PIL import Image
import style as S
import cells as Ce
import icons as I
from digitize_theta import OPEN, BM, PXPT, picture_canvas, polylines

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
PG = fitz.open(OPEN)[0]
JET = (matplotlib.colormaps["jet"](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.float32)
GROUP_COL = {"WT": S.PT_CTL, "IED-": S.PT_NEG_LINE, "IED+": S.PT_POS}


def unjet(rgb, vtop, vbot):
    """jet colours -> values; the jet colour bar runs from vbot (dark blue) to vtop (dark red)."""
    flat = rgb.reshape(-1, 3).astype(np.float32)
    idx = np.empty(len(flat), np.int32)
    for i in range(0, len(flat), 150000):
        idx[i:i + 150000] = ((flat[i:i + 150000, None, :] - JET[None]) ** 2).sum(-1).argmin(1)
    return (vbot + (vtop - vbot) * idx / 255.0).reshape(rgb.shape[:2])


def bar_range(t_top, v_top, t_bot, v_bot, y0, y1):
    """a colour bar drawn from y0 (top) to y1, ticks v_top at t_top and v_bot at t_bot -> values at its two ends."""
    k = (v_top - v_bot) / (t_bot - t_top)
    return v_top + (t_top - y0) * k, v_bot - (y1 - t_bot) * k


def words(clip):
    return [(w[4], (w[0] + w[2]) / 2, (w[1] + w[3]) / 2) for w in PG.get_text("words", clip=fitz.Rect(clip))]


def layer_cells(fig, x, y, w, h, ylim, sp, fis, gcl1, hil, gcl2):
    """the lab's drawings beside a depth axis: CA1 pyramidal cells (soma at sp, tufts to the fissure), both granule
    blades, the hilar SST cell (as on the KCNT1 laminar figure)."""
    ia = I.icon_axes(fig, x, y, w, h, ylim)
    wd = ia.get_xlim()[1]
    xi = 0.5 * wd
    v_, c_, bb_, soma_, end_ = Ce._src("pyr")
    Ce.group(ia, "pyr", xi, sp, fis - 0.5, xscale=min(1.0, 0.96 * wd / ((bb_[2] - bb_[0]) * (fis - sp) / abs(end_ - soma_))))
    k_ = Ce.blade_k(gcl1, fis + 1.0)
    up = Ce.blade(ia, "gc_up", xi, gcl1, -1, k_)
    dn = Ce.blade(ia, "gc_down", xi, gcl2, +1, k_)
    hs = wd * 0.8 / 13.4
    Ce.sst(ia, Ce.frame((xi - 0.03 * hs, hil), (0, -hs), (hs, 0)), spine_lw=0.35, z=6.5)
    return ia


def region_bars(fig, x, y_top, y_bot, ylim, ax_y, ax_h, fis):
    """CA1 / DG bars with their names, left of the layer names."""
    yt, yb = ylim[1], ylim[0]
    f = lambda v: ax_y + ax_h * (v - yt) / (yb - yt)          # noqa: E731
    for nm, a0, a1, col in (("CA1", y_top + 0.5, fis - 1.0, S.PYR), ("DG", fis + 1.0, y_bot - 0.5, S.GC)):
        bx = S.ax_at(fig, x + 0.2, f(a0), 0.06, f(a1) - f(a0)); bx.set_xlim(0, 1); bx.set_ylim(1, 0); bx.axis("off")
        bx.plot([0.5, 0.5], [0, 1], c=col, lw=2.0, solid_capstyle="butt")
        S.text_at(fig, x, (f(a0) + f(a1)) / 2, nm, rotation=90, ha="center", va="center", fontsize=S.LABEL, fontweight="bold", color=col)


def csd_colorbar(fig, x, y, h, lo_word="sink", hi_word="source", label=None, ticks=None, vmin=-1, vmax=1):
    cb = S.ax_at(fig, x, y, 0.13, h)
    cb.imshow(np.linspace(1, 0, 256)[:, None], aspect="auto", cmap=S.CSD_CMAP, extent=(0, 1, vmin, vmax))
    cb.set_xticks([])
    cb.yaxis.tick_right()
    if ticks is None:
        cb.set_yticks([])
        cb.text(1.5, vmax, hi_word, transform=cb.transData, ha="left", va="top", fontsize=S.NOTE, color=S.INK)
        cb.text(1.5, vmin, lo_word, transform=cb.transData, ha="left", va="bottom", fontsize=S.NOTE, color=S.INK)
    else:
        cb.set_yticks(ticks)
        cb.tick_params(labelsize=S.SMALL + 0.5)
    for s in cb.spines.values():
        s.set_visible(False)
    if label:
        cb.set_title(label, fontsize=S.NOTE, loc="left", pad=4)
    return cb


# ================================================================================================= T_rasters
def t_rasters():
    clip = fitz.Rect(70, 158, 595, 292)
    can, _ = picture_canvas(PG, clip)
    to_px = lambda x, y: (int(round((x - clip.x0) * PXPT)), int(round((y - clip.y0) * PXPT)))   # noqa: E731
    panels = [(78.40, 240.64), (247.84, 410.56), (418.72, 582.40)]
    YT, YB = 162.0, 285.4
    vtop, vbot = bar_range(163.8, 0.2, 287.35, -0.2, 160.88, 289.52)
    traces = polylines(PG, clip, color=(0, 0, 0))
    # chain each panel's 3.9 pt segments into whole traces (one per contact)
    segs = [p for p, _w, _c in traces]
    start = {}
    for i, s in enumerate(segs):
        start.setdefault((round(s[0, 0], 2), round(s[0, 1], 2)), []).append(i)
    ends = {i: (round(s[-1, 0], 2), round(s[-1, 1], 2)) for i, s in enumerate(segs)}
    endset = set(ends.values())
    used, chains = set(), []
    for h in [i for i, s in enumerate(segs) if (round(s[0, 0], 2), round(s[0, 1], 2)) not in endset]:
        ch, cur = [h], h
        used.add(h)
        while True:
            nx = [j for j in start.get(ends[cur], []) if j not in used]
            if not nx:
                break
            cur = nx[0]; used.add(cur); ch.append(cur)
        chains.append(np.vstack([segs[i] for i in ch]))
    W, H = 14.75, 3.75
    fig = S.figure(W, H)
    AX0, AY, AH = 2.05, 0.42, 3.05
    PW, GAP = 3.72, 0.14
    SEC = (106.48 - 79.26)                                   # the source's 1 s scale bar, pt
    layers = [("SP", 170.3), ("SLM", 205.5), ("OML1", 221.4), ("MML1", 231.0), ("GCL1", 239.6), ("HIL", 252.8),
              ("GCL2", 263.9), ("MML2", 273.9), ("OML2", 283.5)]
    FIS = 213.0
    for k, ((x0, x1), name, gk) in enumerate(zip(panels, ("Wild-type", "Pten KO, IED−", "Pten KO, IED+"), ("WT", "IED-", "IED+"))):
        a0, _ = to_px(x0, YT)
        a1, _ = to_px(x1, YB)
        _, b0 = to_px(x0, YT)
        _, b1 = to_px(x0, YB)
        vals = unjet(can[b0:b1, a0:a1], vtop, vbot)
        ax = S.ax_at(fig, AX0 + k * (PW + GAP), AY, PW, AH)
        ax.imshow(vals, cmap=S.CSD_CMAP, vmin=-0.16, vmax=0.16, aspect="auto", extent=(0, (x1 - x0) / SEC, YB, YT),
                  interpolation="bilinear")
        for c in chains:
            if x0 - 1 <= c[:, 0].min() <= x0 + 2:
                cc = c[::3]
                ax.plot((cc[:, 0] - x0) / SEC, cc[:, 1], c=S.INK, lw=0.38, alpha=0.9, solid_joinstyle="round")
        ax.set_xlim(0, (x1 - x0) / SEC); ax.set_ylim(YB, YT)
        S.bare(ax)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(name, fontsize=S.LABEL, fontweight="bold", color=GROUP_COL[gk], pad=5)
        if k == 2:
            ax.plot([(x1 - x0) / SEC - 1.0, (x1 - x0) / SEC], [YB + 3.5] * 2, c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
            ax.text((x1 - x0) / SEC - 0.5, YB + 5, "1 s", ha="center", va="top", fontsize=S.NOTE)
    # layer names, the cells, the regions
    for txt, y in layers:
        col = S.SST if txt == "HIL" else S.GC if txt.startswith("GCL") else S.SOFT
        S.text_at(fig, 1.24, AY + AH * (y - YT) / (YB - YT), txt, ha="right", va="center", fontsize=S.NOTE, color=col,
                  fontweight="bold" if txt in ("HIL", "GCL1", "GCL2") else "normal")
    layer_cells(fig, 1.28, AY, 0.7, AH, (YB, YT), 170.3, FIS, 239.6, 252.8, 263.9)
    region_bars(fig, 0.12, YT, YB, (YB, YT), AY, AH, FIS)
    csd_colorbar(fig, AX0 + 3 * PW + 2 * GAP + 0.12, AY + 0.25, AH - 0.5)
    S.save(fig, os.path.join(OUT, "T_rasters.png"))
    print("T_rasters: %d traces" % len(chains))


# ================================================================================================= T_ied_example
def t_ied_example():
    W, H = 8.2, 3.2
    fig = S.figure(W, H)
    # ---- E: voltage by layer around one IED (VRaster)
    clip = fitz.Rect(0, 295, 245, 445)
    can, got = picture_canvas(PG, clip)
    px = lambda v: int(round(v * PXPT))                      # noqa: E731
    hx0, hx1, hy0, hy1 = 82.8, 225.16, 304.09, 433.96         # the map (its colour bar sits to its right)
    vals_rgb = can[px(hy0 - clip.y0):px(hy1 - clip.y0), px(hx0 - clip.x0):px(hx1 - clip.x0)]
    ws = words((70, 425, 240, 445))
    xt = {float(t): x for t, x, y in ws if t.lstrip("-").isdigit()}
    tmin = -20 + (hx0 - xt[-20.0]) * 40 / (xt[20.0] - xt[-20.0])
    tmax = -20 + (hx1 - xt[-20.0]) * 40 / (xt[20.0] - xt[-20.0])
    vtop, vbot = bar_range(318.75, 1500, 419.55, -1500, 304.4, 434.2)
    vals = unjet(vals_rgb, vtop, vbot)
    lines = [317.35, 327.95, 341.2, 354.45, 388.9, 407.46, 420.71]
    names = [("OML1", 322.6), ("MML1", 334.6), ("GCL1", 347.8), ("HIL", 371.7), ("GCL2", 398.2), ("MML2", 414.1), ("OML2", 427.3)]
    AY, AH = 0.36, 2.25
    ax = S.ax_at(fig, 1.05, AY, 2.6, AH)
    ax.imshow(vals, cmap=S.CSD_CMAP, vmin=-1500, vmax=1500, aspect="auto", extent=(tmin, tmax, hy1, hy0), interpolation="bilinear")
    for y in lines:
        ax.axhline(y, c=S.INK, lw=0.6, alpha=0.55)
    ax.axvline(0, c=S.INK, lw=0.8, ls=(0, (3, 2)))
    ax.set_xlim(tmin, tmax); ax.set_ylim(hy1, hy0)
    ax.set_yticks([]); ax.spines["left"].set_visible(False)
    ax.set_xticks([-20, -10, 0, 10, 20]); ax.set_xlabel("Time from the IED peak (ms)", fontsize=S.NOTE)
    for txt, y in names:
        col = S.SST if txt == "HIL" else S.GC if txt.startswith("GCL") else S.SOFT
        S.text_at(fig, 1.0, AY + AH * (y - hy0) / (hy1 - hy0), txt, ha="right", va="center", fontsize=S.SMALL + 0.5, color=col,
                  fontweight="bold" if txt in ("HIL", "GCL1", "GCL2") else "normal")
    ax.set_title("Voltage by layer", fontsize=S.NOTE, fontweight="bold", loc="left", pad=4)
    csd_colorbar(fig, 3.72, AY + 0.2, AH - 0.4, label="µV", ticks=[-1500, 0, 1500], vmin=-1500, vmax=1500)
    # ---- F: spectrograms of two contacts, with their voltage traces (white)
    clip = fitz.Rect(245, 295, 420, 445)
    can, got = picture_canvas(PG, clip)
    hi = PG.get_pixmap(clip=clip, dpi=600, alpha=False)
    hia = np.frombuffer(hi.samples, np.uint8).reshape(hi.height, hi.width, 3)
    k600 = 600 / 72.0
    t_of = lambda x: (x - 334.72) * 25.0 / (391.50 - 374.94)            # noqa: E731  (0 tick, 25 ms bar)
    specs = [((270.7, 399.3, 306.5, 366.4), 307.45, 342.25, "Channel 32"),
             ((270.7, 399.3, 371.6, 431.0), 373.13, 407.69, "Channel 56")]
    for j, ((sx0, sx1, sy0, sy1), y1000, y100, lab) in enumerate(specs):
        sub = can[px(sy0 - clip.y0) + 2:px(sy1 - clip.y0) - 2, px(sx0 - clip.x0) + 2:px(sx1 - clip.x0) - 2]
        f_of = lambda y: 10 ** (3 - (y - y1000) / (y100 - y1000))      # noqa: E731
        ax = S.ax_at(fig, 4.95, 0.12 + j * 1.38, 2.7, 1.12)
        ax.imshow(sub, aspect="auto", extent=(t_of(sx0), t_of(sx1), np.log10(f_of(sy1)), np.log10(f_of(sy0))), interpolation="bilinear")
        # the white voltage trace: the white pixels of the 600 dpi render, column by column
        r0, r1 = int((sy0 - clip.y0) * k600) + 4, int((sy1 - clip.y0) * k600) - 4
        c0, c1 = int((sx0 - clip.x0) * k600) + 4, int((sx1 - clip.x0) * k600) - 4
        box = hia[r0:r1, c0:c1].astype(int)
        white = (box.min(axis=2) > 225)
        lx1 = int((296.2 - sx0) * k600)                                  # the source's white "Channel" label box
        white[: int(12.5 * k600), :max(lx1, 0)] = False
        xs, ys = [], []
        for c in range(0, white.shape[1], 2):
            rr = np.where(white[:, c])[0]
            if rr.size:
                xs.append(sx0 + (c0 - int((sx0 - clip.x0) * k600) + c) / k600)
                ys.append(sy0 + (r0 - int((sy0 - clip.y0) * k600) + np.median(rr)) / k600)
        xs, ys = np.array(xs), np.array(ys)
        ax.plot(t_of(xs), np.log10(f_of(ys)), c="white", lw=0.9)
        ax.set_xlim(t_of(sx0), t_of(sx1)); ax.set_ylim(np.log10(f_of(sy1)), np.log10(f_of(sy0)))
        ax.set_yticks([2, 3]); ax.set_yticklabels(["100", "1000"])
        ax.tick_params(labelsize=S.SMALL + 0.5)
        ax.text(1.02, 0.5, lab, transform=ax.transAxes, ha="left", va="center", fontsize=S.SMALL + 0.5, color=S.INK, rotation=90)
        if j == 1:
            ax.set_xticks([-50, 0, 50]); ax.set_xlabel("Time from the IED peak (ms)", fontsize=S.NOTE)
        else:
            ax.set_xticks([-50, 0, 50], [])
        for s in ax.spines.values():
            s.set_visible(False)
    S.text_at(fig, 4.38, 1.45, "Frequency (Hz)", rotation=90, ha="center", va="center", fontsize=S.NOTE)
    S.save(fig, os.path.join(OUT, "T_ied_example.png"))
    print("T_ied_example")


# ================================================================================================= T_ied_cno
def t_ied_cno():
    d = fitz.open(os.path.join(BM, "25_interictal_discharges.pdf"))
    imgs = []
    for x in (44, 48):
        pix = fitz.Pixmap(d, x)
        if pix.n - pix.alpha != 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        imgs.append(np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3])
    # read off the page's own render: the maps run from -8 to 15 ms; the colour bar's 1000 and -1000 ticks give its ends
    vtop, vbot = 1321.0, -1357.0
    F = [0, 0.103, 0.184, 0.287, 0.388, 0.655, 0.798, 0.901, 1.0]          # the layer lines, as fractions of the depth
    names = ["CA1 SLM", "OML1", "MML1", "GCL1", "HIL", "GCL2", "MML2", "OML2"]
    W, H = 7.3, 3.5
    fig = S.figure(W, H)
    AY, AH, PW = 0.52, 2.45, 2.62
    for k, (im, title) in enumerate(zip(imgs, ("Baseline", "After CNO"))):
        vals = unjet(im[::-1], vtop, vbot)                 # the picture is stored bottom row first
        ax = S.ax_at(fig, 1.05 + k * (PW + 0.18), AY, PW, AH)
        ax.imshow(vals, cmap=S.CSD_CMAP, vmin=-1200, vmax=1200, aspect="auto", extent=(-8, 15, 1, 0), interpolation="bilinear")
        for f in F[1:-1]:
            ax.axhline(f, c=S.INK, lw=0.6, alpha=0.55)
        ax.axvline(0, c=S.INK, lw=0.8, ls=(0, (3, 2)))
        ax.set_xlim(-8, 15); ax.set_ylim(1, 0)
        ax.set_yticks([]); ax.spines["left"].set_visible(False)
        ax.set_xticks([-5, 0, 5, 10, 15])
        ax.set_xlabel("Time from the IED peak (ms)", fontsize=S.NOTE)
        ax.set_title(title, fontsize=S.NOTE + 1, fontweight="bold", pad=24)
        # initiation (-1 to 0 ms) and propagation (2 to 15 ms) windows, as in the source
        for a, b, w in ((-1, 0, "IP"), (2, 15, "PP")):
            ax.plot([a, b], [-0.035, -0.035], c=S.INK, lw=3.0, solid_capstyle="butt", clip_on=False)
            ax.text((a + b) / 2 if w == "PP" else a - 0.4, -0.06, w, ha="center" if w == "PP" else "right", va="bottom",
                    fontsize=S.SMALL, clip_on=False)
    for txt, a, b in zip(names, F[:-1], F[1:]):
        col = S.SST if txt == "HIL" else S.GC if txt.startswith("GCL") else S.SOFT
        S.text_at(fig, 1.0, AY + AH * (a + b) / 2, txt, ha="right", va="center", fontsize=S.SMALL + 0.5, color=col,
                  fontweight="bold" if txt in ("HIL", "GCL1", "GCL2") else "normal")
    csd_colorbar(fig, 1.05 + 2 * PW + 0.18 + 0.15, AY + 0.25, AH - 0.5, label="µV", ticks=[-1000, 0, 1000], vmin=-1200, vmax=1200)
    S.save(fig, os.path.join(OUT, "T_ied_cno.png"))
    print("T_ied_cno")


if __name__ == "__main__":
    import sys
    want = sys.argv[1:] or ["rasters", "example", "cno"]
    if "rasters" in want:
        t_rasters()
    if "example" in want:
        t_ied_example()
    if "cno" in want:
        t_ied_cno()
