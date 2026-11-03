"""
feed.py -- what the server is doing, said as it happens.

The bottom "Output" dock of the page reads this. Before it existed the
server worked in silence: a cold registry read took six seconds, a sync
status nineteen, and the only thing on screen was a spinner -- so somebody
waited without knowing whether anything was happening at all, and the usual
response to that is to click again, which makes it slower. The rule this
module serves is that nobody should ever "just wait": anything that takes
long enough to notice says what it is doing while it does it.

THREE SOURCES, ONE BUFFER

  * Requests (`install_narration`). Every /api/ request is watched; one that
    is still running after a second gets a line saying, in words, what it
    is doing -- "Reading the recording list -- 412 of 1,461" -- and the same
    line is updated in place when it finishes. A request under a second
    produces nothing at all, which is almost all of them: the feed is for
    the waits, not a log of every poll.
  * Background work: local jobs (runner.py), the cloud sync loop, VACC runs,
    the warm start. Each says start / progress / end under a key of its own.
  * Anything else that calls `say`.

A line with a KEY replaces the earlier line with that key: it gets a new id
and the old one leaves the buffer. That is what lets the page update a line
in place rather than append a new one per tick, and what lets a client that
reconnects with `since=<id>` receive the newest version of a line it has
already seen an older version of.

IDS START AT THE CLOCK, NOT AT ONE

A restart (start.py's supervisor, `/api/restart`) begins a new process with
a new buffer. If ids started at 1 each time, a browser's EventSource that
reconnects with the Last-Event-ID of the previous process would be asking
for "everything after 4,000" from a process that has said 30 lines, and
would hear none of them. Starting at the boot's wall-clock milliseconds keeps
ids increasing across restarts, so the old id is simply older than everything
here and the whole buffer is replayed. `BOOT` still changes, for a page that
wants to know a restart happened.

NOTHING HERE MAY BLOCK THE CALLER

`say` is called from request threads, the sync loop and job pumps. Each
subscriber (an open event stream) has a bounded queue; a subscriber that
falls behind by a thousand lines is dropped -- it reconnects and replays
from the buffer -- rather than ever making `say` wait for it.
"""
from __future__ import annotations

import contextvars
import json
import os
import queue
import re
import threading
import time
import uuid
from collections import OrderedDict

# Which process this is. Chosen once, at import: the page compares it to
# notice a restart.
BOOT = os.urandom(6).hex()

MAX_LINES = 3000
# How much one subscriber may fall behind before it is dropped.
SUB_QUEUE = 1000
# A request becomes a line once it has run this long.
SHOW_AFTER_S = 1.0
# How often the one watcher thread looks at the requests in flight.
WATCH_EVERY_S = 0.25

LANES = ("jarvis", "vacc")

_LOCK = threading.Lock()
_LINES = OrderedDict()          # id -> line, oldest first
_BY_KEY = {}                    # key -> id of its current line
_NEXT = [int(time.time() * 1000)]
_SUBS = set()


# --------------------------------------------------------------------------
# The buffer
# --------------------------------------------------------------------------
def say(text, lane="jarvis", kind="info", level="info", key=None,
        progress=None, done=False, ms=None):
    """Add a line (or replace the line with this key). Returns it.

    Never raises and never waits on a reader: this is called from inside
    work that has nothing to do with the feed, and a feed that broke a sync
    or a job would be worse than no feed.
    """
    try:
        if progress is not None:
            progress = [int(progress[0]), int(progress[1])]
    except (TypeError, ValueError, IndexError):
        progress = None
    line = {
        "id": 0, "at": time.time(),
        "lane": lane if lane in LANES else "jarvis",
        "kind": kind or "info", "level": level or "info",
        "text": str(text), "key": key, "progress": progress,
        "done": bool(done), "ms": None if ms is None else int(ms),
    }
    with _LOCK:
        _NEXT[0] += 1
        line["id"] = _NEXT[0]
        if key is not None:
            old = _BY_KEY.get(key)
            if old is not None:
                _LINES.pop(old, None)
            _BY_KEY[key] = line["id"]
        _LINES[line["id"]] = line
        while len(_LINES) > MAX_LINES:
            gone_id, gone = _LINES.popitem(last=False)
            k = gone.get("key")
            if k is not None and _BY_KEY.get(k) == gone_id:
                del _BY_KEY[k]
        # Inside the lock so two lines said at once reach every subscriber
        # in id order. put_nowait never waits, so this costs nothing.
        for sub in list(_SUBS):
            try:
                sub.q.put_nowait(line)
            except queue.Full:
                sub.dropped = True
                _SUBS.discard(sub)
    return line


def last():
    """The newest id, or the boot's starting point when nothing was said."""
    with _LOCK:
        return next(reversed(_LINES)) if _LINES else _NEXT[0]


def lines(since=0, lane=None, limit=500):
    """Lines newer than `since`, oldest first, at most `limit` (the newest
    ones when there are more). A `since` past the newest id came from
    another process, so it is read as "everything"."""
    try:
        since = int(since or 0)
    except (TypeError, ValueError):
        since = 0
    out = []
    with _LOCK:
        newest = next(reversed(_LINES)) if _LINES else _NEXT[0]
        if since > newest:
            since = 0
        for lid in reversed(_LINES):
            if lid <= since:
                break
            ln = _LINES[lid]
            if lane and ln["lane"] != lane:
                continue
            out.append(ln)
            if len(out) >= limit:
                break
    out.reverse()
    return out


class _Sub:
    __slots__ = ("q", "dropped")

    def __init__(self):
        self.q = queue.Queue(maxsize=SUB_QUEUE)
        self.dropped = False


def subscribe():
    sub = _Sub()
    with _LOCK:
        _SUBS.add(sub)
    return sub


def unsubscribe(sub):
    with _LOCK:
        _SUBS.discard(sub)


def sse(since=0, lane=None, heartbeat_s=15.0):
    """The event stream, as a generator of text chunks.

    Subscribes BEFORE reading the backlog, so a line said between the two is
    in the queue rather than lost, and skips anything at or below the last
    id already sent, so it is not sent twice. No lock is held while waiting:
    the wait is on this subscriber's own queue.
    """
    sub = subscribe()
    try:
        yield "retry: 2000\nevent: hello\ndata: %s\n\n" % json.dumps(
            {"boot": BOOT, "last": last()})
        sent = 0
        for ln in lines(since, lane, limit=MAX_LINES):
            sent = ln["id"]
            yield "id: %d\ndata: %s\n\n" % (ln["id"], json.dumps(ln))
        while True:
            try:
                ln = sub.q.get(timeout=heartbeat_s)
            except queue.Empty:
                if sub.dropped:
                    return          # the page reconnects and replays
                yield ": hb\n\n"
                continue
            if ln["id"] <= sent or (lane and ln["lane"] != lane):
                continue
            sent = ln["id"]
            yield "id: %d\ndata: %s\n\n" % (ln["id"], json.dumps(ln))
            if sub.dropped and sub.q.empty():
                return
    finally:
        unsubscribe(sub)


# --------------------------------------------------------------------------
# Requests, narrated
# --------------------------------------------------------------------------
# What a request is doing, in words. Matched by path, segment by segment;
# "*" stands for one segment (an id, a gid, a name). The longest matching
# pattern wins, so a specific route can say more than its family.
#
# Written for the person at the bench, so no route names, no methods and no
# status codes -- the same rule as everything else on the page.
ROUTE_WORDS = [
    ("/api/sync/status", "Taking stock of what is saved on this computer"),
    ("/api/sync/reindex", "Rebuilding the index of what is saved here"),
    ("/api/sync/pending-migrations", "Checking the shared database is up to date"),
    ("/api/registry", "Reading the recording list"),
    ("/api/registry/audit", "Checking the recording list for problems"),
    ("/api/registry/merge", "Merging two recording records into one"),
    ("/api/registry/split", "Splitting a recording record in two"),
    ("/api/registry/retire", "Retiring a recording record"),
    ("/api/registry/*", "Looking up one recording"),
    ("/api/registry/*/patch", "Saving a change to one recording"),
    ("/api/registry/*/probe", "Checking where one recording is"),
    ("/api/sessions", "Reading every recording record"),
    ("/api/sessionref", "Looking up a recording"),
    ("/api/catalog", "Listing the analysis scripts"),
    ("/api/discover", "Looking for recordings"),
    ("/api/browse", "Listing a folder"),
    ("/api/csc/open", "Opening the recording"),
    ("/api/csc/window", "Reading a stretch of the recording"),
    ("/api/csc/overview", "Drawing the whole-recording overview strip"),
    ("/api/csc/export", "Exporting a stretch of the recording"),
    ("/api/panel", "Drawing a panel"),
    ("/api/panel/prewarm", "Getting the next panels ready"),
    ("/api/session/health", "Checking the recording's health"),
    ("/api/session/healthlog", "Recording the health check"),
    ("/api/session/continuity", "Checking the recording for gaps"),
    ("/api/session/timebasis", "Working out the recording's clock"),
    ("/api/session/retime", "Re-timing the recording"),
    ("/api/session/manifest", "Reading the recording's file list"),
    ("/api/session", "Working on this recording"),
    ("/api/cloud/items", "Checking which records have reached the shared database"),
    ("/api/cloud/sync", "Syncing with the shared database"),
    ("/api/cloud/status", "Checking the shared database connection"),
    ("/api/cloud/unshared", "Listing what has not been shared yet"),
    ("/api/cloud/mirror", "Writing the browsable copy of the Event Bank"),
    ("/api/cloud", "Talking to the shared database"),
    ("/api/vacc/knows", "Working out which recordings the VACC can read"),
    ("/api/vacc/inventory", "Listing what the VACC holds"),
    ("/api/vacc/check", "Checking the VACC connection"),
    ("/api/vacc/status", "Checking the VACC connection"),
    ("/api/vacc/scan", "Looking for recordings on the VACC"),
    ("/api/vacc/browse", "Listing a folder on the VACC"),
    ("/api/vacc/upload", "Sending recordings to the VACC"),
    ("/api/vacc/upload/plan", "Planning an upload to the VACC"),
    ("/api/vacc/signin", "Signing in to the VACC"),
    ("/api/vacc/flights", "Listing the jobs on the VACC"),
    ("/api/vacc/found", "Reading what was found on the VACC"),
    ("/api/vacc", "Talking to the VACC"),
    ("/api/toolkit/scopes", "Gathering the mice, groups and days to choose from"),
    ("/api/toolkit/bad-channels", "Collecting the bad channels"),
    ("/api/toolkit", "Working in the ToolKit"),
    ("/api/toolfeed", "Reading what the tools have done"),
    ("/api/warmup/engines", "Loading the analysis libraries"),
    ("/api/warmup/last", "Reopening the last recording"),
    ("/api/warmup/overviews", "Preparing overview strips"),
    ("/api/errors", "Reading the error log"),
    ("/api/errors/grouped", "Grouping the error log"),
    ("/api/errors/export", "Exporting the error log"),
    ("/api/digest", "Putting together what changed"),
    ("/api/devices", "Listing this lab's computers"),
    ("/api/devices/feed", "Reading what the other computers did"),
    ("/api/health/summary", "Summarising recording health"),
    ("/api/results", "Reading the results"),
    ("/api/results/thumb", "Drawing a thumbnail"),
    ("/api/results/manifest", "Listing a folder of results"),
    ("/api/bank", "Reading the Event Bank"),
    ("/api/bank/export", "Exporting from the Event Bank"),
    ("/api/bank/for-session", "Finding what is banked for this recording"),
    ("/api/bank/sync", "Checking the Event Bank is in step"),
    ("/api/curation", "Reading the curation sets"),
    ("/api/curation/dataset", "Collecting the curation dataset"),
    ("/api/curation/startable", "Finding recordings ready to curate"),
    ("/api/curation/*/*", "Working on a curation set"),
    ("/api/rootcanal/read", "Root Canal: reading the recording"),
    ("/api/rootcanal/batch", "Root Canal: starting a batch"),
    ("/api/rootcanal", "Working in Root Canal"),
    ("/api/incisor", "Working in Incisor"),
    ("/api/doppler", "Working in Doppler"),
    ("/api/braces", "Working in Braces"),
    ("/api/confluence", "Working in Confluence"),
    ("/api/panorama", "Working in Panorama"),
    ("/api/horizon", "Working in Horizon"),
    ("/api/strata", "Working in StrataScope"),
    ("/api/layers", "Reading the layer sheets"),
    ("/api/dspca", "Working on the dentate spike map"),
    ("/api/cfc/comodulogram", "Computing a comodulogram"),
    ("/api/cfc", "Working on coupling"),
    ("/api/spectrum/run", "Computing a spectrum"),
    ("/api/arc/monolith", "Working on the Monolith"),
    ("/api/arc/circuit", "Working on circuits"),
    ("/api/arc/precon", "Working on the Precon analysis"),
    ("/api/arc/drift", "Working on drift"),
    ("/api/arc/sanity", "Checking the channels"),
    ("/api/arc", "Working in the Arc"),
    ("/api/figures", "Working on a figure"),
    ("/api/figkit", "Drawing a figure"),
    ("/api/figure", "Drawing a figure"),
    ("/api/toothfairy", "Working with Tooth Fairy"),
    ("/api/aibeta", "Working with Tooth Fairy"),
    ("/api/kilosort", "Working with Kilosort"),
    ("/api/video", "Working on video"),
    ("/api/histoimg", "Working on histology images"),
    ("/api/artifacts", "Reading saved results"),
    ("/api/people", "Reading the people list"),
    ("/api/presence", "Checking who is here"),
    ("/api/history", "Reading the run history"),
    ("/api/answers", "Checking saved answers"),
    ("/api/activity", "Reading the activity log"),
    ("/api/backup", "Listing the backup copy"),
    ("/api/run", "Starting a script"),
    ("/api/scratch/run", "Starting a scratch script"),
    ("/api/spikes", "Working on spikes"),
    ("/api/events", "Reading events"),
    ("/api/deck", "Working on a deck"),
    ("/api/decks", "Listing the decks"),
    ("/api/mice", "Reading the colony"),
    ("/api/notes", "Reading notes"),
    ("/api/housekeeping", "Tidying up"),
]

# Longest pattern first, then the one with fewer wildcards.
_PATTERNS = sorted(
    ((tuple(p.strip("/").split("/")), w) for p, w in ROUTE_WORDS),
    key=lambda pw: (-len(pw[0]), sum(1 for s in pw[0] if s == "*")))

# Paths that are never narrated: the feed itself, the reconnect ping, and
# the long poll that is held open on purpose.
QUIET = ("/api/feed", "/api/ping", "/api/link")

_IDLIKE = re.compile(r"^(?:[0-9a-f]{8,}|\d+|[0-9a-f-]{20,})$", re.I)


def words_for(path):
    """What a request to `path` is doing, in words. Never the path itself."""
    segs = tuple(s for s in (path or "").strip("/").split("/") if s)
    for pat, words in _PATTERNS:
        if len(pat) > len(segs):
            continue
        if all(p == "*" or p == s for p, s in zip(pat, segs)):
            return words
    # Built from the route's own words: drop "api" and anything that looks
    # like an id, and say the rest.
    bits = [s for s in segs[1:] if not _IDLIKE.match(s)]
    bits = [re.sub(r"[-_.]+", " ", b).strip() for b in bits]
    bits = [b for b in bits if b and not re.search(r"[<>%?=&]", b)]
    return ("Working on " + " ".join(bits)) if bits else "Working"


def _fmt_n(n):
    try:
        return "{:,}".format(int(n))
    except (TypeError, ValueError):
        return str(n)


def _seconds(ms):
    s = ms / 1000.0
    if s < 60:
        return "%.1f s" % s
    return "%d min %d s" % (int(s // 60), int(s % 60))


# The request this thread is serving, for `step`.
_REQ = contextvars.ContextVar("jarvis_feed_req", default=None)
_ACTIVE = {}                    # rid -> record
_REQ_LOCK = threading.Lock()
_WATCHER = []


def current():
    """The record of the request being served here, or None. For handing
    to `step(..., req=...)` from a worker thread the request started."""
    return _REQ.get()


def step(text=None, done=None, total=None, req=None):
    """Say what the current request is doing now.

    Remembered even before the request has run a second, so the first line
    that appears already carries it. Outside a request (a background thread,
    a script) it does nothing. `done`/`total` are a count, shown as
    "412 of 1,461".
    """
    rec = req if req is not None else _REQ.get()
    if rec is None:
        return
    try:
        prog = None
        if done is not None and total:
            prog = [int(done), int(total)]
        with _REQ_LOCK:
            rec["step"] = None if text is None else str(text)
            rec["progress"] = prog
            rec["rev"] += 1
    except Exception:                                    # noqa: BLE001
        pass


def _text(rec):
    tail = rec.get("step") or ""
    prog = rec.get("progress")
    if prog:
        tail = (tail + " " if tail else "") + "%s of %s" % (
            _fmt_n(prog[0]), _fmt_n(prog[1]))
    return rec["words"] + (" — " + tail if tail else "")


def _show(rec):
    """Emit (or update) the line for a request still running. Caller holds
    _REQ_LOCK, so a finish cannot slip in between the check and the say."""
    if rec.get("finished"):
        return
    rec["shown"] = True
    rec["shown_rev"] = rec["rev"]
    say(_text(rec), lane="jarvis", kind="request", level="info",
        key=rec["key"], progress=rec.get("progress"))


def _watch():
    while True:
        time.sleep(WATCH_EVERY_S)
        try:
            now = time.perf_counter()
            with _REQ_LOCK:
                for rec in list(_ACTIVE.values()):
                    if now - rec["t0"] < SHOW_AFTER_S:
                        continue
                    if not rec["shown"] or rec["shown_rev"] != rec["rev"]:
                        _show(rec)
        except Exception:                                # noqa: BLE001
            pass                # the watcher must outlive any one request


def _finish(rec, ok):
    with _REQ_LOCK:
        if rec.get("finished"):
            return
        rec["finished"] = True
        _ACTIVE.pop(rec["id"], None)
        if not rec["shown"]:
            return              # under a second: nothing was ever said
        ms = int((time.perf_counter() - rec["t0"]) * 1000)
        text = rec["words"] + (" — done in %s" % _seconds(ms) if ok
                               else " — stopped with a problem after %s"
                               % _seconds(ms))
        say(text, lane="jarvis", kind="request",
            level="ok" if ok else "err", key=rec["key"], done=True, ms=ms,
            progress=rec.get("progress"))


def install_narration(app):
    """The before/after/teardown hooks, and the one watcher thread.

    Registered by app.py right after the app is made, so the start time is
    taken before any other hook has spent anything.
    """
    from flask import request

    def quiet(path):
        # Whole path segments only. A bare startswith also silenced every
        # route that merely begins with the same letters -- /api/feedback,
        # /api/pinger, /api/links -- so a slow one of those was never
        # narrated. The route itself, or anything under it, is quiet.
        if not path.startswith("/api/"):
            return True
        return any(path == q or path.startswith(q + "/") for q in QUIET)

    @app.before_request
    def _feed_begin():
        try:
            path = request.path
            if quiet(path) or request.args.get("wait"):
                return
            rid = (request.headers.get("X-Jarvis-Req") or "").strip()[:64]
            if not rid or not re.match(r"^[A-Za-z0-9._:-]+$", rid):
                rid = uuid.uuid4().hex[:12]
            rec = {"id": rid + ":" + uuid.uuid4().hex[:4], "key": "req:" + rid,
                   "words": words_for(path), "t0": time.perf_counter(),
                   "step": None, "progress": None, "rev": 0,
                   "shown": False, "shown_rev": -1, "finished": False,
                   "streaming": False, "status": None}
            with _REQ_LOCK:
                _ACTIVE[rec["id"]] = rec
            request.environ["jarvis.feed"] = rec
            request.environ["jarvis.feed.token"] = _REQ.set(rec)
        except Exception:                                # noqa: BLE001
            pass

    @app.after_request
    def _feed_header(resp):
        try:
            rec = request.environ.get("jarvis.feed")
            if rec is not None:
                resp.headers["X-Jarvis-Req-Key"] = rec["key"]
                rec["status"] = resp.status_code
                if resp.is_streamed:
                    # A streamed answer is still being worked on after the
                    # view returns -- teardown runs before the first chunk
                    # is sent. Finish when the stream is closed instead.
                    rec["streaming"] = True
                    token = request.environ.get("jarvis.feed.token")

                    def closed(rec=rec, token=token):
                        _finish(rec, (rec.get("status") or 200) < 400)
                        _reset(token)
                    resp.call_on_close(closed)
        except Exception:                                # noqa: BLE001
            pass
        return resp

    @app.teardown_request
    def _feed_end(exc=None):
        try:
            rec = request.environ.get("jarvis.feed")
            if rec is None or rec.get("streaming"):
                return
            status = rec.get("status")
            ok = exc is None and (status is None or status < 400)
            _finish(rec, ok)
            _reset(request.environ.get("jarvis.feed.token"))
        except Exception:                                # noqa: BLE001
            pass

    if not _WATCHER:
        t = threading.Thread(target=_watch, daemon=True,
                             name="jarvis-feed-watch")
        _WATCHER.append(t)
        t.start()


def _reset(token):
    if token is None:
        return
    try:
        _REQ.reset(token)
    except (ValueError, RuntimeError):
        # Closed from another context: the thread is ending anyway, but a
        # test client reuses its thread, so make sure nothing leaks.
        _REQ.set(None)


# --------------------------------------------------------------------------
# Words for background work
# --------------------------------------------------------------------------
TOOL_NAMES = {
    "rootcanal": "Root Canal", "incisor": "Incisor", "doppler": "Doppler",
    "braces": "Braces", "strata": "StrataScope", "drift": "Drift",
    "circuit": "Circuit", "coupling": "Coupling", "spark": "Spark",
    "panorama": "Panorama", "horizon": "Horizon", "cfc": "Coupling",
    "toothfairy": "Tooth Fairy", "dspca": "Dentate spike map",
    "monolith": "Monolith", "precon": "Precon analysis",
}


def tool_name(tool):
    t = str(tool or "").strip()
    return TOOL_NAMES.get(t.lower()) or (t[:1].upper() + t[1:]) or "A job"


def recording_name(spec):
    """A short name for the recording a spec is about, or ''."""
    try:
        spec = spec or {}
        for k in ("label", "name"):
            if spec.get(k):
                return str(spec[k])
        p = str(spec.get("path") or "").rstrip("\\/")
        return re.split(r"[\\/]", p)[-1] if p else ""
    except Exception:                                    # noqa: BLE001
        return ""


def vacc(rid, tool, what="", state="running", done=None, total=None,
         why=None):
    """One VACC run's line, keyed `vacc:<rid>` so it updates in place.

    `state` is submitting / queued / running / fetching / landed / failed /
    cancelled. `what` names the recording (or "9 recordings").
    """
    try:
        name = tool_name(tool) + (" on " + what if what else "")
        phrase = {
            "submitting": "sending it to the VACC",
            "queued": "waiting in the VACC queue",
            "running": "running on the VACC",
            "fetching": "bringing the answer home",
            "landed": "finished on the VACC",
            "failed": "did not finish on the VACC",
            "cancelled": "cancelled",
            "detached": "lost touch with the VACC; it will be picked up again",
        }.get(state, state)
        text = name + ": " + phrase
        if total:
            text += ", %s of %s parts done" % (_fmt_n(done or 0),
                                               _fmt_n(total))
        if why and state == "failed":
            text += " (" + str(why).strip() + ")"
        level = {"landed": "ok", "failed": "err", "cancelled": "warn",
                 "detached": "warn"}.get(state, "info")
        return say(text, lane="vacc", kind="vacc", level=level,
                   key="vacc:%s" % rid,
                   progress=[done or 0, total] if total else None,
                   done=state in ("landed", "failed", "cancelled"))
    except Exception:                                    # noqa: BLE001
        return None
