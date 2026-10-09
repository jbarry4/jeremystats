# -*- coding: utf-8 -*-
"""Incisor on a recording only the cluster can read. Offline.

    python tools/check_incisor_vacc.py

The detector does not change; what changes is everything that used to need
the recording on this computer before anything was sent (incisorvacc.py).
So what is checked is that those moved without changing any answer:

  * the key a scan files under is the same whether a segmentation was in
    hand or only its `breaks_sha` came back with the answer;
  * the channels the desk resolves and the channels a compute node resolves
    are the same channels -- one function, and `vacc_run.py` really calls
    it when the spec says "work it out there";
  * a request's hash recognises the same question and not a different one;
  * a filed scan reopens by (gid, key), and `/events` and `/union` answer by
    it, with no recording open;
  * when this machine has the summary and not the events, the full answer
    is fetched from the run directory once, cached, and a run directory
    that is gone is said, not silently re-run;
  * a VACC batch's plan offers a recording this computer has no copy of,
    and marks it answered once it is.

Nothing talks to the cluster and nothing real is written: the vault is a
temp folder, the login node is stood in for, and the session is fake.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import continuity, incisor, incisorvacc, store, toolresults  # noqa: E402
from backend import vacc  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-72s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


REPORT = {"ok": True, "fs": 30000.0, "t0_us": 123456789,
          "breaks": [[0, 0, 0.0], [5120, 5130, 0.5]]}
SESSION = {"path": "vacc:szzzz00000001", "fs": 30000.0, "duration_s": 60.0,
           "channels": [{"index": i, "number": n, "label": "CSC%d" % n}
                        for i, n in enumerate([1, 2, 3, 4, 5, 6])]}


def keys():
    print("\nthe key, with and without a segmentation in hand")
    spec = {"path": "vacc:szzzz00000001", "channels": [0, 1, 3], "height_sd": 4.5}
    a = incisor.cache_key(spec, REPORT)
    b = incisor.cache_key(spec, breaks_sha=continuity.breaks_sha(REPORT))
    check("report in hand == breaks_sha carried back", a == b, (a, b))
    out = {"spec_channels": [0, 1, 3], "spec_excluded": [],
           "time_basis": {"breaks_sha": continuity.breaks_sha(REPORT)}}
    local = dict(spec, channels=None)
    check("incisorvacc.key_for gives the same key from the answer",
          incisorvacc.key_for(local, out) == a,
          (incisorvacc.key_for(local, out), a))
    check("and a different segmentation a different key",
          incisor.cache_key(spec, breaks_sha="other") != a)


def channels():
    print("\nwhich channels: the desk and the node, one rule")
    kept, excl = incisor.resolve_channels(SESSION, bad=[2, 5])
    check("bad by CSC number, never by index", kept == [0, 2, 3, 5],
          (kept, excl))
    check("and says which it left out",
          [e["number"] for e in excl] == [2, 5], excl)
    got = {}

    def fake_run(session, spec, report, job=None):
        got["channels"] = list(spec.get("channels") or [])
        return {"ok": True, "time_basis": {}}

    import vacc_run
    from backend import csc
    real = (csc.open_session, incisor.run, continuity.check)
    csc.open_session = lambda path, invert=True: dict(SESSION, path=path)
    incisor.run = fake_run
    continuity.check = lambda path: dict(REPORT)
    real_isdir = os.path.isdir
    os.path.isdir = lambda p: True if p == "/netfiles/x/rec" else real_isdir(p)
    try:
        out = vacc_run.run_tool(
            "incisor", {"path": "/netfiles/x/rec", "channels": None,
                        "bad_channels": [2, 5]},
            {"report": None}, None, csc)
    finally:
        csc.open_session, incisor.run, continuity.check = real
        os.path.isdir = real_isdir
    check("vacc_run resolves on the node when the spec says None",
          got.get("channels") == kept, got)
    check("and echoes what it read, for the desk's key",
          out.get("spec_channels") == kept
          and [e["number"] for e in out.get("spec_excluded")] == [2, 5], out)


def requests():
    print("\nthe request's hash")
    base = {"invert": True, "estimator": "sd", "bad_channels": [2, 5],
            "height_sd": 4.5, "abs_uv": 300.0, "dist_ms": 100.0,
            "prom_uv": 0.0, "wlen_ms": 125.0, "band": [5.0, 100.0],
            "lfp_fs": 1000.0}
    a = incisorvacc.request_hash("g1", base)
    check("blind to the path and the resolved channels",
          a == incisorvacc.request_hash(
              "g1", dict(base, path="/x", channels=[0, 1])))
    check("blind to the order bad channels were ticked in",
          a == incisorvacc.request_hash("g1", dict(base, bad_channels=[5, 2])))
    check("not blind to a bad channel",
          a != incisorvacc.request_hash("g1", dict(base, bad_channels=[2])))
    check("not blind to a threshold",
          a != incisorvacc.request_hash("g1", dict(base, height_sd=5.0)))
    check("not blind to the recording",
          a != incisorvacc.request_hash("g2", base))


def plans():
    print("\nthe cost, from the cluster's listing over the registry")
    rec = {"n_channels": 64, "duration_s": 601.0, "fs": 30000.0}
    spec = {"bad_channels": [3]}
    reg = incisorvacc.plan_for(rec, spec, 0.002, 0.1)
    check("from the registry when nothing is listed",
          reg["from"] == "registry" and reg["n_channels"] == 63
          and reg["span_s"] == 601.0, reg)
    # Measured 2026-10-08: on record as 64 x 601 s, on the share 128-plus
    # channel files and about 35 minutes. The listing is the truth.
    found = {"n_channels": 128, "first_ncs_bytes": 16384 + 1044 * 125000,
             "header": "-TimeCreated 2023/04/07 15:56:53 "
                       "-SamplingFrequency 30000"}
    got = incisorvacc.plan_for(rec, spec, 0.002, 0.1, found=found)
    check("the listing's channel count and length win",
          got["from"] == "cluster" and got["n_all"] == 128
          and abs(got["span_s"] - 125000 * 512 / 30000.0) < 0.01, got)
    check("and the estimate grows with them",
          got["seconds"] > reg["seconds"] * 3, (got["seconds"], reg["seconds"]))
    check("memory is sized for one channel held, not every channel",
          got["megasamples_held"] < got["megasamples"] / 30,
          (got["megasamples_held"], got["megasamples"]))
    task = incisorvacc.task_for("g1", "x", "/netfiles/x", dict(spec, path="vacc:g1"),
                                got)
    check("and the task asks slurm for that, not half a terabyte",
          task["megasamples"] == got["megasamples_held"], task["megasamples"])


def panels():
    print("\nan aid window off the cluster is drawn there")
    from backend import analysis, prewarm, vaccio
    asked = []
    real = vaccio.panel
    vaccio.panel = lambda session, spec: (asked.append(dict(spec)) or
                                          {"ok": True, "panel": spec.get("panel")})
    try:
        sess = dict(SESSION, source="vacc", remote="/netfiles/x/rec")
        got = analysis.render_panel(sess, {"panel": "csd", "t0": 1, "t1": 6,
                                           "path": sess["path"]})
        check("a CSD for a recording read off the cluster goes to the link",
              got.get("ok") and asked and asked[0]["panel"] == "csd", asked)
        vaccio.panel = lambda session, spec: {"ok": False, "error": "nope"}
        try:
            analysis.render_panel(sess, {"panel": "theta"})
            raised = False
        except analysis.PanelError as exc:
            raised = "nope" in str(exc)
        check("and the cluster's refusal arrives as the panel's own error", raised)
        check("nothing is drawn ahead off the cluster",
              prewarm.request(sess, [{"panel": "csd", "t0": 0, "t1": 5}]) == 0)
    finally:
        vaccio.panel = real


def full_answer(gid):
    rows = {0: [{"start": 1.0, "amp": 500.0, "channel": 0},
                {"start": 2.0, "amp": 520.0, "channel": 0}],
            1: [{"start": 1.0005, "amp": 480.0, "channel": 1},
                {"start": 3.0, "amp": 450.0, "channel": 1}]}
    return {"ok": True, "params": {"dist_ms": 100.0},
            "channels": [{"index": 0, "number": 1, "label": "CSC1"},
                         {"index": 1, "number": 2, "label": "CSC2"}],
            "picked": {"hilus": {"index": 0, "number": 1, "label": "CSC1",
                                 "margin": 0.2}},
            "n_by_channel": {"0": 2, "1": 2}, "chosen": 0,
            "time_basis": {"breaks_sha": continuity.breaks_sha(REPORT)},
            "spec_channels": [0, 1], "spec_excluded": [],
            "computed_on": {"kind": "vacc", "workspace": "/users/z/zz/jarvis/runs/abcabcabcabc",
                            "file": "result_0.json", "slurm_id": "1_0"},
            "_rows": rows}


def app_side():
    print("\nthe app: review by key, with no recording open")
    from backend import app as A
    tmp = tempfile.mkdtemp(prefix="jarvis-incvacc-")
    real_vault = A.INCISOR_VAULT
    real_ssh = vacc._ssh
    try:
        st = store.Store(tmp, auto_stage=False)
        A.INCISOR_VAULT = toolresults.ToolResults(tmp, "incisor", st)
        incisor.cache_clear()
        gid = "szzzz00000001"
        spec = {"path": incisorvacc.path_of(gid), "channels": None,
                "bad_channels": [], "height_sd": 4.5}
        out = full_answer(gid)
        key = A._incisor_file_vacc(gid, "zz m1 s1", spec, dict(out))
        rec = A.INCISOR_VAULT.get(gid, key)
        check("filed under the key the answer implies",
              rec and key == incisorvacc.key_for(spec, out), (key, rec))
        check("with the request's hash, for the next batch",
              rec and rec.get("request_hash")
              == incisorvacc.request_hash(gid, spec), rec)
        check("and where its full answer is",
              rec and (rec.get("computed_on") or {}).get("file")
              == "result_0.json", rec and rec.get("computed_on"))

        c = A.app.test_client()
        r = c.get("/api/incisor/result?gid=%s&key=%s" % (gid, key)).get_json()
        check("/api/incisor/result opens it", r.get("ok")
              and r["result"]["key"] == key and "_rows" not in r["result"], r)
        check("and says where to look at it: off the cluster",
              r.get("path") == "vacc:" + gid, r.get("path"))
        e = c.post("/api/incisor/events", json={"gid": gid, "key": key,
                                                "channel": 1}).get_json()
        check("/events answers by key", e.get("ok") and e.get("n") == 2, e)
        u = c.post("/api/incisor/union", json={"gid": gid, "key": key,
                                               "pool": [0, 1], "tol_ms": 25,
                                               "hilus": 0}).get_json()
        check("/union answers by key: three spikes, one seen twice",
              u.get("ok") and u.get("n") == 3, u)

        print("\nthe events are not on this machine: fetched, once")
        incisor.cache_clear()
        os.remove(A.INCISOR_VAULT.cached_path(gid, key, ".json"))
        asked = []

        def fake_ssh(cfg, cmd, stdin=None, timeout=45):
            asked.append(cmd)
            return json.dumps(dict(full_answer(gid),
                                   _rows={str(k): v for k, v in
                                          full_answer(gid)["_rows"].items()}))
        vacc._ssh = fake_ssh
        e = c.post("/api/incisor/events", json={"gid": gid, "key": key,
                                                "channel": 0}).get_json()
        check("fetched from the run directory, and the events read",
              e.get("ok") and e.get("n") == 2 and asked
              and "result_0.json" in asked[0], (e, asked))
        check("and cached, so the next ask does not go back",
              os.path.exists(A.INCISOR_VAULT.cached_path(gid, key, ".json")))
        incisor.cache_clear()
        os.remove(A.INCISOR_VAULT.cached_path(gid, key, ".json"))
        vacc._ssh = lambda cfg, cmd, stdin=None, timeout=45: "JARVIS_GONE\n"
        r = c.get("/api/incisor/result?gid=%s&key=%s" % (gid, key))
        body = r.get_json() or {}
        check("a run directory that is gone is said, not re-run",
              r.status_code == 409 and "no longer on the cluster"
              in (body.get("error") or ""), body)
    finally:
        A.INCISOR_VAULT = real_vault
        vacc._ssh = real_ssh
        incisor.cache_clear()
        shutil.rmtree(tmp, ignore_errors=True)


def plan_side():
    print("\nthe batch plan offers a recording with no copy here")
    from backend import app as A
    index = A._incisor_registry_index()
    rec = next((r for r in index.values()
                if r.get("n_channels") and not A._local_path_of(r)), None)
    if rec is None:
        print("  (every registered recording is on this computer; skipped)")
        return
    gid = rec["gid"]
    real_staged = A._vacc_staged
    real_vault = A.INCISOR_VAULT
    tmp = tempfile.mkdtemp(prefix="jarvis-incvacc-")
    try:
        A._vacc_staged = lambda force=False, wait=True: (
            {gid: {"path": "/gpfs2/scratch/zz/copy", "n_channels": 64}}, [])
        A.INCISOR_VAULT = toolresults.ToolResults(
            tmp, "incisor", store.Store(tmp, auto_stage=False))
        c = A.app.test_client()
        body = {"height_sd": 4.5}
        p = c.post("/api/incisor/batch/plan", json=body).get_json() or {}
        row = next((r for r in (p.get("todo") or []) if r["gid"] == gid), None)
        check("it is in the list, runnable", row is not None,
              [r["gid"] for r in (p.get("todo") or [])][:5])
        if row:
            check("with no local copy, a cost and its bad channels",
                  row.get("here") is None and row.get("plan", {}).get("seconds")
                  and isinstance(row.get("bad_channels"), list), row)
            check("and not yet answered", row.get("answered") is None, row)
            spec = incisorvacc.spec_for(
                gid, body, rec, A._probe_for(rec), None, A._incisor_params)
            out = full_answer(gid)
            key = A._incisor_file_vacc(gid, row["label"], spec, out)
            p = c.post("/api/incisor/batch/plan", json=body).get_json() or {}
            row = next((r for r in p["todo"] if r["gid"] == gid), None)
            check("once answered, the plan says so by its key",
                  row and row.get("answered") == key, row and row.get("answered"))
            p = c.post("/api/incisor/batch/plan",
                       json={"height_sd": 5.0}).get_json() or {}
            row = next((r for r in p["todo"] if r["gid"] == gid), None)
            check("and a different question is not answered by it",
                  row and row.get("answered") is None)
            check("a netfiles batch is capped", p.get("cap") == 8, p.get("cap"))
    finally:
        A._vacc_staged = real_staged
        A.INCISOR_VAULT = real_vault
        incisor.cache_clear()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    keys()
    channels()
    requests()
    plans()
    panels()
    app_side()
    plan_side()
    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
