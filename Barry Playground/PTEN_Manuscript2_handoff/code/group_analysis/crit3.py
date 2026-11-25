"""Sessions to criterion: full group comparison table and heterotopia/IED breakdown. Compares ROC_heterotopia_Fixed_hilo.sav (used in the report) with PTEN_sess2crtit_hilo.sav. Usage: python crit3.py [ROC_heterotopia_Fixed_hilo.sav] [PTEN_sess2crtit_hilo.sav]

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
from math import comb
warnings.filterwarnings('ignore'); pd.set_option('display.width',200)
new,meta=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else CRIT_SAV)); old,_=pyreadstat.read_sav((sys.argv[2] if len(sys.argv)>2 else SESS2CRIT_SAV))
print(new.to_string()); print(new.dtypes, meta.variable_value_labels)
mg=new.merge(old,left_on='MouseID',right_on='Mouse',how='outer',indicator=True)
print("only in new:",mg[mg._merge=='left_only'].MouseID.tolist(),"only in old:",mg[mg._merge=='right_only'].Mouse.tolist())
b=mg[mg._merge=='both']; print("changed:\n",b[(b.SesstoCriterion!=b.NumberSessionsCrit)|(b.GRP2HiLo!=b.Group)][['MouseID','SesstoCriterion','NumberSessionsCrit','GRP2HiLo','Group']].to_string())
print("dups:",new.MouseID[new.MouseID.duplicated()].tolist())
pct={1:5.18,3:24.57,5:27.64,7:24.12,8:3.89,10:9.51,28:20.19,29:22.00,30:5.97,33:8.82,34:28.43}
df=new.rename(columns={'SesstoCriterion':'y','GRP2HiLo':'G','GRP':'G2','BIheterotopia':'het'}); df['pct']=df.MouseID.map(pct)
print(df[df.G2=='PTEN'].sort_values('pct').to_string())
def hedges(a,b):
    na,nb=len(a),len(b); sp=np.sqrt(((na-1)*a.var(ddof=1)+(nb-1)*b.var(ddof=1))/(na+nb-2)); return (a.mean()-b.mean())/sp*(1-3/(4*(na+nb)-9))
def perm(a,b):
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean())
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
    a=np.asarray(a,float); b=np.asarray(b,float)
    t=stats.ttest_ind(a,b,equal_var=False); u=stats.mannwhitneyu(a,b,alternative='two-sided')
    print(f"{n}: n={len(a)}v{len(b)} means {a.mean():.2f} v {b.mean():.2f} diff={a.mean()-b.mean():.2f} Welch t={t.statistic:.2f} df={t.df:.1f} p={t.pvalue:.5f} | U={u.statistic} p={u.pvalue:.5f} AUC={u.statistic/(len(a)*len(b)):.2f} | g={hedges(a,b):.2f} | perm p={perm(a,b):.5f}")
for label,d in [("WITH M6",df),("WITHOUT M6",df[df.MouseID!=6])]:
    print("\n########",label)
    print(d.groupby('G').y.agg(['count','mean','median','std','sem','min','max']).round(2)); print(d.groupby('G2').y.agg(['count','mean','median','std','sem','min','max']).round(2))
    g={k:v.y.values for k,v in d.groupby('G')}; Ct,H,L,q=g['CTL'],g['PTEN-Hi'],g['PTEN-Lo'],g['PTEN-?']; P=d[d.G2=='PTEN'].y.values
    print("KW",stats.kruskal(Ct,H,L)); print("Levene",stats.levene(Ct,H,L)); print("Shapiro CTL",stats.shapiro(Ct).pvalue)
    cmp("Lo vs Hi",L,H); cmp("Lo vs CTL",L,Ct); cmp("Hi vs CTL",H,Ct); cmp("PTEN vs CTL",P,Ct)
    qm=d[d.G=='PTEN-?'].set_index('MouseID').y
    for lab,(h,l) in {"M27->Hi,M31->Lo":(np.r_[H,qm[27]],np.r_[L,qm[31]]),"both->Hi":(np.r_[H,q],L),"both->Lo":(H,np.r_[L,q]),"M27->Lo,M31->Hi":(np.r_[H,qm[31]],np.r_[L,qm[27]])}.items():
        cmp("  Lo vs Hi | "+lab,l,h); cmp("  Hi vs CTL | "+lab,h,Ct)
    dd=d[d.G!='PTEN-?'].copy(); dd['p']=dd.pct.fillna(0)
    r=stats.spearmanr(dd.p,dd.y); f1=sm.OLS(dd.y.values,sm.add_constant(dd.p.values)).fit(); f2=sm.OLS(dd.y.values,sm.add_constant(np.c_[dd.p,dd.p**2])).fit()
    print(f"CTL at 0%: n={len(dd)} Spearman rho={r.statistic:.2f} p={r.pvalue:.4f} | linear R2={f1.rsquared:.3f} | quad R2={f2.rsquared:.3f}, quad p={f2.pvalues[2]:.5f}, peak {-f2.params[1]/(2*f2.params[2]):.1f}%")
    import statsmodels.formula.api as smf
    dd['Gq']=dd.G.str.replace('-','_')
    for ref in ['CTL','PTEN_Hi']:
        m=smf.glm(f"y~C(Gq,Treatment('{ref}'))",dd,family=sm.families.Poisson()).fit(scale='X2'); t=m.summary2().tables[1]
        print(ref,"qPoisson disp",round(m.scale,2)); print(np.exp(t[['Coef.','[0.025','0.975]']]).round(2).join(t[['P>|z|']].round(5)).iloc[1:])
print("\n######## HETEROTOPIA (PTEN only)")
p=df[df.G2=='PTEN']; print(p.groupby('het').agg(n=('y','size'),mean=('y','mean'),sem=('y','sem'),pct=('pct','mean'),mice=('MouseID',lambda s:list(s.astype(int)))))
print(pd.crosstab(p.G,p.het))
vals=sorted(p.het.dropna().unique()); 
if len(vals)==2:
    a=p[p.het==vals[1]].y.values; b=p[p.het==vals[0]].y.values; cmp(f"het {vals[1]} vs {vals[0]} sessions",a,b)
    a2=p[(p.het==vals[1])&p.pct.notna()].pct.values; b2=p[(p.het==vals[0])&p.pct.notna()].pct.values; cmp("het vs not: %KO",a2,b2)
    cmp("het vs CTL(noM6)",a,df[(df.G=='CTL')&(df.MouseID!=6)].y.values); cmp("no-het PTEN vs CTL(noM6)",b,df[(df.G=='CTL')&(df.MouseID!=6)].y.values)
    from sklearn.metrics import roc_auc_score
