"""The room's v4 and v6 through the app's route: which saved Bite lines are
stale under each, and the m2 s3 split view's band."""
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
aid = A._er_rooms().get("dentate_spike")["id"]
for v in (4, 6):
    got = c.get("/api/extraction/%s?version=%d" % (aid, v)).get_json()
    pay = got["payload"]
    print("v%d" % v, "splits", {k: (s.get("method"), s.get("cut"), s.get("sink")) for k, s in got["splits"].items()})
    for r in pay["recordings"]:
        if r.get("split_stale") or r.get("split"):
            print("   ", r["session_label"], "split", r.get("split"), "stale", bool(r.get("split_stale")),
                  "counts", r.get("counts"))
    m2 = next(r for r in pay["recordings"] if "m2 s3" in r["session_label"])
    sv = c.get("/api/extraction/%s/split?version=%d&gid=%s" % (aid, v, m2["gid"])).get_json()
    print("   m2 s3 split view: band", (sv.get("band") or {}).get("sel_lo"), (sv.get("band") or {}).get("sel_hi"),
          "moved", sv.get("band_moved"), "contacts", sv["bite"]["contacts"][0], "-", sv["bite"]["contacts"][-1],
          "choice", sv.get("choice"), "stale", bool(sv.get("stale")), "sink", sv["bite"]["bumps"].get("sink"))
