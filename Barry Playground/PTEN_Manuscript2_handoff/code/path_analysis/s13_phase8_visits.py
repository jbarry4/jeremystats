"""Step 13. Timed visits to all four candidate zones in the phase 8 probes (first goal rotation), visible and hidden.

## NOT IN MATLAB: designed here for the phase 8 conflict analysis (report Figures 30 and 31).
Same visit rule as s06, but each visit keeps its entry time so that visits to different zones can be put in the
order the mouse made them. s06 does not keep times, so this step reads the phase 8 sessions again.

- Zone k of a mouse is the goal in the header of its phase k+6 session (as in s06). In phase 8:
  zone 2 = new (current) goal, zone 1 = old goal (phase 7 goal, also the trained location), zones 3 and 4 = never used yet.
- Visible phase 8: the cue sits on the new goal, so old vs new is a place-vs-cue conflict.
  Hidden phase 8 (about 32 min later): no cue, so old vs new is an old-place vs new-place conflict.
- A visit = the smoothed position enters the zone circle after having been more than 1.3 zone radii away.
- Launch distance (cm) = distance from the zone at the start of the run that led into it, walked back while
  speed > 5 cm/s and heading error < 45 degrees (up to 15 frames off course allowed, up to 20 s back), as in s04/s06.
  A directed run = launch >= 20 cm.
- rewarded: a reward (tracker state 1 -> 2) during a visit to the new zone.

Validated: visit counts, launch distances and rewarded flags match s06's WORK/approach/visits.pkl for phase 8.
Output: WORK/phase8/visits.pkl with Mouse, Cond (V/H), zone, role (new/old/never), t_in, t_out (s from start),
dwell (s), time_inside (s), launch (cm), rewarded, launch_t (s).
"""
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
import config
import numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena

DATA_ROOT, WORK = config.DATA_ROOT, config.WORK
OUT = os.path.join(WORK, 'phase8'); os.makedirs(OUT, exist_ok=True)
CM = 75 / 255; SF = 30
S = pd.read_pickle(os.path.join(WORK, 'approach', 'sessions.pkl')); P = json.load(open(os.path.join(WORK, 'approach', 'paths.json')))
sm = lambda a: pd.Series(a).interpolate(limit=15).rolling(5, center=True, min_periods=3).mean().values

Z = {}; D = {}
for _, r in S.iterrows():
    h, d = read_dat(os.path.join(DATA_ROOT, P[r.File]))
    Z.setdefault(r.Mouse, {})[int(r.Phase) - 6] = target_xy(h)
    if int(r.Phase) == 8: D[(r.Mouse, r.Condition)] = (h, d)

vis = []
for (m, c), (h, d) in D.items():
    st = d['state']; t = (d['ts'] - d['ts'][0]) / 1000.0
    X = sm(np.where(d['X'] == 0, np.nan, d['X'])); Y = sm(np.where(d['Y'] == 0, np.nan, d['Y']))
    vx = np.gradient(X) * SF * CM; vy = np.gradient(Y) * SF * CM; spd = np.hypot(vx, vy); mov = spd > 5
    for z, (gx, gy, gr) in Z[m].items():
        role = {2: 'new', 1: 'old'}.get(z, 'never')
        dist = np.hypot(X - gx, Y - gy); inside = dist < gr; out = dist > gr * 1.3
        ux, uy = gx - X, gy - Y
        err = np.degrees(np.arccos(np.clip((vx * ux + vy * uy) / (spd * np.hypot(ux, uy) + 1e-9), -1, 1)))
        armed = True
        for i in range(1, len(X)):
            if out[i]: armed = True
            if armed and inside[i] and not inside[i - 1]:
                armed = False; j = i
                while j < len(X) and not out[j]: j += 1
                bad = 0; k = i - 1; lo = max(0, i - 20 * SF)
                while k > lo:
                    if mov[k] and err[k] < 45: bad = 0
                    else: bad += 1
                    if bad > 15: break
                    k -= 1
                s0 = min(k + bad, i - 1)
                rw = ((st[i:j][:-1] == 1) & (st[i:j][1:] == 2)).any() if role == 'new' else False
                vis.append(dict(Mouse=m, Cond=c, zone=z, role=role, t_in=t[i], t_out=t[min(j, len(t) - 1)], dwell=(j - i) / SF,
                                time_inside=inside[i:j].sum() / SF, launch=dist[s0] * CM, rewarded=rw, launch_t=t[s0]))
V = pd.DataFrame(vis); V.to_pickle(os.path.join(OUT, 'visits.pkl'))
print(len(V), 'visits'); print(V.groupby(['Cond', 'role']).size())
