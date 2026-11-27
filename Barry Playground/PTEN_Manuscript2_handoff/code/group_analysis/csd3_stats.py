"""Statistics for the theta CSD / CNO / IED section (Figures 9, 10, 26, 27, S1, S2). Run after csd3_data.py.

Between groups: two-sided Mann-Whitney U. Within groups (baseline vs CNO): paired t-test.
Group x drug: linear mixed model y ~ group * drug, random intercept per mouse (statsmodels mixedlm); p of the interaction.
Regression on % KO: least squares (scipy linregress), WT at 0% KO; reported for all mice and for KO mice only.
ROC for IED status (WT = IED-negative), mice with CSD at baseline and after CNO:
    AUC = probability an IED mouse has the higher value (ties 0.5); 95% CI: 5000 bootstrap resamples within class (seed 0);
    p: Mann-Whitney; loss of AUC (baseline - CNO): paired bootstrap on the same mice (seed 1);
    'drop' = baseline - CNO as a predictor; best cutoff maximises sensitivity + specificity.
Comparison of measures (MML2 + GCL2 vs 4-layer average): paired bootstrap over mice (seed 5).
Writes work/csd3/csd3_stats.csv (one row per CSD measure).
"""
import os, sys, warnings
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, _ROOT)
from config import *
import numpy as np, pandas as pd
from scipy import stats
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore'); pd.set_option('display.width', 250)
d = pd.read_pickle(os.path.join(WORK, 'csd3', 'csd3.pkl'))
NAME = {'AVG4': '4-layer average', 'M2G2': 'MML2 + GCL2', 'MML2': 'MML2', 'GCL2': 'GCL2', 'MML1': 'MML1', 'GCL1': 'GCL1'}
G = ['WT', 'Lo', 'Hi']
mw = lambda a, b: stats.mannwhitneyu(a, b, alternative='two-sided').pvalue


def mixed(x, a, b, groups, ref, col='G', drop=()):
    x = x.dropna(subset=[a, b]); x = x[x[col].isin(groups) & ~x.mouse.isin(drop)]
    m = x[['mouse', col, a, b]].melt(id_vars=['mouse', col], value_vars=[a, b], var_name='drug', value_name='y')
    m['drug'] = (m.drug == b).astype(int); m['Kc'] = pd.Categorical(m[col], [ref] + [g for g in groups if g != ref])
    f = smf.mixedlm('y ~ Kc*drug', m, groups=m.mouse).fit()
    return {k.split('[T.')[1].split(']')[0]: float(f.pvalues[k]) for k in f.params.index if ':drug' in k}


K = lambda a, b: ((a[:, None] > b[None, :]) + 0.5 * (a[:, None] == b[None, :])).mean()
def auc(x, v): y = x.ied.values == 1; return K(x[v].values[y], x[v].values[~y])
def roc(x, v):
    x = x.dropna(subset=[v]); y = x.ied.values == 1; P, N = x[v].values[y], x[v].values[~y]; r = np.random.default_rng(0)
    lo, hi = np.percentile([K(r.choice(P, len(P)), r.choice(N, len(N))) for _ in range(5000)], [2.5, 97.5])
    cut = max(((P >= c).mean() + (N < c).mean() - 1, c, int((P >= c).sum()), int((N >= c).sum())) for c in np.unique(x[v]))
    return dict(auc=K(P, N), lo=lo, hi=hi, p=mw(P, N), cut=cut[1], tp=cut[2], fp=cut[3], npos=len(P), nneg=len(N))
def loss(x, a, b, seed=1):
    x = x.dropna(subset=[a, b]); y = x.ied.values == 1; A, B = x[a].values, x[b].values; P, N = np.where(y)[0], np.where(~y)[0]
    f = lambda i: K(A[i][y[i]], A[i][~y[i]]) - K(B[i][y[i]], B[i][~y[i]]); r = np.random.default_rng(seed)
    bs = np.array([f(np.r_[r.choice(P, len(P)), r.choice(N, len(N))]) for _ in range(5000)])
    return f(np.arange(len(x))), np.percentile(bs, 2.5), np.percentile(bs, 97.5), min(1, 2 * min((bs <= 0).mean(), (bs >= 0).mean()))
def reg(x, v):
    x = x.dropna(subset=[v]); r = stats.linregress(x.pct, x[v]); return r.rvalue, r.pvalue, len(x)
def pc(x, a, b): return 100 * (x[b].mean() - x[a].mean()) / x[a].mean()

rows = []
for L in NAME:
    a, b, ch = f'{L}_base', f'{L}_cno', f'{L}_chg'
    x = d.dropna(subset=[a]); pr = d.dropna(subset=[a, b]); both = pr
    o = {'measure': NAME[L]}
    for g in G:
        o[f'{g}_base'] = x[x.G == g][a].mean(); o[f'{g}_n_base'] = (x.G == g).sum()
        q = pr[pr.G == g]; o[f'{g}_cno'] = q[b].mean(); o[f'{g}_pctchg'] = pc(q, a, b); o[f'{g}_paired_p'] = stats.ttest_rel(q[b], q[a]).pvalue
        o[f'{g}_n_fall'] = f'{int((q[b] < q[a]).sum())}/{len(q)}'
    q = pr[pr.K == 'KO']; o['KO_base'] = x[x.K == 'KO'][a].mean(); o['KO_cno'] = q[b].mean(); o['KO_pctchg'] = pc(q, a, b); o['KO_paired_p'] = stats.ttest_rel(q[b], q[a]).pvalue
    for v, tag in [(a, 'base'), (b, 'cno'), (ch, 'chg')]:
        y = d.dropna(subset=[v])
        for g1, g2 in [('Lo', 'WT'), ('Hi', 'WT'), ('Lo', 'Hi')]: o[f'mw_{g1}{g2}_{tag}'] = mw(y[y.G == g1][v], y[y.G == g2][v])
        o[f'mw_KOWT_{tag}'] = mw(y[y.K == 'KO'][v], y[y.K == 'WT'][v])
    I = mixed(d, a, b, G, 'WT'); IL = mixed(d, a, b, G, 'Lo'); IK = mixed(d, a, b, ['WT', 'KO'], 'WT', col='K')
    o.update(x_Lo=I['Lo'], x_Hi=I['Hi'], x_HivLo=IL['Hi'], x_KO=IK['KO'])
    for v, tag in [(a, 'base'), (b, 'cno'), (ch, 'chg')]:
        o[f'r_{tag}'], o[f'p_r_{tag}'], o[f'n_r_{tag}'] = reg(d, v)
        o[f'rKO_{tag}'], o[f'p_rKO_{tag}'], _ = reg(d[d.K == 'KO'], v)
    ie = x[x.ied == 1][a]; ne = x[(x.K == 'KO') & (x.ied == 0)][a]; w = x[x.G == 'WT'][a]
    o.update(IED_base=ie.mean(), noIED_base=ne.mean(), mw_IEDnoIED_base=mw(ie, ne), mw_IEDWT_base=mw(ie, w), mw_noIEDWT_base=mw(ne, w))
    ic = pr[pr.ied == 1][b]; nc = pr[(pr.K == 'KO') & (pr.ied == 0)][b]; wc = pr[pr.G == 'WT'][b]
    o.update(IED_cno=ic.mean(), noIED_cno=nc.mean(), mw_IEDnoIED_cno=mw(ic, nc), mw_IEDWT_cno=mw(ic, wc))
    for v, tag in [(a, 'base'), (b, 'cno'), (f'{L}_drop', 'drop')]:
        for sub, st in [(both, 'all'), (both[both.K == 'KO'], 'KO')]:
            R = roc(sub, v)
            for k2, v2 in R.items(): o[f'roc_{st}_{tag}_{k2}'] = v2
    for sub, st in [(both, 'all'), (both[both.K == 'KO'], 'KO')]:
        o[f'loss_{st}'], o[f'loss_{st}_lo'], o[f'loss_{st}_hi'], o[f'loss_{st}_p'] = loss(sub, a, b)
    rows.append(o)
T = pd.DataFrame(rows).set_index('measure')
T.to_csv(os.path.join(WORK, 'csd3', 'csd3_stats.csv'))
print(T.T.to_string(float_format=lambda v: f'{v:.4f}'))

print('\n### Sensitivity, 4-layer average')
loo = {int(m): round(mixed(d, 'AVG4_base', 'AVG4_cno', G, 'WT', drop=[m])['Hi'], 4) for m in d[(d.G == 'Hi') & d.AVG4_cno.notna()].mouse}
print('Hi x drug leaving out each Hi mouse:', loo)
both = d.dropna(subset=['AVG4_base', 'AVG4_cno'])
for L in ['AVG4', 'M2G2']:
    print(f'{NAME[L]}: loss of AUC leaving out each mouse:', {int(m): round(loss(both[both.mouse != m], f'{L}_base', f'{L}_cno')[0], 3) for m in both.mouse})

print('\n### MML2 + GCL2 (and MML2) vs 4-layer average, paired bootstrap')
def cmp(A, B, kind, suf):
    va, vb = f'{A}_{suf}', f'{B}_{suf}'; x = d.dropna(subset=[va, vb]); r = np.random.default_rng(5)
    if kind == 'auc':
        f = lambda s: auc(s, va) - auc(s, vb); P, N = np.where(x.ied == 1)[0], np.where(x.ied == 0)[0]; idx = lambda: np.r_[r.choice(P, len(P)), r.choice(N, len(N))]
    else:
        f = lambda s: stats.pearsonr(s.pct, s[va])[0] - stats.pearsonr(s.pct, s[vb])[0]; idx = lambda: r.choice(len(x), len(x))
    bs = np.array([f(x.iloc[idx()]) for _ in range(5000)]); bs = bs[~np.isnan(bs)]
    return f(x), np.percentile(bs, 2.5), np.percentile(bs, 97.5), min(1, 2 * min((bs <= 0).mean(), (bs >= 0).mean())), len(x)
for A in ['M2G2', 'MML2']:
    for kind, suf, lab in [('auc', 'base', 'IED AUC, baseline'), ('auc', 'cno', 'IED AUC, CNO'), ('auc', 'drop', 'IED AUC, CNO drop'),
                           ('r', 'base', 'r with % KO, baseline'), ('r', 'chg', 'r with % KO, change')]:
        o = cmp(A, 'AVG4', kind, suf); print(f'{NAME[A]} - 4-layer, {lab:22s}: {o[0]:+.3f} [{o[1]:+.2f}, {o[2]:+.2f}] p={o[3]:.3f} n={o[4]}')
print('r between 4-layer average and MML2 + GCL2: baseline %.2f, CNO %.2f' % (d[['AVG4_base', 'M2G2_base']].corr().iloc[0, 1], d[['AVG4_cno', 'M2G2_cno']].corr().iloc[0, 1]))

print('\n### Goal-zone time (phases 8-9), M26 kept')
for k, lab in [('Vis', 'VISIBLE'), ('Goal', 'HIDDEN')]:
    a, b, ch = f'{k}_base', f'{k}_cno', f'{k}_chg'; x = d.dropna(subset=[a, b])
    print(lab)
    for g in G + ['KO']:
        q = x[x.K == 'KO'] if g == 'KO' else x[x.G == g]
        print(f'  {g:3s} n={len(q):2d} {q[a].mean():.2f} -> {q[b].mean():.2f}  change {q[ch].mean():+.2f}  paired p={stats.ttest_rel(q[b], q[a]).pvalue:.3f}  rise {(q[b] > q[a]).sum()}/{len(q)}')
    for tag, v in [('base', a), ('cno', b), ('chg', ch)]:
        print(f'  MW vs WT {tag}: Lo {mw(x[x.G == "Lo"][v], x[x.G == "WT"][v]):.3f}  Hi {mw(x[x.G == "Hi"][v], x[x.G == "WT"][v]):.3f}  KO {mw(x[x.K == "KO"][v], x[x.G == "WT"][v]):.3f}  Lo-Hi {mw(x[x.G == "Lo"][v], x[x.G == "Hi"][v]):.3f}')
    I = mixed(x, a, b, G, 'WT'); IL = mixed(x, a, b, G, 'Lo'); IK = mixed(x, a, b, ['WT', 'KO'], 'WT', col='K')
    I5 = mixed(x, a, b, G, 'WT', drop=[5]); IK5 = mixed(x, a, b, ['WT', 'KO'], 'WT', col='K', drop=[5])
    print(f'  x drug: Lo {I["Lo"]:.3f}  Hi {I["Hi"]:.3f}  Hi vs Lo {IL["Hi"]:.3f}  all KO {IK["KO"]:.3f} | without M5: Hi {I5["Hi"]:.3f}  all KO {IK5["KO"]:.3f}')
    for tag, v, src in [('base', a, d), ('cno', b, x), ('chg', ch, x)]:
        r, p, n = reg(src, v); rk, pk, nk = reg(src[src.K == 'KO'], v)
        print(f'  regression {tag}: all r={r:+.2f} p={p:.3f} n={n} | KO only r={rk:+.2f} p={pk:.3f} n={nk}')
    r, p, n = reg(x[x.mouse != 5], ch); print(f'  regression chg without M5: r={r:+.2f} p={p:.3f} n={n}')
    hp = x[(x.G == 'Hi')]; print('  Hi per mouse change:', hp[ch].round(2).to_dict())
