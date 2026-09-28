"""
spark.py -- find the cue events in a DEWEY recording and pair them up.

Step one of The Arc, and the only step that reads a .nev. Everything after it
works from what this banks, which is why finding and pairing and banking are
one act rather than three: a pair that has been found and not banked is a
number on a screen, and the next step cannot see it.

WHAT A CUE PAIR IS

The paradigm plays two neutral sounds back to back, ten seconds apart, with
no reinforcer -- that is the whole of sensory preconditioning. Each cue runs
for ten seconds, so the second begins exactly as the first ends and the
transition between them is gapless.

The opener and the closer are separate TTL pulses on the same port, and the
gap is 10.000 s with sub-millisecond jitter. Everything this module does is
in service of deciding which pulses are real and which opener belongs to
which closer.

WHICH CUE PAIRS WITH WHICH IS NOT FIXED. The pilot animals were run on
`High tone -> Low Tone` and `Click -> Noise`; J3 is run on
`Click -> Low Tone` and `Noise -> High tone`. It is counterbalanced, so it
is read off each recording rather than written down here.

ONLY PRECONDITIONING SESSIONS HOLD PAIRS, sixteen apiece -- eight of each
pairing. Conditioning pairs a single cue with a reinforcer, and test sessions
present single cues to see what the animal does; measured across all nine
animals, both come back with none, which is the right answer and not a
failure to find them.

WHAT MAKES A PULSE REAL

Three things get in the way, and all three are the rig's behaviour rather
than anything wrong with the recording:

  * MIRRORS. Every code is also fired one higher -- 110 comes with 111, 124
    with 125. They are the same event seen twice, and counting both doubles
    every cue in the session.
  * BOUNCE. A TTL line can fire the same code twice within a few
    milliseconds. Anything repeating inside 150 ms on one port is one press.
  * OTHER EVENT RECORDS. A .nev also holds the recording's own start and
    stop marks and Cheetah's messages. Only `event_id == 11` is a TTL.

The vocabulary, the mirror map and the debounce are transcribed from the
cluster pipeline that produced the published figures --
`Take 3/4 Clean Event_Timeline/scripts/build_clean_events.py` -- so a reading
here and a reading there agree about what a pulse is. The pairing rule is
deliberately NOT transcribed; see `pair_events` for what that cost.

WHAT IT REFUSES TO DECIDE

An opener with no closer, a gap outside tolerance, a TTL nobody has named:
all reported, none silently dropped. A recording where something went wrong
is a recording somebody needs to look at, and a pipeline that quietly returns
the fourteen pairs it liked is how twenty-two become fourteen without anybody
noticing.
"""
from __future__ import annotations

import os
import re

from . import nlx

# --------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------
#: TTL code -> what it means. From the cluster pipeline; these are the codes
#: this rig is wired to send.
PRIMARY = {
    126: "Session",
    124: "Click",
    122: "Noise",
    118: "High tone",
    110: "Low Tone",
    94: "Pellet Delivery",
    62: "Mag Poke",
}

#: The mirror of each code -- the same event, fired one higher. Counting a
#: mirror as a second event doubles every cue in the session.
MIRROR_OF = {111: 110, 119: 118, 123: 122, 125: 124, 127: 126, 63: 62, 95: 94}

#: A repeat of one code on one port inside this many milliseconds is the same
#: press, not a second one.
DEBOUNCE_MS = 150.0

#: The four sounds. Which one opens onto which is NOT written down here, and
#: that is the point -- see `pair_events`.
CUES = ("Click", "Noise", "High tone", "Low Tone")

#: The code the line returns to when a pulse ends. It arrives 20 ms after a
#: magazine poke and ten seconds after a cue, because a cue is ten seconds
#: long -- which is what makes it the third analysis boundary rather than
#: bookkeeping. See `pair_events`.
END_LABEL = "Session"

#: The gap the paradigm uses, and how far off it may be and still be a pair.
#:
#: The cluster pipeline allowed two seconds, which it could afford because it
#: also required a named pair of cues. Reading the pairing off the data
#: instead means the gap is doing more of the work, and two seconds is much
#: too generous for that: it accepted cue pulses 8.02 s apart as pairs, in
#: sessions where every genuine pair measured between 9.9992 s and 10.0013 s.
#:
#: A quarter of a second is still two hundred times the jitter actually
#: present, and rules out everything that was being let through. Anything
#: between this and `NEAR_MISS_S` is reported as a near miss rather than
#: silently dropped -- a cue pair that came out at 8 s is a fact about the
#: session and somebody should see it.
EXPECTED_GAP_S = 10.0
GAP_TOLERANCE_S = 0.25
NEAR_MISS_S = 3.0

#: A .nev holds more than TTLs. 11 is the TTL record.
TTL_EVENT_ID = 11

_PORT_RE = re.compile(r"port\s+(\d+)", re.IGNORECASE)


class SparkError(Exception):
    pass


def port_of(text):
    """Which input port an event string names, as text, or None."""
    m = _PORT_RE.search(str(text or ""))
    return m.group(1) if m else None


def classify(ttl):
    """(label, is_mirror, known) for one TTL code."""
    ttl = int(ttl)
    if ttl in PRIMARY:
        return PRIMARY[ttl], False, True
    base = MIRROR_OF.get(ttl)
    if base in PRIMARY:
        return PRIMARY[base], True, True
    return "Unknown (%d)" % ttl, False, False


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def read_events(nev_path, t_start_us=None):
    """Every TTL in the file, classified, debounced, in time order.

    Times are SECONDS FROM THE START OF THE RECORDING, which is what the
    Event Bank stores and the only frame in which they mean anything.
    """
    recs, meta = nlx.read_nev(nev_path)
    if len(recs) == 0:
        return [], {"n_records": 0, "t_start_us": None}

    origin = (float(t_start_us) if t_start_us is not None
              else float(recs["timestamp"][0]))

    rows = []
    for i in range(len(recs)):
        if int(recs["event_id"][i]) != TTL_EVENT_ID:
            continue
        raw = recs["event_string"][i]
        text = raw.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()
        ttl = int(recs["ttl"][i])
        label, is_mirror, known = classify(ttl)
        rows.append({
            "ttl": ttl,
            "port": port_of(text),
            "timestamp_us": float(recs["timestamp"][i]),
            "t": (float(recs["timestamp"][i]) - origin) / 1e6,
            "label": label,
            "is_mirror": is_mirror,
            "known": known,
            "text": text,
        })

    # Debounce per port AND per code: two different cues arriving close
    # together are two cues, and only a repeat of the SAME code is a bounce.
    by_port = {}
    for r in rows:
        by_port.setdefault(r["port"], []).append(r)
    for _p, rs in by_port.items():
        rs.sort(key=lambda r: r["timestamp_us"])
        last = {}
        for r in rs:
            prev = last.get(r["ttl"])
            dt_ms = None if prev is None else (r["timestamp_us"] - prev) / 1000.0
            r["debounced"] = dt_ms is not None and dt_ms < DEBOUNCE_MS
            r["since_ms"] = dt_ms
            last[r["ttl"]] = r["timestamp_us"]

    rows.sort(key=lambda r: r["timestamp_us"])
    return rows, {"n_records": int(len(recs)), "t_start_us": origin}


def pair_events(rows):
    """Match every opener to the closer it opens onto.

    WHICH CUE PAIRS WITH WHICH IS READ, NOT ASSUMED

    The cluster pipeline hard-coded `High tone -> Low Tone` and
    `Click -> Noise`, which is what the pilot animals were run on. These
    animals are not: J3's first preconditioning session is
    `Click -> Low Tone` and `Noise -> High tone`. The pairings are
    counterbalanced, and a rule that names them would have quietly produced
    eleven pairs with three-hundred-second gaps -- which is what it did
    before this was noticed, and every one of them looked like data.

    So the rule is structural instead, and it is the one the paradigm
    actually defines: a pair is two cue pulses about ten seconds apart. What
    those two cues happen to be is an OUTPUT.

    THE THIRD BOUNDARY IS IN THE FILE

    The rig drops the line back to its resting code when a pulse ends, and a
    cue is ten seconds long, so that code lands ten seconds after the closer
    -- exactly where the connectivity work cuts its third window. The
    cluster derived that moment as `closer + gap`; here it can be read. The
    derived value is kept as a fallback and the two are compared, because a
    boundary that is measured and a boundary that is assumed are different
    claims and it is worth knowing when they disagree.
    """
    usable = [r for r in rows
              if r["known"] and not r["is_mirror"] and not r["debounced"]]
    cues = [r for r in usable if r["label"] in CUES]
    ends = [r for r in usable if r["label"] == END_LABEL]

    pairs, unpaired = [], []
    by_port = {}
    for r in cues:
        by_port.setdefault(r["port"], []).append(r)

    for port, rs in sorted(by_port.items(), key=lambda kv: str(kv[0])):
        rs.sort(key=lambda r: r["timestamp_us"])
        i = 0
        while i < len(rs):
            opener = rs[i]
            cand = rs[i + 1] if i + 1 < len(rs) else None
            gap = None if cand is None else cand["t"] - opener["t"]

            why = None
            if cand is None:
                why = "nothing follows it"
            elif abs(gap - EXPECTED_GAP_S) > GAP_TOLERANCE_S:
                why = ("the next cue is %.3f s away, not %.0f"
                       % (gap, EXPECTED_GAP_S))
            elif cand["label"] == opener["label"]:
                # Two of the same sound is two presentations, not a pair.
                # The paradigm binds one cue to a DIFFERENT one -- that is
                # the whole of what it is for -- so a High tone followed by
                # another High tone is never the thing being looked for,
                # however well the clock agrees.
                why = ("the next cue is another %s, and a pair is two "
                       "different sounds" % opener["label"])
            if why:
                unpaired.append(dict(
                    opener, why=why,
                    near_miss=(cand is not None
                               and cand["label"] != opener["label"]
                               and abs(gap - EXPECTED_GAP_S) <= NEAR_MISS_S),
                    gap_s=None if gap is None else round(gap, 6)))
                i += 1
                continue

            # The measured end of cue 2: the first resting-code mark after
            # the closer, within a cue's length plus slack.
            measured = None
            for e in ends:
                if e["port"] != port or e["t"] <= cand["t"]:
                    continue
                if e["t"] - cand["t"] <= EXPECTED_GAP_S + GAP_TOLERANCE_S:
                    measured = e["t"]
                break
            derived = cand["t"] + gap

            pairs.append({
                "port": port,
                "opener_label": opener["label"],
                "closer_label": cand["label"],
                "opener_t": round(opener["t"], 6),
                "closer_t": round(cand["t"], 6),
                "opener_ttl": opener["ttl"],
                "closer_ttl": cand["ttl"],
                "gap_s": round(gap, 6),
                "in_tolerance": True,
                "offset_t": round(measured if measured is not None
                                  else derived, 6),
                "offset_from": "mark" if measured is not None else "derived",
                "offset_drift_s": (None if measured is None
                                   else round(measured - derived, 6)),
            })
            i += 2

    pairs.sort(key=lambda p: p["opener_t"])
    for n, p in enumerate(pairs, start=1):
        p["pair_id"] = n
    return pairs, unpaired


def summarise(rows, pairs, unpaired):
    """What a person needs to see before deciding this reading is right."""
    kinds = {}
    for r in rows:
        kinds[r["label"]] = kinds.get(r["label"], 0) + 1

    gaps = [p["gap_s"] for p in pairs]
    by_type = {}
    for p in pairs:
        key = "%s -> %s" % (p["opener_label"], p["closer_label"])
        by_type[key] = by_type.get(key, 0) + 1

    unknown = sorted({r["ttl"] for r in rows if not r["known"]})
    drift = [p["offset_drift_s"] for p in pairs
             if p.get("offset_drift_s") is not None]
    return {
        "n_ttl": len(rows),
        "n_mirror": sum(1 for r in rows if r["is_mirror"]),
        "n_debounced": sum(1 for r in rows if r.get("debounced")),
        "n_unknown": sum(1 for r in rows if not r["known"]),
        "unknown_codes": unknown,
        "kinds": sorted(kinds.items(), key=lambda kv: -kv[1]),
        "n_pairs": len(pairs),
        "by_pair_type": sorted(by_type.items()),
        "n_unpaired": len(unpaired),
        "n_near_miss": sum(1 for u in unpaired if u.get("near_miss")),
        "n_out_of_tolerance": sum(1 for p in pairs if not p["in_tolerance"]),
        "gap_min": round(min(gaps), 6) if gaps else None,
        "gap_max": round(max(gaps), 6) if gaps else None,
        "gap_mean": round(sum(gaps) / len(gaps), 6) if gaps else None,
        "n_offset_marked": sum(1 for p in pairs
                               if p.get("offset_from") == "mark"),
        "offset_drift_max": (round(max(abs(d) for d in drift), 6)
                             if drift else None),
        "expected_gap_s": EXPECTED_GAP_S,
        "tolerance_s": GAP_TOLERANCE_S,
        "debounce_ms": DEBOUNCE_MS,
    }


def read(nev_path, t_start_us=None):
    """The whole reading: events, pairs, and what to make of them."""
    rows, meta = read_events(nev_path, t_start_us)
    pairs, unpaired = pair_events(rows)
    return {
        "events": rows,
        "pairs": pairs,
        "unpaired": unpaired,
        "summary": summarise(rows, pairs, unpaired),
        "meta": meta,
    }


# --------------------------------------------------------------------------
# Banking
# --------------------------------------------------------------------------
def bank_events(pairs):
    """Cue pairs as Event Bank events.

    ONE EVENT PER PAIR, not two.

    A pair is a span -- the opener's time to the closer's time -- and the
    bank already stores a span: `start` and `end`. So a pair needs nothing
    the bank does not have, and the third boundary the connectivity work
    wants (the end of cue 2) is `end + (end - start)`, derived at the point
    of use rather than stored as a number that could drift out of agreement
    with the two it came from.

    Banking the opener and closer as two separate events was the other
    option and is worse: it doubles the count, and it loses the one fact
    that matters most -- which opener went with which closer -- unless a
    field is invented to carry it, which the bank's whitelist would drop.
    """
    out = []
    for p in pairs:
        out.append({
            "start": p["opener_t"],
            "end": p["closer_t"],
            "label": "%s → %s" % (p["opener_label"], p["closer_label"]),
        })
    return out


# --------------------------------------------------------------------------
# Clipping
# --------------------------------------------------------------------------
# A cue pair is only usable on a channel that was actually measuring during
# it. If the amplifier saturated -- the animal knocked the headstage, a wire
# shorted, the gain was too high for a movement artefact -- the trace in that
# window is a flat line at the rail, and every number computed from it is a
# number about the rail rather than about the brain.
#
# Nothing downstream can notice this on its own. A coherence between two
# flat-topped windows is high, confidently, and looks exactly like a result.
# So it is found here, at the point the pairs are made, and travels with
# them: `clipped` on the banked event is the list of CSC channels this pair
# is not valid for.
#
# WHAT COUNTS AS CLIPPING
#
# Samples at the digitiser's own ceiling, in a run. `ADMaxValue` is 32767 on
# this rig and `InputRange` is 2000 uV, so the rail is +/- 2000 uV and a
# sample within half a percent of it had nowhere higher to go. One such
# sample is a coincidence; sixteen in a row at 32 kHz is half a millisecond
# of a signal that has stopped being a signal.
#
# CALIBRATION, 2026-09-24
#
# Measured rather than assumed, because a detector that flags everything and
# a detector that flags nothing are equally useless and look the same from a
# distance:
#
#   * Cross-checked against `nlx.read_ncs`, the app's own reader, on a whole
#     663 MB channel: the windowed memmap read here and the full read agree
#     to a tenth of a percent (62.79% vs 62.69% of one window at the rail).
#     The record arithmetic below lands on the right samples.
#   * A healthy channel measures 0.000% at the rail and peaks around 65% of
#     it. A visibly clipped one measured 71% of a window. There is no middle
#     ground to tune against.
#   * Flat-topping BELOW the rail -- an amplifier giving out before the
#     digitiser does -- was looked for across six recordings, four pairs
#     each, all 32 channels, and does not occur in this data: every channel
#     that flat-tops flat-tops at the rail. The level-free test is kept
#     anyway because it costs one comparison.
#   * J6 Precon1 is railed for 29.5% of the ENTIRE recording on CSC1, so a
#     whole session reading as ruined is a real answer here, not a fault in
#     this code.
#
# HOW IT IS READ
#
# Memory-mapped and sliced, not read. A DEWEY recording is 663 MB a channel
# and there are 32 of them; reading all of that to look at sixteen
# twenty-second windows would be twenty gigabytes for a few megabytes of
# answer. Records are fixed-size and their timestamps are monotonic, so the
# record holding any moment is an arithmetic step away, and the operating
# system pages in only what is touched.
CLIP_FRACTION = 0.995      # of ADMaxValue
CLIP_MIN_RUN = 16          # consecutive samples, ~0.5 ms at 32 kHz

#: How much of a window has to be gone before the window counts as lost.
#:
#: Measured, not chosen. Across six recordings and four pairs each, the
#: channels that are visibly clipped lose about 1.2% of a window in runs of
#: ~22 ms; the ones nobody would call clipped lose 0.01-0.07% in runs of
#: 3-4 ms -- a few milliseconds out of forty seconds, from one loud
#: artefact touching the rail.
#:
#: Grading on PRESENCE put those in the same bucket, so a channel that lost
#: three milliseconds came back "major event loss" and the grade stopped
#: meaning anything. A window is lost when enough of it is gone to matter
#: to a correlation: half a percent, or one unbroken stretch of 50 ms.
#: Anything smaller is reported as touched and not graded.
WINDOW_LOST_FRAC = 0.005
WINDOW_LOST_MS = 50.0

#: The four windows a cue pair is analysed in, and the only ones where
#: clipping costs anything.
#:
#: Ten seconds of baseline, then cue 1, then cue 2, then ten seconds after
#: cue 2 ends -- forty seconds, bounded by the pair's own measured
#: boundaries rather than by assuming each cue ran exactly ten seconds.
#:
#: They are kept apart, rather than scanned as one forty-second block,
#: because a pair whose baseline saturated still has three good windows in
#: it. Treating the pair as one thing would throw those away, and there are
#: not so many cue pairs that any can be spared.
CLIP_WINDOWS = ("pre", "cue1", "cue2", "post")
CLIP_PAD_S = 10.0

#: How much of an event is gone, on one channel. The scale is by how many
#: of the four windows saturated, because that is what decides what is left
#: to use rather than how bad any one window looked.
LOSS_NONE = "clean"
LOSS_PARTIAL = "partial event loss"     # one window
LOSS_MAJOR = "major event loss"         # two or three
LOSS_TOTAL = "event lost"               # all four


def loss_grade(n_windows, of=None):
    """What losing `n_windows` of a pair's windows means for this channel.

    `of` is how many windows there are to lose: four for the state windows
    (the default, and the only answer this ever gave before transitions),
    three for the transition windows. The vocabulary is the same for both,
    so "event lost" means every window of that kind, whichever kind it is.
    """
    of = len(CLIP_WINDOWS) if of is None else int(of)
    if n_windows <= 0:
        return LOSS_NONE
    if n_windows == 1 and of > 1:
        return LOSS_PARTIAL
    if n_windows >= of:
        return LOSS_TOTAL
    return LOSS_MAJOR


def pair_windows(pair, pad_s=CLIP_PAD_S):
    """The four analysis windows of one pair, as (name, t0, t1) seconds."""
    o, c, e = pair["opener_t"], pair["closer_t"], pair["offset_t"]
    return [("pre", o - pad_s, o),
            ("cue1", o, c),
            ("cue2", c, e),
            ("post", e, e + pad_s)]


# --------------------------------------------------------------------------
# Transition windows
# --------------------------------------------------------------------------
# The state windows ask what the brain was doing DURING each part of a pair.
# The transition windows ask what it did AT each boundary: a short span
# either side of cue 1 starting, of cue 1 giving way to cue 2, and of cue 2
# ending. Three boundaries, so three windows, each `before` seconds ahead of
# the moment and `after` seconds past it.
#
# They are cut from the pair's MEASURED moments -- the opener, the closer,
# and the cue-2 offset read off the rig's end mark -- exactly as
# `pair_windows` is, so a state window and a transition window of the same
# pair agree about where the boundary is.
STATE_WINDOWS = CLIP_WINDOWS
TRANSITION_WINDOWS = ("onset", "switch", "offset")
KINDS = ("state", "transition")

#: What each window is called on screen. One table for both kinds.
WINDOW_SAY = {
    "pre": "baseline", "cue1": "cue 1", "cue2": "cue 2",
    "post": "after cue 2",
    "onset": "cue 1 onset", "switch": "cue 1 → cue 2",
    "offset": "cue 2 offset",
}

#: The defaults: one second before the boundary, two after.
TRANSITION_BEFORE_S = 1.0
TRANSITION_AFTER_S = 2.0

#: The limits on those lengths, and why they are these.
#:
#: Five seconds either way at most, because the boundaries are ten seconds
#: apart: at five and five the onset window ends exactly where the switch
#: window begins, and past that two "transitions" would share samples and
#: stop being separate measurements.
#:
#: One second in total at least, because Coupling's coherence is a Welch
#: estimate on one-second segments; a shorter window would be refused there
#: after having been checked for clipping here, which is a check nobody can
#: use.
TRANSITION_MIN_S = 0.1
TRANSITION_MAX_S = 5.0
TRANSITION_MIN_TOTAL_S = 1.0

#: A transition window is lost on a channel with this much of it at the
#: rail, IN TIME. The state rule is half a percent of a ten-second window
#: -- which is 50 ms -- or one unbroken 50 ms stretch. Applied as a fraction
#: to a three-second window it would lose the window at 15 ms, three times
#: stricter than the state windows for the same saturation, so it is applied
#: as the time it always was: 50 ms at the rail inside the window, whatever
#: the window's length.
TRANSITION_LOST_MS = WINDOW_LOST_MS


def transition_lengths(before_s=None, after_s=None):
    """(before_s, after_s) as floats, or SparkError saying why not.

    Refused, never clamped: a clipping check run at different lengths from
    the ones somebody typed is a check of windows nobody asked about.
    """
    got = []
    for name, raw, dflt in (("before", before_s, TRANSITION_BEFORE_S),
                            ("after", after_s, TRANSITION_AFTER_S)):
        if raw is None or raw == "":
            got.append(float(dflt))
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise SparkError("The transition window's %s length, %r, is not "
                             "a number of seconds." % (name, raw))
        if v != v or v in (float("inf"), float("-inf")):
            raise SparkError("The transition window's %s length has to be a "
                             "finite number of seconds." % name)
        if v < TRANSITION_MIN_S or v > TRANSITION_MAX_S:
            raise SparkError(
                "The transition window's %s length has to be between %g and "
                "%g s, not %g. The boundaries are ten seconds apart, so past "
                "%g s two transition windows would share samples."
                % (name, TRANSITION_MIN_S, TRANSITION_MAX_S, v,
                   TRANSITION_MAX_S))
        got.append(v)
    before, after = got
    if before + after < TRANSITION_MIN_TOTAL_S:
        raise SparkError(
            "A transition window of %g s before and %g s after is %g s long. "
            "Coupling's coherence is estimated on one-second segments, so a "
            "window shorter than %g s would be checked here and refused "
            "there." % (before, after, before + after,
                        TRANSITION_MIN_TOTAL_S))
    return before, after


def transition_windows(pair, before_s=TRANSITION_BEFORE_S,
                       after_s=TRANSITION_AFTER_S):
    """The three transition windows of one pair, as (name, t0, t1) seconds.

    Same shape as `pair_windows`, and from the same measured moments.
    """
    o, c, e = pair["opener_t"], pair["closer_t"], pair["offset_t"]
    b, a = float(before_s), float(after_s)
    return [("onset", o - b, o + a),
            ("switch", c - b, c + a),
            ("offset", e - b, e + a)]


def windows_for(pair, kind="state", pad_s=CLIP_PAD_S,
                before_s=TRANSITION_BEFORE_S, after_s=TRANSITION_AFTER_S):
    """The windows of one pair for one kind of analysis."""
    if kind == "state":
        return pair_windows(pair, pad_s)
    if kind == "transition":
        return transition_windows(pair, before_s, after_s)
    raise SparkError("There is no %r kind of window; it is one of %s."
                     % (kind, ", ".join(KINDS)))


def window_names(kind="state"):
    """The window names of one kind, in order."""
    if kind == "state":
        return tuple(STATE_WINDOWS)
    if kind == "transition":
        return tuple(TRANSITION_WINDOWS)
    raise SparkError("There is no %r kind of window; it is one of %s."
                     % (kind, ", ".join(KINDS)))


def _runs_at(hit, min_run):
    """Sample spans where `hit` is true for at least `min_run` in a row."""
    import numpy as np
    if not hit.any():
        return 0, 0, []
    edges = np.flatnonzero(
        np.diff(np.concatenate(([0], hit.view(np.int8), [0]))))
    starts, ends = edges[0::2], edges[1::2]
    lens = ends - starts
    longest = int(lens.max()) if lens.size else 0
    keep = lens >= min_run
    spans = [(int(a), int(b)) for a, b in zip(starts[keep], ends[keep])]
    return (int(lens[keep].sum()) if spans else 0), longest, spans


def _clip_runs(block, ceiling, min_run):
    """Where this block of raw ADC samples stopped being a signal.

    Two ways a trace saturates, and the test covers both:

      * the DIGITISER runs out -- samples at ADMaxValue, which is what
        `ceiling` is for;
      * the AMPLIFIER runs out first and the trace flat-tops at some level
        below the rail, which a ceiling test cannot see at all.

    The second is caught by looking for runs of samples at the window's own
    extreme value, whatever that value is. It is strictly more general than
    the ceiling test, and it subsumes it: a railed channel's extreme IS the
    rail.

    Measured across six recordings, four pairs each, all 32 channels: the
    two agree everywhere, because in this data a channel that flat-tops
    flat-tops at the rail. The level-free test is kept anyway -- it costs
    one comparison, and the recording where an amplifier gives out first is
    the one nobody will think to check.

    Returns (n_samples, longest_run, spans) in sample indices.
    """
    import numpy as np
    n1, run1, spans1 = _runs_at(np.abs(block) >= ceiling, min_run)

    # Flat-topping at either extreme, at whatever level it happens.
    n2, run2, spans2 = 0, 0, []
    for extreme in (int(block.max()), int(block.min())):
        if abs(extreme) < ceiling * 0.2:
            # A flat stretch near zero is a quiet channel, not a clipped
            # one; calling that saturation would flag every silent lead.
            continue
        a, b, c = _runs_at(block == extreme, min_run)
        n2 += a
        run2 = max(run2, b)
        spans2 += c

    if n2 <= n1:
        return n1, max(run1, run2), spans1
    # The union, so neither kind is lost. Spans are merged by sorting and
    # coalescing overlaps -- two tests finding the same stretch must not
    # count it twice.
    merged, last = [], None
    for a, b in sorted(spans1 + spans2):
        if last and a <= last[1]:
            last[1] = max(last[1], b)
        else:
            last = [a, b]
            merged.append(last)
    total = sum(b - a for a, b in merged)
    return total, max(run1, run2), [(a, b) for a, b in merged]


def clipping_for(folder, pairs, pad_s=CLIP_PAD_S, progress=None, skip=()):
    """Which channels saturated in which of each pair's four windows.

    Returns {pair_id: {csc: {...}}} where each entry says which windows
    were lost, how much of each, where the runs were, and what that adds up
    to -- and a per-channel tally of how many pairs it touched.

    Window by window, so that as much as possible can be kept: a pair whose
    baseline is at the rail still has two cues and an after-window that are
    perfectly good, and a channel that lost one window out of four is a
    different thing from one that lost all of them.

    The state windows only, in the shape this has always returned. The
    transition windows come from `clipping_both`, which reads each file
    once for both.
    """
    got = _measure(folder, pairs, pad_s=pad_s, progress=progress, skip=skip,
                   kinds=("state",))
    st = got.get("state") or {}
    return st.get("by_pair") or {}, st.get("per_channel") or {}


def clipping_both(folder, pairs, pad_s=CLIP_PAD_S,
                  before_s=TRANSITION_BEFORE_S, after_s=TRANSITION_AFTER_S,
                  progress=None, skip=(), stats=None):
    """State AND transition clipping, from one read of each channel.

    ONE READ, TWO ANSWERS. Reading is the whole cost of this -- a memory
    map paging 40 seconds of 32 kHz samples in from a share, per pair, per
    channel -- and the transition windows lie inside the span the state
    windows already cover. So each channel's samples for a pair are sliced
    out ONCE, as one block spanning every window of both kinds, and both
    measurements are cut from that block in memory. Measuring the two kinds
    in two passes would page the same records in twice for no new
    information.

    Returns {"state": {...}, "transition": {...}}, each with `by_pair`
    (the same per-pair, per-channel shape `clipping_for` returns) and
    `per_channel`. The transition half also says the lengths it was cut
    with, and which windows could not be cut to the sample at all
    (`unmeasured`) -- a window with a break in the clock inside it is a
    window nobody measured, not a clean one.

    `stats`, when given, is filled with how many slices were read and how
    many bytes they held, so "read once" is a thing that can be checked
    rather than asserted.
    """
    before_s, after_s = transition_lengths(before_s, after_s)
    return _measure(folder, pairs, pad_s=pad_s, progress=progress, skip=skip,
                    kinds=KINDS, before_s=before_s, after_s=after_s,
                    stats=stats)


def _detail(hits, run, spans, n_samples, fs, rule):
    """One window's measurement, and whether it counts as lost.

    `rule` is "state" (a fraction of the window, or one long run -- the
    original rule) or "time" (milliseconds at the rail, for the transition
    windows; see TRANSITION_LOST_MS).
    """
    frac = hits / float(n_samples or 1)
    run_ms = run * 1000.0 / fs
    ms = hits * 1000.0 / fs
    if rule == "time":
        gone = ms >= TRANSITION_LOST_MS
    else:
        # Lost, or merely touched. A few milliseconds out of a ten-second
        # window is a loud artefact grazing the rail, not a window that
        # has stopped being usable.
        gone = (frac >= WINDOW_LOST_FRAC or run_ms >= WINDOW_LOST_MS)
    return {
        "n": hits,
        "frac": round(frac, 5),
        "run_ms": round(run_ms, 3),
        "n_spans": len(spans),
        "lost": gone,
    }, (ms if rule == "time" else None)


def _channel_record(detail, lost, spans_all, n_windows, extra=None):
    rec = {
        "windows": lost,
        "touched": [k for k, d in detail.items() if not d["lost"]],
        "detail": detail,
        "grade": loss_grade(len(lost), of=n_windows),
        "worst_frac": round(max(d["frac"] for d in detail.values()), 5),
        "worst_run_ms": round(max(d["run_ms"] for d in detail.values()), 1),
        "spans": spans_all[:60],
    }
    if extra:
        rec.update(extra)
    return rec


def _measure(folder, pairs, pad_s=CLIP_PAD_S, progress=None, skip=(),
             kinds=("state",), before_s=TRANSITION_BEFORE_S,
             after_s=TRANSITION_AFTER_S, stats=None):
    """The engine under `clipping_for` and `clipping_both`."""
    import numpy as np

    kinds = tuple(k for k in KINDS if k in kinds)
    want_state = "state" in kinds
    want_trans = "transition" in kinds

    def empty():
        out = {}
        if want_state:
            out["state"] = {"by_pair": {}, "per_channel": {}}
        if want_trans:
            out["transition"] = {
                "by_pair": {}, "per_channel": {}, "unmeasured": {},
                "before_s": float(before_s), "after_s": float(after_s),
                "measured": False, "why": None}
        return out

    if stats is not None:
        stats.setdefault("reads", 0)
        stats.setdefault("bytes", 0)
        stats.setdefault("channels", 0)
        stats.setdefault("pairs", len(pairs or []))

    if not pairs:
        return empty()

    files = nlx.list_csc_files(folder, even_only=False)
    if not files:
        return empty()

    # Channels somebody has already marked bad are not measured at all.
    #
    # A bad channel is not a cue pair's problem -- it is out for the whole
    # recording, and measuring it here would report it as clipped on every
    # pair and bury the channels that are only bad in one. Worse, the
    # panel would then offer to "keep" a channel nobody can keep.
    #
    # By CSC NUMBER, from the registry's own list, because that is where
    # the decision lives and a second copy would drift from it. The same
    # skip for both kinds: a bad channel is bad at every boundary too.
    skip = {int(c) for c in (skip or [])}
    if skip:
        files = [(n, p) for n, p in files if int(n) not in skip]
    if not files:
        return empty()

    result = empty()
    out = {p["pair_id"]: {} for p in pairs} if want_state else None
    per_channel = {}
    t_out = {p["pair_id"]: {} for p in pairs} if want_trans else None
    t_per_channel = {}
    t_unmeasured = {}

    # The transition windows are cut to the SAMPLE, from the records' own
    # timestamps, which needs the clock they are measured against -- the
    # same origin Spark's pair times and Coupling's windows use.
    origin_us = None
    if want_trans:
        origin_us = nlx.recording_start_us(folder)
        if origin_us is None:
            result["transition"]["why"] = (
                "No .ncs file in that folder could be read for its clock, so "
                "the transition windows could not be placed on it.")
            want_trans = False

    for n, (num, path) in enumerate(files):
        if progress:
            progress(n, len(files), num)
        try:
            hdr = nlx.read_header(path)
            fs = float(hdr.get("SamplingFrequency") or 32000.0)
            admax = float(hdr.get("ADMaxValue") or 32767.0)
            size = os.path.getsize(path)
        except (OSError, ValueError, TypeError):
            continue
        n_rec = max(0, (size - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize)
        if n_rec <= 0:
            continue
        ceiling = admax * CLIP_FRACTION
        try:
            mm = np.memmap(path, dtype=nlx.RECORD_DTYPE, mode="r",
                           offset=nlx.HEADER_BYTES, shape=(int(n_rec),))
        except (OSError, ValueError):
            continue
        if stats is not None:
            stats["channels"] += 1
        try:
            per_rec_s = nlx.SAMPLES_PER_RECORD / fs
            per_rec_us = per_rec_s * 1e6
            spr = nlx.SAMPLES_PER_RECORD
            for p in pairs:
                # Every window this pair is measured in, of both kinds, as
                # record ranges -- then ONE slice spanning all of them.
                s_ranges = []
                if want_state:
                    for name, wa, wb in pair_windows(p, pad_s):
                        i0 = int(max(0, wa // per_rec_s))
                        i1 = int(min(n_rec, wb // per_rec_s + 2))
                        s_ranges.append((name, i0, i1))
                t_wins = (transition_windows(p, before_s, after_s)
                          if want_trans else [])
                t_ranges = []
                for name, wa, wb in t_wins:
                    # Slack either side: the arithmetic guess is exact in a
                    # continuous file, and the cut below is made from the
                    # timestamps, so a record or two of margin is all it
                    # needs to find the sample it wants inside the block.
                    j0 = int(max(0, wa // per_rec_s - 2))
                    j1 = int(min(n_rec, wb // per_rec_s + 3))
                    t_ranges.append((name, wa, wb, j0, j1))
                spans_of = ([(a, b) for _n, a, b in s_ranges if b > a]
                            + [(a, b) for _n, _a, _b, a, b in t_ranges
                               if b > a])
                if not spans_of:
                    continue
                u0 = min(a for a, _b in spans_of)
                u1 = max(b for _a, b in spans_of)

                # THE read. Everything below is arithmetic on this block.
                rows = np.asarray(mm["samples"][u0:u1])
                if stats is not None:
                    stats["reads"] += 1
                    stats["bytes"] += int(rows.nbytes)

                # ---- state: the original four windows, sliced from the
                # block at exactly the records the old per-window read took,
                # so the answer is the same array and the same number.
                if want_state:
                    lost, detail, spans_all = [], {}, []
                    for name, i0, i1 in s_ranges:
                        if i1 <= i0:
                            continue
                        block = rows[i0 - u0:i1 - u0].ravel()
                        hits, run, spans = _clip_runs(block, ceiling,
                                                      CLIP_MIN_RUN)
                        if not hits:
                            continue
                        base = i0 * per_rec_s
                        d, _ms = _detail(hits, run, spans, block.size, fs,
                                         "state")
                        if d["lost"]:
                            lost.append(name)
                        detail[name] = d
                        for a, b in spans[:20]:
                            spans_all.append([round(base + a / fs, 4),
                                              round(base + b / fs, 4)])
                    if detail:
                        out[p["pair_id"]][int(num)] = _channel_record(
                            detail, lost, spans_all, len(CLIP_WINDOWS))
                        per_channel[int(num)] = per_channel.get(int(num), 0) + 1

                # ---- transition: each window cut to the sample from the
                # records' own timestamps, and graded in time.
                if want_trans and t_ranges:
                    ts = np.asarray(mm["timestamp"][u0:u1]).astype(np.float64)
                    nvalid = np.asarray(mm["nvalid"][u0:u1])
                    flat = rows.ravel()
                    lost, detail, spans_all, gaps = [], {}, [], {}
                    for name, wa, wb, _j0, _j1 in t_ranges:
                        want_us = float(origin_us) + float(wa) * 1e6
                        n_want = int(round((float(wb) - float(wa)) * fs))
                        r = int(np.searchsorted(ts, want_us, side="right")) - 1
                        if r < 0 or want_us >= ts[r] + per_rec_us * 1.5:
                            gaps[name] = ("that window is outside this "
                                          "channel's file, or falls in a "
                                          "break in its clock")
                            continue
                        s0 = r * spr + int(round((want_us - ts[r]) * fs / 1e6))
                        s1 = s0 + n_want
                        if s0 < 0 or s1 > flat.size or n_want <= 0:
                            gaps[name] = ("that window runs off the end of "
                                          "this channel's file")
                            continue
                        r1 = (s1 - 1) // spr
                        if np.any(nvalid[r:r1 + 1] != spr):
                            gaps[name] = ("acquisition hiccups inside this "
                                          "window (a short record)")
                            continue
                        if r1 > r:
                            dr = np.abs(np.diff(ts[r:r1 + 1]) - per_rec_us)
                            if float(dr.max()) > per_rec_us * 0.5:
                                gaps[name] = ("a break in the clock falls "
                                              "inside this window")
                                continue
                        block = flat[s0:s1]
                        hits, run, spans = _clip_runs(block, ceiling,
                                                      CLIP_MIN_RUN)
                        if not hits:
                            continue
                        # The time of the block's first sample, from the
                        # record it sits in: seconds from the recording's
                        # start, the frame everything else here uses.
                        base = ((ts[r] - float(origin_us)) / 1e6
                                + (s0 - r * spr) / fs)
                        d, ms = _detail(hits, run, spans, block.size, fs,
                                        "time")
                        d["ms"] = round(ms, 3)
                        if d["lost"]:
                            lost.append(name)
                        detail[name] = d
                        for a, b in spans[:20]:
                            spans_all.append([round(base + a / fs, 4),
                                              round(base + b / fs, 4)])
                    if gaps:
                        t_unmeasured.setdefault(p["pair_id"], {})[
                            int(num)] = gaps
                    if detail:
                        t_out[p["pair_id"]][int(num)] = _channel_record(
                            detail, lost, spans_all, len(TRANSITION_WINDOWS),
                            extra=({"unmeasured": gaps} if gaps else None))
                        t_per_channel[int(num)] = (
                            t_per_channel.get(int(num), 0) + 1)
        finally:
            del mm

    if "state" in result:
        result["state"] = {"by_pair": out, "per_channel": per_channel}
    if "transition" in result and want_trans:
        result["transition"].update({
            "by_pair": t_out, "per_channel": t_per_channel,
            "unmeasured": t_unmeasured, "measured": True, "why": None,
        })
    return result


def clip_summary(per_pair, n_pairs, n_windows=None):
    """Per channel: how many events it clipped in, and how badly.

    A SUMMARY, NOT A VERDICT.

    An earlier version of this sorted channels into "clipped" and "dead",
    on the theory that a channel at the rail through every window is not
    working at all. It is a reasonable theory and it is not this function's
    to have: a channel can clip in every window because the amplifier is
    railed, or because the animal spent the session chewing the tether, and
    those want different answers from a person who was there.

    This module measures saturation. Whether a channel that saturates a lot
    is a broken channel is a judgement, and the app already has somewhere
    for a person to record it -- bad channels, by CSC number, on the
    recording. So this reports the measurement, ordered worst first, and
    leaves the conclusion where it belongs.

    `n_windows` is how many windows each pair has of the kind summarised:
    four state windows (the default), three transition windows.
    """
    n_windows = len(CLIP_WINDOWS) if n_windows is None else int(n_windows)
    seen, worst, lost, grades = {}, {}, {}, {}
    for _pid, chans in (per_pair or {}).items():
        for c, d in chans.items():
            if not (d.get("windows") or []):
                # Touched but nothing lost. Counted nowhere: a channel
                # whose only mark is three milliseconds is a clean channel.
                continue
            seen[c] = seen.get(c, 0) + 1
            worst[c] = max(worst.get(c, 0.0), float(d.get("worst_frac") or 0))
            lost[c] = lost.get(c, 0) + len(d.get("windows") or [])
            g = grades.setdefault(c, {})
            g[d.get("grade")] = g.get(d.get("grade"), 0) + 1

    rows = []
    for c in sorted(seen):
        n_total = max(1, n_pairs) * n_windows
        rows.append({
            "channel": c,
            "in_events": seen[c],
            "of_events": n_pairs,
            "windows_lost": lost[c],
            "windows_total": n_total,
            "worst_frac": round(worst[c], 4),
            # The worst thing that happened to this channel in any one
            # event, which is what decides whether it is worth keeping.
            "grade": (LOSS_TOTAL if grades[c].get(LOSS_TOTAL)
                      else LOSS_MAJOR if grades[c].get(LOSS_MAJOR)
                      else LOSS_PARTIAL),
            "by_grade": grades[c],
        })
    # Worst first: the channel that spent most of a window at the rail is
    # the one somebody should look at, and on a 64-channel recording there
    # are too many rows for the order not to matter.
    rows.sort(key=lambda r: (-r["windows_lost"], -r["worst_frac"],
                             r["channel"]))
    return rows


def label_tally(pairs):
    """How many of each pairing, for the bank's `by_label`."""
    out = {}
    for p in pairs:
        key = "%s → %s" % (p["opener_label"], p["closer_label"])
        out[key] = out.get(key, 0) + 1
    return out
