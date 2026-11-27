"""Step 19. Does the deficit scale with the load? Every per-rotation slope in one place.

The hidden probes run 7, 8, 9, 10, and at each rotation the goal moves to a zone that has not
been used before, so the number of former goals a mouse must hold and rule out grows 0, 1, 2, 3.
Several measures in this report have a slope across those four phases.  This script fits all of
them the same way — least squares per mouse across phases 7 to 10, hidden sessions — and puts
them on one axis.

Slopes are standardised by the SD of the per-mouse slopes for that measure, so measures in
different units can be compared; the raw slopes are printed in the stats file and carried in the
workbook.  Groups are compared on the unstandardised slopes with a two-sided Mann-Whitney, which
is the group x phase test used throughout.

Output: figures/fig_load_slopes.png, WORK/approach/load_slopes.csv, load_slopes_stats.txt
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import linregress, mannwhitneyu as mw

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'DejaVu Sans'], 'font.size': 9,
                     'axes.linewidth': 0.7, 'figure.facecolor': '#fcfcfb',
                     'savefig.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
GRP = ['CTL', 'Lo', 'Hi']

G = pd.read_pickle(WORK + '/probe.pkl').drop_duplicates('MouseID').set_index('MouseID').G3

def slopes(df, val):
    return {g: np.array([linregress(x.index.values.astype(float), x.values).slope
                         for m, gg in df[df.G3 == g].groupby('Mouse')
                         for x in [gg.groupby('Phase')[val].mean()] if len(x) >= 3]) for g in GRP}

p = pd.read_pickle(WORK + '/probe.pkl').rename(columns={'MouseID': 'Mouse'})
p['G3'] = p.Mouse.map(G)
h = p[(p.Condition == 'H') & p.Phase.isin([7, 8, 9, 10]) & p.G3.isin(GRP)]
PC = pd.read_pickle(WORK + '/approach/pauses_cat.pkl'); PC['G3'] = PC.Mouse.map(G)
PC = PC[(PC.Cond == 'H') & PC.G3.isin(GRP)]
full = PC.groupby(['G3', 'Mouse', 'Phase']).size().reset_index()[['G3', 'Mouse', 'Phase']]
def pausecat(cat=None):
    t = (PC if cat is None else PC[PC.cat == cat]).groupby(['G3', 'Mouse', 'Phase']).dur.sum().reset_index()
    return full.merge(t, how='left').fillna({'dur': 0})
rows = [('Pause time at former goals', 's per phase', slopes(pausecat('former'), 'dur')),
        ('Total pause time', 's per phase', slopes(pausecat(), 'dur'))]
A = pd.read_pickle(WORK + '/approach/arrival_dir.pkl'); A['G3'] = A.Mouse.map(G)
A = A[A.directed & (A.Cond == 'H') & A.G3.isin(GRP)].copy()
bnd = lambda q, lo, hi: np.nanmean(q[int((lo + 3) * 30):int((hi + 3) * 30) + 1])
A['sl'] = A.prof.apply(lambda q: bnd(q, 0, 1.2)) / A.prof.apply(lambda q: bnd(q, -1.5, -0.5))
rows += [('Slowing ratio at the goal', 'per phase', slopes(A, 'sl')),
         ('Rewards per session', 'per phase', slopes(h, 'NumRewards')),
         ('Time in the goal zone', 'fraction per phase', slopes(h, 'PGoalTime')),
         ('Pause time at never-used zones', 's per phase', slopes(pausecat('never'), 'dur')),
         ('Pause time at the current goal', 's per phase', slopes(pausecat('current'), 'dur'))]

recs = []
for lab, unit, s in rows:
    pv = mw(s['Hi'], s['CTL'], alternative='two-sided')[1]
    sd = np.std(np.concatenate([s[g] for g in GRP]), ddof=1)
    recs.append(dict(label=lab, unit=unit, p=pv, sd=sd, s=s))
recs.sort(key=lambda r: r['p'])

fig, ax = plt.subplots(figsize=(7.2, 4.1))
fig.subplots_adjust(left=0.30, right=0.86, top=0.855, bottom=0.215)
for i, r in enumerate(recs):
    y = len(recs) - 1 - i
    for k, g in enumerate(GRP):
        v = r['s'][g] / r['sd']
        off = (k - 1) * 0.22
        ax.errorbar(v.mean(), y + off, xerr=v.std(ddof=1) / np.sqrt(len(v)), fmt='o', ms=5,
                    color=COL[g], mec='#fcfcfb', mew=0.6, capsize=2.5, elinewidth=1.1, zorder=3)
    ax.text(1.015, y, f"p = {r['p']:.3f}", transform=ax.get_yaxis_transform(), va='center',
            fontsize=7.6, color=(INK if r['p'] < 0.05 else MUT),
            fontweight=('bold' if r['p'] < 0.05 else 'normal'))
    if i < len(recs) - 1:
        ax.axhline(y - 0.5, color=GRID, lw=0.6, zorder=0)
ax.axvline(0, color='#9a9993', lw=0.9, ls=':', zorder=1)
ax.set_yticks(range(len(recs)))
ax.set_yticklabels([r['label'] for r in reversed(recs)], fontsize=8.2)
ax.set_ylim(-0.6, len(recs) - 0.4)
ax.set_xlabel('Change per rotation (SD of the per-mouse slopes)', fontsize=8.4, color=MUT)
for s_ in ['top', 'right']: ax.spines[s_].set_visible(False)
for s_ in ['left', 'bottom']: ax.spines[s_].set_color('#9a9993')
ax.tick_params(colors=MUT, labelsize=7.8); ax.grid(axis='x', color=GRID, lw=0.6); ax.set_axisbelow(True)
ax.legend(handles=[Line2D([], [], marker='o', ls='', ms=5, color=COL[g], label=LAB[g]) for g in GRP],
          frameon=False, fontsize=7.6, loc='upper center', bbox_to_anchor=(0.5, -0.135), ncol=3,
          columnspacing=1.6, handletextpad=0.3)
fig.suptitle('Every measure that has a slope across the four hidden rotations',
             fontsize=11, y=0.965, color=INK, fontweight='semibold')
ax.text(0.5, 1.045, 'p values are Hi vs WT on the unstandardised slopes (Mann-Whitney)',
        transform=ax.transAxes, ha='center', fontsize=7.4, color=MUT)
os.makedirs(FIGS, exist_ok=True)
fig.savefig(os.path.join(FIGS, 'fig_load_slopes.png'), dpi=200)

out = []
for r in recs:
    for g in GRP:
        for v in r['s'][g]:
            out.append(dict(Measure=r['label'], Unit=r['unit'], Group=g, Slope=round(float(v), 4)))
pd.DataFrame(out).to_csv(os.path.join(WORK, 'approach', 'load_slopes.csv'), index=False)
with open(os.path.join(WORK, 'approach', 'load_slopes_stats.txt'), 'w') as f:
    f.write('Per-mouse least-squares slope across hidden phases 7-10, by measure\n\n')
    f.write(f"{'measure':34s}{'unit':20s}{'WT':>9s}{'Lo':>9s}{'Hi':>9s}{'Hi vs WT':>10s}\n")
    for r in recs:
        f.write(f"{r['label']:34s}{r['unit']:20s}" +
                ''.join(f"{r['s'][g].mean():+9.3f}" for g in GRP) + f"{r['p']:10.4f}\n")
print('wrote fig_load_slopes and load_slopes.csv')
