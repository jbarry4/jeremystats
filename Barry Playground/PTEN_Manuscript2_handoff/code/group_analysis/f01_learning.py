"""Report Figure 1. Learning the cue rule, and the two phenotypes.

a  Sessions to criterion by group (the old Figure 1).
b  Sessions to criterion against percent KO (the old Figure 2): the slowest learners have the
   fewest KO cells, so the dose-response is not monotonic.  The quadratic is a description of
   that shape, not a model: the mice fall in two clusters with a gap between them.
c  The two measures that separate the groups, against each other: sessions to criterion and the
   latent place preference with the cue present.  Lo mice are slow to take up the cue rule and
   keep the place; Hi mice take it up as fast as WT mice and drop the place.

Output: figures/fig01_learning.png
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS, CRIT_SAV
import numpy as np, pandas as pd, pyreadstat, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 11,
                     'axes.spines.top': False, 'axes.spines.right': False, 'axes.edgecolor': '#9a9993',
                     'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                     'axes.titlesize': 11.5, 'axes.titleweight': '600', 'axes.titlecolor': '#0b0b0b',
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb',
                     'savefig.facecolor': '#fcfcfb', 'axes.grid': True, 'grid.color': '#e9e8e3',
                     'grid.linewidth': 0.7, 'axes.axisbelow': True, 'legend.frameon': False})
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948', 'UNK': '#8a8983'}
MK = {'CTL': 'o', 'Lo': '^', 'Hi': 's', 'UNK': 'D'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
pct = {1: 5.18, 3: 24.57, 5: 27.64, 7: 24.12, 8: 3.89, 10: 9.51, 28: 20.19, 29: 22.00,
       30: 5.97, 33: 8.82, 34: 28.43}
het = {8, 10, 27, 29, 30}; iedp = {3, 5, 28, 34}

cr, _ = pyreadstat.read_sav(CRIT_SAV)
cr = cr.dropna(subset=['MouseID']); cr = cr[cr.MouseID != 6].rename(columns={'SesstoCriterion': 'y'})
cr['g'] = cr.GRP2HiLo.map({'CTL': 'CTL', 'PTEN-Lo': 'Lo', 'PTEN-Hi': 'Hi', 'PTEN-?': 'UNK'})
cr['pct'] = cr.MouseID.map(pct)
rng = np.random.default_rng(3)

fig = plt.figure(figsize=(10.6, 4.0))
gs = fig.add_gridspec(1, 3, width_ratios=[1.00, 1.05, 0.88], left=0.062, right=0.988,
                      top=0.845, bottom=0.215, wspace=0.30)

# ---------------------------------------------------------------- a: criterion by group
ax = fig.add_subplot(gs[0, 0])
grp = [('CTL', cr[cr.g == 'CTL'], COL['CTL'], 'o'), ('Lo', cr[cr.g == 'Lo'], COL['Lo'], '^'),
       ('Hi', cr[cr.g == 'Hi'], COL['Hi'], 's'), ('ALL', cr[cr.GRP == 'PTEN'], '#6b6a65', 'D')]
for i, (g, d, c, mk) in zip([0, 1, 2, 3.45], grp):
    d = d.sort_values('y'); xs = []; seen = {}
    for v in d.y:
        k = seen.get(v, 0); seen[v] = k + 1; xs.append(i + ((k + 1) // 2) * 0.07 * (1 if k % 2 else -1))
    ax.scatter(xs, d.y, s=30 if g != 'ALL' else 24, color=c, marker=mk, edgecolor='#fcfcfb',
               linewidth=0.8, alpha=0.95, zorder=3)
    m, se = d.y.mean(), d.y.sem()
    ax.errorbar(i + 0.42, m, yerr=se, fmt='_', color='#0b0b0b', ms=12, mew=1.8, capsize=3,
                elinewidth=1.2, zorder=4)
    ax.text(i + 0.66, m + (0.9 if g == 'CTL' else 0), f"{m:.1f} ± {se:.1f}", va='center',
            ha='left', fontsize=8.6, color='#0b0b0b')
wm = cr[cr.g == 'CTL'].y.mean()
ax.axhline(wm, color='#9a9993', lw=1, ls=(0, (4, 3)), zorder=1)
ax.text(4.57, wm + 0.3, 'WT mean', ha='right', va='bottom', fontsize=8, color='#52514e')
ax.axvline(3.12, color='#d9d8d2', lw=1, zorder=0)
ax.set_xticks([0, 1, 2, 3.45])
ax.set_xticklabels(['WT\nn = 18', 'Lo\nn = 5', 'Hi\nn = 6', 'All KO\nn = 13'], fontsize=9)
ax.set_xlim(-0.5, 4.6); ax.set_ylim(0, 35)
ax.set_ylabel('Sessions to criterion'); ax.grid(axis='x', visible=False)


def br(x1, x2, y, t):
    ax.plot([x1, x1, x2, x2], [y - .5, y, y, y - .5], color='#52514e', lw=1)
    ax.text((x1 + x2) / 2, y + .2, t, ha='center', va='bottom', fontsize=8.2, color='#0b0b0b')


br(0, 0.97, 29.6, 'p < 0.001'); br(1.03, 2, 29.6, 'p = 0.08'); br(0, 3.45, 32.4, 'p < 0.001')
ax.set_title('a   Sessions to criterion (mean ± SE; M6 excluded)', loc='left', fontsize=10)

# ---------------------------------------------------------------- b: criterion vs % KO
ax = fig.add_subplot(gs[0, 1])
c = cr[cr.g == 'CTL']
ax.scatter(rng.uniform(-.9, .9, len(c)), c.y, s=26, color=COL['CTL'], marker='o',
           edgecolor='#fcfcfb', linewidth=0.8, zorder=3)
for g in ['Lo', 'Hi']:
    d = cr[cr.g == g]
    ax.scatter(d.pct, d.y, s=40, color=COL[g], marker=MK[g], edgecolor='#fcfcfb', linewidth=0.8,
               zorder=3)
for _, r in cr[cr.pct.notna()].iterrows():
    tag = f"M{int(r.MouseID)}" + (' IED+' if r.MouseID in iedp else '') + (' het' if r.MouseID in het else '')
    off = {8: (-6, 5, 'right'), 1: (6, 4, 'left'), 29: (6, -3, 'left'), 28: (-6, -7, 'right'), 7: (-4, 7, 'right'), 5: (6, -6, 'left')}.get(int(r.MouseID), (6, 3, 'left'))
    ax.annotate(tag, (r.pct, r.y), xytext=off[:2], textcoords='offset points', fontsize=7,
                color='#52514e', ha=off[2])
dd = cr[cr.g.isin(['CTL', 'Lo', 'Hi'])].copy(); dd['p'] = dd.pct.fillna(0)
co = np.polyfit(dd.p, dd.y, 2); xx = np.linspace(0, 29, 200)
ax.plot(xx, np.polyval(co, xx), color='#52514e', lw=1.4, ls=(0, (5, 3)), zorder=2)
ax.axvspan(9.51, 20.19, color='#f0efec', zorder=0)
ax.text(14.85, 1.2, 'no mice\n9.5–20.2%', ha='center', va='bottom', fontsize=8, color='#52514e')
ax.set_xlabel('% granule cells Pten KO (cell layer)', fontsize=9.5)
ax.set_ylabel('Sessions to criterion')
ax.set_xlim(-2, 34); ax.set_ylim(0, 31)
ax.set_title('b   More KO does not mean slower learning', loc='left', fontsize=10)

# ---------------------------------------------------------------- c: the two phenotypes
ax = fig.add_subplot(gs[0, 2])
T = pd.read_csv(WORK + '/phase8/phase8_mouse.csv').drop_duplicates('Mouse').set_index('Mouse')
cr2 = cr.set_index('MouseID')
ax.axhline(0, color='#9a9993', lw=0.9)
for g in ['CTL', 'Lo', 'Hi']:
    for m, r in T[T.g == {'CTL': 'WT'}.get(g, g)].iterrows():
        if m not in cr2.index: continue
        ax.scatter(cr2.loc[m, 'y'], r.V_old_pull, s=40,
                   marker='D' if bool(r.IED) else MK[g], color=COL[g], edgecolor='#fcfcfb',
                   linewidth=0.8, zorder=3)
ax.set_xlabel('Sessions to criterion', fontsize=9.5)
ax.set_ylabel('Place preference with the cue\npresent (percentage points)', fontsize=9.5)
ax.set_xlim(4, 30); ax.set_ylim(-40, 50)
ax.annotate('slow to learn,\nkeeps the place', xy=(23.5, 30), fontsize=8, color='#52514e',
            ha='center')
ax.annotate('learns fast,\ndrops the place', xy=(10.5, -32), fontsize=8, color='#52514e',
            ha='center')
ax.set_title('c   The two phenotypes', loc='left', fontsize=10)

fig.legend(handles=[Line2D([], [], marker=MK[g], ls='', color=COL[g], ms=6, label=LAB[g])
                    for g in ['CTL', 'Lo', 'Hi']] +
                   [Line2D([], [], marker='D', ls='', color='#6b6a65', ms=6, label='IED+ (panel c) / all Pten KO (panel a)'),
                    Line2D([], [], color='#52514e', lw=1.4, ls=(0, (5, 3)), label='quadratic fit, WT at 0%')],
           loc='lower center', bbox_to_anchor=(0.5, -0.008), ncol=5, fontsize=8.6,
           handletextpad=0.4, columnspacing=1.6)
os.makedirs(FIGS, exist_ok=True)
out = os.path.join(FIGS, 'fig01_learning.png')
fig.savefig(out, dpi=200); print('wrote', out)
