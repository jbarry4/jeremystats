"""
prewarm.py -- remember rendered panels, and render the likely next ones early.

The problem
-----------
A scalogram over 64 channels is a few seconds of work, and curation is a
loop of "jump to the next candidate, look, press a key". Every jump paid the
full cost again, including jumping *back* to something already looked at.
Nothing was cached: /api/panel recomputed from the .ncs every time.

Two halves
----------
`cache`     Rendered panels, keyed on the whole spec. Every input that can
            change the picture is in the spec already -- window, channels,
            filters, frequency band, colormap, limits -- so hashing it is
            enough, and a revisit is free.

`warm`      A background worker that renders specs nobody has asked for yet.
            The client hands it the windows around the events in the
            recording; by the time you press "next" the panel is usually
            already in the cache.

Rules the worker follows, because a speculative render that slows down a
real one is worse than no speculation at all:

  * one worker thread, never more
  * it stands down while a foreground render is in flight
  * a queued job whose session or spec shape is superseded is dropped rather
    than rendered late
  * the cache is bounded in bytes, not entries, because a panel is an
    encoded image and they vary by two orders of magnitude
"""
from __future__ import annotations

import collections
import hashlib
import json
import threading
import time

# Panels are data-URI PNGs. 320 MB is roughly a thousand of a typical one,
# which is far more than a curation pass will visit, and small enough not to
# matter next to what numpy uses to make them.
MAX_BYTES = 320 * 1024 * 1024
MAX_ENTRIES = 1200

# Keys that do not change the picture and so must not change the key.
_IGNORE = ("prewarm", "reason", "_edge_s", "_db_mult", "_legacy_stft")

_LOCK = threading.Lock()
_CACHE = collections.OrderedDict()      # key -> (payload, nbytes, at)
_BYTES = [0]
_STATS = {"hit": 0, "miss": 0, "warmed": 0, "dropped": 0, "evicted": 0}

# Foreground work in flight. The worker waits while this is above zero.
_BUSY = [0]
_BUSY_CV = threading.Condition()

_QUEUE = collections.deque()            # (generation, session, spec)
_QUEUE_CV = threading.Condition()
_GEN = [0]
_WORKER = [None]
MAX_QUEUE = 240


def key_for(session, spec):
    """A stable key for a render request.

    The path identifies the data, the spec identifies everything done to it.
    Sorted JSON so two dicts that differ only in insertion order agree.
    """
    clean = {k: v for k, v in (spec or {}).items()
             if k not in _IGNORE and not k.startswith("_")}
    blob = json.dumps(
        [session.get("path"), session.get("even_only"), clean],
        sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _sizeof(payload):
    try:
        u = payload.get("image") or payload.get("data_uri") or ""
        return len(u) + 512
    except Exception:                                    # noqa: BLE001
        return 4096


def get(session, spec):
    k = key_for(session, spec)
    with _LOCK:
        hit = _CACHE.get(k)
        if hit is None:
            _STATS["miss"] += 1
            return None
        _CACHE.move_to_end(k)            # least-recently-used at the front
        _STATS["hit"] += 1
        return hit[0]


def put(session, spec, payload):
    if not isinstance(payload, dict) or not payload.get("ok", True):
        return
    k = key_for(session, spec)
    n = _sizeof(payload)
    with _LOCK:
        if k in _CACHE:
            _BYTES[0] -= _CACHE[k][1]
            del _CACHE[k]
        _CACHE[k] = (payload, n, time.time())
        _BYTES[0] += n
        while _CACHE and (_BYTES[0] > MAX_BYTES or len(_CACHE) > MAX_ENTRIES):
            _, (_p, old_n, _t) = _CACHE.popitem(last=False)
            _BYTES[0] -= old_n
            _STATS["evicted"] += 1


def clear():
    with _LOCK:
        _CACHE.clear()
        _BYTES[0] = 0


class Busy:
    """Marks a foreground render, so the warmer keeps out of its way."""

    def __enter__(self):
        with _BUSY_CV:
            _BUSY[0] += 1
        return self

    def __exit__(self, *exc):
        with _BUSY_CV:
            _BUSY[0] -= 1
            _BUSY_CV.notify_all()
        return False


def _wait_idle():
    """Block until nothing in the foreground is rendering."""
    with _BUSY_CV:
        while _BUSY[0] > 0:
            _BUSY_CV.wait(timeout=1.0)


def _run():
    from backend import analysis
    while True:
        with _QUEUE_CV:
            while not _QUEUE:
                _QUEUE_CV.wait(timeout=5.0)
            gen, session, spec = _QUEUE.popleft()
        if gen != _GEN[0]:
            _STATS["dropped"] += 1        # superseded while it waited
            continue
        # A little air after a foreground request finishes, so a burst of
        # panning is not immediately followed by speculative work competing
        # for the same disk.
        _wait_idle()
        time.sleep(0.05)
        if gen != _GEN[0]:
            _STATS["dropped"] += 1
            continue
        try:
            if get(session, spec) is not None:
                continue                  # someone asked for it first
            out = analysis.render_panel(session, dict(spec))
            put(session, spec, out)
            _STATS["warmed"] += 1
        except Exception:                 # noqa: BLE001
            # A speculative render that fails is not an error anybody asked
            # about. The same request in the foreground will report it
            # properly.
            pass


def _ensure_worker():
    if _WORKER[0] is None or not _WORKER[0].is_alive():
        t = threading.Thread(target=_run, daemon=True, name="barry-prewarm")
        _WORKER[0] = t
        t.start()


def request(session, specs, supersede=True):
    """Queue speculative renders.

    `supersede` bumps the generation, so anything still queued from an
    earlier ask is dropped instead of rendered after it stopped being
    useful -- moving to a different recording, or changing the filters,
    invalidates every window that was waiting.
    """
    _ensure_worker()
    queued = 0
    with _QUEUE_CV:
        if supersede:
            _GEN[0] += 1
            dropped = len(_QUEUE)
            _QUEUE.clear()
            _STATS["dropped"] += dropped
        gen = _GEN[0]
        for spec in specs:
            if len(_QUEUE) >= MAX_QUEUE:
                break
            if get(session, spec) is not None:
                continue                  # already have it
            _QUEUE.append((gen, session, spec))
            queued += 1
        _QUEUE_CV.notify_all()
    return queued


def windows_around(times, span, limit=24, t_end=None):
    """Windows centred on each of `times`, nearest first, de-duplicated.

    Overlapping events would otherwise queue near-identical renders and
    spend the budget on one busy second of the recording.
    """
    out, seen = [], set()
    for t in times:
        try:
            t0 = float(t) - span / 2.0
        except (TypeError, ValueError):
            continue
        t0 = max(0.0, t0)
        if t_end is not None:
            t0 = min(t0, max(0.0, float(t_end) - span))
        # Quantised to a tenth of the span, so two events a few milliseconds
        # apart share one window rather than asking for two.
        bucket = round(t0 / max(span / 10.0, 1e-6))
        if bucket in seen:
            continue
        seen.add(bucket)
        out.append(t0)
        if len(out) >= limit:
            break
    return out


def stats():
    with _LOCK:
        return dict(_STATS, entries=len(_CACHE),
                    bytes=_BYTES[0], queued=len(_QUEUE),
                    worker=bool(_WORKER[0] and _WORKER[0].is_alive()))
