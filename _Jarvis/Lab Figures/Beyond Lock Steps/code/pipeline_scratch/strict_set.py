"""The user's ask of 2026-11-13: the PTEN and CTL Baseline 10% set without
the events that also sit inside the P-spike border. An Ambiguous workflow
(the 10% DS border + the P-spike border, applied to the CTL & PTEN pool, no
halo), whose DS side is "inside the DS border only"; its X-ray Many folder,
read where its events changed; the room's next version; the v7 set put
away. Through the app's own routes, in-process."""
import collections
import json
import os
import sys
import time

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import warnings  # noqa: E402
warnings.filterwarnings("ignore")
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import cfc, xraymany  # noqa: E402

NAME = "PTEN and CTL Baseline (Optimized Paramters/Snap/10% Grace[Extraction Room; No P-spikes]))"
DS_WF, DS_V = "4a29af93e601", 2          # PTEN and CTL Baseline 10% (room v7)
PS_WF = "4e5ce690d4b1"                    # PTEN Baseline (Optimized Parameters/Snap): the P-spike border
POOL = "3561fc988afd"                     # CTL & PTEN Baseline v2 (Optimized parameters)
OLD_FID = "xm-12427c99f8"                 # the room's v7 set
ROOM = "dentate_spike"
c = app.test_client()


def ok(r, what):
    j = r.get_json() or {}
    if r.status_code != 200 or not j.get("ok"):
        raise SystemExit("%s failed (%s): %s" % (what, r.status_code, j.get("error") or j))
    return j


def classes(run):
    cols = run["cols"]
    return {(cols["gids"][int(g)], round(float(t), 6)): cl
            for cl, g, t in zip(cols["cls"], cols["g"], cols["t"]) if g is not None and t is not None}


# 1 The workflow: both borders on the CTL & PTEN pool, no halo.
body = {"kind": "ambiguous", "nickname": NAME,
        "uses": {"ds": {"artifact_id": DS_WF, "version": DS_V}, "pspike": {"artifact_id": PS_WF}},
        "target": {"artifact_id": POOL}}
sv = ok(c.post("/api/rootcanal/workflow/save", json=body), "save")
aid = sv["artifact_id"]
print("workflow", aid, flush=True)
rj = ok(c.post("/api/rootcanal/workflow/%s/run" % aid, json={}), "run")
run, v = rj["run"], rj["version"]
print("ran v%s counts %s" % (v, run.get("counts")), flush=True)
print("definition", json.dumps(rj["definition"]), flush=True)

# 2 Its DS side against the 10% set: the same events less those inside the
# P-spike border, and nothing else.
old = classes(A.ARTIFACTS.payload(DS_WF, DS_V)["run"])
new = classes(run)
kept_old = {k for k, cl in old.items() if cl == "inside"}
keep = xraymany.inside_by_gid(run)
kept_new = {(g, t) for g, ts in keep.items() for t in ts}
dropped = kept_old - kept_new
print("10%% set %d events; this one %d; dropped %d; added %d" % (
    len(kept_old), len(kept_new), len(dropped), len(kept_new - kept_old)), flush=True)
print("dropped events' class here:", dict(collections.Counter(new.get(k) for k in dropped)), flush=True)
print("this run's DS side's classes:", dict(collections.Counter(new.get(k) for k in kept_new)), flush=True)
groups = A._xm_groups(sorted({g for g, _t in kept_old}))
labels = {m["gid"]: m["session_label"] for m in A._xm_folder(OLD_FID)[3]}
by = collections.Counter(g for g, _t in dropped)
print("dropped by recording:", {labels.get(g, g): n for g, n in by.items()}, flush=True)
print("dropped by group:", dict(collections.Counter(groups.get(g) for g, _t in dropped)), flush=True)
if kept_new - kept_old or dropped != {k for k in kept_old if new.get(k) == "both"}:
    raise SystemExit("Not the 10% set less its P-spike-border events: stopping before the room.")

# 3 Its X-ray Many folder, read where its events changed.
fj = ok(c.post("/api/dspca/many/folder", json={"name": NAME, "source": {"artifact_id": aid, "version": v}}), "folder")
fid = fj["id"]
print("folder", fid, flush=True)
rd = ok(c.post("/api/dspca/many/read", json={"folder": fid}), "read")
print("to read %s (%s events); already read %d" % (rd.get("n"), rd.get("n_events"), len(rd.get("cached") or [])), flush=True)
if rd.get("job"):
    jid = rd["job"]["id"]
    while True:
        job = cfc.get(jid)
        snap = job.snapshot()
        if snap["status"] != "running":
            break
        time.sleep(5)
    print("read job", snap["status"], snap.get("error"), flush=True)
    for m in snap.get("members") or []:
        print("   ", m.get("label"), m.get("status"), m.get("done"), m.get("of"), m.get("error") or "", flush=True)
    if snap["status"] != "done":
        raise SystemExit("The read did not finish.")

# 4 The bands drawn by hand on the v7 set: a band is where the sinks sit on
# the shank, which a few events less does not move. Other calls only where
# the events are the same.
_f, _wf, _v, mem_new = A._xm_folder(fid)
_f, _wf, _v, mem_old = A._xm_folder(OLD_FID)
sh_old = {m["gid"]: m["stamps_hash"] for m in mem_old}
same = {m["gid"] for m in mem_new if sh_old.get(m["gid"]) == m["stamps_hash"]}
prefs = A.STORE.get_prefs() or {}
carried = []
for key in ("extraction_band", "extraction_sep", "extraction_flip", "extraction_split"):
    patch = {}
    for k, val in (prefs.get(key) or {}).items():
        parts = str(k).split("|")
        if len(parts) != 3 or parts[0] != ROOM or parts[1] != OLD_FID or not isinstance(val, dict):
            continue
        if key != "extraction_band" and parts[2] not in same:
            continue
        patch["%s|%s|%s" % (ROOM, fid, parts[2])] = dict(val, carried_from=OLD_FID)
        carried.append((key, labels.get(parts[2], parts[2]), val.get("by")))
    if patch:
        A.STORE.set_prefs({}, merge={key: patch})
print("carried", carried, "| same events on", len(same), "of", len(mem_new), flush=True)

# 5 The room's next version.
note = ("PTEN and CTL Baseline, 10% grace, no P-spikes (2026-11-13): the 10% set's events less the %d that also "
        "sit inside the P-spike border -- inside the DS border only. Hand bands carried over." % len(dropped))
ej = ok(c.post("/api/extraction/extract", json={"room": ROOM, "folder": fid, "direct": True, "note": note}), "extract")
print("room version", ej["version"], "n", ej["n"], "left", ej.get("left"), flush=True)
ok(c.post("/api/extraction/set_archive", json={"folder": OLD_FID, "archived": True}), "archive")
print("archived", OLD_FID, flush=True)

room = A._er_rooms()[ROOM]
pay = A.ARTIFACTS.payload(room["id"], ej["version"])
old_pay = A.ARTIFACTS.payload(room["id"], 7)
old_rec = {r["gid"]: r for r in old_pay["recordings"]}
tot = collections.Counter()
for rec in pay["recordings"]:
    tot[rec["group"]] += rec["n"]
    b, o = rec.get("bite") or {}, old_rec.get(rec["gid"]) or {}
    ob = o.get("bite") or {}
    print("   %-24s %-4s n %4s (v7 %4s) band %s-%s%s  DS1/DS2 %s/%s (v7 %s/%s)  SI %s %s (v7 %s)" % (
        rec["session_label"][:24], rec.get("group"), rec["n"], o.get("n"), rec["box"].get("sel_lo"),
        rec["box"].get("sel_hi"), " by hand" if not rec["box"].get("auto") else "",
        rec["counts"].get("1"), rec["counts"].get("2"), (o.get("counts") or {}).get("1"),
        (o.get("counts") or {}).get("2"), (b.get("scores") or {}).get("si"), (b.get("verdict") or {}).get("word"),
        (ob.get("scores") or {}).get("si")), flush=True)
print("totals", dict(tot), flush=True)
json.dump({"workflow": aid, "run_version": v, "folder": fid, "room_version": ej["version"], "dropped": len(dropped)},
          open(os.path.join(os.path.dirname(__file__), "strict_set.json"), "w"))
