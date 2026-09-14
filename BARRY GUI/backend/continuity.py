"""
continuity.py -- is this recording one continuous block, or several?

Cheetah closes a record early when acquisition hiccups, and the next record's
timestamp jumps forward by more than one block. neo and spikeinterface call
that a section break, so the file reaches Toothy as a MULTI-SEGMENT recording
and Toothy concatenates it. Concatenation closes the gaps and rebuilds the
time axis as `i / fs`, which labels every sample after a gap with a time
earlier than its true one, by the cumulative duration of all preceding gaps.
The error is a step function -- zero in the first segment, constant inside
each later one -- and nothing downstream recorded that it happened.

On `M8_Pten\\M8s9feb8` that is 8 segments, 7 gaps, 0.1225 s never written, and
121.9 ms of error by the end. A dentate spike is 10-20 ms wide, so seeking to
a banked DS time in the raw file after 1762.5 s lands six to twelve event
widths away from the event. Eight of the twenty-five PTEN recordings are like
this; the other seventeen are genuinely clean, which is the check
discriminating rather than always firing.

`nlx.segment_ncs` does one file. This does a folder: a reference channel, a
spot-check of a few others so a disagreement is visible, a stable hash of the
segment map, and a cache, because the answer only changes when the files do.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading

from . import nlx

# Set from app.py at boot, the way cfc.configure works. Without it the cache
# is in-process only, which is correct but does not survive a restart.
CACHE_DIR = None

_MEM = {}
_MEM_ORDER = []
_MEM_MAX = 64
_LOCK = threading.Lock()

# How many channels to cross-check by default. One channel is the
# segmentation; the others are there so "the folder is partly copied" cannot
# masquerade as "the recording has gaps".
SPOT_CHANNELS = 4


def configure(logs_dir):
    """Point the on-disk cache at GUI_logs/.cache/continuity."""
    global CACHE_DIR
    if not logs_dir:
        CACHE_DIR = None
        return
    CACHE_DIR = os.path.join(logs_dir, ".cache", "continuity")
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except OSError:
        CACHE_DIR = None


# --------------------------------------------------------------------------
# Identity of an answer
# --------------------------------------------------------------------------
def gap_map_sha(report):
    """A stable hash of the segmentation, for recording what was applied.

    Only the things that would change a correction go in: the rule, the rate,
    and each segment's true start and sample count. Not the path, not the
    time of the check, not how many channels were spot-checked -- two machines
    looking at the same recording must agree on this string or the whole idea
    of stamping a correction with it is worthless.
    """
    body = {
        "rule": report.get("gap_rule"),
        "tolerance_us": report.get("gap_tolerance_us"),
        "fs": round(float(report.get("fs") or 0), 6),
        "t0_us": report.get("t0_us"),
        "segments": [[int(s["start_us"]), int(s["n_samples"])]
                     for s in report.get("segments") or []],
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _stamp(path):
    """(size, mtime) of a file, or None if it is not there."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [int(st.st_size), int(st.st_mtime_ns)]


def _key(ref, stamp, channels, strict):
    raw = json.dumps([os.path.normcase(os.path.abspath(ref)), stamp,
                      int(channels), bool(strict)],
                     sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _cache_get(key):
    with _LOCK:
        hit = _MEM.get(key)
    if hit is not None:
        return hit
    if not CACHE_DIR:
        return None
    try:
        with open(os.path.join(CACHE_DIR, key + ".json"), "r",
                  encoding="utf-8") as fh:
            hit = json.load(fh)
    except (OSError, ValueError):
        return None
    _cache_mem(key, hit)
    return hit


def _cache_mem(key, value):
    with _LOCK:
        if key not in _MEM:
            _MEM_ORDER.append(key)
        _MEM[key] = value
        while len(_MEM_ORDER) > _MEM_MAX:
            _MEM.pop(_MEM_ORDER.pop(0), None)


def _cache_put(key, value):
    _cache_mem(key, value)
    if not CACHE_DIR:
        return
    tmp = os.path.join(CACHE_DIR, key + ".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(value, fh)
        os.replace(tmp, os.path.join(CACHE_DIR, key + ".json"))
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def cache_clear():
    with _LOCK:
        _MEM.clear()
        del _MEM_ORDER[:]
    if not CACHE_DIR:
        return
    try:
        for name in os.listdir(CACHE_DIR):
            if name.endswith(".json"):
                os.remove(os.path.join(CACHE_DIR, name))
    except OSError:
        pass


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------
def check(folder, channels=SPOT_CHANNELS, strict=False, all_channels=False,
          use_cache=True):
    """Segment a recording folder and cross-check a few of its channels.

    Returns None when there is nothing to check -- no folder, no .ncs. Every
    other outcome, including an unreadable reference channel, comes back as a
    report so the caller can say what happened.
    """
    if not folder or not os.path.isdir(folder):
        return None
    try:
        names = sorted(n for n in os.listdir(folder)
                       if n.lower().endswith(".ncs"))
    except OSError:
        return None
    if not names:
        return None

    files = [os.path.join(folder, n) for n in _numeric_order(names)]
    ref = files[0]
    stamp = _stamp(ref)
    n_probe = len(files) if all_channels else max(1, int(channels))
    key = _key(ref, stamp, n_probe, strict) if stamp else None

    if use_cache and key:
        hit = _cache_get(key)
        if hit is not None:
            hit["cached"] = True
            return hit

    try:
        seg = nlx.segment_ncs(ref, strict=strict)
    except Exception as exc:                             # noqa: BLE001
        return {"folder": folder, "ok": False, "n_ncs": len(files),
                "reference": os.path.basename(ref), "error": str(exc)}

    out = dict(seg)
    out.pop("path", None)
    out["folder"] = folder
    out["ok"] = True
    out["cached"] = False
    out["n_ncs"] = len(files)
    out["reference"] = os.path.basename(ref)
    out["gap_map_sha"] = gap_map_sha(seg)
    out["probed"] = [out["reference"]]
    out["mismatches"] = []

    # Cross-check. A reference channel alone cannot tell "this recording has
    # gaps" from "this folder was copied while it was being written", and
    # those want opposite responses.
    if all_channels:
        others = files[1:]
    else:
        step = max(1, len(files) // max(1, n_probe))
        others = files[step::step][:max(0, n_probe - 1)]

    want = [(s["start_us"], s["n_samples"]) for s in seg["segments"]]
    for path in others:
        name = os.path.basename(path)
        try:
            info = nlx.segment_ncs(path, strict=strict)
        except Exception as exc:                         # noqa: BLE001
            out["mismatches"].append({"channel": name,
                                      "why": "unreadable: %s" % exc})
            continue
        out["probed"].append(name)
        got = [(s["start_us"], s["n_samples"]) for s in info["segments"]]
        if got != want:
            out["mismatches"].append({
                "channel": name,
                "why": "%d segment(s), %d samples -- the reference has "
                       "%d and %d" % (len(got), info["total_samples"],
                                      len(want), seg["total_samples"]),
            })

    if key:
        _cache_put(key, out)
    return out


def _numeric_order(names):
    """CSC2 before CSC10, the way a person reads them."""
    def sort_key(n):
        num = nlx._CSC_NAME_RE.match(n)
        return (0, int(num.group(1)), int(num.group(2) or 0)) if num \
            else (1, 0, 0, )
    return sorted(names, key=lambda n: sort_key(n) + (n.lower(),))


# --------------------------------------------------------------------------
# Converting between the two clocks
# --------------------------------------------------------------------------
# Toothy's time axis is `i / fs` over the concatenated segments. The map back
# to the recording's own clock is a step: constant inside a segment, jumping
# at each boundary by the gap that was closed there.
def concat_to_true(report, t):
    """One concatenated second -> (true second, segment index).

    `(None, None)` when the time is past the end of the data, which is the
    only concatenated time that has no answer. Not clamped: an event at
    2200 s in a 2124 s recording is a fault somewhere else and quietly moving
    it to the last sample would hide that.
    """
    segs = (report or {}).get("segments") or []
    if not segs or t is None:
        return None, None
    t = float(t)
    if t < 0:
        return None, None
    # Small enough to walk. Eight segments is the worst case in this archive
    # and a thousand would still be cheaper than the bisect's own overhead.
    for i in range(len(segs) - 1, -1, -1):
        seg = segs[i]
        if t >= seg["concat_t0_s"] - 1e-12:
            end = seg["concat_t0_s"] + seg["duration_s"]
            # The last segment's end is the end of the recording; inside it,
            # anything up to `end` is real.
            if t > end + 1e-9:
                if i == len(segs) - 1:
                    return None, None
                continue
            return t + seg["error_ms"] / 1e3, i
    return None, None


def true_to_concat(report, t):
    """The other direction, which is partial.

    `(None, None)` when the true time falls inside a gap -- there is no
    sample there and no concatenated time that means it. That case is the
    reason this returns a pair rather than a number.
    """
    segs = (report or {}).get("segments") or []
    if not segs or t is None:
        return None, None
    t = float(t)
    for i, seg in enumerate(segs):
        start = seg["true_t0_s"]
        end = start + seg["duration_s"]
        if start - 1e-12 <= t <= end + 1e-9:
            return t - seg["error_ms"] / 1e3, i
    return None, None


def near_stitch(report, true_t, window_s=0.125):
    """Is this time within `window_s` of a segment boundary?

    Toothy band-pass filters and peak-detects straight across each stitch,
    where the LFP steps discontinuously. An event detected there may be
    filter ringing rather than a real dentate spike. Correcting its time does
    not make it real, and the preview is the honest place to say so.

    The default half-window is the DS detector's own `ds_wlen`.
    """
    for g in (report or {}).get("gaps") or []:
        if abs(float(true_t) - float(g["at_true_time_s"])) <= window_s:
            return True
    return False


def shift_table(report):
    """Per segment: the concatenated span it covers and the shift it takes.

    The whole of what a re-timing would do, in as many rows as there are
    segments -- which is what a preview should show rather than a list of
    two thousand events.
    """
    out = []
    for seg in (report or {}).get("segments") or []:
        out.append({
            "segment": seg["index"],
            "concat_from_s": seg["concat_t0_s"],
            "concat_to_s": seg["concat_t0_s"] + seg["duration_s"],
            "shift_ms": seg["error_ms"],
            "n_samples": seg["n_samples"],
        })
    return out


# --------------------------------------------------------------------------
# Saying it in words
# --------------------------------------------------------------------------
def checks(report):
    """The `{level, name, message}` rows for the session health report."""
    if not report:
        return []
    if not report.get("ok"):
        return [{"level": "warn", "name": "continuity",
                 "message": "Could not check for gaps: %s"
                            % report.get("error", "unknown")}]

    rows = []
    n_seg = int(report.get("n_segments") or 1)
    lost = float(report.get("seconds_lost") or 0.0)
    worst = float(report.get("max_time_error_ms") or 0.0)

    if n_seg > 1:
        first = (report.get("gaps") or [{}])[0].get("at_true_time_s")
        segs = report.get("segments") or []
        onset = float(segs[1].get("error_ms") or 0.0) if len(segs) > 1 else worst
        rows.append({
            "level": "warn", "name": "continuity",
            "message": "%d segments, %d gap(s) -- %s of data was never "
                       "written. Times read from the concatenated file run "
                       "early from %s onward: %s at the first gap, %s by the "
                       "end."
                       % (n_seg, len(report.get("gaps") or []),
                          _ms(lost * 1e3), _secs(first), _ms(onset),
                          _ms(worst)),
        })
    else:
        rows.append({"level": "ok", "name": "continuity",
                     "message": "Continuous -- one segment, no gaps."})

    # A short record below the tolerance can lose time without making a
    # break, and no segment boundary records that it happened. At `ok`,
    # because it is not a reason to distrust the times -- it is stated rather
    # than hidden.
    #
    # Measured from the timestamps at those records, NOT from
    # `n_records * 512 - samples`. That counts unused buffer slots: when the
    # next timestamp follows the short count the record was simply short and
    # nothing was lost, and reporting 199.5 ms of loss for it is wrong.
    n_short = int(report.get("n_short_records") or 0)
    inside = int(report.get("n_short_inside") or 0)
    sub = float(report.get("sub_threshold_lost_s") or 0.0)
    if n_short:
        if inside and sub > 0:
            rows.append({
                "level": "ok", "name": "short records",
                "message": "%d record(s) closed early, %d of them without "
                           "making a segment break. %s went unrecorded at "
                           "those, which no segment boundary accounts for."
                           % (n_short, inside, _ms(sub * 1e3)),
            })
        else:
            rows.append({
                "level": "ok", "name": "short records",
                "message": "%d record(s) closed early, and the next "
                           "timestamp follows each one exactly -- the "
                           "records are short, no time is missing."
                           % n_short,
            })

    bad = report.get("mismatches") or []
    if bad:
        rows.append({
            "level": "bad", "name": "channels disagree",
            "message": "%d channel(s) segment differently from %s -- the "
                       "folder may be mixed or partly copied: %s"
                       % (len(bad), report.get("reference"),
                          "; ".join("%s (%s)" % (b["channel"], b["why"])
                                    for b in bad[:3])),
        })
    return rows


def _ms(value):
    v = float(value or 0.0)
    if abs(v) < 1.0:
        return "%.2f ms" % v
    if abs(v) < 1000.0:
        return "%.1f ms" % v
    return "%.3f s" % (v / 1e3)


def _secs(value):
    if value is None:
        return "the first gap"
    v = float(value)
    if v < 60:
        return "%.1f s" % v
    return "%d m %02d s" % (v // 60, v % 60)
