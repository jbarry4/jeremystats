"""SUPERSEDED (uses the Data4Claude.xlsx summary; see group_analysis/csd3_*.py for the current analysis).

Standalone statistics for the theta CSD / CNO / IED section of the report (Figures 9, 10, 26 and 27).

Usage
    python csd_cno_ied_stats.py Data4Claude.xlsx

Needs only numpy, pandas, scipy and statsmodels. Prints every number reported in that section.
Nothing here reads any other file; the only input is the Data4Claude workbook (version with WT rows).

Input columns, in order (the names in the sheet are not used, only the order):
    Group                         'PTEN -No IED', 'PTEN -IED' or 'WT'
    UVM #                         mouse number (WT written as 'M22' etc.)
    JB % hits                     percent Pten KO granule cells (blank for WT)
    BaseTheta CSD MML-GCL 1 and 2 baseline theta CSD, the average of all channels in MML1, MML2, GCL1 and GCL2
    CNOTheta CSD MML-GCL 1 and 2  the same after CNO
    SpA_Base_P8, Spa_Base_P9, Spa_Base_P8andP9          goal-zone time, baseline, hidden phases 8, 9 and their mean
    SpA_PostCNO_P8, Spa_PostCNO_P9, Spa_PostCNO_P8andP9 the same after CNO

Choices made in the analysis (all as in the report)
    * Lo vs Hi: KO < 15% is Lo, >= 15% is Hi. WT are a separate group.
    * WT are given 0% KO for the regressions on percent KO ("WT at 0%").
    * WT count as IED-negative for the ROC (Figure 27).
    * Goal-zone time is the P8-P9 mean, multiplied by 100 (percent of session).
    * Between groups: two-sided Mann-Whitney U. Within groups (baseline vs CNO): paired t-test.
    * Group x drug: linear mixed model, y ~ group * drug, random intercept per mouse
      (statsmodels mixedlm, REML). The p value reported is the group:drug interaction term.
    * Regression on percent KO: ordinary least squares (scipy linregress) with Pearson r;
      Spearman rho alongside. The 95% band in the figures is the confidence band of the fitted line.
    * ROC: AUC = Mann-Whitney probability that an IED mouse has the higher value (ties count 0.5);
      95% CI from 5000 bootstrap resamples within each class (seed 0); p from Mann-Whitney;
      baseline vs CNO AUC compared on the same mice with a paired bootstrap (seed 1);
      best cutoff = max(sensitivity + specificity - 1), classifying value >= cutoff as IED.
    * Mice enter each test when they have the values that test needs, so n differs between tests.
"""
import sys, warnings
import numpy as np, pandas as pd
from scipy import stats
import statsmodels.formula.api as smf

warnings.filterwarnings('ignore')
pd.set_option('display.width', 220)
f = sys.argv[1] if len(sys.argv) > 1 else 'Data4Claude.xlsx'

# ---------------------------------------------------------------- data
d = pd.read_excel(f)
d.columns = ['grp', 'mouse', 'pct', 'csd_base', 'csd_cno', 'b8', 'b9', 'goal_base', 'c8', 'c9', 'goal_cno']
d['mouse'] = d.mouse.astype(str).str.replace('M', '').astype(int)
d['G'] = np.where(d.grp == 'WT', 'WT', np.where(d.pct < 15, 'Lo', 'Hi'))
d.loc[d.G == 'WT', 'pct'] = 0.0                      # WT at 0% KO
d['ied'] = d.grp.eq('PTEN -IED')                     # WT and 'PTEN -No IED' are IED-negative
for c in ['goal_base', 'goal_cno', 'b8', 'b9', 'c8', 'c9']:
    d[c] *= 100                                      # fraction -> percent of session
d['csd_d'] = d.csd_cno - d.csd_base
d['csd_pc'] = 100 * d.csd_d / d.csd_base
d['goal_d'] = d.goal_cno - d.goal_base
G = ['WT', 'Lo', 'Hi']

print('Per mouse:')
print(d[['G', 'mouse', 'pct', 'ied', 'csd_base', 'csd_cno', 'csd_pc', 'goal_base', 'goal_cno', 'goal_d']]
      .round(4).to_string(index=False))


def mw(a, b):
    return stats.mannwhitneyu(a, b, alternative='two-sided').pvalue


def mixed(df, a, b, groups, ref, drop=()):
    """group x drug mixed model; returns {term: (estimate, p)} for the interaction terms."""
    x = df.dropna(subset=[a, b])
    x = x[~x.mouse.isin(drop)]
    x = x[x.K.isin(groups)][['mouse', 'K', a, b]]
    m = x.melt(id_vars=['mouse', 'K'], value_vars=[a, b], var_name='drug', value_name='y')
    m['drug'] = (m.drug == b).astype(int)
    m['Kc'] = pd.Categorical(m.K, [ref] + [g for g in groups if g != ref])
    fit = smf.mixedlm('y ~ Kc*drug', m, groups=m.mouse).fit()
    return {k.replace('Kc[T.', '').replace(']', ''): (round(float(fit.params[k]), 5), round(float(fit.pvalues[k]), 5))
            for k in fit.params.index if ':drug' in k}


# ---------------------------------------------------------------- 1. group comparisons (Mann-Whitney)
print('\n### 1. Group means and Mann-Whitney p (Figure 9 and 10 tables)')
for v in ['csd_base', 'csd_cno', 'csd_d', 'csd_pc', 'goal_base', 'goal_cno', 'goal_d']:
    x = d.dropna(subset=[v]); g = {k: x[x.G == k][v] for k in G}
    s = '  '.join(f'{k} {g[k].mean():.4f} (n={len(g[k])})' for k in G)
    p = '  '.join(f'{a}-{b} {mw(g[a], g[b]):.4f}' for a, b in [('Lo', 'WT'), ('Hi', 'WT'), ('Lo', 'Hi')])
    print(f'{v:10s} {s} | {p}')

# ---------------------------------------------------------------- 2. paired baseline vs CNO
print('\n### 2. Baseline vs CNO within group (paired t-test)')
for a, b in [('csd_base', 'csd_cno'), ('goal_base', 'goal_cno')]:
    for k in G + ['All KO']:
        x = d.dropna(subset=[a, b]); x = x[x.G != 'WT'] if k == 'All KO' else x[x.G == k]
        t = stats.ttest_rel(x[b], x[a])
        print(f'{a[:-5]:5s} {k:6s} n={len(x):2d} {x[a].mean():.4f} -> {x[b].mean():.4f} '
              f'({100 * (x[b].mean() - x[a].mean()) / x[a].mean():+.0f}%)  p={t.pvalue:.4f}  '
              f'fall {(x[b] < x[a]).sum()}/{len(x)}')

# ---------------------------------------------------------------- 3. group x drug mixed models
print('\n### 3. Group x drug interaction (mixed model, random intercept per mouse)')
d['K'] = d.G
for a, b in [('csd_base', 'csd_cno'), ('goal_base', 'goal_cno')]:
    print(a[:-5], 'Lo and Hi vs WT:', mixed(d, a, b, G, 'WT'))
    print(a[:-5], 'Hi vs Lo:       ', mixed(d, a, b, G, 'Lo'))
d['K'] = np.where(d.G == 'WT', 'WT', 'KO')
for a, b in [('csd_base', 'csd_cno'), ('goal_base', 'goal_cno')]:
    print(a[:-5], 'all KO vs WT (Figure 26):', mixed(d, a, b, ['WT', 'KO'], 'WT'))

# pooled KO vs WT, Mann-Whitney (Figure 26 table and the 'All Pten KO mice together' CSD bullet)
for v in ['csd_base', 'csd_cno', 'csd_d']:
    x = d.dropna(subset=[v])
    print(f'pooled {v}: WT {x[x.K == "WT"][v].mean():.4f}  KO {x[x.K == "KO"][v].mean():.4f}  '
          f'MW p={mw(x[x.K == "KO"][v], x[x.K == "WT"][v]):.4f}')
for v in ['goal_base', 'goal_cno', 'goal_d']:
    x = d.dropna(subset=['goal_base', 'goal_cno'])
    print(f'pooled {v}: WT {x[x.K == "WT"][v].mean():.3f}  KO {x[x.K == "KO"][v].mean():.3f}  '
          f'MW p={mw(x[x.K == "KO"][v], x[x.K == "WT"][v]):.4f}')

# ---------------------------------------------------------------- 4. regression on percent KO
print('\n### 4. Linear regression on percent KO (WT at 0%, all mice; and KO mice only)')
def regress(x, v):
    lr = stats.linregress(x.pct, x[v]); s = stats.spearmanr(x.pct, x[v])
    return (f'n={len(x):2d} slope={lr.slope:+.6f} intercept={lr.intercept:+.5f} r={lr.rvalue:+.2f} '
            f'p={lr.pvalue:.4f} | rho={s.statistic:+.2f} p={s.pvalue:.4f}')
for v in ['csd_base', 'csd_cno', 'csd_d', 'goal_base', 'goal_cno', 'goal_d']:
    for lab, x in [('all mice', d), ('KO only', d[d.G != 'WT'])]:
        print(f'{v:10s} {lab:9s} {regress(x.dropna(subset=[v]), v)}')

# ---------------------------------------------------------------- 5. sensitivity checks quoted in the text
print('\n### 5. Sensitivity')
d['K'] = d.G
loo = {int(m): mixed(d, 'csd_base', 'csd_cno', G, 'WT', drop=[m])['Hi:drug'][1]
       for m in d[(d.G == 'Hi')].dropna(subset=['csd_base', 'csd_cno']).mouse}
print('CSD Hi vs WT interaction, leaving out each Hi mouse:', loo, ' max p =', max(loo.values()))
print('Goal, without M5:  Lo/Hi vs WT', mixed(d, 'goal_base', 'goal_cno', G, 'WT', drop=[5]))
d['K'] = np.where(d.G == 'WT', 'WT', 'KO')
print('Goal, without M5:  all KO vs WT', mixed(d, 'goal_base', 'goal_cno', ['WT', 'KO'], 'WT', drop=[5]))
x = d[d.mouse != 5].dropna(subset=['goal_d'])
print('goal_d on % KO without M5 (all mice):', regress(x, 'goal_d'))

# ---------------------------------------------------------------- 6. CSD by IED status
print('\n### 6. Theta CSD by IED status (KO mice with and without IEDs, and WT)')
for v in ['csd_base', 'csd_cno', 'csd_d']:
    x = d.dropna(subset=[v]); a = x[x.ied][v]; b = x[(x.G != 'WT') & ~x.ied][v]; w = x[x.G == 'WT'][v]
    print(f'{v:9s} IED {a.mean():.4f} (n={len(a)})  KO no IED {b.mean():.4f} (n={len(b)})  WT {w.mean():.4f} (n={len(w)}) | '
          f'IED-noIED p={mw(a, b):.4f}  IED-WT p={mw(a, w):.4f}  noIED-WT p={mw(b, w):.4f}')

# ---------------------------------------------------------------- 7. ROC: does CSD predict IEDs? (Figure 27)
print('\n### 7. ROC for IED status (Figure 27). WT = IED-negative.')
K = lambda a, b: ((a[:, None] > b[None, :]) + 0.5 * (a[:, None] == b[None, :])).mean()
def roc(x, v):
    x = x.dropna(subset=[v]); y = x.ied.values; P, N = x[v].values[y], x[v].values[~y]
    r = np.random.default_rng(0)
    lo, hi = np.percentile([K(r.choice(P, len(P)), r.choice(N, len(N))) for _ in range(5000)], [2.5, 97.5])
    cut = max(((P >= c).mean() + (N < c).mean() - 1, c, (P >= c).mean(), (N < c).mean()) for c in np.unique(x[v]))
    return (f'IED {len(P)} vs {len(N)}  AUC={K(P, N):.3f} (95% CI {lo:.2f}-{hi:.2f}) p={mw(P, N):.4f}  '
            f'cutoff>={cut[1]:.4f} sens={cut[2]:.2f} spec={cut[3]:.2f}')
def paired_auc(x):
    x = x.dropna(subset=['csd_base', 'csd_cno']); y = x.ied.values; A, B = x.csd_base.values, x.csd_cno.values
    P, N = np.where(y)[0], np.where(~y)[0]
    fdiff = lambda i: K(A[i][y[i]], A[i][~y[i]]) - K(B[i][y[i]], B[i][~y[i]])
    r = np.random.default_rng(1)
    bs = np.array([fdiff(np.r_[r.choice(P, len(P)), r.choice(N, len(N))]) for _ in range(5000)])
    return (f'AUC baseline - AUC CNO = {fdiff(np.arange(len(x))):.3f} (95% CI {np.percentile(bs, 2.5):.2f}-'
            f'{np.percentile(bs, 97.5):.2f}) p={min(1, 2 * min((bs <= 0).mean(), (bs >= 0).mean())):.3f}')
d['drop'] = d.csd_base - d.csd_cno                   # larger = bigger fall with CNO
both = d.dropna(subset=['csd_base', 'csd_cno'])
for lab, x in [('all mice', both), ('KO only', both[both.G != 'WT'])]:
    print(f'-- {lab} (mice with CSD at baseline and after CNO, n={len(x)})')
    for v in ['csd_base', 'csd_cno', 'drop']:
        print(f'   {v:9s} {roc(x, v)}')
    print('  ', paired_auc(x))
    xs = both if lab == 'all mice' else both[both.G != 'WT']
    loo = {int(m): round(float(paired_auc(xs[xs.mouse != m]).split('= ')[1].split(' ')[0]), 3) for m in xs.mouse}
    print('   leave-one-out AUC difference:', loo)
allcsd = d.dropna(subset=['csd_base'])
print('-- all mice with baseline CSD, incl. WT without CNO (n=%d)' % len(allcsd))
print('   csd_base ', roc(allcsd, 'csd_base'))
print('   % KO     ', roc(allcsd, 'pct'))
print('   % KO, KO only', roc(allcsd[allcsd.G != 'WT'], 'pct'))
