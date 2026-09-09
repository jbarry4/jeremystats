"""
cloudsync.py -- Turning BARRY's records into rows, and back.

Push and pull are not symmetric, on purpose.

**Two-way**: sessions, the paths and sightings under them, mice, the event
bank, curation sets and every individual decision in them, layer sheets and
every channel label, result filing, storyboards, presets, shared preferences.
These are things two people edit, so they have to travel both ways.

**Push only**: runs, activity, errors. They are append-only history. Pulling
another machine's activity into this machine's day log would be writing
somebody else's actions into a file that says it is yours, and the combined
history is a query -- `select * from activity order by at desc` -- rather than
something to copy around. So it goes up, and it is read from up there.

Set-like things become rows rather than JSON arrays: one row per path, per
sighting, per curated event, per labelled channel. That is what lets two
people curate the same set from opposite ends and both keep their work, which
is the thing a jsonb blob cannot do however carefully you merge it.
"""
from __future__ import annotations

import os

from . import cloud, shards

BUCKET = "results"

# Two-way tables, in dependency order: a child row whose parent is not there
# yet is a foreign key violation, so sessions go before everything that
# references them.
ORDER = [
    "machines", "sessions", "session_paths", "session_sightings", "mice",
    "bank_entries", "curation_sets", "curation_events", "curation_reviews",
    "layer_sheets",
    "layer_labels", "storyboards", "results", "presets", "prefs",
    # Both directions. A report filed on the rig has to reach the desktop,
    # and a triage decision made on the desktop has to reach the rig --
    # otherwise two people each see their own half of the list and neither
    # of them can tell.
    "feedback", "feedback_notes",
    # So somebody added on one computer is pickable on another without
    # waiting for a git pull.
    "people",
]
PUSH_ONLY = ["runs", "activity", "errors", "error_marks"]


# For a record that has never been edited and so carries no timestamp: a
# built-in filter preset, a figure nobody has tagged. `now()` would be the
# obvious fallback and is quietly wrong -- it makes the row look new on every
# single push, so it is re-sent forever. A fixed stamp is sent once and then
# never again, until somebody actually changes it.
UNSTAMPED = "1970-01-01T00:00:00+00:00"


def _prov(rec, key="updated"):
    p = rec.get(key) or {}
    return p if isinstance(p, dict) else {}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


class Sync:
    """Everything BARRY knows, in both directions."""

    def __init__(self, logs_dir, store, bank=None, curate=None, layers=None,
                 mice=None, results=None, repo_root=None, feedback=None,
                 people=None):
        self.logs = os.path.abspath(logs_dir)
        self.store = store
        self.bank = bank
        self.curate = curate
        self.layers = layers
        self.mice = mice
        self.results = results
        self.feedback = feedback
        self.people = people
        self.repo_root = repo_root
        self.cloud = cloud.Cloud(self.logs, store)
        self.machine = shards.machine_id()
        from . import tombs
        self.tombs = tombs.Tombs(self.logs, store)

    # ==================================================================
    # Local records -> rows
    # ==================================================================
    def rows_machines(self):
        prov = self.store.provenance()
        return [{
            "id": self.machine,
            "hostname": prov.get("machine"),
            "os": prov.get("os"),
            "git_user": prov.get("user"),
            "last_seen": cloud.now(),
            "updated_at": cloud.now(),
        }]

    # The made-up recordings exist on every machine unconditionally, so
    # pushing them would put two fake sessions -- and their curation -- into
    # a database the whole lab reads. They are excluded everywhere by gid.
    DEMO_PREFIX = "demo-"

    def _is_demo(self, rec):
        gid = str((rec or {}).get("gid") or "")
        return gid.startswith(self.DEMO_PREFIX)

    def rows_sessions(self):
        sessions, paths, sightings = [], [], []
        for rec in self.store.all_sessions():
            if self._is_demo(rec):
                continue
            gid = rec.get("gid")
            if not gid:
                continue          # nothing to hang it off yet
            up = _prov(rec, "updated")
            cr = _prov(rec, "created")
            sessions.append({
                "gid": gid,
                "key": rec.get("key"),
                "loose_key": rec.get("loose_key"),
                "mouse": _int(rec.get("mouse")),
                "session": _int(rec.get("session")),
                "label": rec.get("label"),
                "project": rec.get("project"),
                "project_source": rec.get("project_source"),
                "cohort": rec.get("cohort"),
                "grp": rec.get("group"),
                "started_at": cloud.ts(rec.get("start")),
                "condition": rec.get("condition"),
                "note": rec.get("note"),
                "bad_channels": sorted({int(b) for b in
                                        (rec.get("bad_channels") or [])}),
                "bad_channels_note": rec.get("bad_channels_note"),
                # Which hippocampus. Carried in the lab's feeder sheet all
                # along, which meant it was true only for whoever had the
                # spreadsheet open -- and a left and a right CA1 recording
                # are different recordings.
                "hemisphere": rec.get("hemisphere"),
                "hemisphere_source": rec.get("hemisphere_source"),
                "ripple_channel": _int(rec.get("ripple_channel")),
                "fissure_channel": _int(rec.get("fissure_channel")),
                "hilus_channel": _int(rec.get("hilus_channel")),
                "extraction_note": rec.get("extraction_note"),
                "needs_processing": rec.get("needs_processing"),
                "reference_channels_source":
                    rec.get("reference_channels_source"),
                "n_channels": _int(rec.get("n_channels")),
                "fs": _num(rec.get("fs")),
                "duration_s": _num(rec.get("duration_s")),
                "has_video": bool(rec.get("has_video")),
                "converted": bool(rec.get("converted")),
                "first_seen_by": rec.get("first_seen_by"),
                "retired": bool(rec.get("retired")),
                "merged_into": rec.get("merged_into"),
                "split_from": rec.get("split_from"),
                "event_classes": rec.get("event_classes") or {},
                "spike_labels": rec.get("spike_labels") or {},
                "bookmarks": rec.get("bookmarks") or [],
                "created_at": cloud.ts(cr.get("at")) or cloud.now(),
                "created_by": cr.get("user"),
                "updated_at": cloud.ts(up.get("at")) or cloud.now(),
                "updated_by": up.get("user") or self.machine,
            })
            for p in (rec.get("paths") or []):
                paths.append({
                    "gid": gid, "path": str(p), "machine": self.machine,
                    "deleted_at": None,
                    "updated_at": cloud.ts(up.get("at")) or cloud.now(),
                })
            for mach, s in (rec.get("seen") or {}).items():
                s = s if isinstance(s, dict) else {}
                sightings.append({
                    "gid": gid, "machine": str(mach),
                    "seen_at": cloud.ts(s.get("at")) or cloud.now(),
                    "path": s.get("path"), "scan_id": s.get("scan_id"),
                    "root": s.get("root"),
                    "updated_at": cloud.ts(s.get("at")) or cloud.now(),
                })
        return {"sessions": sessions, "session_paths": paths,
                "session_sightings": sightings}

    def rows_mice(self):
        out = []
        for rec in (self.mice.all() if self.mice else []):
            if rec.get("mouse") is None:
                continue
            up, cr = _prov(rec, "updated"), _prov(rec, "created")
            out.append({
                "project": rec.get("project") or "Unfiled",
                "mouse": _int(rec.get("mouse")),
                "attrs": rec.get("attrs") or {},
                "note": rec.get("note"),
                "created_at": cloud.ts(cr.get("at")) or cloud.now(),
                "created_by": cr.get("user"),
                "updated_at": cloud.ts(up.get("at")) or cloud.now(),
                "updated_by": up.get("user") or self.machine,
            })
        return {"mice": out}

    def rows_bank(self):
        out = []
        for rec in (self.bank.all() if self.bank else []):
            if self._is_demo(rec):
                continue
            added = rec.get("added") or {}
            out.append({
                "id": rec.get("id"),
                "gid": rec.get("gid"),
                "project": rec.get("project"),
                "mouse": _int(rec.get("mouse")),
                "session": _int(rec.get("session")),
                "session_key": rec.get("session_key"),
                "session_label": rec.get("session_label"),
                "session_path": rec.get("session_path"),
                "recording_start": cloud.ts(rec.get("recording_start")),
                "duration_s": _num(rec.get("duration_s")),
                "type": rec.get("type"),
                "type_name": rec.get("type_name"),
                "name": rec.get("name"),
                "note": rec.get("note"),
                "units": rec.get("units"),
                "n": _int(rec.get("n")) or len(rec.get("events") or []),
                "specified": bool(rec.get("specified")),
                "curation_label": rec.get("curation_label"),
                "source": rec.get("source") or {},
                "added_by": added.get("by"),
                "added_at": cloud.ts(added.get("at")),
                "added_machine": added.get("machine"),
                "history": rec.get("history") or [],
                "events": rec.get("events") or [],
                "updated_at": cloud.ts(added.get("at")) or cloud.now(),
                "updated_by": added.get("by") or self.machine,
            })
        return {"bank_entries": out}

    def rows_curation(self):
        sets, events, reviews = [], [], []
        for rec in (self.curate.all() if self.curate else []):
            gid, kind = rec.get("gid"), rec.get("kind")
            if not gid or not kind:
                continue
            if self._is_demo(rec):
                continue
            set_id = "%s__%s" % (gid, kind)
            up, cr = _prov(rec, "updated"), _prov(rec, "created")
            sets.append({
                "id": set_id, "gid": gid, "kind": kind,
                "name": rec.get("name"),
                "session_label": rec.get("session_label"),
                "source": rec.get("source") or {},
                "imports": rec.get("imports") or [],
                "vocabulary": rec.get("labels") or rec.get("vocabulary") or [],
                # Whose set it is and whether anybody has it open. Without
                # these, "Rain has m33 s8 open" is a fact that stops at the
                # machine she is sitting at.
                "assignee": rec.get("assignee"),
                "is_open": bool(rec.get("open")),
                "opened_at": cloud.ts(rec.get("opened_at")),
                "opened_by": rec.get("opened_by"),
                "closed_at": cloud.ts(rec.get("closed_at")),
                "archived": bool(rec.get("archived")),
                "archived_at": cloud.ts(rec.get("archived_at")),
                "archived_by": rec.get("archived_by"),
                "created_at": cloud.ts(cr.get("at")) or cloud.now(),
                "created_by": cr.get("user"),
                "updated_at": cloud.ts(up.get("at")) or cloud.now(),
                "updated_by": up.get("user") or self.machine,
            })
            for ev in (rec.get("events") or []):
                # A decision carries its own who and when, so it can be
                # ordered against somebody else's decision on the same event.
                at = cloud.ts(ev.get("at"))
                events.append({
                    "set_id": set_id,
                    "event_id": ev.get("id"),
                    "start_s": _num(ev.get("start")),
                    "end_s": _num(ev.get("end")),
                    "channel": _int(ev.get("channel")),
                    "amplitude": _num(ev.get("amplitude")),
                    "label": ev.get("label") or "unspecified",
                    "decided_by": ev.get("by"),
                    "decided_at": at,
                    "updated_at": at or cloud.ts(cr.get("at")) or cloud.now(),
                })
                for r in (ev.get("reviews") or []):
                    who = (r.get("by") or "").strip()
                    if not who or not r.get("label"):
                        continue
                    rat = cloud.ts(r.get("at"))
                    reviews.append({
                        "set_id": set_id,
                        "event_id": ev.get("id"),
                        "reviewer": who,
                        "label": r["label"],
                        "at": rat,
                        "updated_at": rat or at or cloud.now(),
                    })
        return {"curation_sets": sets, "curation_events": events,
                "curation_reviews": reviews}

    def rows_layers(self):
        sheets, labels = [], []
        for rec in (self.layers.all() if self.layers else []):
            if self._is_demo(rec):
                continue
            gid = rec.get("gid")
            if not gid:
                continue
            up, cr = _prov(rec, "updated"), _prov(rec, "created")
            stamp = cloud.ts(up.get("at")) or cloud.now()
            sheets.append({
                "gid": gid,
                "session_label": rec.get("session_label"),
                "channels": [int(c) for c in (rec.get("channels") or [])],
                "regions": rec.get("regions") or [],
                # The history, as a snapshot per version. Without it a
                # colleague pulling this sheet gets the labels but no way to
                # tell an import from a correction.
                "versions": rec.get("versions") or [],
                "created_at": cloud.ts(cr.get("at")) or cloud.now(),
                "created_by": cr.get("user"),
                "updated_at": stamp,
                "updated_by": up.get("user") or self.machine,
            })
            for ch, region in (rec.get("labels") or {}).items():
                labels.append({
                    "gid": gid, "channel": _int(ch), "region": region,
                    "set_by": up.get("user") or self.machine,
                    "updated_at": stamp,
                })
        return {"layer_sheets": sheets, "layer_labels": labels}

    def rows_results(self):
        out = []
        for r in (self.results.catalog() if self.results else []):
            rel = r.get("rel") or r.get("key")
            if not rel:
                continue
            up = _prov(r, "updated")
            out.append({
                "id": r.get("id"),
                "rel_path": rel,
                "title": r.get("title") or r.get("name"),
                "kind": r.get("kind"),
                "type": r.get("type"),
                "bytes": _int(r.get("bytes")),
                "gid": r.get("gid"),
                "session_key": r.get("session_key"),
                "session_label": r.get("session_label"),
                "run_id": r.get("run_id"),
                "script": r.get("script"),
                "machine": r.get("machine"),
                "author": r.get("author"),
                "made_at": cloud.ts(r.get("at") or r.get("made_at")),
                # The real directory it sits in under Results/. Filing
                # in the GUI moves the file, so this is the folder you would
                # see if you opened Results/ in Explorer.
                "folder": r.get("folder"),
                "tags": list(r.get("tags") or []),
                "notes": r.get("notes"),
                "starred": bool(r.get("starred")),
                # An untagged figure has no `updated`; its own mtime is a
                # stable stand-in, where now() would re-send it forever.
                "updated_at": (cloud.ts(up.get("at"))
                               or cloud.ts(r.get("created"))
                               or cloud.ts(r.get("mtime")) or UNSTAMPED),
                "updated_by": up.get("user") or self.machine,
            })
        return {"results": out}

    def rows_storyboards(self):
        out = []
        for d in (self.results.list_decks() if self.results else []):
            deck = self.results.get_deck(d["id"]) or {}
            up, cr = _prov(deck, "updated"), _prov(deck, "created")
            out.append({
                "id": deck.get("id") or d.get("id"),
                "title": deck.get("title"),
                "slides": deck.get("slides") or [],
                "n_slides": len(deck.get("slides") or []),
                "created_at": cloud.ts(cr.get("at")) or cloud.now(),
                "created_by": cr.get("user"),
                "updated_at": cloud.ts(up.get("at")) or cloud.now(),
                "updated_by": up.get("user") or self.machine,
            })
        return {"storyboards": out}

    def rows_runs(self):
        out = []
        for r in self.store.all_runs():
            prov = r.get("provenance") or {}
            sess = r.get("session") or {}
            out.append({
                "id": r.get("id"),
                "script": r.get("script"),
                "label": r.get("label"),
                "lang": r.get("lang"),
                "status": r.get("status"),
                "gid": sess.get("gid"),
                "session_key": sess.get("key"),
                "session_label": sess.get("label"),
                "parameters": r.get("parameters") or {},
                "outputs": r.get("outputs") or [],
                "started_at": cloud.ts(prov.get("at") or r.get("started")),
                "ended_at": cloud.ts(r.get("ended")),
                "duration_s": _num(r.get("duration_s")),
                "machine": prov.get("machine"),
                "git_user": prov.get("user"),
                "updated_at": cloud.ts(prov.get("at")) or cloud.now(),
            })
        return {"runs": out}

    def rows_activity(self, limit=200000):
        out = []
        for a in self.store.list_activity(limit=limit):
            sess = a.get("session") or {}
            out.append({
                "id": a.get("id"),
                "at": cloud.ts(a.get("at")) or cloud.now(),
                "action": a.get("action") or "unknown",
                "detail": a.get("detail") or {},
                "gid": sess.get("gid"),
                "session_key": sess.get("key"),
                "view": a.get("view"),
                "git_user": a.get("user"),
                "machine": a.get("machine") or a.get("shard"),
                "updated_at": cloud.ts(a.get("at")) or cloud.now(),
            })
        return {"activity": [r for r in out if r["id"]]}

    def rows_errors(self, limit=200000):
        out = []
        for e in self.store.list_errors(limit=limit):
            out.append({
                "id": e.get("id"),
                "at": cloud.ts(e.get("at")) or cloud.now(),
                "where_": e.get("where"),
                "message": e.get("message"),
                "detail": (str(e.get("detail"))[:20000]
                           if e.get("detail") else None),
                "context": e.get("context") or {},
                "machine": e.get("machine") or e.get("shard"),
                "git_user": e.get("user"),
                "updated_at": cloud.ts(e.get("at")) or cloud.now(),
            })
        marks = []
        for sig, m in (self.store.resolved_errors() or {}).items():
            m = m if isinstance(m, dict) else {}
            marks.append({
                "signature": sig,
                "resolved": True,
                "note": m.get("note"),
                "marked_by": m.get("by"),
                "machine": m.get("machine") or self.machine,
                "updated_at": cloud.ts(m.get("at")) or cloud.now(),
            })
        return {"errors": [r for r in out if r["id"]], "error_marks": marks}

    def rows_presets(self):
        out = []
        for kind in ("filters", "imports", "layouts"):
            for p in self.store.get_presets(kind):
                saved = p.get("saved") or {}
                out.append({
                    "kind": kind,
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "payload": {k: v for k, v in p.items()
                                if k not in ("saved",)},
                    "builtin": bool(p.get("builtin")),
                    # Built-ins have no `saved` block: see UNSTAMPED.
                    "updated_at": cloud.ts(saved.get("at")) or UNSTAMPED,
                    "updated_by": saved.get("user") or self.machine,
                })
        return {"presets": [r for r in out if r["id"]]}

    def rows_feedback(self):
        """Reports and their triage, both directions.

        The state and the notes are what a second person contributes, and
        they are the reason this has to be shared rather than push-only:
        somebody has to be able to mark a bug planned and have the person
        who filed it see that.
        """
        rows, notes = [], []
        for rec in (self.feedback.all() if self.feedback else []):
            rid = rec.get("id")
            if not rid:
                continue
            ctx = rec.get("context") or {}
            rows.append({
                "id": rid,
                "kind": rec.get("kind") or "bug",
                "state": rec.get("state") or "open",
                "title": rec.get("title"),
                "body": rec.get("detail") or "",
                "wants": rec.get("wants") or "",
                "context": ctx,
                "view": ctx.get("view"),
                "session_label": ctx.get("session_label") or ctx.get("session"),
                "gid": ctx.get("gid"),
                "shots": rec.get("screenshots") or [],
                "state_by": rec.get("state_by"),
                "state_at": cloud.ts(rec.get("state_at")),
                "machine": rec.get("machine") or rec.get("shard"),
                "created_at": cloud.ts(rec.get("at")) or cloud.now(),
                "created_by": rec.get("by"),
                "updated_at": (cloud.ts(rec.get("state_at"))
                               or cloud.ts(rec.get("at")) or cloud.now()),
                "updated_by": rec.get("state_by") or rec.get("by"),
            })
            for i, n in enumerate(rec.get("notes") or []):
                at = cloud.ts(n.get("at"))
                rows_id = "%s-%02d" % (rid, i)
                notes.append({
                    "id": rows_id,
                    "feedback_id": rid,
                    "body": n.get("text") or "",
                    "note_by": n.get("by") or "",
                    "at": at or cloud.now(),
                    "updated_at": at or cloud.now(),
                })
        return {"feedback": rows, "feedback_notes": notes}

    def rows_people(self):
        """The roster, so a name typed on one machine is pickable on another."""
        if not self.people:
            return {"people": []}
        try:
            got = self.people.roster(self.curate, self.bank)
        except Exception:                            # noqa: BLE001
            return {"people": []}
        out = []
        for row in (got.get("people") or []) + (got.get("not_people") or []):
            out.append({
                "name": row.get("name"),
                "email": row.get("email"),
                "is_person": bool(row.get("is_person")),
                "seen": row.get("counts") or {},
                # The other spellings that are this same person. Local-only
                # until now, which meant a merge held until the next pull and
                # then came apart: the shared roster still had the old name,
                # so `_apply_people` wrote it back every cycle and the merge
                # looked like it had failed.
                "aliases": sorted(row.get("aliases") or []) or None,
                # Whether they should still be offered work. Shared, because
                # that is a lab-wide question -- and because a local-only
                # flag would be written back by the next pull.
                "archived": bool(row.get("archived")) or None,
                "last_seen": cloud.now(),
                "updated_at": cloud.now(),
            })
        return {"people": out}

    def rows_prefs(self):
        from .store import PREFS_LOCAL
        prefs = self.store.get_prefs() or {}
        local = {k: v for k, v in prefs.items() if k in PREFS_LOCAL}
        shared = {k: v for k, v in prefs.items()
                  if k not in PREFS_LOCAL and not k.startswith("_")}
        return {"prefs": [{
            "machine": self.machine,
            "local": local,
            "shared": shared,
            "updated_at": cloud.now(),
        }]}

    # ==================================================================
    # Push
    # ==================================================================
    def collect(self, include_history=True):
        """Every table's rows, ready to send."""
        rows = {"machines": self.rows_machines()}
        rows.update(self.rows_sessions())
        rows.update(self.rows_mice())
        rows.update(self.rows_bank())
        rows.update(self.rows_curation())
        rows.update(self.rows_layers())
        rows.update(self.rows_storyboards())
        rows.update(self.rows_results())
        rows.update(self.rows_presets())
        rows.update(self.rows_prefs())
        rows.update(self.rows_feedback())
        rows.update(self.rows_people())
        if include_history:
            rows.update(self.rows_runs())
            rows.update(self.rows_activity())
            rows.update(self.rows_errors())
        return rows

    ON_CONFLICT = {
        "session_paths": "gid,path",
        "session_sightings": "gid,machine",
        "mice": "project,mouse",
        "curation_events": "set_id,event_id",
        "curation_reviews": "set_id,event_id,reviewer",
        "layer_labels": "gid,channel",
        "presets": "kind,id",
    }

    def push(self, include_history=True, on_progress=None, dry_run=False,
             full=False):
        """Send up what has changed since the last successful push.

        The database would drop the no-ops anyway -- barry_keep_newest sees to
        that -- so a full push every couple of minutes is *correct*. It is
        just four thousand rows of it, forever, for a lab that changes a
        handful a day. So the default is incremental, and `full=True` says
        send everything, which is what the migration does.

        A row with no usable stamp is always sent. Better to re-send
        something harmlessly than to have one row that can never travel
        because its timestamp was unreadable.
        """
        since = None if full else (self.cloud.state() or {}).get("last_push")
        rows = self.collect(include_history=include_history)
        started = cloud.now()
        sent, report = 0, {}
        for table in ORDER + (PUSH_ONLY if include_history else []):
            batch = rows.get(table) or []
            if since:
                batch = [r for r in batch
                         if not r.get("updated_at")
                         or str(r["updated_at"]) > since]
            report[table] = len(batch)
            if on_progress:
                on_progress(table, len(batch))
            if batch and not dry_run:
                sent += self.cloud.upsert(
                    table, batch, on_conflict=self.ON_CONFLICT.get(table))
        if not dry_run:
            # The time the push *started*: anything written while it ran must
            # be caught next time rather than skipped.
            self.cloud.save_state({"last_push": started})
        return {"sent": sent, "tables": report, "dry_run": dry_run,
                "since": since, "full": bool(full)}

    # ==================================================================
    # Files
    # ==================================================================
    def upload_results(self, on_progress=None, force=False):
        """Put the figures in the bucket.

        The repo keeps its copy -- a figure viewable on GitHub beside the log
        entry that produced it is the point of committing them. This is so a
        machine that has not pulled can still show one, and so the repo is not
        the only copy of anything.
        """
        if not self.results:
            return {"uploaded": 0, "skipped": 0, "failed": []}
        done, skipped, failed = 0, 0, []
        state = self.cloud.state()
        seen = {} if force else (state.get("uploaded") or {})
        for r in self.results.catalog():
            path, rel = r.get("path"), (r.get("rel") or r.get("key"))
            if not path or not rel or not os.path.isfile(path):
                continue
            try:
                sig = "%d:%d" % (os.path.getsize(path),
                                 int(os.path.getmtime(path)))
            except OSError:
                continue
            if seen.get(rel) == sig:
                skipped += 1
                continue
            try:
                self.cloud.upload(BUCKET, rel, path)
                self.cloud.upsert("results", [{
                    "id": r.get("id"), "rel_path": rel,
                    "storage_path": rel, "storage_at": cloud.now(),
                    "updated_at": cloud.now(),
                }])
                seen[rel] = sig
                done += 1
                if on_progress:
                    on_progress(rel, done)
            except cloud.CloudError as exc:
                failed.append({"rel": rel, "error": str(exc)[:200]})
        self.cloud.save_state({"uploaded": seen})
        return {"uploaded": done, "skipped": skipped, "failed": failed}

    def push_deletions(self):
        """Carry local deletions up, as tombstones rather than DELETEs.

        Soft, because a hard delete is indistinguishable from a row somebody
        else has not fetched yet -- and because a session with curated events
        hanging off it should not evaporate on a stray click. `retired` is
        already how BARRY hides a session it has been told to forget.
        """
        if not self.tombs:
            return {"marked": 0}
        rows = self.tombs.pending()
        if not rows:
            return {"marked": 0}
        stamp = cloud.now()
        done, marked = [], 0
        table_for = {
            "session": ("sessions", "gid"),
            "result": ("results", "rel_path"),
            "bank": ("bank_entries", "id"),
            "curation": ("curation_sets", "id"),
            "layers": ("layer_sheets", "gid"),
            "deck": ("storyboards", "id"),
        }
        for row in rows:
            spec = table_for.get(row.get("kind"))
            if not spec:
                continue
            table, col = spec
            values = {"updated_at": stamp}
            # A session is retired, not deleted: things hang off it.
            if table == "sessions":
                values["retired"] = True
            else:
                values["deleted_at"] = stamp
            try:
                # PATCH, not upsert: there is nothing to insert, and an
                # insert would need a primary key this does not have.
                hit = self.cloud.patch_rows(
                    table, "%s=eq.%s" % (col, row["id"]), values)
                marked += len(hit) if hit else 0
                # Marked, or not there to mark -- either way it is said.
                done.append(row)
            except cloud.CloudError:
                continue          # try again next sync
        self.tombs.mark_synced(done)
        return {"marked": marked}

    def pull_files(self, on_progress=None, limit=None):
        """Fetch figures this machine does not have.

        The other half of the folder mirroring: a laptop that has never
        pulled the repo still ends up with the actual PNGs in the actual
        folders, laid out exactly as the Results view shows them. Only what
        is missing is fetched -- a file already on disk is left alone, since
        it is the same bytes and re-downloading it would be pure noise.
        """
        if not self.results:
            return {"downloaded": 0, "skipped": 0, "failed": []}
        out_dir = self.results.outputs_dir
        rows = self.cloud.select_all(
            "results", "storage_path=not.is.null&deleted_at=is.null")
        got, skipped, failed = 0, 0, []
        for r in rows:
            rel = r.get("rel_path")
            key = r.get("storage_path") or rel
            if not rel:
                continue
            # Deleted or moved away here. Downloading it would recreate the
            # file in the folder somebody moved it out of -- which is exactly
            # how six figures became twelve.
            if self.tombs and self.tombs.is_deleted("result", rel):
                skipped += 1
                continue
            dest = os.path.join(out_dir, *rel.split("/"))
            if os.path.isfile(dest):
                skipped += 1
                continue
            try:
                self.cloud.download(BUCKET, key, dest)
                got += 1
                if on_progress:
                    on_progress(rel, got)
                if limit and got >= limit:
                    break
            except cloud.CloudError as exc:
                failed.append({"rel": rel, "error": str(exc)[:200]})
        if got:
            self.results._cache["at"] = 0
        return {"downloaded": got, "skipped": skipped, "failed": failed}

    def mirror_bank(self, repo_dir):
        """Write the Event Bank out as folders anyone can open.

        Derived and deterministic, so it is safe to commit and every machine
        produces the same bytes. See bankmirror.py.
        """
        from . import bankmirror
        if not self.bank:
            return {"written": 0}
        return bankmirror.BankMirror(repo_dir, self.bank,
                                     mice=self.mice,
                                     store=self.store).rebuild()

    # ==================================================================
    # Pull
    # ==================================================================
    def pull(self, since=None, on_progress=None, on_table=None):
        """Bring down what other machines have changed, and apply it locally.

        Runs, activity and the raw error log stay push-only, and for a
        reason worth keeping: they are append-only records of what happened
        on one machine, and copying somebody else's into this machine's day
        log would be writing their actions into a file that says it is
        yours.

        Error *triage* is different and does come down. "This one is
        handled, by her, with this note" is shared state about a shared
        list, not a record of an event -- and while it only went up, two
        people re-triaged the same errors forever without either of them
        being able to tell.

        Feedback comes down for the same reason: a report filed on the rig
        that never reaches the desktop is not a report, it is a note to
        self.
        """
        state = self.cloud.state()
        since = since or state.get("last_pull")
        q = ("updated_at=gt.%s" % since) if since else ""
        applied, newest = {}, since

        def fetch(table):
            # Said before the request, not after it: the point of announcing
            # a table is that it is the one currently taking the time. The
            # pull is the slow half of a sync -- fifteen round trips -- and
            # it used to report the single word "pulling" for all of them.
            if on_table:
                on_table(table)
            rows = self.cloud.select_all(table, q)
            for r in rows:
                got = r.get("updated_at")
                if got and (not newest_holder[0] or got > newest_holder[0]):
                    newest_holder[0] = got
            return rows

        newest_holder = [newest]

        sessions = fetch("sessions")
        applied["sessions"] = self._apply_sessions(sessions)
        applied["session_paths"] = self._apply_paths(fetch("session_paths"))
        applied["mice"] = self._apply_mice(fetch("mice"))
        applied["bank_entries"] = self._apply_bank(fetch("bank_entries"))
        applied["curation"] = self._apply_curation(
            fetch("curation_sets"), fetch("curation_events"))
        applied["layers"] = self._apply_layers(
            fetch("layer_sheets"), fetch("layer_labels"))
        applied["results"] = self._apply_results(fetch("results"))
        applied["storyboards"] = self._apply_decks(fetch("storyboards"))
        applied["feedback"] = self._apply_feedback(
            fetch("feedback"), fetch("feedback_notes"))
        applied["people"] = self._apply_people(fetch("people"))
        applied["errors"] = self._apply_errors(fetch("errors"))
        applied["error_marks"] = self._apply_error_marks(fetch("error_marks"))
        if on_progress:
            on_progress(applied)

        self.cloud.save_state({"last_pull": newest_holder[0] or cloud.now()})
        return {"applied": applied, "since": since,
                "through": newest_holder[0]}

    # -- appliers -------------------------------------------------------
    def _apply_feedback(self, rows, notes):
        """Reports and their triage, from every machine.

        A report this machine has never seen is written as a report of its
        own, marked with the machine that filed it. One it already has is
        left alone except for the state and the notes, which is exactly what
        `update` writes as an overlay -- so absorbing somebody's triage goes
        through the same path as making it here, and cannot corrupt the file
        the report was filed in.
        """
        if not self.feedback:
            return 0
        by_id = {}
        for n in (notes or []):
            fid = n.get("feedback_id")
            if fid:
                by_id.setdefault(fid, []).append(n)
        n_applied = 0
        for r in (rows or []):
            rid = r.get("id")
            if not rid or r.get("deleted_at"):
                continue
            try:
                if self.feedback.absorb(r, by_id.get(rid) or []):
                    n_applied += 1
            except Exception as exc:                 # noqa: BLE001
                self.store.record_error(
                    "cloud.pull.feedback", str(exc), None, {"id": rid})
        return n_applied

    def _apply_people(self, rows):
        """The roster. Somebody added on one computer becomes pickable here.

        Only the hand-written details -- email, role, initials. The counts
        are compiled from this machine's own data every time the roster is
        read, so pulling somebody else's would be importing a number that
        does not describe anything local.
        """
        if not self.people:
            return 0

        # What this machine already says, so an unchanged row can be
        # skipped. Writing one restamps it, and a restamped row is pushed
        # back up as though it were an edit -- which is how the same seven
        # people came down and went up again on every single cycle, between
        # every pair of machines, forever.
        n = 0
        have = {}
        try:
            # The roster compiles counts from local data as well, which is
            # more work than this needs -- but it is the only reader, and a
            # wrong skip would be worse than a slow one.
            #
            # `roster()` returns a DICT of {people, not_people, me}, and
            # iterating it walks the keys -- so this loop used to bind `row`
            # to the string "people", raise AttributeError on `.get`, hit the
            # except below, and leave `have` empty. Which meant the skip
            # never skipped, and the write loop this guard exists to stop was
            # still running: 11 of 11 unchanged rows written on every cycle.
            got = self.people.roster() or {}
            listed = ((got.get("people") or [])
                      + (got.get("not_people") or [])
                      if isinstance(got, dict) else list(got))
            for row in listed:
                have[(row.get("name") or "").strip().lower()] = row
        except Exception:                            # noqa: BLE001
            have = {}

        # Every spelling this machine has been told is somebody else. Built
        # once: a row per cloud person and a lookup per row would re-read the
        # roster file for each of them.
        aliased = {}
        for row in have.values():
            for other in (row.get("aliases") or []):
                aliased[str(other).strip().lower()] = row.get("name")

        self.merge_reverts = 0
        for r in (rows or []):
            name = (r.get("name") or "").strip()
            if not name:
                continue
            # The old spelling of somebody who has been merged. Writing it
            # would re-create the entry the merge removed, which is exactly
            # what used to happen on every cycle.
            keep = aliased.get(name.lower())
            if keep and keep.strip().lower() != name.lower():
                self.merge_reverts += 1
                continue
            want = {"email": r.get("email"), "role": r.get("role"),
                    "initials": r.get("initials"), "orcid": r.get("orcid")}
            # Aliases are unioned, not overwritten. Two people merging
            # different spellings on different machines are both right, and
            # last-write-wins would have one of them silently undo the
            # other.
            theirs = [a for a in (r.get("aliases") or []) if a]
            # Last-write-wins, unlike aliases: "she is back" is a correction
            # of "she has left", not a second opinion to be unioned with it.
            # `None` means the row says nothing, which is not the same as
            # saying False -- a machine that has not run migration 09 sends
            # nothing here and must not un-archive anybody.
            put_away = r.get("archived")
            mine = have.get(name.lower())
            if mine is not None:
                # Only the fields this row actually carries, and only when
                # they differ. A row that says nothing new is not news.
                same = True
                for k, v in want.items():
                    if v is None:
                        continue
                    if (str(mine.get(k) or "").strip()
                            != str(v or "").strip()):
                        same = False
                        break
                # A different archive state is news.
                if same and put_away is not None:
                    if bool(mine.get("archived")) != bool(put_away):
                        same = False
                # An alias this machine has not got is news even when every
                # other field matches.
                if same and theirs:
                    here = {str(a).strip().lower()
                            for a in (mine.get("aliases") or [])}
                    if any(str(a).strip().lower() not in here
                           for a in theirs):
                        same = False
                if same:
                    continue
            merged = None
            if theirs:
                have_now = {str(a).strip().lower(): str(a).strip()
                            for a in ((mine or {}).get("aliases") or [])}
                for a in theirs:
                    have_now.setdefault(str(a).strip().lower(),
                                        str(a).strip())
                merged = sorted(have_now.values())
            more = {}
            if merged:
                more["aliases"] = merged
            if put_away is not None:
                more["archived"] = bool(put_away)
            try:
                self.people.add(name, r.get("email"), None,
                                role=r.get("role"),
                                initials=r.get("initials"),
                                orcid=r.get("orcid"), **more)
                n += 1
            except TypeError:
                # A People without the `aliases` field. The rest of the row
                # is still worth applying.
                try:
                    self.people.add(name, r.get("email"), None,
                                    role=r.get("role"),
                                    initials=r.get("initials"),
                                    orcid=r.get("orcid"))
                    n += 1
                except Exception:                    # noqa: BLE001
                    continue
            except Exception:                        # noqa: BLE001
                continue
        return n

    def _apply_errors(self, rows):
        """Other machines' errors, filed under the machine that had them.

        The store keeps one append-only log per machine per day, so an error
        from the rig is written to the rig's file for that day and nothing
        pretends it happened here. Written by id, so a re-pull of the same
        row does not double it.
        """
        n = 0
        for r in (rows or []):
            rid = r.get("id")
            machine = r.get("machine")
            # Ours already, by definition -- it is where the row came from.
            if not rid or not machine or machine == self.machine:
                continue
            try:
                if self.store.absorb_error({
                        "id": rid,
                        "at": r.get("at"),
                        "where": r.get("where_"),
                        "message": r.get("message"),
                        "detail": r.get("detail"),
                        "context": r.get("context") or {},
                        "machine": machine,
                        "user": r.get("git_user"),
                }):
                    n += 1
            except Exception:                        # noqa: BLE001
                continue
        return n

    def _apply_error_marks(self, rows):
        """Which error signatures somebody has marked handled.

        Newest wins per signature, and only when it is newer than what this
        machine already says -- so re-triaging one locally is not undone by
        the next pull of an older row.
        """
        have = self.store.resolved_errors() or {}
        n = 0
        for r in (rows or []):
            sig = r.get("signature")
            if not sig:
                continue
            mine = have.get(sig) or {}
            theirs_at = r.get("updated_at") or ""
            mine_at = cloud.ts(mine.get("at")) or ""
            if mine and mine_at >= theirs_at:
                continue
            if r.get("resolved"):
                if not mine:
                    self.store.resolve_error(sig, True, r.get("note") or "")
                    n += 1
            elif mine:
                self.store.resolve_error(sig, False)
                n += 1
        return n

    def _ident_for(self, gid, row=None):
        """The identity dict the local store keys on, for a gid."""
        for rec in self.store.all_sessions():
            if rec.get("gid") == gid:
                out = {k: rec.get(k) for k in
                       ("key", "loose_key", "mouse", "session", "start",
                        "label")}
                out["gid"] = gid
                return out
        if not row:
            return None
        return {"key": row.get("key"), "loose_key": row.get("loose_key"),
                "mouse": row.get("mouse"), "session": row.get("session"),
                "start": row.get("started_at"), "label": row.get("label"),
                # Carried so a recording with no derivable key still has
                # something unique to be filed under. Without it, exactly the
                # recordings that need care most are the ones a pull drops.
                "gid": gid}

    #: Fields a pull is allowed to bring down onto a session, and how to
    #: read each one off the row. Paths and sightings have their own tables.
    SESSION_FIELDS = (
        ("gid", "gid"), ("project", "project"),
        ("project_source", "project_source"), ("cohort", "cohort"),
        ("label", "label"), ("note", "note"), ("condition", "condition"),
        ("bad_channels", "bad_channels"),
        ("bad_channels_note", "bad_channels_note"), ("retired", "retired"),
        # Which hippocampus, and where that was learned. Two-way like the
        # rest: somebody correcting a side on the rig has to reach the
        # desktop, or the two machines disagree about what the recording is.
        ("hemisphere", "hemisphere"),
        ("hemisphere_source", "hemisphere_source"),
        # The anatomical landmarks every CSD is read against. Two-way like
        # the rest: somebody correcting a fissure channel on the rig has to
        # reach the desktop.
        ("ripple_channel", "ripple_channel"),
        ("fissure_channel", "fissure_channel"),
        ("hilus_channel", "hilus_channel"),
        ("extraction_note", "extraction_note"),
        ("needs_processing", "needs_processing"),
        ("reference_channels_source", "reference_channels_source"),
    )

    @staticmethod
    def _same(a, b):
        """Equal for syncing purposes.

        None, "" and [] all mean "not set", and they arrive differently
        depending on which side wrote the row -- treating them as different
        is what turns a sync into a permanent write loop.
        """
        if a in (None, "", [], {}) and b in (None, "", [], {}):
            return True
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return list(a) == list(b)
        return a == b

    def _apply_sessions(self, rows):
        n = 0
        for r in rows:
            gid = r.get("gid")
            ident = self._ident_for(gid, r)
            # A gid is enough: a recording whose folder name says neither
            # mouse nor session has no key, and is precisely the one nobody
            # can afford to lose.
            if not ident or not (ident.get("key") or ident.get("loose_key")
                                 or gid):
                continue
            local, _how = self.store.get_session(ident)
            local = local or {}
            patch = {}
            for here, there in self.SESSION_FIELDS:
                want = r.get(there)
                if here == "bad_channels":
                    want = list(want or [])
                elif here == "retired":
                    want = bool(want)
                if not self._same(local.get(here), want):
                    patch[here] = want
            # Nothing to say: writing anyway would restamp the record and the
            # next push would send it back up, forever.
            if not patch:
                continue
            self.store.upsert_session(ident, patch)
            n += 1
        return n

    def _apply_paths(self, rows):
        by_gid = {}
        for r in rows:
            if r.get("deleted_at"):
                continue
            by_gid.setdefault(r["gid"], []).append(r["path"])
        n = 0
        for gid, paths in by_gid.items():
            ident = self._ident_for(gid)
            if not ident:
                continue
            rec, _how = self.store.get_session(ident)
            have = list((rec or {}).get("paths") or [])
            add = [p for p in paths if p not in have]
            if add:
                self.store.upsert_session(ident, {"paths": have + add})
                n += len(add)
        return n

    def _apply_mice(self, rows):
        if not self.mice:
            return 0
        n = 0
        for r in rows:
            if r.get("mouse") is None:
                continue
            project = r.get("project") or "Unfiled"
            local = self.mice.get(project, r["mouse"]) or {}
            attrs = r.get("attrs") or {}
            if self._same(local.get("attrs") or {}, attrs) \
                    and self._same(local.get("note"), r.get("note")):
                continue          # same as ours; see _apply_sessions
            self.mice.set(project, r["mouse"], attrs, note=r.get("note"))
            n += 1
        return n

    def _apply_bank(self, rows):
        if not self.bank:
            return 0
        have = {e.get("id") for e in self.bank.all()}
        n = 0
        for r in rows:
            if r.get("deleted_at") or r.get("id") in have:
                continue
            try:
                self.bank.add({
                    "id": r.get("id"), "gid": r.get("gid"),
                    "project": r.get("project"), "mouse": r.get("mouse"),
                    "session": r.get("session"),
                    "session_key": r.get("session_key"),
                    "session_label": r.get("session_label"),
                    "session_path": r.get("session_path"),
                    "recording_start": r.get("recording_start"),
                    "duration_s": r.get("duration_s"),
                    "type": r.get("type"), "type_name": r.get("type_name"),
                    "name": r.get("name"), "note": r.get("note"),
                    "events": r.get("events") or [],
                    "pipeline": (r.get("source") or {}).get("pipeline"),
                    "source_file": (r.get("source") or {}).get("file"),
                    "detector": (r.get("source") or {}).get("detector"),
                    "parameters": (r.get("source") or {}).get("parameters"),
                    "added_by": r.get("added_by"),
                    "curated": bool(r.get("specified")),
                    "curation_label": r.get("curation_label"),
                })
                n += 1
            except Exception:            # noqa: BLE001
                continue
        return n

    def _apply_curation(self, sets, events):
        if not self.curate:
            return 0
        by_set = {}
        for e in events:
            by_set.setdefault(e["set_id"], []).append(e)
        n = 0
        for s in sets:
            gid, kind = s.get("gid"), s.get("kind")
            rec = self.curate.get(gid, kind) if gid and kind else None
            if not rec:
                continue          # the set has to exist locally to take
                                  # decisions; a whole new set arrives with
                                  # its own import, not through a sync
            mine = {e["id"]: e for e in (rec.get("events") or [])}
            touched = False
            for e in by_set.get(s["id"], []):
                cur = mine.get(e.get("event_id"))
                if not cur:
                    continue
                if (e.get("label") or "unspecified") != cur.get("label"):
                    cur["label"] = e.get("label") or "unspecified"
                    cur["by"] = e.get("decided_by")
                    cur["at"] = e.get("decided_at")
                    touched = True
                    n += 1
            if touched:
                self.curate._write(rec)
        return n

    def _apply_layers(self, sheets, labels):
        if not self.layers:
            return 0
        by_gid = {}
        for l in labels:
            by_gid.setdefault(l["gid"], {})[str(l["channel"])] = l.get("region")
        n = 0
        for s in sheets:
            gid = s.get("gid")
            if not gid:
                continue
            self.layers.ensure(gid, s.get("session_label"),
                               channels=s.get("channels") or [])
            mine = self.layers.get(gid) or {}

            mapping = {k: v for k, v in (by_gid.get(gid) or {}).items() if v}
            # Only what actually differs. Writing the same labels back on
            # every pull restamps the sheet, and a restamped sheet is pushed
            # up as though it were an edit -- the same loop the roster was
            # stuck in, passing identical rows between machines forever.
            have = mine.get("labels") or {}
            changed = {k: v for k, v in mapping.items() if have.get(k) != v}
            if changed:
                self.layers.set_many(gid, changed)
                n += len(changed)

            # The history, when this machine has less of it than the cloud.
            # Never the other way: a sheet that has been versioned here and
            # not there is this machine being ahead, not behind.
            theirs = s.get("versions") or []
            if theirs and len(theirs) > len(mine.get("versions") or []):
                self.layers.adopt_versions(gid, theirs)
                n += 1
        return n

    def _apply_results(self, rows):
        """Only the filing. The bytes are pulled on demand, not in bulk."""
        if not self.results:
            return 0
        by_rel = {r.get("rel"): r for r in self.results.catalog()}
        n = 0
        for r in rows:
            local = by_rel.get(r.get("rel_path"))
            if not local:
                continue
            patch = {}
            for a, b in (("title", "title"), ("notes", "notes"),
                         ("starred", "starred")):
                if r.get(b) is not None and r.get(b) != local.get(a):
                    patch[a] = r.get(b)
            tags = list(r.get("tags") or [])
            if sorted(tags) != sorted(local.get("tags") or []):
                patch["tags"] = tags
            if patch:
                self.results.curate(local["path"], patch)
                n += 1
        return n

    def _apply_decks(self, rows):
        if not self.results:
            return 0
        n = 0
        for r in rows:
            if r.get("deleted_at"):
                continue
            deck = self.results.get_deck(r["id"]) or {}
            local_at = (deck.get("updated") or {}).get("at")
            if deck and cloud.ts(local_at) and r.get("updated_at") \
                    and cloud.ts(local_at) >= r["updated_at"]:
                continue
            self.results.save_deck({
                "id": r["id"], "title": r.get("title"),
                "slides": r.get("slides") or [],
            })
            n += 1
        return n
