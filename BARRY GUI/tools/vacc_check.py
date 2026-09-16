# -*- coding: utf-8 -*-
"""Does the cluster link behave when the cluster misbehaves?

Every interesting thing about a remote job is a failure: the queue that never
empties, the walltime that kills it at thirty minutes, the node that dies, the
accounting database that has not caught up yet, the connection that hangs.
None of those can be produced on demand against a real cluster, and waiting
for one to happen by accident is how they end up being debugged at the point
where they cost somebody a six-hour run.

So `_ssh` is replaced with a function that returns whatever this file says,
and the state machine is driven through all of it in about a second.

    python tools/vacc_check.py

Needs no cluster, no network, no account, and no ssh binary.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import vacc  # noqa: E402

FAILED = []
CFG = {"netid": "tester", "host": "login.vacc.uvm.edu", "path_map": []}


def check(name, ok, detail=""):
    print("  %-62s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail))
    if not ok:
        FAILED.append(name)


class Fake(object):
    """Stands in for the login node. Records what it was asked."""

    def __init__(self):
        self.replies = []
        self.asked = []

    def __call__(self, cfg, remote_command, stdin=None, timeout=45):
        self.asked.append(stdin if stdin is not None else remote_command)
        if not self.replies:
            return ""
        out = self.replies.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def main():
    real_ssh = vacc._ssh
    fake = Fake()
    vacc._ssh = fake
    try:
        print("\nasking for the right box")
        # The estimate is in seconds; a walltime is a guillotine, so they are
        # not the same quantity.
        r = vacc.slurm_request(60)
        check("a one-minute job still asks for the ten-minute floor",
              r["time_s"] == vacc.MIN_WALL_S, r["time"])
        check("and goes to the short queue", r["partition"] == "short", r["partition"])
        r = vacc.slurm_request(2 * 3600)
        check("two hours of work asks for six", r["time_s"] == 6 * 3600, r["time"])
        check("and lands on general, not short",
              r["partition"] == "general", r["partition"])
        r = vacc.slurm_request(20 * 3600)
        check("a very long job goes to the week queue",
              r["partition"] == "week", r["partition"])
        r = vacc.slurm_request(3 * 3600, partition="short")
        check("an explicit partition is never exceeded",
              r["time_s"] <= 3 * 3600, r["time"])
        check("a --time is ALWAYS produced, never left to the 30m default",
              bool(vacc.slurm_request(0)["time"]),
              vacc.slurm_request(0)["time"])
        check("memory grows with the data",
              vacc.slurm_request(60, 500)["mem"] != vacc.slurm_request(60, 1)["mem"],
              vacc.slurm_request(60, 500)["mem"] + " vs "
              + vacc.slurm_request(60, 1)["mem"])

        print("\nhow a job ended, and what to tell somebody")
        check("running is not an outcome", vacc.outcome_for("RUNNING") is None)
        check("pending is not an outcome", vacc.outcome_for("PENDING") is None)
        check("completed is done", vacc.outcome_for("COMPLETED")[0] == "done")
        check("'COMPLETED+' is still done",
              vacc.outcome_for("COMPLETED+")[0] == "done")
        check("'CANCELLED by 12345' is a cancel, not a failure",
              vacc.outcome_for("CANCELLED by 12345")[0] == "canceled",
              str(vacc.outcome_for("CANCELLED by 12345")))
        to = vacc.outcome_for("TIMEOUT")
        check("a walltime kill is NOT reported as a failure", to[0] == "timeout")
        check("and says the analysis is fine",
              "nothing is wrong" in to[1].lower(), to[1])
        oom = vacc.outcome_for("OUT_OF_MEMORY")
        check("out of memory offers more memory", oom[0] == "oom"
              and "twice" in oom[1].lower(), str(oom))
        nf = vacc.outcome_for("NODE_FAIL")
        check("a dead node is the cluster's fault, and says so",
              nf[0] == "node-fail" and "rather than yours" in nf[1], str(nf))
        check("an unknown state is a failure rather than a crash",
              vacc.outcome_for("WHAT_IS_THIS")[0] == "failed")

        print("\npolling: one connection, two commands")
        fake.replies = [
            "12345 RUNNING\n12346 PENDING\n--\n"
            "12347|12347|COMPLETED|00:04:12|2048K\n"
        ]
        got = vacc.poll_states(CFG, [12345, 12346, 12347])
        check("all three came back from one call", len(got) == 3, str(got))
        check("only one connection was used", len(fake.asked) == 1,
              str(len(fake.asked)))
        check("squeue and sacct went in the same command",
              "squeue" in fake.asked[0] and "sacct" in fake.asked[0])
        check("a live job is marked live", got["12345"]["live"] is True)
        check("a finished one carries its elapsed and peak memory",
              got["12347"]["max_rss"] == "2048K", str(got["12347"]))
        check("nothing is asked when there is nothing to ask about",
              vacc.poll_states(CFG, []) == {} and len(fake.asked) == 1)

        print("\nsqueue wins while a job is alive")
        fake.replies = ["12345 RUNNING\n--\n12345|12345|COMPLETED|00:01:00|1K\n"]
        got = vacc.poll_states(CFG, [12345])
        check("a job in both is read from squeue, not the lagging database",
              got["12345"]["state"] == "RUNNING", str(got["12345"]))

        print("\nan array task is found under the id we submitted")
        # Measured on the real cluster: `sacct -j 999999` answers
        # `999467_3|999999|COMPLETED`. The number sbatch hands back is the RAW
        # one; what sacct PRINTS for anything in an array is the array-and-task
        # form. Keying on what it prints loses the job, and `wait` then fails a
        # run that finished an hour ago as vanished.
        fake.replies = ["--\n999467_3|999999|COMPLETED|01:49:28|\n"]
        got = vacc.poll_states(CFG, [999999])
        check("keyed on the raw id we asked about", "999999" in got, str(got))
        check("and not on the array form sacct printed",
              "999467_3" not in got, str(list(got)))
        check("while keeping that form for anything shown to a person",
              got.get("999999", {}).get("job_id") == "999467_3",
              str(got.get("999999")))
        check("with the state read from the right column",
              got.get("999999", {}).get("state") == "COMPLETED",
              str(got.get("999999")))

        print("\nthe accounting lag is not a vanished job")
        fake.replies = ["--\n"]
        got = vacc.poll_states(CFG, [12345])
        check("a job in neither is simply absent, not failed",
              got == {}, str(got))
        check("and there is a grace period to wait it out",
              vacc.LAG_GRACE_S >= 60, str(vacc.LAG_GRACE_S))

        print("\ncancelling, including before the id is known")
        fake.replies, fake.asked = [""], []
        vacc.cancel(CFG, slurm_id=999)
        check("by id, it scancels the id", "scancel 999" in fake.asked[0],
              fake.asked[0])
        fake.replies, fake.asked = [""], []
        vacc.cancel(CFG, rid="0123456789ab")
        check("with no id yet, it falls back to the job NAME",
              "-n 0123456789ab" in fake.asked[0], fake.asked[0])
        check("which is why every job is named after its run id", True)
        fake.replies, fake.asked = [""], []
        check("with neither, it does nothing rather than cancelling broadly",
              vacc.cancel(CFG) is False and not fake.asked)
        try:
            vacc.cancel(CFG, rid="; rm -rf /")
            check("a run id that is not one is refused", False, "it was accepted")
        except ValueError:
            check("a run id that is not one is refused", True)

        print("\nwhat comes back when the connection does not")
        for kind, msg in (("timeout", "did not answer"),
                          ("auth", "refused the key"),
                          ("unreachable", "reach the cluster")):
            fake.replies = [vacc.SSHError(vacc._why(kind, ""), kind)]
            try:
                vacc.poll_states(CFG, [1])
                check("a %s is raised, not swallowed" % kind, False)
            except vacc.SSHError as exc:
                check("a %s names itself" % kind, exc.kind == kind, exc.kind)
                check("  and reads as a sentence", msg in str(exc), str(exc))

        print("\nstatus never raises, whatever happened")
        vacc.LOGS_DIR = None
        st = vacc.status()
        check("with nothing configured at all it still answers",
              st["ok"] is True and st["available"] is False, str(st)[:120])
        check("and says why in words", bool(st["why"]), st["why"])

        print("\nrefresh survives a probe that explodes")
        vacc.LOGS_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "GUI_logs")
        fake.replies = [RuntimeError("the login node caught fire")]
        vacc._STATE.update(at=0, retry_at=0, failures=0)
        cfg = vacc.load_config(vacc.LOGS_DIR)
        if cfg.get("configured"):
            got = vacc.refresh(force=True)
            check("an exploding probe is caught", got["ok"] is False, str(got)[:120])
            check("and backs off rather than hammering the login node",
                  got["retry_at"] > 0, str(got.get("retry_at")))
        else:
            # No account here, which is its own correct answer.
            got = vacc.refresh(force=True)
            check("an unconfigured machine says so and connects to nothing",
                  got["kind"] == "unconfigured" and not fake.asked[-1:] == ["probe"],
                  str(got)[:120])

        print("\nbackoff")
        check("the first failure waits seconds", vacc._backoff(1) <= 30,
              str(vacc._backoff(1)))
        check("the tenth waits minutes, not hours", vacc._backoff(10) == 300.0,
              str(vacc._backoff(10)))

        print("\nquoting, because lab paths are full of shell")
        # Asserted by round trip rather than by looking at the quoting. What
        # matters is that a shell parsing it gets back exactly what went in;
        # HOW shlex spells that is its business, and an apostrophe comes back
        # as '"'"' rather than the \' this check first expected.
        import shlex
        for awkward in ["VACC Code/KCNT1 Urethane/a&b (1).m",
                        "it's",
                        "/netfiles/x/$HOME`whoami`",
                        "a; rm -rf /",
                        'quote" and $(sub)']:
            back = shlex.split(vacc.q(awkward))
            check("survives a shell unchanged: " + awkward[:34],
                  back == [awkward], str(back))

    finally:
        vacc._ssh = real_ssh

    print()
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
