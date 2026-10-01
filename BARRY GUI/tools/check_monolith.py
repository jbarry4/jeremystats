# -*- coding: utf-8 -*-
"""Checks for backend/monolith.py -- the Monolith, from upload to page.

    python tools\\check_monolith.py

Nothing here touches the cluster, the real artifact store or the real
Monolith state: the state lives in a temporary folder, the far side is a
folder on this machine (vaccupload.LocalRemote), the login node is a fake
that records what it was sent, and the artifact store is a stand-in.

  - pool() is drift.pool_rats + drift.hk_test, entry by entry, on random
    changes -- including fewer than five rats, a rat with no spread, a rat
    with zero variance and every rat changing by the same amount
  - day_stats is driftpool's mean / sd / n; minus FP is (cue - rest) with
    the variances added
  - a folder is whole only when every file is there at its size; a rat runs
    only when both its days' SPC are whole; five rats are needed
  - the tasks: four state chunks covering all 58 bands once, the slow and
    fast transitions in their own bands, PAC, and rest only with both FP
    folders; a recording whose transitions were not banked at -1/+2 s is
    measured on the node
  - the submit: one tar of specs and a script that asks for the right
    partition, time, memory and at most 100 at once; the array id read
    back; a poll read, pending ranges included; a re-run of only what did
    not answer
  - built end to end on made-up arrays: a planted change is the first
    point of interest with every rat the same way; a change that is also
    in rest is in the raw layer and not in minus FP; at most three points a
    region pair, near neighbours listed under; entry_detail agrees with the
    arrays; the page's files have the shapes the summary says
  - the routes, with all of the above stood in for
CONTROL: under no change at all, p < .05 turns up at about the chance rate
and nothing has every rat the same way more often than chance allows.
"""
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import numpy as np                                        # noqa: E402

from backend import drift, driftpool, monolith as MO, sweep, vacc  # noqa: E402
from backend import vaccupload as U                       # noqa: E402

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond or detail == "" else "  " + str(detail)[:400]))


# --------------------------------------------------------------------------
def pool_matches_drift():
    print("\npool() is drift.pool_rats + drift.hk_test")
    rng = random.Random(4)
    cases = []
    for _ in range(400):
        k = rng.choice([0, 1, 3, 4, 5, 6, 7, 8])
        rows = []
        for r in range(k):
            y = rng.gauss(rng.choice([0, 0.3]), 1)
            v = rng.choice([abs(rng.gauss(0, 0.3)) + 1e-3] * 8 + [None, 0.0])
            rows.append((y, v))
        cases.append(rows)
    # Every rat the same amount: HK variance 0.
    cases.append([(0.5, 0.1)] * 6)
    R = 8
    Y = np.full((R, len(cases)), np.nan)
    V = np.full((R, len(cases)), np.nan)
    for j, rows in enumerate(cases):
        for i, (y, v) in enumerate(rows):
            Y[i, j] = y
            V[i, j] = np.nan if v is None else v
    got = MO.pool(Y, V)
    worst = {"est": 0.0, "p": 0.0, "se": 0.0}
    bad_k = bad_same = bad_test = 0
    why_seen = set()
    for j, rows in enumerate(cases):
        rr = [{"rat": "r%d" % i, "delta": y, "v": v, "n": 4}
              for i, (y, v) in enumerate(rows)]
        mp = drift.pool_rats(rr)
        t = drift.hk_test(None, None, pooled=mp)
        k = mp["k"]
        p = t.get("p") if k >= MO.MIN_RATS else None
        mean = mp["mean"]
        same = (sum(1 for r in rr if mean is not None and r["delta"] != 0
                    and (r["delta"] > 0) == (mean > 0)) if mean else 0)
        bad_k += int(got["k"][j]) != k
        bad_same += int(got["same"][j]) != same
        tested = np.isfinite(got["p"][j])
        bad_test += tested != (p is not None)
        why_seen.add(int(got["why"][j]))
        if mean is not None:
            worst["est"] = max(worst["est"], abs(got["est"][j] - mean))
        if p is not None and tested:
            worst["p"] = max(worst["p"], abs(got["p"][j] - p))
            worst["se"] = max(worst["se"], abs(got["se"][j] - t["se"]))
    check("the same k everywhere", bad_k == 0, bad_k)
    check("the same pooled change (worst %.1e)" % worst["est"],
          worst["est"] < 1e-10, worst)
    check("tested exactly where drift tests (%d disagree)" % bad_test,
          bad_test == 0)
    check("the same p (worst %.1e) and SE (worst %.1e)"
          % (worst["p"], worst["se"]), worst["p"] < 1e-10
          and worst["se"] < 1e-10)
    check("the same count of rats changing the same way", bad_same == 0,
          bad_same)
    check("every reason an entry goes untested turns up (%s)"
          % sorted(why_seen), {0, 1, 2, 3, 4, 5} <= why_seen, why_seen)


def stats_match_driftpool():
    print("\nday_stats and the minus-FP layer")
    rng = np.random.default_rng(2)
    X = rng.normal(size=(9, 30))
    X[rng.random(X.shape) < 0.3] = np.nan
    X[:, 0] = np.nan
    X[1:, 1] = np.nan
    m, s2, n = MO.day_stats(X)
    worst = 0.0
    ok_none = True
    for j in range(X.shape[1]):
        vals = [float(v) for v in X[:, j] if np.isfinite(v)]
        mean, sd, nn = driftpool._stats(vals)
        if nn == 0:
            ok_none &= not np.isfinite(m[j]) and n[j] == 0
            continue
        worst = max(worst, abs(m[j] - mean))
        if sd is None:
            ok_none &= not np.isfinite(s2[j])
        else:
            worst = max(worst, abs(s2[j] - sd * sd / nn))
    check("mean and se^2 are driftpool._stats' (worst %.1e)" % worst,
          worst < 1e-12)
    check("no value: NaN; one value: a mean and no se^2", ok_none)

    cue = {(3, "Precon1"): (np.array([1.0]), np.array([0.1]), np.array([4])),
           (3, "Precon4"): (np.array([3.0]), np.array([0.2]), np.array([4])),
           (4, "Precon1"): (np.array([1.0]), np.array([0.1]), np.array([4]))}
    rest = {(3, "Precon1"): (np.array([0.5]), np.array([0.05]),
                             np.array([8])),
            (3, "Precon4"): (np.array([2.5]), np.array([0.05]),
                             np.array([8]))}
    rats, Y, V = MO.layer_changes(cue, rest, "raw")
    check("raw: the change is P4 - P1, its variance the two se^2",
          Y[0, 0] == 2.0 and abs(V[0, 0] - 0.3) < 1e-12)
    check("a rat with one day has no change", not np.isfinite(Y[1, 0]))
    rats, Y, V = MO.layer_changes(cue, rest, "minus_fp")
    check("minus FP: (3 - 2.5) - (1 - 0.5) = 0, variance all four se^2",
          abs(Y[0, 0]) < 1e-12 and abs(V[0, 0] - 0.4) < 1e-12, (Y, V))


# --------------------------------------------------------------------------
REGIONS = sweep.regions()


def fake_manifest(n_rats=6, units=4, rest=3, fast_banked=True, root=None):
    days = []
    for r in range(n_rats):
        rat = MO.RATS[r]
        for _n, day in MO.DAYS:
            folders = []
            for role in MO.FOLDER_ROLES:
                local = os.path.join(root or "C:/nowhere", "r%d" % rat, day,
                                     role)
                files = {"CSC1.ncs": 1000 + r, "CSC2.ncs": 50}
                folders.append({
                    "role": role, "gid": "g%d%s%s" % (rat, day, role),
                    "local": local, "files": files, "n_files": 2,
                    "bytes": sum(files.values()),
                    "remote": {"scratch": "/s/r%d/%s/%s" % (rat, day, role),
                               "temp": "/t/r%d/%s/%s" % (rat, day, role)}})
            days.append({
                "rat": rat, "day": day, "gid": "g%d%s" % (rat, day),
                "label": "r%d %s" % (rat, day), "bad": [], "blocked": {},
                "grey": [], "fast_banked": fast_banked,
                "units": [{"id": "p%02d" % (i + 1), "pair_id": i + 1,
                           "cue_type": "Click_LowTone",
                           "cue_label": "Click → Low Tone",
                           "label": "Click → Low Tone",
                           "pair": {"pair_id": i + 1, "opener_t": 100.0 + 60 * i,
                                    "closer_t": 110.0 + 60 * i,
                                    "offset_t": 120.0 + 60 * i,
                                    "label": "Click → Low Tone"},
                           "drop": {"pre": [], "cue1": []},
                           "manual": {"flat": []}} for i in range(units)],
                "rest": [{"id": "e%02d" % (i + 1), "pair_id": i + 1,
                          "label": "FP1 @ %d s" % (20 * i), "run": "FP1",
                          "fp_gid": "g%d%sFP1" % (rat, day),
                          "local": "", "pair": {"pair_id": i + 1,
                                                "t0": 20.0 * i,
                                                "t1": 20.0 * i + 10},
                          "drop": {"rest": []}, "why": None}
                         for i in range(rest)],
                "folders": folders,
                "bank": {"entry": "b%d%s" % (rat, day), "version": 2}})
    man = {"schema": MO.SCHEMA, "at": MO.now_iso(), "rats": list(MO.RATS),
           "days": days, "notes": [], "regions": REGIONS,
           "inputs": [{"kind": "bank", "entry": d["bank"]["entry"],
                       "version": 2} for d in days],
           "gids": [d["gid"] for d in days], "roots": {},
           "files_rule": MO.FILES_RULE}
    man["digest"] = MO._digest(man)
    return man


def listing_for(man, whole=(), partial=(), where="scratch"):
    """{remote dir: files} with the named (rat, day, role) whole or half."""
    out = {}
    for d, f in MO.folders_of(man):
        key = (d["rat"], d["day"], f["role"])
        rd = f["remote"][where]
        if key in whole:
            out[rd] = dict(f["files"])
        elif key in partial:
            out[rd] = {"CSC1.ncs": 3}
    return out


def data_and_tasks():
    print("\nWhat is on the cluster, and the tasks")
    man = fake_manifest()
    every = {(d["rat"], d["day"], f["role"]) for d, f in MO.folders_of(man)}
    st = MO.folder_state({"a": 1, "b": 2}, {"a": 1, "b": 2})
    check("every file at its size: complete", st["state"] == "complete")
    check("one at the wrong size: partial",
          MO.folder_state({"a": 1, "b": 2}, {"a": 1, "b": 3})["state"]
          == "partial")
    check("nothing there: missing",
          MO.folder_state({"a": 1}, {})["state"] == "missing")
    chk = MO.check_data(man, listing_for(man, whole=every))
    check("all whole: six rats ready, can run",
          chk["ready_rats"] == list(MO.RATS[:6]) and chk["can_run"],
          chk["ready_rats"])
    gone = {(MO.RATS[0], "Precon4", "SPC"), (MO.RATS[1], "Precon1", "SPC")}
    chk2 = MO.check_data(man, listing_for(man, whole=every - gone,
                                          partial=gone))
    check("a rat missing one day's SPC does not run",
          chk2["ready_rats"] == list(MO.RATS[2:6]), chk2["ready_rats"])
    check("four rats ready is not enough", not chk2["can_run"])
    fp = {(MO.RATS[2], "Precon1", "FP2")}
    chk3 = MO.check_data(man, listing_for(man, whole=every - fp))
    d3 = [x for x in chk3["days"] if x["rat"] == MO.RATS[2]
          and x["day"] == "Precon1"][0]
    check("a missing FP folder costs that day's rest, not the rat",
          MO.RATS[2] in chk3["ready_rats"] and not d3["rest_ready"]
          and d3["spc_ready"])
    tl = listing_for(man, whole=every, where="temp")
    chk4 = MO.check_data(man, tl, prefer="scratch")
    check("whole only in temp: read from temp",
          all(r["use"] == "temp" for x in chk4["days"] for r in x["folders"])
          and chk4["days"][0]["folders"][0]["remote"].startswith("/t/"))

    tasks = MO.plan_tasks(man, chk)
    kinds = {}
    for t in tasks:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    nd = 12
    check("per rat-day: 4 state chunks, slow, fast, PAC, rest, PAC rest",
          kinds == {"state": 4 * nd, "trans_slow": nd, "trans_fast": nd,
                    "pac": nd, "rest": nd, "pac_rest": nd}, kinds)
    one = [t for t in tasks if t["rat"] == MO.RATS[0]
           and t["day"] == "Precon1"]
    sb = [b for t in one if t["kind"] == "state" for b in t["spec"]["bands"]]
    check("the state chunks cover all 58 bands once",
          sorted(sb) == sorted(sweep.BAND_IDS) and len(sb) == 58)
    sl = [t for t in one if t["kind"] == "trans_slow"][0]
    fa = [t for t in one if t["kind"] == "trans_fast"][0]
    check("slow and fast transitions in their own bands",
          sl["spec"]["bands"] == sweep.bands_for("trans_slow")
          and fa["spec"]["bands"] == sweep.bands_for("trans_fast"))
    check("every task names its folder or its units do",
          all(t["spec"]["folder"] or all(u.get("folder") for u in
                                         t["spec"]["units"]) for t in tasks))
    check("and has a cost", all(t["est_s"] > 0 for t in tasks))
    tasks3 = MO.plan_tasks(man, chk3)
    check("no rest task where an FP folder is missing",
          not [t for t in tasks3 if t["rat"] == MO.RATS[2]
               and t["day"] == "Precon1" and t["kind"] in ("rest",
                                                          "pac_rest")])
    man_nb = fake_manifest(fast_banked=False)
    tnb = MO.plan_tasks(man_nb, MO.check_data(
        man_nb, listing_for(man_nb, whole=every)))
    fnb = [t for t in tnb if t["kind"] == "trans_fast"][0]
    check("transitions not banked at -1/+2 s: not computed from a guess",
          all(u["drop"] is None and u.get("why") for u in
              fnb["spec"]["units"]))
    c = MO.cost(tasks)
    check("the cost: tasks, CPU, the most at once",
          c["n_tasks"] == len(tasks) and c["cpu_s"] > 0
          and c["concurrency"] == 100)
    return man, chk, tasks


class FakeLogin(object):
    """Records what it is sent; answers sbatch, sacct and ls."""

    def __init__(self):
        self.calls = []
        self.next_id = 777000
        self.sacct = ""
        self.results = []
        self.du = 12345

    def __call__(self, cmd, stdin=None, timeout=45):
        self.calls.append((cmd, stdin))
        if "sbatch" in cmd:
            self.next_id += 1
            return "%d\n" % self.next_id
        if "sacct" in (stdin or "") if isinstance(stdin, str) else False:
            return (self.sacct + "--\n" + "\n".join(self.results) + "\n--\n"
                    + "%d\n--\n" % self.du)
        return ""


def submit_and_poll(man, tasks):
    print("\nSubmitting, polling, running again")
    import io
    import tarfile
    cfg = {"netid": "zz", "workspace": "/users/z/z/zz/jarvis",
           "scratch": "/gpfs2/scratch/zz/jarvis", "env": "",
           "modules": [], "shared": vacc._shared_of({}),
           "temp": vacc._temp_of({})}
    fake = FakeLogin()
    run = MO.submit(cfg, tasks, "temp", APP, ssh=fake)
    check("an array id comes back", run["arrays"][0]["id"] == "777001",
          run["arrays"])
    check("the run lives beside the data, in temp",
          run["rdir"].startswith("/gpfs3tmp/pi/jbarry4/sakhava1/Jarvis_temp/"
                                 "_monolith/"), run["rdir"])
    cmd, blob = fake.calls[-1]
    tar = tarfile.open(fileobj=io.BytesIO(blob))
    names = tar.getnames()
    check("one spec per task and the script, in one tar",
          len([n for n in names if n.startswith("spec_")]) == len(tasks)
          and "submit.sh" in names)
    sh = tar.extractfile("submit.sh").read().decode("utf-8")
    check("the script: array 0-%d, at most 100 at once" % (len(tasks) - 1),
          "#SBATCH --array=0-%d%%100" % (len(tasks) - 1) in sh, sh[:400])
    check("short partition, 2 h, 6 GB, one CPU, numpy on one thread",
          "--partition=short" in sh and "--time=02:00:00" in sh
          and "--mem=6G" in sh and "--cpus-per-task=1" in sh
          and "OMP_NUM_THREADS=1" in sh)
    check("it runs this run's own copy of the code",
          "cd %s/code" % run["rdir"] in sh and "cp -r" in cmd)
    b0 = json.loads(tar.extractfile("spec_0.json").read().decode("utf-8"))
    check("each spec is a sweep task with its stage declared and its "
          "output named", b0["tool"] == "sweep"
          and b0["stages"] == ["sweep units"]
          and b0["spec"]["out"].endswith("/out/%s.npz" % tasks[0]["key"]))
    n = len(tasks)
    fake.sacct = ("777001_0|COMPLETED\n777001_1|FAILED\n777001_2|RUNNING\n"
                  "777001_[3-%d%%100]|PENDING\n" % (n - 1))
    fake.results = ["result_0.json"]
    pl = MO.poll(cfg, run, ssh=fake)
    t = pl["tally"]
    check("the poll: 1 done, 1 failed, 1 running, the rest queued",
          t["done"] == 1 and t["failed"] == 1 and t["running"] == 1
          and t["queued"] == n - 3, t)
    check("still going", pl["active"] and not pl["finished"])
    fake.sacct = "777001_0|COMPLETED\n777001_1|FAILED\n" + "".join(
        "777001_%d|COMPLETED\n" % i for i in range(2, n))
    fake.results = ["result_%d.json" % i for i in range(n) if i != 1]
    pl = MO.poll(cfg, run, ssh=fake)
    check("finished: all but one answered", pl["finished"] and
          pl["tally"]["done"] == n - 1 and pl["tally"]["failed"] == 1,
          pl["tally"])
    run2 = MO.resubmit(cfg, dict(run, arrays=list(run["arrays"])), [1],
                       ssh=fake)
    cmd, stdin = fake.calls[-1]
    check("running again: only task 1, from the same specs",
          "#SBATCH --array=1%100" in stdin and len(run2["arrays"]) == 2
          and run2["arrays"][1]["indices"] == [1], stdin[:300])
    fake.sacct = "777001_1|FAILED\n777002_1|COMPLETED\n"
    fake.results = ["result_%d.json" % i for i in range(n)]
    pl = MO.poll(cfg, run2, ssh=fake)
    check("the newer array speaks for the task it ran again",
          pl["finished"] and pl["tally"]["done"] == n, pl["tally"])
    return cfg, run2


# --------------------------------------------------------------------------
PLANT = {"w": 1, "band": "f10", "m": "coherence", "pair": 0}
BOTH = {"w": 2, "band": "f20", "m": "plv", "pair": 5}


def fake_outputs(man, run, raw, seed=8, null=False):
    """Every task's npz, made up. Under `null` there is no change at all;
    otherwise PLANT rises 1.0 from Precon1 to Precon4 in every rat, and
    BOTH rises by 0.4 in cue AND rest (so minus FP takes it away)."""
    rng = np.random.default_rng(seed)
    os.makedirs(os.path.join(raw, "out"), exist_ok=True)
    days = {(d["rat"], d["day"]): d for d in man["days"]}
    R = len(REGIONS)
    P = len(sweep.pairs_of(list(range(R))))
    MI = sweep.EDGE_METHODS.index
    for t in run["tasks"]:
        d = days[(t["rat"], t["day"])]
        kind = t["kind"]
        rest = kind in ("rest", "pac_rest")
        units = d["rest"] if rest else d["units"]
        U = len(units)
        W = 4 if kind in ("state", "pac") else 3 if kind.startswith(
            "trans") else 1
        up = (t["day"] == "Precon4") and not null
        if kind.startswith("pac"):
            v = rng.normal(0.01, 0.003, (U, W, len(sweep.PAC_CELLS), R * R))
            arrays = {"values": v.astype(np.float32),
                      "wires": np.full((U, W, R), 2, np.int16)}
            meta = {"kind": kind, "units": [u["id"] for u in units],
                    "bands": [], "why": []}
        else:
            if kind == "state":
                ci = t["chunk"]
                bands = MO._chunks(sweep.bands_for("state"),
                                   MO.STATE_CHUNKS)[ci]
            else:
                bands = sweep.bands_for(kind)
            v = rng.normal(0.5, 0.1, (U, W, len(bands), len(
                sweep.EDGE_METHODS), P))
            pw = rng.normal(1.0, 0.1, (U, W, len(bands), R))
            if up and not rest and kind == "state" and PLANT["band"] in bands:
                v[:, PLANT["w"], bands.index(PLANT["band"]), MI(PLANT["m"]),
                  PLANT["pair"]] += 1.0
            if up and kind in ("state", "rest") and BOTH["band"] in bands:
                w = 0 if rest else BOTH["w"]
                v[:, w, bands.index(BOTH["band"]), MI(BOTH["m"]),
                  BOTH["pair"]] += 0.4
            arrays = {"values": v.astype(np.float32),
                      "power": pw.astype(np.float32),
                      "wires": np.full((U, W, R), 2, np.int16)}
            meta = {"kind": kind, "units": [u["id"] for u in units],
                    "bands": bands, "why": []}
        sweep.save_task(os.path.join(raw, "out", t["key"] + ".npz"),
                        arrays, meta)


class FakeArtifacts(object):
    def __init__(self):
        self.put_calls = []

    def put(self, kind, subject, payload, **kw):
        self.put_calls.append((kind, subject, payload, kw))
        return {"id": "zzmono", "version": len(self.put_calls)}


def build_end_to_end(man, tasks, work):
    print("\nBuilt end to end, on made-up arrays")
    run = {"rid": "abcdef012345", "tasks": [
        {"i": i, "key": t["key"], "rat": t["rat"], "day": t["day"],
         "kind": t["kind"], "chunk": t["chunk"], "n_units": t["n_units"],
         "est_s": t["est_s"]} for i, t in enumerate(tasks)],
        "arrays": [{"id": "1", "indices": None}], "dest": "scratch"}
    raw = os.path.join(work, "raw")
    data = os.path.join(work, "data")
    fake_outputs(man, run, raw)
    t0 = time.time()
    summ = MO.build(man, run, raw, data)
    check("built (%.0f s)" % (time.time() - t0), bool(summ))
    shape = summ["files"]["edges_raw.f32"]["shape"]
    check("the edges file: quantities x windows x bands x methods x pairs",
          shape == [len(MO.QUANTITIES), 7, 58, len(MO.METHODS), 66], shape)
    size = os.path.getsize(os.path.join(data, "edges_raw.f32"))
    check("and holds exactly that many float32",
          size == 4 * int(np.prod(shape)), size)
    top = summ["top"]["raw"]
    p0 = top[0] if top else {}
    check("the planted change is the first point of interest",
          p0.get("w") == MO.WINDOWS[PLANT["w"]] and p0.get("band") ==
          PLANT["band"] and p0.get("m") == PLANT["m"]
          and p0.get("pair") == PLANT["pair"], p0)
    check("with every rat the same way, up", p0.get("same") == 6
          and p0.get("k") == 6 and p0.get("up"), p0)
    raw_hit = [x for x in top if x["band"] == BOTH["band"]
               and x["m"] == BOTH["m"] and x["pair"] == BOTH["pair"]
               and x["w"] == MO.WINDOWS[BOTH["w"]]]
    mfp = summ["top"]["minus_fp"]
    mfp_hit = [x for x in mfp if x["band"] == BOTH["band"]
               and x["m"] == BOTH["m"] and x["pair"] == BOTH["pair"]
               and x["w"] == MO.WINDOWS[BOTH["w"]]]
    check("a change also in rest: a point in raw, gone after minus FP",
          raw_hit and not mfp_hit, (len(raw_hit), len(mfp_hit)))
    per = {}
    for x in top:
        per[x["pair"]] = per.get(x["pair"], 0) + 1
    check("at most three points a region pair", max(per.values()) <= 3, per)
    near = [x for x in top for y in top if x is not y
            and x["pair"] == y["pair"] and x["w"] == y["w"]
            and x["m"] == y["m"] and not sweep.BAND_BY_ID[x["band"]]["named"]
            and not sweep.BAND_BY_ID[y["band"]]["named"]
            and abs(x["hz"] - y["hz"]) <= MO.SAME_HZ]
    check("no two points are the same finding a hertz apart", not near,
          near[:2])
    ranks = [(-x["same"], x["p"]) for x in top]
    check("ranked by rats the same way, then p", ranks == sorted(ranks))
    check("every point has p < .05, and says so uncorrected",
          all(x["p"] < 0.05 for x in top)
          and "uncorrected" in summ["correction"])

    arr = np.fromfile(os.path.join(data, "edges_raw.f32"),
                      dtype=np.float32).reshape(shape)
    rng = random.Random(3)
    agree_all, n_seen = True, 0
    for _ in range(6):
        at = (rng.randrange(7), rng.randrange(58), rng.randrange(14),
              rng.randrange(66))
        det = MO.entry_detail(data, man, summ, "edges", "raw", at)
        n_seen += 1
        agree_all &= bool(det["agree"])
    bi = sweep.BAND_IDS.index(PLANT["band"])
    at = (PLANT["w"], bi, MO.METHODS.index(PLANT["m"]), PLANT["pair"])
    det = MO.entry_detail(data, man, summ, "edges", "raw", at)
    check("entry_detail agrees with the arrays (%d entries and the "
          "planted one)" % n_seen, agree_all and det["agree"], det.get(
              "arrays"))
    r0 = det["rats"][0]
    check("and goes all the way down: every cue pair, with its wires",
          len(r0["days"]["Precon1"]["units"]) == 4
          and r0["days"]["Precon1"]["units"][0].get("wires") == [2, 2])
    check("with each rat's weight", all(r.get("weight") for r in det["rats"]))
    det2 = MO.entry_detail(data, man, summ, "edges", "minus_fp", at)
    check("minus FP down to the rest epochs",
          len(det2["rats"][0]["days"]["Precon4"]["rest_units"]) == 3
          and det2["agree"])
    est = arr[0][at]
    check("the planted change is about +1.0 (%.3f)" % est,
          abs(est - 1.0) < 0.1)
    gn = MO.METHODS.index("gc_net")
    det3 = MO.entry_detail(data, man, summ, "edges", "raw",
                           (0, 0, gn, 0))
    u = det3["rats"][0]["days"]["Precon1"]["units"][0]
    E = np.load(os.path.join(data, "days", "r%d_Precon1_edges.npy"
                             % MO.RATS[0]))
    check("Granger net is A->B minus B->A, pair by pair",
          abs(u["v"] - (E[0, 0, 0, MO.METHODS.index("gc_ab"), 0]
                        - E[0, 0, 0, MO.METHODS.index("gc_ba"), 0])) < 1e-6)
    pdet = MO.entry_detail(data, man, summ, "pac", "raw", (0, 3, 13))
    check("PAC and power entries come apart the same way",
          pdet["agree"] and MO.entry_detail(data, man, summ, "power",
                                            "raw", (0, 3, 2))["agree"])
    fa = FakeArtifacts()
    rec = MO.file_artifact(fa, summ, man, by="zz")
    kind, subj, payload, kw = fa.put_calls[0]
    check("filed as a monolith artifact, inputs the bank entries",
          kind == "monolith" and subj["analysis"] == MO.ANALYSIS
          and kw["inputs"] == man["inputs"] and rec["id"] == "zzmono")
    check("its payload names the data files by digest",
          all(len(f["sha256"]) == 64 for f in payload["files"].values()))
    return run, summ, raw


def null_control(work):
    """Fifteen cue pairs and eight rest epochs a day, as the real days
    have. With four, each rat-day's variance rests on three degrees of
    freedom and Hartung-Knapp runs a little hot (7.6% at p < .05)."""
    print("\nControl: no change at all, real-sized days")
    man = fake_manifest(units=15, rest=8)
    every = {(d["rat"], d["day"], f["role"]) for d, f in MO.folders_of(man)}
    tasks = MO.plan_tasks(man, MO.check_data(man, listing_for(man,
                                                              whole=every)))
    run = {"rid": "abcdef012346", "tasks": [
        {"i": i, "key": t["key"], "rat": t["rat"], "day": t["day"],
         "kind": t["kind"], "chunk": t["chunk"], "n_units": t["n_units"],
         "est_s": t["est_s"]} for i, t in enumerate(tasks)]}
    raw = os.path.join(work, "rawnull")
    data = os.path.join(work, "datanull")
    fake_outputs(man, run, raw, seed=21, null=True)
    summ = MO.build(man, run, raw, data)
    c = summ["counts"]["raw"]
    rate = c["p05"] / float(c["tested"])
    check("p < .05 at about the chance rate (%.1f%% of %d)"
          % (100 * rate, c["tested"]), 0.03 <= rate <= 0.07, c)
    a6 = c["agree"].get("6") or {}
    check("all six rats the same way about as often as chance (%d vs %d)"
          % (a6.get("all_same", -1), a6.get("chance_all_same", -1)),
          a6 and abs(a6["all_same"] - a6["chance_all_same"])
          <= 0.25 * a6["chance_all_same"] + 50, a6)


# --------------------------------------------------------------------------
def routes(work, man, run_tasks, raw_src):
    print("\nThe routes, with the cluster stood in for")
    from backend import app as appmod
    root = os.path.join(work, "state")
    real_root = MO._ROOT
    MO.configure(os.path.join(work, "logs"))
    far = os.path.join(work, "far")
    # Real files on this machine for the fake manifest's folders: the CSC
    # channels, and beside them what a real DEWEY folder also holds -- video,
    # events, a log in a subfolder, a processed channel -- none of which may
    # go. The folders' file lists are then read off disk by the real rule.
    junk = {"Events.nev": 70, "VT1.nvt": 900, "VT1.mp4": 800,
            "CSC1_filtered.ncs": 300, os.path.join("ConfigurationLog",
                                                    "Cheetah.log"): 20,
            os.path.join("processed", "CSC1.ncs"): 40,
            "results.mat": 500, os.path.join("processed", "figure.png"): 60}
    kept = {"CSC1.ncs", "CSC2.ncs", "Events.nev", "VT1.nvt", "VT1.mp4",
            "CSC1_filtered.ncs", "ConfigurationLog/Cheetah.log",
            "processed/CSC1.ncs"}
    for d, f in MO.folders_of(man):
        os.makedirs(os.path.join(f["local"], "ConfigurationLog"), exist_ok=True)
        os.makedirs(os.path.join(f["local"], "processed"), exist_ok=True)
        for rel, size in list(f["files"].items()) + list(junk.items()):
            with open(os.path.join(f["local"], rel), "wb") as fh:
                fh.write(b"x" * size)
        files, left = MO._files(f["local"])
        f["files"], f["left_here"] = files, left
        f["n_files"], f["bytes"] = len(files), sum(files.values())
    check("read off disk, a folder sends what Cheetah recorded (8 files) and "
          "leaves the two processed ones here",
          all(set(f["files"]) == kept and f["left_here"]["n"] == 2
              for _d, f in MO.folders_of(man)))
    man["digest"] = MO._digest(man)
    MO.save_manifest(man)
    fake = FakeLogin()
    fa = FakeArtifacts()
    real = {"remote": appmod.MONO_REMOTE, "ssh": appmod.MONO_SSH,
            "fetch": appmod.MONO_FETCH, "arts": appmod.ARTIFACTS,
            "cfg": vacc.load_config}
    cfg = {"netid": "zz", "host": "login.vacc.uvm.edu", "configured": True,
           "workspace": "/users/z/z/zz/jarvis", "scratch": "/gpfs2/zz/jarvis",
           "env": "", "modules": [], "shared": dict(vacc._shared_of({}),
                                                    data_path="/s"),
           "temp": dict(vacc._temp_of({}), data_path="/t")}

    def fetcher(cfg_, run, into, progress=None, stop=None):
        shutil.copytree(os.path.join(raw_src, "out"),
                        os.path.join(into, "out"))
        if progress:
            progress(100)
        return len(os.listdir(os.path.join(into, "out")))

    appmod.MONO_REMOTE = lambda c: U.LocalRemote(far)
    appmod.MONO_SSH = fake
    appmod.MONO_FETCH = fetcher
    appmod.ARTIFACTS = fa
    vacc.load_config = lambda d: dict(cfg)
    try:
        c = appmod.app.test_client()
        st = c.get("/api/arc/monolith/status").get_json()
        check("status says what stays here", st["manifest"]["left_here"]
              == {"n": 2 * 36, "bytes": 36 * 560}
              and st["manifest"]["files_rule"] == MO.FILES_RULE,
              st["manifest"].get("left_here"))
        check("status: the manifest, both places, nothing run",
              st["manifest"]["n_days"] == 12 and len(st["dests"]) == 2
              and not st["run"], st.get("manifest", {}).get("n_days"))
        r = c.post("/api/arc/monolith/upload/plan",
                   json={"dest": "scratch"}).get_json()
        check("the plan: every file to send, none there yet",
              r["ok"] and r["plan"]["files"] == 36 * 8
              and r["plan"]["skipped"] == 0, r.get("plan", {}).get("files"))
        r = c.post("/api/arc/monolith/upload", json={"dest": "scratch"})
        check("an upload without confirm is refused", r.status_code == 400)
        r = c.post("/api/arc/monolith/run", json={"confirm": True})
        check("running before checking is refused", r.status_code == 409,
              r.get_json())
        r = c.post("/api/arc/monolith/upload",
                   json={"dest": "scratch", "confirm": True}).get_json()
        check("confirmed, the upload starts", r["ok"]
              and r["work"]["what"] == "upload")
        t0 = time.time()
        while time.time() - t0 < 60:
            w = c.get("/api/arc/monolith/status").get_json()["work"]
            if w and w["status"] != "running":
                break
            time.sleep(0.1)
        check("and finishes, every file sent",
              w["status"] == "done" and w["result"]["files_sent"] == 36 * 8
              and not w["result"]["failed"], w)
        landed = set()
        for _d, f in MO.folders_of(man):
            landed |= set(U.LocalRemote(far).sizes(f["remote"]["scratch"]))
        check("what reached the cluster is what Cheetah recorded -- every CSC* "
              "file, the video, the events and the logs -- and nothing "
              "processed", landed == kept, sorted(landed))
        r = c.post("/api/arc/monolith/upload/plan",
                   json={"dest": "scratch"}).get_json()
        check("planned again: nothing left to send",
              r["plan"]["files"] == 0 and r["plan"]["skipped"] == 36 * 8)
        r = c.post("/api/arc/monolith/check").get_json()
        check("the check: every folder whole, six rats, can run",
              r["ok"] and r["data"]["can_run"]
              and r["data"]["n_ready"] == 36, r.get("data", {}).get(
                  "ready_rats"))
        check("and says what the run would cost",
              r["data"]["plan"]["n_tasks"] == len(run_tasks)
              and r["data"]["plan"]["cpu_s"] > 0)
        r = c.post("/api/arc/monolith/run", json={})
        check("a run without confirm is refused", r.status_code == 400)
        r = c.post("/api/arc/monolith/run", json={"confirm": True}).get_json()
        check("confirmed, the array is submitted", r["ok"]
              and r["run"]["arrays"][0]["id"] == "777001", r)
        n = len(r["run"]["tasks"])
        fake.sacct = "".join("777001_%d|COMPLETED\n" % i for i in range(n))
        fake.results = ["result_%d.json" % i for i in range(n)]
        r = c.post("/api/arc/monolith/check").get_json()
        check("checked again: every task answered", r["poll"]["finished"]
              and r["poll"]["tally"]["done"] == n, r.get("poll"))
        r = c.post("/api/arc/monolith/fetch", json={"confirm": True})
        check("fetch starts only when pressed and confirmed",
              r.get_json()["ok"])
        t0 = time.time()
        while time.time() - t0 < 240:
            st = c.get("/api/arc/monolith/status").get_json()
            w = st["work"]
            if w and w["status"] != "running":
                break
            time.sleep(0.25)
        check("fetched, built and filed", w["status"] == "done"
              and st["built"] and st["built"]["artifact_id"] == "zzmono",
              w)
        s = c.get("/api/arc/monolith/data/summary").get_json()
        check("the page's summary is served", s.get("schema") == MO.SCHEMA
              and s["top"]["raw"])
        b = c.get("/api/arc/monolith/data/edges_raw")
        check("and its arrays, as bytes",
              b.status_code == 200 and len(b.data) ==
              4 * int(np.prod(s["files"]["edges_raw.f32"]["shape"])))
        check("a file that is not one is refused",
              c.get("/api/arc/monolith/data/..%2fstate").status_code == 404)
        p0 = s["top"]["raw"][0]
        e = c.get("/api/arc/monolith/entry?what=edges&layer=raw&at=%d,%d,%d,%d"
                  % (p0["wi"], p0["bi"], p0["mi"], p0["pair"])).get_json()
        check("one entry all the way down, agreeing with the arrays",
              e["ok"] and e["agree"] and len(e["rats"]) == 6)
        r = c.get("/api/arc/monolith/entry?what=edges&layer=raw&at=99,0,0,0")
        check("an entry outside it is refused", r.status_code == 400)
        r = c.post("/api/arc/monolith/cancel", json={"confirm": True})
        check("cancel reaches the cluster by id and name",
              r.get_json()["ok"] and any("scancel" in (x[0] or "")
                                         for x in fake.calls))
    finally:
        appmod.MONO_REMOTE = real["remote"]
        appmod.MONO_SSH = real["ssh"]
        appmod.MONO_FETCH = real["fetch"]
        appmod.ARTIFACTS = real["arts"]
        vacc.load_config = real["cfg"]
        if real_root:
            MO._ROOT = real_root


def files_rule():
    print("\nWhat Cheetah recorded goes; what was processed stays")
    for rel, want in (("CSC1.ncs", True), ("CSC64.ncs", True),
                      ("CSC12_0001.ncs", True), ("csc4.NCS", True),
                      ("CSC1_filtered.ncs", True), ("CSC_odd name 3.ncs", True),
                      ("sub/CSC9.ncs", True),
                      ("VT1.nvt", True), ("VT1.mp4", True), ("VT2.smi", True),
                      ("VT1.0003.mp4", True), ("VT1.0003.smi", True),
                      ("Events.nev", True), ("CheetahLogFile.txt", True),
                      ("DataProcessingErrors.nde", True),
                      ("ConfigurationLog/CheetahLastConfiguration.log", True),
                      ("results.mat", False), ("figure.png", False),
                      ("spikes.csv", False), ("processed/results.mat", False),
                      ("notes.docx", False), ("VT1_tracked.csv", False)):
        check("%s %s" % (rel, "goes" if want else "stays here"),
              MO.is_sent(rel) is want)
    work = tempfile.mkdtemp(prefix="zz-mono-files-")
    try:
        old = os.path.join(work, ".cache", "monolith")
        os.makedirs(old)
        MO.configure(work)
        stale = fake_manifest()
        stale.pop("files_rule")
        MO.save_manifest(stale)
        check("a manifest made before the rule is not used: it is made again",
              MO.manifest() is None)
        MO.save_manifest(fake_manifest())
        check("one made under it is", MO.manifest() is not None)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def code_list():
    print("\nThe code a run depends on")
    import subprocess
    got = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r)\n"
         "from backend import sweep, csc, monolith\n"
         "print(','.join(sorted(m.split('.', 1)[1] + '.py' for m in sys.modules"
         " if m.startswith('backend.') and m.count('.') == 1)))" % APP],
        capture_output=True, text=True, timeout=120)
    loaded = set((got.stdout or "").strip().split(","))
    missing = sorted(loaded - set(MO.CODE))
    check("monolith.CODE names every backend module a run imports, so an "
          "edit to any of them refuses the run until Jarvis restarts",
          loaded and not missing, missing or got.stderr[-300:])


def main():
    code_list()
    files_rule()
    work = tempfile.mkdtemp(prefix="zz-monolith-")
    try:
        MO.configure(os.path.join(work, "logs0"))
        pool_matches_drift()
        stats_match_driftpool()
        man, chk, tasks = data_and_tasks()
        submit_and_poll(man, tasks)
        run, summ, raw = build_end_to_end(man, tasks, work)
        null_control(work)
        man2 = fake_manifest(root=os.path.join(work, "local"))
        every = {(d["rat"], d["day"], f["role"])
                 for d, f in MO.folders_of(man2)}
        tasks2 = MO.plan_tasks(man2, MO.check_data(
            man2, listing_for(man2, whole=every)))
        routes(work, man2, tasks2, raw)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
