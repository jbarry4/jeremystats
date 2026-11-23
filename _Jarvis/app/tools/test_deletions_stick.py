# -*- coding: utf-8 -*-
"""What was deleted stays deleted. Offline, in a temp folder.

    python tools/test_deletions_stick.py

On 2026-10-20 thirteen deleted Doppler runs came back in one git merge:
deleting erased the shards this clone had, and the merge brought back the
ones other machines still had. So:

  * a tombstone's stamp reads the way every machine writes it (-0400,
    -04:00, Z), and a stamp it cannot read removes nothing;
  * a note outlives only what was made before it -- a curation set started
    again on the same recording after a deletion shares the deleted set's id
    and must survive;
  * the sync's pull erases a local copy of an entry or set the cloud says
    was deleted (made before the deletion) and notes it, already said, so a
    later merge is refused too; a later set with the same id stays;
  * the app's sweep erases anything a note covers that a merge brought
    back, and nothing else;
  * a set started again after a deletion keeps syncing its decisions, and
    survives beside the deleted set's old shard (the merged record carries
    the old shard's `created`, so shards are judged one by one);
  * the push dates deleted_at by the note, not by the push;
  * deleting in Jarvis writes the note -- but not from a test's client, a
    harness server or for a harness's own seed;
  * the harness runner leaves a swept record deleted.

The app is imported for its sweep, with its bank, curation store and
tombstones swapped for temp ones first, and its activity log stubbed.
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
    if not ok and detail is not None:
        print("      " + str(detail)[:500])
    if not ok:
        FAILED.append(name)


def main():
    from backend import tombs as T, eventbank as EB, curation as C
    from backend import cloudsync as CS

    print("\nstamps")
    check("-0400, -04:00 and Z read as the same moment",
          T.when("2026-10-20T11:10:47-0400")
          == T.when("2026-10-20T11:10:47-04:00")
          == T.when("2026-10-20T15:10:47Z"))
    check("a stamp with no zone, or none at all, is not read",
          T.when("2026-10-20T11:10:47") is None and T.when("") is None
          and T.when(None) is None)
    check("newer says no when either side cannot be read",
          T.newer("2026-10-20T11:00:00-0400", "2026-10-19T11:00:00-0400")
          and not T.newer("2026-10-20T11:00:00-0400", None)
          and not T.newer(None, "2026-10-19T11:00:00-0400"))

    tmp = tempfile.mkdtemp(prefix="jarvis-deletions-")
    try:
        bank = EB.EventBank(tmp, None)
        cur = C.Curation(tmp, None)
        tombs = T.Tombs(tmp, None)

        print("\nthe sync's pull")
        old = bank.add({"gid": "gA", "type": "ied", "name": "pre-fix run",
                        "events": [{"start": 1.0}], "added_by": "test",
                        "pipeline": "Doppler (line length)"})
        keep = bank.add({"gid": "gA", "type": "ied", "name": "a live run",
                         "events": [{"start": 2.0}], "added_by": "test",
                         "pipeline": "Doppler (line length)"})
        cur.create("gA", "pooled", [{"start": 1.0}], name="old set",
                   source={"kind": "bank version", "bank_entry": old["id"]})
        sync = CS.Sync.__new__(CS.Sync)
        sync.bank, sync.curate, sync.tombs = bank, cur, tombs
        far = "2099-01-01T00:00:00+00:00"
        long_ago = "2000-01-01T00:00:00+00:00"
        n = sync._apply_bank([{"id": old["id"], "deleted_at": far},
                              {"id": keep["id"], "deleted_at": long_ago}])
        check("an entry the cloud deleted after it was made is erased here",
              bank.get(old["id"]) is None and n == 1, n)
        check("one the cloud row says was deleted before it was made stays",
              bank.get(keep["id"]) is not None)
        row = (tombs._rec().get("gone") or {}).get("bank:" + old["id"]) or {}
        check("and the deletion is noted here, already said, at its time",
              row.get("synced") is True and row.get("at") == far, row)

        ev = cur.get("gA", "pooled")["events"][0]
        n = sync._apply_curation(
            [{"id": "gA__pooled", "gid": "gA", "kind": "pooled",
              "deleted_at": long_ago}],
            [{"set_id": "gA__pooled", "event_id": ev["id"], "label": "spike",
              "decided_by": "someone", "decided_at": "2099-01-01T00:00:00+00:00"}])
        check("a set made after the cloud's deletion stays, and still takes "
              "decisions (the row keeps deleted_at for ever)",
              cur.get("gA", "pooled") is not None
              and cur.get("gA", "pooled")["events"][0].get("label") == "spike",
              cur.get("gA", "pooled")["events"][0])
        n = sync._apply_curation(
            [{"id": "gA__pooled", "gid": "gA", "kind": "pooled",
              "deleted_at": far}], [])
        check("a set made before it is erased, and noted",
              cur.get("gA", "pooled") is None and n == 1
              and tombs.is_deleted("curation", "gA__pooled"), n)

        print("\nthe push dates a deletion by when it happened")
        sent = []

        class FakeCloud:
            def patch_rows(self, table, query, values):
                sent.append((table, query, dict(values)))
                return [{}]
        sync.cloud = FakeCloud()
        tombs.add("bank", "eLate", note="test", at="2026-10-20T11:10:47-0400")
        sync.push_deletions()
        got = [v for t, q, v in sent if q.endswith("eLate")]
        check("deleted_at is the note's time, not the push's",
              got and got[0].get("deleted_at") == "2026-10-20T15:10:47+00:00"
              and got[0].get("updated_at") != got[0].get("deleted_at"), got)

        print("\na deleted set's old shard beside a set started again")
        import json as _json                             # noqa: E402
        cur2 = C.Curation(tmp, None)
        new = cur2.create("gS", "ied", [{"start": 5.0}], name="started again")
        cur2.label("gS", "ied", cur2.get("gS", "ied")["events"][0]["id"],
                   "solid")
        mine = cur2.book.shard_files(cur2.base("gS", "ied"))[0][1]
        stale = _json.load(open(mine, encoding="utf-8"))
        # Another machine's copy of the set that was deleted: made before
        # the note, nothing imported into it since -- and, merged, its
        # `created` wins (FIRST).
        old_at = "2026-10-15T10:00:00-04:00"
        stale["created"] = {"at": old_at, "user": "someone"}
        stale["imports"] = [{"at": "2026-10-15T10:00:00-0400", "n": 1}]
        for k in (stale.get("_at") or {}):
            stale["_at"][k] = "2026-10-15T14:00:00.000000+00:00"
        other = mine.replace("@" + mine.rsplit("@", 1)[1],
                             "@barrylab-d8e8.json")
        _json.dump(stale, open(other, "w", encoding="utf-8"))
        merged = cur2.get("gS", "ied")
        check("(the merged set does carry the old shard's created)",
              (merged.get("created") or {}).get("at") == old_at,
              merged.get("created"))
        gone = cur2.delete_made_before("gS", "ied", "2026-10-20T13:57:59-0400")
        left = [os.path.basename(p) for _m, p in
                cur2.book.shard_files(cur2.base("gS", "ied"))]
        check("only the old shard goes; the set started again stays, "
              "with its decision",
              gone == 1 and left == [os.path.basename(mine)]
              and cur2.get("gS", "ied")["events"][0].get("label") == "solid",
              (gone, left))

        print("\nthe app's sweep")
        from backend import app as A                     # noqa: E402
        saved = (A.BANK, A.CURATE, A.RESULTS.tombs, A.STORE.record_activity,
                 A.mirror_bank_soon)
        try:
            A.BANK, A.CURATE = bank, cur
            A.RESULTS.tombs = tombs
            A.STORE.record_activity = lambda *a, **k: None
            A.mirror_bank_soon = lambda: None
            back = bank.add({"gid": "gB", "type": "pooled", "name": "a pool",
                             "events": [{"start": 3.0}], "added_by": "test",
                             "pipeline": "The Confluence: Junction"})
            tombs.add("bank", back["id"], note="deleted, pre-fix",
                      at="2099-01-01T00:00:00+00:00")
            cur.create("gB", "ied", [{"start": 3.0}], name="came back")
            tombs.add("curation", "gB__ied",
                      at="2099-01-01T00:00:00+00:00")
            cur.create("gC", "ied", [{"start": 4.0}], name="started again")
            tombs.add("curation", "gC__ied",
                      at="2000-01-01T00:00:00+00:00")
            got = A._sweep_tombstoned()
            check("an entry a note covers, brought back by a merge, is erased",
                  bank.get(back["id"]) is None, got)
            check("so is a set the note covers",
                  cur.get("gB", "ied") is None, got)
            check("a set started again after its note is left alone",
                  cur.get("gC", "ied") is not None, got)
            check("an entry no note names is left alone",
                  bank.get(keep["id"]) is not None)
            check("it says what it did", got == {"bank": 1, "curation": 1},
                  got)
            check("and a second sweep finds nothing",
                  A._sweep_tombstoned() == {"bank": 0, "curation": 0})

            print("\ndeleting in Jarvis writes the note")
            cli = A.app.test_client()
            a1 = bank.add({"gid": "gD", "type": "ied", "name": "one",
                           "events": [{"start": 1.0}], "added_by": "Someone",
                           "pipeline": "Doppler (line length)"})
            a2 = bank.add({"gid": "gD", "type": "ied", "name": "two",
                           "events": [{"start": 2.0}], "added_by": "Someone",
                           "pipeline": "Doppler (line length)"})
            cli.post("/api/bank/%s/delete" % a1["id"], json={},
                     base_url="http://127.0.0.1:8733")
            check("a deletion from a browser is noted, to reach Supabase",
                  tombs.is_deleted("bank", a1["id"]))
            cli.post("/api/bank/%s/delete" % a2["id"], json={})
            check("one from a test's client is not",
                  bank.get(a2["id"]) is None
                  and not tombs.is_deleted("bank", a2["id"]))
            a3 = bank.add({"gid": "gD", "type": "ied", "name": "three",
                           "events": [{"start": 3.0}], "added_by": "Someone",
                           "pipeline": "Doppler (line length)"})
            os.environ["BARRY_HARNESS_SERVER"] = "1"
            try:
                cli.post("/api/bank/%s/delete" % a3["id"], json={},
                         base_url="http://127.0.0.1:8791")
            finally:
                os.environ.pop("BARRY_HARNESS_SERVER", None)
            check("nor one on a harness server",
                  not tombs.is_deleted("bank", a3["id"]))
            h = bank.add({"gid": "demo-x", "type": "ied", "name": "seed",
                          "events": [{"start": 4.0}], "added_by": "harness",
                          "pipeline": "harness: seed"})
            cli.post("/api/bank/%s/delete" % h["id"], json={},
                     base_url="http://127.0.0.1:8733")
            check("nor a harness's own seed",
                  not tombs.is_deleted("bank", h["id"]))
            cur.create("gE", "ied", [{"start": 1.0}], name="a set")
            cli.post("/api/curation/gE/ied/delete", json={},
                     base_url="http://127.0.0.1:8733")
            check("deleting a curation set is noted too",
                  tombs.is_deleted("curation", "gE__ied"))
        finally:
            (A.BANK, A.CURATE, A.RESULTS.tombs, A.STORE.record_activity,
             A.mirror_bank_soon) = saved
        print("\nthe harness runner leaves a swept record deleted")
        sys.path.insert(0, HERE)
        import run_harnesses as RH                       # noqa: E402
        root_was = RH.ROOT
        try:
            RH.ROOT = tmp
            os.makedirs(os.path.join(tmp, "GUI_logs", "tombstones"),
                        exist_ok=True)
            import json as _json                         # noqa: E402
            with open(os.path.join(tmp, "GUI_logs", "tombstones",
                                   "deleted@x.json"), "w",
                      encoding="utf-8") as fh:
                _json.dump({"gone": {"bank:abc123def456": {},
                                     "curation:sX__ied": {}}}, fh)
            got = RH._tombstoned([
                "GUI_logs/event_bank/pten_m1_s2_abc123def456@m.json",
                "GUI_logs/curation/sX__ied@m.json",
                "GUI_logs/event_bank/pten_m1_s2_000000000000@m.json",
                "GUI_logs/curation/sX__ds@m.json"])
            check("a tombstoned entry's and set's shards are recognised, "
                  "nothing else",
                  got == {"GUI_logs/event_bank/pten_m1_s2_abc123def456@m.json",
                          "GUI_logs/curation/sX__ied@m.json"}, got)
        finally:
            RH.ROOT = root_was
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s" % ("ALL PASS" if not FAILED else
                    "%d FAILED: %s" % (len(FAILED), "; ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
