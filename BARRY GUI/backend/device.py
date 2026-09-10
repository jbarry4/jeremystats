"""
device.py -- what this computer is called, kept away from who is using it.

The lab name for a machine used to live in the profile, next to your name and
your email, and that was wrong in a way that took a while to become visible.
A profile is a person; a name for a computer is a property of the computer.
Putting them in one record meant every path that wrote a profile could write
the machine name, and several did:

  * picking a colleague off the roster filled the form with their details and
    left the machine name in the box, ready to be saved from a context that
    had nothing to do with this computer
  * a Save that fell through the wrong branch set both at once -- measured,
    and it is how one computer came to file errors under five different
    names (Bluebarry, DESKTOP-4H65AI7, StrawBarry, Strawbarrry and
    "Rig 2 (Barry lab)") while two different computers were both set to
    "Strawbarrry"

That name is stamped on every error, action and run, so two machines sharing
one cannot be told apart, and one machine changing its own turns its history
into somebody else's.

So it lives here, on its own, in its own shard. Switching who this machine
credits work to cannot touch it, because the two are not in the same record
any more.

The shard id stays the identity. This is the label -- what people call it --
and `machine_id()` (the hostname slug plus a hash of the MAC) is what
anything comparing machines should use. A label is for reading.
"""
from __future__ import annotations

import os
import platform

from . import shards

MAX_LEN = 120


class Device:
    def __init__(self, logs_dir, store=None):
        self.dir = os.path.join(logs_dir, "prefs")
        self.store = store
        # LWW, and per machine by virtue of being a shard: this is one
        # computer's own name and only it should be writing the record.
        self.book = shards.Book(self.dir, {}, store)

    def _base(self):
        return "device"

    def get(self, profile=None):
        """What to call this computer, and where the answer came from.

        `profile` is accepted so the old value can be adopted once. The name
        used to be a profile field, and a machine that has been set up should
        not have to be told again just because the record moved.
        """
        rec = self.book.read(self._base()) or {}
        name = (rec.get("name") or "").strip()
        source = "set here" if name else None

        # "Never named" and "named, then cleared" are different answers.
        # `at` is written on every save, so its presence means somebody has
        # made a decision here -- and clearing the box has to mean "use the
        # name the computer reports", not "go back to whatever the profile
        # used to say", or the old value can never be got rid of.
        decided = bool(rec.get("at"))
        if not name and not decided and profile is not None:
            try:
                was = (profile.get() or {}).get("device") or ""
                was = was.strip()
            except Exception:                            # noqa: BLE001
                was = ""
            if was:
                name, source = was, "carried over from the profile"

        real = platform.node()
        return {
            "name": name or real,
            # Whether anybody has actually named it, as opposed to falling
            # back. The interface should not claim a hostname is a choice.
            "named": bool(name),
            "source": source or "the computer's own name",
            "real": real,
            "id": shards.machine_id(),
        }

    def save(self, name):
        """Name this computer. Empty means "go back to the hostname"."""
        clean = ("" if name is None else str(name)).strip()[:MAX_LEN]
        rec = self.book.read(self._base()) or {}
        rec["name"] = clean
        rec["at"] = shards._now()
        rec["by"] = ((self.store.provenance() if self.store else {}) or {}) \
            .get("user")
        self.book.write(self._base(), rec)
        return self.get()

    def adopt(self, profile):
        """Move the old profile value into this record, once.

        Called at start-up. Without it, every machine that had been named
        would silently revert to its hostname the first time it ran a build
        with the two records separated -- and since that name is stamped on
        every row, the history would fork.
        """
        rec = self.book.read(self._base()) or {}
        if (rec.get("name") or "").strip():
            return None                      # already has one of its own
        try:
            was = ((profile.get() or {}).get("device") or "").strip()
        except Exception:                                # noqa: BLE001
            return None
        if not was:
            return None
        self.save(was)
        return was
