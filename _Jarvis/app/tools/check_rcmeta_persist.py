# -*- coding: utf-8 -*-
"""Pressing Run on a Root Canal meta workflow does not file an error.

2026-11-11, Bluebarry, 15:29:16: "rootcanal.meta.state", "[WinError 32]
The process cannot access the file because it is being used by another
process: '...rcmeta\\runs.json.part' -> '...rcmeta\\runs.json'". Run's
request and the run's own thread each write runs.json the moment Run is
pressed, both through one scratch name, and on Windows the second writer
holding runs.json.part makes the first one's rename fail. The fix
(2026.11.12.1): one writer at a time, a copy taken under the lock, and the
store's own atomic write (a private scratch name, the rename retried).

No server, and nothing under GUI_logs: app.py's own `_META_*` definitions
and `_meta_persist` are compiled into a namespace whose LOGS_DIR is a temp
folder, and the error log is stood in for in memory.

    python tools/check_rcmeta_persist.py           # the code on disk
    python tools/check_rcmeta_persist.py --head    # HEAD's, to show the
                                                   # check fails with the
                                                   # fix taken out
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import shards  # noqa: E402

ok = bad = 0


def check(name, cond, got=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r" % (name, got))


class Store:
    """STORE, as far as _meta_persist asks it: the error log."""

    def __init__(self):
        self.errors = []

    def record_error(self, where, exc, detail=None, context=None):
        self.errors.append((where, repr(exc)))


def source(head):
    if head:
        return subprocess.run(
            ["git", "show", "HEAD:_Jarvis/app/backend/app.py"], cwd=APP,
            capture_output=True, check=True).stdout.decode("utf-8")
    with open(os.path.join(APP, "backend", "app.py"), encoding="utf-8") as f:
        return f.read()


def meta_namespace(head, logs_dir):
    """Every top-level `_META_* = ...` in app.py, and its two functions
    that read and write runs.json, run in order against `logs_dir`."""
    tree = ast.parse(source(head))
    keep = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in (
                "_meta_state_load", "_meta_persist"):
            keep.append(n)
        elif isinstance(n, ast.Assign) and all(
                isinstance(t, ast.Name) and t.id.startswith("_META_")
                for t in n.targets):
            keep.append(n)
    store = Store()
    ns = {"os": os, "json": json, "time": time, "threading": threading,
          "shards": shards, "STORE": store, "LOGS_DIR": logs_dir}
    exec(compile(ast.Module(body=keep, type_ignores=[]),
                 "HEAD:app.py" if head else "app.py", "exec"), ns)
    return ns, store


head = "--head" in sys.argv
print("HEAD's _meta_persist (the fix taken out)" if head
      else "the code on disk")

tmp = tempfile.mkdtemp(prefix="check-rcmeta-")
try:
    ns, store = meta_namespace(head, tmp)
    persist = ns["_meta_persist"]
    runs = ns["_META_RUNS"]
    state = ns["_META_STATE"]
    check("runs.json is under the temp folder, not GUI_logs",
          os.path.abspath(state).startswith(os.path.abspath(tmp)), state)

    # 1. Run pressed, 200 times: the request's write and the run thread's
    #    write at the same moment.
    for i in range(200):
        aid = "a%03d" % (i % 7)
        runs[aid] = {"status": "queued", "at": time.time(), "name": aid}
        a = threading.Thread(target=persist, kwargs={"force": True})
        b = threading.Thread(target=persist, kwargs={"force": True})
        a.start()
        b.start()
        a.join()
        b.join()
    check("Run pressed 200 times: no error filed",
          not store.errors, store.errors[:3])

    # 2. A run's thread adding to the runs while a request writes them.
    store.errors.clear()
    stop = threading.Event()

    def grow():
        k = 0
        while not stop.is_set():
            runs["g%d" % (k % 50)] = {"status": "running", "step": k,
                                      "done_steps": list(range(k % 9))}
            runs.pop("g%d" % ((k + 25) % 50), None)
            k += 1

    g = threading.Thread(target=grow)
    g.start()
    for _ in range(150):
        persist(force=True)
    stop.set()
    g.join()
    check("written while another thread changes the runs: no error filed",
          not store.errors, store.errors[:3])

    # 3. Something holding runs.json open for a moment (an indexer, a
    #    backup agent, the harness server reading it at start-up).
    store.errors.clear()
    runs.clear()
    runs["held"] = {"status": "done", "purple": 12}
    with open(state, "r", encoding="utf-8") as held:
        t = threading.Thread(target=persist, kwargs={"force": True})
        t.start()
        time.sleep(0.15)
    t.join()
    check("runs.json held open for 0.15 s: the write waits, no error",
          not store.errors, store.errors[:3])

    # 4. What is left: runs.json, whole, saying what the runs say now.
    store.errors.clear()
    runs.clear()
    runs["last"] = {"status": "done", "purple": 7}
    persist(force=True)
    with open(state, encoding="utf-8") as f:
        got = json.load(f)
    check("runs.json holds the newest state", got == runs, got)
    left = sorted(os.listdir(os.path.dirname(state)))
    check("no scratch file left beside it", left == ["runs.json"], left)
    check("a fresh start reads it back", ns["_meta_state_load"]() == runs,
          ns["_meta_state_load"]())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("%d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
