"""SUPERSEDED / NOT USED IN THE REPORT. Negative-binomial check on counts. Not used in the report.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys, numpy as np, pyreadstat, statsmodels.formula.api as smf
df,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else PROBE_SAV)); d=df[df.Group!='PTEN-?'].rename(columns={'NumberSessionsCrit':'y'})
d['G']=d.Group.str.replace('-','_')
for ref in ['CTL','PTEN_Hi']:
    m=smf.negativebinomial(f"y~C(G,Treatment('{ref}'))",d).fit(disp=0)
    t=m.summary2().tables[1]; t['ratio']=np.exp(t['Coef.']); t['lo']=np.exp(t['[0.025']); t['hi']=np.exp(t['0.975]'])
    print(ref); print(t[['ratio','lo','hi','z','P>|z|']].round(4))
# drop CTL outlier (mouse 6, 27 sessions)
d2=d[d.Mouse!=6]; m=smf.negativebinomial("y~C(G,Treatment('CTL'))",d2).fit(disp=0); print(m.summary2().tables[1].round(4))
