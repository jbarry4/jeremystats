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
      (2, "+ Supra blade", (890.0, 891.0), ["Hilus", "Upper blade"], "silent"),
      (3, "+ Infra blade", (891.3, 892.3), ["Hilus", "Upper blade", "Lower blade"], "silent"),
      (4, "+ CA1", (893.3, 894.3), ["Hilus", "Upper blade", "Lower blade", "CA1"], "silent")]
NEW = {1: "Hilus", 2: "Upper blade", 3: "Lower blade", 4: "CA1"}
DISP = {"Upper blade": "Supra blade", "Lower blade": "Infra blade", "Hilus": "Hilus", "CA1": "CA1"}
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

LFt = sg.sosfiltfilt(sg.butter(4, [1, 300], "band", fs=FS, output="sos"), L[:, s0:s1], axis=1)
tr_snaps = [LFt[:, int((w[0] - 887.5) * FS):int((w[1] - 887.5) * FS)] for _, _, w, _, _ in PH]
TR_CH = [(7, "CA1", "CA1"), (31, "Upper ML", "Upper blade"), (37, "Upper GCL", "Upper blade"), (44, "Hilus", "Hilus"), (51, "Lower GCL", "Lower blade"), (56, "Lower ML", "Lower blade")]
GAP_ROW = np.percentile(np.abs(np.concatenate([t[[c - 1 for c, _, _ in TR_CH]].ravel() for t in tr_snaps])), 99.0) * 1.15
OV_CH = [c for c in range(4, 60, 4) if c != 59]
GAP_OV = np.percentile(np.abs(np.concatenate([t[[c - 1 for c in OV_CH]].ravel() for t in tr_snaps])), 99.0) * 1.0
def nice(v):
    for x in (250, 500, 1000, 2000, 3000, 5000): 
        if x >= v * 0.45: return x
    return 5000
for MODE in ("overlay",):
    fig = plt.figure(figsize=(24, 18))
    if MODE == "row":
        gs = fig.add_gridspec(5, 4, height_ratios=[0.56, 0.9, 0.6, 0.32, 0.6], left=0.095, right=0.93, top=0.885, bottom=0.065, wspace=0.14, hspace=0.42)
        RI, RL, RT = 3, 4, 2
    else:
        gs = fig.add_gridspec(4, 4, height_ratios=[0.62, 1.0, 0.36, 0.72], left=0.095, right=0.93, top=0.885, bottom=0.065, wspace=0.14, hspace=0.27)
        RI, RL, RT = 2, 3, None
    header(fig, "A", "Origin: the seizure starts in the hilus as a hilar interneuron fails")
    for k, (n, title, w, active, inn) in enumerate(PH):
        sa = fig.add_subplot(gs[0, k]); draw(sa, active, NEW[n], inn, labels=(k == 0), ec=False)
        sa.set_title(f"{n}   {title}", fontsize=28, fontweight="bold", loc="left", pad=2, color=COL[NEW[n]])
        a = fig.add_subplot(gs[1, k])
        r0, r1 = w[0] - T_ON, w[1] - T_ON
        im = a.imshow(snaps[k][:58], aspect="auto", cmap="RdBu", vmin=-VMAX, vmax=VMAX, extent=[r0, r1, 59.5, 1.5], interpolation="bilinear")
        a.set_xlim(r0, r1); a.set_ylim(59.5, 1.5); a.set_autoscale_on(False)
        for _, a0, b0 in GROUPS[:-1]: a.axhline(b0 + .5, c="k", lw=1.2, ls=(0, (4, 3)), alpha=.5)
        a.set_xticks([r0, r1]); a.set_xticklabels([f"{r0:.1f} s", f"{r1:.1f} s"], fontsize=19)
        a.get_xticklabels()[0].set_ha("left"); a.get_xticklabels()[1].set_ha("right")
        tt = r0 + np.arange(tr_snaps[k].shape[1]) / FS
        if MODE == "overlay":
            sc_ = 4.0 / GAP_OV
            for c in OV_CH:
                a.plot(tt, c - np.clip(tr_snaps[k][c - 1], -1.3 * GAP_OV, 1.3 * GAP_OV) * sc_, c="#1a1a1a", lw=0.9, alpha=.65)
            if k == 3:
                v = nice(GAP_OV); a.plot([1.06, 1.06], [57, 57 - v * sc_], c="k", lw=4, transform=a.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
                a.text(1.075, 57 - v * sc_ / 2, f"{v/1000:g} mV", transform=a.get_yaxis_transform(), fontsize=18, va="center")
        else:
            a.set_xticks([]); a.spines["bottom"].set_visible(False)
            t_ = fig.add_subplot(gs[RT, k], sharex=a)
            for j, (c, lab, reg) in enumerate(TR_CH):
                t_.plot(tt, np.clip(tr_snaps[k][c - 1], -1.25 * GAP_ROW, 1.25 * GAP_ROW) - j * GAP_ROW, c=COL[reg], lw=1.6)
            t_.set_ylim(-(len(TR_CH) - 0.35) * GAP_ROW, 1.0 * GAP_ROW); t_.set_xlim(r0, r1)
            t_.set_xticks([r0, r1]); t_.set_xticklabels([f"{r0:.1f} s", f"{r1:.1f} s"], fontsize=19)
            t_.get_xticklabels()[0].set_ha("left"); t_.get_xticklabels()[1].set_ha("right")
            t_.spines["left"].set_visible(False)
            if k == 0:
                t_.set_yticks([-j * GAP_ROW for j in range(len(TR_CH))]); t_.set_yticklabels([lab for _, lab, _ in TR_CH], fontsize=17)
                for tl, (_, _, reg) in zip(t_.get_yticklabels(), TR_CH): tl.set_color(COL[reg]); tl.set_fontweight("bold")
                t_.tick_params(axis="y", length=0)
            else:
                t_.set_yticks([])
            if k == 3:
                v = nice(GAP_ROW); y0_ = -(len(TR_CH) - 1) * GAP_ROW
                t_.plot([1.03, 1.03], [y0_, y0_ + v], c="k", lw=4, transform=t_.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
                t_.text(1.045, y0_ + v / 2, f"{v/1000:g} mV", transform=t_.get_yaxis_transform(), fontsize=18, va="center")
        ga = [g for g in GROUPS if g[0] == NEW[n]][0]
        a.plot([1.025, 1.025], [ga[1] - .5, ga[2] + .5], c=COL[NEW[n]], lw=9, transform=a.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
        if k == 0:
            a.set_yticks([(g[1] + g[2]) / 2 for g in GROUPS]); a.set_yticklabels([DISP[g[0]].replace(" ", "\n") for g in GROUPS], fontsize=21)
            for lab, g in zip(a.get_yticklabels(), GROUPS): lab.set_color(COL[g[0]]); lab.set_fontweight("bold")
            a.tick_params(axis="y", length=0)
            a.plot([0.0, 0.25], [1.035, 1.035], c="k", lw=4, clip_on=False, transform=a.transAxes, solid_capstyle="butt")
            a.text(0.27, 1.035, "250 ms", ha="left", va="center", fontsize=19, transform=a.transAxes)
        else:
            a.set_yticks([]); a.spines["left"].set_visible(False)
        if k < 3:
            p0 = gs[0, k].get_position(fig); p1 = gs[0, k + 1].get_position(fig); y = p0.y0 + p0.height * .45
            fig.patches.append(FancyArrowPatch((p0.x1 - .004, y), (p1.x0 + .004, y), transform=fig.transFigure, arrowstyle="-|>", mutation_scale=30, lw=3, color="#444"))
    cax = fig.add_axes([0.943, 0.47, 0.01, 0.2])
    cb = fig.colorbar(im, cax=cax); cb.set_ticks([-VMAX * .9, VMAX * .9]); cb.set_ticklabels(["sink", "source"]); cb.ax.tick_params(labelsize=19, length=0); cb.outline.set_visible(False)
    # interneuron strip
    X0, X1 = 884.0, 895.0
    ia = fig.add_subplot(gs[RI, :])
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
    b = fig.add_subplot(gs[RL, :], sharex=ia)
    w = (tz >= X0) & (tz <= X1)
    for name, a0, b0 in [("Hilus", 40, 49), ("Upper blade", 28, 39), ("Lower blade", 50, 58), ("CA1", 5, 9)]:
        y = uniform_filter1d(np.nanmedian(Cz[a0-1:b0], 0), 20)[w]; b.plot(tz[w] - T_ON, y, c=COL[name], lw=4.5)
    for n, title, (h0, h1), _, _ in PH:
        for ax_ in (ia, b): ax_.axvspan(h0 - T_ON, h1 - T_ON, color="#ececec", lw=0, zorder=0)
        b.text((h0 + h1) / 2 - T_ON, 1.0, str(n), transform=b.get_xaxis_transform(), ha="center", va="bottom", fontsize=26, fontweight="bold", color=COL[NEW[n]])
    LBL = {"Hilus": (0.55, 62), "Upper blade": (2.0, 58), "Lower blade": (3.3, 4.2), "CA1": (5.4, 3.0)}
    for name, (x, y) in LBL.items(): b.text(x, y, DISP[name], color=COL[name], fontsize=22, fontweight="bold", ha="center", bbox=dict(fc="white", ec="none", alpha=.85, pad=1))
    b.set_yscale("log"); b.set_ylim(1, 150); b.set_yticks([1, 10, 100]); b.set_yticklabels(["1", "10", "100"])
    b.set_ylabel("CSD change\nvs own baseline (×)", fontsize=20); b.set_xlabel("Time from hilar onset (s)")
    fig.text(0.095, 0.012, "Snapshots show absolute current (largest in the dendritic layers, where input arrives); lines show change from each layer's own baseline (largest in the normally quiet hilus).",
             fontsize=15, color="#666")
    nm = "v6_overlay"
    fig.savefig(f"{OUT}/KCNT1_m459_A_origin_{nm}.pdf"); fig.savefig(f"{OUT}/KCNT1_m459_A_origin_{nm}.png", dpi=300); fig.savefig(SP + f"prev_{MODE}.png", dpi=55)
    plt.close(fig)


print("ok", GAP_ROW, GAP_OV)
