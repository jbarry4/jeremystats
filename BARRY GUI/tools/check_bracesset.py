"""
check_bracesset.py -- the review half of Braces: what a set of calls resolves
to, and the one flag that is not in the proposal.

`check_braces` covers the RULE (which peak each stamp takes) and
`check_braces_bank` covers the WRITE (what lands in the version history).
Between them sits the part a person actually touches: a proposal plus a pile
of decisions, and the question of what those decisions add up to.

The flag this exists for is `overlap`. Two stamps sent to one time are one
event written twice, which the bank refuses -- and nothing can know it until
somebody has moved something, so it cannot be measured with the others when
the set is made. It is worked out from the calls every time they are read,
which means the thing to check is not that it can be raised but that it is
raised and CLEARED by every route out of it: move one off, leave one where
it was, or decide one was never an event.

Runs against a throwaway logs directory in a temp folder. It never opens the
real sets: a check that needs somebody's afternoon of review cleared is a
check that must not be run twice.

Run it:  python -m tools.check_bracesset   (from the BARRY GUI folder)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import bracesset as brs, store as storemod           # noqa: E402

FAIL = []


def check(name, got, want, why=""):
    ok = got == want
    print("  %-4s %s" % ("ok" if ok else "FAIL", name))
    if not ok:
        print("       wanted %r" % (want,))
        print("       got    %r" % (got,))
        if why:
            print("       %s" % why)
        FAIL.append(name)


def truthy(name, got, why=""):
    ok = bool(got)
    print("  %-4s %s" % ("ok" if ok else "FAIL", name))
    if not ok:
        print("       got %r  %s" % (got, why))
        FAIL.append(name)


def row(i, was, now, flag=None, same=False, peak=0):
    """One row of a proposal, the shape `braces.propose` writes."""
    return {"i": i, "was": was, "now": now, "peak": peak,
            "peak_uv": 100.0, "same": same, "moved": not same,
            "shift_ms": round((now - was) * 1000.0, 3), "flag": flag}


ROOT = tempfile.mkdtemp(prefix="bracesset_check_")
print("\nscratch sets: %s" % ROOT)
try:
    STORE = storemod.Store(ROOT)
    SETS = brs.BracesSets(ROOT, STORE)

    # Four stamps. Two move a little, one is already right, one is flagged
    # and nobody has answered it.
    rows = [
        row(0, 1.000, 1.010),
        row(1, 2.000, 2.006),
        row(2, 3.000, 3.000, same=True),
        row(3, 4.000, 3.940, flag="contested"),
    ]
    rec = SETS.create("entry1", "gid1", None, {"window_ms": 100.0},
                      rows, {}, name="harness", by="harness")
    sid = rec["set_id"]

    print("\nWHAT A SET WITH NO DECISIONS ON IT RESOLVES TO")
    print("-" * 68)
    moves, flags, counts, rejects = brs.resolve(SETS.get(sid))
    check("an unflagged row moves on its own", moves.get(0), 1.010)
    check("...and so does its neighbour", moves.get(1), 2.006)
    check("a stamp already on its peak is not a move", 2 in moves, False)
    check("a flagged row nobody answered stays where it was",
          3 in moves, False,
          "the flag exists because the tool would not vouch for it")
    check("...and is counted as waiting", counts["waiting"], 1)
    check("...and the flag travels to the write", flags.get(3), "contested")
    check("the rest are counted as automatic", counts["auto"], 3)
    check("nothing is rejected", rejects, [])
    check("and nothing overlaps", counts["overlap"], 0)

    print("\nTHE OVERLAP FLAG")
    print("-" * 68)
    # Row 1 dragged by hand onto the time row 0 is already going to. This is
    # the gesture the bench allows -- anywhere within a window of where the
    # stamp sits -- and the one the bank will not write.
    SETS.decide(sid, {"1": {"call": "move", "t": 1.010}}, by="harness")
    rec = SETS.get(sid)
    groups = brs.overlaps(rec)
    check("two stamps on one time is one group", len(groups), 1)
    check("...naming both rows", groups and groups[0]["rows"], [0, 1])
    check("...and the time they share", groups and groups[0]["t"], 1.01)
    check("...counted in stamps, not pairs",
          brs.resolve(rec)[2]["overlap"], 2)
    check("the row that caused it is still counted as moved",
          brs.resolve(rec)[2]["moved"], 1)

    print("\n...IS RAISED BY A DECISION AND CLEARED BY ONE")
    print("-" * 68)
    # 1. move it somewhere else.
    SETS.decide(sid, {"1": {"call": "move", "t": 2.009}}, by="harness")
    check("moving one of the pair off clears it",
          brs.overlaps(SETS.get(sid)), [])
    # 2. leave it where it was.
    SETS.decide(sid, {"1": {"call": "move", "t": 1.010}}, by="harness")
    truthy("...and putting it back raises it again",
           brs.overlaps(SETS.get(sid)))
    SETS.decide(sid, {"1": {"call": "keep"}}, by="harness")
    check("leaving one of the pair alone clears it",
          brs.overlaps(SETS.get(sid)), [])
    # 3. decide it was never an event. A rejected stamp is not written, so
    #    it cannot be half of a pair.
    SETS.decide(sid, {"1": {"call": "move", "t": 1.010}}, by="harness")
    SETS.decide(sid, {"0": {"call": "garbage"}}, by="harness")
    check("a stamp called garbage cannot collide with anything",
          brs.overlaps(SETS.get(sid)), [],
          "it is not written at all, so there is nothing to collide with")
    moves, _f, counts, rejects = brs.resolve(SETS.get(sid))
    check("...and it is rejected rather than moved", rejects, [0])
    check("...and counted apart from the rest", counts["garbage"], 1)

    print("\nA CONFIRM ON A FLAGGED ROW STILL OVERLAPS")
    print("-" * 68)
    # The proposal itself can send two stamps to one time -- not through
    # the rule, which never gives one peak to two stamps, but through a
    # hand move that a later confirm lands on top of. Both halves are
    # decisions, and the flag has to see both.
    SETS.decide(sid, {"0": None, "1": None}, by="harness")
    SETS.decide(sid, {"3": {"call": "move", "t": 3.000}}, by="harness")
    groups = brs.overlaps(SETS.get(sid))
    check("a hand move onto an unanswered stamp's time is seen",
          groups and groups[0]["rows"], [2, 3],
          "row 2 is already right and never moves, which does not make it "
          "safe to land on")

    print("\nA SET NOBODY HAS TOUCHED")
    print("-" * 68)
    empty = SETS.create("entry2", "gid1", None, {}, [], {}, by="harness")
    _m, _f, counts, _r = brs.resolve(SETS.get(empty["set_id"]))
    check("resolves to nothing at all", counts["auto"], 0)
    check("...and overlaps nothing", brs.overlaps(SETS.get(empty["set_id"])),
          [])

finally:
    shutil.rmtree(ROOT, ignore_errors=True)
    print("\nscratch sets removed")

print("=" * 68)
if FAIL:
    print("%d check(s) failed:" % len(FAIL))
    for f in FAIL:
        print("  - %s" % f)
    sys.exit(1)
print("all checks passed")
