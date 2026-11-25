"""Shared bits for the confound and rescue supplements (2026-11-24)."""
import os
import pickle

import numpy as np
from matplotlib.lines import Line2D

import figlib_aa as F
import stats_lib as S

CR = pickle.load(open(os.path.join(F.HERE, "cr.pkl"), "rb"))
PM, OMR, F24 = CR["PM"], CR["OMR"], CR["F24"]
ML = sorted(F.MICE, key=int)
RED_BG = "#fdeeee"
RED_TX = "#c0392b"
G4 = ["WT young", "Hom young", "WT old", "Hom old"]
G4L = ["WT\nyoung", "Hom\nyoung", "WT\nold", "Hom\nold"]


def grp(m):
    return "%s %s" % (F.geno(m), F.MICE[m]["age_group"])


def red(ax, note="floor speed differs between these groups"):
    """Faint red background: this comparison is confounded with floor speed."""
    ax.set_facecolor(RED_BG)
    if note:
        ax.text(0.99, 0.015, note, transform=ax.transAxes, fontsize=5.0, color=RED_TX, ha="right", va="bottom", style="italic",
                zorder=9)


def red_legend(fig, x, y):
    W, H = fig.get_size_inches()
    fig.patches.append(__import__("matplotlib").patches.Rectangle(((x) / W, 1 - (y + 0.12) / H), 0.22 / W, 0.12 / H,
                                                                     transform=fig.transFigure, facecolor=RED_BG,
                                                                     edgecolor="#e3b5b5", lw=0.5))
    fig.text((x + 0.28) / W, 1 - (y + 0.06) / H, "red background = the groups compared ran at different floor speeds",
             fontsize=6.0, color=RED_TX, va="center", style="italic")


def group_dots(ax, v, groups=G4, labels=G4L, pairs=((0, 1), (2, 3)), extra_pairs=(), ylabel="", seed=3, size=16, names=False):
    """One dot per mouse in each genotype x age group, median bar, brackets for P < 0.05 (generous two-group tests)."""
    rng = np.random.RandomState(seed)
    allv = []
    for k, g in enumerate(groups):
        ms = [m for m in ML if grp(m) == g and m in v and np.isfinite(v[m])]
        vs = np.array([v[m] for m in ms])
        allv += list(vs)
        if vs.size:
            ax.plot([k - 0.3, k + 0.3], [np.median(vs)] * 2, color=F.INK, lw=1.2, zorder=3, solid_capstyle="butt")
        for m in ms:
            F.scatter_mouse(ax, k + (rng.rand() - 0.5) * 0.36, v[m], m, size=size)
            if names:
                pass
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(labels)
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.6, len(groups) - 0.4)
    ax.set_ylabel(ylabel)
    items, ps = [], {}
    for a, b in list(pairs) + list(extra_pairs):
        va = [v[m] for m in ML if grp(m) == groups[a] and m in v and np.isfinite(v[m])]
        vb = [v[m] for m in ML if grp(m) == groups[b] and m in v and np.isfinite(v[m])]
        p = S.two(va, vb)["p"]
        ps[(a, b)] = p
        items.append((a, b, p))
    top = max(allv) if allv else 0
    F.brackets(ax, items, top)
    return ps


def genotype_legend(fig, x, y, extra=True):
    F.legend_mice(fig, x, y, extra=extra, speed=False)


def pfmt(p):
    return F.pstr(p).replace("P ", "P ")


FOOT_CONF = "KCNT1 active avoidance · floor speed as a confound, a supplement to the story menu · exploratory, P uncorrected · 2026-11-24"
FOOT_RESC = "KCNT1 active avoidance · what can be rescued, a supplement to the story menu · exploratory, P uncorrected · 2026-11-24"
SPEED_LINE = Line2D
