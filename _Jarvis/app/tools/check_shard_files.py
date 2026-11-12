# -*- coding: utf-8 -*-
"""Braces sets and AI Beta runs travelling as shard files (migration 21).

    python tools/check_shard_files.py

Against a fake shared database and throwaway folders: nothing here talks to
Supabase or writes into GUI_logs. Checks what a push sends (only this
machine's own shards, only when their bytes change, paced), what a pull
writes (other machines' shards, into the cache folder the store reads, and
nowhere else), that the store then sees them merged, the per-record state
the marks are drawn from, and a database that has not been given the table.
"""
import base64
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import bracesset, cloudsync, shards  # noqa: E402

OK, BAD = [], []


def ck(name, good, why=""):
    (OK if good else BAD).append(name)
    print("  %s %s%s" % ("ok  " if good else "FAIL", name,
                         ("\n       %s" % why) if (why and not good) else ""))


def head(t):
    print("\n" + t + "\n" + "-" * 66)


class FakeCloud:
    def __init__(self):
        self.rows, self.st, self.absent, self.requests = {}, {}, False, 0

    def _gate(self):
        self.requests += 1
        if self.absent:
            raise RuntimeError("404 PGRST205 Could not find the table "
                               "'public.shard_files'")

    def select(self, table, query="", limit=None, offset=0, columns=None):
        self._gate()
        rows = list(self.rows.values())
        return rows[:limit] if limit else rows

    def select_all(self, table, query="", columns=None):
        return self.select(table, query)

    def upsert(self, table, rows, on_conflict=None):
        self._gate()
        for r in rows:
            self.rows[r["path"]] = dict(r)
        return len(rows)

    def state(self):
        return dict(self.st)

    def save_state(self, patch):
        self.st.update(patch or {})


def shard_row(path, machine, raw):
    return {"path": path, "store": path.split("/")[0], "machine": machine,
            "sha": hashlib.sha1(raw).hexdigest(), "bytes": len(raw),
            "gz": base64.b64encode(gzip.compress(raw)).decode("ascii"),
            "updated_at": "2026-10-06T12:00:00+00:00"}


def main():
    tmp = tempfile.mkdtemp(prefix="shardfiles_check_")
    try:
        sets = bracesset.BracesSets(tmp, None)
        fake = FakeCloud()
        s = cloudsync.Sync.__new__(cloudsync.Sync)
        s.cloud, s.machine, s._pending = fake, "this", {}
        s._shard_absent_until = 0.0
        s.shard_books = {"braces": (sets.book, "set_id")}
        me = shards.machine_id()

        head("A PUSH SENDS THIS MACHINE'S OWN SHARDS, ONCE PER CHANGE")
        sets.book.write("g1_A", {"set_id": "A", "gid": "g1", "rows": [1, 2]})
        r1 = s.rows_shard_files().get("shard_files") or []
        ck("a new set is sent", len(r1) == 1
           and r1[0]["path"] == "braces/g1_A@%s.json" % me
           and r1[0]["machine"] == me, r1)
        raw = gzip.decompress(base64.b64decode(r1[0]["gz"]))
        ck("as the file itself, gzipped, with its sha",
           hashlib.sha1(raw).hexdigest() == r1[0]["sha"]
           and json.loads(raw.decode("utf-8"))["set_id"] == "A")
        fake.upsert("shard_files", r1)
        fake.save_state(s._pending)
        s._pending = {}
        ck("and not again while it has not changed",
           not s.rows_shard_files().get("shard_files"))
        rec = sets.book.read("g1_A")
        rec["rows"] = [1, 2, 3]
        sets.book.write("g1_A", rec)
        r2 = s.rows_shard_files().get("shard_files") or []
        ck("a changed one is sent again", len(r2) == 1
           and r2[0]["sha"] != r1[0]["sha"])
        fake.upsert("shard_files", r2)
        fake.save_state(s._pending)
        s._pending = {}

        head("A PULL WRITES OTHER MACHINES' SHARDS WHERE THE STORE READS THEM")
        other = json.dumps({"set_id": "B", "gid": "g2", "rows": [9],
                            "_shard": {"machine": "rig-1", "at": "x"}},
                           sort_keys=True).encode("utf-8")
        rows = [shard_row("braces/g2_B@rig-1.json", "rig-1", other)]
        n = s._apply_shard_files(rows)
        dest = os.path.join(sets.pulled, "g2_B@rig-1.json")
        ck("another machine's shard is written into the cache folder",
           n == 1 and os.path.exists(dest)
           and open(dest, "rb").read() == other)
        ck("and never into the tracked folder git carries",
           not os.path.exists(os.path.join(sets.dir, "g2_B@rig-1.json")))
        ck("the store sees it", sets.get("B") is not None
           and sets.get("B")["rows"] == [9])
        ck("written once: the same row again writes nothing",
           s._apply_shard_files(rows) == 0)
        bad = [
            shard_row("braces/../evil@rig-1.json", "rig-1", other),
            shard_row("braces/g3_C@%s.json" % me, me, other),
            shard_row("braces/g4_D@rig-2.json", "rig-1", other),
            shard_row("nosuchstore/g5_E@rig-1.json", "rig-1", other),
            dict(shard_row("braces/g6_F@rig-1.json", "rig-1", other),
                 sha="0" * 40),
        ]
        ck("refused: a path out of the folder, this machine's own shard, a "
           "name another machine's, an unknown store, and a damaged file",
           s._apply_shard_files(bad) == 0
           and sorted(os.listdir(sets.pulled)) == ["g2_B@rig-1.json"],
           os.listdir(sets.pulled))
        ck("our own shard is never sent back by a pull, nor overwritten",
           json.loads(open(sets.book.mine("g1_A"), encoding="utf-8")
                      .read())["rows"] == [1, 2, 3])

        head("ONE RECORD, SHARDS FROM BOTH MACHINES, MERGED")
        theirs = json.loads(open(dest, encoding="utf-8").read())
        both = json.dumps({"set_id": "A", "gid": "g1", "note": "from the rig",
                           "_shard": {"machine": "rig-1",
                                      "at": "2099-01-01T00:00:00+00:00"},
                           "_at": {"note": "2099-01-01T00:00:00+00:00"}},
                          sort_keys=True).encode("utf-8")
        s._apply_shard_files([shard_row("braces/g1_A@rig-1.json", "rig-1",
                                        both)])
        a = sets.get("A")
        ck("a set edited on two machines reads as one, with both edits",
           a is not None and a.get("rows") == [1, 2, 3]
           and a.get("note") == "from the rig", a)
        ck("the store's other set is untouched", theirs["set_id"] == "B")

        head("EACH SET'S MARK")
        st = s._shard_states("braces")
        ck("ours, sent: shared", st.get("A", {}).get("state") == "synced", st)
        ck("one only another machine wrote: shared, and says where from",
           st.get("B", {}).get("state") == "synced"
           and st["B"].get("why") == "from another machine")
        rec = sets.book.read("g1_A")
        rec["rows"] = [7]
        sets.book.write("g1_A", rec)
        ck("ours, changed since: waiting",
           s._shard_states("braces").get("A", {}).get("state") == "waiting")

        head("PACED: A STORE THAT NEVER TRAVELLED GOES IN STEPS")
        big = "x" * 300000
        for j in range(8):
            sets.book.write("g9_P%d" % j, {"set_id": "P%d" % j, "gid": "g9",
                                           "blob": big + str(j)})
        import random
        rnd = random.Random(1)
        for j in range(8):
            rec = sets.book.read("g9_P%d" % j)
            rec["blob"] = "".join(rnd.choice("abcdef0123456789")
                                  for _ in range(250000))
            sets.book.write("g9_P%d" % j, rec)
        sent = 0
        pushes = 0
        while True:
            rows = s.rows_shard_files().get("shard_files") or []
            if not rows:
                break
            ck_size = sum(len(r["gz"]) for r in rows)
            if len(rows) > 1 and ck_size > cloudsync.SHARD_PUSH_BYTES:
                ck("a push stays under its byte budget", False, ck_size)
            fake.upsert("shard_files", rows)
            fake.save_state(s._pending)
            s._pending = {}
            sent += len(rows)
            pushes += 1
            if pushes > 20:
                break
        ck("every shard goes, over several pushes rather than one",
           sent == 9 and pushes > 1, (sent, pushes))

        head("A DATABASE WITHOUT THE TABLE (MIGRATION 21 NOT RUN)")
        fake.absent = True
        s._shard_absent_until = 0.0
        rec = sets.book.read("g1_A")
        rec["rows"] = [8]
        sets.book.write("g1_A", rec)
        ck("the push goes on without it, sending nothing for it",
           s.rows_shard_files() == {})
        before = fake.requests
        s.rows_shard_files()
        ck("and does not ask again until later", fake.requests == before)
        ck("its sets say they have not gone up",
           s._shard_states("braces").get("A", {}).get("state") == "local")

        head("EVERY OTHER BOOK IS UNCHANGED")
        plain = shards.Book(os.path.join(tmp, "plain"), {}, None)
        plain.write("x", {"v": 1})
        ck("a Book with no pulled folder reads exactly as before",
           plain.read("x")["v"] == 1 and plain.bases() == ["x"]
           and plain.extra == [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n  %d ok, %d fail" % (len(OK), len(BAD)))
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
