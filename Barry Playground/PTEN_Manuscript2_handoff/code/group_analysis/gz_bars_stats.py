"""Per phase x group: time in each zone, Friedman test across zones, current vs each other zone (paired t), each zone vs WT (Mann-Whitney) -> bars.pkl.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work/gz) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(os.path.join(WORK,'gz'))
import pandas as pd, numpy as np, itertools, warnings
from scipy import stats
from math import comb
warnings.filterwarnings('ignore')
S=pd.read_pickle('gz.pkl')
def perm(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float); x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
    if comb(len(x),n)<=60000:
        c=t=0
        for idx in itertools.combinations(range(len(x)),n):
            m=np.zeros(len(x),bool); m[list(idx)]=True; t+=1; c+=abs(x[m].mean()-x[~m].mean())>=obs-1e-12
        return c/t
    rng=np.random.default_rng(0); P=np.array([rng.permutation(x) for _ in range(20000)]); return (np.sum(np.abs(P[:,:n].mean(1)-P[:,n:].mean(1))>=obs-1e-12)+1)/20001
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

def sf(d):
    d=np.asarray(d,float); s=np.array(list(itertools.product([1,-1],repeat=len(d)))) if len(d)<=16 else np.random.default_rng(0).choice([1,-1],(100000,len(d)))
    return np.mean(np.abs((s*d).mean(1))>=abs(d.mean())-1e-12)
rows=[]
for cond in ['H','V']:
    for ph in [7,8,9,10]:
        cur=ph-6; k=S[(S.Condition==cond)&(S.Phase==ph)]
        for g in ['CTL','Lo','Hi']:
            d=k[k.G3==g]; Z=d[['z1','z2','z3','z4']].values*100
            fr=stats.friedmanchisquare(*Z.T).pvalue
            rec=dict(cond=cond,phase=ph,group=g,n=len(d),friedman=fr)
            for z in range(1,5):
                rec[f'm{z}']=Z[:,z-1].mean(); rec[f'se{z}']=stats.sem(Z[:,z-1])
                rec[f'p_cur_vs_{z}']=np.nan if z==cur else sf(Z[:,cur-1]-Z[:,z-1])
                rec[f't_cur_vs_{z}']=np.nan if z==cur else stats.ttest_rel(Z[:,cur-1],Z[:,z-1]).pvalue   # paired t-test, used for the 'ns' marks in Figure 12
                if g!='CTL': rec[f'p_vsWT_{z}']=perm(Z[:,z-1],k[k.G3=='CTL'][f'z{z}'].values*100)
            rows.append(rec)
B=pd.DataFrame(rows); B.to_pickle('bars.pkl')
pd.set_option('display.width',260); pd.set_option('display.max_columns',40)
for cond in ['H','V']:
    print('=====',cond)
    for _,r in B[B.cond==cond].iterrows():
        cur=int(r.phase)-6
        s=' '.join([f"z{z}{'*' if z==cur else ' '}={r[f'm{z}']:.2f}" for z in range(1,5)])
        pc=' '.join([f"cur>z{z}:{r[f'p_cur_vs_{z}']:.3f}" for z in range(1,5) if z!=cur])
        vw=' '.join([f"z{z}vsWT:{r[f'p_vsWT_{z}']:.3f}" for z in range(1,5)]) if r.group!='CTL' else ''
        print(f"P{int(r.phase)} {r.group:3s} {s} | Friedman {r.friedman:.4f} | {pc} | {vw}")
