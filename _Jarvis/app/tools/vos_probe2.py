# -*- coding: utf-8 -*-
"""Stage two of the VOS probe: headless, on the saved session.

vos_probe.py found that the Cages filter is a plain GET
(/cages?form[protocol_id]=415&form[status]=active&per_page=200) and that the
session survives a relaunch only by putting the saved cookies back. This uses
both: list every active X6-041 cage across pages, open the print page for
them, save it as a PDF, and hand that to VOS_report_parser.py. GETs only.

    python tools/vos_probe2.py --out <folder>
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vos_probe as P  # noqa: E402

PROTOCOL_ID = "415"      # X6-041 (Barry, J.)

ROWS = r"""
(() => ({
  ids: [...document.querySelectorAll('input[name=cage_select]')].map(c => c.value),
  selAll: [...document.querySelectorAll('label, span, div, p')].map(e => e.textContent.trim())
            .find(t => /^Select All on Page/.test(t) && t.length < 60) || '',
  next: (() => { const a = [...document.querySelectorAll('.pagination a, a[rel=next]')]
            .find(a => a.getAttribute('rel') === 'next' || /next|›|»/i.test(a.textContent));
          return a ? a.getAttribute('href') : ''; })(),
  pages: [...document.querySelectorAll('.pagination a')].map(a => [a.textContent.trim(), a.getAttribute('href')])
}))()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    log = []

    def say(line):
        print(line, flush=True)
        log.append(line)

    port = P.free_port()
    proc = P.launch(headless=True, port=port)
    try:
        tab = P.open_tab(port)
        with open(P.JAR, encoding="utf-8") as fh:
            jar = json.load(fh)
        tab.call("Network.setCookies", {"cookies": [
            {k: c[k] for k in ("name", "value", "domain", "path", "secure",
                               "httpOnly", "sameSite", "expires") if k in c}
            for c in jar]})

        ids, page = [], 1
        while True:
            q = urllib.parse.urlencode({"form[protocol_id]": PROTOCOL_ID,
                                        "form[status]": "active",
                                        "per_page": "200", "page": str(page)})
            href = tab.go(P.BASE + "/cages?" + q, settle=2)
            if not P.signed_in(href):
                say("signed out: %s" % href)
                return 1
            got = tab.js(ROWS)
            say("page %d: %d cages, %r, next=%r, pagination=%s" % (
                page, len(got["ids"]), got["selAll"], got["next"], got["pages"][:8]))
            new = [i for i in got["ids"] if i not in ids]
            ids += new
            if not new or not got["next"] or page >= 20:
                break
            page += 1
        tab.shot(os.path.join(a.out, "b_filtered.png"))
        say("%d active X6-041 cages: %s" % (len(ids), ids))

        url = P.BASE + "/cage_cards/print?" + "&".join(
            "cage_ids%5B%5D=" + i for i in ids)
        tab.go(url, settle=4, limit=120)
        pdesc = tab.js(P.PRINT_DESCRIBE)
        P.save(a.out, "b_print_page.json", pdesc)
        P.save(a.out, "b_print_page.html", tab.js("document.documentElement.outerHTML"))
        tab.shot(os.path.join(a.out, "b_print.png"))
        say("print page: %r, window.print called: %s, selects: %s" % (
            pdesc["title"], pdesc["printCalled"],
            [(s["name"] or s["id"], s["value"]) for s in pdesc["selects"]]))

        parser = P.load_parser()
        for bg in (False, True):
            pdf = tab.call("Page.printToPDF", {
                "printBackground": bg, "preferCSSPageSize": True,
                "paperWidth": 8.5, "paperHeight": 11}, timeout=180)["data"]
            name = "b_cards_bg%d.pdf" % bg
            path = P.save(a.out, name, base64.b64decode(pdf), "wb")
            say("--- parser on %s (%d KB)" % (name, os.path.getsize(path) // 1024))
            recs = parser.parse_pdf(path, debug_dir=os.path.join(a.out, "debug_bg%d" % bg))
            say("    %d mouse rows, %d with warnings" % (
                len(recs), len([r for r in recs if r["Parse Warnings"]])))
            sub = []
            P.compare_with_last(recs, sub)
            for line in sub:
                say("    " + line)
    finally:
        P.close_browser(port, proc)
        P.save(a.out, "probe2_log.txt", "\n".join(log) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
