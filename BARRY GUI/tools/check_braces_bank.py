"""
check_braces_bank.py -- what an alignment writes into the version history.

This is the half of Braces that touches durable data, so it runs against a
THROWAWAY logs directory built fresh in a temp folder. It never opens the
real bank: getting a known starting state by clearing a record is how real
curation work gets deleted, and a check that needs the archive emptied is a
check that must not be run twice.

What it is actually looking for is one thing. A banked event's only identity
was its time, and `braces` changes times on purpose -- so the question is
whether the history can still tell a stamp that MOVED from a stamp that was
deleted while an unrelated one appeared. Before `from_t`, it could not: an
aligned set read back as "every event lost, every event gained".

Run it:  python -m tools.check_braces_bank   (from the BARRY GUI folder)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import eventbank, store as storemod                # noqa: E402

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


ROOT = tempfile.mkdtemp(prefix="braces_check_")
print("\nscratch bank: %s" % ROOT)
try:
    STORE = storemod.Store(ROOT)
    BANK = eventbank.EventBank(ROOT, STORE)

    # A set whose stamps are all a little early, plus the two-stamp run from
    # the design: 27.894 and 27.955 against peaks at 27.800 and 27.920.
    events = [
        {"start": 1.012, "label": "Dentate Spike", "label_id": "spike"},
        {"start": 2.021, "label": "Dentate Spike", "label_id": "spike"},
        {"start": 3.008, "label": "Garbage", "label_id": "garbage"},
        {"start": 27.894, "label": "Dentate Spike", "label_id": "spike"},
        {"start": 27.955, "label": "Dentate Spike", "label_id": "spike"},
        {"start": 40.500, "label": "Dentate Spike", "label_id": "spike"},
    ]
    entry = BANK.add({
        "project": "HARNESS", "mouse": 99, "session": 1,
        "type": "ds", "type_name": "ds",
        "name": "HARNESS m99 s1 (braces check)",
        "gid": "harness-braces-check",
        "session_key": "harness_braces-check",
        "events": events, "curated": True,
        "curation_label": "*",
        "label_names": {"spike": "Dentate Spike", "garbage": "Garbage"},
        "pipeline": "Braces harness", "added_by": "harness",
        "added": {"by": "harness", "at": "2026-09-17T09:00:00-04:00"},
    })
    eid = entry["id"]
    v_before = max(v.get("v") or 0 for v in entry["versions"])
    print("  entry %s at v%d, %d events" % (eid, v_before, entry["n"]))

    print("\nTHE DRY RUN")
    print("-" * 68)
    moves = {0: 1.000, 1: 2.000, 2: 3.000, 3: 27.800, 4: 27.920}
    params = {"n_channels": 64, "window_ms": 100.0, "band": [5, 100],
              "measure": "abs", "estimator": "sd"}
    rep = BANK.align(eid, moves, params, dry_run=True,
                     flags={3: "contested"})
    check("a dry run reports what it would move", rep["moved"], 5)
    check("...and what it would leave alone", rep["unmoved"], 1)
    check("...and names the version it would become",
          rep["next_version"], v_before + 1)
    truthy("...and carries before/after rows", rep["moves"])
    check("...and writes nothing", BANK.get(eid)["n"], 6)
    check("...leaving the entry on the version it was on",
          max(v.get("v") or 0 for v in BANK.get(eid)["versions"]), v_before)

    print("\nREFUSALS")
    print("-" * 68)
    # Two stamps onto one time is a duplicate, not an alignment.
    bad = BANK.align(eid, {0: 5.0, 1: 5.0}, params, dry_run=True)
    truthy("two stamps onto one time is refused", bad.get("error"))
    check("...and nothing was written", BANK.get(eid)["n"], 6)
    # Reordering is NOT a refusal, and it used to be one.
    #
    # The no-crossing rule holds over the peaks the tool assigns itself. It
    # says nothing about a reviewer dragging a stamp onto the peak it
    # plainly belongs on, or about one left where it was while its
    # neighbour moves past it -- both legitimate, and both used to turn an
    # afternoon of review away at the last step. So the write sorts by
    # where the stamps end up and says how many changed places.
    crossed = BANK.align(eid, {0: 9.0}, params, dry_run=True)
    check("an alignment that reorders is not refused",
          crossed.get("error"), None,
          "moving event 0 from 1.012 to 9.0 jumps it past events 1 and 2")
    check("...and says the order did not hold", crossed.get("order_held"),
          False)
    check("...and how many stamps changed places",
          crossed.get("resorted"), 3)
    truthy("...in words the panel can show", crossed.get("reordered"))
    # Nothing to do is not a version -- and not a failure either. It is
    # what a set that is already right looks like, so it comes back as an
    # outcome the panel can be calm about rather than as a red error.
    bad = BANK.align(eid, {}, params, dry_run=True)
    truthy("an alignment that moves nothing writes nothing",
           bad.get("nothing_to_do"))
    truthy("...and is not reported as an error", not bad.get("error"))

    print("\nTHE WRITE")
    print("-" * 68)
    rep = BANK.align(eid, moves, params, dry_run=False, by="harness",
                     flags={3: "contested"})
    check("no error", rep.get("error"), None)
    check("it landed as the next version", rep["version"], v_before + 1)
    rec = BANK.get(eid)
    ver = [v for v in rec["versions"] if v.get("v") == rep["version"]][0]

    check("the new version counts what shifted", ver["shifted"], 5)
    check("...and claims nothing was relabelled", ver["changed"], 0)
    check("...nothing gained", ver["gained"], 0)
    check("...nothing lost", ver["lost"], 0)
    check("...and no label moved anywhere", ver["moves"], {})
    check("it continues the version it read",
          ver["from_v"], v_before)
    truthy("it records how it was aligned", ver.get("aligned"))
    check("...over how many channels", ver["aligned"]["n_channels"], 64)
    check("...and which flags were raised",
          ver["aligned"]["flagged"], {"contested": 1})
    truthy("...with a note a person can read", ver.get("note"))
    print("       note: %s" % ver["note"])

    print("\nTHE EVENTS")
    print("-" * 68)
    by_start = {round(e["start"], 3): e for e in rec["events"]}
    check("the contested stamp moved to the former peak",
          round(by_start[27.800]["start"], 3), 27.800)
    check("...and kept the time it came from",
          round(by_start[27.800]["from_t"], 3), 27.894)
    check("...and why it was asked about",
          by_start[27.800].get("align_flag"), "contested")
    check("its neighbour took the latter peak",
          round(by_start[27.920]["from_t"], 3), 27.955)
    check("the stamp with no peak stayed exactly where it was",
          round(by_start[40.500]["start"], 3), 40.500)
    check("...and carries no from_t, because it did not move",
          "from_t" in by_start[40.500], False)
    check("every label survived untouched",
          sorted(e["label"] for e in rec["events"]),
          sorted(e["label"] for e in events))
    check("the events are still in time order",
          [e["start"] for e in rec["events"]],
          sorted(e["start"] for e in rec["events"]))

    print("\nDOING IT TWICE")
    print("-" * 68)
    # Re-running against the CURRENT events is refused before it gets as far
    # as the twin check, because they are already where it would put them.
    again = BANK.align(eid, moves, params, dry_run=True)
    # NOT an error, and it used to be reported as one. Every stamp already
    # sitting where the recording puts it is a good outcome and the common
    # one for a set looked at twice -- there is simply nothing to write.
    # The panel needs to tell that apart from a refusal so it can be calm
    # about it, which is what `nothing_to_do` is for.
    truthy("re-running over an aligned set moves nothing, and says so",
           again.get("nothing_to_do"))
    truthy("...as an outcome rather than an error", not again.get("error"))
    print("       %s" % (again.get("why") or again.get("error")))

    # The twin check is the other half: the same alignment applied to the
    # same SOURCE version. Here the stamps really would move -- v1's
    # snapshot still holds the original times -- so it gets all the way to
    # the point where a second identical version would be appended.
    br = BANK.align(eid, moves, params, dry_run=False, by="harness",
                    from_version=v_before, flags={3: "contested"})
    check("aligning an older version writes a branch off it",
          br.get("error"), None)
    check("...which records what it was worked from",
          br["from_version"], v_before)
    twin = BANK.align(eid, moves, params, dry_run=True,
                      from_version=v_before)
    truthy("the same alignment is refused a second time", twin.get("error"))
    check("...and says which version already holds it",
          twin.get("already_version"), br["version"])

    print("\nTHE DIFF CAN STILL SEE A MOVE")
    print("-" * 68)
    # THE POINT OF THE WHOLE EXERCISE. Re-bank the aligned set with one call
    # changed. Before `from_t`, the times no longer matched the previous
    # version and this read as six lost and six gained.
    recur = [dict(e) for e in rec["events"]]
    for e in recur:
        if round(e["start"], 3) == 3.000:
            e["label"], e["label_id"] = "Dentate Spike", "spike"
    re_entry = BANK.add({
        "id": eid,
        "project": "HARNESS", "mouse": 99, "session": 1,
        "type": "ds", "type_name": "ds",
        "name": "HARNESS m99 s1 (braces check)",
        "gid": "harness-braces-check",
        "session_key": "harness_braces-check",
        "events": recur, "curated": True, "curation_label": "*",
        "label_names": {"spike": "Dentate Spike", "garbage": "Garbage"},
        "pipeline": "Braces harness", "added_by": "harness",
        "added": {"by": "harness", "at": "2026-09-17T09:00:00-04:00"},
    })
    last = sorted(re_entry["versions"], key=lambda v: v.get("v") or 0)[-1]
    check("one decision changed", last["changed"], 1)
    check("nothing was gained", last["gained"], 0,
          "six gained here means the diff lost track of the moved stamps")
    check("nothing was lost", last["lost"], 0,
          "six lost here means the diff lost track of the moved stamps")
    check("and it does not claim anything shifted this time",
          last.get("shifted"), None,
          "the stamps were already where the previous version had them")
    check("the one call that changed is named",
          last["moves"], {"Garbage → Dentate Spike": 1})

    print("\nA SET WHOSE STAMPS MOVED OUTSIDE THE BANK")
    print("-" * 68)
    # The other half: a re-bank whose times moved but which carries no
    # `from_t` at all. There is nothing to match on, and it MUST read as a
    # replacement rather than quietly pairing events up by position.
    drift = [dict(e) for e in recur]
    for e in drift:
        e.pop("from_t", None)
        e["start"] = round(e["start"] + 0.5, 6)
    d_entry = BANK.add({
        "id": eid,
        "project": "HARNESS", "mouse": 99, "session": 1,
        "type": "ds", "type_name": "ds",
        "name": "HARNESS m99 s1 (braces check)",
        "gid": "harness-braces-check",
        "session_key": "harness_braces-check",
        "events": drift, "curated": True, "curation_label": "*",
        "label_names": {"spike": "Dentate Spike", "garbage": "Garbage"},
        "pipeline": "Braces harness", "added_by": "harness",
        "added": {"by": "harness", "at": "2026-09-17T09:00:00-04:00"},
    })
    last = sorted(d_entry["versions"], key=lambda v: v.get("v") or 0)[-1]
    check("times that moved with no record of it read as a replacement",
          (last["gained"], last["lost"]), (6, 6),
          "guessing they are the same events would be inventing a fact")

    print("\nTWO VERSIONS WITH THE SAME NUMBER")
    print("-" * 68)
    # Real data. Two machines curating one entry both mint the next number
    # and the union keeps both, so this bank holds a history numbered
    # 0,1,2,3,4,3,4. Asking for "3" is then an ambiguous question, and
    # answering it by taking whichever came first in the file would read one
    # person's pass while naming the other's.
    twin_rec = BANK.get(eid)
    vs = sorted(twin_rec["versions"], key=lambda v: v.get("v") or 0)
    clash = dict(vs[-1])
    clash["id"] = "clash-" + clash["id"][:8]
    clash["by"] = "somebody else"
    clash["note"] = "the same number, minted on another machine"
    twin_rec["versions"] = list(twin_rec["versions"]) + [clash]
    BANK.book.write(BANK._base_of(twin_rec), twin_rec)
    BANK._drop_cache()

    n = clash["v"]
    got = BANK.get(eid)
    check("the bank really does hold two versions numbered %s" % n,
          len([v for v in got["versions"] if (v.get("v") or 0) == n]), 2)
    keys = [BANK.version_key(v) for v in got["versions"]
            if (v.get("v") or 0) == n]
    try:
        BANK.events_at(got, n)
        ok, why = False, "it answered instead of refusing"
    except eventbank.BankError as exc:
        # It must not only refuse -- it must hand back the handles to choose
        # between, or the refusal is a dead end.
        ok = all(k in str(exc) for k in keys)
        why = str(exc)
    check("asking by that number is refused rather than guessed", ok, True,
          "picking one silently reads a pass somebody else made\n       "
          + why)
    check("...and every version that number could mean is named",
          len(keys), 2)
    evs, _d = BANK.events_at(got, clash["id"])
    check("asking by id is exact", len(evs), clash["n"])
    # Raised rather than returned as a report: an ambiguous version is bad
    # input, like an entry id that does not exist, and the report's `error`
    # field is for the refusals that come AFTER the work was worked out.
    # The route turns either into a 400 carrying the same sentence.
    try:
        BANK.align(eid, {0: 1.5}, params, dry_run=True, from_version=n)
        aimed = False
    except eventbank.BankError:
        aimed = True
    check("and an alignment cannot be aimed at an ambiguous number",
          aimed, True)

    print("\nAN ALIGNMENT ARRIVING THROUGH A RE-BANK")
    print("-" * 68)
    # The path that `from_t` actually exists for, and the one every check
    # above misses: the bank is NOT aligned, the open Checkup set is, and
    # the set is banked on top of it. The incoming times all differ from the
    # stored ones, so the first pass matches nothing and the whole set goes
    # to the second pass. Before this, that read as a total replacement.
    base = [
        {"start": 10.000, "label": "Dentate Spike", "label_id": "spike"},
        {"start": 20.000, "label": "Dentate Spike", "label_id": "spike"},
        {"start": 30.000, "label": "Garbage", "label_id": "garbage"},
    ]
    common = {
        "project": "HARNESS", "mouse": 99, "session": 2,
        "type": "ds", "type_name": "ds",
        "name": "HARNESS m99 s2 (rebank check)",
        "gid": "harness-rebank-check",
        "session_key": "harness_rebank-check",
        "curated": True, "curation_label": "*",
        "label_names": {"spike": "Dentate Spike", "garbage": "Garbage"},
        "pipeline": "Braces harness", "added_by": "harness",
        "added": {"by": "harness", "at": "2026-09-17T09:00:00-04:00"},
    }
    first = BANK.add(dict(common, events=base))
    eid2 = first["id"]

    shifted_in = [
        {"start": 9.988, "from_t": 10.000,
         "label": "Dentate Spike", "label_id": "spike"},
        {"start": 20.014, "from_t": 20.000,
         "label": "Dentate Spike", "label_id": "spike"},
        # This one also had its call changed, so the pass has to report the
        # move AND the relabel -- they are different facts about one event.
        {"start": 29.991, "from_t": 30.000,
         "label": "Dentate Spike", "label_id": "spike"},
    ]
    second = BANK.add(dict(common, id=eid2, events=shifted_in))
    last = sorted(second["versions"], key=lambda v: v.get("v") or 0)[-1]
    check("every stamp is recognised as having moved", last.get("shifted"), 3)
    check("...so nothing reads as gained", last["gained"], 0,
          "3 gained here is the bug from_t exists to prevent")
    check("...and nothing reads as lost", last["lost"], 0)
    check("...while the one call that changed is still reported",
          last["moves"], {"Garbage → Dentate Spike": 1})
    check("...and counted", last["changed"], 1)
    kept = {round(e["start"], 3): e.get("from_t")
            for e in second["events"]}
    check("the previous time survives the whitelist in add()",
          kept.get(9.988), 10.0,
          "add() builds each event from a field list -- from_t has to be on "
          "it or the next diff is blind again")

finally:
    shutil.rmtree(ROOT, ignore_errors=True)
    print("\nscratch bank removed")

print("=" * 68)
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("all checks passed")
