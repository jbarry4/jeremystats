"""
specparam.py -- separating the rhythms from the slope they sit on.

WHY THIS EXISTS
---------------
A power spectrum of any brain is dominated by its low frequencies. That is
not a bug in the recording and not a filter left on: neural power falls off
as roughly 1/f^x, so on a linear axis the first two hertz tower over
everything and a theta rhythm at 8 Hz is a bump you cannot see. Reading
"delta is 22% of the power" off such a plot says almost nothing about delta,
because most of that 22% is the slope passing through the delta band on its
way down.

Donoghue et al. (2020), *Parameterizing neural power spectra into periodic
and aperiodic components*, Nature Neuroscience 23:1655-1665, is the reference
answer. The spectrum is modelled as two things added together in log power:

    * an APERIODIC component -- the 1/f-like slope, described by an offset,
      an exponent, and optionally a knee where the slope bends;
    * a small number of PERIODIC components -- Gaussian bumps standing off
      that slope, which are the oscillations.

The paper's central point is that the two get conflated. A band power that
rises because the exponent changed is not an oscillation that got stronger,
and the literature is full of both reported as the same thing. Once they are
separated, "how much theta" has an answer that means something: the height of
the theta peak ABOVE the aperiodic component.

WHAT THIS IS
------------
A faithful implementation of that algorithm, in the order the paper gives it:

    1. Fit the aperiodic component to the whole spectrum.
    2. Subtract it. What is left is the flattened spectrum.
    3. Take the tallest bump, fit a Gaussian, subtract it, and repeat until
       the tallest remaining bump is no taller than the noise.
    4. Refit all the Gaussians together.
    5. Subtract the peaks from the ORIGINAL spectrum and fit the aperiodic
       component again, now unbiased by the peaks sitting on it.
    6. The model is the sum. Report how well it fits.

Not a port of the fooof package -- there is no dependency on it here -- but
the same algorithm with the same defaults, so a number out of this is
comparable with a number out of that. Where a choice was not specified in
the paper, the fooof source is what was followed, and it is noted.

THE KNEE
--------
`aperiodic_mode` is 'fixed' (a straight line in log-log) or 'knee' (a bend).
The paper is explicit that a straight line is wrong over a wide range, and
Aperiodicity in Mouse CA1 and DG Power Spectra (eNeuro, 2026) finds the same
in exactly this preparation -- hippocampal LFP in mouse -- where a single
exponent over 4-200 Hz leaves structured residuals. Over a range as wide as
1-200 Hz the default here is therefore 'knee'. Over a narrow one it is
'fixed', because a knee fit to a decade of data is three parameters chasing
a straight line.
"""
from __future__ import annotations

import math

import numpy as np

try:
    from scipy.optimize import curve_fit
    HAVE_SCIPY = True
except Exception:                                        # noqa: BLE001
    curve_fit = None
    HAVE_SCIPY = False


# fooof's defaults, so a fit from here is comparable with one from there.
PEAK_WIDTH_LIMITS = (0.5, 12.0)   # Hz, full width at half maximum
MAX_N_PEAKS = 6
MIN_PEAK_HEIGHT = 0.0             # log10 power
PEAK_THRESHOLD = 2.0              # in standard deviations of the flattened fit
# Points kept for the robust aperiodic refit: the lowest 2.5% of the
# flattened spectrum, which is the part no oscillation is sitting on.
AP_PERCENTILE_THRESH = 2.5
# A peak whose centre is within this many of its own standard deviations of
# the edge of the fit range is dropped: half a bump is not a bump.
BW_STD_EDGE = 1.0

# Above this many octaves of fit range, a straight line in log-log is not a
# good description of an LFP spectrum. 1-200 Hz is 7.6 octaves.
KNEE_ABOVE_OCTAVES = 4.0

# How many times to alternate between fitting the peaks and re-fitting the
# slope underneath them. The eNeuro paper allows twenty; in practice the
# exponent stops moving after three or four, so this stops when it does.
MAX_ALTERNATIONS = 20
CONVERGE_DB = 1e-4

_FWHM_TO_STD = 1.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))


# --------------------------------------------------------------------------
# The two component shapes
# --------------------------------------------------------------------------
def aperiodic(freqs, *params):
    """The 1/f-like component, in log10 power.

    Two parameters or three:

        fixed   L(f) = b - x * log10(f)
        knee    L(f) = b - log10(k + f ** x)

    The knee form is the paper's: below the knee frequency the spectrum is
    flat and above it the slope is `x`. `k` is not itself a frequency --
    the knee frequency is k ** (1 / x), which is what `knee_hz` reports.
    """
    f = np.asarray(freqs, dtype=float)
    if len(params) == 3:
        b, k, x = params
        return b - np.log10(np.maximum(k + f ** x, 1e-300))
    b, x = params
    return b - x * np.log10(np.maximum(f, 1e-300))


def gaussian(freqs, *params):
    """Any number of Gaussians, as (centre, height, standard deviation)."""
    f = np.asarray(freqs, dtype=float)
    out = np.zeros_like(f)
    for i in range(0, len(params), 3):
        ctr, hgt, wid = params[i], params[i + 1], params[i + 2]
        out = out + hgt * np.exp(-((f - ctr) ** 2) / (2 * max(wid, 1e-9) ** 2))
    return out


# --------------------------------------------------------------------------
# Fitting the aperiodic component
# --------------------------------------------------------------------------
def _guess_aperiodic(freqs, logp, mode):
    """A starting point good enough for the optimiser to improve on."""
    off = logp[0]
    # The slope between the ends, which is the right order of magnitude even
    # when a peak is sitting on one of them.
    span = math.log10(freqs[-1]) - math.log10(freqs[0])
    exp0 = (logp[0] - logp[-1]) / span if span > 0 else 1.0
    exp0 = float(np.clip(exp0, 0.1, 8.0))
    if mode == "knee":
        return [off, 0.0, exp0]
    return [off, exp0]


def _fit_aperiodic(freqs, logp, mode, guess=None):
    """One least-squares fit of the aperiodic shape. Returns the parameters.

    The knee is bounded so its frequency stays inside the range being
    fitted. Unbounded it runs away: with the peaks removed, a knee above the
    top of the range describes a straight line just as well as a straight
    line does, and the optimiser will happily send `k` to 1e30 to get there
    -- which then overflows the moment anybody asks what frequency that is.
    A knee outside the data is not a knee.
    """
    p0 = guess if guess is not None else _guess_aperiodic(freqs, logp, mode)
    if mode == "knee":
        # k = knee_hz ** exponent, so the ceiling is the top of the range
        # raised to the largest exponent allowed.
        k_max = float(np.clip(freqs[-1] ** 12.0, 1e3, 1e30))
        lo = [-np.inf, 0.0, 0.0]
        hi = [np.inf, k_max, 12.0]
        p0 = [p0[0], float(np.clip(p0[1], 0.0, k_max)), p0[2]]
    else:
        lo = [-np.inf, 0.0]
        hi = [np.inf, 12.0]
    try:
        popt, _ = curve_fit(aperiodic, freqs, logp, p0=p0,
                            bounds=(lo, hi), maxfev=20000)
        return list(popt)
    except Exception:                                    # noqa: BLE001
        return list(p0)


def _robust_aperiodic(freqs, logp, mode):
    """The paper's two-pass fit.

    An oscillation is power ABOVE the aperiodic component, never below it, so
    a single least-squares fit to the whole spectrum is pulled upward by
    every peak in it. The second pass therefore fits only the points that sit
    lowest once the first fit is taken off -- the floor between the peaks,
    which is the aperiodic component with nothing added.
    """
    first = _fit_aperiodic(freqs, logp, mode)
    flat = logp - aperiodic(freqs, *first)
    flat = np.maximum(flat, 0.0)
    thresh = np.percentile(flat, AP_PERCENTILE_THRESH)
    keep = flat <= thresh
    # Never fit three parameters to a handful of points.
    if keep.sum() < max(6, len(freqs) // 50):
        keep = flat <= np.percentile(flat, 25.0)
    if keep.sum() < 6:
        return first
    return _fit_aperiodic(freqs[keep], logp[keep], mode, guess=first)


# --------------------------------------------------------------------------
# Fitting the peaks
# --------------------------------------------------------------------------
def _guess_peaks(freqs, flat, width_limits, max_peaks, min_height, thresh):
    """Tallest bump first, subtract, repeat. The paper's step 3.

    Stops when the tallest thing left is no taller than the noise, which is
    what keeps this from fitting a Gaussian to every wiggle -- the commonest
    way to turn a smooth spectrum into a list of imaginary oscillations.
    """
    std_limits = (width_limits[0] * _FWHM_TO_STD,
                  width_limits[1] * _FWHM_TO_STD)
    work = flat.copy()
    guesses = []
    while len(guesses) < max_peaks:
        i = int(np.argmax(work))
        height = float(work[i])
        if height <= thresh * float(np.std(work)):
            break
        if height <= min_height:
            break

        ctr = float(freqs[i])
        half = 0.5 * height
        # Walk out to half height on each side to measure the width. Where
        # the spectrum does not come back down before the edge, the other
        # side is used doubled -- fooof's behaviour, and better than
        # inventing a width.
        left = right = None
        for j in range(i, -1, -1):
            if work[j] <= half:
                left = j
                break
        for j in range(i, len(work)):
            if work[j] <= half:
                right = j
                break
        if left is None and right is None:
            break
        if left is None:
            fwhm = 2.0 * (freqs[right] - ctr)
        elif right is None:
            fwhm = 2.0 * (ctr - freqs[left])
        else:
            fwhm = freqs[right] - freqs[left]
        std = float(np.clip(fwhm * _FWHM_TO_STD, std_limits[0], std_limits[1]))

        guesses.append([ctr, height, std])
        work = work - gaussian(freqs, ctr, height, std)
    return guesses


def _refit_peaks(freqs, flat, guesses, width_limits):
    """All of them at once, so neighbours stop stealing each other's height."""
    if not guesses:
        return []
    std_limits = (width_limits[0] * _FWHM_TO_STD,
                  width_limits[1] * _FWHM_TO_STD)
    p0, lo, hi = [], [], []
    for ctr, hgt, std in guesses:
        # Each centre is held near where it was found. Letting them roam
        # lets two Gaussians converge on one peak and report two rhythms.
        p0 += [ctr, hgt, std]
        lo += [ctr - 2.0 * std, 0.0, std_limits[0]]
        hi += [ctr + 2.0 * std, np.inf, std_limits[1]]
    try:
        popt, _ = curve_fit(gaussian, freqs, flat, p0=p0,
                            bounds=(lo, hi), maxfev=20000)
    except Exception:                                    # noqa: BLE001
        popt = p0
    return [list(popt[i:i + 3]) for i in range(0, len(popt), 3)]


def _fit_band_peak(freqs, flat, lo, hi, cf_lo, cf_hi, width_limits):
    """One Gaussian for one named band, with its centre held inside it.

    The point of bounding the centre is that this is asked a question about
    theta, not about whatever the tallest thing nearby happens to be. An
    unbounded Gaussian offered a theta band will happily centre itself on the
    shoulder of the delta slope and report a 3 Hz "theta rhythm".

    Height is bounded below at zero, so the worst answer this can give is
    "there is no rhythm here", never a negative one.
    """
    std_limits = (width_limits[0] * _FWHM_TO_STD,
                  width_limits[1] * _FWHM_TO_STD)
    # A peak can be no taller than the whole spectrum's dynamic range.
    # Without this ceiling the Gaussian absorbs any offset in the flattened
    # spectrum, the slope is then refitted lower to compensate, and the next
    # pass needs a taller Gaussian still -- which is how this produced peaks
    # eight hundred decibels high.
    ceiling = float(np.ptp(flat)) if flat.size else 1.0
    ceiling = max(ceiling, 1e-3)
    # Fitted on a margin either side of the band, so a peak sitting near an
    # edge has its shoulder to be fitted against instead of being clipped.
    pad = 0.5 * (hi - lo)
    m = (freqs >= max(freqs[0], lo - pad)) & (freqs <= min(freqs[-1], hi + pad))
    if m.sum() < 8:
        return None
    ff, yy = freqs[m], flat[m]

    inside = (ff >= cf_lo) & (ff <= cf_hi)
    if not inside.any():
        return None
    i = int(np.argmax(np.where(inside, yy, -np.inf)))
    p0 = [float(ff[i]), float(np.clip(yy[i], 1e-6, ceiling)),
          float(np.clip((hi - lo) / 4.0, std_limits[0], std_limits[1]))]
    try:
        popt, _ = curve_fit(
            gaussian, ff, yy, p0=p0,
            bounds=([cf_lo, 0.0, std_limits[0]],
                    [cf_hi, ceiling, std_limits[1]]), maxfev=20000)
        return [float(popt[0]), float(popt[1]), float(popt[2])]
    except Exception:                                    # noqa: BLE001
        return p0


def _sse(observed, modelled):
    """Sum of squared error, which is what an iteration has to reduce."""
    d = np.asarray(observed) - np.asarray(modelled)
    return float(np.sum(d * d))


def _drop_edge_peaks(peaks, f_lo, f_hi):
    """A bump whose centre is within one standard deviation of the edge.

    Half a peak is not a peak: its height and width are whatever the fit
    range happened to cut it off at, and it will move if the range moves.
    """
    return [p for p in peaks
            if (p[0] - BW_STD_EDGE * p[2]) > f_lo
            and (p[0] + BW_STD_EDGE * p[2]) < f_hi]


def _drop_overlapping(peaks):
    """Two Gaussians describing one bump: keep the taller."""
    out = []
    for p in sorted(peaks, key=lambda q: q[0]):
        if out and abs(p[0] - out[-1][0]) < (p[2] + out[-1][2]):
            if p[1] > out[-1][1]:
                out[-1] = p
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------
# The whole thing
# --------------------------------------------------------------------------
def default_mode(f_lo, f_hi):
    """Knee over a wide range, a straight line over a narrow one."""
    if f_lo <= 0 or f_hi <= f_lo:
        return "fixed"
    octaves = math.log2(f_hi / f_lo)
    return "knee" if octaves >= KNEE_ABOVE_OCTAVES else "fixed"


def fit(freqs, psd, f_lo=1.0, f_hi=None, mode=None,
        width_limits=PEAK_WIDTH_LIMITS, max_peaks=MAX_N_PEAKS,
        min_height=MIN_PEAK_HEIGHT, thresh=PEAK_THRESHOLD, ignore=None,
        bands=None):
    """Separate one spectrum into its slope and its rhythms.

    `ignore` is a boolean mask over `freqs` of bins to leave out of the fit
    -- line noise, which is neither aperiodic nor an oscillation and will
    otherwise be fitted as a very tall, very narrow rhythm.

    Everything returned is in log10 power, which is the space the model is
    fitted in and the space the paper reports in.
    """
    if not HAVE_SCIPY:
        return None
    f = np.asarray(freqs, dtype=float)
    p = np.asarray(psd, dtype=float)
    if f_hi is None:
        f_hi = float(f[-1]) if f.size else 0.0
    inside = (f >= f_lo) & (f <= f_hi) & (p > 0)
    if ignore is not None:
        inside = inside & ~np.asarray(ignore, dtype=bool)
    if inside.sum() < 20:
        return None

    ff = f[inside]
    logp = np.log10(p[inside])
    mode = mode or default_mode(float(ff[0]), float(ff[-1]))

    # 1-2. the slope, robustly, and what stands off it
    ap = _robust_aperiodic(ff, logp, mode)

    # ---- the named bands, alternating with the slope ----
    # This is the eNeuro variant, and it exists because the knee will
    # otherwise settle on top of the biggest low-frequency rhythm and absorb
    # it. Measured on this rig: a generic knee fit put the bend at 10.8 Hz
    # and reported no theta on the most theta-rich channel of the probe.
    band_peaks = {}
    band_fit = np.zeros_like(ff)
    best = _sse(logp, aperiodic(ff, *ap))
    for _ in range(MAX_ALTERNATIONS if bands else 0):
        flat = logp - aperiodic(ff, *ap)
        found, stack = {}, []
        for b in bands:
            got = _fit_band_peak(ff, flat, b["lo"], b["hi"],
                                 b.get("cf_lo", b["lo"]),
                                 b.get("cf_hi", b["hi"]), width_limits)
            if got:
                found[b["name"]] = got
                stack += got
        try_fit = gaussian(ff, *stack) if stack else np.zeros_like(ff)
        # Ordinary least squares, NOT the robust fit. The robust one works
        # by keeping only the lowest residuals, which is how it ignores
        # peaks; run on a spectrum whose peaks are already subtracted it
        # selects the bottom edge of the noise and walks the slope down a
        # little further on every pass.
        try_ap = _fit_aperiodic(ff, logp - try_fit, mode, guess=ap)
        sse = _sse(logp, aperiodic(ff, *try_ap) + try_fit)
        if not np.isfinite(sse) or sse > best:
            break               # this pass made it worse; keep the last one
        was, ap = list(ap), try_ap
        band_fit, band_peaks, best = try_fit, found, sse
        if len(was) == len(ap) and max(abs(a - b) for a, b
                                       in zip(was, ap)) < CONVERGE_DB:
            break

    # 3-4. the rhythms nobody named, on what the named ones leave behind
    flat = logp - aperiodic(ff, *ap) - band_fit
    guesses = _guess_peaks(ff, flat, width_limits, max_peaks,
                           min_height, thresh)
    peaks = _refit_peaks(ff, flat, guesses, width_limits)
    peaks = _drop_edge_peaks(peaks, float(ff[0]), float(ff[-1]))
    peaks = _drop_overlapping(peaks)

    # 5. the slope again, with every rhythm taken off first
    peak_fit = gaussian(ff, *[v for pk in peaks for v in pk]) \
        if peaks else np.zeros_like(ff)
    # Ordinary least squares again, and kept only if it is an improvement.
    final = _fit_aperiodic(ff, logp - peak_fit - band_fit, mode, guess=ap)
    if _sse(logp, aperiodic(ff, *final) + peak_fit + band_fit) \
            <= _sse(logp, aperiodic(ff, *ap) + peak_fit + band_fit):
        ap = final
    ap_fit = aperiodic(ff, *ap)
    model = ap_fit + peak_fit + band_fit

    # 6. how well it did, said out loud rather than assumed
    resid = logp - model
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((logp - logp.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    out = {
        "mode": mode,
        "f_lo": float(ff[0]), "f_hi": float(ff[-1]),
        "offset": float(ap[0]),
        "exponent": float(ap[-1]),
        "r_squared": float(r2),
        "error": float(np.mean(np.abs(resid))),
        "n_peaks": len(peaks),
        # One entry per named band, always, even where the answer is "no
        # rhythm here" -- which is a result and not a gap. `power_db` is the
        # height above the aperiodic component, so a number near zero means
        # the band is slope and nothing else.
        "band_peaks": {name: {
            "center_hz": float(pk[0]),
            "power_db": float(pk[1]),
            "bandwidth_hz": float(2.0 * pk[2]),
        } for name, pk in band_peaks.items()},
        # The fitted curves, on the bins they were fitted over, so the
        # window can draw the model over the data rather than redoing the
        # arithmetic in JavaScript and getting a slightly different answer.
        "freqs": [float(v) for v in ff],
        "aperiodic_db": [float(v) for v in ap_fit],
        "model_db": [float(v) for v in model],
        "flat_db": [float(v) for v in (logp - ap_fit)],
        "peaks": [{
            # Centre, height above the aperiodic component, and bandwidth as
            # the paper defines them: the height is what is left of the peak
            # once the slope is gone, which is the whole point.
            "center_hz": float(pk[0]),
            "power_db": float(pk[1]),
            "bandwidth_hz": float(2.0 * pk[2]),
        } for pk in peaks],
    }
    if mode == "knee":
        out["knee"] = float(ap[1])
        # The knee parameter is not a frequency; this is. Guarded because
        # k ** (1/x) overflows for a large k and a small x, and a knee that
        # lands outside the fitted range is reported as absent rather than
        # as a number nobody can use.
        khz = None
        try:
            if ap[1] > 0 and out["exponent"] > 0.05:
                khz = float(ap[1]) ** (1.0 / out["exponent"])
                if not math.isfinite(khz) or khz > out["f_hi"]                         or khz < out["f_lo"]:
                    khz = None
        except (OverflowError, ValueError, ZeroDivisionError):
            khz = None
        out["knee_hz"] = khz
    return out


def peak_in(fitted, lo, hi, name=None):
    """The fitted rhythm inside a band, if there is one.

    The band-constrained Gaussian when there is one, because it answers the
    question that was asked; otherwise the tallest thing the free search
    happened to find in range.
    """
    if not fitted:
        return None
    if name and name in (fitted.get("band_peaks") or {}):
        return fitted["band_peaks"][name]
    best = None
    for pk in fitted.get("peaks") or []:
        if lo <= pk["center_hz"] < hi:
            if best is None or pk["power_db"] > best["power_db"]:
                best = pk
    return best
