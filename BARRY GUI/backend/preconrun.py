# -*- coding: utf-8 -*-
"""The Precon1 -> Precon4 analysis, run from the Drift panel.

tools/run_precon_drift.py IS the analysis (docs/the-arc-contracts.md section
7). This module only starts it as a child of Jarvis -- one at a time -- and
reads back what it has done. The child drives this same Jarvis over HTTP, so
there is still one writer to the bank and the artifact store and every
artifact is in Results the moment it is filed; the command line still works
and does exactly the same thing.

Three things it runs:

  plan    --dry-run --plan-json: the plan and its cost, item by item. Reads
          only (about 100 local requests, ~10 s); nothing is written.
  run     --yes --plan-json --progress --stop-file: the three stages. The
          cost is re-planned by the run itself and written before anything
          runs. Resumable: what is current is skipped (the runlog says).
  report  tools/precon_drift_report.py: docs/dewey-precon-drift.md, .csv
          and the figures, from the runlog and the snapshots on disk.

The child's output goes to a FILE, never a pipe: a pipe nobody drains fills
at ~64 KB and stops the child mid-run (piped-server-log-deadlocks).

Stopping is between items (the stop file): the item in flight finishes and
is recorded, so nothing is left half-filed. `hard` kills the child instead;
a circuit job it was waiting on still finishes inside Jarvis and is filed,
and the next run finds it current.

A run outlives a restart of Jarvis only as an orphan: `last.json` keeps its
pid, and it is shown as running while that pid is alive and its log is still
being written.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

WHATS = ("plan", "run", "report")
TAIL_LINES = 60
#: A child whose log has not moved for this long is not taken for a live
#: run after a restart, even if its pid answers (a pid can be reused). The
#: run writes at least every 20 s while it waits on a job.
ORPHAN_QUIET_S = 600.0
#: Carries-on in a row that file nothing before the boot-time resume gives
#: up and leaves it to a person.
MAX_STALLS = 3
#: How long a plan stays the plan the Run button quotes.
PLAN_FRESH_S = 6 * 3600.0
FIGURE_EXT = (".png", ".svg")


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds")


class PreconRunError(Exception):
    def __init__(self, msg, code=409):
        super().__init__(msg)
        self.code = code


def _read_json(path):
    """The file, or None. A PermissionError is a writer replacing it that
    very moment (Windows): asked again, briefly, rather than read as gone
    -- which drew a run card that vanished for one poll."""
    for attempt in range(5):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except PermissionError:
            time.sleep(0.02)
        except (OSError, ValueError):
            return None
    return None


def _write_json(path, data):
    """Atomically and to the disk (fsync before the rename): last.json is
    what tells the next Jarvis a run was interrupted, and a power cut must
    not bring it back empty."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    # A reader holding the target (Windows will not replace an open file)
    # is waited for, briefly -- see run_precon_drift.replace_patiently.
    t0 = time.time()
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if time.time() - t0 >= 3.0:
                raise
            time.sleep(0.05)


def _tail(path, n=TAIL_LINES):
    """The last n lines, read from the end: a run log reaches a few MB."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 64 * 1024))
            raw = fh.read()
    except OSError:
        return []
    lines = raw.decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
    if size > 64 * 1024:
        lines = lines[1:]                   # the first may be cut in half
    while lines and not lines[-1].strip():
        lines.pop()
    return lines[-n:]


def _pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))    # QUERY_LIMITED_INFO
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == 259                    # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _proc_created(pid):
    """When process `pid` was created (epoch seconds), or None if that
    cannot be said. After a reboot a remembered pid can belong to anything;
    its creation time is what tells our child from a stranger."""
    if not pid or os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))            # QUERY_LIMITED_INFO
    if not h:
        return None
    try:
        ft = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(h, *[ctypes.byref(f) for f in ft]):
            return None
        t = (ft[0].dwHighDateTime << 32) | ft[0].dwLowDateTime
        return t / 1e7 - 11644473600.0                      # 1601 -> 1970
    finally:
        k.CloseHandle(h)


#: How far a child's creation time may sit from the `started` we recorded
#: just after starting it.
SAME_PROCESS_S = 30.0


def _is_ours(rec):
    """The process `rec` describes is alive AND is the one we started."""
    pid = (rec or {}).get("pid")
    if not _pid_alive(pid):
        return False
    made = _proc_created(pid)
    if made is None:
        return True                        # cannot tell; the log decides
    try:
        at = datetime.fromisoformat(rec.get("started")).timestamp()
    except (TypeError, ValueError):
        return False
    return abs(made - at) <= SAME_PROCESS_S


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _iso_age_s(iso):
    try:
        return time.time() - datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


class Runner(object):
    """One child at a time. `scripts` and `python` are there for the check,
    which runs a stand-in child instead of the analysis."""

    def __init__(self, app_dir, state_dir, python=None, scripts=None,
                 docs_dir=None):
        self.app_dir = app_dir
        self.state_dir = state_dir
        self.python = python or sys.executable
        tools = os.path.join(app_dir, "tools")
        self.scripts = dict({"drift": os.path.join(tools,
                                                   "run_precon_drift.py"),
                             "report": os.path.join(tools,
                                                    "precon_drift_report.py")},
                            **(scripts or {}))
        docs = docs_dir or os.path.join(app_dir, "docs")
        self.runlog = os.path.join(docs, "dewey-precon-drift.runlog.json")
        self.outputs = {"md": os.path.join(docs, "dewey-precon-drift.md"),
                        "csv": os.path.join(docs, "dewey-precon-drift.csv")}
        self.figures = os.path.join(docs, "dewey-precon-drift")
        self.plan_path = os.path.join(state_dir, "plan.json")
        self.progress_path = os.path.join(state_dir, "progress.json")
        self.stop_path = os.path.join(state_dir, "stop")
        self.last_path = os.path.join(state_dir, "last.json")
        self._lock = threading.Lock()
        self._proc = None
        self._what = None
        self._killed = False
        self._resuming = None          # {since, why} while resume_after_boot waits

    def log_path(self, what):
        return os.path.join(self.state_dir, "%s.log" % what)

    # ------------------------------------------------------------------
    # Starting and stopping
    # ------------------------------------------------------------------
    def argv(self, what, base):
        py = [self.python, "-u"]
        if what == "plan":
            return py + [self.scripts["drift"], "--base", base, "--dry-run",
                         "--plan-json", self.plan_path]
        if what == "run":
            return py + [self.scripts["drift"], "--base", base, "--yes",
                         "--plan-json", self.plan_path,
                         "--progress", self.progress_path,
                         "--stop-file", self.stop_path]
        if what == "report":
            return py + [self.scripts["report"]]
        raise PreconRunError("%r is not something this runs (%s)."
                             % (what, ", ".join(WHATS)), 400)

    def start(self, what, base, resumed=None, carry=None):
        """Start `what`. A run is armed to be carried on if it is
        interrupted (`resume`); `resumed` and `carry` are resume()'s."""
        if what not in WHATS:
            raise PreconRunError("%r is not something this runs (%s)."
                                 % (what, ", ".join(WHATS)), 400)
        with self._lock:
            busy = self._busy_locked()
            if busy:
                raise PreconRunError(
                    "The %s is already going (started %s). One at a time: "
                    "this one drives Jarvis, and two would race for it."
                    % ({"plan": "plan", "run": "analysis",
                        "report": "report"}[busy["what"]], busy["started"]))
            os.makedirs(self.state_dir, exist_ok=True)
            if os.path.exists(self.stop_path):
                os.remove(self.stop_path)
            log = self.log_path(what)
            if what == "run":
                if os.path.exists(self.progress_path):
                    os.remove(self.progress_path)
                if os.path.exists(log):     # keep the one before, once
                    try:
                        os.replace(log, self.log_path("run.prev"))
                    except OSError:
                        # Still held open (Windows will not rename it): a
                        # run from the Jarvis before, just ending. Write
                        # beside it rather than refuse to carry on.
                        log = self.log_path("run-%s" % time.strftime(
                            "%Y%m%d-%H%M%S"))
            argv = self.argv(what, base)
            if resumed and what == "run":
                argv += ["--resumed", resumed]
            filed = self._filed() if what == "run" else None
            env = dict(os.environ, PYTHONIOENCODING="utf-8",
                       PYTHONUNBUFFERED="1")
            flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
            fh = open(log, "wb")
            try:
                proc = subprocess.Popen(argv, cwd=self.app_dir, env=env,
                                        stdin=subprocess.DEVNULL, stdout=fh,
                                        stderr=subprocess.STDOUT,
                                        creationflags=flags)
            except Exception:
                fh.close()
                raise
            self._proc, self._what, self._killed = proc, what, False
            rec = {"what": what, "pid": proc.pid, "started": now(),
                   "ended": None, "exit_code": None, "killed": False,
                   "log": log, "argv": argv, "base": base}
            if what == "run":
                rec.update({"resume": True, "resumes": 0, "stalls": 0,
                            "chain_started": rec["started"],
                            "filed_at_start": filed, "resumed_why": None,
                            "auto": False, "gave_up": None})
                rec.update(carry or {})
            last = _read_json(self.last_path) or {}
            last[what] = rec
            last["current"] = what
            _write_json(self.last_path, last)
        threading.Thread(target=self._wait, args=(proc, fh, what),
                         name="precon-%s" % what, daemon=True).start()
        return rec

    def _wait(self, proc, fh, what):
        code = proc.wait()
        try:
            fh.close()
        except OSError:
            pass
        with self._lock:
            last = _read_json(self.last_path) or {}
            rec = last.get(what) or {}
            if rec.get("pid") == proc.pid:
                rec["ended"] = now()
                rec["exit_code"] = code
                rec["killed"] = bool(self._killed and self._proc is proc)
                # Carried on only if it was interrupted (exit 4). Finished,
                # refused, stopped or killed by a person: not again.
                if what == "run" and (code != 4 or rec["killed"]):
                    rec["resume"] = False
                last[what] = rec
                if last.get("current") == what:
                    last["current"] = None
                _write_json(self.last_path, last)
            if self._proc is proc:
                self._proc, self._what = None, None

    def _disarm(self, why):
        """A person stopped it: it is not carried on after a restart."""
        last = _read_json(self.last_path) or {}
        rec = last.get("run")
        if rec and rec.get("resume"):
            rec["resume"] = False
            rec["disarmed"] = {"at": now(), "why": why}
            _write_json(self.last_path, last)

    def stop(self, hard=False):
        with self._lock:
            busy = self._busy_locked()
            if not busy:
                raise PreconRunError("Nothing is running.", 409)
            if busy["what"] == "run":
                self._disarm("stopped by hand" + (" at once" if hard else ""))
            if not hard and busy["what"] == "run":
                with open(self.stop_path, "w", encoding="utf-8") as fh:
                    fh.write(now())
                return {"how": "soft", "what": busy["what"]}
            if self._proc is not None and self._proc.poll() is None:
                self._killed = True
                self._proc.terminate()
            elif busy.get("orphan"):
                os.kill(int(busy["pid"]), signal.SIGTERM)
                last = _read_json(self.last_path) or {}
                rec = last.get(busy["what"]) or {}
                rec.update({"ended": now(), "killed": True})
                last[busy["what"]] = rec
                last["current"] = None
                _write_json(self.last_path, last)
            return {"how": "hard", "what": busy["what"]}

    # ------------------------------------------------------------------
    # Carrying on after an interruption
    # ------------------------------------------------------------------
    def _filed(self):
        """How much the run log says has landed -- the measure of whether a
        carried-on run got anywhere."""
        R = _read_json(self.runlog) or {}
        return (sum(1 for v in (R.get("spark") or {}).values()
                    if v.get("status") in ("banked", "done"))
                + sum(1 for c in (R.get("circuits") or {}).values()
                      if c.get("artifact_id"))
                + sum(1 for d in (R.get("drifts") or {}).values()
                      if d.get("artifact_id")))

    def interrupted(self):
        """The run to carry on, or None: armed, not running, and it ended
        without finishing (exit 4) or nobody saw it end at all (the computer
        went off, or Jarvis and the run went down together)."""
        with self._lock:
            if self._busy_locked():
                return None
            rec = (_read_json(self.last_path) or {}).get("run")
        if not rec or not rec.get("resume"):
            return None
        if rec.get("ended") is not None and rec.get("exit_code") != 4:
            return None
        return rec

    def resume(self, base, why, auto=False):
        """Carry the interrupted run on: the same run, started again. It
        re-plans itself, skips everything current, and redoes the item that
        was in flight from its per-pair cache. Refused, when `auto`, after
        MAX_STALLS carries-on in a row that filed nothing: something is
        wrong that restarting will not fix, and a person should look."""
        rec = self.interrupted()
        if not rec:
            raise PreconRunError("There is no interrupted run to carry on.")
        filed = self._filed()
        stalls = int(rec.get("stalls") or 0)
        was = rec.get("filed_at_start")
        stalls = stalls + 1 if (was is not None and filed <= was) else 0
        if auto and stalls >= MAX_STALLS:
            with self._lock:
                last = _read_json(self.last_path) or {}
                r = last.get("run") or {}
                r["gave_up"] = {"at": now(), "stalls": stalls}
                last["run"] = r
                _write_json(self.last_path, last)
            raise PreconRunError(
                "Not carried on by itself: the last %d tries filed nothing. "
                "Look at what it said, then carry it on by hand." % stalls)
        carry = {"resumes": int(rec.get("resumes") or 0) + 1,
                 "chain_started": rec.get("chain_started")
                 or rec.get("started"),
                 "stalls": stalls, "resumed_why": why, "auto": bool(auto),
                 "interrupted_at": rec.get("ended") or rec.get("started")}
        return self.start("run", base, resumed=why, carry=carry)

    def forget(self):
        """Do not carry the interrupted run on."""
        if not self.interrupted():
            raise PreconRunError("There is no interrupted run to forget.")
        self._disarm("told not to carry it on")
        return True

    def resume_after_boot(self, base, ready=None, orphan_wait_s=600.0,
                          poll_s=3.0, ready_wait_s=60.0, say=None):
        """At Jarvis start -- start.py only, never a harness or a script:
        carry on a run that was interrupted. Waits for this server to answer
        (`ready`), then for a run left over from the Jarvis before to notice
        and end (it does within about two minutes; past `orphan_wait_s` it
        is ended), then resumes. Returns a sentence, or None if there was
        nothing to do."""
        say = say or (lambda m: None)
        rec = (_read_json(self.last_path) or {}).get("run") or {}
        if not rec.get("resume"):
            return None
        self._resuming = {"since": now(), "why": "Jarvis started again"}
        try:
            t0 = time.time()
            while ready is not None and not ready():
                if time.time() - t0 > ready_wait_s:
                    return "not carried on: this Jarvis never answered"
                time.sleep(0.5)
            t0 = time.time()
            while True:
                rec = (_read_json(self.last_path) or {}).get("run") or {}
                if not (rec.get("ended") is None and _is_ours(rec)):
                    break
                if time.time() - t0 > orphan_wait_s:
                    try:
                        os.kill(int(rec["pid"]), signal.SIGTERM)
                    except OSError:
                        pass
                    time.sleep(poll_s)
                    break
                time.sleep(poll_s)
            if not self.interrupted():
                return None
            why = ("Jarvis started again after the run was interrupted "
                   "(%s)" % ("it ended as interrupted" if rec.get("ended")
                             else "nobody saw it end"))
            try:
                got = self.resume(base, why, auto=True)
            except PreconRunError as exc:
                say("  Analysis: %s" % exc)
                return str(exc)
            msg = ("carried on the Precon1 -> Precon4 analysis (pid %d); "
                   "stop it from ToolKit -> Drift" % got["pid"])
            say("  Analysis: " + msg)
            return msg
        finally:
            self._resuming = None

    # ------------------------------------------------------------------
    # Reading back
    # ------------------------------------------------------------------
    def _busy_locked(self):
        p = self._proc
        if p is not None and p.poll() is None:
            last = (_read_json(self.last_path) or {}).get(self._what) or {}
            return {"what": self._what, "pid": p.pid,
                    "started": last.get("started"), "orphan": False}
        # Started by a Jarvis that has since restarted?
        last = _read_json(self.last_path) or {}
        what = last.get("current")
        rec = last.get(what) if what else None
        if rec and rec.get("ended") is None and _is_ours(rec):
            m = _mtime(rec.get("log") or "")
            if m is not None and time.time() - m < ORPHAN_QUIET_S:
                return {"what": what, "pid": rec["pid"],
                        "started": rec.get("started"), "orphan": True}
        return None

    def status(self, server_started=None):
        with self._lock:
            busy = self._busy_locked()
            last = _read_json(self.last_path) or {}
        if busy:
            age = _iso_age_s(busy.get("started"))
            busy["elapsed_s"] = None if age is None else round(age, 1)
            busy["stopping"] = busy["what"] == "run" and \
                os.path.exists(self.stop_path)
        ended = {}
        for what in WHATS:
            rec = last.get(what)
            if not rec:
                continue
            if rec.get("ended") is None and not (busy and
                                                 busy["what"] == what):
                # Its Jarvis went away mid-run and nothing saw it end.
                rec = dict(rec, lost=True)
            ended[what] = {k: rec.get(k) for k in (
                "started", "ended", "exit_code", "killed", "lost")}
        shown = busy["what"] if busy else next(
            (w for w in sorted(ended, key=lambda w: ended[w].get("started")
                               or "", reverse=True)), None)
        plan = _read_json(self.plan_path)
        if plan:
            age = _iso_age_s(plan.get("at"))
            plan["age_s"] = None if age is None else round(age, 1)
            srv = (plan.get("server") or {}).get("started_at")
            plan["fresh"] = bool(
                age is not None and age < PLAN_FRESH_S and
                (server_started is None or srv == server_started))
        run = last.get("run") or {}
        armed = bool(run.get("resume"))
        cut = armed and not (busy and busy["what"] == "run") and (
            run.get("ended") is None or run.get("exit_code") == 4)
        resume = {"armed": armed, "interrupted": bool(cut),
                  "pending": self._resuming,
                  "resumes": run.get("resumes") or 0,
                  "resumed_why": run.get("resumed_why"),
                  "chain_started": run.get("chain_started"),
                  "interrupted_at": run.get("interrupted_at"),
                  "gave_up": run.get("gave_up"),
                  "disarmed": run.get("disarmed")}
        return {
            "busy": busy,
            "last": ended,
            "resume": resume,
            "log": {"what": shown,
                    "lines": _tail((last.get(shown) or {}).get("log")
                                   or self.log_path(shown))
                    if shown else []},
            "plan": plan,
            "progress": _read_json(self.progress_path),
            "runlog": self.runlog_summary(),
            "report": self.report_files(),
        }

    def runlog_summary(self):
        R = _read_json(self.runlog)
        if not R:
            return None
        drifts = []
        for key, d in sorted((R.get("drifts") or {}).items()):
            drifts.append({k: d.get(k) for k in (
                "band", "kind", "role", "contrast", "nickname",
                "artifact_id", "version", "version_id", "at")})
            drifts[-1]["key"] = key
        circuits = R.get("circuits") or {}
        return {
            "updated": R.get("updated"), "finished": R.get("finished"),
            "stopped": R.get("stopped"), "interrupted": R.get("interrupted"),
            "failures": R.get("failures") or [],
            "spark": {s: sum(1 for v in (R.get("spark") or {}).values()
                             if v.get("status") == s)
                      for s in ("banked", "done", "blocked", "failed",
                                "split")},
            "circuits": sum(1 for c in circuits.values()
                            if c.get("artifact_id")),
            "circuit_problems": sum(1 for c in circuits.values()
                                    if c.get("problem")),
            "drifts": drifts,
            "events": (R.get("events") or [])[-12:],
        }

    def report_files(self):
        out = {}
        for k, p in self.outputs.items():
            m = _mtime(p)
            out[k] = None if m is None else {
                "name": os.path.basename(p), "bytes": os.path.getsize(p),
                "at": datetime.fromtimestamp(m).astimezone().isoformat(
                    timespec="seconds")}
        figs = []
        if os.path.isdir(self.figures):
            figs = sorted(f for f in os.listdir(self.figures)
                          if f.lower().endswith(FIGURE_EXT))
        out["figures"] = figs
        return out

    def output_path(self, which):
        """A report file the panel may open: md, csv, or figure/<name>."""
        if which in self.outputs:
            return self.outputs[which]
        if which.startswith("figure/"):
            name = which[len("figure/"):]
            if (name and os.path.basename(name) == name and
                    name.lower().endswith(FIGURE_EXT)):
                return os.path.join(self.figures, name)
        return None
