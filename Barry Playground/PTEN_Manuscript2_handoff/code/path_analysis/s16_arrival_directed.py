"""Step 16. Arrival speed split by how the mouse got to the goal, and example runs for the figure.

Report Figure 23 (top) averages the speed around *every* entry into the goal zone, which pools
runs the mouse aimed at the goal from a distance with crossings it stumbled into.  The share of
directed entries is the same in every group, so the pooled comparison is fair, but it cannot say
whether a Hi mouse fails to settle on the runs it actually aimed.  This script recomputes the
same profile separately for directed entries (launch >= 20 cm, the definition used throughout)
and for the rest, and stores individual directed runs so they can be drawn with speed along the
path.

Speed for the profile is the centred 15-frame (0.5 s) displacement speed of s07, so that time
zero lines up with the entry.  The launch walk-back is the s04 algorithm, unchanged.

Outputs (WORK/approach/):
    arrival_dir.pkl    mean profile per session x entry type, with counts
    runs_ex.pkl        individual runs at phase 10 for the example panel
"""
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK
import numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena

CM = 75 / 255; SF = 30; W = 3 * SF
LAUNCH_MIN = 20.0          # cm; a "directed run", as everywhere else in this package
EX_PHASE = 10.0            # phase kept for the example panel
POST = int(3.0 * SF)       # frames kept after the entry for the examples

sm = lambda a: pd.Series(a).interpolate(limit=15).rolling(5, center=True, min_periods=3).mean().values

S = pd.read_pickle(WORK + '/approach/sessions.pkl')
P = json.load(open(WORK + '/approach/paths.json'))

prof = []; runs = []
for _, r in S.iterrows():
    if r.File not in P: continue
    h, d = read_dat(os.path.join(DATA_ROOT, P[r.File])); st = d['state']
    cx, cy, Rf = fit_arena(d['X'], d['Y'])
    Xs = sm(np.where(d['X'] == 0, np.nan, d['X'])); Ys = sm(np.where(d['Y'] == 0, np.nan, d['Y']))
    gx, gy, gr = target_xy(h)
    dist = np.hypot(Xs - gx, Ys - gy) * CM
    vx = np.gradient(Xs) * SF * CM; vy = np.gradient(Ys) * SF * CM; spd_g = np.hypot(vx, vy)
    ux, uy = (gx - Xs), (gy - Ys)
    err = np.degrees(np.arccos(np.clip((vx * ux + vy * uy) / (spd_g * np.hypot(ux, uy) + 1e-9), -1, 1)))
    inz = np.isin(st, [1, 2, 3]); mov = spd_g > 5

    # centred-window speed, as in s07, on raw (interpolated) coordinates
    Xi = pd.Series(np.where(d['X'] == 0, np.nan, d['X'])).interpolate(limit=15).values
    Yi = pd.Series(np.where(d['Y'] == 0, np.nan, d['Y'])).interpolate(limit=15).values
    k = 7; sp = np.full(len(Xi), np.nan)
    sp[k:-k] = np.hypot(Xi[2 * k:] - Xi[:-2 * k], Yi[2 * k:] - Yi[:-2 * k]) * CM / (2 * k / SF)

    E = np.where((st[:-1] == 0) & (st[1:] == 1))[0] + 1
    R = np.where((st[:-1] == 1) & (st[1:] == 2))[0] + 1
    E = E[(E > W) & (E < len(Xi) - W)]
    if len(E) == 0: continue

    keep = {True: [], False: []}
    for e in E:
        bad = 0; j = e - 1; lo = max(0, e - 20 * SF)
        while j > lo and not inz[j]:
            if mov[j] and err[j] < 45: bad = 0
            else: bad += 1
            if bad > 15: break
            j -= 1
        s_launch = min(j + bad, e - 1)
        launch = dist[s_launch]
        directed = bool(launch >= LAUNCH_MIN)
        keep[directed].append(sp[e - W:e + W + 1])

        nxt = np.where(st[e:] == 0)[0]; end = e + (nxt[0] if len(nxt) else len(st) - e)
        rw = bool(((R >= e) & (R < end)).any())
        if directed and r.Phase == EX_PHASE:
            a = max(s_launch, 0); b = min(e + POST, len(Xi) - 1)
            runs.append(dict(Mouse=r.Mouse, Phase=r.Phase, Cond=r.Condition, rewarded=rw,
                             launch=float(launch), ent_i=int(e - a),
                             x=(Xs[a:b + 1] - gx) * CM, y=(Ys[a:b + 1] - gy) * CM,
                             v=sp[a:b + 1].copy(), gr=float(gr * CM),
                             dwell=float((end - e) / SF)))
    for directed, M in keep.items():
        if not M: continue
        prof.append(dict(Mouse=r.Mouse, Phase=r.Phase, Cond=r.Condition, directed=directed,
                         prof=np.nanmean(np.vstack(M), 0), n=len(M)))

pd.DataFrame(prof).to_pickle(WORK + '/approach/arrival_dir.pkl')
pd.DataFrame(runs).to_pickle(WORK + '/approach/runs_ex.pkl')
print('profiles', len(prof), ' example runs', len(runs))
