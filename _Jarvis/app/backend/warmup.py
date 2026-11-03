# -*- coding: utf-8 -*-
"""warmup.py -- what the start screen gets ready while somebody chooses.

The user's ask (2026-10-21): a start screen that "caches everything", so
that once you are in, nothing makes you wait. The page drives most of it --
every list is fetched into its kept copy (web/js/data.js) -- and this is the
server's half, the two things only the server can do ahead of time:

  ENGINES    The analysis libraries the tools need, imported now rather than
             by the first tool somebody runs. scipy.signal, scikit-learn and
             matplotlib are kept out of start-up on purpose (lazyimp.py), so
             without this the first run of a tool pays one to two seconds of
             importing before it starts.

  OVERVIEWS  The overview strip of each recording somebody opened recently,
             worked out and written to disk (derived.py), so opening one of
             them skips the read -- ten seconds, measured, on the recording
             that was opened first today. One at a time, in the background,
             and it stands aside whenever a recording is being read for
             somebody (`foreground`).

Neither changes an answer: an import is an import, and the strip on disk is
exactly the strip that would have been read, keyed on the file it came from.
"""
from __future__ import annotations

import importlib
import threading
import time

from . import lazyimp

ENGINES = ("scipy.signal", "scipy.stats", "sklearn.mixture",
           "matplotlib.pyplot", "fooof")

_FG = [0]                       # recordings being read for somebody, now
_FG_LOCK = threading.Lock()
_FILL = {"running": False, "done": 0, "of": 0, "current": None,
         "kept": 0, "skipped": 0, "errors": 0, "at": None, "stop": False}
_FILL_LOCK = threading.Lock()


def engines():
    """Import each engine that is installed and not yet imported. Yields
    one record per engine, as each is ready -- for a streamed answer."""
    import sys
    for name in ENGINES:
        if name in sys.modules:
            yield {"name": name, "ms": 0, "already": True}
            continue
        if not lazyimp.have(name.split(".")[0]):
            yield {"name": name, "missing": True}
            continue
        t0 = time.time()
        try:
            importlib.import_module(name)
            ok = True
        except Exception:                                # noqa: BLE001
            ok = False
        yield {"name": name, "ok": ok, "ms": round((time.time() - t0) * 1000)}


class Foreground(object):
    """Around a request that reads a recording for somebody: the overview
    filler waits until there are none."""

    def __enter__(self):
        with _FG_LOCK:
            _FG[0] += 1
        return self

    def __exit__(self, *exc):
        with _FG_LOCK:
            _FG[0] = max(0, _FG[0] - 1)
        return False


def foreground_begin():
    with _FG_LOCK:
        _FG[0] += 1


def foreground_end():
    with _FG_LOCK:
        _FG[0] = max(0, _FG[0] - 1)


def recent_paths(store, limit=30):
    """The recordings this machine opened most recently, newest first, from
    its own activity log (`session.open`)."""
    out, seen = [], set()
    try:
        rows = store.list_activity(limit=2000, action="session.open") or []
    except Exception:                                    # noqa: BLE001
        rows = []
    for r in rows:
        p = ((r.get("detail") or {}).get("path") if isinstance(r, dict) else None)
        if not p or p in seen or str(p).startswith("demo:"):
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= limit:
            break
    return out


def fill_overviews(paths, make_session, overview, bins=700):
    """Start writing the overview strip of each path to disk, one at a time,
    on a background thread. Returns False when one is already running."""
    with _FILL_LOCK:
        if _FILL["running"]:
            return False
        _FILL.update(running=True, done=0, of=len(paths), current=None,
                     kept=0, skipped=0, errors=0, at=time.time(), stop=False)

    def work():
        try:
            for p in paths:
                if _FILL["stop"]:
                    break
                # Stand aside while somebody is reading a recording.
                while _FG[0] > 0 and not _FILL["stop"]:
                    time.sleep(0.25)
                _FILL["current"] = p
                try:
                    sess = make_session(p)
                    if not sess:
                        _FILL["skipped"] += 1
                    else:
                        res = overview(sess, channel=0, bins=bins)
                        if res and res.get("ok"):
                            _FILL["kept"] += 1
                        else:
                            _FILL["skipped"] += 1
                except Exception:                        # noqa: BLE001
                    _FILL["errors"] += 1
                _FILL["done"] += 1
                time.sleep(0.05)
        finally:
            _FILL["running"] = False
            _FILL["current"] = None

    threading.Thread(target=work, daemon=True, name="warmup-overviews").start()
    return True


def fill_state():
    return dict(_FILL)


def stop_fill():
    _FILL["stop"] = True
