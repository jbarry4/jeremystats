# -*- coding: utf-8 -*-
"""Where the page's main thread goes, on a slow computer, while nobody
touches it -- or while one view sits open.

    python tools/perf_profile.py                    10 s idle on the first screen
    python tools/perf_profile.py --view toolkit     10 s with ToolKit open
    python tools/perf_profile.py --throttle 4 --seconds 20 --lite

perf_baseline.py says THAT a view is slow ("blocked 13 s"); this says WHY:
DevTools' sampling profiler runs over the window and the self time is added
up by function and by file. Real time, real Edge, the app on a private port
with preference writes intercepted (tools/ui_shots.py's CDP client), so a
run changes nothing anybody else sees.

Run it from PowerShell, like everything here that drives Edge.
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

from ui_shots import CDP, EDGE, free_port, port_open, serve  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", default="")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--throttle", type=float, default=4.0)
    ap.add_argument("--lite", action="store_true")
    ap.add_argument("--settle", type=float, default=8.0,
                    help="seconds to wait after the view opens, before profiling")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--json", default="")
    ap.add_argument("--css", default="",
                    help="CSS added to the page before profiling, to test "
                         "what turning one thing off is worth")
    ap.add_argument("--boot", action="store_true",
                    help="profile the start-up itself, from navigation to "
                         "the boot screen going, instead of a stretch of idle")
    ap.add_argument("--warm-browser", action="store_true",
                    help="load once first, then profile the second load")
    a = ap.parse_args()

    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    port = free_port()
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    t0 = time.time()
    while not port_open(port):
        if time.time() - t0 > 90:
            print("the app did not start")
            return 2
        time.sleep(0.25)

    dbg = free_port()
    profile = tempfile.mkdtemp(prefix="jarvis-prof-")
    edge = subprocess.Popen([
        EDGE, "--headless=new", "--disable-gpu-compositing", "--no-first-run",
        "--no-default-browser-check", "--remote-allow-origins=*",
        "--remote-debugging-port=%d" % dbg, "--user-data-dir=" + profile,
        "--window-size=1600,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws = None
        end = time.time() + 30
        while time.time() < end and not ws:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json/list" % dbg, timeout=2) as r:
                    for t in json.loads(r.read().decode()):
                        if t.get("type") == "page":
                            ws = t.get("webSocketDebuggerUrl")
                            break
            except Exception:                            # noqa: BLE001
                time.sleep(0.3)
        cdp = CDP(ws)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Fetch.enable", {"patterns": [
            {"urlPattern": "*/api/prefs*", "requestStage": "Request"}]})
        base = "http://127.0.0.1:%d" % port
        cdp.call("Page.navigate", {"url": base + "/img/jarvis.svg"})
        cdp.pump(1.0)
        if a.throttle and a.throttle > 1:
            cdp.call("Emulation.setCPUThrottlingRate", {"rate": a.throttle})
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 1600, "height": 1000, "deviceScaleFactor": 1.5,
            "mobile": False})
        q = "menu=0&warm=0" + ("&lite=on" if a.lite else "")
        ready = ("typeof setView === 'function' && typeof BARRY === 'object'"
                 " && BARRY.state.catalog"
                 " && (!document.getElementById('boot') || "
                 "document.getElementById('boot').classList.contains('gone'))")
        if a.warm_browser:
            cdp.call("Page.navigate", {"url": base + "/?" + q})
            cdp.until(ready, limit=180)
            cdp.pump(3.0)
            cdp.call("Page.navigate", {"url": base + "/img/jarvis.svg"})
            cdp.pump(1.0)
        if a.boot:
            cdp.call("Profiler.enable")
            cdp.call("Profiler.setSamplingInterval", {"interval": 200})
            cdp.call("Profiler.start")
            t_nav = time.time()
        cdp.call("Page.navigate", {"url": base + "/?" + q})
        if not cdp.until(ready, limit=180):
            print("the boot screen never went")
        if a.boot:
            boot_s = time.time() - t_nav
            prof = cdp.call("Profiler.stop", timeout=120)["profile"]
            timing = cdp.js("(function(){var n=performance.getEntriesByType('navigation')[0]||{};"
                            "var r=performance.getEntriesByType('resource');"
                            "var js=r.filter(function(e){return /\\.js(\\?|$)/.test(e.name);});"
                            "return {dcl:n.domContentLoadedEventEnd, load:n.loadEventEnd,"
                            " js:js.length, jsCached:js.filter(function(e){return e.transferSize===0;}).length,"
                            " jsKB:Math.round(js.reduce(function(a,e){return a+(e.transferSize||0);},0)/1024)};})()")
            print("boot: %.1f s wall to the boot screen going; DOMContentLoaded %d ms,"
                  " %s scripts (%s from cache, %s kB over the wire)"
                  % (boot_s, timing.get("dcl") or 0, timing.get("js"),
                     timing.get("jsCached"), timing.get("jsKB")))
            a.seconds = boot_s
            return _report(a, prof)
        if a.view:
            cdp.js("setView(%s)" % json.dumps(a.view))
        if a.css:
            cdp.js("(function(){var s=document.createElement('style');"
                   "s.textContent=%s;document.head.appendChild(s);})()"
                   % json.dumps(a.css))
        cdp.pump(a.settle)

        # What is moving on its own right now: every running animation, by
        # name and by the element it is on.
        anims = cdp.js(
            "(document.getAnimations ? document.getAnimations() : [])"
            ".filter(function (x) { return x.playState === 'running'; })"
            ".map(function (x) { var t = x.effect && x.effect.target;"
            " var it = x.effect && x.effect.getTiming ? x.effect.getTiming().iterations : 0;"
            " return (x.animationName || x.transitionProperty || 'script')"
            " + (it === Infinity ? ' (loops)' : '') + '  on  '"
            " + (t ? (t.tagName.toLowerCase() + (t.id ? '#' + t.id : '')"
            " + (t.getAttribute && t.getAttribute('class') ? '.' + String(t.getAttribute('class')).trim().split(/\\s+/).join('.') : '')) : '?'); })")
        counts = collections.Counter(anims or [])
        print("running animations: %d" % len(anims or []))
        for k, n in counts.most_common(15):
            print("  %3d x %s" % (n, k))

        cdp.call("Profiler.enable")
        cdp.call("Profiler.setSamplingInterval", {"interval": 500})
        cdp.call("Profiler.start")
        cdp.pump(a.seconds)
        prof = cdp.call("Profiler.stop", timeout=120)["profile"]
    finally:
        try:
            edge.kill()
        except Exception:                                # noqa: BLE001
            pass
    return _report(a, prof)


def _report(a, prof):
    """Self time, by file and by function, of one sampled profile."""
    nodes = {n["id"]: n for n in prof["nodes"]}
    # Self time per node from the samples and their deltas.
    self_us = collections.Counter()
    samples, deltas = prof.get("samples") or [], prof.get("timeDeltas") or []
    for i, sid in enumerate(samples):
        dt = deltas[i + 1] if i + 1 < len(deltas) else 0
        self_us[sid] += max(0, dt)
    by_fn = collections.Counter()
    by_file = collections.Counter()
    total = 0
    for nid, us in self_us.items():
        cf = nodes[nid]["callFrame"]
        name = cf.get("functionName") or "(anonymous)"
        url = cf.get("url") or ""
        short = url.split("/")[-1].split("?")[0] or "(native)"
        if name in ("(idle)", "(program)", "(garbage collector)", "(root)"):
            if name != "(idle)":
                by_fn[name] += us
                by_file[name] += us
                total += us
            continue
        key = "%s  %s:%d" % (name, short, cf.get("lineNumber", 0) + 1)
        by_fn[key] += us
        by_file[short] += us
        total += us
    span = a.seconds * 1e6
    print("busy %.0f ms of %.1f s (%.0f%%) with %s, throttle %sx%s"
          % (total / 1000, a.seconds, 100 * total / span,
             "the start-up" if a.boot else
             (("view " + a.view) if a.view else "the first screen"),
             a.throttle, ", Jarvis Light" if a.lite else ""))
    print("\nby file")
    for k, us in by_file.most_common(15):
        print("  %7.0f ms  %s" % (us / 1000, k))
    print("\nby function (self time)")
    for k, us in by_fn.most_common(a.top):
        print("  %7.0f ms  %s" % (us / 1000, k))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"busy_ms": total / 1000, "by_file": by_file.most_common(40),
                       "by_fn": by_fn.most_common(200)}, fh, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
