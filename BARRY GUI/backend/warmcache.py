# -*- coding: utf-8 -*-
"""warmcache.py -- the warm start.

WHAT THIS IS FOR

Opening Jarvis meant sitting in front of a splash for the better part of a
minute. Measured on this machine, from a cold process:

    python import backend.app        2.8 s
    GET /api/sync/status             5.2 s      (STORE.index(), 8 s truly cold)
    GET /api/vacc/knows              5.1 s      (REG.all(), 4-8 s)
    GET /api/registry                6.0 s      (REG.all() again, plus the tree)

Those three are read-only roll-ups over GUI_logs -- 1510 session shards, 3.8
MB, merged into 687 records. Nothing about them is slow by accident and
nothing about them is wrong; they are simply a lot of small files, and the
first request of the process pays for all of them while somebody watches.

The answer they give is also, on the overwhelming majority of boots,
byte-for-byte what they gave last time. The catalogue does not change while
the computer is off.

So: write the answer down when it is computed, and on the next boot hand
back the written one instantly while the real one is recomputed behind it.

WHAT MAKES THIS SAFE, WHICH IS THE WHOLE DESIGN

A cache that can serve a stale answer at any moment is a bug generator, and
this one deliberately is not that. Five rules, each of which narrows when a
cached answer can possibly be seen:

1. **The window is opened by the launcher and by nothing else.** `arm()` is
   called from start.py -- from "Wake up Jarvis" -- and from nowhere in the
   request path. A server started by the harness suite, by vacc_run, or by
   an `import backend.app` in a script never serves a cached byte, so no
   test is ever measuring the cache when it means to measure the store.

2. **A name stops being cacheable the instant its live value exists.** The
   background prime computes each one for real; the moment it has, every
   later request for that name goes to the live builder exactly as it did
   before this module existed. The cache does not answer a second time.

3. **The window closes when the person does something.** Any POST that is
   not known boot chatter shuts it immediately. Somebody who has clicked a
   button is somebody who is owed the truth, and the whole justification
   for this is that nobody has interacted yet.

4. **A hard time limit.** The window closes on its own after WINDOW_S
   whatever else happens, so a prime that wedges cannot leave the cache
   serving for the life of the process.

5. **The cache is void when the code changes.** The stamp includes the
   changelog version and the commit. An update that changes the shape of a
   payload must never hand the new interface last week's shape, and
   "somebody pulled" is exactly when that would otherwise happen.

WHY IT IS NOT SYNCED, AND CANNOT BE

It lives in GUI_logs/.cache/warm, beside index.json and for the same reason:
derived, per-machine, regenerable in one read, and in .gitignore. Two
computers have different catalogues on different drives, so one machine's
warm answer is not just useless on another -- it is wrong there. Nothing in
cloudsync walks .cache, and nothing should.

WHY THE BODIES ARE COMPARED

Every rebuild hashes its own output against what the cache held. On most
boots nothing has changed, and then the client is told so and does not
re-fetch at all: no second megabyte over the socket, and no re-render of a
list somebody may already be reading. The refresh that costs nothing is the
one that did not need to happen.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

# How long the warm window may stay open, at the very most.
#
# Not a guess at how long boot takes -- the prime closes the window as soon
# as it has recomputed everything, which on this machine is about fifteen
# seconds. This is the backstop for the case where it never finishes: a
# drive that has gone away mid-read, a store lock nobody releases. Long
# enough that a genuinely slow catalogue still gets the benefit, short
# enough that a wedged prime is a nuisance for one view rather than for the
# session.
WINDOW_S = 150.0

# POSTs the interface makes on its way up, before anybody has touched
# anything. Measured from a real boot rather than assumed: these are the
# three that appear in the server log between the page load and the person's
# first click.
#
# Everything not on this list is somebody acting, and closes the window.
BOOT_CHATTER = (
    "/api/prefs",            # the theme and VACC reconciliation write-back
    "/api/activity",         # the boot entry in the activity log
    "/api/pipeline/check",   # the pipeline view checking its remembered folder
    "/api/errors/client",    # a client-side error, which must always land
)


def _hash(text):
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


# "nobody has looked yet", as distinct from "looked, and there was nothing".
# None means the second, and the difference decides whether a megabyte gets
# parsed a second time to answer a question somebody already answered.
_UNREAD = object()


def _prune(node, parts):
    """`node` without the field at this dotted path.

    Copies only the dicts along the path and shares everything else, because
    the thing being pruned is a megabyte and the field being removed is a
    timestamp. A path that is not there changes nothing.
    """
    if not parts or not isinstance(node, dict) or parts[0] not in node:
        return node
    out = dict(node)
    if len(parts) == 1:
        out.pop(parts[0], None)
    else:
        out[parts[0]] = _prune(out[parts[0]], parts[1:])
    return out


class WarmCache(object):
    """Last boot's answers, and the machinery for replacing them with this
    boot's."""

    def __init__(self, logs_dir, stamp=None):
        self.dir = os.path.join(logs_dir, ".cache", "warm")
        # What the cache was written by. Anything else on disk is ignored.
        self.stamp = stamp or "unknown"
        self._until = 0.0          # 0 means never armed
        self._ever_armed = False   # did the launcher ever open a window here?
        self._closed_why = None
        self._live = {}            # name -> hash of the live answer, once built
        self._changed = {}         # name -> did the live answer differ?
        self._locks = {}           # name -> lock, so two callers never build twice
        self._guard = threading.Lock()
        self._ignore = {}          # name -> fields that move on their own
        self._writes = 0           # so no two writes share a temporary name
        self._priming = False
        self._rev = 0              # bumped whenever a name goes live

    # ------------------------------------------------------------------
    # The window
    # ------------------------------------------------------------------
    def arm(self, window_s=WINDOW_S):
        """Open the warm window. Only the launcher calls this."""
        self._until = time.time() + window_s
        self._ever_armed = True
        self._closed_why = None

    def close(self, why="done"):
        if self._until:
            self._until = 0.0
            self._closed_why = why

    @property
    def armed(self):
        return self._until > 0 and time.time() < self._until

    def note_write(self, path):
        """A POST came in. If it is somebody acting, the window is over.

        Called from a before_request hook rather than from each route,
        because the rule is about the person and not about the endpoint --
        a route added next year gets it without anybody remembering to.
        """
        if not self.armed:
            return
        for ok in BOOT_CHATTER:
            if path == ok or path.startswith(ok + "/"):
                return
        self.close("somebody clicked something")

    # ------------------------------------------------------------------
    # Disk
    # ------------------------------------------------------------------
    def _path(self, name):
        return os.path.join(self.dir, name + ".json")

    def read(self, name):
        """Last run's body for this name, or None.

        None for every reason: no file, unreadable file, a file written by
        a different version of the code. The caller's fallback is to build
        it live, which is what the app did before this module, so every
        failure here is a return to the old behaviour rather than an error.
        """
        try:
            with open(self._path(name), "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception:                              # noqa: BLE001
            return None
        if not isinstance(rec, dict) or rec.get("stamp") != self.stamp:
            return None
        body = rec.get("body")
        return body if isinstance(body, dict) else None

    def write(self, name, body):
        """Put this answer on disk for the next boot.

        ONLY FROM A PROCESS THE LAUNCHER STARTED. A harness suite reads and
        writes the store constantly -- half of it exists to check what
        happens to a record mid-edit -- and a run that left its intermediate
        state in the warm cache would hand it to the next person who opened
        Jarvis. The window is what makes this feature safe, and a cache
        written outside the window is outside it.

        Written to a temporary file and renamed, because the alternative is
        a boot that reads a half-written megabyte.

        The temporary name is unique per CALL, and that is not decoration.

        Two Jarvises on one machine is an ordinary thing -- a second window
        opened rather than the first one found -- and they share this
        directory, so the process id has to be in there. But a counter is
        in there too, because `write` is public and the caller that
        protects it today is `_build_live`, which happens to hold a
        per-name lock. Relying on that means this method is safe by
        somebody else's arrangement rather than by its own, and the first
        caller who writes without the lock gets: two threads opening one
        temporary file, one truncating what the other is writing, and the
        splice renamed into place -- atomically, and as garbage. Measured
        that way round first: ten threads writing one name through a fixed
        temporary name left an unreadable file on disk.

        With a name per call they cannot meet. Whichever renames last wins,
        and every one of them is whole.

        A failure is swallowed: a cache that cannot be written is a slow
        next boot, and turning that into a 500 on a request that had
        already succeeded would be the module making things worse than not
        existing.
        """
        if not self._ever_armed:
            return
        with self._guard:
            self._writes += 1
            nth = self._writes
        tmp = "%s.%d.%d.part" % (self._path(name), os.getpid(), nth)
        try:
            os.makedirs(self.dir, exist_ok=True)
            text = json.dumps({"stamp": self.stamp, "at": time.time(),
                               "name": name, "body": body})
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, self._path(name))
        except Exception:                              # noqa: BLE001
            # Never leave the half-written one behind to be puzzled over.
            try:
                os.remove(tmp)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Serving
    # ------------------------------------------------------------------
    def volatile(self, name, paths):
        """Fields of this answer that move on their own.

        Declared once, honoured by both the route and the prime, so the two
        cannot disagree about what counts as a change.

        `/api/sync/status` is the case that made this necessary. Its index
        carries `generated`, the moment the roll-up was built, and a fresh
        process always rebuilds -- so every boot differed from every other
        boot by construction, every boot was reported as changed, and the
        page refetched a quarter of a megabyte every single time to be
        handed a different timestamp on identical data.

        Only for fields that say WHEN, never for fields that say WHAT. A
        count excluded from the comparison is a change nobody is told
        about, which is the one failure this whole module has to avoid.
        """
        self._ignore[name] = tuple(tuple(p.split(".")) for p in paths)

    def _sig(self, body, name=None):
        """A short, order-independent fingerprint of one answer.

        `sort_keys` because two dicts that say the same thing in a
        different order are the same answer, and `default=str` because a
        roll-up that has picked up a datetime somewhere should produce a
        slightly wrong fingerprint rather than an exception on a path that
        exists to save time. It is also what makes a tuple and a list
        compare equal, which matters: everything read back off disk is a
        list, and half of what the registry builds is tuples.
        """
        try:
            for path in self._ignore.get(name) or ():
                body = _prune(body, path)
            return _hash(json.dumps(body, sort_keys=True, default=str))
        except Exception:                              # noqa: BLE001
            return None

    def _lock_for(self, name):
        with self._guard:
            if name not in self._locks:
                self._locks[name] = threading.Lock()
            return self._locks[name]

    def _build_live(self, name, build, before=_UNREAD):
        """Compute the real answer, once, and remember what it came to.

        The lock is per name and it is the point: at boot the prime thread
        and the browser can want the same roll-up at the same moment, and
        without it they would each spend eight seconds producing identical
        output. With it the second one waits for the first, which is what
        the request already did before any of this existed.

        `before` is what the cache held, when the caller has already looked
        -- the whole answer is a megabyte and reading it twice to ask one
        question about it is a megabyte of parsing for nothing.
        """
        with self._lock_for(name):
            first = name not in self._live
            # Read before writing, or the comparison is against itself.
            if before is _UNREAD:
                before = self.read(name) if first else None
            body = build()
            sig = self._sig(body, name)
            same = first and before is not None and sig is not None \
                and sig == self._sig(before, name)
            if sig is None or sig != self._live.get(name):
                self.write(name, body)
            self._live[name] = sig
            if first:
                # Only the first live build of a name answers the question
                # the client is asking -- "was the thing I was shown right?"
                self._changed[name] = not same
                self._rev += 1
            return body

    def serve(self, name, build, fresh=False):
        """(body, how) -- the answer, and where it came from.

        `build` must take no arguments and must not touch `request`: it may
        be run on the prime thread, which has no request context. Anything
        a route reads off the query string is captured by the closure
        before it gets here, and a route with arguments that change the
        answer should not be warmed at all.
        """
        if fresh or not self.armed or name in self._live:
            return self._build_live(name, build), "live"
        cached = self.read(name)
        if cached is None:
            # Nothing written down -- a first boot, or the first after an
            # update. It is built live, exactly as it was before this
            # module, and the answer becomes the cache for next time.
            return self._build_live(name, build, before=None), "live"
        return cached, "cache"

    def marker(self, name, how):
        """What goes in the payload so the page knows what it was handed."""
        return {"name": name, "served": how, "rev": self._rev,
                "warming": self._priming and self.armed}

    # ------------------------------------------------------------------
    # The prime
    # ------------------------------------------------------------------
    def prime(self, jobs, delay=2.5):
        """Recompute every warmed answer in the background, then shut the
        window.

        One thread, and the jobs in order, deliberately. Four threads each
        merging a few thousand JSON files fight over the disk and the GIL
        and finish later than one -- and the point of this is to be out of
        the way of the page that is loading, not to be quick about it.

        `delay` is the same reasoning. The browser makes about fifteen
        requests in its first two seconds; starting a heavy read into the
        middle of that makes the cheap ones slow, which is the annoyance
        this module exists to remove. It waits for that burst to land.
        """
        if self._priming:
            return
        self._priming = True

        def run():
            try:
                time.sleep(delay)
                for name, build in jobs:
                    if not self.armed:
                        break
                    try:
                        self._build_live(name, build)
                    except Exception:                  # noqa: BLE001
                        # A roll-up that cannot be computed is a broken
                        # endpoint, and it will say so when somebody asks
                        # for it. It must not stop the rest priming.
                        self._live.setdefault(name, None)
                        self._rev += 1
            finally:
                self._priming = False
                self.close("primed")

        threading.Thread(target=run, name="jarvis-warm-prime",
                         daemon=True).start()

    # ------------------------------------------------------------------
    # What the page polls
    # ------------------------------------------------------------------
    def state(self):
        return {
            "armed": self.armed,
            "warming": self._priming and self.armed,
            "rev": self._rev,
            # name -> true when the live answer is in hand AND it differs
            # from what was served off the cache. False means the page was
            # shown the right thing and has nothing to do.
            "fresh": {k: bool(self._changed.get(k))
                      for k in self._live},
            "closed": self._closed_why,
        }
