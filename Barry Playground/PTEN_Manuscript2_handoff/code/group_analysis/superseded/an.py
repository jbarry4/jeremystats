"""SUPERSEDED / NOT USED IN THE REPORT. First look at AllProbeSessions.sav (group means). Superseded by probe.py.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, numpy as np, pandas as pd, pyreadstat, itertools
from scipy import stats
df,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else PROBE_SAV)); df=df.rename(columns={'NumberSessionsCrit':'y'})
print(df.groupby('Group').y.agg(['count','mean','median','std','sem','min','max']).round(2))
print(df.groupby('Group2').y.agg(['count','mean','median','std','sem','min','max']).round(2))
g={k:v.y.values for k,v in df.groupby('Group')}
C,H,L=g['CTL'],g['PTEN-Hi'],g['PTEN-Lo']; P=df[df.Group2=='PTEN'].y.values
def hedges(a,b):
    na,nb=len(a),len(b); sp=np.sqrt(((na-1)*a.var(ddof=1)+(nb-1)*b.var(ddof=1))/(na+nb-2))
    return (a.mean()-b.mean())/sp*(1-3/(4*(na+nb)-9))
def perm(a,b,exact=True):
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean()); c=t=0
    if exact:
        for idx in itertools.combinations(range(len(x)),n):
            m=np.zeros(len(x),bool); m[list(idx)]=True
            t+=1; c+= abs(x[m].mean()-x[~m].mean())>=obs-1e-12
        return c/t
    rng=np.random.default_rng(1)
    for _ in range(200000):
        p=rng.permutation(x); c+=abs(p[:n].mean()-p[n:].mean())>=obs-1e-12
    return (c+1)/200001
def cmp(n,a,b,exact=True):
    t=stats.ttest_ind(a,b,equal_var=False); u=stats.mannwhitneyu(a,b,alternative='two-sided',method='exact' if len(set(np.r_[a,b]))==len(a)+len(b) else 'auto')
    auc=u.statistic/(len(a)*len(b))
    print(f"{n}: diff={a.mean()-b.mean():.2f} Welch t={t.statistic:.2f} df={t.df:.1f} p={t.pvalue:.4f} | MWU U={u.statistic} p={u.pvalue:.4f} AUC={auc:.2f} | g={hedges(a,b):.2f} | perm p={perm(a,b,exact):.4f}")
print("Shapiro", {k:round(stats.shapiro(v).pvalue,4) for k,v in g.items() if len(v)>2})
print("Levene 3grp", stats.levene(C,H,L))
print("KW 3grp", stats.kruskal(C,H,L)); print("ANOVA 3grp", stats.f_oneway(C,H,L))
print("Welch-type: log ANOVA", stats.f_oneway(np.log(C),np.log(H),np.log(L)))
cmp("Lo vs Hi",L,H); cmp("Lo vs CTL",L,C,False); cmp("Hi vs CTL",H,C,False); cmp("PTEN(all) vs CTL",P,C,False)
# sensitivity: the two '?' mice assigned every way
q=g['PTEN-?']
for lab,(h,l) in {"both?->Hi":(np.r_[H,q],L),"both?->Lo":(H,np.r_[L,q]),"8->Hi,27->Lo":(np.r_[H,q[0]],np.r_[L,q[1]]),"8->Lo,27->Hi":(np.r_[H,q[1]],np.r_[L,q[0]])}.items():
    cmp("Lo vs Hi | "+lab,l,h)
# NB GLM (counts) 
try:
    import statsmodels.formula.api as smf, statsmodels.api as sm
    d=df[df.Group!='PTEN-?']
    m=smf.glm("y~C(Group,Treatment('CTL'))",d,family=sm.families.NegativeBinomial(alpha=0.1)).fit()
    m2=smf.negativebinomial("y~C(Group,Treatment('CTL'))",d).fit(disp=0); print(m2.summary().tables[1])
    print("Lo vs Hi NB:", m2.t_test("C(Group, Treatment('CTL'))[T.PTEN-Lo] - C(Group, Treatment('CTL'))[T.PTEN-Hi] = 0"))
except Exception as e: print("NB skipped",e)
