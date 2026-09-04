"""
curation.py -- Going through candidate events one at a time and saying what
each one is.

Two jobs in the lab look identical once you stop looking at the biology:

    Dentate spikes    is this a dentate spike, or garbage?
    IEDs              is this discharge solid, or a sputter?

Both are: here is a list of times a detector thought something happened, look
at each one in the recording, press a key, move on. Both want undo, both want
to know how far through you are, and both want the answer to survive being
carried to another machine. So this is one engine with a vocabulary per kind
rather than two tools that drift apart.

What is stored, per (recording, kind):

    events    every candidate, each with a label or None
    labels    the vocabulary in force when it was made, copied in

The vocabulary is copied into the record on purpose. If the lab later adds a
category, sets curated last year keep meaning what they meant -- rather than
silently acquiring a fifth option nobody used, or losing a category that was
renamed.

Everything is keyed by the recording's global id, not its path, so a set
curated on the rig is the same set on the laptop.
"""
from __future__ import annotations

import json
import os
import time
import uuid

from . import shards

SCHEMA = 1

# Unspecified is the absence of a label, not a label. A candidate nobody has
# looked at and a candidate someone decided was garbage are different facts,
# and collapsing them loses the only number that matters while curating: how
# many are left.
UNSPECIFIED = None

# Keys the mode itself needs. A category cannot have one of these, however
# good a mnemonic it is: "sputter" wanted `p`, which is also "previous", so
# pressing p to go back a candidate labelled it as a sputter instead. The
# navigation has to be the one thing that always does what it says, so the
# reservation is enforced here rather than left to whoever adds the next
# vocabulary.
RESERVED_KEYS = frozenset({"n", "p", "u", "escape", "backspace",
                           "arrowleft", "arrowright"})

KINDS = {
    "ds": {
        "id": "ds",
        "name": "Dentate spikes",
        "blurb": "Candidate dentate spikes, one at a time: is it one, or is "
                 "it not?",
        "labels": [
            {"id": "spike", "name": "Dentate Spike", "keys": ["1", "d"],
             "color": "#2f9e6e", "good": True},
            {"id": "garbage", "name": "Garbage", "keys": ["2", "g"],
             "color": "#dc2626"},
            {"id": "flag", "name": "Flag", "keys": ["3", "f"],
             "color": "#E5A823"},
            {"id": "review", "name": "Flag for Deep Review",
             "keys": ["4", "r"], "color": "#8b5cf6"},
        ],
    },
    "ied": {
        "id": "ied",
        "name": "IEDs — solid or sputter",
        "blurb": "Candidate interictal discharges: solid, sputter, or "
                 "neither.",
        "labels": [
            {"id": "solid", "name": "Solid", "keys": ["1", "s"],
             "color": "#2f9e6e", "good": True},
            # `t` rather than the obvious `p`: p is "previous".
            {"id": "sputter", "name": "Sputter", "keys": ["2", "t"],
             "color": "#3b82f6", "good": True},
            {"id": "garbage", "name": "Garbage", "keys": ["3", "g"],
             "color": "#dc2626"},
            {"id": "flag", "name": "Flag", "keys": ["4", "f"],
             "color": "#E5A823"},
        ],
    },
}


class CurationError(Exception):
    pass


def _usable_keys(keys):
    return [k for k in (keys or []) if k.lower() not in RESERVED_KEYS]


def vocabulary(kind):
    """A kind's categories, with any key the mode needs stripped out.

    Applied on the way out rather than at definition time so that sets saved
    with an older vocabulary -- which may still carry a reserved key -- are
    cleaned up when they are read, instead of quietly breaking navigation for
    whoever opens them next.
    """
    out = []
    for lab in KINDS[kind]["labels"]:
        out.append(dict(lab, keys=_usable_keys(lab.get("keys"))))
    return out


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Curation:
    def __init__(self, logs_dir, store):
        self.dir = os.path.join(logs_dir, "curation")
        # Decisions merge per candidate, so two people working through the
        # same set from opposite ends both keep every call they made.
        self.book = shards.Book(self.dir, {
            "events": shards.BYID,
            "created": shards.FIRST,
        }, store)
        self.book.absorb_legacy()
        self.store = store
        os.makedirs(self.dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def base(self, gid, kind):
        return shards.safe_base(gid, "".join(
            c for c in str(kind) if c.isalnum()))

    def path(self, gid, kind):
        return self.book.mine(self.base(gid, kind))

    def _read(self, gid, kind):
        return self.book.read(self.base(gid, kind))

    def _write(self, rec):
        rec["updated"] = self.store.provenance() if self.store else {"at": _now()}
        return self.book.write(self.base(rec["gid"], rec["kind"]), rec)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def get(self, gid, kind):
        if kind not in KINDS:
            raise CurationError("Unknown kind %r." % kind)
        rec = self._read(gid, kind)
        if rec:
            # An old set may carry a key the mode has since reserved.
            for lab in rec.get("labels") or []:
                lab["keys"] = _usable_keys(lab.get("keys"))
        return rec

    def all(self):
        return self.book.all()

    @staticmethod
    def progress(rec):
        """How far through, and what the answers were.

        `left` is the number that matters while curating and is the reason
        unspecified is not itself a label.
        """
        evs = rec.get("events") or []
        by = {}
        done = 0
        for e in evs:
            lab = e.get("label")
            if lab:
                done += 1
                by[lab] = by.get(lab, 0) + 1
        return {
            "total": len(evs),
            "specified": done,
            "left": len(evs) - done,
            "by_label": by,
            "percent": round(100.0 * done / len(evs), 1) if evs else 0.0,
        }

    def summary(self, rec):
        kind = KINDS.get(rec.get("kind")) or {}
        return {
            "gid": rec.get("gid"),
            "kind": rec.get("kind"),
            "kind_name": kind.get("name") or rec.get("kind"),
            "name": rec.get("name"),
            "session_label": rec.get("session_label"),
            "source": rec.get("source") or {},
            "created": rec.get("created") or {},
            "updated": rec.get("updated") or {},
            "labels": rec.get("labels") or kind.get("labels") or [],
            "progress": self.progress(rec),
        }

    def summaries(self):
        return [self.summary(r) for r in self.all()]

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def create(self, gid, kind, events, name=None, source=None,
               session_label=None, replace=False):
        """Start a curation set from a list of candidate times.

        Every candidate arrives unspecified. That is the whole point: the
        import says "a detector thought these were interesting", and the
        curation says what they actually are. Conflating the two is how a
        detector's guesses end up in a figure as findings.
        """
        if kind not in KINDS:
            raise CurationError("Unknown kind %r." % kind)
        if not gid:
            raise CurationError(
                "A curation set has to belong to a recording. Open the "
                "recording first so it has a permanent id.")

        clean = []
        for i, ev in enumerate(events or []):
            try:
                start = float(ev.get("start") if isinstance(ev, dict) else ev)
            except (TypeError, ValueError):
                continue
            item = {
                "id": "e" + uuid.uuid4().hex[:10],
                "start": round(start, 6),
                "label": UNSPECIFIED,
            }
            if isinstance(ev, dict):
                for k in ("end", "channel", "amplitude", "note"):
                    if ev.get(k) is not None:
                        item[k] = ev[k]
                if ev.get("label") and ev["label"] in self._label_ids(kind):
                    # An import that already carries a decision keeps it.
                    item["label"] = ev["label"]
            clean.append(item)

        if not clean:
            raise CurationError("None of those candidates had a usable time.")
        clean.sort(key=lambda e: e["start"])

        existing = self._read(gid, kind)
        if existing and not replace:
            # Adding to a set in progress: keep the decisions already made,
            # and only take candidates at times not already covered.
            seen = {round(e["start"], 3) for e in (existing.get("events") or [])}
            fresh = [e for e in clean if round(e["start"], 3) not in seen]
            existing["events"] = sorted(
                (existing.get("events") or []) + fresh,
                key=lambda e: e["start"])
            existing.setdefault("imports", []).append({
                "at": _now(), "n": len(fresh), "skipped": len(clean) - len(fresh),
                "source": source or {},
            })
            return self._write(existing), len(fresh)

        rec = {
            "schema": SCHEMA,
            "gid": gid,
            "kind": kind,
            "name": name or (KINDS[kind]["name"] + " candidates"),
            "session_label": session_label,
            # Copied in, so a later change to the vocabulary cannot rewrite
            # what an old set meant.
            "labels": vocabulary(kind),
            "source": source or {},
            "events": clean,
            "created": self.store.provenance() if self.store else {"at": _now()},
            "imports": [{"at": _now(), "n": len(clean), "skipped": 0,
                         "source": source or {}}],
        }
        return self._write(rec), len(clean)

    def _label_ids(self, kind):
        return {l["id"] for l in KINDS[kind]["labels"]}

    def label(self, gid, kind, event_id, label, note=None):
        """Say what one candidate is. `label` of None puts it back."""
        rec = self._read(gid, kind)
        if not rec:
            raise CurationError("No curation set for that recording.")
        valid = {l["id"] for l in (rec.get("labels") or [])}
        if label is not None and label not in valid:
            raise CurationError(
                "%r is not one of this set's categories (%s)."
                % (label, ", ".join(sorted(valid))))

        who = (self.store.provenance() if self.store else {}).get("user")
        hit = None
        for e in rec.get("events") or []:
            if e.get("id") == event_id:
                hit = e
                break
        if not hit:
            raise CurationError("No candidate %r in this set." % event_id)

        hit["label"] = label
        if note is not None:
            hit["note"] = note
        if label is None:
            hit.pop("by", None)
            hit.pop("at", None)
        else:
            hit["by"] = who
            hit["at"] = _now()
        self._write(rec)
        return hit, self.progress(rec)

    def label_many(self, gid, kind, pairs):
        """Several at once, for a sweep like 'everything left is garbage'."""
        rec = self._read(gid, kind)
        if not rec:
            raise CurationError("No curation set for that recording.")
        valid = {l["id"] for l in (rec.get("labels") or [])}
        who = (self.store.provenance() if self.store else {}).get("user")
        index = {e["id"]: e for e in (rec.get("events") or [])}
        n = 0
        for eid, label in (pairs or {}).items():
            e = index.get(eid)
            if not e:
                continue
            if label is not None and label not in valid:
                continue
            e["label"] = label
            if label is None:
                e.pop("by", None)
                e.pop("at", None)
            else:
                e["by"] = who
                e["at"] = _now()
            n += 1
        self._write(rec)
        return n, self.progress(rec)

    def rename(self, gid, kind, name):
        rec = self._read(gid, kind)
        if not rec:
            raise CurationError("No curation set for that recording.")
        rec["name"] = (name or "").strip() or rec.get("name")
        return self._write(rec)

    def delete(self, gid, kind):
        return bool(self.book.erase(self.base(gid, kind)))

    # ------------------------------------------------------------------
    # Out
    # ------------------------------------------------------------------
    def bank_entries(self, rec, only_specified=True):
        """One Event Bank entry per category.

        Split by category rather than banked as one lump: the reason to curate
        was to separate them, and a bank entry called "candidates" with a
        label field buried in each event is not separated in any way anyone
        can filter on.
        """
        by = {}
        for e in rec.get("events") or []:
            lab = e.get("label")
            if lab is None and only_specified:
                continue
            by.setdefault(lab or "unspecified", []).append(e)

        names = {l["id"]: l["name"] for l in (rec.get("labels") or [])}
        out = []
        for lab, evs in by.items():
            out.append({
                "label": lab,
                "label_name": names.get(lab, lab.title()),
                "n": len(evs),
                "events": [{"start": e["start"],
                            **({"end": e["end"]} if e.get("end") is not None else {}),
                            **({"channel": e["channel"]} if e.get("channel") is not None else {}),
                            "label": names.get(lab, lab)}
                           for e in evs],
            })
        out.sort(key=lambda x: -x["n"])
        return out

    def rows(self, rec):
        """Flat rows, for a CSV."""
        names = {l["id"]: l["name"] for l in (rec.get("labels") or [])}
        out = []
        for e in rec.get("events") or []:
            out.append({
                "gid": rec.get("gid"),
                "session": rec.get("session_label") or "",
                "kind": rec.get("kind"),
                "start_s": e.get("start"),
                "channel": e.get("channel", ""),
                "amplitude_uv": e.get("amplitude", ""),
                "label": names.get(e.get("label"), "") if e.get("label")
                         else "unspecified",
                "label_id": e.get("label") or "",
                "note": (e.get("note") or "").replace("\n", " "),
                "curated_by": e.get("by") or "",
                "curated_at": e.get("at") or "",
            })
        return out


CSV_COLUMNS = ("gid", "session", "kind", "start_s", "channel", "amplitude_uv",
               "label", "label_id", "note", "curated_by", "curated_at")
