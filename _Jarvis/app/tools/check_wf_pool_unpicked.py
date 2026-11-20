# -*- coding: utf-8 -*-
"""A Root Canal workflow saved with no pool picked is told which to pick.

2026-11-12, Bluebarry, 12:01:36 and 12:01:47: "rootcanal/workflow-save",
"There is no saved pool None to use as the target." A new P-spike workflow
opened on "Select pool": the builder's defaults are found by name ("PTEN
Baseline"), and the pools on show are named otherwise now ("PTEN Baseline
v2 (Optimized parameters)"). Save sent {"artifact_id": null}, and
`_wf_pool` in backend/app.py printed the null. The page now says which pool
to pick and sends nothing (web/_dev/rcworkflow.html, "A POOL NOT YET
PICKED"). This checks the server's own words, for any other caller.

No server: app.py's `WF_POOL_UNPICKED` and `_wf_pool` are compiled into a
namespace with the artifact store and rcworkflow stood in for.

    python tools/check_wf_pool_unpicked.py          # the code on disk
    python tools/check_wf_pool_unpicked.py --head   # HEAD's, to show the
                                                    # check fails with the
                                                    # fix taken out
"""
import ast
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)

ok = bad = 0


def check(name, cond, got=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r" % (name, got))


class WorkflowError(Exception):
    pass


class RC:
    WorkflowError = WorkflowError


class Artifacts:
    """ARTIFACTS, as far as _wf_pool asks it: one saved pool, pK v2."""

    def get(self, aid):
        if aid == "pK":
            return {"id": "pK", "kind": "rootcanal_pool", "version": 2,
                    "nickname": "Harness pool"}
        return None

    def payload(self, aid, v):
        return {"members": []} if aid == "pK" else None


def source(head):
    if head:
        return subprocess.run(
            ["git", "show", "HEAD:_Jarvis/app/backend/app.py"], cwd=APP,
            capture_output=True, check=True).stdout.decode("utf-8")
    with open(os.path.join(APP, "backend", "app.py"), encoding="utf-8") as f:
        return f.read()


def namespace(head):
    tree = ast.parse(source(head))
    keep = [n for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name == "_wf_pool")
            or (isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "WF_POOL_UNPICKED"
                        for t in n.targets))]
    ns = {"ARTIFACTS": Artifacts(), "rcworkflow": RC}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "app.py", "exec"), ns)
    return ns


def refusal(fn, ref, what):
    try:
        fn(ref, what)
    except WorkflowError as exc:
        return str(exc)
    return None


def main():
    head = "--head" in sys.argv
    print("_wf_pool, %s" % ("HEAD's" if head else "the code on disk"))
    fn = namespace(head)["_wf_pool"]

    said = refusal(fn, {"artifact_id": None}, "target")
    check("no target picked: says to pick the pool it is applied to, not 'None'",
          said == "Pick the pool it is applied to first.", said)
    said = refusal(fn, {"artifact_id": None}, "source")
    check("no source picked: says to pick the pool the DS border is drawn around",
          said == "Pick the pool the DS border is drawn around first.", said)
    said = refusal(fn, None, "target")
    check("no reference at all: the same words, never 'None'",
          said is not None and "None" not in said, said)
    said = refusal(fn, {"artifact_id": "gone1"}, "target")
    check("a pool named that is not here is still refused by its id",
          said == "There is no saved pool gone1 to use as the target.", said)
    got = fn({"artifact_id": "pK"}, "target")
    check("a pool that is here is taken, at its newest version",
          got[0]["id"] == "pK" and got[1] == 2, got)
    got = fn({"artifact_id": "pK", "version": 1}, "target")
    check("and at the version asked for", got[1] == 1, got)

    print("\n%d ok, %d failed" % (ok, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
