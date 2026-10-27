# -*- coding: utf-8 -*-
"""Doppler banks a run as it lands; Spotter and Panning say what is banked.
Offline, against a throwaway bank and curation store.

    python tools/test_storm_bank.py

The app is imported for its routes and helpers, and its bank and curation
store are swapped for empty ones in a temp folder first -- an entry banked
here would otherwise be real and synced to everybody. The activity log, the
cloud mirror and the registry lookup are stubbed for the same reason.

What is guarded:

  * a run that lands is banked once, as its own IED entry: the detector's
    list, the dialog's name, the note saying how it was made, `run_key` in
    its parameters; landing again files nothing new; a run with no events
    files nothing;
  * /api/curation/startable lists every entry of the kind a set could be
    started from, and not the entry a set was started from nor the one it
    banks into; one whose every version is archived is sent flagged
    `archived`, after the rest, for the list's archived toggle; an entry on
    a recording that has a set says which;
  * the Data Bank names an archived entry's files `ARCHIVED - ...`, and its
    index says archived and carries the note;
  * a Doppler run made before the gap fix on a recording the health check
    found in pieces is kept and marked, and is not an answer; a cached full
    run older than the run on record under its key is not read back;
  * a set's banked state: none before it is banked; "banked vN" after; and
    "changed" once a decision moves away from what that version holds, or
    once two events are merged after it.
"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if not ok and detail is not None:
        print("      " + str(detail)[:500])
    if not ok:
        FAILED.append(name)


def main():
    from backend import app as A                         # noqa: E402
    from backend import curation as C, eventbank as EB   # noqa: E402

    tmp = tempfile.mkdtemp(prefix="jarvis-storm-bank-")
    saved = (A.BANK, A.CURATE, A.STORE.record_activity, A.mirror_bank_soon,
             A._session_by_gid)
    try:
        A.BANK = EB.EventBank(tmp, A.STORE)
        A.CURATE = C.Curation(tmp, A.STORE)
        A.STORE.record_activity = lambda *a, **k: None
        A.mirror_bank_soon = lambda: None
        A._session_by_gid = lambda gid: {
            "gid": gid, "label": "TEST m1 s2 " + gid, "project": "TEST",
            "mouse": 1, "session": 2, "duration_s": 100.0, "here": []}
        cli = A.app.test_client()

        print("\nDoppler banks a run as it lands")
        params = {"method": "storm", "detector": "Storm line length",
                  "band": [20.0, 300.0], "notch_hz": 60.0, "llw_s": 0.015,
                  "prc": 99.9, "channels": [2, 4], "read_channels": [1, 2, 3, 4],
                  "car": True, "detect_on": "even", "min_channels": 1,
                  "fs_work": 2000.0, "excluded": [], "left_out": []}
        out = {"ok": True, "n": 2, "params": params, "events": [
            {"start": 1.5, "end": 1.6, "peak_uv": 300.0, "peak_channel": 2},
            {"start": 7.25, "end": 7.3, "peak_uv": 410.0, "peak_channel": 4}]}
        got = A._doppler_autobank("gA", "key-one", out)
        ent = A.BANK.get((got or {}).get("id"))
        check("it is banked as its own IED entry", ent is not None
              and ent["type"] == "ied" and ent["n"] == 2
              and got.get("auto") is True, got)
        prm = ((ent or {}).get("source") or {}).get("parameters") or {}
        check("carrying the run's key, so it can be found again",
              prm.get("run_key") == "key-one", prm.get("run_key"))
        check("named the way the dialog would have named it",
              (ent or {}).get("name") == "TEST m1 s2 gA  ·  Doppler 20–300 Hz",
              (ent or {}).get("name"))
        check("with the note saying how it was made",
              "Band-passed 20–300 Hz" in ((ent or {}).get("note") or "")
              and "Detected on" in ((ent or {}).get("note") or ""),
              (ent or {}).get("note"))
        check("the peak channel and amplitude ride on each event",
              [(e.get("channel"), e.get("amplitude")) for e in ent["events"]]
              == [(2, 300.0), (4, 410.0)], ent["events"])
        again = A._doppler_autobank("gA", "key-one", out)
        check("landing again files nothing new",
              again and again["id"] == got["id"] and again["auto"] is False
              and len([r for r in A.BANK.all() if r.get("gid") == "gA"]) == 1,
              again)
        check("it is found by the run's key",
              (A._doppler_banked_for("gA", "key-one") or {}).get("id") == got["id"])
        check("a run with no events files nothing",
              A._doppler_autobank("gB", "key-two", dict(out, events=[])) is None
              and not [r for r in A.BANK.all() if r.get("gid") == "gB"])

        print("\nwhat could be started")
        other = A.BANK.add({"gid": "gA", "type": "ied", "name": "older run",
                            "events": [{"start": 3.0}],
                            "pipeline": "Doppler (line length)",
                            "added_by": "test"})
        imp = A.BANK.add({"gid": "gC", "type": "ied", "name": "hand sort",
                          "events": [{"start": 4.0}],
                          "pipeline": "IED hand-sort (ETS)",
                          "added_by": "test"})
        # A set started from the landed run.
        A.CURATE.create("gA", "ied", [{"start": 1.5}, {"start": 7.25}],
                        name="the set",
                        source={"kind": "bank version",
                                "bank_entry": got["id"], "version": 0})
        st = cli.get("/api/curation/startable?kind=ied").get_json()
        ids = {e["id"]: e for e in st.get("entries", [])}
        check("the entry the set was started from is not offered again",
              got["id"] not in ids, sorted(ids))
        # Since 2026-10-20 a set belongs to one bank entry, so starting the
        # other run makes a set of its own and replaces nothing: no
        # `set_name` to warn about, and the set already there is named in
        # `on_recording`.
        check("another run on that recording is, replacing nothing",
              other["id"] in ids and ids[other["id"]].get("set_name") is None
              and ids[other["id"]].get("on_recording") == ["the set"],
              ids.get(other["id"]))
        check("so is an import on a recording with no set, with its pipeline",
              imp["id"] in ids and ids[imp["id"]].get("set_name") is None
              and ids[imp["id"]].get("pipeline") == "IED hand-sort (ETS)",
              ids.get(imp["id"]))
        bad = cli.get("/api/curation/startable?kind=nonsense")
        check("a kind it does not know is refused", bad.status_code == 400)
        put = A.BANK.add({"gid": "gD", "type": "ied", "name": "put away",
                          "events": [{"start": 5.0}],
                          "pipeline": "Doppler (line length)",
                          "added_by": "test"})
        for v in (A.BANK.get(put["id"]).get("versions") or []):
            A.BANK.edit_version(put["id"], A.BANK.version_key(v),
                                {"archived": True})
        st = cli.get("/api/curation/startable?kind=ied").get_json()
        got = st.get("entries", [])
        check("an entry with every version archived is still sent, flagged, "
              "last, and counted",
              got and got[-1]["id"] == put["id"] and got[-1]["archived"] is True
              and not any(e["archived"] for e in got[:-1])
              and st.get("archived") == 1,
              [(e["id"], e["archived"]) for e in got])
        check("the bank's own listing carries the same flag",
              next(r for r in A.BANK.summaries()
                   if r["id"] == put["id"]).get("archived") is True
              and next(r for r in A.BANK.summaries()
                       if r["id"] == other["id"]).get("archived") is False)

        print("\nthe Data Bank says what is archived")
        from backend import bankmirror as BM            # noqa: E402
        A.BANK.update(put["id"], {"note": "made from a run before the fix"})
        made = BM.BankMirror(tmp, A.BANK).rebuild()
        root = made["root"]
        names = [n for _d, _s, fs in os.walk(root) for n in fs]
        check("an archived entry's files say so in their name",
              "ARCHIVED - ied - put away.csv" in names
              and "ARCHIVED - ied - put away.json" in names
              and "ied - put away.csv" not in names, sorted(names))
        check("a current entry's do not",
              "ied - older run.csv" in names, sorted(names))
        import csv as _csv                               # noqa: E402
        with open(os.path.join(root, "_index.csv"), encoding="utf-8") as fh:
            rows = {r["entry_id"]: r for r in _csv.DictReader(fh)}
        check("the index says archived, and the note says why",
              rows[put["id"]]["archived"] == "yes"
              and rows[put["id"]]["note"] == "made from a run before the fix"
              and rows[other["id"]]["archived"] == "no", rows.get(put["id"]))

        print("\nwhether a set's work is in the bank")
        row = lambda: next(s for s in cli.get("/api/curation").get_json()["sets"]
                           if s["gid"] == "gA" and s["kind"] == "ied")
        check("before it is banked: nothing", row().get("banked") is None,
              row().get("banked"))
        rec = A.CURATE.get("gA", "ied")
        e0, e1 = rec["events"]
        A.CURATE.label("gA", "ied", e0["id"], "solid")
        b = cli.post("/api/curation/gA/ied/bank", json={"note": "test"})
        check("the bank route banks it", b.status_code == 200, b.get_json())
        bk = row().get("banked") or {}
        check("after: banked, as the newest version, unchanged",
              bk.get("version") is not None and bk.get("changed") is False, bk)
        A.CURATE.label("gA", "ied", e1["id"], "garbage")
        check("a decision since: changed",
              (row().get("banked") or {}).get("changed") is True,
              row().get("banked"))
        b = cli.post("/api/curation/gA/ied/bank", json={"note": "again"})
        check("banked again: unchanged once more",
              (row().get("banked") or {}).get("changed") is False,
              row().get("banked"))
        time.sleep(1.2)
        A.CURATE.merge_events("gA", "ied", e0["id"], e1["id"])
        check("a merge since, with every count the same or not: changed",
              (row().get("banked") or {}).get("changed") is True,
              row().get("banked"))
        one = cli.get("/api/curation/gA/ied").get_json()
        check("one set's own answer carries the same",
              (one.get("banked") or {}).get("changed") is True, one.get("banked"))
        print("\na Doppler run from before the gap fix")
        from backend import toolresults as TR, healthlog as HL  # noqa: E402
        saved2 = (A.DOPPLER_VAULT, A.HEALTHLOG)
        try:
            A.DOPPLER_VAULT = TR.ToolResults(tmp, "doppler", None)
            A.HEALTHLOG = HL.HealthLog(tmp, None)
            A.HEALTHLOG.record("gP", None, {"ok": True, "n_segments": 3,
                                            "gaps": [{}, {}]})
            A.HEALTHLOG.record("gS", None, {"ok": True, "n_segments": 1})
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

            def filed(gid, key, ver, rh):
                rec = {"gid": gid, "params_hash": key, "request_hash": rh,
                       "n_events": 3, "computed": {"app_version": ver,
                                                   "at": now}}
                A.DOPPLER_VAULT.put(rec)
                return A.DOPPLER_VAULT.get(gid, key)

            old = filed("gP", "kOld", "2026.10.15.1", "rOld")
            new = filed("gP", "kNew", "2026.10.20.1", "rNew")
            one = filed("gS", "kOne", "2026.10.15.1", "rOne")
            unk = filed("gU", "kUnk", "2026.10.15.1", "rUnk")
            check("an old run on a recording in pieces is before the fix",
                  A._doppler_before_fix(old) is True)
            check("a run since the fix, an old run on one segment, and one "
                  "on a recording nobody checked are not",
                  not A._doppler_before_fix(new)
                  and not A._doppler_before_fix(one)
                  and not A._doppler_before_fix(unk))
            check("so the old one is not an answer, and the others are",
                  A._doppler_answered("gP", "rOld") is None
                  and A._doppler_answered("gP", "rNew") == "kNew"
                  and A._doppler_answered("gS", "rOne") == "kOne")
            rv = {r["key"]: r for r in
                  cli.get("/api/doppler/reviews").get_json()["reviews"]}
            check("the landed list keeps it, and says so",
                  rv.get("kOld", {}).get("before_fix") is True
                  and rv.get("kNew", {}).get("before_fix") is False,
                  {k: v.get("before_fix") for k, v in rv.items()})

            path = A.DOPPLER_VAULT.cached_path("gS", "kOne", ".json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"n": 3, "events": []}')
            check("a cached run as new as its record is read back",
                  (A._doppler_recall({"gid": "gS"}, "kOne") or {}).get("n")
                  == 3)
            two_days = time.time() - 2 * 86400
            os.utime(path, (two_days, two_days))
            check("one older than the run on record under its key is not",
                  A._doppler_recall({"gid": "gS"}, "kOne") is None)
        finally:
            A.DOPPLER_VAULT, A.HEALTHLOG = saved2
    finally:
        (A.BANK, A.CURATE, A.STORE.record_activity, A.mirror_bank_soon,
         A._session_by_gid) = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s" % ("ALL PASS" if not FAILED else
                    "%d FAILED: %s" % (len(FAILED), "; ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
