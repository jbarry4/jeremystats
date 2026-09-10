"""
cfc.py -- Phase-amplitude coupling for one window of one channel.

Everywhere else in the GUI a panel answers "what does this look like". This
answers "is the amplitude of the fast oscillation tied to the phase of the slow
one, here, in the window on screen" -- which is the question the MATLAB beta run
in `Reviving CFC/Revival Pipeline` answers for a whole channel, offline, in
minutes. That run is still the one to cite. This is the one you can afford to
point at a window and wait for.

WHERE THE ARITHMETIC COMES FROM
-------------------------------
Ported from `Reviving CFC/05_explainer/cfc_core.py`, which is itself a checked
port of the MATLAB that actually ran:

    01_core_tort/eegfilt.m            -> eegfilt()      (EEGLAB firls + filtfilt)
    01_core_tort/ModIndex_v2.m        -> mod_index()    (Tort normalised entropy)
    03_vacc_pipeline/step04_newFCSE.m -> comodulogram()
    Revival Pipeline/code/ThetaPower.m -> band_power()
    Revival Pipeline/code/CFC.m       -> the surrogate loop

Copied rather than imported. `Reviving CFC/` is a sibling of `BARRY GUI/` and a
clone that carries only the app has to work; an import across that boundary
would make the Toolkit fail at start-up on a machine where somebody moved a
folder. `tools/cfc_check.py` re-runs the assertions from the explainer's
`verify.py` against THIS file, so the copy cannot drift quietly.

TWO PLACES THIS DELIBERATELY DIFFERS FROM THE MATLAB
----------------------------------------------------
**Binning.** `ModIndex_v2.m` finds bin membership with literal comparisons,
`Phase >= position(j) & Phase < position(j) + winsize`, and `PhaseBins.m` had to
reproduce that exactly because gate 4 asserts at 1e-12. The upper edge is
recomputed per bin and is not bit-identical to the next bin's lower edge, so a
sample landing exactly on an edge can be counted twice or not at all. That is
what `floor((phase + pi) / winsize)` gets wrong.

Here the phase always comes out of a Hilbert transform, where landing exactly on
a bin edge is measure-zero, and the floor is one pass of `bincount` instead of
18 boolean masks. `mod_index_literal()` is kept for the check script, which
asserts the two agree on Hilbert phase.

**Decimation.** `read_csc.m` decimates with `Samples(1:10:end)` and no
anti-alias filter, so content above the new Nyquist folds into the 20-200 Hz
amplitude axis -- a caveat the beta's README calls a real risk and flags for a
decision. This uses `scipy.signal.decimate`, which low-passes first. The numbers
here are therefore better than the legacy pipeline's and NOT bit-comparable with
`newFCSE` output. Every panel and every caption says which was used.

SIGNIFICANCE
------------
Report `p`, not `z`. The beta measured the surrogate null to be centred (mean
rank quantile 0.489 against an ideal 0.500) but over-dispersed, `SD(z) ~= 1.4`,
and it does not shrink as surrogates are added -- structural, not sampling
noise. A circular shift of a narrowband phase series mostly rotates the
preferred phase rather than destroying the coupling. So a nominal |z| > 3
behaves like |z| > 2.2-2.6. The permutation p, (1 + #{surr >= obs}) / (nSurr + 1),
is valid whatever the dispersion and measured well calibrated at 5.30% of null
cells under 0.05. `z` is kept because it makes a better picture.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import uuid

import numpy as np
from scipy.signal import decimate, filtfilt, firls, freqz, hilbert

# --------------------------------------------------------------------------
# eegfilt.m
# --------------------------------------------------------------------------
MINFAC = 3            # this many cycles of the low cutoff in the filter
MIN_FILTORDER = 15
TRANS = 0.15          # fractional width of the transition zones
NBIN = 18             # 20 degree phase bins, the Tort convention

# The reference grid, from `Reviving CFC/01_core_tort/CallerRoutine.m`:
#
#     PhaseFreqVector = 2:2:50;      PhaseFreq_BandWidth = 4;
#     AmpFreqVector   = 10:5:200;    AmpFreq_BandWidth   = 10;
#
# Low edge, top edge, step -- the band runs UPWARD from each vector value
# (`Pf2 = Pf1 + BandWidth`), so both axes overlap themselves by half and the
# figure is labelled at the centres. 25 x 39 = 975 cells.
TORT_PHASE = (2.0, 50.0, 2.0)
TORT_PHASE_BW = 4.0
TORT_AMP = (10.0, 200.0, 5.0)
TORT_AMP_BW = 10.0


def eegfilt_order(fs, locutoff):
    """The order eegfilt.m picks for you: 3 * fix(fs / locutoff)."""
    return max(MINFAC * int(fs // max(locutoff, 1e-9)), MIN_FILTORDER)


# What one filter design may cost, in bytes.
#
# `firls` solves a least-squares system whose size is the filter order, so it
# allocates order^2 float64s -- and the order is `3 * fix(fs / locutoff)`,
# which grows without limit as the band goes down. A `0.05` typed where `5`
# was meant is 90000 taps at 3 kHz and a 60.3 GiB allocation, reported to the
# browser as numpy's complaint about an array shape.
#
# 1 GiB is an order of about 11585, which is far above anything real: 2250
# taps for a 4 Hz band at 3 kHz, 9000 for 1 Hz delta.
MAX_DESIGN_BYTES = 1 << 30


def design_limit(fs):
    """The lowest band edge `fs` can afford a filter for, in Hz."""
    import math
    max_order = math.sqrt(MAX_DESIGN_BYTES / 8.0)
    return MINFAC * float(fs) / max_order


def check_designable(fs, locutoff):
    """Refuse an impossible filter in words, before numpy is asked for it.

    Raised rather than clamped: a band edge quietly moved from 0.05 to 0.8 Hz
    would answer a question nobody asked, and the number in the field is the
    thing that is wrong.
    """
    order = eegfilt_order(fs, locutoff)
    cost = 8.0 * order * order
    if cost <= MAX_DESIGN_BYTES:
        return
    raise ValueError(
        "A %g Hz band needs a %d-tap filter at %g Hz (eegfilt uses "
        "3*fix(fs/locutoff)), and designing one means solving a %d by %d "
        "least-squares system -- %.1f GiB. It would also need %.0f s of "
        "recording to run at all. The lowest band edge this rate can afford "
        "is %.2f Hz; raise the bottom of the band range."
        % (locutoff, order, fs, order, order, cost / (1 << 30),
           needed_seconds(locutoff), design_limit(fs)))


def eegfilt_response(fs, locutoff, hicutoff):
    """The piecewise-linear target handed to firls, in Hz."""
    nyq = fs * 0.5
    f = np.array([0.0, (1 - TRANS) * locutoff, locutoff,
                  hicutoff, (1 + TRANS) * hicutoff, nyq])
    m = np.array([0.0, 0.0, 1.0, 1.0, 0.0, 0.0])
    return f, m


def eegfilt_taps(fs, locutoff, hicutoff):
    """The FIR coefficients. Separated out so realised_bw can reuse them.

    Memoised, and it matters more than it sounds. `firls` solves a
    least-squares system whose size is the filter order, and the order here is
    `3 * fix(fs / locutoff)` -- 2251 taps for a 4 Hz band at 3 kHz. Measured at
    51 ms each, which is 0.87 s of a 1.7 s panel render spent designing the
    same seventeen filters that were designed for the previous window, and the
    one before that. The taps depend on nothing but these three numbers.
    """
    key = (round(float(fs), 6), round(float(locutoff), 6),
           round(float(hicutoff), 6))
    got = _TAP_MEMO.get(key)
    if got is not None:
        return got

    check_designable(fs, locutoff)
    order = eegfilt_order(fs, locutoff)
    if order % 2:
        order += 1                      # firls wants an odd number of taps
    f, m = eegfilt_response(fs, locutoff, hicutoff)
    b = firls(order + 1, list(f), m, fs=fs)

    # A few hundred bands' worth. Each is a few tens of kB and the axes only
    # ever hold a few dozen distinct bands, so this settles almost at once.
    if len(_TAP_MEMO) > 256:
        _TAP_MEMO.clear()
    _TAP_MEMO[key] = b
    return b


_TAP_MEMO = {}


def eegfilt(x, fs, locutoff, hicutoff):
    """Zero-phase FIR bandpass, as eegfilt.m does it.

    Zero phase is not a nicety here. The whole measure is about phase, so a
    filter that shifted it would be measuring its own delay.
    """
    return filtfilt(eegfilt_taps(fs, locutoff, hicutoff), [1.0], x)


def needed_seconds(locutoff, margin=1.15):
    """How much signal `eegfilt` needs at its lowest band, in seconds.

    `filtfilt` refuses to run on anything shorter than `3 * ntaps`, and
    eegfilt's tap count is `3 * fix(fs / locutoff)` -- so the requirement is
    `9 / locutoff` SECONDS, independent of the sample rate, because the taps
    scale with it. At 4 Hz that is 2.25 s of signal to produce any output at
    all, whatever window you asked to look at.

    This exists because the first version padded a short window by an amount
    capped at the window's own length, which is exactly backwards: padding
    matters most when the window is small. A 0.25 s window came out three
    samples short of the requirement and scipy raised "The length of the
    input vector x must be greater than padlen" -- a 400 with a message about
    vectors, for a question about a quarter-second of recording.
    """
    return margin * 9.0 / max(float(locutoff), 0.05)


def edge_seconds(locutoff):
    """How far the filter's own transient reaches into each end, in seconds.

    One filter length, and filtfilt runs it both ways, so this much at each
    end of the read is ringing rather than signal and gets cut off again.
    """
    return 3.0 / max(float(locutoff), 0.05)


def realised_bw(fs, locutoff, hicutoff):
    """The half-power width the filter ACTUALLY has, in Hz.

    Not the nominal width. `firls` is handed a trapezoid with 15% ramps and an
    order tied to the low cutoff, and what comes out is about 0.30 * locutoff
    wide however narrow you asked for -- the explainer measures a nominal 10 Hz
    band at 200 Hz coming out roughly 60 Hz wide.

    This is the single most misleading thing about a comodulogram axis, so the
    panels print it. A row labelled "200 Hz" is not a 10 Hz slice of the
    spectrum and nothing on a normal plot says so.
    """
    key = (round(float(fs), 3), round(float(locutoff), 4),
           round(float(hicutoff), 4))
    got = _BW_MEMO.get(key)
    if got is not None:
        return got

    # Resolution matters more than it looks. A theta band is about 1-3 Hz
    # wide, and a fixed 8192-point grid at 30 kHz puts the frequency samples
    # 1.8 Hz apart -- so the first version of this measured a 1.16 Hz band as
    # 0.99 Hz and made the width look sample-rate dependent when it is not.
    # Enough points that the grid step is a twentieth of the width we expect.
    nyq = fs * 0.5
    expect = max(0.30 * locutoff, 0.1)
    worN = int(min(max(nyq / (expect / 20.0), 8192), 262144))

    b = eegfilt_taps(fs, locutoff, hicutoff)
    w, h = freqz(b, worN=worN, fs=fs)
    power = np.abs(h) ** 2
    peak = power.max()
    if not (peak > 0):
        return float("nan")
    over = np.flatnonzero(power >= peak / 2.0)
    if over.size < 2:
        return float("nan")
    out = float(w[over[-1]] - w[over[0]])
    # Bounded, because this is called once per band on every panel render and
    # the axes only ever hold a few dozen distinct bands.
    if len(_BW_MEMO) > 4096:
        _BW_MEMO.clear()
    _BW_MEMO[key] = out
    return out


_BW_MEMO = {}


# --------------------------------------------------------------------------
# ModIndex_v2.m
# --------------------------------------------------------------------------
def mod_index_literal(phase, amp, nbin=NBIN):
    """The ModIndex_v2.m loop, comparison for comparison.

    Only the check script calls this. It is here so the fast path has something
    to be checked against inside the app, rather than in a folder the app is not
    allowed to depend on.
    """
    winsize = 2 * np.pi / nbin
    position = -np.pi + np.arange(nbin) * winsize
    ma = np.empty(nbin)
    for j, left in enumerate(position):
        sel = (phase >= left) & (phase < left + winsize)
        ma[j] = amp[sel].mean() if sel.any() else np.nan
    p = ma / ma.sum()
    return (np.log(nbin) + np.sum(p * np.log(p))) / np.log(nbin)


def phase_bins(phase, nbin=NBIN):
    """Which bin each sample falls in. One pass, reused by every fast band."""
    idx = np.floor((phase + np.pi) * (nbin / (2 * np.pi))).astype(np.int64)
    np.clip(idx, 0, nbin - 1, out=idx)
    return idx


def _mi_from_bins(idx, counts, amp_rows, nbin=NBIN):
    """Modulation index of every amplitude row against one binned phase.

    The loop is over rows rather than vectorised into a matrix product because
    `bincount` with weights is already one pass over the samples, and the
    product would need a dense nSamp x nbin that is far larger than the data.
    """
    out = np.empty(amp_rows.shape[0], dtype=np.float64)
    logn = np.log(nbin)
    for i in range(amp_rows.shape[0]):
        ma = np.bincount(idx, weights=amp_rows[i], minlength=nbin) / counts
        total = ma.sum()
        if not (total > 0):
            out[i] = 0.0
            continue
        p = ma / total
        # An empty bin contributes nothing to the entropy. It cannot happen
        # with Hilbert phase over a window worth analysing, but a two-cycle
        # window would make a nan out of an otherwise fine number.
        nz = p > 0
        out[i] = (logn + np.sum(p[nz] * np.log(p[nz]))) / logn
    return out


def mi(phase, amp, nbin=NBIN):
    """One modulation index. Convenience; the grid does not go through here."""
    idx = phase_bins(phase, nbin)
    counts = np.bincount(idx, minlength=nbin).astype(float)
    counts[counts == 0] = np.nan
    return float(_mi_from_bins(idx, counts, np.atleast_2d(amp), nbin)[0])


# --------------------------------------------------------------------------
# Getting the samples to a rate the analysis can afford
# --------------------------------------------------------------------------
def decimate_to(x, fs, target_fs):
    """Anti-aliased decimation to at or just above `target_fs`.

    Returns (y, fs_out, factor). A factor of 1 means it was already slow
    enough and nothing was done.

    Neuralynx here runs at 30 kHz. A 60 s window is 1.8 million samples, and
    filtering 54 bands of that costs ten times what it costs at 3 kHz for
    nothing: the top of the amplitude axis is 210 Hz, so anything above about
    1 kHz is headroom nobody is using.
    """
    fs = float(fs)
    if target_fs <= 0 or fs <= target_fs:
        return np.asarray(x, dtype=np.float64), fs, 1
    factor = int(fs // target_fs)
    if factor < 2:
        return np.asarray(x, dtype=np.float64), fs, 1
    # scipy's IIR default is cheaper but rings; the FIR path is zero-phase and
    # this is a measurement about phase.
    y = x
    left = factor
    # Decimating by more than ~13 at a time makes a filter with a very narrow
    # transition band and poor conditioning, which is scipy's own advice.
    while left > 1:
        step = min(10, left)
        while left % step and step > 2:
            step -= 1
        y = decimate(y, step, ftype="fir", zero_phase=True)
        left //= step
    return np.asarray(y, dtype=np.float64), fs / factor, factor


# --------------------------------------------------------------------------
# ThetaPower.m
# --------------------------------------------------------------------------
def band_power(x, fs, vec, bw, job=None, stage=None):
    """Squared envelope of each narrow band. `vec` holds the LOW edges.

    This is the reason the tool exists in the shape it does. A single 4-12 Hz
    bandpass answers "how much theta" and cannot answer "which theta", and the
    second question is the one that matters when theta shifts within a session.

    Same definition as ThetaPower.m: the mean squared envelope of the same
    analytic signal whose phase would drive the modulation index. Not a
    periodogram -- one definition of the band, one set of samples, so power and
    coupling are always talking about the same thing.
    """
    vec = np.asarray(vec, dtype=float)
    out = np.empty((vec.size, np.asarray(x).size), dtype=np.float32)
    for i, f1 in enumerate(vec):
        y = eegfilt(x, fs, f1, f1 + bw)
        out[i] = np.abs(hilbert(y)) ** 2
        if job is not None:
            job.tick(stage, i + 1)
    return out


def band_table(fs, vec, bw):
    """What each band really is, for the caption. Centres and realised widths."""
    vec = np.asarray(vec, dtype=float)
    return {
        "low": [float(v) for v in vec],
        "centers": [float(v + bw / 2.0) for v in vec],
        "nominal_bw": float(bw),
        "realised_bw": [round(realised_bw(fs, float(v), float(v) + bw), 3)
                        for v in vec],
    }


# --------------------------------------------------------------------------
# The grid
# --------------------------------------------------------------------------
def comodulogram(x, fs, slow_vec, slow_bw, fast_vec, fast_bw,
                 nsurr=0, seed=42, min_shift_s=0.5, nbin=NBIN, job=None):
    """Modulation index for every (slow band, fast band) cell.

    Returns a dict with MI, and when surrogates were asked for, the null they
    were measured against and the permutation p.

    The surrogate is a circular shift of the phase bins WITHIN the window. It
    destroys the timing relationship between phase and envelope while leaving
    both signals' own statistics -- spectrum, envelope shape, any transients --
    exactly as they were. Shifting the bin index array rather than the
    amplitude block is what makes it affordable: the bins are one array of n
    integers, the amplitudes are 37 x n floats, and the two are equivalent.
    """
    slow_vec = np.asarray(slow_vec, dtype=float)
    fast_vec = np.asarray(fast_vec, dtype=float)
    n_slow, n_fast = slow_vec.size, fast_vec.size
    n = int(np.asarray(x).size)

    # ---- slow bank: phase only ----
    if job:
        job.begin("slow bank", n_slow, "bands")
    phase = np.empty((n_slow, n), dtype=np.float32)
    for j, f1 in enumerate(slow_vec):
        phase[j] = np.angle(hilbert(eegfilt(x, fs, f1, f1 + slow_bw)))
        if job:
            job.tick("slow bank", j + 1)

    # ---- fast bank: envelope only ----
    if job:
        job.begin("fast bank", n_fast, "bands")
    amp = np.empty((n_fast, n), dtype=np.float32)
    for i, f1 in enumerate(fast_vec):
        amp[i] = np.abs(hilbert(eegfilt(x, fs, f1, f1 + fast_bw)))
        if job:
            job.tick("fast bank", i + 1)

    # ---- the observed grid ----
    if job:
        job.begin("modulation index", n_slow * n_fast, "cells")
    MI = np.empty((n_slow, n_fast), dtype=np.float32)
    bins, counts = [], []
    for j in range(n_slow):
        idx = phase_bins(phase[j], nbin)
        cnt = np.bincount(idx, minlength=nbin).astype(float)
        cnt[cnt == 0] = np.nan
        bins.append(idx)
        counts.append(cnt)
        MI[j] = _mi_from_bins(idx, cnt, amp, nbin)
        if job:
            job.tick("modulation index", (j + 1) * n_fast)

    out = {
        "MI": MI,
        "n_samples": n,
        "fs": float(fs),
        "nbin": nbin,
        "nsurr": 0,
    }

    if not nsurr:
        return out

    # ---- the null ----
    if job:
        job.begin("surrogates", n_slow * nsurr, "surrogates")
    rng = np.random.default_rng(seed)
    lo = max(1, int(min_shift_s * fs))
    if n - lo <= lo:
        # A window too short for an honest shift. Saying so beats returning a
        # null built from displacements that leave the coupling intact.
        raise ValueError(
            "This window is too short for surrogates: a shift has to be at "
            "least %.2f s and the window is %.2f s. Widen the window or turn "
            "surrogates off." % (min_shift_s, n / fs))

    acc = np.zeros((n_slow, n_fast))
    acc2 = np.zeros((n_slow, n_fast))
    ge = np.zeros((n_slow, n_fast))
    for j in range(n_slow):
        idx, cnt = bins[j], counts[j]
        for k in range(nsurr):
            s = int(rng.integers(lo, n - lo))
            m = _mi_from_bins(np.roll(idx, s), cnt, amp, nbin)
            acc[j] += m
            acc2[j] += m * m
            ge[j] += (m >= MI[j])
            if job and (k % 4 == 3 or k == nsurr - 1):
                job.tick("surrogates", j * nsurr + k + 1)

    mu = acc / nsurr
    var = np.maximum(acc2 / nsurr - mu ** 2, 0.0) * (nsurr / max(nsurr - 1, 1))
    sd = np.sqrt(var)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(sd > 0, (MI - mu) / sd, np.nan)

    out.update({
        "nsurr": int(nsurr),
        "seed": int(seed),
        "surr_mean": mu.astype(np.float32),
        "surr_sd": sd.astype(np.float32),
        "z": z.astype(np.float32),
        # The one to threshold on. See the module docstring.
        "p": ((1.0 + ge) / (nsurr + 1.0)).astype(np.float32),
    })
    return out


def grid(lo, hi, step):
    """The low edges of a band axis, inclusive of `hi`.

    `arange` with a float step drops or keeps the last point depending on
    rounding, and the difference between a 37-row and a 36-row amplitude axis
    is a figure that does not line up with last year's.
    """
    n = int(round((hi - lo) / step)) + 1
    return [round(lo + i * step, 6) for i in range(max(n, 1))]


# ==========================================================================
# Jobs
#
# A comodulogram with surrogates is half a minute of arithmetic, so it cannot
# happen inside the request that asked for it. This is the smallest thing that
# runs one in a thread and can say honestly where it has got to.
#
# Shaped like runner.Job on purpose -- an id, a status, a snapshot -- so the
# client polls it the same way it polls a script run. It is not runner.Job
# because that one is built around a subprocess with a stdout to pump, and
# there is no subprocess here.
# ==========================================================================
STAGES = [
    ("read", "samples"),
    ("decimate", "samples"),
    ("slow bank", "bands"),
    ("fast bank", "bands"),
    ("modulation index", "cells"),
    ("surrogates", "surrogates"),
    ("draw", "images"),
]

# Seconds per unit, measured on the machine this was built on: a 60 s window at
# 3255 Hz over a 17 x 37 grid. Only a starting point -- `_learn` replaces each
# one with what this machine actually does, so the estimate is right by the
# second run and stays right when somebody runs it on the rig.
# Seconds per unit per MEGASAMPLE, except `draw`, which is seconds flat.
#
# Per megasample rather than per unit, because otherwise the numbers depend on
# how long the last window happened to be: one run over 10 s would divide
# every rate by six and the next estimate for a 60 s window would be six times
# too low. Measured on this machine over a 60 s window at 3 kHz (0.18
# megasamples), which is where the reference figures in the README come from.
_RATES = {
    "read": 1.2e-3,               # per sample read, per megasample
    "decimate": 6.1e-4,
    "slow bank": 0.489,           # per band, per megasample
    "fast bank": 0.272,
    "modulation index": 2.7e-3,   # per cell, per megasample
    "surrogates": 0.106,          # per (band x surrogate), per megasample
    "draw": 0.30,                 # flat: 629 cells to a PNG, whatever the window
}
# Stages whose cost does not scale with the number of samples.
_FLAT = {"draw"}
_RATES_PATH = None
_RATES_LOCK = threading.Lock()


def configure(logs_dir):
    """Where to remember how fast this machine is. Called once by app.py."""
    global _RATES_PATH
    _RATES_PATH = os.path.join(logs_dir, ".cfc_rates.json")
    try:
        with open(_RATES_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh) or {}
        for k, v in saved.items():
            if k in _RATES and isinstance(v, (int, float)) and v > 0:
                _RATES[k] = float(v)
    except (OSError, ValueError):
        pass            # first run on this machine, or the file went bad


def _learn(stage, seconds, units, msamples=1.0):
    """Fold one measurement into the rate for that stage.

    A running mean weighted towards recent runs. Not a plain average: the first
    run on a cold file cache is slower than every later one, and an estimate
    that never forgets it is wrong for ever.

    `msamples` normalises out the window length -- see the note on _RATES.
    """
    if units <= 0 or seconds <= 0:
        return
    denom = units * (1.0 if stage in _FLAT else max(msamples, 1e-6))
    with _RATES_LOCK:
        was = _RATES.get(stage)
        rate = seconds / denom
        _RATES[stage] = rate if not was else (0.7 * was + 0.3 * rate)
        if not _RATES_PATH:
            return
        try:
            tmp = "%s.%d.tmp" % (_RATES_PATH, os.getpid())
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(_RATES, fh, indent=1, sort_keys=True)
            os.replace(tmp, _RATES_PATH)
        except OSError:
            pass        # a cache of how fast we are; losing it costs nothing


class Canceled(Exception):
    """Raised out of the compute when somebody pressed Cancel."""


class Job:
    def __init__(self, spec, plan, msamples=1.0):
        """`plan` is [(stage, units)] for the stages this run will actually do.

        `msamples` is how many megasamples the run works over, which is what
        makes a rate measured on one window length usable on another.
        """
        self.id = uuid.uuid4().hex[:12]
        self.spec = spec
        self.status = "running"
        self.error = None
        self.result = None
        self.started = time.time()
        self.ended = None
        self._cancel = False
        self._lock = threading.Lock()
        units = dict(plan)
        self.stages = [
            {"name": name, "unit": unit, "of": int(units.get(name, 0)),
             "done": 0, "seconds": None, "status": "waiting",
             # Filled in as each finishes, so what actually ran in what
             # order can be read off a completed job instead of having to
             # be caught mid-flight by a fast enough poll.
             "order": None}
            for name, unit in STAGES if name in units
        ]
        self._at = None          # index of the running stage
        self._t0 = None
        self._order = 0          # how many stages have finished
        self.msamples = max(float(msamples), 1e-6)

    # -- driving it ------------------------------------------------------
    def _find(self, name):
        for i, st in enumerate(self.stages):
            if st["name"] == name:
                return i
        return None

    def begin(self, name, of=None, unit=None):
        self.check()
        with self._lock:
            i = self._find(name)
            if i is None:
                return
            self._close(time.time())
            st = self.stages[i]
            if of is not None:
                st["of"] = int(of)
            if unit:
                st["unit"] = unit
            st["status"] = "running"
            self._at = i
            self._t0 = time.time()

    def tick(self, name, done):
        self.check()
        with self._lock:
            i = self._find(name)
            if i is not None:
                self.stages[i]["done"] = int(done)

    def _close(self, now):
        """Finish whatever stage is running. Caller holds the lock."""
        if self._at is None:
            return
        st = self.stages[self._at]
        st["seconds"] = round(now - (self._t0 or now), 3)
        st["done"] = st["of"]
        st["status"] = "done"
        self._order += 1
        st["order"] = self._order
        _learn(st["name"], st["seconds"], st["of"], self.msamples)
        self._at = None

    def finish(self, result):
        with self._lock:
            self._close(time.time())
            self.result = result
            self.status = "done"
            self.ended = time.time()

    def fail(self, exc):
        with self._lock:
            if self._at is not None:
                self.stages[self._at]["status"] = "failed"
                self._at = None
            self.error = str(exc)[:400]
            self.status = "canceled" if isinstance(exc, Canceled) else "failed"
            self.ended = time.time()

    def cancel(self):
        self._cancel = True

    def check(self):
        """Called between bands and every few surrogates, so Cancel lands."""
        if self._cancel:
            raise Canceled("Stopped.")

    # -- reporting it ----------------------------------------------------
    def eta(self):
        """Seconds left, or None while we do not honestly know yet.

        Weighted by measured cost per unit rather than by stage count. On a
        100-surrogate run the surrogates are about seven eighths of the work,
        so a bar that treated seven stages as seven equal steps would sit at
        71% with nearly all the arithmetic still to do.
        """
        left = 0.0
        for i, st in enumerate(self.stages):
            if st["status"] == "done":
                continue
            rate = _RATES.get(st["name"], 0.0) * (
                1.0 if st["name"] in _FLAT else self.msamples)
            remaining = max(st["of"] - st["done"], 0)
            if i == self._at and st["done"] >= 3 and self._t0:
                # This machine, this run, this stage: better than the table.
                rate = (time.time() - self._t0) / st["done"]
            left += rate * remaining
        return round(left, 1) if left > 0 else None

    def snapshot(self):
        with self._lock:
            done_s = sum(s["seconds"] or 0 for s in self.stages)
            return {
                "id": self.id,
                "status": self.status,
                "error": self.error,
                "stages": [dict(s) for s in self.stages],
                "stage": (self.stages[self._at]["name"]
                          if self._at is not None else None),
                "elapsed": round((self.ended or time.time()) - self.started, 2),
                "eta_s": self.eta() if self.status == "running" else None,
                "spent": round(done_s, 2),
                "spec": self.spec,
            }


_JOBS = {}
_JOBS_LOCK = threading.Lock()
MAX_JOBS = 24


def get(job_id):
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def start(spec, plan, work, msamples=1.0):
    """Run `work(job)` in a thread. Returns the Job at once."""
    job = Job(spec, plan, msamples)
    with _JOBS_LOCK:
        # Oldest finished jobs first: a result somebody may still be looking at
        # is worth more than one they have forgotten.
        if len(_JOBS) >= MAX_JOBS:
            spent = sorted((j for j in _JOBS.values() if j.ended),
                           key=lambda j: j.ended)
            for old in spent[:max(1, len(_JOBS) - MAX_JOBS + 1)]:
                _JOBS.pop(old.id, None)
        _JOBS[job.id] = job

    def go():
        try:
            job.finish(work(job))
        except Exception as exc:                     # noqa: BLE001
            job.fail(exc)

    threading.Thread(target=go, daemon=True,
                     name="barry-cfc-" + job.id).start()
    return job


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
# Comparing two windows means going back and forth between them, and paying
# thirty seconds again for a map already made is the difference between a tool
# somebody uses and one they use once.
_CACHE = {}
_CACHE_ORDER = []
_CACHE_LOCK = threading.Lock()
CACHE_MAX = 12


def cache_key(spec):
    """Everything that changes the numbers, and nothing that does not."""
    keep = {k: spec.get(k) for k in (
        "path", "channel", "t0", "t1", "slow_lo", "slow_hi", "slow_step",
        "slow_bw", "fast_lo", "fast_hi", "fast_step", "fast_bw", "nsurr",
        "seed", "target_fs", "nbin", "highpass", "lowpass", "notch")}
    blob = json.dumps(keep, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def cache_get(key):
    with _CACHE_LOCK:
        return _CACHE.get(key)


def cache_put(key, value):
    with _CACHE_LOCK:
        if key not in _CACHE:
            _CACHE_ORDER.append(key)
        _CACHE[key] = value
        while len(_CACHE_ORDER) > CACHE_MAX:
            _CACHE.pop(_CACHE_ORDER.pop(0), None)


def cache_clear():
    with _CACHE_LOCK:
        _CACHE.clear()
        del _CACHE_ORDER[:]


def estimate(spec):
    """What this run is likely to cost, before committing to it.

    Shown next to the surrogate checkbox. An honest number there is what makes
    turning surrogates on a decision rather than a surprise.
    """
    n_slow = len(grid(spec["slow_lo"], spec["slow_hi"], spec["slow_step"]))
    n_fast = len(grid(spec["fast_lo"], spec["fast_hi"], spec["fast_step"]))
    nsurr = int(spec.get("nsurr") or 0)
    ms = msamples(spec)
    # Everything but the draw scales with how many samples there are, and the
    # rates are already per megasample, so this is one multiplication rather
    # than a correction factor. The draw is added once -- an earlier version
    # both included it in the sum and added it again on the way out.
    total = ms * (_RATES["read"] + _RATES["decimate"]
                  + _RATES["slow bank"] * n_slow
                  + _RATES["fast bank"] * n_fast
                  + _RATES["modulation index"] * n_slow * n_fast
                  + _RATES["surrogates"] * n_slow * nsurr) + _RATES["draw"]
    return {"seconds": round(total, 1),
            "cells": n_slow * n_fast,
            "slow": n_slow, "fast": n_fast,
            "megasamples": round(ms, 3),
            "surrogate_runs": n_slow * n_fast * nsurr}


def msamples(spec):
    """How many megasamples the grid will actually be built from."""
    n = (float(spec["t1"]) - float(spec["t0"]))         * float(spec.get("target_fs", 3000) or 3000)
    return max(n, 1.0) / 1e6
