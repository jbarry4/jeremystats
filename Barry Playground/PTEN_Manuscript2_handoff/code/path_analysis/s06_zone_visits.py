"""Step 6. Visits to every candidate goal zone (current, previous, trained, other) in every probe session.

## NOT IN MATLAB: TargetTrajectories.m has no equivalent of this analysis; it was designed here.
A visit = the smoothed position enters the zone circle (geometric, not the tracker state) after having been
more than 1.3 zone radii away (hysteresis). For each visit: launch distance toward that zone (same rule as
s04), time until the mouse is again > 1.3 radii away (dwell), mean speed over the first 0.5 s inside (ent_spd),
and, for the current zone, whether a reward occurred during the visit. Zone roles: current = phase - 6;
previous = phase - 7 (unless it is zone 1); trained = zone 1; other = the rest.
Output: WORK/approach/visits.pkl. Used by s08 (arrival measures; directed run = launch >= 20 cm) and s09.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
# Directed visits to every candidate goal zone (current, previous, trained, other) in every probe session
import sys, json, numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena
CM=75/255; SF=30
S=pd.read_pickle(WORK+'/approach/sessions.pkl'); P=json.load(open(WORK+'/approach/paths.json'))
sm=lambda a: pd.Series(a).interpolate(limit=15).rolling(5,center=True,min_periods=3).mean().values
D={}
for _,r in S.iterrows():
    h,d=read_dat(os.path.join(DATA_ROOT,P[r.File])); D[(r.Mouse,r.Phase,r.Condition)]=(h,d)
Z={}
for (m,ph,c),(h,d) in D.items(): Z.setdefault(m,{})[int(ph)-6]=target_xy(h)
rows=[]; vis=[]
for (m,ph,c),(h,d) in D.items():
    st=d['state']; ph=int(ph); cur=ph-6
    cx,cy,Rf=fit_arena(d['X'],d['Y'])
    X=sm(np.where(d['X']==0,np.nan,d['X'])); Y=sm(np.where(d['Y']==0,np.nan,d['Y']))
    vx=np.gradient(X)*SF*CM; vy=np.gradient(Y)*SF*CM; spd=np.hypot(vx,vy)
    wall=np.hypot(X-cx,Y-cy)/Rf>0.8
    for z,(gx,gy,gr) in Z[m].items():
        dist=np.hypot(X-gx,Y-gy)
        inside=dist<gr; out=dist>gr*1.3   # hysteresis: must leave to 1.3 radii before a new visit counts
        ux,uy=gx-X,gy-Y; err=np.degrees(np.arccos(np.clip((vx*ux+vy*uy)/(spd*np.hypot(ux,uy)+1e-9),-1,1)))
        mov=spd>5
        armed=True; last_out=0
        for i in range(1,len(X)):
            if out[i]: armed=True; last_out=i
            if armed and inside[i] and not inside[i-1]:
                armed=False
                bad=0; k=i-1; lo=max(0,i-20*SF)
                while k>lo:
                    if mov[k] and err[k]<45: bad=0
                    else: bad+=1
                    if bad>15: break
                    k-=1
                s=min(k+bad,i-1); launch=dist[s]*CM
                # dwell: frames until leaving to 1.3 radii
                j=i
                while j<len(X) and not out[j]: j+=1
                rw=((st[i:j][:-1]==1)&(st[i:j][1:]==2)).any() if z==cur else False
                ent_spd=np.nanmean(spd[i:min(i+15,len(X))])
                role='current' if z==cur else ('previous' if (z==cur-1 and z!=1) else ('trained' if z==1 else 'other'))
                if ph==7 and z!=1: role='other'
                vis.append(dict(Mouse=m,Phase=ph,Cond=c,zone=z,role=role,launch=launch,dwell=(j-i)/SF,ent_spd=ent_spd,rewarded=rw))
pd.DataFrame(vis).to_pickle(WORK+'/approach/visits.pkl'); print(len(vis))
