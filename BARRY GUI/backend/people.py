"""
people.py -- who has worked on this repo, gathered rather than declared.

There is no sign-up here and there should not be. Every record BARRY writes
already carries who made it: a curation decision has a `by`, a bank entry has
an `added.by`, a profile shard has a name and a machine, the activity log has
a user on every line. So the roster is a reading of what is already written,
not a new thing to maintain -- which means it is never out of date and never
disagrees with the attribution on the data.

Two consequences worth stating:

Names arrive as they were typed. "Rain", "rain@uvm.edu" and
"theexaminedexistence@gmail.com" may all be one person, and this module does
not pretend to know that. It groups by exact name, counts what each one has
touched, and says where it saw them -- enough for somebody to recognise
themselves in a list and pick the row they meant.

Some names are not people. A decision may honestly say "snapshot import":
nobody knows which hand dragged those PNGs. Those are the record of a
provenance, not somebody who can be assigned a session, so they are marked
rather than offered.
"""
from __future__ import annotations

import os
import platform

from . import shards

# Names that record where something came from rather than a person who could
# be asked about it. Kept in one place because curation.py needs the same
# judgement when it picks a default owner.
NOT_PEOPLE = frozenset({
    "snapshot import", "the import", "unknown", "another machine",
    "a detector", "barry", "barry curation",
})


def _clean(name):
    got = ("" if name is None else str(name)).strip()
    return got[:200] or None


def _looks_like_a_person(name):
    return bool(name) and name.strip().lower() not in NOT_PEOPLE


class People:
    """The roster, compiled on demand from everything else."""

    def __init__(self, logs_dir, store=None, profile=None):
        self.logs = logs_dir
        self.store = store
        self.profile = profile
        # Extra names somebody has typed that no record carries yet -- a new
        # student who has not curated anything is still somebody you want to
        # assign a session to. One shard per machine, like everything else.
        self.book = shards.Book(os.path.join(logs_dir, "prefs"),
                                {"added": shards.BYID}, store)

    # ------------------------------------------------------------------
    def _extra(self):
        rec = self.book.read("people") or {}
        return [r for r in (rec.get("added") or []) if r.get("id")]

    def add(self, name, email=None, note=None):
        """Put somebody on the roster before they have touched anything."""
        name = _clean(name)
        if not name:
            raise ValueError("A person needs a name.")
        rec = self.book.read("people") or {}
        rows = [r for r in (rec.get("added") or [])
                if (r.get("id") or "").lower() != name.lower()]
        rows.append({
            "id": name,
            "name": name,
            "email": _clean(email),
            "note": _clean(note),
            "at": shards._now(),
            "by": (self.store.provenance() if self.store else {}).get("user"),
        })
        rec["added"] = rows
        self.book.write("people", rec)
        return self.roster()

    def forget(self, name):
        """Take a hand-added name off. A name the data carries cannot go:
        it is on the records whether the roster lists it or not."""
        name = _clean(name)
        rec = self.book.read("people") or {}
        rows = [r for r in (rec.get("added") or [])
                if (r.get("id") or "").lower() != (name or "").lower()]
        if len(rows) == len(rec.get("added") or []):
            return False
        rec["added"] = rows
        self.book.write("people", rec)
        return True

    # ------------------------------------------------------------------
    def roster(self, curation=None, bank=None):
        """Everyone, with what they have touched and where they were seen.

        Sorted so the person at this keyboard is first and the people with
        the most work behind them come next -- a picker whose first entry is
        usually the right one saves the typing it exists to save.
        """
        seen = {}

        def note(name, where, n=1, email=None, machine=None):
            name = _clean(name)
            if not name:
                return
            row = seen.setdefault(name, {
                "name": name, "email": None, "machines": [],
                "counts": {}, "total": 0, "is_person": _looks_like_a_person(name),
                "sources": [],
            })
            row["counts"][where] = row["counts"].get(where, 0) + n
            row["total"] += n
            if where not in row["sources"]:
                row["sources"].append(where)
            if email and not row["email"]:
                row["email"] = _clean(email)
            if machine and machine not in row["machines"]:
                row["machines"].append(machine)

        # The profiles, across every machine's shard -- this is the only
        # place somebody has actually said what their name is.
        prof = shards.Book(os.path.join(self.logs, "prefs"), {}, None)
        for base in prof.bases():
            if base != "profile":
                continue
            for machine, path in prof.shard_files(base):
                rec = shards._read_json(path) or {}
                nm = _clean(rec.get("name")) or _clean(rec.get("email"))
                if nm:
                    note(nm, "profile", 1, email=rec.get("email"),
                         machine=_clean(rec.get("device")) or machine)

        # Curation: who decided, and who a set is assigned to.
        for rec in (curation.all() if curation else []):
            who = _clean(rec.get("assignee"))
            if who:
                note(who, "assigned", 1)
            per = {}
            for ev in rec.get("events") or []:
                nm = _clean(ev.get("by"))
                if nm:
                    per[nm] = per.get(nm, 0) + 1
                for r in (ev.get("reviews") or []):
                    rn = _clean(r.get("by"))
                    if rn and rn != nm:
                        per[rn] = per.get(rn, 0) + 1
            for nm, n in per.items():
                note(nm, "decisions", n)

        # The bank: who filed an entry, and who banked each version.
        for rec in (bank.summaries() if bank else []):
            note((rec.get("added") or {}).get("by"), "bank entries", 1,
                 machine=(rec.get("added") or {}).get("machine"))
            for v in rec.get("versions") or []:
                note(v.get("by"), "banked versions", 1,
                     machine=v.get("machine"))

        # Hand-added names.
        for row in self._extra():
            note(row.get("name"), "added by hand", 1, email=row.get("email"))

        me = (self.store.provenance() if self.store else {}).get("user")
        me = _clean(me)
        if me:
            note(me, "this machine", 1,
                 machine=_clean(platform.node()))

        rows = list(seen.values())
        for r in rows:
            r["me"] = bool(me and r["name"] == me)
        rows.sort(key=lambda r: (not r["me"], not r["is_person"],
                                 -r["total"], r["name"].lower()))
        return {
            "people": [r for r in rows if r["is_person"]],
            # Reported, not offered. A name like "snapshot import" is on the
            # records and hiding it would make the roster disagree with the
            # data; offering it as an owner would give a session nobody.
            "not_people": [r for r in rows if not r["is_person"]],
            "me": me,
        }
