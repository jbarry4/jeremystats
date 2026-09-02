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
        try:
            names = sorted(os.listdir(self.root))
        except OSError:
            names = []
        for name in names:
            if not name.endswith(".json"):
                continue
            rec = _read_json(os.path.join(self.root, name))
            if rec:
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
            "added": {
                "by": who,
                "at": _now(),
                "machine": entry.get("machine") or platform.node(),
            },
        }

        name = "%s_%s_%s_%s.json" % (
            _slug(rec["project"], "unfiled"),
            _slug("m%s" % rec["mouse"] if rec["mouse"] is not None else "m", "m"),
            _slug("s%s" % rec["session"] if rec["session"] is not None else "s", "s"),
            rec["id"])
        path = os.path.join(self.root, name)
        with _LOCK:
            _write_json(path, rec)
            self._cache = None
        rec["path"] = path
        return rec

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
            _write_json(self._path_of(entry_id), rec)
            self._cache = None
        return rec

    def delete(self, entry_id):
        path = self._path_of(entry_id)
        if not path:
            return False
        with _LOCK:
            try:
                os.remove(path)
            except OSError:
                return False
            self._cache = None
        return True

    def _path_of(self, entry_id):
        try:
            for name in os.listdir(self.root):
                if name.endswith(entry_id + ".json"):
                    return os.path.join(self.root, name)
        except OSError:
            pass
        return None

    # ------------------------------------------------------------------
    # Matching an entry to an open recording
    # ------------------------------------------------------------------
    def for_session(self, identity):
        """Entries banked against this recording, best match first.

        Same tiering as bad channels: an exact identity beats mouse+session,
        which beats nothing. An entry filed on one machine has to be findable
        from another, where the path is different.
        """
        key = (identity or {}).get("key")
        loose = (identity or {}).get("loose_key")
        mouse = (identity or {}).get("mouse")
        session = (identity or {}).get("session")

        exact, strong, weak = [], [], []
        for rec in self.summaries():
            if key and rec.get("session_key") == key:
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
