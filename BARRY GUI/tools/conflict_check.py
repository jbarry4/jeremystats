"""
conflict_check.py -- Prove no file in GUI_logs can produce a git conflict.

A merge conflict needs two things: a file tracked by git, and two machines that
both change it. Take either away and the conflict is impossible. So every file
under GUI_logs has to be one of:

    per-machine   the filename carries a machine tag, so only that machine
                  ever writes it                       sessions/m1s2@z390-4f1a.json
    write-once    created by its author and never edited afterwards
                                                       runs/2026-09-02/a1b2.json
    untracked     derived, and in .gitignore           .cache/index.json
    inert         documentation, no code writes it     README.md

Anything else is a latent conflict, and this says so by name rather than
waiting for the first bad pull to find it.

The check is deliberately dumb and external: it looks at what is actually on
disk, not at what the code intends. A new store added six months from now that
forgets to shard shows up here the first time it writes a file.

    python tools/conflict_check.py
    python tools/conflict_check.py --logs <path>   # check another clone
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import shards  # noqa: E402

# Files created once and never touched again. A run record is written when the
# run starts and completed by the same process moments later; no other machine
# has any reason to open it.
WRITE_ONCE = ("runs/",)

# Not written by code at all.
INERT = ("README.md", ".gitignore")


def tracked(root, path):
    """Is git watching this file? Untracked files cannot conflict."""
    try:
        res = subprocess.run(["git", "check-ignore", "-q", path],
                             cwd=root, capture_output=True, timeout=10)
        return res.returncode != 0
    except Exception:               # noqa: BLE001
        return True                 # assume the worst


def classify(rel, name):
    if any(rel.startswith(p) for p in WRITE_ONCE):
        return "write-once", "one run, one machine, written once"
    if name in INERT:
        return "inert", "documentation"
    stem = name.rsplit(".", 1)[0]
    if shards.SIGIL in stem:
        machine = stem.rsplit(shards.SIGIL, 1)[1]
        return "per-machine", "only " + machine + " writes this"
    return "SHARED", "no machine tag: two people can both edit it"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=os.path.join(APP, "GUI_logs"))
    ap.add_argument("--quiet", action="store_true",
                    help="only print the problems")
    args = ap.parse_args()

    root = os.path.abspath(args.logs)
    if not os.path.isdir(root):
        print("No such folder: " + root)
        return 2

    repo = os.path.dirname(root)
    print("Checking  %s" % root)
    print("This machine writes as  %s" % shards.machine_id())
    print()

    kinds = {}
    bad = []
    others = set()
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".cache", "__pycache__")]
        for name in sorted(files):
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            kind, why = classify(rel, name)
            if kind == "SHARED":
                if not tracked(repo, full):
                    kind, why = "untracked", "git ignores it"
                else:
                    bad.append((rel, why))
            else:
                stem = name.rsplit(".", 1)[0]
                if shards.SIGIL in stem:
                    others.add(stem.rsplit(shards.SIGIL, 1)[1])
            kinds[kind] = kinds.get(kind, 0) + 1

    for kind in ("per-machine", "write-once", "untracked", "inert", "SHARED"):
        if kind in kinds:
            print("  %-14s %6d file(s)" % (kind, kinds[kind]))

    if others:
        print()
        print("Machines that have written here: %s"
              % ", ".join(sorted(others)))

    print()
    if bad:
        print("%d file(s) COULD CONFLICT -- tracked by git with no machine "
              "tag, so two people editing the same thing collide:" % len(bad))
        for rel, why in bad[:40]:
            print("   %-56s %s" % (rel, why))
        if len(bad) > 40:
            print("   ... and %d more" % (len(bad) - 40))
        print()
        print("Fix: route whatever writes them through a shards.Book (see "
              "backend/shards.py), or add them to .gitignore if they are "
              "derived.")
        return 1

    print("No file here can conflict. Every editable record is per machine, "
          "every append-only log is per machine per day, and everything "
          "derived is untracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
