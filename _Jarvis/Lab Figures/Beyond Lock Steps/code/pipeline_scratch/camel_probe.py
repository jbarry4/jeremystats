"""What a read holds, for m6 s4 in the room's v3/v4."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
import numpy as np  # noqa: E402

room = A._er_rooms().get("dentate_spike")
aid = room["id"]
for v in (3, 4):
    pay = A.ARTIFACTS.payload(aid, v)
    print("v%d" % v, (pay.get("source") or {}).get("folder_name"))
    for r in pay["recordings"]:
        print("   ", r["session_label"], r["gid"], r.get("read"), r.get("group"), r["n"],
              (r.get("box") or {}).get("sel_lo"), (r.get("box") or {}).get("sel_hi"), r.get("bad"))
pay = A.ARTIFACTS.payload(aid, 3)
rec = next(r for r in pay["recordings"] if "m6 s4" in r["session_label"])
got = A._dspca_load(rec["gid"], rec["read"])
for k, val in got.items():
    if isinstance(val, dict):
        print(k, {kk: (getattr(vv, "shape", None) or (type(vv).__name__, str(vv)[:80])) for kk, vv in val.items()})
    else:
        print(k, getattr(val, "shape", None) or str(val)[:160])
