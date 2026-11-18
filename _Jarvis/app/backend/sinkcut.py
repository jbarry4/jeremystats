# -*- coding: utf-8 -*-
"""sinkcut.py -- The Bite line: DS1 and DS2 split by how much their sinks
overlap (asked 2026-11-12).

WHY. X-ray's three splits (PCA, PCA + gap, delta) cut on a peak's position
or on PC1. Pushing two classes' sink PEAKS apart can cut one sink blob in
two, because a blob is wide and its peak wanders inside it from event to
event. Asked for instead: draw the line so DS1's sinks overlap DS2's as
little as possible, while each class's sinks overlap their own class as
much as possible -- with a way to see where the sinks are and to move the
line by hand. It is one line: every event goes to a side, no grey zone.

HOW, in five steps, all numpy and scipy:
  1  SINKS. Each event's depth profile, inside the box's contacts: its CSD
     (5-100 Hz, as X-ray draws it) averaged over a few milliseconds around
     the event. Sinks are the negative side (CSD = -sigma d2V/dz2, the sign
     dspca.class_marker reads a sink by). Going down the profile, every
     stretch between two zero crossings is a BUMP -- the band's ends close
     one too. A bump's size is its area (the sum of -CSD across it). The
     two largest are the event's sink and every other bump is dropped,
     because a profile usually has two clearly large bumps -- one per blade
     of the dentate -- and those two are what DS1 and DS2 differ by. What is
     kept is scaled to add up to 1. An event with no negative CSD in the box
     is flagged; one with a single bump keeps that one. (`sink="negative"`
     keeps the whole negative side instead, every bump, for comparison.)
     THE DEFAULT SINCE 2026-11-12 IS sink="humps": the two bumps are the
     RECORDING's -- the two biggest of its mean profile, parted at the
     source between them (hump_cut) -- and each event's whole negative side
     in each counts, each hump weighing the same. Per event, a hump with a
     notch inside it (a "camel") became two bumps where the notch touched
     zero, and the line followed that bookkeeping; see hump_cut.
  2  OVERLAP. Between two events, the Bhattacharyya coefficient of their
     sink distributions: sum over depth of sqrt(s_i * s_j). 1 is the same
     sink, 0 is sinks that never share a contact.
  3  ORDER. The normalised-cut relaxation: the Fiedler vector of the
     overlap graph's normalised Laplacian gives every event one number,
     and events sorted by it put like sinks next to like.
  4  THE LINE. Every cut position along that order is scored at once (two
     cumulative sums): the normalised cut, and the plainer separation
     index, 1 - between / mean(within). The default line is the lowest
     normalised cut that leaves each side at least 2% of the events and
     never fewer than 5; the curve's other dips are offered as snap
     points, and any other line is a slider position.
  5  NAMES. Which side is DS1 is extraction.name_sides -- X-ray's own rule
     -- so the numbering agrees with the three existing splits.

`fit` runs all five on one recording's cached split arrays
(extraction.split_arrays); `view` is what a page draws: the order, the
sweep, the sink raster, the sorted overlap matrix (at most 200 x 200) and
which side is DS1 at every line position, so the line moves without a
round trip.
"""
from __future__ import annotations

import numpy as np

HALF_MS = 3.0          # the window either side of the event, in ms
# "one" (2026-11-13): the contacts given are ONE hump, taken whole -- the
# Bite line on the top or the bottom hump alone (extraction.add_humps).
SINKS = ("humps", "bumps", "negative", "one")
SINK_DEFAULT = "humps" # 2026-11-12: the recording's two humps (hump_cut)
N_BUMPS = 2            # the bumps kept: one per blade
MIN_SHARE = 0.02       # the default line keeps at least this share a side
MIN_EVENTS = 5         # ... and never fewer than this many events
SMOOTH = 0             # passes of a 1-2-1 taper across depth
MAX_MATRIX = 200       # the overlap picture, at most this many bins a side
WEAK_FRAC = 0.10       # a sink this small next to the median is "weak"
THIRD_BIG = 0.50       # a third bump this big next to the second is real

# HOW CLEAN A LINE IS, said in words. The separation index at the line,
# 1 - between / mean(within): set on the 18 cached reads of 2026-11-12,
# where the two recordings with a second family of sinks scored 0.83-0.96
# (and their lines survived every bootstrap), and the recordings whose
# sinks are one blob drifting a contact or two scored 0.06-0.12 (lines that
# moved with every resample). A line is always drawn -- every event goes to
# a side -- but under PARTIAL_SI it is splitting one family in two.
SEPARATE_SI = 0.50
PARTIAL_SI = 0.20
SMALL_SHARE = 0.05     # a side smaller than this gets a "check them" word


def _r(v, n=4):
    """A float for JSON: n significant figures, None for nan/inf."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return 0.0 if v == 0 else float("%.*g" % (n, v))


def _rl(a, n=4):
    return [_r(v, n) for v in np.asarray(a, dtype=float).ravel()]


# --------------------------------------------------------------------------
# 1  Sinks
# --------------------------------------------------------------------------
def time_axis(n_t, surround_ms=50.0):
    """(fs, stamp index) for a surround of n_t samples, laid out as
    dspca.samples_for_box lays it: -surround..+surround, stamp in the
    middle."""
    fs = (n_t - 1) / (2.0 * float(surround_ms) / 1000.0)
    return fs, n_t // 2


def band_rows(nums_all, nums_sel):
    """The rows of `disp` holding the box's contacts, in the box's order."""
    at = {int(n): i for i, n in enumerate(nums_all)}
    missing = [int(n) for n in nums_sel if int(n) not in at]
    if missing:
        raise ValueError("CSC%s are in the box but not in the read."
                         % ", ".join(str(n) for n in missing))
    return [at[int(n)] for n in nums_sel]


def _taper(x, passes=1):
    """A 1-2-1 taper down axis 1 (depth), ends held, `passes` times."""
    for _ in range(int(passes or 0)):
        xp = np.concatenate([x[:, :1], x, x[:, -1:]], axis=1)
        x = 0.25 * xp[:, :-2] + 0.5 * xp[:, 1:-1] + 0.25 * xp[:, 2:]
    return x


def bumps(neg):
    """The bumps of one profile's negative side, as (first row, row past the
    last, area): each stretch where it is above zero, the ends of the array
    closing a stretch as a zero crossing would."""
    on = np.asarray(neg) > 0
    if not on.any():
        return []
    edge = np.diff(np.concatenate([[0], on.astype(np.int8), [0]]))
    lo, hi = np.flatnonzero(edge == 1), np.flatnonzero(edge == -1)
    return [(int(a), int(b), float(neg[a:b].sum())) for a, b in zip(lo, hi)]


def top_bumps(neg, keep=N_BUMPS, big_third=None):
    """Which contacts the `keep` largest bumps of each event cover.

    neg is events x contacts, the negative side (>= 0). Returns (mask,
    found, spans, third): mask is True on a kept bump, found how many bumps
    each event had, spans each event's kept bumps as [first, last] rows,
    shallowest first, and third the area of its third-largest bump over its
    second's (0 with fewer than three). keep=None keeps every bump.

    THE THIRD BUMP IS THE THING TO WATCH. On most recordings it is noise
    (a few per cent of the second), but where the box takes in a third real
    sink band, "the two largest" becomes "which two of three won" on each
    event -- a ranking of peaks, the very thing this module is meant to
    avoid -- and the line can follow it. `big_third` (a fraction, off by
    default) keeps a third bump too when it is at least that share of the
    second's area: on the 18 reads of 2026-11-12, 0.5 changed nothing
    where the third bump was noise and undid that ranking where it was not.
    """
    neg = np.asarray(neg, dtype=np.float64)
    mask = np.zeros(neg.shape, dtype=bool)
    found, spans, third = [], [], []
    for i, row in enumerate(neg):
        bb = sorted(bumps(row), key=lambda b: -b[2])
        found.append(len(bb))
        third.append(bb[2][2] / bb[1][2] if len(bb) > 2 and bb[1][2] > 0
                     else 0.0)
        top = bb[:keep] if keep else bb
        if keep == 2 and big_third and third[-1] >= float(big_third):
            top = bb[:3]
        for a, b, _ in top:
            mask[i, a:b] = True
        spans.append(sorted([a, b - 1] for a, b, _ in top))
    return (mask, np.asarray(found, dtype=int), spans,
            np.asarray(third, dtype=float))


def sink_dists(disp, nums_sel, t0_index=None, half_ms=HALF_MS, fs=1000.0,
               nums_all=None, sink="bumps", n_bumps=N_BUMPS, smooth=SMOOTH,
               depth_time=False, dead=0.0, recentre_ms=0.0, big_third=None):
    """Each event's sink as a distribution, and what was found on the way.

    disp       events x contacts x samples, the CSD (sinks negative)
    nums_sel   the box's contact numbers: the depth band
    t0_index   the event's sample (the middle of the surround by default)
    half_ms    the window either side of it, averaged over
    nums_all   the contact number of each row of `disp`
    sink       "bumps": the averaged profile's `n_bumps` largest bumps
               (None: all of them); "negative": the whole negative side,
               each sample rectified and then summed
    smooth     passes of a 1-2-1 taper across depth, after the above
    depth_time keep time as well as depth (each event a depth x time map;
               with bumps, the map inside the kept bumps' contacts)
    dead       ignore sink weaker than this fraction of the event's deepest
    recentre_ms  centre each event's window on its own deepest sink within
               this many ms of t0 (0: everyone on t0)
    big_third  with two bumps kept, keep a third as well when its area is
               at least this share of the second's (None: never)

    Returns (S, info): S is events x features, each row adding to 1 (a
    flagged row is zeros); info holds `depth` (the depth-only distribution,
    events x contacts, for drawing), `mass`, `flag` (no sink), `weak`,
    `found` (bumps on each event's profile), `spans` (the kept bumps'
    first and last rows), `third` (third bump's area over the second's),
    `centre` (each window's sample) and `rows`.
    """
    if sink not in SINKS:
        raise ValueError("A sink is one of %s; not %r."
                         % (", ".join(SINKS), sink))
    d = np.nan_to_num(np.asarray(disp, dtype=np.float64))
    n, n_ch, n_t = d.shape
    if nums_all is None:
        if n_ch != len(nums_sel):
            raise ValueError("Pass nums_all: disp has %d rows and the box %d."
                             % (n_ch, len(nums_sel)))
        rows = list(range(n_ch))
    else:
        rows = band_rows(nums_all, nums_sel)
    block = d[:, rows, :]
    t0 = n_t // 2 if t0_index is None else int(t0_index)
    h = max(0, int(round(float(half_ms) * float(fs) / 1000.0)))
    centre = np.full(n, t0, dtype=int)
    if recentre_ms and recentre_ms > 0:
        r = int(round(float(recentre_ms) * float(fs) / 1000.0))
        lo, hi = max(0, t0 - r), min(n_t, t0 + r + 1)
        centre = lo + np.argmin(block[:, :, lo:hi].min(axis=1), axis=1)
    idx = np.clip(centre[:, None] + np.arange(-h, h + 1)[None, :], 0, n_t - 1)
    win = np.take_along_axis(block, idx[:, None, :].repeat(len(rows), 1), 2)
    # The profile (the window's average), its negative side as >= 0.
    prof = np.maximum(0.0, -win.mean(axis=2))                # n x D
    if dead and dead > 0:
        prof = np.maximum(0.0, prof - float(dead)
                          * prof.max(axis=1, keepdims=True))
    cut, camel = None, np.zeros(n, dtype=bool)
    if sink in ("humps", "one"):
        # The recording's two humps, not each event's own two biggest bumps
        # (2026-11-12, "the camel hump"): see hump_cut. "one": the contacts
        # given are a single hump already.
        cut = hump_cut(win.mean(axis=2).mean(axis=0)) if sink == "humps" else None
        halves = ([(0, cut), (cut, prof.shape[1])] if cut is not None
                  else [(0, prof.shape[1])])
        mask = prof > 0
        found = np.array([len(bumps(r)) for r in prof], dtype=int)
        third = np.zeros(n)
        spans, peaks = [], []
        for i, r in enumerate(prof):
            sp, pk = [], []
            for a, b in halves:
                seg = r[a:b]
                if not (seg > 0).any():
                    continue
                nz = np.flatnonzero(seg > 0)
                sp.append([a + int(nz[0]), a + int(nz[-1])])
                pk.append(a + int(np.argmax(seg)))
                if len(bumps(seg)) > 1:
                    camel[i] = True
            spans.append(sp)
            peaks.append(pk)
    else:
        mask, found, spans, third = top_bumps(prof, n_bumps, big_third)
        # Each kept bump's deepest point: where its sink is strongest (a row).
        peaks = [[int(a + np.argmax(prof[i, a:b + 1])) for a, b in sp]
                 for i, sp in enumerate(spans)]
    raw_mass = None
    if sink in ("humps", "one"):
        s = (np.maximum(0.0, -win) * mask[:, :, None]) if depth_time else prof.copy()
        raw_mass = s.reshape(n, -1).sum(axis=1)
        # Each hump an event has weighs the same: the upper blade's sink is
        # usually the bigger, and DS1 and DS2 differ by WHERE the sink sits in
        # both, not by which blade is louder.
        hm = np.stack([s[:, a:b].reshape(n, -1).sum(axis=1) for a, b in halves], 1)
        have = (hm > 0).sum(axis=1)
        for j, (a, b) in enumerate(halves):
            w = np.divide(1.0, hm[:, j] * have, out=np.zeros(n),
                          where=(hm[:, j] > 0) & (have > 0))
            s[:, a:b] = s[:, a:b] * w.reshape((n,) + (1,) * (s.ndim - 1))
    elif sink == "bumps":
        if depth_time:
            s = np.maximum(0.0, -win) * mask[:, :, None]
        else:
            s = prof * mask
    else:
        neg = np.maximum(0.0, -win)                           # n x D x T
        if dead and dead > 0:
            neg = np.maximum(0.0, neg - float(dead)
                             * neg.max(axis=(1, 2), keepdims=True))
        s = neg if depth_time else neg.sum(axis=2)
    s = _taper(s, smooth)
    flat = s.reshape(n, -1)
    mass = flat.sum(axis=1) if raw_mass is None else raw_mass
    flag = ~(mass > 0)
    S = np.zeros_like(flat)
    fm = flat.sum(axis=1)
    S[~flag] = flat[~flag] / np.where(fm[~flag] > 0, fm[~flag], 1.0)[:, None]
    depth = s.sum(axis=2) if depth_time else s
    dm = depth.sum(axis=1)
    depth = np.divide(depth, dm[:, None], out=np.zeros_like(depth),
                      where=dm[:, None] > 0)
    med = float(np.median(mass[~flag])) if np.any(~flag) else 0.0
    weak = (~flag) & (mass < WEAK_FRAC * med)
    return S, {"depth": depth, "mass": mass, "flag": flag, "weak": weak,
               "found": found, "spans": spans, "peaks": peaks, "third": third,
               "centre": centre, "rows": rows, "cut": cut, "camel": camel}


def hump_cut(m):
    """Where a recording's two humps part, on its mean stamp profile `m` (the
    CSD, sinks negative, down the band): the two biggest sink bumps of the
    mean, and the source between them at its strongest. Returns the first
    row of the bottom hump; None when the mean has fewer than two bumps (one
    hump: the whole band).

    WHY THE RECORDING'S AND NOT EACH EVENT'S (2026-11-12). Taking each
    event's own two biggest bumps worked until a hump had a dip inside it --
    two sub-sinks, at the outer and middle molecular layer say, with a notch
    between. Where an event's notch touched zero its hump became two bumps,
    "the two biggest" became the two halves of one hump, and the line split
    the events by that bookkeeping: on m6 s4, 20 of the 26 events on the
    small side were the 22 whose notch reached zero. The notch itself was
    checked and is in the signal (every contact's gain within 0.3% of its
    neighbours' prediction, steady over the recording; nothing on any
    repaired contact). The recording's two humps do not change from event
    to event, so each event's sink is taken whole in each."""
    m = np.asarray(m, dtype=np.float64)
    bb = sorted(bumps(np.maximum(0.0, -m)), key=lambda b: -b[2])[:2]
    if len(bb) < 2:
        return None
    (_a1, b1, _), (a2, _b2, _) = sorted(bb)
    return int(b1 + int(np.argmax(m[b1:a2])) + 1) if a2 > b1 else int(b1)


def stamp_profiles(A, half_ms=HALF_MS, surround_ms=50.0):
    """Each event's CSD down the box at the stamp, averaged +-half_ms (the
    profile the Bite line takes its sink from, signed: sinks negative), and
    the box's contact numbers. From a recording's split arrays."""
    disp = np.nan_to_num(np.asarray(A["disp"], dtype=np.float64))
    ns = [int(n) for n in A["nums_sel"]]
    na = [int(n) for n in A["nums_all"]] or ns
    rows = band_rows(na, ns)
    fs, t0 = time_axis(disp.shape[2], surround_ms)
    h = max(0, int(round(float(half_ms) * fs / 1000.0)))
    lo, hi = max(0, t0 - h), min(disp.shape[2], t0 + h + 1)
    return disp[:, rows, lo:hi].mean(axis=2), ns


# --------------------------------------------------------------------------
# 2  Overlap
# --------------------------------------------------------------------------
def overlap(S):
    """Bhattacharyya coefficients between every pair of rows of S, in
    [0, 1]: sum over features of sqrt(s_i * s_j)."""
    q = np.sqrt(np.maximum(np.asarray(S, dtype=np.float64), 0.0))
    return np.clip(q @ q.T, 0.0, 1.0)


def affinity(W, knn=None, power=1.0):
    """The graph the order is taken from: W with no self-loops, optionally
    sharpened (W ** power) and thinned to each event's `knn` nearest
    (kept where either end chose the other). A whisper of uniform weight
    keeps a thinned graph in one piece."""
    G = np.asarray(W, dtype=np.float64) ** float(power)
    np.fill_diagonal(G, 0.0)
    n = G.shape[0]
    if knn and 0 < int(knn) < n - 1:
        k = int(knn)
        nb = np.argpartition(-G, k, axis=1)[:, :k]
        keep = np.zeros_like(G, dtype=bool)
        keep[np.arange(n)[:, None], nb] = True
        keep |= keep.T
        G = np.where(keep, G, 0.0)
        live = G.sum(axis=1) > 0
        floor = 1e-6 * float(G[live][:, live].mean()) if live.any() else 0.0
        G = G + floor * np.outer(live, live)
        np.fill_diagonal(G, 0.0)
    return G


# --------------------------------------------------------------------------
# 3  Order
# --------------------------------------------------------------------------
def order(G, centroid=None):
    """Every event's place along the normalised cut's Fiedler vector.

    G is an affinity (no self-loops). Returns (idx, coord, lam2): idx sorts
    the events by coord, coord is scaled to 0..1 (nan for an event with no
    edges, sorted last), lam2 is the Laplacian's second eigenvalue -- near
    0 is a graph that falls apart in two. When `centroid` (each event's
    mean sink depth) is given, coord rises with it, so deeper sinks sit to
    the right whatever sign the eigensolver chose.
    """
    from scipy.linalg import eigh
    G = np.asarray(G, dtype=np.float64)
    n = G.shape[0]
    deg = G.sum(axis=1)
    live = np.where(deg > 0)[0]
    coord = np.full(n, np.nan)
    lam2 = None
    if live.size >= 3:
        dm = 1.0 / np.sqrt(deg[live])
        M = dm[:, None] * G[np.ix_(live, live)] * dm[None, :]
        m = live.size
        vals, vecs = eigh(M, subset_by_index=[m - 2, m - 1])
        f = vecs[:, 0] * dm                       # random-walk eigenvector
        lam2 = float(1.0 - vals[0])
        if centroid is not None:
            c = np.asarray(centroid, dtype=float)[live]
            if np.corrcoef(f, c)[0, 1] < 0:
                f = -f
        span = float(f.max() - f.min())
        coord[live] = (f - f.min()) / span if span > 0 else 0.5
    elif live.size:
        coord[live] = 0.5
    idx = np.argsort(coord, kind="stable")       # nan last
    return idx, coord, lam2


def centroid(depth):
    """Each event's mean sink row, from its depth distribution."""
    depth = np.asarray(depth, dtype=float)
    return depth @ np.arange(depth.shape[1], dtype=float)


# --------------------------------------------------------------------------
# 4  The line
# --------------------------------------------------------------------------
def sweep(W, idx, min_share=MIN_SHARE, min_events=MIN_EVENTS):
    """Every line position along `idx`, scored on the overlap matrix W.

    Position k puts the first k events of the order on the left. For each:
    the normalised cut cut/assoc(A) + cut/assoc(B), the mean overlap within
    each side and between them (self-pairs left out), and the separation
    index 1 - between / mean(within). O(n^2), from one 2-D cumulative sum.

    Returns plain lists; `best`, the k of the lowest normalised cut with at
    least `floor` events on each side (min_share of them, and never fewer
    than min_events); and `candidates`, the curve's dips -- each local
    minimum of the normalised cut, lowest first, with its separation index
    and whether it clears the floor -- for a page to offer as snap points.
    """
    idx = np.asarray(idx, dtype=int)
    n = idx.size
    if n < 2:
        raise ValueError("A line needs at least two events.")
    O = np.asarray(W, dtype=np.float64)[np.ix_(idx, idx)].copy()
    np.fill_diagonal(O, 0.0)
    P = O.cumsum(axis=0).cumsum(axis=1)
    cdeg = O.sum(axis=1).cumsum()
    total = cdeg[-1]
    k = np.arange(1, n)
    aa = P[k - 1, k - 1]                 # within A, both ways
    av = cdeg[k - 1]                     # A to everyone
    bv = total - av
    cut = av - aa
    bb = bv - cut
    with np.errstate(divide="ignore", invalid="ignore"):
        ncut = cut / av + cut / bv
        nA, nB = k.astype(float), (n - k).astype(float)
        wA = np.where(nA > 1, aa / (nA * (nA - 1)), np.nan)
        wB = np.where(nB > 1, bb / (nB * (nB - 1)), np.nan)
        btw = cut / (nA * nB)
        si = 1.0 - btw / np.nanmean(np.vstack([wA, wB]), axis=0)
    floor = max(1, int(min_events or 0),
                int(np.ceil(float(min_share) * n)))
    floor = min(floor, max(1, n // 2))          # a small recording still cuts
    ok = (k >= floor) & (n - k >= floor) & np.isfinite(ncut)
    if not ok.any():
        ok = np.isfinite(ncut)
    best = int(k[ok][np.argmin(ncut[ok])])
    return {"k": k.tolist(), "ncut": _rl(ncut), "si": _rl(si),
            "within_left": _rl(wA), "within_right": _rl(wB),
            "between": _rl(btw), "best": best, "floor": floor,
            "candidates": _dips(k, ncut, si, floor, n),
            "min_share": float(min_share), "min_events": int(min_events or 0),
            "n": int(n)}


def _dips(k, ncut, si, floor, n, prominence=0.02, most=5):
    """The local minima of the Ncut curve, lowest first."""
    from scipy.signal import find_peaks
    good = np.isfinite(ncut)
    if not good.any():
        return []
    top = float(np.max(ncut[good])) + 1.0
    y = np.where(good, ncut, top)
    # Walled at both ends, so a dip at the first or last position counts.
    at, _ = find_peaks(-np.concatenate([[top], y, [top]]),
                       prominence=prominence)
    at = sorted((int(a) - 1 for a in at), key=lambda a: y[a])
    return [{"k": int(k[a]), "ncut": _r(ncut[a]), "si": _r(si[a]),
             "clears": bool(k[a] >= floor and n - k[a] >= floor)}
            for a in at[:most]]


def cut_value(coord_sorted, k):
    """The coordinate a line at position k sits at: halfway between the
    k-th and (k+1)-th event of the order."""
    c = np.asarray(coord_sorted, dtype=float)
    k = int(min(max(k, 1), c.size - 1))
    return float((c[k - 1] + c[k]) / 2.0)


def verdict(si, small=None, n=None):
    """A line's separation index in words, for the page. `small` and `n`
    (the smaller side's size, everyone) add a word when that side is under
    SMALL_SHARE: a family that small may be odd events rather than a DS
    class, and is worth a look before it is called one."""
    if si is None or not np.isfinite(si):
        return {"word": "none", "say": "No line: too few events."}
    if si >= SEPARATE_SI:
        out = {"word": "separate",
               "say": "DS1 and DS2 sinks barely overlap: two families."}
    elif si >= PARTIAL_SI:
        out = {"word": "partial",
               "say": "DS1 and DS2 sinks overlap in part: a lean, not a gap."}
    else:
        out = {"word": "one family",
               "say": "The sinks are one family; any line here splits a blob."}
    if small is not None and n and small < SMALL_SHARE * n:
        out["small"] = int(small)
        out["say"] += (" The smaller side is %d event%s: check they are "
                       "dentate spikes." % (small, "" if small == 1 else "s"))
    return out


def scores(W, types):
    """How well any split separates sinks, on overlap matrix W: each class's
    size and mean within-overlap, the mean between, the separation index and
    the normalised cut. Types 1 and 2; anything else is left out."""
    W = np.asarray(W, dtype=np.float64)
    t = np.asarray(types)
    a, b = np.where(t == 1)[0], np.where(t == 2)[0]
    out = {"n1": int(a.size), "n2": int(b.size)}

    def _within(r):
        if r.size < 2:
            return np.nan
        blk = W[np.ix_(r, r)]
        return (blk.sum() - np.trace(blk)) / (r.size * (r.size - 1))
    w1, w2 = _within(a), _within(b)
    btw = (W[np.ix_(a, b)].mean() if a.size and b.size else np.nan)
    cut = W[np.ix_(a, b)].sum() if a.size and b.size else np.nan
    noself = W - np.diag(np.diag(W))
    va, vb = noself[a].sum(), noself[b].sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        si = 1.0 - btw / np.nanmean([w1, w2])
        ncut = cut / va + cut / vb
    out.update({"within1": _r(w1), "within2": _r(w2), "between": _r(btw),
                "si": _r(si), "ncut": _r(ncut)})
    return out


# --------------------------------------------------------------------------
# 5  Names
# --------------------------------------------------------------------------
def _namer(prof, nums_sel, rule, flip, layers):
    from . import extraction
    ns = [int(n) for n in nums_sel]

    def name(lab):
        return extraction.name_sides(np.asarray(lab, dtype=int), prof, ns,
                                     rule, flip, layers)
    return name


def classes_at(coord, cut, prof, nums_sel, rule="tort", flip=False,
               layers=None):
    """Each event's class (1 = DS1, 2 = DS2) for a line at `cut` on the
    coordinate: left of it is one side, right the other, and X-ray's rule
    says which is DS1. An event with no coordinate (no sink) joins the
    right."""
    c = np.asarray(coord, dtype=float)
    lab = np.where(np.isfinite(c), c > float(cut), True).astype(int)
    if lab.min() == lab.max():
        raise ValueError("That line leaves every event on one side.")
    prof = np.asarray(prof, dtype=float)
    return _namer(prof, nums_sel, rule, flip, layers)(lab)


def classes_k(live, k, n, prof, nums_sel, rule="tort", flip=False,
              layers=None):
    """The same, for a line at ORDER POSITION k: the first k events of
    `live` (the order, no-sink events left out) are one side, everyone else
    the other. Positions survive tied coordinates; a cut value does not."""
    lab = np.ones(int(n), dtype=int)
    lab[np.asarray(live, dtype=int)[:int(k)]] = 0
    if lab.min() == lab.max():
        raise ValueError("That line leaves every event on one side.")
    return _namer(np.asarray(prof, dtype=float), nums_sel, rule, flip,
                  layers)(lab)


def sides(idx, prof, nums_sel, rule="tort", flip=False, layers=None):
    """Which class the LEFT side is (1 or 2) at every line position 1..n-1,
    by X-ray's rule on the two sides' mean profiles -- so a page can move
    the line and renumber without asking again."""
    idx = np.asarray(idx, dtype=int)
    p = np.asarray(prof, dtype=float)[idx]
    ok = np.isfinite(p)
    cs, cn = np.nancumsum(p, axis=0), np.cumsum(ok, axis=0)
    ts, tn = cs[-1], cn[-1]
    pair = np.array([0, 1])
    out = []
    with np.errstate(divide="ignore", invalid="ignore"):
        for k in range(1, idx.size):
            left = cs[k - 1] / cn[k - 1]
            right = (ts - cs[k - 1]) / (tn - cn[k - 1])
            # Each side's mean profile as a one-row "class": name_sides
            # takes the mean of one row, which is that row.
            name = _namer(np.vstack([left, right]), nums_sel, rule, flip,
                          layers)
            out.append(int(name(pair)[0]))
    return out


# --------------------------------------------------------------------------
# One recording, start to finish
# --------------------------------------------------------------------------
def fit(A, half_ms=HALF_MS, fs=None, t0_index=None, sink=SINK_DEFAULT,
        n_bumps=N_BUMPS, smooth=SMOOTH, depth_time=False, dead=0.0,
        recentre_ms=0.0, big_third=None, knn=None, power=1.0,
        min_share=MIN_SHARE, min_events=MIN_EVENTS, rule="tort", flip=False,
        layers=None, surround_ms=50.0, sink_nums=None):
    """All five steps on one recording's split arrays (the dict
    extraction.split_arrays makes, or the cached .npz: disp, prof,
    nums_sel, nums_all). Returns the working as arrays; `view` turns it
    into what a page draws. `sink_nums`: the contacts the sink is taken
    over, when not the whole box (one hump, with sink="one"); the sides
    are still named on the whole box's profile, as every split's are."""
    disp = np.asarray(A["disp"], dtype=np.float64)
    ns = [int(n) for n in A["nums_sel"]]
    na = [int(n) for n in A["nums_all"]] or ns
    sn = [int(n) for n in sink_nums] if sink_nums is not None else ns
    fs0, t00 = time_axis(disp.shape[2], surround_ms)
    S, info = sink_dists(disp, sn, t00 if t0_index is None else t0_index,
                         half_ms, fs0 if fs is None else fs, na, sink,
                         n_bumps, smooth, depth_time, dead, recentre_ms,
                         big_third)
    W = overlap(S)
    G = affinity(W, knn, power)
    cen = centroid(info["depth"])
    idx, coord, lam2 = order(G, cen)
    live = idx[np.isfinite(coord[idx])]
    sw = sweep(W, live, min_share, min_events)
    prof = np.asarray(A["prof"], dtype=float)
    left_is = sides(live, prof, ns, rule, flip, layers)
    k = sw["best"]
    # DS1 to the left at the default line, so the picture reads the same
    # way round on every recording.
    if left_is[k - 1] == 2:
        coord = np.where(np.isfinite(coord), 1.0 - coord, coord)
        idx = np.argsort(coord, kind="stable")
        live = idx[np.isfinite(coord[idx])]
        sw = sweep(W, live, min_share, min_events)
        left_is = sides(live, prof, ns, rule, flip, layers)
        k = sw["best"]
    cut = cut_value(coord[live], k)
    types = classes_k(live, k, coord.size, prof, ns, rule, flip, layers)
    return {"S": S, "info": info, "W": W, "G": G, "idx": idx, "live": live,
            "coord": coord, "lam2": lam2, "sweep": sw, "k": k, "cut": cut,
            "types": types, "left_is": left_is, "nums_sel": ns, "sink_nums": sn,
            "params": {"half_ms": float(half_ms), "sink": sink,
                       "n_bumps": int(n_bumps) if n_bumps else None,
                       "big_third": float(big_third) if big_third else None,
                       "smooth": int(smooth),
                       "depth_time": bool(depth_time), "dead": float(dead),
                       "recentre_ms": float(recentre_ms),
                       "knn": int(knn) if knn else None,
                       "power": float(power), "min_share": float(min_share),
                       "min_events": int(min_events or 0), "rule": rule,
                       "flip": bool(flip)}}


def _blocks(O, m=MAX_MATRIX):
    """A sorted overlap matrix as at most m x m block means, self-pairs left
    out. Returns (matrix, edges): bin b holds order positions
    edges[b]..edges[b+1]-1."""
    n = O.shape[0]
    O = O.copy()
    np.fill_diagonal(O, 0.0)
    if n <= m:
        cnt = np.ones((n, n)) - np.eye(n)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(cnt > 0, O, np.nan), list(range(n + 1))
    edges = np.unique(np.linspace(0, n, m + 1).round().astype(int))
    starts = edges[:-1]
    B = np.add.reduceat(np.add.reduceat(O, starts, axis=0), starts, axis=1)
    size = np.diff(edges).astype(float)
    cnt = np.outer(size, size) - np.diag(size)
    with np.errstate(divide="ignore", invalid="ignore"):
        B = np.where(cnt > 0, B / cnt, np.nan)
    return B, edges.tolist()


def view(F, k=None, cut=None, max_matrix=MAX_MATRIX, slim=False):
    """What a page draws, as plain lists. `k` (a line position) or `cut` (a
    coordinate) moves the line; neither keeps the default. `slim`: the line
    alone -- order, sweep, sides, classes, scores -- for a Bite line on one
    hump, drawn over the whole box's raster (2026-11-13).

    order       event indices left to right; coord, each event's place
    sweep       ncut, si, within/between at every line position k = 1..n-1
    left_is     which class the left side is at each k (1 = DS1)
    raster      events in order x contacts (nums_sel): the sink's depth
                distribution, each row scaled to its own peak
    bumps       per event (in event order, not display order): how many
                bumps its profile had, and the kept ones as [first, last]
                contact numbers; peaks, each kept bump's deepest
                contact; short, how many had fewer than two;
                third_big, how many had a third bump at least half the
                second (a third sink band: worth a narrower box)
    matrix      the overlap matrix in the same order, block-averaged to at
                most max_matrix a side; edges map its bins to positions
    line        {k, cut, default_k}; types, each event's class there
    scores      sizes, within, between, separation index, normalised cut
    verdict     that separation index in words: separate / partial / one
                family (the page's sentence under the line)
    """
    live = np.asarray(F["live"], dtype=int)
    coord = np.asarray(F["coord"], dtype=float)
    cs = coord[live]
    if cut is not None and k is None:
        k = int(np.searchsorted(cs, float(cut), side="right"))
    k = int(F["k"] if k is None else min(max(int(k), 1), live.size - 1))
    c = cut_value(cs, k) if cut is None else float(cut)
    lab = np.ones(coord.size, dtype=int)            # right side, and no-sink
    lab[live[:k]] = 0
    left = F["left_is"][k - 1]
    types = np.where(lab == 0, left, 3 - left)
    sw = F["sweep"]
    if slim:
        sc = scores(F["W"], types)
        return {
            "n": int(coord.size),
            "order": [int(i) for i in F["idx"]],
            "coord": _rl(coord, 4),
            "no_sink": [int(i) for i in np.where(F["info"]["flag"])[0]],
            "lam2": _r(F["lam2"]),
            "contacts": [int(n) for n in F["nums_sel"]],
            "sink_contacts": [int(n) for n in F.get("sink_nums") or F["nums_sel"]],
            "sweep": {key: sw[key] for key in ("k", "ncut", "si", "within_left",
                                               "within_right", "between", "best",
                                               "floor", "candidates", "min_share",
                                               "min_events")},
            "left_is": list(F["left_is"]),
            "line": {"k": k, "cut": _r(c, 5), "default_k": int(F["k"]),
                     "default_cut": _r(F["cut"], 5)},
            "types": [int(t) for t in types],
            "scores": sc,
            "verdict": verdict(sc["si"], min(sc["n1"], sc["n2"]), coord.size),
            "params": dict(F["params"]),
        }
    depth = np.asarray(F["info"]["depth"], dtype=float)[F["idx"]]
    peak = depth.max(axis=1, keepdims=True)
    raster = np.divide(depth, peak, out=np.zeros_like(depth), where=peak > 0)
    B, edges = _blocks(np.asarray(F["W"])[np.ix_(F["idx"], F["idx"])],
                       max_matrix)
    ns = [int(n) for n in F["nums_sel"]]
    found = np.asarray(F["info"]["found"], dtype=int)
    pk = F["info"].get("peaks")
    if pk is None:
        # A fit made before peaks were kept: the drawn distribution's.
        dd = np.asarray(F["info"]["depth"], dtype=float)
        pk = [[int(a + np.argmax(dd[i, a:b + 1])) for a, b in sp]
              for i, sp in enumerate(F["info"]["spans"])]
    sc = scores(F["W"], types)
    return {
        "n": int(coord.size),
        "order": [int(i) for i in F["idx"]],
        "coord": _rl(coord, 4),
        "no_sink": [int(i) for i in np.where(F["info"]["flag"])[0]],
        "weak": [int(i) for i in np.where(F["info"]["weak"])[0]],
        "lam2": _r(F["lam2"]),
        "contacts": [int(n) for n in F["nums_sel"]],
        "sweep": {key: sw[key] for key in ("k", "ncut", "si", "within_left",
                                           "within_right", "between", "best",
                                           "floor", "candidates", "min_share",
                                           "min_events")},
        "left_is": list(F["left_is"]),
        "raster": [_rl(row, 3) for row in raster],
        "bumps": {"found": found.tolist(),
                  "kept": [[[ns[a], ns[b]] for a, b in sp]
                           for sp in F["info"]["spans"]],
                  # Each kept bump's deepest point, as a contact number,
                  # shallowest bump first (in event order).
                  "peaks": [[ns[p] for p in row] for row in pk],
                  "short": int(sum(len(sp) < 2 for sp in F["info"]["spans"])),
                  # What the sink is: "humps" (the recording's two, parted
                  # at `hump_at`, the first contact of the bottom one) or
                  # "bumps" (each event's own two biggest); and how many
                  # events have a notch inside a hump (a camel), which
                  # "humps" takes whole and "bumps" would split.
                  "sink": F["params"].get("sink"),
                  "hump_at": (ns[F["info"]["cut"]] if F["info"].get("cut")
                              is not None else None),
                  "camel": int(np.asarray(F["info"].get(
                      "camel", np.zeros(0, dtype=bool))).sum()),
                  # A third sink band in the box: the top two are then a
                  # ranking, and the line may be following it.
                  "third_big": int((np.asarray(F["info"]["third"])
                                    >= THIRD_BIG).sum())},
        "matrix": [_rl(row, 3) for row in B],
        "edges": edges,
        "line": {"k": k, "cut": _r(c, 5), "default_k": int(F["k"]),
                 "default_cut": _r(F["cut"], 5)},
        "types": [int(t) for t in types],
        "scores": sc,
        "verdict": verdict(sc["si"], min(sc["n1"], sc["n2"]), coord.size),
        "params": dict(F["params"]),
    }
