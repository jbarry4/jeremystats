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

THREE DELIBERATE DIFFERENCES FROM INCISOR
-----------------------------------------
**The whole shank at once, not one channel.** Incisor detects per channel and
then picks the hilus, because detection is a question about a site. Alignment
is not. A dentate spike is a population event -- it appears across most of
the shank at the same instant, largest near the hilus and smaller either side
-- so the instant it happened is best estimated from the whole probe, not
from whichever electrode somebody detected on six months ago.

The measure is the mean |filtered| ACROSS CHANNELS, as one trace: at each
moment, how much dentate-spike-band activity there was anywhere on the probe.
One noisy wire cannot carry that and a dead one cannot sink it. Measured on
M8s9feb8, the best and second-best single channels scored within 0.3% of each
other -- which is another way of saying that picking one of them was close to
arbitrary, and that the question was never about a channel.

**The CSD, not the voltage.** A voltage raster at any one site is mostly
what is happening somewhere else: the field spreads, so a sink two hundred
microns away shows up almost as strongly as one on the contact. Averaging
|V| across a shank therefore measures the loudest event anywhere near the
probe, and its peak sits wherever the volume conduction happens to be
largest rather than where the current actually went.

The current source density is the second spatial derivative across depth,
which is exactly the part that cannot be volume-conducted. A dentate spike
is a current sink in the hilus; on CSD that is a sharp, local thing with a
real position, and the instant it peaks is the instant the event happened.
`csc.compute_csd` is the same function the CSD panel draws from -- one
derivative in this codebase, not two that could disagree about a sign.

Rectified before averaging, for the same reason the voltage version was: a
signed sum across a probe cancels, because a sink at one depth is a source
at the next. And rectifying is what makes the measure indifferent to which
polarity convention produced the stamps in the first place.

**No threshold at all.** Detection asks *is anything here*; alignment asks
*where is the thing we already know is here*. `distance` already makes a peak
the largest thing within a hundred milliseconds of itself, so every peak
found here is a candidate a stamp could sensibly move to. A height on top of
that can only remove the right answer -- for a real event that happens to be
small, which is the case alignment exists to handle. The profile's own 4.5 SD
is still computed, so a row can say "smaller than a detector would have called
an event", but nothing is gated on it.

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

from . import continuity, csc, incisor, probes

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

# A move this far out of the window is as likely to be the next spike as
# this one. Flagged rather than refused -- a window is a guess about jitter,
# not a measurement of it, and the person looking can tell.
EDGE_FRAC = 0.8

# How far from what this set typically did before a move is worth a look.
#
# The fixed "near the edge" rule is about the WINDOW -- it catches a stamp
# that went almost as far as it was allowed to. It says nothing when a set's
# jitter is small: measured on M8s9feb8, the median move is 5.6 ms and the
# largest is 59.7, and at a window of 100 ms not one of those trips an
# 80 ms edge. The stamp that moved sixty is still the one worth looking at.
#
# So this is measured against the set's own spread, robustly: the median
# absolute deviation, scaled to a standard deviation the way `analysis.py`
# and `incisor.threshold_for(estimator="mad")` both do it. Six of those is
# far enough out to be about this event rather than about the recording.
OUTLIER_MADS = 6.0

# ...but not for a set whose moves are all within a millisecond of each
# other, where six MADs is a fraction of a sample and every stamp is an
# outlier. Nothing closer to the median than this is ever unusual.
OUTLIER_FLOOR_MS = 8.0

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

# How close two candidate peaks may be.
#
# NOT the detector's `dist_ms`. That is 100 ms and exists to stop one event
# being counted twice; here it would mean the candidate list can hold one
# peak per hundred milliseconds while the window a stamp may move in is also
# a hundred -- so a stamp whose own peak sits 40 ms from a neighbour's cannot
# be given it, because the list does not contain both, and the assignment has
# to put it somewhere else. That is a stamp landing away from the feature
# anybody can see on the screen.
#
# Twelve milliseconds is under the width of a dentate spike, so two distinct
# peaks this far apart are two distinct deflections. Contention between them
# is then settled by the assignment -- one peak per stamp, no crossing --
# which is the part of this that is built to decide it.
#
# Spacing is the only thing gating a candidate now. A floor was tried --
# the detector's own 4.5 SD -- and it is not what
# `dentate_spike_aligner.py` does: that takes the largest thing in the
# window whatever its height, and a stamp with nothing big enough nearby
# gets moved rather than left alone. The trade is real in both directions
# and is written down in the notes rather than hidden in a default.
CAND_DIST_MS = 12.0

# The mains, which is inside the band and has to come out of it.
#
# THE SINGLE BIGGEST THING THAT WAS WRONG HERE. The dentate-spike band is
# 5-100 Hz; sixty hertz is inside it. A current source density is a second
# spatial DIFFERENCE, which does nothing whatever to reject a signal common
# to every contact but not quite equal on them -- so the mains survives into
# exactly the measure this tool aligns on. Measured on M1ptens2oct2 over a
# clean thirty seconds: the 60.06 Hz line in the CSD sits 5,950 times above
# the power either side of it, 1.7e8 against 2.9e4. The trace peaks were
# being picked from was, to a first approximation, a 60 Hz sine wave with a
# dentate spike riding on it.
#
# And one mains period is 16.7 ms while CAND_DIST_MS is 12 -- just under it
# -- so `find_peaks` resolved individual MAINS CYCLES as candidates and
# "nearest peak" snapped the stamp onto one. The corrections were quantised
# to the mains period and were not about the event at all. Notching 60 Hz
# alone took the old rule from placing 6 of 64 stamps to 26, and from making
# the average slightly WORSE than doing nothing to clearly better.
#
# Q=30 is about two hertz wide: narrow enough that a broadband transient
# loses almost nothing, and zero-phase, so it cannot shift the thing being
# timed. 120 Hz is outside the band and measures at 1.0x its neighbours, so
# only the fundamental is taken out.
LINE_HZ = 60.0
LINE_Q = 30.0

# Screening the contacts, over one clean stretch rather than per window.
#
# A CSD does not merely include a bad contact, it AMPLIFIES it: a dead wire
# between two live ones produces the largest deflection anywhere on the
# probe. Anything that then picks a depth, or a peak, by magnitude picks
# that. Measured on M1ptens2oct2: CSC59 is dead at 0.4 uV against a median
# of 60, and the depth pass duly returned a band centred on it -- CSC47-62,
# when the event is at CSC38-53.
#
# Judged against the other contacts rather than an absolute microvolt
# figure, because amplitude differs per preparation.
SCREEN_DUR_S = 30.0
DEAD_FRAC = 0.2          # below this fraction of the median sd = dead
NOISE_MADS = 4.0         # this many MADs above the median log sd = noisy

# Half-width of the event template, in milliseconds. A dentate spike is
# 10-20 ms wide, so +-25 ms holds the whole deflection and its immediate
# flanks without reaching the next event.
TMPL_MS = 25.0

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


def _solve_run(stamps, peaks, window, amps=None, top=0.0):
    """The assignment for one run, as a peak index or None per stamp.

    The dynamic program is the rule, written out. `C[i][j]` is the best
    result over the first `i` stamps and the first `j` peaks, as the tuple
    (stamps left unmatched, total cost) -- compared lexicographically,
    which is what makes the count beat everything else without a penalty
    constant that would have to be tuned and could be wrong.

    WHAT THE COST IS depends on what the caller is aligning to. With no
    `amps` it is seconds moved, and the rule reads "the nearest peak".
    With `amps` it is `top - amplitude`, and the rule reads "the largest
    peak in the window" -- which is what an aligner does when its candidate
    list is every local maximum of a curve rather than a short list of
    events. Both are non-negative, which is all the lexicographic
    comparison needs.

    The first term is untouched either way, and that is where the edge case
    lives: a stamp between two peaks and another after it that can only
    reach the later one means the first must take the earlier, or one of
    them goes unmatched and the count is worse.
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
                cost = d if amps is None else (top - amps[j - 1])
                up = prev[j - 1]
                cand = (up[0], up[1] + cost)
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


def assign(stamps, peaks, window_ms=WINDOW_MS, amps=None):
    """Which peak each stamp takes, or None. The whole rule, top to bottom.

    `stamps` and `peaks` are ascending lists of seconds. The result is one
    entry per stamp, an index into `peaks` or None, and it is guaranteed to
    be strictly increasing over the entries that are not None -- which is
    what keeps the aligned set in time order.

    `amps`, one per peak, switches the rule from "the nearest peak in the
    window" to "the largest" -- see `_solve_run`. Everything else about the
    assignment is the same, including the part that matters most: no two
    stamps are ever given the same peak.
    """
    window = window_s(window_ms)
    stamps = list(stamps)
    peaks = list(peaks)
    amps = list(amps) if amps is not None else None
    if amps is not None and len(amps) != len(peaks):
        raise BracesError(
            "There are %d peaks and %d heights for them, which means the "
            "two lists are not about the same peaks."
            % (len(peaks), len(amps)))
    top = (max(amps) if amps else 0.0)
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
        got = _solve_run(stamps[s_lo:s_hi], peaks[p_lo:p_hi], window,
                         None if amps is None else amps[p_lo:p_hi], top)
        for n, j in enumerate(got):
            out[s_lo + n] = None if j is None else p_lo + j
    return out


def biggest(stamps, peaks, amps, window_ms=WINDOW_MS):
    """The tallest in-window peak for each stamp, ignoring who else wants it.

    The same question `nearest` asks, for the rule that takes the largest
    peak rather than the closest: what would this stamp have had if it were
    the only one here. A stamp whose assigned peak is not this one gave up
    a taller peak so a neighbour could have it, which is the contested
    flag -- the only flag that reports a decision rather than a
    measurement.
    """
    window = window_s(window_ms)
    out = []
    for t in stamps:
        lo = bisect.bisect_left(peaks, t - window)
        hi = bisect.bisect_right(peaks, t + window)
        if hi <= lo:
            out.append(None)
            continue
        best, at = None, None
        for j in range(lo, hi):
            if best is None or amps[j] > best:
                best, at = amps[j], j
        out.append(at)
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
# How much recording to read either side of a window before filtering it.
#
# A 5 Hz low edge has a 200 ms period, so a Butterworth handed a bare 200 ms
# snippet rings across the whole of it -- and the ringing would land exactly
# where the stamp is. Half a second is two and a half cycles of the low edge
# and is trimmed off before anything is measured. `incisor.EDGE_SECONDS` uses
# a full second for the same reason on whole segments, where it costs
# nothing; here it is paid once per window, so it is measured rather than
# generous. Checked against the whole-recording answer, which is the point of
# having computed that first.
PAD_S = 0.5

# Windows closer together than this are read as one.
#
# Two stamps three seconds apart cost two seeks and two reads either way;
# two stamps 200 ms apart would otherwise be read twice over, with the
# overlap filtered twice and the same peak found twice. Merging also gives
# the filter a longer run to settle in, which is free.
MERGE_GAP_S = 1.0


def _notch(x, fs, spec):
    """Take the mains out of one channel, zero-phase, before anything else.

    Zero-phase because the whole output of this tool is a TIME: a filter
    with phase would shift the thing being timed, by an amount that varies
    with frequency, and the shift would be indistinguishable from the jitter
    it is here to remove.
    """
    if not HAVE_SCIPY:
        return x
    f0 = spec.get("line_hz", LINE_HZ)
    if not f0:
        return x
    q = float(spec.get("line_q") or LINE_Q)
    out = np.asarray(x, dtype=np.float64)
    f = float(f0)
    # Whether or not the band covers it: see `_stack`. The only thing that
    # disqualifies a notch here is being too near Nyquist to be one.
    if 0 < f < 0.95 * (fs / 2.0):
        bn, an = _sig.iirnotch(f, q, fs)
        out = _sig.filtfilt(bn, an, out, axis=-1)
    return out


def screen(session, channels, spec, stamps):
    """Which contacts are unusable, decided once over one clean stretch.

    Returns {channel number: why}, which is a sentence for a person, not a
    code. Nothing is hidden by this: a screened contact is interpolated from
    its neighbours and reported, so the run says what it did.

    The stretch is taken from the middle of the stamps rather than from a
    fixed offset, which is the only way to be sure it is inside a recording
    whose length is not known here. Events are a small fraction of the
    variance in thirty seconds, so "clean" only has to mean "typical".
    """
    if not channels or not stamps:
        return {}
    mid = sorted(stamps)[len(stamps) // 2]
    t0 = max(0.0, mid - SCREEN_DUR_S / 2.0)
    got = _stack(session, channels, spec, t0, t0 + SCREEN_DUR_S)
    if not got:
        return {}
    x = got[0]
    sd = np.asarray(x, dtype=np.float64).std(axis=1)
    if sd.size != len(channels):
        return {}
    med = float(np.median(sd))
    bad = {}
    if med <= 0:
        return {}
    for i, c in enumerate(channels):
        if sd[i] < DEAD_FRAC * med:
            bad[int(c["number"])] = ("dead (%.1f uV against a median of %.0f)"
                                     % (sd[i], med))
    live = np.array([sd[i] for i, c in enumerate(channels)
                     if int(c["number"]) not in bad and sd[i] > 0])
    if live.size > 3:
        lg = np.log10(live)
        m = float(np.median(lg))
        mad = float(np.median(np.abs(lg - m))) * 1.4826
        if mad <= 0:
            mad = float(np.std(lg)) or 1.0
        for i, c in enumerate(channels):
            n = int(c["number"])
            if n in bad or sd[i] <= 0:
                continue
            dev = (float(np.log10(sd[i])) - m) / mad
            if dev > NOISE_MADS:
                bad[n] = "noisy (%.0f uV, %+.1f MAD above the rest)" % (
                    sd[i], dev)
    return bad


def repair(stack, channels, bad):
    """Replace unusable rows by the interpolation of their good neighbours.

    INTERPOLATED, NOT DROPPED, and the difference is not cosmetic. Dropping
    a contact out of the middle leaves the remaining ones unevenly spaced,
    and a second difference over an uneven grid is not a current source
    density -- it is a second difference over an uneven grid, which has a
    step in it exactly where the missing wire was.

    Interpolating keeps the geometry regular and means those rows carry no
    independent information, which is true and is what the depth selection
    is told.
    """
    if not bad:
        return stack
    want = {int(n) for n in bad}
    y = np.array(stack, dtype=np.float64, copy=True)
    good = [i for i, c in enumerate(channels)
            if int(c["number"]) not in want]
    if not good:
        return stack
    for i, c in enumerate(channels):
        if int(c["number"]) not in want:
            continue
        lo = max([g for g in good if g < i], default=None)
        hi = min([g for g in good if g > i], default=None)
        if lo is None:
            y[i] = stack[hi]
        elif hi is None:
            y[i] = stack[lo]
        else:
            w = (i - lo) / float(hi - lo)
            y[i] = (1.0 - w) * stack[lo] + w * stack[hi]
    return y


def _stack(session, channels, spec, t0, t1):
    """Every channel over one stretch, filtered, as [nCh x nSamp].

    Stacked rather than accumulated, because a CSD is a derivative ACROSS
    channels and cannot be taken one channel at a time. A window is a
    second or so at 1 kHz, so sixty-four of them is a megabyte -- the reason
    the old voltage version accumulated does not apply here.

    Rows come back in the order `channels` was given, which the callers keep
    in probe order: the second derivative is meaningless over a list sorted
    by anything else.
    """
    band = spec.get("band") or incisor.DS_BAND
    rows, anchor, fs_out = [], None, None
    for ch in channels:
        raw, got_t0, ch_fs = csc._read_channel_window(session, ch, t0, t1)
        if raw.size < 8:
            return None
        q = incisor.decimation_for(ch_fs, float(spec.get("lfp_fs")
                                                or incisor.LFP_FS))
        dec = incisor._decimate(raw, q) if q > 1 else raw.astype(np.float64)
        if dec.size < 16:
            return None
        if anchor is None:
            anchor, fs_out = got_t0, ch_fs / q
        # THE MAINS COMES OUT FIRST, per channel, before the bandpass and
        # long before the derivative.
        #
        # Before the derivative because a second spatial difference
        # amplifies whatever differs most between neighbouring contacts:
        # 60 Hz is common-mode across a shank, so differencing first turns a
        # line that was everywhere into something that looks local, and by
        # then it cannot be told from a current.
        #
        # Before the bandpass because that is correct whether or not the
        # band happens to cover it. At 5-100 Hz -- the lab's own DS band --
        # 60 Hz is INSIDE the passband and a bandpass does nothing to it at
        # all; at 5-10 Hz a third-order Butterworth already has it 46 dB
        # down and the notch is a formality. Notching first is right in both
        # cases, so it is done in both cases rather than conditionally.
        rows.append(incisor._filtered(_notch(dec, fs_out, spec),
                                      fs_out, band))
    if not rows:
        return None
    keep = min(r.size for r in rows)
    return (np.vstack([r[:keep] for r in rows]), anchor, fs_out)


def csd_of(stack, spec):
    """The SIGNED current source density per row, two edge rows dropped.

    Signed, and that is a change. Rectifying here was wrong twice over: a
    dentate spike in this band is a BIPHASIC deflection, so |x| folds each
    half-cycle into its own positive lobe and one event arrives at the peak
    finder as several maxima 8-12 ms apart -- and "nearest" then picks
    whichever lobe happens to be closest to the old stamp. Rectifying also
    stops ongoing activity cancelling when anything is averaged, which is
    what made the first version of the objective test go UP as the alignment
    got worse.

    The rectification that remains happens once, at the very end, on the
    single projected trace -- see `windowed_peaks`.

    THE MEASUREMENT, and why it is not the voltage.

    A voltage raster at any one site is mostly what is happening somewhere
    else: the field spreads, so a big sink two hundred microns away shows up
    almost as strongly as one on the contact. Averaging |V| across a shank
    therefore measures the loudest event anywhere near the probe, and its
    peak sits wherever the volume conduction happens to be largest rather
    than where the current actually went.

    The current source density is the second spatial derivative across
    depth, which is exactly the part that cannot be volume-conducted. A
    dentate spike is a current sink in the hilus; on CSD that is a sharp,
    local thing with a real position, and the instant it peaks is the
    instant the event happened.

    `csc.compute_csd` is the same function the CSD panel draws from and the
    same one `analysis.py` uses -- one derivative in the codebase, not two
    that could disagree about a sign or a spacing.
    """
    if stack.shape[0] < 3:
        raise BracesError(
            "A CSD is a second derivative across depth, so it needs at "
            "least three channels; %d were ticked." % stack.shape[0])

    # Smoothed ACROSS DEPTH first, which is not optional here.
    #
    # A second difference amplifies whatever differs most between
    # neighbours, and on a real probe that is usually one noisy contact
    # rather than any current. Measured on M8s9feb8: the bare derivative put
    # CSC27 at 46,000 between neighbours at 14,000 -- a spike one contact
    # wide, which no current sink can be, and which would have dragged the
    # depth band onto a bad wire.
    #
    # A three-point [1 2 1] taper is the usual answer and is what the
    # original myCSD does before differencing. It costs half a contact of
    # depth resolution; the alignment needs the TIME of the peak, and that
    # is unmoved by a symmetric spatial filter.
    x = np.asarray(stack, dtype=np.float64)
    if x.shape[0] >= 5 and spec.get("csd_smooth", True):
        sm = x.copy()
        sm[1:-1] = 0.25 * x[:-2] + 0.5 * x[1:-1] + 0.25 * x[2:]
        x = sm

    pitch = float(spec.get("spacing_um") or probes.CONTACT_PITCH_UM)
    csd = csc.compute_csd(x.astype(np.float32), pitch)[1:-1]
    return np.asarray(csd, dtype=np.float64)


def spans(stamps, window_ms=WINDOW_MS, pad_s=PAD_S, merge_gap=MERGE_GAP_S):
    """The stretches of recording that actually have to be read.

    THE REASON THIS TOOL IS NOT AS SLOW AS A SCAN. Alignment asks, of each
    stamp, where the event is within a hundred milliseconds of it. That is
    twelve hundred windows of a fifth of a second -- about four minutes of a
    one-hour recording, not the hour. Reading the whole thing on every
    channel to use seven per cent of it is the difference between a run that
    takes three minutes and one that takes ten seconds.

    Returned merged and in order, so a burst is one read rather than five
    overlapping ones.
    """
    w = float(window_ms) / 1000.0
    out = []
    for t in sorted(stamps):
        lo, hi = t - w - pad_s, t + w + pad_s
        if out and lo - out[-1][1] <= merge_gap:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([max(0.0, lo), hi])
    return [(a, b) for a, b in out]


# How many channels the average is taken over, once the depth is known.
#
# A dentate spike is depth-specific: its current sink sits across the hilus
# and is absent at the top of the shank, so averaging all sixty-four buries
# the event under depths that never saw it -- and costs four times the
# reading to do it. A band around the strongest depth is both the better
# measurement and the cheaper one.
DEPTH_BAND = 16

# How many stamps the depth pass looks at. Where the sink is is a fact about
# the probe, not about any one spike, so a sample settles it -- and a sample
# of sixty is seconds rather than minutes.
DEPTH_SAMPLE = 60


def span_csd(session, channels, spec, t0, t1, bad=None):
    """The signed CSD across depth over one stretch, padding trimmed.

    Returns (start_time, sample_rate, values [rows x samples], row
    numbers, lo, hi) or None where nothing could be read -- `values` is
    everything that was read INCLUDING the filter padding, and `lo:hi` is
    the part that was asked for. The row numbers matter: a CSD has
    no value at the ends of the list it is given, so row i is channel i+1,
    and everything downstream matches weights to contacts by NUMBER rather
    than by position in an array somebody may have sliced.
    """
    got = _stack(session, channels, spec, t0, t1)
    if not got:
        return None
    stack, anchor, fs_out = got
    stack = repair(stack, channels, bad)
    if (spec.get("measure") or "csd") == "voltage":
        vals = np.asarray(stack, dtype=np.float64)
        off = 0
    else:
        vals = csd_of(stack, spec)
        off = 1
    want_lo, want_hi = t0 + PAD_S, t1 - PAD_S
    lo = max(0, int(round((want_lo - anchor) * fs_out)))
    hi = min(vals.shape[1], int(round((want_hi - anchor) * fs_out)))
    if hi - lo < 4 or vals.shape[0] < 1:
        return None
    nums = [int(channels[i + off]["number"]) for i in range(vals.shape[0])]
    # EVERYTHING that was read, and where the wanted part of it starts.
    #
    # The padding is filter margin -- a Butterworth rings at the edge of
    # whatever array it is handed -- but it is also half a second of
    # ordinary recording either side of the window, and that is exactly
    # what a baseline wants to be measured on. Trimming it away here left
    # an isolated stamp with 200 ms to estimate a floor from, most of which
    # is the event the floor is meant to admit. Callers take `lo:hi` when
    # they want the window and the whole of it when they want the quiet.
    return (anchor, fs_out, vals, nums, lo, hi)


# How long a moving average is run over the trace, in milliseconds.
#
# Zero, which draws it raw. It is here because rectifying per contact and
# pooling after makes each HALF-CYCLE of a biphasic deflection its own
# positive lobe, so one event can arrive as two or three humps -- |sin| has
# twice the frequency of sin, which is arithmetic and not a property of the
# recording. A moving average about as long as one half-cycle merges them
# back into a single hump whose maximum is a usable time. It is off by
# default because it also costs timing: broadening a peak makes it easier to
# find and harder to place.
SMOOTH_MS = 0.0


def trace_of(csd, fs=None, spec=None):
    """The average rectified CSD across depth -- one number per instant.

    The mean of |CSD| and NOT |mean of CSD|, which would be near zero by
    construction: a sink at one depth is a source at the next, so a signed
    average across a shank cancels whether or not anything happened.

    The edges are reflection-padded rather than zero-padded when a moving
    average is asked for -- zero-padding pulls the first and last few
    milliseconds toward zero and invents a peak just inside them.
    """
    x = np.abs(np.asarray(csd, dtype=np.float64)).mean(axis=0)
    ms = float((spec or {}).get("smooth_ms", SMOOTH_MS) or 0.0)
    n = int(round(float(fs or 0.0) * ms / 1000.0))
    if n > 1 and x.size > n:
        pad = n // 2
        k = np.ones(n, dtype=np.float64) / n
        x = np.convolve(np.pad(x, pad, mode="reflect"), k,
                        mode="same")[pad:pad + x.size]
    return x


def event_template(session, channels, spec, stamps, bad=None, job=None,
                   sample=None, tmpl_ms=TMPL_MS):
    """What a dentate spike looks like on this probe, from the stamps.

    THE STEP THAT MAKES THE REST POSSIBLE. Average the CSD across a sample
    of the events at their curated times. The spike is time-locked to those
    stamps so it adds coherently; the ongoing activity, the noise and
    whatever a bad contact is doing are not time-locked to them, so they
    average down as one over the root of the count. Sixty events is an
    eightfold gain, and what is left is a picture of the event rather than a
    picture of the probe's worst wire.

    That is the whole answer to what the old depth pass got wrong. It scored
    each depth by the median of its largest |CSD| in a window, which is a
    question about magnitude -- and the largest magnitude on a probe with a
    dead contact is the dead contact, because a second spatial difference
    amplifies it. Here an artefact that is not time-locked has already gone
    before the question is asked.

    Returns (template [rows x samples], row numbers, n events, fs).
    """
    picks = sorted(stamps)
    n_want = int(sample or DEPTH_SAMPLE)
    if len(picks) > n_want:
        step = len(picks) / float(n_want)
        picks = [picks[int(i * step)] for i in range(n_want)]
    runs_ = spans(picks, spec.get("window_ms", WINDOW_MS))
    if job:
        job.begin("ds depth", of=len(runs_), unit="windows")

    acc, nums, n, fs_out, half = None, None, 0, None, None
    for k, (a, b) in enumerate(runs_):
        if job:
            job.check()
            job.tick("ds depth", k)
        got = span_csd(session, channels, spec, a, b, bad)
        if not got:
            continue
        t0, fs, vals, row_nums, _lo, _hi = got
        if half is None:
            fs_out, nums = fs, row_nums
            half = max(2, int(round(fs * float(tmpl_ms) / 1000.0)))
        if row_nums != nums:
            continue                       # a short read; it cannot be added
        for t in picks:
            j = int(round((t - t0) * fs))
            if j - half < 0 or j + half + 1 > vals.shape[1]:
                continue
            patch = vals[:, j - half:j + half + 1]
            acc = patch.copy() if acc is None else acc + patch
            n += 1
    if acc is None or not n:
        raise BracesError(
            "None of the chosen channels could be read over the windows "
            "these stamps are in, so there is nothing to build a template "
            "of the event from.")
    return acc / float(n), nums, n, fs_out


def depth_band(session, channels, spec, stamps, want=DEPTH_BAND, job=None,
               bad=None):
    """Where the event is on the shank, and how much of it each contact sees.

    Scored on the event-triggered template rather than on raw magnitude,
    which is the whole difference from what this used to do -- see
    `event_template`. The band is the run of `want` CONTIGUOUS contacts
    holding the most of the template's energy: contiguous because the depths
    a dentate spike sinks at are neighbours on a linear probe, and taking
    the top sixteen by score would be free to pick a scatter of contacts
    from three depths that happened to be noisy.

    Returns (band numbers, per-depth rows, index of the band's first row,
    profile) where the profile is {contact number: weight} -- the event's
    own depth signature, normalised, and the thing every window is then
    projected onto.
    """
    tmpl, nums, n_ev, fs = event_template(session, channels, spec, stamps,
                                          bad=bad, job=job)
    energy = (tmpl ** 2).sum(axis=1)
    by_num = {int(c["number"]): c for c in channels}
    rows = [{"number": int(nums[i]),
             "index": int((by_num.get(int(nums[i])) or {}).get("index", i)),
             "score": round(float(energy[i]), 3)}
            for i in range(len(nums))]
    if not rows:
        raise BracesError("No depth could be scored from those windows.")

    if len(rows) <= want:
        lo, hi = 0, len(rows)
    else:
        lo, best = 0, -1.0
        for i in range(0, len(rows) - want + 1):
            tot = float(energy[i:i + want].sum())
            if tot > best:
                best, lo = tot, i
        hi = lo + want
    chosen = rows[lo:hi]

    # The profile: the template's shape across depth AT THE INSTANT IT PEAKS.
    #
    # One column, not a summary of the whole patch. The dipole is what
    # identifies a dentate spike -- a sink with sources above and below it --
    # and its signs are what let the projection cancel activity that is not
    # shaped like that. A magnitude profile would weight the source flanks
    # positively too and throw that away.
    band = tmpl[lo:hi]
    j = int(np.argmax(np.abs(band).max(axis=0)))
    p = band[:, j].astype(np.float64)
    nrm = float(np.linalg.norm(p)) or 1.0
    p = p / nrm
    profile = {int(chosen[i]["number"]): round(float(p[i]), 6)
               for i in range(len(chosen))}
    return [r["number"] for r in chosen], rows, lo, profile


def windowed_peaks(session, channels, report, spec, stamps, job=None,
                   bad=None):
    """Peak candidates, read only where the stamps are.

    Same answer as reading the whole recording and the same peaks in the
    places that matter -- because the places that matter are exactly the
    windows the stamps can reach, and nothing outside one can ever be
    assigned to anything.

    WHAT A CANDIDATE IS. Each window is read with the mains notched out per
    channel, repaired over any screened contact, turned into a signed CSD
    across depth and then averaged as |CSD| over the contacts read. The
    maxima of that curve are the candidates, and there is no floor: a
    candidate is a local maximum whatever its height, which is what
    `dentate_spike_aligner.py` does.

    Local maxima rather than one argmax per window, and the candidates go
    through the assignment -- one peak per stamp, no crossing -- which is
    the one thing this has to add to that file. It reports one event at a
    time and has nothing to contend with; a set does, and two stamps in a
    burst being handed the same instant would put a duplicate in somebody's
    bank.
    """
    if not HAVE_SCIPY:
        raise BracesError(
            "SciPy is not installed on this machine, so no filtering or "
            "peak finding can be done here.")
    if not channels:
        raise BracesError("No channels to read.")
    if not stamps:
        raise BracesError("No stamps to align.")

    runs_ = spans(stamps, spec.get("window_ms", WINDOW_MS))
    if job:
        job.begin("ds windows", of=len(runs_), unit="windows")

    times, amps, floors, noises = [], [], [], []
    n_ch, read, used_nums = 0, 0.0, None
    for k, (a, b) in enumerate(runs_):
        if job:
            job.check()
            job.tick("ds windows", k)
        got = span_csd(session, channels, spec, a, b, bad)
        if not got:
            continue
        t0, fs, vals, row_nums, lo, hi = got
        n_ch = max(n_ch, vals.shape[0])
        read += (b - a)

        used_nums = row_nums if used_nums is None else used_nums

        # THE TRACE: the average rectified CSD across the contacts read.
        # One number per instant, and its maxima are the candidates.
        v = trace_of(vals, fs, spec)

        # No floor. `dentate_spike_aligner.py` has none: it takes the
        # largest thing in the window whatever its size, and a floor here
        # would be a rule that file does not contain. What is still
        # measured is the baseline, because the bench draws it and because
        # a row's peak against it is worth seeing even when nothing is
        # gated on it.
        med = float(np.median(v))
        noise = float(np.median(np.abs(v - med))) / 0.6745
        floors.append(med + 4.5 * (noise or 1.0))
        noises.append(noise)

        dist = max(1, int(round(fs * float(spec.get("cand_dist_ms")
                                           or CAND_DIST_MS) / 1000.0)))
        idx, _props = _sig.find_peaks(v, distance=dist)
        idx = idx[(idx >= lo) & (idx < hi)] if idx.size else idx
        for i in range(idx.size):
            j = int(idx[i])
            t = t0 + j / fs
            # Parabolic, so the answer is not stuck on the sample grid. At
            # 1 kHz a sample is a millisecond and the jitter being measured
            # is a few of them, so rounding every answer to the grid would
            # throw away a quarter of the precision this is for.
            if 0 < j < v.size - 1:
                y0, y1, y2 = float(v[j - 1]), float(v[j]), float(v[j + 1])
                den = y0 - 2.0 * y1 + y2
                if den != 0:
                    t += (0.5 * (y0 - y2) / den) / fs
            times.append(round(float(t), 6))
            amps.append(round(float(v[j]), 3))

    if not times:
        raise BracesError(
            "No peak was found in any of those windows, so there is nothing "
            "to align these stamps to.")

    # Merged windows are disjoint, so a peak cannot be found twice -- but
    # checked rather than assumed, because a duplicate candidate would let
    # the assignment hand two stamps what is really one instant.
    order = sorted(range(len(times)), key=lambda i: times[i])
    times = [times[i] for i in order]
    amps = [amps[i] for i in order]
    for i in range(1, len(times)):
        if times[i] - times[i - 1] < 1e-6:
            raise BracesError(
                "Two peak candidates landed on the same instant (%.6f), "
                "which means two windows overlapped. Nothing was written."
                % times[i])

    floor = float(np.median(floors)) if floors else 0.0
    sd = float(np.median(noises)) if noises else 0.0
    return {
        "times": times, "amps": amps,
        # Nothing is gated on either of these now: a candidate is a local
        # maximum of the curve whatever its height. They are reported
        # because the bench draws the baseline and because "this peak is
        # barely above the background" is worth seeing even when it did not
        # change the answer.
        "thr_uv": 0.0,
        "cand_floor_uv": round(floor, 3),
        "cand_height_sd": 0.0,
        "sd_uv": round(sd, 3),
        "estimator": "mad",
        "band": list(spec.get("band") or incisor.DS_BAND),
        "line_hz": float(spec.get("line_hz", LINE_HZ) or 0.0),
        "dist_ms": float(spec.get("dist_ms", incisor.DS_DIST_MS)),
        "cand_dist_ms": float(spec.get("cand_dist_ms") or CAND_DIST_MS),
        "n_peaks": len(times),
        "n_channels": n_ch,
        "channels": [int(c["number"]) for c in channels],
        "smooth_ms": float(spec.get("smooth_ms", SMOOTH_MS) or 0.0),
        "screened": {str(k): v for k, v in dict(bad or {}).items()},
        "skipped_channels": [],
        "n_windows": len(runs_),
        "read_s": round(read, 1),
    }


def profile_window(session, channels, report, spec, t0, t1, profile=None,
                   bad=None):
    """The same measurement over one short stretch, for drawing.

    Read, notched, repaired, CSD'd and averaged exactly as the aligning
    pass does -- so the line the bench draws is the line the decision was
    made on, at the same scale, rather than something that merely looks
    like it.

    Filtered with a margin either side and trimmed after: a Butterworth
    rings at the edge of whatever array it is handed, and a bench drawn
    from a bare 600 ms slice would put that ringing exactly where the stamp
    is. The baseline is measured on the whole read and the curve is drawn
    from the window, which is the same split the peak pass makes.
    """
    if not HAVE_SCIPY:
        raise BracesError("SciPy is not installed on this machine.")
    got = span_csd(session, channels, spec,
                   max(0.0, t0 - PAD_S), t1 + PAD_S, bad)
    if not got:
        raise BracesError("None of those channels could be read here.")
    anchor, fs_out, vals, row_nums, lo, hi = got

    line = trace_of(vals, fs_out, spec)
    med = float(np.median(line))
    noise = float(np.median(np.abs(line - med))) / 0.6745
    line = line[lo:hi]
    return {
        "t0": round(anchor + lo / fs_out, 6),
        "fs": fs_out,
        "n_channels": vals.shape[0],
        "measure": (spec.get("measure") or "csd"),
        "smooth_ms": float(spec.get("smooth_ms", SMOOTH_MS) or 0.0),
        # What the background is here. Nothing is gated on it -- a candidate
        # is a local maximum whatever its height -- but a peak that barely
        # clears the surrounding activity is worth being able to see.
        "floor": round(med + 4.5 * (noise or 1.0), 3),
        "values": [round(float(v), 3) for v in line],
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
    "outlier": "unlike the others",
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

    # WHICH RULE. The largest peak in the window where the candidates come
    # with heights, which is what a run of this tool produces; the nearest
    # where they do not, which is what the arithmetic checks hand it. The
    # difference is not a preference: with no floor, a window holds every
    # local maximum of the curve, so "nearest" means the nearest wiggle and
    # the measurement never gets used. Measured on M1ptens2oct2's 64
    # spikes: nearest moved nothing further than 10 ms and scored 0.628 on
    # the event-triggered average, against 0.712 for the same candidates
    # taken largest-first.
    by_size = len(p_amps) == len(p_times) and bool(p_amps)
    taken = assign(stamps, p_times, window_ms,
                   amps=p_amps if by_size else None)
    closest = (biggest(stamps, p_times, p_amps, window_ms) if by_size
               else nearest(stamps, p_times, window_ms))
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
            # Only where a SINGLE floor applied to every candidate. It no
            # longer does: each window has its own, measured on its own
            # quiet, so comparing one window's peak against the median of
            # all the floors flags peaks that cleared the only floor that
            # was ever asked of them. `peaks` says so by sending no
            # `thr_uv`, and a stamp with nothing big enough in reach comes
            # back as `no_peak`, which is the more honest thing to say.
            flag = "weak"
        row["flag"] = flag

    # Which moves are unlike the rest of this set's.
    #
    # Second pass, because it cannot be known one row at a time: whether
    # 60 ms is remarkable depends on what the other twelve hundred did. The
    # flags already set are left alone -- a stamp that gave up a nearer peak
    # is a more specific thing to say than "this one moved further".
    moved = [r["shift_ms"] for r in rows if r.get("moved")
             and r.get("shift_ms") is not None]
    if len(moved) >= 8:
        srt = sorted(moved)
        mid = len(srt) // 2
        med = srt[mid] if len(srt) % 2 else (srt[mid - 1] + srt[mid]) / 2.0
        devs = sorted(abs(x - med) for x in moved)
        m = devs[len(devs) // 2]
        spread = max(OUTLIER_FLOOR_MS, (m / 0.6745) * OUTLIER_MADS)
        for row in rows:
            if row.get("flag") or not row.get("moved"):
                continue
            if row.get("shift_ms") is None:
                continue
            if abs(row["shift_ms"] - med) > spread:
                row["flag"] = "outlier"

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
        "thr_uv": peaks.get("thr_uv"),
        # How big a candidate had to be to be one. Travels with the set,
        # not only with the job, because the bench draws it and because a
        # proposal read back tomorrow still has to be able to say what it
        # would and would not align to.
        "cand_floor_uv": peaks.get("cand_floor_uv"),
        "cand_dist_ms": peaks.get("cand_dist_ms"),
        "n_channels": peaks.get("n_channels"),
        "channels": peaks.get("channels"),
        "skipped_channels": peaks.get("skipped_channels"),
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
        # The channels that went into the profile, and how many. There is no
        # single channel any more: the measurement is the probe.
        "channels": list(peaks.get("channels") or []),
        "n_channels": int(peaks.get("n_channels") or 0),
        "spacing_um": float(spec.get("spacing_um")
                            or probes.CONTACT_PITCH_UM),
        "csd_smooth": bool(spec.get("csd_smooth", True)),
        "band": list(peaks.get("band") or incisor.DS_BAND),
        "order": incisor.DS_ORDER,
        # Which measure, as asked -- not the default written twice. This is
        # the record of how a set's numbers were made, and a voltage run
        # filed as a CSD one is a record that lies about its own contents.
        "measure": (spec.get("measure") or "csd"),
        "window_ms": float(spec.get("window_ms", WINDOW_MS)),
        # Two spacings, and they are not the same number. `dist_ms` is the
        # detector's, kept because it says which stamps exist at all;
        # `cand_dist_ms` is how close two CANDIDATES may be, which is what
        # decides whether a stamp can reach its own peak.
        "dist_ms": float(peaks.get("dist_ms") or incisor.DS_DIST_MS),
        "cand_dist_ms": float(peaks.get("cand_dist_ms") or CAND_DIST_MS),
        # How big a candidate had to be, in SDs. Zero means no floor, which
        # is the rule now -- recorded rather than left out, because a set
        # made under a floor and one made without it are not comparable and
        # the difference has to be visible on the set itself.
        "cand_height_sd": float(peaks.get("cand_height_sd") or 0.0),
        # The mains frequency taken out before anything was measured. Zero
        # would mean it was not, which is a different measurement.
        "line_hz": float(peaks.get("line_hz") or 0.0),
        # How long a moving average was run over the trace. Zero is raw.
        "smooth_ms": float(peaks.get("smooth_ms") or 0.0),
        # The event's depth signature: {contact: weight}. Nothing is
        # projected onto it any more, but it is the one number that says
        # the band sat on an event -- a dentate spike is a sink with
        # sources either side, so this has both signs in it, and a profile
        # that does not is a band that found something else.
        "profile": dict(peaks.get("profile") or {}),
        # Contacts that were interpolated rather than believed, and why.
        "screened": dict(peaks.get("screened") or {}),
        "estimator": peaks.get("estimator"),
        "lfp_fs": round(float(peaks.get("lfp_fs") or incisor.LFP_FS), 4),
        "invert": bool(spec.get("invert", True)),
    }
