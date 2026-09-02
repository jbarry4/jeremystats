"""
test_shards.py -- Prove the shard layer does what the docstring claims.

Two machines, one record, every merge kind, plus the two failure modes that
matter: a lost update (I write back a field you just changed) and a deletion
(a removal that must not be resurrected by an older shard that still has it).

    python tools/test_shards.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import shards  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %-58s %s" % (name, "ok" if ok else "FAILED"))
    if not ok:
        print("      got  %r" % (got,))
        print("      want %r" % (want,))
        FAILED.append(name)


def as_machine(name):
    """Pretend to be a different computer for the next Book operation."""
    os.environ["BARRY_MACHINE"] = name
    shards._MACHINE = None
    return shards.machine_id()


SPEC = {
    "gid": shards.FIRST,
    "paths": shards.UNION,
    "labels": shards.MAPLWW,
    "bookmarks": shards.BYID,
}


def book(d):
    return shards.Book(d, spec=SPEC)


def main():
    tmp = tempfile.mkdtemp(prefix="barry-shards-")
    d = os.path.join(tmp, "sessions")
    try:
        print("Two machines, one record")

        # ---- machine A creates it ------------------------------------
        as_machine("alpha")
        b = book(d)
        b.write("m1s2", {
            "gid": "sAAA", "note": "from alpha", "project": "PTEN",
            "paths": ["D:/PTEN/m1s2"],
            "labels": {"14": "ca1_sp", "16": "hil"},
            "bookmarks": [{"id": "b1", "t": 10}],
        })

        # ---- machine B, same record, different knowledge -------------
        as_machine("beta")
        b = book(d)
        rec = b.read("m1s2")
        check("beta sees alpha's record", rec["note"], "from alpha")
        rec["paths"] = list(rec["paths"]) + ["//netfiles/bigdata/m1s2"]
        rec["labels"]["18"] = "dg_gcl1"
        rec["bookmarks"] = list(rec["bookmarks"]) + [{"id": "b2", "t": 90}]
        rec["note"] = "beta looked at it"
        b.write("m1s2", rec)

        files = sorted(os.listdir(d))
        check("one file per machine, nothing shared", files,
              ["m1s2@alpha.json", "m1s2@beta.json"])

        merged = b.read("m1s2")
        check("UNION keeps both mounts", sorted(merged["paths"]),
              sorted(["D:/PTEN/m1s2", "//netfiles/bigdata/m1s2"]))
        check("MAPLWW keeps both people's labels", merged["labels"],
              {"14": "ca1_sp", "16": "hil", "18": "dg_gcl1"})
        check("BYID keeps both bookmarks",
              [x["id"] for x in merged["bookmarks"]], ["b1", "b2"])
        check("LWW takes the newer note", merged["note"], "beta looked at it")

        # ---- the lost update -----------------------------------------
        # alpha read the record BEFORE beta touched the note, and now writes
        # back something unrelated. Beta's note must survive.
        as_machine("alpha")
        b = book(d)
        stale = b.read("m1s2")
        as_machine("beta")
        book(d).write("m1s2", dict(b.read("m1s2"), note="beta again"))
        as_machine("alpha")
        stale["project"] = "PTEN"          # alpha changes something else
        stale["bad_channels"] = [41, 59]
        book(d).write("m1s2", stale)
        after = book(d).read("m1s2")
        check("a stale write does not clobber a field it did not touch",
              after["note"], "beta again")
        check("...while the field it did touch lands",
              after["bad_channels"], [41, 59])

        # ---- deletion is not resurrected ------------------------------
        as_machine("beta")
        b = book(d)
        rec = b.read("m1s2")
        rec["labels"].pop("14")
        rec["paths"] = [p for p in rec["paths"] if p != "D:/PTEN/m1s2"]
        b.write("m1s2", rec)
        after = book(d).read("m1s2")
        check("a removed label stays removed", sorted(after["labels"]),
              ["16", "18"])
        check("a removed path stays removed", after["paths"],
              ["//netfiles/bigdata/m1s2"])

        # ---- deletion is not resurrected by an untouched write ---------
        # The nastiest case: alpha still lists label 14 in its own shard and
        # writes again for an unrelated reason. Nothing about labels changed
        # for alpha, so nothing about labels may move.
        as_machine("alpha")
        rec = book(d).read("m1s2")
        rec["note"] = "alpha edits only the note"
        book(d).write("m1s2", rec)
        after = book(d).read("m1s2")
        check("an unrelated write does not resurrect a deleted label",
              sorted(after["labels"]), ["16", "18"])
        check("...nor a deleted path", after["paths"],
              ["//netfiles/bigdata/m1s2"])

        # ---- but a deliberate re-add does bring it back -----------------
        as_machine("alpha")
        rec = book(d).read("m1s2")
        rec["labels"]["14"] = "ca1_so"
        book(d).write("m1s2", rec)
        check("re-adding it on purpose works",
              book(d).read("m1s2")["labels"].get("14"), "ca1_so")

        # ---- concurrent edits to the same field converge ----------------
        as_machine("alpha")
        a_rec = book(d).read("m1s2")
        as_machine("beta")
        b_rec = book(d).read("m1s2")
        as_machine("alpha")
        a_rec["project"] = "alpha says PTEN"
        book(d).write("m1s2", a_rec)
        as_machine("beta")
        b_rec["project"] = "beta says KCNT1"
        book(d).write("m1s2", b_rec)
        as_machine("alpha")
        left = book(d).read("m1s2")["project"]
        as_machine("beta")
        right = book(d).read("m1s2")["project"]
        check("a genuine clash resolves the same way on both machines",
              (left, right), ("beta says KCNT1", "beta says KCNT1"))

        # ---- a whole field removed --------------------------------------
        as_machine("beta")
        rec = book(d).read("m1s2")
        rec.pop("bad_channels")
        book(d).write("m1s2", rec)
        check("dropping a field removes it everywhere",
              "bad_channels" in book(d).read("m1s2"), False)

        # ---- FIRST: the global id never moves -------------------------
        as_machine("gamma")
        g = book(d)
        g.write("m1s2", {"gid": "sZZZ", "note": "gamma minted its own id"})
        check("FIRST keeps the earliest gid", book(d).read("m1s2")["gid"],
              "sAAA")

        # ---- every clone agrees ---------------------------------------
        as_machine("alpha")
        one = book(d).read("m1s2")
        as_machine("beta")
        two = book(d).read("m1s2")
        one.pop("_sync", None)
        two.pop("_sync", None)
        check("all machines compile the same record", one, two)

        # ---- legacy absorption ----------------------------------------
        print()
        print("Absorbing a pre-sharding file")
        legacy_dir = os.path.join(tmp, "legacy")
        os.makedirs(legacy_dir)
        shards._write_json(os.path.join(legacy_dir, "m9s9.json"),
                           {"gid": "sOLD", "note": "written before sharding"})
        as_machine("alpha")
        moved = book(legacy_dir).absorb_legacy()
        check("the old file is converted", moved, ["m9s9"])
        check("and gone", os.listdir(legacy_dir), ["m9s9@alpha.json"])
        check("with its content intact",
              book(legacy_dir).read("m9s9")["note"], "written before sharding")

        # ---- day logs --------------------------------------------------
        print()
        print("Append-only logs")
        ldir = os.path.join(tmp, "errors")
        as_machine("alpha")
        shards.DayLog(ldir).append([{"at": "2026-09-02T10:00:00", "m": "a1"}])
        as_machine("beta")
        shards.DayLog(ldir).append([{"at": "2026-09-02T11:00:00", "m": "b1"}])
        check("one file per machine per day", sorted(os.listdir(ldir)),
              ["2026-09-02@alpha.jsonl", "2026-09-02@beta.jsonl"])
        rows = shards.DayLog(ldir).read()
        check("read interleaves them newest first",
              [r["m"] for r in rows], ["b1", "a1"])

    finally:
        os.environ.pop("BARRY_MACHINE", None)
        shards._MACHINE = None
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d check(s) FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
