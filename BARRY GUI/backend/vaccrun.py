"""
vaccrun.py -- one offloaded run, from submit to answer.

`cfc.Job` is a passive state machine: it takes `begin`/`tick`/`finish` and
never asks where the work is happening. `cfc.start` wants a `work(job)` that
blocks until there is a result. So an offloaded run is not a second job
system -- it is a different `work`, and everything downstream of it
(`/api/cfc/job/<id>`, the stage card, Cancel, the result) keeps working
without being told.

TWO POLL LOOPS, AND THEY ARE NOT THE SAME LOOP

The browser polls `/api/cfc/job/<id>` about three times a second and that
must not change: it reads a snapshot out of memory and costs nothing. THIS
polls the cluster, over a fresh ssh connection each time, and if the two were
one loop it would be nine thousand handshakes an hour against a login node
shared with everybody else's interactive work.

So the browser's rate is the browser's and the cluster's rate is here:
seconds while staging, tens of seconds while queued, a few while running.

WHY CANCEL LIVES IN A `finally`

`job.cancel()` sets a flag, and `job.check()` raises `Canceled` out of the
compute -- which is cooperative, in-process, and knows nothing about slurm.
`begin` and `tick` each call `check()` themselves, so `Canceled` can come out
of a line that does not look like it could throw. If the `scancel` were after
the polling loop it would be skipped by exactly the exception that means
somebody pressed Cancel, and the job would run to completion on the cluster
with nothing pointing at it.

WHY EVERY JOB IS NAMED AFTER ITS RUN ID

There is a window between `sbatch` returning and its id being written down.
A cancel arriving in that window has no id to cancel. `--job-name=<rid>` is
what closes it: `scancel -u $USER -n <rid>` works whether or not anybody ever
learned the number.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

from . import cfc, vacc

# The clock and the sleep, as module attributes so a test can run a whole
# thirty-minute outage in a millisecond. Looked up at call time.
CLOCK = time.time
SLEEP = time.sleep


def _sleep(s):
    SLEEP(s)


# --------------------------------------------------------------------------
# When the login node does not answer
# --------------------------------------------------------------------------
# A poll is a fresh ssh connection every few seconds for as long as a job
# runs, and a login node shared with everybody else's interactive work drops
# some of them: a timeout, a refused connection, a reset in the middle of a
# handshake. None of that says anything about the JOB. Before this, one such
# poll raised out of `wait`, the `finally` read the run as unfinished, and
# scancelled a perfectly healthy job -- the flakiest link in the chain got to
# kill the most expensive thing in it.
#
# So a poll that fails is retried, with backoff, for up to half an hour. If
# the cluster is still silent after that the run is DETACHED, not failed: the
# job is left running where it is, and a run that was written down
# (`RunLog`) is picked up again on the next start. Only a run nothing points
# at is cancelled on the way out, because a job with nothing pointing at it
# is the one outcome that costs somebody else.
POLL_RETRY_BASE_S = 5.0
POLL_RETRY_CAP_S = 60.0
POLL_RETRY_LIMIT_S = 1800.0
# Bringing an answer home is shorter: the job is finished and the file is
# there, so five minutes of silence is worth saying out loud.
FETCH_RETRY_LIMIT_S = 300.0
# Kinds that are answers, not silences. Retrying them asks the same
# question and gets the same answer.
NO_RETRY = ("garbled", "no-jobid", "vanished", "detached", "no-result")
_NO_RESULT = "__JARVIS_NO_RESULT__"


class Detached(vacc.SSHError):
    """The cluster stopped answering and the job was left where it is."""

    def __init__(self, message, stderr=""):
        super().__init__(message, "detached", stderr)


def retrying(call, job=None, what="the cluster", limit_s=None, note=None):
    """`call()`, retried through ssh failures. Raises `Detached` at the limit.

    Cancellation still lands between attempts: `job.check()` runs before
    each one. Anything that is not an `SSHError` goes straight through --
    this is for a connection that did not answer, not for a bug.
    """
    first, n = None, 0
    lim = POLL_RETRY_LIMIT_S if limit_s is None else float(limit_s)
    while True:
        if job is not None:
            job.check()
        try:
            return call()
        except vacc.SSHError as exc:
            if getattr(exc, "kind", None) in NO_RETRY:
                raise
            now = CLOCK()
            first = first if first is not None else now
            n += 1
            if note is not None:
                try:
                    note("the cluster did not answer about %s (try %d): %s"
                         % (what, n, exc))
                except Exception:                        # noqa: BLE001
                    pass
            if now - first >= lim:
                raise Detached(
                    "Jarvis lost contact with the cluster while asking about "
                    "%s: %d tries over %d s, the last saying “%s”. "
                    "Nothing was cancelled -- the work is still on the "
                    "cluster." % (what, n, int(now - first), exc),
                    getattr(exc, "stderr", ""))
            _sleep(min(POLL_RETRY_CAP_S,
                       POLL_RETRY_BASE_S * (2 ** min(n - 1, 8))))


def _job_note(job):
    """A `note` for `retrying` that lands in the job's log tail."""
    log = getattr(job, "log", None)
    if log is None:
        return None

    def note(line):
        log.append(line[:300])
        del log[:-40]
    return note


# --------------------------------------------------------------------------
# A run written down, so it outlives the process that submitted it
# --------------------------------------------------------------------------
class RunLog:
    """`GUI_logs/vacc_runs/<rid>.json`: one file per submitted run.

    Written at submit time with everything needed to pick the run up again
    -- the run id, the slurm id or array id, the workspace, the tool, and
    whatever the caller needs to file the answer (gids, cache keys, its own
    plan). A Jarvis restart used to orphan every job in flight: the thread
    polling it died with the process, and the answer sat in scratch until
    the purge took it. Now start-up reads the open records and re-attaches.

    Opt-in. A tool that passes no RunLog behaves exactly as before.
    Machine-local and git-ignored: a record names a job THIS machine's
    process was driving, and another clone re-attaching to it would be two
    processes filing one answer.
    """

    OPEN = ("submitted", "running", "fetched")

    def __init__(self, logs_dir):
        self.root = os.path.join(os.path.abspath(logs_dir), "vacc_runs")
        self._lock = threading.Lock()

    def _path(self, rid):
        vacc.check_rid(rid)
        return os.path.join(self.root, "%s.json" % rid)

    def write(self, rec):
        rec = dict(rec)
        rec.setdefault("status", "submitted")
        rec.setdefault("submitted_at", CLOCK())
        path = self._path(rec["rid"])
        with self._lock:
            os.makedirs(self.root, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, indent=1, sort_keys=True, default=str)
            os.replace(tmp, path)
        return rec

    def get(self, rid):
        try:
            with open(self._path(rid), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def update(self, rid, **patch):
        with self._lock:
            rec = self.get(rid)
        if rec is None:
            return None
        rec.update(patch)
        return self.write(rec)

    def close(self, rid, status, why=None):
        return self.update(rid, status=status, why=why, closed_at=CLOCK())

    def open_runs(self, tool=None):
        """Every run still waiting for an answer, oldest first."""
        out = []
        try:
            names = sorted(os.listdir(self.root))
        except OSError:
            return out
        for name in names:
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.root, name), "r",
                          encoding="utf-8") as fh:
                    rec = json.load(fh)
            except (OSError, ValueError):
                continue
            if rec.get("status") not in self.OPEN:
                continue
            if tool and rec.get("tool") != tool:
                continue
            out.append(rec)
        out.sort(key=lambda r: r.get("submitted_at") or 0)
        return out

# How often to ask the cluster, by what the job is doing.
#
# A round trip to the login node is about 0.4 s (`vacc.ROUND_TRIP_S`), so
# these are chosen for the cluster's sake rather than ours: a job that will
# sit in the queue for an hour does not need asking about every two seconds,
# and every one of these connections lands on a login node shared with
# everybody else's interactive work.
#
# Queued is the slowest deliberately. Nothing about a pending job changes
# except the moment it stops being pending, and a minute's lag on that is
# invisible next to the wait itself.
POLL = {"staging": 5.0, "queued": 30.0, "running": 10.0, "fetching": 2.0}

# Stages a remote run adds in front of whatever the tool itself does. They
# have to exist in `cfc.STAGES` or `Job.begin` drops them silently and the
# run shows no progress at all while working perfectly.
#
# This is the DECLARATION -- (name, what its units are called). A `cfc.start`
# plan is a different shape with the same arity, (name, how many units), and
# passing one where the other belongs fails inside `Job.__init__` on an
# `int()` of the word "files". `steps()` below builds the plan, so the two
# are never written out by hand next to each other.
STAGE_UNITS = [("vacc stage", "files"), ("vacc queue", "jobs"),
               ("vacc fetch", "files")]


def steps(n_stage=0, n_fetch=1):
    """The `cfc.start` plan for the offload stages.

    `n_stage` is 0 for a recording the cluster already reads in place, which
    is the common case here -- and a stage with no units is left out
    entirely rather than shown as a step that instantly completes.
    """
    out = []
    if n_stage:
        out.append(("vacc stage", int(n_stage)))
    out.append(("vacc queue", 1))
    out.append(("vacc fetch", int(n_fetch)))
    return out


class VaccArray:
    """Many recordings at once, as one slurm job array.

    The first version of this submitted one job, waited for it, submitted
    the next, and waited for that -- twenty-eight recordings in series, each
    one queueing on its own, using a several-thousand-core cluster as a
    slow single machine. Forty minutes of wall clock to do about ninety
    seconds of work at a time.

    An array is what slurm has for exactly this, and it is what this lab's
    own `.sbat` files already use: `#SBATCH --array=1-9` beside a `dirs=()`
    indexed by `$SLURM_ARRAY_TASK_ID`. One submit, N tasks, all queued at
    once, and -- because `poll_states` was always built to take a LIST --
    one connection to ask about all of them.

    `%N` on the array range caps how many run at a time. It is worth having
    rather than letting twenty-eight tasks all read the same filesystem at
    once: the VACC's own documentation warns that netfiles degrades when
    many programs touch many files simultaneously, and scratch is shared
    with everybody else's jobs too.
    """

    def __init__(self, cfg, tool, jobs, ssh=None, concurrency=None):
        # `jobs` is [{gid, label, spec_local, spec_remote, report}].
        self.cfg = cfg
        self.tool = tool
        self.jobs = list(jobs)
        self.rid = vacc.new_rid()
        self.array_id = None
        self.concurrency = concurrency
        self._ssh = vacc._runner(cfg, ssh)
        self.ws = vacc._remote_path(cfg.get("workspace") or ".", "runs",
                                    self.rid)
        # Opt-in persistence (fix 4). `record` is the caller's own part of
        # the run record -- whatever it needs to file the answers after a
        # restart; each job's `resume` is kept beside its specs.
        self.runlog = None
        self.record = {}
        self.submitted_at = None

    @classmethod
    def reattach(cls, cfg, rec, ssh=None):
        """The array a run record describes, ready to be polled again."""
        jobs = [dict(j) for j in (rec.get("jobs") or [])]
        arr = cls(cfg, rec.get("tool"), jobs, ssh=ssh)
        arr.rid = vacc.check_rid(rec["rid"])
        arr.array_id = str(rec["array_id"])
        arr.ws = rec.get("workspace") or vacc._remote_path(
            cfg.get("workspace") or ".", "runs", arr.rid)
        arr.submitted_at = rec.get("submitted_at")
        arr.record = dict(rec.get("record") or {})
        return arr

    def _write_record(self, job=None):
        if self.runlog is None:
            return
        keep = ("gid", "member", "label", "spec_local", "spec_remote",
                "tool_steps", "seconds", "megasamples", "resume")
        self.runlog.write({
            "rid": self.rid, "kind": "array", "tool": self.tool,
            "array_id": self.array_id, "workspace": self.ws,
            "submitted_at": self.submitted_at,
            "job_id": getattr(job, "id", None) or self.record.get("job_id"),
            "gids": sorted({j.get("gid") for j in self.jobs if j.get("gid")}),
            "jobs": [{k: j.get(k) for k in keep if k in j} for j in self.jobs],
            "taken": [], "record": self.record,
        })

    def submit(self, seconds=600, megasamples=1.0):
        """Write every spec, then one sbatch. Returns the array job id."""
        vacc.check_rid(self.rid)
        req = vacc.slurm_request(seconds, megasamples,
                                 self.cfg.get("partition"))
        n = len(self.jobs)
        cap = ("%%%d" % int(self.concurrency)) if self.concurrency else ""

        parts = ["set -e", "mkdir -p %s" % vacc.q(self.ws)]
        for i, j in enumerate(self.jobs):
            payload = json.dumps({
                "rid": "%s_%d" % (self.rid, i), "tool": self.tool,
                "spec": j["spec_remote"], "plan": {},
                "stages": [n2 for n2, _ in (j.get("tool_steps") or [])],
                "report": j.get("report"),
            })
            parts.append("cat > %s/spec_%d.json <<'JARVIS_SPEC_EOF'\n%s\n"
                         "JARVIS_SPEC_EOF" % (vacc.q(self.ws), i, payload))

        submit_sh = (
            "#!/bin/bash\n"
            "#SBATCH --job-name=%(rid)s\n"
            "#SBATCH --array=0-%(last)d%(cap)s\n"
            "%(acct)s"
            "#SBATCH --partition=%(part)s\n"
            "#SBATCH --time=%(time)s\n"
            "#SBATCH --mem=%(mem)s\n"
            "#SBATCH --cpus-per-task=%(cpus)d\n"
            "#SBATCH --nodes=1\n"
            "#SBATCH --ntasks=1\n"
            "#SBATCH --output=%(ws)s/%%A_%%a.out\n"
            "#SBATCH --mail-type=NONE\n"
            "%(pre)s\n"
            "cd %(code)s\n"
            "exec python vacc_run.py %(ws)s/spec_${SLURM_ARRAY_TASK_ID}.json\n"
        ) % {
            "rid": self.rid, "last": max(0, n - 1), "cap": cap,
            "acct": vacc.sbatch_account(self.cfg),
            "part": req["partition"], "time": req["time"], "mem": req["mem"],
            "cpus": req["cpus"], "ws": self.ws,
            "pre": vacc.activate(self.cfg),
            "code": vacc._remote_path(self.cfg.get("workspace") or ".", "code"),
        }
        parts.append("cat > %s/submit.sh <<'JARVIS_SH_EOF'\n%s"
                     "JARVIS_SH_EOF" % (vacc.q(self.ws), submit_sh))
        parts.append("cd %s && sbatch --parsable submit.sh" % vacc.q(self.ws))

        out = self._ssh("bash -s", stdin="\n".join(parts) + "\n", timeout=120)
        for line in reversed((out or "").strip().splitlines()):
            got = line.strip().split(";")[0].strip()
            if got.isdigit():
                self.array_id = got
                break
        if not self.array_id:
            raise vacc.SSHError("The cluster did not return an array job id.",
                                "no-jobid", out)
        self.submitted_at = CLOCK()
        try:
            self._write_record()
        except Exception:                                # noqa: BLE001
            pass            # a record that cannot be written costs a resume
        return self.array_id

    def poll(self):
        """Every task's state, and which results have landed. ONE call.

        States and the result listing together: asking slurm what is running
        and the filesystem what has finished are two questions about the
        same thing, and two connections to answer them would be two
        connections per poll for as long as the array runs.
        """
        script = (
            "sacct -n -X -j %(a)s -o 'JobID,State' -P 2>/dev/null\n"
            "echo '--'\n"
            "ls -1 %(ws)s/result_*.json 2>/dev/null | sed 's#.*/##'\n"
        ) % {"a": vacc.q(str(self.array_id)), "ws": vacc.q(self.ws)}
        raw = self._ssh("bash -s", stdin=script, timeout=60)
        states, done, half = {}, [], 0
        for line in (raw or "").splitlines():
            line = line.strip()
            if line == "--":
                half = 1
                continue
            if not line:
                continue
            if half == 0:
                bits = line.split("|")
                jid = bits[0].split(".")[0]
                st = vacc.read_state(bits[1] if len(bits) > 1 else "")
                # `12345_7` -> task 7. The parent row has no underscore and
                # is not a task.
                #
                # `12345_[2-5%2]` is every task still PENDING, folded into
                # one row. Read as "not in sacct" it would have every queued
                # task of a long queue look vanished, and the grace below
                # for a task that never appears would fail them all.
                if "_[" in jid:
                    for i in _task_range(jid.split("_[", 1)[1]):
                        states.setdefault(i, st)
                elif "_" in jid:
                    try:
                        states[int(jid.rsplit("_", 1)[1])] = st
                    except ValueError:
                        pass
            else:
                m = re.match(r"^result_(\d+)\.json$", line)
                if m:
                    done.append(int(m.group(1)))
        return states, set(done)

    def fetch(self, index):
        """One task's answer, localised for the recording it belongs to."""
        raw = self._ssh("cat %s/result_%d.json"
                        % (vacc.q(self.ws), int(index)), timeout=180)
        try:
            out = json.loads(raw)
        except ValueError:
            raise vacc.SSHError("A task finished but its answer could not be "
                                "read.", "garbled", (raw or "")[:400])
        j = self.jobs[index]
        shim = VaccRun(self.cfg, self.tool, j["spec_local"],
                       j["spec_remote"].get("path"), ssh=self._ssh)
        shim.array_id = self.array_id
        shim.slurm_id = "%s_%d" % (self.array_id, index)
        out = shim.relocalize(out)
        # Where the full answer still sits, so any machine can fetch it
        # again (constitution section 6d). The shim's own rid is not this
        # array's, and the run directory is in the workspace, which is
        # backed up and not purged -- the per-channel events are megabytes
        # and are only cached on the machine that filed them.
        on = dict(out.get("computed_on") or {"kind": "vacc",
                                              "host": self.cfg.get("host"),
                                              "netid": self.cfg.get("netid")})
        on.update(slurm_id=shim.slurm_id, rid=self.rid, workspace=self.ws,
                  file="result_%d.json" % int(index))
        out["computed_on"] = on
        return out

    def cancel(self):
        if self.array_id:
            try:
                vacc.cancel(self.cfg, self.array_id, self.rid, ssh=self._ssh)
            except Exception:                            # noqa: BLE001
                pass


def _task_range(text):
    """`2-5%2]` or `0,3,7-9]` -> the task indices it names."""
    body = str(text or "").rstrip("]").split("%")[0]
    out = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
        except ValueError:
            continue
    return out


# How long a batch may take, all told, before what is left is cancelled and
# reported. A day: the general partition's cap is two, and a batch of
# circuits that has not finished in a day is stuck rather than slow.
BATCH_DEADLINE_S = 24 * 3600.0
# A task slurm calls COMPLETED whose answer file has not appeared. The
# filesystem normally leads the accounting database, so a short wait covers
# a listing that raced the write; past it, the task finished without writing
# an answer -- a node that died between the two, a script that exited 0 on
# an exception -- and waiting longer only hides that.
RESULT_GRACE_S = 180.0
# A task sacct never mentions at all -- not as itself, not inside a pending
# range. Given the accounting lag and then some.
UNSEEN_GRACE_S = 900.0


def collect(job, arr, tasks, on_result, failed=0, deadline_s=None,
            taken=None, member_of=None):
    """Poll an array until every task is answered, failed, or out of time.

    The loop `_vacc_run_array` used to hold inline, moved here so it can be
    driven against a fake login node, and with three things it lacked:

      * an ssh error from a poll is retried (`retrying`), not raised -- it
        used to escape the loop with the array still running and nothing
        pointing at it;
      * a batch that really fails cancels its array on the way out;
      * a task that COMPLETED with no answer, or that sacct never reports,
        is failed with a sentence after a grace period, and the whole batch
        has a deadline -- before, either one waited for ever.

    `on_result(i, task, out)` files one answer. `taken` is what a resumed
    run already filed. Returns (done, failed).
    """
    mid = member_of or (lambda t: t.get("member") or t.get("gid"))
    start = CLOCK()
    if arr.submitted_at:
        start = min(start, float(arr.submitted_at))
    deadline = start + float(deadline_s or BATCH_DEADLINE_S)
    taken = set(taken or ())
    done = 0
    finished_at, unseen_since = {}, {}
    note = _job_note(job)

    def mark(i):
        taken.add(i)
        if arr.runlog is not None:
            try:
                arr.runlog.update(arr.rid, taken=sorted(taken),
                                  status="running")
            except Exception:                            # noqa: BLE001
                pass

    try:
        while True:
            job.check()
            states, ready = retrying(arr.poll, job,
                                     "array %s" % arr.array_id, note=note)
            now = CLOCK()
            for i in sorted(ready - taken):
                if i >= len(tasks):
                    continue
                t = tasks[i]
                try:
                    out = retrying(lambda i=i: arr.fetch(i), job,
                                   "the answer of task %d" % i,
                                   limit_s=FETCH_RETRY_LIMIT_S, note=note)
                except (cfc.Canceled, Detached):
                    raise
                except Exception as exc:                 # noqa: BLE001
                    mark(i)
                    failed += 1
                    job.member(mid(t), status="failed", step=None,
                               error=str(exc)[:200], why=str(exc)[:200])
                    continue
                mark(i)
                try:
                    on_result(i, t, out)
                    done += 1
                    job.member(mid(t), status="done", step=None)
                except cfc.Canceled:
                    raise
                except Exception as exc:                 # noqa: BLE001
                    failed += 1
                    job.member(mid(t), status="failed", step=None,
                               error=str(exc)[:200], why=str(exc)[:200])
                out = None
            for i, t in enumerate(tasks):
                if i in taken:
                    continue
                st = states.get(i)
                if not st:
                    unseen_since.setdefault(i, now)
                    if (now - start > UNSEEN_GRACE_S and
                            now - unseen_since[i] > vacc.LAG_GRACE_S):
                        mark(i)
                        failed += 1
                        why = ("The cluster never reported task %d of array "
                               "%s -- not queued, not running, not finished "
                               "-- in %d s, and no answer arrived."
                               % (i, arr.array_id, int(now - start)))
                        job.member(mid(t), status="failed", step=None,
                                   error=why[:200], why=why[:200])
                    else:
                        job.member(mid(t), status="queued", step="waiting")
                    continue
                unseen_since.pop(i, None)
                out = vacc.outcome_for(st)
                if out is None:
                    job.member(mid(t),
                               status="running" if st == "RUNNING"
                               else "queued", step=st.lower())
                    continue
                if out[0] == "done":
                    finished_at.setdefault(i, now)
                    if now - finished_at[i] > RESULT_GRACE_S:
                        mark(i)
                        failed += 1
                        why = ("Task %d finished on the cluster (COMPLETED) "
                               "but wrote no answer in the %d s since. Its "
                               "log is %s/%s_%d.out." % (
                                   i, int(now - finished_at[i]), arr.ws,
                                   arr.array_id, i))
                        job.member(mid(t), status="failed", step=None,
                                   error=why[:200], why=why[:200])
                    else:
                        job.member(mid(t), status="running",
                                   step="fetching")
                    continue
                mark(i)
                failed += 1
                job.member(mid(t), status="failed", step=None,
                           error=out[1] or out[0], why=out[1] or out[0])
            if len(taken) >= len(tasks):
                break
            if now > deadline:
                arr.cancel()
                left = [i for i in range(len(tasks)) if i not in taken]
                why = ("The batch did not finish within %d h, so what was "
                       "left was cancelled on the cluster."
                       % int(round((deadline - start) / 3600.0)))
                for i in left:
                    mark(i)
                    failed += 1
                    job.member(mid(tasks[i]), status="failed", step=None,
                               error=why, why=why)
                break
            _sleep(POLL["running"])
    except cfc.Canceled:
        arr.cancel()
        if arr.runlog is not None:
            arr.runlog.close(arr.rid, "canceled")
        raise
    except Detached:
        # Lost contact, not a failure of the work. A written-down array is
        # left for the next start to pick up; one nothing points at is
        # cancelled, if the cluster will take the message.
        if arr.runlog is None:
            arr.cancel()
        raise
    except Exception as exc:
        arr.cancel()
        if arr.runlog is not None:
            arr.runlog.close(arr.rid, "failed", str(exc)[:300])
        raise
    if arr.runlog is not None:
        arr.runlog.close(arr.rid, "done")
    return done, failed


class VaccRun:
    """One run on the cluster. Built by a route, driven by `cfc.start`."""

    def __init__(self, cfg, tool, spec_local, remote_path, plan=None,
                 megasamples=1.0, ssh=None, tool_steps=None, report=None):
        self.cfg = cfg
        self.tool = tool
        # The stages the TOOL itself will report, e.g. ("ds read", 1800).
        # They are declared in one place and used twice -- to build the local
        # plan, and as the vocabulary the remote shim asserts against -- so a
        # stage the cluster emits and the poller has never heard of is a
        # startup error there rather than silence here. `Job.begin` on an
        # unknown name returns without a word, which is a run that works
        # perfectly and shows no progress at all.
        self.tool_steps = list(tool_steps or [])
        # Travels with the spec rather than being recomputed on the far side:
        # it is inside the cache key, and a segmentation that came out even
        # slightly differently there would file the answer under a name no
        # local run ever looks for.
        self.report = report
        # Two specs, and conflating them is the subtle failure. The LOCAL one
        # is the identity: it is what `params_hash` is taken from, what the
        # cache is keyed on and what appears on screen. The remote one
        # differs in exactly one field -- the path -- and exists only to be
        # executed. If the hash were taken from the remote spec, the cluster
        # would write its answers under a name no local run ever looks for,
        # resume would quietly stop working, and every screen would still
        # look right.
        self.spec_local = dict(spec_local or {})
        self.spec_remote = dict(self.spec_local, path=remote_path)
        self.plan = plan or {}
        self.megasamples = megasamples
        self.rid = vacc.new_rid()
        self.slurm_id = None
        self.state = "staging"
        self.last_error = None
        self._ssh = vacc._runner(cfg, ssh)
        self._gone_since = None
        # Following the node's log. `vacc_run.py` writes one JSON line per
        # stage begin and tick to stdout, which slurm puts in the run's
        # `.out` file -- and until this, nothing ever read it back, so a
        # forty-minute run showed "waiting for the cluster" for forty
        # minutes and then was done.
        self.ws = None
        self._log_off = 0
        self._log_buf = ""
        self._declared = set(n for n, _u in (tool_steps or []))
        # Opt-in persistence (fix 4): a `RunLog` to write this run into at
        # submit time, and the caller's own part of the record -- whatever
        # it needs to file the answer after a restart.
        self.runlog = None
        self.record = {}
        self.submitted_at = None
        # Member ids the node may report (`{"k": "member"}` lines). Empty
        # for every tool that does not declare any.
        self.members = []

    @classmethod
    def reattach(cls, cfg, rec, ssh=None):
        """The run a `RunLog` record describes, ready to `work` again.

        `work` sees the slurm id and skips the submit: it goes straight to
        polling, and fetches the answer if the job finished while nobody
        was watching.
        """
        run = cls(cfg, rec.get("tool"), rec.get("spec_local") or {},
                  rec.get("remote"), plan=rec.get("plan") or {},
                  tool_steps=[tuple(s) for s in (rec.get("tool_steps") or [])])
        if ssh is not None:
            run._ssh = ssh
        run.rid = vacc.check_rid(rec["rid"])
        run.slurm_id = str(rec["slurm_id"])
        run.ws = rec.get("workspace") or vacc._remote_path(
            cfg.get("workspace") or ".", "runs", run.rid)
        run.state = "queued"
        run.submitted_at = rec.get("submitted_at")
        run.record = dict(rec.get("record") or {})
        run.members = list(rec.get("members") or [])
        return run

    def _write_record(self, job):
        if self.runlog is None:
            return
        self.runlog.write({
            "rid": self.rid, "kind": "single", "tool": self.tool,
            "slurm_id": self.slurm_id, "workspace": self.ws,
            "remote": self.spec_remote.get("path"),
            "spec_local": self.spec_local, "plan": self.plan,
            "tool_steps": [list(s) for s in self.tool_steps],
            "members": self.members,
            "submitted_at": self.submitted_at,
            "job_id": getattr(job, "id", None),
            "record": self.record,
        })

    def close_record(self, status, why=None):
        """Say the run is over. The caller does this once the answer is
        FILED, not merely fetched: a restart between the two re-fetches."""
        if self.runlog is None:
            return
        try:
            self.runlog.close(self.rid, status, why)
        except Exception:                                # noqa: BLE001
            pass

    # -- the thing cfc.start wants ------------------------------------------
    def work(self, job):
        """Block until the cluster has an answer. Returns it."""
        note = _job_note(job)
        try:
            job.begin("vacc queue", of=1, unit="jobs")
            if self.slurm_id is None:
                self.submit(job)
            self.wait(job)
            job.begin("vacc fetch", of=1, unit="files")
            out = retrying(lambda: self.fetch(job), job, "the answer",
                           limit_s=FETCH_RETRY_LIMIT_S, note=note)
            job.tick("vacc fetch", 1)
            if self.runlog is not None:
                try:
                    self.runlog.update(self.rid, status="fetched")
                except Exception:                        # noqa: BLE001
                    pass
            return out
        except Detached:
            # Still running there, or finished and not yet fetched. Left
            # alone; the record (if any) stays open for the next start.
            if self.state != "done":
                self.state = "detached"
            raise
        except cfc.Canceled:
            self.close_record("canceled")
            raise
        except Exception as exc:
            self.close_record("failed", str(exc)[:300])
            raise
        finally:
            # Whatever happened -- finished, failed, or Canceled raised out of
            # a `tick` -- a job left running on a shared cluster with nothing
            # pointing at it is the one outcome that costs somebody else.
            if self._unfinished():
                try:
                    vacc.cancel(self.cfg, self.slurm_id, self.rid,
                                ssh=self._ssh)
                except Exception:                    # noqa: BLE001
                    pass

    def _unfinished(self):
        if self.state == "detached":
            # Lost contact is not a failed job. Cancel it only when nothing
            # will ever come back for it.
            return self.runlog is None and self.slurm_id is not None
        return self.state not in ("done", "gone") and (
            self.slurm_id is not None or self.state in ("queued", "running",
                                                        "submitting"))

    # -- submit --------------------------------------------------------------
    def submit(self, job):
        """Write the spec, write the script, sbatch it, keep the id.

        No path is ever interpolated into a command. The spec goes in on
        stdin and the script reads it with `json.load`, so the remote command
        line is a fixed vocabulary with a checked hex id in it and nothing
        else. Lab paths contain spaces, ampersands and apostrophes -- `VACC
        Code/KCNT1 Urethane/` is in this repository -- and every one of those
        is a metacharacter to the login shell.
        """
        self.state = "submitting"
        vacc.check_rid(self.rid)
        ws = vacc._remote_path(self.cfg.get("workspace") or ".", "runs", self.rid)
        self.ws = ws
        req = vacc.slurm_request(self.plan.get("seconds") or 0,
                                 self.megasamples,
                                 self.cfg.get("partition"))
        payload = json.dumps({
            "rid": self.rid, "tool": self.tool, "spec": self.spec_remote,
            "plan": self.plan,
            # The stage vocabulary, declared once and asserted on both ends.
            "stages": [n for n, _ in self.tool_steps],
            "report": self.report,
            # Member ids the node may report on, for a tool whose progress is
            # per item (Circuit: per cue pair). Empty for the others.
            "members": list(self.members),
        })
        # A real script rather than `--wrap`, for two reasons: the preamble is
        # several lines and `--wrap` is one, and a file left in the run
        # directory is something a person can read, edit and `sbatch` by hand
        # when they want to know what actually ran.
        #
        # Both files arrive inside quoted heredocs, so nothing in the spec or
        # the paths is seen by the shell. That is the same discipline as
        # sending the spec on stdin, extended to the script.
        submit_sh = (
            "#!/bin/bash\n"
            "#SBATCH --job-name=%(rid)s\n"
            "%(acct)s"
            "#SBATCH --partition=%(part)s\n"
            "#SBATCH --time=%(time)s\n"
            "#SBATCH --mem=%(mem)s\n"
            "#SBATCH --cpus-per-task=%(cpus)d\n"
            "#SBATCH --nodes=1\n"
            "#SBATCH --ntasks=1\n"
            "#SBATCH --output=%(ws)s/%(rid)s_%%j.out\n"
            "#SBATCH --mail-type=NONE\n"
            "%(pre)s\n"
            "cd %(code)s\n"
            "exec python vacc_run.py %(ws)s/spec.json\n"
        ) % {
            "rid": self.rid, "part": req["partition"], "time": req["time"],
            "mem": req["mem"], "cpus": req["cpus"], "ws": ws,
            "acct": vacc.sbatch_account(self.cfg),
            "pre": vacc.activate(self.cfg),
            "code": vacc._remote_path(self.cfg.get("workspace") or ".", "code"),
        }
        script = (
            "set -e\n"
            "mkdir -p %(ws)s\n"
            "cat > %(ws)s/spec.json <<'JARVIS_SPEC_EOF'\n%(spec)s\n"
            "JARVIS_SPEC_EOF\n"
            "cat > %(ws)s/submit.sh <<'JARVIS_SH_EOF'\n%(sh)s"
            "JARVIS_SH_EOF\n"
            "cd %(ws)s && sbatch --parsable submit.sh\n"
        ) % {"ws": vacc.q(ws), "spec": payload, "sh": submit_sh}
        out = self._ssh("bash -s", stdin=script, timeout=60)
        for line in reversed((out or "").strip().splitlines()):
            digits = line.strip().split(";")[0].strip()
            if digits.isdigit():
                self.slurm_id = digits
                break
        if not self.slurm_id:
            raise vacc.SSHError("The cluster did not return a job id.",
                                "no-jobid", out)
        self.state = "queued"
        self.submitted_at = CLOCK()
        try:
            self._write_record(job)
        except Exception:                                # noqa: BLE001
            pass            # a record that cannot be written costs a resume
        job.tick("vacc queue", 0)
        return self.slurm_id

    # How much of the log one poll will take. A run that prints a
    # traceback in a loop must not become a multi-megabyte ssh every ten
    # seconds; the rest arrives on the next poll.
    FOLLOW_MAX = 262144

    def follow(self, job):
        """Read what the node has written since last time, and replay it.

        Progress lines become `begin` and `tick` on the local job, so the
        panel shows the reading happening on the node rather than a queue
        stage that lasts the whole run. Replaying `begin` also CLOSES the
        queue stage the way a local stage change would -- and the seconds
        that stage then records are real cluster timings, which is what
        `cfc` learns its VACC rates from.

        Anything that is not a progress line is kept as the job's log tail.

        Best effort, always. A log that cannot be read this poll is read on
        the next one, and a failure here must never fail a run that is
        working -- `job.check()` is the only exception let through, because
        that is cancellation.
        """
        if not (self.ws and self.slurm_id):
            return
        path = "%s/%s_%s.out" % (self.ws, self.rid, self.slurm_id)
        cmd = ("f=%s; if [ -f \"$f\" ]; then tail -c +%d \"$f\" | head -c %d; fi"
               % (vacc.q(path), self._log_off + 1, self.FOLLOW_MAX))
        try:
            out = self._ssh(cmd, timeout=30) or ""
        except Exception:                                # noqa: BLE001
            return
        if not out:
            return
        self._log_off += len(out.encode("utf-8"))
        text = self._log_buf + out
        lines = text.split("\n")
        # The last piece may be half a line; keep it for next time.
        self._log_buf = lines.pop() if not text.endswith("\n") else ""
        log = getattr(job, "log", None)
        for ln in lines:
            ln = ln.rstrip("\r")
            if not ln:
                continue
            msg = None
            if ln.startswith("{"):
                try:
                    msg = json.loads(ln)
                except ValueError:
                    msg = None
            if isinstance(msg, dict) and msg.get("k") in ("begin", "tick"):
                name = msg.get("stage")
                # Only stages this run declared. The node checks the same
                # vocabulary, so a mismatch here is a bug on one end and
                # replaying it would corrupt the other tool's learned rate.
                if name not in self._declared:
                    continue
                if msg["k"] == "begin":
                    job.begin(name, of=msg.get("of"), unit=msg.get("unit"))
                else:
                    job.tick(name, int(msg.get("done") or 0))
                continue
            if isinstance(msg, dict) and msg.get("k") == "member":
                # Per-item progress (a cue pair computing on the node). Only
                # ids this run declared, and only scalars -- `Job.member`
                # refuses anything else, and a local job with no such member
                # ignores it.
                mid = msg.get("id")
                if mid in self.members:
                    patch = {k: v for k, v in msg.items()
                             if k in ("status", "step", "done", "of")
                             and not isinstance(v, (list, dict))}
                    try:
                        job.member(mid, **patch)
                    except Exception:                    # noqa: BLE001
                        pass
                continue
            if isinstance(msg, dict) and msg.get("k") == "fatal":
                ln = "fatal: " + str(msg.get("error") or "")
            elif isinstance(msg, dict):
                continue            # done / result markers: not for people
            if log is not None:
                log.append(ln[:300])
                del log[:-40]

    def _wrap(self, ws):
        """What the compute node runs.

        The preamble comes from `vacc.activate` rather than being rebuilt
        here, so the environment a job gets is the same one `env_check`
        reported on. Two spellings of `module load` is two chances for the
        thing that ran to not be the thing that was checked.
        """
        code = vacc._remote_path(self.cfg.get("workspace") or ".", "code")
        return "%s\ncd %s && python vacc_run.py %s/spec.json" % (
            vacc.activate(self.cfg), vacc.q(code), vacc.q(ws))

    # -- wait ----------------------------------------------------------------
    def wait(self, job, deadline=None):
        """Poll the cluster until the job is finished, one way or another."""
        note = _job_note(job)
        while True:
            job.check()                      # raises Canceled; see the finally
            # Retried through ssh failures (fix 1). One dropped connection
            # used to raise straight out of here into the `finally` of
            # `work`, which then scancelled a job that was running fine.
            states = retrying(
                lambda: vacc.poll_states(self.cfg, [self.slurm_id],
                                         ssh=self._ssh),
                job, "job %s" % self.slurm_id, note=note)
            got = states.get(str(self.slurm_id))

            if got is None:
                # Neither squeue nor sacct. Usually the accounting database
                # catching up, NOT a vanished job -- calling this "gone"
                # fails runs that actually succeeded.
                now = CLOCK()
                self._gone_since = self._gone_since or now
                if (now - self._gone_since) > vacc.LAG_GRACE_S:
                    self.state = "gone"
                    raise vacc.SSHError(
                        "The cluster stopped reporting this job and no result "
                        "arrived.", "vanished")
                _sleep(POLL["running"])
                continue
            self._gone_since = None

            state = got.get("state")
            outcome = vacc.outcome_for(state)
            if outcome is None:
                self.state = "running" if state == "RUNNING" else "queued"
                if self.state == "running":
                    job.tick("vacc queue", 1)
                    self.follow(job)
                _sleep(POLL[self.state])
                continue

            # Once more at the end, for whatever arrived since the last
            # poll -- which includes the traceback of a run that died.
            self.follow(job)
            kind, why = outcome
            self.state = "done" if kind == "done" else kind
            self.max_rss = got.get("max_rss")
            if kind == "done":
                job.tick("vacc queue", 1)
                return got
            if kind == "canceled":
                # Into the canceled bucket rather than the failed one:
                # `Job.fail` branches on the exception type, and a run
                # somebody stopped is not a run that broke.
                raise cfc.Canceled(why)
            # What the node itself said last, on the error. "The job
            # failed" is not something anybody can act on; "MemoryError" is.
            tail = [ln for ln in (getattr(job, "log", None) or [])
                    if ln.strip()][-3:]
            if tail:
                why = (why or kind) + " -- the node said: " + " | ".join(tail)
            self.last_error = why
            raise vacc.SSHError(why, kind)

    # -- fetch ---------------------------------------------------------------
    def fetch(self, job):
        """Bring the answer home and put the local path back into it.

        The answer is the numbers, not the pictures -- a spectrogram is
        megabytes and regenerable in milliseconds, so it stays on the cluster
        and what crosses the wire is about thirty kilobytes a recording.
        """
        ws = self.ws or vacc._remote_path(self.cfg.get("workspace") or ".",
                                          "runs", self.rid)
        # A missing file is an answer ("it wrote nothing"), not a silence,
        # so it is said as one rather than surfacing as a failed ssh that
        # `retrying` would ask about again for five minutes.
        raw = self._ssh("f=%s/result.json; if [ -f \"$f\" ]; then cat \"$f\"; "
                        "else echo %s; fi" % (vacc.q(ws), _NO_RESULT),
                        timeout=120)
        if (raw or "").strip() == _NO_RESULT:
            raise vacc.SSHError(
                "The job finished on the cluster but wrote no answer. Its log "
                "is %s/%s_%s.out." % (ws, self.rid, self.slurm_id),
                "no-result")
        try:
            out = json.loads(raw)
        except ValueError:
            raise vacc.SSHError(
                "The job finished but its answer could not be read.",
                "garbled", (raw or "")[:400])
        return self.relocalize(out)

    def relocalize(self, out):
        """Put this machine's terms back on an answer that came over a wire.

        Two things, and the second is the one that bites.

        The path, because the result is about a recording and not about
        where the cluster keeps a copy of it -- a remote path left in here
        reaches the cache key, the result record and the screen.

        And the KEYS OF `_rows`, because JSON has no integer keys. Every
        channel index leaves here as an int and comes back as a string, and
        `incisor.events_for` looks up `int(index)` -- so the panel asked for
        channel 44, the dict had "44", and the answer was an empty list.
        Not an error: a cache hit, a valid response, and no events. The scan
        had worked perfectly and picked the right hilus.

        The same mismatch made the parity check report a maximum difference
        of zero while comparing nothing at all. Once is a bug; twice is the
        boundary being in the wrong place, so it is fixed here -- at the one
        point where a result stops being JSON and starts being a result.
        """
        rows = out.get("_rows")
        if isinstance(rows, dict):
            fixed = {}
            for k, v in rows.items():
                try:
                    fixed[int(k)] = v
                except (TypeError, ValueError):
                    fixed[k] = v
            out["_rows"] = fixed

        local = self.spec_local.get("path")
        remote = self.spec_remote.get("path")
        if not local or not remote or local == remote:
            return out

        def fix(node):
            if isinstance(node, str):
                return local if node == remote else node.replace(remote, local)
            if isinstance(node, list):
                return [fix(v) for v in node]
            if isinstance(node, dict):
                return dict((k, fix(v)) for k, v in node.items())
            return node

        out = fix(out)
        out["computed_on"] = {
            "kind": "vacc", "host": self.cfg.get("host"),
            "netid": self.cfg.get("netid"), "slurm_id": self.slurm_id,
            "rid": self.rid, "partition": self.cfg.get("partition"),
            # `provenance()` will stamp the machine that ACCEPTED this, which
            # is right for "who filed it" and wrong for "who computed it".
            # This is the only place the difference is recorded.
            "max_rss": getattr(self, "max_rss", None),
            # Where the whole answer still is, for a machine that has the
            # summary from the vault and not the per-channel events.
            "workspace": self.ws, "file": "result.json",
        }
        return out