"""Step 11. After a miss: returns to each zone, and pause locations, in every probe session (report Figure 25).

## NOT IN MATLAB as an analysis. The pause definition borrows the MATLAB pause filter's minimum window:
## speed <= 3 cm/s for at least l_win_bottom = 35 frames (~1.2 s). MATLAB then removes windows shared with
## longer stillness windows (150-700 frames) and keeps one quadrant; here pauses longer than 300 frames
## (10 s) are dropped instead, pauses in the wall zone (radius > 0.8 x fitted arena radius) are dropped,
## and all quadrants are kept. Speed here is from the smoothed position (as in s04), not speed_matlab.

Exits: for each visit to each zone (geometric circle, hysteresis 1.3 radii as in s06), the exit is the first
frame beyond 1.3 radii. ret = seconds until the mouse is inside that zone again (searched up to 10 s);
maxd3 = farthest distance from the zone in the 3 s after exit; exit_spd = mean speed +-8 frames around exit;
rewarded = a reward (state 1 -> 2) during the visit (current zone only). A "miss" = unrewarded exit from the
current zone. Pauses: location, duration, whether mostly in goal states, and distance to each zone centre in
zone radii. Outputs: WORK/approach/exits.pkl, pauses.pkl.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
# After leaving a zone: does the mouse come back soon? And where does it pause?
import sys, json, numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena
CM=75/255; SF=30
S=pd.read_pickle(WORK+'/approach/sessions.pkl'); P=json.load(open(WORK+'/approach/paths.json'))
sm=lambda a: pd.Series(a).interpolate(limit=15).rolling(5,center=True,min_periods=3).mean().values
D={}
for _,r in S.iterrows():
    h,d=read_dat(os.path.join(DATA_ROOT,P[r.File])); D[(r.Mouse,int(r.Phase),r.Condition)]=(h,d)
Z={}
for (m,ph,c),(h,d) in D.items(): Z.setdefault(m,{})[ph-6]=target_xy(h)
ex=[]; pz=[]
for (m,ph,c),(h,d) in D.items():
    st=d['state']; cur=ph-6
    cx,cy,Rf=fit_arena(d['X'],d['Y'])
    X=sm(np.where(d['X']==0,np.nan,d['X'])); Y=sm(np.where(d['Y']==0,np.nan,d['Y']))
    spd=np.hypot(np.gradient(X),np.gradient(Y))*SF*CM
    wall=np.hypot(X-cx,Y-cy)/Rf>0.8
    n=len(X)
    role=lambda z: 'current' if z==cur else ('previous' if (z==cur-1 and z!=1) else ('trained' if z==1 else 'other'))
    # ---- exits and returns
    for z,(gx,gy,gr) in Z[m].items():
        if ph==7 and z!=1: rl='other'
        else: rl=role(z)
        dist=np.hypot(X-gx,Y-gy); inside=dist<gr; out=dist>gr*1.3
        i=1
        while i<n:
            if inside[i] and not inside[i-1]:
                j=i
                while j<n and not out[j]: j+=1          # exit = first frame beyond 1.3 radii
                if j>=n-5*SF: break
                rw=((st[i:j][:-1]==1)&(st[i:j][1:]==2)).any() if z==cur else False
                k=j; ret=None
                while k<min(n,j+10*SF):
                    if inside[k]: ret=(k-j)/SF; break
                    k+=1
                w=slice(j,j+3*SF); maxd=np.nanmax(dist[w])*CM
                ex.append(dict(Mouse=m,Phase=ph,Cond=c,zone=z,role=rl,rewarded=rw,ret=ret,maxd3=maxd,exit_spd=np.nanmean(spd[j-8:j+8])))
                i=k if ret is not None else j
            i+=1
    # ---- pauses: speed < 3 cm/s for 35-300 frames (MATLAB l_win_bottom = 35; long rests excluded), away from the wall
    slow=(spd<3)&~np.isnan(spd)
    edges=np.diff(np.r_[0,slow.astype(int),0]); starts=np.where(edges==1)[0]; ends=np.where(edges==-1)[0]
    for a,b in zip(starts,ends):
        L=b-a
        if L<35 or L>300: continue
        px,py=np.nanmean(X[a:b]),np.nanmean(Y[a:b])
        if np.hypot(px-cx,py-cy)/Rf>0.8: continue
        ingoal=np.isin(st[a:b],[1,2,3]).mean()>0.5
        rec=dict(Mouse=m,Phase=ph,Cond=c,dur=L/SF,ingoal=ingoal)
        for z,(gx,gy,gr) in Z[m].items():
            rec[f'd{z}']=np.hypot(px-gx,py-gy)/gr       # distance in zone radii
        rec['cur']=cur
        pz.append(rec)
pd.DataFrame(ex).to_pickle(WORK+'/approach/exits.pkl'); pd.DataFrame(pz).to_pickle(WORK+'/approach/pauses.pkl')
print(len(ex),len(pz))
