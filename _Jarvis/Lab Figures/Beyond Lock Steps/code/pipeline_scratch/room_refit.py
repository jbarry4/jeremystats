"""Fit the two new-round sets again, as the room's next versions, with the
Bite line on the recording's two humps -- through the app's own route,
in-process -- and say each card's line under it."""
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

NOTE = ("Fitted again (2026-11-12): the Bite line's sink is now the recording's "
        "two humps, each event's sink taken whole in each, so a hump with a notch "
        "inside it (a camel) stays one hump. Bands drawn by hand are kept.")
c = app.test_client()
for fid in sys.argv[1:]:
    r = c.post("/api/extraction/extract", json={"room": "dentate_spike", "folder": fid, "direct": True,
                                                "note": NOTE})
    out = r.get_json() or {}
    print("extract", fid, r.status_code, json.dumps({k: out.get(k) for k in ("ok", "version", "n", "error")}),
          "left", [(x.get("session_label"), x.get("why")) for x in out.get("left") or []], flush=True)
    v = out.get("version")
    if not v:
        continue
    room = A._er_rooms().get("dentate_spike")
    pay = A.ARTIFACTS.payload(room["id"], v)
    for rec in pay["recordings"]:
        b = rec.get("bite") or {}
        print("   %-24s %-4s n %4s band %s-%s sink %s  DS1/DS2 %s/%s  SI %s %s" % (
            rec["session_label"][:24], rec.get("group"), rec["n"], rec["box"].get("sel_lo"), rec["box"].get("sel_hi"),
            b.get("sink"), rec["counts"].get("1"), rec["counts"].get("2"),
            (b.get("scores") or {}).get("si"), (b.get("verdict") or {}).get("word")), flush=True)
