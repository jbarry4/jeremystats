"""EXPLORATORY. Prototype of the wall-to-goal run measure that became s04. Not in the report.
## NOT IN MATLAB.
"""
import os, sys
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [_HERE, os.path.join(_HERE, 'path_analysis')]
from config import DATA_ROOT, WORK, FIGS
import sys, json, numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena
CM=75/255; SF=30
S=pd.read_pickle(WORK+'/approach/sessions.pkl'); P=json.load(open(WORK+'/approach/paths.json'))
sm=lambda a: pd.Series(a).rolling(5,center=True,min_periods=3).mean().values
ent=[]
for _,r in S.iterrows():
    if r.File not in P: continue
    h,d=read_dat(DATA_ROOT+'/'+P[r.File]); st=d['state']
    cx,cy,Rf=fit_arena(d['X'],d['Y'])
    X=sm(np.where(d['X']==0,np.nan,d['X'])); Y=sm(np.where(d['Y']==0,np.nan,d['Y']))
    gx,gy,gr=target_xy(h)
    rad=np.hypot(X-cx,Y-cy)/Rf      # 1 = path edge (wall)
    wall=rad>0.8
    dist=np.hypot(X-gx,Y-gy)*CM
    E=np.where((st[:-1]==0)&(st[1:]==1))[0]+1; rew_t=np.where((st[:-1]==1)&(st[1:]==2))[0]+1
    inz=np.isin(st,[1,2,3])
    for e in E:
        w=np.where(wall[:e])[0]
        if not len(w): continue
        s0=w[-1]   # last frame at the wall before entry
        if e-s0>20*SF or e-s0<3: continue
        if inz[s0:e].any(): continue
        xs,ys=X[s0:e+1],Y[s0:e+1]; v=~np.isnan(xs)
        if v.sum()<3: continue
        L=np.nansum(np.hypot(np.diff(xs[v]),np.diff(ys[v])))*CM; D=np.hypot(xs[v][-1]-xs[v][0],ys[v][-1]-ys[v][0])*CM
        nxt=np.where(st[e:]==0)[0]; end=e+(nxt[0] if len(nxt) else len(st)-e)
        rewarded=((rew_t>=e)&(rew_t<end)).any()
        ent.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,rewarded=rewarded,wall_straight=D/L if L>0 else np.nan,wall_dur=(e-s0)/SF,wall_len=L))
    # also: fraction of entries that come straight from the wall within 3 s
pd.DataFrame(ent).to_pickle(WORK+'/approach/ent3.pkl'); print(len(ent))
