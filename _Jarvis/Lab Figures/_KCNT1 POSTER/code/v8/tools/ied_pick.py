"""Which curated m1609 IED (the Lock set's lock_spike windows) is sharpest, drawn the way the methods figure draws them."""
import os, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import style as S
VACC = os.environ.get("KCNT1_VACC", os.path.normpath(os.path.join(HERE, "..", "..", "vacc")))
sys.path.insert(0, VACC)
import methods_fig_v4 as MF  # noqa: E402

TS = [882.748327, 863.441032, 905.339052, 754.128655, 1320.060309, 692.167497]
npz = os.path.join(VACC, "ied_m1609_s1.npz")
Z = np.load(os.path.join(HERE, "data", "m_events.npz"))
clim = np.percentile(np.abs(Z["C0"]), 99.5); gain = np.percentile(np.abs(Z["V0"]), 99.5)
fig = S.figure(2.3 * len(TS), 4.6)
for k, tv in enumerate(TS):
    X, half, z = MF.load(npz, tv)
    Xn = MF.notch(X)
    tt = np.arange(X.shape[-1]) / MF.FS - half
    w = (tt >= -MF.HALF) & (tt <= MF.HALF)
    V = Xn[[c - 1 for c in MF.EVEN]]
    V = sosfiltfilt(butter(3, 1.0, btype="high", fs=MF.FS, output="sos"), V, axis=-1)
    V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
    V = V[:, w]; C = MF.csd(V); tm = tt[w] * 1000
    ax = S.ax_at(fig, 0.15 + 2.3 * k, 0.4, 2.0, 4.0)
    ax.imshow(C, aspect="auto", cmap=S.CSD_CMAP, vmin=-clim, vmax=clim, extent=[tm[0], tm[-1], 65, 1])
    for r in range(32):
        ax.plot(tm, 2 * (r + 1) - 2.8 * V[r] / gain, c=S.INK, lw=0.5)
    ax.set_ylim(65.5, 0.5); ax.set_xlim(-150, 150); S.bare(ax)
    c = np.argmax(np.abs(V).max(1)); s = V[c]; j = np.argmax(np.abs(s)); pk = s[j]
    half_ = abs(pk) / 2; L = j
    while L > 0 and np.sign(pk) * s[L] > half_: L -= 1
    R = j
    while R < len(s) - 1 and np.sign(pk) * s[R] > half_: R += 1
    S.text_at(fig, 0.15 + 2.3 * k, 0.02, "%.2f s\npeak %.1f mV, FWHM %.0f ms" % (tv, pk / 1000, (R - L) / MF.FS * 1000), fontsize=11)
S.save(fig, sys.argv[1])
