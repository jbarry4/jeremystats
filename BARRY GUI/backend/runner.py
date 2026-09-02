"""
runner.py -- Runs repo scripts as subprocesses and streams their output.

The repo's Python scripts have no argparse: their module-level constants are
the interface. So when the user edits a parameter in the GUI we rewrite that
one literal via AST source positions into a temporary sibling copy, run it,
and delete it. The copy lives NEXT TO the original so `__file__`-relative and
`os.path.dirname(__file__)` paths keep resolving exactly as they do today.
With no overrides we run the original file untouched.

MATLAB scripts are invoked with `matlab -batch`, cd'ing to the script folder
first so its local helpers are on the path.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque

from . import sysinfo

MAX_LINES = 5000            # per-job ring buffer
TMP_PREFIX = "_barrygui_tmp_"

_JOBS = {}
_LOCK = threading.Lock()

# Set by app.py so every run is written to GUI_logs without runner.py having to
# know anything about the store. Signature: on_start(job) -> None,
# on_end(job) -> None.
HOOKS = {"on_start": None, "on_end": None}


def _fire(name, job):
    fn = HOOKS.get(name)
    if not fn:
        return
    try:
        fn(job)
    except Exception:
        # History is a side effect; it must never take down a run.
        pass


# --------------------------------------------------------------------------
# MATLAB discovery (delegated to sysinfo so Windows and macOS behave alike)
# --------------------------------------------------------------------------
find_matlab = sysinfo.find_matlab
MATLAB_EXE = find_matlab()


# --------------------------------------------------------------------------
# Python parameter override
# --------------------------------------------------------------------------
def _py_literal(value, kind):
    """Render a GUI-supplied value as Python source."""
    if kind == "num":
        if isinstance(value, str):
            value = float(value) if ("." in value or "e" in value.lower()) else int(value)
        return repr(value)
    if kind == "bool":
        if isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "yes", "on")
        return "True" if value else "False"
    if kind == "none":
        return "None"
    if kind == "list":
        if isinstance(value, str):
            try:
                value = ast.literal_eval(value)
            except Exception:
                value = [v.strip() for v in value.split(",") if v.strip()]
        return repr(value)
    return repr("" if value is None else str(value))


def write_override_copy(script_path, overrides):
    """Write a temp sibling copy with `overrides` applied. Returns its path."""
    with open(script_path, "r", encoding="utf-8", errors="replace") as fh:
        src = fh.read()

    tree = ast.parse(src)
    edits = []                                  # (start_off, end_off, new_text)
    line_offsets = _line_offsets(src)

    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name = targets[0].id
        if name not in overrides or node.value is None:
            continue

        spec = overrides[name]
        new_text = _py_literal(spec.get("value"), spec.get("type", "str"))
        start = line_offsets[node.value.lineno - 1] + node.value.col_offset
        end = line_offsets[node.value.end_lineno - 1] + node.value.end_col_offset
        edits.append((start, end, new_text))

    for start, end, text in sorted(edits, reverse=True):
        src = src[:start] + text + src[end:]

    folder = os.path.dirname(script_path)
    base = os.path.basename(script_path)
    tmp = os.path.join(folder, TMP_PREFIX + uuid.uuid4().hex[:8] + "_" + base)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(src)
    return tmp


def _line_offsets(src):
    offsets, pos = [0], 0
    for line in src.splitlines(keepends=True):
        pos += len(line)
        offsets.append(pos)
    return offsets


# --------------------------------------------------------------------------
# MATLAB call construction
# --------------------------------------------------------------------------
_MATLAB_BARE_RE = re.compile(r"^\s*(\[.*\]|true|false|\d+(\.\d+)?([eE][-+]?\d+)?)\s*$")


def _mat_value(raw):
    """Quote a value for MATLAB unless it is already a literal expression."""
    s = str(raw).strip()
    if s == "":
        return "''"
    if _MATLAB_BARE_RE.match(s):
        return s
    return "'" + s.replace("'", "''") + "'"


def build_matlab_command(script_path, params, extra):
    """Build the `matlab -batch` statement for a script or function."""
    folder = os.path.dirname(script_path)
    stem = os.path.splitext(os.path.basename(script_path))[0]

    if extra.get("kind") != "function":
        body = stem
    else:
        positional, namevalue = [], []
        for p in params:
            val = p.get("value", "")
            if val is None or str(val).strip() == "":
                if p.get("namevalue") or not p.get("required"):
                    continue
            if p.get("namevalue"):
                namevalue.append("'" + p["name"] + "', " + _mat_value(val))
            else:
                positional.append(_mat_value(val))
        args = ", ".join(positional + namevalue)
        body = stem + "(" + args + ")" if args else stem

    # addpath so sibling helpers (components/, stages/, reqsPath/) resolve.
    safe = folder.replace("'", "''")
    setup = "addpath(genpath('" + safe + "'));"
    return [MATLAB_EXE, "-batch", setup + " cd('" + safe + "'); " + body]


# --------------------------------------------------------------------------
# Job management
# --------------------------------------------------------------------------
class Job:
    def __init__(self, job_id, label, cmd, cwd, cleanup=None, meta=None):
        self.id = job_id
        self.label = label
        self.cmd = cmd
        self.cwd = cwd
        self.cleanup = cleanup or []
        self.meta = meta or {}
        self.lines = deque(maxlen=MAX_LINES)
        self.status = "queued"          # queued|running|done|failed|canceled
        self.returncode = None
        self.started = None
        self.ended = None
        self.proc = None
        self.seq = 0
        self.error = None
        self._lock = threading.Lock()

    def emit(self, text, stream="out"):
        with self._lock:
            self.seq += 1
            self.lines.append({"n": self.seq, "t": time.time(),
                               "s": stream, "text": text})

    def snapshot(self, since=0):
        with self._lock:
            return {
                "id": self.id, "label": self.label, "status": self.status,
                "returncode": self.returncode, "started": self.started,
                "ended": self.ended, "seq": self.seq, "meta": self.meta,
                "cmd": self.cmd,
                "lines": [ln for ln in self.lines if ln["n"] > since],
            }

    def duration(self):
        if not self.started:
            return 0.0
        return (self.ended or time.time()) - self.started

    def tail(self, n=60):
        with self._lock:
            return [ln["text"] for ln in list(self.lines)[-n:]]


def _pump(job):
    """Run the subprocess, streaming merged stdout/stderr into the ring buffer."""
    job.status = "running"
    job.started = time.time()
    job.emit("$ " + " ".join(job.cmd), "meta")
    job.emit("  cwd: " + job.cwd, "meta")

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["MPLBACKEND"] = env.get("MPLBACKEND", "Agg")   # headless plotting

    try:
        job.proc = subprocess.Popen(
            job.cmd, cwd=job.cwd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            bufsize=1, text=True, encoding="utf-8", errors="replace",
            env=env, **sysinfo.popen_kwargs())
    except Exception as exc:
        job.emit("Failed to launch: " + str(exc), "err")
        job.status = "failed"
        job.error = "%s: %s" % (type(exc).__name__, exc)
        job.ended = time.time()
        _do_cleanup(job)
        _fire("on_end", job)
        return

    try:
        for line in job.proc.stdout:
            job.emit(line.rstrip("\r\n"))
    except Exception as exc:
        job.emit("Stream error: " + str(exc), "err")

    _fire("on_start", job)

    job.returncode = job.proc.wait()
    job.ended = time.time()
    if job.status == "canceling":
        job.status = "canceled"
        job.emit("-- canceled --", "meta")
    elif job.returncode == 0:
        job.status = "done"
        job.emit("-- finished in %.1fs --" % job.duration(), "meta")
    else:
        job.status = "failed"
        job.emit("-- exited with code %s after %.1fs --"
                 % (job.returncode, job.duration()), "meta")
    _do_cleanup(job)
    _fire("on_end", job)


def _do_cleanup(job):
    for path in job.cleanup:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass


def start_job(label, cmd, cwd, cleanup=None, meta=None):
    job_id = uuid.uuid4().hex[:12]
    job = Job(job_id, label, cmd, cwd, cleanup, meta)
    with _LOCK:
        _JOBS[job_id] = job
        # Keep the job list bounded; drop the oldest finished jobs.
        if len(_JOBS) > 60:
            finished = sorted((j for j in _JOBS.values()
                               if j.status in ("done", "failed", "canceled")),
                              key=lambda j: j.ended or 0)
            for old in finished[:20]:
                _JOBS.pop(old.id, None)
    threading.Thread(target=_pump, args=(job,), daemon=True).start()
    return job


def run_script(repo_root, rel_path, lang, params=None, extra=None):
    """Launch one repo script. Returns the Job."""
    script = os.path.join(repo_root, rel_path.replace("/", os.sep))
    if not os.path.isfile(script):
        raise FileNotFoundError(script)
    folder = os.path.dirname(script)
    params = params or []

    if lang == "python":
        overrides = {}
        for p in params:
            if p.get("changed"):
                overrides[p["name"]] = {"value": p.get("value"),
                                        "type": p.get("type", "str")}
        cleanup = []
        target = script
        if overrides:
            target = write_override_copy(script, overrides)
            cleanup.append(target)
        cmd = [sys.executable, "-u", target]
        return start_job(os.path.basename(rel_path), cmd, folder, cleanup,
                         {"rel": rel_path, "lang": lang,
                          "overrides": sorted(overrides)})

    if lang == "matlab":
        if not MATLAB_EXE:
            raise RuntimeError(
                "MATLAB was not found. Install it or add matlab.exe to PATH.")
        cmd = build_matlab_command(script, params, extra or {})
        return start_job(os.path.basename(rel_path), cmd, folder, [],
                         {"rel": rel_path, "lang": lang})

    raise ValueError("Cannot run " + lang + " files directly.")


def run_file(path, lang="python", cwd=None, label=None, cleanup=None,
             meta=None):
    """Launch an absolute path. Used by the scratch runner, which writes its
    own file rather than pointing at something cataloged in the repo."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if lang != "python":
        raise ValueError("run_file only handles Python.")
    cmd = [sys.executable, "-u", path]
    return start_job(label or os.path.basename(path), cmd,
                     cwd or os.path.dirname(path), cleanup or [],
                     meta or {"lang": lang, "path": path})


def get_job(job_id):
    with _LOCK:
        return _JOBS.get(job_id)


def list_jobs():
    with _LOCK:
        jobs = list(_JOBS.values())
    jobs.sort(key=lambda j: j.started or 0, reverse=True)
    return [{"id": j.id, "label": j.label, "status": j.status,
             "returncode": j.returncode, "started": j.started,
             "ended": j.ended, "meta": j.meta,
             "duration": round(j.duration(), 2)} for j in jobs]


def cancel_job(job_id):
    job = get_job(job_id)
    if not job or job.status not in ("running", "queued"):
        return False
    job.status = "canceling"
    proc = job.proc
    if not proc:
        return False
    # MATLAB and Python both spawn children, so the whole tree must go.
    return sysinfo.kill_tree(proc)


def sweep_temp_files(repo_root):
    """Remove any override copies left behind by a hard crash."""
    removed = 0
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        for name in filenames:
            if name.startswith(TMP_PREFIX):
                try:
                    os.remove(os.path.join(dirpath, name))
                    removed += 1
                except OSError:
                    pass
    return removed
