"""Step 14. Phase 8 conflict probes: statistics, tables and report Figures 30 (visible) and 31 (hidden).

## NOT IN MATLAB: designed here. Input: WORK/phase8/visits.pkl (s13) and WORK/probe.pkl (group_analysis/probe.py).
Only directed runs count (launch >= 20 cm), taken in the order the mouse made them.
The two never-used zones (3 and 4) have never been rewarded, so runs to them give each mouse's no-memory baseline.

Visible phase 8 (cue on the new goal): place (old goal) vs cue (new goal).
  A  Old-place share: of the first 10 directed runs to the old place or the cue, the share to the old place.
     Baseline: the same share computed for each never-used zone against the cue (first 10 never-vs-cue runs), mean of zones 3 and 4.
  B  Latent place preference: of the first 10 directed runs to any zone, % to the old place minus % to one never-used zone
     (never-used % halved, since there are two such zones). Above 0 = the old place draws more runs than a place with no memory.
  C  Old-place share (A) against phase 10 hidden rewards.
Hidden phase 8 (no cue): new place vs old place.
  A  Place pull, first 20 directed runs to any zone: % to the new place minus one never-used zone, and % to the old place
     minus one never-used zone. (First 10 runs: same direction, fewer runs; printed below.)
  B  Old-place pull (as visible B, first 10 runs) with the cue present (visible) and with it gone (hidden), paired by mouse.
  C  Place pull (mean of new and old, minus never-used; first 20 runs) against phase 10 hidden rewards.
Tests: within group, one-sample t vs 0 or paired t; between groups, two-sided Mann-Whitney; links, Spearman, and a
rank regression with group in the model (rank(y) ~ rank(x) + group).
Outputs: FIGS/fig30_phase8_visible.png, FIGS/fig31_phase8_hidden.png, WORK/phase8/phase8_mouse.csv, WORK/phase8/phase8_stats.txt.
"""
import os, sys, warnings
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
import config
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import ttest_1samp, ttest_rel, mannwhitneyu, spearmanr
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore')
WORK, FIGS = config.WORK, config.FIGS; OUT = os.path.join(WORK, 'phase8')
plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 8.5, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': '#9a9993', 'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'axes.grid': True,
                     'grid.color': '#e9e8e3', 'grid.linewidth': 0.6, 'axes.axisbelow': True, 'legend.frameon': False})
INK = '#0b0b0b'; MUT = '#52514e'; GRY = '#9a9993'; RED = '#b3261e'
COL = {'WT': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}; MK = {'WT': 'o', 'Lo': 's', 'Hi': '^'}; GR = ['WT', 'Lo', 'Hi']
fp = lambda p: 'p < 0.001' if p < 0.001 else f'p = {p:.3f}'
mw = lambda a, b: mannwhitneyu(a, b, alternative='two-sided').pvalue
LOG = []
def log(s=''): print(s); LOG.append(s)

# ---------------------------------------------------------------- per-mouse measures
p = pd.read_pickle(os.path.join(WORK, 'probe.pkl')); m0 = p.drop_duplicates('MouseID').set_index('MouseID')
G = m0.G3.replace({'CTL': 'WT'}); IED = m0.IED == '+'; PCT = m0.pct
p10 = p[(p.Phase == 10) & (p.Condition == 'H')].set_index('MouseID').NumRewards
V = pd.read_pickle(os.path.join(OUT, 'visits.pkl')); V['g'] = V.Mouse.map(G)
V = V[V.g.isin(GR) & (V.launch >= 20)].sort_values(['Mouse', 'Cond', 't_in']).copy()

def share(cond, a, b, N=10):
    """share of the first N directed runs to zone-role a or b that went to a"""
    x = V[(V.Cond == cond) & V.zone.isin([a, b])].groupby('Mouse').head(N)
    return x.groupby('Mouse').zone.apply(lambda s: (s == a).mean() * 100)

def pull(cond, N):
    """% of the first N directed runs (any zone) to new, old, and one never-used zone"""
    x = V[V.Cond == cond].groupby('Mouse').head(N)
    return x.groupby('Mouse').role.apply(lambda s: pd.Series({'new': (s == 'new').mean() * 100, 'old': (s == 'old').mean() * 100,
                                                             'nev': (s == 'never').mean() * 50})).unstack()

M = pd.DataFrame({'g': G[G.isin(GR)], 'IED': IED, 'pct': PCT}).dropna(subset=['g'])
M['V_old_share'] = share('V', 1, 2); M['V_never_share'] = (share('V', 3, 2) + share('V', 4, 2)) / 2
v10 = pull('V', 10); M['V_old_pull'] = v10.old - v10.nev
h10 = pull('H', 10); h20 = pull('H', 20); hall = pull('H', 1000)
M['H_old_pull'] = h10.old - h10.nev
for k, h in [('20', h20), ('10', h10), ('all', hall)]:
    M[f'H{k}_new_pct'] = h.new; M[f'H{k}_old_pct'] = h.old; M[f'H{k}_never_pct'] = h.nev
    M[f'H{k}_new_pull'] = h.new - h.nev; M[f'H{k}_old_pull'] = h.old - h.nev; M[f'H{k}_place_pull'] = (h.new + h.old) / 2 - h.nev
M['H_minus_V_old_pull'] = M.H_old_pull - M.V_old_pull
M['P10_rewards'] = p10; M['n_directed_V'] = V[V.Cond == 'V'].groupby('Mouse').size(); M['n_directed_H'] = V[V.Cond == 'H'].groupby('Mouse').size()
M.index.name = 'Mouse'; M.round(2).to_csv(os.path.join(OUT, 'phase8_mouse.csv'))
GM = {g: M[M.g == g] for g in GR}; KO = M[M.g != 'WT']

def within(v, ref=0):
    return {g: (GM[g][v].mean(), ttest_1samp(GM[g][v].dropna(), ref).pvalue) for g in GR}
def between(v):
    w = GM['WT'][v].dropna()
    return {'Lo vs WT': mw(GM['Lo'][v].dropna(), w), 'Hi vs WT': mw(GM['Hi'][v].dropna(), w), 'KO vs WT': mw(KO[v].dropna(), w),
            'Lo vs Hi': mw(GM['Lo'][v].dropna(), GM['Hi'][v].dropna())}
def link(x, y, D=M):
    s = D[[x, y, 'g']].dropna().copy(); out = {}
    for lab, S in [('all', s), ('WT', s[s.g == 'WT']), ('KO', s[s.g != 'WT'])]:
        r, pv = spearmanr(S[x], S[y]); out[lab] = (r, pv, len(S))
    s['rx'] = s[x].rank(); s['ry'] = s[y].rank(); f = smf.ols('ry ~ rx + grp', s.rename(columns={'g': 'grp'})).fit()
    out['with group'] = f.pvalues['rx']; return out
def line(lab, v, ref=0):
    w = within(v, ref); b = between(v)
    log(f'{lab:52s} ' + '  '.join(f'{g} {w[g][0]:+6.1f} ({fp(w[g][1])})' for g in GR) + ' | ' + '  '.join(f'{k} {fp(q)}' for k, q in b.items()))

log('n mice: ' + ', '.join(f'{g} {len(GM[g])}' for g in GR) + f'; IED+ {int(M.IED.sum())}')
log('directed runs per mouse (median): visible ' + str(M.groupby('g').n_directed_V.median().to_dict()) + ', hidden ' + str(M.groupby('g').n_directed_H.median().to_dict()))
log('\nVISIBLE phase 8: place (old goal) vs cue (new goal). Within group vs 0 (pull) or vs baseline (share, paired t).')
for g in GR:
    x = GM[g]; log(f'  old-place share {g}: {x.V_old_share.mean():.1f}%  never-used vs cue {x.V_never_share.mean():.1f}%  paired p = {ttest_rel(x.V_old_share, x.V_never_share).pvalue:.3f}')
b = between('V_old_share'); log('  old-place share between groups: ' + '  '.join(f'{k} {fp(q)}' for k, q in b.items()))
b = between('V_never_share'); log('  never-used vs cue share between groups: ' + '  '.join(f'{k} {fp(q)}' for k, q in b.items()))
line('  latent place preference (old - never, first 10)', 'V_old_pull')
r = link('V_old_share', 'P10_rewards'); log(f"  old-place share vs P10 rewards: all rho {r['all'][0]:+.2f} ({fp(r['all'][1])}, n {r['all'][2]}), WT {r['WT'][0]:+.2f} ({fp(r['WT'][1])}), KO {r['KO'][0]:+.2f} ({fp(r['KO'][1])}); with group {fp(r['with group'])}")
r = link('V_old_pull', 'P10_rewards'); log(f"  latent place pref vs P10 rewards: all rho {r['all'][0]:+.2f} ({fp(r['all'][1])}); with group {fp(r['with group'])}")
for v in ['V_old_pull', 'V_old_share']:
    rr, pv = spearmanr(KO[v], KO.pct); log(f'  within KO, {v} vs % KO: rho {rr:+.2f} ({fp(pv)}, n {len(KO)})')

log('\nHIDDEN phase 8: new place vs old place. Pull = % of directed runs to that place minus % to one never-used zone.')
for k in ['10', '20', 'all']:
    log(f'  first {k} runs:' if k != 'all' else '  all runs:')
    for g in GR:
        x = GM[g]; log(f'    {g}: new {x[f"H{k}_new_pct"].mean():.1f}%  old {x[f"H{k}_old_pct"].mean():.1f}%  never {x[f"H{k}_never_pct"].mean():.1f}%')
    for v, lab in [('new_pull', 'new - never'), ('old_pull', 'old - never'), ('place_pull', 'mean(new, old) - never')]:
        line(f'    {lab}', f'H{k}_{v}')
    for g in GR:
        x = GM[g]; log(f'    new vs old pull, paired, {g}: {fp(ttest_rel(x[f"H{k}_new_pull"], x[f"H{k}_old_pull"]).pvalue)}')
log('\nOLD-PLACE PULL, cue present (visible) vs cue gone (hidden), first 10 directed runs')
for g in GR:
    x = GM[g]; log(f'  {g}: visible {x.V_old_pull.mean():+.1f}  hidden {x.H_old_pull.mean():+.1f}  change {x.H_minus_V_old_pull.mean():+.1f}  paired {fp(ttest_rel(x.H_old_pull, x.V_old_pull).pvalue)}  mice up {int((x.H_minus_V_old_pull > 0).sum())}/{len(x)}')
b = between('H_minus_V_old_pull'); log('  change between groups: ' + '  '.join(f'{k} {fp(q)}' for k, q in b.items()))
log('\nLINKS (hidden first 20 runs)')
for x, y in [('V_old_pull', 'H20_old_pull'), ('V_old_pull', 'H20_new_pull'), ('H20_new_pull', 'P10_rewards'), ('H20_old_pull', 'P10_rewards'), ('H20_place_pull', 'P10_rewards')]:
    r = link(x, y); log(f"  {x} vs {y}: all rho {r['all'][0]:+.2f} ({fp(r['all'][1])}), WT {r['WT'][0]:+.2f} ({fp(r['WT'][1])}), KO {r['KO'][0]:+.2f} ({fp(r['KO'][1])}); with group {fp(r['with group'])}")
log('\nROBUSTNESS: without M52, M54, M59 (phase 8 dated before phase 7)')
Mx = M.drop([52, 54, 59], errors='ignore'); w = Mx[Mx.g == 'WT']
log(f"  WT n {len(w)}: visible latent pull {w.V_old_pull.mean():+.1f} ({fp(ttest_1samp(w.V_old_pull, 0).pvalue)}); old share Hi vs WT {fp(mw(GM['Hi'].V_old_share, w.V_old_share))}; "
    f"hidden new pull {w.H20_new_pull.mean():+.1f} ({fp(ttest_1samp(w.H20_new_pull, 0).pvalue)}), old pull {w.H20_old_pull.mean():+.1f} ({fp(ttest_1samp(w.H20_old_pull, 0).pvalue)})")
r = link('V_old_share', 'P10_rewards', Mx); log(f"  old-place share vs P10 rewards: all rho {r['all'][0]:+.2f} ({fp(r['all'][1])}); with group {fp(r['with group'])}")
open(os.path.join(OUT, 'phase8_stats.txt'), 'w').write('\n'.join(LOG) + '\n')

# ---------------------------------------------------------------- plotting helpers
def spread(vals, dx=0.07, width=0.3):
    """sideways offsets so that mice with equal (or near-equal) values sit side by side instead of on top of each other"""
    v = np.asarray(vals, float); rng_ = np.nanmax(v) - np.nanmin(v); tol = max(rng_, 1) * 0.035
    off = np.zeros(len(v)); order = np.argsort(v); clusters = []; cur = [order[0]]
    for i in order[1:]:
        if v[i] - v[cur[-1]] <= tol: cur.append(i)
        else: clusters.append(cur); cur = [i]
    clusters.append(cur)
    for c in clusters:
        k = len(c); d = min(dx, 2 * width / max(k - 1, 1))
        for j, i in enumerate(c): off[i] = (j - (k - 1) / 2) * d
    return off
def dot(ax, x, y, g, ied, s=26, z=4):   # colour = group; shape = IED status (diamond IED+, circle otherwise)
    ax.scatter(x, y, s=s, marker='D' if ied else 'o', color=COL[g], edgecolor='#fcfcfb', linewidth=0.6, zorder=z)
def meanbar(ax, x, vals, g, w=0.26):
    ax.plot([x - w, x + w], [np.mean(vals)] * 2, color=COL[g], lw=2.2, solid_capstyle='butt', zorder=3)
def star(p): return '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else 'ns'
def bracket(ax, x1, x2, y, p, h=2.0):
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], color=MUT, lw=0.8)
    ax.text((x1 + x2) / 2, y + h * 1.2, f'{star(p)} ({p:.3f})' if p >= 0.001 else '***', ha='center', va='bottom', fontsize=6.8,
            color=RED if p < 0.05 else MUT)
def title(ax, t, sub=None):
    ax.set_title(t, fontsize=9, color=INK, fontweight='bold', loc='left', pad=16 if sub else 6)
    if sub: ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=7.2, color=MUT, va='bottom')
def scatter_link(ax, x, y, xl, yl):
    s = M[[x, y, 'g', 'IED']].dropna(); dup = s.groupby([x, y]).cumcount(); nd = s.groupby([x, y])[x].transform('size')
    step = (s[x].max() - s[x].min()) * 0.035
    for (_, r), k, n in zip(s.iterrows(), dup, nd): dot(ax, r[x] + (k - (n - 1) / 2) * step, r[y], r.g, r.IED)
    ax.set_ylim(-1, s[y].max() * 1.45)
    r = link(x, y); a, b = np.polyfit(s[x].rank(), s[y], 1)
    sl, ic = np.polyfit(s[x], s[y], 1); xx = np.linspace(s[x].min(), s[x].max(), 50); ax.plot(xx, ic + sl * xx, color=INK, lw=1.0, zorder=2, alpha=0.6)
    sig = r['all'][1] < 0.05
    ax.text(0.02, 0.98, f"ρ = {r['all'][0]:+.2f}, {fp(r['all'][1])} (n = {r['all'][2]})\nWT only ρ = {r['WT'][0]:+.2f}, {fp(r['WT'][1])}\nwith group in model: {fp(r['with group'])}",
            transform=ax.transAxes, va='top', fontsize=7.0, color=RED if sig else MUT, linespacing=1.35)
    ax.set_xlabel(xl, fontsize=7.8); ax.set_ylabel(yl, fontsize=7.8)
LEG = [Line2D([], [], marker='o', ls='', color=COL[g], label={'WT': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}[g]) for g in GR] + \
      [Line2D([], [], marker='D', ls='', color='#9a9993', label='IED+ (diamond)')]

# ---------------------------------------------------------------- Figure 30: visible phase 8
fig, axs = plt.subplots(1, 3, figsize=(7.6, 3.35), gridspec_kw={'width_ratios': [1.35, 1, 1.05]})
ax = axs[0]
for i, g in enumerate(GR):
    x = GM[g]; xo, xn = i * 1.0 - 0.22, i * 1.0 + 0.22; oo = spread(x.V_old_share.values, 0.075, 0.18); on = spread(x.V_never_share.values, 0.075, 0.18)
    for (_, r), a, b_ in zip(x.iterrows(), oo, on):
        ax.plot([xo + a, xn + b_], [r.V_old_share, r.V_never_share], color=COL[g], lw=0.6, alpha=0.35, zorder=2)
        ax.scatter(xn + b_, r.V_never_share, s=18, marker='D' if r.IED else 'o', facecolor='#fcfcfb', edgecolor=COL[g], linewidth=0.8, zorder=4)
        dot(ax, xo + a, r.V_old_share, g, r.IED, s=22)
    ax.plot([xn - .15, xn + .15], [x.V_never_share.mean()] * 2, color=GRY, lw=2, zorder=3); ax.plot([xo - .15, xo + .15], [x.V_old_share.mean()] * 2, color=COL[g], lw=2.2, zorder=3)
ax.set_xticks([0, 1, 2]); ax.set_xticklabels(['WT', 'Lo', 'Hi']); ax.set_ylim(-4, 100); ax.set_xlim(-0.55, 2.55)
ax.set_ylabel('% of first 10 runs (zone vs cue)', fontsize=7.8)
b = between('V_old_share'); bracket(ax, -0.22, 1.78, 84, b['Hi vs WT'], h=2.5); bracket(ax, -0.22, 0.78, 72, b['Lo vs WT'], h=2.5)
title(ax, 'A  Place vs cue', 'filled: old place vs cue; open: never-used vs cue')
ax = axs[1]
for i, g in enumerate(GR):
    x = GM[g]; off = spread(x.V_old_pull.values, 0.07, 0.3)
    for (_, r), o in zip(x.iterrows(), off): dot(ax, i + o, r.V_old_pull, g, r.IED)
    meanbar(ax, i, x.V_old_pull, g); w = within('V_old_pull')[g][1]
    ax.text(i, 47, f'{star(w)}\n({w:.3f})', ha='center', va='bottom', fontsize=6.8, color=RED if w < 0.05 else MUT)
ax.axhline(0, color=GRY, lw=0.9, ls=(0, (4, 3))); ax.set_xticks([0, 1, 2]); ax.set_xticklabels(['WT', 'Lo', 'Hi']); ax.set_ylim(-45, 62); ax.set_xlim(-0.55, 2.55)
ax.set_ylabel('old place − never-used zone\n(% of first 10 directed runs)', fontsize=7.8)
title(ax, 'B  Latent place preference', 'vs 0: one-sample t')
ax = axs[2]; scatter_link(ax, 'V_old_share', 'P10_rewards', 'old-place share, visible (%)', 'rewards, phase 10 hidden')
title(ax, 'C  Predicts phase 10')
fig.suptitle('Phase 8 visible: place (old goal) vs cue (new goal)', x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
fig.legend(handles=LEG, loc='upper left', bbox_to_anchor=(0.01, 0.935), ncol=4, fontsize=7.4, handletextpad=0.2, columnspacing=1.2)
fig.subplots_adjust(left=0.09, right=0.985, bottom=0.14, top=0.745, wspace=0.42); fig.savefig(os.path.join(FIGS, 'fig30_phase8_visible.png'), dpi=200); plt.close()

# ---------------------------------------------------------------- Figure 31: hidden phase 8
fig, axs = plt.subplots(1, 3, figsize=(7.6, 3.35), gridspec_kw={'width_ratios': [1.35, 1.2, 1.05]})
ax = axs[0]
for i, g in enumerate(GR):
    x = GM[g]
    for j, (v, lab) in enumerate([('H20_new_pull', 'new'), ('H20_old_pull', 'old')]):
        xc = i * 1.0 + (j - 0.5) * 0.42; off = spread(x[v].values, 0.06, 0.18)
        for (_, r), o in zip(x.iterrows(), off):
            if j == 0: dot(ax, xc + o, r[v], g, r.IED, s=20)
            else: ax.scatter(xc + o, r[v], s=20, marker='D' if r.IED else 'o', facecolor='#fcfcfb', edgecolor=COL[g], linewidth=0.9, zorder=4)
        meanbar(ax, xc, x[v], g, w=0.15); w = within(v)[g][1]
        ax.text(xc, 61, star(w), ha='center', va='bottom', fontsize=7, color=RED if w < 0.05 else MUT)
ax.axhline(0, color=GRY, lw=0.9, ls=(0, (4, 3))); ax.set_xticks([0, 1, 2]); ax.set_xticklabels(['WT', 'Lo', 'Hi']); ax.set_ylim(-35, 72); ax.set_xlim(-0.55, 2.55)
ax.set_ylabel('place − never-used zone\n(% of first 20 directed runs)', fontsize=7.8)
title(ax, 'A  Both places draw runs', 'filled: new place; open: old place')
ax = axs[1]
for i, g in enumerate(GR):
    x = GM[g]; xv, xh = i - 0.22, i + 0.22; ov = spread(x.V_old_pull.values, 0.075, 0.18); oh = spread(x.H_old_pull.values, 0.075, 0.18)
    for (_, r), a, b_ in zip(x.iterrows(), ov, oh):
        ax.plot([xv + a, xh + b_], [r.V_old_pull, r.H_old_pull], color=COL[g], lw=0.7, alpha=0.45, zorder=2)
        ax.scatter(xv + a, r.V_old_pull, s=18, marker='D' if r.IED else 'o', facecolor='#fcfcfb', edgecolor=COL[g], linewidth=0.8, zorder=4)
        dot(ax, xh + b_, r.H_old_pull, g, r.IED, s=20)
    ax.plot([xv - .15, xv + .15], [x.V_old_pull.mean()] * 2, color=GRY, lw=2, zorder=3); ax.plot([xh - .15, xh + .15], [x.H_old_pull.mean()] * 2, color=COL[g], lw=2.2, zorder=3)
    pv = ttest_rel(x.H_old_pull, x.V_old_pull).pvalue
    ax.text(i, 55, f'{star(pv)} ({pv:.2f})\n{int((x.H_minus_V_old_pull > 0).sum())}↑ {int((x.H_minus_V_old_pull < 0).sum())}↓', ha='center', va='bottom', fontsize=6.6, color=MUT)
ax.axhline(0, color=GRY, lw=0.9, ls=(0, (4, 3))); ax.set_xticks([0, 1, 2]); ax.set_xticklabels(['WT', 'Lo', 'Hi']); ax.set_ylim(-45, 72); ax.set_xlim(-0.55, 2.55)
ax.set_ylabel('old place − never-used zone\n(% of first 10 directed runs)', fontsize=7.8)
title(ax, 'B  Old place: cue present → gone', 'open: visible; filled: hidden; paired t')
ax = axs[2]; scatter_link(ax, 'H20_place_pull', 'P10_rewards', 'place pull, hidden (%)', 'rewards, phase 10 hidden')
title(ax, 'C  Phase 10 rewards')
fig.suptitle('Phase 8 hidden: new place vs old place', x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
fig.legend(handles=LEG, loc='upper left', bbox_to_anchor=(0.01, 0.935), ncol=4, fontsize=7.4, handletextpad=0.2, columnspacing=1.2)
fig.subplots_adjust(left=0.09, right=0.985, bottom=0.14, top=0.745, wspace=0.42); fig.savefig(os.path.join(FIGS, 'fig31_phase8_hidden.png'), dpi=200); plt.close()
