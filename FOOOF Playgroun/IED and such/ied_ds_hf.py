"""
ied_ds_hf.py -- 500-1000 Hz power for IEDs and dentate spikes, and the
FOOOF machinery that says whether it is an oscillation or just broadband.

WHY AMPLITUDE AND POWER NEED DIFFERENT DATA
===========================================
v3 and v4 measure amplitude off a store that is lowpassed at 300 Hz and
decimated to 2 kHz. Nothing above 250 Hz survives that -- the anti-alias
filter removed it on purpose. So v5 cannot reuse that cache; it builds its
own, lowpassed at 2000 Hz and decimated to 5 kHz (Nyquist 2500), which leaves
250-2000 Hz intact. It is the same `EventStore`, only with different filter
settings, so the cache key separates the two automatically.

The recording supports this: Cheetah's `DspHighCutFrequency` is 7500 Hz at a
30 kHz sample rate, so 250-2000 Hz is real signal and not filter skirt.

WHAT "POWER ABOVE 250 Hz" ACTUALLY MEANS, AND THE TWO ANSWERS
=============================================================
There are two different questions hiding in the phrase, and they want
different tools:

  BAND POWER   How much energy sits between 500 and 1000 Hz? That is an
               integral under the PSD. FOOOF is not needed and does not help.
  OSCILLATION  Is there a narrowband rhythm in 500-1000 Hz as opposed to
               simply more broadband energy? That is what FOOOF answers, and
               band power cannot.

The distinction is the whole HFO false-positive problem. A sharp transient is
broadband: an IED's fast edges put energy across 250-2000 Hz with no
oscillation anywhere, and a band-pass filter will render that as a convincing
"ripple" that is only the filter ringing on a step. FOOOF separates them
because it models the spectrum as

    PSD(f)  =  aperiodic(f)  +  sum of Gaussian peaks

in log-log space. A transient raises the APERIODIC part (flatter 1/f, lower
exponent, higher offset) and produces no peak. A true fast ripple appears as a
PEAK standing above the aperiodic fit at its own centre frequency. So:

  aperiodic exponent / offset  ->  "is the spectrum flatter/louder overall"
  fitted peak above 250 Hz     ->  "is there an actual oscillation"

Both are reported per event. A class that differs only in exponent has more
broadband energy; a class that differs in peak power has more oscillations.

MEASURED RELATIVE TO A BASELINE, NOT IN ABSOLUTE uV^2/Hz
========================================================
Absolute power depends on the contact's impedance and the background state, so
every event's HF power is expressed in dB against a baseline window taken from
the same contact, the same event, a settable distance before the stamp. What
is compared between classes is therefore "how far above its own background did
this event go", which is the comparison that survives a different electrode.

THE RAIL, HERE, BIASES THE OTHER WAY
====================================
v4 had to worry that clipping inflates a maximum. For power above 250 Hz it
does the opposite, measured: clipping a clean trace at progressively lower
limits REDUCES its 250-500 Hz power (x0.91 at 1200 uV, x0.62 at 800, x0.47 at
500), because flattening a peak destroys the fast edges that carry the
high-frequency energy -- more than the clipped corner adds back. So an IED's
HF power here is if anything an UNDER-estimate. That is a safer direction than
v4's, but it is still a bias and it still falls on the class that clips most.

Mains is not a problem in this band: 300, 360, 420 and 480 Hz sit only 1.03 to
1.13 times above their neighbouring bins, so no notch is applied by default.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt, spectrogram, welch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ied_ds import Probe64, read_ds_bank, read_ied_events   # noqa: E402
from ied_ds_store import EventStore                         # noqa: E402

# The HF cache: wide enough for 250-2000 Hz, small enough to hold 309 events.
HF_LOWPASS = 2000.0
HF_Q = 6                      # 30000 -> 5000 Hz
HF_HALF_MS = 200.0
# FIXED at 500-1000 Hz. Not a slider: the band is part of what the
# measurement IS, and a band that moves while numbers are being read makes two
# runs incomparable without either of them recording which band they used.
HF_BAND = (500.0, 1000.0)
BASELINE_OFFSET_MS = 150.0    # baseline window centred this far before the event
BASELINE_WIN_MS = 40.0

# FOOOF is fitted over this range. NOT 1-2000: a single aperiodic component
# cannot describe three decades of a neural spectrum, and forcing it to try
# makes the fit in the band of interest worse than no fit at all.
FIT_RANGE = (100.0, 2000.0)


def build_hf_store(probe=None, category="Solid", progress=None, refresh=False,
                   half_ms=HF_HALF_MS, lowpass=HF_LOWPASS, q=HF_Q):
    p = probe or Probe64()
    st = EventStore.build(p, read_ied_events(category=category),
                          read_ds_bank(), half_ms=half_ms, lowpass=lowpass,
                          q=q, progress=progress, refresh=refresh)
    return p, st


# --------------------------------------------------------------------------
# Band-limited envelope -- the "is there HF, and when" trace
# --------------------------------------------------------------------------
def hf_envelope(x, fs, band=HF_BAND, smooth_ms=2.0):
    """|Hilbert| of the band-passed trace, lightly smoothed.

    This is what makes high-frequency power visible in TIME rather than as one
    number: it answers "was the fast activity locked to the discharge, or was
    it there anyway", which a single band-power figure cannot.
    """
    lo, hi = band
    nyq = fs / 2.0
    sos = butter(4, [max(lo / nyq, 1e-4), min(hi / nyq, 0.99)],
                 btype="band", output="sos")
    y = sosfiltfilt(sos, np.asarray(x, dtype=float), axis=0)
    env = np.abs(hilbert(y, axis=0))
    n = max(1, int(round(smooth_ms * 1e-3 * fs)))
    if n > 1:
        k = np.ones(n) / n
        if env.ndim == 1:
            env = np.convolve(env, k, mode="same")
        else:
            env = np.apply_along_axis(
                lambda c: np.convolve(c, k, mode="same"), 0, env)
    return env


# --------------------------------------------------------------------------
# Spectra
# --------------------------------------------------------------------------
def psd(x, fs, nperseg=None):
    """Welch PSD of one window.

    `nperseg` defaults to the whole window, which at +-25 ms and 5 kHz is 250
    samples and 20 Hz resolution. That is coarse for a narrow peak but the
    band being integrated is 250 Hz wide, so it is ample for band power --
    and it is why FOOOF is fitted on AVERAGED spectra rather than per event.
    """
    x = np.asarray(x, dtype=float)
    n = x.shape[0]
    # nperseg must not exceed the window: scipy silently clamps it and then
    # rejects the noverlap that was computed from the unclamped value, so the
    # overlap is derived AFTER the clamp rather than before it.
    nper = min(int(nperseg or 512), n)
    if nper < 8:
        shape = (1,) if x.ndim == 1 else (1,) + x.shape[1:]
        return np.array([np.nan]), np.full(shape, np.nan)
    f, P = welch(x, fs=fs, nperseg=nper, noverlap=nper // 2,
                 scaling="density", axis=0)
    return f, P


def band_power(f, P, band=HF_BAND):
    lo, hi = band
    m = (f >= lo) & (f < hi)
    if m.sum() < 2:
        return np.full(P.shape[1:], np.nan) if P.ndim > 1 else np.nan
    return np.trapezoid(P[m], f[m], axis=0)


def db(a, b):
    """10*log10(a/b), NaN-safe."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(np.where((a > 0) & (b > 0), a / b, np.nan))


# --------------------------------------------------------------------------
# FOOOF
# --------------------------------------------------------------------------
def fit_fooof(f, P, frange=FIT_RANGE, max_peaks=4, aperiodic_mode="fixed"):
    """Fit one spectrum and pull out what matters above 250 Hz.

    Returns a dict with the model, the aperiodic parameters, and the biggest
    fitted peak whose centre lies in the HF band. `None` back means the fit
    failed or there was nothing in range -- reported rather than substituted
    with zeros, because "no oscillation was found" and "the fit did not run"
    are different findings.
    """
    try:
        from fooof import FOOOF
    except Exception:
        return None
    f = np.asarray(f, dtype=float)
    P = np.asarray(P, dtype=float)
    ok = np.isfinite(P) & (P > 0)
    if ok.sum() < 8:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fm = FOOOF(peak_width_limits=[20.0, 250.0], max_n_peaks=max_peaks,
                   min_peak_height=0.05, aperiodic_mode=aperiodic_mode,
                   verbose=False)
        try:
            fm.fit(f[ok], P[ok], frange)
        except Exception:
            return None
    if not np.all(np.isfinite(fm.aperiodic_params_)):
        return None
    ap = fm.aperiodic_params_
    out = {"fm": fm, "freqs": fm.freqs, "spectrum": fm.power_spectrum,
           "fit": fm.fooofed_spectrum_, "ap_fit": fm._ap_fit,
           "flat": fm._spectrum_flat,
           "offset": float(ap[0]), "exponent": float(ap[-1]),
           "r2": float(fm.r_squared_), "error": float(fm.error_),
           "peaks": fm.peak_params_,
           "hf_peak_cf": np.nan, "hf_peak_pw": np.nan, "hf_peak_bw": np.nan}
    pk = fm.peak_params_
    if pk is not None and len(pk):
        inb = pk[(pk[:, 0] >= HF_BAND[0]) & (pk[:, 0] < HF_BAND[1])]
        if len(inb):
            best = inb[np.argmax(inb[:, 1])]
            out["hf_peak_cf"] = float(best[0])
            out["hf_peak_pw"] = float(best[1])
            out["hf_peak_bw"] = float(best[2])
    return out


# --------------------------------------------------------------------------
# Per-event measurement
# --------------------------------------------------------------------------
class HFMeasure:
    """Band power, baseline ratio and envelope for every event."""

    def __init__(self, store, probe, band=HF_BAND, win_ms=25.0,
                 base_offset_ms=BASELINE_OFFSET_MS, base_win_ms=BASELINE_WIN_MS):
        self.st = store
        self.p = probe
        self.band = band
        self.win_ms = win_ms
        self.base_offset_ms = base_offset_ms
        self.base_win_ms = base_win_ms
        self._env = {}

    def envelope(self, i):
        """Cached HF envelope for event i, [T, 64]."""
        key = (i, self.band, self.st.notch)
        got = self._env.get(key)
        if got is None:
            got = hf_envelope(self.st.trace(i), self.st.fs, self.band)
            if len(self._env) > 24:      # bounded: one envelope is 2001 x 64
                self._env.clear()
            self._env[key] = got
        return got

    def _slice(self, i, shift, centre_ms, win_ms):
        y = self.st.trace(i)
        c = self.st.stamp_i + int(shift) + int(round(centre_ms * 1e-3 * self.st.fs))
        h = int(round(win_ms * 1e-3 * self.st.fs))
        lo, hi = max(0, c - h), min(y.shape[0], c + h + 1)
        return y[lo:hi]

    def event_psd(self, i, shift, nperseg=None):
        seg = self._slice(i, shift, 0.0, self.win_ms)
        return psd(seg, self.st.fs, nperseg)

    def base_psd(self, i, shift, nperseg=None):
        # Keep the baseline window inside the cached span. Pushed past the
        # edge it silently shrinks to a handful of samples, and a PSD from
        # those is noise that every event's dB is then divided by.
        room = self.st.half_ms - self.base_win_ms / 2 - 5.0
        off = min(self.base_offset_ms, room)
        seg = self._slice(i, shift, -off, self.base_win_ms / 2)
        return psd(seg, self.st.fs, nperseg)

    def measure(self, i, shift):
        """(hf_db[64], hf_abs[64], best_contact) for one event.

        dB of the event window's band power against the same contact's own
        baseline window.
        """
        fe, Pe = self.event_psd(i, shift)
        fb, Pb = self.base_psd(i, shift)
        pe = band_power(fe, Pe, self.band)
        pb = band_power(fb, Pb, self.band)
        d = db(pe, pb)
        d = np.where(self.p.included, d, np.nan)
        pe = np.where(self.p.included, pe, np.nan)
        best = int(np.nanargmax(d)) if np.isfinite(d).any() else -1
        return d, pe, best

    def measure_all(self, idx, shifts):
        D = np.full((len(idx), len(self.p.numbers)), np.nan)
        A = np.full((len(idx), len(self.p.numbers)), np.nan)
        W = np.full(len(idx), -1, dtype=int)
        for j, i in enumerate(idx):
            D[j], A[j], W[j] = self.measure(int(i), shifts[j])
        return D, A, W


def _selftest():
    import time
    def prog(i, n, msg):
        if i % 60 == 0 or i >= n - 1:
            print("  [%3d/%3d] %s" % (i, n, msg))
    t = time.time()
    p, st = build_hf_store(progress=prog)
    print("HF store: %.1f s, %d events, fs %.0f Hz, T %d, %.0f MB"
          % (time.time() - t, len(st), st.fs, st.data.shape[1],
             st.data.nbytes / 1e6))
    print("usable band: up to %.0f Hz (lowpass %.0f)" % (st.fs / 2, st.lowpass))

    shifts = np.zeros(len(st), dtype=int)
    for i in range(len(st)):
        shifts[i], _ = st.centre(i, 0, 50.0)

    hm = HFMeasure(st, p)
    t = time.time()
    for kind in ("IED", "DS"):
        idx = st.where(kind)
        D, A, W = hm.measure_all(idx, shifts[idx])
        best = np.nanmax(D, axis=1)
        csc = p.numbers[W[W >= 0]]
        vals, cnts = np.unique(csc, return_counts=True)
        top = vals[np.argsort(cnts)[::-1][:3]]
        print("\n%-4s n=%d   HF %s Hz, best contact vs own baseline:"
              % (kind, len(idx), "%.0f-%.0f" % HF_BAND))
        print("      median %+6.2f dB   IQR %+.2f to %+.2f   max %+.2f"
              % (np.nanmedian(best), *np.nanpercentile(best, [25, 75]),
                 np.nanmax(best)))
        print("      peak contacts: %s"
              % ", ".join("CSC%d %s" % (c, p.region.get(int(c), "")) for c in top))
    print("\nmeasured both classes in %.1f s" % (time.time() - t))

    # FOOOF on the class-average spectrum of the modal contact
    print("\nFOOOF on class-average spectra (fit %s Hz):" % (FIT_RANGE,))
    for kind in ("IED", "DS"):
        idx = st.where(kind)
        acc = None
        for i in idx:
            f, P = hm.event_psd(int(i), shifts[i], nperseg=256)
            acc = P if acc is None else acc + P
        acc /= len(idx)
        ch = int(np.nanargmax(band_power(f, np.where(
            p.included, acc, np.nan), HF_BAND)))
        r = fit_fooof(f, acc[:, ch])
        if r is None:
            print("  %-4s fit failed" % kind)
            continue
        print("  %-4s CSC%-3d exponent %.3f  offset %.3f  R2 %.3f  "
              "HF peak %s"
              % (kind, p.numbers[ch], r["exponent"], r["offset"], r["r2"],
                 "none" if not np.isfinite(r["hf_peak_cf"])
                 else "%.0f Hz, %.3f log10 power" % (r["hf_peak_cf"],
                                                     r["hf_peak_pw"])))


if __name__ == "__main__":
    _selftest()
