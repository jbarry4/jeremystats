"""Poster: four small real-data panels under the Isolating Biomarkers steps (Detect, Curate, Align, Classify).
One IED+ mouse (m13) for the first three; every Halo event of all 16 mice for the class map.
Written to ../poster/img/strip_<n>.png at 300 dpi, each 3.3 x 2.0 in (shown at actual size on the poster)."""
import os
import sys
import warnings

import numpy as np
from scipy.ndimage import gaussian_filter1d

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import menu_data as D  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "poster", "img")
W, H = 3.3, 2.0
LAB = "m13"
GOLD = "#c99a00"
z = np.load(os.path.join(HERE, "reads", LAB + ".npz"), allow_pickle=True)
fs = float(z["fs"])
kind = z["kind"]
ds = kind == "DS"
t = (np.arange(z["band"].shape[2]) - z["band"].shape[2] // 2) / fs * 1000.0
bad = [int(b) - 1 for b in z["bad"]]


def fill_bad(v):
    v = v.copy()
    good = [i for i in range(v.shape[0]) if i not in bad]
    for i in bad:
        v[i] = np.array([np.interp(i, good, v[good, k]) for k in range(v.shape[1])])
    return v


def fig_ax():
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.03, 0.05, 0.94, 0.9])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    return fig, ax


def save(fig, n):
    fig.savefig(os.path.join(OUT, "strip_%d.png" % n), dpi=300, transparent=False)
    plt.close(fig)


# 1  Detect: one event on every fourth contact, broadband, +-100 ms
mean_ds = fill_bad(z["band"][ds].mean(0))
deep = int(np.argmin(mean_ds[:, np.argmin(np.abs(t))]))
amps = z["amp"][ds]
pick = np.where(ds)[0][int(np.argsort(np.abs(amps - np.quantile(amps, 0.85)))[0])]
ev = fill_bad(z["band"][pick])
fig, ax = fig_ax()
chans = list(range(2, 64, 4))
step = 520.0
for j, c in enumerate(chans):
    ax.plot(t, ev[c] - j * step, color=F.INK, lw=0.7)
ax.axvspan(-12, 12, color=GOLD, alpha=0.18, lw=0)
ax.plot([0], [step * 1.2], marker="v", ms=9, color=GOLD, clip_on=False)
ax.plot([55, 95], [-(len(chans) - 0.2) * step] * 2, color=F.INK, lw=1.4)
ax.text(75, -(len(chans) + 0.5) * step, "40 ms", ha="center", va="top", fontsize=10, color=F.SOFT)
ax.set_xlim(-100, 100)
ax.set_ylim(-(len(chans) + 1.6) * step, step * 1.8)
save(fig, 1)

# 2  Curate: the kept DS of this mouse, overlaid at the deepest contact
fig, ax = fig_ax()
sig = z["band"][ds][:, deep, :]
rng = np.random.RandomState(1)
for i in rng.choice(sig.shape[0], min(120, sig.shape[0]), replace=False):
    ax.plot(t, sig[i], color=F.C_DS, lw=0.35, alpha=0.18)
ax.plot(t, sig.mean(0), color=F.C_DS, lw=2.2)
ax.text(-95, sig.max() * 0.55, "%d kept" % ds.sum(), fontsize=12, color=F.C_DS, weight="bold", va="center")
ax.set_xlim(-100, 100)
save(fig, 2)

# 3  Align: the mean DS current source density, depth down the page, +-50 ms
v = gaussian_filter1d(mean_ds, 1.0, axis=0)
csd = -(v[:-2] - 2 * v[1:-1] + v[2:])
sel = np.abs(t) <= 50
lim = np.nanpercentile(np.abs(csd[:, sel]), 99)
fig, ax = fig_ax()
ax.imshow(csd[:, sel], aspect="auto", cmap="RdBu_r", vmin=-lim, vmax=lim, extent=[-50, 50, csd.shape[0], 0],
          interpolation="bilinear")
ax.axvline(0, color="white", lw=0.6, ls=":")
ax.text(46, 2.5, "sink", color="white", fontsize=11, ha="right", va="top", weight="bold",
        bbox=dict(boxstyle="round,pad=0.15", fc=F.C_DS, ec="none"))
ax.text(46, 8.5, "source", color="white", fontsize=11, ha="right", va="top", weight="bold",
        bbox=dict(boxstyle="round,pad=0.15", fc="#c0392b", ec="none"))
ax.text(-47, 2.5, "depth ↓", color=F.SOFT, fontsize=11, ha="left", va="top")
save(fig, 3)

# 4  Classify: amplitude against fast power, every Halo event of all 16 mice
rc = D.rc()
h = rc[(rc.wf == "halo") & rc.lab.isin(F.LABS)]
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0.13, 0.2, 0.84, 0.76])
for k, col, s, a, zo in (("DS", F.C_DS, 3, 0.35, 1), ("TZ", F.C_PDS, 9, 0.9, 2), ("IED", F.C_IED, 9, 0.9, 3)):
    q = h[h.kind == k]
    ax.scatter(q.amp, q.hf, s=s, color=col, alpha=a, lw=0, zorder=zo)
ax.set_xlabel("amplitude →", fontsize=11, color=F.SOFT, labelpad=2)
ax.set_ylabel("fast power →", fontsize=11, color=F.SOFT, labelpad=2)
ax.set_xticks([])
ax.set_yticks([])
for nm, y, col in (("IED", 0.95, F.C_IED), ("BT", 0.78, F.C_PDS), ("DS", 0.61, F.C_DS)):
    ax.text(0.02, y, nm, transform=ax.transAxes, fontsize=12, weight="bold", color=col, va="top", zorder=5,
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85))
lo, hi = h.hf.quantile(0.002), h.hf.max()
ax.set_xlim(h.amp.quantile(0.002), h.amp.quantile(0.998))
ax.set_ylim(lo, hi + 0.04 * (hi - lo))
save(fig, 4)
print("saved strip_1..4 in", OUT, "deepest contact", deep + 1)
