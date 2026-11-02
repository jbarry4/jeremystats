"""FIG 2 — the analytic signal, and the scatter the modulation index summarises.

hilbert(x) builds the analytic signal z(t) = x(t) + i*x_hat(t). Its modulus is
the instantaneous amplitude and its argument is the instantaneous phase; that
is the entire content of "abs(hilbert)" and "angle(hilbert)".
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert
import cfc_core as c
from style import *

SR = 1000.0
t, lfp = c.pac_lfp(dur=120, srate=SR, fp=8, fa=80, depth=0.95,
                   slow_amp=1.0, fast_amp=0.45, noise=0.45, seed=3)
slow, _ = c.eegfilt(lfp, SR, 7.75, 8.25)
fast, _ = c.eegfilt(lfp, SR, 75, 85)
z = hilbert(slow)
phase, amp = np.angle(z), np.abs(hilbert(fast))

fig = plt.figure(figsize=(7.4, 3.5))
gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.55], wspace=0.35)

# (a) analytic signal in the complex plane
a0 = fig.add_subplot(gs[0])
w = (t >= 10) & (t < 10.30)
a0.plot(np.real(z[w]), np.imag(z[w]), color=C[0], lw=1.4)
i = np.argmax(t >= 10.18)
a0.plot([0, np.real(z[i])], [0, np.imag(z[i])], color=C[1], lw=2)
a0.plot([np.real(z[i])], [np.imag(z[i])], "o", color=C[1], ms=7)
a0.text(0.30, 0.06, "|z| = A(t)\nangle z = phi(t)", transform=a0.transAxes,
        color=C[1], fontsize=8, va="bottom")
a0.axhline(0, color=GRID, lw=0.8); a0.axvline(0, color=GRID, lw=0.8)
a0.set_aspect("equal"); a0.set_xlabel("real  =  filtered signal")
a0.set_ylabel("imag  =  Hilbert transform")
a0.set_title("z(t) = hilbert(slow band)", pad=14)
tag(a0, "a")

# (b) amplitude vs phase
a1 = fig.add_subplot(gs[1])
sub = slice(None, None, 7)
a1.plot(np.degrees(phase[sub]), amp[sub], ".", ms=1.1, color="#c7d9f2",
        rasterized=True)
ma = c.mean_amp_fast(phase, amp)
ctr = np.degrees(c.POSITION + np.pi / c.NBIN)
a1.plot(ctr, ma, "o-", color=C[0], ms=5, lw=2, label="mean A in each of 18 bins")
a1.axhline(amp.mean(), color=C[1], lw=1.6, ls="--", label="grand mean (the flat / no-coupling case)")
a1.set_xlim(-180, 180); a1.set_xticks([-180, -90, 0, 90, 180])
a1.set_xlabel("phase of the 8 Hz band (deg)")
a1.set_ylabel("amplitude of the 75–85 Hz band")
a1.set_title("every sample, and the 18-bin means", pad=14)
a1.legend(loc="lower right", ncol=1)
tag(a1, "b")
note(fig, "MI reads only the blue curve — how far the 18 bin means depart from the dashed line. It is blind to\n"
         "the scatter around them, to the units of A, and to which phase the peak sits at.")
plt.savefig("figures/fig02_two_series_against_each_other.png", bbox_inches="tight", dpi=170)
print("fig02", c.mi_fast(phase, amp))
