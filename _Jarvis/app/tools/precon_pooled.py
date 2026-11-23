# -*- coding: utf-8 -*-
"""precon_pooled.py -- the Precon1 -> Precon4 drifts with both cue pairings
pooled, raw and minus FP, and the page that shows them.

    python tools\\precon_pooled.py              # clear, run, page (all three)
    python tools\\precon_pooled.py --dry-run    # say what it would do
    python tools\\precon_pooled.py --page-only  # rebuild the page, file nothing

CLEAR
  The role-split drifts the first run filed (food pair / no-food pair /
  cue - baseline / food - no-food / rest) are soft-deleted: hidden in
  Results, recoverable, and the deletion syncs, so nothing comes back. The
  write-up, CSV, figures and the averaged page are MOVED to
  GUI_logs/.cache/precon_archive_<stamp>/, not deleted. The run log keeps
  them under `drifts_cleared`. The 240 circuits and their cache are kept.

RUN
  Six drifts: theta, beta, low gamma x state (baseline, cue 1, cue 2, after
  cue 2) and transition (onset, switch, offset). Each rat's day is every
  cue pair of both pairings, blind to type; the change is pooled over rats,
  precision-weighted (DerSimonian-Laird), Hartung-Knapp t; BH across the
  drift; at least 5 rats. Each carries a second layer, minus FP: the day's
  FP1 + FP2 rest subtracted before the change (backend/driftpool.py).

PAGE
  docs/dewey-precon-pooled.html: the node-edge circuit of any band x window
  x method, raw or minus FP, a significance slider (right is stricter), and
  a top 10 for each layer -- one entry per region pair, listing where it
  stands out. docs/dewey-precon-pooled.csv holds every entry of both layers.

In-process, like the other repair tools: it writes this machine's artifact
shards, and a running Jarvis sees them at once.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

DOCS = os.path.join(APP, "docs")
RUNLOG = os.path.join(DOCS, "dewey-precon-drift.runlog.json")
OUT = os.path.join(DOCS, "dewey-precon-pooled")
TEMPLATE = os.path.join(HERE, "precon_pooled.template.html")
BANDS = ("theta", "beta", "gamma_low")
KINDS = ("state", "transition")
BAND_SAY = {"theta": "theta", "beta": "beta", "gamma_low": "low gamma"}
DAY_LABEL = {1: "Precon1", 4: "Precon4"}
ARCHIVE_FILES = ("dewey-precon-drift.md", "dewey-precon-drift.csv",
                 "dewey-precon-drift", "dewey-precon-average.html",
                 "dewey-precon-average.csv", "dewey-precon-average.json")


def nickname(band, kind):
    return "Precon1→4 · %s · %s · both pairings" % (
        BAND_SAY[band], kind)


def load():
    with open(RUNLOG, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save(log):
    import run_precon_drift as R
    if os.path.exists(RUNLOG):
        shutil.copyfile(RUNLOG, RUNLOG + ".bak")
    log["updated"] = R.now()
    R.write_json(RUNLOG, log)


def clear(A, log, dry):
    import run_precon_drift as R
    old = {k: d for k, d in (log.get("drifts") or {}).items()
           if not d.get("pooled")}
    print("clear: %d role-split drift(s) to soft-delete" % len(old))
    gone, kept = [], []
    for key, d in sorted(old.items()):
        aid = d.get("artifact_id")
        rec = A.ARTIFACTS.get(aid) if aid else None
        if not rec:
            kept.append((key, "no such artifact"))
            continue
        if rec.get("deleted"):
            gone.append(aid)
            continue
        if not dry:
            A.ARTIFACTS.delete(aid, by="precon_pooled: superseded by the "
                                        "pooled analysis (both pairings)")
        gone.append(aid)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(APP, "GUI_logs", ".cache", "precon_archive_" + stamp)
    moved = []
    for name in ARCHIVE_FILES:
        src = os.path.join(DOCS, name)
        if os.path.exists(src):
            moved.append(name)
            if not dry:
                os.makedirs(dest, exist_ok=True)
                shutil.move(src, os.path.join(dest, name))
    print("  soft-deleted %d; archived %d file(s)%s" % (
        len(gone), len(moved), (" to " + dest) if moved and not dry else ""))
    for key, why in kept:
        print("  left %s: %s" % (key, why))
    if not dry and old:
        log.setdefault("drifts_cleared", []).append({
            "at": R.now(), "why": "superseded: both cue pairings pooled, "
                                  "raw and minus FP (tools/precon_pooled.py)",
            "archive": os.path.relpath(dest, APP) if moved else None,
            "drifts": old})
        log["drifts"] = {k: d for k, d in (log.get("drifts") or {}).items()
                         if d.get("pooled")}
        log.setdefault("events", []).append({
            "at": R.now(), "stage": "drifts",
            "msg": "cleared %d role-split drifts (soft-deleted); report "
                   "archived" % len(gone)})
        save(log)
    return gone


def refs_for(log, band, kind):
    cue, rest = [], []
    for key, c in (log.get("circuits") or {}).items():
        if c.get("band") != band or not c.get("artifact_id"):
            continue
        r = {"id": c["artifact_id"], "version_id": c.get("version_id"),
             "rat": "r%d" % int(c["rat"]), "day": DAY_LABEL[int(c["day"])]}
        if c.get("kind") == kind:
            cue.append(r)
        elif c.get("kind") == "rest":
            rest.append(r)
    return cue, rest


def run(A, log, dry):
    import run_precon_drift as R
    made = {}
    for band in BANDS:
        for kind in KINDS:
            cue, rest = refs_for(log, band, kind)
            nick = nickname(band, kind)
            print("run: %-42s %2d circuits, %2d rest" % (nick, len(cue),
                                                          len(rest)))
            if dry:
                continue
            t0 = time.time()
            got = A.driftpoolmod.file_pooled(
                A.DRIFT_HOST, cue, rest, band, kind, nickname=nick,
                by="precon_pooled")
            P = got["payload"]
            n1 = sum(p["tier1"] for byw in P["panels"].values()
                     for p in byw.values())
            n2 = sum(p["tier2"] for byw in P["panels"].values()
                     for p in byw.values())
            L = P["layers"]["minus_fp"]
            f1 = sum(p["tier1"] for byw in L["panels"].values()
                     for p in byw.values())
            f2 = sum(p["tier2"] for byw in L["panels"].values()
                     for p in byw.values())
            print("     %s v%s%s: raw %d survive, %d of interest (of %d); "
                  "minus FP %d, %d (of %d); %.1f s" % (
                      got["artifact_id"], got["version"],
                      "" if got["new_version"] else " (confirmed)", n1, n2,
                      P["bh_tests"], f1, f2, L["bh_tests"],
                      time.time() - t0))
            key = "%s|%s|pooled" % (band, kind)
            made[key] = {"band": band, "kind": kind, "role": None,
                         "contrast": "pooled", "pooled": True,
                         "nickname": nick,
                         "artifact_id": got["artifact_id"],
                         "version": got["version"],
                         "version_id": got["version_id"],
                         "digest": got["digest"], "at": R.now(),
                         "inputs": sorted(r["version_id"]
                                          for r in cue + rest),
                         "n_inputs": {"cue": len(cue), "rest": len(rest)}}
    if not dry:
        log.setdefault("drifts", {}).update(made)
        log.setdefault("events", []).append({
            "at": R.now(), "stage": "drifts",
            "msg": "filed %d pooled drifts (both pairings; raw and minus "
                   "FP)" % len(made)})
        save(log)
    return made


def payloads(A, log):
    out = []
    for key, d in sorted((log.get("drifts") or {}).items()):
        if not d.get("pooled"):
            continue
        got = A.ARTIFACTS.payload(d["artifact_id"], d["version_id"])
        P = got.get("payload", got) if isinstance(got, dict) and \
            "payload" in got and "cells" not in got else got
        out.append((d, P))
    order = {(b, k): i for i, (b, k) in enumerate(
        (b, k) for b in BANDS for k in KINDS)}
    out.sort(key=lambda x: order.get((x[0]["band"], x[0]["kind"]), 99))
    return out


def r6(v):
    return None if v is None else round(float(v), 6)


def page(A, log):
    from backend import driftpool as DP
    got = payloads(A, log)
    if not got:
        print("page: no pooled drifts in the run log yet")
        return
    rows = []
    data = {"made": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "drifts": [],
            "region_order": got[0][1].get("region_order"),
            "grey": got[0][1].get("grey"), "min_rats": DP.MIN_RATS,
            "tiers": got[0][1].get("tiers"),
            "analysis_say": got[0][1].get("analysis_say"),
            "layer_say": DP.LAYER_SAY, "top": {}}
    for d, P in got:
        entry = {"band": d["band"], "kind": d["kind"],
                 "nickname": d["nickname"], "artifact_id": d["artifact_id"],
                 "version": d["version"], "windows": P["windows"],
                 "methods": P["methods"], "rats": P.get("rats"),
                 "layers": {}}
        for layer in DP.LAYERS:
            L = P if layer == "raw" else P["layers"][layer]
            cells = {}
            for w in P["windows"]:
                cells[w] = {}
                for m in P["methods"]:
                    cells[w][m] = {}
                    for k, c in (L["cells"].get(w, {}).get(m) or {}).items():
                        cells[w][m][k] = {
                            "d": r6(c.get("delta")), "se": r6(c.get("se")),
                            "t": r6(c.get("t")), "df": c.get("df"),
                            "p": c.get("p"), "q": c.get("q"),
                            "tier": c.get("tier"), "k": c.get("k"),
                            "same": c.get("same_direction"),
                            "why": c.get("why"),
                            "rats": {x["rat"]: r6(x["delta"])
                                     for x in c.get("deltas") or []}}
                        rows.append([d["band"], d["kind"], w, m, layer,
                                     k.replace("|", " – "), c.get("delta"),
                                     c.get("se"), c.get("t"), c.get("df"),
                                     c.get("p"), c.get("q"), c.get("tier"),
                                     c.get("k"), c.get("same_direction"),
                                     d["artifact_id"], d["version"]])
            entry["layers"][layer] = {"cells": cells,
                                      "bh_tests": L.get("bh_tests")}
        data["drifts"].append(entry)
    for layer in DP.LAYERS:
        tops = DP.top([P for _d, P in got], layer, n=10)
        data["top"][layer] = [{
            "pair": t["pair"], "below_line": t["below_line"],
            "tested": t["tested"],
            "best": {k: (r6(v) if isinstance(v, float) else v)
                     for k, v in t["best"].items()
                     if k in ("band", "kind", "window", "method", "delta",
                              "p", "q", "tier", "k", "same_direction", "t",
                              "df", "se")},
            "where": [{k: (r6(v) if isinstance(v, float) else v)
                       for k, v in c.items()
                       if k in ("band", "kind", "window", "method", "delta",
                                "p", "q", "tier", "k", "same_direction")}
                      for c in t["where"]]} for t in tops]
    with open(OUT + ".csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["band", "window type", "window", "method", "layer",
                    "region pair", "change", "se", "t", "df", "p", "q",
                    "tier", "rats", "rats same way", "artifact", "version"])
        w.writerows(rows)
    with open(OUT + ".json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    with open(TEMPLATE, "r", encoding="utf-8") as fh:
        html = fh.read()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")
    assert html.count("/*DATA*/") == 1
    with open(OUT + ".html", "w", encoding="utf-8") as fh:
        fh.write(html.replace("/*DATA*/", blob))
    print("page: %d entries -> %s.html (and .csv, .json)" % (len(rows), OUT))
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--page-only", action="store_true")
    args = ap.parse_args(argv)
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from backend import app as A
    from backend import driftpool
    A.driftpoolmod = driftpool
    log = load()
    if not args.page_only:
        clear(A, log, args.dry_run)
        log = load() if not args.dry_run else log
        run(A, log, args.dry_run)
        log = load() if not args.dry_run else log
    if not args.dry_run:
        page(A, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
