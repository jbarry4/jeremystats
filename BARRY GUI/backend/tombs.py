"""
tombs.py -- Remembering what was deleted, so a sync does not undo it.

A row that vanishes and a row you have not fetched look identical over a REST
API. So "delete" has to be a thing that is *recorded*, not an absence -- or
every sync helpfully puts it back.

That is not hypothetical. Filing six figures into a folder moved them, wrote
new rows for the new paths, and left the old rows behind with their uploaded
copies still attached. The next sync saw six rows whose files were missing
locally, downloaded them into the old folders, and turned six figures into
twelve. Tidying up made a mess, silently, and the only clue was a number
going the wrong way.

So: anything removed here leaves a note, the note travels, and the other side
marks the row deleted rather than serving it back. Notes are cheap, one file
per machine like everything else, and pruned once the sync has carried them.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

from . import shards

# "person" is here for a reason worth stating: removing somebody from the
# roster has to survive the next sync. Another machine still holding the name
# pushes its copy, the pull writes it back, and a merge or a removal undoes
# itself within seconds -- measured, twice.
KINDS = ("session", "result", "bank", "curation", "layers", "deck", "person")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def when(stamp):
    """A stamp as seconds since the epoch, or None when it cannot say.

    Takes what this codebase writes: `_now()`'s `-0400`, isoformat's
    `-04:00`, the database's `Z`. A stamp with no zone is None, not a guess:
    machines here keep their own clocks and offsets, and a deletion decided
    on a misread hour is the one mistake these notes exist to prevent.
    """
    s = str(stamp or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    m = re.match(r"^(.*\d)([+-]\d\d)(\d\d)$", s)
    if m and ":" not in m.group(2) + m.group(3):
        s = "%s%s:%s" % m.groups()
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.timestamp() if dt.tzinfo is not None else None


def newer(a, b):
    """Stamp `a` is later than stamp `b`. False when either cannot be read:
    no evidence, no deletion."""
    ta, tb = when(a), when(b)
    return ta is not None and tb is not None and ta > tb


class Tombs:
    """What this machine has deleted, and whether the sync has said so yet."""

    def __init__(self, logs_dir, store=None):
        self.dir = os.path.join(logs_dir, "tombstones")
        self.store = store
        self.book = shards.Book(self.dir, {"gone": shards.MAPLWW}, store)
        self.base = "deleted"

    def _rec(self):
        return self.book.read(self.base) or {"schema": 1, "gone": {}}

    def add(self, kind, ident, note=None, at=None, synced=False):
        """Note that something is gone.

        `ident` is whatever the other side keys on: a gid for a session, the
        repo-relative path for a result, the entry id for a bank entry.
        `at` and `synced` are for a deletion that arrived from the cloud: it
        happened when the row says, and the cloud already knows.
        """
        if kind not in KINDS or not ident:
            return None
        rec = self._rec()
        rec.setdefault("gone", {})["%s:%s" % (kind, ident)] = {
            "kind": kind, "id": str(ident), "at": at or _now(),
            "by": shards.machine_id(), "note": note, "synced": bool(synced),
        }
        self.book.write(self.base, rec)
        return rec

    def pending(self, kind=None):
        """Deletions the sync has not carried yet."""
        out = []
        for key, row in (self._rec().get("gone") or {}).items():
            if not isinstance(row, dict) or row.get("synced"):
                continue
            if kind and row.get("kind") != kind:
                continue
            out.append(row)
        return out

    def all(self, kind=None):
        return [r for r in (self._rec().get("gone") or {}).values()
                if isinstance(r, dict) and (not kind or r.get("kind") == kind)]

    def mark_synced(self, rows):
        """Said out loud, so it need not be said again.

        Kept rather than dropped: a machine that has been offline for a month
        will pull the row back otherwise, because the server still has it and
        nothing here remembers refusing it.
        """
        if not rows:
            return 0
        rec = self._rec()
        gone = rec.setdefault("gone", {})
        n = 0
        for row in rows:
            key = "%s:%s" % (row.get("kind"), row.get("id"))
            if key in gone and isinstance(gone[key], dict):
                gone[key]["synced"] = True
                gone[key]["synced_at"] = _now()
                n += 1
        if n:
            self.book.write(self.base, rec)
        return n

    def is_deleted(self, kind, ident):
        return ("%s:%s" % (kind, ident)) in (self._rec().get("gone") or {})

    def outlives(self, kind, ident, made_at):
        """A note says (kind, ident) is gone, written after `made_at`.

        So the thing here is the one that was deleted and has come back -- a
        git merge carrying another machine's copy, or a sync that had not
        heard -- and not a later one that happens to share the name. A
        curation set's id is its recording and kind, so a set started again
        on the same recording after a deletion has the deleted one's id;
        it was made after the note, and the note does not touch it.
        """
        row = (self._rec().get("gone") or {}).get("%s:%s" % (kind, ident))
        return isinstance(row, dict) and newer(row.get("at"), made_at)

    def forget(self, kind, ident):
        """Take a note back -- for something deliberately re-created."""
        rec = self._rec()
        if (rec.get("gone") or {}).pop("%s:%s" % (kind, ident), None):
            self.book.write(self.base, rec)
            return True
        return False
