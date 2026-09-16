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
import time

from . import cfc, vacc

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

    # -- the thing cfc.start wants ------------------------------------------
    def work(self, job):
        """Block until the cluster has an answer. Returns it."""
        try:
            job.begin("vacc queue", of=1, unit="jobs")
            self.submit(job)
            self.wait(job)
            job.begin("vacc fetch", of=1, unit="files")
            out = self.fetch(job)
            job.tick("vacc fetch", 1)
            return out
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
        req = vacc.slurm_request(self.plan.get("seconds") or 0,
                                 self.megasamples,
                                 self.cfg.get("partition"))
        payload = json.dumps({
            "rid": self.rid, "tool": self.tool, "spec": self.spec_remote,
            "plan": self.plan,
            # The stage vocabulary, declared once and asserted on both ends.
            "stages": [n for n, _ in self.tool_steps],
            "report": self.report,
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
        job.tick("vacc queue", 0)
        return self.slurm_id

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
        while True:
            job.check()                      # raises Canceled; see the finally
            states = vacc.poll_states(self.cfg, [self.slurm_id],
                                      ssh=self._ssh)
            got = states.get(str(self.slurm_id))

            if got is None:
                # Neither squeue nor sacct. Usually the accounting database
                # catching up, NOT a vanished job -- calling this "gone"
                # fails runs that actually succeeded.
                now = time.time()
                self._gone_since = self._gone_since or now
                if (now - self._gone_since) > vacc.LAG_GRACE_S:
                    self.state = "gone"
                    raise vacc.SSHError(
                        "The cluster stopped reporting this job and no result "
                        "arrived.", "vanished")
                time.sleep(POLL["running"])
                continue
            self._gone_since = None

            state = got.get("state")
            outcome = vacc.outcome_for(state)
            if outcome is None:
                self.state = "running" if state == "RUNNING" else "queued"
                if self.state == "running":
                    job.tick("vacc queue", 1)
                time.sleep(POLL[self.state])
                continue

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
            self.last_error = why
            raise vacc.SSHError(why, kind)

    # -- fetch ---------------------------------------------------------------
    def fetch(self, job):
        """Bring the answer home and put the local path back into it.

        The answer is the numbers, not the pictures -- a spectrogram is
        megabytes and regenerable in milliseconds, so it stays on the cluster
        and what crosses the wire is about thirty kilobytes a recording.
        """
        ws = vacc._remote_path(self.cfg.get("workspace") or ".", "runs", self.rid)
        raw = self._ssh("cat %s/result.json" % vacc.q(ws), timeout=120)
        try:
            out = json.loads(raw)
        except ValueError:
            raise vacc.SSHError(
                "The job finished but its answer could not be read.",
                "garbled", (raw or "")[:400])
        return self.relocalize(out)

    def relocalize(self, out):
        """Put this machine's path back wherever the remote one is.

        The result is about a recording, not about where the cluster keeps a
        copy of it. A remote path left in here reaches the cache key, the
        result record and the screen.
        """
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
        }
        return out