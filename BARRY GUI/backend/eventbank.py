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
import uuid

from . import shards
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
        self._cache = None
        self._stamp = None

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def _fingerprint(self):
        """Changes when any entry does, so a colleague's pull is picked up."""
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
        return (count, newest, total)

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
        """
        out = []
        for rec in self.all():
            row = {k: v for k, v in rec.items() if k != "events"}
            if row.get("versions"):
                row["versions"] = [
                    {k: v for k, v in ver.items() if k != "snap"}
                    for ver in row["versions"]]
            out.append(row)
        return out

    def get(self, entry_id):
        for rec in self.all():
            if rec.get("id") == entry_id:
                return rec
        return None

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
            clean.append(item)
        if not clean:
            raise BankError("None of those events had a usable time.")
        clean.sort(key=lambda e: e["start"])

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
        moves, changed, gained, lost = {}, 0, 0, 0
        if prior:
            was = {}
            for ev in prior.get("events") or []:
                try:
                    was[round(float(ev["start"]), 4)] = ev.get("label")
                except (TypeError, ValueError, KeyError):
                    continue
            for ev in clean:
                try:
                    key = round(float(ev["start"]), 4)
                except (TypeError, ValueError):
                    continue
                if key not in was:
                    gained += 1
                    continue
                before, after = was.pop(key), ev.get("label")
                if before != after:
                    changed += 1
                    step = "%s → %s" % (before or "undecided",
                                             after or "undecided")
                    moves[step] = moves.get(step, 0) + 1
            lost = len(was)

        moved = ((not prior) or changed or gained or lost
                 or prior.get("n") != rec["n"]
                 or (prior.get("by_label") or {}) != counts)
        if moved:
            # A detector's export is version zero, always. It is the thing
            # curation gets done *to* rather than a round of curation, so
            # numbering it 1 would make the first real pass v2 and leave the
            # history claiming a pass that never happened.
            first_import = (not versions) and not rec["specified"]
            fresh = {
                # Highest so far plus one, not the count -- the import sits
                # at zero and would otherwise make the numbering skip.
                "v": 0 if first_import
                     else max([v.get("v") or 0 for v in versions] or [0]) + 1,
                # A stable key, so two machines' histories union instead
                # of one replacing the other.
                "id": uuid.uuid4().hex[:12],
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
            self._cache = None
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
            self._cache = None
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
            self._cache = None
            n += hit
        return n

    @shards.atomic
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
        """Remove one version from the history. The events stay put."""
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
        rec["versions"] = keep
        # Numbers are never reused and never shifted: the next bank counts
        # from the highest that has ever existed, so a deleted v2 does not
        # come back as a different v2.
        rec["version"] = max(x.get("v") or 0 for x in keep)
        rec.setdefault("history", []).append({
            "at": _now(),
            "by": (self.store.provenance().get("user") if self.store else None),
            "changed": ["versions"],
            "why": "deleted version %s" % v,
        })
        self._save(rec)
        return rec

    @shards.atomic
    def _save(self, rec):
        """Write a record back under the id it already has."""
        base = self._base_for_id(rec["id"]) or self._base_of(rec)
        out = self.book.write(base, rec)
        self._cache = None
        return out

    def delete(self, entry_id):
        base = self._base_for_id(entry_id)
        if not base:
            return False
        with _LOCK:
            gone = self.book.erase(base)
            self._cache = None
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
