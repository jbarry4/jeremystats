"""
toolfeed.py -- What has been happening in one tool, from the shared table.

Every mode already writes to `activity`: entering, leaving, labelling,
banking, marking a channel bad, starting a sort. Those rows already go up to
Supabase. What was missing is anybody being able to READ them per tool --
so "is somebody else curating this?", "what did that import actually do?"
and "why does this recording look different from yesterday?" were questions
you answered by asking a person.

Two things this is for, in the order they matter:

  reproducibility  the feed is the record of what was done to a recording,
                   by whom, on which machine, in what order. It is the thing
                   a methods section is written from six months later.
  debugging        when something looks wrong, the sequence that produced it
                   is right there, including the actions from the OTHER
                   machine that this one only learned about through the
                   sync.

Any future toolkit is covered without touching this file. A tool with no
entry falls back to its own id as the action prefix, so a new mode that logs
`mytool.something` has a working feed the moment it logs anything. The map
below exists only for the tools whose actions are not named after them --
curation writes `bank.*` as well, Kilosort writes `phy.*`, and bad channels
were logged as `channels.*` long before there was a toolkit page for them.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from . import extras

# tool id -> the action prefixes that belong to it.
#
# Ids are the ToolKit's own (`toolButton('curate', ...)`), so the page and
# the feed cannot drift apart.
TOOLS = {
    "bad": {
        "name": "Bad channels",
        "prefixes": ["channels.", "toolkit.bad_channels", "session.bad"],
    },
    "curate": {
        "name": "Event curation",
        "prefixes": ["curation.", "bank.", "events."],
    },
    "strata": {
        "name": "StrataScope",
        "prefixes": ["strata.", "layers."],
    },
    "cfc": {
        "name": "Braid",
        "prefixes": ["cfc.", "cfcguide."],
    },
    # Here for the name, not the prefixes: `panorama.*` is what the fallback
    # would have worked out on its own. Without an entry the feed is headed
    # "panorama" where every other tool has a capital letter.
    "panorama": {
        "name": "Panorama",
        "prefixes": ["panorama."],
    },
    "kilosort": {
        "name": "Kilosort",
        "prefixes": ["spikes.", "phy.", "pipeline."],
    },
    "snapshots": {
        "name": "Import sorted snapshots",
        "prefixes": ["dsimport.", "curation.import"],
    },
}

LIMIT = 200
MAX_LIMIT = 1000

# One read of the shared table answers every feed.
#
# Each feed used to ask Supabase for its own tool's rows on every poll --
# every 3 s per open ToolKit, hidden window or not, ~1,200 requests an hour
# on its own (constitution §11, leak 5). Other machines' actions cannot
# arrive faster than their push (a minute at most), so the table is now
# read at most every REFRESH_S seconds, for everybody's rows at once, and
# each tool's feed is cut from that locally. A tool's older history is read
# once per process the first time its feed is opened.
REFRESH_S = 30
# Rows are stamped where the action happened and pushed up to a minute or
# two later, so each refresh re-asks for the last few minutes; ids fold the
# repeats away. Cheap: it is a handful of rows, compressed.
OVERLAP_S = 300
SEED = 60              # a tool's own newest rows, read once
KEEP = 3000            # rows held; the oldest go first

_LOCK = threading.Lock()
_CACHE = {"rows": {}, "at": 0.0, "through": None, "seeded": set()}


def prefixes_for(tool):
    """The action prefixes for a tool, named or not.

    An unknown tool gets `<id>.`, which is what a new mode logs under unless
    it goes out of its way not to. That is the whole "any future toolkit"
    provision: no registration step, and no file to remember to edit.
    """
    tool = (tool or "").strip()
    if not tool:
        return []
    got = TOOLS.get(tool)
    if got:
        return list(got["prefixes"])
    return [tool + "."]


def name_for(tool):
    got = TOOLS.get((tool or "").strip())
    return got["name"] if got else (tool or "").strip()


def matches(action, prefixes):
    a = str(action or "")
    return any(a == p.rstrip(".") or a.startswith(p) for p in prefixes)


def _cloud_query(prefixes, since=None):
    """PostgREST's filter for "any of these prefixes", newest first.

    `or=(...)` with `like` per prefix. The alternative -- fetching
    everything and filtering here -- is a table scan across every machine's
    history to show twenty rows. The limit is `Cloud.select`'s to add; it
    used to be here as well, so every request carried two.
    """
    parts = ["action.like.%s*" % p.replace(",", "") for p in prefixes]
    q = "or=(%s)" % ",".join(parts)
    if since:
        q += "&at=gt.%s" % since
    return q + "&order=at.desc"


def _iso_before(stamp, seconds):
    t = extras.moment_key(stamp)
    if not t:
        return None
    return datetime.fromtimestamp(t - seconds, timezone.utc).isoformat()


def _shared(cloud, tool, prefixes):
    """Every recent shared row this process knows of, refreshed at most
    every REFRESH_S seconds and seeded once per tool. Raises when the cloud
    does not answer, so the caller can say so."""
    with _LOCK:
        # Away is a state, not an error to retry every poll (constitution
        # §11, rule 11): after a failure, wait a refresh before asking again.
        if time.time() - _CACHE.get("fail_at", 0.0) < REFRESH_S:
            raise RuntimeError("not reachable just now")
        rows = _CACHE["rows"]
        got = []
        try:
            if tool not in _CACHE["seeded"]:
                got += cloud.select("activity",
                                    query=_cloud_query(prefixes), limit=SEED)
                _CACHE["seeded"].add(tool)
            fresh = []
            if time.time() - _CACHE["at"] >= REFRESH_S:
                since = _iso_before(_CACHE["through"], OVERLAP_S)
                q = (("at=gt.%s&order=at.desc" % since) if since
                     else "order=at.desc")
                fresh = cloud.select("activity", query=q, limit=500)
                _CACHE["at"] = time.time()
        except Exception:
            _CACHE["fail_at"] = time.time()
            raise
        got += fresh
        if fresh:
            for r in fresh:
                if (extras.moment_key(r.get("at"))
                        > extras.moment_key(_CACHE["through"])):
                    _CACHE["through"] = r.get("at")
        for r in got:
            if r.get("id"):
                rows[r["id"]] = _shape(r)
        if len(rows) > KEEP:
            keep = sorted(rows.values(),
                          key=lambda r: extras.moment_key(r.get("at")),
                          reverse=True)[:KEEP]
            _CACHE["rows"] = rows = {r["id"]: r for r in keep}
        return list(rows.values())


def feed(store, cloud, tool, limit=LIMIT, since=None):
    """Recent activity for one tool, from Supabase when it is reachable.

    Falls back to this machine's own log rather than failing: a feed that
    disappears when the network does is a feed nobody trusts. The answer
    says which it is, because "only this machine" and "everybody" are
    different claims and the reader has to know which one they are looking
    at.
    """
    prefixes = prefixes_for(tool)
    limit = max(1, min(int(limit or LIMIT), MAX_LIMIT))
    if not prefixes:
        return {"ok": False, "error": "No tool named."}

    # This machine's own log, always. It is a local file read, and it is
    # the only place an action exists until the next push -- so a feed built
    # from the shared table alone cannot show what you just did.
    mine = _local(store, prefixes, limit, since)

    if cloud is not None and getattr(cloud, "configured", False):
        try:
            cut = extras.moment_key(since) if since else None
            shared = [r for r in _shared(cloud, tool, prefixes)
                      if matches(r.get("action"), prefixes)
                      and (cut is None
                           or extras.moment_key(r.get("at")) > cut)]
            shared.sort(key=lambda r: extras.moment_key(r.get("at")),
                        reverse=True)
            shared = shared[:limit]
            return {"ok": True, "source": "supabase", "tool": tool,
                    "name": name_for(tool), "prefixes": prefixes,
                    "rows": _merge(shared, mine, limit)}
        except Exception as exc:                          # noqa: BLE001
            # Said, not swallowed: a feed that has quietly fallen back to one
            # machine looks exactly like a lab where nobody else is working.
            local = _local(store, prefixes, limit, since)
            return {"ok": True, "source": "this machine", "tool": tool,
                    "name": name_for(tool), "prefixes": prefixes,
                    "rows": local,
                    "note": "Supabase did not answer (%s), so this is only "
                            "what this computer has done."
                            % str(exc)[:120]}

    return {"ok": True, "source": "this machine", "tool": tool,
            "name": name_for(tool), "prefixes": prefixes,
            "rows": _local(store, prefixes, limit, since),
            "note": "No Supabase key on this machine, so this is only what "
                    "this computer has done."}


def _merge(shared, mine, limit):
    """The shared table, plus what this machine has not pushed yet.

    Keyed on the row id, which is minted once where the action happened, so
    a row that has been pushed appears once rather than twice. Anything of
    ours the shared table does not have is marked `pending`: it is real, it
    is recorded, and nobody else can see it yet. Saying so is the difference
    between "done" and "done and shared", which for a reproducibility record
    is the whole point.
    """
    up = {r.get("id") for r in shared if r.get("id")}
    out = list(shared)
    for r in mine:
        if r.get("id") in up:
            continue
        out.append(dict(r, pending=True))
    out.sort(key=lambda r: extras.moment_key(r.get("at")), reverse=True)
    return out[:limit]


def _local(store, prefixes, limit, since=None):
    """The same shape, from the local log."""
    out = []
    for a in store.list_activity(limit=4000):
        if not matches(a.get("action"), prefixes):
            continue
        sess = a.get("session") or {}
        row = {
            "id": a.get("id"), "at": a.get("at"),
            "action": a.get("action"), "detail": a.get("detail") or {},
            "gid": sess.get("gid"), "session_key": sess.get("key"),
            "view": a.get("view"), "git_user": a.get("user"),
            "machine": a.get("machine") or a.get("shard"),
        }
        # As a moment, not as text. Stamps here come from several
        # machines in several offsets, and comparing two of those as
        # strings has been wrong in eleven places in this codebase.
        #
        # Strictly newer, matching the `at=gt.since` the cloud side sends.
        # `marked_after` is "at or after", so the row the caller already
        # had came back on every poll -- one side inclusive and the other
        # exclusive is how a watermark stops being one.
        if since and (extras.moment_key(row["at"])
                      <= extras.moment_key(since)):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _shape(r):
    """One row, with only the fields the feed shows."""
    return {
        "id": r.get("id"), "at": r.get("at"), "action": r.get("action"),
        "detail": r.get("detail") or {}, "gid": r.get("gid"),
        "session_key": r.get("session_key"), "view": r.get("view"),
        "git_user": r.get("git_user"), "machine": r.get("machine"),
    }
