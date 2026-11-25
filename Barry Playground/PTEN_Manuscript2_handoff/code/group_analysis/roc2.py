"""ROC, second version (without M6). Usage: python roc2.py [ROC_heterotopia_Fixed_hilo.sav]

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
warnings.filterwarnings('ignore')
df,_=pyreadstat.read_sav((sys.argv[1] if len(sys.argv)>1 else CRIT_SAV)); df=df.dropna(subset=['MouseID']).rename(columns={'SesstoCriterion':'y','GRP2HiLo':'G','GRP':'G2','BIheterotopia':'het'}); df=df[df.MouseID!=6]
pct={1:5.18,3:24.57,5:27.64,7:24.12,8:3.89,10:9.51,28:20.19,29:22.00,30:5.97,33:8.82,34:28.43}
iedp={3,5,28,34}; iedm={1,7,8,10,29,30,33}
df['pct']=df.MouseID.map(pct); df.loc[df.G=='CTL','pct']=0
df['ied']=df.MouseID.map(lambda m:1 if m in iedp else (0 if m in iedm else np.nan)); df.loc[df.G=='CTL','ied']=0
def roc(name,x,state):
    x=np.asarray(x,float); s=np.asarray(state).astype(bool); pos,neg=x[s],x[~s]
    k=lambda a,b:((a[:,None]>b[None,:])+0.5*(a[:,None]==b[None,:]))
    auc=k(pos,neg).mean(); flip=auc<0.5
    if flip: pos,neg=-pos,-neg; auc=1-auc
    rng=np.random.default_rng(0); bs=[k(rng.choice(pos,len(pos)),rng.choice(neg,len(neg))).mean() for _ in range(5000)]
    lo,hi=np.percentile(bs,[2.5,97.5]); p=stats.mannwhitneyu(pos,neg).pvalue
    best=None
    for c in np.unique(np.r_[pos,neg]):
        sens=(pos>=c).mean(); spec=(neg<c).mean(); J=sens+spec-1
        if best is None or J>best[0]+1e-12: best=(J,c,sens,spec)
    c=best[1]; tp=(pos>=c).sum(); fp=(neg>=c).sum()
    print(f"{name}: n+={len(pos)} n-={len(neg)} dir={'LOWER' if flip else 'higher'} AUC={auc:.3f} boot[{lo:.2f},{hi:.2f}] p={p:.4f} | cut {'<=' if flip else '>='}{abs(c):.2f} sens={best[2]:.2f} spec={best[3]:.2f} PPV={tp}/{tp+fp}")
K=df[df.G!='PTEN-?']   # known KO class (CTL + 11 PTEN), n=29
I=df[df.ied.notna()]   # known IED (CTL assumed negative + 11 recorded), n=29
print("=== sessions to criterion, each subtype vs ALL other mice ===")
roc("PTEN vs rest (n=31)",df.y,df.G2=='PTEN')
roc("Lo vs rest (CTL+Hi), n=29",K.y,K.G=='PTEN-Lo')
roc("Hi vs rest (CTL+Lo), n=29",K.y,K.G=='PTEN-Hi')
roc("Heterotopia vs rest, n=31",df.y,df.het==1)
roc("IED+ vs rest (CTL+IED-), n=29",I.y,I.ied==1)
roc("IED- PTEN vs rest (CTL+IED+), n=29",I.y,(I.ied==0)&(I.G2=='PTEN'))
roc("PTEN no-het vs rest, n=31",df.y,(df.G2=='PTEN')&(df.het==0))
print("=== percent KO (CTL = 0), each subtype vs ALL other mice ===")
roc("%KO -> IED+ vs rest, n=29",I[I.pct.notna()].pct,I[I.pct.notna()].ied==1)
roc("%KO -> heterotopia vs rest, n=29",K.pct,K.het==1)
roc("%KO -> slow learner (>13 sessions) vs rest, n=29",K.pct,K.y>13)
print("=== three-class: sessions -> CTL / Hi / Lo ===")
# simple ordinal cutoffs: <=13 CTL, 14-19? evaluate confusion with cut 13.5 and best second cut
for c2 in [14.5,19.5,20.5]:
    pred=np.where(K.y<=13,'CTL',np.where(K.y<c2,'mid','high')); print(c2); print(pd.crosstab(K.G,pred))
