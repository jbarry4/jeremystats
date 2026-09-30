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
# Loaded on first use, not at start-up; see lazyimp.py for why.
from . import lazyimp  # noqa: E402
(butter, _welch_coherence, correlate, correlation_lags, decimate,
 hilbert, iirnotch, resample_poly, sosfiltfilt, filtfilt) = lazyimp.names(
    "scipy.signal", "butter", "coherence", "correlate",
    "correlation_lags", "decimate", "hilbert", "iirnotch",
    "resample_poly", "sosfiltfilt", "filtfilt")
hann = lazyimp.names("scipy.signal.windows", "hann")

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
#:
#: This was called BAND_ORDER until the bands below arrived; that name now
#: means the order the bands are listed in (arc_contracts.md 7.1), which is
#: the reading a person reaching for "the band order" of a circuit expects.
BUTTER_ORDER = 4

#: The three bands a circuit can be computed in (arc_contracts.md 7.1). The
#: lag bound is about two cycles of the slowest frequency in the band: a
#: peak further out than that is a peak between two different cycles, and
#: a wider search only gives max(|r|) more chances to find noise.
#:
#: Low gamma stops at 55 Hz, below the 60 Hz mains line and clear of the
#: notch's shoulder -- see "Mains is inside the band" above.
BANDS = {
    "theta": {"id": "theta", "low": 4.0, "high": 12.0, "max_lag_ms": 500.0},
    "beta": {"id": "beta", "low": 13.0, "high": 30.0, "max_lag_ms": 150.0},
    "gamma_low": {"id": "gamma_low", "low": 30.0, "high": 55.0,
                  "max_lag_ms": 60.0},
}
BAND_ORDER = ("theta", "beta", "gamma_low")
#: How each band is written for a person (circuit names, the panel).
BAND_LABELS = {"theta": "Theta", "beta": "Beta", "gamma_low": "Low gamma"}


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


def bandpass(x, fs, low=LOW_FREQ, high=HIGH_FREQ, order=BUTTER_ORDER):
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
            harmonics=NOTCH_HARMONICS, summary_hz=SUMMARY_HZ):
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
                   "summary_hz": float(summary_hz),
                   "nperseg": WELCH_NPERSEG, "noverlap": WELCH_NOVERLAP,
                   "nfft": WELCH_NFFT},
    }

    # coherence -----------------------------------------------------------
    f, cxy = coherence_curve(a, b, fs)
    i = int(np.argmin(np.abs(f - float(summary_hz))))
    out["coherence"] = {
        "summary": {
            "value": round(float(cxy[i]), 6),
            "x": round(float(f[i]), 4),
            "x_unit": "Hz",
            "what": "magnitude-squared coherence at %g Hz"
                    % float(summary_hz),
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
# The three methods, in a band (arc_contracts.md 7.1)
# --------------------------------------------------------------------------
# `metrics` above is the cluster's: coherence READ AT one frequency, `raw_cc`
# on the broadband trace, `amp_cc` on the theta envelope. Asked in three
# bands, two of those stop answering the question:
#
#   * coherence at 8 Hz says nothing about beta, and one bin of a 0.5 Hz
#     grid is a noisy estimate of a 17 Hz-wide band. In a band it is the
#     MEAN of the Welch curve over every bin in [low, high], ends included.
#   * `raw_cc` on the unfiltered trace is the same number in every band --
#     the band never touches it. In a band it is the cross-correlation of the
#     two BAND-PASSED traces (the same zero-phase Butterworth `amp_cc` uses),
#     so it can say whether the band's own oscillations line up, and at what
#     lag.
#   * `amp_cc` is already a band measurement and is unchanged: the envelope
#     of that band, peak |r| within the band's own lag bound.
#
# Everything around them is shared with `metrics` so a band result and a
# classic one are the same measurement up to those two changes: the same
# notch run first, the same Welch segments, the same `_xcorr_coeff`, the same
# refusals. The notched traces and each band's filtered traces are made ONCE
# per region per window by `_BandCache` below, not once per region pair --
# the arithmetic is identical and a region sits in eleven pairs.
COHERENCE_MODE_BAND = "band"


def band_coherence(f, cxy, low, high):
    """Mean magnitude-squared coherence over [low, high] Hz, and its bins.

    Both ends included. The Welch grid here is 0.5 Hz and lands on whole
    and half hertz, so 4-12 Hz is seventeen bins; the tolerance is only so a
    grid that is not exactly representable cannot drop an end bin silently.
    """
    f = np.asarray(f, dtype=np.float64)
    keep = (f >= float(low) - 1e-6) & (f <= float(high) + 1e-6)
    if not keep.any():
        raise CouplingError(
            "No coherence bin falls inside %g-%g Hz on a %g Hz grid, so there "
            "is nothing to average." % (low, high,
                                        float(f[1] - f[0]) if f.size > 1
                                        else float("nan")))
    return float(np.mean(np.asarray(cxy, dtype=np.float64)[keep])), \
        int(keep.sum())


class _BandCache(object):
    """One window's per-region signals, prepared once: notched, then
    band-passed and enveloped per band on first use. A failure is kept and
    raised again each time it is asked for, so every region pair it touches
    is refused with the same sentence."""

    def __init__(self, fs, notch_hz, harmonics=NOTCH_HARMONICS):
        self.fs = float(fs)
        self.notch_hz = notch_hz
        self.harmonics = harmonics
        self._got = {}

    def _get(self, key, make):
        if key not in self._got:
            try:
                self._got[key] = (make(), None)
            except CouplingError as exc:
                self._got[key] = (None, exc)
        val, exc = self._got[key]
        if exc is not None:
            raise exc
        return val

    def notched(self, name, sig):
        return self._get(("n", name), lambda: notch(
            np.asarray(sig, dtype=np.float64), self.fs, self.notch_hz,
            self.harmonics)[0])

    def banded(self, name, sig, low, high):
        return self._get(("b", name, low, high), lambda: bandpass(
            self.notched(name, sig), self.fs, low, high))

    def envelope(self, name, sig, low, high):
        return self._get(("e", name, low, high), lambda: envelope(
            self.notched(name, sig), self.fs, low, high))


def band_metrics(a, b, spec, fs=ANALYSIS_FS, notch_hz=NOTCH_HZ, curves=True,
                 harmonics=NOTCH_HARMONICS, cache=None, names=("a", "b"),
                 coherence=None):
    """The three methods between two signals in ONE band.

    `spec` is a `band_spec` ({id, low, high, max_lag_ms}). Same shape as
    `metrics` -- `{coherence, raw_cc, amp_cc}` each with `summary` and
    `curve` -- so everything that reads one reads the other. `coherence`
    may be the (f, Cxy) already computed for this pair: it does not depend
    on the band, so a pair asked about three bands estimates it once.
    """
    a, b = _check_pair(a, b)
    cache = cache or _BandCache(fs, notch_hz, harmonics)
    na_, nb_ = names
    low, high = float(spec["low"]), float(spec["high"])
    max_lag_s = float(spec["max_lag_ms"]) / 1000.0
    na = cache.notched(na_, a)
    nb = cache.notched(nb_, b)
    if coherence is None:
        coherence = coherence_curve(na, nb, fs)
    f, cxy = coherence
    val, n_bins = band_coherence(f, cxy, low, high)
    out = {
        "coherence": {
            "summary": {
                "value": round(val, 6),
                "x": None,
                "x_unit": "Hz",
                "what": "mean coherence over %g–%g Hz" % (low, high),
                "n_bins": n_bins,
            },
            "curve": _curve(f, cxy, "Hz", "coherence") if curves else None,
        },
    }

    ba = cache.banded(na_, a, low, high)
    bb = cache.banded(nb_, b, low, high)
    lags, r = _xcorr_coeff(ba, bb, fs, max_lag_s)
    val, lag = _peak(lags, r)
    out["raw_cc"] = {
        "summary": {
            "value": round(val, 6),
            "abs": round(abs(val), 6),
            "x": round(lag, 3),
            "x_unit": "ms",
            "what": "peak |r| of the %g–%g Hz band-passed signals within "
                    "+/-%g ms, and where it sat"
                    % (low, high, max_lag_s * 1000.0),
            "lag_note": "positive means the first region follows the second",
        },
        "curve": _curve(lags, r, "ms", "r") if curves else None,
    }

    ea = cache.envelope(na_, a, low, high)
    eb = cache.envelope(nb_, b, low, high)
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

    MINUS `kept`. The third field, in the same two shapes: blocks somebody
    looked at on the traces and put back in against the measurement. The
    measurement still says the amplifier touched its rail there, and it is
    kept in `clipped` because it is still true; `kept` is the judgement that
    it does not matter. So a channel is left out of a window when it was
    clipped or excluded there AND nobody kept it. An event with no `kept`
    gives exactly the union it always gave.
    """
    base = _excluded_union(event)
    kept = (event or {}).get("kept")
    if not kept:
        return base
    k_per, k_flat = _csc_shape(kept)
    if isinstance(base, list) and not k_per:
        return sorted(set(base) - k_flat)
    # A per-window keep on a flat exclusion: the flat exclusion meant every
    # window, so it is written out per window before anything is taken off.
    names = list(CLIP_WINDOW_NAMES) + list(TRANSITION_WINDOW_NAMES)
    per = ({w: set(base) for w in names} if isinstance(base, list)
           else {w: set(v) for w, v in base.items()})
    for w in list(per):
        per[w] -= k_flat | k_per.get(w, set())
    return {w: sorted(v) for w, v in per.items()}


def _csc_shape(got):
    """({window: set}, flat set) from either shape a channel list takes."""
    per, flat = {}, set()
    if isinstance(got, dict):
        for wname, chans in got.items():
            have = per.setdefault(str(wname), set())
            for c in (chans or []):
                try:
                    have.add(int(c))
                except (TypeError, ValueError):
                    continue
        return per, flat
    for c in (got or []):
        try:
            flat.add(int(c))
        except (TypeError, ValueError):
            continue
    return per, flat


def _excluded_union(event):
    """`clipped` union `excluded`, the shape `excluded_for` always returned."""
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
    # The transition windows too, and for the same reason: a channel
    # somebody dropped for the whole event is dropped at its boundaries as
    # well. Without these keys a flat exclusion reached the state windows
    # and silently missed the transition ones.
    for wname in TRANSITION_WINDOW_NAMES:
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

#: The three transition windows, from the same place.
TRANSITION_WINDOW_NAMES = tuple(spark.TRANSITION_WINDOWS)
WINDOW_KINDS = tuple(spark.KINDS)

#: The rest window (arc_contracts.md 7.3): one 10 s epoch of FP1 or FP2,
#: named `rest` in every epoch, so the epochs are the samples of one window
#: exactly as cue pairs are the samples of `pre`.
REST_WINDOW_NAMES = tuple(spark.REST_WINDOWS)


def windows_of(kind="state"):
    """The window names of one kind of analysis, in order.

    State is the four chunks of a pair; transition is the three boundaries;
    rest is one epoch of a no-cue recording. Anything else is refused rather
    than defaulted, because a run made in the wrong kind of window is a
    matrix labelled with the wrong question.
    """
    if kind == "state":
        return CLIP_WINDOW_NAMES
    if kind == "transition":
        return TRANSITION_WINDOW_NAMES
    if kind == "rest":
        return REST_WINDOW_NAMES
    raise CouplingError("There is no %r kind of analysis; it is state, "
                        "transition or rest." % (kind,))


def _exclude_map(exclude, windows):
    """{window name: set of CSC} from either shape the caller may pass.

    A flat list means "not valid for this event at all" and applies to
    every window; a dict names the windows one at a time. Both are real:
    somebody dropping a whole channel means the first, and the clipping
    measurement means the second.

    `windows` may be the `(name, t0, t1)` triples the signal engine works
    in, or plain window names. Both, because `w[0]` on a triple is the
    name and `w[0]` on the string "pre" is "p" -- so a caller holding
    names got a map keyed by first letters, every lookup missed, and the
    exclusion silently did nothing while the result still looked
    complete. Caught by a smoke test that marked four channels clipped
    and watched the picker choose one of them anyway.
    """
    names = [w if isinstance(w, str) else w[0] for w in windows]
    if isinstance(exclude, dict):
        return {n: {int(c) for c in (exclude.get(n) or [])} for n in names}
    flat = {int(c) for c in (exclude or [])}
    return {n: set(flat) for n in names}


def _signals_for_windows(folder, chan_map, windows, exclude=(),
                         target_fs=ANALYSIS_FS, progress=None, blocked=None):
    """Every region's signal in every window: the shared engine.

    `region_signals` is one window of this and `pair_connectivity` is four.
    They share it because the cost is opening 32 files, and doing that once
    per window rather than once per pair is four times the work for the same
    answer.

    ONE WIRE PER REGION PER WINDOW: the lowest-numbered channel in the region
    that has a signal there -- not marked bad, not clipped, and readable.
    See "Channel sanity" below for why one wire rather than an average. The
    rule lives HERE, in the engine, and not only in `channel_sanity`,
    because the wire a result reports has to be the wire it was computed
    from; a preview that picks one way and an engine that picks another is
    a label on the wrong number.

    `blocked` is `{region name: sentence}` for regions that must not be
    computed at all, whatever their wires look like -- histology, where the
    probe is not in the region, or is in one nobody has checked. Those are
    refused with that sentence and their files are not opened.
    """
    blocked = dict(blocked or {})
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

    wanted = sorted({int(c) for name, csc in chan_map.items()
                     if name not in blocked for c in csc})
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
        # Two regions are correlated against each other on one time axis.
        # Two channels at two rates are two different time axes, and a
        # correlation between them is nonsense before anything else gets a
        # chance to be wrong.
        raise CouplingError(
            "The channels in this recording do not share a sampling rate "
            "(%s Hz). There is no single time axis to correlate on."
            % ", ".join(str(f) for f in sorted(fs_seen)))
    source_fs = float(sorted(fs_seen)[0])

    out = {}
    for wname, t0, t1 in windows:
        regions = {}
        for name, csc in chan_map.items():
            if name in blocked:
                regions[name] = {
                    "signal": None, "channel": None, "channels": [],
                    "dropped": [], "spare": [], "n": 0, "usable": False,
                    "blocked": "histology", "why": blocked[name],
                    "of": len(csc),
                }
                continue
            used, dropped, stack = [], [], []
            # Ascending, because "lowest-numbered" is the rule and the
            # montage's own order is only ascending by coincidence.
            for num in sorted(int(c) for c in csc):
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
                    "signal": None, "channel": None, "channels": [],
                    "dropped": dropped, "spare": [], "n": 0,
                    "usable": False, "blocked": "wires",
                    "why": ("none of %s's %d channels are usable in this "
                            "window" % (name, len(csc))),
                    "of": len(csc),
                }
                continue
            # The lowest-numbered wire with a signal. `used` is ascending,
            # so it is the first. The rest are recorded as spares -- not
            # used, but there, which is the difference between a region
            # measured on its last wire and one with three to spare.
            chosen = used[0]
            sig, fs_out = decimate_to(stack[0], source_fs, target_fs)
            regions[name] = {
                "signal": sig, "channel": chosen, "channels": [chosen],
                "spare": used[1:],
                # Only the wires BELOW the chosen one explain the choice;
                # a clipped wire above it was never going to be picked.
                "passed_over": [d for d in dropped if d["csc"] < chosen],
                "dropped": dropped,
                "n": int(sig.size), "usable": True, "blocked": None,
                "why": None, "of": len(csc),
            }
        out[wname] = {
            "t0": float(t0), "t1": float(t1),
            "fs": float(target_fs), "source_fs": source_fs,
            "regions": regions,
        }
    return out


# --------------------------------------------------------------------------
# Channel sanity: which wire a region is actually measured on
# --------------------------------------------------------------------------
#
# A region is four channels, or two, and in this data a good fraction of
# them are at the amplifier's rail for part of an event. Two ways to turn
# that into one signal, and they are not equivalent:
#
#   average       mean of whatever wires survived. More signal, but the
#                 number of wires changes between windows and between
#                 recordings, so `pre` and `cue1` can be an average of four
#                 and an average of one and nothing in the output says so.
#                 A correlation computed on an average of four wires is not
#                 the same measurement as one computed on a single wire,
#                 and comparing them across windows is comparing two
#                 different measurements.
#
#   representative  one wire, chosen by a fixed rule, or none. Every window
#                 of every recording is then the same KIND of measurement,
#                 and where no wire qualifies the answer is "blocked", not
#                 a quietly thinner average.
#
# `representative` is the default, for both reasons above and because it is
# what the cluster pipeline did -- "12 representative channels, one per
# region" -- so the matrices this produces can be laid beside those.
#
# The rule is: the LOWEST-NUMBERED channel in the region that is neither
# marked bad for the recording nor clipped in this window. Lowest-numbered
# rather than best-looking, because "best" would be chosen by a statistic
# computed on the same data the correlation is computed on, and a wire
# picked for looking clean is a wire picked for its noise.

CHANNEL_POLICIES = ("representative", "average")
DEFAULT_CHANNEL_POLICY = "representative"

BLOCKED_BAD = "bad"
BLOCKED_CLIPPED = "clipped"
BLOCKED_ABSENT = "absent"
BLOCKED_HISTOLOGY = "histology"


def representative(csc, bad=(), clipped=(), present=None):
    """The one channel a region is measured on, or None.

    `csc` is the montage's channels for the region, in montage order.
    `bad` is marked bad for the whole recording; `clipped` is what the
    amplifier saturated on in THIS window; `present` (optional) is the
    channels the recording actually has, so a montage that names 32 wires
    on a recording that has 16 does not pick one that is not there.

    Returns `(channel_or_None, why)`, where `why` is a dict of what each
    channel was rejected for -- kept even on success, because "we used
    CSC 6 because 5 clipped" is the sentence somebody needs when two
    windows of one region disagree.
    """
    bad = {int(c) for c in (bad or [])}
    clip = {int(c) for c in (clipped or [])}
    have = None if present is None else {int(c) for c in present}
    rejected, chosen = {}, None
    for num in sorted(int(c) for c in (csc or [])):
        if have is not None and num not in have:
            rejected[num] = BLOCKED_ABSENT
            continue
        if num in bad:
            rejected[num] = BLOCKED_BAD
            continue
        if num in clip:
            rejected[num] = BLOCKED_CLIPPED
            continue
        if chosen is None:
            chosen = num
    return chosen, rejected


def _blocked_why(region, rejected, n):
    """Why a region has no usable wire in this window, in words.

    Names the reason for every wire rather than giving a count, because
    "all four clipped" and "two are bad and two clipped" are different
    problems -- the first is this event, the second is the recording.
    """
    if not n:
        return ("%s has no channels on this recording at all." % region)
    kinds = {}
    for num, why in rejected.items():
        kinds.setdefault(why, []).append(num)
    say = []
    order = (BLOCKED_CLIPPED, BLOCKED_BAD, BLOCKED_ABSENT)
    words = {
        BLOCKED_CLIPPED: "clipped in this window",
        BLOCKED_BAD: "marked bad for the whole recording",
        BLOCKED_ABSENT: "not present on this recording",
    }
    for kind in order:
        got = sorted(kinds.get(kind) or [])
        if got:
            say.append("CSC " + ", ".join(str(c) for c in got)
                       + " " + ("is " if len(got) == 1 else "are ")
                       + words[kind])
    return ("%s is blocked here: %s. Nothing is computed for it in this "
            "window, and the cells in its row and column are blank rather "
            "than zero." % (region, "; ".join(say)))


def channel_sanity(regions, bad=(), clipped_by_window=None,
                   windows=None, present=None, probe=None):
    """One record per region: which wire it is measured on, per window.

    `clipped_by_window` is `{window: [CSC, ...]}` -- what `excluded_for`
    returns for a banked event, or `spark.clipping_for` for a fresh one. A
    flat list is accepted and means every window, which is what a flat list
    has always meant here.

    `probe` is `histo.probe_sanity(...)` output, keyed by slot. When it is
    given, a region whose probe missed is blocked for every window BEFORE
    any channel is looked at -- there is no point choosing the cleanest
    wire in a region the probe is not in.

    Returns a list in `regions` order. Each record carries, per window,
    either the chosen channel or `blocked` with a sentence.
    """
    names = tuple(windows or CLIP_WINDOW_NAMES)
    per = _exclude_map(clipped_by_window or {}, names)
    by_slot = {p.get("slot"): p for p in (probe or [])}

    out = []
    for r in (regions or []):
        if not isinstance(r, dict):
            raise CouplingError(
                "A region has to be a dict with its channels; got %r." % (r,))
        slot = r.get("id")
        name = r.get("region") or slot
        csc = [int(c) for c in (r.get("csc") or [])]
        here = r.get("csc_present")
        have = present if here is None else here

        hist = by_slot.get(slot)
        rec = {
            "slot": slot,
            "region": name,
            # The label the matrix draws. Histology decides it when we have
            # any; otherwise it is the montage's name.
            "label": (hist or {}).get("label") or name,
            "channels": csc,
            "windows": {},
            "blocked": [],
            "histology": (hist or {}).get("verdict"),
        }

        if hist is not None and not hist.get("usable"):
            for w in names:
                rec["windows"][w] = {
                    "channel": None, "blocked": BLOCKED_HISTOLOGY,
                    "rejected": {}, "why": hist.get("why"),
                }
            rec["blocked"] = list(names)
            out.append(rec)
            continue

        for w in names:
            chosen, rejected = representative(
                csc, bad=bad, clipped=per.get(w) or (), present=have)
            if chosen is None:
                rec["windows"][w] = {
                    "channel": None,
                    "blocked": (BLOCKED_ABSENT if not csc else
                                _worst(rejected)),
                    "rejected": {str(k): v for k, v in rejected.items()},
                    "why": _blocked_why(rec["label"], rejected, len(csc)),
                }
                rec["blocked"].append(w)
            else:
                rec["windows"][w] = {
                    "channel": chosen,
                    "blocked": None,
                    "rejected": {str(k): v for k, v in rejected.items()},
                    "why": _chose_why(rec["label"], chosen, rejected),
                }
        out.append(rec)
    return out


def _worst(rejected):
    """One word for why a region is blocked, when several apply.

    Clipping first: it is the one that is about this event and might be
    recovered by dropping a window, where a bad channel is a fact about
    the recording and will be true in every window.
    """
    kinds = set(rejected.values())
    for kind in (BLOCKED_CLIPPED, BLOCKED_BAD, BLOCKED_ABSENT):
        if kind in kinds:
            return kind
    return BLOCKED_CLIPPED


def _chose_why(region, chosen, rejected):
    if not rejected:
        return ("%s is measured on CSC %d, the lowest-numbered channel it "
                "has. Nothing was rejected." % (region, chosen))
    skipped = sorted(k for k in rejected if k < chosen)
    if not skipped:
        return ("%s is measured on CSC %d, the lowest-numbered channel it "
                "has." % (region, chosen))
    return ("%s is measured on CSC %d: CSC %s %s not usable here, so the "
            "next one up was taken."
            % (region, chosen, ", ".join(str(c) for c in skipped),
               "was" if len(skipped) == 1 else "were"))


def blocked_pairs(sanity, window):
    """The region pairs that cannot be computed in one window, and why.

    A pair is blocked when EITHER side is, and the reason names the side
    that is blocked -- both, when both are. This is what the matrix draws
    over a cell instead of a number, so the sentence has to stand alone.
    """
    by = {r["region"]: r for r in (sanity or [])}
    names = [r["region"] for r in (sanity or [])]
    out = {}
    for a, b in region_pairs(names):
        wa = (by[a]["windows"].get(window) or {})
        wb = (by[b]["windows"].get(window) or {})
        why = [w.get("why") for w in (wa, wb) if w.get("channel") is None]
        if why:
            out[(a, b)] = "  ".join(w for w in why if w)
    return out


# --------------------------------------------------------------------------
# What somebody may change before a run, and what they may not
# --------------------------------------------------------------------------
#
# Shown and editable in the Coupling panel before anything is computed, so
# the corners a matrix was made with are a choice somebody made while
# looking at them rather than a constant in a file. Every one is checked
# here, on the server, and a value out of range is refused with a sentence
# -- never clamped, because a run silently made at different corners than
# the ones on screen is the exact failure these are on screen to prevent.
#
# Two are shown and NOT editable, and say why:
#
#   analysis rate  the Welch segment is 1000 samples, so at 1000 Hz it is
#                  one second and the coherence resolution is 0.5 Hz; at
#                  any other rate both change, and the matrix stops being
#                  comparable to the cluster's.
#   channel rule   one wire per region, lowest-numbered usable. Decided,
#                  and the reason is under "Channel sanity" above.

PARAMS = [
    {"id": "low", "name": "Band, low edge", "unit": "Hz",
     "default": LOW_FREQ, "min": 0.5, "max": 200.0, "step": 0.5,
     "say": "The bottom of the band the two correlations are filtered to. "
            "Theta is 4 to 12."},
    {"id": "high", "name": "Band, high edge", "unit": "Hz",
     "default": HIGH_FREQ, "min": 1.0, "max": 250.0, "step": 0.5,
     "say": "The top of the band. Must be above the low edge and below "
            "half the analysis rate."},
    {"id": "summary_hz", "name": "Coherence read at", "unit": "Hz",
     "default": SUMMARY_HZ, "min": 0.5, "max": 250.0, "step": 0.5,
     "say": "Coherence is a curve; the matrix needs one number, so it is "
            "read at this frequency. It has to sit inside the band, or the "
            "coherence cell describes a frequency the other two methods "
            "filtered out."},
    {"id": "max_lag_ms", "name": "Largest lag", "unit": "ms",
     "default": MAX_LAG_SEC * 1000.0, "min": 10.0, "max": 2000.0,
     "step": 10.0,
     "say": "How far either way the two correlations look for their peak. "
            "Wider finds more, and a maximum over more lags is larger by "
            "chance alone."},
    {"id": "notch_hz", "name": "Mains notch", "unit": "Hz",
     "default": NOTCH_HZ, "choices": [None, 50.0, 60.0],
     "say": "Removes mains and its harmonics before correlating. 60 Hz is "
            "inside the band a 1000 Hz signal covers, and a peak over a "
            "thousand lags will find it and call it coupling."},
    {"id": "pad_s", "name": "Baseline either side", "unit": "s",
     "default": spark.CLIP_PAD_S, "min": 1.0, "max": spark.CLIP_PAD_S,
     "step": 0.5, "kind": "state",
     "say": "The length of the pre and post windows. It cannot be longer "
            "than the windows the clipping was measured over: anything "
            "past them has never been checked, and a railed stretch there "
            "would go into the analysis unseen."},
    # The transition windows' lengths. Bounded by the lengths Spark
    # measured the transition clipping with, exactly as `pad_s` is bounded
    # by the baseline it measured -- a shorter window sits inside what was
    # checked, a longer one reaches into samples nobody looked at.
    {"id": "before_s", "name": "Before each boundary", "unit": "s",
     "default": spark.TRANSITION_BEFORE_S, "min": spark.TRANSITION_MIN_S,
     "max": spark.TRANSITION_MAX_S, "step": 0.1, "kind": "transition",
     "say": "How far ahead of cue 1 starting, of cue 2 starting, and of cue "
            "2 ending each transition window begins. It cannot be longer "
            "than the clipping was measured over."},
    {"id": "after_s", "name": "After each boundary", "unit": "s",
     "default": spark.TRANSITION_AFTER_S, "min": spark.TRANSITION_MIN_S,
     "max": spark.TRANSITION_MAX_S, "step": 0.1, "kind": "transition",
     "say": "How far past each boundary the transition window runs. Before "
            "and after together have to make at least a second, the length "
            "of one coherence segment."},
    {"id": "analysis_fs", "name": "Analysis rate", "unit": "Hz",
     "default": ANALYSIS_FS, "fixed": True,
     "say": "Fixed. The Welch segment is 1000 samples, so at 1000 Hz it is "
            "one second; at any other rate the coherence resolution changes "
            "and the result stops being comparable to the cluster's."},
    {"id": "channel_rule", "name": "Channel per region", "unit": "",
     "default": "lowest-numbered usable wire", "fixed": True,
     "say": "One wire per region per window: the lowest-numbered channel "
            "that is not marked bad and did not clip there. Averaging "
            "would make each window a different kind of measurement."},
]

_PARAM_BY_ID = {p["id"]: p for p in PARAMS}


def default_params():
    return {p["id"]: p["default"] for p in PARAMS}


def params_for(kind="state"):
    """The PARAMS a panel shows for one kind of run: the shared ones, and
    the window lengths of that kind only. A baseline field on a transition
    run, or a before-the-boundary field on a state one, would be a control
    that changes nothing."""
    windows_of(kind)
    return [p for p in PARAMS if p.get("kind") in (None, kind)]


#: The body keys a band replaces. In band mode they are not read from the
#: body at all: the band says the edges and the lag, and there is no single
#: frequency coherence is read at.
_BAND_OWNS = ("low", "high", "max_lag_ms", "summary_hz")


def _band_number(pid, raw, band_id):
    """One of a band's own numbers, checked against the same limits PARAMS
    puts on the field it replaces. Refused, never clamped."""
    spec = _PARAM_BY_ID[pid]
    try:
        val = float(raw)
    except (TypeError, ValueError):
        raise CouplingError("The %s band's %s: %r is not a number."
                            % (band_id, spec["name"].lower(), raw))
    if not np.isfinite(val):
        raise CouplingError("The %s band's %s has to be a finite number."
                            % (band_id, spec["name"].lower()))
    lo, hi = spec.get("min"), spec.get("max")
    if (lo is not None and val < lo) or (hi is not None and val > hi):
        raise CouplingError("The %s band's %s has to be between %g and %g "
                            "%s, not %g." % (band_id, spec["name"].lower(),
                                             lo, hi, spec["unit"], val))
    return val


def band_spec(band, analysis_fs=ANALYSIS_FS):
    """One band as `{id, low, high, max_lag_ms}`, from its id or a dict.

    A dict may carry its own `low`, `high` and `max_lag_ms`; anything it
    leaves out is the named band's. The id has to be one of BANDS -- a
    circuit's name and its artifact's key are made from it, and an id
    nobody defined is a label nobody can read. Refuses, never clamps.
    """
    if isinstance(band, dict):
        bid = band.get("id") or band.get("band")
        over = band
    else:
        bid, over = band, {}
    bid = str(bid or "").strip()
    if bid not in BANDS:
        raise CouplingError(
            "%r is not a band. The bands are %s." % (
                bid or band, ", ".join("%s (%g–%g Hz)" % (
                    b, BANDS[b]["low"], BANDS[b]["high"])
                    for b in BAND_ORDER)))
    out = dict(BANDS[bid])
    for pid in ("low", "high", "max_lag_ms"):
        if over.get(pid) is not None:
            out[pid] = _band_number(pid, over[pid], bid)
    nyq = float(analysis_fs) / 2.0
    if not out["low"] < out["high"]:
        raise CouplingError("The %s band's low edge (%g Hz) has to be below "
                            "its high edge (%g Hz)."
                            % (bid, out["low"], out["high"]))
    if out["high"] >= nyq:
        raise CouplingError("The %s band's high edge (%g Hz) has to be below "
                            "half the analysis rate (%g Hz)."
                            % (bid, out["high"], nyq))
    return out


def band_ids(bands):
    """The band ids a caller asked for, checked, in the order asked, no
    repeats. None stays None: no bands is the classic single-band run."""
    if bands is None:
        return None
    if isinstance(bands, (str, dict)):
        bands = [bands]
    specs = [band_spec(b) for b in bands]
    if not specs:
        raise CouplingError("No bands were asked for. Name at least one of "
                            "%s, or leave `bands` out for the classic run."
                            % ", ".join(BAND_ORDER))
    seen = [s["id"] for s in specs]
    dup = sorted({b for b in seen if seen.count(b) > 1})
    if dup:
        raise CouplingError("The %s band is asked for twice. One band is one "
                            "circuit." % ", ".join(dup))
    return specs


def read_params(body, measured_pad_s=None, kind="state",
                measured_transition=None, band=None):
    """The run's parameters, from what the panel sent. Refuses, never clamps.

    `measured_pad_s` is the baseline the clipping was measured over for
    this recording, when the bank says. A longer baseline would read data
    nobody checked, so it is the ceiling whatever PARAMS says.

    `kind` is "state", "transition" or "rest". For a transition run
    `measured_transition` is `(before_s, after_s)` as the bank says the
    transition clipping was measured, and each is the ceiling on its own
    length for the same reason. The baseline bound applies only to a state
    run, and the transition bounds only to a transition run: each kind
    reads only its own windows.

    `band` (an id or a `band_spec` dict) makes these ONE band's parameters
    (arc_contracts.md 7.1): today's output with `low`, `high` and
    `max_lag_ms` from the band, `summary_hz` None (a band's coherence is
    the mean over the band, read at no one frequency), and `band`,
    `coherence_mode: "band"`, `raw_cc_filtered: true` added. Without it
    the output is exactly what it always was.
    """
    if band is not None:
        spec = band_spec(band)
        rest = {k: v for k, v in (body or {}).items()
                if k not in _BAND_OWNS}
        out = read_params(rest, measured_pad_s, kind, measured_transition)
        out.update(low=float(spec["low"]), high=float(spec["high"]),
                   max_lag_ms=float(spec["max_lag_ms"]), summary_hz=None,
                   band=spec["id"], coherence_mode=COHERENCE_MODE_BAND,
                   raw_cc_filtered=True)
        return out
    windows_of(kind)
    body = body or {}
    out = default_params()
    for pid, spec in _PARAM_BY_ID.items():
        if pid not in body or spec.get("fixed"):
            continue
        raw = body[pid]
        if "choices" in spec:
            val = None if raw in (None, "", "off", False) else raw
            try:
                val = None if val is None else float(val)
            except (TypeError, ValueError):
                raise CouplingError("%s: %r is not one of the choices."
                                    % (spec["name"], raw))
            if val not in spec["choices"]:
                raise CouplingError(
                    "%s has to be one of %s, not %s."
                    % (spec["name"],
                       ", ".join("off" if c is None else "%g" % c
                                 for c in spec["choices"]), raw))
            out[pid] = val
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise CouplingError("%s: %r is not a number." % (spec["name"], raw))
        if not np.isfinite(val):
            raise CouplingError("%s has to be a finite number." % spec["name"])
        lo, hi = spec.get("min"), spec.get("max")
        if (lo is not None and val < lo) or (hi is not None and val > hi):
            raise CouplingError("%s has to be between %g and %g %s, not %g."
                                % (spec["name"], lo, hi, spec["unit"], val))
        out[pid] = val

    nyq = out["analysis_fs"] / 2.0
    if not out["low"] < out["high"]:
        raise CouplingError("The band's low edge (%g Hz) has to be below its "
                            "high edge (%g Hz)." % (out["low"], out["high"]))
    if out["high"] >= nyq:
        raise CouplingError("The band's high edge (%g Hz) has to be below "
                            "half the analysis rate (%g Hz)."
                            % (out["high"], nyq))
    if not out["low"] <= out["summary_hz"] <= out["high"]:
        raise CouplingError(
            "Coherence is read at %g Hz, which is outside the %g to %g Hz "
            "band. The coherence cell would describe a frequency the other "
            "two methods filtered out; move it inside the band."
            % (out["summary_hz"], out["low"], out["high"]))
    if (kind == "state" and measured_pad_s is not None
            and out["pad_s"] > float(measured_pad_s)):
        raise CouplingError(
            "The baseline is %g s either side, but this recording's clipping "
            "was only measured over %g s. The extra has never been checked; "
            "make it %g s or less, or re-run the clipping check with a wider "
            "window." % (out["pad_s"], measured_pad_s, measured_pad_s))
    if kind == "transition":
        if out["before_s"] + out["after_s"] < spark.TRANSITION_MIN_TOTAL_S:
            raise CouplingError(
                "A transition window of %g s before and %g s after is %g s "
                "long; coherence is estimated on one-second segments, so it "
                "has to be at least %g s in all."
                % (out["before_s"], out["after_s"],
                   out["before_s"] + out["after_s"],
                   spark.TRANSITION_MIN_TOTAL_S))
        if measured_transition is not None:
            mb, ma = (float(x) for x in measured_transition)
            for pid, cap, word in (("before_s", mb, "before"),
                                   ("after_s", ma, "after")):
                if out[pid] > cap + 1e-9:
                    raise CouplingError(
                        "The transition window runs %g s %s each boundary, "
                        "but this recording's transition clipping was only "
                        "measured to %g s %s. The extra has never been "
                        "checked; make it %g s or less, or re-run the "
                        "clipping check in Spark with a longer window."
                        % (out[pid], word, cap, word, cap))
    out["kind"] = kind
    return out


def sanity_from_run(run, probe=None):
    """What the matrix draws on its axes and blocked cells, built from the
    run itself.

    Not from `channel_sanity`. That one is the PREVIEW -- what the rule
    will pick, worked out from the bank before a single file is opened --
    and the engine can disagree with it for a reason the bank cannot see:
    a wire whose file will not read. The matrix labels a number, so it
    takes its labels from the thing that produced the number.
    """
    by_slot = {}
    by_region = {}
    for rec in (probe or []):
        by_slot[rec.get("slot")] = rec
        by_region[rec.get("intended")] = rec
    names = list(run.get("region_order") or [])
    wins = run.get("windows") or []
    out = []
    for name in names:
        hist = by_region.get(name) or {}
        label = hist.get("label") or name
        rec = {"region": name, "label": label,
               "histology": hist.get("verdict"),
               "histology_why": hist.get("why"),
               "windows": {}}
        for w in wins:
            r = (w.get("regions") or {}).get(name) or {}
            ch = r.get("channel")
            if ch is not None:
                over = r.get("passed_over") or []
                why = ("%s is measured on CSC %d." % (label, ch)
                       if not over else
                       "%s is measured on CSC %d: CSC %s %s not usable here "
                       "(%s), so the next one up was taken."
                       % (label, ch,
                          ", ".join(str(d["csc"]) for d in over),
                          "was" if len(over) == 1 else "were",
                          "; ".join("%d %s" % (d["csc"], d["why"])
                                    for d in over)))
            elif r.get("blocked") == "histology":
                why = r.get("why")
            else:
                gone = r.get("dropped") or []
                why = ("%s has no usable wire in this window: %s. Nothing "
                       "is computed for it here, so the cells in its row "
                       "and column are blank rather than zero."
                       % (label, "; ".join("CSC %d %s" % (d["csc"], d["why"])
                                           for d in gone) or "no channels"))
            rec["windows"][w.get("window")] = {
                "channel": ch, "spare": r.get("spare") or [],
                "blocked": r.get("blocked"), "why": why,
            }
        out.append(rec)

    blocked = {}
    n_pairs = len(region_pairs(names))
    for w in wins:
        dead = [r["region"] for r in out
                if (r["windows"].get(w.get("window")) or {}).get("channel")
                is None]
        blocked[w.get("window")] = {
            "n": n_pairs - len(region_pairs([n for n in names
                                             if n not in dead])),
            "of": n_pairs, "regions": dead,
        }
    return {"channel_sanity": out, "blocked": blocked}


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
                      pad_s=spark.CLIP_PAD_S, curves=False, progress=None,
                      blocked_regions=None, summary_hz=SUMMARY_HZ,
                      kind="state", before_s=spark.TRANSITION_BEFORE_S,
                      after_s=spark.TRANSITION_AFTER_S, bands=None):
    """One cue pair: four windows, 66 region pairs, three methods each.

    `bands` (arc_contracts.md 7.1) is a list of bands -- ids or `band_spec`
    dicts. Each wire is read and decimated ONCE, and the three methods are
    computed in every band from that one read (`band_metrics`). The answer
    is then `{"bands": {band id: <exactly this function's classic output,
    for that band>}, "band_order": [...], ...the keys the bands share}`, so
    `circuit.build`, `sanity_from_run` and the CSV read one band's result
    as they read a classic one. `low`, `high`, `max_lag_s` and `summary_hz`
    are ignored in band mode: each band carries its own. Without `bands`
    nothing here changes: one band, from those four arguments.

    `kind="rest"` is one no-cue epoch (arc_contracts.md 7.3): `pair` is
    `{pair_id, label, t0, t1}` and the one window is `rest`, cut from those
    two times -- see `spark.rest_windows`. Everything else is the same
    engine.

    `kind="transition"` runs the same thing in the pair's three transition
    windows instead -- `spark.transition_windows`, `before_s` ahead of each
    boundary to `after_s` past it. Nothing else changes: one wire per region
    per window, the same exclusion keyed by window name (the transition
    windows' clipping is banked under `onset`, `switch` and `offset` in the
    same dicts), the same histology blocking. `pad_s` means nothing to a
    transition run and `before_s`/`after_s` nothing to a state one.

    `pair` is one of `spark.pair_events`'s pairs -- or a banked event that
    still carries its boundaries. The four windows are `spark.pair_windows`
    and are NOT redefined here: ten seconds before cue 1, cue 1, cue 2, ten
    seconds after cue 2 ends, bounded by the pair's own measured moments
    rather than by assuming each cue ran exactly ten seconds. One definition
    of a window, in the module that found the pair.

    `exclude_by_channel` is the CSC numbers this event is not valid on --
    `excluded_for(event)` for a banked one, plus the recording's bad
    channels. A region is then measured on its lowest-numbered wire that is
    not among them, in each window separately.

    `blocked_regions` is `{region name: sentence}` for regions histology
    rules out. They are refused for every window with that sentence.

    Every refusal is kept where it happened: a region pair that could not be
    measured is a row with `why` set and three Nones, not a missing row.
    """
    chan_map = region_map(regions)
    windows_of(kind)
    if kind == "transition":
        windows = spark.transition_windows(pair, before_s, after_s)
    elif kind == "rest":
        windows = spark.rest_windows(pair)
    else:
        windows = spark.pair_windows(pair, pad_s)
    exclude = (exclude_by_channel if isinstance(exclude_by_channel, dict)
               else sorted({int(c) for c in (exclude_by_channel or [])}))
    # Checked before a single file is opened: a band that does not exist is
    # a refusal of the run, not something to find out after the read.
    specs = band_ids(bands)

    got = _signals_for_windows(folder, chan_map, windows, exclude, target_fs,
                               progress=progress, blocked=blocked_regions)

    names = list(chan_map.keys())
    pairs_of = region_pairs(names)
    if specs is not None:
        return _pair_bands(folder, pair, windows, got, names, pairs_of,
                           exclude, specs, notch_hz, target_fs, pad_s, curves,
                           kind, before_s, after_s)
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
                            max_lag_s=max_lag_s, curves=curves,
                            summary_hz=summary_hz)
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
        out_windows.append(_window_out(wname, t0, t1, w, rows, refused))

    return _pair_out(pair, folder, out_windows, names, exclude, notch_hz,
                     _params_out(target_fs, low, high, max_lag_s, summary_hz,
                                 pad_s, kind, before_s, after_s))


def _window_out(wname, t0, t1, w, rows, refused):
    """One window of a pair result: where it was cut, which wire each region
    was measured on, and the region-pair rows. Shared by the classic run and
    every band of a band run, so the two cannot describe a window apart."""
    return {
        "window": wname,
        "t0": round(float(t0), 6), "t1": round(float(t1), 6),
        "duration_s": round(float(t1) - float(t0), 6),
        "fs": w["fs"], "source_fs": w["source_fs"],
        "n_samples": max((r["n"] for r in w["regions"].values()),
                         default=0),
        "regions": {name: {"channel": r.get("channel"),
                           "channels": r["channels"], "of": r.get("of"),
                           "spare": r.get("spare") or [],
                           "passed_over": r.get("passed_over") or [],
                           "usable": r["usable"],
                           "blocked": r.get("blocked"),
                           "why": r["why"], "dropped": r["dropped"]}
                    for name, r in w["regions"].items()},
        "pairs": rows,
        "n_pairs": len(rows),
        "n_refused": refused,
    }


def _notch_out(notch_hz, target_fs):
    lines = notch_lines(notch_hz, target_fs)
    return {"hz": float(notch_hz) if notch_hz else None,
            "applied": bool(lines),
            "lines_hz": [round(f, 3) for f in lines]}


def _params_out(target_fs, low, high, max_lag_s, summary_hz, pad_s, kind,
                before_s, after_s, band=None):
    """What a pair result says it was made with. `band` (a band_spec) adds
    the band's own fields; `summary_hz` is None for a band, whose coherence
    is read at no single frequency."""
    out = {
        "analysis_fs": float(target_fs),
        "low": float(low), "high": float(high),
        "max_lag_s": float(max_lag_s),
        "summary_hz": None if summary_hz is None else float(summary_hz),
        "nperseg": WELCH_NPERSEG, "noverlap": WELCH_NOVERLAP,
        "nfft": WELCH_NFFT,
        "methods": list(METHODS),
        "pad_s": float(pad_s),
        # Which question the windows answer. The lengths only for a
        # transition run: a state run has no boundary windows, and a
        # number there would be a claim about windows it never cut.
        "kind": kind,
        **({"before_s": float(before_s), "after_s": float(after_s)}
           if kind == "transition" else {}),
        # Where every one of these came from, carried with the result.
        # Circuit saves a matrix that has to be able to say what made
        # it, and a provenance line assembled later is a provenance line
        # somebody can get wrong.
        "source": "14 Correlation Data/compute_connectivity_windows.m",
    }
    if band is not None:
        out.update(band=band["id"], coherence_mode=COHERENCE_MODE_BAND,
                   raw_cc_filtered=True)
    return out


def _pair_out(pair, folder, out_windows, names, exclude, notch_hz, params):
    return {
        "pair_id": pair.get("pair_id"),
        "label": pair.get("label") or "%s -> %s" % (pair.get("opener_label"),
                                                    pair.get("closer_label")),
        "folder": folder,
        "windows": out_windows,
        "region_order": names,
        "excluded": exclude,
        "notch": _notch_out(notch_hz, params["analysis_fs"]),
        "params": params,
    }


def _pair_bands(folder, pair, windows, got, names, pairs_of, exclude, specs,
                notch_hz, target_fs, pad_s, curves, kind, before_s, after_s):
    """Every band of one pair from ONE read (`got`). See pair_connectivity.

    Per window, each region's trace is notched once and filtered once per
    band (`_BandCache`); per region pair, the Welch coherence curve is
    estimated once and averaged over each band. The rows each band gets are
    built exactly as the classic run builds them, refusals included.
    """
    per_band = {s["id"]: [] for s in specs}
    for wname, t0, t1 in windows:
        w = got[wname]
        cache = _BandCache(w["fs"], notch_hz)
        rows = {s["id"]: [] for s in specs}
        refused = {s["id"]: 0 for s in specs}
        for a_name, b_name in pairs_of:
            ra, rb = w["regions"][a_name], w["regions"][b_name]

            def base():
                return {"a": a_name, "b": b_name,
                        "a_channels": ra["channels"],
                        "b_channels": rb["channels"]}

            def refuse(bid, why):
                row = base()
                row["why"] = why
                for m in METHODS:
                    row[m] = None
                rows[bid].append(row)
                refused[bid] += 1

            if not ra["usable"] or not rb["usable"]:
                why = "; ".join(x["why"] for x in (ra, rb) if x.get("why"))
                for s in specs:
                    refuse(s["id"], why)
                continue
            try:
                a, b = _check_pair(ra["signal"], rb["signal"])
                coh = coherence_curve(cache.notched(a_name, a),
                                      cache.notched(b_name, b), w["fs"])
            except CouplingError as exc:
                for s in specs:
                    refuse(s["id"], str(exc))
                continue
            for s in specs:
                try:
                    m = band_metrics(a, b, s, w["fs"], notch_hz=notch_hz,
                                     curves=curves, cache=cache,
                                     names=(a_name, b_name), coherence=coh)
                except CouplingError as exc:
                    refuse(s["id"], str(exc))
                    continue
                row = base()
                row["why"] = None
                for name in METHODS:
                    row[name] = (m[name] if curves else m[name]["summary"])
                rows[s["id"]].append(row)
        for s in specs:
            per_band[s["id"]].append(_window_out(wname, t0, t1, w,
                                                 rows[s["id"]],
                                                 refused[s["id"]]))
    out = {
        "pair_id": pair.get("pair_id"),
        "label": pair.get("label") or "%s -> %s" % (pair.get("opener_label"),
                                                    pair.get("closer_label")),
        "folder": folder,
        "region_order": names,
        "excluded": exclude,
        "notch": _notch_out(notch_hz, target_fs),
        "kind": kind,
        "band_order": [s["id"] for s in specs],
        "bands": {},
    }
    for s in specs:
        params = _params_out(target_fs, s["low"], s["high"],
                             float(s["max_lag_ms"]) / 1000.0, None, pad_s,
                             kind, before_s, after_s, band=s)
        out["bands"][s["id"]] = _pair_out(pair, folder, per_band[s["id"]],
                                          names, exclude, notch_hz, params)
    return out


def split_bands(result):
    """{band id: that band's pair result} from a band run's output, or
    {None: result} for a classic one -- so a caller can walk either."""
    if isinstance(result, dict) and isinstance(result.get("bands"), dict):
        return {bid: result["bands"][bid]
                for bid in (result.get("band_order") or list(result["bands"]))}
    return {None: result}
