"""Step 24. The typical search path into the goal, cue present and cue removed.

One line per group per condition: the run that sits at that group's median, drawn from 3 s before
it entered the zone to 2 s after.  Runs are in goal-centred coordinates, rotated so the approach
comes from the left (y negated first, so handedness matches the room).  An open circle marks where
the run begins, a filled one where it ends.

The median is taken on the slowing ratio - mean speed over the 1.2 s after entry divided by mean
speed over the 1.5 to 0.5 s before it - because that is the measure the groups differ on.  Each
mouse contributes its own median run, and the group's line is the median of those, so the line is
a typical run and not an average of positions: averaging x and y across runs that have been
rotated to a common approach direction cancels the curvature and returns a straight line, which
would misrepresent every run that went into it.

Reads WORK/approach/runs_ex.pkl (s11) and WORK/probe.pkl.
Output: figures/fig_typical_search_path.png
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9,
                     'figure.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb',
                     'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
SF = 30
PRE, POST = 3.0, 2.0

p = pd.read_pickle(WORK + '/probe.pkl'); G = p.drop_duplicates('MouseID').set_index('MouseID').G3
R = pd.read_pickle(WORK + '/approach/runs_ex.pkl'); R['G3'] = R.Mouse.map(G)
R = R[R.G3.isin(COL)].copy()


def slow(r):
    e = r.ent_i; v = np.asarray(r.v, float)
    pre = v[max(0, e - int(1.5 * SF)):max(0, e - int(0.5 * SF))]
    post = v[e:e + int(1.2 * SF)]
    if len(pre) < 5 or len(post) < 5: return np.nan
    a = np.nanmean(pre)
    return np.nan if not a > 0 else np.nanmean(post) / a


R['slow'] = R.apply(slow, axis=1)


def align(r):
    x = np.asarray(r.x, float); y = -np.asarray(r.y, float)
    th = np.pi - np.arctan2(y[0], x[0]); c, s = np.cos(th), np.sin(th)
    return c * x - s * y, s * x + c * y


def nearest(d, col, target):
    return d.iloc[(d[col] - target).abs().values.argmin()]


PICK = {}
for cond in ['V', 'H']:
    for g in COL:
        d = R[(R.Cond == cond) & (R.G3 == g)].dropna(subset=['slow'])
        per_mouse = [nearest(dm, 'slow', dm.slow.median()) for _, dm in d.groupby('Mouse')
                     if len(dm) >= 3]
        s = pd.Series([r.slow for r in per_mouse])
        PICK[(cond, g)] = (per_mouse[int((s - s.median()).abs().values.argmin())],
                           float(s.median()), len(per_mouse), len(d))

GR = float(np.nanmedian(R.gr.astype(float)))
fig = plt.figure(figsize=(7.0, 3.05))
for i, (cond, ttl) in enumerate([('V', 'cue present'), ('H', 'cue removed')]):
    ax = fig.add_axes([0.045 + i * 0.455, 0.235, 0.425, 0.615])
    th = np.linspace(0, 2 * np.pi, 200)
    ax.fill(GR * np.cos(th), GR * np.sin(th), color='#edebe3', zorder=1)
    ax.plot(GR * np.cos(th), GR * np.sin(th), color='#8e8d87', lw=1.0, zorder=2)
    for g in ['CTL', 'Lo', 'Hi']:
        r, med, nm, nr = PICK[(cond, g)]
        x, y = align(r)
        a = max(0, r.ent_i - int(PRE * SF)); b = min(len(x), r.ent_i + int(POST * SF))
        x, y = x[a:b], y[a:b]
        ax.plot(x, y, color=COL[g], lw=2.1, solid_capstyle='round', zorder=4)
        ax.plot(x[0], y[0], 'o', ms=7.0, mfc='#fcfcfb', mec=COL[g], mew=1.8, zorder=6)
        ax.plot(x[-1], y[-1], 'o', ms=7.0, mfc=COL[g], mec='#fcfcfb', mew=1.2, zorder=6)
    ax.set_aspect('equal'); ax.set_xlim(-40, 22); ax.set_ylim(-16, 16); ax.axis('off')
    ax.set_title(ttl, fontsize=10, color=INK, fontweight='semibold', pad=6)
    ax.text(0.5, -0.015, '  '.join('%s %.2f' % (LAB[g], PICK[(cond, g)][1])
                                   for g in ['CTL', 'Lo', 'Hi']),
            transform=ax.transAxes, ha='center', va='top', fontsize=7.4, color=MUT)
    if i == 0:
        ax.plot([-38, -28], [-14, -14], color=MUT, lw=1.4)
        ax.text(-33, -13.1, '10 cm', fontsize=7, ha='center', color=MUT)

fig.text(0.5, 0.145, 'group median slowing ratio beneath each panel (1 = no slowing at all)',
         ha='center', fontsize=7.4, color=MUT)
fig.legend(handles=[Line2D([], [], color=COL[g], lw=2.1, label=LAB[g]) for g in ['CTL', 'Lo', 'Hi']] +
                   [Line2D([], [], marker='o', ls='', ms=6.5, mfc='#fcfcfb', mec=MUT, mew=1.6,
                           label='3 s before entry'),
                    Line2D([], [], marker='o', ls='', ms=6.5, mfc=MUT, mec='#fcfcfb',
                           label='2 s after entry')],
           loc='lower center', bbox_to_anchor=(0.5, -0.015), ncol=5, frameon=False, fontsize=8)
fig.suptitle('Where the typical search begins and ends', x=0.012, ha='left',
             fontsize=11.5, fontweight='semibold', color=INK, y=0.985)
os.makedirs(FIGS, exist_ok=True)
out = os.path.join(FIGS, 'fig_typical_search_path.png')
fig.savefig(out, dpi=200); print('wrote', out)
for (cond, g), (r, med, nm, nr) in PICK.items():
    print('  %s %-11s M%-3.0f  slowing %.2f (group median %.2f over %d mice, %d runs)' %
          (cond, LAB[g], r.Mouse, r.slow, med, nm, nr))
