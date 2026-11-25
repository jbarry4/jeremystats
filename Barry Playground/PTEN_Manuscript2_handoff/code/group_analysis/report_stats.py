"""Per-phase group comparisons for every probe measure (phase_tab.pkl), trained-vs-novel phase effects and slopes (phase_eff.pkl), and Spearman correlations with % KO with Benjamini-Hochberg q (corr.pkl).

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, numpy as np, pandas as pd, pyreadstat, itertools, warnings, json
from scipy import stats
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore'); pd.set_option('display.width',260); pd.set_option('display.max_rows',600); pd.set_option('display.max_columns',40)
df=pd.read_pickle('probe.pkl'); df=df[df.G3!='UNK'].copy()
V=['NumRewards','PGoalTime','NumEntrances','ReRatio','PTimeCenter','PTimeAnnulus','MeanSpeed','MeanTargSpeed']
def perm(a,b):
    from math import comb
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
    if comb(len(x),n)<=50000:
        c=t=0
        for idx in itertools.combinations(range(len(x)),n):
            m=np.zeros(len(x),bool); m[list(idx)]=True; t+=1; c+=abs(x[m].mean()-x[~m].mean())>=obs-1e-12
        return c/t
    rng=np.random.default_rng(0); c=0
    for _ in range(20000):
        p=rng.permutation(x); c+=abs(p[:n].mean()-p[n:].mean())>=obs-1e-12
    return (c+1)/20001
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

def bh(p):
    p=np.array(p,float); o=np.argsort(p); q=np.empty(len(p)); pr=1
    for r,i in enumerate(o[::-1]):
        k=len(p)-r; pr=min(pr,p[i]*len(p)/k); q[i]=pr
    return q
rows=[]
for c in ['V','H']:
    for v in V:
        for ph in [7,8,9,10]:
            d=df[(df.Condition==c)&(df.Phase==ph)]; g={k:d[d.G3==k][v].values for k in ['CTL','Lo','Hi']}
            rows.append(dict(cond=c,var=v,phase=ph,CTL=g['CTL'].mean(),CTLse=stats.sem(g['CTL']),Lo=g['Lo'].mean(),Lose=stats.sem(g['Lo']),Hi=g['Hi'].mean(),Hise=stats.sem(g['Hi']),
                p_LoCTL=perm(g['Lo'],g['CTL']),p_HiCTL=perm(g['Hi'],g['CTL']),p_LoHi=perm(g['Lo'],g['Hi'])))
R=pd.DataFrame(rows)
for k in ['p_LoCTL','p_HiCTL','p_LoHi']: R['q'+k[1:]]=bh(R[k].values)
R.to_pickle('phase_tab.pkl'); print(R.round(4).to_string(index=False))
print("\n=== PHASE EFFECTS ===")
out=[]
for c in ['V','H']:
    for v in V:
        d=df[df.Condition==c].copy(); d['ph']=d.Phase.astype(int).astype(str)
        # omnibus group x phase (categorical) LRT, ML
        try:
            m1=smf.mixedlm(f"{v}~C(G3)*C(ph)",d,groups=d.MouseID).fit(reml=False); m0=smf.mixedlm(f"{v}~C(G3)+C(ph)",d,groups=d.MouseID).fit(reml=False)
            pint=stats.chi2.sf(2*(m1.llf-m0.llf),6)
            mg=smf.mixedlm(f"{v}~C(ph)",d,groups=d.MouseID).fit(reml=False); pgrp=stats.chi2.sf(2*(m0.llf-mg.llf),2)
        except Exception as e: pint=pgrp=np.nan
        rec=dict(cond=c,var=v,p_group=pgrp,p_gxphase=pint)
        for g in ['CTL','Lo','Hi']:
            w=d[d.G3==g].pivot(index='MouseID',columns='Phase',values=v)
            fr=stats.friedmanchisquare(*[w[p].values for p in [7,8,9,10]]).pvalue
            nov=w[[8,9,10]].mean(axis=1); tr=w[7]; diff=(nov-tr).values
            pt=stats.ttest_rel(nov,tr).pvalue
            # exact sign-flip permutation
            n=len(diff); obs=abs(diff.mean()); cnt=0; tot=0
            if n<=14:
                for s in itertools.product([1,-1],repeat=n):
                    tot+=1; cnt+=abs((diff*np.array(s)).mean())>=obs-1e-12
                psf=cnt/tot
            else:
                rng=np.random.default_rng(0); S=rng.choice([1,-1],(20000,n)); psf=(np.sum(np.abs((S*diff).mean(1))>=obs-1e-12)+1)/20001
            sl=np.array([np.polyfit([7,8,9,10],w.loc[i].values,1)[0] for i in w.index]); ps=stats.ttest_1samp(sl,0).pvalue
            rec.update({f'{g}_P7':tr.mean(),f'{g}_nov':nov.mean(),f'{g}_pct':100*(nov.mean()-tr.mean())/tr.mean(),f'{g}_friedman':fr,f'{g}_t':pt,f'{g}_signflip':psf,f'{g}_slope':sl.mean(),f'{g}_slope_p':ps})
        # does the trained->novel change differ between groups?
        ch={}
        for g in ['CTL','Lo','Hi']:
            w=d[d.G3==g].pivot(index='MouseID',columns='Phase',values=v); ch[g]=(w[[8,9,10]].mean(axis=1)-w[7]).values
        rec.update(chg_LoCTL=perm(ch['Lo'],ch['CTL']),chg_HiCTL=perm(ch['Hi'],ch['CTL']),chg_LoHi=perm(ch['Lo'],ch['Hi']))
        out.append(rec)
P=pd.DataFrame(out); P.to_pickle('phase_eff.pkl'); print(P.round(4).T.to_string())
print("\n=== %KO vs outcome, per phase (PTEN n=11) ===")
cr=[]
k=df[df.pct.notna()]
for c in ['V','H']:
    for v in V:
        for ph in [7,8,9,10]:
            d=k[(k.Condition==c)&(k.Phase==ph)]; s=stats.spearmanr(d.pct,d[v]); r=stats.pearsonr(d.pct,d[v])
            cr.append(dict(cond=c,var=v,phase=ph,rho=s.statistic,p_rho=s.pvalue,r=r.statistic,p_r=r.pvalue))
        # change score
        w=k[k.Condition==c].pivot(index='MouseID',columns='Phase',values=v); ch=w[[8,9,10]].mean(axis=1)-w[7]; pc=k.drop_duplicates('MouseID').set_index('MouseID').pct.loc[ch.index]
        s=stats.spearmanr(pc,ch); r=stats.pearsonr(pc,ch); cr.append(dict(cond=c,var=v,phase='chg',rho=s.statistic,p_rho=s.pvalue,r=r.statistic,p_r=r.pvalue))
C=pd.DataFrame(cr); m=C.phase!='chg'; C.loc[m,'q_rho']=bh(C.loc[m,'p_rho'].values); C.to_pickle('corr.pkl'); print(C.round(3).to_string(index=False))
