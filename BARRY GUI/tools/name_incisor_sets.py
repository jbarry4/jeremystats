"""
name_incisor_sets.py -- give every "Incisor CSC##" entry its session.

WHY

Incisor names a banked set after the channel it scanned, which is the one
fact it is sure of and the one fact that does not identify anything: ten
entries in this bank are named exactly "Incisor CSC##", and six of those
names are shared. Two different recordings both called "Incisor CSC42" --
PTEN m47 s1 and PTEN m5 s2 -- are indistinguishable in any list that shows
a name, which is every list.

WHAT IT DOES

    Incisor CSC42   ->   Incisor CSC42_PTEN m47 s1 2024-12-04

The session label, which is what somebody actually recognises. Where an
entry has none, the recording's folder name is used, and where there is
neither, the first characters of the group id -- ugly, and still better
than a name shared with something else.

SAME NAME, SAME SESSION IS A DIFFERENT PROBLEM. Three entries here are
called "Incisor CSC46" and all three are the same recording with the same
count: that is not a naming collision, it is the same set banked three
times. Renaming cannot fix it and this does not pretend to -- they get the
same session suffix plus a short piece of their own id, so they can at
least be told apart, and they are listed at the end for somebody to decide
about. Deleting a banked entry is not a thing a script should decide.

Nothing but the name changes. No events, no versions, no labels.

    python tools\\name_incisor_sets.py            # say what it would do
    python tools\\name_incisor_sets.py --apply    # do it
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import app as A                              # noqa: E402

# Exactly "Incisor CSC" and digits. An entry somebody has already renamed,
# or named something else entirely, is left alone -- this is here to fix a
# generated name, not to impose a convention on names people chose.
PAT = re.compile(r"^Incisor CSC(\d+)$")


def detail_for(rec):
    """What to put after the channel: the most recognisable thing there is."""
    for key in ("session_label", "session_path"):
        got = (rec.get(key) or "").strip()
        if got:
            return os.path.basename(got.rstrip("/\\")) if key == \
                "session_path" else got
    gid = (rec.get("gid") or "").strip()
    return ("recording " + gid[:8]) if gid else "unknown recording"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write the names; without it, only say what would "
                         "change")
    args = ap.parse_args()

    rows = [e for e in A.BANK.all() if PAT.match((e.get("name") or "").strip())]
    if not rows:
        print("No entry is named 'Incisor CSC##'. Nothing to do.")
        return

    was = Counter((e.get("name") or "") for e in rows)
    print("%d entr%s named 'Incisor CSC##'; %d name(s) shared by more than "
          "one" % (len(rows), "y" if len(rows) == 1 else "ies",
                   sum(1 for v in was.values() if v > 1)))

    # First pass: the name everybody would get.
    want = {}
    for rec in rows:
        want[rec["id"]] = "%s_%s" % (rec.get("name"), detail_for(rec))

    # Second: where that is still shared, the same recording is banked more
    # than once. Add a piece of each entry's own id so a list can tell them
    # apart, and say so at the end.
    again = Counter(want.values())
    twins = defaultdict(list)
    for rec in rows:
        if again[want[rec["id"]]] > 1:
            twins[want[rec["id"]]].append(rec)
            want[rec["id"]] += " (" + str(rec["id"])[:4] + ")"

    print()
    for rec in sorted(rows, key=lambda r: (r.get("name") or "")):
        print("  %-16s -> %s" % (rec.get("name"), want[rec["id"]]))

    if twins:
        print("\nSAME RECORDING, BANKED MORE THAN ONCE -- a naming fix "
              "cannot help these:")
        for name, recs in twins.items():
            print("  %s" % name)
            for r in recs:
                print("      id %s  %s event(s)  added %s"
                      % (str(r["id"])[:8], r.get("n"),
                         ((r.get("added") or {}).get("at") or "?")[:19]))
        print("  They are the same set filed twice or three times. Deleting "
              "one is a decision for a person:\n"
              "  the Event Bank can remove an entry, and its versions go "
              "with it.")

    if not args.apply:
        print("\nNothing was written. Run again with --apply.")
        return

    done = 0
    for rec in rows:
        try:
            A.BANK.update(rec["id"], {"name": want[rec["id"]]})
            done += 1
        except Exception as exc:                          # noqa: BLE001
            print("  could not rename %s: %s" % (str(rec["id"])[:8], exc))
    print("\nrenamed %d of %d" % (done, len(rows)))


if __name__ == "__main__":
    main()
