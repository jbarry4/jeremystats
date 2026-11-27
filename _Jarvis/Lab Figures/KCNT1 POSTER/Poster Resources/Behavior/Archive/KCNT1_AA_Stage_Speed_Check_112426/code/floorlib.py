"""Floor (stage) speed check: shared helpers. The ride detector of a1_extract.passive_rides, with every setting exposed,
plus the cached tracks (c1_floor_cache.py)."""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PX = 3.122           # pixels per cm (every header)
C0 = 127.5           # the tracker's arena center in pixels (every header)
DEFAULT = dict(win=4, dr_max=0.4, sd_max=0.25, lo=1.5, hi=9.0, rmin=12.0, phase=0.0, cx=0.0, cy=0.0, drop_lost=False)

_Z = None
_F = None


def sessions():
    global _F
    if _F is None:
        _F = pd.read_csv(os.path.join(HERE, "floor_sessions.csv"), dtype={"mouse": str})
        _F["clock_h"] = [_hours(t) for t in _F.hdr_time]
    return _F


def _hours(s):
    try:
        hm, ap = s.split()
        h, m = map(int, hm.split(":"))
        return (h % 12 + (12 if ap.upper() == "PM" else 0)) + m / 60.0
    except Exception:  # noqa: BLE001
        return np.nan


def cache():
    global _Z
    if _Z is None:
        _Z = np.load(os.path.join(HERE, "floor_cache.npz"))
    return _Z


def track(key):
    """Room-frame track of one session in cm about the tracker's center (y up), lost frames carried forward as in
    a1_extract; returns t (s), X, Y, lost."""
    Z = cache()
    t = Z[key + "|t"].astype(float) / 1000.0
    px, py = Z[key + "|px"].astype(float), Z[key + "|py"].astype(float)
    lost = Z[key + "|st"] == 5
    x = pd.Series(np.where(lost, np.nan, px)).ffill().bfill().values
    y = pd.Series(np.where(lost, np.nan, py)).ffill().bfill().values
    return t, (x - C0) / PX, -(y - C0) / PX, lost


def windows(t, X, Y, lost=None, win=4, dr_max=0.4, sd_max=0.25, lo=1.5, hi=9.0, rmin=12.0, phase=0.0, cx=0.0, cy=0.0,
            drop_lost=False, detail=False):
    """Ride windows: `win` 1-s steps in a row with the radius changing < dr_max cm per step, the 1-s angular speeds'
    s.d. < sd_max and their mean between lo and hi deg/s, at > rmin cm from the center (cx, cy) (cm, tracker frame).
    Windows slide by 1 s (they overlap), exactly as a1_extract.passive_rides does with the defaults."""
    grid = np.arange(phase, t[-1], 1.0)
    i1 = np.searchsorted(t, grid)
    i1 = i1[i1 < len(t)]
    x, y = X[i1] - cx, Y[i1] - cy
    th = np.unwrap(np.arctan2(y, x))
    rad = np.hypot(x, y)
    dt = np.diff(t[i1])
    a = np.degrees(np.diff(th)) / dt
    dr = np.abs(np.diff(rad))
    n = len(a) - win + 1
    if n <= 0:
        return (np.zeros(0), np.zeros((0, 4))) if detail else np.zeros(0)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    A = sw(a, win)
    ok = (sw(dr, win) < dr_max).all(axis=1) & (A.std(axis=1) < sd_max)
    mean = A.mean(axis=1)
    ok &= (mean > lo) & (mean < hi) & (rad[:n] > rmin)
    if drop_lost and lost is not None:
        cl = np.r_[0, np.cumsum(lost)]
        # any lost frame between the window's first and last 1-s sample
        s, e = i1[:n], i1[win:win + n]
        ok &= (cl[e + 1] - cl[s]) == 0
    if not detail:
        return mean[ok]
    idx = np.flatnonzero(ok)
    ang = np.degrees(np.arctan2(y[idx + win // 2], x[idx + win // 2])) % 360
    info = np.c_[t[i1][idx], rad[idx + win // 2], ang, idx]
    return mean[ok], info


def angvel_steps(t, X, Y, lost, rmin=10.0, cx=0.0, cy=0.0):
    """Every 1-s angular speed at > rmin cm from the center (no lost frames): the raw material of the mode estimate."""
    i1 = np.searchsorted(t, np.arange(0, t[-1], 1.0))
    x, y = X[i1] - cx, Y[i1] - cy
    th = np.unwrap(np.arctan2(y, x))
    a = np.degrees(np.diff(th)) / np.diff(t[i1])
    rad = np.hypot(x, y)[1:]
    cl = np.r_[0, np.cumsum(lost)]
    clean = (cl[i1[1:] + 1] - cl[i1[:-1]]) == 0
    return a[(rad > rmin) & clean]


def kde_mode(v, lo=1.0, hi=10.0, bw=0.08):
    """Peak of a Gaussian kernel density between lo and hi (deg/s)."""
    v = np.asarray(v, float)
    v = v[(v > lo - 1) & (v < hi + 1)]
    if v.size < 20:
        return np.nan
    g = np.arange(lo, hi, 0.01)
    # binned KDE for speed
    h, e = np.histogram(v, bins=np.arange(lo - 1, hi + 1.0001, 0.01))
    c = (e[:-1] + e[1:]) / 2
    k = np.exp(-0.5 * ((np.arange(-400, 401) * 0.01) / bw) ** 2)
    dens = np.convolve(h, k, mode="same")
    sel = (c >= lo) & (c <= hi)
    return float(c[sel][np.argmax(dens[sel])]) if g.size else np.nan
