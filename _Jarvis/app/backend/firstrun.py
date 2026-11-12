"""
firstrun.py -- what Setup did on this computer, and whether the app has
finished getting it ready.

The user's ask (2026-11-07): Setup in the console and the welcome in the app
did the same things twice -- sign in to the VACC in one, then again in the
other -- and a new computer then sat on skeleton bars while the first sync,
the recordings and every cache were worked out cold, one view at a time.

So Setup (setup.py `mark_setup`) writes down here what it did, and the app's
welcome (web/js/welcome.js) reads it through `/api/firstrun`: a step Setup
finished is shown done and not asked again, and the first opening after
Setup runs the getting-ready stage once -- the sync, the recordings, the
caches -- with every step said as it happens. `ready_at` is written when it
has run, so it never runs again unless Setup is run again.

Machine-local, in GUI_logs/.cache, which git ignores: this is about one
computer, and another computer's answer would be wrong here.
"""
from __future__ import annotations

import json
import os
import threading
import time

_LOCK = threading.Lock()


def path(logs_dir):
    return os.path.join(logs_dir, ".cache", "firstrun.json")


def read(logs_dir):
    try:
        with open(path(logs_dir), encoding="utf-8") as fh:
            rec = json.load(fh)
        return rec if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        return {}


def update(logs_dir, **fields):
    with _LOCK:
        rec = read(logs_dir)
        rec.update(fields)
        p = path(logs_dir)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = "%s.%d.tmp" % (p, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1)
        os.replace(tmp, p)
        return rec


# The optimisation update (2026-11-09): "you open up the GUI for the first
# time after this update ... if you are not a new user ... it does an
# optimization update". A computer that was set up before the getting-ready
# stage existed has none of its caches, so the first opening after the
# update runs the cache half of it once, on its own screen. Raised when a
# later update needs it run again. A new computer never sees it: its
# welcome runs the same job, and the job finishing is what records it.
OPTIMIZE_VERSION = 1


def optimize_wanted(rec):
    """Whether this computer still needs the optimisation update: not one
    waiting for its first opening (that runs the same job), and not one the
    job has already finished on at this version."""
    return not wanted(rec) and int(rec.get("optimized") or 0) < OPTIMIZE_VERSION


def mark_optimized(logs_dir):
    return update(logs_dir, optimized=OPTIMIZE_VERSION,
                  optimized_at=time.time())


def wanted(rec):
    """Whether the getting-ready stage still has to run: Setup ran here and
    the stage has not finished since. A computer that was set up before this
    existed has no record, and is left alone."""
    return bool(rec.get("setup_at")) and not rec.get("ready_at")


def mark_ready(logs_dir):
    return update(logs_dir, ready_at=time.time())
