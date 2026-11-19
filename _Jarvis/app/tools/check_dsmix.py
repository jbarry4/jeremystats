# -*- coding: utf-8 -*-
"""Checks backend/dsmix.py on made-up recordings with a known answer:
the Tarcsay relative-sink score (DS3), its noise floor, the probability
trim and the mix-up.  python tools/check_dsmix.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from backend import dsmix  # noqa: E402

FAILS = []


def ok(name, cond, why=""):
    print(("ok    " if cond else "FAIL  ") + name + ("" if cond else "  -- " + str(why)))
    if not cond:
        FAILS.append(name)


def recording(kinds, seed=0, noise=0.01):
    """events x 16 contacts x 101 samples (+-50 ms). One blade holds OML
    (contact 6) and MML (contact 9) with a little sink between, as one hump;
    a source parts it from the other blade (contact 12), which every event
    has. Each kind says its OML and MML sink sizes."""
    rng = np.random.default_rng(seed)
    t = np.linspace(-50, 50, 101)
    bump = np.exp(-(t ** 2) / (2 * 4.0 ** 2))
    disp = rng.normal(0, noise, (len(kinds), 16, 101))
    for i, (o, m) in enumerate(kinds):
        disp[i, 5] -= o * bump
        disp[i, 8] -= m * bump
        disp[i, 6] -= 0.08 * bump
        disp[i, 7] -= 0.08 * bump
        disp[i, 9] += 0.3 * bump
        disp[i, 10] += 0.3 * bump
        disp[i, 11] -= 1.2 * bump
    nums = np.arange(1, 17)
    return {"disp": disp, "nums_sel": nums[2:13], "nums_all": nums,
            "prof": disp[:, 2:13, 50], "types_delta": np.ones(len(kinds), int)}


# 60 pure OML (DS1), 60 pure MML (DS2), 30 balanced (hybrid), 10 too small.
kinds = [(1.0, 0.0)] * 60 + [(0.0, 1.0)] * 60 + [(0.5, 0.45)] * 30 + [(0.001, 0.001)] * 10
A = recording(kinds)
# The split's classes: the hybrids and the tiny ones fall on either side.
types = np.array([1] * 60 + [2] * 60 + [1, 2] * 15 + [1, 2] * 5)
rs = dsmix.relsink(A, types)
ok("OML and MML are found from the classes' mean sinks", rs.get("oml") == 6 and rs.get("mml") == 9, rs)
sc = rs["score"]
ok("a pure OML event scores near +1, a pure MML one near -1",
   np.nanmin(sc[:60]) > 0.9 and np.nanmax(sc[60:120]) < -0.9, (np.nanmin(sc[:60]), np.nanmax(sc[60:120])))
ok("a balanced event scores near 0", np.all(np.abs(sc[120:150]) < 0.2), sc[120:150])
ok("events with sinks at noise level are unscorable, not balanced",
   rs["unscorable"][150:].sum() >= 8 and not rs["unscorable"][:150].any(), rs["unscorable"].sum())
# (The floor is the baseline's 99th percentile, so about one noise event in
# a hundred passes it by design.)
t3, d3 = dsmix.ds3_layer(rs, types, 0.5)
ok("DS3 is exactly the balanced events; the rest keep their split's class; the unscorable are not DS3",
   (t3[120:150] == 3).all() and (t3[:120] == types[:120]).all()
   and (t3[150:][rs["unscorable"][150:]] == types[150:][rs["unscorable"][150:]]).all()
   and 30 <= d3["counts"]["3"] <= 32 and d3["unscorable"]["n"] >= 8, d3["counts"])
ok("the cut is a parameter: at 0.05 fewer are DS3", dsmix.ds3_layer(rs, types, 0.05)[1]["counts"]["3"] < 30)
# A source at one layer is "no input there", never a flipped score.
B = recording([(1.0, -0.5)] * 40 + [(0.0, 1.0)] * 40)
rb = dsmix.relsink(B, np.array([1] * 40 + [2] * 40))
ok("a source at MML leaves an OML event at +1 (sink only, floored at 0)", np.nanmin(rb["score"][:40]) > 0.99)
# One class only: no layers.
ok("with one class there is no OML and MML, and that is said",
   "why" in dsmix.relsink(A, np.ones(len(kinds), int)))

# The fit: two tight families, and one family cut in half.
rng = np.random.default_rng(1)
x2 = np.concatenate([rng.normal(0, 1, 200), rng.normal(8, 1, 200)]).reshape(-1, 1)
ty2 = np.array([1] * 200 + [2] * 200)
p_own, p_max = dsmix.posterior(x2, ty2)
m2 = dsmix._mix(p_own, np.ones(400, bool))
ok("two families far apart: the mix-up is clean and nobody is unsure",
   m2["word"] == "clean" and m2["est"] < 0.01 and (p_max < 0.8).sum() == 0, m2)
x1 = rng.normal(0, 1, 400)
ty1 = (x1 > 0).astype(int) + 1
p1, pm1 = dsmix.posterior(x1.reshape(-1, 1), ty1)
m1 = dsmix._mix(p1, np.ones(400, bool))
ok("one family cut in half reads as mixed", m1["word"] == "mixed" and m1["est"] > 0.15, m1)
x3 = np.concatenate([rng.normal(0, 1, 200), rng.normal(3, 1, 200)]).reshape(-1, 1)
p3, pm3 = dsmix.posterior(x3, ty2)
un = pm3 < 0.8
ok("two overlapping families: some events are unsure, and trimming them lowers the mix-up",
   10 < un.sum() < 200 and dsmix._mix(p3, ~un)["est"] < dsmix._mix(p3, np.ones(400, bool))["est"],
   (int(un.sum()), dsmix._mix(p3, ~un), dsmix._mix(p3, np.ones(400, bool))))
ok("modes are cleaned: an unknown mode is plain, cuts stay in range",
   dsmix.clean_mode({"mode": "x", "ds3_cut": 9, "trim_cut": 0.1}) == {"mode": "plain", "ds3_cut": 0.95, "trim_cut": 0.5})

print("\n" + ("all checks passed" if not FAILS else "%d FAILED: %s" % (len(FAILS), "; ".join(FAILS))))
sys.exit(1 if FAILS else 0)
