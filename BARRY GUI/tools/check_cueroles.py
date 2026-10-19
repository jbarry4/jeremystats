# -*- coding: utf-8 -*-
"""check_cueroles.py -- does backend/cueroles.py read the food pair right?

On the REAL conditioning files (E:), for the eight rats of the Precon1 -> 4
analysis, the role table must reproduce the survey of 2026-09-29 exactly:
one food cue per rat, the other cue followed by food 0 times, and the food
pair being the pairing that ends on the food cue. The pairings it reads off
the Precon SPC files are also checked against the pairs the Event Bank
holds for the same rat, which were banked by a different code path (Spark's
bank route) -- two readings that must agree.

Negative controls -- each one breaks something and must be REFUSED:
  1. a synthetic session where both cues are followed by a pellet
  2. a synthetic session where no cue is
  3. rat 3's REAL conditioning with ONE extra pellet 5 s after a High tone
  4. a pellet 14.9 s after the other cue (inside the window) -> refused;
     15.1 s (outside) -> still unambiguous
  5. mirror and debounced pellets after the other cue -> NOT counted
  6. two pairings ending on the food cue -> refused
And: the duplicate J9 Con3 folder is read once; `role_source` is
deterministic (two calls, byte-identical JSON).

    python tools\\check_cueroles.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import circuit, cueroles  # noqa: E402

RATS = (3, 4, 6, 7, 8, 9, 10, 11)

#: The survey (plan, 2026-09-29): the food cue, and the food pair.
EXPECT = {
    3: ("Low Tone", "Click_LowTone"),
    4: ("Noise", "HighTone_Noise"),
    6: ("High tone", "Noise_HighTone"),
    7: ("Low Tone", "Noise_LowTone"),
    8: ("High tone", "Click_HighTone"),
    9: ("Click", "HighTone_Click"),
    10: ("Noise", "LowTone_Noise"),
    11: ("Click", "LowTone_Click"),
}

FAILS = []


def ok(cond, what):
    print("  [%s] %s" % ("ok" if cond else "FAIL", what))
    if not cond:
        FAILS.append(what)
    return cond


def refused(fn, what):
    try:
        fn()
    except cueroles.CueRoleError as exc:
        ok(True, "%s -- refused: %s" % (what, str(exc)[:150]))
        return True
    ok(False, "%s -- was NOT refused" % what)
    return False


# --------------------------------------------------------------------------
def ev(label, t, **kw):
    r = {"label": label, "t": float(t), "known": True, "is_mirror": False,
         "debounced": False}
    r.update(kw)
    return r


def session(food="Low Tone", other="High tone", n=8, extra=()):
    """A synthetic Con session: n presentations of each cue, 60 s apart,
    a pellet 10 s after every food cue, none after the other."""
    rows = []
    t = 30.0
    for _ in range(n):
        rows.append(ev(food, t))
        rows.append(ev("Pellet Delivery", t + 10.0))
        rows.append(ev(other, t + 30.0))
        t += 60.0
    rows.extend(extra)
    rows.sort(key=lambda r: r["t"])
    return rows


def synthetic_records(rat=99, n=2):
    return [{"gid": "harness-con-%d" % i, "project": "DEWEY", "mouse": rat,
             "phase": "Con", "phase_n": i + 1, "run": "SPC",
             "paths": ["__synthetic__/%d" % i], "label": "synthetic Con%d"
             % (i + 1)} for i in range(n)]


class FakeHere(object):
    """Stand in for sessreg.is_here on synthetic paths."""

    def __enter__(self):
        from backend import sessreg
        self.sessreg = sessreg
        self.was = sessreg.is_here
        sessreg.is_here = lambda p: (str(p).startswith("__synthetic__")
                                     or self.was(p))
        return self

    def __exit__(self, *a):
        self.sessreg.is_here = self.was


# --------------------------------------------------------------------------
def bank_pairings(rat):
    """The cue types the Event Bank holds for this rat's Spark entries."""
    from backend import eventbank
    from backend import store as storemod
    logs = os.path.join(APP, "GUI_logs")
    bank = eventbank.EventBank(logs, storemod.Store(logs, auto_stage=False))
    out = {}
    for e in bank.all():
        src = e.get("source") or {}
        if not str(src.get("pipeline") or "").startswith("The Arc"):
            continue
        if e.get("mouse") != rat or (e.get("project") or "") != "DEWEY":
            continue
        for x in e.get("events") or []:
            ct = circuit.cue_type_of(x)
            if ct:
                out[ct] = out.get(ct, 0) + 1
    return out


def real(records):
    print("")
    print("REAL DATA -- the eight rats' Con SPC recordings on E:")
    print("-" * 78)
    t0 = time.time()
    tables = {}
    for rat in RATS:
        try:
            tables[rat] = cueroles.role_table(rat, records)
        except cueroles.CueRoleError as exc:
            ok(False, "r%d: %s" % (rat, exc))
    secs = time.time() - t0
    print("  read in %.1f s" % secs)
    print("")
    hdr = "  %-4s %-10s %-22s %-22s %-24s %s" % (
        "rat", "food cue", "food pair", "no-food pair", "followed / presented",
        "sessions")
    print(hdr)
    for rat in RATS:
        t = tables.get(rat)
        if not t:
            continue
        s = t["source"]
        fol = ", ".join("%s %d/%d" % (c, s["followed"].get(c, 0),
                                      s["presented"].get(c, 0))
                        for c in s["presented"])
        print("  r%-3d %-10s %-22s %-22s %-24s %d read, %d skipped" % (
            rat, t["food_cue"], circuit.cue_label(t["food_pair"]),
            "; ".join(circuit.cue_label(x) for x in t["no_food_pairs"]),
            fol, len(s["sessions"]), len(s["skipped"])))
    print("")
    for rat in RATS:
        t = tables.get(rat)
        if not t:
            continue
        food, pair = EXPECT[rat]
        s = t["source"]
        ok(t["food_cue"] == food and t["food_pair"] == pair,
           "r%d: food cue %s, food pair %s (survey: %s, %s)"
           % (rat, t["food_cue"], t["food_pair"], food, pair))
        others = [c for c in s["presented"] if c != t["food_cue"]]
        ok(others and all(s["followed"].get(c, 0) == 0 for c in others),
           "r%d: the other cue%s (%s) followed by food 0 times"
           % (rat, "s" if len(others) > 1 else "", ", ".join(others)))
        ok(s["followed"].get(t["food_cue"], 0) > 0,
           "r%d: the food cue followed %d times over %d sessions"
           % (rat, s["followed"].get(t["food_cue"], 0), len(s["sessions"])))
        ok(len(t["roles"]) == 2 and sorted(t["roles"].values())
           == ["food", "no_food"],
           "r%d: exactly two pairings, one food and one no_food (%s)"
           % (rat, ", ".join("%s=%s" % kv for kv in sorted(
               t["roles"].items()))))
        banked = bank_pairings(rat)
        ok(set(banked) == set(t["roles"]),
           "r%d: the pairings read off the Precon files equal the banked "
           "ones (%s)" % (rat, ", ".join("%s x%d" % kv for kv in
                                          sorted(banked.items()))))
        for sk in s["skipped"]:
            print("        skipped %s: %s" % (sk["gid"], sk["why"]))

    # The duplicate folder: J9 Con3 is two gids for one directory.
    t9 = tables.get(9)
    if t9:
        dup = [sk for sk in t9["source"]["skipped"]
               if "same folder" in sk["why"]]
        ok(len(dup) == 1, "r9: the Con3 folder named by two gids is read "
           "once (%s)" % (dup[0]["why"] if dup else "no duplicate skipped"))

    # Deterministic: role_source travels into payloads and must not change
    # between two readings of the same files.
    if tables.get(3):
        again = cueroles.role_table(3, records)
        a = json.dumps(cueroles.role_source(tables[3]), sort_keys=True)
        b = json.dumps(cueroles.role_source(again), sort_keys=True)
        ok(a == b, "role_source is identical on a second reading (%d bytes)"
           % len(a))
    return tables


def negative(records):
    print("")
    print("NEGATIVE CONTROLS -- each breaks the reading and must be refused")
    print("-" * 78)
    pairs = ["Click_LowTone", "Noise_HighTone"]

    def run_synth(sessions, pairings=pairs):
        recs = synthetic_records(n=len(sessions))
        by = {r["paths"][0]: s for r, s in zip(recs, sessions)}
        with FakeHere():
            return cueroles.role_table(99, recs, pairings=pairings,
                                       reader=lambda f: by[f])

    # 0. The positive: the synthetic design itself reads cleanly.
    t = run_synth([session(), session()])
    ok(t["food_cue"] == "Low Tone" and t["roles"] == {
        "Click_LowTone": "food", "Noise_HighTone": "no_food"},
        "synthetic control reads: food Low Tone, Click -> Low Tone is food")

    # 1. Both cues fed, in one session.
    both = session(extra=[ev("Pellet Delivery", 30.0 + 30.0 + 8.0)])
    refused(lambda: run_synth([session(), both]),
            "1. a session where both cues get food")

    # 2. Nobody fed.
    none = [r for r in session() if r["label"] != "Pellet Delivery"]
    refused(lambda: run_synth([none]), "2. a session where no cue gets food")

    # 3. The REAL rat 3, ONE pellet added 5 s after the first High tone of
    # its first Con session; every other session read untouched.
    from backend import cueroles as cr
    broke = []

    def break_r3(folder):
        rows = cr.read_rows(folder)
        if rows is None or broke:
            return rows
        broke.append(folder)
        first = next((r for r in rows if r["label"] == "High tone"
                      and r["known"] and not r["is_mirror"]
                      and not r["debounced"]), None)
        if first is None:
            return rows
        rows = copy.deepcopy(rows)
        rows.append(ev("Pellet Delivery", first["t"] + 5.0))
        rows.sort(key=lambda r: r["t"])
        return rows
    refused(lambda: cueroles.role_table(3, records, reader=break_r3),
            "3. rat 3's real conditioning with one pellet 5 s after a "
            "High tone")
    t3 = cueroles.role_table(3, records)
    ok(t3["food_cue"] == "Low Tone", "3. ...and restored, rat 3 reads Low "
       "Tone again")

    # 4. The window's edge.
    inside = session(extra=[ev("Pellet Delivery", 60.0 + 14.9)])
    refused(lambda: run_synth([inside]),
            "4a. a pellet 14.9 s after the other cue (inside 15 s)")
    outside = session(extra=[ev("Pellet Delivery", 60.0 + 15.1)])
    # Placed so it follows NO cue within 15 s: 15.1 after the other cue and
    # 45.1 after the food cue.
    t = run_synth([outside])
    ok(t["food_cue"] == "Low Tone"
       and t["source"]["unclaimed_pellets"] == 1,
       "4b. a pellet 15.1 s after the other cue is outside the window "
       "(read as unclaimed, still unambiguous)")

    # 5. Mirrors and bounces are not pellets.
    ghost = session(extra=[
        ev("Pellet Delivery", 60.0 + 5.0, is_mirror=True),
        ev("Pellet Delivery", 60.0 + 6.0, debounced=True)])
    t = run_synth([ghost])
    ok(t["food_cue"] == "Low Tone"
       and t["source"]["followed"].get("High tone") == 0,
       "5. a mirror and a debounced pellet after the other cue are not "
       "counted")
    # ...and the same pellet NOT marked as a mirror is refused.
    real_one = session(extra=[ev("Pellet Delivery", 60.0 + 5.0)])
    refused(lambda: run_synth([real_one]),
            "5b. the same pellet, not a mirror")

    # 6. Two pairings ending on the food cue.
    refused(lambda: run_synth([session()], pairings=[
        "Click_LowTone", "Noise_LowTone"]),
        "6. two pairings ending on the food cue")
    refused(lambda: run_synth([session()], pairings=[
        "Click_Noise", "LowTone_HighTone"]),
        "6b. no pairing ending on the food cue")

    # 7. A rat with no conditioning at all (r5: no Con recordings).
    refused(lambda: cueroles.role_table(5, records),
            "7. r5, which has no Con SPC recording")


def main():
    t0 = time.time()
    records = cueroles.load_records()
    print("registry: %d records in %.1f s (one read)"
          % (len(records), time.time() - t0))
    real(records)
    negative(records)
    print("")
    if FAILS:
        print("%d FAILED:" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        return 1
    print("all checks pass (%.1f s)" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
