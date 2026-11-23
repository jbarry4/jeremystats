# -*- coding: utf-8 -*-
"""What this machine knows about the animals, beside the Drive:

  registry.json   every recording Jarvis knows (project, mouse, session,
                  start time, folders, retired?) -- the recording dates are
                  the most trustworthy dates the lab has: the acquisition
                  system wrote them.
  mice.json       Jarvis's per-mouse attributes (genotype, DOB, implant...)
  softmouse.json  every mouse in SoftMouse.NET, ended ones too (read-only call)
  vos.json        every VOS census Jarvis or the sheet kept (cage, DOB, sex)
  local text      repo documents (xlsx/csv/docx/pdf/txt/md) outside caches,
                  into <work>/text/local__*.txt, listed in local_sources.json
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import extract  # noqa: E402
from backend.paths import LOGS_DIR, REPO_ROOT  # noqa: E402

W = os.path.expandvars(r"%LOCALAPPDATA%\Jarvis\chickenscratch")
DOC_EXT = (".xlsx", ".xlsm", ".csv", ".docx", ".pdf", ".txt", ".md")
SKIP = (os.sep + ".git", os.sep + "GUI_logs" + os.sep + ".cache", os.sep + "node_modules",
        os.sep + "web" + os.sep, os.sep + "Results" + os.sep, "histo_cache",
        os.sep + "GUI_logs" + os.sep + "error_reports", os.sep + "backend" + os.sep,
        os.sep + "Data Bank" + os.sep + "HARNESS", os.sep + "Apps Script")
MAX = 30 * 1024 * 1024


def dump(name, obj):
    with open(os.path.join(W, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=0, default=str)


def registry():
    from backend import store, sessreg, mice as micebook
    S = store.Store(LOGS_DIR, auto_stage=False)
    rows = sessreg.Registry(S).all()
    keep = []
    for r in rows:
        keep.append({k: r.get(k) for k in ("gid", "project", "mouse", "session", "start",
                                           "label", "key", "retired", "here", "paths",
                                           "facts", "notes", "created")})
    dump("registry.json", keep)
    ms = micebook.MouseBook(LOGS_DIR, S).all()
    dump("mice.json", [{k: m.get(k) for k in ("project", "mouse", "attrs", "created", "updated")}
                       for m in ms])
    return len(keep), len(ms)


def softmouse_full():
    from backend import softmouse
    mice = softmouse._read_list()
    dump("softmouse.json", mice)
    return len(mice)


def vos():
    out = []
    d = os.path.join(REPO_ROOT, "Colony Management", "VOS Exports", "Jarvis", "syncs")
    for n in sorted(os.listdir(d)):
        if n.endswith(".json"):
            with open(os.path.join(d, n), encoding="utf-8") as fh:
                rec = json.load(fh)
            out.append({"file": n, "date": rec.get("date"), "stamp": rec.get("stamp"),
                        "source": rec.get("source"), "census": rec.get("census")})
    dump("vos.json", out)
    return len(out)


def local_docs():
    out = []
    for root, dirs, files in os.walk(REPO_ROOT):
        if any(s in root + os.sep for s in SKIP):
            dirs[:] = []
            continue
        for n in files:
            if not n.lower().endswith(DOC_EXT) or n.startswith("~$"):
                continue
            p = os.path.join(root, n)
            try:
                if os.path.getsize(p) > MAX:
                    continue
            except OSError:
                continue
            rel = os.path.relpath(p, REPO_ROOT)
            tid = "local__" + hashlib.sha1(rel.encode()).hexdigest()[:16]
            tp = os.path.join(W, "text", tid + ".txt")
            if not os.path.exists(tp):
                try:
                    t = extract.to_text(p)
                except Exception as e:                   # noqa: BLE001
                    t = "[extract failed: %s]" % e
                if t is None:
                    continue
                with open(tp, "w", encoding="utf-8") as fh:
                    fh.write(t)
            out.append({"id": tid, "name": n, "path": "LOCAL/" + rel.replace(os.sep, "/"),
                        "kind": "local", "local": p, "text": tp,
                        "chars": os.path.getsize(tp),
                        "modified": os.path.getmtime(p)})
    dump("local_sources.json", out)
    return len(out)


if __name__ == "__main__":
    os.makedirs(os.path.join(W, "text"), exist_ok=True)
    print("registry, mice:", registry())
    print("vos censuses:", vos())
    print("local docs:", local_docs())
    try:
        print("softmouse:", softmouse_full())
    except Exception as e:                               # noqa: BLE001
        print("softmouse: failed:", e)
