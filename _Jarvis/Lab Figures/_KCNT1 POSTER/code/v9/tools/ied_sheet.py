"""Contact sheet: the best-scoring m1609 IEDs drawn the way the methods figure draws them (CSD + every 4th contact's
voltage, +-150 ms, on the figure's own gain; and two contacts' 0-600 Hz spectrograms, +-400 ms).
usage: python ied_sheet.py VACC_DIR METRICS_JSON OUT.png N [first]
(VACC_DIR holds sharp_m1609_s1.npz from scan_sharp.py, ied_m1609_s1.npz and methods_fig_v4.py; METRICS_JSON is
data/sharp_metrics_m1609.json.)"""
import json, os, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt
V_DIR, MET, OUT, N = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
FIRST = int(sys.argv[5]) if len(sys.argv) > 5 else 0
sys.path.insert(0, V_DIR)
import methods_fig_v4 as MF  # noqa: E402
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

met = json.load(open(MET))
z_ = lambda v: (v - v.mean()) / v.std()                                         # noqa: E731
pk = np.array([abs(m["peak_uv"]) for m in met]); pr = np.array([m["prom_ratio"] for m in met])
fw = np.array([m["fwhm_ms"] for m in met]); hf = np.array([m["hf_db_med"] for m in met])
score = z_(np.log(pk)) + z_(np.log(pr)) - z_(np.log(fw)) + z_(hf)
order = np.argsort(-score)
npz = os.path.join(V_DIR, "sharp_m1609_s1.npz")
zz = np.load(npz)
have = set(np.round(zz["t"], 3))
cands = [met[i] for i in order if round(met[i]["t"], 3) in have][FIRST:FIRST + N]
cands.append([m for m in met if abs(m["t"] - 905.339) < 0.01][0])            # the v8 IED, for comparison
src = {round(t, 3): npz for t in zz["t"]}
src[905.339] = os.path.join(V_DIR, "ied_m1609_s1.npz")

hp = butter(3, 1.0, btype="high", fs=MF.FS, output="sos")
base_cache = {}
fig, axs = plt.subplots(3, len(cands), figsize=(3.3 * len(cands), 10.5), gridspec_kw=dict(height_ratios=[4, 1.3, 1.3]))
for j, m in enumerate(cands):
    f = src[round(m["t"], 3)]
    X, half, z = MF.load(f, m["t"])
    Xn = MF.notch(X)
    tt = np.arange(X.shape[-1]) / MF.FS - half - m["off_ms"] / 1000.0          # centred on the largest contact's peak
    w = (tt >= -0.15) & (tt <= 0.15)
    V = sosfiltfilt(hp, Xn[[c - 1 for c in MF.EVEN]], axis=-1)
    V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
    C = MF.csd(V[:, w]); tm = tt[w] * 1000
    KV = 3.5 / np.abs(V[:, w]).max()
    cl = float(np.percentile(np.abs(np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "m_events_v9.npz"))["C0"]), 99.5))   # the DS's CSD scale, as the figure
    ax = axs[0, j]
    ax.imshow(C, aspect="auto", cmap="RdBu_r", vmin=-cl, vmax=cl, extent=[tm[0], tm[-1], 65, 1], interpolation="bilinear")
    for c in range(4, 65, 4):
        ax.plot(tm, c - KV * V[c // 2 - 1, w], c="k", lw=1.0)
    ax.set_ylim(65.5, 0.5); ax.set_xlim(-150, 150); ax.set_xticks([-100, 0, 100]); ax.set_yticks([])
    ax.set_title("%.2f s  (%s)\npk %.1f mV @%d, FWHM %.0f ms\nprom %.1f, HF %.1f dB" % (m["t"], m["origin"][:3], m["peak_uv"] / 1000,
                 m["csc"], m["fwhm_ms"], m["prom_ratio"], m["hf_db_med"]), fontsize=8.5)
    sw = (tt >= -0.5) & (tt <= 0.5)
    for r_, c in ((1, 9), (2, 41)):
        key = (f, c)
        if key not in base_cache:
            base_cache[key] = MF.baseline(z, c)
        s_, f_, ts_ = MF.xf_spec(Xn[c - 1][sw])
        S_ = s_ - base_cache[key][:, None]
        a2 = axs[r_, j]
        a2.pcolormesh((ts_ - 0.5) * 1000, f_, S_, cmap="jet", vmin=-6, vmax=29, shading="gouraud")
        y = sosfiltfilt(hp, Xn[c - 1])[sw]; y = y - np.median(y)
        tT = tt[sw] * 1000
        a2.plot(tT, 300 + 255 * np.clip(y / 3000.0, -1.1, 1.1), c="w", lw=0.6)
        a2.set_ylim(0, 600); a2.set_xlim(-400, 400); a2.set_yticks([]); a2.set_xticks([])
        if j == 0:
            a2.set_ylabel("CSC %d" % c)
fig.tight_layout()
fig.savefig(OUT, dpi=60)
print("wrote", OUT, [round(m["t"], 2) for m in cands])
