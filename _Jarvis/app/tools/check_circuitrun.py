# -*- coding: utf-8 -*-
"""Does the Circuit backend do what arc_contracts.md section 6 says?

    python tools\\check_circuitrun.py            everything below except VACC
    python tools\\check_circuitrun.py --vacc     plus a real cluster smoke run

Three parts.

1. The VACC reliability fixes, against a fake login node and a fake clock
   (no network, and a thirty-minute outage takes a millisecond):
     fix 1  a flaky poll is retried and never cancels a healthy job
            -- with a negative control: retrying switched off, the same
            fake fails the run and scancels it, which is the old bug;
     fix 2  an ssh error in an array poll is retried; an array that really
            fails is cancelled;
     fix 3  a task that COMPLETED with no answer, or that sacct never
            reports, is failed with a sentence after its grace; a pending
            range is not "never reported"; the batch has a deadline;
     fix 4  a run written down at submit is picked up by a NEW RunLog (a
            restart), polled without re-submitting, fetched and filed.

2. Real data through Flask's test client: plan -> run -> poll the cfc job
   (pairs land one by one) -> the artifact exists with the right subject,
   inputs and digest; a second identical run computes nothing and makes NO
   new version (confirmed); a run at other parameters makes version 2.
   Negative controls for the cache (a refused cache file is recomputed; the
   hash moves with bad channels and histology) and for the version rule.

   Harnesses restore, never clear: the per-pair cache is pointed at a
   temporary directory for the run, and every artifact this makes is
   deleted (ARTIFACTS.delete) and then erased, in a finally. A recording
   that already has a real circuit artifact is never used. Nothing is
   written to the Event Bank.

3. (--vacc) A real cluster run of the `circuit` tool. See `vacc_smoke`.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import threading
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "tools"))
os.chdir(APP)

from backend import cfc, circuit, vacc, vaccrun  # noqa: E402

FAILED = []
PASSED = []
SCRATCH = os.environ.get("CIRCUIT_SEED_DIR") or os.path.join(
    tempfile.gettempdir(), "claude",
    "c--Users-Z390-Desktop-jeremystats",
    "9d4ef501-267d-40a5-ac8e-0b4c4f8457cc", "scratchpad")
CFG = {"netid": "tester", "host": "login.vacc.uvm.edu",
       "workspace": "/gpfs1/home/t/e/tester/jarvis",
       "partition": "general", "modules": [], "env": "", "path_map": []}


def check(name, ok, detail=""):
    print("  %-66s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:600])
    (PASSED if ok else FAILED).append(name)
    return ok


# ==========================================================================
# Fakes
# ==========================================================================
class Clock(object):
    """time that moves only when something sleeps."""

    def __init__(self):
        self.t = 1.0e9

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += float(s)


class FakeSingle(object):
    """One job. `polls` is a list; each item is a state word, None for
    'in neither squeue nor sacct', or an Exception to raise."""

    def __init__(self, polls, result=None, jobid="778899"):
        self.polls = list(polls)
        self.result = result if result is not None else {"numbers": [1]}
        self.jobid = jobid
        self.asked, self.scancelled = [], []

    def __call__(self, cmd, stdin=None, timeout=45):
        text = (stdin if stdin is not None else cmd) or ""
        self.asked.append(text)
        if "sbatch" in text:
            return self.jobid + "\n"
        if "scancel" in text:
            self.scancelled.append(text)
            return ""
        if "squeue" in text:
            st = self.polls.pop(0) if self.polls else "COMPLETED"
            if isinstance(st, Exception):
                raise st
            if st is None:
                return "--\n"
            if st in ("RUNNING", "PENDING"):
                return "%s %s\n--\n" % (self.jobid, st)
            return "--\n%s|%s|%s|00:01:00|1K\n" % (self.jobid, self.jobid, st)
        if "result.json" in text:
            return json.dumps(self.result)
        return ""


class FakeArray(object):
    """An array. `polls` is a list of (sacct_rows, listing) or Exceptions;
    the last one repeats. `results` maps task index to its answer."""

    def __init__(self, polls, results=None, array_id="555000"):
        self.polls = list(polls)
        self.results = results or {}
        self.array_id = array_id
        self.asked, self.scancelled, self.n_poll = [], [], 0

    def __call__(self, cmd, stdin=None, timeout=45):
        text = (stdin if stdin is not None else cmd) or ""
        self.asked.append(text)
        if "sbatch" in text:
            return self.array_id + "\n"
        if "scancel" in text:
            self.scancelled.append(text)
            return ""
        if "sacct" in text:
            self.n_poll += 1
            got = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
            if isinstance(got, Exception):
                raise got
            rows, listing = got
            return ("\n".join("%s|%s" % (j, s) for j, s in rows) + "\n--\n"
                    + "\n".join("result_%d.json" % i for i in listing) + "\n")
        if "result_" in text and "cat" in text:
            i = int(text.split("result_")[1].split(".")[0])
            return json.dumps(self.results.get(i, {"i": i}))
        return ""


class ArrJob(object):
    """Enough of cfc.Job for `collect`."""

    def __init__(self):
        self.members, self.log, self.canceled = {}, [], False

    def check(self):
        if self.canceled:
            raise cfc.Canceled("Stopped.")

    def member(self, mid, **patch):
        self.members.setdefault(mid, {}).update(patch)

    def begin(self, *a, **k):
        pass

    def tick(self, *a, **k):
        pass


def _ssh_err(msg="Connection reset by peer"):
    return vacc.SSHError(msg, "failed")


def _drive(run, where="vacc:scratch", limit=10.0):
    job = cfc.start({"path": run.spec_local.get("path")}, vaccrun.steps(),
                    run.work, 1.0, where)
    t0 = time.time()
    while job.status == "running" and time.time() - t0 < limit:
        time.sleep(0.005)
    return job


def _arr(fake, n=2, runlog=None):
    tasks = [{"gid": "g%d" % i, "member": "g%d|X" % i,
              "spec_local": {"path": "D:\\r%d" % i},
              "spec_remote": {"path": "/gpfs2/scratch/r%d" % i},
              "seconds": 1, "megasamples": 1} for i in range(n)]
    arr = vaccrun.VaccArray(CFG, "circuit", tasks, ssh=fake)
    arr.runlog = runlog
    arr.submit(seconds=1)
    return arr, tasks


# ==========================================================================
# Part 1: the reliability fixes
# ==========================================================================
def part_fixes():
    saved = (vaccrun.CLOCK, vaccrun.SLEEP, dict(vaccrun.POLL),
             vaccrun.retrying)
    clock = Clock()
    vaccrun.CLOCK, vaccrun.SLEEP = clock, clock.sleep
    # Fake seconds: every sleep advances the fake clock, instantly.
    for k in vaccrun.POLL:
        vaccrun.POLL[k] = 10.0
    tmp = tempfile.mkdtemp(prefix="barry_circuitrun_")
    try:
        print("\nfix 1: a flaky poll does not kill a healthy job")
        fake = FakeSingle([_ssh_err(), _ssh_err("timed out"), "RUNNING",
                           "COMPLETED"])
        run = vaccrun.VaccRun(CFG, "circuit", {"path": "D:\\x"},
                              "/gpfs2/scratch/x", ssh=fake)
        job = _drive(run)
        check("two ssh errors on the poll, and the run still finishes",
              job.status == "done", "%s %s" % (job.status, job.error))
        check("  and nothing was scancelled", not fake.scancelled,
              fake.scancelled)
        check("  and the retries are in the job's log for a person",
              any("did not answer" in ln for ln in job.log), job.log)

        # Negative control: the same fake, retrying switched off (the code
        # as it was). It must fail AND scancel -- the bug this fixes.
        vaccrun.retrying = lambda call, *a, **k: call()
        fake = FakeSingle([_ssh_err(), "RUNNING", "COMPLETED"])
        run = vaccrun.VaccRun(CFG, "circuit", {"path": "D:\\x"},
                              "/gpfs2/scratch/x", ssh=fake)
        job = _drive(run)
        vaccrun.retrying = saved[3]
        check("NEGATIVE CONTROL: without the retry the run fails",
              job.status == "failed", job.status)
        check("NEGATIVE CONTROL: ... and scancels a healthy job",
              bool(fake.scancelled), fake.scancelled)

        print("\nfix 1: a cluster that stays silent detaches, not cancels")
        log = vaccrun.RunLog(tmp)
        fake = FakeSingle([_ssh_err()] * 5000)
        run = vaccrun.VaccRun(CFG, "circuit", {"path": "D:\\x"},
                              "/gpfs2/scratch/x", ssh=fake)
        run.runlog = log
        job = _drive(run)
        check("after the limit the run stops, saying it lost contact",
              job.status == "failed" and "lost contact" in (job.error or ""),
              "%s %s" % (job.status, job.error))
        check("  a written-down run is NOT scancelled", not fake.scancelled,
              fake.scancelled)
        rec = log.get(run.rid) or {}
        check("  and its record stays open for the next start",
              rec.get("status") in vaccrun.RunLog.OPEN, rec.get("status"))
        fake = FakeSingle([_ssh_err()] * 5000)
        run = vaccrun.VaccRun(CFG, "circuit", {"path": "D:\\x"},
                              "/gpfs2/scratch/x", ssh=fake)
        job = _drive(run)
        check("  one nothing points at IS scancelled on the way out",
              bool(fake.scancelled), fake.scancelled)
        fake = FakeSingle(["COMPLETED"])
        fake.result = None
        orig = fake.__call__

        def no_file(cmd, stdin=None, timeout=45, _o=orig):
            if "result.json" in ((stdin or cmd) or ""):
                return vaccrun._NO_RESULT + "\n"
            return _o(cmd, stdin, timeout)
        run = vaccrun.VaccRun(CFG, "circuit", {"path": "D:\\x"},
                              "/gpfs2/scratch/x", ssh=no_file)
        t = clock.t
        job = _drive(run)
        check("a job that COMPLETED with no result.json fails at once, "
              "saying so", job.status == "failed"
              and "wrote no answer" in (job.error or "")
              and clock.t - t < 1.0, "%s %s" % (job.status, job.error))

        print("\nfix 2: array polls")
        A = "555000"
        fake = FakeArray([_ssh_err(), _ssh_err(), _ssh_err(),
                          ([(A + "_0", "COMPLETED"), (A + "_1", "COMPLETED")],
                           [0, 1])])
        arr, tasks = _arr(fake)
        job = ArrJob()
        got = []
        done, failed = vaccrun.collect(job, arr, tasks,
                                       lambda i, t, o: got.append(i))
        check("three ssh errors in arr.poll, then both tasks are collected",
              (done, failed) == (2, 0) and sorted(got) == [0, 1],
              (done, failed, got))
        check("  and the array was not cancelled", not fake.scancelled,
              fake.scancelled)
        fake = FakeArray([RuntimeError("the poller itself broke")])
        arr, tasks = _arr(fake)
        try:
            vaccrun.collect(ArrJob(), arr, tasks, lambda *a: None)
            raised = False
        except RuntimeError:
            raised = True
        check("a batch that really fails raises ...", raised)
        check("  ... and cancels its array", any(A in s for s in
                                                 fake.scancelled),
              fake.scancelled)
        fake = FakeArray([([(A + "_0", "RUNNING")], [])])
        arr, tasks = _arr(fake, n=1)
        job = ArrJob()
        job.canceled = True
        try:
            vaccrun.collect(job, arr, tasks, lambda *a: None)
        except cfc.Canceled:
            pass
        check("Cancel on a batch scancels its array",
              bool(fake.scancelled), fake.scancelled)

        print("\nfix 3: grace, and a deadline")
        fake = FakeArray([([(A + "_0", "COMPLETED"), (A + "_1", "COMPLETED")],
                           [1])])
        arr, tasks = _arr(fake)
        job = ArrJob()
        t0 = clock.t
        done, failed = vaccrun.collect(job, arr, tasks, lambda *a: None)
        m0 = job.members.get("g0|X") or {}
        check("COMPLETED with no answer file: failed, not waited on for ever",
              (done, failed) == (1, 1) and m0.get("status") == "failed",
              (done, failed, m0))
        check("  with a sentence saying so",
              "wrote no answer" in (m0.get("why") or ""), m0.get("why"))
        check("  and only after its grace",
              clock.t - t0 >= vaccrun.RESULT_GRACE_S, clock.t - t0)
        fake = FakeArray([([(A + "_1", "COMPLETED")], [1])])
        arr, tasks = _arr(fake)
        job = ArrJob()
        t0 = clock.t
        done, failed = vaccrun.collect(job, arr, tasks, lambda *a: None)
        m0 = job.members.get("g0|X") or {}
        check("a task sacct never reports: failed with a sentence",
              failed == 1 and "never reported" in (m0.get("why") or ""),
              (done, failed, m0))
        check("  only after the unseen grace",
              clock.t - t0 >= vaccrun.UNSEEN_GRACE_S, clock.t - t0)
        # Pending as a folded range for longer than the unseen grace, then
        # done: a queued task is not a vanished one.
        n_pend = int(vaccrun.UNSEEN_GRACE_S / 10.0) + 30
        fake = FakeArray([([(A + "_[0-1%1]", "PENDING")], [])] * n_pend
                         + [([(A + "_0", "COMPLETED"),
                              (A + "_1", "COMPLETED")], [0, 1])])
        arr, tasks = _arr(fake)
        job = ArrJob()
        orig_poll = vaccrun.POLL["running"]
        vaccrun.POLL["running"] = 10.0
        done, failed = vaccrun.collect(job, arr, tasks, lambda *a: None)
        vaccrun.POLL["running"] = orig_poll
        check("a range still PENDING past the unseen grace is waited for",
              (done, failed) == (2, 0), (done, failed, job.members))
        check("  the range parser reads 2-5%2 and 0,3,7-9",
              vaccrun._task_range("2-5%2]") == [2, 3, 4, 5]
              and vaccrun._task_range("0,3,7-9]") == [0, 3, 7, 8, 9])
        # Negative control: the same queue with the range parser blinded
        # reads every queued task as never reported, and fails them.
        saved_range = vaccrun._task_range
        vaccrun._task_range = lambda text: []
        fake = FakeArray([([(A + "_[0-1%1]", "PENDING")], [])] * n_pend
                         + [([(A + "_0", "COMPLETED"),
                              (A + "_1", "COMPLETED")], [0, 1])])
        arr, tasks = _arr(fake)
        vaccrun.POLL["running"] = 10.0
        try:
            done, failed = vaccrun.collect(ArrJob(), arr, tasks,
                                           lambda *a: None)
        finally:
            vaccrun._task_range = saved_range
        check("NEGATIVE CONTROL: without the range parse, queued = vanished",
              failed == 2, (done, failed))
        fake = FakeArray([([(A + "_0", "RUNNING")], [])])
        arr, tasks = _arr(fake, n=1)
        job = ArrJob()
        done, failed = vaccrun.collect(job, arr, tasks, lambda *a: None,
                                       deadline_s=600)
        m0 = job.members.get("g0|X") or {}
        check("a batch past its deadline is cancelled and says so",
              failed == 1 and bool(fake.scancelled)
              and "did not finish within" in (m0.get("why") or ""),
              (failed, fake.scancelled, m0))

        print("\nfix 4: a restart, with the run written down at submit")
        log = vaccrun.RunLog(tmp)
        fake = FakeSingle(["RUNNING"] * 3)
        run = vaccrun.VaccRun(CFG, "circuit", {"path": "D:\\x", "k": 1},
                              "/gpfs2/scratch/x", ssh=fake,
                              tool_steps=[("circuit pairs", 2)])
        run.runlog = log
        run.record = {"gid": "gX", "keys": ["a", "b"]}

        class J(object):
            id = "abcabcabcabc"

            def tick(self, *a):
                pass
        run.submit(J())
        # ... and the process dies here. A new process, a new RunLog:
        log2 = vaccrun.RunLog(tmp)
        open_ = [r for r in log2.open_runs(tool="circuit")
                 if r["rid"] == run.rid]
        check("the record is on disk with rid, slurm id, workspace, tool, "
              "caller keys", bool(open_) and open_[0].get("slurm_id")
              == "778899" and open_[0].get("workspace") and
              (open_[0].get("record") or {}).get("keys") == ["a", "b"],
              open_[:1])
        fake2 = FakeSingle(["RUNNING", "COMPLETED"], result={"back": 7})
        again = vaccrun.VaccRun.reattach(CFG, open_[0], ssh=fake2)
        again.runlog = log2
        job = cfc.adopt(cfc.Job({"path": "D:\\x"}, vaccrun.steps(), 1.0,
                                "vacc:scratch", id=open_[0]["job_id"]))

        def go():
            try:
                job.finish(again.work(job))
            except Exception as exc:                     # noqa: BLE001
                job.fail(exc)
        th = threading.Thread(target=go)
        th.start()
        th.join(10)
        check("re-attached: polled, not re-submitted",
              not any("sbatch" in a for a in fake2.asked), fake2.asked[:2])
        check("  the answer came home under the SAME job id",
              job.status == "done" and (job.result or {}).get("back") == 7
              and cfc.get(open_[0]["job_id"]) is job,
              "%s %s" % (job.status, job.result))
        check("  and the record says fetched (closed by the filer)",
              (log2.get(run.rid) or {}).get("status") == "fetched")
    finally:
        vaccrun.CLOCK, vaccrun.SLEEP = saved[0], saved[1]
        vaccrun.POLL.update(saved[2])
        vaccrun.retrying = saved[3]
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# Part 2: real data
# ==========================================================================
ROUTE_PLAN_KEYS = ("gid", "label", "rat", "cue_type", "cue_label", "kind",
                   "pairs", "n_pairs", "n_cached", "params", "defaults",
                   "measured_pad_s", "transition_measured", "probe", "grey",
                   "cost", "artifact")
ROUTE_ROW_KEYS = ("gid", "label", "mouse", "session", "phase", "phase_n",
                  "date", "banked", "reachable", "vacc", "n_pairs",
                  "cue_types", "transition_measured", "circuits")
ROUTE_RESULT_KEYS = ("ok", "artifact_id", "version", "digest", "name",
                     "nickname", "new_version", "payload", "computed_on")
_ROUTE_EXTRA = ("ok", "gid", "entry_id", "rat", "bad_channels",
                "run_params", "sanity")


def _poll(C, jid, limit=900):
    """Poll a cfc job; return (snapshot, timeline of member-status counts)."""
    seen, t0 = [], time.time()
    while True:
        snap = C.get("/api/cfc/job/%s" % jid).get_json()["job"]
        ms = snap.get("members") or []
        tally = {}
        for m in ms:
            tally[m.get("status")] = tally.get(m.get("status"), 0) + 1
        if not seen or seen[-1][1] != tally:
            seen.append((round(time.time() - t0, 2), tally))
        if snap["status"] != "running" or time.time() - t0 > limit:
            return snap, seen
        time.sleep(0.2)


def _values(res):
    out = {}
    for w in res.get("windows") or []:
        for row in w.get("pairs") or []:
            for m in ("coherence", "raw_cc", "amp_cc"):
                out[(w["window"], row["a"], row["b"], m)] = \
                    circuit.summary_value(row.get(m))
    return out


def part_resume(A, CR, host, gid, blob):
    """Fix 4 through Circuit itself: a VACC circuit submitted, the process
    'dies', a new process re-attaches from the run record, fetches, fills
    the cache and files the artifact. Against a fake login node, into an
    artifact store in a temporary directory -- never the real one."""
    from backend import artifacts as artmod
    print("\nfix 4 through Circuit: submit, 'restart', re-attach, file")
    tmp = tempfile.mkdtemp(prefix="barry_circuit_resume_")
    saved = (CR._ROOT, CR.RUNLOG)
    try:
        CR._ROOT = os.path.join(tmp, "cache")
        CR.RUNLOG = vaccrun.RunLog(tmp)
        store = artmod.Artifacts(os.path.join(tmp, "logs"), None)
        remote = "/gpfs2/scratch/fake/" + gid
        fh = CR.Host(**dict(host.__dict__, artifacts=store,
                            vacc_cfg=lambda: CFG,
                            vacc_status=lambda: {"configured": True,
                                                 "available": True},
                            vacc_states=lambda gids, wait: {
                                g: {"state": vacc.STAGED, "remote": remote}
                                for g in gids}))
        prep = CR.prepare(fh, gid, blob["cue_type"], "state", {})
        todo = [p for p in prep["pairs"] if not p["cached"]]
        spec = CR._vacc_spec(prep, todo)
        run = vaccrun.VaccRun(CFG, "circuit", spec, remote,
                              ssh=FakeSingle([]),
                              tool_steps=[("circuit pairs", len(todo))])
        run.members = [p["pair_id"] for p in todo]
        run.runlog = CR.RUNLOG
        run.record = {"prep": prep, "nickname": None}

        class J(object):
            id = "resumecheck1"

            def tick(self, *a):
                pass
        run.submit(J())
        # The process dies here. The answer the node would have written:
        by = {x["pair_id"]: x for x in blob["results"]}
        answer = {"pairs": [dict({k: v for k, v in by[p["pair_id"]].items()
                                  if k not in _ROUTE_EXTRA},
                                 label=p["label"],
                                 folder=remote) for p in todo]}
        fake2 = FakeSingle(["RUNNING", "COMPLETED"], result=answer)
        CR._RESUMED["done"] = False
        jobs = CR.resume(fh, ssh=fake2)
        job = jobs[0] if jobs else None
        t0 = time.time()
        while job is not None and job.status == "running" and \
                time.time() - t0 < 60:
            time.sleep(0.05)
        res = (job.result if job else None) or {}
        check("re-attached under the job id written at submit",
              job is not None and job.id == "resumecheck1", jobs)
        check("  polled, never re-submitted",
              not any("sbatch" in a for a in fake2.asked))
        check("  the pairs landed in the cache and the circuit was filed",
              job is not None and job.status == "done"
              and res.get("version") == 1 and res.get("n_pairs") == len(todo)
              and CR.prepare(fh, gid, blob["cue_type"], "state", {})
              ["n_cached"] == len(todo), (job and job.error, res.get("n_pairs")))
        check("  computed_on says vacc and the slurm id",
              (res.get("computed_on") or {}).get("kind") == "vacc"
              and (res.get("computed_on") or {}).get("slurm_id") == "778899",
              res.get("computed_on"))
        check("  and the run record is closed `done`",
              (CR.RUNLOG.get(run.rid) or {}).get("status") == "done")
        check("  filed into the temporary store, not the real one",
              store.get(res.get("artifact_id")) is not None
              and A.ARTIFACTS.get(res.get("artifact_id")) is None)
    finally:
        CR._ROOT, CR.RUNLOG = saved
        shutil.rmtree(tmp, ignore_errors=True)


def part_transition(A, CR, host, gid):
    """A transition circuit, on the entry the bank WOULD write once Spark
    has measured the boundaries -- captured the way
    tools/check_arc_transition.py captures it (the real clipping read, the
    real bank route, `BANK.add` swapped for a catcher). No real entry is
    re-banked; the artifact goes to a temporary store."""
    import copy
    from backend import artifacts as artmod
    print("\na transition circuit, on a captured (never banked) entry")
    C = A.app.test_client()
    real = A._coupling_entry(gid)
    kept = {}
    real_add = A.BANK.add
    A.BANK.add = lambda e: kept.setdefault("entry", copy.deepcopy(e)) or e
    try:
        r = C.post("/api/arc/spark/%s/clipping" % gid, json={})
        check("the clipping read answered (both kinds, one read)",
              r.status_code == 200, r.get_json())
        C.post("/api/arc/spark/%s/bank" % gid, json={"excluded": {}})
    finally:
        A.BANK.add = real_add
    got = kept.get("entry")
    if not check("  and the bank route's entry was captured, not filed",
                 bool(got) and A._coupling_entry(gid).get("version")
                 == real.get("version")):
        return
    fake = copy.deepcopy(real)
    fake["events"] = got["events"]
    fake.setdefault("source", {})["parameters"] = got["parameters"]
    tmp = tempfile.mkdtemp(prefix="barry_circuit_transition_")
    saved = CR._ROOT
    try:
        CR._ROOT = os.path.join(tmp, "cache")
        store = artmod.Artifacts(os.path.join(tmp, "logs"), None)
        th = CR.Host(**dict(host.__dict__, artifacts=store,
                            entry=lambda g: fake if g == gid
                            else host.entry(g)))
        ct = CR.cue_types_of(th, fake)[0]["cue_type"]
        try:
            CR.prepare(th, gid, ct, "transition", {"before_s": 1.5})
            refused = None
        except CR.CircuitRunError as exc:
            refused = str(exc)
        check("a transition window longer than was measured is refused",
              refused and "measured" in refused, refused)
        prep = CR.prepare(th, gid, ct, "transition", {})
        check("prepare: transition measured, %d pairs" % prep["n_pairs"],
              prep["transition_measured"] and prep["n_pairs"] > 0)
        job = CR.start_local(th, prep)
        t0 = time.time()
        while job.status == "running" and time.time() - t0 < 600:
            time.sleep(0.5)
        res = job.result or {}
        pl = res.get("payload") or {}
        check("the transition circuit filed (%.0f s)" % (time.time() - t0),
              job.status == "done" and res.get("version") == 1, job.error)
        check("  windows onset, switch, offset; params carry before/after",
              pl.get("windows") == ["onset", "switch", "offset"]
              and pl.get("kind") == "transition"
              and (pl.get("params") or {}).get("before_s") == 1.0
              and (pl.get("params") or {}).get("after_s") == 2.0,
              (pl.get("windows"), pl.get("params")))
        check("  its own subject: a different artifact from the state one",
              (store.get(res.get("artifact_id")) or {}).get("subject_key")
              == circuit.subject_key(gid, ct, "transition"))
    finally:
        CR._ROOT = saved
        shutil.rmtree(tmp, ignore_errors=True)


def part_real():
    from backend import app as A
    from backend import artifacts as artmod
    from backend import circuitrun as CR
    C = A.app.test_client()
    made = set()
    saved_root = CR._ROOT
    tmpcache = tempfile.mkdtemp(prefix="barry_circuit_cache_")
    CR._ROOT = tmpcache
    host = A._circuit_host()
    FRESH, SEED = "s6a38e45cf331", "s360e48254222"
    pre_ok = False
    try:
        print("\nthe recordings list")
        t = time.time()
        r = C.get("/api/arc/circuit/recordings").get_json()
        rows = {x["gid"]: x for x in r.get("rows") or []}
        check("GET /recordings answers, %d rows in %.1f s"
              % (len(rows), time.time() - t), r.get("ok") and rows, r)
        row = rows.get(FRESH) or {}
        check("  a row has every contract field",
              all(k in row for k in ROUTE_ROW_KEYS),
              [k for k in ROUTE_ROW_KEYS if k not in row])
        check("  cue types are the recording's ACTUAL pairings",
              [c["cue_type"] for c in row.get("cue_types") or []]
              and all(c["cue_type"] in circuit.CUE_TYPES
                      for c in row["cue_types"]), row.get("cue_types"))
        # Only a circuit this check could file over, or delete in its
        # cleanup: a classic one (no band). The Precon analysis filed band
        # circuits on SEED (r7 Precon1) on 2026-09-30; their subject keys end
        # in the band, so nothing here can touch them, and refusing on them
        # would have made this check unrunnable for as long as they exist.
        for gid in (FRESH, SEED):
            mine = [c for c in (rows.get(gid, {}).get("circuits") or [])
                    if c.get("band") in (None, "")]
            if mine:
                check("PRECONDITION: %s has no real classic circuit artifact"
                      % gid, False, mine)
                return
        pre_ok = True
        ct = row["cue_types"][0]["cue_type"]

        print("\nplan: %s %s, state" % (row.get("label"), ct))
        p = C.get("/api/arc/circuit/%s/plan?cue_type=%s&kind=state"
                  % (FRESH, ct)).get_json()
        check("GET /plan answers with every contract field",
              p.get("ok") and all(k in p for k in ROUTE_PLAN_KEYS),
              [k for k in ROUTE_PLAN_KEYS if k not in p] or p.get("error"))
        check("  nothing cached yet (a fresh cache)", p.get("n_cached") == 0,
              p.get("n_cached"))
        check("  the cost is said before it is spent: %s"
              % (p.get("cost") or {}).get("sentence"),
              (p.get("cost") or {}).get("local_s") is not None)
        print("      vacc: can=%s why=%s" % (p["cost"].get("vacc_can"),
                                             p["cost"].get("vacc_why")))
        q = C.get("/api/arc/circuit/%s/plan?cue_type=%s&kind=transition"
                  % (FRESH, ct))
        check("a transition plan on an unmeasured entry is refused 409",
              q.status_code == 409 and "transition" in
              (q.get_json().get("error") or ""), q.status_code)
        q = C.get("/api/arc/circuit/%s/plan?cue_type=Click_Noise&kind=state"
                  % FRESH)
        check("a cue type the rat never heard is refused, naming its own",
              q.status_code == 400 and "pairings" in
              (q.get_json().get("error") or ""), q.get_json())

        print("\nrun 1: fresh, local")
        t = time.time()
        r = C.post("/api/arc/circuit/%s/run" % FRESH,
                   json={"cue_type": ct, "kind": "state", "params": {},
                         "where": "local"}).get_json()
        check("POST /run returns a cfc job id", r.get("ok") and r.get("job"),
              r)
        snap, seen = _poll(C, r["job"])
        wall1 = time.time() - t
        res = C.get("/api/cfc/result/%s" % r["job"]).get_json()
        out = res.get("result") or {}
        if out.get("artifact_id"):
            made.add(out["artifact_id"])
        check("the job finished (%.1f s wall)" % wall1,
              snap["status"] == "done", snap.get("error"))
        n = p["n_pairs"]
        dones = [s[1].get("done", 0) for s in seen]
        check("pairs landed one by one (%s)"
              % " ".join("%s@%.0fs" % (s[1].get("done", 0), s[0])
                         for s in seen),
              len(set(dones)) >= min(n, 3) and dones[-1] == n, seen)
        st = [s for s in snap["stages"] if s["name"] == "circuit pairs"]
        per = (st[0]["seconds"] / n) if st and st[0]["seconds"] else None
        print("      per pair %.2f s, %d pairs" % (per or -1, n))
        check("the result has every contract field",
              all(k in out for k in ROUTE_RESULT_KEYS),
              [k for k in ROUTE_RESULT_KEYS if k not in out])
        rec = A.ARTIFACTS.get(out.get("artifact_id")) or {}
        subj = rec.get("subject") or {}
        check("the artifact exists, subject = recording, cue type, kind",
              subj.get("gid") == FRESH and subj.get("cue_type") == ct
              and subj.get("window_kind") == "state", subj)
        entry = A._coupling_entry(FRESH)
        v1 = (rec.get("versions") or [{}])[-1]
        check("  inputs pin the bank entry and its version",
              v1.get("inputs") == [{"kind": "bank", "entry": entry["id"],
                                    "version": entry["version"]}],
              v1.get("inputs"))
        check("  the payload digest is the stored one",
              artmod.digest(out["payload"]) == out["digest"] == v1["digest"],
              (artmod.digest(out["payload"]), out.get("digest")))
        check("  the name is the automatic one: %s" % rec.get("name"),
              rec.get("name") == circuit.name_for(subj))
        check("  version 1, new", out.get("version") == 1
              and out.get("new_version") is True)
        check("  every pair is in the payload",
              out["payload"]["n_pairs"] == n, out["payload"]["n_pairs"])

        print("\nrun 2: the same, again")
        p2 = C.get("/api/arc/circuit/%s/plan?cue_type=%s&kind=state"
                   % (FRESH, ct)).get_json()
        check("the plan now says every pair is cached",
              p2["n_cached"] == n, p2["n_cached"])
        t = time.time()
        r = C.post("/api/arc/circuit/%s/run" % FRESH,
                   json={"cue_type": ct, "kind": "state",
                         "where": "local"}).get_json()
        snap, seen = _poll(C, r["job"])
        wall2 = time.time() - t
        out2 = (C.get("/api/cfc/result/%s" % r["job"]).get_json()
                .get("result") or {})
        ms = snap.get("members") or []
        check("nothing was computed: every member is `cached` (%.1f s)"
              % wall2, ms and all(m["status"] == "cached" for m in ms),
              [m["status"] for m in ms])
        check("no new version: confirmed, still v1, same digest",
              out2.get("new_version") is False and out2.get("confirmed")
              and out2.get("version") == 1
              and out2.get("digest") == out.get("digest"), out2.get("version"))
        rec = A.ARTIFACTS.get(out["artifact_id"])
        check("  and v1 carries the confirmation",
              len(rec["versions"]) == 1
              and len(rec["versions"][0].get("confirmed") or []) == 1)

        print("\nnegative controls for the cache")
        prep = CR.prepare(host, FRESH, ct, "state", {})
        pid = prep["pairs"][0]["pair_id"]
        # The key the run uses: the bank version AND this pair's wires
        # (circuitrun.drop_tag) -- never rebuilt by hand from the version.
        path = CR.cache_path(*CR._pair_key(prep, pid))
        good = open(path, "r", encoding="utf-8").read()
        bad = json.loads(good)
        bad["pair_id"] = pid + 1000
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(bad, fh)
        prep2 = CR.prepare(host, FRESH, ct, "state", {})
        check("a cache file that is not this pair is refused (n_cached %d)"
              % prep2["n_cached"], prep2["n_cached"] == n - 1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(good)
        h0 = CR.params_hash(prep["params"], prep["bad"], prep["blocked"])
        check("the hash moves with a bad channel",
              CR.params_hash(prep["params"], prep["bad"] + [31],
                             prep["blocked"]) != h0)
        check("the hash moves with a histology block",
              CR.params_hash(prep["params"], prep["bad"],
                             dict(prep["blocked"], **{"Left PER": "x"}))
              != h0 or "Left PER" in prep["blocked"])
        check("... and not with a transition length on a state run",
              CR.params_hash(dict(prep["params"], before_s=3.0),
                             prep["bad"], prep["blocked"]) == h0)

        print("\nrun 3: other parameters")
        p3 = C.post("/api/arc/circuit/%s/plan" % FRESH,
                    json={"cue_type": ct, "kind": "state",
                          "params": {"summary_hz": 6.0}}).get_json()
        check("NEGATIVE CONTROL (cache): other params, nothing cached",
              p3["n_cached"] == 0, p3["n_cached"])
        r = C.post("/api/arc/circuit/%s/run" % FRESH,
                   json={"cue_type": ct, "kind": "state", "where": "local",
                         "params": {"summary_hz": 6.0},
                         "nickname": "check_circuitrun"}).get_json()
        snap, seen = _poll(C, r["job"])
        out3 = (C.get("/api/cfc/result/%s" % r["job"]).get_json()
                .get("result") or {})
        check("NEGATIVE CONTROL (versions): a different answer is v2",
              out3.get("version") == 2 and out3.get("new_version") is True
              and out3.get("digest") != out.get("digest")
              and out3.get("artifact_id") == out.get("artifact_id"),
              (out3.get("version"), out3.get("digest")))
        check("  the nickname from the body landed",
              out3.get("nickname") == "check_circuitrun", out3.get("nickname"))
        check("  v1 is still there and still readable",
              artmod.digest(A.ARTIFACTS.payload(out["artifact_id"], 1))
              == out["digest"])

        print("\nseeded: %s from the Circuit-engine agent's cache" % SEED)
        seed_file = os.path.join(SCRATCH, "circuit_cache_%s.json" % SEED)
        seeded = 0
        if os.path.isfile(seed_file):
            blob = json.load(open(seed_file, "r", encoding="utf-8"))
            sprep = CR.prepare(host, SEED, blob["cue_type"], "state", {})
            fresh1 = CR.plain(CR.compute_pair(
                sprep["path"], sprep["pairs"][0]["pair"],
                sprep["pairs"][0]["drop"], sprep["blocked"],
                sprep["params"], "state"))
            by = {x["pair_id"]: x for x in blob["results"]}
            seed1 = by.get(sprep["pairs"][0]["pair_id"]) or {}
            a, b = _values(fresh1), _values(seed1)
            same = (a.keys() == b.keys() and all(
                (a[k] is None and b[k] is None) or
                (a[k] is not None and b[k] is not None
                 and abs(a[k] - b[k]) < 1e-9) for k in a))
            check("the seed agrees with a fresh computation of pair %s "
                  "(%d numbers)" % (sprep["pairs"][0]["pair_id"], len(a)),
                  same and len(a) > 0)
            if same:
                for sp in sprep["pairs"]:
                    got = by.get(sp["pair_id"])
                    if got is None:
                        continue
                    got = {k: v for k, v in got.items()
                           if k not in _ROUTE_EXTRA}
                    got["label"] = sp["label"]
                    CR.cache_put(*(CR._pair_key(sprep, sp["pair_id"])
                                   + (got,)))
                    seeded += 1
            ps = C.get("/api/arc/circuit/%s/plan?cue_type=%s&kind=state"
                       % (SEED, blob["cue_type"])).get_json()
            check("seeded %d pairs; the plan sees %d cached"
                  % (seeded, ps.get("n_cached")),
                  ps.get("n_cached") == seeded and seeded > 0)
        else:
            print("      (no seed file at %s; skipped)" % seed_file)

        if os.path.isfile(seed_file) and seeded:
            part_resume(A, CR, host, SEED, blob)
        part_transition(A, CR, host, FRESH)

        print("\nbatch")
        bp = C.post("/api/arc/circuit/batch/plan", json={
            "gids": [FRESH, SEED, "s_not_a_recording"], "cue_types": "all",
            "kind": "state", "params": {}, "where": "local"}).get_json()
        check("POST /batch/plan: todo, already, blocked, total_s, sentence",
              bp.get("ok") and all(k in bp for k in ("todo", "already",
                                                      "blocked", "total_s",
                                                      "sentence")), bp)
        print("      " + str(bp.get("sentence")))
        check("  the unbanked gid is blocked with a reason",
              any(b["gid"] == "s_not_a_recording" and b.get("why")
                  for b in bp.get("blocked") or []), bp.get("blocked"))
        bv = C.post("/api/arc/circuit/batch/plan", json={
            "gids": [FRESH, SEED], "cue_types": "all", "kind": "state",
            "params": {}, "where": "vacc"}).get_json()
        print("      vacc: " + str(bv.get("sentence") or bv.get("error")))
        check("  a VACC plan blocks what the cluster does not hold, saying so",
              (not bv.get("ok")) or all(
                  "cluster" in (b.get("why") or "")
                  for b in bv.get("blocked") or []), bv)
        # A tiny local batch: FRESH's current version is at summary_hz 6,
        # so at the defaults it is TODO -- all of its pairs cached from run
        # 1, so it computes nothing and files; SEED's other cue type is
        # computed fresh only if asked, so ask for the seeded one only.
        sct = blob["cue_type"] if os.path.isfile(seed_file) else None
        br = C.post("/api/arc/circuit/batch/run", json={
            "gids": [FRESH] + ([SEED] if sct else []),
            "cue_types": [ct] + ([sct] if sct else []),
            "kind": "state", "params": {}, "where": "local"}).get_json()
        check("POST /batch/run returns a job", br.get("ok") and br.get("job"),
              br)
        snap, seen = _poll(C, br["job"])
        bres = (C.get("/api/cfc/result/%s" % br["job"]).get_json()
                .get("result") or {})
        for m in bres.get("made") or []:
            made.add(m["artifact_id"])
        ms = {m["id"]: m for m in snap.get("members") or []}
        check("the batch finished with a member row per (recording, cue "
              "type)", snap["status"] == "done"
              and "%s|%s" % (FRESH, ct) in ms, (snap.get("error"), list(ms)))
        check("  each filed its artifact as it landed",
              all(m.get("artifact_id") for m in ms.values()
                  if m.get("status") == "done"), ms)
        again = C.post("/api/arc/circuit/batch/plan", json={
            "gids": [FRESH] + ([SEED] if sct else []),
            "cue_types": [ct] + ([sct] if sct else []),
            "kind": "state", "params": {}, "where": "local"}).get_json()
        check("re-planning the finished batch: nothing to do, all already",
              not again.get("todo") and len(again.get("already") or []) ==
              (2 if sct else 1), again.get("sentence"))
        return {"wall1": wall1, "wall2": wall2, "per_pair": per, "n": n}
    finally:
        CR._ROOT = saved_root
        shutil.rmtree(tmpcache, ignore_errors=True)
        for g in ((FRESH, SEED) if pre_ok else ()):
            for k in ("state",):
                for c in circuit.CUE_TYPES:
                    hit = A.ARTIFACTS.find("circuit",
                                           circuit.subject_key(g, c, k))
                    if hit:
                        made.add(hit["id"])
        for aid in sorted(made):
            try:
                A.ARTIFACTS.delete(aid)
                A.ARTIFACTS.erase(aid)
                print("  cleaned up artifact %s (deleted, then erased)" % aid)
            except Exception as exc:                     # noqa: BLE001
                print("  COULD NOT CLEAN UP artifact %s: %s" % (aid, exc))
                FAILED.append("cleanup " + aid)


# ==========================================================================
# Part 3: a real cluster run (--vacc)
# ==========================================================================
SMOKE = ["/gpfs2/scratch/sakhava1/DEWEY GUI Project/HOF/J1_PRECON1_SP_091225/DATA",
         "/gpfs2/scratch/sakhava1/DEWEY GUI Project/HOF/J2_PRECON2_SP_091325/DATA"]


def _synthetic(pid, t):
    return {"pair_id": pid, "opener_t": float(t), "closer_t": float(t) + 10,
            "offset_t": float(t) + 20, "gap_s": 10.0,
            "opener_label": "Click", "closer_label": "Noise",
            "label": "Click → Noise"}


def vacc_smoke():
    """The `circuit` tool on the real cluster, single and as an array.

    No banked DEWEY recording is on the cluster (all 33 are on E: only),
    so this cannot be a real circuit. It is the next best thing and says
    so: J1/J2 recordings the cluster DOES hold, with synthetic cue-pair
    times, run through the real submit -> queue -> node
    (`vacc_run.py` -> `circuitrun.run_node` -> `coupling.pair_connectivity`)
    -> poll -> fetch path, single and as a two-task array. Everything it
    starts it waits for, and cancels in a finally if it did not end.
    """
    from backend import coupling
    cfg = vacc.load_config(os.path.join(APP, "GUI_logs"))
    if not cfg.get("netid"):
        print("  (no VACC account on this machine; skipped)")
        return None
    params = coupling.read_params({}, kind="state")
    per = cfc.rate_for("circuit pairs", "vacc:scratch")
    req = vacc.slurm_request(2 * per, 1.0, cfg.get("partition"))
    print("\nVACC, real: cost first -- single: 2 pairs, about %.0f s of "
          "compute, asking %s on %s; array: 2 tasks of 1 pair, the same "
          "request each, plus the queue" % (2 * per, req["time"],
                                            req["partition"]))
    t = time.time()
    push = vacc.push_code(cfg, APP)
    print("  code pushed (%s, %.1f s)" % ("uploaded" if push["uploaded"]
                                          else "unchanged", time.time() - t))
    out = {}
    tmp = tempfile.mkdtemp(prefix="barry_vacc_smoke_")
    log = vaccrun.RunLog(tmp)
    job = run = arr = None
    try:
        pairs = [_synthetic(1, 600), _synthetic(2, 900)]
        spec = {"path": "vacc-smoke/J1_PRECON1_SP", "gid": "vacc-smoke",
                "kind": "state", "params": params, "blocked": {},
                "pairs": pairs, "drops": {}}
        run = vaccrun.VaccRun(cfg, "circuit", spec, SMOKE[0],
                              plan={"seconds": 2 * per},
                              tool_steps=[("circuit pairs", 2)])
        run.members = [1, 2]
        run.runlog = log

        def work(job):
            job.members_init([{"id": 1, "label": "pair 1"},
                              {"id": 2, "label": "pair 2"}])
            return run.work(job)
        t0 = time.time()
        job = cfc.start({"path": None}, vaccrun.steps() +
                        [("circuit pairs", 2)], work, 1.0, "vacc:scratch")
        seen = []
        while job.status == "running" and time.time() - t0 < 2400:
            ms = tuple((m["id"], m["status"], m.get("step"))
                       for m in (job.snapshot().get("members") or []))
            if not seen or seen[-1][1] != ms:
                seen.append((round(time.time() - t0, 1), ms))
            time.sleep(2)
        snap = job.snapshot()
        # The last state too: a job that ran between two queued polls
        # (thirty seconds apart) has its whole log replayed at the end.
        seen.append((round(time.time() - t0, 1),
                     tuple((m["id"], m["status"], m.get("step"))
                           for m in (snap.get("members") or []))))
        stages = {s["name"]: s["seconds"] for s in snap["stages"]}
        res = job.result or {}
        got = res.get("pairs") or []
        ok = [g for g in got if g.get("windows")]
        nvals = sum(1 for g in ok for v in _values(g).values()
                    if v is not None)
        check("single: slurm %s done in %.0f s wall (queue %.0f s, node "
              "pairs %.1f s)" % (run.slurm_id, time.time() - t0,
                                 stages.get("vacc queue") or -1,
                                 stages.get("circuit pairs") or -1),
              job.status == "done", "%s %s %s" % (job.status, job.error,
                                                  snap.get("log")))
        check("  both pairs came back computed, %d numbers" % nvals,
              len(ok) == 2 and nvals > 0,
              [g.get("error") for g in got])
        check("  per-pair progress arrived from the node",
              any(st == "running" and "node" in (step or "")
                  for _t, ms in seen for _i, st, step in ms), seen[-3:])
        check("  stamped computed_on vacc with the slurm id",
              (res.get("computed_on") or {}).get("slurm_id") == run.slurm_id,
              res.get("computed_on"))
        out["single"] = {"slurm_id": run.slurm_id, "stages": stages,
                         "wall_s": round(time.time() - t0, 1),
                         "members_seen": seen}

        tasks = []
        for i, folder in enumerate(SMOKE):
            sp = {"path": "vacc-smoke/%d" % i, "gid": "vacc-smoke-%d" % i,
                  "kind": "state", "params": params, "blocked": {},
                  "pairs": [_synthetic(1, 600)], "drops": {}}
            tasks.append({"gid": "vacc-smoke-%d" % i,
                          "member": "vacc-smoke-%d|x" % i,
                          "spec_local": sp,
                          "spec_remote": dict(sp, path=folder),
                          "tool_steps": [("circuit pairs", 1)],
                          "seconds": per, "megasamples": 1.0})
        arr = vaccrun.VaccArray(cfg, "circuit", tasks)
        arr.runlog = log
        t0 = time.time()
        arr.submit(seconds=per)
        aj = ArrJob()
        landed = []
        done, failed = vaccrun.collect(
            aj, arr, tasks,
            lambda i, t, o: landed.append((i, round(time.time() - t0, 1),
                                           len(o.get("pairs") or []))),
            deadline_s=2400)
        check("array %s: %d done, %d failed in %.0f s wall; landed %s"
              % (arr.array_id, done, failed, time.time() - t0, landed),
              (done, failed) == (2, 0), aj.members)
        check("  and its run record is closed `done`",
              (log.get(arr.rid) or {}).get("status") == "done")
        out["array"] = {"array_id": arr.array_id, "landed": landed,
                        "wall_s": round(time.time() - t0, 1)}
        arr = None
    finally:
        if job is not None and job.status == "running":
            job.cancel()
            print("  cancelled the single run (the finally scancels it)")
        if arr is not None:
            arr.cancel()
            print("  cancelled array %s" % arr.array_id)
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def main():
    part_fixes()
    got = part_real()
    if "--vacc" in sys.argv:
        smoke = vacc_smoke()
        if smoke:
            print("vacc: %s" % json.dumps(smoke, default=str)[:1500])
    print()
    print("%d passed, %d failed" % (len(PASSED), len(FAILED)))
    if got:
        print("timings: %s" % json.dumps(got))
    if FAILED:
        print("FAILED: " + "; ".join(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
