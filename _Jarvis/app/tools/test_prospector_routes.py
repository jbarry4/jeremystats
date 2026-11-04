# -*- coding: utf-8 -*-
"""Prospector in Panning, end to end, against a throwaway bank. Offline.

    python tools/test_prospector_routes.py

The app is imported for its routes, and its bank, curation store and
Prospector store are swapped for empty ones in a temp folder before anything
is asked of them -- a sweep accepted here would otherwise bank a real
version, synced to everybody. The activity log and the cloud mirror are
stubbed for the same reason. No recording is read: the sweeps accepted are
made up, which is everything the accept route is given.

What is guarded:

  * the pooled vocabulary holds Prospector's two flags, `computed` (no
    button, no key), `flagged` (the Flagged pass has them), `ai`, and never
    a non-event, so Junction's `usable` keeps them;
  * its three calls fall where the bars put them, and nothing for an event
    that could not be read;
  * a version re-timed before versions carried the mark is read from its
    note, so no reader shifts it twice;
  * the status says why it cannot sweep until a run is chosen, and what the
    chosen bar did once one is;
  * a sweep of anything but a pooled set is refused;
  * accepting puts its calls on the events no person decided -- adopting
    the two flags into a pool made before they existed -- banks every call
    as a Prospector version (tagged, by Prospector (AI), origins kept), and
    files the sweep with every score;
  * training never reads that version as a person's pass;
  * a second sweep replaces Prospector's own calls and never a person's;
  * AI Beta's panel is not offered Prospector's inputs.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:500])
    if not ok:
        FAILED.append(name)


def main():
    import numpy as np
    from backend import app as A                         # noqa: E402
    from backend import confluence as CF                 # noqa: E402
    from backend import curation as C, eventbank as EB   # noqa: E402
    from backend import prospector as P                  # noqa: E402

    print("the vocabulary")
    vocab = {l["id"]: l for l in C.vocabulary("pooled")}
    ai = [vocab.get(k) or {} for k in ("likely_spike", "likely_garbage")]
    check("the pooled kind holds both of Prospector's flags",
          all(a.get("ai") and a.get("computed") and a.get("flagged")
              and not a.get("good") and not a.get("keys") for a in ai), ai)
    kept = CF.usable([{"start": 1.0, "label_id": "likely_garbage"},
                      {"start": 2.0, "label_id": "garbage"},
                      {"start": 3.0, "label_id": "likely_spike"}],
                     C.vocabulary("pooled"))
    check("Junction keeps an event Prospector flagged, drops Garbage",
          [e["start"] for e in kept] == [1.0, 3.0], kept)

    print("\nits calls")
    p = np.array([0.99, 0.979, 0.97, 0.5, 0.49, np.nan, 0.995])
    ok = np.array([True, True, True, True, True, True, False])
    got = list(P._call(p, ok, 0.979, 0.5))
    check("Spike at the bar, the flags under it, nothing unread",
          got == ["spike", "spike", "likely_spike", "likely_spike",
                  "likely_garbage", None, None], got)

    print("\nthe clock")
    ent = {"time_basis": {"kind": "neuralynx_true",
                          "converted_from": "toothy_concat"},
           "versions": [
               {"v": 0, "note": "Imported from ETS"},
               {"v": 1, "note": "Re-timed from toothy_concat to "
                                "neuralynx_true. 185 event(s) moved"},
               {"v": 2, "note": "Gui final curation"}]}
    bank0 = EB.EventBank(tempfile.mkdtemp(prefix="jarvis-pr-clock-"), A.STORE)
    check("a version after a note-only re-time is on the recording's clock",
          P._basis_at(bank0, ent, {"v": 2}) == "neuralynx_true"
          and P._basis_at(bank0, ent, {"v": 0}) == "toothy_concat",
          (P._basis_at(bank0, ent, {"v": 2}), P._basis_at(bank0, ent, {"v": 0})))

    tmp = tempfile.mkdtemp(prefix="jarvis-prospector-routes-")
    saved = (A.BANK, A.CURATE, A.PROSPECTOR, A.STORE.record_activity,
             A.mirror_bank_soon, A._session_by_gid)
    try:
        A.BANK = EB.EventBank(tmp, A.STORE)
        A.CURATE = C.Curation(tmp, A.STORE)
        A.PROSPECTOR = P.Store(tmp, A.STORE)
        A.STORE.record_activity = lambda *a, **k: None
        A.mirror_bank_soon = lambda: None
        real = saved[5]
        A._session_by_gid = lambda gid: ({"gid": gid, "label": gid + " label"}
                                         if str(gid).startswith("g")
                                         else real(gid))
        cli = A.app.test_client()

        print("\nnot chosen yet")
        st = cli.get("/api/prospector").get_json()
        check("it says it cannot sweep, and how to choose one",
              st.get("ready") is False
              and "prospector_train.py" in (st.get("why") or ""), st)

        pool = A.BANK.add({
            "gid": "g1", "type": "pooled", "name": "pool",
            "session_label": "g1 label", "project": "TEST", "mouse": 1,
            "session": 2, "pipeline": "The Confluence: Junction",
            "added_by": "prospector-test",
            "events": [{"start": 1.0, "origin": "both", "pair_t": 1.004},
                       {"start": 2.0, "origin": "incisor"},
                       {"start": 3.0, "origin": "doppler"},
                       {"start": 4.0, "origin": "incisor"}]})
        r = cli.post("/api/curation/from-bank", json={
            "gid": "g1", "kind": "pooled", "entry": pool["id"],
            "replace": True, "version": 0}).get_json()
        sk = r.get("kind") or "pooled"
        # A pool made before the two flags existed: its copied vocabulary
        # has no such labels.
        rec = A.CURATE._read("g1", sk)
        rec["labels"] = [l for l in rec["labels"] if not l.get("ai")]
        A.CURATE._write(rec)
        evs = cli.get("/api/curation/g1/" + sk).get_json()["set"]["events"]
        ids = [e["id"] for e in evs]
        cli.post("/api/curation/g1/" + sk + "/label",
                 json={"event": ids[0], "label": "garbage"})

        print("\nchosen")
        rid = "pr20990101-000000"
        A.PROSPECTOR.save({
            "id": rid, "at": "2099-01-01T00:00:00",
            "data": {"n_recordings": 40, "n_events": 24390},
            "final": {"model": "blend", "families": ["incisor", "origin"],
                      "results": {"pooled": {"auc": 0.94}, "bars": {
                          "0.99": {"spike_called": 8114, "spike_recall": 0.508,
                                   "garbage_into_spike": 57,
                                   "by_origin": {}}}}}},
            model={"model": None, "feature_names": [], "families": []})
        A.PROSPECTOR.set_model(rid, 0.979, 0.99, prov={"user": "test"})
        st = cli.get("/api/prospector").get_json()
        check("ready, with the bar and what it did on recordings it never saw",
              st.get("ready") and st.get("t_spike") == 0.979
              and (st.get("held_out") or {}).get("garbage_into_spike") == 57,
              st)
        bad = cli.post("/api/prospector/sweep",
                       json={"gid": "g1", "kind": "ds"})
        check("a sweep of a dentate spike set is refused in a sentence",
              bad.status_code == 400 and "pooled" in bad.get_json()["error"],
              bad.get_json())

        def made_up(sid, calls):
            P.remember(sid, {
                "gid": "g1", "kind": sk, "run_id": rid,
                "session_label": "g1 label",
                "policy": {"t_spike": 0.979, "t_lean": 0.5, "target": 0.99},
                "counts": {c: sum(1 for x in calls if x == c)
                           for c in P.CALLS + ("unread",)},
                "at": "2099-01-01T00:00:00", "basis": None,
                "rows": [{"id": e["id"], "start": e["start"],
                          "origin": e.get("origin"),
                          "pair_t": e.get("pair_t"),
                          "p": None if c is None else 0.9, "label": c,
                          "readable": c is not None, "human": None,
                          "human_by": None}
                         for e, c in zip(evs, calls)]})

        print("\naccepted")
        made_up("s1", ["likely_garbage", "spike", "likely_spike", None])
        res = cli.post("/api/prospector/sweep/s1/accept", json={}).get_json()
        cur = A.CURATE.get("g1", sk)
        by = {e["id"]: e for e in cur["events"]}
        check("its calls are on the two undecided events it could read",
              res.get("ok") and res.get("applied") == 2
              and by[ids[1]]["label"] == "spike"
              and by[ids[2]]["label"] == "likely_spike"
              and not by[ids[3]].get("label"), res)
        check("by Prospector, and a person's Garbage stays",
              by[ids[1]].get("by") == P.BY and by[ids[0]]["label"] == "garbage"
              and by[ids[0]].get("by") != P.BY, by[ids[0]])
        labs = {l["id"]: l for l in cur["labels"]}
        check("a pool made before the flags now carries the one it uses",
              (labs.get("likely_spike") or {}).get("computed") is True
              and "likely_garbage" not in labs, sorted(labs))
        ent = A.BANK.get(pool["id"])
        top = max(ent["versions"], key=lambda v: v.get("v") or 0)
        check("every call banked as a Prospector version",
              top.get("tag") == P.TAG and top.get("by") == P.BY
              and (top.get("by_label") or {}).get("likely_garbage") == 1
              and (top.get("by_label") or {}).get("unspecified") == 1, top)
        # A version's snapshot is start and label (eventbank.SNAP_FIELDS);
        # where each came from is on the entry's events, as for every pool.
        vev = ent.get("events") or []
        check("its events keep where they came from",
              [e.get("origin") for e in sorted(vev, key=lambda e: e["start"])]
              == ["both", "incisor", "doppler", "incisor"], vev)
        check("training never reads it as a person's pass",
              P._is_ai(top) and not P._is_pass(top))
        filed = A.PROSPECTOR.sweeps.read("s1") or {}
        check("the sweep is filed with every score, the AI's first calls",
              len(filed.get("rows") or []) == 4 and filed.get("applied") == 2,
              filed)

        print("\nswept again")
        cli.post("/api/curation/g1/" + sk + "/label",
                 json={"event": ids[2], "label": "garbage"})
        made_up("s2", ["spike", "likely_garbage", "spike", "likely_spike"])
        res2 = cli.post("/api/prospector/sweep/s2/accept", json={}).get_json()
        by = {e["id"]: e for e in A.CURATE.get("g1", sk)["events"]}
        check("its own calls are replaced, a person's never",
              res2.get("ok") and by[ids[1]]["label"] == "likely_garbage"
              and by[ids[3]]["label"] == "likely_spike"
              and by[ids[0]]["label"] == "garbage"
              and by[ids[2]]["label"] == "garbage", by)

        print("\nAI Beta")
        state = cli.get("/api/aibeta/state").get_json()
        fam_ids = {f.get("id") for f in state.get("families") or []}
        check("its panel is not offered Prospector's inputs",
              "origin" not in fam_ids and not any(
                  str(f).startswith("spec") for f in fam_ids), sorted(fam_ids))
    finally:
        (A.BANK, A.CURATE, A.PROSPECTOR, A.STORE.record_activity,
         A.mirror_bank_soon, A._session_by_gid) = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s" % ("all passed" if not FAILED else "%d FAILED: %s"
                    % (len(FAILED), FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
