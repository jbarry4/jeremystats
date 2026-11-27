"""Methods: reading the CSD (poster v9). A curated dentate spike and an IED from one KCNT1 recording (m1609, YH Het; VACC raw,
methods_fig_v4.py's processing), on ONE depth axis with the lab's cells beside it (cells.py):
  CSD + voltage   the CSD with the voltage of every fourth contact drawn over it, as in figure E (one CSD scale and one
                  trace gain for both events, set by the dentate spike and the IED, so the IED's size shows)
  0-600 Hz        Jarvis-pane spectrograms (dB over each contact's own baseline) at the middle of eight 8-contact bands,
                  each at its own depth, with that contact's voltage (>1 Hz) drawn over it

v9 (the user's comments on v8):
  - the IED: "isn't SHARP enough. I want something with a high prominence and narrow halfwidth, and high power". Every one
    of the 688 spikes in m1609's committed Lock set was scored on VACC (tools/scan_sharp.py: the largest contact's peak,
    its half-width, how far it stands above every other swing within 300 ms, and its 100-600 Hz power over baseline);
    the chosen one is IED_T below (tools/ied_sheet.py draws the best ones side by side). v8's (905.34 s) stood barely
    above its neighbours (1.2x).
  - each event is named in a header card, as the f-I matrix's cell types are: its name, what it is, and its own waveform
    (the two on one scale, so the IED's size shows there too)
  - the cells: both blades the same size (one scale), a PV basket cell at each granule layer's hilar border, the hilar
    SST cell between them, all clear of the CA1 and DG bars (cells.py v9)

Where the cells sit: m1609 has no traced layers, so they follow its own mean dentate spike (methods_fig.py's landmarks):
the upper and lower blades' sinks (CSC 34 and 56) are their middle molecular layers; granule cell layers 7 contacts
(140 um) inside each sink, the hilus between them; CA1's pyramidal layer 27.5 contacts (550 um) above the upper sink, the
fissure 5.5 above it: the spacings of the Allen laminae at the probe (section.py).

data/m_events_v9.npz holds everything drawn, so the figure redraws without the raw windows. To rebuild it, delete it and
put the VACC windows (windows_m1609.npz, sharp_m1609_s1.npz) and methods_fig_v4.py (code/v2) in the folder named by the
environment variable KCNT1_VACC (default: the scratch folder's vacc/)."""
import os, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch
import style as S
import icons as I
import cells as Ce

HERE = os.path.dirname(os.path.abspath(__file__))
VACC = os.environ.get("KCNT1_VACC", os.path.normpath(os.path.join(HERE, "..", "..", "vacc")))
SPEC = [4, 12, 20, 28, 36, 44, 52, 60]
IED_T = float(os.environ.get("KCNT1_IED_T", "1305.428753"))
CACHE = os.environ.get("KCNT1_EVENTS_CACHE", os.path.join(HERE, "data", "m_events_v9.npz"))
OUT = os.environ.get("KCNT1_EVENTS_OUT", os.path.join(HERE, "out", "M_events.png"))
EV = [("Dentate spike", "a normal dentate event", "5–100 Hz", os.path.join(VACC, "windows_m1609.npz"), 1716.611, True),
      ("IED", "an interictal discharge", ">1 Hz", os.path.join(VACC, "sharp_m1609_s1.npz"), IED_T, False)]
DS_C, DS_T = "#2B7A87", "#E5F1F3"                  # the two events' own colours: a calm teal, an alarm crimson
IED_C, IED_TINT = "#B2182B", "#FBE8EA"

if not os.path.exists(CACHE):
    sys.path.insert(0, VACC)
    import methods_fig_v4 as MF  # noqa: E402
    out = {}
    hp = butter(3, 1.0, btype="high", fs=MF.FS, output="sos")
    for k, (label, _what, _b, npz, tv, is_ds) in enumerate(EV):
        X, half, z = MF.load(npz, tv)
        Xn = MF.notch(X)
        tt = np.arange(X.shape[-1]) / MF.FS - half
        V = Xn[[c - 1 for c in MF.EVEN]]
        if is_ds:
            V = MF.band(V, 5.0, 100.0)
        else:
            V = sosfiltfilt(hp, V, axis=-1)
            V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
            near = np.abs(tt) <= 0.04                      # v9: centred on the largest contact's peak
            r = int(np.argmax(np.abs(V[:, near]).max(1)))
            off = tt[np.flatnonzero(near)[int(np.argmax(np.abs(V[r, near])))]]
            tt = tt - off
            V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
            out["off_ms"] = off * 1000
        w = (tt >= -MF.HALF) & (tt <= MF.HALF)
        V = V[:, w]
        j0 = int(np.argmin(np.abs(tt)))                        # the second around the event, 2501 samples (as v8)
        sw = slice(j0 - 1250, j0 + 1251)
        for j, c in enumerate(SPEC):
            s_, f_, ts_ = MF.xf_spec(Xn[c - 1][sw])
            out["S%d_%d" % (k, j)] = (s_ - MF.baseline(z, c)[:, None]).astype(np.float32)
            y = sosfiltfilt(hp, Xn[c - 1])[sw]                     # the contact's voltage over the same second, >1 Hz
            out["T%d_%d" % (k, j)] = (y - np.median(y)).astype(np.float32)
        out["f"], out["ts"] = f_, ts_ - 0.5
        out["tT%d" % k] = tt[sw] * 1000
        out["V%d" % k], out["C%d" % k], out["tm%d" % k] = V.astype(np.float32), MF.csd(V).astype(np.float32), tt[w] * 1000
    np.savez_compressed(CACHE, **out)
Z = np.load(CACHE)

clim = np.percentile(np.abs(Z["C0"]), 99.5)            # one CSD scale for both, set by the dentate spike (the IED saturates it)
KV = 3.5 / float(np.abs(Z["V1"]).max())                # one trace gain for both: the IED's biggest swing spans 3.5 contacts
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
Y0, HH = 0.95, 5.31                                     # v9: the header cards above
CW, SWD, G = 1.9, 1.29, 0.11
GW = CW + G + SWD
GX = [1.56, 1.56 + GW + 0.2]                           # left edge of each event's group
CX0, CX1 = 0.34, 1.49                                  # v9: the cells' own column, clear of the region bars

# ------------------------------------------------------------------ the cells, once, on the left
ia = I.icon_axes(fig, CX0, Y0, CX1 - CX0, HH, YL)
wd = ia.get_xlim()[1]
xi = 0.5 * wd
v_, c_, bb_, soma_, end_ = Ce._src("pyr")
sy_ = (FISSURE - 0.3 - CA1_SP) / (end_ - soma_)
Ce.group(ia, "pyr", xi, CA1_SP, FISSURE - 0.3, xscale=min(1.0, 0.97 * wd / ((bb_[2] - bb_[0]) * abs(sy_))))
k = Ce.blade_k(GCL1, FISSURE + 0.4)                     # one scale for both blades
up = Ce.blade(ia, "gc_up", xi, GCL1, -1, k)
dn = Ce.blade(ia, "gc_down", xi, GCL2, +1, k)
hs = wd * 0.78 / 13.4
Ce.sst(ia, Ce.frame((xi - 0.04 * wd, (GCL1 + GCL2) / 2 + 0.2), (0, -hs), (hs, 0)), spine_lw=0.35)
Ce.pv_basket(ia, up, xi + 0.24 * wd, z=6)
Ce.pv_basket(ia, dn, xi - 0.24 * wd, z=6, mirror=True)
for nm, a, b, col in (("CA1", 1.2, FISSURE - 0.6, S.PYR), ("DG", FISSURE + 0.6, 64.8, S.GC)):
    S.text_at(fig, 0.09, Y0 + HH * (((a + b) / 2) - YL[1]) / (YL[0] - YL[1]), nm, rotation=90, ha="center", va="center",
              fontsize=S.LABEL, fontweight="bold", color=col)
    bx = S.ax_at(fig, 0.22, Y0, 0.05, HH); bx.set_ylim(*YL); bx.set_xlim(0, 1); bx.axis("off")
    bx.plot([0.5, 0.5], [a, b], c=col, lw=1.8, solid_capstyle="butt")

# ------------------------------------------------------------------ the header cards: what each event is, and its waveform
card = S.ax_at(fig, 0, 0, W, H, zorder=-5)
card.set_xlim(0, W); card.set_ylim(H, 0); card.axis("off")
wf_k = [int(np.argmax(np.abs(Z["V%d" % k]).max(1))) for k in (0, 1)]           # each event's largest contact
wf_max = max(float(np.abs(Z["V%d" % k][wf_k[k]]).max()) for k in (0, 1))
for k, (label, what, band_txt, _npz, _tv, is_ds) in enumerate(EV):
    x0 = GX[k]
    col, tint = (DS_C, DS_T) if is_ds else (IED_C, IED_TINT)
    card.add_patch(FancyBboxPatch((x0, 0.02), GW, 0.56, boxstyle="round,pad=0,rounding_size=0.1", fc=tint, ec="none", zorder=0))
    ga = S.ax_at(fig, x0 + 0.16, 0.07, 0.92, 0.46)                  # the waveform, both on the IED's scale
    tm = Z["tm%d" % k]
    m = np.abs(tm) <= 75
    y = Z["V%d" % k][wf_k[k]][m] / wf_max
    if np.abs(y).max() > 0 and y[np.argmax(np.abs(y))] < 0:
        y = -y                                                     # drawn with its peak up, as a glyph
    for lw_, al in ((7.0, 0.10), (4.6, 0.16), (2.8, 0.28)):
        ga.plot(tm[m], y, c=col, lw=lw_, alpha=al, solid_capstyle="round", solid_joinstyle="round")
    ga.plot(tm[m], y, c=col, lw=1.5, solid_joinstyle="round")
    ga.set_xlim(-75, 75); ga.set_ylim(-0.62, 1.08); ga.axis("off")
    S.text_at(fig, x0 + 0.17, 0.08, band_txt, fontsize=S.SMALL, color=col, ha="left", va="top", alpha=0.9)
    S.text_at(fig, x0 + 1.2, 0.07, label, fontsize=S.TITLE + 3, fontweight="bold", color=col)
    S.text_at(fig, x0 + 1.2, 0.385, what, fontsize=S.NOTE, color=col)

# ------------------------------------------------------------------ each event: CSD + voltage, and the spectrograms
TR = list(range(4, 65, 4))                              # the voltage of every fourth contact over the CSD
for k, (label, what, band_txt, _npz, _tv, is_ds) in enumerate(EV):
    x0 = GX[k]
    tm = Z["tm%d" % k]
    V, C = Z["V%d" % k], Z["C%d" % k]
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
    xs = x0 + CW + G
    for j, c in enumerate(SPEC):
        top = Y0 + HH * ((8 * j + 0.5 + 0.2) - YL[1]) / (YL[0] - YL[1])
        hh = HH * (8 - 0.4) / (YL[0] - YL[1])
        ax2 = S.ax_at(fig, xs, top, SWD, hh)
        im2 = ax2.pcolormesh(Z["ts"] * 1000, Z["f"], Z["S%d_%d" % (k, j)], cmap=S.SPEC_CMAP, vmin=slo, vmax=shi, shading="gouraud",
                             rasterized=True)
        ts_ms = Z["ts"] * 1000
        ax2.set_ylim(0, 600); ax2.set_xlim(ts_ms[0], ts_ms[-1]); ax2.set_yticks([])
        tr, tT = Z["T%d_%d" % (k, j)], Z["tT%d" % k]
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

# ------------------------------------------------------------------ the two colour scales, once, on the right
cx = GX[1] + GW + 0.26
cax = S.ax_at(fig, cx, Y0 + 0.35, 0.12, 0.3 * HH)
cb = fig.colorbar(im, cax=cax, ticks=[-clim * 0.8, clim * 0.8])
cb.ax.set_yticklabels(["sink", "source"], fontsize=S.NOTE - 0.5); cb.ax.tick_params(length=0, pad=2); cb.outline.set_visible(False)
S.text_at(fig, cx + 0.06, Y0 + 0.1, "CSD", fontsize=S.NOTE, fontweight="bold", ha="center")
cax = S.ax_at(fig, cx, Y0 + 0.52 * HH, 0.12, 0.3 * HH)
cb = fig.colorbar(im2, cax=cax, ticks=[slo, 0, shi])
cb.ax.set_yticklabels(["−6", "0", "+%d" % round(shi)], fontsize=S.SMALL); cb.ax.tick_params(length=2, pad=2)
cb.outline.set_visible(False)
S.text_at(fig, cx + 0.06, Y0 + 0.52 * HH - 0.25, "dB", fontsize=S.NOTE, fontweight="bold", ha="center")
S.save(fig, OUT)

# the numbers the CSD text quotes
FS = 2500.0
s = Z["V1"][wf_k[1]]
j = int(np.argmax(np.abs(s))); pk = s[j]; sg = np.sign(pk)
L = j
while L > 0 and sg * s[L] > abs(pk) / 2:
    L -= 1
R_ = j
while R_ < len(s) - 1 and sg * s[R_] > abs(pk) / 2:
    R_ += 1
ds_pk = float(np.abs(Z["V0"]).max())
hf = lambda k_: np.mean([Z["S%d_%d" % (k_, jj)][(Z["f"] >= 100) & (Z["f"] <= 600)][:, np.abs(Z["ts"]) <= 0.05].mean() for jj in range(8)])  # noqa: E731
print("M_events: IED %.3f s (peak offset %.1f ms), largest contact CSC %d: %.0f uV, half-width %.1f ms; DS peak %.0f uV (IED %.1fx); "
      "100-600 Hz at 0: IED %.1f dB, DS %.1f dB; CSD clim %.0f, spectrogram %.0f..%.0f dB" %
      (IED_T, float(Z["off_ms"]), 2 * (wf_k[1] + 1), abs(pk), (R_ - L) / FS * 1000, ds_pk, abs(pk) / ds_pk, hf(1), hf(0), clim, slo, shi))
