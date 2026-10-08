"""
export_review.py -- the Monolith as a review site for Travis.

The site is plain files plus three small functions (sign in, sign out, the
open questions), for Vercel (project `dewey-monolith`). Its source is
review/site (tracked); this assembles it with the built Monolith into
GUI_logs/.cache/review_site, which is what is deployed.

    python tools/export_review.py build [--url URL] [--budget-mb 95]
                                        [--ahead 25] [--leaves 10]
        Assemble the site from the RUNNING Jarvis: it asks the same routes
        the Monolith page asks (summary, damage, the arrays, events), so
        the copy is what the page shows. The pooled arrays always go in,
        gzipped. Then everything a person can open from the review's leads
        is asked ahead and copied: each lead's entry down to its rats and
        presentations (the first --ahead of every comparison and layer, and
        of the contrast), the within-region PAC, and the traces of the
        strongest rat's first presentation on Precon1 and Precon4 for the
        first --leaves leads (read on the cluster, through Jarvis, now).
        Progress's session files go in last, while they fit the budget
        (Vercel Hobby takes 100 MB a deploy). Writes nothing outside the
        site folder.

    python tools/export_review.py env [--set --confirm]
        The Vercel project's environment: which variables, and where each
        comes from. With --set, the ones this machine can supply are put in
        with `npx vercel env add` (values on stdin, never printed). The
        password and the Supabase service key you add yourself.

There is no live link to the cluster (the lab's decision, 2026-10-06): the
VACC's login nodes run any command a key asks for, whatever its
authorized_keys line says, so a key kept on Vercel would be a key to the
whole account. A line that was not copied ahead says it opens in Jarvis.

Nothing here deploys: `npx vercel deploy --prod` from the site folder does,
once you have said so.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
LOGS = os.path.join(APP, "GUI_logs")
SRC = os.path.join(APP, "review", "site")
OUT = os.path.join(LOGS, ".cache", "review_site")
LAYERS = ("raw", "minus_fp")
WEB_FILES = ("monolith.html", "monolith-guide.html", "monolith_guide.json",
             "js/monolith_figs.js", "js/monolith_help.js", "js/monolith.js",
             "js/monolith_events.js", "js/monolith_progress.js",
             "js/monolith_physical.js", "js/monolith_tour.js", "js/tour.js")
# The windows in the lab's words, as the page says them (js/monolith.js).
WLABEL = {"pre": "Pre-baseline", "cue1": "Cue 1", "cue2": "Cue 2",
          "post": "Post-baseline", "pair": "Cue 1 + Cue 2", "onset": "Onset",
          "switch": "Switch", "offset": "Offset", "c21": "Cue 2 − Cue 1"}
CAUSE_SAY = {"histology": "probe placement (histology)", "bad": "bad wires",
             "clipped": "clipping (signal at the rail)",
             "unread": "not measured"}
LEAD_KEYS = ("layer", "w", "wi", "band", "bi", "hz", "m", "mi", "pair", "a",
             "b", "est", "se", "p", "k", "same")


def say(*a):
    print(*a, flush=True)


def key_of(path):
    """FNV-1a of a request's path: the name it is copied ahead under
    (js/static_adapter.js works out the same)."""
    h = 0x811c9dc5
    for b in path.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xffffffff
    return "%08x" % h


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------
class Jarvis:
    """The running Jarvis's Monolith routes."""

    def __init__(self, url):
        self.base = url.rstrip("/") + "/api/arc/monolith"

    def raw(self, path, timeout=600):
        try:
            with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                why = json.loads(body).get("error")
            except Exception:                            # noqa: BLE001
                why = body[:200]
            raise RuntimeError("%s: HTTP %d %s" % (path, exc.code, why))

    def json(self, path, timeout=600):
        return json.loads(self.raw(path, timeout))


def _slim(t):
    return {k: t.get(k) for k in LEAD_KEYS if k in t}


def leads_of(S, n=10):
    sp = S.get("splits") or {}
    groups = [g["id"] for g in sp.get("groups") or []]
    leads = {"pooled": {l: [_slim(t) for t in ((S.get("top") or {}).get(l)
                                                 or [])[:n]] for l in LAYERS}}
    for g in groups:
        leads[g] = {l: [_slim(t) for t in (((sp.get("top") or {}).get(g) or {})
                                            .get(l) or [])[:n]]
                    for l in LAYERS}
    con = {"pooled": [_slim(t) for t in (((S.get("contrast") or {}).get("top")
                                          or {}).get("raw") or [])[:n]]}
    for g in groups:
        con[g] = [_slim(t) for t in ((((sp.get("contrast") or {}).get("top")
                                       or {}).get(g) or {}).get("raw") or [])[:n]]
    return leads, con, groups


def counts_of(S, groups):
    sp = S.get("splits") or {}
    counts = {"pooled": {l: (S.get("counts") or {}).get(l) for l in LAYERS}}
    con = {"pooled": ((S.get("contrast") or {}).get("counts") or {}).get("raw")}
    for g in groups:
        counts[g] = {l: ((sp.get("counts") or {}).get(g) or {}).get(l)
                     for l in LAYERS}
        con[g] = (((sp.get("contrast") or {}).get("counts") or {}).get(g)
                  or {}).get("raw")
    return counts, con


def entry_path(layer, t, g):
    return "/entry?what=edges&layer=%s&at=%d,%d,%d,%d%s" % (
        layer, t["wi"], t["bi"], t["mi"], t["pair"],
        "&split=" + g if g and g != "pooled" else "")


def default_cell(S):
    cells = S.get("pac_cells") or []
    return next((i for i, c in enumerate(cells)
                 if c.get("fp") == 6 and c.get("fa") == 40), 0)


def damage_of(D):
    W = (D or {}).get("whole") or {}
    causes = {}
    for row in W.get("state") or []:
        for k, v in row.items():
            if k in CAUSE_SAY and isinstance(v, (int, float)):
                causes[CAUSE_SAY[k]] = causes.get(CAUSE_SAY[k], 0) + int(v)
    return {"cue": W.get("cue") or {}, "rest": W.get("rest") or {},
            "causes": causes, "seats": W.get("seats") or {}}


def dir_bytes(root):
    n = 0
    for base, _ds, fs in os.walk(root):
        if os.sep + "node_modules" in base or os.sep + ".vercel" in base:
            continue
        for f in fs:
            n += os.path.getsize(os.path.join(base, f))
    return n


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(path, mode, **({} if mode == "wb" else {"encoding": "utf-8",
                                                        "newline": "\n"})) as fh:
        fh.write(data)


def copy_sources(out):
    """The site's own files, and the Monolith page's, the page told to read
    from the site's files instead of Jarvis."""
    for base, _ds, fs in os.walk(SRC):
        for f in fs:
            src = os.path.join(base, f)
            dst = os.path.join(out, os.path.relpath(src, SRC))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    web = os.path.join(APP, "web")
    for rel in WEB_FILES:
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(web, rel), dst)
    page = os.path.join(out, "monolith.html")
    with open(page, encoding="utf-8") as fh:
        html = fh.read()
    first = '<script src="js/monolith_figs.js"></script>'
    if first not in html or "</style>" not in html:
        raise SystemExit("web/monolith.html has changed shape: the review copy "
                         "cannot be told where to read from.")
    html = html.replace(first, '<script src="js/static_adapter.js"></script>\n'
                        + first, 1)
    html = html.replace("</style>", ".reviewbar { font-size: 13px; color: "
                        "var(--ink-3); margin: 0 0 10px; }\n.reviewbar a { "
                        "color: var(--ink); }\n</style>", 1)
    write(page, html)


def build(args):
    J = Jarvis(args.url)
    say("Asking Jarvis at %s …" % args.url)
    try:
        S = J.json("/data/summary")
    except Exception as exc:                             # noqa: BLE001
        raise SystemExit("Jarvis did not answer with a built Monolith (%s). Is "
                         "it running, on the code with Progress (restart it)?"
                         % exc)
    out = os.path.abspath(args.out)
    if os.path.isdir(out):
        # The assembled copy only: keep the Vercel link and the installed
        # packages, replace everything else.
        for name in os.listdir(out):
            if name in (".vercel", "node_modules", "package-lock.json"):
                continue
            p = os.path.join(out, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(out, exist_ok=True)
    copy_sources(out)
    data = os.path.join(out, "data")
    write(os.path.join(data, "summary.json"), json.dumps(S))
    D = J.json("/damage")
    write(os.path.join(data, "damage.json"), json.dumps(D))
    try:
        write(os.path.join(data, "events.json"), json.dumps(J.json("/events")))
    except Exception as exc:                             # noqa: BLE001
        say("  events-first report not copied: %s" % exc)
    # Section 6, physical cue against balanced cue: its comparisons, and
    # its circuits' arrays (raw before Progress, Minus FP after it).
    phys = []
    try:
        P6 = J.json("/data/physical")
        write(os.path.join(data, "physical.json"), json.dumps(P6))
        phys = sorted([n[:-4] for n in (P6.get("files") or {})
                       if n.startswith("phys_edges_") or n.startswith("phys_snd_")],
                      key=lambda n: ("minus_fp" in n, n))
    except Exception as exc:                             # noqa: BLE001
        say("  section 6 not copied (compare it in Jarvis first): %s" % exc)
    # The arrays: every pooled one, then Progress's while they fit.
    budget = int(args.budget_mb * 1e6)
    core = [n[:-4] for n in (S.get("files") or {})] + \
        [n[:-4] for n in ((S.get("splits") or {}).get("files") or {})]
    order = {"": 0, "ab": 1, "cd": 2}

    def sess_rank(n):
        body = n[len("session_"):]
        body, _, w = body.rpartition("_")
        what, _, rest = body.partition("_")
        layer, _, g = rest.partition("__")
        return (order.get(g, 3), what != "edges", layer != "raw", int(w))
    sessions = sorted([n[:-4] for n in ((S.get("sessions") or {}).get("files")
                                        or {})], key=sess_rank)
    omitted, t0 = [], time.time()

    def arrays(names, room=None):
        for i, name in enumerate(names):
            try:
                gz = gzip.compress(J.raw("/data/" + name), 6, mtime=0)
            except Exception as exc:                     # noqa: BLE001
                say("  NOT COPIED: %s (%s)" % (name, exc))
                omitted.append(name)
                continue
            if room is not None and dir_bytes(out) + len(gz) > room:
                omitted.append(name)
                continue
            write(os.path.join(data, name + ".f32z"), gz)
            if i % 10 == 0:
                say("  arrays %d of %d (%.0f MB so far, %.0f s)" % (
                    i + 1, len(names), dir_bytes(out) / 1e6, time.time() - t0))
    arrays(core)
    # Ahead of time: the leads' entries, the within-region PAC, a few traces.
    aleads, acon, groups = leads_of(S, args.ahead)
    ahead = {"entry": 0, "pacself": 0, "leaf": 0}
    done = set()

    def keep(kind, path):
        if path in done:
            return None
        done.add(path)
        try:
            got = J.json(path)
        except Exception as exc:                         # noqa: BLE001
            say("  not copied ahead: %s (%s)" % (path, exc))
            return None
        write(os.path.join(data, "ahead", kind, key_of(path) + ".json"),
              json.dumps(got))
        ahead[kind] += 1
        return got
    say("  asking the leads' entries ahead …")
    first = []
    for g in ["pooled"] + groups:
        for layer in LAYERS:
            for t in aleads[g][layer]:
                got = keep("entry", entry_path(layer, t, g))
                if got and g == "pooled" and layer == "raw":
                    first.append((t, got))
        for t in acon[g]:
            for layer in LAYERS:
                keep("entry", entry_path(layer, t, g))
    cell = default_cell(S)
    pw = ((S.get("files") or {}).get("pac_raw.f32") or {}).get("shape",
                                                               [0, 0])[1]
    say("  asking the within-region PAC ahead …")
    for layer in LAYERS:
        for w in range(pw):
            keep("pacself", "/pacself?layer=%s&window=%d&cell=%d" % (layer, w,
                                                                      cell))
    say("  asking %d presentations' traces ahead (each read on the cluster) …"
        % (2 * min(args.leaves, len(first))))
    for t, e in first[:args.leaves]:
        rats = sorted([r for r in e.get("rats") or [] if r.get("delta") is not None],
                      key=lambda r: -(r.get("weight") or 0))
        if not rats:
            continue
        r = rats[0]
        for day in ("Precon1", "Precon4"):
            u = next((u for u in ((r.get("days") or {}).get(day) or {})
                      .get("units") or [] if u.get("v") is not None), None)
            if u:
                keep("leaf", "/leaf?layer=raw&at=%d,%d,%d,%d&rat=%d&day=%s&unit=%s"
                     "&cell=%d" % (t["wi"], t["bi"], t["mi"], t["pair"],
                                   r["rat"], day, u["id"], cell))
    # Then Progress's session files, the pooled ones first, while they fit
    # (a megabyte kept back for the write-up's numbers).
    say("  section 6's circuits (raw) …")
    arrays([n for n in phys if "_raw__" in n], room=budget - 1e6)
    say("  Progress's session files, while they fit …")
    arrays(sessions, room=budget - 1e6)
    arrays([n for n in phys if "_raw__" not in n], room=budget - 1e6)
    # The write-up's numbers.
    leads, con, groups = leads_of(S)
    counts, ccounts = counts_of(S, groups)
    wins = [w for w in S.get("windows") or [] if w["id"] != "c21"]
    bands = S.get("bands") or []
    hz = [b["hz"] for b in bands if not b.get("named")]
    review = {
        "made_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "built_at": S.get("built_at"),
        "rid": S.get("rid"), "histology": S.get("histology") or {},
        "rats": S.get("rats") or [], "regions": S.get("regions") or [],
        "n_pairs": len(S.get("pairs") or []), "min_rats": S.get("min_rats"),
        "windows": [{"id": w["id"], "label": WLABEL.get(w["id"], w["label"]),
                     "kind": w.get("kind")} for w in wins],
        "contrast_window": {"id": "c21", "label": WLABEL["c21"]}
        if any(w["id"] == "c21" for w in S.get("windows") or []) else None,
        "window_say": {w["id"]: WLABEL.get(w["id"], w["label"])
                       for w in S.get("windows") or []},
        "bands": {"n_hz": len(hz), "lo": min(hz) if hz else None,
                  "hi": max(hz) if hz else None,
                  "named": [b["label"] for b in bands if b.get("named")]},
        "band_say": {b["id"]: b["label"] for b in bands},
        "methods": [{"id": m["id"], "label": m["label"]}
                    for m in S.get("methods") or []],
        "method_say": {m["id"]: m["label"] for m in S.get("methods") or []},
        "identity": S.get("identity") or {},
        "splits": [{"id": g["id"], "label": g["label"]}
                   for g in (S.get("splits") or {}).get("groups") or []],
        "counts": counts, "contrast": ccounts, "leads": leads,
        "contrast_leads": con, "damage": damage_of(D),
        "histology_changes": ((D or {}).get("histology") or {}).get("changes")
        or {},
        "sessions": {"order": (S.get("sessions") or {}).get("order") or [],
                     "trajectory": (S.get("trajectory") or {}).get("days") or []},
        "copy": {"omitted": omitted, "ahead": ahead},
    }
    write(os.path.join(data, "review.json"), json.dumps(review))
    total = dir_bytes(out)
    say("")
    say("The site is in %s: %.1f MB (budget %.0f MB)." % (out, total / 1e6,
                                                          args.budget_mb))
    say("  %d arrays in it; %d left out (they open in Jarvis)."
        % (len(core) + len(sessions) + len(phys) - len(omitted), len(omitted)))
    say("  ahead of time: %(entry)d entries, %(pacself)d PAC views, "
        "%(leaf)d presentations." % ahead)
    if total > args.budget_mb * 1e6:
        say("  OVER BUDGET: the pooled arrays and what was asked ahead are "
            "already more than it allows; Vercel will refuse the upload.")
    return out


# --------------------------------------------------------------------------
# the Vercel project's environment
# --------------------------------------------------------------------------
def env_cmd(args):
    with open(os.path.join(APP, "cloud.json"), encoding="utf-8") as fh:
        cloud = json.load(fh)
    rows = [
        ("SITE_PASSWORD", None, "you choose it: npx vercel env add SITE_PASSWORD"),
        ("SITE_SECRET", secrets.token_hex(32), "a random secret, made here"),
        ("SUPABASE_URL", cloud.get("url"), "cloud.json"),
        ("SUPABASE_SERVICE_KEY", None, "the Supabase dashboard (Settings → API "
         "→ service_role): npx vercel env add SUPABASE_SERVICE_KEY"),
    ]
    for name, value, where in rows:
        say("  %-22s %s  (%s)" % (name, "ready" if value else "—", where))
    if not args.set:
        return
    if not args.confirm:
        raise SystemExit("--set writes these into the Vercel project: add "
                         "--confirm.")
    site = os.path.abspath(args.out)
    if not os.path.isfile(os.path.join(site, ".vercel", "project.json")):
        raise SystemExit("The site folder is not linked to a Vercel project "
                         "yet: run `npx vercel link` in %s." % site)
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    for name, value, _w in rows:
        if not value:
            continue
        for target in ("production", "preview"):
            subprocess.run([npx, "vercel", "env", "rm", name, target, "--yes"],
                           cwd=site, capture_output=True)
            p = subprocess.run([npx, "vercel", "env", "add", name, target],
                               cwd=site, input=value, capture_output=True,
                               text=True)
            say("  %s → %s: %s" % (name, target, "set" if p.returncode == 0
                                   else (p.stderr or p.stdout).strip()[-200:]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--url", default="http://127.0.0.1:8733")
    b.add_argument("--out", default=OUT)
    b.add_argument("--budget-mb", type=float, default=95.0)
    b.add_argument("--ahead", type=int, default=25)
    b.add_argument("--leaves", type=int, default=10)
    e = sub.add_parser("env")
    e.add_argument("--set", action="store_true")
    e.add_argument("--confirm", action="store_true")
    e.add_argument("--out", default=OUT)
    args = ap.parse_args()
    {"build": build, "env": env_cmd}[args.cmd](args)


if __name__ == "__main__":
    main()
