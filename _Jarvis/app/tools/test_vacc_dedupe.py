# -*- coding: utf-8 -*-
"""The duplicate guard for VACC jobs (backend/flights.py), without a cluster.

The rule (2026-10-20): the same tool, on the same recording, with the same
settings, is never submitted twice. This checks each of the four locks:

  * this process -- `FLIGHTS.claim` refuses a key already held;
  * a double click -- `submit_id` is remembered and recalled;
  * another computer -- the lock script really is atomic: run twice in a
    real bash against a temporary directory, the second run reports the
    first one's owner and goes no further, and only the owner's own rid
    can remove it;
  * every single run -- `VaccRun.submit` takes a lock even when no route
    gave it one, refuses on the marker, and on its way out removes only
    its own lock.

    python tools/test_vacc_dedupe.py

No network, no cluster. Writes only to a temporary directory.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import flights, vacc, vaccrun  # noqa: E402

FAILED = []
N = [0]


def check(what, ok, note=""):
    N[0] += 1
    if not ok:
        FAILED.append(what + ("   [%s]" % note if note else ""))
    print("  %s %s%s" % ("ok  " if ok else "FAIL", what,
                         ("   [%s]" % note if note else "")))


def test_keys():
    print("\n== a key is the tool's own question, and nothing more ==")
    a = flights.key("incisor", "s1", "rh")
    check("same tool, recording and question: same key",
          a == flights.key("incisor", ["s1"], "rh"), a)
    check("another question: another key",
          a != flights.key("incisor", "s1", "rh2"))
    check("another tool: another key",
          a != flights.key("doppler", "s1", "rh"))
    check("the order of recordings does not matter",
          flights.key("circuit", ["b", "a"], 1)
          == flights.key("circuit", ["a", "b"], 1))
    check("the hash is a safe directory name", flights.keyhash(a).isalnum()
          and len(flights.keyhash(a)) == 16, flights.keyhash(a))


def test_claims():
    print("\n== this process: one claim per key ==")
    f = flights.Flights()
    k = flights.key("incisor", "s1", "rh")
    f.claim(k, tool="incisor")
    try:
        f.claim(k, tool="incisor")
        check("a second claim of the same key is refused", False)
    except flights.Duplicate as exc:
        check("a second claim of the same key is refused", True)
        p = exc.payload()
        check("and the refusal says it is a duplicate, with the flight",
              p["kind"] == "duplicate" and p["duplicate"]["key"] == k, str(p))
        check("in a sentence a person can act on",
              "Follow it" in p["error"], p["error"])
    f.attach(k, job_id="j1", rid="abc123abc123")
    check("attaching a job marks it running",
          f.find(k)["state"] == "running" and f.find(k)["job_id"] == "j1")
    check("listing by tool finds it", len(f.list("incisor")) == 1
          and not f.list("doppler"))
    f.release(k)
    check("once released the key is free again", f.find(k) is None)
    f.claim(k, tool="incisor")
    check("and can be claimed again", f.find(k) is not None)

    print("\n== a double click: submit_id ==")
    f.remember("click-1", {"ok": True, "job": {"id": "j1"}})
    check("a repeat of the same click gets the first answer",
          f.recall("click-1") == {"ok": True, "job": {"id": "j1"}})
    check("another click is not confused with it", f.recall("click-2") is None)
    check("no submit_id, nothing recalled", f.recall(None) is None)


def _bash():
    for cand in ("bash", r"C:\Program Files\Git\bin\bash.exe"):
        try:
            subprocess.run([cand, "-c", "true"], capture_output=True,
                           timeout=20, check=True)
            return cand
        except Exception:                                # noqa: BLE001
            continue
    return None


def test_cluster_lock():
    print("\n== another computer: the lock really is atomic ==")
    bash = _bash()
    if not bash:
        print("  (no bash on this machine; skipped)")
        return
    tmp = tempfile.mkdtemp(prefix="jarvis-locks-")
    try:
        root = tmp.replace("\\", "/")
        k = flights.key("doppler", "s9", "q")
        path = root + "/locks/" + flights.keyhash(k)
        mine = flights.owner_line(k, "aaaaaaaaaaaa", "doppler", "Bluebarry")
        theirs = flights.owner_line(k, "bbbbbbbbbbbb", "doppler", "Strawbarry")

        def run(script):
            p = subprocess.run([bash, "-c", "set -e\n" + script
                                + "echo SUBMITTED\n"],
                               capture_output=True, text=True, timeout=30)
            return p.stdout

        first = run(flights.take_lock_sh(path, theirs, 3600))
        check("the first computer takes the lock and goes on to submit",
              "SUBMITTED" in first and flights.duplicate_in(first) is None,
              first.strip())
        second = run(flights.take_lock_sh(path, mine, 3600))
        held = flights.duplicate_in(second)
        check("the second is told who holds it, and does NOT submit",
              "SUBMITTED" not in second and held is not None
              and held.get("device") == "Strawbarry", second.strip())

        subprocess.run([bash, "-c", flights.drop_own_lock_sh(
            path, "aaaaaaaaaaaa")], capture_output=True, timeout=30)
        check("a run that does not own the lock cannot remove it",
              os.path.isdir(path))
        subprocess.run([bash, "-c", flights.drop_own_lock_sh(
            path, "bbbbbbbbbbbb")], capture_output=True, timeout=30)
        check("its owner removes it", not os.path.isdir(path))
        third = run(flights.take_lock_sh(path, mine, 3600))
        check("and then it can be taken again", "SUBMITTED" in third)

        # A stale lock: older than the job could run, so taken over.
        subprocess.run([bash, "-c", "touch -d '3 hours ago' %s"
                        % vacc.q(path)], capture_output=True, timeout=30)
        fourth = run(flights.take_lock_sh(path, theirs, 3600))
        check("a lock older than any job could run is taken over",
              "SUBMITTED" in fourth, fourth.strip())

        print("\n== cluster_holders reads the same directory ==")
        def fake_ssh(cmd):
            p = subprocess.run([bash, "-c", cmd], capture_output=True,
                               text=True, timeout=30)
            return p.stdout
        cfg = {"workspace": root}
        got = flights.cluster_holders(cfg, ssh=fake_ssh)
        check("it lists the held lock by hash, with its owner",
              flights.keyhash(k) in got
              and got[flights.keyhash(k)].get("device") == "Strawbarry",
              json.dumps(got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _FakeSSH:
    def __init__(self, reply="12345\n"):
        self.reply = reply
        self.calls = []

    def __call__(self, cmd, stdin=None, timeout=60):
        self.calls.append((cmd, stdin))
        return self.reply


def test_vaccrun():
    print("\n== every single run takes a lock, even with no door ==")
    cfg = {"workspace": "/gpfs1/home/s/a/sakhava1/jarvis", "netid": "sakhava1",
           "host": "login.vacc.uvm.edu", "partition": "general"}
    ssh = _FakeSSH()
    run = vaccrun.VaccRun(cfg, "drift", {"a": 1}, None,
                          plan={"seconds": 60}, ssh=ssh)
    run._ssh = ssh

    class _Job:
        id = "j"
        log = []

        def check(self):
            pass

        def begin(self, *a, **k):
            pass

        def tick(self, *a, **k):
            pass

    run.submit(_Job())
    script = ssh.calls[0][1] or ""
    check("the submit script takes a lock before sbatch",
          "mkdir" in script and script.index("locks/")
          < script.index("sbatch"), script[:200])
    check("and names the job in a Slurm comment",
          "#SBATCH --comment=jv1;drift;" in script)
    check("the spec carries the lock for the node to release",
          '"lock": "' in script)

    print("\n== a duplicate on the cluster stops the run, by name ==")
    holder = json.dumps({"device": "Strawbarry", "rid": "bbbbbbbbbbbb"})
    ssh2 = _FakeSSH("jarvis-duplicate=%s\n" % holder)
    run2 = vaccrun.VaccRun(cfg, "drift", {"a": 1}, None,
                           plan={"seconds": 60}, ssh=ssh2)
    run2._ssh = ssh2
    try:
        run2.submit(_Job())
        check("a held lock refuses the submit", False)
    except vacc.SSHError as exc:
        check("a held lock refuses the submit", exc.kind == "duplicate",
              exc.kind)
        check("and says which computer has it", "Strawbarry" in str(exc),
              str(exc))
    check("no job id was taken from the refusal", run2.slurm_id is None)
    run2._drop_lock()
    last = ssh2.calls[-1][0]
    check("leaving removes the lock only if it is ours",
          "grep -qF" in last and run2.rid in last, last)


def main():
    print("The VACC duplicate guard, offline.")
    test_keys()
    test_claims()
    test_cluster_lock()
    test_vaccrun()
    print("\n%d check(s)" % N[0])
    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        for f in FAILED:
            print("   " + f)
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
