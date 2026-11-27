"""Take the two new sets into the Extraction Room (fitted here, no X-ray)
and archive the two old ones -- through the app's own routes, in-process."""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend.app import app  # noqa: E402

c = app.test_client()
NEW = [a for a in sys.argv[1:] if not a.startswith("--")]
OLD = ["xm-df8f89c45c34-v2", "xm-f7e3cb9cee38-v2"]
idx = c.get("/api/extraction").get_json()
for f in idx.get("folders") or []:
    if f["id"] in NEW + OLD:
        print("folder", f["id"], f["name"], "read", f.get("read_here"), "of", f.get("members"),
              "bundles", f.get("bundles"), "in room", f.get("in_room"), flush=True)
for fid in NEW:
    r = c.post("/api/extraction/extract", json={"room": "dentate_spike", "folder": fid, "direct": True,
                                                "note": "The new round (2026-11-12): fitted here, no X-ray."})
    out = r.get_json() or {}
    print("extract", fid, r.status_code, json.dumps({k: out.get(k) for k in ("ok", "version", "n", "error")}),
          "left", [(x.get("session_label"), x.get("why")) for x in out.get("left") or []], flush=True)
for fid in (OLD if "--archive" in sys.argv else []):
    r = c.post("/api/extraction/set_archive", json={"folder": fid, "archived": True}).get_json()
    print("archived", fid, bool(r and r.get("ok")), flush=True)
