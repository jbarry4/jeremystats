"""EXPLORATORY. Second attempt: whole-session heading-to-goal index (moving > 5 cm/s, 10-50 cm from goal, with the other zones as control) and approach efficiency from 30 cm. Index near zero, effects small. Not in the report.
## NOT IN MATLAB.
"""
import os, sys
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [_HERE, os.path.join(_HERE, 'path_analysis')]
from config import DATA_ROOT, WORK, FIGS
import sys, json, numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
CM=75/255; SF=30
S=pd.read_pickle(WORK+'/approach/sessions.pkl'); P=json.load(open(WORK+'/approach/paths.json'))
sm=lambda a: pd.Series(a).rolling(5,center=True,min_periods=3).mean().values
def zones_for(mouse,hdrs):  # zone k = goal of phase 6+k for this mouse (hidden session header)
    return hdrs
rows=[];ent=[]
# collect goal centres per mouse/phase first
GC={}
for _,r in S.iterrows():
    if r.File not in P: continue
    h,_=read_dat(DATA_ROOT+'/'+P[r.File]) if False else (None,None)
for _,r in S.iterrows():
    if r.File not in P: continue
    fn=DATA_ROOT+'/'+P[r.File]
    with open(fn,errors='replace') as f:
        for line in f:
            if 'ReinforcedSector.0' in line and 'RoomTrack' not in line and '//' not in line:
                a,rp,dp=[float(v) for v in line.split('(')[1].split(')')[0].split()]; break
    GC[(r.Mouse,int(r.Phase))]=(127.5+127.5*rp/100*np.cos(np.radians(a)),127.5-127.5*rp/100*np.sin(np.radians(a)))
for _,r in S.iterrows():
    if r.File not in P: continue
    h,d=read_dat(DATA_ROOT+'/'+P[r.File]); st=d['state']
    X=sm(np.where(d['X']==0,np.nan,d['X'])); Y=sm(np.where(d['Y']==0,np.nan,d['Y']))
    gx,gy,gr=target_xy(h)
    vx=np.r_[np.nan,np.diff(X)]; vy=np.r_[np.nan,np.diff(Y)]; sp=np.hypot(vx,vy)*CM*SF
    def hidx(cx,cy,mask):
        tx,ty=cx-X,cy-Y; c=(vx*tx+vy*ty)/(np.hypot(vx,vy)*np.hypot(tx,ty)); m=mask&~np.isnan(c); return np.mean(c[m])
    dist=np.hypot(X-gx,Y-gy)*CM
    moving=(sp>5)&(dist>10)&(dist<50)
    goal_h=hidx(gx,gy,moving)
    others=[GC[(r.Mouse,ph)] for ph in range(7,11) if ph!=int(r.Phase) and (r.Mouse,ph) in GC]
    ctrl=[]
    for (cx,cy) in others:
        dd=np.hypot(X-cx,Y-cy)*CM; ctrl.append(hidx(cx,cy,(sp>5)&(dd>10)&(dd<50)))
    # approach efficiency from 30 cm
    E=np.where((st[:-1]==0)&(st[1:]==1))[0]+1; rew_t=np.where((st[:-1]==1)&(st[1:]==2))[0]+1
    effs=[]
    for e in E:
        far=np.where(dist[:e]>=30)[0]
        if not len(far): continue
        s0=far[-1]
        if e-s0>30*SF: continue
        xs,ys=X[s0:e+1],Y[s0:e+1]; v=~np.isnan(xs)
        if v.sum()<5: continue
        L=np.nansum(np.hypot(np.diff(xs[v]),np.diff(ys[v])))*CM
        nxt=np.where(st[e:]==0)[0]; end=e+(nxt[0] if len(nxt) else len(st)-e)
        rewarded=((rew_t>=e)&(rew_t<end)).any()
        eff=(dist[s0]-dist[e])/L if L>0 else np.nan
        ent.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,rewarded=rewarded,eff=eff,dur=(e-s0)/SF,length=L))
    rows.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,goal_heading=goal_h,ctrl_heading=np.nanmean(ctrl),
        frac_far_approach=len([1 for x in ent if x['Mouse']==r.Mouse and x['Phase']==r.Phase and x['Cond']==r.Condition])/max(len(E),1)))
pd.DataFrame(rows).to_pickle(WORK+'/approach/sess2.pkl'); pd.DataFrame(ent).to_pickle(WORK+'/approach/ent2.pkl')
print('ok',len(rows),len(ent))
