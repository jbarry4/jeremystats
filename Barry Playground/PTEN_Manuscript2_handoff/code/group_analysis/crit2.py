"""Sessions to criterion: group tests (Welch, permutation, Mann-Whitney), comparing the two uploads of PTEN_sess2crtit_hilo.sav. Usage: python crit2.py [PTEN_sess2crtit_hilo.sav] [PTEN_sess2crtit_hilo_first.sav]

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
import statsmodels.api as sm
warnings.filterwarnings('ignore'); pd.set_option('display.width',200)
new,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else SESS2CRIT_SAV)); old,_=pyreadstat.read_sav((sys.argv[2] if len(sys.argv)>2 else SESS2CRIT_SAV_FIRST))
print(new.to_string()); print(new.dtypes)
mg=new.merge(old,on='Mouse',how='outer',suffixes=('_new','_old'),indicator=True)
print("only in new:",mg[mg._merge=='left_only'].Mouse.tolist(),"only in old:",mg[mg._merge=='right_only'].Mouse.tolist())
b=mg[mg._merge=='both']; print("changed rows:\n",b[(b.NumberSessionsCrit_new!=b.NumberSessionsCrit_old)|(b.Group_new!=b.Group_old)].to_string())
print("dup mice:",new.Mouse[new.Mouse.duplicated()].tolist())
df=new.rename(columns={'NumberSessionsCrit':'y'}); df['pct']=pd.to_numeric(df.PercentKO,errors='coerce')
print("M6 row:\n",df[df.Mouse==6].to_string())
for label,d in [("WITH M6",df),("WITHOUT M6",df[df.Mouse!=6])]:
    print("\n########",label)
    print(d.groupby('Group').y.agg(['count','mean','median','std','sem','min','max']).round(2)); print(d.groupby('Group2').y.agg(['count','mean','median','std','sem','min','max']).round(2))
    g={k:v.y.values for k,v in d.groupby('Group')}; Ct,H,L,q=g['CTL'],g['PTEN-Hi'],g['PTEN-Lo'],g['PTEN-?']; P=d[d.Group2=='PTEN'].y.values
    def hedges(a,b):
        na,nb=len(a),len(b); sp=np.sqrt(((na-1)*a.var(ddof=1)+(nb-1)*b.var(ddof=1))/(na+nb-2)); return (a.mean()-b.mean())/sp*(1-3/(4*(na+nb)-9))
    def perm(a,b):
        x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
        from math import comb
        if comb(len(x),n)<=100000:
            c=t=0
            for idx in itertools.combinations(range(len(x)),n):
                m=np.zeros(len(x),bool); m[list(idx)]=True; t+=1; c+=abs(x[m].mean()-x[~m].mean())>=obs-1e-12
            return c/t
        rng=np.random.default_rng(1); c=0
        for _ in range(200000):
            p=rng.permutation(x); c+=abs(p[:n].mean()-p[n:].mean())>=obs-1e-12
        return (c+1)/200001
    def cmp(n,a,b):
        t=stats.ttest_ind(a,b,equal_var=False); u=stats.mannwhitneyu(a,b,alternative='two-sided')
        print(f"{n}: diff={a.mean()-b.mean():.2f} Welch t={t.statistic:.2f} df={t.df:.1f} p={t.pvalue:.5f} | U={u.statistic} p={u.pvalue:.5f} AUC={u.statistic/(len(a)*len(b)):.2f} | g={hedges(a,b):.2f} | perm p={perm(a,b):.5f}")
    print("KW",stats.kruskal(Ct,H,L)); print("Levene",stats.levene(Ct,H,L))
    cmp("Lo vs Hi",L,H); cmp("Lo vs CTL",L,Ct); cmp("Hi vs CTL",H,Ct); cmp("PTEN vs CTL",P,Ct)
    for lab,(h,l) in {"M27->Hi,M31->Lo":(np.r_[H,q[0]],np.r_[L,q[1]]),"both->Hi":(np.r_[H,q],L),"both->Lo":(H,np.r_[L,q]),"M27->Lo,M31->Hi":(np.r_[H,q[1]],np.r_[L,q[0]])}.items():
        cmp("  Lo vs Hi | "+lab,l,h); cmp("  Hi vs CTL | "+lab,h,Ct)
    dd=d[d.Group!='PTEN-?'].copy(); dd['p']=dd.pct.fillna(0)
    r=stats.spearmanr(dd.p,dd.y); X1=sm.add_constant(dd.p.values); X2=sm.add_constant(np.c_[dd.p,dd.p**2])
    f1=sm.OLS(dd.y.values,X1).fit(); f2=sm.OLS(dd.y.values,X2).fit()
    print(f"CTL at 0%: n={len(dd)} Spearman rho={r.statistic:.2f} p={r.pvalue:.4f} | linear R2={f1.rsquared:.3f} | quad R2={f2.rsquared:.3f}, quad term p={f2.pvalues[2]:.5f}, AIC {f1.aic:.1f}->{f2.aic:.1f}")
