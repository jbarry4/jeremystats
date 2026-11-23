"""StrataScope Beta's Consult, from Claude Code's side.

The page primes a consult (web/js/strataconsult.js -> backend/strataconsult.py
-> GUI_logs/.cache/strata_consult/<gid>/<id>/). This reads it and answers it.

  python tools/strata_consult.py show [--gid G] [--id I] [--full]
      The newest consult (or the one named): the recording, the open step,
      the sheet against the proposal row by row with every depth curve, the
      lines and their anchors and votes, checks, earlier decisions, and the
      paths of the pictures to look at (screen.png, strip.png, evidence.png).

  python tools/strata_consult.py push REPLY.json [--gid G] [--id I]
      Send a reply. It lands in the open StrataScope window over /api/link.

  python tools/strata_consult.py schema
      What a reply may hold.

Run it with the app's Python from _Jarvis/app. No third-party imports.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
LOGS = os.path.join(APP, "GUI_logs")
ROOT = os.path.join(LOGS, ".cache", "strata_consult")

SHORT = {
    "ca1_so": "SO", "ca1_sp": "SP", "ca1_rad": "SR", "ca1_slm": "SLM",
    "ca1_sr": "CA1*", "dg_oml1": "OML1", "dg_mml1": "MML1", "dg_iml1": "IML1",
    "dg_gcl1": "GCL1", "hil": "HIL", "dg_gcl2": "GCL2", "dg_iml2": "IML2",
    "dg_mml2": "MML2", "dg_oml2": "OML2", "thal": "THAL", "dg": "DG*",
    "dg2": "DG2*",
}
CURVES = ["mua", "ripple", "theta", "theta_phase", "theta_coherence",
          "neighbour_coherence", "slow_gamma", "mid_gamma", "fast_gamma", "rms"]
CURVE_HEAD = {"mua": "MUA", "ripple": "Rip", "theta": "Th", "theta_phase": "Ph",
              "theta_coherence": "Coh", "neighbour_coherence": "nCoh",
              "slow_gamma": "sG", "mid_gamma": "mG", "fast_gamma": "fG",
              "rms": "RMS"}

SCHEMA = """A reply is JSON:

{
  "summary": "Two or three plain sentences: how it looks overall.",
  "items": [
    {"kind": "note",  "title": "...", "why": "...", "look": "what to look at", "refs": ["Author Year"]},
    {"kind": "move",  "step": "3", "line": "dg_mml1|dg_iml1", "to_ch": 24,
                      "confidence": "likely", "why": "...", "look": "...", "refs": [...]},
        # line = "<above>|<below>" region ids (the strip's line id), or give
        # "above"/"below" instead. to_ch: the line goes ABOVE that CSC channel
        # (or to_row: a row index; "bottom" for below the last row).
        # A move is a proposal until the person Accepts the step.
    {"kind": "label", "channels": [30, 31], "region": "dg_gcl1", "why": "..."},
        # writes the sheet at once, like painting the rail; region null clears.
    {"kind": "confidence", "step": "1", "line": "ca1_rad|ca1_slm", "value": "guess", "why": "..."},
    {"kind": "show",  "step": "3", "curves": ["mid_gamma", "theta_phase"], "why": "..."},
        # curves: mua ripple theta theta_phase theta_coherence slow_gamma mid_gamma
    {"kind": "step",  "step": "2", "why": "..."},
    {"kind": "param", "key": "gcl_half_um", "value": 40, "why": "..."}
        # keys: spacing_um species gcl_half_um lower_ml_scale sp_half_um
        #       still_buffer_s ref_channel ripple_height_sd ripple_edge_sd
  ]
}

Items are applied in order by "Apply one by one", so put an item that opens a
step or changes a parameter before the moves that depend on it. Retired
regions (ca1_sr "CA1", dg "DG", dg2 "DG2") are refused as labels.
"""


def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def find(gid=None, cid=None):
    if gid is None:
        last = _load(os.path.join(ROOT, "LATEST.json"))
        if not last:
            sys.exit("No consult yet: press Consult in StrataScope's Beta tab.")
        gid = last["gid"]
        if cid is None:
            cid = last["id"]
    import re
    d = os.path.join(ROOT, re.sub(r"[^A-Za-z0-9_.-]+", "_", gid)[:80])
    if cid is None:
        ids = sorted(x for x in os.listdir(d)
                     if os.path.isfile(os.path.join(d, x, "request.json")))
        if not ids:
            sys.exit("No consult for %s." % gid)
        cid = ids[-1]
    f = os.path.join(d, cid)
    if not os.path.isfile(os.path.join(f, "request.json")):
        sys.exit("No consult %s for %s." % (cid, gid))
    return gid, cid, f


def _fmt(v, k):
    if v is None:
        return "  . "
    if k == "theta_phase":
        return "%4.0f" % v
    return "%4.2f" % v


def _norm(vals):
    xs = [v for v in vals if v is not None]
    if not xs:
        return vals
    lo, hi = min(xs), max(xs)
    if hi <= lo:
        return [None if v is None else 0.0 for v in vals]
    return [None if v is None else (v - lo) / (hi - lo) for v in vals]


def _labels_from_lines(lines, n):
    ls = sorted([l for l in lines if l.get("at") is not None], key=lambda l: l["at"])
    out = {}
    for r in range(n):
        region = None
        for l in ls:
            if l["at"] <= r:
                region = l["below"]
            else:
                if region is None:
                    region = l["above"]
                break
        out[r] = region
    return out


def show(args):
    gid, cid, f = find(args.gid, args.id)
    q = _load(os.path.join(f, "request.json")) or {}
    rep = _load(os.path.join(f, "reply.json"))
    dec = _load(os.path.join(f, "decisions.json")) or {}
    p = print
    p("CONSULT %s  %s  (%s)" % (cid, q.get("label") or gid, gid))
    p("folder: %s" % f)
    p("primed: %s by %s   open step: %s   read: %s" % (
        q.get("at"), q.get("who"), q.get("open_step"), q.get("scanned")))
    if q.get("note"):
        p("THEIR QUESTION: %s" % q["note"])
    p("step states: %s" % json.dumps(q.get("step_states")))
    p("theta walk: %s   ref channel: %s   ripples: %s" % (
        json.dumps(q.get("theta_walk")), q.get("ref_channel"), q.get("ripples_n")))
    p("params: %s" % json.dumps(q.get("params")))
    if q.get("masks"):
        p("masks: %s" % json.dumps(q["masks"]))
    p("pictures (Read these):")
    for im in q.get("images") or []:
        p("   %s" % os.path.join(f, im))

    chans = q.get("channels") or []
    labels = q.get("labels") or {}
    bad = set(int(b) for b in (q.get("bad") or []))
    prof = q.get("profile") or {}
    curves = prof.get("curves") or {}
    pchans = prof.get("channels") or chans
    rowof = {int(c): i for i, c in enumerate(pchans)}
    lines = (q.get("lines") or {}).get("lines") or []
    lstep = (q.get("lines") or {}).get("step")
    prop = _labels_from_lines(lines, len(chans)) if lines else {}
    norm = {k: (_norm(curves[k]) if k != "theta_phase" else curves[k])
            for k in CURVES if k in curves}
    p("")
    p("ROWS  (row 0 = top of probe; curves min-max normalised, phase in deg;"
      " '>' marks a proposed line above that row)")
    head = "  row  ch  bad  sheet  step%s-lines  " % (lstep or "-")
    head += " ".join("%4s" % CURVE_HEAD[k] for k in CURVES if k in norm)
    p(head)
    line_at = {}
    for l in lines:
        if l.get("at") is not None:
            line_at.setdefault(l["at"], []).append(l)
    for i, c in enumerate(chans):
        for l in line_at.get(i, []):
            p("  %s line %s|%s  (%s)" % (">" * 3, SHORT.get(l["above"], l["above"]),
                                         SHORT.get(l["below"], l["below"]),
                                         l.get("confidence")))
        lab = labels.get(str(c))
        pr = prop.get(i) if lines else None
        r = rowof.get(int(c))
        vals = " ".join(_fmt(norm[k][r] if r is not None and r < len(norm[k]) else None, k)
                        for k in CURVES if k in norm)
        p("  %3d %4s  %3s  %-5s  %-5s %s %s" % (
            i, c, "BAD" if int(c) in bad else "", SHORT.get(lab, lab or "-"),
            SHORT.get(pr, pr or "") if lines else "",
            "*" if (lines and pr and lab != pr) else " ", vals))
    for l in line_at.get(len(chans), []):
        p("  >>> line %s|%s at bottom" % (l["above"], l["below"]))

    p("")
    p("LINES of the open step (id, above ch, confidence, why):")
    for l in lines:
        at = l.get("at")
        ch = chans[at] if at is not None and at < len(chans) else ("bottom" if at is not None else None)
        p("  %-22s above ch %-6s %-7s %s" % (l.get("id"), ch, l.get("confidence"),
                                            (l.get("why") or "")[:200]))
    p("")
    p("PROPOSALS by step (anchor: lead -> row/ch; votes with offsets):")
    for sid, st in sorted((q.get("proposals") or {}).items()):
        if not isinstance(st, dict):
            continue
        p(" Step %s:" % sid)
        for a in st.get("anchors") or []:
            ld = a.get("lead") or {}
            r = ld.get("row")
            p("   %-10s lead %s at row %s (ch %s), conf %s" % (
                a.get("key"), ld.get("name"), r,
                chans[r] if r is not None and r < len(chans) else None,
                a.get("confidence")))
            for v in a.get("votes") or []:
                r2 = v.get("row")
                p("              vote %s at row %s (ch %s), off %s" % (
                    v.get("name"), r2, chans[r2] if r2 is not None and r2 < len(chans) else None,
                    v.get("off")))
        for l in st.get("lines") or []:
            at = l.get("at")
            p("   proposed %-22s above ch %s" % (
                l.get("id"), chans[at] if at is not None and at < len(chans) else at))
        for n in st.get("notes") or []:
            p("   note: %s" % n)
        if "use_iml" in st:
            p("   use_iml: %s" % st.get("use_iml"))
    if q.get("checks"):
        p("")
        p("CHECKS: %s" % json.dumps(q["checks"])[:3000])
    if q.get("ica"):
        p("")
        p("ICA: %s" % json.dumps(q["ica"])[:2500 if not args.full else 100000])
    if q.get("evidence_text"):
        p("")
        t = q["evidence_text"]
        p("EVIDENCE WINDOW TEXT:\n%s" % (t if args.full else t[:2500]))
    if q.get("earlier"):
        p("")
        p("EARLIER CONSULTS on this recording:")
        for e in q["earlier"]:
            p("  %s: %s | decisions %s" % (e.get("id"), e.get("reply_summary"),
                                          json.dumps(e.get("decisions"))[:600]))
    if rep:
        p("")
        p("ALREADY REPLIED (rev %s): %s" % (rep.get("rev"), rep.get("summary")))
        for i, it in enumerate(rep.get("items") or []):
            d = dec.get("%s:%s" % (rep.get("rev"), i)) or {}
            p("  %d. %s %s -> %s" % (i + 1, it.get("kind"),
                                     json.dumps({k: v for k, v in it.items()
                                                 if k not in ("why", "look", "refs", "kind")}),
                                     d.get("state", "pending")))
    if args.full:
        p("")
        p("RAW CURVES: %s" % json.dumps(curves))


def _base():
    for port in range(8733, 8741):
        url = "http://127.0.0.1:%d" % port
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as r:
                h = json.loads(r.read().decode("utf-8"))
            if os.path.normcase(os.path.abspath(h.get("logs") or "")) == \
                    os.path.normcase(os.path.abspath(LOGS)):
                return url
        except Exception:                                # noqa: BLE001
            continue
    return None


def push(args):
    gid, cid, f = find(args.gid, args.id)
    with open(args.reply, encoding="utf-8") as fh:
        reply = json.load(fh)
    base = _base()
    if not base:
        sys.exit("Jarvis is not running here, so the reply cannot be pushed.")
    from urllib.parse import quote
    req = urllib.request.Request(
        base + "/api/strata/%s/consult/reply" % quote(gid, safe=""),
        data=json.dumps({"id": cid, "reply": reply}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code in (404, 405):
            sys.exit("The running Jarvis has no consult routes (HTTP %d): it "
                     "started before they were added. Restart Jarvis." % e.code)
        sys.exit("Refused (HTTP %d): %s" % (e.code, body[:500]))
    print("Pushed reply rev %s to %s (%s items). It is in the Consult card now."
          % (out.get("rev"), gid, out.get("items")))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--gid")
    s.add_argument("--id")
    s.add_argument("--full", action="store_true")
    s = sub.add_parser("push")
    s.add_argument("reply")
    s.add_argument("--gid")
    s.add_argument("--id")
    sub.add_parser("schema")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "show":
        show(a)
    elif a.cmd == "push":
        push(a)
    else:
        print(SCHEMA)


if __name__ == "__main__":
    main()
