"""Extraction Room 2.0's routes (backend/er2run.py does the work).

Kept out of app.py like figroutes.py: `install(app, A)` is called once with
the app module, whose LOGS_DIR, APP_DIR, ARTIFACTS and fail() are read off it
when a request needs them.

  GET  /api/er2                      bundles, runs, what can be asked, the bar
  POST /api/er2/amber                freeze a new bundle from the battery folder
  GET  /api/er2/amber/status         how that is going
  POST /api/er2/run                  make a run and start it (here or on the VACC)
  GET  /api/er2/run/<rid>            the run, its progress, its leaderboard
  POST /api/er2/run/<rid>/refresh    VACC: ask slurm, bring answers home
  POST /api/er2/run/<rid>/stop       stop here / cancel on the VACC
  POST /api/er2/run/<rid>/resume     here: carry on with the unanswered tasks
  GET  /api/er2/run/<rid>/task/<i>   one task's whole answer
"""
from __future__ import annotations

import json
import os
import threading

from flask import jsonify, request

from . import er2run as R
from .er2 import amber as AMB
from .er2 import engine as E

CONFIG = os.path.join(AMB.ROOT, "config.json")
_AMBER = {"state": "idle", "log": []}


def _cfg():
    try:
        return json.load(open(CONFIG, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cfg(**kw):
    c = _cfg()
    c.update(kw)
    os.makedirs(AMB.ROOT, exist_ok=True)
    tmp = CONFIG + ".part"
    json.dump(c, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, CONFIG)


def _bundles():
    out = []
    if not os.path.isdir(AMB.AMBER):
        return out
    for d in sorted(os.listdir(AMB.AMBER)):
        mf = os.path.join(AMB.AMBER, d, "manifest.json")
        if os.path.isfile(mf):
            m = json.load(open(mf, encoding="utf-8"))
            fams = {}
            for f in m["event_families"]:
                fams[f] = fams.get(f, 0) + 1
            out.append({"version": m["version"], "made": m["made"], "n_events": m["n_events"], "n_mice": len(m["mice"]),
                        "n_event_features": len(m["event_features"]), "n_mouse_features": len(m["mouse_features"]),
                        "event_families": fams, "classifier": m["classifier"], "event_set": m["event_set"],
                        "mice": m["mice"], "source": m.get("source")})
    return out[::-1]


def install(app, A):
    R.APP = A          # its ARTIFACTS is made later in app.py; read when needed

    @app.route("/api/er2")
    def api_er2():
        return jsonify({"ok": True, "bundles": _bundles(), "runs": R.runs(), "targets": list(E.TARGETS), "views": list(E.VIEWS),
                        "models": list(E.MODELS), "bar": E.BAR, "source": _cfg().get("source"),
                        "amber": {k: _AMBER[k] for k in ("state", "error") if k in _AMBER}})

    @app.route("/api/er2/amber", methods=["POST"])
    def api_er2_amber():
        body = request.get_json(force=True) or {}
        src = body.get("source") or _cfg().get("source")
        if not src or not os.path.isdir(src):
            return A.fail("er2/amber", ValueError("Say where the battery folder is (it holds data/ds_v6.pkl)."), 400, {})
        if _AMBER["state"] == "running":
            return jsonify({"ok": True, "state": "running"})
        _save_cfg(source=src)
        _AMBER.update(state="running", log=[], error=None)

        def work():
            try:
                man = AMB.build(src, log=lambda s: _AMBER["log"].append(s))
                _AMBER.update(state="done", version=man["version"])
            except Exception as exc:                      # noqa: BLE001
                _AMBER.update(state="failed", error="%s: %s" % (type(exc).__name__, exc))
        threading.Thread(target=work, daemon=True, name="er2-amber").start()
        return jsonify({"ok": True, "state": "running"})

    @app.route("/api/er2/amber/status")
    def api_er2_amber_status():
        return jsonify({"ok": True, "state": _AMBER["state"], "error": _AMBER.get("error"), "version": _AMBER.get("version"),
                        "log": _AMBER["log"][-8:]})

    @app.route("/api/er2/run", methods=["POST"])
    def api_er2_run():
        b = request.get_json(force=True) or {}
        try:
            run = R.new_run(targets=b.get("targets") or E.TARGETS, views=b.get("views") or E.VIEWS, models=b.get("models") or E.MODELS,
                            amber_version=b.get("amber_version"), where=b.get("where") or "local", n_shuffle=int(b.get("n_shuffle") or 0),
                            explain=b.get("explain", True), drop=b.get("drop", True), note=b.get("note") or "", by=A.who() if hasattr(A, "who") else None)
            if run["where"] == "vacc":
                cfg = A.vaccmod.load_config(A.LOGS_DIR)
                if not (cfg or {}).get("configured"):
                    raise ValueError("Sign in to the VACC first (Setup).")
                run = R.submit_vacc(cfg, run["rid"], A.APP_DIR)
            else:
                R.start_local(run["rid"])
        except Exception as exc:                          # noqa: BLE001
            return A.fail("er2/run", exc, 400, {})
        return jsonify({"ok": True, "run": _run_view(run["rid"])})

    def _run_view(rid):
        run = R.read_run(rid)
        lb_path = os.path.join(R._dir(rid), "leaderboard.json")
        lb = json.load(open(lb_path, encoding="utf-8")) if os.path.isfile(lb_path) else None
        st = R._LOCAL.get(rid) or {}
        alive = bool(st.get("thread") and st["thread"].is_alive())
        return dict({k: v for k, v in run.items() if k != "tasks"}, answered=len(R.answered(rid)), running_here=alive,
                    tasks=[{"i": t["i"], "target": t["target"], "view": t["view"], "model": t["model"]} for t in run["tasks"]],
                    leaderboard=lb)

    @app.route("/api/er2/run/<rid>")
    def api_er2_run_get(rid):
        try:
            v = _run_view(rid)
            if v["answered"] and not v.get("leaderboard") or (v["answered"] == v["n"] and not (v.get("leaderboard") or {}).get("rows")):
                R.leaderboard(rid)
                v = _run_view(rid)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("er2/run/get", exc, 404, {"rid": rid})
        return jsonify({"ok": True, "run": v})

    @app.route("/api/er2/run/<rid>/refresh", methods=["POST"])
    def api_er2_run_refresh(rid):
        try:
            run = R.read_run(rid)
            out = {}
            if run.get("where") == "vacc":
                cfg = A.vaccmod.load_config(A.LOGS_DIR)
                out["slurm"] = R.poll_vacc(cfg, rid)
                out["fetch"] = R.fetch_vacc(cfg, rid)
            if R.answered(rid):
                R.leaderboard(rid)
            if len(R.answered(rid)) == run["n"] and not run.get("artifact"):
                R.finish(rid)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("er2/run/refresh", exc, 400, {"rid": rid})
        return jsonify(dict(out, ok=True, run=_run_view(rid)))

    @app.route("/api/er2/run/<rid>/stop", methods=["POST"])
    def api_er2_run_stop(rid):
        try:
            run = R.read_run(rid)
            if run.get("where") == "vacc":
                R.cancel_vacc(A.vaccmod.load_config(A.LOGS_DIR), rid)
            else:
                R.stop_local(rid)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("er2/run/stop", exc, 400, {"rid": rid})
        return jsonify({"ok": True, "run": _run_view(rid)})

    @app.route("/api/er2/run/<rid>/resume", methods=["POST"])
    def api_er2_run_resume(rid):
        try:
            R.start_local(rid)
        except Exception as exc:                          # noqa: BLE001
            return A.fail("er2/run/resume", exc, 400, {"rid": rid})
        return jsonify({"ok": True, "run": _run_view(rid)})

    @app.route("/api/er2/run/<rid>/task/<int:i>")
    def api_er2_task(rid, i):
        p = os.path.join(R._dir(rid), "results", "%d.json" % i)
        if not os.path.isfile(p):
            return A.fail("er2/task", FileNotFoundError("That task has no answer yet."), 404, {"rid": rid, "i": i})
        return jsonify({"ok": True, "result": json.load(open(p, encoding="utf-8"))})

    return True
