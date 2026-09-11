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


def _cloud_query(prefixes, since=None, limit=LIMIT):
    """PostgREST's filter for "any of these prefixes", newest first.

    `or=(...)` with `like` per prefix. The alternative -- fetching
    everything and filtering here -- is a table scan across every machine's
    history to show twenty rows.
    """
    parts = ["action.like.%s*" % p.replace(",", "") for p in prefixes]
    q = "or=(%s)" % ",".join(parts)
    if since:
        q += "&at=gt.%s" % since
    return q + "&order=at.desc&limit=%d" % int(limit)


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

    if cloud is not None and getattr(cloud, "configured", False):
        try:
            rows = cloud.select("activity",
                                query=_cloud_query(prefixes, since, limit),
                                limit=limit)
            return {"ok": True, "source": "supabase", "tool": tool,
                    "name": name_for(tool), "prefixes": prefixes,
                    "rows": [_shape(r) for r in rows]}
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
        if since and not extras.marked_after(since, row["at"]):
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
