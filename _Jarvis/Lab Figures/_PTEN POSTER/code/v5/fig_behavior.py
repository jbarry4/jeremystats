"""PTEN poster v5: the behavior figures, read back out of the PTEN behavioral menu's vector pages (the report's own figures)
and redrawn in the poster's look: Aptos, white ground, and the DS section's group colours (the user: "make this match
the color scheme from the IEDs and Dentate spikes"): WT grey, Lo KO pink, Hi KO magenta; IED+ mice as diamonds where the
source marks them. Every number, n and P value printed on a source panel is carried over as printed. Axis calibrations are
the sources' own tick positions (read with gridview.py; noted beside each).

  B_cued, B_hidden        page 4 a/b and c/d: one WT, Lo and Hi mouse per phase (runs, rewards, goals) with the session
                          numbers, and rewards and proportion of time in goal per phase (mean +- SE)
  B_criterion, _ko        page 3 a, b: sessions to criterion by group; against % KO with the quadratic fit
  B_oldplace, B_neverused, B_predicts   page 6 a, b, c
  B_former_hidden, _cued  page 13 a, b
  B_speed                 page 10 c
  B_stay, B_entries, B_prev_ko, B_rpe_ko   page 17 b, c, d, e"""
import os
import numpy as np
import fitz
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon, Rectangle
import style as S
import vec as V

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
BMP = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\PTEN POSTER\Menus, etc\PTEN_Behavioral_Menu\pages"
BLUE, GREEN, RED, GREY = (0.16, 0.47, 0.84), (0.0, 0.51, 0.0), (0.89, 0.29, 0.28), (0.42, 0.42, 0.40)
COL = {BLUE: S.PT_CTL, GREEN: S.PT_NEG_LINE, RED: S.PT_POS, GREY: "#5F6B7A"}
FILLC = {BLUE: S.PT_CTL, GREEN: S.PT_NEG, RED: S.PT_POS, GREY: "#5F6B7A"}
NAME = {BLUE: "WT", GREEN: "Lo KO", RED: "Hi KO"}
NOVEL = "#F3F4F6"                                   # the phases with a new goal (8-10), as the source's grey band


def pdf(n):
    return os.path.join(BMP, n)


def group_of(c):
    return next((k for k in COL if V.near(c, k, 0.08)), None)


def key_handles(ied=True, pooled=False):
    hs = [Line2D([], [], ls="", marker="o", ms=7, mfc=FILLC[c], mec="white", label=NAME[c]) for c in (BLUE, GREEN, RED)]
    if ied:
        hs.append(Line2D([], [], ls="", marker="D", ms=6.5, mfc="white", mec=S.INK, mew=1.0, label="IED+"))
    if pooled:
        hs.append(Line2D([], [], ls="", marker="D", ms=6.5, mfc=COL[GREY], mec="white", label="all KO"))
    return hs


def style_ax(ax, fs=S.SMALL + 1):
    ax.tick_params(labelsize=fs)


def bracket(ax, x0, x1, y, text, h=None, fs=S.SMALL + 0.5, color=S.INK):
    h = h if h is not None else (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.025
    ax.plot([x0, x0, x1, x1], [y - h, y, y, y - h], c=color, lw=1.0, clip_on=False)
    ax.text((x0 + x1) / 2, y + h * 0.4, text, ha="center", va="bottom", fontsize=fs, color=color, clip_on=False)


# ================================================================================================= runs + measures (p.4)
RUNS = {
    "cued": dict(cy=[185.4, 239.8, 294.1], stats=[["42 \u00b7 139 \u00b7 1.11 s", "32 \u00b7 107 \u00b7 1.52 s", "28 \u00b7 88 \u00b7 1.66 s", "39 \u00b7 74 \u00b7 1.99 s"],
                                                ["21 \u00b7 67 \u00b7 1.27 s", "35 \u00b7 70 \u00b7 1.96 s", "18 \u00b7 55 \u00b7 1.78 s", "25 \u00b7 38 \u00b7 2.44 s"],
                                                ["19 \u00b7 50 \u00b7 1.34 s", "44 \u00b7 82 \u00b7 1.82 s", "24 \u00b7 102 \u00b7 1.08 s", "32 \u00b7 81 \u00b7 1.59 s"]],
                 meas=[("Rewards", (165, 252), V.Axis(221.1, 20, 182.2, 35), (17, 36), [20, 25, 30, 35], {7: "L"}),
                       ("Time in goal (share)", (256, 340), V.Axis(295.2, 0.05, 265.9, 0.07), (0.043, 0.072), [0.05, 0.06, 0.07], {})]),
    "hidden": dict(cy=[397.7, 452.0, 506.4], stats=[["21 \u00b7 92 \u00b7 1.03 s", "12 \u00b7 25 \u00b7 2.21 s", "10 \u00b7 23 \u00b7 2.37 s", "16 \u00b7 35 \u00b7 1.40 s"],
                                                  ["13 \u00b7 47 \u00b7 1.42 s", "7 \u00b7 32 \u00b7 1.24 s", "3 \u00b7 35 \u00b7 0.57 s", "9 \u00b7 24 \u00b7 1.08 s"],
                                                  ["10 \u00b7 41 \u00b7 1.01 s", "6 \u00b7 44 \u00b7 0.55 s", "17 \u00b7 54 \u00b7 1.06 s", "4 \u00b7 44 \u00b7 1.13 s"]],
                   meas=[("Rewards", (388, 460), V.Axis(448.8, 5, 400.5, 25), (3, 26), [5, 10, 15, 20, 25], {7: "L", 10: "H"}),
                         ("Time in goal (share)", (475, 560), V.Axis(519.0, 0.02, 483.1, 0.05), (0.013, 0.052), [0.02, 0.03, 0.04, 0.05],
                          {9: "L", 10: "LH"})]),
}
CX = [128.7, 185.4, 242.1, 298.9]
PHASE_X = V.Axis(360.6, 7, 419.7, 10)


def b_runs(which):
    cfg = RUNS[which]
    pg = V.page(pdf("04_the_task_and_the_session_measures.pdf"))
    W, H = 7.0, 3.55
    fig = S.figure(W, H)
    D = 1.02                                                      # arena diameter on the poster, in
    X0, Y0 = 0.42, 0.3
    rowlab = ["WT · M22", "Lo · M33", "Hi · M34"]
    rowcol = [S.PT_CTL, S.PT_NEG_LINE, S.PT_POS]
    for i, cy in enumerate(cfg["cy"]):
        for j, cx in enumerate(CX):
            ps = V.paths(pg, (cx - 23, cy - 23, cx + 23, cy + 23))
            ax = S.ax_at(fig, X0 + j * (D + 0.08), Y0 + i * (D + 0.12), D, D)
            ax.set_xlim(cx - 21.5, cx + 21.5); ax.set_ylim(cy + 21.5, cy - 21.5); ax.set_aspect("equal"); ax.axis("off")
            ax.add_patch(Circle((cx, cy), 20.7, fc="#F6F7F9", ec="#B9C1CB", lw=0.9, zorder=0))
            for p in ps:
                if p["type"] not in ("s", "fs"):
                    continue
                q = V.polyline(p)
                if len(q) < 2:
                    continue
                st = p["stroke"]
                if V.near(st, (0.79, 0.78, 0.76), 0.05) and p["width"] < 0.3:
                    ax.plot(q[:, 0], q[:, 1], c="#E1E5EA", lw=0.22, zorder=1)
                elif group_of(st) in (BLUE, GREEN, RED) and p["width"] < 0.6:
                    ax.plot(q[:, 0], q[:, 1], c=COL[group_of(st)], lw=0.7, alpha=0.95, zorder=2)
                elif V.near(st, (0.04, 0.04, 0.04), 0.05) and p["rect"].width < 9:
                    ax.add_patch(Circle(((p["rect"].x0 + p["rect"].x1) / 2, (p["rect"].y0 + p["rect"].y1) / 2), p["rect"].width / 2,
                                        fc="none", ec=S.INK, lw=1.5, zorder=4))
                elif max(st) < 0.75 and p["rect"].width < 9 and p["rect"].width > 4:
                    ax.add_patch(Circle(((p["rect"].x0 + p["rect"].x1) / 2, (p["rect"].y0 + p["rect"].y1) / 2), p["rect"].width / 2,
                                        fc="none", ec="#8A94A0", lw=0.8, zorder=3))
            for m in V.markers(ps, maxsize=2.0, minsize=0.5):
                if V.near(m["fill"], (0.04, 0.04, 0.04), 0.05):
                    ax.add_patch(Circle((m["x"], m["y"]), 0.75, fc=S.INK, ec="white", lw=0.25, zorder=5))
            S.text_at(fig, X0 + j * (D + 0.08) + D / 2, Y0 + i * (D + 0.12) + D + 0.005, cfg["stats"][i][j], ha="center", va="top",
                      fontsize=9.5, color=S.SOFT)
            if i == 0:
                S.text_at(fig, X0 + j * (D + 0.08) + D / 2, 0.05, ["Phase 7 (trained)", "Phase 8", "Phase 9", "Phase 10"][j], ha="center",
                          fontsize=S.SMALL + 0.5, fontweight="bold")
        S.text_at(fig, 0.2, Y0 + i * (D + 0.12) + D / 2, rowlab[i], rotation=90, ha="center", va="center", fontsize=S.SMALL,
                  color=rowcol[i], fontweight="bold")
    # rewards and time in goal per phase
    R = V.Render(pg, (340, 150 if which == "cued" else 380, 446, 345 if which == "cued" else 570), z=8)
    for k, (lab, (ya, yb), yax, ylim, yt, letters) in enumerate(cfg["meas"]):
        ax = S.ax_at(fig, 5.05, 0.32 + k * 1.72, 1.75, 1.28)
        ax.axvspan(7.5, 10.5, color=NOVEL, lw=0, zorder=0)
        ps = V.paths(pg, (350, ya, 446, yb))
        for c in (BLUE, GREEN, RED):
            pts = sorted([(m["x"], m["y"]) for m in V.markers(ps, maxsize=3.2) if V.near(m["fill"], c, 0.08)])
            if not pts:
                continue
            xs = np.round(PHASE_X(np.array([p[0] for p in pts])))
            ys = yax(np.array([p[1] for p in pts]))
            off = {BLUE: -0.09, GREEN: 0.0, RED: 0.09}[c]
            ax.plot(xs + off, ys, c=COL[c], lw=1.6, zorder=2)
            for (px_, py_), x_, y_ in zip(pts, xs, ys):
                lo, hi = R.whisker(px_, py_, c, tol=60, gap=7, half=0.3, vertical=True)
                ax.plot([x_ + off] * 2, [yax(lo), yax(hi)], c=COL[c], lw=1.0, zorder=2)
                ax.scatter([x_ + off], [y_], s=22, color=FILLC[c], edgecolor="white", lw=0.5, zorder=3)
        for ph, t in letters.items():
            ax.text(ph, ylim[1] * 0.995 if ylim[1] > 1 else ylim[1] - (ylim[1] - ylim[0]) * 0.01, t, ha="center", va="top",
                    fontsize=S.SMALL, fontweight="bold")
        ax.set_xlim(6.6, 10.4); ax.set_ylim(*ylim)
        ax.set_xticks([7, 8, 9, 10]); ax.set_yticks(yt)
        if k == 1:
            ax.set_xticklabels(["7", "8", "9", "10"]); ax.set_xlabel("Phase", fontsize=S.SMALL + 1, labelpad=1)
        else:
            ax.set_xticklabels([])
        if max(yt) < 1:
            ax.set_yticklabels(["%.2f" % v for v in yt])
        style_ax(ax, S.SMALL)
        ax.set_title(lab, fontsize=S.SMALL + 1, fontweight="bold", loc="left", pad=3)
    S.save(fig, os.path.join(OUT, "B_%s.png" % which))
    print("B_%s" % which)


# ================================================================================================= sessions to criterion (p.3)
def b_criterion():
    pg = V.page(pdf("03_learning_the_cue_rule.pdf"))
    ps = V.paths(pg, (41, 175, 222, 336))
    ya = V.Axis(302.6, 0, 183.3, 35)                       # 0 and 35 sessions
    cats = [84.0, 109.9, 136.0, 173.6]                     # WT, Lo, Hi, all KO
    W, H = 3.0, 2.7
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.5, 0.28, 2.42, 1.9)
    stats = [(8.8, 0.5), (21.2, 2.1), (14.0, 2.8), (17.3, 2.0)]
    for m in V.markers(ps, maxsize=5):
        g = group_of(m["fill"])
        if g is None:
            continue
        k = int(np.argmin([abs(m["x"] - c) for c in cats]))
        x = k + (m["x"] - cats[k]) / 26.0 - 0.12
        ax.scatter([x], [ya(m["y"])], s=26, marker="D" if g == GREY else "o", color=FILLC[g], edgecolor="white", lw=0.5, zorder=3)
    for k, (mu, se) in enumerate(stats):
        ax.errorbar([k + 0.22], [mu], yerr=[se], fmt="none", ecolor=S.INK, elinewidth=1.3, capsize=3.5, capthick=1.3, zorder=4)
        ax.plot([k + 0.12, k + 0.32], [mu, mu], c=S.INK, lw=1.8, zorder=4)
        ax.text(k + 0.22, mu + se + 0.6, "%.1f\n± %.1f" % (mu, se), fontsize=9, va="bottom", ha="center", color=S.SOFT, linespacing=0.95)
    ax.axhline(8.8, c=S.FAINT, lw=0.9, ls=(0, (3, 2)), zorder=1)
    ax.set_ylim(0, 42)
    bracket(ax, 0, 1, 32.5, "P < 0.001", h=0.9, fs=10)
    bracket(ax, 1, 2, 32.5, "P 0.08", h=0.9, fs=10)
    bracket(ax, 0, 3, 38.0, "P < 0.001", h=0.9, fs=10)
    ax.set_xticks(range(4)); ax.set_xticklabels(["WT\nn 18", "Lo\nn 5", "Hi\nn 6", "All KO\nn 13"], fontsize=S.SMALL)
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.45, 3.85); ax.set_yticks([0, 10, 20, 30])
    style_ax(ax)
    ax.set_ylabel("Sessions to criterion", fontsize=S.NOTE)
    S.save(fig, os.path.join(OUT, "B_criterion.png"))
    print("B_criterion")


def b_criterion_ko():
    pg = V.page(pdf("03_learning_the_cue_rule.pdf"))
    ps = V.paths(pg, (222, 175, 420, 336))
    xa, ya = V.Axis(263.2, 0, 390.8, 30), V.Axis(304.8, 0, 197.8, 25)
    # the source's mouse labels, each beside its point (page pt of the point, read from the grid render)
    labs = {"M10": (303.8, 185.2), "M29": (356.9, 197.8), "M8": (280.1, 215.0), "M1": (285.5, 210.9), "M30": (288.8, 219.1),
            "M33": (301.0, 230.7), "M34 IED+": (384.3, 223.3), "M3 IED+": (367.7, 244.6), "M7": (366.0, 265.7), "M28 IED+": (349.3, 270.0),
            "M5 IED+": (381.0, 265.7)}
    W, H = 2.9, 2.7
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.5, 0.28, 2.3, 1.9)
    ax.axvspan(9.5, 20.2, color=NOVEL, lw=0, zorder=0)
    ax.text(14.85, 1.2, "no mice\n9.5\u201320.2%", ha="center", va="bottom", fontsize=9.5, color=S.SOFT, linespacing=1.0)
    M = [m for m in V.markers(ps, maxsize=5) if group_of(m["fill"]) in (BLUE, GREEN, RED)]
    for p in ps:
        if p["type"] == "s" and V.near(p["stroke"], (0.32, 0.32, 0.31), 0.05) and p["width"] > 0.9:
            q = V.polyline(p)
            ax.plot(xa(q[:, 0]), ya(q[:, 1]), c=S.INK, lw=1.5, zorder=2)
    for m in M:
        g = group_of(m["fill"])
        nm = min(labs, key=lambda k: (labs[k][0] - m["x"]) ** 2 + (labs[k][1] - m["y"]) ** 2)
        near_ = (labs[nm][0] - m["x"]) ** 2 + (labs[nm][1] - m["y"]) ** 2 < 25
        ied = near_ and "IED+" in nm
        x = xa(m["x"]) + (0 if g != BLUE else 0)
        ax.scatter([x], [ya(m["y"])], s=30 if ied else 26, marker="D" if ied else "o", color=FILLC[g], edgecolor=S.INK if ied else "white",
                   lw=0.8 if ied else 0.5, zorder=3)
        if near_:
            ax.text(x + 0.7, ya(m["y"]) + 0.3, nm.replace(" IED+", ""), fontsize=8.5, color=S.SOFT, va="bottom", ha="left")
    ax.set_xlim(-2, 31); ax.set_ylim(0, 30)
    ax.set_xticks([0, 10, 20, 30]); ax.set_yticks([0, 10, 20, 30])
    style_ax(ax)
    ax.set_xlabel("% granule cells KO", fontsize=S.NOTE)
    ax.set_ylabel("Sessions to criterion", fontsize=S.NOTE)
    S.save(fig, os.path.join(OUT, "B_criterion_ko.png"))
    print("B_criterion_ko")


if __name__ == "__main__":
    import sys
    want = sys.argv[1:] or ["runs"]
    if "runs" in want:
        b_runs("cued")
        b_runs("hidden")
    if "criterion" in want:
        b_criterion()
        b_criterion_ko()
