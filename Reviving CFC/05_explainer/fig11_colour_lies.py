"""FIG 11 — the picture is not the data: colour scale and colormap.

contourf(..., 30, 'lines', 'none') with no CLim autoscales every figure to
its own range. Saved that way, one .fig per channel, two comodulograms are
never on the same scale — the eye compares patterns that the numbers do not
support. A rainbow map makes it worse by inventing edges where the data is
smooth.

All three panels below are the SAME pink-noise recording with no coupling
in it whatsoever.
"""
import numpy as np, matplotlib.pyplot as plt
import cfc_core as c, make_comodulograms as M
from style import *

noi, pac = M.noise_only(), M.pac()
px = c.bin_centers(c.PHASE_VEC_LAB, c.PHASE_BW_LAB)
ay = c.bin_centers(c.AMP_VEC_LAB, c.AMP_BW_LAB)

fig, axs = plt.subplots(1, 3, figsize=(10.0, 3.3))
panels = [
    ("jet, autoscaled\n(what the saved .fig looks like)", "jet", None),
    ("sequential, autoscaled", SEQ, None),
    ("sequential, scaled to the real-coupling map", SEQ, pac.max()),
]
for k, (ttl, cmap, vmax) in enumerate(panels):
    ax = axs[k]
    top = noi.max() if vmax is None else vmax
    im = ax.contourf(px, ay, noi.T, levels=np.linspace(0, top, 31), cmap=cmap)
    cb = fig.colorbar(im, ax=ax, pad=0.02, ticks=np.linspace(0, top, 4))
    cb.ax.set_yticklabels([f"{v:.4f}" for v in np.linspace(0, top, 4)], fontsize=6.5)
    ax.set_xlabel("phase frequency (Hz)")
    if k == 0:
        ax.set_ylabel("amplitude frequency (Hz)")
    ax.set_title(ttl, fontsize=8.8)
    tag(ax, "abc"[k])
note(fig, "Same numbers in all three. The left panel invites a story about low-frequency coupling; the right panel\n"
          "shows the truth, which is that the largest MI anywhere on this map is %.4f. Fix CLim across every\n"
          "figure you intend to compare, and use a perceptually uniform sequential map." % noi.max(), y=-0.03)
plt.tight_layout()
plt.savefig("figures/fig11_colour_lies.png", bbox_inches="tight", dpi=170)
print("fig11 done", noi.max(), pac.max())
