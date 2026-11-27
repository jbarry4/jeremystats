"""Fit a circle to the outer edge of a session's path. Used for display, and for the wall test in the approach analysis.

## DEVIATION FROM MATLAB: not in TargetTrajectories.m. MATLAB draws every session on the fixed arena
## (centre 127.5, radius 127.5). The camera view shifted a little between recording days, so raw paths
## differ in size and position (centre shifts up to ~4 cm, scale up to ~7%). For the figures, each path
## is re-centred and scaled to a common arena using this fit; zone circles and reward points get the same
## transform. All PlaceAccuracy-style measures (rewards, entries, zone times, speed) still use raw coordinates.
## In the approach analysis (s04, s06) the fit defines "at the wall" (outer 20% of the fitted radius).

Method: split the path into 90 angular bins around the current centre, take the 99th percentile of the
radius in each bin as an edge point, least-squares fit a circle to those points, repeat 3 times.
"""
import numpy as np


def fit_arena(X, Y, c0=(127.5, 127.5), nb=90, q=99, iters=3):
    ok = X > 0; x = X[ok].astype(float); y = Y[ok].astype(float); cx, cy = c0
    for _ in range(iters):
        a = np.arctan2(y - cy, x - cx); r = np.hypot(x - cx, y - cy)
        b = ((a + np.pi) / (2 * np.pi) * nb).astype(int) % nb
        px = []; py = []
        for k in range(nb):
            m = b == k
            if m.sum() < 20: continue
            rr = np.percentile(r[m], q); ang = (k + .5) / nb * 2 * np.pi - np.pi
            px.append(cx + rr * np.cos(ang)); py.append(cy + rr * np.sin(ang))
        px = np.array(px); py = np.array(py)
        A = np.c_[2 * px, 2 * py, np.ones(len(px))]
        s = np.linalg.lstsq(A, px ** 2 + py ** 2, rcond=None)[0]
        cx, cy = s[0], s[1]; R = np.sqrt(s[2] + cx ** 2 + cy ** 2)
    return cx, cy, R
