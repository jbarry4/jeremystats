# -*- coding: utf-8 -*-
"""How many requests this computer's Jarvis has made to Supabase, and who
made them -- read from the running app, not predicted.

The free tier is priced in requests (constitution §11): each one is about a
kilobyte of headers and a gateway log line whatever it carries. Every
request passes through `Cloud._call`, which counts it (`cloud.meter`), and
`/api/cloud/status` serves the count. This prints it.

    python tools/cloud_meter.py              the last hour
    python tools/cloud_meter.py 600          the last ten minutes
    python tools/cloud_meter.py 3600 8734    a Jarvis on a particular port

Read-only, and it makes no request to Supabase itself: it asks the local
server what it has already done. The count starts when that Jarvis started.
"""
import json
import sys
import urllib.request

FIRST_PORT = 8733          # start.py takes the first free port from here
SPAN = 40


def ask(port, window):
    url = "http://127.0.0.1:%d/api/cloud/status?window=%d" % (port, window)
    with urllib.request.urlopen(url, timeout=3) as res:
        return json.loads(res.read().decode("utf-8"))


def main():
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 3600
    ports = ([int(sys.argv[2])] if len(sys.argv) > 2
             else range(FIRST_PORT, FIRST_PORT + SPAN))
    for port in ports:
        try:
            got = ask(port, window)
        except Exception:                                # noqa: BLE001
            continue
        req = got.get("requests")
        if req is None:
            print("Jarvis on port %d is running code from before the meter "
                  "(2026.09.29.1). Restart it." % port)
            return 2
        covers = req.get("covers_s") or 0
        print("Jarvis on port %d, machine %s" % (port, got.get("machine")))
        print("  pace: %s s  (%s)" % (got.get("pull_interval_s"),
                                      got.get("pace")))
        print("  %d request(s) to Supabase in the last %d s%s, %d failed, "
              "%.1f KB back"
              % (req["requests"], req["window_s"],
                 "" if covers >= 0.9 * req["window_s"]
                 else " (running for only %d s)" % covers,
                 req.get("failed") or 0, (req.get("bytes") or 0) / 1024.0))
        if req["requests"]:
            per_h = req["requests"] * 3600.0 / max(60, min(covers or 1,
                                                          req["window_s"]))
            print("  about %d an hour, %d a day at this rate"
                  % (per_h, per_h * 24))
        for title, key in (("by caller", "by_caller"), ("by table", "by_table")):
            rows = req.get(key) or []
            if not rows:
                continue
            print("  %s:" % title)
            for r in rows[:15]:
                print("    %6d  %8.1f KB  %s" % (r["n"], r["bytes"] / 1024.0,
                                                  r["key"]))
        return 0
    print("No Jarvis answering on ports %d-%d." % (FIRST_PORT,
                                                    FIRST_PORT + SPAN - 1))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
