"""Step 4. Approach measures for every entry into the current goal, all 256 probe sessions (report Figures 20-22).

## NOT IN MATLAB: TargetTrajectories.m has no equivalent of this analysis; it was designed here.
## MATLAB's own approach measure is the path over the 3 s before each rewarded entry (subplot 2,3,4) and the
## mean speed 30-45 cm from the target in that window (WarpSpeed). Those are conditioned on a reward and a
## fixed window, so they cannot show where an approach started; the measures below were built instead.
## An earlier attempt using the last 3 s before every entry is in exploratory/ (it showed no visible vs
## hidden difference because a window that ends in an entry always looks like a direct approach).

Coordinates: lost frames (X = 0) set to NaN, gaps up to 15 frames interpolated, 5-frame centred running mean.
Velocity: numpy gradient of the smoothed position x 30 frames/s x cm per pixel.
Per entry (state 0 -> 1):
  launch      distance from the goal (cm) where the final run toward it began. Working back from the entry,
              the run continues while the mouse moves > 5 cm/s with heading within 45 deg of the goal; up to
              15 frames (0.5 s) off course are allowed; search limited to 20 s.
  wall run    from the last frame at the wall (radius > 0.8 x fitted arena radius, arena_fit) to the entry,
              kept if the mouse did not enter the zone on the way and it lasted 3 frames to 20 s:
              straightness = straight-line distance / path length; duration (s).
  rewarded    whether a reward (state 1 -> 2) occurred before the mouse next left the zone (state 0).
Per session: share of non-goal time at the wall, total path length / rewards (path per reward), counts.
Outputs: WORK/approach/entF.pkl (entries), sesF.pkl (sessions), segs.pkl (wall-run coordinates for Figure 20).
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
import sys, json, numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena
CM=75/255; SF=30
S=pd.read_pickle(WORK+'/approach/sessions.pkl'); P=json.load(open(WORK+'/approach/paths.json'))
sm=lambda a: pd.Series(a).interpolate(limit=15).rolling(5,center=True,min_periods=3).mean().values
ent=[]; ses=[]; segs={}
for _,r in S.iterrows():
    if r.File not in P: continue
    h,d=read_dat(os.path.join(DATA_ROOT,P[r.File])); st=d['state']
    cx,cy,Rf=fit_arena(d['X'],d['Y'])
    X=sm(np.where(d['X']==0,np.nan,d['X'])); Y=sm(np.where(d['Y']==0,np.nan,d['Y']))
    gx,gy,gr=target_xy(h)
    rad=np.hypot(X-cx,Y-cy)/Rf; wall=rad>0.8
    dist=np.hypot(X-gx,Y-gy)*CM
    vx=np.gradient(X)*SF*CM; vy=np.gradient(Y)*SF*CM; spd=np.hypot(vx,vy)
    ux,uy=(gx-X),(gy-Y); err=np.degrees(np.arccos(np.clip((vx*ux+vy*uy)/(spd*np.hypot(ux,uy)+1e-9),-1,1)))
    inz=np.isin(st,[1,2,3])
    E=np.where((st[:-1]==0)&(st[1:]==1))[0]+1; R=np.where((st[:-1]==1)&(st[1:]==2))[0]+1
    mov=spd>5
    # session level
    L=np.nansum(np.hypot(np.diff(X),np.diff(Y)))*CM
    ses.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,wall_frac=np.nanmean(wall[~inz]),
        path_per_rew=L/max(len(R),1),n_rew=len(R),n_ent=len(E)))
    key=(r.Mouse,r.Phase,r.Condition); segs[key]=dict(cx=cx,cy=cy,R=Rf,gx=gx,gy=gy,gr=gr,s=[])
    for e in E:
        # launch: walk back while heading toward goal (allow 0.5 s of off-heading/stationary frames)
        bad=0; k=e-1; lo=max(0,e-20*SF)
        while k>lo and not inz[k]:
            if mov[k] and err[k]<45: bad=0
            else: bad+=1
            if bad>15: break
            k-=1
        s_launch=min(k+bad,e-1)
        launch=dist[s_launch]; launch_dur=(e-s_launch)/SF
        # from last wall contact
        w=np.where(wall[lo:e])[0]
        ws=np.nan; wd=np.nan; s0=None
        if len(w):
            s0=lo+w[-1]
            if not inz[s0:e].any() and e-s0>=3:
                xs,ys=X[s0:e+1],Y[s0:e+1]; v=~np.isnan(xs)
                pl=np.nansum(np.hypot(np.diff(xs[v]),np.diff(ys[v])))*CM
                ws=np.hypot(xs[v][-1]-xs[v][0],ys[v][-1]-ys[v][0])*CM/pl if pl>0 else np.nan; wd=(e-s0)/SF
            else: s0=None
        nxt=np.where(st[e:]==0)[0]; end=e+(nxt[0] if len(nxt) else len(st)-e)
        rw=((R>=e)&(R<end)).any()
        ent.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,rewarded=rw,launch=launch,launch_dur=launch_dur,
                        wall_straight=ws,wall_dur=wd,from_wall=s0 is not None))
        if s0 is not None: segs[key]['s'].append((X[s0:e+1].copy(),Y[s0:e+1].copy(),rw))
pd.DataFrame(ent).to_pickle(WORK+'/approach/entF.pkl'); pd.DataFrame(ses).to_pickle(WORK+'/approach/sesF.pkl')
pd.to_pickle(segs,WORK+'/approach/segs.pkl'); print(len(ent),len(ses))
