"""Sessions to criterion vs % KO: linear vs inverted-U (quadratic) fits with WT at 0%.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import numpy as np, itertools
from scipy import stats
import statsmodels.api as sm
m=[1,3,5,7,8,10,28,29,30,33,34]; y=np.array([22,14,9,9,21,28,8,25,20,15,19.]); p=np.array([5.18,24.57,27.64,24.12,3.89,9.51,20.19,22.00,5.97,8.82,28.43])
ctl=np.array([8,11,7,11,8,10,13,12,12,7,7,9,8,7,7.])
def corr(n,a,b):
    r=stats.pearsonr(a,b); s=stats.spearmanr(a,b); ci=r.confidence_interval()
    print(f"{n}: n={len(a)} Pearson r={r.statistic:.2f} [{ci.low:.2f},{ci.high:.2f}] p={r.pvalue:.3f} | Spearman rho={s.statistic:.2f} p={s.pvalue:.3f}")
corr("PTEN all",p,y)
lo=p<15; corr("within Lo",p[lo],y[lo]); corr("within Hi",p[~lo],y[~lo])
# linear model within PTEN
X=sm.add_constant(p); f=sm.OLS(y,X).fit(); print(f.params.round(3), f.bse.round(3), f.pvalues.round(4), "R2",round(f.rsquared,3)); print(f.conf_int().round(3))
# leave-one-out
print("LOO r:",[round(stats.pearsonr(np.delete(p,i),np.delete(y,i)).statistic,2) for i in range(len(p))])
# with controls at 0%
pa=np.r_[p,np.zeros(len(ctl))]; ya=np.r_[y,ctl]
corr("incl CTL at 0",pa,ya)
X1=sm.add_constant(pa); X2=sm.add_constant(np.c_[pa,pa**2])
f1=sm.OLS(ya,X1).fit(); f2=sm.OLS(ya,X2).fit()
print("linear R2",round(f1.rsquared,3),"AIC",round(f1.aic,1),"| quad R2",round(f2.rsquared,3),"AIC",round(f2.aic,1)); print(f2.params.round(4),f2.pvalues.round(5))
print("peak of quadratic at %KO:",round(-f2.params[1]/(2*f2.params[2]),1))
print("gap in pct:",sorted(p))
for i in np.argsort(p): print(m[i],p[i],y[i])
