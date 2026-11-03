# -*- coding: utf-8 -*-
"""Import the bad contacts from the Toothy bad-channel workbook.

    python tools/import_bad_channels.py            # say what would change
    python tools/import_bad_channels.py --apply

A companion to import_toothy.py rather than part of it: this is a different
file with one sheet in it -- `Recording Sessions`, holding mouse_id, session
and the contacts not to believe -- and the reference channels that tool
imports come from the other workbook. Two files, two readers, so a change to
either is a change to one of them.

WHAT A BAD CHANNEL IS HERE
    A CSC NUMBER, not a row index. Jarvis interpolates these from their
    neighbours rather than dropping them, because a current source density is
    a second difference across depth and taking a contact out of the middle
    leaves the rest unevenly spaced -- which is not a CSD. So the list is
    "which wires are not believed", and it is read by Braces, Incisor and
    every panel that renders a CSD.

    Channel 59 is in all 62 rows. The others -- 8, 25, 41, 47, 55, 57 -- are
    per-mouse, and five mice change between their own two sessions (m3, m5,
    m6, m8, m13), so this is keyed on the pair and not on the animal.

WHICH RECORDING A ROW MEANS
    Mouse plus session is not an identity in this lab: the numbering restarts
    per project, so PTEN m13 s2 and KCNT1 m13 s2 are two recordings with one
    loose key, and nine of these 62 rows collide that way. Matching on the
    pair alone picks whichever was read first, which is how a PTEN workbook
    ends up writing to a KCNT1 recording.

    So a row is resolved by the pair, then narrowed: retired records are not
    candidates, and where more than one survives, the PTEN cohort wins --
    this is the PTEN workbook. Anything still ambiguous is skipped and named,
    because the alternative is guessing in the direction of silence.

WHAT IT WRITES, AND WHAT IT LEAVES
    The workbook is the authority for the sessions it names, so a row that
    disagrees is set to the workbook's list. Both directions: a contact the
    workbook does not list is removed, which is the half worth saying out
    loud because it marks a channel believable again.

    Nothing is written for a session the workbook does not mention. A sheet
    of 62 rows is not a statement about the other 526 recordings Jarvis
    knows, and reading it as one would clear every channel anybody has
    marked by hand in the trace view.
"""
import argparse
import collections
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl                                          # noqa: E402

# Next to the app rather than in it: the file arrives from the lab share and
# is not the app's to keep. Both places are tried so it can be either.
WORKBOOK = "PTEN Toothy Data all bad channels.xlsx"
SHEET = "Recording Sessions"

# What the record says about where its list came from. The same words the 59
# rows already carrying one use -- a store where half the records name the
# file and half name the workbook reads as two sources when it is one.
NOTE = "Bad channels from the Toothy workbook."

# The cohorts this workbook is about, in the order they win a tie.
PTEN_GROUPS = ("PTEN", "PTEN_DKO")

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def say(msg=""):
    OUT.write(msg + "\n")
    OUT.flush()


def clean(v):
    v = "" if v is None else str(v).strip()
    return "" if v.lower() in ("", "none", "nan", "n/a", "#n/a") else v


def mouse_of(v):
    """`m47` -> 47. The column is text; the number is what identifies."""
    m = re.search(r"(\d+)", clean(v))
    return int(m.group(1)) if m else None


def session_of(v):
    m = re.search(r"(\d+)", clean(v))
    return int(m.group(1)) if m else None


def channels_of(v):
    """The CSC numbers in a cell.

    Excel stores `59` as a number and `8,41,59` as text, and the text has no
    fixed spacing -- `8, 41,59` and `8,41, 59` are both in this sheet. Split
    on anything that is not a digit and the three cases become one.
    """
    return sorted({int(n) for n in re.findall(r"\d+", clean(v))})


def open_book(path):
    if not os.path.exists(path):
        say("Cannot find %s" % path)
        say("Looked relative to %s -- pass --file to say where it is."
            % os.getcwd())
        sys.exit(1)
    return openpyxl.load_workbook(path, read_only=True, data_only=True)


def read_sheet(wb, name):
    if name not in wb.sheetnames:
        say("No sheet called %r. This workbook has: %s"
            % (name, ", ".join(wb.sheetnames)))
        sys.exit(1)
    got = list(wb[name].iter_rows(values_only=True))
    if not got:
        return {}, []
    head = [clean(c) for c in got[0]]
    return ({h: i for i, h in enumerate(head) if h},
            [r for r in got[1:] if any(clean(c) for c in r)])


def barry_index(store):
    by = collections.defaultdict(list)
    for s in store.all_sessions():
        try:
            by[(int(s.get("mouse")), int(s.get("session")))].append(s)
        except (TypeError, ValueError):
            continue
    return by


def resolve(recs):
    """Which of these recordings the workbook means.

    Returns (record, why) or (None, why-not). See the header: the pair is not
    an identity, so this narrows rather than picks.
    """
    live = [r for r in recs if not r.get("retired")]
    if not live:
        return None, "every recording Jarvis has for this pair is retired"
    if len(live) == 1:
        return live[0], "the only one"
    pten = [r for r in live if (r.get("group") or "") in PTEN_GROUPS]
    if len(pten) == 1:
        others = [(r.get("label") or r.get("key")) for r in live
                  if r not in pten]
        return pten[0], "the PTEN one; also here: " + ", ".join(others)
    return None, ("%d recordings share this mouse and session and none of "
                  "them is the only PTEN one: %s"
                  % (len(live), ", ".join((r.get("label") or r.get("key") or "?")
                                          for r in live)))


def do_bad(store, index, wb, apply_it):
    idx, body = read_sheet(wb, SHEET)
    for col in ("mouse_id", "session", "bad channel"):
        if col not in idx:
            say("The sheet has no %r column. It has: %s"
                % (col, ", ".join(sorted(idx))))
            sys.exit(1)

    say("\n" + "=" * 70)
    say("BAD CHANNELS  (contacts to interpolate)")
    say("=" * 70)

    same = changed = added = skipped = 0
    for r in body:
        mouse = mouse_of(r[idx["mouse_id"]])
        session = session_of(r[idx["session"]])
        want = channels_of(r[idx["bad channel"]])
        if mouse is None or session is None:
            say("  SKIPPED: a row with no mouse or session: %r" % (r,))
            skipped += 1
            continue

        recs = index.get((mouse, session)) or []
        if not recs:
            say("  m%-3d s%-3d  SKIPPED: Jarvis has no recording for this pair"
                % (mouse, session))
            skipped += 1
            continue
        rec, why = resolve(recs)
        if rec is None:
            say("  m%-3d s%-3d  SKIPPED: %s" % (mouse, session, why))
            skipped += 1
            continue

        got = sorted({int(b) for b in (rec.get("bad_channels") or [])})
        if got == want:
            same += 1
            continue

        # Said as a difference rather than as a new value: "8,25,41,59"
        # against "8,24,25,41,59" is two lists to compare by eye, and
        # "-CSC24" is the sentence.
        gone = [b for b in got if b not in want]
        new = [b for b in want if b not in got]
        bits = " ".join(["+CSC%d" % b for b in new]
                        + ["-CSC%d" % b for b in gone])
        say("  m%-3d s%-3d  %-22s  %s -> %s"
            % (mouse, session, bits, got or "nothing", want or "nothing"))
        if len(recs) > 1:
            say("            (%s)" % why)
        if got:
            changed += 1
        else:
            added += 1

        if apply_it:
            store.set_bad_channels(
                {"gid": rec.get("gid"), "key": rec.get("key"),
                 "loose_key": rec.get("loose_key"),
                 "mouse": mouse, "session": session,
                 "label": rec.get("label")},
                want, note=NOTE)

    say("\n  newly set %d   changed %d   already agree %d   skipped %d"
        % (added, changed, same, skipped))
    say("  (%d rows in the sheet)" % len(body))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without it, only reports.")
    ap.add_argument("--file", default=None,
                    help="where the workbook is, if it is not beside the app "
                         "or in it")
    args = ap.parse_args()

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tries = ([args.file] if args.file else
             [os.path.join(here, WORKBOOK),
              os.path.join(os.path.dirname(here), WORKBOOK),
              WORKBOOK])
    path = next((p for p in tries if p and os.path.exists(p)), tries[0])

    import backend.app as A

    wb = open_book(path)
    index = barry_index(A.STORE)
    say("Reading %s" % path)
    say("  sheets: %s" % ", ".join(wb.sheetnames))
    say("  Jarvis (mouse, session) keys: %d" % len(index))

    if not args.apply:
        say("\n*** DRY RUN -- nothing will be written. Add --apply to do it.")
    do_bad(A.STORE, index, wb, args.apply)
    say("\n" + ("Applied." if args.apply
                else "Nothing was written. Re-run with --apply."))
    wb.close()


if __name__ == "__main__":
    main()
