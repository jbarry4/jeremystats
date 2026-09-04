"""
app.py -- The BARRY GUI local server.

Serves the single-page frontend and a JSON API over the repo and the data.
Binds to 127.0.0.1 only: this is a local workbench, not a service.

Cross-platform: everything OS-specific is delegated to sysinfo, so the same
code runs on Windows and macOS.
"""
from __future__ import annotations

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

from . import (analysis, cloud as cloudmod, cloudsync, compose, csc,
               curation, discovery, eventbank, events, export, extras, ids,
               demo as demomod,
               dsimport,
               feedback as feedbackmod,
               profile as profilemod,
               layers, live, mice as micebook, nlx, pipeline, prewarm,
               probes as probebook, rebuild,
               registry, results, runner, sessreg, shards, spikesort, store,
               storyboard, sysinfo, toolkit, video)

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
WEB_DIR = os.path.join(APP_DIR, "web")
REPO_ROOT = os.path.abspath(os.path.join(APP_DIR, ".."))
LOGS_DIR = os.path.join(APP_DIR, "GUI_logs")

app = Flask(__name__, static_folder=None)

STORE = store.Store(LOGS_DIR, auto_stage=False)
# Reports live beside the logs, one file each, sharded by machine -- same
# rule as everything else that gets edited, so two people never write the
# same file.
FEEDBACK = feedbackmod.Feedback(LOGS_DIR)
# Who you are, said once. Everything attributed -- curation, banking, layer
# sheets, figures, runs -- goes through STORE.provenance(), which prefers
# this over the git identity. Wired after the Store exists because it needs
# one, and back onto it so provenance() can see it.
PROFILE = profilemod.Profile(LOGS_DIR, STORE)
STORE.profile = PROFILE

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
        # A finished scan is the one moment BARRY has the whole picture of a
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


def _body_session(body):
    return _session_for(body.get("path", ""),
                        _even_only_arg(body),
                        bool(body.get("invert", True)))


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
    out["bookmarks"] = (stored or {}).get("bookmarks", [])
    out["spike_sets"] = ((stored or {}).get("spike_labels") or {}).get("sets", [])
    out["event_classes"] = (stored or {}).get("event_classes") or {}
    return jsonify(out)


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
            spacing_um=float(body.get("spacing_um", 50) or 50))
    except Exception as exc:
        return fail("csc/window", exc, 400, {"path": body.get("path")})
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
    return jsonify({"ok": True, "sessions": STORE.all_sessions()})


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


@app.route("/api/sync/status")
def api_sync_status():
    idx = None
    try:
        # index() rebuilds only when the store has actually changed; this
        # route is hit on every boot and after every export.
        idx = STORE.index()
    except Exception:
        pass
    return jsonify({"ok": True, "git": STORE.git_status(),
                    "root": LOGS_DIR, "index": idx,
                    "auto_stage": STORE.auto_stage,
                    "conflicts": conflict_audit()})


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
        saved = save_output(blob, name, subdir=ident.get("label"))
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


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "repo": REPO_ROOT,
                    "matlab": runner.MATLAB_EXE,
                    "ffmpeg": sysinfo.find_ffmpeg(),
                    "python": sys.executable, "scipy": csc.HAVE_SCIPY,
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
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        entries = body.get("entries")
        if entries is None:
            entries = body.get("entry") or []
        n = STORE.record_activity(entries)
        return jsonify({"ok": True, "written": n})
    return jsonify({
        "ok": True,
        "activity": STORE.list_activity(
            limit=int(request.args.get("limit", 500)),
            day=request.args.get("day") or None,
            action=request.args.get("action") or None,
            session_key=request.args.get("session") or None),
        "days": STORE.activity_days(),
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


def save_output(blob, filename, subdir=None):
    """Write an exported file into the Output folder and report where it went."""
    d = outputs_dir()
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
# output so a MATLAB figure is cataloged even though BARRY did not make it.
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
    """Every layer sheet, for the ToolKit list."""
    out = []
    for rec in LAYERS.all():
        row = LAYERS.summary(rec)
        sess = REG.by_gid(rec.get("gid"))
        row["session"] = REG.summary(sess) if sess else None
        out.append(row)
    out.sort(key=lambda r: -(r.get("progress", {}).get("labelled") or 0))
    return jsonify({"ok": True, "sheets": out, "regions": layers.REGIONS})


@app.route("/api/layers/<gid>")
def api_layers_get(gid):
    rec = LAYERS.get(gid)
    if not rec:
        return jsonify({"ok": False, "error": "No layer sheet yet."}), 404
    return jsonify({"ok": True, "sheet": LAYERS.summary(rec),
                    "session": _session_by_gid(gid)})


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
    head = ("# BARRY GUI layer labels -- %s -- %d of %d channels labelled "
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
    """The registry record a curation set belongs to."""
    rec = REG.by_gid(gid)
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


@app.route("/api/curation")
def api_curation_list():
    """Every curation set, with how far through each one is."""
    out = []
    for row in CURATE.summaries():
        rec = REG.by_gid(row["gid"])
        row["session"] = REG.summary(rec) if rec else None
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
                    "session": _session_by_gid(gid)})


@app.route("/api/curation/create", methods=["POST"])
def api_curation_create():
    """Import candidates. They all arrive unspecified, on purpose."""
    body = request.get_json(force=True) or {}
    gid = body.get("gid")
    kind = body.get("kind")
    try:
        sess = _cur_session(gid)
        rec, n = CURATE.create(
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
                   "total": len(rec.get("events") or []),
                   "source": (body.get("source") or {}).get("from")},
        "session": {"key": sess.get("key"), "label": sess.get("label")},
    }])
    return jsonify({"ok": True, "added": n, "set": CURATE.summary(rec)})


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


@app.route("/api/curation/<gid>/<kind>/delete", methods=["POST"])
def api_curation_delete(gid, kind):
    ok = CURATE.delete(gid, kind)
    STORE.record_activity([{"action": "curation.delete",
                            "detail": {"gid": gid, "kind": kind}}])
    return jsonify({"ok": ok})


@app.route("/api/curation/<gid>/<kind>/bank", methods=["POST"])
def api_curation_bank(gid, kind):
    """Send the curated events to the Event Bank, one entry per category."""
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
                         or "BARRY curation (" + kind + ")"),
            "added_by": body.get("added_by"),
            "version_note": body.get("note"),
            # What the bank needs to tell a guess from a decision.
            "curated": True,
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
    head = ("# BARRY GUI event curation -- %s -- %s -- %d of %d specified "
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

def _attachments(rec):
    """What is hanging off this recording, counted for the housekeeping view.

    Counted rather than listed: the view wants to say "3 figures, 1 deck" at a
    glance and fetch the detail only when a row is opened.
    """
    key = rec.get("key")
    loose = rec.get("loose_key")
    label = rec.get("label")
    paths = set(rec.get("paths") or [])

    figures = 0
    for r in RESULTS.catalog():
        if (r.get("session_key") and r["session_key"] == key) \
                or (label and r.get("session_label") == label) \
                or (r.get("session_path") in paths):
            figures += 1

    decks = 0
    for d in RESULTS.list_decks():
        if label and label in (d.get("title") or ""):
            decks += 1

    banked = 0
    try:
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
        "layers": len((LAYERS.get(rec.get("gid")) or {}).get("labels") or {}),
        "ds": sum((CURATE.progress(c).get("total") or 0) for c in [CURATE.get(rec.get("gid"), k) for k in curation.KINDS] if c),
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
    """Every recording BARRY has met, as a project / mouse / session tree."""
    if request.args.get("backfill"):
        REG.backfill()
    tree = REG.tree(_attachments)
    if not request.args.get("no_demo"):
        # Last, so real data is what you see first -- but always there, so
        # a machine with nothing mounted is not an empty application.
        tree = list(tree) + [_demo_project()]
    return jsonify({
        "ok": True,
        "projects": REG.projects(),
        "known_projects": list(sessreg.KNOWN_PROJECTS),
        "tree": tree,
        "demo_paths": [demomod.path_for(s)
                       for s in demomod.SESSIONS.values()],
        "total": len([r for r in REG.all() if not r.get("retired")]),
        # So the tree can branch on any of them without a second round trip.
        "mice": MICE.index(),
        "attributes": MICE.attributes(),
    })


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
            rec = REG.set_project(gid, body["project"])
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
    recording drive is touched -- BARRY does not delete data it did not
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
    """Drop a record entirely.

    For a recording that should never have been registered -- a scratch copy,
    a test tree, a folder that was moved and re-registered under a new name.
    The recording itself is untouched; only what BARRY remembers about it
    goes. Opening or scanning it again starts a fresh record.
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
    """
    sessions = STORE.all_sessions()
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
        picked = toolkit.select(STORE.all_sessions(), **args)
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
        picked = toolkit.select(STORE.all_sessions(), **args)
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
    head = ("# BARRY GUI bad-channel export -- %s -- %d row(s) from %d "
            "session(s) -- taken %s\n"
            % (toolkit.scope_label(**args), len(rows), len(picked), stamp))
    text = head + body

    stem = toolkit.filename(form, **args)
    name = "%s_%s.csv" % (stem, time.strftime("%Y%m%d_%H%M%S"))

    saved = None
    try:
        saved = save_output(text.encode("utf-8"), name, subdir="ToolKit")
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
        saved = save_output(blob, name, subdir="Storyboards")
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
                "Run the setup script, or set BARRY_MATLAB to the executable.")
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
            out.append(extras.session_health(p, deep=deep))
        except Exception as exc:
            out.append({"path": p, "level": "bad", "checks": [
                {"level": "bad", "name": "check failed", "message": str(exc)}]})
    STORE.record_activity([{
        "action": "session.health",
        "detail": {"n": len(out), "deep": deep,
                   "levels": [o.get("level") for o in out]},
    }])
    return jsonify({"ok": True, "reports": out})


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
    try:
        res = extras.overview(sess, channel=body.get("channel"),
                              bins=int(body.get("bins") or
                                       extras.OVERVIEW_BINS))
    except Exception as exc:
        return fail("csc/overview", exc, 400, {"path": body.get("path")})
    return jsonify(res)


# ==========================================================================
# Errors: grouping and triage
# ==========================================================================
@app.route("/api/errors/grouped")
def api_errors_grouped():
    recs = STORE.list_errors(limit=int(request.args.get("limit", 600)),
                             day=request.args.get("day") or None)
    book = STORE.resolved_errors()

    # An occurrence counts as resolved only if it happened BEFORE somebody
    # said so. Marking a signature resolved used to hide it forever, so a bug
    # that came back after being fixed was filed under a resolved group and
    # never shown again -- which is the one case where you most want to see
    # it. A recurrence reopens the group and says when it started again.
    for r in recs:
        mark = book.get(extras.signature(r))
        r["resolved"] = bool(mark) and (r.get("at") or "") <= (mark.get("at") or "")

    groups = extras.group_errors(recs)
    for g in groups:
        mark = book.get(g["signature"])
        if not mark:
            continue
        g["resolved_at"] = mark.get("at")
        g["resolved_by"] = mark.get("by")
        g["resolved_note"] = mark.get("note")
        if not g["resolved"]:
            # It was closed and has happened again since.
            g["reopened"] = True
            g["reopened_at"] = next(
                (r.get("at") for r in reversed(g["records"])
                 if (r.get("at") or "") > (mark.get("at") or "")),
                g.get("last"))
    return jsonify({"ok": True, "groups": groups, "days": STORE.error_days(),
                    "total": len(recs),
                    "unresolved": sum(1 for g in groups if not g["resolved"]),
                    "reopened": sum(1 for g in groups if g.get("reopened"))})


@app.route("/api/errors/resolve", methods=["POST"])
def api_errors_resolve():
    body = request.get_json(force=True) or {}
    sigs = body.get("signatures") or ([body["signature"]]
                                      if body.get("signature") else [])
    resolved = body.get("resolved", True)
    for sig in sigs:
        STORE.resolve_error(sig, bool(resolved), body.get("note"))
    STORE.record_activity([{
        "action": "error.resolve",
        "detail": {"n": len(sigs), "resolved": bool(resolved),
                   "note": body.get("note")},
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
        "BARRY GUI diagnostic bundle",
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
    L.append("BARRY GUI debug report")
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
        saved = save_output(
            text.encode("utf-8"),
            "debug-report-%s.txt" % time.strftime("%Y%m%d_%H%M%S"),
            subdir="Debug")
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
REG = sessreg.Registry(STORE)
CURATE = curation.Curation(LOGS_DIR, STORE)
LAYERS = layers.Layers(LOGS_DIR, STORE)
MICE = micebook.MouseBook(LOGS_DIR, STORE)


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
        "detail": {"id": rec["id"], "project": rec["project"],
                   "mouse": rec["mouse"], "session": rec["session"],
                   "type": rec["type"], "n": rec["n"],
                   "pipeline": rec["source"]["pipeline"]},
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
# recorded as a run like everything else BARRY launches.
@app.route("/api/kilosort/check")
def api_kilosort_check():
    """What this machine has, and what it is missing."""
    return jsonify(spikesort.jsonsafe(dict(
        spikesort.check(REPO_ROOT, request.args.get("python")), ok=True)))


@app.route("/api/kilosort/plan", methods=["POST"])
def api_kilosort_plan():
    """What a run would do, before anything is launched.

    Bad channels come from BARRY's own record of the recording when the
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

    Phy is a desktop app with its own window; BARRY starts it and gets out of
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
# BARRY writes locally first, always. The files are what make it work on a
# rig with no network and on a drive that is not mounted; this pushes what
# they hold to Postgres and brings back what other machines have changed.
# Nothing here is on the critical path of anything: if the sync is down,
# BARRY carries on and catches up later.
# ==========================================================================
CLOUD = cloudsync.Sync(
    LOGS_DIR, STORE, bank=BANK, curate=CURATE, layers=LAYERS, mice=MICE,
    results=None, repo_root=REPO_ROOT)

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
    if not CLOUD.cloud.configured:
        return dict(_cloud_last, error="not configured")
    if not _cloud_lock.acquire(blocking=False):
        return dict(_cloud_last, error="a sync is already running")
    try:
        _cloud_last["running"] = True
        _cloud_results()
        out = {"pushed": 0, "pulled": 0}
        if pull:
            got = CLOUD.pull()
            out["pulled"] = sum(v for v in (got.get("applied") or {}).values()
                                if isinstance(v, int))
        if push:
            # Deletions first: a push that re-sends a row we have locally
            # deleted would undo the tombstone it is about to write.
            out["deleted"] = CLOUD.push_deletions().get("marked", 0)
            sent = CLOUD.push(include_history=True)
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
        # the automatic sync stands down until BARRY is restarted -- by which
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
        _cloud_lock.release()
    return dict(_cloud_last)


def _cloud_loop():
    """Background sync. Pull first, so a push never sends a stale edit over
    somebody else's newer one -- the database would reject it anyway, but
    losing the race locally means the next pull just undoes your screen."""
    time.sleep(20)          # let the app finish starting
    while True:
        cfg = CLOUD.cloud.reload()
        base = max(30, int(cfg.get("interval") or 120))
        # Held off entirely while something is wrong that retrying cannot
        # fix -- see the clock case in cloud_sync_once. A manual sync clears
        # the flag by succeeding.
        if (cfg.get("enabled") and cfg.get("auto")
                and not _cloud_last.get("blocked")):
            cloud_sync_once(files=cfg.get("upload_results", True))
        # Back off while it is failing, up to half an hour. Something that is
        # down stays down; retrying every two minutes for a day is just noise
        # in somebody's network logs and ours.
        fails = _cloud_last.get("failures", 0)
        wait = base * min(2 ** fails, 16) if fails else base
        time.sleep(min(wait, 1800))


if CLOUD.cloud.configured and CLOUD.cloud.cfg.get("auto"):
    threading.Thread(target=_cloud_loop, daemon=True,
                     name="barry-cloud-sync").start()


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
    return jsonify({"ok": bool(res.get("ok")), "last": res})


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
        patch["interval"] = max(30, int(body["interval"]))
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
        except Exception:                        # noqa: BLE001
            return True
        return True


_logging.getLogger("werkzeug").addFilter(_QuietPolls())
