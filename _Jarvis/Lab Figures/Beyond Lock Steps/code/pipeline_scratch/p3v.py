"""The deduped Confluence sets' reads, on the VACC, as one Root Canal batch
(where: vacc, forced) through the running Jarvis. Merges into p3_reads.json."""
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8733"
S = os.path.dirname(os.path.abspath(__file__))
NEWREADS = os.path.join(S, "p3_reads.json")
DEDUPED = {"41dd94702761": "m2", "edc1a5080093": "m21", "43a2cfedde17": "m22", "f4c18a9a8bd4": "m26", "35c325a44d44": "m28",
           "a62d1b78448b": "m33", "eaecc4a5e194": "m34", "b60578899091": "m5", "1429bf1f239f": "m59", "cb139fb2ea29": "m6",
           "d4a4bcb4e47f": "m60", "ab69363ee622": "m61", "ece9a84acdea": "m7", "2a8e47760eea": "m8"}


def call(path, body=None, timeout=120):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


got = json.load(open(NEWREADS)) if os.path.exists(NEWREADS) else {}
todo = [e for e in DEDUPED if e not in got]
print("to read on the VACC:", [DEDUPED[e] for e in todo], flush=True)
r = call("/api/rootcanal/batch", {"entries": todo, "force": True, "where": "vacc"}, timeout=300)
if not r.get("ok"):
    raise SystemExit("REFUSED %s" % r.get("error"))
jid = r["job"]["id"]
print("job", jid, flush=True)
last = None
while True:
    time.sleep(20)
    try:
        d = call("/api/cfc/job/" + jid, timeout=60)
    except Exception as exc:                              # noqa: BLE001
        print("poll retry:", exc, flush=True)
        continue
    if not d.get("ok"):
        raise SystemExit("job lost: %s" % d.get("error"))
    j = d["job"]
    rows = j.get("members") or []
    line = " ".join("%s:%s" % (DEDUPED.get(m["id"], m["id"]), m.get("status")) for m in rows)
    if line != last:
        print(time.strftime("%H:%M"), line, flush=True)
        last = line
    for m in rows:
        if m.get("status") == "done" and m.get("read"):
            got[m["id"]] = m["read"]
    json.dump(got, open(NEWREADS, "w"))
    if j.get("state") in ("done", "failed", "canceled", "error"):
        print("state", j.get("state"), j.get("error") or "", "| result", json.dumps(j.get("result"))[:1500], flush=True)
        break
print("have", len(got), "of", len(DEDUPED), "| missing", [DEDUPED[e] for e in DEDUPED if e not in got])
