"""
vos.py -- VOS census to the Lab Operations Schedule, in one click.

BEFORE THIS, by hand: sign in to uvm.vos.redplank.co, filter Cages to X6-041 /
Active, 200 a page, Select All, Print Selected, Save as PDF, run
VOS_report_parser.py on it, paste the CSV into "VOS Imports", then Lab Tools >
Sync VOS Census and pick the date.

NOW: Misc > VOS log in > Sync VOS. The same steps, the same parser, the same
importer, with nobody clicking:

  1. The cage list is a plain GET -- /cages?form[protocol_id]=415&
     form[status]=active&per_page=200 -- read with the saved session cookies.
     No browser needed for that.
  2. The print page (/cage_cards/print?cage_ids[]=...) is opened in a hidden
     Chrome and saved with Page.printToPDF, which is what "Save as PDF" does.
  3. The PDF goes to VOS_report_parser.py UNCHANGED. On 2026-11-04 its output
     was identical, all 87 rows, to the 110326 export made by hand.
  4. The rows go to the sheet's Apps Script web app (VOS_Import.gs doPost),
     first as a preview. If nobody would be newly RETIRED it is applied at
     once; otherwise it waits in Misc for Apply. A partial fetch would retire
     the colony, so that is the one outcome a person has to look at.

THE SESSION (memory: vos-session-is-a-cookie-jar). VOS signs in only through
myUVM + Duo, and every cookie that holds the session is a session cookie, so
a Chrome profile reopened later is signed out. What works is keeping the
cookies ourselves -- saved over CDP after the sign-in, sent with every request
and put back into the hidden Chrome. A keep-alive GET every half hour while
Jarvis runs is what stops an idle timeout from asking for Duo again; how long
VOS keeps a session at all is recorded in status.json as it is learned.

Everything here is machine-local, in %LOCALAPPDATA%\\Jarvis\\vos: the cookies
are a credential and the web app secret is one too. Nothing goes in the repo
except the archived PDF + CSV, beside the hand-made ones.

    GET  /api/vos/status        signed in?, the sheet link, the run, the hold
    POST /api/vos/login         open Chrome on the myUVM sign-in
    POST /api/vos/sync          fetch, parse, preview, apply unless held
    POST /api/vos/apply         apply the held preview
    POST /api/vos/discard       drop it
    POST /api/vos/config        {webapp_url}
"""
from __future__ import annotations

import base64
import contextlib
import csv
import datetime as dt
import importlib.util
import io
import json
import os
import re
import secrets
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, request

from . import feed as feedmod
from .paths import REPO_ROOT

BASE = "https://uvm.vos.redplank.co"
PROTOCOL = "X6-041"
PROTOCOL_ID = "415"      # the value of "X6-041 (Barry, J.)" in VOS's filter
COOKIE_DOMAINS = ("redplank", "uvm.edu", "duosecurity")

STATE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                     "Jarvis", "vos")
PROFILE = os.path.join(STATE, "chrome-profile")
JAR = os.path.join(STATE, "cookies.json")
CONFIG = os.path.join(STATE, "config.json")
STATUS = os.path.join(STATE, "status.json")

COLONY = os.path.join(REPO_ROOT, "Colony Management")
PARSER = os.path.join(COLONY, "VOS Exports", "VOS Report to CSV",
                      "VOS_report_parser.py")
ARCHIVE = os.path.join(COLONY, "VOS Exports", "Jarvis")

LOGIN_WAIT_S = 600
KEEPALIVE_S = 30 * 60
# A run that finds fewer cages than this share of the last good run stops
# before the sheet: that is what a broken page or a lost filter looks like.
MIN_SHARE_OF_LAST = 0.75

CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
)

_LOCK = threading.Lock()
RUN = {"running": False, "what": None, "step": "", "started": None}
HOLD = {"preview": None, "payload": None}


# --- small files ------------------------------------------------------------

def _read(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


def _status_update(**kw):
    st = _read(STATUS, {})
    st.update(kw)
    _write(STATUS, st)
    return st


def _config():
    cfg = _read(CONFIG, {})
    if not cfg.get("secret"):
        # Sent with every call; the web app keeps the first one it is shown
        # (VOS_Import.gs, doPost) and refuses anything else after that.
        cfg["secret"] = secrets.token_urlsafe(24)
        _write(CONFIG, cfg)
    return cfg


def _say(text, level="info", done=False, progress=None):
    feedmod.say("VOS: " + text, key="vos", level=level, done=done,
                progress=progress)


def _step(text):
    RUN["step"] = text
    _say(text)


# --- the session, without a browser -----------------------------------------

def _jar():
    return _read(JAR, [])


def _cookie_header(url):
    host = urllib.parse.urlparse(url).hostname or ""
    pairs = []
    for c in _jar():
        dom = c.get("domain", "").lstrip(".")
        if host == dom or host.endswith("." + dom):
            pairs.append("%s=%s" % (c["name"], c["value"]))
    return "; ".join(pairs)


def _absorb_set_cookies(headers):
    """Rails may hand out a new _session_id; keep whatever it sets."""
    got = headers.get_all("Set-Cookie") or []
    if not got:
        return
    jar = _jar()
    for raw in got:
        name, _, rest = raw.partition("=")
        value = rest.split(";", 1)[0]
        for c in jar:
            if c.get("name") == name.strip() and "redplank" in c.get("domain", ""):
                c["value"] = value
    _write(JAR, jar)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(path):
    """(status, body, final_location) for a VOS page, on the saved cookies.
    A redirect to the sign-in page is answered, not followed."""
    url = BASE + path
    req = urllib.request.Request(url, headers={
        "Cookie": _cookie_header(url),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis-VOS"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=60) as r:
            _absorb_set_cookies(r.headers)
            return r.status, r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, "", e.headers.get("Location")


def check_session():
    """True when the saved cookies still open VOS. Writes what it learned."""
    if not _jar():
        _status_update(signed_in=False, checked=time.time())
        return False
    try:
        code, _body, loc = _get("/cages?per_page=25")
    except OSError as e:
        _status_update(check_error=str(e), checked=time.time())
        return None
    ok = code == 200
    st = _read(STATUS, {})
    upd = {"signed_in": ok, "checked": time.time(), "check_error": None}
    if ok:
        upd["last_ok"] = time.time()
    elif st.get("signed_in"):
        # The moment a session that worked stops working: how long VOS lets
        # one live is learned from this, sign-in to here.
        upd["lost_at"] = time.time()
        upd["lived_s"] = round(time.time() - (st.get("signed_in_at") or time.time()))
        upd["lost_to"] = loc
    _status_update(**upd)
    return ok


def _keepalive():
    while True:
        time.sleep(KEEPALIVE_S)
        if RUN["running"] or not _jar():
            continue
        try:
            check_session()
        except Exception:                                # noqa: BLE001
            pass


# --- Chrome over the DevTools protocol --------------------------------------

class _CDP:
    """Enough of a DevTools websocket for one page (as tools/ui_shots.py)."""

    def __init__(self, ws_url, timeout=60):
        rest = ws_url.split("://", 1)[1]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            got = self.sock.recv(4096)
            if not got:
                raise RuntimeError("DevTools closed during the handshake")
            head += got
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

    def _send(self, data, opcode=0x1):
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            head = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
        elif n < 65536:
            head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
        self.sock.sendall(head + mask + bytes(
            b ^ mask[i % 4] for i, b in enumerate(data)))

    def _message(self):
        parts = []
        while True:
            b1, b2 = self._read(2)
            fin, op, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            payload = self._read(n)
            if op == 0x9:
                self._send(payload, 0xA)
                continue
            if op == 0x8:
                raise RuntimeError("DevTools sent close")
            parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8", "replace")

    def call(self, method, params=None, timeout=60):
        self.n += 1
        mid = self.n
        self._send(json.dumps({"id": mid, "method": method,
                               "params": params or {}}).encode())
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self._message())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result") or {}
        raise RuntimeError("no answer to %s" % method)

    def js(self, expr, timeout=60):
        got = self.call("Runtime.evaluate", {"expression": expr,
                                             "returnByValue": True,
                                             "awaitPromise": True}, timeout)
        return (got.get("result") or {}).get("value")

    def go(self, url, settle=1.5, limit=90):
        self.call("Page.navigate", {"url": url})
        time.sleep(0.6)
        end = time.time() + limit
        while time.time() < end:
            try:
                if self.js("document.readyState") == "complete":
                    break
            except RuntimeError:
                pass
            time.sleep(0.3)
        time.sleep(settle)
        return self.js("location.href")


def _chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    raise RuntimeError("Chrome is not installed where Jarvis looks for it")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _Browser:
    """A Chrome on Jarvis's own profile -- never the everyday one."""

    def __init__(self, headless):
        os.makedirs(PROFILE, exist_ok=True)
        self.port = _free_port()
        args = [_chrome(), "--remote-debugging-port=%d" % self.port,
                "--remote-allow-origins=*", "--user-data-dir=" + PROFILE,
                "--no-first-run", "--no-default-browser-check",
                "--window-size=1100,900"]
        if headless:
            args += ["--headless=new", "--disable-gpu"]
        self.proc = subprocess.Popen(args + ["about:blank"],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        ws, end = None, time.time() + 30
        while not ws and time.time() < end:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json/list" % self.port, timeout=2) as r:
                    ws = next((t["webSocketDebuggerUrl"] for t in json.loads(r.read())
                               if t.get("type") == "page"), None)
            except Exception:                            # noqa: BLE001
                time.sleep(0.3)
        if not ws:
            self.close()
            raise RuntimeError("Chrome did not open DevTools")
        self.tab = _CDP(ws)
        self.tab.call("Page.enable")
        self.tab.call("Runtime.enable")
        self.tab.call("Network.enable")
        # Should the print page ever call window.print(), a dialog would
        # hold it; there is nobody to press Cancel.
        self.tab.call("Page.addScriptToEvaluateOnNewDocument", {
            "source": "window.print = function () {};"})

    def load_cookies(self):
        jar = _jar()
        if jar:
            self.tab.call("Network.setCookies", {"cookies": [
                {k: c[k] for k in ("name", "value", "domain", "path", "secure",
                                   "httpOnly", "sameSite", "expires") if k in c}
                for c in jar]})

    def save_cookies(self):
        cookies = self.tab.call("Network.getAllCookies")["cookies"]
        mine = [c for c in cookies
                if any(d in c.get("domain", "") for d in COOKIE_DOMAINS)]
        if mine:
            _write(JAR, mine)
        return mine

    def close(self):
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/version" % self.port, timeout=3) as r:
                _CDP(json.loads(r.read())["webSocketDebuggerUrl"])._send(
                    json.dumps({"id": 1, "method": "Browser.close"}).encode())
        except Exception:                                # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=15)
        except Exception:                                # noqa: BLE001
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _signed_in_url(href):
    return (href or "").startswith(BASE) and "/users/sign_in" not in href \
        and "/auth/" not in href


# --- the jobs -----------------------------------------------------------------

def _start(what, fn):
    with _LOCK:
        if RUN["running"]:
            return False
        RUN.update(running=True, what=what, step="", started=time.time(),
                   error=None)

    def body():
        try:
            fn()
        except Exception as e:                           # noqa: BLE001
            RUN["error"] = str(e)
            _say(str(e), level="error", done=True)
            _status_update(last_error={"at": time.time(), "what": what,
                                       "error": str(e)})
        finally:
            RUN.update(running=False, step="")
    threading.Thread(target=body, daemon=True, name="jarvis-vos-" + what).start()
    return True


def _login():
    _step("opening Chrome for the myUVM sign-in")
    b = _Browser(headless=False)
    try:
        href = b.tab.go(BASE + "/cages")
        if not _signed_in_url(href):
            _step("waiting for you to sign in (myUVM + Duo) in the Chrome window")
            b.tab.go(BASE + "/auth/sso/new", settle=0.5)
            end = time.time() + LOGIN_WAIT_S
            while time.time() < end:
                try:
                    href = b.tab.js("location.href", timeout=10)
                except RuntimeError:
                    href = ""
                if _signed_in_url(href):
                    break
                time.sleep(1)
        if not _signed_in_url(href):
            raise RuntimeError("the sign-in was not finished within %d minutes"
                               % (LOGIN_WAIT_S // 60))
        time.sleep(1.5)
        b.save_cookies()
    finally:
        b.close()
    _status_update(signed_in=True, signed_in_at=time.time(), last_ok=time.time(),
                   lost_at=None, lived_s=None)
    _say("signed in", done=True)


def _list_cages():
    ids, page, expected = [], 1, None
    while page <= 20:
        q = urllib.parse.urlencode({"form[protocol_id]": PROTOCOL_ID,
                                    "form[status]": "active",
                                    "per_page": "200", "page": str(page)})
        code, html, loc = _get("/cages?" + q)
        if code != 200:
            _status_update(signed_in=False, lost_at=time.time(), lost_to=loc)
            raise RuntimeError("VOS signed Jarvis out. Press Sign in and approve Duo, "
                               "then Sync again.")
        if PROTOCOL not in html:
            raise RuntimeError("the Cages page no longer offers %s; nothing was sent "
                               "to the sheet" % PROTOCOL)
        m = re.search(r"Select All on Page \((\d+) cages?\)", html)
        if m and expected is None:
            expected = int(m.group(1))
        got = []
        for tag in re.findall(r"<input[^>]*name=\"cage_select\"[^>]*>", html):
            v = re.search(r"value=\"(\d+)\"", tag)
            if v and v.group(1) not in ids and v.group(1) not in got:
                got.append(v.group(1))
        ids += got
        if not got or len(got) < 200:
            break
        page += 1
    return ids, expected


def _load_parser():
    spec = importlib.util.spec_from_file_location("vos_report_parser", PARSER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso_date(text):
    """'9/14/25', '10/1/2025', '2025-10-25' -> '2025-09-14'. Else as given."""
    t = str(text or "").strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%y", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return t


def _fetch():
    """The cages, their cards as a PDF, the parser's rows. Raises on anything
    that would make the sheet wrong."""
    _step("reading the active %s cages" % PROTOCOL)
    ids, expected = _list_cages()
    if not ids:
        raise RuntimeError("VOS listed no active %s cages; nothing was sent" % PROTOCOL)
    if expected is not None and expected != len(ids):
        raise RuntimeError("VOS said %d cages but Jarvis read %d; nothing was sent"
                           % (expected, len(ids)))
    last = (_read(STATUS, {}).get("last_sync") or {}).get("cages")
    if last and len(ids) < MIN_SHARE_OF_LAST * last:
        raise RuntimeError("only %d cages, against %d last time. That looks like a "
                           "broken page rather than a colony; nothing was sent"
                           % (len(ids), last))

    _step("printing %d cage cards to PDF" % len(ids))
    b = _Browser(headless=True)
    try:
        b.load_cookies()
        url = BASE + "/cage_cards/print?" + "&".join(
            "cage_ids%5B%5D=" + i for i in ids)
        href = b.tab.go(url, settle=3, limit=120)
        if not _signed_in_url(href):
            raise RuntimeError("VOS signed Jarvis out. Press Sign in and approve Duo, "
                               "then Sync again.")
        pdf = base64.b64decode(b.tab.call("Page.printToPDF", {
            "printBackground": False, "preferCSSPageSize": True,
            "paperWidth": 8.5, "paperHeight": 11}, timeout=180)["data"])
        b.save_cookies()
    finally:
        b.close()

    now = dt.datetime.now()
    stamp = now.strftime("%m%d%y")
    os.makedirs(ARCHIVE, exist_ok=True)
    base = os.path.join(ARCHIVE, "VOS Report %s %s" % (stamp, now.strftime("%H%M")))
    with open(base + ".pdf", "wb") as fh:
        fh.write(pdf)

    _step("reading the cards")
    parser = _load_parser()
    # The parser prints its log; the server's console is not where anybody
    # reads it, and the warnings come back in the rows anyway.
    with contextlib.redirect_stdout(io.StringIO()):
        records = parser.parse_pdf(base + ".pdf")
    records.sort(key=lambda r: (r["Extracted Sorting ID"], r["Source Page"],
                                r["Position on Page"]))
    cards = {re.sub(r"^CC-(\d+).*$", r"\1", r["Cage Card"]) for r in records
             if r["Cage Card"]}
    missing = sorted(set(ids) - cards)
    if missing:
        raise RuntimeError("the PDF has no card for cage(s) %s; nothing was sent"
                           % ", ".join(missing))
    cols = parser.build_column_map(stamp)
    with open(base + ".csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=[new for _, new in cols])
        w.writeheader()
        for rec in records:
            w.writerow({new: rec.get(orig, "") for orig, new in cols})

    kept, issues, skipped = sort_cards(records)
    held = {i["mouse"] for i in issues if i.get("hold")}
    mice, seen = [], set()
    for r in kept:
        mid = str(r["Extracted Sorting ID"])
        if mid in seen:
            continue
        seen.add(mid)
        mice.append({"id": mid, "hold": True} if mid in held else
                    {"id": mid, "cage": r["Cage Card"],
                     "dob": _iso_date(r["DOB"]), "sex": r["Sex"]})
    block = {"headers": [new for _, new in cols],
             "rows": [[rec.get(orig, "") for orig, _ in cols] for rec in kept]}
    return {"stamp": stamp, "cages": len(ids), "rows": len(records),
            "mice": mice, "block": block, "issues": issues, "skipped": skipped,
            "pdf": base + ".pdf", "csv": base + ".csv"}


# --- what is wrong, in words ---------------------------------------------------

# Not KCNT1 mice: the protocol holds them, the KCNT1 sheet does not.
SKIP_STRAINS = ("PACAP",)

CARD_NAMING = "Cage card naming issue"
CARD_COUNT = "Cage card count issue"
CARD_OTHER = "Cage card issue"
SHEET = "Spreadsheet issue"
SKIPPED = "Skipped"

KIND_CATEGORY = {"typo": CARD_NAMING, "dup_tag": CARD_NAMING,
                 "parent_in_cage": CARD_NAMING, "count": CARD_COUNT,
                 "untagged": CARD_COUNT, "card_missing": CARD_OTHER,
                 "assumed": CARD_OTHER}


def sort_cards(records):
    """(rows to send, issues, skipped cards) from the parser's rows.

    PACAP cards are skipped -- not the KCNT1 sheet's -- and so are rows with
    no mouse tag, which no sheet row could ever match. A tag on two cards is
    an issue AND a hold: the sheet keeps that mouse as it is until VOS is
    fixed, rather than Jarvis guessing which cage is right.
    """
    kept, skipped, issues, seen = [], {}, [], set()

    def add(category, cage, text, mouse=None, hold=False):
        key = (category, cage, mouse, text)
        if key in seen:
            return
        seen.add(key)
        issues.append({"category": category, "cage": cage, "mouse": mouse,
                       "text": text, "hold": hold})

    for r in records:
        strain = r.get("Strain") or ""
        cage = r["Cage Card"]
        if any(s.lower() in strain.lower() for s in SKIP_STRAINS):
            sk = skipped.setdefault(cage, {"cage": cage, "strain": strain,
                                           "mice": 0, "why": "not a KCNT1 cage"})
            sk["mice"] += 1
            continue
        kinds = r.get("_issues") or []
        if not r["Mouse Tag"]:
            sk = skipped.setdefault(cage, {"cage": cage, "strain": strain, "mice": 0,
                                           "why": "the card lists no mouse IDs"})
            sk["mice"] += 1
            add(CARD_COUNT, cage, "%s lists no mouse IDs but says # Animals %s; "
                "nothing was sent for it" % (cage, r.get("# Animals")))
            continue
        kept.append(r)
        for kind, text in kinds:
            if kind == "dup_tag":
                add(CARD_NAMING, cage, "mouse %s is on more than one cage (%s); its "
                    "row in the sheet is left as it is until VOS is fixed"
                    % (r["Mouse Tag"], text.split(" also appears on ")[-1] + ", " + cage),
                    mouse=r["Mouse Tag"], hold=True)
            elif kind == "untagged":
                continue
            else:
                add(KIND_CATEGORY.get(kind, CARD_OTHER), cage, "%s: %s" % (cage, text))
    # The dup_tag line is said once per mouse, not once per card it is on.
    one = {}
    for i in issues:
        if i["hold"]:
            one.setdefault(i["mouse"], i)
    issues = [i for i in issues if not i["hold"] or one.get(i["mouse"]) is i]
    for i in issues:
        if i["hold"]:
            cages = sorted({r["Cage Card"] for r in kept if r["Mouse Tag"] == i["mouse"]})
            i["text"] = ("mouse %s is on %s; its row in the sheet is left as it is "
                         "until VOS is fixed" % (i["mouse"], " and ".join(cages)))
    return kept, issues, sorted(skipped.values(), key=lambda s: s["cage"])


def sheet_issues(res):
    """What the sheet's answer says is wrong with the sheet itself."""
    out = []
    sheet = res.get("sheet") or "the sheet"
    for d in res.get("sheetDuplicates") or []:
        out.append({"category": SHEET, "mouse": d["id"],
                    "text": "Mouse ID %s is on %d rows of %s (rows %s)"
                    % (d["id"], len(d["rows"]), sheet,
                       ", ".join(str(x) for x in d["rows"]))})
    for mid in res.get("revived") or []:
        out.append({"category": SHEET, "mouse": mid,
                    "text": "%s was RETIRED in the sheet but is in a VOS cage again; "
                            "it gets its cage back" % mid})
    for mid in res.get("heldMissing") or []:
        out.append({"category": SHEET, "mouse": mid,
                    "text": "%s is not in the sheet yet, and is not added while VOS "
                            "has it on two cages" % mid})
    return out


def _post_sheet(payload, mode):
    cfg = _config()
    url = cfg.get("webapp_url")
    if not url:
        raise RuntimeError("the sheet is not connected yet: paste the web app URL "
                           "under VOS log in")
    body = dict(payload, mode=mode, secret=cfg["secret"])
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    # Apps Script answers a POST with a redirect to the result, which urllib
    # follows as a GET -- exactly what the redirect wants.
    with urllib.request.urlopen(req, timeout=300) as r:
        text = r.read().decode("utf-8", "replace")
    try:
        out = json.loads(text)
    except ValueError:
        raise RuntimeError("the web app did not answer with JSON. Is it deployed "
                           "with access for Anyone? It said: %s"
                           % re.sub(r"<[^>]+>", " ", text)[:300])
    if not out.get("ok"):
        raise RuntimeError("the sheet refused: %s" % out.get("error"))
    return out


def _payload(got):
    return {"stamp": got["stamp"], "mice": got["mice"], "block": got["block"]}


def _summary(got, res, applied):
    return {"at": time.time(), "stamp": got["stamp"], "cages": got["cages"],
            "rows": got["rows"], "issues": got["issues"] + sheet_issues(res),
            "skipped": got["skipped"],
            "pdf": got["pdf"], "csv": got["csv"], "applied": applied,
            "sheet": res.get("sheet"), "result": res}


def _sync():
    if not _config().get("webapp_url"):
        raise RuntimeError("the sheet is not connected yet: paste the web app URL "
                           "under VOS log in")
    got = _fetch()
    _step("asking the sheet what would change")
    payload = _payload(got)
    pre = _post_sheet(payload, "preview")
    retire = pre.get("newlyRetired") or []
    if retire:
        HOLD.update(preview=_summary(got, pre, False), payload=payload)
        _status_update(last_fetch=HOLD["preview"])
        _say("%d mouse/mice would be marked RETIRED; waiting for you in Misc"
             % len(retire), level="warn", done=True)
        return
    _step("writing to the sheet")
    res = _post_sheet(payload, "apply")
    summ = _summary(got, res, True)
    HOLD.update(preview=None, payload=None)
    _status_update(last_sync=summ, last_fetch=summ, last_error=None)
    _say("synced: %s updated, %d added, %d retired, %d issue(s) to fix in Misc" % (
        res.get("active"), len(res.get("added") or []),
        len(res.get("newlyRetired") or []), len(summ["issues"])),
        level="warn" if summ["issues"] else "info", done=True)


def _apply():
    if not HOLD["payload"]:
        raise RuntimeError("there is nothing waiting to apply")
    _step("writing to the sheet")
    pre = HOLD["preview"]
    res = _post_sheet(HOLD["payload"], "apply")
    card = [i for i in pre["issues"] if i["category"] != SHEET]
    summ = dict(pre, at=time.time(), applied=True, result=res,
                sheet=res.get("sheet"), issues=card + sheet_issues(res))
    HOLD.update(preview=None, payload=None)
    _status_update(last_sync=summ, last_fetch=summ, last_error=None)
    _say("applied: %s updated, %d added, %d retired" % (
        res.get("active"), len(res.get("added") or []),
        len(res.get("newlyRetired") or [])), done=True)


# --- routes ---------------------------------------------------------------------

def status():
    st = _read(STATUS, {})
    cfg = _config()
    return {
        "ok": True,
        "signed_in": st.get("signed_in"),
        "signed_in_at": st.get("signed_in_at"),
        "checked": st.get("checked"),
        "lost_at": st.get("lost_at"),
        "lived_s": st.get("lived_s"),
        "has_session": bool(_jar()),
        "sheet_connected": bool(cfg.get("webapp_url")),
        "webapp_url": cfg.get("webapp_url") or "",
        "run": {k: RUN.get(k) for k in ("running", "what", "step", "started", "error")},
        "hold": HOLD["preview"],
        "last_sync": st.get("last_sync"),
        "last_error": st.get("last_error"),
        "protocol": PROTOCOL,
        "chrome": next((p for p in CHROME_PATHS if os.path.exists(p)), None),
    }


def install(app, fail):
    os.makedirs(STATE, exist_ok=True)
    threading.Thread(target=_keepalive, daemon=True,
                     name="jarvis-vos-keepalive").start()

    def busy():
        return jsonify({"ok": False, "error": "VOS is already %s" % (
            "signing in" if RUN["what"] == "login" else "syncing")}), 409

    @app.route("/api/vos/status")
    def api_vos_status():
        if request.args.get("check") == "1" and not RUN["running"]:
            check_session()
        return jsonify(status())

    @app.route("/api/vos/login", methods=["POST"])
    def api_vos_login():
        return jsonify(status()) if _start("login", _login) else busy()

    @app.route("/api/vos/sync", methods=["POST"])
    def api_vos_sync():
        return jsonify(status()) if _start("sync", _sync) else busy()

    @app.route("/api/vos/apply", methods=["POST"])
    def api_vos_apply():
        if not HOLD["payload"]:
            return jsonify({"ok": False, "error": "nothing is waiting to apply"}), 400
        return jsonify(status()) if _start("apply", _apply) else busy()

    @app.route("/api/vos/discard", methods=["POST"])
    def api_vos_discard():
        HOLD.update(preview=None, payload=None)
        return jsonify(status())

    @app.route("/api/vos/config", methods=["POST"])
    def api_vos_config():
        try:
            url = str((request.get_json(silent=True) or {}).get("webapp_url") or "").strip()
            if url and not re.match(r"^https://script\.google\.com/\S+/exec$", url):
                return jsonify({"ok": False, "error":
                                "that is not an Apps Script web app URL (it should "
                                "start https://script.google.com/ and end /exec)"}), 400
            cfg = _config()
            cfg["webapp_url"] = url
            _write(CONFIG, cfg)
            return jsonify(status())
        except Exception as e:                           # noqa: BLE001
            return fail("vos config", e)
