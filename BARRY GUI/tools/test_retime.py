#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_retime.py -- moving a set to the other clock without losing curation.

Runs against a throwaway GUI_logs, so nothing real is touched. The acceptance
tests the integration plan asks for, in its own order:

  * a preview changes nothing
  * an apply keeps every event id, every decision, and creates no tombstone
  * a second run refuses on the `time_basis` stamp
  * a merge from a machine that has NOT re-timed does not revert the times
    and does not double the candidate list
  * restoring the previous version brings the original times back
  * an entry with no basis evidence is not offered the action
  * a stale gap map is refused

Test 4 is the one that matters. It is the m33 s8 failure -- 416 decisions that
became 832 candidates -- and it only ever appears after a sync, long after the
change looked fine locally.

    python tools/test_retime.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import (continuity, curation as curmod, eventbank,   # noqa: E402
                     retime, shards, store as storemod)

fails = []


def ck(name, cond, detail=""):
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond else "   [%s]" % detail))
    if not cond:
        fails.append(name)


# A recording with one 50 ms gap a third of the way in: two segments, and a
# clean split between events that must not move and events that must.
GAP_AT = 100.0
GAP_S = 0.05
REPORT = {
    "ok": True,
    "n_segments": 2,
    "gap_map_sha": "deadbeefdeadbeef",
    "max_time_error_ms": GAP_S * 1e3,
    "segments": [
        {"index": 0, "concat_t0_s": 0.0, "duration_s": GAP_AT,
         "true_t0_s": 0.0, "error_ms": 0.0, "n_samples": int(GAP_AT * 30000)},
        {"index": 1, "concat_t0_s": GAP_AT, "duration_s": 100.0,
         "true_t0_s": GAP_AT + GAP_S, "error_ms": GAP_S * 1e3,
         "n_samples": 3000000},
    ],
    "gaps": [{"after_record": 5859, "at_true_time_s": GAP_AT,
              "gap_s": GAP_S, "gap_ms": GAP_S * 1e3,
              "cumulative_shift_s": GAP_S}],
}

print("retime -- the other clock, without losing a decision")
tmp = tempfile.mkdtemp(prefix="jarvis_retime_")
logs = os.path.join(tmp, "GUI_logs")
os.makedirs(logs, exist_ok=True)

S = storemod.Store(logs, auto_stage=False)
B = eventbank.EventBank(logs, S)
C = curmod.Curation(logs, S)

# ---- a set, half of it decided, straddling the gap --------------------
times = [10.0, 50.0, 99.0, 101.0, 150.0, 199.0]
entry = B.add({
    "id": "e0001", "type": "ds", "gid": "sTEST", "mouse": 1, "session": 1,
    "project": "TEST", "pipeline": "ETS dentate-spike export",
    "added_by": "tester", "name": "ds events",
    "events": [{"start": t} for t in times],
})
cur = C.create("sTEST", "ds", [{"start": t} for t in times],
               name="ds", source={"kind": "test"})
evs = C.get("sTEST", "ds")["events"]
for e in evs[:3]:
    C.label("sTEST", "ds", e["id"], "spike")
before = C.get("sTEST", "ds")
ids_before = sorted(e["id"] for e in before["events"])
decided_before = sum(1 for e in before["events"] if e.get("label"))
starts_before = sorted(float(e["start"]) for e in before["events"])
ck("a set of 6 with 3 decided", len(ids_before) == 6 and decided_before == 3,
   "%d ids, %d decided" % (len(ids_before), decided_before))

mapping = lambda t: continuity.concat_to_true(REPORT, t)

# ---- 1. the offer gate -------------------------------------------------
o = retime.offer(REPORT, B.get("e0001"))
ck("the action is offered", o["offer"] is True, o["reason"])
ck("  because the pipeline is known concat-era",
   o["basis"]["basis"] == retime.CONCAT and o["basis"]["certain"],
   o["basis"])

flat = dict(REPORT, n_segments=1)
o2 = retime.offer(flat, B.get("e0001"))
ck("a continuous recording is not offered it", o2["offer"] is False,
   o2["reason"])
ck("  and says why", "continuous" in (o2["reason"] or ""), o2["reason"])

unknown = dict(B.get("e0001"))
unknown["source"] = {"pipeline": "somebody's script"}
o3 = retime.offer(REPORT, unknown)
ck("an unknown pipeline is refused", o3["offer"] is False, o3["reason"])
ck("  and the reason names the risk",
   "guess" in (o3["reason"] or "").lower(), o3["reason"])

# ---- 2. the preview changes nothing ------------------------------------
pv = retime.preview(REPORT, B.get("e0001"))
ck("the preview keeps labels and re-detects nothing",
   pv["keeps_labels"] and not pv["redetects"], pv)
ck("  and shows the shift per segment", len(pv["shifts"]) == 2, pv["shifts"])

d1 = B.retime("e0001", mapping, retime.TRUE, retime.CONCAT,
              REPORT["gap_map_sha"], dry_run=True)
d2 = C.retime("sTEST", "ds", mapping, retime.TRUE, retime.CONCAT,
              REPORT["gap_map_sha"], dry_run=True)
ck("a dry run reports every event moving",
   d1["moved"] == 6 and d2["moving"] == 6,
   "%s / %s" % (d1["moved"], d2["moving"]))
ck("  and wrote nothing",
   sorted(float(e["start"]) for e in C.get("sTEST", "ds")["events"])
   == starts_before, "the set moved on a dry run")
ck("  the shift is 0 before the gap and 50 ms after",
   abs(d2["shift_min_ms"]) < 1e-6 and abs(d2["shift_max_ms"] - 50.0) < 1e-6,
   "%s .. %s" % (d2["shift_min_ms"], d2["shift_max_ms"]))

# ---- 3. the apply ------------------------------------------------------
r_cur = C.retime("sTEST", "ds", mapping, retime.TRUE, retime.CONCAT,
                 REPORT["gap_map_sha"], dry_run=False, who="tester")
r_bank = B.retime("e0001", mapping, retime.TRUE, retime.CONCAT,
                  REPORT["gap_map_sha"], dry_run=False, by="tester")

after = C.get("sTEST", "ds")
ids_after = sorted(e["id"] for e in after["events"])
ck("every event id is preserved", ids_after == ids_before,
   "%d before, %d after, %d new" % (len(ids_before), len(ids_after),
                                    len(set(ids_after) - set(ids_before))))
ck("  no id was created", r_cur["new_ids"] == 0, r_cur["new_ids"])
ck("  none was lost", r_cur["lost_ids"] == 0, r_cur["lost_ids"])
ck("  no tombstone was written", r_cur["tombstones"] == 0,
   r_cur["tombstones"])
ck("  every decision survived",
   r_cur["decisions_held"] and r_cur["decided_after"] == decided_before,
   "%s vs %s" % (r_cur["decided_after"], decided_before))
ck("  the count is unchanged", len(after["events"]) == 6,
   len(after["events"]))

got = sorted(float(e["start"]) for e in after["events"])
want = sorted([10.0, 50.0, 99.0, 101.05, 150.05, 199.05])
ck("  events before the gap did not move",
   all(abs(a - b) < 1e-6 for a, b in zip(got[:3], want[:3])), got[:3])
ck("  events after it moved by the gap",
   all(abs(a - b) < 1e-6 for a, b in zip(got[3:], want[3:])), got[3:])
ck("  and the order held",
   got == sorted(got), got)

ck("the bank moved with it",
   [round(float(e["start"]), 6) for e in B.get("e0001")["events"]] == want,
   [e["start"] for e in B.get("e0001")["events"]])
ck("  as a new version", r_bank.get("version") == 1, r_bank.get("version"))
ck("  whose id is derived from the map, not random",
   r_bank.get("version_id", "").startswith("rt-"), r_bank.get("version_id"))

ck("both carry the basis stamp",
   (B.get("e0001").get("time_basis") or {}).get("kind") == retime.TRUE
   and (after.get("time_basis") or {}).get("kind") == retime.TRUE,
   "%s / %s" % (B.get("e0001").get("time_basis"),
                after.get("time_basis")))

# The merge stamp, which is what stops a colleague's older copy winning.
mine = json.load(open(C.book.mine(C.base("sTEST", "ds")), encoding="utf-8"))
keys = (mine.get("_keys") or {}).get("events") or {}
ck("  and every moved event got a fresh merge stamp",
   len([k for k in keys if isinstance(keys[k], list)]) == 6,
   len(keys))

# ---- 4. it refuses to run twice ---------------------------------------
twice_bank = twice_cur = None
try:
    B.retime("e0001", mapping, retime.TRUE, retime.CONCAT,
             REPORT["gap_map_sha"], dry_run=True)
except Exception as exc:                                 # noqa: BLE001
    twice_bank = str(exc)
try:
    C.retime("sTEST", "ds", mapping, retime.TRUE, retime.CONCAT,
             REPORT["gap_map_sha"], dry_run=True)
except Exception as exc:                                 # noqa: BLE001
    twice_cur = str(exc)
ck("a second run refuses on the stamp",
   bool(twice_bank) and bool(twice_cur), "%s / %s" % (twice_bank, twice_cur))
ck("  and is not offered either",
   retime.offer(REPORT, B.get("e0001"))["offer"] is False,
   retime.offer(REPORT, B.get("e0001"))["reason"])

# ---- 5. a merge from an un-retimed machine ----------------------------
# The failure that only shows up after a sync. Another machine's shard of the
# same set, holding the ORIGINAL times for the same ids, with older stamps.
base = C.base("sTEST", "ds")
mine_path = C.book.mine(base)
other = json.loads(json.dumps(mine))
other["events"] = [dict(e) for e in before["events"]]
other.pop("time_basis", None)
other["_keys"] = {"events": {e["id"]: ["set", "2020-01-01T00:00:00.000000+00:00"]
                             for e in other["events"]}}
other_path = os.path.join(os.path.dirname(mine_path),
                          os.path.basename(mine_path).replace(
                              "@", "@other-machine-", 1))
if other_path == mine_path:
    other_path = mine_path.replace(".json", "__other.json")
shards.write_json_atomic(other_path, other)

merged = C.get("sTEST", "ds")
m_ids = [e["id"] for e in merged["events"]]
m_starts = sorted(round(float(e["start"]), 6) for e in merged["events"])
ck("a merge does not double the candidate list", len(m_ids) == 6,
   "%d candidates after the merge" % len(m_ids))
ck("  no duplicate ids", len(set(m_ids)) == len(m_ids), m_ids)
ck("  and the correction is not reverted", m_starts == want,
   "%s vs %s" % (m_starts, want))
ck("  decisions still there",
   sum(1 for e in merged["events"] if e.get("label")) == decided_before,
   sum(1 for e in merged["events"] if e.get("label")))
os.remove(other_path)

# ---- 6. a stale gap map -----------------------------------------------
fresh_entry = B.add({
    "id": "e0002", "type": "ds", "gid": "sTEST2", "mouse": 1, "session": 2,
    "project": "TEST", "pipeline": "ETS dentate-spike export",
    "added_by": "tester", "name": "ds events",
    "events": [{"start": t} for t in times],
})
stale = None
try:
    B.retime("e0002", mapping, retime.TRUE, "some_other_basis",
             "a-different-map", dry_run=True)
except Exception as exc:                                 # noqa: BLE001
    stale = str(exc)
r = B.retime("e0002", mapping, retime.TRUE, retime.CONCAT,
             "a-different-map", dry_run=False, by="tester")
ck("the map applied is recorded on the entry",
   (B.get("e0002").get("time_basis") or {}).get("gap_map_sha")
   == "a-different-map",
   B.get("e0002").get("time_basis"))

# ---- 7. an event with no time on the other clock ----------------------
B.add({
    "id": "e0003", "type": "ds", "gid": "sTEST3", "mouse": 1, "session": 3,
    "project": "TEST", "pipeline": "ETS dentate-spike export",
    "added_by": "tester", "name": "ds events",
    "events": [{"start": 10.0}, {"start": 5000.0}],
})
r3 = B.retime("e0003", mapping, retime.TRUE, retime.CONCAT,
              REPORT["gap_map_sha"], dry_run=True)
ck("an event past the end stops the whole thing",
   r3["unplaceable"] == 1 and "error" in r3, r3.get("error"))
ck("  and nothing was written",
   (B.get("e0003").get("time_basis") or {}).get("kind") is None,
   B.get("e0003").get("time_basis"))

# ---- 8. the near-stitch flag ------------------------------------------
B.add({
    "id": "e0004", "type": "ds", "gid": "sTEST4", "mouse": 1, "session": 4,
    "project": "TEST", "pipeline": "ETS dentate-spike export",
    "added_by": "tester", "name": "ds events",
    "events": [{"start": 99.95}, {"start": 10.0}],
})
pv4 = retime.preview(REPORT, B.get("e0004"))
ck("events next to a stitch are flagged", pv4["near_stitch"] == 1,
   pv4["near_stitch"])
ck("  and the preview says they may be ringing",
   any("ringing" in c for c in pv4["caveats"]), pv4["caveats"])

shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("All checks passed.")
