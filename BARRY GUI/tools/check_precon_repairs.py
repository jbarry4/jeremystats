# -*- coding: utf-8 -*-
"""Checks for what the first real Precon1 -> Precon4 run (2026-09-30) found.

    python tools\\check_precon_repairs.py

1. The bank kept an entry's FIRST parameters for ever (`_source_for`), so
   Spark's transition re-bank never said it had measured anything, and
   Circuit refused all 80 runs. Now the SAME pipeline filing again brings
   its parameters; a different pipeline, or an adopted import, still does
   not overwrite the source. On a temp bank.
2. `here[0]` read an FP recording for r10 Precon1 and Precon4: the registry
   files a day's FP1, SPC and FP2 under one gid. `cued_folder` picks the
   SPC. Against the real registry rows, with the here[0] they have.
3. The circuit cache was keyed on the bank version alone, which a new
   clipping measurement does not move. Now the pair's wires are in the
   key (rest epochs keep theirs: filled at run time from their own check).
4. One recording's route error stopped the whole Spark stage; now it fails
   that recording and the stage goes on. A reading that is not the banked
   pairs is refused, and a re-bank the bank did not keep stops the stage
   at once. Against a fake Jarvis.
5. The run died replacing progress.json while Jarvis read it (Windows
   will not replace an open file). `replace_patiently` waits for the
   reader. Against a real open handle.

Each with a CONTROL that the check can tell the bug from the fix.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond or detail == "" else "  " + str(detail)[:300]))


class Store(object):
    def provenance(self):
        return {"user": "check", "machine": "check"}

    def _stage(self, path):
        pass                             # no git here


def bank_checks(tmp):
    print("1. the bank, filing an entry again")
    from backend import eventbank as EB
    B = EB.EventBank(tmp, Store())
    evs = [{"start": 10.0, "label": "Click_LowTone"},
           {"start": 30.0, "label": "Click_LowTone"}]
    base = {"id": "chkrefile0001", "gid": "harness-refile", "type": "ttl",
            "name": "refile check", "events": evs, "added_by": "check",
            "pipeline": "The Arc: Spark", "detector": "spark.pair_events",
            "parameters": {"clip_measured": True}}
    B.add(dict(base))
    B.add(dict(base, events=[dict(e, clipped={"onset": [3]}) for e in evs],
               parameters={"clip_measured": True,
                           "transition_measured": True,
                           "transition_before_s": 1.0}))
    got = B.get("chkrefile0001")
    p = (got.get("source") or {}).get("parameters") or {}
    check("the same pipeline filing again brings its parameters",
          p.get("transition_measured") is True
          and p.get("transition_before_s") == 1.0, p)
    check("  and the events it filed", all(
        e.get("clipped") == {"onset": [3]} for e in got.get("events")))
    check("  and the source is otherwise the one it had",
          got["source"].get("pipeline") == "The Arc: Spark"
          and got["source"].get("detector") == "spark.pair_events")
    B.add(dict(base, pipeline="Jarvis curation",
               parameters={"curated_by": "someone"}))
    got = B.get("chkrefile0001")
    check("another pipeline (curation) does not overwrite the source",
          got["source"].get("pipeline") == "The Arc: Spark"
          and got["source"]["parameters"].get("transition_measured") is True,
          got["source"])
    # CONTROL: the rule before -- the first source, for ever.
    real = EB._source_for

    def old_rule(entry, prior, pipeline):
        came = entry.get("import_from") or {}
        for g in (came.get("source"), (prior or {}).get("source")):
            if g:
                return g
        return real(entry, None, pipeline)
    EB._source_for = old_rule
    try:
        B.add(dict(base, id="chkrefile0002"))
        B.add(dict(base, id="chkrefile0002",
                   parameters={"transition_measured": True}))
        old = (B.get("chkrefile0002").get("source") or {}).get(
            "parameters") or {}
    finally:
        EB._source_for = real
    check("CONTROL: under the old rule the parameters stay the first ones",
          old.get("transition_measured") is None, old)


def folder_checks():
    print("2. which folder holds the cue pairs")
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from backend import app as A, circuitrun as CR, ids
    for gid, what in (("s0c6efa477a94", "r10 Precon1"),
                      ("s5e2c6d208fc7", "r10 Precon4")):
        rec = A.REG.by_gid(gid)
        if not rec:
            check("%s is in the registry" % what, False)
            continue
        sm = A.REG.summary(rec)
        here = sm.get("here") or []
        if not here:
            print("  (skipped %s: not reachable from this machine)" % what)
            continue
        first = (ids.identify(here[0]) or {}).get("run")
        got = CR.cued_folder(sm)
        check("%s: without its bank entry, the SPC folder (%s)"
              % (what, os.path.basename(os.path.dirname(got))),
              (ids.identify(got) or {}).get("run") == "SPC", got)
        ent = A._coupling_entry(gid)
        got2 = CR.cued_folder(sm, ent)
        check("%s: with it, the folder its pairs were banked from" % what,
              ent and os.path.normcase(got2) ==
              os.path.normcase(ent.get("session_path")), got2)
        check("CONTROL: %s's here[0] is the %s, which is the bug"
              % (what, first), first != "SPC", first)
        lab = CR.session_label(sm, got)
        check("%s: named by its folder (%s), not the row (%s)"
              % (what, lab, sm.get("label")),
              lab and " SPC " in lab, lab)
    one = {"here": ["X:\\a"], "mouse": None}
    check("a row whose folders say nothing falls back to here[0]",
          CR.cued_folder(one) == "X:\\a")
    check("and a row with no folder here is None", CR.cued_folder({}) is None)


def cache_checks():
    print("3. the circuit cache knows the wires")
    from backend import circuitrun as CR
    prep = {"gid": "g", "kind": "state", "phash": "h", "bank_version": 1,
            "pairs": [{"pair_id": 1, "drop": {"cue1": [3]}},
                      {"pair_id": 2, "drop": {"cue1": [3, 5]}}]}
    k1 = CR._pair_key(prep, 1)
    k1b = CR._pair_key(dict(prep, pairs=[{"pair_id": 1,
                                          "drop": {"cue1": [3, 9]}}]), 1)
    check("the same version with other wires is another cache entry",
          k1 != k1b and k1[:4] == k1b[:4], (k1, k1b))
    check("the same wires, the same entry",
          CR._pair_key(prep, 1) == CR._pair_key(dict(prep), 1))
    row = {"pair_id": 1, "drop": {"cue1": [3]}}
    seen = []
    real = CR.cache_has
    CR.cache_has = lambda *a: seen.append(a) or False
    try:
        CR._mark_cached(row, "g", "state", "h", 1, None)
    finally:
        CR.cache_has = real
    check("the plan's 'cached' asks under the same key the run uses",
          seen and seen[0][4] == k1[4], (seen, k1))
    rest = dict(prep, kind="rest")
    check("a rest epoch keeps the version-only key",
          CR._pair_key(rest, 1)[4] == 1)
    check("CONTROL: under the old key the wires made no difference",
          (prep["gid"], 1, "state", "h", 1) ==
          ("g", 1, "state", "h", prep["bank_version"]) and k1[4] != 1)


class FakeApi(object):
    """Enough of Jarvis for run_spark: four recordings."""

    def __init__(self, keeps=True):
        self.keeps = keeps
        self.n = 0
        self.entries = {}
        for g in ("g1", "g2", "g3", "g4"):
            self.entries["e" + g] = {
                "id": "e" + g, "version": 1, "name": "n",
                "events": [{"start": 10.0, "label": "A"},
                           {"start": 30.0, "label": "A"}],
                "source": {"parameters": {"clip_measured": True}}}

    def same_boot(self):
        return None

    def get(self, path, **kw):
        import run_precon_drift as R
        self.n += 1
        if path.startswith("/api/bank/"):
            return {"entry": json.loads(json.dumps(
                self.entries[path.rsplit("/", 1)[1]]))}
        if path.startswith("/api/arc/spark/"):
            gid = path.rsplit("/", 1)[1]
            if gid == "g2":
                raise R.ApiError(409, "There are no cue pairs here to check.")
            pairs = [{"pair_id": 1, "opener_t": 10.0},
                     {"pair_id": 2, "opener_t": 30.0}]
            if gid == "g3":
                pairs = pairs[:1]              # another recording
            return {"pairs": pairs, "path": "X:\\" + gid}
        if path == "/api/arc/circuit/recordings":
            return {"rows": [{"gid": g, "transition_measured": True}
                             for g in ("g1", "g4")]}
        raise R.ApiError(404, "no route " + path)

    def post(self, path, body=None, write=True, **kw):
        self.n += 1
        gid = path.split("/")[4]
        if path.endswith("/clipping"):
            return {"by_pair": {"1": {"5": {"windows": ["cue1"]}}},
                    "transition": {"measured": True, "by_pair": {
                        "2": {"7": {"windows": ["onset"]}}}},
                    "read": {"seconds": 0.1}}
        if path.endswith("/bank"):
            e = self.entries["e" + gid]
            if self.keeps or gid != "g4":
                e["source"]["parameters"].update({
                    "transition_measured": True, "transition_before_s": 1.0,
                    "transition_after_s": 2.0})
            return {"entry": {"id": e["id"], "version": 1}, "n": 2}
        raise AssertionError(path)


def spark_checks(tmp):
    print("4. the Spark stage, one recording at a time")
    import run_precon_drift as R
    plan = [{"gid": g, "rat": 1, "day": 1, "state": "todo",
             "entry": "e" + g, "hand": 0} for g in ("g1", "g2", "g3", "g4")]
    real_prog = R.PROG
    R.PROG = R.Progress(None)
    try:
        log = R.RunLog(os.path.join(tmp, "spark.runlog.json"))
        api = FakeApi(keeps=True)
        bad = R.run_spark(api, plan, log)
        st = {g: log["spark"][g]["status"] for g in log["spark"]}
        check("a route error fails that recording, and the stage goes on",
              st.get("g2") == "failed" and st.get("g4") == "banked",
              st)
        check("  it says the route's own words",
              "no cue pairs" in log["spark"]["g2"]["why"])
        check("a reading that is not the banked pairs is refused, not "
              "re-banked", st.get("g3") == "failed"
              and "not the banked cue pairs" in log["spark"]["g3"]["why"],
              log["spark"].get("g3"))
        check("the ones that were fine are banked, with both answers",
              st.get("g1") == "banked"
              and log["spark"]["g1"]["blocks_state"] == 1
              and log["spark"]["g1"]["blocks_transition"] == 1,
              log["spark"].get("g1"))
        log2 = R.RunLog(os.path.join(tmp, "spark2.runlog.json"))
        api2 = FakeApi(keeps=False)
        try:
            R.run_spark(api2, plan, log2)
            stopped = None
        except R.Refused as exc:
            stopped = str(exc)
        check("a re-bank the bank did not keep stops the stage at once",
              stopped and "does not say its transition windows were "
              "measured" in stopped
              and log2["spark"]["g4"]["status"] == "not_kept", stopped)
    finally:
        R.PROG = real_prog


def replace_checks(tmp):
    print("5. replacing a file somebody is reading")
    import run_precon_drift as R
    path = os.path.join(tmp, "progress.json")
    R.write_json(path, {"n": 1})
    fh = open(path, "r", encoding="utf-8")        # Jarvis, reading
    tmpf = path + ".x.tmp"
    with open(tmpf, "w", encoding="utf-8") as out:
        out.write('{"n": 2}')
    try:
        os.replace(tmpf, path)
        control = "replaced"                        # (not Windows)
    except PermissionError:
        control = "refused"
    if control == "refused":
        check("CONTROL: a plain os.replace over an open file is refused "
              "(Windows)", True)
        threading.Timer(0.4, fh.close).start()
        t0 = time.time()
        R.write_json(path, {"n": 3})
        took = time.time() - t0
        check("replace_patiently waits for the reader, then writes "
              "(%.2f s)" % took, json.load(open(path, encoding="utf-8"))
              == {"n": 3} and 0.3 < took < 3.0, took)
    else:
        fh.close()
        print("  (this system replaces open files; nothing to wait for)")
    if os.path.exists(tmpf):
        os.remove(tmpf)
    for f in os.listdir(tmp):
        if f.startswith("progress.json.") and f.endswith(".tmp"):
            os.remove(os.path.join(tmp, f))
    g = R.Progress(os.path.join(tmp, "no", "such", "dir", "p.json"))
    real = R.write_json
    R.write_json = lambda *a: (_ for _ in ()).throw(
        PermissionError("held"))
    try:
        g.stage("circuits", 2)
        g.item(1, "x")
        ok = True
    except Exception:                                # noqa: BLE001
        ok = False
    finally:
        R.write_json = real
    check("a progress write that fails does not end the run", ok)


def main():
    tmp = tempfile.mkdtemp(prefix="check_precon_repairs_")
    try:
        bank_checks(tmp)
        folder_checks()
        cache_checks()
        spark_checks(tmp)
        replace_checks(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
