"""Phase 1: put Lock's alignment of PTEN m1 s2 (Confluence entry bfa98498290b)
back on top. Replays the committed Lock pass br1f1b0830ec -- its own moves,
by index, with its own params -- onto the live events (v3, identical to the
v1 it was made from), as a new aligned version. Dry run unless --apply."""
import os
import sys

import numpy as np

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
sys.path.insert(0, APP)
from backend import eventbank, store as storemod, bracesset as brsetmod, curation  # noqa: E402

APPLY = "--apply" in sys.argv
logs = os.path.join(APP, "GUI_logs")
STORE = storemod.Store(logs, auto_stage=False)
B = eventbank.EventBank(logs, STORE)
BR = brsetmod.BracesSets(logs, STORE)
EID, SET = "bfa98498290b", "br1f1b0830ec"

rec = B.get(EID)
lock = BR.get(SET)
assert lock and lock["entry_id"] == EID, "no Lock set"
print("Lock set from_version", lock["from_version"], "committed", lock.get("committed"))

# 1. The live events must be v1 event for event, so the indices mean the same.
v1, _ = B.events_at(rec, lock["from_version"])
live = rec.get("events") or []
same = len(v1) == len(live) and all(abs(float(a["start"]) - float(b["start"])) < 1e-9 and
                                    (a.get("label_id") or a.get("label")) == (b.get("label_id") or b.get("label"))
                                    for a, b in zip(v1, live))
print("live == v1 event for event:", same, len(v1), len(live))
assert same

moves, flags, counts, rejects = brsetmod.resolve(lock)
print("moves", len(moves), "counts", counts, "rejects", len(rejects or {}))

entry = rec
goods = [lab for lab in (curation.KINDS.get(entry.get("type") or "ds") or curation.KINDS["ds"])["labels"] if lab.get("good")]
keep_ids = {lab["id"] for lab in goods} | {lab["name"] for lab in goods}
for lid, name in (entry.get("label_names") or {}).items():
    if lid in keep_ids:
        keep_ids.add(name)

note = ("Lock's alignment put back (2026-11-19): pass %s, committed as v2 on 2026-10-23, replayed onto v3. "
        "v3 (\"Banked on leaving Panning\", 6 minutes after Lock) had returned every stamp to its v1 time." % SET)
rep = B.align(EID, moves, lock.get("params") or {}, note=note, by="Shahriar Tafti", dry_run=not APPLY,
              from_version=None, flags=flags, keep_ids=keep_ids, reject=rejects)
print({k: v for k, v in rep.items() if k not in ("events", "preview", "rows")})

# 2. Check: the result's spike times against Lock's v2.
rec = B.get(EID)
v2 = [v for v in rec["versions"] if v.get("id") == "br-c14cd1ea1c"][0]
want = np.array(sorted(float(x[0]) for x in v2["snap"] if len(x) > 1 and x[1] in ("spike", "Spike")))
if APPLY:
    got = np.array(sorted(float(e["start"]) for e in rec["events"] if (e.get("label_id") or "") == "spike"))
    print("newest version", rec.get("version"), "aligned", bool(rec.get("aligned")))
else:
    got = np.array(sorted(float(e["start"]) for e in (rep.get("events") or [])
                          if (e.get("label_id") or "") == "spike")) if rep.get("events") else None
if got is not None and len(got):
    print("spikes", len(got), "equal to Lock v2:", len(got) == len(want) and bool(np.allclose(got, want, atol=1e-6)),
          "max diff ms", float(np.max(np.abs(got - want))) * 1000 if len(got) == len(want) else None)
