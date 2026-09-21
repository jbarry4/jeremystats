# -*- coding: utf-8 -*-
"""Start a server on the harness port and run the suite against it.

`run_harnesses.py` drives real browser pages against a live server, and it
looks for one on 127.0.0.1:8791 -- while `start.py` takes the first free port
from 8733 up. So running the suite has always meant remembering to start a
second Jarvis on the right port first, and a suite pointed at nothing reports
"0 ok, 0 fail" for every page, which reads exactly like a clean sweep.

This holds the server for exactly as long as the run takes and no longer.

    python tools/harness_run.py              every harness
    python tools/harness_run.py motion theme just the ones whose names match

Run it from PowerShell. Measured: under a bash shell Edge's --dump-dom
writes nothing on this machine, so every page reports zero checks and the
whole suite passes vacuously.

The server runs in a thread of this process rather than a child, so there is
no second interpreter to leave behind if the run is interrupted -- and with
`use_reloader=False` (which start.py also sets) there is no watcher thread
holding the port either. A backend edit therefore needs a fresh run of this
script; it cannot be picked up mid-suite.
"""
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

# The port run_harnesses.py looks for by default. Not insisted on: two
# people (or two agents) in one clone both want to run the suite, and a run
# that attaches to somebody else's server is a run against somebody else's
# code -- with `use_reloader=False` on both, their server is whatever the
# files said when it started. That failure is silent and looks like a pass,
# so this takes a port of its own rather than sharing one.
PORT = 8791

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass


def port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def free_port(preferred=PORT, span=40):
    for port in range(preferred, preferred + span):
        if port_open(port):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    return 0


def main():
    port = free_port()
    if not port:
        print("no free port in %d..%d." % (PORT, PORT + 39))
        return 2

    # Quiet: the suite makes thousands of requests and the access log is both
    # useless here and, on Windows, a lock every thread queues on.
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    from backend.app import app

    def serve():
        app.run(host="127.0.0.1", port=port, debug=False,
                threaded=True, use_reloader=False)

    threading.Thread(target=serve, daemon=True).start()

    for _ in range(200):                         # 20 s, then give up loudly
        if port_open(port):
            break
        time.sleep(0.1)
    else:
        print("the server never came up on %d." % port)
        return 2

    # Imported rather than shelled out to, so it shares this process's server
    # thread -- and pointed at the port actually taken above. Its main()
    # reads sys.argv itself.
    import run_harnesses
    run_harnesses.BASE = "http://127.0.0.1:%d" % port
    print("serving %d for this run (%s)." % (port, run_harnesses.BASE))
    return run_harnesses._run()


if __name__ == "__main__":
    sys.exit(main())
