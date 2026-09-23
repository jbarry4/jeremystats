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
from .eventbank import EventBank

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

# THE ONE FLAG THAT IS NOT IN THE PROPOSAL.
#
# `braces.REASONS` names the reasons the TOOL would not vouch for a row, and
# they are measured once, when the set is made. This one is a fact about the
# REVIEW: two stamps sent to the same time are one event written twice, not
# two events, and the bank will not write it.
#
# It cannot be measured with the others. Nothing can know it until somebody
# has moved something, and it stops being true the moment they move it back
# -- so it is worked out from the calls every time they are read, and it is
# the only way a row that arrived with no flag on it can end up wanting an
# answer. That is also why it is not written into `rows`: a flag stored
# against a decision that has since changed would be a lie the panel shows.
#
# It is not a refusal either. Somebody in the middle of a review will pass
# through this state on the way to a set that is right, and being stopped at
# the moment of making a mistake -- rather than being shown it and left to
# fix it -- is how a tool makes people careful about the wrong thing.
OVERLAP = "overlap"

# Same rounding the bank matches duplicates on, so "these two share a time"
# means one thing across the two. Read from there rather than spelled again:
# a flag that disagreed with the write it is warning about would be worse
# than no flag at all.
OVERLAP_DP = EventBank.DUP_DP


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
def settled(rec):
    """Every row, and the time it would be written at.

    Yields `(n, row, call, kind, t)` in row order -- `n` the row's number,
    `kind` what the review made of it, and `t` where the stamp ends up. `t`
    is None for a row somebody called garbage, which is not written at all.

    ONE PLACE, because `resolve` and `overlaps` have to agree about where a
    stamp lands. A flag that disagreed with the write it is warning about
    would be worse than no flag, and two copies of this walk would disagree
    the first time either was edited.
    """
    calls = rec.get("calls") or {}
    for n, row in enumerate(rec.get("rows") or []):
        said = calls.get(str(n)) or {}
        call = said.get("call")
        was = row.get("was")
        # Where the proposal would put it: its peak, unless the peak is
        # where it already is, or there was no peak to go to.
        prop = (row["now"] if (row.get("now") is not None
                               and not row.get("same")) else was)
        if call == "move":
            yield n, row, call, "moved", said.get("t")
        elif call == "garbage":
            yield n, row, call, "garbage", None
        elif call == "keep":
            yield n, row, call, "kept", was
        elif call == "confirm":
            yield n, row, call, "confirmed", prop
        elif row.get("flag"):
            # Flagged and unresolved: it stays put, and it is still waiting.
            yield n, row, call, "waiting", was
        else:
            yield n, row, call, "auto", prop


def overlaps(rec):
    """Rows that would be written onto a time another row already holds.

    Returns `[{"t": seconds, "rows": [n, ...]}, ...]`, earliest first. Empty
    is the normal answer and the one the panel is built around.

    This is the `OVERLAP` flag: worked out from the calls as they stand,
    named by ROW so the panel can jump to them, and gone the moment one of
    them is moved off. Two stamps on one time is the one thing a review can
    produce that the bank will not write -- see `EventBank.align` -- so it
    is said here, against the rows that caused it, rather than as a refusal
    at the end of an afternoon.
    """
    at = {}
    for n, _row, _call, _kind, t in settled(rec):
        if t is None:
            continue
        try:
            key = round(float(t), OVERLAP_DP)
        except (TypeError, ValueError):
            continue
        at.setdefault(key, []).append(n)
    return [{"t": k, "rows": v} for k, v in sorted(at.items()) if len(v) > 1]


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
    moves, flags = {}, {}
    counts = {"confirmed": 0, "kept": 0, "moved": 0, "waiting": 0,
              "auto": 0, "no_peak": 0, "garbage": 0, "overlap": 0}
    rejects = []
    for n, row, _call, kind, t in settled(rec):
        i = row.get("i")
        why = row.get("flag")
        if why:
            flags[i] = why
        counts[kind] += 1
        if kind == "garbage":
            # Not an event after all. It does not move, it is not written,
            # and it is counted on its own -- lumping it in with "kept"
            # would hide the one decision here that changes what the set
            # contains rather than where something in it sits.
            rejects.append(i)
            continue
        if kind == "waiting" and why == "no_peak":
            counts["no_peak"] += 1
        # A stamp going where it already is is not a move. `align` reads it
        # the same way -- a new time within a nanosecond of the old one
        # records no shift -- so saying it twice only makes the two able to
        # disagree.
        try:
            shifts = abs(float(t) - float(row.get("was"))) > 1e-9
        except (TypeError, ValueError):
            continue
        if kind == "moved" or shifts:
            moves[i] = t
    # Named by row where the panel needs them, counted in stamps here: the
    # counts are what the pills and the bar are drawn from, and "3 stamps
    # share a time with another" is the sentence a person can act on.
    counts["overlap"] = sum(len(g["rows"]) for g in overlaps(rec))
    return moves, flags, counts, rejects
