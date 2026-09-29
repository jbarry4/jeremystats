# -*- coding: utf-8 -*-
"""A restart picks up the Incisor and Doppler batches it left running. Offline.

    python tools/test_vaccresume.py

A restart used to orphan every Incisor and Doppler batch in flight: the
polling thread died with the process, nothing had written the job down, and
the answers sat in scratch until the purge took them. Now each batch writes
a run record, and start-up re-attaches (`_resume_vacc_batches`).

Offline: the run records are in a temp folder, the login node is a fake that
reports the array task done and hands back its answer, and filing is
captured rather than written -- no vault, no cache, no registry is touched.
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import app as appmod, vacc, vaccrun  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-66s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


class FakeArray(object):
    """A login node on which array `555000` has finished task 0."""

    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def __call__(self, cmd, stdin=None, timeout=45):
        text = (stdin if stdin is not None else cmd) or ""
        self.asked.append(text)
        if "sacct" in text:
            return "555000_0|COMPLETED\n--\nresult_0.json\n"
        if "result_" in text and "cat" in text:
            return json.dumps(self.answer)
        return ""


def main():
    tmp = tempfile.mkdtemp(prefix="zz-vaccruns-")
    log = vaccrun.RunLog(tmp)
    cfg = {"netid": "zztester", "host": "login.vacc.uvm.edu",
           "workspace": "/users/z/z/zztester/jarvis", "path_map": []}

    rid = vacc.new_rid()
    log.write({
        "rid": rid, "kind": "array", "tool": "doppler", "array_id": "555000",
        "workspace": "/users/z/z/zztester/jarvis/runs/" + rid,
        "submitted_at": time.time() - 60, "status": "submitted",
        "gids": ["zz-gid"], "taken": [], "record": {"tool": "doppler"},
        "jobs": [{"gid": "zz-gid", "label": "zz m1 s1",
                  "spec_local": {"path": "X:/zz/m1/s1"},
                  "spec_remote": {"path": "/gpfs2/zz/m1/s1"},
                  "resume": {"key": "zz-key-1"}}],
    })
    other = vacc.new_rid()
    log.write({"rid": other, "kind": "array", "tool": "circuit",
               "array_id": "1", "jobs": [], "status": "submitted"})

    filed = []
    real = {
        "VACC_RUNLOG": appmod.VACC_RUNLOG,
        "_session_for": appmod._session_for,
        "_doppler_remember": appmod._doppler_remember,
        "cache_put": appmod.dopplermod.cache_put,
    }
    real_load = vacc.load_config
    real_poll = dict(vaccrun.POLL)
    appmod.VACC_RUNLOG = log
    appmod._VACC_RESUMED.update(done=False, jobs=[])
    appmod._session_for = lambda path, *a, **k: ({"path": path}, None)
    appmod._doppler_remember = lambda sess, spec, key, out: filed.append(
        ("remember", sess.get("gid"), spec.get("path"), key, out))
    appmod.dopplermod.cache_put = lambda key, out: filed.append(("cache", key))
    vacc.load_config = lambda logs_dir: dict(cfg)
    for k in vaccrun.POLL:
        vaccrun.POLL[k] = 0.01
    try:
        print("\na batch a previous process left running")
        fake = FakeArray({"n": 3, "events": []})
        jobs = appmod._resume_vacc_batches(ssh=fake)
        check("start-up adopts it", len(jobs) == 1, jobs)
        check("only Incisor and Doppler records; Circuit resumes its own",
              all("circuit" not in str(j.spec) for j in jobs))
        t0 = time.time()
        while jobs and jobs[0].status == "running" and time.time() - t0 < 20:
            time.sleep(0.02)
        check("it finishes", jobs and jobs[0].status == "done",
              jobs and (jobs[0].status, jobs[0].error))
        check("the answer is filed into the cache under its key",
              ("cache", "zz-key-1") in filed, filed)
        rem = [f for f in filed if f[0] == "remember"]
        check("and remembered, on the recording rebuilt from its own spec",
              rem and rem[0][1] == "zz-gid" and rem[0][2] == "X:/zz/m1/s1"
              and rem[0][4].get("n") == 3, rem)
        check("stamped with where it was computed, and by which slurm task",
              rem and (rem[0][4].get("computed_on") or {}).get("kind") == "vacc"
              and rem[0][4]["computed_on"].get("slurm_id") == "555000_0", rem)
        rec = log.get(rid)
        check("its run record is closed", rec and rec.get("status") == "done",
              rec and rec.get("status"))
        check("the Circuit record is left for Circuit",
              (log.get(other) or {}).get("status") == "submitted")
        again = appmod._resume_vacc_batches(ssh=FakeArray({}))
        check("it runs once per process", again == jobs)
    finally:
        appmod.VACC_RUNLOG = real["VACC_RUNLOG"]
        appmod._session_for = real["_session_for"]
        appmod._doppler_remember = real["_doppler_remember"]
        appmod.dopplermod.cache_put = real["cache_put"]
        vacc.load_config = real_load
        vaccrun.POLL.update(real_poll)

    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
