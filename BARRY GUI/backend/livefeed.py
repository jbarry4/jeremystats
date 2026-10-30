"""
livefeed.py -- what the VACC work is doing right now, a line at a time.

The user's ask (2026-10-23), about the welcome's VACC and Recordings steps:
"make sure its not just a static loading screen, but like an informative
letting you know what's happening bar loading sort of thing ... rapid fire
spit out tons of text."

So the slow things -- signing in, the probe that confirms a connection, a
walk of scratch or of netfiles -- say what they are doing as they do it,
here, and `/api/vacc/feed` hands the lines to whoever is watching. Every
line is a real event: a key tried, a field the cluster answered with, a
recording folder found on the walk. Nothing is made up to look busy; when
there is nothing to say the page says how long it has been waiting.

In memory only and bounded. It is a window onto work in progress, not a
log -- the activity log is the record -- so a restart starting it empty is
right, and a walk of 1,462 folders cannot grow it without limit.

Progress is separate from lines: a task (`walk:/netfiles/bigdata_jbarry`,
`signin`, `probe`) has how far it has got and, when anything honest can be
said about it, out of how many. A walk's "out of" is the size of the last
walk of the same place, so it is said as an estimate.
"""
from __future__ import annotations

import collections
import threading
import time

MAX_LINES = 3000
MAX_TEXT = 300


class Feed:
    def __init__(self, cap=MAX_LINES):
        self._lock = threading.Lock()
        self._lines = collections.deque(maxlen=cap)
        self._n = 0
        self._tasks = {}

    def say(self, text, kind="", task=None):
        """One line. `kind`: '' | 'ok' | 'warn' | 'dim' | 'hot'."""
        text = " ".join(str(text or "").split())[:MAX_TEXT]
        if not text:
            return
        with self._lock:
            self._n += 1
            self._lines.append({"n": self._n, "t": time.time(),
                                "text": text, "kind": kind or "",
                                "task": task})

    def task(self, name, **kw):
        """Start or move a task: label, done, of, state ('run'|'done'|'fail'),
        estimate (True when `of` is a guess)."""
        with self._lock:
            cur = self._tasks.get(name)
            if cur is None or kw.get("restart"):
                cur = {"name": name, "started": time.time(), "done": 0,
                       "of": None, "label": name, "state": "run",
                       "estimate": False}
                self._tasks[name] = cur
            for k in ("label", "done", "of", "state", "estimate"):
                if k in kw and kw[k] is not None:
                    cur[k] = kw[k]
            cur["at"] = time.time()
            if cur["state"] != "run":
                cur.setdefault("ended", time.time())
            else:
                cur.pop("ended", None)

    def bump(self, name, by=1):
        with self._lock:
            cur = self._tasks.get(name)
            if cur is not None:
                cur["done"] = (cur.get("done") or 0) + by
                cur["at"] = time.time()

    def read(self, since=0, limit=1500):
        """Lines after `since`, and every task touched in the last ten
        minutes. `since` < 0 asks only where the feed is up to."""
        now = time.time()
        with self._lock:
            nxt = self._n
            skipped = 0
            if since is None or since < 0:
                lines = []
            else:
                lines = [ln for ln in self._lines if ln["n"] > since]
                # Too far behind: the newest, and say how many were skipped.
                skipped = max(0, len(lines) - limit)
                lines = lines[-limit:]
            tasks = [dict(t, age_s=round(now - t["started"], 1))
                     for t in self._tasks.values()
                     if now - t.get("at", now) < 600]
            # Old finished tasks go, so the table stays small.
            for k in [k for k, t in self._tasks.items()
                      if t.get("state") != "run"
                      and now - t.get("at", now) > 600]:
                self._tasks.pop(k, None)
        out = {"next": nxt, "lines": lines, "tasks": tasks, "now": now}
        if skipped:
            out["skipped"] = skipped
        return out


FEED = Feed()
say = FEED.say
task = FEED.task
bump = FEED.bump
read = FEED.read
