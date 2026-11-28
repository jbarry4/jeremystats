"""X-ray Many's read of one folder, on a compute node: python k2_xray_read.py <folder id>

The route Jarvis runs on a desk (/api/dspca/many/read), called in-process, with the recordings opened off /netfiles
(vaccpatch). It writes each read's .npz into this copy's GUI_logs/.cache/dspca and its record into
GUI_logs/dspca/results under Jarvis_MACHINE, which the desk then takes home.
"""
import json
import sys
import time

import vaccpatch as V

A = V.A
fid = sys.argv[1]
c = A.app.test_client()
r = c.post("/api/dspca/many/read", json={"folder": fid})
out = r.get_json()
print("start", r.status_code, json.dumps({k: v for k, v in (out or {}).items() if k != "job"})[:600], flush=True)
job = (out or {}).get("job")
t0 = time.time()
last = None
while job and job.get("state") not in ("done", "failed", "canceled", "error"):
    time.sleep(10)
    job = c.get("/api/cfc/job/" + job["id"]).get_json().get("job") or {}
    now = [(m.get("id"), m.get("status"), m.get("done"), m.get("of")) for m in job.get("members") or []]
    if now != last:
        print(round(time.time() - t0), now, flush=True)
        last = now
    if job.get("state") is None and all(m.get("status") in ("done", "error", "stopped")
                                        for m in job.get("members") or [{}]):
        break
print("end", job.get("state") if job else None, json.dumps((job or {}).get("result"))[:3000], flush=True)
