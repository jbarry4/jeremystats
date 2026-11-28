"""Why does stage 1 look like a supra-blade event in the raster while the bottom plot (and the stage drawing) say hilus?
Absolute |CSD| per zone vs each zone's own quiet baseline, in the 0-1 s window, and when each zone first rises."""
import os, sys
import numpy as np
from scipy import signal as sg
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
SEA = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\app\tools\seahorse"
sys.path.insert(0, SEA)
import story_m459 as S  # noqa: E402

d = np.load(S.CACHE)
L, Lb = d["L"].astype(np.float64), d["Lb"].astype(np.float64)
w0 = S.window_start(d)
FS = S.FS_LFP
t = w0 + np.arange(L.shape[1]) / FS - S.ONSET


def csd(X, pitch=S.FIG_PITCH_MM):
    Xf = sg.sosfiltfilt(sg.butter(4, 60, fs=FS, output="sos"), S.fix_bad(X), axis=1)
    C = -np.diff(gaussian_filter1d(Xf, 1.2, axis=0), 2, axis=0) / pitch ** 2
    return np.vstack([np.full((1, C.shape[1]), np.nan), C, np.full((1, C.shape[1]), np.nan)])


C, Cb = csd(L), csd(Lb)
A = uniform_filter1d(np.abs(np.nan_to_num(C)), int(0.1 * FS), axis=1)
Ab = uniform_filter1d(np.abs(np.nan_to_num(Cb)), int(0.1 * FS), axis=1)
base = np.median(Ab, 1)
G = {"CA1": (5, 9), "CA1 all": (2, 27), "Supra blade": (28, 39), "Hilus": (40, 49), "Infra blade": (50, 58)}
w1 = (t >= 0) & (t < 1)
pre = (t >= -3) & (t < 0)
print("zone            baseline|CSD|  pre(-3..0)abs  stage1 abs   stage1 peak abs   stage1 ratio(median ch)  peak ratio")
for k, (a, b) in G.items():
    rows = slice(a - 1, b)
    bz = np.median(base[rows])
    s1 = np.median(A[rows][:, w1])
    pk = np.max(np.median(A[rows][:, w1], 0))
    pr = np.median(A[rows][:, pre])
    rat = np.median(A[rows][:, w1] / base[rows, None])
    prat = np.max(np.median(A[rows][:, w1] / base[rows, None], 0))
    print("%-14s %10.0f %14.0f %12.0f %14.0f %16.1f %16.1f" % (k, bz, pr, s1, pk, rat, prat))
# per channel: baseline, stage-1 mean abs, ratio
print("\nCSC  baseline  stage1_abs  ratio   (stage-1 window 0-1 s)")
for c in range(2, 60):
    r = c - 1
    print("%3d %9.0f %10.0f %7.1f" % (c, base[r], A[r, w1].mean(), A[r, w1].mean() / base[r]))
# first time each zone's ratio passes 10x / 20x (100 ms boxcar, 0.2 s smoothing like the figure)
R = A / base[:, None]
for k, (a, b) in G.items():
    z = uniform_filter1d(np.nanmedian(R[a - 1:b], 0), int(0.2 * FS))
    for thr in (10, 20, 30):
        m = (t > -1) & (z > thr)
        print("%-12s first > %dx at %s s" % (k, thr, ("%.2f" % t[m][0]) if m.any() else "never"))
# the sharpest event in stage 1: where is its first sink?
seg = (t >= 0.4) & (t < 0.8)
Cs = gaussian_filter1d(np.nan_to_num(C), 0.004 * FS, axis=1)
i = np.argmax(np.abs(Cs[27:49, seg]).max(0))
tt = t[seg][i]
print("\nbiggest CSD moment in 0.4-0.8 s at %.3f s; profile (CSC: CSD):" % tt)
j = np.flatnonzero(seg)[i]
print(" ".join("%d:%+.0f" % (c, Cs[c - 1, j] / 1000) for c in range(26, 52)))
for lag in (-0.03, -0.02, -0.01, -0.005, 0.0):
    jj = np.argmin(np.abs(t - (tt + lag)))
    print("t%+.3f  " % lag + " ".join("%d:%+.0f" % (c, Cs[c - 1, jj] / 1000) for c in range(26, 52)))
