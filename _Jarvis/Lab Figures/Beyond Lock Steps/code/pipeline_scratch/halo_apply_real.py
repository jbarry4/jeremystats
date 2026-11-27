"""Apply the Halo (2x / 1.5x) to 'Ambiguous Dataset (Optimized Parameters/Snap)'
v2 and bank its DS side, through the app's own routes (in-process)."""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend.app import app  # noqa: E402

AID = "6fa7fef7b7a3"
c = app.test_client()
r = c.post("/api/rootcanal/workflow/%s/halo" % AID, json={
    "version": 2, "reach": 2, "margin": 1.5,
    "nickname": "Halo · data rich, but less specific",
    "note": ("Ambiguous Dataset (Optimized Parameters/Snap/Halo): the data-rich, "
             "less specific set. Its dentate spikes for the Extraction Room are "
             "the events inside the DS border only plus those outside both that "
             "the DS halo captured.")})
out = r.get_json()
if not out or not out.get("ok"):
    print("HALO FAILED", r.status_code, json.dumps(out)[:600])
    sys.exit(1)
v = out["version"]
run = out["run"]
print("saved v%s" % v, "counts", run.get("counts"), "halo", {k: run["halo"].get(k) for k in ("reach", "margin", "captured", "from_version")})
b = c.post("/api/rootcanal/workflow/%s/bank" % AID, json={
    "version": v, "side": "ds",
    "name": "Dentate spikes · Ambiguous Dataset (Optimized Parameters/Snap/Halo) · data rich, but less specific",
    "note": "Data rich, but less specific: for the Extraction Room's new round."})
bo = b.get_json()
print("bank", b.status_code, json.dumps(bo)[:400])
