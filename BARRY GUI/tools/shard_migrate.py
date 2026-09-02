"""
shard_migrate.py -- Convert pre-sharding logs into per-machine records.

Every editable file written before shards.py existed becomes this machine's
shard of the same record:

    sessions/m1s2.json  ->  sessions/m1s2@z390-4f1a.json

Content is unchanged; only the name moves, and with it the guarantee that
nobody else will ever write that file.

Run once per clone, and commit the result. Two clones both running it produces
"both deleted the old file, each added their own", which git resolves without
asking anyone -- whereas one clone editing a file another has deleted is the
one conflict shape this whole design exists to avoid, so do it deliberately
and early rather than letting it happen lazily on the first write.

Booting BARRY does the same thing automatically. This is here for the case
where you would rather do it in one step, see the count, and commit before
anything else touches the logs.

    python tools/shard_migrate.py            # say what would move
    python tools/shard_migrate.py --write
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import shards  # noqa: E402


def legacy_in(folder, ext=".json"):
    out = []
    for name in sorted(_ls(folder)):
        if not name.endswith(ext):
            continue
        _base, machine = shards.split_name(name, ext)
        if machine == shards.LEGACY:
            out.append(name)
    return out


def _ls(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=os.path.join(APP, "GUI_logs"))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    logs = os.path.abspath(args.logs)
    if not os.path.isdir(logs):
        print("No such folder: " + logs)
        return 2

    me = shards.machine_id()
    print("Logs      %s" % logs)
    print("Machine   %s" % me)
    print("Mode      %s" % ("WRITE" if args.write else "dry run"))
    print()

    folders = [
        ("sessions", os.path.join(logs, "sessions"), ".json"),
        ("presets", os.path.join(logs, "presets"), ".json"),
        ("event bank", os.path.join(logs, "event_bank"), ".json"),
        ("curation sets", os.path.join(logs, "curation"), ".json"),
        ("layer sheets", os.path.join(logs, "layers"), ".json"),
        ("mice", os.path.join(logs, "mice"), ".json"),
        ("storyboards", os.path.join(logs, "storyboards"), ".json"),
        ("result tags", os.path.join(logs, "results", "curation"), ".json"),
        ("error triage", os.path.join(logs, "errors"), ".json"),
        ("error log", os.path.join(logs, "errors"), ".jsonl"),
        ("activity log", os.path.join(logs, "activity"), ".jsonl"),
    ]

    total = 0
    for label, folder, ext in folders:
        found = legacy_in(folder, ext)
        loose = [n for n in found if n != "resolved.json"] \
            if label == "error triage" else found
        if label == "error triage":
            loose = [n for n in found if n == "resolved.json"]
        print("  %-15s %4d to convert" % (label, len(loose)))
        total += len(loose)

    singles = []
    for name in ("preferences.json",):
        if os.path.isfile(os.path.join(logs, name)):
            singles.append(name)
            total += 1
    stale = os.path.isfile(os.path.join(logs, "index.json"))

    if singles:
        print("  %-15s %4d to convert  (%s)"
              % ("preferences", len(singles), ", ".join(singles)))
    if stale:
        print("  %-15s %4d to drop      (derived; .cache holds it now)"
              % ("index.json", 1))

    print()
    if not total and not stale:
        print("Nothing to convert. Everything here is already per machine.")
        return 0
    if not args.write:
        print("%d file(s) would move. Re-run with --write." % total)
        return 0

    # Constructing the stores is what performs the migration: every book
    # absorbs its own legacy files, so there is exactly one implementation of
    # "what does converting mean" and this tool cannot drift from it.
    from backend import (curation, eventbank, layers, mice, results, store)

    st = store.Store(logs, auto_stage=False)
    layers.Layers(logs, st)
    curation.Curation(logs, st)
    mice.MouseBook(logs, st)
    eventbank.EventBank(logs, st)
    out = os.path.join(APP, "Output")
    results.Results(st, out, os.path.dirname(APP))

    print("Converted. Check it with:")
    print("    python tools/conflict_check.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
