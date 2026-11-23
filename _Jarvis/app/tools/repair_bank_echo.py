# -*- coding: utf-8 -*-
"""Restore bank events that another machine's stripped copy is hiding.

    python tools\\repair_bank_echo.py            # dry run: list, change nothing
    python tools\\repair_bank_echo.py --apply    # back up, then repair
    python tools\\repair_bank_echo.py --apply --only <entry id>

What happened (found 2026-09-30). On 2026-09-25 barrylab pulled the DEWEY
Spark entries from the cloud while running code from before the bank knew
`clipped`/`excluded`, so its `bank.add` dropped them, and wrote its copy
stamped a minute AFTER this machine's original. Rain's commit of those
shards (2026-09-28) was merged here, and field-level newest-wins let the
stripped echo win: 31 of 35 DEWEY entries read back with no clipping at
all, and Coupling correlated clipped wires as if they were clean.

The measurements were never lost -- this machine's own shard still holds
them. The repair re-files each affected entry through the bank's own
`add()` with THIS machine's events. Book.write re-stamps a field only when
it differs from what was read, so the events get today's stamp and win the
merge from now on. No new version is minted: the event times and labels
are the same, and a version records what a person decided, which did not
change.

Refuses an entry unless this machine's events and the merged events have
the same times and labels -- the repair only ever ADDS back fields the
echo dropped; it never changes what an event is.

Every shard it touches is copied first to
GUI_logs/.cache/bank_repair_backup_<stamp>/ (git-ignored).
"""
import glob
import io
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

BANK_DIR = os.path.join(APP, "GUI_logs", "event_bank")
EXTRA = ("clipped", "excluded", "kept")


def load(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ident(evs):
    return [(round(float(e.get("start")), 6),
             None if e.get("end") is None else round(float(e["end"]), 6),
             e.get("label")) for e in (evs or [])]


def extras(evs):
    return sum(1 for e in (evs or []) for k in EXTRA if e.get(k))


def main():
    apply = "--apply" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv \
        else None
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from backend import app as appmod
    from backend import shards
    BANK = appmod.BANK
    me = shards.machine_id()

    todo, refused = [], []
    for path in sorted(glob.glob(os.path.join(BANK_DIR, "*@%s.json" % me))):
        if os.path.basename(path).startswith(("harness_", "demo_")):
            continue                      # test data is not repaired
        mine = load(path)
        eid = mine.get("id")
        if not eid or (only and eid != only):
            continue
        merged = BANK.get(eid) or {}
        want, have = mine.get("events") or [], merged.get("events") or []
        if extras(want) <= extras(have):
            continue                      # nothing hidden here
        if ident(want) != ident(have):
            refused.append((eid, os.path.basename(path),
                            "the events themselves differ, not just their "
                            "clipping -- left for a person"))
            continue
        todo.append((eid, path, mine, merged))

    print("this machine: %s" % me)
    print("%d entr%s with fields hidden by another machine's copy"
          % (len(todo), "y" if len(todo) == 1 else "ies"))
    for eid, path, mine, merged in todo:
        print("  %s r%s s%s  %s  this machine %d fields, merged view %d"
              % (eid, merged.get("mouse"), merged.get("session"),
                 os.path.basename(path), extras(mine.get("events")),
                 extras(merged.get("events"))))
    for eid, name, why in refused:
        print("  REFUSED %s %s: %s" % (eid, name, why))
    if not apply:
        print("\ndry run: nothing changed. Run with --apply to repair.")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(APP, "GUI_logs", ".cache",
                          "bank_repair_backup_" + stamp)
    os.makedirs(backup, exist_ok=True)
    for eid, _p, _m, _g in todo:
        for f in glob.glob(os.path.join(BANK_DIR, "*_%s@*.json" % eid)):
            shutil.copy2(f, backup)
    print("\nbacked up to %s" % backup)

    fixed, failed = 0, []
    for eid, path, mine, merged in todo:
        src = merged.get("source") or {}
        added = merged.get("added") or {}
        body = {k: merged.get(k) for k in (
            "id", "gid", "project", "mouse", "session", "session_key",
            "session_loose_key", "session_label", "session_path",
            "recording_start", "duration_s", "type", "type_name", "name",
            "note", "curation_label", "time_basis")}
        body.update({
            "events": mine.get("events"),
            "pipeline": src.get("pipeline"),
            "source_file": src.get("file"),
            "parameters": src.get("parameters"),
            "detector": src.get("detector"),
            "added_by": added.get("by"),
            "curated": bool(merged.get("specified")),
        })
        before_versions = len(merged.get("versions") or [])
        try:
            BANK.add(body)
        except Exception as exc:                        # noqa: BLE001
            failed.append((eid, str(exc)))
            continue
        after = BANK.get(eid) or {}
        ok = (extras(after.get("events")) == extras(mine.get("events"))
              and ident(after.get("events")) == ident(mine.get("events"))
              and len(after.get("versions") or []) == before_versions
              and all(after.get(k) == merged.get(k) for k in (
                  "gid", "project", "mouse", "session", "session_label",
                  "type", "name")))
        if ok:
            fixed += 1
        else:
            failed.append((eid, "the re-read does not match what was "
                                "written; restore from %s" % backup))
    print("repaired %d, failed %d" % (fixed, len(failed)))
    for eid, why in failed:
        print("  FAILED %s: %s" % (eid, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
