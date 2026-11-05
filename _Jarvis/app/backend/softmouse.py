"""
softmouse.py -- SoftMouse.NET genotypes to the Lab Operations Schedule, in one click.

BEFORE THIS, by hand: sign in at softmouse.net, Mice > Mouse List, the
download icon, wait on "Data Export Status", save the .xlsx, paste Physical
Tag / State / Genotype into "SoftMouse Imports" with the date on each
header, then Lab Tools > Sync SoftMouse to KCNT1 and pick the date.

NOW: Misc > SoftMouse log in > Sync SoftMouse. What the probe found
(tools/softmouse_probe.py, 2026-11-05):

  1. The Mouse List is a jqGrid that fills itself from POST /mouse/list.json
     -- 100 rows a page whatever is asked for, every mouse the account has,
     ended ones included. Read with the saved session cookies; no browser.
     The live mice (no end date) were exactly the 139 of that morning's
     hand export: same tags, same State, same Genotype (15 listed their
     genes in another order, which the importer does not care about).
  2. The rows go to the sheet's web app (doPost in VOS_Import.gs, kind
     "softmouse" -> softMouseFromJarvis_ in SoftMouse_Import.gs): the same
     web app and secret as VOS, so connecting the sheet once serves both.
     First as a preview. It applies at once unless a genotype the sheet
     already had (WT / Het / Hom) would be replaced or erased to N/A; then
     it waits in Misc for Apply. That is the one change a person must see:
     a fill is news, an overwrite might be a typo in SoftMouse.

THE SESSION is session cookies only (JSESSIONID, ISHToken, INGRESSCOOKIE),
like VOS: a Chrome reopened later is signed out, the cookies replayed are
not. SoftMouse signs in with the lab's username and password, no Duo. The
cookies are kept in %LOCALAPPDATA%\\Jarvis\\softmouse. Since 2026-11-05 the
lab's sign-in is kept too (softmouse_login.py: PIN-sealed in the cloud,
DPAPI-sealed on each machine once someone types the PIN), so a lapsed session
signs itself back in, in a Chrome nobody sees. Without it, Sign in opens
Jarvis's own Chrome for a person to type into, as before.

THE RECORD. In the sheet, a date-stamped block in "SoftMouse Imports" with
the hand-pasted blocks' three columns. In Jarvis, one JSON per sync under
SoftMouse Exports/Jarvis/syncs (who, what the sheet changed, the whole list,
and the ended mice with their end dates and how they ended), beside a CSV of
the list in the export's columns.

    GET  /api/softmouse/status     signed in?, the run, the hold, the last sync
    GET  /api/softmouse/history    every sync, newest first, with what changed
    POST /api/softmouse/login      sign in: by itself if it can, else open Chrome
    POST /api/softmouse/unlock     {pin}: keep the lab's sign-in on this machine
    POST /api/softmouse/forget     drop it from this machine
    POST /api/softmouse/sync       read, preview, apply unless held
    POST /api/softmouse/apply      apply the held preview
    POST /api/softmouse/discard    drop it
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import html
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, request

from . import feed as feedmod
from . import softmouse_login as loginmod
from . import vos
from .paths import REPO_ROOT

BASE = "https://www.softmouse.net"
LIST_URL = BASE + "/mouse/list.json"
PAGE_ROWS = 100           # what SoftMouse sends a page, whatever is asked

STATE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                     "Jarvis", "softmouse")
PROFILE = os.path.join(STATE, "chrome-profile")
JAR = os.path.join(STATE, "cookies.json")
STATUS = os.path.join(STATE, "status.json")

ARCHIVE = os.path.join(REPO_ROOT, "Colony Management", "SoftMouse Exports", "Jarvis")
HISTORY = os.path.join(ARCHIVE, "syncs")

LOGIN_WAIT_S = 600
KEEPALIVE_S = 30 * 60
# Fewer live mice than this share of the last good list stops before the
# sheet: a half-read list would write N/A over real genotypes.
MIN_SHARE_OF_LAST = 0.75
KNOWN_GENOTYPES = ("wt", "het", "hom")

# The hand export's columns, from the list's own fields. Alt. ID is not in
# the list, so it is not here either.
CSV_COLUMNS = (("Physical Tag", "physicaltag"), ("Sex", "sex"),
               ("Date of Birth", "dateofbirth"), ("Age", "age"),
               ("State", "mousestate"), ("Mouseline", "mouseline"),
               ("Genotype", "genotype"), ("Cage Tag", "cagetag"),
               ("Protocol", "protocol"), ("Sire Tag", "ftag"),
               ("Dam Tag", "mtag"), ("Comment", "comment"))

SOFTMOUSE = "SoftMouse issue"
SHEET = vos.SHEET

_LOCK = threading.Lock()
RUN = {"running": False, "what": None, "step": "", "started": None}
HOLD = {"preview": None, "payload": None, "record": None}
WHO = {"fn": None}

_read, _write = vos._read, vos._write


def _status_update(**kw):
    st = _read(STATUS, {})
    st.update(kw)
    _write(STATUS, st)
    return st


def _say(text, level="info", done=False):
    feedmod.say("SoftMouse: " + text, key="softmouse", level=level, done=done)


def _step(text):
    RUN["step"] = text
    _say(text)


# --- the session, without a browser -----------------------------------------

def _jar():
    return _read(JAR, [])


def _cookie_header():
    return "; ".join("%s=%s" % (c["name"], c["value"]) for c in _jar())


def _absorb_set_cookies(headers):
    got = headers.get_all("Set-Cookie") or []
    if not got:
        return
    jar = _jar()
    for raw in got:
        name, _, rest = raw.partition("=")
        for c in jar:
            if c.get("name") == name.strip():
                c["value"] = rest.split(";", 1)[0]
    _write(JAR, jar)


class SignedOut(RuntimeError):
    pass


def _list_page(page, rows=PAGE_ROWS):
    """One page of the Mouse List's own data call. A sign-in page, a redirect
    or anything that is not the list's JSON means the session is gone."""
    body = urllib.parse.urlencode({"_search": "false", "nd": str(int(time.time() * 1000)),
                                   "rows": str(rows), "page": str(page),
                                   "sidx": "birthDate", "sord": "asc"}).encode()
    req = urllib.request.Request(LIST_URL, data=body, headers={
        "Cookie": _cookie_header(),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis-SoftMouse",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json"})
    opener = urllib.request.build_opener(vos._NoRedirect)
    try:
        with opener.open(req, timeout=90) as r:
            _absorb_set_cookies(r.headers)
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SignedOut("SoftMouse answered %s" % e.code)
    try:
        d = json.loads(text)
    except ValueError:
        raise SignedOut("SoftMouse sent a page, not the list")
    if not isinstance(d, dict) or "list" not in d:
        raise SignedOut("SoftMouse sent something other than the list")
    return d


def check_session():
    if not _jar():
        _status_update(signed_in=False, checked=time.time())
        return False
    st = _read(STATUS, {})
    try:
        _list_page(1, rows=1)
        ok = True
    except SignedOut:
        ok = False
    except OSError as e:
        _status_update(check_error=str(e), checked=time.time())
        return None
    upd = {"signed_in": ok, "checked": time.time(), "check_error": None}
    if ok:
        upd["last_ok"] = time.time()
    elif st.get("signed_in"):
        upd["lost_at"] = time.time()
        upd["lived_s"] = round(time.time() - (st.get("signed_in_at") or time.time()))
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


# --- signing in -------------------------------------------------------------------

SIGNED_IN_JS = r"""
(() => {
  const t = document.body ? document.body.innerText : '';
  return !document.querySelector('input[type=password]') && /Family Tree/.test(t)
         && /Matings/.test(t) && /Mouselines/i.test(t);
})()
"""


AUTO_LOGIN_WAIT_S = 60

# The page's own submit (login.do?reqCode=doLogin, with its csrftoken).
FILL_JS = r"""
(() => {
  const u = document.querySelector('input[name=username]');
  const p = document.querySelector('input[name=password]');
  if (!u || !p || typeof submitForm !== 'function') return false;
  u.value = %s; p.value = %s;
  submitForm();
  return true;
})()
"""


def _login():
    saved = loginmod.here()
    if saved:
        return _auto_login(*saved)
    _step("opening Chrome for the SoftMouse sign-in")
    b = vos._Browser(headless=False, profile=PROFILE)
    try:
        b.tab.go(BASE + "/", settle=1)
        _step("waiting for you to sign in to SoftMouse in the Chrome window")
        end, ok = time.time() + LOGIN_WAIT_S, False
        while time.time() < end and not ok:
            try:
                ok = bool(b.tab.js(SIGNED_IN_JS, timeout=10))
            except RuntimeError:
                ok = False
            if not ok:
                time.sleep(1.5)
        if not ok:
            raise RuntimeError("the sign-in was not finished within %d minutes"
                               % (LOGIN_WAIT_S // 60))
        _keep_cookies(b)
    finally:
        b.close()
    _signed_in()


def _keep_cookies(b):
    time.sleep(1.5)
    mine = [c for c in b.tab.call("Network.getAllCookies")["cookies"]
            if "softmouse" in c.get("domain", "")]
    _write(JAR, mine)


def _signed_in(how=""):
    _status_update(signed_in=True, signed_in_at=time.time(), last_ok=time.time(),
                   lost_at=None, lived_s=None)
    _say("signed in" + how, done=True)


def _auto_login(username, password, quiet=False):
    """The lab's saved sign-in, typed by Jarvis into a Chrome nobody sees."""
    _step("signing in to SoftMouse with the lab's saved sign-in")
    b = vos._Browser(headless=True, profile=PROFILE)
    try:
        b.tab.go(BASE + "/", settle=1)
        if not b.tab.js(SIGNED_IN_JS, timeout=10):
            if not b.tab.js(FILL_JS % (json.dumps(username), json.dumps(password)),
                            timeout=15):
                raise RuntimeError("the SoftMouse sign-in page has changed; Jarvis "
                                   "could not find where to type. Use Forget, then "
                                   "Sign in by hand")
            end, ok = time.time() + AUTO_LOGIN_WAIT_S, False
            while time.time() < end and not ok:
                time.sleep(1.5)
                try:
                    ok = bool(b.tab.js(SIGNED_IN_JS, timeout=10))
                except RuntimeError:
                    ok = False
            if not ok:
                raise RuntimeError("SoftMouse did not accept the lab's saved sign-in "
                                   "(was the password changed?). Set it up again, or "
                                   "Forget it and Sign in by hand")
        _keep_cookies(b)
    finally:
        b.close()
    if quiet:
        _status_update(signed_in=True, signed_in_at=time.time(), last_ok=time.time(),
                       lost_at=None, lived_s=None)
    else:
        _signed_in(" with the lab's saved sign-in")


def _ensure_session():
    """Before a sync: a lapsed session signs itself back in when it can."""
    if check_session() is False and loginmod.here():
        _auto_login(*loginmod.here(), quiet=True)


# --- the jobs -----------------------------------------------------------------------

def _start(what, fn):
    with _LOCK:
        if RUN["running"]:
            return False
        RUN.update(running=True, what=what, step="", started=time.time(), error=None)

    def body():
        try:
            fn()
        except SignedOut:
            _status_update(signed_in=False, lost_at=time.time())
            msg = ("SoftMouse signed Jarvis out mid-read. Press Sync again."
                   if loginmod.here() else
                   "SoftMouse signed Jarvis out. Press Sign in, then Sync again.")
            RUN["error"] = msg
            _say(msg, level="error", done=True)
            _status_update(last_error={"at": time.time(), "what": what, "error": msg})
        except Exception as e:                           # noqa: BLE001
            RUN["error"] = str(e)
            _say(str(e), level="error", done=True)
            _status_update(last_error={"at": time.time(), "what": what, "error": str(e)})
        finally:
            RUN.update(running=False, step="")
    threading.Thread(target=body, daemon=True, name="jarvis-softmouse-" + what).start()
    return True


def _read_list():
    _step("reading the Mouse List")
    first = _list_page(1)
    mice, pages = list(first["list"]), int(first.get("total") or 1)
    for p in range(2, pages + 1):
        _step("reading the Mouse List, page %d of %d" % (p, pages))
        mice += _list_page(p)["list"]
    ids = {m.get("id") for m in mice}
    if len(ids) != int(first.get("records") or 0):
        raise RuntimeError("SoftMouse said %s mice but Jarvis read %d; nothing was sent"
                           % (first.get("records"), len(ids)))
    return mice


def _text(m, key):
    """A field as text. Some carry markup ("M444<br>" as a dam tag)."""
    v = m.get(key)
    return html.unescape(re.sub(r"<[^>]+>", " ", str(v))).strip() if v is not None else ""


def _live(m):
    return not m.get("enddate") and (m.get("mousestate") or "").lower() != "ended"


def softmouse_issues(live):
    """What is wrong in SoftMouse itself, in the lab's words."""
    out, seen = [], {}
    for m in live:
        tag = (m.get("physicaltag") or "").strip()
        if not tag:
            out.append({"category": SOFTMOUSE, "mouse": None,
                        "text": "a live %s mouse born %s has no physical tag; it cannot be "
                                "matched to the sheet" % (m.get("mouseline") or "",
                                                          m.get("dateofbirth") or "?")})
            continue
        seen.setdefault(tag, 0)
        seen[tag] += 1
        geno = (m.get("genotype") or "").strip()
        if not geno:
            out.append({"category": SOFTMOUSE, "mouse": tag,
                        "text": "%s has no genotype in SoftMouse; the sheet's YH, SST and "
                                "PV would read N/A" % tag})
        elif "YH(" not in geno.replace(" ", "").upper():
            out.append({"category": SOFTMOUSE, "mouse": tag,
                        "text": "%s's genotype '%s' has no YH result; YH would read N/A"
                                % (tag, geno)})
    for tag, n in seen.items():
        if n > 1:
            out.append({"category": SOFTMOUSE, "mouse": tag,
                        "text": "%s is on %d live mice in SoftMouse; the sheet gets "
                                "whichever comes last" % (tag, n)})
    return out


def sheet_issues(res):
    out = []
    sheet = res.get("sheet") or "the sheet"
    for d in res.get("sheetDuplicates") or []:
        out.append({"category": SHEET, "mouse": d["id"],
                    "text": "Mouse ID %s is on %d rows of %s (rows %s)"
                    % (d["id"], len(d["rows"]), sheet, ", ".join(str(x) for x in d["rows"]))})
    missing = res.get("notInSheet") or []
    if missing:
        out.append({"category": SHEET, "mouse": None,
                    "text": "%d live SoftMouse mice have no row in %s, so nothing was "
                            "written for them: %s" % (len(missing), sheet,
                                                      ", ".join(sorted(missing, key=vos._id_order)))})
    return out


def overwrites(res):
    """The changes a person must see: a genotype the sheet knew, replaced."""
    return [c for c in res.get("changes") or []
            if c["field"] != "Role" and c["from"].strip().lower() in KNOWN_GENOTYPES
            and c["from"].strip().lower() != c["to"].strip().lower()]


def _fetch():
    mice = _read_list()
    live = [m for m in mice if _live(m)]
    ended = [m for m in mice if not _live(m)]
    if not live:
        raise RuntimeError("SoftMouse listed no live mice; nothing was sent")
    last = (_read(STATUS, {}).get("last_sync") or {}).get("mice")
    if last and len(live) < MIN_SHARE_OF_LAST * last:
        raise RuntimeError("only %d live mice, against %d last time. That looks like a "
                           "broken read rather than a colony; nothing was sent"
                           % (len(live), last))

    now = dt.datetime.now()
    stamp = now.strftime("%m%d%y")
    os.makedirs(ARCHIVE, exist_ok=True)
    path = os.path.join(ARCHIVE, "SoftMouse List %s %s.csv" % (stamp, now.strftime("%H%M")))
    sexes = {"M": "Male", "F": "Female"}
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([h for h, _ in CSV_COLUMNS])
        for m in live:
            w.writerow([sexes.get(_text(m, k), _text(m, k)) if k == "sex" else _text(m, k)
                        for _, k in CSV_COLUMNS])

    rows = [[_text(m, "physicaltag"), _text(m, "mousestate"), _text(m, "genotype")]
            for m in live]
    return {"stamp": stamp, "mice": len(live), "ended": len(ended), "csv": path,
            "payload": {"kind": "softmouse", "stamp": stamp,
                        "mice": [{"tag": t, "state": s, "genotype": g} for t, s, g in rows if t],
                        "block": {"headers": ["Physical Tag " + stamp, "State " + stamp,
                                              "Genotype " + stamp],
                                  "rows": rows}},
            "issues": softmouse_issues(live),
            "list": rows,
            "ended_list": [[_text(m, "physicaltag"), _text(m, "enddate"),
                            _text(m, "endtype"), _text(m, "endreason")] for m in ended]}


def _summary(got, res, applied):
    return {"at": time.time(), "stamp": got["stamp"], "mice": got["mice"],
            "ended": got["ended"], "csv": got["csv"], "applied": applied,
            "sheet": res.get("sheet"), "result": res,
            "overwrites": overwrites(res),
            "issues": got["issues"] + sheet_issues(res)}


def _record(summ, outcome, got):
    try:
        at = dt.datetime.fromtimestamp(summ["at"])
        person, machine = (WHO["fn"] or (lambda: (None, None)))()
        res = summ.get("result") or {}
        rec = {"v": 1, "date": at.date().isoformat(), "time": at.strftime("%H:%M"),
               "stamp": summ.get("stamp"), "source": "Jarvis", "outcome": outcome,
               "by": person, "machine": machine, "sheet": summ.get("sheet"),
               "block_at": res.get("blockAt"), "mice": summ.get("mice"),
               "issues": summ.get("issues") or [], "result": res,
               "csv": os.path.basename(summ.get("csv") or "") or None,
               "list": got.get("list") or [], "ended_list": got.get("ended_list") or []}
        _write(os.path.join(HISTORY, at.strftime("%Y-%m-%d %H%M%S") + " jarvis.json"), rec)
    except Exception as e:                               # noqa: BLE001
        _say("the sheet is synced, but Jarvis could not keep its record: %s" % e,
             level="warn")


def _post(payload, mode):
    """The sheet, refusing any answer that is not SoftMouse's. A script from
    before softMouseFromJarvis_ ignores "kind" and would read the list as a
    VOS census of nobody -- applied, that retires the colony."""
    res = vos._post_sheet(payload, mode)
    if res.get("kind") != "softmouse":
        raise RuntimeError("the sheet's script is older than Jarvis's SoftMouse sync. "
                           "Paste the new SoftMouse_Import.gs and VOS_Import.gs into "
                           "Apps Script and deploy a new version; nothing was written")
    return res


def _sync():
    if not vos._config().get("webapp_url"):
        raise RuntimeError("the sheet is not connected yet: paste the web app URL "
                           "under VOS log in (one link serves both)")
    _ensure_session()
    got = _fetch()
    _step("asking the sheet what would change")
    pre = _post(got["payload"], "preview")
    held = overwrites(pre)
    if held:
        HOLD.update(preview=_summary(got, pre, False), payload=got["payload"], record=got)
        _status_update(last_fetch=HOLD["preview"])
        _say("%d genotype(s) the sheet already had would change; waiting for you in Misc"
             % len(held), level="warn", done=True)
        return
    _step("writing to the sheet")
    res = _post(got["payload"], "apply")
    summ = _summary(got, res, True)
    HOLD.update(preview=None, payload=None, record=None)
    _status_update(last_sync=summ, last_fetch=summ, last_error=None)
    _record(summ, "applied", got)
    _say("synced: %s matched, %d change(s), %d issue(s) to look at in Misc" % (
        res.get("matched"), len(res.get("changes") or []), len(summ["issues"])),
        level="warn" if summ["issues"] else "info", done=True)


def _apply():
    if not HOLD["payload"]:
        raise RuntimeError("there is nothing waiting to apply")
    _step("writing to the sheet")
    pre, got = HOLD["preview"], HOLD["record"]
    res = _post(HOLD["payload"], "apply")
    summ = dict(pre, at=time.time(), applied=True, result=res, sheet=res.get("sheet"),
                overwrites=overwrites(res),
                issues=[i for i in pre["issues"] if i["category"] != SHEET] + sheet_issues(res))
    HOLD.update(preview=None, payload=None, record=None)
    _status_update(last_sync=summ, last_fetch=summ, last_error=None)
    _record(summ, "applied", got)
    _say("applied: %s matched, %d change(s)" % (res.get("matched"),
                                               len(res.get("changes") or [])), done=True)


def _same(row):
    """State and genes, so that "PV-Cre(het), YH(WT)" equals "YH(WT), PV-Cre(het)"."""
    genes = sorted(g.replace(" ", "").lower() for g in (row[2] or "").split(",") if g.strip())
    return (row[1] or "").lower(), tuple(genes)


def history():
    """Every sync, newest first, with what SoftMouse itself changed since the
    one before: mice new to the list, mice gone from it, genotypes and states
    that moved. A discarded sync is compared but never becomes the baseline."""
    recs = []
    if os.path.isdir(HISTORY):
        for name in os.listdir(HISTORY):
            if name.endswith(".json"):
                rec = _read(os.path.join(HISTORY, name), None)
                if isinstance(rec, dict):
                    recs.append((name, rec))
    recs = [r for _, r in sorted(recs, key=lambda nr: (nr[1].get("date") or "",
                                                       nr[1].get("time") or "", nr[0]))]
    out, prev = [], None
    for r in recs:
        cur = {row[0]: row for row in r.get("list") or [] if row and row[0]}
        diff = None
        if prev is not None and cur:
            both = sorted(set(cur) & set(prev), key=vos._id_order)
            diff = {"arrived": sorted(set(cur) - set(prev), key=vos._id_order),
                    "left": sorted(set(prev) - set(cur), key=vos._id_order),
                    "changed": [{"id": t, "from": "%s · %s" % (prev[t][1], prev[t][2] or "(no genotype)"),
                                 "to": "%s · %s" % (cur[t][1], cur[t][2] or "(no genotype)")}
                                for t in both if _same(prev[t]) != _same(cur[t])]}
        item = {k: r.get(k) for k in ("date", "time", "stamp", "source", "outcome", "by",
                                      "machine", "sheet", "block_at", "issues", "result")}
        item.update(mice=len(cur), diff=diff, applied=r.get("outcome") == "applied",
                    csv=os.path.join(ARCHIVE, r["csv"]) if r.get("csv") else None)
        out.append(item)
        if cur and r.get("outcome") != "discarded":
            prev = cur
    return out[::-1]


# --- routes ---------------------------------------------------------------------

def status():
    st = _read(STATUS, {})
    return {
        "ok": True,
        "signed_in": st.get("signed_in"),
        "signed_in_at": st.get("signed_in_at"),
        "checked": st.get("checked"),
        "lost_at": st.get("lost_at"),
        "lived_s": st.get("lived_s"),
        "has_session": bool(_jar()),
        # The lab's sign-in on this machine? (Whether the cloud has one is
        # only asked when someone types the PIN: this is polled.)
        "auto": {"here": os.path.isfile(loginmod.LOCAL), "hint": loginmod.HINT},
        "sheet_connected": bool(vos._config().get("webapp_url")),
        "run": {k: RUN.get(k) for k in ("running", "what", "step", "started", "error")},
        "hold": HOLD["preview"],
        "last_sync": st.get("last_sync"),
        "last_error": st.get("last_error"),
    }


def install(app, fail, who=None):
    os.makedirs(STATE, exist_ok=True)
    WHO["fn"] = who
    threading.Thread(target=_keepalive, daemon=True,
                     name="jarvis-softmouse-keepalive").start()

    def busy():
        return jsonify({"ok": False, "error": "SoftMouse is already %s" % (
            "signing in" if RUN["what"] == "login" else "syncing")}), 409

    @app.route("/api/softmouse/status")
    def api_softmouse_status():
        if request.args.get("check") == "1" and not RUN["running"]:
            check_session()
        return jsonify(status())

    @app.route("/api/softmouse/login", methods=["POST"])
    def api_softmouse_login():
        return jsonify(status()) if _start("login", _login) else busy()

    @app.route("/api/softmouse/unlock", methods=["POST"])
    def api_softmouse_unlock():
        pin = str((request.get_json(silent=True) or {}).get("pin") or "").strip()
        if not pin:
            return jsonify({"ok": False, "error": "type the PIN"}), 400
        if RUN["running"]:
            return busy()
        try:
            loginmod.unlock(pin)
        except loginmod.WrongPin as e:
            return jsonify({"ok": False, "error": str(e), "hint": loginmod.HINT}), 403
        except Exception as e:                           # noqa: BLE001
            return jsonify({"ok": False, "error": str(e)}), 400
        _say("the lab's sign-in is kept on this machine now")
        _start("login", _login)
        return jsonify(status())

    @app.route("/api/softmouse/forget", methods=["POST"])
    def api_softmouse_forget():
        loginmod.forget_here()
        return jsonify(status())

    @app.route("/api/softmouse/sync", methods=["POST"])
    def api_softmouse_sync():
        return jsonify(status()) if _start("sync", _sync) else busy()

    @app.route("/api/softmouse/apply", methods=["POST"])
    def api_softmouse_apply():
        if not HOLD["payload"]:
            return jsonify({"ok": False, "error": "nothing is waiting to apply"}), 400
        return jsonify(status()) if _start("apply", _apply) else busy()

    @app.route("/api/softmouse/discard", methods=["POST"])
    def api_softmouse_discard():
        if HOLD["preview"]:
            _record(dict(HOLD["preview"], at=time.time()), "discarded", HOLD["record"] or {})
        HOLD.update(preview=None, payload=None, record=None)
        return jsonify(status())

    @app.route("/api/softmouse/history")
    def api_softmouse_history():
        try:
            return jsonify({"ok": True, "syncs": history()})
        except Exception as e:                           # noqa: BLE001
            return fail("softmouse history", e)
