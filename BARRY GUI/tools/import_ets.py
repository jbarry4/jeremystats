"""
import_ets.py -- Bring an ETS export of dentate-spike times into the Event Bank.

The DS pipeline writes one folder per recording:

    ETS/m1s2_ets/ets_hp_1_lp_300_nf.mat
        Combined_DS_timestamps_sec   [1 x N] seconds from the start

Which is a perfectly good export and a poor place to leave things: the folder
name is the only record of which recording it belongs to, the filter settings
live in the file name, and nothing says whether anyone has looked at the times
yet.

This reads the tree, matches each folder to a recording BARRY already knows by
mouse and session, and files the times in the Event Bank as **unspecified**
dentate-spike candidates. Unspecified is the point: a detector saying "there
is something at 315.275 s" and a person saying "that is a dentate spike" are
different claims, and the bank should not pretend the first is the second.
Curating a set later writes specified entries back.

Safe to run twice. An entry banked by a previous run of this importer, for the
same recording and the same count, is left alone unless --replace is given.

    python tools/import_ets.py                       # dry run, says what it would do
    python tools/import_ets.py --write               # actually bank it
    python tools/import_ets.py --write --replace     # re-import, dropping the old entries
    python tools/import_ets.py --root <path> --by me@lab
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import eventbank, ids, sessreg, store   # noqa: E402

DEFAULT_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(APP)), "jeremystats", "DS Analysis", "ETS")

FOLDER = re.compile(r"^m(\d+)s(\d+)_ets$", re.I)

# What marks an entry as ours, so a second run can recognise its own work.
PIPELINE = "ETS dentate-spike export"


def read_times(path):
    """The timestamp array out of an ETS .mat, whatever the variable is called."""
    import numpy as np
    import scipy.io as sio

    mat = sio.loadmat(path)
    names = [k for k in mat if not k.startswith("__")]
    if not names:
        raise ValueError("no variables in the file")
    # Prefer the documented name; fall back to the only array present, so a
    # renamed export still imports rather than failing silently.
    name = next((n for n in names if "timestamp" in n.lower()), names[0])
    arr = np.asarray(mat[name]).ravel().astype(float)
    arr = arr[np.isfinite(arr)]
    arr.sort()
    return name, arr


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help="the ETS folder (default: %(default)s)")
    ap.add_argument("--logs", default=os.path.join(APP, "GUI_logs"))
    ap.add_argument("--by", default=None,
                    help="who is importing (default: the git user BARRY uses)")
    ap.add_argument("--write", action="store_true",
                    help="actually bank it; without this it only reports")
    ap.add_argument("--replace", action="store_true",
                    help="drop entries a previous run of this importer made")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print("No such folder: " + args.root)
        return 2

    st = store.Store(args.logs, auto_stage=False)
    reg = sessreg.Registry(st)
    bank = eventbank.EventBank(args.logs, st)
    known = st.all_sessions()
    existing = bank.summaries()

    print("Reading  %s" % args.root)
    print("Banking  %s" % os.path.join(args.logs, "event_bank"))
    print("Mode     %s%s" % ("WRITE" if args.write else "dry run",
                             "  (replacing)" if args.replace else ""))
    print()

    rows = []
    for name in sorted(os.listdir(args.root)):
        m = FOLDER.match(name)
        if not m:
            continue
        mouse, session = int(m.group(1)), int(m.group(2))
        folder = os.path.join(args.root, name)
        mats = [f for f in sorted(os.listdir(folder)) if f.lower().endswith(".mat")]
        if not mats:
            rows.append((name, mouse, session, 0, None, "no .mat in the folder"))
            continue
        try:
            var, times = read_times(os.path.join(folder, mats[0]))
        except Exception as exc:                       # noqa: BLE001
            rows.append((name, mouse, session, 0, None, "unreadable: %s" % exc))
            continue

        # Which recording is this? Matched the way everything else in BARRY
        # is matched, so an ETS folder lines up with the same recording the
        # bad channels and the layer labels are on.
        ident = {
            "mouse": mouse, "session": session,
            "loose_key": ids.make_loose_key(mouse, session),
            "key": None, "start": None,
        }
        rec, how = ids.match(ident, known)
        rows.append((name, mouse, session, len(times), rec,
                     None if rec else "no recording registered for m%d s%d"
                     % (mouse, session)))

        if not args.write or not rec or not len(times):
            continue

        # Idempotent: our own entry for this recording, same size, is left be.
        mine = [e for e in existing
                if (e.get("source") or {}).get("pipeline") == PIPELINE
                and e.get("mouse") == mouse and e.get("session") == session]
        if mine and not args.replace:
            continue
        for e in mine:
            bank.delete(e["id"])

        bank.add({
            "project": rec.get("project") or rec.get("group"),
            "mouse": mouse,
            "session": session,
            "session_key": rec.get("key"),
            "session_loose_key": rec.get("loose_key"),
            "session_label": rec.get("label"),
            "session_path": (rec.get("paths") or [None])[-1],
            "recording_start": rec.get("start"),
            "gid": rec.get("gid"),
            "type": "ds",
            "name": "DS candidates (ETS)",
            "note": "Imported from %s. Not yet curated: every time in here is "
                    "a detector's candidate, not a confirmed dentate spike."
                    % mats[0],
            "events": [{"start": float(t)} for t in times],
            "pipeline": PIPELINE,
            "source_file": os.path.join(folder, mats[0]),
            "detector": mats[0].replace(".mat", ""),
            "parameters": {"variable": var, "filter": mats[0]},
            "added_by": args.by,
            # The whole point: these arrive unspecified.
            "curated": False,
        })

    # ---- report -----------------------------------------------------------
    ok = [r for r in rows if r[4] and r[3]]
    missing = [r for r in rows if not r[4]]
    empty = [r for r in rows if r[4] and not r[3]]

    print("%-14s %6s %6s   %s" % ("folder", "mouse", "n", "recording"))
    for name, mouse, session, n, rec, why in rows:
        label = (rec or {}).get("label") if rec else ("-- " + (why or "?"))
        print("%-14s %6d %6d   %s" % (name, mouse, n, label))

    print()
    print("%d folder(s): %d matched a registered recording, %d unmatched, "
          "%d empty" % (len(rows), len(ok), len(missing), len(empty)))
    print("%d timestamps in total" % sum(r[3] for r in rows))
    if missing:
        print()
        print("Unmatched. Scan the drive these live on so BARRY registers "
              "them, then run this again:")
        for r in missing:
            print("   %s  (%s)" % (r[0], r[5]))
    if not args.write:
        print()
        print("Nothing written. Re-run with --write to bank it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
