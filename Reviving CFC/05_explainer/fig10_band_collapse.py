"""FIG 10 — how the comodulogram becomes four numbers for SPSS.

Notes_ComodAnalysis.m (and CFCReader.R, which reproduces it) transposes the
comodulogram so rows are amplitude frequencies and columns are phase
frequencies, then averages COLUMN RANGES:

    Delta     = cols 1:3        DelTheta = cols 3:9
    Theta     = cols 7:23       Beta     = cols 23:40

With PhaseFreqVector = 1:0.5:26 and BW 0.5, column k is centred at
1.25 + 0.5*(k-1) Hz. So those slices are the phase-frequency ranges printed
below. Two things worth knowing before you read the SPSS output: the bands
overlap at their shared boundary columns, and columns 41–51 (21.25–26.25 Hz)
are never used by any band.
"""
import numpy as np, matplotlib.pyplot as plt
import cfc_core as c, make_comodulograms as M
from style import *

pac = M.pac()
px = c.bin_centers(c.PHASE_VEC_LAB, c.PHASE_BW_LAB)
ay = c.bin_centers(c.AMP_VEC_LAB, c.AMP_BW_LAB)

BANDS = [("Delta", 1, 3), ("Del-Theta", 3, 9), ("Theta", 7, 23), ("Beta", 23, 40)]

fig, (a0, a1) = plt.subplots(1, 2, figsize=(9.6, 3.6),
                             gridspec_kw=dict(width_ratios=[1.2, 1]))

im = a0.contourf(px, ay, pac.T, levels=np.linspace(0, pac.max(), 31), cmap=SEQ)
cb = fig.colorbar(im, ax=a0, pad=0.02, ticks=np.linspace(0, pac.max(), 5))
cb.ax.set_yticklabels([f"{v:.3f}" for v in np.linspace(0, pac.max(), 5)], fontsize=7)
cb.set_label("MI", fontsize=8)
for k, (nm, c1, c2) in enumerate(BANDS):
    lo, hi = px[c1 - 1], px[c2 - 1]
    a0.plot([lo, hi], [206 + k * 9, 206 + k * 9], color=C[k], lw=4, solid_capstyle="butt",
            clip_on=False)
    a0.text(hi + 0.4, 206 + k * 9, f" {nm} {c1}:{c2} = {lo:.2f}–{hi:.2f} Hz",
            color=C[k], fontsize=7.4, va="center", fontweight="600")
a0.axvspan(px[40], px[-1], color="#8a8880", alpha=0.13, zorder=5, lw=0)
a0.text(px[45], 40, "cols 41–51\nnever used", color="#5c5a54", fontsize=7.2, ha="center", zorder=6)
a0.set_xlim(px[0], px[-1]); a0.set_ylim(ay[0], ay[-1])
a0.set_xlabel("phase frequency (Hz)"); a0.set_ylabel("amplitude frequency (Hz)")
a0.set_title("the four column slices, on the map", pad=48, fontsize=9.5)
tag(a0, "a")

for k, (nm, c1, c2) in enumerate(BANDS):
    a1.plot(pac[c1 - 1:c2, :].mean(axis=0), ay, color=C[k], lw=2, label=nm)
a1.set_xlabel("mean MI across the band's columns")
a1.set_ylabel("amplitude frequency (Hz)")
a1.set_title("what goes into CFCMerged.csv", fontsize=9.5)
a1.legend(loc="upper right"); a1.grid(axis="x")
tag(a1, "b")
note(fig, "Each curve is one column of CFCMerged.csv, one value per amplitude row per channel. Averaging raw MI\n"
          "over a band dilutes a narrow peak: the Theta slice spans 17 columns, so a blob two columns wide is\n"
          "divided by ~8 before it reaches the statistics. Peak MI within the band is often the better summary.", y=-0.02)
plt.tight_layout()
plt.savefig("figures/fig10_band_collapse.png", bbox_inches="tight", dpi=170)
for nm, c1, c2 in BANDS:
    print(f"{nm:10s} cols {c1}:{c2}  = {px[c1-1]:.2f}-{px[c2-1]:.2f} Hz")
