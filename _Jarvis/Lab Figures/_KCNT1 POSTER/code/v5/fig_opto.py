"""Figures F and G (poster v5): one light-driven SST interneuron, redrawn from the numbers in Dylan Marchand's 2024 poster
(FinalKcnt1_Dylan 1.pdf, Figs. 7 and 8; data/opto_fig7.npz and data/opto_fig8.json from opto_extract.py, opto_tiles.py,
opto_extract8.py and opto_rates2.py).
F: LFP, spectrogram and the unit's spikes at baseline and with 5, 7 and 12 Hz light; on the right, its firing rate per run.
G: the unit's spike autocorrelation under the same four conditions; on the right, the rhythmic power at the light frequency.
The four condition columns sit at the same x in F and G."""
import os, json
import numpy as np
import style as S
import hpc

HERE = os.path.dirname(os.path.abspath(__file__))
D7 = np.load(os.path.join(HERE, "data", "opto_fig7.npz"), allow_pickle=True)
D8 = json.load(open(os.path.join(HERE, "data", "opto_fig8.json")))
UNIT, UNIT_DARK = hpc.UNIT, "#9A6C00"
LIGHT = "#2F86D6"                      # blue light (ChR2): every light cue on the poster
COLS = [("Baseline", "Baseline", "Baseline"), ("5 Hz A", "5 Hz light", "5 Hz (run 1)"),
        ("7 Hz", "7 Hz light", "7 Hz"), ("12 Hz A", "12 Hz light", "12 Hz")]
X0, CW, CG = 0.98, 2.47, 0.3
xs = [X0 + k * (CW + CG) for k in range(4)]
XR = xs[3] + CW                        # right edge of the four columns
SPEC_V = (112, 180)
YLIM = (-1700, 950)
RUNS = [("Baseline", 0), ("5 Hz (run 1)", 1), ("5 Hz (run 2)", 1), ("7 Hz", 2), ("10 Hz (run 1)", 3), ("10 Hz (run 2)", 3), ("12 Hz", 4)]


def summary(fig, x, y, w, h, vals, ylabel, ylim, yticks, title, note):
    ax = S.ax_at(fig, x, y, w, h)
    jit = np.array([0, -0.13, 0.13, 0, -0.13, 0.13, 0])
    means = [np.mean([v for (n, p), v in zip(RUNS, vals) if p == q]) for q in range(5)]
    ax.plot(range(5), means, c=S.SOFT, lw=1.4, zorder=2)
    for (n, p), v, j in zip(RUNS, vals, jit):
        ax.plot(p + j, v, "o", ms=7.5, mfc=S.GENO["WT"] if p == 0 else UNIT, mec="white", mew=0.9, zorder=3)
    ax.set_xticks(range(5)); ax.set_xticklabels(["Base", "5", "7", "10", "12"])
    ax.set_xlim(-0.45, 4.45); ax.set_ylim(*ylim); ax.set_yticks(yticks)
    ax.set_xlabel("Light (Hz)", labelpad=2)
    ax.set_ylabel(ylabel)
    S.text_at(fig, x - 0.62, y - 0.5, title, fontsize=S.LABEL, fontweight="bold", color=S.INK)
    S.text_at(fig, x - 0.62, y - 0.24, note, fontsize=S.SMALL, color=S.SOFT)
    return ax


# ======================================================================== F
fig = S.figure(15.0, 3.75)
Y_T, Y_L, H_L, Y_S, H_S, Y_K, H_K = 0.0, 0.5, 0.92, 1.48, 1.42, 2.98, 0.34
for k, (key, title, _) in enumerate(COLS):
    lit = k > 0
    S.text_at(fig, xs[k], Y_T, title, fontsize=S.TITLE, fontweight="bold", color=LIGHT if lit else S.INK)
    if not lit:
        S.text_at(fig, xs[k] + 0.92, Y_T + 0.03, "no light", fontsize=S.NOTE, color=S.SOFT)
    e = D7[key + "|spec_extent"]
    t_a, t_b = float(e[0]), float(e[1])                 # the spectrogram's span; every row is cut to it
    span = t_b - t_a
    if lit:                                              # the light train, on for the whole window
        la = S.ax_at(fig, xs[k], Y_L - 0.16, CW, 0.065)
        la.axhspan(0, 1, color=LIGHT, lw=0); la.set_xlim(0, 1); S.bare(la)
    # LFP: the PDF's own drawn trace (min/max envelope)
    a = S.ax_at(fig, xs[k], Y_L, CW, H_L)
    t, lo, hi = D7[key + "|env_t"], D7[key + "|env_lo"], D7[key + "|env_hi"]
    m = (t >= t_a) & (t <= t_b) & np.isfinite(lo)
    a.fill_between(t[m] - t_a, lo[m], hi[m], color=S.INK, lw=0.35, edgecolor=S.INK)
    a.set_xlim(0, span); a.set_ylim(*YLIM); S.bare(a)
    if k == 0:
        a.text(-0.12, 0.5, "LFP", transform=a.transAxes, ha="right", va="center", fontsize=S.LABEL, color=S.INK)
    if k == 3:
        a.plot([span + 0.18, span + 0.18], [250, 750], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
        a.text(span + 0.3, 500, "0.5 mV", ha="left", va="center", fontsize=S.NOTE, color=S.INK)
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
    if k == 0:
        ka.text(-0.12, 0.5, "SST\nunit", transform=ka.transAxes, ha="right", va="center", fontsize=S.NOTE, color=UNIT_DARK,
                fontweight="bold", linespacing=0.95)
        ka.plot([0, 1], [-0.3, -0.3], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
        ka.text(0.5, -0.4, "1 s", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
    ka.text(span, -0.14, "%.1f spikes/s" % (len(sp) / span), ha="right", va="top", fontsize=S.SMALL, color=S.SOFT)
cax = S.ax_at(fig, XR + 0.14, Y_S + 0.12, 0.11, H_S - 0.24)
cb = fig.colorbar(im_spec, cax=cax)
cb.set_ticks([120, 150, 180]); cb.ax.tick_params(labelsize=S.SMALL, length=2.5, pad=2)
cb.outline.set_visible(False)
S.text_at(fig, XR + 0.195, Y_S - 0.1, "dB", fontsize=S.NOTE, color=S.INK, ha="center")
summary(fig, 13.12, 0.9, 1.78, 2.0, D8["rate_hz"], "Spikes/s", (0, 12.5), [0, 5, 10], "Firing rate",
        "every run (two at 5 and 10 Hz)")
S.save(fig, os.path.join(HERE, "out", "F_opto.png"))

# ======================================================================== G
fig = S.figure(15.0, 2.9)
rows = {r["name"]: r for r in D8["rows"]}
AX0 = {"Baseline": 1961.6, "5 Hz (run 1)": 1958.8, "7 Hz": 1958.8, "12 Hz": 1958.6}
Y_A, H_A = 0.36, 1.78
for k, (key, title, rname) in enumerate(COLS):
    r = rows[rname]
    sh = (1959.65 - AX0[rname]) / 223.3           # each row against its own axes box, not the bottom row's labels
    b = np.array(r["bins"]) + sh
    c = np.array(r["counts"])
    pk = max(r["fit"])
    a = S.ax_at(fig, xs[k], Y_A, CW, H_A)
    a.bar(b, c / pk, width=0.0046, color=UNIT, lw=0, zorder=2)
    a.plot(np.array(r["fit_lag"]) + sh, np.array(r["fit"]) / pk, c=S.INK, lw=1.3, zorder=3)
    a.set_xlim(0, 1); a.set_ylim(0, 1.32)
    a.set_xticks([0, 0.5, 1]); a.set_xticklabels(["0", "0.5", "1"])
    if k == 0:
        a.set_yticks([0, 0.5, 1]); a.set_ylabel("Spikes (scaled)")
    else:
        a.set_yticks([]); a.spines["left"].set_visible(False)
    lab = "bursts, no rhythm" if k == 0 else "rhythm at %.1f Hz" % r["peak_hz"]
    a.text(0.98, 1.0, lab, transform=a.transAxes, ha="right", va="top", fontsize=S.NOTE, color=S.SOFT if k == 0 else LIGHT,
           fontweight="bold")
    S.text_at(fig, xs[k], Y_A - 0.32, title, fontsize=S.LABEL, fontweight="bold", color=LIGHT if k else S.INK)
S.text_at(fig, (xs[0] + XR) / 2, Y_A + H_A + 0.32, "Lag between spikes (s)", fontsize=S.LABEL, color=S.INK, ha="center")
summary(fig, 13.12, 0.72, 1.78, 1.42, [p / 1000 for p in D8["power_printed"]], "Power (×1000)", (0, 8.2), [0, 4, 8],
        "Rhythm strength", "power at the light frequency")
S.save(fig, os.path.join(HERE, "out", "G_entrain.png"))
print("F, G written")
