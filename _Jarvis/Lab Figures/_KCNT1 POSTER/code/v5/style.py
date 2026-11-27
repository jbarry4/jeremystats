"""One look for every figure on the KCNT1 poster (v5).

Every figure is drawn at the exact size it occupies on the 48 x 36 in poster, so the type below is the type that prints:
the same font as the poster's text (Calibri), the same sizes, the same strokes and the same colors everywhere.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

# --------------------------------------------------------------------------- type (points, at print size)
FONT = "Calibri"
TICK = 14
LABEL = 16
TITLE = 17          # a figure's own small titles (bold)
NOTE = 13           # annotations, legends, scale bars
SMALL = 11.5        # the smallest type allowed on the poster

# --------------------------------------------------------------------------- color
INK = "#1E1E1E"
SOFT = "#5F6B7A"     # secondary text, scale bars
FAINT = "#A7B0BC"    # reference lines, dividers
GRID = "#E9EDF1"
GREEN = "#154734"    # the poster's own heading green
GOLD = "#C99A00"     # the poster's panel-heading gold

GENO = {"WT": "#8C8C8C", "Het": "#E08A2C", "Hom": "#7B2D8E"}
# hippocampal regions, used wherever a figure names a region (seizure, discharges, methods)
REGION = {"CA1": "#0072B2", "Supra blade": "#009E73", "Hilus": "#C0392B", "Infra blade": "#CC79A7"}

# CSD everywhere: sinks blue, sources red, white at zero
CSD_CMAP = LinearSegmentedColormap.from_list(
    "csd", ["#08306B", "#2171B5", "#6BAED6", "#DEEBF7", "#FFFFFF", "#FEE0D2", "#FC9272", "#CB181D", "#67000D"])
SPEC_CMAP = "jet"   # spectrograms keep the lab's (and Jarvis's) jet

LW_AXIS = 1.1
LW_TRACE = 0.9


def apply():
    plt.rcParams.update({
        "font.family": FONT, "font.size": TICK, "axes.labelsize": LABEL, "axes.titlesize": TITLE,
        "axes.titleweight": "bold", "xtick.labelsize": TICK, "ytick.labelsize": TICK, "legend.fontsize": NOTE,
        "axes.linewidth": LW_AXIS, "xtick.major.width": LW_AXIS, "ytick.major.width": LW_AXIS,
        "xtick.major.size": 4.5, "ytick.major.size": 4.5, "xtick.major.pad": 3, "ytick.major.pad": 3,
        "axes.edgecolor": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "text.color": INK,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titlepad": 6, "axes.labelpad": 4,
        "legend.frameon": False, "legend.handlelength": 1.4, "legend.borderaxespad": 0.2,
        "lines.linewidth": 1.6, "lines.solid_capstyle": "round", "pdf.fonttype": 42, "svg.fonttype": "none",
        "figure.dpi": 100, "savefig.dpi": 300, "savefig.facecolor": "white", "image.interpolation": "bilinear",
    })


def figure(w_in, h_in):
    """A figure in poster inches; place axes with `ax_at` in inches from its top-left corner."""
    apply()
    fig = plt.figure(figsize=(w_in, h_in))
    fig._wh = (w_in, h_in)
    return fig


def ax_at(fig, x, y, w, h, **kw):
    W, H = fig._wh
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H], **kw)


def text_at(fig, x, y, s, **kw):
    W, H = fig._wh
    kw.setdefault("va", "top")
    return fig.text(x / W, 1 - y / H, s, **kw)


def title(fig, x, y, s, color=INK, size=TITLE, **kw):
    return text_at(fig, x, y, s, fontsize=size, fontweight="bold", color=color, **kw)


def bare(ax):
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])


def scalebar(ax, x, y, dx=None, dy=None, label_x="", label_y="", color=INK, lw=1.8, fs=NOTE, pad=0.02):
    """L-shaped (or single) scale bar in data units."""
    if dx:
        ax.plot([x, x + dx], [y, y], color=color, lw=lw, clip_on=False, solid_capstyle="butt")
        ax.annotate(label_x, (x + dx / 2, y), xytext=(0, -3), textcoords="offset points", ha="center", va="top",
                    fontsize=fs, color=color, annotation_clip=False)
    if dy:
        ax.plot([x, x], [y, y + dy], color=color, lw=lw, clip_on=False, solid_capstyle="butt")
        ax.annotate(label_y, (x, y + dy / 2), xytext=(-4, 0), textcoords="offset points", ha="right", va="center",
                    fontsize=fs, color=color, rotation=90, annotation_clip=False)


def save(fig, path):
    fig.savefig(path, dpi=300)
    plt.close(fig)
