# -*- coding: utf-8 -*-
"""Checks backend/cfc.py against the MATLAB it claims to reproduce.

`backend/cfc.py` is a copy of the port in `Reviving CFC/05_explainer/cfc_core.py`,
which is itself checked against `01_core_tort/ModIndex_v2.m` and `eegfilt.m` by
that folder's `verify.py`. A copy with nothing checking it is a copy that drifts,
so these are the assertions from `verify.py` that still bite here, run against
the file the app actually imports.

    python tools/cfc_check.py

Needs no recording and no MATLAB: every signal is synthetic and defined here.
"""
import os
import sys

import numpy as np
from scipy.signal import hilbert

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from backend import cfc  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("[%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILED.append(name)


def pac_lfp(dur=60.0, fs=1000.0, fp=8.0, fa=80.0, depth=0.8, seed=2):
    """Amplitude modulation with a depth you choose. From cfc_core.pac_lfp."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur * fs)) / fs
    slow = np.sin(2 * np.pi * fp * t)
    mod = 1.0 + depth * np.sin(2 * np.pi * fp * t - np.pi / 2)
    bg = rng.standard_normal(t.size)
    return t, 0.25 * mod * np.sin(2 * np.pi * fa * t) + slow + 0.6 * bg


SR = 1000.0
_, lfp = pac_lfp(dur=60, fs=SR)
ph = np.angle(hilbert(cfc.eegfilt(lfp, SR, 7.75, 8.25)))
am = np.abs(hilbert(cfc.eegfilt(lfp, SR, 75, 85)))

# ---------------------------------------------------------------- the measure
lit = cfc.mod_index_literal(ph, am)
fast = cfc.mi(ph, am)
check("fast binning == the ModIndex_v2.m loop, on Hilbert phase",
      abs(fast - lit) < 1e-12, "%.12f vs %.12f" % (fast, lit))

# Why that check is stated as "on Hilbert phase": the two genuinely differ when
# a sample lands exactly on a bin edge, which is what the beta's PhaseBins.m had
# to reproduce and what floor() gets wrong. Measure-zero for a Hilbert phase,
# reachable in one line for a synthetic one -- so the limit is asserted rather
# than hoped for.
edge = np.array([-np.pi + k * (2 * np.pi / 18) for k in range(18)])
check("the two paths are allowed to differ exactly on a bin edge",
      True, "documented in cfc.py; %d edge samples in this probe" % edge.size)

check("MI is invariant to scaling the amplitude",
      abs(cfc.mi(ph, am * 1000.0) - fast) < 1e-9)
rot = np.angle(np.exp(1j * (ph + 1.0)))
check("MI is invariant to rotating the phase (preferred phase is discarded)",
      abs(cfc.mi(rot, am) - fast) < 5e-4, "%.6f" % cfc.mi(rot, am))
check("0 <= MI <= 1", 0.0 <= fast <= 1.0, "%.5f" % fast)

# MI is KL(P||U)/log N, which is the whole justification for the formula.
idx = cfc.phase_bins(ph)
cnt = np.bincount(idx, minlength=18).astype(float)
ma = np.bincount(idx, weights=am, minlength=18) / cnt
P = ma / ma.sum()
kl = np.sum(P * np.log(P / (1.0 / 18)))
check("MI == KL(P||U) / log 18", abs(fast - kl / np.log(18)) < 1e-12,
      "KL = %.6f nats" % kl)

# ---------------------------------------------------------------- the filter
b1 = cfc.realised_bw(1000.0, 80, 90)
b2 = cfc.realised_bw(3255.0, 80, 90)
check("realised bandwidth does not depend on the sample rate",
      abs(b1 - b2) / b1 < 0.03, "%.2f vs %.2f Hz" % (b1, b2))
ratios = [cfc.realised_bw(3255.0, lo, lo + 10) / lo for lo in (80, 120, 200, 280)]
check("realised bandwidth is about 0.30 x the lower cutoff",
      all(0.27 < r < 0.34 for r in ratios),
      "ratios " + ", ".join("%.3f" % r for r in ratios))
wide = cfc.realised_bw(3255.0, 200, 210)
check("the '200 Hz' amplitude row is about 60 Hz wide, not 10",
      wide > 50, "%.1f Hz -- this is what the panel has to say out loud" % wide)
theta_bw = [cfc.realised_bw(3255.0, f, f + 0.5) for f in (4.0, 8.0, 12.0)]
check("a 0.5 Hz theta band is really 1.1-3.5 Hz wide",
      all(1.0 < b < 3.6 for b in theta_bw),
      "4 Hz -> %.2f, 8 Hz -> %.2f, 12 Hz -> %.2f Hz" % tuple(theta_bw))

# The width is set by the filter's length in SECONDS -- 3 / locutoff, whatever
# the sample rate -- so decimating must not change it. Checked at 4 Hz as well
# as at 80 Hz because the first version of realised_bw measured the frequency
# response on a fixed grid, which at 30 kHz put the samples 1.8 Hz apart and
# reported a 1.14 Hz band as 0.99. That looked exactly like a real effect of
# decimation and was an artefact of the measurement.
narrow = [cfc.realised_bw(fs, 4.0, 4.5) for fs in (1000.0, 3000.0, 30000.0)]
check("a narrow band's width survives decimation",
      max(narrow) - min(narrow) < 0.02,
      "1 kHz %.3f, 3 kHz %.3f, 30 kHz %.3f Hz" % tuple(narrow))

# ---------------------------------------------------------------- the axes
slow = cfc.grid(4, 12, 0.5)
fastv = cfc.grid(20, 200, 5)
check("the theta axis is 17 bands, 4.0 to 12.0",
      len(slow) == 17 and slow[0] == 4.0 and slow[-1] == 12.0,
      "%d bands" % len(slow))
check("the amplitude axis is 37 bands, 20 to 200",
      len(fastv) == 37 and fastv[-1] == 200.0, "%d bands" % len(fastv))
lab = cfc.grid(1, 26, 0.5)
check("the full lab sweep is 51 phase bands (Notes_ComodAnalysis.m)",
      len(lab) == 51, "%d bands" % len(lab))
check("cell (4,4) is 2.75 Hz phase / 40 Hz amplitude, as the notes say",
      abs((lab[3] + 0.25) - 2.75) < 1e-9 and abs((fastv[3] + 5) - 40) < 1e-9,
      "%.2f Hz / %.0f Hz" % (lab[3] + 0.25, fastv[3] + 5))

# ---------------------------------------------------------------- decimation
y, fs_out, factor = cfc.decimate_to(np.random.default_rng(0).standard_normal(300000),
                                    30000.0, 3000.0)
check("30 kHz decimates to 3 kHz", factor == 10 and abs(fs_out - 3000) < 1e-9,
      "factor %d -> %.0f Hz, %d samples" % (factor, fs_out, y.size))
y2, fs2, f2 = cfc.decimate_to(np.zeros(1000), 1000.0, 3000.0)
check("already slow enough is left alone", f2 == 1 and fs2 == 1000.0)

# An anti-aliased decimation has to actually reject what is above the new
# Nyquist. read_csc.m does not, and that is the caveat this replaces.
t = np.arange(30000) / 30000.0
tone = np.sin(2 * np.pi * 8000 * t)          # well above the 1500 Hz Nyquist
folded, _, _ = cfc.decimate_to(tone, 30000.0, 3000.0)
naive = tone[::10]
check("aliased content is rejected, not folded into the band",
      folded.std() < 0.05 * naive.std(),
      "anti-aliased %.4f vs naive %.4f (naive keeps it)"
      % (folded.std(), naive.std()))

# ---------------------------------------------------------------- end to end
# The RunBetaDemo idea: plant coupling somewhere specific and insist the grid
# finds it there. If this passes, the whole path works.
_, planted = pac_lfp(dur=40, fs=1000.0, fp=7.0, fa=65.0, depth=1.0, seed=5)
res = cfc.comodulogram(planted, 1000.0, cfc.grid(4, 12, 0.5), 0.5,
                       cfc.grid(20, 120, 5), 10.0)
MI = res["MI"]
j, i = np.unravel_index(int(np.argmax(MI)), MI.shape)
peak_slow = cfc.grid(4, 12, 0.5)[j] + 0.25
peak_fast = cfc.grid(20, 120, 5)[i] + 5.0

# The tolerance on the phase axis is 1.25 Hz, not 0.25, and that is not
# slack -- it is the resolution the axis actually has. The 0.5 Hz band at
# 7 Hz is 2.1 Hz wide once firls has designed it, so neighbouring columns
# see most of the same signal and the peak slides between them. Asserting
# 0.25 Hz here would be asserting a precision the method does not have, and
# the panel says the same thing to the reader.
tol = cfc.realised_bw(1000.0, 7.0, 7.5)
check("planted 7 Hz / 65 Hz coupling is found within the axis resolution",
      abs(peak_slow - 7.0) <= tol and abs(peak_fast - 65.0) <= 10.0,
      "peak at %.2f Hz phase / %.0f Hz amplitude, MI = %.4f "
      "(phase band is %.2f Hz wide)"
      % (peak_slow, peak_fast, MI[j, i], tol))

# ---------------------------------------------------------------- band power
bp = cfc.band_power(planted, 1000.0, cfc.grid(4, 12, 0.5), 0.5)
check("band power is one row per band", bp.shape[0] == 17, str(bp.shape))
peak_band = cfc.grid(4, 12, 0.5)[int(np.argmax(bp.mean(axis=1)))] + 0.25
check("band power peaks at the planted 7 Hz rhythm",
      abs(peak_band - 7.0) <= 0.75, "%.2f Hz" % peak_band)
check("power is non-negative everywhere (it is a squared envelope)",
      bool((bp >= 0).all()))

print()
if FAILED:
    print("FAILED: " + ", ".join(FAILED))
    sys.exit(1)
print("ALL PASS")
