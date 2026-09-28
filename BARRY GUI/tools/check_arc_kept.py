# -*- coding: utf-8 -*-
"""Check that a block KEPT against the measurement is used downstream.

    python tools/check_arc_kept.py            J7 Precon2
    python tools/check_arc_kept.py <gid>

Run it from PowerShell. Nothing here writes to the Event Bank.

A banked event carries three per-window lists: `clipped` (what the read
measured), `excluded` (what somebody removed) and `kept` (what somebody put
back in against the measurement). `coupling.excluded_for` is
(clipped + excluded) - kept. This checks:

  1. NO EXISTING ENTRY CHANGES. On every real banked Spark entry, for every
     event, `excluded_for` equals an independent re-implementation of the
     union it always was -- and no real entry carries `kept` yet, so that
     equality is the whole of the before-and-after.
  2. THE ARITHMETIC, on hand-built events in every combination of shapes
     (dict or flat list on either side, state and transition windows).
  3. THE BANK ROUTE writes `kept` from the request, only where the
     measurement actually removed the block (Flask test client, `BANK.add`
     replaced by a function that keeps what it was handed).
  4. COUPLING USES IT. On the entry the bank route would have written, a
     clipped wire that is the lowest in its region, kept, becomes that
     region's wire -- in the overview's channel sanity AND in a real run,
     in a state window and in a transition window.

Negative control for 2 and 4: `excluded_for` is swapped for the bare union
(the subtraction dropped) and the same checks must fail.
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

RESULTS = {"ok": 0, "fail": 0}
STATE = ("pre", "cue1", "cue2", "post")
TRANS = ("onset", "switch", "offset")


def check(name, cond, detail=""):
    RESULTS["ok" if cond else "fail"] += 1
    print(("ok    " if cond else "FAIL  ") + name
          + ("" if cond or not detail else "   [%s]" % detail))
    return cond


def note(msg):
    print("      " + msg)


def head(msg):
    print("\n== " + msg)


def union_reference(ev):
    """The union `excluded_for` returned before `kept` existed, written out
    again here from its definition rather than imported, so the comparison
    is between two implementations and not one function with itself."""
    per, flat = {}, set()
    for key in ("clipped", "excluded"):
        got = (ev or {}).get(key)
        if isinstance(got, dict):
            for w, chans in got.items():
                per.setdefault(str(w), set()).update(int(c) for c in chans or [])
        elif got:
            flat.update(int(c) for c in got)
    if not per:
        return sorted(flat)
    for w in per:
        per[w] |= flat
    for w in STATE + TRANS:
        per.setdefault(w, set(flat))
    return {k: sorted(v) for k, v in per.items()}


def arithmetic(coupling, label=""):
    """(n_ok, n_cases) for the hand-built cases."""
    ex = coupling.excluded_for
    cases = [
        # dict clipped, dict kept, state window
        ({"clipped": {"pre": [1, 2], "cue1": [1]}, "kept": {"pre": [1]}},
         lambda r: r["pre"] == [2] and r["cue1"] == [1]),
        # transition window
        ({"clipped": {"switch": [5, 7]}, "kept": {"switch": [5]}},
         lambda r: r["switch"] == [7]),
        # kept also takes a block off `excluded`
        ({"clipped": {"pre": [1]}, "excluded": {"pre": [3]},
          "kept": {"pre": [1, 3]}},
         lambda r: r["pre"] == []),
        # flat clipped (old entry), per-window kept
        ({"clipped": [9], "kept": {"onset": [9]}},
         lambda r: isinstance(r, dict) and r["onset"] == [] and r["pre"] == [9]
         and r["switch"] == [9]),
        # flat kept applies to every window
        ({"clipped": {"pre": [4], "offset": [4, 6]}, "kept": [4]},
         lambda r: r["pre"] == [] and r["offset"] == [6]),
        # flat on both sides stays flat
        ({"clipped": [2, 3], "kept": [3]}, lambda r: r == [2]),
        # a keep of a block nothing removed changes nothing
        ({"clipped": {"cue2": [8]}, "kept": {"cue1": [8]}},
         lambda r: r["cue2"] == [8] and r["cue1"] == []),
    ]
    n = 0
    for ev, ok in cases:
        try:
            if ok(ex(ev)):
                n += 1
        except Exception:                                # noqa: BLE001
            pass
    return n, len(cases)


def main(argv):
    from backend import app as A
    from backend import coupling, nlx

    # ---------------- 1. no existing entry changes ----------------
    head("every real banked entry")
    banked = A._spark_banked()
    n_ev = n_same = n_kept = 0
    for gid, b in banked.items():
        e = A.BANK.get(b["id"]) or {}
        for ev in e.get("events") or []:
            n_ev += 1
            if ev.get("kept"):
                n_kept += 1
            if coupling.excluded_for(ev) == union_reference(ev):
                n_same += 1
    check("%d real entries, %d events: excluded_for is the union it always "
          "was, on every one" % (len(banked), n_ev),
          n_ev > 0 and n_same == n_ev, "%d of %d agree" % (n_same, n_ev))
    check("  and no real event carries `kept` yet, so nothing moved",
          n_kept == 0, "%d do" % n_kept)
    snap = os.path.join(os.environ.get("ARC_EXCL_SNAPSHOT", ""))
    if snap and os.path.exists(snap):
        before = json.load(open(snap))
        now = {g: [coupling.excluded_for(ev) for ev in
                   (A.BANK.get(b["id"]) or {}).get("events") or []]
               for g, b in banked.items()}
        check("  and equal to the snapshot taken before the change",
              json.loads(json.dumps(now, sort_keys=True)) == before,
              "differs from %s" % snap)

    # ---------------- 2. arithmetic ----------------
    head("the arithmetic")
    ok, of = arithmetic(coupling)
    check("(clipped + excluded) - kept, in every shape, state and transition",
          ok == of, "%d of %d" % (ok, of))
    real = coupling.excluded_for
    coupling.excluded_for = coupling._excluded_union
    try:
        bad, _ = arithmetic(coupling)
    finally:
        coupling.excluded_for = real
    check("NEGATIVE CONTROL: without the subtraction the cases fail",
          bad < of - 2, "%d of %d still passed" % (bad, of))

    # ---------------- 3. the bank route ----------------
    gids = [a for a in argv if not a.startswith("--")]
    if not gids:
        gids = [g for g, b in banked.items()
                if str(b.get("name") or "").startswith("DEWEY r7 s2 Precon2")]
    gid = gids[0]
    sm, got = A._spark_read(gid)
    head("the bank route, %s" % sm.get("label"))
    client = A.app.test_client()
    t = time.time()
    r = client.post("/api/arc/spark/%s/clipping" % gid, json={})
    note("clipping read: %.1f s" % (time.time() - t))
    check("the clipping route answers", r.status_code == 200)
    kept = {}
    real_add = A.BANK.add

    def fake_add(entry):
        kept["entry"] = copy.deepcopy(entry)
        return {"id": entry.get("id") or "captured", "version": -1}
    A.BANK.add = fake_add
    try:
        client.post("/api/arc/spark/%s/bank" % gid, json={})
    finally:
        A.BANK.add = real_add
    entry = kept["entry"]

    # A clipped wire that is the lowest usable one in its region, for one
    # state window and one transition window.
    bad = {int(c) for c in (sm.get("bad_channels") or [])}
    present = {int(n) for n, _p in nlx.list_csc_files(got["path"],
                                                      even_only=False)}
    rat, probe = A._coupling_probe(sm)
    blocked = A._coupling_blocked(probe)
    cmap = coupling.dewey_map()

    def pick(windows):
        for i, ev in enumerate(entry["events"], start=1):
            cl = ev.get("clipped") or {}
            for w in windows:
                for name, csc in cmap.items():
                    if name in blocked:
                        continue
                    usable = [c for c in sorted(csc)
                              if c in present and c not in bad]
                    if not usable or usable[0] not in (cl.get(w) or []):
                        continue
                    if not any(c not in (cl.get(w) or []) for c in usable[1:]):
                        continue      # needs a spare, so the change is visible
                    return i, w, name, usable[0]
        return None
    s_pick, t_pick = pick(STATE), pick(TRANS)
    check("a clipped lowest wire with a spare exists in a state window",
          s_pick is not None)
    check("  and in a transition window", t_pick is not None)
    if not (s_pick and t_pick):
        return finish()
    note("state: pair %d %s, %s CSC %d   transition: pair %d %s, %s CSC %d"
         % (s_pick + t_pick))

    ask = {}
    for pid, w, _n, c in (s_pick, t_pick):
        ask.setdefault(str(pid), {}).setdefault(w, []).append(c)
    # A keep on a block the measurement never removed must not be banked.
    ask.setdefault(str(s_pick[0]), {}).setdefault("cue2", []).append(999)
    A.BANK.add = fake_add
    try:
        r = client.post("/api/arc/spark/%s/bank" % gid,
                        json={"excluded": {}, "kept": ask})
    finally:
        A.BANK.add = real_add
    entry = kept["entry"]
    evs = entry["events"]
    check("the bank route writes `kept` onto the events, per window",
          s_pick[3] in (evs[s_pick[0] - 1].get("kept") or {}).get(s_pick[1], [])
          and t_pick[3] in (evs[t_pick[0] - 1].get("kept") or {}).get(
              t_pick[1], []),
          [evs[s_pick[0] - 1].get("kept"), evs[t_pick[0] - 1].get("kept")])
    check("  only where the measurement removed the block",
          999 not in ((evs[s_pick[0] - 1].get("kept") or {}).get("cue2") or []))
    check("  and the measurement itself is unchanged: `clipped` still names it",
          s_pick[3] in (evs[s_pick[0] - 1].get("clipped") or {}).get(
              s_pick[1], []))

    # ---------------- 4. coupling uses it ----------------
    head("coupling follows")
    fake = copy.deepcopy(A._coupling_entry(gid))
    fake["events"] = evs
    fake.setdefault("source", {})["parameters"] = entry["parameters"]
    real_entry = A._coupling_entry
    A._coupling_entry = lambda g: fake if g == gid else real_entry(g)

    def overview_wire(kind, pid, w, name):
        o = client.get("/api/arc/coupling/%s/overview%s" % (
            gid, "?kind=transition" if kind == "transition" else "")).get_json()
        e = next(x for x in o["events"] if x["pair_id"] == pid)
        reg = next(x for x in e["regions"] if x["region"] == name)
        return reg["windows"][w]["channel"]

    def run_wire(kind, pid, w, name):
        out = client.post("/api/arc/coupling/%s/run" % gid,
                          json={"pair_id": pid, "kind": kind}).get_json()
        win = next(x for x in out["windows"] if x["window"] == w)
        return win["regions"][name]["channel"]

    try:
        for kind, (pid, w, name, c) in (("state", s_pick),
                                        ("transition", t_pick)):
            ov = overview_wire(kind, pid, w, name)
            check("%s: the overview measures %s on the kept wire CSC %d in %s"
                  % (kind, name, c, w), ov == c, "got CSC %s" % ov)
            t = time.time()
            rw = run_wire(kind, pid, w, name)
            check("  and a real %s run uses it (%.1f s)"
                  % (kind, time.time() - t), rw == c, "got CSC %s" % rw)
        # Negative control: the subtraction dropped.
        coupling.excluded_for = coupling._excluded_union
        try:
            for kind, (pid, w, name, c) in (("state", s_pick),
                                            ("transition", t_pick)):
                ov = overview_wire(kind, pid, w, name)
                rw = run_wire(kind, pid, w, name)
                check("NEGATIVE CONTROL (%s): without the subtraction the "
                      "kept wire is passed over again" % kind,
                      ov != c and rw != c, "overview %s, run %s" % (ov, rw))
        finally:
            coupling.excluded_for = real
    finally:
        A._coupling_entry = real_entry
    return finish()


def finish():
    print("\n%d passed, %d failed" % (RESULTS["ok"], RESULTS["fail"]))
    return 1 if RESULTS["fail"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
