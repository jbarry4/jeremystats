# -*- coding: utf-8 -*-
"""Unit checks of the artifact store (backend/artifacts.py).

    python tools\\check_artifacts.py            the checks
    python tools\\check_artifacts.py --break    the negative controls too

Everything runs in a throwaway GUI_logs under the system temp directory, so
nothing here can touch a real artifact. Two machines are simulated by
switching `shards._MACHINE`, which is the one thing that decides whose shard
a write lands in.

`--break` re-runs the important checks against a deliberately broken store
(digest ignoring content, citations ignored by delete, snapshots rewritten,
versions merged last-write-wins) and REQUIRES each of those checks to fail.
A check that still passes against the broken store was not checking anything.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import artifacts as A      # noqa: E402
from backend import shards              # noqa: E402


class FakeStore:
    def __init__(self):
        self.user = "harness person"
        self.n = 0

    def provenance(self):
        self.n += 1
        return {"user": self.user, "machine": "machine-" + shards.machine_id(),
                "at": "2026-09-25T12:00:%02d-04:00" % (self.n % 60),
                "app_version": "2026.09.25.1", "commit": "abc1234"}

    def _stage(self, path):
        pass


def circuit_payload(scale=1.0):
    return {
        "schema": "arc.circuit/1", "kind": "state",
        "cue_type": "HighTone_LowTone",
        "windows": ["pre", "cue1", "cue2", "post"],
        "methods": ["coherence"],
        "n_pairs": 2,
        "cells": {"pre": {"coherence": {"Left PER|Left POR": {
            "n": 2, "mean": 0.3 * scale, "sd": 0.01,
            "values": [{"pair_id": 1, "v": 0.29 * scale},
                       {"pair_id": 2, "v": 0.31 * scale}],
            "of": 2, "warn": None}}}},
        "grey": [],
        "computed_on": {"kind": "local"},
    }


SUBJ = {"gid": "harness-art-1", "project": "DEWEY", "mouse": 4, "session": 1,
        "phase": "Precon", "phase_n": 1, "run": "SPC",
        "cue_type": "HighTone_LowTone", "window_kind": "state"}

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("ok    " if cond else "FAIL  ") + name
          + ("" if cond or not detail else "   [%s]" % detail))
    return bool(cond)


def raises(fn):
    try:
        fn()
    except A.ArtifactError as exc:
        return str(exc) or True
    return None


def run():
    tmp = tempfile.mkdtemp(prefix="jarvis-artifacts-check-")
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp):
    del results[:]
    shards._MACHINE = "machine-a"
    store = FakeStore()
    S = A.Artifacts(tmp, store)

    # -- create --------------------------------------------------------------
    rec = S.create("circuit", SUBJ, circuit_payload(), params={"low": 4},
                   inputs=[{"kind": "bank", "entry": "e1", "version": 3}])
    aid = rec["id"]
    check("create returns version 1", rec["version"] == 1
          and len(rec["versions"]) == 1, str(rec.get("version")))
    check("the automatic name is built from the metadata",
          rec["name"] == "DEWEY r4 s1 Precon1 SPC · High tone → "
                         "Low Tone · state", rec["name"])
    check("subject_key is deterministic",
          rec["subject_key"] == "circuit|harness-art-1|HighTone_LowTone|state",
          rec["subject_key"])
    check("the record carries only whitelisted fields",
          set(rec) == set(A.FIELDS), sorted(set(rec) ^ set(A.FIELDS)))
    v1 = rec["versions"][0]
    check("a version carries who, when, machine, app version, commit",
          all(v1.get(k) for k in ("by", "at", "machine", "app_version",
                                  "commit", "digest", "id")), str(v1))
    snap = S.snap_path(aid, 1, v1["digest"])
    check("the payload snapshot is on disk under snap/<id>/v1__<digest>.json",
          os.path.isfile(snap) and os.path.basename(snap)
          == "v1__%s.json" % v1["digest"], snap)
    check("the record file is artifacts/circuit/<id>@<machine>.json",
          os.path.isfile(os.path.join(tmp, "artifacts", "circuit",
                                      aid + "@machine-a.json")))
    check("unknown kinds are refused",
          raises(lambda: S.create("banana", SUBJ, {})))
    check("a second create for the same subject is refused",
          raises(lambda: S.create("circuit", SUBJ, circuit_payload())))
    check("a subject missing its key parts is refused",
          raises(lambda: S.create("circuit", {"gid": "harness-x"}, {})))

    # -- digest / confirmed ----------------------------------------------------
    mtime = os.path.getmtime(snap)
    same = circuit_payload()
    same["computed_on"] = {"kind": "vacc", "job": 7}
    same["cells"]["pre"]["coherence"]["Left PER|Left POR"]["mean"] = \
        0.3 + 1e-15                                     # last-bit noise
    rec2 = S.add_version(aid, same, params={"low": 4})
    check("a digest-equal re-run adds no version",
          len(rec2["versions"]) == 1 and rec2["version"] == 1,
          "%d versions" % len(rec2["versions"]))
    check("and stamps `confirmed` on the version instead",
          len(rec2["versions"][0].get("confirmed") or []) == 1,
          str(rec2["versions"][0].get("confirmed")))
    check("the snapshot is not rewritten by a confirmation",
          os.path.getmtime(snap) == mtime)
    rec3 = S.add_version(aid, circuit_payload(scale=2.0), note="rerun")
    check("a different payload makes v2", rec3["version"] == 2
          and len(rec3["versions"]) == 2, str(rec3["version"]))
    check("v1's payload is still restorable and unchanged",
          S.payload(aid, 1)["cells"]["pre"]["coherence"]
          ["Left PER|Left POR"]["mean"] == 0.3)
    check("the current payload is v2",
          S.payload(aid)["cells"]["pre"]["coherence"]
          ["Left PER|Left POR"]["mean"] == 0.6)
    check("snapshots are never rewritten (v1 untouched by v2)",
          os.path.getmtime(snap) == mtime)

    # -- find / nickname -------------------------------------------------------
    f = S.find("circuit", rec["subject_key"])
    check("find by subject_key returns the one artifact",
          f and f["id"] == aid, str(f and f["id"]))
    check("find takes the subject dict too",
          (S.find("circuit", SUBJ) or {}).get("id") == aid)
    put = S.put("circuit", SUBJ, circuit_payload(scale=3.0))
    check("put on a known subject adds a version rather than an artifact",
          put["id"] == aid and put["version"] == 3, str(put["version"]))
    n = S.set_nickname(aid, "  J4 baseline  ")
    check("a nickname is set, trimmed", n["nickname"] == "J4 baseline",
          repr(n["nickname"]))
    check("and the automatic name is untouched", n["name"] == rec["name"])

    # -- cite / delete ---------------------------------------------------------
    drift = S.create("drift", {"left": [{"id": aid, "gid": SUBJ["gid"]}],
                               "right": [{"id": aid, "gid": SUBJ["gid"]}],
                               "cue_type": "HighTone_LowTone",
                               "window_kind": "state",
                               "left_label": "Precon", "right_label": "Postcon"},
                     {"schema": "arc.drift/1", "cells": {}},
                     inputs=[{"kind": "artifact", "id": aid, "version": 2,
                              "side": "left"}])
    S.cite(aid, 2, drift["id"], 1)
    S.cite(aid, 2, drift["id"], 1)
    got = S.cited_by(aid)
    check("cite records the citation, once", len(got) == 1, str(got))
    check("cited_by names the citing drift",
          got and got[0]["by_name"] == drift["name"], str(got))
    check("cited_by filters by version",
          len(S.cited_by(aid, 1)) == 0 and len(S.cited_by(aid, 2)) == 1)
    why = raises(lambda: S.delete(aid))
    check("delete is refused while a drift cites a version", why, "")
    check("and the refusal names what cites it",
          isinstance(why, str) and "Precon vs Postcon" in why, str(why))
    check("the refused artifact is not marked deleted",
          not S.get(aid).get("deleted"))
    S.delete(drift["id"])
    check("once the drift is deleted, the circuit can be",
          not raises(lambda: S.delete(aid)) and S.get(aid)["deleted"])
    check("a deleted artifact is not found for its subject",
          S.find("circuit", SUBJ) is None)
    check("deleted artifacts are not listed by default",
          all(r["id"] != aid for r in S.list()))
    check("and its payloads stay on disk", os.path.isfile(snap))

    # -- two machines ----------------------------------------------------------
    subj2 = dict(SUBJ, gid="harness-art-2")
    shards._MACHINE = "machine-a"
    base = S.create("circuit", subj2, circuit_payload())
    bid = base["id"]
    # Machine b works in its own clone, as a colleague does, and its shard
    # arrives afterwards -- the git-pull case, where both machines mint v2
    # without having seen each other's.
    clone = tempfile.mkdtemp(prefix="jarvis-artifacts-check-clone-")
    shutil.copytree(os.path.join(tmp, "artifacts"),
                    os.path.join(clone, "artifacts"))
    shards._MACHINE = "machine-b"
    SBc = A.Artifacts(clone, store)
    SBc.add_version(bid, circuit_payload(scale=5.0), note="from b")
    shards._MACHINE = "machine-a"
    S.add_version(bid, circuit_payload(scale=7.0), note="from a")
    S.set_nickname(bid, "named on a")
    # The pull: b's shard and b's snapshot land beside a's.
    shutil.copy2(os.path.join(clone, "artifacts", "circuit",
                              bid + "@machine-b.json"),
                 os.path.join(tmp, "artifacts", "circuit"))
    for name in os.listdir(os.path.join(clone, "artifacts", "snap", bid)):
        dst = os.path.join(tmp, "artifacts", "snap", bid, name)
        if not os.path.exists(dst):
            shutil.copy2(os.path.join(clone, "artifacts", "snap", bid, name),
                         dst)
    shutil.rmtree(clone, ignore_errors=True)
    shards._MACHINE = "machine-b"
    SB = A.Artifacts(tmp, store)
    shards._MACHINE = "machine-a"
    files = sorted(os.listdir(os.path.join(tmp, "artifacts", "circuit")))
    check("each machine wrote its own shard",
          bid + "@machine-a.json" in files and bid + "@machine-b.json" in files,
          ", ".join(f for f in files if f.startswith(bid)))
    merged = S.get(bid)
    notes = sorted(v.get("note") or "" for v in merged["versions"])
    check("the two machines' shards merge: both v2s kept",
          len(merged["versions"]) == 3 and notes == ["", "from a", "from b"],
          str(notes))
    why = raises(lambda: S.payload(bid, 2))
    check("asking for an ambiguous v2 by number is refused", why, "")
    ids = [v["id"] for v in merged["versions"] if v["v"] == 2]
    check("asking by version id is answered",
          all(S.payload(bid, i) is not None for i in ids))
    check("the nickname from a is seen by b", SB.get(bid)["nickname"]
          == "named on a")

    # -- restart ---------------------------------------------------------------
    S2 = A.Artifacts(tmp, FakeStore())
    check("a fresh store (restart) re-reads everything from disk",
          S2.get(bid) and len(S2.get(bid)["versions"]) == 3
          and S2.get(aid)["deleted"])
    check("and the payloads come back, digest-verified",
          S2.payload(bid, ids[0]) is not None)

    # -- tampering / sync ------------------------------------------------------
    p = S.snap_path(bid, 1, S.get(bid)["versions"][0]["digest"])
    with open(p, "r", encoding="utf-8") as fh:
        body = json.load(fh)
    body["n_pairs"] = 99
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(body, fh)
    check("a payload changed on disk is refused, not served",
          raises(lambda: S.payload(bid, 1)))

    rows = S.records_for_cloud()
    target = next(r for r, _st in rows if r["id"] == bid)
    tmp2 = tempfile.mkdtemp(prefix="jarvis-artifacts-check-b-")
    try:
        shards._MACHINE = "machine-c"
        SC = A.Artifacts(tmp2, FakeStore())
        check("absorb_record adds an unknown artifact",
              SC.absorb_record(dict(target)) == "added")
        check("absorbing it again is a no-op",
              SC.absorb_record(dict(target)) == "same")
        v0 = target["versions"][1]
        payload = S.payload(bid, v0["id"])
        check("absorb_snapshot fills in a missing payload",
              SC.absorb_snapshot(bid, v0["id"], v0["v"], v0["digest"],
                                 payload) == "added")
        check("and is 'already' the second time",
              SC.absorb_snapshot(bid, v0["id"], v0["v"], v0["digest"],
                                 payload) == "already")
        bad = dict(payload, n_pairs=12345)
        got = SC.absorb_snapshot(bid, target["versions"][2]["id"],
                                 target["versions"][2]["v"],
                                 target["versions"][2]["digest"], bad)
        check("a snapshot whose content does not match its digest is a "
              "conflict, reported and not filed",
              str(got).startswith("conflict"), str(got))
    finally:
        shards._MACHINE = "machine-a"
        shutil.rmtree(tmp2, ignore_errors=True)

    sync_checks()

    bad = [r for r in results if not r[1]]
    print("\n%d check(s), %d failed" % (len(results), len(bad)))
    return results


class FakeCloud:
    """The two artifact tables, with the database's own rules: newest
    updated_at wins on `artifacts`, and `artifact_snapshots` refuses
    updates (migration 18's add-only trigger)."""

    def __init__(self):
        self.art, self.snaps, self.requests = {}, {}, 0

    def select_all(self, table, query=""):
        self.requests += 1
        return [dict(r) for r in (self.art.values() if table == "artifacts"
                                  else self.snaps.values())]

    def push(self, rows):
        for r in rows.get("artifacts") or []:
            old = self.art.get(r["id"])
            if not old or r["updated_at"] >= old["updated_at"]:
                self.art[r["id"]] = dict(r)
        for r in rows.get("artifact_snapshots") or []:
            self.snaps.setdefault((r["artifact_id"], r["version_id"]), dict(r))


def _sync_for(store, fake):
    from backend import cloudsync
    s = cloudsync.Sync.__new__(cloudsync.Sync)
    s.artifacts, s.cloud, s.machine = store, fake, shards.machine_id()
    s._art_sent_sig = s._art_pending_sig = None
    return s


def _push(s, fake):
    fake.push(s.rows_artifacts())
    s._art_sent_sig = s._art_pending_sig          # what push() does at the end
    s.artifacts.cloud_dirty = False


def _pull(s, fake):
    s._apply_artifacts(list(fake.art.values()))
    s._apply_artifact_snapshots(list(fake.snaps.values()))


def sync_checks():
    """Two machines, one fake cloud: both mint a v2 offline, and the later
    push overwrites the earlier one's row -- the case a newest-wins record
    loses. Both must end with all three versions and all three payloads."""
    import time as _t
    da = tempfile.mkdtemp(prefix="jarvis-artifacts-sync-a-")
    db = tempfile.mkdtemp(prefix="jarvis-artifacts-sync-b-")
    fake = FakeCloud()
    try:
        subj = dict(SUBJ, gid="s-sync-check")
        shards._MACHINE = "sync-a"
        SA = A.Artifacts(da, FakeStore())
        ca = _sync_for(SA, fake)
        x = SA.create("circuit", subj, circuit_payload())
        _push(ca, fake)
        shards._MACHINE = "sync-b"
        SB = A.Artifacts(db, FakeStore())
        cb = _sync_for(SB, fake)
        _pull(cb, fake)
        check("sync: a pulled artifact arrives with its payload",
              SB.get(x["id"]) and SB.payload(x["id"], 1) is not None)
        shards._MACHINE = "sync-a"
        SA.add_version(x["id"], circuit_payload(scale=2.0), note="a")
        _push(ca, fake)
        _t.sleep(1.1)                         # b's push is strictly later
        shards._MACHINE = "sync-b"
        SB.add_version(x["id"], circuit_payload(scale=3.0), note="b")
        _push(cb, fake)
        check("sync: the later push really did overwrite the earlier row",
              len(fake.art[x["id"]]["versions"]) == 2)
        for _round in range(3):
            shards._MACHINE = "sync-a"
            _pull(ca, fake)
            _push(ca, fake)
            shards._MACHINE = "sync-b"
            _pull(cb, fake)
            _push(cb, fake)
        va = SA.get(x["id"])["versions"]
        vb = SB.get(x["id"])["versions"]
        check("sync: both machines end with all three versions",
              len(va) == 3 and len(vb) == 3, "%d / %d" % (len(va), len(vb)))
        check("sync: and every payload, on both",
              all(SA.payload(x["id"], v["id"]) is not None for v in va)
              and all(SB.payload(x["id"], v["id"]) is not None for v in vb))
        before = fake.requests
        shards._MACHINE = "sync-b"
        got = cb.rows_artifacts()
        check("sync: a quiet push sends nothing and asks nothing",
              not got["artifacts"] and not got["artifact_snapshots"]
              and fake.requests == before,
              "%d requests" % (fake.requests - before))
        # A snapshot that arrives altered is a conflict, not a file.
        vid = va[-1]["id"]
        key = (x["id"], vid)
        bad = dict(fake.snaps[key],
                   payload=dict(fake.snaps[key]["payload"], n_pairs=77))
        dc = tempfile.mkdtemp(prefix="jarvis-artifacts-sync-c-")
        try:
            shards._MACHINE = "sync-c"
            SC = A.Artifacts(dc, FakeStore())
            cc = _sync_for(SC, fake)
            cc.snapshot_conflicts = []
            cc._apply_artifacts(list(fake.art.values()))
            cc._apply_artifact_snapshots([bad])
            check("sync: an altered payload is reported as a conflict",
                  any("conflict" in c for c in cc.snapshot_conflicts),
                  str(cc.snapshot_conflicts))
            check("sync: and is not filed",
                  SC.payload(x["id"], vid) is None)
        finally:
            shutil.rmtree(dc, ignore_errors=True)
    finally:
        shards._MACHINE = "machine-a"
        shutil.rmtree(da, ignore_errors=True)
        shutil.rmtree(db, ignore_errors=True)


# ---------------------------------------------------------------------------
# Negative controls: break the store, require the checks to notice.
# ---------------------------------------------------------------------------
def negative_controls():
    import builtins                                   # noqa: F401
    controls = []

    def expect_fail(label, names, patch, unpatch):
        patch()
        try:
            got = run()
        except Exception as exc:                          # noqa: BLE001
            got = [(n, False, "threw %s" % exc) for n in names]
        finally:
            unpatch()
        by = {n: ok for n, ok, _d in got}
        caught = [n for n in names if by.get(n) is False]
        controls.append((label, len(caught) == len(names), names, caught))

    real_digest = A.digest
    expect_fail("digest ignores content",
                ["a different payload makes v2"],
                lambda: setattr(A, "digest", lambda p: "000000000000"),
                lambda: setattr(A, "digest", real_digest))

    real_active = A.Artifacts._active_cites
    expect_fail("delete ignores citations",
                ["delete is refused while a drift cites a version"],
                lambda: setattr(A.Artifacts, "_active_cites",
                                lambda self, rec, *a, **k: []),
                lambda: setattr(A.Artifacts, "_active_cites", real_active))

    real_snap = A.Artifacts._write_snap

    def rewriting(self, aid, v, dig, payload):
        path = self.snap_path(aid, v, dig)
        if os.path.isfile(path):
            os.remove(path)
        return real_snap(self, aid, v, dig, payload)
    import time as _t
    real_sleep = _t.sleep

    def patched():
        A.Artifacts._write_snap = rewriting
        # Windows mtimes are coarse; make a rewrite visible.
        A.Artifacts._orig_add = A.Artifacts.add_version

        def slow_add(self, *a, **k):
            real_sleep(0.05)
            return A.Artifacts._orig_add(self, *a, **k)
        A.Artifacts.add_version = slow_add
    def unpatched():
        A.Artifacts._write_snap = real_snap
        A.Artifacts.add_version = A.Artifacts._orig_add
    expect_fail("snapshots are rewritten",
                ["the snapshot is not rewritten by a confirmation"],
                patched, unpatched)

    real_book = A.Artifacts.book

    def lww_book(self, kind):
        b = real_book(self, kind)
        b.spec["versions"] = shards.LWW
        return b
    expect_fail("versions merged last-write-wins",
                ["the two machines' shards merge: both v2s kept"],
                lambda: setattr(A.Artifacts, "book", lww_book),
                lambda: setattr(A.Artifacts, "book", real_book))

    real_fp = A.Artifacts.cloud_fingerprint
    expect_fail("sync compares nothing (every row looks current)",
                ["sync: both machines end with all three versions"],
                lambda: setattr(A.Artifacts, "cloud_fingerprint",
                                lambda self, rec: "same"),
                lambda: setattr(A.Artifacts, "cloud_fingerprint", real_fp))

    print("\n== negative controls ==")
    for label, ok, names, caught in controls:
        print(("ok    " if ok else "FAIL  ") + "broken store (%s) is caught by: "
              % label + "; ".join(names))
    return all(c[1] for c in controls)


if __name__ == "__main__":
    got = run()
    ok = all(r[1] for r in got)
    if "--break" in sys.argv:
        ok = negative_controls() and ok
        # And the real store once more, so the last word is about it.
        got = run()
        ok = ok and all(r[1] for r in got)
    sys.exit(0 if ok else 1)
