# -*- coding: utf-8 -*-
"""Where the page's opening seconds actually go.

Written because "loading times surged" is a report, not a diagnosis, and
the obvious suspect is rarely the one. Times every request the app makes
before it is usable, and weighs what comes back -- so a route that is slow
because it is doing work is told apart from one that is slow because it is
sending a megabyte.

    python tools/load_cost.py                  against the harness server
    python tools/load_cost.py 8733             against a running Jarvis
    python tools/load_cost.py --field-costs    what each field of the
                                               registry payload weighs

Read-only. Makes the same requests the page makes.
"""
import json
import os
import sys
import time
import urllib.request

PORT = 8791
for a in sys.argv[1:]:
    if a.isdigit():
        PORT = int(a)
BASE = "http://127.0.0.1:%d" % PORT

#: Everything the page asks for before it can be used, in the order it asks.
BOOT = [
    "/api/catalog",
    "/api/profile",
    "/api/probes",
    "/api/panels",
    "/api/vacc/status",
    "/api/registry",
    "/api/toolkit/scopes",
]


def human(n):
    for u in ("B", "KB", "MB"):
        if abs(n) < 1024 or u == "MB":
            return "%.1f %s" % (n, u)
        n /= 1024.0
    return "%.1f MB" % n


def timed(path):
    t0 = time.time()
    try:
        with urllib.request.urlopen(BASE + path, timeout=300) as fh:
            raw = fh.read()
        return time.time() - t0, len(raw), raw
    except Exception as exc:                             # noqa: BLE001
        return time.time() - t0, 0, str(exc).encode()


def main():
    print("against %s" % BASE)
    print()
    print("%-26s %9s %11s" % ("request", "seconds", "bytes"))
    print("-" * 50)
    total_t = total_b = 0.0
    reg = None
    for path in BOOT:
        t, n, raw = timed(path)
        total_t += t
        total_b += n
        flag = "  <-- slowest so far" if t > 1.5 else ""
        print("%-26s %9.2f %11s%s" % (path, t, human(n), flag))
        if path == "/api/registry" and n:
            try:
                reg = json.loads(raw)
            except ValueError:
                pass
    print("-" * 50)
    print("%-26s %9.2f %11s" % ("in series", total_t, human(total_b)))
    print()
    print("The page issues most of these at once, so the wall clock is")
    print("nearer the slowest single request than the sum -- but every one")
    print("of them competes for the same server thread.")

    if reg and "--field-costs" in sys.argv:
        rows = []
        for p in (reg.get("tree") or []):
            for m in (p.get("mice") or []):
                rows.extend(m.get("sessions") or [])
        if rows:
            print()
            print("what each field of a session row weighs, across %d rows"
                  % len(rows))
            print("-" * 50)
            cost = {}
            for r in rows:
                for k, v in r.items():
                    cost[k] = cost.get(k, 0) + len(json.dumps({k: v}))
            for k, v in sorted(cost.items(), key=lambda kv: -kv[1])[:16]:
                print("   %-22s %10s   %5.1f%%"
                      % (k, human(v), 100.0 * v / max(1, sum(cost.values()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
