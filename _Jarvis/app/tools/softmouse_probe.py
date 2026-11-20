# -*- coding: utf-8 -*-
"""Find out how SoftMouse.NET can be read without a person clicking through it.

By hand: sign in at softmouse.net, Mice > Mouse List, the cloud icon to
export, wait for the export, download the .xlsx, paste Physical Tag / State /
Genotype into "SoftMouse Imports", Lab Tools > Sync SoftMouse to KCNT1.

This opens Chrome on a profile of its own (never the everyday one), waits for
a person to sign in, then only looks -- GETs and the page's own list loads,
nothing is edited, ended or exported:

  1. the page after sign-in, and the Mice tab's Mouse List: its HTML, every
     XHR / fetch it makes (with the POST bodies and the responses), which is
     where a jqGrid list gets its rows;
  2. the export control: what it would call, without calling it;
  3. the session cookies, saved, then the list's data call replayed with
     urllib and those cookies alone;
  4. a headless relaunch on the same profile: still signed in, or not.

    python tools/softmouse_probe.py --out <folder>

Run it from PowerShell. The profile and cookies live in
%LOCALAPPDATA%\\Jarvis\\softmouse -- machine-local, never in the repository.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vos_probe as P  # noqa: E402
from ui_shots import free_port  # noqa: E402

BASE = "https://www.softmouse.net"
STATE = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "Jarvis", "softmouse")
P.PROFILE = os.path.join(STATE, "chrome-profile")
JAR = os.path.join(STATE, "cookies.json")


class Tab(P.Tab):
    """Keeps request ids, POST bodies and response types too."""

    def call(self, method, params=None, timeout=60):
        self.n += 1
        mid = self.n
        self._send_frame(json.dumps({"id": mid, "method": method,
                                     "params": params or {}}).encode())
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self._recv_message())
            m = msg.get("method")
            if m == "Network.requestWillBeSent":
                p = msg.get("params") or {}
                rq = p.get("request") or {}
                self.requests.append({"id": p.get("requestId"), "type": p.get("type"),
                                      "method": rq.get("method"), "url": rq.get("url"),
                                      "post": rq.get("postData"),
                                      "headers": rq.get("headers")})
                continue
            if m == "Network.responseReceived":
                p = msg.get("params") or {}
                for r in self.requests:
                    if r["id"] == p.get("requestId"):
                        r["status"] = (p.get("response") or {}).get("status")
                        r["mime"] = (p.get("response") or {}).get("mimeType")
                continue
            if m:
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result") or {}
        raise RuntimeError("no answer to %s" % method)


def open_tab(port):
    tab = Tab(P.page_ws(port))
    tab.call("Page.enable")
    tab.call("Runtime.enable")
    tab.call("Network.enable")
    return tab


SIGNED_IN = r"""
(() => {
  const t = document.body ? document.body.innerText : '';
  const pw = !!document.querySelector('input[type=password]');
  return !pw && /Family Tree/.test(t) && /Matings/.test(t) && /Mouselines/i.test(t);
})()
"""

DESCRIBE = r"""
(() => ({
  href: location.href,
  title: document.title,
  links: [...document.querySelectorAll('a')].map(a => [a.textContent.trim().slice(0, 40), a.getAttribute('href'), a.getAttribute('onclick')])
           .filter(x => x[0] || x[2]).slice(0, 250),
  buttons: [...document.querySelectorAll('button, input[type=button], input[type=submit], [onclick], [title]')]
           .map(b => [b.tagName, (b.textContent || b.value || '').trim().slice(0, 40), b.getAttribute('title'), (b.getAttribute('onclick') || '').slice(0, 200), b.id, b.className.toString().slice(0, 60)])
           .slice(0, 250),
  grids: [...document.querySelectorAll('table.ui-jqgrid-btable, table[id]')].map(t => [t.id, t.rows.length]),
  jqgrid: (() => { try { return [...document.querySelectorAll('table.ui-jqgrid-btable')].map(t => {
            const g = window.jQuery(t); return { id: t.id, url: g.jqGrid('getGridParam', 'url'),
              datatype: g.jqGrid('getGridParam', 'datatype'), mtype: g.jqGrid('getGridParam', 'mtype'),
              postData: g.jqGrid('getGridParam', 'postData'), rowNum: g.jqGrid('getGridParam', 'rowNum'),
              records: g.jqGrid('getGridParam', 'records'),
              colNames: g.jqGrid('getGridParam', 'colNames') }; }); } catch (e) { return String(e); } })(),
  forms: [...document.querySelectorAll('form')].map(f => ({ id: f.id, action: f.getAttribute('action'), method: f.method,
           fields: [...f.elements].map(e => [e.name, e.type, e.type === 'password' ? '' : String(e.value).slice(0, 40)]).slice(0, 60) })),
  text: (document.body ? document.body.innerText : '').slice(0, 3000),
}))()
"""


def cookie_header(cookies, url):
    host = urllib.parse.urlparse(url).hostname or ""
    return "; ".join("%s=%s" % (c["name"], c["value"]) for c in cookies
                     if host.endswith(c["domain"].lstrip(".")))


def replay(req, cookies):
    """The list's own data call, with nothing but the saved cookies."""
    headers = {"Cookie": cookie_header(cookies, req["url"]),
               "User-Agent": (req.get("headers") or {}).get("User-Agent", "Mozilla/5.0"),
               "X-Requested-With": "XMLHttpRequest"}
    data = None
    if req.get("method") == "POST":
        data = (req.get("post") or "").encode()
        headers["Content-Type"] = (req.get("headers") or {}).get(
            "Content-Type", "application/x-www-form-urlencoded")
    r = urllib.request.Request(req["url"], data=data, headers=headers,
                               method=req.get("method") or "GET")
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.status, resp.headers.get("Content-Type"), resp.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--login-wait", type=float, default=480)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(P.PROFILE, exist_ok=True)
    log = []

    def say(line):
        print(line, flush=True)
        log.append(line)

    port = free_port()
    proc = P.launch(headless=False, port=port)
    try:
        tab = open_tab(port)
        tab.go(BASE + "/", settle=1)
        say("waiting for the SoftMouse sign-in in the Chrome window ...")
        end = time.time() + a.login_wait
        ok = False
        while time.time() < end:
            try:
                ok = bool(tab.js(SIGNED_IN, timeout=10))
            except RuntimeError:
                ok = False
            if ok:
                break
            time.sleep(1.5)
        if not ok:
            say("never signed in (last page: %s)" % tab.js("location.href"))
            return 1
        time.sleep(3)
        first = tab.js(DESCRIBE)
        say("signed in; on %s" % first["href"])
        P.save(a.out, "1_after_signin.json", first)

        # The Mice tab, the way a person gets to it.
        mice = next((l for l in first["links"] if l[0] == "Mice" and l[1]), None)
        say("Mice tab link: %s" % (mice,))
        tab.requests.clear()
        if mice:
            href = urllib.parse.urljoin(first["href"], mice[1])
            tab.go(href, settle=6, limit=90)
        desc = tab.js(DESCRIBE)
        xhr = [r for r in tab.requests if r["type"] in ("XHR", "Fetch")]
        for r in xhr:
            try:
                body = tab.call("Network.getResponseBody", {"requestId": r["id"]})
                r["body"] = (body.get("body") or "")[:20000]
            except RuntimeError as e:
                r["body_error"] = str(e)
        desc["xhr"] = xhr
        desc["documents"] = [r for r in tab.requests if r["type"] == "Document"]
        P.save(a.out, "2_mouse_list.json", desc)
        P.save(a.out, "2_mouse_list.html", tab.js("document.documentElement.outerHTML"))
        say("mouse list: %s; grids %s; %d XHR" % (desc["href"], desc["grids"], len(xhr)))
        say("jqgrid: %s" % json.dumps(desc["jqgrid"])[:1500])
        for r in xhr:
            say("  XHR %s %s %s [%s] post=%s body=%s" % (r["method"], r.get("status"), r["url"][:160],
                r.get("mime"), (r.get("post") or "")[:300], (r.get("body") or "")[:200].replace("\n", " ")))

        # The export control, looked at, not pressed.
        exp = [b for b in desc["buttons"] if any(k in json.dumps(b).lower()
               for k in ("export", "download", "excel", "xls", "cloud"))]
        say("export controls: %s" % json.dumps(exp)[:1500])

        cookies = tab.call("Network.getAllCookies").get("cookies") or []
        keep = [c for c in cookies if "softmouse" in c.get("domain", "")]
        P.save(a.out, "3_cookie_names.json",
               [{k: c.get(k) for k in ("name", "domain", "expires", "session", "httpOnly")} for c in keep])
        with open(JAR, "w", encoding="utf-8") as fh:
            json.dump(keep, fh)
        say("cookies: %s" % ", ".join("%s(%s)" % (c["name"], "session" if c.get("session") else
            time.strftime("%Y-%m-%d", time.localtime(c.get("expires", 0)))) for c in keep))

        data_calls = [r for r in xhr if r.get("status") == 200 and r["url"].startswith(BASE)]
        for i, r in enumerate(data_calls[:6]):
            try:
                st, ct, raw = replay(r, keep)
                P.save(a.out, "3_replay_%d.txt" % i, raw.decode("utf-8", "replace")[:200000])
                say("replay %d: %s %s %d bytes, same as the page's: %s" % (
                    i, st, ct, len(raw), raw.decode("utf-8", "replace")[:2000] == (r.get("body") or "")[:2000]))
            except Exception as e:                       # noqa: BLE001
                say("replay %d failed: %s" % (i, e))
    finally:
        P.close_browser(port, proc)

    # 4. Signed in after a relaunch, headless, on the same profile?
    port = free_port()
    proc = P.launch(headless=True, port=port)
    try:
        tab = open_tab(port)
        tab.go(BASE + "/", settle=2)
        say("headless relaunch on the profile: signed in = %s (%s)" % (
            bool(tab.js(SIGNED_IN)), tab.js("location.href")))
    finally:
        P.close_browser(port, proc)
    P.save(a.out, "log.txt", "\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
