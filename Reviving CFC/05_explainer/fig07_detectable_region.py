"""FIG 7 — the comodulogram can only see part of itself.

An amplitude band of width B carries the modulation sidebands fa ± fp only
if B >= 2*fp. Combined with Fig 6 (B ~ 0.30*fa for this filter), the largest
phase frequency detectable at amplitude frequency fa is about 0.15*fa.

Below that line MI reports the coupling. Above it MI reports zero — for
signals with EXACTLY the same true coupling. The empty upper-left of a
comodulogram is a property of the analysis, not of the brain.
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert, firls, freqz
import cfc_core as c
from style import *

SR = 1000.0
FP = np.array([2, 4, 6, 8, 10, 12, 14, 17, 20, 23, 26], float)
FA = np.array([30, 45, 60, 80, 100, 125, 150, 175, 200], float)


def build():
    out = np.zeros((len(FP), len(FA)))
    for a, fp in enumerate(FP):
        for b, fa in enumerate(FA):
            _, lfp = c.pac_lfp(dur=80, srate=SR, fp=fp, fa=fa, depth=1.0,
                               slow_amp=1.0, fast_amp=0.45, noise=0.5, seed=7)
            ph = np.angle(hilbert(c.eegfilt(lfp, SR, fp - 0.25, fp + 0.25)[0]))
            am = np.abs(hilbert(c.eegfilt(lfp, SR, fa - 5, fa + 5)[0]))
            out[a, b] = c.mi_fast(ph, am)
    return (out,)


MI = c.cached("detectable_region", build)[0]


def realised_bw(lo, hi, sr=SR):
    order = c.eegfilt_order(sr, lo)
    order += order % 2
    f, m = c.eegfilt_response(sr, lo, hi)
    b = firls(order + 1, list(f), m, fs=sr)
    w, h = freqz(b, worN=40000, fs=sr)
    H = np.abs(h) ** 2; idx = np.where(H >= H.max() / 2)[0]
    return w[idx[-1]] - w[idx[0]]


fa_line = np.linspace(25, 205, 60)
fp_line = np.array([realised_bw(f - 5, f + 5) / 2 for f in fa_line])

fig, (a0, a1) = plt.subplots(1, 2, figsize=(9.4, 3.4),
                             gridspec_kw=dict(width_ratios=[1.15, 1]))

pc = a0.pcolormesh(FA, FP, MI, cmap=SEQ, shading="nearest", vmin=0)
cb = fig.colorbar(pc, ax=a0, pad=0.02); cb.ax.tick_params(labelsize=7)
cb.set_label("MI recovered", fontsize=8)
a0.plot(fa_line, fp_line, color=C[1], lw=2.2)
a0.text(0.03, 0.96, "detection limit\nfp ≈ 0.15 · fa", transform=a0.transAxes, color=C[1],
        fontsize=8.5, fontweight="600", va="top", ha="left")
a0.set_xlabel("amplitude frequency (Hz)")
a0.set_ylabel("phase frequency (Hz)")
a0.set_title("identical true coupling everywhere (depth = 1)")
tag(a0, "a")

for k, fp in enumerate([4, 8, 12, 20]):
    a = int(np.argmin(np.abs(FP - fp)))
    a1.plot(FA, MI[a], "-o", ms=4, color=C[k], label=f"phase {fp:.0f} Hz")
a1.set_xlabel("amplitude frequency (Hz)"); a1.set_ylabel("MI recovered")
a1.set_title("same coupling, read out at different amplitude frequencies")
a1.legend(loc="lower right"); a1.grid(axis="y")
tag(a1, "b")
note(fig, "Nothing about the simulated brain changes across these panels — only which filter pair reads it. A real\n"
          "theta→low-gamma effect at 8 Hz / 30 Hz is almost invisible on this grid, while the identical effect at\n"
          "8 Hz / 150 Hz reads a large MI. Compare blobs across a comodulogram only at similar amplitude frequency.", y=-0.02)
plt.tight_layout()
plt.savefig("figures/fig07_detectable_region.png", bbox_inches="tight", dpi=170)
print("fig07 done")
