"""Make the two X-ray Many folders the new room round reads from, and read
every recording of each at its kept events (in-process, through the app's
own routes). Prints progress; safe to run again (reads already here are
skipped, and a folder with the same source is not made twice)."""
import json
import os
import sys
import time

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend.app import app  # noqa: E402

c = app.test_client()
WANT = [
    ("CTL Baseline (Optimized Paramters/Snap/10% Grace))", "bac8eaf5dfa8", 3),
    ("Ambiguous Dataset (Optimized Parameters/Snap/Halo) · data rich, less specific",
     "6fa7fef7b7a3", 3),
]
many = c.get("/api/dspca/many").get_json()
have = {(f["source"].get("artifact_id"), f["source"].get("version")): f["id"]
        for f in many.get("folders") or [] if not f.get("archived")}
fids = []
for name, aid, v in WANT:
    fid = have.get((aid, v))
    if not fid:
        r = c.post("/api/dspca/many/folder", json={
            "name": name, "source": {"artifact_id": aid, "version": v}}).get_json()
        print("folder", name, json.dumps(r)[:300], flush=True)
        fid = r.get("id")
    else:
        print("folder exists", name, fid, flush=True)
    fids.append(fid)

for fid in fids:
    r = c.post("/api/dspca/many/read", json={"folder": fid}).get_json()
    if not r.get("ok"):
        print("READ FAILED", fid, json.dumps(r)[:400], flush=True)
        continue
    job = r.get("job")
    print("read", fid, "todo", r.get("n"), "events", r.get("n_events"),
          "cached", len(r.get("cached") or []), "skipped", r.get("skipped"), flush=True)
    if not job:
        continue
    jid = job.get("id")
    last = None
    while True:
        time.sleep(5)
        s = c.get("/api/cfc/job/%s" % jid).get_json() or {}
        st = s.get("status") or (s.get("job") or {}).get("status")
        snap = s.get("job") or s
        mem = snap.get("members") or []
        done = sum(1 for m in mem if m.get("status") in ("done", "error"))
        line = "%s %s %d/%d" % (fid, st, done, len(mem))
        if line != last:
            print(line, flush=True)
            last = line
        if st in ("done", "error", "stopped", "failed", "canceled"):
            res = (c.get("/api/cfc/result/%s" % jid).get_json() or {}).get("result") or {}
            if st != "done":
                print("job error", snap.get("error"), flush=True)
            print("result", json.dumps({k: (len(v) if isinstance(v, list) else v)
                                        for k, v in res.items()})[:300], flush=True)
            for f in res.get("failed") or []:
                print("  failed", f, flush=True)
            break
print("ALL DONE", fids, flush=True)
