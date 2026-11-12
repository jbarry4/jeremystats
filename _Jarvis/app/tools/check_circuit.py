# -*- coding: utf-8 -*-
"""Assert `backend/circuit.py` builds the circuit payload the contract says.

Three parts:

  1. REAL DATA. Pair results from Coupling (state windows), run through the
     Flask test client over every cue pair of one cue type of one recording
     and cached to a JSON file, are built into a circuit, and the payload is
     checked against the raw results by code that does not share a line
     with the engine: each cell's values are exactly the per-pair summary
     values, n/mean/SD recomputed by hand, grey regions have no cells,
     `warn` sits exactly where n < of/2, and a cell is absent exactly where
     no pair had both regions usable.

  2. SYNTHETIC EDGES. n = 1 (sd null, warn), a region usable in no pair, a
     relocated probe with numbers in the results (still grey), mixed cue
     types / params / kinds / windows (refused), both method-result shapes,
     transition window names.

  3. NEGATIVE CONTROLS. The engine is broken on purpose, one thing at a
     time (relocated not excluded; SD with ddof=0; warn at n <= of/2; only
     the nested method-result shape read), the checks are re-run,
     and each break must be caught. The engine is restored after each.

    python tools\\check_circuit.py                  # synthetic + controls
    python tools\\check_circuit.py CACHE.json ...   # + real data
    python tools\\check_circuit.py --fetch GID CACHE.json [CUE_TYPE]

`--fetch` runs Coupling over the pairs through the test client (about
5-12 s a pair) and writes ONLY the cache file; it writes nothing to the
Event Bank or the artifacts. Run it from PowerShell.
"""
import copy
import json
import math
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import circuit, probes                      # noqa: E402

ORDER = list(probes.DEWEY_NETWORK_ORDER)
GREYISH = ("relocated", "missed", "unscored")
FAILS = []


def check(cond, what):
    if not cond:
        FAILS.append(what)
    return bool(cond)


# --------------------------------------------------------------------------
# An independent reading of the raw pair results
# --------------------------------------------------------------------------
def raw_value(got):
    """Per-pair summary value, read directly from either shape."""
    if got is None:
        return None
    if "curve" in got or ("summary" in got and isinstance(got["summary"],
                                                          dict)):
        return got["summary"]["value"]
    return got["value"]


def expected(results, probe, methods):
    """{(window, method, A|B): [(pair_id, v)]} built from the raw rows."""
    verdict = {r["intended"]: r["verdict"] for r in (probe or [])}
    grey = [n for n in ORDER if verdict.get(n, "unscored") in GREYISH]
    out, usable = {}, {}
    for res in sorted(results, key=lambda r: r["pair_id"]):
        for w in res["windows"]:
            wn = w["window"]
            for n in ORDER:
                reg = w["regions"].get(n)
                usable.setdefault((wn, n), 0)
                if reg and reg["usable"] and n not in grey:
                    usable[(wn, n)] += 1
            for row in w["pairs"]:
                a, b = row["a"], row["b"]
                if a in grey or b in grey:
                    continue
                if not (w["regions"][a]["usable"]
                        and w["regions"][b]["usable"]):
                    continue
                if ORDER.index(a) > ORDER.index(b):
                    a, b = b, a
                for m in methods:
                    v = raw_value(row.get(m))
                    if v is None:
                        continue
                    out.setdefault((wn, m, a + "|" + b), []).append(
                        (res["pair_id"], v))
    return out, grey, usable


def verify(payload, results, probe, tag, of=None):
    """Every assertion about a payload, against the raw results."""
    before = len(FAILS)
    methods = list(payload["methods"])
    exp, grey, usable = expected(results, probe, methods)
    of = len(results) if of is None else of
    check(payload["schema"] == "arc.circuit/1", tag + ": schema")
    check(payload["region_order"] == ORDER, tag + ": region order")
    check(payload["grey"] == grey,
          tag + ": grey is %s, expected %s" % (payload["grey"], grey))
    check(payload["n_pairs"] == len(results), tag + ": n_pairs")
    check([p["pair_id"] for p in payload["pairs"]]
          == sorted(r["pair_id"] for r in results), tag + ": pairs listed")
    check(payload["windows"] == [w["window"] for w in results[0]["windows"]],
          tag + ": windows come from the results")
    for r in payload["regions"]:
        want = "grey" if r["region"] in grey else "ok"
        check(r["status"] == want, tag + ": %s status %s, expected %s"
              % (r["region"], r["status"], want))
        check(bool(r.get("why")), tag + ": %s has no why" % r["region"])

    n_cells = n_warn = n_absent = 0
    for wn in payload["windows"]:
        for m in methods:
            cells = payload["cells"][wn][m]
            for key in cells:
                a, b = key.split("|")
                check(a not in grey and b not in grey,
                      tag + ": grey region in cell %s %s %s" % (wn, m, key))
                check(ORDER.index(a) < ORDER.index(b),
                      tag + ": key %s out of order" % key)
            for i, a in enumerate(ORDER):
                for b in ORDER[i + 1:]:
                    key = a + "|" + b
                    want = exp.get((wn, m, key))
                    got = cells.get(key)
                    if not want:
                        if a not in grey and b not in grey:
                            n_absent += 1
                        check(got is None, tag + ": %s %s %s should be "
                              "absent, is %r" % (wn, m, key, got))
                        continue
                    if not check(got is not None, tag + ": %s %s %s missing"
                                 % (wn, m, key)):
                        continue
                    n_cells += 1
                    vals = [(x["pair_id"], x["v"]) for x in got["values"]]
                    check(vals == want, tag + ": %s %s %s values %s != %s"
                          % (wn, m, key, vals, want))
                    xs = [v for _, v in want]
                    check(got["n"] == len(xs), tag + ": n %s" % key)
                    check(abs(got["mean"] - statistics.mean(xs)) < 1e-12,
                          tag + ": mean %s %s %s" % (wn, m, key))
                    if len(xs) < 2:
                        check(got["sd"] is None,
                              tag + ": sd should be null at n=1 %s" % key)
                    else:
                        check(got["sd"] is not None and
                              abs(got["sd"] - statistics.stdev(xs)) < 1e-12,
                              tag + ": sd %s %s %s is %r, stdev %r"
                              % (wn, m, key, got["sd"],
                                 statistics.stdev(xs)))
                    check(got["of"] == of, tag + ": of %s" % key)
                    should = 2 * len(xs) < of
                    if should:
                        n_warn += 1
                    check(bool(got["warn"]) == should,
                          tag + ": warn %s %s %s n=%d of=%d is %r"
                          % (wn, m, key, len(xs), of, got["warn"]))
                    if should:
                        check(got["warn"] == "usable in %d of %d pairs"
                              % (len(xs), of), tag + ": warn text")
        for n in ORDER:
            ru = payload["region_usable"][wn][n]
            check(ru["usable"] == usable[(wn, n)] and ru["of"] == of,
                  tag + ": region_usable %s %s %r, expected %d of %d"
                  % (wn, n, ru, usable[(wn, n)], of))

    sm = circuit.summary(payload)
    check(sm["n_cells"] == n_cells and sm["n_warn"] == n_warn
          and sm["n_absent"] == n_absent,
          tag + ": summary %r vs cells %d warn %d absent %d"
          % ({k: sm[k] for k in ("n_cells", "n_warn", "n_absent")},
             n_cells, n_warn, n_absent))
    return {"ok": len(FAILS) == before, "cells": n_cells, "warn": n_warn,
            "absent": n_absent, "grey": grey}


# --------------------------------------------------------------------------
# Real data
# --------------------------------------------------------------------------
def fetch(gid, path, want=None):
    from backend import app as appmod
    c = appmod.app.test_client()
    info = c.get("/api/arc/coupling/%s" % gid).get_json()
    ov = c.get("/api/arc/coupling/%s/overview" % gid).get_json()
    if not info.get("reachable"):
        sys.exit("%s is not reachable from this machine." % gid)
    by = {}
    for p in info["pairs"]:
        by.setdefault(circuit.cue_type_of(p), []).append(p)
    want = want or max((t for t in by if t), key=lambda t: len(by[t]))
    results = []
    for p in by[want]:
        t = time.time()
        body = c.post("/api/arc/coupling/%s/run" % gid,
                      json={"pair_id": p["pair_id"], "params": {}}).get_json()
        if not body.get("ok"):
            sys.exit("pair %s: %s" % (p["pair_id"], body.get("error")))
        results.append(body)
        print("  pair %s %s %.1fs" % (p["pair_id"], p["label"],
                                      time.time() - t))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"gid": gid, "label": info["label"], "entry": info["entry"],
                   "cue_type": want, "all_pairs": info["pairs"],
                   "probe": ov["probe"], "results": results}, f)
    print("cached", path)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_real(d):
    res = d["results"]
    of = sum(1 for p in d["all_pairs"]
             if circuit.cue_type_of(p) == d["cue_type"])
    return circuit.build(
        res, d["probe"], "state", d["cue_type"], res[0]["run_params"],
        {"gid": d["gid"], "session_label": d["label"],
         "bank_entry": d["entry"]["id"],
         "bank_version": d["entry"]["version"]}, of=of), of


def real(path):
    d = load(path)
    FAILS_BEFORE = len(FAILS)
    payload, of = build_real(d)
    r = verify(payload, d["results"], d["probe"], d["label"], of=of)
    # A relocated probe that Coupling DID compute: numbers existed in the
    # results and the circuit dropped them. Otherwise "grey has no cells"
    # would pass for a region Coupling had refused anyway.
    verdict = {p["intended"]: p["verdict"] for p in d["probe"]}
    reloc_computed = sorted({
        n for res in d["results"] for w in res["windows"]
        for n, x in w["regions"].items()
        if verdict.get(n) == "relocated" and x["usable"]})
    # The absent cells are exactly the pairs where one side was unusable.
    dead_pairs = 0
    for wn in payload["windows"]:
        live = [n for n in ORDER if n not in r["grey"]]
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                both = any(
                    w["regions"][a]["usable"] and w["regions"][b]["usable"]
                    for res in d["results"] for w in res["windows"]
                    if w["window"] == wn)
                key = a + "|" + b
                present = key in payload["cells"][wn]["coherence"]
                check(present == both, d["label"] + ": %s %s present=%s "
                      "both-usable-somewhere=%s" % (wn, key, present, both))
                dead_pairs += (not both)
    json.dumps(payload)          # must be plain JSON
    print("  %s  %s  %d of %d pairs  windows %s"
          % (d["label"], d["cue_type"], len(d["results"]), of,
             ",".join(payload["windows"])))
    print("    grey: %s" % ", ".join("%s (%s)" % (n, verdict.get(n))
                                     for n in r["grey"]))
    print("    relocated probes Coupling computed and the circuit "
          "dropped: %s" % (", ".join(reloc_computed) or "none"))
    print("    cells kept %d, of which warn %d; absent %d (all 3 methods x "
          "%d windows); absent region pairs per method %d"
          % (r["cells"], r["warn"], r["absent"], len(payload["windows"]),
             dead_pairs))
    print("    summary: %s" % json.dumps(
        {k: v for k, v in circuit.summary(payload).items()
         if k != "by_window"}))
    return len(FAILS) == FAILS_BEFORE, r


# --------------------------------------------------------------------------
# Synthetic pair results
# --------------------------------------------------------------------------
def _probe(verdicts=None):
    verdicts = verdicts or {}
    return [{"slot": "S%d" % i, "intended": n, "label": n,
             "verdict": verdicts.get(n, "intended"),
             "why": "Histology says %s." % verdicts.get(n, "intended")}
            for i, n in enumerate(ORDER)]


def synth(pair_id, label="High tone → Noise",
          windows=("pre", "cue1", "cue2", "post"), dead=None, curves=False,
          params=None, kind=None, value=None):
    """A pair_connectivity-shaped result. `dead` is {window: {regions}}."""
    dead = dead or {}
    value = value or (lambda pid, w, a, b, m:
                      round(0.1 + 0.01 * pid + 0.001 * ORDER.index(a)
                            + 0.0001 * ORDER.index(b)
                            + {"coherence": 0, "raw_cc": .2,
                               "amp_cc": .4}[m], 6))
    wins = []
    for wn in windows:
        gone = set(dead.get(wn, ()))
        regs = {n: {"channel": None if n in gone else 1, "usable":
                    n not in gone, "blocked": "wires" if n in gone else None,
                    "why": ("%s dead" % n) if n in gone else None}
                for n in ORDER}
        rows = []
        for i, a in enumerate(ORDER):
            for b in ORDER[i + 1:]:
                row = {"a": a, "b": b}
                for m in ("coherence", "raw_cc", "amp_cc"):
                    if a in gone or b in gone:
                        row[m] = None
                        continue
                    s = {"value": value(pair_id, wn, a, b, m), "x": 8.0,
                         "x_unit": "Hz", "what": "t"}
                    row[m] = {"summary": s, "curve": {"x": [], "y": []}} \
                        if curves else s
                rows.append(row)
        wins.append({"window": wn, "t0": 100.0 * pair_id, "t1":
                     100.0 * pair_id + 10, "regions": regs, "pairs": rows})
    p = {"analysis_fs": 1000.0, "low": 4.0, "high": 12.0, "max_lag_s": 0.5,
         "summary_hz": 8.0, "nperseg": 1000, "noverlap": 500, "nfft": 2000,
         "methods": ["coherence", "raw_cc", "amp_cc"], "pad_s": 10.0}
    p.update(params or {})
    out = {"pair_id": pair_id, "label": label, "windows": wins,
           "region_order": list(ORDER), "params": p,
           "notch": {"hz": 60.0, "applied": True}}
    if kind:
        out["kind"] = kind
    return out


def refused(fn, needle, tag):
    try:
        fn()
    except circuit.CircuitError as exc:
        msg = str(exc)
        check(needle.lower() in msg.lower(),
              tag + ": refused, but the sentence does not name %r: %s"
              % (needle, msg))
        return msg
    check(False, tag + ": was not refused")
    return None


SRC = {"gid": "sTEST", "session_label": "synthetic", "bank_entry": "e",
       "bank_version": 1}
READ_PARAMS = {"low": 4.0, "high": 12.0, "summary_hz": 8.0,
               "max_lag_ms": 500.0, "notch_hz": 60.0, "pad_s": 10.0,
               "analysis_fs": 1000.0,
               "channel_rule": "lowest-numbered usable wire"}


def synthetic():
    T = "HighTone_Noise"

    # A: n=1 cell, a region usable in no pair, a relocated probe WITH numbers.
    # Left ACC is dead in cue1 of every pair but pair 3; Right OFC is dead
    # everywhere; Left POR is relocated but fully computed in the results.
    res = [synth(i, dead={
        "pre": {"Right OFC"}, "cue2": {"Right OFC"}, "post": {"Right OFC"},
        "cue1": {"Right OFC"} | ({"Left ACC"} if i != 3 else set())})
        for i in range(1, 9)]
    probe = _probe({"Left POR": "relocated", "Right PER": "missed",
                    "Left PER": "unscored"})
    pl = circuit.build(res, probe, "state", T, READ_PARAMS, SRC)
    r = verify(pl, res, probe, "synthetic A")
    c = pl["cells"]["cue1"]["coherence"].get("Right ACC|Left ACC")
    check(c and c["n"] == 1 and c["sd"] is None
          and c["warn"] == "usable in 1 of 8 pairs",
          "synthetic A: the n=1 cell is %r" % c)
    check(not any("Right OFC" in k for w in pl["cells"].values()
                  for m in w.values() for k in m),
          "synthetic A: Right OFC, usable in no pair, has cells")
    check(pl["region_usable"]["pre"]["Right OFC"]["usable"] == 0,
          "synthetic A: Right OFC usable count")
    check(pl["grey"] == ["Right PER", "Left POR", "Left PER"],
          "synthetic A: grey %r" % pl["grey"])
    check(not any("Left POR" in k for w in pl["cells"].values()
                  for m in w.values() for k in m),
          "synthetic A: relocated Left POR has cells")
    print("  A  n=1 cell, dead region, relocated-with-numbers: cells %d "
          "warn %d absent %d grey %s" % (r["cells"], r["warn"], r["absent"],
                                        r["grey"]))

    # B: both method-result shapes give the same payload.
    flat = [synth(i) for i in range(1, 5)]
    nest = [synth(i, curves=True) for i in range(1, 5)]
    pa = circuit.build(flat, _probe(), "state", T, READ_PARAMS, SRC)
    pb = circuit.build(nest, _probe(), "state", T, READ_PARAMS, SRC)
    check(pa["cells"] == pb["cells"], "synthetic B: shapes disagree")
    check(len(pa["cells"]["pre"]["coherence"]) == 66,
          "synthetic B: 66 cells with nothing grey")
    verify(pb, nest, _probe(), "synthetic B nested")
    print("  B  flat and nested method results: identical, 66 cells a panel")

    # C: transition windows, names taken from the results.
    tr = [synth(i, windows=("onset", "switch", "offset"), kind="transition",
                params={"before_s": 1.0, "after_s": 2.0}) for i in (2, 5, 7)]
    pt = circuit.build(tr, _probe(), "transition", T,
                       dict(READ_PARAMS, before_s=1.0, after_s=2.0), SRC)
    check(pt["windows"] == ["onset", "switch", "offset"],
          "synthetic C: windows %r" % pt["windows"])
    check(pt["params"]["kind"] == "transition"
          and pt["params"]["before_s"] == 1.0, "synthetic C: params")
    check(pt["pairs"][0]["opener_t"] == 201.0, "synthetic C: opener_t %r"
          % pt["pairs"][0]["opener_t"])
    verify(pt, tr, _probe(), "synthetic C")
    odd = [synth(i, windows=("a", "b")) for i in (1, 2)]
    po = circuit.build(odd, _probe(), "transition", T, None, SRC)
    check(po["windows"] == ["a", "b"], "synthetic C: arbitrary window names")
    print("  C  transition windows onset/switch/offset, and arbitrary names")

    # D: refusals.
    msgs = []
    msgs.append(refused(lambda: circuit.build(
        [synth(1), synth(2, label="Low Tone → Click")], _probe(),
        "state", T, None, SRC), "Low Tone → Click", "mixed cue types"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1), synth(2, params={"low": 5.0})], _probe(), "state", T,
        None, SRC), "low is 4 in pair 1 and 5 in pair 2", "mixed params"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1), synth(2, params={"max_lag_s": 0.25})], _probe(), "state",
        T, None, SRC), "max_lag_s", "mixed lag"))
    notched = synth(2)
    notched["notch"] = {"hz": None, "applied": False}
    msgs.append(refused(lambda: circuit.build(
        [synth(1), notched], _probe(), "state", T, None, SRC), "notch_hz",
        "mixed notch"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1), synth(2, windows=("onset", "switch", "offset"))],
        _probe(), "state", T, None, SRC), "same windows", "mixed windows"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1, kind="state"), synth(2, kind="transition")], _probe(),
        "state", T, None, SRC), "transition", "mixed kinds"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1), synth(2)], _probe(), "transition", T, None, SRC),
        "state windows", "state results built as transition"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1), synth(2)], _probe(), "state", T,
        dict(READ_PARAMS, high=30.0), SRC), "parameters given",
        "params argument disagrees with the results"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1), synth(1)], _probe(), "state", T, None, SRC),
        "more than once", "duplicate pair"))
    msgs.append(refused(lambda: circuit.build(
        [synth(1)], _probe(), "state", "Click_Noise", None, SRC),
        "never pooled", "wrong cue type"))
    for m in msgs:
        if m:
            print("     refused: %s" % m)

    # E: cue types, names.
    check(circuit.cue_type_of({"label": "High tone → Low Tone"})
          == "HighTone_LowTone", "cue_type_of contract pair")
    check(circuit.cue_type_of({"opener_label": "click",
                               "closer_label": "NOISE"}) == "Click_Noise",
          "cue_type_of case")
    check(circuit.cue_type_of({"label": "Low Tone -> Click"})
          == "LowTone_Click", "cue_type_of ascii arrow")
    check(circuit.cue_type_of({"label": "Tone → Shock"}) is None,
          "cue_type_of unknown")
    check(circuit.cue_type_of({"label": ""}) is None, "cue_type_of empty")
    nm = circuit.name_for({"project": "DEWEY", "mouse": 4, "session": 1,
                           "phase": "Precon", "phase_n": 1, "run": "SPC",
                           "cue_type": "HighTone_LowTone",
                           "window_kind": "state"})
    check(nm == "DEWEY r4 s1 Precon1 SPC · High tone → Low Tone "
          "· state", "name_for: %r" % nm)
    check(circuit.subject_key("g", "Click_Noise", "state")
          == "circuit|g|Click_Noise|state", "subject_key")

    # F: no histology at all is unscored, i.e. grey -- absent is not
    # negative.
    pn = circuit.build([synth(1)], [], "state", T, None, SRC)
    check(pn["grey"] == ORDER and not any(
        m for w in pn["cells"].values() for m in w.values()),
        "no histology should grey everything")
    print("  E/F cue types, names, and no-histology-is-grey")


# --------------------------------------------------------------------------
# Negative controls
# --------------------------------------------------------------------------
def controls(real_paths):
    def relocated_kept():
        circuit.GREY_VERDICTS = frozenset(("missed", "unscored"))

    def sd_ddof0():
        def sd(xs):
            if len(xs) < 2:
                return None
            m = sum(xs) / len(xs)
            return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
        circuit._sample_sd = sd

    def warn_at_half():
        circuit._warn = lambda n, of: (("usable in %d of %d pairs" % (n, of))
                                       if n <= of / 2.0 else None)

    def summary_value_nested_only():
        orig = circuit.summary_value

        def only(got):
            if isinstance(got, dict) and not isinstance(got.get("summary"),
                                                        dict):
                return None
            return orig(got)
        circuit.summary_value = only

    breaks = [("relocated probes not excluded", relocated_kept),
              ("SD with ddof=0", sd_ddof0),
              ("warn at n <= of/2", warn_at_half),
              ("only the nested method shape read", summary_value_nested_only)]
    saved = {k: getattr(circuit, k) for k in
             ("GREY_VERDICTS", "_sample_sd", "_warn", "summary_value")}
    all_caught = True
    for name, brk in breaks:
        global FAILS
        keep = FAILS
        FAILS = []
        try:
            brk()
            try:
                synthetic_quiet()
                for p in real_paths:
                    d = load(p)
                    payload, of = build_real(d)
                    verify(payload, d["results"], d["probe"], d["label"],
                           of=of)
            except circuit.CircuitError as exc:
                FAILS.append("refused: %s" % exc)
            caught = len(FAILS)
        finally:
            for k, v in saved.items():
                setattr(circuit, k, v)
            FAILS = keep
        all_caught &= caught > 0
        print("  %-38s %s (%d failed assertions)"
              % (name, "CAUGHT" if caught else "NOT CAUGHT", caught))
    check(all_caught, "a negative control was not caught")
    # Restored: the clean run must be clean again.
    before = len(FAILS)
    synthetic_quiet()
    check(len(FAILS) == before, "engine not restored after the controls")


def synthetic_quiet():
    out = sys.stdout
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    try:
        synthetic()
    finally:
        sys.stdout.close()
        sys.stdout = out


def main(argv):
    if argv[:1] == ["--fetch"]:
        fetch(argv[1], argv[2], argv[3] if len(argv) > 3 else None)
        return 0
    real_paths = [a for a in argv if a.endswith(".json")]
    if real_paths:
        print("Real data")
        for p in real_paths:
            real(p)
    else:
        print("Real data: skipped (no cache given; make one with --fetch)")
    print("Synthetic")
    synthetic()
    print("Negative controls")
    controls(real_paths)
    if FAILS:
        print("\nFAIL (%d)" % len(FAILS))
        for f in FAILS[:60]:
            print("  " + f)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
