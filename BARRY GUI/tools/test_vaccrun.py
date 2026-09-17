# -*- coding: utf-8 -*-
"""Does an offloaded run behave like an ordinary one?

The claim VACC Mode rests on is that a run on the cluster is a `cfc.Job` with
a different `work()` -- so the progress card, the poll endpoint, Cancel and
the result all keep working without being told anything. This drives that
claim through a fake login node: submit, queue, run, finish, fetch, and every
way it can end badly.

Three things here cannot be tested any other way, and all three are the kind
that cost a six-hour run when they are wrong:

  * Cancel must `scancel`. `job.cancel()` only sets a flag, and `Canceled`
    comes out of `tick` -- so a `scancel` written after the polling loop is
    skipped by exactly the exception that means somebody pressed Cancel, and
    the job runs to completion on a shared cluster with nothing pointing at
    it.

  * The params hash must come from the LOCAL spec. The remote spec differs by
    one field, and hashing that one instead writes answers under a name no
    local run ever looks for: resume stops working and every screen still
    looks right.

  * A job in neither squeue nor sacct is the accounting database lagging, not
    a job that vanished.

    python tools/test_vaccrun.py

No cluster, no network, no account.
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import cfc, vacc, vaccrun  # noqa: E402

FAILED = []
CFG = {"netid": "tester", "host": "login.vacc.uvm.edu",
       "workspace": "/gpfs1/home/t/e/tester/jarvis",
       "partition": "general", "modules": [], "env": "", "path_map": []}


def check(name, ok, detail=""):
    print("  %-62s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail))
    if not ok:
        FAILED.append(name)


class FakeCluster(object):
    """A login node that does whatever the test says.

    `states` is the sequence squeue/sacct report, one per poll, so a whole
    job lifetime is a list.
    """

    def __init__(self, states, result=None, jobid="778899"):
        self.states = list(states)
        self.result = result if result is not None else {"numbers": [1, 2, 3]}
        self.jobid = jobid
        self.asked = []
        self.scancelled = []

    def __call__(self, remote_command, stdin=None, timeout=45):
        text = (stdin if stdin is not None else remote_command) or ""
        self.asked.append(text)
        if "sbatch" in text:
            return self.jobid + "\n"
        if "scancel" in text:
            self.scancelled.append(text)
            return ""
        if "squeue" in text:
            state = self.states.pop(0) if self.states else "COMPLETED"
            if state is None:                    # in neither: the lag window
                return "--\n"
            if state in ("RUNNING", "PENDING"):
                return "%s %s\n--\n" % (self.jobid, state)
            # JobID then JobIDRaw, as the real sacct is asked for them. They
            # differ for array tasks -- see the array check in vacc_check.py.
            return "--\n%s|%s|%s|00:03:00|4096K\n" % (self.jobid, self.jobid,
                                                      state)
        if "cat" in text and "result.json" in text:
            return json.dumps(self.result)
        return ""


def run_job(fake, spec_local, remote_path, plan=None, poll_fast=True):
    """Build a VaccRun on the fake and drive it through cfc.start."""
    if poll_fast:
        for k in vaccrun.POLL:
            vaccrun.POLL[k] = 0.01
    r = vaccrun.VaccRun(CFG, "incisor", spec_local, remote_path,
                        plan=plan or {"seconds": 120}, ssh=fake)
    job = cfc.start({"path": spec_local.get("path")},
                    vaccrun.steps(), r.work, 1.0, "vacc:netfiles")
    t0 = time.time()
    while job.status == "running" and (time.time() - t0) < 20:
        time.sleep(0.01)
    return r, job


def main():
    import tempfile
    cfc.configure(tempfile.mkdtemp(prefix="barry_vaccrun_"))

    print("\nthe stages exist, or nothing would show progress")
    names = [n for n, _ in cfc.STAGES]
    for s in ("vacc stage", "vacc queue", "vacc fetch"):
        check("%-12s is a registered stage" % s, s in names)
    check("queue wait is never learned as a rate",
          "vacc queue" in cfc._NOLEARN)
    check("and none of them scale with the recording",
          all(s in cfc._FLAT for s in ("vacc stage", "vacc queue", "vacc fetch")))

    print("\na run that works")
    fake = FakeCluster(["PENDING", "RUNNING", "COMPLETED"])
    r, job = run_job(fake, {"path": "Y:\\x\\m1", "height_sd": 4.5},
                     "/netfiles/bigdata_jbarry/x/m1")
    check("it finished", job.status == "done", job.status + " " + str(job.error))
    check("the answer came back", (job.result or {}).get("numbers") == [1, 2, 3],
          str(job.result))
    check("the slurm id was kept", r.slurm_id == "778899", str(r.slurm_id))
    check("nothing was cancelled", not fake.scancelled, str(fake.scancelled))

    print("\nsubmitting: no path on a command line, ever")
    sub = [a for a in fake.asked if "sbatch" in a][0]
    check("the spec went in on stdin as JSON", '"height_sd": 4.5' in sub
          or '"height_sd":4.5' in sub, sub[:120])
    check("the job is named after its run id",
          "--job-name=" + r.rid in sub, sub[:200])
    check("a --time was set, never left to the 30-minute default",
          "--time=" in sub, sub[:200])
    check("and a partition with it", "--partition=" in sub)

    print("\nthe two specs stay apart")
    check("the local spec keeps the local path",
          r.spec_local["path"] == "Y:\\x\\m1", r.spec_local["path"])
    check("the remote spec differs in the path and nothing else",
          r.spec_remote["path"] == "/netfiles/bigdata_jbarry/x/m1"
          and r.spec_remote["height_sd"] == r.spec_local["height_sd"],
          str(r.spec_remote))
    check("everything else about them is identical",
          {k: v for k, v in r.spec_local.items() if k != "path"}
          == {k: v for k, v in r.spec_remote.items() if k != "path"})

    print("\nand the answer comes home in this machine's terms")
    fake = FakeCluster(["COMPLETED"], result={
        "path": "/netfiles/bigdata_jbarry/x/m1",
        "where": {"file": "/netfiles/bigdata_jbarry/x/m1/CSC1.ncs"},
        "list": ["/netfiles/bigdata_jbarry/x/m1/a", "untouched"],
    })
    r, job = run_job(fake, {"path": "Y:\\x\\m1"},
                     "/netfiles/bigdata_jbarry/x/m1")
    out = job.result or {}
    check("the top-level path is local again", out.get("path") == "Y:\\x\\m1",
          str(out.get("path")))
    check("nested ones too",
          out.get("where", {}).get("file") == "Y:\\x\\m1/CSC1.ncs",
          str(out.get("where")))
    check("inside lists as well", out.get("list", [None])[0] == "Y:\\x\\m1/a",
          str(out.get("list")))
    check("and anything that was not a remote path is left alone",
          out.get("list", [None, None])[1] == "untouched")
    check("it records that the cluster computed it",
          (out.get("computed_on") or {}).get("kind") == "vacc"
          and (out.get("computed_on") or {}).get("slurm_id") == "778899",
          str(out.get("computed_on")))

    print("\nhow it ends badly")
    for state, want, phrase in (
            ("TIMEOUT", "failed", "more time than it was given"),
            ("OUT_OF_MEMORY", "failed", "out of memory"),
            ("NODE_FAIL", "failed", "cluster's problem"),
            ("FAILED", "failed", "failed on the cluster")):
        fake = FakeCluster(["RUNNING", state])
        r, job = run_job(fake, {"path": "D:\\x"}, "/gpfs2/scratch/x")
        check("%-14s ends the job" % state, job.status == want,
              job.status + " " + str(job.error))
        check("  and says what happened in words",
              phrase in (job.error or "").lower(), str(job.error))
        check("  and stops the job on the cluster",
              any("scancel" in s for s in fake.scancelled), str(fake.scancelled))

    print("\na cancel on the cluster is a cancel here, not a failure")
    fake = FakeCluster(["RUNNING", "CANCELLED by 1234"])
    r, job = run_job(fake, {"path": "D:\\x"}, "/gpfs2/scratch/x")
    check("it lands in the canceled bucket", job.status == "canceled",
          job.status + " " + str(job.error))

    print("\npressing Cancel here stops it there")
    # The one that matters: Canceled comes out of `tick`, so a scancel written
    # after the loop would be skipped by the very exception it must handle.
    fake = FakeCluster(["RUNNING"] * 400)
    for k in vaccrun.POLL:
        vaccrun.POLL[k] = 0.02
    r = vaccrun.VaccRun(CFG, "incisor", {"path": "D:\\x"}, "/gpfs2/scratch/x",
                        plan={"seconds": 60}, ssh=fake)
    job = cfc.start({"path": "D:\\x"}, vaccrun.steps(), r.work, 1.0,
                    "vacc:netfiles")
    t0 = time.time()
    while r.slurm_id is None and (time.time() - t0) < 5:
        time.sleep(0.01)
    job.cancel()
    t0 = time.time()
    while job.status == "running" and (time.time() - t0) < 10:
        time.sleep(0.01)
    check("the job reports canceled", job.status == "canceled", job.status)
    check("and the cluster was told, from the finally",
          any("scancel" in s for s in fake.scancelled), str(fake.scancelled))
    check("by id, since we had one",
          any("778899" in s for s in fake.scancelled), str(fake.scancelled))

    print("\nthe accounting lag is not a vanished job")
    # Two polls where the job is in neither, then it turns up completed.
    fake = FakeCluster([None, None, "COMPLETED"])
    r, job = run_job(fake, {"path": "D:\\x"}, "/gpfs2/scratch/x")
    check("it waits the lag out rather than failing", job.status == "done",
          job.status + " " + str(job.error))

    print("\nand a job that really is gone eventually says so")
    saved = vacc.LAG_GRACE_S
    vacc.LAG_GRACE_S = 0.05
    try:
        fake = FakeCluster([None] * 200)
        r, job = run_job(fake, {"path": "D:\\x"}, "/gpfs2/scratch/x")
        check("after the grace period it fails", job.status == "failed",
              job.status)
        check("and says the result never arrived",
              "no result arrived" in (job.error or "").lower(), str(job.error))
    finally:
        vacc.LAG_GRACE_S = saved

    print("\nlearned rates still go to the cluster's own keys")
    check("nothing the cluster taught landed on a bare stage name",
          all(" @ " in k for k in cfc._RATES
              if k.startswith("vacc ") and cfc._RATES[k] and k not in
              ("vacc stage", "vacc queue", "vacc fetch")),
          str([k for k in cfc._RATES if k.startswith("vacc ")]))
    check("the local ds detect rate was never touched by any of this",
          cfc._RATES["ds detect"] == 0.15, str(cfc._RATES["ds detect"]))

    print()
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
