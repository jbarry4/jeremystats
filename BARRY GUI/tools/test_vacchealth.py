# -*- coding: utf-8 -*-
"""The VACC health check: squeue --me, the shared space, recent failures.
Offline.

    python tools/test_vacchealth.py

What the routine probe now asks in its one connection -- the account's jobs
(`squeue --me`), whether it can open the lab's shared space and write into
Jarvis Data, and what failed in the last day -- and what /api/vacc/status
makes of it: each job marked by whether Jarvis here is following it, and a
refusal that says what was refused and who to ask. The login node is a fake;
nothing connects, and the run records are in a temp folder.
"""
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


def main():
    cfg = {"netid": "zztester", "host": "login.vacc.uvm.edu", "path_map": [],
           "shared": vacc._shared_of({})}

    print("\nthe probe asks it all in one connection")
    script = vacc._PROBE.replace('echo "end=1"', vacc._root_checks(cfg) + "\n"
                                 + vacc._shared_checks(cfg) + "\n" + vacc._JOBS
                                 + '\necho "end=1"')
    check("squeue --me, falling back to -u $USER", "squeue --me" in script
          and 'squeue -u "$USER" -h -o' in script)
    check("the shared space and Jarvis Data are tested",
          "shared=" in script and "jdata=" in script
          and "'/gpfs2/scratch/sakhava1/Jarvis Data'" in script)
    check("sacct is bounded, so it cannot slow the probe", "timeout 8 sacct" in script)
    check("end=1 is still the last line", script.rstrip().endswith('echo "end=1"'))

    calls = []

    def fake(c, cmd, stdin=None, timeout=45):
        calls.append(stdin)
        return ("whoami=zztester\nhost=vacc-login1\nqueued=1\nrunning=2\n"
                "partitions=general,short\nhome=/users/z/z/zztester\n"
                "shared=ok\njdata=creatable\n"
                "job=555000_[0-3]|0123456789ab|PENDING|0:00|(Priority)\n"
                "job=555001|abcdef012345|RUNNING|1:02:03|node07\n"
                "job=9|myjob.sh|RUNNING|0:05|node02\n"
                "fail=500|fedcba987654|TIMEOUT|2026-09-29T02:00:00\n"
                "end=1\n")
    real_ssh = vacc._ssh
    vacc._ssh = fake
    try:
        got = vacc.probe(cfg)
    finally:
        vacc._ssh = real_ssh
    check("one connection", len(calls) == 1)
    check("three jobs, parsed", [j["id"] for j in got["jobs"]]
          == ["555000_[0-3]", "555001", "9"], got.get("jobs"))
    check("with state, time and why",
          got["jobs"][1] == {"id": "555001", "name": "abcdef012345",
                             "state": "RUNNING", "elapsed": "1:02:03",
                             "reason": "node07"}, got["jobs"][1])
    check("and the day's failures", got["fails"][0]["state"] == "TIMEOUT", got["fails"])

    print("\nthe sentences")
    sh = cfg["shared"]
    w = vacc.shared_words(sh, "denied", None, "zztester")
    check("refused: what, and who to ask",
          "/gpfs2/scratch/sakhava1" in w and "Ask Shahriar" in w and "zztester" in w, w)
    check("with the OnDemand link", "ondemand.vacc.uvm.edu" in w, w)
    check("never a bare permission denied", "permission denied" not in w.lower())
    w = vacc.shared_words(sh, "ok", "nowrite", "zztester")
    check("readable but not writable says an upload would be refused",
          "upload would be refused" in w and "Ask Shahriar" in w, w)
    check("all well says nothing", vacc.shared_words(sh, "ok", "ok") == ""
          and vacc.shared_words(sh, "ok", "creatable") == "")

    print("\n/api/vacc/status marks what Jarvis here is following")
    log = vaccrun.RunLog(tempfile.mkdtemp(prefix="zz-vaccruns-"))
    log.write({"rid": "0123456789ab", "kind": "array", "tool": "doppler",
               "array_id": "555000", "jobs": []})
    log.write({"rid": "aaaaaaaaaaaa", "kind": "array", "tool": "incisor",
               "array_id": "444000", "jobs": []})
    real_log, real_state = appmod.VACC_RUNLOG, dict(vacc._STATE)
    appmod.VACC_RUNLOG = log
    real_load = vacc.load_config
    vacc.load_config = lambda d: dict(cfg, configured=True, needs_netid=False)
    vacc._STATE.update(at=time.time(), ok=True, probe=got, kind=None, why="")
    try:
        st = appmod._vacc_status_marked()
    finally:
        appmod.VACC_RUNLOG = real_log
        vacc.load_config = real_load
        vacc._STATE.clear()
        vacc._STATE.update(real_state)
    j = {x["id"]: x for x in st["jobs"]}
    check("an array with a run record here is followed, with its tool",
          j["555000_[0-3]"]["followed"] and j["555000_[0-3]"]["tool"] == "doppler",
          j["555000_[0-3]"])
    check("a Jarvis job with no record here is Jarvis's, not followed",
          not j["555001"]["followed"] and j["555001"]["jarvis"], j["555001"])
    check("the person's own job is neither", not j["9"]["followed"]
          and not j["9"]["jarvis"], j["9"])
    check("a run waited on that the cluster no longer lists is said",
          [w["rid"] for w in st["waiting"]] == ["aaaaaaaaaaaa"], st["waiting"])
    check("the shared space arrives with its states and no complaint",
          st["shared"]["state"] == "ok" and st["shared"]["data_state"] == "creatable"
          and st["shared"]["why"] == "", st["shared"])

    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
