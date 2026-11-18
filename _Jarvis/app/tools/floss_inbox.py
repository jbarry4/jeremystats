# -*- coding: utf-8 -*-
"""The mother AI's side of Floss: what is waiting, and settling it.

Floss tickets are GUI_logs/floss/<id>@<shard>.json (backend/floss.py). They
reach this machine by git. docs/floss.md says what to do with each.

    python tools/floss_inbox.py                  open tickets on disk
    python tools/floss_inbox.py --remote         also origin/master's (fetches; never pulls)
    python tools/floss_inbox.py show ID          one ticket: ask, report, needs, patch
    python tools/floss_inbox.py patch ID > x.diff
    python tools/floss_inbox.py mark ID integrated|changed|rejected|noted
                                      [--commit SHA] [--note "..."]

Open = no `mother` field yet, and something to look at: a patch (ready,
held, applied, dismissed), needs, or a failure.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
DIR = os.path.join(APP, "GUI_logs", "floss")
sys.path.insert(0, APP)
from backend.paths import APP_REL, REPO_ROOT  # noqa: E402


def _local():
    out = {}
    for p in glob.glob(os.path.join(DIR, "*@*.json")):
        try:
            with open(p, encoding="utf-8") as fh:
                t = json.load(fh)
            out[os.path.basename(p)] = (t, p)
        except (OSError, ValueError):
            pass
    return out


def _remote():
    git = lambda *a: subprocess.run(["git"] + list(a), cwd=REPO_ROOT, capture_output=True)
    git("fetch", "-q", "origin")
    rel = APP_REL + "/GUI_logs/floss/"
    names = git("ls-tree", "--name-only", "origin/master", rel).stdout.decode().split()
    out = {}
    for n in names:
        if n.endswith(".json"):
            r = git("show", "origin/master:" + n)
            try:
                out[os.path.basename(n)] = (json.loads(r.stdout.decode("utf-8")), None)
            except ValueError:
                pass
    return out


def _open(t):
    if t.get("mother"):
        return False
    rep = t.get("report") or {}
    return bool(t.get("patch") or rep.get("needs") or t.get("status") == "failed")


def _find(tid, every):
    hits = [v for k, v in every.items() if k.startswith(tid)]
    if len(hits) != 1:
        sys.exit("%d tickets match %s" % (len(hits), tid))
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="list", choices=("list", "show", "patch", "mark"))
    ap.add_argument("id", nargs="?")
    ap.add_argument("verdict", nargs="?", choices=("integrated", "changed", "rejected", "noted"))
    ap.add_argument("--remote", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--commit")
    ap.add_argument("--note")
    a = ap.parse_args()
    every = _local()
    if a.remote:
        for k, v in _remote().items():
            every.setdefault(k, v)

    if a.cmd == "list":
        rows = sorted(every.items(), reverse=True)
        n = 0
        for name, (t, path) in rows:
            if not a.all and not _open(t):
                continue
            n += 1
            rep = t.get("report") or {}
            print("%-44s %-10s %-9s %s" % (name[:-5], t.get("status"),
                                           "disk" if path else "remote", t.get("who") or ""))
            print("    ask:   %s" % " ".join((t.get("ask") or "").split())[:200])
            if rep.get("summary"):
                print("    found: %s" % rep["summary"])
            for f in t.get("files") or []:
                print("    file:  %s (+%d -%d)" % (f["path"], f["added"], f["removed"]))
            for w in t.get("held_because") or []:
                print("    held:  %s" % w)
            for w in rep.get("needs") or []:
                print("    needs: %s" % w)
        print("%d %s" % (n, "tickets" if a.all else "open"))
        return

    t, path = _find(a.id or "", every)
    if a.cmd == "patch":
        sys.stdout.write(t.get("patch") or "")
        return
    if a.cmd == "show":
        print(json.dumps({k: v for k, v in t.items() if k != "patch"}, indent=1, ensure_ascii=False))
        print("\n--- patch ---\n" + (t.get("patch") or "(none)"))
        return
    if not a.verdict:
        sys.exit("mark needs integrated, changed, rejected or noted")
    if not path:
        sys.exit("that ticket is only on origin/master; pull first, then mark it")
    t["mother"] = {"status": a.verdict, "commit": a.commit, "note": a.note,
                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write((json.dumps(t, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    os.replace(tmp, path)
    print("marked %s %s" % (os.path.basename(path), a.verdict))


if __name__ == "__main__":
    main()
