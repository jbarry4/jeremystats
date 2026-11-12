# -*- coding: utf-8 -*-
"""Keep the Spark stage's work from the 2026-09-30 Precon run.

    python tools\\repair_precon_spark.py            # dry run: say, change nothing
    python tools\\repair_precon_spark.py --apply    # back up, then repair

What happened. The first real run of tools/run_precon_drift.py re-banked
12 of the 16 recordings: one read each (about 35 s), the transition windows'
clipping measured at -1 s / +2 s, and filed onto every event. But the bank
kept each entry's FIRST `source` -- parameters and all -- whenever an entry
was filed again (eventbank `_source_for`), so the entries went on saying
`transition_measured` was never looked at, and Circuit refused every run.
That is fixed; this keeps the seven minutes of measuring instead of redoing
them.

For each recording the run log says was banked, the entry is repaired only
if it demonstrably holds THAT run's measurement: the same number of cue
pairs the run filed, and exactly the state and transition blocks the run
log says it excluded, window by window counted from the events themselves.
Then its parameters are given what the Spark route would have written
(`transition_measured`, the lengths, the 50 ms rule), through the bank's own
`add()` with the events unchanged -- no new version, since the pairs and
their times did not change. Anything that does not match is left alone and
said. Refused while a run is going.

Every shard it touches is copied first to
GUI_logs/.cache/bank_repair_backup_<stamp>/ (git-ignored).
"""
import glob
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

RUNLOG = os.path.join(APP, "docs", "dewey-precon-drift.runlog.json")
BANK_DIR = os.path.join(APP, "GUI_logs", "event_bank")


def blocks(events, windows):
    """The same count the run log made (`_blocks`), from the events."""
    return sum(len(chans or []) for ev in events
               for w, chans in ((ev.get("excluded") or {}).items()
                                if isinstance(ev.get("excluded"), dict)
                                else [])
               if w in windows)


def ident(events):
    return [(round(float(e.get("start")), 6), e.get("label"))
            for e in events or []]


def main():
    apply = "--apply" in sys.argv
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    import run_precon_drift as R
    from backend import app as A, spark as S

    last = json.load(open(A.PRECON.last_path, encoding="utf-8")) \
        if os.path.exists(A.PRECON.last_path) else {}
    if A.PRECON.status()["busy"]:
        print("A Precon run or plan is going; try again when it has ended.")
        return 2
    log = json.load(open(RUNLOG, encoding="utf-8"))
    todo, skip = [], []
    for gid, rec in sorted((log.get("spark") or {}).items()):
        tag = "%s (entry %s)" % (gid, rec.get("entry"))
        if rec.get("status") != "banked":
            skip.append((tag, "the run did not bank it (%s: %s)"
                         % (rec.get("status"), rec.get("why"))))
            continue
        ent = A.BANK.get(rec["entry"]) or {}
        src = ent.get("source") or {}
        if not ent:
            skip.append((tag, "no such bank entry"))
            continue
        if R.transition_done(ent):
            skip.append((tag, "already says its transition windows were "
                              "measured"))
            continue
        if src.get("pipeline") != A.SPARK_PIPELINE:
            skip.append((tag, "not a Spark entry (%r)" % src.get("pipeline")))
            continue
        evs = ent.get("events") or []
        got = {"pairs": len(evs),
               "state": blocks(evs, R.STATE_WINDOWS),
               "transition": blocks(evs, R.TRANSITION_WINDOWS)}
        want = {"pairs": rec.get("n_pairs"),
                "state": rec.get("blocks_state"),
                "transition": rec.get("blocks_transition")}
        if got != want:
            skip.append((tag, "its events are not what the run filed "
                              "(entry %s, run log %s)" % (got, want)))
            continue
        todo.append((gid, rec, ent, got))

    print("run log: %s" % RUNLOG)
    print("%d entr%s hold the run's measurement and lack its parameters:"
          % (len(todo), "y" if len(todo) == 1 else "ies"))
    for gid, rec, ent, got in todo:
        print("  %s %-44s %2d pairs, %4d state + %4d transition blocks"
              % (gid, ent.get("session_label") or "", got["pairs"],
                 got["state"], got["transition"]))
    for tag, why in skip:
        print("  left: %s: %s" % (tag, why))
    if not apply:
        print("\ndry run: nothing changed. Run with --apply to repair.")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(APP, "GUI_logs", ".cache",
                          "bank_repair_backup_" + stamp)
    os.makedirs(backup, exist_ok=True)
    for _g, rec, _e, _got in todo:
        for f in glob.glob(os.path.join(BANK_DIR, "*_%s@*.json"
                                        % rec["entry"])):
            shutil.copy2(f, backup)
    print("\nbacked up to %s" % backup)

    fixed, failed = 0, []
    for gid, rec, ent, got in todo:
        src = ent.get("source") or {}
        params = dict(src.get("parameters") or {})
        params.update({
            "clip_measured": True, "state_measured": True,
            "transition_measured": True,
            "transition_before_s": R.BEFORE_S,
            "transition_after_s": R.AFTER_S,
            "transition_lost_ms": S.TRANSITION_LOST_MS,
        })
        added = ent.get("added") or {}
        body = {k: ent.get(k) for k in (
            "id", "gid", "project", "mouse", "session", "session_key",
            "session_loose_key", "session_label", "session_path",
            "recording_start", "duration_s", "type", "type_name", "name",
            "note", "curation_label", "time_basis")}
        body.update({"events": ent.get("events"),
                     "pipeline": src.get("pipeline"),
                     "source_file": src.get("file"),
                     "parameters": params,
                     "detector": src.get("detector"),
                     "added_by": added.get("by"),
                     "curated": bool(ent.get("specified"))})
        n_versions = len(ent.get("versions") or [])
        try:
            A.BANK.add(body)
        except Exception as exc:                          # noqa: BLE001
            failed.append((gid, str(exc)))
            continue
        after = A.BANK.get(rec["entry"]) or {}
        ok = (R.transition_done(after)
              and ident(after.get("events")) == ident(ent.get("events"))
              and blocks(after.get("events") or [], R.TRANSITION_WINDOWS)
              == got["transition"]
              and len(after.get("versions") or []) == n_versions
              and (after.get("source") or {}).get("pipeline")
              == src.get("pipeline"))
        if ok:
            fixed += 1
            log["spark"][gid]["repaired"] = {
                "at": R.now(), "why": "the bank kept the entry's first "
                "parameters; given the ones this run measured "
                "(tools/repair_precon_spark.py)"}
        else:
            failed.append((gid, "the re-read does not match; restore from "
                                "%s" % backup))
    if fixed:
        log.setdefault("events", []).append({
            "at": R.now(), "stage": "spark",
            "msg": "repaired %d entr%s: transition_measured given from this "
                   "run's own measurement" % (fixed,
                                              "y" if fixed == 1 else "ies")})
        R.write_json(RUNLOG, log)
    print("repaired %d, failed %d" % (fixed, len(failed)))
    for gid, why in failed:
        print("  FAILED %s: %s" % (gid, why))
    # What Circuit now reads -- the only check that matters.
    C = A.app.test_client()
    rows = {r["gid"]: r for r in C.get(
        "/api/arc/circuit/recordings").get_json()["rows"]}
    ready = [g for g, _r, _e, _x in todo
             if (rows.get(g) or {}).get("transition_measured")]
    print("Circuit now reads a transition measurement for %d of the %d"
          % (len(ready), len(todo)))
    return 1 if failed or len(ready) != len(todo) else 0


if __name__ == "__main__":
    sys.exit(main())
