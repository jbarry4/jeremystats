"""The deck's own explanatory pictures, in the figures' style (Arial, the
PuOr pair, greys for the days). Each is saved as PNG with the boxes (in
millimetres from its top-left) that the deck's blue box lands on."""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                         # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, APP)
from backend import monolith as MO, joe                # noqa: E402

# Everything this writes goes to the git-ignored cache, not beside the code.
OUT = os.path.join(APP, "GUI_logs", ".cache", "joe_deck", "img")
os.makedirs(OUT, exist_ok=True)
MM = 1 / 25.4
C_UP, C_DOWN, C_P1, C_P4, C_NULL = "#E66101", "#5E3C99", "#8C8C8C", "#1A1A1A", "#D4D4D4"
# tab 8's lights since 2026-10-23: colour-blind safe, and a shape for each
# state (lit: a disc; a check that lit: a diamond; dark: a hollow ring)
LIT, CHECK_LIT, GREY = "#0072B2", "#D55E00", "#9A9A9A"
plt.rcParams.update({"font.family": "Arial", "font.size": 8, "axes.linewidth": 0.6, "svg.fonttype": "none",
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6})
BOXES = {}


def save(fig, name, W, H, boxes):
    p = os.path.join(OUT, name + ".png")
    fig.savefig(p, dpi=400)
    plt.close(fig)
    BOXES[name] = {"file": p, "w_mm": W, "h_mm": H, "boxes": boxes}


def ax_mm(fig, x, y, w, h, W, H, **kw):
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H], **kw)


# 1. Coherence: in step, and out of step ---------------------------------
def coherence_demo():
    W, H = 150.0, 84.0
    fig = plt.figure(figsize=(W * MM, H * MM))
    rng = np.random.default_rng(3)
    t = np.linspace(0, 0.25, 1000)
    f = 40.0
    for k, (title, lock) in enumerate((("In step: coherence near 1", True), ("Out of step: coherence near 0", False))):
        y0 = 6 + k * 40
        ax = ax_mm(fig, 8, y0 + 7, 136, 28, W, H)
        ph = 2 * np.pi * f * t
        a = np.sin(ph) + 0.18 * rng.standard_normal(t.size)
        # Out of step: its own frequency, wandering, so the two slide past each other.
        drift = 0.0 if lock else 2 * np.pi * 9.0 * t + np.cumsum(rng.standard_normal(t.size)) * 0.12
        b = np.sin(ph + 0.5 + drift) + 0.18 * rng.standard_normal(t.size)
        # Guides at region A's peaks: in step, B's peaks keep landing the
        # same distance from them (a fixed delay); out of step, they slide.
        for pk in (np.arange(10) + 0.25) / f:
            ax.plot([pk, pk], [-2.9, 2.9], color="#9A9A9A", lw=0.5, ls=(0, (1.5, 1.5)))
        ax.plot(t, a + 1.6, color="#1A1A1A", lw=0.8)
        ax.plot(t, b - 1.6, color=C_UP if lock else C_DOWN, lw=0.8)
        ax.text(-0.004, 1.6, "Region A", ha="right", va="center", fontsize=7)
        ax.text(-0.004, -1.6, "Region B", ha="right", va="center", fontsize=7)
        ax.set_xlim(-0.03, 0.25)
        ax.axis("off")
        fig.text(8 / W, 1 - (y0 + 1) / H, title, fontsize=9, fontweight="bold", va="top")
    save(fig, "coherence", W, H, {"instep": [2, 4, 148, 42], "outstep": [2, 44, 148, 82]})


# 2. A trial's windows ------------------------------------------------------
def timeline():
    W, H = 150.0, 83.0
    fig = plt.figure(figsize=(W * MM, H * MM))
    ax = ax_mm(fig, 6, 6, 138, 71, W, H)
    ax.set_xlim(-24, 23)
    ax.set_ylim(-2.6, 10)
    ax.axis("off")
    # the bar: baseline 20 s, cue 1, cue 2
    ax.add_patch(Rectangle((-20, 6.2), 20, 1.6, color="#E6E6E6"))
    ax.add_patch(Rectangle((-10, 6.2), 10, 1.6, color="#CFCFCF"))
    ax.add_patch(Rectangle((0, 6.2), 10, 1.6, color="#F4B37C"))
    ax.add_patch(Rectangle((10, 6.2), 10, 1.6, color="#B69BD0"))
    ax.text(-15, 8.3, "baseline (first 10 s)", ha="center", va="bottom", fontsize=7, color="#555555")
    ax.text(-5, 8.3, "baseline (last 10 s)", ha="center", va="bottom", fontsize=7, color="#555555")
    ax.text(5, 8.3, "cue 1 (10 s)", ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    ax.text(15, 8.3, "cue 2 (10 s)", ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    for x in (-20, -10, 0, 10, 20):
        ax.plot([x, x], [6.0, 6.2], color="#333333", lw=0.6)
    ax.text(0, 5.5, "cue 1 starts", ha="center", va="top", fontsize=6.5, color="#555555")

    def bracket(x0, x1, y, text, color):
        ax.plot([x0, x0, x1, x1], [y + 0.35, y, y, y + 0.35], color=color, lw=1.2)
        ax.text((x0 + x1) / 2, y - 0.35, text, ha="center", va="top", fontsize=7, color=color, fontweight="bold")
    # comparison 1: base20 vs cue1 + cue2
    bracket(-20, -0.4, 3.6, "20 s baseline", "#333333")
    bracket(0.4, 20, 3.6, "both cues (20 s)", C_UP)
    ax.text(-23.5, 3.25, "1", fontsize=10, fontweight="bold", va="center")
    # comparison 2: base10 vs cue1
    bracket(-10, -0.4, 1.0, "10 s baseline", "#333333")
    bracket(0.4, 10, 1.0, "cue 1", C_UP)
    ax.text(-23.5, 0.65, "2", fontsize=10, fontweight="bold", va="center")
    # comparison 5: cue 1 vs cue 2, whatever the sounds
    bracket(0.4, 9.6, -1.6, "cue 1", "#333333")
    bracket(10.4, 20, -1.6, "cue 2", C_UP)
    ax.text(-23.5, -1.95, "5", fontsize=10, fontweight="bold", va="center")
    # boxes in mm: x = 6 + (v + 24) / 47 * 138 ; y = 6 + (10 - v) / 12.6 * 71
    X = lambda v: 6 + (v + 24) / 47 * 138                # noqa: E731
    Y = lambda v: 6 + (10 - v) / 12.6 * 71               # noqa: E731
    save(fig, "timeline", W, H, {
        "baseline": [X(-21), Y(9.6), X(0), Y(5.8)], "cues": [X(0), Y(9.6), X(20.6), Y(5.8)],
        "cmp1": [X(-24), Y(4.3), X(21), Y(2.3)], "cmp2": [X(-24), Y(1.7), X(21), Y(-0.3)],
        "cmp5": [X(-24), Y(-0.9), X(21), Y(-2.9)]})


# 3. Tab 8's lights -----------------------------------------------------------
def lights(R):
    models = [m for m in R["models"]]
    res = {(r["model"], r["band"]): r for r in R["results"] if r["method"] == ("welch" if r["model"] == "m7" else "dickson")}
    W, H = 150.0, 8.0 + 6.4 * len(models) + 4.0
    fig = plt.figure(figsize=(W * MM, H * MM))
    ax = ax_mm(fig, 0, 0, W, H, W, H)
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    cx = {"theta": 112.0, "gamma": 134.0}
    ax.text(cx["theta"], 4.5, "theta", ha="center", va="center", fontsize=8, fontweight="bold")
    ax.text(cx["gamma"], 4.5, "gamma", ha="center", va="center", fontsize=8, fontweight="bold")
    boxes = {}
    for i, m in enumerate(models):
        y = 10.0 + 6.4 * i
        check = m.get("kind") == "check"
        if i and check and models[i - 1].get("kind") != "check":
            ax.plot([2, W - 2], [y - 3.2, y - 3.2], color="#BBBBBB", lw=0.5)
        ax.text(4, y, "%d" % m["no"], va="center", fontsize=7.5, fontweight="bold")
        ax.text(11, y, (m.get("title") or m["label"]) + ("   (check)" if check else ""), va="center", fontsize=7.5,
                color="#555555" if check else "#111111")
        for band in ("theta", "gamma"):
            r = res.get((m["id"], band))
            lit = bool(r and (r.get("gate") or {}).get("passed") and (r.get("mixed") or {}).get("ok"))
            if lit and check:
                ax.add_patch(plt.Polygon([(cx[band], y - 2.5), (cx[band] + 2.5, y), (cx[band], y + 2.5), (cx[band] - 2.5, y)],
                                         closed=True, color=CHECK_LIT))
            elif lit:
                ax.add_patch(plt.Circle((cx[band], y), 2.1, color=LIT))
            else:
                ax.add_patch(plt.Circle((cx[band], y), 1.8, fill=False, ec=GREY, lw=0.9))
            boxes["%s_%s" % (m["id"], band)] = [cx[band] - 4, y - 3.2, cx[band] + 4, y + 3.2]
        boxes["row_%s" % m["id"]] = [2, y - 3.2, W - 2, y + 3.2]
    save(fig, "lights", W, H, boxes)


# 4. Each rat, the change of the change -------------------------------------
def rats(R, mid, name):
    r = next(x for x in R["results"] if x["model"] == mid and x["band"] == "gamma" and x["method"] == "dickson")
    q = r["quick"]
    W, H = 120.0, 80.0
    fig = plt.figure(figsize=(W * MM, H * MM))
    ax = ax_mm(fig, 22, 8, 92, 58, W, H)
    vals = [q["per_rat"][k] for k in sorted(q["per_rat"], key=int)]
    names = sorted(q["per_rat"], key=int)
    xs = np.arange(len(vals))
    ax.axhline(0, color="#777777", lw=0.6, ls="--")
    for x, v in zip(xs, vals):
        ax.plot([x, x], [0, v], color=C_UP if v > 0 else C_DOWN, lw=1.4)
        ax.plot(x, v, "o", ms=6, color=C_UP if v > 0 else C_DOWN)
    ax.set_xticks(xs)
    ax.set_xticklabels(["rat %s" % n for n in names], fontsize=7)
    ax.set_ylabel("Cue − baseline, Precon4\nminus Precon1 (gamma coherence)", fontsize=7.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=7)
    lo, hi = min(vals + [0]), max(vals)
    ax.set_ylim(lo - 0.15 * (hi - lo), hi + 0.15 * (hi - lo))
    up = sum(v > 0 for v in vals)
    save(fig, name, W, H, {"dots": [20, 4, 116, 68]})
    return up, len(vals)


# 5. The four kinds of follow-up ------------------------------------------
def families():
    W, H = 150.0, 96.0
    fig = plt.figure(figsize=(W * MM, H * MM))
    rng = np.random.default_rng(7)
    t = np.linspace(0, 1, 600)
    boxes = {}
    cells = (("conduction", "Not just a shared signal", "PLI, imaginary coherence"),
             ("direction", "Which leads", "Granger, amplitude lag"),
             ("amplitude", "Bursts rise together", "amplitude cross-correlation"),
             ("pac", "Theta paces gamma", "phase–amplitude coupling"))
    for k, (key, title, sub) in enumerate(cells):
        cx0 = 4 + (k % 2) * 73
        cy0 = 4 + (k // 2) * 46
        fig.patches.append(FancyBboxPatch((cx0 / W, 1 - (cy0 + 42) / H), 69 / W, 42 / H, boxstyle="round,pad=0,rounding_size=0.012",
                                          transform=fig.transFigure, facecolor="#F4F4F4", edgecolor="#CCCCCC", lw=0.6, zorder=0))
        fig.text((cx0 + 3) / W, 1 - (cy0 + 3) / H, title, fontsize=8.5, fontweight="bold", va="top")
        fig.text((cx0 + 3) / W, 1 - (cy0 + 8.5) / H, sub, fontsize=6.5, color="#555555", va="top")
        ax = ax_mm(fig, cx0 + 4, cy0 + 14, 61, 25, W, H)
        ax.set_zorder(2)
        ax.patch.set_alpha(0)
        ax.axis("off")
        if key == "conduction":
            ph = 2 * np.pi * 6 * t
            ax.plot(t, np.sin(ph) + 1.3, color="#1A1A1A", lw=0.9)
            ax.plot(t, np.sin(ph - 0.9) - 1.3, color=C_UP, lw=0.9)
            for x in (0.0417, 0.2083, 0.375):
                ax.annotate("", xy=(x + 0.9 / (2 * np.pi * 6), -0.3), xytext=(x, 2.3),
                            arrowprops=dict(arrowstyle="->", color="#5E3C99", lw=0.8))
            ax.text(1.03, 0, "a steady\ndelay: real\ncoupling", fontsize=6.5, va="center")
            ax.set_xlim(0, 1.3)
        elif key == "direction":
            ph = 2 * np.pi * 4 * t
            env = np.exp(-((t - 0.3) / 0.06) ** 2)
            env2 = np.exp(-((t - 0.38) / 0.06) ** 2)
            ax.plot(t, env * np.sin(ph * 8) + 1.3, color="#1A1A1A", lw=0.7)
            ax.plot(t, env2 * np.sin(ph * 8) - 1.3, color=C_UP, lw=0.7)
            ax.annotate("", xy=(0.38, -0.2), xytext=(0.3, 0.3), arrowprops=dict(arrowstyle="->", color="#5E3C99", lw=1.0))
            ax.text(0.5, 0, "A first, then B:\nA leads", fontsize=6.5, va="center")
            ax.set_xlim(0, 1)
        elif key == "amplitude":
            env = 0.25 + np.abs(np.sin(2 * np.pi * 1.5 * t)) ** 3
            g = np.sin(2 * np.pi * 45 * t)
            ax.plot(t, env * g + 1.3, color="#1A1A1A", lw=0.5)
            ax.plot(t, (env + 0.08 * rng.standard_normal(t.size)) * np.sin(2 * np.pi * 45 * t + 1) - 1.3, color=C_UP, lw=0.5)
            ax.text(1.03, 0, "louder\ntogether", fontsize=6.5, va="center")
            ax.set_xlim(0, 1.3)
        else:
            th = np.sin(2 * np.pi * 7 * t)
            g = (0.15 + 0.85 * np.clip(th, 0, None) ** 2) * np.sin(2 * np.pi * 60 * t)
            ax.plot(t, th * 0.9 + 1.3, color="#1A1A1A", lw=0.8)
            ax.plot(t, g - 1.3, color=C_UP, lw=0.5)
            ax.text(1.03, 0, "gamma bursts\nat theta peaks", fontsize=6.5, va="center")
            ax.set_xlim(0, 1.3)
        ax.set_ylim(-2.6, 2.6)
        boxes[key] = [cx0 - 1, cy0 - 1, cx0 + 70, cy0 + 43]
    save(fig, "families", W, H, boxes)


if __name__ == "__main__":
    MO.configure(os.path.join(APP, "GUI_logs"))
    R = joe.result()
    coherence_demo()
    timeline()
    lights(R)
    u1 = rats(R, "m1", "rats_m1")
    u2 = rats(R, "m2", "rats_m2")
    families()
    BOXES["_rats_up"] = {"m1": u1, "m2": u2}
    with open(os.path.join(OUT, "boxes.json"), "w", encoding="utf-8") as fh:
        json.dump(BOXES, fh, indent=1)
    print("ok", sorted(BOXES), u1, u2)
