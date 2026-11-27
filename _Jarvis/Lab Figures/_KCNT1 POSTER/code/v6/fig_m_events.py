"""Methods: reading the CSD (poster v6). The curated dentate spike and IED of KCNT1 m1609 (VACC raw, methods_fig_v4.py's
processing: voltage on the 32 even contacts, CSD from them, Jarvis-pane spectrograms in dB over the contact's own baseline),
now drawn on ONE depth axis with the lab's cell icons beside it instead of channel labels.

Where the cells sit: m1609 has no traced layers, so the icons follow its own mean dentate spike (methods_fig.py's landmarks):
the upper and lower blades' sinks (CSC 34 and 56) are their middle molecular layers, the source between them (CSC 40) the
granule layer and hilus; granule cell layers 7 contacts (140 um) inside each sink and CA1's pyramidal layer 27.5 contacts
(550 um) above the upper sink, the spacings of the Allen laminae at the probe (section.py). Spectrograms are taken at the
middle of eight 8-contact bands (CSC 4, 12 ... 60) so each sits at its own depth.

data/m_events.npz holds everything drawn (voltage, CSD, spectrograms), so the figure redraws without the raw windows. To
rebuild it from the raw, delete it and put the VACC windows (windows_m1609.npz, ied_m1609_s1.npz) and methods_fig_v4.py
(code/v2) in a folder named by the environment variable KCNT1_VACC (default: the scratch folder's vacc/)."""
import os, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt
import style as S
import icons as I

HERE = os.path.dirname(os.path.abspath(__file__))
VACC = os.environ.get("KCNT1_VACC", os.path.normpath(os.path.join(HERE, "..", "..", "vacc")))
SPEC = [4, 12, 20, 28, 36, 44, 52, 60]
CACHE = os.path.join(HERE, "data", "m_events.npz")
EV = [("Dentate spike", os.path.join(VACC, "windows_m1609.npz"), 1716.611, True),
      ("IED", os.path.join(VACC, "ied_m1609_s1.npz"), 882.748327, False)]

if not os.path.exists(CACHE):
    sys.path.insert(0, VACC)
    import methods_fig_v4 as MF  # noqa: E402
    out = {}
    for k, (label, npz, tv, is_ds) in enumerate(EV):
        X, half, z = MF.load(npz, tv)
        Xn = MF.notch(X)
        tt = np.arange(X.shape[-1]) / MF.FS - half
        w = (tt >= -MF.HALF) & (tt <= MF.HALF)
        V = Xn[[c - 1 for c in MF.EVEN]]
        if is_ds:
            V = MF.band(V, 5.0, 100.0)
        else:
            V = sosfiltfilt(butter(3, 1.0, btype="high", fs=MF.FS, output="sos"), V, axis=-1)
            V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
        V = V[:, w]
        sw = (tt >= -0.5) & (tt <= 0.5)
        for j, c in enumerate(SPEC):
            s_, f_, ts_ = MF.xf_spec(Xn[c - 1][sw])
            out["S%d_%d" % (k, j)] = (s_ - MF.baseline(z, c)[:, None]).astype(np.float32)
        out["f"], out["ts"] = f_, ts_ - 0.5
        out["V%d" % k], out["C%d" % k], out["tm%d" % k] = V.astype(np.float32), MF.csd(V).astype(np.float32), tt[w] * 1000
    np.savez_compressed(CACHE, **out)
Z = np.load(CACHE)

gain = np.percentile(np.abs(Z["V0"]), 99.5)           # one trace gain and one CSD scale for both, set by the dentate spike
clim = np.percentile(np.abs(Z["C0"]), 99.5)
allS = np.concatenate([Z["S%d_%d" % (k, j)].ravel() for k in (0, 1) for j in range(8)])
slo, shi = -6.0, max(12.0, float(np.percentile(allS, 99.9)))

# depth, in contacts (CSC 1 at the top): where m1609's dentate spike puts the layers
UP_SINK, SOURCE, LO_SINK = 34, 40, 56
GCL1, GCL2 = UP_SINK + 7, LO_SINK - 7
FISSURE = UP_SINK - 5.5
CA1_SP = UP_SINK - 27.5
YL = (65.5, 0.5)

W, H = 13.8, 4.55
fig = S.figure(W, H)
Y0, HH = 0.74, 3.38
VW, CW, SWD, G = 1.42, 1.52, 1.62, 0.17
GX = [1.05, 6.75]                                       # left edge of each event's group

# the cells, once, on the left
ia = I.icon_axes(fig, 0.36, Y0, 0.62, HH, YL)
xi = 0.55 * ia.get_xlim()[1]
I.pyramidal(ia, xi, CA1_SP, FISSURE + 0.4, width=3.7)
I.granule(ia, xi, GCL1, FISSURE + 1.0, width=3.3)
I.granule(ia, xi, GCL2, LO_SINK + 5.0, width=3.3)
for nm, a, b, col in (("CA1", 1.2, FISSURE - 0.6, S.PYR), ("DG", FISSURE + 0.6, 64.6, S.GC)):
    S.text_at(fig, 0.13, Y0 + HH * (((a + b) / 2) - YL[1]) / (YL[0] - YL[1]), nm, rotation=90, ha="center", va="center",
              fontsize=S.LABEL, fontweight="bold", color=col)
    bx = S.ax_at(fig, 0.27, Y0, 0.05, HH); bx.set_ylim(*YL); bx.set_xlim(0, 1); bx.axis("off")
    bx.plot([0.5, 0.5], [a, b], c=col, lw=1.6, solid_capstyle="butt")

for k, (label, _npz, _tv, is_ds) in enumerate(EV):
    x0 = GX[k]
    tm = Z["tm%d" % k]
    V, C = Z["V%d" % k], Z["C%d" % k]
    S.text_at(fig, x0, 0.02, label, fontsize=S.TITLE + 2, fontweight="bold", color=S.INK)
    # voltage, 32 even contacts at their depth
    ax = S.ax_at(fig, x0, Y0, VW, HH)
    for r in range(32):
        ax.plot(tm, 2 * (r + 1) - 2.8 * V[r] / gain, color=S.INK, lw=0.6, clip_on=False)
    ax.set_xlim(tm[0], tm[-1]); ax.set_ylim(*YL); S.bare(ax)
    ax.axhline(FISSURE, c=S.FAINT, lw=0.8, ls=(0, (3, 3)), zorder=0)
    sb = 1000.0
    ax.plot([tm[-1] + 9] * 2, [63, 63 - 2.8 * sb / gain], color=S.INK, lw=1.6, clip_on=False, solid_capstyle="butt")
    ax.text(tm[-1] + 19, 63 - 1.4 * sb / gain, "1 mV", rotation=90, va="center", ha="left", fontsize=S.NOTE)
    ax.plot([tm[-1] - 50, tm[-1]], [66.6, 66.6], color=S.INK, lw=1.6, clip_on=False, solid_capstyle="butt")
    ax.text(tm[-1] - 25, 67.4, "50 ms", ha="center", va="top", fontsize=S.NOTE)
    ax.set_title("Voltage", fontsize=S.LABEL, pad=5, fontweight="normal", color=S.SOFT)
    # CSD
    ax = S.ax_at(fig, x0 + VW + G + 0.18, Y0, CW, HH)
    im = ax.imshow(C, aspect="auto", cmap=S.CSD_CMAP, vmin=-clim, vmax=clim, interpolation="bilinear", extent=[tm[0], tm[-1], 65, 1])
    ax.set_ylim(*YL)
    ax.axhline(FISSURE, c=S.INK, lw=0.7, ls=(0, (3, 3)), alpha=0.35)
    ax.set_yticks([]); ax.spines["left"].set_visible(False)
    ax.set_xticks([-100, 0, 100]); ax.set_xlabel("ms", labelpad=1)
    ax.set_title("CSD", fontsize=S.LABEL, pad=5, fontweight="normal", color=S.SOFT)
    # spectrograms, each at its own depth
    xs = x0 + VW + G + 0.18 + CW + G + 0.05
    for j, c in enumerate(SPEC):
        top = Y0 + HH * ((8 * j + 0.5 + 0.18) - YL[1]) / (YL[0] - YL[1])
        hh = HH * (8 - 0.36) / (YL[0] - YL[1])
        ax2 = S.ax_at(fig, xs, top, SWD, hh)
        im2 = ax2.pcolormesh(Z["ts"] * 1000, Z["f"], Z["S%d_%d" % (k, j)], cmap=S.SPEC_CMAP, vmin=slo, vmax=shi, shading="gouraud",
                             rasterized=True)
        ax2.set_ylim(0, 600); ax2.set_xlim(-500, 500); ax2.set_yticks([])
        ax2.axvline(0, color="w", lw=0.6, ls=(0, (2, 2)), alpha=0.7)
        for sp_ in ax2.spines.values():
            sp_.set_visible(False)
        if j < 7:
            ax2.set_xticks([])
        else:
            ax2.spines["bottom"].set_visible(True)
            ax2.set_xticks([-400, 0, 400]); ax2.set_xlabel("ms", labelpad=1)
        if j == 0:
            ax2.set_title("0–600 Hz", fontsize=S.LABEL, pad=5, fontweight="normal", color=S.SOFT)

# the two colour scales, once, on the right
cx = 12.25
cax = S.ax_at(fig, cx, Y0 + 0.35, 0.13, 1.25)
cb = fig.colorbar(im, cax=cax, ticks=[-clim * 0.8, clim * 0.8])
cb.ax.set_yticklabels(["sink", "source"], fontsize=S.NOTE); cb.ax.tick_params(length=0, pad=3); cb.outline.set_visible(False)
S.text_at(fig, cx + 0.065, Y0 + 0.08, "CSD", fontsize=S.NOTE, fontweight="bold", ha="center")
cax = S.ax_at(fig, cx, Y0 + 2.05, 0.13, 1.25)
cb = fig.colorbar(im2, cax=cax, ticks=[slo, 0, shi])
cb.ax.set_yticklabels(["−6", "0", "+%d" % round(shi)], fontsize=S.SMALL + 0.5); cb.ax.tick_params(length=2, pad=2)
cb.outline.set_visible(False)
S.text_at(fig, cx + 0.065, Y0 + 1.78, "dB", fontsize=S.NOTE, fontweight="bold", ha="center")
S.save(fig, os.path.join(HERE, "out", "M_events.png"))
print("M_events: gain %.0f uV, CSD clim %.0f, spectrogram %.0f..%.0f dB, IED peak %.0f uV" % (gain, clim, slo, shi, np.abs(Z["V1"]).max()))
