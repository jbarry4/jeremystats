# -*- coding: utf-8 -*-
"""blobs.py -- Blob Analysis: the top and the bottom sink of every dentate
spike, timed and sized, DS1 and DS2 apart, one recording at a time (asked
2026-11-12).

THE ASK, in the user's words: "separate it out to top blob and bottom blob
analysis of DS1 and DS2 ... how long the sink lasts ... what its activity
curve looks like; is it fast and strong; or slow and diffused ... and
numbers/averages associated with that ... For the groups we also want
histogram related data, since sometimes it seems like the PTEN are either
weaker DS or high power ones."

THE TWO BLOBS. Each event's depth profile in the box -- its CSD (sinks
negative, CSD = -sigma d2V/dz2) averaged over 3 ms either side of the
stamp -- is cut into bumps exactly as sinkcut.bumps cuts it: every stretch of
sink between two zero crossings, the band's ends closing one too. The two
largest by area are the event's blobs; the shallower one (the smaller row of
`disp`) is the TOP blob, the other the BOTTOM -- one per blade of the
dentate. An event with ONE bump gives it to whichever blob it sits nearer:
the recording's usual top and bottom depths (the median centre of each, from
the same class's two-bump events). A single bump that covers both usual
depths is the two blades run together ("merged") and counts as neither, as
does a bump with no usual depths to go by; the missing blob is None.

THE ACTIVITY CURVE of a blob is its sink over time at its own depth: minus
the CSD averaged over the blob's contacts (the event's own bump at the
stamp), over the whole -50..+50 ms. Up is sink.

THE NUMBERS, every one measured on each event and only then summarised
(median, with mean, SD and quartiles beside it):
  peak        the curve's highest sink within PEAK_MS of the stamp
  latency_ms  when it peaks, after the stamp (negative: before); the vertex
              of a parabola through the top three samples, so finer than 1 ms
  fwhm_ms     how long the sink lasts: the time the curve stays above half
              its peak. Each half-peak crossing is found by walking out from
              the peak to the first sample below half and placing the
              crossing on the straight line between it and the sample before
  rise_ms     10% to 90% of the peak, on the way up; decay_ms, 90% to 10% on
              the way down (crossings placed the same way)
  sharpness   peak / area_t, per ms: one over the sink's equivalent duration.
              High is fast and strong, low slow and diffuse. It has no
              amplitude in it -- a weak sink of the same shape scores the
              same -- so it is read beside `peak`, not instead of it
  area_t      the sink over time at the blob's depth: the curve summed over
              its sink episode (the stretch around the peak where the curve
              stays above zero) times the sample step
  area        the total sink, over time AND depth: -CSD, sink side only,
              summed over the blob's contacts and the same episode, times
              the sample step and the contact spacing
  spread_um   the blob's depth at half its peak, on the stamp profile, with
              the crossings placed between contacts the same way, times the
              spacing
A number the window cuts off -- a curve that never falls below half (or 10%,
or zero) before the window's edge, a blob at half peak where the band ends
-- is None, and counted as OPEN so the page can say how many were dropped.

THE UNIT IS THE RECORDING. One recording is one mouse; its events are not
independent of each other. Group averages are averages of recording
medians, and only for groups of more than two recordings. Every pooled
distribution weights each recording equally (each recording's events
carry 1 / its count), every bootstrap resamples recordings, not events, and
every permutation shuffles recording labels.

FOR GROUPS (`group_compare`, any grouping: CTL vs PTEN, separable vs not,
a hand-picked set): what averages hide --
  histograms on shared bins, each recording's and each group's (the mean
  of its recordings'); weighted ECDFs; the shift function (CTL vs PTEN at
  each decile of the equal-weight distributions, with recording-bootstrap
  CIs); and three tests on recordings: Mann-Whitney on the medians
  (location), Brown-Forsythe on the medians (spread: "are PTEN mice more
  varied?"; its p by permuting recording labels, because the F table is
  far too generous at four or five recordings a group), and a permutation
  of recording labels on the Anderson-Darling distance between the
  equal-weight distributions (shape). And a
  bimodality hint per group: Hartigan's dip (rcstats' port) and Sarle's
  bimodality coefficient, on the recording medians ("weak mice and strong
  mice?") and on the pooled events ("weak DS and strong DS?").

HONEST P VALUES. `compare_all` runs every measure and gives each test its
raw p and the Benjamini-Hochberg q across everything it ran. A result is a
"finding" only when q < 0.05 (and, for the medians, the bootstrap CI of the
difference leaves out zero); p < 0.05 alone is a "hint", never a finding.

THE FILTER. `disp` is the CSD as X-ray draws it, 5-100 Hz. That band rounds
off slow sinks: a sink that builds over tens of ms loses its slow part, so
its width, rise and decay read shorter than they are. The timing numbers
here may be worth redoing on a wider band (e.g. 1-300 Hz); the depth numbers
care less.

Numpy and scipy only; no Flask. JSON-friendly outputs: lists, floats to 4
significant figures, None for missing.
"""
from __future__ import annotations

import itertools

import numpy as np

from . import sinkcut

HALF_MS = sinkcut.HALF_MS      # the stamp profile: this many ms either side
PEAK_MS = 10.0                 # the curve's peak is looked for this near the stamp
BLOBS = ("top", "bottom")
MIN_RECS = 3                   # averages and tests need more than two recordings
MIN_EVENTS = 5                 # a recording with fewer events is left out
N_BOOT = 2000
N_PERM = 5000
N_BINS = 20
N_GRID = 512                   # the shared x grid the ECDFs are worked on
N_ECDF = 101                   # ... and the one they are drawn on
N_PSEUDO = 50                  # quantiles per recording for the pooled dip
N_DIP_SIM = 1000
DECILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
BC_SPLIT = 5.0 / 9.0           # a uniform's bimodality coefficient
ALPHA = 0.05
SEED = 0

MEASURES = [
    {"id": "peak", "words": "Peak sink", "unit": "CSD",
     "higher": "a stronger sink"},
    {"id": "latency_ms", "words": "When the sink peaks, after the stamp",
     "unit": "ms", "higher": "a later peak (below zero: before the stamp)"},
    {"id": "fwhm_ms", "words": "How long the sink lasts (time above half "
     "its peak)", "unit": "ms", "higher": "a longer sink"},
    {"id": "rise_ms", "words": "Rise time, 10% to 90% of the peak",
     "unit": "ms", "higher": "a slower build"},
    {"id": "decay_ms", "words": "Decay time, 90% to 10% of the peak",
     "unit": "ms", "higher": "a slower fade"},
    {"id": "sharpness", "words": "Sharpness: peak over the sink's area in "
     "time", "unit": "1/ms",
     "higher": "fast and strong; lower is slow and diffuse"},
    {"id": "area_t", "words": "Sink over time, at the blob's depth",
     "unit": "CSD·ms", "higher": "more sink at that depth"},
    {"id": "area", "words": "Total sink, over time and depth",
     "unit": "CSD·ms·µm", "higher": "more sink in all"},
    {"id": "spread_um", "words": "Depth spread (depth above half its peak)",
     "unit": "µm", "higher": "a sink spread over more depth"},
]
MEASURE_IDS = tuple(m["id"] for m in MEASURES)
# A number the window can cut off, and the crossing that decides it.
CAN_OPEN = ("fwhm_ms", "rise_ms", "decay_ms", "sharpness", "area_t", "area",
            "spread_um")
TESTS = ("location", "spread", "shape", "bimodal")

def _r(v, n=4):
    """A float for JSON: n significant figures, None for nan/inf/None."""
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
# One event
# --------------------------------------------------------------------------
def _fill(block, pos):
    """One event's band (contacts x time) with NaN filled: a NaN between two
    good contacts is interpolated across depth, sample by sample; a NaN at
    the band's ends (nothing beyond it to go by) is 0 -- no sink. Returns the
    block and how many contacts had a NaN."""
    bad = ~np.isfinite(block)
    if not bad.any():
        return block, 0
    out = block.copy()
    for t in np.flatnonzero(bad.any(axis=0)):
        ok = ~bad[:, t]
        if not ok.any():
            out[:, t] = 0.0
            continue
        out[~ok, t] = np.interp(pos[~ok], pos[ok], block[ok, t],
                                left=0.0, right=0.0)
    return out, int(bad.any(axis=1).sum())


def _cross(y, i, level, step):
    """Walking from sample i (at or above `level`) in direction `step`
    (+1 or -1), where y first falls below level: a fractional index on the
    straight line between the last sample at or above it and the first
    below. None when it never does before the array ends."""
    seg = y[i::step] if step > 0 else y[i::-1]
    below = np.flatnonzero(seg < level)
    if below.size == 0:
        return None
    k = int(below[0])
    if k == 0:
        return float(i)
    prev, cur = float(seg[k - 1]), float(seg[k])
    frac = (prev - level) / (prev - cur) if prev != cur else 0.0
    return i + step * (k - 1 + frac)


def _vertex(y, i):
    """The peak's fractional index: the vertex of the parabola through
    samples i-1, i, i+1 (i itself at an edge or a flat top)."""
    if 0 < i < y.size - 1:
        a, b, c = float(y[i - 1]), float(y[i]), float(y[i + 1])
        den = a - 2.0 * b + c
        if den < 0:
            return i + 0.5 * (a - c) / den
    return float(i)


def _peak(curve, t0, w):
    """The sink's peak: the highest local maximum of sink within w samples
    of the stamp (a sample above zero and at least as high as both
    neighbours, inside the window) -- so a bigger sink climbing in from
    the window's edge does not take the place of this event's own. With
    none, the window's highest sample, flagged as an edge. Returns (index,
    edge)."""
    lo, hi = max(0, t0 - w), min(curve.size, t0 + w + 1)
    j = np.arange(lo + 1, hi - 1)
    c = curve[j]
    top = j[(c >= curve[j - 1]) & (c >= curve[j + 1]) & (c > 0)]
    if top.size:
        return int(top[np.argmax(curve[top])]), False
    return lo + int(np.argmax(curve[lo:hi])), True


def _bumps2(p):
    """sinkcut's bumps of a stamp profile (sink positive), the two largest
    by area kept, shallowest first. Returns (how many there were, kept as
    (first, past-last, area), the third's area over the second's)."""
    bb = sorted(sinkcut.bumps(np.maximum(p, 0.0)), key=lambda b: -b[2])
    third = bb[2][2] / bb[1][2] if len(bb) > 2 and bb[1][2] > 0 else 0.0
    return len(bb), sorted(bb[:2]), float(third)


def _centre(p, a, b, pos):
    w = np.maximum(p[a:b], 0.0)
    s = float(w.sum())
    return float(w @ pos[a:b] / s) if s > 0 else float(pos[a:b].mean())


def _blob(block, p, a, b, pos, wdepth, t0, fs, spacing, peak_ms):
    """Every number of one blob: rows a..b-1 of the band (`block`, contacts
    x time, sinks negative), `p` the stamp profile (sink positive)."""
    dt = 1000.0 / float(fs)
    curve = -block[a:b].mean(axis=0)                     # up = sink
    n_t = curve.size
    ip, edge = _peak(curve, t0, max(1, int(round(float(peak_ms) / dt))))
    pk = float(curve[ip])
    out = {"curve": curve, "edge_peak": edge, "open": {}}
    out["peak"] = pk
    out["latency_ms"] = (_vertex(curve, ip) - t0) * dt
    if not pk > 0:                                       # no sink in the window
        for m in CAN_OPEN:
            out[m] = np.nan
            out["open"][m] = False
        out["spread_um"] = _spread(p, a, b, pos, spacing, out)
        return out
    cut = {}
    for name, frac in (("h", 0.5), ("r10", 0.1), ("r90", 0.9), ("z", 0.0)):
        cut[name] = (_cross(curve, ip, frac * pk, -1),
                     _cross(curve, ip, frac * pk, +1))

    def span(x, y, m):
        out["open"][m] = x is None or y is None
        out[m] = np.nan if out["open"][m] else (y - x) * dt
    span(cut["h"][0], cut["h"][1], "fwhm_ms")
    span(cut["r10"][0], cut["r90"][0], "rise_ms")
    span(cut["r90"][1], cut["r10"][1], "decay_ms")
    zl, zr = cut["z"]
    shut = zl is not None and zr is not None
    for m in ("area_t", "area", "sharpness"):
        out["open"][m] = not shut
    if shut:
        s0, s1 = int(np.ceil(zl)), int(np.floor(zr))
        out["area_t"] = float(curve[s0:s1 + 1].sum()) * dt
        sink = np.maximum(0.0, -block[a:b, s0:s1 + 1]).sum(axis=1)
        out["area"] = float(sink @ wdepth[a:b]) * dt * spacing
        out["sharpness"] = pk / out["area_t"] if out["area_t"] > 0 else np.nan
    else:
        out["area_t"] = out["area"] = out["sharpness"] = np.nan
    out["spread_um"] = _spread(p, a, b, pos, spacing, out)
    return out


def _spread(p, a, b, pos, spacing, out):
    """The blob's depth above half its peak on the stamp profile, in um.
    Open (None) when the band ends before the profile falls below half."""
    k = a + int(np.argmax(p[a:b]))
    half = float(p[k]) / 2.0
    up, down = _cross(p, k, half, -1), _cross(p, k, half, +1)
    out["open"]["spread_um"] = up is None or down is None
    if out["open"]["spread_um"] or not half > 0:
        return np.nan
    idx = np.arange(pos.size, dtype=float)
    return float(np.interp(down, idx, pos) - np.interp(up, idx, pos)) * spacing


# --------------------------------------------------------------------------
# Every event of one recording
# --------------------------------------------------------------------------
def _refs(cen, kind, classes):
    """The usual depth of each blob, per class: the median centre of the
    top and bottom blobs of the class's two-bump events (all two-bump
    events when the class has none)."""
    two = kind == "two"
    out = {}
    for c in set(classes.tolist()):
        m = two & (classes == c)
        if not m.any():
            m = two
        out[c] = ((float(np.median(cen[m, 0])), float(np.median(cen[m, 1])))
                  if m.any() else None)
    return out


def _hump_spans(p, halves):
    """An event's blobs under the recording's two humps: in each half, from
    its first to its last contact with sink at the stamp (a notch inside a
    hump stays inside its blob). Returns ({blob: (first, past-last)}, how
    many of its humps have a notch, the bumps across the band)."""
    out, notched = {}, 0
    names = ("top", "bottom") if len(halves) == 2 else (None,)
    for name, (a, b) in zip(names, halves):
        seg = np.maximum(p[a:b], 0.0)
        if not (seg > 0).any():
            continue
        nz = np.flatnonzero(seg > 0)
        out[name] = (a + int(nz[0]), a + int(nz[-1]) + 1)
        notched += len(sinkcut.bumps(seg)) > 1
    return out, notched, len(sinkcut.bumps(np.maximum(p, 0.0)))


def event_blobs(disp, band_rows, spacing_um, fs=1000.0, t0=50,
                half_ms=HALF_MS, classes=None, peak_ms=PEAK_MS,
                one_bump="nearest", sink=None):
    """The two blobs of every event, and every number of each.

    disp        events x contacts x samples, the CSD (sinks negative)
    band_rows   the rows of `disp` in the box (sinkcut.band_rows makes them
                from nums_all and nums_sel); taken shallow to deep, so the
                smaller row is the top
    spacing_um  the contact spacing (from the probe: 30 for the H10-D,
                50 for the linear arrays -- dspca.spacing_for)
    fs, t0      samples per second, and the stamp's sample
    half_ms     the stamp profile is averaged over this many ms either side
    classes     each event's class (0 = DS one kind, 1 = DS1, 2 = DS2);
                used to place single bumps, and kept. None: all 0
    peak_ms     the curve's peak is looked for this many ms either side
    one_bump    "nearest" (place a single bump by the usual depths) or
                "drop" (an event with one bump has neither blob)

    Returns numpy, not JSON (`event_json` makes JSON of it):
      n, t_ms (T), fs, t0, spacing_um, rows (the band rows, sorted)
      classes (E), found (E: bumps on each profile), third (E: the third
        bump's area over the second's -- at sinkcut.THIRD_BIG or more, a
        third sink band is in the box and "the two largest" is a ranking
        that can swap from event to event), nan_rows (E),
      kind (E: "two", "one", "merged", "unplaced", "none")
      top / bottom: each measure (E floats, nan where missing or open),
        span (E x 2: first and last row of `disp`, -1 missing),
        curve (E x T, up = sink, nan rows where missing),
        has (E), from_one (E: the blob is a single bump, placed),
        edge_peak (E: the peak sat at the search window's edge),
        open (measure -> E: cut off by the window)
    """
    d = np.asarray(disp, dtype=np.float64)
    n, _, n_t = d.shape
    rows = np.array(sorted(int(r) for r in band_rows), dtype=int)
    pos = rows.astype(float)
    wdepth = np.gradient(pos) if pos.size > 1 else np.ones(1)
    cls = (np.zeros(n, dtype=int) if classes is None
           else np.asarray(classes, dtype=int).ravel())
    if cls.size != n:
        raise ValueError("%d classes for %d events." % (cls.size, n))
    t0 = int(t0)
    h = max(0, int(round(float(half_ms) * float(fs) / 1000.0)))
    found = np.zeros(n, dtype=int)
    third = np.zeros(n)
    nan_rows = np.zeros(n, dtype=int)
    kind = np.empty(n, dtype=object)
    cen = np.full((n, 2), np.nan)
    blocks, profs = [], []
    for i in range(n):
        blk, nan_rows[i] = _fill(d[i, rows, :], pos)
        blocks.append(blk)
        profs.append(-blk[:, max(0, t0 - h):min(n_t, t0 + h + 1)].mean(axis=1))
    # THE TWO BLOBS ARE THE RECORDING'S TWO HUMPS (2026-11-12, as the Bite
    # line's): each event's own two biggest bumps put the two halves of a
    # notched ("camel") hump in as top and bottom wherever the notch touched
    # zero. Each event's blob is its sink inside the hump, notch and all.
    # A recording whose mean has one bump only keeps the per-event bumps.
    sink = str(sink or sinkcut.SINK_DEFAULT)
    cut = (sinkcut.hump_cut(-np.mean(profs, axis=0))
           if sink == "humps" and n else None)
    camel = np.zeros(n, dtype=int)
    placed = []
    if cut is not None:
        halves = [(0, cut), (cut, rows.size)]
        for i in range(n):
            sp, camel[i], found[i] = _hump_spans(profs[i], halves)
            kind[i] = {0: "none", 1: "one"}.get(len(sp), "two")
            placed.append(sp)
    else:
        sink = "bumps"
        kept = []
        for i in range(n):
            p = profs[i]
            found[i], bb, third[i] = _bumps2(p)
            kind[i] = {0: "none", 1: "one"}.get(len(bb), "two")
            for j, (a, b, _) in enumerate(bb):
                cen[i, j] = _centre(p, a, b, pos)
            kept.append(bb)
        refs = _refs(cen, kind, cls)
        for i in range(n):
            placed.append(_place(kept[i], cen[i], refs.get(cls[i]), kind, i,
                                 pos, one_bump))
    ev = {"n": int(n), "fs": float(fs), "t0": t0,
          "t_ms": (np.arange(n_t) - t0) * 1000.0 / float(fs),
          "spacing_um": float(spacing_um), "rows": rows, "classes": cls,
          "found": found, "third": third, "nan_rows": nan_rows,
          "kind": kind, "sink": sink, "camel": camel,
          "hump_row": None if cut is None else int(rows[cut]),
          "half_ms": float(half_ms), "peak_ms": float(peak_ms)}
    for blob in BLOBS:
        ev[blob] = _empty(n, n_t)
    for i in range(n):
        for blob, (a, b) in placed[i].items():
            x = _blob(blocks[i], profs[i], a, b, pos, wdepth, t0, fs,
                      float(spacing_um), peak_ms)
            _put(ev[blob], i, x, (rows[a], rows[b - 1]),
                 kind[i] == "one")
    return ev


def _place(bb, cen, ref, kind, i, pos, one_bump):
    """Which kept bump is which blob: {blob: (first, past-last)}."""
    if len(bb) == 2:
        return {"top": bb[0][:2], "bottom": bb[1][:2]}
    if len(bb) != 1:
        return {}
    if one_bump != "nearest" or ref is None:
        kind[i] = "unplaced"
        return {}
    a, b = bb[0][:2]
    if pos[a] <= ref[0] and pos[b - 1] >= ref[1]:
        kind[i] = "merged"                  # both blades in one bump
        return {}
    near = "top" if abs(cen[0] - ref[0]) <= abs(cen[0] - ref[1]) else "bottom"
    return {near: (a, b)}


def _empty(n, n_t):
    b = {m: np.full(n, np.nan) for m in MEASURE_IDS}
    b.update({"span": np.full((n, 2), -1, dtype=int),
              "curve": np.full((n, n_t), np.nan),
              "has": np.zeros(n, dtype=bool),
              "from_one": np.zeros(n, dtype=bool),
              "edge_peak": np.zeros(n, dtype=bool),
              "open": {m: np.zeros(n, dtype=bool) for m in CAN_OPEN}})
    return b


def _put(b, i, x, span, from_one):
    for m in MEASURE_IDS:
        b[m][i] = x[m]
    for m in CAN_OPEN:
        b["open"][m][i] = bool(x["open"].get(m, False))
    b["span"][i] = span
    b["curve"][i] = x["curve"]
    b["has"][i] = True
    b["from_one"][i] = bool(from_one)
    b["edge_peak"][i] = bool(x["edge_peak"])


def event_json(ev, curves=True):
    """`event_blobs`' arrays as JSON: lists, 4 significant figures, None
    for missing. curves=False leaves the E x T curves out."""
    out = {k: ev[k] for k in ("n", "fs", "t0", "spacing_um", "half_ms",
                              "peak_ms")}
    out.update({"t_ms": _rl(ev["t_ms"]), "rows": ev["rows"].tolist(),
                "classes": ev["classes"].tolist(),
                "found": ev["found"].tolist(), "third": _rl(ev["third"], 3),
                "nan_rows": ev["nan_rows"].tolist(),
                "kind": list(ev["kind"])})
    for blob in BLOBS:
        b = ev[blob]
        o = {m: _rl(b[m]) for m in MEASURE_IDS}
        o["span"] = [None if s[0] < 0 else [int(s[0]), int(s[1])]
                     for s in b["span"]]
        for k in ("has", "from_one", "edge_peak"):
            o[k] = b[k].tolist()
        o["open"] = {m: b["open"][m].tolist() for m in CAN_OPEN}
        if curves:
            o["curve"] = [_rl(c) if h else None
                          for c, h in zip(b["curve"], b["has"])]
        out[blob] = o
    return out


# --------------------------------------------------------------------------
# One recording, summarised
# --------------------------------------------------------------------------
def _summ(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not x.size:
        return {"n": 0, "median": None, "mean": None, "sd": None,
                "q25": None, "q75": None}
    q25, med, q75 = np.percentile(x, [25, 50, 75])
    return {"n": int(x.size), "median": _r(med), "mean": _r(x.mean()),
            "sd": _r(x.std(ddof=1)) if x.size > 1 else None,
            "q25": _r(q25), "q75": _r(q75)}


def _mean_sem(c):
    """Mean and SEM down axis 0 of the rows that are there."""
    c = np.asarray(c, dtype=float)
    c = c[np.isfinite(c).all(axis=1)] if c.size else c
    if not c.shape[0]:
        return {"n": 0, "mean": None, "sem": None}
    sem = (c.std(axis=0, ddof=1) / np.sqrt(c.shape[0])
           if c.shape[0] > 1 else None)
    return {"n": int(c.shape[0]), "mean": _rl(c.mean(axis=0)),
            "sem": _rl(sem) if sem is not None else None}


def recording_summary(ev, classes=None):
    """One recording's blobs, per class and blob: the numbers' medians (with
    mean, SD, quartiles) and the mean activity curve with its SEM.

    classes overrides the ones `event_blobs` kept (0 = DS one kind, 1 =
    DS1, 2 = DS2). Returns JSON:
      n, t_ms, spacing_um, classes (E), kinds ({kind: count}),
      third_big (events whose third bump is at least half the second's:
        where that is common, top and bottom may be swapping bands),
      cls: {"all", and "0" / "1" / "2" as present: {n, top, bottom}}, each
        blob {n (events that have it), missing, from_one, edge_peak,
              stats: {measure: {n, median, mean, sd, q25, q75, open}},
              curve: {n, mean, sem}},
      values: {blob: {measure: E values, None where missing or open}} --
        what `group_compare` pools.
    """
    cls = np.asarray(ev["classes"] if classes is None else classes,
                     dtype=int).ravel()
    if cls.size != ev["n"]:
        raise ValueError("%d classes for %d events." % (cls.size, ev["n"]))
    kinds = {}
    for k in ev["kind"]:
        kinds[k] = kinds.get(k, 0) + 1
    out = {"n": ev["n"], "t_ms": _rl(ev["t_ms"]),
           "spacing_um": ev["spacing_um"], "classes": cls.tolist(),
           "kinds": kinds,
           "third_big": int((np.asarray(ev["third"])
                             >= sinkcut.THIRD_BIG).sum()),
           # What a blob is ("humps": the recording's two; "bumps": each
           # event's own two biggest), and how many events have a notch
           # inside a hump -- taken whole under humps.
           "sink": ev.get("sink", "bumps"),
           "camel": int((np.asarray(ev.get("camel", np.zeros(0))) > 0).sum()),
           "cls": {},
           "values": {blob: {m: _rl(ev[blob][m]) for m in MEASURE_IDS}
                      for blob in BLOBS}}
    groups = [("all", np.ones(cls.size, dtype=bool))]
    groups += [(str(c), cls == c) for c in sorted(set(cls.tolist()))]
    for key, m in groups:
        entry = {"n": int(m.sum())}
        for blob in BLOBS:
            b = ev[blob]
            has = m & b["has"]
            st = {}
            for meas in MEASURE_IDS:
                st[meas] = _summ(b[meas][has])
                st[meas]["open"] = (int((b["open"][meas] & has).sum())
                                    if meas in CAN_OPEN else 0)
            entry[blob] = {"n": int(has.sum()),
                           "missing": int((m & ~b["has"]).sum()),
                           "from_one": int((has & b["from_one"]).sum()),
                           "edge_peak": int((has & b["edge_peak"]).sum()),
                           "stats": st, "curve": _mean_sem(b["curve"][has])}
        out["cls"][key] = entry
    return out


def recording(A, spacing_um, classes=None, surround_ms=50.0, **kw):
    """`event_blobs` then `recording_summary`, on one recording's split
    arrays (extraction.split_arrays, or its cached .npz: disp, nums_sel,
    nums_all). Returns (summary, ev)."""
    disp = np.asarray(A["disp"], dtype=np.float64)
    ns = [int(x) for x in A["nums_sel"]]
    na = [int(x) for x in A["nums_all"]] or ns
    fs, t0 = sinkcut.time_axis(disp.shape[2], surround_ms)
    ev = event_blobs(disp, sinkcut.band_rows(na, ns), spacing_um, fs=fs,
                     t0=t0, classes=classes, **kw)
    return recording_summary(ev), ev


# --------------------------------------------------------------------------
# Distributions with every recording weighted the same
# --------------------------------------------------------------------------
def _grid(vals, n=N_GRID):
    """A shared x grid: every value when there are few, else the pooled
    values' quantiles (ends included)."""
    allv = np.concatenate(vals)
    u = np.unique(allv)
    if u.size <= n:
        return u
    return np.unique(np.quantile(allv, np.linspace(0.0, 1.0, n)))


def _ecdfs(vals, grid):
    """Each recording's ECDF on the grid: recordings x grid."""
    return np.vstack([np.searchsorted(np.sort(v), grid, side="right") / v.size
                      for v in vals])


def _quant(F, grid, qs):
    """Quantiles of mixture CDFs (rows of F, on `grid`): the first grid
    value where F reaches q. F may be 1-D or n x grid."""
    F = np.atleast_2d(F)
    q = np.asarray(qs, dtype=float)
    at = (F[:, None, :] >= q[None, :, None] - 1e-9).argmax(axis=2)
    return grid[at]


def _hist(vals, edges):
    """Each recording's share of its events in each bin, and below / above
    the bins."""
    rows, under, over = [], [], []
    for v in vals:
        c, _ = np.histogram(v, edges)
        rows.append(c / v.size)
        under.append(float((v < edges[0]).sum()) / v.size)
        over.append(float((v > edges[-1]).sum()) / v.size)
    return np.vstack(rows), np.asarray(under), np.asarray(over)


def _bc(x):
    """Sarle's bimodality coefficient (sample-size corrected); above 5/9
    leans two-humped. None under 4 values. Skew alone also raises it."""
    from scipy import stats
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < 4 or np.ptp(x) == 0:
        return None
    g = stats.skew(x, bias=False)
    k = stats.kurtosis(x, bias=False)
    return float((g * g + 1.0) / (k + 3.0 * (n - 1) ** 2 / ((n - 2) * (n - 3))))


_DIP_NULL = {}


def _dip(x, p_value=True):
    """Hartigan's dip (rcstats' port of R's diptest) and, with 10 or more
    values, its p against the uniform, simulated once per sample size."""
    from . import rcstats
    x = np.asarray(x, dtype=float)
    if x.size < 4:
        return None, None
    d = float(rcstats.dip_statistic(x))
    if not p_value or x.size < 10:
        return d, None
    n = int(x.size)
    if n not in _DIP_NULL:
        rng = np.random.default_rng(SEED)
        _DIP_NULL[n] = np.sort([rcstats.dip_statistic(rng.random(n))
                                for _ in range(N_DIP_SIM)])
    null = _DIP_NULL[n]
    ge = null.size - np.searchsorted(null, d - 1e-12, side="left")
    return d, float((1 + ge) / (1 + null.size))


def _bimodal(meds, vals):
    """Two humps? On the recording medians (a real test, at 10 or more
    recordings) and on the pooled events, each recording standing in as
    N_PSEUDO of its own quantiles (a hint only: events are not
    independent, so no p)."""
    dm, pm = _dip(meds)
    pseudo = np.concatenate([np.quantile(v, (np.arange(N_PSEUDO) + 0.5)
                                         / N_PSEUDO) for v in vals])
    de, _ = _dip(pseudo, p_value=False)
    bm, be = _bc(meds), _bc(pseudo)
    return {"medians": {"n": int(len(meds)), "dip": _r(dm), "p": _r(pm),
                        "bc": _r(bm),
                        "hint": bool(pm < ALPHA) if pm is not None
                        else (bm is not None and bm > BC_SPLIT)},
            "events": {"dip": _r(de), "bc": _r(be),
                       "hint": be is not None and be > BC_SPLIT}}


# --------------------------------------------------------------------------
# Groups
# --------------------------------------------------------------------------
def _values(rec, blob, measure, cls):
    v = np.asarray([np.nan if x is None else x
                    for x in rec["values"][blob][measure]], dtype=float)
    if str(cls) != "all":
        v = v[np.asarray(rec["classes"]) == int(cls)]
    return v[np.isfinite(v)]


def _boot_rows(rng, r, n_boot):
    """Recording resamples as weights: n_boot x r, each row adding to 1."""
    pick = rng.integers(0, r, size=(n_boot, r))
    w = np.zeros((n_boot, r))
    np.add.at(w, (np.arange(n_boot)[:, None], pick), 1.0)
    return w / r, pick


def _ad(FA, FB, H):
    """Anderson-Darling distance between mixture CDFs (rows of FA, FB) on
    the pooled mixture H: sum (FA - FB)^2 / (H (1 - H)) dH."""
    dH = np.diff(np.concatenate([[0.0], H]))
    w = H * (1.0 - H)
    ok = w > 1e-12
    return (((FA - FB)[..., ok]) ** 2 / w[ok] * dH[ok]).sum(axis=-1)


def _ks(FA, FB, H=None):
    return np.abs(FA - FB).max(axis=-1)


def _splits(r, ra, n_perm, rng):
    """Recording-label shuffles as masks (True = group A): every split of r
    recordings into ra and r - ra when there are at most n_perm of them,
    else n_perm random ones. Returns (masks, exact)."""
    from math import comb
    if comb(r, ra) <= n_perm:
        M = np.zeros((comb(r, ra), r), dtype=bool)
        for j, c in enumerate(itertools.combinations(range(r), ra)):
            M[j, list(c)] = True
        return M, True
    M = np.zeros((int(n_perm), r), dtype=bool)
    for j in range(int(n_perm)):
        M[j, rng.permutation(r)[:ra]] = True
    return M, False


def _perm_p(obs, null, exact):
    """A permutation p: the share of splits at least as extreme (the
    observed split is one of them when they were all enumerated)."""
    ge = int((null >= obs - 1e-12 * max(1.0, abs(obs))).sum())
    return float(ge / null.size if exact else (1 + ge) / (1 + null.size))


def _shape_null(F, M, stat):
    """The distance between the two equal-weight distributions for every
    split in M (recordings x grid ECDFs in F)."""
    H = F.mean(axis=0)
    fn = _ad if stat == "ad" else _ks
    Mf = M.astype(float)
    na = Mf.sum(axis=1, keepdims=True)
    return np.concatenate([fn(Mf[k:k + 1000] @ F / na[k:k + 1000],
                              (1.0 - Mf[k:k + 1000]) @ F
                              / (F.shape[0] - na[k:k + 1000]), H)
                           for k in range(0, M.shape[0], 1000)])


def _bf(x, M):
    """The Brown-Forsythe F (Levene's, about each group's median) of values
    x for every split in M. Its F-table p is not used: with four or five
    recordings a group's deviations hold a zero (odd n) or a pair (n = 4)
    and the table is far too generous -- 0.0007 for made-up labels on the
    cached reads. The p is the permutation one."""
    x = np.asarray(x, dtype=float)
    A, B = np.where(M, x, np.nan), np.where(~M, x, np.nan)
    with np.errstate(all="ignore"):
        z = np.where(M, np.abs(x - np.nanmedian(A, axis=1, keepdims=True)),
                     np.abs(x - np.nanmedian(B, axis=1, keepdims=True)))
        na, nb = M.sum(axis=1), (~M).sum(axis=1)
        za = np.where(M, z, 0.0).sum(axis=1) / na
        zb = np.where(~M, z, 0.0).sum(axis=1) / nb
        zm = z.mean(axis=1)
        between = na * (za - zm) ** 2 + nb * (zb - zm) ** 2
        within = np.where(M, (z - za[:, None]) ** 2,
                          (z - zb[:, None]) ** 2).sum(axis=1)
        f = (x.size - 2) * between / within
    return np.where(np.isfinite(f), f, np.where(between > 0, np.inf, 0.0))


def _word(p, q, ci_clear=True):
    """A result in words. Only q (and a CI clear of zero) makes a finding."""
    if p is None:
        return "untested"
    if q is not None and q < ALPHA and ci_clear:
        return "finding"
    return "hint" if p < ALPHA else "no sign"


def _labels(groups, ref):
    seen = []
    for g in groups:
        if g is not None and g not in seen:
            seen.append(g)
    if ref is None and "CTL" in seen:
        ref = "CTL"
    if ref in seen:
        seen.remove(ref)
        seen.insert(0, ref)
    return seen


def _rec_curve(rec, blob, cls):
    try:
        c = rec["cls"][str(cls)][blob]["curve"]["mean"]
    except (KeyError, TypeError):
        return None
    return c


def group_compare(recs, groups, measure, blob="top", cls="all", ref=None,
                  names=None, n_bins=N_BINS, n_boot=N_BOOT, n_perm=N_PERM,
                  min_events=MIN_EVENTS, dist_stat="ad", seed=SEED):
    """One measure of one blob of one class, across groups of recordings.

    recs     recording summaries (`recording_summary`)
    groups   each recording's group ("CTL", "PTEN", "separable", "picked",
             ...); None leaves it out
    cls      0, 1, 2 or "all" -- or a list, one per recording (DS1 of the
             separable beside the one kind of the rest, say)
    ref      the reference group, drawn first and subtracted (CTL when
             there is one)

    Returns JSON:
      measure, blob, cls, unit, words, higher, left_out [{rec, why}],
      bins (edges), ecdf_x,
      groups: [{label, recs, n_rec, n_events, medians,
                stats (of the medians; None under MIN_RECS recordings),
                deciles (of the equal-weight distribution),
                hist, under, over (shares, the mean of its recordings'),
                rec_hist, ecdf, rec_ecdf, curve {n, mean, sem} (across
                recordings' mean curves), bimodal}],
      compare (two groups with MIN_RECS each, else None):
        {a, b, shift: {q, a, b, diff (b - a), lo, hi},
         effect: {diff (b - a, median of medians), lo, hi},
         tests: {location: Mann-Whitney on medians (ci_clear: the
                 effect's CI leaves out zero), spread: Brown-Forsythe on
                 medians, shape: Anderson-Darling (or KS) between the
                 equal-weight distributions -- these two with p from
                 permuting recording labels (every split when there are
                 at most n_perm); each {name, stat, p, q, word}; q is None
                 here and filled by `compare_all`, so alone the best word
                 is "hint"},
         n_boot}
    """
    from scipy import stats
    if measure not in MEASURE_IDS:
        raise ValueError("A measure is one of %s; not %r."
                         % (", ".join(MEASURE_IDS), measure))
    if blob not in BLOBS:
        raise ValueError("A blob is top or bottom; not %r." % blob)
    if len(groups) != len(recs):
        raise ValueError("%d groups for %d recordings."
                         % (len(groups), len(recs)))
    names = list(names) if names is not None else list(range(len(recs)))
    cl = list(cls) if isinstance(cls, (list, tuple)) else [cls] * len(recs)
    meta = next(m for m in MEASURES if m["id"] == measure)
    labels = _labels(groups, ref)
    keep, left = [], []
    for i, (rec, g) in enumerate(zip(recs, groups)):
        if g is None:
            continue
        v = _values(rec, blob, measure, cl[i])
        if v.size < min_events:
            left.append({"rec": names[i], "why": "%d event%s" % (
                v.size, "" if v.size == 1 else "s")})
        else:
            keep.append((i, g, v))
    out = {"measure": measure, "blob": blob,
           "cls": cl if isinstance(cls, (list, tuple)) else cls,
           "unit": meta["unit"], "words": meta["words"],
           "higher": meta["higher"], "left_out": left, "bins": None,
           "ecdf_x": None, "groups": [], "compare": None}
    if not keep:
        return out
    vals = [v for _, _, v in keep]
    grid = _grid(vals)
    F = _ecdfs(vals, grid)
    lo, hi = _quant(F.mean(axis=0), grid, [0.005, 0.995])[0]
    if not hi > lo:
        lo, hi = float(grid[0]) - 0.5, float(grid[-1]) + 0.5
    edges = np.linspace(lo, hi, int(n_bins) + 1)
    ex = np.linspace(grid[0], grid[-1], N_ECDF)
    Fx = _ecdfs(vals, ex)
    rh, under, over = _hist(vals, edges)
    out["bins"], out["ecdf_x"] = _rl(edges), _rl(ex)
    rows = {}
    for lab in labels:
        ix = [j for j, (_, g, _) in enumerate(keep) if g == lab]
        rows[lab] = ix
        if not ix:
            continue
        meds = np.array([np.median(vals[j]) for j in ix])
        enough = len(ix) >= MIN_RECS
        curves = [_rec_curve(recs[keep[j][0]], blob, cl[keep[j][0]])
                  for j in ix]
        curves = np.array([[np.nan if y is None else y for y in c]
                           for c in curves if c], dtype=float)
        out["groups"].append({
            "label": lab, "recs": [names[keep[j][0]] for j in ix],
            "n_rec": len(ix), "n_events": int(sum(vals[j].size for j in ix)),
            "medians": _rl(meds),
            "stats": _summ(meds) if enough else None,
            "deciles": (_rl(_quant(F[ix].mean(axis=0), grid, DECILES)[0])
                        if enough else None),
            "hist": _rl(rh[ix].mean(axis=0)) if enough else None,
            "under": _r(under[ix].mean()) if enough else None,
            "over": _r(over[ix].mean()) if enough else None,
            "rec_hist": [_rl(rh[j], 3) for j in ix],
            "rec_under": _rl(under[ix], 3), "rec_over": _rl(over[ix], 3),
            "ecdf": _rl(Fx[ix].mean(axis=0)) if enough else None,
            "rec_ecdf": [_rl(Fx[j], 3) for j in ix],
            "curve": (_mean_sem(curves) if enough and curves.size
                      else None),
            "bimodal": (_bimodal(meds, [vals[j] for j in ix])
                        if enough else None),
            "say": (None if enough else "Fewer than %d recordings: no "
                    "averages." % MIN_RECS)})
    two = [lab for lab in labels if len(rows.get(lab, [])) >= MIN_RECS]
    if len(labels) == 2 and len(two) == 2:
        out["compare"] = _compare(vals, F, grid, rows[labels[0]],
                                  rows[labels[1]], labels, n_boot, n_perm,
                                  dist_stat, seed, stats)
    return out


def _compare(vals, F, grid, ia, ib, labels, n_boot, n_perm, dist_stat, seed,
             stats):
    rng = np.random.default_rng(seed)
    ma = np.array([np.median(vals[j]) for j in ia])
    mb = np.array([np.median(vals[j]) for j in ib])
    qa = _quant(F[ia].mean(axis=0), grid, DECILES)[0]
    qb = _quant(F[ib].mean(axis=0), grid, DECILES)[0]
    wa, pa = _boot_rows(rng, len(ia), n_boot)
    wb, pb = _boot_rows(rng, len(ib), n_boot)
    sh = _quant(wb @ F[ib], grid, DECILES) - _quant(wa @ F[ia], grid, DECILES)
    eff = np.median(mb[pb], axis=1) - np.median(ma[pa], axis=1)
    e_lo, e_hi = np.percentile(eff, [2.5, 97.5])
    d_obs = float(np.median(mb) - np.median(ma))
    tests = {}
    u = stats.mannwhitneyu(mb, ma, alternative="two-sided")
    ci_clear = bool(e_lo > 0 or e_hi < 0)
    tests["location"] = {"name": "Mann-Whitney U on recording medians",
                         "stat": _r(u.statistic), "p": _r(u.pvalue),
                         "ci_clear": ci_clear}
    # Both tests below shuffle the same recording labels; the observed
    # split is the first len(ia) rows of the stacked arrays.
    order = list(ia) + list(ib)
    M, exact = _splits(len(order), len(ia), n_perm, rng)
    obs = np.zeros((1, len(order)), dtype=bool)
    obs[0, :len(ia)] = True
    meds = np.concatenate([ma, mb])
    bf0 = float(_bf(meds, obs)[0])
    tests["spread"] = {"name": "Brown-Forsythe on recording medians, "
                       "recording labels permuted",
                       "stat": _r(bf0),
                       "p": _r(_perm_p(bf0, _bf(meds, M), exact)),
                       "sd_a": _r(ma.std(ddof=1)), "sd_b": _r(mb.std(ddof=1)),
                       "perms": int(M.shape[0]), "exact": exact}
    Fo = F[order]
    s0 = float(_shape_null(Fo, obs, dist_stat)[0])
    tests["shape"] = {"name": ("Anderson-Darling" if dist_stat == "ad"
                               else "Kolmogorov-Smirnov")
                      + " between the equal-weight distributions, "
                      "recording labels permuted",
                      "stat": _r(s0),
                      "p": _r(_perm_p(s0, _shape_null(Fo, M, dist_stat),
                                      exact)),
                      "perms": int(M.shape[0]), "exact": exact}
    for t in tests.values():
        t["q"] = None
        t["word"] = _word(t["p"], None, t.get("ci_clear", True))
    return {"a": labels[0], "b": labels[1],
            "shift": {"q": list(DECILES), "a": _rl(qa), "b": _rl(qb),
                      "diff": _rl(qb - qa),
                      "lo": _rl(np.percentile(sh, 2.5, axis=0)),
                      "hi": _rl(np.percentile(sh, 97.5, axis=0))},
            "effect": {"diff": _r(d_obs), "lo": _r(e_lo), "hi": _r(e_hi)},
            "tests": tests, "n_boot": int(n_boot)}


def bh(ps):
    """Benjamini-Hochberg q values, in the order given (None kept None)."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    m = len(idx)
    out = [None] * len(ps)
    run = 1.0
    for r, i in enumerate(sorted(idx, key=lambda i: ps[i], reverse=True)):
        run = min(run, ps[i] * m / (m - r))
        out[i] = _r(min(1.0, run))
    return out


def compare_all(recs, groups, measures=MEASURE_IDS, blobs=BLOBS,
                classes=("all",), **kw):
    """`group_compare` for every measure x blob x class asked, with each
    test's p corrected (Benjamini-Hochberg) across all of them -- the
    family is everything this call ran, per test (location, spread, shape,
    and the dip on the recording medians of each group). Each test gets its
    q and its word: "finding" (q < 0.05, and for location a bootstrap CI
    clear of zero), "hint" (p < 0.05 only: not a finding) or "no sign".

    Returns {results: [group_compare outputs], family: {test: how many p
    values were corrected together}}."""
    res = [group_compare(recs, groups, m, b, c, **kw)
           for c in classes for b in blobs for m in measures]
    fam = {}
    for test in ("location", "spread", "shape"):
        slots = [r["compare"]["tests"][test] for r in res if r["compare"]]
        for t, q in zip(slots, bh([t["p"] for t in slots])):
            t["q"] = q
            t["word"] = _word(t["p"], q, t.get("ci_clear", True))
        fam[test] = sum(t["p"] is not None for t in slots)
    slots = [g["bimodal"]["medians"] for r in res for g in r["groups"]
             if g["bimodal"]]
    for t, q in zip(slots, bh([t["p"] for t in slots])):
        t["q"] = q
        t["word"] = _word(t["p"], q)
    fam["bimodal"] = sum(t["p"] is not None for t in slots)
    return {"results": res, "family": fam}
