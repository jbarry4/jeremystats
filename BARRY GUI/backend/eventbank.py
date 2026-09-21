"""
eventbank.py -- the shared record of detected events.

A detector's output normally lives as an `ets.mat` beside the recording, on
whichever drive it was run on, named after whoever was running it. Six months
later nobody can say which version of which script produced it, or find it
from a different machine. The bank is the answer to that: one entry per set of
events, filed by project / mouse / session / type, and it will not accept an
entry that cannot say who added it, when, and what produced it.

One JSON file per entry, so git merges two people's banking without conflict --
the same reason the run log is shaped that way.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import threading
import time
import uuid

from . import shards, versions as versionsmod
from datetime import datetime, timezone

SCHEMA = 1
_LOCK = threading.Lock()

# The kinds of thing worth telling apart when you come back to them. Free text
# is still accepted -- this is the menu, not the whitelist.
EVENT_TYPES = [
    {"id": "ied", "name": "IED", "note": "interictal epileptiform discharge"},
    {"id": "seizure", "name": "Seizure", "note": "electrographic seizure"},
    {"id": "spike", "name": "Spike", "note": "threshold-crossing unit or spike"},
    {"id": "ripple", "name": "Ripple", "note": "sharp-wave ripple"},
    {"id": "ds", "name": "Dentate spike", "note": ""},
    {"id": "artifact", "name": "Artifact", "note": "to be excluded"},
    {"id": "ttl", "name": "TTL", "note": "hardware event marker"},
    {"id": "behavior", "name": "Behavior", "note": "scored from video"},
    {"id": "other", "name": "Other", "note": ""},
]


def snap_sha(snap):
    """A digest of a snapshot that two machines can agree on.

    Canonicalised first: a time is rounded to the microsecond and a label is
    text, so 315.275 and 315.27500000000003 -- the same event written by two
    different float paths -- do not read as two different snapshots. The
    digest is what makes "both copies agree" a check instead of an
    assumption, and what catches a half-transferred one before somebody
    restores from it.
    """
    rows = []
    for pair in (snap or []):
        try:
            t = round(float(pair[0]), 6)
        except (TypeError, ValueError, IndexError):
            continue
        lab = pair[1] if isinstance(pair, (list, tuple)) and len(pair) > 1 \
            else None
        rows.append([t, None if lab is None else str(lab)])
    blob = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class BankError(Exception):
    """A refusal the user should read, not a crash."""


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _slug(text, fallback="x"):
    out = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-").lower()
    return out[:40] or fallback


def _source_for(entry, prior, pipeline):
    """Where the times came from, which is never the curation that read
    them.

    In order: what the adopted import said, then what this entry already
    said, and only if neither exists is a source built from the caller's
    `pipeline`. An entry acquires a source once and keeps it.
    """
    came = entry.get("import_from") or {}
    for got in (came.get("source"),
                (prior or {}).get("source")):
        if got:
            return got
    return {
        "pipeline": pipeline,
        "run_id": entry.get("run_id"),
        "file": entry.get("source_file"),
        "parameters": entry.get("parameters") or {},
        "detector": entry.get("detector"),
    }


class EventBank:
    def __init__(self, root, store):
        self.root = os.path.join(root, "event_bank")
        self.store = store
        os.makedirs(self.root, exist_ok=True)
        # An entry is imported by one machine but curated by another, and
        # "specified" is written back onto it -- so it is edited by more than
        # one person and has to be sharded like everything else.
        self.book = shards.Book(self.root, {
            "events": shards.LWW,
            "added": shards.FIRST,
            "history": shards.BYID,
            # Per version, not whole-list. Two machines banking the same
            # entry is the normal case -- one person curates on the rig,
            # another spot-checks on the desktop -- and under last-write-
            # wins one machine's entire version history simply vanished.
            # Each version carries an `id` so BYID can key on it.
            "versions": shards.BYID,
        }, store)
        self.book.absorb_legacy()
        self._drop_cache()

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def _drop_cache(self):
        """Forget everything read from disk. Called by every write.

        One method rather than a line per write site, because there are eight
        of them and `summaries` and the id index are derived from `all` -- so
        a write that dropped only `_cache` would leave the other two holding
        the previous answer. They are also fingerprint-checked, but a
        fingerprint is (count, newest mtime, total mtime) and mtime is only
        good to the second on some filesystems: two writes inside one tick
        are indistinguishable. Dropping them outright is the part that does
        not depend on the clock.
        """
        self._cache = None
        self._stamp = None
        self._summaries = None
        self._sum_stamp = None
        self._by_id = None
        self._id_stamp = None
        self._fp = None
        self._fp_at = 0.0

    # How long a fingerprint is trusted without re-taking it. This only
    # governs how fast a change made *outside this process* is noticed -- a
    # git pull, or the sync applying a colleague's entry. Our own writes call
    # _drop_cache and are seen immediately regardless.
    FINGERPRINT_TTL = 0.25

    def _fingerprint(self):
        """Changes when any entry does, so a colleague's pull is picked up.

        Memoised for a quarter of a second, because taking it means a stat of
        every shard in the bank and the three readers that check it -- all(),
        summaries() and get() -- are usually called within one request. Forty
        get() calls in a loop meant forty sweeps of a hundred and fifty files
        to answer forty dictionary lookups.
        """
        now = time.time()
        if self._fp is not None and now - self._fp_at < self.FINGERPRINT_TTL:
            return self._fp
        count = newest = total = 0
        try:
            with os.scandir(self.root) as it:
                for e in it:
                    if not e.name.endswith(".json"):
                        continue
                    try:
                        mt = e.stat().st_mtime_ns
                    except OSError:
                        continue
                    count += 1
                    total += mt
                    newest = max(newest, mt)
        except OSError:
            pass
        self._fp = (count, newest, total)
        self._fp_at = now
        return self._fp

    def all(self):
        stamp = self._fingerprint()
        if self._cache is not None and stamp == self._stamp:
            return self._cache
        out = []
        for rec in self.book.all():
            # The event list can be long; the index carries a summary and
            # the detail view fetches the whole entry by id.
            rec.setdefault("n", len(rec.get("events") or []))
            out.append(rec)
        out.sort(key=lambda r: (r.get("added") or {}).get("at") or "", reverse=True)
        self._cache = out
        self._stamp = stamp
        return out

    def summaries(self):
        """Every entry without its event list, for browsing.

        And without the per-version snapshots. Each is a line per candidate,
        so a set of four hundred costs about ten kilobytes a version -- fine
        on one entry, and several megabytes across a bank once everything
        has a history. The listing does not need them; opening an entry
        fetches the whole record, which does.

        Cached on the same fingerprint as `all()`, because it was rebuilding
        every record on every call and `/api/bank` asks for it twice: once
        directly and once inside `tree()`. So a hundred and fifty entries,
        each with its version history, were stripped and rebuilt twice per
        request -- and every write drops the cache, which is why the request
        right after a delete was the slow one.
        """
        stamp = self._fingerprint()
        if self._summaries is not None and stamp == self._sum_stamp:
            return self._summaries
        out = []
        for rec in self.all():
            row = {k: v for k, v in rec.items() if k != "events"}
            if row.get("versions"):
                # The name each version is known by, worked out from what
                # each was based on. Computed here rather than stored: a
                # name depends on the whole history, and a stored one
                # would go stale the moment a branch arrived from another
                # machine.
                # Per ROW, not per version number: this bank really does
                # hold entries whose numbers repeat, where two machines
                # minted the same one and the union rightly kept both.
                # Keyed on the number, two versions would share a name.
                row["versions"] = [
                    dict({k: v for k, v in ver.items() if k != "snap"},
                         label=nm, has_snap=bool(ver.get("snap")))
                    for ver, nm in versionsmod.label_rows(row["versions"])]
            out.append(row)
        self._summaries = out
        self._sum_stamp = stamp
        return out

    def get(self, entry_id):
        """One entry by id.

        Through an index rather than a scan of the whole bank: this is called
        once per id inside loops that walk a selection, so the linear version
        made those quadratic.
        """
        stamp = self._fingerprint()
        if self._by_id is None or stamp != self._id_stamp:
            self._by_id = {r.get("id"): r for r in self.all() if r.get("id")}
            self._id_stamp = stamp
        return self._by_id.get(entry_id)

    def tree(self):
        """Grouped project -> mouse -> session, which is how people look."""
        groups = {}
        for rec in self.summaries():
            proj = rec.get("project") or "Unfiled"
            mouse = rec.get("mouse")
            mkey = "m%s" % mouse if mouse is not None else "unknown mouse"
            skey = rec.get("session")
            skey = "s%s" % skey if skey is not None else "unknown session"

            g = groups.setdefault(proj, {"project": proj, "n": 0, "mice": {}})
            m = g["mice"].setdefault(mkey, {"mouse": mkey, "n": 0, "sessions": {}})
            sess = m["sessions"].setdefault(
                skey, {"session": skey, "label": rec.get("session_label"),
                       "entries": []})
            sess["entries"].append(rec)
            g["n"] += 1
            m["n"] += 1

        # Sort numerically where the names are numeric, so m2 precedes m10.
        def num(key):
            m = re.search(r"(\d+)", str(key))
            return int(m.group(1)) if m else 10 ** 9

        out = []
        for proj in sorted(groups, key=lambda k: (k == "Unfiled", k.lower())):
            g = groups[proj]
            mice = []
            for mk in sorted(g["mice"], key=num):
                m = g["mice"][mk]
                m["sessions"] = [m["sessions"][sk]
                                 for sk in sorted(m["sessions"], key=num)]
                mice.append(m)
            g["mice"] = mice
            out.append(g)
        return out

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    @shards.atomic
    def add(self, entry):
        """File a set of events. Refuses anything it could not explain later.

        The three required facts are who, when and what produced it. `when` we
        can supply; the other two have to come from the caller, because
        guessing them is exactly how an entry becomes unusable evidence.
        """
        events = entry.get("events") or []
        if not events:
            raise BankError("There are no events to bank.")

        pipeline = (entry.get("pipeline") or "").strip()
        if not pipeline:
            raise BankError(
                "Say what produced these events -- the script, the detector or "
                "the file they came from. An entry that cannot say where it "
                "came from is not worth keeping.")

        prov = self.store.provenance() if self.store else {}
        who = (entry.get("added_by") or prov.get("user") or "").strip()
        if not who:
            raise BankError("Say who is adding these events.")

        # Writing over an entry that already exists, rather than beside it.
        # The id decides the filename, so passing one back replaces that
        # entry in place and everything pointing at it keeps pointing at it.
        prior = self.get(entry["id"]) if entry.get("id") else None

        etype = (entry.get("type") or "").strip() or "other"
        clean = []
        for ev in events:
            try:
                start = float(ev.get("start"))
            except (TypeError, ValueError):
                continue
            item = {"start": round(start, 6)}
            end = ev.get("end")
            if end is not None:
                try:
                    end = float(end)
                    if end > start:
                        item["end"] = round(end, 6)
                except (TypeError, ValueError):
                    pass
            # `label_id` as well as `label`. The display name is what
            # makes an entry readable on its own; the id is what a
            # curation set can actually be rebuilt from. Dropping the id
            # here is half of why a banked set came back undecided --
            # there was nothing left for the set to match on but the
            # name, and the set only spoke ids.
            for key in ("channel", "amplitude", "label", "label_id"):
                if ev.get(key) is not None:
                    item[key] = ev[key]
            # Where this stamp was before Braces moved it, and why it was
            # asked about. Whitelisted explicitly, because the whitelist is
            # what an event IS here -- and a `from_t` dropped on the way in
            # is the diff losing the one thing that lets it tell a stamp
            # that moved from a stamp that was deleted. Coerced and rounded
            # like `start`, since it is the same kind of thing.
            src = ev.get("from_t")
            if src is not None:
                try:
                    src = round(float(src), 6)
                    # A stamp that came back to where it started did not
                    # move, and carrying a from_t equal to start would make
                    # the history claim a shift that cancelled out.
                    if abs(src - item["start"]) > 1e-9:
                        item["from_t"] = src
                except (TypeError, ValueError):
                    pass
            if ev.get("align_flag"):
                item["align_flag"] = ev["align_flag"]
            clean.append(item)
        if not clean:
            raise BankError("None of those events had a usable time.")
        clean.sort(key=lambda e: e["start"])

        # A detector that knows what clock it produced may say so, and the
        # stamp travels with the entry. Belt and braces beside
        # `retime.basis_of`, which can already work it out from the
        # pipeline: a fact recorded on the thing itself survives a rename
        # of the pipeline that produced it.
        basis = entry.get("time_basis")

        rec = {
            "id": entry.get("id") or uuid.uuid4().hex[:12],
            "schema": SCHEMA,
            "project": (entry.get("project") or "").strip() or "Unfiled",
            "mouse": entry.get("mouse"),
            "session": entry.get("session"),
            "session_key": entry.get("session_key"),
            "session_loose_key": entry.get("session_loose_key"),
            "session_label": entry.get("session_label"),
            "session_path": entry.get("session_path"),
            "recording_start": entry.get("recording_start"),
            "duration_s": entry.get("duration_s"),
            "type": etype,
            "type_name": entry.get("type_name") or etype,
            "name": (entry.get("name") or "").strip() or (etype + " events"),
            "note": (entry.get("note") or "").strip(),
            "units": "seconds relative to the start of the recording",
            "n": len(clean),
            "events": clean,
            # The detector that produced the times stays the source.
            # Curation said what they are; it did not find them, and
            # overwriting this with "Jarvis curation" would lose the only
            # record of where the candidates came from.
            #
            # Written out rather than folded into one expression: a
            # conditional binds looser than `or`, so
            # `(A or B) if C else None or D` meant that with no
            # `import_from` -- which is every bank after the first,
            # because the import is folded in and gone by then -- the
            # whole thing fell through to D and rewrote the detector out
            # of the record. The one curated entry in the bank had
            # already lost "ETS dentate-spike export" this way.
            "source": _source_for(entry, prior, pipeline),
            # Who first filed this, not who last touched it -- an entry that
            # forgets where it came from every time it is refreshed is not
            # provenance. The refreshes go in `history` below.
            "added": (prior.get("added") if prior else None) or {
                "by": who,
                "at": _now(),
                "machine": entry.get("machine") or platform.node(),
            },
            # Whether anyone has said what these events ARE.
            #
            # A detector's output and a curated set are both lists of times,
            # and treating them the same is how a guess ends up in a figure as
            # a finding. An import is unspecified until somebody has gone
            # through it; curation writes back entries that carry a label and
            # are specified from the moment they are created.
            "specified": bool(entry.get("curated")),
            "curation_label": entry.get("curation_label"),
            "gid": entry.get("gid"),
        }

        # Versions. Each bank of the same entry is a numbered version
        # holding what was in it and a note, so "how has the labelling
        # shifted" is answerable from the record rather than from memory.
        counts = entry.get("by_label")
        if counts is None:
            counts = {}
            for ev in clean:
                key = ev.get("label") or "unspecified"
                counts[key] = counts.get(key, 0) + 1
        rec["by_label"] = counts
        # Carried so the history can be read without the curation set --
        # a bank entry has to make sense on its own.
        rec["label_names"] = (entry.get("label_names")
                              or (prior.get("label_names") if prior else None)
                              or {})
        versions = list((prior.get("versions") if prior else None) or [])

        # Where the lineage starts: the detector's export, before anyone
        # had looked at any of it. Numbered zero, because it is the thing
        # curation was done *to* rather than a round of curation -- and
        # because numbering it one would push every real version up by one
        # on an entry that already has a history.
        came_from = entry.get("import_from")
        if came_from and not any(v.get("imported") for v in versions):
            was = came_from.get("added") or {}
            n0 = came_from.get("n") or len(came_from.get("events") or [])
            v0 = {
                "v": 0,
                "id": "v0-" + str(came_from.get("id") or uuid.uuid4().hex[:8]),
                "at": was.get("at") or _now(),
                "by": was.get("by") or "unknown",
                "note": "Imported from "
                        + ((came_from.get("source") or {}).get("pipeline")
                           or "a detector")
                        + ". " + str(n0) + " candidates, none decided yet.",
                "n": n0,
                "by_label": {"unspecified": n0},
                "changed": 0, "gained": 0, "lost": 0, "moves": {},
                "machine": was.get("machine"),
                "imported": True,
                "from_entry": came_from.get("id"),
            }
            # The import's own times, so folding it in is not a deletion.
            # Banking a half-curated set writes only the decided ones,
            # and the import entry is then removed as "now version 0" --
            # so without this the candidates nobody had reached yet
            # existed nowhere afterwards, and the position join the
            # snapshot import depends on had nothing left to join to.
            src_events = came_from.get("events") or []
            if src_events and len(src_events) <= self.SNAP_MAX_EVENTS:
                v0["snap"] = [[ev.get("start"),
                               ev.get("label_id") or ev.get("label")]
                              for ev in src_events]
            versions.insert(0, v0)
        # What actually moved, candidate by candidate.
        #
        # The counts alone cannot see it: two calls going one way and two
        # coming back leaves every total identical, and the history then
        # reads "nothing moved" about a pass in which four decisions
        # changed. So the comparison is per candidate, matched on time, and
        # what it reports is which category each one came from and went to.
        #
        # MATCHED ON TIME, WHICH BRACES CHANGES ON PURPOSE.
        #
        # Time was the only identity a banked event had, and that held until
        # something moved one. `braces` does exactly that, so a stamp it
        # shifted would arrive here as one event vanishing and an unrelated
        # one appearing -- a history reading "1198 lost, 1198 gained" about a
        # pass in which nothing was decided differently at all.
        #
        # So an event Braces moved carries `from_t`: the time it used to
        # have. Matched in TWO PASSES rather than one, and the order is not a
        # style choice: every event that is still where it was claims its own
        # slot first, and only the leftovers are matched on where they came
        # from. One pass, whichever key it preferred, could hand a moved
        # event the slot belonging to an event that had not moved at all.
        moves, changed, gained, lost, shifted = {}, 0, 0, 0, 0
        if prior:
            was = {}
            for ev in prior.get("events") or []:
                try:
                    was[round(float(ev["start"]), 4)] = ev.get("label")
                except (TypeError, ValueError, KeyError):
                    continue

            def _pair(before, after):
                if before != after:
                    step = "%s → %s" % (before or "undecided",
                                        after or "undecided")
                    moves[step] = moves.get(step, 0) + 1
                    return 1
                return 0

            left = []
            for ev in clean:
                try:
                    key = round(float(ev["start"]), 4)
                except (TypeError, ValueError):
                    continue
                if key in was:
                    changed += _pair(was.pop(key), ev.get("label"))
                else:
                    left.append(ev)
            # Second pass: what did this used to be?
            for ev in left:
                src = ev.get("from_t")
                key = None
                if src is not None:
                    try:
                        key = round(float(src), 4)
                    except (TypeError, ValueError):
                        key = None
                if key is None or key not in was:
                    gained += 1
                    continue
                shifted += 1
                changed += _pair(was.pop(key), ev.get("label"))
            lost = len(was)

        moved = ((not prior) or changed or gained or lost or shifted
                 or prior.get("n") != rec["n"]
                 or (prior.get("by_label") or {}) != counts)
        if moved:
            # A detector's export is version zero, always. It is the thing
            # curation gets done *to* rather than a round of curation, so
            # numbering it 1 would make the first real pass v2 and leave the
            # history claiming a pass that never happened.
            first_import = (not versions) and not rec["specified"]
            # Which version this pass was worked from.
            #
            # The stored number stays a plain increasing integer -- it is
            # what the cloud table and the sync are keyed on. This is
            # what makes the LINEAGE recoverable: a pass based on v1
            # while v2 and v3 already existed is a branch off v1, and
            # `versions.labels` reads that back out as "v1.1". Without
            # it, going back to an earlier version and carrying on left
            # a history claiming the work came after everything before
            # it.
            #
            # Absent means "from whatever was newest", which is what
            # every pass did before there was a choice.
            based_on = entry.get("based_on")
            if based_on is None and not first_import:
                based_on = versionsmod.based_on_default(versions)
            fresh = {
                # Highest so far plus one, not the count -- the import sits
                # at zero and would otherwise make the numbering skip.
                "v": 0 if first_import
                     else max([v.get("v") or 0 for v in versions] or [0]) + 1,
                # A stable key, so two machines' histories union instead
                # of one replacing the other.
                "id": uuid.uuid4().hex[:12],
                # The version this one was worked from, by stored id.
                "from_v": (None if first_import else based_on),
                "at": _now(),
                "by": who,
                "note": (entry.get("version_note") or "").strip(),
                "n": rec["n"],
                "by_label": dict(counts),
                "changed": changed,
                "gained": gained,
                "lost": lost,
                "moves": moves,
                "machine": entry.get("machine") or platform.node(),
            }
            # Only when something did. A zero on every version in a history
            # that has never been aligned is a column of noise.
            if shifted:
                fresh["shifted"] = shifted
            if len(clean) <= self.SNAP_MAX_EVENTS:
                fresh["snap"] = [[ev.get("start"),
                                  ev.get("label_id") or ev.get("label")]
                                 for ev in clean]
            # The first version of an entry nobody has curated is the
            # detector's export -- the thing curation gets done *to*.
            # Saying so here means a later curated bank recognises it
            # and does not insert a second, identical record of the same
            # import as version zero: the history read v0 "imported, none
            # decided", v1 "imported, none decided", v2 "first pass".
            if first_import:
                fresh["imported"] = True
                fresh["note"] = fresh["note"] or (
                    "Imported from "
                    + ((rec.get("source") or {}).get("pipeline")
                       or "a detector")
                    + ". " + str(rec["n"])
                    + " candidates, none decided yet.")
            versions.append(fresh)

            # A set whose very first bank is already curated: the migration
            # edge case, where the sorting happened before Jarvis existed and
            # arrives all at once. The unsorted list still has to be v0 --
            # it is the thing the sorting was done to, and without it the
            # history opens on a finished set and cannot say what moved. So
            # the same times with no decision on any of them go in below the
            # pass that decided them.
            if (not prior) and rec["specified"] and len(versions) == 1:
                fresh["v"] = 1
                # The unsorted list going in below it IS what this pass
                # was done to, whatever the caller said.
                fresh["from_v"] = 0
                versions.insert(0, {
                    "v": 0,
                    "id": "v0-" + uuid.uuid4().hex[:8],
                    "at": fresh["at"],
                    "by": fresh["by"],
                    "note": "Imported from "
                            + ((rec.get("source") or {}).get("pipeline")
                               or "a detector")
                            + ". " + str(rec["n"])
                            + " candidates, none decided yet.",
                    "n": rec["n"],
                    "by_label": {"unspecified": rec["n"]},
                    "changed": 0, "gained": 0, "lost": 0, "moves": {},
                    "machine": fresh.get("machine"),
                    "imported": True,
                    "synthesized": True,
                    "snap": ([[ev.get("start"), None] for ev in clean]
                             if len(clean) <= self.SNAP_MAX_EVENTS else None),
                })
                if versions[0]["snap"] is None:
                    versions[0].pop("snap")
                # What the first pass actually did, now that there is a
                # before to compare it to.
                moved_to = {}
                for ev in clean:
                    lab = ev.get("label_id") or ev.get("label")
                    if lab:
                        key = "undecided → %s" % lab
                        moved_to[key] = moved_to.get(key, 0) + 1
                fresh["moves"] = moved_to
                fresh["changed"] = sum(moved_to.values())

            # Older snapshots go; their counts and their notes stay, so the
            # history is still complete, only less finely comparable far
            # back. Version zero keeps its snapshot however old it gets:
            # it is the only record of the candidates the detector found,
            # and the entry it came from has been deleted.
            for old in versions[:-self.SNAP_VERSIONS]:
                if not old.get("imported"):
                    old.pop("snap", None)
        elif versions:
            # Nothing changed, so no new version -- but say it was checked,
            # because "banked again and it was identical" is information.
            versions[-1].setdefault("confirmed", [])
            versions[-1]["confirmed"].append({"at": _now(), "by": who})
        rec["versions"] = versions
        # `is not None`, because version zero is a real version and
        # `versions[-1]["v"] or 1` would quietly relabel every import as v1.
        rec["version"] = (versions[-1]["v"] if versions
                          and versions[-1].get("v") is not None else
                          (0 if not rec["specified"] else 1))

        if prior:
            rec["history"] = list(prior.get("history") or [])
            if prior.get("n") != rec["n"] or prior.get("events") != clean:
                rec["history"].append({
                    "at": _now(), "by": who, "changed": ["events"],
                    "was_n": prior.get("n"), "now_n": rec["n"],
                    "why": "re-banked from the curation set",
                })

        base = self._base_of(rec)
        with _LOCK:
            rec = self.book.write(base, rec)
            self._drop_cache()
        rec["path"] = self.book.mine(base)
        rec["replaced"] = bool(prior)
        rec["new_version"] = bool(moved) and bool(prior)
        return rec

    # A version keeps what every candidate was called at the time, so any
    # two versions can be compared rather than only consecutive ones. Kept
    # for the most recent versions only: the point is the recent history,
    # and an entry banked every week for a year should not carry a year of
    # event lists.
    SNAP_VERSIONS = 12
    SNAP_MAX_EVENTS = 6000
    # How many before/after rows a preview carries. A set is usually a few
    # hundred to a few thousand; past this the panel says it is showing part.
    PREVIEW_MAX = 5000

    def source_entry_for(self, gid, kind, events):
        """The detector import these curated events came from, if it is here.

        Every curated time has to be one of the import's times. A list that
        merely overlaps is a different list, and adopting it would fold two
        unrelated records together -- which is worse than the duplicate this
        is trying to avoid.
        """
        want = set()
        for ev in events or []:
            try:
                want.add(round(float(ev["start"]), 4))
            except (TypeError, ValueError, KeyError):
                continue
        if not want:
            return None
        best = None
        for rec in self.all():
            if rec.get("gid") != gid:
                continue
            if (rec.get("type") or "") != kind:
                continue
            # Something already curated is not the thing it came from.
            if rec.get("curation_label") is not None:
                continue
            got = set()
            for ev in rec.get("events") or []:
                try:
                    got.add(round(float(ev["start"]), 4))
                except (TypeError, ValueError, KeyError):
                    continue
            if not got or not want.issubset(got):
                continue
            # The most complete list wins, then the oldest -- the import is
            # the thing that came first.
            key = (len(got), (rec.get("added") or {}).get("at") or "")
            if best is None or key > best[0]:
                best = (key, rec)
        return best[1] if best else None

    def curated_entries(self, gid, kind=None, label=None):
        """The entries a curation set has already written, newest first.

        Identity is the triple the curation route stamps on everything it
        banks: which recording, which kind of set, which category. Entries
        that came from anywhere else have no `curation_label` and are never
        matched, so re-banking a set cannot touch an imported list that
        happens to sit beside it.
        """
        out = []
        for rec in self.all():
            if rec.get("gid") != gid:
                continue
            if rec.get("curation_label") is None:
                continue
            if kind is not None and (rec.get("type") or "") != kind:
                continue
            if label is not None and rec.get("curation_label") != label:
                continue
            out.append(rec)
        out.sort(key=lambda r: (r.get("added") or {}).get("at") or "",
                 reverse=True)
        return out

    def _base_of(self, rec):
        """The filename stem. The entry id is last so _base_for_id can find
        it again without having to reconstruct the project and mouse."""
        return shards.safe_base("%s_%s_%s_%s" % (
            _slug(rec.get("project"), "unfiled"),
            _slug("m%s" % rec["mouse"] if rec.get("mouse") is not None
                  else "m", "m"),
            _slug("s%s" % rec["session"] if rec.get("session") is not None
                  else "s", "s"),
            rec["id"]))

    @shards.atomic
    def update(self, entry_id, patch):
        """Edit the describable parts. Provenance is not one of them."""
        rec = self.get(entry_id)
        if not rec:
            raise BankError("No such entry.")
        editable = ("project", "mouse", "session", "type", "type_name",
                    "name", "note", "session_label", "session_path")
        for k in editable:
            if k in patch:
                rec[k] = patch[k]
        rec.setdefault("history", []).append({
            "at": _now(),
            "by": (self.store.provenance().get("user") if self.store else None),
            "changed": sorted(k for k in patch if k in editable),
        })
        with _LOCK:
            base = self._base_for_id(entry_id)
            rec = self.book.write(base, rec) if base else rec
            self._drop_cache()
        return rec

    @shards.atomic
    def rename_person(self, old, new):
        """Re-credit an entry from one spelling of a name to another.

        `update` refuses this on purpose -- "provenance is not one of them" --
        and that guard is right: nobody editing a description should be able
        to change who added the events. But a person whose name is recorded
        three ways has three partial histories, and reconciling that is a
        different act from editing a caption. So it gets its own method,
        narrow enough to read at a glance, rather than a hole in the other
        one.

        Recorded in the entry's history, because a silent re-credit is
        indistinguishable from the record having always said this.
        """
        old_l = str(old or "").strip().lower()
        if not old_l or not new:
            return 0
        n = 0
        for rec in list(self.all()):
            eid = rec.get("id")
            live = self.get(eid)
            if not live:
                continue
            hit = 0
            added = live.get("added") or {}
            if str(added.get("by") or "").strip().lower() == old_l:
                added["by"] = new
                live["added"] = added
                hit += 1
            for v in (live.get("versions") or []):
                if str(v.get("by") or "").strip().lower() == old_l:
                    v["by"] = new
                    hit += 1
            if not hit:
                continue
            live.setdefault("history", []).append({
                "at": _now(),
                "by": (self.store.provenance().get("user")
                       if self.store else None),
                "renamed": {"from": old, "to": new, "fields": hit},
            })
            base = self._base_for_id(eid)
            if base:
                self.book.write(base, live)
            self._drop_cache()
            n += hit
        return n

    # ------------------------------------------------------------------
    # Re-timing
    # ------------------------------------------------------------------
    # What a snapshot holds: a start and a label. Any other field on an
    # event cannot survive a round trip through one, so restoring from a
    # version has to say which fields it dropped rather than dropping them.
    SNAP_FIELDS = {"start", "label", "label_id"}

    @staticmethod
    def basis_at(rec, v):
        """Which clock the events were on as of version `v`.

        NOT the entry's `time_basis`, which describes the current events. If
        the correction was applied at v4 then v5 is on the recording's clock
        and v3 is not, and asking the entry gives the wrong answer for three
        of those. Applying the shift to a version that already has it is the
        single failure this whole area exists to prevent.
        """
        vers = sorted((rec.get("versions") or []),
                      key=lambda x: x.get("v") or 0)
        last = None
        for ver in vers:
            if (ver.get("v") or 0) > v:
                break
            if ver.get("retimed"):
                last = (ver["retimed"] or {}).get("to")
        if last:
            return last
        tb = rec.get("time_basis") or {}
        # No conversion at or before this version, so it is on whatever the
        # entry started on -- which is what a later conversion recorded as
        # the thing it converted FROM.
        return tb.get("converted_from") or tb.get("kind")

    @staticmethod
    def version_key(ver):
        """A handle that names one version and only one.

        The `id` where there is one. Versions minted before ids existed have
        none -- three of the eight on M8s9feb8 -- and the obvious fallback,
        the stored number, is the one thing that is NOT unique. Falling back
        to it produced exactly the confusion it was meant to avoid: a chooser
        showing "v6" sent back "4", and the bank answered about a version
        numbered 4 that the person had never heard of.

        So an id-less version is keyed on what it contains. Deterministic,
        so the key a plan hands out is the key a run sends back; derived
        rather than minted, so nothing has to be written to the archive to
        make old versions addressable; and content-based rather than
        positional, so a shard arriving between the two does not shift it.
        """
        if ver.get("id"):
            return str(ver["id"])
        seed = json.dumps([ver.get("v"), ver.get("at"), ver.get("by"),
                           ver.get("note"), ver.get("n")],
                          sort_keys=True, separators=(",", ":"))
        return "vk-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def from_name(rec, src_v=None):
        """The NAME of the version a write would read from."""
        vers = list(rec.get("versions") or [])
        named = versionsmod.label_rows(vers)
        if not named:
            return None
        par = EventBank.parent_of(rec, src_v)
        for row, name in named:
            if row is par:
                return name
        return versionsmod.newest([n for _r, n in named])

    @staticmethod
    def is_branch(rec, src_v=None):
        """Whether a write would BRANCH rather than continue the line.

        It branches when something is already built on what it is reading:
        reading v3 while v4 exists writes v3.1 and leaves v4 alone, while
        reading the newest writes the next whole number. The two are
        different enough that saying the wrong one is worse than saying
        nothing, and the panel has no way to tell them apart from a number.
        """
        nxt = EventBank.next_name(rec, src_v)
        frm = EventBank.from_name(rec, src_v)
        if not nxt or not frm:
            return False
        return len(versionsmod.key(nxt)) > len(versionsmod.key(frm))

    @staticmethod
    def next_name(rec, src_v=None):
        """What a version written now would be CALLED, given what it reads.

        Not "the one after the tip". Picking up an older version branches
        off it -- that is the whole rule this module's names exist to
        express -- so reading v4 while v5 and v6 exist writes v4.1, not v7.
        Naming it off the tip is how the panel came to promise one number
        and the history then showed another.
        """
        vers = list(rec.get("versions") or [])
        named = versionsmod.label_rows(vers)
        names = [n for _r, n in named]
        if not names:
            return "1"
        par = EventBank.parent_of(rec, src_v)
        from_name = None
        if par is not None:
            for row, name in named:
                if row is par:
                    from_name = name
                    break
        if from_name is None:
            from_name = versionsmod.newest(names)
        return versionsmod.next_after(from_name, names)

    @staticmethod
    def parent_of(rec, want):
        """The version a new one should say it came from.

        `want` is whatever the caller asked to read: an id, a content key,
        or a number. Resolved to the actual row here so the new version can
        record its parent's ID rather than the string it happened to be
        addressed by -- which is the difference between a history that
        labels correctly and one where every aligned version looks like the
        start of a new line.

        `None` means "whatever is newest", which is what a run that was not
        told otherwise reads.
        """
        vers = list(rec.get("versions") or [])
        if not vers:
            return None
        if want is None:
            # The newest BY LINEAGE, resolved to the row itself.
            #
            # Not by number: `based_on_default` answers with a number, and
            # on a history where two versions share one, the first row
            # carrying it is not necessarily the newest -- which made a
            # write that read the newest claim it had branched off
            # something in the middle.
            named = versionsmod.label_rows(vers)
            tip = versionsmod.newest([n for _r, n in named])
            for row, name in named:
                if name == tip:
                    return row
            return None
        try:
            return EventBank.version_at(rec, want)
        except Exception:                                # noqa: BLE001
            # An unresolvable ref is not a reason to refuse the write --
            # the events were read from somewhere and the caller has
            # already been told if that failed. It is a reason to record no
            # parentage rather than a wrong one.
            return None

    @staticmethod
    def version_at(rec, want):
        """One version, by its id, by its content key, or by its number.

        THE NUMBER IS NOT UNIQUE. Two machines curating the same entry both
        mint the next number and the union keeps both, which is the right
        outcome and is what the per-version `id` exists for -- this bank
        holds an entry numbered 0,1,2,3,4,3,4. So a caller that asks for "3"
        is asking an ambiguous question, and answering it by taking whichever
        came first in the file would quietly read one person's pass while
        naming the other's.

        Asked by id, it is exact. Asked by a number only one version has, it
        is exact. Asked by a number two versions share, it refuses and says
        which ids to choose between, because there is no defensible way to
        pick and a wrong answer here reads events that somebody else decided.
        """
        vers = list(rec.get("versions") or [])
        if want is None:
            raise BankError("No version was asked for.")
        # Exact first: the id, then the content key an id-less version is
        # addressed by. Only if neither matches is the ambiguous number
        # tried at all.
        for ver in vers:
            if ver.get("id") is not None and ver.get("id") == want:
                return ver
        for ver in vers:
            if EventBank.version_key(ver) == want:
                return ver
        try:
            n = int(want)
        except (TypeError, ValueError):
            raise BankError("This set has no version %r." % (want,))
        same = [v for v in vers if (v.get("v") or 0) == n]
        if not same:
            raise BankError("This set has no version %s." % n)
        if len(same) > 1:
            raise BankError(
                "This set has %d versions numbered %s -- they were minted "
                "independently on different machines and both were kept. "
                "Ask for one of them by its key: %s."
                % (len(same), n,
                   ", ".join(EventBank.version_key(v) for v in same)))
        return same[0]

    def events_at(self, rec, v):
        """Rebuild one version's events from its snapshot.

        Returns (events, dropped) where `dropped` names the fields the
        current events carry that a snapshot cannot hold. Never guesses at
        one: an event with a channel comes back without it, said out loud.
        """
        hit = self.version_at(rec, v)
        snap = hit.get("snap")
        if not snap:
            raise BankError(
                "Version %s has no snapshot on this machine, so the events "
                "it held cannot be read back. %s"
                % (v, "It was recorded elsewhere and its snapshot has not "
                      "synced yet." if hit.get("snap_elsewhere")
                   else "Sets over %d events do not carry one."
                        % self.SNAP_MAX_EVENTS))

        names = rec.get("label_names") or {}
        out = []
        for row in snap:
            try:
                start = float(row[0])
            except (TypeError, ValueError, IndexError):
                continue
            ev = {"start": start}
            lab = row[1] if len(row) > 1 else None
            if lab:
                ev["label_id"] = lab
                ev["label"] = names.get(lab, lab)
            out.append(ev)

        dropped = sorted({k for e in (rec.get("events") or [])
                          for k in e if k not in self.SNAP_FIELDS})
        return out, dropped

    def retime_versions(self, entry_id, target):
        """Every version, and whether the correction can be run from it.

        One row per version with the reason it is not on offer where it is
        not, because "this one is missing" is a question somebody will ask
        of every version that is.
        """
        rec = self.get(entry_id)
        if not rec:
            raise BankError("No bank entry %s." % entry_id)
        cur = max([v.get("v") or 0 for v in (rec.get("versions") or [])]
                  or [0])
        dropped = sorted({k for e in (rec.get("events") or [])
                          for k in e if k not in self.SNAP_FIELDS})
        rows = []
        for ver in sorted((rec.get("versions") or []),
                          key=lambda x: x.get("v") or 0):
            v = ver.get("v") or 0
            basis = self.basis_at(rec, v)
            why = None
            if basis == target:
                why = ("already on %s — it was corrected at or before this "
                       "version" % target)
            elif not ver.get("snap"):
                why = ("no snapshot on this machine, so its events cannot "
                       "be read back")
            rows.append({
                "v": v,
                "id": ver.get("id"),
                "at": ver.get("at"),
                "by": ver.get("by"),
                "n": ver.get("n"),
                "note": ver.get("note"),
                "by_label": ver.get("by_label") or {},
                "basis": basis,
                "current": v == cur,
                "retimed": bool(ver.get("retimed")),
                "usable": why is None,
                "why_not": why,
            })
        return {"current_version": cur, "versions": rows,
                "drops_fields": dropped}

    @shards.atomic
    def retime(self, entry_id, mapping, target, basis_from, gap_map_sha,
               note=None, by=None, dry_run=True, extra=None,
               from_version=None):
        """Mint a version of `entry_id` with every time on the other clock.

        `mapping` is a callable taking one time and returning
        `(new_time, segment_index)`, or `(None, None)` when there is no
        answer -- an event past the end of the data. Those are reported and
        NOT moved; an event this cannot place is a fault somewhere else and
        quietly clamping it to the last sample would hide that.

        `dry_run=True` is the default and returns exactly what the write
        would do, because a timestamp rewrite that cannot be read before it
        happens should not be offered at all.

        `from_version` reads the events out of that version's snapshot
        instead of taking the current ones, so the correction can be applied
        to the set as it stood at a chosen point -- with that version's
        labels. It still lands as the next version; nothing is overwritten
        and no version is removed.
        """
        rec = self.get(entry_id)
        if not rec:
            raise BankError("No bank entry %s." % entry_id)

        src_v, dropped = None, []
        if from_version is not None:
            try:
                src_v = int(from_version)
            except (TypeError, ValueError):
                raise BankError("%r is not a version number." % from_version)

        if src_v is None:
            basis = (rec.get("time_basis") or {}).get("kind")
        else:
            # The basis of THAT version, not of the entry. See basis_at.
            basis = self.basis_at(rec, src_v)
        if basis == target:
            raise BankError(
                "This entry is already on %s. Absence of a basis means "
                "unknown, not correct -- but this one says so." % target)
        if basis and basis != basis_from:
            raise BankError(
                "This entry says it is on %s, not %s. Re-timing it would "
                "be applying a correction it does not need." % (basis, basis_from))

        if src_v is None:
            events = rec.get("events") or []
        else:
            events, dropped = self.events_at(rec, src_v)

        moved, unplaceable, shifts = [], [], []
        for ev in events:
            try:
                t = float(ev.get("start"))
            except (TypeError, ValueError):
                unplaceable.append(ev)
                continue
            new_t, seg = mapping(t)
            if new_t is None:
                unplaceable.append(ev)
                continue
            item = dict(ev)
            item["start"] = round(float(new_t), 6)
            if ev.get("end") is not None:
                try:
                    e_new, _seg = mapping(float(ev["end"]))
                    if e_new is not None:
                        item["end"] = round(float(e_new), 6)
                except (TypeError, ValueError):
                    pass
            shifts.append(round((float(new_t) - t) * 1e3, 4))
            moved.append(item)

        # A uniform forward shift is monotone, so the order cannot change --
        # asserted rather than assumed, because if it ever did the set and
        # the bank would stop lining up and nothing else would notice.
        ordered = sorted(moved, key=lambda e: e["start"])
        order_held = [id(x) for x in ordered] == [id(x) for x in moved]

        report = {
            "entry_id": entry_id,
            "name": rec.get("name"),
            "gid": rec.get("gid"),
            "session_label": rec.get("session_label"),
            "was": len(events),
            "moved": len(moved),
            "unplaceable": len(unplaceable),
            "unplaceable_times": [e.get("start") for e in unplaceable[:10]],
            "order_held": order_held,
            "shift_min_ms": min(shifts) if shifts else 0.0,
            "shift_max_ms": max(shifts) if shifts else 0.0,
            "from": basis_from,
            "to": target,
            "gap_map_sha": gap_map_sha,
            "dry_run": bool(dry_run),
            # Before and after for a handful, because a preview of a
            # timestamp rewrite that shows only counts is asking to be
            # approved on trust.
            "sample": [
                {"was": e.get("start"), "now": m["start"],
                 "label": m.get("label"),
                 "shift_ms": round((m["start"] - e["start"]) * 1e3, 3)}
                for e, m in list(zip(events, moved))[:8]
            ],
            # And all of them, four values each rather than a dict, so the
            # panel can scroll the set, mark the ones that move and draw
            # them on the recording. Eight was worse than useless here:
            # every gap is at 1762 s and the set starts at 1.7 s, so the
            # first eight all shift by 0.00 ms.
            "moves": [
                [e.get("start"), m["start"],
                 round((m["start"] - e["start"]) * 1e3, 3), m.get("label")]
                for e, m in list(zip(events, moved))[:self.PREVIEW_MAX]
            ],
            "moves_capped": len(moved) > self.PREVIEW_MAX,
            "n_shifted": sum(1 for e, m in zip(events, moved)
                             if abs(m["start"] - e["start"]) > 5e-7),
            # What this would become and what it would keep. Computed here
            # rather than in the branch that writes, so a DRY RUN can name
            # both -- which is what the confirmation is built from.
            "current_version": max(
                [v.get("v") or 0 for v in (rec.get("versions") or [])] or [0]),
            # And what those are CALLED. The number is not unique, so a
            # confirmation that says "this becomes v5" can be naming a
            # version that already exists -- see `versions.tip_next`.
            "current_name": versionsmod.tip_next(rec.get("versions") or [])[0],
            # What THIS write would be called, which depends on what it is
            # reading: picking up an older version branches off it.
            "next_name": EventBank.next_name(rec, src_v),
            # And WHAT IT IS READING, by name, plus whether that makes this
            # a branch. Both, because a confirmation that says "becomes v4,
            # branching off v3" is describing two different writes: v4
            # continues v3, and branching off v3 would be v3.1. The panel
            # cannot work out which from a version number.
            "from_name": EventBank.from_name(rec, src_v),
            "branching": EventBank.is_branch(rec, src_v),
            "next_version": max(
                [v.get("v") or 0 for v in (rec.get("versions") or [])]
                or [0]) + 1,
            "n_versions": len(rec.get("versions") or []),
            # Which version supplied the times and the labels. `None` means
            # the live set, which is the default and the common case.
            "from_version": src_v,
            # Fields the current events carry that a snapshot cannot hold,
            # and which restoring from one therefore loses. Empty for every
            # entry in this archive but the twenty-one that carry a channel.
            "drops_fields": dropped,
        }
        if dropped:
            report["warning"] = (
                "Version %s's snapshot holds a start and a label only, so "
                "%s would not survive being read back from it."
                % (src_v, ", ".join(dropped)))
        if unplaceable:
            report["error"] = ("%d event(s) have no time on the other clock. "
                               "Nothing was written." % len(unplaceable))
            return report
        if not order_held:
            report["error"] = ("The shift reordered the events, which a "
                               "forward step function cannot do. Nothing was "
                               "written.")
            return report
        # Already done, with the same map, from the same source. The id is
        # derived rather than random so two machines converge on one
        # version; the same derivation makes a repeat recognisable here
        # instead of appending a second identical entry to the history.
        twin = "rt-" + hashlib.sha256(
            ("%s|%s|%s|%s" % (entry_id, gap_map_sha, target, src_v)
             ).encode("utf-8")).hexdigest()[:10]
        for ver in (rec.get("versions") or []):
            if ver.get("id") == twin:
                report["already_version"] = ver.get("v")
                report["error"] = (
                    "This exact correction is already version %s of this "
                    "set — same gap map, same source. Delete that version "
                    "to undo it, or correct from a different one."
                    % ver.get("v"))
                return report

        if dry_run:
            return report

        prov = self.store.provenance() if self.store else {}
        who = (by or prov.get("user") or "unknown").strip()
        versions = list(rec.get("versions") or [])
        # The version this one is built on, as a row rather than as
        # the string it was addressed by -- see `parent_of`.
        _par = EventBank.parent_of(rec, src_v)
        counts = {}
        for ev in moved:
            key = ev.get("label") or "unspecified"
            counts[key] = counts.get(key, 0) + 1

        fresh = {
            # Derived from what was applied, not minted at random: two
            # machines correcting the same entry with the same map must
            # converge on one version rather than each adding its own.
            "id": "rt-" + hashlib.sha256(
                ("%s|%s|%s|%s" % (entry_id, gap_map_sha, target, src_v)
                 ).encode("utf-8")).hexdigest()[:10],
            "v": max([v.get("v") or 0 for v in versions] or [0]) + 1,
            # A correction applied to a chosen version is a branch off that
            # version, not a continuation of whatever happened to be newest.
            # Without this, re-timing v1 while v2 and v3 existed produced a
            # v4 whose history claimed it came after them.
            #
            # BY ID as well as by number. What the caller sends is a ref,
            # and a ref written into `from_v` matches no version number at
            # all -- so the labeller called the result a root and named it
            # as though it began a new line.
            "from_v": ((_par.get("v") if _par else None)
                       if src_v is not None
                       else versionsmod.based_on_default(versions)),
            "from_id": (_par or {}).get("id"),
            "at": _now(),
            "by": who,
            "note": note or (
                "Re-timed from %s to %s%s. %d event(s) moved by %.1f to "
                "%.1f ms; every label kept, nothing re-detected."
                % (basis_from, target,
                   "" if src_v is None else ", reading v%d" % src_v,
                   len(moved), report["shift_min_ms"],
                   report["shift_max_ms"])),
            "n": len(moved),
            "by_label": counts,
            # Nothing was decided differently. The counts are identical and
            # saying otherwise would put a relabelling in the history that
            # never happened.
            "changed": 0, "gained": 0, "lost": 0, "moves": {},
            "machine": platform.node(),
            "retimed": {
                "from": basis_from, "to": target,
                # The lineage, so a version minted off an older one is not
                # mistaken for one minted off its own predecessor.
                "source_version": src_v,
                "gap_map_sha": gap_map_sha,
                "shift_min_ms": report["shift_min_ms"],
                "shift_max_ms": report["shift_max_ms"],
            },
        }
        if len(moved) <= self.SNAP_MAX_EVENTS:
            fresh["snap"] = [[ev.get("start"),
                              ev.get("label_id") or ev.get("label")]
                             for ev in moved]
        versions.append(fresh)

        rec["events"] = moved
        rec["versions"] = versions
        rec["n"] = len(moved)
        rec["by_label"] = counts
        # Written LAST in spirit: an entry whose events moved but whose
        # stamp is absent reads as un-retimed and is re-runnable, which is
        # the recoverable half of a partial application. The two go into one
        # file here so they land together or not at all.
        rec["time_basis"] = {
            "kind": target,
            "converted_from": basis_from,
            "gap_map_sha": gap_map_sha,
            "tool": "jarvis.retime/1",
            "at": _now(),
            "by": who,
        }
        if extra:
            rec["time_basis"].update(extra)

        base = self._base_of(rec)
        with _LOCK:
            rec = self.book.write(base, rec)
            self._drop_cache()
        report["version"] = fresh["v"]
        report["version_id"] = fresh["id"]
        report["time_basis"] = rec["time_basis"]
        return report

    # ------------------------------------------------------------------
    # Alignment
    # ------------------------------------------------------------------
    @shards.atomic
    def align(self, entry_id, moves, params, note=None, by=None,
              dry_run=True, from_version=None, flags=None, keep_ids=None,
              reject=None):
        """Mint a version of `entry_id` with every stamp on its own peak.

        `moves` is `{index_into_the_source_events: new_start}`. Indices
        rather than times, because the whole point is that a time is not an
        identity here -- two stamps 0.05 ms apart would key to one entry in
        a dict and one of them would be silently skipped.

        An index absent from `moves` is a stamp that stays where it is: a
        flag nobody resolved, or one with no peak in reach. It is written
        unchanged, and it is NOT an error.

        Everything else is `retime`'s shape, for the same reasons written
        there: a dry run that shows what the write would do, a version id
        derived from what was applied so two machines converge on one
        version, a refusal to apply the same alignment twice, and `from_v`
        pointing at the version the stamps were read from.
        """
        rec = self.get(entry_id)
        if not rec:
            raise BankError("No bank entry %s." % entry_id)

        # By id where the caller has one, because the NUMBER is not unique
        # -- see `version_at`. `src_v` stays the number for the record, since
        # `from_v` is what `versions.label_rows` walks to work out lineage
        # and that is numbered; `src_id` is what actually chose the version.
        src_v, src_id, dropped = None, None, []
        if from_version is not None:
            src = self.version_at(rec, from_version)
            src_v = src.get("v") or 0
            src_id = src.get("id")

        if from_version is None:
            events = rec.get("events") or []
        else:
            events, dropped = self.events_at(rec, from_version)

        flags = flags or {}
        out, shifts, dropped_lbl = [], [], {}
        # ONLY THE EVENTS.
        #
        # A curated set is a detector's candidate list plus a verdict on
        # each one, and Braces only ever moves the ones somebody kept --
        # moving a rejected stamp would assert a position for something
        # that is not an event. So the rejected ones were being carried
        # into the aligned version unchanged, which makes the version an
        # analysis reads a mixture of events and things that were thrown
        # out.
        #
        # Nothing is lost: a version is a new row in a history, and every
        # earlier one still holds the whole candidate list with its
        # verdicts. That is where "what did the detector find, and what did
        # we reject" is answered. What THIS version is for is the spikes.
        want = set(keep_ids) if keep_ids else None
        # Stamps somebody looked at on the recording and said were not
        # events after all. Not moved, not written, and counted apart from
        # the ones that were already rejected in curation -- "I threw this
        # one out just now" and "this was thrown out last week" are
        # different facts and the record should keep them that way.
        drop = {int(i) for i in (reject or [])}
        for i, ev in enumerate(events):
            if i in drop:
                dropped_lbl["rejected here"] = dropped_lbl.get(
                    "rejected here", 0) + 1
                continue
            if want is not None:
                lab = ev.get("label_id") or ev.get("label")
                if lab not in want:
                    k = lab or "undecided"
                    dropped_lbl[k] = dropped_lbl.get(k, 0) + 1
                    continue
            item = dict(ev)
            # `from_t` never accumulates: a stamp aligned twice records the
            # place it started this round from, not two rounds ago. The
            # version record is where the whole lineage lives.
            item.pop("from_t", None)
            new_t = moves.get(i, moves.get(str(i)))
            if new_t is not None:
                try:
                    was_t = float(ev.get("start"))
                    new_t = float(new_t)
                except (TypeError, ValueError):
                    raise BankError(
                        "Event %d has no usable time, so it cannot be "
                        "aligned." % i)
                if abs(new_t - was_t) > 1e-9:
                    item["start"] = round(new_t, 6)
                    item["from_t"] = round(was_t, 6)
                    shifts.append(round((new_t - was_t) * 1e3, 4))
            why = flags.get(i, flags.get(str(i)))
            if why:
                # Why it was asked about, kept on the event. Six months on,
                # "this one is 94 ms off its neighbour" is a question the
                # record should answer rather than the person who was there.
                item["align_flag"] = why
            else:
                item.pop("align_flag", None)
            out.append(item)

        ordered = sorted(out, key=lambda e: float(e.get("start") or 0.0))
        order_held = [id(x) for x in ordered] == [id(x) for x in out]

        # Two stamps at one time is the failure the one-peak-per-stamp rule
        # exists to prevent, so it is checked here too rather than trusted
        # across a module boundary: this is the last place before the write.
        seen, collided = set(), []
        for e in out:
            try:
                k = round(float(e["start"]), self.DUP_DP)
            except (TypeError, ValueError, KeyError):
                continue
            if k in seen:
                collided.append(k)
            seen.add(k)

        absol = sorted(abs(s) for s in shifts)
        report = {
            "entry_id": entry_id,
            "name": rec.get("name"),
            "gid": rec.get("gid"),
            "session_label": rec.get("session_label"),
            "was": len(events),
            "moved": len(shifts),
            # Of what is being WRITTEN, not of what was read. The rejected
            # candidates are not being written, so counting them as
            # "staying where they are" would promise sixteen stamps in a
            # version that will not contain them.
            "unmoved": len(out) - len(shifts),
            "n_events": len(out),
            "order_held": order_held,
            "collisions": collided[:10],
            "shift_min_ms": min(shifts) if shifts else 0.0,
            "shift_max_ms": max(shifts) if shifts else 0.0,
            "shift_max_abs_ms": absol[-1] if absol else 0.0,
            "params": dict(params or {}),
            "dry_run": bool(dry_run),
            "moves": [
                [e.get("from_t"), e.get("start"),
                 round((float(e["start"]) - float(e["from_t"])) * 1e3, 3),
                 e.get("label"), e.get("align_flag")]
                for e in out if e.get("from_t") is not None
            ][:self.PREVIEW_MAX],
            "moves_capped": len(shifts) > self.PREVIEW_MAX,
            "current_version": max(
                [v.get("v") or 0 for v in (rec.get("versions") or [])] or [0]),
            # And what those are CALLED. The number is not unique, so a
            # confirmation that says "this becomes v5" can be naming a
            # version that already exists -- see `versions.tip_next`.
            "current_name": versionsmod.tip_next(rec.get("versions") or [])[0],
            # What THIS write would be called, which depends on what it is
            # reading: picking up an older version branches off it.
            "next_name": EventBank.next_name(rec, src_v),
            # And WHAT IT IS READING, by name, plus whether that makes this
            # a branch. Both, because a confirmation that says "becomes v4,
            # branching off v3" is describing two different writes: v4
            # continues v3, and branching off v3 would be v3.1. The panel
            # cannot work out which from a version number.
            "from_name": EventBank.from_name(rec, src_v),
            "branching": EventBank.is_branch(rec, src_v),
            "next_version": max(
                [v.get("v") or 0 for v in (rec.get("versions") or [])]
                or [0]) + 1,
            "n_versions": len(rec.get("versions") or []),
            "from_version": src_v,
            "drops_fields": dropped,
            # What was left out for not being an event, by label. Said
            # before the write, because "where did my 16 garbage stamps
            # go" has to have an answer on the screen that asked.
            "dropped": dict(dropped_lbl),
            "n_dropped": sum(dropped_lbl.values()),
        }
        if dropped:
            report["warning"] = (
                "Version %s's snapshot holds a start and a label only, so "
                "%s would not survive being read back from it."
                % (src_v, ", ".join(dropped)))
        if not order_held:
            report["error"] = (
                "The alignment reordered the events, which the no-crossing "
                "rule makes impossible -- so something upstream is wrong. "
                "Nothing was written.")
            return report
        if collided:
            report["error"] = (
                "%d stamp(s) would land on a time another stamp already "
                "holds, which is a duplicate rather than an alignment. "
                "Nothing was written." % len(collided))
            return report
        if not shifts and not dropped_lbl:
            # NOT AN ERROR, and it used to be reported as one.
            #
            # Every stamp already sitting where the recording puts it is a
            # good outcome and a common one -- a set aligned once and
            # looked at again says exactly this. There is still nothing to
            # write, so the write does not happen; `nothing_to_do` says
            # which of the two it is, and the panel can be calm about it
            # rather than showing a red failure for a set that is right.
            report["nothing_to_do"] = True
            report["why"] = (
                "Every stamp is already where the recording puts it, so "
                "there is no new version to write. Nothing was changed.")
            return report
        if not shifts:
            # Nothing moved, but the rejected candidates would go, which
            # IS a change worth a version: what an analysis reads is then
            # the spikes rather than the spikes plus everything somebody
            # threw out.
            pass

        twin = "br-" + hashlib.sha256(
            ("%s|%s|%s" % (entry_id, src_id or src_v,
                           json.dumps(params or {}, sort_keys=True,
                                      separators=(",", ":")))
             ).encode("utf-8")).hexdigest()[:10]
        for ver in (rec.get("versions") or []):
            if ver.get("id") == twin:
                report["already_version"] = ver.get("v")
                report["error"] = (
                    "This exact alignment is already version %s of this set "
                    "— same channel, same settings, same source. Delete "
                    "that version to undo it, or align from a different one."
                    % ver.get("v"))
                return report

        if dry_run:
            return report

        prov = self.store.provenance() if self.store else {}
        who = (by or prov.get("user") or "unknown").strip()
        versions = list(rec.get("versions") or [])
        # The version this one is built on, as a row rather than as
        # the string it was addressed by -- see `parent_of`.
        _par = EventBank.parent_of(rec, src_v)
        counts = {}
        for ev in out:
            key = ev.get("label") or "unspecified"
            counts[key] = counts.get(key, 0) + 1

        by_reason = {}
        for why in flags.values():
            if why:
                by_reason[why] = by_reason.get(why, 0) + 1

        fresh = {
            "id": twin,
            "v": max([v.get("v") or 0 for v in versions] or [0]) + 1,
            # An alignment applied to a chosen version is a branch off
            # that version, not a continuation of whatever happened to be
            # newest -- and recorded by ID, because what the panel sends is
            # a ref and a ref matches no version NUMBER, which made every
            # aligned version look like the start of a fresh line.
            "from_v": ((_par.get("v") if _par else None)
                       if src_v is not None
                       else versionsmod.based_on_default(versions)),
            "from_id": (_par or {}).get("id"),
            "at": _now(),
            "by": who,
            "n": len(out),
            "by_label": dict(counts),
            # Nothing was decided differently. Braces never reads a label,
            # let alone writes one, and a relabelling in the history that
            # never happened is worse than no history at all.
            "changed": 0, "gained": 0, "lost": 0, "moves": {},
            "shifted": len(shifts),
            # `platform.node()`, as `bank` and `retime` both write it. NOT
            # `provenance()["machine"]`, which is what the lab calls this
            # computer -- one history carrying both names for one machine is
            # unreadable, and the rest of this file already chose.
            "machine": platform.node(),
            "aligned": {
                "tool": "jarvis.braces/1",
                "source_version": src_v,
                "source_version_id": src_id,
                "n_moved": len(shifts),
                "n_unmoved": len(events) - len(shifts),
                "shift_min_ms": report["shift_min_ms"],
                "shift_max_ms": report["shift_max_ms"],
                "shift_median_ms": (absol[len(absol) // 2] if absol else 0.0),
                "flagged": by_reason,
                "order_held": True,
            },
        }
        fresh["aligned"].update(params or {})
        fresh["note"] = note or (
            "Aligned to the mean magnitude over %s channels, ±%g ms%s. "
            "%d stamp(s) moved by %.1f to %.1f ms; %d left where they were. "
            "No labels changed."
            % ((params or {}).get("n_channels"),
               (params or {}).get("window_ms"),
               "" if src_v is None else ", reading v%d" % src_v,
               len(shifts), report["shift_min_ms"], report["shift_max_ms"],
               len(events) - len(shifts)))
        if len(out) <= self.SNAP_MAX_EVENTS:
            fresh["snap"] = [[ev.get("start"),
                              ev.get("label_id") or ev.get("label")]
                             for ev in out]
        versions.append(fresh)

        rec["events"] = out
        rec["versions"] = versions
        rec["n"] = len(out)
        rec["by_label"] = counts
        # What the CURRENT events are aligned to, the way `time_basis` says
        # what clock they are on. Read by the panel to mark a set that has
        # already been done, and by `align` itself through the twin check.
        rec["aligned"] = {
            "tool": "jarvis.braces/1",
            "at": _now(),
            "by": who,
            "version": fresh["v"],
            "source_version": src_v,
            "source_version_id": src_id,
        }
        rec["aligned"].update(params or {})

        base = self._base_of(rec)
        with _LOCK:
            rec = self.book.write(base, rec)
            self._drop_cache()
        report["version"] = fresh["v"]
        report["version_id"] = fresh["id"]
        report["aligned"] = rec["aligned"]
        return report

    # ------------------------------------------------------------------
    # Duplicate times
    # ------------------------------------------------------------------
    # Two records of one event, not two events. A detector run twice into
    # the same set, or a set restarted on one machine while another still
    # held decisions on it, leaves two rows at the same time -- and because
    # the two copies were then decided separately, a good many of them
    # disagree about what the event was. So this is not housekeeping: every
    # row it removes is a call somebody made, and which call goes has to be
    # said out loud before it goes rather than settled by a sort order.

    # The same key the curation sets match on, so "duplicate" means one
    # thing across the two. Four places is 0.1 ms -- inside a single sample
    # at any rate this lab records at, so two rows this close are one event
    # written twice and never two events.
    DUP_DP = 4
    # Reported, not acted on. Rows a hair apart are the interesting case:
    # they are either one event the detector found twice with a jitter, or
    # two real events in a burst, and nothing here can tell which. Saying
    # how many there are lets somebody go and look.
    NEAR_MS = 1.0

    @classmethod
    def _dup_key(cls, value):
        """A start time as a match key, or None if it is not a time."""
        try:
            return round(float(value), cls.DUP_DP)
        except (TypeError, ValueError):
            return None

    def dup_groups(self, events):
        """Every time that more than one event claims, in order.

        Returns a list of (key, [(index, event), ...]) with the original
        positions kept, because "the first copy" has to mean the first one
        in the set and not the first one some dict happened to yield.
        """
        groups = {}
        for i, ev in enumerate(events or []):
            key = self._dup_key(ev.get("start"))
            if key is None:
                continue
            groups.setdefault(key, []).append((i, ev))
        return [(k, v) for k, v in sorted(groups.items()) if len(v) > 1]

    @shards.atomic
    def dedupe(self, entry_id, conflicts=None, note=None, by=None,
               dry_run=True):
        """Mint a version holding one row per time instead of two.

        `dry_run=True` is the default and returns exactly what the write
        would do, down to which label each contested time would end up
        with. A pass that silently drops a third of somebody's decisions
        should not be offered without that.

        Which copy survives, in order:

          1. A decided copy beats an undecided one. Nothing is lost there:
             the undecided row is the same candidate with nobody's opinion
             attached.
          2. Copies that agree collapse to the one carrying the most
             fields, so a row with a channel is not dropped in favour of a
             bare one saying the same thing.
          3. Copies that DISAGREE are a conflict -- two people decided two
             records of one candidate and both calls are real. There is no
             rule that can settle that, so `conflicts` must say `first` or
             `last` explicitly; without it nothing is written and every
             contested time is named in the report.

        The live events only. Re-running it from an older version would
        mean deciding which of two questions is being asked, and the one
        anybody wants here is "the set as it stands has doubles in it".
        """
        rec = self.get(entry_id)
        if not rec:
            raise BankError("No bank entry %s." % entry_id)
        if conflicts not in (None, "first", "last"):
            raise BankError(
                "%r is not a way to settle a disagreement. Use 'first' or "
                "'last'." % conflicts)

        events = rec.get("events") or []
        groups = self.dup_groups(events)

        # Rows a hair apart, counted and not touched. See NEAR_MS.
        times = sorted(t for t in (self._dup_key(e.get("start"))
                                   for e in events) if t is not None)
        times_seen = set(times)
        near = sum(1 for a, b in zip(times, times[1:])
                   if 0 < (b - a) * 1e3 <= self.NEAR_MS)

        def labelled(ev):
            return ev.get("label_id") or ev.get("label")

        drop_idx, rows, contested = set(), [], []
        kept_decided = undecided_dropped = 0
        for key, members in groups:
            decided = [(i, e) for i, e in members if labelled(e)]
            calls = sorted({labelled(e) for _i, e in decided})
            if decided:
                undecided_dropped += len(members) - len(decided)
            if not decided:
                # Nobody decided any of them, so there is nothing to lose:
                # keep the fullest copy and drop the rest.
                pool = members
            elif len(calls) == 1:
                pool = decided
                kept_decided += 1
            else:
                pool = decided
                kept_decided += 1
                contested.append((key, calls, [
                    {"i": i, "label": e.get("label"),
                     "label_id": e.get("label_id")} for i, e in decided]))

            if len(calls) > 1:
                # Positional, and only where the caller has said which.
                pick = pool[0] if conflicts == "first" else pool[-1]
            else:
                # Richest, then first, so the choice does not depend on
                # dict order and two machines reach the same survivor.
                pick = sorted(pool, key=lambda p: (-len(p[1]), p[0]))[0]
            for i, _e in members:
                if i != pick[0]:
                    drop_idx.add(i)

            rows.append({
                "t": key,
                "n": len(members),
                "labels": [e.get("label") or None for _i, e in members],
                "kept": pick[0] - members[0][0],
                "kept_label": pick[1].get("label"),
                "conflict": len(calls) > 1,
            })

        kept = [e for i, e in enumerate(events) if i not in drop_idx]

        def counts_of(evs):
            out = {}
            for ev in evs:
                k = ev.get("label") or "unspecified"
                out[k] = out.get(k, 0) + 1
            return out

        # What the removed copies carried that the rows replacing them do
        # not. Empty for every entry in this archive, but a dedupe that
        # quietly drops an amplitude should say so rather than be found out.
        survivors = {self._dup_key(e.get("start")) for e in kept}
        lost_fields = set()
        for i in drop_idx:
            ev = events[i]
            key = self._dup_key(ev.get("start"))
            if key not in survivors:
                continue
            mine = next((k for k in kept
                         if self._dup_key(k.get("start")) == key), {})
            lost_fields |= {f for f in ev
                            if f not in mine and f not in self.SNAP_FIELDS}

        versions = rec.get("versions") or []
        cur = max([v.get("v") or 0 for v in versions] or [0])
        report = {
            "entry_id": entry_id,
            "name": rec.get("name"),
            "gid": rec.get("gid"),
            "session_label": rec.get("session_label"),
            "was": len(events),
            "now": len(kept),
            "times": len(times_seen),
            "groups": len(groups),
            "removed": len(drop_idx),
            "kept_decided": kept_decided,
            "undecided_dropped": undecided_dropped,
            "conflicts": len(contested),
            # Every contested time, not a sample. A choice made across
            # fourteen of somebody's calls is made by reading all fourteen.
            "conflict_rows": [
                {"t": t, "calls": calls, "copies": copies}
                for t, calls, copies in contested[:self.PREVIEW_MAX]
            ],
            "rows": rows[:self.PREVIEW_MAX],
            "rows_capped": len(rows) > self.PREVIEW_MAX,
            "policy": conflicts,
            "near_pairs": near,
            "near_ms": self.NEAR_MS,
            "dp": self.DUP_DP,
            "by_label_was": counts_of(events),
            "by_label_now": counts_of(kept),
            "drops_fields": sorted(lost_fields),
            "current_version": cur,
            "next_version": cur + 1,
            "n_versions": len(versions),
            "dry_run": bool(dry_run),
        }
        if lost_fields:
            report["warning"] = (
                "The copies being removed carry %s and the rows kept in "
                "their place do not, so that would go with them."
                % ", ".join(sorted(lost_fields)))
        if not groups:
            report["error"] = (
                "No two events in this set share a time to %d decimal "
                "place(s). There is nothing to collapse." % self.DUP_DP)
            return report
        if contested and conflicts is None:
            # Everything downstream of the unmade choice is withdrawn, not
            # filled in from a fallback. The survivor above defaults to the
            # last copy so the loop has something to hold, and reporting
            # that as the answer would show a caller a mix nobody asked
            # for and let them act on it.
            report["by_label_now"] = None
            for row in report["rows"]:
                if row["conflict"]:
                    row["kept"] = row["kept_label"] = None
            report["error"] = (
                "%d of these times carry two different calls, so collapsing "
                "them would throw one away. Say which copy to keep -- the "
                "first or the last -- and nothing is decided by accident."
                % len(contested))
            return report

        # Derived from what is being removed, not minted at random: two
        # machines collapsing the same doubles converge on one version, and
        # the same derivation makes a repeat recognisable here instead of
        # appending a second identical pass to the history.
        twin = "dd-" + hashlib.sha256(
            ("%s|%s|%s" % (entry_id, conflicts or "-",
                           snap_sha([[e.get("start"), labelled(e)]
                                     for e in kept]))
             ).encode("utf-8")).hexdigest()[:10]
        for ver in versions:
            if ver.get("id") == twin:
                report["already_version"] = ver.get("v")
                report["error"] = (
                    "This exact collapse is already version %s of this set "
                    "-- same survivors, same choice. Delete that version to "
                    "undo it." % ver.get("v"))
                return report
        if dry_run:
            return report

        prov = self.store.provenance() if self.store else {}
        who = (by or prov.get("user") or "unknown").strip()
        counts = counts_of(kept)
        fresh = {
            "id": twin,
            "v": cur + 1,
            "at": _now(),
            "by": who,
            "note": note or (
                "Collapsed %d time(s) that each held more than one record. "
                "%d event(s) removed, %d left; %s"
                % (len(groups), len(drop_idx), len(kept),
                   ("%d of them disagreed about the call and the %s copy "
                    "was kept." % (len(contested), conflicts))
                   if contested else
                   "none of them disagreed about the call.")),
            "n": len(kept),
            "by_label": counts,
            # Nothing was re-decided. Rows went; the decisions on the rows
            # that stayed are the ones that were already there, and putting
            # a relabelling in the history would be inventing one.
            "changed": 0, "gained": 0, "moves": {},
            "lost": len(drop_idx),
            "machine": platform.node(),
            "deduped": {
                "dp": self.DUP_DP,
                "groups": len(groups),
                "removed": len(drop_idx),
                "conflicts": len(contested),
                "policy": conflicts,
                "undecided_dropped": undecided_dropped,
                # The times that were contested and what won, so the pass
                # can be argued with later by somebody who was not here.
                "settled": [[t, calls, next(
                    (r["kept_label"] for r in rows if r["t"] == t), None)]
                    for t, calls, _copies in contested],
            },
        }
        if len(kept) <= self.SNAP_MAX_EVENTS:
            fresh["snap"] = [[ev.get("start"), labelled(ev)] for ev in kept]

        rec["events"] = kept
        rec["versions"] = versions + [fresh]
        rec["version"] = fresh["v"]
        rec["n"] = len(kept)
        rec["by_label"] = counts
        rec.setdefault("history", []).append({
            "at": _now(), "by": who, "changed": ["events"],
            "was_n": len(events), "now_n": len(kept),
            "why": "collapsed %d duplicate time(s)" % len(groups),
        })

        base = self._base_of(rec)
        with _LOCK:
            rec = self.book.write(base, rec)
            self._drop_cache()
        report["version"] = fresh["v"]
        report["version_id"] = fresh["id"]
        return report

    def snapshots(self):
        """Every version snapshot this machine holds.

        (entry_id, v, snap, machine, at) per version that has one. What the
        push sends; the versions without a snapshot are the ones that
        arrived from somewhere else and are still waiting for theirs.
        """
        out = []
        for rec in self.all():
            eid = rec.get("id")
            if not eid:
                continue
            for ver in (rec.get("versions") or []):
                snap = ver.get("snap")
                if not snap:
                    continue
                try:
                    v = int(ver.get("v"))
                except (TypeError, ValueError):
                    continue
                out.append((eid, v, snap,
                            ver.get("machine") or rec.get("machine"),
                            ver.get("at")))
        return out

    def absorb_snapshot(self, entry_id, v, snap, sha=None):
        """Fill in one version's snapshot from another machine.

        Returns "added", "already", "unknown" or a conflict string. Never
        overwrites: a snapshot is immutable, so the only honest outcomes are
        "this machine did not have it" and "it already did".
        """
        if not snap:
            return "unknown"
        rec = self.get(entry_id)
        if not rec:
            return "unknown"
        try:
            v = int(v)
        except (TypeError, ValueError):
            return "unknown"
        hit = None
        for ver in (rec.get("versions") or []):
            if ver.get("v") == v:
                hit = ver
                break
        if hit is None:
            # The metadata has not arrived yet. `bank_entries` is applied
            # before this table for exactly that reason, so this is a
            # genuinely unknown version rather than a race.
            return "unknown"

        if hit.get("snap"):
            if snap_sha(hit["snap"]) == snap_sha(snap):
                # Same content. Clear the flag if it was still set: it
                # is restorable here, and has been all along.
                if hit.pop("snap_elsewhere", None):
                    self._save(rec)
                return "already"
            return ("conflict: %s v%d differs from the copy here (%s vs %s)"
                    % (entry_id, v, snap_sha(hit["snap"])[:12],
                       snap_sha(snap)[:12]))

        if sha and snap_sha(snap) != sha:
            return ("conflict: %s v%d arrived with a digest that does not "
                    "match its own content" % (entry_id, v))

        hit["snap"] = snap
        hit.pop("snap_elsewhere", None)
        self._save(rec)
        return "added"

    def absorb_versions(self, entry_id, versions, current=None):
        """Take on version metadata from another machine.

        Merged by version number, and only ever ADDING: a version this
        machine already knows is left exactly as it is, snapshot included.
        The incoming rows have no snapshot -- they came over Supabase, which
        carries the metadata and not the half-megabyte of snapshots -- so
        overwriting a local version with one would throw away the only copy
        of what it held.

        Returns how many were new, so the sync can report movement rather
        than guess at it.
        """
        rec = self.get(entry_id)
        if not rec:
            return 0
        have = {}
        for v in (rec.get("versions") or []):
            if v.get("v") is not None:
                have[int(v["v"])] = v
        added = 0
        for incoming in (versions or []):
            try:
                num = int(incoming.get("v"))
            except (TypeError, ValueError):
                continue
            if num in have:
                continue
            row = {k: incoming.get(k) for k in
                   ("v", "at", "by", "n", "note", "by_label", "machine")
                   if incoming.get(k) is not None}
            row["v"] = num
            # Said outright on the record: this one arrived without its
            # snapshot, so it can be seen and cited but not restored until
            # the JSON shard carrying it turns up.
            row["snap_elsewhere"] = True
            have[num] = row
            added += 1
        if not added:
            return 0
        rec["versions"] = [have[k] for k in sorted(have)]
        try:
            top = max(have)
        except ValueError:
            top = rec.get("version")
        # The pointer only ever moves forward. A machine that is behind must
        # not drag the current version back for everybody.
        if current is not None:
            try:
                top = max(top, int(current))
            except (TypeError, ValueError):
                pass
        if top is not None and (rec.get("version") or 0) < top:
            rec["version"] = top
        self._save(rec)
        return added

    def edit_version(self, entry_id, v, patch):
        """Change what a version says about itself, not what it holds."""
        rec = self.get(entry_id)
        if not rec:
            raise BankError("No such entry.")
        hit = None
        for ver in rec.get("versions") or []:
            if ver.get("v") == v:
                hit = ver
                break
        if hit is None:
            raise BankError("That entry has no version %s." % v)

        who = (self.store.provenance().get("user") if self.store else None)
        changed = []
        if "note" in patch:
            new = (patch.get("note") or "").strip()
            if new != (hit.get("note") or ""):
                hit["note"] = new
                changed.append("note")
        if "title" in patch:
            new = (patch.get("title") or "").strip()
            if new != (hit.get("title") or ""):
                if new:
                    hit["title"] = new
                else:
                    hit.pop("title", None)
                changed.append("title")
        if "archived" in patch:
            want = bool(patch.get("archived"))
            if want != bool(hit.get("archived")):
                hit["archived"] = want
                if not want:
                    hit.pop("archived", None)
                changed.append("archived" if want else "unarchived")
        if not changed:
            return rec, []
        # An edited note says so. The point of a note is that somebody
        # wrote it at the time; one quietly rewritten later is worth less,
        # and pretending otherwise is the kind of thing this store exists
        # not to do.
        hit.setdefault("edits", []).append(
            {"at": _now(), "by": who, "changed": changed})
        self._save(rec)
        return rec, changed

    @shards.atomic
    def delete_version(self, entry_id, v):
        """Remove one version from the history.

        For an ordinary version the events stay put -- the history loses a
        row and nothing else changes.

        For a CORRECTION the events do not stay put, because leaving them
        would leave the set on the recording's clock with nothing recording
        that it is. Deleting the correction restores the times from the
        version below it and clears the basis stamp, which is what makes the
        session go back to showing an unresolved segment issue: `patched` is
        computed from that stamp and from nothing else.
        """
        rec = self.get(entry_id)
        if not rec:
            raise BankError("No such entry.")
        vs = rec.get("versions") or []
        keep = [x for x in vs if x.get("v") != v]
        if len(keep) == len(vs):
            raise BankError("That entry has no version %s." % v)
        if not keep:
            raise BankError(
                "That is the only version this entry has. Delete the whole "
                "entry instead, or archive the version.")

        gone = next(x for x in vs if x.get("v") == v)
        undo = None
        if gone.get("retimed"):
            # Only the correction that is actually in force needs undoing.
            # Deleting a superseded one is a history edit and nothing more.
            top = max(x.get("v") or 0 for x in vs)
            if (gone.get("v") or 0) == top:
                undo = self._undo_retime(rec, gone, keep)

        rec["versions"] = keep
        # Numbers are never reused and never shifted: the next bank counts
        # from the highest that has ever existed, so a deleted v2 does not
        # come back as a different v2.
        rec["version"] = max(x.get("v") or 0 for x in keep)
        rec.setdefault("history", []).append({
            "at": _now(),
            "by": (self.store.provenance().get("user") if self.store else None),
            "changed": ["versions"] + (["events", "time_basis"]
                                       if undo else []),
            "why": ("deleted version %s" % v) + (
                ", restoring the times it moved from v%s and clearing the "
                "basis stamp" % undo["restored_from"] if undo else ""),
        })
        self._save(rec)
        if undo:
            rec = dict(rec)
            rec["undo"] = undo
        return rec

    def _undo_retime(self, rec, gone, keep):
        """Put the times back the way the correction found them.

        Refuses rather than half-undoing. A set whose correction has been
        deleted but whose times are still corrected reads as un-corrected to
        everything that looks at it, which would make the segment warning
        say "nobody has dealt with this" about a set that has silently had
        the shift applied -- the exact confusion this area exists to
        prevent.
        """
        below = [x for x in keep if (x.get("v") or 0) < (gone.get("v") or 0)]
        src = None
        for ver in sorted(below, key=lambda x: x.get("v") or 0, reverse=True):
            if ver.get("snap"):
                src = ver
                break
        if src is None:
            raise BankError(
                "Deleting this correction would have to put %d event time(s) "
                "back, and no earlier version on this machine carries a "
                "snapshot to put them back from. Nothing was deleted: a set "
                "whose correction is gone but whose times are still shifted "
                "reads as uncorrected everywhere, which is worse than "
                "either state." % len(rec.get("events") or []))

        events, dropped = self.events_at(rec, src.get("v"))
        counts = {}
        for ev in events:
            key = ev.get("label") or "unspecified"
            counts[key] = counts.get(key, 0) + 1
        rec["events"] = events
        rec["n"] = len(events)
        rec["by_label"] = counts

        # The stamp goes back to whatever is true once this version is gone.
        # `basis_at` reads the remaining history, so a set corrected twice
        # and un-corrected once lands on the earlier correction rather than
        # on nothing.
        top = max([x.get("v") or 0 for x in keep] or [0])
        was = dict(rec.get("time_basis") or {})
        basis = self.basis_at({"versions": keep,
                               "time_basis": {"converted_from":
                                              was.get("converted_from")}},
                              top)
        if basis:
            # A fresh stamp, not the old one with its `kind` swapped. The
            # correction's `gap_map_sha`, `at` and `by` describe a
            # conversion that has just been undone, and carrying them
            # forward would leave the set claiming to have been converted
            # against a map it is no longer the result of.
            rec["time_basis"] = {
                "kind": basis,
                "tool": "jarvis.retime/1",
                "at": _now(),
                "by": (self.store.provenance().get("user")
                       if self.store else None),
                "restored_from_version": src.get("v"),
                "note": "Restored when the correction at v%s was deleted."
                        % gone.get("v"),
            }
        if not basis:
            # Nothing left says this set was converted, so nothing should.
            # This is what flips the session back to an unresolved segment
            # issue: `patched` is derived from this key existing.
            rec.pop("time_basis", None)
        return {"restored_from": src.get("v"), "n": len(events),
                "dropped_fields": dropped, "was_basis": was.get("kind"),
                "now_basis": basis}

    @shards.atomic
    def _save(self, rec):
        """Write a record back under the id it already has."""
        base = self._base_for_id(rec["id"]) or self._base_of(rec)
        out = self.book.write(base, rec)
        self._drop_cache()
        return out

    def delete(self, entry_id):
        base = self._base_for_id(entry_id)
        if not base:
            return False
        with _LOCK:
            gone = self.book.erase(base)
            self._drop_cache()
        return bool(gone)

    def _base_for_id(self, entry_id):
        for base in self.book.bases():
            if base.endswith("_" + str(entry_id)):
                return base
        return None

    def _path_of(self, entry_id):
        base = self._base_for_id(entry_id)
        return self.book.mine(base) if base else None

    # ------------------------------------------------------------------
    # Matching an entry to an open recording
    # ------------------------------------------------------------------
    def for_session(self, identity):
        """Entries banked against this recording, best match first.

        Same tiering as bad channels: an exact identity beats mouse+session,
        which beats nothing. An entry filed on one machine has to be findable
        from another, where the path is different.
        """
        gid = (identity or {}).get("gid")
        key = (identity or {}).get("key")
        loose = (identity or {}).get("loose_key")
        mouse = (identity or {}).get("mouse")
        session = (identity or {}).get("session")

        exact, strong, weak = [], [], []
        for rec in self.summaries():
            # The permanent id first. `session_key` carries the recording's
            # header start time, so matching on it means a re-read header or
            # a clock that moved by a second stops an entry being recognised
            # as belonging to the recording it was banked against. The gid
            # never moves, which is the whole reason it exists.
            if gid and rec.get("gid") == gid:
                exact.append(dict(rec, match="exact"))
            elif key and rec.get("session_key") == key:
                exact.append(dict(rec, match="exact"))
            elif loose and rec.get("session_loose_key") == loose:
                strong.append(dict(rec, match="strong"))
            elif (mouse is not None and rec.get("mouse") == mouse
                  and session is not None and rec.get("session") == session):
                strong.append(dict(rec, match="strong"))
            elif mouse is not None and rec.get("mouse") == mouse:
                weak.append(dict(rec, match="weak"))
        return exact + strong + weak


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, path)
