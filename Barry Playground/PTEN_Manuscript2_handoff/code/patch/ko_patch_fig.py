"""CNO silences hM4D-expressing Pten KO granule neurons: the figure, from the raw recordings.

Everything here is computed from the AxoGraph files, not read off the earlier figure.  The five
neurons are those that pass the inclusion gates of the methods document, identified in the raw
files by fingerprinting all four published measures (see patch_cell_identities.csv):

    KO01 080326N005AA 003 -> 005      KO04 080326N008AA 005 -> 007
    KO02 080326N002AA 005 -> 007      KO05 080326N009AA 005 -> 007
    KO03 080326N001AA 006 -> 008  (the neuron that did not respond to CNO)

Series are 20 steps of 500 ms from 21 ms, incremented by 10 pA from a first step chosen per cell
to bracket rheobase; the first step and the increment are read from each file's own pulse row.
Spikes are peaks above -10 mV preceded within 2 ms by dV/dt > 100 mV/ms, with threshold at the
first sample of the spike's rising phase where dV/dt reaches 20 mV/ms, accepted when the peak
exceeds threshold by 20 mV.  Spikes per sweep are compared at matched injected current.

a  One neuron's voltage response at a current it fired at before CNO, before and after.
b  Spikes per sweep against injected current, each neuron and the group mean.
c  Spikes per sweep at matched current, each neuron, with the paired test and a bootstrap
   confidence interval resampled over neurons.
d  Rheobase; neurons silenced above the highest current tested are drawn at that current.
e  Spike threshold and resting potential.

Output: figures/fig21_ko_patch.png
"""
import os, sys, re
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS, PATCH_RAW
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy import stats

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9,
                     'figure.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb',
                     'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
BASE = '#2a78d6'; CNO = '#e34948'
CELLS = [('KO01', '080326N005AA', '003', '005'), ('KO02', '080326N002AA', '005', '007'),
         ('KO03', '080326N001AA', '006', '008'), ('KO04', '080326N008AA', '005', '007'),
         ('KO05', '080326N009AA', '005', '007')]
EXAMPLE = 'KO05'
SR = 80000.0; ON = 0.0207; DUR = 0.500


def trace(cell, num):
    from neo.io import AxographIO
    p = os.path.join(PATCH_RAW, '%s %s.axgd' % (cell, num))
    bl = AxographIO(p).read_block()
    V = np.vstack([np.asarray(s.analogsignals[0]).ravel() * 1000.0 for s in bl.segments])
    d = open(p, 'rb').read()[-9000:].decode('utf-16-be', 'ignore')
    f = re.search(r'Pulse #1[^\n]*\n([^\n]*)', d).group(1).split('\t')
    return V, float(f[11]), float(f[12])


T = pd.read_csv(WORK + '/patch/patch_per_sweep.csv')
T = T[T.group == 'KO'].copy()
M = pd.read_csv(WORK + '/patch/patch_series_measures.tsv', sep='\t', header=None,
                names=['file', 'sr', 'n', 'start', 'inc', 'mean', 'rheo', 'thr', 'rest', 'per'])
M['key'] = M.file.str.replace('.axgd', '', regex=False)
M = M.set_index('key')

pc = T.groupby(['cell', 'cond']).spikes.mean().unstack()
# The effect with its uncertainty at the unit that matters: resample neurons, not sweeps.
_rng = np.random.default_rng(0); _cells = list(pc.index); _b = []
for _ in range(4000):
    _s = _rng.choice(_cells, len(_cells), replace=True)
    _b.append(np.mean([pc.loc[c, 'cno'] - pc.loc[c, 'baseline'] for c in _s]))
_b = np.array(_b); B_EFF = _b.mean(); CI = (np.percentile(_b, 2.5), np.percentile(_b, 97.5))
# The drug effect across the whole F-I relation: a mixed model over every matched sweep, with a
# random intercept and slope per neuron.  Its Wald p treats sweeps as the replication unit, so it
# is referred to t on 4 df - the degrees of freedom five neurons provide.
import statsmodels.formula.api as smf
from scipy.stats import t as _t
T['rel'] = T.groupby('cell').current_pA.transform(lambda s: s - s.min())
_lmm = smf.mixedlm('spikes ~ cond + rel', T, groups=T['cell'], re_formula='~cond').fit(reml=False)
B_LMM = _lmm.params['cond[T.cno]']
P_LMM = 2 * _t.sf(abs(B_LMM / _lmm.bse['cond[T.cno]']), 4)

fig = plt.figure(figsize=(7.2, 6.6))

# ---------------------------------------------------------------- a: example traces
lab, cell, a_, b_ = [c for c in CELLS if c[0] == EXAMPLE][0]
Va, s0, inc = trace(cell, a_); Vb, s1, _ = trace(cell, b_)
cur_a = s0 + inc * np.arange(Va.shape[0]); cur_b = s1 + inc * np.arange(Vb.shape[0])
shared = np.intersect1d(cur_a, cur_b)
pick = shared[int(len(shared) * 0.75)]
t = (np.arange(Va.shape[1]) / SR - ON) * 1000.0
for k, (V, cur, col, ttl) in enumerate([(Va, cur_a, BASE, 'aCSF'), (Vb, cur_b, CNO, 'CNO 10 µM')]):
    ax = fig.add_axes([0.065 + k * 0.235, 0.730, 0.205, 0.195])
    v = V[list(cur).index(pick)]
    m = (t > -30) & (t < 560)
    ax.plot(t[m], v[m], color=col, lw=0.7)
    ax.set_ylim(-95, 45); ax.axis('off')
    ax.set_title(ttl, fontsize=9, color=col, pad=1)
    if k == 0:
        ax.plot([0, 100], [-92, -92], color=INK, lw=1.4)
        ax.plot([0, 0], [-92, -72], color=INK, lw=1.4)
        ax.text(50, -97, '100 ms', ha='center', va='top', fontsize=7, color=MUT)
        ax.text(-8, -82, '20 mV', ha='right', va='center', fontsize=7, color=MUT)
for _l, _x, _y in [('a', 0.012, 0.945), ('b', 0.566, 0.945), ('c', 0.012, 0.612),
                   ('d', 0.264, 0.612), ('e', 0.519, 0.612), ('f', 0.756, 0.612)]:
    fig.text(_x, _y, _l, fontsize=11, fontweight='bold', va='top', color=INK)
fig.text(0.300, 0.700, '%s, %.0f pA injected' % (EXAMPLE, pick), fontsize=8, color=MUT,
         ha='center', va='top')

# ---------------------------------------------------------------- b: F-I curves
ax = fig.add_axes([0.620, 0.735, 0.350, 0.190])
RHEO = {c: M.loc['%s %s' % (c, a_)].rheo for _, c, a_, _ in CELLS}
T['rel_rheo'] = T.current_pA - T.cell.map(RHEO)
keep = T.groupby('rel_rheo').cell.nunique()
keep = keep[keep >= 3].index
q = T[T.rel_rheo.isin(keep)]
for cond, col, nm in [('baseline', BASE, 'aCSF'), ('cno', CNO, 'CNO')]:
    for cell in T.cell.unique():
        r = q[(q.cond == cond) & (q.cell == cell)].sort_values('rel_rheo')
        ax.plot(r.rel_rheo, r.spikes, color=col, lw=0.6, alpha=0.22, zorder=2)
    g = q[q.cond == cond].groupby('rel_rheo').spikes.agg(['mean', 'sem'])
    ax.fill_between(g.index, g['mean'] - g['sem'], g['mean'] + g['sem'], color=col, alpha=0.18, lw=0)
    ax.plot(g.index, g['mean'], color=col, lw=2.4, label=nm, zorder=5)
ax.axvline(0, color='#9a9993', lw=0.8, ls=(0, (3, 3)))
ax.set_xlim(keep.min(), keep.max() + 26); ax.set_ylim(0, 17)
ax.set_xticks([x for x in [-50, 0, 50, 100] if keep.min() <= x <= keep.max()])
ax.set_xlabel('current above each neuron\'s own rheobase (pA)', fontsize=8.2, labelpad=1)
ax.set_ylabel('spikes per sweep', fontsize=8.5)
# Direct labels instead of a legend box: the figure already has one, and a box here sits on the data.
for cond, col, nm in [('baseline', BASE, 'aCSF'), ('cno', CNO, 'CNO')]:
    g = q[q.cond == cond].groupby('rel_rheo').spikes.mean()
    ax.text(g.index[-1] + 4, g.iloc[-1], nm, color=col, fontsize=8, fontweight='semibold',
            ha='left', va='center')
ax.text(0.025, 0.97, 'drug effect %+.1f spikes/sweep, p = %s\nmixed model over %d matched pairs, 4 df'
        % (B_LMM, ('%.3f' % P_LMM).lstrip('0'), len(T) // 2), transform=ax.transAxes, va='top',
        fontsize=7.0, color=INK, zorder=8,
        bbox=dict(facecolor='#fcfcfb', edgecolor='none', pad=1.5))
for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)

# ---------------------------------------------------------------- c-e: paired measures
rows = {}
for lab, cell, a_, b_ in CELLS:
    ra, rb = M.loc['%s %s' % (cell, a_)], M.loc['%s %s' % (cell, b_)]
    hi_b = rb.start + rb.inc * 19
    rows[lab] = dict(
        spikes=(pc.loc[cell, 'baseline'], pc.loc[cell, 'cno']),
        rheo=(ra.rheo, rb.rheo if np.isfinite(rb.rheo) else hi_b),
        rheo_cens=not np.isfinite(rb.rheo),
        thr=(ra.thr, rb.thr), rest=(ra.rest, rb.rest))

PAN = [('spikes', 'spikes per sweep (matched current)', 'Firing rate', 0.078, (0, 10)),
       ('rheo', 'rheobase (pA)', 'Rheobase', 0.330, (100, 950)),
       ('thr', 'spike threshold (mV)', 'Threshold', 0.585, (-55, -32)),
       ('rest', 'resting potential (mV)', 'Resting potential', 0.822, (-92, -74))]
for key, ylab, ttl, x0, ylim in PAN:
    ax = fig.add_axes([x0, 0.085, 0.140, 0.470])
    av, bv = [], []
    for lab in rows:
        a, b = rows[lab][key]
        cens = rows[lab]['rheo_cens'] and key in ('rheo', 'thr')
        if not np.isfinite(a):
            continue
        ax.scatter([0], [a], s=22, color=BASE, zorder=3)
        if not np.isfinite(b):
            continue
        ax.plot([0, 1], [a, b], color='#9a9993', lw=0.8, ls=(0, (2, 2)) if cens else '-', zorder=2)
        ax.scatter([1], [b], s=22, facecolor='none' if cens else CNO, edgecolor=CNO, lw=1.2, zorder=3)
        if cens:                      # silenced: shown, but not in the paired test (methods)
            continue
        av.append(a); bv.append(b)
    av, bv = np.array(av), np.array(bv)
    for x, v in [(0, av), (1, bv)]:
        ax.plot([x - 0.18, x + 0.18], [v.mean()] * 2, color=INK, lw=2.0, zorder=4)
    p = stats.ttest_rel(av, bv).pvalue
    ax.set_xticks([0, 1]); ax.set_xticklabels(['aCSF', 'CNO'], fontsize=8.5)
    ax.set_xlim(-0.45, 1.45); ax.set_ylim(*ylim)
    ax.set_ylabel(ylab, fontsize=8.2)
    ax.set_title(ttl, fontsize=9, loc='left', pad=13)
    sub = ('paired t p = %s' % (('%.3f' % p).lstrip('0') if p >= 0.001 else '< .001')) + \
          ('   n = %d of 5' % len(av) if len(av) < 5 else '')
    ax.text(0.0, 1.015, sub, transform=ax.transAxes, fontsize=7.2, va='bottom',
            color=INK if p < 0.05 else MUT)
    if key == 'spikes':
        ax.text(0.97, 0.985, 'bootstrap over neurons\n95%% CI %.1f to %.1f' % CI,
                transform=ax.transAxes, fontsize=6.8, va='top', ha='right', color=MUT,
                linespacing=1.35)
    for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)

fig.legend(handles=[Line2D([], [], marker='o', ls='', color=BASE, ms=6, label='aCSF'),
                    Line2D([], [], marker='o', ls='', mfc=CNO, mec=CNO, ms=6, label='CNO'),
                    Line2D([], [], marker='o', ls='', mfc='none', mec=CNO, mew=1.2, ms=6,
                           label='silenced: no spike at any current tested')],
           loc='lower center', bbox_to_anchor=(0.5, -0.005), ncol=3, frameon=False, fontsize=7.6)
fig.suptitle('CNO silences hM4D-expressing Pten KO granule neurons (n = 5)', x=0.008, ha='left',
             fontsize=11.5, fontweight='semibold', color=INK, y=0.995)
os.makedirs(FIGS, exist_ok=True)
out = os.path.join(FIGS, 'fig21_ko_patch.png')
fig.savefig(out, dpi=200); print('wrote', out)
print('per-cell means %.2f -> %.2f, paired t p = %.4f' %
      (pc.baseline.mean(), pc.cno.mean(), stats.ttest_rel(pc.baseline, pc.cno).pvalue))
print('bootstrap over neurons: %+.2f spikes/sweep, 95%% CI %.2f to %.2f' % (B_EFF, CI[0], CI[1]))
for k, v in rows.items(): print(' ', k, {m: tuple(np.round(x, 2) for x in v[m]) for m in ['spikes', 'rheo', 'thr', 'rest']})
