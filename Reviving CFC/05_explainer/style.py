"""Shared plot styling. One light surface, one sequential blue ramp for
magnitude, a fixed categorical order for identity — no rainbow anywhere
except the one figure that exists to show why rainbows lie."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8880"
GRID = "#e6e5e0"

# categorical slots, fixed order, never cycled
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
     "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# single-hue sequential ramp (blue 100 -> 700), light = near zero
SEQ = LinearSegmentedColormap.from_list("seqblue", [
    "#fcfcfb", "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95",
    "#104281", "#0d366b"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": "#c9c8c2", "axes.linewidth": 0.8,
    "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 10, "axes.titleweight": "600", "axes.titlelocation": "left",
    "axes.titlepad": 8, "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": INK2, "ytick.color": INK2,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
    "grid.color": GRID, "grid.linewidth": 0.7,
    "legend.frameon": False, "legend.fontsize": 8,
    "lines.linewidth": 1.6, "figure.dpi": 130,
})


def tag(ax, s):
    ax.text(-0.13, 1.16, s, transform=ax.transAxes, fontsize=10,
            fontweight="bold", color=INK, ha="right", va="top")


def note(fig, s, y=-0.01, x=0.02):
    """Caption in FIGURE coordinates. Never inside an axes: a wide text
    artist inside an axes makes tight_layout shrink the plot to fit it."""
    fig.text(x, y, s, fontsize=7.6, color=MUTED, ha="left", va="top")
