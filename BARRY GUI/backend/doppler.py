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
# ...and only once there are enough events for a fraction to mean anything.
# With one event every channel that took part is "in 100% of them": a run of
# PTEN m5 s44 that found one IED carried sixteen of these warnings.
SUSPECT_MIN_EVENTS = 20

_CACHE = {}
_CACHE_ORDER = []
CACHE_MAX = 8
_CACHE_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# The two methods, and the defaults the panel and every route read
# --------------------------------------------------------------------------
#
# STORM is the default. It is what the IED detector study chose: it catches
# every hand-sorted Solid on the ten PTEN recordings (169 of 169 reachable) in
# 2,568 candidates run through this engine (validate_production.py; 2,595 in
# the study, which sampled the percentile), against the lab's original
# settings which catch 111 of
# them in 4,447 -- AND it still catches all 169 with the threshold one step
# higher or one more channel required. That margin is the point. The cheapest
# setting that merely reaches 169 (2,072) sits on a cliff: chosen on nine
# recordings it missed Solids on the tenth four times in ten, and the first
# defaults shipped here (2,491) lost two Solids to nothing more than this
# engine's exact percentile. This one, chosen the same way, missed none. The
# study is in `FOOOF Playgroun/IED detection and such/README.md` (steps 7-10
# for this choice). In order:
#
#   decimate to 2 kHz                anti-aliased, as each channel is read
#   notch 60 Hz and harmonics
#   common-average reference         per probe bank, good channels only. The
#                                    single biggest fix: one channel's noise
#                                    and whole-probe movement stop counting
#   band-pass 20-300 Hz              raw line length is dominated by 300+ Hz
#                                    unit/EMG activity, which is not an IED.
#                                    The low edge matters little (5, 10, 20
#                                    or none are within a few percent); 20 is
#                                    the one with margin on both sides
#   line length over 15 ms           10, 12.5, 20 and 30 all cost more
#   even channels                    the lab's convention, and what the
#                                    channel-count rule was validated on
#   one pooled 99.9th percentile     per recording, over the detection channels
#   merge gaps < 300 ms, keep >= 12.5 ms
#                                    300 ms is the lab's own definition of one
#                                    event; a longer merge looks cheaper only
#                                    by folding doublets into one candidate
#   at least 7 channels take part    inside the lab's own "5-10 even channels"
#                                    review rule; an upper bound never helped
#
# LEGACY is Kleen's LLspikedetector exactly as the lab ran it: raw, native
# rate, 40 ms, every chosen channel, 99.9th, no channel rule. It is what
# tools/check_doppler_parity.py holds against the MATLAB, and what every run
# banked before Storm existed was made with.

STORM = {
    "method": "storm",
    "llw_s": 0.015,
    "prc": 99.9,
    "notch_hz": 60.0,
    "band": [20.0, 300.0],
    "car": True,
    "fs_work": 2000.0,
    "merge_s": 0.300,
    "min_event_s": 0.0125,
    "min_channels": 7,
    "detect_on": "even",
}
LEGACY = {
    "method": "legacy",
    "llw_s": LLW_S,
    "prc": PRC,
    "notch_hz": None,
    "band": None,
    "car": False,
    "fs_work": None,
    "merge_s": MERGE_S,
    "min_event_s": MIN_EVENT_S,
    "min_channels": 1,
    "detect_on": "all",
}
METHODS = {"storm": STORM, "legacy": LEGACY}
PARAM_KEYS = tuple(STORM.keys())


def params_from(body):
    """The detection parameters a request asks for, defaults filled in.

    A key the caller sent wins, including an explicit None -- that is how the
    panel says "no band-pass". A key it did not send takes the method's
    default. Types are made what the engine expects, so a number typed into
    a box arrives as a number.
    """
    body = body or {}
    method = body.get("method") or "storm"
    if method not in METHODS:
        raise ValueError("No such Doppler method: %r" % (method,))
    out = dict(METHODS[method])
    for k in PARAM_KEYS:
        if k == "method" or k not in body:
            continue
        out[k] = body[k]
    def num(v, cast=float):
        return None if v in (None, "", False) else cast(v)
    out["llw_s"] = float(out["llw_s"])
    out["prc"] = float(out["prc"])
    out["notch_hz"] = num(out["notch_hz"])
    b = out.get("band")
    out["band"] = [float(b[0]), float(b[1])] if b else None
    out["car"] = bool(out["car"])
    out["fs_work"] = num(out["fs_work"])
    out["merge_s"] = float(out["merge_s"])
    out["min_event_s"] = float(out["min_event_s"])
    out["min_channels"] = max(1, int(out["min_channels"] or 1))
    if out["detect_on"] not in ("even", "odd", "all"):
        out["detect_on"] = "even"
    # Not one of PARAM_KEYS, on purpose: adding a key there would rename
    # every run already in the vault. It goes into a run's key and its
    # request hash only when it is set (see `_spec_fingerprint`).
    out["channel_range"] = channel_range(body.get("channel_range"))
    return out


def detects_on(rule, number):
    if rule == "even":
        return int(number) % 2 == 0
    if rule == "odd":
        return int(number) % 2 == 1
    return True


# --------------------------------------------------------------------------
# Which channels go in: the range, then everything else inside it
# --------------------------------------------------------------------------
#
# Some recordings carry 128 channels where only the first 64 are wanted --
# a second headstage, another region, or nothing connected. The range is
# applied FIRST and by CSC number: a channel outside it is not read at all,
# and every other rule runs inside it unchanged -- detect on the even ones,
# leave the bad ones out, reference each probe bank to itself. It is not a
# list of "left out" channels: those are a choice about one run of one
# recording, and a range is a rule that applies to every recording it is
# run on, One or Many, so it is said once in the notes, as a range.

def channel_range(value):
    """`[first, last]`, CSC numbers inclusive, or None for every channel."""
    if not value:
        return None
    try:
        lo, hi = int(value[0]), int(value[1])
    except (TypeError, ValueError, IndexError):
        raise ValueError("A channel range is two CSC numbers: the first and "
                         "the last.")
    if lo < 1 or hi < lo:
        raise ValueError("CSC%d to CSC%d is not a range of channels." % (lo, hi))
    return [lo, hi]


def in_range(rng, number):
    return rng is None or rng[0] <= int(number) <= rng[1]


def restrict(session, kept, excluded, rng):
    """The range applied to a channel list resolved on a compute node, where
    the desk could not open the recording and the list only exists there.
    Returns (kept, excluded, out_of_range) -- the same three the desk's
    `_doppler_spec` makes, so both say the same thing about the same run."""
    rng = channel_range(rng)
    if rng is None:
        return list(kept), list(excluded or []), []
    chans = session.get("channels") or []
    by_index = {int(c["index"]): c for c in chans}
    kept = [i for i in kept
            if i in by_index and in_range(rng, by_index[i]["number"])]
    excluded = [x for x in (excluded or []) if in_range(rng, x["number"])]
    outside = [{"index": int(c["index"]), "number": int(c["number"]),
                "label": c.get("label")}
               for c in chans if not in_range(rng, c["number"])]
    if not kept:
        raise ValueError("Nothing is left to read in CSC%d to CSC%d: every "
                         "channel there is marked bad, or there is none."
                         % (rng[0], rng[1]))
    return kept, excluded, outside


def feed(session, spec):
    """Which channels a run reads, in which role, by label -- the list shown
    before anything is submitted, and the one the bank note writes out.

    From the spec the run will be given and by the engine's own rules: the
    channels read (range and bad channels already applied), less any on a
    bank marked not connected (`run_storm` drops those), split into the ones
    detection runs on and the ones read for the common reference only.
    """
    chans = session.get("channels") or []
    by_index = {int(c["index"]): c for c in chans}
    storm = (spec.get("method") or "legacy") != "legacy"
    rule = (spec.get("detect_on") or "even") if storm else "all"
    nc = not_connected(spec.get("banks")) if storm else set()

    def label(c):
        return c.get("label") or "CSC%d" % int(c["number"])

    def labels(rows):
        return [label(c) for c in sorted(rows, key=lambda c: int(c["number"]))]
    read = [by_index[i] for i in (spec.get("channels") or []) if i in by_index]
    on_nc = [c for c in read if int(c["number"]) in nc]
    read = [c for c in read if int(c["number"]) not in nc]
    return {
        "rule": rule,
        "range": spec.get("channel_range"),
        "car": bool(spec.get("car")) if storm else False,
        "detect": labels([c for c in read if detects_on(rule, c["number"])]),
        "reference": labels([c for c in read
                             if not detects_on(rule, c["number"])]),
        "bad": labels(spec.get("excluded") or []),
        "left_out": labels(spec.get("left_out") or []),
        "out_of_range": labels(spec.get("out_of_range") or []),
        "not_connected": labels(on_nc),
    }


def not_connected(banks):
    """CSC numbers on a bank somebody marked as not connected.

    A KCNT1 128-channel recording with no second implant has CSC 65-128 on an
    unconnected headstage: 1-3 mV of mains and nothing below 8 Hz. Averaged
    into a common reference, that would put its noise into every channel.
    """
    out = set()
    for b in (banks or []):
        if "not connected" in str(b.get("region") or "").lower():
            out.update(range(int(b["first"]), int(b["last"]) + 1))
    return out


def car_groups(numbers, banks):
    """Row indices to average together: one group per probe bank.

    Two implants are two references -- averaging hippocampus into cortex
    would subtract one region's activity from the other's. With no banks on
    record the recording is one probe and one group.
    """
    if not banks:
        return [list(range(len(numbers)))]
    groups = []
    for b in banks:
        lo, hi = int(b["first"]), int(b["last"])
        g = [i for i, n in enumerate(numbers) if lo <= int(n) <= hi]
        if g:
            groups.append(g)
    placed = {i for g in groups for i in g}
    rest = [i for i in range(len(numbers)) if i not in placed]
    if rest:
        groups.append(rest)
    return groups


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
            "invert", "path")
    out = {k: spec.get(k) for k in keep}
    # Constant since even-only reading was removed (2026-10), and kept so a
    # key computed before then still finds its entry.
    out["even_only"] = False
    # A Legacy run's key is exactly what it was before Storm existed, so
    # every run already in the vault is still found by the question that
    # made it. A Storm run's key also carries everything Storm adds.
    if (spec.get("method") or "legacy") != "legacy":
        for k in PARAM_KEYS:
            out[k] = spec.get(k)
        out["banks"] = [[b.get("first"), b.get("last"), b.get("region")]
                        for b in (spec.get("banks") or [])]
    # Only when set, so every run made without one keeps its name.
    if spec.get("channel_range"):
        out["channel_range"] = list(spec["channel_range"])
    return out


def cache_key(spec, report=None, gap_map_sha=None):
    """`gap_map_sha` may be given directly, for a run whose segmentation was
    made on the cluster: the answer carries it in `time_basis`, so the key is
    the one a report in hand would have produced."""
    if gap_map_sha is None:
        gap_map_sha = (report or {}).get("gap_map_sha")
    body = {"spec": _spec_fingerprint(spec),
            "gap_map": gap_map_sha}
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
    storm = (spec.get("method") or "legacy") == "storm"
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
        "passes": 1 if storm else 2,
        "method": spec.get("method") or "legacy",
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
        "seconds": max(120.0, span * max(1, len(want))
                       * (1.2 if storm else 2.0) / 20.0),
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
    """Find IEDs, by whichever method the spec names.

    A spec with no method is a Legacy one: every run made before Storm
    existed, re-opened from the vault, must be answered the way it was asked.
    """
    if (spec.get("method") or "legacy") == "storm":
        return run_storm(session, spec, report, job)
    return run_legacy(session, spec, report, job)


def run_legacy(session, spec, report, job=None):
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


# --------------------------------------------------------------------------
# Storm: the validated method
# --------------------------------------------------------------------------

def run_storm(session, spec, report, job=None):
    """The default. See STORM at the top of this file for what and why.

    ONE pass over the recording. Each channel is read whole at its native
    rate, decimated to 2 kHz and notched straight away, so what is held is
    every read channel at 2 kHz -- 0.9 GB for half an hour of 64 channels,
    where the Legacy method's 30 kHz traces were 14 GB.
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
    if not HAVE_SCIPY:
        raise RuntimeError("The Storm method needs scipy, which is not "
                           "installed here.")

    by_index = {c["index"]: c for c in (session.get("channels") or [])}
    nc = not_connected(spec.get("banks"))
    want = [by_index[i] for i in (spec.get("channels") or []) if i in by_index
            and int(by_index[i]["number"]) not in nc]
    if not want:
        raise ValueError("No channels chosen.")
    numbers = [int(c["number"]) for c in want]
    rule = spec.get("detect_on") or "even"
    det = [k for k, n in enumerate(numbers) if detects_on(rule, n)]
    if not det:
        raise ValueError(
            "None of the channels being read are %s-numbered, so there is "
            "nothing to detect on. Detect on every channel, or put some back."
            % rule)

    fs = float(report.get("fs") or session.get("fs") or 30000.0)
    q = max(1, int(round(fs / float(spec.get("fs_work") or 2000.0))))
    fsw = fs / q
    llw = float(spec.get("llw_s") or STORM["llw_s"])
    prc = float(spec.get("prc") or STORM["prc"])
    notch = spec.get("notch_hz")
    band = spec.get("band")
    merge_s = float(spec.get("merge_s") if spec.get("merge_s") is not None
                    else STORM["merge_s"])
    min_s = float(spec.get("min_event_s") if spec.get("min_event_s")
                  is not None else STORM["min_event_s"])
    k_min = int(spec.get("min_channels") or 1)
    w = max(2, int(round(llw * fsw)))
    plan = plan_for(session, spec, report)

    # ---- read, decimate, notch ------------------------------------------
    if job:
        job.begin("ied read", of=int(plan["span_s"] * len(want)),
                  unit="seconds")
    done = [0.0]
    rows = []
    for ch in want:
        def on_read(got, base=done[0]):
            if job:
                job.tick("ied read", int(base + got))
        x = _read_channel(session, ch, report, spec, job, on_read)
        done[0] += plan["span_s"]
        y = _sig.resample_poly(x, 1, q) if q > 1 else x
        del x
        if notch:
            y = apply_filters(y, fsw, notch, None)
        rows.append(np.asarray(y, dtype=np.float32))
    n2 = min(r.size for r in rows)
    if n2 <= w:
        raise ValueError("Nothing long enough was read from the chosen "
                         "channels to measure line length over.")
    N = np.stack([r[:n2] for r in rows])
    del rows

    # ---- common-average reference, per bank --------------------------------
    if spec.get("car"):
        for g in car_groups(numbers, spec.get("banks")):
            if len(g) < 2:
                continue
            ref = N[g].astype(np.float64).mean(axis=0)
            N[g] -= ref.astype(np.float32)
            del ref

    # ---- band-pass and line length on the detection channels ---------------
    if job:
        job.begin("ied detect", of=len(det), unit="channels")
    D = np.zeros((len(det), n2), dtype=np.float32)
    n_pool, kept = 0, []
    m_tail = tail_size(prc, len(det) * n2)
    for j, k in enumerate(det):
        y = N[k].astype(np.float64)
        if band:
            y = apply_filters(y, fsw, None, band)
        D[j] = y
        L = linelength(D[j][None, :].astype(np.float64), w)[0]
        Lf = L[np.isfinite(L)]
        n_pool += Lf.size
        kept.append(keep_tail(Lf, prc, m_tail))
        del L, Lf
        if job:
            job.tick("ied detect", j + 1)
    del N
    thr = prctile_from_tail(np.concatenate(kept), n_pool, prc, m_tail)
    del kept
    Li = np.zeros((len(det), n2), dtype=bool)
    for j in range(len(det)):
        L = linelength(D[j][None, :].astype(np.float64), w)[0]
        with np.errstate(invalid="ignore"):
            Li[j] = L > thr

    ets, ech = _storm_events(Li, w, fsw, merge_s, min_s, k_min)
    del Li
    stamps = _stamp_at_peak(ets, D, ech)
    det_want = [want[k] for k in det]
    out = _summarise(session, spec, report, plan, det_want, ets, ech, stamps,
                     D, fsw, thr, prc, llw, q=q, fs_native=fs)
    out["params"].update({
        "method": "storm",
        "detector": "Storm line length (validated on the PTEN hand-sorts)",
        "car": bool(spec.get("car")),
        "car_groups": len(car_groups(numbers, spec.get("banks")))
        if spec.get("car") else 0,
        "fs_work": fsw,
        "min_channels": k_min,
        "detect_on": rule,
        "read_channels": numbers,
        "not_connected": sorted(nc),
        "display": "as the detector saw it: common-average referenced, "
                   "notched, band-passed" if spec.get("car") else
                   "as the detector saw it",
    })
    return out


def _storm_events(Li, w, fsw, merge_s, min_s, k_min):
    """LLspikedetector's event logic at the working rate, then the channel rule.

    Returns (ets, ech) in the shapes the Legacy path hands `_summarise`:
    `ets` 1-based [on, off] sample indices at the working rate, already
    shifted by half the line-length window as the .m file shifts them, and
    `ech` events x detection-channels participation.
    """
    n_ch = Li.shape[0]
    a = Li.any(axis=0)
    if not a.any():
        return (np.zeros((0, 2), dtype=np.int64),
                np.zeros((0, n_ch), dtype=bool))
    da = np.diff(a.astype(np.int8))
    on = np.flatnonzero(da == 1) + 1                    # 0-based, inclusive
    off = np.flatnonzero(da == -1)
    if a[0]:
        on = np.concatenate([[0], on])
    if a[-1]:
        off = np.concatenate([off, [a.size - 1]])
    ech = np.zeros((on.size, n_ch), dtype=bool)
    for i in range(on.size):
        ech[i] = Li[:, on[i]:off[i] + 1].any(axis=1)
    shift = int(round(w / 2.0))
    ets = np.stack([on + 1 + shift, off + 1 + shift], axis=1).astype(np.int64)
    # Sequential merge, as written: a gap shorter than merge_s joins the event
    # to the one before, and a chain of short gaps joins them onto the first.
    if ets.shape[0] > 1:
        gap = ets[1:, 0] - ets[:-1, 1]
        start = np.concatenate([[True], gap >= merge_s * fsw])
        first = np.flatnonzero(start)
        last = np.concatenate([first[1:] - 1, [ets.shape[0] - 1]])
        ets = np.stack([ets[first, 0], ets[last, 1]], axis=1)
        ech = np.logical_or.reduceat(ech, first, axis=0)
    keep = ((ets[:, 1] - ets[:, 0]) >= min_s * fsw) & \
        (ech.sum(axis=1) >= k_min)
    return ets[keep], ech[keep]


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
               fs, thr, prc, llw, q=1, fs_native=None):
    """`fs` is the rate `ets`, `stamps` and `traces` are at; `q` is how many
    native samples one of them is, so a stamp is placed on the recording's
    own clock at the native rate whatever rate the detector worked at."""
    fs_native = float(fs_native or fs)
    numbers = [int(c["number"]) for c in want]
    span = float(plan["span_s"]) or 1.0
    half = int(round(SNIPPET_MS / 1000.0 * fs / 2.0))

    events, kept_rows = [], []
    for i in range(ets.shape[0]):
        # Sample indices, not seconds, and `sample_to_true` rather than
        # `concat_to_true`: the latter is exact only to the segment and
        # returns a (seconds, segment) PAIR. `stamps` is 0-based; `ets` is
        # the MATLAB's 1-based, so its offset is one sample earlier.
        t = _true_at(report, int(stamps[i]) * q, fs_native)
        t_end = _true_at(report, (int(ets[i, 1]) - 1) * q, fs_native)
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
            if ets.shape[0] >= SUSPECT_MIN_EVENTS and \
                    row["n"] >= SUSPECT_FRAC * ets.shape[0]:
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
            "channel_range": spec.get("channel_range"),
            "out_of_range": list(spec.get("out_of_range") or []),
            "preset": spec.get("preset"),
            "stamp": "peak",
            "method": spec.get("method") or "legacy",
            "merge_s": float(spec.get("merge_s") or MERGE_S),
            "min_event_s": float(spec.get("min_event_s") or MIN_EVENT_S),
            "gap_map_sha": report.get("gap_map_sha"),
        },
    }
