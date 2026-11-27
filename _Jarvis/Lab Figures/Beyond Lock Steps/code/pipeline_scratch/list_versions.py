"""Read only: the dentate_spike room's versions, their sets and event counts."""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402

c = app.test_client()
room = A._er_rooms()["dentate_spike"]
print({k: v for k, v in room.items() if k not in ("payload",)} if isinstance(room, dict) else room)
for V in range(1, 12):
    r = c.get("/api/extraction/%s?version=%d" % (room["id"], V))
    if r.status_code != 200:
        print(V, "status", r.status_code)
        continue
    j = r.get_json() or {}
    recs = (j.get("payload") or {}).get("recordings") or []
    n = sum(int(x.get("n") or len(x.get("events") or []) or 0) for x in recs)
    meta = {k: j.get(k) for k in ("label", "note", "set_name", "set", "created", "mode") if k in j}
    print(V, "recordings", len(recs), "events", n, str(meta)[:400])
    if recs:
        print("   keys", sorted(recs[0].keys())[:40])
