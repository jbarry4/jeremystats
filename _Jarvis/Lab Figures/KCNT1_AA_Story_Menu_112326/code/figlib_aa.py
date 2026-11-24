"""House style for the KCNT1 active-avoidance story menu (2026-11-23), adapted from the DS story menu's figlib.

Pages are US letter, portrait. Mice: WT gray, Het orange, Hom purple. Shape: circle = young (under 18 weeks),
square = old. A black ring = a flagged mouse (461/462 not naive, 457 Lab Ops note, virus-injected within 7 days of AA).
"""
import json
import os
import pickle
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Wedge, Circle, FancyArrowPatch  # noqa: E402
from scipy import stats as st  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({
    "font.family": "Arial", "font.size": 7, "axes.titlesize": 7.5, "axes.labelsize": 7, "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5, "legend.fontsize": 6.5, "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5,
    "ytick.major.size": 2.5, "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    "pdf.fonttype": 42, "ps.fonttype": 42, "lines.linewidth": 1.0,
})
INK = "#1d2433"
SOFT = "#5a6273"
FAINT = "#9aa1ad"
GRID = "#e6e8ec"
KICK = "#1f6f8b"
GCOL = {"WT": "#8c8c8c", "Het": "#e08a2c", "Hom": "#7b2d8e"}
GWORD = {"WT": "WT", "Het": "Het", "Hom": "Hom"}
ZONE = "#d62728"
ROTC = {"fast": "#2b8cbe", "medium": "#7fb8d6", "slow": "#d9a441"}

A = pickle.load(open(os.path.join(HERE, "analysis.pkl"), "rb"))
B = pickle.load(open(os.path.join(HERE, "speed.pkl"), "rb"))   # a4_speed.py: everything at one floor speed
MICE = A["MICE"]
REF = B["REF"]
VALS_RAW, RES_RAW = A["VALS"], A["RES"]
VALS, RES = B["VALS_ADJ"], B["RES_ADJ"]      # the menu's default: values and tests at one floor speed
FLAG = {m for m, d in MICE.items() if d["not_naive"] or m == "457" or d["injected_7d"]}
SPEED_NOTE = "every value at one floor speed (%.1f deg/s; page 3)" % REF


def _speed_specific(contrast):
    return contrast == "rot_corr_all" or "_adj_rot" in contrast or contrast.endswith(("_slow", "_medium", "_fast"))


def geno(m):
    return MICE[m]["yh"]


def young(m):
    return MICE[m]["age_group"] == "young"


# ------------------------------------------------------------------ text and layout
def wrap(text, width_in, size_pt):
    per_line = max(int(width_in * 72.0 / (size_pt * 0.50)), 8)
    out = []
    for para in str(text).split("\n"):
        out.append(textwrap.fill(para, per_line) if para.strip() else "")
    return "\n".join(out)


def put(fig, x, y, text, width_in, size=7.0, color=INK, weight="normal", va="top", ha="left", style="normal", line=1.25):
    W, H = fig.get_size_inches()
    s = wrap(text, width_in, size)
    fig.text(x / W, 1 - y / H, s, fontsize=size, color=color, weight=weight, va=va, ha=ha, style=style, linespacing=line)
    n = s.count("\n") + 1
    return n * size * line / 72.0


def axes_in(fig, x, y, w, h, **kw):
    W, H = fig.get_size_inches()
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H], **kw)


def letter(fig, x, y, s, title="", width=5.3):
    """Panel letter and its heading (a finding, in words). Long headings wrap; extra lines go upward from y."""
    W, H = fig.get_size_inches()
    n = 1
    if title:
        per_line = max(int((width - 0.16) * 72.0 / (7.5 * 0.50)), 20)
        text = textwrap.fill(title, per_line)
        n = text.count("\n") + 1
        fig.text((x + 0.16) / W, 1 - y / H, text, fontsize=7.5, weight="bold", va="bottom",
                 ha="left", color=INK, linespacing=1.15)
    fig.text(x / W, 1 - (y - (n - 1) * 7.5 * 1.15 * 1.2 / 72.0) / H, s, fontsize=8.5, weight="bold", va="bottom", ha="left",
             color=INK)


# ------------------------------------------------------------------ significance marks
def stars(p):
    if p is None or not np.isfinite(p) or p >= 0.05:
        return ""
    return "***" if p < 0.001 else ("**" if p < 0.01 else "*")


def brackets(ax, items, top, color=INK, fs=7.0, lw=0.6, pad=0.06, step=0.1, gap=0.12):
    """Significance brackets: items are (x1, x2, p) or (x1, x2, p, feet), feet = ((a0, a1), (b0, b1)) bars under each
    end when an end stands for a pair of columns. Only P < 0.05 is drawn (* < 0.05, ** < 0.01, *** < 0.001). Brackets
    sit above `top` (data units), stack only where they overlap, and the y limit grows to hold them."""
    sig = [it for it in items if it[2] is not None and np.isfinite(it[2]) and it[2] < 0.05]
    if not sig:
        return 0
    lo, hi = ax.get_ylim()
    span = hi - lo
    levels, placed = [], []
    for it in sorted(sig, key=lambda it: (abs(it[1] - it[0]), min(it[0], it[1]))):
        x1, x2 = sorted(it[:2])
        lv = 0
        while lv < len(levels) and any(not (x2 + gap < a or x1 - gap > b) for a, b in levels[lv]):
            lv += 1
        if lv == len(levels):
            levels.append([])
        levels[lv].append((x1, x2))
        placed.append((x1, x2, it[2], it[3] if len(it) > 3 else None, lv))
    base = top + pad * span
    tick = 0.03 * span
    for x1, x2, p, feet, lv in placed:
        yb = base + lv * step * span
        ax.plot([x1, x1, x2, x2], [yb - tick, yb, yb, yb - tick], color=color, lw=lw, solid_capstyle="butt",
                clip_on=False, zorder=7)
        if feet:
            for a0, a1 in feet:
                ax.plot([a0, a1], [yb - tick, yb - tick], color=color, lw=lw, solid_capstyle="butt", clip_on=False, zorder=7)
        ax.text((x1 + x2) / 2, yb + 0.004 * span, stars(p), ha="center", va="center", fontsize=fs, color=color, zorder=7,
                weight="bold")
    ax.set_ylim(lo, max(hi, base + (len(levels) - 1) * step * span + 0.07 * span))
    return len(levels)


def pstars(p):
    """'P 0.003 **' for titles and tables."""
    s = stars(p)
    return pstr(p) + (" " + s if s else "")


FOOT = "KCNT1 active avoidance story menu · exploratory, P values uncorrected · 2026-11-23"


def page(title, kicker, number=None):
    fig = plt.figure(figsize=(8.5, 11))
    put(fig, 0.5, 0.42, kicker, 7.5, size=7, color=KICK, weight="bold")
    h = put(fig, 0.5, 0.62, title, 7.5, size=13, weight="bold")
    if number is not None:
        fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "%s" % number, fontsize=6.5, color=FAINT, ha="right", va="bottom")
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, FOOT, fontsize=6.5, color=FAINT, ha="left", va="bottom")
    return fig, 0.62 + h + 0.08


def textcol(fig, y, blocks, x=5.95, w=2.05):
    for head, body in blocks:
        if head:
            y += put(fig, x, y, head, w, size=7.2, weight="bold") + 0.03
        y += put(fig, x, y, body, w, size=6.6, color=INK) + 0.14
    return y


def pstr(p):
    if p is None or not np.isfinite(p):
        return "P n/a"
    if p < 0.0001:
        return "P %.1e" % p
    if p < 0.001:
        return "P %.4f" % p
    if p < 0.01:
        return "P %.3f" % p
    return "P %s" % ("%.2g" % p)


def res(mid, contrast, raw=False):
    """A result at one floor speed (default) or before the speed adjustment (raw=True). Speed-specific contrasts
    (correlation with speed, speed bands, speed in the model) only exist raw."""
    T = RES_RAW if (raw or _speed_specific(contrast)) else RES
    s = T[(T.id == mid) & (T.contrast == contrast)]
    if s.empty:
        return dict(p=np.nan, test="", effect=np.nan, mean_a=np.nan, mean_b=np.nan)
    return s.iloc[0].to_dict()


def P(mid, contrast, raw=False):
    return res(mid, contrast, raw)["p"]


MM_MAP = {"geno_x_session": "geno_x_session_speed", "geno_x_day": "geno_x_day_speed", "geno_adj_rot_age": "geno_speed"}


def mm(measure, model, term_part, raw=False):
    """Mixed-model term P: with floor speed (and speed x session) in the model by default."""
    M = A["MM"] if raw else B["MM_ADJ"]
    model = model if raw else MM_MAP.get(model, model)
    s = M[(M.measure == measure) & (M.model == model) & (M.term.str.contains(term_part, regex=False))]
    return (float(s.p.iloc[0]), float(s.coef.iloc[0])) if len(s) else (np.nan, np.nan)


def circ_p(group):
    """Preferred-direction difference: permutation with labels swapped only inside a floor-speed band."""
    C = B["CIRC_ADJ"]
    s = C[C.group == group]
    return float(s.p_direction.iloc[0]) if len(s) else np.nan


# ------------------------------------------------------------------ mice on plots
def marker_of(m):
    return "o" if young(m) else "s"


def scatter_mouse(ax, x, y, m, size=18, z=4, alpha=1.0):
    ax.scatter([x], [y], s=size, marker=marker_of(m), color=GCOL[geno(m)], edgecolor=INK if m in FLAG else "white",
               linewidth=0.8 if m in FLAG else 0.5, zorder=z, alpha=alpha)


def legend_mice(fig, x, y, extra=True, speed=True):
    W, H = fig.get_size_inches()
    if speed:
        fig.text(7.95 / W, 1 - (y + 0.1) / H, SPEED_NOTE, fontsize=6.3, color=KICK, ha="right", va="center", style="italic")
    hs = [Line2D([], [], ls="", marker="o", ms=4.5, mfc=GCOL[g], mec="white", label=g) for g in ("WT", "Het", "Hom")]
    if extra:
        hs += [Line2D([], [], ls="", marker="o", ms=4.2, mfc="white", mec=SOFT, label="young (<18 wk)"),
               Line2D([], [], ls="", marker="s", ms=4.0, mfc="white", mec=SOFT, label="old (19-46 wk)"),
               Line2D([], [], ls="", marker="o", ms=4.5, mfc=FAINT, mec=INK, mew=0.9, label="flagged mouse")]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(x / W, 1 - y / H), ncol=len(hs), frameon=False, fontsize=6.3,
               handletextpad=0.3, columnspacing=1.0)


def robust_limits(values, k=4.0):
    v = np.array([x for x in values.values() if np.isfinite(x)])
    if v.size < 6:
        return None, None, {}
    q1, q3 = np.percentile(v, [25, 75])
    iqr = q3 - q1
    if iqr <= 0:
        return None, None, {}
    lo_f, hi_f = q1 - k * iqr, q3 + k * iqr
    off = {l: x for l, x in values.items() if np.isfinite(x) and (x < lo_f or x > hi_f)}
    if len(off) != 1:
        return None, None, {}
    inside = v[(v >= lo_f) & (v <= hi_f)]
    pad = 0.12 * float(np.ptp(inside)) if inside.size > 1 else 1.0
    return float(inside.min() - pad), float(inside.max() + pad), off


def dots(ax, values, groups, order, xlabels=None, ylabel="", jitter=0.16, names="extremes", seed=3):
    """One dot per mouse at its group, median line. names: 'all', 'extremes' (top/bottom 2 per group) or None.
    Returns the top of what is drawn (data units), for significance brackets."""
    rng = np.random.RandomState(seed)
    lo, hi, off = robust_limits(values)
    allv = np.array([v for l, v in values.items() if np.isfinite(v) and l not in off and groups.get(l) in order])
    top = float(allv.max()) if allv.size else 0.0
    if any(values[m] > hi for m in off if groups.get(m) in order):
        top = hi
    for k, g in enumerate(order):
        ms = [m for m in values if groups.get(m) == g and np.isfinite(values[m])]
        vs = np.array([values[m] for m in ms])
        if vs.size:
            ax.plot([k - 0.3, k + 0.3], [np.median(vs)] * 2, color=INK, lw=1.2, zorder=3, solid_capstyle="butt")
        xs = k - 0.05 + (rng.rand(len(ms)) - 0.5) * 2 * jitter
        for x, m, v in zip(xs, ms, vs):
            if m in off:
                y = hi if v > hi else lo
                ax.scatter([x], [y], marker="^" if v > hi else "v", s=24, color=GCOL[geno(m)], edgecolor="white", zorder=6, clip_on=False)
                ax.text(x + 0.08, y, "%s %.3g" % (m, v), fontsize=4.6, color=SOFT, va="center")
            else:
                scatter_mouse(ax, x, v, m)
        if names and vs.size:
            order_idx = np.argsort(vs)
            pick = order_idx if names == "all" else np.r_[order_idx[:2], order_idx[-2:]]
            for i in set(pick.tolist()):
                if ms[i] in off:
                    continue
                ax.text(xs[i] + 0.07, vs[i], ms[i], fontsize=4.4, color=SOFT, va="center", zorder=5)
    if off:
        ax.set_ylim(lo, hi)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(xlabels or order)
    ax.set_xlim(-0.6, len(order) - 0.4)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", length=0)
    return top


GENO_PAIRS = (("Het_vs_WT", 0, 1), ("Hom_vs_WT", 0, 2), ("Hom_vs_Het", 1, 2))


def geno_dots(ax, mid, ylabel, title=None, contrasts=(("Het_vs_WT", "Het vs WT"), ("Hom_vs_WT", "Hom vs WT")), names="extremes",
              values=None, stack=True, marks=True, raw=False):
    """WT / Het / Hom dots with brackets for every pairwise P < 0.05; the title lists the exact P values. Values and
    tests at one floor speed unless raw=True."""
    v = values if values is not None else (VALS_RAW if raw else VALS)[mid]
    top = dots(ax, v, {m: geno(m) for m in v}, ["WT", "Het", "Hom"], ylabel=ylabel, names=names)
    cons = list(contrasts)
    if mid and marks:
        listed = {c for c, _w in cons}
        if "Hom_vs_Het" not in listed and P(mid, "Hom_vs_Het", raw) < 0.05:
            cons.append(("Hom_vs_Het", "Hom vs Het"))
    sep = "\n" if stack else " · "
    bits = sep.join("%s %s" % (w, pstr(P(mid, c, raw))) for c, w in cons) if mid else ""
    if title:
        ax.set_title("%s\n%s" % (title, bits) if bits else title, fontsize=6.0, loc="left", color=INK, linespacing=1.15)
    elif bits:
        ax.set_title(bits, fontsize=5.9, loc="left", color=SOFT, linespacing=1.15)
    if mid and marks:
        brackets(ax, [(a, b, P(mid, c, raw)) for c, a, b in GENO_PAIRS], top)
    return ax


def grid(fig, x, y, ncols, nrows, w, h, gx=0.55, gy=0.75):
    """Axes in a grid, positions in inches from the page's top-left; returns a flat list (row by row)."""
    out = []
    for r in range(nrows):
        for c in range(ncols):
            out.append(axes_in(fig, x + c * (w + gx), y + r * (h + gy), w, h))
    return out


def theil(x, y, n_boot=1000, seed=0):
    x, y = np.asarray(x, float), np.asarray(y, float)
    sl, ic, _lo, _hi = st.theilslopes(y, x)
    xx = np.linspace(x.min(), x.max(), 50)
    rng = np.random.RandomState(seed)
    boots = []
    for _ in range(n_boot):
        k = rng.randint(0, x.size, x.size)
        if np.ptp(x[k]) == 0:
            continue
        s, i, _a, _b = st.theilslopes(y[k], x[k])
        boots.append(s * xx + i)
    boots = np.array(boots)
    return xx, sl * xx + ic, np.percentile(boots, 2.5, axis=0), np.percentile(boots, 97.5, axis=0)


# ------------------------------------------------------------------ arena drawing
R_ARENA = 41.0
SECTOR = (45.0, 60.0)


def arena(ax, r=R_ARENA, zone=True, lw=0.6, ring_color="#b8bcc4"):
    ax.add_patch(Circle((0, 0), r, fill=False, ec=ring_color, lw=lw, zorder=1))
    if zone:
        c, w = SECTOR
        ax.add_patch(Wedge((0, 0), r, c - w / 2, c + w / 2, color=ZONE, alpha=0.13, lw=0, zorder=0))
    ax.set_xlim(-r * 1.12, r * 1.12)
    ax.set_ylim(-r * 1.12, r * 1.12)
    ax.set_aspect("equal")
    ax.axis("off")


def rot_arrow(ax, r=R_ARENA * 1.08, a0=150, a1=200, color=INK, lw=0.8):
    t = np.radians(np.linspace(a0, a1, 40))
    ax.plot(r * np.cos(t), r * np.sin(t), color=color, lw=lw)
    ax.add_patch(FancyArrowPatch((r * np.cos(t[-3]), r * np.sin(t[-3])), (r * np.cos(t[-1]), r * np.sin(t[-1])),
                                 arrowstyle="-|>", mutation_scale=6, color=color, lw=lw))


def occupancy_ring(ax, occ36, r0=R_ARENA * 1.02, r1=R_ARENA * 1.16, cmap="Greys", vmax=None):
    """occ36: share of time per 10-deg bin of the angle from the zone center (-180..180). Drawn in the room frame."""
    vmax = vmax or max(float(np.max(occ36)), 1e-6)
    cm = plt.get_cmap(cmap)
    for k, v in enumerate(occ36):
        a0 = -180 + 10 * k + SECTOR[0]
        ax.add_patch(Wedge((0, 0), r1, a0, a0 + 10, width=r1 - r0, color=cm(min(v / vmax, 1.0) * 0.9 + 0.05), lw=0))


def save(fig, out_dir, name):
    """PNG at 300 dpi; the PDF is vector, with the rasterized path tracks at 600 dpi (they were 100 dpi before)."""
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(os.path.join(out_dir, name + ".png"), dpi=300)
    fig.savefig(os.path.join(out_dir, name + ".pdf"), dpi=600)
    plt.close(fig)
