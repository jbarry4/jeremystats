"""
live.py -- Shared state across browser windows.

"Link time" has to work between panes in one window AND between separate
windows, including two different browsers. A pane popped out into its own
window is a separate JavaScript context with no way to reach the original, so
the shared cursor has to live on the server.

The model is deliberately tiny: one slot per channel name, holding a value and
a monotonically increasing version. Clients poll it, ignore their own echoes
via `origin`, and apply anything newer than what they last saw. No websockets,
no dependencies, and it survives a window being closed.
"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
# Waiters block on this instead of the client asking again and again.
_CHANGED = threading.Condition(_LOCK)
_STATE = {}
_VERSION = {"n": 0}

MAX_CHANNELS = 32


def publish(channel, value, origin=None):
    """Write a value and bump the global version."""
    with _LOCK:
        _VERSION["n"] += 1
        if channel not in _STATE and len(_STATE) >= MAX_CHANNELS:
            # Drop the least recently touched slot rather than grow forever.
            oldest = min(_STATE, key=lambda k: _STATE[k]["at"])
            _STATE.pop(oldest, None)
        _STATE[channel] = {
            "value": value,
            "origin": origin,
            "version": _VERSION["n"],
            "at": time.time(),
        }
        # Wake every held poll: this is what makes linking feel instant
        # rather than "within 400ms".
        _CHANGED.notify_all()
        return _STATE[channel]


def read(channel, since=0):
    """Return the slot if it is newer than `since`, else None."""
    with _LOCK:
        slot = _STATE.get(channel)
        if not slot or slot["version"] <= int(since or 0):
            return None
        return dict(slot)


def snapshot(since=0):
    """Every slot newer than `since`, for a single polling call."""
    with _LOCK:
        since = int(since or 0)
        out = {k: dict(v) for k, v in _STATE.items() if v["version"] > since}
        return {"version": _VERSION["n"], "channels": out}


def wait(since=0, timeout=25.0):
    """`snapshot`, but held open until there is something to say.

    Returns as soon as the version passes `since`, or empty-handed when
    the timeout runs out -- the client then simply asks again, so an idle
    window costs one request every `timeout` seconds instead of two and a
    half a second.

    A `since` that is *ahead* of the counter means this process restarted
    while a tab stayed open. Waiting would block until the timeout and
    then do it again forever, so say so and let the client reset.
    """
    timeout = max(0.0, min(float(timeout or 0), 60.0))
    deadline = time.time() + timeout
    with _LOCK:
        since = int(since or 0)
        if since > _VERSION["n"]:
            return {"version": _VERSION["n"], "reset": True,
                    "channels": {k: dict(v) for k, v in _STATE.items()}}
        while _VERSION["n"] <= since:
            left = deadline - time.time()
            if left <= 0:
                break
            _CHANGED.wait(left)
        return {"version": _VERSION["n"],
                "channels": {k: dict(v) for k, v in _STATE.items()
                             if v["version"] > since}}


def clear(channel=None):
    with _LOCK:
        if channel:
            _STATE.pop(channel, None)
        else:
            _STATE.clear()
        return True
