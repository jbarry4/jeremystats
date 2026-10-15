# -*- coding: utf-8 -*-
"""The Confluence's routes, end to end, against a throwaway bank. Offline.

    python tools/test_confluence_routes.py

The app is imported for its routes, and its bank and curation store are
swapped for empty ones in a temp folder before anything is asked of them --
a pool banked here would otherwise be a real entry, synced to everybody.
The activity log and the cloud mirror are stubbed for the same reason.

What is guarded:

  * /api/confluence/recordings lists a recording only when it has BOTH a
    dentate-spike entry and an IED entry, with the pools already made;
  * /plan answers the counts without writing anything, and leaves out what
    was called Garbage;
  * /plan reads an OLDER version when asked, from its snapshot;
  * /merge banks one entry of type `pooled` with origin and pair_t on its
    events and the inputs in its parameters; asked again with the same
    inputs it answers with the one already there (`cached`), and `force`
    makes a second;
  * two entries from different recordings are refused in a sentence;
  * /batch pools several and says, per recording, what happened;
  * a set made from the pool, merged in Panning through the route, and
    undone through the route, ends as it began;
  * Root Canal lists a pooled set (once curated) next to the DS sets, with
    its type.
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
    from backend import app as A                         # noqa: E402
    from backend import curation as C, eventbank as EB   # noqa: E402

    tmp = tempfile.mkdtemp(prefix="jarvis-confluence-routes-")
    saved = (A.BANK, A.CURATE, A.STORE.record_activity, A.mirror_bank_soon,
             A._session_by_gid)
    try:
        A.BANK = EB.EventBank(tmp, A.STORE)
        A.CURATE = C.Curation(tmp, A.STORE)
        A.STORE.record_activity = lambda *a, **k: None
        A.mirror_bank_soon = lambda: None
        # The test recordings are not registered; the routes that ask for
        # one are told about them and nothing else.
        real = saved[4]
        A._session_by_gid = lambda gid: ({"gid": gid, "label": gid + " label"}
                                         if str(gid).startswith("g")
                                         else real(gid))
        cli = A.app.test_client()

        def bank(gid, typ, events, name, pipeline):
            return A.BANK.add({"gid": gid, "type": typ, "name": name,
                               "session_label": gid + " label",
                               "project": "TEST", "mouse": 1, "session": 2,
                               "events": events, "pipeline": pipeline,
                               "added_by": "confluence-test"})

        ds = bank("g1", "ds", [{"start": 1.0, "channel": 12},
                               {"start": 2.0, "label": "Garbage",
                                "label_id": "garbage"},
                               {"start": 3.0}], "DS one", "Incisor")
        ied = bank("g1", "ied", [{"start": 1.003, "channel": 30},
                                 {"start": 5.0}], "IED one",
                   "Doppler (line length)")
        bank("g2", "ds", [{"start": 1.0}], "DS only", "Incisor")
        ds3 = bank("g3", "ds", [{"start": 7.0}], "DS three", "Incisor")
        ied3 = bank("g3", "ied", [{"start": 7.002}], "IED three",
                    "Doppler (line length)")

        print("\nwhich recordings")
        got = cli.get("/api/confluence/recordings").get_json()
        gids = sorted(r["gid"] for r in got["recordings"])
        check("only recordings with both kinds are listed", gids == ["g1", "g3"],
              gids)
        check("with the default window", got.get("window_ms") == 5.0, got)

        print("\nthe plan")
        body = {"gid": "g1", "ds_entry": ds["id"], "ied_entry": ied["id"],
                "window_ms": 5}
        n_before = len(A.BANK.all())
        p = cli.post("/api/confluence/plan", json=body).get_json()
        st = p.get("stats") or {}
        check("it counts without writing",
              p.get("ok") and len(A.BANK.all()) == n_before, p)
        check("Garbage left out, one merged, one each alone",
              st.get("n_ds") == 2 and st.get("ds_left_out") == 1
              and st.get("merged") == 1 and st.get("incisor_only") == 1
              and st.get("doppler_only") == 1 and st.get("n") == 3, st)
        check("the events come back by origin, for the picture",
              [e["o"] for e in p.get("events", [])]
              == ["both", "incisor", "doppler"], p.get("events"))

        # An older version: re-bank the DS entry with one more event, then
        # ask for v0 by its id.
        v0 = A.BANK.get(ds["id"])["versions"][0]
        A.BANK.add(dict(A.BANK.get(ds["id"]),
                        events=A.BANK.get(ds["id"])["events"]
                        + [{"start": 5.001}],
                        pipeline="Incisor", added_by="confluence-test",
                        version_note="one more"))
        now = cli.post("/api/confluence/plan", json=body).get_json()["stats"]
        old = cli.post("/api/confluence/plan",
                       json=dict(body, ds_version=v0["id"])).get_json()
        check("the newest version by default",
              now.get("merged") == 2, now)
        check("an older version when asked, from its snapshot",
              old.get("ok") and old["stats"].get("merged") == 1
              and old["params"]["ds_version"] == "0", old)

        bad = cli.post("/api/confluence/plan",
                       json={"gid": "g1", "ds_entry": ds3["id"],
                             "ied_entry": ied["id"]})
        check("entries from two recordings are refused in a sentence",
              bad.status_code == 400
              and (bad.get_json() or {}).get("error", "").endswith("."),
              bad.get_json())

        print("\nthe merge")
        m = cli.post("/api/confluence/merge", json=body).get_json()
        ent = A.BANK.get((m.get("entry") or {}).get("id"))
        check("one entry of type pooled is banked",
              m.get("ok") and not m.get("cached") and ent
              and ent["type"] == "pooled", m)
        evs = (ent or {}).get("events") or []
        check("its events carry origin and pair_t",
              [e.get("origin") for e in evs] == ["both", "incisor", "both"]
              and evs[0].get("pair_t") == 1.003, evs)
        prm = ((ent or {}).get("source") or {}).get("parameters") or {}
        check("its parameters name the inputs and the window",
              prm.get("ds_entry") == ds["id"] and prm.get("ied_entry")
              == ied["id"] and prm.get("window_ms") == 5.0, prm)
        m2 = cli.post("/api/confluence/merge", json=body).get_json()
        check("the same inputs again answer with the one already there",
              m2.get("cached") and m2["entry"]["id"] == ent["id"], m2)
        m3 = cli.post("/api/confluence/merge",
                      json=dict(body, force=True)).get_json()
        check("force makes a second",
              m3.get("ok") and not m3.get("cached")
              and m3["entry"]["id"] != ent["id"], m3)

        print("\nmany at once")
        b = cli.post("/api/confluence/batch", json={
            "window_ms": 5, "items": [
                {"gid": "g3", "ds_entry": ds3["id"], "ied_entry": ied3["id"]},
                {"gid": "g2", "ds_entry": ds3["id"], "ied_entry": ied["id"]},
            ]}).get_json()
        rows = {r["gid"]: r for r in b.get("rows", [])}
        check("each recording says what happened",
              rows.get("g3", {}).get("ok")
              and (rows["g3"].get("stats") or {}).get("merged") == 1
              and rows.get("g2", {}).get("ok") is False
              and rows["g2"].get("error"), b)

        print("\nPanning through the routes")
        r = cli.post("/api/curation/from-bank", json={
            "gid": "g1", "kind": "pooled", "entry": ent["id"],
            "replace": True, "version": 0}).get_json()
        st_ = cli.get("/api/curation/g1/pooled").get_json().get("set") or {}
        pev = st_.get("events") or []
        check("a set made from the pool carries the origins",
              r.get("ok") is not False
              and [e.get("origin") for e in pev] == ["both", "incisor", "both"],
              pev)
        a_, b_ = pev[1], pev[0]          # the Incisor-only one, and a merged one
        mg = cli.post("/api/curation/g1/pooled/merge",
                      json={"keep": a_["id"], "drop": b_["id"]}).get_json()
        check("merging through the route keeps Incisor's earlier-time one",
              mg.get("ok") and mg.get("event", {}).get("id") in (a_["id"], b_["id"]),
              mg)
        after = cli.get("/api/curation/g1/pooled").get_json()["set"]["events"]
        check("and the set is one shorter", len(after) == len(pev) - 1,
              [e["start"] for e in after])
        survivor = mg["event"]
        gone = next(e for e in (a_, b_) if e["id"] == mg["dropped"])
        before = {k: v for k, v in (a_ if survivor["id"] == a_["id"] else b_)
                  .items() if k in ("origin", "pair_t", "label", "channel")}
        un = cli.post("/api/curation/g1/pooled/unmerge", json={
            "keep": survivor["id"], "before": before,
            "dropped": {k: gone.get(k) for k in ("start", "origin",
                                                 "pair_t", "channel")}
        }).get_json()
        back = cli.get("/api/curation/g1/pooled").get_json()["set"]["events"]
        check("undone through the route, it ends as it began",
              un.get("ok") and sorted(e["start"] for e in back)
              == sorted(e["start"] for e in pev)
              and sorted(str(e.get("origin")) for e in back)
              == sorted(str(e.get("origin")) for e in pev), back)

        print("\nRoot Canal")
        # Curated: label everything a spike and bank the set back.
        for e in back:
            cli.post("/api/curation/g1/pooled/label",
                     json={"event": e["id"], "label": "spike"})
        # Banked straight onto the pool: the route that does this in the
        # app wants a registered recording, which a test gid is not.
        bundle = A.CURATE.bank_one(A.CURATE.get("g1", "pooled"))
        A.BANK.add(dict(A.BANK.get(ent["id"]), events=bundle["events"],
                        by_label=bundle["by_label"],
                        label_names=bundle["label_names"], curated=True,
                        curation_label="*", pipeline="Jarvis curation",
                        added_by="confluence-test"))
        rc = cli.get("/api/rootcanal/candidates?gid=g1").get_json()
        types = {s.get("entry_id"): s.get("type") for s in rc.get("sets", [])}
        check("a curated pooled set is offered beside the DS sets, with "
              "its type", types.get(ent["id"]) == "pooled", rc)
        kept = (A.BANK.get(ent["id"]).get("events") or [])
        check("and banking it from the set kept every origin",
              sorted(str(e.get("origin")) for e in kept)
              == sorted(str(e.get("origin")) for e in pev), kept)
    finally:
        (A.BANK, A.CURATE, A.STORE.record_activity,
         A.mirror_bank_soon, A._session_by_gid) = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s" % ("ALL PASS" if not FAILED else
                    "%d FAILED: %s" % (len(FAILED), "; ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
