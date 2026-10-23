# -*- coding: utf-8 -*-
"""Measure how long starting up, switching views and opening tools take.

    python tools/perf_baseline.py            measure and compare to the stored run
    python tools/perf_baseline.py --save     measure and store this run as the baseline
    python tools/perf_baseline.py --runs 5   the median of five runs (default three)

Measuring a slower computer, and Jarvis Light (2026-10-21):

    --lite            measure with Jarvis Light on (the frame gets ?lite=on)
    --throttle 4      slow the page's CPU four times over (DevTools), and draw
                      at a 1.5x screen scale, like a laptop at 150 %
    --warm-browser    load everything once first and measure the SECOND
                      load in the same browser profile: what somebody who
                      opened Jarvis yesterday meets (HTTP cache, stashes)
    --json PATH       also write the median report to PATH
    --baseline PATH   compare against PATH instead of the stored baseline

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


def _devtools(dbg):
    """The page target's DevTools connection, once Edge has opened one."""
    import urllib.request
    sys.path.insert(0, HERE)
    from ui_shots import CDP
    end = time.time() + 30
    while time.time() < end:
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/list" % dbg, timeout=2) as r:
                for t in json.loads(r.read().decode()):
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return CDP(t["webSocketDebuggerUrl"])
        except Exception:                                # noqa: BLE001
            pass
        time.sleep(0.3)
    raise SystemExit("Edge did not open DevTools; nothing was measured.")


def run_once(opts=None):
    opts = opts or {}
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
    query = "?lite=on" if opts.get("lite") else ""
    url = "http://127.0.0.1:%d/_dev/perf.html%s" % (port, query)
    throttle = float(opts.get("throttle") or 0)
    warm = bool(opts.get("warm_browser"))
    if not throttle and not warm:
        edge = subprocess.Popen(
            [EDGE, "--headless=new", "--disable-gpu-compositing",
             "--user-data-dir=" + PROFILE, "--no-first-run",
             "--no-default-browser-check", "--window-size=1600,1000", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not got.wait(WAIT_S):
                raise SystemExit("perf.html sent nothing within %ds. Edge may "
                                 "not have started; nothing was measured."
                                 % WAIT_S)
        finally:
            edge.kill()
    else:
        # Driven over DevTools, on the wall clock: the CPU slowed down and the
        # screen scaled the way a laptop's is, and -- for --warm-browser --
        # one full run first whose report is thrown away, so the measured
        # one meets a browser that has been here before.
        dbg = free_port()
        edge = subprocess.Popen(
            [EDGE, "--headless=new", "--disable-gpu-compositing",
             "--user-data-dir=" + PROFILE, "--no-first-run",
             "--no-default-browser-check", "--window-size=1600,1000",
             "--remote-allow-origins=*", "--remote-debugging-port=%d" % dbg,
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            cdp = _devtools(dbg)
            cdp.call("Page.enable")
            # Onto the app's own origin first, so the measured page loads in
            # the renderer the throttle is set on: from about:blank the
            # navigation swapped processes and the boot ran unthrottled.
            cdp.call("Page.navigate", {
                "url": "http://127.0.0.1:%d/img/jarvis.svg" % port})
            time.sleep(1.0)
            if throttle:
                cdp.call("Emulation.setCPUThrottlingRate", {"rate": throttle})
                cdp.call("Emulation.setDeviceMetricsOverride", {
                    "width": 1600, "height": 1000, "deviceScaleFactor": 1.5,
                    "mobile": False})
            if warm:
                cdp.call("Page.navigate", {"url": url})
                if not got.wait(WAIT_S):
                    raise SystemExit("the priming run sent nothing within %ds."
                                     % WAIT_S)
                got.clear()
                box.pop("report", None)
            cdp.call("Page.navigate", {"url": url})
            if not got.wait(WAIT_S):
                raise SystemExit("perf.html sent nothing within %ds; nothing "
                                 "was measured." % WAIT_S)
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
        "idle: main thread blocked": (rep.get("idle") or {}).get("blocked"),
    }
    for group, key in (("views", "cold"), ("warm", "warm"), ("tools", "tool")):
        for r in rep.get(group) or []:
            out["%s %s: settled" % (key, r["label"])] = r.get("settled")
            out["%s %s: paint" % (key, r["label"])] = r.get("paint")
            out["%s %s: first row" % (key, r["label"])] = r.get("firstRow")
            out["%s %s: last row" % (key, r["label"])] = r.get("lastRow")
    return {k: v for k, v in out.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


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
    if b.get("heapMB") is not None:
        print("   heap %d MB, %d elements" % (b["heapMB"], b.get("nodes") or 0))
    i = rep.get("idle")
    if i:
        print("idle %ds: %d running animations (%d infinite), blocked %d ms"
              % (i["ms"] / 1000, i["animations"], i["infinite"], i["blocked"]))
    for group, title in (("views", "first visit"), ("warm", "second visit"),
                         ("tools", "ToolKit")):
        rows = rep.get(group) or []
        if not rows:
            continue
        print("\n%s" % title)
        for r in sorted(rows, key=lambda r: -r["settled"]):
            slow = r["slowest"][0] if r.get("slowest") else None
            fill = ""
            if r.get("firstRow") is not None:
                fill = "  rows %d: first %d last %d" % (
                    r.get("rows") or 0, r["firstRow"], r.get("lastRow") or 0)
            heap = ("  heap %d MB" % r["heapMB"]) if r.get("heapMB") else ""
            print("  %-22s paint %5d  settled %6d  blocked %5d  api %2d%s%s  %s"
                  % (r["label"][:22], r["paint"], r["settled"],
                     r.get("blocked", 0), r["api"], fill, heap,
                     ("%s %dms" % (slow["url"], slow["ms"])) if slow else ""))


def median_of(reps):
    """One report whose every number is the median of the runs.

    A single run was too noisy to judge a view by -- the same view measured
    twice moved by more than the thresholds below. Rows are matched by label;
    a number missing from a run is left out of that one's median rather
    than counted as zero.
    """
    import copy
    import statistics

    def med(vals):
        vals = [v for v in vals if isinstance(v, (int, float))]
        return statistics.median(vals) if vals else None

    out = copy.deepcopy(reps[0])
    for part in ("boot", "server", "idle"):
        for k, v in (out.get(part) or {}).items():
            if isinstance(v, (int, float)):
                out[part][k] = med([(r.get(part) or {}).get(k) for r in reps])
    for group in ("views", "warm", "tools"):
        for row in out.get(group) or []:
            same = [x for r in reps for x in (r.get(group) or [])
                    if x.get("label") == row.get("label")]
            for k, v in row.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    row[k] = med([x.get(k) for x in same])
    out["runs"] = len(reps)
    return out


def run_many(n, passthrough=()):
    """`n` runs, each in its own process, and their median.

    Its own process because a second run in this one would measure nothing
    true: the server's imports are already paid, and Flask refuses to add
    the report route to an app that has served a request.
    """
    reps = []
    for i in range(n):
        print("  run %d of %d..." % (i + 1, n), flush=True)
        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            res = subprocess.run([sys.executable, os.path.abspath(__file__),
                                  "--once", tmp] + list(passthrough))
            if res.returncode != 0:
                raise SystemExit("run %d failed; nothing compared." % (i + 1))
            with open(tmp, encoding="utf-8") as fh:
                reps.append(json.load(fh))
        finally:
            os.remove(tmp)
    return median_of(reps)


def _opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def main():
    args = sys.argv[1:]
    opts = {"lite": "--lite" in args,
            "throttle": float(_opt(args, "--throttle", 0) or 0),
            "warm_browser": "--warm-browser" in args}
    passthrough = (["--lite"] if opts["lite"] else []) \
        + (["--throttle", str(opts["throttle"])] if opts["throttle"] else []) \
        + (["--warm-browser"] if opts["warm_browser"] else [])
    if "--once" in args:
        rep = run_once(opts)
        rep["options"] = opts
        with open(args[args.index("--once") + 1], "w", encoding="utf-8") as fh:
            json.dump(rep, fh)
        return 0
    save = "--save" in args
    n = int(args[args.index("--runs") + 1]) if "--runs" in args else 3
    print("measuring in real time, median of %d runs%s; this takes a few "
          "minutes each..." % (n, (" (" + " ".join(passthrough) + ")")
                               if passthrough else ""), flush=True)
    rep = run_many(n, passthrough)
    rep["options"] = opts
    show(rep)
    if _opt(args, "--json"):
        with open(_opt(args, "--json"), "w", encoding="utf-8",
                  newline="\n") as fh:
            json.dump(rep, fh, indent=1)
        print("\nreport written: %s" % _opt(args, "--json"))

    against = _opt(args, "--baseline") or BASELINE
    if against != BASELINE and not os.path.exists(against):
        raise SystemExit("no such baseline: %s" % against)
    if save or not os.path.exists(against):
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, indent=1)
        print("\nbaseline written: %s" % os.path.relpath(BASELINE, APP))
        return 0

    with open(against, encoding="utf-8") as fh:
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
