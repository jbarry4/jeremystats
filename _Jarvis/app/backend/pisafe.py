"""
pisafe.py -- the PI's practice layer.

2026-11-20. On the PI's computer everything can be opened, looked at and
tried -- saves, deletes, pushes -- but none of it becomes permanent, and all
of it can be put back in one step.

What was decided (2026-11-20)
-----------------------------
  * WHO. This computer's real profile says the name "Jeremy Barry", the role
    PI (or Principal Investigator), or the email jbarry4@uvm.edu. Read from
    the real profile shard only, so a profile edited inside the layer can
    neither switch it off nor on.
  * NOTHING ON SCREEN says so. Every save, delete and push answers the way
    it always does.
  * KEPT until a lab member reverts it -- `tools/pisafe.py revert` on that
    computer, or POST /api/pisafe {"action": "revert"} -- across restarts,
    and thrown away by itself 14 days after the layer began.
  * WHAT LEAVES THE COMPUTER looks done and does nothing: nothing is written
    to the shared database, nothing is uploaded to or started on the VACC,
    nothing is published, emailed or written to a lab sheet. Downloads still
    come in, so everything everyone else has done is there to look at.

How
---
  shards.py  the layer itself. Records are written under "pisafe-<machine>"
             and read with this machine's own on top; deleting one hides it.
             Never committed (.gitignore), never read by another machine.
  cloud.py   every write to the shared database answered here, not sent.
  cloudsync  push, deletions and figure uploads do nothing; the pull, the
             Data Bank mirror and the tombstone sweep run in the real view
             (app.cloud_sync_once), so colleagues' work still arrives in the
             real records and nothing from the layer is copied into them.
  HELD       the routes below, answered {"ok": true} without running.
  vacc.py    a backstop: no sbatch, scancel, rm, mv or upload through ssh.

Revert deletes the layer's files and its hidden list. The real records were
never touched, so there is nothing else to put back.

`Jarvis_PISAFE=1` (or 0) in the environment forces it either way, for tests.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone

from . import shards

NAMES = {"jeremy barry"}
ROLES = {"pi", "principal investigator"}
EMAILS = {"jbarry4@uvm.edu"}
KEEP_DAYS = 14

#: Mutating routes that reach outside this computer (or delete files a Book
#: does not own). Answered as done, never run, while the layer is on.
HELD = [re.compile(p) for p in (
    # the shared database's own settings
    r"^/api/cloud/(key|config|mirror|active)$",
    # the VACC: uploads, tidying, starting and stopping lab jobs. NOT
    # signing in, setting up or adding found recordings (2026-11-20: "The PI
    # can't load recordings from the VACC"): those are this computer's own
    # account and records, and reading from the cluster needs them.
    r"^/api/vacc/(upload|found/tidy)$",
    r"^/api/arc/monolith/(run|upload|forget|stop|cancel)$",
    r"^/api/arc/precon/(run|resume|forget|stop)$",
    r"^/api/arc/(circuit|drift|coupling)/.*run$",
    r"^/api/er2/run(/[^/]+/(resume|stop|refresh))?$",
    r"^/api/(incisor|doppler)/batch$",
    r"^/api/aibeta/train$",
    r"^/api/kilosort/(install|run)$",
    # publishing, email, the lab's sheets
    r"^/api/arc/monolith/joeexport/site$",
    r"^/api/inside/week/email$",
    r"^/api/(softmouse|vos)/apply$",
    r"^/api/(softmouse/forget|vos/config)$",
    # code changes and code runs
    r"^/api/floss/(install|use|undo|unlock|ask)$",
    r"^/api/scratch/run$",
    # files deleted outright
    r"^/api/results/delete$",
    r"^/api/panorama/sets/[^/]+/delete$",
    # the test routes that clear real things
    r"^/api/(people/_test_purge|presence/_test_clear|presence/_test_ghost"
    r"|artifacts/_test/erase|artifacts/_test/make|debug/clear)$",
)]

_LOCK = threading.Lock()
_STATE = {"logs": None}


def _norm(text):
    return " ".join(str(text or "").lower().split())


def matches(rec):
    """Is this profile the PI's?"""
    rec = rec or {}
    if _norm(rec.get("name")) in NAMES:
        return True
    role = _norm(rec.get("role")).replace(".", "")
    if role in ROLES:
        return True
    return _norm(rec.get("email")) in EMAILS


def state_dir(logs_dir):
    return os.path.join(logs_dir, ".pisafe")


def real_profile(logs_dir):
    """This computer's real profile record, never the layer's."""
    path = os.path.join(logs_dir, "prefs", "profile%s%s.json"
                        % (shards.SIGIL, shards.real_machine_id()))
    return shards._read_json(path) or {}


def _forced():
    v = str(os.environ.get("Jarvis_PISAFE") or "").strip().lower()
    if v in ("1", "on", "true", "yes"):
        return True
    if v in ("0", "off", "false", "no"):
        return False
    return None


def _started(logs_dir):
    got = shards._read_json(os.path.join(state_dir(logs_dir), "started.json"))
    return got if isinstance(got, dict) else None


def _age_days(stamp):
    try:
        t = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 86400.0


def decide(logs_dir):
    """Turn the layer on or off for this computer, from its real profile.

    Called at start-up before the first record is opened, and again after
    a profile is saved. Old layers (KEEP_DAYS) are thrown away here.
    """
    with _LOCK:
        _STATE["logs"] = os.path.abspath(logs_dir)
        forced = _forced()
        on = forced if forced is not None else matches(real_profile(logs_dir))
        sd = state_dir(logs_dir)
        if on:
            os.makedirs(sd, exist_ok=True)
            began = _started(logs_dir)
            age = _age_days((began or {}).get("at"))
            if began and age is not None and age > KEEP_DAYS:
                shards.configure_safe(False, sd)
                _revert_files(logs_dir)
                began = None
            if not began:
                shards.write_json_atomic(
                    os.path.join(sd, "started.json"),
                    {"at": datetime.now(timezone.utc).isoformat(),
                     "machine": shards.real_machine_id(),
                     "forced": forced is not None})
        shards.configure_safe(on, sd)
        return on


def _layer_files(logs_dir):
    """Every file the layer wrote, by name: anywhere in GUI_logs but the
    cache (a walk of ~13,000 files, under a tenth of a second), and in the
    folders it noted, which may be inside the cache."""
    tag = shards.SIGIL + shards.SAFE_PREFIX
    seen, out = set(), []
    root = os.path.abspath(logs_dir)
    dirs = set(shards.safe_touched())
    got = shards._read_json(os.path.join(state_dir(logs_dir), "touched.json"))
    if isinstance(got, list):
        dirs.update(os.path.abspath(d) for d in got)
    for here, subs, _files in os.walk(root):
        if here == root:
            subs[:] = [s for s in subs if s != ".cache"]
        dirs.add(here)
    for d in sorted(dirs):
        # Only ever inside GUI_logs, whatever the list says.
        if os.path.commonpath([root, os.path.abspath(d)]) != root:
            continue
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            if tag in name:
                p = os.path.join(d, name)
                if p not in seen:
                    seen.add(p)
                    out.append(p)
    return out


def _revert_files(logs_dir):
    files = _layer_files(logs_dir)
    removed, failed = 0, []
    for p in files:
        try:
            os.remove(p)
            removed += 1
        except OSError as exc:
            failed.append("%s: %s" % (os.path.basename(p), exc))
    sd = state_dir(logs_dir)
    for name in ("hidden.json", "touched.json", "started.json"):
        try:
            os.remove(os.path.join(sd, name))
        except OSError:
            pass
    return {"removed": removed, "failed": failed}


def revert(logs_dir=None):
    """Throw the layer away. The real records were never touched."""
    logs_dir = logs_dir or _STATE["logs"]
    with _LOCK:
        was_on = shards.safe_on()
        sd = state_dir(logs_dir)
        out = _revert_files(logs_dir)
        shards.configure_safe(was_on, sd)
        if was_on:
            shards.write_json_atomic(
                os.path.join(sd, "started.json"),
                {"at": datetime.now(timezone.utc).isoformat(),
                 "machine": shards.real_machine_id(), "after_revert": True})
        out["on"] = was_on
        return out


def status(logs_dir=None):
    logs_dir = logs_dir or _STATE["logs"]
    files = _layer_files(logs_dir)
    size = 0
    for p in files:
        try:
            size += os.path.getsize(p)
        except OSError:
            pass
    hidden = shards._read_json(os.path.join(state_dir(logs_dir), "hidden.json"))
    n_hidden = sum(len(t) for t in (hidden or {}).values()
                   if isinstance(t, dict))
    began = _started(logs_dir) or {}
    age = _age_days(began.get("at"))
    return {"on": shards.safe_on(), "started": began.get("at"),
            "clears_in_days": (None if age is None
                               else max(0.0, round(KEEP_DAYS - age, 1))),
            "files": len(files), "bytes": size, "hidden": n_hidden,
            "machine": shards.real_machine_id(),
            "who": {k: real_profile(logs_dir).get(k)
                    for k in ("name", "role", "email")}}


def held(path, method):
    """Is this request one the layer answers without running?"""
    if not shards.safe_on() or method in ("GET", "HEAD", "OPTIONS"):
        return False
    return any(p.match(path) for p in HELD)


def install(app, logs_dir):
    from flask import jsonify, request

    @app.before_request
    def _pisafe_hold():
        if held(request.path, request.method):
            return jsonify({"ok": True, "held": True})
        return None

    @app.route("/api/pisafe", methods=["GET", "POST"])
    def api_pisafe():
        if request.method == "GET":
            return jsonify(dict(status(logs_dir), ok=True))
        body = request.get_json(force=True, silent=True) or {}
        if body.get("action") == "revert":
            got = revert(logs_dir)
            return jsonify(dict(got, ok=not got["failed"],
                                status=status(logs_dir)))
        return jsonify({"ok": False, "error": "action must be 'revert'"}), 400


def refuse_outward(what):
    """For a code path that would change something off this computer: raise
    while the layer is on. The routes above stop the known ones; this is
    the net under them."""
    if shards.safe_on():
        raise Held("%s was not sent." % what)


class Held(RuntimeError):
    pass
