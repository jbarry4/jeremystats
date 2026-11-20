# -*- coding: utf-8 -*-
"""check_precon_drift_report.py -- tools/precon_drift_report.py on synthetic
drifts, with a planted change it must find and a control where it must not.

Nothing real is read or written: the circuits are made from the fixture in
web/_dev/fixtures/ (its region order, methods, parameters and cell layout),
with values drawn from a known model -- rat offset + day effect + noise --
and grey regions per rat mimicking the DEWEY histology (POR in no rat, PER
in 2 of 8, RSC and DHC lost in some). Every drift is made by the REAL
`backend/drift.py build` (matched, Hartung-Knapp, BH across the artifact),
written to a temp folder with a run log pointing at the files, and the
report is built from that run log.

PLANTED: theta, state, food pair, cue 1 and cue 2, coherence, two region
pairs (Right ACC - Right OFC, Left OFC - Left ACC): +0.12 on Precon4.
Checks:
  - the CSV has exactly one row per drift cell, and three rows picked out
    equal the payload values they came from
  - the planted cells reach q < .05 in the food-pair drift and not in the
    no-food one; the food - no-food contrast finds them too
  - the md leads with the answer and names the artifact of every number
  - every drift has its figure
NEGATIVE CONTROL: the same run with nothing planted -- the md must say
nothing changed, and no planted cell may reach q < .05.

    python tools\\check_precon_drift_report.py [--keep DIR]
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import drift  # noqa: E402
import precon_drift_report as rep  # noqa: E402
import run_precon_drift as rpd  # noqa: E402

FIXTURE = os.path.join(APP, "web", "_dev", "fixtures",
                       "circuit_s360e48254222.json")
RATS = rpd.RATS
BANDS = {"theta": (4.0, 12.0, 500.0), "beta": (13.0, 30.0, 150.0),
         "gamma_low": (30.0, 55.0, 60.0)}
KIND_WINDOWS = {"state": ["pre", "cue1", "cue2", "post"],
                "transition": ["onset", "switch", "offset"],
                "rest": ["rest"]}
PLANT_PAIRS = ("Right ACC|Right OFC", "Left OFC|Left ACC")
PLANT = 0.12
BASE = {"coherence": 0.30, "raw_cc": 0.40, "amp_cc": 0.30}
# Grey per rat: POR everywhere; PER usable only in r3 and r7; one RSC and
# some DHC lost -- the shape of the real histology, not its detail.
GREY = {r: {"Left POR", "Right POR"} for r in RATS}
for r in RATS:
    if r not in (3, 7):
        GREY[r] |= {"Left PER", "Right PER"}
GREY[4] |= {"Right RSC"}
GREY[9] |= {"Right RSC", "Left RSC"}
GREY[6] |= {"Left DHC"}
GREY[10] |= {"Right DHC", "Left DHC"}
GREY[11] |= {"Right DHC"}

FAILS = []


def ok(cond, what):
    print("  [%s] %s" % ("ok" if cond else "FAIL", what))
    if not cond:
        FAILS.append(what)
    return cond


def _sd(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def make_circuit(tpl, rat, day, kind, cue_type, role, band, plant, seed):
    rng = random.Random(seed)
    order = list(tpl["region_order"])
    grey = GREY[rat]
    windows = KIND_WINDOWS[kind]
    n_pairs = 8
    pairs = [{"pair_id": i, "label": "synthetic", "opener_t":
              100.0 + 60.0 * i} for i in range(1, n_pairs + 1)]
    low, high, lag = BANDS[band]
    params = dict(tpl["params"], low=low, high=high, max_lag_ms=lag,
                  band=band, coherence_mode="band", raw_cc_filtered=True,
                  kind=kind)
    if kind == "transition":
        params.update(before_s=1.0, after_s=2.0)
    cells, usable = {}, {}
    for w in windows:
        cells[w] = {}
        usable[w] = {r: {"usable": 0 if r in grey else n_pairs,
                         "of": n_pairs} for r in order}
        for m in tpl["methods"]:
            panel = {}
            for i, a in enumerate(order):
                for b in order[i + 1:]:
                    if a in grey or b in grey:
                        continue
                    key = "%s|%s" % (a, b)
                    # A rat's own level, the same on both days (keyed by rat,
                    # pair, method -- not by day), so the matched design has
                    # something to take out.
                    rr = random.Random("%s|%s|%s|%s" % (rat, key, m, band))
                    level = BASE[m] + rr.gauss(0, 0.06)
                    eff = 0.0
                    if (plant and day == 4 and band == "theta"
                            and kind == "state" and role == "food"
                            and w in ("cue1", "cue2") and m == "coherence"
                            and key in PLANT_PAIRS):
                        eff = PLANT
                    k = n_pairs - rng.choice((0, 0, 0, 1, 2))
                    vals = [level + eff + rng.gauss(0, 0.05)
                            for _ in range(k)]
                    panel[key] = {
                        "n": k, "mean": sum(vals) / k, "sd": _sd(vals),
                        "values": [{"pair_id": j + 1, "v": v}
                                   for j, v in enumerate(vals)],
                        "of": n_pairs,
                        "warn": None}
            cells[w][m] = panel
    regions = [{"region": r, "slot": None, "label": r,
                "histology": "missed" if r in grey else "intended",
                "status": "grey" if r in grey else "ok",
                "why": "synthetic: grey in r%d" % rat if r in grey else ""}
               for r in order]
    gid = "harness-syn-r%d-p%d" % (rat, day)
    out = {
        "schema": "arc.circuit/1", "kind": kind,
        "cue_type": cue_type if kind != "rest" else "none",
        "cue_label": ("no cue" if kind == "rest" else
                      cue_type.replace("_", " → ")),
        "windows": windows, "methods": list(tpl["methods"]),
        "region_order": order, "regions": regions, "pairs": pairs,
        "n_pairs": n_pairs, "cells": cells, "region_usable": usable,
        "grey": [r for r in order if r in grey], "params": params,
        "source": {"gid": gid, "session_label": "synthetic r%d Precon%d"
                   % (rat, day), "bank_entry": "syn", "bank_version": 1},
        "computed_on": {"kind": "synthetic"},
    }
    if role:
        out["cue_role"] = role
        out["role_source"] = {"rat": rat, "synthetic": True}
    return out


def _vid(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def make_run(folder, plant):
    """Synthetic circuits, every drift of the plan built by drift.build,
    written to `folder` with a run log. Returns the run log path."""
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        tpl = json.load(fh)
    roles = {}
    for rat in RATS:
        roles[rat] = {"food": "Click_LowTone", "no_food": "Noise_HighTone"}
    circ = {}
    for band in BANDS:
        for kind in ("state", "transition", "rest"):
            for rat in RATS:
                for day in rpd.DAYS:
                    for role in (("food", "no_food") if kind != "rest"
                                 else (None,)):
                        ct = roles[rat][role] if role else "none"
                        seed = "%s|%s|%s|%s|%s" % (band, kind, rat, day, role)
                        p = make_circuit(tpl, rat, day, kind, ct, role, band,
                                         plant, seed)
                        aid = _vid("circ|" + seed)
                        circ[(band, kind, rat, day, role)] = (p, {
                            "artifact_id": aid, "id": aid, "version": 1,
                            "version_id": _vid("v|" + seed),
                            "digest": _vid("d|" + seed),
                            "rat": "r%d" % rat, "name": "syn r%d P%d %s %s %s"
                            % (rat, day, kind, role, band)})
    drifts = {}
    os.makedirs(folder, exist_ok=True)
    for band, kind, role, contrast in rpd.drift_plan():
        L, R, lr, rr, bl, br, blr, brr = [], [], [], [], [], [], [], []
        use = ("food", "no_food") if contrast == "roles" else (role,)
        for rat in RATS:
            for ro in use:
                for day, P, Rf, B, BR in ((1, L, lr, bl, blr),
                                          (4, R, rr, br, brr)):
                    p, ref = circ[(band, kind, rat, day, ro)]
                    P.append(p)
                    Rf.append(ref)
                    if contrast == "baseline":
                        if kind == "transition":
                            sp, sref = circ[(band, "state", rat, day, ro)]
                            B.append(sp)
                            BR.append(sref)
                        else:
                            B.append(None)
                            BR.append(None)
        kw = dict(design="matched", test="hk", bh_scope="artifact",
                  contrast=contrast)
        if contrast == "baseline":
            kw.update(baselines={"left": bl, "right": br},
                      baseline_refs={"left": blr, "right": brr})
        payload = drift.build(L, R, lr, rr,
                              {"left": "Precon1", "right": "Precon4"},
                              computed_on={"kind": "synthetic"}, **kw)
        key = rpd.drift_key(band, kind, role, contrast)
        aid = _vid("drift|" + key + ("|p" if plant else "|0"))
        fname = "drift_%s.json" % aid
        with open(os.path.join(folder, fname), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        drifts[key] = {"band": band, "kind": kind, "role": role,
                       "contrast": contrast,
                       "nickname": rpd.drift_nickname(band, kind, role,
                                                      contrast),
                       "artifact_id": aid, "version": 1,
                       "version_id": _vid("dv|" + key),
                       "digest": _vid("dd|" + key),
                       "payload_file": fname}
    log = {"schema": rpd.RUNLOG_SCHEMA, "synthetic": True,
           "design": {"rats": list(RATS),
                      "excluded": {"r5": rpd.EXCLUDED_RATS[5]}},
           "roles": {str(r): {"food_pair": roles[r]["food"]} for r in RATS},
           "drifts": drifts, "circuits": {}, "spark": {}}
    path = os.path.join(folder, "runlog.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=1)
    return path


def check_run(folder, plant):
    print("")
    print("%s -- %s" % ("PLANTED" if plant else "NEGATIVE CONTROL",
                        folder))
    print("-" * 78)
    runlog = make_run(folder, plant)
    out_md = os.path.join(folder, "report.md")
    out_csv = os.path.join(folder, "report.csv")
    figs = os.path.join(folder, "figures")
    got = rep.build_report(runlog, out_md, out_csv, figs)
    _log, drifts = rep.load_runlog(runlog)
    payloads = {}
    n_cells = 0
    for d in drifts:
        with open(os.path.join(folder, d["payload_file"]),
                  encoding="utf-8") as fh:
            payloads[d["key"]] = json.load(fh)
        n_cells += sum(1 for _ in rep.cells(payloads[d["key"]]))
    with open(out_csv, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ok(len(drifts) == 33, "%d drifts built by drift.build (33 planned)"
       % len(drifts))
    ok(len(rows) == n_cells, "CSV rows %d == drift cells %d"
       % (len(rows), n_cells))
    ok(list(rows[0].keys()) == list(rep.CSV_COLUMNS),
       "CSV columns are exactly the contract's (%s)" % ", ".join(
           rep.CSV_COLUMNS))

    # Three rows, by hand, against the payloads they came from.
    by_aid = {d["artifact_id"]: d for d in drifts}
    picks = [rows[0], rows[len(rows) // 2], rows[-1]]
    for r in picks:
        d = by_aid[r["artifact_id"]]
        c = payloads[d["key"]]["cells"][r["window"]][r["method"]][
            r["region pair"].replace(" – ", "|")]
        same = (abs(float(r["delta"]) - c["delta"]) < 1e-12
                and (r["q"] == "" if c.get("q") is None
                     else abs(float(r["q"]) - c["q"]) < 1e-12)
                and (r["t"] == "" if c.get("t") is None
                     else abs(float(r["t"]) - c["t"]) < 1e-12)
                and str(r["k"]) == str(c.get("k")))
        ok(same, "CSV row %s %s %s %s equals its payload cell (delta %s, "
           "t %s, q %s, k %s)" % (d["nickname"], r["window"], r["method"],
                                  r["region pair"], r["delta"], r["t"],
                                  r["q"], r["k"]))

    def cell(key, w, m, pair):
        return payloads[key]["cells"].get(w, {}).get(m, {}).get(pair)

    food = rpd.drift_key("theta", "state", "food", None)
    nofood = rpd.drift_key("theta", "state", "no_food", None)
    roles_k = rpd.drift_key("theta", "state", None, "roles")
    planted = [(w, pair) for w in ("cue1", "cue2") for pair in PLANT_PAIRS]
    fq = [cell(food, w, "coherence", pair)["q"] for w, pair in planted]
    nq = [cell(nofood, w, "coherence", pair)["q"] for w, pair in planted]
    rq = [cell(roles_k, w, "coherence", pair)["q"] for w, pair in planted]
    with open(out_md, encoding="utf-8") as fh:
        md = fh.read()
    head = md.split("\n")[2]
    if plant:
        ok(all(q is not None and q < 0.05 for q in fq),
           "planted cells reach q < .05 in the food-pair drift (q %s)"
           % ", ".join("%.2g" % q for q in fq))
        ok(all(q is None or q >= 0.05 for q in nq),
           "...and not in the no-food drift (q %s)"
           % ", ".join("%.2g" % q for q in nq))
        ok(all(q is not None and q < 0.05 for q in rq),
           "the food - no-food contrast finds them (q %s)"
           % ", ".join("%.2g" % q for q in rq))
        ok(head.startswith("**The answer: after correction,")
           and "changed" in head and "theta cue 1" in head,
           "the md leads with the answer: %s" % head[:160])
        d = by_aid[[x for x in drifts if x["key"] == food][0]["artifact_id"]]
        line = [x for x in md.split("\n")
                if "Right ACC – Right OFC, cue 1, coherence" in x]
        ok(bool(line), "the planted cell is named in the text: %s"
           % (line[0].strip()[:150] if line else "absent"))
        ok(("[%s v1]" % d["artifact_id"]) in md,
           "the food-pair drift is cited by artifact id and version")
    else:
        ok(all(q is None or q >= 0.05 for q in fq),
           "nothing planted: the would-be cells do not reach q < .05 (q %s)"
           % ", ".join("%.2g" % q for q in fq))
        ok(not [x for x in md.split("\n")
                if "Right ACC – Right OFC, cue 1, coherence" in x],
           "...and the text does not name them")
        # The headline is a count of the payloads' own q < .05 cells in the
        # raw cue drifts, recounted here independently. With nothing planted
        # these are BH's false discoveries at its nominal rate.
        n_sig = n_test = 0
        for d in drifts:
            if d.get("contrast") is None and d["kind"] in ("state",
                                                           "transition"):
                for w, m, k, c in rep.cells(payloads[d["key"]]):
                    n_test += c.get("p") is not None
                    n_sig += c.get("q") is not None and c["q"] < 0.05
        want = ("no region pair's coupling changed" if n_sig == 0 else
                "%d of %d region-pair tests" % (n_sig, n_test))
        ok(want in head, "the headline states the payloads' own count "
           "(%d of %d, recounted): %s" % (n_sig, n_test, head[:140]))
        frag = [x for x in md.split("\n") if x.startswith("  - ")
                and "k = 2 rats" in x]
        ok(all("FRAGILE" in x for x in frag),
           "every discovery resting on 2 rats is marked fragile (%d: %s)"
           % (len(frag), frag[0].strip()[:150] if frag else "none"))
        # The "nothing changed" sentence, forced: the same payloads with
        # every q < .05 raised to 1.
        forced = os.path.join(folder, "forced")
        os.makedirs(forced, exist_ok=True)
        with open(runlog, encoding="utf-8") as fh:
            log = json.load(fh)
        for key, d in log["drifts"].items():
            p = copy.deepcopy(payloads[key])
            for w, m, k, c in rep.cells(p):
                if c.get("q") is not None and c["q"] < 0.05:
                    c["q"] = 1.0
            with open(os.path.join(forced, d["payload_file"]), "w",
                      encoding="utf-8") as fh:
                json.dump(p, fh)
        with open(os.path.join(forced, "runlog.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(log, fh)
        rep.build_report(os.path.join(forced, "runlog.json"),
                         os.path.join(forced, "report.md"),
                         os.path.join(forced, "report.csv"),
                         os.path.join(forced, "figures"), figures=False)
        with open(os.path.join(forced, "report.md"), encoding="utf-8") as fh:
            fhead = fh.read().split("\n")[2]
        ok(fhead.startswith("**The answer: after correction, no region "
                            "pair's coupling changed") and "closest" in fhead
           and "[" in fhead,
           "with no q < .05 anywhere the md says nothing changed, and cites "
           "the closest: %s" % fhead[:200])
    # Every number cites: each line that states a q names an artifact.
    uncited = [x for x in md.split("\n")
               if ("q = " in x or "q < 0.05 [" in x) and "[" not in x
               and not x.startswith("  -")]
    ok(not uncited, "every line stating a q names its artifact (%d do not)"
       % len(uncited))
    missing = [d["nickname"] for d in drifts if not os.path.isfile(
        os.path.join(figs, rep.fig_name(d)))]
    ok(not missing and os.path.isfile(os.path.join(figs,
                                                   "sanity-checks.png")),
       "a figure for each of the %d drifts, and the sanity figure (%s)"
       % (len(drifts), "missing: " + ", ".join(missing) if missing
          else "all there"))
    return md


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", default=None,
                    help="write here and keep it (default: a temp folder, "
                         "removed after)")
    args = ap.parse_args(argv)
    root = args.keep or tempfile.mkdtemp(prefix="precon_report_")
    try:
        md = check_run(os.path.join(root, "planted"), True)
        check_run(os.path.join(root, "control"), False)
        print("")
        print("The planted report's first lines:")
        for line in md.split("\n")[:6]:
            print("  | " + line[:200])
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)
    print("")
    if FAILS:
        print("%d FAILED:" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        return 1
    print("all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
