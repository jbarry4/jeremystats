"""
check_review.py -- the review site (tools/export_review.py, review/), on a
made-up Monolith and a stand-in: nothing is deployed, nothing reaches the
cluster or Supabase.

  1. The gate and the functions under Node (review/check_site.mjs), with a
     stand-in for @vercel/functions.
  2. A made-up Monolith -- all four sessions, AB/CD, Progress -- served by
     Jarvis on a free port, and `build` run against it: every file the site
     needs and no link to the cluster, each array decompressing to its
     shape and to Jarvis's bytes, the budget leaving Progress's last files
     out, every lead's entry asked ahead under the name the page looks for.
  3. The pages in Edge, served as plain files: the Monolith reading the
     copy, a lead's link opening on its line and its sessions, a line that
     is not a lead saying it opens in Jarvis, the write-up's numbers.

    python tools/check_review.py
"""
from __future__ import annotations

import gzip
import http.server
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from types import SimpleNamespace

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "tools"))
os.chdir(APP)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

import numpy as np                                        # noqa: E402

from backend import app as appmod                         # noqa: E402
from backend import monolith as MO                        # noqa: E402
import check_monolith as CM                               # noqa: E402
import export_review as XR                                # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PASSED, FAILED = [], []


def check(name, cond, detail=None):
    (PASSED if cond else FAILED).append(name)
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond or detail is None else "   [%s]" % (detail,)), flush=True)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# --------------------------------------------------------------------------
def node_checks(work):
    print("\n1. The gate and the functions, under Node")
    d = os.path.join(work, "node")
    shutil.copytree(os.path.join(APP, "review", "site"), d)
    shutil.copyfile(os.path.join(APP, "review", "check_site.mjs"),
                    os.path.join(d, "check_site.mjs"))
    stubs = {
        "@vercel/functions": "export function next() { return new Response(null, "
                             "{ headers: { 'x-middleware-next': '1' } }); }\n",
    }
    for name, src in stubs.items():
        p = os.path.join(d, "node_modules", *name.split("/"))
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "package.json"), "w") as fh:
            json.dump({"name": name, "type": "module", "main": "index.js",
                       "exports": "./index.js"}, fh)
        with open(os.path.join(p, "index.js"), "w", encoding="utf-8") as fh:
            fh.write(src)
    p = subprocess.run(["node", "check_site.mjs"], cwd=d, capture_output=True,
                       text=True, timeout=120)
    out = (p.stdout or "") + (p.stderr or "")
    for ln in out.splitlines():
        m = re.match(r"^\s+(ok|FAIL)\s+(.*)$", ln)
        if m:
            check(m.group(2), m.group(1) == "ok")
    if not re.search(r"\d+ passed, 0 failed", out):
        check("the Node checks ran to the end", False, out[-600:])


# --------------------------------------------------------------------------
def fake_monolith(work):
    """All four sessions, two cue pairs a day, split and Progress built, and
    filed as the built Monolith of a logs folder of its own."""
    MO.configure(os.path.join(work, "logs"))
    man = CM.fake_manifest(units=6, days_of=sorted(MO.DAYS + MO.TRAJ_DAYS,
                                                    key=lambda x: x[0]))
    for d in man["days"]:
        for i, u in enumerate(d["units"]):
            u["cue_type"] = "Click_LowTone" if i % 2 == 0 else "Noise_HighTone"
            u["cue_label"] = u["label"] = ("Click → Low Tone" if i % 2 == 0
                                           else "Noise → High tone")
    man["digest"] = MO._digest(man)
    every = {(d["rat"], d["day"], f["role"]) for d, f in MO.folders_of(man)}
    core = MO.core_view(man)
    base = MO.plan_tasks(core, MO.check_data(core, CM.listing_for(core, whole=every)))
    add = MO.plan_tasks(man, MO.check_data(man, CM.listing_for(man, whole=every)),
                        extra={"days": list(MO.TRAJ_NAMES)})

    def run_of(rid, ts):
        return {"rid": rid, "dest": "scratch", "arrays": [{"id": "1", "indices": None}],
                "submitted_at": MO.now_iso(), "code": "deadbeef" * 8,
                "tasks": [{"i": i, "key": t["key"], "rat": t["rat"], "day": t["day"],
                           "kind": t["kind"], "chunk": t["chunk"], "n_units": t["n_units"],
                           "est_s": t["est_s"]} for i, t in enumerate(ts)]}
    b = run_of("7b0000000001", base)
    CM.fake_outputs(core, b, os.path.join(MO.run_dir_local(b["rid"]), "raw"))
    t = run_of("7b0000000002", add)
    t["parts"] = [{"rid": b["rid"], "tasks": b["tasks"]}]
    raw = os.path.join(MO.run_dir_local(t["rid"]), "raw")
    CM.fake_outputs(man, t, raw, seed=11)
    data = os.path.join(MO.run_dir_local(t["rid"]), "data")
    summ = MO.build(man, t, raw, data)
    roles, notes = CM.fake_roles(man)
    MO.split_build(man, summ, data, roles, notes)
    MO.session_build(man, summ, data, roles=roles)
    MO.physical_build(man, summ, data, roles)
    MO.save_manifest(man)
    MO.save_state(run=t, built={"rid": t["rid"], "at": MO.now_iso(),
                                "artifact_id": "zz", "version": 1,
                                "counts": summ["counts"]})
    return man, MO.summary_now(), data


def build_checks(work, port):
    print("\n2. Building the site from Jarvis")
    S = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/api/arc/monolith/"
                                          "data/summary" % port).read())
    out = os.path.join(work, "site")
    args = SimpleNamespace(url="http://127.0.0.1:%d" % port, out=out,
                           budget_mb=500.0, leaves=0, ahead=10)
    XR.build(args)
    must = ["index.html", "login.html", "monolith.html", "monolith-guide.html",
            "monolith_guide.json", "middleware.js", "vercel.json", "package.json",
            "lib/gate.js", "api/login.js", "api/logout.js", "api/questions.js",
            "js/static_adapter.js", "js/report.js",
            "js/monolith.js", "js/monolith_progress.js", "js/monolith_physical.js", "css/site.css",
            "data/summary.json", "data/damage.json", "data/review.json", "data/physical.json"]
    missing = [f for f in must if not os.path.isfile(os.path.join(out, f))]
    check("every file the site needs (%d)" % len(must), not missing, missing)
    pk = json.load(open(os.path.join(out, "package.json"), encoding="utf-8"))
    check("and no link to the cluster: no bridge function, no ssh package, no key",
          not os.path.exists(os.path.join(out, "api", "remote.js")) and "ssh2" not in pk.get("dependencies", {})
          and not any(f.startswith("vacc") for f in os.listdir(out))
          and "VACC_KEY" not in open(os.path.join(out, "js", "static_adapter.js"), encoding="utf-8").read())
    page = open(os.path.join(out, "monolith.html"), encoding="utf-8").read()
    check("the Monolith page reads the copy: the adapter first, before the page's own",
          page.index('<script src="js/static_adapter.js">') < page.index('<script src="js/monolith_figs.js">')
          < page.index('<script src="js/monolith.js">'))
    phys = [n[:-4] for n in S["physical"]["files"] if n.startswith("phys_edges_")]
    names = [n[:-4] for n in S["files"]] + [n[:-4] for n in S["splits"]["files"]] \
        + [n[:-4] for n in S["sessions"]["files"]] + phys
    bad = []
    for n in names:
        p = os.path.join(out, "data", n + ".f32z")
        if not os.path.isfile(p):
            bad.append(n + ": missing")
            continue
        got = gzip.decompress(open(p, "rb").read())
        want = urllib.request.urlopen("http://127.0.0.1:%d/api/arc/monolith/data/%s"
                                      % (port, n)).read()
        if got != want:
            bad.append(n + ": differs")
    check("with room for all: every array (%d), gzipped, byte for byte Jarvis's"
          % len(names), not bad, bad[:4])
    R = json.load(open(os.path.join(out, "data", "review.json"), encoding="utf-8"))
    check("the write-up's numbers are the summary's", R["rats"] == S["rats"]
          and R["counts"]["pooled"]["raw"] == S["counts"]["raw"]
          and R["counts"]["ab"]["raw"] == S["splits"]["counts"]["ab"]["raw"]
          and R["contrast"]["pooled"] == S["contrast"]["counts"]["raw"]
          and [w["id"] for w in R["windows"]] == list(MO.WINDOWS)
          and R["contrast_window"]["id"] == "c21", R.get("counts", {}).get("pooled"))
    t0 = S["top"]["raw"][0]
    check("its leads are the points of interest, ten at most, each with what its "
          "link needs", R["leads"]["pooled"]["raw"][0]["pair"] == t0["pair"]
          and len(R["leads"]["pooled"]["raw"]) == min(10, len(S["top"]["raw"]))
          and all(k in R["leads"]["pooled"]["raw"][0] for k in ("w", "band", "m", "pair", "p")))
    path = XR.entry_path("raw", t0, "pooled")
    f = os.path.join(out, "data", "ahead", "entry", XR.key_of(path) + ".json")
    live = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/api/arc/monolith%s"
                                             % (port, path)).read())
    check("the first lead's entry is asked ahead, under its path's name, as Jarvis "
          "answers it", os.path.isfile(f) and json.load(open(f, encoding="utf-8"))
          == live, path)
    js = subprocess.run(["node", "-e", "let h=0x811c9dc5;for(const b of new TextEncoder()"
                         ".encode(process.argv[1])){h^=b;h=Math.imul(h,0x01000193)>>>0;}"
                         "console.log(h.toString(16).padStart(8,'0'))", path],
                        capture_output=True, text=True).stdout.strip()
    check("the page works out the same name (FNV-1a) as the export", js == XR.key_of(path),
          (js, XR.key_of(path)))
    want_e = set()
    for g in ["pooled"] + [x["id"] for x in S["splits"]["groups"]]:
        top = S["top"] if g == "pooled" else S["splits"]["top"][g]
        con = S["contrast"]["top"]["raw"] if g == "pooled" else S["splits"]["contrast"]["top"][g]["raw"]
        for layer in ("raw", "minus_fp"):
            for t in top[layer][:10]:
                want_e.add(XR.entry_path(layer, t, g))
            for t in con[:10]:
                want_e.add(XR.entry_path(layer, t, g))
    have_e = set(os.listdir(os.path.join(out, "data", "ahead", "entry")))
    check("every lead of every comparison and layer, and of the contrast, asked ahead (%d)" % len(want_e),
          have_e == {XR.key_of(x) + ".json" for x in want_e} and R["copy"]["ahead"]["entry"] == len(want_e),
          (len(have_e), len(want_e)))
    pac = [p for p in os.listdir(os.path.join(out, "data", "ahead", "pacself"))]
    pw = S["files"]["pac_raw.f32"]["shape"][1]
    check("the within-region PAC asked ahead for every window and both layers (%d)"
          % (2 * pw), len(pac) == 2 * pw, len(pac))
    # A budget that holds the pooled arrays and only some of Progress.
    small = os.path.join(work, "site_small")
    sess_bytes = sum(os.path.getsize(os.path.join(out, "data", n[:-4] + ".f32z"))
                     for n in S["sessions"]["files"])
    tight = (XR.dir_bytes(out) - sess_bytes / 2) / 1e6
    XR.build(SimpleNamespace(url=args.url, out=small, leaves=0, ahead=10, budget_mb=tight))
    check("the whole site stays inside the budget (%.0f MB)" % tight,
          XR.dir_bytes(small) <= tight * 1e6, XR.dir_bytes(small) / 1e6)
    R2 = json.load(open(os.path.join(small, "data", "review.json"), encoding="utf-8"))
    om = R2["copy"]["omitted"]
    kept = [n for n in names if n.startswith("session_") and os.path.isfile(
        os.path.join(small, "data", n + ".f32z"))]
    check("a tighter budget: every pooled array and section 6's raw circuits still in, "
          "Progress's later files (and section 6's Minus FP) left to Jarvis and listed",
          om and all(n.startswith("session_") or n.startswith("phys_edges_minus_fp__") for n in om)
          and all(os.path.isfile(os.path.join(small, "data", n[:-4] + ".f32z"))
                  for n in list(S["files"]) + list(S["splits"]["files"]))
          and all(os.path.isfile(os.path.join(small, "data", n + ".f32z")) for n in phys if "_raw__" in n)
          and kept and not set(kept) & set(om), (len(om), len(kept)))
    check("and the pooled sessions go in before AB and CD's",
          all("__" not in n for n in kept) or all("__" in n for n in om), om[:3])
    return out, S


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def page_checks(work, site, S):
    print("\n3. The pages, served as plain files, in Edge")
    if not os.path.isfile(EDGE):
        check("Edge is here to look at the pages", False, EDGE)
        return
    port = free_port()
    handler = lambda *a, **k: Quiet(*a, directory=site, **k)       # noqa: E731
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix="review_edge_")

    def dom(page, budget=20000):
        p = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--user-data-dir=" + prof,
                            "--window-size=1500,1100", "--virtual-time-budget=%d" % budget,
                            "--dump-dom", "http://127.0.0.1:%d/%s" % (port, page)],
                           capture_output=True, timeout=240)
        return p.stdout.decode("utf-8", "replace")
    t0 = S["top"]["raw"][0]
    html = dom("monolith.html#go=raw,%s,%s,%s,%d,all" % (t0["w"], t0["band"], t0["m"], t0["pair"]))
    check("the Monolith draws its circuit from the copy", 'id="circsvg"' in html
          and 'class="edge' in html, re.findall(r"could not be read[^<]*", html)[:1])
    check("says it is the review copy, read only, every p uncorrected",
          'id="reviewbar"' in html and "read only" in html and "uncorrected" in html)
    check("a lead's link opens on the Monolith tab with its line selected",
          re.search(r'id="tab-main"[^>]*aria-selected="true"', html) is not None
          and re.search(r'class="edge sel"[^>]*data-pair="%d"' % t0["pair"], html) is not None)
    check("and the line's sessions open from the copy made ahead (no cluster here)",
          'id="trajmat"' in html, re.findall(r"needs the cluster[^<]*", html)[:1])
    # A line no lead is: its pooled numbers, and where the rest is.
    leads = {(t["wi"], t["bi"], t["mi"], t["pair"]) for t in S["top"]["raw"][:10]}
    other = next(p for p in range(len(S["pairs"])) if (t0["wi"], t0["bi"], t0["mi"], p) not in leads and p != t0["pair"])
    html2 = dom("monolith.html#go=raw,%s,%s,%s,%d,all" % (t0["w"], t0["band"], t0["m"], other))
    check("a line that is not a lead says it opens that far in Jarvis",
          "opens that far in Jarvis" in html2 and 'id="circsvg"' in html2, re.findall(r"Could not read it:[^<]*", html2)[:1])
    rep = dom("index.html")
    check("the write-up: every section", all('id="%s"' % s in rep for s in (
        "scope", "abcd", "windows", "minusfp", "histology", "kept", "results",
        "questions", "site")))
    check("says every p is uncorrected, and the counts against chance",
          "Every p on this site is uncorrected" in rep and "By chance" in rep)
    n = S["counts"]["raw"]["tested"]
    check("its numbers are the Monolith's (%s tested)" % format(n, ","),
          format(n, ",") in rep)
    check("the leads link into the Monolith", re.search(
        r'href="monolith\.html#go=raw,%s,%s,%s,%d,all"' % (t0["w"], t0["band"], t0["m"], t0["pair"]),
        rep) is not None)
    check("with no questions service here, the list says it could not be read",
          "The questions could not be read" in rep)
    ph = dom("monolith.html#tab=phys")
    check("section 6 opens by its link, from the copy: the verdict, the leads and a circuit",
          re.search(r'id="tab-phys"[^>]*aria-selected="true"', ph) is not None and 'id="physverdict"' in ph
          and 'id="physleadtbl"' in ph and 'class="mfig physcircuit"' in ph and 'id="physmake"' not in ph,
          re.findall(r"(?:Could not read|not in this copy)[^<]*", ph)[:2])
    srv.shutdown()


def main():
    work = tempfile.mkdtemp(prefix="review_check_")
    try:
        node_checks(work)
        print("\nA made-up Monolith, all four sessions …", flush=True)
        man, S, data = fake_monolith(work)
        port = free_port()
        threading.Thread(target=lambda: appmod.app.run(
            host="127.0.0.1", port=port, use_reloader=False, threaded=True),
            daemon=True).start()
        time.sleep(1.5)
        site, S = build_checks(work, port)
        page_checks(work, site, S)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("\n%d passed, %d failed" % (len(PASSED), len(FAILED)))
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
