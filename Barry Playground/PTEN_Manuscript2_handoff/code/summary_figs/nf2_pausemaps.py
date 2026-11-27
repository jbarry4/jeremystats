"""Where they look: the same mice with the cue on and off, and the group result beside it.

a-f  One session per mouse per condition at phase 10, cue present (left) and cue removed (right).
     Grey is the whole path; each marker is a pause, drawn where it happened and sized by how long
     it lasted.  Filled black marks a pause at the current goal, an open amber ring a pause at one
     of the three former goals, a pale dot a pause in the open interior.  Arenas are drawn in the
     room view, so the phase 7 goal is in the upper right quadrant and phases 8 to 10 follow
     anti-clockwise.
g    Pause time by the kind of place the pause was at, cue removed, every mouse.
h    What removing the cue does to each mouse's total pause time: per-mouse change with the group
     mean +- SE beside it.

Output: WORK/sumfig/nf2_pausemaps.png
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
MK = {'current': 'o', 'former': 'o', 'never': 's', 'open': '.'}

D = C.load(mice={m for _, m, _ in C.EX}, phases=(10,), conds=('H', 'V'))
fig = plt.figure(figsize=(7.2, 7.4))


def draw_map(ax, s, P):
    x, y = C.path_xy(s); Rc = s['R'] * C.CM
    ax.set_aspect('equal')
    ax.add_patch(plt.Circle((0, 0), Rc, fill=False, ec=GRID, lw=1.1))
    ax.add_patch(plt.Circle((0, 0), Rc * C.WALL, fill=False, ec='#c3c2bc', lw=0.7, ls=(0, (3, 3))))
    ax.plot(x, y, color='#d9d8d2', lw=0.3, zorder=1)
    for z in sorted(s['zones']):
        zx, zy, zr = C.zone_xy(s, z)
        cur = z == s['cur']
        ax.add_patch(plt.Circle((zx, zy), zr, fill=False, lw=1.5 if cur else 0.9,
                                ec=INK if cur else C.KIND['former'], ls='-' if cur else (0, (4, 2)), zorder=3))
    for kind in ['open', 'never', 'former', 'current']:
        q = P[P.kind == kind]
        if not len(q): continue
        ax.scatter(q.x, q.y, s=7 + q.dur * 8, marker=MK[kind],
                   facecolor=C.KIND[kind] if kind != 'former' else 'none',
                   edgecolor=C.KIND[kind], lw=0.9 if kind == 'former' else 0.3,
                   alpha=0.95 if kind != 'open' else 0.8, zorder=4)
    ax.set_xlim(-Rc * 1.05, Rc * 1.05); ax.set_ylim(-Rc * 1.05, Rc * 1.05); ax.axis('off')


MAPW = 0.215
for r, (g, m, name) in enumerate(C.EX):
    for c, cond in enumerate(['V', 'H']):
        s = D[(m, 10, cond)]; P = C.pauses(s)
        ax = fig.add_axes([0.055 + c * (MAPW + 0.015), 0.705 - r * 0.215, MAPW, 0.195])
        draw_map(ax, s, P)
        ax.text(0.5, 0.012, '%.0f s, %d pauses' % (P.dur.sum(), len(P)), transform=ax.transAxes,
                ha='center', va='bottom', fontsize=7.4, color=C.COL[g])
        ax.text(-0.03, 1.0, 'abcdef'[r * 2 + c], transform=ax.transAxes, fontsize=10,
                fontweight='bold', va='bottom')
        if r == 0:
            ax.text(0.5, 1.10, 'cue present' if cond == 'V' else 'cue removed', transform=ax.transAxes,
                    ha='center', va='bottom', fontsize=8.6, color=INK)
    fig.text(0.048, 0.805 - r * 0.215, '%s  %s' % (C.LAB[g], name), rotation=90, ha='right',
             va='center', fontsize=8.6, color=C.COL[g], fontweight='bold')

h = [Line2D([], [], marker='o', ls='', mfc=C.KIND['current'], mec=C.KIND['current'], ms=6, label='at the current goal'),
     Line2D([], [], marker='o', ls='', mfc='none', mec=C.KIND['former'], mew=1.2, ms=6, label='at a former goal'),
     Line2D([], [], marker='.', ls='', mfc=C.KIND['open'], mec=C.KIND['open'], ms=9, label='open interior'),
     Line2D([], [], marker='o', ls='', mfc='#bbbab4', mec='#bbbab4', ms=4, label='short pause'),
     Line2D([], [], marker='o', ls='', mfc='#bbbab4', mec='#bbbab4', ms=9, label='long pause')]
fig.legend(handles=h, loc='upper left', bbox_to_anchor=(0.045, 0.145), ncol=2, frameon=False,
           fontsize=7.4, handletextpad=0.3, columnspacing=1.0, labelspacing=0.45)

# ---------------- g: pause time by zone kind, cue removed, every mouse
ss = pd.read_csv(C.WORK + '/approach/search_sets.csv')
h10 = ss[(ss.Condition == 'H') & (ss.Phase == 10)]
order = ['current', 'former', 'open']
ax = fig.add_axes([0.605, 0.545, 0.375, 0.355])
W = 0.26
for gi, g in enumerate(['CTL', 'Lo', 'Hi']):
    for ki, k in enumerate(order):
        v = h10[(h10.Group == g) & (h10.Place == k)]['Pause time (s)'].values
        xc = ki + (gi - 1) * W
        ax.bar(xc, np.mean(v), W * 0.84, color=C.COL[g], alpha=0.28, ec=C.COL[g], lw=1.0, zorder=2)
        ax.errorbar(xc, np.mean(v), np.std(v, ddof=1) / np.sqrt(len(v)), color=C.COL[g], lw=1.2,
                    capsize=2.5, zorder=3)
        rng = np.random.default_rng(7 + ki * 10 + gi)
        ax.scatter(xc + rng.uniform(-W * 0.2, W * 0.2, len(v)), v, s=6, color=C.COL[g],
                   alpha=0.7, lw=0, zorder=4)
for ki, k in enumerate(order):
    a = h10[(h10.Group == 'CTL') & (h10.Place == k)]['Pause time (s)'].values
    b = h10[(h10.Group == 'Hi') & (h10.Place == k)]['Pause time (s)'].values
    p = mw(a, b, alternative='two-sided').pvalue
    ax.text(ki, 268, ('%.3f' % p).lstrip('0'), ha='center', fontsize=7.4,
            color=INK if p < 0.05 else MUT, fontweight='bold' if p < 0.05 else 'normal')
ax.text(1, 292, 'Hi vs WT', ha='center', fontsize=7.4, color=MUT)
ax.set_xticks(range(len(order))); ax.set_xticklabels([C.KINDLAB[k] for k in order], fontsize=8)
ax.set_ylabel('pause time per session (s)', fontsize=8.4); ax.set_ylim(0, 305)
ax.set_title('g   Where the pauses are, cue removed', fontsize=9, loc='left', pad=6)
for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
fig.legend(handles=[Line2D([], [], marker='s', ls='', color=C.COL[g], ms=6, label=C.LAB[g])
                    for g in ['CTL', 'Lo', 'Hi']],
           loc='upper center', bbox_to_anchor=(0.79, 0.995), ncol=3, frameon=False, fontsize=7.6,
           handletextpad=0.3, columnspacing=1.0)

# ---------------- h: what removing the cue does to each mouse
G = C.groups()
ied = pd.read_csv(C.WORK + '/phase8/phase8_mouse.csv').drop_duplicates('Mouse').set_index('Mouse').IED
tot = ss[ss.Phase == 10].groupby(['Mouse', 'Condition'])['Pause time (s)'].sum().unstack()
ax = fig.add_axes([0.605, 0.085, 0.375, 0.335])
ax.axhline(0, color=MUT, lw=0.8)
dd = {}
for gi, g in enumerate(['CTL', 'Lo', 'Hi']):
    mm = [i for i in tot.index if G.get(i) == g and np.isfinite(tot.loc[i, 'V']) and np.isfinite(tot.loc[i, 'H'])]
    d = np.array([tot.loc[i, 'H'] - tot.loc[i, 'V'] for i in mm]); dd[g] = d
    rng = np.random.default_rng(21 + gi)
    for x, i, val in zip(gi + rng.uniform(-0.14, 0.14, len(mm)), mm, d):
        ax.scatter(x, val, s=20, marker='D' if bool(ied.get(i, False)) else 'o', color=C.COL[g],
                   lw=0, alpha=0.75, zorder=3)
    ax.errorbar(gi + 0.30, d.mean(), d.std(ddof=1) / np.sqrt(len(d)), color=C.COL[g], lw=1.6,
                marker='_', ms=14, capsize=3, zorder=4)
    p = ttest_rel([tot.loc[i, 'V'] for i in mm], [tot.loc[i, 'H'] for i in mm]).pvalue
    ax.text(gi, -185, 'p = %s' % ('%.3f' % p).lstrip('0'), ha='center', fontsize=7.2,
            color=INK if p < 0.05 else MUT)
p = mw(dd['Hi'], dd['CTL'], alternative='two-sided').pvalue
ax.plot([0, 0, 2, 2], [152, 162, 162, 152], color=INK, lw=0.9)
ax.text(1, 166, 'Hi vs WT  p = %s' % ('%.3f' % p).lstrip('0'), ha='center', fontsize=7.6, color=INK)
ax.set_xticks(range(3)); ax.set_xticklabels([C.LAB[g] for g in ['CTL', 'Lo', 'Hi']], fontsize=8)
ax.set_xlim(-0.5, 2.6); ax.set_ylim(-200, 195)
ax.set_ylabel('change in pause time (s)\ncue removed minus cue present', fontsize=8.4)
ax.set_title('h   What removing the cue does', fontsize=9, loc='left', pad=6)
for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)

os.makedirs(C.FIGS, exist_ok=True)
fig.savefig(os.path.join(C.FIGS, 'nf2_pausemaps.png'), dpi=200)
print('saved')
for g, m, name in C.EX:
    for cond in ['V', 'H']:
        P = C.pauses(D[(m, 10, cond)])
        print(name, g, cond, 'total %.1f n=%d' % (P.dur.sum(), len(P)),
              P.groupby('kind').dur.sum().round(1).to_dict())
for g in ['CTL', 'Lo', 'Hi']:
    print('%-4s change %+.1f s' % (g, dd[g].mean()))
