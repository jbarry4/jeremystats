"""
cloudsync.py -- Turning Jarvis's records into rows, and back.

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

import json
import os
import re
import time

from datetime import datetime

from . import cloud, eventbank, shards

BUCKET = "results"
# What the bucket accepts (supabase/03_storage.sql, allowed_mime_types), by
# extension, stated rather than guessed: `mimetypes` reads the Windows
# registry, which calls a .csv "application/vnd.ms-excel" -- a type the
# bucket refuses.
BUCKET_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml", ".webp": "image/webp",
    ".pdf": "application/pdf", ".csv": "text/csv", ".txt": "text/plain",
    ".json": "application/json", ".mp4": "video/mp4",
}

# Two-way tables, in dependency order: a child row whose parent is not there
# yet is a foreign key violation, so sessions go before everything that
# references them.
#: Tables whose rows carry a `gid` and are refused by the database when no
#: session has it. Kept beside ORDER so adding a table to one and forgetting
#: the other is visible.
GID_TABLES = (
    "session_paths", "session_sightings", "bank_entries", "curation_sets",
    "layer_sheets", "layer_labels", "results", "health_checks",
    "tool_results",
)

#: After finding the artifact tables missing (migration 18 not run), how long
#: before asking again. One request per interval is the whole cost.
ART_ABSENT_RETRY_S = 15 * 60

ORDER = [
    "machines", "sessions", "session_paths", "session_sightings", "mice",
    "bank_entries",
    # After the entries, always: a snapshot is filed against a version, and
    # the version's metadata travels in the entry. The other way round, every
    # snapshot would arrive for a version this machine has never heard of.
    "bank_snapshots",
    "curation_sets", "curation_events", "curation_reviews",
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
    # Both directions, and late in the order because nothing references it.
    # A rig that checked forty recordings and a desktop that checked twelve
    # should both be able to ask which of the fifty-two have gaps.
    "health_checks",
    # What a tool has already worked out, keyed on the recording and on
    # the settings that change the answer. Late because nothing
    # references it, and both directions: the whole point is that a
    # colleague's scan answers your question without being re-run.
    "tool_results",
    # Jarvis Artifacts (migration 18): the record, then its payloads, which
    # reference it. Last, because nothing else references either.
    "artifacts", "artifact_snapshots",
]
PUSH_ONLY =["runs", "activity", "errors", "error_marks"]


# For a record that has never been edited and so carries no timestamp: a
# built-in filter preset, a figure nobody has tagged. `now()` would be the
# obvious fallback and is quietly wrong -- it makes the row look new on every
# single push, so it is re-sent forever. A fixed stamp is sent once and then
# never again, until somebody actually changes it.
UNSTAMPED = "1970-01-01T00:00:00+00:00"


def _slim_versions(versions):
    """Version metadata, with the snapshots left behind.

    `snap` is the copy that makes a version restorable and it is the bulk of
    the record. It stays in the JSON shard; this is what travels.
    """
    out = []
    for v in (versions or []):
        if not isinstance(v, dict):
            continue
        row = {k: v.get(k) for k in
               ("v", "at", "by", "n", "note", "by_label", "machine",
                "imported")
               if v.get(k) is not None}
        if row.get("v") is not None:
            # Said on the row rather than inferred later: a reader needs to
            # know this copy cannot be restored from.
            row["snap_here"] = bool(v.get("snap"))
            out.append(row)
    return out


def _bank_touched(rec):
    """When this entry last changed.

    The newest of: when it was added, the newest version, and the newest
    history line. Using only `added.at` meant an edited entry looked
    unchanged for ever and the incremental push skipped it.
    """
    stamps = []
    added = _prov(rec, "added")
    if added.get("at"):
        stamps.append(cloud.ts(added["at"]))
    for v in (rec.get("versions") or []):
        if isinstance(v, dict) and v.get("at"):
            stamps.append(cloud.ts(v["at"]))
    for h in (rec.get("history") or []):
        if isinstance(h, dict) and h.get("at"):
            stamps.append(cloud.ts(h["at"]))
    stamps = [x for x in stamps if x]
    return max(stamps) if stamps else None


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


def _now_iso():
    return cloud.now()


def _newer_in(stamp, since):
    """Is an incoming `stamp` newer than what is already here?

    The pull-side twin of `_after`, with the opposite bias about a stamp it
    cannot read. `_after` says yes, because on the push a needless upsert is
    cheap and a dropped row is somebody's lost edit. Here a yes means
    overwriting what is on this machine, so an unreadable or missing stamp
    is not enough: no evidence, no overwrite.
    """
    if not stamp or not since:
        return bool(stamp) and not since
    a, b = cloud.ts(stamp), cloud.ts(since)
    if not a or not b:
        return False
    try:
        return datetime.fromisoformat(a) > datetime.fromisoformat(b)
    except ValueError:
        return False


def _decision_wins(theirs_at, ours_at, our_label, ours_cleared=None):
    """Should an incoming decision replace the one already here?

    This had no rule at all: any differing label was taken, so a pull could
    undo today's curation with a row from last January -- measured, on a
    real set, before this existed. A curation decision is the most expensive
    thing in this application to redo, because it is a judgement somebody
    made once while looking at a waveform.

    A decision beats no decision. Past that, the newer one wins. An incoming
    row with no stamp cannot overturn a decision that has one: on the push
    side an unreadable stamp means "send it and let the database sort it
    out", which is cheap, and on the pull side it would mean "overwrite
    somebody's judgement on no evidence", which is not.
    """
    undecided = (our_label or "unspecified") == "unspecified"
    # Only an event nobody has ever ruled on yields automatically. An undo
    # that carries a time is a decision about the candidate and is defended
    # like one -- otherwise a colleague's older label would arrive, find the
    # label empty, and undo the undo.
    if undecided and not ours_cleared:
        return True
    ours_at = ours_at or (ours_cleared if undecided else None)
    if not theirs_at:
        return False
    if not ours_at:
        return True
    return _newer_in(theirs_at, ours_at)


def _ts_key(stamp):
    """A stamp as something `max` can order -- as a time, not as text,
    because two stamps from `cloud.ts` differ in whether they carry
    microseconds, and that decides a text comparison."""
    try:
        return datetime.fromisoformat(cloud.ts(stamp) or UNSTAMPED)
    except (TypeError, ValueError):
        return datetime.fromisoformat(UNSTAMPED)


def _after(stamp, since):
    """Is `stamp` newer than `since`? Compared as times, not as text.

    This was `str(stamp) > since`, which is only true if both are in the same
    offset -- and they were not. A row stamped in Vermont local time sorted
    before a UTC "since" from the same afternoon, so the incremental push
    dropped it.

    An unparseable stamp counts as newer. Sending a row that did not need
    sending costs one upsert the database discards; dropping one that did
    loses somebody's edit, silently, until a full push happens to run.
    """
    if not stamp:
        return True
    a, b = cloud.ts(stamp), cloud.ts(since)
    if not a or not b:
        return True
    try:
        return datetime.fromisoformat(a) > datetime.fromisoformat(b)
    except ValueError:
        return True



def _absent(exc):
    """Is this "no such table" rather than a real failure?

    PostgREST answers a request for a table it has never heard of with 404
    and PGRST205. Anything else -- a timeout, a refusal, a network drop -- is
    a genuine failure and must still stop the pull, because pretending a
    table is empty when the answer was "I could not reach it" would delete
    things.
    """
    text = str(exc)
    return "PGRST205" in text or ("404" in text and "Could not find" in text)

class Sync:
    """Everything Jarvis knows, in both directions."""

    def __init__(self, logs_dir, store, bank=None, curate=None, layers=None,
                 mice=None, results=None, repo_root=None, feedback=None,
                 people=None, health=None, vaults=None):
        self.logs = os.path.abspath(logs_dir)
        self.store = store
        self.bank = bank
        self.curate = curate
        self.layers = layers
        self.mice = mice
        self.results = results
        self.feedback = feedback
        self.people = people
        self.health = health
        # {tool name: toolresults.ToolResults}. What each tool has already
        # worked out, so a colleague's scan answers your question rather than
        # being run again. Optional: a Sync built without them simply sends
        # no vault rows, which is what every caller that predates them does.
        self.vaults = vaults or {}
        # artifacts.Artifacts, set by app.py after construction. None means
        # no artifact rows are sent or taken. The two signatures are what
        # let a quiet push skip the artifact tables without a request: see
        # rows_artifacts.
        self.artifacts = None
        self._art_sent_sig = None
        self._art_pending_sig = None
        # Artifact id -> the fingerprint the cloud row carries, as of the
        # last push that asked. Kept so `item_states` can say which artifact
        # is up there without asking again. `_pending` twin, committed only
        # when a push completes.
        self._art_cloud_fp = {}
        self._art_fp_pending = None
        # When the artifact tables were last found missing: asked again after
        # ART_ABSENT_RETRY_S rather than never. See rows_artifacts.
        self._art_absent_until = 0.0
        # What a push is about to have sent, committed to the sync state only
        # once the whole push has gone through -- the same two-step as the
        # artifact signatures, so a push that fails half way re-sends rather
        # than forgetting. See rows_machines, rows_people, rows_bank_snapshots.
        self._pending = {}
        # The last "which snapshot keys are still missing up there" question
        # and when it was asked, so a snapshot whose entry has not landed is
        # asked about every quarter of an hour rather than every minute.
        self._snap_asked = (None, 0.0)
        # Whether the figures in the cloud may have changed since pull_files
        # last looked. True at start so a fresh process looks once; after
        # that only a pull that saw `results` move sets it.
        self.results_moved = True
        self._full = False
        self.repo_root = repo_root
        self.cloud = cloud.Cloud(self.logs, store)
        self.machine = shards.machine_id()
        from . import tombs
        self.tombs = tombs.Tombs(self.logs, store)

    # ==================================================================
    # Local records -> rows
    # ==================================================================
    def rows_health_checks(self):
        """Every continuity check this machine knows about.

        Flat, one row per check, keyed on the check's own id. A check is a
        thing that happened on a date -- it is never edited -- so the same id
        always carries the same bytes and there is nothing to merge.
        """
        if not self.health:
            return {"health_checks": []}
        from . import healthlog
        try:
            return {"health_checks": healthlog.rows_for_cloud(self.health)}
        except Exception:                                # noqa: BLE001
            # A malformed local record must not take the whole push with it.
            return {"health_checks": []}

    # How often the machine row says "still here" when nothing about the
    # machine has changed. /api/devices calls a machine online for three
    # times this, so one late heartbeat does not take it off the list.
    HEARTBEAT_S = 300

    def rows_machines(self):
        """This computer's row -- sent when it changes, or as a heartbeat.

        It went up on every push, stamped now(), which made a push that had
        nothing to say cost a request every minute on every machine forever
        (constitution §11, leak 3). `last_seen` is a heartbeat and does need
        refreshing, but "still here" every five minutes answers the only
        question anybody asks of it -- is that rig on -- exactly as well.
        """
        prov = self.store.provenance()
        row = {
            "id": self.machine,
            "hostname": prov.get("machine"),
            "os": prov.get("os"),
            "git_user": prov.get("user"),
            # Which code this machine runs, so a rig that never pulled is a
            # line in the device list rather than a surprise in the bill.
            # Migration 19; without it the column is dropped and retried.
            # Named for itself: `version` is already a bank_entries column,
            # and the pending-migration check matches columns by name.
            "jarvis_version": "%s%s" % (prov.get("app_version") or "",
                                 ("+" + prov["commit"])
                                 if prov.get("commit") else ""),
        }
        sig = json.dumps(row, sort_keys=True, default=str)
        sent = (self.cloud.state() or {}).get("machines_sent") or {}
        age = time.time() - float(sent.get("at") or 0)
        if (sent.get("sig") == sig and age < self.HEARTBEAT_S
                and not self._full):
            return []
        stamp = cloud.now()
        row["last_seen"] = stamp
        row["updated_at"] = stamp
        self._pending["machines_sent"] = {"sig": sig, "at": time.time()}
        return [row]

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
                # Which probe went into the animal, and what each block of
                # sixty-four channels is. Both decide how a CSD is
                # computed, so they belong to the recording and travel with
                # it -- the probe used to live in one window's view state,
                # which meant it lasted as long as that window and reached
                # nobody.
                #
                # `probe_source` is deliberately only ever 'manual' or
                # absent. A guess derived from the channel count is not
                # written: once filed it would be indistinguishable from an
                # answer, and seventy of the seventy-one dual implants here
                # are currently guesses.
                #
                # Safe to send before migration 17 has been run anywhere:
                # `missing_column` drops a column the schema has not got
                # yet and retries, rather than failing the batch.
                "probe": rec.get("probe"),
                "probe_source": rec.get("probe_source"),
                "channel_banks": rec.get("channel_banks"),
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
                # The version history, without the snapshots.
                #
                # Measured on this store: 110 versions are 44 KB of metadata
                # and 0.5 MB of snapshots. The metadata is what makes a
                # version visible on another machine -- who, when, how many,
                # the label mix -- and the snapshot is what lets it be
                # restored. So the metadata comes here and the snapshots stay
                # in the JSON shard, which is the redundancy copy.
                "versions": _slim_versions(rec.get("versions")),
                "version": _int(rec.get("version")),
                # The newest thing that happened to it, not the moment it was
                # created. This was `added.at`, so an entry that was edited
                # afterwards never looked new to the incremental push and
                # stopped travelling the moment it existed -- which is most
                # of why a new version needed a git pull.
                "updated_at": _bank_touched(rec) or cloud.now(),
                "updated_by": added.get("by") or self.machine,
            })
        return {"bank_entries": out}

    def rows_bank_snapshots(self):
        """One row per version that has a snapshot here.

        `updated_at` is the version's creation time, not now(): it never
        changes, so the incremental push sends each of these once and then
        stops. A snapshot is immutable, so a re-push would be the same bytes
        anyway -- this just saves sending them.
        """
        if not self.bank:
            return {"bank_snapshots": []}
        # Demo entries stay local, as they do for `rows_bank`.
        real = {rec.get("id") for rec in self.bank.all()
                if not self._is_demo(rec)}
        local = [(eid, v, snap, machine, at)
                 for eid, v, snap, machine, at in self.bank.snapshots()
                 if eid in real]

        # Which of these the cloud already has -- remembered here, rather
        # than asked every push.
        #
        # NOT a timestamp comparison. These rows carry the version's own
        # creation time so that a pushed snapshot is never re-sent -- which
        # also means every snapshot older than the day this feature shipped
        # is older than `last_push` and would be skipped for ever. So the
        # question is by key.
        #
        # It used to be asked of the whole table on every push: every key in
        # bank_snapshots and every id in bank_entries, ~25 KB, every minute,
        # on every machine -- about 1.2 GB a month each, for an answer that
        # changes when somebody banks a version. Now a key this machine has
        # seen up there (or sent) is kept in the sync state, and only keys
        # it has not are asked about, by name. A quiet push asks nothing.
        state = self.cloud.state() or {}
        known_keys = set() if self._full else set(state.get("snap_keys") or [])
        missing = {"%s:%d" % (eid, int(v)) for eid, v, _s, _m, _a in local}
        missing -= known_keys
        if not missing:
            return {"bank_snapshots": []}
        # The same unanswerable question -- a snapshot whose entry has not
        # reached the database -- is asked again every quarter hour, not
        # every minute.
        asked, asked_at = self._snap_asked
        if asked == missing and time.time() - asked_at < 900:
            return {"bank_snapshots": []}
        self._snap_asked = (set(missing), time.time())

        ids = sorted({k.rsplit(":", 1)[0] for k in missing})
        have = set()
        known = None
        try:
            if len(ids) <= 40:
                # By name: a short URL and a small answer.
                inlist = "in.(%s)" % ",".join(
                    '"%s"' % i.replace('"', '') for i in ids)
                snap_rows = self.cloud.select_all(
                    "bank_snapshots", query="entry_id=" + inlist,
                    columns="entry_id,v")
                entry_rows = self.cloud.select_all(
                    "bank_entries", query="id=" + inlist, columns="id")
            else:
                # A machine with no memory of this yet (first push after an
                # update, or a cleared cache): one full key read, once, and
                # everything it says is remembered.
                snap_rows = self.cloud.select_all(
                    "bank_snapshots", columns="entry_id,v")
                entry_rows = self.cloud.select_all(
                    "bank_entries", columns="id")
            for r in snap_rows:
                have.add((str(r.get("entry_id")), int(r.get("v"))))
            # And which entries the database actually has.
            #
            # `bank_snapshots.entry_id` references `bank_entries(id)`, so a
            # snapshot for an entry that has not landed yet is rejected --
            # and a rejected row fails the whole batch, which aborts the
            # push before curation, layers, results and everything else
            # later in the order. One new entry could stop a day's work
            # leaving the machine. The entry goes up from a table earlier
            # in the same push, so its snapshots follow a minute later.
            known = {str(r.get("id")) for r in entry_rows if r.get("id")}
        except Exception:                            # noqa: BLE001
            # No answer means send nothing rather than everything: an
            # unanswered question is not a reason to risk the push that
            # carries every other table.
            return {"bank_snapshots": []}

        # What the cloud said it has is a fact now, whatever this push does.
        local_keys = {"%s:%d" % (eid, int(v)) for eid, v, _s, _m, _a in local}
        up_there = {"%s:%d" % k for k in have} & local_keys
        if up_there:
            self.cloud.save_state(
                {"snap_keys": sorted(known_keys | up_there)})
            known_keys |= up_there

        out = []
        sending = set()
        for eid, v, snap, machine, at in local:
            if (str(eid), int(v)) in have:
                continue
            # Its entry has to be there first, or the batch is refused and
            # takes the rest of the push with it.
            if known is not None and str(eid) not in known:
                continue
            sending.add("%s:%d" % (eid, int(v)))
            out.append({
                "entry_id": eid,
                "v": int(v),
                "n": len(snap),
                "sha256": eventbank.snap_sha(snap),
                "snap": snap,
                "machine": machine,
                "updated_at": cloud.ts(at) or UNSTAMPED,
            })
        if sending:
            self._pending["snap_keys"] = sorted(known_keys | sending)
        return {"bank_snapshots": out}

    # -- Jarvis Artifacts ------------------------------------------------
    @staticmethod
    def _art_local_only(rec):
        """Demo and harness artifacts stay on this machine, as demo bank
        entries do."""
        subj = rec.get("subject") or {}
        gids = [subj.get("gid")] + [
            (r or {}).get("gid") for side in ("left", "right")
            for r in (subj.get(side) or []) if isinstance(r, dict)]
        return any(str(g or "").startswith(("demo-", "harness-"))
                   for g in gids)

    def rows_artifacts(self):
        """Artifact records as rows, and their payloads add-only.

        Content-addressed rather than time-filtered, which is why both tables
        are in NO_INCREMENTAL. The cloud row carries `fp`, a fingerprint of
        what it knows (version ids and their confirmations, citation ids,
        nickname, deleted); a record is sent when its fingerprint differs
        from the cloud's. A timestamp comparison would lose the case that
        matters: two machines each holding a version the other has not
        seen, where the later push overwrites the earlier one's row. Here
        the machine that is ahead keeps sending until the cloud agrees, and
        the pull merges by id, so both versions end up everywhere.

        Payloads go up once, keyed (artifact_id, version_id) -- a version id
        is minted once, so the same key is the same bytes -- and the table
        refuses updates outright (migration 18), so a payload is never
        overwritten there either.

        Egress: two requests, and only when this machine's artifacts have
        changed since the last successful push (or a pull found the cloud
        behind). A quiet push costs nothing.
        """
        empty = {"artifacts": [], "artifact_snapshots": []}
        store = self.artifacts
        if store is None:
            return empty
        if time.time() < getattr(self, "_art_absent_until", 0.0):
            # The tables were missing a moment ago; one request every
            # ART_ABSENT_RETRY_S is the whole cost of waiting for them.
            return empty
        sig = store.signature()
        if sig == self._art_sent_sig and not store.cloud_dirty:
            self._art_pending_sig = sig
            return empty
        recs = [(r, st) for r, st in store.records_for_cloud()
                if not self._art_local_only(r)]
        if not recs:
            self._art_pending_sig = sig
            return empty
        try:
            there = {str(r.get("id")): r.get("fp") for r in
                     self.cloud.select_all("artifacts", query="select=id,fp")}
            have = {(str(r.get("artifact_id")), str(r.get("version_id")))
                    for r in self.cloud.select_all(
                        "artifact_snapshots",
                        query="select=artifact_id,version_id")}
        except Exception as exc:                         # noqa: BLE001
            # Migration 18 not run: nothing to send to. Ask again in a while
            # -- NOT "once something here changes". Marking the signature
            # sent here meant that a Jarvis running when the migration WAS
            # run never pushed its artifacts until one of them changed or it
            # was restarted: found 2026-09-28, three artifacts sat unsent
            # for ten minutes after the tables appeared. Anything else -- no
            # answer -- sends nothing and asks again next time.
            if _absent(exc):
                self._art_absent_until = time.time() + ART_ABSENT_RETRY_S
            return empty

        now = cloud.now()
        rows, live = [], set()
        fp_after = dict(there)
        for rec, nick_at in recs:
            live.add(rec["id"])
            fp = self.artifacts.cloud_fingerprint(rec)
            if there.get(rec["id"]) == fp:
                continue
            fp_after[rec["id"]] = fp
            added = rec.get("added") or {}
            deleted = rec.get("deleted") or None
            rows.append({
                "id": rec["id"], "kind": rec.get("kind"),
                "schema": rec.get("schema"),
                "subject": rec.get("subject") or {},
                "subject_key": rec.get("subject_key"),
                "name": rec.get("name"), "nickname": rec.get("nickname"),
                "nickname_at": cloud.ts(nick_at) if nick_at else None,
                "version": _int(rec.get("version")),
                "versions": rec.get("versions") or [],
                "cited": rec.get("cited") or [],
                "added": added,
                "added_at": cloud.ts(added.get("at")),
                "deleted": deleted,
                "deleted_at": cloud.ts((deleted or {}).get("at")),
                "fp": fp,
                # When it was SENT. Record rows are compared by `fp`, not by
                # time, and a pull asks for rows newer than its last one --
                # so the stamp has to be the moment the row reached the
                # cloud, or a late push from a laptop that was offline would
                # sit behind every other machine's cursor for ever.
                "updated_at": now,
                "updated_by": added.get("by") or self.machine,
            })
        snaps = []
        for aid, ver, payload in store.snapshots():
            if aid not in live or (aid, str(ver.get("id"))) in have:
                continue
            snaps.append({
                "artifact_id": aid, "version_id": ver.get("id"),
                "v": _int(ver.get("v")), "digest": ver.get("digest"),
                "payload": payload, "machine": ver.get("machine"),
                "updated_at": now,
            })
        self._art_pending_sig = sig
        self._art_fp_pending = fp_after
        # Kept in the sync state with the cursor, so a restarted Jarvis can
        # still say which artifacts are up there before its first push.
        self._pending["art_fp"] = fp_after
        return {"artifacts": rows, "artifact_snapshots": snaps}

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
                    # The word, because `curation_events.label` is NOT
                    # NULL -- the shared table has no way to write "nobody
                    # has decided", so the word is that encoding and this
                    # line is not the careless `or` it looks like. I tried
                    # sending null here and Postgres refused it:
                    # 23502, null value in column "label".
                    #
                    # The bug this looked like was real but was on the way
                    # back IN: the applier wrote the word as a local label
                    # and `progress` counted it as a decision, so seven
                    # untouched candidates read as done and `left` was 0.
                    # Both of those are fixed where they belong.
                    "label": ev.get("label") or "unspecified",
                    "decided_by": ev.get("by"),
                    # Or when it was un-decided. `decided_at` on the wire
                    # means "when this row's state was set", which is true
                    # of a decision and of taking one back -- and without a
                    # time on the undo it could not be ordered, so it
                    # stopped at the machine that made it while a
                    # colleague's copy kept the decision and pushed it back.
                    "decided_at": at or cloud.ts(ev.get("cleared_at")),
                    "updated_at": (at or cloud.ts(ev.get("cleared_at"))
                                   or cloud.ts(cr.get("at")) or cloud.now()),
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
                # The workbench half. A bench that exists on one computer
                # answers "what am I working on"; the shared one answers
                # "what is anybody working on", which is the question that
                # stops two people labelling the same recording twice.
                "name": rec.get("name"),
                "assignee": rec.get("assignee"),
                "is_open": bool(rec.get("open")),
                "opened_at": cloud.ts(rec.get("opened_at")),
                "opened_by": rec.get("opened_by"),
                "archived": bool(rec.get("archived")),
                "archived_at": cloud.ts(rec.get("archived_at")),
                "archived_by": rec.get("archived_by"),
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
                # What it is of. The run record has always known; the
                # catalogue used to drop it, so "what do we have on m306"
                # could only ever be a text search over labels.
                "project": r.get("project"),
                "mouse": _int(r.get("mouse")),
                "session_no": _int(r.get("session_no")),
                "recorded_on": r.get("recorded_on"),
                "tool": r.get("script") or r.get("kind"),
                "app_version": r.get("app_version"),
                "commit_sha": r.get("commit"),
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

    def rows_tool_results(self):
        """The vault: one row per (tool, recording, question).

        The numbers only. The picture each of these is drawn into is
        megabytes and regenerable from them in milliseconds, so it stays in
        GUI_logs/.cache and never leaves the machine that made it.
        """
        out = []
        for tool, vault in (self.vaults or {}).items():
            for r in vault.all():
                gid = r.get("gid")
                ph = r.get("params_hash")
                if not gid or not ph:
                    continue
                comp = r.get("computed") or {}
                up = _prov(r, "updated") or comp
                out.append({
                    "id": "%s:%s:%s" % (tool, gid, ph),
                    "tool": tool,
                    "gid": gid,
                    "params_hash": ph,
                    # What was asked. A tool that keeps its settings under
                    # `spec` says so; one that keeps them at the top level --
                    # Panorama does -- is read using the field list the vault
                    # already hashes on, rather than this file having to know
                    # each tool's parameters by name.
                    "spec": (r.get("spec")
                             or {k: r.get(k) for k in (vault.keys or ())
                                 if r.get(k) is not None}),
                    # Everything that is not bookkeeping is the answer. Listed
                    # by exclusion rather than by name because each tool's
                    # numbers are its own -- naming them here would mean this
                    # file had to change every time a tool learned to measure
                    # something new.
                    "numbers": {k: v for k, v in r.items()
                                if not k.startswith("_")
                                and k not in ("gid", "params_hash", "spec",
                                              "computed", "updated", "tool",
                                              "fit_engine", "session_label",
                                              "region", "channel_label")},
                    "engine": r.get("fit_engine"),
                    "session_label": r.get("session_label"),
                    "region": r.get("region"),
                    "channel_label": r.get("channel_label"),
                    "seconds": _num(comp.get("seconds")),
                    "computed_at": cloud.ts(comp.get("at")),
                    "computed_by": up.get("user"),
                    "machine": comp.get("machine") or up.get("machine"),
                    "app_version": up.get("app_version"),
                    "commit_sha": up.get("commit"),
                    "updated_at": (cloud.ts(up.get("at"))
                                   or cloud.ts(comp.get("at")) or UNSTAMPED),
                    "updated_by": up.get("user") or self.machine,
                })
        return {"tool_results": out}

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
                "app_version": prov.get("app_version"),
                "commit_sha": prov.get("commit"),
                # The complete layout a rebuild reads back. It has always been
                # on the run record here and has never travelled, so a
                # colleague could see that a figure was made and not rebuild
                # it. `panels` is part of the recipe, not a summary of it --
                # a summary is exactly what cannot be rebuilt from.
                "recipe": {k: v for k, v in r.items()
                           if k in ("panels", "recipe", "layout", "format",
                                    "problems")} or None,
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

    # What a roster row says that another machine can use -- everything but
    # the counts, which each machine compiles from its own data and which
    # `_apply_people` never takes.
    _PEOPLE_FIELDS = ("name", "email", "role", "initials", "orcid", "note",
                      "is_person", "aliases", "archived")

    def rows_people(self):
        """The roster, so a name typed on one machine is pickable on another.

        Only rows that changed, stamped with when they changed. Every row
        used to go up on every push stamped now(), so every push moved the
        `people` watermark and every machine's every pull downloaded the
        whole roster again -- a quiet pull was two requests, not one, on
        every machine, forever (constitution §11, leak 2; rule 2).

        Two kinds of row, handled differently because only one of them has
        an honest time:

        - A name somebody added or edited by hand carries `edited_at`. It is
          sent when what it says differs from what this machine last sent,
          stamped with that time, so the database's newest-wins trigger
          orders it against an edit made elsewhere.
        - A name compiled from the records (a decision's `by`, a profile) has
          no such time and no typed details. Stamping it now() would let it
          blank a role somebody typed on another machine, so it is only ever
          INSERTED: a name the cloud has not got goes up once; a name it has
          is left alone. Asking which is one request, made only when this
          machine has names it has not asked about.
        """
        if not self.people:
            return {"people": []}
        try:
            got = self.people.roster(self.curate, self.bank)
        except Exception:                            # noqa: BLE001
            return {"people": []}
        state = self.cloud.state() or {}
        sent = {} if self._full else dict(state.get("people_fp") or {})
        rows = [self._people_row(r) for r in
                (got.get("people") or []) + (got.get("not_people") or [])
                if (r.get("name") or "").strip()]
        if "people_fp" not in state and not self._full:
            # First push on this code. Everything the roster says has
            # already gone up -- the old code sent it all every minute -- so
            # it is recorded as sent rather than sent again. Sending it again
            # would stamp this machine's copy "now" and let a stale role
            # here overwrite a newer one from elsewhere, lab-wide.
            self.cloud.save_state({"people_fp": {
                row["name"].strip().lower(): fp for row, fp, _e in rows}})
            return {"people": []}
        last_push = state.get("last_push")
        changed = []
        unknown = []
        for row, fp, edited in rows:
            key = row["name"].strip().lower()
            if sent.get(key) == fp:
                continue
            if edited:
                # Changed by hand since the last push: that time. Changed
                # some other way (an email from a profile) with no fresh
                # edit behind it: now, or the push's own "newer than the
                # last push" filter would drop it and it would never travel.
                row["updated_at"] = (edited if _after(edited, last_push)
                                     else cloud.now())
                changed.append((key, fp, row))
            elif key not in sent:
                unknown.append((key, fp, row))
        if unknown:
            names = ",".join('"%s"' % k[2]["name"].replace('"', '')
                             for k in unknown)
            try:
                there = {(r.get("name") or "").strip().lower()
                         for r in self.cloud.select_all(
                             "people", query="name=in.(%s)" % names,
                             columns="name")}
            except Exception:                        # noqa: BLE001
                there = None                         # ask again next push
            if there is not None:
                stamp = cloud.now()
                for key, fp, row in unknown:
                    if key in there:
                        # Already up there. Remembered, not sent.
                        sent[key] = fp
                        continue
                    row["updated_at"] = stamp
                    changed.append((key, fp, row))
                self.cloud.save_state({"people_fp": sent})
        if changed:
            pending = dict(sent)
            pending.update({key: fp for key, fp, _row in changed})
            self._pending["people_fp"] = pending
        return {"people": [row for _key, _fp, row in changed]}

    def _people_row(self, row):
        """(cloud row, fingerprint of what it says, its edit time or None)."""
        out = self._people_payload(row)
        fp = json.dumps({k: out.get(k) for k in self._PEOPLE_FIELDS},
                        sort_keys=True, default=str)
        return out, fp, cloud.ts(row.get("edited_at"))

    def _people_payload(self, row):
        return {
            "name": row.get("name"),
            "email": row.get("email"),
            # The details somebody actually typed. These were missing,
            # and they are the only part of a roster entry that is not
            # compiled from the data -- so they were the only part that
            # never travelled. An edited role stayed on the machine it
            # was edited on, which is exactly what was reported.
            "role": row.get("role") or None,
            "initials": row.get("initials") or None,
            "orcid": row.get("orcid") or None,
            "note": row.get("note") or None,
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
            # No `last_seen`: nothing reads it, and stamping it was half
            # of what made every row look new on every push.
        }

    def rows_prefs(self):
        """This machine's preferences, when they have changed.

        Stamped with when they were last written -- `set_prefs` keeps that in
        `updated` -- rather than now(), so an unchanged record stops going up
        every minute (constitution §11, rule 2). The screen-shaped keys live
        in this machine's own shard and are written without that stamp, so
        its file time stands in for them.
        """
        from .store import PREFS_LOCAL
        prefs = self.store.get_prefs() or {}
        local = {k: v for k, v in prefs.items() if k in PREFS_LOCAL}
        shared = {k: v for k, v in prefs.items()
                  if k not in PREFS_LOCAL and not k.startswith("_")}
        stamps = [cloud.ts(prefs.get("updated"))]
        try:
            own = self.store._prefs_path()
            if own and os.path.isfile(own):
                stamps.append(cloud.ts(os.path.getmtime(own)))
        except Exception:                            # noqa: BLE001
            pass
        stamps = [s for s in stamps if s]
        return {"prefs": [{
            "machine": self.machine,
            "local": local,
            "shared": shared,
            "updated_at": max(stamps, key=_ts_key) if stamps else UNSTAMPED,
        }]}

    # ==================================================================
    # Push
    # ==================================================================
    # ==================================================================
    # Has it gone up? Per record, without asking the database
    # ==================================================================
    ITEM_KINDS = ("bank", "curation", "layers", "artifacts")

    def item_states(self, kinds=None, last_push=None, known_gids=None):
        """{kind: {id: {"state", "at"}}} for the records a person works on.

        `state` is one of:

          synced   this machine's copy was in a push that finished;
          waiting  changed since the last push that finished;
          local    never travels -- a demo or harness record, or one whose
                   recording the shared table does not have (the push drops
                   those; see `_push`);
          unknown  artifacts only, before any push has asked the cloud
                   what it holds.

        Answered from the push cursor and the artifact fingerprints the last
        push saw, so it costs nothing at the database. The stamps are the
        ones `rows_*` send, so "waiting" here is exactly "the next push will
        carry it". Asking the database instead is `/api/bank/sync?verify=1`.
        """
        want = set(kinds or self.ITEM_KINDS)
        out = {}

        def judge(stamp):
            if not last_push:
                return "waiting"
            if not stamp:
                # Sent on every push (see `_after`), so the last one had it.
                return "synced"
            return "waiting" if _after(stamp, last_push) else "synced"

        def orphan(gid):
            return bool(known_gids is not None and gid
                        and gid not in known_gids)

        if "bank" in want:
            d = {}
            for rec in (self.bank.all() if self.bank else []):
                rid = rec.get("id")
                if not rid:
                    continue
                if self._is_demo(rec):
                    d[rid] = {"state": "local", "why": "demo"}
                elif orphan(rec.get("gid")):
                    d[rid] = {"state": "local", "why": "no recording"}
                else:
                    t = _bank_touched(rec)
                    d[rid] = {"state": judge(t), "at": t}
            out["bank"] = d

        if "curation" in want:
            d = {}
            for rec in (self.curate.all() if self.curate else []):
                gid, kind = rec.get("gid"), rec.get("kind")
                if not gid or not kind:
                    continue
                sid = "%s__%s" % (gid, kind)
                if self._is_demo(rec):
                    d[sid] = {"state": "local", "why": "demo"}
                    continue
                if orphan(gid):
                    d[sid] = {"state": "local", "why": "no recording"}
                    continue
                stamps = [cloud.ts(_prov(rec, "updated").get("at"))]
                for ev in (rec.get("events") or []):
                    stamps.append(cloud.ts(ev.get("at"))
                                  or cloud.ts(ev.get("cleared_at")))
                    for r in (ev.get("reviews") or []):
                        stamps.append(cloud.ts(r.get("at")))
                stamps = [s for s in stamps if s]
                t = max(stamps, key=_ts_key) if stamps else None
                d[sid] = {"state": judge(t), "at": t}
            out["curation"] = d

        if "layers" in want:
            d = {}
            for rec in (self.layers.all() if self.layers else []):
                gid = rec.get("gid")
                if not gid:
                    continue
                if self._is_demo(rec):
                    d[gid] = {"state": "local", "why": "demo"}
                elif orphan(gid):
                    d[gid] = {"state": "local", "why": "no recording"}
                else:
                    t = cloud.ts(_prov(rec, "updated").get("at"))
                    d[gid] = {"state": judge(t), "at": t}
            out["layers"] = d

        if "artifacts" in want and self.artifacts is not None:
            d = {}
            store = self.artifacts
            if not self._art_cloud_fp:
                # A fresh process: what the last push that asked was told.
                try:
                    self._art_cloud_fp = dict(
                        (self.cloud.state() or {}).get("art_fp") or {})
                except Exception:                        # noqa: BLE001
                    pass
            try:
                level = (store.signature() == self._art_sent_sig
                         and not store.cloud_dirty)
                recs = store.records_for_cloud()
            except Exception:                            # noqa: BLE001
                level, recs = False, []
            for rec, _nick in recs:
                aid = rec.get("id")
                if not aid:
                    continue
                if self._art_local_only(rec):
                    d[aid] = {"state": "local", "why": "demo"}
                    continue
                up = level or (self._art_cloud_fp.get(aid)
                               == store.cloud_fingerprint(rec))
                # Nothing heard from the cloud about artifacts at all yet
                # (no push since this process started, none remembered):
                # that is not knowing, and it is said as not knowing.
                d[aid] = {"state": "synced" if up
                          else "waiting" if self._art_cloud_fp
                          else "unknown"}
            out["artifacts"] = d
        return out

    def collect(self, include_history=True):
        """Every table's rows, ready to send."""
        rows = {"machines": self.rows_machines()}
        rows.update(self.rows_sessions())
        rows.update(self.rows_mice())
        rows.update(self.rows_bank())
        # The snapshots that make a banked version restorable. In ORDER and
        # in ON_CONFLICT since the day the table shipped -- and never built,
        # so nothing was ever sent. A table nobody collects rows for is a
        # table that stays empty however correct the rest of it is.
        rows.update(self.rows_bank_snapshots())
        rows.update(self.rows_curation())
        rows.update(self.rows_layers())
        rows.update(self.rows_storyboards())
        rows.update(self.rows_results())
        rows.update(self.rows_presets())
        rows.update(self.rows_prefs())
        rows.update(self.rows_feedback())
        rows.update(self.rows_people())
        rows.update(self.rows_health_checks())
        # Called, not merely declared. bank_snapshots was in ORDER and in
        # ON_CONFLICT from the day it shipped and never built here, so it
        # sent nothing at all against a hundred and fifty-eight local
        # snapshots. One missing line, invisible from either end.
        rows.update(self.rows_tool_results())
        rows.update(self.rows_artifacts())
        if include_history:
            rows.update(self.rows_runs())
            rows.update(self.rows_activity())
            rows.update(self.rows_errors())
        return rows

    # Tables whose builder decides for itself what to send, so the
    # incremental `updated_at` filter must not have a second go at it.
    # `bank_snapshots` carries each version's own creation time and works
    # out what is missing by asking the database -- filtering that answer by
    # those stamps would drop every snapshot older than the last push, which
    # is all of them.
    NO_INCREMENTAL = {"bank_snapshots", "artifacts", "artifact_snapshots"}

    ON_CONFLICT = {
        # Keyed on the permanent id, and stated rather than left to the
        # fallback: `_one_per_key` guesses `id` when nothing is named, and
        # a session row has no `id` -- so a batch carrying one gid twice
        # went up untouched and Postgres refused the whole thing with "ON
        # CONFLICT DO UPDATE command cannot affect row a second time".
        #
        # It only takes one such record to stop every session syncing, and
        # there is one here: a harness fixture whose timestamps collided
        # with a real recording, leaving two local records under one gid.
        # Repairing that record is worth doing and is a separate job; a
        # push must not be the thing that notices.
        "sessions": "gid",
        "session_paths": "gid,path",
        "session_sightings": "gid,machine",
        "mice": "project,mouse",
        "bank_snapshots": "entry_id,v",
        "curation_events": "set_id,event_id",
        "curation_reviews": "set_id,event_id,reviewer",
        "layer_labels": "gid,channel",
        "presets": "kind,id",
        "artifacts": "id",
        "artifact_snapshots": "artifact_id,version_id",
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
        # THE CURSOR IS TAKEN BEFORE THE READ, and that ordering is the
        # whole correctness of an incremental push.
        #
        # It used to be taken after `collect`, which opens a window the
        # length of the read -- thirty seconds on this store -- in which
        # anything edited is lost for ever: the row is not in the batch,
        # because collect had already passed it, and the cursor then moves
        # past its timestamp, so no later push considers it either. It is
        # not retried, because nothing knows it was missed.
        #
        # Measured, not theorised: renaming ten bank entries during a push
        # sent five. The other five were written while collect was running
        # and stayed behind the cursor through every subsequent cycle --
        # the local side reported them as sent, and the database had the
        # old names days later.
        #
        # Taken first, the same row is merely re-sent next time, which the
        # database drops as a no-op. Sending something twice is free;
        # sending it never is not.
        started = cloud.now()
        self._pending = {}
        # A full push (the migration) sends everything regardless of what
        # this machine remembers sending -- the database it is filling may
        # be a new one.
        self._full = bool(full)
        try:
            return self._push(since, started, include_history, on_progress,
                              dry_run, full)
        except Exception:
            # Whatever was about to be remembered as sent was not. And the
            # snapshot question is asked again at once rather than in a
            # quarter of an hour: this failure is not the database saying
            # the entry is missing.
            self._pending = {}
            self._art_fp_pending = None
            self._snap_asked = (None, 0.0)
            raise

    def _push(self, since, started, include_history, on_progress, dry_run,
              full):
        rows = self.collect(include_history=include_history)
        sent, report = 0, {}

        # Rows pointing at a recording that no longer exists anywhere.
        #
        # Half the tables here carry a foreign key to `sessions`, and a row
        # whose gid has no session is refused by the database -- correctly,
        # and with a 409 that takes the whole batch down and everything
        # after it in the order with it. One orphaned layer sheet stopped
        # layer_sheets, storyboards, results, presets, prefs, feedback,
        # people, health_checks and tool_results from syncing, for
        # everybody, and it did it silently because a push that fails is
        # retried rather than reported.
        #
        # They are dropped rather than repaired: an orphan is a record of
        # work on a recording that has been forgotten, and deciding what to
        # do about it is a person's job. What is not a person's job is
        # having every other table stop because of it. Counted, so the
        # number is visible rather than a silence.
        known = {r.get("gid") for r in (rows.get("sessions") or [])
                 if r.get("gid")}
        orphans = {}
        if known:
            for table in GID_TABLES:
                have = rows.get(table)
                if not have:
                    continue
                keep = [r for r in have
                        if not r.get("gid") or r["gid"] in known]
                if len(keep) != len(have):
                    orphans[table] = len(have) - len(keep)
                    rows[table] = keep

        for table in ORDER + (PUSH_ONLY if include_history else []):
            batch = rows.get(table) or []
            if since and table not in self.NO_INCREMENTAL:
                batch = [r for r in batch if _after(r.get("updated_at"), since)]
            report[table] = len(batch)
            if on_progress:
                on_progress(table, len(batch))
            if batch and not dry_run:
                sent += self.cloud.upsert(
                    table, batch, on_conflict=self.ON_CONFLICT.get(table))
        if not dry_run:
            # The time the push *started*: anything written while it ran must
            # be caught next time rather than skipped.
            self.cloud.save_state(dict(self._pending, last_push=started))
            self._pending = {}
            # Only now, with every table sent, is the artifact store's
            # state the one the cloud has.
            self._art_sent_sig = self._art_pending_sig
            if self._art_fp_pending is not None:
                self._art_cloud_fp = self._art_fp_pending
                self._art_fp_pending = None
            if self.artifacts is not None:
                self.artifacts.cloud_dirty = False
        out = {"sent": sent, "tables": report, "dry_run": dry_run,
               "since": since, "full": bool(full)}
        if orphans:
            out["orphans"] = orphans
        return out

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
        # Files the bucket refused for good, by the same signature: not
        # asked again until the file itself changes.
        refused = {} if force else dict(state.get("upload_refused") or {})
        for r in self.results.catalog():
            path, rel = r.get("path"), (r.get("rel") or r.get("key"))
            if not path or not rel or not os.path.isfile(path):
                continue
            try:
                sig = "%d:%d" % (os.path.getsize(path),
                                 int(os.path.getmtime(path)))
            except OSError:
                continue
            if seen.get(rel) == sig or refused.get(rel) == sig:
                skipped += 1
                continue
            # A type the bucket does not take (03_storage.sql) is not sent.
            # This used to be sent anyway and refused, every five minutes,
            # for ever -- a spreadsheet, and every CSV, because Windows
            # names .csv "application/vnd.ms-excel". Measured on one
            # machine: 73 files, ~21,000 refused requests a day.
            ctype = BUCKET_TYPES.get(os.path.splitext(rel)[1].lower())
            if not ctype:
                refused[rel] = sig
                skipped += 1
                continue
            try:
                self.cloud.upload(BUCKET, rel, path, content_type=ctype)
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
                # A 4xx is the bucket's answer about this file (its type,
                # its size), not the network's, and asking again gets the
                # same answer. A 5xx or no answer is tried next time.
                if re.search(r"HTTP 4\d\d", str(exc)):
                    refused[rel] = sig
        self.cloud.save_state({"uploaded": seen, "upload_refused": refused})
        return {"uploaded": done, "skipped": skipped, "failed": failed}

    def push_deletions(self):
        """Carry local deletions up, as tombstones rather than DELETEs.

        Soft, because a hard delete is indistinguishable from a row somebody
        else has not fetched yet -- and because a session with curated events
        hanging off it should not evaporate on a stray click. `retired` is
        already how Jarvis hides a session it has been told to forget.
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

        Asked only when there can be an answer. This read every figure row
        in the table, every column, every five minutes on every machine --
        ~90 KB a time, ~0.8 GB a month each -- whether or not a figure had
        been added anywhere (constitution §11, leak 7). Now: the whole list
        once when Jarvis starts (which also retries anything that failed),
        and after that only when a pull saw the `results` watermark move,
        and then only rows newer than the last look, and only the three
        columns this uses.
        """
        if not self.results:
            return {"downloaded": 0, "skipped": 0, "failed": []}
        if not self.results_moved:
            return {"downloaded": 0, "skipped": 0, "failed": [],
                    "asked": False}
        out_dir = self.results.outputs_dir
        through = getattr(self, "_files_through", None)
        q = "storage_path=not.is.null&deleted_at=is.null"
        if through:
            q += "&updated_at=gt.%s" % through
        rows = self.cloud.select_all(
            "results", q, columns="rel_path,storage_path,updated_at")
        self.results_moved = False
        for r in rows:
            at = r.get("updated_at")
            if at and (not through or _ts_key(at) > _ts_key(through)):
                through = at
        # The database's own stamps, never this machine's clock: an empty
        # answer leaves the cursor where it was.
        self._files_through = through
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

        missing = []

        # Which tables have anything to say, asked once.
        #
        # This used to ask all twenty-one, every cycle, and on a quiet one
        # every single answer was an empty list. Measured: 7 KB of rows and
        # 21 requests per cycle, at a cycle every 20 seconds -- 90,720
        # requests a day per machine, and about 6.5 GB of egress a month
        # against a 5 GB allowance. The bytes were never the problem; the
        # requests were.
        #
        # `barry_watermarks` (migration 17) is one row per table carrying
        # its newest `updated_at`, so one request answers all of them. A
        # quiet cycle is then a single small request instead of a sweep.
        #
        # Falls back to asking everything when the view is not there, which
        # is what a database that has not had migration 17 run on it looks
        # like -- and what every clone looks like until somebody runs it.
        # Never an error: a sync that refuses to work until a migration has
        # been applied everywhere is a sync that stops working for the
        # person who did not apply it.
        fresh = None
        listed = set()
        if since:
            try:
                marks = self.cloud.select("barry_watermarks", "", limit=100)
                fresh = set()
                for row in (marks or []):
                    listed.add(row.get("table_name"))
                    at = row.get("updated_at")
                    # As times, not text (see _after): a stamp with no
                    # microseconds sorts wrongly against one with them.
                    if at and _after(at, since):
                        fresh.add(row.get("table_name"))
            except Exception as exc:                     # noqa: BLE001
                if not _absent(exc):
                    raise
                fresh = None                 # no view here; ask each table
        # The figure list is worth reading again only when it moved.
        if fresh is None or "results" in fresh:
            self.results_moved = True
        # A table the view does not list cannot be skipped on its say-so --
        # `errors` and `error_marks` were left out of it, and were silently
        # never pulled again. Until the view lists them (migration 19) they
        # are asked about every ten minutes rather than every cycle.
        unlisted_due = (time.time() - getattr(self, "_unlisted_at", 0.0)
                        >= 600)
        # Their own cursor: the shared one moves on every cycle, and a table
        # asked every ten minutes with it would miss what landed between.
        unlisted_since = getattr(self, "_unlisted_since", None) or since
        uq = ("updated_at=gt.%s" % unlisted_since) if unlisted_since else ""
        if unlisted_due:
            self._unlisted_at = time.time()
            self._unlisted_since = since

        def fetch(table):
            # Skipped entirely when the watermark says this table has not
            # moved. That is the whole saving: on a quiet cycle every one of
            # these returns without a request being made at all.
            tq = q
            if fresh is not None and table not in fresh:
                if table in listed or not unlisted_due:
                    return []
                tq = uq
            # Said before the request, not after it: the point of announcing
            # a table is that it is the one currently taking the time. The
            # pull is the slow half of a sync -- fifteen round trips -- and
            # it used to report the single word "pulling" for all of them.
            if on_table:
                on_table(table)
            try:
                rows = self.cloud.select_all(table, tq)
            except Exception as exc:                     # noqa: BLE001
                # A table this database has never been given. Reported and
                # skipped, because the alternative is what actually
                # happened: `health_checks` went into the order before
                # migration 15 had been run anywhere, every pull 404'd on
                # it, and everything after it in the sequence -- plus the
                # `last_pull` stamp that makes a cycle count for anything --
                # never ran. One table's absence must not take the other
                # fourteen with it, and a migration you can run late is
                # worth a great deal more than one that has to be run first.
                if _absent(exc):
                    missing.append(table)
                    return []
                raise
            for r in rows:
                got = r.get("updated_at")
                if got and (not newest_holder[0]
                            or _ts_key(got) > _ts_key(newest_holder[0])):
                    newest_holder[0] = got
            return rows

        newest_holder = [newest]

        sessions = fetch("sessions")
        applied["sessions"] = self._apply_sessions(sessions)
        applied["session_paths"] = self._apply_paths(fetch("session_paths"))
        applied["mice"] = self._apply_mice(fetch("mice"))
        applied["bank_entries"] = self._apply_bank(fetch("bank_entries"))
        # After the entries: see the note beside `bank_snapshots` in ORDER.
        applied["bank_snapshots"] = self._apply_bank_snapshots(
            fetch("bank_snapshots"))
        applied["curation"] = self._apply_curation(
            fetch("curation_sets"), fetch("curation_events"))
        applied["layers"] = self._apply_layers(
            fetch("layer_sheets"), fetch("layer_labels"))
        applied["results"] = self._apply_results(fetch("results"))
        applied["storyboards"] = self._apply_decks(fetch("storyboards"))
        applied["feedback"] = self._apply_feedback(
            fetch("feedback"), fetch("feedback_notes"))
        applied["people"] = self._apply_people(fetch("people"))
        applied["health_checks"] = self._apply_health_checks(
            fetch("health_checks"))
        applied["errors"] = self._apply_errors(fetch("errors"))
        applied["error_marks"] = self._apply_error_marks(fetch("error_marks"))
        if self.artifacts is not None:
            # The record before its payloads, as for the bank.
            applied["artifacts"] = self._apply_artifacts(fetch("artifacts"))
            applied["artifact_snapshots"] = self._apply_artifact_snapshots(
                fetch("artifact_snapshots"))
        if on_progress:
            on_progress(applied)

        self.cloud.save_state({"last_pull": newest_holder[0] or cloud.now()})
        if missing:
            applied["_missing_tables"] = missing
        out = {"applied": applied, "since": since,
               "through": newest_holder[0]}
        # A version that disagrees with itself across machines is a fault,
        # not a merge. It rides out with the result so it is on screen
        # rather than in a log nobody opens.
        clashes = getattr(self, "snapshot_conflicts", None)
        if clashes:
            out["snapshot_conflicts"] = clashes
            self.snapshot_conflicts = []
        return out

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

    def _apply_health_checks(self, rows):
        """File checks made on other machines.

        Only ever adds. A check is never edited, so a row already here is
        the same row -- there is no side to prefer and nothing to overwrite.
        Grouped by session first so one recording's history is one write
        rather than one write per check.
        """
        if not self.health or not rows:
            return 0
        by_gid = {}
        for r in rows:
            gid = r.get("gid")
            if not gid or not r.get("id"):
                continue
            by_gid.setdefault(gid, []).append(r)

        added = 0
        for gid, incoming in by_gid.items():
            rec = self.health.book.read(gid) or {}
            rec["gid"] = gid
            checks = list(rec.get("checks") or [])
            have = {c.get("id") for c in checks}
            grew = False
            for r in incoming:
                if r["id"] in have:
                    continue
                checks.append({
                    "id": r["id"],
                    "at": r.get("at"),
                    "by": r.get("by_user"),
                    "machine": r.get("machine"),
                    "level": r.get("level"),
                    "n_segments": r.get("n_segments"),
                    "n_gaps": r.get("n_gaps"),
                    "seconds_lost": r.get("seconds_lost"),
                    "max_time_error_ms": r.get("max_time_error_ms"),
                    "true_duration_s": r.get("true_duration_s"),
                    "concat_duration_s": r.get("concat_duration_s"),
                    "gap_map_sha": r.get("gap_map_sha"),
                    "gap_rule": r.get("gap_rule"),
                    "n_ncs": r.get("n_ncs"),
                    "n_probed": r.get("n_probed"),
                    "all_channels": bool(r.get("all_channels")),
                    "mismatches": r.get("mismatches"),
                })
                have.add(r["id"])
                added += 1
                grew = True
            if not grew:
                continue
            # The path is whatever this machine knows, or whatever the
            # sender knew. A folder is mounted differently on every machine,
            # so a path from elsewhere is a hint rather than a fact -- kept
            # only when there is nothing better.
            if not rec.get("path"):
                rec["path"] = incoming[0].get("path")
            if not rec.get("label"):
                rec["label"] = incoming[0].get("label")
            checks.sort(key=lambda c: str(c.get("at") or ""))
            rec["checks"] = checks[-200:]
            self.health.book.write(gid, rec)
        return added

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

        # Names this machine has retired. Checked as well as the aliases
        # because the aliases are not enough: the same push that resurrects
        # a merged-away name also unions its old alias back the other way,
        # so the alias that was supposed to suppress it disappears. A
        # tombstone cannot be argued with by an incoming row.
        retired = set()
        try:
            retired = self.people.retired()
        except Exception:                            # noqa: BLE001
            retired = set()

        self.merge_reverts = 0
        for r in (rows or []):
            name = (r.get("name") or "").strip()
            if not name:
                continue
            # The old spelling of somebody who has been merged. Writing it
            # would re-create the entry the merge removed, which is exactly
            # what used to happen on every cycle.
            if name.lower() in retired:
                # Removed here on purpose. The other machine will stop
                # sending it once it pulls; until then this is what keeps it
                # from coming back every twenty seconds.
                self.merge_reverts += 1
                continue
            keep = aliased.get(name.lower())
            if keep and keep.strip().lower() != name.lower():
                self.merge_reverts += 1
                continue
            want = {"email": r.get("email"), "role": r.get("role"),
                    "initials": r.get("initials"), "orcid": r.get("orcid"),
                    "note": r.get("note")}
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
                self.people.add(name, r.get("email"), r.get("note"),
                                role=r.get("role"),
                                initials=r.get("initials"),
                                orcid=r.get("orcid"), **more)
                n += 1
            except TypeError:
                # A People without the `aliases` field. The rest of the row
                # is still worth applying.
                try:
                    self.people.add(name, r.get("email"), r.get("note"),
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
            # Compared as times. `mine.get("at")` is local ("14:05-04:00")
            # and `updated_at` is the cloud's UTC ("18:05+00:00"), so as text
            # a mark made locally this afternoon sorted BEFORE a remote one
            # from this morning -- and re-triaging an error here was undone
            # by the next pull. Same fault as the push filter had.
            if mine and not _newer_in(r.get("updated_at"), mine.get("at")):
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
        # Which probe, and which block of channels is which region. Two-way
        # like the rest: confirming a dual implant on the rig has to reach
        # the desktop, or the two machines compute different CSDs from the
        # same recording and neither of them looks wrong.
        #
        # `channel_banks` merges by bank id locally (`shards.BYID`), so two
        # people labelling two different banks both keep their work. It
        # arrives here as whole-value LWW, which is the best a single column
        # can do -- and is why the UI fills both banks from one template
        # rather than asking twice.
        ("probe", "probe"),
        ("probe_source", "probe_source"),
        ("channel_banks", "channel_banks"),
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

    def _apply_bank_snapshots(self, rows):
        """Fill in the snapshots this machine is missing.

        Only ever fills in. `absorb_snapshot` refuses to overwrite, so a
        version that is already restorable here is left exactly as it is --
        which is what makes this safe to run against a machine that has been
        curating offline.

        A disagreement between two copies of one version is filed rather than
        resolved. There is no correct side to pick: v7 is what v7 was, and
        two different answers means something upstream is wrong.
        """
        if not self.bank:
            return 0
        added = 0
        clashes = []
        for r in rows:
            try:
                got = self.bank.absorb_snapshot(
                    r.get("entry_id"), r.get("v"), r.get("snap"),
                    r.get("sha256"))
            except Exception as exc:                       # noqa: BLE001
                clashes.append("%s v%s: %s"
                               % (r.get("entry_id"), r.get("v"), exc))
                continue
            if got == "added":
                added += 1
            elif isinstance(got, str) and got.startswith("conflict"):
                clashes.append(got)
        if clashes:
            # Carried out of the sync rather than logged and forgotten: the
            # caller puts it in the result, and the result is on screen.
            self.snapshot_conflicts = clashes
        return added

    def _art_clash(self, text):
        self.snapshot_conflicts = list(
            getattr(self, "snapshot_conflicts", None) or []) + [text]

    def _apply_artifacts(self, rows):
        """Other machines' artifact records, merged by id -- versions and
        citations only ever added, the nickname by the newer stamp, and a
        deletion refused while something here still cites it (reported)."""
        store = self.artifacts
        if store is None:
            return 0
        n = 0
        for r in rows:
            try:
                got = store.absorb_record(dict(r))
            except Exception as exc:                     # noqa: BLE001
                self._art_clash("artifact %s: %s" % (r.get("id"), exc))
                continue
            if got in ("added", "merged"):
                n += 1
            elif isinstance(got, str) and got.startswith("conflict"):
                self._art_clash(got)
            # This machine knows something the cloud row does not: send it
            # next push even if nothing here was written.
            mine = store.get(r.get("id"))
            if mine and store.cloud_fingerprint(mine) != r.get("fp"):
                store.cloud_dirty = True
        return n

    def _apply_artifact_snapshots(self, rows):
        """Fill in payloads this machine is missing. Never overwrites; a
        payload that disagrees with its version's digest is a conflict,
        reported and not filed."""
        store = self.artifacts
        if store is None:
            return 0
        n = 0
        for r in rows:
            try:
                got = store.absorb_snapshot(
                    r.get("artifact_id"), r.get("version_id"), r.get("v"),
                    r.get("digest"), r.get("payload"))
            except Exception as exc:                     # noqa: BLE001
                self._art_clash("artifact %s %s: %s" % (
                    r.get("artifact_id"), r.get("version_id"), exc))
                continue
            if got == "added":
                n += 1
            elif isinstance(got, str) and got.startswith("conflict"):
                self._art_clash(got)
        return n

    def _apply_bank(self, rows):
        if not self.bank:
            return 0
        have = {e.get("id") for e in self.bank.all()}
        n = 0
        for r in rows:
            if r.get("deleted_at"):
                continue
            # An entry this machine already has is not nothing to do. It
            # used to be skipped outright, so a version created elsewhere
            # arrived in the row and was thrown away -- which is why a new
            # v# only showed up after a git pull.
            if r.get("id") in have:
                try:
                    got = self.bank.absorb_versions(
                        r.get("id"), r.get("versions") or [],
                        r.get("version"))
                    if got:
                        n += got
                except Exception:        # noqa: BLE001
                    pass
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
                # And the history it arrived with, or a brand new entry
                # would show as v0 on this machine while the machine that
                # made it shows v3.
                if r.get("versions"):
                    try:
                        self.bank.absorb_versions(
                            r.get("id"), r.get("versions"), r.get("version"))
                    except Exception:    # noqa: BLE001
                        pass
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
                # Normalised both ways: the string "unspecified" and an
                # empty label mean the same thing -- nobody has decided --
                # and the difference between them is not news.
                theirs = e.get("label") or None
                if theirs == "unspecified":
                    theirs = None
                ours = cur.get("label") or None
                if ours == "unspecified":
                    ours = None
                if theirs == ours:
                    continue
                if not _decision_wins(e.get("decided_at"), cur.get("at"),
                                      ours or "unspecified",
                                      cur.get("cleared_at")):
                    continue
                cur["label"] = theirs
                if theirs is None:
                    cur.pop("by", None)
                    cur.pop("at", None)
                    # When it became undecided, from the row that said so --
                    # without it the next pull of that same old decision
                    # would find an unstamped blank and take the shortcut.
                    cur["cleared_at"] = e.get("decided_at") or _now_iso()
                else:
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

            # Whose it is, whether it is on a bench and whether it has been
            # filed away -- written only when they actually differ. Writing
            # them back unconditionally restamps the sheet, and a restamped
            # sheet is pushed up as though it were an edit: the loop the
            # roster was stuck in, passing identical rows between machines
            # forever.
            if s.get("name") and s.get("name") != mine.get("name"):
                self.layers.rename(gid, s["name"])
                mine = self.layers.get(gid) or {}
            if s.get("assignee") and s.get("assignee") != mine.get("assignee"):
                self.layers.assign(gid, s["assignee"])
                mine = self.layers.get(gid) or {}
            if bool(s.get("archived")) != bool(mine.get("archived")):
                self.layers.archive(gid, bool(s.get("archived")))
                mine = self.layers.get(gid) or {}
            # `is_open` is a claim about right now, so the later claim wins
            # rather than the remote one always winning: putting a sheet down
            # here should not be undone by a colleague's older pull.
            if bool(s.get("is_open")) != bool(mine.get("open")):
                ours = mine.get("opened_at") or mine.get("closed_at")
                if not mine.get("archived") and (
                        not ours or _newer_in(s.get("opened_at"), ours)):
                    try:
                        self.layers.open_set(gid, bool(s.get("is_open")),
                                             who=s.get("opened_by"))
                    except Exception:                          # noqa: BLE001
                        pass
                    mine = self.layers.get(gid) or {}

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
