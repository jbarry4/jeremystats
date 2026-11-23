"""check_er2_fetch_race.py -- Extraction Room 2.0's "bring answers home",
asked for twice at once.

2026-11-20 09:21:58 on Bluebarry: "Ask the VACC and bring answers home" was
pressed again while the first fetch of r005 was still going (it takes three
minutes over ssh, one `cat` per task, and the button shows nothing while it
works). Both fetches walked the same unanswered tasks in step, and both
wrote each answer through the same `<i>.json.part`, so one renamed the
other's half-written `.part`: WinError 32 on the rename, the first fetch
failed, the second carried on. `er2run.fetch_vacc` now brings a run's
answers home one fetch at a time, and `_write_json` writes through a `.part`
of its own.

Builds a throwaway run in a temp folder (never the real er2 runs), gives it
a fake VACC runner that answers each `cat` after a short wait with a few
hundred KB of JSON, then has THREADS fetches of the same run go at once,
ROUNDS times. Writes nothing outside the temp folder.

    python tools/check_er2_fetch_race.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from backend import er2run as R                        # noqa: E402

THREADS, ROUNDS, N = 4, 3, 40
ok = bad = 0


def check(name, cond, detail=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    " + name)
    else:
        bad += 1
        print("  FAIL  " + name + ("\n        " + str(detail) if detail else ""))


BIG = json.dumps({"score": 0.5, "calls": [{"mouse": "m%d" % k, "p": [0.1] * 40} for k in range(400)]})


def fake_runner(cfg):
    def r(cmd, timeout=None):           # no `binary`: the per-task `cat` path, as on 11-20
        time.sleep(0.002)
        return BIG
    return r


tmp = tempfile.mkdtemp(prefix="er2race_")
real_root, real_runner, real_finish = R.ROOT, R.vacc._runner, R.finish
R.ROOT = tmp
R.vacc._runner = fake_runner
R.finish = lambda rid, *a, **k: None    # files an artifact; not what is checked here
try:
    for rnd in range(ROUNDS):
        rid = "r%03d" % (rnd + 1)
        os.makedirs(os.path.join(tmp, rid, "results"))
        R.save_run({"rid": rid, "where": "vacc", "rdir": "/scratch/x/" + rid, "n": N, "state": "submitted",
                    "tasks": [{"i": i, "key": "k%d" % i, "target": "t", "view": "v", "model": "m"} for i in range(N)]})
        errs, outs = [], []
        go = threading.Barrier(THREADS)

        def one():
            go.wait()
            try:
                outs.append(R.fetch_vacc({}, rid))
            except Exception as exc:    # noqa: BLE001
                errs.append("%s: %s" % (type(exc).__name__, exc))

        ts = [threading.Thread(target=one) for _ in range(THREADS)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        res = os.path.join(tmp, rid, "results")
        left = [f for f in os.listdir(res) if f.endswith(".part")]
        good = 0
        for i in range(N):
            try:
                json.load(open(os.path.join(res, "%d.json" % i), encoding="utf-8"))
                good += 1
            except (OSError, ValueError):
                pass
        check("round %d: %d fetches at once, none failed" % (rnd + 1, THREADS), not errs, errs[:2])
        check("round %d: all %d answers home and whole" % (rnd + 1, N), good == N, "%d of %d" % (good, N))
        check("round %d: no .part left behind" % (rnd + 1), not left, left[:3])
        check("round %d: each answer brought home once" % (rnd + 1),
              sum(o["fetched"] for o in outs) == N, [o["fetched"] for o in outs])
finally:
    R.ROOT, R.vacc._runner, R.finish = real_root, real_runner, real_finish
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
