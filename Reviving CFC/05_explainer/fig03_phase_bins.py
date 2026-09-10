"""FIG 3 — the amplitude distribution over phase, P(j), at three coupling
strengths. This is the object MI is computed from; everything else is
bookkeeping. Plotted over two cycles, as ModIndex_v1.m does.
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert
import cfc_core as c
from style import *

SR = 1000.0
depths = [0.0, 0.35, 1.0]
labels = ["depth = 0  (no coupling)", "depth = 0.35  (weak)", "depth = 1.0  (strong)"]
fig, axs = plt.subplots(1, 3, figsize=(8.6, 2.9), sharey=True)
for ax, d, lab, col in zip(axs, depths, labels, [MUTED, C[0], C[0]]):
    t, lfp = c.pac_lfp(dur=120, srate=SR, fp=8, fa=80, depth=d,
                       slow_amp=1, fast_amp=0.45, noise=0.45, seed=3)
    ph = np.angle(hilbert(c.eegfilt(lfp, SR, 7.75, 8.25)[0]))
    am = np.abs(hilbert(c.eegfilt(lfp, SR, 75, 85)[0]))
    mi, ma = c.mod_index(ph, am)
    P = ma / ma.sum()
    x = np.arange(10, 720, 20)
    ax.bar(x, np.r_[P, P], width=17, color=col, edgecolor=SURFACE, linewidth=0.6)
    ax.axhline(1 / 18, color=C[1], lw=1.5, ls="--")
    ax.set_xlim(0, 720); ax.set_xticks([0, 360, 720])
    ax.set_xlabel("phase (deg)")
    ax.set_title(lab)
    ax.text(0.97, 0.94, f"MI = {mi:.4f}", transform=ax.transAxes, ha="right",
            va="top", fontsize=10, color=INK, fontweight="600")
axs[0].set_ylabel("P(j)  =  ⟨A⟩ⱼ / Σ⟨A⟩")
axs[0].text(20, 1/18 + 0.0018, "uniform, 1/18", color=C[1], fontsize=7.5)
note(fig, "P is the amplitude distribution turned into a probability mass function: 18 numbers that sum to 1.\n"
             "MI asks one question about it — how far from flat? — and nothing else.", y=-0.07)
plt.subplots_adjust(wspace=0.18)
plt.savefig("figures/fig03_phase_bins.png", bbox_inches="tight", dpi=170)
print("fig03 done")
