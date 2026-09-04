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
import time

from . import shards

KINDS = ("session", "result", "bank", "curation", "layers", "deck")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Tombs:
    """What this machine has deleted, and whether the sync has said so yet."""

    def __init__(self, logs_dir, store=None):
        self.dir = os.path.join(logs_dir, "tombstones")
        self.store = store
        self.book = shards.Book(self.dir, {"gone": shards.MAPLWW}, store)
        self.base = "deleted"

    def _rec(self):
        return self.book.read(self.base) or {"schema": 1, "gone": {}}

    def add(self, kind, ident, note=None):
        """Note that something is gone.

        `ident` is whatever the other side keys on: a gid for a session, the
        repo-relative path for a result, the entry id for a bank entry.
        """
        if kind not in KINDS or not ident:
            return None
        rec = self._rec()
        rec.setdefault("gone", {})["%s:%s" % (kind, ident)] = {
            "kind": kind, "id": str(ident), "at": _now(),
            "by": shards.machine_id(), "note": note, "synced": False,
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

    def forget(self, kind, ident):
        """Take a note back -- for something deliberately re-created."""
        rec = self._rec()
        if (rec.get("gone") or {}).pop("%s:%s" % (kind, ident), None):
            self.book.write(self.base, rec)
            return True
        return False
