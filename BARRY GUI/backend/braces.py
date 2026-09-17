"""
braces.py -- putting every dentate spike stamp on the peak it belongs to.

Braces move teeth into the position they should already have been in. This
moves stamps, and for the same reason: the event is real and correctly
called, it is just not quite where the record says it is.

WHERE THE JITTER COMES FROM
---------------------------
A stamp is only as good as the trace it was measured against. A set detected
on CSC38 and read back against CSC41 is a few milliseconds out, because
adjacent sites on a shank see the same spike at slightly different times and
amplitudes. A set that came through Toothy was measured on a 1 kHz grid built
over a nominal rate. A set imported from a snapshot folder has whatever time
was in the file name. None of that is wrong enough to notice one event at a
time, and all of it is wrong enough to smear an average across a thousand.

WHAT THIS IS NOT
----------------
Not a detector. The set already says these are dentate spikes -- somebody
went through them one at a time in Checkup and said so. The only question
here is WHERE each one is, and the answer is never "nowhere": a stamp this
cannot place stays exactly where it was and is flagged. Nothing is dropped,
nothing is invented, and no label is ever read, let alone changed.

TWO DELIBERATE DIFFERENCES FROM INCISOR
---------------------------------------
**Magnitude, not the signed trace.** `incisor._detect` runs `find_peaks` on
the signed trace, which is why polarity is a correctness question there and
not a preference (`incisor.py`, "TWO THINGS THAT WOULD BE SILENTLY WRONG").
A stamp that arrived from Toothy, from a snapshot folder, or from somebody's
hand may sit on a trough. `|x|` finds the event under either convention, and
is the one measure that does not care which tool produced the stamp.

**A lower floor.** Detection asks *is anything here*; alignment asks *where
is the thing we already know is here*. Making the peak clear 4.5 SD a second
time would strand real events whose peak on THIS channel is a little smaller
-- and this channel is often not the one detection ran on. The floor is a
fraction of the set's own detection threshold, so it travels with the
parameters the set was made with rather than being a new magic number.

THE RULE, WHICH IS THE INTERESTING PART
---------------------------------------
Nearest-peak-wins is wrong, and wrong in a way that quietly loses events.
Take two stamps and two peaks, where the first stamp sits between the peaks
nearer the later one, and the second stamp can only reach the later one:

    peak A          stamp 1   peak B      stamp 2
    27.800          27.894    27.920      27.955

Nearest-peak-wins gives B to stamp 1 (26 ms away), and stamp 2 -- a real,
curated dentate spike -- is left with nothing, because A is 155 ms behind it.
The right answer moves stamp 1 FURTHER, to A, so that stamp 2 can have B.

So the objective is not "move as little as possible". It is, in this order:

    1. match as many stamps as possible
    2. among the ways of doing that, move them the least in total

subject to three constraints:

    a stamp takes at most one peak
    a peak is taken by at most one stamp
    the assignment does not cross

The second constraint is what stops alignment manufacturing duplicates: two
stamps snapped onto one peak are two events at an identical time, which
`eventbank.DUP_DP` would then make somebody resolve by hand at 0.1 ms. The
third is about labels. Labels travel with stamps, so if stamp 2 could take
peak A while stamp 1 took peak B, two events would swap places and their
curation calls would follow them -- a Garbage and a Dentate Spike trading
identities. Events in a recording do not reorder, so neither may this.

HOW IT IS COMPUTED
------------------
Not as one global problem. Stamps and peaks are both sorted, and "within the
window" is an interval condition, so the candidate graph falls apart into
contiguous RUNS that cannot affect one another. Almost every run is one stamp
and one or two peaks and is settled by inspection; the rest get a small
dynamic program over the run alone.
"""
from __future__ import annotations

import bisect
import math

import numpy as np

from . import continuity, csc, incisor

try:
    from scipy import signal as _sig
    HAVE_SCIPY = True
except Exception:                                        # noqa: BLE001
    _sig = None
    HAVE_SCIPY = False


# --------------------------------------------------------------------------
# The numbers
# --------------------------------------------------------------------------
# How far a stamp may move. Yours: wide enough for the jitter actually seen,
# narrow enough that a stamp cannot reach the next spike in a burst. It is
# also, deliberately, the same size as the detector's own peak spacing --
# which is why a stamp can have two peaks in reach and never three.
WINDOW_MS = 100.0

# The alignment floor, as a fraction of the set's own detection threshold.
# See the note at the top: the event is already known to be an event.
FLOOR_FRAC = 0.5

# A move this far out of the window is as likely to be the next spike as
# this one. Flagged rather than refused -- a window is a guess about jitter,
# not a measurement of it, and the person looking can tell.
EDGE_FRAC = 0.8

# Below this, a stamp counts as having been right already. One millisecond
# is one sample at the rate everything here is decimated to, so a "move"
# smaller than this is not a move.
SAME_MS = 1.0

# Half a microsecond. Every time here has been rounded to six decimal places
# on the way out of `continuity.sample_to_true`, so two times closer than
# this are the same instant -- and without it a stamp exactly one window from
# its peak falls outside by a rounding error. Measured: 50.0 + 0.1 is
# 50.100000000000001, and a peak stored as 50.1 is 50.099999999999994, so
# "exactly 100 ms away" was out of reach.
EPS_S = 5e-7

# A safety valve, not a tuning knob. Runs are small in every real set --
# measured at 4x5 on a 1224-event recording -- but a set with hand-added
# stamps packed tighter than the detector's spacing could in principle chain
# a long one, and the DP is O(k*l). Past this many cells the run is split at
# its widest internal gap, which is the least-interacting place to cut.
MAX_RUN_CELLS = 250_000


class BracesError(Exception):
    """A refusal the user should read, not a crash."""


# --------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------
def window_s(window_ms):
    """The window in seconds, with the rounding slack. One place, because
    `assign`, `nearest` and `greedy` must agree on what is in reach or they
    disagree about which stamps were contested."""
    return float(window_ms) / 1000.0 + EPS_S


def reach(stamps, peaks, window):
    """For each stamp, the half-open range of peak indices within `window`.

    `bisect` rather than a scan: both sequences are sorted, and a set with a
    thousand stamps against twenty thousand peaks is the ordinary case.
    """
    out = []
    for t in stamps:
        lo = bisect.bisect_left(peaks, t - window)
        hi = bisect.bisect_right(peaks, t + window)
        out.append((lo, hi))
    return out


def runs(stamps, peaks, window):
    """Split into groups that cannot affect one another.

    Two consecutive stamps interact only if they can reach a common peak.
    Where they cannot, the earlier one's choice is invisible to the later
    one -- the non-crossing rule is then satisfied automatically, because
    every peak the first can reach is before every peak the second can.

    Transitive, and therefore safe to decide pairwise: `lo` and `hi` are
    non-decreasing because the stamps are sorted, so if stamp i and i+1 are
    disjoint then so are i and i+2.

    Yields (stamp_lo, stamp_hi, peak_lo, peak_hi), all half-open.
    """
    span = reach(stamps, peaks, window)
    n = len(stamps)
    i = 0
    while i < n:
        j = i + 1
        p_lo, p_hi = span[i]
        while j < n and span[j][0] < p_hi:
            p_lo = min(p_lo, span[j][0])
            p_hi = max(p_hi, span[j][1])
            j += 1
        yield (i, j, p_lo, p_hi)
        i = j


def _solve_run(stamps, peaks, window):
    """The assignment for one run, as a peak index or None per stamp.

    The dynamic program is the rule, written out. `C[i][j]` is the best
    result over the first `i` stamps and the first `j` peaks, as the tuple
    (stamps left unmatched, total seconds moved) -- compared
    lexicographically, which is what makes the count beat the distance
    without a penalty constant that would have to be tuned and could be
    wrong.
    """
    k, l = len(stamps), len(peaks)
    if not k:
        return []
    if not l:
        return [None] * k

    # Nothing matched, nothing moved: the starting corner.
    prev = [(0, 0.0)] * (l + 1)
    # Which transition produced each cell: 0 stamp unmatched, 1 peak unused,
    # 2 matched. Kept for every cell because the answer is the path, not the
    # cost, and the path cannot be recovered from the costs alone.
    back = []
    for i in range(1, k + 1):
        t = stamps[i - 1]
        row = [(prev[0][0] + 1, prev[0][1])]     # j = 0: stamp i unmatched
        brow = [0] * (l + 1)
        for j in range(1, l + 1):
            # Stamp i takes nothing.
            best = (prev[j][0] + 1, prev[j][1])
            bk = 0
            # Peak j goes unused.
            cand = row[j - 1]
            if cand < best:
                best, bk = cand, 1
            # Matched, if it is in reach at all.
            d = abs(t - peaks[j - 1])
            if d <= window:
                up = prev[j - 1]
                cand = (up[0], up[1] + d)
                if cand < best:
                    best, bk = cand, 2
            row.append(best)
            brow[j] = bk
        back.append(brow)
        prev = row

    out = [None] * k
    i, j = k, l
    while i > 0:
        if j == 0:
            i -= 1                      # nothing left to take
            continue
        bk = back[i - 1][j]
        if bk == 2:
            out[i - 1] = j - 1
            i -= 1
            j -= 1
        elif bk == 1:
            j -= 1
        else:
            i -= 1
    return out


def _split_point(stamps):
    """Where to cut an oversized run: the widest gap between stamps.

    The least-interacting place there is. Two stamps far apart share the
    fewest peaks, so a cut there changes the answer least -- and on any run
    small enough to be real, this is never reached.
    """
    best, at = -1.0, len(stamps) // 2
    for i in range(1, len(stamps)):
        gap = stamps[i] - stamps[i - 1]
        if gap > best:
            best, at = gap, i
    return at


def assign(stamps, peaks, window_ms=WINDOW_MS):
    """Which peak each stamp takes, or None. The whole rule, top to bottom.

    `stamps` and `peaks` are ascending lists of seconds. The result is one
    entry per stamp, an index into `peaks` or None, and it is guaranteed to
    be strictly increasing over the entries that are not None -- which is
    what keeps the aligned set in time order.
    """
    window = window_s(window_ms)
    stamps = list(stamps)
    peaks = list(peaks)
    out = [None] * len(stamps)
    if not stamps or not peaks:
        return out

    todo = list(runs(stamps, peaks, window))
    while todo:
        s_lo, s_hi, p_lo, p_hi = todo.pop()
        k, l = s_hi - s_lo, p_hi - p_lo
        if not k or not l:
            continue
        if k * l > MAX_RUN_CELLS and k > 1:
            at = s_lo + _split_point(stamps[s_lo:s_hi])
            # Re-derive each half's peaks rather than halving the range: the
            # cut moves which peaks are reachable, and a half that kept the
            # whole range could hand the same peak to both.
            for lo, hi in ((s_lo, at), (at, s_hi)):
                if hi > lo:
                    sub = reach(stamps[lo:hi], peaks, window)
                    todo.append((lo, hi, min(x[0] for x in sub),
                                 max(x[1] for x in sub)))
            continue
        got = _solve_run(stamps[s_lo:s_hi], peaks[p_lo:p_hi], window)
        for n, j in enumerate(got):
            out[s_lo + n] = None if j is None else p_lo + j
    return out


def nearest(stamps, peaks, window_ms=WINDOW_MS):
    """The closest in-window peak to each stamp, ignoring who else wants it.

    NOT what a greedy aligner would produce -- see `greedy` for that. This is
    the question "was there something closer", and a stamp whose assigned
    peak is not this one gave up a closer peak so its neighbour could have
    one. That is the contested flag, and it is the only flag that reports a
    decision the tool actually made rather than a measurement.
    """
    window = window_s(window_ms)
    out = []
    for n, (lo, hi) in enumerate(reach(stamps, peaks, window)):
        if lo >= hi:
            out.append(None)
            continue
        t = stamps[n]
        out.append(min(range(lo, hi), key=lambda j: abs(t - peaks[j])))
    return out


def greedy(stamps, peaks, window_ms=WINDOW_MS):
    """What nearest-peak-wins would actually have produced.

    Each stamp in turn takes the closest peak still free. Kept because the
    summary reports what the rule bought -- "nearest-peak-wins would have
    stranded 14 of these" is the one number that justifies moving stamps
    further than they had to go, and it is not a number anybody would
    believe without it being counted.
    """
    window = window_s(window_ms)
    used = set()
    out = []
    for n, (lo, hi) in enumerate(reach(stamps, peaks, window)):
        free = [j for j in range(lo, hi) if j not in used]
        if not free:
            out.append(None)
            continue
        t = stamps[n]
        pick = min(free, key=lambda j: abs(t - peaks[j]))
        used.add(pick)
        out.append(pick)
    return out


# --------------------------------------------------------------------------
# Reading the channel
# --------------------------------------------------------------------------
def channel_peaks(session, ch, report, spec, job=None, on_read=None):
    """Every DS-band magnitude peak on one channel, on the recording's clock.

    The read is `incisor._segment_traces` and the filter is
    `incisor._filtered`, both used as they are rather than re-derived --
    everything those two know about chunk edges, decimation phase and
    segment stitching is the reason a stamp made here lands on the same
    sample Toothy would have put it on.

    What differs is three lines: the threshold is scaled by `floor_frac`,
    the peaks are found on `|x|`, and nothing is rejected on shape.
    """
    if not HAVE_SCIPY:
        raise BracesError(
            "SciPy is not installed on this machine, so no filtering or "
            "peak finding can be done here.")

    fs = float(report.get("fs") or session.get("fs") or 30000.0)
    q = incisor.decimation_for(fs, float(spec.get("lfp_fs") or incisor.LFP_FS))
    lfp_fs = fs / q
    band = spec.get("band") or incisor.DS_BAND

    segs = incisor._segment_traces(session, ch, report, spec, job, on_read)
    if not segs:
        raise BracesError(
            "Nothing readable on CSC%s, so there are no peaks to align to."
            % ch.get("number"))

    ds = [(i, start, incisor._filtered(tr, lfp_fs, band))
          for i, start, tr in segs]
    pooled = np.concatenate([f for _, _, f in ds])

    # The SAME threshold Incisor would set on this channel, so "weak peak"
    # means weak by the detector's own standard rather than by one invented
    # here. The floor for FINDING peaks is a fraction of it; the threshold
    # itself is kept, and is what a peak is called weak against.
    thr = incisor.threshold_for(pooled,
                                spec.get("height_sd", incisor.DS_HEIGHT_SD),
                                spec.get("abs_uv", incisor.DS_ABS_THR_UV),
                                spec.get("estimator") or "sd")
    if not math.isfinite(thr["thr_uv"]) or not math.isfinite(thr["sd_uv"]):
        n_bad = int(np.count_nonzero(~np.isfinite(pooled)))
        raise BracesError(
            "CSC%s's filtered trace is not all numbers (%d of %d samples), "
            "so no floor can be set from it."
            % (ch.get("number"), n_bad, pooled.size))

    frac = float(spec.get("floor_frac", FLOOR_FRAC))
    floor = (float(spec["floor_uv"]) if spec.get("floor_uv")
             else thr["thr_uv"] * frac)
    dist = max(1, int(round(lfp_fs * float(spec.get("dist_ms",
                                                    incisor.DS_DIST_MS))
                            / 1000.0)))

    times, amps = [], []
    for seg_i, start_concat, f in ds:
        if job:
            job.check()
        mag = np.abs(f)
        idx, props = _sig.find_peaks(mag, height=floor, distance=dist)
        heights = props.get("peak_heights",
                            mag[idx] if idx.size else np.array([]))
        for n in range(idx.size):
            j = int(idx[n])
            # The decimated index back to a full-rate index in the whole
            # recording, then to a time through the breakpoint map. The same
            # single place a time is made in `incisor._channel_pass`, and it
            # never assumes a linear axis.
            t = continuity.sample_to_true(report, start_concat + j * q)
            if t is None:
                continue
            times.append(round(float(t), 6))
            amps.append(round(float(heights[n]), 3))

    # Sorted together. Segments arrive in order and peaks within a segment
    # are in order, so this is already true -- asserted by construction
    # rather than trusted, because `assign` is only correct on sorted input
    # and a silently unsorted peak list would mis-align quietly.
    order = sorted(range(len(times)), key=lambda i: times[i])
    times = [times[i] for i in order]
    amps = [amps[i] for i in order]

    return {
        "times": times,
        "amps": amps,
        "floor_uv": round(float(floor), 3),
        "floor_source": ("given" if spec.get("floor_uv")
                         else "%g of %s (%.0f uV)"
                              % (frac, thr["thr_source"], thr["thr_uv"])),
        "thr_uv": round(float(thr["thr_uv"]), 3),
        "sd_uv": round(float(thr["sd_uv"]), 3),
        "thr_source": thr["thr_source"],
        "estimator": thr["estimator"],
        "lfp_fs": lfp_fs,
        "band": list(band),
        "dist_ms": float(spec.get("dist_ms", incisor.DS_DIST_MS)),
        "n_peaks": len(times),
        "channel": int(ch["number"]),
    }


# --------------------------------------------------------------------------
# The proposal
# --------------------------------------------------------------------------
# Every reason a row is not confirmed on arrival. Named here rather than
# spelled at each site, so the panel's filter pills, the version record's
# counts and the CSV all say the same words.
REASONS = {
    "no_peak": "no peak in reach",
    "edge": "near the edge",
    "contested": "not the nearest peak",
    "weak": "weak peak",
}


def propose(events, peaks, window_ms=WINDOW_MS, edge_frac=EDGE_FRAC,
            same_ms=SAME_MS, align_ids=None):
    """One row per event: where it was, where it goes, and whether to ask.

    `events` is the banked list -- dicts with a `start` -- and is NOT
    required to be sorted, because a bank entry's order is whatever last
    wrote it. The rule needs sorted stamps, so it is sorted here and the
    rows come back in the original order with their original index on them.

    ONLY THE DENTATE SPIKES. `align_ids` is the set of label ids that name a
    real event -- `{"spike"}` for the DS vocabulary, which is the one label
    carrying `good: True`. Everything else in a curated set is a candidate
    somebody looked at and REJECTED: Garbage, or a Flag nobody has settled.

    Leaving them in would be wrong twice. Moving a Garbage stamp onto a peak
    asserts a position for something that is not an event. Worse, and this
    is the real fault: one peak per stamp means a Garbage stamp sitting near
    a real spike would TAKE that spike's peak, and the spike would be
    stranded or pushed onto the wrong one. So they are excluded from the run
    entirely rather than filtered out of the answer afterwards -- they must
    not be able to compete for a peak in the first place.

    They are not touched and not lost: they simply get no row, so `resolve`
    never puts them in `moves` and `EventBank.align` writes them unchanged.

    `align_ids=None` means align everything, which is what the rule's own
    checks use -- they are about the arithmetic and have no labels at all.
    """
    rows, skipped = [], {}
    for i, ev in enumerate(events or []):
        try:
            t = float(ev.get("start"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(t):
            continue
        if align_ids is not None:
            lab = ev.get("label_id") or ev.get("label")
            if lab not in align_ids:
                key = lab or "undecided"
                skipped[key] = skipped.get(key, 0) + 1
                continue
        rows.append({"i": i, "was": t})
    if not rows:
        return dict(summarize([], peaks, window_ms, edge_frac, same_ms),
                    skipped=skipped, n_skipped=sum(skipped.values()))

    rows.sort(key=lambda r: r["was"])
    stamps = [r["was"] for r in rows]
    p_times = list(peaks.get("times") or [])
    p_amps = list(peaks.get("amps") or [])
    thr_uv = float(peaks.get("thr_uv") or 0.0)

    taken = assign(stamps, p_times, window_ms)
    closest = nearest(stamps, p_times, window_ms)
    # What the naive tool would have produced, for the one line of the
    # summary that says why this one is worth its extra machinery.
    naive = greedy(stamps, p_times, window_ms)

    edge_s = float(window_ms) * float(edge_frac) / 1000.0
    same_s = float(same_ms) / 1000.0

    for n, row in enumerate(rows):
        j = taken[n]
        row["peak"] = j
        if j is None:
            row["now"] = row["was"]
            row["shift_ms"] = None
            row["peak_uv"] = None
            row["flag"] = "no_peak"
            row["moved"] = False
            row["same"] = False
            continue
        now = p_times[j]
        d = now - row["was"]
        row["now"] = now
        row["shift_ms"] = round(d * 1000.0, 3)
        row["peak_uv"] = p_amps[j] if j < len(p_amps) else None
        row["same"] = abs(d) < same_s
        row["moved"] = not row["same"]
        flag = None
        # Order matters: a stamp that had to give up a nearer peak is the
        # only flag that reports a DECISION, so it outranks the two that
        # merely report a measurement.
        if closest[n] is not None and closest[n] != j:
            flag = "contested"
        elif abs(d) > edge_s:
            flag = "edge"
        elif (row["peak_uv"] is not None and thr_uv
              and row["peak_uv"] < thr_uv):
            flag = "weak"
        row["flag"] = flag

    # Strictly increasing over what was matched. Guaranteed by the
    # non-crossing rule, and checked anyway: if it ever failed, the set and
    # the bank would stop lining up and nothing else would notice.
    last = None
    for row in rows:
        if row["peak"] is None:
            continue
        if last is not None and row["now"] <= last:
            raise BracesError(
                "The alignment put two stamps at or past one another "
                "(%.6f then %.6f). Nothing was written." % (last, row["now"]))
        last = row["now"]

    # What the rule bought, counted rather than asserted.
    stranded = sum(1 for n in range(len(rows))
                   if naive[n] is None and taken[n] is not None)
    return dict(summarize(rows, peaks, window_ms, edge_frac, same_ms,
                          greedy_stranded=stranded),
                skipped=skipped, n_skipped=sum(skipped.values()))


def summarize(rows, peaks, window_ms, edge_frac, same_ms,
              greedy_stranded=0):
    """The counts the panel leads with, and the shift histogram."""
    moved = [r for r in rows if r["moved"]]
    shifts = [r["shift_ms"] for r in moved if r["shift_ms"] is not None]
    flagged = [r for r in rows if r.get("flag")]
    by_reason = {}
    for r in flagged:
        by_reason[r["flag"]] = by_reason.get(r["flag"], 0) + 1

    # Twenty bins across the window, both signs. The panel draws this before
    # it draws the table, because "is this channel right" comes before "is
    # this stamp right": one lobe off zero is a systematic offset and is
    # what the tool is for, and a flat smear is a wrong channel.
    nbins = 20
    lo, hi = -float(window_ms), float(window_ms)
    hist = [0] * nbins
    step = (hi - lo) / nbins
    for s in shifts:
        b = int((s - lo) / step)
        hist[min(nbins - 1, max(0, b))] += 1

    arr = sorted(abs(s) for s in shifts)

    def pct(p):
        if not arr:
            return 0.0
        return round(arr[min(len(arr) - 1, int(p * (len(arr) - 1)))], 3)

    med = 0.0
    if shifts:
        srt = sorted(shifts)
        mid = len(srt) // 2
        med = (srt[mid] if len(srt) % 2 else (srt[mid - 1] + srt[mid]) / 2.0)

    return {
        "rows": rows,
        "n": len(rows),
        "n_moved": len(moved),
        "n_same": sum(1 for r in rows if r.get("same")),
        "n_no_peak": sum(1 for r in rows if r["peak"] is None),
        "n_flagged": len(flagged),
        "by_reason": by_reason,
        # How many of these a nearest-peak-wins tool would have left behind.
        "greedy_stranded": int(greedy_stranded),
        "shift_median_ms": round(med, 3),
        "shift_p95_ms": pct(0.95),
        "shift_max_ms": round(arr[-1], 3) if arr else 0.0,
        "hist": hist,
        "hist_lo_ms": lo,
        "hist_hi_ms": hi,
        "window_ms": float(window_ms),
        "edge_frac": float(edge_frac),
        "same_ms": float(same_ms),
        "n_peaks": len(peaks.get("times") or []),
        "floor_uv": peaks.get("floor_uv"),
        "floor_source": peaks.get("floor_source"),
        "thr_uv": peaks.get("thr_uv"),
        "channel": peaks.get("channel"),
        "band": peaks.get("band"),
        "dist_ms": peaks.get("dist_ms"),
        "estimator": peaks.get("estimator"),
    }


def params_of(spec, peaks):
    """What was asked, for the record and for the cache key.

    Only the settings that change the numbers. Which version supplied the
    stamps is not one of them -- that is lineage, and it is recorded
    separately on the version itself.
    """
    return {
        "channel": peaks.get("channel"),
        "band": list(peaks.get("band") or incisor.DS_BAND),
        "order": incisor.DS_ORDER,
        "measure": "abs",
        "window_ms": float(spec.get("window_ms", WINDOW_MS)),
        "dist_ms": float(peaks.get("dist_ms") or incisor.DS_DIST_MS),
        "floor_uv": peaks.get("floor_uv"),
        "estimator": peaks.get("estimator"),
        "lfp_fs": round(float(peaks.get("lfp_fs") or incisor.LFP_FS), 4),
        "invert": bool(spec.get("invert", True)),
    }
