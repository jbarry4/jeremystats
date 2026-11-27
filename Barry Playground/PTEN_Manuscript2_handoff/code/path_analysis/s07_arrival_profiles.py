"""Step 7. Speed around each entry into the current goal (top of report Figure 23), all probe sessions.

## NOT IN MATLAB: TargetTrajectories.m has no equivalent of this analysis; it was designed here.
Speed here is displacement over a centred 15-frame (0.5 s) window, after interpolating gaps up to 15 frames.
## This differs from the MATLAB-matched speed (traj_lib.speed_matlab), which is shifted 12 frames; a centred
## window is used so that time zero lines up with the entry. Window: 3 s before to 3 s after each entry.
Output: WORK/approach/arrival.pkl (mean profile per session).
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
# Speed around each entry into the current goal, every probe session
import sys, json, numpy as np, pandas as pd
from traj_lib import read_dat
CM=75/255; SF=30; W=3*SF
S=pd.read_pickle(WORK+'/approach/sessions.pkl'); P=json.load(open(WORK+'/approach/paths.json'))
out=[]
for _,r in S.iterrows():
    h,d=read_dat(os.path.join(DATA_ROOT,P[r.File])); st=d['state']
    X=pd.Series(np.where(d['X']==0,np.nan,d['X'])).interpolate(limit=15).values; Y=pd.Series(np.where(d['Y']==0,np.nan,d['Y'])).interpolate(limit=15).values
    # centred 0.5 s window displacement speed
    k=7; sp=np.full(len(X),np.nan); sp[k:-k]=np.hypot(X[2*k:]-X[:-2*k],Y[2*k:]-Y[:-2*k])*CM/(2*k/SF)
    E=np.where((st[:-1]==0)&(st[1:]==1))[0]+1; E=E[(E>W)&(E<len(X)-W)]
    if len(E)==0: continue
    M=np.vstack([sp[e-W:e+W+1] for e in E])
    out.append(dict(Mouse=r.Mouse,Phase=r.Phase,Cond=r.Condition,prof=np.nanmean(M,0),n=len(E)))
pd.to_pickle(pd.DataFrame(out),WORK+'/approach/arrival.pkl'); print(len(out))
