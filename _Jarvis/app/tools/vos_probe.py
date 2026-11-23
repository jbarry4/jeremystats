# -*- coding: utf-8 -*-
"""Find out how VOS can be read without a person clicking through it.

VOS (uvm.vos.redplank.co) signs in only through myUVM + Duo, so the sync has
to borrow a browser that stays signed in. This opens Chrome on a profile of
its own (never the everyday one), waits for the sign-in, and then looks --
GETs only, nothing is edited, retired, transferred or printed on paper:

  1. the Cages page: its filter form, the per-page control, the row ids;
  2. the same list filtered to X6-041 / Active / 200 a page;
  3. whether the list or a cage answers as .json / .csv;
  4. the cage-card print page for those cages, saved as HTML and as a PDF
     made the way Chrome's "Save as PDF" makes one, then fed to the existing
     VOS_report_parser.py and compared with the last hand-made export;
  5. which cookies hold the session and how long they last, then a headless
     relaunch on the same profile: still signed in, or not.

    python tools/vos_probe.py --out <folder>

Run it from PowerShell. The profile and a copy of the session cookies live
in %LOCALAPPDATA%\\Jarvis\\vos -- machine-local, never in the repository.
"""
import argparse
import base64
import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ui_shots import CDP, free_port  # noqa: E402

BASE = "https://uvm.vos.redplank.co"
PROTOCOL = "X6-041"
CHROME = os.environ.get("CHROME") or next(
    (p for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"))
     if os.path.exists(p)), None)
STATE = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "Jarvis", "vos")
PROFILE = os.path.join(STATE, "chrome-profile")
JAR = os.path.join(STATE, "cookies.json")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PARSER = os.path.join(REPO, "Colony Management", "VOS Exports",
                      "VOS Report to CSV", "VOS_report_parser.py")
LAST_EXPORT = os.path.join(os.path.dirname(PARSER), "VOS Report 110326.csv")


class Tab(CDP):
    """A CDP page that also keeps the network requests it sees."""

    def __init__(self, ws_url, timeout=60):
        super().__init__(ws_url, timeout)
        self.requests = []

    def call(self, method, params=None, timeout=60):
        self.n += 1
        mid = self.n
        self._send_frame(json.dumps({"id": mid, "method": method,
                                     "params": params or {}}).encode())
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self._recv_message())
            if msg.get("method") == "Network.requestWillBeSent":
                p = msg.get("params") or {}
                self.requests.append({"type": p.get("type"),
                                      "method": (p.get("request") or {}).get("method"),
                                      "url": (p.get("request") or {}).get("url")})
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"]))
                return msg.get("result") or {}
        raise RuntimeError("no answer to %s" % method)

    def go(self, url, settle=1.5, limit=60):
        self.call("Page.navigate", {"url": url})
        time.sleep(0.6)
        self.until("document.readyState === 'complete'", limit=limit)
        time.sleep(settle)
        return self.js("location.href")


def launch(headless, port):
    args = [CHROME, "--remote-debugging-port=%d" % port,
            "--remote-allow-origins=*", "--user-data-dir=" + PROFILE,
            "--no-first-run", "--no-default-browser-check",
            "--window-size=1400,1000"]
    if headless:
        args += ["--headless=new", "--disable-gpu"]
    args.append("about:blank")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def page_ws(port, limit=30):
    end = time.time() + limit
    while time.time() < end:
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json/list" % port, timeout=2) as r:
                for t in json.loads(r.read().decode()):
                    if t.get("type") == "page":
                        return t["webSocketDebuggerUrl"]
        except Exception:                                # noqa: BLE001
            pass
        time.sleep(0.3)
    raise RuntimeError("Chrome did not open DevTools")


def open_tab(port):
    tab = Tab(page_ws(port))
    tab.call("Page.enable")
    tab.call("Runtime.enable")
    tab.call("Network.enable")
    # The print page may call window.print() on load; a print dialog would
    # freeze the page for the rest of the probe.
    tab.call("Page.addScriptToEvaluateOnNewDocument", {
        "source": "window.print = function () { window.__printCalled = true; };"})
    return tab


def close_browser(port, proc):
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/json/version" % port, timeout=3) as r:
            CDP(json.loads(r.read().decode())["webSocketDebuggerUrl"])._post(
                "Browser.close", {})
    except Exception:                                    # noqa: BLE001
        pass
    try:
        proc.wait(timeout=15)
    except Exception:                                    # noqa: BLE001
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)


def signed_in(href):
    return (href or "").startswith(BASE) and "/users/sign_in" not in href \
        and "/auth/" not in href


def save(out, name, data, mode="w"):
    path = os.path.join(out, name)
    if mode == "wb":
        with open(path, "wb") as fh:
            fh.write(data)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else
                     json.dumps(data, indent=1, ensure_ascii=False))
    return path


# --- what the Cages page is made of ----------------------------------------
DESCRIBE = r"""
(() => {
  const field = e => ({name: e.name, tag: e.tagName, type: e.type, id: e.id,
    value: e.value, inForm: !!e.form,
    options: e.options ? [...e.options].slice(0, 300).map(o => [o.value, o.text.trim()]) : undefined});
  const forms = [...document.forms].map(f => ({id: f.id, cls: f.className,
    action: f.getAttribute('action'), method: f.getAttribute('method') || 'get',
    fields: [...f.elements].filter(e => e.name).map(field)}));
  const loose = [...document.querySelectorAll('select, input')]
    .filter(e => !e.form && (e.name || e.id)).map(field);
  const rows = [...document.querySelectorAll('table tbody tr')];
  const firstRows = rows.slice(0, 3).map(r => r.outerHTML.slice(0, 1500));
  const hrefs = [...new Set([...document.querySelectorAll('a[href]')]
    .map(a => a.getAttribute('href')))].slice(0, 200);
  const buttons = [...document.querySelectorAll('button, a.btn, input[type=submit]')]
    .map(b => [b.tagName, (b.textContent || b.value || '').trim().slice(0, 40),
               b.getAttribute('href') || b.getAttribute('data-url') || '',
               b.getAttribute('onclick') || '', b.id, b.className.slice(0, 60)]);
  const selAll = [...document.querySelectorAll('label, span, div, p')]
    .map(e => e.textContent.trim()).find(t => /^Select All on Page/.test(t) && t.length < 60);
  const paging = [...document.querySelectorAll('.pagination a, nav a, a[rel=next]')]
    .map(a => [a.textContent.trim(), a.getAttribute('href')]).slice(0, 30);
  const scripts = [...document.scripts].map(s => s.src || ('inline:' + s.textContent.length));
  return {url: location.href, title: document.title, forms, loose, rows: rows.length,
          firstRows, hrefs, buttons, selAll, paging, scripts};
})()
"""

# Fill the filter the way a person would, but only READ the URL it would
# submit to -- a GET form's query is the whole request.
FILTER_URL = r"""
((protocol) => {
  const pick = (sel, re) => { const o = [...sel.options].find(o => re.test(o.text.trim()));
                              if (o) { sel.value = o.value; return o.value; } return null; };
  const sels = [...document.querySelectorAll('select')];
  const proto = sels.find(s => [...s.options].some(o => o.text.includes(protocol)));
  if (!proto) return {error: 'no select offers ' + protocol};
  const form = proto.form;
  const report = {protocolField: proto.name, protocolValue: pick(proto, new RegExp(protocol.replace('-', '\\-'))),
                  method: form ? (form.getAttribute('method') || 'get') : null,
                  action: form ? form.action : null};
  const status = sels.find(s => [...s.options].some(o => /^Active$/i.test(o.text.trim()))
                                && [...s.options].some(o => /retired|inactive|all/i.test(o.text)));
  if (status) { report.statusField = status.name; report.statusValue = pick(status, /^Active$/i); }
  const per = sels.find(s => [...s.options].some(o => o.text.trim() === '200'));
  if (per) { report.perField = per.name || per.id; report.perValue = pick(per, /^200$/);
             report.perInForm = !!per.form; }
  if (!form) return Object.assign(report, {error: 'protocol select has no form'});
  const q = new URLSearchParams(new FormData(form));
  if (per && !per.form && per.name) q.set(per.name, per.value);
  report.url = form.action.split('?')[0] + '?' + q.toString();
  return report;
})(%s)
"""

ROW_IDS = r"""
(() => {
  const rows = [...document.querySelectorAll('table tbody tr')];
  return rows.map(r => {
    const cb = r.querySelector('input[type=checkbox]');
    const a = [...r.querySelectorAll('a[href]')].find(a => /C-\d+/.test(a.textContent));
    return {label: a ? a.textContent.trim() : r.cells[1] ? r.cells[1].textContent.trim() : '',
            href: a ? a.getAttribute('href') : '',
            cbName: cb ? cb.name : '', cbValue: cb ? cb.value : '',
            cbData: cb ? JSON.stringify(cb.dataset) : '',
            text: [...r.cells].map(c => c.textContent.trim()).join(' | ').slice(0, 300)};
  });
})()
"""

TRY_FORMATS = r"""
(async (urls) => {
  const out = [];
  for (const u of urls) {
    for (const accept of ['application/json', 'text/csv']) {
      try {
        const r = await fetch(u, {credentials: 'same-origin', headers: {Accept: accept},
                                  redirect: 'manual'});
        const t = r.type === 'opaqueredirect' ? '' : await r.text();
        out.push({url: u, accept, status: r.status, type: r.headers.get('content-type'),
                  head: t.slice(0, 400)});
      } catch (e) { out.push({url: u, accept, error: String(e)}); }
    }
  }
  return out;
})(%s)
"""

PRINT_DESCRIBE = r"""
(() => ({
  url: location.href, title: document.title, printCalled: !!window.__printCalled,
  selects: [...document.querySelectorAll('select')].map(s => ({name: s.name, id: s.id, value: s.value,
            options: [...s.options].map(o => [o.value, o.text.trim()])})),
  bodyClasses: document.body.className,
  textLen: document.body.innerText.length,
  firstCard: (document.querySelector('[class*=card]') || document.body).outerHTML.slice(0, 4000),
  classes: [...new Set([...document.querySelectorAll('*')].map(e => e.className)
            .filter(c => typeof c === 'string' && c))].slice(0, 120)
}))()
"""


def load_parser():
    spec = importlib.util.spec_from_file_location("vos_report_parser", PARSER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def compare_with_last(records, log):
    if not os.path.exists(LAST_EXPORT):
        log.append("no %s to compare with" % LAST_EXPORT)
        return
    with open(LAST_EXPORT, encoding="utf-8-sig") as fh:
        old = {(r["Extracted Sorting ID 110326"], r["Cage Card 110326"])
               for r in csv.DictReader(fh)}
    new = {(str(r["Extracted Sorting ID"]), r["Cage Card"]) for r in records}
    log.append("vs 110326 export: %d rows then, %d now, %d identical (id, cage)"
               % (len(old), len(new), len(old & new)))
    log.append("  only in the 110326 export: %s" % sorted(old - new))
    log.append("  only in today's probe:     %s" % sorted(new - old))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--login-wait", type=float, default=420)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(PROFILE, exist_ok=True)
    if not CHROME:
        print("Chrome not found")
        return 2
    log = []

    def say(line):
        print(line, flush=True)
        log.append(line)

    port = free_port()
    proc = launch(headless=False, port=port)
    try:
        tab = open_tab(port)
        href = tab.go(BASE + "/cages")
        if not signed_in(href):
            say("waiting for the myUVM / Duo sign-in in the Chrome window ...")
            tab.go(BASE + "/auth/sso/new", settle=0.5)
            end = time.time() + a.login_wait
            while time.time() < end:
                try:
                    href = tab.js("location.href", timeout=10)
                except RuntimeError:
                    href = ""
                if signed_in(href):
                    break
                time.sleep(1)
        if not signed_in(href):
            say("never signed in (last page: %s)" % href)
            return 1
        say("signed in; landed on %s" % href)
        time.sleep(2)

        # 1. the Cages page as it comes
        tab.requests.clear()
        tab.go(BASE + "/cages", settle=2.5)
        desc = tab.js(DESCRIBE)
        desc["requests"] = [r for r in tab.requests if r["type"] in ("XHR", "Fetch", "Document")]
        save(a.out, "1_cages_page.json", desc)
        save(a.out, "1_cages_page.html", tab.js("document.documentElement.outerHTML"))
        say("cages page: %s rows, %s, %d forms" % (desc["rows"], desc["selAll"], len(desc["forms"])))

        # 2. filtered to the protocol
        filt = tab.js(FILTER_URL % json.dumps(PROTOCOL))
        save(a.out, "2_filter.json", filt)
        say("filter: %s" % json.dumps(filt)[:600])
        ids = []
        if filt.get("url") and (filt.get("method") or "get").lower() == "get":
            tab.requests.clear()
            tab.go(filt["url"], settle=3)
            rows = tab.js(ROW_IDS)
            desc2 = tab.js(DESCRIBE)
            desc2["requests"] = [r for r in tab.requests if r["type"] in ("XHR", "Fetch", "Document")]
            save(a.out, "2_filtered_page.json", desc2)
            save(a.out, "2_rows.json", rows)
            tab.shot(os.path.join(a.out, "2_filtered.png"))
            for r in rows:
                digits = "".join(ch for ch in r["label"] if ch.isdigit())
                if digits:
                    ids.append(digits)
            say("filtered page: %d rows, %s, paging=%s" % (
                len(rows), desc2["selAll"], desc2["paging"][:6]))
            say("cage ids: %s" % ids)
        else:
            say("filter form is not a plain GET; not submitting it")

        # 3. does anything answer as data?
        tries = [BASE + "/cages.json", BASE + "/cages.csv"]
        if filt.get("url"):
            path, _, q = filt["url"].partition("?")
            tries += [path + ".json?" + q, path + ".csv?" + q]
        if ids:
            tries += [BASE + "/cages/%s.json" % ids[0], BASE + "/cages/%s" % ids[0]]
        fmts = tab.js(TRY_FORMATS % json.dumps(tries), timeout=120)
        save(a.out, "3_formats.json", fmts)
        for f in fmts:
            say("  %-70s %-17s -> %s %s" % (f["url"][len(BASE):][:70], f["accept"],
                                           f.get("status"), (f.get("type") or "")[:40]))
        if ids:
            tab.go(BASE + "/cages/%s" % ids[0], settle=2)
            save(a.out, "3_cage_detail.html", tab.js("document.documentElement.outerHTML"))
            tab.shot(os.path.join(a.out, "3_cage_detail.png"))

        # 4. the print page, and a PDF of it
        if ids:
            url = BASE + "/cage_cards/print?" + "&".join(
                "cage_ids%5B%5D=" + i for i in ids)
            tab.go(url, settle=4, limit=120)
            pdesc = tab.js(PRINT_DESCRIBE)
            save(a.out, "4_print_page.json", pdesc)
            save(a.out, "4_print_page.html", tab.js("document.documentElement.outerHTML"))
            say("print page: %s, window.print called: %s, selects: %s" % (
                pdesc["title"], pdesc["printCalled"],
                [(s["name"] or s["id"], s["value"]) for s in pdesc["selects"]]))
            parser = load_parser()
            for bg in (False, True):
                pdf = tab.call("Page.printToPDF", {
                    "printBackground": bg, "preferCSSPageSize": True,
                    "paperWidth": 8.5, "paperHeight": 11}, timeout=180)["data"]
                name = "4_cards_bg%d.pdf" % bg
                path = save(a.out, name, base64.b64decode(pdf), "wb")
                say("--- parser on %s (%d KB)" % (name, os.path.getsize(path) // 1024))
                recs = parser.parse_pdf(path)
                say("    %d mouse rows, %d with warnings" % (
                    len(recs), len([r for r in recs if r["Parse Warnings"]])))
                sub = []
                compare_with_last(recs, sub)
                for line in sub:
                    say("    " + line)

        # 5. the session: which cookies, how long they live
        cookies = tab.call("Network.getAllCookies")["cookies"]
        mine = [c for c in cookies if any(d in c["domain"] for d in
                ("redplank", "uvm.edu", "duosecurity"))]
        save(a.out, "5_cookies.json", [{
            "name": c["name"], "domain": c["domain"], "session": c.get("session"),
            "expires": (time.strftime("%Y-%m-%d %H:%M", time.localtime(c["expires"]))
                        if c.get("expires", -1) > 0 else "session"),
            "httpOnly": c.get("httpOnly")} for c in mine])
        for c in mine:
            say("  cookie %-40s %-28s %s" % (c["name"][:40], c["domain"][:28],
                time.strftime("%Y-%m-%d %H:%M", time.localtime(c["expires"]))
                if c.get("expires", -1) > 0 else "session"))
        with open(JAR, "w", encoding="utf-8") as fh:
            json.dump(mine, fh)
    finally:
        close_browser(port, proc)

    # 5b. headless, same profile: still signed in?
    port = free_port()
    proc = launch(headless=True, port=port)
    try:
        tab = open_tab(port)
        href = tab.go(BASE + "/cages", settle=2)
        say("headless relaunch, profile only: %s (%s)" % (
            "SIGNED IN" if signed_in(href) else "signed out", href))
        if not signed_in(href):
            with open(JAR, encoding="utf-8") as fh:
                jar = json.load(fh)
            tab.call("Network.setCookies", {"cookies": [
                {k: c[k] for k in ("name", "value", "domain", "path", "secure",
                                   "httpOnly", "sameSite", "expires") if k in c}
                for c in jar]})
            href = tab.go(BASE + "/cages", settle=2)
            say("headless relaunch, cookies restored: %s (%s)" % (
                "SIGNED IN" if signed_in(href) else "signed out", href))
            if not signed_in(href):
                href = tab.go(BASE + "/auth/sso/new", settle=6)
                say("headless relaunch, silent SSO bounce: %s (%s)" % (
                    "SIGNED IN" if signed_in(href) else "signed out", href))
    finally:
        close_browser(port, proc)
        save(a.out, "probe_log.txt", "\n".join(log) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
