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


def rows_detail(people):
    """Every stored detail row: hand-edited first, then the profiles."""
    out = []
    for r in people._extra():
        out.append(dict(r, name=r.get("name")))
    prof = shards.Book(os.path.join(people.logs, "prefs"), {}, None)
    for machine, path in prof.shard_files("profile"):
        got = shards._read_json(path) or {}
        nm = _clean(got.get("name")) or _clean(got.get("email"))
        if nm:
            out.append(dict(got, name=nm))
    return out


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

    # What may be said about a person. `name` is the key every other record
    # uses, so it is not in here -- renaming somebody would orphan their
    # decisions rather than move them.
    # `aliases` is how a merge stays readable. A six-month-old caption
    # crediting an email address should still be traceable to the person
    # credited by name now, and the surviving entry is the only place
    # that can be written down.
    FIELDS = ("email", "role", "initials", "orcid", "note", "aliases",
              "archived")

    # Fields that are not text. `_clean` would turn False into the string
    # "False", which is truthy, so an unarchive would archive.
    FLAGS = ("archived",)

    def add(self, name, email=None, note=None, **extra):
        """Put somebody on the roster, or edit what it says about them.

        The same call for both: a roster is a small set of facts about a
        person, and "add" and "edit" differ only in whether a row was there
        already. Anything not passed is left as it was, so editing one field
        does not blank the rest.
        """
        name = _clean(name)
        if not name:
            raise ValueError("A person needs a name.")
        rec = self.book.read("people") or {}
        was = None
        rows = []
        for r in (rec.get("added") or []):
            if (r.get("id") or "").lower() == name.lower():
                was = r
            else:
                rows.append(r)

        row = dict(was or {})
        row["id"] = name
        row["name"] = name
        given = dict(extra)
        if email is not None:
            given["email"] = email
        if note is not None:
            given["note"] = note
        for k in self.FIELDS:
            if k in given and given[k] is not None:
                # A list stays a list, a flag stays a bool. `_clean` is for
                # the text fields: over `aliases` it would join them into one
                # string, and over `False` it would produce "False", which is
                # truthy -- so unarchiving would archive.
                if k in self.FLAGS:
                    row[k] = bool(given[k])
                elif isinstance(given[k], (list, tuple)):
                    row[k] = list(given[k])
                else:
                    row[k] = _clean(given[k])
        row.setdefault("at", shards._now())
        row["edited_at"] = shards._now()
        row["by"] = (self.store.provenance() if self.store else {}).get("user")
        rows.append(row)
        rec["added"] = rows
        self.book.write("people", rec)
        return self.roster()

    def details(self, name):
        """What the roster holds about one person, editable fields only."""
        name = _clean(name)
        for r in self._extra():
            if (r.get("id") or "").lower() == (name or "").lower():
                out = {k: r.get(k) or "" for k in self.FIELDS}
                out["name"] = r.get("name")
                out["edited_at"] = r.get("edited_at")
                return out
        # Not hand-edited, but the profiles may still know something.
        prof = shards.Book(os.path.join(self.logs, "prefs"), {}, None)
        for machine, path in prof.shard_files("profile"):
            got = shards._read_json(path) or {}
            nm = _clean(got.get("name")) or _clean(got.get("email"))
            if nm and nm.lower() == (name or "").lower():
                out = {k: got.get(k) or "" for k in self.FIELDS}
                out["name"] = nm
                out["from_profile"] = machine
                return out
        return {"name": name, **{k: "" for k in self.FIELDS}}

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

    def archive(self, name, yes=True):
        """Take somebody off the pickers without taking them off the record.

        Works on a name the data carries, and that is the whole point:
        `forget` refuses those, correctly, so somebody who has left the lab
        had nowhere to go and kept being offered as an owner for new work.

        A person who has never been added by hand has no row here at all --
        the roster compiled them from their decisions -- so one is created to
        hold the flag. That row says nothing except "archived"; it does not
        claim to be the source of the name.
        """
        name = _clean(name)
        if not name:
            raise ValueError("A person needs a name.")
        rec = self.book.read("people") or {}
        rows, found = [], False
        for r in (rec.get("added") or []):
            if (r.get("id") or "").lower() == name.lower():
                found = True
                r = dict(r)
                r["archived"] = bool(yes)
                r["edited_at"] = shards._now()
            rows.append(r)
        if not found:
            rows.append({
                "id": name, "name": name, "archived": bool(yes),
                "at": shards._now(), "edited_at": shards._now(),
                "by": (self.store.provenance() if self.store else {})
                .get("user"),
            })
        rec["added"] = rows
        self.book.write("people", rec)
        return True

    def archived(self):
        """The names flagged archived, lower-cased for lookup."""
        out = set()
        for r in self._extra():
            if r.get("archived"):
                nm = _clean(r.get("name") or r.get("id"))
                if nm:
                    out.add(nm.lower())
        return out

    # ------------------------------------------------------------------
    def roster(self, curation=None, bank=None):
        """Everyone, with what they have touched and where they were seen.

        Sorted so the person at this keyboard is first and the people with
        the most work behind them come next -- a picker whose first entry is
        usually the right one saves the typing it exists to save.
        """
        seen = {}

        # Alias -> the surviving name, from the `aliases` written on each
        # roster entry.
        #
        # Resolved HERE rather than by rewriting the records, and that is
        # the important part. `added.by` on a bank entry is declared
        # shards.FIRST -- whoever recorded it first stays authoritative, on
        # purpose, so that nobody editing a description can quietly change
        # who added the events. The activity log is append-only for the same
        # reason. Both of those are right, and both mean a name in a record
        # is what the machine believed at the time.
        #
        # So the record keeps what it said and the roster does the folding.
        # Which is also reversible: remove an alias and the two names come
        # apart again, with nothing lost.
        alias_of = {}
        for row in ((self.book.read("people") or {}).get("added") or []):
            keep = _clean(row.get("name") or row.get("id"))
            for other in (row.get("aliases") or []):
                other = _clean(other)
                if other and keep:
                    alias_of[other.lower()] = keep

        def note(name, where, n=1, email=None, machine=None):
            name = _clean(name)
            if not name:
                return
            name = alias_of.get(name.lower(), name)
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

        # Hand-added and hand-edited names.
        for row in self._extra():
            note(row.get("name"), "added by hand", 1, email=row.get("email"))

        # Everything the roster or a profile says about each of them, so the
        # picker can show a role and the editor can open populated.
        for r in rows_detail(self):
            hit = seen.get(r["name"])
            if hit is not None:
                for k in ("email", "role", "initials", "orcid", "note"):
                    if r.get(k) and not hit.get(k):
                        hit[k] = r[k]

        me = (self.store.provenance() if self.store else {}).get("user")
        me = _clean(me)
        if me:
            note(me, "this machine", 1,
                 machine=_clean(platform.node()))

        rows = list(seen.values())
        # Which spellings were folded into each surviving name. The map was
        # built above and then discarded, so the rows said nothing about it
        # -- which made the sync unable to share a merge, and made a roster
        # where a name somebody remembers has quietly disappeared.
        folded = {}
        for other, keep in alias_of.items():
            folded.setdefault(keep, []).append(other)
        # Archived names stay in the list, with the flag on them, and every
        # count stays exactly as it was. Archiving is a statement about who
        # should be OFFERED work, not about who did it -- so it is the
        # caller's business to leave them out of a picker, and nobody's
        # business to make the totals disagree with the records.
        put_away = self.archived()
        for r in rows:
            r["me"] = bool(me and r["name"] == me)
            got = sorted(folded.get(r["name"]) or [])
            if got:
                r["aliases"] = got
            if r["name"].lower() in put_away:
                r["archived"] = True
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
