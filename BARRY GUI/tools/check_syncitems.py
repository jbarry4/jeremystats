# -*- coding: utf-8 -*-
"""Has it reached the shared database: the backend half.

    python tools/check_syncitems.py

Nothing here talks to Supabase and nothing is written under GUI_logs.

1. `Sync.item_states` against stores made up here: a record older than the
   push cursor is synced, a newer one waiting, a demo one local, one whose
   recording the registry lacks local, and with no push ever everything is
   waiting.
2. The change hook (`syncitems.install`): a write to a Book under a shared
   directory asks for an urgent push, a write anywhere else does not, and
   nothing is asked while a sync holds the lock -- that write came from a
   pull.
3. `cloud_sync_once`: a pull that fails no longer stops the push behind it,
   and the failure is still what is reported.
4. `/api/cloud/items` answers on the real app, shaped as the page reads it.
"""
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

FAILS = []


def check(what, ok, note=""):
    print(("  ok   " if ok else "  FAIL ") + what
          + ("   [%s]" % note if note and not ok else ""))
    if not ok:
        FAILS.append(what)


class Store:
    def __init__(self, recs):
        self.recs = recs

    def all(self):
        return list(self.recs)


def part1():
    from backend import cloudsync
    print("1. item_states")
    tmp = tempfile.mkdtemp(prefix="syncitems-")
    try:
        bank = Store([
            {"id": "old", "gid": "g1", "added": {"at": "2026-09-01T10:00:00+00:00"}},
            {"id": "new", "gid": "g1", "added": {"at": "2026-09-01T10:00:00+00:00"},
             "versions": [{"v": 2, "at": "2026-09-03T10:00:00+00:00"}]},
            {"id": "demo", "gid": "demo-x", "added": {"at": "2026-09-01T10:00:00+00:00"}},
            {"id": "orphan", "gid": "gone", "added": {"at": "2026-09-01T10:00:00+00:00"}},
        ])
        cur = Store([
            {"gid": "g1", "kind": "ds", "updated": {"at": "2026-09-01T10:00:00+00:00"},
             "events": [{"id": "e1", "at": "2026-09-01T11:00:00+00:00"}]},
            {"gid": "g2", "kind": "ds", "updated": {"at": "2026-09-01T10:00:00+00:00"},
             # A decision made after the push, inside an old set: that is
             # what makes the set waiting.
             "events": [{"id": "e1", "at": "2026-09-04T11:00:00+00:00"}]},
        ])
        lay = Store([{"gid": "g1", "updated": {"at": "2026-09-05T00:00:00+00:00"}}])
        s = cloudsync.Sync(tmp, None, bank=bank, curate=cur, layers=lay)
        cursor = "2026-09-02T00:00:00+00:00"
        got = s.item_states(last_push=cursor, known_gids={"g1", "g2"})
        b = got["bank"]
        check("an entry untouched since the push is synced",
              b["old"]["state"] == "synced", b["old"])
        check("an entry with a version after it is waiting",
              b["new"]["state"] == "waiting", b["new"])
        check("a demo entry never travels",
              b["demo"]["state"] == "local" and b["demo"]["why"] == "demo")
        check("nor one whose recording the registry does not have",
              b["orphan"]["state"] == "local"
              and b["orphan"]["why"] == "no recording")
        c = got["curation"]
        check("a set is keyed as the push files it, gid__kind",
              set(c) == {"g1__ds", "g2__ds"}, sorted(c))
        check("a set whose decisions are all older is synced",
              c["g1__ds"]["state"] == "synced", c["g1__ds"])
        check("a decision after the push makes its set waiting",
              c["g2__ds"]["state"] == "waiting", c["g2__ds"])
        check("a layer sheet edited after the push is waiting",
              got["layers"]["g1"]["state"] == "waiting")
        none = s.item_states(last_push=None, known_gids={"g1", "g2"})
        check("with no push ever, every shareable record is waiting",
              none["bank"]["old"]["state"] == "waiting"
              and none["curation"]["g1__ds"]["state"] == "waiting")
        check("no artifact store, no artifact answer",
              "artifacts" not in got)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def part2():
    from flask import Flask
    from backend import shards, syncitems
    print("2. the change hook")
    tmp = tempfile.mkdtemp(prefix="syncitems-")
    was = shards.ON_CHANGE
    try:
        shared = os.path.join(tmp, "event_bank")
        other = os.path.join(tmp, "prefs")
        os.makedirs(shared)
        os.makedirs(other)
        asked = []
        lock = threading.Lock()

        class Reg:
            def all(self):
                return []

        class FakeSync:
            ITEM_KINDS = ("bank",)
            cloud = None

            def item_states(self, *a, **k):
                return {}

        syncitems.install(Flask("t"), cloud_sync=FakeSync(), stores=(shared,),
                          registry=Reg(), last={},
                          touch=lambda urgent=False: asked.append(urgent),
                          lock=lock)
        shards.Book(shared).write("e1", {"id": "e1", "name": "x"})
        check("a write to a shared store asks for an urgent push",
              asked == [True], asked)
        del asked[:]
        shards.Book(other).write("p1", {"a": 1})
        check("a write anywhere else asks for nothing", asked == [], asked)
        b = shards.Book(shared)
        with lock:
            b.write("e2", {"id": "e2"})
        check("nothing is asked while a sync is applying what it pulled",
              asked == [], asked)
        b.erase("e1")
        check("erasing a shared record asks too", asked == [True], asked)
    finally:
        shards.ON_CHANGE = was
        shutil.rmtree(tmp, ignore_errors=True)


def part3_and_4():
    from backend import app as A
    print("3. a failed pull does not hold the push back")
    calls = []
    saved = {k: getattr(A.CLOUD, k) for k in
             ("pull", "push", "push_deletions", "mirror_bank")}
    saved_last = dict(A._cloud_last)

    def pull(**k):
        calls.append("pull")
        raise RuntimeError('GET /rest/v1/barry_watermarks -> HTTP 522 '
                           '{"title":"Error 522: Connection timed out"}')

    def push(**k):
        calls.append("push")
        return {"sent": 3}

    A.CLOUD.pull = pull
    A.CLOUD.push = push
    A.CLOUD.push_deletions = lambda: {"marked": 0}
    A.CLOUD.mirror_bank = lambda d: {"written": 0}
    # The failure would be filed in GUI_logs/errors; this is a rehearsal.
    real_err = A.STORE.record_error
    A.STORE.record_error = lambda *a, **k: None
    real_conf = type(A.CLOUD.cloud).configured
    type(A.CLOUD.cloud).configured = property(lambda self: True)
    try:
        out = A.cloud_sync_once(pull=True, push=True, files=False)
        check("the push ran after the pull failed",
              calls == ["pull", "push"], calls)
        check("and the result is the failure", out.get("ok") is False
              and "522" in (out.get("error") or ""), out.get("error"))
        check("with what did go through kept", out.get("pushed") == 3,
              out.get("pushed"))
        check("a 522 is the brief kind of failure",
              A._cloud_backoff(1, None) <= 180, A._cloud_backoff(1, None))
        del calls[:]
        out = A.cloud_sync_once(pull=True, push=False, files=False)
        check("a pull on its own still fails as itself",
              calls == ["pull"] and out.get("ok") is False, calls)
    finally:
        for k, v in saved.items():
            setattr(A.CLOUD, k, v)
        type(A.CLOUD.cloud).configured = real_conf
        A.STORE.record_error = real_err
        A._cloud_last.clear()
        A._cloud_last.update(saved_last)

    print("4. the route")
    r = A.app.test_client().get("/api/cloud/items?kinds=bank,curation")
    d = r.get_json() or {}
    check("it answers", r.status_code == 200 and d.get("ok") is True,
          r.status_code)
    check("with the fields the page reads",
          all(k in d for k in ("on", "last", "waiting", "items", "last_push")),
          sorted(d))
    if d.get("on"):
        check("narrowed to the kinds asked for",
              set(d["items"]) == {"bank", "curation"}, sorted(d["items"]))
        states = {v.get("state") for kind in d["items"].values()
                  for v in kind.values()}
        check("every state is one the page knows",
              states <= {"synced", "waiting", "local", "unknown"}, states)
    check("the hook is installed", A.shards.ON_CHANGE is not None)
    A._push_urgent[0] = 0.0
    A.shards.ON_CHANGE(A.BANK.book)
    check("a bank write asks for an urgent push", A._push_urgent[0] > 0)
    A._push_urgent[0] = 0.0


if __name__ == "__main__":
    part1()
    part2()
    part3_and_4()
    print("")
    print("%d failed" % len(FAILS) if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)
