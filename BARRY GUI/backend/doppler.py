# -*- coding: utf-8 -*-
"""doppler.py -- interictal discharges by line length, step 1 of The Storm.

A port of Jon Kleen's `LLspikedetector.m` (IED/03_IED_Detection), which is
what this lab has always used, wrapped in the reading and stamping this
application does for every other detector.

WHY A PORT AND NOT THE MATLAB

The cluster can run MATLAB -- `vacc.activate` emits `module load` from
vacc.json and the lab's own .sbat files do exactly that. The port exists
because `vacc_run.py` runs the SAME code on the cluster that runs here, which
is what makes the stage protocol, the result cache, cancellation and the
parity check work at all. The MATLAB stays as the oracle: `tools/
check_doppler_parity.py` runs it and asserts this file agrees exactly.

THREE PLACES A PORT OF THIS SILENTLY DISAGREES

Each of these produces an answer that is nearly right, which is worse than
one that is obviously wrong. They are the reason `llspikedetector()` below is
a literal transcription and not a tidy rewrite.

  `prctile` IS NOT `np.percentile`. MATLAB places the k-th of n sorted values
  at (k-0.5)/n; numpy's default places it at k/(n-1). On a billion
  line-length samples the two land on different values, which moves the
  threshold, which moves every event. This is numpy's `method="hazen"`, and
  `matlab_prctile` implements it directly rather than depending on a numpy
  new enough to name it.

  `round` IS NOT `np.round`. MATLAB rounds a half away from zero; numpy
  rounds a half to even. `ets = round(ets+(sfx*llw)/2)` hits this on every
  event whose centre lands on a half sample.

  THE MERGE LOOP MUTATES AS IT GOES. `ets(i+1,1)=ets(i,1)` inside the loop
  means three events closer than 300 ms all collapse onto the FIRST one's
  onset, not pairwise. A vectorised rewrite gets two of the three.

WHAT THIS FIXES, DELIBERATELY

The original is not wrong so much as unable to say what it did.

  BAD CHANNELS ARE DROPPED BEFORE THE TRANSFORM, not zeroed after the event
  list is built. In the original, `ech(:,badch)=0` runs after
  `a=nansum(Li,1)>0` has already decided where events start and stop, so a
  bad channel widens windows and shifts onsets, and the event survives as
  long as any good channel also fired. Here a bad channel is not read.

  THE THRESHOLD POOLS ONLY KEPT CHANNELS. One noisy channel used to raise
  the bar for every channel.

  TIMES ARE TRUE RECORDING SECONDS. The original flattens records by
  NumberValidSamples and warns that gaps are not interpolated, so `ets/fs`
  drifts from the recording's own clock. Detection still happens on the
  concatenated signal -- the raw files are never touched -- and
  `continuity.concat_to_true` converts on the way out.

  A SPLIT RECORDING REFUSES. `CSCn_0001.ncs` continuation files are real
  here; a reader that takes only part one reports a rate for a third of a
  recording and looks entirely healthy doing it.
"""
from __future__ import annotations

import hashlib
import json
import threading

import numpy as np

# Loaded on first use, not at start-up; see lazyimp.py for why.
from . import lazyimp  # noqa: E402
HAVE_SCIPY = lazyimp.have("scipy")
_sig = lazyimp.module("scipy.signal") if HAVE_SCIPY else None

from . import continuity, csc, nlx

# --------------------------------------------------------------------------
# Defaults -- every one of them cited to the script it came from
# --------------------------------------------------------------------------

LLW_S = 0.040          # vacc_ied_detect1.m:48   'llw'
PRC = 99.9             # vacc_ied_detect1.m:49   'prc'
MERGE_S = 0.300        # LLspikedetector.m:77    sfx*.3
MIN_EVENT_S = 0.025    # LLspikedetector.m:86    minL

# Filtering is OFF by default so a first run reproduces the legacy numbers
# and any change to them is deliberate. Both of these are None unless the
# caller says otherwise.
NOTCH_HZ = None        # 60.0 is the usual answer here
BAND = None            # (3.0, 70.0) is the usual answer here
NOTCH_Q = 30.0

# How many events' worth of raw signal comes back with a run. The average is
# computed on the cluster; these are so the report can show individual
# examples without a second read. Capped because the one number you least
# control is how many events a detector found.
SNIPPET_MAX = 200
SNIPPET_MS = 400.0
# The rate the average and the snippets are kept at. See `_summarise`.
DISPLAY_HZ = 1000.0

# Reading is chunked so memory stays bounded whatever the recording is.
CHUNK_SECONDS = 60.0

# A channel that takes part in more than this fraction of events is reported
# as suspect. Measured on the lab's own runs: a real channel in a 32-channel
# probe is in 10-60% of events; the ones that were actually broken sat above
# 95%.
SUSPECT_FRAC = 0.90

_CACHE = {}
_CACHE_ORDER = []
CACHE_MAX = 8
_CACHE_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# The MATLAB conventions, exactly
# --------------------------------------------------------------------------

def matlab_prctile(values, p):
    """`prctile(values, p)` for a vector, to the bit.

    MATLAB puts the k-th of n sorted values at the (k-0.5)/n quantile and
    interpolates linearly between them, clamping outside. That is Hazen's
    definition; numpy's default is a different one and lands elsewhere.
    """
    a = np.asarray(values, dtype=np.float64).ravel()
    a = a[np.isfinite(a)]
    n = a.size
    if n == 0:
        return float("nan")
    if n == 1:
        return float(a[0])
    a = np.sort(a, kind="stable")
    pos = float(p) * n / 100.0 + 0.5          # 1-based position
    if pos <= 1.0:
        return float(a[0])
    if pos >= n:
        return float(a[-1])
    lo = int(np.floor(pos))
    frac = pos - lo
    return float(a[lo - 1] + frac * (a[lo] - a[lo - 1]))


def tail_size(prc, n_upper):
    """How many values from one end of each channel decide `prctile`.

    The p-th percentile of n values reads the order statistics at 1-based
    position p*n/100 + 0.5 and the one above it, so at most
    n*(1-p/100) + 1.5 values sit at or above them. The largest m values of
    the whole pool are among the largest m of every channel, so keeping that
    many per channel keeps every value the answer can depend on, at full
    precision -- where pooling every value as float32 moved the threshold in
    its seventh digit.
    """
    frac = (100.0 - float(prc)) / 100.0 if prc >= 50 else float(prc) / 100.0
    return int(np.ceil(float(n_upper) * frac)) + 2


def keep_tail(values, prc, m):
    """The m values of `values` that `prctile_from_tail` needs, float64."""
    v = np.asarray(values, dtype=np.float64).ravel()
    if v.size <= m:
        return v.copy()
    if prc >= 50:
        return np.partition(v, v.size - m)[v.size - m:].copy()
    return np.partition(v, m - 1)[:m].copy()


def prctile_from_tail(kept, n, prc, m):
    """`matlab_prctile` of n values, from the tails `keep_tail` kept.

    `kept` is every channel's tail concatenated; its own top (or bottom) m
    are the pool's top (or bottom) m. Raises rather than guessing if a
    position it needs falls outside what was kept.
    """
    a = np.sort(np.asarray(kept, dtype=np.float64), kind="stable")
    if n == 0:
        return float("nan")
    if a.size == n:
        return matlab_prctile(a, prc)
    top = prc >= 50
    k = min(m, a.size)
    a = a[a.size - k:] if top else a[:k]
    base = n - k if top else 0                 # global 0-based index of a[0]

    def at(j):                                 # global 0-based order statistic
        if not (base <= j < base + k):
            raise RuntimeError("the kept tail does not reach order statistic "
                               "%d of %d" % (j, n))
        return float(a[j - base])

    if n == 1:
        return at(0)
    pos = float(prc) * n / 100.0 + 0.5
    if pos <= 1.0:
        return at(0)
    if pos >= n:
        return at(n - 1)
    lo = int(np.floor(pos))
    frac = pos - lo
    return float(at(lo - 1) + frac * (at(lo) - at(lo - 1)))


def matlab_round(x):
    """MATLAB rounds a half AWAY FROM ZERO. numpy rounds a half to even."""
    a = np.asarray(x, dtype=np.float64)
    return np.sign(a) * np.floor(np.abs(a) + 0.5)


def linelength(x, w):
    """The line-length transform, matching the loop in LLspikedetector.m.

    `L(:,i) = sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2)` for i = 1 ..
    N-numsamples, and NaN for the tail the window does not fit in.

    Done as a cumulative sum rather than a sliding loop -- the same
    arithmetic in O(n) instead of O(n*w), which is what makes a 30 kHz
    recording finish at all. Checked against the literal loop in the parity
    harness on a small matrix, because "the same arithmetic" is exactly the
    kind of claim that wants a test.
    """
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    n_ch, n = x.shape
    out = np.full((n_ch, n), np.nan, dtype=np.float64)
    if n <= w:
        return out
    ad = np.abs(np.diff(x, axis=1))                       # n-1 wide
    c = np.zeros((n_ch, ad.shape[1] + 1), dtype=np.float64)
    np.cumsum(ad, axis=1, out=c[:, 1:])
    valid = n - w                                         # columns 0..valid-1
    out[:, :valid] = c[:, w - 1:w - 1 + valid] - c[:, :valid]
    return out


def llspikedetector(d, sfx, llw=LLW_S, prc=PRC, badch=None):
    """A literal transcription of LLspikedetector.m.

    Returns (ets, ech) with `ets` in **1-based MATLAB sample indices**, so
    the parity harness can compare against the MATLAB's own output without
    anybody having to reason about an off-by-one at the same time as an
    arithmetic difference.

    Quirks reproduced on purpose, not overlooked:

      the unterminated-event fix clamps to `length(a)` where `a` has already
      been replaced by its own diff, so it is N-1 rather than N;

      events are dropped for having no participating GOOD channel only after
      the bad ones are zeroed, which is the original's order; and

      the merge loop is sequential and its mutation carries forward.
    """
    d = np.atleast_2d(np.asarray(d, dtype=np.float64))
    if d.ndim > 2:
        raise ValueError("Accepts only vector or 2-D matrix for data")
    # `if size(d,1)>size(d,2); d=d'; end` -- rows are channels.
    if d.shape[0] > d.shape[1]:
        d = d.T
    n_ch, n = d.shape
    if badch is None:
        badch = np.zeros(n_ch, dtype=bool)
    badch = np.asarray(badch, dtype=bool).ravel()

    w = int(matlab_round(llw * sfx))
    L = linelength(d, w)

    thr = matlab_prctile(L, prc)
    with np.errstate(invalid="ignore"):
        Li = L > thr                                      # NaN > x is False

    a = Li.sum(axis=0) > 0
    da = np.diff(a.astype(np.int8))
    e_on = np.flatnonzero(da == 1) + 2                    # 1-based
    e_off = np.flatnonzero(da == -1) + 1                  # 1-based

    if e_on.size == 0 and e_off.size == 0:
        return (np.zeros((0, 2), dtype=np.int64),
                np.zeros((0, n_ch), dtype=bool))
    if e_off.size and (e_on.size == 0 or e_off[0] < e_on[0]):
        e_on = np.concatenate(([1], e_on))
    if e_off.size < e_on.size:
        # `length(a)` AFTER a was overwritten by diff(a): N-1, not N.
        e_off = np.concatenate((e_off, [da.size]))
    if e_off.size != e_on.size:
        raise ValueError("start and end of events is not matching up, "
                         "check your code")

    ets = np.stack([e_on, e_off], axis=1).astype(np.int64)

    ech = np.zeros((ets.shape[0], n_ch), dtype=bool)
    for i in range(ets.shape[0]):
        lo, hi = int(ets[i, 0]), int(ets[i, 1])           # 1-based inclusive
        ech[i, :] = Li[:, lo - 1:hi].any(axis=1)

    ets = matlab_round(ets + (sfx * llw) / 2.0).astype(np.int64)

    ech[:, badch] = False
    keep = ech.sum(axis=1) >= 1
    ets, ech = ets[keep], ech[keep]

    # The merge, sequential and mutating, exactly as written.
    s = ets.shape[0]
    drop = np.zeros(s, dtype=bool)
    for i in range(s - 1):
        if (ets[i + 1, 0] - ets[i, 1]) < sfx * MERGE_S:
            ets[i + 1, 0] = ets[i, 0]
            ech[i + 1, :] = ech[i, :] | ech[i + 1, :]
            drop[i] = True
    ets, ech = ets[~drop], ech[~drop]

    too_short = (ets[:, 1] - ets[:, 0]) < (sfx * MIN_EVENT_S)
    return ets[~too_short], ech[~too_short]


# --------------------------------------------------------------------------
# Filtering -- off unless asked for
# --------------------------------------------------------------------------

def apply_filters(x, fs, notch_hz=None, band=None, notch_q=NOTCH_Q):
    """Notch then bandpass, zero-phase, or the signal untouched.

    Both stages are None by default. A run with no filtering is the one that
    reproduces the legacy numbers, and it is the default so that a difference
    from the legacy numbers is always something somebody asked for.
    """
    if notch_hz is None and band is None:
        return x
    if not HAVE_SCIPY:
        raise RuntimeError("Filtering needs scipy, which is not installed "
                           "here. Run with no filter, or install scipy.")
    y = np.asarray(x, dtype=np.float64)
    if notch_hz:
        # Every harmonic that fits, not just the fundamental: mains at 60 Hz
        # arrives with a 120 and a 180 and the line-length transform is most
        # sensitive to the highest one present.
        for k in range(1, 6):
            f = float(notch_hz) * k
            if f >= fs / 2.0:
                break
            b, a = _sig.iirnotch(f, notch_q, fs)
            y = _sig.filtfilt(b, a, y, axis=-1)
    if band:
        lo, hi = float(band[0]), float(band[1])
        hi = min(hi, fs / 2.0 * 0.99)
        sos = _sig.butter(3, [lo, hi], btype="band", fs=fs, output="sos")
        y = _sig.sosfiltfilt(sos, y, axis=-1)
    return y


# --------------------------------------------------------------------------
# Planning and caching
# --------------------------------------------------------------------------

def _spec_fingerprint(spec):
    keep = ("channels", "bad_channels", "llw_s", "prc", "notch_hz", "band",
            "even_only", "invert", "path")
    return {k: spec.get(k) for k in keep}


def cache_key(spec, report=None):
    body = {"spec": _spec_fingerprint(spec),
            "gap_map": (report or {}).get("gap_map_sha")}
    raw = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


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


def check_parts(folder):
    """Refuse a recording that is in more than one piece per channel.

    `CSCn_0001.ncs` is what Cheetah writes when a recording is restarted or
    a file grows past its limit, and the KCNT1 urethane recordings have
    them. A reader that takes only `CSCn.ncs` gets part one and reports a
    perfectly healthy-looking rate for a third of a recording, which is the
    worst failure available to a detector. Joining them is real work and is
    not done here, so this says so instead.
    """
    try:
        parts = nlx.csc_parts(folder)
    except Exception:                                    # noqa: BLE001
        return None
    split = {str(k): list(v) for k, v in (parts or {}).items() if len(v) > 1}
    if not split:
        return None
    names = sorted(split)[:4]
    return ("This recording is in more than one piece: %s %s a continuation "
            "file beside it. Reading only the first piece would report a "
            "rate for part of the recording, so nothing was run."
            % (", ".join(names),
               "has" if len(names) == 1 else "each have"))


def plan_for(session, spec, report=None):
    fs = float((report or {}).get("fs") or session.get("fs") or 30000.0)
    by_index = {c["index"]: c for c in (session.get("channels") or [])}
    want = [i for i in (spec.get("channels") or []) if i in by_index]
    span = float(session.get("duration_s") or 0.0)
    if report and report.get("segments"):
        span = float(sum(s["duration_s"] for s in report["segments"]))
    megasamples = span * fs * max(1, len(want)) / 1e6
    return {
        "n_channels": len(want),
        "span_s": span,
        "fs": fs,
        "megasamples": megasamples,
        "window_samples": int(matlab_round(
            float(spec.get("llw_s") or LLW_S) * fs)),
        "excluded": list(spec.get("excluded") or []),
        # Read twice: once to pool the line-length distribution for the
        # threshold, once to apply it. Said here rather than discovered from
        # a progress bar that reaches 50% and starts again.
        "passes": 2,
        # WHAT SLURM IS ASKED FOR. `vacc.slurm_request` sizes the wall time
        # from `plan["seconds"]`, and this key used to be missing -- so every
        # run asked for the ten-minute floor, and a whole recording read
        # twice over netfiles does not fit in ten minutes. A job killed at
        # its time limit reports as a failure with no result, which reads
        # as a detector bug rather than as a request that was too small.
        #
        # Seeded conservatively: twenty seconds of one channel read per
        # second of wall, which is slower than the lab's local reads. The
        # 3x SAFETY in `slurm_request` goes on top. Asking for too much
        # costs a place in the queue; asking for too little costs the run.
        "seconds": max(120.0, span * max(1, len(want)) * 2 / 20.0),
    }


def estimate(session, spec, report=None):
    # One figure, from `plan_for`, so what the panel quotes and what slurm
    # is asked for cannot come apart. The real rate is learned by cfc once
    # this has run on the cluster.
    return plan_for(session, spec, report)


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def _read_channel(session, ch, report, spec, job=None, on_read=None):
    """One channel's whole recording, concatenated, in microvolts.

    Concatenated across segments because that is what the detector has
    always run on, and because a line-length window that straddles a gap is
    a question nobody has answered. The concat index is converted back to
    true recording seconds on the way out, so the gap never becomes a lie
    about when something happened.
    """
    fs = float(report.get("fs") or session.get("fs") or 30000.0)
    pieces = []
    at_concat = 0
    for seg in report.get("segments") or []:
        n_samples = int(seg["n_samples"])
        start_concat = at_concat
        at_concat += n_samples
        t0 = float(seg["true_t0_s"])
        want_i = 0
        while want_i < n_samples:
            if job:
                job.check()
            take = min(int(CHUNK_SECONDS * fs), n_samples - want_i)
            t_lo = continuity.sample_to_true(report, start_concat + want_i)
            if t_lo is None:
                break
            t_hi = continuity.sample_to_true(
                report, min(start_concat + want_i + take,
                            start_concat + n_samples - 1))
            if t_hi is None or t_hi <= t_lo:
                t_hi = t_lo + take / fs
            raw, got_t0, _got_fs = csc._read_channel_window(
                session, ch, max(t0, t_lo), t_hi)
            if not raw.size:
                break
            i_first = continuity.true_to_sample(report, got_t0)
            if i_first is None:
                break
            i0 = (start_concat + want_i) - i_first
            if i0 < 0 or i0 >= raw.size:
                break
            take = min(take, raw.size - i0)
            if take <= 0:
                break
            pieces.append(np.asarray(raw[i0:i0 + take], dtype=np.float64))
            want_i += take
            if on_read:
                on_read(min(n_samples, want_i) / fs)
    if not pieces:
        return np.zeros(0, dtype=np.float64)
    return np.concatenate(pieces)


def run(session, spec, report, job=None):
    """Find IEDs on the kept channels, and say enough about them to judge.

    Two passes over the recording. The first pools every kept channel's
    line-length values so the percentile threshold is taken over the
    channels that count; the second applies it and records which channels
    crossed where. The alternative -- one pass holding every channel's
    transform at once -- is 7 GB on a 32-channel half-hour recording at 30
    kHz, which is most of why the lab's .sbat files ask for 800 GB.
    """
    if not report or not report.get("ok"):
        raise ValueError("That recording has not been segmented, so there is "
                         "no clock to stamp events on.")
    if report.get("mismatches"):
        raise ValueError(
            "The channels checked for gaps do not agree with one another "
            "(%s), so there is no single clock to stamp events on."
            % ", ".join(str(m) for m in report["mismatches"][:3]))

    refusal = check_parts(session.get("path"))
    if refusal:
        raise ValueError(refusal)

    by_index = {c["index"]: c for c in (session.get("channels") or [])}
    want = [by_index[i] for i in (spec.get("channels") or []) if i in by_index]
    if not want:
        raise ValueError("No channels chosen.")

    fs = float(report.get("fs") or session.get("fs") or 30000.0)
    llw = float(spec.get("llw_s") or LLW_S)
    prc = float(spec.get("prc") or PRC)
    band = spec.get("band") or None
    notch = spec.get("notch_hz") or None
    w = int(matlab_round(llw * fs))
    plan = plan_for(session, spec, report)

    # ---- pass one: pool the line-length distribution -------------------
    if job:
        job.begin("ied read", of=int(plan["span_s"] * len(want) * 2),
                  unit="seconds")
    done = [0.0]
    pooled, n_samples, n_pool = [], 0, 0
    n_upper = len(want) * int(report.get("total_samples")
                              or (plan["span_s"] * fs + 1))
    m_tail = tail_size(prc, n_upper)
    for ch in want:
        def on_read(got, base=done[0]):
            if job:
                job.tick("ied read", int(base + got))
        x = _read_channel(session, ch, report, spec, job, on_read)
        done[0] += plan["span_s"]
        if x.size <= w:
            pooled.append(np.zeros(0))
            continue
        x = apply_filters(x, fs, notch, band)
        L = linelength(x, w)[0]
        n_samples = max(n_samples, x.size)
        # The values themselves, not a histogram, and float64, not float32:
        # the threshold has to be the exact order statistic MATLAB would
        # have picked. Only the tail the percentile can land in is kept --
        # see `tail_size` -- which is what keeps this from being the whole
        # recording in memory.
        Lf = L[np.isfinite(L)]
        n_pool += Lf.size
        pooled.append(keep_tail(Lf, prc, m_tail))
        del L, Lf
    if not n_pool:
        raise ValueError("Nothing was read from any chosen channel.")
    thr = prctile_from_tail(np.concatenate(pooled), n_pool, prc, m_tail)
    del pooled

    # ---- pass two: apply it -------------------------------------------
    if job:
        job.begin("ied detect", of=len(want), unit="channels")
    masks, traces = [], []
    for k, ch in enumerate(want):
        def on_read(got, base=done[0]):
            if job:
                job.tick("ied read", int(base + got))
        x = _read_channel(session, ch, report, spec, job, on_read)
        done[0] += plan["span_s"]
        x = apply_filters(x, fs, notch, band)
        L = linelength(x, w)[0]
        with np.errstate(invalid="ignore"):
            masks.append(np.packbits(L > thr))
        traces.append(x.astype(np.float32))
        if job:
            job.tick("ied detect", k + 1)
    n = max(t.size for t in traces)
    Li = np.zeros((len(want), n), dtype=bool)
    for k, m in enumerate(masks):
        row = np.unpackbits(m)[:n]
        Li[k, :row.size] = row.astype(bool)
    del masks

    ets, ech = _events_from_mask(Li, fs, llw)
    stamps = _stamp_at_peak(ets, traces, ech)
    return _summarise(session, spec, report, plan, want, ets, ech, stamps,
                      traces, fs, thr, prc, llw)


def _events_from_mask(Li, sfx, llw):
    """The post-transform half of LLspikedetector, on a ready-made mask.

    Split out from `llspikedetector` so the streaming run and the literal
    port share the one copy of this arithmetic rather than agreeing by
    inspection. Bad channels are already absent here -- they were never
    read -- so the original's `ech(:,badch)=0` has nothing left to do.
    """
    n_ch = Li.shape[0]
    a = Li.sum(axis=0) > 0
    da = np.diff(a.astype(np.int8))
    e_on = np.flatnonzero(da == 1) + 2
    e_off = np.flatnonzero(da == -1) + 1
    if e_on.size == 0 and e_off.size == 0:
        return (np.zeros((0, 2), dtype=np.int64),
                np.zeros((0, n_ch), dtype=bool))
    if e_off.size and (e_on.size == 0 or e_off[0] < e_on[0]):
        e_on = np.concatenate(([1], e_on))
    if e_off.size < e_on.size:
        e_off = np.concatenate((e_off, [da.size]))
    ets = np.stack([e_on, e_off], axis=1).astype(np.int64)

    ech = np.zeros((ets.shape[0], n_ch), dtype=bool)
    for i in range(ets.shape[0]):
        ech[i, :] = Li[:, int(ets[i, 0]) - 1:int(ets[i, 1])].any(axis=1)

    ets = matlab_round(ets + (sfx * llw) / 2.0).astype(np.int64)
    keep = ech.sum(axis=1) >= 1
    ets, ech = ets[keep], ech[keep]

    s = ets.shape[0]
    drop = np.zeros(s, dtype=bool)
    for i in range(s - 1):
        if (ets[i + 1, 0] - ets[i, 1]) < sfx * MERGE_S:
            ets[i + 1, 0] = ets[i, 0]
            ech[i + 1, :] = ech[i, :] | ech[i + 1, :]
            drop[i] = True
    ets, ech = ets[~drop], ech[~drop]
    too_short = (ets[:, 1] - ets[:, 0]) < (sfx * MIN_EVENT_S)
    return ets[~too_short], ech[~too_short]


def _stamp_at_peak(ets, traces, ech):
    """The stamp is the largest deflection inside the window.

    The detector hands back a window, not a moment. The onset is where the
    line length first crossed, which is a property of the transform's window
    rather than of the discharge; the midpoint is what the old review images
    used and is an average of two edges. The peak is the thing a person is
    looking at when they decide, and it is what leaves Eye the least to fix.

    Measured only on the channels that took part, so a large excursion on a
    channel this event never involved cannot claim the stamp. Returns
    0-based concat sample indices.
    """
    out = np.zeros(ets.shape[0], dtype=np.int64)
    for i in range(ets.shape[0]):
        lo = max(0, int(ets[i, 0]) - 1)
        hi = int(ets[i, 1])
        rows = np.flatnonzero(ech[i])
        best_i, best_v = lo, -1.0
        for r in rows:
            seg = traces[r][lo:hi]
            if not seg.size:
                continue
            j = int(np.argmax(np.abs(seg)))
            v = float(abs(seg[j]))
            if v > best_v:
                best_i, best_v = lo + j, v
        out[i] = best_i
    return out


def _true_at(report, i, fs):
    """0-based concatenated sample -> true recording seconds, or None."""
    t = continuity.sample_to_true(report, i)
    if t is None and not (report or {}).get("breaks"):
        # An older cached report with no per-record breaks: the segment map
        # is the best there is. `concat_to_true` takes SECONDS and returns
        # (seconds, segment).
        t, _seg = continuity.concat_to_true(report, float(i) / fs)
    return t


def _summarise(session, spec, report, plan, want, ets, ech, stamps, traces,
               fs, thr, prc, llw):
    numbers = [int(c["number"]) for c in want]
    span = float(plan["span_s"]) or 1.0
    half = int(round(SNIPPET_MS / 1000.0 * fs / 2.0))

    events, kept_rows = [], []
    for i in range(ets.shape[0]):
        # Sample indices, not seconds, and `sample_to_true` rather than
        # `concat_to_true`: the latter is exact only to the segment and
        # returns a (seconds, segment) PAIR. `stamps` is 0-based; `ets` is
        # the MATLAB's 1-based, so its offset is one sample earlier.
        t = _true_at(report, int(stamps[i]), fs)
        t_end = _true_at(report, int(ets[i, 1]) - 1, fs)
        if t is None:
            continue
        rows = np.flatnonzero(ech[i])
        # WHICH channel carried the peak, not only how big it was. It is the
        # one the stamp was taken from, so it is the one to put in front of
        # somebody deciding -- and it is the only per-event channel the
        # Event Bank can hold, since an event there has `channel` and not a
        # list of them.
        peak, peak_ch = 0.0, (numbers[rows[0]] if rows.size else None)
        for r in rows:
            seg = traces[r][max(0, int(ets[i, 0]) - 1):int(ets[i, 1])]
            if seg.size:
                v = float(np.max(np.abs(seg)))
                if v > peak:
                    peak, peak_ch = v, numbers[r]
        events.append({
            "start": round(float(t), 6),
            "end": round(float(t_end), 6) if t_end and t_end > t else None,
            "peak_uv": round(peak, 3),
            "peak_channel": peak_ch,
            "n_channels": int(rows.size),
            "channels": [numbers[r] for r in rows],
            "near_stitch": bool(continuity.near_stitch(report, float(t))),
        })
        kept_rows.append(i)

    # The average, computed here so the report draws with no second read.
    #
    # At the DISPLAY rate, not the recording's. 400 ms at 30 kHz is 12000
    # points per channel, and the old full-rate stack was events x channels
    # x 12000 float32 -- 7.7 GB for 5000 events on 32 channels -- with a
    # snippet sample of 200 x 32 x 12000 values that made a result file of
    # half a gigabyte. Each window is block-averaged down to about 1 kHz
    # first, which still resolves a 25 ms discharge, and the mean and SEM
    # are accumulated rather than stacked.
    step = max(1, int(np.floor(fs / DISPLAY_HZ)))
    nb = (2 * half) // step if half else 0
    prof_mean = prof_sem = None
    snippets = {"idx": [], "data": [], "step_samples": step}
    if events and nb:
        n_ev = len(events)
        pick = set(int(i) for i in np.unique(np.linspace(
            0, n_ev - 1, min(SNIPPET_MAX, n_ev)).astype(int)))
        acc = np.zeros((len(want), nb), dtype=np.float64)
        acc2 = np.zeros((len(want), nb), dtype=np.float64)
        cnt = np.zeros((len(want), nb), dtype=np.int64)
        win = np.full((len(want), 2 * half), np.nan, dtype=np.float64)
        for j, row in enumerate(kept_rows):
            c = int(stamps[row])
            lo, hi = c - half, c + half
            win.fill(np.nan)
            for r in range(len(want)):
                tr = traces[r]
                a, b = max(0, lo), min(tr.size, hi)
                if b > a:
                    win[r, (a - lo):(b - lo)] = tr[a:b]
            blocks = win[:, :nb * step].reshape(len(want), nb, step)
            with np.errstate(invalid="ignore"):
                w = np.nanmean(blocks, axis=2) if step > 1 else blocks[:, :, 0]
            ok = np.isfinite(w)
            acc[ok] += w[ok]
            acc2[ok] += w[ok] * w[ok]
            cnt += ok
            if j in pick:
                snippets["idx"].append(j)
                snippets["data"].append(np.nan_to_num(w).round(2).tolist())
        with np.errstate(invalid="ignore", divide="ignore"):
            n_ok = np.maximum(cnt, 1)
            prof_mean = acc / n_ok
            var = np.maximum(acc2 / n_ok - prof_mean * prof_mean, 0.0)
            prof_sem = np.sqrt(var) / np.sqrt(n_ok)
        prof_mean[cnt == 0] = np.nan
        prof_sem[cnt == 0] = np.nan

    per_channel = []
    counts = ech.sum(axis=0) if ech.size else np.zeros(len(want))
    for k, c in enumerate(want):
        per_channel.append({
            "index": int(c["index"]), "number": numbers[k],
            "label": c.get("label"),
            "n": int(counts[k]) if ech.size else 0,
            "rate_hz": round(float(counts[k]) / span, 5) if ech.size else 0.0,
        })

    warnings = []
    if ets.shape[0]:
        for row in per_channel:
            if row["n"] >= SUSPECT_FRAC * ets.shape[0]:
                warnings.append(
                    "CSC%d took part in %d%% of events, which is what a "
                    "broken channel looks like rather than a busy one."
                    % (row["number"], round(100.0 * row["n"] / ets.shape[0])))
        near = sum(1 for e in events if e["near_stitch"])
        if near:
            warnings.append(
                "%d of %d events sit within 125 ms of a break between "
                "records, where the signal is joined rather than continuous."
                % (near, len(events)))
    rate = len(events) / span * 60.0
    if rate > 300:
        warnings.append(
            "%.0f events a minute is high enough to be a threshold that is "
            "too low rather than a recording that is busy." % rate)

    return {
        "ok": True,
        "units": "microvolts",
        "n": len(events),
        "events": events,
        "per_channel": per_channel,
        "profile": {
            "n": len(events),
            # Block centres, in ms from the stamp.
            "ms": (((np.arange(nb) * step + (step - 1) / 2.0) - half)
                   / fs * 1000.0).round(3).tolist() if nb else [],
            "mean": (np.nan_to_num(prof_mean).round(3).tolist()
                     if prof_mean is not None else []),
            "sem": (np.nan_to_num(prof_sem).round(3).tolist()
                    if prof_sem is not None else []),
            "channels": numbers,
        },
        "snippets": snippets,
        "warnings": warnings,
        "duration_s": span,
        "time_basis": {
            "kind": "neuralynx_true",
            "tool": "jarvis.doppler/1",
            "origin": "first .ncs record timestamp",
            "t0_us": report.get("t0_us"),
            "gap_map_sha": report.get("gap_map_sha"),
        },
        "params": {
            "detector": "LLspikedetector (line length)",
            "llw_s": llw, "prc": prc,
            "threshold": round(float(thr), 6),
            "notch_hz": spec.get("notch_hz"),
            "band": spec.get("band"),
            "fs": fs,
            "channels": numbers,
            "bad_channels": list(spec.get("bad_channels") or []),
            "excluded": list(spec.get("excluded") or []),
            "left_out": list(spec.get("left_out") or []),
            "preset": spec.get("preset"),
            "stamp": "peak",
            "merge_s": MERGE_S,
            "min_event_s": MIN_EVENT_S,
            "gap_map_sha": report.get("gap_map_sha"),
        },
    }
