# -*- coding: utf-8 -*-
"""The first opening after Setup, and the caches it leaves behind.

    python tools/test_firstrun.py

What Setup writes down (backend/firstrun.py) and what the app makes of it;
the "will this folder open" answers kept on disk between starts
(sessreg.keep_opens), the thing that took the first registry read after a
restart from 3.0 s to 0.7 s here; and the two getting-ready jobs behind
/api/firstrun/prepare, run for real against this machine's registry --
except the shared database, which is made to look unconfigured so nothing
is pulled or pushed. The firstrun record lives in a temp folder.
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import app as appmod, firstrun, livefeed, sessreg  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-66s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="jarvis_firstrun_")

    print("\nwhat Setup writes down")
    check("a computer with no record is not a first opening",
          not firstrun.wanted({}))
    check("but it does get the optimisation update", firstrun.optimize_wanted({}))
    check("once, at this version", not firstrun.optimize_wanted(
        {"optimized": firstrun.OPTIMIZE_VERSION}))
    check("and again when a later update raises the version",
          firstrun.optimize_wanted({"optimized": firstrun.OPTIMIZE_VERSION - 1}))
    rec = firstrun.update(tmp, setup_at=time.time(), accounts={"vacc": True},
                          ready_at=None)
    check("after Setup the getting-ready stage is wanted", firstrun.wanted(rec))
    check("and not the optimisation update as well -- it is the same job",
          not firstrun.optimize_wanted(rec))
    rec = firstrun.mark_ready(tmp)
    check("and once it has run it is not", not firstrun.wanted(rec))
    check("what Setup did is kept beside it",
          firstrun.read(tmp).get("accounts") == {"vacc": True})
    rec = firstrun.update(tmp, setup_at=time.time(), ready_at=None)
    check("Setup run again asks for it again", firstrun.wanted(rec))

    print("\nthe folder answers survive a restart")
    keep = os.path.join(tmp, "opens.json")
    was_file, was = sessreg._OPENS_FILE[0], dict(sessreg._OPENS)
    try:
        sessreg._OPENS.clear()
        sessreg._OPENS["X:\\nowhere\\m1"] = (123.5, True)
        sessreg._OPENS_FILE[0] = keep
        sessreg._OPENS_SAVED[0] = None
        sessreg.save_opens()
        check("written down", os.path.isfile(keep))
        sessreg._OPENS.clear()
        sessreg.keep_opens(keep)
        check("and read back the same", sessreg._OPENS.get("X:\\nowhere\\m1")
              == (123.5, True), sessreg._OPENS)
        stamp = os.path.getmtime(keep)
        time.sleep(0.05)
        sessreg.save_opens()
        check("an unchanged cache is not rewritten",
              os.path.getmtime(keep) == stamp)
        sessreg.keep_opens(os.path.join(tmp, "missing.json"))
        check("a missing file is an empty cache, not an error", True)
    finally:
        sessreg._OPENS.clear()
        sessreg._OPENS.update(was)
        sessreg._OPENS_FILE[0] = was_file

    print("\nthe routes")
    real_path = firstrun.path
    firstrun.path = lambda logs_dir: real_path(tmp)
    real_reload = appmod.CLOUD.cloud.reload
    appmod.CLOUD.cloud.reload = lambda: {}          # nothing goes to Supabase
    client = appmod.app.test_client()
    try:
        got = client.get("/api/firstrun").get_json()
        check("/api/firstrun says it is wanted", got.get("wanted") is True, got)
        cat = client.get("/api/catalog").get_json()
        check("and so does the catalogue the boot already reads",
              cat.get("firstrun") is True)
        bad = client.post("/api/firstrun/prepare", json={"stage": "all"})
        check("an unknown stage is refused", bad.status_code == 400)

        since = livefeed.read(-1)["next"]
        client.post("/api/firstrun/prepare", json={"stage": "sync"})
        done = wait(client, "sync")
        check("with no key, the sync says so and moves on",
              (done or {}).get("skipped") is True, done)
        lines = [ln["text"] for ln in livefeed.read(since)["lines"]
                 if ln.get("task") == "ready:sync"]
        check("in words", any("no shared-database key" in t for t in lines),
              lines)

        since = livefeed.read(-1)["next"]
        t0 = time.time()
        client.post("/api/firstrun/prepare", json={"stage": "cache"})
        again = client.post("/api/firstrun/prepare",
                            json={"stage": "cache"}).get_json()
        check("asking twice does not start a second", again.get("running") == "cache")
        done = wait(client, "cache", limit=300)
        check("the caches are built (%.1f s)" % (time.time() - t0),
              bool(done and (done.get("folders") or {}).get("of")), done)
        feed = livefeed.read(since)
        tasks = {t["name"]: t["state"] for t in feed["tasks"]}
        for name in ("ready:folders", "ready:registry", "ready:status",
                     "ready:engines"):
            check("%s finished" % name, tasks.get(name) == "done", tasks)
        said = [ln["text"] for ln in feed["lines"]]
        check("every folder count is said",
              any("folders reachable from this computer" in t for t in said))
        check("and the recordings list",
              any("the recordings list every tool picks from" in t for t in said))
        got = client.get("/api/firstrun").get_json()
        check("the job finishing records the optimisation",
              bool(got.get("optimized_at")) and got.get("optimize") is False, got)
        check("so the catalogue stops asking for it",
              client.get("/api/catalog").get_json().get("optimize") is False)

        client.post("/api/firstrun", json={"ready": True})
        got = client.get("/api/firstrun").get_json()
        check("marking it ready stops it being wanted", got.get("wanted") is False)
    finally:
        firstrun.path = real_path
        appmod.CLOUD.cloud.reload = real_reload

    print("\n%s" % ("all passed" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


def wait(client, stage, limit=60):
    end = time.time() + limit
    while time.time() < end:
        job = client.get("/api/firstrun").get_json().get("job") or {}
        if job.get("running") != stage and (job.get("done") or {}).get(stage):
            return job["done"][stage]
        if not job.get("running") and job.get("error"):
            return {"error": job["error"]}
        time.sleep(0.3)
    return None


if __name__ == "__main__":
    sys.exit(main())
