"""
profile.py -- who you are, said once.

Everything BARRY writes down carries who did it: a curation decision, a
banked event set, a layer sheet, an exported figure, a run. Until now that
name came from `git config user.name`, falling back to the Windows account.
Both are wrong often enough to matter:

  * a shared rig logs in as "BarryLab" and every decision on it is
    attributed to a computer
  * a git identity is an email address for commits, which is not what you
    want printed under a figure
  * two people using the same machine are indistinguishable
  * the machine name is whatever IT called it, not what the lab calls it

So there is a profile: your name, your email, and what to call this machine.
It is filled in once and then everything is tagged from it. `provenance()`
prefers it and falls back to the old behaviour, so nothing breaks on a
machine that has not set one.

Stored per machine, as a shard, for the same reason as everything else here:
two people on two computers must never write the same file. It IS committed
-- attribution should travel with the data, and there is nothing secret in
a name and a lab email.
"""
from __future__ import annotations

import os
import platform

from . import shards

FIELDS = ("name", "email", "device", "role", "initials", "orcid", "note")

# Bounded so a paste accident cannot write a novel into every record.
MAX_LEN = 200


class Profile:
    def __init__(self, logs_dir, store=None):
        self.dir = os.path.join(logs_dir, "prefs")
        self.store = store
        # LWW on every field: it is one person editing their own row, and
        # the last thing they typed is what they meant.
        self.book = shards.Book(self.dir, {}, store)

    def _base(self):
        return "profile"

    def get(self):
        rec = self.book.read(self._base()) or {}
        out = {k: (rec.get(k) or "") for k in FIELDS}
        out["machine"] = platform.node()
        out["shard"] = shards.machine_id()
        # What would actually be used for attribution right now, so the UI
        # can show the consequence rather than just the form.
        out["effective"] = self.effective(rec)
        out["set"] = bool(out["name"] or out["email"])
        return out

    def effective(self, rec=None):
        """The name and machine that will be stamped on new records."""
        rec = rec if rec is not None else (self.book.read(self._base()) or {})
        name = (rec.get("name") or "").strip()
        email = (rec.get("email") or "").strip()
        device = (rec.get("device") or "").strip()
        return {
            "user": name or email or None,
            "email": email or None,
            "device": device or platform.node(),
        }

    def save(self, patch):
        clean = {}
        for k in FIELDS:
            if k in (patch or {}):
                v = patch[k]
                clean[k] = ("" if v is None else str(v)).strip()[:MAX_LEN]
        if not clean:
            raise ValueError("Nothing to save.")
        rec = self.book.read(self._base()) or {}
        rec.update(clean)
        self.book.write(self._base(), rec)
        return self.get()
