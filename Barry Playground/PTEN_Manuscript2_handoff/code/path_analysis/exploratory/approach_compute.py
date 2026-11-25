"""EXPLORATORY. First attempt: heading toward the goal and straightness over the last 3 s before every entry. No visible vs hidden difference, because any 3 s window that ends in an entry looks direct (selection on the outcome). Not in the report.
## NOT IN MATLAB.
"""
import os, sys
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [_HERE, os.path.join(_HERE, 'path_analysis')]
from config import DATA_ROOT, WORK, FIGS
import sys, json, os, numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
CM=75/255; SF=30; W=3*SF
S=pd.read_pickle(WORK+'/approach/sessions.pkl')
P=json.load(open(WORK+'/approach/paths.json'))
def smooth(a,k=5):
    s=pd.Series(a); return s.rolling(k,center=True,min_periods=3).mean().values
rows=[]; ent_rows=[]
for _,r in S.iterrows():
    f=r.File
    if f not in P: continue
    fn=DATA_ROOT+'/'+P[f]
    h,d=read_dat(fn); st=d['state']; X=np.where(d['X']==0,np.nan,d['X']); Y=np.where(d['Y']==0,np.nan,d['Y'])
    gx,gy,gr=target_xy(h)
    Xs,Ys=smooth(X),smooth(Y)
    vx=np.r_[np.nan,np.diff(Xs)]; vy=np.r_[np.nan,np.diff(Ys)]
    sp=np.hypot(vx,vy)*CM*SF
    tx,ty=gx-Xs,gy-Ys
    cosang=(vx*tx+vy*ty)/(np.hypot(vx,vy)*np.hypot(tx,ty))
    ent=np.where((st[:-1]==0)&(st[1:]==1))[0]+1
    rew_t=np.where((st[:-1]==1)&(st[1:]==2))[0]+1
    inzone=np.isin(st,[1,2,3])
    n_rew=len(rew_t)
    for e in ent:
        a=e-W
        if a<1: continue
        if inzone[a:e].any(): continue            # require 3 s fully outside the zone before entry
        nxt=np.where(st[e:]==0)[0]; end=e+(nxt[0] if len(nxt) else len(st)-e)
        rewarded=((rew_t>=e)&(rew_t<end)).any()
        c=cosang[a:e]; s=sp[a:e]; ok=(~np.isnan(c))&(s>2)
        xs,ys=Xs[a:e+1],Ys[a:e+1]; v=~np.isnan(xs)
        if v.sum()<60 or ok.sum()<15: continue
        L=np.nansum(np.hypot(np.diff(xs[v]),np.diff(ys[v]))); D=np.hypot(xs[v][-1]-xs[v][0],ys[v][-1]-ys[v][0])
        d0=np.hypot(xs[v][0]-gx,ys[v][0]-gy)*CM
        ent_rows.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,rewarded=rewarded,heading=np.nanmean(c[ok]),straight=D/L if L>0 else np.nan,start_dist=d0))
    rows.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,File=f,n_rew=n_rew,n_ent=len(ent),track_loss=np.isnan(X).mean()))
E=pd.DataFrame(ent_rows); Ssum=pd.DataFrame(rows)
E.to_pickle(WORK+'/approach/entries.pkl'); Ssum.to_pickle(WORK+'/approach/sess_counts.pkl')
print(len(Ssum),'sessions',len(E),'approach windows')
