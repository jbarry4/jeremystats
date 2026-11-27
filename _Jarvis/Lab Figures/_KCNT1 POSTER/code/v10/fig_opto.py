"""Figure F (poster v6): one light-driven SST interneuron, redrawn from the numbers in Dylan Marchand's 2024 poster
(FinalKcnt1_Dylan 1.pdf, Figs. 7 and 8; data/opto_fig7.npz and data/opto_fig8.json from opto_extract.py, opto_tiles.py,
opto_extract8.py and opto_rates2.py).

v5 drew this as two figures (F: LFP, spectrogram, spikes; G: autocorrelation). v6 draws them as ONE grid, so each light
condition is one column from top to bottom: a tinted column per condition, its name once at the top with the light it got,
then the LFP, the spectrogram, the unit's spikes and the unit's spike autocorrelation. Under each autocorrelation, blue
ticks mark multiples of the light's period, where the peaks should fall if the bursts lock to the light. On the right:
firing rate (mean of each run) beside the first rows, rhythm strength (autocorrelation power at the light frequency) beside
the last.

v7: the light bar is the light itself, one blue tick per pulse at the condition's frequency, so 5, 7 and 12 Hz read in the
bar (pulse width is not drawn: it is not in the 2024 poster).
v8: the unit's row is named by the cell itself: an SST cell (cells.py) glowing blue (it carries ChR2), its axon running into
its own spikes; the plots 0.4 in taller."""
import os, json
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle
import style as S

HERE = os.path.dirname(os.path.abspath(__file__))
D7 = np.load(os.path.join(HERE, "data", "opto_fig7.npz"), allow_pickle=True)
D8 = json.load(open(os.path.join(HERE, "data", "opto_fig8.json")))
UNIT, UNIT_DARK = S.SST_FILL, S.SST
LIGHT = "#2F86D6"                      # blue light (ChR2): every light cue on the poster
LIGHT_TINT, REST_TINT = "#EAF3FC", "#F2F4F7"
COLS = [("Baseline", "Baseline", "Baseline", None), ("5 Hz A", "5 Hz light", "5 Hz (run 1)", 5.0),
        ("7 Hz", "7 Hz light", "7 Hz", 7.0), ("12 Hz A", "12 Hz light", "12 Hz", 12.0)]
X0, CW, CG = 1.18, 2.42, 0.30
xs = [X0 + k * (CW + CG) for k in range(4)]
XR = xs[3] + CW
SPEC_V = (112, 180)
YLIM = (-1700, 950)
RUNS = [("Baseline", 0), ("5 Hz (run 1)", 1), ("5 Hz (run 2)", 1), ("7 Hz", 2), ("10 Hz (run 1)", 3), ("10 Hz (run 2)", 3), ("12 Hz", 4)]

W, H = 15.0, 7.95
Y_H = 0.0                                   # column names
Y_B, H_B = 0.40, 0.15                       # the light: one blue tick per pulse
Y_L, H_L = 0.60, 0.96                       # LFP
Y_S, H_S = 1.66, 1.98                       # spectrogram
Y_K, H_K = 3.74, 0.40                       # spikes
Y_A, H_A = 4.70, 2.45                       # autocorrelation
PAD = 0.12


def summary(fig, x, y, w, h, vals, ylim, yticks, title, note, xlabel=True, ty=None):
    """a summary panel at (x, y, w, h); its title and note at ty (default just above it), starting 0.68 in left of it so a
    glyph of the row it summarises can sit before the title (v10)."""
    ax = S.ax_at(fig, x, y, w, h)
    jit = np.array([0, -0.13, 0.13, 0, -0.13, 0.13, 0])
    means = [np.mean([v for (n, p), v in zip(RUNS, vals) if p == q]) for q in range(5)]
    ax.plot(range(5), means, c=S.SOFT, lw=1.4, zorder=2)
    for (n, p), v, j in zip(RUNS, vals, jit):
        ax.plot(p + j, v, "o", ms=7.5, mfc=S.GENO["WT"] if p == 0 else UNIT, mec="white", mew=0.9, zorder=3)
    ax.set_xticks(range(5)); ax.set_xticklabels(["Base", "5", "7", "10", "12"] if xlabel else [])
    ax.set_xlim(-0.45, 4.45); ax.set_ylim(*ylim); ax.set_yticks(yticks)
    if xlabel:
        ax.set_xlabel("Light (Hz)", labelpad=2)
    ty = y - 0.62 if ty is None else ty
    S.text_at(fig, x - 0.2, ty, title, fontsize=S.LABEL, fontweight="bold", color=S.INK)
    S.text_at(fig, x - 0.68, ty + 0.3, note, fontsize=S.SMALL + 0.5, color=S.SOFT)
    return ax


fig = S.figure(W, H)
bg = S.ax_at(fig, 0, 0, W, H, zorder=-10)
bg.set_xlim(0, W); bg.set_ylim(H, 0); bg.axis("off")
rows8 = {r["name"]: r for r in D8["rows"]}
AX0 = {"Baseline": 1961.6, "5 Hz (run 1)": 1958.8, "7 Hz": 1958.8, "12 Hz": 1958.6}
for k, (key, name, rname, hz) in enumerate(COLS):
    lit = hz is not None
    # the column: one tinted card from its name to its autocorrelation
    bg.add_patch(FancyBboxPatch((xs[k] - PAD, Y_H - 0.04), CW + 2 * PAD, Y_A + H_A + 0.42 - Y_H, boxstyle="round,pad=0,rounding_size=0.12",
                                fc=LIGHT_TINT if lit else REST_TINT, ec="none", zorder=0))
    S.text_at(fig, xs[k] + CW / 2, Y_H + 0.08, name, fontsize=S.TITLE + 1, fontweight="bold", color=S.INK, ha="center")
    e = D7[key + "|spec_extent"]
    t_a, t_b = float(e[0]), float(e[1])
    span = t_b - t_a
    la = S.ax_at(fig, xs[k], Y_B, CW, H_B)              # v7: the bar is the light itself, one tick per pulse
    la.set_xlim(0, span); la.set_ylim(0, 1); S.bare(la)
    if lit:
        la.axhspan(0.0, 1.0, color=LIGHT_TINT, lw=0)
        tp = np.arange(0.0, span, 1.0 / hz)
        la.vlines(tp + 0.5 / hz, 0.0, 1.0, colors=LIGHT, lw=1.25)
    else:
        la.axhspan(0.42, 0.58, color="#C9CFD7", lw=0)
    # LFP: the PDF's own drawn trace (min/max envelope)
    a = S.ax_at(fig, xs[k], Y_L, CW, H_L)
    t, lo, hi = D7[key + "|env_t"], D7[key + "|env_lo"], D7[key + "|env_hi"]
    m = (t >= t_a) & (t <= t_b) & np.isfinite(lo)
    a.fill_between(t[m] - t_a, lo[m], hi[m], color=S.INK, lw=0.35, edgecolor=S.INK)
    a.set_xlim(0, span); a.set_ylim(*YLIM); S.bare(a)
    a.patch.set_alpha(0)
    if k == 3:
        a.plot([span + 0.2, span + 0.2], [250, 750], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
        a.text(span + 0.32, 500, "0.5 mV", ha="left", va="center", fontsize=S.NOTE, color=S.INK)
    # spectrogram: colors read back to dB, one scale for all, 0-100 Hz
    sa = S.ax_at(fig, xs[k], Y_S, CW, H_S)
    Z = D7[key + "|spec"]
    f = np.linspace(e[3], e[2], Z.shape[0])
    keep = f <= 101
    im = sa.imshow(Z[keep], aspect="auto", cmap=S.SPEC_CMAP, vmin=SPEC_V[0], vmax=SPEC_V[1], extent=[0, span, f[keep][-1], f[keep][0]],
                   interpolation="bilinear")
    sa.set_xlim(0, span); sa.set_ylim(0, 100); sa.set_xticks([])
    for sp_ in sa.spines.values():
        sp_.set_visible(False)
    if k == 0:
        sa.set_yticks([0, 50, 100]); sa.set_ylabel("Hz", labelpad=2)
        im_spec = im
    else:
        sa.set_yticks([])
    # the unit's spikes
    ka = S.ax_at(fig, xs[k], Y_K, CW, H_K)
    sp = D7[key + "|spikes"]
    sp = sp[(sp >= t_a) & (sp <= t_b)] - t_a
    ka.vlines(sp, 0.06, 0.94, color=UNIT, lw=1.1)
    ka.set_xlim(0, span); ka.set_ylim(0, 1); S.bare(ka)
    ka.patch.set_alpha(0)
    if k == 0:
        ka.plot([0, 1], [-0.32, -0.32], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
        ka.text(0.5, -0.45, "1 s", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
    # the unit's spike autocorrelation, scaled to its own peak
    r = rows8[rname]
    sh = (1959.65 - AX0[rname]) / 223.3
    b = np.array(r["bins"]) + sh
    c = np.array(r["counts"])
    pk = max(r["fit"])
    aa = S.ax_at(fig, xs[k], Y_A, CW, H_A)
    aa.patch.set_alpha(0)
    aa.bar(b, c / pk, width=0.0046, color=UNIT, lw=0, zorder=2)
    aa.plot(np.array(r["fit_lag"]) + sh, np.array(r["fit"]) / pk, c=S.INK, lw=1.3, zorder=3)
    aa.set_xlim(0, 1); aa.set_ylim(-0.13, 1.25)
    aa.spines["bottom"].set_bounds(0, 1)
    aa.set_xticks([0, 0.5, 1]); aa.set_xticklabels(["0", "0.5", "1"])
    if lit:                                    # where the peaks fall if the bursts follow the light: every 1/f s
        per = np.arange(1, int(hz) + 1) / hz
        aa.plot(per[per <= 1.0], np.full((per <= 1.0).sum(), -0.065), "^", ms=5.2, mfc=LIGHT, mec="none", zorder=4, clip_on=False)
    if k == 0:
        aa.set_yticks([0, 0.5, 1]); aa.set_ylabel("Spikes (scaled)")
    else:
        aa.set_yticks([]); aa.spines["left"].set_visible(False)

# row names, once, on the left
for y, h, txt, col, fs, fw in ((Y_B, H_B, "Light", LIGHT, S.NOTE + 0.5, "bold"), (Y_L, H_L, "LFP", S.INK, S.LABEL, "normal")):
    S.text_at(fig, X0 - 0.32, y + h / 2, txt, ha="right", va="center", fontsize=fs, color=col, fontweight=fw, linespacing=0.95)
# v8: the unit's row is named by the cell itself: an SST cell (cells.py) glowing in the light it carries ChR2 for, its axon
# running into its own spikes
import cells as Ce  # noqa: E402
from matplotlib.patches import Circle as _Ci  # noqa: E402
cy_, cx_ = Y_K + H_K / 2 + 0.06, 0.57
for rr, al in zip(np.linspace(0.45, 0.06, 14), np.linspace(0.025, 0.06, 14)):
    bg.add_patch(_Ci((cx_, cy_), rr, fc=LIGHT, ec="none", alpha=al, zorder=1))
u_ = 0.071
Ce.sst(bg, Ce.frame((cx_, cy_), (0, -u_), (u_, 0)), z=3, spine_lw=0.4)
Ce.axon(bg, [(cx_ + 0.03, cy_ + 0.05), (cx_ + 0.2, cy_ + 0.14), (cx_ + 0.42, cy_ + 0.15), (X0 - 0.13, cy_ + 0.08)], UNIT, lw=0.9, z=2)
S.text_at(fig, cx_, Y_K + H_K + 0.13, "SST unit", ha="center", va="top", fontsize=S.NOTE + 0.5, color=UNIT_DARK, fontweight="bold")
S.text_at(fig, (xs[0] + XR) / 2, Y_A + H_A + 0.42, "Lag between spikes (s)", fontsize=S.LABEL, color=S.INK, ha="center")
bg.plot(XR - 1.66, Y_A + H_A + 0.56, "^", ms=6.5, mfc=LIGHT, mec="none")
S.text_at(fig, XR - 1.55, Y_A + H_A + 0.45, "every light period", fontsize=S.SMALL + 0.5, color=S.SOFT, ha="left")
cax = S.ax_at(fig, XR + 0.2, Y_S + 0.12, 0.11, H_S - 0.24)
cb = fig.colorbar(im_spec, cax=cax)
cb.set_ticks([120, 150, 180]); cb.ax.tick_params(labelsize=S.SMALL, length=2.5, pad=2)
cb.outline.set_visible(False)
S.text_at(fig, XR + 0.255, Y_S - 0.1, "dB", fontsize=S.NOTE, color=S.INK, ha="center")
# v10 (the user, on v9's arrows: "Idk if I like the arrows... see if you can improve it"): no arrows. Each summary is
# named with a small copy of the row it summarises, drawn as that row is: the unit's spikes (amber ticks) before "Firing
# rate", its spike autocorrelation (amber peaks under their fitted curve) before "Rhythm strength". The two panels share
# their light axis and fill the right-hand column top to bottom: the rate panel ends level with the spikes' row, the
# rhythm panel with the autocorrelation's.
SX, SW = 13.2, 1.7
ra = summary(fig, SX, 0.72, SW, Y_K + H_K - 0.72, D8["rate_hz"], (0, 12.5), [0, 5, 10], "Firing rate",
             "spikes/s, mean of each run", xlabel=False, ty=Y_H + 0.04)
rb = summary(fig, SX, Y_A + 0.42, SW, H_A - 0.42, [p / 1000 for p in D8["power_printed"]], (0, 8.2), [0, 4, 8],
             "Rhythm strength", "power at the light frequency", ty=Y_A - 0.24)
rb.text(0.03, 0.99, "×1000", transform=rb.transAxes, ha="left", va="top", fontsize=S.SMALL, color=S.SOFT)
gx = SX - 0.68                                      # the glyphs: the rows themselves, in miniature
rng_ = np.random.default_rng(4)
tk = np.sort(rng_.uniform(0, 0.4, 9))
for t_ in tk:
    bg.plot([gx + t_, gx + t_], [Y_H + 0.07, Y_H + 0.27], c=UNIT, lw=1.3, solid_capstyle="butt")
lag = np.linspace(0, 0.42, 200)
ac = 0.03 + 0.97 * np.exp(-((((lag / 0.42) * 2.0) % 1.0 - 0.5) / 0.09) ** 2 / 2)          # two peaks a light period apart
ac[lag < 0.04] *= lag[lag < 0.04] / 0.04
y_b = Y_A - 0.03
bg.fill_between(gx + lag, y_b, y_b - 0.22 * ac, color=UNIT, lw=0)
bg.plot(gx + lag, y_b - 0.22 * ac, c=S.INK, lw=0.9)
S.save(fig, os.path.join(HERE, "out", "F_opto.png"))
print("F written")
