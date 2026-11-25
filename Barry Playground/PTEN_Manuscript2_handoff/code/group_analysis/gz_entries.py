"""Joins zone times with entrances/rewards per session (gzM.pkl); pausing at the goal at phase 10.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work/gz) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(os.path.join(WORK,'gz'))
import pyreadstat, pandas as pd, numpy as np, itertools, warnings
from scipy import stats
from math import comb
warnings.filterwarnings('ignore')
S=pd.read_pickle('gz.pkl')
old,_=pyreadstat.read_sav(PROBE_SAV)
o=old[['MouseID','Phase','Condition','NumRewards','NumEntrances','PGoalTime','MeanSpeed','MeanTargSpeed']].rename(columns={'MouseID':'Mouse'})
o['Mouse']=o.Mouse.astype(int); o['Phase']=o.Phase.astype(int)
M=S.merge(o,on=['Mouse','Phase','Condition'],how='left')
print('unmatched',M.NumEntrances.isna().sum())
M['dwell_entry']=M.correct*1800/M.NumEntrances          # s per entry, current goal (new zone method)
M['dwell_entry_old']=M.PGoalTime*1800/M.NumEntrances
M['rew_entry']=M.NumRewards/M.NumEntrances
M['rew_time']=M.NumRewards*1.2; M['goal_s']=M.correct*1800; M['goal_s_old']=M.PGoalTime*1800
M['unrewarded_s']=M.goal_s_old-M.rew_time
# cross-checks
print('rewards x 1.2 s exceeds goal time (old zone method):',(M.rew_time>M.goal_s_old+1e-6).sum(),'of',len(M))
print('rewards x 1.2 s exceeds goal time (new zone method):',(M.rew_time>M.goal_s+1e-6).sum())
print('dwell/entry new vs old method r=',np.corrcoef(M.dwell_entry,M.dwell_entry_old)[0,1].round(3))
print('entries > 0 always?',(M.NumEntrances>0).all(), ' min entries',M.NumEntrances.min())
M.to_pickle('gzM.pkl')
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

for cond in ['H','V']:
    print('#####',cond)
    for ph in [7,8,9,10]:
        k=M[(M.Condition==cond)&(M.Phase==ph)]
        for v in ['NumEntrances','dwell_entry','rew_entry','MeanSpeed']:
            g={x:k[k.G3==x][v].values for x in ['CTL','Lo','Hi']}; ip=k[k.ied=='+'][v]; im=k[k.ied=='-'][v]; kk=k[k.pct.notna()]; r=stats.spearmanr(kk.pct,kk[v])
            print(f" P{ph} {v:13s} WT {g['CTL'].mean():.3f} Lo {g['Lo'].mean():.3f} Hi {g['Hi'].mean():.3f} | LoWT {perm(g['Lo'],g['CTL']):.3f} HiWT {perm(g['Hi'],g['CTL']):.3f} LoHi {perm(g['Lo'],g['Hi']):.3f} | IED+ {ip.mean():.3f} IED- {im.mean():.3f} p {perm(ip,im):.3f} | rho {r.statistic:+.2f} p {r.pvalue:.3f}")
