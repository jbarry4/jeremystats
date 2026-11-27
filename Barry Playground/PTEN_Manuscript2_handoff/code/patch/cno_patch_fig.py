"""Report Figure 36: CNO silences hM4D-expressing Pten KO granule neurons.

A version of the lab's patch-clamp summary figure with the Pten;Raptor dKO group removed,
so that the figure shows only the two groups that appear in the rest of this report:
uninfected wild-type granule neurons recorded with no drug (time control) and Pten KO
granule neurons expressing hM4D(Gi) before and during 10 uM CNO.

Panels follow the original: a, sample current-clamp responses; b, normalised F-I curves;
c-f, paired per-cell values for spikes per sweep, spike threshold, rheobase and resting
potential.  p values are the two-tailed paired t tests reported in the methods; they are
within-group tests and so are unchanged by dropping the dKO group.

Inputs (inputs/patch/):
    cno_patch_cells.csv   per-cell baseline and post values for panels c-f
    cno_patch_fi.csv      F-I curves, SEM bands and cell counts for panel b
    cno_patch_traces.json sample traces for panel a, in axes fractions

Output: figures/fig36_cno_patch.png
"""
import os, sys, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import INPUTS, FIGS

PATCH = os.path.join(INPUTS, 'patch')
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 6.5, 'axes.linewidth': 0.7,
                     'xtick.major.width': 0.7, 'ytick.major.width': 0.7,
                     'xtick.major.size': 2.5, 'ytick.major.size': 2.5,
                     'savefig.facecolor': 'white', 'figure.facecolor': 'white'})

# colours, as in the original figure: light = baseline, dark = after
# (CNO for the Pten KO cells; 10 min later with no drug for the wild-type time control)
LIGHT = {'WT': '#a6a6a6', 'KO': '#8fbde4'}
DARK = {'WT': '#3a3a3a', 'KO': '#1f77b4'}
EDGE = {'WT': '#4d4d4d', 'KO': '#12527a'}
LINE = {'WT': '#555555', 'KO': '#1f77b4'}

cells = pd.read_csv(os.path.join(PATCH, 'cno_patch_cells.csv'))
cells = cells[cells.group.isin(['WT', 'KO'])].copy()
fi = pd.read_csv(os.path.join(PATCH, 'cno_patch_fi.csv'))
traces = json.load(open(os.path.join(PATCH, 'cno_patch_traces.json')))

fig = plt.figure(figsize=(6.5, 4.5))

# ------------------------------------------------------------------ a: sample traces
# four trace axes, two rows (wild-type, Pten KO) x two columns (before, after)
TR = {'a1': [0.075, 0.792, 0.199, 0.158], 'a2': [0.285, 0.792, 0.199, 0.158],
      'a3': [0.075, 0.586, 0.199, 0.158], 'a4': [0.285, 0.586, 0.199, 0.158]}
for k, rect in TR.items():
    ax = fig.add_axes(rect)
    for t in traces[k]:
        t = np.asarray(t)
        ax.plot(t[:, 0], t[:, 1], color='black', lw=0.3, solid_joinstyle='round')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    if k == 'a4':   # scale bar: 20 mV, 200 ms (as in the source figure)
        ax.plot([0.73, 1.0], [0.031, 0.031], color='black', lw=1.3, clip_on=False)
        ax.plot([1.0, 1.0], [0.031, 0.156], color='black', lw=1.3, clip_on=False)
        ax.text(1.02, 0.095, '20 mV', fontsize=5.8, va='center', ha='left')
        ax.text(0.865, 0.0, '200 ms', fontsize=5.8, va='top', ha='center')

fig.text(0.1745, 0.966, 'aCSF', fontsize=6.8, ha='center', weight='bold')
fig.text(0.3845, 0.966, 'aCSF, 10 min later', fontsize=6.8, ha='center', weight='bold')
fig.text(0.1745, 0.760, 'aCSF', fontsize=6.8, ha='center', weight='bold')
fig.text(0.3845, 0.760, 'aCSF + 10 μM CNO', fontsize=6.8, ha='center', weight='bold')
fig.text(0.4835, 0.945, '80 to 240 pA', fontsize=5.8, ha='right', color='#808080')
fig.text(0.4835, 0.739, '200 to 340 pA', fontsize=5.8, ha='right', color='#808080')
fig.text(0.058, 0.871, 'Wild-type\nno drug', fontsize=6.5, ha='center', va='center', rotation=90)
fig.text(0.058, 0.665, 'Pten KO\n+ HM4Di', fontsize=6.5, ha='center', va='center', rotation=90)

# ------------------------------------------------------------------ b: normalised F-I
axb = fig.add_axes([0.605, 0.670, 0.375, 0.280])
axn = fig.add_axes([0.605, 0.586, 0.375, 0.070])
SER = [('WT_aCSF', 'WT', '-', 'WT aCSF, start'), ('WT_later', 'WT', '--', 'WT aCSF, +10 min \u2014 no drug'),
       ('KO_aCSF', 'KO', '-', 'Pten KO aCSF'), ('KO_CNO', 'KO', '--', 'Pten KO + CNO')]
for name, grp, ls, lab in SER:
    d = fi[fi.series == name]
    axb.fill_between(d.current_rel_rheobase_pA, d.lo, d.hi, color=LINE[grp], alpha=0.16, lw=0)
    axb.plot(d.current_rel_rheobase_pA, d.rate_norm, color=LINE[grp], ls=ls, lw=1.4)
    axn.step(d.current_rel_rheobase_pA, d.n_cells, where='mid', color=LINE[grp], ls=ls, lw=0.9)
axb.axvline(0, color='#bbbbbb', lw=0.6, zorder=0)
axb.set_xlim(-20, 100); axb.set_ylim(-0.02, 1.02)
axb.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
axb.set_xticklabels([]); axb.set_xticks([-20, 0, 20, 40, 60, 80, 100])
axb.set_ylabel('Firing rate / peak rate', fontsize=6.5)
for s in ('top', 'right'): axb.spines[s].set_visible(False)
axn.set_xlim(-20, 100); axn.set_ylim(0, 9); axn.set_yticks([0, 3, 6, 9])
axn.set_xticks([-20, 0, 20, 40, 60, 80, 100])
axn.set_ylabel('Cells', fontsize=6.5)
axn.set_xlabel('Current from baseline rheobase (pA)', fontsize=6.5)
for s in ('top', 'right'): axn.spines[s].set_visible(False)
leg = [Line2D([], [], color=LINE[g], ls=ls, lw=1.4, label=f'{lab} ({n})')
       for (name, g, ls, lab), n in zip(SER, [5, 5, 5, 5])]
axb.legend(handles=leg, fontsize=5.6, loc='upper left', bbox_to_anchor=(0.00, 1.03),
           ncol=1, frameon=False, handlelength=1.9, handletextpad=0.5, labelspacing=0.28)

# ------------------------------------------------------------------ c-f: paired panels
def swarm(vals, ylim, rect, xspan, ms_pt, pad=1.25):
    """Beeswarm offsets in data units: spread points sideways only as far as needed so
    that no marker hides another.  Collision is tested in points, using the panel's real
    geometry, so the spread is the same whatever the y units of the panel are."""
    vals = np.asarray(vals, float)
    if len(vals) == 0:
        return np.zeros(0)
    h_pt = rect[3] * fig.get_figheight() * 72.0
    w_pt = rect[2] * fig.get_figwidth() * 72.0
    d = ms_pt * pad                                     # keep-out diameter, points
    ypt = (vals - ylim[0]) / (ylim[1] - ylim[0]) * h_pt
    order = np.argsort(ypt, kind='stable')
    xpt = np.zeros(len(vals))
    placed = []
    for i in order:
        best = 0.0
        step = d / 3.0
        for k in range(60):
            for cand in ((0.0,) if k == 0 else (step * k, -step * k)):
                ok = True
                for j in placed:
                    dy = abs(ypt[i] - ypt[j])
                    if dy >= d:
                        continue
                    if abs(cand - xpt[j]) < np.sqrt(max(d * d - dy * dy, 0.0)):
                        ok = False; break
                if ok:
                    best = cand; break
            else:
                continue
            break
        xpt[i] = best
        placed.append(i)
    xpt -= (xpt.min() + xpt.max()) / 2.0                # centre the cloud on the column
    return xpt / w_pt * xspan                           # points -> data units

X = {('WT', 'base'): 0.0, ('WT', 'post'): 1.0, ('KO', 'base'): 2.4, ('KO', 'post'): 3.4}
PANELS = [
    ('spikes_per_sweep', 'Spikes per sweep', [0.075, 0.085, 0.175, 0.300],
     (0, 26), [0, 5, 10, 15, 20, 25], {'WT': '<0.001', 'KO': '0.051'}, {'WT': '(5)', 'KO': '(5)'}),
    ('spike_threshold_mV', 'Spike threshold (mV)', [0.328, 0.085, 0.175, 0.300],
     (-56, -28), [-54, -48, -42, -36, -30], {'WT': '0.555', 'KO': '0.477'}, {'WT': '(5)', 'KO': '(5/3)'}),
    ('rheobase_pA', 'Rheobase (pA)', [0.581, 0.085, 0.175, 0.300],
     (30, 1010), [200, 400, 600, 800, 1000], {'WT': '1.000', 'KO': '0.254'}, {'WT': '(5)', 'KO': '(5/3)'}),
    ('resting_potential_mV', 'Resting potential (mV)', [0.825, 0.085, 0.175, 0.300],
     (-87, -70), [-84, -81, -78, -75, -72], {'WT': '0.724', 'KO': '0.490'}, {'WT': '(5)', 'KO': '(5)'}),
]
XSPAN = 4.6
for meas, ylab, rect, ylim, yticks, pvals, nlab in PANELS:
    ax = fig.add_axes(rect)
    d = cells[cells.measure == meas]
    for grp in ('WT', 'KO'):
        gd = d[d.group == grp].reset_index(drop=True)
        sil = gd.post_censored.notna() & (gd.post_censored.astype(str) != '')
        has = gd.post.notna()
        # one swarm per column, so that points never sit on top of one another
        ob = swarm(gd.baseline.values, ylim, rect, XSPAN, 2.9)
        op = np.zeros(len(gd))
        op[has.values] = swarm(gd.post[has].values, ylim, rect, XSPAN, 3.4)
        for i, r in gd.iterrows():
            xb = X[(grp, 'base')] + ob[i]
            if has[i]:
                xp = X[(grp, 'post')] + op[i]
                ax.plot([xb, xp], [r.baseline, r.post], color='#bababa', lw=0.5,
                        ls=':' if sil[i] else '-', zorder=1)
                if sil[i]:
                    ax.plot([xp], [r.post], marker='^', ms=3.4, mfc='white',
                            mec=DARK[grp], mew=0.8, ls='', zorder=3)
                else:
                    ax.plot([xp], [r.post], marker='o', ms=2.9, mfc=DARK[grp],
                            mec=EDGE[grp], mew=0.35, ls='', zorder=3)
            ax.plot([xb], [r.baseline], marker='o', ms=2.9, mfc=LIGHT[grp],
                    mec=EDGE[grp], mew=0.35, ls='', zorder=3)
        # mean +/- SEM per column; silenced neurons (rheobase above the highest current
        # tested) are drawn as open triangles but excluded from the CNO mean, as in the
        # paired test
        meas_post = gd[gd.post.notna() & gd.post_censored.isna()].post.values
        for key, vals in (('base', gd.baseline.values), ('post', meas_post)):
            if len(vals) == 0: continue
            m = vals.mean(); se = vals.std(ddof=1) / np.sqrt(len(vals))
            x = X[(grp, key)]
            ax.plot([x - 0.32, x + 0.32], [m, m], color='black', lw=1.0, zorder=4)
            ax.plot([x, x], [m - se, m + se], color='black', lw=0.7, zorder=4)
            for yy in (m - se, m + se):
                ax.plot([x - 0.19, x + 0.19], [yy, yy], color='black', lw=0.7, zorder=4)
    # p-value brackets
    yr = ylim[1] - ylim[0]
    for grp in ('WT', 'KO'):
        x0, x1 = X[(grp, 'base')], X[(grp, 'post')]
        yb = ylim[1] + 0.045 * yr
        ax.plot([x0, x0, x1, x1], [yb - 0.018 * yr, yb, yb, yb - 0.018 * yr],
                color='black', lw=0.6, clip_on=False)
        ax.text((x0 + x1) / 2, yb + 0.012 * yr, pvals[grp], fontsize=6.3,
                ha='center', va='bottom', clip_on=False)
    ax.set_xlim(-0.6, 4.0); ax.set_ylim(*ylim); ax.set_yticks(yticks)
    ax.set_xticks([0.5, 2.9])
    ax.set_xticklabels([f'WT\n{nlab["WT"]}', f'Pten KO\n{nlab["KO"]}'], fontsize=6.5)
    ax.tick_params(axis='x', length=0)
    ax.set_ylabel(ylab, fontsize=6.5)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
    if meas == 'spikes_per_sweep':
        hl = [Line2D([], [], marker='o', ls='', ms=3.2, mfc=LIGHT['WT'], mec=EDGE['WT'], mew=0.35, label='aCSF'),
              Line2D([], [], marker='o', ls='', ms=3.2, mfc=DARK['WT'], mec=EDGE['WT'], mew=0.35, label='after (CNO;\n+10 min for WT)')]
        ax.legend(handles=hl, fontsize=5.8, loc='upper left', bbox_to_anchor=(0.01, 1.02),
                  frameon=False, handletextpad=0.3, labelspacing=0.45)

for lab, x, y in [('a', 0.012, 0.975), ('b', 0.525, 0.975), ('c', 0.012, 0.460),
                  ('d', 0.265, 0.460), ('e', 0.518, 0.460), ('f', 0.762, 0.460)]:
    fig.text(x, y, lab, fontsize=9, weight='bold', va='top')

os.makedirs(FIGS, exist_ok=True)
out = os.path.join(FIGS, 'fig36_cno_patch.png')
fig.savefig(out, dpi=200)
plt.close()
print('wrote', out)
