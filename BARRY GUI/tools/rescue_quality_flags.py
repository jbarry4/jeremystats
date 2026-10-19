"""rescue_quality_flags.py -- put stranded quality flags back on a recording.

The Sessions view sent a write identity carrying no gid, no key and no loose
key, so `get_session` had nothing to match on and `upsert_session` read every
"good" as a new recording. The flag never reached the row on screen; it went
into a record of its own holding a label, a flag and no paths at all.

The Sessions view sends the gid now. This moves the flags that were stranded
before the fix onto the recordings they were meant for, and retires the empty
records that were holding them.

The label is what makes that possible -- it was copied onto the stray record,
and it names exactly one live recording. A stray whose label matches none, or
more than one, is reported and left alone rather than guessed at.

    python tools\\rescue_quality_flags.py           # say what would happen
    python tools\\rescue_quality_flags.py --apply   # do it
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import sessreg, store as storemod  # noqa: E402


def main():
    apply = "--apply" in sys.argv
    STORE = storemod.Store(os.path.join(APP, "GUI_logs"), auto_stage=False)
    REG = sessreg.Registry(STORE)

    rows = REG.all()
    # A stray is a record with something somebody said on it and nowhere for
    # it to have come from: no paths at all.
    SAID = ("quality", "notes", "note")
    strays = [r for r in rows
              if not (r.get("paths") or [])
              and not r.get("retired")
              and any(r.get(k) for k in SAID)]

    by_label = defaultdict(list)
    for r in rows:
        if (r.get("paths") or []) and not r.get("retired"):
            by_label[(r.get("label") or "").strip()].append(r)

    print("stranded records carrying a flag or a note: %d\n" % len(strays))
    if not strays:
        print("Nothing to rescue.")
        return 0

    plan, unclear = [], []
    for s in strays:
        label = (s.get("label") or "").strip()
        hits = by_label.get(label) or []
        said = {k: s.get(k) for k in SAID if s.get(k)}
        if len(hits) == 1:
            plan.append((s, hits[0], said))
            print("  %-42s %s" % (label, said))
            print("     -> %s" % hits[0].get("gid"))
        else:
            unclear.append((s, hits, said))
            print("  %-42s %s" % (label, said))
            print("     ? %d live recordings share that label" % len(hits))

    print("\n%d to move, %d left alone" % (len(plan), len(unclear)))
    if not apply:
        print("\nDry run. Nothing was written. Re-run with --apply to act.")
        return 0

    for stray, target, said in plan:
        # Never overwrite something already said about the real recording.
        patch = {k: v for k, v in said.items() if not target.get(k)}
        if patch:
            REG._patch(target, patch)
        REG._patch(stray, {"retired": True})
    print("\nDone. %d flag(s) moved, %d empty record(s) retired."
          % (len(plan), len(plan)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
