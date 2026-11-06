# -*- coding: utf-8 -*-
"""Floss (backend/floss.py) end to end, with a stand-in for Claude Code.

Builds a throwaway repo shaped like this one, points Floss at it, and has a
fake engine edit files the way Claude Code would, printing stream-json. Checks:
a small fix comes back ready, is used and undone on the "live" tree; a fix
too big, or in a fenced file, is held and refused; a run that ends in an
error says so; no key, no run. Touches nothing real and spends nothing.

    python tools/check_floss.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from backend import floss, floss_key  # noqa: E402

FAKE = r'''
import json, os, sys
brief = sys.stdin.read()
mode = os.environ["FLOSS_FAKE"]
app = os.path.join("_Jarvis", "app")
def say(ev): print(json.dumps(ev), flush=True)
say({"type": "system", "subtype": "init"})
say({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read",
     "input": {"file_path": os.path.abspath(os.path.join(app, "backend", "thing.py"))}}]}})
if mode == "error":
    say({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in"})
    sys.exit(1)
def edit(rel, old, new):
    p = os.path.join(app, *rel.split("/"))
    s = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
if mode == "small":
    edit("backend/thing.py", "return a - b", "return a + b")
    # what py_compile leaves behind (2026-11-06: it held a one-line fix)
    os.makedirs(os.path.join(app, "backend", "__pycache__"), exist_ok=True)
    open(os.path.join(app, "backend", "__pycache__", "thing.cpython-314.pyc"), "wb").close()
elif mode == "big":
    edit("backend/thing.py", "# end", "\n".join("x%d = %d" % (i, i) for i in range(80)))
elif mode == "fenced":
    edit("backend/cloud.py", "KEY = 1", "KEY = 2")
assert "thing" in brief or True
say({"type": "result", "subtype": "success", "is_error": False, "num_turns": 3,
     "total_cost_usd": 0.01, "duration_ms": 1200,
     "result": "I fixed the sum.\n```json\n{\"summary\": \"add, not subtract\", "
               "\"cause\": \"a minus\", \"fix\": \"a plus\", \"confidence\": \"high\", "
               "\"tested\": \"py_compile\", \"needs\": [\"a check for add()\"]}\n```"})
'''


def git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True)


def main():
    tmp = tempfile.mkdtemp(prefix="floss-check-")
    try:
        repo = os.path.join(tmp, "repo")
        be = os.path.join(repo, "_Jarvis", "app", "backend")
        os.makedirs(be)
        os.makedirs(os.path.join(repo, "_Jarvis", "app", "web"))
        with open(os.path.join(be, "thing.py"), "w", newline="\n") as fh:
            fh.write("def add(a, b):\n    return a - b\n# end\n")
        with open(os.path.join(be, "cloud.py"), "w", newline="\n") as fh:
            fh.write("KEY = 1\n")
        for a in (["init", "-q"], ["config", "user.name", "t"], ["config", "user.email", "t@t"],
                  ["config", "core.autocrlf", "false"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
            git(a, repo)
        fake = os.path.join(tmp, "fake_claude.py")
        with open(fake, "w") as fh:
            fh.write(FAKE)

        floss.REPO_ROOT = repo
        floss.APP_REL = "_Jarvis/app"
        floss.TICKETS = os.path.join(tmp, "tickets")
        floss.WT_ROOT = os.path.join(tmp, "wt")
        floss.RUNLOGS = os.path.join(tmp, "runs")
        floss.HOME = os.path.join(tmp, "home")
        floss.HOOKS.update(shard=lambda: "test-shard", who=lambda: "Debug_Bot",
                           machine=lambda: "Testbarry", build=lambda: "0000.00.00.0",
                           errors=lambda: [{"at": "now", "where": "x", "message": "boom"}])
        floss.engine = lambda: fake
        floss.engine_version = lambda p: "fake"
        floss._command = lambda exe, key, rules: [sys.executable, exe]
        floss_key.here = lambda: "sk-ant-api03-fake"
        thing = os.path.join(be, "thing.py")

        def run(mode):
            os.environ["FLOSS_FAKE"] = mode
            tid = floss.ask("add() gives the wrong answer", {"view": "xplore"})
            for _ in range(200):
                if not floss.RUN["running"]:
                    break
                time.sleep(0.05)
            assert not floss.RUN["running"], "still running"
            return floss.load(tid)

        t = run("small")
        assert t["status"] == "ready", t
        assert t["files"] == [{"path": "backend/thing.py", "added": 1, "removed": 1}], t["files"]
        assert t["report"]["summary"] == "add, not subtract", t["report"]
        assert t["report"]["needs"] == ["a check for add()"]
        assert t["run"]["cost_usd"] == 0.01 and t["context"]["recent"][0]["message"] == "boom"
        assert "return a + b" in t["patch"]
        assert not os.listdir(floss.WT_ROOT), "the copy was left behind"
        assert "a - b" in open(thing).read(), "the run touched the live tree"
        after = floss.use(t["id"], by="Debug_Bot")
        assert after == {"restart": True, "reload": False}, after
        assert "a + b" in open(thing).read()
        assert floss.load(t["id"])["status"] == "applied"
        floss.undo(t["id"])
        assert "a - b" in open(thing).read()
        print("ok  a small fix comes back ready, is used, and comes out again")

        # The live code moved on: the fix no longer fits and is refused.
        t = run("small")
        with open(thing, "w", newline="\n") as fh:
            fh.write("def add(a, b):\n    return b - a\n# end\n")
        try:
            floss.use(t["id"])
            raise AssertionError("used a fix that no longer fits")
        except RuntimeError as e:
            assert "looked, so his fix no longer fits" in str(e), e
        git(["checkout", "--", "."], repo)
        print("ok  a fix that no longer fits is refused")

        t = run("big")
        assert t["status"] == "held" and any("lines changed" in w for w in t["held_because"]), t
        try:
            floss.use(t["id"])
            raise AssertionError("used a held fix")
        except RuntimeError:
            pass
        t = run("fenced")
        assert t["status"] == "held" and any("fenced" in w for w in t["held_because"]), t
        print("ok  too big, or fenced, is held and cannot be used here")

        t = run("none")
        assert t["status"] == "nothing", t
        t = run("error")
        assert t["status"] == "failed" and "Not logged in" in t["error"], t
        print("ok  no change, and an error, are said as such")

        floss_key.here = lambda: None
        try:
            floss.ask("add() gives the wrong answer")
            raise AssertionError("ran without a key")
        except RuntimeError as e:
            assert "locked" in str(e)
        print("ok  no key, no run")

        blob = floss_key.seal("sk-ant-oat01-abc", "12345")
        assert floss_key.open_sealed(blob, "12345") == "sk-ant-oat01-abc"
        try:
            floss_key.open_sealed(blob, "54321")
            raise AssertionError("a wrong PIN opened it")
        except floss_key.WrongPin:
            pass
        assert floss_key.kind_of("sk-ant-api03-x") == "api" and floss_key.kind_of("nope") is None
        print("ok  the key seals and opens only with its PIN")

        env = floss._env("sk-ant-oat01-abc")
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-abc" and "ANTHROPIC_API_KEY" not in env
        assert not [k for k in env if k.upper().startswith("CLAUDECODE")]
        print("ok  the run gets only the lab's key and its own Claude home")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
