"""FIG 6 — the bandwidth you asked for is not the bandwidth you got.

eegfilt.m picks its own filter length:  filtorder = 3 * fix(srate/locutoff),
i.e. always about three cycles of the lower cutoff. A three-cycle FIR has a
fractional bandwidth of roughly 1/3 no matter what passband you requested,
so the realised filter is a CONSTANT-Q filter with Q ~ 3.3. The nominal
0.5 Hz / 10 Hz bandwidths in the drivers only bind at the very bottom of
each axis.
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import firls, freqz
import cfc_core as c
from style import *

SR = 3255.0   # Neuralynx 32556 Hz downsampled x10, as read_csc(...,10) gives


def realised(sr, lo, hi):
    order = c.eegfilt_order(sr, lo)
    if order % 2:
        order += 1
    f, m = c.eegfilt_response(sr, lo, hi)
    b = firls(order + 1, list(f), m, fs=sr)
    w, h = freqz(b, worN=60000, fs=sr)
    H = np.abs(h) ** 2                      # filtfilt applies the filter twice
    pk = H.max(); idx = np.where(H >= pk / 2)[0]
    return w, H / pk, w[idx[0]], w[idx[-1]], order + 1


fig, (a0, a1) = plt.subplots(1, 2, figsize=(9.2, 3.3))

# (a) three amplitude bands, all nominally 10 Hz wide
for k, lo in enumerate([20, 80, 200]):
    w, H, l, h, n = realised(SR, lo, lo + 10)
    a0.plot(w, H, color=C[k], lw=1.8,
            label=f"asked for {lo}–{lo+10} Hz  ({n} taps)  →  got {l:.0f}–{h:.0f} Hz")
    a0.axvspan(lo, lo + 10, color=C[k], alpha=0.10, lw=0)
a0.axhline(0.5, color=MUTED, lw=1, ls=":")
a0.text(300, 0.52, "half power", fontsize=7.5, color=MUTED)
a0.set_xlim(0, 320); a0.set_ylim(0, 1.05)
a0.set_xlabel("frequency (Hz)"); a0.set_ylabel("power gain (filtfilt)")
a0.set_title("amplitude-band filters, srate = 3255 Hz")
a0.legend(loc="upper center", fontsize=7.2)
tag(a0, "a")

# (b) realised bandwidth across both axes
los_a = np.arange(20, 301, 5.0)
bw_a = [realised(SR, lo, lo + 10)[3] - realised(SR, lo, lo + 10)[2] for lo in los_a]
los_p = np.arange(1, 26.01, 0.5)
bw_p = [realised(SR, lo, lo + 0.5)[3] - realised(SR, lo, lo + 0.5)[2] for lo in los_p]

a1.plot(los_a, bw_a, color=C[0], lw=2, label="amplitude bands (nominal 10 Hz)")
a1.plot(los_p, bw_p, color=C[1], lw=2, label="phase bands (nominal 0.5 Hz)")
a1.plot(los_a, 0.30 * los_a, color=MUTED, lw=1.2, ls="--", label="0.30 × lower cutoff  (Q ≈ 3.3)")
a1.axhline(10, color=C[0], lw=1, ls=":")
a1.axhline(0.5, color=C[1], lw=1, ls=":")
a1.set_xscale("log"); a1.set_yscale("log")
a1.set_xlabel("lower cutoff of the band (Hz)")
a1.set_ylabel("realised −3 dB bandwidth (Hz)")
a1.set_title("nominal bandwidth (dotted) vs what you get (solid)")
a1.legend(loc="upper left", fontsize=7.2)
a1.grid(which="both")
tag(a1, "b")
note(fig, "Consequence for the grid: a phase column labelled 26 Hz actually spans about 23–31 Hz, so the 0.5 Hz\n"
          "column spacing is ~15× finer than the resolution behind it — neighbouring columns are near-copies.\n"
          "On the amplitude axis the 200 Hz row spans about 178–238 Hz. Blobs are wide because the filters are.", y=-0.02)
plt.tight_layout()
plt.savefig("figures/fig06_what_the_filters_really_do.png", bbox_inches="tight", dpi=170)
print("fig06 done")
