import numpy as np
from scipy import signal as sg
from scipy.ndimage import gaussian_filter1d
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
SP = "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad/"
z = np.load(SP + "m459_cache/m459_s1_400_1000.npz")
L = z["lfp"].astype(np.float32); M = z["mua"].astype(np.float32); FS = 2000.0; T0 = 400
L[58] = 0.5 * (L[57] + L[59]); M[58] = 0.5 * (M[57] + M[59])
b0, b1 = int((400 - T0) * FS), int((840 - T0) * FS)
B = L[:, b0:b1]; MB = M[:, int((400 - T0) * 1000):int((840 - T0) * 1000)]
bp = lambda X, lo, hi: sg.sosfiltfilt(sg.butter(4, [lo, hi], "band", fs=FS, output="sos"), X, axis=1)
rip = np.sqrt((bp(B, 150, 250) ** 2).mean(1)); mua = MB.mean(1); th = np.sqrt((bp(B, 5, 10) ** 2).mean(1))
lf = bp(B, 2, 40)
# theta phase relative to ch 7 (CA1 pyramidal per notes)
thf = bp(B, 5, 10); ref = thf[6]
thcorr = np.array([np.corrcoef(ref, thf[i])[0, 1] for i in range(64)])
# dentate spikes: detect on each candidate hilus ch, pick ch with largest DS-like peaks
def ds_avg(hc, thr=5):
    x = lf[hc]; sd = np.median(np.abs(x)) / 0.6745
    pk, _ = sg.find_peaks(x, height=thr * sd, distance=int(0.2 * FS), width=(int(0.005*FS), int(0.04*FS)))
    pk = pk[(pk > 400) & (pk < lf.shape[1] - 400)]
    seg = np.stack([lf[:, p - 200:p + 200] for p in pk]) if len(pk) else None
    return pk, seg
best = None
for hc in range(20, 50):
    pk, seg = ds_avg(hc)
    if seg is None: continue
    a = seg.mean(0); score = a[hc, 200] / (np.abs(a[:, 200]).mean() + 1e-9)
    if best is None or len(pk) * score > best[0]: best = (len(pk) * score, hc, pk, seg)
_, hc, pk, seg = best
avg = seg.mean(0)
csd = -np.diff(gaussian_filter1d(avg, 1, axis=0), 2, axis=0) / (0.05 ** 2)
print("DS trigger channel CSC", hc + 1, "n DS =", len(pk))
print("ch  ripRMS  MUA  thetaCorr(vs ch7)  DSpeak  DS_CSD@peak")
for i in range(64):
    print(f"{i+1:3d} {rip[i]:6.1f} {mua[i]:6.1f} {thcorr[i]:6.2f} {avg[i,200]:8.0f} {csd[i-1,200] if 0<i<63 else float('nan'):10.0f}")
fig, ax = plt.subplots(1, 5, figsize=(16, 9), sharey=True)
y = np.arange(1, 65)
ax[0].plot(rip, y); ax[0].set_title("Ripple RMS 150-250")
ax[1].plot(mua, y); ax[1].set_title("MUA mean")
ax[2].plot(thcorr, y); ax[2].axvline(0, c="k", lw=.5); ax[2].set_title("Theta corr vs CSC7")
t = (np.arange(400) - 200) / FS * 1000
for i in range(64): ax[3].plot(t, -avg[i] / np.abs(avg).max() * 3 + i + 1, c="k", lw=.6)
ax[3].set_title(f"DS-triggered LFP (n={len(pk)}, trig CSC{hc+1})")
lim = np.percentile(np.abs(csd), 99)
ax[4].imshow(csd, aspect="auto", cmap="RdBu", vmin=-lim, vmax=lim, extent=[t[0], t[-1], 63.5, 1.5])
ax[4].set_title("DS-triggered CSD (sink red)")
ax[0].invert_yaxis(); ax[0].set_ylabel("CSC")
for a in ax: a.grid(alpha=.3)
fig.savefig(SP + "m459_layermap_diag.png", dpi=110, bbox_inches="tight")
np.savez(SP + "m459_cache/layerdiag.npz", rip=rip, mua=mua, thcorr=thcorr, avg=avg, csd=csd, hc=hc)
