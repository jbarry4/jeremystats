# -*- coding: utf-8 -*-
"""The PI's practice layer, from the command line (backend/pisafe.py).

    python tools/pisafe.py            what the layer holds on this computer
    python tools/pisafe.py revert     throw it away

Run on the PI's computer. If Jarvis is open there, the revert goes through it
(so the running app forgets the layer at once); if not, the files are removed
here directly. Either way the real records were never touched.
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import pisafe, shards  # noqa: E402
from backend.paths import LOGS_DIR  # noqa: E402

PORTS = (8733,)


def _live(method, body=None):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in PORTS:
        url = "http://127.0.0.1:%d/api/pisafe" % port
        try:
            req = urllib.request.Request(
                url, method=method,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Content-Type": "application/json"})
            return json.loads(op.open(req, timeout=30).read())
        except Exception:                                # noqa: BLE001
            continue
    return None


def show(s):
    print("practice layer:", "ON" if s.get("on") else "off")
    who = s.get("who") or {}
    print("  profile here:  %s / %s / %s" % (who.get("name"), who.get("role"),
                                              who.get("email")))
    print("  began:         %s" % (s.get("started") or "-"))
    print("  clears itself: %s" % (
        "in %s days" % s["clears_in_days"] if s.get("clears_in_days") is not None
        else "-"))
    print("  holds:         %d files (%d bytes), %d hidden records"
          % (s.get("files", 0), s.get("bytes", 0), s.get("hidden", 0)))


def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "status").lower()
    if cmd not in ("status", "revert"):
        print(__doc__)
        return 2
    if cmd == "status":
        s = _live("GET")
        if s is None:
            shards.configure_safe(False, pisafe.state_dir(LOGS_DIR))
            s = pisafe.status(LOGS_DIR)
            s["on"] = pisafe.matches(pisafe.real_profile(LOGS_DIR))
        show(s)
        return 0
    got = _live("POST", {"action": "revert"})
    if got is None:
        print("(Jarvis is not running here; removing the files directly)")
        shards.configure_safe(False, pisafe.state_dir(LOGS_DIR))
        got = pisafe.revert(LOGS_DIR)
    print("removed %d files%s" % (got.get("removed", 0), "" if not got.get(
        "failed") else "; could not remove: " + "; ".join(got["failed"])))
    return 0 if not got.get("failed") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
