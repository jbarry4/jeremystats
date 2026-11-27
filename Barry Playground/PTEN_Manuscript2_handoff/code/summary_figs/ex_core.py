"""Shared loader for the example-mouse figures in the standalone summary.

Arenas are drawn in the room view (y negated; see rotate), so the phase 7 goal sits in the upper
right quadrant and the goal rotation runs anti-clockwise through phases 8, 9 and 10.

Three mice are followed through the whole summary.  Each is the mouse closest to its group's
median across five measures that the summary shows (sessions to criterion, pause time at former
goals at hidden phase 10, total pause time at hidden phase 10, hidden-minus-cued speed, braking
rate at the current goal), scored as the summed absolute deviation from the group median in units
of that measure's median absolute deviation.  The rule was fixed before any figure was drawn.

    WT  M9    Lo  M8    Hi  M5

Definitions here are copied from the package, not re-derived, so the numbers in the summary match
the report:
  pauses   speed < 3 cm/s for 35-300 frames, wall annulus (> 0.8 x fitted arena radius) excluded (s11)
  zone kind  current goal / former goal / never used, within 2.5 zone radii of the pause (s18)
  speed    gradient speed for pauses; centred 15-frame displacement speed for arrival (s16, s21)
  directed run  launch >= 20 cm (whole package)
"""
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE),
                                                                   os.path.join(os.path.dirname(_HERE), 'path_analysis')]
from config import DATA_ROOT, WORK as _W, FIGS
import numpy as np, pandas as pd
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena

RAW = DATA_ROOT + '/'
WORK = _W

CM = 75 / 255; SF = 30
NEAR = 2.5          # zone radii: how close a pause must be to count as "at" a zone (s18)
WALL = 0.8          # fraction of fitted arena radius; beyond this is the wall annulus
LAUNCH_MIN = 20.0   # cm, a directed run

EX = [('CTL', 9.0, 'M9'), ('Lo', 8.0, 'M8'), ('Hi', 5.0, 'M5')]
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
# zone-kind colours, deliberately outside the group palette, with shape coding as well
KIND = {'current': '#0b0b0b', 'former': '#bf8700', 'never': '#8c8c8c', 'open': '#c9c8c2'}
KINDLAB = {'current': 'current goal', 'former': 'former goal', 'never': 'never used', 'open': 'open interior'}

sm = lambda a: pd.Series(a).interpolate(limit=15).rolling(5, center=True, min_periods=3).mean().values


def groups():
    p = pd.read_pickle(WORK + '/probe.pkl')
    return p.drop_duplicates('MouseID').set_index('MouseID').G3


def disp_speed(Xs, Ys, k=7):
    """Centred 15-frame displacement speed, as used for the arrival profiles (s16)."""
    n = len(Xs); sp = np.full(n, np.nan)
    i = np.arange(k, n - k)
    sp[i] = np.hypot(Xs[i + k] - Xs[i - k], Ys[i + k] - Ys[i - k]) * CM * SF / (2 * k)
    return sp


def load(mice=None, phases=(7, 8, 9, 10), conds=('H', 'V')):
    """Read the raw sessions for the given mice. Returns {(mouse, phase, cond): dict}."""
    S = pd.read_pickle(WORK + '/approach/sessions.pkl')
    P = json.load(open(WORK + '/approach/paths.json'))
    out = {}; zones = {}
    for _, r in S.iterrows():
        if r.File not in P: continue
        if mice is not None and r.Mouse not in mice: continue
        ph = int(r.Phase)
        h, d = read_dat(RAW + P[r.File])
        zones.setdefault(r.Mouse, {})[ph - 6] = target_xy(h)
        if ph not in phases or r.Condition not in conds: continue
        cx, cy, Rf = fit_arena(d['X'], d['Y'])
        X = sm(np.where(d['X'] == 0, np.nan, d['X'])); Y = sm(np.where(d['Y'] == 0, np.nan, d['Y']))
        out[(r.Mouse, ph, r.Condition)] = dict(
            X=X, Y=Y, state=d['state'], cx=cx, cy=cy, R=Rf, targ=target_xy(h), cur=ph - 6,
            spd=np.hypot(np.gradient(X), np.gradient(Y)) * SF * CM, vdisp=disp_speed(X, Y))
    for k in out: out[k]['zones'] = zones[k[0]]
    return out


def rotate(s, x, y):
    """Put centred coordinates (cm) into the room view.

    The tracker stores y running down the image, so plotting it straight into a y-up axis mirrors
    the arena vertically: the phase 7 goal lands in the lower right and the rotation sequence looks
    clockwise.  Negating y gives the room view, in which the phase 7 goal sits in the upper right
    quadrant (39-46 deg in every mouse) and phases 7 to 10 run anti-clockwise, which is the lab
    convention.  No rotation is applied: the zone layout is the same in every mouse, so none is
    needed, and the arenas are drawn as recorded."""
    return np.asarray(x), -np.asarray(y)


def zone_xy(s, z):
    """Zone centre and radius in centred cm, room view."""
    gx, gy, gr = s['zones'][z]
    zx, zy = rotate(s, (gx - s['cx']) * CM, (gy - s['cy']) * CM)
    return float(zx), float(zy), gr * CM


def path_xy(s):
    return rotate(s, (s['X'] - s['cx']) * CM, (s['Y'] - s['cy']) * CM)


def pauses(s):
    """Pause list for one session, with position in cm from the arena centre and zone kind."""
    X, Y, spd, st = s['X'], s['Y'], s['spd'], s['state']
    cx, cy, Rf, cur = s['cx'], s['cy'], s['R'], s['cur']
    slow = (spd < 3) & ~np.isnan(spd)
    e = np.diff(np.r_[0, slow.astype(int), 0])
    out = []
    for a, b in zip(np.where(e == 1)[0], np.where(e == -1)[0]):
        L = b - a
        if L < 35 or L > 300: continue
        px, py = np.nanmean(X[a:b]), np.nanmean(Y[a:b])
        if np.hypot(px - cx, py - cy) / Rf > WALL: continue
        D = {z: np.hypot(px - gx, py - gy) / gr for z, (gx, gy, gr) in s['zones'].items()}
        former = [z for z in D if z < cur]; never = [z for z in D if z > cur]
        if D.get(cur, 9) < NEAR: kind = 'current'
        elif former and min(D[z] for z in former) < NEAR: kind = 'former'
        elif never and min(D[z] for z in never) < NEAR: kind = 'never'
        else: kind = 'open'
        rx, ry = rotate(s, (px - cx) * CM, (py - cy) * CM)
        out.append(dict(dur=L / SF, x=float(rx), y=float(ry), kind=kind,
                        i0=a, i1=b, zone=min(D, key=D.get)))
    return pd.DataFrame(out)


def directed_runs(s, zone=None, v_min=5.0, head_max=45.0, slack=15, maxlen=20.0):
    """Runs toward a zone: launch >= 20 cm, walked back while speed > 5 cm/s and heading error
    < 45 deg, allowing 15 frames off course, searching up to 20 s (as elsewhere in the package).
    Returns a list of dicts with the frame window and the entry frame."""
    X, Y, spd = s['X'], s['Y'], s['spd']
    gx, gy, gr = s['targ'] if zone is None else s['zones'][zone]
    dist = np.hypot(X - gx, Y - gy)
    inside = dist < gr
    n = len(X); runs = []
    ent = np.where(inside[1:] & ~inside[:-1])[0] + 1
    for e in ent:
        i = e; bad = 0
        while i > 0 and e - i < maxlen * SF:
            dx, dy = gx - X[i], gy - Y[i]
            vx, vy = X[i] - X[i - 1], Y[i] - Y[i - 1]
            ok = spd[i] > v_min and np.hypot(vx, vy) > 0 and \
                np.degrees(abs(np.arctan2(dx * vy - dy * vx, dx * vx + dy * vy))) < head_max
            if ok: bad = 0
            else:
                bad += 1
                if bad > slack: break
            i -= 1
        i0 = i + bad
        launch = dist[i0] * CM
        if launch >= LAUNCH_MIN:
            runs.append(dict(i0=i0, ent=e, launch=launch))
    return runs
