# -*- coding: utf-8 -*-
"""Braces' Many, as one batch on the server (2026-10-14).

    python tools/check_braces_batch.py           # here, and the cluster stood in for
    python tools/check_braces_batch.py --vacc    # and one real set on the VACC

What used to go wrong: Many was the browser asking for one run at a time and
waiting on each, so it ran only while the panel stayed open, and it offered
only what this computer could open -- on a laptop where every recording is
on the VACC, nothing could be ticked and nothing was ever sent. Now a batch
is one job (`/api/braces/batch`): the sets this computer has are aligned
here, the ones only the cluster has go up as one array, and both halves run
at once. This checks, on this machine's real bank and recordings:

  * a set sent in a batch is read, filed as a proposal, and its row says
    where it landed -- under the same question hash the one-set run uses;
  * sent again with the same settings it is opened, not read again; with
    `force` it is read again;
  * a set that cannot run fails on its own row, with the reason, and the
    batch goes on;
  * the cluster's half: a set prepared for the VACC becomes an array task
    whose member is the SET, and the answer that comes back is filed --
    live, and again from the run record alone, as after a restart;
  * `/api/braces/inflight` finds the batch again, members and all;
  * with --vacc, one real set only the cluster has goes up, runs on a
    node, and comes back filed.

Nothing real is written: proposals go to a temp folder, and the activity
log is stood in for. The bank is only read.
"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import bracesset, store  # noqa: E402

FAILED = []
VACC = "--vacc" in sys.argv


def check(name, ok, detail=""):
    print("  %-72s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:600])
    if not ok:
        FAILED.append(name)


def wait(A, job_id, limit_s, say_every=30):
    t0 = time.time()
    last = 0
    while True:
        job = A.cfcmod.get(job_id)
        snap = job.snapshot() if job else {"status": "gone"}
        if snap["status"] != "running":
            return snap
        if time.time() - t0 > limit_s:
            return snap
        if time.time() - last > say_every:
            last = time.time()
            rows = ", ".join("%s:%s" % (m["label"], m["status"])
                             for m in (snap.get("members") or []))
            print("      ... %3d s  %s" % (time.time() - t0, rows[:200]))
        time.sleep(1.0)


def member(snap, mid):
    return next((m for m in (snap.get("members") or []) if m["id"] == mid), {})


def candidates(A, c):
    got = c.get("/api/braces/candidates").get_json() or {}
    sets = [s for s in (got.get("sets") or []) if (s.get("n_good") or 0) > 0]
    index = A._incisor_registry_index()
    here, away = [], []
    for s in sets:
        row = index.get(s.get("gid")) or {}
        (here if A._local_path_of(row) else away).append(s)
    here.sort(key=lambda s: s.get("n_good") or 0)
    away.sort(key=lambda s: s.get("n_good") or 0)
    return here, away


def main():
    from backend import app as A
    tmp = tempfile.mkdtemp(prefix="jarvis-brbatch-")
    real = {"BRACES": A.BRACES, "record_activity": A.STORE.record_activity,
            "_vacc_run_array": A._vacc_run_array,
            "_braces_prepare": A._braces_prepare,
            "_braces_vacc_task": A._braces_vacc_task,
            "push_code": A.vaccmod.push_code}
    try:
        A.BRACES = bracesset.BracesSets(tmp, store.Store(tmp, auto_stage=False))
        A.STORE.record_activity = lambda *a, **k: None
        c = A.app.test_client()
        here, away = candidates(A, c)
        print("\n%d set(s) this computer can read, %d it cannot"
              % (len(here), len(away)))
        if not here:
            check("a set this computer can read, to align here", False,
                  "none in this bank")
            return

        # ---- here ------------------------------------------------------
        one = here[0]
        print("\na batch of one, here: %s (%d spikes)"
              % (one.get("session_label") or one.get("name"), one["n_good"]))
        body = {"entries": [{"id": one["id"], "from_version": None}],
                "measure": "csd", "window_ms": 100}
        r = c.post("/api/braces/batch", json=body).get_json() or {}
        check("it is accepted as one job, with a row for the set",
              r.get("ok") and (r.get("job") or {}).get("id"), r)
        jid = (r.get("job") or {}).get("id")
        fl = c.get("/api/braces/inflight").get_json() or {}
        mine = next((f for f in fl.get("jobs") or [] if f["id"] == jid), None)
        check("/api/braces/inflight finds it, with its members",
              mine and [m["id"] for m in mine["members"]] == [one["id"]], fl)
        snap = wait(A, jid, 900)
        m = member(snap, one["id"])
        check("the batch finishes", snap["status"] == "done", snap.get("error"))
        check("the set landed, aligned here, with its proposal named",
              m.get("status") == "done" and m.get("set_id")
              and m.get("where") == "here" and not m.get("cached"), m)
        filed = A.BRACES.get(m.get("set_id")) if m.get("set_id") else None
        check("and the proposal is filed, by whoever sent it",
              filed and filed.get("entry_id") == one["id"]
              and (filed.get("created") or {}).get("by"), filed and filed.get("created"))
        prep = real["_braces_prepare"](dict(body, entry_id=one["id"],
                                            from_version=None))
        check("under the question hash the one-set run asks",
              filed and (filed.get("params") or {}).get("request_hash")
              == prep["rq_hash"],
              filed and (filed.get("params") or {}).get("request_hash"))
        check("and the one-set run opens it rather than reading again",
              (c.post("/api/braces/run", json=dict(
                  body, entry_id=one["id"], from_version=None))
               .get_json() or {}).get("existing", {}).get("set_id")
              == m.get("set_id"))

        print("\nsent again: opened, not read; forced: read")
        n0 = len(A.BRACES.all())
        r2 = c.post("/api/braces/batch", json=body).get_json() or {}
        s2 = wait(A, (r2.get("job") or {}).get("id"), 120)
        m2 = member(s2, one["id"])
        check("the same question is answered by the alignment already made",
              m2.get("status") == "done" and m2.get("cached")
              and m2.get("set_id") == m.get("set_id"), m2)
        check("and nothing new is filed", len(A.BRACES.all()) == n0)
        r3 = c.post("/api/braces/batch", json=dict(body, force=True)).get_json() or {}
        s3 = wait(A, (r3.get("job") or {}).get("id"), 900)
        m3 = member(s3, one["id"])
        check("forced, it is read again and filed anew",
              m3.get("status") == "done" and not m3.get("cached")
              and m3.get("set_id") and m3.get("set_id") != m.get("set_id"), m3)

        print("\na set that cannot run fails on its own row")
        r4 = c.post("/api/braces/batch", json={
            "entries": [{"id": "nosuchentry0"}, {"id": one["id"]}],
            "measure": "csd", "window_ms": 100}).get_json() or {}
        s4 = wait(A, (r4.get("job") or {}).get("id"), 300)
        bad = member(s4, "nosuchentry0")
        check("named, with the reason", bad.get("status") == "failed"
              and "No bank entry" in (bad.get("error") or ""), bad)
        check("and the batch goes on to the next",
              member(s4, one["id"]).get("status") == "done"
              and s4["status"] == "done", s4.get("members"))
        r5 = c.post("/api/braces/batch", json={"entries": []})
        check("an empty batch is refused with a sentence",
              r5.status_code == 400 and "Tick" in (r5.get_json() or {}).get("error", ""))

        # ---- the cluster, stood in for ------------------------------------
        print("\nthe cluster's half, stood in for")
        answer = {"out": dict(filed.get("summary") or {}),
                  "rows": list(filed.get("rows") or []),
                  "params": {k: v for k, v in (filed.get("params") or {}).items()
                             if k not in ("request_hash", "request")},
                  "n_channels": 64}
        made = {}

        def fake_prepare(b):
            p = real["_braces_prepare"](b)
            p["where"] = "vacc"
            return p

        def fake_task(p):
            rec = p["rec"]
            spec = dict(p["spec"], path="vacc:" + str(rec.get("gid")))
            return {"gid": rec.get("gid"), "member": rec["id"],
                    "label": A._braces_label(rec), "sess": None,
                    "report": None, "key": None, "spec_local": spec,
                    "spec_remote": dict(spec, path="/netfiles/zz/copy"),
                    "tool_steps": list(p["steps"]), "seconds": 60.0,
                    "megasamples": 1.0, "state": "native",
                    "resume": {"braces": A._braces_resume_parts(p)}}

        def fake_array(job, tasks, failed, concurrency=None, tool=None,
                       adopt=None, runlog=None, record=None, deadline_s=None):
            made["tool"], made["cap"] = tool, concurrency
            made["tasks"] = tasks
            made["record"] = record
            for t in tasks:
                job.member(t["member"], status="running", step="on a node")
                adopt(t, dict(answer, out=dict(answer["out"]),
                              computed_on={"kind": "vacc", "slurm_id": "9_0"}))
                job.member(t["member"], status="done", step=None)
            return len(tasks), failed

        A._braces_prepare = fake_prepare
        A._braces_vacc_task = fake_task
        A._vacc_run_array = fake_array
        A.vaccmod.push_code = lambda cfg, app_dir: None
        n0 = len(A.BRACES.all())
        r6 = c.post("/api/braces/batch", json=dict(body, force=True)).get_json() or {}
        s6 = wait(A, (r6.get("job") or {}).get("id"), 300)
        m6 = member(s6, one["id"])
        check("a set only the cluster has goes up as an array task",
              made.get("tool") == "braces" and len(made.get("tasks") or []) == 1,
              made)
        check("whose member is the SET, not the recording",
              (made.get("tasks") or [{}])[0].get("member") == one["id"])
        check("on a netfiles copy the array is capped",
              made.get("cap") == A.INCISOR_NETFILES_CAP, made.get("cap"))
        check("with the batch's job id in its run record, so a restart "
              "does not adopt it twice",
              (made.get("record") or {}).get("job_id") == r6["job"]["id"])
        check("its answer is filed, and the row names the proposal",
              m6.get("status") == "done" and m6.get("set_id")
              and m6.get("where") == "vacc", m6)
        f6 = A.BRACES.get(m6.get("set_id")) if m6.get("set_id") else None
        check("filed as computed on the VACC, under the same question",
              f6 and (f6.get("params") or {}).get("computed_on", {})
              .get("kind") == "vacc"
              and (f6.get("params") or {}).get("request_hash") == prep["rq_hash"],
              f6 and f6.get("params"))
        A._file_batch_answer("braces", made["tasks"][0],
                             dict(answer, out=dict(answer["out"])))
        check("and after a restart, from the run record alone, it is filed "
              "the same way", len(A.BRACES.all()) == n0 + 2
              and A.BRACES.all()[0].get("params", {}).get("request_hash")
              == prep["rq_hash"])
        A._braces_prepare = real["_braces_prepare"]
        A._braces_vacc_task = real["_braces_vacc_task"]
        A._vacc_run_array = real["_vacc_run_array"]
        A.vaccmod.push_code = real["push_code"]

        # ---- the cluster, for real ----------------------------------------
        if VACC:
            # One the cluster can read: only there if there is one, else one
            # this computer has too, sent there on purpose (`where: vacc`).
            pick, sent_where = None, None
            for s in [x for x in away if x.get("gid")] + here[:40]:
                try:
                    A._vacc_place_for_gid(s["gid"])
                    pick = s
                    sent_where = "vacc" if s in here else None
                    break
                except Exception:                        # noqa: BLE001
                    continue
            print("\none real set on the VACC: %s%s"
                  % ((pick or {}).get("session_label") or "none found",
                     " (on this computer too, sent there on purpose)"
                     if sent_where else ""))
            if not pick:
                check("a set the cluster can read, to send", False, away[:3])
            else:
                # Forced: the same question was answered here above, and
                # this is about the cluster reading it, not about the cache.
                rb = {"entries": [{"id": pick["id"], "from_version": None}],
                      "measure": "csd", "window_ms": 100, "force": True}
                if sent_where:
                    rb["where"] = sent_where
                rv = c.post("/api/braces/batch", json=rb).get_json() or {}
                sv = wait(A, (rv.get("job") or {}).get("id"), 1800)
                mv = member(sv, pick["id"])
                check("it went up, ran on a node and came back",
                      mv.get("status") == "done" and mv.get("set_id")
                      and mv.get("where") == "vacc" and not mv.get("cached"),
                      (sv.get("status"), mv, sv.get("error")))
                fv = A.BRACES.get(mv.get("set_id")) if mv.get("set_id") else None
                check("filed here as computed on the cluster",
                      fv and ((fv.get("params") or {}).get("computed_on") or {})
                      .get("slurm_id"), fv and fv.get("params", {}).get("computed_on"))
                print("      %s" % ((fv or {}).get("summary") or {}).get("n"))
    finally:
        A.BRACES = real["BRACES"]
        A.STORE.record_activity = real["record_activity"]
        A._vacc_run_array = real["_vacc_run_array"]
        A._braces_prepare = real["_braces_prepare"]
        A._braces_vacc_task = real["_braces_vacc_task"]
        A.vaccmod.push_code = real["push_code"]
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
    print("\n%s" % ("all passed" if not FAILED else
                    "%d FAILED:\n  " % len(FAILED) + "\n  ".join(FAILED)))
    sys.exit(1 if FAILED else 0)
