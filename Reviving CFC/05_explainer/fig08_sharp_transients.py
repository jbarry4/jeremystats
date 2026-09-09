"""FIG 8 — a spike train alone produces a comodulogram.

An interictal discharge is broadband by construction: a sharp event puts
energy into every amplitude band at the same instant. If those events are
not uniformly distributed over the phase of a slow band — and after a big
transient the slow band has a large deflection of its own, so they never
are — MI is non-zero with no oscillatory coupling anywhere in the signal.

The signal here is pink noise plus 1.5 sharp transients per second and
nothing else. There is no phase-amplitude coupling in it at all.
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert
import cfc_core as c, make_comodulograms as M
from style import *

SR, DUR = 1000.0, 120.0
t, lfp, ev = c.ied_lfp(dur=DUR, srate=SR, rate=1.5, seed=1, amp=6.0)
ied, pac, noi = M.ied(), M.pac(), M.noise_only()
px = c.bin_centers(c.PHASE_VEC_LAB, c.PHASE_BW_LAB)
ay = c.bin_centers(c.AMP_VEC_LAB, c.AMP_BW_LAB)

fig = plt.figure(figsize=(10.0, 3.5))
gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 1.1, 1.1], wspace=0.42)

a0 = fig.add_subplot(gs[0])
w = (t > 20) & (t < 24)
a0.plot(t[w], lfp[w], color=INK, lw=0.8)
a0.set_xlabel("time (s)"); a0.set_ylabel("µV")
a0.set_title("input: noise + sharp transients", fontsize=9)
tag(a0, "a")

for k, (m, ttl) in enumerate([(ied, "its comodulogram"), (pac, "real coupling, for scale")]):
    ax = fig.add_subplot(gs[k + 1])
    lv = np.linspace(0, m.max(), 31)
    im = ax.contourf(px, ay, m.T, levels=lv, cmap=SEQ)
    cb = fig.colorbar(im, ax=ax, pad=0.02); cb.ax.tick_params(labelsize=7)
    cb.set_ticks(np.linspace(0, m.max(), 4))
    cb.ax.set_yticklabels([f"{v:.3f}" for v in np.linspace(0, m.max(), 4)], fontsize=7)
    ax.set_xlabel("phase frequency (Hz)")
    if k == 0:
        ax.set_ylabel("amplitude frequency (Hz)")
    ax.set_title(f"{ttl}  (max {m.max():.4f})", fontsize=9)
    tag(ax, "bc"[k])

note(fig, "The spike-train map peaks at MI = %.4f, about %.0f times the pink-noise floor (%.4f).\n"
          "Its signature differs from real coupling: smeared over the whole amplitude axis, hugging low\n"
          "phase frequencies, no closed blob. On IED-heavy recordings, mask events before running CFC —\n"
          "otherwise a group difference in IED rate reads out as a group difference in coupling."
          % (ied.max(), ied.max()/noi.max(), noi.max()), y=-0.03)

plt.savefig("figures/fig08_sharp_transients.png", bbox_inches="tight", dpi=170)
print("fig08 done", ied.max(), noi.max())
