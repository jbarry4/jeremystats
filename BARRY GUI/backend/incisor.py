"""
incisor.py -- dentate spike detection, on the recording's own clock.

Dentate means "toothed", and an incisor is the sharp one.

WHAT THIS IS
------------
A hand port of Toothy's `ephys.get_ds_peaks()` -- about fifty-seven lines of
`scipy.signal` -- with each step citing where it came from. Toothy is a
PyQt application and this is a Flask backend, so nothing is imported from it;
what is shared is the arithmetic, and the arithmetic is written down here so
the two can be compared line by line.

    Toothy                                      here
    ------                                      ----
    data_processing.py:499  resample to 1 kHz   _segment_traces
    pyfx.py:145             butter(3) bandpass  _filtered
    ephys.py:1010-1022      max(4.5 sd, 0.3mV)  threshold_for
    ephys.py:1024           find_peaks          _detect
    ephys.py:1029-1035      peak_widths         _detect
    ephys.py:916            estimate_hil_chan   pick_hilus
    ephys.py:892 / :902     theta / ripple      pick_theta / pick_ripple

WHY NOT JUST RUN TOOTHY
-----------------------
Toothy builds its time axis as `np.linspace(0, N/lfp_fs, N)`
(`raw_data_pipeline.py:200`) -- an index over a nominal rate, with no
reference to any `.ncs` record timestamp. Every acquisition gap therefore
shifts all later dentate spikes earlier by the cumulative gap. That is the
defect `continuity.py` exists to repair after the fact, in 82 of 246
recordings checked here.

This reads the `.ncs` files through Jarvis's own readers and stamps each peak
through `continuity.sample_to_true`, which is built from the file's own
record timestamps and its measured sample rate. A set produced here never
needs the correction, because it never has the error.

TWO THINGS THAT WOULD BE SILENTLY WRONG
---------------------------------------
**Polarity.** `nlx.py:157` inverts by lab convention and `invert=True` is the
default everywhere in Jarvis; Toothy applies no inversion at all. Dentate
spike detection is `find_peaks` on the *signed* trace -- positive deflections
only -- so the two conventions find opposite events, and both look entirely
plausible. `invert` is therefore explicit in the spec, in the cache key and
in the result, never inherited.

**Units.** Toothy divides the raw signal by 1000 and works in millivolts;
`csc.open_session` returns microvolts. Toothy's 0.3 mV floor is 300 uV here.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading

import numpy as np

from . import cfc, continuity, csc, nlx

try:
    from scipy import signal as _sig
    HAVE_SCIPY = True
except Exception:                                        # noqa: BLE001
    _sig = None
    HAVE_SCIPY = False


# --------------------------------------------------------------------------
# Toothy's numbers
# --------------------------------------------------------------------------
# Every default here is a literal from `qparam.py:29-68`, converted where the
# units differ. Changing one changes what counts as a dentate spike, so each
# says what it means rather than only what it is.
LFP_FS = 1000.0            # qparam.py:30  lfp_fs
DS_BAND = (5.0, 100.0)     # qparam.py:35  ds_freq
DS_ORDER = 3               # pyfx.py:145   butter_bandpass(..., order=3)
DS_HEIGHT_SD = 4.5         # qparam.py:37  ds_height_thr, in SD of the channel
DS_ABS_THR_UV = 300.0      # qparam.py:38  ds_abs_thr = 0.3 mV
DS_DIST_MS = 100.0         # qparam.py:39  ds_dist_thr
DS_PROM_UV = 0.0           # qparam.py:40  ds_prom_thr
DS_WLEN_MS = 125.0         # qparam.py:41  ds_wlen

# For the channel estimates, which need two more bands.
THETA_BAND = (6.0, 10.0)   # qparam.py:32  theta
SWR_BAND = (120.0, 180.0)  # qparam.py:36  swr_freq

# Reading. The recording is read at full rate and decimated as it arrives;
# only the decimated trace is kept, and only for one channel at a time.
CHUNK_SECONDS = 120.0
# Thrown away at each chunk edge before the chunks are joined. Measured
# against a single-pass filter on this band: 0.125 s of overlap leaves 0.258
# SD of error, 0.25 s leaves 0.041, 0.5 s leaves 0.0015, 1.0 s leaves 2.4e-7.
# At 1 kHz an edge is a thousand samples and costs nothing, so take the one
# that is exact to float precision rather than the one that is merely enough.
EDGE_SECONDS = 1.0

# A run this short cannot be filtered or thresholded meaningfully -- half a
# second is four cycles of the low edge of the band.
MIN_SEGMENT_S = 0.5

# How many amplitudes per channel travel with the answer, for the strip plot
# that Toothy draws off every event (`ephys.py:1177`).
#
# Every one of them would be right and is not affordable: sixty-four channels
# of two thousand events is the payload that arrives as a 200 with a body
# that will not parse, which is the same failure `_incisor_public` exists to
# avoid. Four hundred dots in a column forty pixels wide are already drawn on
# top of one another -- the sample is taken at an even STRIDE so it spans the
# recording rather than its first minutes, and the count panel is drawn from
# `n`, never from this.
AMP_SAMPLE_MAX = 400


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
_CACHE = {}
_CACHE_ORDER = []
CACHE_MAX = 8
_CACHE_LOCK = threading.Lock()


def cache_key(spec, report=None):
    """Everything that changes the answer, and nothing that does not.

    `breaks_sha` is in here rather than `gap_map_sha`: the times this
    produces come from the breakpoint map, so a recording whose short records
    have been re-read must not serve a cached answer built from the old one.
    """
    body = {
        "path": spec.get("path"),
        "channels": sorted(int(c) for c in (spec.get("channels") or [])),
        "invert": bool(spec.get("invert", True)),
        "even_only": bool(spec.get("even_only")),
        "height_sd": round(float(spec.get("height_sd", DS_HEIGHT_SD)), 6),
        "abs_uv": round(float(spec.get("abs_uv", DS_ABS_THR_UV)), 6),
        "dist_ms": round(float(spec.get("dist_ms", DS_DIST_MS)), 6),
        "prom_uv": round(float(spec.get("prom_uv", DS_PROM_UV)), 6),
        "wlen_ms": round(float(spec.get("wlen_ms", DS_WLEN_MS)), 6),
        "band": [round(float(v), 6) for v in
                 (spec.get("band") or DS_BAND)],
        "lfp_fs": round(float(spec.get("lfp_fs", LFP_FS)), 6),
        "estimator": spec.get("estimator") or "sd",
        "breaks_sha": (continuity.breaks_sha(report) if report else None),
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


def _finite(v, dp=None):
    """A float, or None where there is no number.

    `NaN` and `Infinity` are not JSON. Python writes them anyway and the
    browser then fails to parse a response it was told was fine, which is
    how this arrived: HTTP 200, unparseable body.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, dp) if dp is not None else f


def _clean(obj):
    """The same structure with every non-finite number replaced by null.

    Applied once, to the whole answer, rather than trusted to every site
    that builds a number: the guarantee wanted here is about the payload,
    and a guarantee that depends on remembering is not one.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------
def decimation_for(fs, lfp_fs):
    """How far to decimate, as an integer factor. 30 kHz -> 1 kHz is 30."""
    q = int(round(float(fs) / float(lfp_fs)))
    return max(1, q)


def plan_for(session, spec, report=None):
    """The shape of the work, without doing any of it."""
    fs = float(session.get("fs") or 0) or 30000.0
    lfp_fs = float(spec.get("lfp_fs") or LFP_FS)
    q = decimation_for(fs, lfp_fs)
    chans = list(spec.get("channels") or [])

    # The segments are the unit of work, and `true_duration_s` is the length
    # -- NOT `session["duration_s"]`, which is `n_rec * 512 / fs` and is
    # short by every gap the recording has.
    segs = [s for s in ((report or {}).get("segments") or [])
            if s.get("duration_s", 0) >= MIN_SEGMENT_S]
    span = sum(s["duration_s"] for s in segs) if segs else \
        float(session.get("duration_s") or 0.0)

    return {
        "fs": fs,
        "lfp_fs": fs / q,
        "decimate": q,
        "n_channels": len(chans) or 1,
        "n_segments": len(segs),
        "span_s": span,
        "chunks": sum(max(1, int(math.ceil(s["duration_s"] / CHUNK_SECONDS)))
                      for s in segs) or 1,
        "samples_read": int(span * fs * (len(chans) or 1)),
        "megasamples": span * fs * (len(chans) or 1) / 1e6,
        "volume": cfc.volume_key(session.get("path") or spec.get("path")),
        "network": bool((cfc.volume_key(session.get("path")
                                        or spec.get("path")) or "")
                        .startswith("\\\\")),
        "invert": bool(spec.get("invert", True)),
        "even_only": bool(session.get("even_only")),
        # What was NOT scanned, and how the recording was read.
        #
        # None of this changes when a dentate spike happened -- a time comes
        # from a sample index and the file's own record timestamps. What it
        # changes is which channels there were to find one on, and the
        # hilus, theta and ripple picks are argmaxes over exactly that set.
        # So it is reported with the plan rather than left to be inferred
        # from a channel count that came back smaller than the probe.
        "excluded": list(spec.get("excluded") or []),
        "n_excluded": len(spec.get("excluded") or []),
        "bad_channels": list(spec.get("bad_channels") or []),
        "probe": spec.get("probe") or "h3",
        "probe_name": spec.get("probe_name") or "H3 (single linear array)",
        "channel_scheme": session.get("channel_scheme") or None,
        "n_csc_files": session.get("n_csc_files"),
    }


def estimate(session, spec, report=None):
    """What a run would cost here, from what this machine has measured."""
    plan = plan_for(session, spec, report)
    where = cfc.volume_key(session.get("path") or spec.get("path"))
    seconds = (cfc.rate_for("ds read", where)
               * plan["span_s"] * plan["n_channels"]
               + cfc.rate_for("ds detect") * plan["n_channels"])
    plan["seconds"] = round(max(0.2, seconds), 1)
    return plan


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def _decimate(x, q):
    """Anti-aliased decimation by an integer factor.

    `scipy.signal.decimate` in two stages rather than one: scipy itself warns
    that a single stage above about thirteen is numerically poor, and 30 kHz
    to 1 kHz is thirty.

    Toothy uses `scipy.signal.resample` instead (`data_processing.py:499`),
    which is an FFT method. Both are anti-aliased and the difference between
    them in this band is far below the detection threshold, but it is a real
    difference and it is named here rather than left for somebody to find.
    """
    if q <= 1:
        return np.asarray(x, dtype=np.float64)
    out = np.asarray(x, dtype=np.float64)
    for step in _factor(q):
        out = _sig.decimate(out, step, ftype="iir", zero_phase=True)
    return out


def _factor(q):
    """Split a decimation factor into stages of at most 13."""
    out = []
    left = int(q)
    for p in (5, 4, 3, 2):
        while left % p == 0 and left > 13:
            out.append(p)
            left //= p
    if left > 1:
        out.append(left)
    return out or [1]


def _segment_traces(session, ch, report, spec, job=None, on_read=None):
    """One channel, decimated, one array per segment.

    Chunked at full rate so the reading stays bounded, but joined before any
    filtering: a whole recording at 1 kHz is 2.1 million samples -- eight
    megabytes -- so the reason `spectrum.py` streams does not survive the
    decimation. Filtering whole segments removes every chunk-boundary
    question from the detection filter, and is what Toothy does
    (`data_processing.py:576` filters whole traces).

    WALKED IN SAMPLES, NOT IN TIME. An earlier version chose each chunk by
    time, rounded to samples and trimmed to a multiple of the decimation
    factor, which dropped up to q-1 samples at every boundary -- 17 ms over a
    recording, putting every later event that much early. Measured against
    Toothy: a median offset of -9.71 ms. Here the position is carried in
    samples and each piece begins exactly where the last one ended, so the
    joined trace is the segment and nothing else.

    Returns [(segment_index, concat_sample_start, trace)], where the concat
    sample start is the index into the whole recording that
    `continuity.sample_to_true` takes.
    """
    fs = float(report.get("fs") or session.get("fs") or 30000.0)
    q = decimation_for(fs, float(spec.get("lfp_fs") or LFP_FS))
    chunk_n = max(q, int(round(CHUNK_SECONDS * fs)) // q * q)
    out = []
    at_concat = 0
    # Seconds of this channel already read, across ALL its segments. Without
    # it `on_read` restarts at zero on each segment and the bar walks
    # backwards eight times on a recording with eight of them, which reads as
    # a stall rather than as progress.
    done_s = [0.0]
    for seg in report.get("segments") or []:
        n_samples = int(seg["n_samples"])
        start_concat = at_concat
        at_concat += n_samples
        if seg["duration_s"] < MIN_SEGMENT_S:
            continue

        t0 = float(seg["true_t0_s"])
        pieces = []
        want_i = 0                      # segment-local sample index
        while want_i < n_samples:
            if job:
                job.check()
            take = min(chunk_n, n_samples - want_i)
            take -= take % q            # whole decimated samples only
            if take <= 0:
                break
            # Where this run of samples begins and ends, on the clock. The
            # breakpoint map, not a linear axis -- a short record inside the
            # segment moves this and nothing else would notice.
            t_lo = continuity.sample_to_true(report, start_concat + want_i)
            if t_lo is None:
                break
            t_hi = continuity.sample_to_true(
                report, min(start_concat + want_i + take,
                            start_concat + n_samples - 1))
            if t_hi is None or t_hi <= t_lo:
                t_hi = t_lo + take / fs

            raw, got_t0, got_fs = csc._read_channel_window(
                session, ch, max(t0, t_lo - EDGE_SECONDS), t_hi + EDGE_SECONDS)
            if raw.size:
                # Which samples these ARE, by index, not by time.
                #
                # `got_t0` is a real record timestamp, so it converts back to
                # a sample index exactly. Locating the wanted run by
                # subtracting times instead makes the samples taken depend on
                # the map -- measured: moving the anchors by 3 ms moved the
                # trace by ninety samples -- and the trace is the recording,
                # not a view of the map.
                i_first = continuity.true_to_sample(report, got_t0)
                if i_first is None:
                    break
                i0 = (start_concat + want_i) - i_first
                if i0 < 0 or i0 >= raw.size:
                    break
                # Decimated WITH a margin, then trimmed in the decimated
                # domain. Two things at once:
                #
                #   the anti-alias filter rings at the edges of whatever
                #   array it is handed, so decimating exactly the wanted run
                #   puts that ringing at every chunk boundary; and
                #
                #   the output length becomes exactly take/q, where trimming
                #   raw samples to a multiple of q and hoping left this one
                #   decimated sample short per boundary -- 14 of them on
                #   M8s2feb6, which is 14 ms by the end of the segment.
                #
                # The margin is whatever the read actually affords, rounded
                # to a whole number of decimated samples so the phase of the
                # grid does not move.
                take = min(take, raw.size - i0)
                take -= take % q
                if take <= 0:
                    break
                m_lo = min(int(EDGE_SECONDS * got_fs), i0) // q * q
                m_hi = min(int(EDGE_SECONDS * got_fs),
                           raw.size - i0 - take) // q * q
                dec = _decimate(raw[i0 - m_lo:i0 + take + m_hi], q)
                lo_n, hi_n = m_lo // q, m_hi // q
                dec = dec[lo_n:dec.size - hi_n] if hi_n else dec[lo_n:]
                want = take // q
                if dec.size != want:
                    # Never silently: a trace that is not the segment is the
                    # bug this whole loop exists to avoid.
                    dec = dec[:want]
                pieces.append(dec)
                want_i += take
            else:
                break
            if on_read:
                on_read(done_s[0] + min(n_samples, want_i) / fs)
        done_s[0] += n_samples / fs
        if pieces:
            out.append((int(seg["index"]), start_concat,
                        np.concatenate(pieces)))
    return out


# --------------------------------------------------------------------------
# Filtering and detection -- the ported part
# --------------------------------------------------------------------------
def _filtered(trace, lfp_fs, band, order=DS_ORDER):
    """Zero-phase Butterworth bandpass. `pyfx.py:145-158`.

    `sosfiltfilt` with `padtype='odd'`: scipy's default, pinned explicitly
    because Toothy pins it and a scipy change would otherwise be invisible.
    """
    lo, hi = float(band[0]), float(band[1])
    nyq = lfp_fs / 2.0
    hi = min(hi, nyq * 0.99)
    sos = _sig.butter(order, [lo / nyq, hi / nyq], btype="band", output="sos")
    return _sig.sosfiltfilt(sos, trace, padtype="odd")


def threshold_for(filtered, height_sd, abs_uv, estimator="sd"):
    """The voltage a peak has to reach. `ephys.py:1010-1022`.

        height = np.std(LFP) * ds_height_thr
        thres_mv = max(height, min_amp)

    Toothy uses `np.std` over the whole filtered trace -- not a median
    absolute deviation, no percentile, no robust statistic -- so that is what
    `estimator="sd"` does and it is the default.

    `estimator="mad"` is this codebase's own preference
    (`analysis.py:1328`, `sd = mad / 0.6745`) and is offered because it is
    better: one enormous artifact raises `np.std` enough to hide every real
    event after it. It is not the default, because a number out of here
    should be comparable with a number out of Toothy unless somebody has
    said otherwise.
    """
    x = np.asarray(filtered, dtype=np.float64)
    if estimator == "mad":
        med = float(np.median(x))
        sd = float(np.median(np.abs(x - med))) / 0.6745
    else:
        sd = float(np.std(x, dtype=np.float64))
    by_sd = sd * float(height_sd)
    floor = float(abs_uv)
    return {
        "sd_uv": sd,
        "thr_sd_uv": by_sd,
        "thr_abs_uv": floor,
        "thr_uv": max(by_sd, floor),
        # Which arm won. "The threshold is 300 uV" and "the threshold is
        # 300 uV because the floor bound it" are different facts, and only
        # the second one tells somebody what to change.
        "thr_source": "sd" if by_sd >= floor else "absolute",
        "estimator": estimator,
    }


def _detect(filtered, lfp_fs, thr_uv, spec):
    """`ephys.py:1024-1043`. Peaks, spacing, prominence, widths.

    No rectification and no envelope -- the ripple detector two functions up
    in Toothy takes `scipy.signal.hilbert` and this one deliberately does
    not, so only positive deflections are found. That is what makes polarity
    a correctness question rather than a preference.

    Nothing is rejected here on width or duration: the widths are measured
    and carried, and Toothy applies no criterion to them either.
    """
    dist = max(1, int(round(lfp_fs * float(spec.get("dist_ms", DS_DIST_MS))
                            / 1000.0)))
    wlen = max(1, int(round(lfp_fs * float(spec.get("wlen_ms", DS_WLEN_MS))
                            / 1000.0)))
    prom = float(spec.get("prom_uv", DS_PROM_UV)) or None

    ipks, props = _sig.find_peaks(filtered, height=thr_uv, distance=dist,
                                  prominence=prom if prom else 0.0)
    if not ipks.size:
        return {"idx": ipks, "amp": np.array([]), "prom": np.array([]),
                "half_width_ms": np.array([]), "width_height": np.array([]),
                "asym": np.array([]), "start": np.array([]),
                "stop": np.array([])}

    widths, w_height, lo, hi = _sig.peak_widths(filtered, peaks=ipks,
                                                rel_height=0.5, wlen=wlen)
    half_ms = (widths / lfp_fs) * 1000.0

    # Asymmetry, on the INT-CAST edges. `ephys.py:1033-1034`:
    #
    #     istarts, istops = [x.astype('int') for x in [starts, stops]]
    #     ds_asym = list(map(get_asym, ipks, istarts, istops))
    #
    # and `get_asym` (`ephys.py:776-780`) is
    #
    #     i0, i1 = ipk - istart, istop - ipk
    #     asym = (i1 - i0) / min(i0, i1) * 100
    #
    # The cast is not incidental. `peak_widths` returns fractional edges, and
    # computing this from them instead differs by up to 115 percentage points
    # on real data -- measured against Toothy's own code on 985 events of
    # CSC41. Fractional edges are arguably the better number, but parity is
    # the point of this module and asymmetry is a column the DS1/DS2 stage
    # will read, so it matches. No clamping either: where a peak sits on its
    # own edge Toothy divides by zero and gets an infinity, and so does this.
    istarts = lo.astype(int)
    istops = hi.astype(int)
    i0 = ipks - istarts
    i1 = istops - ipks
    with np.errstate(divide="ignore", invalid="ignore"):
        asym = (i1 - i0) / np.minimum(i0, i1) * 100.0
    return {
        "idx": ipks,
        "amp": filtered[ipks],
        "prom": props.get("prominences", np.zeros(ipks.size)),
        "half_width_ms": half_ms,
        "width_height": w_height,
        "asym": asym,
        # The int-cast edges, as Toothy reports them (`lfp_time[istarts]`).
        "start": istarts,
        "stop": istops,
    }


# --------------------------------------------------------------------------
# Channel estimates -- ephys.py:892, :902, :916
# --------------------------------------------------------------------------
def _normalize(v):
    """`pyfx.Normalize`: min-max onto 0..1, NaN-safe."""
    a = np.asarray(v, dtype=np.float64)
    lo = np.nanmin(a) if np.isfinite(a).any() else 0.0
    hi = np.nanmax(a) if np.isfinite(a).any() else 1.0
    if not np.isfinite(hi - lo) or (hi - lo) <= 0:
        return np.zeros_like(a)
    return (a - lo) / (hi - lo)


def pick_hilus(channels):
    """`ephys.py:916 estimate_hil_chan`.

        norm_amp, norm_n = map(pyfx.Normalize, arr)
        res = np.nanargmax(norm_amp * norm_n)

    Large events and many of them. The product is reported per channel as
    well as the winner, because an argmax over a product is not a thing to
    take on trust -- somebody who disagrees needs to see whether their
    channel lost on amplitude or on count.
    """
    # A channel that failed, or whose statistics are not numbers, is not a
    # candidate: an argmax against a missing comparison is not a choice.
    ok = [c for c in channels if not c.get("bad") and not c.get("error")
          and c.get("mean_amp") is not None and c.get("n") is not None]
    if not ok:
        return None
    amp = _normalize([c.get("mean_amp") or 0.0 for c in ok])
    n = _normalize([c.get("n") or 0 for c in ok])
    score = amp * n
    for c, a, m, s in zip(ok, amp, n, score):
        c["norm_amp"], c["norm_n"], c["score"] = float(a), float(m), float(s)
    i = int(np.nanargmax(score))
    return _winner(ok, i, "score", "largest and most frequent dentate spikes")


def pick_theta(channels):
    """`ephys.py:892 estimate_theta_chan`: argmax of theta-band SD."""
    ok = [c for c in channels if not c.get("bad")
          and not c.get("error") and c.get("std_theta") is not None]
    if not ok:
        return None
    v = np.array([c.get("std_theta") or 0.0 for c in ok])
    if not np.isfinite(v).any():
        return None
    return _winner(ok, int(np.nanargmax(v)), "std_theta",
                   "most power in 6-10 Hz")


def pick_ripple(channels):
    """`ephys.py:902 estimate_ripple_chan`.

        norm_swr[norm_theta >= np.nanpercentile(norm_theta, 60)] = np.nan
        res = np.nanargmax(norm_swr / norm_theta)

    Ripples where theta is weak: the top forty percent of theta channels are
    dropped before the ratio is taken.
    """
    ok = [c for c in channels if not c.get("bad")
          and not c.get("error") and c.get("std_theta") is not None]
    if not ok:
        return None
    theta = _normalize([c.get("std_theta") or 0.0 for c in ok])
    swr = _normalize([c.get("std_swr") or 0.0 for c in ok]).astype(float)
    if np.isfinite(theta).any():
        swr = swr.copy()
        swr[theta >= np.nanpercentile(theta, 60)] = np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = swr / np.where(theta > 0, theta, np.nan)
    if not np.isfinite(ratio).any():
        return None
    return _winner(ok, int(np.nanargmax(ratio)), "std_swr",
                   "most ripple power relative to theta")


def pick_most_spikes(channels):
    """The channel carrying the most dentate spikes, and nothing else.

    NOT the hilus pick. `pick_hilus` is Toothy's, and it is an argmax over a
    PRODUCT of normalised amplitude and normalised count (`ephys.py:916`),
    so a channel with many small events loses to one with fewer large ones.
    That is usually the right trade and sometimes it is not -- a hilus site
    next to a quiet one can come second on amplitude while carrying nearly
    every spike in the recording.

    Offered rather than applied. "The most events are here" and "the hilus
    is here" are different claims, and the second is the one being banked,
    so somebody presses a button and owns it.
    """
    ok = [c for c in channels if not c.get("bad") and not c.get("error")
          and c.get("n")]
    if not ok:
        return None
    v = [int(c.get("n") or 0) for c in ok]
    return _winner(ok, int(np.argmax(v)), "n", "most dentate spikes detected")


def _winner(rows, i, field, why):
    """The pick, with the runner-up and the margin between them.

    A margin is the difference between "this channel" and "this channel,
    barely" -- and the second is a thing somebody should look at rather than
    accept.
    """
    best = rows[i]
    vals = sorted(((r.get(field) or 0.0) for r in rows), reverse=True)
    second = vals[1] if len(vals) > 1 else 0.0
    top = vals[0] if vals else 0.0
    margin = ((top - second) / top) if (top and math.isfinite(top)) else 0.0
    return {
        "index": best["index"],
        "number": best["number"],
        "label": best["label"],
        "how": why,
        "value": _finite(top),
        "runner_up": _finite(second),
        # `if top` is true for a NaN, so the guard above tests finiteness as
        # well -- a margin of NaN is what turns a 200 into a parse error.
        "margin": _finite(margin) or 0.0,
    }


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------
def _channel_pass(session, ch, report, spec, job=None, on_read=None):
    """One channel: read it, filter it, threshold it, find its peaks.

    Returns (events, summary). The events carry true times; the summary
    carries everything the panel needs to explain the threshold and to rank
    this channel against the others.
    """
    fs = float(report.get("fs") or session.get("fs") or 30000.0)
    q = decimation_for(fs, float(spec.get("lfp_fs") or LFP_FS))
    lfp_fs = fs / q
    band = spec.get("band") or DS_BAND

    segs = _segment_traces(session, ch, report, spec, job, on_read)
    base = {"index": ch["index"], "number": ch["number"],
            "label": ch.get("label"), "bad": bool(ch.get("bad"))}
    if not segs:
        return [], dict(base, n=0,
                        error="nothing readable on this channel")

    # The joined trace must BE the segment. A stitching fault shows up as a
    # trace a few samples short, which shifts every later event earlier by a
    # growing amount -- measured once at a median of -9.71 ms against Toothy,
    # and the whole reason this assertion exists. Half a decimated sample of
    # slack per segment, no more.
    by_index = {int(x["index"]): x for x in (report.get("segments") or [])}
    # A shortfall can only be at the TAIL, and a tail costs no timestamp.
    #
    # The read loop walks the segment in samples and locates each chunk by
    # its absolute index, so a chunk that comes up short does not leave a
    # hole -- the next one starts exactly where it stopped. The only way to
    # end with fewer samples than the segment claims is to run out at the
    # end, and every event's time comes from its own index, so the events
    # that were found are unaffected. What is lost is the last fraction of a
    # second of analysis.
    #
    # Rejecting a channel for that was wrong and cost whole recordings:
    # KCNT1 m306 s1 came back with zero events on every channel because its
    # segment 6 was thirty-six decimated samples -- thirty-six milliseconds
    # -- short of what the header implies. So the shortfall is REPORTED
    # always and fails only when it is large enough to mean something other
    # than the reader's own granularity.
    slack = max(int(nlx.SAMPLES_PER_RECORD) // q + 1,
                int(0.02 * sum(int(x["n_samples"]) // q
                               for x in (report.get("segments") or []))))
    short, lost = [], 0
    for seg_i, _start, tr in segs:
        want = int(by_index[seg_i]["n_samples"]) // q
        gap = want - tr.size
        lost += max(0, gap)
        if abs(gap) > slack:
            short.append(
                "segment %d is %d decimated samples, expected %d -- short by "
                "%.1f s, which is more than the reader's granularity explains"
                % (seg_i, tr.size, want, gap / lfp_fs))
    if short:
        return [], dict(base, n=0, error="; ".join(short[:3]))

    # Filtered whole-segment, then pooled for the threshold.
    #
    # Toothy's `np.std` spans its concatenated trace including the voltage
    # step at each stitch; pooling the segments excludes that ringing. A
    # handful of samples out of two million either way, but it is a real
    # difference between the two and it belongs in the record rather than in
    # somebody's later confusion.
    ds = [(i, start, _filtered(tr, lfp_fs, band)) for i, start, tr in segs]
    pooled = np.concatenate([f for _, _, f in ds])
    thr = threshold_for(pooled, spec.get("height_sd", DS_HEIGHT_SD),
                        spec.get("abs_uv", DS_ABS_THR_UV),
                        spec.get("estimator") or "sd")
    if spec.get("threshold_uv"):
        # An override replaces the number, not the story of where the
        # automatic one came from -- both stay in the summary.
        thr["thr_uv"] = float(spec["threshold_uv"])
        thr["thr_source"] = "override"

    # A threshold that is not a number means the trace is not one either --
    # a NaN anywhere in it poisons `np.std`. Failed with a reason rather
    # than nulled: a channel left in the ranking with a missing threshold
    # can still win the hilus pick, against a comparison that is not a
    # number, and that is worse than one channel short.
    if not math.isfinite(thr["thr_uv"]) or not math.isfinite(thr["sd_uv"]):
        n_bad = int(np.count_nonzero(~np.isfinite(pooled)))
        return [], dict(base, n=0, error=(
            "this channel's filtered trace is not all numbers (%d of %d "
            "samples), so no threshold can be set from it"
            % (n_bad, pooled.size)))

    # The two other bands, from the RAW decimated trace. Not from the
    # DS-filtered one: that is 5-100 Hz, and a ripple measured through it
    # would be a measurement of the filter.
    raw_all = np.concatenate([tr for _, _, tr in segs])
    std_theta = float(np.std(_filtered(raw_all, lfp_fs, THETA_BAND),
                             dtype=np.float64))
    std_swr = (float(np.std(_filtered(raw_all, lfp_fs, SWR_BAND),
                            dtype=np.float64))
               if SWR_BAND[1] < lfp_fs / 2.0 else 0.0)

    events = []
    for seg_i, start_concat, f in ds:
        if job:
            job.check()
        got = _detect(f, lfp_fs, thr["thr_uv"], spec)
        for k in range(got["idx"].size):
            j = int(got["idx"][k])
            # The decimated index back to a full-rate index in the whole
            # recording, then to a time through the breakpoint map. This is
            # the ONLY place a time is made here, and it never assumes a
            # linear axis -- see `continuity.sample_to_true`.
            concat_i = start_concat + j * q
            t = continuity.sample_to_true(report, concat_i)
            if t is None:
                continue
            near = continuity.near_stitch(report, t)
            events.append({
                "start": round(float(t), 6),
                # Absolute Neuralynx microseconds: the one identity that does
                # not depend on which tool made the number.
                "abs_us": int(report.get("t0_us") or 0) + int(round(t * 1e6)),
                "segment": seg_i,
                # An event within a filter length of a stitch may be ringing
                # against the voltage step rather than a dentate spike.
                # `near_stitch`'s own default half-window is this detector's
                # `ds_wlen`, which is not a coincidence.
                "near_stitch": bool(near) if near is not None else False,
                # Shape measures can legitimately have no value. Toothy's
                # asymmetry divides by the distance from the peak to its own
                # half-height edge, and that distance can be zero -- the
                # event is still real, so it stays and the measure is null.
                "amp": _finite(got["amp"][k], 4),
                "prom": _finite(got["prom"][k], 4),
                "half_width_ms": _finite(got["half_width_ms"][k], 4),
                "width_height": _finite(got["width_height"][k], 4),
                "asym": _finite(got["asym"][k], 3),
                "idx": int(concat_i),
                "channel": int(ch["number"]),
            })

    events.sort(key=lambda e: e["start"])
    amps = np.array([e["amp"] for e in events]) if events else np.array([])

    # What the three per-channel plots are drawn from. Toothy draws the same
    # three off `DF_MEAN` and `DF_ALL` in `ephys.py:1144
    # plot_channel_events`: the count, every event's amplitude, and the mean
    # half-prominence height with its standard error.
    #
    # `width_height` is `peak_widths(rel_height=0.5)`'s evaluation height --
    # the trace level halfway down the peak's own prominence. Toothy labels
    # that axis "prominence / 2" and this keeps the name, because a plot
    # somebody has been reading for two years should not change its labels
    # on the way into a second tool.
    wh = np.array([e["width_height"] for e in events
                   if e["width_height"] is not None], dtype=np.float64)
    # `.agg('sem')`, which is what Toothy takes: the ddof=1 standard
    # deviation over the root of the count. Zero for a single event, because
    # one measurement has no spread -- not NaN, which would put a hole in
    # the error bar rather than a point with none.
    wh_sem = (float(np.std(wh, ddof=1) / math.sqrt(wh.size))
              if wh.size > 1 else 0.0)
    stride = max(1, int(math.ceil(len(events) / float(AMP_SAMPLE_MAX))))
    amp_sample = [round(float(e["amp"]), 3) for e in events[::stride]
                  if e["amp"] is not None]
    span = sum(float(x["duration_s"]) for x in (report.get("segments") or [])
               if x["duration_s"] >= MIN_SEGMENT_S) or 1.0
    summary = dict(base, **{
        "n": len(events),
        "rate_hz": _finite(len(events) / span, 5),
        "mean_amp": _finite(amps.mean(), 3) if amps.size else 0.0,
        "median_amp": _finite(np.median(amps), 3) if amps.size else 0.0,
        # Over the events that HAVE a width; `_finite` may have nulled some.
        "mean_half_width_ms": _finite(np.mean(
            [e["half_width_ms"] for e in events
             if e["half_width_ms"] is not None] or [0.0]), 3),
        "std_theta": _finite(std_theta, 4),
        "std_swr": _finite(std_swr, 4),
        # The third plot: mean height above the surround, with its error.
        "width_height_mean": _finite(wh.mean(), 4) if wh.size else None,
        "width_height_sem": _finite(wh_sem, 4),
        "n_width_height": int(wh.size),
        # The second plot. `n` above is the first, and is exact.
        "amp_sample": amp_sample,
        "amp_sample_stride": int(stride),
        "n_near_stitch": sum(1 for e in events if e["near_stitch"]),
        "n_samples": int(raw_all.size),
        # Decimated samples the reader could not supply at the tail of a
        # segment, within the one-record tolerance above. Usually zero.
        # Decimated samples the reader could not supply at the tail of a
        # segment. Usually zero; when it is not, that many milliseconds at
        # the very end of a segment were not looked at. No timestamp moves.
        "tail_short": int(lost),
        "tail_short_ms": round(1000.0 * lost / lfp_fs, 1),
    })
    summary.update(thr)
    return events, summary




def run(session, spec, report, job=None):
    """Scan the chosen channels, and say which one the dentate spikes are on.

    The whole thing in one pass: Toothy detects on every channel and then
    picks the hilus channel from the per-channel statistics
    (`raw_data_pipeline.py:290`, `ephys.py:916`), so the scan and the pick are
    not separable steps. What the caller does with the pick -- accept it,
    drag it somewhere else -- happens afterwards and costs nothing.
    """
    if not HAVE_SCIPY:
        raise RuntimeError("Dentate spike detection needs scipy, which is "
                           "not installed here.")
    if not report or not report.get("ok"):
        raise ValueError("That recording has not been segmented, so there is "
                         "no clock to stamp events on.")
    # Times are stamped from a segmentation measured on a few channels. If
    # those disagreed with one another, the segmentation is not a fact about
    # the recording and nothing here can be trusted.
    if report.get("mismatches"):
        raise ValueError(
            "The channels checked for gaps do not agree with one another "
            "(%s), so there is no single clock to stamp events on."
            % ", ".join(str(m) for m in report["mismatches"][:3]))

    plan = plan_for(session, spec, report)
    by_index = {c["index"]: c for c in (session.get("channels") or [])}
    want = [by_index[i] for i in (spec.get("channels") or [])
            if i in by_index]
    if not want:
        raise ValueError("No channels chosen.")

    if job:
        job.begin("ds read", of=int(plan["span_s"] * len(want)),
                  unit="seconds")

    done = [0.0]
    rows, per_channel = {}, []
    for ch in want:
        def on_read(got, base=done[0]):
            if job:
                job.tick("ds read", int(base + got))

        events, summary = _channel_pass(session, ch, report, spec, job,
                                        on_read)
        done[0] += plan["span_s"]
        if job:
            job.tick("ds read", int(done[0]))
        rows[ch["index"]] = events
        per_channel.append(summary)

    if job:
        # Opened once, after the loop, with its count already reached: the
        # detection happened interleaved with the reading and cannot be shown
        # as a phase of its own without holding every channel at once.
        job.begin("ds detect", of=len(want), unit="channels")
        job.tick("ds detect", len(want))

    picked = {
        "hilus": pick_hilus(per_channel),
        "theta": pick_theta(per_channel),
        "ripple": pick_ripple(per_channel),
    }
    # Beside the picks, not among them: a second answer to the hilus
    # question that the panel offers as a button. See `pick_most_spikes`.
    alternates = {"most_spikes": pick_most_spikes(per_channel)}
    hil = picked["hilus"]
    chosen = hil["index"] if hil else want[0]["index"]

    out = _clean({
        "ok": True,
        "units": "microvolts",
        # What clock these are on, said in the answer rather than inferred
        # from the name of the tool that made it.
        "time_basis": {
            "kind": "neuralynx_true",
            "tool": "jarvis.incisor/1",
            "origin": "first .ncs record timestamp",
            "t0_us": report.get("t0_us"),
            "gap_map_sha": report.get("gap_map_sha"),
            "breaks_sha": continuity.breaks_sha(report),
            # How good the clock itself is. A time from here is worth a
            # fraction of a millisecond, not a microsecond, and a reader
            # should not have to measure that again.
            "residual_sd_us": report.get("map_residual_sd_us"),
            "residual_max_us": report.get("map_residual_max_us"),
            # The channel picks below do not enter this, and saying so is
            # worth a field: the three of them are computed FROM the
            # detection and never feed back into it. A time is a sample
            # index put through the record timestamps. Changing the hilus,
            # theta or ripple channel changes which events you are looking
            # at -- each channel was detected on separately and has its own
            # list -- and moves none of them.
            "depends_on_channel": False,
        },
        "continuity": {
            "n_segments": report.get("n_segments"),
            "seconds_lost": report.get("seconds_lost"),
            "n_short_inside": report.get("n_short_inside"),
            "sub_threshold_lost_s": report.get("sub_threshold_lost_s"),
            "probed": report.get("probed"),
            "true_duration_s": report.get("true_duration_s"),
        },
        "params": _params(spec, plan),
        "plan": plan,
        "channels": per_channel,
        "picked": picked,
        "alternates": alternates,
        "chosen": chosen,
        "events": rows.get(chosen) or [],
        "n": len(rows.get(chosen) or []),
        # NOT every channel's events. That was sixty-four times the payload
        # to draw one channel, and a response large enough to be cut short in
        # transit arrives as a 200 with a body that will not parse. The
        # per-channel counts are in `channels`; the events themselves come
        # from `events_for`, out of the cache this run just filled.
        "n_by_channel": {str(k): len(v) for k, v in rows.items()},
    })


    # Kept beside the answer, not inside it: `_rows` never reaches a
    # response, and the cache holds the whole object.
    out["_rows"] = rows
    return out


def events_for(out, index):
    """One channel's events out of a finished scan.

    `run` keeps them all -- they were all detected -- but only ships the
    chosen channel's. This is how the panel gets another one without the
    recording being read again.
    """
    return (out.get("_rows") or {}).get(int(index)) or []


def _params(spec, plan):
    """Exactly what was applied, in the units it was applied in."""
    return {
        "detector": "Incisor",
        "ported_from": "Toothy ephys.get_ds_peaks",
        "height_sd": float(spec.get("height_sd", DS_HEIGHT_SD)),
        "abs_thr_uv": float(spec.get("abs_uv", DS_ABS_THR_UV)),
        "dist_ms": float(spec.get("dist_ms", DS_DIST_MS)),
        "prom_uv": float(spec.get("prom_uv", DS_PROM_UV)),
        "wlen_ms": float(spec.get("wlen_ms", DS_WLEN_MS)),
        "band_hz": list(spec.get("band") or DS_BAND),
        "filter_order": DS_ORDER,
        "lfp_fs": plan["lfp_fs"],
        "decimate": plan["decimate"],
        "estimator": spec.get("estimator") or "sd",
        "invert": bool(spec.get("invert", True)),
        "even_only": bool(plan.get("even_only")),
        "bad_channels_excluded": list(spec.get("bad_channels") or []),
        "n_channels_scanned": int(plan.get("n_channels") or 0),
        "probe": spec.get("probe") or "h3",
        "notes": [
            "Filtered per segment and pooled for the threshold, so the "
            "voltage step at each stitch is excluded; Toothy's np.std spans "
            "its concatenated trace and includes it.",
            "Decimated with scipy.signal.decimate in stages; Toothy uses "
            "scipy.signal.resample, an FFT method. Measured against Toothy's "
            "own code on 300 s of CSC41: the same dentate spikes to within "
            "one sample, a 2% difference in the threshold (an FFT resample "
            "is a brick wall and decimate is not, so they leave different "
            "variance in band), and one event in 193.",
            "Times are stamped through the record-level breakpoint map, not "
            "from a linear axis.",
            "Channels marked bad on this session were not read at all, so "
            "they cannot win the hilus, theta or ripple pick. Toothy keeps "
            "them and nulls them out of the estimates afterwards "
            "(ephys.py noise_idx); the three answers are the same either "
            "way.",
            "The hilus, theta and ripple channels are derived FROM the "
            "detection, not used to produce it. Every event time here is a "
            "sample index put through the record timestamps, so choosing a "
            "different channel shows a different set of events and moves "
            "none of them.",
        ],
    }
