"""FIG 1 — what the pipeline does to one channel of raw LFP.

Two bandpass filters, two Hilbert transforms, and you are left with exactly
two numbers per sample: a slow-band phase and a fast-band amplitude. Every
comodulogram in this repo is built out of just those two series.
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert
import cfc_core as c
from style import *

SR = 1000.0
t, lfp = c.pac_lfp(dur=60, srate=SR, fp=8, fa=80, depth=0.95,
                   slow_amp=1.0, fast_amp=0.45, noise=0.45, seed=3)

slow, _ = c.eegfilt(lfp, SR, 7.75, 8.25)      # a lab phase band: 8 : 8+0.5
fast, _ = c.eegfilt(lfp, SR, 75, 85)          # a lab amp   band: 75: 75+10
phase = np.angle(hilbert(slow))
amp = np.abs(hilbert(fast))

w = (t >= 10) & (t < 10.75)
fig, ax = plt.subplots(5, 1, figsize=(7.4, 7.0), sharex=True,
                       gridspec_kw=dict(hspace=0.55))

ax[0].plot(t[w], lfp[w], color=INK, lw=1.0)
ax[0].set_title("Raw LFP  (one .ncs channel, 60 Hz notched, downsampled x10)")
ax[0].set_ylabel("µV")

ax[1].plot(t[w], slow[w], color=C[0])
ax[1].set_title("eegfilt(lfp, srate, 8, 8.5)   —  the phase band")
ax[1].set_ylabel("µV")

ax[2].plot(t[w], phase[w], color=C[0], lw=1.2)
ax[2].set_title("angle(hilbert(...))   —  phase, radians, wrapped to [-pi, pi)")
ax[2].set_yticks([-np.pi, 0, np.pi]); ax[2].set_yticklabels(["-π", "0", "π"])
ax[2].set_ylabel("phase")

ax[3].plot(t[w], fast[w], color=MUTED, lw=0.8)
ax[3].set_title("eegfilt(lfp, srate, 75, 85)   —  the amplitude band")
ax[3].set_ylabel("µV")

ax[4].plot(t[w], fast[w], color="#d9d8d2", lw=0.8)
ax[4].plot(t[w], amp[w], color=C[1], lw=1.8, label="abs(hilbert(...))")
ax[4].plot(t[w], -amp[w], color=C[1], lw=1.8)
ax[4].set_title("abs(hilbert(...))   —  the amplitude envelope")
ax[4].set_ylabel("µV"); ax[4].set_xlabel("time (s)")
ax[4].legend(loc="upper right")

# mark slow-band troughs on every panel so the alignment is visible
tr = t[w][np.r_[False, (np.diff(np.sign(np.diff(slow[w]))) > 0), False]]
for a in ax:
    for x in tr:
        a.axvline(x, color="#cfcec8", lw=0.7, zorder=0)

for a, s in zip(ax, "abcde"):
    tag(a, s)
note(fig, "Grey verticals mark troughs of the 8 Hz band. The envelope in (e) rises and falls with them:\n"
            "that is phase–amplitude coupling, before any statistic has been computed.")
plt.savefig("figures/fig01_from_lfp_to_phase_and_amplitude.png",
            bbox_inches="tight", dpi=170)
print("fig01 done")
