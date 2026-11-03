# -*- coding: utf-8 -*-
"""Checks for tools/precon_average.py.

    python tools\\check_precon_average.py

1. Known answers, on made-up rats: the per-rat mean is the mean of that
   rat's cells in the view; the t, df and p are a one-sample t on those
   means (against scipy); BH matches a hand implementation; a pair with
   fewer than 3 rats is not tested; cue - rest is each rat's cue mean minus
   its rest mean; the cue - baseline and food - no-food drifts are not read.
2. On the real run: the "all" view and "cue sessions - rest" recomputed
   independently from the drift payloads agree with the tool's JSON.
3. CONTROL: the same per-rat values with random signs give p < .05 at
   about the chance rate, so the test is not finding structure that is
   not there.
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import precon_average as PA                              # noqa: E402

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond or detail == "" else "  " + str(detail)[:300]))


def known_answers():
    print("1. known answers")
    from scipy import stats
    # rat -> pair -> cells (band, kind, window, method, role, delta)
    rows = {}
    vals = {"r1": 0.10, "r2": 0.30, "r3": 0.20, "r4": -0.05}
    for rat, v in vals.items():
        rows[rat] = {
            "A|B": [("theta", "state", "cue1", "coherence", "food", v),
                    ("theta", "state", "cue1", "coherence", "food", v + 0.2),
                    ("beta", "transition", "onset", "raw_cc", "no_food", v),
                    ("theta", "rest", "rest", "coherence", None, -v)],
            "A|C": ([("theta", "state", "pre", "amp_cc", "food", 1.0)]
                    if rat in ("r1", "r2") else []),
        }
    results, pairs, rats = PA.analyse(rows)
    V = {(v["view"], v["level"]): {e["pair"]: e for e in v["entries"]}
         for v in results}
    e = V[("all", "all")]["A|B"]
    want = {r: (v + (v + 0.2) + v) / 3 for r, v in vals.items()}
    check("a rat's value is the mean of its cells in the view",
          all(abs(e["per_rat"][r] - want[r]) < 1e-12 for r in want),
          e["per_rat"])
    t, p = stats.ttest_1samp(list(want.values()), 0.0)
    check("t and p are a one-sample t across rats (scipy agrees)",
          abs(e["t"] - t) < 1e-9 and abs(e["p"] - p) < 1e-9 and e["df"] == 3,
          (e["t"], t, e["p"], p))
    check("rats up is counted from the per-rat means",
          e["pos"] == sum(1 for v in want.values() if v > 0), e["pos"])
    s = V[("kind", "state")]["A|B"]
    check("the state view reads only state cells",
          all(abs(s["per_rat"][r] - (vals[r] + vals[r] + 0.2) / 2) < 1e-12
              for r in vals))
    check("rest is its own view, not in 'all'",
          all(abs(V[("rest", "all")]["A|B"]["per_rat"][r] + vals[r]) < 1e-12
              for r in vals))
    cr = V[("cue-rest", "all")]["A|B"]
    check("cue - rest is each rat's cue mean minus its rest mean",
          all(abs(cr["per_rat"][r] - (want[r] + vals[r])) < 1e-12
              for r in vals))
    c = V[("all", "all")]["A|C"]
    check("a pair with fewer than 3 rats is not tested",
          c["k"] == 2 and c["p"] is None and c["q"] is None, c)
    ps = [0.01, 0.04, 0.03, None, 0.5]
    q = PA.bh(ps)
    m = 4
    by = sorted([(p, i) for i, p in enumerate(ps) if p is not None])
    hand = [None] * len(ps)
    prev = 1.0
    for rank in range(m, 0, -1):
        p, i = by[rank - 1]
        prev = min(prev, p * m / rank)
        hand[i] = prev
    check("BH matches a hand implementation, None stays None",
          q == hand, (q, hand))
    check("the p of a t test is the two-sided tail (scipy agrees)",
          abs(PA.t_sf2(2.5, 7) - 2 * stats.t.sf(2.5, 7)) < 1e-12)


def real_run():
    print("2. the real run, recomputed another way")
    path = PA.OUT + ".json"
    if not os.path.exists(path):
        print("  (no docs/dewey-precon-average.json; run the tool first)")
        return
    doc = json.load(open(path, encoding="utf-8"))
    import precon_drift_report as PR
    log, _ = PR.load_runlog(PA.RUNLOG)
    rdir = os.path.dirname(PA.RUNLOG)
    per_cue, per_rest = {}, {}
    read = 0
    for key, d in log["drifts"].items():
        band, kind, role, contrast = key.split("|")
        if contrast != "raw":
            continue
        read += 1
        P = PR.payload_of(d, rdir)
        tgt = per_rest if kind == "rest" else per_cue
        for byw in P["cells"].values():
            for cells in byw.values():
                for pk, c in cells.items():
                    for x in c.get("deltas") or []:
                        if x.get("delta") is not None:
                            tgt.setdefault(pk, {}).setdefault(
                                x["rat"], []).append(x["delta"])
    check("only the raw drifts are read (15 of the 33)",
          read == 15 and len(doc["from"]) == 15, (read, len(doc["from"])))
    V = {(v["view"], v["level"]): {e["pair"]: e for e in v["entries"]}
         for v in doc["views"]}
    bad = []
    for pk, byrat in per_cue.items():
        e = V[("all", "all")][pk]
        for rat, xs in byrat.items():
            if abs(e["per_rat"][rat] - sum(xs) / len(xs)) > 1e-9:
                bad.append((pk, rat))
    check("every rat's 'all' value agrees (%d pairs)" % len(per_cue),
          not bad, bad[:5])
    bad = []
    for pk, byrat in per_cue.items():
        e = V[("cue-rest", "all")][pk]
        for rat, xs in byrat.items():
            rs = (per_rest.get(pk) or {}).get(rat)
            if not rs:
                continue
            want = sum(xs) / len(xs) - sum(rs) / len(rs)
            if abs(e["per_rat"][rat] - want) > 1e-9:
                bad.append((pk, rat))
    check("every rat's cue - rest value agrees", not bad, bad[:5])
    return V


def control(V):
    print("3. CONTROL: random signs")
    if not V:
        return
    from scipy import stats
    random.seed(11)
    hits = tot = 0
    for _ in range(300):
        for e in V[("all", "all")].values():
            if e["p"] is None:
                continue
            vals = [v * random.choice((-1, 1)) for v in e["per_rat"].values()]
            _t, p = stats.ttest_1samp(vals, 0.0)
            tot += 1
            hits += p < 0.05
    rate = hits / tot
    check("p < .05 at no more than about chance (%.1f%%)" % (100 * rate),
          rate < 0.08, rate)
    real = sum(1 for e in V[("all", "all")].values()
               if e["p"] is not None and e["p"] < 0.05)
    print("  (the real 'all' view: %d of %d pairs at p < .05)"
          % (real, sum(1 for e in V[("all", "all")].values()
                       if e["p"] is not None)))


def main():
    known_answers()
    V = real_run()
    control(V)
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
