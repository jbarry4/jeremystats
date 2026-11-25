"""Replay: each session's walking on the floor, replayed on a floor turning at another speed -> replay.pkl

The mouse's path on the floor = its room track turned back by the floor's refined reading (about that day's true
center). Turning that path forward again at a chosen speed gives the room track the same walking would have produced
on that floor; entrances and shocks are then counted with the tracker's rules (zone 45 deg +-30 about the tracker's
center; a new entrance needs 1.5 s outside; a shock on entry and every 2.5 s inside). Replayed at the session's own
speed, the track is the real one, which checks the counter against the tracker's own counts.
"""
import os
import pickle
import time

import numpy as np
import pandas as pd

import floorlib as FL

HERE = FL.HERE
O = pickle.load(open(os.path.join(HERE, "floor_check.pkl"), "rb"))
SESS = O["SESS"].set_index("key")
SPEEDS = [2.5, 3.5, 4.91, 6.0]
ZC, ZW = 45.0, 30.0


def runs(mask):
    m = np.r_[False, mask, False].astype(np.int8)
    d = np.diff(m)
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


def count(t, x, y, refr=1.5, isi=2.5):
    ang = np.degrees(np.arctan2(y, x))
    inz = np.abs((ang - ZC + 180.0) % 360.0 - 180.0) <= ZW
    s, e = runs(inz)
    if not s.size:
        return 0, 0, 0.0
    ts, te = t[s], t[np.minimum(e, len(t) - 1)]
    # merge visits separated by less than the refractory time
    keep = np.r_[True, (ts[1:] - te[:-1]) >= refr]
    grp = np.cumsum(keep) - 1
    gs = pd.Series(ts).groupby(grp).min().values
    ge = pd.Series(te).groupby(grp).max().values
    ent = len(gs)
    shocks = int(np.sum(1 + np.floor(np.maximum(ge - gs, 0) / isi)))
    return ent, shocks, float(inz.mean() * 100)


def main():
    t0 = time.time()
    rows = []
    for k, r in SESS[SESS.use].iterrows():
        t, X, Y, _lost = FL.track(k)
        om = float(r.local1)
        cx, cy = O["CENTER"][r.date]
        px, py = X - cx, Y - cy
        a = -np.radians(om) * t
        ax_, ay_ = px * np.cos(a) - py * np.sin(a), px * np.sin(a) + py * np.cos(a)      # the path on the floor
        row = dict(key=k, mouse=r.mouse, session=int(r.session), om=om)
        e0, s0, z0 = count(t, X, Y)
        row.update(ent_own=e0, sh_own=s0, zone_own=z0)
        for w in SPEEDS:
            b = np.radians(w) * t
            rx = cx + ax_ * np.cos(b) - ay_ * np.sin(b)
            ry = cy + ax_ * np.sin(b) + ay_ * np.cos(b)
            e, s, z = count(t, rx, ry)
            row.update({"ent_%g" % w: e, "sh_%g" % w: s, "zone_%g" % w: z})
        rows.append(row)
    R = pd.DataFrame(rows)
    pickle.dump(dict(R=R, SPEEDS=SPEEDS), open(os.path.join(HERE, "replay.pkl"), "wb"))
    print("replayed", len(R), "sessions in %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
