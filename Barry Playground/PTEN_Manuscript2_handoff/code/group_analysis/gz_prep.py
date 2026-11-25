"""Reads AllProbes_ByGZLocation.sav and builds gz.pkl: time in each of the four goal zones per session, and zone roles (current, previous, trained, never used) and their shares.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work/gz) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(os.path.join(WORK,'gz'))
import pyreadstat, pandas as pd, numpy as np
from scipy import stats
df,_=pyreadstat.read_sav(ZONE_SAV)
df=df.dropna(subset=['Mouse']); df=df[df.Group!='DKO'].copy()
pct={1:5.18,3:24.57,5:27.64,7:24.12,8:3.89,10:9.51,28:20.19,29:22.00,30:5.97,33:8.82,34:28.43}
df['pct']=df.Mouse.map(pct)
df['G3']=np.where(df.Group=='CTL','CTL',np.where(df.pct.isna(),'UNK',np.where(df.pct<15,'Lo','Hi')))
df['ied']=df.Subgroup.map({'IED+':'+','IED-':'-'})
w=df.pivot_table(index=['Mouse','G3','Group','ied','pct','Condition','Phase'],values='GoalTimes',columns='GoalLocation',dropna=False).reset_index()
w=w.dropna(subset=[1.0,2.0,3.0,4.0])
w.columns=[str(int(c)) if isinstance(c,float) else c for c in w.columns]
rows=[]
for _,r in w.iterrows():
    ph=int(r.Phase); cur=ph-6; z={k:r[str(k)] for k in (1,2,3,4)}; tot=sum(z.values())
    old=[k for k in (1,2,3,4) if k<cur]; new=[k for k in (1,2,3,4) if k>cur]
    rows.append(dict(Mouse=int(r.Mouse),G3=r.G3,Group=r.Group,ied=r.ied,pct=r.pct,Condition=r.Condition,Phase=ph,
        total=tot,correct=z[cur],old_all=sum(z[k] for k in old) if old else np.nan,old_mean=np.mean([z[k] for k in old]) if old else np.nan,
        recent=z[cur-1] if cur>1 else np.nan,trained=z[1] if cur>1 else np.nan,never_mean=np.mean([z[k] for k in new]) if new else np.nan,
        sh_correct=z[cur]/tot,sh_recent=(z[cur-1]/tot if cur>1 else np.nan),sh_trained=(z[1]/tot if cur>1 else np.nan),
        sh_oldmean=(np.mean([z[k] for k in old])/tot if old else np.nan),sh_nevermean=(np.mean([z[k] for k in new])/tot if new else np.nan),
        z1=z[1],z2=z[2],z3=z[3],z4=z[4]))
S=pd.DataFrame(rows); S.to_pickle('gz.pkl')
print(S.groupby(['Condition','Phase','G3']).size().unstack())
