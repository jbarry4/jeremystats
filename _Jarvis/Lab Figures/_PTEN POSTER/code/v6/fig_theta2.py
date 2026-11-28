"""PTEN poster v5: the theta-CSD and CNO graphs of the behavior report (menu pages 20 b, 22 a, 23 b), read back out of the
vector pages and redrawn in the poster's look (Aptos, the DS section's group colours). Every number and P value printed on
the source is kept as printed. Axis calibrations are the source's own tick positions (read with gridview.py).

  T_profiles   theta CSD per layer by IED status: baseline, after CNO, the change (mean +- SE; stars as on the source)
  T_roc        MML2 + GCL2 theta current: ROC at baseline and after CNO, and each mouse from baseline to CNO
  T_dreadd     CNO and the hM4D-expressing KO granule neurons: firing against current, aCSF and CNO"""
import os
import numpy as np
import fitz
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
import style as S
import vec as V
from digitize_theta import BM

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
BLUE, GREEN, RED = (0.16, 0.47, 0.84), (0.0, 0.51, 0.0), (0.89, 0.29, 0.28)          # the report's WT, Lo, Hi
NEW = {BLUE: S.PT_CTL, GREEN: S.PT_NEG_LINE, RED: S.PT_POS}


def recolor(c):
    for k, v in NEW.items():
        if V.near(c, k, 0.08):
            return v
    return None


# ================================================================================================= T_profiles
def t_profiles():
    pg = V.page(os.path.join(BM, "20_theta_csd_by_layer.pdf"))
    R = V.Render(pg, (128, 392, 482, 522), z=8)
    ps = V.paths(pg, (130, 392, 482, 522))
    axes = [V.Axis(158.7, 0.0, 254.7, 0.08), V.Axis(270.9, 0.0, 366.9, 0.08), V.Axis(435.3, 0.0, 452.9, 0.01)]
    xr = [(150, 262), (262, 375), (375, 482)]
    rows = 401.6 + 14.1 * np.arange(9)
    layers = ["CA1 SP", "CA1 SLM", "OML1", "MML1", "GCL1", "Hilus", "GCL2", "MML2", "OML2"]
    pts = {}
    for m in V.markers(ps, maxsize=5.5):
        col = next((k for k in NEW if V.near(m["fill"], k, 0.08)), None)
        if col is None or m["y"] < 392:
            continue
        k = next(i for i, (a, b) in enumerate(xr) if a <= m["x"] < b)
        row = int(np.argmin(np.abs(rows - m["y"])))
        lo, hi = R.whisker(m["x"], m["y"], col, tol=50, gap=4, half=0.35)
        pts[(k, col, row)] = (float(axes[k](m["x"])), float(axes[k](lo)), float(axes[k](hi)), m["y"] - rows[row])
    # the stars: small filled glyphs in the group colours, grouped into runs
    stars = []
    for col in (GREEN, RED):
        gl = sorted([p["rect"] for p in ps if p["type"] == "f" and V.near(p["fill"], col, 0.06) and p["rect"].width < 3 and p["rect"].height < 3],
                    key=lambda r: (round(r.y0), r.x0))
        runs = []
        for r in gl:
            if runs and abs(runs[-1][-1].y0 - r.y0) < 1 and r.x0 - runs[-1][-1].x1 < 2:
                runs[-1].append(r)
            else:
                runs.append([r])
        for run in runs:
            x, y = (run[0].x0 + run[-1].x1) / 2, (run[0].y0 + run[0].y1) / 2
            k = next(i for i, (a, b) in enumerate(xr) if a <= x < b)
            stars.append((k, col, int(np.argmin(np.abs(rows - y))), "*" * len(run), float(axes[k](x))))
    W, H = 7.2, 3.75
    fig = S.figure(W, H)
    titles = ["Baseline", "After CNO", "CNO − baseline"]
    lims = [(0, 0.08), (0, 0.08), (-0.03, 0.022)]
    for k in range(3):
        ax = S.ax_at(fig, 1.0 + k * 2.1, 0.55, 1.8, 2.62)
        ax.axhspan(5 - 0.5, 5 + 0.5, color="#F2EEE6", lw=0, zorder=0)
        if k == 2:
            ax.axvline(0, c=S.FAINT, lw=0.9, zorder=0)
        for col in (BLUE, GREEN, RED):
            r_ = sorted(r for (kk, c, r) in pts if kk == k and c == col)
            xs = [pts[(k, col, r)][0] for r in r_]
            ys = [r + pts[(k, col, r)][3] / 14.1 for r in r_]
            nc = NEW[col]
            ax.plot(xs, ys, c=nc, lw=1.6, zorder=2)
            for r, x, y in zip(r_, xs, ys):
                _, lo, hi, _ = pts[(k, col, r)]
                ax.plot([lo, hi], [y, y], c=nc, lw=1.1, zorder=2, solid_capstyle="butt")
                ax.scatter([x], [y], s=34 if col != RED else 40, marker="D" if col == RED else "o", color=nc, edgecolor="white",
                           lw=0.6, zorder=3)
        for (kk, col, row, st, xv) in stars:
            if kk != k:
                continue
            ax.text(xv, row + (0.16 if col == RED else -0.02), st, color=NEW[col], fontsize=S.NOTE + 2, fontweight="bold",
                    ha="center", va="center", zorder=4)
        ax.set_ylim(8.6, -0.6)
        ax.set_yticks(range(9))
        ax.set_yticklabels(layers if k == 0 else [], fontsize=S.SMALL + 0.5)
        if k == 0:
            for tl, nm in zip(ax.get_yticklabels(), layers):
                tl.set_color(S.SST if nm == "Hilus" else S.GC if nm.startswith("GCL") else S.INK)
        ax.set_xlim(*lims[k])
        if k < 2:
            ax.set_xticks([0, 0.04, 0.08], ["0", "0.04", "0.08"])
        else:
            ax.set_xticks([-0.02, 0, 0.02], ["−0.02", "0", "0.02"])
        ax.tick_params(labelsize=S.SMALL + 0.5)
        ax.set_title(titles[k], fontsize=S.NOTE + 0.5, fontweight="bold", pad=4)
        ax.set_xlabel("Theta CSD (a.u.)" if k < 2 else "Change", fontsize=S.NOTE)
    hs = [Line2D([], [], color=S.PT_CTL, marker="o", ms=6, mec="white", lw=1.6, label="WT (10)"),
          Line2D([], [], color=S.PT_NEG_LINE, marker="o", ms=6, mec="white", lw=1.6, label="KO, no IEDs (8)"),
          Line2D([], [], color=S.PT_POS, marker="D", ms=6, mec="white", lw=1.6, label="KO, IEDs (5)")]
    fig.legend(handles=hs, loc="upper center", bbox_to_anchor=(0.57, 1.01), ncol=3, fontsize=S.NOTE, handlelength=1.6, columnspacing=1.2)
    S.save(fig, os.path.join(OUT, "T_profiles.png"))
    print("T_profiles: %d points, %d star runs" % (len(pts), len(stars)))


# ================================================================================================= T_roc
def t_roc():
    pg = V.page(os.path.join(BM, "22_theta_csd_marks_the_ied_mice.pdf"))
    ps = V.paths(pg, (134, 151, 470, 283))
    ax_x, ax_y = V.Axis(175.6, 0, 263.8, 1), V.Axis(261.4, 0, 172.8, 1)
    my = V.Axis(262.6, 0, 179.5, 0.08)
    cats = [339.1, 392.4, 445.6]
    W, H = 7.3, 3.2
    fig = S.figure(W, H)
    a = S.ax_at(fig, 0.72, 0.45, 2.3, 2.3)
    a.plot([0, 1], [0, 1], c=S.FAINT, lw=0.9, ls=(0, (3, 2)))
    for p in ps:
        if p["type"] != "s" or p["rect"].x1 > 275:
            continue
        if p["rect"].y0 > 244 and p["rect"].width < 14 and p["rect"].x0 > 180:
            continue                                                       # the source's legend keys
        if V.near(p["stroke"], (0.04, 0.04, 0.04), 0.05) and p["width"] > 1.2:
            col, lw = S.PT_POS, 2.4
        elif V.near(p["stroke"], (0.54, 0.54, 0.51), 0.05) and p["width"] > 1.2:
            col, lw = S.PT_CTL, 2.4
        else:
            continue
        q = V.polyline(p)
        a.plot(ax_x(q[:, 0]), ax_y(q[:, 1]), c=col, lw=lw, solid_capstyle="butt", zorder=3 if col == S.PT_POS else 2)
    a.set_xlim(-0.02, 1.02); a.set_ylim(-0.02, 1.03)
    a.set_xticks([0, 0.5, 1]); a.set_yticks([0, 0.5, 1])
    a.set_xlabel("False positives", fontsize=S.NOTE); a.set_ylabel("True positives", fontsize=S.NOTE)
    a.tick_params(labelsize=S.SMALL + 0.5)
    a.legend(handles=[Line2D([], [], c=S.PT_POS, lw=2.4, label="Baseline 0.97 (P < 0.001)"),
                      Line2D([], [], c=S.PT_CTL, lw=2.4, label="After CNO 0.78 (P 0.075)")],
             loc="lower right", fontsize=S.SMALL, handlelength=1.0, borderaxespad=0.1, title="AUC", title_fontsize=S.SMALL,
             alignment="left", frameon=True, facecolor="white", edgecolor="none", framealpha=1)
    a.set_title("Loss of AUC with CNO 0.20, P 0.026", fontsize=S.NOTE, loc="left", pad=4)
    # each mouse, baseline -> CNO
    b = S.ax_at(fig, 3.75, 0.45, 3.45, 2.3)
    for p in ps:
        if p["type"] == "s" and p["rect"].x0 > 300 and p["width"] < 1.0:
            c = recolor(p["stroke"])
            if c:
                q = V.polyline(p)
                b.plot(q[:, 0], my(q[:, 1]), c=c, lw=1.0, alpha=0.9, zorder=2)
        if p["type"] == "s" and p["rect"].x0 > 300 and V.near(p["stroke"], (0.04, 0.04, 0.04), 0.05) and p["width"] > 1.2:
            q = V.polyline(p)
            b.plot(q[:, 0], my(q[:, 1]), c=S.INK, lw=3.0, zorder=4, solid_capstyle="butt")
    for m in V.markers(ps, maxsize=5):
        c = recolor(m["fill"])
        if c and m["x"] > 300:
            b.scatter([m["x"]], [my(m["y"])], s=30, marker="D" if m["shape"] == "D" else "o", color=c, edgecolor="white", lw=0.6, zorder=3)
    cut = float(my(227.2))
    b.axhline(cut, c=S.SOFT, lw=0.9, ls=(0, (4, 2)), zorder=1)
    b.text(cats[0] - 24, cut + 0.002, "best baseline cutoff: 5/5 IED, 2/16 false positives", fontsize=S.SMALL, color=S.SOFT, va="bottom")
    b.set_xticks(cats); b.set_xticklabels(["WT", "KO, no IED", "KO, IED"], fontsize=S.SMALL + 1)
    for tl, c in zip(b.get_xticklabels(), (S.INK, S.PT_NEG_LINE, S.PT_POS)):
        tl.set_color(c)
    b.tick_params(axis="x", length=0)
    b.set_xlim(cats[0] - 30, cats[2] + 25)
    b.set_ylim(0, 0.09); b.set_yticks([0, 0.04, 0.08]); b.tick_params(labelsize=S.SMALL + 0.5)
    b.set_ylabel("MML2 + GCL2 theta CSD", fontsize=S.NOTE)
    b.set_title("CNO drop as predictor: AUC 0.89, P 0.008", fontsize=S.NOTE, loc="left", pad=4)
    S.save(fig, os.path.join(OUT, "T_roc.png"))
    print("T_roc")


# ================================================================================================= T_dreadd
def t_dreadd():
    pg = V.page(os.path.join(BM, "23_the_dreadd_works.pdf"))
    ps = V.paths(pg, (330, 172, 522, 270))
    ax_x, ax_y = V.Axis(383.9, 0, 458.1, 100), V.Axis(267.7, 0, 197.4, 15)
    COL = {BLUE: "#4A5361", RED: "#C2571A"}                       # aCSF slate, CNO orange
    W, H = 4.6, 3.2
    fig = S.figure(W, H)
    a = S.ax_at(fig, 0.72, 0.62, 3.0, 2.0)
    for p in ps:
        col = next((k for k in COL if V.near(p["fill"], k, 0.06) or V.near(p["stroke"], k, 0.06)), None)
        if col is None or p["rect"].x0 > 488:
            continue                                               # the source's "aCSF" / "CNO" labels
        q = p["pts"]
        if p["type"] == "f" and max(p["rect"].width, p["rect"].height) > 3:
            a.add_patch(Polygon(np.column_stack([ax_x(q[:, 0]), ax_y(q[:, 1])]), closed=True, fc=COL[col], ec="none", alpha=0.32, zorder=1))
        elif p["type"] == "s":
            q = V.polyline(p)
            a.plot(ax_x(q[:, 0]), ax_y(q[:, 1]), c=COL[col], lw=1.0 if p["width"] < 1 else 2.2, alpha=0.95, zorder=2)
    a.axvline(0, c=S.FAINT, lw=0.9, zorder=0)
    a.set_xlim(-55, 150); a.set_ylim(-0.5, 19)
    a.set_xticks([-50, 0, 50, 100]); a.set_yticks([0, 5, 10, 15])
    a.tick_params(labelsize=S.SMALL + 0.5)
    a.set_xlabel("Current above rheobase (pA)", fontsize=S.NOTE)
    a.set_ylabel("Spikes per sweep", fontsize=S.NOTE)
    a.text(152, 15.5, "aCSF", color=COL[BLUE], fontsize=S.NOTE, fontweight="bold", va="center", clip_on=False)
    a.text(152, 4.5, "CNO", color=COL[RED], fontsize=S.NOTE, fontweight="bold", va="center", clip_on=False)
    S.text_at(fig, 0.72, 0.05, "Drug effect −4.3 spikes/sweep, P 0.037\n(mixed model over 100 matched pairs, 4 df)",
              fontsize=S.SMALL + 0.5, color=S.INK, linespacing=1.15)
    S.save(fig, os.path.join(OUT, "T_dreadd.png"))
    print("T_dreadd")


if __name__ == "__main__":
    import sys
    want = sys.argv[1:] or ["profiles", "roc", "dreadd"]
    if "profiles" in want:
        t_profiles()
    if "roc" in want:
        t_roc()
    if "dreadd" in want:
        t_dreadd()
