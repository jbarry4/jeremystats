# -*- coding: utf-8 -*-
"""A saved Root Canal pool says, on the machine it is opened on, which of
its members' reads are here.

2026-10-30, Homebarry: Rain's pool 789627824001, saved on Strawbarry, was
opened, and the panel at once asked /api/rootcanal/event for member
adc84ab8c916's trace -- "This member's read is not on this machine". The
saved payload says `here: true` and carries a ready `event_body` for every
member, because both were true on Strawbarry, and /api/rootcanal/pool/<id>
handed it back as it was. `memberHere` in web/js/rootcanal.js believes the
server, so the click panel asked instead of reading the member here.

No server and nothing written: the artifact store and the read cache are
stood in for in memory, and the real route is asked through Flask's test
client.

    python tools/check_rootcanal_saved_here.py
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
# Before the import: no day-report loop or warm-up threads for a check.
os.environ.setdefault("BARRY_HARNESS_SERVER", "1")

from backend import app as A  # noqa: E402

ok = bad = 0


def check(name, got, want):
    global ok, bad
    if got == want:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r, want %r" % (name, got, want))


PARAMS = {"filt": "lfp", "lo_hz": 1.0, "hi_hz": 100.0, "win_ms": 25.0, "k": 2}


def member(key, gid, rh, here, read_on=None):
    return {
        "key": key, "entry_id": key, "gid": gid, "banked": False,
        "here": here, "read_on": read_on,
        "pin": {"read": rh, "params": dict(PARAMS)},
        "event_body": (dict(PARAMS, entry_id=key, read=rh) if here else None),
    }


SAVED = {
    "params": {"measure": {"filt": "lfp"}},
    "members": [
        # Read on Strawbarry, which saved it; not read here.
        member("away", "sAWAY", "rAWAY", True),
        # Read elsewhere when it was saved, read here since.
        member("came", "sCAME", "rCAME", False, read_on="Blackbarry"),
        # Read on both.
        member("both", "sBOTH", "rBOTH", True),
        # Read on neither, and the save did not say where.
        member("none", "sNONE", "rNONE", False),
    ],
}
KEEP = copy.deepcopy(SAVED)
ON_THIS_MACHINE = {("sCAME", "rCAME"), ("sBOTH", "rBOTH")}

A.ARTIFACTS.summary = lambda aid: {"id": aid, "kind": "rootcanal_pool"}
A.ARTIFACTS.payload = lambda aid, v=None: SAVED
A.ARTIFACTS.payload_version = lambda aid, v=None: (
    {"id": aid}, {"v": 2, "machine": "Strawbarry"})
A.ROOTCANAL.has_cached = lambda gid, rh, ext=".npz": (gid, rh) in ON_THIS_MACHINE
A._rootcanal_read_on = lambda gid, rh: None

r = A.app.test_client().get("/api/rootcanal/pool/checkpool?version=2")
got = r.get_json() or {}
check("the saved pool opens", (r.status_code, got.get("ok")), (200, True))
by = {m["key"]: m for m in (got.get("payload") or {}).get("members") or []}

print("a member read only where the pool was saved")
a = by.get("away") or {}
check("is not here", a.get("here"), False)
check("has no click request to send", a.get("event_body"), None)
check("says it was read where the pool was saved", a.get("read_on"),
      "Strawbarry")

print("a member read here since the pool was saved")
c = by.get("came") or {}
check("is here", c.get("here"), True)
check("has its click request, pinned to its read",
      c.get("event_body"), dict(PARAMS, entry_id="came", read="rCAME"))
check("is not said to be read elsewhere", c.get("read_on"), None)

print("a member read on both")
b = by.get("both") or {}
check("is here, its click request as saved",
      (b.get("here"), b.get("event_body")),
      (True, KEEP["members"][2]["event_body"]))

print("a member read on neither, the save not saying where")
n = by.get("none") or {}
check("is not here", n.get("here"), False)
check("is not credited to the machine that saved the pool",
      n.get("read_on"), None)

print("the saved payload itself")
check("is not changed by being opened", SAVED, KEEP)

print("\n%d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
