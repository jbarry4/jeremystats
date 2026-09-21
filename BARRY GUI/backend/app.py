"""
app.py -- The Jarvis local server.

Serves the single-page frontend and a JSON API over the repo and the data.
Binds to 127.0.0.1 only: this is a local workbench, not a service.

Cross-platform: everything OS-specific is delegated to sysinfo, so the same
code runs on Windows and macOS.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid

from flask import Flask, jsonify, request, send_from_directory, Response, send_file

from . import (analysis, cfc as cfcmod, cloud as cloudmod, cloudsync,
               compose, continuity as continuitymod, csc,
               healthlog as healthlogmod,
               incisor as incisormod,
               braces as bracesmod,
               bracesset as brsetmod,
               versions as versionsmod,
               panorama as panoramamod,
               panoramaset as pnsetmod,
               retime as retimemod,
               spectrum as spectrummod,
               device as devicemod,
               curation, discovery, eventbank, events, export, extras, ids,
               demo as demomod,
               dsimport,
               feedback as feedbackmod,
               presence as presencemod,
               profile as profilemod,
               layers, live, mice as micebook, nlx, notes as notesmod,
               people as peoplemod,
               pipeline, prewarm,
               probes as probebook, rebuild,
               registry, results, runner, sessreg, shards, spikesort, recipe as recipemod, store, thumbs, toolresults,
               storyboard, sysinfo, toolfeed, toolkit, vacc as vaccmod, vaccrun as vaccrunmod, video,
               warmcache)

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
WEB_DIR = os.path.join(APP_DIR, "web")
REPO_ROOT = os.path.abspath(os.path.join(APP_DIR, ".."))
LOGS_DIR = os.path.join(APP_DIR, "GUI_logs")

app = Flask(__name__, static_folder=None)

STORE = store.Store(LOGS_DIR, auto_stage=False)

# Last boot's answers to the three slow roll-ups, so this boot can show
# something in the time it takes to paint rather than in the time it takes to
# merge fifteen hundred shards. See warmcache.py -- in particular the five
# rules that bound when a cached byte can be seen at all.
#
# Stamped with the version and commit of the code that wrote it: an update
# that changes the shape of a payload must never hand the new interface last
# week's shape.
#
# Created here, armed nowhere. `arm()` is the launcher's call and only the
# launcher's, so a server started by the harness suite or by a script reads
# the store exactly as it always did.
WARM = warmcache.WarmCache(
    LOGS_DIR, stamp="|".join(str(x) for x in store._code_version()))

# Reports live beside the logs, one file each, sharded by machine -- same
# rule as everything else that gets edited, so two people never write the
# same file.
FEEDBACK = feedbackmod.Feedback(LOGS_DIR)
# How fast this machine is at each stage of a comodulogram, remembered between
# runs so the progress estimate is right on the rig as well as here. A cache of
# timings, nothing more -- deleting the file costs one wrong estimate.
cfcmod.configure(LOGS_DIR)
# Whether a recording is one continuous block or several, keyed on the
# reference file's size and mtime. A clean folder is decided by two records
# per channel, so the check runs on every health report rather than being a
# deep-check extra; the cache is what keeps a re-scan of the archive from
# re-reading the ones that are not clean.
continuitymod.configure(LOGS_DIR)
# Where the cluster is, and who this machine is on it. Reads two JSON files
# and nothing else -- no connection is made here, and none is ever made on
# the path of a request. `vacc.loop` below keeps the answer worth reading.
vaccmod.configure(LOGS_DIR)
# When each recording was last checked for gaps, by whom, and what the answer
# was. Kept because "which of these three hundred have a problem" is a
# question about the archive, and a check that runs when you open one session
# cannot answer it.
HEALTHLOG = healthlogmod.HealthLog(LOGS_DIR, STORE)
# Who you are, said once. Everything attributed -- curation, banking, layer
# sheets, figures, runs -- goes through STORE.provenance(), which prefers
# this over the git identity. Wired after the Store exists because it needs
# one, and back onto it so provenance() can see it.
PROFILE = profilemod.Profile(LOGS_DIR, STORE)
STORE.profile = PROFILE

# What this COMPUTER is called, in a record of its own. It used to be a
# profile field, which meant every path that saved a profile could rename
# the machine -- and that name is stamped on every error, action and run.
DEVICE = devicemod.Device(LOGS_DIR, STORE)
STORE.device = DEVICE
# Once, at start-up. Without it a machine that has already been named would
# revert to its hostname the first time it runs this build, and since the
# name is on every row the history would fork.
_adopted = DEVICE.adopt(PROFILE)
# So the profile dialog can SAY what this computer is called without being
# able to change it.
PROFILE.device = DEVICE

_CATALOG = {"items": [], "sections": [], "scanned": 0}
_SESSIONS = {}          # cache key -> opened session
_DESC_CACHE = {}
MAX_CACHED_SESSIONS = 6


# ==========================================================================
# Error plumbing -- every failure is logged with context and returned readably
# ==========================================================================
def fail(where, exc, status=400, context=None, user_message=None):
    """Log an error and return a JSON body the UI can show verbatim."""
    detail = traceback.format_exc(limit=8)
    rec = STORE.record_error(where, user_message or str(exc), detail, context)
    return jsonify({
        "ok": False,
        "error": user_message or str(exc),
        "type": type(exc).__name__,
        "where": where,
        "error_id": rec["id"],
    }), status


@app.errorhandler(Exception)
def unhandled(exc):
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return exc
    return fail("unhandled:" + request.path, exc, 500,
                {"path": request.path, "method": request.method})


# ==========================================================================
# Static
# ==========================================================================
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.before_request
def _trace_start():
    request.environ["_barry_t0"] = time.perf_counter()


@app.after_request
def no_cache(resp):
    # API answers are never cached; files are cached and revalidated.
    #
    # This set `no-store` on EVERYTHING, and `no-store` means the browser may
    # not keep the response at all -- not even to ask whether it is still
    # good. So all 2.5 MB of web/js and app.css came down again on every
    # load, over the same six connections the pollers are already using.
    #
    # `no-cache` is the header that means what was wanted here: keep it, but
    # ask before using it. The answer to the asking is a 304 with no body, so
    # editing a module and hitting refresh still shows the edit -- which in a
    # codebase with no build step is not negotiable, and is why this is not
    # `max-age`.
    #
    # Setting it only when the view has not spoken also stops this hook
    # overwriting a deliberate one. /api/results/file asks for a day of
    # caching because its URL carries a hash of the file's size and mtime, so
    # a changed figure is a different URL; that header was being replaced
    # with `no-store` here, one line after it was set, and every thumbnail in
    # the Results grid was fetched again on every render.
    if request.endpoint in ("static_files", "index"):
        resp.headers.setdefault("Cache-Control", "no-cache")
    elif "Cache-Control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-store"

    # Record what was asked for and how it went. A request that returns 200
    # with nothing useful in it leaves no other trace anywhere, and that is
    # exactly the kind of bug this is here to explain.
    path = request.path
    if extras.trace_worthy(path):
        t0 = request.environ.get("_barry_t0")
        rec = {
            "at": time.strftime("%H:%M:%S"),
            "method": request.method,
            "path": path,
            "status": resp.status_code,
            "ms": round((time.perf_counter() - t0) * 1000, 1) if t0 else None,
        }
        if request.method == "GET" and request.query_string:
            rec["query"] = request.query_string.decode("utf-8", "replace")[:400]
        elif request.method == "POST":
            body = request.get_json(silent=True)
            if isinstance(body, dict):
                rec["body"] = {k: _trace_brief(v) for k, v in body.items()}
        extras.TRACE.add(rec)
    return resp


def _trace_brief(v):
    """Keep a request body readable without copying a megabyte of samples."""
    if isinstance(v, (list, tuple)):
        return list(v) if len(v) <= 8 else "[%d items]" % len(v)
    if isinstance(v, dict):
        return "{%s}" % ", ".join(sorted(v)[:8])
    if isinstance(v, str) and len(v) > 200:
        return v[:200] + "..."
    return v


# ==========================================================================
# Catalog / scripts
# ==========================================================================
def refresh_catalog():
    items = registry.scan_repo(REPO_ROOT)
    _CATALOG["items"] = items
    _CATALOG["sections"] = registry.build_sections(items)
    _CATALOG["scanned"] = time.time()
    _DESC_CACHE.clear()
    return _CATALOG


@app.route("/api/catalog")
def api_catalog():
    if request.args.get("refresh") or not _CATALOG["items"]:
        refresh_catalog()
    sysdesc = sysinfo.describe()
    return jsonify({
        "ok": True,
        "repo": REPO_ROOT,
        "repo_name": os.path.basename(REPO_ROOT),
        "scanned": _CATALOG["scanned"],
        "sections": _CATALOG["sections"],
        "items": _CATALOG["items"],
        "matlab": runner.MATLAB_EXE,
        "matlab_release": sysinfo.matlab_release(runner.MATLAB_EXE),
        "python": sys.executable,
        "python_version": sysdesc["python"],
        "system": sysdesc,
        "logs_dir": LOGS_DIR,
        "ffmpeg": sysinfo.find_ffmpeg(),
    })


@app.route("/api/script")
def api_script():
    rel = request.args.get("rel", "")
    full = os.path.join(REPO_ROOT, rel.replace("/", os.sep))
    if not _inside_repo(full) or not os.path.isfile(full):
        return jsonify({"ok": False, "error": "Script not found: " + rel}), 404

    item = next((i for i in _CATALOG["items"] if i["rel"] == rel), None)
    lang = item["lang"] if item else _lang_of(full)

    key = rel + ":" + str(os.path.getmtime(full))
    if key not in _DESC_CACHE:
        _DESC_CACHE.clear()
        _DESC_CACHE[key] = registry.describe(full, lang)
    desc, params, extra = _DESC_CACHE[key]

    source = ""
    if request.args.get("source"):
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                source = fh.read(300_000)
        except OSError as exc:
            source = "(could not read: %s)" % exc

    return jsonify({"ok": True, "rel": rel, "lang": lang, "item": item,
                    "description": desc, "params": params, "extra": extra,
                    "source": source, "abspath": full})


def _lang_of(path):
    ext = os.path.splitext(path)[1].lower()
    return {".py": "python", ".m": "matlab", ".ipynb": "notebook"}.get(ext, "other")


def _inside_repo(path):
    try:
        return os.path.commonpath([os.path.abspath(path), REPO_ROOT]) == REPO_ROOT
    except ValueError:
        return False


# ==========================================================================
# Jobs + run history
# ==========================================================================
def _job_history_start(job):
    meta = job.meta or {}
    STORE.record_run({
        "id": job.id,
        "kind": meta.get("kind", "script"),
        "script": meta.get("rel") or job.label,
        "label": job.label,
        "lang": meta.get("lang"),
        "command": job.cmd,
        "cwd": job.cwd,
        "parameters": meta.get("parameters") or {},
        "overrides": meta.get("overrides") or [],
        "session": meta.get("session") or {},
        "stage": meta.get("stage"),
        "status": "running",
        "started": job.started,
    })


def _job_history_end(job):
    STORE.update_run(job.id, {
        "status": job.status,
        "returncode": job.returncode,
        "ended": job.ended,
        "duration_s": round(job.duration(), 3),
        "output_tail": job.tail(80),
    })
    if job.status == "failed":
        STORE.record_error(
            "run:" + (job.meta.get("rel") or job.label),
            "Run failed with exit code %s" % job.returncode,
            "\n".join(job.tail(40)),
            {"run_id": job.id, "command": job.cmd, "cwd": job.cwd})


runner.HOOKS["on_start"] = _job_history_start
runner.HOOKS["on_end"] = _job_history_end


@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(force=True) or {}
    rel = body.get("rel", "")
    full = os.path.join(REPO_ROOT, rel.replace("/", os.sep))
    if not _inside_repo(full) or not os.path.isfile(full):
        return jsonify({"ok": False, "error": "Script not found: " + rel}), 404
    try:
        params = body.get("params") or []
        job = runner.run_script(REPO_ROOT, rel, body.get("lang") or _lang_of(full),
                                params, body.get("extra") or {})
        job.meta["kind"] = "script"
        job.meta["parameters"] = {p["name"]: p.get("value") for p in params
                                  if p.get("changed") or p.get("required")}
        if body.get("session"):
            job.meta["session"] = body["session"]
    except Exception as exc:
        return fail("run:" + rel, exc, 400, {"rel": rel})
    return jsonify({"ok": True, "job": job.snapshot()})


@app.route("/api/jobs")
def api_jobs():
    return jsonify({"ok": True, "jobs": runner.list_jobs()})


@app.route("/api/job/<job_id>")
def api_job(job_id):
    job = runner.get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "No such job."}), 404
    since = int(request.args.get("since", 0))
    return jsonify({"ok": True, "job": job.snapshot(since)})


@app.route("/api/job/<job_id>/cancel", methods=["POST"])
def api_cancel(job_id):
    return jsonify({"ok": runner.cancel_job(job_id)})


# ==========================================================================
# Pipeline
# ==========================================================================
@app.route("/api/pipeline")
def api_pipeline():
    return jsonify({"ok": True, "tracks": pipeline.all_stages(),
                    "matlab": runner.MATLAB_EXE})


@app.route("/api/pipeline/check", methods=["POST"])
def api_pipeline_check():
    body = request.get_json(force=True) or {}
    folder = body.get("folder", "")
    track = body.get("track", "session")
    stages = pipeline.all_stages().get(track, [])
    return jsonify({
        "ok": True,
        "info": pipeline.inspect_folder(folder),
        "identity": ids.identify(folder) if folder else None,
        "stages": [pipeline.check_stage(s, folder) for s in stages],
    })


@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    body = request.get_json(force=True) or {}
    key = body.get("key")
    folder = body.get("folder", "")
    track = body.get("track", "session")

    stage = next((s for s in pipeline.all_stages().get(track, [])
                  if s["key"] == key), None)
    if not stage:
        return jsonify({"ok": False, "error": "Unknown stage: " + str(key)}), 404
    if stage.get("arg_folder") and not os.path.isdir(folder):
        return jsonify({"ok": False,
                        "error": "Pick a valid folder first."}), 400

    options = body.get("options") or {}
    params, extra = pipeline.build_stage_call(stage, folder, options,
                                              body.get("second"))
    try:
        job = runner.run_script(REPO_ROOT, stage["script"], stage["lang"],
                                params, extra)
    except Exception as exc:
        return fail("pipeline:" + key, exc, 400,
                    {"stage": key, "folder": folder})

    job.label = stage["title"]
    job.meta.update({
        "kind": "pipeline", "stage": key, "track": track,
        "parameters": dict(options, folder=folder),
        "session": _identity_brief(folder),
    })
    return jsonify({"ok": True, "job": job.snapshot()})


def _identity_brief(folder):
    if not folder:
        return {}
    ident = ids.identify(folder)
    return {k: ident.get(k) for k in
            ("key", "loose_key", "label", "mouse", "session", "group", "path")}


# ==========================================================================
# Session discovery
# ==========================================================================
@app.route("/api/discover/start", methods=["POST"])
def api_discover_start():
    body = request.get_json(force=True) or {}
    root = body.get("root", "")
    if not os.path.isdir(root):
        return jsonify({"ok": False,
                        "error": "Not a folder: " + str(root)}), 400
    try:
        job = discovery.start_scan(
            root, int(body.get("max_depth", discovery.MAX_DEPTH)),
            bool(body.get("read_headers", True)))
        remember_root(root)
    except Exception as exc:
        return fail("discover", exc, 400, {"root": root})
    return jsonify({"ok": True, "job": job.snapshot()})


@app.route("/api/discover/<job_id>")
def api_discover_status(job_id):
    job = discovery.get_scan(job_id)
    if not job:
        return jsonify({"ok": False, "error": "No such scan."}), 404
    include = job.status == "done"
    data = job.snapshot(include_sessions=include)
    if include:
        # A finished scan is the one moment Jarvis has the whole picture of a
        # drive, so everything it walked past gets written into the registry
        # -- not just the handful anyone happens to open. Done once per job:
        # the status route is polled, and re-registering on every poll would
        # rewrite two hundred files a second.
        if not getattr(job, "_registered", False):
            job._registered = True
            try:
                found = data.get("sessions") or []
                # Anything the assessment cannot vouch for is held back
                # rather than registered. Seven folders on the lab drives
                # are 64 files of header and no data -- an aborted
                # acquisition is indistinguishable from a real recording in
                # a tree, and once registered nothing questions it again.
                usable = [x for x in found
                          if (x.get("quality") or {}).get("usable", True)
                          or x.get("path") in ACCEPTED_FOLDERS]
                job.held_back = [{
                    "path": x.get("path"),
                    "name": x.get("name"),
                    "label": (x.get("identity") or {}).get("label"),
                    "channels": x.get("channels"),
                    "quality": x.get("quality"),
                } for x in found if x not in usable]
                job.reg_new, job.reg_seen = REG.ingest(
                    usable, scan_id=job.id, root=job.root)
                STORE.record_activity([{
                    "action": "registry.scan",
                    "detail": {"root": job.root, "found": job.reg_seen,
                               "new": job.reg_new, "scan": job.id},
                }])
            except Exception as exc:                       # noqa: BLE001
                STORE.record_error("registry/ingest", str(exc), None,
                                   {"root": job.root})
        data["held_back"] = getattr(job, "held_back", [])
        data["registered"] = {"new": getattr(job, "reg_new", 0),
                              "seen": getattr(job, "reg_seen", 0)}

        # Attach any stored record (bad channels, notes) to each session, and
        # the permanent id it now certainly has.
        stored = STORE.all_sessions()
        for s in data.get("sessions", []):
            rec, how = ids.match(s["identity"], stored)
            s["gid"] = (rec or {}).get("gid")
            s["stored"] = {
                "match": how,
                "bad_channels": (rec or {}).get("bad_channels", []),
                "notes": (rec or {}).get("notes"),
            } if rec else None
    return jsonify({"ok": True, "job": data})


@app.route("/api/discover/<job_id>/cancel", methods=["POST"])
def api_discover_cancel(job_id):
    job = discovery.get_scan(job_id)
    if job:
        job.stop()
    return jsonify({"ok": bool(job)})


# ==========================================================================
# CSC / Xplorefinder sessions
# ==========================================================================
def _even_only_arg(body):
    """None when the caller did not say, so the recording decides.

    `bool(body.get("even_only", True))` turned "not specified" into "yes,
    skip the odd channels", which is how half of every 64-channel recording
    went unlooked-at. Absent now means absent.
    """
    v = (body or {}).get("even_only")
    return None if v is None else bool(v)


def _session_for(path, even_only=None, invert=True):
    key = "%s|%s|%s" % (os.path.abspath(path), even_only, invert)
    if key not in _SESSIONS:
        sess = csc.open_session(path, even_only=even_only, invert=invert)
        if not sess.get("ok"):
            return None, sess
        if len(_SESSIONS) >= MAX_CACHED_SESSIONS:
            _SESSIONS.pop(next(iter(_SESSIONS)))
        _SESSIONS[key] = sess
    return _SESSIONS[key], None


def _gid_for_path(path):
    """The permanent id of whatever recording lives at this path.

    One pass over the merged registry, matching any path a record carries --
    the registry unions paths across machines, so the row that answers may
    have been written by a colleague on a mount this machine has never had.
    """
    want = os.path.normcase(os.path.abspath(path or ""))
    if not want:
        return None
    try:
        for rec in (REG.all() or []):
            for known in (rec.get("paths") or []):
                if isinstance(known, str) and \
                        os.path.normcase(os.path.abspath(known)) == want:
                    return rec.get("gid")
    except Exception:                                    # noqa: BLE001
        pass
    return None


def _body_session(body):
    sess, err = _session_for(body.get("path", ""),
                             _even_only_arg(body),
                             bool(body.get("invert", True)))
    # The gid, here, rather than only when somebody happened to come through
    # /api/csc/open first.
    #
    # `_incisor_remember` files a finished scan under the gid and returns
    # quietly when there is not one, so a scan reached by any other route
    # computed its answer, put it in the in-process cache, and never wrote
    # it down -- lost on restart, never synced, and never visible to a
    # colleague. Measured: the vault held zero records while scans were
    # completing fine.
    if sess is not None and not sess.get("gid"):
        sess["gid"] = _gid_for_path(sess.get("path"))
    return sess, err


@app.route("/api/csc/open", methods=["POST"])
def api_csc_open():
    body = request.get_json(force=True) or {}
    path = body.get("path", "")
    sess, err = _session_for(path, _even_only_arg(body),
                             bool(body.get("invert", True)))
    if err:
        return jsonify(err), 400

    if sess.get("source") == "demo":
        # A demo path has no mouse or session in it to parse, so the
        # identity comes from its definition. Without this the tab reads
        # "unidentified" and every attachment keyed on the recording -- the
        # curation set most of all -- has nothing to hang off.
        spec = demomod.get(sess["path"]) or {}
        identity = {
            "key": "demo_%s" % spec.get("id"),
            "loose_key": "demo_%s" % spec.get("id"),
            "label": spec.get("label"),
            "project": spec.get("project"),
            "mouse": spec.get("mouse"),
            "session": spec.get("session"),
            "start": spec.get("date", "") + "T00:00:00",
            "gid": spec.get("gid"),
            "confidence": "exact",
            "demo": True,
        }
    else:
        identity = ids.identify(
            sess["path"], header_time=_header_time(sess))
    # Opening a recording is also laying eyes on it: make sure it has a
    # permanent id and a project before anything else reads the record.
    # Not for a demo: it is not a discovery, and writing it in would leave
    # two fake sessions in every clone's registry for good.
    try:
        if sess.get("source") != "demo":
            REG.ensure(identity)
    except Exception as exc:                               # noqa: BLE001
        STORE.record_error("registry/ensure", str(exc), None, {"path": path})
    stored, how = STORE.get_session(identity)

    # Honour a remembered even-only, when the caller did not say.
    #
    # Which channels a probe is on is a fact about the recording, not a view
    # preference, so it is stored with the session -- but the identity that
    # finds that record needs the file open first, and by then it has been
    # opened with the measured default. So: if nothing was asked for and the
    # record remembers something different, open it again the right way.
    # _session_for caches, so this costs one extra header read the first
    # time a recording is opened in a process and nothing after that.
    if _even_only_arg(body) is None and stored:
        want = (stored.get("view_state") or {}).get("even_only")
        if want is not None and bool(want) != bool(sess.get("even_only")):
            again, err2 = _session_for(path, bool(want),
                                       bool(body.get("invert", True)))
            if not err2 and again:
                sess = again

    out = {k: v for k, v in sess.items() if k != "channels"}
    # A demo has no stored record, so its gid comes off the identity. Every
    # attachment -- the curation set most of all -- is keyed on this.
    out["gid"] = (stored or {}).get("gid") or identity.get("gid")
    # Carried on the identity too, so two windows that opened the same
    # recording by different paths agree on what to call it -- which is what
    # the cross-window channels are keyed on.
    if out["gid"]:
        identity = dict(identity, gid=out["gid"])
    out["channels"] = [{kk: vv for kk, vv in c.items() if kk != "file"}
                       for c in sess["channels"]]
    out["identity"] = identity
    out["stored"] = stored
    out["stored_match"] = how
    out["bad_channels"] = (stored or {}).get("bad_channels", [])
    folder = sess["path"] if os.path.isdir(sess["path"]) else os.path.dirname(sess["path"])
    out["media"] = video.find_media(folder)
    out["nev"] = _find_nev(folder)
    out["view_state"] = (stored or {}).get("view_state") or {}
    out["probe"] = _probe_for(stored)
    out["probe_source"] = (stored or {}).get("probe_source") or (
        "view" if ((stored or {}).get("view_state") or {}).get("probe")
        else ("guessed" if out["probe"] != "h3" else None))
    out["bookmarks"] = (stored or {}).get("bookmarks", [])
    out["spike_sets"] = ((stored or {}).get("spike_labels") or {}).get("sets", [])
    out["event_classes"] = (stored or {}).get("event_classes") or {}
    return jsonify(out)


def _probe_for(stored):
    """Which probe template a recording was made with, from one place.

    Three answers in descending order of authority, and the order is the
    point:

      1. `probe` on the record -- somebody said so, and it travels between
         machines with everything else about the recording.
      2. `view_state.probe` -- where the choice used to live. Read so that
         a recording somebody set up before this field existed does not
         quietly revert to H3 on its next open.
      3. `probes.suggest(n_channels)` -- a guess, and only ever one that a
         number can support: 128 channels is two 64-contact implants far
         more often than it is one 128-contact array in this lab.

    Never guesses past a real answer, and never writes. Filing the guess
    would turn it into a fact nobody could find again, which is the same
    argument `banks_for` makes about leaving `region` blank.
    """
    stored = stored or {}
    said = stored.get("probe")
    if said and probebook.get(said):
        return str(said).lower()
    was = (stored.get("view_state") or {}).get("probe")
    if was and probebook.get(was):
        return str(was).lower()
    return probebook.suggest(stored.get("n_channels"))


def _find_nev(folder):
    """Cheetah's own event files, so they can be offered without a file picker."""
    out = []
    try:
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(".nev"):
                full = os.path.join(folder, name)
                try:
                    out.append({"name": name, "path": full,
                                "bytes": os.path.getsize(full)})
                except OSError:
                    continue
    except OSError:
        pass
    return out


def _header_time(sess):
    try:
        from . import nlx
        ch = sess["channels"][0]
        if ch.get("file"):
            return nlx.header_start_time(nlx.read_header(ch["file"]))
    except Exception:
        pass
    return None


@app.route("/api/csc/window", methods=["POST"])
def api_csc_window():
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        win = csc.get_window(
            sess, float(body.get("t0", 0)), float(body.get("t1", 10)),
            channels=body.get("channels"), px=int(body.get("px", 1400)),
            highpass=float(body.get("highpass", 0) or 0),
            lowpass=float(body.get("lowpass", 0) or 0),
            notch=float(body.get("notch", 0) or 0),
            mode=body.get("mode", "voltage"),
            spacing_um=float(body.get("spacing_um", 50) or 50),
            full_rate=bool(body.get("full_rate")))
    except Exception as exc:
        return fail("csc/window", exc, 400, {"path": body.get("path")})
    if not win.get("ok"):
        return jsonify(win), 400
    # The same steps a panel reports, so the trace view can wear the same
    # badge. This route does not go through `render_panel`.
    steps = analysis.window_steps(win.get("sampling"))
    win["sampling"] = steps
    win["downsampled"] = any(x.get("lossy") for x in steps)
    win["reversible"] = any(x.get("lossy") and x.get("reversible", True)
                            for x in steps)
    win["full_rate"] = bool(body.get("full_rate"))
    bad = set(int(b) for b in (body.get("bad_channels") or []))
    if bad:
        for s in win.get("series", []):
            if s["number"] in bad:
                s["bad"] = True
    return jsonify(win)


@app.route("/api/csc/export", methods=["POST"])
def api_csc_export():
    body = request.get_json(force=True) or {}
    fmt = (body.get("format") or "png").lower()
    if fmt not in export.MIME:
        return jsonify({"ok": False, "error": "Unsupported format."}), 400
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        blob = export.render_window(sess, body, fmt=fmt,
                                    dpi=int(body.get("dpi", 200)))
    except Exception as exc:
        return fail("csc/export", exc, 400, {"format": fmt})

    name = "%s_%.2f-%.2fs.%s" % (
        os.path.splitext(sess.get("name", "csc"))[0],
        float(body.get("t0", 0)), float(body.get("t1", 0)), fmt)
    return Response(blob, mimetype=export.MIME[fmt], headers={
        "Content-Disposition": 'attachment; filename="%s"' % name})


# ==========================================================================
# Bad channels + session records
# ==========================================================================
@app.route("/api/session/bad", methods=["POST"])
def api_session_bad():
    body = request.get_json(force=True) or {}
    identity = body.get("identity")
    if not identity or identity.get("mouse") is None:
        return jsonify({
            "ok": False,
            "error": "This recording's mouse/session could not be identified "
                     "from its path, so bad channels cannot be remembered "
                     "across machines. Rename the folder to include m<N> and "
                     "s<N>, or mark channels per-session only."}), 400
    try:
        rec = STORE.set_bad_channels(identity, body.get("bad_channels") or [],
                                     body.get("note"))
    except Exception as exc:
        return fail("session/bad", exc, 400, {"identity": identity})
    return jsonify({"ok": True, "session": rec})


@app.route("/api/session/bad-for-path", methods=["POST"])
def api_session_bad_for_path():
    """The same thing as `/api/session/bad`, for a caller holding a path.

    The trace view has the identity because it opened the recording. A tool
    panel does not -- Incisor picks a registry row and a folder -- and
    making it open the whole recording just to learn its mouse and session
    is a lot of reading for a checkbox. The identity is worked out here
    instead, from the same path and header the scan itself uses, so both
    ways of marking a channel bad land on one record.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    identity = ids.identify(sess["path"], header_time=_header_time(sess))
    if not identity or identity.get("mouse") is None:
        return jsonify({
            "ok": False,
            "error": "This recording's mouse and session could not be read "
                     "from its path, so bad channels cannot be remembered "
                     "for it. Rename the folder to include m<N> and s<N>, "
                     "or mark them in the trace view."}), 400
    try:
        rec = STORE.set_bad_channels(identity,
                                     body.get("bad_channels") or [],
                                     body.get("note"))
    except Exception as exc:                             # noqa: BLE001
        return fail("session/bad-for-path", exc, 400,
                    {"path": sess.get("path")})
    return jsonify({"ok": True, "session": rec,
                    "bad_channels": (rec or {}).get("bad_channels") or []})


@app.route("/api/session/note", methods=["POST"])
def api_session_note():
    """Free-text notes and the quality flag, both keyed on session identity."""
    body = request.get_json(force=True) or {}
    identity = body.get("identity") or {}
    patch = {}
    if "notes" in body:
        patch["notes"] = body.get("notes", "")
    if "quality" in body:
        q = body.get("quality")
        if q not in (None, "", "good", "review", "exclude"):
            return jsonify({"ok": False,
                            "error": "Unknown quality flag: %s" % q}), 400
        patch["quality"] = q or ""
    if not patch:
        return jsonify({"ok": False, "error": "Nothing to save."}), 400
    try:
        rec = STORE.upsert_session(identity, patch)
    except Exception as exc:
        return fail("session/note", exc, 400)
    STORE.record_activity([{
        "action": "session.annotate",
        "detail": {k: v for k, v in patch.items()},
        "session": {k: identity.get(k) for k in ("key", "label", "mouse",
                                                 "session")},
    }])
    return jsonify({"ok": True, "session": rec})


@app.route("/api/session/events", methods=["POST"])
def api_session_events():
    """Save the event-class scheme (names, colors, visibility) for a session.

    Kept with the session rather than globally: "TTL 1" means something
    different on one rig than another, and the whole point is that everyone
    looking at this recording sees the same scheme.
    """
    body = request.get_json(force=True) or {}
    identity = body.get("identity") or {}
    if identity.get("mouse") is None and not identity.get("key"):
        return jsonify({"ok": True, "saved": False,
                        "reason": "unidentified session"})
    try:
        rec = STORE.upsert_session(
            identity, {"event_classes": body.get("event_classes") or {}})
    except Exception as exc:
        return fail("session/events", exc, 400)
    return jsonify({"ok": True, "saved": True,
                    "event_classes": rec.get("event_classes", {})})


@app.route("/api/sessions")
def api_sessions():
    # REG.all() rather than STORE.all_sessions(): the same records, merged
    # the same way, but cached against the shard directory's signature
    # instead of re-read from 1510 files on every call. Measured: 4.1 s a
    # call against 0.1 s. Safe here because nothing downstream edits what it
    # is handed -- these go straight out as JSON.
    return jsonify({"ok": True, "sessions": REG.all()})


@app.route("/api/identify")
def api_identify():
    path = request.args.get("path", "")
    identity = ids.identify(path)
    stored, how = STORE.get_session(identity)
    return jsonify({"ok": True, "identity": identity,
                    "stored": stored, "match": how})


# ==========================================================================
# History / errors / sync
# ==========================================================================
@app.route("/api/history")
def api_history():
    return jsonify({"ok": True, "runs": STORE.list_runs(
        limit=int(request.args.get("limit", 300)),
        session_key=request.args.get("session") or None,
        script=request.args.get("script") or None,
        status=request.args.get("status") or None)})


@app.route("/api/history/<run_id>")
def api_history_one(run_id):
    rec = STORE.get_run(run_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such run."}), 404
    return jsonify({"ok": True, "run": rec})


@app.route("/api/errors")
def api_errors():
    return jsonify({"ok": True,
                    "errors": STORE.list_errors(
                        limit=int(request.args.get("limit", 300)),
                        day=request.args.get("day") or None),
                    "days": STORE.error_days()})


@app.route("/api/errors/test", methods=["POST"])
def api_errors_test():
    """Write a sample error so the log viewer can be verified end to end."""
    rec = STORE.record_error("selftest", "Test error from the Errors panel",
                             "No stack trace -- this entry was created on purpose.",
                             {"source": "ui"})
    return jsonify({"ok": True, "error": rec})


def _sync_status_body():
    """The EXPENSIVE half of the answer, and only that half.

    Measured cold: 8.2 s, effectively all of it `STORE.index()` merging the
    session shards for the first time in this process; warm it is 0.02 s.
    That one number is the whole reason this route was worth warming, and
    the rest of what the route returns is measured in tens of
    milliseconds.

    So the rest is deliberately NOT in here. Everything below costs
    nothing, and two of them -- what this process started at, and what has
    been edited since it did -- are facts about this process rather than
    about the store. Yesterday's answers to those are not stale, they are
    wrong: a cached `code_changed` from a session where somebody edited the
    source would raise "restart Jarvis, it is running older code" on a
    Jarvis that had started ten seconds ago.

    Keeping them out also makes the fingerprint mean something. With
    `started_at` in the body, every boot differs from every other boot by
    construction, the comparison always says "changed", and the page always
    refetches a quarter of a megabyte to be told what it already had.
    """
    idx = None
    try:
        # index() rebuilds only when the store has actually changed; this
        # route is hit on every boot and after every export.
        idx = STORE.index()
    except Exception:
        pass
    return {"ok": True, "root": LOGS_DIR, "index": idx,
            "auto_stage": STORE.auto_stage}


@app.route("/api/sync/status")
def api_sync_status():
    body, how = WARM.serve("sync_status", _sync_status_body,
                           fresh=bool(request.args.get("fresh")))
    body = dict(body)
    # Always live, cache or no cache. 0.26 s between them, against the 8 s
    # the index costs, and every one of them is either about this process or
    # about the working tree as it is right now.
    body["git"] = STORE.git_status()
    # Carried on a poll that already happens, so noticing that Jarvis needs
    # restarting costs no extra request.
    body["code_changed"] = _code_changed()
    body["started_at"] = _STARTED_AT
    body["conflicts"] = conflict_audit()
    body["warm"] = WARM.marker("sync_status", how)
    return jsonify(body)


def conflict_audit():
    """Can anything in GUI_logs produce a merge conflict?

    The answer should always be no, and saying so where people can see it is
    the point: a store added later that forgets to shard its files shows up
    here the first time it writes one, rather than the first time two people
    pull. Same check as tools/conflict_check.py, run from inside.
    """
    shared, machines, n = [], set(), 0
    for folder, dirs, files in os.walk(LOGS_DIR):
        dirs[:] = [d for d in dirs
                   if d not in (".cache", "__pycache__")
                   and not d.startswith(".")]
        for name in files:
            if name.startswith("."):
                continue          # configuration, not a record
            rel = os.path.relpath(os.path.join(folder, name),
                                  LOGS_DIR).replace("\\", "/")
            n += 1
            if rel.startswith("runs/") or name in ("README.md", ".gitignore"):
                continue
            stem = name.rsplit(".", 1)[0]
            if shards.SIGIL in stem:
                machines.add(stem.rsplit(shards.SIGIL, 1)[1])
            elif len(shared) < 12:
                shared.append(rel)
    return {
        "ok": not shared,
        "files": n,
        "shared": shared,
        "machines": sorted(machines),
        "mine": shards.machine_id(),
    }


# ==========================================================================
# The warm start
# ==========================================================================
# When the roll-up was built, which is not part of what it says.
#
# `STORE.index()` stamps itself, and a fresh process always rebuilds -- so
# without this every boot differed from every other boot by construction,
# every boot was reported as changed, and the page refetched a quarter of a
# megabyte each time to be handed a different timestamp over identical
# counts. Measured: with it declared, two consecutive boots compare equal.
#
# The counts themselves are emphatically NOT excluded. A change in what the
# store holds is the one thing this whole mechanism exists to notice.
WARM.volatile("sync_status", ["index.generated"])


@app.before_request
def _warm_watch_writes():
    """The window closes the moment somebody does something.

    Here rather than in each route, because the rule is about the person and
    not about the endpoint: a route added next year inherits it without
    anybody remembering to opt in. warmcache.BOOT_CHATTER lists the three
    POSTs the interface makes on its own way up.
    """
    if request.method != "GET" and request.path.startswith("/api/"):
        WARM.note_write(request.path)


@app.route("/api/warm/state")
def api_warm_state():
    """Which warmed answers have been recomputed for real, and which of them
    turned out to differ from what the page was shown.

    Polled by the page for as long as `warming` is true, and it has to be
    cheap enough to poll: no store reads, no disk, just what the prime
    thread has recorded. A name appears here once its live value is in hand;
    the value says whether refetching it would change anything, which on an
    ordinary boot is false for all three and the page does nothing at all.
    """
    return jsonify(dict({"ok": True}, **WARM.state()))


def warm_start(window_s=warmcache.WINDOW_S):
    """Open the warm window and start recomputing behind it.

    Called by start.py, which is to say by "Wake up Jarvis", and by nothing
    else. A server brought up by the harness suite, by vacc_run or by a
    script that imports this module never calls it, so those read the store
    live exactly as they always have -- a test that measures the cache when
    it means to measure the store is a test that has stopped testing.

    The order is the order they are wanted in: the sync chip and the error
    badge are on screen from the first frame, VACC decides whether the rail
    chip appears, and the registry is wanted the moment somebody opens
    Sessions. It also happens to be the cheapest order -- all three read the
    session shards, and the first one to do it pays for the other two.
    """
    WARM.arm(window_s)
    WARM.prime([
        ("sync_status", _sync_status_body),
        ("vacc_knows", _vacc_knows_body),
        ("registry", _registry_body),
    ])


@app.route("/api/sync/reindex", methods=["POST"])
def api_sync_reindex():
    try:
        return jsonify({"ok": True, "index": STORE.rebuild_index()})
    except Exception as exc:
        return fail("sync/reindex", exc, 400)


# ==========================================================================
# Presets
# ==========================================================================
VALID_PRESETS = {"filters", "imports", "layouts"}


@app.route("/api/presets/<kind>", methods=["GET", "POST", "DELETE"])
def api_presets(kind):
    if kind not in VALID_PRESETS:
        return jsonify({"ok": False,
                        "error": "Unknown preset kind: " + kind}), 404
    if request.method == "GET":
        return jsonify({"ok": True, "presets": STORE.get_presets(kind)})

    body = request.get_json(force=True) or {}
    try:
        if request.method == "DELETE":
            items = STORE.delete_preset(kind, body.get("id"))
            return jsonify({"ok": True, "presets": items})
        preset = body.get("preset") or body
        if not (preset.get("name") or "").strip():
            return jsonify({"ok": False, "error": "Give the preset a name."}), 400
        saved = STORE.save_preset(kind, preset)
        return jsonify({"ok": True, "preset": saved,
                        "presets": STORE.get_presets(kind)})
    except Exception as exc:
        return fail("presets/" + kind, exc, 400)


# ==========================================================================
# Events
# ==========================================================================
@app.route("/api/events/inspect", methods=["POST"])
def api_events_inspect():
    body = request.get_json(force=True) or {}
    path = body.get("path", "")
    fs = body.get("fs")
    try:
        info = events.inspect(path, fs=fs, n_samples=body.get("n_samples"),
                              duration_s=body.get("duration_s"))
    except events.ImportError_ as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("events/inspect", exc, 400, {"path": path})
    info["ok"] = True
    return jsonify(info)


@app.route("/api/events/apply", methods=["POST"])
def api_events_apply():
    body = request.get_json(force=True) or {}
    try:
        res = events.apply_mapping(
            body.get("path", ""), body.get("mapping") or {},
            float(body.get("fs") or 0), body.get("n_samples"),
            body.get("duration_s"))
    except events.ImportError_ as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("events/apply", exc, 400, {"path": body.get("path")})
    return jsonify(res)


# ==========================================================================
# Analysis panels + figure composition
# ==========================================================================
@app.route("/api/panels")
def api_panels():
    return jsonify({"ok": True, "panels": analysis.PANELS,
                    "colormaps": [dict(c, swatch=analysis.colormap_swatch(c["id"], 24))
                                  for c in analysis.COLORMAPS],
                    "pages": [{"id": k, "w": v[0], "h": v[1]}
                              for k, v in compose.PAGE_PRESETS.items()]})


@app.route("/api/panel", methods=["POST"])
def api_panel():
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    # Everything that changes the picture is in the spec, so a repeat of the
    # same request is answered from memory -- which is most of curation,
    # where you go back and forth over the same candidates.
    hit = prewarm.get(sess, body)
    if hit is not None:
        return jsonify(dict(hit, cached=True))
    try:
        with prewarm.Busy():
            out = analysis.render_panel(sess, body)
        prewarm.put(sess, body, out)
        return jsonify(out)
    except analysis.PanelError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("panel:" + str(body.get("panel")), exc, 400,
                    {"panel": body.get("panel")})


@app.route("/api/panel/prewarm", methods=["POST"])
def api_panel_prewarm():
    """Render the windows we are probably about to be asked for.

    The client sends the spec it is currently drawing plus the times it
    expects to visit -- the events in the recording, or the undecided
    candidates in a curation set. Each becomes a window centred on that
    time, rendered in the background and only while nothing on screen is
    waiting.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    spec = dict(body.get("spec") or {})
    times = body.get("times") or []
    if not spec or not times:
        return jsonify({"ok": True, "queued": 0, "reason": "nothing to warm"})
    try:
        span = float(spec.get("t1", 0)) - float(spec.get("t0", 0))
    except (TypeError, ValueError):
        span = 0.0
    if not (span > 0):
        return jsonify({"ok": False, "error": "That spec has no time span."}), 400

    limit = int(body.get("limit") or 16)
    starts = prewarm.windows_around(times, span, limit=max(1, min(limit, 64)),
                                    t_end=sess.get("duration_s"))
    specs = []
    for t0 in starts:
        one = dict(spec)
        one["t0"] = t0
        one["t1"] = t0 + span
        specs.append(one)
    queued = prewarm.request(sess, specs,
                             supersede=bool(body.get("supersede", True)))
    return jsonify({"ok": True, "queued": queued, "considered": len(specs)})


@app.route("/api/panel/cache")
def api_panel_cache():
    """What the panel cache is holding. Diagnostic; ?clear=1 empties it."""
    if request.args.get("clear"):
        prewarm.clear()
    return jsonify({"ok": True, "cache": prewarm.stats()})


# ==========================================================================
# Cross-frequency coupling
#
# A comodulogram is not a panel. A panel is a fraction of a second and
# redraws when the window moves; this is two seconds without surrogates and
# half a minute with them, so it cannot happen inside the request that asked
# for it and it has to be able to say where it has got to.
#
# Hence a job: POST starts one and gets an id back at once, the client polls
# the id, and the result is fetched when the job says it is done. The same
# shape as /api/job/<id> for script runs, deliberately, so the client's
# polling is one idiom rather than two.
# ==========================================================================
def _cfc_spec(body, sess):
    """Fill a request out into the full spec the cache is keyed on.

    Every default lives here rather than in the renderer, so the cache key and
    the thing that ran can never be built from different numbers -- which is
    how a cache returns somebody else's answer.
    """
    spec = {
        "path": sess.get("path"),
        "channel": body.get("channel"),
        "t0": float(body.get("t0", 0) or 0),
        "t1": float(body.get("t1", 0) or 0),
        # Tort's grid unless the caller names another. See cfc.TORT_*.
        "slow_lo": float(body.get("slow_lo") or cfcmod.TORT_PHASE[0]),
        "slow_hi": float(body.get("slow_hi") or cfcmod.TORT_PHASE[1]),
        "slow_step": float(body.get("slow_step") or cfcmod.TORT_PHASE[2]),
        "slow_bw": float(body.get("slow_bw") or cfcmod.TORT_PHASE_BW),
        "fast_lo": float(body.get("fast_lo") or cfcmod.TORT_AMP[0]),
        "fast_hi": float(body.get("fast_hi") or cfcmod.TORT_AMP[1]),
        "fast_step": float(body.get("fast_step") or cfcmod.TORT_AMP[2]),
        "fast_bw": float(body.get("fast_bw") or cfcmod.TORT_AMP_BW),
        "nsurr": int(body.get("nsurr", 0) or 0),
        "seed": int(body.get("seed", 42) or 42),
        "nbin": int(body.get("nbin", cfcmod.NBIN) or cfcmod.NBIN),
        "target_fs": float(body.get("target_fs", 3000) or 3000),
        "highpass": float(body.get("highpass", 0) or 0),
        "lowpass": float(body.get("lowpass", 0) or 0),
        "notch": float(body.get("notch", 0) or 0),
        # Jet: MATLAB's default when CallerRoutine.m was written, so a
        # map from here reads like a map from the paper.
        "cmap": body.get("cmap") or "jet",
        "invert": bool(body.get("invert", True)),
    }
    if spec["channel"] is None:
        picked = body.get("channels") or []
        spec["channel"] = int(picked[0]) if picked else 0
    spec["channel"] = int(spec["channel"])
    return spec


@app.route("/api/cfc/estimate", methods=["POST"])
def api_cfc_estimate():
    """What that run would cost, before anybody commits to it.

    Shown next to the surrogate checkbox. Turning surrogates on multiplies the
    wait by about ten, and a number there is the difference between a decision
    and a surprise. The rates behind it are what this machine actually
    measured on its last run, not a guess.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    spec = _cfc_spec(body, sess)
    out = cfcmod.estimate(spec)
    out["ok"] = True
    out["cached"] = cfcmod.cache_get(cfcmod.cache_key(spec)) is not None
    return jsonify(out)


@app.route("/api/cfc/comodulogram", methods=["POST"])
def api_cfc_comodulogram():
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    spec = _cfc_spec(body, sess)

    key = cfcmod.cache_key(spec)
    hit = cfcmod.cache_get(key)
    if hit is not None and not body.get("force"):
        # Comparing two windows means going back and forth between them, and
        # paying half a minute again for a map already made is the difference
        # between a tool somebody uses and one they use once.
        return jsonify({"ok": True, "cached": True, "result": hit})

    n_slow = len(cfcmod.grid(spec["slow_lo"], spec["slow_hi"], spec["slow_step"]))
    n_fast = len(cfcmod.grid(spec["fast_lo"], spec["fast_hi"], spec["fast_step"]))
    plan = [("read", 1), ("decimate", 1),
            ("slow bank", n_slow), ("fast bank", n_fast),
            ("modulation index", n_slow * n_fast)]
    if spec["nsurr"]:
        plan.append(("surrogates", n_slow * spec["nsurr"]))
    plan.append(("draw", 1))

    def work(job):
        out = analysis.run_comodulogram(sess, spec, job)
        cfcmod.cache_put(key, out)
        return out

    # How big the window is, so the progress estimate is comparable between a
    # ten-second look and a two-minute one.
    job = cfcmod.start(spec, plan, work, cfcmod.msamples(spec))
    STORE.record_activity([{
        "action": "cfc.comodulogram",
        "detail": {"t0": round(spec["t0"], 2), "t1": round(spec["t1"], 2),
                   "channel": spec["channel"], "nsurr": spec["nsurr"],
                   "cells": n_slow * n_fast},
    }])
    return jsonify({"ok": True, "cached": False, "job": job.snapshot()})


def _spectrum_spec(body, sess):
    """What the run is being asked for, with the defaults filled in.

    An empty window means the whole recording, which is the thing this view
    is for -- "where does the power sit in this session" is not a question
    about a ten-second look.
    """
    dur = float(sess.get("duration_s") or 0.0)
    t0 = float(body.get("t0") or 0.0)
    t1 = float(body.get("t1") or 0.0)
    if t1 <= t0:
        t0, t1 = 0.0, dur
    chans = body.get("channels")
    if not chans:
        # Whatever the session has selected, or the first channel. Never all
        # sixty-four by accident: that is a minute of work nobody asked for.
        chans = [c["index"] for c in (sess.get("channels") or [])][:1]
    return {
        "path": sess.get("path"),
        "channels": [int(c) for c in chans],
        "t0": max(0.0, t0),
        "t1": min(t1, dur) if dur else t1,
        "fmax": float(body.get("fmax") or spectrummod.DEFAULT_FMAX),
        "segment_s": float(body.get("segment_s") or 8.0),
        "even_only": bool(sess.get("even_only")),
        # Mains. `None` means "not said", which is 60 Hz here; an explicit
        # 0 means somebody turned it off and wants the interference shown.
        "line_hz": (spectrummod.LINE_HZ if body.get("line_hz") is None
                    else float(body.get("line_hz") or 0.0)),
        "parameterize": bool(body.get("parameterize", True)),
    }


@app.route("/api/spectrum/estimate", methods=["POST"])
def api_spectrum_estimate():
    """What a run would do, and how long it would take here.

    Asked before anything is read, so the window can say what it is about to
    cost rather than going quiet for a minute.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        spec = _spectrum_spec(body, sess)
        plan = spectrummod.estimate(sess, spec)
    except Exception as exc:                             # noqa: BLE001
        return fail("spectrum/estimate", exc, 400, {"path": body.get("path")})
    return jsonify({"ok": True, "plan": plan, "spec": spec,
                    "cached": spectrummod.cache_get(
                        spectrummod.cache_key(spec)) is not None})


@app.route("/api/spectrum/run", methods=["POST"])
def api_spectrum_run():
    """Start one. Poll it on /api/cfc/job/<id>, which is not cfc-specific."""
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        spec = _spectrum_spec(body, sess)
        plan = spectrummod.plan_for(sess, spec)
    except Exception as exc:                             # noqa: BLE001
        return fail("spectrum/run", exc, 400, {"path": body.get("path")})

    key = spectrummod.cache_key(spec)
    hit = spectrummod.cache_get(key)
    if hit is not None and not body.get("force"):
        return jsonify({"ok": True, "cached": True, "result": hit})

    steps = [("spectrum read",
              int(plan["span_s"] * plan["n_channels"])),
             ("spectrum", plan["n_channels"])]

    def work(job):
        out = spectrummod.run(sess, spec, job)
        spectrummod.cache_put(key, out)
        return out

    job = cfcmod.start(spec, steps, work, max(0.001, plan["megasamples"]))
    STORE.record_activity([{
        "action": "spectrum.run",
        "detail": {"t0": round(spec["t0"], 2), "t1": round(spec["t1"], 2),
                   "channels": len(spec["channels"]),
                   "fmax": spec["fmax"],
                   "whole": spec["t0"] <= 0
                            and spec["t1"] >= (sess.get("duration_s") or 0)},
    }])
    return jsonify({"ok": True, "cached": False, "job": job.snapshot(),
                    "plan": plan})


# ==========================================================================
# Panorama -- the whole recording, spectrally, end to end
#
# The same three-call contract as the spectrum: estimate what it will cost,
# start it, poll it on /api/cfc/job/<id>. Deliberately not its own job
# system -- there is one, it learns how fast this machine is, and a second
# would start from zero.
# ==========================================================================
def _panorama_spec(body, sess):
    """What the run is being asked for, with the defaults filled in.

    An empty window means the whole recording, which is the entire point of
    this tool: "what did this session do" is not a question about a
    ten-second look.
    """
    dur = float(sess.get("duration_s") or 0.0)
    t0 = float(body.get("t0") or 0.0)
    t1 = float(body.get("t1") or 0.0)
    if t1 <= t0:
        t0, t1 = 0.0, dur
    chans = body.get("channels")
    if not chans:
        # One channel, never all sixty-four by accident -- that is an hour of
        # fitting nobody asked for.
        chans = [c["index"] for c in (sess.get("channels") or [])][:1]
    spec = {
        "path": sess.get("path"),
        "channels": [int(c) for c in chans],
        "t0": max(0.0, t0),
        "t1": min(t1, dur) if dur else t1,
        "f_lo": float(body.get("f_lo") or panoramamod.DEFAULT_FLO),
        "f_hi": float(body.get("f_hi") or panoramamod.DEFAULT_FHI),
        "sub_s": float(body.get("sub_s") or panoramamod.DEFAULT_SUB_S),
        "win_s": float(body.get("win_s") or panoramamod.DEFAULT_WIN_S),
        "step_s": float(body.get("step_s") or panoramamod.DEFAULT_STEP_S),
        "bins": int(body.get("bins") or panoramamod.DEFAULT_BINS),
        "hist_scale": ("linear" if body.get("hist_scale") == "linear"
                       else "log"),
        "cmap": str(body.get("cmap") or "jet"),
        "scale": ("linear" if body.get("scale") == "linear" else "log10"),
        "even_only": bool(sess.get("even_only")),
        # Mains. `None` means "not said", which is 60 Hz here; an explicit 0
        # means somebody turned it off and wants the interference shown.
        "line_hz": (spectrummod.LINE_HZ if body.get("line_hz") is None
                    else float(body.get("line_hz") or 0.0)),
    }
    for k in ("peak_width_limits", "max_n_peaks", "min_peak_height",
              "aperiodic_mode"):
        if body.get(k) is not None:
            spec[k] = body[k]
    return spec


@app.route("/api/panorama/estimate", methods=["POST"])
def api_panorama_estimate():
    """What a run would do, and how long it would take here."""
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        spec = _panorama_spec(body, sess)
        got = panoramamod.estimate(sess, spec)
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/estimate", exc, 400, {"path": body.get("path")})
    # The channel list rides along with the estimate rather than being a
    # second call: the estimate has already opened the session to work out
    # what the run would cost, and the form needs both before it can be
    # filled in at all.
    chans = [{"index": c.get("index"), "number": c.get("number"),
              "label": c.get("label"), "bad": bool(c.get("bad"))}
             for c in (sess.get("channels") or [])]
    return jsonify({"ok": True, "plan": got["plan"], "spec": spec,
                    "seconds": got["seconds"], "read_s": got["read_s"],
                    "fit_s": got["fit_s"], "notes": got["notes"],
                    "engine": panoramamod.fit_engine(spec),
                    "colormaps": [dict(c) for c in analysis.COLORMAPS],
                    "session": {"duration_s": sess.get("duration_s"),
                                "fs": sess.get("fs"),
                                "channels": chans},
                    "cached": panoramamod.cache_get(
                        panoramamod.cache_key(spec)) is not None})


@app.route("/api/panorama/run", methods=["POST"])
def api_panorama_run():
    """Start one. Poll it on /api/cfc/job/<id>, which is not cfc-specific."""
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        spec = _panorama_spec(body, sess)
        plan = panoramamod.plan_for(sess, spec)
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/run", exc, 400, {"path": body.get("path")})

    if not panoramamod.HAVE_FOOOF:
        return jsonify({
            "ok": False,
            "error": "Panorama's per-window fits need the `fooof` package, "
                     "which is not installed here. Run `pip install -r "
                     "requirements.txt` in the BARRY GUI folder.",
        }), 501

    key = panoramamod.cache_key(spec)
    hit = panoramamod.cache_get(key)
    if hit is not None and not body.get("force"):
        return jsonify({"ok": True, "cached": True, "result": hit})

    n_ch = plan["n_channels"]
    steps = [("spectrum read", int(plan["span_s"] * n_ch)),
             ("panorama windows", int(plan["n_windows"] * n_ch))]

    def work(job):
        state = {}

        def on_preview(x, upto, plan_, st):
            # Throttled here rather than in the module: how often a picture
            # is worth re-encoding is a question about the screen watching
            # it, not about the arithmetic.
            now = time.time()
            if now - state.get("at", 0) < 1.5:
                return
            uri = panoramamod.preview_png(x, upto, plan_, st)
            if uri:
                state["at"] = now
                job.set_preview(uri)

        out = panoramamod.run(sess, spec, job, on_preview=on_preview)
        # The spectrogram matrices ride out of `run` so they can be
        # kept for re-colouring, and come straight back off before the
        # result goes anywhere near jsonify -- they are numpy arrays.
        mats = out.pop("_mats", None)
        panoramamod.cache_put(key, out)
        if mats:
            panoramamod.mats_put(key, mats)
        return out

    job = cfcmod.start(spec, steps, work, max(0.001, plan["megasamples"]))
    STORE.record_activity([{
        "action": "panorama.run",
        "detail": {"t0": round(spec["t0"], 2), "t1": round(spec["t1"], 2),
                   "channels": len(spec["channels"]),
                   "f_lo": spec["f_lo"], "f_hi": spec["f_hi"],
                   "windows": plan["n_windows"],
                   "whole": spec["t0"] <= 0
                            and spec["t1"] >= (sess.get("duration_s") or 0)},
    }])
    return jsonify({"ok": True, "cached": False, "job": job.snapshot(),
                    "plan": plan, "notes": panoramamod.notes_for(plan)})


@app.route("/api/panorama/recolor", methods=["POST"])
def api_panorama_recolor():
    """The same spectrogram under a different colormap or scale.

    From the cached result, so changing Jet for Viridis costs a re-encode
    rather than reading the recording again.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        spec = _panorama_spec(body, sess)
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/recolor", exc, 400, {"path": body.get("path")})
    key = panoramamod.cache_key(spec)
    hit = panoramamod.cache_get(key)
    if hit is None:
        return jsonify({"ok": False,
                        "error": "That run is no longer held here. Run it "
                                 "again and the picture comes back with "
                                 "it."}), 409
    mats = panoramamod.mats_get(key)
    if not mats:
        # The numbers are still here but the matrices have been evicted, so
        # the picture cannot be re-coloured without reading again. Said,
        # rather than silently handing back the old colours.
        return jsonify({"ok": False,
                        "error": "The picture behind this run is no longer "
                                 "held. Run it again to change the "
                                 "colours."}), 409
    try:
        panoramamod.recolor(hit, mats, spec.get("cmap"), spec.get("scale"))
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/recolor", exc, 400, {"path": body.get("path")})
    return jsonify({"ok": True,
                    "channels": [{"index": c.get("index"),
                                  "spectrogram": c.get("spectrogram")}
                                 for c in hit.get("channels") or []]})


@app.route("/api/panorama/rebin", methods=["POST"])
def api_panorama_rebin():
    """Re-cut the histograms, from numbers already computed.

    A histogram is a count of the per-window dominant frequencies, and those
    are already in the held result -- so changing the bin count or switching
    to linear bins is arithmetic on a few thousand floats. It used to be
    part of the cache key, which made it a reason to read half an hour of
    recording again.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        spec = _panorama_spec(body, sess)
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/rebin", exc, 400, {"path": body.get("path")})
    hit = panoramamod.cache_get(panoramamod.cache_key(spec))
    if hit is None:
        return jsonify({"ok": False,
                        "error": "That run is no longer held here. Run it "
                                 "again."}), 409
    try:
        # In place, so a save afterwards writes the bins on screen.
        panoramamod.rebin(hit, spec.get("bins"), spec.get("hist_scale"))
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/rebin", exc, 400, {"path": body.get("path")})
    return jsonify({"ok": True,
                    "channels": [{"index": c.get("index"),
                                  "hist": c.get("hist"),
                                  "modal_hz": c.get("modal_hz")}
                                 for c in hit.get("channels") or []]})


@app.route("/api/panorama/save", methods=["POST"])
def api_panorama_save():
    """Step 3. The figure and the numbers behind it, into Results/.

    Five files under one stem, not one: a picture cannot be re-plotted and a
    CSV cannot be looked at. The JSON carries every setting including which
    fitter produced the numbers, so a figure found in six months can be
    explained without anybody having to remember.

    `results.py` catalogues Results/ by scanning, so nothing is registered
    here -- the files appear in the Results view, go into the repo, and are
    mirrored to the cloud bucket, on their own.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        spec = _panorama_spec(body, sess)
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/save", exc, 400, {"path": body.get("path")})

    out = panoramamod.cache_get(panoramamod.cache_key(spec))
    if out is None:
        return jsonify({"ok": False,
                        "error": "That run is no longer held here. Run it "
                                 "again and Save will have something to "
                                 "write."}), 409

    index = max(0, int(body.get("index") or 0))
    counting = "flat" if body.get("counting") == "flat" else "peak"
    rows = out.get("channels") or []
    if index >= len(rows) or "hist" not in rows[index]:
        return jsonify({"ok": False,
                        "error": "That channel produced nothing to save."}), 400
    ch = rows[index]

    stamp = time.strftime("%Y%m%d_%H%M%S")
    label = str(body.get("name") or "panorama").strip() or "panorama"
    stem = "".join(c if (c.isalnum() or c in " -_.") else "-"
                   for c in label).strip().replace(" ", "_")[:70]
    stem = "%s_%s" % (stem or "panorama", stamp)

    head = ("# Jarvis Panorama -- %s -- %s -- %.3g-%.3g Hz -- %s windows of "
            "%.3g s every %.3g s -- taken %s\n"
            % (label, ch.get("label") or "", spec["f_lo"], spec["f_hi"],
               "{:,}".format(ch["hist"]["n_windows"]), spec["win_s"],
               spec["step_s"], time.strftime("%Y-%m-%dT%H:%M:%S")))

    psd_rows, hist_rows, win_rows = panoramamod.tables(out, index)
    written, errors = [], []

    def put(blob, suffix):
        try:
            got = save_output(blob, stem + suffix, subdir="Panorama")
            written.append(got)
        except Exception as exc:                         # noqa: BLE001
            errors.append("%s: %s" % (suffix, exc))
            STORE.record_error("panorama/save", str(exc), None,
                               {"name": stem + suffix})

    try:
        put(panoramamod.figure(out, index, counting, title=label), ".png")
    except Exception as exc:                             # noqa: BLE001
        errors.append("figure: %s" % exc)
        STORE.record_error("panorama/figure", str(exc), None, {"stem": stem})

    put((head + extras.to_csv(psd_rows)).encode("utf-8"), "_psd.csv")
    put((head + extras.to_csv(hist_rows)).encode("utf-8"), "_histogram.csv")
    put((head + extras.to_csv(win_rows)).encode("utf-8"), "_windows.csv")
    put(json.dumps({
        "tool": "panorama",
        "label": label,
        "spec": spec,
        "plan": out.get("plan"),
        "fit_engine": out.get("fit_engine"),
        "counting": counting,
        "channel": {"index": ch.get("index"), "label": ch.get("label"),
                    "number": ch.get("number"), "bad": ch.get("bad")},
        "gaps": ch.get("gaps"),
        "summary": {"modal_hz": ch.get("modal_hz"),
                    "median_hz": ch.get("median_hz"),
                    "n_windows": ch["hist"]["n_windows"],
                    "n_used": ch["hist"]["n_used"],
                    "n_nopeak": ch["hist"]["n_nopeak"],
                    "n_rejected": ch["hist"]["n_rejected"],
                    # How often the dominant peak only just won. Over a
                    # wide range this is high for almost any recording,
                    # which is the point: a modal frequency of 41 Hz out
                    # of a set of coin tosses is not the same claim as one
                    # out of a clear rhythm, and the file has to say which.
                    "close_call_frac": panoramamod._close_calls(ch)},
        "notes": out.get("notes"),
        "provenance": STORE.provenance(),
    }, indent=1, sort_keys=True).encode("utf-8"), "_params.json")

    if not written:
        return jsonify({"ok": False,
                        "error": "Nothing could be written to Results/: "
                                 + "; ".join(errors)}), 500

    run = STORE.record_run({
        "kind": "panorama", "script": "Panorama",
        "label": "Panorama -- " + label,
        "status": "done", "format": "png",
        "parameters": {"f_lo": spec["f_lo"], "f_hi": spec["f_hi"],
                       "t0": spec["t0"], "t1": spec["t1"],
                       "win_s": spec["win_s"], "sub_s": spec["sub_s"],
                       "step_s": spec["step_s"], "bins": spec["bins"],
                       "counting": counting,
                       "channel": ch.get("label")},
        "output": written[0],
        "outputs": written,
    })
    STORE.record_activity([{
        "action": "panorama.save",
        "detail": {"label": label, "files": len(written),
                   "channel": ch.get("label")},
    }])
    return jsonify({"ok": True,
                    "folder": "Results/Panorama",
                    "files": [w["rel"] for w in written],
                    "saved": written,
                    "errors": errors,
                    "run": run.get("id") if isinstance(run, dict) else None})


# ==========================================================================
# Panorama over many recordings
#
# The tool asks one question of every recording in a set, one at a time, and
# files each answer as it lands. Everything durable is in `panoramaset.py`;
# this is the HTTP around it plus the two things only the app knows -- how to
# open a recording, and what the layer sheets say.
# ==========================================================================
PNSETS = pnsetmod.Sets(LOGS_DIR, STORE)

# Incisor's answers, kept.
#
# Its cache was a dictionary in memory holding eight entries. Scan a ninth
# recording and the first is gone; restart the app and they all are -- which
# is why "those candidates are no longer cached, run the scan again" is a
# sentence this app has to say. A scan is minutes of reading; being told to
# do it again because somebody restarted Jarvis is not a cache miss, it is
# lost work.
#
# Split the same way panoramaset splits Panorama's, and for the same reason.
# The durable half is small -- which channel is the hilus and how that was
# decided, the parameters, the counts -- and is committed and synced, so a
# colleague's scan answers your question without being re-run. The per-
# channel event lists are megabytes and regenerable from the recording, so
# they go to .cache, which git ignores.
INCISOR_VAULT = toolresults.ToolResults(LOGS_DIR, "incisor", STORE)


def _incisor_remember(sess, spec, key, out):
    """File a finished scan: the numbers durably, the events as cache."""
    gid = (sess or {}).get("gid")
    if not gid:
        return False
    try:
        with open(INCISOR_VAULT.cached_path(gid, key, ".json"),
                  "w", encoding="utf-8") as fh:
            json.dump(out, fh)
    except Exception as exc:                             # noqa: BLE001
        STORE.record_error("incisor.cache", exc, None, {"gid": gid})
    try:
        rec = dict(_incisor_public(out))
        rec.update({
            "gid": gid,
            "params_hash": key,
            "session_label": (sess.get("identity") or {}).get("label"),
            "path_used": sess.get("path"),
            "spec": {k: v for k, v in (spec or {}).items() if k != "channels"},
            "n_channels": len((spec or {}).get("channels") or []),
            "computed": STORE.provenance(),
        })
        INCISOR_VAULT.put(rec)
        return True
    except Exception as exc:                             # noqa: BLE001
        STORE.record_error("incisor.remember", exc, None, {"gid": gid})
        return False


def _incisor_recall(sess, key):
    """The full scan back, from disk, when memory has forgotten it."""
    gid = (sess or {}).get("gid")
    if not gid:
        return None
    path = INCISOR_VAULT.cached_path(gid, key, ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            out = json.load(fh)
    except Exception:                                    # noqa: BLE001
        return None
    # Back into memory, so the next channel change does not read disk again.
    incisormod.cache_put(key, out)
    return out


def _pn_opener(member):
    """Open one recording for the bulk worker.

    Deliberately NOT `_session_for`. That cache holds six and evicts by
    iterating a plain dict while request threads insert into it, so a run
    over forty recordings would both thrash it and race it -- and it would
    evict whatever the person at the keyboard has open. The worker is
    sequential, so it holds one session and lets it go.
    """
    path = (member or {}).get("path")
    if not path:
        return {"ok": False, "error": "no path recorded for this session"}
    try:
        return csc.open_session(path)
    except Exception as exc:                             # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def _pn_channel_for(gid, region, fallback=None):
    """Which channel to analyse, and how that was decided.

    The layer sheet first, because a channel number means a different depth
    in every animal and the sheet is where somebody already wrote down what
    is where. A set-wide fallback number second, marked as such. Otherwise
    nothing -- shown as needing a sheet rather than analysed on whatever
    channel happened to be first, which would silently compare the hilus in
    one animal with stratum radiatum in the next.
    """
    if region:
        rec = LAYERS.get(gid)
        labels = (rec or {}).get("labels") or {}
        hits = sorted(int(n) for n, r in labels.items() if r == region)
        if hits:
            return {"channel": hits[0], "channel_from": "layers",
                    "region": region,
                    "channel_label": "CSC%d" % hits[0],
                    "alternatives": hits[1:]}
    if fallback is not None:
        return {"channel": int(fallback), "channel_from": "fallback",
                "region": region, "channel_label": "CSC%d" % int(fallback)}
    return {"channel": None, "channel_from": "none", "region": region}


def _pn_member_rows(gids, region=None, fallback=None):
    """Turn a list of recordings into set members, channels resolved."""
    out = []
    for gid in gids:
        # Through `_session_by_gid`, so the demo recordings work: they are
        # not in the registry on purpose, and every route that looks a gid
        # up has to know that or they arrive as "unidentified".
        rec = _session_by_gid(gid) or {}
        # `loadable` before `here` before `paths`: a folder can outlive its
        # contents, and a set assembled on the rig and opened on a laptop
        # should say "not reachable" rather than fail at run time.
        path = ((rec.get("loadable") or rec.get("here") or rec.get("paths")
                 or [None])[0])
        got = _pn_channel_for(gid, region, fallback)
        got.update({
            "gid": gid,
            "label": rec.get("label") or rec.get("key") or gid,
            "path": path,
        })
        out.append(got)
    return out


@app.route("/api/panorama/sets")
def api_panorama_sets():
    """Every set this lab has, newest first."""
    rows = []
    for rec in PNSETS.all(include_archived=bool(request.args.get("archived"))):
        state = rec.get("state") or {}
        members = [m for m in (rec.get("members") or [])
                   if m.get("enabled", True)]
        counts = {}
        for m in members:
            st = (state.get(m["id"]) or {}).get("status") or "waiting"
            counts[st] = counts.get(st, 0) + 1
        rows.append({
            "set_id": rec["set_id"], "name": rec.get("name"),
            "params": rec.get("params"), "params_hash": rec.get("params_hash"),
            "n_members": len(members), "counts": counts,
            "grouping": rec.get("grouping"),
            "archived": bool(rec.get("archived")),
            "created": rec.get("created"), "updated": rec.get("updated"),
            "saved": len(rec.get("saved") or []),
        })
    return jsonify({"ok": True, "sets": rows,
                    "regions": [dict(r) for r in layers.REGIONS]})


@app.route("/api/panorama/sets", methods=["POST"])
def api_panorama_set_create():
    """A new set: a question, and the recordings to ask it of."""
    body = request.get_json(force=True) or {}
    gids = [g for g in (body.get("gids") or []) if g]
    if not gids:
        return jsonify({"ok": False,
                        "error": "Pick at least one recording."}), 400
    try:
        params = _panorama_params(body)
        members = _pn_member_rows(gids, body.get("region"),
                                  body.get("fallback_channel"))
        rec = PNSETS.create(body.get("name"), params, members,
                            grouping=body.get("grouping") or "auto",
                            note=body.get("note"))
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/set-create", exc, 400, {"n": len(gids)})
    STORE.record_activity([{
        "action": "panorama.set_create",
        "detail": {"name": rec.get("name"), "n": len(rec.get("members") or []),
                   "region": body.get("region")},
    }])
    return jsonify({"ok": True, "set": _pn_tree(rec)})


def _panorama_params(body):
    """The question a set asks, with the defaults filled in.

    The same fields `_panorama_spec` takes, minus the recording and the
    channel -- those vary per member -- and minus the colormap, which does
    not change any number.
    """
    f_lo = float(body.get("f_lo") or panoramamod.DEFAULT_FLO)
    f_hi = float(body.get("f_hi") or panoramamod.DEFAULT_FHI)
    if f_hi <= f_lo:
        f_hi = max(f_lo * 2.0, panoramamod.DEFAULT_FHI)
    out = {
        "f_lo": f_lo, "f_hi": f_hi,
        "sub_s": float(body.get("sub_s") or panoramamod.DEFAULT_SUB_S),
        "win_s": float(body.get("win_s") or panoramamod.DEFAULT_WIN_S),
        "step_s": float(body.get("step_s") or panoramamod.DEFAULT_STEP_S),
        "bins": int(body.get("bins") or panoramamod.DEFAULT_BINS),
        "hist_scale": ("linear" if body.get("hist_scale") == "linear"
                       else "log"),
        "line_hz": (spectrummod.LINE_HZ if body.get("line_hz") is None
                    else float(body.get("line_hz") or 0.0)),
    }
    if body.get("t0") is not None:
        out["t0"] = float(body["t0"])
    if body.get("t1") is not None:
        out["t1"] = float(body["t1"])
    for k in ("peak_width_limits", "max_n_peaks", "min_peak_height",
              "aperiodic_mode"):
        if body.get(k) is not None:
            out[k] = body[k]
    return out


def _pn_tree(rec):
    """A set as the tree draws it: members, state, and each one's numbers."""
    ph = rec.get("params_hash")
    state = rec.get("state") or {}
    rows = []
    for m in rec.get("members") or []:
        gid = m["id"]
        st = dict(state.get(gid) or {})
        res = PNSETS.result_get(gid, ph)
        row = dict(m)
        row["status"] = st.get("status") or "waiting"
        row["error"] = st.get("error")
        # Why it cannot run, worked out now rather than when its turn comes.
        if not m.get("path"):
            row["blocked_why"] = "no folder this machine can read"
        elif m.get("channel") is None:
            row["blocked_why"] = "no channel chosen"
        row["job"] = st.get("job")
        row["at"] = st.get("at")
        if res:
            row.update({
                "n_windows": res.get("n_windows"),
                "n_used": res.get("n_used"),
                "n_nopeak": res.get("n_nopeak"),
                "modal_hz": res.get("modal_hz"),
                "median_hz": res.get("median_hz"),
                "exponent": (res.get("fit") or {}).get("exponent"),
                "r2": (res.get("fit") or {}).get("r_squared"),
                "gap_s": (res.get("gaps") or {}).get("seconds"),
                "gap_n": (res.get("gaps") or {}).get("n"),
                # How often the dominant frequency was a coin toss between
                # two near-equal peaks. High means this recording's
                # histogram is mostly about which of several broad bumps
                # happened to win, and should be read knowing that.
                "close_call": res.get("close_call_frac"),
                # The sparkline. Counts only -- the edges are the set's and
                # are sent once, beside the tree, rather than forty times.
                "spark": res.get("counts_peak"),
                "seconds": (res.get("computed") or {}).get("seconds"),
                "has_png": PNSETS.has_png(gid, ph),
            })
            if row["status"] == "waiting":
                # Computed under this question by somebody, sometime -- the
                # set's own state map just has not heard about it.
                row["status"] = "done"
                row["cached"] = True
        rows.append(row)
    edges = None
    for m in rows:
        res = PNSETS.result_get(m["id"], ph)
        if res and res.get("edges"):
            edges = res["edges"]
            break
    return {
        "set_id": rec["set_id"], "name": rec.get("name"),
        "note": rec.get("note"),
        "params": rec.get("params"), "params_hash": ph,
        "grouping": rec.get("grouping"),
        "archived": bool(rec.get("archived")),
        "created": rec.get("created"), "updated": rec.get("updated"),
        "saved": rec.get("saved") or [],
        "members": rows,
        "edges": edges,
    }


@app.route("/api/panorama/sets/<set_id>")
def api_panorama_set(set_id):
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    # A member whose job went away with the last process is interrupted, not
    # running. Done on read so a reload tells the truth without anybody
    # having to press anything.
    if PNSETS.reconcile(rec, cfcmod.exists):
        PNSETS._write(rec)
    return jsonify({"ok": True, "set": _pn_tree(rec),
                    "regions": [dict(r) for r in layers.REGIONS]})


@app.route("/api/panorama/sets/<set_id>/members", methods=["POST"])
def api_panorama_set_members(set_id):
    body = request.get_json(force=True) or {}
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    if body.get("remove"):
        rec = PNSETS.remove_member(set_id, body["remove"])
        return jsonify({"ok": True, "set": _pn_tree(rec)})
    gids = [g for g in (body.get("gids") or []) if g]
    if not gids:
        return jsonify({"ok": False, "error": "Nothing to add."}), 400
    members = _pn_member_rows(gids, body.get("region")
                              or (rec.get("members") or [{}])[0].get("region"),
                              body.get("fallback_channel"))
    rec = PNSETS.add_members(set_id, members)
    return jsonify({"ok": True, "set": _pn_tree(rec)})


@app.route("/api/panorama/sets/<set_id>/channel", methods=["POST"])
def api_panorama_set_channel(set_id):
    """Override one recording's channel, or re-resolve every one by rule."""
    body = request.get_json(force=True) or {}
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    if body.get("gid"):
        ch = body.get("channel")
        rec = PNSETS.set_channel(
            set_id, body["gid"],
            None if ch in (None, "") else int(ch),
            channel_label=(None if ch in (None, "") else "CSC%d" % int(ch)),
            how="manual")
        return jsonify({"ok": True, "set": _pn_tree(rec)})

    region = body.get("region")
    fallback = body.get("fallback_channel")
    keep_manual = body.get("keep_manual", True)
    for m in list(rec.get("members") or []):
        if keep_manual and m.get("channel_from") == "manual":
            continue
        got = _pn_channel_for(m["id"], region, fallback)
        PNSETS.set_channel(set_id, m["id"], got["channel"],
                           channel_label=got.get("channel_label"),
                           how=got["channel_from"], region=region)
    return jsonify({"ok": True, "set": _pn_tree(PNSETS.get(set_id))})


@app.route("/api/panorama/sets/<set_id>/estimate", methods=["POST"])
def api_panorama_set_estimate(set_id):
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    body = request.get_json(force=True) or {}
    force = bool(body.get("force"))
    split = PNSETS.pending(rec, force=force)
    try:
        plan = pnsetmod.plan_for_set(rec, _pn_opener, split["todo"])
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/set-estimate", exc, 400, {"set": set_id})
    return jsonify({"ok": True, "plan": plan,
                    "todo": len(split["todo"]),
                    "cached": len(split["cached"]),
                    "blocked": [m["id"] for m in split["blocked"]]})


@app.route("/api/panorama/sets/<set_id>/run", methods=["POST"])
def api_panorama_set_run(set_id):
    """Start the set. Poll it on /api/cfc/job/<id> like everything else."""
    body = request.get_json(force=True) or {}
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    if not panoramamod.HAVE_FOOOF:
        return jsonify({
            "ok": False,
            "error": "Panorama's per-window fits need the `fooof` package, "
                     "which is not installed here. Run `pip install -r "
                     "requirements.txt` in the BARRY GUI folder.",
        }), 501

    force = bool(body.get("force"))
    split = PNSETS.pending(rec, force=force)
    if not split["todo"]:
        return jsonify({"ok": True, "nothing": True,
                        "set": _pn_tree(rec),
                        "cached": len(split["cached"]),
                        "blocked": [m["id"] for m in split["blocked"]]})
    try:
        plan = pnsetmod.plan_for_set(rec, _pn_opener, split["todo"])
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/set-run", exc, 400, {"set": set_id})

    steps = [("panorama bulk", int(max(1, plan["span_s"])))]
    where = cfcmod.volume_key((split["todo"][0] or {}).get("path"))

    def work(job):
        return pnsetmod.run_set(PNSETS, set_id, _pn_opener, job, force=force)

    job = cfcmod.start({"set_id": set_id, "path": (split["todo"][0] or {}).get("path")},
                       steps, work, 1.0, where)
    STORE.record_activity([{
        "action": "panorama.set_run",
        "detail": {"set": rec.get("name"), "n": len(split["todo"]),
                   "cached": len(split["cached"]),
                   "span_s": plan["span_s"]},
    }])
    return jsonify({"ok": True, "job": job.snapshot(), "plan": plan})


# ==========================================================================
# Converging a set
# ==========================================================================
def _pn_auto_groups(rec, attr="group"):
    """Groups derived from what the lab already wrote down.

    No grouping record, nothing to maintain: the mouse's own attribute
    first -- which is where PTEN and CTL are already recorded -- then the
    cohort the folders name, then the project. Materialised into a real
    grouping only when somebody edits it, the way `layers.ensure` copies
    REGIONS in, so a set grouped today still means what it meant if the
    project labels are corrected next month.
    """
    idx = MICE.index()
    assign, names = {}, {}
    for m in rec.get("members") or []:
        gid = m["id"]
        got = _session_by_gid(gid) or {}
        attrs = ((idx.get(str(got.get("project"))) or {})
                 .get(str(got.get("mouse"))) or {}).get("attrs") or {}
        label = (attrs.get(attr) or got.get("cohort")
                 or got.get("project") or "").strip()
        if not label:
            assign[gid] = []
            continue
        key = "auto:" + label
        assign[gid] = [key]
        names[key] = label
    return assign, names


def _pn_grouping_for(rec, body):
    """(groups_of, names) for however this set is grouped.

    `facet` narrows a stored grouping to one axis -- genotype, say -- which
    is what makes "at most one group per recording" checkable: PTEN and
    female are not rival groups and a recording in both is not
    double-counted, but PTEN and CTL are.
    """
    which = body.get("grouping") or rec.get("grouping") or "auto"
    if which == "auto" or not which:
        assign, names = _pn_auto_groups(rec, body.get("attr") or "group")
        return (lambda g: assign.get(g, [])), names

    got = PNSETS.grouping_get(which)
    if not got:
        # Named a grouping that is not here -- another machine's, most
        # likely. Derived beats wrong.
        assign, names = _pn_auto_groups(rec, body.get("attr") or "group")
        return (lambda g: assign.get(g, [])), names

    facet = body.get("facet")
    defs = {g["id"]: g for g in (got.get("groups") or [])}
    names = {k: v.get("name") or k for k, v in defs.items()}
    assign = got.get("assign") or {}

    def groups_of(gid):
        ids = [g for g in (assign.get(gid) or []) if g in defs]
        if facet:
            ids = [g for g in ids if defs[g].get("facet") == facet]
        return ids

    return groups_of, names


@app.route("/api/panorama/sets/<set_id>/converge", methods=["POST"])
def api_panorama_converge(set_id):
    """Every recording's histogram, pooled by group. The point of a set."""
    body = request.get_json(force=True) or {}
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    try:
        groups_of, names = _pn_grouping_for(rec, body)
        conv = pnsetmod.converge(
            PNSETS, rec, groups_of,
            dominant=("flat" if body.get("dominant") == "flat" else "peak"),
            weight=("window" if body.get("weight") == "window"
                    else "session"))
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/converge", exc, 400, {"set": set_id})
    if not conv.get("ok"):
        return jsonify(conv), 409
    conv["names"] = names
    conv["grouping"] = body.get("grouping") or rec.get("grouping") or "auto"
    conv["attr"] = body.get("attr") or "group"
    conv["attributes"] = [a for a in MICE.attributes()
                          if a.get("n") or a.get("suggested")]
    return jsonify({"ok": True, "converged": conv})


@app.route("/api/panorama/groupings")
def api_panorama_groupings():
    return jsonify({"ok": True,
                    "groupings": [{"id": g["id"], "name": g.get("name"),
                                   "groups": g.get("groups") or [],
                                   "n_assigned": len(g.get("assign") or {}),
                                   "updated": g.get("updated")}
                                  for g in PNSETS.grouping_all()]})


@app.route("/api/panorama/groupings", methods=["POST"])
def api_panorama_grouping_create():
    """A custom grouping, seeded from the derived one so nothing is retyped."""
    body = request.get_json(force=True) or {}
    set_id = body.get("set_id")
    groups, assign = body.get("groups"), body.get("assign")
    if set_id and not groups:
        rec = PNSETS.get(set_id)
        if not rec:
            return jsonify({"ok": False, "error": "No such set."}), 404
        auto, names = _pn_auto_groups(rec, body.get("attr") or "group")
        facet = body.get("attr") or "group"
        groups = [{"id": k, "name": v, "facet": facet, "order": i}
                  for i, (k, v) in enumerate(sorted(names.items(),
                                                    key=lambda kv: kv[1]))]
        assign = auto
    rec2 = PNSETS.grouping_create(body.get("name") or "Custom grouping",
                                  groups=groups, assign=assign,
                                  note=body.get("note"))
    if set_id:
        PNSETS.set_grouping(set_id, rec2["id"])
    return jsonify({"ok": True, "grouping": rec2})


@app.route("/api/panorama/groupings/<gid_>", methods=["POST"])
def api_panorama_grouping_edit(gid_):
    body = request.get_json(force=True) or {}
    if body.get("assign") is not None and body.get("gid"):
        rec = PNSETS.grouping_assign(gid_, body["gid"], body["assign"])
    else:
        rec = PNSETS.grouping_edit(gid_, groups=body.get("groups"),
                                   name=body.get("name"),
                                   note=body.get("note"))
    if not rec:
        return jsonify({"ok": False, "error": "No such grouping."}), 404
    return jsonify({"ok": True, "grouping": rec})


@app.route("/api/panorama/sets/<set_id>/save", methods=["POST"])
def api_panorama_set_save(set_id):
    """The convergence figure and the two tables behind it, into Results/.

    `set_id` and the question's hash go in the filename. `save_output` never
    clobbers -- it appends `_2` -- so repeats accumulate, and the hash is
    what tells you which run a stray `_3` belongs to.
    """
    body = request.get_json(force=True) or {}
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    try:
        groups_of, names = _pn_grouping_for(rec, body)
        conv = pnsetmod.converge(
            PNSETS, rec, groups_of,
            dominant=("flat" if body.get("dominant") == "flat" else "peak"),
            weight=("window" if body.get("weight") == "window"
                    else "session"))
    except Exception as exc:                             # noqa: BLE001
        return fail("panorama/set-save", exc, 400, {"set": set_id})
    if not conv.get("ok"):
        return jsonify(conv), 409

    label = str(body.get("name") or rec.get("name") or "panorama").strip()
    stem = "".join(c if (c.isalnum() or c in " -_.") else "-"
                   for c in label).strip().replace(" ", "_")[:60]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stem = "converge_%s_%s_%s_%s" % (stem or "set", set_id,
                                     rec.get("params_hash"), stamp)

    head = ("# Jarvis Panorama -- convergence -- %s -- %d recordings -- "
            "%.3g-%.3g Hz -- dominant by %s -- %s -- taken %s\n"
            % (label, conv.get("n_sessions", 0),
               (rec.get("params") or {}).get("f_lo"),
               (rec.get("params") or {}).get("f_hi"),
               conv.get("dominant"),
               ("one vote per recording" if conv.get("weight") != "window"
                else "weighted by recording length"),
               time.strftime("%Y-%m-%dT%H:%M:%S")))

    per_rows, long_rows = panoramamod.converge_tables(conv, names)
    written, errors = [], []

    def put(blob, suffix):
        try:
            written.append(save_output(blob, stem + suffix,
                                       subdir="Panorama"))
        except Exception as exc:                         # noqa: BLE001
            errors.append("%s: %s" % (suffix, exc))
            STORE.record_error("panorama/set-save", str(exc), None,
                               {"name": stem + suffix})

    try:
        put(panoramamod.converge_figure(conv, title=label, names=names),
            ".png")
    except Exception as exc:                             # noqa: BLE001
        errors.append("figure: %s" % exc)
        STORE.record_error("panorama/converge-figure", str(exc), None,
                           {"set": set_id})

    put((head + extras.to_csv(per_rows)).encode("utf-8"), "_recordings.csv")
    put((head + extras.to_csv(long_rows)).encode("utf-8"), "_histograms.csv")
    put(json.dumps({
        "tool": "panorama", "kind": "convergence",
        "set_id": set_id, "name": rec.get("name"),
        "params": rec.get("params"), "params_hash": rec.get("params_hash"),
        "grouping": conv.get("grouping"), "attr": conv.get("attr"),
        "group_names": names,
        "dominant": conv.get("dominant"), "weight": conv.get("weight"),
        "groups": [{k: g[k] for k in ("id", "n", "modal_hz", "nopeak_mean",
                                      "gids")}
                   for g in conv.get("groups") or []],
        "n_sessions": conv.get("n_sessions"),
        "not_run": conv.get("not_run"),
        "no_windows": conv.get("no_windows"),
        "in_several_groups": conv.get("in_several_groups"),
        "provenance": STORE.provenance(),
    }, indent=1, sort_keys=True).encode("utf-8"), "_params.json")

    if not written:
        return jsonify({"ok": False,
                        "error": "Nothing could be written to Results/: "
                                 + "; ".join(errors)}), 500

    run = STORE.record_run({
        "kind": "panorama", "script": "Panorama convergence",
        "label": "Panorama convergence -- " + label,
        "status": "done", "format": "png",
        "parameters": {"set_id": set_id,
                       "params_hash": rec.get("params_hash"),
                       "dominant": conv.get("dominant"),
                       "weight": conv.get("weight"),
                       "grouping": conv.get("grouping"),
                       "n_recordings": conv.get("n_sessions")},
        "output": written[0], "outputs": written,
    })
    PNSETS.record_saved(set_id, {"kind": "convergence",
                                 "result_rel": written[0]["rel"],
                                 "run": run.get("id")})
    STORE.record_activity([{
        "action": "panorama.converge_save",
        "detail": {"set": rec.get("name"), "files": len(written),
                   "recordings": conv.get("n_sessions")},
    }])
    return jsonify({"ok": True, "folder": "Results/Panorama",
                    "files": [w["rel"] for w in written],
                    "errors": errors,
                    "run": run.get("id") if isinstance(run, dict) else None})


@app.route("/api/panorama/sets/<set_id>/archive", methods=["POST"])
def api_panorama_set_archive(set_id):
    """Put a set away without losing it. The usual way to finish with one."""
    body = request.get_json(force=True) or {}
    rec = PNSETS.archive(set_id, bool(body.get("on", True)))
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    return jsonify({"ok": True, "set": _pn_tree(rec)})


@app.route("/api/panorama/sets/<set_id>/delete", methods=["POST"])
def api_panorama_set_delete(set_id):
    """Delete a set, and optionally the answers computed for it.

    The answers are keyed on the recording and the question, not on the set,
    so another set may be relying on them -- which is why they are NOT
    removed unless asked for. `results: true` is for a harness clearing up
    after itself, and for somebody who really does want the numbers gone.
    """
    body = request.get_json(force=True) or {}
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    ph = rec.get("params_hash")
    gone = {"sets": 0, "results": 0, "pictures": 0}

    if body.get("results"):
        for m in rec.get("members") or []:
            gid = m["id"]
            if PNSETS.results.erase(PNSETS.result_base(gid, ph)):
                gone["results"] += 1
            p = PNSETS.png_path(gid, ph)
            try:
                if os.path.exists(p):
                    os.remove(p)
                    gone["pictures"] += 1
            except OSError:
                pass

    gone["sets"] = PNSETS.book.erase(shards.safe_base(set_id)) or 0
    STORE.record_activity([{
        "action": "panorama.set_delete",
        "detail": {"set": rec.get("name"), "results": gone["results"]},
    }])
    return jsonify({"ok": True, "removed": gone})


@app.route("/api/panorama/sets/<set_id>/result/<gid>")
def api_panorama_set_result(set_id, gid):
    """One recording's answer, for when a row in the tree is clicked."""
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    got = PNSETS.result_get(gid, rec["params_hash"])
    if not got:
        return jsonify({"ok": False,
                        "error": "That recording has not been run under "
                                 "this set's settings yet."}), 404
    return jsonify({"ok": True, "result": got,
                    "has_png": PNSETS.has_png(gid, rec["params_hash"])})


@app.route("/api/panorama/sets/<set_id>/spectrogram/<gid>.png")
def api_panorama_set_png(set_id, gid):
    """The cached picture. Not in the record -- see panoramaset.py."""
    rec = PNSETS.get(set_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    path = PNSETS.png_path(gid, rec["params_hash"])
    if not os.path.exists(path):
        return jsonify({"ok": False,
                        "error": "No picture held for that recording."}), 404
    return send_file(path, mimetype="image/png")


def _stored_for(sess):
    """The saved record for an open session, or `{}`.

    Bad channels and the chosen probe are not in the `.ncs` files -- they are
    decisions somebody made about this recording -- so anything that has to
    honour them must look them up the same way the trace view does: by
    identity, not by path. Two machines with the recording on different
    drives are the same session and must get the same answer.
    """
    try:
        if sess.get("source") == "demo":
            spec = demomod.get(sess.get("path")) or {}
            return {"bad_channels": list(spec.get("bad") or [])}
        identity = ids.identify(sess.get("path"),
                                header_time=_header_time(sess))
        rec, _how = STORE.get_session(identity)
        return rec or {}
    except Exception:                                    # noqa: BLE001
        # A recording whose record cannot be found is scanned whole rather
        # than not at all -- but it is not silently treated as having no
        # bad channels, because the panel reports what this returned.
        return {}


def _incisor_spec(body, sess):
    """What the run is being asked for, with the defaults filled in.

    `invert` is read from the session rather than defaulted here, and travels
    into the spec explicitly, because dentate spike detection is positive
    peaks on a signed trace: the two conventions find opposite events and
    both look entirely plausible. Measured on M8s9feb8, the lab's convention
    (inverted) gives 1230 events at 1444 uV on the hilus channel and the
    other gives four.
    """
    stored = _stored_for(sess)

    # Bad channels are dropped from the scan, not merely down-weighted.
    #
    # Toothy keeps detecting on them and nulls them out of the three
    # estimates afterwards (`noise_idx`, `ephys.py:892/902/916`). Dropping
    # them instead gives the same three answers for less reading, and it
    # means the channel list in the reply IS the list that was looked at --
    # a ranking table with a dead channel sitting in it invites somebody to
    # pick the dead channel.
    #
    # `None` means the caller did not say, so the session's own record
    # decides. An explicit list -- including an empty one -- overrides it,
    # which is how the panel offers "scan it with this one put back".
    if body.get("bad_channels") is None:
        bad = {int(b) for b in (stored.get("bad_channels") or [])}
    else:
        bad = {int(b) for b in body["bad_channels"]}

    all_ch = sess.get("channels") or []
    by_index = {int(c["index"]): c for c in all_ch}
    chans = body.get("channels")
    if not chans:
        chans = [c["index"] for c in all_ch]
    chans = [int(c) for c in chans if int(c) in by_index]
    kept = [i for i in chans if int(by_index[i]["number"]) not in bad]
    dropped = [i for i in chans if int(by_index[i]["number"]) in bad]
    if not kept:
        raise ValueError(
            "Every channel in this recording is marked bad, so there is "
            "nothing to scan. Put at least one back and run it again.")

    # The recording's probe, not the window's. It used to be read straight
    # out of `view_state`, so a scan run from a machine that had never had
    # the recording open scanned a dual implant as one linear array.
    probe_id = _probe_for(stored)
    probe = probebook.get(probe_id) or {}
    spec = {
        "path": sess.get("path"),
        "channels": kept,
        "invert": bool(sess.get("invert", True)),
        "even_only": bool(sess.get("even_only")),
        "estimator": (body.get("estimator") or "sd"),
        # Carried so the answer can say what it left out, rather than
        # quietly returning a shorter list than it was asked for. `channels`
        # is in the cache key, so changing the bad set re-scans by itself.
        "bad_channels": sorted(bad),
        "excluded": [{"index": i, "number": int(by_index[i]["number"]),
                      "label": by_index[i].get("label")} for i in dropped],
        # The detector does not use this -- only a CSD cares which contacts
        # are neighbours -- but it decides how the traces window lays the
        # recording out, and a scan that does not say which probe it was
        # read as leaves the reader to guess.
        "probe": probe_id,
        "probe_name": probe.get("name") or probe_id,
    }
    for key, default in (("height_sd", incisormod.DS_HEIGHT_SD),
                         ("abs_uv", incisormod.DS_ABS_THR_UV),
                         ("dist_ms", incisormod.DS_DIST_MS),
                         ("prom_uv", incisormod.DS_PROM_UV),
                         ("wlen_ms", incisormod.DS_WLEN_MS),
                         ("lfp_fs", incisormod.LFP_FS)):
        v = body.get(key)
        spec[key] = float(default if v is None else v)
    band = body.get("band") or incisormod.DS_BAND
    spec["band"] = [float(band[0]), float(band[1])]
    if body.get("threshold_uv"):
        spec["threshold_uv"] = float(body["threshold_uv"])
    return spec


def _incisor_report(path):
    """The segmentation every Incisor time is stamped from."""
    rep = continuitymod.check(path)
    if not rep or not rep.get("ok"):
        raise ValueError(rep.get("error") if rep else "could not segment")
    return rep


@app.route("/api/incisor/estimate", methods=["POST"])
def api_incisor_estimate():
    """What a scan would do, and how long it would take here."""
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        rep = _incisor_report(sess["path"])
        spec = _incisor_spec(body, sess)
        plan = incisormod.estimate(sess, spec, rep)
    except Exception as exc:                             # noqa: BLE001
        return fail("incisor/estimate", exc, 400, {"path": body.get("path")})
    key = incisormod.cache_key(spec, rep)
    return jsonify({
        "ok": True, "plan": plan, "spec": spec,
        # The vault as well as memory, because `/api/incisor/scan` consults
        # both -- so checking only memory here told somebody a scan would
        # take two minutes and then returned it instantly, or worse, offered
        # to send a recording to the cluster that had already been answered
        # on it. The two have to agree about what "cached" means.
        "cached": (incisormod.cache_get(key) is not None
                   or _incisor_recall(sess, key) is not None),
        # What the cluster would make of the same scan. On the ESTIMATE
        # rather than behind its own request, because "six minutes here,
        # forty seconds there" is the reason anybody presses the button and
        # it should arrive with the cost, not a round trip after it.
        "vacc": _vacc_estimate(sess, spec, plan),
        "continuity": {
            "n_segments": rep.get("n_segments"),
            "seconds_lost": rep.get("seconds_lost"),
            "true_duration_s": rep.get("true_duration_s"),
            "n_short_inside": rep.get("n_short_inside"),
            "residual_sd_us": rep.get("map_residual_sd_us"),
            "probed": rep.get("probed"),
            "mismatches": rep.get("mismatches"),
        },
        # What the session already believes about its own anatomy, so the
        # window can put the scan's answer beside it rather than over it.
        "known": _known_channels(sess.get("path")),
        # Every channel in the recording, marked. The plan says how many
        # were scanned and which were left out; this is what a panel needs
        # to let somebody change that -- and it is the full list, including
        # the ones being skipped, because you cannot put a channel back from
        # a list it is not in.
        "channels": [{"index": int(c["index"]), "number": int(c["number"]),
                      "label": c.get("label"),
                      "bad": int(c["number"]) in set(spec["bad_channels"])}
                     for c in (sess.get("channels") or [])],
    })


def _known_channels(path):
    """Ripple, fissure and hilus as the registry already holds them.

    Imported from the Toothy workbook by `tools/import_toothy.py` for 62
    sessions and corroborated against the layer sheet in 57 of 57 cases where
    both exist. Two independent sources agreeing is the best evidence either
    of them could have, so the scan's estimate is shown BESIDE this rather
    than replacing it.
    """
    # `all()` rather than `summary()`: the records straight out of the
    # shards, cached against their signature, instead of the whole project
    # tree -- which takes seconds on this lab's data and is three quarters
    # of what `/api/registry` costs.
    want = os.path.normcase(os.path.abspath(path or ""))
    try:
        for rec in (REG.all() or []):
            for known in (rec.get("paths") or []):
                if os.path.normcase(os.path.abspath(known)) == want:
                    return {k: rec.get(k) for k in
                            ("hilus_channel", "fissure_channel",
                             "ripple_channel")
                            if rec.get(k) is not None}
    except Exception:                                    # noqa: BLE001
        pass
    return {}


def _incisor_public(out):
    """The answer without the per-channel event lists.

    They stay in the cache for `/api/incisor/events`. Sending all of them to
    draw one channel is sixty-four times the payload, and a response big
    enough to be truncated in transit arrives as a 200 that will not parse.
    """
    return {k: v for k, v in (out or {}).items() if not k.startswith("_")}


@app.route("/api/incisor/events", methods=["POST"])
def api_incisor_events():
    """One channel's events from the scan already run.

    Out of the cache, so changing the channel in the panel costs a small
    request rather than reading the recording again. A miss is honest about
    itself -- the caller should re-scan rather than be given nothing that
    looks like an answer.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        rep = _incisor_report(sess["path"])
        spec = _incisor_spec(body, sess)
    except Exception as exc:                             # noqa: BLE001
        return fail("incisor/events", exc, 400, {"path": body.get("path")})
    ekey = incisormod.cache_key(spec, rep)
    hit = incisormod.cache_get(ekey) or _incisor_recall(sess, ekey)
    if hit is None:
        return jsonify({"ok": False,
                        "error": "That scan is not on this machine. "
                                 "Run it again."}), 409
    try:
        index = int(body.get("channel"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Which channel?"}), 400
    evs = incisormod.events_for(hit, index)
    return jsonify({"ok": True, "channel": index, "n": len(evs),
                    "events": evs})


@app.route("/api/incisor/scan", methods=["POST"])
def api_incisor_scan():
    """Detect on every chosen channel and say which one is the hilus.

    One job, because Toothy's channel estimate is made FROM the per-channel
    detection (`ephys.py:916`) -- scanning and picking are not separable
    steps, and pretending otherwise would mean reading the recording twice.
    Poll it on /api/cfc/job/<id>, which is not cfc-specific.
    """
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        rep = _incisor_report(sess["path"])
        spec = _incisor_spec(body, sess)
        plan = incisormod.plan_for(sess, spec, rep)
    except Exception as exc:                             # noqa: BLE001
        return fail("incisor/scan", exc, 400, {"path": body.get("path")})

    key = incisormod.cache_key(spec, rep)
    hit = incisormod.cache_get(key)
    if hit is None and not body.get("force"):
        # Asked and answered before, on this machine or a colleague's.
        hit = _incisor_recall(sess, key)
    if hit is not None and not body.get("force"):
        return jsonify({"ok": True, "cached": True,
                        "result": _incisor_public(hit)})

    steps = [("ds read", int(plan["span_s"] * plan["n_channels"])),
             ("ds detect", plan["n_channels"])]

    def finish(out):
        """Everything that happens to an answer, wherever it was computed.

        One function, called by both branches. The cluster's result is not a
        second kind of result: it goes into the same cache under the same
        key, the same vault record, and the same public shape -- which is
        what makes a VACC scan indistinguishable from a local one to the
        panel, to `/api/incisor/events`, and to a colleague pulling the
        shard tomorrow.
        """
        incisormod.cache_put(key, out)
        _incisor_remember(sess, spec, key, out)
        # The job's result is what the client fetches, so the private rows
        # come off here rather than being serialised and thrown away.
        return _incisor_public(out)

    if str(body.get("where") or "").startswith("vacc"):
        try:
            run, where = _vacc_run_for("incisor", sess, spec, plan, rep, steps)
        except Exception as exc:                         # noqa: BLE001
            return fail("incisor/scan-vacc", exc, 400,
                        {"path": body.get("path")})

        def work(job, _run=run):
            return finish(_run.work(job))

        job = cfcmod.start(spec, vaccrunmod.steps() + steps, work,
                           max(0.001, plan["megasamples"]), where)
        STORE.record_activity([{
            "action": "incisor.scan",
            "detail": {"channels": len(spec["channels"]), "where": where,
                       "remote": run.spec_remote.get("path")},
        }])
        return jsonify({"ok": True, "cached": False, "job": job.snapshot(),
                        "plan": plan, "where": where,
                        "remote": run.spec_remote.get("path")})

    def work(job):
        return finish(incisormod.run(sess, spec, rep, job))

    job = cfcmod.start(spec, steps, work, max(0.001, plan["megasamples"]))
    STORE.record_activity([{
        "action": "incisor.scan",
        "detail": {"channels": len(spec["channels"]),
                   "segments": rep.get("n_segments"),
                   "invert": spec["invert"],
                   "height_sd": spec["height_sd"]},
    }])
    return jsonify({"ok": True, "cached": False, "job": job.snapshot(),
                    "plan": plan})


@app.route("/api/incisor/batch/plan", methods=["GET", "POST"])
def api_incisor_batch_plan():
    """Which recordings a batch would do, and why the rest are left out.

    Everything knowable before the run is settled before it. A recording the
    cluster cannot reach, or one two cluster folders both claim to be,
    should say so while somebody can still fix it rather than wait its turn
    behind thirty others and then fail -- which is the discipline
    `panoramaset.pending` already applies locally.

    GET as well as POST, because it reads and answers a question rather than
    doing anything -- and because it was POST-only while the panel asked for
    it with `api()`, which is a GET. That is a 404 on a route that is right
    there in the file, and the app correctly reported it as the server being
    older than the code, which was the one explanation that was not true.
    """
    try:
        staged, _unknown = _vacc_staged()
        cfg = vaccmod.load_config(LOGS_DIR)
        todo, blocked, done = [], [], []
        for rec in (REG.all() or []):
            gid = rec.get("gid")
            if not gid or gid not in staged:
                continue
            row = staged[gid] or {}
            label = rec.get("label") or rec.get("key") or gid
            if row.get("conflict"):
                blocked.append({"gid": gid, "label": label,
                                "why": "two folders on the cluster both "
                                       "claim to be this recording"})
                continue
            todo.append({"gid": gid, "label": label, "remote": row.get("path"),
                         "n_channels": row.get("n_channels"),
                         "project": rec.get("project"),
                         "mouse": rec.get("mouse"),
                         "session": rec.get("session")})
        todo.sort(key=lambda r: (str(r.get("project") or ""),
                                 str(r.get("mouse") or ""),
                                 str(r.get("session") or "")))
    except Exception as exc:                             # noqa: BLE001
        return fail("incisor/batch-plan", exc, 400)
    return jsonify({"ok": True, "todo": todo, "blocked": blocked,
                    "done": done, "n": len(todo),
                    "partition": cfg.get("partition")})


@app.route("/api/incisor/reviews")
def api_incisor_reviews():
    """Every finished scan waiting to be looked at.

    Read out of the vault rather than out of memory, so a batch that ran
    overnight, or on a colleague's machine, is here in the morning. What
    comes back is the per-channel summary the three plots are drawn from
    plus the automatic pick -- the events themselves stay where they are and
    are fetched one channel at a time by `/api/incisor/events`.

    Banked ones are marked rather than hidden: "I already did that one" is
    the first thing somebody wants to know coming back to a list of thirty.
    """
    try:
        rows = []
        for rec in (INCISOR_VAULT.all() or []):
            gid = rec.get("gid")
            if not gid:
                continue
            banked = None
            try:
                got = BANK.for_session({"gid": gid}) or []
                for e in got:
                    if (e.get("kind") or "") == "ds":
                        banked = {"id": e.get("id"), "n": e.get("n_events"),
                                  "channel": (e.get("source") or {}).get("channel")}
                        break
            except Exception:                            # noqa: BLE001
                banked = None
            picked = rec.get("picked") or {}
            # The path this machine can open it at, so selecting a review
            # re-enters the ordinary panel rather than needing a second way
            # to render a scan. The answer is already in the vault, so that
            # re-entry costs a cache hit and nothing else.
            local, label, row = None, None, None
            for r2 in (REG.all() or []):
                if r2.get("gid") != gid:
                    continue
                # The whole registry row, because banking needs it. An entry
                # without project/mouse/session files itself under "Unfiled"
                # and cannot be found by the animal it came from -- which is
                # the one thing a banked set has to be findable by.
                row = {k: r2.get(k) for k in
                       ("project", "mouse", "session", "key", "loose_key",
                        "label", "duration_s", "cohort")}
                # The registry's label, not the record's. A scan run in a
                # batch never went through the panel, so `session_label` was
                # never filled in and every row in the queue read as a bare
                # gid -- which is not a name anybody can pick a recording by.
                label = r2.get("label") or r2.get("key")
                for p in (r2.get("paths") or []):
                    if isinstance(p, str) and os.path.isdir(p):
                        local = p
                        break
                break
            ran = rec.get("computed_on") or {}
            rows.append({
                "gid": gid,
                "local": local,
                "row": row,
                "params_hash": rec.get("params_hash"),
                "label": label or rec.get("session_label") or gid,
                # NOT the per-channel summaries. Sixty-four of them per
                # recording across thirty-one recordings is about two
                # megabytes to draw a list of names, and the panel reads
                # them out of the vault anyway the moment one is opened --
                # the same argument `_incisor_public` already makes about
                # `_rows`.
                "n_summaries": len(rec.get("channels") or []),
                # Where it was computed, which is NOT where it was filed.
                # `computed` below carries the machine that accepted it.
                "ran_on": ran.get("kind") or "here",
                "slurm_id": ran.get("slurm_id"),
                "picked": picked,
                "hilus": (picked.get("hilus") or {}).get("index"),
                "n_channels": rec.get("n_channels"),
                "computed": rec.get("computed") or {},
                "where": (rec.get("computed") or {}).get("where"),
                "banked": banked,
            })
        rows.sort(key=lambda r: str(r.get("label") or ""))
    except Exception as exc:                             # noqa: BLE001
        return fail("incisor/reviews", exc, 400)
    return jsonify({"ok": True, "reviews": rows, "n": len(rows)})


@app.route("/api/incisor/batch", methods=["POST"])
def api_incisor_batch():
    """Run Incisor on every reachable recording, on the cluster.

    One `cfc.Job` with members, not one job per recording: the members API
    is what the progress card already knows how to draw, and it is what
    `panoramaset.run_set` uses for exactly this. Poll it on
    /api/cfc/job/<id> like everything else.

    Resume is free and is not implemented here. A recording whose answer is
    already in the vault under this question's `params_hash` is skipped in
    milliseconds, because that is what the vault IS -- so a batch that dies
    halfway, or a colleague who ran the other half, costs nothing.
    """
    body = request.get_json(force=True) or {}
    force = bool(body.get("force"))
    try:
        staged, _unknown = _vacc_staged()
        cfg = vaccmod.load_config(LOGS_DIR)
        vaccmod.push_code(cfg, APP_DIR)
    except Exception as exc:                             # noqa: BLE001
        return fail("incisor/batch", exc, 400)

    wanted = body.get("gids")
    members = []
    for rec in (REG.all() or []):
        gid = rec.get("gid")
        row = staged.get(gid) if gid else None
        if not row or row.get("conflict"):
            continue
        if wanted and gid not in wanted:
            continue
        local = None
        for p in (rec.get("paths") or []):
            if isinstance(p, str) and os.path.isdir(p):
                local = p
                break
        members.append({"gid": gid,
                        "label": rec.get("label") or rec.get("key") or gid,
                        "remote": row.get("path"), "local": local})
    if not members:
        return jsonify({"ok": False,
                        "error": "Nothing on the cluster to run."}), 400

    concurrency = body.get("concurrency")

    def work(job):
        job.members_init([{"id": m["gid"], "label": m["label"]}
                          for m in members])

        # Everything knowable locally, before anything is submitted: the
        # channel list, the continuity report and the cache key all come
        # from this machine, and a recording already answered under this
        # question's hash never reaches the cluster at all.
        tasks, skipped, failed = [], 0, 0
        for m in members:
            job.check()
            gid = m["gid"]
            try:
                prep = _incisor_prepare(m, body, force)
            except Exception as exc:                     # noqa: BLE001
                failed += 1
                job.member(gid, status="failed", step=None,
                           error=str(exc)[:200])
                continue
            if prep is None:
                skipped += 1
                job.member(gid, status="done", cached=True,
                           step="already answered")
                continue
            job.member(gid, status="queued", step="waiting for the cluster")
            tasks.append(prep)

        done = 0
        if tasks:
            done, failed = _incisor_run_array(job, tasks, failed, concurrency)
        return {"n": len(members), "done": done, "failed": failed,
                "skipped": skipped, "submitted": len(tasks)}

    # Counted in recordings. The offload stages belong to each member rather
    # than to the batch, so the batch's own stage is the list it is walking.
    steps = [("panorama pool", len(members))]
    job = cfcmod.start({"path": members[0].get("local") or ""}, steps, work,
                       1.0, "vacc:scratch")
    STORE.record_activity([{"action": "incisor.batch",
                            "detail": {"n": len(members), "where": "vacc"}}])
    return jsonify({"ok": True, "job": job.snapshot(), "n": len(members)})


def _incisor_prepare(member, body, force):
    """Everything one member needs, worked out here. None if already answered.

    Deliberately all the local work up front, before a single task is
    submitted: opening the recording, reading its continuity and computing
    the cache key are this machine's job, and doing them while the cluster
    waits is what made the first version of this take forty minutes.
    """
    local = member.get("local")
    if not local:
        raise RuntimeError("this machine cannot open the recording to read "
                           "its channel list")
    sess, err = _session_for(local, None, True)
    if err:
        raise RuntimeError((err or {}).get("error") or "could not open it")
    if not sess.get("gid"):
        sess["gid"] = member["gid"]

    rep = _incisor_report(local)
    spec = _incisor_spec(dict(body, path=local), sess)
    key = incisormod.cache_key(spec, rep)
    if not force and (incisormod.cache_get(key) is not None
                      or _incisor_recall(sess, key) is not None):
        return None

    plan = incisormod.plan_for(sess, spec, rep)
    return {
        "gid": member["gid"], "label": member["label"],
        "sess": sess, "spec_local": spec, "report": rep, "key": key,
        "plan": plan,
        "spec_remote": dict(spec, path=member["remote"]),
        "tool_steps": [("ds read", int(plan["span_s"] * plan["n_channels"])),
                       ("ds detect", plan["n_channels"])],
        "seconds": float((incisormod.estimate(sess, spec, rep) or {})
                         .get("seconds") or 0),
        "megasamples": max(0.001, plan.get("megasamples") or 1.0),
    }


def _incisor_run_array(job, tasks, failed, concurrency=None):
    """Submit every task at once and collect answers as they land.

    One `sbatch --array`, so the cluster runs them in parallel instead of
    this process running them one at a time; one `sacct` per poll for all of
    them, because `poll_states` was always meant to take a list.

    Answers are fetched the moment each task's `result_<i>.json` appears
    rather than at the end, so the queue fills up while the rest are still
    running and a batch that is cancelled halfway keeps what it has.
    """
    cfg = vaccmod.load_config(LOGS_DIR)
    arr = vaccrunmod.VaccArray(cfg, "incisor", tasks,
                               concurrency=concurrency)
    worst = max([t["seconds"] for t in tasks] or [60.0])
    msamp = max([t["megasamples"] for t in tasks] or [1.0])
    arr.submit(seconds=worst, megasamples=msamp)
    for t in tasks:
        job.member(t["gid"], step="queued on " + str(arr.array_id))

    done, taken = 0, set()
    try:
        while True:
            job.check()
            states, ready = arr.poll()
            for i in sorted(ready - taken):
                taken.add(i)
                t = tasks[i]
                try:
                    out = arr.fetch(i)
                    incisormod.cache_put(t["key"], out)
                    _incisor_remember(t["sess"], t["spec_local"], t["key"], out)
                    done += 1
                    job.member(t["gid"], status="done", step=None)
                    # Let the answer go as soon as it is written down.
                    #
                    # A scan of sixty-four channels carries every event on
                    # every one of them in `_rows`, and a batch of
                    # twenty-eight holding all of those at once is what
                    # killed the server the first time this ran in parallel:
                    # no traceback, no error, the process simply gone. The
                    # durable copy is on disk and the recent ones are in
                    # incisor's own bounded cache; this reference is the
                    # only unbounded one.
                    out = None
                    t["sess"] = None
                    t["report"] = None
                except Exception as exc:                 # noqa: BLE001
                    failed += 1
                    job.member(t["gid"], status="failed", step=None,
                               error=str(exc)[:200])
            for i, t in enumerate(tasks):
                if i in taken:
                    continue
                st = states.get(i)
                job.member(t["gid"],
                           status="running" if st == "RUNNING" else "queued",
                           step=(st or "waiting").lower())
                out = vaccmod.outcome_for(st) if st else None
                if out and out[0] != "done":
                    taken.add(i)
                    failed += 1
                    job.member(t["gid"], status="failed", step=None,
                               error=out[1] or out[0])
            if len(taken) >= len(tasks):
                break
            # Every task is finished as far as slurm knows, but a result has
            # not appeared: the accounting database lags the filesystem, so
            # this waits rather than calling them lost.
            time.sleep(vaccrunmod.POLL["running"])
    except cfcmod.Canceled:
        arr.cancel()
        raise
    return done, failed


class _MemberJob:
    """`cfc.Job`'s surface, pointed at one row of a batch.

    `begin` and `tick` become `member(...)` updates rather than stage moves,
    and `check` passes through so cancelling the batch cancels the member
    that is running -- and, through `VaccRun`'s `finally`, scancels it.
    """

    def __init__(self, job, gid):
        self._job = job
        self._gid = gid

    def begin(self, name, of=None, unit=None):
        self._job.member(self._gid, step=name, done=0, of=int(of or 0))

    def tick(self, name, done):
        self._job.member(self._gid, step=name, done=int(done))

    def check(self):
        return self._job.check()

    def set_preview(self, *a, **k):
        return None

    def members_init(self, *a, **k):
        return None

    def member(self, *a, **k):
        return None


# ==========================================================================
# Braces -- putting every dentate spike stamp on the peak it belongs to
# ==========================================================================
# Step three of The Dentist. Incisor found them, Checkup said which ones are
# real, and this says where each one actually is.
#
# The read is one channel, so none of Incisor's per-channel scan machinery is
# here -- but the SPEC is Incisor's, built by `_incisor_spec`, because the
# band, the decimation and the threshold have to be the detector's or "weak
# peak" means weak by a standard nobody chose.


def _braces_who(body):
    """Who is doing this. The profile wins; the body is a fallback for a
    caller that already knows (the harness, and a batch acting for someone
    who started it elsewhere)."""
    return ((body or {}).get("by")
            or (STORE.provenance() or {}).get("user") or "unknown")


def _braces_entry(entry_id):
    """The bank entry, or a 400 that says which id was not found."""
    rec = BANK.get(entry_id)
    if not rec:
        raise ValueError("No bank entry %s." % entry_id)
    return rec


def _braces_session(rec):
    """The recording an entry's events were detected in.

    Through the registry gid, never through the mouse and session numbers.
    Numbering restarts per project -- m1 s1 exists once in every one of them
    -- so matching on the pair finds a different animal's recording and says
    nothing about it. `session_path` is tried first only because it is the
    exact folder the set was banked against; the gid is what makes it
    findable at all on a machine where that path does not exist.
    """
    gid = rec.get("gid")
    row = _session_by_gid(gid) if gid else None
    # `here` is the folders THIS machine can actually reach, which is not
    # the same list as `paths` -- a recording seen on the rig and on a
    # laptop has two, and only one of them opens here. There is no `path`
    # key on a registry row at all; asking for one gets None for every
    # recording in the archive, which reads as "no set can be aligned".
    # `curate.js` has taken `here[0]` since the workbench was written.
    here = (row or {}).get("here") or []
    path = (here[0] if here else None) or rec.get("session_path")
    if not path and (row or {}).get("paths"):
        # Known, but not on this machine. A different sentence, because it
        # is a different problem: nobody has to re-bank anything, they have
        # to plug in the drive.
        raise ValueError(
            "The recording this set came from is not reachable on this "
            "machine. It was last seen at %s."
            % ((row["paths"] or [""])[-1]))
    if not path:
        raise ValueError(
            "This set does not say which recording it came from, so there "
            "is nothing to measure its stamps against. Re-bank it from a "
            "curation set, or import it onto a recording first.")
    sess, err = _session_for(path, None, True)
    if err:
        raise ValueError(
            "The recording this set came from could not be opened here (%s). "
            "It may be on a drive this machine cannot see."
            % ((err or {}).get("error") or "unknown"))
    if not sess.get("gid"):
        sess["gid"] = gid or _gid_for_path(path)
    return sess, (row or {})


def _braces_channels(sess):
    """This recording's channels, with the bad ones actually marked.

    `csc.open_session` writes `"bad": False` on every channel it builds --
    which channels are bad is not in the `.ncs` files, it is a decision
    somebody made about the recording, and it lives in the session record
    keyed on identity. `_incisor_spec` has always looked it up separately for
    exactly this reason.

    Braces did not, so every channel arrived good and the list came up
    sixty-four of sixty-four ticked on a recording with bad channels on
    record. One place now, called by the plan and by the run, so the ticks
    somebody sees are the ticks the read honours.
    """
    stored = _stored_for(sess)
    bad = {int(b) for b in (stored.get("bad_channels") or [])}
    out = []
    for c in (sess.get("channels") or []):
        row = dict(c)
        row["bad"] = int(c["number"]) in bad
        out.append(row)
    return out


def _braces_spec(body, sess):
    """Incisor's spec, narrowed to the one channel and given Braces' own
    two numbers. Built from `_incisor_spec` so the band, the decimation and
    the threshold cannot drift from the detector's."""
    spec = _incisor_spec(dict(body, channels=None), sess)
    # What the magnitude is taken of. CSD by default -- the part of the
    # signal that cannot be volume-conducted -- with the voltage the
    # detectors themselves ran on one setting away, so the two can be
    # compared on the same set rather than argued about.
    spec["measure"] = ("voltage" if body.get("measure") == "voltage"
                       else "csd")
    # The mains, and how long a moving average to run over the trace.
    # Both are settings because both change the number: a notch that is not
    # taken out leaves 60 Hz inside a 5-100 Hz band, and smoothing merges
    # the twin lobes rectification makes at the cost of some timing.
    if body.get("line_hz") is not None:
        spec["line_hz"] = float(body.get("line_hz") or 0.0)
    if body.get("smooth_ms") is not None:
        spec["smooth_ms"] = float(body.get("smooth_ms") or 0.0)
    for key, default in (("window_ms", bracesmod.WINDOW_MS),
                         ("edge_frac", bracesmod.EDGE_FRAC),
                         ("same_ms", bracesmod.SAME_MS)):
        v = body.get(key)
        spec[key] = float(default if v is None else v)
    return spec


@app.route("/api/braces/plan", methods=["POST"])
def api_braces_plan():
    """What a run would read, and from which version -- before it reads it.

    Everything knowable up front is settled up front: which recording, which
    channel and why, which versions can supply the stamps. A set whose
    recording this machine cannot open should say so while somebody can
    still do something about it.
    """
    body = request.get_json(force=True) or {}
    try:
        rec = _braces_entry(body.get("entry_id"))
        sess, row = _braces_session(rec)
        spec = _braces_spec(body, sess)
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/plan", exc, 400,
                    {"entry_id": body.get("entry_id")})

    # Named through the lineage labeller, because the stored NUMBER is not
    # unique: two machines curating the same entry both mint the next one
    # and the union keeps both, so this bank holds histories reading
    # 0,1,2,3,4,3,4. Listed by number alone, two of those rows are the same
    # sentence twice and picking one is a coin toss -- `label_rows` walks
    # `from_v` and gives the second line its own name (v3.1), which is what
    # the version chooser in curation already shows.
    named = versionsmod.label_rows(rec.get("versions") or [])
    versions = []
    for ver, name in named:
        why = None
        if not ver.get("snap"):
            why = ("no snapshot on this machine, so the stamps it held "
                   "cannot be read back")
        versions.append({
            "v": ver.get("v") or 0,
            # What a person reads, and what the dropdown must show: unique
            # where the number is not.
            "name": name,
            "id": ver.get("id"),
            # What a caller must send back. The id where there is one --
            # it is the only thing that names one version and only one --
            # and the number where there is not. Versions minted before ids
            # existed have none, and this archive still holds plenty: on
            # M8s9feb8 three of eight. Sending a literal "null" back for
            # those was the next bug along.
            "ref": BANK.version_key(ver),
            "at": ver.get("at"),
            "by": ver.get("by"), "n": ver.get("n"), "note": ver.get("note"),
            "aligned": bool(ver.get("aligned")),
            "usable": why is None, "why_not": why,
        })
    versions.sort(key=lambda r: versionsmod.key(r["name"]))
    _cur_name, _next_name = versionsmod.tip_next(rec.get("versions") or [])
    return jsonify({
        "ok": True,
        "entry": {"id": rec["id"], "name": rec.get("name"),
                  "n": rec.get("n"), "gid": rec.get("gid"),
                  "type": rec.get("type"),
                  "session_label": rec.get("session_label"),
                  "aligned": rec.get("aligned")},
        "session": {"path": sess.get("path"), "name": sess.get("name"),
                    "fs": sess.get("fs"),
                    "n_channels": len(sess.get("channels") or [])},

        # Every channel, with whether it is marked bad. ALL of them, not
        # only the good ones: a sweep that silently leaves eight channels
        # out is a ranking somebody will read as complete. They arrive
        # unticked instead, which says the same thing and can be undone.
        "channels": [{"number": int(c["number"]),
                      "label": c.get("label"),
                      "bad": bool(c.get("bad"))}
                     for c in _braces_channels(sess)],
        "versions": versions,
        # The NAME of the newest and of the one a commit would write. The
        # number is not unique -- see `versions.tip_next` -- so anything
        # shown to a person has to be the lineage name or it is a label
        # that belongs to two versions at once.
        "current_name": _cur_name,
        "next_name": _next_name,
        "current_version": max([v["v"] for v in versions] or [0]),
        "spec": {k: spec.get(k) for k in
                 ("band", "lfp_fs", "height_sd", "abs_uv", "dist_ms",
                  "estimator", "window_ms", "edge_frac",
                  "same_ms", "invert")},
    })


@app.route("/api/braces/run", methods=["POST"])
def api_braces_run():
    """Read the channel, find its peaks, and propose where each stamp goes.

    A job, because it reads a whole channel -- seconds on a local drive and
    a good deal longer over the network, which is long enough that a request
    holding the connection open is the wrong shape. Poll it on
    /api/cfc/job/<id>, which is not cfc-specific.

    Nothing is written to the bank here. What comes out is a proposal.
    """
    body = request.get_json(force=True) or {}
    try:
        rec = _braces_entry(body.get("entry_id"))
        sess, row = _braces_session(rec)
        spec = _braces_spec(body, sess)
        report = _incisor_report(sess["path"])
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/run", exc, 400,
                    {"entry_id": body.get("entry_id")})

    # Whichever version supplies the stamps, addressed by its id -- the
    # NUMBER is not unique, and this bank holds entries with two versions
    # numbered 3 and two numbered 4.
    src_v = body.get("from_version")
    try:
        if src_v is None:
            events = rec.get("events") or []
        else:
            events, _dropped = BANK.events_at(rec, src_v)
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/run", exc, 400, {"from_version": src_v})
    if not events:
        return jsonify({"ok": False,
                        "error": "There are no stamps in that version to "
                                 "align."}), 400

    who = _braces_who(body)
    span = sum(float(s.get("duration_s") or 0.0)
               for s in (report.get("segments") or [])) or 1.0

    # Only the stamps somebody called a dentate spike. `good: True` is the
    # curation vocabulary's own mark for "this names a real event", so the
    # set of things worth aligning is read from there rather than spelled
    # out here -- a fifth category added to the DS vocabulary tomorrow gets
    # this right without anybody remembering to come back.
    #
    # BY ID *AND* BY DISPLAY NAME. Older entries in this bank carry only
    # `label` -- "Dentate Spike" -- because `label_id` was added later, and
    # `by_label` on those reads {"Dentate Spike": 10} rather than
    # {"spike": 10}. Matching on the id alone silently skipped every stamp
    # in them, which would have looked like a set with nothing to align
    # rather than like a bug.
    goods = [lab for lab
             in (curation.KINDS.get(rec.get("type") or "ds")
                 or curation.KINDS["ds"])["labels"]
             if lab.get("good")]
    align_ids = {lab["id"] for lab in goods} | {lab["name"] for lab in goods}
    # And whatever this entry itself calls them, for a set banked under a
    # vocabulary that has since been renamed.
    for lid, name in (rec.get("label_names") or {}).items():
        if lid in align_ids:
            align_ids.add(name)

    # NOTHING TO ALIGN.
    #
    # A set can be fully curated and hold no events at all -- somebody went
    # through it and rejected every candidate, which is a real answer and
    # nine of the forty-eight sets in this bank are that. Running anyway
    # reads the recording for a minute and files a proposal with no rows in
    # it, which is a thing somebody then has to work out is empty on
    # purpose. Refused here instead, with the reason.
    n_good = sum(1 for ev in events
                 if (ev.get("label_id") or ev.get("label")) in align_ids)
    if not n_good:
        return jsonify({
            "ok": False,
            "error": "Nothing in this set is a dentate spike: all %d "
                     "candidate(s) were rejected or are still undecided. "
                     "There is nothing to align, so nothing was read."
                     % len(events)}), 400

    # Which channels go into the profile.
    #
    # Whatever the caller ticked, and where it said nothing, every channel
    # this recording has not marked bad. A bad channel is not hidden from the
    # list -- it arrives unticked, so leaving it out is visible and putting it
    # back is one click -- but it is not read unless somebody asks for it.
    want_ch = body.get("channels")
    all_ch = _braces_channels(sess)
    if want_ch:
        want = {int(x) for x in want_ch}
    else:
        want = {int(c["number"]) for c in all_ch if not c.get("bad")}
    if not want:
        return jsonify({"ok": False,
                        "error": "No channels are ticked, so there is "
                                 "nothing to build a profile from."}), 400

    # A contact nobody wants is INTERPOLATED, not removed.
    #
    # A current source density is a second difference ACROSS DEPTH. Taking
    # a contact out of the middle of the list does not leave a shorter
    # probe, it leaves an unevenly spaced one -- and a second difference
    # over an uneven grid has a step in it exactly where the missing wire
    # was, which is then the largest thing on the shank. So the geometry is
    # kept whole and the unwanted rows are replaced by the interpolation of
    # their neighbours: they carry no information of their own, which is
    # what "we do not trust this wire" means.
    idx = [i for i, c in enumerate(all_ch) if int(c["number"]) in want]
    use_chans = all_ch[idx[0]:idx[-1] + 1]
    left_out = [int(c["number"]) for c in use_chans
                if int(c["number"]) not in want]

    stamp_times = [float(e["start"]) for e in events
                   if e.get("start") is not None]
    depth_n = int(body.get("depth_band") or bracesmod.DEPTH_BAND)

    def work(job):
        # The probe is screened FIRST, over one clean stretch.
        #
        # A CSD does not merely include a bad contact, it amplifies it: a
        # dead wire between two live ones is the largest deflection
        # anywhere on the shank. Every magnitude question after this --
        # which depth, which peak -- would otherwise be answered with it.
        # Screened contacts join the ones nobody ticked: interpolated, and
        # reported rather than silently dropped.
        screened = bracesmod.screen(sess, use_chans, spec, stamp_times)
        bad_nums = dict(screened)
        for n in left_out:
            bad_nums.setdefault(int(n), "not ticked")

        # Where on the shank these events actually are, worked out from the
        # events themselves: the CSD averaged over a sample of the stamps
        # at their curated times, so what is time-locked to them adds and
        # what is not falls away. The band and the depth profile both come
        # out of that average.
        band_nums, depth_rows, at, prof = bracesmod.depth_band(
            sess, use_chans, spec, stamp_times, want=depth_n, job=job,
            bad=bad_nums)
        # One more contact either side of the band.
        #
        # A CSD has no value at the ends of the list it is
        # given, so reading exactly the band would lose its
        # top and bottom rows -- the two the band was chosen
        # for. The extra pair is read and then thrown away by
        # `compute_csd` itself.
        want_set = set(band_nums)
        on = []
        for i, c in enumerate(use_chans):
            if int(c["number"]) in want_set:
                on.append(c)
            elif ((i + 1 < len(use_chans)
                   and int(use_chans[i + 1]["number"]) in want_set)
                  or (i and int(use_chans[i - 1]["number"]) in want_set)):
                on.append(c)
        job.check()
        # Then only the windows the stamps can reach, on only those
        # channels. Neither half is a shortcut -- reading a channel that
        # cannot see the event, or a stretch no stamp can reach, cannot
        # change where a stamp goes.
        peaks = bracesmod.windowed_peaks(sess, on, report, spec,
                                         stamp_times, job, bad=bad_nums)
        # Recorded, not used: see `params_of`. The profile says the band is
        # sitting on a dipole, which is worth keeping even though nothing
        # is projected onto it.
        peaks["profile"] = {str(k): v for k, v in prof.items()}
        peaks["depth"] = {"channels": band_nums, "profile": depth_rows,
                          "from": at, "of": len(use_chans),
                          "weights": {str(k): v for k, v in prof.items()},
                          "screened": {str(k): v
                                       for k, v in screened.items()}}
        job.check()
        out = bracesmod.propose(events, peaks,
                               window_ms=spec["window_ms"],
                               edge_frac=spec["edge_frac"],
                               same_ms=spec["same_ms"],
                               align_ids=align_ids)
        params = bracesmod.params_of(spec, peaks)
        params["left_out"] = left_out
        rows = out.pop("rows")
        # Into the set, not only into the job's result: the job is gone by
        # tomorrow, and somebody opening this proposal then still has to be
        # able to ask which channels it was measured from.
        out["left_out"] = left_out
        # Which contacts were interpolated rather than believed, on the
        # summary as well as in the params: the panel says so in the line
        # that explains what the measurement was made on, and a set read
        # back tomorrow has to be able to say it too.
        out["screened"] = peaks.get("screened") or {}
        out["depth"] = peaks.get("depth")
        out["n_windows"] = peaks.get("n_windows")
        out["read_s"] = peaks.get("read_s")
        made = BRACES.create(rec["id"], rec.get("gid"), src_v, params, rows,
                             out, name=rec.get("name"), by=who)
        # The summary travels with the job's result so the panel can draw
        # the counts and the histogram without a second request.
        return {"set_id": made["set_id"], "summary": out, "params": params,
                "n_rows": len(rows),
                "n_channels": peaks.get("n_channels"),
                "from_version": src_v}

    steps = [("ds depth", len(use_chans)),
             ("ds windows", max(1, len(bracesmod.spans(
                 stamp_times, spec["window_ms"]))))]
    job = cfcmod.start(spec, steps, work, max(0.001, span / 60.0))
    STORE.record_activity([{
        "action": "braces.run",
        "detail": {"entry": rec["id"], "n_channels": len(use_chans),
                   "n": len(events), "from_version": src_v,
                   "window_ms": spec["window_ms"]},
    }])
    return jsonify({"ok": True, "job": job.snapshot(),
                    "n_channels": len(use_chans), "left_out": left_out,
                    "n": len(events)})


@app.route("/api/braces/sets")
def api_braces_sets():
    """Every alignment on this machine, accepted or still being reviewed."""
    gid = request.args.get("gid")
    out = []
    for rec in BRACES.all():
        if gid and rec.get("gid") != gid:
            continue
        _moves, _flags, counts, _rej = brsetmod.resolve(rec)
        out.append({
            "set_id": rec["set_id"], "entry_id": rec.get("entry_id"),
            "gid": rec.get("gid"), "name": rec.get("name"),
            "created": rec.get("created"),
            "from_version": rec.get("from_version"),
            "params": rec.get("params"),
            "summary": rec.get("summary"),
            "committed": rec.get("committed"),
            "n": len(rec.get("rows") or []),
            "counts": counts,
        })
    return jsonify({"ok": True, "sets": out, "n": len(out)})


@app.route("/api/braces/set/<set_id>")
def api_braces_set(set_id):
    """One proposal, with every row and whatever has been decided about it."""
    rec = BRACES.get(set_id)
    if not rec:
        return jsonify({"ok": False,
                        "error": "No alignment set %s." % set_id}), 404
    moves, _flags, counts, rejects = brsetmod.resolve(rec)
    entry = BANK.get(rec.get("entry_id")) or {}
    # Where the recording is, so the panel can open it in the trace view
    # without a second round trip to work out something the set already
    # implies. None when this machine cannot reach it, which the browse
    # button reads as "not from here".
    here = None
    try:
        sess, _row = _braces_session(entry)
        here = sess.get("path")
    except Exception:                                    # noqa: BLE001
        here = None
    return jsonify({
        "session_path": here,
        "ok": True,
        "set": {k: rec.get(k) for k in
                ("set_id", "entry_id", "gid", "name", "from_version",
                 "params", "summary", "created", "committed", "rows",
                 "calls")},
        "counts": counts,
        "would_move": len(moves),
        "entry": {"id": entry.get("id"), "name": entry.get("name"),
                  "n": entry.get("n"),
                  "session_label": entry.get("session_label"),
                  "label_names": entry.get("label_names") or {},
                  "current_version": max(
                      [v.get("v") or 0
                       for v in (entry.get("versions") or [])] or [0]),
                  "current_name": versionsmod.tip_next(
                      entry.get("versions") or [])[0],
                  "next_name": versionsmod.tip_next(
                      entry.get("versions") or [])[1]},
    })


@app.route("/api/braces/set/<set_id>/decide", methods=["POST"])
def api_braces_decide(set_id):
    """Confirm a row, keep it where it was, or move it somewhere else."""
    body = request.get_json(force=True) or {}
    calls = body.get("calls")
    if calls is None and body.get("call") is not None:
        # One row, which is what the bench sends on every keystroke.
        calls = {str(body.get("row")): {"call": body["call"],
                                        "t": body.get("t")}}
    try:
        rec = BRACES.decide(set_id, calls or {}, by=_braces_who(body))
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/decide", exc, 400, {"set_id": set_id})
    moves, _flags, counts, rejects = brsetmod.resolve(rec)
    return jsonify({"ok": True, "counts": counts, "would_move": len(moves),
                    "calls": rec.get("calls") or {}})


@app.route("/api/braces/set/<set_id>/commit", methods=["POST"])
def api_braces_commit(set_id):
    """Write the alignment as the next version of the bank entry.

    A dry run by default, and the panel shows what comes back before
    anything happens: a timestamp rewrite that cannot be read before it
    happens should not be offered at all. The same rule `retime` follows,
    for the same reason.
    """
    body = request.get_json(force=True) or {}
    rec = BRACES.get(set_id)
    if not rec:
        return jsonify({"ok": False,
                        "error": "No alignment set %s." % set_id}), 404
    if rec.get("committed"):
        return jsonify({
            "ok": False,
            "error": "This alignment is already version %s of the set."
                     % (rec["committed"] or {}).get("version")}), 400

    moves, flags, counts, rejects = brsetmod.resolve(rec)
    dry = body.get("apply") is not True
    try:
        # The labels that name a real event, worked out the same way the
        # run worked them out: from the curation vocabulary for this
        # entry's kind, by id AND by display name, plus whatever this
        # entry itself calls them. Everything else is a candidate somebody
        # REJECTED, and an aligned version has no business carrying it.
        entry = BANK.get(rec.get("entry_id")) or {}
        goods = [lab for lab
                 in (curation.KINDS.get(entry.get("type") or "ds")
                     or curation.KINDS["ds"])["labels"]
                 if lab.get("good")]
        keep_ids = ({lab["id"] for lab in goods}
                    | {lab["name"] for lab in goods})
        for lid, name in (entry.get("label_names") or {}).items():
            if lid in keep_ids:
                keep_ids.add(name)
        report = BANK.align(rec["entry_id"], moves, rec.get("params") or {},
                            note=body.get("note"), by=_braces_who(body),
                            dry_run=dry,
                            from_version=rec.get("from_version"),
                            flags=flags, keep_ids=keep_ids,
                            reject=rejects)
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/commit", exc, 400, {"set_id": set_id})

    report["counts"] = counts
    # Said out loud rather than left to be noticed: a flag nobody resolved
    # does not move, and the number of them belongs beside the button.
    report["left_alone"] = counts.get("waiting", 0)
    if dry or report.get("error"):
        return jsonify({"ok": not report.get("error"), "report": report})

    BRACES.mark_committed(set_id, report.get("version"),
                          report.get("version_id"), by=_braces_who(body))
    STORE.record_activity([{
        "action": "braces.commit",
        "detail": {"entry": rec["entry_id"], "set": set_id,
                   "version": report.get("version"),
                   "moved": report.get("moved"),
                   "left_alone": report["left_alone"]},
    }])
    return jsonify({"ok": True, "report": report})


@app.route("/api/braces/set/<set_id>/profile", methods=["POST"])
def api_braces_profile(set_id):
    """The summed profile over one short window, for the bench.

    The bench has to draw the thing the rule actually looked at. Drawing one
    channel would be drawing something else -- a trace that peaks a few
    milliseconds from where the decision was made, which is exactly the
    disagreement this tool exists to remove, shown to the person being asked
    to adjudicate it.

    Read here rather than assembled in the browser: six hundred milliseconds
    of sixty-four channels is a short read on this side and sixty-four
    requests on the other.
    """
    body = request.get_json(force=True) or {}
    rec = BRACES.get(set_id)
    if not rec:
        return jsonify({"ok": False,
                        "error": "No alignment set %s." % set_id}), 404
    entry = BANK.get(rec.get("entry_id"))
    if not entry:
        return jsonify({"ok": False,
                        "error": "That set's bank entry is gone."}), 404
    try:
        sess, _row = _braces_session(entry)
        report = _incisor_report(sess["path"])
        pr = rec.get("params") or {}
        spec = _braces_spec(dict(body, band=pr.get("band")), sess)
        want = {int(x) for x in (pr.get("channels") or [])}
        chans = [c for c in _braces_channels(sess)
                 if int(c["number"]) in want] or _braces_channels(sess)
        t0 = float(body.get("t0"))
        t1 = float(body.get("t1"))
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/profile", exc, 400, {"set_id": set_id})
    if not (t1 > t0):
        return jsonify({"ok": False, "error": "Empty window."}), 400

    try:
        # The set's own screening, so the bench draws the trace this
        # proposal was made on rather than a fresh measurement over
        # contacts the run did not believe.
        got = bracesmod.profile_window(
            sess, chans, report, spec, t0, t1,
            bad=dict(pr.get("screened") or {}))
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/profile", exc, 400, {"set_id": set_id})
    return jsonify({"ok": True, **got})


@app.route("/api/braces/set/<set_id>/delete", methods=["POST"])
def api_braces_delete(set_id):
    """Throw away a proposal nobody accepted."""
    try:
        return jsonify(BRACES.forget(set_id))
    except Exception as exc:                             # noqa: BLE001
        return fail("braces/delete", exc, 400, {"set_id": set_id})


def _n_good(rec):
    """How many events in this entry are the thing Braces aligns.

    The curation vocabulary decides, not a hard-coded word: a fifth
    category added to the DS labels tomorrow is handled without anybody
    remembering to come back here. Counted by id and by display name,
    because entries banked before `label_id` existed carry only the name.
    """
    goods = [lab for lab
             in (curation.KINDS.get(rec.get("type") or "ds")
                 or curation.KINDS["ds"])["labels"]
             if lab.get("good")]
    want = {lab["id"] for lab in goods} | {lab["name"] for lab in goods}
    for lid, name in (rec.get("label_names") or {}).items():
        if lid in want:
            want.add(name)
    n = 0
    for ev in (rec.get("events") or []):
        if (ev.get("label_id") or ev.get("label")) in want:
            n += 1
    return n


def _tip_usable(vers):
    """The newest version whose stamps can be read back on this machine.

    `versions.tip_next` names the newest there is, which is the right
    answer to "what is this entry on" and the wrong one to "what can a run
    start from": a version that arrived as a row without its snapshot has
    a name and a count and no times. Newest by LINEAGE rather than last in
    the list, because creation order and lineage order are the same thing
    only until something branches.
    """
    named = versionsmod.label_rows(vers or [])
    ok = [name for ver, name in named if ver.get("snap")]
    return versionsmod.newest(ok) if ok else None


@app.route("/api/bank/sync")
def api_bank_sync():
    """Which entries and versions have reached the database, and which have
    not.

    `?verify=1` asks the database; without it the answer comes from the
    local push cursor, which is instant and works with the network down.
    `?id=` narrows it to one entry.
    """
    want_id = request.args.get("id")
    verify = request.args.get("verify") in ("1", "true", "yes")
    state = {}
    try:
        state = CLOUD.cloud.state() or {}
    except Exception:                                    # noqa: BLE001
        state = {}
    last_push = state.get("last_push")

    entries = [e for e in BANK.all()
               if not want_id or e.get("id") == want_id]

    # What the database holds, asked once for all of them rather than once
    # each: forty-eight round trips to answer one panel is a panel nobody
    # opens twice.
    up_entry, up_snap, err = {}, {}, None
    if verify:
        try:
            # `query=` is the whole query string, and `select_all` does
            # not add one of its own -- so the column list goes here, and
            # the snapshot table's column is `v`, the same name the push
            # writes. Asked for by name rather than `*`: the entries table
            # carries every event of every set, which is megabytes nobody
            # needs to answer "is it up there".
            for row in CLOUD.cloud.select_all(
                    "bank_entries", query="select=id,n,versions,updated_at"):
                up_entry[row.get("id")] = row
            for row in CLOUD.cloud.select_all(
                    "bank_snapshots", query="select=entry_id,v"):
                up_snap.setdefault(str(row.get("entry_id")), set()).add(
                    str(row.get("v")))
        except Exception as exc:                         # noqa: BLE001
            err = str(exc)

    out = []
    for rec in entries:
        vers = list(rec.get("versions") or [])
        named = versionsmod.label_rows(vers)
        touched = cloudsync._bank_touched(rec)
        # "Waiting" means changed since the last push finished. A machine
        # that has never pushed has everything waiting, which is true.
        waiting = True
        if last_push and touched:
            waiting = cloudsync._after(touched, last_push)
        elif last_push and not touched:
            waiting = False

        # Demo recordings never go up, by design -- so reporting one as
        # "not in the database" is crying wolf about the one thing here
        # that is working exactly as intended.
        demo = CLOUD._is_demo(rec)
        row = {
            "id": rec.get("id"), "name": rec.get("name"),
            "gid": rec.get("gid"), "local_only": bool(demo),
            "session_label": rec.get("session_label"),
            "n": rec.get("n"),
            "touched": touched,
            "waiting": bool(waiting),
            "n_versions": len(vers),
            "newest": (named[-1][1] if named else None),
            "versions": [],
        }
        cloud_row = up_entry.get(rec.get("id")) if verify else None
        there = up_snap.get(str(rec.get("id"))) or set()
        their_v = set()
        if cloud_row:
            for v in (cloud_row.get("versions") or []):
                if isinstance(v, dict) and v.get("v") is not None:
                    their_v.add(str(v.get("v")))
        for ver, name in named:
            vn = str(ver.get("v"))
            row["versions"].append({
                "v": ver.get("v"), "name": name,
                "id": ver.get("id"),
                "at": ver.get("at"), "by": ver.get("by"),
                "n": ver.get("n"),
                # A version with no snapshot HERE cannot have sent one, and
                # is the reason somebody else may not be able to read it
                # back. Said plainly rather than left to be inferred from a
                # missing row at the other end.
                "snap_here": bool(ver.get("snap")),
                "in_cloud": (vn in their_v) if verify and cloud_row else None,
                "snap_in_cloud": (vn in there) if verify else None,
            })
        if verify:
            row["in_cloud"] = bool(cloud_row)
            row["cloud_n"] = (cloud_row or {}).get("n")
            row["cloud_updated"] = (cloud_row or {}).get("updated_at")
            row["cloud_versions"] = len(their_v)
            # The three ways of being out of step, named so the panel does
            # not have to work them out from four numbers.
            missing = [v["name"] for v in row["versions"]
                       if v["in_cloud"] is False]
            no_snap = [v["name"] for v in row["versions"]
                       if v["snap_here"] and v["snap_in_cloud"] is False]
            row["missing_versions"] = missing
            row["missing_snapshots"] = no_snap
            row["state"] = ("local only" if demo
                            else "absent" if not cloud_row
                            else "versions" if missing
                            else "snapshots" if no_snap
                            else "behind" if row["waiting"]
                            else "synced")
        else:
            row["state"] = ("local only" if demo
                            else "waiting" if row["waiting"] else "sent")
        out.append(row)

    out.sort(key=lambda r: (r.get("touched") or ""), reverse=True)
    return jsonify({
        "ok": True,
        # A property, not a call.
        "configured": bool(CLOUD.cloud.configured),
        "verified": bool(verify and not err),
        "error": err,
        "last_push": last_push,
        "n": len(out),
        "entries": out,
    })


@app.route("/api/braces/candidates")
def api_braces_candidates():
    """Dentate spike sets that could be aligned, newest first.

    Curated sets only. An uncurated import is a list of candidates rather
    than a list of events, and moving those before anybody has said which
    are real is work done twice -- the flags would be about stamps that get
    thrown away an hour later.
    """
    gid = request.args.get("gid")
    out = []
    for rec in BANK.all():
        if (rec.get("type") or "") != "ds":
            continue
        if gid and rec.get("gid") != gid:
            continue
        if not rec.get("specified"):
            continue
        # NOTHING TO ALIGN, so not offered.
        #
        # A set can be fully curated and hold no events at all: somebody
        # went through it and rejected every candidate, which is a real
        # answer and nine of the sets in this bank are that, one of them
        # 738 rejections. They were listed and greyed out for a while,
        # which is defensible -- "this one is finished and it is all
        # garbage" is worth being able to see -- but the place to see that
        # is the Event Bank, which holds every entry and says what is in
        # it. A list of things to align should hold things to align.
        if not _n_good(rec):
            continue
        vers = rec.get("versions") or []
        out.append({
            "id": rec["id"], "name": rec.get("name"),
            "gid": rec.get("gid"), "n": rec.get("n"),
            "project": rec.get("project"), "mouse": rec.get("mouse"),
            "session": rec.get("session"),
            "session_label": rec.get("session_label"),
            "by_label": rec.get("by_label") or {},
            "current_version": max([v.get("v") or 0 for v in vers] or [0]),
            "current_name": versionsmod.tip_next(vers)[0],
            # How many of these are actually dentate spikes.
            #
            # Not `n`, which counts candidates: a set can be fully curated
            # and hold nothing but rejections, and there is nothing to
            # align in that. Worked out from the curation vocabulary the
            # same way the run works it out -- by id AND by display name,
            # because older entries carry only the name.
            "n_good": _n_good(rec),
            # The whole history, named and in lineage order, so a bulk
            # table can show which version each entry would be read from
            # and let any of them be changed before anything runs. `ref` is
            # what a run must be given back: the per-version id where there
            # is one, because it is the only thing that names one version
            # and only one, and the number where there is not.
            "versions": [
                {"v": ver.get("v") or 0,
                 "name": name,
                 "ref": BANK.version_key(ver),
                 "n": ver.get("n"),
                 "at": ver.get("at"),
                 "by": ver.get("by"),
                 "note": ver.get("note"),
                 "aligned": bool(ver.get("aligned")),
                 # A version with no snapshot on this machine cannot
                 # supply stamps, so it cannot be a starting point.
                 "usable": bool(ver.get("snap")),
                 # The newest one that can actually be read HERE.
                 #
                 # Not the same as the newest, and the difference is not
                 # rare: measured on this bank, 14 of 49 sets have a tip
                 # whose snapshot never reached this machine, so the
                 # newest READABLE version is one or more behind. A bulk
                 # run defaulting to a version it cannot open is a queue
                 # of failures, and one silently defaulting to an older
                 # version without saying so is worse.
                 "newest": name == _tip_usable(vers)}
                for ver, name in versionsmod.label_rows(vers)
            ],
            "newest_name": versionsmod.tip_next(vers)[0],
            "newest_usable_name": _tip_usable(vers),
            "aligned": rec.get("aligned"),
            "added": rec.get("added"),
        })
    out.sort(key=lambda r: ((r.get("added") or {}).get("at") or ""),
             reverse=True)
    return jsonify({"ok": True, "sets": out, "n": len(out)})


@app.route("/api/cfc/cache")
def api_cfc_cache():
    """What the comodulogram cache is holding. Diagnostic; ?clear=1 empties it.

    Same shape as /api/panel/cache, and there for the same two reasons: to be
    able to see whether a repeat really was a repeat, and to be able to force
    a recompute without editing the request. A harness needs the second one --
    a run that comes back cached never shows a progress display, so checks
    aimed at the progress display fail on a feature that works.
    """
    if request.args.get("clear"):
        cfcmod.cache_clear()
    return jsonify({"ok": True, "cleared": bool(request.args.get("clear"))})


@app.route("/api/cfc/job/<job_id>")
def api_cfc_job(job_id):
    job = cfcmod.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "No such run. It may have "
                                              "finished long enough ago to "
                                              "have been dropped."}), 404
    return jsonify({"ok": True, "job": job.snapshot()})


@app.route("/api/cfc/job/<job_id>/cancel", methods=["POST"])
def api_cfc_cancel(job_id):
    job = cfcmod.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "No such run."}), 404
    job.cancel()
    return jsonify({"ok": True})


@app.route("/api/cfc/result/<job_id>")
def api_cfc_result(job_id):
    job = cfcmod.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "No such run."}), 404
    snap = job.snapshot()
    if snap["status"] != "done":
        return jsonify({"ok": False, "status": snap["status"],
                        "error": snap.get("error")
                                 or "That run has not finished."}), 409
    return jsonify({"ok": True, "result": job.result, "job": snap})


@app.route("/api/cfc/job/<job_id>/preview")
def api_cfc_job_preview(job_id):
    """The picture a run has built so far, for the waiting screen.

    Its own route, not part of the job snapshot: the snapshot is polled
    several times a second by every tool, and sixty kilobytes of base64
    riding along with it would be two hundred kilobytes a second of
    nothing for the tools that have no preview. The snapshot carries
    `preview_rev`, an integer, and the caller asks for the image when
    that changes.
    """
    job = cfcmod.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "No such run."}), 404
    uri, rev = job.preview()
    if not uri:
        return jsonify({"ok": True, "png": None, "rev": rev})
    return jsonify({"ok": True, "png": uri, "rev": rev})


def _figure_plan(run):
    """What it would take to rebuild this figure. The original, unchanged --
    only moved, so the registry owns it rather than one route."""
    rec, complete = rebuild.recipe_for(run)
    steps, _problems = rebuild.audit(
        rec, complete,
        [p["id"] for p in analysis.PANELS],
        [c["id"] for c in analysis.COLORMAPS],
        list(compose.PAGE_PRESETS.keys()),
        STORE.all_sessions())
    worst = "ok"
    for st in steps:
        if st["status"] == "missing":
            worst = "missing"
            break
        if st["status"] == "warn":
            worst = "warn"
    return {"recipe": rec, "complete": complete, "steps": steps,
            "verdict": worst}


def _panorama_plan(run):
    """Panorama kept its answers, so most of this is already done.

    A figure has to be made again from the recording. A Panorama does not:
    the numbers behind it are in the vault under the recording and the
    settings that produced them, so re-opening it is a read, and the only
    open question is whether the recording is still reachable for a *fresh*
    run to compare against.
    """
    sess = run.get("session") or {}
    gid = sess.get("gid")
    params = run.get("parameters") or {}
    ph = pnsetmod.params_hash(params) if params else None
    kept = bool(gid and ph and PNSETS.result_get(gid, ph))
    here = [p for p in (sess.get("paths") or [sess.get("path")]) if p]
    reachable = any(os.path.isdir(p) for p in here)

    steps = [
        {"id": "answer", "title": "Find the numbers it was drawn from",
         "status": "ok" if kept else "warn",
         "what": ("Kept, under this recording and these settings."
                  if kept else
                  "Not kept -- this ran before Panorama filed its answers, "
                  "so the figure can be re-made but not compared."),
         },
        {"id": "recording", "title": "Locate the recording",
         "status": "ok" if reachable else "missing",
         "what": (here[0] if reachable else
                  "None of its paths are reachable from this machine."),
         },
    ]
    return {
        "recipe": {"gid": gid, "params_hash": ph, "parameters": params,
                   "label": run.get("label")},
        "complete": kept,
        "steps": steps,
        "verdict": "ok" if kept and reachable else
                   ("warn" if reachable else "missing"),
    }


def _panorama_verify(run):
    """Is the answer still the answer?

    Compares against the numbers, not the picture. A colormap change is not a
    result changing, and a result changing is not hidden by a rendering that
    happens to look the same.
    """
    sess = run.get("session") or {}
    gid = sess.get("gid")
    params = run.get("parameters") or {}
    ph = pnsetmod.params_hash(params) if params else None
    was = PNSETS.result_get(gid, ph) if (gid and ph) else None
    if not was:
        raise LookupError("This ran before Panorama kept its answers, so "
                          "there is nothing to compare a new run against.")
    return {"gid": gid, "params_hash": ph,
            "computed": was.get("computed"),
            "summary": {k: was.get(k) for k in
                        ("modal_hz", "median_hz", "n_used", "n_windows",
                         "n_nopeak", "n_rejected") if k in was}}


def _toolkit_plan(run):
    """A ToolKit export is a query, so re-running it is cheap and exact.

    Nothing has to be read off a drive: the scope names which recordings, the
    registry holds their bad channels, and the answer falls out. What can
    change is the answer -- somebody marks a channel bad next week and the
    same question returns a different list, which is the point of asking it
    again rather than a reason not to.
    """
    params = run.get("parameters") or {}
    args = {k: params.get(k) for k in
            ("scope", "key", "mouse", "group", "date_from", "date_to")}
    args["scope"] = args.get("scope") or "all"
    try:
        picked = toolkit.select(STORE.all_sessions(), **args)
        err = None
    except Exception as exc:                             # noqa: BLE001
        picked, err = [], str(exc)
    was = _int_or_none((run.get("summary") or {}).get("rows")) \
        or _int_or_none(run.get("rows"))
    steps = [
        {"id": "scope", "title": "Read the scope back",
         "status": "ok" if not err else "missing",
         "what": err or toolkit.scope_label(**args)},
        {"id": "sessions", "title": "Find the recordings it covered",
         "status": "ok" if picked else "warn",
         "what": ("%d recording(s) match that scope now." % len(picked))
                 if picked else
                 "No recording matches that scope any more."},
    ]
    if was is not None:
        steps.append({"id": "rows", "title": "What it found when it ran",
                      "status": "ok", "what": "%d row(s)." % was})
    return {"recipe": dict(args, form=params.get("form"),
                           include_clean=params.get("include_clean")),
            "complete": not err,
            "steps": steps,
            "verdict": "missing" if err else ("ok" if picked else "warn")}


def _toolkit_verify(run):
    """Ask the same question again and say whether the answer moved."""
    params = run.get("parameters") or {}
    args = {k: params.get(k) for k in
            ("scope", "key", "mouse", "group", "date_from", "date_to")}
    args["scope"] = args.get("scope") or "all"
    form = params.get("form") or "long"
    picked = toolkit.select(STORE.all_sessions(), **args)
    rows = toolkit.rows(picked, form,
                        include_clean=bool(params.get("include_clean")))
    was = _int_or_none((run.get("summary") or {}).get("rows")) \
        or _int_or_none(run.get("rows"))
    now = len(rows)
    return {
        "scope": toolkit.scope_label(**args),
        "was": was, "now": now,
        "same": (was is None or was == now),
        "note": ("It still comes out the same: %d row(s)." % now)
                if was == now else
                ("It was %s row(s) and is now %d -- bad channels have been "
                 "marked or cleared since." % (was, now) if was is not None
                 else "The original did not record how many rows it found, "
                      "so there is nothing to compare %d against." % now),
    }


def _deck_plan(run):
    """A deck export is re-runnable as long as the deck is still there.

    And as long as its slides still point at results that exist -- which is
    the part that rots, because a slide holds a result id and filing a result
    into a folder changes it. `_repoint` exists for exactly that, so this
    checks the outcome rather than assuming it worked.
    """
    deck_id = (run.get("parameters") or {}).get("id") or run.get("deck_id")
    deck = RESULTS.get_deck(deck_id) if deck_id else None
    slides = (deck or {}).get("slides") or []
    dangling = 0
    for sl in slides:
        for it in (sl.get("items") or []):
            rid = it.get("result_id") or it.get("id")
            if rid and not RESULTS.resolve({"result_id": rid}):
                dangling += 1
    steps = [
        {"id": "deck", "title": "Find the deck",
         "status": "ok" if deck else "missing",
         "what": ((deck or {}).get("title") or deck_id or "(no id recorded)")
                 if deck else
                 "That deck is not on this machine. It may not have been "
                 "committed, or it was deleted."},
        {"id": "slides", "title": "Check the slides still point at something",
         "status": "ok" if (deck and not dangling) else
                   ("warn" if deck else "missing"),
         "what": ("There is no deck to check." if not deck
                  else "%d slide(s), all resolving." % len(slides)
                  if not dangling
                  else "%d slide item(s) point at a result that is not here."
                       % dangling)},
    ]
    return {"recipe": {"id": deck_id, "slides": len(slides)},
            "complete": bool(deck),
            "steps": steps,
            "verdict": "missing" if not deck else
                       ("warn" if dangling else "ok")}


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


recipemod.register("figure", "Rebuild\u2026", _figure_plan)
recipemod.register("panorama", "Re-open\u2026", _panorama_plan,
                   verify=_panorama_verify)
recipemod.register("toolkit", "Run it again\u2026", _toolkit_plan,
                   verify=_toolkit_verify)
recipemod.register("deck", "Re-export\u2026", _deck_plan)


@app.route("/api/recipe/<run_id>")
def api_recipe(run_id):
    """What it would take to make this again -- whatever kind it is.

    The figure-only route below stays, because figrebuild.js calls it and a
    rebuild is not the thing to break while generalising rebuilds.
    """
    run = STORE.get_run(run_id)
    if not run:
        return jsonify({"ok": False, "error": "No run " + run_id}), 404
    try:
        plan = recipemod.plan_for(run)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("recipe", exc, 400, {"run": run_id})
    return jsonify({"ok": True, "run": run,
                    "offer": recipemod.offer(run), **plan})


@app.route("/api/recipe/<run_id>/verify", methods=["POST"])
def api_recipe_verify(run_id):
    """Does it still come out the same?"""
    run = STORE.get_run(run_id)
    if not run:
        return jsonify({"ok": False, "error": "No run " + run_id}), 404
    try:
        got = recipemod.verify(run)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("recipe/verify", exc, 400, {"run": run_id})
    return jsonify({"ok": True, **got})


@app.route("/api/figure/recipe/<run_id>")
def api_figure_recipe(run_id):
    """What it would take to rebuild this figure, and what stands in the way.

    Everything is checked before anything is done, so the caller can show the
    whole plan -- including the parts that will not work -- rather than
    discovering a missing drive four steps in.
    """
    run = STORE.get_run(run_id)
    if not run:
        return jsonify({"ok": False, "error": "No run " + run_id}), 404
    if run.get("kind") != "figure":
        return jsonify({"ok": False,
                        "error": "Run %s is a %s, not a figure."
                                 % (run_id, run.get("kind") or "record")}), 400

    recipe, complete = rebuild.recipe_for(run)
    try:
        steps, problems = rebuild.audit(
            recipe, complete,
            [p["id"] for p in analysis.PANELS],
            [c["id"] for c in analysis.COLORMAPS],
            list(compose.PAGE_PRESETS.keys()),
            STORE.all_sessions())
    except Exception as exc:
        return fail("figure/recipe", exc, 400, {"run": run_id})

    worst = "ok"
    for st in steps:
        if st["status"] == "missing":
            worst = "missing"
            break
        if st["status"] == "warn":
            worst = "warn"
    return jsonify({"ok": True, "run": run, "recipe": recipe,
                    "complete": complete, "steps": steps,
                    "problems": problems, "verdict": worst})


@app.route("/api/figure/export", methods=["POST"])
def api_figure_export():
    body = request.get_json(force=True) or {}
    layout = body.get("layout") or {}
    fmt = (body.get("format") or "png").lower()
    if fmt not in compose.MIME:
        return jsonify({"ok": False, "error": "Unsupported format: " + fmt}), 400

    sessions, problems = {}, []
    for sid, spec in (body.get("sessions") or {}).items():
        sess, err = _session_for(spec.get("path", ""),
                                 _even_only_arg(spec),
                                 bool(spec.get("invert", True)))
        if err:
            problems.append("%s: %s" % (sid, err.get("error")))
        else:
            sessions[sid] = sess
    if not sessions:
        return jsonify({"ok": False,
                        "error": "No session could be opened. "
                                 + ("; ".join(problems) if problems else "")}), 400

    try:
        blob, panel_problems = compose.render_figure(
            sessions, layout, fmt=fmt, dpi=int(body.get("dpi", 200)))
    except compose.ComposeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("figure/export", exc, 400, {"format": fmt})

    # A figure is a result worth reproducing, so it goes in the history too.
    run = STORE.record_run({
        "kind": "figure", "script": "Xplorefinder figure",
        "label": layout.get("title") or "figure",
        "status": "done", "format": fmt,
        "parameters": {k: layout.get(k) for k in
                       ("t0", "t1", "highpass", "lowpass", "notch", "cmap",
                        "rows", "cols", "page", "bad_channels")},
        "panels": [{"panel": p.get("panel"), "title": p.get("title"),
                    "row": p.get("row"), "col": p.get("col")}
                   for p in (layout.get("panels") or [])],
        # The parameters above are for reading; this is for rebuilding. A
        # summary cannot be rebuilt from, so the whole layout is kept.
        "recipe": rebuild.pack_recipe(layout, body.get("sessions") or {}),
        "session": layout.get("identity") or {},
        "problems": panel_problems,
    })

    stamp = time.strftime("%Y%m%d_%H%M%S")
    name = "%s_%s.%s" % (_safe_name(layout.get("title") or "figure"), stamp, fmt)

    # Every export is also filed under Output/, grouped by session, so figures
    # are recoverable without hunting through the browser download folder.
    saved = None
    try:
        ident = layout.get("identity") or {}
        saved = save_output(blob, name, subdir=ident.get("label"),
                            lane=lane_of(body))
        STORE.update_run(run["id"], {"output": saved})
    except Exception as exc:
        STORE.record_error("figure/save", "Could not write to Output/: %s" % exc,
                           None, {"name": name})

    resp = Response(blob, mimetype=compose.MIME[fmt], headers={
        "Content-Disposition": 'attachment; filename="%s"' % name,
        "X-Barry-Run-Id": run["id"],
    })
    if saved:
        resp.headers["X-Barry-Output"] = saved["rel"]
        if saved.get("github"):
            resp.headers["X-Barry-Github"] = saved["github"]
    if panel_problems:
        resp.headers["X-Barry-Problems"] = " | ".join(panel_problems)[:900]
    return resp


@app.route("/api/figure/preview", methods=["POST"])
def api_figure_preview():
    """Same render as export, returned inline as a PNG for the preview pane."""
    body = request.get_json(force=True) or {}
    layout = body.get("layout") or {}
    sessions = {}
    for sid, spec in (body.get("sessions") or {}).items():
        sess, err = _session_for(spec.get("path", ""),
                                 _even_only_arg(spec),
                                 bool(spec.get("invert", True)))
        if not err:
            sessions[sid] = sess
    if not sessions:
        return jsonify({"ok": False, "error": "No session loaded."}), 400
    try:
        blob, problems = compose.render_figure(
            sessions, layout, fmt="png", dpi=int(body.get("dpi", 110)))
    except compose.ComposeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("figure/preview", exc, 400)

    import base64
    return jsonify({"ok": True, "problems": problems,
                    "image": "data:image/png;base64,"
                             + base64.b64encode(blob).decode("ascii")})


def _safe_name(text):
    keep = "".join(c if (c.isalnum() or c in " -_.") else "_" for c in str(text))
    return (keep.strip() or "figure")[:80]


# ==========================================================================
# Video / tracking
# ==========================================================================
@app.route("/api/video/status")
def api_video_status():
    return jsonify({"ok": True, **video.status()})


@app.route("/api/video/list", methods=["POST"])
def api_video_list():
    body = request.get_json(force=True) or {}
    folder = body.get("folder", "")
    media = video.find_media(folder)
    out = []
    for v in media["videos"]:
        try:
            out.append(video.probe(v["path"]))
        except Exception as exc:
            out.append(dict(v, error=str(exc)))
    return jsonify({"ok": True, "videos": out, "tracking": media["tracking"],
                    **video.status()})


@app.route("/api/video/convert", methods=["POST"])
def api_video_convert():
    """Transcode a whole video to MP4 so the browser can seek it itself.

    Runs in the background; poll /api/video/convert/status. The clip player
    keeps working the whole time, so this never blocks looking at the video.
    """
    body = request.get_json(force=True) or {}
    path = body.get("path", "")
    if body.get("clear"):
        return jsonify({"ok": True, "removed": video.clear_converted(),
                        "disk": video.converted_size_on_disk()})
    try:
        st = video.convert_start(path, force=bool(body.get("force")))
    except video.VideoError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:                              # noqa: BLE001
        return fail("video/convert", exc, 400, {"path": path})
    return jsonify({"ok": True, **st, "disk": video.converted_size_on_disk()})


@app.route("/api/video/convert/status")
def api_video_convert_status():
    path = request.args.get("path", "")
    st = video.convert_state(path) if path else {"state": "none"}
    return jsonify({"ok": True, **st, "disk": video.converted_size_on_disk()})


@app.route("/api/video/converted")
def api_video_converted():
    """Serve the converted MP4 itself, with range support so it seeks.

    send_file handles Range requests when conditional=True, which is what
    makes scrubbing work without any of the clip machinery.
    """
    path = request.args.get("path", "")
    st = video.convert_state(path)
    if st.get("state") != "ready" or not st.get("out"):
        return jsonify({"ok": False,
                        "error": "That video has not been converted."}), 404
    return send_file(st["out"], mimetype="video/mp4", conditional=True)


@app.route("/api/video/clip")
def api_video_clip():
    path = request.args.get("path", "")
    try:
        t0 = float(request.args.get("t0", 0))
        dur = float(request.args.get("duration", 6))
        offset = float(request.args.get("offset", 0))
        width = int(request.args.get("width", 480))
    except ValueError as exc:
        return jsonify({"ok": False, "error": "Bad clip parameters: %s" % exc}), 400

    ext = os.path.splitext(path)[1].lower()
    # Already browser-playable: stream the file itself so seeking is native.
    if ext in video.NATIVE_EXTS and os.path.isfile(path):
        return send_file(path, conditional=True)
    try:
        out = video.clip(path, t0, dur, offset, width)
    except video.VideoError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("video/clip", exc, 400, {"path": path})
    return send_file(out, mimetype="video/mp4", conditional=True)


@app.route("/api/video/frame")
def api_video_frame():
    path = request.args.get("path", "")
    try:
        blob = video.frame(path, float(request.args.get("t", 0)),
                           float(request.args.get("offset", 0)),
                           int(request.args.get("width", 480)))
    except video.VideoError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("video/frame", exc, 400, {"path": path})
    return Response(blob, mimetype="image/jpeg")


@app.route("/api/video/tracking", methods=["POST"])
def api_video_tracking():
    body = request.get_json(force=True) or {}
    try:
        return jsonify(video.tracking(body.get("path", ""), body.get("t0"),
                                      body.get("t1"),
                                      int(body.get("max_points", 4000))))
    except video.VideoError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("video/tracking", exc, 400, {"path": body.get("path")})


# ==========================================================================
# Filesystem helpers
# ==========================================================================
@app.route("/api/roots")
def api_roots():
    return jsonify({"ok": True, "roots": sysinfo.default_roots(),
                    "repo": REPO_ROOT})


@app.route("/api/browse")
def api_browse():
    path = request.args.get("path") or REPO_ROOT
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return jsonify({"ok": False, "error": "Not a folder: " + path}), 400
    try:
        entries = sorted(os.listdir(path), key=lambda s: s.lower())
    except OSError as exc:
        return jsonify({"ok": False,
                        "error": "Cannot read %s: %s" % (path, exc)}), 400

    dirs, files = [], []
    for e in entries:
        full = os.path.join(path, e)
        try:
            if os.path.isdir(full):
                dirs.append({"name": e, "path": full})
            else:
                files.append({"name": e, "path": full,
                              "size": os.path.getsize(full)})
        except OSError:
            continue

    parent = os.path.dirname(path)
    return jsonify({"ok": True, "path": path,
                    "parent": parent if parent != path else None,
                    "dirs": dirs, "files": files[:500], "n_files": len(files),
                    "is_session": bool(discovery.classify_folder(path, entries))})


@app.route("/api/pick", methods=["POST"])
def api_pick():
    """Native folder/file picker, run in a subprocess so Flask never blocks."""
    body = request.get_json(force=True) or {}
    kind = body.get("kind", "folder")
    start = body.get("start") or REPO_ROOT
    code = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        + ("p = filedialog.askdirectory(initialdir=r'''%s''')\n" % start
           if kind == "folder" else
           "p = filedialog.askopenfilename(initialdir=r'''%s''')\n" % start)
        + "print(p or '')\n"
    )
    try:
        res = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, timeout=600)
        lines = (res.stdout or "").strip().splitlines()
        picked = lines[-1].strip() if lines else ""
    except Exception as exc:
        return fail("pick", exc, 400, {"kind": kind})
    return jsonify({"ok": True, "path": picked})


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    body = request.get_json(force=True) or {}
    try:
        sysinfo.reveal(body.get("path", ""))
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "Path not found."}), 404
    except Exception as exc:
        return fail("reveal", exc, 400)
    return jsonify({"ok": True})


# What this process actually loaded.
#
# Captured at import, so it is the state of the source when this server
# started rather than whatever is on disk now. Anything newer than these is
# a change the running process has not got.
def _source_stamps():
    out = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for name in sorted(os.listdir(here)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(here, name)
        try:
            out[name] = os.path.getmtime(path)
        except OSError:
            continue
    return out


_LOADED_AT = _source_stamps()
_STARTED_AT = time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _code_changed():
    """Source files written since this server started."""
    now = _source_stamps()
    out = []
    for name, when in sorted(now.items()):
        was = _LOADED_AT.get(name)
        # A file that appeared after start counts too: it is code this
        # process has never imported.
        if was is None or when > was + 1.0:
            out.append(name)
    return out


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "repo": REPO_ROOT,
                    "matlab": runner.MATLAB_EXE,
                    "ffmpeg": sysinfo.find_ffmpeg(),
                    "python": sys.executable, "scipy": csc.HAVE_SCIPY,
                    "started_at": _STARTED_AT,
                    "code_changed": _code_changed(),
                    "logs": LOGS_DIR, "system": sysinfo.describe()})


@app.route("/api/cleanup", methods=["POST"])
def api_cleanup():
    return jsonify({"ok": True,
                    "removed": runner.sweep_temp_files(REPO_ROOT),
                    "clips": video.cleanup_clips()})


# ==========================================================================
# Shared state across windows (Link time)
# ==========================================================================
@app.route("/api/probes")
def api_probes():
    """Which physical column each channel sits in, per probe.

    The client needs this to lay out an H10 -- six columns, six panes -- and
    to keep a CSD from running across contacts that are not neighbours.
    """
    return jsonify({"ok": True, "probes": probebook.listing()})


@app.route("/api/link", methods=["GET", "POST"])
def api_link():
    if request.method == "GET":
        # `wait` turns this into a long poll. Held open server-side, so an
        # idle window asks once every 25s instead of twice a second, and a
        # linked window hears about a move immediately.
        held = request.args.get("wait")
        since = request.args.get("since", 0)
        if held:
            return jsonify({"ok": True, **live.wait(since, held)})
        return jsonify({"ok": True, **live.snapshot(since)})
    body = request.get_json(force=True) or {}
    slot = live.publish(body.get("channel", "time"), body.get("value"),
                        body.get("origin"))
    return jsonify({"ok": True, "slot": slot})


# ==========================================================================
# Per-session persisted state -- everything is saved by default
# ==========================================================================
@app.route("/api/session/state", methods=["POST"])
def api_session_state():
    """Remember how a session was last being looked at.

    Filters, colormap, gain, selected channels, panel types. Reopening the
    recording puts you back where you were instead of at defaults.
    """
    body = request.get_json(force=True) or {}
    identity = body.get("identity") or {}
    if identity.get("mouse") is None and not identity.get("key"):
        return jsonify({"ok": True, "saved": False,
                        "reason": "unidentified session"})
    try:
        rec = STORE.upsert_session(identity, {"view_state": body.get("state") or {}})
    except Exception as exc:
        return fail("session/state", exc, 400)
    return jsonify({"ok": True, "saved": True, "session": rec})


@app.route("/api/session/bookmarks", methods=["GET", "POST", "DELETE"])
def api_bookmarks():
    body = request.get_json(silent=True) or {}
    identity = body.get("identity") or {}
    if request.method == "GET":
        rec = _find_session_by_key(request.args.get("key"))
        return jsonify({"ok": True, "bookmarks": (rec or {}).get("bookmarks", [])})
    try:
        if request.method == "DELETE":
            marks = STORE.delete_bookmark(identity, body.get("id"))
            return jsonify({"ok": True, "bookmarks": marks})
        bm = STORE.save_bookmark(identity, body.get("bookmark") or {})
        return jsonify({"ok": True, "bookmark": bm,
                        "bookmarks": STORE.get_bookmarks(identity)})
    except Exception as exc:
        return fail("session/bookmarks", exc, 400)


def _find_session_by_key(key):
    if not key:
        return None
    for s in STORE.all_sessions():
        if s.get("key") == key or s.get("loose_key") == key:
            return s
    return None


# ==========================================================================
# Threshold spike labeling
# ==========================================================================
@app.route("/api/spikes/detect", methods=["POST"])
def api_spikes_detect():
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    try:
        res = analysis.detect_spikes(sess, body)
    except analysis.PanelError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("spikes/detect", exc, 400)
    res["committed"] = False        # a draft until it is explicitly saved
    return jsonify(res)


@app.route("/api/spikes/commit", methods=["POST"])
def api_spikes_commit():
    body = request.get_json(force=True) or {}
    identity = body.get("identity") or {}
    if identity.get("mouse") is None and not identity.get("key"):
        return jsonify({
            "ok": False,
            "error": "This recording has no detectable mouse/session id, so a "
                     "spike set cannot be saved against it."}), 400
    try:
        saved = STORE.save_spike_set(identity, {
            "name": body.get("name") or "threshold set",
            "events": body.get("events") or [],
            "params": body.get("params") or {},
            "t0": body.get("t0"), "t1": body.get("t1"),
            "n": len(body.get("events") or []),
        })
    except Exception as exc:
        return fail("spikes/commit", exc, 400)
    return jsonify({"ok": True, "set": saved,
                    "sets": STORE.get_spike_labels(identity).get("sets", [])})


@app.route("/api/spikes/sets", methods=["POST"])
def api_spike_sets():
    body = request.get_json(force=True) or {}
    return jsonify({"ok": True,
                    "sets": STORE.get_spike_labels(body.get("identity") or {})
                                 .get("sets", [])})


@app.route("/api/spikes/delete", methods=["POST"])
def api_spikes_delete():
    body = request.get_json(force=True) or {}
    try:
        sets = STORE.delete_spike_set(body.get("identity") or {}, body.get("id"))
    except Exception as exc:
        return fail("spikes/delete", exc, 400)
    return jsonify({"ok": True, "sets": sets})


# ==========================================================================
# Activity log
# ==========================================================================
@app.route("/api/activity", methods=["GET", "POST"])
def api_activity():
    """This machine's log, or the whole lab's.

    `scope=everyone` reads the shared copy instead. The log stays push-only
    -- an append-only record of what happened on one machine, which is why
    copying somebody else's into this machine's day file would be writing
    their actions into a file that says it is mine. The combined history is
    a query, and this is it.

    Falls back to the local log if the cloud cannot be reached, and says
    which it gave you: "nobody else did anything" and "I could not find out
    what anybody else did" are different answers.
    """
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        entries = body.get("entries")
        if entries is None:
            entries = body.get("entry") or []
        n = STORE.record_activity(entries)
        return jsonify({"ok": True, "written": n})

    limit = int(request.args.get("limit", 500))
    scope = (request.args.get("scope") or "mine").lower()
    action = request.args.get("action") or None
    session_key = request.args.get("session") or None
    machine = request.args.get("machine") or None

    if scope == "everyone" and CLOUD.cloud.configured:
        bits = ["order=at.desc"]
        if action:
            # A prefix, so "curation" finds curation.enter and curation.bank
            # -- the useful question is about a kind of work, not one verb.
            bits.append("action=like.%s*" % action)
        if session_key:
            bits.append("session_key=eq.%s" % session_key)
        if machine:
            bits.append("machine=eq.%s" % machine)
        try:
            rows = CLOUD.cloud.select("activity", query="&".join(bits),
                                      limit=min(limit, 2000)) or []
            return jsonify({
                "ok": True, "scope": "everyone",
                "activity": [{
                    "id": r.get("id"), "at": r.get("at"),
                    "action": r.get("action"), "detail": r.get("detail"),
                    "view": r.get("view"), "machine": r.get("machine"),
                    "user": r.get("git_user"),
                    "session": {"key": r.get("session_key"),
                                "gid": r.get("gid")},
                } for r in rows],
                "days": STORE.activity_days(),
            })
        except Exception as exc:                         # noqa: BLE001
            # Not fatal, but not silent either: what came back is this
            # machine's own log, and saying so is the difference between
            # "nobody else did anything" and "I could not find out".
            return jsonify({
                "ok": True, "scope": "mine",
                "wanted": "everyone",
                "scope_error": str(exc)[:200],
                "activity": STORE.list_activity(
                    limit=limit, day=request.args.get("day") or None,
                    action=action, session_key=session_key),
                "days": STORE.activity_days(),
            })

    return jsonify({
        "ok": True,
        "scope": "mine",
        "wanted": scope,
        "scope_error": ("no cloud configured"
                        if scope == "everyone" else None),
        "activity": STORE.list_activity(
            limit=limit,
            day=request.args.get("day") or None,
            action=action,
            session_key=session_key),
        "days": STORE.activity_days(),
    })


@app.route("/api/toolfeed/<tool>")
def api_toolfeed(tool):
    """What has happened in one tool, newest first, from the shared table.

    The tool id is the ToolKit's own -- `curate`, `strata`, `cfc`,
    `kilosort`, `snapshots`, `bad` -- and an id with no entry falls back to
    its own name as the action prefix, so a toolkit added next year has a
    feed without anybody registering it.

    Supabase when there is a key and it answers; this machine's own log when
    there is not. Which one it was comes back in `source`, because "nobody
    else is working on this" and "I could not ask" look identical on screen
    and are not the same fact.
    """
    try:
        limit = int(request.args.get("limit") or toolfeed.LIMIT)
    except (TypeError, ValueError):
        limit = toolfeed.LIMIT
    got = toolfeed.feed(STORE, CLOUD.cloud, tool, limit=limit,
                        since=request.args.get("since") or None)
    return jsonify(got)


@app.route("/api/toolfeed")
def api_toolfeed_tools():
    """Which tools have a feed, for anything that wants to list them."""
    return jsonify({"ok": True, "tools": [
        {"id": k, "name": v["name"], "prefixes": v["prefixes"]}
        for k, v in sorted(toolfeed.TOOLS.items())]})


@app.route("/api/activity/who")
def api_activity_who():
    """Who has done what, and where -- the shape of the shared log.

    Two counts per person and per machine rather than a list: the list is
    the view above, and what this answers is "is there anything from the rig
    at all", which a page of rows makes you work out for yourself.
    """
    if not CLOUD.cloud.configured:
        return jsonify({"ok": True, "configured": False,
                        "people": [], "machines": []})
    try:
        rows = CLOUD.cloud.select("activity", query="order=at.desc",
                                  limit=2000) or []
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)[:200]}), 502

    people, machines, actions = {}, {}, {}
    for r in rows:
        # Folded through the roster, like the digest. The log keeps whatever
        # name the machine believed at the time -- deliberately, it is a
        # record of what happened -- so every reader has to fold, or two
        # readers disagree about who exists.
        for bucket, key in ((people, _alias(r.get("git_user") or "unknown")),
                            (machines, r.get("machine") or "unknown")):
            slot = bucket.setdefault(key, {"n": 0, "last": None})
            slot["n"] += 1
            # As a moment, not as text. These rows do not share an
            # offset -- what came from the shared table is UTC and what was
            # written here is local -- so the string test this replaces
            # could hold a row that is not the latest one.
            if not slot["last"] or extras.marked_after(slot["last"],
                                                       r.get("at")):
                slot["last"] = r.get("at")
        # Grouped by the part before the dot: "curation" rather than
        # "curation.enter", because the shape of somebody's week is about
        # kinds of work.
        kind = str(r.get("action") or "").split(".")[0] or "other"
        actions[kind] = actions.get(kind, 0) + 1

    def listed(bucket):
        return sorted(
            [{"name": k, "n": v["n"], "last": v["last"]}
             for k, v in bucket.items()],
            key=lambda x: -x["n"])

    try:
        total = CLOUD.cloud.count("activity")
    except Exception:                                    # noqa: BLE001
        total = None

    # Counted over the whole log, not tallied from a page.
    #
    # This route exists to answer "is there anything from the rig at all",
    # and a page cannot answer it: the thousand newest rows on a machine that
    # has just run a harness suite are all its own, so the tally said one
    # machine where the answer was five. Both sets are small and known -- the
    # machines from the device table, the people from the roster -- so an
    # exact count is a bounded number of requests that fetch no rows.
    def tally(field, names):
        out = []
        for shown, spellings in names:
            got, last = 0, None
            # Case-folded and de-duplicated: "Rain" and an alias "rain" are
            # the same `ilike` and would otherwise be added twice.
            spellings = list({str(x).strip().lower(): str(x).strip()
                              for x in spellings if x}.values())
            for spelling in spellings:
                if not spelling:
                    continue
                try:
                    # `ilike`, not `eq`. Aliases are stored lower-cased and
                    # the log holds the name as it was typed -- "rain
                    # younger" against "Rain Younger" -- so a case-sensitive
                    # match counted nothing and reported the two spellings as
                    # two people, which is the very thing the merge fixed.
                    got += CLOUD.cloud.count(
                        "activity",
                        query="%s=ilike.%s" % (field, _q(spelling)))
                except Exception:                        # noqa: BLE001
                    continue
            if not got:
                continue
            # The last-seen still comes off the sample: it is only wrong when
            # somebody has not been active recently, and then the sample says
            # nothing rather than something false.
            for bucket in (people, machines):
                if shown in bucket:
                    last = bucket[shown].get("last")
                    break
            out.append({"name": shown, "n": got, "last": last})
        return sorted(out, key=lambda x: -x["n"])

    # A person is counted under every spelling the log might hold, because
    # the log keeps what each machine believed at the time -- deliberately --
    # and the roster is what says those are the same person.
    who_names = []
    try:
        got = PEOPLE.roster() or {}
        for row in ((got.get("people") or [])
                    + (got.get("not_people") or [])):
            nm = row.get("name")
            who_names.append((nm, [nm] + list(row.get("aliases") or [])))
    except Exception:                                    # noqa: BLE001
        who_names = [(k, [k]) for k in people]

    # Every source that knows a machine name, unioned. No single one is
    # complete: the `machines` table holds the computers that have registered
    # a heartbeat (three of them here), while the log carries six -- a
    # machine can have written activity and never synced since, or synced
    # under a name it no longer uses. The device picker in Errors already
    # unions these; this route counted from the first one alone and
    # attributed 3,802 of 10,955 rows.
    hosts = set()
    try:
        for d in (CLOUD.cloud.select("machines", limit=200) or []):
            if d.get("hostname"):
                hosts.add(d["hostname"])
    except Exception:                                    # noqa: BLE001
        pass
    hosts.update(k for k in machines if k and k != "unknown")
    try:
        for r in (CLOUD.cloud.select(
                "errors", query="order=at.desc", limit=600) or []):
            if r.get("machine"):
                hosts.add(r["machine"])
    except Exception:                                    # noqa: BLE001
        pass
    host_names = [(h, [h]) for h in sorted(hosts)]

    exact_people = tally("git_user", who_names)
    exact_machines = tally("machine", host_names)

    return jsonify({
        "ok": True, "configured": True,
        "sampled": len(rows),
        "total": total,
        "people": exact_people or listed(people),
        "machines": exact_machines or listed(machines),
        # So the arithmetic can be checked rather than trusted. Anything not
        # attributed is a machine or a name nothing here knows about, which
        # is a fact about the log worth surfacing rather than a rounding
        # error to bury.
        "attributed": {
            "people": sum(x["n"] for x in exact_people),
            "machines": sum(x["n"] for x in exact_machines),
        },
        "unattributed": ({
            "people": max(0, (total or 0)
                          - sum(x["n"] for x in exact_people)),
            "machines": max(0, (total or 0)
                            - sum(x["n"] for x in exact_machines)),
        } if isinstance(total, int) else None),
        # Exact where it matters, and said so. `people` and `machines` are
        # counted over the whole log; the action kinds are not, because there
        # is no bounded list of action names to iterate -- and "the shape of
        # the recent work" is a fair thing to read off recent work.
        "counts_are": "every row" if exact_people else (
            "the most recent %d row(s)" % len(rows)),
        "actions": sorted(
            [{"kind": k, "n": v} for k, v in actions.items()],
            key=lambda x: -x["n"]),
        "actions_are": "the most recent %d row(s)" % len(rows),
        "partial": bool(isinstance(total, int) and total > len(rows)
                        and not exact_people),
    })


# ==========================================================================
# Native Neuralynx event files
# ==========================================================================
@app.route("/api/events/nev", methods=["POST"])
def api_events_nev():
    """Read a .nev, resolving times against the recording's own clock."""
    body = request.get_json(force=True) or {}
    path = body.get("path", "")
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "Not found: " + str(path)}), 404

    t_start = body.get("t_start_us")
    if t_start is None and body.get("session_path"):
        t_start = _recording_start_us(body["session_path"])
    try:
        evs, meta = nlx.nev_events(path, t_start_us=t_start)
    except Exception as exc:
        return fail("events/nev", exc, 400, {"path": path})
    return jsonify({"ok": True, "events": evs, "path": path,
                    "n": meta.get("n", 0),
                    "relative_to": meta.get("relative_to"),
                    "labels": meta.get("labels", [])})


def _recording_start_us(session_path):
    """First CSC timestamp, so .nev times land on the recording's clock."""
    try:
        sess, err = _session_for(session_path)
        if err or not sess or sess.get("source") != "ncs":
            return None
        first = sess["channels"][0].get("file")
        if not first:
            return None
        import numpy as np
        with open(first, "rb") as fh:
            fh.seek(nlx.HEADER_BYTES)
            rec = np.fromfile(fh, dtype=nlx.RECORD_DTYPE, count=1)
        return float(rec["timestamp"][0]) if rec.size else None
    except Exception:
        return None


# ==========================================================================
# Output folder -- where downloads land
# ==========================================================================
# The two lanes a saved file can land in, and the folder the second one uses.
# The folder name comes from results.py rather than being spelled again here:
# the writer, the catalogue and .gitignore all have to agree on it, and a typo
# in any one of them puts harness output back in the gallery silently.
SCRATCH_LANE = "scratch"
SCRATCH_DIR = results.SCRATCH_DIR


def lane_of(body=None):
    """Which lane this request asked to be saved in. Exhibit unless it says.

    Only a harness ever asks for scratch, and it asks explicitly rather than
    being sniffed out of a header: the harness pages drive the real interface
    from inside an iframe, so their requests carry the app's own Referer and
    are indistinguishable from a person's. Saying so in the body is the only
    honest signal there is.
    """
    asked = ((body or {}).get("lane")
             or request.args.get("lane") or "").strip().lower()
    return SCRATCH_LANE if asked == SCRATCH_LANE else "exhibit"


def outputs_dir():
    """Where everything the GUI saves goes, and the only place Results reads.

    Named to match the section rather than the log dock, which is also called
    Output and meant two different things in the same window.
    """
    d = os.path.join(APP_DIR, "Results")
    os.makedirs(d, exist_ok=True)
    return d


@app.route("/api/outputs")
def api_outputs():
    d = outputs_dir()
    items = []
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for name in files:
            full = os.path.join(root, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, d).replace("\\", "/")
            items.append({"name": name, "rel": rel, "path": full,
                          "bytes": st.st_size, "mtime": st.st_mtime,
                          "ext": os.path.splitext(name)[1].lower()})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify({"ok": True, "dir": d, "files": items[:400],
                    "github": github_url_for(d)})


@app.route("/api/outputs/file")
def api_outputs_file():
    """Serve a saved output so it can be previewed in the browser."""
    rel = request.args.get("rel", "")
    d = outputs_dir()
    full = os.path.abspath(os.path.join(d, rel.replace("/", os.sep)))
    if not full.startswith(d) or not os.path.isfile(full):
        return jsonify({"ok": False, "error": "No such output file."}), 404
    return send_file(full, conditional=True)


_GH_CACHE = {}


def github_url_for(path):
    """Best-effort github.com URL for a path inside the repo."""
    if "url" in _GH_CACHE:
        base = _GH_CACHE["url"]
    else:
        base = None
        try:
            res = subprocess.run(["git", "remote", "get-url", "origin"],
                                 cwd=REPO_ROOT, capture_output=True,
                                 text=True, timeout=15)
            remote = (res.stdout or "").strip()
            if res.returncode == 0 and remote:
                if remote.startswith("git@"):
                    remote = remote.replace(":", "/").replace("git@", "https://")
                base = remote[:-4] if remote.endswith(".git") else remote
        except Exception:
            base = None
        _GH_CACHE["url"] = base

    if not base:
        return None
    branch = _GH_CACHE.get("branch")
    if branch is None:
        try:
            res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 cwd=REPO_ROOT, capture_output=True,
                                 text=True, timeout=15)
            branch = (res.stdout or "").strip() or "master"
        except Exception:
            branch = "master"
        _GH_CACHE["branch"] = branch

    try:
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
    except ValueError:
        return None
    if rel.startswith(".."):
        return None
    from urllib.parse import quote
    return "%s/tree/%s/%s" % (base, branch, quote(rel))


def save_output(blob, filename, subdir=None, lane="exhibit"):
    """Write an exported file into the Output folder and report where it went.

    `lane` is which half of Results/ this belongs in, and it is the caller's
    to declare rather than something guessed from the filename later.

      exhibit  a result. Somebody made it on purpose, it is evidence, and it
               is committed so a colleague can see it beside the log entry
               that produced it.
      scratch  a by-product. Harness screenshots, debug reports, the figure
               a test rendered to prove rendering works. Real output of a
               real run, and nobody will ever cite it.

    They were the same folder until now, and the arithmetic of that is why
    this argument exists: of 197 files in Results/, about 120 were harness
    and debug by-products, 23 of them byte-identical copies of one another.
    A folder that is 5% results is not a folder anybody reads.

    Scratch goes to Results/_scratch/, which the catalogue skips and git
    ignores. Underscore rather than a dot so it stays visible -- "send me
    your debug report" is a thing people say, and a hidden folder would make
    that harder, not easier.
    """
    d = outputs_dir()
    if lane == SCRATCH_LANE:
        d = os.path.join(d, SCRATCH_DIR)
        os.makedirs(d, exist_ok=True)
    if subdir:
        safe_sub = "".join(c for c in str(subdir)
                           if c.isalnum() or c in " -_.") .strip()
        if safe_sub:
            d = os.path.join(d, safe_sub)
            os.makedirs(d, exist_ok=True)
    full = os.path.join(d, filename)

    # Never silently clobber an earlier figure.
    stem, ext = os.path.splitext(full)
    n = 2
    while os.path.exists(full):
        full = "%s_%d%s" % (stem, n, ext)
        n += 1

    with open(full, "wb") as fh:
        fh.write(blob)
    return {"path": full,
            "rel": os.path.relpath(full, outputs_dir()).replace("\\", "/"),
            "github": github_url_for(full)}


# ==========================================================================
# Results catalog
# ==========================================================================
RESULTS = results.Results(STORE, outputs_dir(), REPO_ROOT)

# Data roots the user has scanned. Session folders are searched for stage
# output so a MATLAB figure is cataloged even though Jarvis did not make it.
_KNOWN_ROOTS = []


def remember_root(root):
    root = os.path.abspath(root or "")
    if root and os.path.isdir(root) and root not in _KNOWN_ROOTS:
        _KNOWN_ROOTS.insert(0, root)
        del _KNOWN_ROOTS[6:]


@app.route("/api/results")
def api_results():
    refresh = bool(request.args.get("refresh"))
    try:
        items = RESULTS.catalog(refresh=refresh)
    except Exception as exc:
        return fail("results", exc, 400)

    q = (request.args.get("q") or "").strip().lower()
    kind = request.args.get("kind") or ""
    session = request.args.get("session") or ""
    folder = request.args.get("folder") or ""
    if q or kind or session or folder:
        def keep(r):
            if kind and r.get("type") != kind:
                return False
            if session and r.get("session_key") != session:
                return False
            if folder:
                got = RESULTS.clean_folder(r.get("folder"))
                if folder == "~unfiled":
                    if got:
                        return False
                # A folder means the folder and everything under it: asking
                # for "Figure 3" and being shown nothing because it all sits
                # in "Figure 3/Panels" is not an answer.
                elif not (got == folder or got.startswith(folder + "/")):
                    return False
            if not q:
                return True
            hay = " ".join(str(r.get(k) or "") for k in
                           ("title", "name", "session_label", "notes",
                            "author", "kind")).lower()
            hay += " " + " ".join(r.get("tags") or []).lower()
            return q in hay
        items = [r for r in items if keep(r)]

    # Tag and session facets, so the UI can offer real filters.
    tags, sessions = {}, {}
    for r in items:
        for t in (r.get("tags") or []):
            tags[t] = tags.get(t, 0) + 1
        if r.get("session_key"):
            sessions[r["session_key"]] = r.get("session_label") or r["session_key"]

    return jsonify({
        "ok": True,
        "results": items[:800],
        "total": len(items),
        "outputs_dir": outputs_dir(),
        "github": github_url_for(outputs_dir()),
        "tags": sorted(tags.items(), key=lambda kv: -kv[1]),
        "sessions": sorted(sessions.items(), key=lambda kv: kv[1]),
        "roots": _KNOWN_ROOTS,
    })


@app.route("/api/results/file")
def api_results_file():
    """Serve a cataloged result for preview.

    Restricted to files that are actually in the catalog, so this cannot be
    used to read arbitrary paths off the machine.
    """
    # id first, then the portable identifiers. A page still holding ids from
    # a deck built on another machine would otherwise show a grid of broken
    # images, which is what "storyboards do not render across devices"
    # actually looked like.
    rec = RESULTS.resolve({
        "result_id": request.args.get("id", ""),
        "rel": request.args.get("rel"),
        "name": request.args.get("name"),
    })
    if not rec or not os.path.isfile(rec["path"]):
        return jsonify({"ok": False, "error": "No such result."}), 404
    as_attachment = bool(request.args.get("download"))
    return send_file(rec["path"], conditional=True,
                     as_attachment=as_attachment,
                     download_name=rec["name"] if as_attachment else None)


@app.route("/api/results/thumb")
def api_results_thumb():
    """A small picture of a result, for the grid.

    The grid used the original as its own thumbnail: a figure off the builder
    averages a megabyte and a half here, so thirty cards was forty-five
    megabytes to draw thirty postage stamps, each decoded at full size to be
    scaled down. Falls through to the original whenever a thumbnail cannot be
    made, because a slow card beats an empty one.
    """
    rec = RESULTS.resolve({
        "result_id": request.args.get("id", ""),
        "rel": request.args.get("rel"),
        "name": request.args.get("name"),
    })
    if not rec or not os.path.isfile(rec["path"]):
        return jsonify({"ok": False, "error": "No such result."}), 404
    small = None
    if rec.get("type") == "image":
        small = thumbs.thumb_for(rec["path"],
                                 os.path.join(LOGS_DIR, ".cache", "thumbs"))
    # max-age rather than no-store: the name is a hash of the file's size and
    # mtime, so a changed figure is a different URL and this one can be kept.
    resp = send_file(small or rec["path"], conditional=True)
    if small:
        resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@app.route("/api/results/curate", methods=["POST"])
def api_results_curate():
    body = request.get_json(force=True) or {}
    rid = body.get("id")
    rec = RESULTS.get(rid) if rid else None
    path = rec["path"] if rec else body.get("path")
    if not path:
        return jsonify({"ok": False, "error": "Unknown result."}), 404
    try:
        saved = RESULTS.curate(path, body)
    except Exception as exc:
        return fail("results/curate", exc, 400)
    STORE.record_activity([{
        "action": "result.curate",
        "detail": {"id": rid, "title": body.get("title"),
                   "tags": body.get("tags"), "starred": body.get("starred")},
    }])
    return jsonify({"ok": True, "curation": saved})


@app.route("/api/results/reveal", methods=["POST"])
def api_results_reveal():
    body = request.get_json(force=True) or {}
    rec = RESULTS.get(body.get("id", ""))
    if not rec:
        return jsonify({"ok": False, "error": "No such result."}), 404
    try:
        sysinfo.reveal(rec["path"])
    except Exception as exc:
        return fail("results/reveal", exc, 400)
    return jsonify({"ok": True})


# ==========================================================================
# StrataScope -- which anatomical layer each channel is in
# ==========================================================================

@app.route("/api/layers/regions")
def api_layers_regions():
    return jsonify({"ok": True, "regions": layers.REGIONS})


@app.route("/api/layers")
def api_layers_list():
    """Every layer sheet, for the ToolKit list.

    One index for the whole list rather than a lookup per sheet. `by_gid`
    re-checks the shard directory's signature on every call -- a listing
    plus a stat of all 1510 files, about 0.3 s -- so seventy-two sheets
    meant seventy-two of those, and this route took ten seconds to return
    423 KB. Measured: 0.16 s to read the sheets, 14.6 s to look up twenty
    of their recordings.

    Exactly the shape of fix `_attach_index(bulk=True)` is in
    `/api/registry`, and for the same reason: the expensive part is per
    STORE, not per row, so it belongs outside the loop.
    """
    by_gid = {r.get("gid"): r for r in REG.all() if r.get("gid")}
    out = []
    for rec in LAYERS.all():
        row = LAYERS.summary(rec)
        sess = by_gid.get(rec.get("gid"))
        row["session"] = REG.summary(sess) if sess else None
        out.append(row)
    out.sort(key=lambda r: -(r.get("progress", {}).get("labelled") or 0))
    return jsonify({"ok": True, "sheets": out, "regions": layers.REGIONS})


@app.route("/api/layers/<gid>")
def api_layers_get(gid):
    rec = LAYERS.get(gid)
    if not rec:
        return jsonify({"ok": False, "error": "No layer sheet yet."}), 404
    out = LAYERS.summary(rec)
    # With the snapshots, unlike the list: somebody reading one sheet wants
    # to see what a version held, and that is the only place it can come
    # from. The list leaves them out because sixty-odd of them is a lot of
    # bytes for a count.
    out["versions"] = [dict(v) for v in (rec.get("versions") or [])]
    return jsonify({"ok": True, "sheet": out,
                    "session": _session_by_gid(gid)})


@app.route("/api/layers/<gid>/snapshot", methods=["POST"])
def api_layers_snapshot(gid):
    """Freeze the sheet as it stands as the next version.

    The same act as banking a curated set: a pass is finished, and what it
    said should still be readable after somebody starts the next one. Named
    rather than automatic -- a version per keystroke would be a log, and the
    thing worth keeping is the moment somebody decided they were done.
    """
    body = request.get_json(force=True, silent=True) or {}
    try:
        rec = LAYERS.snapshot(gid, note=body.get("note"),
                              by=(PROFILE.effective() or {}).get("user"))
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    STORE.record_activity([{
        "action": "layers.snapshot",
        "detail": {"gid": gid,
                   "v": (rec.get("versions") or [{}])[-1].get("v"),
                   "n": len(rec.get("labels") or {})},
    }])
    out = LAYERS.summary(rec)
    out["versions"] = [dict(v) for v in (rec.get("versions") or [])]
    return jsonify({"ok": True, "sheet": out})


@app.route("/api/layers/<gid>/version-export", methods=["POST"])
def api_layers_version_export(gid):
    """One version of a layer sheet, as CSV.

    Straight out of the snapshot rather than replayed: the same reason the
    event bank exports a version from its snapshot. An export that
    reconstructs the same thing by a different route is one that can
    disagree with the history panel.
    """
    body = request.get_json(force=True, silent=True) or {}
    rec = LAYERS.get(gid)
    if not rec:
        return jsonify({"ok": False, "error": "No layer sheet."}), 404
    want = body.get("v")
    version = None
    for v in (rec.get("versions") or []):
        if want is None or int(v.get("v", -1)) == int(want):
            version = v
            if want is not None:
                break
    if version is None:
        return jsonify({"ok": False,
                        "error": "That sheet has no v%s." % want}), 404

    names = {r["id"]: r["name"]
             for r in (rec.get("regions") or layers.REGIONS)}
    notes = {r["id"]: r.get("note") for r in (rec.get("regions") or layers.REGIONS)}
    snap = version.get("snap") or {}
    sess = _session_by_gid(gid) or {}
    rows = []
    # Every channel the sheet covers, labelled or not: a CSV that silently
    # omits the unlabelled ones cannot be told from one where they were
    # never offered.
    for ch in LAYERS.covered(rec):
        key = str(int(ch))
        region = snap.get(key)
        rows.append({
            "project": sess.get("project"),
            "mouse": sess.get("mouse"),
            "session": sess.get("session"),
            "session_label": rec.get("session_label"),
            "gid": gid,
            "version": version.get("v"),
            "channel": int(ch),
            "region": region or "",
            "region_name": names.get(region, "") if region else "",
            "region_note": notes.get(region, "") if region else "",
            "labelled_by": version.get("by"),
            "version_at": version.get("at"),
            "version_note": version.get("note"),
        })
    text = extras.to_csv(rows)
    name = body.get("name") or ("layers-%s-v%s.csv" % (gid, version.get("v")))
    return Response(
        text, mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="%s"' % name})


@app.route("/api/layers/<gid>/start", methods=["POST"])
def api_layers_start(gid):
    """Open (or make) the sheet for a recording, with its channel order."""
    body = request.get_json(force=True) or {}
    sess = _session_by_gid(gid)
    if not sess:
        return jsonify({"ok": False,
                        "error": "No recording with the id " + gid}), 404
    rec = LAYERS.ensure(gid, session_label=sess.get("label"),
                        channels=body.get("channels"))
    # The channel order can change between visits -- even-only toggled, a file
    # missing -- so it is refreshed rather than trusted from first contact.
    if body.get("channels"):
        rec["channels"] = list(body["channels"])
        LAYERS._write(rec)
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec),
                    "session": REG.summary(sess)})


@app.route("/api/layers/<gid>/set", methods=["POST"])
def api_layers_set(gid):
    body = request.get_json(force=True) or {}
    try:
        if "labels" in body:
            rec = LAYERS.set_many(gid, body["labels"])
        else:
            rec = LAYERS.set(gid, body.get("channel"), body.get("region"))
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("layers/set", exc, 400, {"gid": gid})
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec)})


@app.route("/api/layers/<gid>/fill", methods=["POST"])
def api_layers_fill(gid):
    body = request.get_json(force=True) or {}
    try:
        rec, n = LAYERS.fill_down(gid, body.get("channels"))
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    STORE.record_activity([{"action": "layers.fill",
                            "detail": {"gid": gid, "filled": n}}])
    return jsonify({"ok": True, "filled": n, "sheet": LAYERS.summary(rec)})


@app.route("/api/layers/<gid>/clear", methods=["POST"])
def api_layers_clear(gid):
    try:
        rec = LAYERS.clear(gid)
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec)})


@app.route("/api/layers/<gid>/open", methods=["POST"])
def api_layers_open(gid):
    """Put a sheet on the workbench, or take it off."""
    body = request.get_json(silent=True) or {}
    on = bool(body.get("on", True))
    try:
        rec = LAYERS.open_set(gid, on, who=body.get("who"),
                              unarchive=bool(body.get("unarchive")))
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    STORE.record_activity([{"action": "layers.open",
                            "detail": {"gid": gid, "on": on}}])
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec)})


@app.route("/api/layers/<gid>/archive", methods=["POST"])
def api_layers_archive(gid):
    body = request.get_json(silent=True) or {}
    on = bool(body.get("on", True))
    try:
        rec = LAYERS.archive(gid, on)
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    STORE.record_activity([{"action": "layers.archive",
                            "detail": {"gid": gid, "on": on}}])
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec)})


@app.route("/api/layers/<gid>/assign", methods=["POST"])
def api_layers_assign(gid):
    body = request.get_json(silent=True) or {}
    try:
        rec = LAYERS.assign(gid, body.get("who"))
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    STORE.record_activity([{"action": "layers.assign",
                            "detail": {"gid": gid,
                                       "who": body.get("who")}}])
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec)})


@app.route("/api/layers/<gid>/rename", methods=["POST"])
def api_layers_rename(gid):
    body = request.get_json(silent=True) or {}
    try:
        rec = LAYERS.rename(gid, body.get("name"))
    except layers.LayerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    STORE.record_activity([{"action": "layers.rename",
                            "detail": {"gid": gid,
                                       "name": body.get("name")}}])
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec)})


@app.route("/api/layers/close-all", methods=["POST"])
def api_layers_close_all():
    gone = LAYERS.close_all()
    STORE.record_activity([{"action": "layers.close_all",
                            "detail": {"n": len(gone)}}])
    return jsonify({"ok": True, "closed": gone})


@app.route("/api/layers/<gid>/delete", methods=["POST"])
def api_layers_delete(gid):
    return jsonify({"ok": LAYERS.delete(gid)})


@app.route("/api/layers/<gid>/export")
def api_layers_export(gid):
    rec = LAYERS.get(gid)
    if not rec:
        return jsonify({"ok": False, "error": "No layer sheet yet."}), 404
    rows = LAYERS.rows(rec)
    prog = LAYERS.progress(rec)
    head = ("# Jarvis layer labels -- %s -- %d of %d channels labelled "
            "-- taken %s\n"
            % (rec.get("session_label") or gid, prog["labelled"],
               prog["total"], time.strftime("%Y-%m-%dT%H:%M:%S")))
    text = head + extras.to_csv(rows, list(layers.CSV_COLUMNS))
    name = "layers_%s_%s.csv" % (gid, time.strftime("%Y%m%d_%H%M%S"))
    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="Layers")
    except Exception as exc:
        STORE.record_error("layers/save", str(exc), None, {"name": name})
    resp = Response(text, mimetype="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="%s"' % name,
        "X-Barry-Rows": str(len(rows)),
    })
    if saved:
        resp.headers["X-Barry-Output"] = saved["rel"]
    return resp


# ==========================================================================
# Event curation -- deciding what each candidate actually is
# ==========================================================================

def _cur_session(gid):
    """The registry record a curation set belongs to.

    Demo recordings are deliberately not in the registry, so this went
    through _session_by_gid, which knows about both -- otherwise importing
    candidates onto a built-in recording fails, and that is the first thing
    the Guide asks a newcomer to do.
    """
    rec = _session_by_gid(gid)
    if not rec:
        raise curation.CurationError(
            "No recording with the id %s. Open it once so it is registered."
            % gid)
    return rec


@app.route("/api/curation/kinds")
def api_curation_kinds():
    """The vocabularies on offer, and where their keys are."""
    return jsonify({"ok": True,
                    "kinds": [dict(curation.KINDS[k],
                                   labels=curation.vocabulary(k))
                              for k in curation.KINDS],
                    "reserved": sorted(curation.RESERVED_KEYS)})


def _cur_history(gid, kind, summaries=None):
    """The banked versions of one curation set, newest first.

    What the bench offers when somebody picks a set up: which pass to work
    from. Read off the bank's cached summaries -- the history is the bank's,
    not the curation record's, because banking is what mints a version.

    `snap` is what makes a version restorable, and a version banked on
    another machine arrives here as metadata before its snapshot does. So
    `has_snap` is reported per version: offering to pick up something this
    machine cannot actually read back would fail at the click.
    """
    rows = summaries if summaries is not None else BANK.summaries()
    out = []
    for rec in rows:
        if rec.get("gid") != gid or (rec.get("type") or "") != kind:
            continue
        vers = []
        for ver in (rec.get("versions") or []):
            vers.append({
                "v": ver.get("v"),
                "label": ver.get("label"),
                "at": ver.get("at"),
                "by": ver.get("by"),
                "n": ver.get("n"),
                "note": ver.get("note"),
                "imported": bool(ver.get("imported")),
                "from_v": ver.get("from_v"),
                "has_snap": bool(ver.get("has_snap")),
                "by_label": ver.get("by_label"),
            })
        vers.sort(key=lambda r: -(r["v"] if isinstance(r["v"], int) else -1))
        out.append({
            "entry": rec.get("id"),
            "name": rec.get("name"),
            "n": rec.get("n"),
            "versions": vers,
        })
    # Newest entry first, by its newest version.
    out.sort(key=lambda e: -max([(v["v"] if isinstance(v["v"], int) else -1)
                                 for v in e["versions"]] or [-1]))
    return out


@app.route("/api/curation")
def api_curation_list():
    """Every curation set, with how far through each one is."""
    out = []
    # Read once for the whole list rather than per set: the summaries are
    # cached but the match is a scan, and forty sets against a bank of
    # hundreds is forty scans for one request.
    banked = BANK.summaries()
    # The same rule for the registry, for a reason that is not the same.
    #
    # `REG.by_gid` keeps an index and is not a scan -- but it re-checks the
    # shard directory's signature on every call to know the index is still
    # good, and that check is 77 ms on this archive. Forty-eight sets is
    # forty-eight checks, which measured at 5.2 s of the 4.5 s this request
    # was taking. The freshness check is worth its cost once per request and
    # nothing at all per row: the answer cannot change halfway through
    # building one list.
    by_gid = {r.get("gid"): r for r in REG.all() if r.get("gid")}
    for row in CURATE.summaries():
        rec = by_gid.get(row["gid"])
        row["session"] = REG.summary(rec) if rec else None
        row["history"] = _cur_history(row["gid"], row.get("kind"), banked)
        out.append(row)
    out.sort(key=lambda r: (r.get("progress", {}).get("left", 0) == 0,
                            -(r.get("progress", {}).get("total") or 0)))
    return jsonify({"ok": True, "sets": out,
                    "kinds": [dict(curation.KINDS[k],
                                   labels=curation.vocabulary(k))
                              for k in curation.KINDS]})


@app.route("/api/curation/<gid>/<kind>")
def api_curation_get(gid, kind):
    rec = CURATE.get(gid, kind)
    if not rec:
        return jsonify({"ok": False, "error": "No such curation set."}), 404
    return jsonify({"ok": True, "set": rec,
                    "progress": CURATE.progress(rec),
                    "history": _cur_history(gid, kind),
                    "session": _session_by_gid(gid)})


@app.route("/api/curation/create", methods=["POST"])
def api_curation_create():
    """Import candidates. They all arrive unspecified, on purpose."""
    body = request.get_json(force=True) or {}
    gid = body.get("gid")
    kind = body.get("kind")
    try:
        sess = _cur_session(gid)
        rec, n, extra = CURATE.create(
            gid, kind, body.get("events") or [],
            name=body.get("name"),
            source=body.get("source") or {},
            session_label=sess.get("label"),
            replace=bool(body.get("replace")))
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("curation/create", exc, 400, {"gid": gid, "kind": kind})

    STORE.record_activity([{
        "action": "curation.import",
        "detail": {"gid": gid, "kind": kind, "added": n,
                   "labelled": extra.get("labelled", 0),
                   "disagreed": len(extra.get("disagreed") or []),
                   "total": len(rec.get("events") or []),
                   "source": (body.get("source") or {}).get("from")},
        "session": {"key": sess.get("key"), "label": sess.get("label")},
    }])
    return jsonify({"ok": True, "added": n,
                    "labelled": extra.get("labelled", 0),
                    "disagreed": extra.get("disagreed") or [],
                    "set": CURATE.summary(rec)})


@app.route("/api/curation/from-bank", methods=["POST"])
def api_curation_from_bank():
    """Start a curation set from one version of a banked entry.

    The bank holds the candidates and their history; this reads a version
    out of it. `version` 0 is the detector's list with nothing decided,
    which is the normal way to begin a fresh pass. A later version carries
    the decisions as they stood when it was banked, which is how you carry
    on from somebody else's work or go back to it.

    A recording has one curation set per kind, so this replaces whatever is
    there -- and refuses unless the caller has said so, because the set it
    would replace may be half-finished.
    """
    body = request.get_json(force=True) or {}
    gid = (body.get("gid") or "").strip()
    kind = (body.get("kind") or "").strip()
    entry_id = (body.get("entry") or "").strip()
    if kind not in curation.KINDS:
        return jsonify({"ok": False,
                        "error": "%r is not a kind of curation this Jarvis "
                                 "knows about." % kind}), 400

    ent = BANK.get(entry_id) if entry_id else None
    if not ent:
        return jsonify({"ok": False, "error": "No such bank entry."}), 404
    if gid and ent.get("gid") and ent["gid"] != gid:
        return jsonify({
            "ok": False,
            "error": "That entry was banked against a different recording. "
                     "Its times are seconds from the start of that one, so "
                     "on this one they would land somewhere arbitrary."}), 400
    gid = gid or ent.get("gid")
    if not gid:
        return jsonify({"ok": False,
                        "error": "That entry has no recording id, so there "
                                 "is nothing to attach a set to."}), 400

    sess = _session_by_gid(gid)
    if not sess:
        return jsonify({"ok": False, "error": "No such recording."}), 404

    try:
        want_v = int(body.get("version"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Which version?"}), 400

    versions = ent.get("versions") or []
    ver = next((v for v in versions if v.get("v") == want_v), None)
    if ver is None:
        return jsonify({
            "ok": False,
            "error": "That entry has no version %s. It has %s."
                     % (want_v, ", ".join("v%s" % v.get("v")
                                          for v in versions) or "none")}), 404

    vocab = curation.vocabulary(kind)
    snap = ver.get("snap")
    if snap:
        events = []
        for pair in snap:
            try:
                start = float(pair[0])
            except (TypeError, ValueError, IndexError):
                continue
            item = {"start": start}
            lab = curation.resolve_label(vocab, pair[1] if len(pair) > 1
                                         else None)
            if lab:
                item["label"] = lab
            events.append(item)
    elif want_v == (ent.get("version") or 0):
        # The newest version is whatever the entry currently holds, so it
        # does not need a snapshot of its own.
        events = [{"start": e.get("start"),
                   **({"label": curation.resolve_label(
                        vocab, e.get("label_id") or e.get("label"))}
                      if curation.resolve_label(
                        vocab, e.get("label_id") or e.get("label")) else {})}
                  for e in (ent.get("events") or [])]
    else:
        return jsonify({
            "ok": False,
            "error": "Version %s no longer carries a candidate-by-candidate "
                     "snapshot, so a set cannot be built from it -- only the "
                     "recent versions keep one. Its counts and its note are "
                     "still in the history." % want_v}), 400

    if not events:
        return jsonify({"ok": False,
                        "error": "That version has no usable times in it."}), 400

    existing = CURATE.get(gid, kind)
    if existing and not body.get("replace"):
        prog = CURATE.progress(existing)
        return jsonify({
            "ok": False,
            "exists": {
                "name": existing.get("name"),
                "total": prog["total"], "specified": prog["specified"],
                "left": prog["left"],
                "assignee": existing.get("assignee"),
                "archived": bool(existing.get("archived")),
            },
            "error": "%s already has a %s set -- %d of %d decided. A "
                     "recording has one set per kind, so starting from v%s "
                     "would replace it."
                     % (sess.get("label") or gid,
                        curation.KINDS[kind]["name"].lower(),
                        prog["specified"], prog["total"], want_v)}), 409

    try:
        rec, n, extra = CURATE.create(
            gid, kind, events,
            name=(body.get("name") or "").strip() or ent.get("name"),
            source={"kind": "bank version", "bank_entry": ent["id"],
                    "entry_name": ent.get("name"), "version": want_v,
                    "pipeline": (ent.get("source") or {}).get("pipeline"),
                    "by": ver.get("by")},
            session_label=sess.get("label"),
            replace=True)
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    prog = CURATE.progress(rec)
    STORE.record_activity([{
        "action": "curation.from_bank",
        "detail": {"gid": gid, "kind": kind, "entry": ent["id"],
                   "version": want_v, "n": n,
                   "decided": prog["specified"],
                   "replaced": bool(existing)},
        "session": {"key": sess.get("key"), "label": sess.get("label")},
    }])
    return jsonify({"ok": True, "n": n, "version": want_v,
                    "replaced": bool(existing),
                    "entry": {"id": ent["id"], "name": ent.get("name")},
                    "progress": prog,
                    "set": CURATE.summary(rec)})


@app.route("/api/curation/for-recording/<gid>")
def api_curation_for_recording(gid):
    """What is banked against this recording that a set could start from.

    Every entry with a version history, per kind, with each version's counts
    -- so the picker can say "v0, 373 candidates, none decided" and "v1, the
    folder sort, 283 spikes" and let somebody choose between them.
    """
    out = []
    for rec in BANK.all():
        if rec.get("gid") != gid:
            continue
        kind = (rec.get("type") or "").strip()
        if kind not in curation.KINDS:
            continue
        vs = []
        newest = rec.get("version") or 0
        for v in (rec.get("versions") or []):
            vs.append({
                "v": v.get("v"), "at": v.get("at"), "by": v.get("by"),
                "n": v.get("n"), "note": v.get("note"),
                "by_label": v.get("by_label") or {},
                "imported": bool(v.get("imported")),
                # Whether a set can actually be built from it.
                "usable": bool(v.get("snap")) or v.get("v") == newest,
            })
        vs.sort(key=lambda x: -(x["v"] or 0))
        out.append({
            "id": rec["id"], "name": rec.get("name"), "kind": kind,
            "kind_name": curation.KINDS[kind]["name"],
            "n": rec.get("n"),
            "source": (rec.get("source") or {}).get("pipeline"),
            "label_names": rec.get("label_names") or {},
            "versions": vs,
        })
    out.sort(key=lambda r: (r["kind"], r["name"] or ""))

    have = []
    for kind in curation.KINDS:
        got = CURATE.get(gid, kind)
        if got:
            have.append(CURATE.summary(got))
    return jsonify({"ok": True, "entries": out, "existing": have,
                    "session": _session_by_gid(gid)})


@app.route("/api/curation/<gid>/<kind>/label", methods=["POST"])
def api_curation_label(gid, kind):
    body = request.get_json(force=True) or {}
    try:
        if "labels" in body:
            n, prog = CURATE.label_many(gid, kind, body["labels"])
            return jsonify({"ok": True, "changed": n, "progress": prog})
        ev, prog = CURATE.label(gid, kind, body.get("event"),
                                body.get("label"), body.get("note"))
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("curation/label", exc, 400, {"gid": gid, "kind": kind})
    return jsonify({"ok": True, "event": ev, "progress": prog})


@app.route("/api/curation/<gid>/<kind>/rename", methods=["POST"])
def api_curation_rename(gid, kind):
    body = request.get_json(force=True) or {}
    try:
        rec = CURATE.rename(gid, kind, body.get("name"))
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "set": CURATE.summary(rec)})


@app.route("/api/curation/<gid>/<kind>/open", methods=["POST"])
def api_curation_open(gid, kind):
    """Put a set on the workbench, or take it off.

    Closing costs nothing and requires nothing. Every decision was
    written through the moment it was made, so there is no unsaved state
    to protect and no banking to do first -- banking is publishing a
    result, not saving work.
    """
    body = request.get_json(force=True, silent=True) or {}
    on = body.get("open")
    on = True if on is None else bool(on)
    try:
        rec = CURATE.open_set(gid, kind, on, who=body.get("who"),
                              unarchive=bool(body.get("unarchive")),
                              based_on=body.get("based_on"))
    except curation.CurationError as exc:
        got = CURATE.get(gid, kind)
        # An archived set is not a missing one, and the caller can do
        # something about it -- so say which case this is.
        if got is not None and got.get("archived"):
            return jsonify({"ok": False, "archived": True,
                            "name": got.get("name"),
                            "error": str(exc)}), 409
        return jsonify({"ok": False, "error": str(exc)}), 404
    STORE.record_activity([{
        "action": "curation.open" if on else "curation.close",
        "detail": {"gid": gid, "kind": kind,
                   "assignee": rec.get("assignee"),
                   "left": CURATE.progress(rec).get("left")},
    }])
    return jsonify({"ok": True, "set": CURATE.summary(rec)})


@app.route("/api/presence", methods=["GET"])
def api_presence():
    """Everyone currently in a curation set.

    A GET with no side effects, because the workbench polls this and a poll
    that writes cannot be made frequent. `active` and `age_s` are worked out
    on the server so that the workbench and the curation bar cannot disagree
    about who counts as present.
    """
    PRESENCE.sweep()
    rows = PRESENCE.all()
    return jsonify({
        "ok": True,
        "machine": PRESENCE.machine(),
        "ttl_s": presencemod.TTL_S,
        "configured": bool(CLOUD.cloud.configured),
        "sessions": rows,
    })


@app.route("/api/presence/beat", methods=["POST"])
def api_presence_beat():
    """This machine is in this set, and here is how far it has got.

    Answers with whoever else is in it, so one request does the whole job:
    the client needs to know it was heard AND whether somebody has appeared
    beside it, and asking twice would double the traffic of the thing that
    has to be frequent.
    """
    body = request.get_json(force=True, silent=True) or {}
    gid, kind = body.get("gid"), body.get("kind")
    if not gid:
        return jsonify({"ok": False, "error": "Need a gid."}), 400
    PRESENCE.beat(
        gid, kind,
        first=bool(body.get("first")),
        doing=body.get("doing"),
        n_total=body.get("n_total"), n_decided=body.get("n_decided"),
        n_this_visit=body.get("n_this_visit"),
        at_index=body.get("at_index"), at_time_s=body.get("at_time_s"))
    return jsonify({
        "ok": True,
        # Whoever else is in this set -- the reason to answer at all.
        "others": [r for r in PRESENCE.for_set(gid, kind, include_self=False)
                   if r.get("active")],
        # And whether this machine has had the set taken off it, which it
        # cannot find out any other way: the taking happens elsewhere.
        "taken": PRESENCE.taken_from_me(gid, kind),
    })


@app.route("/api/presence/release", methods=["POST"])
def api_presence_release():
    """Leaving a set. The TTL would do this anyway; this does it now."""
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("gid"):
        return jsonify({"ok": False, "error": "Need a gid."}), 400
    return jsonify({"ok": PRESENCE.release(body["gid"], body.get("kind"))})


@app.route("/api/presence/take", methods=["POST"])
def api_presence_take():
    """Take a set another session is in.

    Deliberate, never automatic. The other session is marked rather than
    deleted so it finds out on its next beat and can say so on screen --
    otherwise it would carry on writing decisions into a set it no longer
    holds, which is the silent version of the collision this exists to
    prevent.
    """
    body = request.get_json(force=True, silent=True) or {}
    gid, kind = body.get("gid"), body.get("kind")
    from_machine = body.get("machine")
    if not gid or not from_machine:
        return jsonify({"ok": False,
                        "error": "Need a gid and whose session to take."}), 400
    ok = PRESENCE.take(gid, kind, from_machine)
    STORE.record_activity([{
        "action": "curation.take",
        "detail": {"gid": gid, "kind": kind, "from": from_machine},
    }])
    return jsonify({"ok": bool(ok)})


# The prefix a harness row must carry. Nothing else can be written or
# deleted through the two routes below -- a route that can write an arbitrary
# presence row could tell the lab that somebody is curating a set they have
# never opened.
_TEST_GID = "harness-"


@app.route("/api/presence/_test_ghost", methods=["POST"])
def api_presence_test_ghost():
    """Write a presence row as though another machine had beaten.

    For web/_dev/presence.html. Half of what presence does is about a second
    machine, and one browser does not have one -- but a row written here is
    byte-for-byte what a colleague's heartbeat leaves, so every reader is
    exercised for real rather than against a stub.
    """
    body = request.get_json(force=True, silent=True) or {}
    gid = body.get("gid") or ""
    if not gid.startswith(_TEST_GID):
        return jsonify({"ok": False,
                        "error": "Test rows only, and only under "
                                 + _TEST_GID}), 400
    row = {
        "gid": gid, "kind": body.get("kind") or "ds",
        "machine": body.get("machine") or "harness-ghost",
        "person": body.get("person"), "device": body.get("device"),
        "last_seen": cloudmod.now(), "started_at": cloudmod.now(),
        "doing": body.get("doing") or "curating",
    }
    for k in ("n_total", "n_decided", "n_this_visit", "at_index", "at_time_s"):
        if body.get(k) is not None:
            row[k] = body[k]
    try:
        CLOUD.cloud.upsert(presencemod.TABLE, [row],
                           on_conflict="gid,kind,machine")
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)[:200]}), 502
    return jsonify({"ok": True, "row": row})


@app.route("/api/presence/_test_clear", methods=["POST"])
def api_presence_test_clear():
    """Remove every row for a harness set, so a test leaves nothing behind.

    A harness that left "Somebody is curating m33 s8" in the table would be
    lying to whoever opens the workbench next, which is a worse failure than
    anything it was testing.
    """
    body = request.get_json(force=True, silent=True) or {}
    gid = body.get("gid") or ""
    if not gid.startswith(_TEST_GID):
        return jsonify({"ok": False,
                        "error": "Test rows only, and only under "
                                 + _TEST_GID}), 400
    try:
        CLOUD.cloud.delete(presencemod.TABLE, "gid=eq.%s" % gid)
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)[:200]}), 502
    return jsonify({"ok": True})


@app.route("/api/curation/<gid>/<kind>/assign", methods=["POST"])
def api_curation_assign(gid, kind):
    """Say whose set this is."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        rec = CURATE.assign(gid, kind, body.get("who"))
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    STORE.record_activity([{
        "action": "curation.assign",
        "detail": {"gid": gid, "kind": kind,
                   "assignee": rec.get("assignee")},
    }])
    return jsonify({"ok": True, "set": CURATE.summary(rec)})


@app.route("/api/notes")
def api_notes():
    """The version and what changed in it.

    Read from CHANGELOG.md on every request, but only re-parsed when the
    file has actually changed -- so editing the notes shows up without a
    restart, which is the whole point of them living in a file.
    """
    return jsonify(NOTES.read())


@app.route("/api/people")
def api_people():
    """Everyone who has worked on this repo, most likely first.

    Gathered from the profiles, the curation decisions and the bank
    rather than from a list somebody has to keep up to date.
    """
    return jsonify({"ok": True, **PEOPLE.roster(CURATE, BANK)})


@app.route("/api/people/add", methods=["POST"])
def api_people_add():
    """Put somebody on the roster, or edit what it says about them.

    `aliases` is accepted because it is how a merge is expressed: the
    records keep the name each machine stamped on them -- deliberately,
    provenance is not editable -- and an alias on the surviving entry is
    what folds them at read time. Without it here there was no way to
    merge two names except by editing a shard by hand.
    """
    body = request.get_json(force=True, silent=True) or {}
    extra = {}
    if "aliases" in body:
        got = body.get("aliases")
        if isinstance(got, (list, tuple)):
            # Lower-cased, because the fold is case-insensitive and storing
            # both "Rain" and "rain" as aliases of the same person is two
            # entries for one statement.
            extra["aliases"] = sorted({str(a).strip().lower()
                                       for a in got if str(a).strip()})
        elif got in (None, ""):
            extra["aliases"] = []
    if "archived" in body:
        extra["archived"] = bool(body.get("archived"))
    try:
        PEOPLE.add(body.get("name"), body.get("email"), body.get("note"),
                   role=body.get("role"), initials=body.get("initials"),
                   orcid=body.get("orcid"), **extra)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **PEOPLE.roster(CURATE, BANK)})


@app.route("/api/people/<name>")
def api_people_one(name):
    """What the roster holds about one person, for the editor."""
    return jsonify({"ok": True, "person": PEOPLE.details(name)})


@app.route("/api/people/forget", methods=["POST"])
def api_people_forget():
    """Take a hand-added name off. A name the data carries stays:
    it is on the records whether the roster lists it or not."""
    body = request.get_json(force=True, silent=True) or {}
    gone = PEOPLE.forget(body.get("name"))
    return jsonify({"ok": True, "removed": bool(gone),
                    **PEOPLE.roster(CURATE, BANK)})


# Names a harness may create and destroy. Anything else is somebody's
# colleague, and this route will not touch it.
_TEST_PERSON = "zz "


@app.route("/api/device")
def api_device():
    """What this computer is called, and how firmly.

    Separate from the profile on purpose. Switching who this machine credits
    work to must not be able to rename the machine, and when the two shared
    a record it could -- measured: one computer filed errors under five
    different names while two computers were both set to the same one.
    """
    got = DEVICE.get(PROFILE)
    got["adopted_from_profile"] = _adopted
    return jsonify({"ok": True, "device": got})


@app.route("/api/device", methods=["POST"])
def api_device_save():
    """Name this computer. Empty puts it back to the hostname.

    Nothing about a person is touched here, and nothing here travels with a
    profile: the record is a shard belonging to this machine.
    """
    body = request.get_json(force=True, silent=True) or {}
    got = DEVICE.save(body.get("name"))
    STORE.record_activity([{
        "action": "device.rename",
        "detail": {"name": got.get("name"), "id": got.get("id")},
    }])
    return jsonify({"ok": True, "device": got})


@app.route("/api/people/_test_purge", methods=["POST"])
def api_people_test_purge():
    """Remove a harness's probe people, here and in the shared roster.

    A harness that creates a person has to be able to un-create one, and
    removing it locally is not enough: a push during the run sends it up and
    the next pull writes it back. That happened twice while building this,
    and both times a name had to be deleted out of the shared table by hand.

    Guarded on the prefix rather than trusted: a purge that could take any
    name is a route that can quietly delete a colleague.
    """
    body = request.get_json(force=True, silent=True) or {}
    names = [str(n) for n in (body.get("names") or []) if n]
    refused = [n for n in names if not n.lower().startswith(_TEST_PERSON)]
    if refused:
        return jsonify({
            "ok": False,
            "error": "This only removes probe names beginning %r. Refused: %s"
                     % (_TEST_PERSON, ", ".join(refused)),
        }), 400

    gone, cloud_gone = [], []
    for name in names:
        try:
            if PEOPLE.forget(name):
                gone.append(name)
        except Exception:                                # noqa: BLE001
            pass
        if CLOUD.cloud.configured:
            try:
                CLOUD.cloud.delete("people", "name=eq.%s" % _q(name))
                cloud_gone.append(name)
            except Exception:                            # noqa: BLE001
                pass
    return jsonify({"ok": True, "removed": gone, "removed_shared": cloud_gone})


@app.route("/api/people/retired")
def api_people_retired():
    """Names that have been merged away or removed from the roster.

    Worth exposing because the logs keep them: the activity and error logs
    record whatever name each machine believed at the time, on purpose, so a
    merged-away colleague still appears in them. A reader -- or a check --
    needs to be able to tell "a name that used to be somebody" from "a name
    nothing has ever heard of".
    """
    try:
        names = sorted(PEOPLE.retired())
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)[:200]}), 500
    return jsonify({"ok": True, "names": names})


@app.route("/api/people/archive", methods=["POST"])
def api_people_archive():
    """Take somebody off the pickers, or put them back.

    Not removal, and unlike removal it works on a name the data carries --
    which is the case it exists for. Nothing is deleted, no count changes,
    and their name stays on every record it is already on.
    """
    body = request.get_json(force=True, silent=True) or {}
    want = body.get("archived", True)
    try:
        PEOPLE.archive(body.get("name"), bool(want))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    STORE.record_activity([{
        "action": "profile.archive",
        "detail": {"name": body.get("name"), "archived": bool(want)},
    }])
    return jsonify({"ok": True, "archived": bool(want),
                    **PEOPLE.roster(CURATE, BANK)})


# ==========================================================================
# What a sitting actually was
# ==========================================================================
def _sitting_of(rec, who=None, gap_s=1800):
    """Group one set's decisions into sittings, and describe the last.

    A "sitting" is decisions with no gap longer than half an hour. Somebody
    who curates for forty minutes, goes to lunch and comes back has done two
    of them, and averaging across the lunch would report a rate nobody
    achieved.

    A decision that shares its timestamp with others was not individually
    timed -- it came from a fill-down, or from a snapshot import that stamped
    the whole set at once. Those are counted separately and kept out of the
    pace, because the alternative is arithmetic: 738 decisions across 100
    timestamps really does divide out at seven a second, and nobody has ever
    curated at seven a second.

    Nothing here is measured, only grouped. Every decision already carries
    its author and its time.
    """
    rows = []
    for ev in (rec.get("events") or []):
        at = presencemod._parse(ev.get("at"))
        if not at or not ev.get("label"):
            continue
        if who and str(ev.get("by") or "") != who:
            continue
        rows.append((at, ev.get("label"), ev.get("by"), ev.get("at")))
    rows.sort(key=lambda r: r[0])
    if not rows:
        return None

    # How many decisions share each raw stamp. A stamp held by one decision
    # is a moment somebody pressed a key; a stamp held by fourteen is one
    # operation that touched fourteen candidates.
    crowd = {}
    for r in rows:
        crowd[r[3]] = crowd.get(r[3], 0) + 1

    sittings, cur = [], [rows[0]]
    for prev, row in zip(rows, rows[1:]):
        if (row[0] - prev[0]).total_seconds() > gap_s:
            sittings.append(cur)
            cur = [row]
        else:
            cur.append(row)
    sittings.append(cur)

    last = sittings[-1]
    by_label = {}
    for row in last:
        by_label[row[1]] = by_label.get(row[1], 0) + 1
    people = sorted({r[2] for r in last if r[2]})

    # Only the individually-stamped ones can say anything about pace.
    paced = [r for r in last if crowd.get(r[3], 0) == 1]
    bulk = len(last) - len(paced)
    biggest = max([crowd.get(r[3], 0) for r in last] or [0])

    span = (last[-1][0] - last[0][0]).total_seconds()
    paced_span = ((paced[-1][0] - paced[0][0]).total_seconds()
                  if len(paced) > 1 else 0.0)
    # Ten decisions and half a minute before a rate is worth quoting. Two
    # decisions a second apart divide out at thirty a minute, which is a
    # number rather than a fact.
    per_min = ((len(paced) / (paced_span / 60.0))
               if (len(paced) >= 10 and paced_span > 30) else None)

    return {
        "n": len(last),
        "seconds": span,
        # What the pace was actually computed from, so the card can say so.
        "paced": len(paced),
        "paced_seconds": paced_span,
        "bulk": bulk,
        "bulk_biggest": biggest if bulk else 0,
        "per_min": per_min,
        "started": last[0][0].isoformat(),
        "ended": last[-1][0].isoformat(),
        "by_label": by_label,
        "who": [_alias(p) for p in people],
        "sittings": len(sittings),
        "total_decided": len(rows),
    }


@app.route("/api/curation/<gid>/<kind>/receipt")
def api_curation_receipt(gid, kind):
    """What the last sitting on this set came to.

    Worth having for two unrelated reasons: it is pleasant to see what an
    afternoon added up to, and it is the only place the pace of curation is
    visible -- which matters, because a set decided at forty a minute and a
    set decided at four are not the same evidence.
    """
    rec = CURATE.get(gid, kind)
    if not rec:
        return jsonify({"ok": False, "error": "No such set."}), 404
    pr = CURATE.progress(rec)
    sitting = _sitting_of(rec, who=request.args.get("who") or None)
    return jsonify({
        "ok": True,
        "gid": gid, "kind": kind,
        "name": rec.get("name"),
        "session": rec.get("session_label") or rec.get("name"),
        "progress": pr,
        "labels": rec.get("labels") or [],
        "sitting": sitting,
    })


# ==========================================================================
# The hall of garbage
# ==========================================================================
# How quickly a decision has to be made to count as an easy one. Anything
# under a couple of seconds was not deliberated over -- the candidate was
# obvious on sight, which is exactly what makes it worth showing a newcomer.
QUICK_S = 2.5


@app.route("/api/curation/garbage-hall")
def api_garbage_hall():
    """The most obviously-rejected candidates in the whole store.

    "Confidently" is defined as: rejected, decided quickly, never flagged,
    and never revisited. That is measurable from what is already recorded --
    each decision carries its author, its time, and its review trail -- and
    it picks out the candidates nobody had to think about.

    Which makes it a teaching set. The fastest way to explain what garbage
    looks like is forty examples that nobody hesitated over.
    """
    want = int(request.args.get("limit", 40))
    rows = []
    bulk = 0        # decisions whose timing cannot mean anything
    for st in CURATE.all():
        gid, kind = st.get("gid"), st.get("kind")
        rec = CURATE.get(gid, kind)
        if not rec:
            continue

        # Which timestamps were written in bulk rather than as somebody
        # worked.
        #
        # 8,831 decisions were stamped by a backfill after the fact, all
        # sharing one `at` -- so the gap between them is zero and says
        # nothing about how long anybody took. Counting those as "decided
        # instantly" would fill this list with the least considered
        # candidates in the store and present them as the most obvious.
        #
        # A timestamp shared by more than a handful of decisions did not
        # come from a person making them one at a time.
        stamps = {}
        for ev in (rec.get("events") or []):
            if ev.get("label") and ev.get("at"):
                stamps[ev["at"]] = stamps.get(ev["at"], 0) + 1
        crowded = {at for at, n in stamps.items() if n > 3}
        bulk += sum(n for at, n in stamps.items() if at in crowded)
        # Which of this set's labels mean "not an event". A set carries its
        # own vocabulary, so this cannot be hard-coded to "garbage".
        reject = {l.get("id") for l in (rec.get("labels") or [])
                  if l.get("id") in ("garbage",) or l.get("rejects")}
        if not reject:
            continue
        evs = rec.get("events") or []
        prev = None
        for ev in evs:
            at = presencemod._parse(ev.get("at"))
            if ev.get("label") not in reject or not at:
                prev = at
                continue
            # Revisited, or flagged on the way: somebody hesitated, so it is
            # not an example of the obvious.
            if len(ev.get("reviews") or []) > 1:
                prev = at
                continue
            took = (at - prev).total_seconds() if prev else None
            prev = at
            if ev.get("at") in crowded:
                continue
            if took is None or took > QUICK_S or took <= 0:
                continue
            rows.append({
                "gid": gid, "kind": kind,
                "session": rec.get("session_label") or rec.get("name"),
                "id": ev.get("id"),
                "start": ev.get("start"),
                "label": ev.get("label"),
                "by": _alias(ev.get("by")),
                "at": ev.get("at"),
                "took_s": round(took, 2),
            })
    rows.sort(key=lambda r: r["took_s"])
    return jsonify({
        "ok": True, "quick_s": QUICK_S,
        "n": len(rows), "hall": rows[:want],
        # Said out loud, because a short hall and an empty one have very
        # different causes and only one of them is about the curation.
        "unusable": bulk,
        # Deliberately not leading with the number: whoever shows this
        # states the count itself, and a sentence that repeats it reads as
        # two different figures.
        "why": ("They were stamped in bulk rather than one at a time, so how "
                "long anybody took over them is not recorded and they cannot "
                "qualify.") if bulk else None,
    })


# ==========================================================================
# Groundwork for ordering candidates by how hard they look
#
# NOT a classifier. This is the dataset it would need, exported in a form
# something else can train on, plus the slot a score would be written back
# into.
#
# Deliberately stopping there. The moment a model exists somebody will be
# tempted to let it decide, and the entire value of this system is that a
# person did -- every decision in here has a name and a time against it. The
# useful thing a model can do is change the ORDER: put the obvious garbage
# last so the hard cases get looked at while people are still fresh.
# ==========================================================================
@app.route("/api/curation/dataset")
def api_curation_dataset():
    """Every human decision, as rows something else can learn from.

    One row per decided candidate: which recording, when in it, what it was
    called, by whom, how long they took, and whether anybody revisited it.
    The last two are the interesting columns -- they are a rough measure of
    how hard the call was, which is the thing worth predicting.
    """
    rows = []
    for st in CURATE.all():
        gid, kind = st.get("gid"), st.get("kind")
        rec = CURATE.get(gid, kind)
        if not rec:
            continue
        prev = None
        for ev in (rec.get("events") or []):
            at = presencemod._parse(ev.get("at"))
            if not ev.get("label"):
                prev = at or prev
                continue
            took = ((at - prev).total_seconds()
                    if (at and prev) else None)
            prev = at or prev
            rows.append({
                "gid": gid, "kind": kind,
                "session": rec.get("session_label"),
                "event_id": ev.get("id"),
                "start_s": ev.get("start"),
                "label": ev.get("label"),
                "decided_by": _alias(ev.get("by")),
                "decided_at": ev.get("at"),
                # How long the person took, and how many times the label
                # changed. Hesitation is the signal; the label is the target.
                "took_s": round(took, 3) if took and 0 < took < 600 else None,
                "revisions": max(0, len(ev.get("reviews") or []) - 1),
            })
    fmt = (request.args.get("format") or "json").lower()
    if fmt == "csv":
        return Response(
            extras.to_csv(rows), mimetype="text/csv",
            headers={"Content-Disposition":
                     'attachment; filename="curation-dataset.csv"'})
    return jsonify({"ok": True, "n": len(rows),
                    "rows": rows[:int(request.args.get("limit", 500))]})


@app.route("/api/curation/<gid>/<kind>/order", methods=["POST"])
def api_curation_order(gid, kind):
    """Set the order candidates are visited in.

    The slot a model would write into, and usable without one: `hardest`
    puts the candidates somebody hesitated over first, which is worth having
    on its own for a review pass.

    Stored on the set rather than applied to it. Re-ordering the events
    themselves would change what `index` means in every other window, in
    every saved view, and in the aid window -- and the order somebody wants
    to work in is a preference, not a property of the data.
    """
    body = request.get_json(force=True, silent=True) or {}
    how = (body.get("order") or "time").strip()
    if how not in ("time", "hardest", "scored"):
        return jsonify({"ok": False,
                        "error": "Order must be time, hardest or scored."}), 400
    scores = body.get("scores") or None
    try:
        rec = CURATE.set_order(gid, kind, how, scores=scores)
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    STORE.record_activity([{
        "action": "curation.order",
        "detail": {"gid": gid, "kind": kind, "order": how,
                   "scored": len(scores or {})},
    }])
    return jsonify({"ok": True, "set": CURATE.summary(rec)})


@app.route("/api/curation/close-all", methods=["POST"])
def api_curation_close_all():
    """Clear the workbench. Nothing is archived, deleted or unbanked."""
    body = request.get_json(force=True, silent=True) or {}
    closed = CURATE.close_all(kind=body.get("kind"))
    if closed:
        STORE.record_activity([{
            "action": "curation.close_all",
            "detail": {"sets": len(closed)},
        }])
    return jsonify({"ok": True, "closed": closed, "n": len(closed)})


@app.route("/api/curation/<gid>/<kind>/archive", methods=["POST"])
def api_curation_archive(gid, kind):
    """Put a curation session out of the way, or bring it back."""
    body = request.get_json(force=True, silent=True) or {}
    on = body.get("archived")
    on = True if on is None else bool(on)
    try:
        rec = CURATE.archive(gid, kind, on)
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    STORE.record_activity([{
        "action": "curation.archive" if on else "curation.unarchive",
        "detail": {"gid": gid, "kind": kind},
    }])
    return jsonify({"ok": True, "set": CURATE.summary(rec)})


@app.route("/api/curation/<gid>/<kind>/delete", methods=["POST"])
def api_curation_delete(gid, kind):
    ok = CURATE.delete(gid, kind)
    STORE.record_activity([{"action": "curation.delete",
                            "detail": {"gid": gid, "kind": kind}}])
    return jsonify({"ok": ok})


@app.route("/api/curation/<gid>/<kind>/bank", methods=["POST"])
def api_curation_bank(gid, kind):
    """Send the curated events to the Event Bank, as one versioned entry.

    One entry for the whole set, not one per category -- see the paragraph
    below on `prior`. It used to be one per category; those get folded into
    this one and removed, because every event in them came from this set and
    is being written again right now.
    """
    body = request.get_json(force=True) or {}
    rec = CURATE.get(gid, kind)
    if not rec:
        return jsonify({"ok": False, "error": "No such curation set."}), 404
    sess = _session_by_gid(gid)
    if not sess:
        return jsonify({"ok": False, "error": "No such recording."}), 404

    bundle = CURATE.bank_one(rec, only_specified=not body.get("include_left"))
    if not bundle["n"]:
        return jsonify({"ok": False,
                        "error": "Nothing has been curated yet, so there is "
                                 "nothing to bank."}), 400

    # One entry for the whole set. `prior` is everything this set has ever
    # banked -- including the per-category entries it used to be split into,
    # which get folded into this one and then removed, because every event
    # in them came from this set and is being written again right now.
    prior = BANK.curated_entries(gid, kind)
    whole = [p for p in prior if p.get("curation_label") == "*"]
    keep = whole[0]["id"] if whole else None
    # Nothing curated here yet: continue the detector's export these
    # candidates came from, rather than filing a second record of the same
    # four hundred times.
    # The detector's export these candidates came from, whether or not
    # anything has been curated yet. If nothing has, the curated result
    # continues that entry in place -- same id, same link. If something has,
    # the import is folded into its history as version zero and the second
    # record of the same four hundred times goes away.
    adopt = BANK.source_entry_for(gid, kind, bundle["events"])
    if not keep and adopt:
        keep = adopt["id"]
    removed = []
    try:
        entry = BANK.add({
            "id": keep,
            "project": sess.get("project") or sess.get("group"),
            "mouse": sess.get("mouse"),
            "session": sess.get("session"),
            "session_key": sess.get("key"),
            "session_loose_key": sess.get("loose_key"),
            "session_label": sess.get("label"),
            "recording_start": sess.get("start"),
            "name": rec.get("name"),
            "type": kind,
            "events": bundle["events"],
            "by_label": bundle["by_label"],
            "label_names": bundle["label_names"],
            "pipeline": (body.get("pipeline")
                         or "Jarvis curation (" + kind + ")"),
            "added_by": body.get("added_by"),
            "version_note": body.get("note"),
            # Where this pass belongs in the history. The caller may say;
            # otherwise it is whatever the set was picked up from, and
            # failing that whatever was newest.
            "based_on": (body.get("based_on")
                         if body.get("based_on") is not None
                         else rec.get("based_on")),
            # What the bank needs to tell a guess from a decision.
            "curated": True,
            "import_from": adopt,
            # "*" means the whole set rather than one of its categories.
            "curation_label": "*",
            "gid": gid,
        })
    except eventbank.BankError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    made = [{"id": entry["id"], "n": bundle["n"],
             "by_label": bundle["by_label"],
             "label_names": bundle["label_names"],
             "version": entry.get("version"),
             "new_version": bool(entry.get("new_version")),
             "adopted": (adopt or {}).get("name") if adopt else None,
             "replaced": bool(entry.get("replaced"))}]

    for old_entry in prior:
        if old_entry["id"] == entry["id"]:
            continue
        if old_entry.get("curation_label") == "*":
            continue
        if BANK.delete(old_entry["id"]):
            removed.append({"id": old_entry["id"],
                            "name": old_entry.get("name"),
                            "n": old_entry.get("n"),
                            "why": "folded into one entry for the set"})

    # The import, now that it is version zero of this entry's history. Its
    # times and its provenance are both carried over, so nothing is lost by
    # it no longer being a record of its own.
    #
    # Unless version zero could not hold them. A curated bundle carries
    # only the decided candidates, so folding the import in is a deletion
    # of every candidate nobody has reached yet -- recoverable from v0's
    # snapshot, and only from there. If the import was too big for one,
    # the second record of those times is the only copy left and it stays.
    if adopt and adopt["id"] != entry["id"]:
        v0 = next((v for v in (entry.get("versions") or [])
                   if v.get("imported")), None)
        safe = bool(v0 and v0.get("snap"))
        if not safe:
            kept_import = {
                "id": adopt["id"], "name": adopt.get("name"),
                "n": adopt.get("n"),
                "why": "kept: too many candidates to snapshot into "
                       "version 0, so this is still the only record of "
                       "the times the detector found",
            }
            made[0]["kept_import"] = kept_import
        elif BANK.delete(adopt["id"]):
            removed.append({"id": adopt["id"], "name": adopt.get("name"),
                            "n": adopt.get("n"),
                            "why": "now version 0 of this entry"})

    STORE.record_activity([{
        "action": "curation.bank",
        "detail": {"gid": gid, "kind": kind,
                   "entry": entry["id"],
                   "version": entry.get("version"),
                   "note": (body.get("note") or "")[:200],
                   "by_label": bundle["by_label"],
                   "folded": len(removed),
                   "n": bundle["n"]},
        "session": {"key": sess.get("key"), "label": sess.get("label")},
    }])
    mirror_bank_soon()

    return jsonify({"ok": True, "entries": made, "removed": removed})


def _slug_for_file(text):
    """Something safe to put in a download's filename."""
    keep = [c if (c.isalnum() or c in "-_") else "-"
            for c in str(text or "").strip()]
    out = "".join(keep).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return (out[:48] or "barry").lower()


@app.route("/api/curation/<gid>/<kind>/banked")
def api_curation_banked(gid, kind):
    """What this set has already been banked as.

    Read before banking so the dialog can show what it is adding to -- a
    version note written without seeing the previous ones tends to say
    "update". Events are left out: this is the history, not the payload.
    """
    found = BANK.curated_entries(gid, kind)
    whole = [e for e in found if e.get("curation_label") == "*"]
    ent = whole[0] if whole else None

    # The detector import this set will be written onto, if it has not been
    # banked under its own name yet. `curated_entries` only knows about
    # entries this set has already written, and an import has no
    # `curation_label` -- so a set whose history is v0 (the detector) plus v1
    # (a sort done before Jarvis) looked untouched here, and the dialog
    # offered to write "version 1" while the route was about to write v2.
    # Asked the same way the bank route asks, so the two cannot disagree.
    if ent is None:
        rec = CURATE.get(gid, kind)
        if rec:
            bundle = CURATE.bank_one(rec, only_specified=True)
            if bundle["n"]:
                ent = BANK.source_entry_for(gid, kind, bundle["events"])
    if ent is None:
        return jsonify({"ok": True, "entry": None,
                        "split": [{"id": e["id"], "name": e.get("name"),
                                   "n": e.get("n"),
                                   "label": e.get("curation_label")}
                                  for e in found]})
    return jsonify({
        "ok": True,
        "entry": {
            "id": ent["id"], "name": ent.get("name"), "n": ent.get("n"),
            "version": ent.get("version"),
            "by_label": ent.get("by_label") or {},
            "label_names": ent.get("label_names") or {},
            "added": ent.get("added") or {},
            # So the dialog can say "carrying on from the detector's export"
            # rather than "this set has not been banked before", which was
            # true of the set and false of the entry it writes onto.
            "adopted": ent.get("curation_label") is None,
            "source": (ent.get("source") or {}).get("pipeline"),
            "versions": [{k: v for k, v in ver.items() if k != "snap"}
                         for ver in (ent.get("versions") or [])],
        },
        "split": [{"id": e["id"], "name": e.get("name"), "n": e.get("n"),
                   "label": e.get("curation_label")}
                  for e in found if e.get("curation_label") != "*"],
    })


@app.route("/api/curation/<gid>/<kind>/restore", methods=["POST"])
def api_curation_restore(gid, kind):
    """Put a banked version's labels back onto the live set."""
    body = request.get_json(force=True, silent=True) or {}
    entry_id = body.get("entry")
    try:
        want_v = int(body.get("version"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Which version?"}), 400

    ent = BANK.get(entry_id) if entry_id else None
    if not ent:
        return jsonify({"ok": False, "error": "No such bank entry."}), 404
    ver = None
    for v in ent.get("versions") or []:
        if v.get("v") == want_v:
            ver = v
            break
    if not ver:
        return jsonify({"ok": False,
                        "error": "That entry has no version %s." % want_v}), 404
    snap = ver.get("snap")
    if not snap:
        return jsonify({
            "ok": False,
            "error": "Version %s no longer carries a candidate-by-candidate "
                     "snapshot, so it cannot be put back -- only the recent "
                     "versions keep one. Its counts and its note are still "
                     "in the history." % want_v}), 400

    rec = CURATE.get(gid, kind)
    if not rec:
        return jsonify({"ok": False, "error": "No such curation set."}), 404

    # The snapshot holds display names; the set works in ids.
    to_id = {}
    for lab in rec.get("labels") or []:
        to_id[lab["name"]] = lab["id"]
        to_id[lab["id"]] = lab["id"]
    # A LIST per instant, not one candidate.
    #
    # Two candidates can share a rounded time -- one set on this machine
    # holds 41 such pairs -- and a dict keyed on the time holds one of
    # them, so the other could never be matched and its banked decision was
    # dropped without a word. That is where a version holding 64 decisions
    # put 63 of them back. Consumed in order, so N stamps at one instant
    # take the N decisions banked at that instant.
    by_t = {}
    for e in rec.get("events") or []:
        try:
            by_t.setdefault(round(float(e["start"]), 4), []).append(e)
        except (TypeError, ValueError, KeyError):
            continue
    used = {}

    pairs, missing, unchanged, shared = {}, 0, 0, 0
    for pair in snap:
        try:
            when, lab = float(pair[0]), pair[1]
        except (TypeError, ValueError, IndexError):
            continue
        key = round(when, 4)
        here = by_t.get(key) or []
        seen = used.get(key, 0)
        if seen >= len(here):
            # More decisions banked at this instant than there are
            # candidates on the bench to put them on.
            missing += 1
            continue
        hit = here[seen]
        used[key] = seen + 1
        if len(here) > 1:
            shared += 1
        if hit is None:
            missing += 1
            continue
        want = None if lab in (None, "unspecified") else to_id.get(lab, lab)
        if hit.get("label") == want:
            unchanged += 1
            continue
        pairs[hit["id"]] = want

    if not pairs:
        return jsonify({"ok": True, "changed": 0, "unchanged": unchanged,
                        "missing": missing, "shared": shared,
                        "version": want_v,
                        "progress": CURATE.progress(rec)})
    try:
        # Credited to whoever banked that version, at the time they
        # banked it -- those are their calls, not the calls of the
        # person putting them back.
        n, prog = CURATE.label_many(gid, kind, pairs,
                                    who=ver.get("by"),
                                    at=ver.get("at"))
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # From here the decisions on the bench are that version's. Said, so
    # banking afterwards lands as a branch off it rather than as another
    # pass on top of whatever was newest.
    try:
        CURATE.set_based_on(gid, kind, want_v)
    except curation.CurationError:
        pass        # the set is gone; the restore already reported that
    STORE.record_activity([{
        "action": "curation.restore",
        "detail": {"gid": gid, "kind": kind, "entry": entry_id,
                   "version": want_v, "changed": n, "unchanged": unchanged,
                   "missing": missing},
    }])
    return jsonify({"ok": True, "changed": n, "unchanged": unchanged,
                    "missing": missing,
                    # How many of those decisions landed on a candidate
                    # that shares its instant with another. Reported
                    # because a set with these in it is worth deduping,
                    # and because silence here is what made 64 decisions
                    # look like 63.
                    "shared": shared,
                    "version": want_v, "progress": prog})


@app.route("/api/curation/restamp", methods=["POST"])
def api_curation_restamp():
    """One-time repair for decisions written while the stamper was broken.

    Set `dry_run` to see what it would do without doing it.
    """
    body = request.get_json(force=True, silent=True) or {}
    rows = CURATE.restamp(dry_run=bool(body.get("dry_run")))
    n = sum(r["restamped"] for r in rows)
    if not body.get("dry_run") and n:
        STORE.record_activity([{
            "action": "curation.restamp",
            "detail": {"sets": len(rows), "decisions": n},
        }])
    return jsonify({"ok": True, "sets": rows, "decisions": n,
                    "dry_run": bool(body.get("dry_run"))})


@app.route("/api/curation/backfill", methods=["POST"])
def api_curation_backfill():
    """Stamp decisions that arrived from an import without provenance.

    Set `dry_run` to read what it would do before letting it run.
    """
    body = request.get_json(force=True, silent=True) or {}
    dry = bool(body.get("dry_run"))
    rows = CURATE.backfill(dry_run=dry)
    stamped = sum(r["stamped"] for r in rows)
    reviewed = sum(r["reviewed"] for r in rows)
    assigned = sum(1 for r in rows if r.get("assigned"))
    if not dry and (stamped or reviewed or assigned):
        STORE.record_activity([{
            "action": "curation.backfill",
            "detail": {"sets": len(rows), "stamped": stamped,
                       "reviewed": reviewed, "assigned": assigned},
        }])
    return jsonify({"ok": True, "sets": rows, "stamped": stamped,
                    "reviewed": reviewed, "assigned": assigned,
                    "dry_run": dry})


@app.route("/api/curation/dedupe", methods=["POST"])
def api_curation_dedupe():
    """Collapse candidates that are two records of one time.

    Set `dry_run` to read what it would do before letting it run.
    """
    body = request.get_json(force=True, silent=True) or {}
    dry = bool(body.get("dry_run"))
    rows = CURATE.dedupe(gid=body.get("gid"), kind=body.get("kind"),
                         dry_run=dry)
    removed = sum(r["removed"] for r in rows)
    if not dry and removed:
        STORE.record_activity([{
            "action": "curation.dedupe",
            "detail": {"sets": len(rows), "removed": removed},
        }])
    return jsonify({"ok": True, "sets": rows, "removed": removed,
                    "dry_run": dry})


@app.route("/api/curation/handoff")
def api_curation_handoff():
    """Save decisions to one file that can travel by any means at all.

    Because the two automatic paths both have a way of not happening: git
    needs somebody to commit, and the cloud sync stops itself when the
    machine's clock is off. Somebody who has just been through four hundred
    candidates should not have to find out afterwards that neither ran.
    """
    gid = (request.args.get("gid") or "").strip()
    kind = (request.args.get("kind") or "").strip()
    if gid and kind:
        rec = CURATE.get(gid, kind)
        if not rec:
            return jsonify({"ok": False, "error": "No such curation set."}), 404
        sets = [rec]
        stem = gid + "-" + kind
    else:
        sets = CURATE.with_decisions()
        if not sets:
            return jsonify({
                "ok": False,
                "error": "Nothing has been curated on this machine yet, so "
                         "there is nothing to hand off."}), 400
        stem = "all"

    bundle = CURATE.handoff(sets)
    who = (bundle.get("from") or {}).get("who") or "someone"
    n = sum(len(s["events"]) for s in bundle["sets"])
    decided = sum(1 for s in bundle["sets"] for e in s["events"]
                  if e.get("label"))
    STORE.record_activity([{
        "action": "curation.handoff",
        "detail": {"sets": len(bundle["sets"]), "events": n,
                   "decided": decided, "who": who},
    }])
    name = "barry-curation-%s-%s.json" % (
        _slug_for_file(who), _slug_for_file(stem))
    body = json.dumps(bundle, indent=1)
    return app.response_class(
        body, mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="%s"' % name})


@app.route("/api/curation/absorb", methods=["POST"])
def api_curation_absorb():
    """Bring another machine's decisions in, saying exactly what happened."""
    body = request.get_json(force=True, silent=True) or {}
    bundle = body.get("bundle")
    if bundle is None and body.get("path"):
        try:
            with open(body["path"], "r", encoding="utf-8") as fh:
                bundle = json.load(fh)
        except (OSError, ValueError) as exc:
            return jsonify({"ok": False,
                            "error": "Could not read that file: %s" % exc}), 400
    if bundle is None:
        # A file dropped straight in, rather than wrapped.
        bundle = body if "sets" in body else None
    if bundle is None:
        return jsonify({"ok": False,
                        "error": "Send the handoff file's contents as "
                                 "`bundle`, or a `path` to it."}), 400
    try:
        report = CURATE.absorb(bundle, prefer=body.get("prefer"))
    except curation.CurationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    STORE.record_activity([{
        "action": "curation.absorb",
        "detail": {"from": report.get("from"),
                   "sets": len(report["sets"]),
                   "added": sum(s.get("added", 0) for s in report["sets"]),
                   "taken": sum(s.get("taken", 0) for s in report["sets"]),
                   "agreed": sum(s.get("agreed", 0) for s in report["sets"]),
                   "disagreed": sum(len(s.get("disagreed") or [])
                                    for s in report["sets"])},
    }])
    return jsonify({"ok": True, "report": report})


@app.route("/api/curation/<gid>/<kind>/export")
def api_curation_export(gid, kind):
    """The whole set as a CSV, unspecified rows included."""
    rec = CURATE.get(gid, kind)
    if not rec:
        return jsonify({"ok": False, "error": "No such curation set."}), 404
    rows = CURATE.rows(rec)
    prog = CURATE.progress(rec)
    head = ("# Jarvis event curation -- %s -- %s -- %d of %d specified "
            "-- taken %s\n"
            % (rec.get("session_label") or gid, kind, prog["specified"],
               prog["total"], time.strftime("%Y-%m-%dT%H:%M:%S")))
    text = head + extras.to_csv(rows, list(curation.CSV_COLUMNS))
    name = "curation_%s_%s_%s.csv" % (kind, gid,
                                      time.strftime("%Y%m%d_%H%M%S"))
    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="Curation")
    except Exception as exc:
        STORE.record_error("curation/save", str(exc), None, {"name": name})
    resp = Response(text, mimetype="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="%s"' % name,
        "X-Barry-Rows": str(len(rows)),
    })
    if saved:
        resp.headers["X-Barry-Output"] = saved["rel"]
    return resp


# ==========================================================================
# The session registry -- one record per recording, with a permanent id
# ==========================================================================

def _attach_index(bulk=False):
    """The figure catalogue and the deck list, read once.

    `_attachments` asked for both per recording, so the housekeeping view
    read the same two stores five hundred times -- 1.7 s of `list_decks` and
    6060 directory listings for one request. Passing an index in makes the
    same answers cost one read.

    Figures are indexed the three ways the matching asks about them. Deck
    titles are only listed, because the test is "the recording's label
    appears in this title" and a substring cannot be indexed -- but the cost
    was the reading, not the test.
    """
    # Sets of figure positions, not counts.
    #
    # The test is "this figure matches by key OR by label OR by path", and one
    # figure can match on more than one -- so counting per dimension and
    # taking the larger under-counts a recording whose figures match on
    # different fields, and adding them double-counts the ones that match on
    # two. The union of positions is the same arithmetic the loop did.
    by_key, by_label, by_path = {}, {}, {}
    for i, r in enumerate(RESULTS.catalog()):
        k = r.get("session_key")
        if k:
            by_key.setdefault(k, set()).add(i)
        lab = r.get("session_label")
        if lab:
            by_label.setdefault(lab, set()).add(i)
        pth = r.get("session_path")
        if pth:
            by_path.setdefault(pth, set()).add(i)
    idx = {
        "fig_key": by_key, "fig_label": by_label, "fig_path": by_path,
        "deck_titles": [d.get("title") or "" for d in RESULTS.list_decks()],
    }
    if bulk:
        idx.update(_bulk_index())
    return idx


def _bulk_index():
    """The bank, the curation sets and the layer sets, read once each.

    Only worth building for a whole tree. `_attachments` asked each of these
    stores per recording, which over 526 records was 950 ms of re-scanning
    the same 66 banked entries, 585 ms of curation reads and 153 ms of layer
    reads. In bulk the same answers are one read apiece.

    A single recording does NOT use this -- three direct reads for one record
    are cheaper than reading every store to answer about one.
    """
    # The bank, indexed the five ways `for_session` asks about it.
    #
    # Sets of entry positions, unioned. `for_session` is an elif-chain, so
    # every entry falls into exactly one of exact/strong/weak and the count
    # is "entries matching any of the five tests" -- which is the union, and
    # is the same arithmetic as the length of the three lists together.
    bank = {"gid": {}, "key": {}, "loose": {}, "ms": {}, "mouse": {}}
    for i, r in enumerate(BANK.summaries()):
        for slot, val in (("gid", r.get("gid")),
                          ("key", r.get("session_key")),
                          ("loose", r.get("session_loose_key")),
                          ("ms", (r.get("mouse"), r.get("session"))),
                          ("mouse", r.get("mouse"))):
            if slot in ("ms", "mouse"):
                # Matched with `is not None`, as the chain does -- a mouse
                # numbered 0 is a mouse.
                if val is None or (slot == "ms" and None in val):
                    continue
            elif not val:
                continue
            bank[slot].setdefault(val, set()).add(i)

    # How many events are curated against each recording, summed over kinds
    # the way the count wants it. Curation records carry their own gid.
    cur = {}
    for r in CURATE.all():
        gid = r.get("gid")
        if gid:
            cur[gid] = cur.get(gid, 0) + (CURATE.progress(r).get("total")
                                          or 0)

    layers = {}
    for r in LAYERS.all():
        gid = r.get("gid")
        if gid:
            layers[gid] = len(r.get("labels") or {})
    return {"bank": bank, "cur_total": cur, "layer_n": layers}


def _attachments(rec, idx=None):
    """What is hanging off this recording, counted for the housekeeping view.

    Counted rather than listed: the view wants to say "3 figures, 1 deck" at a
    glance and fetch the detail only when a row is opened.

    `idx` is `_attach_index()`, shared across a whole tree. Without one this
    builds its own, which is what the single-recording routes want.
    """
    idx = idx or _attach_index()
    key = rec.get("key")
    loose = rec.get("loose_key")
    label = rec.get("label")
    paths = set(rec.get("paths") or [])

    # The same three ways a figure can belong to a recording. Unioned, not
    # summed and not maxed: the loop this replaces counted each figure once
    # if it matched by key, by label OR by path, so a figure matching two of
    # them must not count twice and figures matching different ones must
    # both count.
    hit = set()
    if key:
        hit |= idx["fig_key"].get(key, set())
    if label:
        hit |= idx["fig_label"].get(label, set())
    for pth in paths:
        hit |= idx["fig_path"].get(pth, set())
    figures = len(hit)

    decks = 0
    if label:
        for title in idx["deck_titles"]:
            if label in title:
                decks += 1

    banked = 0
    try:
        if "bank" in idx:
            # The same five tests as `for_session`, answered from the index.
            bidx, mouse = idx["bank"], rec.get("mouse")
            got = set()
            if rec.get("gid"):
                got |= bidx["gid"].get(rec["gid"], set())
            if key:
                got |= bidx["key"].get(key, set())
            if loose:
                got |= bidx["loose"].get(loose, set())
            if mouse is not None and rec.get("session") is not None:
                got |= bidx["ms"].get((mouse, rec.get("session")), set())
            if mouse is not None:
                got |= bidx["mouse"].get(mouse, set())
            banked = len(got)
        else:
            banked = len(BANK.for_session({
                "gid": rec.get("gid"),
                "key": key, "loose_key": loose,
                "mouse": rec.get("mouse"), "session": rec.get("session"),
                "start": rec.get("start"),
            }) or [])
    except Exception:                              # noqa: BLE001
        banked = 0

    spikes = rec.get("spike_sets") or []
    return {
        "bad_channels": len(rec.get("bad_channels") or []),
        "figures": figures,
        "decks": decks,
        "banked": banked,
        "spike_sets": len(spikes),
        "layers": (idx["layer_n"].get(rec.get("gid"), 0)
                   if "layer_n" in idx
                   else len((LAYERS.get(rec.get("gid")) or {}).get("labels")
                            or {})),
        "ds": (idx["cur_total"].get(rec.get("gid"), 0)
               if "cur_total" in idx
               else sum((CURATE.progress(c).get("total") or 0)
                        for c in [CURATE.get(rec.get("gid"), k)
                                  for k in curation.KINDS] if c)),
        "note": bool(rec.get("note")),
    }


def _session_by_gid(gid):
    """A recording summary for a gid, demo or real.

    The demo recordings are not in the registry -- on purpose -- so every
    route that looks a gid up has to know about them or they open as
    "unidentified" with nowhere to read from. One place, rather than the
    same three lines in five routes.
    """
    for row in demomod.registry_rows():
        if row["gid"] == gid:
            return row
    rec = REG.by_gid(gid)
    return REG.summary(rec) if rec else None


def _demo_project():
    """The made-up recordings, as one project in the tree.

    Not stored in the registry: they are not discoveries, they exist
    unconditionally, and writing them to disk would mean every clone had two
    fake sessions in its records for ever. Added at the edge instead, so
    everything downstream treats them as ordinary.
    """
    rows = demomod.registry_rows()
    by_mouse = {}
    for r in rows:
        by_mouse.setdefault(r["mouse"], []).append(r)
    return {
        "project": "DEMO",
        "demo": True,
        "n": len(rows),
        "mice": [{"mouse": "m%s" % m, "n": len(v), "demo": True,
                  "sessions": v}
                 for m, v in sorted(by_mouse.items())],
    }


@app.route("/api/registry")
def api_registry():
    """Every recording Jarvis has met, as a project / mouse / session tree.

    Warmed, but only in its plain form. `?backfill=` writes to the registry
    and `?no_demo=` changes the answer, so either one goes straight to the
    builder -- a cache keyed on a name rather than on a query string must
    never be handed a request whose query string matters.
    """
    backfill = bool(request.args.get("backfill"))
    demo = not request.args.get("no_demo")
    if backfill or not demo:
        body, how = _registry_body(backfill=backfill, demo=demo), "live"
    else:
        body, how = WARM.serve("registry", _registry_body,
                               fresh=bool(request.args.get("fresh")))
    body = dict(body)
    body["warm"] = WARM.marker("registry", how)
    return jsonify(body)


def _registry_body(backfill=False, demo=True):
    """The tree, with nothing read off the request.

    Measured at 6.0 s on 687 records, and the Sessions view cannot draw a
    row until it lands -- which is why that view has had a skeleton in it
    for as long as it has existed. Most of the six seconds is `REG.all()`
    merging the shards, the same read `/api/vacc/knows` does; once either
    one has done it the other is nearly free, which is why they are primed
    in that order.
    """
    if backfill:
        REG.backfill()
    # One index for the whole tree: `_attachments` used to read the figure
    # catalogue and the deck list once per recording, which is 508 reads of
    # the same two stores for one request.
    idx = _attach_index(bulk=True)
    tree = REG.tree(lambda rec: _attachments(rec, idx))

    # Which of these THIS computer has met, marked on the row.
    #
    # Not a machine-id lookup: sightings are keyed on the label a machine
    # was using at the time, so this one computer's are filed under three
    # different names and an id lookup matched none of 476 recordings.
    names = _my_names()
    seen_n = [0]

    def mark(node):
        if isinstance(node, dict):
            if node.get("gid") and "paths" in node:
                got = REG.seen_by(node, names)
                node["seen_here"] = got
                if got:
                    seen_n[0] += 1
            for v in node.values():
                mark(v)
        elif isinstance(node, list):
            for v in node:
                mark(v)

    mark(tree)

    if demo:
        # Last, so real data is what you see first -- but always there, so
        # a machine with nothing mounted is not an empty application.
        tree = list(tree) + [_demo_project()]
    return {
        "ok": True,
        "projects": REG.projects(),
        "known_projects": list(sessreg.KNOWN_PROJECTS),
        "tree": tree,
        "demo_paths": [demomod.path_for(s)
                       for s in demomod.SESSIONS.values()],
        "total": len([r for r in REG.all() if not r.get("retired")]),
        # How many this computer has actually met, so the local view can say
        # what it is showing rather than looking like a shorter catalogue.
        "seen_here": seen_n[0],
        "my_names": sorted(names),
        # So the tree can branch on any of them without a second round trip.
        "mice": MICE.index(),
        "attributes": MICE.attributes(),
    }


@app.route("/api/registry/<gid>")
def api_registry_one(gid):
    # A demo gid resolves without being in the registry, so curation and
    # StrataScope can open one the same way they open anything else.
    for row in demomod.registry_rows():
        if row["gid"] == gid:
            return jsonify({"ok": True, "session": row, "attachments": {}})
    rec = REG.by_gid(gid)
    if not rec:
        return jsonify({"ok": False, "error": "No session " + gid}), 404
    return jsonify({"ok": True,
                    "session": REG.summary(rec, _attachments),
                    "record": {k: v for k, v in rec.items()
                               if k not in ("view_state",)}})


@app.route("/api/registry/<gid>/patch", methods=["POST"])
def api_registry_patch(gid):
    """Manual organisation: project, label, note, and the known paths."""
    body = request.get_json(force=True) or {}
    try:
        rec = None
        if "project" in body:
            # `project_source` is only ever passed by something putting a
            # record back as it found it -- see `set_project`. A person
            # choosing from the picker sends no source and gets "manual",
            # which is what choosing means.
            rec = REG.set_project(gid, body["project"],
                                  body.get("project_source") or "manual")
        if "label" in body:
            rec = REG.set_label(gid, body["label"])
        if "note" in body:
            rec = REG.set_note(gid, body["note"])
        if body.get("add_path"):
            rec = REG.add_path(gid, body["add_path"])
        if body.get("forget_path"):
            rec = REG.forget_path(gid, body["forget_path"])
        if rec is None:
            return jsonify({"ok": False,
                            "error": "Nothing to change."}), 400
    except KeyError:
        return jsonify({"ok": False, "error": "No session " + gid}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("registry/patch", exc, 400, {"gid": gid})
    STORE.record_activity([{
        "action": "registry.patch",
        "detail": {"gid": gid, "fields": sorted(body.keys())},
        "session": {"key": rec.get("key"), "label": rec.get("label")},
    }])
    return jsonify({"ok": True, "session": REG.summary(rec, _attachments)})


# ==========================================================================
# Folders a scan would not vouch for
# ==========================================================================
# A scan assesses each folder before registering it (see discovery.assess).
# Anything it holds back is listed rather than dropped, and can be accepted
# here -- because "this looks wrong" is a judgement about data, and the person
# who made the recording is better placed to make it than a size check.
ACCEPTED_FOLDERS = set()


@app.route("/api/discover/accept", methods=["POST"])
def api_discover_accept():
    """Register a folder the scan held back."""
    body = request.get_json(force=True) or {}
    path = body.get("path") or ""
    if not os.path.isdir(path):
        return jsonify({"ok": False, "error": "No such folder: " + path}), 400
    contents = discovery.classify_folder(path)
    if not contents:
        return jsonify({"ok": False,
                        "error": "There is no recording data in there."}), 400
    rec = discovery.describe_session(path, contents)
    ACCEPTED_FOLDERS.add(path)
    new, seen = REG.ingest([rec], scan_id="accepted", root=path)
    STORE.record_activity([{
        "action": "scan.accept",
        "detail": {"path": path,
                   "verdict": (rec.get("quality") or {}).get("verdict")},
    }])
    return jsonify({"ok": True, "registered": {"new": new, "seen": seen},
                    "session": rec})


@app.route("/api/registry/audit")
def api_registry_audit():
    """Re-check what is already registered against what is on disk now.

    The assessment arrived after these records did, so the folders it would
    hold back today are already in the registry. This finds them: a recording
    with no data in it is not a recording, and it should not be sitting in a
    project tree looking like one.

    Reachable paths only -- a recording on somebody else's drive cannot be
    judged from here, and guessing would be worse than saying nothing.
    """
    rows, unreachable = [], 0
    for rec in REG.all():
        if rec.get("retired"):
            continue
        here = [p for p in (rec.get("paths") or []) if os.path.isdir(p)]
        if not here:
            unreachable += 1
            continue
        contents = discovery.classify_folder(here[0])
        if not contents:
            rows.append({
                "gid": rec.get("gid"), "label": rec.get("label"),
                "path": here[0],
                "quality": {"verdict": "reject", "usable": False,
                            "reasons": ["there is no recording data in this "
                                        "folder any more"]},
            })
            continue
        q = discovery.assess(here[0], contents)
        if q["verdict"] in ("empty", "reject", "suspect"):
            rows.append({"gid": rec.get("gid"), "label": rec.get("label"),
                         "path": here[0], "quality": q,
                         "attached": _attachments(rec)})
    order = {"reject": 0, "empty": 1, "suspect": 2}
    rows.sort(key=lambda r: (order.get(r["quality"]["verdict"], 3),
                             str(r.get("label"))))
    return jsonify({"ok": True, "rows": rows, "unreachable": unreachable,
                    "checked": len(REG.all()) - unreachable})


@app.route("/api/registry/retire", methods=["POST"])
def api_registry_retire():
    """Mark a registered recording as not worth carrying.

    Retired, not deleted: the record stays, so anything already pointing at
    its id still resolves, and it stops appearing in the tree. Nothing on the
    recording drive is touched -- Jarvis does not delete data it did not
    write, and an aborted acquisition is still the lab's to keep or bin.
    """
    body = request.get_json(force=True) or {}
    gids = body.get("gids") or ([body["gid"]] if body.get("gid") else [])
    reason = body.get("reason") or "no data in the folder"
    done = []
    for gid in gids:
        rec = REG.by_gid(gid)
        if not rec:
            continue
        ident = {k: rec.get(k) for k in
                 ("key", "loose_key", "mouse", "session", "start", "label")}
        ident["gid"] = gid
        STORE.upsert_session(ident, {
            "retired": True, "retired_reason": reason,
            "retired_at": cloudmod.now(),
        })
        RESULTS.tombs.add("session", gid, note="retired: " + reason)
        done.append(gid)
    STORE.record_activity([{
        "action": "registry.retire",
        "detail": {"n": len(done), "reason": reason},
    }])
    return jsonify({"ok": True, "retired": done})


@app.route("/api/registry/<gid>/forget", methods=["POST"])
def api_registry_forget(gid):
    """Drop a record entirely, and keep it dropped.

    For a recording that should never have been registered -- a scratch copy,
    a test tree, a folder that was moved and re-registered under a new name.
    The recording itself is untouched; only what Jarvis remembers about it
    goes.

    It stays gone. The record is erased and a tombstone is written against
    its permanent id, so a colleague's copy of the registry does not push it
    back and the next scan of that drive does not re-register it. That is the
    point of the button: a scratch copy that creeps back on every scan has
    not been forgotten.

    This used to claim that "opening or scanning it again starts a fresh
    record", which is not what happens -- the scan finds the folder, reports
    it catalogued, and nothing appears, because the tombstone retires the row
    the moment it returns. Bringing one back is a deliberate act, not a side
    effect of walking a drive.
    """
    rec = REG.by_gid(gid)
    if not rec:
        return jsonify({"ok": False, "error": "No session " + gid}), 404
    # Every machine's shard of this record, not just this one's: forgetting a
    # session that only half the lab stops knowing about is worse than not
    # forgetting it, because the next scan pulls the other half back in.
    base = STORE.session_base(rec.get("key") or "")
    if not STORE.sessions.erase(base):
        return jsonify({"ok": False,
                        "error": "Nothing on disk for " + gid}), 400
    # Remembered, so the next sync retires it up there rather than pulling
    # it straight back down.
    RESULTS.tombs.add("session", gid, note="forgotten in housekeeping")
    STORE.record_activity([{
        "action": "registry.forget",
        "detail": {"gid": gid, "key": rec.get("key")},
    }])
    return jsonify({"ok": True})


@app.route("/api/registry/merge", methods=["POST"])
def api_registry_merge():
    """Two records that turned out to be the same recording."""
    body = request.get_json(force=True) or {}
    try:
        rec = REG.merge(body.get("keep"), body.get("drop"))
    except KeyError as exc:
        return jsonify({"ok": False, "error": "No session %s" % exc}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("registry/merge", exc, 400, dict(body))
    STORE.record_activity([{
        "action": "registry.merge",
        "detail": {"keep": body.get("keep"), "drop": body.get("drop")},
    }])
    return jsonify({"ok": True, "session": REG.summary(rec, _attachments)})


@app.route("/api/registry/split", methods=["POST"])
def api_registry_split():
    """One record that turned out to be two recordings."""
    body = request.get_json(force=True) or {}
    try:
        rec = REG.split(body.get("gid"), body.get("path"))
    except KeyError as exc:
        return jsonify({"ok": False, "error": "No session %s" % exc}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("registry/split", exc, 400, dict(body))
    STORE.record_activity([{
        "action": "registry.split",
        "detail": {"from": body.get("gid"), "path": body.get("path"),
                   "gid": rec.get("gid")},
    }])
    return jsonify({"ok": True, "session": REG.summary(rec, _attachments)})


# ==========================================================================
# ToolKit -- jobs that run across many sessions at once
# ==========================================================================

def _bad_channel_args():
    """The scope arguments, read the same way for preview and download."""
    a = request.args
    return {
        "scope": (a.get("scope") or "all").strip(),
        "key": a.get("key") or None,
        "mouse": a.get("mouse") or None,
        "group": a.get("group") or None,
        "date_from": a.get("from") or None,
        "date_to": a.get("to") or None,
    }


@app.route("/api/toolkit/scopes")
def api_toolkit_scopes():
    """What there is to choose from, so the picker is not free text.

    Offering the mice and projects that actually exist is the difference
    between a filter and a guessing game.

    Through REG.all(), which is the same read cached against the shard
    signature. Straight off the store this was 4.9 s EVERY time the ToolKit
    was opened -- not merely the first -- because `STORE.all_sessions()`
    re-reads and re-merges all 1510 shards on every call and the registry
    does not. Nothing below edits a record, so the shared copies are fine.
    """
    sessions = REG.all()
    mice, groups, days = set(), set(), []
    for rec in sessions:
        if rec.get("mouse") is not None:
            mice.add(int(rec["mouse"]))
        if rec.get("group"):
            groups.add(rec["group"])
        day = toolkit._day(rec.get("start"))
        if day:
            days.append(day)
    return jsonify({
        "ok": True,
        "sessions": [{"key": r.get("key"), "label": r.get("label"),
                      "date": toolkit._day(r.get("start")),
                      "mouse": r.get("mouse"), "session": r.get("session"),
                      "group": r.get("group"),
                      "n_bad": len(r.get("bad_channels") or [])}
                     for r in sorted(sessions,
                                     key=lambda r: (r.get("mouse") or 0,
                                                    r.get("session") or 0))],
        "mice": sorted(mice),
        "groups": sorted(groups),
        "first_day": min(days) if days else None,
        "last_day": max(days) if days else None,
        "total": len(sessions),
    })


@app.route("/api/toolkit/bad-channels")
def api_toolkit_bad_channels():
    """Preview the bad-channel export: the rows, plus counts worth reading."""
    args = _bad_channel_args()
    form = "wide" if request.args.get("form") == "wide" else "long"
    include_clean = request.args.get("clean") in ("1", "true", "yes")
    try:
        # REG.all(): the same records, cached against the shard
        # signature. `toolkit.select` and `rows` only read.
        picked = toolkit.select(REG.all(), **args)
    except toolkit.ToolkitError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    rows = toolkit.rows(picked, form, include_clean=include_clean)
    return jsonify({
        "ok": True,
        "scope_label": toolkit.scope_label(**args),
        "columns": toolkit.columns(form),
        "rows": rows,
        "summary": toolkit.summarize(picked),
        "filename": toolkit.filename(form, **args) + ".csv",
    })


@app.route("/api/toolkit/bad-channels/export")
def api_toolkit_bad_channels_export():
    """The same rows as a CSV, streamed back and filed under Results/.

    Filed as well as downloaded: a list of bad channels that lives only in a
    browser's download folder is not a record anyone else can find.
    """
    args = _bad_channel_args()
    form = "wide" if request.args.get("form") == "wide" else "long"
    include_clean = request.args.get("clean") in ("1", "true", "yes")
    try:
        # REG.all(): the same records, cached against the shard
        # signature. `toolkit.select` and `rows` only read.
        picked = toolkit.select(REG.all(), **args)
    except toolkit.ToolkitError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    rows = toolkit.rows(picked, form, include_clean=include_clean)
    if not rows:
        return jsonify({"ok": False,
                        "error": "Nothing to export: no bad channels are "
                                 "marked in %s."
                                 % toolkit.scope_label(**args)}), 400

    cols = toolkit.columns(form)
    body = extras.to_csv(rows, cols)
    # A header comment line, so a CSV opened months later still says what it
    # was a list of and when it was taken.
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    head = ("# Jarvis bad-channel export -- %s -- %d row(s) from %d "
            "session(s) -- taken %s\n"
            % (toolkit.scope_label(**args), len(rows), len(picked), stamp))
    text = head + body

    stem = toolkit.filename(form, **args)
    name = "%s_%s.csv" % (stem, time.strftime("%Y%m%d_%H%M%S"))

    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="ToolKit",
                            lane=lane_of())
    except Exception as exc:
        STORE.record_error("toolkit/save", "Could not write to Results/: %s"
                           % exc, None, {"name": name})

    run = STORE.record_run({
        "kind": "toolkit", "script": "ToolKit bad-channel export",
        "label": "Bad channels -- " + toolkit.scope_label(**args),
        "status": "done", "format": "csv",
        "parameters": dict(args, form=form, include_clean=include_clean),
        "summary": toolkit.summarize(picked),
        "rows": len(rows),
    })
    if saved:
        STORE.update_run(run["id"], {"output": saved})

    resp = Response(text, mimetype="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="%s"' % name,
        "X-Barry-Run-Id": run["id"],
        "X-Barry-Rows": str(len(rows)),
    })
    if saved:
        resp.headers["X-Barry-Output"] = saved["rel"]
    return resp


# ==========================================================================
# Storyboard decks
# ==========================================================================
@app.route("/api/decks")
def api_decks():
    return jsonify({"ok": True, "decks": RESULTS.list_decks()})


@app.route("/api/deck/<deck_id>")
def api_deck_get(deck_id):
    deck = RESULTS.get_deck(deck_id)
    if not deck:
        return jsonify({"ok": False, "error": "No such deck."}), 404
    return jsonify({"ok": True, "deck": deck})


@app.route("/api/deck", methods=["POST"])
def api_deck_save():
    body = request.get_json(force=True) or {}
    deck = body.get("deck") or {}
    if not isinstance(deck, dict):
        return jsonify({"ok": False, "error": "Bad deck payload."}), 400
    try:
        saved = RESULTS.save_deck(deck)
    except Exception as exc:
        return fail("deck/save", exc, 400)
    STORE.record_activity([{
        "action": "deck.save",
        "detail": {"id": saved["id"], "title": saved.get("title"),
                   "slides": len(saved.get("slides") or [])},
    }])
    return jsonify({"ok": True, "deck": saved})


@app.route("/api/deck/<deck_id>/delete", methods=["POST"])
def api_deck_delete(deck_id):
    ok = RESULTS.delete_deck(deck_id)
    if ok:
        STORE.record_activity([{"action": "deck.delete", "detail": {"id": deck_id}}])
    return jsonify({"ok": ok})


@app.route("/api/deck/export", methods=["POST"])
def api_deck_export():
    """Render a whole deck to a multi-page PDF (or a PNG per slide)."""
    body = request.get_json(force=True) or {}
    deck = body.get("deck") or RESULTS.get_deck(body.get("id", "")) or {}
    fmt = (body.get("format") or "pdf").lower()
    if not deck.get("slides"):
        return jsonify({"ok": False, "error": "This deck has no slides."}), 400
    try:
        blob, mime, name = storyboard.render_deck(deck, RESULTS, fmt=fmt)
    except storyboard.DeckError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("deck/export", exc, 400)

    saved = None
    try:
        saved = save_output(blob, name, subdir="Storyboards",
                            lane=lane_of(body))
    except Exception:
        saved = None

    headers = {"Content-Disposition": 'attachment; filename="%s"' % name}
    if saved:
        headers["X-Barry-Output"] = saved["rel"]
    STORE.record_run({
        "kind": "deck", "script": "Storyboard export",
        "label": deck.get("title") or "deck", "status": "done",
        "format": fmt, "output": saved,
        "parameters": {"slides": len(deck.get("slides") or [])},
    })
    return Response(blob, mimetype=mime, headers=headers)



# ==========================================================================
# Workbench preferences -- favourites, smart collections, last-used state
# ==========================================================================
@app.route("/api/prefs", methods=["GET", "POST"])
def api_prefs():
    if request.method == "GET":
        return jsonify({"ok": True, "prefs": STORE.get_prefs()})
    body = request.get_json(force=True) or {}
    try:
        prefs = STORE.set_prefs(body.get("patch") or body)
    except Exception as exc:
        return fail("prefs", exc, 400)
    return jsonify({"ok": True, "prefs": prefs})


# ==========================================================================
# Pipeline: preflight + batch queue
# ==========================================================================
@app.route("/api/pipeline/preflight", methods=["POST"])
def api_pipeline_preflight():
    """Everything that would make a stage fail, checked before it runs."""
    body = request.get_json(force=True) or {}
    folder = body.get("folder", "")
    track = body.get("track", "session")
    stages = pipeline.all_stages().get(track, [])
    key = body.get("key")
    if key:
        stages = [s for s in stages if s["key"] == key]

    checks = []

    def add(level, name, message):
        checks.append({"level": level, "name": name, "message": message})

    if not folder:
        add("bad", "folder", "No folder chosen.")
    elif not os.path.isdir(folder):
        add("bad", "folder", "Not a folder: " + folder)
    else:
        add("ok", "folder", folder)

    langs = {s.get("lang") for s in stages}
    if "matlab" in langs:
        if runner.MATLAB_EXE:
            rel = sysinfo.matlab_release(runner.MATLAB_EXE) or ""
            add("ok", "MATLAB", (rel + " at " if rel else "") + runner.MATLAB_EXE)
        else:
            add("bad", "MATLAB",
                "These stages need MATLAB and it was not found on PATH. "
                "Run the setup script, or set Jarvis_MATLAB to the executable.")
    if "python" in langs:
        add("ok", "Python", "%s (%s)" % (sysinfo.describe()["python"],
                                         sys.executable))
        py_items = [it for it in _CATALOG["items"]
                    if it.get("rel") in {s.get("script") for s in stages}]
        missing = extras.missing_python_packages(py_items, REPO_ROOT)
        if missing:
            add("warn", "Python packages",
                "Not importable: " + ", ".join(missing))
        else:
            add("ok", "Python packages", "Everything these stages import "
                                         "is installed.")

    # Free space -- IED output is not small.
    try:
        free = shutil.disk_usage(folder if os.path.isdir(folder)
                                 else REPO_ROOT).free
        gb = free / 1024.0 ** 3
        add("ok" if gb > 5 else "warn", "free space", "%.1f GB free" % gb)
    except Exception:
        pass

    if os.path.isdir(folder):
        health = extras.session_health(folder, deep=False)
        checks.extend(health["checks"])
        # A stage's own input check is the most specific evidence we have.
        for s in stages:
            st = pipeline.check_stage(s, folder)
            level = "ok" if st.get("ready") else "warn"
            checks.append({
                "level": level, "name": s["title"],
                "message": st.get("reason") or ("Inputs present."
                                                if st.get("ready")
                                                else "Inputs not found yet."),
            })

    levels = [c["level"] for c in checks]
    return jsonify({
        "ok": True, "checks": checks,
        "level": "bad" if "bad" in levels else
                 ("warn" if "warn" in levels else "ok"),
        "can_run": "bad" not in levels,
    })


_BATCH = {}


@app.route("/api/pipeline/batch", methods=["POST"])
def api_pipeline_batch():
    """Queue one stage across many folders and walk them one at a time."""
    body = request.get_json(force=True) or {}
    folders = [f for f in (body.get("folders") or []) if os.path.isdir(f)]
    keys = body.get("keys") or ([body.get("key")] if body.get("key") else [])
    track = body.get("track", "session")
    if not folders:
        return jsonify({"ok": False, "error": "No valid folders."}), 400
    if not keys:
        return jsonify({"ok": False, "error": "No stages chosen."}), 400

    batch_id = "batch_" + uuid.uuid4().hex[:8]
    _BATCH[batch_id] = {
        "id": batch_id, "track": track, "keys": keys,
        "options": body.get("options") or {},
        "items": [{"folder": f, "key": k, "status": "queued", "job": None,
                   "label": os.path.basename(f.rstrip("\\/")) or f}
                  for f in folders for k in keys],
        "started": time.time(), "canceled": False, "cursor": 0,
    }
    STORE.record_activity([{
        "action": "pipeline.batch",
        "detail": {"id": batch_id, "folders": len(folders), "stages": keys},
    }])
    _batch_advance(batch_id)
    return jsonify({"ok": True, "batch": _batch_view(batch_id)})


def _batch_advance(batch_id):
    """Start the next queued item if nothing of ours is running."""
    b = _BATCH.get(batch_id)
    if not b or b["canceled"]:
        return
    for item in b["items"]:
        if item["status"] == "running":
            return
    nxt = next((i for i in b["items"] if i["status"] == "queued"), None)
    if not nxt:
        return

    stage = next((s for s in pipeline.all_stages().get(b["track"], [])
                  if s["key"] == nxt["key"]), None)
    if not stage:
        nxt["status"] = "failed"
        nxt["error"] = "Unknown stage."
        return _batch_advance(batch_id)

    params, extra = pipeline.build_stage_call(stage, nxt["folder"],
                                              b["options"], None)
    try:
        job = runner.run_script(REPO_ROOT, stage["script"], stage["lang"],
                                params, extra)
    except Exception as exc:
        nxt["status"] = "failed"
        nxt["error"] = str(exc)
        STORE.record_error("batch:" + nxt["key"], str(exc), None,
                           {"folder": nxt["folder"]})
        return _batch_advance(batch_id)

    job.label = "%s -- %s" % (stage["title"], nxt["label"])
    job.meta.update({"kind": "pipeline", "stage": nxt["key"],
                     "track": b["track"], "batch": batch_id,
                     "parameters": dict(b["options"], folder=nxt["folder"]),
                     "session": _identity_brief(nxt["folder"])})
    nxt["status"] = "running"
    nxt["job"] = job.id


@app.route("/api/pipeline/batch/<batch_id>")
def api_pipeline_batch_status(batch_id):
    if batch_id not in _BATCH:
        return jsonify({"ok": False, "error": "No such batch."}), 404
    # Poll-driven: reconcile against the job table, then start the next one.
    b = _BATCH[batch_id]
    for item in b["items"]:
        if item["status"] != "running" or not item["job"]:
            continue
        job = runner.get_job(item["job"])
        if not job:
            item["status"] = "failed"
            item["error"] = "The job vanished."
            continue
        snap = job.snapshot()
        if snap["status"] in ("done", "failed", "canceled", "cancelled"):
            item["status"] = snap["status"]
            item["seconds"] = (snap.get("ended") or 0) - (snap.get("started") or 0)
    _batch_advance(batch_id)
    return jsonify({"ok": True, "batch": _batch_view(batch_id)})


@app.route("/api/pipeline/batch/<batch_id>/cancel", methods=["POST"])
def api_pipeline_batch_cancel(batch_id):
    b = _BATCH.get(batch_id)
    if not b:
        return jsonify({"ok": False, "error": "No such batch."}), 404
    b["canceled"] = True
    for item in b["items"]:
        if item["status"] == "queued":
            item["status"] = "canceled"
        elif item["status"] == "running" and item["job"]:
            runner.cancel_job(item["job"])
    return jsonify({"ok": True, "batch": _batch_view(batch_id)})


def _batch_view(batch_id):
    b = _BATCH.get(batch_id) or {}
    items = b.get("items") or []
    counts = {}
    for i in items:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    done = sum(counts.get(k, 0) for k in ("done", "failed", "canceled"))
    return {
        "id": b.get("id"), "items": items, "counts": counts,
        "total": len(items), "finished": done,
        "canceled": b.get("canceled"),
        "running": counts.get("running", 0) > 0 or counts.get("queued", 0) > 0,
        "seconds": round(time.time() - (b.get("started") or time.time()), 1),
    }


# ==========================================================================
# Session health
# ==========================================================================
@app.route("/api/session/health", methods=["POST"])
def api_session_health():
    body = request.get_json(force=True) or {}
    paths = body.get("paths") or ([body["path"]] if body.get("path") else [])
    deep = bool(body.get("deep"))
    out = []
    for p in paths[:60]:
        try:
            rep = extras.session_health(p, deep=deep)
        except Exception as exc:
            out.append({"path": p, "level": "bad", "checks": [
                {"level": "bad", "name": "check failed", "message": str(exc)}]})
            continue
        # File what the continuity check found.
        #
        # `session_health` runs it and returns the answer, which is why the
        # report on screen is right -- and nothing kept it, so the archive
        # log held only the sessions somebody had aimed the continuity route
        # at by hand. Checking a hundred and eighty-nine recordings flagged
        # the ones with gaps and left the filter with nothing to filter.
        cont = rep.get("continuity")
        if cont and cont.get("ok"):
            gid = _gid_for_path(p)
            if gid:
                rep["gid"] = gid
                try:
                    HEALTHLOG.record(gid, p, cont,
                                     label=(rep.get("identity") or {}).get(
                                         "label"),
                                     deep=bool(deep))
                except Exception as exc:                 # noqa: BLE001
                    app.logger.warning("health log: %s", exc)
        out.append(rep)
    STORE.record_activity([{
        "action": "session.health",
        "detail": {"n": len(out), "deep": deep,
                   "levels": [o.get("level") for o in out]},
    }])
    return jsonify({"ok": True, "reports": out})


def _gid_for_path(path):
    """Which registered session is this folder?

    Through the registry's own path list, which is how the application
    decides two names are one recording. NOT through `ids.identify`: the
    bank and the health log key on the registry's session id, and matching
    on the identity string silently returns nothing -- which reads as "this
    recording has nothing filed against it".
    """
    if not path:
        return None
    want = os.path.normcase(os.path.abspath(path)).rstrip("\\/")
    try:
        for rec in REG.all():
            for entry in (rec.get("paths") or []):
                where = entry.get("path") if isinstance(entry, dict) else entry
                if not where:
                    continue
                if os.path.normcase(os.path.abspath(where)).rstrip("\\/") \
                        == want:
                    return rec.get("gid")
    except Exception:                                    # noqa: BLE001
        return None
    return None


@app.route("/api/health/summary")
def api_health_summary():
    """What is known about every recording anybody has checked.

    One row per session: when it was last checked and by whom, whether it
    has gaps, what is banked against it, and whether that has been
    re-timed. The session list filters on this -- which is the point of
    keeping the checks at all.
    """
    try:
        rows = HEALTHLOG.summary(BANK)
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
    issues = [r for r in rows.values() if r.get("concat_issue")]
    return jsonify({
        "ok": True,
        "sessions": rows,
        "n_checked": len(rows),
        "n_concat": len(issues),
        "n_unpatched": len([r for r in rows.values() if r.get("unpatched")]),
    })


@app.route("/api/session/healthlog", methods=["POST"])
def api_session_healthlog():
    """One recording's check history, beside what is banked against it.

    The two together are the question people actually have: this recording
    has gaps -- was anything built from it before that was known, and by
    whom?
    """
    body = request.get_json(force=True) or {}
    gid = body.get("gid") or _gid_for_path(body.get("path"))
    if not gid:
        return jsonify({"ok": False, "unknown_session": True,
                        "reason": "That folder is not in the session "
                                  "registry, so there is nothing filed "
                                  "against it."}), 200

    rec = HEALTHLOG.get(gid) or {}
    checks = sorted((rec.get("checks") or []),
                    key=lambda c: extras.moment_key(c.get("at")),
                    reverse=True)
    entries = []
    for e in BANK.all():
        if e.get("gid") != gid:
            continue
        basis = e.get("time_basis") or {}
        added = e.get("added") or {}
        entries.append({
            "entry_id": e.get("id"),
            "name": e.get("name"),
            "type": e.get("type"),
            "n": e.get("n"),
            "pipeline": (e.get("source") or {}).get("pipeline"),
            "added_at": added.get("at"),
            "added_by": added.get("by"),
            "added_on": added.get("machine"),
            "versions": len(e.get("versions") or []),
            "time_basis": basis.get("kind"),
            "retimed_at": basis.get("at"),
            "retimed_by": basis.get("by"),
            "retimed_map": basis.get("gap_map_sha"),
            "patched": basis.get("kind") == retimemod.TRUE,
        })
    return jsonify({
        "ok": True, "gid": gid,
        "path": rec.get("path"), "label": rec.get("label"),
        "checks": checks, "n_checks": len(checks),
        "latest": healthlogmod.HealthLog.latest(rec),
        "banked": entries,
    })


@app.route("/api/session/continuity", methods=["POST"])
def api_session_continuity():
    """The whole segment map for one recording.

    The health report carries a capped version of this so a sixty-session
    scan cannot return a hundred thousand rows; the details panel asks here
    for the rest. `refresh` skips the cache, which is the honest thing to
    offer after somebody has re-copied a folder.
    """
    body = request.get_json(force=True) or {}
    path = body.get("path") or ""
    if not path:
        return jsonify({"ok": False, "error": "No path."}), 400
    try:
        rep = continuitymod.check(
            path,
            all_channels=bool(body.get("all_channels")),
            strict=bool(body.get("strict")),
            use_cache=not bool(body.get("refresh")))
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
    if rep is None:
        return jsonify({"ok": False,
                        "error": "No .ncs files in that folder."}), 404
    # Filed against the session, so the archive can be asked about this
    # later rather than the answer being thrown away with the response.
    gid = body.get("gid") or _gid_for_path(path)
    try:
        HEALTHLOG.record(gid, path, rep, label=body.get("label"),
                         deep=bool(body.get("all_channels")))
    except Exception as exc:                             # noqa: BLE001
        app.logger.warning("health log: %s", exc)
    rep["gid"] = gid

    STORE.record_activity([{
        "action": "session.continuity",
        "detail": {"path": path, "gid": gid,
                   "segments": rep.get("n_segments"),
                   "seconds_lost": rep.get("seconds_lost"),
                   "gap_map_sha": rep.get("gap_map_sha"),
                   "cached": rep.get("cached"),
                   "all_channels": bool(body.get("all_channels"))},
    }])
    return jsonify(rep)


@app.route("/api/session/timebasis", methods=["POST"])
def api_session_timebasis():
    """Which clock this session's banked events are on, and the evidence.

    Reads. Writes nothing, and is the only one of the two that the health
    report calls -- so a report can say what is wrong without anything being
    able to act on it by accident.
    """
    body = request.get_json(force=True) or {}
    path = body.get("path") or ""
    gid = body.get("gid") or ""
    kind = body.get("kind") or "ds"
    if not path and not gid:
        return jsonify({"ok": False, "error": "Need a path or a gid."}), 400

    rep = None
    if path:
        try:
            rep = continuitymod.check(path)
        except Exception:                                # noqa: BLE001
            rep = None

    # Which session this folder is, if the caller did not say. A row built
    # from a scan rather than from the registry has no gid, and answering
    # "nothing is banked" because none was supplied is a statement about the
    # data made on the strength of a missing parameter.
    if not gid and path:
        want = os.path.normcase(os.path.abspath(path)).rstrip("\\/")
        for rec in REG.all():
            for entry in (rec.get("paths") or []):
                where = entry.get("path") if isinstance(entry, dict) else entry
                if not where:
                    continue
                if os.path.normcase(os.path.abspath(where)).rstrip("\\/") \
                        == want:
                    gid = rec.get("gid")
                    break
            if gid:
                break
        out_gid_resolved = bool(gid)
    else:
        out_gid_resolved = bool(gid)

    if not gid:
        # Said plainly rather than answered as an empty list.
        return jsonify({
            "ok": True, "gid": None, "unknown_session": True,
            "n_entries": 0, "entries": [],
            "reason": ("This folder is not in the session registry, so there "
                       "is no way to tell which banked sets belong to it. "
                       "Scan it in first."),
        })

    # Every banked entry for this session, each with its own answer -- two
    # sets on one recording can be on different clocks and averaging that
    # into one verdict would be the wrong kind of tidy.
    entries = [e for e in BANK.all() if e.get("gid") == gid]
    who = (STORE.provenance() or {}).get("user")
    cur_set = CURATE.get(gid, kind) if gid else None

    out = {"ok": True, "gid": gid, "n_entries": len(entries), "entries": [],
           "gid_resolved": out_gid_resolved}
    if rep and rep.get("ok"):
        out["continuity"] = {
            "n_segments": rep.get("n_segments"),
            "max_time_error_ms": rep.get("max_time_error_ms"),
            "seconds_lost": rep.get("seconds_lost"),
            "gap_map_sha": rep.get("gap_map_sha"),
        }
    for e in entries:
        gate = retimemod.offer(rep, e, cur_set, me=who)
        out["entries"].append({
            "entry_id": e.get("id"),
            "name": e.get("name"),
            "type": e.get("type"),
            "n": e.get("n"),
            "pipeline": (e.get("source") or {}).get("pipeline"),
            "basis": gate.get("basis"),
            "correctable": bool(gate.get("offer")),
            "reason": gate.get("reason"),
        })
    return jsonify(out)


@app.route("/api/session/retime", methods=["POST"])
def api_session_retime():
    """Move a banked event set from Toothy's clock to the recording's own.

    Preview by default. `apply: true` writes, and only then -- there is no
    path through here that rewrites a timestamp because a flag was omitted.
    """
    body = request.get_json(force=True) or {}
    path = body.get("path") or ""
    entry_id = body.get("entry_id") or ""
    gid = body.get("gid") or ""
    kind = body.get("kind") or "ds"
    do_apply = bool(body.get("apply"))
    # Which version supplies the times and the labels. Absent means the
    # live set, which is the default and the common case.
    from_version = body.get("from_version")
    if from_version in ("", "current"):
        from_version = None
    if not path or not entry_id:
        return jsonify({"ok": False,
                        "error": "Need the recording path and the entry."}), 400

    try:
        rep = continuitymod.check(path)
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
    if not rep or not rep.get("ok"):
        return jsonify({"ok": False,
                        "error": "Could not segment that recording."}), 400

    entry = BANK.get(entry_id)
    if not entry:
        return jsonify({"ok": False, "error": "No such bank entry."}), 404

    who = (STORE.provenance() or {}).get("user")
    cur_set = CURATE.get(gid, kind) if gid else None

    # Every version and whether the correction can run from it, always --
    # this is what the picker is built from, and it has to be there even
    # when the gate below refuses, because "already corrected" is exactly
    # the case where somebody needs to pick an earlier one.
    try:
        offer_versions = BANK.retime_versions(entry_id, retimemod.TRUE)
    except Exception:                                    # noqa: BLE001
        offer_versions = {"versions": [], "current_version": None,
                          "drops_fields": []}

    gate = retimemod.offer(rep, entry, cur_set, me=who)
    if not gate.get("offer") and from_version is None:
        return jsonify({"ok": False, "offered": False,
                        "reason": gate.get("reason"),
                        "basis": gate.get("basis"),
                        # So the window can offer the way forward rather
                        # than only the refusal: a set already on the
                        # recording's clock can still be corrected again
                        # from a version that predates that correction.
                        "versions": offer_versions}), 409

    # The map the correction is derived from, and the hash that will be
    # stamped on what it writes. A later run against a folder that has
    # changed under the entry will not match this, which is the point.
    sha = rep.get("gap_map_sha")
    mapping = lambda t: continuitymod.concat_to_true(rep, t)

    out = {
        "ok": True,
        "applied": do_apply,
        "gap_map_sha": sha,
        "preview": retimemod.preview(rep, entry, gid=gid, kind=kind),
        "versions": offer_versions,
        "from_version": from_version,
        "continuity": {"n_segments": rep.get("n_segments"),
                       "max_time_error_ms": rep.get("max_time_error_ms"),
                       "seconds_lost": rep.get("seconds_lost")},
    }
    # Correcting from an older version corrects the BANK only.
    #
    # The curation set holds the decisions people have made since that
    # version, and rewriting it from a bank version they have moved on from
    # would discard them. The curation set is a workbench with owners;
    # picking a version out of a dropdown is not a mandate to reset it.
    cur_v = (offer_versions or {}).get("current_version")
    touch_set = bool(gid) and (from_version is None or from_version == cur_v)
    if gid and not touch_set:
        out["set_skipped"] = (
            "Reading v%s rather than the current v%s, so only the banked "
            "set is corrected. The curation set holds the decisions made "
            "since v%s and is left exactly as it is."
            % (from_version, cur_v, from_version))

    try:
        # The curation set first on a dry run, because it is the one that
        # can refuse for a reason worth seeing before anything is written.
        if touch_set:
            out["set"] = CURATE.retime(
                gid, kind, mapping, retimemod.TRUE, retimemod.CONCAT, sha,
                dry_run=not do_apply, who=who)
        out["entry"] = BANK.retime(
            entry_id, mapping, retimemod.TRUE, retimemod.CONCAT, sha,
            dry_run=not do_apply, by=who, from_version=from_version)
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400

    if (out.get("set") or {}).get("error") or (out.get("entry") or {}).get("error"):
        out["ok"] = False

    if do_apply and out["ok"]:
        STORE.record_activity([{
            "action": "events.retime",
            "detail": {"entry": entry_id, "gid": gid, "kind": kind,
                       "from": retimemod.CONCAT, "to": retimemod.TRUE,
                       "from_version": from_version,
                       "set_touched": touch_set,
                       "gap_map_sha": sha,
                       "n": (out.get("entry") or {}).get("moved"),
                       "version": (out.get("entry") or {}).get("version"),
                       "shift_max_ms": (out.get("entry") or {}).get(
                           "shift_max_ms")},
        }])
    return jsonify(out)


@app.route("/api/session/manifest", methods=["POST"])
def api_session_manifest():
    """A CSV row per session -- the table people paste into a methods table."""
    body = request.get_json(force=True) or {}
    rows = body.get("rows") or []
    text = extras.to_csv(rows, body.get("columns"))
    name = body.get("name") or "sessions.csv"
    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="Manifests")
    except Exception:
        saved = None
    headers = {"Content-Disposition": 'attachment; filename="%s"' % name}
    if saved:
        headers["X-Barry-Output"] = saved["rel"]
    return Response(text, mimetype="text/csv", headers=headers)


# ==========================================================================
# Recording overview -- the viewer's minimap strip
# ==========================================================================
@app.route("/api/csc/overview", methods=["POST"])
def api_csc_overview():
    body = request.get_json(force=True) or {}
    sess, err = _body_session(body)
    if err:
        return jsonify(err), 400
    bins = int(body.get("bins") or extras.OVERVIEW_BINS)
    # Two profiles off one route, because they are two answers to the same
    # question -- what is where in this recording -- drawn on the same strip.
    # 'amplitude' is the cheap one (a 0.35 s probe per bin) and stays the
    # default so the strip appears immediately; 'band' reads the channel
    # right through at 250 Hz and is asked for separately, once somebody
    # wants it.
    if (body.get("profile") or "amplitude") == "band":
        band = body.get("band") or {}
        try:
            res = extras.band_profile(
                sess, channel=body.get("channel"), bins=bins,
                lo=float(band.get("lo", extras.BAND_DEFAULT[0])),
                hi=float(band.get("hi", extras.BAND_DEFAULT[1])),
                measure=body.get("measure") or "abs")
        except Exception as exc:
            return fail("csc/overview band", exc, 400,
                        {"path": body.get("path"), "band": band})
        return jsonify(res)
    try:
        res = extras.overview(sess, channel=body.get("channel"), bins=bins)
    except Exception as exc:
        return fail("csc/overview", exc, 400, {"path": body.get("path")})
    return jsonify(res)


# ==========================================================================
# Errors: grouping and triage
# ==========================================================================
# ==========================================================================
# The JSON shards, as a backup you can look at
#
# Supabase is the primary route now. This is the redundancy: the copy that
# survives an unreachable database, the copy that holds the version
# snapshots that are too large to send, and the copy a fresh `git clone`
# arrives with. A backup nobody can inspect is a backup nobody trusts.
# ==========================================================================
# What each folder under GUI_logs is for, so the list reads as something
# other than a directory dump.
_SHARD_WHAT = {
    "activity": "every action, per machine per day",
    "errors": "the error log, per machine per day",
    "runs": "what was run, with its parameters",
    "sessions": "the recording registry",
    "curation": "curation sets and every decision in them",
    "event_bank": "banked entries and their version snapshots",
    "layers": "StrataScope layer sheets",
    "mice": "the colony",
    "prefs": "profiles, this computer's name, preferences",
    "presets": "saved filter and analysis presets",
    "results": "the figure catalogue",
    "storyboards": "decks",
    "feedback": "reports filed from the interface",
    "tombstones": "what has been deleted, so a delete travels",
}

# Enough to read a shard, not enough to stream a gigabyte into a browser.
SHARD_MAX = 400_000


def _shard_root():
    return LOGS_DIR


@app.route("/api/backup/json")
def api_backup_json():
    """What the redundancy copy holds, by folder and by file."""
    root = _shard_root()
    groups = []
    total_files = total_bytes = 0
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        # `.cache` and friends are Jarvis's own working files, not a copy of
        # anything -- listing them as part of the backup invites somebody to
        # treat them as one.
        if name.startswith("."):
            continue
        files = []
        for fn in sorted(os.listdir(folder)):
            full = os.path.join(folder, fn)
            if not os.path.isfile(full):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            # `base@machine.json` -- the shard naming. Split so the list can
            # say whose a file is, which is the whole point of sharding.
            stem = fn.rsplit(".", 1)[0]
            base, _, machine = stem.partition("@")
            files.append({
                "name": fn, "base": base or stem,
                "machine": machine or None,
                "mine": machine == shards.machine_id(),
                "bytes": st.st_size,
                "at": datetime.datetime.fromtimestamp(
                    st.st_mtime).astimezone().isoformat(timespec="seconds"),
            })
            total_files += 1
            total_bytes += st.st_size
        if not files:
            continue
        files.sort(key=lambda f: f["at"], reverse=True)
        groups.append({
            "folder": name,
            "what": _SHARD_WHAT.get(name),
            "n": len(files),
            "bytes": sum(f["bytes"] for f in files),
            "machines": sorted({f["machine"] for f in files if f["machine"]}),
            "files": files,
        })
    groups.sort(key=lambda g: -g["bytes"])
    return jsonify({
        "ok": True, "root": root,
        "folders": groups,
        "files": total_files, "bytes": total_bytes,
        # Said here rather than left to be inferred: this is the backup, and
        # what it is a backup OF is the shared database.
        "role": ("The redundancy copy. Supabase is the primary route; this "
                 "is what survives an unreachable database, what holds the "
                 "version snapshots that are too large to send, and what a "
                 "fresh clone of the repository arrives with."),
    })


@app.route("/api/backup/json/<folder>/<name>")
def api_backup_json_one(folder, name):
    """One shard, as it is on disk.

    Read-only, and pinned inside GUI_logs: the file name comes from a URL,
    so it is checked against the resolved path rather than trusted to be
    free of "..".
    """
    root = os.path.abspath(_shard_root())
    full = os.path.abspath(os.path.join(root, folder, name))
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        return jsonify({"ok": False, "error": "No such shard."}), 404
    try:
        size = os.path.getsize(full)
        with io.open(full, encoding="utf-8", errors="replace") as fh:
            text = fh.read(SHARD_MAX + 1)
    except OSError as exc:
        return jsonify({"ok": False, "error": str(exc)[:200]}), 500
    clipped = len(text) > SHARD_MAX
    if clipped:
        text = text[:SHARD_MAX]
    pretty = text
    try:
        # JSONL -- one record per line -- in the day logs; a single object
        # everywhere else. Both are shown as they are, only re-indented.
        if not clipped:
            if text.lstrip().startswith("{") and "\n{" in text:
                rows = [json.loads(l) for l in text.splitlines() if l.strip()]
                pretty = json.dumps(rows, indent=1)[:SHARD_MAX]
            else:
                pretty = json.dumps(json.loads(text), indent=1)[:SHARD_MAX]
    except Exception:                                    # noqa: BLE001
        pretty = text                    # unparseable is worth seeing raw
    return jsonify({
        "ok": True, "folder": folder, "name": name,
        "bytes": size, "clipped": clipped, "text": pretty,
    })


@app.route("/api/errors/client", methods=["POST"])
def api_errors_client():
    """A fault the interface noticed about itself.

    JS errors have always gone into the activity log and nowhere else, so
    the Errors page -- the place somebody actually looks -- never showed
    them. This is the way in.

    `where` is prefixed with "ui/" so a browser fault is never mistaken for
    a server one at a glance, and the traceback slot carries whatever stack
    the browser had.
    """
    body = request.get_json(force=True, silent=True) or {}
    where = str(body.get("where") or "unknown")[:120]
    message = str(body.get("message") or "")[:2000]
    if not message:
        return jsonify({"ok": False, "error": "Nothing to report."}), 400
    ctx = body.get("context")
    rec = STORE.record_error(
        "ui/" + where, message,
        str(body.get("stack") or "")[:8000] or None,
        ctx if isinstance(ctx, dict) else {"detail": ctx})
    return jsonify({"ok": True, "id": (rec or {}).get("id")})


# Which machines have been archived, and when that was last asked.
#
# The flag lives in Supabase (migration 10) because two people archiving two
# different computers through a last-write-wins pref would each undo the
# other. Cached for a minute: it is read on every error list and changes
# about twice a year.
_ARCHIVED_SEEN = {"at": 0.0, "ids": frozenset()}


def _archived_machines(max_age=60.0):
    """The ids of computers taken off the lists, or an empty set."""
    now = time.time()
    if now - _ARCHIVED_SEEN["at"] < max_age:
        return _ARCHIVED_SEEN["ids"]
    ids = frozenset()
    if CLOUD.cloud.configured:
        try:
            rows = CLOUD.cloud.select(
                "machines", query="archived=is.true&select=id", limit=500)
            ids = frozenset(str(r.get("id")) for r in rows if r.get("id"))
        except Exception:                            # noqa: BLE001
            # An unreachable database must not empty the error feed, and it
            # must not hide anything either: no answer means no filtering.
            ids = _ARCHIVED_SEEN["ids"]
    _ARCHIVED_SEEN["at"] = now
    _ARCHIVED_SEEN["ids"] = ids
    return ids


def _drop_archived(recs, want):
    """Rows from archived computers, unless asked for all of them.

    Returns (kept, hidden_count, ids). Matched on `shard` -- the id --
    because `machine` is the friendly name and this lab has four names in
    its logs for three computers.
    """
    if want == "all":
        return recs, 0, frozenset()
    gone = _archived_machines()
    if not gone:
        return recs, 0, gone
    def retired(rec):
        shard = str(rec.get("shard") or "")
        if shard:
            # A row that knows which computer wrote it is identified by
            # that and nothing else.
            return shard in gone
        # And one that does not falls back to the friendly name -- which is
        # what `host_of` does to decide the identity in the first place. The
        # two used to disagree, so a name-only machine could be archived and
        # its rows stayed.
        return str(rec.get("machine") or "") in gone

    kept = [r for r in recs if not retired(r)]
    return kept, len(recs) - len(kept), gone


@app.route("/api/errors/export")
def api_errors_export():
    """Every unresolved error, with the activity around each occurrence.

    A traceback says what broke; the actions before it say why. So each
    occurrence is printed with the log either side of it, on one clock, in
    one file -- which is the thing somebody can actually read through when
    a dozen faults need clearing at once.

    `?machines=all` includes archived computers, `?days=N` limits how far
    back to look, `?all=1` includes the ones already marked resolved.
    """
    want_all = request.args.get("all") == "1"
    try:
        days = int(request.args.get("days") or 0)
    except (TypeError, ValueError):
        days = 0

    recs = STORE.list_errors(limit=4000)
    recs, hidden_n, hidden_ids = _drop_archived(
        recs, request.args.get("machines") or "active")
    if days > 0:
        cut = time.time() - days * 86400
        recs = [r for r in recs
                if (extras.moment_key(r.get("at")) or 0) >= cut]

    book = STORE.resolved_errors()
    acts = STORE.list_activity(limit=8000)
    # Oldest first, so "what happened around this" can be sliced by time.
    acts = sorted(acts, key=lambda a: extras.moment_key(a.get("at")))

    # Group by the same signature the errors view groups on: where it
    # happened plus the first line of what it said.
    groups = {}
    for r in recs:
        sig = "%s | %s" % (r.get("where") or "?",
                           str(r.get("message") or "").split("\n")[0][:120])
        groups.setdefault(sig, []).append(r)

    def resolved(sig, rows):
        mark = (book or {}).get(sig) or {}
        if not mark:
            return False
        return all(extras.marked_after(r.get("at"), mark.get("at"))
                   for r in rows)

    live = [(sig, rows) for sig, rows in groups.items()
            if want_all or not resolved(sig, rows)]
    live.sort(key=lambda kv: max(extras.moment_key(r.get("at"))
                                 for r in kv[1]), reverse=True)

    sysdesc = sysinfo.describe()
    L = []
    L.append("Jarvis -- open errors, with the log around them")
    L.append("generated   " + time.strftime("%Y-%m-%d %H:%M:%S"))
    L.append("machine     %s / %s" % (sysdesc.get("hostname"),
                                      shards.machine_id()))
    L.append("version     %s" % (NOTES.read().get("version")
                                 if NOTES else "?"))
    L.append("scope       %d group(s) %s, from %d error(s) on record"
             % (len(live), "including resolved" if want_all else "open",
                len(recs)))
    if hidden_n:
        L.append("excluded    %d from archived computer(s): %s"
                 % (hidden_n, ", ".join(sorted(hidden_ids))))
    L.append("")
    L.append("Each group below is one fault. Under each occurrence is what "
             "this machine")
    L.append("was doing either side of it -- the traceback says what broke, "
             "the actions")
    L.append("say why.")

    for i, (sig, rows) in enumerate(live[:60], 1):
        rows = sorted(rows, key=lambda r: extras.moment_key(r.get("at")),
                      reverse=True)
        machines = sorted({str(r.get("machine") or r.get("shard") or "?")
                           for r in rows})
        L.append("")
        L.append("=" * 74)
        L.append("%d/%d  %s  x%d" % (i, min(len(live), 60),
                                     rows[0].get("where") or "?", len(rows)))
        L.append("=" * 74)
        L.append("first seen  %s" % (rows[-1].get("at") or "?"))
        L.append("last seen   %s" % (rows[0].get("at") or "?"))
        L.append("machines    %s" % ", ".join(machines))
        L.append("")
        L.append(str(rows[0].get("message") or "").strip()[:2000])

        ctx = rows[0].get("context")
        if isinstance(ctx, dict) and ctx:
            L.append("")
            L.append("context")
            for k in sorted(ctx):
                L.append("    %-16s %s" % (k, str(ctx[k])[:200]))

        tb = rows[0].get("detail") or rows[0].get("stack")
        if tb:
            L.append("")
            L.append("traceback")
            for line in str(tb).strip().split("\n")[-24:]:
                L.append("    " + line[:200])

        for r in rows[:3]:
            when = extras.moment_key(r.get("at"))
            L.append("")
            L.append("--- around %s on %s ---"
                     % (r.get("at") or "?",
                        r.get("machine") or r.get("shard") or "?"))
            near = [a for a in acts
                    if abs((extras.moment_key(a.get("at")) or 0) - when) <= 120]
            if not near:
                L.append("    (nothing in the activity log within two "
                         "minutes)")
                continue
            # Twelve either side, and the error in its place among them.
            before = [a for a in near
                      if (extras.moment_key(a.get("at")) or 0) <= when][-12:]
            after = [a for a in near
                     if (extras.moment_key(a.get("at")) or 0) > when][:12]
            for a in before:
                L.append("    %+6.1fs  %-24s %s"
                         % ((extras.moment_key(a.get("at")) or 0) - when,
                            a.get("action") or "?",
                            json.dumps(a.get("detail") or {},
                                       default=str)[:120]))
            L.append("    %+6.1fs  %s" % (0.0, ">>> THE ERROR <<<"))
            for a in after:
                L.append("    %+6.1fs  %-24s %s"
                         % ((extras.moment_key(a.get("at")) or 0) - when,
                            a.get("action") or "?",
                            json.dumps(a.get("detail") or {},
                                       default=str)[:120]))

    if len(live) > 60:
        L.append("")
        L.append("... and %d more group(s), not printed." % (len(live) - 60))

    text = "\n".join(L) + "\n"
    name = "jarvis-open-errors-%s.txt" % time.strftime("%Y%m%d_%H%M%S")
    return Response(text, mimetype="text/plain; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="%s"' % name})


@app.route("/api/errors/grouped")
def api_errors_grouped():
    recs = STORE.list_errors(limit=int(request.args.get("limit", 600)),
                             day=request.args.get("day") or None)
    # A retired computer's faults are not this week's problem.
    recs, hidden_n, hidden_ids = _drop_archived(
        recs, request.args.get("machines") or "active")
    book = STORE.resolved_errors()

    # An occurrence counts as resolved only if it happened BEFORE somebody
    # said so. Marking a signature resolved used to hide it forever, so a bug
    # that came back after being fixed was filed under a resolved group and
    # never shown again -- which is the one case where you most want to see
    # it. A recurrence reopens the group and says when it started again.
    # Split per machine unless asked not to. The same fault in two places
    # is two things to chase, and folding them said only "twice".
    per_machine = request.args.get("fold") != "fault"

    for r in recs:
        # A mark for this machine specifically, or one for the fault
        # everywhere. Machine-scoped wins where both exist: it is the more
        # specific statement, and "fixed on the rig" is a real thing to say.
        mark = (book.get(extras.mark_key(extras.signature(r),
                                         extras.host_of(r)))
                or book.get(extras.signature(r)))
        # Compared as times, not as text: an error pulled from the shared
        # table is UTC and a mark written here is local, so the string test
        # this replaces called an error newer than the mark that resolved
        # it and left it red for good.
        r["resolved"] = bool(mark) and extras.marked_after(
            r.get("at"), mark.get("at"))

    groups = extras.group_errors(recs, per_machine=per_machine)

    # The registered name for each computer, keyed on the same shard id the
    # groups are keyed on. Preferred over the newest label in the log: the
    # log carries whatever was last typed into a profile's `device` field,
    # and on this store that is a typo ("Strawbarrry") which two different
    # computers have both been set to.
    known = {}
    if CLOUD.cloud.configured:
        try:
            for m in (CLOUD.cloud.select("machines", limit=200) or []):
                if m.get("id") and m.get("hostname"):
                    known[m["id"]] = m["hostname"]
        except Exception:                                # noqa: BLE001
            known = {}
    # ...except for this computer, which knows its own name better than the
    # table does. `machines.hostname` is only as fresh as the last successful
    # push, so a rename that has not been pushed yet -- and somebody renaming
    # a machine while the sync is failing is exactly that -- left every error
    # here labelled with the name before last, with nothing on screen saying
    # why. The local record changes the moment the name is saved.
    my_id = shards.machine_id()
    my_name = ((STORE.provenance() or {}).get("machine") or "").strip()
    if my_id and my_name:
        known[my_id] = my_name

    for g in groups:
        mid = g.get("machine")
        if mid and known.get(mid):
            g["machine_label"] = _machine_label(known[mid], mid)
        # Whether this row is a computer or only a name. A record written
        # before the shard field existed can only be filed under its label,
        # and a label is not unique -- so the row says so rather than
        # implying an identity it does not have.
        g["machine_known"] = bool(mid and mid in known)
        g["machine_is_shard"] = bool(
            mid and extras.real_host(mid) and "-" in str(mid))
        mark = (book.get(g["key"]) if g.get("machine") else None)
        scope = "machine" if mark else "everywhere"
        if not mark:
            mark = book.get(g["signature"])
        if not mark:
            continue
        g["resolved_scope"] = scope
        g["resolved_at"] = mark.get("at")
        g["resolved_by"] = mark.get("by")
        g["resolved_note"] = mark.get("note")
        if not g["resolved"]:
            # It was closed and has happened again since.
            g["reopened"] = True
            # "Since the mark" compared as a time, for the same reason the
            # resolved test above is: an error from the shared table is UTC
            # and a mark written here is local, so as text a row from this
            # afternoon can sort either side of a mark from this evening.
            g["reopened_at"] = next(
                (r.get("at") for r in reversed(g["records"])
                 if not extras.marked_after(r.get("at"), mark.get("at"))),
                g.get("last"))
    return jsonify({"ok": True, "groups": groups, "days": STORE.error_days(),
                    "total": len(recs),
                    "unresolved": sum(1 for g in groups if not g["resolved"]),
                    "reopened": sum(1 for g in groups if g.get("reopened")),
                    # Said, not silently applied: a list that hides rows
                    # without saying so is a list nobody can trust.
                    "hidden_archived": hidden_n,
                    "archived_machines": sorted(hidden_ids)})


@app.route("/api/errors/resolve", methods=["POST"])
def api_errors_resolve():
    body = request.get_json(force=True) or {}
    sigs = body.get("signatures") or ([body["signature"]]
                                      if body.get("signature") else [])
    resolved = body.get("resolved", True)
    # Where the fix applies. Without a machine this behaves exactly as it
    # always did -- the fault is closed everywhere -- which is what every
    # existing mark means and what "Resolved" should keep meaning by
    # default. With one, the claim is only about that computer.
    machine = body.get("machine") or None
    for sig in sigs:
        STORE.resolve_error(extras.mark_key(sig, machine),
                            bool(resolved), body.get("note"))
    STORE.record_activity([{
        "action": "error.resolve",
        "detail": {"n": len(sigs), "resolved": bool(resolved),
                   "machine": machine, "note": body.get("note")},
    }])
    return jsonify({"ok": True, "resolved": STORE.resolved_errors()})


# How much of the run goes into a report when nobody says otherwise. Ten
# minutes is the window in which somebody notices something and files it;
# longer stops being context and starts being a log dump.
REPORT_WINDOW_S = 600


def _recent_window(seconds=REPORT_WINDOW_S):
    """What happened in the last `seconds`, for attaching to a report.

    The person filing cannot know which lines matter, so this is gathered
    for them rather than asked for: the actions they took, the errors that
    were recorded, and the requests the server actually served.
    """
    import datetime as _dt
    cutoff = _dt.datetime.now().astimezone() - _dt.timedelta(seconds=seconds)

    def recent(rows, key="at"):
        out = []
        for r in rows or []:
            stamp = str(r.get(key) or "")
            try:
                when = _dt.datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.astimezone()
            if when >= cutoff:
                out.append(r)
        return out

    try:
        acts = recent(STORE.list_activity(limit=400))
    except Exception:                                     # noqa: BLE001
        acts = []
    try:
        errs = recent(STORE.list_errors(limit=200))
    except Exception:                                     # noqa: BLE001
        errs = []
    reqs = []
    try:
        # The server's own view of what it served.
        reqs = (extras.TRACE.recent(limit=120) or [])
    except Exception:                                     # noqa: BLE001
        reqs = []
    return {"window_s": seconds, "actions": acts, "errors": errs,
            "requests": reqs}


# How much of the log an error comes with. Five minutes before, because
# that is where the cause is, and one after, because "and then it recovered"
# and "and then everything broke" are different bugs.
CONTEXT_BEFORE_S = 300
CONTEXT_AFTER_S = 60


def _ctx_when(at):
    """One timestamp as an aware datetime, or None.

    Everything here compares MOMENTS, never the strings that spell them.
    The local activity log writes local time with its offset (-04:00) and
    the cloud copy writes UTC (+00:00), so a lexicographic comparison
    between the two is meaningless -- it silently dropped every cloud row
    from the window, which looked like "the other machine logged nothing"
    rather than like a bug.
    """
    text = str(at or "").strip().replace("Z", "+00:00")
    try:
        when = datetime.datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when


def _ctx_window(at):
    """(from, to) as aware datetimes around a timestamp."""
    when = _ctx_when(at)
    if when is None:
        return None, None
    return (when - datetime.timedelta(seconds=CONTEXT_BEFORE_S),
            when + datetime.timedelta(seconds=CONTEXT_AFTER_S))


@app.route("/api/errors/context", methods=["POST"])
def api_errors_context():
    """What was happening around one error.

    Local first: this machine's own activity log is on disk and needs no
    network. Then the cloud, which is the only place another machine's
    activity can be read from -- the log is push-only by design, because
    copying somebody else's actions into this machine's day file would be
    writing their history into a file that says it is mine.

    Both sources are merged and de-duplicated by id, so a run with the cloud
    unreachable degrades to "what this machine remembers" rather than to an
    error.
    """
    body = request.get_json(force=True, silent=True) or {}
    at = body.get("at")
    machine = body.get("machine")
    if not at:
        return jsonify({"ok": False, "error": "Need the time of the error."}), 400
    lo, hi = _ctx_window(at)
    if lo is None:
        return jsonify({"ok": False, "error": "Could not read that time."}), 400

    rows, seen = [], set()

    def take(entry, where):
        key = entry.get("id") or (str(entry.get("at")) + str(entry.get("action")))
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "at": entry.get("at"),
            "action": entry.get("action"),
            "detail": entry.get("detail"),
            "view": entry.get("view"),
            "machine": entry.get("machine"),
            "user": entry.get("git_user") or entry.get("user"),
            "from": where,
        })

    # This machine's own log. Cheap, offline, and the common case: most
    # errors are read on the machine that had them.
    try:
        for entry in (STORE.list_activity(limit=4000) or []):
            when = _ctx_when(entry.get("at"))
            if when is not None and lo <= when <= hi:
                take(entry, "local")
    except Exception:                                    # noqa: BLE001
        pass

    # And the cloud, for everyone else's.
    cloud_error = None
    if CLOUD.cloud.configured:
        try:
            q = "at=gte.%s&at=lte.%s&order=at.asc" % (
                lo.isoformat(), hi.isoformat())
            if machine:
                q += "&machine=eq.%s" % machine
            for entry in (CLOUD.cloud.select("activity", query=q,
                                             limit=2000) or []):
                # Filtered again on this side. PostgREST compares the
                # moments correctly, but a row that slipped through a
                # paging edge would otherwise be reported as being in a
                # window it is not in.
                when = _ctx_when(entry.get("at"))
                if when is not None and lo <= when <= hi:
                    take(entry, "cloud")
        except Exception as exc:                         # noqa: BLE001
            # Not fatal: what this machine remembers is still worth showing.
            cloud_error = str(exc)[:200]

    if machine:
        rows = [r for r in rows
                if not r.get("machine") or r.get("machine") == machine]
    # Sorted on the moment, for the same reason: two machines' strings do
    # not order against each other even when their times do.
    rows.sort(key=lambda r: _ctx_when(r.get("at"))
              or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))

    # Other errors in the same window, because one fault often arrives as
    # six and the first of them is the one worth reading.
    nearby = []
    try:
        for err in (STORE.list_errors(limit=2000) or []):
            when = _ctx_when(err.get("at"))
            if when is not None and lo <= when <= hi:
                nearby.append({
                    "at": err.get("at"), "where": err.get("where"),
                    "message": err.get("message"),
                    "machine": err.get("machine"),
                })
    except Exception:                                    # noqa: BLE001
        pass
    nearby.sort(key=lambda r: _ctx_when(r.get("at"))
                or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))

    return jsonify({
        "ok": True, "at": at, "machine": machine,
        "from": lo.isoformat(), "to": hi.isoformat(),
        "before_s": CONTEXT_BEFORE_S, "after_s": CONTEXT_AFTER_S,
        "actions": rows, "errors": nearby,
        "cloud_error": cloud_error,
    })


# ==========================================================================
# Sync progress
#
# A full sync is three or four seconds and the registry read alone is five,
# and the button said nothing for all of it -- so the honest reading of the
# interface was that nothing had happened. The loop already accepts an
# `on_progress`; nothing was listening.
#
# Held in memory rather than written down: it describes a sync that is
# happening now, and a progress record that outlives the thing it describes
# is worse than none.
# ==========================================================================
def _q(value):
    """A value safe to drop into a PostgREST filter.

    Bare, not quoted. Double quotes are how PostgREST is told that a value
    contains reserved characters, and they cannot be used here: `_safe_query`
    percent-encodes them on the way out, so `machine=neq."Bluebarry"` arrives
    as `machine=neq.%22Bluebarry%22` and is compared against a string that
    includes the quote marks. It is never equal, so `neq` silently matches
    every row -- measured as the same 1,000 rows and the same count as no
    filter at all.

    `_safe_query` already encodes the spaces and the characters a URL cannot
    carry, which is what a name like "Rig 2 (Barry lab)" actually needs. A
    comma in a hostname would still confuse the filter; no machine in this
    lab has one, and a wrong count is the failure mode rather than a wrong
    row, so this is not worth a quoting scheme that does not work.
    """
    return str(value).replace(",", " ")


def _alias(name):
    """A name folded onto the person it belongs to, via the roster."""
    try:
        for row in ((PEOPLE.book.read("people") or {}).get("added") or []):
            keep = row.get("name") or row.get("id")
            for other in (row.get("aliases") or []):
                if str(other).strip().lower() == str(name).strip().lower():
                    return keep
    except Exception:                                    # noqa: BLE001
        pass
    return name


def _this_host():
    """What this machine calls itself, as the logs spell it.

    The activity and error rows carry the hostname, not the machine id, so
    filtering "not me" has to compare the same thing they store.
    """
    try:
        return (STORE.provenance() or {}).get("machine")
    except Exception:                                    # noqa: BLE001
        return None


_sync_step = {"at": None, "phase": None, "table": None, "n": 0,
              "done": 0, "of": 0, "running": False}


def _sync_note(phase, table=None, n=0, of=0, done=None):
    _sync_step.update({
        "at": cloudmod.now(), "phase": phase, "table": table, "n": n,
        "of": of or _sync_step.get("of") or 0,
        "running": phase != "idle",
    })
    if done is not None:
        _sync_step["done"] = done
    # The denominator is an estimate -- counting exactly would mean walking
    # every table first, which is most of the work the bar is reporting on --
    # and some tables are fetched twice (curation is a set list and an event
    # list). So it stretches rather than letting the bar run past its end,
    # which reads as a bug in a way that a slightly slow bar does not.
    if _sync_step["done"] > _sync_step["of"]:
        _sync_step["of"] = _sync_step["done"]


# Which migration adds which column, so the answer is "run this file"
# rather than "a column is missing". Only the ones added after the first
# release need saying; anything older than 05 has been run everywhere for
# months.
COLUMN_MIGRATIONS = {
    "hemisphere": "06_hemisphere.sql",
    "hemisphere_source": "06_hemisphere.sql",
    "ripple_channel": "07_reference_channels.sql",
    "fissure_channel": "07_reference_channels.sql",
    "hilus_channel": "07_reference_channels.sql",
    "extraction_note": "07_reference_channels.sql",
    "needs_processing": "07_reference_channels.sql",
    "reference_channels_source": "07_reference_channels.sql",
    "aliases": "08_people_aliases.sql",
    "archived": "09_people_archived.sql",
    "versions": "11_bank_versions.sql",
    "version": "11_bank_versions.sql",
    "orcid": "12_people_orcid.sql",
    "is_open": "13_layer_bench.sql",
    "opened_at": "13_layer_bench.sql",
    "opened_by": "13_layer_bench.sql",
    # A whole table, not a column -- but the probe asks for a column OF a
    # table, and a missing table answers "does not exist" the same way a
    # missing column does. So asking for this one column is how a machine
    # finds out that `bank_snapshots` has never been created.
    "sha256": "14_bank_snapshots.sql",
    # Same trick again: a missing table answers a column probe exactly as a
    # missing column does, so asking for this one is how a machine finds out
    # that health_checks has never been created.
    "gap_map_sha": "15_health_checks.sql",
    # `results` learning what it is of, and `runs` learning which code made
    # it. Two columns rather than one because they are on different tables,
    # and a machine can have run half a migration.
    "recorded_on": "16_results_museum.sql",
    "recipe": "16_results_museum.sql",
    # And the third trick of the same kind: tool_results is a whole table,
    # and a column probe is how a machine finds out it was never created.
    "params_hash": "16_results_museum.sql",
}


# Answers from the schema probe below, cached: {(table, column): present}.
# A schema does not change while nobody is looking, and this is read by a
# dialog rather than by a loop.
_SCHEMA_SEEN = {}

# Which table each migration column belongs to, so the probe knows where to
# look. Kept beside COLUMN_MIGRATIONS rather than derived from it: a column
# name alone does not say which table wants it.
COLUMN_TABLES = {
    "hemisphere": "sessions",
    "hemisphere_source": "sessions",
    "ripple_channel": "sessions",
    "fissure_channel": "sessions",
    "hilus_channel": "sessions",
    "extraction_note": "sessions",
    "needs_processing": "sessions",
    "reference_channels_source": "sessions",
    "aliases": "people",
    "archived": "people",
    "versions": "bank_entries",
    "version": "bank_entries",
    "orcid": "people",
    "is_open": "layer_sheets",
    "opened_at": "layer_sheets",
    "opened_by": "layer_sheets",
    "sha256": "bank_snapshots",
    "gap_map_sha": "health_checks",
    "recorded_on": "results",
    "recipe": "runs",
    "params_hash": "tool_results",
}


def _probe_schema():
    """Which migration columns the database is missing, asked directly.

    The alternative is waiting to be refused, and a refusal only happens
    when something changes: `sessions` is pushed when a recording changes, so
    a machine could sit for days with a migration un-run and never be told.
    """
    if not CLOUD.cloud.configured:
        return {}
    missing = {}
    for col, table in COLUMN_TABLES.items():
        key = (table, col)
        if key not in _SCHEMA_SEEN:
            try:
                CLOUD.cloud.select(table, query="select=%s" % col, limit=1)
                _SCHEMA_SEEN[key] = True
            except Exception as exc:                     # noqa: BLE001
                # Only a missing COLUMN counts. A table that is not there at
                # all, or a network that is down, is a different problem and
                # saying "run this migration" about it would be a guess.
                text = str(exc)
                _SCHEMA_SEEN[key] = not ("42703" in text
                                         or "does not exist" in text)
        if not _SCHEMA_SEEN[key]:
            missing.setdefault(table, set()).add(col)
    return missing


@app.route("/api/sync/pending-migrations")
def api_pending_migrations():
    """Columns this machine has tried to send and the database has not got.

    Worth a route of its own because the consequence used to be invisible
    and total: `sessions` is first in the push order, so one column it did
    not recognise aborted the push before any other table was reached, and
    the lab simply stopped syncing. It degrades now -- the field is dropped
    and the rest goes up -- which makes saying so the only way anybody finds
    out.
    """
    # What was actually refused, plus what the schema says it has not got.
    # The first is proof, the second is warning; both go in the same list
    # because the consequence is identical.
    found = {}
    for table, cols in (cloudmod.PENDING_COLUMNS or {}).items():
        found.setdefault(table, set()).update(cols)
    for table, cols in _probe_schema().items():
        found.setdefault(table, set()).update(cols)
    pend = {t: sorted(c) for t, c in found.items() if c}
    files = sorted({COLUMN_MIGRATIONS[c]
                    for cols in pend.values() for c in cols
                    if c in COLUMN_MIGRATIONS})
    unknown = sorted({c for cols in pend.values() for c in cols
                      if c not in COLUMN_MIGRATIONS})
    return jsonify({
        "ok": True,
        "pending": pend,
        "run": files,
        # A column nobody can name a file for is the more worrying case: it
        # means this machine is sending something no migration accounts for.
        "unaccounted": unknown,
        "note": ("Those fields are being dropped on the way up, so the rest "
                 "of the sync works. Run the file(s) in supabase/ and they "
                 "will travel on the next full push.") if pend else None,
    })


@app.route("/api/sync/progress")
def api_sync_progress():
    """Where a running sync has got to.

    Polled while the button spins. Cheap on purpose -- it reads a dict --
    because the alternative to a cheap poll is a spinner that lies.
    """
    return jsonify({"ok": True, "step": dict(_sync_step),
                    "last": dict(_cloud_last)})


@app.route("/api/devices/feed")
def api_devices_feed():
    """One machine's recent life: what it did, and what went wrong.

    Errors and actions interleaved rather than in two lists, because the
    useful shape is "these four things happened and then it broke". Per
    machine, because "the rig has been quiet since four" is a different
    observation from anything the combined list can show.

    The debug trace itself stays local -- it is this process's own request
    trail and is not collected from anywhere else -- so a remote machine's
    feed is its actions and its errors, which is what it actually publishes.
    """
    machine = request.args.get("machine") or None
    limit = int(request.args.get("limit", 120))
    if not CLOUD.cloud.configured:
        return jsonify({"ok": True, "configured": False, "feed": []})

    rows = []

    def pull(table, kind):
        q = ["order=at.desc"]
        if machine:
            q.append("machine=eq.%s" % machine)
        try:
            got = CLOUD.cloud.select(table, query="&".join(q),
                                     limit=limit) or []
        except Exception:                                # noqa: BLE001
            return
        for r in got:
            rows.append({
                "kind": kind,
                "at": r.get("at"),
                "machine": r.get("machine"),
                "user": r.get("git_user"),
                "what": (r.get("action") if kind == "action"
                         else r.get("where_") or r.get("where")),
                "detail": (r.get("detail") if kind == "action"
                           else r.get("message")),
                "view": r.get("view"),
            })

    pull("activity", "action")
    pull("errors", "error")
    rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    return jsonify({"ok": True, "configured": True,
                    "machine": machine, "feed": rows[:limit]})


@app.route("/api/digest")
def api_digest():
    """What changed since you last looked.

    The mark is per machine and stored in prefs, so "since I last looked"
    means what it says rather than "since midnight". Reading the digest does
    not move it -- `POST /api/digest/seen` does -- because a digest that
    clears itself the moment it is rendered cannot be read twice, and the
    first read is usually the one where you get interrupted.
    """
    since = request.args.get("since")
    if not since:
        try:
            since = (STORE.get_prefs() or {}).get("digest_seen") or None
        except Exception:                                # noqa: BLE001
            since = None
    if not since:
        # First run: a day, so it says something rather than everything --
        # and written down, so it stays put. Recomputing "a day ago" on every
        # read made the window slide, which meant two reads a second apart
        # covered two different days and "since I last looked" was really
        # "in the last 24 hours" until somebody pressed the button once.
        since = presencemod._iso_ago(86400)
        try:
            STORE.set_prefs({"digest_seen": since})
        except Exception:                                # noqa: BLE001
            pass

    mine = shards.machine_id()
    out = {"ok": True, "since": since, "machine": mine,
           "by_person": [], "by_kind": [], "sessions": [], "errors": 0,
           "n": 0, "configured": bool(CLOUD.cloud.configured)}
    if not CLOUD.cloud.configured:
        return jsonify(out)

    # This machine is excluded in the QUERY, not afterwards. Asking for the
    # newest two thousand rows and then discarding this machine's spends the
    # whole budget -- capped at a thousand by PostgREST -- on rows that do
    # not count: measured at 1,000 fetched and 8 kept, so the card said
    # "8 actions" where the answer was over a thousand.
    mine_q = ("&machine=neq.%s" % _q(_this_host())) if _this_host() else ""
    try:
        rows = CLOUD.cloud.select(
            "activity", query="at=gt.%s%s&order=at.desc" % (since, mine_q),
            limit=1000) or []
        # And the headline comes from a count, not from len(rows). A page is
        # not a total, and one that has been capped looks exactly like one
        # that has not.
        total = CLOUD.cloud.count(
            "activity", query="at=gt.%s%s" % (since, mine_q))
    except Exception as exc:                             # noqa: BLE001
        out["error"] = str(exc)[:200]
        return jsonify(out)

    people, kinds, sessions = {}, {}, {}
    for r in rows:
        # Belt and braces: the query already excludes this machine, and a row
        # with no machine at all should still not be attributed to it.
        if r.get("machine") and r.get("machine") == _this_host():
            continue
        who = r.get("git_user") or r.get("machine") or "somebody"
        # Folded through the roster's aliases, like the roster itself. The
        # activity log keeps whatever name the machine believed at the time
        # -- deliberately, it is a record of what happened -- so the folding
        # has to happen wherever it is read.
        who = _alias(who)
        people[who] = people.get(who, 0) + 1
        kind = str(r.get("action") or "").split(".")[0] or "other"
        kinds[kind] = kinds.get(kind, 0) + 1
        key = r.get("session_key")
        if key:
            slot = sessions.setdefault(key, {"key": key, "n": 0,
                                             "who": set(), "last": None})
            slot["n"] += 1
            slot["who"].add(who)
            # As a moment, not as text. These rows do not share an
            # offset -- what came from the shared table is UTC and what was
            # written here is local -- so the string test this replaces
            # could hold a row that is not the latest one.
            if not slot["last"] or extras.marked_after(slot["last"],
                                                       r.get("at")):
                slot["last"] = r.get("at")

    try:
        # Counted, and excluded in the query, for the same reason.
        out["errors"] = CLOUD.cloud.count(
            "errors", query="at=gt.%s%s" % (since, mine_q)) or 0
    except Exception:                                    # noqa: BLE001
        pass

    # The true total, with the breakdown computed from as much of it as one
    # page holds. Said out loud when those differ, rather than letting a
    # breakdown that adds up to less than the headline look like an
    # arithmetic mistake.
    seen = sum(people.values())
    out["n"] = total if isinstance(total, int) else seen
    out["counted"] = seen
    out["partial"] = bool(isinstance(total, int) and total > seen)
    # Which host it left out, by the name the LOG spells it. That is not the
    # name the device table uses -- provenance().machine is "Bluebarry" where
    # machines.hostname is "desktop-4h65ai7-d565" for the same computer --
    # and anything checking the exclusion has to compare the same one.
    out["excluded_host"] = _this_host()
    out["by_person"] = sorted(
        [{"who": k, "n": v} for k, v in people.items()], key=lambda x: -x["n"])
    out["by_kind"] = sorted(
        [{"kind": k, "n": v} for k, v in kinds.items()], key=lambda x: -x["n"])
    out["sessions"] = sorted(
        [{"key": s["key"], "n": s["n"], "who": sorted(s["who"]),
          "last": s["last"]} for s in sessions.values()],
        key=lambda x: -x["n"])[:12]
    return jsonify(out)


@app.route("/api/digest/seen", methods=["POST"])
def api_digest_seen():
    """Move the "last looked" mark to now. Only ever called deliberately."""
    stamp = cloudmod.now()
    try:
        STORE.set_prefs({"digest_seen": stamp})
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)[:200]}), 500
    return jsonify({"ok": True, "seen": stamp})


@app.route("/api/devices")
def api_devices():
    """Every machine that syncs here, and whether it still is.

    `machines.last_seen` is already a heartbeat -- the sync loop stamps it on
    every push -- so there is nothing new to write. What this adds is the
    reading: online or not, and whether it is actually sending anything,
    which are different questions. A machine can be reachable and have
    stopped logging.
    """
    if not CLOUD.cloud.configured:
        return jsonify({"ok": True, "configured": False, "devices": []})
    try:
        machines = CLOUD.cloud.select("machines", limit=200) or []
    except Exception as exc:                             # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)[:200]}), 502

    # The newest thing each machine has sent, per kind. Two small queries
    # rather than one per machine: the point is a table, and a table should
    # not cost a request per row.
    newest = {}
    for table, key in (("activity", "actions"), ("errors", "errors")):
        try:
            rows = CLOUD.cloud.select(
                table, query="order=at.desc", limit=600) or []
        except Exception:                                # noqa: BLE001
            rows = []
        for r in rows:
            who = r.get("machine")
            if not who:
                continue
            slot = newest.setdefault(who, {})
            if key not in slot:
                slot[key] = {"at": r.get("at"), "n": 0}
            slot[key]["n"] += 1

    mine = shards.machine_id()

    # Every name the logs mention, so the ones no machine claims can be
    # listed rather than silently dropped. The log stores friendly names and
    # those change: this lab has DESKTOP-4H65AI7, BarryLab, Strawbarrry and
    # Blackbarry on record alongside the three names currently in use.
    log_names = set(newest)
    claimed = set()

    # Rows that say only a name.
    #
    # The error feed groups by `host_of`, which is the shard when there is
    # one and the friendly name when there is not -- so a pre-shard row is
    # filed under a key like "Bluebarry" that is NOT any machine's id. That
    # key is offered in the picker, so it has to be offerable here too, or
    # four computers are filterable and unarchivable.
    #
    # Deliberately not folded into `unclaimed_names`: a device is called
    # Bluebarry, so the name reads as claimed there and disappears. And
    # folding it into that device would be a guess -- three computers in
    # this lab answer to Bluebarry, which is exactly why the row cannot be
    # attributed to one of them.
    name_only = {}
    try:
        ids = {str(m.get("id")) for m in machines if m.get("id")}
        for rec in (STORE.list_errors(limit=4000) or []):
            # Exactly the key the feed groups under.
            key = str(extras.host_of(rec) or "").strip()
            if not key or key == "unknown" or key in ids:
                continue
            # A shard id decodes: hostname slug, hyphen, four hex. A name
            # does not. NOT `if rec.get("shard")` -- that field holds a
            # friendly name on these rows, which is the whole reason they
            # end up as their own key.
            if extras.real_host(key) and "-" in key:
                continue
            name_only[key] = name_only.get(key, 0) + 1
    except Exception:                                    # noqa: BLE001
        name_only = {}

    out = []
    for m in machines:
        seen = presencemod._age_s(m.get("last_seen"))
        host = m.get("hostname")
        real = _real_host(m.get("id"))
        # What to call it. For every other machine that is the table, which
        # is the only thing here that has heard of them. For this one it is
        # the local record: the table is only as fresh as the last successful
        # push, so while the sync is down this row would keep showing the
        # name before last -- including in the panel somebody opens to rename
        # it. `host` stays what it was, because the counts below and the
        # also-known-as matching are keyed on the name the log rows carry.
        shown = host
        if m.get("id") == mine:
            shown = ((STORE.provenance() or {}).get("machine")
                     or "").strip() or host
        # Rows written under this machine's other names. Matched on the
        # friendly name or the real hostname and nothing looser -- a fuzzy
        # match here would have folded StrawBarry into Strawbarry, and they
        # are two people's computers.
        aka = sorted(
            n for n in log_names
            if n and n.lower() in {(host or "").lower(), (real or "").lower(),
                                   (shown or "").lower()} - {""}
            and n != shown)
        claimed.update(aka)
        for name in (host, shown):
            if name:
                claimed.add(name)
        # Keyed on the name being shown, not on the table's copy of it: rows
        # written since a rename carry the new name, and `aka` deliberately
        # leaves that one out.
        got = newest.get(shown) or {}
        # Counted under every name it has answered to.
        for other in aka:
            more = newest.get(other) or {}
            for key in ("actions", "errors"):
                if key in more and key not in got:
                    got = dict(got)
                    got[key] = more[key]
        out.append({
            "id": m.get("id"),
            "hostname": shown,
            # What to put on screen: "Bluebarry (DESKTOP-4H65AI7)".
            "label": _machine_label(shown, m.get("id")),
            # What the shared table still has, when this machine has been
            # renamed and the new name has not reached it. The panel says so
            # rather than showing two names and leaving it a mystery.
            "pushed_name": host if shown != host else None,
            "real_host": real,
            "also_known_as": aka,
            "archived": bool(m.get("archived")),
            "os": m.get("os"),
            "user": m.get("git_user"),
            "first_seen": m.get("first_seen"),
            "last_seen": m.get("last_seen"),
            "age_s": seen,
            # Online means "pushed recently". The sync loop pushes at least
            # once a minute, so a machine quiet for five has either been
            # closed or has stopped syncing -- and both of those are things
            # somebody would want to know.
            "online": seen is not None and seen <= 300,
            "is_me": m.get("id") == mine,
            "last_action_at": (got.get("actions") or {}).get("at"),
            "recent_actions": (got.get("actions") or {}).get("n") or 0,
            "last_error_at": (got.get("errors") or {}).get("at"),
            "recent_errors": (got.get("errors") or {}).get("n") or 0,
        })
    # Archived last, then by how recently they were heard from.
    out.sort(key=lambda d: (bool(d.get("archived")),
                            d.get("age_s") is None, d.get("age_s") or 0))
    return jsonify({
        "ok": True, "configured": True, "machine": mine,
        "machine_label": _machine_label(
            (STORE.provenance() or {}).get("machine"), mine),
        "devices": out,
        # Names in the logs that no machine in the table answers to -- an
        # older friendly name, or a computer that never registered. Reported
        # rather than guessed at: matching them by shape is how two people's
        # machines would get merged.
        "unclaimed_names": sorted(n for n in log_names
                                  if n and n not in claimed),
        # Keys the error feed offers that are names rather than computers.
        # Each carries how many rows are filed under it, because "25 errors
        # nobody can attribute" and "1" are different problems.
        "name_only_machines": [
            {"name": n, "n_errors": c,
             "archived": n in _archived_machines()}
            for n, c in sorted(name_only.items(),
                               key=lambda kv: (-kv[1], kv[0]))],
        # Labels that more than one computer answers to. The hazard, and the
        # reason the real hostname is shown in brackets: `machines.hostname`
        # is pushed from `provenance().machine`, which is the free-text
        # `device` field of a profile -- so it is whatever was last typed,
        # it changes, and nothing stops two machines being given the same
        # one. This lab has had exactly that.
        "ambiguous_labels": sorted(
            name for name, ids in _by_label(machines).items()
            if len(ids) > 1),
    })


# ==========================================================================
# What a computer is called, and what it actually is
#
# `machines.id` is `slug(platform.node())` plus a four-character hash of the
# MAC address, so it decodes the real computer name -- which the friendly
# name often is not. Bluebarry is DESKTOP-4H65AI7; StrawBarry is LCOM549913
# and Strawbarry is JarvisLAB, and those last two are different computers
# whose friendly names differ by the case of one letter.
#
# So a machine is shown as "Friendly (ACTUAL)" whenever the two differ. It
# is the difference between two rows somebody has to squint at and two rows
# that cannot be mistaken for each other.
# ==========================================================================
def _by_label(machines):
    """label -> the machine ids using it. Usually one each; not always."""
    out = {}
    for m in machines or []:
        name = (m.get("hostname") or "").strip().lower()
        if name and m.get("id"):
            out.setdefault(name, set()).add(m["id"])
    return out


def _my_names():
    """Every spelling this computer answers to.

    Its id, the label it is called now, the hostname it reports, and the
    older labels the logs have it under. Used wherever "did THIS machine do
    this" has to be answered against records keyed on a label that changes.
    """
    out = set()
    mid = shards.machine_id()
    out.add(mid)
    real = _real_host(mid)
    if real:
        out.add(real)
    try:
        got = DEVICE.get(PROFILE) or {}
        for k in ("name", "real"):
            if got.get(k):
                out.add(got[k])
    except Exception:                                    # noqa: BLE001
        pass
    try:
        if (STORE.provenance() or {}).get("machine"):
            out.add(STORE.provenance()["machine"])
    except Exception:                                    # noqa: BLE001
        pass
    # And whatever the device table says this id has been called.
    if CLOUD.cloud.configured:
        try:
            for m in (CLOUD.cloud.select("machines", limit=200) or []):
                if m.get("id") == mid and m.get("hostname"):
                    out.add(m["hostname"])
        except Exception:                                # noqa: BLE001
            pass
    return {n for n in out if n}


def _real_host(machine_id):
    """The computer's own name, out of its shard id.

    The id is the hostname slug plus "-" plus four hex characters. Anything
    that does not look like that is returned as it came: better to show an
    unfamiliar id than to invent a hostname by chopping it.
    """
    got = str(machine_id or "")
    if "-" not in got:
        return got.upper() or None
    head, tag = got.rsplit("-", 1)
    if len(tag) == 4 and all(c in "0123456789abcdef" for c in tag.lower()):
        return head.upper() or None
    return got.upper() or None


def _machine_label(friendly, machine_id):
    """"Bluebarry (DESKTOP-4H65AI7)", or just the name when they agree."""
    real = _real_host(machine_id)
    name = str(friendly or "").strip() or real or str(machine_id or "")
    if not real or real.lower() == name.lower():
        return name
    return "%s (%s)" % (name, real)


@app.route("/api/devices/archive", methods=["POST"])
def api_devices_archive():
    """Take a computer off the lists, or put it back.

    Same reasoning as archiving a person: a machine that has been retired
    still wrote every row it wrote, so it cannot be deleted -- but it should
    not go on cluttering a device picker for ever. Nothing is removed and no
    count changes.

    Keyed on the id rather than the name, because the name is the thing that
    changes: this lab has four names in its logs for three computers.
    """
    body = request.get_json(force=True, silent=True) or {}
    mid = (body.get("id") or "").strip()
    if not mid:
        return jsonify({"ok": False,
                        "error": "Which computer? Pass its id."}), 400
    want = bool(body.get("archived", True))
    if not CLOUD.cloud.configured:
        return jsonify({"ok": False,
                        "error": "The machine list lives in the shared "
                                 "database, so archiving one needs a "
                                 "connection."}), 400
    # A name with no computer behind it. Rows written before errors carried
    # a shard are filed under the friendly name, so the feed offers names
    # the `machines` table has never heard of -- and a patch on a row that
    # does not exist succeeds and changes nothing, which looks exactly like
    # archiving and is not. So the name is filed as a machine of its own:
    # honest, because it IS a computer whose logs are here, and it makes the
    # picker and the manager agree about what exists.
    name_only = bool(body.get("name_only"))
    try:
        if name_only:
            CLOUD.cloud.upsert("machines", [{
                "id": mid,
                "hostname": mid,
                "archived": want,
                "updated_at": cloudmod.now(),
            }], on_conflict="id")
        else:
            CLOUD.cloud.patch_rows("machines", "id=eq.%s" % _q(mid),
                                   {"archived": want})
    except Exception as exc:                             # noqa: BLE001
        msg = str(exc)
        if "42703" in msg or "PGRST204" in msg:
            return jsonify({
                "ok": False,
                "error": "The shared database has no `archived` column on "
                         "machines yet. Run supabase/10_machines_archived"
                         ".sql and try again.",
                "run": "10_machines_archived.sql"}), 400
        return jsonify({"ok": False, "error": msg[:200]}), 502
    # The answer this route just changed is cached for a minute, and the
    # error feed filters on it. Without dropping it here, a machine stayed
    # in the picker for up to sixty seconds after being archived and the
    # click looked like it had done nothing.
    _ARCHIVED_SEEN["at"] = 0.0
    STORE.record_activity([{
        "action": "device.archive",
        "detail": {"id": mid, "archived": want, "name_only": name_only},
    }])
    return jsonify({"ok": True, "id": mid, "archived": want})


@app.route("/api/errors/bundle", methods=["POST"])
def api_errors_bundle():
    """One block of text with everything a bug report needs."""
    body = request.get_json(force=True) or {}
    sig = body.get("signature")
    recs = STORE.list_errors(limit=600)
    if sig:
        recs = [r for r in recs if extras.signature(r) == sig]
    recs = recs[:8]

    sysdesc = sysinfo.describe()
    lines = [
        "Jarvis diagnostic bundle",
        "generated  " + time.strftime("%Y-%m-%d %H:%M:%S"),
        "repo       " + REPO_ROOT,
        "machine    %s / %s %s (%s)" % (sysdesc.get("hostname"),
                                        sysdesc.get("os"),
                                        sysdesc.get("release"),
                                        sysdesc.get("machine")),
        "python     %s  (%s)" % (sysdesc.get("python"), sys.executable),
        "matlab     " + (runner.MATLAB_EXE or "not found"),
        "ffmpeg     " + (sysinfo.find_ffmpeg() or "not found"),
        "user       " + str(STORE.provenance().get("user")),
        "",
        "%d matching error(s), newest first" % len(recs),
        "=" * 72,
    ]
    for r in recs:
        lines += [
            "",
            "[%s]  %s" % (r.get("at"), r.get("where")),
            "machine: %s   user: %s" % (r.get("machine"), r.get("user")),
            "message: %s" % r.get("message"),
        ]
        if r.get("context"):
            lines.append("context: " + json.dumps(r["context"], default=str)[:1200])
        if r.get("detail"):
            lines += ["detail:", str(r["detail"])[:4000]]
        lines.append("-" * 72)
    return jsonify({"ok": True, "text": "\n".join(lines)})


# ==========================================================================
# Results: bulk actions and a manifest
# ==========================================================================
@app.route("/api/results/bulk", methods=["POST"])
def api_results_bulk():
    """Tag, star or untag many results in one go."""
    body = request.get_json(force=True) or {}
    ids_ = body.get("ids") or []
    add = [t.strip() for t in (body.get("add_tags") or []) if t.strip()]
    remove = [t.strip() for t in (body.get("remove_tags") or []) if t.strip()]
    star = body.get("starred")
    # "" is a real instruction here -- take it out of its folder -- so the
    # difference between "not given" and "cleared" has to survive.
    folder = body.get("folder")
    moves = []
    touched = 0
    for rid in ids_:
        rec = RESULTS.get(rid)
        if not rec:
            continue
        tags = list(rec.get("tags") or [])
        for t in add:
            if t not in tags:
                tags.append(t)
        tags = [t for t in tags if t not in remove]
        patch = {"tags": tags}
        if star is not None:
            patch["starred"] = bool(star)
        if folder is not None:
            moves.append(rid)
        try:
            RESULTS.curate(rec["path"], patch)
            touched += 1
        except Exception:
            continue
    # The move happens after the tagging, and one at a time: each one
    # renames a file and repoints whatever held its old path.
    moved, failed = 0, []
    for rid in moves:
        try:
            RESULTS.move(rid, folder, store=STORE)
            moved += 1
        except (ValueError, OSError) as exc:
            failed.append(str(exc))
    STORE.record_activity([{
        "action": "result.bulk",
        "detail": {"n": touched, "add": add, "remove": remove,
                   "starred": star, "folder": folder, "moved": moved},
    }])
    return jsonify({"ok": True, "touched": touched, "moved": moved,
                    "failed": failed, "folders": RESULTS.folders()})


@app.route("/api/results/folders")
def api_results_folders():
    """Every folder results are filed in, as a tree."""
    return jsonify({"ok": True, "folders": RESULTS.folders(),
                    "unfiled": RESULTS.unfiled()})


@app.route("/api/results/folders/new", methods=["POST"])
def api_results_folders_new():
    """Make an empty folder, because that is how people work: you make
    "Figure 3" and then decide what goes in it."""
    body = request.get_json(force=True) or {}
    try:
        folder = RESULTS.make_folder(body.get("name"))
    except (ValueError, OSError) as exc:
        return fail("results/folders/new", exc, 400)
    return jsonify({"ok": True, "folder": folder,
                    "folders": RESULTS.folders()})


@app.route("/api/results/folders/rename", methods=["POST"])
def api_results_folders_rename():
    """Rename a folder, and everything under it.

    Renaming has to carry the children or a rename silently orphans them:
    "Figure 3" becoming "Figure 4" while "Figure 3/Panels" stays behind is a
    worse outcome than refusing.
    """
    body = request.get_json(force=True) or {}
    src = RESULTS.clean_folder(body.get("from"))
    dst = RESULTS.clean_folder(body.get("to"))
    try:
        touched = RESULTS.rename_folder(src, dst, store=STORE)
    except (ValueError, OSError) as exc:
        return fail("results/folders/rename", exc, 400)
    STORE.record_activity([{
        "action": "result.folder.rename",
        "detail": {"from": src, "to": dst, "n": touched},
    }])
    return jsonify({"ok": True, "touched": touched,
                    "folders": RESULTS.folders()})


@app.route("/api/results/delete", methods=["POST"])
def api_results_delete():
    """Delete result files. Only ever inside the Output folder."""
    body = request.get_json(force=True) or {}
    out = outputs_dir()
    removed, refused = [], []
    for rid in (body.get("ids") or []):
        rec = RESULTS.get(rid)
        if not rec:
            continue
        full = os.path.abspath(rec["path"])
        if not full.startswith(out):
            refused.append({"path": full,
                            "error": "Outside the Output folder -- delete it "
                                     "where it lives."})
            continue
        try:
            os.remove(full)
            removed.append(full)
        except OSError as exc:
            refused.append({"path": full, "error": str(exc)})
    if removed:
        RESULTS.catalog(refresh=True)
    STORE.record_activity([{
        "action": "result.delete",
        "detail": {"removed": len(removed), "refused": len(refused)},
    }])
    return jsonify({"ok": True, "removed": removed, "refused": refused})


@app.route("/api/results/manifest", methods=["POST"])
def api_results_manifest():
    body = request.get_json(force=True) or {}
    wanted = set(body.get("ids") or [])
    items = RESULTS.catalog()
    if wanted:
        items = [r for r in items if r.get("id") in wanted]
    rows = [{
        "title": r.get("title") or r.get("name"),
        "file": r.get("name"),
        "type": r.get("type"),
        "session": r.get("session_label"),
        "tags": r.get("tags"),
        "starred": r.get("starred"),
        "bytes": r.get("bytes"),
        "modified": r.get("modified"),
        "author": r.get("author"),
        "machine": r.get("machine"),
        "script": r.get("script"),
        "notes": r.get("notes"),
        "path": r.get("path"),
    } for r in items]
    text = extras.to_csv(rows)
    name = body.get("name") or "results-manifest.csv"
    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="Manifests")
    except Exception:
        saved = None
    headers = {"Content-Disposition": 'attachment; filename="%s"' % name}
    if saved:
        headers["X-Barry-Output"] = saved["rel"]
    return Response(text, mimetype="text/csv", headers=headers)


# ==========================================================================
# History: CSV export
# ==========================================================================
@app.route("/api/history/export", methods=["POST"])
def api_history_export():
    body = request.get_json(force=True) or {}
    what = body.get("what") or "runs"
    if what == "activity":
        recs = STORE.list_activity(limit=int(body.get("limit") or 5000))
        rows = [{
            "at": a.get("at"), "action": a.get("action"), "view": a.get("view"),
            "session": (a.get("session") or {}).get("label"),
            "user": a.get("user"), "machine": a.get("machine"),
            "detail": json.dumps(a.get("detail") or {}, default=str)[:600],
        } for a in recs]
        name = "activity.csv"
    else:
        recs = STORE.list_runs(limit=int(body.get("limit") or 2000))
        rows = [{
            "at": (r.get("provenance") or {}).get("at"),
            "id": r.get("id"), "kind": r.get("kind"),
            "script": r.get("script"), "label": r.get("label"),
            "status": r.get("status"), "seconds": r.get("seconds"),
            "session": (r.get("session") or {}).get("label"),
            "user": (r.get("provenance") or {}).get("user"),
            "machine": (r.get("provenance") or {}).get("machine"),
            "output": (r.get("output") or {}).get("rel"),
            "parameters": json.dumps(r.get("parameters") or {},
                                     default=str)[:600],
        } for r in recs]
        name = "run-history.csv"
    text = extras.to_csv(rows)
    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="Manifests")
    except Exception:
        saved = None
    headers = {"Content-Disposition": 'attachment; filename="%s"' % name}
    if saved:
        headers["X-Barry-Output"] = saved["rel"]
    return Response(text, mimetype="text/csv", headers=headers)


# ==========================================================================
# Misc: repo grep, scratch runner, housekeeping
# ==========================================================================
@app.route("/api/repo/grep", methods=["POST"])
def api_repo_grep():
    body = request.get_json(force=True) or {}
    try:
        res = extras.repo_grep(
            REPO_ROOT, body.get("pattern") or "",
            regex=bool(body.get("regex")), case=bool(body.get("case")),
            limit=int(body.get("limit") or 400),
            exts=body.get("exts") or None)
    except Exception as exc:
        return fail("repo/grep", exc, 400, {"pattern": body.get("pattern")})
    if res.get("ok"):
        STORE.record_activity([{
            "action": "repo.grep",
            "detail": {"pattern": body.get("pattern"),
                       "hits": len(res.get("hits") or []),
                       "regex": bool(body.get("regex"))},
        }])
    return jsonify(res)


@app.route("/api/scratch/run", methods=["POST"])
def api_scratch_run():
    """Run an ad-hoc snippet with the repo importable, as a normal job."""
    body = request.get_json(force=True) or {}
    code = body.get("code") or ""
    if not code.strip():
        return jsonify({"ok": False, "error": "Nothing to run."}), 400
    src = extras.scratch_source(code, REPO_ROOT, APP_DIR)
    scratch_dir = os.path.join(LOGS_DIR, "scratch")
    os.makedirs(scratch_dir, exist_ok=True)
    name = "scratch_%s.py" % time.strftime("%Y%m%d_%H%M%S")
    full = os.path.join(scratch_dir, name)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        job = runner.run_file(full, "python", cwd=REPO_ROOT,
                              label="Scratch " + name, cleanup=[],
                              meta={"kind": "scratch", "script": name,
                                    "lang": "python",
                                    "parameters":
                                        {"lines": code.count("\n") + 1}})
    except Exception as exc:
        return fail("scratch", exc, 400)
    STORE.record_activity([{"action": "scratch.run",
                            "detail": {"file": name,
                                       "lines": code.count("\n") + 1}}])
    return jsonify({"ok": True, "job": job.snapshot(), "file": full})


@app.route("/api/scratch/saved", methods=["GET", "POST"])
def api_scratch_saved():
    """Named snippets, kept in preferences so they sync with everything else."""
    prefs = STORE.get_prefs()
    snips = prefs.get("scratch") or []
    if request.method == "GET":
        return jsonify({"ok": True, "snippets": snips,
                        "preamble": extras.SCRATCH_PREAMBLE})
    body = request.get_json(force=True) or {}
    if body.get("delete"):
        snips = [s for s in snips if s.get("id") != body["delete"]]
    else:
        snip = {"id": body.get("id") or uuid.uuid4().hex[:8],
                "name": (body.get("name") or "snippet").strip(),
                "code": body.get("code") or "", "at": time.strftime("%Y-%m-%d %H:%M")}
        snips = [s for s in snips if s.get("id") != snip["id"]]
        snips.insert(0, snip)
        del snips[40:]
    STORE.set_prefs({"scratch": snips})
    return jsonify({"ok": True, "snippets": snips})


@app.route("/api/housekeeping")
def api_housekeeping():
    try:
        res = extras.housekeeping_scan(REPO_ROOT, outputs_dir(), LOGS_DIR,
                                       big_mb=int(request.args.get("big", 25)))
    except Exception as exc:
        return fail("housekeeping", exc, 400)
    return jsonify(res)


@app.route("/api/housekeeping/clean", methods=["POST"])
def api_housekeeping_clean():
    body = request.get_json(force=True) or {}
    try:
        res = extras.housekeeping_clean(body.get("paths") or [], REPO_ROOT)
    except Exception as exc:
        return fail("housekeeping/clean", exc, 400)
    # Thumbnails are derived and rebuild themselves, so the only question is
    # whether the folder has got big. Swept here rather than on the hot path:
    # a cache that tidies itself while somebody is waiting for a page has
    # turned a saving into a stall.
    try:
        freed = thumbs.sweep(os.path.join(LOGS_DIR, ".cache", "thumbs"))
        if freed:
            res["freed"] = (res.get("freed") or 0) + freed
            res.setdefault("notes", []).append(
                "Dropped %.1f MB of thumbnails, which rebuild as they are "
                "looked at." % (freed / 1e6))
    except Exception:                                    # noqa: BLE001
        pass
    STORE.record_activity([{
        "action": "housekeeping.clean",
        "detail": {"removed": len(res.get("removed") or []),
                   "freed": res.get("freed"),
                   "refused": len(res.get("failed") or [])},
    }])
    return jsonify(res)


# ==========================================================================
# Debug trace -- the context behind a bug that raised nothing
# ==========================================================================
@app.route("/api/debug/trace")
def api_debug_trace():
    return jsonify({
        "ok": True,
        "trace": extras.TRACE.recent(
            limit=int(request.args.get("limit", 300)),
            path=request.args.get("path") or None,
            failed_only=bool(request.args.get("failed"))),
        "seq": extras.TRACE.seq,
    })


@app.route("/api/debug/clear", methods=["POST"])
def api_debug_clear():
    extras.TRACE.clear()
    return jsonify({"ok": True})


@app.route("/api/debug/report", methods=["POST"])
def api_debug_report():
    """Everything needed to explain a silent bug, as one block of text.

    The browser sends what only it knows -- which controls were used, what its
    console said, how each request looked from its side. The server adds the
    request trail, the environment and the recent errors.
    """
    body = request.get_json(force=True) or {}
    sysdesc = sysinfo.describe()
    L = []
    L.append("Jarvis debug report")
    L.append("generated  " + time.strftime("%Y-%m-%d %H:%M:%S"))
    L.append("machine    %s / %s %s" % (sysdesc.get("hostname"),
                                        sysdesc.get("os"), sysdesc.get("release")))
    L.append("python     %s" % sysdesc.get("python"))
    L.append("matlab     %s" % (runner.MATLAB_EXE or "not found"))
    L.append("ffmpeg     %s" % (sysinfo.find_ffmpeg() or "not found"))
    L.append("repo       " + REPO_ROOT)
    L.append("view       " + str(body.get("view")))
    L.append("session    " + str(body.get("session")))

    if body.get("note"):
        L += ["", "WHAT I WAS DOING", "-" * 66, str(body["note"])[:4000]]

    acts = body.get("actions") or []
    if acts:
        L += ["", "UI ACTIONS, oldest first (%d)" % len(acts), "-" * 66]
        for a in acts[-140:]:
            L.append("%-9s %-26s %s" % (
                str(a.get("at", ""))[-8:], a.get("action", ""),
                json.dumps(a.get("detail") or {}, default=str)[:150]))

    console = body.get("console") or []
    if console:
        L += ["", "BROWSER CONSOLE (%d)" % len(console), "-" * 66]
        for c in console[-60:]:
            L.append("%-9s %-5s %s" % (c.get("at", ""), c.get("level", ""),
                                       str(c.get("text", ""))[:400]))

    net = body.get("requests") or []
    if net:
        L += ["", "REQUESTS AS THE BROWSER SAW THEM (%d)" % len(net), "-" * 66]
        for r in net[-140:]:
            L.append("%-9s %-4s %-36s %3s %8s ms%s" % (
                r.get("at", ""), r.get("method", ""),
                str(r.get("path", ""))[:36], r.get("status", ""),
                r.get("ms", ""),
                "  " + str(r.get("error"))[:140] if r.get("error") else ""))

    trace = extras.TRACE.recent(limit=200)
    L += ["", "REQUESTS AS THE SERVER SAW THEM, newest first (%d)" % len(trace),
          "-" * 66]
    for t in reversed(trace):
        extra = t.get("query") or (json.dumps(t.get("body") or {}, default=str)
                                   if t.get("body") else "")
        L.append("%-9s %-4s %-32s %3s %8s ms  %s" % (
            t.get("at", ""), t.get("method", ""), str(t.get("path", ""))[:32],
            t.get("status", ""), t.get("ms", ""), str(extra)[:170]))

    errs = STORE.list_errors(limit=12)
    if errs:
        L += ["", "LAST %d LOGGED ERRORS" % len(errs), "-" * 66]
        for e in errs:
            L.append("[%s] %s: %s" % (e.get("at"), e.get("where"),
                                      e.get("message")))
            if e.get("detail"):
                L.append(str(e["detail"])[:1200])

    text = "\n".join(L)
    saved = None
    try:
        # Scratch, always. A debug report is a by-product of something going
        # wrong, it is read once by whoever it was sent to, and forty-nine of
        # them had accumulated in the results folder where nobody wants them.
        # Still written, still findable at Results/_scratch/Debug, just not
        # filed among the figures.
        saved = save_output(
            text.encode("utf-8"),
            "debug-report-%s.txt" % time.strftime("%Y%m%d_%H%M%S"),
            subdir="Debug", lane=SCRATCH_LANE)
    except Exception:
        saved = None
    STORE.record_activity([{
        "action": "debug.report",
        "detail": {"note": bool(body.get("note")), "requests": len(net),
                   "actions": len(acts), "console": len(console)},
    }])
    return jsonify({"ok": True, "text": text,
                    "saved": saved["rel"] if saved else None})


# ==========================================================================
# Event bank -- the shared record of detected events
# ==========================================================================
BANK = eventbank.EventBank(LOGS_DIR, STORE)
# Alignments waiting to be accepted. Beside the bank rather than inside it:
# a proposal is not a version until somebody says so.
BRACES = brsetmod.BracesSets(LOGS_DIR, STORE)
REG = sessreg.Registry(STORE)
CURATE = curation.Curation(LOGS_DIR, STORE)
LAYERS = layers.Layers(LOGS_DIR, STORE)
MICE = micebook.MouseBook(LOGS_DIR, STORE)
# Compiled from what everything else already records, so it cannot
# drift out of step with the attribution on the data.
PEOPLE = peoplemod.People(LOGS_DIR, STORE, PROFILE)
# So removing somebody from the roster survives the next sync. Without it
# another machine still holding the name pushes its copy back and the pull
# re-creates it -- measured, on a merge and on a harness probe.
PEOPLE.tombs = RESULTS.tombs
# The version, read from the one place it is written: the newest
# heading in CHANGELOG.md.
NOTES = notesmod.Notes(APP_DIR, REPO_ROOT)


# ==========================================================================
# Mice -- what is true about the animal rather than the recording
# ==========================================================================
@app.route("/api/mice")
def api_mice():
    """Every mouse record, plus every attribute anyone has used.

    The attribute list is what lets the housekeeping tree offer "group by
    genotype" without anyone declaring a schema: the names come from what has
    actually been filled in.
    """
    return jsonify({
        "ok": True,
        "mice": MICE.all(),
        "attributes": MICE.attributes(),
        "suggested": micebook.SUGGESTED,
    })


@app.route("/api/mice/set", methods=["POST"])
def api_mice_set():
    """Attach attributes to one mouse, or to several at once.

    Several at once because that is how labelling actually goes -- you select
    the six DKO animals and say so once, rather than opening six panels.
    """
    body = request.get_json(force=True) or {}
    targets = body.get("targets")
    if not targets:
        targets = [{"project": body.get("project"), "mouse": body.get("mouse")}]
    attrs = body.get("attrs") or {}
    if not attrs and body.get("note") is None:
        return jsonify({"ok": False, "error": "Nothing to set."}), 400
    out = []
    for t in targets:
        # No mouse number means no animal to attach anything to. Refusing
        # beats returning ok and writing nothing, which reads as a bug in the
        # page rather than a fact about the folder name.
        if t.get("mouse") is None:
            return jsonify({
                "ok": False,
                "error": "That recording has no mouse number, so there is no "
                         "animal to label. Rename the folder so the mouse can "
                         "be read from it, or set its label by hand.",
            }), 400
        out.append(MICE.set(t.get("project") or sessreg.UNFILED, t["mouse"],
                            attrs, note=body.get("note"),
                            replace=bool(body.get("replace"))))
    STORE.record_activity([{
        "action": "mice.label",
        "detail": {"n": len(out), "attrs": sorted(attrs)},
    }])
    return jsonify({"ok": True, "mice": out, "attributes": MICE.attributes()})


@app.route("/api/mice/forget", methods=["POST"])
def api_mice_forget():
    body = request.get_json(force=True) or {}
    ok = MICE.delete(body.get("project") or sessreg.UNFILED, body.get("mouse"))
    return jsonify({"ok": bool(ok), "attributes": MICE.attributes()})


@app.route("/api/profile", methods=["GET", "POST"])
def api_profile():
    """Who you are. Everything attributed is tagged from this.

    Before it existed, attribution came from `git config user.name` falling
    back to the Windows account -- so on a shared rig every curation
    decision was credited to a computer, and two people on one machine were
    indistinguishable.
    """
    if request.method == "GET":
        return jsonify({"ok": True, "profile": PROFILE.get(),
                        "fields": list(profilemod.FIELDS),
                        "provenance": STORE.provenance()})
    body = request.get_json(force=True) or {}
    try:
        prof = PROFILE.save(body)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:                              # noqa: BLE001
        return fail("profile/save", exc, 400)
    return jsonify({"ok": True, "profile": prof,
                    "provenance": STORE.provenance()})


@app.route("/api/feedback", methods=["GET", "POST"])
def api_feedback():
    """Bug reports, feature requests and suggestions.

    Kept next to the errors because that is where you are standing when you
    notice something, and taking screenshots because the useful half of most
    reports is the screen.
    """
    if request.method == "GET":
        return jsonify({"ok": True, "reports": FEEDBACK.all(),
                        "kinds": [{"id": k, "name": v}
                                  for k, v in feedbackmod.KINDS.items()],
                        "states": list(feedbackmod.STATES),
                        "counts": FEEDBACK.counts(),
                        "user": STORE.provenance().get("user")})
    body = request.get_json(force=True) or {}
    # The last ten minutes go in whether or not the form asked for them:
    # the person filing cannot know which lines matter, and a report without
    # them usually cannot be acted on.
    if body.get("recent") is None and not body.get("no_recent"):
        try:
            body["recent"] = _recent_window()
        except Exception:                                 # noqa: BLE001
            body["recent"] = None
    try:
        rec = FEEDBACK.add(body, user=STORE.provenance().get("user"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:                          # noqa: BLE001
        return fail("feedback/add", exc, 400)
    return jsonify({"ok": True, "report": rec})


@app.route("/api/feedback/<rec_id>", methods=["POST"])
def api_feedback_update(rec_id):
    body = request.get_json(force=True) or {}
    try:
        rec = FEEDBACK.update(rec_id, body,
                              user=STORE.provenance().get("user"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "report": rec})


@app.route("/api/feedback/shot/<name>")
def api_feedback_shot(name):
    path = FEEDBACK.shot_path(name)
    if not path:
        return jsonify({"ok": False, "error": "No such attachment."}), 404
    return send_file(path)


# Scans are held between the look and the go-ahead, so the import writes
# exactly what was shown rather than re-reading a folder that may have
# changed in between.
_DSSCANS = {}


@app.route("/api/dsimport/scan", methods=["POST"])
def api_dsimport_scan():
    """Read a folder of sorted snapshots and say what would be imported.

    Writes nothing. Every folder gets a verdict and, when it cannot be
    imported, the reason -- because the failure mode that matters here is
    decisions landing on the wrong events, which nobody would notice.
    """
    body = request.get_json(force=True) or {}
    root = body.get("root", "")
    kind = body.get("kind", "ds")
    try:
        rows = dsimport.scan(root, BANK, kind=kind)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:                              # noqa: BLE001
        return fail("dsimport/scan", exc, 400, {"root": root})
    token = "scan" + uuid.uuid4().hex[:10]
    _DSSCANS[token] = rows
    if len(_DSSCANS) > 8:
        _DSSCANS.pop(next(iter(_DSSCANS)))
    # The per-event maps are big and only the server needs them.
    public = [{k: v for k, v in r.items() if not k.startswith("_")}
              for r in rows]
    return jsonify({"ok": True, "token": token, "root": root,
                    "rows": public, "summary": dsimport.summary(rows)})


@app.route("/api/dsimport/apply", methods=["POST"])
def api_dsimport_apply():
    body = request.get_json(force=True) or {}
    rows = _DSSCANS.get(body.get("token") or "")
    if rows is None:
        return jsonify({"ok": False,
                        "error": "That scan has expired. Scan again."}), 400
    only = set(body.get("folders") or [])
    if only:
        rows = [r for r in rows if r.get("folder") in only]
    try:
        out = dsimport.apply(rows, BANK, CURATE, kind=body.get("kind", "ds"),
                             replace=bool(body.get("replace", True)),
                             who=STORE.provenance().get("user"))
    except Exception as exc:                              # noqa: BLE001
        return fail("dsimport/apply", exc, 400)
    return jsonify({"ok": True, **out})


@app.route("/api/bank")
def api_bank():
    """The whole bank, grouped and flat, without the event lists."""
    return jsonify({
        "ok": True,
        "tree": BANK.tree(),
        "entries": BANK.summaries(),
        "types": eventbank.EVENT_TYPES,
        "root": BANK.root,
        "user": STORE.provenance().get("user"),
    })


@app.route("/api/bank/<entry_id>")
def api_bank_entry(entry_id):
    rec = BANK.get(entry_id)
    if not rec:
        return jsonify({"ok": False, "error": "No such entry."}), 404
    return jsonify({"ok": True, "entry": rec})


@app.route("/api/bank/add", methods=["POST"])
def api_bank_add():
    body = request.get_json(force=True) or {}
    try:
        rec = BANK.add(body)
    except eventbank.BankError as exc:
        # A refusal, not a fault: show it and log nothing.
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("bank/add", exc, 400)
    STORE.record_activity([{
        "action": "bank.add",
        # `.get`, not `[...]`. These are the fields of an activity line, not
        # a contract: a set banked without a mouse -- a detector's output,
        # filed before anybody has said which animal it is -- writes a record
        # whose null keys the shard writer drops, and `rec["mouse"]` then
        # raised KeyError('mouse'). The bank had already succeeded, so the
        # entry existed and the caller was told "Not banked: 'mouse'".
        "detail": {"id": rec.get("id"), "project": rec.get("project"),
                   "mouse": rec.get("mouse"), "session": rec.get("session"),
                   "type": rec.get("type"), "n": rec.get("n"),
                   "pipeline": (rec.get("source") or {}).get("pipeline")},
        "session": {"key": rec.get("session_key"),
                    "label": rec.get("session_label")},
    }])
    mirror_bank_soon()

    return jsonify({"ok": True, "entry": {k: v for k, v in rec.items()
                                          if k != "events"}})


@app.route("/api/bank/<entry_id>/update", methods=["POST"])
def api_bank_update(entry_id):
    body = request.get_json(force=True) or {}
    try:
        rec = BANK.update(entry_id, body)
    except eventbank.BankError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return fail("bank/update", exc, 400)
    STORE.record_activity([{"action": "bank.update",
                            "detail": {"id": entry_id,
                                       "fields": sorted(body)}}])
    mirror_bank_soon()

    return jsonify({"ok": True, "entry": {k: v for k, v in rec.items()
                                          if k != "events"}})


@app.route("/api/bank/<entry_id>/version/<int:v>", methods=["POST"])
def api_bank_version(entry_id, v):
    """Edit, archive or delete one version of an entry's history."""
    body = request.get_json(force=True, silent=True) or {}
    action = (body.get("action") or "edit").strip()
    undo = None
    try:
        if action == "delete":
            rec = BANK.delete_version(entry_id, v)
            changed = ["deleted"]
            # Deleting a correction puts the times back and drops the basis
            # stamp, which is what makes the session show an unresolved
            # segment issue again -- `patched` is computed from that stamp.
            # Reported so the window can say so rather than leaving somebody
            # to notice a filter change on their own.
            undo = rec.get("undo")
        elif action in ("archive", "unarchive"):
            rec, changed = BANK.edit_version(
                entry_id, v, {"archived": action == "archive"})
        else:
            patch = {}
            if "note" in body:
                patch["note"] = body.get("note")
            if "title" in body:
                patch["title"] = body.get("title")
            if not patch:
                return jsonify({"ok": False,
                                "error": "Nothing to change."}), 400
            rec, changed = BANK.edit_version(entry_id, v, patch)
    except eventbank.BankError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    STORE.record_activity([{
        "action": "bank.version." + action,
        "detail": {"entry": entry_id, "version": v, "changed": changed},
    }])
    mirror_bank_soon()
    return jsonify({"ok": True, "changed": changed, "undo": undo,
                    "versions": [{k: val for k, val in x.items()
                                  if k != "snap"}
                                 for x in (rec.get("versions") or [])]})


@app.route("/api/bank/<entry_id>/dedupe", methods=["POST"])
def api_bank_dedupe(entry_id):
    """Collapse rows of one entry that hold the same time twice.

    Defaults to a dry run: the answer says which times are doubled, which
    of them carry two different calls, and which copy each would keep.
    Writing needs `dry_run: false`, and where any time is contested it also
    needs `conflicts` set to "first" or "last" -- the collapse refuses to
    pick somebody's call for them.
    """
    body = request.get_json(force=True, silent=True) or {}
    dry = body.get("dry_run")
    dry = True if dry is None else bool(dry)
    try:
        out = BANK.dedupe(entry_id,
                          conflicts=body.get("conflicts"),
                          note=(body.get("note") or None),
                          by=body.get("by"),
                          dry_run=dry)
    except eventbank.BankError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:                                  # noqa: BLE001
        return fail("bank/dedupe", exc, 400)

    # The set the entry was banked from. If its doubles are still there the
    # next re-bank puts these straight back, and finding that out after the
    # fact is how somebody comes to run this twice.
    rec = BANK.get(entry_id) or {}
    try:
        cur = CURATE.get(rec.get("gid"), rec.get("type"))
        if cur:
            seen, again = set(), 0
            for ev in cur.get("events") or []:
                key = BANK._dup_key(ev.get("start"))
                if key is None:
                    continue
                if key in seen:
                    again += 1
                seen.add(key)
            if again:
                out["source_set_dupes"] = again
                out["source_set_name"] = cur.get("name")
    except Exception:                                         # noqa: BLE001
        pass

    if not dry and not out.get("error"):
        STORE.record_activity([{
            "action": "bank.dedupe",
            "detail": {"id": entry_id, "version": out.get("version"),
                       "removed": out.get("removed"),
                       "conflicts": out.get("conflicts"),
                       "policy": out.get("policy")},
            "session": {"key": rec.get("session_key"),
                        "label": rec.get("session_label")},
        }])
        mirror_bank_soon()
    # A dry run that refuses still SUCCEEDED: answering "not without a
    # choice, and here are the fourteen times it turns on" is the preview
    # doing its job. `ok: false` makes the client's api() throw, which threw
    # away the answer and left the panel with nothing to show -- so it is
    # kept for a write that would not happen, and for a fault.
    return jsonify({"ok": bool(dry) or not out.get("error"), **out})


@app.route("/api/bank/<entry_id>/delete", methods=["POST"])
def api_bank_delete(entry_id):
    ok = BANK.delete(entry_id)
    if ok:
        STORE.record_activity([{"action": "bank.delete",
                                "detail": {"id": entry_id}}])
    mirror_bank_soon()

    return jsonify({"ok": ok})


@app.route("/api/bank/for-session", methods=["POST"])
def api_bank_for_session():
    """What has been banked against this recording, best match first."""
    body = request.get_json(force=True) or {}
    identity = body.get("identity")
    if not identity and body.get("path"):
        identity = ids.identify(body["path"])
    identity = dict(identity or {})
    # ids.identify reads a folder name; it cannot know the permanent id, so
    # look it up. Without this the match falls back to the header start time,
    # which is exactly the fragile thing the gid was minted to replace.
    if not identity.get("gid"):
        rec, _how = STORE.get_session(identity)
        if rec and rec.get("gid"):
            identity["gid"] = rec["gid"]
    matches = BANK.for_session(identity)
    return jsonify({"ok": True, "entries": matches,
                    "identity": identity or {}})


@app.route("/api/bank/version-export", methods=["POST"])
def api_bank_version_export():
    """One version of one entry, as a CSV of what it held at the time.

    Read straight out of the version's snapshot rather than replayed from the
    decisions since: a snapshot is what the history panel shows, and an
    export that reconstructs the same thing by a different route is an export
    that can disagree with the screen.

    The identity of the recording rides along on every row. A CSV that says
    only `start_s, label` is unusable six months later, and this is exactly
    the file somebody will still have then.
    """
    body = request.get_json(force=True) or {}
    entry_id = body.get("id")
    want_v = body.get("v")
    if entry_id is None or want_v is None:
        return jsonify({"ok": False, "error": "Need an entry id and a version."}), 400

    rec = None
    for r in BANK.all():
        if r.get("id") == entry_id:
            rec = r
            break
    if rec is None:
        return jsonify({"ok": False, "error": "No such entry."}), 404

    version = None
    for v in (rec.get("versions") or []):
        if int(v.get("v", -1)) == int(want_v):
            version = v
            break
    if version is None:
        return jsonify({"ok": False,
                        "error": "That entry has no v%s." % want_v}), 404

    # The names the labels had, so the CSV reads as words rather than ids.
    names = {}
    for src in (version.get("label_names"), rec.get("label_names")):
        if isinstance(src, dict):
            names.update(src)

    added = rec.get("added") or {}
    rows = []
    for pair in (version.get("snap") or []):
        try:
            start, label = pair[0], (pair[1] if len(pair) > 1 else None)
        except (TypeError, IndexError):
            continue
        rows.append({
            "project": rec.get("project"),
            "mouse": rec.get("mouse"),
            "session": rec.get("session"),
            "session_label": rec.get("session_label"),
            "type": rec.get("type"),
            "name": rec.get("name"),
            "version": version.get("v"),
            "start_s": start,
            # Both, because an id is what the data says and a name is what a
            # person reads, and neither on its own survives a rename.
            "label": label,
            "label_name": names.get(label, label),
            "decided_by": version.get("by"),
            "version_at": version.get("at"),
            "version_note": version.get("note"),
            "added_by": added.get("by"),
            "entry_id": rec.get("id"),
        })

    text = extras.to_csv(rows)
    name = body.get("name") or ("event-bank-%s-v%s.csv"
                                % (entry_id, version.get("v")))
    return Response(
        text, mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="%s"' % name})


@app.route("/api/bank/export", methods=["POST"])
def api_bank_export():
    """One entry, or the whole bank, as a CSV of event times."""
    body = request.get_json(force=True) or {}
    wanted = body.get("ids")
    rows = []
    for rec in BANK.all():
        if wanted and rec.get("id") not in wanted:
            continue
        src = rec.get("source") or {}
        added = rec.get("added") or {}
        for ev in (rec.get("events") or []):
            rows.append({
                "project": rec.get("project"),
                "mouse": rec.get("mouse"),
                "session": rec.get("session"),
                "session_label": rec.get("session_label"),
                "type": rec.get("type"),
                "name": rec.get("name"),
                "start_s": ev.get("start"),
                "end_s": ev.get("end"),
                "channel": ev.get("channel"),
                "amplitude": ev.get("amplitude"),
                "pipeline": src.get("pipeline"),
                "run_id": src.get("run_id"),
                "added_by": added.get("by"),
                "added_at": added.get("at"),
                "entry_id": rec.get("id"),
            })
    text = extras.to_csv(rows)
    name = body.get("name") or "event-bank.csv"
    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="Event bank")
    except Exception:
        saved = None
    headers = {"Content-Disposition": 'attachment; filename="%s"' % name}
    if saved:
        headers["X-Barry-Output"] = saved["rel"]
    return Response(text, mimetype="text/csv", headers=headers)


# ==========================================================================
# Kilosort and Phy
# ==========================================================================
# Nothing here runs Kilosort in-process. A sort takes an hour and holds a GPU;
# it belongs in its own process, with its output streamed, cancellable, and
# recorded as a run like everything else Jarvis launches.
@app.route("/api/kilosort/check")
def api_kilosort_check():
    """What this machine has, and what it is missing."""
    return jsonify(spikesort.jsonsafe(dict(
        spikesort.check(REPO_ROOT, request.args.get("python")), ok=True)))


@app.route("/api/kilosort/plan", methods=["POST"])
def api_kilosort_plan():
    """What a run would do, before anything is launched.

    Bad channels come from Jarvis's own record of the recording when the
    caller does not name them, which is the point: the numbers people marked
    while looking at the traces are the numbers that should be excluded, and
    nobody should be retyping them into a second place.
    """
    body = request.get_json(force=True) or {}
    path = body.get("session_path") or ""
    bad = body.get("bad_csc")
    if bad is None and path:
        sess, _err = _session_for(path)
        if sess:
            rec, _how = STORE.get_session(sess)
            bad = (rec or {}).get("bad_channels") or []
    try:
        return jsonify(spikesort.jsonsafe(dict(spikesort.plan(
            REPO_ROOT, path, body.get("probe"), body.get("settings"),
            bad_csc=bad or [], invert=body.get("invert", True),
            python=body.get("python")), ok=True)))
    except Exception as exc:                       # noqa: BLE001
        return fail("kilosort/plan", exc, 400)


@app.route("/api/kilosort/run", methods=["POST"])
def api_kilosort_run():
    """Write the run script out, then execute it as a normal job."""
    body = request.get_json(force=True) or {}
    path = body.get("session_path") or ""
    bad = body.get("bad_csc")
    if bad is None and path:
        sess, _err = _session_for(path)
        if sess:
            rec, _how = STORE.get_session(sess)
            bad = (rec or {}).get("bad_channels") or []
    plan = spikesort.plan(REPO_ROOT, path, body.get("probe"),
                          body.get("settings"), bad_csc=bad or [],
                          invert=body.get("invert", True),
                          python=body.get("python"))
    if not plan["ready"] and not body.get("anyway"):
        return jsonify({"ok": False, "error": "; ".join(
            x["what"] for x in plan["problems"]), "plan": plan}), 400

    os.makedirs(plan["results_dir"], exist_ok=True)
    script = os.path.join(plan["results_dir"], "run_kilosort_barry.py")
    with open(script, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(plan["script"])

    python = body.get("python") or sys.executable
    job = runner.start_job(
        "Kilosort: " + os.path.basename(path.rstrip("/" + os.sep)),
        [python, "-u", script], cwd=plan["results_dir"],
        meta={"kind": "kilosort", "session_path": path,
              "results_dir": plan["results_dir"], "script": script})
    STORE.record_run({
        "id": job.id,
        "script": "kilosort",
        "label": "Kilosort 4",
        "status": "running",
        "session": {"path": path},
        "parameters": {
            "probe": plan["probe"], "settings": plan["settings_file"],
            "bad_csc": plan["bad_csc"], "bad_channels": plan["bad_channels"],
            "invert": plan["invert"], "n_chan_bin": plan["n_chan_bin"],
            "fs": plan["fs"],
        },
        "outputs": [plan["results_dir"]],
    })
    return jsonify({"ok": True, "job": job.id, "script": script,
                    "results_dir": plan["results_dir"], "plan": plan})


@app.route("/api/kilosort/install", methods=["POST"])
def api_kilosort_install():
    """Run one pip install, streamed, so a failure is readable.

    Only the exact commands the check offers -- an arbitrary pip line from
    the browser would be a remote install endpoint, which this is not.
    """
    body = request.get_json(force=True) or {}
    what = body.get("what")
    python = body.get("python") or sys.executable
    plans = {
        "torch": [python, "-m", "pip", "install", "torch", "--index-url",
                  "https://download.pytorch.org/whl/cu121"],
        "torch-cpu": [python, "-m", "pip", "install", "torch"],
        "kilosort": [python, "-m", "pip", "install", "kilosort"],
        "phy": [python, "-m", "pip", "install", "phy", "--pre", "--upgrade"],
    }
    cmd = plans.get(what)
    if not cmd:
        return jsonify({"ok": False,
                        "error": "Not something I install: %r" % what}), 400
    job = runner.start_job("pip install " + what, cmd, cwd=REPO_ROOT,
                           meta={"kind": "install", "what": what})
    return jsonify({"ok": True, "job": job.id,
                    "command": " ".join(cmd)})


@app.route("/api/kilosort/runs")
def api_kilosort_runs():
    """Sorts already done for one recording."""
    path = request.args.get("path") or ""
    return jsonify({"ok": True, "runs": spikesort.results_dirs(path),
                    "binary": spikesort.find_binary(path)})


@app.route("/api/phy/open", methods=["POST"])
def api_phy_open():
    """Launch Phy on a results folder.

    Phy is a desktop app with its own window; Jarvis starts it and gets out of
    the way. Its console output still comes back as a job, because when it
    refuses to start the reason is on stderr.
    """
    body = request.get_json(force=True) or {}
    results = body.get("results_dir") or ""
    info = spikesort.phy_command(results)
    if not info["exists"]:
        return jsonify({
            "ok": False,
            "error": "No params.py in %s -- Phy reads that, and Kilosort "
                     "writes it when a sort finishes. This folder has not "
                     "finished sorting." % (results or "(nothing chosen)"),
        }), 400
    python = body.get("python") or sys.executable
    job = runner.start_job(
        "Phy: " + os.path.basename(results.rstrip("/" + os.sep)),
        [python, "-m", "phy", "template-gui", info["params"]],
        cwd=results, meta={"kind": "phy", "results_dir": results})
    STORE.record_activity([{
        "action": "phy.open", "detail": {"results_dir": results},
    }])
    return jsonify({"ok": True, "job": job.id, "command": info["command"]})


@app.route("/api/phy/guide")
def api_phy_guide():
    """The keys and the views, so the first hour is not spent reading docs."""
    return jsonify({"ok": True, "keys": spikesort.PHY_KEYS,
                    "views": spikesort.PHY_VIEWS})


@app.route("/api/kilosort/terminal", methods=["POST"])
def api_kilosort_terminal():
    """Open a terminal already in the right folder, with the env set up.

    The escape hatch. Everything above is a convenience over commands anyone
    can type, and when the convenience is in the way the right answer is a
    prompt in the right directory rather than a worse version of one.
    """
    body = request.get_json(force=True) or {}
    folder = body.get("path") or REPO_ROOT
    if not os.path.isdir(folder):
        return jsonify({"ok": False,
                        "error": "No such folder: " + folder}), 400
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k",
                              "cd /d " + folder], shell=False)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Terminal", folder])
        else:
            subprocess.Popen(["x-terminal-emulator"], cwd=folder)
    except Exception as exc:                       # noqa: BLE001
        return fail("kilosort/terminal", exc, 400)
    return jsonify({"ok": True, "path": folder})


# ==========================================================================
# Supabase -- the shared copy
#
# Jarvis writes locally first, always. The files are what make it work on a
# rig with no network and on a drive that is not mounted; this pushes what
# they hold to Postgres and brings back what other machines have changed.
# Nothing here is on the critical path of anything: if the sync is down,
# Jarvis carries on and catches up later.
# ==========================================================================
CLOUD = cloudsync.Sync(
    LOGS_DIR, STORE, bank=BANK, curate=CURATE, layers=LAYERS, mice=MICE,
    results=None, repo_root=REPO_ROOT, feedback=FEEDBACK, people=PEOPLE,
    health=HEALTHLOG,
    # What each tool has already worked out. Panorama's is the set runner's
    # own; Incisor's is the one that stops "run the scan again" being the
    # answer to a restart.
    vaults={"panorama": PNSETS.vault, "incisor": INCISOR_VAULT})

# Who is curating what, right now. Cloud-only by design -- see
# backend/presence.py: a presence row that survives a restart is a lie.
PRESENCE = presencemod.Presence(CLOUD.cloud, STORE)

_cloud_lock = threading.Lock()
_cloud_last = {"at": None, "ok": None, "pushed": 0, "pulled": 0,
               "error": None, "running": False}


def _cloud_results():
    """RESULTS is built after this block; bind it lazily rather than
    reordering the module around a background job."""
    if CLOUD.results is None:
        CLOUD.results = RESULTS
    return CLOUD.results


def cloud_sync_once(push=True, pull=True, files=False):
    """One round trip. Never raises: a sync that fails is a status line,
    not an interruption to whatever someone is doing."""
    # `ok=False` explicitly on both of these. They return a copy of the LAST
    # sync's record, and that record's `ok` belongs to a run that already
    # finished -- so a refusal after a good sync came back saying ok, and the
    # button reported the previous run's "sent 5, brought back 3" as though
    # this press had done something.
    if not CLOUD.cloud.configured:
        return dict(_cloud_last, ok=False, error="not configured")
    if not _cloud_lock.acquire(blocking=False):
        # Which step, and how long it has been on it. Pressing the button
        # again is what somebody does when a sync looks stuck, so this is
        # the moment to say what it is actually doing -- and a step that has
        # been going for a minute is the difference between "wait" and "it
        # is hung on a request that will not time out for another fifty
        # seconds", which nothing on screen could tell you before.
        step = dict(_sync_step)
        where = " ".join(str(x) for x in (step.get("phase"), step.get("table"))
                         if x) or "running"
        age = presencemod._age_s(step.get("at"))
        return dict(_cloud_last, ok=False, error=(
            "A sync is already running (%s%s), so this one did nothing. If "
            "that does not move, it is stuck on that step."
            % (where, "" if age is None else ", %ds on that step"
               % int(age))))
    try:
        _cloud_last["running"] = True
        _cloud_results()
        out = {"pushed": 0, "pulled": 0}
        # Roughly how many steps, so the bar has a denominator. Approximate
        # on purpose: a precise count would mean walking every table first,
        # which is most of the work the bar is meant to be reporting on.
        steps = (len(cloudsync.ORDER) if pull else 0) + (
            len(cloudsync.ORDER) + len(cloudsync.PUSH_ONLY) if push else 0)
        _sync_note("starting", of=steps, done=0)
        seen = [0]

        def step(phase):
            def note(table, n=0):
                seen[0] += 1
                _sync_note(phase, table=table, n=n, done=seen[0])
            return note

        if pull:
            _sync_note("pulling", of=steps, done=seen[0])
            got = CLOUD.pull(on_progress=None, on_table=step("pulling"))
            out["pulled"] = sum(v for v in (got.get("applied") or {}).values()
                                if isinstance(v, int))
            _sync_note("pulled", n=out["pulled"], of=steps, done=seen[0])
        if push:
            # Deletions first: a push that re-sends a row we have locally
            # deleted would undo the tombstone it is about to write.
            _sync_note("tombstones", of=steps, done=seen[0])
            out["deleted"] = CLOUD.push_deletions().get("marked", 0)
            sent = CLOUD.push(include_history=True,
                              on_progress=step("pushing"))
            out["pushed"] = sent.get("sent", 0)
        if files:
            # Up first, then down: a figure this machine made should reach
            # the others before it goes looking for theirs.
            up = CLOUD.upload_results()
            out["uploaded"] = up.get("uploaded", 0)
            down = CLOUD.pull_files()
            out["downloaded"] = down.get("downloaded", 0)
        # And the browsable copy of the bank, so the folder tree agrees with
        # the view whether or not anything changed up there.
        out["mirrored"] = CLOUD.mirror_bank(APP_DIR).get("written", 0)
        _cloud_last.update({"at": cloudmod.now(), "ok": True,
                            "error": None, "failures": 0, **out})
        # Whatever was blocking it evidently is not any more.
        _cloud_last.pop("blocked", None)
        _cloud_last.pop("blocked_note", None)
    except Exception as exc:                       # noqa: BLE001
        # Log the first failure of a run, not every one. The commonest reason
        # to fail is "the schema is not applied yet", which does not fix
        # itself in two minutes -- and filling the error log with the same
        # line 700 times before anyone reads it helps nobody.
        first = _cloud_last.get("ok") is not False
        _cloud_last.update({"at": cloudmod.now(), "ok": False,
                            "error": str(exc)[:400]})
        _cloud_last["failures"] = _cloud_last.get("failures", 0) + 1
        # A clock that is ahead of the server's is not something retrying
        # fixes. Every attempt fails identically and logs the same line, so
        # the automatic sync stands down until Jarvis is restarted -- by which
        # time the clock has either been set or it has not. Syncing by hand
        # still works, so there is a way to test the fix without a restart.
        msg = str(exc)
        if "PGRST303" in msg or "issued at future" in msg:
            _cloud_last["blocked"] = "clock"
            _cloud_last["blocked_note"] = (
                "This machine's clock is ahead of Supabase's, so every "
                "request is rejected. Automatic syncing is paused. Set the "
                "clock (Settings > Time & language > Date & time > Sync "
                "now), then press Sync now here.")
        if first:
            STORE.record_error("cloud.sync", exc)
    finally:
        _cloud_last["running"] = False
        # Back to idle whatever happened. A progress record that outlives
        # the sync it describes is worse than none: the bar would sit at
        # 80% forever and nobody would trust the next one.
        _sync_note("idle")
        _cloud_lock.release()
    return dict(_cloud_last)


# How often each half runs, in seconds. Separate because they cost
# different things: a pull is incremental and usually comes back empty, a
# push is only worth making when this machine has changed something.
PULL_EVERY = 20
PUSH_EVERY = 60          # a floor; a write pushes sooner than this
PUSH_AFTER_WRITE = 6     # quiet period after the last write before pushing
FILES_EVERY = 300        # figures and screenshots, which are big and rare

# How far a quiet machine backs off, and how fast.
#
# A pull every 20 seconds is right when somebody is working and two people
# are editing the same set. It is not right for the eight hours the rig sits
# on the Sessions view with nobody in the room -- and it was doing it
# anyway: 4,320 cycles a day, each one asking twenty-one tables a question
# whose answer was "nothing", which measured at about 6.5 GB of egress a
# month against a 5 GB allowance.
#
# So the interval doubles each time a pull brings back nothing and drops
# straight back to the floor the moment anything arrives or anybody writes.
# A cycle that finds work is as quick as it ever was; a cycle that finds
# none happens sixteen times less often.
PULL_MAX = 320           # five and a bit minutes, the ceiling when idle
PULL_GROWTH = 2.0        # doubling, so it reaches the ceiling in four

# When a write happened, so a push can follow it promptly. Set by the
# after_request hook rather than by each route: there are about ninety routes
# that write and one place they all pass through.
_push_wanted = [0.0]


def cloud_touch():
    """Note that something local changed, so the next push is soon."""
    _push_wanted[0] = time.time()


def _cloud_backoff(fails, blocked):
    """How long to wait after a failure, by what kind of failure it was.

    Doubling to a thirty-minute ceiling treated every failure as permanent,
    so one gateway timeout -- which the message text itself calls brief --
    took sync offline for half an hour, which is indistinguishable from it
    being broken.

    A clock that is ahead used to stand sync down until Jarvis was restarted.
    Windows fixes its own clock eventually, and ten minutes is a reasonable
    time to look again; being silently offline until somebody restarts is
    not.
    """
    if blocked:
        return 600
    err = str(_cloud_last.get("error") or "")
    transient = ("504" in err or "502" in err or "503" in err
                 or "Gateway" in err or "timed out" in err
                 or "Timeout" in err or "Connection" in err
                 or "555" in err)
    if transient:
        # Brief by nature. Creep up a little so a real outage is not hammered.
        return min(30 * max(1, fails), 180)
    # Structural -- a missing table, a rejected key. These do not fix
    # themselves in thirty seconds, but they do get fixed, so keep looking.
    return min(120 * max(1, fails), 900)


def _cloud_loop():
    """Background sync, pull and push on their own clocks.

    Pull first whenever both are due, so a push never sends a stale edit over
    somebody else's newer one -- the database would reject it anyway, but
    losing the race locally means the next pull just undoes your screen.
    """
    time.sleep(8)           # let the app finish starting
    next_pull = next_push = next_files = 0.0
    retry_at = 0.0
    idle_pull = float(PULL_EVERY)   # grows while nothing is happening
    while True:
        try:
            cfg = CLOUD.cloud.reload()
            now = time.time()
            if not (cfg.get("enabled") and cfg.get("auto")):
                time.sleep(5)
                continue
            # Standing down after a failure, for as long as that kind of
            # failure deserves.
            if now < retry_at:
                time.sleep(min(5, retry_at - now))
                continue

            # A write since the last push brings the next one forward.
            wrote = _push_wanted[0]
            due_push = (now >= next_push
                        or (wrote and now - wrote >= PUSH_AFTER_WRITE))
            due_pull = now >= next_pull
            due_files = now >= next_files and cfg.get("upload_results", True)

            if due_pull or due_push or due_files:
                if due_push:
                    _push_wanted[0] = 0.0
                before = dict(_cloud_last.get("applied") or {})
                cloud_sync_once(pull=due_pull, push=due_push,
                                files=due_files)
                base = max(5, int(cfg.get("interval") or PULL_EVERY))
                if due_pull:
                    # Did that cycle find anything? A local write counts as
                    # well: somebody typing here is the best available
                    # evidence that somebody is also working elsewhere.
                    got = _cloud_last.get("applied") or {}
                    moved = any(v for k, v in got.items()
                                if not str(k).startswith("_"))
                    if moved or wrote or got != before:
                        idle_pull = base
                    else:
                        idle_pull = min(PULL_MAX,
                                        max(base, idle_pull * PULL_GROWTH))
                    next_pull = time.time() + idle_pull
                if due_push:
                    next_push = time.time() + max(base, PUSH_EVERY)
                if due_files:
                    next_files = time.time() + FILES_EVERY

                fails = _cloud_last.get("failures", 0)
                if fails:
                    retry_at = time.time() + _cloud_backoff(
                        fails, _cloud_last.get("blocked"))
        except Exception:                            # noqa: BLE001
            # The loop itself must not die: everything it calls already
            # reports its own failures, and a thread that has quietly exited
            # looks exactly like a network that is quietly down.
            time.sleep(30)
        time.sleep(1)


if CLOUD.cloud.configured and CLOUD.cloud.cfg.get("auto"):
    threading.Thread(target=_cloud_loop, daemon=True,
                     name="barry-cloud-sync").start()


@app.after_request
def _note_local_write(resp):
    """Any successful write means there is something worth pushing.

    Here rather than in each route: there are about ninety that write, and
    one place they all pass through. GETs are excluded, and so are failures
    -- a rejected request changed nothing.
    """
    try:
        if (request.method in ("POST", "PUT", "PATCH", "DELETE")
                and resp.status_code < 400
                and request.path.startswith("/api/")
                # Not the sync routes themselves, or a manual sync would
                # schedule another one on its way out.
                and not request.path.startswith("/api/cloud/")
                and not request.path.startswith("/api/sync/")):
            cloud_touch()
    except Exception:                                # noqa: BLE001
        pass
    return resp


# The Data Bank folder tree is derived, so it is rebuilt whenever the bank
# changes rather than being kept in step by hand. In a thread because it walks
# a few hundred files and nobody should wait for it to finish banking.
_mirror_lock = threading.Lock()


def mirror_bank_soon():
    def go():
        if not _mirror_lock.acquire(blocking=False):
            return
        try:
            CLOUD.mirror_bank(APP_DIR)
        except Exception as exc:                   # noqa: BLE001
            STORE.record_error("bank.mirror", exc)
        finally:
            _mirror_lock.release()
    threading.Thread(target=go, daemon=True, name="barry-bank-mirror").start()


# Once at startup, so the folder is there and correct before anyone looks.
mirror_bank_soon()


def _seed_demo():
    """Give the demo recordings something to curate and something banked.

    Created once, if it is not already there, so the Guide can walk the
    curation exercise instead of describing it. Written to disk like any
    other set -- a person's decisions during the Guide should persist, and
    twenty-four events is nothing -- but excluded from the cloud sync, since
    nobody wants two fake recordings arriving in a shared database.
    """
    for spec in demomod.SESSIONS.values():
        gid = spec["gid"]
        try:
            if CURATE.get(gid, "ds"):
                continue
            CURATE.create(gid, "ds", demomod.curation_events(spec["id"]),
                          name=spec["label"] + " (demo set)",
                          source={"kind": "demo", "note": spec["note"]},
                          session_label=spec["label"], replace=True)
        except Exception as exc:                          # noqa: BLE001
            STORE.record_error("demo/seed", exc, None, {"gid": gid})


threading.Thread(target=_seed_demo, daemon=True, name="barry-demo-seed").start()


# ==========================================================================
# VACC -- the cluster link
#
# One background thread asks how the cluster is; every route below reads what
# it last found. Nothing here connects on the path of a request, because a
# status chip renders on every page load and a ten-second connect timeout on
# a login node that is busy would be ten seconds of Jarvis not starting.
# ==========================================================================
threading.Thread(target=vaccmod.loop, daemon=True, name="barry-vacc").start()


@app.route("/api/vacc/status")
def api_vacc_status():
    """How the cluster is, from the cache. Never connects."""
    return jsonify(vaccmod.status())


@app.route("/api/vacc/check", methods=["POST"])
def api_vacc_check():
    """Ask now, rather than waiting for the loop.

    Behind a POST because it costs a connection, and separate from
    `/api/vacc/status` so that reading the chip can never be the thing that
    makes the page slow.
    """
    try:
        vaccmod.refresh(force=True)
    except Exception as exc:                             # noqa: BLE001
        return fail("vacc/check", exc, 400)
    return jsonify(vaccmod.status())


def _match_index():
    """The two lookups `_cluster_match` reads, built once.

    Both maps hold the RECORD, never the bare id. That is not a detail: the
    loose branch has to check the candidate's start date and project before
    it will accept a match, and every caller asks the result for its `gid`.

    This function exists because there were two copies of this loop and they
    drifted. `/api/vacc/scan` filed the record in both maps; `_vacc_staged`
    filed the record in `by_loose` and the bare **gid string** in `by_key`.
    So the moment a cluster folder matched a known recording EXACTLY -- the
    common case, and the one the whole feature is for -- `_cluster_match`
    handed back a string and the caller's `rec.get("gid")` raised
    `'str' object has no attribute 'get'`. The Incisor VACC list printed
    that sentence where the recordings should have been.

    `_cluster_match` was written to stop precisely this, by keeping the
    matching rule in one place, and it did. What drifted was what the two
    callers fed it -- so the builder lives here now as well.
    """
    by_key, by_loose = {}, {}
    for rec in (REG.all() or []):
        if not rec.get("gid"):
            continue
        if rec.get("key"):
            by_key.setdefault(str(rec["key"]).lower(), rec)
        if rec.get("loose_key"):
            by_loose.setdefault(str(rec["loose_key"]).lower(), rec)
    return by_key, by_loose


def _cluster_match(path, by_key, by_loose):
    """Which known recording a cluster folder is, or why it is nobody.

    Returns `(rec, how, why)`. `rec` is None when nothing matched or when a
    match was refused, and `why` then says which.

    THE RULE, IN ONE PLACE

    An exact key is mouse, session AND the recording's own start time, so two
    different recordings sharing one is not a thing that happens. A loose key
    is mouse and session only, and in this lab that is not an identity: the
    numbering restarts per project, so m13 s3 is a PTEN recording from
    2023-08-01, a KCNT1 one, and a KCNT1 Urethane one, and their loose keys
    are character-for-character identical.

    So a loose match has to agree about the day AND about the project, and
    the project comes from the full path -- `KCNT1 Urethane/...` is a
    different body of work from `KCNT1/...` even though one name contains
    the other. Both are checked because either alone lets a pair through:
    two projects can record on the same day, and one project can hold the
    same mouse-and-session twice across years.
    """
    ident = ids.identify(path)
    key = str(ident.get("key") or "").lower()
    loose = str(ident.get("loose_key") or "").lower()

    if key and key in by_key:
        return by_key[key], "exact", None
    if not (loose and loose in by_loose):
        return None, None, None

    cand = by_loose[loose]
    mine_day = str(ident.get("start") or "")[:10]
    their_day = str(cand.get("start") or "")[:10]
    if mine_day and their_day and mine_day != their_day:
        return (None, None,
                "same mouse and session as %s, but recorded on %s rather "
                "than %s" % (cand.get("gid"), mine_day, their_day))

    mine_proj = sessreg.guess_project(ident, [path])
    their_proj = (cand.get("project") or "").strip()
    if (mine_proj and their_proj and mine_proj != sessreg.UNFILED
            and their_proj != sessreg.UNFILED and mine_proj != their_proj):
        return (None, None,
                "same mouse and session as %s, but this path is %s work and "
                "that recording is %s" % (cand.get("gid"), mine_proj,
                                          their_proj))
    return cand, "loose", None


def _vacc_staged(force=False, wait=True):
    """What the cluster already holds, keyed by the gid it belongs to.

    The matching is done HERE rather than in `vacc.py`, and on this machine
    rather than on the cluster, because `ids.identify` works from a path
    string alone -- so a remote folder is identified by exactly the rules a
    local one is, by exactly the same code. Nothing about identity has to be
    reimplemented for the cluster, and the two cannot drift.

    Measured against the real scratch: 120 recordings there, 36 of which the
    registry already knows -- 29 by exact key and 7 by the loose one. The
    other 84 are real recordings that Jarvis has never been shown; they are
    reported separately rather than silently dropped, because "the cluster
    has 84 recordings you have never opened" is worth knowing.
    """
    cfg = vaccmod.load_config(LOGS_DIR)
    root = cfg.get("scratch_root") or os.path.dirname(cfg.get("scratch") or "")
    if not root:
        return {}, []
    if not wait and not vaccmod.inventory_ready(cfg, root):
        # Nothing in hand and the caller cannot afford to wait for a walk of
        # the cluster's filesystem. Start one and answer with what is known
        # now, which is nothing -- and nothing renders as `unknown`, which is
        # the honest state for a question that has not been asked yet.
        vaccmod.inventory_soon(cfg, root)
        return {}, []
    found = vaccmod.inventory_cached(cfg, root, force=force)

    by_key, by_loose = _match_index()

    # Exact beats loose, and two exacts for one gid is a refusal.
    #
    # The rule about WHICH recording a cluster folder is lives in
    # `_cluster_match`, so this and `/api/vacc/scan` cannot drift about it.
    # What is decided here is the other half: what to do when two folders
    # both answer to one recording.
    staged, unknown, by_gid = {}, [], {}
    for row in found:
        rec, how, why = _cluster_match(row["path"], by_key, by_loose)
        if rec is None:
            unknown.append(dict(row, why=why) if why else row)
            continue
        gid = rec.get("gid")
        if not gid:
            unknown.append(row)
            continue
        by_gid.setdefault(gid, []).append(dict(row, how=how))

    for gid, rows in by_gid.items():
        exact = [r for r in rows if r["how"] == "exact"]
        best = exact or rows
        if len(best) > 1:
            # Two folders on the cluster both claiming to be this recording.
            # Nothing here can tell which, and picking one silently is how
            # the wrong data gets analysed under the right name.
            staged[gid] = {"conflict": [r["path"] for r in best],
                           "how": "ambiguous"}
            continue
        staged[gid] = best[0]
        for r in rows:
            if r is not best[0]:
                unknown.append(r)
    return staged, unknown


def _vacc_estimate(sess, spec, plan):
    """Could the cluster run this, and roughly what would it cost?

    Never raises and never connects: it reads the cached status and the
    cached inventory, because this rides on an estimate that has to answer
    whether or not there is a cluster today. A reason is always given, since
    a disabled button with no explanation is the `canOpen` mistake again --
    absent capability should be stated rather than hidden.
    """
    out = {"can": False, "state": None, "reason": "", "seconds": None,
           "queued": None, "cached": False}
    try:
        st = vaccmod.status()
        if not st.get("configured"):
            out["reason"] = "No VACC account is set up on this computer."
            return out
        if not st.get("available"):
            out["reason"] = st.get("why") or "The cluster is not reachable."
            return out
        out["queued"] = st.get("queued")
        try:
            remote, state = _vacc_remote_for(sess)
        except Exception as exc:                         # noqa: BLE001
            out["reason"] = str(exc)
            return out
        out.update(can=True, state=state, remote=remote)
        # The rate table learned per remote filesystem -- so this is what the
        # cluster has actually done, once it has done one, and the local
        # seed until then. See `_is_remote` in cfc.py for why those two
        # numbers are never allowed to mix.
        where = "vacc:netfiles" if state == vaccmod.NATIVE else "vacc:scratch"
        span = float(plan.get("span_s") or 0)
        nch = int(plan.get("n_channels") or 0)
        read = cfcmod.rate_for("ds read", where) * span * nch
        det = cfcmod.rate_for("ds detect", where) * nch
        out["seconds"] = round(max(1.0, read + det), 1)
        out["measured"] = cfcmod.rate_for("ds read", where) != \
            cfcmod.rate_for("ds read")
    except Exception as exc:                             # noqa: BLE001
        out["reason"] = str(exc)[:200]
    return out


def _vacc_remote_for(sess):
    """Where this recording is, in the cluster's terms. Raises if nowhere.

    Two ways, and native is preferred: a share VACC mounts needs no copy at
    all, while a scratch copy is a cache of something that lives elsewhere.
    Today the netfiles share is mounted and refused -- see `readable_roots`
    -- so in practice everything runnable comes through the second, which is
    exactly why the error below names both.
    """
    cfg = vaccmod.load_config(LOGS_DIR)

    # By the path, because that is what a session has. `_body_session`
    # returns what `csc.open_session` returns -- channels and a sample rate,
    # no identity -- and there is no by-key lookup on the registry, so both
    # of the obvious shortcuts fall through silently and leave `gid` None.
    # Which is exactly what happened: a recording sitting on the cluster
    # reported "VACC cannot reach this", correctly formatted and wrong.
    #
    # One pass over the merged records, matching any path they carry. The
    # registry unions paths across machines, so the row that answers may
    # have been written by a colleague.
    want = os.path.normcase(os.path.abspath(sess.get("path") or ""))
    gid, paths = None, []
    for rec in (REG.all() or []):
        for known in (rec.get("paths") or []):
            if not isinstance(known, str):
                continue
            if os.path.normcase(os.path.abspath(known)) == want:
                gid = rec.get("gid")
                paths = [p for p in (rec.get("paths") or [])
                         if isinstance(p, str)]
                break
        if gid:
            break
    if sess.get("path") and sess["path"] not in paths:
        paths.append(sess["path"])

    staged, _unknown = _vacc_staged()

    got = vaccmod.resolve_gid(gid, paths, cfg, staged=staged)
    if got.get("state") in (vaccmod.NATIVE, vaccmod.STAGED) and got.get("remote"):
        return got["remote"], got["state"]

    denied = vaccmod.status().get("denied_roots") or []
    why = got.get("why") or "the cluster has no copy of it"
    if denied:
        why += ("; and the share it maps onto (%s) is mounted but this "
                "account cannot read it" % ", ".join(denied))
    raise RuntimeError("VACC cannot reach this recording: " + why)


def _vacc_run_for(tool, sess, spec, plan, report, tool_steps):
    """A `VaccRun` for one recording, and the `where` its rates belong to.

    `where` distinguishes the two remote filesystems, so what the cluster
    teaches about reading netfiles is not folded in with what it teaches
    about reading scratch -- the same split `_PER_VOLUME` makes locally, for
    the same reason.
    """
    cfg = vaccmod.load_config(LOGS_DIR)
    remote, state = _vacc_remote_for(sess)
    # Sent once per submit; a tree that has not changed costs one round trip
    # and no upload, because the remote keeps the content hash.
    vaccmod.push_code(cfg, APP_DIR)
    est = None
    try:
        est = incisormod.estimate(sess, spec, report) if tool == "incisor" \
            else None
    except Exception:                                    # noqa: BLE001
        est = None
    seconds = float((est or {}).get("seconds") or plan.get("seconds") or 0)
    run = vaccrunmod.VaccRun(
        cfg, tool, spec, remote,
        plan={"seconds": seconds},
        megasamples=max(0.001, plan.get("megasamples") or 1.0),
        tool_steps=list(tool_steps), report=report)
    where = "vacc:netfiles" if state == vaccmod.NATIVE else "vacc:scratch"
    return run, where


@app.route("/api/registry/<gid>/bank", methods=["POST"])
def api_registry_bank(gid):
    """Say which probe a block of channels is.

    The only way a bank gets an anatomy. A scan records that a 128-channel
    recording is two banks of sixty-four and stops there, because the number
    of channels cannot tell you which one went into hippocampus -- so this
    is a person answering, and it is recorded as one.
    """
    body = request.get_json(force=True) or {}
    bank_id = str(body.get("bank") or "").strip()
    region = body.get("region")
    region = str(region).strip() if region not in (None, "") else None
    try:
        rec = REG.by_gid(gid)
        if not rec:
            return jsonify({"ok": False, "error": "No session " + gid}), 404
        banks = [dict(b) for b in (rec.get("channel_banks") or [])]
        if not banks:
            return jsonify({"ok": False,
                            "error": "That recording has one probe in it."}), 400
        hit = [b for b in banks if b.get("id") == bank_id]
        if not hit:
            return jsonify({"ok": False,
                            "error": "No bank %s here." % bank_id}), 400
        hit[0]["region"] = region
        hit[0]["said_by"] = (STORE.provenance() or {}).get("user")
        rec = REG._patch(rec, {"channel_banks": banks})
    except Exception as exc:                             # noqa: BLE001
        return fail("registry/bank", exc, 400, {"gid": gid})
    STORE.record_activity([{
        "action": "registry.bank",
        "detail": {"gid": gid, "bank": bank_id, "region": region},
    }])
    return jsonify({"ok": True, "channel_banks": (rec or {}).get("channel_banks")})


@app.route("/api/registry/<gid>/probe", methods=["POST"])
def api_registry_probe(gid):
    """Say which probe template a recording was made with.

    A fact about the animal, so it belongs on the recording rather than on
    whoever happens to have it open -- which is where it used to live, in
    the Xplorefinder session's view state, and therefore only for as long as
    that window stayed open and only for the person who set it.

    It is load-bearing rather than descriptive. The template decides how the
    array is divided into lines of contacts, and a CSD is only meaningful
    down one line: get it wrong on a dual implant and the derivative steps
    from hippocampus to M2 between two contacts and produces a number that
    is not a current sink and does not look wrong.

    `""` clears it, which is not the same as `h3` -- one says nobody has
    said, the other says somebody said it is a single array. `banks_for`
    already draws that distinction for regions and this follows it.
    """
    body = request.get_json(force=True) or {}
    want = body.get("probe")
    want = str(want).strip().lower() if want not in (None, "") else None
    if want and not probebook.get(want):
        return jsonify({"ok": False,
                        "error": "No probe template called %r." % want}), 400
    try:
        rec = REG.by_gid(gid)
        if not rec:
            return jsonify({"ok": False, "error": "No session " + gid}), 404
        patch = {"probe": want, "probe_source": "manual" if want else None}
        # Choosing a template with named regions IS somebody saying which
        # bank is which.
        #
        # `banks_for` refuses to guess a region, and it is right to: a
        # number of channels cannot tell you which probe went into
        # hippocampus. But picking "Dual array (hippocampus + M2)" is not a
        # guess -- it is a person naming the implant, and leaving the banks
        # blank afterwards would mean the same fact had to be entered twice
        # and could disagree with itself.
        #
        # Only ever fills a blank. A region somebody already set stands,
        # because this is the weaker statement of the two: the template says
        # what the montage usually is, and the bank says what this animal
        # was.
        banks = [dict(b) for b in (rec.get("channel_banks") or [])]
        if banks and want:
            cols = probebook.get(want) or {}
            named = [c for c in (cols.get("columns") or []) if c.get("region")]
            if len(named) == len(banks):
                touched = False
                who = (STORE.provenance() or {}).get("user")
                for bank, col in zip(banks, named):
                    if bank.get("region"):
                        continue
                    bank["region"] = col["region"]
                    bank["said_by"] = who
                    bank["said_via"] = "probe:" + want
                    touched = True
                if touched:
                    patch["channel_banks"] = banks
        rec = REG._patch(rec, patch)
    except Exception as exc:                             # noqa: BLE001
        return fail("registry/probe", exc, 400, {"gid": gid})
    STORE.record_activity([{
        "action": "registry.probe",
        "detail": {"gid": gid, "probe": want},
    }])
    return jsonify({"ok": True, "probe": (rec or {}).get("probe"),
                    "probe_source": (rec or {}).get("probe_source"),
                    "channel_banks": (rec or {}).get("channel_banks")})


@app.route("/api/vacc/browse")
def api_vacc_browse():
    """One level of the cluster's filesystem. `?path=` to go deeper."""
    try:
        cfg = vaccmod.load_config(LOGS_DIR)
        got = vaccmod.browse(cfg, request.args.get("path"))
    except Exception as exc:                             # noqa: BLE001
        return fail("vacc/browse", exc, 400,
                    {"path": request.args.get("path")})
    got["ok"] = True
    got["root"] = cfg.get("scratch_root")
    got["home"] = cfg.get("workspace")
    return jsonify(got)


@app.route("/api/vacc/scan", methods=["POST"])
def api_vacc_scan():
    """Walk a cluster folder and tell known recordings they also live there.

    Paths only. A recording found here that Jarvis has never met is
    REPORTED, not minted: a gid is permanent and everything in the lab hangs
    off it, so creating five hundred of them from a directory walk is a
    decision somebody should make deliberately and not a side effect of
    pressing Scan.

    What it does add is a path, which is exactly what `paths` is for --
    "every absolute path it has ever been opened from, on any machine".
    A cluster path is one more mount of the same recording, and everything
    downstream already knows how to show a path this computer cannot reach.

    `?dry=1` says what it would do and writes nothing.
    """
    body = request.get_json(force=True) or {}
    dry = bool(body.get("dry"))
    root = body.get("path")
    try:
        cfg = vaccmod.load_config(LOGS_DIR)
        found = vaccmod.inventory(cfg, root or cfg.get("scratch_root"))
    except Exception as exc:                             # noqa: BLE001
        return fail("vacc/scan", exc, 400, {"path": root})

    by_key, by_loose = _match_index()

    added, already, unmatched, ambiguous = [], [], [], []
    for row in found:
        ident = ids.identify(row["path"])
        # One rule, shared with the batch matcher -- see `_cluster_match`.
        rec, how, why = _cluster_match(row["path"], by_key, by_loose)
        if rec is None and why:
            ambiguous.append({"path": row["path"], "why": why})
            continue
        if rec is None:
            # Nobody here knows this recording. Whether it can BECOME one
            # depends on whether its folder names an animal and a session:
            # a gid is permanent and everything hangs off it, and one minted
            # for `ACTIVE_WHEEL_DATA/bw10` can never be matched to anything
            # by identity, so it would be a record that exists and cannot be
            # found. Measured: 84 of the 120 recordings on this cluster are
            # that shape.
            can_register = (ident.get("mouse") is not None
                            and ident.get("session") is not None)
            unmatched.append({"path": row["path"],
                              "n_channels": row.get("n_channels"),
                              "mouse": ident.get("mouse"),
                              "session": ident.get("session"),
                              "project": sessreg.guess_project(ident,
                                                               [row["path"]]),
                              "start": ident.get("start"),
                              "can_register": can_register,
                              "why": None if can_register else
                              "the folder does not name a mouse and a session"})
            continue
        entry = {"gid": rec["gid"], "label": rec.get("label") or rec.get("key"),
                 "path": row["path"], "how": how}
        if row["path"] in (rec.get("paths") or []):
            already.append(entry)
            continue
        if not dry:
            try:
                REG.add_path(rec["gid"], row["path"])
            except Exception as exc:                     # noqa: BLE001
                entry["error"] = str(exc)[:160]
        added.append(entry)

    # A recording whose first exposure is the cluster.
    #
    # Only the ones whose folder names an animal and a session. Registering
    # goes through `REG.ingest` -- the same call the local drive scanner
    # makes -- so a recording met on the cluster is registered by exactly the
    # rules a recording met on a drive is, and the gid it gets is the one a
    # local scan would later resolve to rather than a second record for the
    # same thing.
    registered = []
    to_register = [u for u in unmatched if u.get("can_register")]
    if body.get("register") and to_register and not dry:
        found_by_path = {r["path"]: r for r in found}
        rows = []
        for u in to_register:
            row = found_by_path.get(u["path"]) or {}
            rows.append({
                "path": u["path"],
                "identity": ids.identify(u["path"]),
                "channels": row.get("n_channels"),
            })
        try:
            new, seen = REG.ingest(rows, scan_id=None, root=root)
            registered = [{"path": r["path"],
                           "label": (r["identity"] or {}).get("label"),
                           "n_channels": r.get("channels")} for r in rows]
            unmatched = [u for u in unmatched if not u.get("can_register")]
            STORE.record_activity([{
                "action": "vacc.register",
                "detail": {"root": root, "new": new, "seen": seen},
            }])
        except Exception as exc:                         # noqa: BLE001
            return fail("vacc/register", exc, 400, {"root": root})

    if not dry and added:
        STORE.record_activity([{
            "action": "vacc.scan",
            "detail": {"root": root, "added": len(added),
                       "unmatched": len(unmatched)},
        }])
    return jsonify({"ok": True, "dry": dry, "root": root or cfg.get("scratch_root"),
                    "n_found": len(found),
                    "added": added, "already": already,
                    "unmatched": unmatched, "ambiguous": ambiguous,
                    "registered": registered,
                    "can_register": len(to_register)})


@app.route("/api/vacc/inventory")
def api_vacc_inventory():
    """What the cluster holds. `?force=1` walks it again rather than using
    the five-minute cache."""
    try:
        staged, unknown = _vacc_staged(force=bool(request.args.get("force")))
    except Exception as exc:                             # noqa: BLE001
        return fail("vacc/inventory", exc, 400)
    return jsonify({"ok": True, "staged": staged,
                    "n_staged": len(staged),
                    "unknown": unknown[:200], "n_unknown": len(unknown)})


@app.route("/api/vacc/knows")
def api_vacc_knows():
    """Which recordings the cluster can already read, keyed by gid.

    Read-only and offline: this is arithmetic over the registry's own paths
    plus a `net use` on this machine, and it answers even when the cluster is
    unreachable. Worth having on its own -- "nine of these are blocked here,
    and VACC can read all nine" is the sentence the whole feature is for.

    The arithmetic is cheap -- 0.05 s for 687 recordings. What is not cheap
    is `REG.all()` underneath it, which is four to eight seconds the first
    time a process asks, and this is one of the two calls the interface
    makes before anybody has clicked anything. Hence the warm path.
    """
    try:
        body, how = WARM.serve("vacc_knows", _vacc_knows_body,
                               fresh=bool(request.args.get("fresh")))
    except Exception as exc:                             # noqa: BLE001
        return fail("vacc/knows", exc, 400)
    body = dict(body)
    body["warm"] = WARM.marker("vacc_knows", how)
    return jsonify(body)


def _vacc_knows_body():
    """Raises rather than returning a response.

    A warmed builder hands back a plain dict, because the prime thread runs
    it outside any request and `jsonify` needs an application context. The
    route above turns a failure into the 400 this used to return directly.
    """
    cfg = vaccmod.load_config(LOGS_DIR)
    rows = [{"gid": r.get("gid"), "paths": r.get("paths") or []}
            for r in REG.all() if r.get("gid")]
    # What the cluster physically holds, so a recording it already has a
    # copy of is not reported as something to upload.
    #
    # `wait=False`: this renders on the Sessions view, and the walk that
    # answers it takes about ten seconds. Waiting for it made a page load
    # take thirteen and a half. The first call starts the walk and says
    # "not established" for the staged ones; the next call, a few seconds
    # later, has the answer. A slightly late chip is worth far more than
    # a view that does not appear.
    try:
        staged, _unknown = _vacc_staged(wait=False)
    except Exception:                                    # noqa: BLE001
        staged = {}
    got = vaccmod.resolve_many(rows, cfg, staged=staged)
    return {"ok": True, "knows": got,
            "counts": vaccmod.histogram(got),
            "n_rules": len(cfg.get("path_map") or []),
            "drives": vaccmod.drive_map()}


@app.route("/api/vacc/signin/state")
def api_vacc_signin_state():
    """What the guided sign-in needs to know before it asks anything.

    Read-only and offline: no connection is attempted, because this is what
    decides whether to OFFER to connect. A probe here would put a ten-second
    stall in front of a panel whose whole job is to explain why there is
    nothing to stall on yet.
    """
    cfg = vaccmod.load_config(LOGS_DIR)
    keys = vaccmod.existing_keys()
    return jsonify({
        "ok": True,
        "configured": bool(cfg.get("configured")),
        "netid": cfg.get("netid") or "",
        "host": cfg.get("host") or vaccmod.DEFAULT_HOST,
        "have_ssh": vaccmod.have_ssh(),
        "have_key": vaccmod.have_key(),
        "key_path": vaccmod.key_paths()[0],
        # Somebody who already uses the cluster from a terminal has a key
        # that works. Saying so lets setup offer to use it instead of
        # asking for a password to install a second one.
        "other_keys": [k for k in keys if not k["mine"]],
        "public_key": vaccmod.read_pubkey(),
    })


@app.route("/api/vacc/signin", methods=["POST"])
def api_vacc_signin():
    """Get this machine onto the cluster, from a netid and one password.

    The whole flow, in one request, because it is one thing from the
    person's point of view and splitting it across three would mean holding
    a password between them.

      1. make a key if there is not one
      2. log in with the password, answer Duo with a push, append the
         public key to `authorized_keys`
      3. throw the password away
      4. prove the key works by connecting again with the key ALONE
      5. only then write the config

    Step 4 is the one that makes this honest. Writing the config after step
    2 would record "signed in" on the strength of a password that is now
    gone -- and if the key did not actually take, the next poll fails with
    nothing left to retry with and no way to tell why.
    """
    body = request.get_json(force=True) or {}
    netid = (body.get("netid") or "").strip()
    password = body.get("password") or ""
    use_existing = (body.get("use_key") or "").strip()

    try:
        if use_existing:
            # An existing key the person nominated. Nothing to install and
            # no password to ask for -- just prove it works and write it
            # down. Refused if it is in the repository, same as `setup`.
            repo = os.path.dirname(APP_DIR)
            try:
                inside = os.path.commonpath(
                    [os.path.abspath(use_existing), repo]) == repo
            except ValueError:
                inside = False
            if inside:
                return jsonify({"ok": False,
                                "error": "That key is inside the repository. "
                                         "Move it to ~/.ssh first."}), 400
            key_path = use_existing
            made = {"created": False}
            installed = {"already": True, "netid": netid}
        else:
            made = vaccmod.make_key()
            key_path = vaccmod.key_paths()[0]
            installed = vaccmod.install_key(netid, password,
                                            duo=body.get("duo") or "1")
            netid = installed.get("netid") or netid

        # The proof. Key only, password auth off -- the ordinary `_ssh`
        # options, which is exactly how every later call will connect.
        check = dict(vaccmod.load_config(LOGS_DIR))
        check["netid"] = netid
        check["key_path"] = key_path
        who = vaccmod._ssh(check, "whoami", timeout=30).strip()
    except vaccmod.SSHError as exc:
        # `kind` rather than the text, so the page can say something useful
        # about a wrong password without parsing English.
        return jsonify({"ok": False, "error": str(exc),
                        "kind": getattr(exc, "kind", "failed")}), 400
    except Exception as exc:                             # noqa: BLE001
        return fail("vacc/signin", exc, 400, {"netid": netid})

    if who and who != netid:
        # The cluster says you are somebody else. Almost always a typo in
        # the netid that happened to match another account's key, and not
        # something to write into a config file.
        return jsonify({
            "ok": False, "kind": "mismatch",
            "error": "The key works, but the cluster says that account is "
                     "%r rather than %r. Check the netid." % (who, netid),
        }), 400

    vaccmod.save_config(LOGS_DIR, netid=netid, key_path=key_path,
                        enabled=True)
    vaccmod.refresh(force=True)
    STORE.record_activity([{
        "action": "vacc.signin",
        "detail": {"netid": netid, "made_key": bool(made.get("created")),
                   "key_was_there": bool(installed.get("already"))},
    }])
    return jsonify({
        "ok": True,
        "netid": netid,
        "key_path": key_path,
        "made_key": bool(made.get("created")),
        "already_installed": bool(installed.get("already")),
        "config": vaccmod.load_config(LOGS_DIR),
    })


@app.route("/api/vacc/setup", methods=["POST"])
def api_vacc_setup():
    """Record who this machine is on the cluster.

    Only the per-machine half. The tracked file -- where the cluster is, and
    which shares it mounts -- is a lab-wide fact edited in the repository and
    reviewed like any other change, not something one machine sets for
    everybody from a text box.
    """
    body = request.get_json(force=True) or {}
    netid = (body.get("netid") or "").strip()
    if netid and not re.match(r"^[a-z0-9._-]{2,32}$", netid, re.I):
        return jsonify({"ok": False,
                        "error": "That does not look like a NetID."}), 400
    key_path = (body.get("key_path") or "").strip()
    if key_path:
        repo = os.path.dirname(APP_DIR)
        try:
            inside = os.path.commonpath(
                [os.path.abspath(key_path), repo]) == repo
        except ValueError:
            inside = False
        if inside:
            # The one arrangement that turns "there is no secret here" into a
            # lie. Refused rather than warned about.
            return jsonify({
                "ok": False,
                "error": "That key is inside the repository. Move it to "
                         "~/.ssh and point at it there.",
            }), 400
    try:
        vaccmod.save_config(LOGS_DIR, netid=netid or None,
                            key_path=key_path or None,
                            account=(body.get("account") or "").strip() or None)
        vaccmod.refresh(force=True)
    except Exception as exc:                             # noqa: BLE001
        return fail("vacc/setup", exc, 400)
    STORE.record_activity([{"action": "vacc.setup",
                            "detail": {"netid": bool(netid)}}])
    return jsonify(vaccmod.status())


@app.route("/api/cloud/mirror", methods=["POST"])
def api_cloud_mirror():
    """Rewrite the Data Bank folder tree from the bank.

    Derived, so this can be run any time and deleting the tree is harmless.
    """
    try:
        return jsonify(dict(CLOUD.mirror_bank(APP_DIR), ok=True))
    except Exception as exc:                       # noqa: BLE001
        return fail("cloud/mirror", exc, 400)


@app.route("/api/cloud/status")
def api_cloud_status():
    cfg = CLOUD.cloud.reload()
    out = {
        "ok": True,
        "configured": CLOUD.cloud.configured,
        "project": cfg.get("project"),
        "url": cfg.get("url"),
        "auto": bool(cfg.get("auto")),
        "interval": cfg.get("interval"),
        # A project is set but this machine has not been told the key -- the
        # state a fresh clone is in, and what makes the panel ask.
        "needs_key": bool(cfg.get("needs_key")),
        "key_in_repo": bool(cfg.get("key_in_repo")),
        "machine": CLOUD.machine,
        "last": dict(_cloud_last),
        "state": CLOUD.cloud.state(),
    }
    if request.args.get("ping") and CLOUD.cloud.configured:
        out["ping"] = CLOUD.cloud.ping()
    return jsonify(out)


@app.route("/api/cloud/sync", methods=["POST"])
def api_cloud_sync():
    """Sync now, rather than waiting for the next tick."""
    body = request.get_json(silent=True) or {}
    res = cloud_sync_once(push=body.get("push", True),
                          pull=body.get("pull", True),
                          files=body.get("files", True))
    out = {"ok": bool(res.get("ok")), "last": res}
    # The reason at the top level, where the client's `api()` looks for it.
    # It only reads `error` there, so a failure whose reason sat one level
    # down in `last` was thrown away and reported as "Request failed (200)"
    # -- which is how a bug report about the sync arrived saying nothing at
    # all about why it failed.
    if not out["ok"]:
        out["error"] = (res.get("error")
                        or "The sync did not finish and did not say why.")
    return jsonify(out)


@app.route("/api/cloud/key", methods=["POST"])
def api_cloud_key():
    """Take the Supabase key from the Sync panel and keep it on this machine.

    A browser is not where I would choose to hand over a service-role
    credential, but the alternative in practice is somebody editing a JSON
    file, and the version of that which actually happens is the key ending up
    pasted into the repo. This server only listens on 127.0.0.1, and the key
    is written to GUI_logs/.cloud.json, which git ignores.

    The commonest mistake is pasting the publishable key -- they sit next to
    each other in the dashboard -- so that is caught by name rather than
    surfacing later as a permissions error that explains nothing.
    """
    body = request.get_json(force=True) or {}
    key = (body.get("key") or "").strip()
    ok, why = cloudmod.looks_like_a_key(key)
    if not ok:
        return jsonify({"ok": False, "error": why}), 400

    target = cloudmod.config_path(LOGS_DIR)
    if not _git_ignores(target):
        return jsonify({
            "ok": False,
            "error": "Refusing to save: git is not ignoring %s. Add "
                     "GUI_logs/.cloud.json to .gitignore first." % target,
        }), 400

    cloudmod.save_config(LOGS_DIR, key=key)
    CLOUD.cloud.reload()
    ping = CLOUD.cloud.ping()
    if not ping.get("reachable"):
        return jsonify({"ok": False, "saved": True,
                        "error": "Saved, but the project did not answer: %s"
                                 % str(ping.get("error"))[:200]}), 200
    if not ping.get("schema"):
        return jsonify({"ok": False, "saved": True,
                        "error": "Connected, but the tables are not there "
                                 "yet -- run the SQL in supabase/."}), 200
    STORE.record_activity([{"action": "cloud.key.set",
                            "detail": {"project": CLOUD.cloud.cfg
                                       .get("project")}}])
    return jsonify({"ok": True, "saved": True, "ping": ping})


def _git_ignores(path):
    """Would git pick this file up? Used before writing anything secret."""
    try:
        res = subprocess.run(["git", "check-ignore", "-q", path],
                             cwd=REPO_ROOT, capture_output=True, timeout=10)
        return res.returncode == 0
    except Exception:                              # noqa: BLE001
        return False        # cannot tell, so do not write


@app.route("/api/cloud/config", methods=["POST"])
def api_cloud_config():
    """Turn the sync on or off, and set how often.

    Deliberately cannot set the key: a browser is the wrong place to hand
    over a service-role credential, and tools/cloud_setup.py already refuses
    to write it anywhere git can see.
    """
    body = request.get_json(force=True) or {}
    patch = {}
    for k in ("auto", "enabled", "upload_results"):
        if k in body:
            patch[k] = bool(body[k])
    if "interval" in body:
        patch["interval"] = max(5, int(body["interval"]))
    if not patch:
        return jsonify({"ok": False, "error": "Nothing to change."}), 400
    cloudmod.save_config(LOGS_DIR, **patch)
    CLOUD.cloud.reload()
    return jsonify({"ok": True, "config": CLOUD.cloud.cfg})


# ==========================================================================
# A readable console
# ==========================================================================
# The dev server logs every request, and the polled routes drown out
# everything else -- a real 500 scrolls past in under a second. These lines
# are suppressed; the requests themselves are untouched and still show up in
# the in-app request trace.
#
# Errors are never quiet: anything that is not a 2xx/3xx still prints, so a
# route that starts failing is as loud as it ever was.
import logging as _logging

_QUIET_PATHS = (
    "/api/link", "/api/job/", "/api/activity", "/api/debug",
    "/api/results/file", "/api/outputs/file",
    "/api/video/clip", "/api/video/frame",
)

# The rest of the pollers -- but on GET only, which is the difference
# between reading a thing and doing one.
#
# These cannot join the tuple above, because that one silences both verbs:
# "/api/curation" there would take "POST /api/curation/decide" with it, and
# a curation decision is exactly the kind of line worth keeping. Same for
# "/api/registry", whose POSTs are somebody rescanning or forgetting a
# recording.
_QUIET_GETS = (
    "/api/sync/status", "/api/sync/progress", "/api/warm/state",
    "/api/presence", "/api/toolfeed", "/api/registry", "/api/curation",
    "/api/video/convert/status", "/api/vacc/status",
)

# The interface itself: 34 files on a cold load, and the access line for
# each one is noise by definition -- nobody debugs a 200 on app.css.
#
# They were not covered before because every rule above starts "/api/", and
# these do not. A page load therefore printed 35+ lines, and Python's
# logging holds one global handler lock, so request threads queue behind
# each other to write them.
#
# That queueing has a sharp edge worth knowing about: if the Jarvis console
# window is put into QuickEdit selection mode -- a stray click in it is
# enough -- Windows blocks every write to it until the selection is
# cleared, and the whole server stops with it. Fewer writes is a smaller
# window for that, not a fix for it.
_QUIET_SUFFIXES = (".js", ".css", ".map", ".svg", ".png", ".ico",
                   ".woff", ".woff2", ".jpg", ".jpeg", ".gif", ".webp")


class _QuietPolls(_logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
            # Werkzeug's access line: '"GET /path HTTP/1.1" 200 -'
            if '" 2' not in msg and '" 3' not in msg:
                return True                      # never hide a failure
            for p in _QUIET_PATHS:
                if ('GET ' + p) in msg or ('POST ' + p) in msg:
                    return False
            # Pulled apart rather than matched: this module has no `re`, and
            # the one thing worse than a noisy log is a filter that throws
            # into its own except and quietly stops filtering.
            i = msg.find('"GET ')
            if i >= 0:
                path = msg[i + 5:].split(" ", 1)[0].split("?", 1)[0]
                if path.lower().endswith(_QUIET_SUFFIXES):
                    return False
                for p in _QUIET_GETS:
                    if path == p or path.startswith(p + "/"):
                        return False
        except Exception:                        # noqa: BLE001
            return True
        return True


_logging.getLogger("werkzeug").addFilter(_QuietPolls())
