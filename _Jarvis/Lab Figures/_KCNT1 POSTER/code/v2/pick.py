"""Score the extracted candidates and draw the best few of each kind (voltage + CSD) for a visual pick."""
import json
import numpy as np
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
FS = 2500.0
EVEN = list(range(2, 65, 2))
H_MM = 0.04            # H3: 20 um pitch, even contacts 40 um apart
BAD = [59]

def notch(X): b, a = iirnotch(60.0, 30.0, FS); return filtfilt(b, a, X, axis=-1)
def band(X, lo, hi): return sosfiltfilt(butter(3, [lo, hi], btype="band", fs=FS, output="sos"), X, axis=-1)
def evens(X):
    V = X[..., [c - 1 for c in EVEN], :].copy()
    return V
def csd(V):
    P = np.concatenate([V[..., :1, :], V, V[..., -1:, :]], axis=-2)
    return -(P[..., 2:, :] - 2 * P[..., 1:-1, :] + P[..., :-2, :]) / H_MM ** 2 / 1000.0

res = {}
for name in ("m1606", "m306"):
    z = np.load("windows_%s.npz" % name)
    X = z["X"].astype(np.float64); kind = z["kind"]; t = z["t"]
    n = X.shape[-1]; tt = (np.arange(n) / FS - float(z["half"])) * 1000.0
    w = (tt >= -150) & (tt <= 150); core = (tt >= -30) & (tt <= 30)
    out = {}
    for K in ("ds", "ds_curated", "ied"):
        idx = np.flatnonzero(kind == K)
        if not len(idx): continue
        Xn = notch(X[idx])
        if K.startswith("ds"):
            V = evens(band(Xn, 5.0, 100.0))
        else:
            V = evens(Xn); V = V - np.median(V[..., (tt >= -150) & (tt < -60)], axis=-1, keepdims=True)
        C = csd(V)
        tmpl = C[..., core].mean(axis=0)
        corr = np.array([np.corrcoef(c[..., core].ravel(), tmpl.ravel())[0, 1] for c in C])
        amp = np.abs(V[..., core]).max(axis=(-1, -2))
        pre = V[..., (tt >= -150) & (tt < -50)].std(axis=(-1, -2))
        post = V[..., (tt > 60) & (tt <= 150)].std(axis=(-1, -2))
        quiet = (pre + post) / amp
        zamp = np.abs(amp - np.median(amp)) / (1.4826 * np.median(np.abs(amp - np.median(amp))) + 1e-9)
        score = corr - 0.15 * zamp - 1.0 * quiet if K.startswith("ds") else corr + 0.3 * (amp / amp.max()) - 1.0 * quiet
        order = np.argsort(-score)
        out[K] = dict(idx=idx[order].tolist(), t=t[idx][order].tolist(), corr=corr[order].tolist(), amp=amp[order].tolist(), quiet=quiet[order].tolist())
        # contact sheet of the best 6
        fig, axs = plt.subplots(2, 6, figsize=(18, 7))
        for j in range(6):
            k = order[j]
            Vk, Ck = V[k][:, w], C[k][:, w]
            g = np.percentile(np.abs(Vk), 99.5)
            ax = axs[0, j]
            for i in range(len(EVEN)): ax.plot(tt[w], i - 1.6 * Vk[i] / g, "k", lw=0.4)
            ax.set_ylim(len(EVEN) + 0.5, -2); ax.set_title("%s %s t=%.3f\ncorr %.2f amp %.0f quiet %.2f" % (name, K, t[idx][k], corr[k], amp[k], quiet[k]), fontsize=7)
            ax = axs[1, j]
            cl = np.percentile(np.abs(Ck), 99.5)
            ax.imshow(Ck, aspect="auto", cmap="jet", vmin=-cl, vmax=cl, extent=[tt[w][0], tt[w][-1], len(EVEN) - 0.5, -0.5])
        fig.tight_layout(); fig.savefig("sheet_%s_%s.png" % (name, K), dpi=70); plt.close(fig)
    res[name] = out
json.dump(res, open("picks.json", "w"), indent=1)
for name, o in res.items():
    for K, v in o.items():
        print(name, K, ["%.3f(c%.2f,a%.0f,q%.2f)" % (a, b, c, d) for a, b, c, d in zip(v["t"][:6], v["corr"][:6], v["amp"][:6], v["quiet"][:6])])
