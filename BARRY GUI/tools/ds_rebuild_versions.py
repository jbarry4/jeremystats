"""
ds_rebuild_versions.py -- rebuild every dentate-spike entry's history from
the snapshot folders, once.

What the history should say
--------------------------
For a recording that was sorted by dragging PNGs into subfolders, there are
exactly two things that ever happened to it:

    v0    the detector found N candidates and nobody had looked at any of
          them
    v1    somebody went through all N and filed each one

Anything else in the version list is an artifact of how the entry got into
Jarvis -- a bank that ran twice, a per-category split that was later folded
in, a version written before `label_id` was stored. Those are not passes of
curation and reading them as passes makes the history lie about how much
review a set has had.

So this replaces the version list of each matched entry with exactly those
two, built from the folders on disk, and drops the rest.

Where the numbers come from
---------------------------
The folder layout, which `dsimport.py` already knows how to read:

    <recording>/
      Raster_Evt001_1ch.png     every candidate, numbered, never moved
      ...
      Dentate Spike/            a copy in here means "yes"
      Garbage/                  ...means "no"
      Flag/                     ...means "come back to this"
      Flag for Deep Review/     ...means "come back to this properly"

A candidate in the root with no copy in any subfolder is unsorted, and stays
unspecified in v1 -- that is a real state, not a missing one. A candidate
filed under two different decisions is not a decision: it becomes a flag,
which is what `dsimport.CONFLICT_LABEL` is for.

Times come from the bank entry, matched by position, and that is only safe
because the counts agree exactly -- checked per folder by the scan, which
refuses anything that does not line up rather than importing it half-right.

Safety
------
Nothing is written without `--write`. The dry run prints every entry, what
its versions are now and what they would become. The event times themselves
are never touched: only the `versions` list, `version`, `by_label` and
`label_names`. And the whole bank is git-tracked, so a bad run is one
`git checkout` away from undone.

    python tools/ds_rebuild_versions.py --root "E:\\PTEN_DS_Curation\\..." --dry-run
    python tools/ds_rebuild_versions.py --root "E:\\PTEN_DS_Curation\\..." --write
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(ROOT))

_pkg = os.path.basename(ROOT)
_mod = __import__(_pkg + ".backend", fromlist=["dsimport", "eventbank",
                                               "store", "shards"])
dsimport = _mod.dsimport
eventbank = _mod.eventbank
storemod = _mod.store


def _stamp(rec, key, fallback):
    got = (rec.get(key) or {})
    return got.get("at") or fallback


def rebuild(root, logs_dir, write=False, kind="ds"):
    store = storemod.Store(logs_dir, auto_stage=False)
    bank = eventbank.EventBank(logs_dir, store)

    rows = dsimport.scan(root, bank, kind=kind)
    ready = [r for r in rows if r.get("verdict") == "ready"]
    skipped = [r for r in rows if r.get("verdict") != "ready"]

    print("%d folder(s) under" % len(rows))
    print("   %s" % root)
    print("%d ready, %d skipped\n" % (len(ready), len(skipped)))
    for r in skipped:
        print("   skipped  %-24s %-16s %s"
              % (r.get("folder"), r.get("verdict"),
                 (r.get("reason") or "")[:60]))
    if skipped:
        print()

    names = {}
    from importlib import import_module
    curation = import_module(_pkg + ".backend.curation")
    for lab in curation.vocabulary(kind):
        names[lab["id"]] = lab["name"]

    done, missed = [], []
    for r in ready:
        entry = bank.get(r["entry_id"])
        if not entry:
            missed.append((r["folder"], "the entry is gone"))
            continue
        events = entry.get("events") or []
        marks = r.get("_events") or {}
        if len(events) != len(marks):
            missed.append((r["folder"], "%d events vs %d snapshots"
                           % (len(events), len(marks))))
            continue

        # v1's snapshot: the times in the entry's own order, each carrying
        # the label the folders say. Written as label ids, which is what
        # `restore` maps back and what a curation set actually speaks.
        snap1, counts = [], {}
        for i, ev in enumerate(events, start=1):
            lab = marks.get(i) or None
            snap1.append([ev.get("start"), lab])
            key = lab or "unspecified"
            counts[key] = counts.get(key, 0) + 1

        n = len(events)
        was = [v.get("v") for v in (entry.get("versions") or [])]
        by = (entry.get("added") or {}).get("by") or "unknown"
        at0 = _stamp(entry, "added", None)

        v0 = {
            "v": 0,
            "id": "v0-" + uuid.uuid4().hex[:8],
            "at": at0,
            "by": by,
            "note": "Imported from "
                    + ((entry.get("source") or {}).get("pipeline")
                       or "a detector")
                    + ". " + str(n) + " candidates, none decided yet.",
            "n": n,
            "by_label": {"unspecified": n},
            "changed": 0, "gained": 0, "lost": 0, "moves": {},
            "machine": (entry.get("added") or {}).get("machine"),
            "imported": True,
            # Every time, with no decision on any of it. This is the thing
            # curation was done *to*, and keeping it is what makes the sort
            # in v1 undoable.
            "snap": [[ev.get("start"), None] for ev in events],
        }
        # What actually moved between the two, per candidate, so the entry
        # says how the sort went rather than only what it ended at.
        moves = {}
        for lab in set(m for m in marks.values() if m):
            step = "undecided \u2192 %s" % lab
            moves[step] = sum(1 for m in marks.values() if m == lab)
        decided = sum(1 for m in marks.values() if m)

        v1 = {
            "v": 1,
            "id": "v1-" + uuid.uuid4().hex[:8],
            "at": _stamp(entry, "updated", at0),
            "by": (r.get("_notes") and by) or by,
            "note": "Sorted by dragging the snapshots into folders, before "
                    "Jarvis. " + str(decided) + " of " + str(n)
                    + " decided"
                    + (", %d filed under two folders and flagged"
                       % len(r.get("conflicts") or [])
                       if r.get("conflicts") else "")
                    + ".",
            "n": n,
            "by_label": dict(counts),
            "changed": decided,
            "gained": 0, "lost": 0,
            "moves": moves,
            "machine": (entry.get("added") or {}).get("machine"),
            "snap": snap1,
            "rebuilt_from": {"folder": r.get("folder"), "root": root},
        }

        entry["versions"] = [v0, v1]
        entry["version"] = 1
        entry["by_label"] = dict(counts)
        entry["label_names"] = dict(names)

        done.append({
            "folder": r.get("folder"),
            "entry": entry["id"],
            "name": entry.get("name"),
            "session": entry.get("session_label"),
            "n": n, "decided": decided,
            "was": was, "counts": counts,
            "conflicts": len(r.get("conflicts") or []),
        })
        if write:
            bank._save(entry)

    # ------------------------------------------------------------------
    w = max([len(d["folder"]) for d in done] + [10])
    print("%-*s  %6s %6s  %-18s  %s"
          % (w, "folder", "n", "sorted", "versions were", "now"))
    for d in done:
        print("%-*s  %6d %6d  %-18s  %s"
              % (w, d["folder"], d["n"], d["decided"],
                 (str(d["was"]) if d["was"] else "(none)")[:18], "[0, 1]"))
    print()
    for f, why in missed:
        print("   NOT rebuilt  %-24s %s" % (f, why))
    if missed:
        print()

    tot = {}
    for d in done:
        for k, v in d["counts"].items():
            tot[k] = tot.get(k, 0) + v
    print("%d entr%s rebuilt to v0 + v1"
          % (len(done), "y" if len(done) == 1 else "ies"))
    print("   candidates : %d" % sum(d["n"] for d in done))
    print("   decided    : %d" % sum(d["decided"] for d in done))
    print("   by label   : %s"
          % "  ".join("%s %d" % (names.get(k, k), tot[k])
                      for k in sorted(tot, key=lambda x: -tot[x])))
    print("   conflicts  : %d filed under two folders, flagged"
          % sum(d["conflicts"] for d in done))
    dropped = sum(max(0, len([x for x in d["was"] if x not in (0, 1)]))
                  for d in done)
    print("   dropped    : %d version(s) that were neither v0 nor v1"
          % dropped)
    if not write:
        print("\nDry run -- nothing was written. Add --write to apply.")
    return done, missed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True,
                    help="the folder of per-recording snapshot folders")
    ap.add_argument("--logs", default=os.path.join(ROOT, "GUI_logs"))
    ap.add_argument("--kind", default="ds")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(a.root):
        print("No such folder: %s" % a.root)
        return 2
    rebuild(a.root, a.logs, write=a.write, kind=a.kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
