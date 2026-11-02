"""Checks for backend/dayreport.py, the end-of-day error report.

    python tools/test_dayreport.py

Fed made-up records, so it never reads or writes GUI_logs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import dayreport as D  # noqa: E402
from backend import extras  # noqa: E402

bad = 0


def ok(name, cond, said=None):
    global bad
    if not cond:
        bad += 1
    print(("ok    " if cond else "FAIL  ") + name
          + ("" if cond or said is None else "   [%s]" % said))


DAY = "2026-10-21"
T = lambda hms: "%sT%s-04:00" % (DAY, hms)  # noqa: E731

errors = [
    {"at": T("10:00:00"), "where": "api.curation.bank", "message":
     "KeyError: 'events'", "detail": "Traceback (most recent call last):"
     "\n  File \"app.py\", line 1, in x\nKeyError: 'events'",
     "context": {"gid": "s123", "kind": "ds"}, "user": "Rain"},
    {"at": T("10:05:00"), "where": "api.curation.bank",
     "message": "KeyError: 'events'", "user": "Rain"},
    {"at": T("14:30:00"), "where": "client", "message":
     "TypeError: x is undefined", "detail": "at render (toolkit.js:12)"},
]
activity = [
    {"at": T("09:56:00"), "action": "view.open", "view": "toolkit"},
    {"at": T("09:59:30"), "action": "set.pickup",
     "detail": {"gid": "s123"}, "session": {"key": "pten_m2_s3"}},
    {"at": T("10:00:20"), "action": "bank.try"},
    {"at": T("10:30:00"), "action": "far.away"},
    {"at": "2026-10-20T23:59:00-04:00", "action": "yesterday"},
]

text = D.build(DAY, errors, activity, extras.signature, machine="Bluebarry (x)",
               user="Rain", build_id="2026.10.21 abc1234", tests_left_out=4,
               generated="fixed")
print(text)
ok("headed with the day and computer", DAY in text and "Bluebarry" in text)
ok("says the build", "abc1234" in text)
ok("counts and distinct", "3 error(s), 2 distinct" in text, text[:400])
ok("says tests left out", "4 test fault(s)" in text)
ok("the repeated fault is one group x2", "api.curation.bank  x2" in text)
ok("full traceback kept", "KeyError: 'events'" in text and 'File "app.py"' in text)
ok("context printed", "gid" in text and "s123" in text)
ok("activity before the error, in seconds", "-30.0s" in text
   and "set.pickup" in text, None)
ok("the error marked in its place", ">>> api.curation.bank" in text)
ok("activity after the error", "+20.0s" in text and "bank.try" in text)
ok("nothing outside the window", "far.away" not in text)
ok("no context said plainly for the client fault",
   "nothing in this computer's activity log" in text)
ok("recording key on the line", "rec=pten_m2_s3" in text)
ok("no ellipsis anywhere", "..." not in text and "…" not in text)

empty = D.build(DAY, [], activity, extras.signature, machine="m")
ok("an empty day says so", "No errors on this computer today." in empty)

ok("due: not today before six", not D.due(DAY, DAY, 17, None, "1|x"))
ok("due: today after six", D.due(DAY, DAY, 18, None, "1|x"))
ok("due: not when unchanged", not D.due(DAY, DAY, 20, "1|x", "1|x"))
ok("due: yesterday when out of date", D.due("2026-10-20", DAY, 8, "1|a", "2|b"))
ok("due: never tomorrow", not D.due("2026-10-22", DAY, 23, None, "1|x"))
ok("stamp changes with a new error",
   D.stamp_of(errors[:2]) != D.stamp_of(errors))
ok("path per computer per day",
   D.path_for("R", DAY, "bluebarry-x").endswith("2026-10-21@bluebarry-x.txt"))

print("\n%s" % ("All good." if not bad else "%d FAILED" % bad))
sys.exit(1 if bad else 0)
