"""Per-mouse summary used to choose the example mice (M22, M33, M34) for Figures 16-20.

## NOT IN MATLAB. Prints, for every mouse: number of wall-to-goal runs and % rewarded (visible, hidden, hidden
## phase 10), median time in goal and entry speed at hidden phase 10, launch distance and straightness V/H.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK
import numpy as np, pandas as pd
D=WORK+'/approach/'
segs=pd.read_pickle(D+'segs.pkl'); M=pd.read_pickle(D+'mouseF.pkl'); V=pd.read_pickle(D+'visits.pkl')
p=pd.read_pickle(WORK+'/probe.pkl'); G=p.drop_duplicates('MouseID').set_index('MouseID').G3
rows=[]
for m in M.Mouse.unique():
    d={'Mouse':int(m),'G':G[m]}
    for c in ['V','H']:
        rs=[rw for ph in [7,8,9,10] for (_,_,rw) in segs.get((m,ph,c),{'s':[]})['s']]
        d[f'n{c}']=len(rs); d[f'rw{c}']=np.mean(rs)
        rs10=[rw for (_,_,rw) in segs.get((m,10,c),{'s':[]})['s']]; d[f'rw10{c}']=np.mean(rs10) if rs10 else np.nan
    x=V[(V.Mouse==m)&(V.Cond=='H')&(V.Phase==10)&(V.role=='current')]
    d['dwell10']=x.dwell.median(); d['speed10']=x.ent_spd.median()
    q=M[M.Mouse==m].set_index('Cond'); d['launchV']=q.launch.V; d['launchH']=q.launch.H; d['straightV']=q.wall_st.V; d['straightH']=q.wall_st.H
    rows.append(d)
R=pd.DataFrame(rows).sort_values(['G','Mouse']); print(R.round(2).to_string()); print(R.groupby('G').median(numeric_only=True).round(2))
