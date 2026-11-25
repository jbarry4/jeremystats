"""Braking on approach: the Whishaw test, cue present and cue removed.

Whishaw, Cassel and Jarrard (1995, J Neurosci 15:5779) treat deceleration on approach as the sign
that an animal expects the goal at a place; their fimbria-fornix rats decelerated at the same
distance from the vanished platform as controls, which is how they concluded that those rats knew
where it was.  Three event-based measures apply that test here.  The cued session is the control
and is plotted first in every panel.

a  Braking events at the current goal per 10 m of off-wall path, each mouse joined between
   conditions.
b  Proportion of directed runs that contain any braking.
c  Distance from the goal at which a braking run first fell below 70% of its approach maximum,
   over the runs that braked.

The shape of the approach itself is not shown here because it does not differ: with each run
scaled to its own approach maximum, a permutation test across the whole distance profile with
max-statistic correction gives p = 0.53, and the within-animal hidden-minus-cued profile gives
p = 0.83.  That null is the point, and it is reported in the text: the approach is normal and the
difference is at arrival.

Output: WORK/sumfig/nf4_arrival.png
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
import ex_core as C
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import mannwhitneyu as mw, ttest_rel

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9,
                     'figure.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
G = C.groups()
ied = pd.read_csv(C.WORK + '/phase8/phase8_mouse.csv').drop_duplicates('Mouse').set_index('Mouse').IED
mk = lambda i: 'D' if bool(ied.get(i, False)) else 'o'

ev = pd.read_csv(C.WORK + '/approach/braking_events.csv')
rb = pd.read_csv(C.WORK + '/approach/braking_runs.csv')
rate = {}
for cond in ['V', 'H']:
    e = ev[(ev.Phase == 10) & (ev.Cond == cond)]
    met = e[e.cat == '__metres__'].drop_duplicates('Mouse').set_index('Mouse').d_goal
    rate[cond] = e[e.cat == 'current'].groupby('Mouse').size().reindex(met.index).fillna(0) / met * 10
RATE = pd.DataFrame(rate)
q = rb[rb.Phase == 10]
FRAC = (q.groupby(['Mouse', 'Cond']).braked.mean() * 100).unstack()
DIST = q[q.braked].groupby(['Mouse', 'Cond']).brake_dist.mean().unstack()

fig = plt.figure(figsize=(7.0, 3.5))
PAN = [(RATE, 'events per 10 m of path', 'a   Braking at the goal', (0, 23), 0.085),
       (FRAC, 'runs with any braking (%)', 'b   Runs with a slowdown', (0, 108), 0.415),
       (DIST, 'distance from the goal (cm)', 'c   Where it starts', (0, 22), 0.745)]
for T, ylab, ttl, ylim, x0 in PAN:
    ax = fig.add_axes([x0, 0.215, 0.225, 0.575])
    dd = {}
    for gi, g in enumerate(['CTL', 'Lo', 'Hi']):
        mm = [i for i in T.index if G.get(i) == g and np.isfinite(T.loc[i, 'V']) and np.isfinite(T.loc[i, 'H'])]
        v = np.array([T.loc[i, 'V'] for i in mm]); hh = np.array([T.loc[i, 'H'] for i in mm])
        dd[g] = hh - v
        xs = [gi * 2.4 + 0.0, gi * 2.4 + 0.85]
        for i, a, b in zip(mm, v, hh):
            ax.plot(xs, [a, b], color=C.COL[g], lw=0.6, alpha=0.40, zorder=2)
            ax.scatter(xs, [a, b], s=13, marker=mk(i), color=C.COL[g], lw=0, alpha=0.75, zorder=3)
        ax.plot(xs, [v.mean(), hh.mean()], color=C.COL[g], lw=2.4, zorder=4, solid_capstyle='round')
        for x, m_, s_ in [(xs[0], v.mean(), v.std(ddof=1) / np.sqrt(len(v))),
                          (xs[1], hh.mean(), hh.std(ddof=1) / np.sqrt(len(hh)))]:
            ax.errorbar(x, m_, s_, color=C.COL[g], lw=1.4, capsize=3, zorder=5)
        p = ttest_rel(v, hh).pvalue
        ax.text(gi * 2.4 + 0.42, ylim[1] * 0.045, ('%.3f' % p).lstrip('0') if p >= 0.001 else '<.001',
                ha='center', fontsize=6.8, color=INK if p < 0.05 else MUT)
    pv = mw(dd['Hi'], dd['CTL'], alternative='two-sided').pvalue
    ax.set_xticks([gi * 2.4 + 0.42 for gi in range(3)])
    ax.set_xticklabels(['WT', 'Lo', 'Hi'], fontsize=8)
    ax.set_xlim(-0.55, 5.8); ax.set_ylim(*ylim)
    ax.set_ylabel(ylab, fontsize=7.8)
    ax.set_title(ttl, fontsize=8.8, loc='left', pad=13)
    ax.text(0.0, 1.015, 'change, Hi vs WT  p = %s' % ('%.3f' % pv).lstrip('0'),
            transform=ax.transAxes, fontsize=7.2, va='bottom',
            color=INK if pv < 0.05 else MUT)
    for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)

fig.text(0.5, 0.055, 'each pair is one mouse: cue present on the left, cue removed on the right; '
         'p beneath is the paired t-test', ha='center', fontsize=7.2, color=MUT)
fig.legend(handles=[Line2D([], [], marker='D', ls='', color='#8c8c8c', ms=5, label='IED+'),
                    Line2D([], [], marker='o', ls='', color='#8c8c8c', ms=5, label='IED− or not recorded')],
           loc='lower center', bbox_to_anchor=(0.5, -0.005), ncol=2, frameon=False, fontsize=7.2,
           handletextpad=0.4, columnspacing=1.6)
os.makedirs(C.FIGS, exist_ok=True)
fig.savefig(os.path.join(C.FIGS, 'nf4_arrival.png'), dpi=200)
print('saved')
for T, lab in [(RATE, 'rate per 10 m'), (FRAC, 'runs braked %'), (DIST, 'brake distance cm')]:
    for g in ['CTL', 'Lo', 'Hi']:
        mm = [i for i in T.index if G.get(i) == g and np.isfinite(T.loc[i, 'V']) and np.isfinite(T.loc[i, 'H'])]
        v = np.array([T.loc[i, 'V'] for i in mm]); hh = np.array([T.loc[i, 'H'] for i in mm])
        print('%-18s %-4s cued %6.2f  hidden %6.2f  change %+6.2f  paired p %.3f' %
              (lab, g, v.mean(), hh.mean(), (hh - v).mean(), ttest_rel(v, hh).pvalue))
    d = {g: np.array([T.loc[i, 'H'] - T.loc[i, 'V'] for i in T.index if G.get(i) == g
                      and np.isfinite(T.loc[i, 'V']) and np.isfinite(T.loc[i, 'H'])]) for g in ['CTL', 'Lo', 'Hi']}
    print('   change Hi vs WT p = %.3f ; hidden level Hi vs WT p = %.3f' %
          (mw(d['Hi'], d['CTL']).pvalue,
           mw([T.loc[i, 'H'] for i in T.index if G.get(i) == 'Hi' and np.isfinite(T.loc[i, 'H'])],
              [T.loc[i, 'H'] for i in T.index if G.get(i) == 'CTL' and np.isfinite(T.loc[i, 'H'])]).pvalue))
