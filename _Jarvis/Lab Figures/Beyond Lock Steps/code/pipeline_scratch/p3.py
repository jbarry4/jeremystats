"""Duplicate fix, Root Canal part, through the running Jarvis.
  read  -- read each deduped Confluence set's newest version (one job each)
  save  -- refit + save the three pools with the new reads (--apply to save)
  run   -- rerun the four workflows on the newest pools, unbanked"""
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8733"
S = os.path.dirname(os.path.abspath(__file__))
DEDUPED = {"41dd94702761": "m2", "edc1a5080093": "m21", "43a2cfedde17": "m22", "f4c18a9a8bd4": "m26", "35c325a44d44": "m28",
           "a62d1b78448b": "m33", "eaecc4a5e194": "m34", "b60578899091": "m5", "1429bf1f239f": "m59", "cb139fb2ea29": "m6",
           "d4a4bcb4e47f": "m60", "ab69363ee622": "m61", "ece9a84acdea": "m7", "2a8e47760eea": "m8"}
POOLS = ["07cdcb084c86", "3561fc988afd", "105b40acbbb0"]
NEWREADS = os.path.join(S, "p3_reads.json")


def call(path, body=None, timeout=3600):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def wait(job):
    while job and (job.get("status") or job.get("state")) not in ("done", "failed", "canceled", "error"):
        time.sleep(5)
        try:
            nxt = call("/api/cfc/job/" + job["id"], timeout=60)
        except Exception as exc:                      # a hung poll: ask again
            print("   poll retry:", exc, flush=True)
            continue
        if not nxt.get("ok"):
            return {"state": "lost", "error": nxt.get("error")}
        job = nxt.get("job") or {}
    return job


step = sys.argv[1]
if step == "read":
    got = json.load(open(NEWREADS)) if os.path.exists(NEWREADS) else {}
    for eid, lab in DEDUPED.items():
        if eid in got:
            continue
        t0 = time.time()
        # Ask first; a "cached" answer counts only when this exact read is on
        # disk (not a covering superset read, which pool fit refuses).
        r = call("/api/rootcanal/read", {"entry_id": eid}, timeout=300)
        gid = (call("/api/bank/" + eid, timeout=120).get("entry") or {}).get("gid")
        here = r.get("ok") and gid and os.path.exists(os.path.join(
            r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app\GUI_logs\.cache\rootcanal", "%s__%s.npz" % (gid, r.get("read"))))
        if not here:
            r = call("/api/rootcanal/read", {"entry_id": eid, "force": True}, timeout=300)
        else:
            r["job"] = None
        if not r.get("ok"):
            print(lab, "REFUSED", r.get("error"), flush=True)
            continue
        if r.get("job"):
            j = wait(r["job"])
            if (j.get("status") or j.get("state")) != "done":
                print(lab, "job", j.get("status") or j.get("state"), j.get("error"), flush=True)
                continue
        got[eid] = r["read"]
        json.dump(got, open(NEWREADS, "w"))
        print("%-4s read %s  n %s  %s  %.0f s" % (lab, r["read"], r.get("n"), "cached" if r.get("cached") else "read", time.time() - t0),
              flush=True)
    print("done", len(got), "of", len(DEDUPED))
elif step == "save":
    new = json.load(open(NEWREADS))
    for pid in POOLS:
        d = call("/api/rootcanal/pool/" + pid)
        a, p = d["artifact"], d["payload"]
        members, swapped = [], 0
        for m in a["current"]["inputs"]:
            key = m["key"]
            if m["entry_id"] in new:
                key = "u:%s:%s" % (m["entry_id"], new[m["entry_id"]])
                swapped += key != m["key"]
            members.append({"key": key, "params": m.get("params")})
        meas = {k: v for k, v in (p["params"].get("measure") or {}).items() if k != "filter_label"}
        body = {"members": members, "mouse_types": p.get("mouse_types") or {}, "focus": p.get("focus"), "measure": meas,
                "k": p["params"].get("k"), "complete_only": bool(p["params"].get("complete_only")),
                "cluster_calls": p["params"].get("cluster_calls") or {}, "cluster_names": p["params"].get("cluster_names") or {},
                "margin": None, "border": None, "drawn": p["params"].get("drawn") or [], "all_ds": p["params"].get("all_ds") or None,
                "saved": {"artifact_id": pid, "version": a["version"]}}
        f = call("/api/rootcanal/pool/fit", body)
        res = f.get("result") or f.get("pool") or f
        print(pid, a["nickname"], "v%s" % a["version"], "| members swapped", swapped, "| before", p.get("counts"), "| after",
              res.get("counts") if f.get("ok", True) else f.get("error"))
        if "--apply" in sys.argv:
            body.update(artifact_id=pid, nickname=a["nickname"],
                        note="Duplicate stamps removed (2026-11-19): %d recordings re-read after Spike stamps under 10 ms "
                             "from a neighbour were marked Garbage in their Confluence sets." % swapped)
            s = call("/api/rootcanal/pool/save", body)
            print("   saved v%s" % s.get("version"), s.get("error") or "")
elif step == "run":
    for wid in ("178daabb125c", "4a29af93e601", "6fa7fef7b7a3", "a7eee6a6ca9f"):
        body = {"refresh": True}
        if wid in ("178daabb125c", "4a29af93e601"):
            body["bank"] = False
        r = call("/api/rootcanal/workflow/%s/run" % wid, body)
        if not r.get("ok"):
            print(wid, "FAILED", r.get("error"))
            break
        d, run = r["definition"], r["run"]
        print(wid, "-> v%s" % r["version"], "| target", (d.get("target") or {}).get("version"), "| source",
              (d.get("source") or {}).get("version"), "| uses", {k: v.get("version") for k, v in (d.get("uses") or {}).items()},
              "| counts", run.get("counts"))
