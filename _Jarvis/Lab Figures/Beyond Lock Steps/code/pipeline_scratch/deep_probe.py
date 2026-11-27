"""What the room holds per recording and per event (read only)."""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402

c = app.test_client()
room = A._er_rooms()["dentate_spike"]
j = c.get("/api/extraction/%s?version=6" % room["id"]).get_json()
print("top keys:", sorted(j.keys()))
print("payload keys:", sorted(j["payload"].keys()))
r = j["payload"]["recordings"][0]
for k, v in sorted(r.items()):
    s = repr(v)
    print("  rec.%-18s %s" % (k, s if len(s) < 160 else s[:160] + " [cut for the probe only]"))
Ar, a, b = A._er_split_arrays(r)
print("split_arrays extras:", type(a), type(b))
for k, v in sorted(Ar.items()):
    if isinstance(v, np.ndarray):
        print("  A.%-16s %s %s" % (k, v.shape, v.dtype))
    else:
        s = repr(v)
        print("  A.%-16s %s" % (k, s if len(s) < 200 else s[:200]))
L = A._dspca_load(r["gid"], r["read"])
print("dspca_load keys:", sorted(L.keys()))
print("row keys:", sorted(L["rows"][0].keys()))
print("row0:", {k: (v if not isinstance(v, (list, dict)) else type(v).__name__) for k, v in L["rows"][0].items()})
for k, v in L.items():
    if k != "rows":
        s = repr(v)
        print("  L.%-14s %s" % (k, s if len(s) < 200 else s[:200]))
print("n recs", len(j["payload"]["recordings"]))
for r in j["payload"]["recordings"]:
    print("  %-28s %-5s ko %-6s n %4d dur %s sep %s" % (r["session_label"], r["group"], r.get("ko_now", r.get("ko_pct")), r["n"], r.get("duration_s"), (j.get("seps") or {}).get(r["gid"])))
try:
    t = c.get("/api/extraction/%s/timeline?version=6&gid=%s" % (room["id"], r["gid"])).get_json()
    print("timeline keys:", sorted(t.keys()), {k: (len(v) if isinstance(v, list) else v) for k, v in t.items() if k != "theta"})
    if isinstance(t.get("theta"), dict):
        print("theta keys:", {k: (len(v) if isinstance(v, list) else v) for k, v in t["theta"].items()})
except Exception as exc:
    print("timeline:", exc)
