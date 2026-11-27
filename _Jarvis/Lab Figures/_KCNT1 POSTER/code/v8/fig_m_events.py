"""Methods: reading the CSD (poster v7). A curated dentate spike and a curated IED from one KCNT1 recording (m1609, YH Het;
VACC raw, methods_fig_v4.py's processing), on ONE depth axis with the lab's cells beside it (cells.py):
  CSD + voltage   the CSD with the voltage of every fourth contact drawn over it, as in figure E (one CSD scale and one
                  trace gain for both events, set by the dentate spike, so the IED's size shows)
  0-600 Hz        Jarvis-pane spectrograms (dB over each contact's own baseline) at the middle of eight 8-contact bands,
                  each at its own depth, with that contact's voltage (>1 Hz) drawn over it, so the power can be read
                  against the wave that carries it
v7: the IED is the sharpest curated one in the recording that, like the old one, runs from CA1 through both blades
(905.34 s: half-width 12 ms on its largest contact, against 44 ms for v6's 882.75 s; tools/ied_pick.py compares six).

Where the cells sit: m1609 has no traced layers, so they follow its own mean dentate spike (methods_fig.py's landmarks):
the upper and lower blades' sinks (CSC 34 and 56) are their middle molecular layers; granule cell layers 7 contacts
(140 um) inside each sink, the hilus between them; CA1's pyramidal layer 27.5 contacts (550 um) above the upper sink, the
fissure 5.5 above it: the spacings of the Allen laminae at the probe (section.py).

data/m_events_v7.npz holds everything drawn, so the figure redraws without the raw windows. To rebuild it, delete it and
put the VACC windows (windows_m1609.npz, ied_m1609_s1.npz) and methods_fig_v4.py (code/v2) in the folder named by the
environment variable KCNT1_VACC (default: the scratch folder's vacc/)."""
import os, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt
import matplotlib.patheffects as pe
import style as S
import icons as I
import cells as Ce

HERE = os.path.dirname(os.path.abspath(__file__))
VACC = os.environ.get("KCNT1_VACC", os.path.normpath(os.path.join(HERE, "..", "..", "vacc")))
SPEC = [4, 12, 20, 28, 36, 44, 52, 60]
CACHE = os.path.join(HERE, "data", "m_events_v7.npz")
EV = [("Dentate spike", "5–100 Hz", os.path.join(VACC, "windows_m1609.npz"), 1716.611, True),
      ("IED", ">1 Hz", os.path.join(VACC, "ied_m1609_s1.npz"), 905.339052, False)]

if not os.path.exists(CACHE):
    sys.path.insert(0, VACC)
    import methods_fig_v4 as MF  # noqa: E402
    out = {}
    hp = butter(3, 1.0, btype="high", fs=MF.FS, output="sos")
    for k, (label, _b, npz, tv, is_ds) in enumerate(EV):
        X, half, z = MF.load(npz, tv)
        Xn = MF.notch(X)
        tt = np.arange(X.shape[-1]) / MF.FS - half
        w = (tt >= -MF.HALF) & (tt <= MF.HALF)
        V = Xn[[c - 1 for c in MF.EVEN]]
        if is_ds:
            V = MF.band(V, 5.0, 100.0)
        else:
            V = sosfiltfilt(hp, V, axis=-1)
            V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
        V = V[:, w]
        sw = (tt >= -0.5) & (tt <= 0.5)
        for j, c in enumerate(SPEC):
            s_, f_, ts_ = MF.xf_spec(Xn[c - 1][sw])
            out["S%d_%d" % (k, j)] = (s_ - MF.baseline(z, c)[:, None]).astype(np.float32)
            y = sosfiltfilt(hp, Xn[c - 1])[sw]                     # the contact's voltage over the same second, >1 Hz
            out["T%d_%d" % (k, j)] = (y - np.median(y)).astype(np.float32)
        out["f"], out["ts"], out["tT"] = f_, ts_ - 0.5, (tt[sw]) * 1000
        out["V%d" % k], out["C%d" % k], out["tm%d" % k] = V.astype(np.float32), MF.csd(V).astype(np.float32), tt[w] * 1000
    np.savez_compressed(CACHE, **out)
Z = np.load(CACHE)

clim = np.percentile(np.abs(Z["C0"]), 99.5)            # one CSD scale for both, set by the dentate spike (the IED saturates it)
KV = 3.5 / float(np.abs(Z["V1"]).max())                # one trace gain for both: the IED's biggest swing spans 3.5 contacts
gain = np.percentile(np.abs(Z["V0"]), 99.5)            # (v6's dentate-spike gain, for the printout)
allS = np.concatenate([Z["S%d_%d" % (k, j)].ravel() for k in (0, 1) for j in range(8)])
slo, shi = -6.0, max(12.0, float(np.percentile(allS, 99.9)))
tgain = max(np.percentile(np.abs(Z["T1_%d" % j]), 99.9) for j in range(8))     # spectrogram traces: one gain, set by the IED

# depth, in contacts (CSC 1 at the top): where m1609's dentate spike puts the layers
UP_SINK, LO_SINK = 34, 56
GCL1, GCL2 = UP_SINK + 7, LO_SINK - 7
FISSURE = UP_SINK - 5.5
CA1_SP = UP_SINK - 27.5
YL = (65.5, 0.5)

W, H = 9.6, 6.74
fig = S.figure(W, H)
Y0, HH = 0.66, 5.6
CW, SWD, G = 2.08, 1.4, 0.13
GX = [1.06, 4.88]                                       # left edge of each event's group

# the cells, once, on the left
ia = I.icon_axes(fig, 0.3, Y0, 0.7, HH, YL)
xi = 0.5 * ia.get_xlim()[1]
Ce.group(ia, "pyr", xi, CA1_SP, FISSURE - 0.3)
Ce.group(ia, "gc_up", xi, GCL1, FISSURE + 0.6)
Ce.group(ia, "gc_down", xi, GCL2, YL[0] - 0.8)
hs = ia.get_xlim()[1] * 0.86 / 13.4
Ce.sst(ia, Ce.frame((xi, (GCL1 + GCL2) / 2), (0, -hs), (hs, 0)), spine_lw=0.35)
for nm, a, b, col in (("CA1", 1.2, FISSURE - 0.6, S.PYR), ("DG", FISSURE + 0.6, 64.8, S.GC)):
    S.text_at(fig, 0.09, Y0 + HH * (((a + b) / 2) - YL[1]) / (YL[0] - YL[1]), nm, rotation=90, ha="center", va="center",
              fontsize=S.LABEL, fontweight="bold", color=col)
    bx = S.ax_at(fig, 0.22, Y0, 0.05, HH); bx.set_ylim(*YL); bx.set_xlim(0, 1); bx.axis("off")
    bx.plot([0.5, 0.5], [a, b], c=col, lw=1.8, solid_capstyle="butt")

TR = list(range(4, 65, 4))                              # the voltage of every fourth contact over the CSD
for k, (label, band_txt, _npz, _tv, is_ds) in enumerate(EV):
    x0 = GX[k]
    tm = Z["tm%d" % k]
    V, C = Z["V%d" % k], Z["C%d" % k]
    tl = S.text_at(fig, x0, 0.0, label, fontsize=S.TITLE + 2, fontweight="bold", color=S.INK)
    bb = tl.get_window_extent(fig.canvas.get_renderer())
    S.text_at(fig, x0 + bb.width / fig.dpi + 0.1, 0.075, band_txt, fontsize=S.NOTE, color=S.SOFT)
    # CSD with the voltage over it
    ax = S.ax_at(fig, x0, Y0, CW, HH)
    im = ax.imshow(C, aspect="auto", cmap=S.CSD_CMAP, vmin=-clim, vmax=clim, interpolation="bilinear", extent=[tm[0], tm[-1], 65, 1])
    for c in TR:
        r = c // 2 - 1
        ax.plot(tm, c - KV * V[r], color=S.INK, lw=0.75, alpha=0.85, solid_joinstyle="round")
    ax.set_xlim(tm[0], tm[-1]); ax.set_ylim(*YL)
    ax.axhline(FISSURE, c=S.INK, lw=0.7, ls=(0, (3, 3)), alpha=0.35)
    ax.set_yticks([]); ax.spines["left"].set_visible(False)
    ax.set_xticks([-100, 0, 100]); ax.set_xlabel("ms", labelpad=1)
    ax.set_title("CSD + voltage", fontsize=S.LABEL - 1, pad=5, fontweight="normal", color=S.SOFT)
    if k == 0:
        sb = 2000.0                                      # 2 mV at the shared trace gain, in the dentate spike's quiet corner
        ax.plot([tm[0] + 7] * 2, [YL[0] - 1.6, YL[0] - 1.6 - KV * sb], color=S.INK, lw=1.8, solid_capstyle="butt")
        ax.text(tm[0] + 15, YL[0] - 1.6 - KV * sb / 2, "2 mV", ha="left", va="center", fontsize=S.SMALL, color=S.INK,
                path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])
    # spectrograms, each at its own depth, with its voltage over it
    xs = x0 + CW + G
    for j, c in enumerate(SPEC):
        top = Y0 + HH * ((8 * j + 0.5 + 0.2) - YL[1]) / (YL[0] - YL[1])
        hh = HH * (8 - 0.4) / (YL[0] - YL[1])
        ax2 = S.ax_at(fig, xs, top, SWD, hh)
        im2 = ax2.pcolormesh(Z["ts"] * 1000, Z["f"], Z["S%d_%d" % (k, j)], cmap=S.SPEC_CMAP, vmin=slo, vmax=shi, shading="gouraud",
                             rasterized=True)
        ts_ms = Z["ts"] * 1000
        ax2.set_ylim(0, 600); ax2.set_xlim(ts_ms[0], ts_ms[-1]); ax2.set_yticks([])
        tr, tT = Z["T%d_%d" % (k, j)], Z["tT"]
        m = (tT >= ts_ms[0]) & (tT <= ts_ms[-1])
        ax2.plot(tT[m], 300 + 255 * np.clip(tr[m] / tgain, -1.1, 1.1), c="white", lw=0.8,
                 path_effects=[pe.withStroke(linewidth=1.7, foreground="#1E1E1E", alpha=0.55)], solid_joinstyle="round")
        for sp_ in ax2.spines.values():
            sp_.set_visible(False)
        if j < 7:
            ax2.set_xticks([])
        else:
            ax2.spines["bottom"].set_visible(True)
            ax2.set_xticks([-400, 0, 400]); ax2.set_xlabel("ms", labelpad=1)
        if j == 0:
            ax2.set_title("0–600 Hz", fontsize=S.LABEL - 1, pad=5, fontweight="normal", color=S.SOFT)

# the two colour scales, once, on the right
cx = 8.86
cax = S.ax_at(fig, cx, Y0 + 0.35, 0.12, 0.3 * HH)
cb = fig.colorbar(im, cax=cax, ticks=[-clim * 0.8, clim * 0.8])
cb.ax.set_yticklabels(["sink", "source"], fontsize=S.NOTE - 0.5); cb.ax.tick_params(length=0, pad=2); cb.outline.set_visible(False)
S.text_at(fig, cx + 0.06, Y0 + 0.1, "CSD", fontsize=S.NOTE, fontweight="bold", ha="center")
cax = S.ax_at(fig, cx, Y0 + 0.52 * HH, 0.12, 0.3 * HH)
cb = fig.colorbar(im2, cax=cax, ticks=[slo, 0, shi])
cb.ax.set_yticklabels(["−6", "0", "+%d" % round(shi)], fontsize=S.SMALL); cb.ax.tick_params(length=2, pad=2)
cb.outline.set_visible(False)
S.text_at(fig, cx + 0.06, Y0 + 0.52 * HH - 0.25, "dB", fontsize=S.NOTE, fontweight="bold", ha="center")
S.save(fig, os.path.join(HERE, "out", "M_events.png"))
pk = lambda V: float(np.abs(V).max())                     # noqa: E731
print("M_events: gain %.0f uV, CSD clim %.0f, spectrogram %.0f..%.0f dB, DS peak %.0f uV, IED peak %.0f uV, trace gain %.0f uV" %
      (gain, clim, slo, shi, pk(Z["V0"]), pk(Z["V1"]), tgain))
