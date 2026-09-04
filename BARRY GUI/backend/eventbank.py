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


class BankError(Exception):
    """A refusal the user should read, not a crash."""


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _slug(text, fallback="x"):
    out = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-").lower()
    return out[:40] or fallback


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
        """Every entry without its event list, for browsing."""
        return [{k: v for k, v in rec.items() if k != "events"}
                for rec in self.all()]

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
            for key in ("channel", "amplitude", "label"):
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
            "source": {
                "pipeline": pipeline,
                "run_id": entry.get("run_id"),
                "file": entry.get("source_file"),
                "parameters": entry.get("parameters") or {},
                "detector": entry.get("detector"),
            },
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
            fresh = {
                "v": len(versions) + 1,
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
                fresh["snap"] = [[ev.get("start"), ev.get("label")]
                                 for ev in clean]
            versions.append(fresh)
            # Older snapshots go; their counts and their notes stay, so the
            # history is still complete, only less finely comparable far
            # back.
            for old in versions[:-self.SNAP_VERSIONS]:
                old.pop("snap", None)
        elif versions:
            # Nothing changed, so no new version -- but say it was checked,
            # because "banked again and it was identical" is information.
            versions[-1].setdefault("confirmed", [])
            versions[-1]["confirmed"].append({"at": _now(), "by": who})
        rec["versions"] = versions
        rec["version"] = versions[-1]["v"] if versions else 1

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
