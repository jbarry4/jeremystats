"""
panorama.py -- what a whole recording did, spectrally, from end to end.

The Spectrum view answers "how much power, at which frequency" for a window or
a whole recording, collapsed over time. XploreFinder's spectrogram panel answers
"what changed, when" for a window you are looking at. Neither answers the
question this does, which is the one asked of a recording before anything else:
across the entire session, which frequency was in charge, and how often?

Three things come out of one pass, and that is the point of the module:

  the spectrogram       power against frequency against time, whole recording
  the histogram         how many windows each frequency was dominant in
  the power spectrum    the whole-recording PSD

They are not three analyses. Averaging the spectrogram's columns IS the
whole-recording Welch spectrum -- same segments, same window, same average --
so computing a second one would be reading a thirty-minute recording twice to
get the same numbers. The per-window fits come off the same columns. One read,
three answers.

WHY EACH COLUMN IS A SHORT WELCH AND NOT ONE PERIODOGRAM
--------------------------------------------------------
A column here averages `n_avg` overlapping sub-windows of `sub_s` seconds
rather than being a single transform of `win_s` seconds. This is not a detail.
Fitting one periodogram per column gave a median R-squared of 0.45 and
exponents ranging -0.3 to 2.9 on real data -- a fit to noise, and the "dominant
frequency" that came out of it was a measurement of per-window variance rather
than of any rhythm. Averaging first is what makes a per-window fit mean
anything, and it is why a group difference out of this is a difference in
biology rather than in signal-to-noise.

WHY GAPS ARE HOLES AND NOT CLOSED UP
------------------------------------
Cheetah closes a record early when acquisition hiccups, so a recording can be
several segments with time missing between them. `spectrum.py` reads chunk by
chunk and concatenates, which is right for a PSD -- a spectrum does not care
what order its samples came in -- and wrong here. A spectrogram's x-axis is
time: concatenating across a gap draws every column after it earlier than it
happened, silently, by as much as the gap. Eight of twenty-five PTEN recordings
have gaps; see `continuity.py`.

So the signal is laid out on the TRUE time axis with NaN where nothing was
recorded. Windows overlapping a hole come out NaN, are drawn transparent, and
take no part in the spectrum, the fits or the histogram. A window that spans a
gap has no single time and no honest spectrum, and saying so is the answer.

WHICH FITTER, AND WHY IT IS NOT THE ONE NEXT DOOR
-------------------------------------------------
This uses the `fooof` package. The GUI also carries `specparam.py`, a
dependency-free reimplementation of the same algorithm that Braid and the
Spectrum view use, whose defaults differ slightly (peak width floor 0.5 against
1.0, minimum height 0.0 against 0.05). The lab has already run the command-line
analysis this replaces, and numbers out of the GUI have to be comparable with
the numbers already in people's notebooks -- so this one uses the package those
came from. Every result and every saved file records which fitter produced it
and with what settings, because two fitters in one app is only a problem when
you cannot tell which you are looking at.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import threading
import warnings

import numpy as np

from . import analysis, cfc, csc, nlx, specparam, spectrum

try:
    from scipy import signal as _sig
    HAVE_SCIPY = True
except Exception:                                        # noqa: BLE001
    _sig = None
    HAVE_SCIPY = False

try:
    # `record=True`, not `simplefilter("ignore")`.
    #
    # The package announces its own deprecation on import -- noted, and
    # deliberate; see the module docstring -- and it forces the filter to
    # show it, so an "ignore" set here is overridden and the notice lands on
    # stderr at every server start anyway. Recording captures the warning
    # instead of filtering it, which the package cannot undo.
    with warnings.catch_warnings(record=True):
        from fooof import FOOOFGroup as _FOOOFGroup
        from fooof.sim.gen import gen_aperiodic as _gen_aperiodic
        import fooof as _fooof
    HAVE_FOOOF = True
    FOOOF_VERSION = getattr(_fooof, "__version__", "?")
except Exception:                                        # noqa: BLE001
    _FOOOFGroup = None
    _gen_aperiodic = None
    HAVE_FOOOF = False
    FOOOF_VERSION = None


# The band this is asked about. 2 Hz because below it a 2 s transform has
# nothing to say, 200 because that is where the Spectrum view stops too and
# the two must be comparable.
DEFAULT_FLO = 2.0
DEFAULT_FHI = 200.0

# The three times that define a column, and the one relationship between them
# that matters: `sub_s` buys frequency resolution (1/sub Hz), `step_s` is how
# often the histogram gets a vote, and `win_s` is how much recording each
# column averages over. n_avg = (win - sub)/step + 1 sub-windows per column.
DEFAULT_SUB_S = 2.0
DEFAULT_WIN_S = 8.0
DEFAULT_STEP_S = 1.0

DEFAULT_BINS = 48
DEFAULT_SCALE = "log"

# Read in shorter chunks than `spectrum.CHUNK_SECONDS`. Not for throughput --
# the extra discarded edges cost about three percent -- but because the
# waiting screen paints the spectrogram as it arrives, and at two minutes a
# chunk a thirty-five minute recording moves eighteen times in four minutes,
# which does not read as progress.
CHUNK_SECONDS = 30.0

# How wide a picture is worth sending, and how tall.
MAX_COLUMNS = 2000
IMAGE_ROWS = 220
PREVIEW_COLS = 240
PREVIEW_ROWS = 110

# Windows per call to the fitter.
#
# Not one call for the lot, which is what it looks like it should be: a
# fit is about sixty-five milliseconds, so a thirty-five minute recording
# is over two minutes inside one call -- two minutes with the bar frozen
# at nothing and Cancel doing nothing, because neither can be answered
# from inside it. Sixty-four is about four seconds: often enough that the
# bar moves and Cancel lands, rare enough that the per-call overhead is
# not worth measuring.
FIT_BATCH = 64

# The settings the playground scripts ran with, which is what makes a number
# out of this comparable with a number already in somebody's notebook.
FIT_DEFAULTS = {
    "peak_width_limits": (1.0, 12.0),
    "max_n_peaks": 6,
    "min_peak_height": 0.05,
    "aperiodic_mode": "fixed",
}


def fit_engine(spec=None):
    """Which fitter produced a number, and with what settings.

    Carried in every result and every saved file. There are two spectral
    fitters in this app and the only thing that makes that safe is that no
    number is ever ambiguous about which one it came from.
    """
    out = {"name": "fooof", "version": FOOOF_VERSION,
           "available": bool(HAVE_FOOOF)}
    out.update(_fit_settings(spec or {}))
    return out


def _fit_settings(spec):
    got = dict(FIT_DEFAULTS)
    for k in list(got):
        if spec.get(k) is not None:
            got[k] = spec[k]
    got["peak_width_limits"] = [float(x) for x in got["peak_width_limits"]]
    got["max_n_peaks"] = int(got["max_n_peaks"])
    got["min_peak_height"] = float(got["min_peak_height"])
    got["aperiodic_mode"] = str(got["aperiodic_mode"])
    return got


# ==========================================================================
# Reading, on the true time axis
# ==========================================================================
def segments_for(session, ch, t0, t1):
    """The contiguous stretches of [t0, t1), in true seconds, and the gaps.

    Reading a stretch that spans a gap returns the two sides concatenated,
    with nothing to say where the join was -- so the stretches are read apart
    and each is put back at the time it actually happened.
    """
    whole = [(float(t0), float(t1))]
    none = {"n": 0, "seconds": 0.0, "checked": False, "n_segments": 1,
            "paused_s": 0.0, "dropped_s": 0.0, "n_paused": 0, "n_dropped": 0}
    if (session or {}).get("source") != "ncs" or not ch.get("file"):
        # A .mat or the demo is already one continuous array: Toothy closed
        # the gaps before it was written, which is the problem this cannot
        # see and `continuity.py` exists to report.
        return whole, none
    try:
        seg = nlx.segment_ncs(ch["file"], strict=False)
    except Exception as exc:                             # noqa: BLE001
        got = dict(none)
        got["error"] = str(exc)[:200]
        return whole, got

    out = []
    for s in seg.get("segments") or []:
        a = float(s["true_t0_s"])
        b = a + float(s["duration_s"])
        a, b = max(a, t0), min(b, t1)
        if b > a:
            out.append((a, b))
    if not out:
        return whole, none

    inside = [g for g in (seg.get("gaps") or [])
              if t0 <= g.get("at_true_time_s", -1) <= t1]
    return out, {
        "n": len(inside),
        "seconds": round(sum(g["gap_s"] for g in inside), 6),
        "checked": True,
        "n_segments": len(out),
        "paused_s": round(sum(g["gap_s"] for g in inside if g.get("paused")), 6),
        "dropped_s": round(sum(g["gap_s"] for g in inside
                               if not g.get("paused")), 6),
        "n_paused": sum(1 for g in inside if g.get("paused")),
        "n_dropped": sum(1 for g in inside if not g.get("paused")),
        "true_duration_s": seg.get("true_duration_s"),
        "concat_duration_s": seg.get("concat_duration_s"),
    }


def _decimate(seg, factor):
    """Decimate one piece, or slice it when it is too short to filter.

    `scipy.signal.decimate` filtfilts a FIR of about 20*factor taps and needs
    several times that many samples. The last fragment of a segment can be
    shorter than that; slicing it is crude, but it is a fraction of a second
    at the end of a stretch and the alternative is an exception.
    """
    if factor <= 1 or not HAVE_SCIPY:
        return np.asarray(seg, dtype=np.float64)
    need = 3 * (20 * factor + 1)
    if seg.size < need:
        return np.asarray(seg[::factor], dtype=np.float64)
    return _sig.decimate(np.asarray(seg, dtype=np.float64), factor,
                         ftype="fir", zero_phase=True)


def read_gapped(session, ch, t0, t1, factor, out_fs, job=None, on_read=None,
                on_chunk=None):
    """One channel over [t0, t1), decimated, on the TRUE time axis.

    Returns (x, gaps). `x` is NaN wherever the recording has a hole, so its
    index IS its time and every later step inherits that for free.
    """
    n_out = max(0, int(round((t1 - t0) * out_fs)))
    x = np.full(n_out, np.nan, dtype=np.float64)
    segs, gaps = segments_for(session, ch, t0, t1)

    read_s = 0.0
    for (a, b) in segs:
        # One write cursor per segment, not one per chunk.
        #
        # A segment is contiguous by definition -- that is what makes it a
        # segment -- so its chunks are written one after another. Placing
        # each at the time it nominally starts instead left a one-sample
        # hole wherever a chunk came back a sample short of its span, and a
        # stray NaN costs a whole window of spectrogram, not a sample.
        cursor = max(0, min(int(round((a - t0) * out_fs)), n_out))
        seg_end = max(cursor, min(int(round((b - t0) * out_fs)), n_out))
        at = a
        while at < b:
            if job:
                job.check()
            lo = max(a, at - spectrum.EDGE_SECONDS)
            hi = min(b, at + CHUNK_SECONDS + spectrum.EDGE_SECONDS)
            seg, got_t0, fs = csc._read_channel_window(session, ch, lo, hi)
            if seg.size:
                piece = _decimate(seg, factor)
                rate = (fs / factor) if factor > 1 else fs
                # Cut from where the read ACTUALLY starts: a .ncs read snaps
                # back to a record boundary, so the samples begin up to 17 ms
                # at 30 kHz before the time asked for.
                want_lo = at
                want_hi = min(b, at + CHUNK_SECONDS)
                i0 = int(round((want_lo - got_t0) * rate))
                i1 = int(round((want_hi - got_t0) * rate))
                i0 = max(0, min(i0, piece.size))
                i1 = max(i0, min(i1, piece.size))
                piece = piece[i0:i1]
                if piece.size and cursor < seg_end:
                    # Never past this segment's own slot: rounding drift
                    # must not push samples into the gap after it, which is
                    # the one place they certainly did not come from.
                    end = min(seg_end, cursor + piece.size)
                    x[cursor:end] = piece[:end - cursor]
                    cursor = end
            at += CHUNK_SECONDS
            read_s = min(t1 - t0, read_s + CHUNK_SECONDS)
            if on_read:
                on_read(read_s)
            if on_chunk:
                on_chunk(x, min(at, b))
    return x, gaps


# ==========================================================================
# The spectrogram, and everything that comes off it
# ==========================================================================
def _bridge_line(freqs, pxx, mask):
    """Bridge the mains bins across every column at once, in log power.

    `spectrum.remove_line` does this for one spectrum; a spectrogram is two
    thousand of them and `np.interp` does not take a second axis, so the
    weights are worked out once from the frequency axis -- which is shared --
    and applied to the whole array.
    """
    out = np.array(pxx, dtype=np.float64, copy=True)
    if not mask.any():
        return out, 0.0
    good = ~mask
    if good.sum() < 2:
        return out, 0.0

    lf = np.log10(np.asarray(freqs, dtype=float))
    with np.errstate(divide="ignore", invalid="ignore"):
        lp = np.log10(out)
    lp[~np.isfinite(lp) & np.isfinite(out)] = np.nan

    xg = lf[good]
    idx = np.clip(np.searchsorted(xg, lf[mask]), 1, xg.size - 1)
    x0, x1 = xg[idx - 1], xg[idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.where(x1 > x0, (lf[mask] - x0) / (x1 - x0), 0.0)

    g = lp[good]
    lo, hi = g[idx - 1, :], g[idx, :]
    before = np.nanmean(out[mask, :]) if mask.any() else 0.0
    lp[mask, :] = lo + w[:, None] * (hi - lo)
    out = np.power(10.0, lp)
    after = np.nanmean(out[mask, :]) if mask.any() else 0.0
    removed = float(max(0.0, (before - after)))
    return out, removed


def spectrogram(x, fs, sub_s, win_s, step_s, f_lo, f_hi):
    """(freqs, times, pxx) in uV^2/Hz. NaN columns where the recording is."""
    nper = max(16, int(round(sub_s * fs)))
    hop = max(1, int(round(step_s * fs)))
    nover = max(0, min(nper - 1, nper - hop))
    freqs, times, pxx = _sig.spectrogram(
        x, fs=fs, window="hann", nperseg=nper, noverlap=nover,
        scaling="density", mode="psd")

    # Each column an average of the sub-windows covering win_s -- Welch, made
    # explicit. See the module docstring for why this is not optional.
    n_avg = max(1, int(round((win_s - sub_s) / step_s)) + 1)
    if n_avg > 1 and pxx.shape[1] > n_avg:
        from numpy.lib.stride_tricks import sliding_window_view
        pxx = sliding_window_view(pxx, n_avg, axis=1).mean(axis=2)
        times = sliding_window_view(times, n_avg).mean(axis=1)

    keep = (freqs >= f_lo) & (freqs <= f_hi)
    return freqs[keep], times, pxx[keep, :], n_avg


def _log_rows(freqs, m, n_rows=IMAGE_ROWS):
    """Resample the frequency axis onto log-spaced rows, for the picture.

    Over 2-200 Hz on a linear axis theta is four pixels of four hundred and
    nine tenths of the height is 20-200 Hz, so the band people are looking
    for is the one part of the picture that cannot be read.
    """
    f = np.asarray(freqs, dtype=float)
    if f.size < 2:
        return f, m
    lo = max(f[0], 1e-6)
    edges = np.logspace(np.log10(lo), np.log10(f[-1]), int(n_rows) + 1)
    out = np.full((int(n_rows), m.shape[1]), np.nan, dtype=np.float64)
    centres = np.sqrt(edges[:-1] * edges[1:])
    for i in range(int(n_rows)):
        sel = (f >= edges[i]) & (f < edges[i + 1])
        if sel.any():
            out[i, :] = np.nanmean(m[sel, :], axis=0)
        else:
            # Finer than the data here: take the nearest real row rather
            # than leaving a transparent stripe through the picture.
            out[i, :] = m[int(np.argmin(np.abs(f - centres[i]))), :]
    return centres, out


def _clim(m):
    finite = m[np.isfinite(m)]
    if finite.size < 4:
        return -1.0, 1.0
    return (float(np.percentile(finite, 2.0)),
            float(np.percentile(finite, 99.5)))


def render(freqs, times, pxx, cmap="jet", scale="log10", n_rows=IMAGE_ROWS,
           max_cols=MAX_COLUMNS, clim=None):
    """The spectrogram as a PNG data URI, plus what it takes to draw axes."""
    m = np.asarray(pxx, dtype=np.float64)
    if scale != "linear":
        with np.errstate(divide="ignore", invalid="ignore"):
            m = np.log10(m)
        m[~np.isfinite(m)] = np.nan
    if m.shape[1] > max_cols:
        m = analysis._decimate_cols(m, max_cols=max_cols)
    rows, m = _log_rows(freqs, m, n_rows)
    lo, hi = clim if clim else _clim(m)
    # origin="upper": row zero is the top of the image, and a spectrogram is
    # read with the high frequencies up there.
    uri = analysis._encode_image(m[::-1, :], cmap, (lo, hi))
    return {
        "png": uri,
        "t0": float(times[0]) if len(times) else 0.0,
        "t1": float(times[-1]) if len(times) else 0.0,
        "f_lo": float(rows[0]), "f_hi": float(rows[-1]),
        "rows": [float(v) for v in rows],
        "row_scale": "log",
        "vmin": lo, "vmax": hi,
        "cmap": cmap, "scale": scale,
        "n_cols": int(m.shape[1]), "n_rows": int(m.shape[0]),
    }


# ==========================================================================
# Dominant frequency, both ways
# ==========================================================================
def dominant(freqs, pxx, f_lo, f_hi, settings, job=None, stage=None,
             done_base=0):
    """Per-window fits, and the two answers to "which frequency was on top".

    `peak` is the tallest rhythm the fit actually found, and is None when it
    found none -- which is an answer, and the one that matters: a genotype
    that abolishes a rhythm shows up as windows with no peak, not as a
    smaller peak.

    `flat` is the highest bin left after the aperiodic slope is subtracted.
    It always returns a number, which is its weakness as much as its
    convenience: over 2-200 Hz on a 1/f spectrum a window with nothing in it
    still votes, usually near the bottom of the range.
    """
    n = pxx.shape[1]
    out = {
        "peak_hz": np.full(n, np.nan), "peak_pw": np.full(n, np.nan),
        "flat_hz": np.full(n, np.nan),
        "exponent": np.full(n, np.nan), "offset": np.full(n, np.nan),
        "r2": np.full(n, np.nan),
    }
    ok = np.isfinite(pxx).all(axis=0) & (pxx > 0).all(axis=0)
    idx = np.flatnonzero(ok)
    out["n_windows"] = int(n)
    out["n_rejected"] = int(n - idx.size)
    if not idx.size or not HAVE_FOOOF:
        out["n_nopeak"] = int(idx.size)
        return out

    fg = _FOOOFGroup(peak_width_limits=list(settings["peak_width_limits"]),
                     max_n_peaks=settings["max_n_peaks"],
                     min_peak_height=settings["min_peak_height"],
                     aperiodic_mode=settings["aperiodic_mode"],
                     verbose=False)
    freqs = np.asarray(freqs, dtype=float)

    for start in range(0, idx.size, FIT_BATCH):
        if job:
            job.check()
        sel = idx[start:start + FIT_BATCH]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fg.fit(freqs, pxx[:, sel].T.copy(), [float(f_lo), float(f_hi)])

        ap = np.atleast_2d(fg.get_params("aperiodic_params"))
        r2 = np.atleast_1d(fg.get_params("r_squared"))
        log_spectra = fg.power_spectra      # already log10
        ffreqs = fg.freqs

        for i, w in enumerate(sel):
            out["offset"][w] = float(ap[i][0])
            out["exponent"][w] = float(ap[i][-1])
            out["r2"][w] = float(r2[i])
            flat = log_spectra[i] - _gen_aperiodic(ffreqs, ap[i])
            out["flat_hz"][w] = float(ffreqs[int(np.argmax(flat))])

        peaks = fg.get_params("peak_params")
        if peaks is not None and np.size(peaks):
            for row in np.atleast_2d(peaks):
                run = int(row[-1])
                if run < 0 or run >= sel.size:
                    continue
                cf, pw = float(row[0]), float(row[1])
                w = sel[run]
                if not np.isfinite(out["peak_pw"][w]) or pw > out["peak_pw"][w]:
                    out["peak_hz"][w] = cf
                    out["peak_pw"][w] = pw

        if job and stage:
            job.tick(stage, int(done_base + start + sel.size))

    out["n_nopeak"] = int(np.sum(np.isnan(out["peak_hz"][idx])))
    return out


def edges_for(f_lo, f_hi, bins=DEFAULT_BINS, scale=DEFAULT_SCALE):
    """The histogram's bins. Log-spaced by default, and for a reason.

    On linear bins a range that spans two decades makes the top of it a
    forest of thin spikes and squeezes theta into three of them.
    """
    n = max(4, int(bins))
    lo = max(float(f_lo), 1e-6)
    hi = max(float(f_hi), lo * 1.0001)
    if scale == "linear":
        return np.linspace(lo, hi, n + 1)
    return np.logspace(math.log10(lo), math.log10(hi), n + 1)


def histogram(dom, f_lo, f_hi, bins=DEFAULT_BINS, scale=DEFAULT_SCALE):
    """How often each frequency was the dominant one, both ways of asking."""
    edges = edges_for(f_lo, f_hi, bins, scale)
    peak = np.asarray(dom["peak_hz"], dtype=float)
    flat = np.asarray(dom["flat_hz"], dtype=float)
    c_peak, _ = np.histogram(peak[np.isfinite(peak)], bins=edges)
    c_flat, _ = np.histogram(flat[np.isfinite(flat)], bins=edges)
    n_used = int(np.sum(np.isfinite(peak)))
    return {
        "edges": [float(v) for v in edges],
        "peak": [int(v) for v in c_peak],
        "flat": [int(v) for v in c_flat],
        "scale": scale,
        "bins": int(len(edges) - 1),
        "n_windows": int(dom.get("n_windows", 0)),
        "n_rejected": int(dom.get("n_rejected", 0)),
        # Windows the fit looked at and found no rhythm in. Reported rather
        # than folded into the counts: it is the finding, not the shortfall.
        "n_nopeak": int(dom.get("n_nopeak", 0)),
        "n_used": n_used,
    }


# ==========================================================================
# Planning and cost
# ==========================================================================
def plan_for(session, spec):
    """What a run would do, without doing any of it."""
    fs = float(session.get("fs") or 0) or 30000.0
    dur = float(session.get("duration_s") or 0.0)
    t0 = max(0.0, float(spec.get("t0") or 0.0))
    t1 = float(spec.get("t1") or dur or 0.0)
    if t1 <= t0:
        t1 = dur
    span = max(0.0, t1 - t0)

    f_lo = float(spec.get("f_lo") or DEFAULT_FLO)
    f_hi = float(spec.get("f_hi") or DEFAULT_FHI)
    if f_hi <= f_lo:
        f_hi = max(f_lo * 2.0, DEFAULT_FHI)

    want_fs = spectrum.target_rate(f_hi)
    factor = max(1, int(math.floor(fs / want_fs))) if want_fs < fs else 1
    out_fs = fs / factor

    sub_s = float(spec.get("sub_s") or DEFAULT_SUB_S)
    win_s = float(spec.get("win_s") or DEFAULT_WIN_S)
    step_s = float(spec.get("step_s") or DEFAULT_STEP_S)
    win_s = max(win_s, sub_s)
    nper = max(16, int(round(sub_s * out_fs)))
    n_avg = max(1, int(round((win_s - sub_s) / step_s)) + 1)
    n_windows = max(0, int(math.floor(max(0.0, span - win_s) / step_s)) + 1)

    line_hz = spec.get("line_hz")
    line_hz = spectrum.LINE_HZ if line_hz is None else float(line_hz or 0.0)
    channels = list(spec.get("channels") or [])
    n_ch = len(channels) or 1

    return {
        "fs": fs, "fs_used": out_fs, "decimate": factor,
        "t0": t0, "t1": t1, "span_s": span,
        "f_lo": f_lo, "f_hi": f_hi,
        "sub_s": sub_s, "win_s": win_s, "step_s": step_s,
        "nperseg": nper,
        "resolution_hz": (out_fs / nper) if nper else 0.0,
        "n_avg": n_avg,
        "n_windows": n_windows,
        "n_channels": n_ch,
        "line_hz": line_hz,
        "line_half_bw": spectrum.LINE_HALF_BW,
        "bins": int(spec.get("bins") or DEFAULT_BINS),
        "hist_scale": spec.get("hist_scale") or DEFAULT_SCALE,
        "cmap": spec.get("cmap") or "jet",
        "scale": spec.get("scale") or "log10",
        "chunks": max(1, int(math.ceil(span / CHUNK_SECONDS))),
        "megasamples": max(1e-6, span * out_fs / 1e6),
        "fit": _fit_settings(spec),
    }


def estimate(session, spec):
    """What it will cost, before anybody waits for it."""
    plan = plan_for(session, spec)
    n_ch = plan["n_channels"]
    read = cfc.rate_for("spectrum read", cfc.volume_key(session.get("path"))) \
        * plan["span_s"] * n_ch
    fit = cfc.rate_for("panorama windows") * plan["n_windows"] * n_ch
    return {
        "ok": True,
        "plan": plan,
        "seconds": round(read + fit, 1),
        "read_s": round(read, 1),
        "fit_s": round(fit, 1),
        "notes": notes_for(plan),
    }


def notes_for(plan):
    """The honest sentences the form and the waiting screen both say."""
    out = []
    if plan["decimate"] > 1:
        out.append("decimating %s to %s Hz, which is what makes %g Hz "
                   "answerable" % ("{:,}".format(int(plan["fs"])),
                                   "{:,.0f}".format(plan["fs_used"]),
                                   plan["f_hi"]))
    out.append("%.3g s transform, so %.3g Hz bins"
               % (plan["sub_s"], plan["resolution_hz"]))
    out.append("each column averages %d sub-window%s over %.3g s"
               % (plan["n_avg"], "" if plan["n_avg"] == 1 else "s",
                  plan["win_s"]))
    out.append("%s window%s, one every %.3g s"
               % ("{:,}".format(plan["n_windows"]),
                  "" if plan["n_windows"] == 1 else "s", plan["step_s"]))
    if plan["line_hz"]:
        out.append("bridging %g Hz and its harmonics, %g Hz either side"
                   % (plan["line_hz"], plan["line_half_bw"]))
    return out


# ==========================================================================
# Caching, the same shape as spectrum.py's
# ==========================================================================
_CACHE = {}
_CACHE_ORDER = []
_CACHE_LOCK = threading.Lock()
CACHE_MAX = 8


def cache_key(spec):
    keep = {k: spec.get(k) for k in (
        "path", "channels", "t0", "t1", "f_lo", "f_hi", "sub_s", "win_s",
        "step_s", "line_hz", "bins", "hist_scale", "even_only", "invert",
        "peak_width_limits", "max_n_peaks", "min_peak_height",
        "aperiodic_mode") if spec.get(k) is not None}
    blob = json.dumps(keep, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def cache_get(key):
    with _CACHE_LOCK:
        return _CACHE.get(key)


def cache_put(key, value):
    with _CACHE_LOCK:
        if key not in _CACHE and len(_CACHE_ORDER) >= CACHE_MAX:
            _CACHE.pop(_CACHE_ORDER.pop(0), None)
        if key not in _CACHE:
            _CACHE_ORDER.append(key)
        _CACHE[key] = value


def cache_clear():
    with _CACHE_LOCK:
        _CACHE.clear()
        del _CACHE_ORDER[:]


# ==========================================================================
# The run
# ==========================================================================
def read_channel(session, ch, plan, job=None, on_preview=None,
                 read_base=0.0):
    """Pass one: read the channel and turn it into spectrogram columns.

    `read_base` is how far the read stage had got before this channel.
    Passed in rather than held on the module, because two runs can be in
    flight at once and module state would have each driving the other's bar.
    """
    factor, out_fs = plan["decimate"], plan["fs_used"]
    t0, t1 = plan["t0"], plan["t1"]
    head = {"index": ch.get("index"), "label": ch.get("label"),
            "number": ch.get("number"), "bad": bool(ch.get("bad"))}

    def on_read(done):
        if job:
            job.tick("spectrum read", int(read_base + done))

    preview_state = {"at": 0.0}

    def on_chunk(x, upto):
        if on_preview:
            on_preview(x, upto, plan, preview_state)

    x, gaps = read_gapped(session, ch, t0, t1, factor, out_fs, job,
                          on_read=on_read, on_chunk=on_chunk)
    head["gaps"] = gaps
    if not np.isfinite(x).any():
        head["error"] = ("nothing was recorded on this channel in that "
                         "stretch.")
        return head

    freqs, times, pxx, n_avg = spectrogram(
        x, out_fs, plan["sub_s"], plan["win_s"], plan["step_s"],
        plan["f_lo"], plan["f_hi"])
    if pxx.shape[1] < 1 or freqs.size < 4:
        head["error"] = ("that stretch is shorter than one %.3g s window."
                         % plan["win_s"])
        return head

    mask, line_at = spectrum.line_bins(freqs, plan["line_hz"], plan["f_hi"])
    pxx, line_power = _bridge_line(freqs, pxx, mask)

    # The whole-recording spectrum IS the average of the columns. No second
    # Welch: same segments, same window, same average.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        psd = np.nanmean(pxx, axis=1)

    head.update({
        "_freqs": freqs, "_times": times,
        # float32 between the passes. The columns are what has to be held
        # while the other channels are read, and at 0.5 Hz bins over a
        # thirty-five minute recording that is 6.7 MB a channel in float64 --
        # 430 MB across sixty-four of them. The fit converts back per
        # channel, one at a time.
        "_pxx": pxx.astype(np.float32),
        "_psd": psd, "_mask": mask, "_n_samples": int(np.isfinite(x).sum()),
        "line_at": line_at, "line_power": line_power,
    })
    return head


def fit_channel(got, plan, job=None, fit_base=0):
    """Pass two: the fits, the histogram and the picture, for one channel."""
    if "error" in got or "_pxx" not in got:
        return got
    freqs = got.pop("_freqs")
    times = got.pop("_times")
    pxx = np.asarray(got.pop("_pxx"), dtype=np.float64)
    psd = got.pop("_psd")
    mask = got.pop("_mask")
    n_samples = got.pop("_n_samples")

    dom = dominant(freqs, pxx, plan["f_lo"], plan["f_hi"], plan["fit"],
                   job=job, stage="panorama windows", done_base=fit_base)
    hist = histogram(dom, plan["f_lo"], plan["f_hi"],
                     plan["bins"], plan["hist_scale"])

    finite = np.isfinite(psd) & (psd > 0)
    fitted = None
    if finite.sum() > 8:
        fitted = specparam.fit(freqs[finite], psd[finite],
                               f_lo=max(plan["f_lo"], float(freqs[finite][0])),
                               f_hi=plan["f_hi"], bands=spectrum.FIT_BANDS)

    peak = np.asarray(dom["peak_hz"], dtype=float)
    modal = None
    if hist["n_used"]:
        centres = np.sqrt(np.asarray(hist["edges"][:-1])
                          * np.asarray(hist["edges"][1:]))
        modal = float(centres[int(np.argmax(hist["peak"]))])

    got.update({
        "spectrogram": render(freqs, times, pxx, plan["cmap"], plan["scale"]),
        "freqs": [float(v) for v in freqs],
        "psd": [float(v) if np.isfinite(v) else None for v in psd],
        "line_bins": [int(v) for v in np.flatnonzero(mask)],
        "fit": fitted,
        "hist": hist,
        "windows": {
            "t_s": [round(float(v), 4) for v in times],
            "peak_hz": _nlist(dom["peak_hz"]),
            "flat_hz": _nlist(dom["flat_hz"]),
            "exponent": _nlist(dom["exponent"]),
            "r2": _nlist(dom["r2"]),
        },
        "modal_hz": modal,
        "median_hz": (float(np.nanmedian(peak))
                      if np.isfinite(peak).any() else None),
        "n_samples": n_samples,
    })
    return got


def _nlist(a):
    return [None if not np.isfinite(v) else round(float(v), 5) for v in a]


def run(session, spec, job=None, on_preview=None):
    """The whole panorama, for every channel asked for.

    Read everything, then fit everything, rather than read-and-fit a channel
    at a time. `Job.begin` closes whatever stage is running and marks it
    complete, so opening the fit stage once per channel closed the read stage
    early and then reset the fit's own count -- the bars went backwards on
    the second channel -- and it taught the rate learner the whole run's
    units once per channel. One `begin` per stage is the constraint, and two
    passes is what satisfies it.
    """
    if not HAVE_SCIPY:
        raise RuntimeError(
            "A spectrogram needs scipy, which is not installed here.")
    if not HAVE_FOOOF:
        raise RuntimeError(
            "Panorama's per-window fits need the `fooof` package, which is "
            "not installed here. `pip install -r requirements.txt` in the "
            "BARRY GUI folder puts it in.")

    plan = plan_for(session, spec)
    channels = list(spec.get("channels") or [])
    if not channels:
        raise ValueError("No channels chosen.")

    by_index = {c["index"]: c for c in (session.get("channels") or [])}
    wanted = [by_index[i] for i in channels if i in by_index]

    # ---- pass one: read
    if job:
        job.begin("spectrum read",
                  of=int(plan["span_s"] * len(wanted)), unit="seconds")
    rows, read_base = [], 0.0
    for ch in wanted:
        if job:
            job.check()
        try:
            rows.append(read_channel(session, ch, plan, job, on_preview,
                                     read_base))
        except cfc.Canceled:
            raise
        except Exception as exc:                         # noqa: BLE001
            rows.append({"index": ch.get("index"), "label": ch.get("label"),
                         "number": ch.get("number"),
                         "bad": bool(ch.get("bad")),
                         "error": str(exc)[:300]})
        read_base += plan["span_s"]
        if job:
            job.tick("spectrum read", int(read_base))

    # ---- pass two: fit
    if job:
        job.begin("panorama windows",
                  of=int(plan["n_windows"] * len(wanted)), unit="windows")
    fit_base = 0
    for i, got in enumerate(rows):
        if job:
            job.check()
        try:
            rows[i] = fit_channel(got, plan, job, fit_base)
        except cfc.Canceled:
            raise
        except Exception as exc:                         # noqa: BLE001
            rows[i] = {"index": got.get("index"), "label": got.get("label"),
                       "number": got.get("number"), "bad": got.get("bad"),
                       "gaps": got.get("gaps"), "error": str(exc)[:300]}
        fit_base += plan["n_windows"]
        if job:
            job.tick("panorama windows", int(fit_base))

    ok = [r for r in rows if "hist" in r]
    return {
        "ok": True,
        "plan": plan,
        "channels": rows,
        "n_ok": len(ok),
        "units": "uV^2/Hz",
        "fit_engine": fit_engine(spec),
        "notes": notes_for(plan),
        "colormaps": [dict(c) for c in analysis.COLORMAPS],
    }


# ==========================================================================
# Step 3 -- the figure and the tables behind it
# ==========================================================================
def _png_bytes(data_uri):
    import base64
    return base64.b64decode(str(data_uri).split(",", 1)[1])


def figure(result, index=0, counting="peak", title=None):
    """The three steps as one publication-quality figure. Returns PNG bytes.

    The spectrogram is drawn from the PNG the run already produced rather
    than recomputed: it is the same picture the screen showed, colour limits
    and all, and a figure that quietly differs from what somebody looked at
    before pressing Save is worse than no figure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.image import imread

    from . import export

    rows = result.get("channels") or []
    ch = rows[min(index, len(rows) - 1)] if rows else {}
    if "hist" not in ch:
        raise ValueError("That channel produced nothing to draw.")
    plan = result.get("plan") or {}
    sg = ch.get("spectrogram") or {}

    fig = plt.figure(figsize=(12.5, 8.6), facecolor="white")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1.0],
                          hspace=0.34, wspace=0.22,
                          left=0.075, right=0.975, top=0.90, bottom=0.085)

    # ---- the spectrogram, across the top
    ax = fig.add_subplot(gs[0, :])
    img = imread(io.BytesIO(_png_bytes(sg["png"])), format="png")
    f_lo, f_hi = float(sg["f_lo"]), float(sg["f_hi"])
    ax.imshow(img, aspect="auto", interpolation="nearest",
              extent=[sg["t0"] / 60.0, sg["t1"] / 60.0,
                      np.log10(f_lo), np.log10(f_hi)], origin="upper")
    ticks = [t for t in (2, 4, 8, 12, 20, 30, 60, 120, 200)
             if f_lo <= t <= f_hi]
    ax.set_yticks([np.log10(t) for t in ticks])
    ax.set_yticklabels([str(t) for t in ticks])
    ax.set_ylabel("frequency (Hz)", color=export.INK)
    ax.set_xlabel("time (min)", color=export.INK)
    gaps = ch.get("gaps") or {}
    head = title or "Panorama"
    sub = "%s  ·  %.3g-%.3g Hz  ·  %.3g s windows every %.3g s" % (
        ch.get("label") or "", plan.get("f_lo"), plan.get("f_hi"),
        plan.get("win_s"), plan.get("step_s"))
    if gaps.get("n"):
        sub += "  ·  %d gap(s), %.3f s never written, drawn blank" % (
            gaps["n"], gaps["seconds"])
    ax.set_title(head, fontsize=13, color=export.UVM_GREEN, loc="left",
                 pad=22, weight="bold")
    ax.annotate(sub, xy=(0, 1), xycoords="axes fraction",
                xytext=(0, 8), textcoords="offset points",
                fontsize=9, color=export.MUTED)

    # ---- the power spectrum, bottom left
    axp = fig.add_subplot(gs[1, 0])
    f = np.asarray(ch.get("freqs") or [], dtype=float)
    p = np.array([np.nan if v is None else v for v in (ch.get("psd") or [])],
                 dtype=float)
    ok = np.isfinite(p) & (p > 0) & (f > 0)
    axp.loglog(f[ok], p[ok], color=export.UVM_GREEN, lw=1.4,
               label="whole recording")
    fit = ch.get("fit") or {}
    if fit.get("offset") is not None and fit.get("exponent") is not None:
        ap = np.power(10.0, aperiodic_curve(f[ok], fit))
        axp.loglog(f[ok], ap, color=export.MUTED, lw=1.1, ls="--",
                   label="aperiodic fit (exp %.2f)" % fit["exponent"])
    axp.set_xlabel("frequency (Hz)", color=export.INK)
    axp.set_ylabel("power (uV^2/Hz)", color=export.INK)
    axp.grid(True, which="both", color=export.GRID, lw=0.6)
    axp.legend(frameon=False, fontsize=8)
    axp.set_title("2 · Power spectrum   (%.3g Hz steps, %s segments)"
                  % (plan.get("resolution_hz") or 0,
                     "{:,}".format(ch["hist"]["n_windows"])),
                  fontsize=10, color=export.UVM_GREEN, loc="left")

    # ---- the histogram, bottom right
    axh = fig.add_subplot(gs[1, 1])
    h = ch["hist"]
    edges = np.asarray(h["edges"], dtype=float)
    counts = np.asarray(h["flat" if counting == "flat" else "peak"],
                        dtype=float)
    axh.bar(edges[:-1], counts, width=np.diff(edges), align="edge",
            color=export.UVM_GOLD, edgecolor="none")
    if h["scale"] == "log":
        axh.set_xscale("log")
    for name, lo, hi in [("delta", 1, 4), ("theta", 4, 12), ("beta", 13, 30),
                         ("low gamma", 30, 60), ("high gamma", 60, 120)]:
        if hi < edges[0] or lo > edges[-1]:
            continue
        axh.axvline(max(lo, edges[0]), color=export.GRID, lw=0.8)
    axh.set_xlabel("dominant frequency (Hz)", color=export.INK)
    axh.set_ylabel("windows (occurrences)", color=export.INK)
    axh.grid(True, axis="y", color=export.GRID, lw=0.6)
    axh.set_title("1 · Dominant frequency   (%s, %d no peak of %d)"
                  % ("tallest fitted peak" if counting != "flat"
                     else "flattened argmax",
                     h["n_nopeak"], h["n_windows"]),
                  fontsize=10, color=export.UVM_GREEN, loc="left")

    eng = result.get("fit_engine") or {}
    fig.text(0.075, 0.018,
             "fitted with %s %s  ·  peak width %s, max %s peaks, min height "
             "%s, %s aperiodic" % (
                 eng.get("name"), eng.get("version"),
                 eng.get("peak_width_limits"), eng.get("max_n_peaks"),
                 eng.get("min_peak_height"), eng.get("aperiodic_mode")),
             fontsize=7.5, color=export.MUTED)

    for a in (ax, axp, axh):
        a.tick_params(colors=export.MUTED, labelsize=8)
        for s in a.spines.values():
            s.set_color(export.GRID)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def aperiodic_curve(freqs, fit):
    """log10 power of the fitted aperiodic component, knee or not."""
    f = np.asarray(freqs, dtype=float)
    knee = float(fit.get("knee") or 0.0)
    return float(fit["offset"]) - np.log10(
        knee + np.power(f, float(fit["exponent"])))


def tables(result, index=0):
    """The numbers behind the picture, as rows ready for `extras.to_csv`."""
    rows = result.get("channels") or []
    ch = rows[min(index, len(rows) - 1)] if rows else {}
    freqs = ch.get("freqs") or []
    psd = ch.get("psd") or []
    psd_rows = [{"frequency_hz": round(float(f), 6),
                 "power_uv2_per_hz": psd[i]}
                for i, f in enumerate(freqs)]

    h = ch.get("hist") or {}
    edges = h.get("edges") or []
    hist_rows = [{"bin_lo_hz": round(edges[i], 6),
                  "bin_hi_hz": round(edges[i + 1], 6),
                  "count_tallest_peak": h["peak"][i],
                  "count_flattened_argmax": h["flat"][i]}
                 for i in range(max(0, len(edges) - 1))]

    w = ch.get("windows") or {}
    t = w.get("t_s") or []
    win_rows = [{"t_s": t[i],
                 "dominant_peak_hz": w["peak_hz"][i],
                 "dominant_flat_hz": w["flat_hz"][i],
                 "aperiodic_exponent": w["exponent"][i],
                 "r_squared": w["r2"][i]}
                for i in range(len(t))]
    return psd_rows, hist_rows, win_rows


# ==========================================================================
# The waiting screen's picture
# ==========================================================================
def preview_png(x, upto, plan, state, cmap=None):
    """A coarse spectrogram of what has been read so far.

    Cheap enough to redo every chunk and small enough to poll for: the point
    is that a run which is obviously wrong can be cancelled in the first ten
    seconds rather than at the end of four minutes.
    """
    if not HAVE_SCIPY:
        return None
    out_fs = plan["fs_used"]
    n = int(round((upto - plan["t0"]) * out_fs))
    n = max(0, min(n, x.size))
    if n < int(plan["win_s"] * out_fs) * 2:
        return None
    sub = x[:n]
    # A preview is a picture, not a measurement: a shorter transform and a
    # coarser hop, sized so the whole recording would land in PREVIEW_COLS.
    step = max(plan["step_s"], (plan["span_s"] / PREVIEW_COLS) or 1.0)
    try:
        freqs, times, pxx, _ = spectrogram(
            sub, out_fs, plan["sub_s"], plan["win_s"], step,
            plan["f_lo"], plan["f_hi"])
    except Exception:                                    # noqa: BLE001
        return None
    if pxx.shape[1] < 2:
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        m = np.log10(pxx)
    m[~np.isfinite(m)] = np.nan
    rows, m = _log_rows(freqs, m, PREVIEW_ROWS)
    # Hold the colour limits from the first preview, so the picture does not
    # re-scale under the reader every time another chunk lands.
    if not state.get("clim"):
        state["clim"] = _clim(m)
    # Pad to the full width, so the image grows left to right in place
    # instead of being restretched every time.
    want = PREVIEW_COLS
    if m.shape[1] < want:
        pad = np.full((m.shape[0], want - m.shape[1]), np.nan)
        m = np.concatenate([m, pad], axis=1)
    elif m.shape[1] > want:
        m = analysis._decimate_cols(m, max_cols=want)
    return analysis._encode_image(m[::-1, :], cmap or plan.get("cmap", "jet"),
                                  state["clim"])
