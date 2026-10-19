# -*- coding: utf-8 -*-
"""Assert `backend/ratidentity.py` says what the lab's identity sheet says,
and that the recordings agree with it.

  1. Every cell of `RAT Identity for multisite 2026 - Sheet1.csv` equals the
     literal in ratidentity.IDENTITY, character for character.
  2. Each rat's four seats are four different sounds, one of each.
  3. Every cue type banked for a rat (from the Monolith's manifest, when
     there is one on this machine) is that rat's AB or CD -- a presentation
     with no seat would be pooled into neither side, or the wrong one.

    python tools\\check_ratidentity.py
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import ratidentity as RI                    # noqa: E402

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print("  %s  %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "   [%s]" % (detail,)))


def main():
    path = os.path.join(APP, RI.SHEET_FILE)
    if not os.path.isfile(path):
        print("The sheet is not here: " + path)
        print("Nothing was checked; that is a failure, not a skip.")
        return 1
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh) if any(x.strip() for x in r)]
    head = [x.strip() for x in rows[0]]
    check("the columns are Rat ID, A, B, C, D", head[1:5] == list(RI.SEATS), head)
    seen = {}
    for r in rows[1:]:
        rat = int(r[0].strip().lstrip("Jj"))
        seen[rat] = {s: r[1 + i].strip() for i, s in enumerate(RI.SEATS)}
    check("the same rats: %s" % ", ".join("J%d" % x for x in sorted(seen)),
          set(seen) == set(RI.IDENTITY), (sorted(seen), sorted(RI.IDENTITY)))
    diffs = [(rat, s, seen[rat][s], RI.IDENTITY[rat][s]) for rat in sorted(set(seen) & set(RI.IDENTITY))
             for s in RI.SEATS if seen[rat][s] != RI.IDENTITY[rat][s]]
    check("every cell matches the sheet", not diffs, diffs)
    bad = [rat for rat, ids in RI.IDENTITY.items() if sorted(ids.values()) != sorted(RI._KEY)]
    check("each rat hears each of the four sounds once", not bad, bad)
    check("J3: AB is Click → Low tone, CD is Noise → High tone, Cue 2 of CD is D (High tone)",
          RI.cue_type_of_pair(3, "AB") == "Click_LowTone" and RI.cue_type_of_pair(3, "CD") == "Noise_HighTone"
          and RI.seat(3, "Noise_HighTone", "cue2") == {"seats": ["D"], "sounds": ["High tone"]})
    check("a presentation is named by its seats first, the sounds after",
          RI.seat_say(3, "Click_LowTone") == "AB · A → B (Click → Low tone)"
          and RI.seat_say(3, "Noise_HighTone") == "CD · C → D (Noise → High tone)"
          and RI.seat_say(3, "Nothing_Here") is None, RI.seat_say(3, "Click_LowTone"))
    try:
        from backend import monolith as MO
        MO.configure(os.path.join(APP, "GUI_logs"))
        man = MO._read_json(MO._path("manifest.json"))
    except Exception:                                    # noqa: BLE001
        man = None
    if man:
        by = {}
        for d in man["days"]:
            by.setdefault(int(d["rat"]), set()).update(u.get("cue_type") for u in d["units"])
        wrong = []
        for rat, cts in sorted(by.items()):
            try:
                RI.check(rat, cts)
            except RI.IdentityError as exc:
                wrong.append(str(exc))
        check("every banked presentation is its rat's AB or CD (%d rats, %d sessions)"
              % (len(by), len(man["days"])), not wrong, wrong)
    else:
        print("  (no Monolith manifest on this machine: the recordings were not checked)")
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
