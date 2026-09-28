# -*- coding: utf-8 -*-
"""Measure how long starting up, switching views and opening tools take.

    python tools/perf_baseline.py            measure and compare to the stored run
    python tools/perf_baseline.py --save     measure and store this run as the baseline

Drives `web/_dev/perf.html` in headless Edge IN REAL TIME and prints what it
found. That is the whole reason this is not just another harness: the harness
runner uses `--virtual-time-budget`, which fast-forwards timers so a page
settles instantly, and every duration measured under it would be invented.
Here Edge runs on the wall clock, and the page POSTs its numbers back to
`/_dev/perf-report` -- a route registered by THIS tool on the in-process
server, so the application itself carries no such thing.

Timings are noisy in a way shapes are not, so the comparison is not a diff.
A number counts as a regression only when it is both 30% worse and at least
100 ms worse: a 12 ms view becoming 20 ms is noise, a 900 ms one becoming
1,300 ms is not.

Run it from PowerShell, for the same measured reason as everything else that
drives Edge here.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

BASELINE = os.path.join(APP, "web", "_dev", "baseline", "perf.json")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PROFILE = os.path.join(tempfile.gettempdir(), "jarvis-perf-profile")
WAIT_S = 420

# How much worse counts as worse. Both must hold.
REL, ABS_MS = 0.30, 100


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve(port, box, got, ready):
    """Bring the server up the way start.py does, and time it.

    Not the way the harness suite does. The suite deliberately skips the warm
    start so that it measures the store rather than a cache, which is right
    for a test and wrong for this: a person never meets a server without it,
    and timing a cold registry read that nobody ever waits for would put the
    effort in the wrong place. The catalogue index and the warm start are
    both part of what "start-up" means, so both are timed.
    """
    t0 = time.time()
    from flask import request, jsonify
    from backend.app import app, refresh_catalog, warm_start
    box["import_s"] = time.time() - t0

    t1 = time.time()
    refresh_catalog()
    box["catalog_s"] = time.time() - t1
    warm_start()

    @app.route("/_dev/perf-report", methods=["POST"])
    def _perf_report():                       # noqa: D401
        box["report"] = request.get_json(force=True, silent=True)
        got.set()
        return jsonify({"ok": True})

    box["server_s"] = time.time() - t0
    ready.set()
    app.run(host="127.0.0.1", port=port, debug=False,
            use_reloader=False, threaded=True)


def run_once():
    port = free_port()
    box, got, ready = {}, threading.Event(), threading.Event()
    threading.Thread(target=serve, args=(port, box, got, ready),
                     daemon=True).start()
    if not ready.wait(300):
        raise SystemExit("the server did not come up within 300 s")
    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)

    # A fresh profile every time: a locked one makes Edge exit at once and
    # produce nothing, which is how two comparisons in this project once read
    # as clean when neither page had run.
    import shutil
    shutil.rmtree(PROFILE, ignore_errors=True)
    url = "http://127.0.0.1:%d/_dev/perf.html" % port
    edge = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu-compositing",
         "--user-data-dir=" + PROFILE, "--no-first-run",
         "--no-default-browser-check", "--window-size=1600,1000", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not got.wait(WAIT_S):
            raise SystemExit("perf.html sent nothing within %ds. Edge may not "
                             "have started; nothing was measured." % WAIT_S)
    finally:
        edge.kill()
    rep = box.get("report")
    if not rep or not rep.get("boot"):
        raise SystemExit("perf.html reported, but with no boot measurement.")
    rep["server"] = {"import_ms": box.get("import_s", 0) * 1000,
                     "catalog_ms": box.get("catalog_s", 0) * 1000,
                     "total_ms": box.get("server_s", 0) * 1000}
    return rep


def flat(rep):
    """Every number worth comparing, by a stable name."""
    b = rep.get("boot") or {}
    s = rep.get("server") or {}
    out = {
        "server: ready to serve": s.get("total_ms"),
        "server: imports": s.get("import_ms"),
        "server: script index": s.get("catalog_ms"),
        "boot: interactive": b.get("interactive"),
        "boot: settled": b.get("settled"),
        "boot: first contentful paint": b.get("firstContentfulPaint"),
        "boot: main thread blocked": b.get("blocked"),
    }
    for group, key in (("views", "cold"), ("warm", "warm"), ("tools", "tool")):
        for r in rep.get(group) or []:
            out["%s %s: settled" % (key, r["label"])] = r.get("settled")
            out["%s %s: paint" % (key, r["label"])] = r.get("paint")
    return {k: v for k, v in out.items() if isinstance(v, (int, float))}


def show(rep):
    s = rep.get("server") or {}
    print("server: %5d ms to serve  (imports %d, script index %d)"
          % (s.get("total_ms", 0), s.get("import_ms", 0),
             s.get("catalog_ms", 0)))
    b = rep["boot"]
    print("boot: interactive %5d ms, settled %5d ms, %d scripts %d kB, "
          "%d api %d kB, blocked %d ms"
          % (b["interactive"], b["settled"], b["scripts"], b["scriptKB"],
             b["api"], b["apiKB"], b["blocked"]))
    for e in b.get("apiSlowest") or []:
        print("   %6d ms %5d kB  %s" % (e["ms"], e["kb"], e["url"]))
    for group, title in (("views", "first visit"), ("warm", "second visit"),
                         ("tools", "ToolKit")):
        rows = rep.get(group) or []
        if not rows:
            continue
        print("\n%s" % title)
        for r in sorted(rows, key=lambda r: -r["settled"]):
            slow = r["slowest"][0] if r.get("slowest") else None
            print("  %-22s paint %5d  settled %6d  blocked %5d  api %2d  %s"
                  % (r["label"][:22], r["paint"], r["settled"],
                     r.get("blocked", 0), r["api"],
                     ("%s %dms" % (slow["url"], slow["ms"])) if slow else ""))


def main():
    save = "--save" in sys.argv[1:]
    print("measuring in real time; this takes a few minutes...", flush=True)
    rep = run_once()
    show(rep)

    if save or not os.path.exists(BASELINE):
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, indent=1)
        print("\nbaseline written: %s" % os.path.relpath(BASELINE, APP))
        return 0

    with open(BASELINE, encoding="utf-8") as fh:
        was = flat(json.load(fh))
    now = flat(rep)
    worse, better = [], []
    for k in sorted(set(was) & set(now)):
        a, b = was[k], now[k]
        if b - a >= ABS_MS and b >= a * (1 + REL):
            worse.append((k, a, b))
        elif a - b >= ABS_MS and b <= a * (1 - REL):
            better.append((k, a, b))
    print()
    for k, a, b in better:
        print("  faster  %-40s %6d -> %6d ms" % (k, a, b))
    for k, a, b in worse:
        print("  SLOWER  %-40s %6d -> %6d ms" % (k, a, b))
    print("\n%d faster, %d slower (a change counts when it is both %d%% and "
          "%d ms)." % (len(better), len(worse), REL * 100, ABS_MS))
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main())
