"""
bracesset.py -- an alignment, kept between running it and accepting it.

Running Braces is fast. Reviewing it is not: a set of twelve hundred stamps
arrives with twenty-odd flags on it, and going through those is an afternoon's
work with the recording open. The application will be restarted under that,
the machine will be used for something else, and a colleague may look at half
of them. So the proposal is written down rather than held in a tab.

WHY THIS IS NOT A `toolresults` RECORD

`toolresults` keys an answer on (recording, parameters) so that asking the
same question twice costs nothing. That is exactly right for Panorama, whose
answer is a measurement. An alignment is a measurement plus a pile of human
decisions, and those are not a function of the parameters -- two people
reviewing the same proposal will resolve its flags differently, and both are
legitimate. So a set is keyed on itself, minted when somebody runs it.

The measurement half could be cached and is not, deliberately: the read is a
single channel at 1 kHz, which is seconds, and a cache that can go stale
against a recording is a liability out of proportion to what it saves.

WHAT IS IN IT

    rows        one per event: where it was, which peak it got, why it was
                flagged. The proposal, and it never changes.
    calls       index -> what a person decided about that row. The review,
                and it is the only part that is written after creation.

Separate on purpose. Re-running the measurement must not silently discard an
afternoon of review, and a review must not be able to rewrite what the
detector measured -- so a re-run mints a new set and says so.

`calls` is `MAPLWW` so that two people reviewing different flags on one
proposal merge row by row. The same row reviewed twice is a real
disagreement, and last-writer-wins settles it and terminates. The entries
stay small -- a verb and maybe a time -- because `Book.write` fingerprints
every value in a MAPLWW field on every write.
"""
from __future__ import annotations

import os
import time
import uuid

from . import shards

SCHEMA = 1

SET_SPEC = {
    "created": shards.FIRST,
    "set_id": shards.FIRST,
    # What was measured, and what it was measured from. Frozen: a set whose
    # rows came from two different channels is not a set.
    "entry_id": shards.FIRST,
    "gid": shards.FIRST,
    "from_version": shards.FIRST,
    "params": shards.FIRST,
    "rows": shards.FIRST,
    # The review. The only field anybody writes after the set exists.
    "calls": shards.MAPLWW,
}

# What a person can decide about one row.
#
#   confirm   take the proposal
#   keep      leave the stamp where it was -- the flag was right to ask
#   move      put it somewhere neither the detector nor the tool chose
#
# A row nobody has touched has no entry at all, which is how "still to do"
# is counted. There is deliberately no "reject": a stamp is never deleted
# here, only left alone.
# `garbage` is the odd one out and deliberately so.
#
# Braces reads labels and does not write them: which candidates are real is
# curation's question, answered a step earlier, and a tool that quietly
# re-decides it would make the curation set stop being the record of what
# anybody decided. But somebody looking at a stamp on the recording, with
# the CSD under it, sometimes sees what they missed -- and making them go
# back to Checkup for one obvious mistake is how obvious mistakes stay in.
#
# So it exists, it asks twice, and it says out loud that it should have
# happened earlier. A stamp marked here is not moved and not written: the
# aligned version holds the spikes, so a rejected one simply is not in it,
# and the version's note says how many went that way.
CALLS = ("confirm", "keep", "move", "garbage")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def new_set_id():
    return "br" + uuid.uuid4().hex[:10]


class BracesSetError(Exception):
    """A refusal the user should read, not a crash."""


class BracesSets:
    def __init__(self, root, store):
        self.dir = os.path.join(root, "braces")
        self.store = store
        os.makedirs(self.dir, exist_ok=True)
        self.book = shards.Book(self.dir, SET_SPEC, store)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def all(self):
        out = []
        for rec in self.book.all():
            if rec and rec.get("set_id"):
                out.append(rec)
        out.sort(key=lambda r: (r.get("created") or {}).get("at") or "",
                 reverse=True)
        return out

    def get(self, set_id):
        for rec in self.all():
            if rec.get("set_id") == set_id:
                return rec
        return None

    def _base(self, rec):
        return shards.safe_base("%s_%s" % (
            (rec.get("gid") or "unfiled")[:40], rec["set_id"]))

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    @shards.atomic
    def create(self, entry_id, gid, from_version, params, rows, summary,
               name=None, by=None):
        """File a proposal. Nothing in it is a decision yet."""
        prov = self.store.provenance() if self.store else {}
        who = (by or prov.get("user") or "unknown").strip()
        rec = {
            "schema": SCHEMA,
            "set_id": new_set_id(),
            "entry_id": entry_id,
            "gid": gid,
            "name": name or "",
            "from_version": from_version,
            "params": dict(params or {}),
            "summary": dict(summary or {}),
            "rows": list(rows or []),
            "calls": {},
            "created": {"by": who, "at": _now(),
                        "machine": prov.get("machine")},
        }
        # `@shards.atomic` already holds the book's lock, and it is an
        # RLock, so `Book.write` re-enters it rather than deadlocking.
        return self.book.write(self._base(rec), rec)

    @shards.atomic
    def decide(self, set_id, calls, by=None):
        """Record what somebody said about one or more rows.

        `calls` is `{row_index: {"call": ..., "t": ...}}`. A row whose call
        is `move` must carry the time it was moved to; the others must not,
        because a confirm that also carried a time would be two facts in one
        field and the second would win silently.
        """
        rec = self.get(set_id)
        if not rec:
            raise BracesSetError("No alignment set %s." % set_id)
        if rec.get("committed"):
            raise BracesSetError(
                "This alignment was already accepted as version %s. Run it "
                "again to propose something different."
                % (rec["committed"] or {}).get("version"))
        prov = self.store.provenance() if self.store else {}
        who = (by or prov.get("user") or "unknown").strip()
        n_rows = len(rec.get("rows") or [])
        fresh = dict(rec.get("calls") or {})
        for key, val in (calls or {}).items():
            try:
                i = int(key)
            except (TypeError, ValueError):
                raise BracesSetError("%r is not a row." % key)
            if i < 0 or i >= n_rows:
                raise BracesSetError(
                    "Row %d is not in this set, which has %d." % (i, n_rows))
            if val is None:
                fresh.pop(str(i), None)
                continue
            call = (val or {}).get("call")
            if call not in CALLS:
                raise BracesSetError(
                    "%r is not something that can be decided about a stamp. "
                    "Use one of: %s" % (call, ", ".join(CALLS)))
            item = {"call": call, "by": who, "at": _now()}
            if call == "move":
                try:
                    item["t"] = round(float(val.get("t")), 6)
                except (TypeError, ValueError):
                    raise BracesSetError(
                        "Moving a stamp needs the time to move it to.")
            fresh[str(i)] = item
        rec["calls"] = fresh
        return self.book.write(self._base(rec), rec)

    @shards.atomic
    def mark_committed(self, set_id, version, version_id, by=None):
        """Say which version this proposal became.

        Written after the bank write, never before: a set marked accepted
        whose version does not exist is a lie the panel would show, whereas
        a version whose set is not marked is merely untidy and is repaired
        by running it again.
        """
        rec = self.get(set_id)
        if not rec:
            raise BracesSetError("No alignment set %s." % set_id)
        prov = self.store.provenance() if self.store else {}
        rec["committed"] = {
            "version": version,
            "version_id": version_id,
            "by": (by or prov.get("user") or "unknown").strip(),
            "at": _now(),
        }
        return self.book.write(self._base(rec), rec)

    @shards.atomic
    def forget(self, set_id):
        """Drop a proposal nobody accepted.

        Only a proposal. A set that became a version is the record of how
        that version was made, and deleting it would leave a version in the
        history that nothing can explain -- so that is refused here rather
        than guarded in the route.
        """
        rec = self.get(set_id)
        if not rec:
            raise BracesSetError("No alignment set %s." % set_id)
        if rec.get("committed"):
            raise BracesSetError(
                "This alignment became version %s, and is the record of how "
                "that version was made. Delete the version instead."
                % (rec["committed"] or {}).get("version"))
        self.book.forget(self._base(rec))
        return {"ok": True, "set_id": set_id}


# --------------------------------------------------------------------------
# Reading a set back
# --------------------------------------------------------------------------
def resolve(rec):
    """What this set would write, given the review so far.

    Returns (moves, flags, counts, rejects) where `moves` is
    `{event_index: new_time}` -- exactly what `EventBank.align` takes --
    and `rejects` is the indices somebody marked as not an event after all.

    THE RULE FOR A FLAG NOBODY RESOLVED: it stays where it was. Not moved
    quietly on the grounds that the proposal was probably right; the flag
    exists because the tool would not vouch for it, and accepting it by
    default would make the flag decorative.

    A row that is NOT flagged is confirmed on arrival, which is what makes
    this usable at twelve hundred events. A person can still flag one by
    hand, and then the same rule applies to it.
    """
    calls = rec.get("calls") or {}
    moves, flags = {}, {}
    counts = {"confirmed": 0, "kept": 0, "moved": 0, "waiting": 0,
              "auto": 0, "no_peak": 0, "garbage": 0}
    rejects = []
    for n, row in enumerate(rec.get("rows") or []):
        i = row.get("i")
        said = calls.get(str(n)) or {}
        call = said.get("call")
        why = row.get("flag")
        if why:
            flags[i] = why
        if call == "move":
            moves[i] = said["t"]
            counts["moved"] += 1
            continue
        if call == "garbage":
            # Not an event after all. It does not move, it is not written,
            # and it is counted on its own -- lumping it in with "kept"
            # would hide the one decision here that changes what the set
            # contains rather than where something in it sits.
            rejects.append(i)
            counts["garbage"] += 1
            continue
        if call == "keep":
            counts["kept"] += 1
            continue
        if call == "confirm":
            if row.get("now") is not None and not row.get("same"):
                moves[i] = row["now"]
            counts["confirmed"] += 1
            continue
        # Nobody has said anything about this one.
        if why:
            # Flagged and unresolved: it stays put, and it is still waiting.
            counts["waiting"] += 1
            if why == "no_peak":
                counts["no_peak"] += 1
            continue
        if row.get("now") is not None and not row.get("same"):
            moves[i] = row["now"]
        counts["auto"] += 1
    return moves, flags, counts, rejects
