# -*- coding: utf-8 -*-
"""Checks for backend/preconrun.py and the /api/arc/precon routes -- the
Drift panel's way of running tools/run_precon_drift.py.

    python tools\\check_preconrun.py

Never runs the analysis: every child here is a stand-in script written to a
temp folder that answers the same flags (--plan-json, --progress,
--stop-file) the way the real one does. The routes are exercised through
the Flask test client with the runner pointed at the stand-in; activity
records are not written.

What it establishes
  - one child at a time; a second start is refused
  - the child's output goes to a file: 300 KB of output does not stall it
    (CONTROL: the same child on an undrained pipe does stall)
  - a soft stop ends a run between items with exit 3; a hard stop kills it
  - after a "restart" (a new Runner), a live child is still seen as running
    while its log moves, and as lost once it has gone quiet
  - the plan is fresh only for the Jarvis that made it, and the run route
    refuses any plan but the one on file (CONTROL: the right one starts)
  - report files: only md, csv and figure/<name>.png|svg are served
  - the real script's Progress settles items the way the panel counts them
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import preconrun as P                     # noqa: E402

N_PASS = N_FAIL = 0


def check(name, ok, detail=""):
    global N_PASS, N_FAIL
    if ok:
        N_PASS += 1
        print("  ok    %s" % name)
    else:
        N_FAIL += 1
        print("  FAIL  %s  %s" % (name, detail))


CHILD = r'''
import json, os, sys, time
a = sys.argv[1:]
def val(flag):
    return a[a.index(flag) + 1] if flag in a else None
def write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)
mode = os.environ.get("STANDIN_MODE", "")
if "--dry-run" in a:
    if mode == "flood":
        for i in range(6000):
            print("x" * 50, i)
    from datetime import datetime, timezone
    at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    write(val("--plan-json"), {"at": at, "dry_run": True,
        "server": {"started_at": "BOOT-A"}, "cost": {"total_s": 4440,
        "lines": ["Total: about 74 min."]}})
    print("planned")
    sys.exit(0)
if "--yes" in a:
    prog, stop = val("--progress"), val("--stop-file")
    if val("--resumed"):
        print("carrying on:", val("--resumed"), flush=True)
    d = {"stage": "circuits", "stages": {"circuits": {"of": 50, "done": 0,
         "already": 0, "failed": 0}}, "stopped": None, "finished": None}
    for n in range(1, 51):
        if mode in ("interrupt", "quick") and n > 3:
            if mode == "interrupt":
                print("INTERRUPTED: Jarvis restarted (stand-in)", flush=True)
                sys.exit(4)
            break
        if os.path.exists(stop):
            d["stopped"] = "now"
            write(prog, d)
            print("stopped, as asked, before item", n)
            sys.exit(3)
        d["item"] = {"n": n, "tag": "item %d" % n}
        write(prog, d)
        print("item", n, flush=True)
        time.sleep(0.2)
        d["stages"]["circuits"]["done"] += 1
    d["finished"] = "now"
    write(prog, d)
    sys.exit(0)
print("report written")
sys.exit(0)
'''


def iso_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds")


def set_run(r, **rec):
    """Write last.json's run record by hand -- what a Jarvis that went down
    mid-run leaves behind."""
    last = json.load(open(r.last_path, encoding="utf-8")) \
        if os.path.exists(r.last_path) else {}
    last["run"] = dict({"what": "run", "started": iso_now(), "ended": None,
                        "exit_code": None, "killed": False, "resume": True,
                        "log": r.log_path("run"), "resumes": 0,
                        "stalls": 0, "filed_at_start": 0}, **rec)
    last["current"] = "run"
    json.dump(last, open(r.last_path, "w", encoding="utf-8"))


def hour_ago():
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=1)).astimezone()         .isoformat(timespec="seconds")


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def resume_checks(tmp, child, runner, docs):
    base = "http://127.0.0.1:1"
    r = runner()
    print("interrupted, and carried on")
    os.environ["STANDIN_MODE"] = "interrupt"
    first = r.start("run", base)
    wait_idle(r)
    s = r.status()
    check("an interrupted run ends with exit 4",
          s["last"]["run"]["exit_code"] == 4, s["last"]["run"])
    check("and is armed to be carried on",
          s["resume"]["armed"] and s["resume"]["interrupted"], s["resume"])
    rec = r.interrupted()
    check("interrupted() names it", rec is not None
          and rec["started"] == first["started"])
    os.environ["STANDIN_MODE"] = "quick"
    got = r.resume(base, "because the check said so")
    av = got["argv"]
    check("resume starts the same run, with --resumed and why",
          av[:len(first["argv"])] == first["argv"] and "--resumed" in av
          and av[av.index("--resumed") + 1] == "because the check said so",
          av)
    check("the chain is kept (resumes 1, the first run's chain_started)",
          got["resumes"] == 1 and got["chain_started"]
          == first["chain_started"], got)
    wait_idle(r)
    check("the carried-on child was told it was carrying on",
          "carrying on: because the check said so"
          in "\n".join(r.status()["log"]["lines"]))
    s = r.status()
    check("finished: not carried on again",
          r.interrupted() is None and s["resume"]["armed"] is False
          and s["last"]["run"]["exit_code"] == 0)

    os.environ["STANDIN_MODE"] = ""
    r.start("run", base)
    time.sleep(0.6)
    r.stop()
    wait_idle(r)
    last = json.load(open(r.last_path, encoding="utf-8"))["run"]
    check("a soft stop disarms it (a person stopped it)",
          r.interrupted() is None and last["resume"] is False
          and (last.get("disarmed") or {}).get("why") == "stopped by hand",
          last.get("disarmed"))
    r.start("run", base)
    time.sleep(0.6)
    r.stop(hard=True)
    wait_idle(r)
    check("so does a hard stop", r.interrupted() is None)

    print("the computer went off")
    set_run(r, pid=dead_pid())
    s = r.status()
    check("a run nobody saw end, whose process is gone, is interrupted",
          s["busy"] is None and s["resume"]["interrupted"]
          and s["last"]["run"].get("lost") and r.interrupted() is not None,
          s["resume"])
    # A pid remembered from a run started an hour ago, now held by a live
    # process made seconds ago (this one): after a reboot, pids are reused.
    set_run(r, pid=os.getpid(), started=hour_ago())
    rec = json.load(open(r.last_path, encoding="utf-8"))["run"]
    check("a remembered pid that is someone else's now is not the run",
          P._is_ours(rec) is False and r.status()["busy"] is None
          and r.interrupted() is not None)
    sleeper = subprocess.Popen([sys.executable, "-c",
                                "import time; time.sleep(30)"])
    try:
        check("CONTROL: a process started when the record says is ours",
              P._is_ours({"pid": sleeper.pid, "started": iso_now()}))
    finally:
        sleeper.kill()
        sleeper.wait()

    print("carrying on by itself gives up when it gets nowhere")
    os.environ["STANDIN_MODE"] = "interrupt"
    r.start("run", base)
    wait_idle(r)
    ok = True
    for i in (1, 2):
        try:
            r.resume(base, "auto %d" % i, auto=True)
            wait_idle(r)
        except P.PreconRunError as exc:
            ok = False
            check("two carries-on that file nothing are still allowed",
                  False, exc)
    if ok:
        check("two carries-on that file nothing are still allowed", True)
    try:
        r.resume(base, "auto 3", auto=True)
        check("the third that files nothing is refused", False)
    except P.PreconRunError as exc:
        check("the third that files nothing is refused, and says why",
              "filed nothing" in str(exc))
    check("and it is recorded as given up",
          (r.status()["resume"]["gave_up"] or {}).get("stalls") == 3)
    got = r.resume(base, "by hand")
    wait_idle(r)
    check("a person can still carry it on by hand (the third carry-on)",
          got["resumes"] == 3, got["resumes"])
    json.dump({"circuits": {"k": {"artifact_id": "a1"}}},
              open(os.path.join(docs, "dewey-precon-drift.runlog.json"), "w",
                   encoding="utf-8"))
    got = r.resume(base, "auto after progress", auto=True)
    wait_idle(r)
    check("once something lands, the count of tries starts again",
          got["stalls"] == 0, got["stalls"])
    os.remove(os.path.join(docs, "dewey-precon-drift.runlog.json"))

    print("forget")
    check("an interrupted run is there to forget", r.interrupted() is not None)
    r.forget()
    check("forgotten: not carried on", r.interrupted() is None and
          r.status()["resume"]["disarmed"]["why"] == "told not to carry it on")
    try:
        r.forget()
        check("forgetting nothing is refused", False)
    except P.PreconRunError:
        check("forgetting nothing is refused", True)

    print("when Jarvis starts again")
    os.environ["STANDIN_MODE"] = "quick"
    r2 = runner()
    check("nothing armed: nothing is started",
          r2.resume_after_boot(base, ready=lambda: True) is None
          and r2.status()["busy"] is None)
    set_run(r2, pid=dead_pid())
    msg = r2.resume_after_boot(base, ready=lambda: True, poll_s=0.2)
    b = r2.status()["busy"]
    check("an interrupted run is carried on by itself",
          msg and "carried on" in msg and b and b["what"] == "run", msg)
    wait_idle(r2)
    rec = json.load(open(r2.last_path, encoding="utf-8"))["run"]
    check("and says so: auto, and why", rec["auto"] is True
          and "Jarvis started again" in rec["resumed_why"], rec)

    # A run left over from the Jarvis before, still alive: it is waited for.
    def orphan(mode):
        env = dict(os.environ, STANDIN_MODE=mode)
        fh = open(r2.log_path("run"), "wb")
        p = subprocess.Popen([sys.executable, "-u", child, "--yes",
                              "--progress", r2.progress_path,
                              "--stop-file", r2.stop_path],
                             stdout=fh, stderr=subprocess.STDOUT, env=env)
        set_run(r2, pid=p.pid, started=iso_now())
        fh.close()                         # the child has its own handle
        return p, fh
    p, fh = orphan("interrupt")
    t0 = time.time()
    msg = r2.resume_after_boot(base, ready=lambda: True, poll_s=0.2,
                               orphan_wait_s=30)
    took = time.time() - t0
    fh.close()
    check("a live run from the Jarvis before is waited for, then carried "
          "on (%.1f s)" % took, p.poll() == 4 and msg
          and "carried on" in msg, (p.poll(), msg))
    wait_idle(r2)
    p, fh = orphan("")                       # would run for ten seconds
    t0 = time.time()
    msg = r2.resume_after_boot(base, ready=lambda: True, poll_s=0.2,
                               orphan_wait_s=1.0)
    took = time.time() - t0
    fh.close()
    check("one that will not end is ended after the wait (%.1f s)" % took,
          p.poll() not in (None, 0, 3, 4) and took < 6 and msg
          and "carried on" in msg, (p.poll(), took, msg))
    wait_idle(r2)
    set_run(r2, pid=os.getpid(), started=hour_ago())
    t0 = time.time()
    msg = r2.resume_after_boot(base, ready=lambda: True, poll_s=0.2,
                               orphan_wait_s=30)
    check("a pid that is not ours is neither waited for nor ended",
          time.time() - t0 < 5 and msg and "carried on" in msg, msg)
    wait_idle(r2)
    r2.forget() if r2.interrupted() else None
    os.environ["STANDIN_MODE"] = ""


def child_side_checks(tmp):
    """tools/run_precon_drift.py when Jarvis goes away, against a fake
    Jarvis this check can drop and restart."""
    import http.server
    import threading
    import run_precon_drift as R
    print("the run, when Jarvis goes away")
    state = {"boot": "BOOT-1"}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, obj):
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/api/health":
                return self.reply(200, {"ok": True,
                                        "started_at": state["boot"]})
            if self.path == "/api/x":
                return self.reply(200, {"ok": True, "x": 1})
            if self.path == "/api/drop":
                self.close_connection = True
                return                        # no response at all
            if self.path.startswith("/api/cfc/job/"):
                return self.reply(404, {"ok": False, "error": "no such job"})
            return self.reply(404, {"ok": False, "error": "nope"})

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port
    R.GONE_S, R.GONE_POLL_S = 1.5, 0.2
    api = R.Api(base, boot="BOOT-1")

    def raises(fn, kind):
        try:
            fn()
        except kind as exc:
            return str(exc) or True
        except Exception as exc:                     # noqa: BLE001
            return False if kind is not type(exc) else str(exc)
        return False
    check("the same Jarvis answers", api.get("/api/x")["x"] == 1)
    got = raises(lambda: api.get("/api/drop"), R.ApiError)
    check("a request the SAME Jarvis drops is asked again, then fails as "
          "an item (ApiError, not interrupted)", bool(got), got)
    n0 = api.n
    raises(lambda: api.get("/api/drop"), R.ApiError)
    check("  asked three times", api.n - n0 == 3, api.n - n0)
    got = raises(lambda: R.wait_job(api, "j1", "t"), R.ApiError)
    check("a job the same Jarvis does not know is an ApiError", bool(got))
    state["boot"] = "BOOT-2"
    got = raises(lambda: api.get("/api/drop"), R.JarvisGone)
    check("a dropped request, and a Jarvis with another boot: interrupted",
          got and "restarted" in got, got)
    got = raises(lambda: R.wait_job(api, "j1", "t"), R.JarvisGone)
    check("a job a restarted Jarvis does not know: interrupted",
          got and "restarted" in got, got)
    got = raises(api.same_boot, R.JarvisGone)
    check("between items, a new boot: interrupted", bool(got), got)
    check("JarvisGone is neither ApiError nor Refused, so no item or stage "
          "handler swallows it",
          not issubclass(R.JarvisGone, (R.ApiError, R.Refused)))
    srv.shutdown()
    srv.server_close()
    t0 = time.time()
    got = raises(lambda: api.get("/api/x"), R.JarvisGone)
    took = time.time() - t0
    check("nothing answering for GONE_S: interrupted (%.1f s)" % took,
          got and "has not answered" in got and 1.4 <= took < 6, got)
    probe = R.Api(base)                              # discovery: no boot
    check("a probe without a boot fails fast, as discovery needs",
          bool(raises(lambda: probe.get("/api/health"), R.ApiError)))

    # The stages end as interrupted, with the record saying where.
    rl = os.path.join(tmp, "stages.runlog.json")
    pg = os.path.join(tmp, "stages.progress.json")
    real_spark, real_circ, real_prog = R.run_spark, R.run_circuits, R.PROG
    R.PROG = R.Progress(pg)

    def spark(api, rows, log, only=None):
        R.PROG.stage("spark", 2)
        R.PROG.item(1, "r3 Precon1")
        R.PROG.item(2, "r3 Precon4")
        raise R.JarvisGone("Jarvis restarted (test)")
    reached = []
    R.run_spark = spark
    R.run_circuits = lambda *a, **k: reached.append("circuits") or []
    try:
        log = R.RunLog(rl)
        failures, stopped, inter = R.run_stages(
            None, log, ("spark", "circuits", "drifts"), spark_rows=[],
            items=[], roles={}, bands=(), recs={}, kinds=())
    finally:
        R.run_spark, R.run_circuits = real_spark, real_circ
        prog, R.PROG = R.PROG, real_prog
    saved = json.load(open(rl, encoding="utf-8"))
    pgd = json.load(open(pg, encoding="utf-8"))
    check("run_stages: interrupted, not failed, and no later stage ran",
          inter and "restarted" in inter["why"] and failures == []
          and reached == [], (inter, failures, reached))
    check("the run log says interrupted, where, and not finished",
          saved["interrupted"]["stage"] == "spark"
          and saved["interrupted"]["item"]["tag"] == "r3 Precon4"
          and saved["finished"] is None
          and any("interrupted" in e["msg"] for e in saved["events"]))
    check("the item in flight is not counted (1 done, 0 failed)",
          (pgd["stages"]["spark"]["done"], pgd["stages"]["spark"]["failed"])
          == (1, 0), pgd["stages"]["spark"])

    # The run log survives a torn write.
    rl2 = os.path.join(tmp, "torn.runlog.json")
    L = R.RunLog(rl2)
    L.data["circuits"]["k1"] = {"artifact_id": "a1"}
    L.save()
    L.data["circuits"]["k2"] = {"artifact_id": "a2"}
    L.save()                           # .bak now holds k1 only
    open(rl2, "w").close()             # the power cut: zero bytes
    L2 = R.RunLog(rl2)
    check("a torn run log is set aside and the copy before it read",
          set(L2.data["circuits"]) == {"k1"} and L2.recovered
          and any(f.startswith("torn.runlog.json.unreadable-")
                  for f in os.listdir(tmp)), L2.recovered)
    open(rl2 + ".bak", "w").close()
    for f in os.listdir(tmp):
        if f.startswith("torn.runlog.json.unreadable-"):
            os.remove(os.path.join(tmp, f))
    open(rl2, "w").close()
    L3 = R.RunLog(rl2)
    check("neither readable: a fresh log, both kept aside",
          L3.data["circuits"] == {} and len([
              f for f in os.listdir(tmp)
              if f.startswith("torn.runlog.json")
              and "unreadable" in f]) == 2)


def wait_idle(r, timeout=20.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not r.status()["busy"]:
            return True
        time.sleep(0.1)
    return False


def main():
    tmp = tempfile.mkdtemp(prefix="check_preconrun_")
    try:
        return run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(tmp):
    child = os.path.join(tmp, "standin.py")
    with open(child, "w", encoding="utf-8") as fh:
        fh.write(CHILD)
    docs = os.path.join(tmp, "docs")
    os.makedirs(os.path.join(docs, "dewey-precon-drift"))

    def runner():
        return P.Runner(tmp, os.path.join(tmp, "state"),
                        scripts={"drift": child, "report": child},
                        docs_dir=docs)

    print("idle")
    r = runner()
    s = r.status()
    check("nothing running, no plan", s["busy"] is None and s["plan"] is None
          and s["runlog"] is None, s)

    print("plan: one at a time, output to a file")
    os.environ["STANDIN_MODE"] = "flood"
    t0 = time.time()
    r.start("plan", "http://127.0.0.1:1")
    try:
        r.start("plan", "http://127.0.0.1:1")
        check("a second start is refused", False, "it started")
    except P.PreconRunError as exc:
        check("a second start is refused", exc.code == 409, exc.code)
    check("the plan ends by itself", wait_idle(r))
    took = time.time() - t0
    os.environ["STANDIN_MODE"] = ""
    size = os.path.getsize(r.log_path("plan"))
    check("300 KB of output did not stall it (%d KB in %.1f s)"
          % (size // 1024, took), size > 280 * 1024 and took < 15, took)
    s = r.status("BOOT-A")
    check("its exit code is recorded", s["last"]["plan"]["exit_code"] == 0,
          s["last"])
    check("the log tail ends with its last line",
          s["log"]["what"] == "plan" and s["log"]["lines"][-1] == "planned",
          s["log"]["lines"][-2:])
    check("the plan is fresh for the Jarvis that made it",
          s["plan"] and s["plan"]["fresh"] is True, s["plan"])
    check("and stale for any other", r.status("BOOT-B")["plan"]["fresh"]
          is False)

    # CONTROL: the same flood into a pipe nobody reads stops the child.
    env = dict(os.environ, STANDIN_MODE="flood")
    pj = os.path.join(tmp, "control_plan.json")
    p = subprocess.Popen([sys.executable, "-u", child, "--dry-run",
                          "--plan-json", pj], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, env=env)
    time.sleep(4.0)
    stalled = p.poll() is None
    p.kill()
    p.communicate()
    check("CONTROL: on an undrained pipe the same child stalls", stalled)

    print("run: progress, soft stop, hard stop")
    r.start("run", "http://127.0.0.1:1")
    time.sleep(1.2)
    s = r.status()
    check("busy is the run", s["busy"] and s["busy"]["what"] == "run", s)
    check("progress is read back", (s["progress"] or {}).get("item")
          is not None, s["progress"])
    r.stop()
    check("stopping is said while it finishes the item",
          r.status()["busy"] is None or r.status()["busy"]["stopping"])
    check("the run ends after a soft stop", wait_idle(r))
    s = r.status()
    done = s["progress"]["stages"]["circuits"]["done"]
    check("it stopped between items with exit 3 (%d of 50 done)" % done,
          s["last"]["run"]["exit_code"] == 3 and 0 < done < 50
          and s["progress"]["stopped"], s["last"]["run"])
    check("a soft stop is not a kill", s["last"]["run"]["killed"] is False)
    r.start("run", "http://127.0.0.1:1")
    check("a new run clears the stop file",
          not os.path.exists(r.stop_path))
    check("and keeps the log before it",
          os.path.exists(r.log_path("run.prev")))
    time.sleep(0.8)
    r.stop(hard=True)
    check("the run ends after a hard stop", wait_idle(r))
    s = r.status()
    check("a hard stop is recorded as a kill",
          s["last"]["run"]["killed"] is True
          and s["last"]["run"]["exit_code"] not in (0, 3), s["last"]["run"])
    try:
        r.stop()
        check("stopping nothing is refused", False)
    except P.PreconRunError:
        check("stopping nothing is refused", True)

    print("a restart: the child outlives the Runner")
    r.start("run", "http://127.0.0.1:1")
    time.sleep(0.6)
    r2 = runner()                          # what a restarted Jarvis builds
    b = r2.status()["busy"]
    check("a new Runner sees the live child as running (orphan)",
          b and b["what"] == "run" and b["orphan"] is True, b)
    try:
        r2.start("plan", "http://127.0.0.1:1")
        check("and refuses to start another beside it", False)
    except P.PreconRunError:
        check("and refuses to start another beside it", True)
    old = time.time() - 3600
    os.utime(r.log_path("run"), (old, old))
    b = r2.status()["busy"]
    check("a child whose log has gone quiet is not taken for a run",
          b is None, b)
    r.stop(hard=True)
    wait_idle(r)
    last = json.load(open(r.last_path, encoding="utf-8"))
    last["run"]["ended"] = None
    last["current"] = "run"
    json.dump(last, open(r.last_path, "w", encoding="utf-8"))
    s = runner().status()
    check("a run nobody saw end is shown as lost",
          s["busy"] is None and s["last"]["run"].get("lost") is True,
          s["last"]["run"])

    resume_checks(tmp, child, runner, docs)

    print("report files")
    check("md, csv and figures are the only files served",
          r.output_path("md").endswith("dewey-precon-drift.md")
          and r.output_path("csv").endswith("dewey-precon-drift.csv")
          and r.output_path("figure/a.png").endswith("a.png")
          and r.output_path("figure/a.svg") is not None)
    check("nothing else is (paths, other types)",
          all(r.output_path(w) is None for w in (
              "runlog", "../app.py", "figure/../../x.png",
              "figure/a.txt", "figure/", "figure/sub/a.png")))
    with open(os.path.join(docs, "dewey-precon-drift", "b.png"), "wb") as fh:
        fh.write(b"\x89PNG")
    check("figures are listed", r.report_files()["figures"] == ["b.png"])

    print("the real script's Progress")
    import run_precon_drift as R
    pp = os.path.join(tmp, "prog.json")
    g = R.Progress(pp)
    g.stage("circuits", 4)
    g.item(1, "a", 0)                 # done
    g.item(2, "b", 0)
    g.outcome("already")              # already current
    g.item(3, "c", 0)                 # a failure is appended while open
    g.item(4, "d", 1)                 # ... and seen when the next opens
    g.end_stage(1)
    got = json.load(open(pp, encoding="utf-8"))["stages"]["circuits"]
    check("items settle as done / already / failed",
          (got["done"], got["already"], got["failed"]) == (2, 1, 1), got)
    g2 = R.Progress(None)
    g2.stage("spark", 2)
    g2.item(1, "a")
    g2.end_stage()
    check("without a path it writes nothing", not os.path.exists(
        os.path.join(tmp, "None")))
    help_ = subprocess.run([sys.executable, os.path.join(
        HERE, "run_precon_drift.py"), "--help"], capture_output=True,
        text=True, timeout=60).stdout
    check("the real script takes --plan-json --progress --stop-file",
          all(f in help_ for f in ("--plan-json", "--progress",
                                   "--stop-file")))

    child_side_checks(tmp)

    print("routes")
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from backend import app as A
    real_runner, real_act = A.PRECON, A.STORE.record_activity
    A.PRECON = runner()
    A.STORE.record_activity = lambda rows: None
    try:
        for f in ("plan.json", "progress.json"):
            p_ = os.path.join(A.PRECON.state_dir, f)
            if os.path.exists(p_):
                os.remove(p_)
        C = A.app.test_client()
        s = C.get("/api/arc/precon/status").get_json()
        check("status answers", s.get("ok") and s["server_started"]
              == A._STARTED_AT, s.get("error"))
        g = C.post("/api/arc/precon/run", json={})
        check("run with no plan is refused (409)", g.status_code == 409,
              g.status_code)
        g = C.post("/api/arc/precon/plan", json={}).get_json()
        check("plan starts", g.get("ok"), g)
        wait_idle(A.PRECON)
        plan = C.get("/api/arc/precon/status").get_json()["plan"]
        # The stand-in's plan says BOOT-A; this Jarvis is another boot.
        g = C.post("/api/arc/precon/run", json={"plan_at": plan["at"]})
        check("a plan from another Jarvis boot is refused (409)",
              g.status_code == 409 and "restarted" in g.get_json()["error"],
              g.get_json())
        pj = json.load(open(A.PRECON.plan_path, encoding="utf-8"))
        pj["server"]["started_at"] = A._STARTED_AT
        json.dump(pj, open(A.PRECON.plan_path, "w", encoding="utf-8"))
        g = C.post("/api/arc/precon/run", json={"plan_at": "not it"})
        check("a plan other than the one on file is refused (409)",
              g.status_code == 409, g.status_code)
        real_cc = A._code_changed
        A._code_changed = lambda: ["drift.py"]
        try:
            g = C.post("/api/arc/precon/run", json={"plan_at": pj["at"]})
        finally:
            A._code_changed = real_cc
        check("a Jarvis running older code is refused (409)",
              g.status_code == 409 and "drift.py" in g.get_json()["error"],
              g.get_json())
        pj["dry_run"] = False
        json.dump(pj, open(A.PRECON.plan_path, "w", encoding="utf-8"))
        g = C.post("/api/arc/precon/run", json={"plan_at": pj["at"]})
        check("the plan a run wrote as it started is refused (409)",
              g.status_code == 409 and "again" in g.get_json()["error"],
              g.get_json())
        pj["dry_run"] = True
        json.dump(pj, open(A.PRECON.plan_path, "w", encoding="utf-8"))
        g = C.post("/api/arc/precon/run", json={"plan_at": pj["at"]})
        check("CONTROL: the plan on file starts the run", g.status_code
              == 200 and g.get_json()["status"]["busy"]["what"] == "run",
              g.get_json())
        time.sleep(0.5)
        g = C.post("/api/arc/precon/stop", json={}).get_json()
        check("stop answers soft", g.get("how") == "soft", g)
        wait_idle(A.PRECON)
        check("the route's run stopped with exit 3",
              A.PRECON.status()["last"]["run"]["exit_code"] == 3)
        g = C.get("/api/arc/precon/file/md")
        check("a missing report file is a 404 that says what to do",
              g.status_code == 404 and "Write the report" in
              g.get_json()["error"])
        with open(os.path.join(docs, "dewey-precon-drift.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("# report →\n")
        with open(os.path.join(docs, "dewey-precon-drift.csv"), "w",
                  encoding="utf-8") as fh:
            fh.write("band,kind\n")
        g = C.get("/api/arc/precon/file/md")
        check("the write-up is served as text",
              g.status_code == 200 and g.mimetype == "text/plain"
              and "→" in g.get_data(as_text=True), g.status_code)
        g.close()
        g = C.get("/api/arc/precon/file/csv")
        check("the CSV downloads", g.status_code == 200 and "attachment"
              in (g.headers.get("Content-Disposition") or ""))
        g.close()
        g = C.get("/api/arc/precon/file/figure/..%2F..%2Fapp.py")
        check("a path outside the figures is a 404", g.status_code == 404)
        g = C.post("/api/arc/precon/report", json={}).get_json()
        check("report starts", g.get("ok"), g)
        wait_idle(A.PRECON)
        s = C.get("/api/arc/precon/status").get_json()
        check("the report's output is the log shown",
              s["log"]["what"] == "report"
              and s["log"]["lines"][-1] == "report written", s["log"])
        check("report files are listed with their sizes",
              s["report"]["md"]["bytes"] > 0 and s["report"]["csv"]
              and s["report"]["figures"] == ["b.png"], s["report"])
        g = C.post("/api/arc/precon/resume", json={})
        check("resume with nothing interrupted is refused (409)",
              g.status_code == 409, g.status_code)
        g = C.post("/api/arc/precon/forget", json={})
        check("forget with nothing interrupted is refused (409)",
              g.status_code == 409, g.status_code)
        os.environ["STANDIN_MODE"] = "interrupt"
        A.PRECON.start("run", "http://127.0.0.1:1")
        wait_idle(A.PRECON)
        s = C.get("/api/arc/precon/status").get_json()
        check("status says interrupted and armed",
              s["resume"]["interrupted"] and s["resume"]["armed"],
              s["resume"])
        real_cc = A._code_changed
        A._code_changed = lambda: ["coupling.py"]
        try:
            g = C.post("/api/arc/precon/resume", json={})
        finally:
            A._code_changed = real_cc
        check("resume on older code is refused (409)",
              g.status_code == 409 and "coupling.py" in g.get_json()["error"])
        os.environ["STANDIN_MODE"] = "quick"
        g = C.post("/api/arc/precon/resume", json={})
        check("CONTROL: resume carries it on",
              g.status_code == 200
              and g.get_json()["status"]["busy"]["what"] == "run",
              g.get_json())
        wait_idle(A.PRECON)
        os.environ["STANDIN_MODE"] = "interrupt"
        A.PRECON.start("run", "http://127.0.0.1:1")
        wait_idle(A.PRECON)
        g = C.post("/api/arc/precon/forget", json={})
        check("forget disarms an interrupted run",
              g.status_code == 200
              and g.get_json()["status"]["resume"]["armed"] is False)
        os.environ["STANDIN_MODE"] = ""
    finally:
        A.PRECON, A.STORE.record_activity = real_runner, real_act

    print("\n%d passed, %d failed" % (N_PASS, N_FAIL))
    return 1 if N_FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
