"""Report Figure 4. Does performance change with each goal rotation?

Each mouse's least-squares slope across phases 7 to 10, one point per mouse, with the group mean
+- SE and its test against zero.  Top row: goal hidden.  Bottom row: goal cued, the control - if a
group's hidden slope is a rotation effect rather than a drift over days, the cued slope should be
flat.  Only the test against zero is shown, which is the question the panel asks.

Reads WORK/probe.pkl.  Output: figures/fig04_change_per_phase.png
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy import stats

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 10,
                     'axes.spines.top': False, 'axes.spines.right': False, 'axes.edgecolor': '#9a9993',
                     'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb',
                     'savefig.facecolor': '#fcfcfb', 'axes.grid': True, 'grid.color': '#e9e8e3',
                     'grid.linewidth': 0.7, 'axes.axisbelow': True, 'legend.frameon': False})
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
MK = {'CTL': 'o', 'Lo': '^', 'Hi': 's'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
V = [('NumRewards', 'Rewards', 'rewards'), ('ReRatio', 'Rewards per entrance', 'ratio'),
     ('PGoalTime', 'Proportion time in goal', 'proportion'),
     ('MeanTargSpeed', 'Mean target speed', 'cm/s')]

df = pd.read_pickle(WORK + '/probe.pkl'); df = df[df.G3 != 'UNK']
fp = lambda p: 'p < .001' if p < .001 else ('p = %.3f' % p).replace('0.', '.')


def fm(m):
    if abs(m) < 5e-5: return '0.00'
    return '%+.2f' % m if abs(m) >= 0.1 else ('%+.3f' % m if abs(m) >= 0.01 else '%+.4f' % m)


def slopes(cond, v):
    out = {}
    for g in ['CTL', 'Lo', 'Hi']:
        vals = []
        for m, q in df[(df.Condition == cond) & (df.G3 == g)].groupby('MouseID'):
            a = q.groupby('Phase')[v].mean()
            a = a[a.index.isin([7, 8, 9, 10])]
            if len(a) >= 3:
                vals.append(stats.linregress(a.index.values.astype(float), a.values).slope)
        out[g] = np.array(vals)
    return out


fig, axs = plt.subplots(2, 4, figsize=(11.0, 5.8))
fig.subplots_adjust(left=0.065, right=0.988, top=0.820, bottom=0.085, hspace=0.62, wspace=0.34)
rng = np.random.default_rng(4)
for r, (cond, clab) in enumerate([('H', 'Goal hidden'), ('V', 'Goal cued (control)')]):
    for j, (v, lab, unit) in enumerate(V):
        ax = axs[r, j]; sl = slopes(cond, v)
        allv = np.r_[sl['CTL'], sl['Lo'], sl['Hi']]
        lo, hi = allv.min(), allv.max(); span = hi - lo
        ax.axhline(0, color='#52514e', lw=1, zorder=1)
        for i, g in enumerate(['CTL', 'Lo', 'Hi']):
            y = sl[g]
            ax.scatter(i - 0.14 + rng.uniform(-.09, .09, len(y)), y, s=20, color=COL[g],
                       marker=MK[g], edgecolor='#fcfcfb', linewidth=0.7, alpha=0.9, zorder=3)
            m, se = y.mean(), stats.sem(y)
            ax.errorbar(i + 0.22, m, yerr=se, fmt='_', color='#0b0b0b', ms=11, mew=1.6,
                        capsize=3, elinewidth=1.1, zorder=4)
            p0 = stats.ttest_1samp(y, 0).pvalue
            ax.text(i, lo - span * 0.19, fm(m), ha='center', va='top', fontsize=8,
                    color='#0b0b0b', fontweight='600')
            ax.text(i, lo - span * 0.33, fp(p0), ha='center', va='top', fontsize=7.6,
                    color='#0b0b0b' if p0 < .05 else '#52514e', fontweight='600' if p0 < .05 else '400')
        ax.set_ylim(lo - span * 0.50, hi + span * 0.16); ax.set_xlim(-.6, 2.6)
        ax.set_xticks([0, 1, 2]); ax.set_xticklabels(['WT', 'Lo', 'Hi'], fontsize=8.5)
        ax.tick_params(labelsize=8.5); ax.grid(axis='x', visible=False)
        ax.set_title(lab, loc='left', fontsize=9.5, fontweight='600', color='#0b0b0b', pad=4)
        ax.set_ylabel('%s per phase' % unit, fontsize=8.5)
    axs[r, 0].annotate(clab, xy=(-0.30, 0.5), xycoords='axes fraction', rotation=90, ha='center',
                       va='center', fontsize=10.5, fontweight='600', color='#0b0b0b')
fig.legend(handles=[Line2D([], [], marker=MK[g], ls='', color=COL[g], ms=6, label=LAB[g])
                    for g in ['CTL', 'Lo', 'Hi']],
           loc='upper right', bbox_to_anchor=(0.988, 0.935), ncol=3, fontsize=9)
fig.suptitle('Change per phase across the four rotations (slope per mouse, mean ± SE, test vs zero)',
             x=0.008, ha='left', fontsize=12, fontweight='600', color='#0b0b0b', y=0.975)
os.makedirs(FIGS, exist_ok=True)
out = os.path.join(FIGS, 'fig04_change_per_phase.png')
fig.savefig(out, dpi=200); print('wrote', out)
for cond in ['H', 'V']:
    for v, lab, _ in V:
        sl = slopes(cond, v)
        print(cond, '%-14s' % v, {g: (round(float(sl[g].mean()), 4),
                                      round(float(stats.ttest_1samp(sl[g], 0).pvalue), 4)) for g in sl})
