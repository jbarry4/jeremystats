"""Figures for the theta CSD / CNO / IED section (current data). Run after csd3_data.py.
    Figure 9   fig9_csd_regression_main   theta CSD on % KO (WT at 0): 4-layer average, MML2 + GCL2, MML2, GCL2
    Figure 10  fig10_goal_vis_hid         goal-zone time on % KO: visible (top) and hidden (bottom)
    Figure 26  fig26_goal_pooled          hidden goal-zone time, all Pten KO vs WT, baseline and after CNO
    Figure 27  fig27_roc_main             ROC for clear IEDs and each mouse's baseline -> CNO, same four measures as Figure 9
    Figure S1  figS1_csd_regression_supp  as Figure 9 for MML1 and GCL1
    Figure S2  figS2_roc_supp             as Figure 27 for MML1 and GCL1
Regression line: least squares through all mice with the 95% confidence band of the fit. M26 excluded from CSD.
"""
import os, sys, warnings
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, _ROOT)
from config import *
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy import stats
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore')
plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 8.5, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': '#9a9993', 'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'axes.grid': True,
                     'grid.color': '#e9e8e3', 'grid.linewidth': 0.6, 'axes.axisbelow': True, 'legend.frameon': False})
INK = '#0b0b0b'; MUT = '#52514e'; RED = '#b3261e'; COL = {'WT': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948', 'KO': '#7a4fa0'}
NAME = {'AVG4': '4-layer average', 'M2G2': 'MML2 + GCL2', 'MML1': 'MML1', 'MML2': 'MML2', 'GCL1': 'GCL1', 'GCL2': 'GCL2'}
d = pd.read_pickle(os.path.join(WORK, 'csd3', 'csd3.pkl'))
rng = np.random.default_rng(3); d['xj'] = np.where(d.G == 'WT', rng.uniform(-0.7, 0.7, len(d)), d.pct)
fp = lambda p: 'p < 0.001' if p < 0.001 else f'p = {p:.3f}'
K = lambda a, b: ((a[:, None] > b[None, :]) + 0.5 * (a[:, None] == b[None, :])).mean()
def auc(x, v): y = x.ied.values == 1; return K(x[v].values[y], x[v].values[~y])
LEG = [Line2D([], [], marker='o', ls='', color=COL[k], label=k) for k in ['WT', 'Lo', 'Hi']] + [Line2D([], [], marker='D', ls='', color='#9a9993', label='IED')]


def panel(ax, v, title, ylab, xlabel=False):
    x = d.dropna(subset=[v]); X = x.pct.values; Y = x[v].values; n = len(X)
    sl, ic, r, p, se = stats.linregress(X, Y); xx = np.linspace(-1, 31, 200); yh = ic + sl * xx
    s = np.sqrt(np.sum((Y - (ic + sl * X)) ** 2) / (n - 2)); sxx = np.sum((X - X.mean()) ** 2)
    ci = stats.t.ppf(.975, n - 2) * s * np.sqrt(1 / n + (xx - X.mean()) ** 2 / sxx)
    ax.fill_between(xx, yh - ci, yh + ci, color='#b9b8b2', alpha=.35, lw=0, zorder=1); ax.plot(xx, yh, color=INK, lw=1.4, zorder=3)
    for _, rr in x.iterrows():
        ax.scatter(rr.xj, rr[v], s=30, marker='D' if rr.ied else 'o', color=COL[rr.G], edgecolor='#fcfcfb', linewidth=0.7, zorder=4)
    if v.endswith('_chg'): ax.axhline(0, color='#9a9993', lw=0.8)
    ax.axvline(15, color='#9a9993', lw=0.8, ls=(0, (4, 3)), zorder=1); ax.set_xlim(-2, 31)
    ax.set_title(title, fontsize=9, color=INK, fontweight='bold', loc='left', pad=14); ax.set_ylabel(ylab, fontsize=7.8)
    ax.text(0, 1.01, f"r = {r:+.2f}, {fp(p)}, n = {n}", transform=ax.transAxes, ha='left', va='bottom', fontsize=7.4,
            color=RED if p < 0.05 else MUT, fontweight='bold' if p < 0.05 else 'normal')
    if xlabel: ax.set_xlabel('% granule cells Pten KO (WT = 0)', fontsize=7.8)


def regfig(rows, fn, title, foot):
    h = 2.75 * len(rows) + 0.95; fig, axs = plt.subplots(len(rows), 3, figsize=(7.6, h), squeeze=False)
    for i, (k, lab, yl) in enumerate(rows):
        for j, (suf, cl) in enumerate([('base', 'Baseline'), ('cno', 'After CNO'), ('chg', 'CNO − baseline')]):
            panel(axs[i, j], f'{k}_{suf}', f'{lab}: {cl}' if j == 0 else cl, yl if j == 0 else '', xlabel=(i == len(rows) - 1))
    fig.suptitle(title, x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
    fig.legend(handles=LEG, loc='upper left', bbox_to_anchor=(0.01, 1 - 0.42 / h), ncol=4, fontsize=7.6, handletextpad=0.2)
    fig.text(0.5, 0.004, foot, ha='center', fontsize=7.0, color=MUT, wrap=True)
    fig.tight_layout(rect=(0, 0.014, 1, 1 - 0.62 / h)); fig.savefig(os.path.join(FIGS, fn + '.png'), dpi=200); plt.close()


def curve(x, v):
    y = x.ied.values == 1; X = x[v].values; th = np.r_[np.inf, np.sort(np.unique(X))[::-1]]
    return np.array([(X[~y] >= t).mean() for t in th]), np.array([(X[y] >= t).mean() for t in th])


def loss(x, a, b):
    y = x.ied.values == 1; A, B = x[a].values, x[b].values; P, N = np.where(y)[0], np.where(~y)[0]
    f = lambda i: K(A[i][y[i]], A[i][~y[i]]) - K(B[i][y[i]], B[i][~y[i]]); r = np.random.default_rng(1)
    bs = np.array([f(np.r_[r.choice(P, len(P)), r.choice(N, len(N))]) for _ in range(5000)])
    return f(np.arange(len(x))), min(1, 2 * min((bs <= 0).mean(), (bs >= 0).mean()))


def rocfig(order, fn, title):
    h = 2.85 * len(order) + 0.85
    fig, axs = plt.subplots(len(order), 2, figsize=(7.2, h), gridspec_kw={'width_ratios': [1, 1.35]}, squeeze=False)
    for i, L in enumerate(order):
        both = d.dropna(subset=[f'{L}_base', f'{L}_cno']); ax = axs[i, 0]; ax.plot([0, 1], [0, 1], color='#c9c8c2', lw=0.8, ls=':')
        for v, col, ls, lab in [(f'{L}_base', INK, '-', 'Baseline'), (f'{L}_cno', '#8a8983', '--', 'After CNO')]:
            y = both.ied.values == 1; a = auc(both, v); p = stats.mannwhitneyu(both[v].values[y], both[v].values[~y]).pvalue
            fx, ty = curve(both, v); ax.step(fx, ty, where='post', color=col, lw=2, ls=ls, label=f'{lab}  AUC {a:.2f} ({fp(p)})')
        ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.04); ax.set_aspect('equal')
        ax.legend(fontsize=6.6, loc='lower right', handlelength=1.4, borderaxespad=0.1)
        ax.set_ylabel('True-positive rate', fontsize=7.6); ax.set_xlabel('False-positive rate' if i == len(order) - 1 else '', fontsize=7.6)
        ax.set_title(f'{NAME[L]}: ROC', fontsize=9.5, color=INK, fontweight='bold', loc='left', pad=14)
        dd, pp = loss(both, f'{L}_base', f'{L}_cno')
        ax.text(0, 1.01, f"loss of AUC with CNO {dd:.2f}, {fp(pp)}", transform=ax.transAxes, fontsize=7.2, color=RED if pp < 0.05 else MUT, va='bottom')
        ax = axs[i, 1]
        cats = [('WT', both[both.G == 'WT']), ('KO, no IED', both[(both.G != 'WT') & (both.ied == 0)]), ('KO, IED', both[both.ied == 1])]
        for gi, (lab, s) in enumerate(cats):
            xs = np.array([gi - 0.17, gi + 0.17])
            for _, rr in s.iterrows():
                ax.plot(xs, [rr[f'{L}_base'], rr[f'{L}_cno']], color=COL[rr.G], alpha=0.6, lw=0.9, marker='D' if rr.ied else 'o', ms=3.4, mec='none')
            ax.plot(xs, [s[f'{L}_base'].mean(), s[f'{L}_cno'].mean()], color=INK, lw=2.2, zorder=5)
        X = both[f'{L}_base'].values; y = both.ied.values == 1
        cut = max(((X[y] >= q).mean() + (X[~y] < q).mean() - 1, q, int((X[y] >= q).sum()), int((X[~y] >= q).sum())) for q in np.unique(X))
        ax.axhline(cut[1], color='#9a9993', lw=0.9, ls='--')
        ax.text(-0.45, cut[1], f'best baseline cutoff: {cut[2]}/5 IED, {cut[3]}/16 false positives', fontsize=6.3, color=MUT, va='bottom')
        ax.set_xticks(range(3)); ax.set_xticklabels([q[0] for q in cats], fontsize=7.8); ax.set_xlim(-0.5, 2.5); ax.set_ylabel('Theta CSD', fontsize=7.6)
        ax.set_title('Each mouse, baseline → CNO', fontsize=9.5, color=INK, fontweight='bold', loc='left', pad=14)
        ad = auc(both, f'{L}_drop'); pdp = stats.mannwhitneyu(both[f'{L}_drop'].values[y], both[f'{L}_drop'].values[~y]).pvalue
        ax.text(0, 1.01, f"CNO drop as predictor: AUC {ad:.2f}, {fp(pdp)}", transform=ax.transAxes, fontsize=7.2, color=RED if pdp < 0.05 else MUT, va='bottom')
    fig.suptitle(title, x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
    fig.text(0.5, 0.004, 'Mice with CSD at baseline and after CNO: 5 IED vs 16 others (8 WT, 8 KO); WT counted as IED-negative.\n'
             'Green Lo, red Hi, diamond IED; black line = group mean. M26 excluded.', ha='center', fontsize=6.9, color=MUT)
    fig.tight_layout(rect=(0, 0.5 / h, 1, 1 - 0.35 / h)); fig.savefig(os.path.join(FIGS, fn + '.png'), dpi=200); plt.close()


FOOT = 'Least-squares fit through all mice, WT at 0% KO; band: 95% CI of the fit. Dashed line: 15% KO. Red: p < 0.05.'
regfig([(L, NAME[L], 'Theta CSD') for L in ['AVG4', 'M2G2', 'MML2', 'GCL2']], 'fig9_csd_regression_main',
       'Theta CSD on % KO: the measures that predict IEDs', FOOT + ' M26 excluded.')
regfig([('Vis', 'Visible goal', 'Goal-zone time (%)'), ('Goal', 'Hidden goal', 'Goal-zone time (%)')], 'fig10_goal_vis_hid',
       'Goal-zone time on % KO: visible (top) and hidden (bottom), phases 8–9', FOOT)
regfig([(L, NAME[L], 'Theta CSD') for L in ['MML1', 'GCL1']], 'figS1_csd_regression_supp',
       'Supplementary: theta CSD on % KO, MML1 and GCL1', FOOT + ' M26 excluded.')
rocfig(['AVG4', 'M2G2', 'MML2', 'GCL2'], 'fig27_roc_main', 'Theta CSD as a predictor of clear IEDs, before and after CNO')

# --- v3: the same two figures without the 4-layer average, for the combined circuit figure
regfig([(L, NAME[L], 'Theta CSD') for L in ['M2G2', 'MML2', 'GCL2']], 'fig12b_csd_regression',
       'Theta CSD on % KO: the lower-blade measures', FOOT + ' M26 excluded.')
rocfig(['M2G2', 'MML2', 'GCL2'], 'fig12c_roc',
       'Theta CSD as a predictor of clear IEDs, before and after CNO')
rocfig(['MML1', 'GCL1'], 'figS2_roc_supp', 'Supplementary: MML1 and GCL1 as predictors of IEDs')

# ---------- Figure 26: hidden goal time, all Pten KO pooled vs WT
x = d.dropna(subset=['Goal_base', 'Goal_cno']).copy()
m = x[['mouse', 'K', 'Goal_base', 'Goal_cno']].melt(id_vars=['mouse', 'K'], var_name='drug', value_name='y'); m['drug'] = (m.drug == 'Goal_cno').astype(int)
m['Kc'] = pd.Categorical(m.K, ['WT', 'KO']); inter = smf.mixedlm('y ~ Kc*drug', m, groups=m.mouse).fit().pvalues['Kc[T.KO]:drug']
pchg = stats.mannwhitneyu(x[x.K == 'KO'].Goal_chg, x[x.K == 'WT'].Goal_chg).pvalue
fig = plt.figure(figsize=(6.6, 3.5))
ax = fig.add_axes([0.08, 0.2, 0.27, 0.62])
for g, off in [('WT', -0.03), ('KO', 0.03)]:
    q = x[x.K == g]
    ax.errorbar(np.array([0, 1]) + off, [q.Goal_base.mean(), q.Goal_cno.mean()], yerr=[q.Goal_base.sem(), q.Goal_cno.sem()], color=COL[g], marker='o', ms=5.5,
                lw=2, capsize=2.5, mec='#fcfcfb', label=('WT' if g == 'WT' else 'All Pten KO') + f' (n={len(q)})')
ax.set_xticks([0, 1]); ax.set_xticklabels(['Baseline', 'After CNO'], fontsize=8.5); ax.set_xlim(-0.35, 1.35)
ax.set_ylabel('Time in goal (% of session), P8–9', fontsize=8); ax.legend(fontsize=7.4, loc='upper left')
ax.set_title('Group means ± SE', fontsize=9.5, color=INK, fontweight='bold', loc='left', pad=16)
ax.text(0, 1.015, f"group × CNO {fp(inter)}", transform=ax.transAxes, fontsize=7.6, color=MUT, va='bottom')
ax = fig.add_axes([0.42, 0.2, 0.27, 0.62])
for gi, g in enumerate(['WT', 'KO']):
    xs = np.array([gi - 0.18, gi + 0.18])
    for _, rr in x[x.K == g].iterrows():
        ax.plot(xs, [rr.Goal_base, rr.Goal_cno], color=COL[rr.G], alpha=0.55, lw=0.9, marker='D' if rr.ied else 'o', ms=3.2, mec='none')
ax.set_xticks([0, 1]); ax.set_xticklabels(['WT', 'All Pten KO'], fontsize=8.5); ax.set_xlim(-0.5, 1.5)
ax.set_title('Each mouse, baseline → CNO', fontsize=9.5, color=INK, fontweight='bold', loc='left', pad=16)
ax.text(0, 1.015, 'Pten KO: green = Lo, red = Hi, diamond = IED', transform=ax.transAxes, fontsize=7.2, color=MUT, va='bottom')
ax = fig.add_axes([0.77, 0.2, 0.21, 0.62])
for gi, g in enumerate(['WT', 'KO']):
    q = x[x.K == g]; xs = gi + np.random.default_rng(2).uniform(-0.12, 0.12, len(q))
    for xi, (_, rr) in zip(xs, q.iterrows()):
        ax.scatter(xi, rr.Goal_chg, s=22, color=COL[rr.G], marker='D' if rr.ied else 'o', edgecolor='#fcfcfb', lw=0.6, zorder=3)
    ax.plot([gi - 0.25, gi + 0.25], [q.Goal_chg.mean()] * 2, color=INK, lw=2, zorder=4)
ax.axhline(0, color='#9a9993', lw=0.8); ax.set_xticks([0, 1]); ax.set_xticklabels(['WT', 'All KO'], fontsize=8.5); ax.set_xlim(-0.6, 1.6)
ax.set_ylabel('CNO − baseline (points)', fontsize=8)
ax.set_title('Change with CNO', fontsize=9.5, color=INK, fontweight='bold', loc='left', pad=16)
ax.text(0, 1.015, f"Mann-Whitney {fp(pchg)}", transform=ax.transAxes, fontsize=7.6, color=MUT, va='bottom')
fig.suptitle('Hidden goal-zone time after CNO: all Pten KO mice vs WT', x=.01, ha='left', fontsize=11.5, fontweight='bold', color=INK, y=.985)
fig.text(0.5, 0.02, 'Hidden-goal sessions, phases 8 and 9 averaged. Bars in the right panel are group means.', ha='center', fontsize=7.4, color=MUT)
fig.savefig(os.path.join(FIGS, 'fig26_goal_pooled.png'), dpi=200); plt.close()
print('figures written to', FIGS)
