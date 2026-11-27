"""Step 18. What the mice search: pause time near each kind of place (report Figure 38).

Figure 37 asked how much the mice pause and, afterwards, how far those pauses were from the
current goal.  This script asks a different question: which *places* the pauses are at.

Each of the four zones was the goal of one phase (zone k is the goal of phase k + 6), so at any
hidden phase the zones divide into three kinds — the current goal, the former goals, and the
zones that have never yet been the goal.  The number of former goals therefore grows 0, 1, 2, 3
across phases 7 to 10, and with it the number of places a mouse has to hold in mind and rule out.
Every pause is assigned to the nearest kind of zone within 2.5 zone radii (current first, then
former, then never-used), and pauses near none of them are counted separately.

Pauses are those of s11: 1.2 to 10 s below 3 cm/s, with the wall annulus (radius above 0.8 of the
fitted arena radius) excluded by that definition, so none of these measures contain thigmotaxis.

Both conditions are drawn: the hidden sessions, where the set has to be held in mind, and the cued
sessions, where the beacon marks the current goal and there is no need to work through the others.

Reads WORK/approach/pauses_d.pkl.  Writes WORK/approach/pauses_cat.pkl, search_sets.csv,
search_sets_stats.txt and figures/fig38_search_sets.png.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu as mw, linregress

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9,
                     'axes.linewidth': 0.7, 'figure.facecolor': '#fcfcfb',
                     'savefig.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
NEAR = 2.5          # zone radii: how close a pause must be to count as "at" a zone
PH = [7., 8., 9., 10.]

G = pd.read_pickle(WORK + '/probe.pkl').drop_duplicates('MouseID').set_index('MouseID').G3
P = pd.read_pickle(WORK + '/approach/pauses_d.pkl')
P['G3'] = P.Mouse.map(G)
P = P[P.G3.isin(COL)].copy()

D = P[['d1', 'd2', 'd3', 'd4']].values
cur = P.Phase.values.astype(int) - 6         # zone k was the goal of phase k + 6
cat = np.full(len(P), 'open', dtype=object)
for i in range(len(P)):
    c = cur[i]
    former = [z for z in range(1, 5) if z < c]
    never = [z for z in range(1, 5) if z > c]
    if D[i, c - 1] < NEAR: cat[i] = 'current'
    elif former and min(D[i, z - 1] for z in former) < NEAR: cat[i] = 'former'
    elif never and min(D[i, z - 1] for z in never) < NEAR: cat[i] = 'never'
P['cat'] = cat
P.to_pickle(WORK + '/approach/pauses_cat.pkl')

CATS = [('former', 'Former goals\n(the set to rule out)', (0, 190)),
        ('never', 'Zones never used\n(no reason to check)', (0, 190)),
        ('current', 'The current goal', (0, 110)),
        ('open', 'Away from every zone', (0, 110))]
full = P.groupby(['G3', 'Mouse', 'Phase', 'Cond']).size().reset_index()[['G3', 'Mouse', 'Phase', 'Cond']]

fig, axes = plt.subplots(2, 4, figsize=(8.6, 5.4))
fig.subplots_adjust(left=0.095, right=0.995, top=0.84, bottom=0.095, wspace=0.42, hspace=0.52)
rng = np.random.default_rng(5)
rows = []; lines = []
for ri, (cond, clab) in enumerate([('H', 'HIDDEN goal'), ('V', 'CUED goal')]):
    for ax, (c, ttl, ylim) in zip(axes[ri], CATS):
        t = P[P.cat == c].groupby(['G3', 'Mouse', 'Phase', 'Cond']).dur.sum().reset_index()
        t = full.merge(t, on=['G3', 'Mouse', 'Phase', 'Cond'], how='left').fillna({'dur': 0})
        if ri == 0:
            t2 = t.copy(); t2['cat'] = c; rows.append(t2)
        t = t[t.Cond == cond]
        for g in ['CTL', 'Lo', 'Hi']:
            mu = []; se = []
            for ph in PH:
                v = t[(t.G3 == g) & (t.Phase == ph)].dur.values
                mu.append(v.mean()); se.append(v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0)
                ax.scatter(PH.index(ph) + rng.uniform(-0.14, 0.14, len(v)), v, s=6, color=COL[g],
                           alpha=0.30, edgecolor='none', zorder=2)
            ax.errorbar(range(4), mu, yerr=se, color=COL[g], lw=1.9, marker='o', ms=4.2,
                        mec='#fcfcfb', mew=0.6, capsize=2, elinewidth=0.9, zorder=4, label=LAB[g])
            lines.append(f"{cond} {c:8s} {g:4s} " + ' '.join(f"{m:7.2f}" for m in mu))
        sl = {g: [linregress(x.index.values.astype(float), x.values).slope
                  for m, gg in t[t.G3 == g].groupby('Mouse')
                  for x in [gg.set_index('Phase').dur] if len(x) >= 3] for g in ['CTL', 'Lo', 'Hi']}
        pv = mw(sl['Hi'], sl['CTL'], alternative='two-sided')[1]
        lines.append(f"{cond} {c:8s} slopes WT {np.mean(sl['CTL']):+.2f}  Lo {np.mean(sl['Lo']):+.2f}  "
                     f"Hi {np.mean(sl['Hi']):+.2f}  Hi vs WT group x phase p={pv:.4f}")
        ax.set_ylim(ylim[0] - (ylim[1] - ylim[0]) * 0.22, ylim[1])
        ax.text(0.5, 0.095, f"slope WT {np.mean(sl['CTL']):+.1f}, Hi {np.mean(sl['Hi']):+.1f}",
                transform=ax.transAxes, ha='center', va='bottom', fontsize=6.5, color=MUT)
        ax.text(0.5, 0.005, f'g $\times$ ph p = {pv:.3f}', transform=ax.transAxes, ha='center',
                va='bottom', fontsize=7.2, color=(INK if pv < 0.05 else MUT),
                fontweight=('bold' if pv < 0.05 else 'normal'))
        ax.set_xticks(range(4)); ax.set_xticklabels(['7', '8', '9', '10'], fontsize=7.8)
        ax.set_xlim(-0.45, 3.45); ax.set_xlabel('Phase', fontsize=7.8, color=MUT)
        ax.set_title(ttl, fontsize=8.2, color=INK, fontweight='semibold', pad=3)
        for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
        for sp in ['left', 'bottom']: ax.spines[sp].set_color('#9a9993')
        ax.tick_params(colors=MUT, labelsize=7.4); ax.grid(axis='y', color=GRID, lw=0.6); ax.set_axisbelow(True)
    axes[ri][0].set_ylabel(f'{clab}\nPause time per session (s)', fontsize=8, color=MUT)
axes[0][0].legend(frameon=False, fontsize=6.8, loc='upper left', bbox_to_anchor=(-0.03, 1.03), labelspacing=0.2)
for i, n in enumerate(['0', '1', '2', '3']):
    for ri in (0, 1): axes[ri][0].text(i, 186, n, ha='center', fontsize=6.6, color=MUT)
axes[0][0].text(-0.42, 186, 'n former:', ha='left', fontsize=6.2, color=MUT)
fig.suptitle('What the mice search, hidden vs cued: pause time near each kind of place',
             fontsize=11, y=0.975, color=INK, fontweight='semibold')
os.makedirs(FIGS, exist_ok=True)
fig.savefig(os.path.join(FIGS, 'fig38_search_sets.png'), dpi=200)

out = pd.concat(rows)[['cat', 'G3', 'Mouse', 'Phase', 'Cond', 'dur']].rename(
    columns={'cat': 'Place', 'G3': 'Group', 'Cond': 'Condition', 'dur': 'Pause time (s)'})
out.to_csv(os.path.join(WORK, 'approach', 'search_sets.csv'), index=False)
with open(os.path.join(WORK, 'approach', 'search_sets_stats.txt'), 'w') as f:
    f.write('Pause time per probe session by kind of place (phases 7, 8, 9, 10), hidden (H) and cued (V)\n'
            f'a pause counts as "at" a zone within {NEAR} zone radii; wall pauses already excluded by s11\n\n')
    f.write('\n'.join(lines) + '\n')
print('wrote fig38 and search_sets.csv')
