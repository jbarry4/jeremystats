"""The DS3 round's figure (Halo set, room v6, Impression v2), in the house
Nature style: PDF (vector) and PNG (300 dpi), and the robustness numbers."""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import numpy as np  # noqa: E402
from scipy import stats as st  # noqa: E402
from backend import joepromptfigs as JF  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = r"c:\Users\Z390\Desktop\DS3_figures_2026-11-13"
os.makedirs(OUT, exist_ok=True)
rows = json.load(open(os.path.join(HERE, "ds3_round.json")))
plt = JF._plt()
BLUE, ORANGE, GREEN, GREY = JF.OKABE[0], JF.OKABE[1], JF.OKABE[2], JF.GREY
FS, FS_S = 6.5, 5.5
scored = [x for x in rows if not x["why"]]
ctl = [x for x in scored if x["g"] == "CTL"]
pten = sorted([x for x in scored if x["g"] == "PTEN"], key=lambda x: x["ko"])

fig = JF._fig(183, 128)
gs = fig.add_gridspec(2, 4, left=0.07, right=0.985, top=0.86, bottom=0.13, hspace=0.62, wspace=0.62,
                      height_ratios=[1, 1])

# a  What each recording's events are.
ax = fig.add_subplot(gs[0, :])
order = sorted([x for x in rows if x["g"] == "CTL"], key=lambda x: x["lab"]) + sorted(
    [x for x in rows if x["g"] == "PTEN"], key=lambda x: x["ko"])
xs = np.arange(len(order)) + np.array([0 if x["g"] == "CTL" else 0.6 for x in order])
bot = np.zeros(len(order))
for key, col, lab in (("n1", BLUE, "DS1"), ("n2", ORANGE, "DS2"), ("n3", GREEN, "DS3 (hybrid)")):
    v = np.array([100.0 * x[key] / x["n"] for x in order])
    ax.bar(xs, v, bottom=bot, color=col, width=0.78, label=lab, linewidth=0)
    bot += v
ax.set_xticks(xs)
ax.set_xticklabels([x["lab"].split()[0] + ("\n%.0f%%" % x["ko"] if x["g"] == "PTEN" else "\n" + ("n=%d" % x["n"]))
                    for x in order], fontsize=FS_S)
nc = sum(1 for x in order if x["g"] == "CTL")
ax.text(xs[:nc].mean(), 106, "Control", ha="center", va="bottom", fontsize=FS)
ax.text(xs[nc:].mean(), 106, "PTEN (by % knockout)", ha="center", va="bottom", fontsize=FS)
for x_, r in zip(xs, order):
    if r["why"]:
        ax.text(x_, 50, "not scored", rotation=90, ha="center", va="center", fontsize=FS_S, color="white")
ax.set_ylim(0, 100)
ax.set_ylabel("Share of events (%)", fontsize=FS)
ax.legend(fontsize=FS_S, frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.13), handlelength=1.0)
JF._tidy(ax)


def two(ax, key, ylabel, scale=1.0):
    rng = np.random.default_rng(3)
    for i, (grp, col) in enumerate(((ctl, GREY), (pten, GREEN))):
        v = np.array([x[key] * scale for x in grp])
        ax.scatter(i + rng.uniform(-0.13, 0.13, v.size), v, s=11, color=col, edgecolor="white", linewidth=0.3, zorder=3)
        ax.plot([i - 0.25, i + 0.25], [np.median(v)] * 2, color="black", lw=0.9, zorder=4)
    a, b = [x[key] for x in ctl], [x[key] for x in pten]
    p = st.mannwhitneyu(a, b, alternative="two-sided").pvalue
    ax.set_yscale("symlog", linthresh=0.1 * (scale if scale > 1 else 1) if scale > 1 else 0.1)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Control\n(n = %d)" % len(a), "PTEN\n(n = %d)" % len(b)], fontsize=FS)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel(ylabel, fontsize=FS)
    ax.set_ylim(bottom=0)
    ax.text(0.5, 1.02, "P = %.2f" % p, transform=ax.transAxes, ha="center", va="bottom", fontsize=FS)
    JF._tidy(ax)
    return p


p_rate = two(fig.add_subplot(gs[1, 0]), "rate", "DS3 rate (events per min)")
p_share = two(fig.add_subplot(gs[1, 1]), "share", "DS3 share of events (%)", 100.0)

# d  Among PTEN, against the knockout.
ax = fig.add_subplot(gs[1, 2])
ko = np.array([x["ko"] for x in pten], float)
sh = np.array([100.0 * x["share"] for x in pten])
ax.scatter(ko, sh, s=13, color=GREEN, edgecolor="white", linewidth=0.3, zorder=3)
ax.set_yscale("symlog", linthresh=1.0)
ax.set_ylim(bottom=0)
ax.set_xlabel("PTEN knockout (%)", fontsize=FS)
ax.set_ylabel("DS3 share of events (%)", fontsize=FS)
rho = st.spearmanr(ko, sh)
ax.text(0.04, 0.97, "Spearman $\\rho$ = %.2f\nP = %.3f, n = %d" % (rho.correlation, rho.pvalue, len(pten)),
        transform=ax.transAxes, ha="left", va="top", fontsize=FS)
JF._tidy(ax)

# e  The same correlation when OML and MML are placed another way (measured
# 2026-11-13 by ds3_sens.py and ds3_fixed.py; Halo set, then No P-spikes set).
ax = fig.add_subplot(gs[1, 3])
SENS = [("Bite line,\nlowest point", 0.88, 0.66), ("Bite line,\ndefault", 0.10, -0.05), ("PCA", 0.07, -0.43),
        ("delta", 0.02, 0.22), ("No split:\nblade quarters", 0.08, -0.26)]
yy = np.arange(len(SENS))[::-1]
ax.axvline(0, color=GREY, lw=0.6)
ax.scatter([x[1] for x in SENS], yy + 0.12, s=13, color=GREEN, edgecolor="white", linewidth=0.3, label="Halo set", zorder=3)
ax.scatter([x[2] for x in SENS], yy - 0.12, s=13, color="white", edgecolor=GREEN, linewidth=0.8, label="No P-spikes set", zorder=3)
ax.set_yticks(yy)
ax.set_yticklabels([x[0] for x in SENS], fontsize=FS_S)
ax.set_xlim(-1, 1)
ax.set_xlabel("Spearman rho," + chr(10) + "DS3 share vs % knockout", fontsize=FS)
ax.legend(fontsize=FS_S, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=1, handletextpad=0.2)
JF._tidy(ax)
for a_ in fig.axes:
    a_.tick_params(labelsize=FS_S)
JF.letters(fig)
for ext, kw in ((".pdf", {}), (".png", {"dpi": 300})):
    fig.savefig(os.path.join(OUT, "DS3_PTEN_vs_CTL" + ext), **kw)
plt.close(fig)

# Robustness, for the words.
print("PTEN vs CTL: DS3 rate P %.3f, share P %.3f (Mann-Whitney, n %d vs %d)" % (p_rate, p_share, len(ctl), len(pten)))
print("PTEN, share vs %%KO: rho %.2f P %.4f" % (rho.correlation, rho.pvalue))
rng = np.random.default_rng(0)
perm = np.array([st.spearmanr(ko, rng.permutation(sh)).correlation for _ in range(20000)])
print("   permutation P %.4f" % float((np.abs(perm) >= abs(rho.correlation) - 1e-12).mean()))
loo = [st.spearmanr(np.delete(ko, i), np.delete(sh, i)) for i in range(len(ko))]
print("   leave one mouse out: rho %.2f to %.2f, worst P %.3f" % (min(l.correlation for l in loo), max(l.correlation for l in loo), max(l.pvalue for l in loo)))
rr = st.spearmanr(ko, [x["rate"] for x in pten])
print("   rate vs %%KO: rho %.2f P %.4f" % (rr.correlation, rr.pvalue))
print("   DS3 counts among PTEN by KO:", [(x["ko"], x["n3"], x["n"]) for x in pten])
lo = [x for x in pten if x["ko"] < 10]; hi = [x for x in pten if x["ko"] >= 10]
print("   low KO (<10%%) n %d median share %.2f%% | high KO n %d median %.2f%% | MWU P %.3f" % (
    len(lo), 100 * np.median([x["share"] for x in lo]), len(hi), 100 * np.median([x["share"] for x in hi]),
    st.mannwhitneyu([x["share"] for x in lo], [x["share"] for x in hi]).pvalue))
al = st.spearmanr([x["ko"] or 0.0 for x in scored], [x["share"] for x in scored])
print("   all 17 with controls at 0%%: rho %.2f P %.3f (a CTL-vs-PTEN mix, not a dose)" % (al.correlation, al.pvalue))
print("saved to", OUT)
