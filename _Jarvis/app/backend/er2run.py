"""EXTRACTION ROOM 2.0 -- runs: making them, running them (here or on the
VACC), bringing the answers home, and the leaderboard.

A run is a grid of tasks (target x view x model) over one frozen amber
bundle. It is numbered and never overwritten (asked 2026-11-18: "versioned and
frozen"):

  %LOCALAPPDATA%/Jarvis/er2/runs/r007/
      run.json          what was asked, where it ran, the slurm array, states
      results/<i>.json  each task's full answer (scores, every held-out call,
                        the explanation)
      leaderboard.json  the table, the MOST IMPORTANT list, the baselines

The leaderboard (small) is also filed as a versioned Jarvis artifact,
"er2_leaderboard", so it syncs to the lab like every other artifact; the
full per-task answers stay on the machine that ran them.

On the VACC: the backend is pushed (vacc.push_code), the amber bundle goes up
once per run beside its specs (a few MB), and one slurm array runs
vacc_run.py with tool "er2" per task. Nothing is written outside the run's
own folder in scratch; nothing is read from or written to /netfiles.
"""
import datetime
import io
import json
import os
import tarfile
import threading
import time

from . import artifacts as artifactsmod
from . import vacc
from .er2 import amber as AMB
from .er2 import engine as E
from .er2 import explain as EX

ROOT = os.path.join(AMB.ROOT, "runs")


def _lb_summary(payload):
    p = payload or {}
    rows = p.get("rows") or []
    return {"tasks": len(rows), "passing": sum(1 for r in rows if r.get("passes")),
            "best": max([r.get("main") or 0 for r in rows] or [0])}


artifactsmod.register_kind("er2_leaderboard", lambda s: "er2|%s" % (s or {}).get("study", "ds_pten"),
                           lambda s: "Extraction Room 2.0 · %s" % (s or {}).get("study", "ds_pten"), _lb_summary,
                           lambda s: [], "leaderboard")
PARTITION = "short"
TASK_TIME = "03:00:00"
TASK_MEM = "4G"
CONCURRENCY = 60
_LOCK = threading.Lock()
_LOCAL = {}            # rid -> {"thread", "stop", "done", "of"}
APP = None              # set by er2routes.install: the app module (its ARTIFACTS store)


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dir(rid):
    if not (rid.startswith("r") and rid[1:].isdigit()):
        raise ValueError("not a run id: %r" % rid)
    return os.path.join(ROOT, rid)


def _write_json(path, obj):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def read_run(rid):
    return json.load(open(os.path.join(_dir(rid), "run.json"), encoding="utf-8"))


def save_run(run):
    _write_json(os.path.join(_dir(run["rid"]), "run.json"), run)


def runs():
    if not os.path.isdir(ROOT):
        return []
    out = []
    for d in sorted(os.listdir(ROOT)):
        try:
            r = read_run(d)
        except (OSError, ValueError):
            continue
        out.append({k: r.get(k) for k in ("rid", "made", "where", "amber_version", "state", "n", "note", "by")})
    return out[::-1]


def new_run(targets=E.TARGETS, views=E.VIEWS, models=E.MODELS, amber_version=None, where="local", n_shuffle=0,
            explain=True, drop=True, note="", by=None):
    man, _ = AMB.load(amber_version)
    tasks = E.grid(targets, views, models)
    os.makedirs(ROOT, exist_ok=True)
    with _LOCK:
        have = [int(d[1:]) for d in os.listdir(ROOT) if d.startswith("r") and d[1:].isdigit()]
        rid = "r%03d" % ((max(have) + 1) if have else 1)
        os.makedirs(os.path.join(ROOT, rid, "results"))
    run = {"rid": rid, "made": now_iso(), "by": by, "note": note, "where": where, "amber_version": man["version"],
           "amber_fingerprint": man["fingerprint"], "n_shuffle": int(n_shuffle), "explain": bool(explain), "drop": bool(drop),
           "tasks": [dict(t, i=i, key="%s__%s__%s" % (t["target"], t["view"], t["model"])) for i, t in enumerate(tasks)],
           "n": len(tasks), "state": "made", "arrays": []}
    save_run(run)
    return run


def spec_of(run, t, amber_root=None):
    return {"target": t["target"], "view": t["view"], "model": t["model"], "amber_version": run["amber_version"],
            "amber_root": amber_root, "seed": 0, "n_shuffle": run["n_shuffle"], "explain": run["explain"], "drop": run["drop"]}


def answered(rid):
    d = os.path.join(_dir(rid), "results")
    return sorted(int(f[:-5]) for f in os.listdir(d) if f.endswith(".json") and f[:-5].isdigit())


# ------------------------------------------------------------------ here
def run_local(rid, log=print):
    """Every task not yet answered, one after another, on this machine."""
    run = read_run(rid)
    st = _LOCAL.setdefault(rid, {"stop": False, "done": 0, "of": run["n"]})
    run["state"] = "running here"
    save_run(run)
    have = set(answered(rid))
    for t in run["tasks"]:
        if st["stop"]:
            break
        if t["i"] in have:
            continue
        try:
            res = E.run_task(spec_of(run, t), log=log)
        except Exception as exc:                          # noqa: BLE001
            res = {"error": "%s: %s" % (type(exc).__name__, exc), "target": t["target"], "view": t["view"], "model": t["model"]}
        _write_json(os.path.join(_dir(rid), "results", "%d.json" % t["i"]), res)
        st["done"] = len(answered(rid))
    run = read_run(rid)
    run["state"] = "stopped" if st["stop"] else "answered"
    save_run(run)
    if not st["stop"]:
        finish(rid)
    return run


def start_local(rid):
    if rid in _LOCAL and _LOCAL[rid].get("thread") and _LOCAL[rid]["thread"].is_alive():
        return False
    _LOCAL[rid] = {"stop": False, "done": len(answered(rid)), "of": read_run(rid)["n"]}
    th = threading.Thread(target=run_local, args=(rid, lambda *a: None), daemon=True, name="er2-" + rid)
    _LOCAL[rid]["thread"] = th
    th.start()
    return True


def stop_local(rid):
    if rid in _LOCAL:
        _LOCAL[rid]["stop"] = True


# ------------------------------------------------------------------ VACC
def _tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name, data in files:
            data = data.encode("utf-8") if isinstance(data, str) else data
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = int(time.time())
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def remote_dir(cfg, rid):
    root = cfg.get("scratch") or (cfg.get("shared") or {}).get("root") or "."
    return vacc._remote_path(root, "er2", rid)


def submit_script(cfg, rdir, rid, n, indices=None):
    arr = ",".join(str(i) for i in indices) if indices else "0-%d" % max(0, n - 1)
    return ("#!/bin/bash\n"
            "#SBATCH --job-name=er2_%(rid)s\n"
            "#SBATCH --array=%(arr)s%%%(cap)d\n"
            "%(acct)s"
            "#SBATCH --partition=%(part)s\n"
            "#SBATCH --time=%(time)s\n"
            "#SBATCH --mem=%(mem)s\n"
            "#SBATCH --cpus-per-task=1\n"
            "#SBATCH --nodes=1\n"
            "#SBATCH --ntasks=1\n"
            "#SBATCH --output=%(rd)s/logs/%%A_%%a.out\n"
            "#SBATCH --mail-type=NONE\n"
            "%(pre)s\n"
            "export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1\n"
            "cd %(rd)s/code\n"
            "exec python vacc_run.py %(rd)s/spec_${SLURM_ARRAY_TASK_ID}.json\n") % {
        "rid": rid, "arr": arr, "cap": CONCURRENCY, "acct": vacc.sbatch_account(cfg), "part": PARTITION, "time": TASK_TIME,
        "mem": TASK_MEM, "rd": rdir, "pre": vacc.activate(cfg)}


def submit_vacc(cfg, rid, app_dir):
    """Push the code and the amber bundle, write every spec, submit one array."""
    run = read_run(rid)
    r = vacc._runner(cfg)
    pushed = vacc.push_code(cfg, app_dir)
    rdir = remote_dir(cfg, rid)
    v = run["amber_version"]
    ad = os.path.join(AMB.AMBER, "v%d" % v)
    files = [("amber/v%d/manifest.json" % v, open(os.path.join(ad, "manifest.json"), "rb").read()),
             ("amber/v%d/amber.npz" % v, open(os.path.join(ad, "amber.npz"), "rb").read())]
    for t in run["tasks"]:
        files.append(("spec_%d.json" % t["i"], json.dumps({"rid": "%s_%d" % (rid, t["i"]), "tool": "er2",
                                                           "spec": spec_of(run, t, amber_root=rdir + "/amber")})))
    files.append(("submit.sh", submit_script(cfg, rdir, rid, run["n"])))
    code = vacc._remote_path(cfg.get("workspace") or ".", "code")
    script = ("set -e; mkdir -p %(rd)s; cd %(rd)s; tar -xf -; mkdir -p logs; rm -rf code; cp -r %(code)s code; "
              "sbatch --parsable submit.sh" % {"rd": vacc.q(rdir), "code": vacc.q(code)})
    out = r("bash -c %s" % vacc.q(script), stdin=_tar(files), timeout=600)
    aid = next((ln.strip().split(";")[0] for ln in reversed((out or "").strip().splitlines())
                if ln.strip().split(";")[0].strip().isdigit()), None)
    if not aid:
        raise RuntimeError("The cluster did not return an array job id: %s" % (out or "nothing")[:300])
    run.update(where="vacc", rdir=rdir, state="submitted", code=pushed.get("sha256"))
    run["arrays"].append({"id": aid, "indices": None, "at": now_iso()})
    save_run(run)
    return run


def resubmit_vacc(cfg, rid, app_dir, indices):
    """Run some tasks again with the current code (pushed and copied into the run)."""
    run = read_run(rid)
    if not indices:
        return run
    r = vacc._runner(cfg)
    # the run's own code folder is refreshed in place, never removed: other
    # tasks of the same run may be starting from it at this moment
    refresh_code(cfg, rid, app_dir)
    sh = submit_script(cfg, run["rdir"], rid, run["n"], indices=sorted(indices))
    script = ("set -e; cd %(rd)s; cat > submit_again.sh; sbatch --parsable submit_again.sh" % {"rd": vacc.q(run["rdir"])})
    out = r("bash -c %s" % vacc.q(script), stdin=sh, timeout=300)
    aid = next((ln.strip().split(";")[0] for ln in reversed((out or "").strip().splitlines())
                if ln.strip().split(";")[0].strip().isdigit()), None)
    if not aid:
        raise RuntimeError("The cluster did not return an array job id: %s" % (out or "nothing")[:300])
    run["arrays"].append({"id": aid, "indices": sorted(indices), "at": now_iso()})
    save_run(run)
    return run


def refresh_code(cfg, rid, app_dir):
    """Put the current backend into a submitted run's code folder (tasks still
    queued pick it up when they start)."""
    run = read_run(rid)
    vacc.push_code(cfg, app_dir)
    code = vacc._remote_path(cfg.get("workspace") or ".", "code")
    vacc._runner(cfg)("bash -c %s" % vacc.q("set -e; cp -r %s/backend/er2/. %s/code/backend/er2/" % (vacc.q(code), vacc.q(run["rdir"]))),
                      timeout=300)


def poll_vacc(cfg, rid):
    """Slurm's word for every task, and which have written an answer."""
    from . import monolith
    run = read_run(rid)
    if not run.get("rdir"):
        return {"tasks": [], "finished": False}
    return monolith.poll(cfg, dict(run, tasks=[{"i": t["i"], "key": t["key"]} for t in run["tasks"]]))


def fetch_vacc(cfg, rid):
    """Bring home every answer not here yet (each is a few hundred KB of JSON)."""
    run = read_run(rid)
    r = vacc._runner(cfg)
    have = set(answered(rid))
    blob = r("bash -c %s" % vacc.q("cd %s && tar -cf - result_*.json 2>/dev/null || true" % vacc.q(run["rdir"])),
             timeout=600, binary=True) if _runner_takes_binary(r) else None
    got = 0
    if blob:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r") as tar:
            for m in tar.getmembers():
                nm = os.path.basename(m.name)
                if not (nm.startswith("result_") and nm.endswith(".json")):
                    continue
                i = int(nm[len("result_"):-5])
                if i in have:
                    continue
                data = tar.extractfile(m).read()
                with open(os.path.join(_dir(rid), "results", "%d.json" % i), "wb") as fh:
                    fh.write(data)
                got += 1
    else:
        for t in run["tasks"]:
            if t["i"] in have:
                continue
            txt = r("cat %s/result_%d.json 2>/dev/null || true" % (vacc.q(run["rdir"]), t["i"]), timeout=120)
            if txt and txt.strip().startswith("{"):
                _write_json(os.path.join(_dir(rid), "results", "%d.json" % t["i"]), json.loads(txt))
                got += 1
    if len(answered(rid)) == run["n"]:
        run["state"] = "answered"
        save_run(run)
        finish(rid)
    return {"fetched": got, "answered": len(answered(rid)), "n": run["n"]}


def _runner_takes_binary(r):
    import inspect
    try:
        return "binary" in inspect.signature(r).parameters
    except (TypeError, ValueError):
        return False


def cancel_vacc(cfg, rid):
    run = read_run(rid)
    for a in run.get("arrays") or []:
        try:
            vacc.cancel(cfg, slurm_id=a["id"])
        except Exception:                                 # noqa: BLE001
            pass
    run["state"] = "cancelled"
    save_run(run)
    return run


# ------------------------------------------------------------------ the leaderboard
def results(rid):
    out = []
    for i in answered(rid):
        try:
            out.append(json.load(open(os.path.join(_dir(rid), "results", "%d.json" % i), encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def leaderboard(rid):
    R = [r for r in results(rid) if "score" in r]
    # the nuisance-only baseline: the same model on placement / year / counts
    # only; for the set networks (which need events) the best pooled model's
    base = {(r["target"], r["model"]): r["score"]["main"] for r in R if r["view"] == "nuisance"}
    for r in R:
        if r["view"] == "nuisance":
            k = (r["target"], "*")
            base[k] = max(base.get(k, -9), r["score"]["main"])
    rows = []
    for r in R:
        ex = r.get("explain") or {}
        rows.append({"target": r["target"], "view": r["view"], "model": r["model"], "task": r["task"], "main": r["score"]["main"],
                     "score": r["score"], "passes": r.get("passes"), "bar": r.get("bar"),
                     "chance_p": (r.get("chance") or {}).get("p"), "nuisance_baseline": base.get((r["target"], r["model"]), base.get((r["target"], "*"))),
                     "top_family": ((ex.get("perm_family") or [{}])[0]).get("item"),
                     "top_feature": ((ex.get("perm_feature") or [{}])[0]).get("item"), "seconds": r.get("seconds")})
    rows.sort(key=lambda x: (x["target"], -(x["main"] if x["main"] == x["main"] else -9)))
    most = {}
    for tg in E.TARGETS:
        mine = [r for r in R if r["target"] == tg and r["view"] != "nuisance"]
        good = [r for r in mine if r.get("passes")]
        why = "models that reached the bar"
        if not good:
            good = sorted(mine, key=lambda r: -(r["score"]["main"] if r["score"]["main"] == r["score"]["main"] else -9))[:3]
            why = "no model reached the bar: built from the three best"
        if good:
            most[tg] = dict(EX.consolidate(good), basis=why)
    errs = [{"target": r.get("target"), "view": r.get("view"), "model": r.get("model"), "error": r["error"]}
            for r in results(rid) if "error" in r]
    lb = {"rid": rid, "made": now_iso(), "rows": rows, "most_important": most, "errors": errs, "bar": E.BAR}
    _write_json(os.path.join(_dir(rid), "leaderboard.json"), lb)
    return lb


def finish(rid, artifacts=None, by=None):
    """The leaderboard, and (when given the store) its versioned artifact."""
    lb = leaderboard(rid)
    if artifacts is None and APP is not None:
        artifacts = getattr(APP, "ARTIFACTS", None)
    if artifacts is not None:
        run = read_run(rid)
        payload = {"rid": rid, "amber_version": run["amber_version"], "amber_fingerprint": run["amber_fingerprint"],
                   "where": run["where"], "rows": lb["rows"], "most_important": lb["most_important"], "bar": lb["bar"]}
        art = artifacts.put("er2_leaderboard", {"study": "ds_pten"}, payload, params={"n_shuffle": run["n_shuffle"]},
                            by=by, note="run %s" % rid)
        run["artifact"] = {"id": art.get("id"), "version": art.get("version")}
        save_run(run)
    return lb
