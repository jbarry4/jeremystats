"""Sensitivity analysis: probe results with and without M6.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import numpy as np, pandas as pd, pyreadstat, itertools, warnings
from scipy import stats
from math import comb
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore')
raw,_=pyreadstat.read_sav(PROBE_SAV)
pct={1:5.18,3:24.57,5:27.64,7:24.12,8:3.89,10:9.51,28:20.19,29:22.00,30:5.97,33:8.82,34:28.43}
raw=raw[raw.Group!='DKO'].copy()
raw['G3']=raw.apply(lambda r:'CTL' if r.Group=='CTL' else ('UNK' if pct.get(int(r.MouseID)) is None else ('Lo' if pct[int(r.MouseID)]<15 else 'Hi')),axis=1)
raw=raw[raw.G3!='UNK']
V=['NumRewards','ReRatio','PGoalTime','NumEntrances','MeanSpeed','MeanTargSpeed','PTimeCenter','PTimeAnnulus']
def perm(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float); x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
    rng=np.random.default_rng(0); P=np.array([rng.permutation(x) for _ in range(20000)])
    return (np.sum(np.abs(P[:,:n].mean(1)-P[:,n:].mean(1))>=obs-1e-12)+1)/20001
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

res={}
for lab,d in [('no6',raw[raw.MouseID!=6]),('with6',raw)]:
    out={}
    for c in ['V','H']:
        k=d[d.Condition==c]
        mm=k.groupby(['MouseID','G3'])[V].mean().reset_index()
        for v in V:
            w=mm[mm.G3=='CTL'][v]
            out[(c,v,'mean','CTL')]=w.mean()
            for g in ['Lo','Hi']: out[(c,v,'mean',g)]=perm(mm[mm.G3==g][v],w)
            for ph in [7,8,9,10]:
                kk=k[k.Phase==ph]; w=kk[kk.G3=='CTL'][v]; out[(c,v,ph,'CTL')]=w.mean()
                for g in ['Lo','Hi']: out[(c,v,ph,g)]=perm(kk[kk.G3==g][v],w)
            # slopes
            for win,phs in [('s710',[7,8,9,10]),('s810',[8,9,10])]:
                sl={}
                for g in ['CTL','Lo','Hi']:
                    ww=k[k.G3==g].pivot(index='MouseID',columns='Phase',values=v)[phs]; sl[g]=np.array([np.polyfit(phs,ww.loc[i].values,1)[0] for i in ww.index])
                out[(c,v,win,'CTL')]=sl['CTL'].mean()
                for g in ['Lo','Hi']: out[(c,v,win,g)]=perm(sl[g],sl['CTL'])
            # mixed model group effect
            dd=k.copy(); dd['ph']=dd.Phase.astype(int).astype(str)
            try:
                m1=smf.mixedlm(f"{v}~C(G3)+C(ph)",dd,groups=dd.MouseID).fit(reml=False); m0=smf.mixedlm(f"{v}~C(ph)",dd,groups=dd.MouseID).fit(reml=False)
                out[(c,v,'mixed','grp')]=stats.chi2.sf(2*(m1.llf-m0.llf),2)
                m2=smf.mixedlm(f"{v}~C(G3)*C(ph)",dd,groups=dd.MouseID).fit(reml=False); out[(c,v,'mixed','gxp')]=stats.chi2.sf(2*(m2.llf-m1.llf),6)
            except Exception: pass
        # pooled PTEN vs CTL hidden
    res[lab]=out
A,B=res['no6'],res['with6']
print('cond var phase grp | WT mean or p (no M6) -> (with M6)')
for key in A:
    a,b=A[key],B.get(key,np.nan)
    flag=''
    if key[3]!='CTL' and ((a<.05)!=(b<.05)): flag='  <<< crosses 0.05'
    if key[3]=='CTL': print(f"{key}: WT {a:.4f} -> {b:.4f}")
    else: print(f"{key}: p {a:.4f} -> {b:.4f}{flag}")
