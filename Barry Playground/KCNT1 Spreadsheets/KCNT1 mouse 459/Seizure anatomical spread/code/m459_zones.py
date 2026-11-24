import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from scipy.ndimage import uniform_filter1d
ZONES = {  # CSC numbers, inclusive
 "supra_distal": (28, 31), "supra_prox": (33, 34), "supra_GCL": (35, 39), "hilus": (40, 49),
 "infra_GCL": (50, 52), "infra_prox": (53, 54), "infra_distal": (56, 58)}
SOS = sg.butter(4, [1, 300], "band", fs=FS, output="sos")
def csd(X):  # no spatial smoothing; row i = CSC i+1; edges NaN; µV/mm²
    C = -np.diff(X, 2, axis=0) / 0.05**2
    return np.vstack([np.full((1, X.shape[1]), np.nan), C, np.full((1, X.shape[1]), np.nan)])
zm = lambda C, z: np.nanmean(C[ZONES[z][0]-1:ZONES[z][1]], 0)
# baseline: median |CSD| per zone, 400-840 s
B = csd(sg.sosfiltfilt(SOS, L[:, idx(400):idx(840)], axis=1))
BASE = {z: np.median(np.abs(zm(B, z))) for z in ZONES}
# DG-wide activity for detection (independent of any one zone): sum |CSD| CSC 28-58, 10 ms smoothing
dg_b = uniform_filter1d(np.nansum(np.abs(B[27:58]), 0), int(0.01 * FS)); thr = np.median(dg_b) + 15 * (np.median(np.abs(dg_b - np.median(dg_b))) / .6745)
a0, a1 = 880.0, 922.0
X = sg.sosfiltfilt(SOS, L[:, idx(a0):idx(a1)], axis=1); C = csd(X)
dg = uniform_filter1d(np.nansum(np.abs(C[27:58]), 0), int(0.01 * FS))
pk, _ = sg.find_peaks(dg, height=thr, distance=int(0.06 * FS), prominence=thr * 0.5)
t = a0 + pk / FS
print("baseline |CSD| medians:", {z: int(v) for z, v in BASE.items()}, " detect thr", int(thr), " n discharges", len(pk))
W = int(0.03 * FS)
rows = []
for p in pk:
    s = slice(p - W, p + W); r = [a0 + p / FS]
    for z in ZONES:
        y = zm(C, z)[s]; k = np.argmin(y); r += [-y[k] / BASE[z], (k - W) / FS * 1000]   # sink amp (× baseline), time rel. peak (ms)
    rows.append(r)
R = np.array(rows); np.save(SP + "m459_cache/zones_discharges.npy", R)
names = list(ZONES)
print("\nmedian sink amplitude (× quiet baseline) per discharge")
print("window        n   " + " ".join(f"{z:>12s}" for z in names))
for w0, w1 in [(880, 886.5), (886.5, 888.7), (888.7, 892), (892, 897), (897, 902), (902, 907), (907, 912), (912, 916.5), (916.5, 922)]:
    m = (R[:, 0] >= w0) & (R[:, 0] < w1)
    if m.sum(): print(f"{w0:6.1f}-{w1:5.1f} {m.sum():3d}   " + " ".join(f"{np.median(R[m, 1 + 2*i]):12.1f}" for i in range(len(names))))
print("\nmedian sink timing (ms rel. DG peak), seizure 888.7-916.5")
m = (R[:, 0] >= 888.7) & (R[:, 0] < 916.5)
print(" ".join(f"{z}: {np.median(R[m, 2 + 2*i]):+.1f}" for i, z in enumerate(names)))
