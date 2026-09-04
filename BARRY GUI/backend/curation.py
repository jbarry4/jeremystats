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
import platform
import time
import uuid
from datetime import datetime, timezone

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


def _eid():
    return "e" + uuid.uuid4().hex[:10]


def _when(stamp):
    """A stamp as something comparable, whatever timezone wrote it.

    These are local times with an offset -- "2026-09-04T13:51:40-0400" -- so
    comparing them as strings gets the wrong answer between two machines in
    different timezones, and "the newer decision wins" would quietly mean
    "the one further east wins". Parsed, with anything unreadable sorting
    oldest so a decision with a real stamp always beats one without.
    """
    if not stamp:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        got = datetime.fromisoformat(str(stamp))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if got.tzinfo is None:
        got = got.replace(tzinfo=timezone.utc)
    return got


def _own_review(ev):
    """Make sure the decision already on a candidate is one of its reviews.

    Decisions made before candidates kept a review list -- and any that
    arrived through an import -- carry only `label`, `by` and `at`. Without
    backfilling that as a review, absorbing somebody else's call leaves the
    candidate looking like she is the only person who ever saw it, and "two
    people agreed" can never be true of anything.
    """
    lab = ev.get("label")
    if not lab:
        return
    who = (ev.get("by") or "").strip() or "unknown"
    for r in (ev.get("reviews") or []):
        if (r.get("by") or "") == who:
            return
    ev["reviews"] = sorted(
        (ev.get("reviews") or []) + [
            {"by": who, "label": lab, "at": ev.get("at") or _now()}],
        key=lambda r: _when(r.get("at")))


def _remember_review(ev, who, label, at):
    """Note that somebody said what this candidate is.

    Several people looking the same candidate over is the normal case -- one
    person goes through a session and another spot-checks it -- and "two
    people agreed" is worth more than one person's call. One row per person,
    holding their latest call, so a reviewer changing their own mind does not
    look like two reviewers.
    """
    who = (who or "").strip() or "unknown"
    rows = [r for r in (ev.get("reviews") or [])
            if (r.get("by") or "") != who]
    rows.append({"by": who, "label": label, "at": at or _now()})
    rows.sort(key=lambda r: _when(r.get("at")))
    ev["reviews"] = rows


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

    HANDOFF_SCHEMA = 1

    def handoff(self, sets):
        """One file carrying everything needed to move decisions.

        The whole set rather than only the decided candidates, because the
        candidates nobody has reached yet are what tells the other side how
        much is left -- and because a set that arrives missing half its
        candidates looks finished when it is not.
        """
        prov = self.store.provenance() if self.store else {}
        out = []
        for rec in sets:
            out.append({
                "gid": rec.get("gid"),
                "kind": rec.get("kind"),
                "name": rec.get("name"),
                "session_label": rec.get("session_label"),
                "labels": rec.get("labels"),
                "source": rec.get("source"),
                "created": rec.get("created"),
                "updated": rec.get("updated"),
                "events": [
                    {k: v for k, v in e.items() if not k.startswith("_")}
                    for e in (rec.get("events") or [])
                ],
            })
        return {
            "schema": self.HANDOFF_SCHEMA,
            "what": "BARRY curation handoff",
            "from": {
                "who": prov.get("user"),
                "machine": prov.get("machine") or platform.node(),
                "at": _now(),
            },
            "sets": out,
        }

    def absorb(self, bundle, prefer=None):
        """Take another machine's decisions into the local sets.

        `prefer` of "theirs" or "mine" settles a straight disagreement;
        the default settles it by which decision was made later, which is
        what you want when the two machines have simply been worked on at
        different times.
        """
        if not isinstance(bundle, dict) or "sets" not in bundle:
            raise CurationError(
                "That is not a curation handoff file -- it has no `sets`. "
                "Use the file saved by Hand off, not an export CSV.")
        schema = bundle.get("schema")
        if schema and int(schema) > self.HANDOFF_SCHEMA:
            raise CurationError(
                "That handoff was written by a newer BARRY (schema %s, this "
                "one reads %s). Update this copy first rather than importing "
                "it half-understood." % (schema, self.HANDOFF_SCHEMA))

        who_from = (bundle.get("from") or {}).get("who") or "another machine"
        report = {"from": bundle.get("from") or {}, "sets": []}
        for incoming in bundle.get("sets") or []:
            report["sets"].append(
                self._absorb_one(incoming, who_from, prefer))
        return report

    def _absorb_one(self, incoming, who_from, prefer):
        gid = incoming.get("gid")
        kind = incoming.get("kind")
        # Four different things happen to a decision and rolling them into
        # one count is how "8 taken" comes out of 1 blank filled, 5
        # disagreements and 2 new candidates.
        line = {"gid": gid, "kind": kind,
                "name": incoming.get("name"),
                "session_label": incoming.get("session_label"),
                "created_set": False,
                "added": 0,        # candidates we did not have
                "taken": 0,        # ours was undecided, so hers now stands
                "agreed": 0,       # we had both said the same thing
                "overruled": 0,    # we disagreed and hers is newer
                "kept": 0,         # we disagreed and ours stands
                "disagreed": [], "unchanged": 0}
        if not gid or kind not in KINDS:
            line["error"] = "That set says it is a %r set, which this BARRY " \
                            "does not know about." % (kind,)
            return line

        theirs = incoming.get("events") or []
        rec = self._read(gid, kind)
        if not rec:
            # Nothing here to merge into: take the set wholesale. Their
            # decisions come with it, which is the point.
            rec = {
                "schema": SCHEMA, "gid": gid, "kind": kind,
                "name": incoming.get("name")
                        or (KINDS[kind]["name"] + " candidates"),
                "session_label": incoming.get("session_label"),
                "labels": incoming.get("labels") or vocabulary(kind),
                "source": incoming.get("source") or {},
                "events": sorted(
                    [dict(e) for e in theirs],
                    key=lambda e: e.get("start") or 0),
                "created": incoming.get("created")
                           or (self.store.provenance() if self.store
                               else {"at": _now()}),
                "imports": [],
            }
            for e in rec["events"]:
                _own_review(e)
            line["created_set"] = True
            line["added"] = len(rec["events"])
            line["taken"] = sum(1 for e in rec["events"] if e.get("label"))
        else:
            mine = rec.get("events") or []
            by_id = {e.get("id"): e for e in mine if e.get("id")}
            # Falling back to the time, because a set built independently on
            # the other machine has its own ids for the same candidates.
            # Four decimals is a tenth of a millisecond -- tight enough that
            # two real candidates are never confused, loose enough to
            # survive a float round trip through JSON.
            by_t = {}
            for e in mine:
                try:
                    by_t.setdefault(round(float(e["start"]), 4), e)
                except (TypeError, ValueError, KeyError):
                    continue

            for ev in theirs:
                hit = by_id.get(ev.get("id"))
                if hit is None:
                    try:
                        hit = by_t.get(round(float(ev["start"]), 4))
                    except (TypeError, ValueError, KeyError):
                        hit = None
                if hit is None:
                    fresh = dict(ev)
                    fresh.setdefault("id", _eid())
                    _own_review(fresh)
                    mine.append(fresh)
                    by_id[fresh["id"]] = fresh
                    line["added"] += 1
                    continue

                their_label = ev.get("label")
                if their_label is None:
                    line["unchanged"] += 1
                    continue
                # Ours first, so a candidate two people have looked at can
                # actually say both of their names.
                _own_review(hit)
                _remember_review(hit, ev.get("by") or who_from, their_label,
                                 ev.get("at"))
                if not hit.get("label"):
                    hit["label"] = their_label
                    hit["by"] = ev.get("by") or who_from
                    hit["at"] = ev.get("at") or _now()
                    line["taken"] += 1
                elif hit["label"] == their_label:
                    line["agreed"] += 1
                else:
                    take = (prefer == "theirs" or
                            (prefer != "mine"
                             and _when(ev.get("at")) > _when(hit.get("at"))))
                    line["disagreed"].append({
                        "id": hit.get("id"), "start": hit.get("start"),
                        "mine": hit["label"], "mine_by": hit.get("by"),
                        "theirs": their_label,
                        "theirs_by": ev.get("by") or who_from,
                        "took": "theirs" if take else "mine",
                    })
                    if take:
                        hit["label"] = their_label
                        hit["by"] = ev.get("by") or who_from
                        hit["at"] = ev.get("at") or _now()
                        line["overruled"] += 1
                    else:
                        line["kept"] += 1

            rec["events"] = sorted(mine, key=lambda e: e.get("start") or 0)

        rec.setdefault("imports", []).append({
            "at": _now(), "n": line["added"], "skipped": 0,
            "source": {"kind": "handoff", "from": who_from,
                       "taken": line["taken"], "agreed": line["agreed"],
                       "overruled": line["overruled"],
                       "kept": line["kept"],
                       "disagreed": len(line["disagreed"])},
        })
        self._write(rec)
        line["progress"] = self.progress(rec)
        return line

    def with_decisions(self):
        """Every set anybody has actually decided something in."""
        out = []
        for rec in self.all():
            if any(e.get("label") for e in (rec.get("events") or [])):
                out.append(rec)
        return out

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
        if label is not None:
            _own_review(hit)
            _remember_review(hit, who, label, _now())
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
        """The set grouped by category.

        No longer how banking works -- `bank_one` writes one entry for the
        set and every event carries its label, because four entries per
        session whose names differed only in the last word could not show a
        decision moving between two of them. Kept for the per-category CSV,
        where a group per file is what is wanted.
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

    def bank_one(self, rec, only_specified=True):
        """The whole set as one bankable list, every event carrying its label.

        Not split by category. A category is a property of an event, and
        splitting on it produced four entries per session with near-identical
        names -- while making it impossible to see a decision move from one
        category to another, which is what re-curating a set mostly does.
        """
        names = {l["id"]: l["name"] for l in (rec.get("labels") or [])}
        out = []
        counts = {}
        for e in rec.get("events") or []:
            lab = e.get("label")
            if lab is None and only_specified:
                continue
            item = {"start": e["start"]}
            if e.get("end") is not None:
                item["end"] = e["end"]
            if e.get("channel") is not None:
                item["channel"] = e["channel"]
            item["label"] = names.get(lab, lab) if lab else "unspecified"
            item["label_id"] = lab or "unspecified"
            if e.get("by"):
                item["by"] = e["by"]
            # Who has looked this one over, so a spot-check that agreed is
            # not indistinguishable from nobody having checked.
            revs = e.get("reviews") or []
            if len(revs) > 1:
                item["reviewers"] = [r.get("by") for r in revs if r.get("by")]
            out.append(item)
            key = lab or "unspecified"
            counts[key] = counts.get(key, 0) + 1
        out.sort(key=lambda x: x["start"])
        return {
            "n": len(out),
            "events": out,
            "by_label": counts,
            "label_names": names,
        }

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
