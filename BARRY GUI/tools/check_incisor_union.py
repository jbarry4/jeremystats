# -*- coding: utf-8 -*-
"""check_incisor_union.py -- Extract all, checked against every saved scan.

No server and no reading: every Incisor scan this machine has kept is on
disk under GUI_logs/.cache/incisor, with every channel's candidates in it,
so the union can be checked against real detections by arithmetic alone.

    python tools/check_incisor_union.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import incisor                                  # noqa: E402

OK = FAIL = 0


def ck(what, cond, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  ok   " + what)
    else:
        FAIL += 1
        print("  FAIL " + what + ("   [%s]" % detail if detail else ""))


def head(t):
    print("\n" + t + "\n" + "-" * 66)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                    # noqa: BLE001
        pass
    files = sorted(glob.glob(os.path.join(APP, "GUI_logs", ".cache",
                                          "incisor", "*.json")))
    scans = []
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                                # noqa: BLE001
            continue
        if (d.get("_rows") or {}) and d.get("chosen") is not None:
            scans.append((os.path.basename(f), d))
    head("SAVED SCANS")
    ck("there are saved scans to check against", len(scans) > 0,
       "%d files, none with rows" % len(files))
    if not scans:
        return 1
    print("  %d scans with every channel's candidates" % len(scans))

    head("A SCAN RECALLED FROM DISK STILL HAS ITS EVENTS")
    # The bug this fixes: JSON makes every key a string, and every reader
    # looked channels up by integer, so a recalled scan had no events on
    # any channel. Checked on the files exactly as they sit on disk.
    missing = []
    for name, d in scans:
        want = d.get("n")
        got = len(incisor.events_for(d, d["chosen"]))
        if want and got != want:
            missing.append("%s: %s of %s" % (name[:24], got, want))
    ck("events_for finds the chosen channel's candidates on every scan",
       not missing, "; ".join(missing[:3]))
    ck("by integer and by string key alike",
       all(len(incisor.events_for(d, d["chosen"]))
           == len(incisor.events_for(d, str(d["chosen"])))
           for _n, d in scans[:20]))

    head("THE UNION, ON EVERY SCAN")
    bad_sum, bad_dup, bad_bound, bad_rep, bad_hil = [], [], [], [], []
    for name, d in scans:
        rows = {int(k): v for k, v in d["_rows"].items()}
        chans = {c["index"]: c for c in (d.get("channels") or [])}
        order = [i for i in sorted(rows) if not (chans.get(i) or {}).get("bad")]
        hil = d["chosen"]
        if hil not in order:
            continue
        k = order.index(hil)
        pool = order[max(0, k - 3):k + 4]
        evs, s = incisor.union(d, pool, hilus=hil)
        per = [len(rows.get(i) or []) for i in pool]
        # Every hilus event is in exactly one group (the window is under the
        # detector's spacing, so a group holds at most one per channel), so
        # the union is the hilus's own count plus what it missed.
        if s["n"] != s["n_hilus"] + s["only_off_hilus"]:
            bad_hil.append(name[:24])
        if not (max(per) <= s["n"] <= sum(per)):
            bad_bound.append("%s: %d not in [%d, %d]"
                             % (name[:24], s["n"], max(per), sum(per)))
        t = [e["start"] for e in evs]
        if len(set(round(x, 6) for x in t)) != len(t) or t != sorted(t):
            bad_dup.append(name[:24])
        if sum(s["by_seen_on"].values()) != s["n"]:
            bad_sum.append(name[:24])
        # The time kept is the detection where the spike was LARGEST.
        byt = {}
        for i in pool:
            for e in rows.get(i) or []:
                byt.setdefault(round(float(e["start"]), 6), []).append(
                    (abs(float(e.get("amp") or 0)), i))
        for e in evs[:50]:
            here = byt.get(round(float(e["start"]), 6)) or []
            num = (chans.get(e["index"]) or {}).get("number")
            if not any(i == e["index"] for _a, i in here) or (
                    e.get("channel") is not None and num is not None
                    and int(e["channel"]) != int(num)):
                bad_rep.append(name[:24])
                break
    ck("the union is the hilus's count plus what the hilus alone missed",
       not bad_hil, ", ".join(bad_hil[:3]))
    ck("never fewer than the busiest channel, never more than the sum",
       not bad_bound, "; ".join(bad_bound[:3]))
    ck("every spike once: no two banked times the same, and in order",
       not bad_dup, ", ".join(bad_dup[:3]))
    ck("the seen-on counts add up to the union",
       not bad_sum, ", ".join(bad_sum[:3]))
    ck("each kept time is a real detection, on the channel it names",
       not bad_rep, ", ".join(bad_rep[:3]))

    head("THE LARGEST DETECTION WINS")
    fake = {"_rows": {
        1: [{"start": 10.000, "amp": 400.0}],
        2: [{"start": 10.001, "amp": 900.0}],
        3: [{"start": 10.002, "amp": 500.0}, {"start": 20.0, "amp": 350.0}],
    }}
    evs, s = incisor.union(fake, [1, 2, 3], hilus=1)
    ck("three channels one millisecond apart are one spike, plus a second",
       s["n"] == 2, s)
    ck("and it keeps the time and channel where it was largest",
       abs(evs[0]["start"] - 10.001) < 1e-9 and evs[0]["index"] == 2,
       evs[0])
    ck("it says how many channels saw each",
       [e["seen_on"] for e in evs] == [3, 1], [e["seen_on"] for e in evs])
    ck("and that the hilus alone missed the second",
       s["only_off_hilus"] == 1, s)
    # Anchored, not chained: 0, 20, 40, 60 ms at a 25 ms window is three
    # groups under anchoring and ONE under chaining -- a chain would let a
    # run of events creep along the recording and merge.
    chain = {"_rows": {i: [{"start": 5.0 + 0.020 * i, "amp": 300.0}]
                       for i in range(4)}}
    _e, s2 = incisor.union(chain, [0, 1, 2, 3], tol_ms=25)
    ck("the window is anchored on each group's first event, not chained",
       s2["n"] == 2, s2["n"])

    head("REFUSALS SAY WHY")
    for kw, what in (({"tol_ms": 0}, "a zero window"),
                     ({"tol_ms": 150}, "a window wider than the detector's "
                                       "own 100 ms spacing")):
        try:
            incisor.union(fake, [1, 2], **kw)
            ck("%s is refused" % what, False, "accepted")
        except ValueError as exc:
            ck("%s is refused with a sentence" % what, len(str(exc)) > 40,
               str(exc))
    try:
        incisor.union(fake, [])
        ck("an empty pool is refused", False, "accepted")
    except ValueError:
        ck("an empty pool is refused", True)

    print("\n  %d ok, %d fail" % (OK, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
