# -*- coding: utf-8 -*-
"""dspcahf.py -- high-frequency power per dentate spike, for X-ray's Y axis.

WHY THIS IS A SECOND READ, AND NOT A COLUMN OFF THE FIRST ONE

X-ray reads at 1000 Hz. That is the right rate for everything else it does
-- a dentate spike is tens of milliseconds and the DS band is 5-100 Hz --
and it is decided by `Params.lfp_fs`, which the decimation in `_read_span`
turns into a factor of thirty on a 30 kHz recording.

The band this module measures is 500-1000 Hz. At 1000 Hz sampling the
Nyquist is 500, so that band is entirely at or above it AND has already
been taken out by the anti-alias filter the decimation applies. A number
computed for it from the cached read would not be high-frequency power; it
would be whatever survived, scaled to look like an answer.

So this reads the recording again at 5 kHz, which is `HF_Q = 6` on a 30 kHz
file -- the same factor `ied_ds_hf.py` uses, for the same reason. It is
minutes, and it is cached on the question like every other expensive thing
here, so it is minutes once per recording rather than minutes per look.

THE MEASUREMENT, WHICH IS ied_ampwidth_gui_v5's

  band            500-1000 Hz, FIXED. Not a setting, because the band is
                  part of what the measurement IS: two runs under one name
                  that used different bands are not comparable, and
                  nothing in the numbers would say so.
  event window    +-25 ms about the stamp
  baseline        +-20 ms, centred 150 ms BEFORE the stamp, on the same
                  contact of the same event
  spectrum        Welch, `nperseg` the window or 512, whichever is smaller,
                  half overlap, density scaling
  band power      the trapezoid integral of the PSD across the band
  the number      10*log10(event / baseline)

DB AGAINST ITS OWN BASELINE, not against an absolute. Impedance varies
across a probe and across a day, so raw band power on contact 40 is not
comparable with contact 12 and neither is comparable with yesterday's.
A ratio to the same contact's own quiet period a moment earlier is.

WHAT IT IS NOT. It is not evidence of an oscillation. An IED's fast edges
raise the whole spectrum, and band-passing a sharp transient makes a
filter ring convincingly; band power cannot tell either of those from a
ripple. v5 answers that with a FOOOF fit on averaged spectra, which needs
an averaged spectrum and is a different panel. This is the one number per
event that a scatter axis can be, and it is labelled as power rather than
as oscillation.

NOTHING HERE DRAWS, for the same reason `dspca.py` does not.
"""
from __future__ import annotations

import numpy as np

from . import csc
from . import incisor

HF_BAND = (500.0, 1000.0)     # fixed; see the module docstring
HF_FS = 5000.0                # what the read is decimated to
HF_WIN_MS = 25.0              # half-width of the event window
HF_BASE_OFF_MS = 150.0        # how far before the stamp the baseline sits
HF_BASE_WIN_MS = 40.0         # full width of the baseline window
HF_PAD_S = 0.30               # read margin, so both windows are inside it


class HfError(Exception):
    """Something this pass cannot do, said in a sentence."""


def hf_keys():
    """What makes two HF passes the same question."""
    return {"hf_band": list(HF_BAND), "hf_fs": HF_FS,
            "hf_win_ms": HF_WIN_MS, "hf_base_off_ms": HF_BASE_OFF_MS,
            "hf_base_win_ms": HF_BASE_WIN_MS}


def _psd(x, fs):
    """Welch PSD down axis 0. `x` is [samples] or [samples x channels]."""
    from scipy.signal import welch
    x = np.asarray(x, dtype=float)
    n = x.shape[0]
    # `nperseg` must not exceed the window. scipy clamps it silently and
    # then rejects the overlap computed from the UNclamped value, so the
    # overlap is derived after the clamp rather than before it.
    nper = min(512, n)
    if nper < 8:
        shape = (1,) if x.ndim == 1 else (1,) + x.shape[1:]
        return np.array([np.nan]), np.full(shape, np.nan)
    f, P = welch(x, fs=fs, nperseg=nper, noverlap=nper // 2,
                 scaling="density", axis=0)
    return f, P


def _band_power(f, P, band=HF_BAND):
    lo, hi = band
    m = (f >= lo) & (f < hi)
    if m.sum() < 2:
        return np.full(P.shape[1:], np.nan) if P.ndim > 1 else np.nan
    trapz = getattr(np, "trapezoid", None) or np.trapz
    return trapz(P[m], f[m], axis=0)


def _db(a, b):
    """10*log10(a/b), NaN where either side is not positive."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(np.where((a > 0) & (b > 0), a / b, np.nan))


def measure(session, channels, stamps, p, bad=None, stop=None, job=None):
    """HF power per event per contact, and the dB against its own baseline.

    One window per stamp rather than one span per run of stamps: the
    windows here are 50 ms of a 5 kHz read and the baseline sits 150 ms
    before, so merging neighbours would save little and the arithmetic of
    which sample is which stamp's is where this kind of code goes wrong.

    `stop` is asked before each event, and has no progress attached -- see
    the note on `dspca.read`.
    """
    nums = [int(c["number"]) for c in channels]
    n_ch = len(nums)
    if not stamps:
        raise HfError("There are no stamps to measure.")

    half_s = HF_WIN_MS * 1e-3
    base_off_s = HF_BASE_OFF_MS * 1e-3
    base_half_s = (HF_BASE_WIN_MS / 2.0) * 1e-3
    # Everything both windows need, plus a margin for the decimation edge.
    back = base_off_s + base_half_s + HF_PAD_S
    fwd = half_s + HF_PAD_S

    D = np.full((len(stamps), n_ch), np.nan)
    A = np.full((len(stamps), n_ch), np.nan)
    missed = []
    fs_out = None

    if job:
        job.begin("ds pca hf", of=len(stamps), unit="spikes")

    for i, ev in enumerate(stamps):
        if stop:
            stop()
        if job:
            job.tick("ds pca hf", i)
        t = float(ev["t"])
        cols = []
        ok = True
        for ch in channels:
            raw, got_t0, ch_fs = csc._read_channel_window(
                session, ch, t - back, t + fwd)
            if raw is None or np.asarray(raw).size < 64:
                ok = False
                break
            q = incisor.decimation_for(ch_fs, HF_FS)
            dec = (incisor._decimate(raw, q) if q > 1
                   else np.asarray(raw, dtype=float))
            fs_out = ch_fs / q
            cols.append((dec, got_t0))
        if not ok or not cols:
            missed.append(i)
            continue

        keep = min(c.size for c, _ in cols)
        anchor = cols[0][1]
        Y = np.vstack([c[:keep] for c, _ in cols]).T       # [samples x ch]

        def _slice(centre_s, half):
            c = int(round((t + centre_s - anchor) * fs_out))
            h = int(round(half * fs_out))
            lo, hi = max(0, c - h), min(Y.shape[0], c + h + 1)
            return Y[lo:hi]

        ev_seg = _slice(0.0, half_s)
        ba_seg = _slice(-base_off_s, base_half_s)
        if ev_seg.shape[0] < 16 or ba_seg.shape[0] < 16:
            missed.append(i)
            continue
        fe, Pe = _psd(ev_seg, fs_out)
        fb, Pb = _psd(ba_seg, fs_out)
        pe = _band_power(fe, Pe)
        pb = _band_power(fb, Pb)
        A[i] = pe
        D[i] = _db(pe, pb)

    # A contact nobody can read is not a quiet contact: it is no answer,
    # and averaging it in as one would drag every event's number down.
    out_bad = set(int(k) for k in (bad or {}))
    for j, n in enumerate(nums):
        if n in out_bad:
            D[:, j] = np.nan
            A[:, j] = np.nan

    with np.errstate(invalid="ignore"):
        best = np.where(np.isfinite(D).any(axis=1),
                        np.nanargmax(np.where(np.isfinite(D), D, -np.inf),
                                     axis=1), -1)
    return {
        "nums": nums,
        "db": D,
        "abs": A,
        "best": [int(b) for b in best],
        "fs": float(fs_out or HF_FS),
        "missed": missed,
        "band": list(HF_BAND),
        "win_ms": HF_WIN_MS,
        "base_off_ms": HF_BASE_OFF_MS,
        "base_win_ms": HF_BASE_WIN_MS,
    }


def per_event(hf, sel=None):
    """One number per event: the dB on the best contact, or over `sel`.

    `sel` is the row indices of the contacts the box covers. Averaged over
    those rather than taken from the best one when a box is given, because
    the box is the statement of where the event is being measured and a
    per-event best contact would wander between events.
    """
    D = np.asarray(hf.get("db"))
    if D.size == 0:
        return []
    if sel:
        sub = D[:, list(sel)]
        with np.errstate(invalid="ignore"):
            v = np.nanmean(sub, axis=1)
    else:
        with np.errstate(invalid="ignore"):
            v = np.nanmax(D, axis=1)
    return [None if not np.isfinite(x) else float(x) for x in v]
