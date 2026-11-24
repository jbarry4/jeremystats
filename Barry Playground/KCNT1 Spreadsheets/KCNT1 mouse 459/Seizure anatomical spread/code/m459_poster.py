import sys, os; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import AsinhNorm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
OUT = "/Users/jeremybarry/Documents/GitHub/jeremystats/Barry Playground/KCNT1 Spreadsheets/KCNT1 mouse 459/Seizure anatomical spread"
plt.rcParams.update({"font.family": "Arial", "font.size": 22, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.linewidth": 1.5, "xtick.major.width": 1.5, "ytick.major.width": 1.5, "xtick.major.size": 7, "ytick.major.size": 7,
                     "pdf.fonttype": 42})
COL = {"CA1": "#7b3294", "Upper blade": "#1b9e3a", "Hilus": "#d7301f", "Lower blade": "#2166ac"}
GROUPS = [("CA1", 2, 27), ("Upper blade", 28, 39), ("Hilus", 40, 49), ("Lower blade", 50, 59)]
LINES = [("Hilus", 40, 49), ("Upper blade", 28, 39), ("Lower blade", 50, 58), ("CA1", 5, 9)]
PH = [(1, "Hilus", (888.7, 889.7), ["Hilus"]),
      (2, "+ Upper blade", (890.0, 891.0), ["Hilus", "Upper blade"]),
      (3, "+ Lower blade", (891.3, 892.3), ["Hilus", "Upper blade", "Lower blade"]),
      (4, "+ CA1", (893.3, 894.3), ["Hilus", "Upper blade", "Lower blade", "CA1"])]
NEW = {1: "Hilus", 2: "Upper blade", 3: "Lower blade", 4: "CA1"}

# CSD over the whole span once
s0, s1 = idx(887.5), idx(895.5)
Xc = sg.sosfiltfilt(sg.butter(4, 60, fs=FS, output="sos"), L[:, s0:s1], axis=1)
C = -np.diff(gaussian_filter1d(Xc, 1.2, axis=0), 2, axis=0) / 0.05**2      # rows = CSC 2..63
C = gaussian_filter1d(C, 0.004 * FS, axis=1)
snaps = [C[:, int((w[0] - 887.5) * FS):int((w[1] - 887.5) * FS)] for _, _, w, _ in PH]
allv = np.abs(np.concatenate([s[:58].ravel() for s in snaps]))
VMAX = np.percentile(allv, 98.5); LW = np.percentile(allv, 40)
Cz = np.load(SP + "m459_cache/csd_ratio_100hz.npy"); tz = T0 + np.arange(Cz.shape[1]) / 100

def schematic(ax, active, new):
    ax.set_xlim(0, 10); ax.set_ylim(0.3, 10); ax.axis("off")
    g = "#dcdcdc"
    c = lambda r: COL[r] if r in active else g
    th = np.linspace(np.pi * .12, np.pi * .88, 60)
    ax.plot(5 + 4.6 * np.cos(th), 5.0 + 3.9 * np.sin(th), c=c("CA1"), lw=14, solid_capstyle="round", zorder=2)
    ax.plot([2.0, 8.6], [5.9, 5.9], c=c("Upper blade"), lw=16, solid_capstyle="round", zorder=2)
    ax.plot([2.0, 8.6], [2.1, 2.1], c=c("Lower blade"), lw=16, solid_capstyle="round", zorder=2)
    t2 = np.linspace(np.pi / 2, 3 * np.pi / 2, 50); ax.plot(2.0 + 1.9 * np.cos(t2), 4.0 + 1.9 * np.sin(t2), c=g, lw=16, solid_capstyle="round", zorder=1)
    ax.add_patch(FancyBboxPatch((2.4, 2.95), 6.0, 2.1, boxstyle="round,pad=0.15", fc=c("Hilus"), ec="none", zorder=2))
    # highlight the newly recruited region
    hl = dict(c="k", lw=2.5, zorder=3, ls=(0, (2, 1.5)))
    if new == "CA1": ax.plot(5 + 4.6 * np.cos(th), 5.0 + 3.9 * np.sin(th) + .55, **hl)
    if new == "Upper blade": ax.plot([2.0, 8.6], [6.55, 6.55], **hl)
    if new == "Lower blade": ax.plot([2.0, 8.6], [1.45, 1.45], **hl)
    if new == "Hilus": ax.add_patch(FancyBboxPatch((2.25, 2.8), 6.3, 2.4, boxstyle="round,pad=0.15", fc="none", ec="k", lw=2.5, ls=(0, (2, 1.5)), zorder=3))
    ax.plot([6.6, 6.6], [9.9, 0.7], c="k", lw=2, zorder=4); ax.plot(6.6, 0.7, "v", c="k", ms=12, zorder=4)

fig = plt.figure(figsize=(24, 18))
gs = fig.add_gridspec(3, 4, height_ratios=[0.34, 1.0, 0.82], left=0.085, right=0.93, top=0.855, bottom=0.07, wspace=0.16, hspace=0.12)
fig.text(0.085, 0.965, "A KCNT1 seizure starts in the hilus and spreads through the dentate gyrus to CA1", fontsize=36, fontweight="bold", va="top")
fig.text(0.085, 0.928, "KCNT1 Hom mouse 459 · awake head-fixed · 64-ch linear probe (50 µm)", fontsize=22, color="#555", va="top")
for k, (n, title, w, active) in enumerate(PH):
    sa = fig.add_subplot(gs[0, k]); schematic(sa, active, NEW[n])
    sa.set_title(f"{n}   {title}", fontsize=30, fontweight="bold", loc="left", pad=6, color=COL[NEW[n]])
    a = fig.add_subplot(gs[1, k])
    S = snaps[k][:58]                      # CSC 2..59
    im = a.imshow(S, aspect="auto", cmap="RdBu", vmin=-VMAX, vmax=VMAX,
                  extent=[0, w[1] - w[0], 59.5, 1.5], interpolation="bilinear")
    for _, a0, b0 in GROUPS[:-1]: a.axhline(b0 + .5, c="k", lw=1.2, ls=(0, (4, 3)), alpha=.55)
    a.set_xticks([]); a.spines["bottom"].set_visible(False)
    gname = NEW[n]; ga = [g for g in GROUPS if g[0] == gname][0]
    a.plot([1.02, 1.02], [ga[1] - .5, ga[2] + .5], c=COL[gname], lw=9, transform=a.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
    if k == 0:
        a.set_yticks([(g[1] + g[2]) / 2 for g in GROUPS]); a.set_yticklabels([g[0].replace(" ", "\n") for g in GROUPS], fontsize=22)
        for lab, g in zip(a.get_yticklabels(), GROUPS): lab.set_color(COL[g[0]]); lab.set_fontweight("bold")
        a.tick_params(axis="y", length=0)
        a.plot([0.05, 0.30], [61.3, 61.3], c="k", lw=4, clip_on=False); a.text(0.175, 63.6, "250 ms", ha="center", va="top", fontsize=20)
        a.annotate("", xy=(-0.015, 59.5), xytext=(-0.015, 1.5), xycoords=("axes fraction", "data"),
                   arrowprops=dict(arrowstyle="-", lw=0))
    else:
        a.set_yticks([]); a.spines["left"].set_visible(False)
    if k < 3:
        fig.patches.append(FancyArrowPatch((0, 0), (1, 0), transform=fig.transFigure))  # placeholder removed below
cax = fig.add_axes([0.945, 0.38, 0.011, 0.27])
cb = fig.colorbar(im, cax=cax); cb.set_ticks([-VMAX * .9, 0, VMAX * .9]); cb.set_ticklabels(["sink", "0", "source"]); cb.ax.tick_params(labelsize=20, length=0)
cb.outline.set_visible(False); cax.set_title("CSD", fontsize=20, pad=10)
fig.patches = [p for p in fig.patches if not isinstance(p, FancyArrowPatch)]
# arrows between CSD columns
for k in range(3):
    x0 = gs[1, k].get_position(fig).x1; x1 = gs[1, k + 1].get_position(fig).x0
    y = gs[0, k].get_position(fig).y0 + 0.05
    fig.patches.append(FancyArrowPatch((x0 + 0.003, y), (x1 - 0.003, y), transform=fig.transFigure, arrowstyle="-|>", mutation_scale=34, lw=3, color="#444"))
# summary
b = fig.add_subplot(gs[2, :])
w = (tz >= 888.0) & (tz <= 895.0)
for name, a0, b0 in LINES:
    y = uniform_filter1d(np.nanmedian(Cz[a0-1:b0], 0), 20)[w]
    b.plot(tz[w], y, c=COL[name], lw=4.5)
    ph = {"Hilus": (888.7, 889.7), "Upper blade": (890.0, 891.0), "Lower blade": (891.3, 892.3), "CA1": (893.3, 894.3)}[name]
    m = (tz[w] >= ph[0]) & (tz[w] <= ph[1]); k = np.argmax(np.where(m, y, -1))
    dx = {"Hilus": -0.05, "Upper blade": 0.0, "Lower blade": -0.45, "CA1": -0.35}[name]
    dy = {"Hilus": 1.45, "Upper blade": 1.5, "Lower blade": 0.42, "CA1": 0.36}[name]
    xx, yy = (tz[w][k] + dx, y[k] * dy) if name != "Lower blade" else (891.6, 4.6)
    b.text(xx, yy, name, color=COL[name], fontsize=24, fontweight="bold", ha="center", va="center",
           bbox=dict(fc="white", ec="none", alpha=.85, pad=1.5))
for n, title, (h0, h1), _ in PH:
    b.axvspan(h0, h1, color="#ececec", lw=0, zorder=0)
    b.text((h0 + h1) / 2, 1.0, str(n), transform=b.get_xaxis_transform(), ha="center", va="bottom", fontsize=28, fontweight="bold", color=COL[NEW[n]])
b.set_yscale("log"); b.set_ylim(1, 150); b.set_yticks([1, 10, 50]); b.set_yticklabels(["1", "10", "50"])
b.set_ylabel("|CSD|  (× baseline)"); b.set_xlabel("Time (s)")
b.set_xlim(888.0, 895.0); b.set_xticks(np.arange(888, 895.1, 1)); b.set_xticklabels([f"{x:.0f}" for x in np.arange(0, 7.1, 1)])
b.text(0.0, -0.21, "t = 0 at 888 s into session 1 (2024-12-06)", transform=b.transAxes, fontsize=16, color="#777")
fig.savefig(f"{OUT}/KCNT1_m459_seizure_spread_poster.pdf")
fig.savefig(f"{OUT}/KCNT1_m459_seizure_spread_poster.png", dpi=300)
fig.savefig(SP + "poster_preview.png", dpi=60)
print("ok", VMAX, LW)
