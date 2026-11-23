# -*- coding: utf-8 -*-
"""An edit saved after a run does not hide the run from Ambiguous.

2026-11-05, Bluebarry, 17:06:50 and 17:07:10: saving the Ambiguous
workflow failed twice with "'Verified P-Spike' has not been run yet, so it
has no border to lend." The P-spike workflow (abe99ac5d1b6) had run at
17:04:05 as v2 (1381 kept), and at 17:04:09 its definition was saved again
as v3, "Definition changed", with no run of its own. _wf_definition read
the newest version only, found no run there, and refused. The fix
(2026.11.05.6, _wf_last_run) lends the newest version that holds a run.

The store is a stand-in in memory: nothing under GUI_logs is read or
written.

    python tools/check_wf_border_lend.py           # the code on disk
    python tools/check_wf_border_lend.py --head    # HEAD's _wf_definition
                                                   # and _wf_current, to
                                                   # show the check fails
                                                   # with the fix taken out
"""
import ast
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

# Before the import: no day-report loop or warm-up threads for a check.
os.environ.setdefault("BARRY_HARNESS_SERVER", "1")

from backend import app as A  # noqa: E402
from backend import rcworkflow  # noqa: E402

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
    """ARTIFACTS, as far as _wf_definition and _wf_current ask it."""

    def __init__(self):
        self.recs, self.pays = {}, {}

    def add(self, aid, nickname, pays):
        self.recs[aid] = {"id": aid, "kind": "rootcanal_workflow",
                          "nickname": nickname, "version": len(pays)}
        self.pays[aid] = {i + 1: p for i, p in enumerate(pays)}

    def get(self, aid):
        return self.recs.get(aid)

    def payload(self, aid, v=None):
        p = self.pays.get(aid) or {}
        if v is None:
            v = max(p) if p else None
        return p.get(int(v)) if v is not None else None


def head_functions():
    """HEAD's own _wf_definition and _wf_current, compiled into the app's
    namespace (this process only): the code before the fix, with nothing
    on disk changed."""
    src = subprocess.run(
        ["git", "show", "HEAD:_Jarvis/app/backend/app.py"], cwd=APP,
        capture_output=True, check=True).stdout.decode("utf-8")
    tree = ast.parse(src)
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name in ("_wf_definition", "_wf_current")]
    ns = vars(A)            # in this process only; they read the stub store
    exec(compile(ast.Module(body=keep, type_ignores=[]), "HEAD:app.py",
                 "exec"), ns)
    return ns["_wf_definition"], ns["_wf_current"]


if "--head" in sys.argv:
    wf_definition, wf_current = head_functions()
    print("HEAD's _wf_definition and _wf_current (the fix taken out)")
else:
    wf_definition, wf_current = A._wf_definition, A._wf_current
    print("the code on disk")

S = Store()
A.ARTIFACTS = S
run_ds = {"kept": 1857, "counts": {"in": 1857}}
run_p = {"kept": 1381, "counts": {"in": 1381}}
S.add("ds0000000001", "Verified DS", [
    {"definition": {"kind": "ds"}},
    {"definition": {"kind": "ds"}, "run": run_ds}])
# Bluebarry's abe99ac5d1b6: defined, run, then saved again with no run.
S.add("ps0000000001", "Verified P-Spike", [
    {"definition": {"kind": "pspike"}},
    {"definition": {"kind": "pspike"}, "run": run_p},
    {"definition": {"kind": "pspike"}}])
S.add("ps0000000002", "Never run", [
    {"definition": {"kind": "pspike"}},
    {"definition": {"kind": "pspike"}}])


def define(uses):
    try:
        return wf_definition({"kind": "ambiguous", "uses": uses}), None
    except rcworkflow.WorkflowError as exc:
        return None, exc


both = {"ds": {"artifact_id": "ds0000000001"},
        "pspike": {"artifact_id": "ps0000000001"}}
got, exc = define(both)
check("Ambiguous saves on a P-spike run followed by an edit",
      exc is None, str(exc))
check("... and borrows the run (v2), not the edit after it (v3)",
      got and got["uses"]["pspike"]["version"] == 2,
      got and got["uses"])
check("... DS borrows its newest version, which ran (v2)",
      got and got["uses"]["ds"]["version"] == 2, got and got["uses"])

got2, exc2 = define({"ds": {"artifact_id": "ds0000000001"},
                     "pspike": {"artifact_id": "ps0000000002"}})
check("a workflow that never ran still has no border to lend",
      got2 is None and "has not been run yet" in str(exc2), (got2, exc2))

got3, exc3 = define({"ds": {"artifact_id": "ds0000000001"},
                     "pspike": {"artifact_id": "ps0000000001",
                                "version": 3}})
check("pinning the edit itself (v3) is still refused: it holds no run",
      got3 is None and "has not been run yet" in str(exc3), (got3, exc3))

if got:
    stale = wf_current(got)
    check("the edit alone does not make Ambiguous out of date",
          not [s for s in stale if "workflow" in s.get("what", "")], stale)
    S.pays["ps0000000001"][4] = {"definition": {"kind": "pspike"},
                                 "run": dict(run_p, kept=1400)}
    S.recs["ps0000000001"]["version"] = 4
    stale = wf_current(got)
    check("a newer run does make it out of date (pinned 2, newest 4)",
          any(s.get("pinned") == 2 and s.get("newest") == 4
              for s in stale), stale)

print("\n%d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
