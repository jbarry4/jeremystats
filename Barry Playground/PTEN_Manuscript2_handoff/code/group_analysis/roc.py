"""ROC: sessions to criterion as a classifier of group. Usage: python roc.py [ROC_heterotopia_Fixed_hilo.sav]

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
df['pct']=df.MouseID.map(pct); df['ied']=df.MouseID.map(lambda m:1 if m in iedp else (0 if m in iedm else np.nan))
def delong(pos,neg):
    m,n=len(pos),len(neg)
    psi=lambda x,y:(x>y)+0.5*(x==y)
    V10=np.array([np.mean([psi(p,q) for q in neg]) for p in pos]); V01=np.array([np.mean([psi(p,q) for p in pos]) for q in neg])
    auc=V10.mean(); se=np.sqrt(V10.var(ddof=1)/m+V01.var(ddof=1)/n); return auc,se
def roc(name,x,state,higher_pos=True):
    x=np.asarray(x,float); s=np.asarray(state).astype(bool)
    pos,neg=x[s],x[~s]
    if not higher_pos: pos,neg=-pos,-neg
    auc,se=delong(pos,neg)
    # logit-transformed CI to stay in [0,1]
    if 0<auc<1 and se>0:
        l=np.log(auc/(1-auc)); sl=se/(auc*(1-auc)); lo,hi=1/(1+np.exp(-(l-1.96*sl))),1/(1+np.exp(-(l+1.96*sl)))
    else: lo=hi=np.nan
    rng=np.random.default_rng(0); bs=[]
    for _ in range(5000):
        a=rng.choice(pos,len(pos)); b=rng.choice(neg,len(neg)); bs.append(((a[:,None]>b[None,:])+0.5*(a[:,None]==b[None,:])).mean())
    blo,bhi=np.percentile(bs,[2.5,97.5])
    p=stats.mannwhitneyu(pos,neg,alternative='two-sided').pvalue
    # Youden cutoff
    xs=np.r_[pos,neg]; best=None
    for c in np.unique(xs):
        for thr in [c-0.5] if True else []:
            sens=(pos>thr).mean(); spec=(neg<=thr).mean(); J=sens+spec-1
            if best is None or J>best[0]+1e-12: best=(J,thr,sens,spec)
    thr=best[1] if higher_pos else -best[1]
    print(f"{name}: n+={len(pos)} n-={len(neg)} AUC={auc:.3f} SE={se:.3f} 95%CI logit [{lo:.2f},{hi:.2f}] boot [{blo:.2f},{bhi:.2f}] p={p:.4f} | cutoff {'>' if higher_pos else '<'}{abs(thr):.1f}: sens={best[2]:.2f} spec={best[3]:.2f} J={best[0]:.2f}")
P=df[df.G2=='PTEN']; K=df[df.pct.notna()]; C=df[df.G=='CTL']
print("--- test variable: sessions to criterion (higher = positive unless noted) ---")
roc("PTEN (13) vs CTL (18)",df.y,df.G2=='PTEN')
d=df[df.G.isin(['PTEN-Lo','CTL'])]; roc("Lo vs CTL",d.y,d.G=='PTEN-Lo')
d=df[df.G.isin(['PTEN-Hi','CTL'])]; roc("Hi vs CTL",d.y,d.G=='PTEN-Hi')
roc("Lo vs Hi (within PTEN, n=11)",K.y,K.G=='PTEN-Lo')
roc("Heterotopia vs none (within PTEN, n=13)",P.y,P.het==1)
roc("Heterotopia vs everyone else (incl CTL)",df.y,df.het==1)
I=df[df.ied.notna()]; roc("IED+ vs IED- (recorded PTEN, n=11); LOWER sessions = IED+",I.y,I.ied==1,False)
print("--- test variable: percent KO ---")
roc("%KO -> IED+ (higher)",I.pct,I.ied==1)
roc("%KO -> heterotopia (LOWER %KO = het)",K.pct,K.het==1,False)
med=K.y.median(); print("median sessions among PTEN w/ histology:",med)
roc("%KO -> slow learner (sessions > CTL max 13); LOWER %KO",K.pct,K.y>13,False)
print(K[['MouseID','y','G','het','pct','ied']].sort_values('y').to_string(index=False))
