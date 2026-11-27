"""Audit step 4: pairs of good stamps under 1 ms apart in the pooled entries. Read only."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
sys.path.insert(0, APP)
from backend import eventbank, store as storemod  # noqa: E402

logs = os.path.join(APP, "GUI_logs")
B = eventbank.EventBank(logs, storemod.Store(logs, auto_stage=False))
IDS = {"bfa98498290b": "m1", "afa70b62f372": "m13", "41dd94702761": "m2", "edc1a5080093": "m21", "43a2cfedde17": "m22",
       "f4c18a9a8bd4": "m26", "35c325a44d44": "m28", "db66d3c694fd": "m3", "a62d1b78448b": "m33", "eaecc4a5e194": "m34",
       "b60578899091": "m5", "8aad148bd6f6": "m51", "1429bf1f239f": "m59", "cb139fb2ea29": "m6", "d4a4bcb4e47f": "m60",
       "ab69363ee622": "m61", "ece9a84acdea": "m7", "2a8e47760eea": "m8"}
GOOD = None
tot = 0
for eid, lab in IDS.items():
    rec = B.get(eid)
    names = rec.get("label_names") or {}
    ev = sorted(rec.get("events") or [], key=lambda e: float(e["start"]))
    good = [e for e in ev if str(names.get(e.get("label_id"), e.get("label")) or "").lower().startswith(("spike", "dentate"))]
    pairs = []
    for a, b in zip(good, good[1:]):
        if float(b["start"]) - float(a["start"]) < 0.001:
            pairs.append((round(float(a["start"]), 5), round((float(b["start"]) - float(a["start"])) * 1000, 3),
                          a.get("origin"), b.get("origin"), a.get("stamp"), b.get("stamp"), a.get("from_t") is not None, b.get("from_t") is not None))
    tot += len(pairs)
    print("%-4s good %4d  pairs<1ms %2d %s" % (lab, len(good), len(pairs), pairs[:2]))
print("total", tot)
