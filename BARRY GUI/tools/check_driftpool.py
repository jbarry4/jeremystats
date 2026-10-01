# -*- coding: utf-8 -*-
"""Checks for backend/driftpool.py -- the pooled, within-rat Precon drift.

    python tools\\check_driftpool.py

On made-up circuits, so every expected number is worked out here:
  - a rat-day is every cue pair of BOTH pairings, blind to type (8 + 8 = 16)
  - a rat's change is P4 - P1 of those means; its variance the two se^2
  - the pooled change and test are drift.pool_rats + drift.hk_test on
    exactly those rows (the functions every within-rat drift uses)
  - minus FP is (P4 cue - P4 rest) - (P1 cue - P1 rest), variance four se^2
  - fewer than 5 rats: shown, not tested; 5: tested
  - tier 1 is q < .05; tier 2 is (q < .25 or p < .01) with most rats the
    same way; neither otherwise
  - BH runs across every window x method x region pair of one layer
  - a cue pair in two circuits of one recording is refused
  - top(): one entry per region pair, listing where it stands out
CONTROL: circuits with no day effect at all -- nothing survives, and p < .05
turns up at about the chance rate.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import drift, driftpool as DP                # noqa: E402

N = {"ok": 0, "bad": 0}
WIN = ["pre", "cue1"]
MET = ["coherence"]
KEYS = ["Right ACC|Left ACC", "Right OFC|Left OFC"]


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond or detail == "" else "  " + str(detail)[:300]))


def circuit(vals_by_key, pair_ids, cue_type, kind="state", windows=WIN,
            grey=()):
    """A circuit payload: every window x method gets the same values."""
    cells = {}
    for w in windows:
        cells[w] = {}
        for m in MET:
            cells[w][m] = {}
            for k, vals in vals_by_key.items():
                cells[w][m][k] = {"values": [{"pair_id": p, "v": v}
                                             for p, v in zip(pair_ids, vals)]}
    return {"kind": kind, "band": "theta", "windows": list(windows),
            "methods": MET, "region_order": ["Right ACC", "Right OFC",
                                             "Left OFC", "Left ACC"],
            "grey": list(grey), "cue_type": cue_type, "cells": cells,
            "params": {"channel_rule": "lowest"}}


def rest_circuit(vals_by_key):
    return {"kind": "rest", "windows": ["rest"], "methods": MET,
            "cells": {"rest": {"coherence": {
                k: {"values": [{"pair_id": i, "v": v}
                               for i, v in enumerate(vals, 1)]}
                for k, vals in vals_by_key.items()}}}}


def sd(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def make(nrats, shift, rest_shift=0.0, seed=1):
    rnd = random.Random(seed)
    members, rest, raw = [], [], {}
    for r in range(1, nrats + 1):
        for day, add in (("Precon1", 0.0), ("Precon4", shift)):
            a = {k: [0.3 + add + rnd.gauss(0, 0.05) for _ in range(8)]
                 for k in KEYS}
            b = {k: [0.3 + add + rnd.gauss(0, 0.05) for _ in range(8)]
                 for k in KEYS}
            rv = {k: [0.2 + (rest_shift if day == "Precon4" else 0)
                      + rnd.gauss(0, 0.03) for _ in range(8)] for k in KEYS}
            raw[(r, day)] = (a, b, rv)
            members.append({"rat": "r%d" % r, "day": day,
                            "payload": circuit(a, range(1, 9), "Click_LowTone"),
                            "ref": {"id": "c%d%sa" % (r, day),
                                    "version_id": "v"}})
            members.append({"rat": "r%d" % r, "day": day,
                            "payload": circuit(b, range(9, 17),
                                               "Noise_HighTone"),
                            "ref": {"id": "c%d%sb" % (r, day),
                                    "version_id": "v"}})
            rest.append({"rat": "r%d" % r, "day": day,
                         "payload": rest_circuit(rv),
                         "ref": {"id": "rest%d%s" % (r, day),
                                 "version_id": "v"}})
    return members, rest, raw


def known_answers():
    print("known answers")
    members, rest, raw = make(6, 0.05, rest_shift=0.04)
    P = DP.build(members, rest, "theta", "state")
    k = KEYS[0]
    c = P["cells"]["cue1"]["coherence"][k]
    rows = []
    for r in range(1, 7):
        v1 = raw[(r, "Precon1")][0][k] + raw[(r, "Precon1")][1][k]
        v4 = raw[(r, "Precon4")][0][k] + raw[(r, "Precon4")][1][k]
        rows.append({"rat": "r%d" % r,
                     "delta": sum(v4) / 16 - sum(v1) / 16,
                     "v": sd(v1) ** 2 / 16 + sd(v4) ** 2 / 16, "n": 32,
                     "left": sum(v1) / 16, "right": sum(v4) / 16})
    check("a rat-day is all 16 cue pairs, both pairings, blind to type",
          all(d["n"] == 32 for d in c["deltas"]), [d["n"] for d in c["deltas"]])
    check("each rat's change is P4 - P1 of those means",
          all(abs(d["delta"] - r["delta"]) < 1e-12
              for d, r in zip(c["deltas"], rows)))
    mp = drift.pool_rats(rows)
    t = drift.hk_test(None, None, pooled=mp)
    check("pooled and tested by drift.pool_rats + drift.hk_test on those rows",
          abs(c["delta"] - mp["mean"]) < 1e-12 and abs(c["t"] - t["stat"])
          < 1e-9 and abs(c["p"] - t["p"]) < 1e-12 and c["df"] == 5,
          (c["delta"], mp["mean"], c["t"], t["stat"]))
    f = P["layers"]["minus_fp"]["cells"]["cue1"]["coherence"][k]
    rows_f = []
    for r in range(1, 7):
        out = {}
        var = 0.0
        for day in ("Precon1", "Precon4"):
            a, b, rv = raw[(r, day)]
            cue = a[k] + b[k]
            out[day] = sum(cue) / 16 - sum(rv[k]) / 8
            var += sd(cue) ** 2 / 16 + sd(rv[k]) ** 2 / 8
        rows_f.append({"rat": "r%d" % r,
                       "delta": out["Precon4"] - out["Precon1"], "v": var,
                       "n": 48})
    mpf = drift.pool_rats(rows_f)
    check("minus FP: (P4 cue - P4 rest) - (P1 cue - P1 rest)",
          all(abs(d["delta"] - r["delta"]) < 1e-12
              for d, r in zip(f["deltas"], rows_f)))
    check("  its variance is the four se^2 added, and it is pooled the same",
          abs(f["delta"] - mpf["mean"]) < 1e-12)
    check("  subtracting a rest shift of +0.04 moves the change by -0.04",
          abs((c["delta"] - f["delta"]) - 0.04) < 0.02,
          c["delta"] - f["delta"])
    every = [(w, m, kk) for w in WIN for m in MET
             for kk in P["cells"][w][m]]
    qs = drift._bh([P["cells"][w][m][kk]["p"] for w, m, kk in every])
    check("BH runs across every window x method x region pair of a layer",
          all(abs(P["cells"][w][m][kk]["q"] - q) < 1e-12
              for (w, m, kk), q in zip(every, qs)))
    check("the payload names the pooling, the tiers and the minimum",
          P["cue_type"] == "pooled" and P["min_rats"] == 5
          and P["tiers"]["point_of_interest"]["q"] == 0.25
          and "minus_fp" in P["layers"])

    m4, r4, _ = make(4, 0.05)
    P4 = DP.build(m4, r4, "theta", "state")
    c4 = P4["cells"]["cue1"]["coherence"][k]
    check("4 rats: shown, not tested, and why", c4["p"] is None
          and c4["delta"] is not None and "at least 5" in (c4["why"] or ""),
          c4.get("why"))
    m5, r5, _ = make(5, 0.05)
    c5 = DP.build(m5, r5, "theta", "state")["cells"]["cue1"]["coherence"][k]
    check("5 rats: tested", c5["p"] is not None and c5["df"] == 4)

    T = DP.tier_of
    check("tier 1: q < .05", T({"p": 0.001, "q": 0.04, "majority": False}) == 1)
    check("tier 2: q < .25 with most rats the same way",
          T({"p": 0.03, "q": 0.2, "majority": True}) == 2)
    check("tier 2: p < .01 with most rats the same way",
          T({"p": 0.008, "q": 0.4, "majority": True}) == 2)
    check("not tier 2 without the majority",
          T({"p": 0.008, "q": 0.2, "majority": False}) == 0)
    check("neither: q .3 and p .02", T({"p": 0.02, "q": 0.3,
                                        "majority": True}) == 0)
    check("untested is never a tier", T({"p": None, "q": None}) == 0)

    dup = [dict(members[0]), dict(members[0])]
    dup[1] = dict(members[0], ref={"id": "x", "version_id": "v"})
    try:
        DP.build(dup + members[2:], rest, "theta", "state")
        check("a cue pair in two circuits of one recording is refused", False)
    except DP.PoolError:
        check("a cue pair in two circuits of one recording is refused", True)

    one = [m for m in members if not (m["rat"] == "r6"
                                      and m["day"] == "Precon4")]
    Po = DP.build(one, rest, "theta", "state")
    co = Po["cells"]["cue1"]["coherence"][k]
    check("a rat on one day only sits out, and says so",
          co["k"] == 5 and any("r6" in w for w in Po["warn"]), Po["warn"])

    from backend.artifacts import digest
    shuffled = list(members)
    random.Random(9).shuffle(shuffled)
    rs = list(rest)
    random.Random(4).shuffle(rs)
    check("the same circuits in any order make the same payload (digest)",
          digest(DP.build(shuffled, rs, "theta", "state"))
          == digest(DP.build(members, rest, "theta", "state")))

    big, rb, _ = make(8, 0.2, seed=3)
    Pb = DP.build(big, rb, "theta", "state")
    tops = DP.top([Pb], "raw")
    check("top: one entry per region pair",
          len({t["pair"] for t in tops}) == len(tops) == 2, len(tops))
    check("  listing every window where it stands out",
          all(len(t["where"]) == 2 for t in tops if not t["below_line"]),
          [len(t["where"]) for t in tops])


def null_circuits(nrats, windows, keys, seed):
    """No day effect anywhere: every window and region pair independent."""
    rnd = random.Random(seed)
    members, rest = [], []
    order = sorted({x for k in keys for x in k.split("|")})
    for r in range(1, nrats + 1):
        for day in ("Precon1", "Precon4"):
            for ct, ids in (("Click_LowTone", range(1, 9)),
                            ("Noise_HighTone", range(9, 17))):
                cells = {w: {"coherence": {k: {"values": [
                    {"pair_id": i, "v": 0.3 + rnd.gauss(0, 0.05)}
                    for i in ids]} for k in keys}} for w in windows}
                members.append({"rat": "r%d" % r, "day": day, "payload": {
                    "kind": "state", "band": "theta", "windows": windows,
                    "methods": ["coherence"], "region_order": order,
                    "grey": [], "cue_type": ct, "cells": cells,
                    "params": {}}, "ref": {"id": "n%d%s%s" % (r, day, ct),
                                            "version_id": "v"}})
            rest.append({"rat": "r%d" % r, "day": day, "payload": {
                "kind": "rest", "windows": ["rest"], "methods": ["coherence"],
                "cells": {"rest": {"coherence": {k: {"values": [
                    {"pair_id": i, "v": 0.2 + rnd.gauss(0, 0.03)}
                    for i in range(1, 9)]} for k in keys}}}},
                "ref": {"id": "nr%d%s" % (r, day), "version_id": "v"}})
    return members, rest


def control():
    print("CONTROL: no day effect anywhere")
    windows = ["pre", "cue1", "cue2", "post"]
    keys = ["A%d|B%d" % (i, i) for i in range(6)]
    hits = tot = drifts = with_t1 = 0
    for seed in range(60):
        members, rest = null_circuits(8, windows, keys, 500 + seed)
        P = DP.build(members, rest, "theta", "state")
        drifts += 1
        any_t1 = False
        for byw in P["cells"].values():
            for panel in byw.values():
                for c in panel.values():
                    if c["p"] is None:
                        continue
                    tot += 1
                    hits += c["p"] < 0.05
                    any_t1 = any_t1 or c["tier"] == 1
        with_t1 += any_t1
    rate = hits / tot
    check("p < .05 at about the chance rate (%.1f%% of %d tests)"
          % (100 * rate, tot), 0.025 <= rate <= 0.075, rate)
    check("a drift with any survivor is rare under the null (%d of %d)"
          % (with_t1, drifts), with_t1 <= 0.12 * drifts, with_t1)


def main():
    known_answers()
    control()
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
