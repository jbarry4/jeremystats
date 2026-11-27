"""The calls made on each new-round set, beside the Bite line's split and SI
before (bumps: v3/v4) and now (humps: v5/v6)."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

aid = A._er_rooms().get("dentate_spike")["id"]
for old, new, fid in ((3, 5, "xm-500fa6c3c5"), (4, 6, "xm-f6c45faefb")):
    seps = A._er_seps("dentate_spike", fid)
    po, pn = A.ARTIFACTS.payload(aid, old), A.ARTIFACTS.payload(aid, new)
    print("set", fid, (pn.get("source") or {}).get("folder_name"))
    ro = {r["gid"]: r for r in po["recordings"]}
    for r in pn["recordings"]:
        o = ro.get(r["gid"]) or {}
        bo, bn = o.get("bite") or {}, r.get("bite") or {}
        s = seps.get(r["gid"]) or {}
        print("   %-24s call %-5s by %-16s | before %s/%s SI %-6s %-10s | now %s/%s SI %-6s %s" % (
            r["session_label"][:24], s.get("verdict"), (s.get("by") or "")[:16],
            (o.get("counts") or {}).get("1"), (o.get("counts") or {}).get("2"),
            (bo.get("scores") or {}).get("si"), (bo.get("verdict") or {}).get("word"),
            r["counts"].get("1"), r["counts"].get("2"), (bn.get("scores") or {}).get("si"),
            (bn.get("verdict") or {}).get("word")))
