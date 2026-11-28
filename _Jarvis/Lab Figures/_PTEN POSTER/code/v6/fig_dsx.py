"""PTEN poster v5: the dentate-spike panels that v4 cropped from the menus, read back out of the menus' vector pages and
redrawn in the poster's look (Aptos, the poster's sizes, the group and event colours of fig_ds.py). Every bracket, star and
number is the source's. Axis calibrations are the sources' own tick positions (read with gridview.py; noted inline).

  X_output    Jeremy menu (tight layers) p.2 c: fast power at the DS against its sink, binned within mice (log x)
  X_in_time   follow-up p.3 b: 240-420 Hz power over each mouse's own baseline, -100..100 ms around the DS peak
  X_spectra   Jeremy menu p.5 a: the added fast power by frequency, each layer
  X_vs_wt     Jeremy menu p.8b b: control DS against the IED+ mice's DS, BTs and IED-class events
  X_borders   Jeremy menu p.8b a: every event, with the DS border and the IED border
  X_examples  DS story menu p.2 c: a DS, a BT and an IED of one IED+ mouse (m28), LFP and 240-420 Hz"""
import os
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
import style as S
import vec as V

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
MEN = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\PTEN POSTER\Menus, etc"
JM = os.path.join(MEN, "Jeremy_Menu_TightLayers_112726", "pages")
FU = os.path.join(MEN, "Jeremy_Menu_Followup_112526", "pages")
DSM = os.path.join(MEN, "DS_Story_Menu_112326", "pages")
# the menus' colours -> the poster's
MAP = [((0.42, 0.42, 0.42), S.PT_CTL), ((0.55, 0.55, 0.55), S.PT_CTL), ((0.69, 0.69, 0.69), S.PT_CTL), ((0.55, 0.55, 0.55), S.PT_CTL),
       ((0.91, 0.64, 0.79), S.PT_NEG_LINE), ((0.66, 0.20, 0.43), S.PT_POS),
       ((0.18, 0.43, 0.71), S.PT_DS), ((0.56, 0.27, 0.68), S.PT_BT), ((0.84, 0.15, 0.16), S.PT_IED)]


def newc(c, tol=0.07):
    if c is None:
        return None
    for k, v in MAP:
        if V.near(c, k, tol):
            return v
    return None


def strokes(ps, minlen=3):
    for p in ps:
        if p["type"] in ("s", "fs") and newc(p["stroke"]) and max(p["rect"].width, p["rect"].height) >= minlen:
            yield p, V.polyline(p), newc(p["stroke"])


def bands(ps):
    for p in ps:
        if p["type"] == "f" and newc(p["fill"]) and (p["fop"] or 1) < 0.99 and max(p["rect"].width, p["rect"].height) > 4                 and len(p["pts"]) > 6:                          # a band, not a shaded window (a plain rectangle)
            yield p, p["pts"], newc(p["fill"]), p["fop"]


def group_key(fig, x, y, items, fs=S.SMALL + 0.5):
    hs = [Line2D([], [], color=c, lw=2.2, label=l) for l, c in items]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(x, y), fontsize=fs, handlelength=1.3, borderaxespad=0, labelspacing=0.3)


# ================================================================================================= X_output
def x_output():
    pg = V.page(os.path.join(JM, "02_q1_synaptic_efficacy.pdf"))
    ps = V.paths(pg, (60, 520, 226, 625))
    xa, ya = V.Axis(140.0, 1, 172.5, 2, log=True), V.Axis(586.25, 10, 528.25, 20)
    W, H = 3.9, 2.7
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.62, 0.15, 3.15, 1.95)
    for p, q, c, a in bands(ps):
        ax.add_patch(Polygon(np.column_stack([xa(q[:, 0]), ya(q[:, 1])]), closed=True, fc=c, ec="none", alpha=0.18, zorder=1))
    for p, q, c in strokes(ps, minlen=8):
        if p["rect"].y0 > 520 and p["rect"].x0 > 62 and p["rect"].width > 20:
            ax.plot(xa(q[:, 0]), ya(q[:, 1]), c=c, lw=2.0, zorder=2)
    for m in V.markers(ps, maxsize=3.5):
        c = newc(m["fill"])
        if c and not (m["x"] < 78 and m["y"] < 546):          # not the source's legend keys
            ax.scatter([xa(m["x"])], [ya(m["y"])], s=20, color=c, edgecolor="white", lw=0.5, zorder=3)
    ax.axvline(1, c=S.FAINT, lw=0.9, ls=(0, (3, 2)), zorder=0)
    ax.set_xscale("log", base=2)
    ax.set_xlim(0.2, 4.2); ax.set_xticks([0.25, 0.5, 1, 2, 4]); ax.set_xticklabels(["\u00bc", "\u00bd", "1", "2", "4"])
    ax.set_ylim(6, 21); ax.set_yticks([7.5, 10, 12.5, 15, 17.5, 20])
    ax.tick_params(labelsize=S.SMALL + 1)
    ax.set_xlabel("DS sink (control average = 1)", fontsize=S.NOTE)
    ax.set_ylabel("Fast power (dB)", fontsize=S.NOTE)
    group_key(fig, 0.2, 0.93, [("Control", S.PT_CTL), ("PTEN IED\u2212", S.PT_NEG_LINE), ("PTEN IED+", S.PT_POS)])
    S.save(fig, os.path.join(OUT, "X_output.png"))
    print("X_output")


# ================================================================================================= X_in_time
def x_in_time():
    pg = V.page(os.path.join(FU, "03_when_fast_power_is_measured.pdf"))
    ps = V.paths(pg, (66, 420, 300, 575))
    xa, ya = V.Axis(68.5, -100, 296.75, 100), V.Axis(543.0, 0, 446.5, 30)
    W, H = 3.9, 2.7
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.62, 0.15, 3.15, 1.95)
    ax.axvspan(-100, -50, color="#EEF0F3", lw=0, zorder=0)
    ax.axvspan(-25, 25, color="#FBEAF1", lw=0, zorder=0)
    ax.text(-75, 34.5, "baseline", ha="center", va="top", fontsize=9.5, color=S.SOFT)
    ax.text(0, 34.5, "measured", ha="center", va="top", fontsize=9.5, color=S.PT_POS)
    ax.axhline(0, c=S.FAINT, lw=0.8, zorder=0)
    for p, q, c, a in bands(ps):
        ax.add_patch(Polygon(np.column_stack([xa(q[:, 0]), ya(q[:, 1])]), closed=True, fc=c, ec="none", alpha=0.18, zorder=1))
    order = {S.PT_CTL: 2, S.PT_NEG_LINE: 2, S.PT_DS: 3, S.PT_BT: 4, S.PT_IED: 5}
    for p, q, c in strokes(ps, minlen=40):
        if p["rect"].x0 < 75:                                  # the curves start at -100 ms (legend keys do not)
            ax.plot(xa(q[:, 0]), ya(q[:, 1]), c=c, lw=1.6, zorder=order.get(c, 3))
    ax.axvline(0, c=S.INK, lw=0.8, ls=(0, (3, 2)), zorder=6)
    ax.set_xlim(-100, 100); ax.set_ylim(-8, 35)
    ax.set_xticks([-100, -50, 0, 50, 100]); ax.set_yticks([0, 10, 20, 30])
    ax.tick_params(labelsize=S.SMALL + 1)
    ax.set_xlabel("Time from the DS peak (ms)", fontsize=S.NOTE)
    ax.set_ylabel("240–420 Hz (dB)", fontsize=S.NOTE)
    group_key(fig, 0.62, 0.93, [("Control DS", S.PT_CTL), ("IED\u2212 DS", S.PT_NEG_LINE), ("IED+ DS", S.PT_DS), ("IED+ BT", S.PT_BT),
                                ("IED+ IED", S.PT_IED)], fs=10)
    S.save(fig, os.path.join(OUT, "X_in_time.png"))
    print("X_in_time")


# ================================================================================================= X_spectra
def x_spectra():
    pg = V.page(os.path.join(JM, "05_q4_dominant_frequency.pdf"))
    P = [((58, 140), V.Axis(68.0, 100, 131.9, 500), V.Axis(213.6, 10, 239.3, 5), "Upper MML", [5, 10]),
         ((145, 228), V.Axis(155.5, 100, 219.6, 500), V.Axis(192.0, 12.5, 245.5, 2.5), "Upper OML", [2.5, 5, 7.5, 10, 12.5]),
         ((232, 316), V.Axis(243.2, 100, 307.3, 500), V.Axis(203.2, 12.5, 246.6, 5.0), "Lower MML", [5, 7.5, 10, 12.5]),
         ((320, 402), V.Axis(331.2, 100, 395.3, 500), V.Axis(190.5, 12.5, 243.9, 2.5), "Lower OML", [2.5, 5, 7.5, 10, 12.5])]
    W, H = 7.0, 2.6
    fig = S.figure(W, H)
    for k, ((x0, x1), xa, ya, name, yt) in enumerate(P):
        ps = V.paths(pg, (x0, 185, x1, 252))
        ax = S.ax_at(fig, 0.72 + k * 1.6, 0.3, 1.3, 1.78)
        for p, q, c, a in bands(ps):
            ax.add_patch(Polygon(np.column_stack([xa(q[:, 0]), ya(q[:, 1])]), closed=True, fc=c, ec="none", alpha=0.16, zorder=1))
        for p, q, c in strokes(ps, minlen=30):
            ax.plot(xa(q[:, 0]), ya(q[:, 1]), c=c, lw=1.4, zorder=2)
        ax.set_xlim(60, 505); ax.set_xticks([100, 300, 500])
        ax.set_yticks(yt)
        ax.tick_params(labelsize=S.SMALL)
        ax.set_title(name, fontsize=S.SMALL + 1, fontweight="bold", loc="left", pad=2)
        if k == 0:
            ax.set_ylabel("Added power at the DS\n(dB over before)", fontsize=S.SMALL + 1)
    S.text_at(fig, 0.72 + 1.6 * 1.5 + 0.65, 2.5, "Frequency (Hz)", ha="center", va="bottom", fontsize=S.NOTE)
    S.save(fig, os.path.join(OUT, "X_spectra.png"))
    print("X_spectra")


# ================================================================================================= X_vs_wt
def x_vs_wt():
    pg = V.page(os.path.join(JM, "08b_q7_supp_classes_and_q4.pdf"))
    P = [((60, 200), [85.5, 119.6, 153.9, 188.3], V.Axis(537.1, 20, 458.1, 50), "Fast power (dB)", (10, 55), [20, 30, 40, 50],
          ["***", "***", "***", "***", "***"], "Fast power"),
         ((230, 370), [264.6, 295.8, 327.4, 358.6], V.Axis(561.2, 0, 465.9, 2.0), "Upper MML sink (control = 1)", (-0.05, 2.65),
          [0, 0.5, 1.0, 1.5, 2.0], ["n.s.", "*", "n.s.", "n.s.", "n.s."], "Upper MML current"),
         ((395, 535), [426.1, 457.7, 489.25, 520.5], V.Axis(550.25, 0.5, 467.4, 3.0), "Lower MML sink (control = 1)", (0.1, 4.0),
          [0.5, 1.0, 2.0, 3.0], ["n.s.", "*", "n.s.", "n.s.", "n.s."], "Lower MML current")]
    pairs = [(0, 1), (1, 2), (0, 2), (1, 3), (0, 3)]                 # bottom to top, as on the source
    cols = [S.PT_CTL, S.PT_DS, S.PT_BT, S.PT_IED]
    W, H = 7.3, 3.4
    fig = S.figure(W, H)
    for k, ((x0, x1), cats, ya, ylab, ylim, yt, stars, title) in enumerate(P):
        ps = V.paths(pg, (x0, 450, x1, 575))
        ax = S.ax_at(fig, 0.72 + k * 2.27, 0.42, 1.75, 2.62)
        cx = lambda x: np.interp(x, cats, [0, 1, 2, 3])            # noqa: E731
        for p, q, c in strokes(ps, minlen=3):
            if c == S.PT_NEG_LINE or V.near(p["stroke"], (0.91, 0.64, 0.79), 0.1) or V.near(p["stroke"], (0.66, 0.2, 0.43), 0.12):
                ax.plot(cx(q[:, 0]), ya(q[:, 1]), c=S.PT_POS, lw=0.7, alpha=0.45, zorder=1)
        vals = {i: [] for i in range(4)}
        for m in V.markers(ps, maxsize=4.5):
            c = newc(m["fill"])
            if c in cols:
                i = int(np.argmin([abs(m["x"] - v) for v in cats]))
                vals[i].append(float(ya(m["y"])))
                ax.scatter([cx(m["x"])], [ya(m["y"])], s=26, color=cols[i], edgecolor="white", lw=0.5, zorder=3)
        for i in range(4):
            if vals[i]:
                ax.plot([i - 0.25, i + 0.25], [np.median(vals[i])] * 2, c=S.INK, lw=1.8, zorder=4, solid_capstyle="butt")
        y0, step = ylim[1] - (ylim[1] - ylim[0]) * 0.30, (ylim[1] - ylim[0]) * 0.062
        for j, ((a, b), st) in enumerate(zip(pairs, stars)):
            yb = y0 + j * step
            ax.plot([a, a, b, b], [yb - step * 0.3, yb, yb, yb - step * 0.3], c=S.INK if st != "n.s." else S.FAINT, lw=0.9)
            ax.text((a + b) / 2, yb - step * 0.08, st, ha="center", va="bottom", fontsize=S.SMALL if st != "n.s." else 9,
                    color=S.INK if st != "n.s." else S.SOFT)
        ax.set_ylim(*ylim); ax.set_yticks(yt)
        ax.set_xticks(range(4)); ax.set_xticklabels(["Ctl\nDS", "IED+\nDS", "IED+\nBT", "IED+\nIED"], fontsize=S.SMALL)
        for tl, c in zip(ax.get_xticklabels(), cols):
            tl.set_color(c if c != S.PT_CTL else S.INK)
        ax.tick_params(axis="x", length=0); ax.set_xlim(-0.5, 3.5)
        ax.tick_params(axis="y", labelsize=S.SMALL + 0.5)
        ax.set_ylabel(ylab, fontsize=S.SMALL + 1)
        ax.set_title(title, fontsize=S.SMALL + 1, fontweight="bold", loc="left", pad=2)
    S.save(fig, os.path.join(OUT, "X_vs_wt.png"))
    print("X_vs_wt")


# ================================================================================================= X_borders
def x_borders():
    pg = V.page(os.path.join(JM, "08b_q7_supp_classes_and_q4.pdf"))
    ya = V.Axis(272.2, 0, 184.7, 50)
    P = [((60, 200), V.Axis(71.8, 100, 150.1, 1000, log=True), "Largest amplitude (\u00b5V)", True),
         ((225, 345), V.Axis(244.4, 5, 334.8, 25), "Half-width (ms)", False)]
    W, H = 5.4, 2.9
    fig = S.figure(W, H)
    rng = np.random.RandomState(1)
    for k, ((x0, x1), xa, xl, log) in enumerate(P):
        ps = V.paths(pg, (x0, 175, x1, 300))
        ax = S.ax_at(fig, 0.62 + k * 2.45, 0.3, 2.1, 2.1)
        M = V.markers(ps, maxsize=3.0, minsize=0.5)
        for c_src, c, s, a, z in (((0.18, 0.43, 0.71), S.PT_DS, 2.0, 0.25, 1), ((0.69, 0.69, 0.69), S.PT_CTL, 5, 0.6, 2),
                                  ((0.56, 0.27, 0.68), S.PT_BT, 7, 0.85, 3), ((0.84, 0.15, 0.16), S.PT_IED, 7, 0.85, 4)):
            pts = np.array([(m["x"], m["y"]) for m in M if V.near(m["fill"], c_src, 0.06)])
            if len(pts):
                ax.scatter(xa(pts[:, 0]), ya(pts[:, 1]), s=s, color=c, edgecolor="none", alpha=a, zorder=z, rasterized=True)
        for p, q, c in strokes(ps, minlen=20):
            if p["width"] >= 0.9:
                ax.plot(xa(q[:, 0]), ya(q[:, 1]), c=c, lw=1.8, zorder=5)
        if log:
            ax.set_xscale("log"); ax.set_xlim(90, 4000); ax.set_xticks([100, 300, 1000, 3000]); ax.set_xticklabels(["100", "300", "1000", "3000"])
        else:
            ax.set_xlim(2, 28); ax.set_xticks([5, 10, 15, 20, 25])
        ax.set_ylim(-12, 54); ax.set_yticks([0, 20, 40])
        if k:
            ax.set_yticklabels([])
        ax.tick_params(labelsize=S.SMALL + 0.5)
        ax.set_xlabel(xl, fontsize=S.NOTE)
    fig.axes[0].set_ylabel("Fast power (dB)", fontsize=S.NOTE)
    hs = [Line2D([], [], ls="", marker="o", ms=5, mfc=c, mec="none", label=l) for l, c in (("DS", S.PT_DS), ("BT", S.PT_BT), ("IED class", S.PT_IED))]
    hs += [Line2D([], [], color=S.PT_DS, lw=1.8, label="DS border"), Line2D([], [], color=S.PT_IED, lw=1.8, label="IED border")]
    fig.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.55, 1.0), ncol=5, fontsize=10, handlelength=1.0, columnspacing=0.8,
               handletextpad=0.3)
    S.save(fig, os.path.join(OUT, "X_borders.png"))
    print("X_borders")


# ================================================================================================= X_examples
def x_examples():
    pg = V.page(os.path.join(DSM, "02_primer.pdf"))
    P = [((60, 156), V.Axis(71.1, -50, 148.3, 50), V.Axis(404.0, 400, 449.9, -400), V.Axis(476.6, 10, 503.6, -10),
          "DS: 994 \u00b5V, 7.7 ms, 18 dB", S.PT_DS, [-400, 0, 400], [-10, 0, 10]),
         ((180, 270), V.Axis(186.4, -50, 264.4, 50), V.Axis(420.7, 0, 444.2, -600), V.Axis(478.0, 150, 501.8, -150),
          "BT: 1084 \u00b5V, 7.3 ms, 26 dB", S.PT_BT, [-600, 0], [-150, 0, 150]),
         ((290, 390), V.Axis(302.1, -50, 380.0, 50), V.Axis(404.0, 800, 456.6, -800), V.Axis(475.1, 150, 505.0, -150),
          "IED: 1068 \u00b5V, 5.9 ms, 32 dB", S.PT_IED, [-800, 0, 800], [-150, 0, 150])]
    W, H = 8.4, 2.9
    fig = S.figure(W, H)
    for k, ((x0, x1), xa, ya, yb, title, col, yt1, yt2) in enumerate(P):
        for r, (y0, y1, ax_y, yt, h, top) in enumerate(((395, 465, ya, yt1, 1.25, 0.28), (467, 512, yb, yt2, 0.75, 1.68))):
            ps = V.paths(pg, (x0, y0, x1, y1))
            ax = S.ax_at(fig, 0.75 + k * 2.6, top, 2.25, h)
            for p in ps:
                if p["type"] == "f" and p["fill"] is not None and min(p["fill"]) > 0.8 and max(p["fill"]) < 0.97 and p["rect"].width > 5:
                    ax.axvspan(float(xa(p["rect"].x0)), float(xa(p["rect"].x1)), color="#EEF0F3", lw=0, zorder=0)
            for p, q, c in strokes(ps, minlen=45):
                if c != col:
                    continue                                    # a neighbour's trace, running under this panel
                ax.plot(xa(q[:, 0]), ax_y(q[:, 1]), c=col, lw=1.2 if r == 0 else 1.0, zorder=2)
            ax.set_xlim(-60, 60); ax.set_yticks(yt)
            ax.tick_params(labelsize=S.SMALL)
            if r == 0:
                ax.set_xticks([-50, 0, 50], [])
                ax.set_title(title, fontsize=S.SMALL + 1, color=col, fontweight="bold", loc="left", pad=3)
            else:
                ax.set_xticks([-50, 0, 50])
            if k == 0:
                ax.set_ylabel("LFP (\u00b5V)" if r == 0 else "240\u2013420 Hz", fontsize=S.SMALL + 1)
    S.text_at(fig, 0.75 + 2.6 + 1.1, 2.88, "Time from the peak (ms)", ha="center", va="bottom", fontsize=S.NOTE)
    S.save(fig, os.path.join(OUT, "X_examples.png"))
    print("X_examples")


if __name__ == "__main__":
    import sys
    want = sys.argv[1:] or ["output", "in_time", "spectra", "vs_wt", "borders", "examples"]
    for w in want:
        globals()["x_" + w]()
