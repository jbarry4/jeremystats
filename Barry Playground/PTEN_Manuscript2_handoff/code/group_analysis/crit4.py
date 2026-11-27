"""Sessions to criterion without M6: regression on group. Usage: python crit4.py [ROC_heterotopia_Fixed_hilo.sav]

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, numpy as np, pandas as pd, pyreadstat, warnings
from scipy import stats
import statsmodels.api as sm, statsmodels.formula.api as smf
warnings.filterwarnings('ignore')
df,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else CRIT_SAV)); df=df.dropna(subset=['MouseID']).rename(columns={'SesstoCriterion':'y','GRP2HiLo':'G'}); df=df[df.MouseID!=6]
pct={1:5.18,3:24.57,5:27.64,7:24.12,8:3.89,10:9.51,28:20.19,29:22.00,30:5.97,33:8.82,34:28.43}
dd=df[df.G!='PTEN-?'].copy(); dd['p']=dd.MouseID.map(pct).fillna(0); dd['Gq']=dd.G.str.replace('-','_'); print(len(dd), dd.Gq.value_counts().to_dict())
r=stats.spearmanr(dd.p,dd.y); f1=sm.OLS(dd.y.values,sm.add_constant(dd.p.values)).fit(); f2=sm.OLS(dd.y.values,sm.add_constant(np.c_[dd.p,dd.p**2])).fit()
print(f"Spearman rho={r.statistic:.2f} p={r.pvalue:.4f} | linear R2={f1.rsquared:.3f} | quad R2={f2.rsquared:.3f}, quad p={f2.pvalues[2]:.5f}, peak {-f2.params[1]/(2*f2.params[2]):.1f}%")
for ref in ['CTL','PTEN_Hi']:
    m=smf.glm(f"y~C(Gq,Treatment('{ref}'))",dd,family=sm.families.Poisson()).fit(scale='X2'); t=m.summary2().tables[1]
    print(ref,"disp",round(m.scale,2)); print(np.exp(t[['Coef.','[0.025','0.975]']]).round(2).join(t[['P>|z|']].round(5)).iloc[1:])
