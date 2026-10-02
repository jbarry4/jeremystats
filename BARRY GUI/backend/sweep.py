"""
sweep.py -- the Monolith's engine: every coupling measure, 1 to 55 Hz.

The Precon drifts asked three questions in three bands. The Monolith asks
fourteen in fifty-eight: a band centred on every whole hertz from 1 to 55,
plus theta, beta and low gamma as the rows the earlier work was done in. It
runs on the VACC, one array task per rat-day, kind and band chunk
(`run_node`), and comes home as arrays that `monolith.py` pools over rats.

WHAT IT READS, AND WHAT IT DOES NOT CHANGE

The traces are read by `coupling._signals_for_windows`, the same engine
every circuit uses: one wire per region per window, the lowest-numbered
usable one, clipped and bad wires passed over, histology-blocked regions
never opened. So a region in the Monolith is measured on exactly the wire a
circuit of the same window would use. Mains is notched first, as there.

THE BANDS

A band per whole hertz, `f` +/- 15% (never narrower than +/- 0.5 Hz), and
never past 55 Hz: the top bands are cut at 55 rather than reaching across
the 60 Hz notch, so the 55 Hz band is 46.75-55. Theta, beta and low gamma
are kept exactly as `coupling.BANDS` defines them -- and computed exactly
as the circuits computed them (`pad=False` below), so the Monolith's state
rows for coherence, raw cc and envelope cc are the Precon drifts' numbers,
and can be checked against them.

Each 1 Hz band is filtered with a reflection of three cycles of its low
edge either side (`analytic`). A 0.5-1.5 Hz Butterworth rings for seconds,
and in a 10 s window its edges would be most of what was measured. The
reflection is the window's own data, mirrored: nothing outside the window
-- nothing the clipping check did not see -- is read.

THE TWO TRANSITION WINDOWS

Slow bands (centre <= 12 Hz, and theta) are measured -3 s / +3 s around
each boundary; fast bands (>= 13 Hz, beta, low gamma) -1 s / +2 s, as the
circuits are. Six seconds is what a 1 Hz band needs to hold more than one
cycle either side.

THE METHODS (`EDGE_METHODS`, all symmetric unless said)

  coherence   Welch magnitude-squared coherence, averaged over the band.
  icoh        |mean over the band of the imaginary part of coherency|.
              Blind to anything at zero lag, so blind to volume conduction.
  raw_cc      peak |r| of the band-passed traces within two cycles (the
              band's own lag bound for the three named bands); signed.
  env_cc      the same, on the band's mean-removed envelopes.
  env_cc0     Pearson r of the two envelopes at zero lag.
  orth_env    envelope correlation after orthogonalising each signal on
              the other (Hipp et al. 2012), both ways, averaged.
  plv         phase-locking value over the window's samples.
  ppc         pairwise phase consistency (Vinck 2010): PLV without its
              sample-size bias, over segments of the window.
  pli         phase-lag index (Stam 2007): |mean sign of the lag|.
  wpli        weighted PLI (Vinck 2011), over the window's samples.
  dwpli       debiased squared wPLI (Vinck 2011), over segments.
  gc_ab       spectral Granger causality, first region -> second, from the
              nonparametric (Wilson) factorisation of the Welch spectrum
              (Dhamala et al. 2008), in nats, averaged over the band.
  gc_ba       the same, second -> first.

`gc_net` (gc_ab - gc_ba) is made where the values are pooled, not here.
Node power is log10 of the Welch power density averaged over the band.

Segments for ppc and dwpli: the window cut into pieces of two cycles of the
band centre or 2/(band width), whichever is longer, so the pieces are
close enough to independent that PPC on independent noise averages zero.

Welch segments: 1 s (the circuits' segment, MATLAB's hanning(1000), 50%
overlap, zero-padded to twice) wherever the band is wide enough for a 1 s
segment to resolve it; 1.5 s for the 4 Hz band and 2 s for 1-3 Hz.
Granger is factorised at 250 Hz, from the same segments in time.

PAC (`pac_window`): Tort's modulation index, phase from 2-12 Hz, amplitude
centred on 15-50 Hz, every region's phase against every region's amplitude
(itself included). A cell whose amplitude band cannot carry the phase
frequency's sidebands, or reaches down into the phase band, is not
measured.
"""
from __future__ import annotations

import json
import math
import os
import time

import numpy as np

from . import lazyimp  # noqa: E402
(butter, sosfiltfilt, hilbert) = lazyimp.names(
    "scipy.signal", "butter", "sosfiltfilt", "hilbert")

from . import coupling, spark

SCHEMA = "arc.sweep/1"
FS = coupling.ANALYSIS_FS
GC_FS = 250.0

SWEEP_HZ = tuple(range(1, 56))
HALF_FRAC = 0.15
MIN_HALF_HZ = 0.5
TOP_HZ = 55.0
SPLIT_HZ = 12.0
NAMED = tuple(coupling.BAND_ORDER)
PAD_CYCLES = 3.0

EDGE_METHODS = ("coherence", "icoh", "raw_cc", "env_cc", "env_cc0",
                "orth_env", "plv", "ppc", "pli", "wpli", "dwpli",
                "gc_ab", "gc_ba")
DERIVED = ("gc_net",)
ALL_METHODS = EDGE_METHODS + DERIVED

STATE = tuple(spark.CLIP_WINDOWS)
TRANSITION = tuple(spark.TRANSITION_WINDOWS)
REST = tuple(spark.REST_WINDOWS)
WINDOWS = STATE + TRANSITION
SLOW_LEN = (3.0, 3.0)
FAST_LEN = (spark.TRANSITION_BEFORE_S, spark.TRANSITION_AFTER_S)

KINDS = ("state", "trans_slow", "trans_fast", "rest", "pac", "pac_rest",
         "pac_trans")

#: Named bands of the sweep's own, beyond the circuits' three (coupling's
#: BANDS, which the circuits share and this does not touch). Appended AFTER
#: them, so a Monolith built before one was added is the same arrays with
#: one band fewer at the end, and can have it added by a small run.
#: Delta (user, 2026-10-02): 1-4 Hz; lags searched over two cycles of its
#: slowest edge, 2 s; Welch pieces of 2 s so its lowest hertz has two cycles
#: in each (the 1 s pieces of the faster bands would hold one).
SWEEP_NAMED = {
    "delta": {"id": "delta", "low": 1.0, "high": 4.0, "max_lag_ms": 2000.0,
              "label": "Delta", "welch_s": 2.0},
}

PAC_PHASE_HZ = tuple(range(2, 13))
PAC_AMP_HZ = tuple(range(15, 51, 5))
PAC_BINS = 18
PAC_GAP_HZ = 2.0


class SweepError(Exception):
    pass


# --------------------------------------------------------------------------
# The bands
# --------------------------------------------------------------------------
def band_of(f):
    """The proportional band around `f` Hz: (low, high)."""
    f = float(f)
    h = max(MIN_HALF_HZ, HALF_FRAC * f)
    return round(max(0.5, f - h), 6), round(min(TOP_HZ, f + h), 6)


def bands():
    """Every band, 1 Hz bins first, then the three named ones."""
    out = []
    for f in SWEEP_HZ:
        lo, hi = band_of(f)
        out.append({"id": "f%02d" % f, "hz": f, "low": lo, "high": hi,
                    "lag_s": round(2.0 / f, 6),
                    "speed": "slow" if f <= SPLIT_HZ else "fast",
                    "named": False, "pad": True,
                    "label": "%d Hz" % f})
    for bid in NAMED:
        b = coupling.BANDS[bid]
        out.append({"id": bid, "hz": None, "low": float(b["low"]),
                    "high": float(b["high"]),
                    "lag_s": float(b["max_lag_ms"]) / 1000.0,
                    "speed": "slow" if b["high"] <= SPLIT_HZ else "fast",
                    "named": True, "pad": False,
                    "label": "%s %g–%g Hz" % (coupling.BAND_LABELS[bid],
                                              b["low"], b["high"])})
    for bid, b in SWEEP_NAMED.items():
        out.append({"id": bid, "hz": None, "low": float(b["low"]),
                    "high": float(b["high"]),
                    "lag_s": float(b["max_lag_ms"]) / 1000.0,
                    "speed": "slow" if b["high"] <= SPLIT_HZ else "fast",
                    "named": True, "pad": False, "welch_s": b["welch_s"],
                    "label": "%s %g–%g Hz" % (b["label"], b["low"],
                                              b["high"])})
    return out


BANDS = bands()
BAND_IDS = tuple(b["id"] for b in BANDS)
BAND_BY_ID = {b["id"]: b for b in BANDS}


def bands_for(kind):
    """The band ids a kind of task measures, in BAND_IDS order."""
    if kind == "trans_slow":
        return [b for b in BAND_IDS if BAND_BY_ID[b]["speed"] == "slow"]
    if kind == "trans_fast":
        return [b for b in BAND_IDS if BAND_BY_ID[b]["speed"] == "fast"]
    if kind in ("state", "rest"):
        return list(BAND_IDS)
    if kind in ("pac", "pac_rest", "pac_trans"):
        return []
    raise SweepError("There is no %r kind of sweep task." % (kind,))


def welch_len_s(band):
    """Welch segment length for a band: 1 s unless it is too narrow (or
    the band says its own, as delta does)."""
    if band.get("welch_s"):
        return float(band["welch_s"])
    half = (float(band["high"]) - float(band["low"])) / 2.0
    if half < 0.55:
        return 2.0
    if half < 0.72:
        return 1.5
    return 1.0


def seg_len_s(band):
    """The piece length ppc and dwpli count as one observation: two cycles
    of the centre, or twice the band's coherence time (1 / width), whichever
    is longer. Measured on independent noise: at one coherence time
    neighbouring pieces still share phase, and PPC came out at +0.036
    (+/- 0.008) where it should be 0; at two it is 0 within its error."""
    centre = (float(band["low"]) + float(band["high"])) / 2.0
    width = float(band["high"]) - float(band["low"])
    return max(2.0 / centre, 2.0 / width)


def pac_cells():
    """[(phase Hz, amp Hz, (phase lo, hi), (amp lo, hi) or None)]."""
    out = []
    for fp in PAC_PHASE_HZ:
        plo, phi = band_of(fp)
        for fa in PAC_AMP_HZ:
            # +/- 1.5 fp: the sidebands at fa +/- fp sit well inside the
            # Butterworth's corners. At +/- (fp + 1) they sat a hertz in,
            # were cut by a dB or two, and the 6 Hz cell read lower than
            # the 7 Hz one for a 6 Hz modulation.
            w = max(1.5 * fp, HALF_FRAC * fa)
            alo, ahi = fa - w, min(TOP_HZ, fa + w)
            ok = (alo >= phi + PAC_GAP_HZ) and (ahi - alo >= 2.0 * fp)
            out.append((fp, fa, (plo, phi),
                        (round(alo, 6), round(ahi, 6)) if ok else None))
    return out


PAC_CELLS = pac_cells()


def regions():
    return list(coupling.dewey_map().keys())


def pairs_of(names):
    return coupling.region_pairs(names)


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------
_SOS = {}


def _sos(low, high, fs):
    key = (round(low, 6), round(high, 6), float(fs))
    got = _SOS.get(key)
    if got is None:
        nyq = float(fs) / 2.0
        if not (0 < low < high < nyq):
            raise SweepError("A %g-%g Hz band does not fit a %g Hz signal."
                             % (low, high, fs))
        got = butter(coupling.BUTTER_ORDER, [low / nyq, high / nyq],
                     btype="bandpass", output="sos")
        _SOS[key] = got
    return got


def analytic(x, fs, low, high, pad=True):
    """The band's analytic signal over the window.

    `pad=False` is the circuits' own filtering (`coupling.bandpass`), so the
    named bands come out exactly as they did there. `pad=True` mirrors the
    window three cycles of `low` either side first, then crops."""
    x = np.asarray(x, dtype=np.float64)
    sos = _sos(low, high, fs)
    if not pad:
        return hilbert(sosfiltfilt(sos, x))
    p = min(x.size - 1, int(round(PAD_CYCLES * float(fs) / float(low))))
    xp = np.pad(x, p, mode="reflect")
    z = hilbert(sosfiltfilt(sos, xp))
    return z[p:p + x.size]


def _hann(n):
    return coupling.matlab_hanning(int(n))


def _segments(x, n, step):
    """(R, K, n) views of the rows of x, K = (N - n) // step + 1."""
    N = x.shape[-1]
    K = (N - n) // step + 1
    if K < 1:
        return None
    idx = np.arange(K)[:, None] * step + np.arange(n)[None, :]
    return x[:, idx]


# --------------------------------------------------------------------------
# Wilson's factorisation and Granger
# --------------------------------------------------------------------------
def _inv2(m):
    """Inverse of a stack of 2x2 matrices, in closed form."""
    a, b = m[..., 0, 0], m[..., 0, 1]
    c, d = m[..., 1, 0], m[..., 1, 1]
    det = a * d - b * c
    out = np.empty_like(m)
    out[..., 0, 0] = d / det
    out[..., 0, 1] = -b / det
    out[..., 1, 0] = -c / det
    out[..., 1, 1] = a / det
    return out


def _mm(x, y):
    """x @ y for stacks of 2x2 matrices, written out: numpy's batched
    matmul spends most of its time on dispatch at this size."""
    out = np.empty(np.broadcast_shapes(x.shape, y.shape),
                   dtype=np.result_type(x, y))
    x00, x01, x10, x11 = x[..., 0, 0], x[..., 0, 1], x[..., 1, 0], x[..., 1, 1]
    y00, y01, y10, y11 = y[..., 0, 0], y[..., 0, 1], y[..., 1, 0], y[..., 1, 1]
    out[..., 0, 0] = x00 * y00 + x01 * y10
    out[..., 0, 1] = x00 * y01 + x01 * y11
    out[..., 1, 0] = x10 * y00 + x11 * y10
    out[..., 1, 1] = x10 * y01 + x11 * y11
    return out


def _ct(m):
    return np.conj(np.swapaxes(m, -1, -2))


WILSON_TOL = 1e-9
WILSON_MAX = 100


def wilson(S, tol=WILSON_TOL, max_iter=WILSON_MAX):
    """Minimum-phase factor of a two-sided 2x2 spectral matrix.

    `S` is (P, N, 2, 2) over N frequencies from 0 to fs (fft order).
    Returns (H, Sigma, iterations): S = H Sigma H^H, H(0 lag) = I.
    Wilson (1972), as FieldTrip's sfactorization_wilson does it: start from
    the Cholesky factor of the zero-lag covariance, then psi <- psi
    [psi^-1 S psi^-H + I]_+ until psi stops moving. The plus operator keeps
    the positive lags, half the zero lag, and only the upper triangle of
    that half -- which is what makes the factor unique.

    Written on the four entries as separate (P, N) arrays: a 2x2 matrix
    product through numpy's batched matmul spends its time on dispatch."""
    P, N = S.shape[0], S.shape[1]
    s11, s12 = S[..., 0, 0], S[..., 0, 1]
    s21, s22 = S[..., 1, 0], S[..., 1, 1]
    g0 = np.real(np.fft.ifft(S, axis=1)[:, 0])
    g0 = (g0 + np.swapaxes(g0, -1, -2)) / 2.0
    h = np.linalg.cholesky(g0)                         # lower, h h^T = g0
    one = np.ones((1, N), dtype=np.complex128)
    p11 = h[:, 0, 0][:, None] * one                    # psi = h^T, upper
    p12 = h[:, 1, 0][:, None] * one
    p21 = np.zeros((P, N), dtype=np.complex128)
    p22 = h[:, 1, 1][:, None] * one
    half = N // 2
    it = 0
    for it in range(1, max_iter + 1):
        det = p11 * p22 - p12 * p21
        i11, i12, i21, i22 = p22 / det, -p12 / det, -p21 / det, p11 / det
        # g = pin S pin^H + I
        t11 = i11 * s11 + i12 * s21
        t12 = i11 * s12 + i12 * s22
        t21 = i21 * s11 + i22 * s21
        t22 = i21 * s12 + i22 * s22
        g11 = t11 * np.conj(i11) + t12 * np.conj(i12) + 1.0
        g12 = t11 * np.conj(i21) + t12 * np.conj(i22)
        g21 = t21 * np.conj(i11) + t22 * np.conj(i12)
        g22 = t21 * np.conj(i21) + t22 * np.conj(i22) + 1.0
        gm = np.fft.ifft(np.stack([g11, g12, g21, g22]), axis=2)
        gm[:, :, 0] *= 0.5
        gm[2, :, 0] = 0.0                              # upper triangle only
        gm[:, :, half:] = 0.0
        q11, q12, q21, q22 = np.fft.fft(gm, axis=2)
        n11 = p11 * q11 + p12 * q21
        n12 = p11 * q12 + p12 * q22
        n21 = p21 * q11 + p22 * q21
        n22 = p21 * q12 + p22 * q22
        num = (np.abs(n11 - p11) ** 2 + np.abs(n12 - p12) ** 2
               + np.abs(n21 - p21) ** 2 + np.abs(n22 - p22) ** 2).sum(axis=1)
        den = (np.abs(n11) ** 2 + np.abs(n12) ** 2 + np.abs(n21) ** 2
               + np.abs(n22) ** 2).sum(axis=1)
        p11, p12, p21, p22 = n11, n12, n21, n22
        if np.all(num <= (tol * tol) * den):
            break
    psi = np.empty((P, N, 2, 2), dtype=np.complex128)
    psi[..., 0, 0], psi[..., 0, 1] = p11, p12
    psi[..., 1, 0], psi[..., 1, 1] = p21, p22
    a0 = np.real(np.fft.ifft(psi, axis=1)[:, 0])        # (P, 2, 2)
    sigma = _mm(a0, np.swapaxes(a0, -1, -2))
    H = _mm(psi, _inv2(a0.astype(np.complex128))[:, None])
    return H, sigma, it


def granger(H, sigma):
    """Geweke's spectral Granger, both ways, from a factorisation.

    Returns (gc_12, gc_21), each (P, N): channel 1 -> 2 and 2 -> 1, in nats.
    The spectra are the factorisation's own (H Sigma H^H), and each
    intrinsic part is a squared magnitude, so neither ratio can go below
    one through rounding: S11 = |H11 + (s12/s11) H12|^2 s11 + |H12|^2
    (s22 - s12^2/s11), and the first term is what 1 would be on its own.
    """
    s11, s22 = sigma[:, 0, 0][:, None], sigma[:, 1, 1][:, None]
    s12 = sigma[:, 0, 1][:, None]
    H11, H12 = H[..., 0, 0], H[..., 0, 1]
    H21, H22 = H[..., 1, 0], H[..., 1, 1]
    intr1 = np.abs(H11 + (s12 / s11) * H12) ** 2 * s11
    intr2 = np.abs(H22 + (s12 / s22) * H21) ** 2 * s22
    S11 = intr1 + np.abs(H12) ** 2 * (s22 - s12 * s12 / s11)
    S22 = intr2 + np.abs(H21) ** 2 * (s11 - s12 * s12 / s22)
    tiny = 1e-300
    gc_21 = np.log(np.maximum(S11, tiny) / np.maximum(intr1, tiny))
    gc_12 = np.log(np.maximum(S22, tiny) / np.maximum(intr2, tiny))
    return gc_12, gc_21


# --------------------------------------------------------------------------
# One window
# --------------------------------------------------------------------------
def _band_mask(freqs, low, high):
    return (freqs >= float(low) - 1e-6) & (freqs <= float(high) + 1e-6)


def _peak_signed(c, lag):
    """c: (P, 2*lag+1) in lag order -lag..+lag. Signed value at max |c|."""
    i = np.argmax(np.abs(c), axis=1)
    return c[np.arange(c.shape[0]), i]


def _fast_len(n):
    """The smallest 2^a 3^b 5^c at least n: an FFT that long is fast, and
    n + lag + 1 is enough room that no lag up to `lag` wraps round."""
    best = 1 << max(0, int(n - 1).bit_length())
    p5 = 1
    while p5 < best:
        p35 = p5
        while p35 < best:
            p = p35
            while p < n:
                p *= 2
            if p < best:
                best = p
            p35 *= 3
        p5 *= 5
    return best


def _xcorr_peak(Y, ia, ib, lag):
    """Peak normalised cross-correlation of rows ia vs ib within +/- lag
    samples, signed, `coupling._xcorr_coeff`'s convention (r[k] =
    sum a[n+k] b[n]). Y is (R, n), real. NaN rows stay NaN."""
    n = Y.shape[1]
    nfft = _fast_len(n + lag + 1)
    F = np.fft.rfft(Y, n=nfft, axis=1)
    c = np.fft.irfft(F[ia] * np.conj(F[ib]), n=nfft, axis=1)
    e = np.sum(Y * Y, axis=1)
    den = np.sqrt(e[ia] * e[ib])
    lagged = np.concatenate([c[:, nfft - lag:], c[:, :lag + 1]], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        lagged = lagged / den[:, None]
    return _peak_signed(lagged, lag)


def _corr_rows(A, B):
    """Pearson r between matching rows of A and B."""
    A = A - A.mean(axis=1, keepdims=True)
    B = B - B.mean(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.sum(A * B, axis=1) / np.sqrt(
            np.sum(A * A, axis=1) * np.sum(B * B, axis=1))


def window_measures(sigs, band_ids, fs=FS, notch_hz=coupling.NOTCH_HZ):
    """Every method in every band asked for, for one window.

    `sigs` is a list, one per region (region order), of the window's
    1000 Hz trace or None for a region not measured here. Returns
    (values (B, M, P) float64, power (B, R) float64, notes) with NaN where
    a pair or a region could not be measured."""
    R = len(sigs)
    names = list(range(R))
    pairs = pairs_of(names)
    ia = np.array([a for a, _b in pairs], dtype=int)
    ib = np.array([b for _a, b in pairs], dtype=int)
    P = len(pairs)
    B = len(band_ids)
    M = len(EDGE_METHODS)
    mi = {m: i for i, m in enumerate(EDGE_METHODS)}
    values = np.full((B, M, P), np.nan)
    power = np.full((B, R), np.nan)
    notes = []

    ok = [s is not None and np.asarray(s).size > 0 for s in sigs]
    if not any(ok):
        return values, power, ["no region has a signal in this window"]
    n = min(np.asarray(s).size for s, k in zip(sigs, ok) if k)
    X = np.zeros((R, n))
    for r, s in enumerate(sigs):
        if not ok[r]:
            continue
        s = np.asarray(s, dtype=np.float64)[:n]
        if not np.all(np.isfinite(s)) or s.std() <= 0:
            ok[r] = False
            notes.append("region %d: a flat or non-finite trace" % r)
            continue
        X[r] = coupling.notch(s, fs, notch_hz)[0]
    okv = np.array(ok)
    pair_ok = okv[ia] & okv[ib]

    # Welch, per segment-length class: spectra for coherence, icoh, power.
    specs = [BAND_BY_ID[b] for b in band_ids]
    classes = sorted({welch_len_s(b) for b in specs})
    welch = {}
    for L in classes:
        nseg = int(round(L * fs))
        if n < nseg:
            continue
        win = _hann(nseg)
        segs = _segments(X, nseg, nseg // 2)
        segs = segs - segs.mean(axis=2, keepdims=True)
        F = np.fft.rfft(segs * win, n=2 * nseg, axis=2)          # (R, K, f)
        Saa = np.mean(np.abs(F) ** 2, axis=1)                    # (R, f)
        Sab = np.mean(F[ia] * np.conj(F[ib]), axis=1)            # (P, f)
        freqs = np.fft.rfftfreq(2 * nseg, 1.0 / fs)
        # One-sided density: no band here touches DC or Nyquist.
        scale = 2.0 / (fs * np.sum(win * win))
        welch[L] = (freqs, Saa, Sab, scale)

    # Granger, per class, at 250 Hz.
    gc = {}
    usable_pairs = np.nonzero(pair_ok)[0]
    if usable_pairs.size:
        rows = []
        for r in range(R):
            if okv[r]:
                y, _f = coupling.decimate_to(X[r], fs, GC_FS)
                rows.append(y)
            else:
                rows.append(None)
        n250 = min(len(y) for y in rows if y is not None)
        X250 = np.zeros((R, n250))
        for r, y in enumerate(rows):
            if y is not None:
                X250[r] = y[:n250]
        for L in classes:
            nseg = int(round(L * GC_FS))
            if n250 < nseg:
                continue
            win = _hann(nseg)
            segs = _segments(X250, nseg, nseg // 2)
            segs = segs - segs.mean(axis=2, keepdims=True)
            F = np.fft.fft(segs * win, n=2 * nseg, axis=2)       # (R, K, N)
            a, b = ia[usable_pairs], ib[usable_pairs]
            S = np.empty((usable_pairs.size, 2 * nseg, 2, 2),
                         dtype=np.complex128)
            S[..., 0, 0] = np.mean(np.abs(F[a]) ** 2, axis=1)
            S[..., 1, 1] = np.mean(np.abs(F[b]) ** 2, axis=1)
            S[..., 0, 1] = np.mean(F[a] * np.conj(F[b]), axis=1)
            S[..., 1, 0] = np.conj(S[..., 0, 1])
            try:
                H, sig, _it = wilson(S)
                g12, g21 = granger(H, sig)
            except np.linalg.LinAlgError as exc:
                notes.append("Granger %.1f s: %s" % (L, exc))
                continue
            freqs = np.fft.fftfreq(2 * nseg, 1.0 / GC_FS)
            gc[L] = (freqs, g12, g21)

    for bi, bid in enumerate(band_ids):
        band = BAND_BY_ID[bid]
        lo, hi = band["low"], band["high"]
        L = welch_len_s(band)
        if L in welch:
            freqs, Saa, Sab, scale = welch[L]
            m = _band_mask(freqs, lo, hi)
            with np.errstate(invalid="ignore", divide="ignore"):
                coh = (np.abs(Sab[:, m]) ** 2
                       / (Saa[ia][:, m] * Saa[ib][:, m]))
                cohy = Sab[:, m] / np.sqrt(Saa[ia][:, m] * Saa[ib][:, m])
            values[bi, mi["coherence"]] = np.where(pair_ok, coh.mean(axis=1),
                                                   np.nan)
            values[bi, mi["icoh"]] = np.where(
                pair_ok, np.abs(np.imag(cohy).mean(axis=1)), np.nan)
            with np.errstate(divide="ignore"):
                pw = np.log10(Saa[:, m].mean(axis=1) * scale)
            power[bi] = np.where(okv, pw, np.nan)
        if L in gc:
            freqs, g12, g21 = gc[L]
            m = _band_mask(freqs, lo, hi) & (freqs >= 0)
            v12 = np.full(P, np.nan)
            v21 = np.full(P, np.nan)
            v12[usable_pairs] = g12[:, m].mean(axis=1)
            v21[usable_pairs] = g21[:, m].mean(axis=1)
            values[bi, mi["gc_ab"]] = v12
            values[bi, mi["gc_ba"]] = v21

        # Analytic-signal methods.
        Z = np.zeros((R, n), dtype=np.complex128)
        for r in range(R):
            if okv[r]:
                Z[r] = analytic(X[r], fs, lo, hi, pad=band["pad"])
        Xc = Z[ia] * np.conj(Z[ib])                               # (P, n)
        with np.errstate(invalid="ignore", divide="ignore"):
            ph = Xc / np.abs(Xc)
            plv = np.abs(ph.mean(axis=1))
            im = np.imag(Xc)
            pli = np.abs(np.mean(np.sign(im), axis=1))
            wpli = np.abs(im.mean(axis=1)) / np.mean(np.abs(im), axis=1)
        values[bi, mi["plv"]] = np.where(pair_ok, plv, np.nan)
        values[bi, mi["pli"]] = np.where(pair_ok, pli, np.nan)
        values[bi, mi["wpli"]] = np.where(pair_ok, wpli, np.nan)

        ls = int(round(seg_len_s(band) * fs))
        K = n // ls if ls > 0 else 0
        if K >= 2:
            c = Xc[:, :K * ls].reshape(P, K, ls).mean(axis=2)
            with np.errstate(invalid="ignore", divide="ignore"):
                u = c / np.abs(c)
                ppc = (np.abs(u.sum(axis=1)) ** 2 - K) / (K * (K - 1))
                ci = np.imag(c)
                s1 = ci.sum(axis=1)
                s2 = np.sum(ci * ci, axis=1)
                sa = np.sum(np.abs(ci), axis=1)
                dw = (s1 * s1 - s2) / (sa * sa - s2)
            values[bi, mi["ppc"]] = np.where(pair_ok, ppc, np.nan)
            values[bi, mi["dwpli"]] = np.where(pair_ok, dw, np.nan)

        E = np.abs(Z)
        Ec = E - E.mean(axis=1, keepdims=True)
        nrm = np.sqrt(np.sum(Ec * Ec, axis=1))
        with np.errstate(invalid="ignore", divide="ignore"):
            cm = (Ec @ Ec.T) / np.outer(nrm, nrm)
        values[bi, mi["env_cc0"]] = np.where(pair_ok, cm[ia, ib], np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            ob = np.abs(im) / E[ia]
            oa = np.abs(im) / E[ib]
        r1 = _corr_rows(E[ia], np.nan_to_num(ob))
        r2 = _corr_rows(E[ib], np.nan_to_num(oa))
        values[bi, mi["orth_env"]] = np.where(pair_ok, (r1 + r2) / 2.0,
                                              np.nan)

        lag = int(round(band["lag_s"] * fs))
        if 1 <= lag < n:
            Y = np.real(Z)
            values[bi, mi["raw_cc"]] = np.where(
                pair_ok, _xcorr_peak(Y, ia, ib, lag), np.nan)
            values[bi, mi["env_cc"]] = np.where(
                pair_ok, _xcorr_peak(Ec, ia, ib, lag), np.nan)
        else:
            notes.append("%s: a %d-sample lag bound does not fit a %d-sample "
                         "window" % (bid, lag, n))
    return values, power, notes


def pac_window(sigs, fs=FS, notch_hz=coupling.NOTCH_HZ):
    """Tort's modulation index for every cell and every ordered region
    pair (phase region, amplitude region), itself included.

    Returns (C, R*R) with NaN for cells not measured and regions absent."""
    R = len(sigs)
    C = len(PAC_CELLS)
    out = np.full((C, R * R), np.nan)
    ok = [s is not None and np.asarray(s).size > 0 for s in sigs]
    if not any(ok):
        return out
    n = min(np.asarray(s).size for s, k in zip(sigs, ok) if k)
    X = {}
    for r, s in enumerate(sigs):
        if not ok[r]:
            continue
        s = np.asarray(s, dtype=np.float64)[:n]
        if not np.all(np.isfinite(s)) or s.std() <= 0:
            continue
        X[r] = coupling.notch(s, fs, notch_hz)[0]
    have = sorted(X)
    if not have:
        return out
    logn = math.log(PAC_BINS)
    edges = np.linspace(-np.pi, np.pi, PAC_BINS + 1)
    cells_by_fp = {}
    for ci, (fp, fa, pband, aband) in enumerate(PAC_CELLS):
        cells_by_fp.setdefault(fp, []).append((ci, aband))
    for fp, cells in cells_by_fp.items():
        plo, phi = band_of(fp)
        phase_idx = {}
        for r in have:
            ph = np.angle(analytic(X[r], fs, plo, phi, pad=True))
            idx = np.clip(np.digitize(ph, edges) - 1, 0, PAC_BINS - 1)
            phase_idx[r] = idx
        live = [(ci, ab) for ci, ab in cells if ab is not None]
        if not live:
            continue
        amp_rows, amp_key = [], []
        for ci, (alo, ahi) in live:
            for r in have:
                amp_rows.append(np.abs(analytic(X[r], fs, alo, ahi,
                                                pad=True)))
                amp_key.append((ci, r))
        A = np.vstack(amp_rows)                                   # (Q, n)
        for rp in have:
            idx = phase_idx[rp]
            order = np.argsort(idx, kind="stable")
            sidx = idx[order]
            starts = np.searchsorted(sidx, np.arange(PAC_BINS))
            counts = np.bincount(idx, minlength=PAC_BINS).astype(float)
            if np.any(counts == 0):
                continue
            sums = np.add.reduceat(A[:, order], starts, axis=1)    # (Q, bins)
            mean = sums / counts[None, :]
            p = mean / mean.sum(axis=1, keepdims=True)
            with np.errstate(divide="ignore", invalid="ignore"):
                h = -np.sum(np.where(p > 0, p * np.log(p), 0.0), axis=1)
            mi_ = (logn - h) / logn
            for q, (ci, ra) in enumerate(amp_key):
                out[ci, rp * R + ra] = mi_[q]
    return out


# --------------------------------------------------------------------------
# A task on a compute node
# --------------------------------------------------------------------------
def _windows_for(kind, unit):
    pair = unit.get("pair") or {}
    if kind in ("state", "pac"):
        return spark.pair_windows(pair, spark.CLIP_PAD_S)
    if kind in ("trans_slow", "pac_trans"):
        # PAC at the transitions takes the slow windows, -3/+3 s: its phase
        # runs from 2 Hz, and the fast windows' -1/+2 s would hold three
        # cycles of that before the boundary.
        return spark.transition_windows(pair, *SLOW_LEN)
    if kind == "trans_fast":
        return spark.transition_windows(pair, *FAST_LEN)
    if kind in ("rest", "pac_rest"):
        return spark.rest_windows(pair)
    raise SweepError("There is no %r kind of sweep task." % (kind,))


def _measure_slow(folder, units, bad, only):
    """Clipping in the slow transition windows, measured here, with the
    detector and the 50 ms rule every window has. {unit id: {window:
    [CSC lost]}}; a channel that could not be measured counts as lost."""
    spans = [{"pair_id": u["id"], "windows": _windows_for("trans_slow", u)}
             for u in units]
    got = spark.clipping_windows(folder, spans, skip=bad, only=only)
    out = {}
    for u in units:
        lost = {w: set() for w in TRANSITION}
        if not got.get("measured"):
            out[u["id"]] = None
            continue
        for c, rec in ((got.get("by_pair") or {}).get(u["id"]) or {}).items():
            for w in rec.get("windows") or []:
                if w in lost:
                    lost[w].add(int(c))
        for c, per in ((got.get("unmeasured") or {}).get(u["id"])
                       or {}).items():
            for w in (per or {}):
                if w in lost:
                    lost[w].add(int(c))
        out[u["id"]] = {w: sorted(v) for w, v in lost.items()}
    return out


def run_task(spec, progress=None):
    """One task: every unit (cue pair or rest epoch) of one rat-day, one
    kind, the bands asked for. Returns (arrays, meta)."""
    kind = spec["kind"]
    if kind not in KINDS:
        raise SweepError("There is no %r kind of sweep task." % (kind,))
    names = list(spec.get("regions") or regions())
    chan_map = {k: v for k, v in coupling.dewey_map().items() if k in names}
    names = list(chan_map.keys())
    R = len(names)
    band_ids = list(spec.get("bands") or bands_for(kind))
    for b in band_ids:
        if b not in BAND_BY_ID:
            raise SweepError("%r is not a sweep band." % (b,))
    units = list(spec.get("units") or [])
    blocked = spec.get("blocked") or {}
    bad = sorted(int(c) for c in (spec.get("bad") or []))
    wnames = (STATE if kind in ("state", "pac") else
              TRANSITION if kind.startswith("trans") or kind == "pac_trans"
              else REST)
    U, W = len(units), len(wnames)
    pac = kind in ("pac", "pac_rest", "pac_trans")
    slowish = kind in ("trans_slow", "pac_trans")
    if pac:
        arr = np.full((U, W, len(PAC_CELLS), R * R), np.nan, np.float32)
        power = None
    else:
        arr = np.full((U, W, len(band_ids), len(EDGE_METHODS),
                       len(pairs_of(names))), np.nan, np.float32)
        power = np.full((U, W, len(band_ids), R), np.nan, np.float32)
    wires = np.full((U, W, R), -1, np.int16)
    why = []

    slow = {}
    if slowish:
        only = sorted({int(c) for n_, cs in chan_map.items()
                       if n_ not in blocked for c in cs})
        by_folder = {}
        for u in units:
            by_folder.setdefault(u.get("folder") or spec.get("folder"),
                                 []).append(u)
        for folder, us in by_folder.items():
            slow.update(_measure_slow(folder, us, bad, only))

    t0 = time.time()
    for ui, u in enumerate(units):
        if progress:
            progress(ui, U)
        folder = u.get("folder") or spec.get("folder")
        wins = _windows_for(kind, u)
        if slowish:
            lost = slow.get(u["id"])
            if lost is None:
                why.append({"unit": u["id"], "why": "the slow windows' "
                            "clipping could not be measured; not computed"})
                continue
            manual = u.get("manual") or {}
            flat = set(int(c) for c in (manual.get("flat") or []))
            drop = {w: sorted(set(lost.get(w) or []) | set(bad) | flat
                              | set(int(c) for c in (manual.get(w) or [])))
                    for w in TRANSITION}
        else:
            drop = u.get("drop")
            if drop is None:
                why.append({"unit": u["id"], "why": u.get("why") or
                            "no clipping measurement; not computed"})
                continue
        try:
            got = coupling._signals_for_windows(
                folder, chan_map, wins, drop, FS, blocked=blocked)
        except coupling.CouplingError as exc:
            why.append({"unit": u["id"], "why": str(exc)})
            continue
        for wi, (wname, _a, _b) in enumerate(wins):
            w = got[wname]
            sigs = []
            for ri, name in enumerate(names):
                r = w["regions"][name]
                sigs.append(r["signal"] if r["usable"] else None)
                if r.get("channel") is not None:
                    wires[ui, wi, ri] = int(r["channel"])
            if pac:
                arr[ui, wi] = pac_window(sigs)
            else:
                v, pw, notes = window_measures(sigs, band_ids)
                arr[ui, wi] = v
                power[ui, wi] = pw
                for nt in notes:
                    why.append({"unit": u["id"], "window": wname, "why": nt})
    meta = {
        "schema": SCHEMA, "kind": kind, "regions": names,
        "windows": list(wnames), "bands": band_ids,
        "methods": list(EDGE_METHODS) if not pac else None,
        "pac_cells": [[c[0], c[1], c[3]] for c in PAC_CELLS] if pac else None,
        "units": [u["id"] for u in units], "why": why,
        "seconds": round(time.time() - t0, 1),
        "slow_clipping": ({str(k): v for k, v in slow.items()}
                          if slow else None),
    }
    out = {"values": arr, "wires": wires}
    if power is not None:
        out["power"] = power
    return out, meta


def save_task(path, arrays, meta):
    """`path`.npz, written as .part and renamed."""
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        np.savez_compressed(fh, meta=np.frombuffer(
            json.dumps(meta).encode("utf-8"), dtype=np.uint8), **arrays)
    os.replace(tmp, path)


def load_task(path):
    with np.load(path, allow_pickle=False) as z:
        meta = json.loads(bytes(z["meta"]).decode("utf-8"))
        arrays = {k: z[k] for k in z.files if k != "meta"}
    return arrays, meta


def run_node(spec, job):
    """What `vacc_run.py` calls for `tool == "sweep"`: one task, its arrays
    written beside the run (`spec["out"]`), and a small answer saying so."""
    units = spec.get("units") or []
    job.begin("sweep units", of=len(units), unit="units")
    arrays, meta = run_task(spec, progress=lambda i, n: job.tick(
        "sweep units", i))
    job.tick("sweep units", len(units))
    out = spec["out"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    save_task(out, arrays, meta)
    return {"schema": SCHEMA, "task": spec.get("task"), "file": out,
            "bytes": os.path.getsize(out), "n_units": len(units),
            "seconds": meta["seconds"], "why": meta["why"][:50],
            "n_why": len(meta["why"])}


# --------------------------------------------------------------------------
# How each number was made: one window, every measure's own picture
# --------------------------------------------------------------------------
# The Monolith page's cue-pair view and its Guide both draw from this. The
# NUMBERS come from `window_measures` itself -- the same call the node made
# -- so what the picture is captioned with is the stored number, not a
# second estimate of it; the pictures are the intermediate steps those
# numbers summarise (the spectrum a band mean is taken over, the lag curve a
# peak is read off, the phase differences a PLV is the length of).
SHOW_HZ = 60.0
TRACE_FS = 250.0


def _rl(x, n=4):
    """Floats to `n` significant digits, NaN as None: small JSON."""
    out = []
    for v in np.asarray(x, dtype=np.float64).ravel():
        out.append(float("%.*g" % (n, v)) if np.isfinite(v) else None)
    return out


def _fv(x):
    x = float(x)
    return x if np.isfinite(x) else None


def lag_curve(ya, yb, lag):
    """r at every lag from -lag to +lag samples, `coupling._xcorr_coeff`'s
    convention (r[k] = sum a[n+k] b[n] / sqrt(sum a^2 sum b^2))."""
    ya = np.asarray(ya, dtype=np.float64)
    yb = np.asarray(yb, dtype=np.float64)
    n = ya.size
    nfft = _fast_len(n + lag + 1)
    c = np.fft.irfft(np.fft.rfft(ya, n=nfft) * np.conj(np.fft.rfft(yb, n=nfft)),
                     n=nfft)
    den = math.sqrt(float(np.dot(ya, ya)) * float(np.dot(yb, yb)))
    if not den > 0:
        return np.full(2 * lag + 1, np.nan)
    return np.concatenate([c[nfft - lag:], c[:lag + 1]]) / den


def _pac_bins(phase, amp):
    """Mean amplitude in each of PAC_BINS phase bins, normalised to sum 1,
    and Tort's modulation index from them."""
    edges = np.linspace(-np.pi, np.pi, PAC_BINS + 1)
    idx = np.clip(np.digitize(phase, edges) - 1, 0, PAC_BINS - 1)
    counts = np.bincount(idx, minlength=PAC_BINS).astype(float)
    sums = np.bincount(idx, weights=amp, minlength=PAC_BINS)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = sums / counts
        p = mean / np.nansum(mean)
        h = -np.nansum(np.where(p > 0, p * np.log(p), 0.0))
    mi = (math.log(PAC_BINS) - h) / math.log(PAC_BINS)
    return p, mi


def explain(a, b, band_id, fs=FS, notch_hz=coupling.NOTCH_HZ, cell=None):
    """Everything one window says about one pair of signals, measure by
    measure: the numbers (exactly the analysis's), and the curves each was
    read from. `a` and `b` are the window's two 1000 Hz traces as the node
    had them (decimated, not yet notched). `cell` is a PAC_CELLS index."""
    band = BAND_BY_ID[band_id]
    lo, hi = float(band["low"]), float(band["high"])
    v, pw, notes = window_measures([a, b], [band_id], fs, notch_hz)
    values = {m: _fv(v[0, i, 0]) for i, m in enumerate(EDGE_METHODS)}
    values["gc_net"] = (None if values["gc_ab"] is None or
                        values["gc_ba"] is None
                        else values["gc_ab"] - values["gc_ba"])
    out = {"band": band, "values": values,
           "power": [_fv(pw[0, 0]), _fv(pw[0, 1])], "notes": notes}
    xa = coupling.notch(np.asarray(a, dtype=np.float64), fs, notch_hz)[0]
    xb = coupling.notch(np.asarray(b, dtype=np.float64), fs, notch_hz)[0]
    n = min(xa.size, xb.size)
    xa, xb = xa[:n], xb[:n]
    out["n"] = int(n)
    out["seconds"] = round(n / float(fs), 3)

    # Welch: the band's own segments, as window_measures cut them.
    L = welch_len_s(band)
    nseg = int(round(L * fs))
    if n >= nseg:
        X = np.vstack([xa, xb])
        win = _hann(nseg)
        segs = _segments(X, nseg, nseg // 2)
        segs = segs - segs.mean(axis=2, keepdims=True)
        F = np.fft.rfft(segs * win, n=2 * nseg, axis=2)
        Saa = np.mean(np.abs(F[0]) ** 2, axis=0)
        Sbb = np.mean(np.abs(F[1]) ** 2, axis=0)
        Sab = np.mean(F[0] * np.conj(F[1]), axis=0)
        freqs = np.fft.rfftfreq(2 * nseg, 1.0 / fs)
        keep = freqs <= SHOW_HZ
        scale = 2.0 / (fs * np.sum(win * win))
        with np.errstate(invalid="ignore", divide="ignore"):
            coh = np.abs(Sab) ** 2 / (Saa * Sbb)
            icoh = np.imag(Sab) / np.sqrt(Saa * Sbb)
            psa = np.log10(Saa * scale)
            psb = np.log10(Sbb * scale)
        out["spectra"] = {"f": _rl(freqs[keep], 5), "coh": _rl(coh[keep]),
                          "icoh": _rl(icoh[keep]), "psd_a": _rl(psa[keep]),
                          "psd_b": _rl(psb[keep]), "seg_s": L,
                          "k": int(segs.shape[1])}

    # Granger: the same segments, at 250 Hz, factorised (Wilson).
    try:
        ya = coupling.decimate_to(xa, fs, GC_FS)[0]
        yb = coupling.decimate_to(xb, fs, GC_FS)[0]
        m = min(ya.size, yb.size)
        ng = int(round(L * GC_FS))
        if m >= ng:
            Y = np.vstack([ya[:m], yb[:m]])
            win = _hann(ng)
            segs = _segments(Y, ng, ng // 2)
            segs = segs - segs.mean(axis=2, keepdims=True)
            F = np.fft.fft(segs * win, n=2 * ng, axis=2)
            S = np.empty((1, 2 * ng, 2, 2), dtype=np.complex128)
            S[0, :, 0, 0] = np.mean(np.abs(F[0]) ** 2, axis=0)
            S[0, :, 1, 1] = np.mean(np.abs(F[1]) ** 2, axis=0)
            S[0, :, 0, 1] = np.mean(F[0] * np.conj(F[1]), axis=0)
            S[0, :, 1, 0] = np.conj(S[0, :, 0, 1])
            H, sig, it = wilson(S)
            g12, g21 = granger(H, sig)
            f = np.fft.fftfreq(2 * ng, 1.0 / GC_FS)
            keep = (f >= 0) & (f <= SHOW_HZ)
            out["granger"] = {"f": _rl(f[keep], 5), "ab": _rl(g12[0, keep]),
                              "ba": _rl(g21[0, keep]), "iterations": int(it)}
    except (coupling.CouplingError, np.linalg.LinAlgError) as exc:
        out["granger"] = {"why": str(exc)}

    # The band's analytic signals: what every phase and envelope measure
    # is computed on.
    za = analytic(xa, fs, lo, hi, pad=band["pad"])
    zb = analytic(xb, fs, lo, hi, pad=band["pad"])
    Xc = za * np.conj(zb)
    dphi = np.angle(Xc)
    k = max(1, int(round(fs / TRACE_FS)))
    with np.errstate(invalid="ignore", divide="ignore"):
        unit = Xc / np.abs(Xc)
        ob = np.abs(np.imag(Xc)) / np.abs(za)
        oa = np.abs(np.imag(Xc)) / np.abs(zb)
    mv = np.nanmean(unit)
    im = np.imag(Xc)
    hist = np.histogram(dphi, bins=36, range=(-np.pi, np.pi))[0] / float(n)
    pos = float(np.sum(im > 0)) / n
    neg = float(np.sum(im < 0)) / n
    wpos = float(np.sum(np.abs(im[im > 0])))
    wneg = float(np.sum(np.abs(im[im < 0])))
    tot = max(wpos + wneg, 1e-300)
    out["phase"] = {"rose": _rl(hist), "mean_angle": _fv(np.angle(mv)),
                    "plv": _fv(np.abs(mv)), "lead_frac": pos, "lag_frac": neg,
                    "w_lead": wpos / tot, "w_lag": wneg / tot}
    ls = int(round(seg_len_s(band) * fs))
    K = n // ls if ls > 0 else 0
    if K >= 1:
        c = Xc[:K * ls].reshape(K, ls).mean(axis=1)
        mag = np.abs(c)
        out["segments"] = {"angle": _rl(np.angle(c)),
                           "size": _rl(mag / max(float(np.max(mag)), 1e-300)),
                           "imag": _rl(np.imag(c) / max(float(np.max(mag)),
                                                       1e-300)),
                           "k": int(K), "seg_s": round(ls / fs, 4)}
    lag = int(round(band["lag_s"] * fs))
    if 1 <= lag < n:
        Ea = np.abs(za) - np.abs(za).mean()
        Eb = np.abs(zb) - np.abs(zb).mean()
        rr = lag_curve(np.real(za), np.real(zb), lag)
        re = lag_curve(Ea, Eb, lag)
        lags = np.arange(-lag, lag + 1) * 1000.0 / fs
        step = max(1, int(math.ceil(lags.size / 801.0)))
        ir, ie = int(np.nanargmax(np.abs(rr))), int(np.nanargmax(np.abs(re)))
        out["lags"] = {"ms": _rl(lags[::step], 5), "raw": _rl(rr[::step]),
                       "env": _rl(re[::step]),
                       "raw_peak": [_fv(lags[ir]), _fv(rr[ir])],
                       "env_peak": [_fv(lags[ie]), _fv(re[ie])],
                       "max_ms": round(lag * 1000.0 / fs, 3)}
    with np.errstate(invalid="ignore"):
        r_ab = np.corrcoef(np.abs(za), np.nan_to_num(ob))[0, 1]
        r_ba = np.corrcoef(np.abs(zb), np.nan_to_num(oa))[0, 1]
    out["orth"] = {"r_a": _fv(r_ab), "r_b": _fv(r_ba)}
    out["traces"] = {
        "fs": fs / k, "t": _rl(np.arange(0, n, k) / fs, 5),
        "raw_a": _rl(xa[::k]), "raw_b": _rl(xb[::k]),
        "band_a": _rl(np.real(za)[::k]), "band_b": _rl(np.real(zb)[::k]),
        "env_a": _rl(np.abs(za)[::k]), "env_b": _rl(np.abs(zb)[::k]),
        "dphi": _rl(dphi[::k]), "orth_b": _rl(ob[::k]),
        "orth_a": _rl(oa[::k])}

    if cell is not None and 0 <= int(cell) < len(PAC_CELLS):
        fp, fa, (plo, phi), aband = PAC_CELLS[int(cell)]
        pac = {"cell": int(cell), "fp": fp, "fa": fa,
               "phase_band": [plo, phi], "amp_band": list(aband) if aband
               else None, "bins": PAC_BINS}
        if aband:
            ph = {"a": np.angle(analytic(xa, fs, plo, phi, pad=True)),
                  "b": np.angle(analytic(xb, fs, plo, phi, pad=True))}
            am = {"a": np.abs(analytic(xa, fs, aband[0], aband[1], pad=True)),
                  "b": np.abs(analytic(xb, fs, aband[0], aband[1], pad=True))}
            for key, (p_, a_) in (("aa", ("a", "a")), ("ab", ("a", "b")),
                                  ("ba", ("b", "a")), ("bb", ("b", "b"))):
                dist, mi = _pac_bins(ph[p_], am[a_])
                pac[key] = {"p": _rl(dist), "mi": _fv(mi)}
        out["pac"] = pac
    return out
