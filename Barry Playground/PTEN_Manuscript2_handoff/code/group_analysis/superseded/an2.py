"""SUPERSEDED / NOT USED IN THE REPORT. First mixed-model look. Superseded by phase.py.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, numpy as np, pyreadstat, itertools
from scipy import stats
import statsmodels.formula.api as smf
df,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else PROBE_SAV)); df=df.rename(columns={'NumberSessionsCrit':'y'}); df=df[df.Mouse!=6]
print(df.groupby('Group').y.agg(['count','mean','median','std','sem','min','max']).round(2))
print(df.groupby('Group2').y.agg(['count','mean','median','std','sem','min','max']).round(2))
g={k:v.y.values for k,v in df.groupby('Group')}
Ct,H,L,q=g['CTL'],g['PTEN-Hi'],g['PTEN-Lo'],g['PTEN-?']; P=df[df.Group2=='PTEN'].y.values
def hedges(a,b):
    na,nb=len(a),len(b); sp=np.sqrt(((na-1)*a.var(ddof=1)+(nb-1)*b.var(ddof=1))/(na+nb-2))
    return (a.mean()-b.mean())/sp*(1-3/(4*(na+nb)-9))
def perm(a,b):
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean()); rng=np.random.default_rng(1); c=0
    for _ in range(200000):
        p=rng.permutation(x); c+=abs(p[:n].mean()-p[n:].mean())>=obs-1e-12
    return (c+1)/200001
def cmp(n,a,b):
    t=stats.ttest_ind(a,b,equal_var=False); u=stats.mannwhitneyu(a,b,alternative='two-sided')
    print(f"{n}: diff={a.mean()-b.mean():.2f} Welch t={t.statistic:.2f} df={t.df:.1f} p={t.pvalue:.5f} | U={u.statistic} p={u.pvalue:.5f} AUC={u.statistic/(len(a)*len(b)):.2f} | g={hedges(a,b):.2f} | perm p={perm(a,b):.5f}")
print("KW", stats.kruskal(Ct,H,L)); print("ANOVA", stats.f_oneway(Ct,H,L)); print("Levene", stats.levene(Ct,H,L))
cmp("Lo vs Hi",L,H); cmp("Lo vs CTL",L,Ct); cmp("Hi vs CTL",H,Ct); cmp("PTEN vs CTL",P,Ct)
for lab,(h,l) in {"both->Hi":(np.r_[H,q],L),"both->Lo":(H,np.r_[L,q]),"M27->Hi,M31->Lo":(np.r_[H,q[0]],np.r_[L,q[1]]),"M27->Lo,M31->Hi":(np.r_[H,q[1]],np.r_[L,q[0]])}.items():
    cmp("Hi vs CTL | "+lab,h,Ct); cmp("Lo vs Hi | "+lab,l,h)
d=df[df.Group!='PTEN-?'].copy(); d['G']=d.Group.str.replace('-','_')
import statsmodels.api as sm
for ref in ['CTL','PTEN_Hi']:
    m=smf.glm(f"y~C(G,Treatment('{ref}'))",d,family=sm.families.Poisson()).fit(scale='X2')
    t=m.summary2().tables[1]; print(ref,"quasi-Poisson, dispersion",round(m.scale,2)); print(np.exp(t[['Coef.','[0.025','0.975]']]).round(2).join(t[['P>|z|']].round(5)))
