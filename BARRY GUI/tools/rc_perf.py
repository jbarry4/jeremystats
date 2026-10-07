# -*- coding: utf-8 -*-
"""How long Root Canal takes to answer a change, on the wall clock.

    python tools/rc_perf.py            every check, against the budget
    python tools/rc_perf.py --runs 5   five presses each (default 3); the
                                       first is judged, the rest shown

Reported 2026-10-06: "delay or no update when clusters are changed". The
picture redraws in tens of milliseconds; the wait is the request that
refits. So this times those requests -- the same routes the panel calls, in
process, on this machine's real reads -- and holds them to a budget:

    Single, a press      under 1 s
    Pooled, a press      under 2 s

Run in real time, never under the harness runner, whose virtual clock
invents every duration (memory: virtual time cannot time). Reads nothing
it does not already have cached and writes nothing anywhere: the member
rows cache it may warm is cache.
"""
import os
import statistics
import sys
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
os.chdir(APP)
warnings.filterwarnings("ignore")

BUDGET_S = {"single": 1.0, "pooled": 2.0, "open": 4.0}
# Opening a set is not a press: it is the read coming off disk and its
# first measurement, and it shows its own progress. Its budget is its own.
LOOK_S = 3.0      # how long a person looks at a picture before the next press


def main():
    runs = 3
    if "--runs" in sys.argv:
        runs = max(1, int(sys.argv[sys.argv.index("--runs") + 1]))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import backend.app as A
    c = A.app.test_client()
    cands = [x for x in A._rootcanal_pool_candidates()
             if not x["banked"] and x.get("here")]
    if not cands:
        print("No cached Root Canal reads on this machine: nothing to time.")
        return 0
    bad = []

    def timed(what, kind, fn):
        ts = []
        out = None
        for _ in range(runs):
            t0 = time.perf_counter()
            out = fn()
            ts.append(time.perf_counter() - t0)
        # The FIRST press is the one a person waits for: a repeat of the
        # same settings is answered from what the first one kept. Judged on
        # the first; the repeats are shown beside it.
        first, again = ts[0], (statistics.median(ts[1:]) if len(ts) > 1
                               else ts[0])
        over = first > BUDGET_S[kind]
        if over:
            bad.append(what)
        err = (out or {}).get("error") if isinstance(out, dict) else None
        print("  %-48s first %5.2f s, again %5.2f s  (budget %.0f s)%s%s" % (
            what, first, again, BUDGET_S[kind], "  OVER" if over else "",
            "  ERROR: " + err if err else ""))
        if err:
            bad.append(what + " (error)")
        return out

    # The largest cached read: the slowest Single there is here.
    big = max(cands, key=lambda x: x.get("n") or 0)
    body = {"entry_id": big["entry_id"], "read": big["read"]}
    print("Single: %s, %s events" % (big["session_label"], big.get("n")))
    timed("open the set (the read off disk, first fit)", "open",
          lambda: c.post("/api/rootcanal/fit", json=body).get_json())
    # A person looks at the picture before pressing anything; the other
    # preset filters are measured in the background meanwhile.
    time.sleep(LOOK_S)
    for k in (1, 3, 6):
        timed("k = %d" % k, "single", lambda k=k: c.post(
            "/api/rootcanal/fit", json=dict(body, k=k)).get_json())
    timed("only events on all 3 axes", "single", lambda: c.post(
        "/api/rootcanal/fit", json=dict(body, complete_only=True)).get_json())
    timed("a cluster relabelled", "single", lambda: c.post(
        "/api/rootcanal/fit", json=dict(body, cluster_calls={"0": "ied"}))
        .get_json())
    for f in ("none", "ds"):
        timed("filter: %s" % f, "single", lambda f=f: c.post(
            "/api/rootcanal/fit", json=dict(body, filt=f)).get_json())
    fit = c.post("/api/rootcanal/fit", json=body).get_json()
    miss = [e["i"] for e in fit.get("events") or []
            if e["amp_uV"] is not None and e["hw_ms"] is None]
    if miss:
        timed("search the %d with no half-width again" % len(miss), "single",
              lambda: c.post("/api/rootcanal/fit",
                             json=dict(body, retry=miss)).get_json())

    mem = [{"key": x["key"]} for x in cands]
    print("Pooled: %d recordings" % len(mem))
    pb = {"members": mem}
    timed("first pool", "pooled",
          lambda: c.post("/api/rootcanal/pool/fit", json=pb).get_json())
    for k in (1, 3, 6):
        timed("k = %d" % k, "pooled", lambda k=k: c.post(
            "/api/rootcanal/pool/fit", json=dict(pb, k=k)).get_json())
    timed("only events on all 3 axes", "pooled", lambda: c.post(
        "/api/rootcanal/pool/fit", json=dict(pb, complete_only=True))
        .get_json())
    first = c.post("/api/rootcanal/pool/fit", json=pb).get_json()
    mk = ((first.get("members") or [{}])[0]).get("mouse_key")
    if mk:
        timed("focus on one mouse", "pooled", lambda: c.post(
            "/api/rootcanal/pool/fit",
            json=dict(pb, focus={"mouse_key": mk})).get_json())
    timed("a cluster relabelled", "pooled", lambda: c.post(
        "/api/rootcanal/pool/fit", json=dict(pb, cluster_calls={"0": "ied"}))
        .get_json())

    print("")
    if bad:
        print("OVER BUDGET: " + "; ".join(bad))
        return 1
    print("every press inside its budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
