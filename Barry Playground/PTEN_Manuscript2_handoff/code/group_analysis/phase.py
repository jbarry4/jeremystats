"""Phase effects: trained (phase 7) vs mean of novel phases (paired t), per-mouse slopes across phases 7-10, and mixed models (mouse random effect) for group and group x phase.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import numpy as np, pandas as pd, itertools, warnings
from scipy import stats
import statsmodels.formula.api as smf
warnings.filterwarnings('ignore'); pd.set_option('display.width',250)
df=pd.read_pickle('probe.pkl'); V=['NumRewards','PGoalTime','NumEntrances','ReRatio','PTimeCenter','PTimeAnnulus','MeanSpeed','MeanTargSpeed']
def perm(a,b):
    x=np.r_[a,b]; n=len(a); obs=abs(a.mean()-b.mean()); c=t=0
    for idx in itertools.combinations(range(len(x)),n):
        m=np.zeros(len(x),bool); m[list(idx)]=True; t+=1; c+=abs(x[m].mean()-x[~m].mean())>=obs-1e-12
    return c/t
def perm(a,b,*_a,**_k):  # switched to Mann-Whitney U (two-sided) for all group comparisons
    from scipy.stats import mannwhitneyu as _mw; import numpy as _np
    a=_np.asarray(a,float); b=_np.asarray(b,float); a=a[~_np.isnan(a)]; b=b[~_np.isnan(b)]
    return _mw(a,b,alternative='two-sided').pvalue

print("=== per-phase means (CTL / Lo / Hi) and Lo-vs-Hi exact permutation p ===")
for c in ['V','H']:
    for v in V:
        out=[]
        for ph in [7,8,9,10]:
            d=df[(df.Condition==c)&(df.Phase==ph)]; a=d[d.G3=='Lo'][v].values; b=d[d.G3=='Hi'][v].values; k=d[d.G3=='CTL'][v].values
            out.append(f"P{ph}: {k.mean():.3g}/{a.mean():.3g}/{b.mean():.3g} p={perm(a,b):.3f}")
        print(c,v.ljust(14),' | '.join(out))
print("\n=== per-mouse slope across phases 7-10; Lo vs Hi, and each vs CTL ===")
sl=df.groupby(['MouseID','G3','Condition']).apply(lambda d:pd.Series({v:np.polyfit(d.Phase,d[v],1)[0] for v in V})).reset_index()
for c in ['V','H']:
    d=sl[sl.Condition==c]
    for v in V:
        a,b,k=[d[d.G3==g][v].values for g in ['Lo','Hi','CTL']]
        print(c,v.ljust(14),f"slope CTL={k.mean():.3g} Lo={a.mean():.3g} Hi={b.mean():.3g} | LoHi perm p={perm(a,b):.3f} | Lo-CTL MWU p={stats.mannwhitneyu(a,k).pvalue:.3f} Hi-CTL MWU p={stats.mannwhitneyu(b,k).pvalue:.3f}")
print("\n=== mixed model (random mouse intercept), Lo vs Hi only: group, phase, group x phase ===")
d0=df[df.G3.isin(['Lo','Hi'])].copy(); d0['ph']=d0.Phase-7
for c in ['V','H']:
    for v in V:
        d=d0[d0.Condition==c]
        try:
            m=smf.mixedlm(f"{v}~C(G3)*ph",d,groups=d.MouseID).fit(reml=False); m0=smf.mixedlm(f"{v}~ph",d,groups=d.MouseID).fit(reml=False)
            lr=2*(m.llf-m0.llf); print(c,v.ljust(14),f"group(Lo-Hi at P7) p={m.pvalues.iloc[1]:.3f} | gxphase p={m.pvalues.iloc[3]:.3f} | overall group LR p={stats.chi2.sf(lr,2):.3f}")
        except Exception as e: print(c,v,'fail',e)
print("\n=== H minus V drop per mouse (mean over phases) ===")
mm=pd.read_pickle('mm.pkl'); w=mm.pivot(index=['MouseID','G3'],columns='Condition',values=V)
for v in V:
    dd=(w[(v,'H')]-w[(v,'V')]).reset_index(name='d'); a,b,k=[dd[dd.G3==g].d.values for g in ['Lo','Hi','CTL']]
    print(v.ljust(14),f"CTL={k.mean():.3g} Lo={a.mean():.3g} Hi={b.mean():.3g} | LoHi perm p={perm(a,b):.3f}")
