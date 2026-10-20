# -*- coding: utf-8 -*-
"""Screenshots of the real app, driven over the DevTools protocol.

`msedge --headless --screenshot` does not work on this app: with a virtual
time budget the held polls stop the clock and it hangs, and without one it
shoots at the load event, which is the boot screen. So this drives Edge the
way a person would, on the wall clock: start Jarvis in a thread on a private
port, open the page, wait for the boot screen to go, then for each shot run
a line of the page's own JavaScript, wait for what it should show, and take
the picture.

    python tools/ui_shots.py                       every shot, 1366x768
    python tools/ui_shots.py --only eventbank      shots whose name matches
    python tools/ui_shots.py --size 1920x1080 --theme light --tag after
    python tools/ui_shots.py --eval "setView('toolkit')" --name tk

Shots go to <temp>/jarvis-shots/<tag>/ unless --out says otherwise: they are
for looking at, not for the repository. Run it from PowerShell, like the
harness suite -- Edge launched from the bash tool's sandbox writes nothing.
Nothing here clicks a toggle that writes shared preferences: themes are
applied with `remember=false`.
"""
import argparse
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

EDGE = os.environ.get("EDGE") or (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

#: name, the page's own JavaScript to get there, and what must be true
#: before the picture is taken (a JS expression), then a settle in seconds.
SHOTS = [
    ("pipeline", "setView('pipeline')", "1", 0.8),
    ("explorer", "setView('explorer')", "1", 0.8),
    ("xplore", "setView('xplore')", "1", 0.8),
    ("sessions", "setView('sessions')",
     "!!document.querySelector('#view-sessions .pad')", 2.5),
    ("history", "setView('history')", "1", 1.5),
    ("errors", "setView('errors')", "1", 1.0),
    ("results", "setView('results')", "1", 1.5),
    ("eventbank", "setView('eventbank')",
     "!!document.querySelector('#bankBody .bank-row')", 1.5),
    ("storyboard", "setView('storyboard')", "1", 1.0),
    ("toolkit", "setView('toolkit')", "!!document.querySelector('#tkBody')",
     1.5),
    ("misc", "setView('misc')", "1", 0.8),
]

# ToolKit tools, opened through the ToolKit's own picker.
TOOLS = ["incisor", "curate", "braces", "dspca", "doppler", "spotter", "eye",
         "junction", "panning", "lock", "horizon", "panorama", "cfc",
         "spark", "coupling", "circuit", "drift", "bad", "strata",
         "kilosort", "snapshots"]
for _t in TOOLS:
    SHOTS.append(("tool-" + _t,
                  "setView('toolkit'); BARRY.views.toolkit.pick('%s')" % _t,
                  "!!document.querySelector('#tkResult')", 2.5))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def serve(port):
    from backend.app import app
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False,
            threaded=True)


class CDP:
    """A DevTools websocket, by hand: enough of RFC 6455 for one client."""

    def __init__(self, ws_url, timeout=60):
        rest = ws_url.split("://", 1)[1]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)
        ).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            got = self.sock.recv(4096)
            if not got:
                raise RuntimeError("DevTools closed during the handshake")
            head += got
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise RuntimeError("DevTools refused the websocket: %r" % head[:200])
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _read(self, k):
        while len(self.buf) < k:
            got = self.sock.recv(1 << 20)
            if not got:
                raise RuntimeError("DevTools closed the connection")
            self.buf += got
        out, self.buf = self.buf[:k], self.buf[k:]
        return out

    def _send_frame(self, data, opcode=0x1):
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            head = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
        elif n < 65536:
            head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(head + mask + masked)

    def _recv_message(self):
        parts = []
        while True:
            b1, b2 = self._read(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            payload = self._read(n)
            if op == 0x9:                       # ping
                self._send_frame(payload, 0xA)
                continue
            if op == 0x8:
                raise RuntimeError("DevTools sent close")
            parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8", "replace")

    def _post(self, method, params):
        """A command whose answer nobody waits for."""
        self.n += 1
        self._send_frame(json.dumps({"id": self.n, "method": method,
                                     "params": params}).encode())

    def _paused(self, p):
        """A request held by `Fetch`: a WRITE to the preferences is answered
        here and never reaches the server, so a screenshot run cannot change
        anybody's theme, VACC Mode or anything else it boots with (memory:
        pressing a toggle writes shared prefs). Everything else goes on."""
        req = p.get("request") or {}
        if req.get("method") == "POST" and "/api/prefs" in req.get("url", ""):
            self._post("Fetch.fulfillRequest", {
                "requestId": p["requestId"], "responseCode": 200,
                "responseHeaders": [{"name": "Content-Type",
                                     "value": "application/json"}],
                "body": base64.b64encode(b'{"ok": true}').decode()})
        else:
            self._post("Fetch.continueRequest", {"requestId": p["requestId"]})

    def call(self, method, params=None, timeout=60):
        self.n += 1
        mid = self.n
        self._send_frame(json.dumps({"id": mid, "method": method,
                                     "params": params or {}}).encode())
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self._recv_message())
            if msg.get("method") == "Fetch.requestPaused":
                self._paused(msg.get("params") or {})
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result") or {}
        raise RuntimeError("no answer to %s" % method)

    def pump(self, seconds):
        """Wait, answering held requests meanwhile (instead of time.sleep)."""
        end = time.time() + seconds
        while time.time() < end:
            try:
                self.js("1", timeout=10)
            except RuntimeError:
                pass
            time.sleep(0.1)

    def js(self, expr, timeout=60):
        got = self.call("Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
            "awaitPromise": True}, timeout=timeout)
        if got.get("exceptionDetails"):
            raise RuntimeError("JS: %s" % json.dumps(got["exceptionDetails"])[:400])
        return (got.get("result") or {}).get("value")

    def until(self, expr, limit=30.0, step=0.25):
        end = time.time() + limit
        while time.time() < end:
            try:
                if self.js("!!(%s)" % expr, timeout=20):
                    return True
            except RuntimeError:
                pass
            time.sleep(step)
        return False

    def shot(self, path, clip=None):
        params = {"format": "png", "captureBeyondViewport": False}
        if clip:
            params["clip"] = dict(clip, scale=1)
        data = self.call("Page.captureScreenshot", params, timeout=90)["data"]
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--size", default="1366x768")
    ap.add_argument("--theme", default="")
    ap.add_argument("--tag", default="now")
    ap.add_argument("--out", default="")
    ap.add_argument("--eval", default="")
    ap.add_argument("--wait", default="1")
    ap.add_argument("--name", default="custom")
    ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--query", default="", help="extra ?query for the page")
    ap.add_argument("--steps", default="",
                    help='JSON [[js, wait, settle], ...] run in order, then '
                         'one shot named --name')
    a = ap.parse_args()

    w, h = (int(x) for x in a.size.lower().split("x"))
    out = a.out or os.path.join(tempfile.gettempdir(), "jarvis-shots", a.tag)
    os.makedirs(out, exist_ok=True)

    port = free_port()
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    t0 = time.time()
    while not port_open(port):
        if time.time() - t0 > 90:
            print("the app did not start")
            return 2
        time.sleep(0.25)

    dbg = free_port()
    profile = tempfile.mkdtemp(prefix="jarvis-shots-")
    edge = subprocess.Popen([
        EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--hide-scrollbars",
        "--remote-allow-origins=*",
        "--remote-debugging-port=%d" % dbg, "--user-data-dir=" + profile,
        "--window-size=%d,%d" % (w, h), "about:blank"],
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
        if not ws:
            print("Edge did not open DevTools")
            return 2
        cdp = CDP(ws)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Fetch.enable", {"patterns": [
            {"urlPattern": "*/api/prefs*", "requestStage": "Request"}]})
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": w, "height": h, "deviceScaleFactor": 1, "mobile": False})
        url = "http://127.0.0.1:%d/%s" % (port, ("?" + a.query) if a.query else "")
        cdp.call("Page.navigate", {"url": url})
        if not cdp.until("!document.getElementById('boot') || "
                         "document.getElementById('boot').classList"
                         ".contains('gone') || (window.getComputedStyle("
                         "document.getElementById('boot')).display === 'none')",
                         limit=120):
            print("the boot screen never went")
        cdp.pump(1.5)
        if a.theme:
            cdp.js("applyTheme(themeById(%s), false)" % json.dumps(a.theme))
            cdp.pump(0.6)

        if a.steps:
            raw = a.steps
            if raw.startswith("@"):
                # A file: PowerShell strips the quotes out of a JSON
                # argument on its way to a native program.
                with open(raw[1:], "r", encoding="utf-8") as fh:
                    raw = fh.read()
            for js_, wait_, settle_ in json.loads(raw):
                try:
                    cdp.js(js_)
                except RuntimeError as exc:
                    print("  step failed: %s" % exc)
                if not cdp.until(wait_ or "1", limit=30):
                    print("  step waited out: %s" % (wait_ or "")[:80])
                cdp.pump(float(settle_ or 0.5))
            path = os.path.join(out, "%s@%dx%d%s.png" % (
                a.name, w, h, ("-" + a.theme) if a.theme else ""))
            cdp.shot(path)
            print("  %-22s %s" % (a.name, path))
            return 0
        shots = ([(a.name, a.eval, a.wait, a.settle)] if a.eval else
                 [s for s in SHOTS if not a.only or any(
                     o and o in s[0] for o in a.only.split(","))])
        for name, expr, wait, settle in shots:
            try:
                cdp.js(expr)
            except RuntimeError as exc:
                print("  %-22s could not get there: %s" % (name, exc))
                continue
            ok = cdp.until(wait, limit=30)
            cdp.pump(settle)
            path = os.path.join(out, "%s@%dx%d%s.png" % (
                name, w, h, ("-" + a.theme) if a.theme else ""))
            cdp.shot(path)
            print("  %-22s %s%s" % (name, path, "" if ok else "  (waited out)"))
        return 0
    finally:
        try:
            edge.kill()
        except Exception:                                # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
