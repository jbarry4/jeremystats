"""
store.py -- The GUI_logs store: everything BARRY remembers, on disk, in git.

Layout -- and every path in it is chosen so that **no two machines ever write
the same file**, which is what makes a git conflict impossible rather than
merely unlikely. See shards.py for the mechanism.

    GUI_logs/
      README.md
      runs/YYYY-MM-DD/<runid>.json         written once, by its own machine
      sessions/<identity>@<machine>.json   bad channels, notes, paths, gid
      presets/filters@<machine>.json       named filter presets
      presets/imports@<machine>.json       event-import presets
      presets/layouts@<machine>.json       saved figure layouts
      prefs/workbench@<machine>.json       theme, favourites, where-was-I
      errors/YYYY-MM-DD@<machine>.jsonl    one error per line
      activity/YYYY-MM-DD@<machine>.jsonl  one action per line
      .cache/index.json                    derived; git ignores it

Records that can be edited are split per machine and compiled on read.
Append-only logs get the machine in the filename instead, because two people
appending to one file is the oldest conflict there is. And the pooled index is
derived from all of the above, so it is a local cache rather than something to
track -- a regenerated roll-up in git conflicts on literally every pull.

Nothing here ever commits or pushes. It writes files; you commit them.
"""
from __future__ import annotations

import getpass
import json
import os
import platform
import time
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone

from . import shards

_LOCK = threading.RLock()

SCHEMA = 1

# How each field of a record is compiled when two machines disagree.
# Anything unlisted is last-writer-wins, which is right for a field that
# holds one person's decision.
SESSION_SPEC = {
    # Birth facts. The global id must never flip, or every attachment keyed
    # on it comes loose, so the earliest one minted wins for good.
    "gid": shards.FIRST,
    "created": shards.FIRST,
    # Each machine knows a different mount and none of them is wrong.
    "paths": shards.UNION,
    # One key per machine, written only by that machine.
    "seen": shards.MAPLWW,
    "bookmarks": shards.BYID,
}

PRESET_SPEC = {"presets": shards.BYID}

PREFS_BASE = "workbench"
PREFS_SPEC = {
    # Favourited scripts are about the work, so everyone's picks add up --
    # and un-favouriting still removes, because UNION carries tombstones.
    "fav_scripts": shards.UNION,
    # Named collections of results: merged per collection.
    "result_collections": shards.BYID,
    # Already a map keyed by hostname, which is the same idea one level down;
    # merging it per key means each machine only ever changes its own entry.
    "themes": shards.MAPLWW,
}

# Settings that describe this screen rather than this project. Merging them
# would mean a colleague's push changes what is in front of you, which is a
# bug however tidy the diff looks -- and half of them are absolute paths that
# do not exist on the other machine anyway. Stored per machine like everything
# else, and simply read from your own shard.
PREFS_LOCAL = ("theme", "density", "panes", "last_view", "last_session",
               "chrome", "fullscreen", "zoom",
               "recent_scripts", "recent_bookmarks", "pipeline_folders",
               "scratch_draft")

TRIAGE_SPEC = {"marks": shards.MAPLWW}
TRIAGE_BASE = "resolved"


class Store:
    def __init__(self, root, auto_stage=False):
        self.root = os.path.abspath(root)
        self.auto_stage = auto_stage
        self.dirs = {
            "runs": os.path.join(self.root, "runs"),
            "sessions": os.path.join(self.root, "sessions"),
            "presets": os.path.join(self.root, "presets"),
            "errors": os.path.join(self.root, "errors"),
            "activity": os.path.join(self.root, "activity"),
            "prefs": os.path.join(self.root, "prefs"),
            "cache": os.path.join(self.root, ".cache"),
        }
        # Everything editable, per machine, compiled on read.
        self.sessions = shards.Book(self.dirs["sessions"], SESSION_SPEC, self)
        self.presets = shards.Book(self.dirs["presets"], PRESET_SPEC, self)
        self.prefs = shards.Book(self.dirs["prefs"], PREFS_SPEC, self)
        self.triage = shards.Book(self.dirs["errors"], TRIAGE_SPEC, self)
        self.error_log = shards.DayLog(self.dirs["errors"], self)
        self.activity_log = shards.DayLog(self.dirs["activity"], self)
        # Runs are one small JSON file each, which merges cleanly in git but
        # means listing them is one open() per run. Cached in memory and
        # invalidated by the day folders' own mtimes, so a colleague's
        # `git pull` is picked up without anyone having to ask.
        self._runs = None
        self._runs_stamp = None
        self.ensure()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def ensure(self):
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)
        readme = os.path.join(self.root, "README.md")
        if not os.path.exists(readme):
            _write_text(readme, _README)
        # Any file written before sharding becomes this machine's shard.
        # Done once, up front: both sides of a pull doing it produces "both
        # deleted the old file and each added their own", which git resolves
        # by itself, whereas one machine editing a file another has deleted
        # is exactly the conflict this whole design exists to avoid.
        for book in (self.sessions, self.presets, self.triage):
            book.absorb_legacy()
        self._absorb_legacy_prefs()
        self._absorb_legacy_logs()
        for kind, default in (("filters", _DEFAULT_FILTERS),
                              ("imports", _DEFAULT_IMPORTS),
                              ("layouts", {"presets": []})):
            # Built-in presets carry fixed ids, so every machine writing them
            # once still compiles to one set rather than N copies.
            if not self.presets.read(kind):
                self.presets.write(kind, dict(default))

    def _absorb_legacy_prefs(self):
        old = os.path.join(self.root, "preferences.json")
        if os.path.isfile(old):
            data = _read_json(old) or {}
            data.pop("updated", None)
            if data:
                cur = self.prefs.read(PREFS_BASE) or {}
                cur.update(data)
                self.prefs.write(PREFS_BASE, cur)
            try:
                os.remove(old)
            except OSError:
                pass
            self._stage(old)
        stale = os.path.join(self.root, "index.json")
        if os.path.isfile(stale):
            try:
                os.remove(stale)        # derived; it lives in .cache now
            except OSError:
                pass
            self._stage(stale)

    def _absorb_legacy_logs(self):
        """A day's log written before sharding becomes this machine's."""
        for d in (self.dirs["errors"], self.dirs["activity"]):
            for name in sorted(_listdir(d)):
                if not name.endswith(".jsonl") or shards.SIGIL in name:
                    continue
                day = name[:-len(".jsonl")]
                src = os.path.join(d, name)
                dst = os.path.join(d, "%s%s%s.jsonl"
                                   % (day, shards.SIGIL, shards.machine_id()))
                try:
                    with open(src, "r", encoding="utf-8") as fh:
                        body = fh.read()
                    with open(dst, "a", encoding="utf-8", newline="\n") as fh:
                        fh.write(body)
                    os.remove(src)
                except OSError:
                    continue
                self._stage(src)
                self._stage(dst)

    # ------------------------------------------------------------------
    # Provenance -- who/what/where, stamped on every record
    # ------------------------------------------------------------------
    def provenance(self):
        return {
            "user": _git_user() or _os_user(),
            "machine": platform.node(),
            "os": platform.system(),
            "at": _now(),
        }

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------
    def record_run(self, record):
        """Persist one script/stage run. Returns the stored record."""
        with _LOCK:
            rec = dict(record)
            rec.setdefault("id", uuid.uuid4().hex[:12])
            rec.setdefault("schema", SCHEMA)
            rec["provenance"] = self.provenance()
            day = rec["provenance"]["at"][:10]
            folder = os.path.join(self.dirs["runs"], day)
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, rec["id"] + ".json")
            _write_json(path, rec)
            self._stage(path)
            self._runs = None
            return rec

    def update_run(self, run_id, patch):
        """Fill in the outcome once a run finishes."""
        with _LOCK:
            path = self._find_run(run_id)
            if not path:
                return None
            rec = _read_json(path) or {}
            rec.update(patch)
            _write_json(path, rec)
            self._stage(path)
            self._runs = None
            return rec

    def _find_run(self, run_id):
        for day in sorted(_listdir(self.dirs["runs"]), reverse=True):
            p = os.path.join(self.dirs["runs"], day, run_id + ".json")
            if os.path.isfile(p):
                return p
        return None

    def _runs_fingerprint(self):
        """A stamp that changes whenever any run record does.

        Folder mtimes alone are not enough: on Windows, editing a file in
        place leaves its directory's mtime untouched, so a `git pull` that
        overwrote an existing record would have gone unnoticed. scandir hands
        back each entry's mtime from the same directory read, so covering
        every file costs one pass rather than one stat per file.
        """
        count = 0
        newest = 0
        total = 0
        base = self.dirs["runs"]
        for day in _listdir(base):
            try:
                with os.scandir(os.path.join(base, day)) as it:
                    for entry in it:
                        if not entry.name.endswith(".json"):
                            continue
                        try:
                            mt = entry.stat().st_mtime_ns
                        except OSError:
                            continue
                        count += 1
                        total += mt
                        if mt > newest:
                            newest = mt
            except OSError:
                continue
        return (count, newest, total)

    def all_runs(self):
        """Every run record, newest first, read from disk at most once per
        change. Both the history view and the results catalog want the whole
        list, and re-reading a few thousand small files for each request is
        the one thing that would make this store feel slow with a year of
        work in it."""
        stamp = self._runs_fingerprint()
        if self._runs is not None and stamp == self._runs_stamp:
            return self._runs

        out = []
        for day in sorted(_listdir(self.dirs["runs"]), reverse=True):
            folder = os.path.join(self.dirs["runs"], day)
            for name in sorted(_listdir(folder), reverse=True):
                if not name.endswith(".json"):
                    continue
                rec = _read_json(os.path.join(folder, name))
                if rec:
                    out.append(rec)
        self._runs = out
        self._runs_stamp = stamp
        return out

    def list_runs(self, limit=400, session_key=None, script=None, status=None):
        out = []
        for rec in self.all_runs():
            if session_key and rec.get("session", {}).get("key") != session_key:
                continue
            if script and script not in (rec.get("script") or ""):
                continue
            if status and rec.get("status") != status:
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        return out

    def get_run(self, run_id):
        path = self._find_run(run_id)
        return _read_json(path) if path else None

    # ------------------------------------------------------------------
    # Sessions (bad channels, notes, remembered event files)
    # ------------------------------------------------------------------
    def session_base(self, key):
        return shards.safe_base(key)

    def session_path(self, key):
        """This machine's shard for a session. Deliberately not "the file":
        there is no such thing any more, and code that wants the record should
        ask get_session for the compiled one."""
        return self.sessions.mine(self.session_base(key))

    def get_session(self, identity):
        """Look up a stored session record, matching across machines."""
        from . import ids
        key = identity.get("key")
        if key:
            rec = self.sessions.read(self.session_base(key))
            if rec:
                return rec, "exact"
        stored = self.all_sessions()
        rec, how = ids.match(identity, stored)
        return rec, how

    def all_sessions(self):
        return self.sessions.all()

    def upsert_session(self, identity, patch):
        """Create or update the record for a session, merging `patch`."""
        with _LOCK:
            existing, _how = self.get_session(identity)
            rec = existing or {
                "schema": SCHEMA,
                "key": identity.get("key"),
                "loose_key": identity.get("loose_key"),
                "mouse": identity.get("mouse"),
                "session": identity.get("session"),
                "group": identity.get("group"),
                "start": identity.get("start"),
                "label": identity.get("label"),
                "created": self.provenance(),
                "paths": [],
            }
            # Remember every path this session has been seen at, so a colleague
            # on another mount can still tell it is the same recording.
            path = identity.get("path")
            if path and path not in rec.get("paths", []):
                rec.setdefault("paths", []).append(path)
            rec.update(patch)
            rec["updated"] = self.provenance()
            if not rec.get("key"):
                rec["key"] = identity.get("key")
            base = self.session_base(
                rec.get("key") or identity.get("loose_key") or "unknown")
            return self.sessions.write(base, rec)

    def set_bad_channels(self, identity, bad, note=None):
        """`bad` is a list of CSC channel NUMBERS (not row indices).

        Channel numbers are used deliberately: row indices shift the moment
        someone toggles even-only or a channel file goes missing, but CSC14 is
        always CSC14.
        """
        patch = {"bad_channels": sorted({int(b) for b in bad})}
        if note is not None:
            patch["bad_channels_note"] = note
        return self.upsert_session(identity, patch)

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _preset_file(self, kind):
        return self.presets.mine(shards.safe_base(kind))

    def _preset_doc(self, kind):
        return self.presets.read(shards.safe_base(kind)) or {"presets": []}

    def get_presets(self, kind):
        return self._preset_doc(kind).get("presets", [])

    def save_preset(self, kind, preset):
        with _LOCK:
            items = self.get_presets(kind)
            preset = dict(preset)
            preset.setdefault("id", uuid.uuid4().hex[:8])
            preset["saved"] = self.provenance()
            if kind == "filters":
                preset["label"] = filter_label(
                    preset.get("name", "preset"), preset.get("highpass"),
                    preset.get("lowpass"), preset.get("notch"))
            items = [p for p in items if p.get("id") != preset["id"]
                     and p.get("name") != preset.get("name")]
            items.append(preset)
            items.sort(key=lambda p: (p.get("name") or "").lower())
            doc = self._preset_doc(kind)
            doc["presets"] = items
            self.presets.write(shards.safe_base(kind), doc)
            return preset

    def delete_preset(self, kind, preset_id):
        with _LOCK:
            doc = self._preset_doc(kind)
            doc["presets"] = [p for p in doc.get("presets", [])
                              if p.get("id") != preset_id]
            self.presets.write(shards.safe_base(kind), doc)
            return doc["presets"]

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------
    def record_error(self, where, message, detail=None, context=None):
        """Append one error to this machine's log for today.

        JSONL because it is append-only, and one file per machine per day
        because two people appending to a shared day file is the single most
        reliable way to produce a merge conflict.
        """
        rec = {
            "id": uuid.uuid4().hex[:12],
            "at": _now(),
            "where": where,
            "message": str(message),
            "detail": detail,
            "context": context or {},
            "machine": platform.node(),
            "shard": shards.machine_id(),
            "user": _git_user() or _os_user(),
        }
        try:
            self.error_log.append([rec])
        except Exception:          # noqa: BLE001
            pass                   # never let logging an error raise another
        return rec

    def list_errors(self, limit=300, day=None):
        return self.error_log.read(limit=limit, day=day)

    def error_days(self):
        return self.error_log.days()

    # ------------------------------------------------------------------
    # Pooled index
    # ------------------------------------------------------------------
    def index(self, max_age=30.0):
        """The pooled index, rebuilt only when the store has changed.

        /api/sync/status asks for this on every boot and after every export.
        Rebuilding from scratch each time meant re-reading every run and every
        error file for a number that had not moved.
        """
        stamp = (self._runs_fingerprint(),
                 tuple(sorted(_listdir(self.dirs["sessions"]))),
                 tuple(sorted(_listdir(self.dirs["errors"]))))
        cached = getattr(self, "_index_cache", None)
        if cached and cached["stamp"] == stamp and \
                time.time() - cached["at"] < max_age:
            return cached["index"]
        idx = self.rebuild_index()
        self._index_cache = {"stamp": stamp, "at": time.time(), "index": idx}
        return idx

    def rebuild_index(self):
        """Roll every per-file record into one summary for fast browsing."""
        with _LOCK:
            runs = self.all_runs()
            sessions = self.all_sessions()
            by_session = {}
            for r in runs:
                key = (r.get("session") or {}).get("key")
                if key:
                    by_session[key] = by_session.get(key, 0) + 1
            index = {
                "schema": SCHEMA,
                "generated": _now(),
                "counts": {
                    "runs": len(runs),
                    "sessions": len(sessions),
                    "errors": len(self.list_errors(limit=100000)),
                },
                "sessions": [
                    {
                        "key": s.get("key"),
                        "loose_key": s.get("loose_key"),
                        "label": s.get("label"),
                        "mouse": s.get("mouse"),
                        "session": s.get("session"),
                        "group": s.get("group"),
                        "start": s.get("start"),
                        "bad_channels": s.get("bad_channels", []),
                        "paths": s.get("paths", []),
                        "runs": by_session.get(s.get("key"), 0),
                    } for s in sessions
                ],
                "recent_runs": [
                    {
                        "id": r.get("id"), "script": r.get("script"),
                        "status": r.get("status"), "at": (r.get("provenance") or {}).get("at"),
                        "session": (r.get("session") or {}).get("label"),
                    } for r in runs[:100]
                ],
            }
            # Derived, so it is a cache and not a tracked file. A roll-up of
            # everything else, regenerated on every boot, is guaranteed to
            # differ between two clones -- tracking it would mean a conflict
            # on every single pull, over a file anyone can rebuild in a
            # second. .cache is in .gitignore.
            os.makedirs(self.dirs["cache"], exist_ok=True)
            _write_json(os.path.join(self.dirs["cache"], "index.json"), index)
            return index

    # ------------------------------------------------------------------
    # git
    # ------------------------------------------------------------------
    def _stage(self, path):
        if not self.auto_stage:
            return
        try:
            subprocess.run(["git", "add", "--", path], cwd=self.root,
                           capture_output=True, timeout=15)
        except Exception:
            pass          # staging is a convenience, never a hard failure

    def git_status(self):
        """Summarize what is uncommitted under GUI_logs."""
        try:
            res = subprocess.run(["git", "status", "--porcelain", "--", "."],
                                 cwd=self.root, capture_output=True,
                                 text=True, timeout=20)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if res.returncode != 0:
            return {"ok": False, "error": (res.stderr or "git failed").strip()}
        lines = [l for l in (res.stdout or "").splitlines() if l.strip()]
        return {
            "ok": True,
            "dirty": len(lines),
            "files": [l[3:] for l in lines[:200]],
            "root": self.root,
        }


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _os_user():
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


_GIT_USER_CACHE = {}


def _git_user():
    if "v" in _GIT_USER_CACHE:
        return _GIT_USER_CACHE["v"]
    val = None
    try:
        res = subprocess.run(["git", "config", "user.email"],
                             capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            val = (res.stdout or "").strip() or None
    except Exception:
        val = None
    _GIT_USER_CACHE["v"] = val
    return val


def _listdir(path):
    try:
        return os.listdir(path)
    except OSError:
        return []


def _read_json(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path, data):
    _write_text(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def _write_text(path, text):
    """Atomic write: a half-written JSON file in git would be worse than none."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def filter_label(name, hp, lp, notch):
    """'IED  1-70 Hz, notch 60' -- the numbers belong in the menu, not a tooltip."""
    hp, lp, notch = float(hp or 0), float(lp or 0), float(notch or 0)
    if not hp and not lp and not notch:
        return name + "  (no filtering)"
    if hp and lp:
        band = "%g-%g Hz" % (hp, lp)
    elif hp:
        band = ">%g Hz" % hp
    elif lp:
        band = "<%g Hz" % lp
    else:
        band = ""
    bits = [b for b in (band, ("notch %g" % notch) if notch else "") if b]
    return name + "  " + ", ".join(bits)


def _preset(pid, name, hp, lp, notch, note):
    return {"id": pid, "name": name, "highpass": hp, "lowpass": lp,
            "notch": notch, "builtin": True, "note": note,
            "label": filter_label(name, hp, lp, notch)}


_DEFAULT_FILTERS = {
    "presets": [
        _preset("none", "None", 0, 0, 0,
                "Raw signal, exactly as recorded"),
        _preset("lfp", "LFP", 0, 300, 0,
                "Wideband local field potential"),
        _preset("theta", "Theta", 4, 12, 0,
                "Hippocampal theta band"),
        _preset("spike", "Spikes", 300, 0, 0,
                "Unit/spike band"),
        _preset("ied", "IED", 1, 70, 60,
                "Interictal discharge band with line notch"),
        _preset("ripple", "Ripple", 120, 250, 0,
                "Sharp-wave ripple band"),
        _preset("ds", "Dentate spike", 5, 100, 60,
                "Toothy dentate-spike band"),
    ]
}

_DEFAULT_IMPORTS = {
    "presets": [
        {"id": "ets_mat", "name": "LLspikedetector ets.mat", "builtin": True,
         "kind": "mat", "units": "samples", "columns": {"start": 0, "end": 1},
         "note": "ets = [onset offset] in samples; ech gives channel participation"},
        {"id": "toothy_ds", "name": "Toothy DS_DF", "builtin": True,
         "kind": "csv", "units": "samples",
         "columns": {"start": "idx", "channel": "ch"},
         "filter": {"is_valid": 1},
         "note": "Toothy dentate-spike table; idx is a sample index"},
    ]
}

_README = """# GUI_logs

Everything BARRY GUI remembers, kept as plain JSON so it travels through git.

| Folder | What it holds |
|---|---|
| `runs/YYYY-MM-DD/` | One file per script or pipeline stage run: what ran, with which parameters, against which session, and how it ended. |
| `sessions/` | One file per recording: bad channels, notes, and every path the session has been seen at. |
| `presets/` | Named filter presets, event-import presets, and figure layouts. |
| `errors/` | One JSONL file per day, one error per line. |
| `index.json` | A pooled roll-up of everything above, regenerated on demand. |

## Why one file per run and per session

Git merges separate files without conflict. Two people can both work, both
commit, and a pull brings in both sets. A single shared log would conflict on
almost every push.

## Sync

BARRY never commits or pushes on its own. It only writes files here. To share
your work:

    git add "BARRY GUI/GUI_logs"
    git commit -m "session logs"
    git push

To pick up everyone else's, just `git pull` -- new files appear and BARRY reads
them on the next refresh.

## Session identity

Sessions are keyed on mouse number + session number + recording start time,
parsed from the folder names and the Neuralynx header. That key is identical on
every machine, so a bad channel marked on one computer is found on the next,
even though one mounts the data at `D:\\PTEN` and another at
`\\\\netfiles03.uvm.edu\\bigdata_jbarry`.
"""


# ==========================================================================
# Activity log, bookmarks and spike labels
#
# These are added to Store as bound methods below, keeping the class body
# above focused on the original four record types.
# ==========================================================================
def _activity_dir(self):
    return self.dirs["activity"]


def record_activity(self, entries):
    """Append UI/analysis actions to this machine's log for today.

    Deliberately high-volume -- every filter change, colormap pick, raster
    switch, event import and download -- so it is JSONL, appended in batches
    the client sends. One file per machine per day: an append-only log shared
    between two people conflicts on essentially every push, because both sides
    add lines in the same place and git has no way to know whose come first.
    """
    if isinstance(entries, dict):
        entries = [entries]
    if not entries:
        return 0
    prov = self.provenance()
    rows = []
    for e in entries:
        rows.append({
            "id": uuid.uuid4().hex[:10],
            "at": e.get("at") or prov["at"],
            "action": e.get("action") or "unknown",
            "detail": e.get("detail") or {},
            "session": e.get("session") or {},
            "view": e.get("view"),
            "user": prov["user"],
            "machine": prov["machine"],
            "shard": shards.machine_id(),
            "os": prov["os"],
        })
    # One day per call: a batch that straddles midnight goes to both files.
    total = 0
    by_day = {}
    for r in rows:
        by_day.setdefault(str(r["at"])[:10], []).append(r)
    for _day, batch in sorted(by_day.items()):
        total += self.activity_log.append(batch)
    return total


def list_activity(self, limit=500, day=None, action=None, session_key=None):
    def keep(rec):
        if action and rec.get("action") != action:
            return False
        if session_key and (rec.get("session") or {}).get("key") != session_key:
            return False
        return True
    return self.activity_log.read(limit=limit, day=day, keep=keep)


def activity_days(self):
    return self.activity_log.days()


def get_bookmarks(self, identity):
    rec, _ = self.get_session(identity)
    return (rec or {}).get("bookmarks", [])


def save_bookmark(self, identity, bookmark):
    """A named point (or span) in a recording, remembered with the session."""
    with _LOCK:
        marks = list(self.get_bookmarks(identity))
        bm = dict(bookmark)
        bm.setdefault("id", uuid.uuid4().hex[:8])
        bm["saved"] = self.provenance()
        marks = [m for m in marks if m.get("id") != bm["id"]]
        marks.append(bm)
        marks.sort(key=lambda m: float(m.get("t", 0) or 0))
        self.upsert_session(identity, {"bookmarks": marks})
        return bm


def delete_bookmark(self, identity, bookmark_id):
    with _LOCK:
        marks = [m for m in self.get_bookmarks(identity) if m.get("id") != bookmark_id]
        self.upsert_session(identity, {"bookmarks": marks})
        return marks


def get_spike_labels(self, identity):
    """Committed threshold-detector output for a session."""
    rec, _ = self.get_session(identity)
    return (rec or {}).get("spike_labels", {"sets": []})


def save_spike_set(self, identity, spike_set):
    """Commit a detection run: its parameters plus the accepted times."""
    with _LOCK:
        store = dict(self.get_spike_labels(identity))
        sets = list(store.get("sets", []))
        s = dict(spike_set)
        s.setdefault("id", uuid.uuid4().hex[:8])
        s["committed"] = self.provenance()
        sets = [x for x in sets if x.get("id") != s["id"]]
        sets.append(s)
        self.upsert_session(identity, {"spike_labels": {"sets": sets}})
        return s


def delete_spike_set(self, identity, set_id):
    with _LOCK:
        store = dict(self.get_spike_labels(identity))
        sets = [x for x in store.get("sets", []) if x.get("id") != set_id]
        self.upsert_session(identity, {"spike_labels": {"sets": sets}})
        return sets


# ==========================================================================
# Workbench preferences -- small, shared, and synced like everything else
# ==========================================================================
# One file rather than one per setting: favourites, smart collections and
# "where was I" all live here, so a git pull brings the whole workbench over.
def _prefs_path(self):
    return self.prefs.mine(PREFS_BASE)


def get_prefs(self):
    """Compiled preferences, with the screen-shaped ones kept local.

    Favourites, smart collections and named views are worth sharing: they are
    about the project. Theme, density and pane sizes are about the monitor in
    front of you, and merging those means a colleague's push silently
    restyles your workbench. So they are read from this machine's own shard
    and never taken from anyone else's.
    """
    merged = self.prefs.read(PREFS_BASE) or {}
    merged.pop("_sync", None)
    own = shards._read_json(self._prefs_path()) or {}
    for key in PREFS_LOCAL:
        merged.pop(key, None)
        if key in own and own[key] is not None:
            merged[key] = own[key]
    return merged


def set_prefs(self, patch):
    """Shallow-merge a patch into preferences. A null value clears a key."""
    with _LOCK:
        rec = self.prefs.read(PREFS_BASE) or {}
        for k, v in (patch or {}).items():
            if v is None:
                rec.pop(k, None)
            else:
                rec[k] = v
        rec["updated"] = _now()
        self.prefs.write(PREFS_BASE, rec)
        return self.get_prefs()


# ==========================================================================
# Error triage
# ==========================================================================
# Errors themselves are append-only JSONL, so "resolved" is kept beside them
# keyed on the grouping signature -- one mark clears every past repeat and
# any future one that looks the same.
def _resolved_path(self):
    return self.triage.mine(TRIAGE_BASE)


def resolved_errors(self):
    return (self.triage.read(TRIAGE_BASE) or {}).get("marks") or {}


def resolve_error(self, signature, resolved=True, note=None):
    """Mark an error signature handled -- or un-mark it.

    Merged key by key, so two people triaging different errors on the same
    day both keep their marks instead of one overwriting the other.
    """
    with _LOCK:
        rec = self.triage.read(TRIAGE_BASE) or {"marks": {}}
        marks = rec.setdefault("marks", {})
        if resolved:
            marks[signature] = {"at": _now(), "by": _git_user() or _os_user(),
                                "machine": shards.machine_id(),
                                "note": note or ""}
        else:
            marks.pop(signature, None)
        self.triage.write(TRIAGE_BASE, rec)
        return self.resolved_errors()


for _fn in (record_activity, list_activity, activity_days,
            get_bookmarks, save_bookmark, delete_bookmark,
            get_spike_labels, save_spike_set, delete_spike_set,
            _prefs_path, get_prefs, set_prefs,
            _resolved_path, resolved_errors, resolve_error):
    setattr(Store, _fn.__name__, _fn)
