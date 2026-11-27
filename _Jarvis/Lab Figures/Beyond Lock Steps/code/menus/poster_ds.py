"""Poster figure (draft): the IED / DS story in four panels, from the Jeremy menu's data.
a  DS fast power per mouse, by group      b  BT and IED-class events per minute, mice in order of knockout
c  fast power, WT DS | DS | BT | IED       d  lower-blade MML sink, same classes
Written to ../poster/img/ds_story.png at 600 dpi."""
import os
import sys
import warnings

import numpy as np
from matplotlib.lines import Line2D

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import jpages as J  # noqa: E402
import menu_data as D  # noqa: E402
import stats_lib as S  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "poster", "img", "ds_story.png")
LABS, CTL, IEDP = J.LABS, J.CTL, J.IEDP
FS_T, FS_L, FS_K = 7.2, 6.6, 6.2      # title, label, tick sizes (the poster shows this figure at about 2.3x)

fig = plt.figure(figsize=(6.6, 3.0))


def title(ax, s):
    ax.set_title(s, fontsize=FS_T, loc="left", weight="bold", color=F.INK, pad=7)


def tidy(ax):
    ax.tick_params(labelsize=FS_K)
    ax.yaxis.label.set_size(FS_L)
    for t in ax.get_xticklabels():
        t.set_fontsize(FS_K)


# a  DS fast power per mouse
hf = D.values("rootcanal|ds_hf_median|v6||")
groups = {l: F.subgroup(l) for l in LABS}
a = F.axes_in(fig, 0.5, 0.62, 0.95, 1.8)
F.dots(a, {l: hf[l] for l in LABS}, groups, ["CTL", "IED-", "IED+"], xlabels=["Control", "IED−", "IED+"],
       ylabel="DS fast power (dB)", names=("m7",))
pairs = []
for g, k in (("IED-", 1), ("IED+", 2)):
    pairs.append((0, k, S.two([hf[l] for l in CTL], [hf[l] for l in LABS if groups[l] == g])["p"]))
F.defer_brackets(a, pairs)
title(a, "DS fast power: IED+ above\nevery control, IED− below")
tidy(a)

# b  BT and IED-class events per minute, by knockout
rc = D.rc()
h = rc[rc.wf == "halo"]
rate_bt = {l: (h[h.lab == l].kind == "TZ").sum() / S.M[l]["dur_min"] for l in LABS}
rate_ied = {l: (h[h.lab == l].kind == "IED").sum() / S.M[l]["dur_min"] for l in LABS}
ctl_max = max(rate_bt[l] + rate_ied[l] for l in CTL)
b = F.axes_in(fig, 1.95, 0.62, 1.6, 1.8)
order = sorted(LABS, key=lambda l: (F.ko(l), l))
for i, l in enumerate(order):
    b.bar(i, rate_bt[l], color=F.C_PDS, width=0.72, edgecolor="white", lw=0.4)
    b.bar(i, rate_ied[l], bottom=rate_bt[l], color=F.C_IED, width=0.72, edgecolor="white", lw=0.4)
b.axhline(ctl_max, color=F.SOFT, lw=0.7, ls=":")
b.set_xticks(range(len(order)))
b.set_xticklabels(["%.0f" % F.ko(l) if F.ko(l) else "0" for l in order], fontsize=FS_K - 0.6, rotation=90)
for t, l in zip(b.get_xticklabels(), order):
    t.set_color(F.color_of(l) if F.subgroup(l) != "IED-" else "#b5508a")
b.tick_params(axis="x", length=0)
b.set_xlabel("Each mouse, % knockout", fontsize=FS_L)
b.set_ylabel("Events per minute", fontsize=FS_L)
b.set_xlim(-0.6, len(order) - 0.4)
b.text(-0.4, ctl_max + 0.04, "highest control", fontsize=FS_K - 0.8, color=F.SOFT, ha="left", va="bottom")
b.legend(handles=[Line2D([], [], ls="", marker="s", ms=5, mfc=F.C_PDS, mec="white", label="BT"),
                  Line2D([], [], ls="", marker="s", ms=5, mfc=F.C_IED, mec="white", label="IED class")],
         loc="upper left", bbox_to_anchor=(0.0, 0.88), frameon=False, fontsize=FS_K, handletextpad=0.2, borderaxespad=0.1)
title(b, "Only the five IED+ mice make BTs\nand IEDs above the control rate")
tidy(b)

# c, d  DS -> BT -> IED within the IED+ mice
med = lambda l, k, col: float(h[(h.lab == l) & (h.kind == k)][col].median())  # noqa: E731
refn = J.ref_reads("notch")
key = ("lower", "MML")
c, _v, _p = J.class_panel(fig, 3.95, 0.62, 0.9, 1.8, lambda l, k: med(l, k, "hf"), "Fast power (dB)", "")
title(c, "Fast power climbs\nfrom DS to BT to IED")
d, _v, _p = J.class_panel(fig, 5.3, 0.62, 0.9, 1.8, lambda l, k: J.fq(l, "notch", "sink", (k,) + key) / refn,
                          "Lower MML sink\n(control deepest sink = 1)", "")
title(d, "BTs: more MML current\nthan the mouse's own DS")
for ax in (c, d):
    tidy(ax)
    ax.yaxis.label.set_size(FS_L)

hs = [Line2D([], [], ls="", marker="o", ms=4.8, mfc=F.C_CTL, mec="white", label="Control"),
      Line2D([], [], ls="", marker="o", ms=4.8, mfc=F.C_NEG, mec="white", label="PTEN IED−"),
      Line2D([], [], ls="", marker="o", ms=4.8, mfc=F.C_POS, mec="white", label="PTEN IED+"),
      Line2D([], [], ls="", marker="D", ms=4.4, mfc=F.C_NEG, mec="white", label="m7 (24% KO, no IEDs)"),
      Line2D([], [], ls="", marker="o", ms=4.8, mfc=F.C_DS, mec="white", label="DS"),
      Line2D([], [], ls="", marker="o", ms=4.8, mfc=F.C_PDS, mec="white", label="BT"),
      Line2D([], [], ls="", marker="o", ms=4.8, mfc=F.C_IED, mec="white", label="IED class")]
fig.legend(handles=hs, loc="lower left", bbox_to_anchor=(0.45 / 6.6, 0.0), ncol=len(hs), frameon=False, fontsize=FS_K,
           handletextpad=0.25, columnspacing=0.9)
F.finish(fig)
fig.savefig(OUT, dpi=600)
print("saved", OUT)
