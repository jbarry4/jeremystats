# -*- coding: utf-8 -*-
"""test_shardcache.py -- Book.all() must never hand back a superseded record.

    python tools/test_shardcache.py

`Book.all()` keeps the compiled record list and re-uses it until the shard
directory's stamp moves, which is what took /api/registry's three reads of
1,702 session shards from about twelve seconds to half of one.

The stamp is each file's mtime and size, and that is not quite enough on its
own. Windows updates a file time from a clock that ticks about every 15 ms --
the same tick `shards._now()` already works around -- so a write that lands
inside one tick AND leaves the file the same length moves neither half of the
stamp. A curation decision changed from one four-letter label to another does
exactly that, which is why the hard case below is the one with equal lengths
written back to back.

`write()` therefore drops the cache outright rather than trusting the stamp.
A colleague's writes still arrive by pull, where the stamp is reliable.

Writes nothing outside a temp directory.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import shards  # noqa: E402

FAILED = []


def ck(what, got):
    print("  %-58s %s" % (what, "ok" if got else "FAIL"))
    if not got:
        FAILED.append(what)


def main():
    tmp = tempfile.mkdtemp(prefix="barry-shardcache-")
    try:
        book = shards.Book(os.path.join(tmp, "curation"))

        book.write("setA", {"gid": "setA", "verdict": "good"})
        book.write("setB", {"gid": "setB", "verdict": "good"})

        def verdict(base):
            for r in book.all():
                if r.get("gid") == base:
                    return r.get("verdict")
            return None

        ck("a fresh store reads back what was written",
           verdict("setA") == "good")

        # Warm the cache, then overwrite with a same-length value at once.
        book.all()
        book.write("setA", {"gid": "setA", "verdict": "junk"})
        ck("a same-length change is visible immediately",
           verdict("setA") == "junk")
        ck("the untouched record is still itself", verdict("setB") == "good")

        # Many rapid same-length flips -- what a fill-down looks like.
        ok = True
        for i in range(40):
            want = "good" if i % 2 else "junk"
            book.write("setB", {"gid": "setB", "verdict": want})
            if verdict("setB") != want:
                ok = False
                break
        ck("40 rapid same-length writes each read back correctly", ok)

        book.all()
        book.write("setC", {"gid": "setC", "verdict": "good"})
        ck("a record created after the cache warmed is listed",
           verdict("setC") == "good")

        book.all()
        ck("a repeat read with no write gives the same count",
           len(book.all()) == 3)

        # The list handed out is the caller's to edit. sessreg.Registry.all()
        # copies for the same reason; without it, one caller's edit becomes
        # every later reader's record.
        for r in book.all():
            r["verdict"] = "CLOBBERED"
        ck("editing the returned list does not edit the cache",
           verdict("setA") == "junk")

        # The ordering guarantees the rewrite had to preserve.
        names = [r.get("gid") for r in book.all()]
        ck("every record is listed exactly once", sorted(names) ==
           ["setA", "setB", "setC"])
        ck("bases() and all() agree on how many there are",
           len(book.bases()) == len(book.all()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("all checks passed." if not FAILED else "%d FAILED" % len(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
