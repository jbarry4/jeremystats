"""Zone-time statistics by role and phase (perseveration analysis, Figures 11-15 text).

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
    rng=np.random.default_rng(0); P=np.array([rng.permutation(x) for _ in range(20000)])
    return (np.sum(np.abs(P[:,:n].mean(1)-P[:,n:].mean(1))>=obs-1e-12)+1)/20001
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

def signflip(d):
    d=np.asarray(d,float); n=len(d); obs=abs(d.mean())
    if n<=16:
        s=np.array(list(itertools.product([1,-1],repeat=n))); return np.mean(np.abs((s*d).mean(1))>=obs-1e-12)
    rng=np.random.default_rng(0); s=rng.choice([1,-1],(50000,n)); return np.mean(np.abs((s*d).mean(1))>=obs-1e-12)
for cond in ['H','V']:
    print(f"\n################ {cond} ################")
    for ph in [7,8,9,10]:
        k=S[(S.Condition==cond)&(S.Phase==ph)]; print(f"--- phase {ph}")
        for v in ['total','correct','sh_correct','recent','sh_recent','trained','sh_trained','old_mean','sh_oldmean','never_mean','sh_nevermean']:
            if k[v].isna().all(): continue
            g={x:k[k.G3==x][v].values for x in ['CTL','Lo','Hi']}; P=k[k.Group=='PTEN'][v].values
            ip=k[k.ied=='+'][v].values; im=k[k.ied=='-'][v].values
            kk=k[k.pct.notna()]; rho=stats.spearmanr(kk.pct,kk[v])
            print(f"  {v:12s} WT {g['CTL'].mean():.4f} Lo {g['Lo'].mean():.4f} Hi {g['Hi'].mean():.4f} | LoWT {perm(g['Lo'],g['CTL']):.3f} HiWT {perm(g['Hi'],g['CTL']):.3f} LoHi {perm(g['Lo'],g['Hi']):.3f} PTENvWT {perm(P,g['CTL']):.3f} | IED+ {ip.mean():.4f} IED- {im.mean():.4f} p {perm(ip,im):.3f} | rho%KO {rho.statistic:+.2f} p {rho.pvalue:.3f}")
        # within-group: old (recent) vs never-used zones, old mean vs never mean
        if ph in (8,9):
            for x in ['CTL','Lo','Hi']:
                s=k[k.G3==x]; d=(s.old_mean-s.never_mean).values; d2=(s.recent-s.never_mean).values
                print(f"  within {x}: old_mean-never {d.mean():+.4f} p {signflip(d):.3f} ({(d>0).sum()}/{len(d)} >0) | recent-never {d2.mean():+.4f} p {signflip(d2):.3f}")
        if ph==10:
            for x in ['CTL','Lo','Hi']:
                s=k[k.G3==x]; print(f"  within {x}: z1 {s.z1.mean():.4f} z2 {s.z2.mean():.4f} z3 {s.z3.mean():.4f} z4 {s.z4.mean():.4f} | z3 vs mean(z1,z2) p {signflip((s.z3-(s.z1+s.z2)/2).values):.3f} | z1 vs mean(z2,z3) p {signflip((s.z1-(s.z2+s.z3)/2).values):.3f} | correct-recent {(s.correct-s.recent).mean():+.4f} p {signflip((s.correct-s.recent).values):.3f}")
        # correct vs non-correct mean within group
        for x in ['CTL','Lo','Hi']:
            s=k[k.G3==x]; nc=(s.total-s.correct)/3; d=(s.correct-nc).values
            print(f"  {x}: correct vs mean other zone {d.mean():+.4f} p {signflip(d):.3f} ({(d>0).sum()}/{len(d)} prefer correct)")
