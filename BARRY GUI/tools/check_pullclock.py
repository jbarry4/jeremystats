# -*- coding: utf-8 -*-
"""A row that reaches the database late is still pulled.

2026-10-30: "results banked in Panning don't show up in Lock unless a github
sync is done ... all automatic syncing seems broken". `updated_at` is the
writer's clock and the pull's cursor was the newest one it had seen, so a
row made at 10:00:00 and pushed at 10:00:40 was never pulled by a machine
whose cursor had already reached 10:00:20. The table's watermark could not
see it either: a late row with an older stamp does not move a max.

Driven against a fake database, no network:

  - on the writers' clocks (migration 24 not run): a row up to
    UPDATED_SLACK_S late is pulled; the cursor is still `last_pull`;
  - on the database's arrival clock (migration 24 run): a row with an old
    `updated_at` and a new `synced_at` is pulled however old its stamp is;
    the cursor is `last_arrival`, and a quiet cycle asks only the view.

    python tools/check_pullclock.py
"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import cloudsync  # noqa: E402

ok = bad = 0


def check(name, got, want=True):
    global ok, bad
    if got == want:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r, want %r" % (name, got, want))


class FakeCloud:
    """Enough of cloud.Cloud for `Sync.pull`: a table of rows per name, the
    watermark view worked out from them, and the `gt.` filter."""

    def __init__(self, arrival):
        self.arrival = arrival
        self.now = None             # the database's clock, for `_clock`
        self.tables = {}
        self.st = {}
        self.asked = []

    def state(self):
        return dict(self.st)

    def save_state(self, d):
        self.st.update(d)

    def _marks(self):
        out = []
        for t, rows in self.tables.items():
            m = {"table_name": t,
                 "updated_at": max((r["updated_at"] for r in rows), default=None)}
            if self.arrival:
                m["synced_at"] = max((r["synced_at"] for r in rows), default=None)
            out.append(m)
        if self.arrival:
            out.append({"table_name": "_clock", "updated_at": self.now,
                        "synced_at": self.now})
        return out

    def select(self, table, query="", limit=1000, offset=0, columns=None):
        if table == "barry_watermarks":
            self.asked.append(table)
            return self._marks()
        return self.select_all(table, query, columns)

    def select_all(self, table, query="", columns=None):
        self.asked.append(table)
        rows = list(self.tables.get(table, []))
        m = re.match(r"(\w+)=gt\.(.+)", query or "")
        if m:
            col, at = m.group(1), cloudsync._ts_key(m.group(2))
            if col not in ("updated_at", "synced_at") or (
                    col == "synced_at" and not self.arrival):
                raise RuntimeError("no column %s" % col)
            rows = [r for r in rows if cloudsync._ts_key(r[col]) > at]
        return rows


def sync_on(fake):
    s = cloudsync.Sync.__new__(cloudsync.Sync)
    s.__init__  # noqa: B018 -- built by hand: no store, no bank
    for k, v in dict(bank=None, curate=None, layers=None, mice=None,
                     results=None, feedback=None, people=None, health=None,
                     vaults={}, artifacts=None, shard_books={},
                     results_moved=True, snapshot_conflicts=[]).items():
        setattr(s, k, v)
    s.cloud = fake
    got = []
    # Every applier is replaced by one that records what reached it.
    for name in dir(s):
        if name.startswith("_apply_"):
            setattr(s, name, (lambda n: lambda *a: got.append(
                (n, [r.get("id") for r in (a[0] or [])])) or 0)(name))
    return s, got


def seen(got, applier):
    return [i for n, ids in got if n == applier for i in ids]


print("ON THE WRITERS' CLOCKS (migration 24 not run)")
fake = FakeCloud(arrival=False)
fake.tables["bank_entries"] = [
    {"id": "mine", "updated_at": "2026-10-30T10:00:20+00:00"}]
fake.st["last_pull"] = "2026-10-30T10:00:20+00:00"
# Strawbarry's row, made at 10:00:00, lands now -- behind the cursor.
fake.tables["bank_entries"].append(
    {"id": "late", "updated_at": "2026-10-30T10:00:00+00:00"})
s, got = sync_on(fake)
s.pull()
check("a row 20 s behind the cursor is pulled", "late" in seen(got, "_apply_bank"))
check("the cursor stays on the writers' clock",
      "last_arrival" in fake.st, False)
fake2 = FakeCloud(arrival=False)
fake2.tables["bank_entries"] = [
    {"id": "mine", "updated_at": "2026-10-30T10:30:00+00:00"},
    {"id": "ancient", "updated_at": "2026-10-30T10:00:00+00:00"}]
fake2.st["last_pull"] = "2026-10-30T10:30:00+00:00"
s, got = sync_on(fake2)
s.pull()
check("...but one older than the margin is not (that is what 24 is for)",
      "ancient" in seen(got, "_apply_bank"), False)

print("\nON THE DATABASE'S ARRIVAL CLOCK (migration 24 run)")
fake = FakeCloud(arrival=True)
fake.tables["bank_entries"] = [
    {"id": "mine", "updated_at": "2026-10-30T10:30:00+00:00",
     "synced_at": "2026-10-30T10:30:05+00:00"}]
fake.tables["bank_snapshots"] = []
fake.st["last_pull"] = "2026-10-30T10:30:00+00:00"
fake.now = "2026-10-30T10:31:00+00:00"
s, got = sync_on(fake)
s.pull()
check("the first pull on it starts from the beginning",
      seen(got, "_apply_bank"), ["mine"])
check("...and keeps the database's time as its cursor",
      fake.st.get("last_arrival"), "2026-10-30T10:31:00+00:00")
# A version made offline at 09:00 and pushed at 11:00.
fake.tables["bank_entries"].append(
    {"id": "offline", "updated_at": "2026-10-30T09:00:00+00:00",
     "synced_at": "2026-10-30T11:00:00+00:00"})
fake.tables["bank_snapshots"].append(
    {"id": "offline:3", "updated_at": "2026-10-30T09:00:00+00:00",
     "synced_at": "2026-10-30T11:00:01+00:00"})
fake.now = "2026-10-30T11:00:30+00:00"
s, got = sync_on(fake)
s.pull()
check("a row stamped two hours ago that arrived now is pulled",
      "offline" in seen(got, "_apply_bank"))
check("...and its snapshot", "offline:3" in seen(got, "_apply_bank_snapshots"))
check("...and 'mine' is not asked for again", "mine" in seen(got, "_apply_bank"),
      False)
check("the cursor moved to the database's time",
      fake.st.get("last_arrival"), "2026-10-30T11:00:30+00:00")
s, got = sync_on(fake)
fake.now = "2026-10-30T11:02:00+00:00"
s.pull()
fake.now = "2026-10-30T11:03:00+00:00"
fake.asked = []
got.clear()
s.pull()
check("a quiet cycle asks only the view", fake.asked, ["barry_watermarks"])
check("...and applies nothing", [x for x in got if x[1]], [])

print("\n%d ok, %d fail" % (ok, bad))
sys.exit(1 if bad else 0)
