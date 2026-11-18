# -*- coding: utf-8 -*-
"""Working sets are bank-identity based. Offline, against a throwaway bank.

    python tools/test_set_identity.py

The user's ruling (2026-10-20): "The working sets should be clearly distinct
in the work bench... no overlap of recording, purely bank identity based.
Make sure bank identity and recording identities don't override each other."
Before it, a set was one per (recording, kind): two Doppler runs on one
recording shared one set, so starting from the second replaced the first,
and one run's decisions sat on the bench while another run's versions were
being chosen -- which is how flags appeared to carry across M3S2's versions.

A NEW set belongs to one bank entry, and its kind says which:
`<kind>.e<entry id>`. The sets made before stay `ds`/`ied`/`pooled` until
restarted (the user chose new sets only).

What is guarded:

  * two entries of one kind on one recording give two sets, neither
    replacing the other, each named for its entry;
  * a decision in one set is not in the other;
  * banking a set writes a version of ITS entry and of no other;
  * starting the same entry again is refused (409), naming its set's kind;
  * the startable list leaves out the entries a set stands for, keeps the
    rest, and never offers to replace anything;
  * an older set (one per recording and kind) is used for the entry it was
    started from, rather than doubled;
  * an older set on the same recording never banks onto, or adopts, an
    entry a per-entry set stands for;
  * the banked-history route, the categories route and the for-recording
    route answer for a per-entry set.
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
    print("  %-72s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:600])
    if not ok:
        FAILED.append(name)


def main():
    from backend import app as A                         # noqa: E402
    from backend import curation as C, eventbank as EB   # noqa: E402

    tmp = tempfile.mkdtemp(prefix="jarvis-set-identity-")
    saved = (A.BANK, A.CURATE, A.STORE.record_activity, A.mirror_bank_soon,
             A._session_by_gid)
    try:
        A.BANK = EB.EventBank(tmp, A.STORE)
        A.CURATE = C.Curation(tmp, A.STORE)
        A.STORE.record_activity = lambda *a, **k: None
        A.mirror_bank_soon = lambda: None
        real = saved[4]
        A._session_by_gid = lambda gid: (
            {"gid": gid, "label": gid + " label", "project": "TEST",
             "mouse": 3, "session": 2}
            if str(gid).startswith("g") else real(gid))
        cli = A.app.test_client()

        def bank(gid, typ, starts, name, pipeline):
            return A.BANK.add({"gid": gid, "type": typ, "name": name,
                               "session_label": gid + " label",
                               "project": "TEST", "mouse": 3, "session": 2,
                               "events": [{"start": s} for s in starts],
                               "pipeline": pipeline,
                               "added_by": "set-identity-test"})

        def start(gid, kind, entry, version=0, **extra):
            body = dict({"gid": gid, "kind": kind, "entry": entry,
                         "version": version}, **extra)
            r = cli.post("/api/curation/from-bank", json=body)
            return r.status_code, (r.get_json() or {})

        a = bank("g1", "ied", [1.0, 2.0, 3.0], "Doppler run A",
                 "Doppler (line length)")
        b = bank("g1", "ied", [1.0, 2.5, 4.0, 5.0], "Doppler run B",
                 "Doppler (line length)")
        c = bank("g1", "ied", [9.0], "Doppler run C", "Doppler (line length)")

        # -- two entries, two sets ------------------------------------------
        sa, ja = start("g1", "ied", a["id"])
        sb, jb = start("g1", "ied", b["id"])
        ka, kb = ja.get("kind"), jb.get("kind")
        check("entry A starts a set of its own (ied.e<A>)",
              sa == 200 and ka == C.set_kind("ied", a["id"]), (sa, ja))
        check("entry B starts another, and does not replace A's",
              sb == 200 and kb == C.set_kind("ied", b["id"])
              and A.CURATE.get("g1", ka) is not None, (sb, jb))
        check("the two sets hold their own entries' candidates",
              len(A.CURATE.get("g1", ka)["events"]) == 3
              and len(A.CURATE.get("g1", kb)["events"]) == 4)
        check("each set knows its entry (summary `entry`, `kind_base`)",
              A.CURATE.summary(A.CURATE.get("g1", ka)).get("entry") == a["id"]
              and A.CURATE.summary(A.CURATE.get("g1", kb)).get("kind_base")
              == "ied")

        # -- a decision stays in its set ------------------------------------
        ev = A.CURATE.get("g1", ka)["events"][0]
        r = cli.post("/api/curation/g1/%s/label" % ka,
                     json={"event": ev["id"], "label": "solid"})
        check("a decision is made in set A", r.status_code == 200, r.get_json())
        lab_b = [e.get("label") for e in A.CURATE.get("g1", kb)["events"]]
        check("set B carries none of A's decisions", not any(lab_b), lab_b)

        # -- banking writes its own entry and no other ----------------------
        b_before = A.BANK.get(b["id"]).get("version")
        c_before = A.BANK.get(c["id"]).get("version")
        r = cli.post("/api/curation/g1/%s/bank" % ka, json={"note": "test"})
        j = r.get_json() or {}
        check("banking set A answers", r.status_code == 200 and j.get("ok"), j)
        ea = A.BANK.get(a["id"])
        check("set A banked into entry A, as its next version",
              (j.get("entry") or {}).get("id", a["id"]) == a["id"]
              and len(ea.get("versions") or []) >= 2, j)
        check("entry B and entry C did not move",
              A.BANK.get(b["id"]).get("version") == b_before
              and A.BANK.get(c["id"]).get("version") == c_before)
        ids = {e["id"] for e in A.BANK.all() if e.get("gid") == "g1"}
        check("no new entry was made for the set", ids == {a["id"], b["id"],
                                                            c["id"]}, ids)

        # -- starting the same entry again ----------------------------------
        s2, j2 = start("g1", "ied", a["id"])
        check("starting entry A again is refused (409) and names its set",
              s2 == 409 and j2.get("kind") == ka, (s2, j2))

        # -- the startable list ---------------------------------------------
        r = cli.get("/api/curation/startable?kind=ied")
        got = r.get_json() or {}
        offered = {e["id"] for e in got.get("entries") or []}
        check("startable leaves out A and B (they have sets), keeps C",
              c["id"] in offered and a["id"] not in offered
              and b["id"] not in offered, offered)
        row_c = next((e for e in got.get("entries") or []
                      if e["id"] == c["id"]), {})
        check("startable never offers to replace a set (set_name None)",
              row_c.get("set_name") is None, row_c)
        check("startable names the other sets on the recording",
              len(row_c.get("on_recording") or []) == 2, row_c)
        r = cli.get("/api/curation/startable?kind=" + ka)
        check("startable answers when asked with a per-entry kind",
              r.status_code == 200, r.get_json())

        # -- an older set ---------------------------------------------------
        d = bank("g2", "ied", [1.0, 2.0], "Older run D",
                 "Doppler (line length)")
        rec, _n, _x = A.CURATE.create(
            "g2", "ied", [{"start": 1.0}, {"start": 2.0}],
            source={"bank_entry": d["id"], "from": "bank"},
            session_label="g2 label")
        s3, j3 = start("g2", "ied", d["id"])
        check("the older set is THE set of the entry it came from (409, ied)",
              s3 == 409 and j3.get("kind") == "ied", (s3, j3))

        # An older set on g1 too, from entry C; it banks, and must not land
        # on entry A (which now carries the "*" a per-entry set writes).
        A.CURATE.create("g1", "ied", [{"start": 9.0}],
                        source={"bank_entry": c["id"], "from": "bank"},
                        session_label="g1 label")
        old = A.CURATE.get("g1", "ied")
        A.CURATE.label("g1", "ied", old["events"][0]["id"], "solid")
        a_vers = len(A.BANK.get(a["id"]).get("versions") or [])
        r = cli.post("/api/curation/g1/ied/bank", json={"note": "older"})
        j = r.get_json() or {}
        check("the older set on g1 banks", r.status_code == 200, j)
        check("...and not onto entry A, which a per-entry set stands for",
              len(A.BANK.get(a["id"]).get("versions") or []) == a_vers
              and (j.get("entry") or {}).get("id") != a["id"], j)

        # -- the other routes ----------------------------------------------
        r = cli.get("/api/curation/g1/%s/banked" % ka)
        j = r.get_json() or {}
        check("banked history of set A is entry A's",
              r.status_code == 200 and (j.get("entry") or {}).get("id")
              == a["id"], j)
        r = cli.get("/api/curation/categories/" + ka)
        j = r.get_json() or {}
        check("categories answer for a per-entry kind",
              r.status_code == 200 and any(l.get("id") == "solid"
                                           for l in j.get("labels") or []), j)
        r = cli.get("/api/curation/for-recording/g1")
        j = r.get_json() or {}
        kinds = sorted(s.get("kind") for s in j.get("existing") or [])
        check("for-recording lists every set on the recording",
              ka in kinds and kb in kinds and "ied" in kinds, kinds)
        r = cli.get("/api/curation/g1/%s" % kb)
        check("a per-entry set is read by its kind",
              r.status_code == 200 and (r.get_json() or {}).get("ok"))
    finally:
        (A.BANK, A.CURATE, A.STORE.record_activity, A.mirror_bank_soon,
         A._session_by_gid) = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d FAILED" % len(FAILED))
        for f in FAILED:
            print("  - " + f)
        return 1
    print("all ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
