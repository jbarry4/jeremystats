"""A quick look: every recording's mean DS down the whole shank."""
import os
import pickle

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
recs = pickle.load(open(os.path.join(HERE, "deep_v6.pkl"), "rb"))
full = pickle.load(open(os.path.join(HERE, "deep_full_v6.pkl"), "rb"))
fig, axs = plt.subplots(3, 6, figsize=(20, 13))
for ax, d in zip(axs.ravel(), recs):
    F = full[d["gid"]]
    m = F["csd_mean"]
    na = np.array(F["nums_all"])
    v = np.percentile(np.abs(m), 99.5)
    ax.imshow(m, aspect="auto", cmap="RdBu", vmin=-v, vmax=v, extent=[-50, 50, na[-1] + 0.5, na[0] - 0.5], interpolation="bilinear")
    lf = F["lfp_mean"]
    nl = np.array(F["nums_lfp"])
    sc = 3.0 / max(np.abs(lf).max(), 1e-9)
    for i in range(0, lf.shape[0], 2):
        ax.plot(F["tt"], nl[i] - lf[i] * sc, color="k", lw=0.4)
    ax.axhline(d["ns"][0] - 0.5, color="g", lw=0.8)
    ax.axhline(d["ns"][-1] + 0.5, color="g", lw=0.8)
    if d["hump_cut"] is not None:
        ax.axhline(d["ns"][d["hump_cut"]] - 0.5, color="m", lw=0.6, ls=":")
    ax.set_title("%s %s KO %.1f n %d  gap %s  bad %s" % (d["lab"], d["g"], d["ko"], d["n"], d.get("blade_gap_mean"), F["bad"]), fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "deep_look.png"), dpi=70)
