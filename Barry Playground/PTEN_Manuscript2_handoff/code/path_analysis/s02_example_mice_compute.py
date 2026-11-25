"""Step 2. Per-session quantities for the example mice (report Figures 16-19), following TargetTrajectories.m.

Default example mice: M22 (WT), M33 (Lo KO), M34 (Hi KO). The earlier set was M4, M10, M3: change MICE.
Output: WORK/traj/traj_examples.pkl

Per session, as in MATLAB:
  rewards / entrances (state transitions), rewarded-entry frames, speed (Speed_MtxEZ equivalent),
  target speed = speed in the goal zone (MATLAB: TargSpeed = SpeedMtx(tent), i.e. the speed value at each
  entrance; because the speed window runs ~0.4 s forward from that frame, it measures movement into and through
  the zone, not the approach. PlaceAccuracy's MeanTargSpeed),
  mean speed (nanmean), time in each goal zone = share of frames within TargetRadius of the zone centre.

## DEVIATION FROM MATLAB (zone centres): MATLAB takes G1-G4 from PTEN_Feeder_GoalZones.xlsx. Here each
## mouse's zone k is the goal position written in the header of its phase (k+6) hidden session.
## Zone times agree with AllProbes_ByGZLocation.sav within 0.35 percentage points for these mice.
"""
import os, sys, json, pickle
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK
import numpy as np, pandas as pd
from traj_lib import read_dat, target_xy, speed_matlab

MICE = [22, 33, 34]

S = pd.read_pickle(os.path.join(WORK, 'approach', 'sessions.pkl')); S = S[S.Mouse.isin(MICE)]
P = json.load(open(os.path.join(WORK, 'approach', 'paths.json')))
R = {}
for _, r in S.iterrows():
    h, d = read_dat(os.path.join(DATA_ROOT, P[r.File]))
    R[(int(r.Mouse), int(r.Phase), r.Condition)] = dict(k=r.File, h=h, d=d, targ=target_xy(h))
ZC = {m: {ph - 6: R[(m, ph, 'H')]['targ'][:2] for ph in range(7, 11)} for m in {k[0] for k in R}}
out = {}
for (m, ph, c), s in R.items():
    d = s['d']; X, Y, st, t = d['X'], d['Y'], d['state'], d['ts'] / 1000
    v = speed_matlab(X, Y, t); r = s['targ'][2]
    ent = np.where((st[:-1] == 0) & (st[1:] == 1))[0]      # frame before each entrance (MATLAB tent)
    rew = np.where((st[:-1] == 1) & (st[1:] == 2))[0]      # frame before each reward (MATLAB tSck2)
    z = {zz: (((X - x0) ** 2 + (Y - y0) ** 2) <= r ** 2).mean() for zz, (x0, y0) in ZC[m].items()}
    out[(m, ph, c)] = dict(k=s['k'], X=X, Y=Y, t=t, state=st, v=v, ent=ent, rew=rew, targ=s['targ'], zc=ZC[m], z=z,
                           n_rew=len(rew), n_ent=len(ent), gt=np.isin(st, [1, 2, 3]).mean(),
                           meanspeed=np.nanmean(v), targspeed=np.nanmean(v[ent]))
pickle.dump(out, open(os.path.join(WORK, 'traj', 'traj_examples.pkl'), 'wb'))

# table values used in the report (hidden sessions)
for c in ['H', 'V']:
    for m in MICE:
        for ph in [7, 8, 9, 10]:
            o = out[(m, ph, c)]; inz = np.isin(o['state'], [1, 2, 3])
            X = np.where(o['X'] == 0, np.nan, o['X']).astype(float); Y = np.where(o['Y'] == 0, np.nan, o['Y']).astype(float)
            sts = []
            for e in o['rew']:                                   # 3 s before entry = 4.2 to 1.2 s before the reward
                a = e - int(4.2 * 30); b = e - int(1.2 * 30)
                if a < 0: continue
                xs, ys = X[a:b + 1], Y[a:b + 1]; ok = ~np.isnan(xs)
                if ok.sum() < 3: continue
                L = np.nansum(np.hypot(np.diff(xs[ok]), np.diff(ys[ok]))); D = np.hypot(xs[ok][-1] - xs[ok][0], ys[ok][-1] - ys[ok][0])
                if L > 0: sts.append(D / L)
            print(c, m, ph, f"rewards {o['n_rew']} entries {o['n_ent']} s/entry {inz.sum()/30/max(o['n_ent'],1):.2f}",
                  f"zone speed {np.nanmean(o['v'][inz]):.1f} entry speed {o['targspeed']:.1f} mean speed {o['meanspeed']:.1f}",
                  f"straightness {np.mean(sts):.2f} zones", ' '.join(f"{o['z'][k]*100:.1f}" for k in range(1, 5)),
                  f"lost {(o['X']==0).mean()*100:.1f}%")
