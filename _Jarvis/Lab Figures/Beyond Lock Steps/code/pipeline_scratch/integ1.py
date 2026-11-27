"""Data integrity, step 1: what the two room sets are made of -- their
workflows, pools, X-ray Many folders and the room versions -- read only."""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402

c = app.test_client()
OUT = {}

wfs = c.get("/api/rootcanal/workflows").get_json()["workflows"]
OUT["workflows"] = []
for w in wfs:
    OUT["workflows"].append({k: w.get(k) for k in ("id", "nickname", "name", "kind", "version", "archived",
                                                   "folder", "stale", "updated", "grace", "shape")})

for aid in ("bac8eaf5dfa8", "6fa7fef7b7a3"):
    one = c.get("/api/rootcanal/workflow/" + aid).get_json()
    pay = one.get("payload") or {}
    d = pay.get("definition") or {}
    run = pay.get("run") or {}
    OUT[aid] = {"artifact": one.get("artifact"), "shown": one.get("shown"), "stale": one.get("stale"),
                "definition": d,
                "run_keys": sorted(run.keys()),
                "counts": run.get("counts"), "kept": run.get("kept"), "grace": run.get("grace"),
                "bank": run.get("bank"), "at": run.get("at"), "by": run.get("by"),
                "lines": [{k: l.get(k) for k in ("version", "ran", "at", "kept", "counts", "grace", "bank")}
                          for l in one.get("lines") or []]}

many = c.get("/api/dspca/many").get_json()["folders"]
OUT["folders"] = [{"id": f["id"], "name": f["name"], "at": f.get("at"), "source": f.get("source"),
                   "archived": f.get("archived"),
                   "members": [(m["session_label"], m.get("group"), m["n"], m["stamps_hash"], m.get("read"))
                               for m in f["members"]]} for f in many]

room = A._er_rooms().get("dentate_spike")
OUT["room"] = {"id": room["id"], "version": room.get("version")}
vers = []
for v in range(1, int(room.get("version") or 0) + 1):
    pay = A.ARTIFACTS.payload(room["id"], v) or {}
    src = pay.get("source") or {}
    vers.append({"v": v, "round": pay.get("round"), "source": src,
                 "recs": [(r.get("session_label"), r.get("group"), r.get("n"), r.get("read"),
                           r.get("stamps_hash") or (r.get("bundle") or {}).get("stamps_hash"))
                          for r in pay.get("recordings") or []]})
OUT["room_versions"] = vers

with open(os.path.join(os.path.dirname(__file__), "integ1.json"), "w", encoding="utf-8") as fh:
    json.dump(OUT, fh, indent=1, default=str)
print("ok")
