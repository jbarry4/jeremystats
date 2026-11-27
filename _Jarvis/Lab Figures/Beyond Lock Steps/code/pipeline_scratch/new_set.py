"""The user's ask of 2026-11-13: in the Workflow tab, "PTEN and CTL Baseline
(Optimized Paramters/Snap/10% Grace[Extraction Room]))" with the latest
inputs, then put it in the Extraction Room in place of the CTL Baseline 10%
set. Through the app's own routes, in-process. Not banked (the room reads
the run; the bank already holds these events as ad9b1441cdaa)."""
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
from backend import xraymany  # noqa: E402

NAME = "PTEN and CTL Baseline (Optimized Paramters/Snap/10% Grace[Extraction Room]))"
OLD_WF, OLD_V, OLD_FID = "bac8eaf5dfa8", 3, "xm-500fa6c3c5"
ROOM = "dentate_spike"
c = app.test_client()


def ok(r, what):
    j = r.get_json() or {}
    if r.status_code != 200 or not j.get("ok"):
        raise SystemExit("%s failed (%s): %s" % (what, r.status_code, j.get("error") or j))
    return j


# 1 The workflow: the 10% one's definition, every input at its newest.
old = A.ARTIFACTS.payload(OLD_WF, OLD_V)["definition"]
body = {"kind": "ds", "nickname": NAME, "grace": old["grace"], "shape": old["shape"],
        "source": {"type": "pool", "artifact_id": old["source"]["artifact_id"]},
        "target": {"artifact_id": old["target"]["artifact_id"]}}
sv = ok(c.post("/api/rootcanal/workflow/save", json=body), "save")
aid = sv["artifact_id"]
print("workflow", aid, "v", sv["version"], flush=True)

# 2 Run it, not banked.
rj = ok(c.post("/api/rootcanal/workflow/%s/run" % aid, json={"bank": False, "refresh": True}), "run")
run, v = rj["run"], rj["version"]
print("ran v", v, "counts", run.get("counts"), "definition", json.dumps(rj["definition"]), flush=True)

# 3 The same events as the 10% set's run?
def keys(run_):
    cols = run_["cols"]
    return {(cols["gids"][int(g)], round(float(t), 6), cl)
            for cl, g, t in zip(cols["cls"], cols["g"], cols["t"]) if g is not None and t is not None}
oldrun = A.ARTIFACTS.payload(OLD_WF, OLD_V)["run"]
a, b = keys(oldrun), keys(run)
print("same events and classes as %s v%d: %s (old %d, new %d, only old %d, only new %d)"
      % (OLD_WF, OLD_V, a == b, len(a), len(b), len(a - b), len(b - a)), flush=True)

# 4 Its X-ray Many folder.
fj = ok(c.post("/api/dspca/many/folder", json={"name": NAME, "source": {"artifact_id": aid, "version": v}}), "folder")
fid = fj["id"]
print("folder", fid, "n", fj["n"], flush=True)

# 5 The bands drawn by hand on the old set, where the recording's events are the same.
_f, _wf, _v, mem_new = A._xm_folder(fid)
_f, _wf, _v, mem_old = A._xm_folder(OLD_FID)
same = {m["gid"] for m in mem_new} & {m["gid"] for m in mem_old if any(
    x["gid"] == m["gid"] and x["stamps_hash"] == m["stamps_hash"] for x in mem_new)}
prefs = A.STORE.get_prefs() or {}
carried = []
for key in ("extraction_band", "extraction_sep", "extraction_flip", "extraction_split"):
    patch = {}
    for k, val in (prefs.get(key) or {}).items():
        parts = str(k).split("|")
        if len(parts) == 3 and parts[0] == ROOM and parts[1] == OLD_FID and parts[2] in same and isinstance(val, dict):
            patch["%s|%s|%s" % (ROOM, fid, parts[2])] = dict(val, carried_from=OLD_FID)
            carried.append((key, parts[2], val.get("by")))
    if patch:
        A.STORE.set_prefs({}, merge={key: patch})
print("carried", carried, "same-events recordings", len(same), "of", len(mem_new), flush=True)

# 6 The room's next version, fitted by the room in each band.
note = ("PTEN and CTL Baseline, 10% grace (2026-11-13): the same events as the CTL Baseline 10% set "
        "(border around the CTL pool, applied to the CTL & PTEN pool), from a workflow named for "
        "what it holds. Hand bands carried over.")
ej = ok(c.post("/api/extraction/extract", json={"room": ROOM, "folder": fid, "direct": True, "note": note}), "extract")
print("room version", ej["version"], "n", ej["n"], "left", ej.get("left"), flush=True)

# 7 The old set put away in the room (nothing deleted).
ok(c.post("/api/extraction/set_archive", json={"folder": OLD_FID, "archived": True}), "archive")
print("archived", OLD_FID, flush=True)

room = A._er_rooms()[ROOM]
pay = A.ARTIFACTS.payload(room["id"], ej["version"])
tot = {}
for rec in pay["recordings"]:
    tot[rec["group"]] = tot.get(rec["group"], 0) + rec["n"]
    b = rec.get("bite") or {}
    print("   %-24s %-4s n %4s band %s-%s%s  DS1/DS2 %s/%s  SI %s %s" % (
        rec["session_label"][:24], rec.get("group"), rec["n"], rec["box"].get("sel_lo"), rec["box"].get("sel_hi"),
        " (by hand)" if not rec["box"].get("auto") else "", rec["counts"].get("1"), rec["counts"].get("2"),
        (b.get("scores") or {}).get("si"), (b.get("verdict") or {}).get("word")), flush=True)
print("totals", tot, flush=True)
json.dump({"workflow": aid, "run_version": v, "folder": fid, "room_version": ej["version"]},
          open(os.path.join(os.path.dirname(__file__), "new_set.json"), "w"))
