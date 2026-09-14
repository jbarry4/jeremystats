"""
spectrum.py -- how much power, at which frequency, over a whole recording.

Theta is always there. What varies is how much of it, so the useful picture is
power against frequency: a curve per channel, read at a glance for where the
rhythm sits and how strong it is relative to everything else.

WHY THIS IS NOT JUST scipy.signal.welch
---------------------------------------
A 35-minute recording at 30 kHz is 63.7 million samples in one channel. Sixty
four of them is four billion samples, which is sixteen gigabytes in float32 --
so the obvious implementation, read the recording and hand it to `welch`, does
not run at all on a real session.

Two things make it tractable, and both are the standard thing rather than a
trick:

**Decimate first.** The question is about 1-200 Hz. Everything above the band
being asked for is noise for this purpose, and keeping 30 kHz to answer a
200 Hz question costs a factor of seventy-five. `scipy.signal.decimate`
low-passes before it drops samples, so nothing above the new Nyquist folds
back -- and the decimation is reported rather than assumed, because a spectrum
that quietly stops being valid above some frequency nobody mentioned is worse
than no spectrum.

**Stream it.** Welch's method IS an average of periodograms over segments, so
it can be accumulated a chunk at a time and never needs the whole recording in
memory. Reading in chunks with a small overlap, decimating each, and averaging
the periodograms gives the same estimate as one pass over the lot, in bounded
memory, with progress somebody can watch.

The overlap is thrown away on both sides of every chunk but the ends. A
zero-phase decimation filter rings for a filter length at each edge, and those
samples would otherwise be averaged in as if they were signal.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading

import numpy as np

from . import cfc, csc

try:
    from scipy import signal as _sig
    HAVE_SCIPY = True
except Exception:                                        # noqa: BLE001
    _sig = None
    HAVE_SCIPY = False


# How much of the recording to read at a time. Long enough that the
# decimation edges are a rounding error against it, short enough that a
# 64-channel run reports progress often and never holds much.
CHUNK_SECONDS = 120.0

# Thrown away at each chunk edge. A zero-phase decimation rings for a filter
# length either side, and averaging that in would be averaging in the filter.
EDGE_SECONDS = 0.5

# The band this is asked about, and the rate that answers it. Everything above
# `fmax` is noise for this question; `decimate_to` keeps a comfortable margin
# over Nyquist so the anti-alias filter's shoulder is outside the band shown.
DEFAULT_FMAX = 200.0
NYQUIST_MARGIN = 2.5

# Bands worth a number beside the curve. Reading a peak off a log plot is
# guesswork; these are the answer to "how much theta", which is the question.
BANDS = [
    ("delta", 1.0, 4.0),
    ("theta", 4.0, 12.0),
    ("alpha", 8.0, 13.0),
    ("beta", 13.0, 30.0),
    ("low gamma", 30.0, 60.0),
    ("high gamma", 60.0, 120.0),
]


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
# Keyed on what changes the answer and nothing else. A few thousand floats a
# channel, held in memory, dropped oldest-first -- cheap to recompute, and
# not worth outliving the process.
_CACHE = {}
_CACHE_ORDER = []
CACHE_MAX = 16
_CACHE_LOCK = threading.Lock()


def cache_key(spec):
    body = {
        "path": spec.get("path"),
        "channels": sorted(int(c) for c in (spec.get("channels") or [])),
        "t0": round(float(spec.get("t0") or 0.0), 3),
        "t1": round(float(spec.get("t1") or 0.0), 3),
        "fmax": round(float(spec.get("fmax") or DEFAULT_FMAX), 3),
        "segment_s": round(float(spec.get("segment_s") or 8.0), 3),
        "even_only": bool(spec.get("even_only")),
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


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


def target_rate(fmax):
    """The rate to decimate to for a question about `fmax`."""
    return max(2.0 * float(fmax), NYQUIST_MARGIN * float(fmax))


def plan_for(session, spec):
    """What a run would do, without doing any of it.

    Returns the shape of the work -- how much to read, how far to decimate,
    how many segments each channel averages over -- so the window can say
    what it is about to cost before anybody waits for it.
    """
    fs = float(session.get("fs") or 0) or 30000.0
    t0 = max(0.0, float(spec.get("t0") or 0.0))
    t1 = float(spec.get("t1") or session.get("duration_s") or 0.0)
    if t1 <= t0:
        t1 = float(session.get("duration_s") or 0.0)
    span = max(0.0, t1 - t0)

    fmax = float(spec.get("fmax") or DEFAULT_FMAX)
    want_fs = target_rate(fmax)
    factor = max(1, int(math.floor(fs / want_fs))) if want_fs < fs else 1
    out_fs = fs / factor

    # The segment length, in the decimated rate. Long segments buy frequency
    # resolution and cost the number of them there are to average, which is
    # what makes the estimate smooth: 8 s at 500 Hz is 0.125 Hz bins, which
    # resolves theta into eight bins rather than one.
    seconds = float(spec.get("segment_s") or 8.0)
    nper = int(2 ** round(math.log2(max(64.0, seconds * out_fs))))
    nper = max(64, min(nper, 1 << 20))

    n_ch = len(spec.get("channels") or []) or 1
    chunks = max(1, int(math.ceil(span / CHUNK_SECONDS)))
    return {
        "fs": fs,
        "t0": t0, "t1": t1, "span_s": span,
        "fmax": fmax,
        "decimate": factor,
        "fs_used": out_fs,
        "nperseg": nper,
        "resolution_hz": out_fs / nper if nper else 0.0,
        "n_channels": n_ch,
        "chunks": chunks,
        "reads": chunks * n_ch,
        # What a periodogram is averaged over, which is what makes the curve
        # smooth: too few and it is noise, and the number is worth saying.
        "segments_per_channel": int(max(1, span * out_fs / max(1, nper // 2))),
        "samples_read": int(span * fs * n_ch),
        "megasamples": span * fs * n_ch / 1e6,
    }


def estimate(session, spec):
    """How long a run would take, from what this machine has actually done."""
    plan = plan_for(session, spec)
    # Straight multiplication, no per-megasample factor: these stages are in
    # `cfc._FLAT` because their units are seconds of recording and channels,
    # which already say how many samples there are. Twice the window is twice
    # the wait, which is what somebody watching the bar expects.
    seconds = (cfc.rate_for("spectrum read")
               * plan["span_s"] * plan["n_channels"]
               + cfc.rate_for("spectrum") * plan["n_channels"])
    plan["seconds"] = round(max(0.2, seconds), 1)
    return plan


def _read_decimated(session, ch, t0, t1, factor, job=None, on_read=None):
    """One channel over one stretch, at the reduced rate.

    Read in chunks with an overlap that is thrown away, because a zero-phase
    decimation rings at each edge and averaging that in would be averaging in
    the filter rather than the signal.
    """
    out, rates = [], []
    at = t0
    while at < t1:
        if job:
            job.check()
        lo = max(t0, at - EDGE_SECONDS)
        hi = min(t1, at + CHUNK_SECONDS + EDGE_SECONDS)
        seg, got_t0, fs = csc._read_channel_window(session, ch, lo, hi)
        if seg.size:
            if factor > 1 and HAVE_SCIPY:
                seg = _sig.decimate(seg.astype(np.float64), factor,
                                    ftype="fir", zero_phase=True)
                rate = fs / factor
            else:
                rate = fs
            rates.append(rate)

            # Cut from where the read ACTUALLY starts.
            #
            # `_read_channel_window` snaps back to a record boundary, so the
            # samples returned begin up to one record -- 17 ms at 30 kHz --
            # before the time asked for. Trimming by the requested time cut
            # every chunk after the first in the wrong place and left a step
            # at each join; measured against a single-pass welch, 0.76%
            # median and 13% at worst where the two must agree exactly.
            want_lo = at
            want_hi = min(t1, at + CHUNK_SECONDS)
            i0 = int(round((want_lo - got_t0) * rate))
            i1 = int(round((want_hi - got_t0) * rate))
            i0 = max(0, min(i0, seg.size))
            i1 = max(i0, min(i1, seg.size))
            seg = seg[i0:i1]
            if seg.size:
                out.append(np.asarray(seg, dtype=np.float64))
        at += CHUNK_SECONDS
        if on_read:
            on_read(min(t1, at) - t0)
    if not out:
        return np.empty(0), 0.0
    return np.concatenate(out), (rates[0] if rates else 0.0)


def run(session, spec, job=None):
    """The power spectrum of each chosen channel over the chosen window."""
    if not HAVE_SCIPY:
        raise RuntimeError(
            "A power spectrum needs scipy, which is not installed here.")

    plan = plan_for(session, spec)
    channels = list(spec.get("channels") or [])
    if not channels:
        raise ValueError("No channels chosen.")

    info = session.get("channels") or []
    by_index = {c["index"]: c for c in info}
    factor = plan["decimate"]
    nper = plan["nperseg"]
    t0, t1 = plan["t0"], plan["t1"]

    if job:
        job.begin("spectrum read",
                  of=int(plan["span_s"] * len(channels)), unit="seconds")

    read_done = [0.0]
    rows, freqs = [], None
    for n, index in enumerate(channels):
        ch = by_index.get(index)
        if not ch:
            continue
        if job:
            job.check()

        # Within the channel as well as between them: a whole recording is
        # eighteen chunks, and a bar that only moves once a channel is a bar
        # that does not move.
        def on_read(done, base=read_done[0]):
            if job:
                job.tick("spectrum read", int(base + done))

        data, rate = _read_decimated(session, ch, t0, t1, factor, job, on_read)
        read_done[0] += plan["span_s"]
        if job:
            job.tick("spectrum read", int(read_done[0]))
        if data.size < nper:
            # Too short to say anything at the resolution asked for. Said,
            # not padded: a spectrum computed from less data than its own
            # window is a picture of the window.
            rows.append({
                "index": index, "label": ch.get("label"),
                "number": ch.get("number"), "bad": bool(ch.get("bad")),
                "error": "only %d sample(s) after decimation; the window is "
                         "shorter than one %d-sample segment"
                         % (int(data.size), nper),
            })
            continue

        # NOT job.begin("spectrum") here. `begin` closes the running stage,
        # so doing it per channel marked the read finished on the first one
        # and the remaining fifteen channels of reading moved no bar at all.
        f, pxx = _sig.welch(data, fs=rate, nperseg=nper,
                            noverlap=nper // 2, detrend="constant",
                            scaling="density")
        keep = (f > 0) & (f <= plan["fmax"])
        f, pxx = f[keep], pxx[keep]
        if freqs is None:
            freqs = f

        peak = int(np.argmax(pxx)) if pxx.size else 0
        total = float(np.trapezoid(pxx, f)) if pxx.size > 1 else 0.0
        bands = {}
        for name, lo, hi in BANDS:
            m = (f >= lo) & (f < hi)
            power = float(np.trapezoid(pxx[m], f[m])) if m.sum() > 1 else 0.0
            sub = f[m]
            bands[name] = {
                "power": power,
                "share": (power / total) if total > 0 else 0.0,
                "peak_hz": float(sub[int(np.argmax(pxx[m]))]) if m.sum() else None,
            }
        rows.append({
            "index": index, "label": ch.get("label"),
            "number": ch.get("number"), "bad": bool(ch.get("bad")),
            "psd": [float(v) for v in pxx],
            "peak_hz": float(f[peak]) if f.size else None,
            "peak_power": float(pxx[peak]) if pxx.size else None,
            "total_power": total,
            "bands": bands,
            "n_samples": int(data.size),
        })

    if job:
        # Opened once, after the loop, with its count already reached: the
        # transforms happened interleaved with the reads and cannot be shown
        # as a phase of their own without holding every channel in memory.
        job.begin("spectrum", of=len(channels), unit="channels")
        job.tick("spectrum", len(channels))
        job.begin("draw", of=1, unit="images")
        job.tick("draw", 1)

    ok = [r for r in rows if "psd" in r]
    return {
        "ok": True,
        "freqs": [float(v) for v in (freqs if freqs is not None else [])],
        "channels": rows,
        "n_ok": len(ok),
        "units": "uV^2/Hz",
        "plan": plan,
        # Everything a reader needs to know the picture is honest, in the
        # answer rather than in a docstring.
        "sampling": _sampling_note(plan),
        "bands": [{"name": n, "lo": lo, "hi": hi} for n, lo, hi in BANDS],
    }


def _sampling_note(plan):
    """What was done to the data before the transform, in words."""
    steps = []
    if plan["decimate"] > 1:
        steps.append({
            "what": "decimated",
            "why": "the question is about %g Hz and the recording is %g Hz; "
                   "everything above the band asked for is noise for this "
                   "purpose" % (plan["fmax"], plan["fs"]),
            "from": plan["fs"], "to": plan["fs_used"],
            "factor": plan["decimate"],
            "antialiased": True,
            # Nothing in the band shown was lost. Above it, everything was.
            "lossy": True,
            "reversible": True,
            "note": "Low-passed before dropping samples, so nothing above "
                    "%g Hz folds back into the band. The spectrum is only "
                    "valid up to %g Hz."
                    % (plan["fs_used"] / 2.0, plan["fmax"]),
        })
    steps.append({
        "what": "averaged",
        "why": "Welch: the recording is cut into overlapping segments and "
               "their periodograms averaged, which is what makes the curve "
               "readable rather than noise",
        "segments": plan["segments_per_channel"],
        "seconds_each": round(plan["nperseg"] / max(1.0, plan["fs_used"]), 3),
        "resolution_hz": round(plan["resolution_hz"], 4),
        "lossy": False,
    })
    return steps
