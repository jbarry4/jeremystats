"""ML battery (Extraction Room 2.0) on the deduplicated data, 2026-11-19.
Waits for battery run 5's merged tables, builds amber bundle v2 through the
running Jarvis, submits the same run as r003 (all targets, views and models,
explain + drop-one-family, no shuffles) to the VACC, and follows it home."""
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8733"
BAT = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
NEED = [os.path.join(BAT, "merged", "measures.pkl"), os.path.join(BAT, "merged_around", "measures.pkl")]
T0 = time.mktime(time.strptime("2026-11-19 17:00", "%Y-%m-%d %H:%M"))
S = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(S, "er2_state.json")


def call(path, body=None, timeout=300):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def say(*a):
    print(time.strftime("%H:%M"), *a, flush=True)


st = json.load(open(STATE)) if os.path.exists(STATE) else {}
if "rid" not in st:
    say("waiting for the battery's merged tables")
    while not all(os.path.exists(p) and os.path.getmtime(p) > T0 for p in NEED):
        time.sleep(30)
    time.sleep(20)
    r = call("/api/er2/amber", {"source": BAT})
    say("amber:", r)
    while True:
        time.sleep(15)
        s = call("/api/er2/amber/status")
        if s.get("state") != "running":
            break
    say("amber", s.get("state"), "v%s" % s.get("version"), s.get("error") or "", "|", (s.get("log") or [])[-3:])
    if s.get("state") != "done":
        sys.exit(1)
    r = call("/api/er2/run", {"amber_version": s["version"], "where": "vacc", "n_shuffle": 0, "explain": True, "drop": True,
                              "note": "Rebuilt 2026-11-19 on battery run 5 (room v9: duplicate stamps removed, m1 on Lock); same as r003"})
    if not r.get("ok"):
        say("run refused:", r.get("error"))
        sys.exit(1)
    st = {"rid": r["run"]["rid"], "amber": s["version"], "n": r["run"]["n"]}
    json.dump(st, open(STATE, "w"))
    say("submitted", st)

rid, last = st["rid"], None
while True:
    time.sleep(240)
    try:
        r = call("/api/er2/run/%s/refresh" % rid, {}, timeout=900)
    except Exception as exc:                              # noqa: BLE001
        say("refresh retry:", exc)
        continue
    run = r.get("run") or {}
    line = "%s/%s answered, state %s" % (run.get("answered"), run.get("n"), run.get("state"))
    if line != last:
        say(line, "| slurm", json.dumps(r.get("slurm"))[:200])
        last = line
    if run.get("n") and run.get("answered") == run.get("n"):
        say("ALL ANSWERED", rid)
        break
    if not r.get("ok"):
        say("refresh error:", r.get("error"))
