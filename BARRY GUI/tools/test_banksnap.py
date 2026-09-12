"""
test_banksnap.py -- A banked version travels whole, or not at all.

Migration 11 sent the version history up without its snapshots, so a
colleague's v7 was visible and not restorable: you could see who made it and
how many events it held, and you needed a git pull to have it. Migration 14
and `bank_snapshots` close that, and this proves the properties that make it
safe to do so.

Two scratch banks stand in for two machines. Nothing here touches the real
store: both live in a temp folder that is deleted afterwards.

What is being proven
--------------------
  * a snapshot reaches a machine that only had the metadata, and the
    `snap_elsewhere` flag that said "not restorable here" is cleared;
  * a snapshot ALREADY held is never overwritten -- the second machine's
    copy of its own work survives a pull;
  * two different snapshots for one version is reported as a conflict and
    the local copy is kept, because there is no correct side to pick;
  * a payload whose digest does not match its own content is refused, which
    is what catches a half-transferred one before somebody restores from it;
  * the digest agrees across float noise, so the same events written by two
    paths are one snapshot and not two.

The versions above v0 are appended directly rather than by re-banking
through `add`. `add` mints v0 from the events itself and has its own rules
about what counts as a new version; those are its business and are covered
elsewhere. What is under test here is the transfer.

    python tools/test_banksnap.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import eventbank, store as storemod  # noqa: E402

FAILED = []

SNAP = [[315.275, "ds"], [402.5, "ds"], [510.125, None]]


def check(name, got, want):
    ok = got == want
    print("  %-58s %s" % (name, "ok" if ok else "FAILED"))
    if not ok:
        print("      got  %r" % (got,))
        print("      want %r" % (want,))
        FAILED.append(name)


def a_bank(root, name):
    """A bank of its own, in its own folder."""
    where = os.path.join(root, name)
    os.makedirs(where, exist_ok=True)
    return eventbank.EventBank(where, storemod.Store(where))


def an_entry(bank, eid):
    """An entry that exists. `add` gives it its own v0."""
    bank.add({
        "id": eid, "gid": "gtest", "project": "TEST", "mouse": 1,
        "session": 1, "type": "ds", "type_name": "DS candidates",
        "name": "test set", "units": "s",
        # The bank insists on knowing what produced the events, and is right
        # to: an entry that cannot say where it came from is not worth
        # keeping.
        "pipeline": "test_banksnap.py",
        "events": [{"start": 1.0}, {"start": 2.0}],
    })
    return bank.get(eid)


def with_snapshot(bank, eid, v, snap):
    """A version this machine can restore: metadata and snapshot."""
    rec = bank.get(eid)
    rec.setdefault("versions", []).append({
        "v": v, "at": "2026-09-10T12:00:00-04:00", "by": "me",
        "n": len(snap), "snap": snap, "machine": "rig",
    })
    rec["version"] = v
    bank._save(rec)
    return rec


def seen_only(bank, eid, v, n):
    """What migration 11 delivers: a version you can see and cannot restore."""
    bank.absorb_versions(eid, [{"v": v, "at": "2026-09-10T12:00:00-04:00",
                                "by": "them", "n": n}], v)
    return bank.get(eid)


def version_of(bank, eid, v):
    rec = bank.get(eid) or {}
    for ver in (rec.get("versions") or []):
        if ver.get("v") == v:
            return ver
    return None


def the_digest():
    print("the digest")
    same = [[315.27500000000003, "ds"], [402.5, "ds"], [510.125, None]]
    check("float noise is the same snapshot",
          eventbank.snap_sha(SNAP) == eventbank.snap_sha(same), True)
    check("a different label is a different snapshot",
          eventbank.snap_sha(SNAP)
          == eventbank.snap_sha([[315.275, "ied"], [402.5, "ds"],
                                 [510.125, None]]), False)
    check("a missing event is a different snapshot",
          eventbank.snap_sha(SNAP) == eventbank.snap_sha(SNAP[:2]), False)


def it_arrives(root):
    print("a snapshot reaches a machine that only had the metadata")
    src = a_bank(root, "rig")
    dst = a_bank(root, "desk")
    an_entry(src, "e1")
    with_snapshot(src, "e1", 7, SNAP)
    an_entry(dst, "e1")
    seen_only(dst, "e1", 7, len(SNAP))

    before = version_of(dst, "e1", 7)
    check("the version is visible before it arrives", bool(before), True)
    check("and says it is not restorable here",
          bool((before or {}).get("snap_elsewhere")), True)
    check("and has no snapshot", (before or {}).get("snap"), None)

    mine = [row for row in src.snapshots() if row[1] == 7]
    check("the rig offers it", len(mine), 1)
    eid, v, snap, _m, _at = mine[0]
    check("absorbing it is new work",
          dst.absorb_snapshot(eid, v, snap, eventbank.snap_sha(snap)),
          "added")

    after = version_of(dst, "e1", 7)
    check("the snapshot is here now",
          eventbank.snap_sha((after or {}).get("snap")),
          eventbank.snap_sha(SNAP))
    check("and it no longer says otherwise",
          (after or {}).get("snap_elsewhere"), None)
    check("absorbing it twice changes nothing",
          dst.absorb_snapshot(eid, v, snap), "already")


def it_never_overwrites(root):
    print("a snapshot already held is not overwritten")
    dst = a_bank(root, "desk2")
    an_entry(dst, "e2")
    with_snapshot(dst, "e2", 7, SNAP)
    mine = version_of(dst, "e2", 7)["snap"]

    # The same version, different content -- which must not be applied.
    theirs = [[315.275, "ds"], [402.5, "ds"]]
    got = dst.absorb_snapshot("e2", 7, theirs, eventbank.snap_sha(theirs))
    check("a disagreement is reported as a conflict",
          isinstance(got, str) and got.startswith("conflict"), True)
    check("and the local copy is untouched",
          eventbank.snap_sha(version_of(dst, "e2", 7)["snap"]),
          eventbank.snap_sha(mine))
    check("an identical copy is a no-op",
          dst.absorb_snapshot("e2", 7, list(SNAP)), "already")


def it_checks_the_digest(root):
    print("a payload that disagrees with its own digest is refused")
    dst = a_bank(root, "desk3")
    an_entry(dst, "e3")
    seen_only(dst, "e3", 7, len(SNAP))
    got = dst.absorb_snapshot("e3", 7, SNAP, "0" * 64)
    check("refused", isinstance(got, str) and got.startswith("conflict"),
          True)
    check("and nothing was written",
          version_of(dst, "e3", 7).get("snap"), None)
    check("the same payload with its real digest is taken",
          dst.absorb_snapshot("e3", 7, SNAP, eventbank.snap_sha(SNAP)),
          "added")


def it_declines_the_unknown(root):
    print("a snapshot for a version nobody here has heard of")
    dst = a_bank(root, "desk4")
    check("an unknown entry", dst.absorb_snapshot("nope", 7, SNAP),
          "unknown")
    an_entry(dst, "e4")
    check("a known entry, unknown version",
          dst.absorb_snapshot("e4", 9, SNAP), "unknown")


def main():
    root = tempfile.mkdtemp(prefix="barry-banksnap-")
    try:
        the_digest()
        print()
        it_arrives(root)
        print()
        it_never_overwrites(root)
        print()
        it_checks_the_digest(root)
        print()
        it_declines_the_unknown(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILED:
        print("%d check(s) FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
