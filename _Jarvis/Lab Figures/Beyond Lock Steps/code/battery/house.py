"""The look of every PDF in this folder (the lab's Nature-style figures):
fonts, colors, millimeter placement. No data, no Jarvis."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402

_have = {f.name for f in font_manager.fontManager.ttflist}
_fam = next((f for f in ("Arial", "Helvetica", "Liberation Sans") if f in _have), "DejaVu Sans")
plt.rcParams.update({
    "font.family": _fam, "font.size": 6, "axes.titlesize": 6.5, "axes.labelsize": 6, "xtick.labelsize": 5.5, "ytick.labelsize": 5.5,
    "legend.fontsize": 5.5, "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.major.size": 2.0,
    "ytick.major.size": 2.0, "xtick.major.pad": 1.5, "ytick.major.pad": 1.5, "lines.linewidth": 0.75, "axes.spines.top": False,
    "axes.spines.right": False, "pdf.fonttype": 42, "ps.fonttype": 42, "axes.unicode_minus": True, "figure.facecolor": "white",
    "axes.facecolor": "white", "savefig.facecolor": "white"})

W = 183.0                                   # page width, mm
INK, MUTE, HAIR = "#1A1A1A", "#6B6B6B", "#C9C9C9"
C_CTL = "#5A6470"
C_DS1, C_DS2, C_DS3 = "#0072B2", "#D55E00", "#009E73"
C_IEDN, C_IEDP = "#E2A458", "#8E2A0B"       # PTEN IED-, PTEN IED+
RED, PURPLE, GREEN = "#B5361F", "#6A3D9A", "#1B7F4B"
KO_CMAP = LinearSegmentedColormap.from_list("ko", ["#F6C99B", "#E2711D", "#8E2A0B"])
KO_NORM = Normalize(0, 30)
CSD_CMAP = LinearSegmentedColormap.from_list("csd", ["#0B3C7A", "#2F79B9", "#A9CCE6", "#FAFAFA", "#F0B49A", "#CC4B37", "#7A0F1C"])
SI_CMAP = LinearSegmentedColormap.from_list("si", ["#FFFFFF", "#D9EFE6", "#7CC7A9", "#1B7F4B"])
FS, FS_S = 6.5, 5.5
GROUP_COL = {"CTL": C_CTL, "PTEN": "#C8591A", "IED-": C_IEDN, "IED+": C_IEDP}
GROUP_NAME = {"CTL": "Control", "PTEN": "PTEN knockout", "IED-": "PTEN IED−", "IED+": "PTEN IED+"}


def col_of(r):
    """A recording's color: slate for control, light to dark orange by knockout."""
    return C_CTL if r.group == "CTL" else KO_CMAP(KO_NORM(r.ko))


def page(h_mm):
    return plt.figure(figsize=(W / 25.4, h_mm / 25.4))


def ax_mm(fig, H, x, y, w, h, **kw):
    """Axes placed in millimeters from the page's top-left."""
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H], **kw)


def text_mm(fig, H, x, y, s, **kw):
    kw.setdefault("fontsize", FS)
    kw.setdefault("ha", "left")
    kw.setdefault("va", "center")
    return fig.text(x / W, 1 - y / H, s, **kw)


def letter(fig, H, x, y, s):
    fig.text(x / W, 1 - y / H, s, fontsize=8, fontweight="bold", va="top", ha="left")


def bare(ax):
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])


def stamp(fig, word="UNCORRECTED"):
    fig.text(0.995, 0.997, word, fontsize=8, fontweight="bold", color=RED, ha="right", va="top")
