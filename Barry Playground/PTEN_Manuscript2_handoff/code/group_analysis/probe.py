"""RUN FIRST. Reads AllProbeSessions.sav, drops DKO mice, adds group labels (G3: CTL / Lo < 15% KO / Hi > 15% KO / UNK = no histology), % KO, heterotopia and IED labels; writes probe.pkl and mm.pkl (per-mouse means). Prints the probe-session group comparisons (Figures 3-4 statistics). Usage: python probe.py [AllProbeSessions.sav]

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, numpy as np, pandas as pd, pyreadstat, itertools, warnings
from scipy import stats
warnings.filterwarnings('ignore')
pd.set_option('display.width',250); pd.set_option('display.max_rows',500); pd.set_option('display.max_columns',40)
df,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else PROBE_SAV)); df=df[(df.Group!="DKO")].copy()
pct={1:5.18,3:24.57,5:27.64,7:24.12,8:3.89,10:9.51,28:20.19,29:22.00,30:5.97,33:8.82,34:28.43}
crit={1:22,3:14,5:9,7:9,8:21,10:28,27:8,28:8,29:25,30:20,31:27,33:15,34:19}
hbh={8,10,27,29,30}; iedp={3,5,28,34}; iedm={1,7,8,10,29,30,33}
def g3(r):
    if r.Group=='CTL': return 'CTL'
    p=pct.get(int(r.MouseID)); return 'UNK' if p is None else ('Lo' if p<15 else 'Hi')
df['G3']=df.apply(g3,axis=1); df['pct']=df.MouseID.map(pct); df['HBH']=df.MouseID.isin(hbh); 
df['IED']=df.MouseID.map(lambda m:'+' if m in iedp else ('-' if m in iedm else 'NR'))
V=['NumRewards','PGoalTime','NumEntrances','ReRatio','PTimeCenter','PTimeAnnulus','MeanSpeed','MeanTargSpeed']
df.to_pickle('probe.pkl')
mm=df.groupby(['MouseID','G3','Group','HBH','IED','Condition'])[V].mean().reset_index(); mm['pct']=mm.MouseID.map(pct); mm['crit']=mm.MouseID.map(crit)
mm.to_pickle('mm.pkl')
def perm(a,b):
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
    from math import comb
    if comb(len(x),n)<=20000:
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

def hedges(a,b):
    na,nb=len(a),len(b); sp=np.sqrt(((na-1)*a.var(ddof=1)+(nb-1)*b.var(ddof=1))/(na+nb-2)); return (a.mean()-b.mean())/sp*(1-3/(4*(na+nb)-9))
def bh(p):
    p=np.array(p); o=np.argsort(p); q=np.empty(len(p)); pr=1
    for r,i in enumerate(o[::-1]):
        k=len(p)-r; pr=min(pr,p[i]*len(p)/k); q[i]=pr
    return q
print("=== mouse-level means (across 4 probe phases) by group ===")
for c in ['V','H']:
    d=mm[mm.Condition==c]
    print(c); print(d.groupby('G3')[V].agg(['mean','sem']).round(3).T.unstack().to_string())
def table(name,sel_a,sel_b):
    rows=[]
    for c in ['V','H']:
        d=mm[mm.Condition==c]
        for v in V:
            a=d[sel_a(d)][v].values; b=d[sel_b(d)][v].values
            t=stats.ttest_ind(a,b,equal_var=False); u=stats.mannwhitneyu(a,b,alternative='two-sided')
            rows.append(dict(cond=c,var=v,na=len(a),nb=len(b),mA=a.mean(),mB=b.mean(),g=hedges(a,b),welch_p=t.pvalue,mwu_p=u.pvalue,auc=u.statistic/(len(a)*len(b)),perm_p=perm(a,b)))
    r=pd.DataFrame(rows); r['perm_q']=bh(r.perm_p.values)
    print(f"\n=== {name} (A vs B) ==="); print(r.round(4).to_string(index=False))
table("Lo vs Hi",lambda d:d.G3=='Lo',lambda d:d.G3=='Hi')
table("Lo vs CTL",lambda d:d.G3=='Lo',lambda d:d.G3=='CTL')
table("Hi vs CTL",lambda d:d.G3=='Hi',lambda d:d.G3=='CTL')
table("All PTEN (13) vs CTL",lambda d:d.Group=='PTEN',lambda d:d.G3=='CTL')
table("HBH vs non-HBH within PTEN",lambda d:(d.Group=='PTEN')&d.HBH,lambda d:(d.Group=='PTEN')&~d.HBH)
table("IED+ vs IED- (recorded PTEN)",lambda d:d.IED=='+',lambda d:d.IED=='-')
print("\n=== correlations with %KO within PTEN (n=11), mouse means ===")
for c in ['V','H']:
    d=mm[(mm.Condition==c)&mm.pct.notna()]
    for v in V:
        r=stats.pearsonr(d.pct,d[v]); s=stats.spearmanr(d.pct,d[v]); print(c,v,f"r={r.statistic:.2f} p={r.pvalue:.3f} rho={s.statistic:.2f} p={s.pvalue:.3f}")
print("\n=== correlations with sessions-to-criterion within PTEN (n=13) ===")
for c in ['V','H']:
    d=mm[(mm.Condition==c)&(mm.Group=='PTEN')]
    for v in V:
        s=stats.spearmanr(d.crit,d[v]); print(c,v,f"rho={s.statistic:.2f} p={s.pvalue:.3f}")
print("\n=== per-mouse PTEN table ===")
w=mm[mm.Group=='PTEN'].pivot(index='MouseID',columns='Condition',values=V); w.columns=[f"{a}_{b}" for a,b in w.columns]
w.insert(0,'pct',w.index.map(pct)); w.insert(1,'crit',w.index.map(crit)); w.insert(2,'HBH',w.index.isin(hbh)); w.insert(3,'IED',[('+' if m in iedp else '-' if m in iedm else 'NR') for m in w.index])
print(w.sort_values('pct').round(3).to_string())
