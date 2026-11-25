"""Report Figures 2 and 3. What the task looks like, and what the session measures show.

One figure per condition: the three example mice on the left, phase by phase, and the four
session measures on the right.  Putting them side by side is the point - the paths show a task
being performed and the measures show the summary numbers that, on their own, missed what was
happening at the goal.

Left   Every rewarded approach (3 s before each reward) over the full 30-minute path, for one
       mouse per group at each phase.  Arenas are drawn in the room view.
Right  The four measures that recur through the report, by phase, mean +- SE across mice, with
       letters marking uncorrected p < 0.05 at that phase.

Reads WORK/traj/traj_preview.pkl, probe.pkl and phase_tab.pkl.
Output: figures/fig02_visible.png, figures/fig03_hidden.png
"""
import os, sys, pickle
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE),
                                                                   os.path.join(os.path.dirname(_HERE), 'path_analysis')]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.lines import Line2D
from arena_fit import fit_arena

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9.5,
                     'figure.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb',
                     'axes.facecolor': '#fcfcfb', 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': '#9a9993', 'axes.labelcolor': '#52514e',
                     'xtick.color': '#52514e', 'ytick.color': '#52514e', 'axes.grid': True,
                     'grid.color': '#e9e8e3', 'grid.linewidth': 0.7, 'axes.axisbelow': True,
                     'legend.frameon': False})
INK = '#0b0b0b'; MUT = '#52514e'; R0 = 127.5; RD = 121.0
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
MK = {'CTL': 'o', 'Lo': '^', 'Hi': 's'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
MICE = [(22, 'CTL', 'M22 (WT)'), (33, 'Lo', 'M33 (Lo, 8.8%)'), (34, 'Hi', 'M34 (Hi, 28.4%)')]
V = [('NumRewards', 'Rewards'), ('ReRatio', 'Rewards per entrance'),
     ('PGoalTime', 'Proportion time in goal'), ('MeanTargSpeed', 'Mean target speed (cm/s)')]

T = pickle.load(open(WORK + '/traj/traj_preview.pkl', 'rb'))
for key, o in T.items():
    cx, cy, Rf = fit_arena(o['X'], o['Y']); k = RD / Rf; ok = o['X'] > 0
    o['X'] = np.where(ok, (o['X'] - cx) * k + R0, 0.); o['Y'] = np.where(ok, (o['Y'] - cy) * k + R0, 0.)
    o['zc'] = {z: ((x - cx) * k + R0, (y - cy) * k + R0) for z, (x, y) in o['zc'].items()}
    o['targ'] = (None, None, o['targ'][2] * k)
df = pd.read_pickle(WORK + '/probe.pkl'); df = df[df.G3 != 'UNK']
R = pd.read_pickle(WORK + '/phase_tab.pkl')


def arena(ax, o, ph):
    ax.add_patch(Circle((R0, R0), R0, fill=False, ec='#9a9993', lw=0.9))
    r = o['targ'][2]
    for z, (x, y) in o['zc'].items():
        cur = (z == ph - 6); prev = (z == ph - 7); trained = (z == 1)
        ec = INK if cur else ('#52514e' if (prev or trained) else '#b8b7b0')
        ls = '-' if cur else ((0, (3, 2)) if prev else ((0, (1, 1.5)) if trained else '-'))
        ax.add_patch(Circle((x, y), r, fill=False, ec=ec, lw=1.5 if cur else 0.9, ls=ls, zorder=6))
    ax.set_xlim(-4, 259); ax.set_ylim(259, -4)      # room view: y runs down the tracker image
    ax.set_aspect('equal'); ax.axis('off')


def build(cond, name, fn):
    fig = plt.figure(figsize=(11.2, 5.6))
    # ---- left: the example mice
    L = 0.052; W = 0.129; top = 0.845; rowh = 0.248
    for i, (m, g, lab) in enumerate(MICE):
        for j, ph in enumerate(range(7, 11)):
            ax = fig.add_axes([L + j * W, top - (i + 1) * rowh + 0.045, W - 0.008, rowh - 0.052])
            o = T[(m, ph, cond)]
            X = np.where(o['X'] == 0, np.nan, o['X']); Y = np.where(o['Y'] == 0, np.nan, o['Y'])
            ax.plot(X, Y, color='#c9c8c2', lw=0.3, zorder=1)
            for e in o['rew']:
                a = max(0, e - int(4.2 * 30)); b = e - int(1.2 * 30)
                if b > a: ax.plot(X[a:b + 1], Y[a:b + 1], color=COL[g], lw=0.8, alpha=0.9, zorder=3)
            ax.scatter(X[o['rew']], Y[o['rew']], s=5, color=INK, zorder=7, lw=0)
            arena(ax, o, ph)
            tpe = np.isin(o['state'], [1, 2, 3]).sum() / 30 / max(o['n_ent'], 1)
            ax.text(R0, 272, '%d rew · %d ent · %.2f s' % (o['n_rew'], o['n_ent'], tpe),
                    ha='center', va='top', fontsize=7.0, color=MUT)
            if i == 0:
                ax.set_title('Phase %d%s' % (ph, ' (trained)' if ph == 7 else ''), fontsize=9,
                             fontweight='600', color=INK, pad=4)
            if j == 0:
                ax.text(-34, R0, lab, rotation=90, va='center', ha='center', fontsize=8.6,
                        fontweight='600', color=COL[g])
    # ---- right: the four measures
    gs = fig.add_gridspec(2, 2, left=0.600, right=0.985, top=0.800, bottom=0.225,
                          hspace=0.52, wspace=0.34)
    for k, (v, lab) in enumerate(V):
        ax = fig.add_subplot(gs[k // 2, k % 2])
        tops = []
        for j, g in enumerate(['CTL', 'Lo', 'Hi']):
            d = df[(df.Condition == cond) & (df.G3 == g)].groupby('Phase')[v].agg(['mean', 'sem'])
            x = np.array([7, 8, 9, 10]) + (j - 1) * 0.08
            ax.errorbar(x, d['mean'], yerr=d['sem'], color=COL[g], marker=MK[g], ms=4.4, lw=1.6,
                        elinewidth=1.0, capsize=2.0, mec='#fcfcfb', mew=0.7, zorder=3)
            tops.append((d['mean'] + d['sem']).values)
        tops = np.max(tops, axis=0); lo, hi = ax.get_ylim(); span = hi - lo
        ax.set_ylim(lo, hi + span * 0.18)
        for i, ph in enumerate([7, 8, 9, 10]):
            r = R[(R.cond == cond) & (R['var'] == v) & (R.phase == ph)].iloc[0]; s = ''
            if r.p_LoCTL < .05: s += 'L'
            if r.p_HiCTL < .05: s += 'H'
            if r.p_LoHi < .05: s += '×'
            if s: ax.text(ph, tops[i] + span * 0.05, s, ha='center', va='bottom', fontsize=8,
                          color=INK, fontweight='600')
        ax.axvspan(7.5, 10.4, color='#f0efec', alpha=0.6, zorder=0)
        ax.set_xlim(6.6, 10.4); ax.set_xticks([7, 8, 9, 10])
        ax.set_xticklabels(['7\ntrained', '8', '9', '10'], fontsize=8)
        ax.tick_params(labelsize=8)
        ax.set_title(lab, loc='left', fontsize=9, fontweight='600', color=INK, pad=3)
        ax.grid(axis='x', visible=False)
        if k >= 2: ax.set_xlabel('Probe phase', fontsize=8.5, labelpad=2)
    fig.legend(handles=[Line2D([], [], color=COL[g], marker=MK[g], ms=5, lw=1.8, label=LAB[g])
                        for g in ['CTL', 'Lo', 'Hi']],
               loc='upper right', bbox_to_anchor=(0.988, 0.915), ncol=3, fontsize=8.6)
    fig.suptitle('%s goal sessions: the three example mice, and the session measures' % name,
                 x=0.008, ha='left', fontsize=12, fontweight='600', color=INK, y=0.975)
    fig.text(0.052, 0.055, 'Grey: the full 30-minute path.  Coloured: the 3 s before each reward.  '
             'Black dots: where the reward was triggered.\nCircles: solid = current goal, dashed = '
             'previous goal, dotted = the trained goal (zone 1), light grey = not yet used.',
             fontsize=7.4, color=MUT)
    fig.text(0.600, 0.045, 'Mean ± SE across mice.  Letters mark uncorrected p < 0.05 at that '
             'phase:\nL = Lo vs WT,  H = Hi vs WT,  × = Lo vs Hi.  Shaded: novel goal locations.',
             fontsize=7.4, color=MUT)
    os.makedirs(FIGS, exist_ok=True)
    out = os.path.join(FIGS, fn)
    fig.savefig(out, dpi=200); plt.close(); print('wrote', out)


build('V', 'Visible', 'fig02_visible.png')
build('H', 'Hidden', 'fig03_hidden.png')
