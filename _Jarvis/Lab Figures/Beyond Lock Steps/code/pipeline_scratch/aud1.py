"""Audit step 1: the workflows behind the battery sets, their pools, and one
member's full record. Read only."""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

AR = A.ARTIFACTS
OUT = {}
for aid in ("6fa7fef7b7a3", "a7eee6a6ca9f", "178daabb125c", "4e5ce690d4b1", "4a29af93e601", "bac8eaf5dfa8"):
    rec = AR.get(aid) or {}
    vs = {}
    for v in range(1, int(rec.get("version") or 0) + 1):
        pay = AR.payload(aid, v) or {}
        run = pay.get("run") or {}
        vs[v] = {"definition": pay.get("definition"), "at": run.get("at"), "counts": run.get("counts"),
                 "inputs": run.get("inputs") or run.get("pinned") or run.get("sources")}
    OUT[aid] = {"nickname": rec.get("nickname"), "newest": rec.get("version"), "kind": rec.get("kind"),
                "updated": rec.get("updated"), "versions": vs}

pools = {}
for r in AR.list(kind="rootcanal_pool"):
    pools[r["id"]] = {"nickname": r.get("nickname") or r.get("name"), "newest": r.get("version"),
                      "archived": r.get("archived"), "updated": r.get("updated")}
OUT["pools"] = pools
pay = AR.payload("3561fc988afd", 2) or {}
OUT["pool_keys"] = sorted(pay.keys())
OUT["member0"] = (pay.get("members") or [{}])[0]
OUT["params"] = {k: pay.get(k) for k in pay if k not in ("members", "events", "rows", "cols")}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "aud1.json"), "w", encoding="utf-8") as fh:
    json.dump(OUT, fh, indent=1, default=str)
print("ok")
