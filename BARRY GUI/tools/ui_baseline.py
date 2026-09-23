# -*- coding: utf-8 -*-
"""Capture the UI measurement baseline, or diff against the stored one.

A consistency refactor is mostly a large mechanical diff, and a large
mechanical diff cannot be reviewed by reading it -- 1,500 changed lines of
CSS all look correct. What can be reviewed is the RESULT: every control's
measured shape, every composition's structure and every grid's column
count, sorted into a text file.

    python tools/ui_baseline.py            diff against the stored baseline
    python tools/ui_baseline.py --save     store what it measures now

A phase meant to change nothing must produce an empty diff. A phase meant
to change three selectors must produce exactly those three lines. Anything
else stops the phase.

Run it from PowerShell, and for the same measured reason the harness suite
carries: under a bash shell Edge's `--dump-dom` writes nothing on this
machine, which would report an empty baseline as a clean one.

The server runs in a thread of this process, exactly as `harness_run.py`
does, so there is nothing to start first and nothing left behind.
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

BASELINE = os.path.join(APP, "web", "_dev", "baseline", "ui.txt")

EDGE = os.environ.get("EDGE") or (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
PROFILE = os.path.join(tempfile.gettempdir(), "jarvis-uibaseline-profile")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve(port):
    from backend.app import app
    # use_reloader=False, like start.py: a watcher thread would hold the
    # port open past the run and the next one would attach to stale code.
    app.run(host="127.0.0.1", port=port, debug=False,
            use_reloader=False, threaded=True)


def capture(port):
    """Drive the audit harness and return the text of its dump."""
    url = "http://127.0.0.1:%d/_dev/uiaudit.html" % port
    dump = os.path.join(tempfile.gettempdir(), "jarvis-uibaseline.html")
    try:
        os.remove(dump)
    except OSError:
        pass
    # To a FILE, never a pipe -- `--dump-dom` writes nothing to a pipe on
    # this machine, and an empty capture reads exactly like a clean diff.
    with open(dump, "wb") as sink:
        subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu",
             # Its own profile, or Edge hands the URL to the browser the
             # person already has open and exits without dumping anything.
             "--user-data-dir=" + PROFILE,
             "--no-first-run", "--no-default-browser-check",
             # Wide enough to hold the 1500px pass the harness resizes to.
             "--window-size=1700,1000",
             "--virtual-time-budget=300000", "--dump-dom", url],
            stdout=sink, stderr=subprocess.DEVNULL, timeout=560, cwd=APP)
    with open(dump, "rb") as fh:
        raw = fh.read().decode("utf-8", "replace")

    m = re.search(r'<pre id="dump">(.*?)</pre>', raw, re.S)
    if not m:
        title = (re.search(r"<title>(.*?)</title>", raw, re.S)
                 or [None, "?"])[1]
        raise SystemExit(
            "the harness produced no dump (title: %s, %d bytes captured).\n"
            "An empty capture is not a clean baseline -- fix this before "
            "trusting any diff." % (title.strip(), len(raw)))

    body = m.group(1)
    body = (body.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'")
                .replace("&amp;", "&"))
    text = body.strip("\n")
    if len(text.splitlines()) < 20:
        raise SystemExit("the dump has only %d lines; something did not run"
                         % len(text.splitlines()))
    return text + "\n"


def main():
    save = "--save" in sys.argv[1:]

    port = free_port()
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    print("serving %d for this run." % port, flush=True)

    text = capture(port)

    if save or not os.path.exists(BASELINE):
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("baseline written: %s (%d lines)"
              % (os.path.relpath(BASELINE, APP), len(text.splitlines())))
        return 0

    with open(BASELINE, encoding="utf-8") as fh:
        was = fh.read()
    if was == text:
        print("no change: %d lines, identical to the baseline"
              % len(text.splitlines()))
        return 0

    import difflib
    diff = list(difflib.unified_diff(
        was.splitlines(), text.splitlines(),
        "baseline", "now", lineterm="", n=1))
    print("\n".join(diff))
    adds = len([d for d in diff if d.startswith("+") and d[1:2] != "+"])
    dels = len([d for d in diff if d.startswith("-") and d[1:2] != "-"])
    print("\n%d line(s) added, %d removed. Every one of them has to be a "
          "change you meant." % (adds, dels))
    return 1


if __name__ == "__main__":
    sys.exit(main())
