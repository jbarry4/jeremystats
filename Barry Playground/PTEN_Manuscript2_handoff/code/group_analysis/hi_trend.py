"""Hidden-session decline across phases 7-10: per-mouse slopes and steadiness of the Hi decline vs WT (slopes.pkl). Used by fig8.py.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import numpy as np, pandas as pd, itertools, warnings
from scipy import stats
from math import comb
warnings.filterwarnings('ignore')
df=pd.read_pickle('probe.pkl'); d=df[(df.G3!='UNK')&(df.Condition=='H')]
V=['NumRewards','ReRatio','PGoalTime','MeanTargSpeed','MeanSpeed','NumEntrances']
def perm(a,b):
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
    if comb(len(x),n)<=60000:
        c=t=0
        for idx in itertools.combinations(range(len(x)),n):
            m=np.zeros(len(x),bool); m[list(idx)]=True; t+=1; c+=abs(x[m].mean()-x[~m].mean())>=obs-1e-12
        return c/t
    rng=np.random.default_rng(0); c=0
    for _ in range(50000):
        p=rng.permutation(x); c+=abs(p[:n].mean()-p[n:].mean())>=obs-1e-12
    return (c+1)/50001
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

out={}
for v in V:
    print('==',v)
    for phs,lab in [([7,8,9,10],'7-10'),([8,9,10],'8-10 (novel only)')]:
        sl={}
        for g in ['CTL','Lo','Hi']:
            w=d[d.G3==g].pivot(index='MouseID',columns='Phase',values=v)[phs]
            sl[g]=np.array([np.polyfit(phs,w.loc[i].values,1)[0] for i in w.index])
            dec = -1 if v in ['NumRewards','ReRatio','PGoalTime','NumEntrances'] else 1
            pg=stats.page_trend_test((dec*w.values)) # increasing trend in dec*value
            print(f"  {lab} {g}: means {np.round(w.mean().values,3)} slope={sl[g].mean():.3f}±{stats.sem(sl[g]):.3f} t-p={stats.ttest_1samp(sl[g],0).pvalue:.4f} Page p={pg.pvalue:.4f} n_neg={int((sl[g]<0).sum())}/{len(sl[g])}")
        print(f"  {lab} slope diff: Hi vs CTL perm p={perm(sl['Hi'],sl['CTL']):.4f} MWU p={stats.mannwhitneyu(sl['Hi'],sl['CTL']).pvalue:.4f} | Hi vs Lo perm p={perm(sl['Hi'],sl['Lo']):.4f} | Lo vs CTL perm p={perm(sl['Lo'],sl['CTL']):.4f}")
        out[(v,lab)]=sl
    w=d[d.G3=='Hi'].pivot(index='MouseID',columns='Phase',values=v); print('  Hi per mouse:\n',w.round(3).to_string())
    # last vs first novel within Hi, and 10 vs 7
    for a,b in [(7,10),(8,10)]:
        for g in ['Hi','CTL','Lo']:
            w=d[d.G3==g].pivot(index='MouseID',columns='Phase',values=v); print(f"  {g} P{a} vs P{b}: {w[a].mean():.3f} -> {w[b].mean():.3f} paired t p={stats.ttest_rel(w[a],w[b]).pvalue:.4f}", end=' |')
        print()
pd.to_pickle(out,'slopes.pkl')
