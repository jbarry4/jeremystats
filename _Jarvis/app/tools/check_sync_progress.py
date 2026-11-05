# -*- coding: utf-8 -*-
"""Does a running sync say where it has got to?

The browser harness cannot answer this. web/_dev/digest.html runs under
Chromium's --virtual-time-budget, where the page's timers fast-forward while
the server carries on at the real clock -- so a poll loop in there either
outruns the sync (nine thousand samples taken inside the pull's first table)
or loses the lock to the background pass, which fires every twenty seconds
and returns "a sync is already running" rather than queueing.

Here the clock is real, so the question is answerable: start a sync in one
thread, poll /api/sync/progress from another, and look at what it said.

What has to hold:

  * every sample names a phase, and the phases are ones we recognise
  * at least one names the TABLE it is on -- "pushing" for four seconds is
    a spinner, "pushing error_marks" is progress
  * `done` never goes backwards inside a sync, and never passes `of`
  * the pull is described, not skipped. It is the slow half -- fifteen round
    trips -- and it used to report the single word "pulling" for all of them

Run it against a server that is already up:

    python tools/check_sync_progress.py [http://127.0.0.1:8791]
"""
import json
import sys
import threading
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1
        else "http://127.0.0.1:8791").rstrip("/")

KNOWN = {"starting", "pulling", "pulled", "tombstones", "pushing",
         "files", "idle"}

fails = []


def ck(name, cond, detail=""):
    print(("ok    " if cond else "FAIL  ") + name
          + ("" if cond or not detail else "   [%s]" % detail))
    if not cond:
        fails.append(name)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.load(r)


def post(path, body=None):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main():
    print("== a sync in flight, described ==")
    shape = get("/api/sync/progress")
    ck("the route answers", shape.get("ok") is True, shape)
    step = shape.get("step") or {}
    for k in ("phase", "table", "done", "of", "running"):
        ck("the step has a %s" % k, k in step, sorted(step))

    result = {}

    def run_sync():
        # Retried, because the background loop may hold the lock. It returns
        # rather than queueing, on purpose -- two syncs at once is worse than
        # a late one -- so getting a real sync means asking again.
        for _ in range(8):
            try:
                got = post("/api/cloud/sync", {})
            except Exception as exc:                     # noqa: BLE001
                result["error"] = str(exc)
                return
            last = got.get("last") or {}
            if "already running" not in str(last.get("error") or ""):
                result["last"] = last
                return
            result["declined"] = result.get("declined", 0) + 1
            time.sleep(0.4)
        result["last"] = {}

    samples = []
    worker = threading.Thread(target=run_sync)
    worker.start()
    # 60ms is fine here: the sync is seconds long on the real clock, so this
    # takes fifty-odd samples of it rather than nine thousand of its first
    # instant.
    while worker.is_alive() or len(samples) < 3:
        try:
            samples.append((get("/api/sync/progress").get("step") or {}))
        except Exception:                                # noqa: BLE001
            pass
        time.sleep(0.06)
        if len(samples) > 1200:
            break
    worker.join(timeout=300)

    if result.get("declined"):
        print("  (%d request(s) found the lock held)" % result["declined"])
    live = [s for s in samples if s.get("running")]
    print("  %d sample(s), %d of them mid-sync" % (len(samples), len(live)))

    seq = []
    for s in live:
        tag = s.get("phase") + (":" + s["table"] if s.get("table") else "")
        if not seq or seq[-1] != tag:
            seq.append(tag)
    print("  " + " -> ".join(seq[:24]))
    if len(seq) > 24:
        print("  ... and %d more" % (len(seq) - 24))

    ck("a running sync was observed", len(live) > 0, len(samples))
    ck("every phase is one we recognise",
       all((s.get("phase") in KNOWN) for s in live),
       sorted({s.get("phase") for s in live} - KNOWN))
    ck("at least one sample names the table it is on",
       any(s.get("table") for s in live),
       "none of %d" % len(live))
    # The pull is the slow half and the reason this exists.
    pull_tables = {s.get("table") for s in live
                   if s.get("phase") == "pulling" and s.get("table")}
    ck("the pull names the tables it is fetching",
       len(pull_tables) >= 2, sorted(pull_tables))
    push_tables = {s.get("table") for s in live
                   if s.get("phase") == "pushing" and s.get("table")}
    ck("so does the push", len(push_tables) >= 2, sorted(push_tables))

    # Monotonic within a sync. A reset to zero is the next sync starting,
    # which is not a fault; a step backwards mid-push would be.
    back = 0
    last_done = -1
    for s in live:
        d = s.get("done") or 0
        if d < last_done and s.get("phase") not in ("starting", "pulling"):
            back += 1
        last_done = d if d >= last_done else d
    ck("the count never goes backwards inside a phase", back == 0, back)
    over = [s for s in live if (s.get("done") or 0) > (s.get("of") or 0)]
    ck("the bar never runs past its own end", not over,
       over[:1])

    ck("the sync itself finished", "error" not in result, result.get("error"))
    print("\n" + ("%d FAILURE(S)" % len(fails) if fails
                  else "all checks passed"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
