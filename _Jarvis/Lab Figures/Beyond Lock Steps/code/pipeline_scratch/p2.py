"""Phase 2, through the running Jarvis (http://127.0.0.1:8733), so nothing
needs a restart. Steps (argv): check | read | save | run."""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8733"
M1 = "bfa98498290b"
POOLS = ["3561fc988afd", "105b40acbbb0"]


def call(path, body=None, timeout=1800):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def wait(job):
    while job and job.get("state") not in ("done", "failed", "canceled", "error"):
        time.sleep(3)
        job = call("/api/cfc/job/" + job["id"]).get("job") or {}
    return job


def body_of(pid, swap=None):
    d = call("/api/rootcanal/pool/" + pid)
    a, p = d["artifact"], d["payload"]
    ins = a["current"]["inputs"]
    members = []
    for m in ins:
        key = m["key"]
        if swap and m.get("entry_id") == M1:
            key = swap
        members.append({"key": key, "params": m.get("params")})
    meas = {k: v for k, v in (p["params"].get("measure") or {}).items() if k != "filter_label"}
    return {"members": members, "mouse_types": p.get("mouse_types") or {}, "focus": p.get("focus"),
            "measure": meas, "k": p["params"].get("k") or p.get("k"), "complete_only": bool(p["params"].get("complete_only")),
            "cluster_calls": p["params"].get("cluster_calls") or {}, "cluster_names": p["params"].get("cluster_names") or {},
            "margin": None, "border": None, "drawn": p["params"].get("drawn") or [], "all_ds": p["params"].get("all_ds") or None,
            "saved": {"artifact_id": pid, "version": a["version"]}}, a, p


def summary(res_or_payload):
    r = res_or_payload
    per = {}
    mem = r.get("members") or []
    for e in r.get("events") or []:
        lab = (mem[e["m"]] if isinstance(e.get("m"), int) else {}).get("session_label")
        per.setdefault(lab, {}).setdefault(e.get("cls_pool"), 0)
        per[lab][e.get("cls_pool")] += 1
    return r.get("counts"), per


step = sys.argv[1]
if step == "check":
    for pid in POOLS:
        b, a, p = body_of(pid)
        got = call("/api/rootcanal/pool/fit", b)
        if not got.get("ok"):
            print(pid, "FIT FAILED", got.get("error"))
            continue
        res = got.get("result") or got.get("pool") or got
        c0, per0 = summary(p)
        c1, per1 = summary(res)
        print(pid, a["nickname"], "v", a["version"], "| saved", c0, "| refit", c1,
              "| per-mouse identical:", per0 == per1)
elif step == "read":
    r = call("/api/rootcanal/read", {"entry_id": M1})
    print({k: r.get(k) for k in ("ok", "cached", "read", "n", "error")})
    if r.get("job"):
        j = wait(r["job"])
        print("job", j.get("state"), j.get("result") or j.get("error"))
elif step == "save":
    rh = sys.argv[2]
    for pid in POOLS:
        b0, a, p = body_of(pid)
        old = next(m["key"] for m in b0["members"] if m["key"].startswith("u:" + M1) or M1 in m["key"])
        b, a, p = body_of(pid, swap="u:%s:%s" % (M1, rh))
        got = call("/api/rootcanal/pool/fit", b)
        res = got.get("result") or got.get("pool") or got
        c0, per0 = summary(p)
        c1, per1 = summary(res)
        diff = {k: (per0.get(k), per1.get(k)) for k in set(per0) | set(per1) if per0.get(k) != per1.get(k)}
        print(pid, a["nickname"], "old m1 key", old, "| before", c0, "| after", c1, "| mice that changed:", diff)
        if "--apply" in sys.argv:
            b.update(artifact_id=pid, nickname=a["nickname"], focus=p.get("focus"),
                     note="m1 s2 re-read from its Confluence set's restored Lock version (2026-11-19); "
                          "the old read held the pre-Lock stamps that Panning's bank-on-leave had put back.")
            s = call("/api/rootcanal/pool/save", b)
            print("   saved:", {k: s.get(k) for k in ("ok", "error", "version", "confirmed")},
                  {k: (s.get("artifact") or {}).get(k) for k in ("id", "version")})
elif step == "run":
    for wid, bank in (("4a29af93e601", False), ("6fa7fef7b7a3", None), ("a7eee6a6ca9f", None)):
        body = {"refresh": True}
        if bank is False:
            body["bank"] = False
        r = call("/api/rootcanal/workflow/%s/run" % wid, body)
        if not r.get("ok"):
            print(wid, "FAILED", r.get("error"))
            break
        run, d = r["run"], r["definition"]
        print(wid, "-> v%s" % r["version"], "| target", d.get("target"), "| uses",
              {k: (v.get("artifact_id"), v.get("version")) for k, v in (d.get("uses") or {}).items()},
              "| counts", run.get("counts"), "kept", run.get("kept"), "| bank", (run.get("bank") or {}).get("entry_id"))
        print("   diff vs last run:", json.dumps(run.get("diff"))[:1500])
