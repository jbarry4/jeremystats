"""FIG 5 — the comodulogram: 1887 modulation indices in one picture.

Grid is the lab's own (step04_newFCSE.m): Phase 1:0.5:26 with BW 0.5 (51
columns), Amp 20:5:200 with BW 10 (37 rows). Axis ticks are bin CENTRES —
MATLAB plots PhaseFreqVector + BW/2, AmpFreqVector + BW/2.
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert
import cfc_core as c, make_comodulograms as M
from style import *

pac, noi = M.pac(), M.noise_only()
px = c.bin_centers(c.PHASE_VEC_LAB, c.PHASE_BW_LAB)
ay = c.bin_centers(c.AMP_VEC_LAB, c.AMP_BW_LAB)
vmax = pac.max()

fig = plt.figure(figsize=(10.2, 3.5))
gs = fig.add_gridspec(1, 4, width_ratios=[1.25, 1.25, 0.05, 1.0], wspace=0.62)
levels = np.linspace(0, vmax, 31)

axes = []
for k, (m, ttl) in enumerate([(pac, "simulated 8 Hz → 80 Hz coupling"),
                              (noi, "pink noise, no coupling (same scale)")]):
    ax = fig.add_subplot(gs[k])
    im = ax.contourf(px, ay, m.T, levels=levels, cmap=SEQ, extend="neither")
    ax.set_xlabel("phase frequency (Hz)")
    if k == 0:
        ax.set_ylabel("amplitude frequency (Hz)")
    ax.set_title(ttl, fontsize=9)
    tag(ax, "ab"[k])
    axes.append(ax)

cax = fig.add_subplot(gs[2])
cb = fig.colorbar(im, cax=cax)
cb.set_ticks(np.linspace(0, vmax, 5))
cb.ax.set_yticklabels([f"{v:.3f}" for v in np.linspace(0, vmax, 5)], fontsize=7)
cax.set_title("MI", fontsize=8, color=INK2, loc="left", pad=6)

j, i = np.unravel_index(np.argmax(pac), pac.shape)
axm = axes[0]
axm.plot(px[j], ay[i], "s", mfc="none", mec=C[1], mew=1.8, ms=9)
axm.annotate(f"peak cell\nphase {c.PHASE_VEC_LAB[j]:.1f}–{c.PHASE_VEC_LAB[j]+0.5:.1f} Hz\n"
             f"amp {c.AMP_VEC_LAB[i]:.0f}–{c.AMP_VEC_LAB[i]+10:.0f} Hz\nMI = {pac[j,i]:.4f}",
             (px[j], ay[i]), xytext=(16, 12), textcoords="offset points",
             fontsize=7.4, color=C[1], fontweight="600")

# (c) the one cell, unpacked
SR = 1000.0
_, lfp = c.pac_lfp(dur=120, srate=SR, fp=8, fa=80, depth=0.9,
                   slow_amp=1.0, fast_amp=0.45, noise=0.6, seed=3)
ph = np.angle(hilbert(c.eegfilt(lfp, SR, c.PHASE_VEC_LAB[j], c.PHASE_VEC_LAB[j] + 0.5)[0]))
am = np.abs(hilbert(c.eegfilt(lfp, SR, c.AMP_VEC_LAB[i], c.AMP_VEC_LAB[i] + 10)[0]))
mi, ma = c.mod_index(ph, am)
P = ma / ma.sum()
a2 = fig.add_subplot(gs[3])
x = np.arange(10, 720, 20)
a2.bar(x, np.r_[P, P], width=17, color=C[0], edgecolor=SURFACE, linewidth=0.5)
a2.axhline(1 / 18, color=C[1], lw=1.4, ls="--")
a2.set_xlim(0, 720); a2.set_xticks([0, 360, 720])
a2.set_xlabel("phase (deg)"); a2.set_ylabel("P(j)")
a2.set_title("that one pixel, unpacked", fontsize=9)
tag(a2, "c")
note(fig, "Every pixel in (a) and (b) is one 18-bin histogram like (c), collapsed to a single number. The whole map is\n"
          "2 filter banks (51 + 37 bandpasses), 88 Hilbert transforms, and 1887 modulation indices.", y=-0.02)
plt.savefig("figures/fig05_comodulogram.png", bbox_inches="tight", dpi=170)
print("fig05 done", pac.max(), noi.max())
