"""Step 21. Braking: where the mouse slows down, and how far out it starts.

Whishaw, Cassel & Jarrard (1995, J Neurosci 15:5779) take deceleration on approach as the sign
that an animal expects to find the goal at a place.  Their fimbria-fornix rats decelerated at the
same distance from the vanished platform as controls, which is how they concluded the rats knew
where it was and the deficit lay elsewhere.  This script applies the same logic here, with two
differences the task allows: the mice make tens of approaches per session rather than four, and
the goal moves, so braking can be scored separately at the current goal, at former goals, and
everywhere else.

Braking is the intention to check; a pause is the act.  Scoring braking separately matters
because a mouse that slows at a former goal and then moves on has still treated it as a
candidate, and the 1.2 s dwell rule makes that invisible to any pause measure.

Two measures:

1. BRAKING RATE BY PLACE.  Along the whole path, off the wall, a braking event is a drop from a
   local speed maximum of at least 12 cm/s to below half that speed within 1 s.  The event is
   placed where the mouse ended up slow, and assigned to the nearest zone kind within 2.5 zone
   radii: current goal, former goal, or a zone not yet used; otherwise it counts as elsewhere.
   Rates are per metre of off-wall path, because Hi mice cover about 29% more ground and a raw
   count would reward that.

2. BRAKING DISTANCE AT THE CURRENT GOAL.  On each directed run (launch >= 20 cm), the distance
   from the goal at which speed first falls below 70% of that run's approach maximum.  Runs with
   no such drop before the mouse reaches the goal are recorded as not braking, so the censoring
   is explicit: the proportion of runs with any braking is reported beside the distance.

Outputs (WORK/approach/): braking_events.csv, braking_runs.csv, braking_stats.txt
"""
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK
import numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena

CM = 75 / 255; SF = 30
LAUNCH_MIN = 20.0        # cm, a directed run, as everywhere in this package
WALL = 0.8               # fraction of fitted arena radius; beyond this is the wall annulus
NEAR = 2.5               # zone radii: how close a braking event must be to count as "at" a zone
V_HI = 12.0              # cm/s, the speed a mouse must reach for a slowdown to count as braking
DROP = 0.5               # it must fall below this fraction of that speed
WIN = 1.0                # within this many seconds
RUN_DROP = 0.7           # braking distance: first fall below this fraction of the approach max

sm = lambda a: pd.Series(a).interpolate(limit=15).rolling(5, center=True, min_periods=3).mean().values

S = pd.read_pickle(WORK + '/approach/sessions.pkl')
P = json.load(open(WORK + '/approach/paths.json'))

# zone k was the goal of phase k + 6; collect every zone's centre per mouse
hdrs = {}
for _, r in S.iterrows():
    if r.File in P:
        h, _ = read_dat(os.path.join(DATA_ROOT, P[r.File]))
        hdrs.setdefault(r.Mouse, {})[int(r.Phase) - 6] = target_xy(h)

EV = []; RUNS = []
for _, r in S.iterrows():
    if r.File not in P: continue
    h, d = read_dat(os.path.join(DATA_ROOT, P[r.File])); st = d['state']
    cx, cy, Rf = fit_arena(d['X'], d['Y'])
    Xs = sm(np.where(d['X'] == 0, np.nan, d['X'])); Ys = sm(np.where(d['Y'] == 0, np.nan, d['Y']))
    gx, gy, gr = target_xy(h)
    cur = int(r.Phase) - 6
    Z = hdrs.get(r.Mouse, {})

    # centred 15-frame displacement speed, as used for the arrival profiles
    k = 7; n = len(Xs); sp = np.full(n, np.nan)
    sp[k:-k] = np.hypot(Xs[2 * k:] - Xs[:-2 * k], Ys[2 * k:] - Ys[:-2 * k]) * CM / (2 * k / SF)
    rad = np.hypot(Xs - cx, Ys - cy)
    off = rad <= WALL * Rf                                  # off the wall
    step = np.r_[0, np.hypot(np.diff(Xs), np.diff(Ys))] * CM
    metres = np.nansum(step[off]) / 100.0

    # ---- 1. braking events
    w = int(WIN * SF)
    i = k + 1
    while i < n - w - k:
        if not (off[i] and sp[i] >= V_HI and np.isfinite(sp[i])):
            i += 1; continue
        if sp[i] < np.nanmax(sp[max(k, i - w // 2):i + w // 2 + 1]):   # must be the local peak
            i += 1; continue
        seg = sp[i:i + w + 1]
        below = np.where(seg < DROP * sp[i])[0]
        if len(below) == 0:
            i += 1; continue
        j = i + int(below[0] + np.argmin(seg[below[0]:]))               # where it ended up slow
        j = min(j, n - 1)
        cat = 'elsewhere'; best = NEAR
        for z, (zx, zy, zr) in Z.items():
            dd = np.hypot(Xs[j] - zx, Ys[j] - zy) / zr
            if dd < best:
                best = dd; cat = 'current' if z == cur else ('former' if z < cur else 'never')
        EV.append(dict(Mouse=r.Mouse, Phase=r.Phase, Cond=r.Condition, cat=cat,
                       v_peak=float(sp[i]), v_min=float(sp[j]),
                       d_goal=float(np.hypot(Xs[j] - gx, Ys[j] - gy) * CM)))
        i = j + k                                                       # don't re-detect the same slowdown
    EV.append(dict(Mouse=r.Mouse, Phase=r.Phase, Cond=r.Condition, cat='__metres__',
                   v_peak=np.nan, v_min=np.nan, d_goal=metres))

    # ---- 2. braking distance on directed runs into the current goal
    dist = np.hypot(Xs - gx, Ys - gy) * CM
    vx = np.gradient(Xs) * SF * CM; vy = np.gradient(Ys) * SF * CM; spg = np.hypot(vx, vy)
    ux, uy = gx - Xs, gy - Ys
    err = np.degrees(np.arccos(np.clip((vx * ux + vy * uy) / (spg * np.hypot(ux, uy) + 1e-9), -1, 1)))
    inz = np.isin(st, [1, 2, 3]); mov = spg > 5
    E = np.where((st[:-1] == 0) & (st[1:] == 1))[0] + 1
    E = E[(E > 3 * SF) & (E < n - 3 * SF)]
    for e in E:
        bad = 0; j2 = e - 1; lo = max(0, e - 20 * SF)
        while j2 > lo and not inz[j2]:
            if mov[j2] and err[j2] < 45: bad = 0
            else: bad += 1
            if bad > 15: break
            j2 -= 1
        s0 = min(j2 + bad, e - 1)
        if dist[s0] < LAUNCH_MIN: continue
        seg = sp[s0:e + 1]
        if np.all(~np.isfinite(seg)) or len(seg) < 5: continue
        vmax = np.nanmax(seg)
        if not vmax > 0: continue
        ib = np.where(seg < RUN_DROP * vmax)[0]
        ib = ib[ib > int(np.nanargmax(seg))] if len(ib) else ib         # after the peak
        braked = len(ib) > 0
        RUNS.append(dict(Mouse=r.Mouse, Phase=r.Phase, Cond=r.Condition,
                         launch=float(dist[s0]), v_max=float(vmax), braked=braked,
                         brake_dist=float(dist[s0 + ib[0]]) if braked else np.nan))

pd.DataFrame(EV).to_csv(os.path.join(WORK, 'approach', 'braking_events.csv'), index=False)
pd.DataFrame(RUNS).to_csv(os.path.join(WORK, 'approach', 'braking_runs.csv'), index=False)
print('braking events', (pd.DataFrame(EV).cat != '__metres__').sum(), ' directed runs', len(RUNS))
