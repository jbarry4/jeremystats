"""
coupling.py -- the three correlations between two regions, in one window.

Step two of The Arc. Spark finds the cue pairs and banks them; this reads the
traces under those pairs and says how tightly any two of the twelve DEWEY
regions were moving together in each of the pair's four windows. Circuit is
what makes a matrix out of the numbers; this only makes the numbers.

WHERE THE ARITHMETIC COMES FROM
-------------------------------
Transcribed from the cluster's `14 Correlation Data/
compute_connectivity_windows.m`, which produced the published connectivity
figures. Every parameter below is that file's -- the 1000 Hz analysis rate,
the 4-12 Hz theta band, the half-second lag bound, `hanning(1000)` with
`noverlap = 500` and `nfft = 2000`, and reading coherence off at 8 Hz. They
are transcribed rather than chosen so that a number computed here and a
number computed there are the same claim about the same recording.

The three methods keep the cluster's names -- `coherence`, `raw_cc`,
`amp_cc` -- for the same reason. A result that travels under a different
word is a result somebody has to translate.

WHAT EACH ONE ANSWERS
---------------------
  * `coherence`   how much of the 8 Hz rhythm the two regions share,
                  regardless of when. Magnitude-squared, so 0 to 1, and it
                  is blind to delay by construction.
  * `raw_cc`      the same two traces slid past one another: how alike they
                  are, and at what offset they line up best. This is the one
                  that can say which region leads.
  * `amp_cc`      the same question asked of the theta ENVELOPE rather than
                  the theta oscillation: not "do the waves line up" but "do
                  the two regions get loud and quiet together". Two regions
                  can share an envelope with no phase relationship at all,
                  and those are different findings.

TWO THINGS THAT WILL PRODUCE A CONFIDENT WRONG ANSWER
-----------------------------------------------------
**Mains is inside the band this works in.** Decimating to 1000 Hz leaves
60 Hz a long way below Nyquist, and `raw_cc`'s summary statistic is
`max(|r|)` over a thousand lags -- a MAXIMUM-SELECTION statistic. Every
channel in the room shares the same mains, so 60 Hz is coherent between any
two regions, at every lag that is a multiple of 16.7 ms, at an amplitude
that does not care whether the animal was doing anything. Given a thousand
lags to choose from, the maximum finds it. It does not look like an
artefact when it does: it looks like a strong, reproducible coupling with a
crisp lag. So the notch is ON by default, it runs before anything
correlates, and `notch` in the output says whether it ran. Turning it off is
allowed and is a thing you should have a reason for.

**A clipped channel is a flat line that correlates beautifully.** Spark
measures saturation per pair per channel and banks it as `clipped`;
somebody invalidating a channel by hand banks it as `excluded`. Both arrive
here as CSC numbers and both are dropped from the region average before the
average is taken -- see `excluded_for`. A region whose wires are all gone
returns None with a sentence saying so, and NEVER a number computed from
whatever was left over: a four-wire region averaged over one wire and a
four-wire region averaged over four are different measurements, and nothing
downstream can tell them apart once they are both a float.

WHAT IT REFUSES
---------------
A region with no usable channels, a window shorter than one Welch segment, a
trace with no variance, a window that falls across a segment break in the
.ncs: all refused with a reason, none guessed at. `pair_connectivity` keeps
the refusal beside the region pair it belongs to rather than dropping the
row, because "we could not measure this" and "these two regions are not
coupled" are opposite findings and a gap in a matrix cannot tell you which.
"""
from __future__ import annotations

import math
import os
from fractions import Fraction

import numpy as np
from scipy.signal import (butter, coherence as _welch_coherence, correlate,
                          correlation_lags, decimate, hilbert, iirnotch,
                          resample_poly, sosfiltfilt, filtfilt)
from scipy.signal.windows import hann

from . import nlx, probes, spark

# --------------------------------------------------------------------------
# The parameters, all of them from compute_connectivity_windows.m
# --------------------------------------------------------------------------
#: The rate everything is measured at. The recordings are 32 kHz; nothing
#: this module asks about lives above 12 Hz, and a 32-fold decimation is the
#: difference between a window that costs 1.3 million samples per channel
#: and one that costs 40,000.
ANALYSIS_FS = 1000.0

#: Theta, as the cluster pipeline defines it. `amp_cc` filters to this band;
#: `coherence` is reported at a single frequency inside it and `raw_cc` is
#: broadband, which is exactly why the notch matters to `raw_cc` and not to
#: the other two.
LOW_FREQ = 4.0
HIGH_FREQ = 12.0

#: How far two regions may be slid past one another. Half a second is far
#: beyond any conduction delay and is deliberately generous: a peak sitting
#: at 400 ms is evidence about the method, not about the brain, and cutting
#: the axis short would hide it.
MAX_LAG_SEC = 0.5

#: Welch, exactly as the MATLAB called it: `hanning(1000)`, 50% overlap,
#: zero-padded to 2000. At 1000 Hz that is a one-second segment and a 0.5 Hz
#: frequency grid, so 8 Hz lands ON a bin rather than between two.
WELCH_NPERSEG = 1000
WELCH_NOVERLAP = 500
WELCH_NFFT = 2000

#: Where coherence is read off. One number per region pair, at the middle of
#: the theta band, which is what the matrix is built from.
SUMMARY_HZ = 8.0

#: Mains, and how it is removed. See the module docstring for why this is on
#: by default.
#:
#: HARMONICS TOO. 60 Hz is not the only line: 120, 180 and the rest are all
#: below the 500 Hz Nyquist and all shared by every channel in the room.
#: Removing only the fundamental leaves a 120 Hz line that is just as
#: periodic and just as capable of owning `max(|r|)` -- it would move the
#: reported lag from a multiple of 16.7 ms to a multiple of 8.3 ms and
#: nothing else about the answer would change, which is the worst kind of
#: fix because the result still looks clean.
#:
#: FIXED WIDTH, NOT FIXED Q. `iirnotch` takes a Q, and a constant Q means a
#: notch that is 2 Hz wide at 60 and 16 Hz wide at 480 -- eight times as
#: much signal thrown away at the top as at the bottom, for a line that is
#: no wider up there. So the width is pinned and the Q is computed from it.
#:
#: MEASURED, on J4 Precon1, cue pair 1. There is MORE power at 60 Hz than
#: at 8 Hz in these recordings -- 348 against 271 in the pre-cue window of
#: right ACC -- and 145 again at 120 Hz. Across the four windows and all 66
#: region pairs, notching moves the reported peak lag on 12 of 264, and all
#: twelve had their un-notched peak sitting on an exact multiple of
#: 16.667 ms. On a synthetic pair where the mains is three times theta and
#: theta in one channel genuinely lags the other by 30 ms, the un-notched
#: answer is r = -0.94 at +25 ms -- one and a half mains cycles, so
#: anti-phase, with the sign of the coupling reversed as well as its
#: timing -- and the notched answer is r = +0.68 at -33 ms, which is the
#: delay that is really there.
NOTCH_HZ = 60.0
NOTCH_BW_HZ = 2.0
NOTCH_HARMONICS = True

#: The three methods, in the order they are reported. Named exactly as the
#: cluster names them.
METHODS = ("coherence", "raw_cc", "amp_cc")

#: Order of the bandpass `amp_cc` runs before taking an envelope. Fourth
#: order Butterworth, run forwards and backwards, so the band has no phase
#: response at all -- see `bandpass` for why that is not optional here.
BAND_ORDER = 4


class CouplingError(Exception):
    pass


# --------------------------------------------------------------------------
# Windows, filters, rates
# --------------------------------------------------------------------------
def matlab_hanning(n):
    """MATLAB's `hanning(n)`: the symmetric Hann WITHOUT its zero endpoints.

    `np.hanning(n)` and scipy's symmetric `hann(n)` are MATLAB's `hann(n)`,
    which is a different window: it starts and ends at exactly zero, so two
    of every thousand samples contribute nothing at all. MATLAB's `hanning`
    is `0.5 * (1 - cos(2*pi*k/(n+1)))` for k = 1..n, which is the interior
    of `hann(n + 2)`.

    The difference to a coherence estimate is in the fourth decimal place.
    It is written out anyway because the MATLAB says `hanning` and this is a
    transcription: a reader comparing the two files should not have to work
    out whether the spelling was deliberate.
    """
    return hann(int(n) + 2, sym=True)[1:-1]


def _decimation_steps(q):
    """Split an integer decimation into factors small enough to be stable.

    `scipy.signal.decimate` warns above q = 13 and it is right to: the
    anti-alias filter is an order-8 Chebyshev, and designing one whose
    cutoff is a thirty-second of Nyquist puts all eight poles on top of each
    other. 32 becomes 8 then 4, which is two well-conditioned filters.

    Returns None if `q` cannot be made out of factors this size, and the
    caller resamples instead.
    """
    q = int(q)
    steps = []
    for f in (8, 7, 5, 4, 3, 2):
        while q > 1 and q % f == 0:
            steps.append(f)
            q //= f
    if q != 1:
        return None
    return sorted(steps, reverse=True)


def decimate_to(x, fs, target_fs=ANALYSIS_FS):
    """`x` at `target_fs`, anti-aliased. Returns (y, fs_out).

    `scipy.signal.decimate` with its default IIR filter IS MATLAB's
    `decimate` -- order-8 Chebyshev type I, run forwards and backwards --
    so this is the same operation the cluster performed, staged rather than
    done in one step. Numbers from the two are extremely close and not
    bit-identical, and this is the reason.

    ZERO PHASE IS NOT A PREFERENCE HERE. Two of the three methods report a
    LAG. Any filter with a phase response delays the signal, and while both
    regions get the same filter and a common delay cancels, a non-linear
    phase response does not cancel -- it reshapes each trace differently
    depending on its own spectrum, and the peak of the cross-correlation
    moves. `zero_phase=True` and `filtfilt` everywhere below are there so
    that every lag this module reports is a lag in the data.
    """
    x = np.asarray(x, dtype=np.float64)
    fs = float(fs)
    target = float(target_fs)
    if not np.isfinite(fs) or fs <= 0:
        raise CouplingError("That channel's header has no sampling rate, so "
                            "there is no way to know what its samples mean.")
    if abs(fs - target) < 1e-9:
        return x, fs
    if fs < target:
        raise CouplingError(
            "This recording samples at %g Hz, below the %g Hz these "
            "correlations are defined at. Upsampling to reach it would "
            "invent the difference." % (fs, target))

    ratio = fs / target
    q = int(round(ratio))
    steps = _decimation_steps(q) if abs(ratio - q) < 1e-9 and q >= 2 else None
    if steps:
        # filtfilt needs about three filter lengths of signal. A window
        # shorter than that is refused rather than padded into existence.
        need = 3 * (WELCH_NPERSEG // 10)
        if x.size < need:
            raise CouplingError(
                "That window is %d samples, too short to decimate without "
                "the filter's own edges being most of the answer."
                % x.size)
        for f in steps:
            x = decimate(x, f, ftype="iir", zero_phase=True)
        return x, fs / float(q)

    # A rate that is not a whole multiple of 1000 -- 30 kHz recordings, and
    # anything Cheetah was set up differently for. `resample_poly` designs
    # one linear-phase FIR and compensates its own delay, so the rate is
    # right and the timing still is.
    frac = Fraction(target / fs).limit_denominator(4096)
    y = resample_poly(x, frac.numerator, frac.denominator)
    return np.asarray(y, dtype=np.float64), fs * frac.numerator / frac.denominator


def notch_lines(hz, fs, harmonics=NOTCH_HARMONICS):
    """Which mains lines a notch at `hz` should remove, given `fs`."""
    if not hz or float(hz) <= 0:
        return []
    hz = float(hz)
    nyq = float(fs) / 2.0
    if hz >= nyq:
        return []
    if not harmonics:
        return [hz]
    out, k = [], 1
    while hz * k < nyq * 0.98:
        out.append(hz * k)
        k += 1
    return out


def notch(x, fs, hz=NOTCH_HZ, harmonics=NOTCH_HARMONICS, bw_hz=NOTCH_BW_HZ):
    """Mains out, everything else left alone. Returns (y, lines_removed).

    Run before any of the three methods, on both signals, and see the module
    docstring for why. In practice only `raw_cc` can notice: `coherence` is
    read at 8 Hz and `amp_cc` bandpasses to 4-12 Hz first, so both have
    already thrown 60 Hz away by the time they are asked anything. It is
    applied to all three regardless so that the three are statements about
    the same signal.
    """
    lines = notch_lines(hz, fs, harmonics)
    if not lines:
        return np.asarray(x, dtype=np.float64), []
    y = np.asarray(x, dtype=np.float64)
    for f0 in lines:
        b, a = iirnotch(f0, f0 / float(bw_hz), fs=float(fs))
        y = filtfilt(b, a, y)
    return y, lines


def bandpass(x, fs, low=LOW_FREQ, high=HIGH_FREQ, order=BAND_ORDER):
    """Zero-phase Butterworth band, as second-order sections.

    `sosfiltfilt` rather than `filtfilt` on a transfer function: a
    fourth-order bandpass is an eighth-order filter, and its `b, a` form
    loses enough precision at a 4 Hz corner on a 1000 Hz rate to ring
    visibly. The sections do not.
    """
    nyq = float(fs) / 2.0
    if not (0 < low < high < nyq):
        raise CouplingError(
            "A %g-%g Hz band does not fit inside a %g Hz signal."
            % (low, high, fs))
    sos = butter(order, [low / nyq, high / nyq], btype="bandpass",
                 output="sos")
    return sosfiltfilt(sos, np.asarray(x, dtype=np.float64))


def envelope(x, fs, low=LOW_FREQ, high=HIGH_FREQ):
    """The theta envelope: bandpass, Hilbert, magnitude, mean removed.

    THE MEAN REMOVAL IS LOAD-BEARING. An envelope is strictly positive, so
    two envelopes correlated as they stand are two positive numbers
    multiplied together at every lag: the normalised cross-correlation of
    any two of them is near 1 everywhere, and the peak is wherever the noise
    happened to be largest. Centring turns "both are positive" back into
    "both are above their own average at the same moment", which is the
    question. `raw_cc` is NOT centred, for the matching reason -- an LFP is
    already about zero and MATLAB's `xcorr(...,'coeff')` does not centre
    either, so centring there would be a silent departure from the file this
    is transcribed from.

    Measured, because "already about zero" is the kind of claim that is
    worth checking rather than assuming: on J4 Precon1, cue pair 1, cue 1,
    the twelve region averages sit between -5 and +25 uV against a standard
    deviation near 900, and centring them moves the peak r by 0.001 to
    0.006 and moves no peak's lag at all. It is a fourth-decimal-place
    difference, and it is the MATLAB's fourth decimal place.
    """
    amp = np.abs(hilbert(bandpass(x, fs, low, high)))
    return amp - amp.mean()


# --------------------------------------------------------------------------
# The three methods
# --------------------------------------------------------------------------
def _check_pair(a, b):
    """Two signals fit to correlate, or a sentence saying why not."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size == 0 or b.size == 0:
        raise CouplingError("One of those regions has no signal in this "
                            "window.")
    if a.size != b.size:
        raise CouplingError(
            "Those two windows are %d and %d samples long. Correlating them "
            "would be correlating two different spans of time."
            % (a.size, b.size))
    for name, v in (("first", a), ("second", b)):
        if not np.all(np.isfinite(v)):
            raise CouplingError("The %s region's trace has values that are "
                                "not numbers in this window." % name)
        if v.std() <= 0:
            # A flat trace is what a saturated amplifier leaves behind, and
            # it is also what a disconnected wire leaves behind. Either way
            # there is nothing here to correlate, and 'coeff' would divide
            # by zero and hand back a nan that looks like a missing value
            # rather than a broken channel.
            raise CouplingError(
                "The %s region's trace does not vary at all in this window "
                "-- a flat line, which is what a saturated or disconnected "
                "channel looks like." % name)
    return a, b


def coherence_curve(a, b, fs, nperseg=WELCH_NPERSEG, noverlap=WELCH_NOVERLAP,
                    nfft=WELCH_NFFT):
    """Welch magnitude-squared coherence. Returns (freqs, Cxy).

    Refuses a window shorter than one segment rather than letting scipy
    shorten `nperseg` for it, which it will do with a warning nobody sees.
    A coherence computed over one 300 ms segment is not the same estimator
    as one computed over nineteen overlapping seconds, and reporting both
    under one name in one matrix is how a short window becomes a strong
    result.
    """
    if a.size < nperseg:
        raise CouplingError(
            "This window is %d samples and the coherence estimate is "
            "defined on %d-sample segments. A shorter segment would be a "
            "different measurement wearing the same name."
            % (a.size, nperseg))
    f, cxy = _welch_coherence(a, b, fs=fs, window=matlab_hanning(nperseg),
                              nperseg=nperseg, noverlap=noverlap, nfft=nfft)
    return f, cxy


def _xcorr_coeff(a, b, fs, max_lag_s=MAX_LAG_SEC):
    """MATLAB's `xcorr(a, b, maxlag, 'coeff')`. Returns (lags_ms, r).

    Normalised by the two signals' own energies -- `sqrt(sum(a^2) *
    sum(b^2))` -- which is what 'coeff' means and is why r is bounded to
    [-1, 1] with r(0) = 1 when a is b.

    THE SIGN OF THE LAG. `r[k] = sum_n a[n+k] * b[n]`, the same convention
    MATLAB uses. So a POSITIVE lag means the feature arrives in `a` LATER
    than in `b`: b leads, a follows. Written out because half the value of
    this method is the direction, and a convention that is only implied gets
    read backwards eventually.
    """
    n = a.size
    max_lag = int(round(float(max_lag_s) * float(fs)))
    if max_lag < 1:
        raise CouplingError("A maximum lag of %g s is less than one sample "
                            "at %g Hz." % (max_lag_s, fs))
    if max_lag >= n:
        raise CouplingError(
            "A +/-%g s lag range needs more than %d samples of window; this "
            "one has %d, so the longest lags would be computed from almost "
            "no overlap." % (max_lag_s, 2 * max_lag, n))
    denom = math.sqrt(float(np.dot(a, a)) * float(np.dot(b, b)))
    if denom <= 0:
        raise CouplingError("One of those traces carries no energy at all.")
    full = correlate(a, b, mode="full", method="fft")
    lags = correlation_lags(n, n, mode="full")
    keep = np.abs(lags) <= max_lag
    return lags[keep] * (1000.0 / float(fs)), full[keep] / denom


def _peak(lags_ms, r):
    """Where |r| is largest, as (signed r, lag in ms).

    The signed value at the peak, not the absolute one. The summary the
    cluster reports is `max(|r|)`, and the magnitude is what goes in the
    matrix -- but an r of -0.6 and an r of +0.6 are opposite findings about
    two regions, and throwing the sign away at the point of measurement
    means nothing downstream can ever get it back.
    """
    i = int(np.argmax(np.abs(r)))
    return float(r[i]), float(lags_ms[i])


def _curve(x, y, x_unit, y_unit, dp=6):
    return {"x": [round(float(v), 4) for v in x],
            "y": [round(float(v), dp) for v in y],
            "x_unit": x_unit, "y_unit": y_unit, "n": int(len(x))}


def metrics(a, b, fs=ANALYSIS_FS, notch_hz=NOTCH_HZ, low=LOW_FREQ,
            high=HIGH_FREQ, max_lag_s=MAX_LAG_SEC, curves=True,
            harmonics=NOTCH_HARMONICS):
    """All three correlations between two signals, with their curves.

    `a` and `b` are one window of two regions, already at `fs`. Each method
    comes back as `{"curve": {x, y, ...}, "summary": {value, x, x_unit}}` --
    the curve because a single number out of a thousand lags is a claim
    somebody should be able to look at, and the summary because the matrix
    needs one number.

    `curves=False` drops the curves and keeps the summaries, which is what
    `pair_connectivity` uses: 66 region pairs x 4 windows x 3 methods is 792
    curves of about a thousand points each, and nothing reads them all.
    """
    a, b = _check_pair(a, b)
    a, lines = notch(a, fs, notch_hz, harmonics)
    b, _ = notch(b, fs, notch_hz, harmonics)

    out = {
        "fs": float(fs),
        "n": int(a.size),
        "duration_s": round(a.size / float(fs), 6),
        # Said in the result, not only in the call, because a matrix that
        # has been notched and one that has not are different matrices and
        # the difference is invisible in the numbers.
        "notch": {
            "hz": (float(notch_hz) if notch_hz else None),
            "applied": bool(lines),
            "lines_hz": [round(f, 3) for f in lines],
            "bandwidth_hz": NOTCH_BW_HZ,
            "why": ("60 Hz mains sits inside the band a 1000 Hz signal "
                    "covers, and max(|r|) over a thousand lags will find "
                    "it and report it as coupling."),
        },
        "params": {"low": float(low), "high": float(high),
                   "max_lag_s": float(max_lag_s),
                   "summary_hz": SUMMARY_HZ,
                   "nperseg": WELCH_NPERSEG, "noverlap": WELCH_NOVERLAP,
                   "nfft": WELCH_NFFT},
    }

    # coherence -----------------------------------------------------------
    f, cxy = coherence_curve(a, b, fs)
    i = int(np.argmin(np.abs(f - SUMMARY_HZ)))
    out["coherence"] = {
        "summary": {
            "value": round(float(cxy[i]), 6),
            "x": round(float(f[i]), 4),
            "x_unit": "Hz",
            "what": "magnitude-squared coherence at %g Hz" % SUMMARY_HZ,
        },
        "curve": _curve(f, cxy, "Hz", "coherence") if curves else None,
    }

    # raw_cc --------------------------------------------------------------
    lags, r = _xcorr_coeff(a, b, fs, max_lag_s)
    val, lag = _peak(lags, r)
    out["raw_cc"] = {
        "summary": {
            "value": round(val, 6),
            "abs": round(abs(val), 6),
            "x": round(lag, 3),
            "x_unit": "ms",
            "what": "peak |r| within +/-%g ms, and where it sat"
                    % (max_lag_s * 1000.0),
            "lag_note": "positive means the first region follows the second",
        },
        "curve": _curve(lags, r, "ms", "r") if curves else None,
    }

    # amp_cc --------------------------------------------------------------
    ea = envelope(a, fs, low, high)
    eb = envelope(b, fs, low, high)
    lags2, r2 = _xcorr_coeff(ea, eb, fs, max_lag_s)
    val2, lag2 = _peak(lags2, r2)
    out["amp_cc"] = {
        "summary": {
            "value": round(val2, 6),
            "abs": round(abs(val2), 6),
            "x": round(lag2, 3),
            "x_unit": "ms",
            "what": "peak |r| of the %g-%g Hz envelopes within +/-%g ms"
                    % (low, high, max_lag_s * 1000.0),
            "lag_note": "positive means the first region follows the second",
        },
        "curve": _curve(lags2, r2, "ms", "r") if curves else None,
    }
    return out


# --------------------------------------------------------------------------
# Which channels a region has, and which of them it may use
# --------------------------------------------------------------------------
def dewey_map():
    """The twelve DEWEY regions as {display name: [CSC numbers]}.

    Keyed by the DISPLAY NAME -- "Left POR", not "L_POR" -- because that is
    the key `DEWEY_REGION_COLORS` and `DEWEY_NETWORK_ORDER` already use, and
    one region vocabulary across the pipeline is worth more than a shorter
    key here.

    In network-ring order rather than CSC order, so a matrix built straight
    off this comes out in the same arrangement as the cluster's figures and
    the two can be laid side by side.
    """
    by_name = {r["region"]: list(r["csc"]) for r in probes.DEWEY_REGIONS}
    return {name: by_name[name] for name in probes.DEWEY_NETWORK_ORDER
            if name in by_name}


def region_map(regions):
    """Normalise whatever the caller has into {name: [CSC numbers]}.

    Takes a plain dict, the list `probes.regions_for` returns, or
    `probes.DEWEY_REGIONS` itself, because all three exist in this
    application and making callers convert between them is how a region ends
    up keyed by an id in one place and a display name in another.

    None means the DEWEY montage, which is the only montage The Arc runs on.
    """
    if regions is None:
        return dewey_map()
    if isinstance(regions, dict):
        return {str(k): [int(c) for c in v] for k, v in regions.items()}
    out = {}
    for r in regions:
        if not isinstance(r, dict):
            raise CouplingError("A region has to be a name and a list of CSC "
                                "numbers; got %r." % (r,))
        name = r.get("region") or r.get("id") or r.get("label")
        # `csc_present` is what `regions_for` leaves after dropping the
        # recording's bad channels; `csc` is the montage's full list. Prefer
        # the former where it exists, so a bad channel somebody marked on
        # the recording is not quietly re-admitted here.
        csc = r.get("csc_present")
        if csc is None:
            csc = r.get("csc") or []
        out[str(name)] = [int(c) for c in csc]
    return out


def excluded_for(event):
    """The CSC numbers one banked event is not valid on.

    The union of `clipped` (measured: the amplifier saturated in one of this
    pair's windows) and `excluded` (decided: somebody looked and said not
    this one). They are banked apart because a measurement and a judgement
    are different claims -- see `eventbank.py` -- and they are unioned here
    because at the point of correlating, both mean the same thing: this wire
    was not measuring the brain during this event.

    Returns a DICT keyed by window name when the event carries per-window
    lists, and a flat sorted list when it does not. `_exclude_map` takes
    either, so callers can pass this straight through -- an older entry
    banked before the windows were separated keeps working and simply
    excludes its channels everywhere, which is what it meant.
    """
    ev = event or {}
    per, flat = {}, set()
    for key in ("clipped", "excluded"):
        got = ev.get(key)
        if isinstance(got, dict):
            for wname, chans in got.items():
                have = per.setdefault(str(wname), set())
                for c in (chans or []):
                    try:
                        have.add(int(c))
                    except (TypeError, ValueError):
                        continue
            continue
        for c in (got or []):
            try:
                flat.add(int(c))
            except (TypeError, ValueError):
                continue
    if not per:
        return sorted(flat)
    # A flat list beside a per-window one applies to every window.
    for wname in list(per) or CLIP_WINDOW_NAMES:
        per[wname] |= flat
    for wname in CLIP_WINDOW_NAMES:
        per.setdefault(wname, set(flat))
    return {k: sorted(v) for k, v in per.items()}


# --------------------------------------------------------------------------
# Reading the traces
# --------------------------------------------------------------------------
# A DEWEY recording is 663 MB a channel and there are 32 of them. A cue
# pair's four windows are forty seconds -- about five megabytes a channel at
# 32 kHz. `nlx.read_ncs` would read all twenty gigabytes to hand back a
# hundred and sixty megabytes of answer, per pair.
#
# So the same approach `spark.clipping_for` uses: memory-map the file,
# find the record holding the moment, slice. Records are a fixed 1044 bytes
# and their timestamps are monotonic, so the record index is an arithmetic
# step away and the operating system pages in only what is touched.
#
# It differs from `clipping_for` in one way, and the reason is what this
# module is for: clipping asks "did anything in roughly this span hit the
# rail", where a record either side costs nothing. A correlation asks "what
# happened at this moment relative to that one", where a record either side
# is sixteen milliseconds of lag error. So the window is cut to the sample
# using the RECORD'S OWN TIMESTAMP rather than an assumed record length, and
# a window that straddles a break in the clock is refused instead of being
# silently stitched across the gap.
def _record_at(mm, n_rec, want_us, per_rec_us):
    """The index of the record containing `want_us`, or None if outside.

    Guesses arithmetically and then walks, because the guess is exact in a
    continuous file and is wrong by however much time was lost in one that
    has stopped and restarted. Three or four timestamp reads, not a scan:
    reading the whole timestamp column strides over the entire 663 MB and
    pages in the samples with it.
    """
    first = float(mm["timestamp"][0])
    last = float(mm["timestamp"][n_rec - 1])
    if want_us < first or want_us >= last + per_rec_us:
        return None
    i = int((want_us - first) // per_rec_us)
    i = max(0, min(n_rec - 1, i))
    for _ in range(8):
        got = float(mm["timestamp"][i])
        step = int((want_us - got) // per_rec_us)
        if step == 0:
            break
        j = max(0, min(n_rec - 1, i + step))
        if j == i:
            break
        i = j
    # The walk lands on the right record or one either side of it; settle it
    # by comparison rather than by trusting the arithmetic.
    while i > 0 and float(mm["timestamp"][i]) > want_us:
        i -= 1
    while i + 1 < n_rec and float(mm["timestamp"][i + 1]) <= want_us:
        i += 1
    return i


def _window_block(mm, n_rec, fs, origin_us, t0, t1):
    """The raw samples for [t0, t1) seconds, or (None, why).

    Times are seconds from the start of the RECORDING -- the frame Spark
    banks in and the only one that means anything across channels.
    """
    per_rec_us = nlx.SAMPLES_PER_RECORD / float(fs) * 1e6
    want_us = float(origin_us) + float(t0) * 1e6
    n_want = int(round((float(t1) - float(t0)) * float(fs)))
    if n_want <= 0:
        return None, "that window has no length"

    i0 = _record_at(mm, n_rec, want_us, per_rec_us)
    if i0 is None:
        return None, "that window is outside this channel's file"
    i1 = min(n_rec, i0 + n_want // nlx.SAMPLES_PER_RECORD + 2)

    ts = np.asarray(mm["timestamp"][i0:i1]).astype(np.float64)
    nvalid = np.asarray(mm["nvalid"][i0:i1])
    if np.any(nvalid != nlx.SAMPLES_PER_RECORD):
        # A short record is where Cheetah closed a block early, which is the
        # start of a section break. Everything after it in this slice is at
        # a different offset than the arithmetic says, so the window cannot
        # be cut to the sample and is refused rather than cut to the record.
        return None, "acquisition hiccups inside this window (a short record)"
    if ts.size > 1:
        drift = np.abs(np.diff(ts) - per_rec_us)
        if float(drift.max()) > per_rec_us * 0.5:
            return None, "a break in the clock falls inside this window"

    block = np.asarray(mm["samples"][i0:i1]).ravel()
    s0 = int(round((want_us - ts[0]) * float(fs) / 1e6))
    s1 = s0 + n_want
    if s0 < 0 or s1 > block.size:
        return None, "that window runs off the end of this channel's file"
    return block[s0:s1], None


def _channel_windows(path, windows, origin_us):
    """One channel's raw samples for each window. Returns (per_window, meta).

    `per_window` is {name: array or None}; a None carries its reason in
    `meta["why"][name]`. One memory map per channel for all four windows,
    rather than one per window: opening the map is cheap and paging the same
    records in four times is not.
    """
    hdr = nlx.read_header(path)
    # `_header_float` rather than `float(hdr[...])`: some Digital Lynx
    # headers write one value per channel on a single line, and a bare
    # float() of that raises on a recording that is otherwise fine.
    fs = nlx._header_float(hdr, "SamplingFrequency") or nlx.DEFAULT_FS
    adbv = nlx._header_float(hdr, "ADBitVolts") or nlx.FALLBACK_ADBITVOLTS
    size = os.path.getsize(path)
    n_rec = max(0, (size - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize)
    if n_rec <= 0:
        return {}, {"fs": fs, "why": {}, "empty": True}

    got, why = {}, {}
    mm = np.memmap(path, dtype=nlx.RECORD_DTYPE, mode="r",
                   offset=nlx.HEADER_BYTES, shape=(int(n_rec),))
    try:
        for name, t0, t1 in windows:
            block, reason = _window_block(mm, n_rec, fs, origin_us, t0, t1)
            if block is None:
                got[name] = None
                why[name] = reason
                continue
            # Counts to microvolts, and negated, which is the lab's
            # `invertPolarity = true` -- the same convention `nlx.read_ncs`
            # applies. A correlation between a signal read this way and one
            # read the other way is sign-flipped, and nothing about the
            # number says so.
            got[name] = -(block.astype(np.float64) * (adbv * 1e6))
    finally:
        del mm
    return got, {"fs": float(fs), "adbitvolts": float(adbv), "why": why,
                 "n_records": int(n_rec)}


#: The four window names, taken from Spark so there is one source for them.
CLIP_WINDOW_NAMES = tuple(spark.CLIP_WINDOWS)


def _exclude_map(exclude, windows):
    """{window name: set of CSC} from either shape the caller may pass.

    A flat list means "not valid for this event at all" and applies to
    every window; a dict names the windows one at a time. Both are real:
    somebody dropping a whole channel means the first, and the clipping
    measurement means the second.
    """
    names = [w[0] for w in windows]
    if isinstance(exclude, dict):
        return {n: {int(c) for c in (exclude.get(n) or [])} for n in names}
    flat = {int(c) for c in (exclude or [])}
    return {n: set(flat) for n in names}


def _signals_for_windows(folder, chan_map, windows, exclude=(),
                         target_fs=ANALYSIS_FS, progress=None):
    """Every region's signal in every window: the shared engine.

    `region_signals` is one window of this and `pair_connectivity` is four.
    They share it because the cost is opening 32 files, and doing that once
    per window rather than once per pair is four times the work for the same
    answer.
    """
    # Per window, not per event.
    #
    # A cue pair is analysed in four windows and a channel can be ruined in
    # one of them and perfectly good in the other three -- that is the
    # whole reason the windows are measured separately. Excluding by event
    # threw the three good windows away with the bad one, which on data
    # this clipped is most of the data.
    ex = _exclude_map(exclude, windows)
    every = set.intersection(*ex.values()) if ex else set()
    files = dict(nlx.list_csc_files(folder, even_only=False))
    origin = nlx.recording_start_us(folder)
    if origin is None:
        raise CouplingError(
            "No .ncs file in that folder could be read, so there is no clock "
            "to place these windows against.")

    wanted = sorted({int(c) for csc in chan_map.values() for c in csc})
    # Why a channel is unusable, keyed by (channel, window) and not by
    # channel: a wire can be fine in `pre` and off the end of the file in
    # `post`, and one reason per channel would put the second window's
    # sentence against the first window's perfectly good trace.
    traces, why, fs_seen = {}, {}, set()
    for n, num in enumerate(wanted):
        if progress:
            progress(n, len(wanted), num)
        if num in every:
            # Gone in every window: no reason to open the file at all.
            for wname, _a, _b in windows:
                why[(num, wname)] = "not valid for this event"
            continue
        path = files.get(num)
        if path is None:
            for wname, _a, _b in windows:
                why[(num, wname)] = "no CSC%d.ncs in this recording" % num
            continue
        try:
            got, meta = _channel_windows(path, windows, origin)
        except (OSError, ValueError) as exc:
            for wname, _a, _b in windows:
                why[(num, wname)] = "could not be read (%s)" % exc
            continue
        fs_seen.add(round(meta.get("fs") or 0.0, 3))
        # Drop only the windows this channel is invalidated for, keeping
        # the rest of its trace.
        for wname, _a, _b in windows:
            if num in ex.get(wname, ()):
                got.pop(wname, None)
                why[(num, wname)] = "not valid for this window"
        traces[num] = got
        for wname, reason in (meta.get("why") or {}).items():
            why.setdefault((num, wname), reason)
    if not traces:
        # The two reasons look identical from here and mean opposite things:
        # a folder that cannot be read is a problem with the machine, and an
        # event with every wire invalidated is a problem with the event.
        if every and set(wanted) <= every:
            raise CouplingError(
                "Every one of the %d channels these regions need is "
                "invalidated for this event, so there is nothing left to "
                "correlate." % len(wanted))
        raise CouplingError("None of the channels these regions need could be "
                            "read from that folder.")
    if len(fs_seen) > 1:
        # Regions are averaged across wires and then correlated against each
        # other. Two channels at two rates are two different time axes, and
        # averaging them is nonsense before anything else gets a chance to
        # be wrong.
        raise CouplingError(
            "The channels in this recording do not share a sampling rate "
            "(%s Hz). There is no single time axis to correlate on."
            % ", ".join(str(f) for f in sorted(fs_seen)))
    source_fs = float(sorted(fs_seen)[0])

    out = {}
    for wname, t0, t1 in windows:
        regions = {}
        for name, csc in chan_map.items():
            used, dropped, stack = [], [], []
            for num in csc:
                num = int(num)
                arr = (traces.get(num) or {}).get(wname)
                if arr is None:
                    dropped.append({"csc": num,
                                    "why": why.get((num, wname),
                                                   "no signal in this "
                                                   "window")})
                    continue
                used.append(num)
                stack.append(arr)
            if not stack:
                # REFUSE RATHER THAN GUESS. No fallback to the nearest
                # region, to the recording average, or to zeros: a region
                # with nothing left in it has not been measured, and a
                # number here would be indistinguishable from one that was.
                regions[name] = {
                    "signal": None, "channels": [], "dropped": dropped,
                    "n": 0, "usable": False,
                    "why": ("none of %s's %d channels are usable in this "
                            "window" % (name, len(csc))),
                }
                continue
            n_min = min(a.size for a in stack)
            mean = np.mean([a[:n_min] for a in stack], axis=0)
            # Averaged at the source rate and decimated once, rather than
            # decimated per wire and averaged: decimation is linear, so the
            # two give the same answer, and a four-wire region costs one
            # filter pass instead of four.
            sig, fs_out = decimate_to(mean, source_fs, target_fs)
            regions[name] = {
                "signal": sig, "channels": used, "dropped": dropped,
                "n": int(sig.size), "usable": True, "why": None,
                # Said out loud so a reader can see when a region was
                # averaged over fewer wires than the montage gives it.
                "of": len(csc),
            }
        out[wname] = {
            "t0": float(t0), "t1": float(t1),
            "fs": float(target_fs), "source_fs": source_fs,
            "regions": regions,
        }
    return out


def region_signals(folder, channels_by_region, t0, t1, exclude=(),
                   target_fs=ANALYSIS_FS):
    """One window of every region, decimated, averaged over usable wires.

    `channels_by_region` is anything `region_map` understands. `exclude` is
    CSC NUMBERS -- never row indices, which move the moment somebody toggles
    even-only -- and is normally `excluded_for(banked_event)`.

    Returns `{"fs", "t0", "t1", "regions": {name: {...}}}` where each region
    carries its `signal` (or None), the channels it was actually made from,
    the ones it lost and why, and how many the montage gives it. A region
    that lost everything is None WITH a sentence, not an absence: a caller
    that cannot tell "no usable wires" from "not coupled" will read the
    first as the second.
    """
    chan_map = region_map(channels_by_region)
    got = _signals_for_windows(folder, chan_map, [("window", t0, t1)],
                               exclude, target_fs)
    out = got["window"]
    out["exclude"] = sorted(int(c) for c in (exclude or []))
    return out


# --------------------------------------------------------------------------
# A cue pair, end to end
# --------------------------------------------------------------------------
def region_pairs(names):
    """Every unordered pair of regions, in the order the names came in.

    Twelve regions is 66 pairs. Unordered because none of the three methods
    is asymmetric in a way that makes (A, B) and (B, A) different findings:
    coherence is symmetric outright, and the two correlations are mirror
    images -- r_BA(lag) = r_AB(-lag) -- so the second copy would be the same
    result with its lag sign flipped, filed under a different key.
    """
    names = list(names)
    return [(names[i], names[j])
            for i in range(len(names)) for j in range(i + 1, len(names))]


def pair_connectivity(folder, pair, regions=None, exclude_by_channel=(),
                      notch_hz=NOTCH_HZ, low=LOW_FREQ, high=HIGH_FREQ,
                      max_lag_s=MAX_LAG_SEC, target_fs=ANALYSIS_FS,
                      pad_s=spark.CLIP_PAD_S, curves=False, progress=None):
    """One cue pair: four windows, 66 region pairs, three methods each.

    `pair` is one of `spark.pair_events`'s pairs -- or a banked event that
    still carries its boundaries. The four windows are `spark.pair_windows`
    and are NOT redefined here: ten seconds before cue 1, cue 1, cue 2, ten
    seconds after cue 2 ends, bounded by the pair's own measured moments
    rather than by assuming each cue ran exactly ten seconds. One definition
    of a window, in the module that found the pair.

    `exclude_by_channel` is the CSC numbers this event is not valid on --
    `excluded_for(event)` for a banked one. They come out of the region
    averages before the averages are taken, which is the only place taking
    them out means anything.

    Every refusal is kept where it happened: a region pair that could not be
    measured is a row with `why` set and three Nones, not a missing row.
    """
    chan_map = region_map(regions)
    windows = spark.pair_windows(pair, pad_s)
    exclude = (exclude_by_channel if isinstance(exclude_by_channel, dict)
               else sorted({int(c) for c in (exclude_by_channel or [])}))

    got = _signals_for_windows(folder, chan_map, windows, exclude, target_fs,
                               progress=progress)

    names = list(chan_map.keys())
    pairs_of = region_pairs(names)
    out_windows = []
    for wname, t0, t1 in windows:
        w = got[wname]
        rows, refused = [], 0
        for a_name, b_name in pairs_of:
            ra, rb = w["regions"][a_name], w["regions"][b_name]
            row = {"a": a_name, "b": b_name,
                   "a_channels": ra["channels"], "b_channels": rb["channels"]}
            if not ra["usable"] or not rb["usable"]:
                row["why"] = "; ".join(
                    x["why"] for x in (ra, rb) if x.get("why"))
                for m in METHODS:
                    row[m] = None
                rows.append(row)
                refused += 1
                continue
            try:
                m = metrics(ra["signal"], rb["signal"], w["fs"],
                            notch_hz=notch_hz, low=low, high=high,
                            max_lag_s=max_lag_s, curves=curves)
            except CouplingError as exc:
                row["why"] = str(exc)
                for name in METHODS:
                    row[name] = None
                rows.append(row)
                refused += 1
                continue
            row["why"] = None
            for name in METHODS:
                row[name] = (m[name] if curves else m[name]["summary"])
            rows.append(row)
        out_windows.append({
            "window": wname,
            "t0": round(float(t0), 6), "t1": round(float(t1), 6),
            "duration_s": round(float(t1) - float(t0), 6),
            "fs": w["fs"], "source_fs": w["source_fs"],
            "n_samples": max((r["n"] for r in w["regions"].values()),
                             default=0),
            "regions": {name: {"channels": r["channels"], "of": r.get("of"),
                               "usable": r["usable"], "why": r["why"],
                               "dropped": r["dropped"]}
                        for name, r in w["regions"].items()},
            "pairs": rows,
            "n_pairs": len(rows),
            "n_refused": refused,
        })

    lines = notch_lines(notch_hz, target_fs)
    return {
        "pair_id": pair.get("pair_id"),
        "label": pair.get("label") or "%s -> %s" % (pair.get("opener_label"),
                                                    pair.get("closer_label")),
        "folder": folder,
        "windows": out_windows,
        "region_order": names,
        "excluded": exclude,
        "notch": {"hz": float(notch_hz) if notch_hz else None,
                  "applied": bool(lines),
                  "lines_hz": [round(f, 3) for f in lines]},
        "params": {
            "analysis_fs": float(target_fs),
            "low": float(low), "high": float(high),
            "max_lag_s": float(max_lag_s),
            "summary_hz": SUMMARY_HZ,
            "nperseg": WELCH_NPERSEG, "noverlap": WELCH_NOVERLAP,
            "nfft": WELCH_NFFT,
            "methods": list(METHODS),
            "pad_s": float(pad_s),
            # Where every one of these came from, carried with the result.
            # Circuit saves a matrix that has to be able to say what made
            # it, and a provenance line assembled later is a provenance line
            # somebody can get wrong.
            "source": "14 Correlation Data/compute_connectivity_windows.m",
        },
    }
