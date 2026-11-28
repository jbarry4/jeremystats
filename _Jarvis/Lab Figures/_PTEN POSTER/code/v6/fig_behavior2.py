"""PTEN poster v5: the rest of the behavior figures (see fig_behavior.py for the method and the colours).

  B_oldplace, B_neverused, B_predicts   page 6 a, b, c (cue against place, phase 8)
  B_former_hidden, B_former_cued        page 13 a, b (pause time at former goals)
  B_speed                               page 10 c (speed around goal entries)
  B_stay, B_entries, B_prev_ko, B_rpe_ko   page 17 b, c, d, e (the last hidden rotation)"""
import os
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
import style as S
import vec as V
from fig_behavior import pdf, group_of, COL, FILLC, NAME, BLUE, GREEN, RED, NOVEL, OUT, bracket, style_ax


def _open_markers(ps, maxsize=7.0):
    """open symbols: small closed paths stroked in a group colour with no (or a white) fill."""
    out = []
    for p in ps:
        r = p["rect"]
        if p["type"] in ("s", "fs") and group_of(p["stroke"]) in (BLUE, GREEN, RED) and 2.0 <= r.width <= maxsize \
                and 2.0 <= r.height <= maxsize and (p["fill"] is None or min(p["fill"]) > 0.9):
            out.append(dict(x=(r.x0 + r.x1) / 2, y=(r.y0 + r.y1) / 2, g=group_of(p["stroke"]), D="c" not in p["kinds"]))
    return out


def _dot(ax, x, y, g, shape="o", s=26, open_=False):
    ied = shape == "D"
    if open_:
        ax.scatter([x], [y], s=s * 0.85, marker="D" if ied else "o", facecolor="white", edgecolor=COL[g], lw=1.0, zorder=3)
    else:
        ax.scatter([x], [y], s=s * (1.1 if ied else 1), marker="D" if ied else "o", color=FILLC[g], edgecolor=S.INK if ied else "white",
                   lw=0.7 if ied else 0.5, zorder=3)


# ================================================================================================= page 6
def b_oldplace():
    pg = V.page(pdf("06_cue_against_place.pdf"))
    ps = V.paths(pg, (60, 182, 234, 320))
    ya = V.Axis(313.6, 0, 187.5, 100)                         # 0 and 100 %
    pos = {BLUE: (99.3, 118.8), GREEN: (143.8, 162.4), RED: (185.4, 207.7)}      # old place (filled), cue zone (open)
    gx = lambda g, x: [BLUE, GREEN, RED].index(g) + (x - pos[g][0]) / (pos[g][1] - pos[g][0]) * 0.42 - 0.21   # noqa: E731
    W, H = 2.8, 2.7
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.5, 0.28, 2.22, 1.92)
    for p in ps:
        g = group_of(p["stroke"])
        if p["type"] == "s" and g in pos and p["width"] < 0.8 and p["rect"].width > 3:
            q = V.polyline(p)
            ax.plot(gx(g, q[:, 0]), ya(q[:, 1]), c=COL[g], lw=0.6, alpha=0.7, zorder=1)
    filled, opened = {g: [] for g in pos}, {g: [] for g in pos}
    for m in V.markers(ps, maxsize=8.5):
        g = group_of(m["fill"])
        if g in pos:
            filled[g].append(float(ya(m["y"])))
            _dot(ax, gx(g, m["x"]), ya(m["y"]), g, m["shape"], s=24)
    for m in _open_markers(ps):
        opened[m["g"]].append(float(ya(m["y"])))
        _dot(ax, gx(m["g"], m["x"]), ya(m["y"]), m["g"], "D" if m["D"] else "o", s=24, open_=True)
    for k, g in enumerate([BLUE, GREEN, RED]):
        for vals, dx in ((filled[g], -0.21), (opened[g], 0.21)):
            if vals:
                ax.plot([k + dx - 0.12, k + dx + 0.12], [np.mean(vals)] * 2, c=S.INK, lw=2.0, zorder=4, solid_capstyle="butt")
    ax.set_ylim(-3, 112)
    bracket(ax, -0.21, 0.79, 82, "ns (P 0.242)", h=2.2, fs=9.5)
    bracket(ax, -0.21, 1.79, 97, "* (P 0.010)", h=2.2, fs=9.5)
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["WT", "Lo", "Hi"], fontsize=S.SMALL + 1)
    ax.tick_params(axis="x", length=0); ax.set_xlim(-0.55, 2.55); ax.set_yticks([0, 20, 40, 60, 80])
    style_ax(ax)
    ax.set_ylabel("% of first 10 runs", fontsize=S.NOTE)
    S.save(fig, os.path.join(OUT, "B_oldplace.png"))
    print("B_oldplace n (old, open): %s" % {NAME[g]: (len(filled[g]), len(opened[g])) for g in filled})


def b_neverused():
    pg = V.page(pdf("06_cue_against_place.pdf"))
    ps = V.paths(pg, (280, 182, 420, 330))
    ya = V.Axis(261.1, 0, 206.9, 40)
    cats = {BLUE: 304.9, GREEN: 341.0, RED: 377.1}
    W, H = 2.4, 2.7
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.75, 0.28, 1.6, 1.92)
    ax.axhline(0, c=S.FAINT, lw=0.9, zorder=0)
    vals = {g: [] for g in cats}
    for m in V.markers(ps, maxsize=8.5):
        g = group_of(m["fill"])
        if g in cats:
            k = [BLUE, GREEN, RED].index(g)
            vals[g].append(float(ya(m["y"])))
            _dot(ax, k + (m["x"] - cats[g]) / 36.0, ya(m["y"]), g, m["shape"])
    for k, (g, t, st) in enumerate(zip([BLUE, GREEN, RED], ["P 0.007", "P 0.016", "P 0.578"], ["**", "*", "ns"])):
        ax.plot([k - 0.25, k + 0.25], [np.mean(vals[g])] * 2, c=S.INK, lw=2.0, zorder=4, solid_capstyle="butt")
        ax.text(k, 44, st + "\n" + t, ha="center", va="bottom", fontsize=9.5, color=S.INK if k < 2 else S.SOFT, linespacing=0.95)
    ax.set_ylim(-42, 64)
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["WT", "Lo", "Hi"], fontsize=S.SMALL + 1)
    ax.tick_params(axis="x", length=0); ax.set_xlim(-0.6, 2.6); ax.set_yticks([-40, -20, 0, 20, 40])
    style_ax(ax)
    ax.set_ylabel("Old place − never-used\n(% of first 10 runs)", fontsize=S.SMALL + 1)
    S.save(fig, os.path.join(OUT, "B_neverused.png"))
    print("B_neverused n: %s" % {NAME[g]: len(v) for g, v in vals.items()})


def b_predicts():
    pg = V.page(pdf("06_cue_against_place.pdf"))
    ps = V.paths(pg, (170, 400, 330, 565))
    xa, ya = V.Axis(209.1, 20, 302.7, 60), V.Axis(561.7, 0, 407.5, 40)
    W, H = 2.4, 2.7
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.5, 0.28, 1.84, 1.92)
    for p in ps:
        if p["type"] == "s" and V.near(p["stroke"], (0.04, 0.04, 0.04), 0.06) and p["rect"].width > 20:
            q = V.polyline(p)
            ax.plot(xa(q[:, 0]), ya(q[:, 1]), c=S.INK, lw=1.5, zorder=2)
    n = 0
    for m in V.markers(ps, maxsize=8.5):
        g = group_of(m["fill"])
        if g in (BLUE, GREEN, RED):
            n += 1
            _dot(ax, xa(m["x"]), ya(m["y"]), g, m["shape"], s=28)
    ax.text(0.03, 0.99, "ρ +0.62, P < 0.001 (n 30)\nWT only ρ +0.46, P 0.049\ngroup in model: P 0.018", transform=ax.transAxes,
            ha="left", va="top", fontsize=9.5, color=S.INK, linespacing=1.1)
    ax.set_xlim(5, 65); ax.set_ylim(0, 41)
    ax.set_xticks([20, 40, 60]); ax.set_yticks([0, 10, 20, 30, 40])
    style_ax(ax)
    ax.set_xlabel("Old-place share, cued (%)", fontsize=S.SMALL + 1)
    ax.set_ylabel("Rewards, hidden phase 10", fontsize=S.SMALL + 1)
    S.save(fig, os.path.join(OUT, "B_predicts.png"))
    print("B_predicts n %d" % n)


if __name__ == "__main__":
    import sys
    want = sys.argv[1:] or ["place", "former", "speed", "zones"]
    if "place" in want:
        b_oldplace(); b_neverused(); b_predicts()


# ================================================================================================= page 13
FORMER = {"hidden": dict(clip=(60, 200, 380, 420), x=V.Axis(174.3, 7, 348.0, 10), y=V.Axis(336.0, 0, 216.7, 200),
                         t1="slope per phase: WT +25.3, Lo +28.8, Hi +9.6", t2="group \u00d7 phase, Hi vs WT: P 0.003"),
          "cued": dict(clip=(60, 470, 380, 690), x=V.Axis(142.0, 7, 349.0, 10), y=V.Axis(646.0, 0, 504.0, 200),
                       t1="slope per phase: WT +18.6, Lo +18.6, Hi +15.0", t2="group \u00d7 phase, Hi vs WT: P 0.198")}


def b_former(which):
    cfg = FORMER[which]
    pg = V.page(pdf("13_the_set_to_rule_out.pdf"))
    ps = V.paths(pg, cfg["clip"])
    R = V.Render(pg, cfg["clip"], z=8)
    W, H = 3.6, 2.9
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.62, 0.42, 2.9, 1.95)
    sizes = sorted({round(m["w"], 1) for m in V.markers(ps, maxsize=9.0) if group_of(m["fill"]) in (BLUE, GREEN, RED)})
    cut = (sizes[0] + sizes[-1]) / 2                       # each mouse's dot is the small size, the group mean the large one
    for m in V.markers(ps, maxsize=cut):
        g = group_of(m["fill"])
        if g in (BLUE, GREEN, RED):
            ax.scatter([cfg["x"](m["x"])], [cfg["y"](m["y"])], s=9, color=FILLC[g], edgecolor="none", alpha=0.75, zorder=2)
    for p in ps:
        g = group_of(p["stroke"])
        if p["type"] == "s" and g in (BLUE, GREEN, RED) and p["width"] > 1.5:
            q = V.polyline(p)
            ax.plot(cfg["x"](q[:, 0]), cfg["y"](q[:, 1]), c=COL[g], lw=2.2, zorder=3)
    for m in V.markers(ps, maxsize=9.0, minsize=cut):
        g = group_of(m["fill"])
        if g in (BLUE, GREEN, RED):
            lo, hi = R.whisker(m["x"], m["y"], g, tol=60, gap=7, half=0.3, vertical=True)
            x = cfg["x"](m["x"])
            ax.plot([x, x], [cfg["y"](lo), cfg["y"](hi)], c=COL[g], lw=1.2, zorder=3)
            ax.scatter([x], [cfg["y"](m["y"])], s=34, color=FILLC[g], edgecolor="white", lw=0.7, zorder=4)
    ax.set_xlim(6.7, 10.35); ax.set_ylim(-5, 205 if which == "hidden" else 170)
    ax.set_xticks([7, 8, 9, 10]); ax.set_yticks([0, 50, 100, 150])
    style_ax(ax)
    ax.set_xlabel("Phase", fontsize=S.NOTE, labelpad=1)
    ax.set_ylabel("Pause at former goals (s)", fontsize=S.SMALL + 1)
    top = ax.secondary_xaxis("top")
    top.set_xticks([7, 8, 9, 10], ["0", "1", "2", "3"]); top.tick_params(labelsize=S.SMALL, length=0, pad=1, colors=S.SOFT)
    top.spines["top"].set_visible(False)
    S.text_at(fig, 0.8, 0.2, "former goals", fontsize=9.5, color=S.SOFT, va="center", ha="right")
    ax.text(0.03, 0.97, cfg["t1"] + "\n" + cfg["t2"], transform=ax.transAxes, ha="left", va="top", fontsize=9.5, linespacing=1.15,
            fontweight="normal")
    S.text_at(fig, 0.82 + 1.35, 0.0, "Goal hidden" if which == "hidden" else "Goal cued", ha="center", fontsize=S.NOTE,
              fontweight="bold", color=S.GREEN)
    S.save(fig, os.path.join(OUT, "B_former_%s.png" % which))
    print("B_former_%s" % which)


if __name__ == "__main__":
    import sys
    if "former" in (sys.argv[1:] or ["former"]):
        b_former("hidden"); b_former("cued")


# ================================================================================================= page 10 c
def b_speed():
    pg = V.page(pdf("10_arriving_at_the_goal.pdf"))
    ya = V.Axis(538.6, 0, 453.9, 25)
    panels = [((48, 160), V.Axis(111.9, 0, 130.3, 1), "Hidden, trained\nlocation (phase 7)", "P 0.176"),
              ((160, 268), V.Axis(219.6, 0, 237.8, 1), "Hidden, last\nrotation (phase 10)", "P < 0.001"),
              ((268, 380), V.Axis(326.9, 0, 345.3, 1), "Cued, last\nrotation (phase 10)", "P 0.176")]
    W, H = 6.9, 3.1
    fig = S.figure(W, H)
    for k, ((x0, x1), xa, title, pv) in enumerate(panels):
        ps = V.paths(pg, (x0, 440, x1, 545))
        ax = S.ax_at(fig, 0.62 + k * 2.12, 0.75, 1.88, 1.85)
        ax.axvspan(0, 1.2, color=NOVEL, lw=0, zorder=0)
        for g in (GREEN, BLUE, RED):
            for p in ps:
                if p["type"] == "f" and V.near(p["fill"], g, 0.06) and p["rect"].width > 8:
                    q = p["pts"]
                    ax.add_patch(Polygon(np.column_stack([xa(q[:, 0]), ya(q[:, 1])]), closed=True, fc=FILLC[g], ec=COL[g], lw=0.6,
                                         alpha=0.75 if g != BLUE else 0.85, zorder=2 if g != RED else 3))
        ax.set_xlim(-2.1, 2.6); ax.set_ylim(0, 27)
        ax.set_xticks([-2, -1, 0, 1, 2]); ax.set_yticks([0, 10, 20])
        if k:
            ax.set_yticklabels([])
        style_ax(ax)
        ax.set_title(title, fontsize=S.SMALL + 1, fontweight="bold", pad=14, linespacing=1.0)
        ax.text(0.6, 27.3, "1.2 s to earn it", ha="center", va="bottom", fontsize=9, color=S.SOFT, clip_on=False)
        ax.text(-2.0, 1.5, "reward window,\nHi vs WT: " + pv, ha="left", va="bottom", fontsize=9.5, linespacing=1.05,
                fontweight="bold" if "<" in pv else "normal")
        if k == 1:
            ax.set_xlabel("Time from goal entry (s)", fontsize=S.NOTE)
    fig.axes[0].set_ylabel("Speed (cm/s)", fontsize=S.NOTE)
    S.save(fig, os.path.join(OUT, "B_speed.png"))
    print("B_speed")


if __name__ == "__main__":
    import sys
    if "speed" in (sys.argv[1:] or ["speed"]):
        b_speed()


# ================================================================================================= page 17
KO_NAMES = [(3.9, "M8"), (5.2, "M1"), (6.0, "M30"), (8.8, "M33"), (9.5, "M10"), (20.2, "M28"), (22.0, "M29"), (24.1, "M7"),
            (24.6, "M3"), (27.6, "M5"), (28.4, "M34")]                  # each KO mouse's % KO, as labelled on the source


def _groups_panel(clip, ya, cats, means, ylim, yt, ylabel, brackets_, out, line=None, W=2.6, H=2.5):
    """dots per group (jitter kept) and the group mean +- SE (the source's black bars, read from its render)."""
    pg = V.page(pdf("17_last_rotation_zones.pdf"))
    ps = V.paths(pg, clip)
    R = V.Render(pg, clip, z=8)
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.62, 0.3, W - 0.72, H - 0.75)
    for m in V.markers(ps, maxsize=5.5):
        g = group_of(m["fill"])
        if g in cats:
            k = [BLUE, GREEN, RED].index(g)
            ied = m["shape"] == "D"
            ax.scatter([k - 0.12 + (m["x"] - cats[g][0]) / 30.0], [ya(m["y"])], s=24 if not ied else 26, marker="D" if ied else "o",
                       color=FILLC[g], edgecolor=S.INK if ied else "white", lw=0.7 if ied else 0.5, zorder=3)
    for k, g in enumerate([BLUE, GREEN, RED]):
        mx = cats[g][1]
        if means is not None:
            mv = means[k]
            y_pt = ya.p0 + (mv - ya.v0) * (ya.p1 - ya.p0) / (ya.v1 - ya.v0)
        else:                                                   # no printed mean: the bar's own centre (mean +- SE is symmetric)
            col = R.match((0.04, 0.04, 0.04), 70)[:, R.px(mx, 0)[0]]
            rows = np.where(col)[0]
            runs = np.split(rows, np.where(np.diff(rows) > 4)[0] + 1)
            run = max(runs[:-1] if len(runs) > 1 else runs, key=len)     # the error bar (the last run is the x axis)
            y_pt = R.pt(0, (run.min() + run.max()) / 2)[1]
            mv = float(ya(y_pt))
        lo, hi = R.whisker(mx, y_pt, (0.04, 0.04, 0.04), tol=70, gap=4, half=0.3, vertical=True)
        ax.errorbar([k + 0.28], [mv], yerr=[[abs(mv - ya(hi))], [abs(ya(lo) - mv)]], fmt="none", ecolor=S.INK, elinewidth=1.3, capsize=3,
                    capthick=1.3, zorder=4)
        ax.plot([k + 0.18, k + 0.38], [mv, mv], c=S.INK, lw=1.8, zorder=4)
    if line:
        ax.axhline(line[0], c=S.SOFT, lw=0.9, ls=(0, (4, 2)), zorder=1)
        ax.text(2.55, line[0] + (ylim[1] - ylim[0]) * 0.015, line[1], ha="right", va="bottom", fontsize=9, color=S.SOFT, linespacing=1.0)
    for (a, b, y, t) in brackets_:
        bracket(ax, a, b, y, t, h=(ylim[1] - ylim[0]) * 0.02, fs=9.5)
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["WT", "Lo KO", "Hi KO"], fontsize=S.SMALL + 1)
    ax.tick_params(axis="x", length=0); ax.set_xlim(-0.5, 2.6)
    ax.set_ylim(*ylim); ax.set_yticks(yt)
    style_ax(ax)
    ax.set_ylabel(ylabel, fontsize=S.SMALL + 1)
    S.save(fig, os.path.join(OUT, out))
    print(out)


def b_stay():
    _groups_panel((264, 181, 416, 300), V.Axis(296.1, 0, 199.6, 2.5), {BLUE: (304.0, 316.0), GREEN: (340.6, 352.9), RED: (376.3, 389.4)},
                  [1.16, 1.07, 0.76], (0, 3.0), [0, 0.5, 1.0, 1.5, 2.0, 2.5], "Time per entry (s)",
                  [(0, 2, 2.75, "Hi vs WT: P 0.04"), (1, 2, 2.45, "Lo vs Hi: P 0.13")], "B_stay.png",
                  line=(1.2, "1.2 s pause\nneeded for a reward"))


def b_entries():
    _groups_panel((418, 171, 572, 300), V.Axis(291.0, 0, 209.9, 100), {BLUE: (459.7, 473.4), GREEN: (497.7, 511.4), RED: (537.7, 549.7)},
                  [48.7, 32.4, 43.5], (0, 150), [0, 40, 80, 120], "Entries into current goal",
                  [(0, 2, 138, "Hi vs WT: P 0.77"), (1, 2, 124, "Lo vs Hi: P 0.43")], "B_entries.png")


def _ko_panel(clip, xa, ya, ylim, yt, ylabel, stats, out, W=4.35, H=2.5):
    pg = V.page(pdf("17_last_rotation_zones.pdf"))
    ps = V.paths(pg, clip)
    fig = S.figure(W, H)
    ax = S.ax_at(fig, 0.62, 0.3, W - 0.72, H - 0.75)
    ax.axvline(15, c=S.FAINT, lw=0.9, zorder=0)
    for p in ps:
        if p["type"] == "f" and p["fill"] is not None and V.near(p["fill"], (0.73, 0.72, 0.70), 0.06) and p["rect"].width > 30:
            q = p["pts"]
            ax.add_patch(Polygon(np.column_stack([xa(q[:, 0]), ya(q[:, 1])]), closed=True, fc="#E4E7EC", ec="none", zorder=1))
        if p["type"] == "s" and V.near(p["stroke"], (0.04, 0.04, 0.04), 0.06) and p["rect"].width > 30:
            q = V.polyline(p)
            ax.plot(xa(q[:, 0]), ya(q[:, 1]), c=S.INK, lw=1.6, zorder=2)
    for m in V.markers(ps, maxsize=8.5):
        g = group_of(m["fill"])
        if g is None:
            continue
        x, y = float(xa(m["x"])), float(ya(m["y"]))
        if g == BLUE and m["w"] > 5:                            # the WT mean, a bar left of the WT dots
            ax.plot([-1.0, -1.0], [float(ya(m["y"] + m["h"] / 2)), float(ya(m["y"] - m["h"] / 2))], c=S.PT_CTL, lw=5, solid_capstyle="butt", zorder=3)
            continue
        ied = m["shape"] == "D"
        ax.scatter([x], [y], s=34 if g != BLUE else 14, marker="D" if ied else "o", color=FILLC[g], edgecolor=S.INK if ied else "white",
                   lw=0.7 if ied else 0.4, zorder=3)
        if g != BLUE:
            nm = min(KO_NAMES, key=lambda t: abs(t[0] - x))[1]
            ax.text(x + 0.5, y + (ylim[1] - ylim[0]) * 0.02, nm, fontsize=8.5, color=S.SOFT, ha="left", va="bottom")
    ax.text(0.98, 0.98, stats, transform=ax.transAxes, ha="right", va="top", fontsize=9.5, linespacing=1.12)
    ax.set_xlim(-2.2, 31); ax.set_ylim(*ylim)
    ax.set_xticks([0, 10, 20, 30]); ax.set_yticks(yt)
    style_ax(ax)
    ax.set_xlabel("% granule cells KO (WT at 0)", fontsize=S.SMALL + 1)
    ax.set_ylabel(ylabel, fontsize=S.SMALL + 1)
    S.save(fig, os.path.join(OUT, out))
    print(out)


def b_prev_ko():
    _ko_panel((60, 350, 300, 480), V.Axis(71.8, 0, 279.4, 30), V.Axis(466.8, 0, 361.6, 4), (-0.3, 4.2), [0, 1, 2, 3, 4],
              "Time in previous goal\n(% of session)",
              "Pearson r +0.53, P 0.09\nSpearman ρ +0.62, P 0.04\nIED+ vs IED−: P 0.04", "B_prev_ko.png")


def b_rpe_ko():
    _ko_panel((300, 350, 572, 480), V.Axis(340.6, 0, 562.9, 30), V.Axis(468.7, 0, 359.6, 0.7), (-0.02, 0.75),
              [0, 0.2, 0.4, 0.6], "Rewards per entry",
              "Pearson r −0.75, P 0.01\nSpearman ρ −0.73, P 0.01\nIED+ vs IED−: P 0.07", "B_rpe_ko.png")


if __name__ == "__main__":
    import sys
    if "zones" in (sys.argv[1:] or ["zones"]):
        b_stay(); b_entries(); b_prev_ko(); b_rpe_ko()
