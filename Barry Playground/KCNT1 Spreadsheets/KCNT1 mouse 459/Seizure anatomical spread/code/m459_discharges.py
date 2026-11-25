import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from scipy.ndimage import gaussian_filter1d
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
a0, a1 = 884.0, 920.0
s0, s1 = idx(a0), idx(a1)
X = L[:, s0:s1]
lf = sg.sosfiltfilt(sg.butter(4, [1, 100], "band", fs=FS, output="sos"), X, axis=1)
C = -np.diff(gaussian_filter1d(lf, 1, axis=0), 2, axis=0) / 0.05**2; C = np.vstack([C[:1]*0, C, C[:1]*0])   # row i = CSC i+1
hf = sg.sosfiltfilt(sg.butter(4, [150, 600], "band", fs=FS, output="sos"), X, axis=1)
t = a0 + np.arange(X.shape[1]) / FS
# discharges: troughs of upper-ML sink (CSC 29-33 mean CSD most negative)
ml_up = C[28:33].mean(0); ml_lo = C[52:57].mean(0)
bX = sg.sosfiltfilt(sg.butter(4, [1, 100], "band", fs=FS, output="sos"), L[:, idx(600):idx(840)], axis=1)
bC = -np.diff(gaussian_filter1d(bX, 1, axis=0), 2, axis=0) / 0.05**2
sd = np.median(np.abs(bC[27:32].mean(0))) / .6745
bhf = sg.sosfiltfilt(sg.butter(4, [150, 600], "band", fs=FS, output="sos"), L[:, idx(600):idx(840)], axis=1)
HSD = np.median(np.abs(bhf[39:49].mean(0))) / .6745
pk, pr = sg.find_peaks(-ml_up, prominence=25 * sd, distance=int(0.05 * FS))
print("discharges:", len(pk), "baseline-sd", round(sd))
rows = []
for p in pk:
    w = slice(max(p - int(0.04 * FS), 0), p + int(0.04 * FS))
    wide = slice(max(p - int(0.06 * FS), 0), p + int(0.12 * FS))
    inp_u = -C[28:33, w].mean(0).min(); inp_l = -C[52:57, w].mean(0).min()
    # output: HF (150-600) RMS in GCL+hilus (CSC 35-52) within wide window; population-spike count on hilus HF
    out_rms = np.sqrt((hf[34:52, wide] ** 2).mean())
    h = hf[39:49, wide].mean(0); hsd = HSD
    nps = len(sg.find_peaks(-h, height=8 * hsd, distance=int(0.003 * FS))[0])
    ca1 = np.sqrt((hf[3:10, wide] ** 2).mean())
    rows.append((t[p], inp_u, inp_l, out_rms, nps, ca1))
R = np.array(rows); np.save(SP + "m459_cache/discharges.npy", R)
for a, b in [(884, 886.5), (886.5, 889), (889, 892), (892, 897), (897, 902), (902, 907), (907, 912), (912, 916.5)]:
    m = (R[:, 0] >= a) & (R[:, 0] < b)
    if m.sum(): print(f"{a}-{b}: n={m.sum():3d}  ML-up sink {np.median(R[m,1]):8.0f}  ML-lo sink {np.median(R[m,2]):8.0f}  GCL/hilus HF rms {np.median(R[m,3]):6.1f}  popspikes/discharge {np.median(R[m,4]):4.1f}  CA1 HF {np.median(R[m,5]):5.1f}")
fig, ax = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
for a, k, lb in zip(ax, (1, 2, 3, 4), ("ML-up sink", "ML-lo sink", "GCL/hilus HF rms", "pop spikes")):
    a.plot(R[:, 0], R[:, k], ".", ms=4); a.set_ylabel(lb)
fig.savefig(SP + "m459_discharges.png", dpi=70, bbox_inches="tight")
