import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
SP = "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad/"
OUT = "/Users/jeremybarry/Documents/GitHub/jeremystats/Barry Playground/KCNT1 Spreadsheets/KCNT1 mouse 459/Seizure anatomical spread"
plt.rcParams.update({"font.family": "Arial", "font.size": 22, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 1.5,
                     "xtick.major.width": 1.5, "ytick.major.width": 1.5, "xtick.major.size": 7, "ytick.major.size": 7, "pdf.fonttype": 42})
T_ON, T_END = 888.7, 916.5
R = np.load(SP + "m459_cache/zones_discharges.npy")
Z = ["supra_distal", "supra_prox", "supra_GCL", "hilus", "infra_GCL", "infra_prox", "infra_distal"]
amp = {z: R[:, 1 + 2 * i] for i, z in enumerate(Z)}; t = R[:, 0] - T_ON
C = {"supra_distal": "#a6dba0", "supra_prox": "#4dac56", "supra_GCL": "#0b5d1e",
     "infra_distal": "#a6c8e6", "infra_prox": "#4a8cc9", "infra_GCL": "#0b3c78", "hilus": "#d7301f"}
LAB = {"supra_distal": "Distal dendrites (CSC 28–31)", "supra_prox": "Proximal dendrites (CSC 33–34)", "supra_GCL": "Cell layer (CSC 35–39)",
       "infra_distal": "Distal dendrites (CSC 56–58)", "infra_prox": "Proximal dendrites (CSC 53–54)", "infra_GCL": "Cell layer (CSC 50–52)", "hilus": "Hilus (CSC 40–49)"}
def runmed(x, y, k=5, gap=1.2):
    o = np.argsort(x); x, y = x[o], y[o]
    m = np.array([np.median(y[max(0, i - k):i + k + 1]) for i in range(len(y))])
    g = np.flatnonzero(np.diff(x) > gap)
    return np.insert(x, g + 1, np.nan), np.insert(m, g + 1, np.nan)
def frame(ax, ylab=True):
    ax.axvspan(t.min() - .5, 0, color="#f4f4f4", lw=0, zorder=0); ax.axvline(0, c="#444", lw=1.5); ax.axvline(T_END - T_ON, c="#444", lw=1.5, ls=(0, (4, 3)))
    ax.set_xlim(t.min() - .3, t.max() + .3)
def series(ax, keys, ylim=(2, 800)):
    for z in keys:
        ax.plot(t, amp[z], "o", ms=4.5, c=C[z], alpha=.3, mec="none")
        xx, yy = runmed(t, amp[z]); ax.plot(xx, yy, c=C[z], lw=4.5, label=LAB[z])
    ax.set_yscale("log"); ax.set_ylim(*ylim); ax.set_yticks([3, 10, 30, 100, 300]); ax.set_yticklabels(["3", "10", "30", "100", "300"])
    frame(ax)

fig = plt.figure(figsize=(24, 18))
gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 0.8, 0.8], width_ratios=[1, 0.2], left=0.08, right=0.975, top=0.875, bottom=0.065, hspace=0.38, wspace=0.12)
fig.text(0.04, 0.968, "B", fontsize=48, fontweight="bold", va="top")
fig.text(0.075, 0.965, "Per-discharge current sinks by dendritic zone, cell layer and hilus", fontsize=32, fontweight="bold", va="top")
fig.text(0.075, 0.927, "KCNT1 Hom mouse 459 · peak current sink per discharge (n = %d), × quiet baseline (400–840 s) · t = 0 at hilar onset" % len(t), fontsize=20, color="#555", va="top")
a1 = fig.add_subplot(gs[0, 0]); series(a1, ["supra_distal", "supra_prox", "supra_GCL"])
a1.set_title("Supra blade", loc="left", fontsize=26, fontweight="bold", color="#1b9e3a"); a1.set_ylabel("Sink (× baseline)")
a1.legend(loc="lower right", fontsize=17, frameon=False, ncol=3, bbox_to_anchor=(1.0, 1.0))
a1.text(-4.4, 520, "pre-onset", fontsize=18, color="#777", ha="center"); a1.text(13.9, 520, "seizure", fontsize=18, color="#777", ha="center")
a2 = fig.add_subplot(gs[1, 0], sharex=a1); series(a2, ["infra_distal", "infra_prox", "infra_GCL"])
a2.set_title("Infra blade", loc="left", fontsize=26, fontweight="bold", color="#2166ac"); a2.set_ylabel("Sink (× baseline)")
a2.legend(loc="lower right", fontsize=17, frameon=False, ncol=3, bbox_to_anchor=(1.0, 1.0))
a3 = fig.add_subplot(gs[2, 0], sharex=a1); series(a3, ["hilus"], ylim=(1, 200)); a3.set_yticks([1, 3, 10, 30, 100]); a3.set_yticklabels(["1", "3", "10", "30", "100"])
a3.set_title("Hilus", loc="left", fontsize=26, fontweight="bold", color="#d7301f"); a3.set_ylabel("Sink (× baseline)")
a4 = fig.add_subplot(gs[3, 0], sharex=a1)
for side, col in (("supra", "#1b9e3a"), ("infra", "#2166ac")):
    r = amp[f"{side}_prox"] / amp[f"{side}_distal"]
    a4.plot(t, r, "o", ms=4.5, c=col, alpha=.3, mec="none"); xx, yy = runmed(t, r); a4.plot(xx, yy, c=col, lw=4.5, label=side.capitalize())
a4.axhline(1, c="k", lw=1, ls=(0, (4, 3))); frame(a4)
a4.set_yscale("log"); a4.set_ylim(0.1, 60); a4.set_yticks([0.1, 1, 10]); a4.set_yticklabels(["0.1", "1", "10"])
a4.set_title("Proximal ÷ distal sink", loc="left", fontsize=26, fontweight="bold"); a4.set_xlabel("Time from hilar onset (s)")
a4.legend(loc="lower right", fontsize=17, frameon=False, ncol=2, bbox_to_anchor=(1.0, 1.0)); a4.set_ylabel("Ratio")
a4.text(t.min(), 0.13, "distal-dominated", fontsize=16, color="#666"); a4.text(t.min(), 40, "proximal-dominated", fontsize=16, color="#666", va="top")
for ax in (a1, a2, a3): ax.tick_params(labelbottom=False)
# zone key: laminar strip
k = fig.add_subplot(gs[:, 1]); k.set_xlim(0, 1); k.set_ylim(60, 26); k.axis("off")
key = [(28, 31, "supra_distal", "distal"), (32, 32, None, ""), (33, 34, "supra_prox", "proximal"), (35, 39, "supra_GCL", "cell layer"),
       (40, 49, "hilus", "hilus"), (50, 52, "infra_GCL", "cell layer"), (53, 54, "infra_prox", "proximal"), (55, 55, None, ""), (56, 58, "infra_distal", "distal")]
for a, b, z, lab in key:
    k.add_patch(Rectangle((0.08, a - .5), 0.22, b - a + 1, fc=(C[z] if z else "#eeeeee"), ec="white", lw=1.5))
    if lab: k.text(0.36, (a + b) / 2, lab, fontsize=18, va="center", color=(C[z] if z else "#999"), fontweight="bold")
    k.text(0.04, (a + b) / 2, f"{a}" if a == b else f"{a}–{b}", fontsize=13, va="center", ha="right", color="#777")
k.text(0.19, 59.2, "CSC59 bad\n(excluded)", fontsize=13, color="#999", ha="center", va="top")
k.text(0.94, 33.5, "SUPRA", fontsize=19, color="#1b9e3a", fontweight="bold", rotation=90, va="center", ha="center")
k.text(0.94, 54.0, "INFRA", fontsize=19, color="#2166ac", fontweight="bold", rotation=90, va="center", ha="center")
k.set_title("Zones on the probe", fontsize=22, fontweight="bold", loc="left")
k.text(0.19, 61.6, "grey = 1-channel gap", fontsize=13, color="#999", ha="center", va="top")
fig.savefig(f"{OUT}/KCNT1_m459_B_progression_v5_stacked.pdf"); fig.savefig(f"{OUT}/KCNT1_m459_B_progression_v5_stacked.png", dpi=300); fig.savefig(SP + "prevB5.png", dpi=55)
print("ok")
