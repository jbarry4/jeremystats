"""Step 20. What the mice do instead of searching: speed, and transit through the goal.

Removing the marker should slow a mouse down: it has to work out where the goal is rather than
run to a beacon.  WT and Lo mice do slow down.  At the last rotation Hi mice speed up, and the
comparison that shows it most cleanly is within the same mouse at the same phase, hidden session
against cued.

Panel c is the consequence: at hidden phase 10 Hi mice enter the goal zone as often as WT and
collect a third of the rewards, because a reward needs 1.2 s stationary and they are not
stopping.

Reads WORK/probe.pkl.  Output: figures/fig_speed_mode.png, WORK/approach/speed_mode.csv
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu as mw, ttest_rel

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'DejaVu Sans'], 'font.size': 9,
                     'axes.linewidth': 0.7, 'figure.facecolor': '#fcfcfb',
                     'savefig.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
GRP = ['CTL', 'Lo', 'Hi']; PH = [7, 8, 9, 10]

p = pd.read_pickle(WORK + '/probe.pkl').rename(columns={'MouseID': 'Mouse'})
p = p[p.G3.isin(GRP) & p.Phase.isin(PH)]
w = p.pivot_table(index=['G3', 'Mouse', 'Phase'], columns='Condition', values='MeanSpeed').reset_index()
w['d'] = w['H'] - w['V']

fig, axes = plt.subplots(1, 3, figsize=(8.4, 3.0))
fig.subplots_adjust(left=0.072, right=0.988, top=0.795, bottom=0.17, wspace=0.36)
rng = np.random.default_rng(4)

ax = axes[0]
for g in GRP:
    for cond, ls, mk in [('V', '--', 's'), ('H', '-', 'o')]:
        v = [p[(p.G3 == g) & (p.Phase == ph) & (p.Condition == cond)].MeanSpeed for ph in PH]
        ax.errorbar(range(4), [x.mean() for x in v], yerr=[x.std(ddof=1) / np.sqrt(len(x)) for x in v],
                    color=COL[g], ls=ls, marker=mk, ms=4, lw=1.7, mec='#fcfcfb', mew=0.5,
                    capsize=2, elinewidth=0.9)
ax.set_title('Speed, cued (dashed) vs hidden (solid)', fontsize=8.4, color=INK, fontweight='semibold', pad=4)
ax.set_ylabel('Mean speed (cm/s)', fontsize=8, color=MUT)

ax = axes[1]
for g in GRP:
    mu = []; se = []
    for ph in PH:
        v = w[(w.G3 == g) & (w.Phase == ph)].d.dropna().values
        mu.append(v.mean()); se.append(v.std(ddof=1) / np.sqrt(len(v)))
        ax.scatter(PH.index(ph) + rng.uniform(-0.14, 0.14, len(v)), v, s=7, color=COL[g],
                   alpha=0.32, edgecolor='none', zorder=2)
    ax.errorbar(range(4), mu, yerr=se, color=COL[g], lw=1.9, marker='o', ms=4.2,
                mec='#fcfcfb', mew=0.6, capsize=2, elinewidth=0.9, zorder=4, label=LAB[g])
ax.axhline(0, color='#9a9993', lw=0.9, ls=':', zorder=1)
a = w[(w.G3 == 'Hi') & (w.Phase == 10)].d.dropna(); b = w[(w.G3 == 'CTL') & (w.Phase == 10)].d.dropna()
pv = mw(a, b, alternative='two-sided')[1]
ax.text(3, 4.3, f'p = {pv:.3f}', ha='center', fontsize=7.2, color=INK, fontweight='bold')
ax.set_title('Does removing the marker slow them down?', fontsize=8.4, color=INK, fontweight='semibold', pad=4)
ax.set_ylabel('Hidden minus cued speed (cm/s)', fontsize=8, color=MUT)
ax.legend(frameon=False, fontsize=7.0, loc='lower left', labelspacing=0.2, handlelength=1.4)

ax = axes[2]
h10 = p[(p.Condition == 'H') & (p.Phase == 10)]
for g in GRP:
    d = h10[h10.G3 == g]
    ax.scatter(d.NumEntrances, d.NumRewards, s=26, color=COL[g], edgecolor='#fcfcfb',
               linewidth=0.6, zorder=3, label=LAB[g])
lim = [0, max(h10.NumEntrances.max(), 1) * 1.08]
ytop = max(h10.NumRewards.max(), 1) * 1.14
for frac, lab in [(1 / 3, 'one in three'), (1 / 6, 'one in six')]:
    ax.plot(lim, [x * frac for x in lim], color='#c9c8c3', lw=0.8, ls=':', zorder=1)
    xe = min(lim[1] * 0.98, (ytop * 0.93) / frac)
    ax.text(xe, xe * frac, lab, fontsize=6.3, color=MUT, ha='right', va='bottom')
ax.set_xlim(*lim); ax.set_ylim(0, ytop)
ax.legend(frameon=False, fontsize=7.0, loc='upper left', labelspacing=0.2, handletextpad=0.2)
ax.set_title('Hidden phase 10: entries vs rewards', fontsize=8.4, color=INK, fontweight='semibold', pad=4)
ax.set_xlabel('Goal-zone entries', fontsize=8, color=MUT)
ax.set_ylabel('Rewards', fontsize=8, color=MUT)

for i, ax in enumerate(axes):
    for s_ in ['top', 'right']: ax.spines[s_].set_visible(False)
    for s_ in ['left', 'bottom']: ax.spines[s_].set_color('#9a9993')
    ax.tick_params(colors=MUT, labelsize=7.6); ax.grid(color=GRID, lw=0.6); ax.set_axisbelow(True)
    if i < 2:
        ax.set_xticks(range(4)); ax.set_xticklabels([str(x) for x in PH], fontsize=7.8)
        ax.set_xlabel('Phase', fontsize=8, color=MUT)
fig.suptitle('What they do instead: running', fontsize=11, y=0.955, color=INK, fontweight='semibold')
os.makedirs(FIGS, exist_ok=True)
fig.savefig(os.path.join(FIGS, 'fig_speed_mode.png'), dpi=200)

w.to_csv(os.path.join(WORK, 'approach', 'speed_mode.csv'), index=False)
lines = ['Mean speed per probe session, and the within-mouse hidden-minus-cued difference\n']
for g in GRP:
    for ph in PH:
        v = w[(w.G3 == g) & (w.Phase == ph)]
        t = ttest_rel(v.H.dropna(), v.V.dropna())[1] if len(v.dropna()) > 1 else np.nan
        lines.append(f"{g:4s} phase {ph:2d}  cued {v.V.mean():6.2f}  hidden {v.H.mean():6.2f}  "
                     f"diff {v.d.mean():+6.2f}  paired p={t:.4f}")
lines.append(f"\nHi vs WT on the hidden-minus-cued difference at phase 10: p={pv:.4f}")
e = h10[h10.G3 == 'Hi']; c = h10[h10.G3 == 'CTL']
lines.append(f"Hidden phase 10 entries: WT {c.NumEntrances.mean():.1f}  Hi {e.NumEntrances.mean():.1f}  "
             f"p={mw(e.NumEntrances, c.NumEntrances, alternative='two-sided')[1]:.3f}")
lines.append(f"Hidden phase 10 rewards: WT {c.NumRewards.mean():.1f}  Hi {e.NumRewards.mean():.1f}  "
             f"p={mw(e.NumRewards, c.NumRewards, alternative='two-sided')[1]:.4f}")
open(os.path.join(WORK, 'approach', 'speed_mode_stats.txt'), 'w').write('\n'.join(lines) + '\n')
print('wrote fig_speed_mode')
