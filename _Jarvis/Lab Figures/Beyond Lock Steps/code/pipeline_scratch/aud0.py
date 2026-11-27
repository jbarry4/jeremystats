"""Audit probe: what bank entries does one recording have, and their versions. Read only."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
sys.path.insert(0, APP)
from backend import eventbank, store as storemod  # noqa: E402

logs = os.path.join(APP, "GUI_logs")
B = eventbank.EventBank(logs, storemod.Store(logs, auto_stage=False))
want = sys.argv[1] if len(sys.argv) > 1 else "m51"
for r in B.all():
    lab = str(r.get("session_label") or "")
    if want not in lab:
        continue
    print("=" * 100)
    print(r.get("id"), r.get("type"), "|", lab, "| gid", r.get("gid"), "| n", len(r.get("events") or []),
          "| aligned", r.get("aligned"), "| archived", eventbank.entry_archived(r))
    print("   keys:", sorted(k for k in r.keys() if k not in ("events", "versions", "history")))
    for v in sorted(r.get("versions") or [], key=lambda v: (v.get("v") or 0, str(v.get("at")))):
        print("   v%-4s id %-14s at %-26s by %-18s n %-5s al %-5s pipe %s | %s" % (
            v.get("v"), v.get("id"), v.get("at"), (v.get("by") or {}).get("user") if isinstance(v.get("by"), dict) else v.get("by"),
            v.get("n") if v.get("n") is not None else len(v.get("snap") or []),
            bool(v.get("aligned")), v.get("pipeline") or (v.get("source") or {}).get("pipeline") if isinstance(v.get("source"), dict) else v.get("pipeline"),
            str(v.get("note") or "")[:70]))
