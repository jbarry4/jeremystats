"""Step 1. Check every raw file against the PlaceAccuracy output (AllProbeSessions.sav, via WORK/probe.pkl).

Rewards  = number of state 1 -> 2 transitions  (MATLAB: Nshocks = sum(Shocks(1:end-1)==1 & Shocks(2:end)==2))
Entrances= number of state 0 -> 1 transitions  (MATLAB: Nent   = sum(Shocks(1:end-1)==0 & Shocks(2:end)==1))
Goal time= share of frames in states 1, 2 or 3 (MATLAB: PGoalTime)
All three are computed exactly as in MATLAB. Expected result: 0 mismatches out of 256.
"""
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK
import numpy as np, pandas as pd
from traj_lib import read_dat

S = pd.read_pickle(os.path.join(WORK, 'approach', 'sessions.pkl'))
P = json.load(open(os.path.join(WORK, 'approach', 'paths.json')))
p = pd.read_pickle(os.path.join(WORK, 'probe.pkl'))
bad = 0; gdiff = []
for _, r in S.iterrows():
    h, d = read_dat(os.path.join(DATA_ROOT, P[r.File])); st = d['state']
    rw = ((st[:-1] == 1) & (st[1:] == 2)).sum(); en = ((st[:-1] == 0) & (st[1:] == 1)).sum()
    gt = np.isin(st, [1, 2, 3]).mean()
    q = p[(p.MouseID == r.Mouse) & (p.Phase == r.Phase) & (p.Condition == r.Condition)]
    ok = len(q) == 1 and q.NumRewards.iloc[0] == rw and q.NumEntrances.iloc[0] == en
    if len(q) == 1: gdiff.append(abs(gt - q.PGoalTime.iloc[0]))
    if not ok:
        bad += 1; print('MISMATCH', r.File, rw, en, q[['NumRewards', 'NumEntrances']].values.tolist())
print('mismatches:', bad, 'of', len(S)); print('largest goal-time difference vs PGoalTime:', max(gdiff))
