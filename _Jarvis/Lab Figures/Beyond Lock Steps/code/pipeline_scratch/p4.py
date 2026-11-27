"""Phase 3, through the running Jarvis: the two room sets rebuilt from the
fixed workflow runs.
  folder  -- a new X-ray Many folder per set from the newest run (ids -> p4_state.json)
  read    -- read each new folder (one job each)
  copy    -- carry every per-set decision (band, call, split, flip, mode) from the old folder
  extract -- the room's next version from each new folder (direct round), then archive the old sets
  check   -- each card's stamps against its run's kept stamps"""
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8733"
S = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(S, "p4_state.json")
SETS = [  # (old folder, workflow, label)
    ("xm-f6c45faefb", "6fa7fef7b7a3", "Halo"),
    ("xm-1d6cfcdd3d", "a7eee6a6ca9f", "No P-spikes"),
]
SETS = [x for x in SETS if x[2] in (sys.argv[2:] or [x[2]])]
KEYS = ("extraction_band", "extraction_sep", "extraction_split", "extraction_flip", "extraction_mode")
ROOM = "dentate_spike"


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
        time.sleep(10)
        try:
            nxt = call("/api/cfc/job/" + job["id"], timeout=60)
        except Exception as exc:                      # noqa: BLE001
            print("   poll retry:", exc, flush=True)
            continue
        if not nxt.get("ok"):
            return {"status": "lost", "error": nxt.get("error")}
        job = nxt.get("job") or {}
    return job


st = json.load(open(STATE)) if os.path.exists(STATE) else {}
step = sys.argv[1]
folders = {f["id"]: f for f in call("/api/dspca/many")["folders"]}

if step == "folder":
    for old, wid, lab in SETS:
        if lab in st:
            continue
        w = call("/api/rootcanal/workflow/" + wid)
        v = (w.get("artifact") or {}).get("version") or w.get("version")
        name = folders[old]["name"] + " · fixed 2026-11-19"
        r = call("/api/dspca/many/folder", {"name": name, "source": {"artifact_id": wid, "version": v}})
        print(lab, "workflow v%s" % v, "->", r)
        if r.get("ok"):
            st[lab] = {"old": old, "new": r["id"], "workflow": wid, "version": v, "name": name}
            json.dump(st, open(STATE, "w"), indent=1)
elif step == "read":
    for old, wid, lab in SETS:
        fid = st[lab]["new"]
        t0 = time.time()
        r = call("/api/dspca/many/read", {"folder": fid})
        j = wait(r.get("job")) if r.get("job") else None
        print(lab, fid, "| started:", {k: r.get(k) for k in ("ok", "error")}, "| job:", (j or {}).get("status"),
              "| %.0f s" % (time.time() - t0), flush=True)
        if j:
            bad = [m for m in (j.get("members") or []) if m.get("status") not in ("done", None)]
            print("   members not done:", [(m.get("label") or m.get("id"), m.get("status"), m.get("error")) for m in bad])
elif step == "copy":
    prefs = call("/api/prefs")
    prefs = prefs.get("prefs") or prefs
    for old, wid, lab in SETS:
        new = st[lab]["new"]
        merge = {}
        for k in KEYS:
            m = {}
            for kk, v in (prefs.get(k) or {}).items():
                parts = str(kk).split("|")
                if parts[0] == ROOM and len(parts) >= 2 and parts[1] == old:
                    m["|".join([ROOM, new] + parts[2:])] = v
            if m:
                merge[k] = m
        print(lab, {k: len(v) for k, v in merge.items()})
        if "--apply" in sys.argv and merge:
            r = call("/api/prefs", {"merge": merge})
            print("   copied:", r.get("ok"), r.get("error") or "")
elif step == "extract":
    for old, wid, lab in SETS:
        new = st[lab]["new"]
        r = call("/api/extraction/extract", {"room": ROOM, "folder": new, "direct": True,
                                              "note": "%s set rebuilt 2026-11-19: m1 s2 on Lock's stamps, duplicate stamps "
                                                      "removed; calls and bands carried from %s." % (lab, old)})
        print(lab, {k: r.get(k) for k in ("ok", "error", "artifact_id", "version", "n")}, "| left out:", r.get("left"))
        if r.get("ok"):
            st[lab].update(room_artifact=r["artifact_id"], room_version=r["version"])
            json.dump(st, open(STATE, "w"), indent=1)
            a = call("/api/extraction/set_archive", {"folder": old, "archived": True})
            print("   old set archived:", a.get("ok"))
elif step == "check":
    for old, wid, lab in SETS:
        s = st[lab]
        room = call("/api/extraction/%s?version=%s" % (s["room_artifact"], s["room_version"]))
        pay = room.get("payload") or room
        recs = pay.get("recordings") or []
        print(lab, "room v%s" % s["room_version"], "| cards", len(recs), "| events", sum(r.get("n") or 0 for r in recs),
              "| source", pay.get("source"), "| left out", pay.get("left_out"))
        # each card against the workflow run's kept events (ds + halo_ds)
        sys.path.insert(0, r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app")
        from backend import xraymany  # noqa: E402
        wv = call("/api/rootcanal/workflow/%s?version=%s" % (wid, s["version"]))
        run = (wv.get("payload") or {}).get("run") or wv.get("run") or {}
        kept = xraymany.inside_by_gid(run) if run else {}
        oldroom = call("/api/extraction/%s?version=%s" % (s["room_artifact"], s.get("old_room_version", 6)))
        oldn = {r["gid"]: r.get("n") for r in (oldroom.get("payload") or {}).get("recordings") or []}
        bad = 0
        for r in recs:
            k = len(kept.get(r["gid"]) or []) if kept else None
            ok = k is None or k == r.get("n")
            bad += not ok
            print("   %-28s n %4s | run kept %4s | old room %4s %s" % (r.get("session_label"), r.get("n"), k, oldn.get(r["gid"]),
                                                                    "" if ok else "<-- MISMATCH"))
        print("   mismatches:", bad, "| run read:", bool(kept))
