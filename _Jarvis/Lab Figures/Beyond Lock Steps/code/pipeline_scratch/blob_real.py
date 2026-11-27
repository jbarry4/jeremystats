"""Blob Analysis on the real new-round set (room v3, CTL Baseline Snap 10%),
without saving an Impression: every card as it stands, calls taken as
separable for the test only."""
import json
import os
import sys
import time

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import blobs as B  # noqa: E402
import numpy as np  # noqa: E402

room = A._er_rooms().get("dentate_spike")
aid = room["id"]
pay = A.ARTIFACTS.payload(aid, 3)
print("room v3:", (pay.get("source") or {}).get("folder_name"), pay.get("round"), len(pay["recordings"]), "recordings")
for r in pay["recordings"][:18]:
    b = r.get("box") or {}
    bi = (r.get("bite") or {})
    print("  %-28s %-4s n %4s band %s-%s  bite %s/%s  %s" % (
        r["session_label"][:28], r.get("group"), r["n"], b.get("sel_lo"), b.get("sel_hi"),
        r["counts"].get("1"), r["counts"].get("2"), (bi.get("verdict") or {}).get("word")))
t = time.time()
rows = A._er_impression_rows(pay)
print("impression rows %.1fs" % (time.time() - t), "errors", [r["session_label"] for r in rows if r.get("error")])
recs = []
t = time.time()
for row in rows:
    r = {"gid": row["gid"], "direct": True, "read": row["read"], "box": row["band"], "contacts": row["contacts"]}
    Ar, _rule, _fl = A._er_split_arrays(r)
    summ, _ev = B.recording(Ar, float(row.get("spacing_um") or 25.0), classes=np.asarray(row["types"]))
    recs.append(dict(row, call="yes", summary=summ))
print("measured %d recordings in %.1fs; summary kB %d" % (len(recs), time.time() - t,
      len(json.dumps([r["summary"] for r in recs])) // 1024))
labels, classes = A._blob_labels(recs, "group", [], "all")
print("groups", {l: labels.count(l) for l in set(labels)})
for m in ("peak", "fwhm_ms", "sharpness", "spread_um"):
    for blob in ("top", "bottom"):
        g = B.group_compare([r["summary"] for r in recs], labels, m, blob=blob, cls=classes)
        gs = {x["label"]: (x["stats"] or {}).get("median") for x in g["groups"]}
        t_ = (g.get("compare") or {}).get("tests") or {}
        print("  %-10s %-6s medians %s | loc p %s spread p %s shape p %s" % (
            m, blob, {k: (None if v is None else round(v, 4)) for k, v in gs.items()},
            (t_.get("location") or {}).get("p"), (t_.get("spread") or {}).get("p"), (t_.get("shape") or {}).get("p")))
