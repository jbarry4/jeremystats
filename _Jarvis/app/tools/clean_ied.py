# -*- coding: utf-8 -*-
"""clean_ied.py -- a solids-only version of each imported IED set.

The import banks everything the detector found, with whatever verdicts
the folders recorded on top: Solid, Sputter, Flag, Garbage, and a large
majority nobody ever rendered. That is the right thing to keep, because
it is what the tree actually says -- but it is not what you plot.

This adds a NEW VERSION to each of those entries holding only the
events somebody confirmed. Same entry, same id, same lineage: the bank
computes the diff itself, so the version history reads "1,033 lost" and
the fuller version is still there to go back to. Nothing is deleted.

    python tools/clean_ied.py                  # dry run; says what it would do
    python tools/clean_ied.py --write
    python tools/clean_ied.py --write --keep solid,sputter

SPUTTER IS DROPPED BY DEFAULT and it is a judgement, so it is one flag
away. `curation.KINDS['ied']` counts both Solid and Sputter as good --
a sputtering discharge is still a discharge -- but "the Solid folder
tells us which ones are the real IED events" is how this tree was
described, so Solid is the default and the count of what that costs is
printed every run.

An entry already holding nothing but the kept labels gets no new
version: the bank writes one only when something moved, and a version
that changed nothing is a line of noise in a history.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import eventbank, store                    # noqa: E402

PIPELINE = "IED hand-sort (ETS)"
LABEL_NAME = {"solid": "Solid", "sputter": "Sputter",
              "garbage": "Garbage", "flag": "Flag"}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=os.path.join(APP, "GUI_logs"))
    ap.add_argument("--keep", default="solid",
                    help="labels to keep, comma separated (default: solid)")
    ap.add_argument("--by", default="import_ied")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                    # noqa: BLE001
        pass

    keep = [k.strip().lower() for k in args.keep.split(",") if k.strip()]
    unknown = [k for k in keep if k not in LABEL_NAME]
    if unknown:
        print("Not an IED label: %s. Pick from %s."
              % (", ".join(unknown), ", ".join(sorted(LABEL_NAME))))
        return 2

    st = store.Store(args.logs, auto_stage=False)
    bank = eventbank.EventBank(args.logs, st)
    mine = [e for e in bank.summaries()
            if (e.get("source") or {}).get("pipeline") == PIPELINE]
    if not mine:
        print("No IED sets from %s are in the bank. Run "
              "tools/import_ied.py first." % PIPELINE)
        return 1

    print("Banking  %s" % os.path.join(args.logs, "event_bank"))
    print("Keeping  %s" % ", ".join(LABEL_NAME[k] for k in keep))
    print("Mode     %s" % ("WRITE" if args.write else "dry run"))
    print()
    print("%-26s %6s %7s %7s  %s"
          % ("recording", "was", "kept", "dropped", "version"))

    total_was = total_kept = 0
    dropped_by_label = {}
    for e in sorted(mine, key=lambda x: (x.get("mouse") or 0,
                                         x.get("session") or 0)):
        full = bank.get(e["id"])
        events = full.get("events") or []
        cut = [ev for ev in events if (ev.get("label_id") or "") in keep]
        for ev in events:
            if (ev.get("label_id") or "") in keep:
                continue
            lid = ev.get("label_id") or "unspecified"
            dropped_by_label[lid] = dropped_by_label.get(lid, 0) + 1
        total_was += len(events)
        total_kept += len(cut)

        vs = full.get("versions") or []
        at = max([v.get("v") or 0 for v in vs] or [0])
        same = len(cut) == len(events)
        note = ("already only %s" % ", ".join(LABEL_NAME[k] for k in keep)
                if same else "v%d" % (at + 1))
        print("%-26s %6d %7d %7d  %s"
              % (full.get("session_label") or full["id"], len(events),
                 len(cut), len(events) - len(cut), note))

        if not args.write or same:
            continue
        if not cut:
            print("      nothing confirmed here; left alone rather than "
                  "banked empty")
            continue

        # Same id, so this is a VERSION of the same entry and the bank
        # works out the diff. The note is the original's, with a line
        # saying what this version is -- the provenance the import
        # established has to survive every later pass.
        base = (full.get("note") or "").strip()
        mark = "Version %d keeps only" % (at + 1)
        if mark not in base:
            base = (base + " " if base else "") + (
                "%s the %s events -- %d of %d -- so the set can be plotted "
                "without filtering. The fuller version is still v%d; "
                "nothing was deleted."
                % (mark, " and ".join(LABEL_NAME[k] for k in keep),
                   len(cut), len(events), at))

        bank.add({
            "id": full["id"],
            "project": full.get("project"),
            "mouse": full.get("mouse"), "session": full.get("session"),
            "session_key": full.get("session_key"),
            "session_loose_key": full.get("session_loose_key"),
            "session_label": full.get("session_label"),
            "session_path": full.get("session_path"),
            "recording_start": full.get("recording_start"),
            "duration_s": full.get("duration_s"),
            "gid": full.get("gid"),
            "type": full.get("type"), "type_name": full.get("type_name"),
            "name": full.get("name"),
            "note": base,
            "events": cut,
            "label_names": full.get("label_names") or dict(LABEL_NAME),
            "pipeline": PIPELINE,
            "source_file": (full.get("source") or {}).get("file"),
            "detector": (full.get("source") or {}).get("detector"),
            "time_basis": "recording",
            "parameters": dict(full.get("parameters") or {}, kept=keep),
            "version_note": (
                "Kept only the %s events: %d of %d. The rest were the "
                "other verdicts and the events nobody rendered; they are "
                "still in v%d."
                % (" and ".join(LABEL_NAME[k] for k in keep),
                   len(cut), len(events), at)),
            "added_by": args.by,
            "curated": True,
        })

    print()
    print("%d events across %d sets, %d kept, %d dropped"
          % (total_was, len(mine), total_kept, total_was - total_kept))
    print("   dropped: %s"
          % ", ".join("%d %s" % (v, LABEL_NAME.get(k, k))
                      for k, v in sorted(dropped_by_label.items(),
                                         key=lambda x: -x[1])))
    if "sputter" not in keep and dropped_by_label.get("sputter"):
        print("   %d Sputter went with them. The ied vocabulary counts "
              "Sputter as good; --keep solid,sputter keeps it."
              % dropped_by_label["sputter"])
    if not args.write:
        print()
        print("Nothing written. Re-run with --write to bank it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
