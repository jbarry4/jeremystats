"""SUPERSEDED / NOT USED IN THE REPORT. First version of s02 (M24/M4, M10, M3 example mice, files found by name). Superseded by path_analysis/s02.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
import sys; sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'path_analysis'))
from traj_lib import *
import pickle
PIX=75/255; SF=30
def speed(X,Y,t,w=15,sh=12):
    Xn=pd.Series(np.where(X==0,np.nan,X)); Yn=pd.Series(np.where(Y==0,np.nan,Y))
    v=(np.sqrt(Xn.diff(w)**2+Yn.diff(w)**2)*PIX/pd.Series(t).diff(w)).values
    return np.roll(v,-sh)
S={}
for f in FILES:
    k=os.path.basename(f).replace('Track_Room.dat',''); h,d=read_dat(f); m,ph,c=parse_name(k)
    S[(m,ph,c)]=dict(k=k,h=h,d=d,targ=target_xy(h))
ZC={m:{ph-6:S[(m,ph,'H')]['targ'][:2] for ph in range(7,11)} for m in {k[0] for k in S}}
out={}
for (m,ph,c),s in S.items():
    d=s['d']; X,Y,st,t=d['X'],d['Y'],d['state'],d['ts']/1000
    v=speed(X,Y,t); r=s['targ'][2]
    ent=np.where((st[:-1]==0)&(st[1:]==1))[0]; rew=np.where((st[:-1]==1)&(st[1:]==2))[0]
    z={z:(((X-x0)**2+(Y-y0)**2)<=r**2).mean() for z,(x0,y0) in ZC[m].items()}
    out[(m,ph,c)]=dict(k=s['k'],X=X,Y=Y,t=t,state=st,v=v,ent=ent,rew=rew,targ=s['targ'],zc=ZC[m],z=z,
        n_rew=len(rew),n_ent=len(ent),gt=np.isin(st,[1,2,3]).mean(),meanspeed=np.nanmean(v),targspeed=np.nanmean(v[ent]))
pickle.dump(out,open(WORK+'/traj/traj.pkl','wb'))
g=pd.read_pickle(WORK+'/gz/gz.pkl').set_index(['Mouse','Phase','Condition'])
for key in sorted(out):
    o=out[key]; gg=g.loc[key]
    print(key, o['n_rew'], 'z:',[round(o['z'][i]*100,2) for i in range(1,5)],'gz:',[round(gg[f'z{i}']*100,2) for i in range(1,5)])
