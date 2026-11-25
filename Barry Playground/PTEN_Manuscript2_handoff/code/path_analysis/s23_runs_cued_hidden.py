"""Step 23. Directed runs into the goal at phase 10, cue present and cue removed.

The same drawing as panel a of fig16a, but with both conditions, so the cue is the comparison
rather than the group.  Every directed run into the current goal at phase 10 for one mouse per
group, goal-centred and rotated so the approach comes from the left, path coloured by speed.  The
dot marks where the mouse was 1.2 s after entering: inside the zone (green) is a reward, outside
(red) is a miss.  y is negated before rotating, so the handedness of each run matches the room.

Top row: cue present (visible phase 10).  Bottom row: cue removed (hidden phase 10).

Reads WORK/approach/runs_ex.pkl (s11) and WORK/probe.pkl.
Output: figures/fig_runs_cued_hidden.png
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9,
                     'figure.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb',
                     'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
SF = 30; VMAX = 35.0
IN_C = '#1a7f37'; OUT_C = '#d1242f'
norm = Normalize(0, VMAX); cmap = plt.get_cmap('viridis')
EX = [('CTL', 22.0), ('Lo', 10.0), ('Hi', 34.0)]          # the mice used in report Figure 8
ROWS = [('V', 'cue present'), ('H', 'cue removed')]

p = pd.read_pickle(WORK + '/probe.pkl'); G = p.drop_duplicates('MouseID').set_index('MouseID').G3
R = pd.read_pickle(WORK + '/approach/runs_ex.pkl'); R['G3'] = R.Mouse.map(G)
R = R[R.G3.isin(COL)].copy()


def align(r):
    """Goal-centred, rotated so the approach comes from the left; y negated first (tracker y runs
    down the image, so without this every run's curvature is mirrored)."""
    x = np.asarray(r.x, float); y = -np.asarray(r.y, float)
    th = np.pi - np.arctan2(y[0], x[0]); c, s = np.cos(th), np.sin(th)
    return c * x - s * y, s * x + c * y


fig = plt.figure(figsize=(7.0, 5.0))
gs = fig.add_gridspec(2, 3, hspace=0.30, wspace=0.10,
                      left=0.085, right=0.885, top=0.845, bottom=0.075)
for i, (cond, rlab) in enumerate(ROWS):
    for j, (g, m) in enumerate(EX):
        ax = fig.add_subplot(gs[i, j])
        d = R[(R.Cond == cond) & (R.G3 == g) & (R.Mouse == m)]
        gr = d.iloc[0].gr
        for _, r in d.iterrows():
            x, y = align(r); v = np.nan_to_num(np.asarray(r.v, float))
            pts = np.array([x, y]).T.reshape(-1, 1, 2)
            lc = LineCollection(np.concatenate([pts[:-1], pts[1:]], axis=1), cmap=cmap, norm=norm,
                                lw=0.85, alpha=0.8); lc.set_array(v[:-1]); ax.add_collection(lc)
            e = r.ent_i; k = e + int(1.2 * SF)
            if k < len(x):
                ins = np.hypot(x[k], y[k]) <= gr
                ax.plot(x[k], y[k], 'o', ms=3.6, mfc=(IN_C if ins else OUT_C), mec='white',
                        mew=0.55, zorder=5)
        th = np.linspace(0, 2 * np.pi, 200)
        ax.plot(gr * np.cos(th), gr * np.sin(th), color='#333333', lw=1.1, zorder=3)
        ax.set_aspect('equal'); ax.set_xlim(-42, 42); ax.set_ylim(-30, 30); ax.axis('off')
        ax.text(0.5, 1.02, '%d runs · %.0f%% rewarded' % (len(d), 100 * d.rewarded.mean()),
                transform=ax.transAxes, ha='center', va='bottom', fontsize=7.8, color=MUT)
        if i == 0:
            ax.text(0.5, 1.16, '%s (M%.0f)' % (LAB[g], m), transform=ax.transAxes, ha='center',
                    va='bottom', fontsize=8.6, color=COL[g], fontweight='semibold')
        if j == 0:
            ax.text(-0.035, 0.5, rlab, transform=ax.transAxes, rotation=90, ha='right',
                    va='center', fontsize=9.2, color=INK, fontweight='semibold')
            if i == 1:
                ax.plot([-40, -30], [-27, -27], color=MUT, lw=1.4)
                ax.text(-35, -25.5, '10 cm', fontsize=6.6, ha='center', color=MUT)

cax = fig.add_axes([0.905, 0.22, 0.016, 0.46])
cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, extend='max')
cb.set_label('speed (cm/s)', fontsize=8); cb.ax.tick_params(labelsize=7.5)
cb.outline.set_visible(False)
fig.legend(handles=[Line2D([], [], marker='o', ls='', ms=5, mfc=IN_C, mec='white',
                           label='in the zone 1.2 s after entry (reward)'),
                    Line2D([], [], marker='o', ls='', ms=5, mfc=OUT_C, mec='white',
                           label='outside it (no reward)')],
           loc='upper center', bbox_to_anchor=(0.49, 0.945), ncol=2, frameon=False, fontsize=8)
fig.suptitle('Directed runs into the goal at phase 10, with the cue and without it',
             x=0.012, ha='left', fontsize=11.5, fontweight='semibold', color=INK, y=0.985)
os.makedirs(FIGS, exist_ok=True)
out = os.path.join(FIGS, 'fig_runs_cued_hidden.png')
fig.savefig(out, dpi=200); print('wrote', out)
for cond, rlab in ROWS:
    for g, m in EX:
        d = R[(R.Cond == cond) & (R.G3 == g) & (R.Mouse == m)]
        print('  %-12s %-4s M%-3.0f %3d runs  %4.0f%% rewarded' %
              (rlab, LAB[g], m, len(d), 100 * d.rewarded.mean()))
