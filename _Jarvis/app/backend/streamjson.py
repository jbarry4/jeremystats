# -*- coding: utf-8 -*-
"""streamjson.py -- answers that arrive a piece at a time.

WHY

Every answer this server gave was all or nothing. A strip of 900 amplitude
bins, a list of hundreds of records: the page saw nothing until the last
one was computed, then everything at once -- "nothing... then BAM", in the
user's words (2026-10-21). Where each piece has its own real cost (a seek
on network storage, a file to stat), there is no reason to hold the first
ones back until the last is done.

THE SHAPE

Newline-delimited JSON (`application/x-ndjson`), one object per line:

    {"head": {...}}              first: what the rest is about
    {"item": ...}                one per piece, in the order they are ready
    {"item": ...}
    {"done": true, "n": 2, ...}  last: how many, and anything summed up

or, if something fails part-way,

    {"error": "...", "n": 1}     instead of "done": what got through stays

The page reads it with `BARRY.data.stream(url, body, onItem)`
(web/js/data.js), which calls `onItem` as each line lands and resolves with
the head and the tail.

WHERE NOT TO USE IT

A list that comes out of one shared read -- `REG.all()` merging fifteen
hundred shards -- gains nothing by being streamed: every row is ready at the
same moment. Those are answered from the page's stash first and the live
answer after (constitution section 10). Stream only what costs per item.
"""
from __future__ import annotations

import json
import traceback

MIMETYPE = "application/x-ndjson"


def _line(obj):
    return json.dumps(obj, separators=(",", ":"), default=str) + "\n"


def lines(head, items, tail=None):
    """The generator behind `stream`, separate so it can be tested without
    Flask. `items` is any iterable; `tail` a callable returning extra fields
    for the closing line (computed after the last item)."""
    yield _line({"head": head or {}})
    n = 0
    try:
        for it in items:
            n += 1
            yield _line({"item": it})
    except GeneratorExit:            # the page went away: stop working
        raise
    except Exception as exc:         # noqa: BLE001
        yield _line({"error": str(exc) or type(exc).__name__, "n": n,
                     "type": type(exc).__name__,
                     "trace": traceback.format_exc(limit=3)})
        return
    end = {"done": True, "n": n}
    if tail:
        try:
            end.update(tail() or {})
        except Exception as exc:     # noqa: BLE001
            end["tail_error"] = str(exc)
    yield _line(end)


def stream(head, items, tail=None):
    """A Flask response that sends `head`, then each item as it is ready."""
    from flask import Response, stream_with_context
    resp = Response(stream_with_context(lines(head, items, tail)),
                    mimetype=MIMETYPE)
    # Never cached, never buffered by anything between here and the page.
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


def wants_stream(request):
    """Whether the page asked for the streamed form (`?stream=1`, or an
    Accept naming ndjson). Every streamed route still answers the old way
    for anything that did not ask -- harnesses and scripts keep working."""
    try:
        if request.args.get("stream") in ("1", "true", "yes"):
            return True
        return MIMETYPE in (request.headers.get("Accept") or "")
    except Exception:                # noqa: BLE001
        return False
