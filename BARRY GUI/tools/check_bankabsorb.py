# -*- coding: utf-8 -*-
"""A bank write on another machine reaches this one through the shared
database, without git (2026-10-30).

"Results banked in Panning don't show up in Lock unless a github sync is
done." A bank write elsewhere arrived as a version's metadata only: the live
events, the curated flag and the alignment mark stayed as they were here,
and a version numbered like one already here was dropped. Run against a
THROWAWAY bank in a temp folder; the real one is never opened.

    python tools/check_bankabsorb.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import cloudsync, eventbank, store as storemod  # noqa: E402

ok = bad = 0

from datetime import datetime, timedelta, timezone  # noqa: E402
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def T(hours):
    """A stamp `hours` from now, in UTC -- ahead of anything the throwaway
    bank wrote, or behind it."""
    return (NOW + timedelta(hours=hours)).isoformat()


def check(name, got, want=True):
    global ok, bad
    if got == want:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r\n        want %r" % (name, got, want))


ROOT = tempfile.mkdtemp(prefix="bankabsorb_")
try:
    STORE = storemod.Store(ROOT)
    BANK = eventbank.EventBank(ROOT, STORE)
    evs = [{"start": 1.0 + i, "label": "Spike", "label_id": "spike"}
           for i in range(4)]
    ent = BANK.add({
        "project": "HARNESS", "mouse": 98, "session": 1, "type": "pooled",
        "name": "HARNESS m98 s1 (absorb check)", "gid": "harness-absorb",
        "events": evs, "curated": False, "pipeline": "absorb harness",
        "added_by": "harness",
        "added": {"by": "harness", "at": "2026-10-30T09:00:00-04:00"},
    })
    eid = ent["id"]
    here = BANK.get(eid)
    v0 = max(v.get("v") or 0 for v in here["versions"])

    def apply(row):
        """What `_apply_bank` does for an entry this machine has."""
        rec = BANK.get(eid)
        before = cloudsync._bank_touched(rec)
        BANK.absorb_versions(eid, row.get("versions") or [], row.get("version"))
        return BANK.absorb_live(eid, row, before)

    print("A SORT BANKED ON ANOTHER MACHINE")
    sorted_evs = [dict(e, label="Garbage", label_id="garbage") if i == 2
                  else dict(e) for i, e in enumerate(evs)]
    row = {"id": eid, "updated_at": T(1),
           "events": sorted_evs, "n": 4, "specified": True,
           "by_label": {"Spike": 3, "Garbage": 1},
           "versions": [{"v": v0 + 1, "id": "vk-strawberry1",
                         "at": T(1), "by": "Rain",
                         "n": 4, "machine": "BARRYLAB",
                         "note": "Every event decided in Panning."}],
           "version": v0 + 1}
    check("it is taken on", apply(row), 1)
    rec = BANK.get(eid)
    check("the live events are the sorted ones",
          [e.get("label_id") for e in rec["events"]],
          ["spike", "spike", "garbage", "spike"])
    check("the set is curated here now", rec.get("specified"), True)
    check("the version came, under its own id",
          any(v.get("id") == "vk-strawberry1" for v in rec["versions"]), True)
    shard = [f for f in os.listdir(os.path.join(ROOT, "event_bank"))
             if f.endswith(".json")]
    stamps = json.load(open(os.path.join(ROOT, "event_bank", shard[0]),
                            encoding="utf-8")).get("_at") or {}
    check("written with the other machine's time, not now",
          str(stamps.get("events", ""))[:19], T(1)[:19])
    check("the same row again changes nothing", apply(row), 0)

    print("\nTWO MACHINES, ONE NUMBER")
    # Here: an alignment minted as the next number.
    BANK.align(eid, {0: 1.01}, {"n_channels": 4, "window_ms": 200},
               dry_run=False, by="harness")
    mine = max(BANK.get(eid)["versions"], key=lambda v: v.get("v") or 0)
    other = {"v": mine["v"], "id": "vk-strawberry2",
             "at": T(1.1), "by": "Rain", "n": 4,
             "machine": "BARRYLAB", "note": "Every event decided in Panning."}
    BANK.absorb_versions(eid, [other], mine["v"])
    same = [v for v in BANK.get(eid)["versions"] if v.get("v") == mine["v"]]
    check("both v%s are kept" % mine["v"],
          sorted(str(v.get("id")) for v in same),
          sorted([str(mine.get("id")), "vk-strawberry2"]))

    print("\nOLDER THAN WHAT IS HERE")
    old = dict(row, updated_at=T(-5),
               events=evs, specified=False)
    check("an older live set is not taken", apply(old), 0)
    check("...and the events here stand",
          BANK.get(eid)["events"][0]["start"], 1.01)

    print("\nALIGNED ELSEWHERE")
    al = dict(row, updated_at=T(2),
              aligned={"tool": "jarvis.lock/1", "version": 9},
              versions=[{"v": 9, "id": "br-elsewhere", "by": "Rain",
                         "at": T(2), "n": 4,
                         "machine": "BARRYLAB",
                         "aligned": {"tool": "jarvis.lock/1"},
                         "note": "Aligned to the mean magnitude over 4"}],
              version=9)
    check("the alignment is taken on", apply(al), 1)
    check("...with its mark", (BANK.get(eid).get("aligned") or {}).get("tool"),
          "jarvis.lock/1")
finally:
    shutil.rmtree(ROOT, ignore_errors=True)

print("\n%d ok, %d fail" % (ok, bad))
sys.exit(1 if bad else 0)
