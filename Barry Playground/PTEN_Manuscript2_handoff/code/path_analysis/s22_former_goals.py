"""Step 22. The set to rule out: pause time at former goals as the set grows, hidden and cued.

This is the two panels worth keeping from the full search-set figure (s18).  Across phases 7 to 10
the number of former goals in play grows 0, 1, 2, 3, so a mouse that works through the candidate
places should spend more and more time at them.  WT and Lo mice do; Hi mice do not, and the cued
sessions show the same mice doing it normally when the goal is marked.

Reads WORK/approach/pauses_cat.pkl (s18).  Output: figures/fig17_former_goals.png
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import mannwhitneyu as mw, linregress

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9,
                     'figure.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
MK = {'CTL': 'o', 'Lo': '^', 'Hi': 's'}
DX = {'CTL': -0.085, 'Lo': 0.0, 'Hi': 0.085}
PH = [7.0, 8.0, 9.0, 10.0]

P = pd.read_pickle(WORK + '/approach/pauses_cat.pkl')
full = P.groupby(['G3', 'Mouse', 'Phase', 'Cond']).size().reset_index()[['G3', 'Mouse', 'Phase', 'Cond']]
t = P[P.cat == 'former'].groupby(['G3', 'Mouse', 'Phase', 'Cond']).dur.sum().reset_index()
t = full.merge(t, on=['G3', 'Mouse', 'Phase', 'Cond'], how='left').fillna({'dur': 0})

fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.3))
fig.subplots_adjust(left=0.145, right=0.985, top=0.650, bottom=0.145, wspace=0.26)
rng = np.random.default_rng(5)
YLIM = (0, 200)
for ax, (cond, clab) in zip(axes, [('H', 'Goal hidden'), ('V', 'Goal cued')]):
    d = t[t.Cond == cond]
    for g in ['CTL', 'Lo', 'Hi']:
        mu = []; se = []
        for ph in PH:
            v = d[(d.Phase == ph) & (d.G3 == g)].dur.values
            mu.append(v.mean()); se.append(v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0)
            ax.scatter(PH.index(ph) + DX[g] + rng.uniform(-0.05, 0.05, len(v)), v, s=6,
                       color=COL[g], alpha=0.30, edgecolor='none', zorder=2)
        ax.errorbar(np.arange(4) + DX[g], mu, yerr=se, color=COL[g], lw=1.9, marker=MK[g], ms=4.0,
                    mec='#fcfcfb', mew=0.6, capsize=2, elinewidth=0.9, zorder=4, label=LAB[g])
    sl = {g: [linregress(x.index.values.astype(float), x.values).slope
              for m, gg in d[d.G3 == g].groupby('Mouse')
              for x in [gg.set_index('Phase').dur] if len(x) >= 3] for g in ['CTL', 'Lo', 'Hi']}
    pv = mw(sl['Hi'], sl['CTL'], alternative='two-sided')[1]
    ax.set_ylim(YLIM[0] - (YLIM[1] - YLIM[0]) * 0.28, YLIM[1])
    ax.text(0.5, 0.085, 'slope per phase   WT %+.1f   Lo %+.1f   Hi %+.1f' %
            (np.mean(sl['CTL']), np.mean(sl['Lo']), np.mean(sl['Hi'])), transform=ax.transAxes,
            ha='center', va='bottom', fontsize=6.6, color=MUT)
    ax.text(0.5, 0.005, 'group $\\times$ phase, Hi vs WT  p = %.3f' % pv, transform=ax.transAxes,
            ha='center', va='bottom', fontsize=7.2, color=(INK if pv < 0.05 else MUT),
            fontweight=('bold' if pv < 0.05 else 'normal'))
    for i, ph in enumerate(PH):
        x1 = d[(d.Phase == ph) & (d.G3 == 'Hi')].dur
        x2 = d[(d.Phase == ph) & (d.G3 == 'CTL')].dur
        q = mw(x1, x2, alternative='two-sided')[1]
        if q < 0.05:
            ax.annotate(('%.3f' % q).lstrip('0'), xy=(i, 1.17), xycoords=('data', 'axes fraction'),
                        ha='center', va='bottom', fontsize=6.6, color=INK, annotation_clip=False)
    ax.set_xticks(range(4)); ax.set_xticklabels(['7', '8', '9', '10'], fontsize=8)
    ax.set_xlim(-0.45, 3.45); ax.set_xlabel('Phase', fontsize=8.2, color=MUT)
    ax.set_title(clab, fontsize=9.2, color=INK, fontweight='semibold', pad=26)
    for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
    for sp in ['left', 'bottom']: ax.spines[sp].set_color('#9a9993')
    ax.spines['left'].set_bounds(*YLIM)
    ax.set_yticks([q for q in ax.get_yticks() if YLIM[0] - 1e-9 <= q <= YLIM[1]])
    ax.tick_params(colors=MUT, labelsize=7.8); ax.grid(axis='y', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for i, n in enumerate(['0', '1', '2', '3']):
        ax.annotate(n, xy=(i, 1.075), xycoords=('data', 'axes fraction'), ha='center',
                    fontsize=7.0, color=MUT, annotation_clip=False)
    if cond == 'H':
        ax.annotate('former goals:', xy=(-0.02, 1.075), xycoords='axes fraction',
                    ha='right', fontsize=6.4, color=MUT, annotation_clip=False)
axes[0].set_ylabel('pause time at former goals\nper session (s)', fontsize=8.2, color=MUT)
fig.legend(handles=[Line2D([], [], color=COL[g], lw=1.9, marker=MK[g], ms=4, label=LAB[g])
                    for g in ['CTL', 'Lo', 'Hi']],
           loc='upper center', bbox_to_anchor=(0.5, 0.915), ncol=3, frameon=False, fontsize=8)
fig.suptitle('The set to rule out: do they work through the places that used to pay?',
             fontsize=10.5, y=0.975, color=INK, fontweight='semibold')
os.makedirs(FIGS, exist_ok=True)
out = os.path.join(FIGS, 'fig17_former_goals.png')
fig.savefig(out, dpi=200); print('wrote', out)
for cond in ['H', 'V']:
    d = t[t.Cond == cond]
    for g in ['CTL', 'Lo', 'Hi']:
        print(cond, g, [round(d[(d.Phase == ph) & (d.G3 == g)].dur.mean(), 1) for ph in PH])
