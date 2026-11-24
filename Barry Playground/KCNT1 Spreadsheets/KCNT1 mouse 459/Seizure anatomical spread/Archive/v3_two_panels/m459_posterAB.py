import sys, os; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from hpc_schematic import draw, COL
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from matplotlib.lines import Line2D
OUT = "/Users/jeremybarry/Documents/GitHub/jeremystats/Barry Playground/KCNT1 Spreadsheets/KCNT1 mouse 459/Seizure anatomical spread"
plt.rcParams.update({"font.family": "Arial", "font.size": 22, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 1.5,
                     "xtick.major.width": 1.5, "ytick.major.width": 1.5, "xtick.major.size": 7, "ytick.major.size": 7, "pdf.fonttype": 42})
T_ON = 888.7                                    # hilar onset = t 0
GROUPS = [("CA1", 2, 27), ("Upper blade", 28, 39), ("Hilus", 40, 49), ("Lower blade", 50, 59)]
PH = [(1, "Hilus", (888.7, 889.7), ["Hilus"], "active"),
      (2, "+ Upper blade", (890.0, 891.0), ["Hilus", "Upper blade"], "silent"),
      (3, "+ Lower blade", (891.3, 892.3), ["Hilus", "Upper blade", "Lower blade"], "silent"),
      (4, "+ CA1", (893.3, 894.3), ["Hilus", "Upper blade", "Lower blade", "CA1"], "silent")]
NEW = {1: "Hilus", 2: "Upper blade", 3: "Lower blade", 4: "CA1"}
SUB = "KCNT1 Hom mouse 459 · awake head-fixed · 64-ch linear probe (50 µm) · t = 0 at hilar onset"

def header(fig, letter, title):
    fig.text(0.06, 0.968, letter, fontsize=48, fontweight="bold", va="top")
    fig.text(0.095, 0.965, title, fontsize=34, fontweight="bold", va="top")
    fig.text(0.095, 0.927, SUB, fontsize=20, color="#555", va="top")

# ===================== PANEL A: ORIGIN =====================
s0 = idx(887.5); s1 = idx(895.5)
Xc = sg.sosfiltfilt(sg.butter(4, 60, fs=FS, output="sos"), L[:, s0:s1], axis=1)
C = gaussian_filter1d(-np.diff(gaussian_filter1d(Xc, 1.2, axis=0), 2, axis=0) / 0.05**2, 0.004 * FS, axis=1)
snaps = [C[:, int((w[0] - 887.5) * FS):int((w[1] - 887.5) * FS)] for _, _, w, _, _ in PH]
VMAX = np.percentile(np.abs(np.concatenate([s[:58].ravel() for s in snaps])), 98.5)
Cz = np.load(SP + "m459_cache/csd_ratio_100hz.npy"); tz = T0 + np.arange(Cz.shape[1]) / 100
srt = np.load(SP + "m459_cache/hilar_sort.npz"); u1 = srt["tsec"][srt["lab"] == 1]
U1_TEMPLATE = srt["templates"][[int(r[0]) for r in srt["units"]].index(1)]

fig = plt.figure(figsize=(24, 18))
gs = fig.add_gridspec(4, 4, height_ratios=[0.62, 1.0, 0.36, 0.72], left=0.095, right=0.93, top=0.885, bottom=0.065, wspace=0.14, hspace=0.27)
header(fig, "A", "Origin: the seizure starts in the hilus as a hilar interneuron fails")
for k, (n, title, w, active, inn) in enumerate(PH):
    sa = fig.add_subplot(gs[0, k]); draw(sa, active, NEW[n], inn, labels=(k == 0))
    sa.set_title(f"{n}   {title}", fontsize=28, fontweight="bold", loc="left", pad=2, color=COL[NEW[n]])
    a = fig.add_subplot(gs[1, k])
    im = a.imshow(snaps[k][:58], aspect="auto", cmap="RdBu", vmin=-VMAX, vmax=VMAX, extent=[0, 1, 59.5, 1.5], interpolation="bilinear")
    for _, a0, b0 in GROUPS[:-1]: a.axhline(b0 + .5, c="k", lw=1.2, ls=(0, (4, 3)), alpha=.5)
    a.set_xticks([]); a.spines["bottom"].set_visible(False)
    ga = [g for g in GROUPS if g[0] == NEW[n]][0]
    a.plot([1.025, 1.025], [ga[1] - .5, ga[2] + .5], c=COL[NEW[n]], lw=9, transform=a.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
    if k == 0:
        a.set_yticks([(g[1] + g[2]) / 2 for g in GROUPS]); a.set_yticklabels([g[0].replace(" ", "\n") for g in GROUPS], fontsize=21)
        for lab, g in zip(a.get_yticklabels(), GROUPS): lab.set_color(COL[g[0]]); lab.set_fontweight("bold")
        a.tick_params(axis="y", length=0)
        a.plot([0.05, 0.30], [61.0, 61.0], c="k", lw=4, clip_on=False); a.text(0.175, 63.2, "250 ms", ha="center", va="top", fontsize=19)
    else:
        a.set_yticks([]); a.spines["left"].set_visible(False)
    if k < 3:
        p0 = gs[0, k].get_position(fig); p1 = gs[0, k + 1].get_position(fig); y = p0.y0 + p0.height * .45
        fig.patches.append(FancyArrowPatch((p0.x1 - .004, y), (p1.x0 + .004, y), transform=fig.transFigure, arrowstyle="-|>", mutation_scale=30, lw=3, color="#444"))
cax = fig.add_axes([0.943, 0.47, 0.01, 0.2])
cb = fig.colorbar(im, cax=cax); cb.set_ticks([-VMAX * .9, VMAX * .9]); cb.set_ticklabels(["sink", "source"]); cb.ax.tick_params(labelsize=19, length=0); cb.outline.set_visible(False)
# interneuron strip
X0, X1 = 884.0, 895.0
ia = fig.add_subplot(gs[2, :])
bins = np.arange(X0, X1 + .01, 0.25); h, _ = np.histogram(u1, bins)
ia.bar(bins[:-1] - T_ON, h / 0.25, width=0.25, align="edge", color="#e6a700", ec="none")
ia.axhline(13.7, c="#555", lw=1.5, ls=(0, (4, 3))); ia.text(X0 - T_ON + 0.05, 17, "baseline 13.7 Hz", fontsize=16, color="#555", va="bottom")
ia.axvspan(892.4 - T_ON, X1 - T_ON, fc="none", ec="#b0b0b0", hatch="///", lw=0, zorder=0)
ia.text(895.0 - T_ON - 0.05, 50, "single spikes masked by\npopulation discharges", fontsize=15, color="#777", ha="right", va="top")
ia.set_ylabel("Hz", fontsize=20); ia.set_xlim(X0 - T_ON, X1 - T_ON); ia.set_yticks([0, 40]); ia.set_ylim(0, 62); ia.tick_params(labelbottom=False)
ia.set_title("Hilar interneuron (ch 41): fires ~3× baseline in the 3 s before onset, then is lost — silent for >80 s after the seizure", loc="left", fontsize=20, fontweight="bold", color="#8a6100", pad=6)
wa = ia.inset_axes([1.005, 0.05, 0.045, 0.9]); wv = U1_TEMPLATE
for j in range(7): wa.plot(wv[j] - j * 120, c="#8a6100", lw=1.6)
wa.axis("off")
# fold-change lines
b = fig.add_subplot(gs[3, :], sharex=ia)
w = (tz >= X0) & (tz <= X1)
for name, a0, b0 in [("Hilus", 40, 49), ("Upper blade", 28, 39), ("Lower blade", 50, 58), ("CA1", 5, 9)]:
    y = uniform_filter1d(np.nanmedian(Cz[a0-1:b0], 0), 20)[w]; b.plot(tz[w] - T_ON, y, c=COL[name], lw=4.5)
for n, title, (h0, h1), _, _ in PH:
    for ax_ in (ia, b): ax_.axvspan(h0 - T_ON, h1 - T_ON, color="#ececec", lw=0, zorder=0)
    b.text((h0 + h1) / 2 - T_ON, 1.0, str(n), transform=b.get_xaxis_transform(), ha="center", va="bottom", fontsize=26, fontweight="bold", color=COL[NEW[n]])
LBL = {"Hilus": (0.55, 62), "Upper blade": (2.0, 58), "Lower blade": (3.3, 4.2), "CA1": (5.4, 3.0)}
for name, (x, y) in LBL.items(): b.text(x, y, name, color=COL[name], fontsize=22, fontweight="bold", ha="center", bbox=dict(fc="white", ec="none", alpha=.85, pad=1))
b.set_yscale("log"); b.set_ylim(1, 150); b.set_yticks([1, 10, 100]); b.set_yticklabels(["1", "10", "100"])
b.set_ylabel("CSD change\nvs own baseline (×)", fontsize=20); b.set_xlabel("Time from hilar onset (s)")
fig.text(0.095, 0.012, "Snapshots show absolute current (largest in the dendritic layers, where input arrives); lines show change from each layer's own baseline (largest in the normally quiet hilus).",
         fontsize=15, color="#666")
fig.savefig(f"{OUT}/KCNT1_m459_A_origin.pdf"); fig.savefig(f"{OUT}/KCNT1_m459_A_origin.png", dpi=300); fig.savefig(SP + "prevA.png", dpi=55)
plt.close(fig)

# ===================== PANEL B: PROGRESSION =====================
R = np.load(SP + "m459_cache/discharges.npy")          # t, inUp, inLo, outDG, nps, outCA1
pre = R[:, 0] < T_ON
fold = lambda k: R[:, k] / np.median(R[pre, k])
tR = R[:, 0] - T_ON
fig = plt.figure(figsize=(24, 18))
gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.95], width_ratios=[1, 1, 0.95], left=0.085, right=0.965, top=0.875, bottom=0.075, wspace=0.3, hspace=0.36)
header(fig, "B", "Progression: same synaptic input, dentate output jumps, CA1 locks in")
a = fig.add_subplot(gs[0, :])
SER = [("Synaptic input  (dendritic sink, upper molecular layer)", 1, "#555555"), ("Dentate output  (granule + hilus, 150–600 Hz)", 3, COL["Hilus"]), ("CA1 output  (pyramidal layer, 150–600 Hz)", 5, COL["CA1"])]
for lab, k, c in SER:
    y = fold(k); a.plot(tR, y, "o", ms=5, c=c, alpha=.28, mec="none")
    o = np.argsort(tR); rm = np.array([np.median(y[o][max(0, i - 5):i + 6]) for i in range(len(o))])
    tt_ = tR[o].astype(float); rr = rm.astype(float); gap = np.flatnonzero(np.diff(tt_) > 1.2)
    tt_ = np.insert(tt_, gap + 1, np.nan); rr = np.insert(rr, gap + 1, np.nan)
    a.plot(tt_, rr, c=c, lw=5, label=lab)
a.axhline(1, c="k", lw=1, ls=(0, (4, 3)))
a.axvspan(0, 916.3 - T_ON, color="#f3f3f3", lw=0, zorder=0)
a.text(0.2, 30, "seizure", fontsize=20, color="#777"); a.axvline(916.3 - T_ON, c="#777", lw=1.5)
a.set_yscale("log"); a.set_ylim(0.15, 40); a.set_yticks([0.3, 1, 3, 10, 30]); a.set_yticklabels(["0.3", "1", "3", "10", "30"])
a.set_xlim(-5, 31); a.set_xlabel("Time from hilar onset (s)"); a.set_ylabel("Per discharge, × pre-ictal")
a.legend(loc="upper right", fontsize=19, frameon=False)
a.annotate("dentate output jumps ~8×\nwhile input does not rise", xy=(2.3, 7.5), xytext=(3.2, 0.25), fontsize=19, arrowprops=dict(arrowstyle="-|>", lw=2, color="#333"), color="#333")
# I/O gain
g = fig.add_subplot(gs[1, 0])
cm = plt.cm.plasma; tn = np.clip((tR - 0) / 28, 0, 1)
g.scatter(fold(1)[pre], fold(3)[pre], s=60, c="#9a9a9a", ec="none", label="pre-ictal")
sc = g.scatter(fold(1)[~pre], fold(3)[~pre], s=60, c=tR[~pre], cmap=cm, vmin=0, vmax=28, ec="none")
g.set_xscale("log"); g.set_yscale("log"); g.set_xlim(0.2, 3); g.set_ylim(0.3, 25)
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator
g.xaxis.set_major_locator(FixedLocator([0.3, 1, 3])); g.xaxis.set_major_formatter(FixedFormatter(["0.3", "1", "3"])); g.xaxis.set_minor_locator(NullLocator())
g.yaxis.set_major_locator(FixedLocator([0.3, 1, 3, 10])); g.yaxis.set_major_formatter(FixedFormatter(["0.3", "1", "3", "10"])); g.yaxis.set_minor_locator(NullLocator())
g.set_xlabel("Synaptic input (× pre-ictal)"); g.set_ylabel("Dentate output (× pre-ictal)")
g.set_title("Input → output gain", fontsize=24, fontweight="bold", loc="left")
cgx = g.inset_axes([0.52, 0.1, 0.42, 0.04]); cbg = fig.colorbar(sc, cax=cgx, orientation="horizontal"); cbg.set_label("s from onset", fontsize=16); cbg.ax.tick_params(labelsize=15); cbg.set_ticks([0, 10, 20])
g.text(0.22, 0.75, "pre-ictal", fontsize=18, color="#777")
# DG -> CA1 lag
l = fig.add_subplot(gs[1, 1])
ST = [(889.0, 892.0, 0.0, .43), (892.0, 897.0, 0.0, .29), (897.0, 902.0, 11.5, .48), (902.0, 907.0, 14.0, .42), (907.0, 912.0, 12.0, .52), (912.0, 916.5, 13.5, .43)]
xs = [((s0_ + s1_) / 2 - T_ON) for s0_, s1_, _, _ in ST]
l.plot(xs, [s[2] for s in ST], c=COL["CA1"], lw=3.5, zorder=2)
l.scatter(xs, [s[2] for s in ST], s=[s[3] * 900 for s in ST], c=COL["CA1"], ec="white", lw=1.5, zorder=3)
l.axhline(0, c=COL["Hilus"], lw=3, alpha=.6); l.text(28.5, 1.0, "within DG: 0 ms", color=COL["Hilus"], fontsize=17, ha="right")
l.set_ylim(-3, 19); l.set_xlim(-1, 29); l.set_xlabel("Time from hilar onset (s)"); l.set_ylabel("CA1 delay after DG (ms)")
l.set_title("DG → CA1 delay", fontsize=24, fontweight="bold", loc="left")
l.text(9.5, 16.0, "CA1 locks in ~12–14 ms\nbehind the dentate", fontsize=18, color=COL["CA1"])
l.text(0.0, 3.5, "0 ms, weak\n(volume\nconduction)", fontsize=15, color="#777")
# loop schematic
s = fig.add_subplot(gs[1, 2]); draw(s, ["Hilus", "Upper blade", "Lower blade", "CA1"], None, "silent", labels=True)
arr = dict(arrowstyle="-|>", mutation_scale=22, lw=3.2)
s.add_patch(FancyArrowPatch((6.3, 4.45), (9.25, 4.9), connectionstyle="arc3,rad=-0.2", color="#c26b00", **arr))
s.add_patch(FancyArrowPatch((9.55, 5.9), (7.2, 8.05), connectionstyle="arc3,rad=0.35", color="#c26b00", **arr))
s.add_patch(FancyArrowPatch((1.3, 7.3), (0.2, 3.0), connectionstyle="arc3,rad=0.3", color="#999", ls=(0, (3, 2)), **arr))
s.text(10.3, 8.4, "≈13 ms", fontsize=20, color="#c26b00", fontweight="bold", ha="right")
s.text(-0.1, 6.0, "to cortex?\n(not recorded)", fontsize=14, color="#888", ha="right")
s.set_title("Hypersynchronous loop", fontsize=24, fontweight="bold", loc="left", pad=18)
fig.savefig(f"{OUT}/KCNT1_m459_B_progression.pdf"); fig.savefig(f"{OUT}/KCNT1_m459_B_progression.png", dpi=300); fig.savefig(SP + "prevB.png", dpi=55)
print("ok")
