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
    back, and nothing else.

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

        n = sync._apply_curation(
            [{"id": "gA__pooled", "gid": "gA", "kind": "pooled",
              "deleted_at": long_ago}], [])
        check("a set made after the cloud's deletion stays",
              cur.get("gA", "pooled") is not None and n == 0, n)
        n = sync._apply_curation(
            [{"id": "gA__pooled", "gid": "gA", "kind": "pooled",
              "deleted_at": far}], [])
        check("a set made before it is erased, and noted",
              cur.get("gA", "pooled") is None and n == 1
              and tombs.is_deleted("curation", "gA__pooled"), n)

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
        finally:
            (A.BANK, A.CURATE, A.RESULTS.tombs, A.STORE.record_activity,
             A.mirror_bank_soon) = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s" % ("ALL PASS" if not FAILED else
                    "%d FAILED: %s" % (len(FAILED), "; ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
