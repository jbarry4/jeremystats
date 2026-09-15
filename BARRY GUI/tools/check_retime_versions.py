# -*- coding: utf-8 -*-
"""Correcting a chosen version, re-running, and undoing.

Against a COPY of the bank, never the real one. Every check here writes, and
the thing being written is the record of somebody's curation decisions.

What has to hold:

  * the correction can read an older version's events and labels, not just
    the current ones
  * which clock a version was on is worked out from the history, not from
    the entry -- get that wrong in the permissive direction and the shift is
    applied twice
  * the same correction cannot land twice
  * a correction that HAS been run can be run again from a version that
    predates it
  * deleting the correction puts the times back AND clears the stamp, so
    `healthlog.summary` goes back to reporting an unresolved segment issue
  * and when the times cannot be put back, nothing is deleted at all

Run: python tools/check_retime_versions.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import eventbank, healthlog                  # noqa: E402

FAILED = []


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "   [%s]" % detail))
    if not ok:
        FAILED.append(name)


class FakeStore:
    """Enough of a store for the bank to write into a temp directory.

    `provenance` is the one method whose ANSWER matters -- it decides who
    the version says wrote it. Everything else the shard book reaches for
    (`_stage`, and whatever else it grows) is bookkeeping for the real
    store's mirror and sync, which a temp directory has none of, so it is
    no-opped rather than stubbed one method at a time.
    """

    def provenance(self):
        return {"user": "checker", "machine": "test"}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


TRUE = "neuralynx_true"
CONCAT = "toothy_concat"

# A shift that only bites after 100 s, like a real gap map: everything
# before the first gap is untouched and everything after steps forward.
def shift(t):
    return (t + (0.12 if t >= 100.0 else 0.0), 0)


def fresh_bank():
    root = tempfile.mkdtemp(prefix="retimever-")
    bank = eventbank.EventBank(root, FakeStore())
    return root, bank


def seed(bank, n=40):
    """An entry with three versions whose labels differ, as a real one does."""
    evs = [{"start": round(5.0 * i + 1.0, 3),
            "label": "Dentate Spike", "label_id": "spike"} for i in range(n)]
    bank.add({
        "gid": "g-test", "name": "check set", "kind": "ds",
        "session_label": "m1 s1", "duration_s": 400.0,
        "pipeline": "tools/check_retime_versions.py", "added_by": "checker",
        "label_names": {"spike": "Dentate Spike", "garbage": "Garbage"},
        "events": evs, "specified": True,
    })
    eid = bank.all()[0]["id"]
    # A second pass that relabels some of them, so the versions genuinely
    # differ and "which version" is a question with consequences.
    evs2 = [dict(e) for e in evs]
    for e in evs2[:9]:
        e["label"], e["label_id"] = "Garbage", "garbage"
    bank.add({"id": eid,
              "gid": "g-test", "name": "check set", "kind": "ds",
              "session_label": "m1 s1", "duration_s": 400.0,
              "pipeline": "tools/check_retime_versions.py",
              "added_by": "checker",
              "label_names": {"spike": "Dentate Spike",
                              "garbage": "Garbage"},
              "events": evs2, "specified": True})
    return bank.all()[0]["id"]


print("Reading an older version")
root, bank = fresh_bank()
try:
    eid = seed(bank)
    rec = bank.get(eid)
    vs = [v.get("v") for v in rec["versions"]]
    print("   versions:", vs)
    ck("more than one version to choose between", len(vs) > 1, str(vs))

    lo, hi = min(vs), max(vs)
    rep_cur = bank.retime(eid, shift, TRUE, CONCAT, "sha-1", dry_run=True)
    rep_old = bank.retime(eid, shift, TRUE, CONCAT, "sha-1", dry_run=True,
                          from_version=lo)
    ck("the current set previews", rep_cur.get("moved") == 40,
       str(rep_cur.get("moved")))
    ck("and so does the oldest version", rep_old.get("moved") == 40,
       str(rep_old.get("moved")))
    ck("the preview says which version it read",
       rep_old.get("from_version") == lo, str(rep_old.get("from_version")))

    # The labels are the point: v0 has none decided as garbage, the latest
    # has nine. A correction read off v0 must carry v0's labels.
    def garbage(rep):
        return sum(1 for m in rep["moves"] if m[3] == "Garbage")
    ck("the current version carries its 9 relabelled events",
       garbage(rep_cur) == 9, str(garbage(rep_cur)))
    ck("and the oldest carries none of them",
       garbage(rep_old) == 0, str(garbage(rep_old)))

    print()
    print("Applying, and refusing to apply it twice")
    done = bank.retime(eid, shift, TRUE, CONCAT, "sha-1", dry_run=False,
                       from_version=lo)
    ck("it applied", not done.get("error"), str(done.get("error")))
    newv = done.get("version")
    ck("it minted a new version", newv is not None and newv > hi, str(newv))
    rec = bank.get(eid)
    ck("the entry is now stamped on the true clock",
       (rec.get("time_basis") or {}).get("kind") == TRUE,
       str(rec.get("time_basis")))
    ck("the times moved", rec["events"][-1]["start"] > 196.0,
       str(rec["events"][-1]["start"]))
    ck("the labels are the ones from the version it read",
       sum(1 for e in rec["events"] if e.get("label") == "Garbage") == 0,
       str(sum(1 for e in rec["events"] if e.get("label") == "Garbage")))

    again = bank.retime(eid, shift, TRUE, CONCAT, "sha-1", dry_run=True,
                        from_version=lo)
    ck("the identical correction is refused", bool(again.get("error")),
       "no error raised")
    ck("and it names the version that already holds it",
       again.get("already_version") == newv, str(again.get("already_version")))

    print()
    print("Which clock a version was on")
    rec = bank.get(eid)
    ck("the version it minted is on the true clock",
       bank.basis_at(rec, newv) == TRUE, str(bank.basis_at(rec, newv)))
    ck("the one it read is still on the concatenated clock",
       bank.basis_at(rec, lo) == CONCAT, str(bank.basis_at(rec, lo)))
    offer = bank.retime_versions(eid, TRUE)
    usable = [r["v"] for r in offer["versions"] if r["usable"]]
    ck("the corrected version is not offered as a source",
       newv not in usable, str(usable))
    ck("the earlier ones still are", lo in usable, str(usable))

    print()
    print("Running it again after it has already been run")
    # A different gap map -- the folder was re-checked and the answer moved.
    redo = bank.retime(eid, shift, TRUE, CONCAT, "sha-2", dry_run=False,
                       from_version=lo)
    ck("a re-run from a pre-correction version is allowed",
       not redo.get("error"), str(redo.get("error")))
    ck("and it lands as another new version",
       redo.get("version") == newv + 1, str(redo.get("version")))

    print()
    print("Deleting the correction puts it back")
    rec = bank.get(eid)
    before_n = len(rec["events"])
    out = bank.delete_version(eid, redo["version"])
    undo = out.get("undo") or {}
    ck("deleting the correction reports an undo", bool(undo), str(out.keys()))
    rec = bank.get(eid)
    ck("the event count is unchanged", len(rec["events"]) == before_n,
       str(len(rec["events"])))
    ck("and the times went back to what the first correction left",
       abs(rec["events"][-1]["start"] - 196.12) < 1e-6,
       str(rec["events"][-1]["start"]))

    # And the one that actually matters: the session goes back to unresolved.
    bank.delete_version(eid, newv)
    rec = bank.get(eid)
    ck("with every correction gone it no longer claims the true clock",
       (rec.get("time_basis") or {}).get("kind") != TRUE,
       str(rec.get("time_basis")))
    ck("  and the stale gap map from the correction is gone with it",
       not (rec.get("time_basis") or {}).get("gap_map_sha"),
       str(rec.get("time_basis")))
    ck("and the times are fully back",
       abs(rec["events"][-1]["start"] - 196.0) < 1e-6,
       str(rec["events"][-1]["start"]))

    print()
    print("And `patched` follows from that, with nothing else to update")
    stamped = [(rec.get("time_basis") or {}).get("kind")]
    ck("nothing reports this set as patched",
       not all(k == TRUE for k in stamped), str(stamped))

    print()
    print("A correction with nothing to restore from is not deleted")
    root2, bank2 = fresh_bank()
    try:
        eid2 = seed(bank2, n=12)
        d2 = bank2.retime(eid2, shift, TRUE, CONCAT, "sha-9", dry_run=False)
        rec2 = bank2.get(eid2)
        # Strip every snapshot below the correction, as a set too large to
        # snapshot would arrive from a colleague.
        for ver in rec2["versions"]:
            if (ver.get("v") or 0) < d2["version"]:
                ver.pop("snap", None)
        bank2._save(rec2)
        moved_to = bank2.get(eid2)["events"][-1]["start"]
        try:
            bank2.delete_version(eid2, d2["version"])
            ck("it refuses rather than half-undoing", False, "it deleted it")
        except eventbank.BankError as exc:
            ck("it refuses rather than half-undoing", True)
            ck("  and says why", "snapshot" in str(exc), str(exc)[:80])
        rec2 = bank2.get(eid2)
        ck("  and nothing was changed",
           len(rec2["versions"]) and
           abs(rec2["events"][-1]["start"] - moved_to) < 1e-9
           and (rec2.get("time_basis") or {}).get("kind") == TRUE,
           "state moved")
    finally:
        shutil.rmtree(root2, ignore_errors=True)
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
if FAILED:
    print("%d check(s) FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
    raise SystemExit(1)
print("all good")
