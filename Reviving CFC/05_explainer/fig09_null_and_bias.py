"""FIG 9 — MI is biased upward and has no fixed zero, so it needs a null.

Two separate problems:

(1) FINITE-SAMPLE BIAS. With a finite recording the 18 bin means are never
    exactly equal, so MI > 0 even with no coupling at all, and the bias
    shrinks roughly as 1/N. Two recordings of different length are not
    directly comparable.

(2) NO REFERENCE SCALE. "MI = 0.004" means nothing on its own. The usual
    fix is a surrogate distribution: shift the amplitude series against the
    phase series, recompute, repeat, and express the observed MI as a
    z-score against that null.
"""
import numpy as np, matplotlib.pyplot as plt
from scipy.signal import hilbert
import cfc_core as c
from style import *

SR = 1000.0


def pair(lfp, fp=8.0, fa=80.0):
    ph = np.angle(hilbert(c.eegfilt(lfp, SR, fp - 0.25, fp + 0.25)[0]))
    am = np.abs(hilbert(c.eegfilt(lfp, SR, fa - 5, fa + 5)[0]))
    return ph, am


def build():
    durs = np.array([2.5, 5, 10, 20, 40, 80, 160, 320])
    bias = []
    for d in durs:
        lfp = c.pink_noise(int(d * SR), SR, seed=5)
        bias.append(c.mi_fast(*pair(lfp)))
    _, lfp_p = c.pac_lfp_natural(dur=120, srate=SR, fp=8, fa=80, depth=0.06,
                                 slow_amp=1, fast_amp=0.45, noise=0.6, seed=3)
    lfp_n = c.pink_noise(int(120 * SR), SR, seed=5)
    php, amp_ = pair(lfp_p); phn, amn = pair(lfp_n)
    s_p = c.surrogate_mi(php, amp_, 400, SR, seed=1)
    s_n = c.surrogate_mi(phn, amn, 400, SR, seed=1)
    return (durs, np.array(bias), s_p, s_n,
            np.array([c.mi_fast(php, amp_), c.mi_fast(phn, amn)]))


durs, bias, s_p, s_n, obs = c.cached("null_and_bias", build)

fig, (a0, a1) = plt.subplots(1, 2, figsize=(9.2, 3.3))

a0.loglog(durs, bias, "-o", color=C[0], ms=5, label="MI of pure pink noise")
a0.loglog(durs, bias[-1] * durs[-1] / durs, ls="--", color=MUTED, lw=1.2,
          label="1/N reference slope")
a0.set_xlabel("epoch length (s)   at 1000 Hz"); a0.set_ylabel("MI with no coupling present")
a0.set_title("the floor is not zero, and it moves with N")
a0.legend(loc="upper right"); a0.grid(which="both")
for d, b in zip(durs, bias):
    if d in (5, 320):
        a0.annotate(f"{b:.5f}", (d, b), textcoords="offset points",
                    xytext=(6, 6), fontsize=7.5, color=INK2)
tag(a0, "a")

ymax = 0
for s_, o, col, lab in [(s_n, obs[1], MUTED, "no coupling"),
                        (s_p, obs[0], C[0], "weak real coupling")]:
    n_, _, _ = a1.hist(s_, bins=40, color=col, alpha=0.6,
                       label=f"{lab}: surrogate null")
    ymax = max(ymax, n_.max())
for s_, o, col, ha, dx in [(s_n, obs[1], INK, "left", 6), (s_p, obs[0], C[0], "right", -6)]:
    z = (o - s_.mean()) / s_.std()
    a1.axvline(o, color=col, lw=2)
    a1.annotate(f"observed\nz = {z:+.1f}", (o, ymax * 1.02), textcoords="offset points",
                xytext=(dx, 0), fontsize=8, color=col, fontweight="600", ha=ha, va="top")
a1.set_ylim(0, ymax * 1.28)
a1.set_xlabel("MI"); a1.set_ylabel("surrogates")
a1.set_title("400 shifted surrogates, same recording", fontsize=9.5)
a1.legend(loc="upper center", fontsize=7.5)
tag(a1, "b")
note(fig, "The pipeline in this repo stores raw MI and the R readers average raw MI across bands. That is fine for\n"
          "a within-session comparison of equal-length epochs and misleading otherwise: match epoch length across\n"
          "groups, or convert to a z-score against a per-channel surrogate null before any group statistic.", y=-0.02)
plt.tight_layout()
plt.savefig("figures/fig09_null_and_bias.png", bbox_inches="tight", dpi=170)
print("fig09 done", obs, bias[0], bias[-1])
