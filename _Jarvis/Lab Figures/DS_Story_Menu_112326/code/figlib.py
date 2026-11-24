"""House style and shared drawing for the DS story menu (2026-11-23, round 3).

Pages are US letter, portrait. Colors:
  mice   : control gray, IED- light magenta, IED+ dark magenta (the grant's palette); m7 is a diamond.
  events : DS blue, borderline transients (BT, the in-between class) purple, IED red (Jarvis's code).
  CSD    : sink blue, source red.

Rules this file enforces (asked for on 2026-11-23):
  - every mouse stays on the scale (no clipped dots with printed values); positive, skewed numbers go on a log axis
  - significance brackets are laid out after the axis limits are final, in points, so a star never touches a line
  - mouse names are placed where they overlap nothing (no stacks of names)
  - a correlation gets its fitted line and 95% band; line plots of means get their shaded band
  - on line plots significance is a bar along the axis (no stars)
  - depth is always the vertical axis, registered on each recording's own dentate spike (never the lab's layer labels)
"""
import json
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import transforms  # noqa: E402
import matplotlib.ticker  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.textpath import TextPath  # noqa: E402
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
LEADER = "#c3c8d0"
C_CTL = "#8c8c8c"
C_NEG = "#e7a3c9"
C_POS = "#a8326e"
C_LOW = "#f2b47e"
C_HIGH = "#c2571a"
GROUP_COLOR = {"CTL": C_CTL, "IED-": C_NEG, "IED+": C_POS, "low KO": C_LOW, "high KO": C_HIGH}
GROUP_WORD = {"CTL": "Control", "IED-": "PTEN IED\u2212", "IED+": "PTEN IED+", "low KO": "Low KO\n(4\u20135%)", "high KO": "High KO\n(19\u201328%)"}
C_DS = "#2f6db5"
C_DS1 = "#c2571a"
C_PDS = "#8e44ad"
C_IED = "#d62728"
C_FAR = "#b0b0b0"
KIND_COLOR = {"DS": C_DS, "TZ": C_PDS, "BT": C_PDS, "IED": C_IED, "far": C_FAR}
KIND_WORD = {"DS": "DS", "TZ": "BT", "BT": "BT", "IED": "IED", "far": "outside both"}

BATTERY = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
META = {m["lab"]: m for m in json.load(open(os.path.join(BATTERY, "data", "meta.json")))}
LABS = ["m2", "m21", "m22", "m26", "m59", "m60", "m61", "m8", "m33", "m1", "m7", "m13", "m28", "m3", "m5", "m34"]
_FONT = FontProperties(family="Arial")


def subgroup(lab):
    return META[lab]["subgroup"]


def ko(lab):
    return META[lab]["ko"]


def kogroup(lab):
    m = META[lab]
    if m["group"] == "CTL":
        return "CTL"
    return "low KO" if m["ko"] < 10 else "high KO"


def color_of(lab):
    return GROUP_COLOR[subgroup(lab)]


def marker_of(lab):
    return "D" if lab == "m7" else "o"


# ------------------------------------------------------------------ text and layout
def wrap(text, width_in, size_pt):
    """Wrap to a box width (inches) at a font size (points), by Arial's average character width."""
    per_line = max(int(width_in * 72.0 / (size_pt * 0.50)), 8)
    out = []
    for para in str(text).split("\n"):
        out.append(textwrap.fill(para, per_line) if para.strip() else "")
    return "\n".join(out)


def put(fig, x, y, text, width_in, size=7.0, color=INK, weight="normal", va="top", ha="left", style="normal", line=1.25):
    """Text at figure coordinates (inches from the left/top), wrapped to width_in. Returns its height in inches."""
    W, H = fig.get_size_inches()
    s = wrap(text, width_in, size)
    fig.text(x / W, 1 - y / H, s, fontsize=size, color=color, weight=weight, va=va, ha=ha, style=style, linespacing=line)
    n = s.count("\n") + 1
    return n * size * line / 72.0


def axes_in(fig, x, y, w, h, **kw):
    """Axes placed in inches from the page's top-left."""
    W, H = fig.get_size_inches()
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H], **kw)


_BOLD = FontProperties(family="Arial", weight="bold")


def wrap_measured(text, width_pt, size, bold=True):
    """Greedy word wrap measured with the real font, so a line never runs past width_pt."""
    prop = _BOLD if bold else _FONT
    lines, cur = [], ""
    for word in str(text).split():
        trial = (cur + " " + word).strip()
        wd = TextPath((0, 0), trial, size=size, prop=prop).get_extents().width
        if wd > width_pt and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def letter(fig, x, y, s, title="", width=5.15, size=7.5):
    """A panel letter and its heading (a sentence that states the finding). The heading wraps to `width` inches;
    extra lines grow upward so the panel below keeps its place. Returns the number of lines."""
    W, H = fig.get_size_inches()
    lines = wrap_measured(title, (width - 0.16) * 72.0, size) if title else [""]
    lh = size * 1.22 / 72.0
    top = y - (len(lines) - 1) * lh
    fig.text(x / W, 1 - top / H, s, fontsize=8.5, weight="bold", va="bottom", ha="left", color=INK)
    if title:
        fig.text((x + 0.16) / W, 1 - y / H, "\n".join(lines), fontsize=size, weight="bold", va="bottom", ha="left", color=INK,
                 linespacing=1.22)
    return len(lines)


def note(fig, x, y, text, width_in, size=5.9, color=SOFT):
    return put(fig, x, y, text, width_in, size=size, color=color)


def page(title, kicker, number=None):
    fig = plt.figure(figsize=(8.5, 11))
    put(fig, 0.5, 0.42, kicker, 7.5, size=7, color=C_POS, weight="bold")
    h = put(fig, 0.5, 0.62, title, 7.5, size=13, weight="bold")
    if number is not None:
        fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "%s" % number, fontsize=6.5, color=FAINT, ha="right", va="bottom")
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, "DS story menu \u00b7 exploratory, P values uncorrected \u00b7 2026-11-23", fontsize=6.5,
             color=FAINT, ha="left", va="bottom")
    return fig, 0.62 + h + 0.08


def pstr(p):
    if not np.isfinite(p):
        return "P n/a"
    if p < 0.0001:
        return "P %.1e" % p
    if p < 0.001:
        return "P %.4f" % p
    if p < 0.01:
        return "P %.3f" % p
    return "P %s" % ("%.2g" % p)


def pnum(p):
    return pstr(p)[2:]


def stars(p):
    if not np.isfinite(p):
        return ""
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "n.s."))


def text_size_pt(s, size):
    """Width and height (points) of a one-line string in Arial."""
    if not s:
        return 0.0, 0.0
    ext = TextPath((0, 0), s, size=size, prop=_FONT).get_extents()
    return float(ext.width) + 0.6, float(size) * 0.92


def axes_height_pt(ax):
    return ax.get_position().height * ax.figure.get_size_inches()[1] * 72.0


def axes_width_pt(ax):
    return ax.get_position().width * ax.figure.get_size_inches()[0] * 72.0


# ------------------------------------------------------------------ deferred layout (done in save())
def note_y(ax, values):
    """Remember the data values that must stay on this axis's scale."""
    v = [float(x) for x in np.ravel(values) if np.isfinite(x)]
    ax.__dict__.setdefault("_ydata", []).extend(v)


def defer_labels(ax, pts, texts, color=SOFT, size=5.0):
    """Name these points once the axis limits are final (placed where they overlap nothing)."""
    L = ax.__dict__.setdefault("_labels", [])
    for (x, y), t in zip(pts, texts):
        if np.isfinite(x) and np.isfinite(y):
            L.append((float(x), float(y), t, color, size))


def defer_brackets(ax, pairs, show_ns=False):
    """pairs: [(x1, x2, p)]. Drawn above the data once the limits are final; P < 0.05 only unless show_ns."""
    ax._brackets = {"pairs": list(pairs), "show_ns": show_ns}


def link_y(*axes):
    for a in axes:
        a._ylink = list(axes)


BASE_PT, STEP_PT, TOP_PT = 5.0, 10.0, 8.5


def _levels(ax):
    b = getattr(ax, "_brackets", None)
    if not b:
        return []
    return [(x1, x2, p) for x1, x2, p in sorted(b["pairs"], key=lambda t: abs(t[1] - t[0]))
            if np.isfinite(p) and (p < 0.05 or b["show_ns"])]


def _fy(ax):
    if ax.get_yscale() == "log":
        return np.log10, lambda v: 10 ** v
    return (lambda v: v), (lambda v: v)


def _finish_ylim(group):
    data = [v for a in group for v in getattr(a, "_ydata", [])]
    if not data:
        return
    f, finv = _fy(group[0])
    inv = group[0].yaxis_inverted()
    vals = f(np.array([v for v in data if (group[0].get_yscale() != "log" or v > 0)]))
    if inv:
        vals = -vals                      # upside-down axis: its visual top is the smallest value
    lo, hi = float(np.min(vals)), float(np.max(vals))
    span = hi - lo if hi > lo else (abs(hi) if hi else 1.0)
    n = max(len(_levels(a)) for a in group)
    H = min(axes_height_pt(a) for a in group)
    L = lo - 0.09 * span
    if n:
        room = BASE_PT + (n - 1) * STEP_PT + TOP_PT
        Ht = L + (hi - L) * H / max(H - room, 0.35 * H)
    else:
        Ht = hi + 0.09 * span
    for a in group:
        if inv:
            a.set_ylim(finv(-L), finv(-Ht))
        else:
            a.set_ylim(finv(L), finv(Ht))
        if a.get_yscale() == "log":
            nice = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
            lo_, hi_ = a.get_ylim()
            t = [v for v in nice if lo_ <= v <= hi_]
            a.yaxis.set_major_locator(matplotlib.ticker.FixedLocator(t))
            a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _p: "%g" % v))
            a.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())


def _draw_brackets(ax):
    lv = _levels(ax)
    if not lv:
        return
    data = getattr(ax, "_ydata", [])
    H = axes_height_pt(ax)
    if data:
        x0 = ax.get_xlim()[0]
        pts = ax.transData.transform(np.column_stack([np.full(len(data), x0), np.asarray(data, float)]))
        top = float(np.max(ax.transAxes.inverted().transform(pts)[:, 1]))
    else:
        top = 1.0 - (BASE_PT + len(lv) * STEP_PT) / H
    y0 = top + BASE_PT / H
    tr = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    tick = 2.5 / H
    for k, (x1, x2, p) in enumerate(lv):
        y = y0 + k * STEP_PT / H
        ax.plot([x1, x1, x2, x2], [y - tick, y, y, y - tick], color=INK, lw=0.6, transform=tr, clip_on=False, zorder=6,
                solid_capstyle="butt")
        s = stars(p)
        ax.text((x1 + x2) / 2.0, y + 0.8 / H, s, transform=tr, ha="center", va="bottom", fontsize=6.6 if p < 0.05 else 5.4,
                color=INK, zorder=6, clip_on=False)


def _place_labels(ax):
    L = getattr(ax, "_labels", None)
    if not L:
        return
    fig = ax.figure
    k = 72.0 / fig.dpi
    P = np.array([ax.transData.transform((x, y)) for x, y, _t, _c, _s in L]) * k      # points
    bb = ax.get_window_extent()
    ax_box = (bb.x0 * k, bb.y0 * k, bb.x1 * k, bb.y1 * k)
    # obstacles: every plotted dot on this axis
    obs = []
    from matplotlib.collections import PathCollection
    for coll in ax.collections:
        if not isinstance(coll, PathCollection):
            continue
        try:
            offs = coll.get_offsets()
        except Exception:  # noqa: BLE001
            continue
        if offs is None or len(offs) == 0 or len(offs) > 400:
            continue
        for xy in np.asarray(offs, float):
            if np.all(np.isfinite(xy)):
                px, py = ax.transData.transform(xy) * k
                obs.append((px - 3.0, py - 3.0, px + 3.0, py + 3.0))
    # lines (fits, medians, reference lines): sampled every ~2.5 points along their path
    soft = []
    for ln in ax.lines:
        try:
            path = ln.get_transform().transform_path(ln.get_path())
        except Exception:  # noqa: BLE001
            continue
        V = np.asarray(path.vertices, float) * k
        if V.shape[0] > 600:
            continue
        for a_, b_ in zip(V[:-1], V[1:]):
            if not (np.all(np.isfinite(a_)) and np.all(np.isfinite(b_))):
                continue
            n_ = max(int(np.hypot(*(b_ - a_)) / 2.5), 1)
            for t_ in np.linspace(0, 1, n_ + 1):
                q = a_ + t_ * (b_ - a_)
                soft.append((q[0] - 1.0, q[1] - 1.0, q[0] + 1.0, q[1] + 1.0))
    renderer = fig.canvas.get_renderer()
    for tx in ax.texts:
        try:
            e_ = tx.get_window_extent(renderer)
            obs.append((e_.x0 * k, e_.y0 * k, e_.x1 * k, e_.y1 * k))
        except Exception:  # noqa: BLE001
            pass
    placed = []

    def overlap(b, boxes):
        tot = 0.0
        for o in boxes:
            w = min(b[2], o[2]) - max(b[0], o[0])
            h = min(b[3], o[3]) - max(b[1], o[1])
            if w > 0 and h > 0:
                tot += w * h
        return tot

    order = np.argsort([-np.sum(np.hypot(*(P - P[i]).T) < 14) for i in range(len(L))], kind="stable")
    angles = [0, 30, -30, 180, 150, -150, 60, -60, 90, -90, 120, -120]
    for i in order:
        x, y, t, col, size = L[i]
        w, h = text_size_pt(t, size)
        px, py = P[i]
        best = None
        for d in (4.2, 6.5, 9.5, 13.5, 18.0):
            for ang in angles:
                c, s = np.cos(np.radians(ang)), np.sin(np.radians(ang))
                ax_, ay_ = px + d * c, py + d * s
                bx0 = ax_ if c > 0.3 else (ax_ - w if c < -0.3 else ax_ - w / 2)
                by0 = ay_ if s > 0.3 else (ay_ - h if s < -0.3 else ay_ - h / 2)
                box = (bx0, by0, bx0 + w, by0 + h)
                own = [o for o in obs if not (abs((o[0] + o[2]) / 2 - px) < 0.5 and abs((o[1] + o[3]) / 2 - py) < 0.5)]
                cost = overlap(box, placed) * 4 + overlap(box, own) * 2 + overlap(box, soft) * 1.5
                out = max(0, ax_box[0] - box[0]) + max(0, box[2] - ax_box[2]) + max(0, ax_box[1] - box[1]) + max(0, box[3] - ax_box[3])
                cost += out * h * 3 + d * 0.05
                if best is None or cost < best[0]:
                    best = (cost, box, d)
            if best[0] < d * 0.05 + 1e-6:
                break
        cost, box, d = best
        placed.append(box)
        dx, dy = box[0] - px, box[1] - py
        cx, cy = (box[0] + box[2]) / 2 - px, (box[1] + box[3]) / 2 - py
        if abs(cx) >= abs(cy):
            rel = (0.0, 0.5) if cx > 0 else (1.0, 0.5)
        else:
            rel = (0.5, 0.0) if cy > 0 else (0.5, 1.0)
        ax.annotate(t, xy=(x, y), xycoords="data", xytext=(dx, dy), textcoords="offset points", ha="left", va="bottom",
                    fontsize=size, color=col, zorder=7, annotation_clip=False,
                    arrowprops=(dict(arrowstyle="-", color=LEADER, lw=0.45, shrinkA=0, shrinkB=2.2, relpos=rel)
                                if d > 7 else None))


def finish(fig):
    done = set()
    for ax in fig.axes:
        grp = getattr(ax, "_ylink", None) or [ax]
        key = tuple(id(a) for a in grp)
        if key in done:
            continue
        done.add(key)
        _finish_ylim(grp)
    for ax in fig.axes:
        _draw_brackets(ax)
    for ax in fig.axes:
        _place_labels(ax)


def save(fig, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    finish(fig)
    fig.savefig(os.path.join(out_dir, name + ".png"), dpi=300)
    fig.savefig(os.path.join(out_dir, name + ".pdf"), dpi=600)
    plt.close(fig)


# ------------------------------------------------------------------ per-mouse plots
def mouse_dot(ax, x, y, lab, s=None, hollow=False, z=4):
    col = color_of(lab)
    if hollow:
        ax.scatter([x], [y], s=s or 24, marker=marker_of(lab), facecolor="white", edgecolor=col, linewidth=0.9, zorder=z)
    else:
        ax.scatter([x], [y], s=s or (26 if lab == "m7" else 22), color=col, marker=marker_of(lab), edgecolor="white",
                   linewidth=0.5, zorder=z)


def dots(ax, values, groups, order, xlabels=None, ylabel="", names=(), jitter=0.12, hollow=(), log=False):
    """One dot per mouse at its group; a median line per group. values: {lab: v}; groups: {lab: group}.
    names: mice to name (placed later where they overlap nothing). hollow: mice drawn open and left out of the median."""
    rng = np.random.RandomState(3)
    if log:
        ax.set_yscale("log")
    for k, g in enumerate(order):
        labs = [l for l in values if groups.get(l) == g and np.isfinite(values[l])]
        vs = np.array([values[l] for l in labs if l not in hollow])
        if vs.size:
            ax.plot([k - 0.28, k + 0.28], [np.median(vs)] * 2, color=INK, lw=1.2, zorder=3, solid_capstyle="butt")
        xs = k + (rng.rand(len(labs)) - 0.5) * 2 * jitter
        for x, l in zip(xs, labs):
            mouse_dot(ax, x, values[l], l, hollow=l in hollow)
            if l in names:
                defer_labels(ax, [(x, values[l])], [l + (" (left out)" if l in hollow else "")])
    note_y(ax, [values[l] for l in values if np.isfinite(values[l])])
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(xlabels or [GROUP_WORD.get(g, g) for g in order])
    ax.set_xlim(-0.6, len(order) - 0.4)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", length=0)


def theil(x, y, n_boot=2000, seed=0, xx=None):
    """Theil-Sen line and a 95% bootstrap band over mice."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    sl, ic, _lo, _hi = st.theilslopes(y, x)
    xx = np.linspace(x.min(), x.max(), 60) if xx is None else xx
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


def fit_line(ax, x, y, color=SOFT, n=80, log_y=False):
    """Least-squares line with its 95% confidence band (for the mean), over the range of x."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    yy_ = np.log10(y) if log_y else y
    b, a = np.polyfit(x, yy_, 1)
    xx = np.linspace(x.min(), x.max(), n)
    fit = a + b * xx
    res = yy_ - (a + b * x)
    s = np.sqrt((res ** 2).sum() / max(x.size - 2, 1))
    se = s * np.sqrt(1.0 / x.size + (xx - x.mean()) ** 2 / ((x - x.mean()) ** 2).sum())
    t = st.t.ppf(0.975, max(x.size - 2, 1))
    lo, hi = fit - t * se, fit + t * se
    if log_y:
        fit, lo, hi = 10 ** fit, 10 ** lo, 10 ** hi
    ax.fill_between(xx, lo, hi, color=color, alpha=0.13, lw=0, zorder=1)
    ax.plot(xx, fit, color=color, lw=1.1, zorder=2)
    return b


def ko_scatter(ax, values, ylabel="", hollow=(), names=True, log=False):
    """Value against % knockout; controls at 0. Theil-Sen line with a 95% bootstrap band over the PTEN mice (the
    hollow ones left out of the line)."""
    if log:
        ax.set_yscale("log")
    labs = [l for l in values if np.isfinite(values[l])]
    for l in labs:
        mouse_dot(ax, ko(l), values[l], l, hollow=l in hollow)
    note_y(ax, [values[l] for l in labs])
    pt = [l for l in labs if META[l]["group"] != "CTL" and l not in hollow]
    if len(pt) >= 5:
        xx = np.linspace(min(ko(l) for l in pt), max(ko(l) for l in pt), 60)
        yv = np.array([values[l] for l in pt])
        if log:
            xx, yy, blo, bhi = theil([ko(l) for l in pt], np.log10(yv), xx=xx)
            yy, blo, bhi = 10 ** yy, 10 ** blo, 10 ** bhi
        else:
            xx, yy, blo, bhi = theil([ko(l) for l in pt], yv, xx=xx)
        ax.fill_between(xx, blo, bhi, color=C_POS, alpha=0.12, lw=0, zorder=1)
        ax.plot(xx, yy, color=C_POS, lw=1.1, zorder=2)
    if names:
        nm = [l for l in labs if META[l]["group"] != "CTL"]
        defer_labels(ax, [(ko(l), values[l]) for l in nm], [l + (" (left out)" if l in hollow else "") for l in nm])
    ax.axvline(15, color=FAINT, lw=0.6, ls=":", zorder=0)
    ax.text(15.4, 0.98, "15%", fontsize=5.3, color=FAINT, va="top", transform=ax.get_xaxis_transform())
    ax.set_xlabel("PTEN knockout (% of granule cells)")
    ax.set_ylabel(ylabel)
    ax.set_xlim(-2, 31)


def group_pairs(values, groups, order, contrasts, exclude=()):
    """Generous P for each (cid, a, b) between two groups of a dot plot, from the values (excluded mice left out)."""
    import stats_lib as S
    out = []
    for _cid, a, b in contrasts:
        A = [values[l] for l in values if groups.get(l) == a and l not in exclude and np.isfinite(values[l])]
        B = [values[l] for l in values if groups.get(l) == b and l not in exclude and np.isfinite(values[l])]
        if len(A) >= 3 and len(B) >= 3:
            out.append((order.index(a), order.index(b), S.two(A, B)["p"]))
    return out


IED_PAIRS = [("IEDneg_vs_CTL", "CTL", "IED-"), ("IEDpos_vs_CTL", "CTL", "IED+"), ("IEDpos_vs_IEDneg", "IED-", "IED+")]
KO_PAIRS = [("lowKO_vs_CTL", "CTL", "low KO"), ("highKO_vs_CTL", "CTL", "high KO"), ("highKO_vs_lowKO", "low KO", "high KO")]


def contrast_table(values, exclude=()):
    """{contrast id: stats dict} for these values (stats_lib, generous, uncorrected)."""
    import stats_lib as S
    v = {l: x for l, x in values.items() if l not in exclude}
    return {r["contrast"]: r for r in S.contrasts(v)}


def three_ways(fig, x, y, w, h, values, ylabel, gap=0.32, names_ied=(), hollow=(), log=False, ko_title=True):
    """The three groupings side by side: IED groups | KO groups | % knockout. Brackets mark P < 0.05 (generous,
    uncorrected); hollow mice are drawn open and left out of every test and line."""
    w1 = (w - 2 * gap) * 0.34
    w2 = (w - 2 * gap) * 0.30
    w3 = (w - 2 * gap) * 0.36
    a1 = axes_in(fig, x, y, w1, h)
    a2 = axes_in(fig, x + w1 + gap, y, w2, h)
    a3 = axes_in(fig, x + w1 + w2 + 2 * gap, y, w3, h)
    g1 = {l: subgroup(l) for l in values}
    g2 = {l: kogroup(l) for l in values}
    dots(a1, values, g1, ["CTL", "IED-", "IED+"], ylabel=ylabel, xlabels=["Control", "IED\u2212", "IED+"],
         names=tuple(names_ied) + tuple(hollow), hollow=hollow, log=log)
    dots(a2, values, g2, ["CTL", "low KO", "high KO"], xlabels=["Control", "Low KO", "High KO"], hollow=hollow,
         names=tuple(hollow), log=log)
    ko_scatter(a3, values, hollow=hollow, log=log)
    defer_brackets(a1, group_pairs(values, g1, ["CTL", "IED-", "IED+"], IED_PAIRS, hollow))
    defer_brackets(a2, group_pairs(values, g2, ["CTL", "low KO", "high KO"], KO_PAIRS, hollow))
    link_y(a1, a2, a3)
    T = contrast_table(values, hollow)
    if ko_title:
        rp, ra = T.get("KO_dose_PTEN", {}), T.get("KO_dose_all", {})
        a3.set_title("PTEN \u03c1 %+.2f, %s\nall \u03c1 %+.2f, %s" % (rp.get("effect", np.nan), pstr(rp.get("p", np.nan)),
                                                                     ra.get("effect", np.nan), pstr(ra.get("p", np.nan))),
                     fontsize=5.8, color=SOFT, loc="left", pad=3)
    return a1, a2, a3, T


def legend_mice(fig, x, y, extra=None):
    W, H = fig.get_size_inches()
    hs = [Line2D([], [], ls="", marker="o", ms=4.5, mfc=C_CTL, mec="white", label="Control"),
          Line2D([], [], ls="", marker="o", ms=4.5, mfc=C_NEG, mec="white", label="PTEN IED\u2212"),
          Line2D([], [], ls="", marker="o", ms=4.5, mfc=C_POS, mec="white", label="PTEN IED+"),
          Line2D([], [], ls="", marker="D", ms=4.2, mfc=C_NEG, mec="white", label="m7 (24% KO, no IEDs)")]
    hs += list(extra or [])
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(x / W, 1 - y / H), ncol=len(hs), frameon=False, fontsize=6.3,
               handletextpad=0.3, columnspacing=1.0)


def bracket_note(fig, x, y):
    """The key for brackets, once per page."""
    put(fig, x, y, "Brackets: * P < 0.05, ** < 0.01, *** < 0.001 (generous, uncorrected); no bracket: P \u2265 0.05.", 5.0,
        size=5.8, color=SOFT)


# ------------------------------------------------------------------ line plots: bands and significance bars
def runs(mask):
    """(start, end) index pairs of the True runs of a boolean array."""
    m = np.asarray(mask, bool)
    out, i = [], 0
    while i < m.size:
        if m[i]:
            j = i
            while j + 1 < m.size and m[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def sig_bar_y(ax, grid, mask, xfrac, color, lw=2.6):
    """A vertical bar at axes-fraction x over the depths where mask is True (depth on y)."""
    tr = transforms.blended_transform_factory(ax.transAxes, ax.transData)
    step = float(np.median(np.diff(grid))) if len(grid) > 1 else 0
    for i, j in runs(mask):
        ax.plot([xfrac, xfrac], [grid[i] - step / 2, grid[j] + step / 2], color=color, lw=lw, transform=tr, clip_on=False,
                solid_capstyle="butt", zorder=6)


def sig_bar_x(ax, grid, mask, yfrac, color, lw=2.6, log=False):
    """A horizontal bar at axes-fraction y over the x values where mask is True."""
    tr = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    g = np.asarray(grid, float)
    for i, j in runs(mask):
        if log:
            lo = g[i] / (g[i + 1] / g[i]) ** 0.35 if i + 1 < g.size else g[i] * 0.85
            hi = g[j] * (g[j] / g[j - 1]) ** 0.35 if j > 0 else g[j] * 1.15
        else:
            st_ = float(np.median(np.diff(g))) if g.size > 1 else 0
            lo, hi = g[i] - st_ / 2, g[j] + st_ / 2
        ax.plot([lo, hi], [yfrac, yfrac], color=color, lw=lw, transform=tr, clip_on=False, solid_capstyle="butt", zorder=6)


# ------------------------------------------------------------------ depth registered on the dentate spike
def ds_regions(R):
    """Coarse regions on the blade-to-blade axis u from the median DS landmarks R = {top, gu, gl, bot}."""
    return [("CA1", -9.0, R["top"]), ("distal", R["top"], 0.0), ("proximal", 0.0, R["gu"]), ("Hilus", R["gu"], R["gl"]),
            ("proximal", R["gl"], 1.0), ("distal", 1.0, R["bot"]), ("below", R["bot"], 9.0)]


REGION_SHADE = ["#f2f4f8", "#fbe3cf", "#fdf0e4", "#f3f3ee", "#fdf0e4", "#fbe3cf", "#ffffff"]
REGION_KEYS = ["ca1", "upper_distal", "upper_proximal", "hilus", "lower_proximal", "lower_distal"]
REGION_LONG = {"ca1": "CA1", "upper_distal": "Upper blade, distal dendrites", "upper_proximal": "Upper blade, proximal dendrites",
               "hilus": "Hilus", "lower_proximal": "Lower blade, proximal dendrites", "lower_distal": "Lower blade, distal dendrites"}


def shade_regions(ax, R, labels=True, size=5.6, lines=True, bracket_x=-0.80, shade=True):
    """Shade the DS-defined regions on a depth axis (y = u, increasing downward) and name them at the left:
    CA1, then the upper blade (distal and proximal dendrites), the hilus, the lower blade (proximal, distal)."""
    lo_y, hi_y = sorted(ax.get_ylim())
    regs = ds_regions(R)
    for (name, a, b), col in zip(regs, REGION_SHADE):
        if shade:
            ax.axhspan(max(a, lo_y), min(b, hi_y), color=col, zorder=0, lw=0)
    if lines:
        for v in (0.0, 1.0):
            ax.axhline(v, color=SOFT, lw=0.45, ls=":", zorder=1)
    ax.set_yticks([])
    if not labels:
        return
    tr = transforms.blended_transform_factory(ax.transAxes, ax.transData)
    sub = [("CA1", (max(lo_y, -9) + R["top"]) / 2), ("distal dendrites", R["top"] / 2), ("proximal dendrites", R["gu"] / 2),
           ("Hilus", (R["gu"] + R["gl"]) / 2), ("proximal dendrites", (R["gl"] + 1.0) / 2), ("distal dendrites", (1.0 + R["bot"]) / 2)]
    for t, yy in sub:
        if lo_y <= yy <= hi_y:
            ax.text(-0.035, yy, t, transform=tr, ha="right", va="center", fontsize=size, color=INK, clip_on=False)
    for t, a, b in (("Upper blade", R["top"], R["gu"]), ("Lower blade", R["gl"], R["bot"])):
        ax.plot([bracket_x + 0.03, bracket_x, bracket_x, bracket_x + 0.03], [a + 0.01, a + 0.01, b - 0.01, b - 0.01], transform=tr,
                color=SOFT, lw=0.6, clip_on=False)
        ax.text(bracket_x - 0.03, (a + b) / 2, t, transform=tr, ha="right", va="center", fontsize=size + 0.2, color=INK,
                rotation=90, clip_on=False, weight="bold")


def embed_png(fig, x, y, w, h, path):
    """A pre-rendered picture placed in inches from the page's top-left (no resampling in the PDF)."""
    import matplotlib.image as mpimg
    a = axes_in(fig, x, y, w, h)
    a.imshow(mpimg.imread(path), interpolation="none", aspect="auto")
    a.axis("off")
    return a
