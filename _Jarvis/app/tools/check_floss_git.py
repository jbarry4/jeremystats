# -*- coding: utf-8 -*-
"""Floss finds git where the rest of Jarvis does.

2026-11-09, Strawbarry, 10:23: Rain's Floss ticket (20261109-102332-eca9,
"Reading Panning's sets shows up for a long time") failed at once with
"[WinError 2] The system cannot find the file specified". The ticket has
no `head` or `run`, so it stopped in `_prepare`, copying the code. The
only thing `_prepare` starts is git, and the message names no file, so
Windows could not find the program to start. `floss._git` asked for plain
"git". A computer with only GitHub Desktop has a git but not on PATH, and
every other git call in Jarvis goes through `store.git_exe()`, which looks
where Git for Windows and GitHub Desktop put theirs (2026.10.07.6). The day
reports from Strawbarry carry a commit, which `store` reads that way.

Here, PATH is stripped of every folder that holds git, and `store.git_exe`
is given the real one, as it would find GitHub Desktop's. Nothing is
written: the call is `git rev-parse --short HEAD` in this repo.

    python tools/check_floss_git.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

ok = bad = 0


def check(name, cond, got=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r" % (name, got))


def main():
    real = shutil.which("git")
    if not real:
        print("  this computer has no git on PATH to hide; nothing to check")
        return 1
    real = os.path.abspath(real)
    names = ("git.exe", "git.cmd", "git.bat", "git")
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not any(os.path.isfile(os.path.join(d, n)) for n in names)]
    os.environ["PATH"] = os.pathsep.join(keep)

    # The machine this stands for: no git on PATH...
    hidden = shutil.which("git") is None
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=30)
        bare = "ran"
    except FileNotFoundError as exc:
        bare = str(exc)
    check("precondition: with git off PATH, plain \"git\" cannot be started "
          "(the ticket's words)", hidden and "WinError 2" in bare
          if os.name == "nt" else hidden and bare != "ran", bare)

    # ...but a git that store.git_exe() finds, as it finds GitHub Desktop's.
    from backend import store
    store._GIT_EXE[:] = [real]
    from backend import floss
    try:
        got = floss._git(["rev-parse", "--short", "HEAD"], floss.REPO_ROOT).strip()
        err = None
    except Exception as exc:                             # noqa: BLE001
        got, err = None, "%s: %s" % (type(exc).__name__, exc)
    check("Floss runs git where store.git_exe() found it, as the rest of "
          "Jarvis does", bool(got) and err is None, err or got)

    print("\n%d ok, %d failed" % (ok, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
