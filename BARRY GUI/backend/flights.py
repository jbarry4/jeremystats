"""
flights.py -- every VACC job in flight, and the one door a submit goes through.

The user's rule (2026-10-20): the same tool, on the same recording, with the
same settings, is never submitted twice. While one is queued or running -- on
this computer or another -- the button offers to follow it. Once it has landed
it offers to open it, and "Run again anyway" is a deliberate second act.

Before this module there was no "already running" anywhere. `cfc.start` mints
a job per call and never compares specs; the routes checked only "already
landed"; `_DOPPLER_INFLIGHT` and `_BRACES_INFLIGHT` existed so a panel could
find a run again and were never asked before a submit. The client guarded
with `if (job) return`, set only after the POST came back -- and a VACC
route pushes code over ssh before it answers, so a second click in those
seconds submitted a second sbatch.

FOUR LOCKS, BECAUSE THERE ARE FOUR WAYS TO DUPLICATE

  1. This process: `FLIGHTS.claim(key)` under a lock, taken BEFORE any ssh.
     Two requests in the same second cannot both pass.
  2. This computer across a restart: the key goes into the run record
     (`GUI_logs/vacc_runs/<rid>.json`), and `_resume_vacc_batches` claims it
     again before the server serves.
  3. Another computer: the submit script makes `<workspace>/locks/<hash>`
     with `mkdir`, which is atomic on the cluster's filesystem, and refuses
     when it is already there. The node removes it when the job ends
     (`vacc_run.py`), the landing removes it again, and one older than the
     job could possibly run is stale. `cluster_holders` reads the same
     directory, so a route can refuse before it spends a submit.
  4. A double click: `submit_id`, minted per click, remembered here for ten
     minutes, so a retried POST gets the job the first one started.

Landed work is not this module's business: each tool already asks its own
vault or cache, and keeps doing so.

THE KEY is each tool's own "same question" hash -- Incisor's
`incisorvacc.request_hash`, Doppler's `cache_key`, Braces' `rq_hash` -- so
"the same job" means exactly what that tool's cache already means by it.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time

#: How long a `submit_id` is remembered: long enough to absorb a double
#: click, a retry after a timeout, and a page that re-posted on reload.
SUBMIT_MEMORY_S = 600.0
#: A cluster lock older than the job's own time limit plus this is stale.
STALE_MARGIN_S = 3600.0
#: Where the locks live, under the account's workspace.
LOCKS_DIR = "locks"

_HEX = re.compile(r"^[0-9a-f]{16}$")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def key(tool, gids, question):
    """`<tool>:<16 hex>` for one tool's question about one or more recordings.

    `question` is whatever that tool already uses to decide two requests are
    the same -- a hash or a dict -- and nothing else is added, so this module
    can never call two jobs different that the tool's cache calls the same.
    """
    if isinstance(gids, str) or gids is None:
        gids = [gids] if gids else []
    blob = json.dumps({"tool": tool, "gids": sorted(str(g) for g in gids),
                       "q": question}, sort_keys=True, default=str)
    return "%s:%s" % (tool, hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16])


def keyhash(k):
    """The 16 hex after the colon: safe as a directory name, checked."""
    h = (k or "").split(":", 1)[-1]
    if not _HEX.match(h):
        raise ValueError("not a flight key: %r" % (k,))
    return h


def safe(text, limit=40):
    """Something that can sit in a Slurm comment or a shell word."""
    return _SAFE.sub("-", str(text or ""))[:limit] or "-"


class Duplicate(Exception):
    """This exact job is already queued or running. `flight` says where."""

    def __init__(self, flight):
        self.flight = dict(flight or {})
        where = self.flight.get("where") or "this computer"
        since = self.flight.get("since")
        when = ""
        if since:
            mins = max(0, int((time.time() - float(since)) / 60))
            when = (" for %d min" % mins) if mins else " since a moment ago"
        super().__init__(
            "This exact job is already %s on the VACC, from %s%s. Follow it "
            "rather than starting a second one."
            % ("being submitted" if self.flight.get("state") == "claimed"
               else "running", where, when))

    def payload(self):
        return {"ok": False, "kind": "duplicate", "error": str(self),
                "duplicate": self.flight}


class Flights:
    """The one registry of VACC work in flight in this process."""

    def __init__(self):
        self._lock = threading.Lock()
        self._by_key = {}
        self._submits = {}

    # -- the door -----------------------------------------------------------
    def claim(self, k, **meta):
        """Take `k`, or raise Duplicate naming whoever has it."""
        now = time.time()
        with self._lock:
            have = self._by_key.get(k)
            if have is not None:
                raise Duplicate(have)
            flight = dict(meta, key=k, state="claimed", since=now,
                          where=meta.get("where") or "this computer")
            self._by_key[k] = flight
            return dict(flight)

    def attach(self, k, **patch):
        """Note what the claim turned into: the job id, the run id, slurm's."""
        with self._lock:
            f = self._by_key.get(k)
            if f is None:
                return None
            f.update({a: b for a, b in patch.items() if b is not None})
            if f.get("state") == "claimed" and (patch.get("job_id")
                                                or patch.get("rid")):
                f["state"] = "running"
            return dict(f)

    def release(self, k):
        """The job ended -- landed, failed or cancelled. Free the key."""
        with self._lock:
            return self._by_key.pop(k, None)

    def find(self, k):
        with self._lock:
            f = self._by_key.get(k)
            return dict(f) if f else None

    def list(self, tool=None):
        with self._lock:
            items = [dict(f) for f in self._by_key.values()
                     if tool is None or f.get("tool") == tool]
        items.sort(key=lambda f: f.get("since") or 0, reverse=True)
        return items

    # -- a double click -------------------------------------------------------
    def recall(self, submit_id):
        """The answer a repeat of this click should get, or None."""
        if not submit_id:
            return None
        now = time.time()
        with self._lock:
            for sid in [s for s, (at, _) in self._submits.items()
                        if now - at > SUBMIT_MEMORY_S]:
                self._submits.pop(sid, None)
            got = self._submits.get(str(submit_id))
            return dict(got[1]) if got else None

    def remember(self, submit_id, answer):
        if submit_id and isinstance(answer, dict):
            with self._lock:
                self._submits[str(submit_id)] = (time.time(), dict(answer))


FLIGHTS = Flights()


# --------------------------------------------------------------------------
# The cluster side
# --------------------------------------------------------------------------
def lock_root(cfg):
    from . import vacc
    return vacc._remote_path(cfg.get("workspace") or ".", LOCKS_DIR)


def lock_path(cfg, k):
    from . import vacc
    return vacc._remote_path(cfg.get("workspace") or ".", LOCKS_DIR,
                             keyhash(k))


def owner_line(k, rid, tool, device="", who=""):
    """The one-line JSON written into a lock: enough to say who has it."""
    return json.dumps({"key": k, "rid": rid, "tool": tool,
                       "device": device or "", "who": who or "",
                       "at": int(time.time())}, sort_keys=True)


def comment(tool, k, device=""):
    """`--comment` for sbatch, so `squeue -o %k` can say whose job it is."""
    return "jv1;%s;%s;%s" % (safe(tool, 16), keyhash(k), safe(device, 32))


def parse_comment(text):
    """The inverse of `comment`; None for any other job's comment."""
    bits = (text or "").strip().split(";")
    if len(bits) != 4 or bits[0] != "jv1" or not _HEX.match(bits[2]):
        return None
    return {"tool": bits[1], "hash": bits[2], "device": bits[3]}


def take_lock_sh(path, owner, stale_s):
    """Bash that takes the lock at `path` atomically, or reports its holder.

    Prints `jarvis-duplicate=<owner json>` and stops the script (exit 0,
    before any sbatch) when somebody else holds it. A lock older than
    `stale_s` belongs to a job that cannot still be running and is taken
    over. `path` and `owner` are quoted here; nothing else is interpolated.
    """
    from . import vacc
    p = vacc.q(path)
    return (
        "mkdir -p %(root)s\n"
        "if ! mkdir %(p)s 2>/dev/null; then\n"
        "  age=$(( $(date +%%s) - $(stat -c %%Y %(p)s 2>/dev/null || echo 0) ))\n"
        "  if [ \"$age\" -gt %(stale)d ]; then\n"
        "    rm -rf %(p)s && mkdir %(p)s\n"
        "  else\n"
        "    echo \"jarvis-duplicate=$(cat %(p)s/owner 2>/dev/null)\"\n"
        "    exit 0\n"
        "  fi\n"
        "fi\n"
        "printf '%%s\\n' %(owner)s > %(p)s/owner\n"
    ) % {"root": vacc.q(path.rsplit("/", 1)[0]), "p": p,
         "stale": int(stale_s), "owner": vacc.q(owner)}


def mark_lock_sh(path, owner):
    """Bash that records a lock without refusing (a batch member the route
    has already checked): the node's `finally` still removes it."""
    from . import vacc
    p = vacc.q(path)
    return ("mkdir -p %s\nprintf '%%s\\n' %s > %s/owner\n"
            % (p, vacc.q(owner), p))


def drop_own_lock_sh(path, rid):
    """Bash that removes the lock at `path` only if its owner names `rid`.

    Never an unconditional `rm`: a run refused as a duplicate must not take
    the other computer's lock with it on the way out.
    """
    from . import vacc
    p = vacc.q(path)
    needle = vacc.q('"rid": "%s' % rid)
    return ("if grep -qF %s %s/owner 2>/dev/null; then rm -rf %s; fi"
            % (needle, p, p))


def duplicate_in(output):
    """The holder a submit script reported, or None."""
    for line in (output or "").splitlines():
        if line.startswith("jarvis-duplicate="):
            raw = line[len("jarvis-duplicate="):].strip()
            try:
                return json.loads(raw) if raw else {}
            except ValueError:
                return {}
    return None


def cluster_holders(cfg, ssh=None, timeout=30):
    """Every lock on the cluster for this account: {hash: owner dict}.

    One connection. An unreadable owner file still counts: something holds
    the lock even if it cannot say what.
    """
    from . import vacc
    root = vacc.q(lock_root(cfg))
    cmd = ("for d in %s/*/; do [ -d \"$d\" ] || continue; "
           "h=$(basename \"$d\"); "
           "echo \"lock=$h|$(stat -c %%Y \"$d\" 2>/dev/null)|"
           "$(head -c 600 \"$d/owner\" 2>/dev/null)\"; done" % root)
    run = ssh or (lambda c: vacc._ssh(cfg, c, timeout=timeout))
    out = run(cmd)
    held = {}
    for line in (out or "").splitlines():
        if not line.startswith("lock="):
            continue
        h, _, rest = line[5:].partition("|")
        mtime, _, raw = rest.partition("|")
        if not _HEX.match(h):
            continue
        try:
            owner = json.loads(raw) if raw.strip() else {}
        except ValueError:
            owner = {}
        try:
            owner.setdefault("at", int(mtime))
        except ValueError:
            pass
        held[h] = owner
    return held


def default_lock(tool, spec_local, rid, seconds=None, device=""):
    """A lock for a run whose route did not claim one (vaccrun.VaccRun).

    The safety net under every tool, including those whose routes have not
    been given a door yet: the local spec is the run's identity (it is what
    the caches are keyed on), so two runs of one spec share a lock and the
    second is refused on the cluster, atomically, at submit.
    """
    import socket
    k = key(tool, [], spec_local or {})
    dev = device or socket.gethostname()
    return {"key": k, "device": dev,
            "owner": owner_line(k, rid, tool, dev, ""),
            "stale_s": float(seconds or 3600) * 3 + STALE_MARGIN_S}


def holder_flight(k, owner, here_device=""):
    """A cluster lock, said the way a local flight is."""
    dev = (owner or {}).get("device") or ""
    return {"key": k, "state": "running", "tool": (owner or {}).get("tool"),
            "rid": (owner or {}).get("rid"), "who": (owner or {}).get("who"),
            "since": (owner or {}).get("at"),
            "where": ("this computer (from before a restart)"
                      if dev and dev == here_device else (dev or
                                                          "another computer")),
            "on_cluster": True}
