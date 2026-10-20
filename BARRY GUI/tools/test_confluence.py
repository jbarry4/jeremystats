# -*- coding: utf-8 -*-
"""The Confluence: pooling Incisor's and Doppler's events. Offline.

    python tools/test_confluence.py

Run against throwaway stores in a temp folder -- never the lab's: a bank
entry or a curation set made here would sync to everybody.

What is guarded:

  * the pool is one to one, nearest first: a burst of three IEDs near one
    dentate spike merges the nearest and leaves the other two as Doppler's;
  * a merged event keeps Incisor's time and holds Doppler's as `pair_t`;
  * the window is inclusive of its edge and nothing past it pairs;
  * the counts add up: merged + Incisor only = Incisor's total, and the
    same for Doppler;
  * what was called Garbage, in either vocabulary, stays out; undecided and
    flagged go in;
  * a window of 0 or over 100 ms is refused in a sentence;
  * the bank keeps `origin` and `pair_t` on every event, and refuses an
    origin it does not know;
  * a curation set made from a pool carries the origins;
  * Panning's merge keeps the candidate with Incisor's time whichever was
    clicked first, so no stamp moves; the decision carries over when the
    survivor had none; the origins join to "both"; the other is gone; and
    banking the set afterwards carries origin and pair_t;
  * merging a candidate with itself, or one that is not there, is refused.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import confluence as CF  # noqa: E402
from backend import curation as C  # noqa: E402
from backend import eventbank as EB  # noqa: E402
from backend import store as storemod  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


def pooling():
    print("\npooling")
    ds = [{"start": 10.000, "channel": 12, "amplitude": 900},
          {"start": 20.000},
          {"start": 30.000}]
    ied = [{"start": 10.004}, {"start": 10.001}, {"start": 10.003},
           {"start": 20.005}, {"start": 30.0051}, {"start": 50.0}]
    ied.sort(key=lambda e: e["start"])
    out, st = CF.pool(ds, ied, CF.window_s(5))
    by_t = {round(e["start"], 4): e for e in out}
    first = by_t.get(10.0) or {}
    check("the nearest IED merges with the dentate spike",
          first.get("origin") == "both"
          and abs(first.get("pair_t", 0) - 10.001) < 1e-9, first)
    check("and the dentate spike's time is the one kept",
          first.get("start") == 10.0 and first.get("channel") == 12, first)
    check("the other two of the burst stay Doppler's own",
          by_t.get(10.003, {}).get("origin") == "doppler"
          and by_t.get(10.004, {}).get("origin") == "doppler",
          sorted(by_t))
    check("5 ms exactly is inside the window",
          by_t.get(20.0, {}).get("origin") == "both", by_t.get(20.0))
    check("5.1 ms is outside it",
          by_t.get(30.0, {}).get("origin") == "incisor"
          and by_t.get(30.0051, {}).get("origin") == "doppler",
          (by_t.get(30.0), by_t.get(30.0051)))
    check("the counts add up",
          st["merged"] + st["incisor_only"] == st["n_ds"] == 3
          and st["merged"] + st["doppler_only"] == st["n_ied"] == 6
          and st["n"] == len(out) == 3 + 6 - st["merged"], st)
    check("the gaps are reported in ms",
          st["dt_ms"] == [1.0, 5.0], st["dt_ms"])
    check("the pool comes out in time order",
          [e["start"] for e in out] == sorted(e["start"] for e in out))

    print("\nkeeping Doppler's time instead")
    dout, dst = CF.pool(ds, [dict(e, channel=40) if e["start"] == 10.001
                             else e for e in ied], CF.window_s(5), "doppler")
    d_by = {round(e["start"], 4): e for e in dout}
    m = d_by.get(10.001) or {}
    check("the same pairs merge, filed under Doppler's stamp",
          m.get("origin") == "both" and m.get("pair_t") == 10.0
          and m.get("stamp") == "doppler" and 10.0 not in d_by, m)
    check("with Doppler's channel, and Incisor's amplitude where it has none",
          m.get("channel") == 40 and m.get("amplitude") == 900, m)
    check("the gap is still Doppler's time less Incisor's",
          m.get("dt_ms") == 1.0 and dst["dt_ms"] == st["dt_ms"], m)
    check("and the counts do not change",
          all(dst[k] == st[k] for k in ("merged", "incisor_only",
                                        "doppler_only", "n"))
          and dst["keep"] == "doppler" and st["keep"] == "incisor", dst)
    check("the default keeps Incisor's and writes no stamp",
          "stamp" not in first, first)
    try:
        CF.keep_of("both")
        got = None
    except ValueError as e:
        got = str(e)
    check("keeping anybody else's time is refused in a sentence",
          bool(got) and got.endswith("."), got)

    print("\nwhat goes in")
    vocab_ds = C.vocabulary("ds")
    vocab_ied = C.vocabulary("ied")
    garbage_ds = [l for l in vocab_ds
                  if not l.get("good") and not l.get("flagged")]
    check("the DS vocabulary has a non-event to leave out", bool(garbage_ds),
          [l["id"] for l in vocab_ds])
    evs = [{"start": 1, "label_id": "garbage"},
           {"start": 2, "label": "Garbage"},
           {"start": 3, "label_id": "flag"},
           {"start": 4},
           {"start": 5, "label_id": "solid"},
           {"start": "nonsense"}]
    kept = [e["start"] for e in CF.usable(evs, vocab_ied)]
    check("Garbage stays out, by id or by name; flagged, undecided and "
          "decided go in", kept == [3.0, 4.0, 5.0], kept)

    print("\nthe window")
    for bad in (0, -1, 101):
        try:
            CF.window_s(bad)
            got = None
        except ValueError as e:
            got = str(e)
        check("a window of %s ms is refused in a sentence" % bad,
              bool(got) and got.endswith("."), got)
    check("a missing window is the 5 ms default",
          CF.window_s(None) == 0.005)


def banking(tmp):
    print("\nthe bank")
    where = os.path.join(tmp, "bank")
    os.makedirs(where, exist_ok=True)
    bank = EB.EventBank(where, storemod.Store(where))
    out, _st = CF.pool([{"start": 1.0}, {"start": 2.0}],
                       [{"start": 1.002}, {"start": 3.0}], CF.window_s(5))
    events = [{k: e[k] for k in ("start", "origin", "pair_t") if k in e}
              for e in out]
    events.append({"start": 4.0, "origin": "somebody else"})
    events.append({"start": 6.002, "origin": "both", "pair_t": 6.0,
                   "stamp": "doppler"})
    events.append({"start": 7.0, "origin": "both", "pair_t": 7.001,
                   "stamp": "nobody"})
    ent = bank.add({"gid": "g-test", "type": "pooled", "name": "pool",
                    "events": events,
                    "pipeline": "The Confluence: Junction (test)",
                    "added_by": "confluence-test"})
    got = {e["start"]: e for e in ent["events"]}
    check("origin and pair_t are kept on the way in",
          got[1.0].get("origin") == "both" and got[1.0].get("pair_t") == 1.002
          and got[2.0].get("origin") == "incisor"
          and got[3.0].get("origin") == "doppler", ent["events"])
    check("an origin it does not know is dropped, not stored",
          "origin" not in got[4.0], got[4.0])
    check("whose stamp a merged event is filed under is kept",
          got[6.002].get("stamp") == "doppler", got[6.002])
    check("and a stamp it does not know is dropped",
          "stamp" not in got[7.0], got[7.0])
    return events


def panning(tmp):
    print("\nPanning's merge")
    where = os.path.join(tmp, "curation")
    os.makedirs(where, exist_ok=True)
    store = storemod.Store(where)
    me = (store.provenance() or {}).get("user")
    cur = C.Curation(where, store)
    rec, _n, _rep = cur.create("g-pan", "pooled", [
        {"start": 5.0000, "origin": "doppler"},
        {"start": 5.0030, "origin": "incisor", "channel": 7},
        {"start": 9.0000, "origin": "doppler"},
        {"start": 9.0040, "origin": "doppler"},
        {"start": 12.0, "origin": "both", "pair_t": 12.001},
    ], name="test pool")
    check("a set made from a pool carries the origins",
          [e.get("origin") for e in rec["events"]]
          == ["doppler", "incisor", "doppler", "doppler", "both"],
          [e.get("origin") for e in rec["events"]])
    ids = {round(e["start"], 4): e["id"] for e in rec["events"]}
    # Decide the Doppler one first, then merge clicking IT first: the
    # survivor must still be Incisor's.
    cur.label("g-pan", "pooled", ids[5.0], "spike")
    ev, _prog, gone = cur.merge_events("g-pan", "pooled", ids[5.0],
                                       ids[5.003])
    check("the survivor is the one with Incisor's time, whichever was "
          "clicked first",
          ev["id"] == ids[5.003] and gone == ids[5.0], (ev, gone))
    check("its time did not move",
          ev["start"] == 5.003 and ev.get("pair_t") == 5.0, ev)
    check("it took the other's decision, having none of its own",
          ev.get("label") == "spike", ev.get("label"))
    check("the origins joined to both", ev.get("origin") == "both",
          ev.get("origin"))
    check("and it says who merged it and when",
          ev.get("merged_by") == me and bool(me)
          and bool(ev.get("merged_at")), ev)
    after = cur.get("g-pan", "pooled")
    check("the other candidate is gone",
          ids[5.0] not in [e["id"] for e in after["events"]]
          and len(after["events"]) == 4, [e["id"] for e in after["events"]])

    print("\nundoing a merge")
    back_ev, restored, _p = cur.unmerge("g-pan", "pooled", ids[5.003],
                                        {"origin": "incisor", "channel": 7},
                                        {"start": 5.0, "origin": "doppler",
                                         "label": "spike"})
    after = cur.get("g-pan", "pooled")
    starts = sorted(round(e["start"], 4) for e in after["events"])
    check("the other candidate is back, at its own time",
          5.0 in starts and len(after["events"]) == 5, starts)
    check("under a new id, since the old one was removed",
          restored["id"] != ids[5.0] and restored.get("label") == "spike",
          restored)
    check("the survivor is as it was: its own origin, no pair, no merge "
          "stamp, undecided",
          back_ev.get("origin") == "incisor" and "pair_t" not in back_ev
          and "merged_by" not in back_ev and not back_ev.get("label"),
          back_ev)
    try:
        cur.unmerge("g-pan", "pooled", "nope", {}, {"start": 1.0})
        got = None
    except C.CurationError as e:
        got = str(e)
    check("undoing on a candidate that is not there is refused", bool(got),
          got)
    # Merged again, so the rest of the checks see the set they expect.
    ids[5.0] = restored["id"]
    cur.merge_events("g-pan", "pooled", ids[5.0], ids[5.003])

    ev2, _p, gone2 = cur.merge_events("g-pan", "pooled", ids[9.004],
                                      ids[9.0])
    check("two of Doppler's keep the earlier time",
          ev2["id"] == ids[9.0] and ev2["start"] == 9.0
          and ev2.get("pair_t") == 9.004 and ev2.get("origin") == "doppler",
          ev2)

    for name, a, b in (("itself", ids[12.0], ids[12.0]),
                       ("one that is not there", ids[12.0], "nope")):
        try:
            cur.merge_events("g-pan", "pooled", a, b)
            got = None
        except C.CurationError as e:
            got = str(e)
        check("merging with %s is refused" % name, bool(got), got)

    print("\nmerging to Doppler's time")
    rec2, _n, _rep = cur.create("g-pan2", "pooled", [
        {"start": 3.0000, "origin": "incisor", "channel": 7},
        {"start": 3.0020, "origin": "doppler", "channel": 30},
        {"start": 6.0000, "origin": "incisor"},
        {"start": 6.0010, "origin": "incisor"},
        {"start": 8.0, "origin": "both", "pair_t": 8.003, "stamp": "doppler"},
    ], name="test pool 2")
    i2 = {round(e["start"], 4): e["id"] for e in rec2["events"]}
    check("a set carries whose stamp a merged event is under",
          next(e for e in rec2["events"] if e["id"] == i2[8.0])
          .get("stamp") == "doppler", rec2["events"])
    dv, _p, dgone = cur.merge_events("g-pan2", "pooled", i2[3.0], i2[3.002],
                                     stamp="doppler")
    check("the survivor is the one with Doppler's time, whichever was "
          "clicked first",
          dv["id"] == i2[3.002] and dgone == i2[3.0]
          and dv["start"] == 3.002 and dv.get("pair_t") == 3.0, dv)
    check("and it says Doppler's is the stamp it is filed under",
          dv.get("origin") == "both" and dv.get("stamp") == "doppler", dv)
    try:
        cur.merge_events("g-pan2", "pooled", i2[6.0], i2[6.001],
                         stamp="doppler")
        got = None
    except C.CurationError as e:
        got = str(e)
    check("two of Incisor's cannot be merged to Doppler's time", bool(got),
          got)
    dv2, _p, _g = cur.merge_events("g-pan2", "pooled", i2[6.0], i2[8.0],
                                   stamp="doppler")
    check("a merged event already under Doppler's stamp stays the survivor",
          dv2["id"] == i2[8.0] and dv2["start"] == 8.0
          and dv2.get("stamp") == "doppler", dv2)
    back2, _r, _p = cur.unmerge("g-pan2", "pooled", i2[3.002],
                                {"origin": "doppler", "channel": 30},
                                {"start": 3.0, "origin": "incisor",
                                 "channel": 7})
    check("undoing it takes the stamp off again",
          back2.get("origin") == "doppler" and "stamp" not in back2
          and "pair_t" not in back2, back2)
    try:
        cur.merge_events("g-pan2", "pooled", i2[6.0], i2[6.001],
                         stamp="somebody")
        got = None
    except C.CurationError as e:
        got = str(e)
    check("a stamp that is neither detector's is refused", bool(got), got)
    b2 = cur.bank_one(cur.get("g-pan2", "pooled"), only_specified=False)
    check("banking the set carries the stamp",
          any(e.get("stamp") == "doppler" and round(e["start"], 4) == 8.0
              for e in b2["events"]), b2["events"])

    cur.label("g-pan", "pooled", ids[12.0], "garbage")
    banked = cur.bank_one(cur.get("g-pan", "pooled"), only_specified=False)
    by = {round(e["start"], 4): e for e in banked["events"]}
    check("banking the set carries origin and pair_t",
          by[5.003].get("origin") == "both" and by[5.003].get("pair_t") == 5.0
          and by[12.0].get("origin") == "both"
          and by[12.0].get("label_id") == "garbage", banked["events"])


def main():
    tmp = tempfile.mkdtemp(prefix="jarvis-confluence-")
    try:
        pooling()
        banking(tmp)
        panning(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%s" % ("ALL PASS" if not FAILED else
                    "%d FAILED: %s" % (len(FAILED), "; ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
