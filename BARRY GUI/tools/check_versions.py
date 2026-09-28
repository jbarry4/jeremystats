# -*- coding: utf-8 -*-
"""Prove the on-read version repair loses nothing, against the real bank.

    python tools/check_versions.py

`versions.repair` folds pre-id twins into their id-bearing copies and gives
every remaining version a derived id. It changes nothing on disk -- it runs
on what is read -- but it still decides what a person SEES, so it has to be
shown not to hide anything. For every entry in the merged bank this asserts:

  nothing lost     every input version survives as a version whose fields
                   are a superset of its own. A twin is only folded when the
                   copy it folds into already says everything it says.
  every snapshot   the set of distinct snapshots is the same before and after.
  unique ids       no two versions of one entry share an id afterwards, so
                   every version can be asked for exactly.
  deterministic    repairing twice gives the same ids -- two machines reading
                   the same history agree without talking to each other.

Read-only. Exit 1 if any assertion fails.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
os.environ.setdefault("JARVIS_WARM", "0")

from backend import versions as V          # noqa: E402
from backend.app import BANK               # noqa: E402

IGNORE = {"id", "id_derived"}


def covers(big, small):
    """Whether `big` carries every field `small` does, with the same value."""
    return all(k in IGNORE or (k in big and big[k] == v)
               for k, v in small.items())


def snaps(vers):
    return {json.dumps(v.get("snap"), sort_keys=True)
            for v in vers if v.get("snap") is not None}


def main():
    entries = BANK.all()
    problems = []
    tot_in = tot_out = folded = derived = 0
    dup_before = dup_after = 0

    for rec in entries:
        eid = rec.get("id") or "?"
        vin = [v for v in (rec.get("versions") or []) if isinstance(v, dict)]
        if not vin:
            continue
        vout, rep = V.repair(eid, vin)
        again, _ = V.repair(eid, vin)
        tot_in += len(vin)
        tot_out += len(vout)
        folded += rep["folded"]
        derived += rep["derived"]

        # Numbers that no id could tell apart, before; ids that repeat, after.
        by_v = {}
        for v in vin:
            by_v.setdefault(v.get("v"), []).append(v)
        for group in by_v.values():
            if len(group) > 1 and len({g.get("id") for g in group
                                       if g.get("id")}) < len(group):
                dup_before += 1
        ids = [v["id"] for v in vout]
        if len(ids) != len(set(ids)):
            dup_after += 1
            problems.append("%s: repeated ids after repair" % eid)

        for v in vin:
            if not any(covers(o, v) for o in vout):
                problems.append("%s: version v%s by %s at %s was LOST"
                                % (eid, v.get("v"), v.get("by"), v.get("at")))
        if snaps(vin) != snaps(vout):
            problems.append("%s: the set of snapshots changed" % eid)
        if [v["id"] for v in again] != ids:
            problems.append("%s: repair is not deterministic" % eid)

    print("entries with a history  %d" % sum(1 for r in entries
                                             if r.get("versions")))
    print("versions read           %d" % tot_in)
    print("versions after repair   %d" % tot_out)
    print("pre-id twins folded     %d" % folded)
    print("ids derived             %d" % derived)
    print("numbers no id resolved  %d before, %d after" % (dup_before, dup_after))
    print()
    if problems:
        print("%d PROBLEM(S):" % len(problems))
        for p in problems[:40]:
            print("  " + p)
        return 1
    print("nothing lost: every version survives whole, every snapshot is kept, "
          "every id is unique, and the repair is deterministic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
