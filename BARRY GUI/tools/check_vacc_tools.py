# -*- coding: utf-8 -*-
"""Braces, Eye, Doppler and Spotter on a recording only the cluster has.
Offline.

    python tools/check_vacc_tools.py

What moved (2026-10-09), and what is checked about each:

  Braces / Eye   a set whose recording this computer has not got opens
                 over the link and is aligned by a job on the cluster:
                 `_braces_session` reaches for `vacc:<gid>`, the job's spec
                 carries the contacts BY CSC NUMBER, the stamps and which
                 labels count, and `vacc_run.py` rebuilds the same contacts
                 and calls the same `braces.align`.
  Doppler        a run, a batch member and a review need no copy here: the
                 node resolves the channels (the one rule), the key comes
                 from the answer's gap map, a request is recognised by its
                 hash, and the snippets come by key.
  Spotter        the participation it lights comes out of Doppler's run
                 even when this computer never had the run's events --
                 fetched once from the run directory on the cluster.
  Sessions       "Find everything on VACC" and "on netfiles" walk only what
                 they say.

Nothing talks to the cluster and nothing real is written: the login node
and the inventory are stood in for, and the vaults are temp folders.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import app as A                         # noqa: E402
from backend import braces, doppler, incisor, store, toolresults, vacc  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-72s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


SESSION = {"path": "vacc:szzzz00000002", "source": "vacc", "fs": 30000.0,
           "duration_s": 600.0, "remote": "/netfiles/bigdata_jbarry/x/rec",
           "channels": [{"index": i, "number": n, "label": "CSC%d" % n}
                        for i, n in enumerate([1, 2, 3, 4, 5, 6])]}


def braces_side():
    print("\nBraces / Eye: aligned on the cluster when this computer has none")
    real = {k: getattr(A, k) for k in ("_session_by_gid", "_vacc_place_for_gid",
                                       "_session_for")}
    A._session_by_gid = lambda gid: {"gid": gid, "here": [],
                                     "paths": ["E:\\gone\\rec"]}
    A._vacc_place_for_gid = lambda gid: {"remote": SESSION["remote"],
                                         "state": vacc.NATIVE}
    opened = []
    A._session_for = lambda path, invert=True: (
        opened.append(path) or (dict(SESSION, path=path), None))
    try:
        sess, _row = A._braces_session({"gid": "szzzz00000002",
                                        "session_path": "E:\\gone\\rec"})
        check("a set whose recording is only on VACC opens over the link",
              sess["path"] == "vacc:szzzz00000002" and opened == [
                  "vacc:szzzz00000002"], opened)

        real_push = vacc.push_code
        vacc.push_code = lambda cfg, app_dir, timeout=180: None
        try:
            chans = SESSION["channels"][1:5]
            spec = {"window_ms": 100.0, "edge_frac": 0.2, "same_ms": 1.0,
                    "measure": "csd", "band": [5.0, 100.0]}
            events = [{"start": 1.0, "label_id": "spike"},
                      {"start": 2.0, "label_id": "spike"}]
            run, where = A._braces_vacc_run(
                {"gid": "szzzz00000002"}, spec, chans, events, [1.0, 2.0],
                {"spike", "Dentate Spike"}, [3], 16,
                [("ds depth", 4), ("ds windows", 2)])
        finally:
            vacc.push_code = real_push
        js = run.spec_local
        check("the job is Braces, read from the cluster's copy",
              run.tool == "braces" and run.spec_remote["path"]
              == SESSION["remote"] and where == "vacc:netfiles", where)
        check("contacts travel by CSC number, never by row index",
              js["use_channels"] == [2, 3, 4, 5], js["use_channels"])
        check("the stamps, the labels that count and who was left out go up",
              js["stamp_times"] == [1.0, 2.0] and len(js["events"]) == 2
              and js["align_ids"] == ["Dentate Spike", "spike"]
              and js["left_out"] == [3], js)
        check("its stages are the ones the node reports",
              [n for n, _ in run.tool_steps] == ["ds depth", "ds windows"])
    finally:
        for k, v in real.items():
            setattr(A, k, v)

    print("\nvacc_run.py rebuilds the contacts and calls the same align")
    import vacc_run
    from backend import csc
    got = {}
    real_open, real_align = csc.open_session, braces.align
    csc.open_session = lambda path, invert=True: dict(SESSION, path=path,
                                                      source="ncs")
    braces.align = lambda session, use, spec, events, stamps, ids, left, n, \
        job=None: got.update(numbers=[c["number"] for c in use], ids=ids,
                             n=n, stamps=stamps) or {"out": {}, "rows": [],
                                                     "params": {}}
    real_isdir = os.path.isdir
    os.path.isdir = lambda p: True if p == SESSION["remote"] else real_isdir(p)
    try:
        vacc_run.run_tool("braces", {"path": SESSION["remote"],
                                     "use_channels": [5, 2, 4],
                                     "events": [], "stamp_times": [1.5],
                                     "align_ids": ["spike"], "left_out": [],
                                     "depth_n": 12}, {}, None, csc)
    finally:
        csc.open_session, braces.align = real_open, real_align
        os.path.isdir = real_isdir
    check("the node picks the contacts by number, in the recording's order",
          got.get("numbers") == [2, 4, 5], got)
    check("and passes the stamps, the labels and the depth through",
          got.get("stamps") == [1.5] and got.get("ids") == ["spike"]
          and got.get("n") == 12, got)
    check("channels_by_number ignores numbers the recording has not got",
          [c["number"] for c in braces.channels_by_number(SESSION, [9, 1])]
          == [1])


def doppler_side():
    print("\nDoppler: no copy here")
    spec = A._doppler_spec_vacc("g1", {"prc": 99.0},
                                {"bad_channels": [4, 2], "project": "PTEN"})
    check("the spec leaves the channels to the node and keeps the bad ones",
          spec["channels"] is None and spec["bad_channels"] == [2, 4]
          and spec["path"] == "vacc:g1" and spec["prc"] == 99.0, spec)
    h = A._doppler_request_hash("g1", spec)
    check("a request's hash is blind to the path and the resolved channels",
          h == A._doppler_request_hash("g1", dict(spec, path="/x",
                                                  channels=[0, 1])))
    check("and not blind to a setting",
          h != A._doppler_request_hash("g1", dict(spec, prc=98.0)))

    tmp = tempfile.mkdtemp(prefix="jarvis-vtools-")
    real_vault, real_ssh = A.DOPPLER_VAULT, vacc._ssh
    try:
        A.DOPPLER_VAULT = toolresults.ToolResults(
            tmp, "doppler", store.Store(tmp, auto_stage=False))
        doppler.cache_clear()
        out = {"ok": True, "n": 2, "spec_channels": [0, 2, 4],
               "spec_excluded": [{"index": 1, "number": 2}],
               "time_basis": {"gap_map_sha": "abc123"},
               "events": [{"start": 1.0, "channels": [1, 3], "peak_channel": 1,
                           "peak_uv": 900.0},
                          {"start": 5.0, "channels": [5], "peak_channel": 5,
                           "peak_uv": 700.0}],
               "snippets": {"1": [0.1, 0.2]},
               "computed_on": {"kind": "vacc", "workspace": "/w/runs/aaaabbbbcccc",
                               "file": "result_3.json"}}
        key = A._doppler_file_vacc("g1", "zz m1 s1", spec, dict(out))
        filed = dict(spec, channels=[0, 2, 4],
                     excluded=[{"index": 1, "number": 2}])
        check("filed under the key the answer implies",
              key == doppler.cache_key(filed, gap_map_sha="abc123"), key)
        rec = A.DOPPLER_VAULT.get("g1", key) or {}
        check("with the request's hash and where the run lives",
              rec.get("request_hash") == h
              and (rec.get("computed_on") or {}).get("file") == "result_3.json",
              rec)
        check("a second ask of the same question is answered",
              A._doppler_answered("g1", h) == key)
        c = A.app.test_client()
        s = c.post("/api/doppler/snippets", json={"gid": "g1", "key": key}
                   ).get_json()
        check("the snippets come by key, with no recording open",
              s.get("ok") and s.get("snippets") == {"1": [0.1, 0.2]}, s)

        print("\nSpotter: participation from a run this computer never had")
        doppler.cache_clear()
        os.remove(A.DOPPLER_VAULT.cached_path("g1", key, ".json"))
        asked = []
        vacc._ssh = lambda cfg, cmd, stdin=None, timeout=45: (
            asked.append(cmd) or json.dumps(out))
        p = c.post("/api/doppler/participation", json={"gid": "g1"}).get_json()
        check("the events and their channels are fetched from the cluster",
              p.get("ok") and p.get("n") == 2
              and p["events"][0]["channels"] == [1, 3]
              and asked and "result_3.json" in asked[0], (p, asked))
        check("and cached, so the next ask stays here",
              os.path.exists(A.DOPPLER_VAULT.cached_path("g1", key, ".json")))

        print("\na batch member with no copy here")
        A._incisor_registry_index_real = A._incisor_registry_index
        A._incisor_registry_index = lambda: {"g2": {"gid": "g2",
                                                    "n_channels": 64,
                                                    "duration_s": 600.0,
                                                    "fs": 30000.0}}
        try:
            prep = A._doppler_prepare_vacc(
                {"gid": "g2", "label": "zz", "remote": "/netfiles/x/g2",
                 "listed": {"n_channels": 128,
                            "first_ncs_bytes": 16384 + 1044 * 100000,
                            "header": "-SamplingFrequency 30000"}}, {}, False)
        finally:
            A._incisor_registry_index = A._incisor_registry_index_real
        check("prepared from the cluster's listing, finished on the node",
              prep["spec_local"]["channels"] is None
              and prep["spec_remote"]["path"] == "/netfiles/x/g2"
              and prep["resume"]["vacc_only"]
              and prep["plan"]["n_channels"] == 128, prep["plan"])
        check("and its walltime is sized from that, not the registry",
              prep["seconds"] > 1000, prep["seconds"])
    finally:
        A.DOPPLER_VAULT, vacc._ssh = real_vault, real_ssh
        doppler.cache_clear()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nvacc_run.py resolves Doppler's channels on the node")
    import vacc_run
    from backend import csc, continuity
    got = {}
    real = (csc.open_session, doppler.run, continuity.check)
    csc.open_session = lambda path, invert=True: dict(SESSION, path=path,
                                                      source="ncs")
    doppler.run = lambda session, sp, report, job=None: (
        got.update(channels=sp.get("channels")) or {"ok": True})
    continuity.check = lambda path: {"ok": True}
    real_isdir = os.path.isdir
    os.path.isdir = lambda p: True if p == SESSION["remote"] else real_isdir(p)
    try:
        res = vacc_run.run_tool("doppler", {"path": SESSION["remote"],
                                            "channels": None,
                                            "bad_channels": [2, 5]},
                                {"report": None}, None, csc)
    finally:
        csc.open_session, doppler.run, continuity.check = real
        os.path.isdir = real_isdir
    want, _ex = incisor.resolve_channels(SESSION, [2, 5])
    check("by the same rule as Incisor's node", got.get("channels") == want,
          got)
    check("and echoes what it read", res.get("spec_channels") == want, res)


def sessions_side():
    print("\nSessions: each find walks only what it says")
    cfg = {"netid": "zz", "scratch_root": "/gpfs2/scratch/zz", "places": [],
           "path_map": [{"unc": "//netfiles03.uvm.edu/bigdata_jbarry",
                         "vacc": "/netfiles/bigdata_jbarry"}]}
    walked = []
    real = {k: getattr(vacc, k) for k in ("load_config", "inventory_soon",
                                          "readable_native_roots",
                                          "inventory", "_inv_load")}
    vacc.load_config = lambda logs_dir: dict(cfg)
    vacc.inventory_soon = lambda c, root=None: walked.append(root)
    vacc.readable_native_roots = lambda c=None: ["/netfiles/bigdata_jbarry"]
    vacc.inventory = lambda c, root=None, timeout=180: []
    vacc._inv_load = lambda root: None
    vacc._INVS.clear()
    try:
        c = A.app.test_client()
        # The share is the expensive one: "on VACC" must never walk it. The
        # cluster's own space is walked by itself whenever nothing is in
        # hand (as it always was), so "on netfiles" may also start that.
        walked.clear()
        g = c.post("/api/vacc/found/look", json={"which": "vacc"}
                   ).get_json() or {}
        check("Find everything on VACC walks the cluster's space, not netfiles",
              g.get("ok") and "/gpfs2/scratch/zz" in walked
              and "/netfiles/bigdata_jbarry" not in walked,
              (walked, g.get("error")))
        walked.clear()
        g = c.post("/api/vacc/found/look", json={"which": "netfiles"}
                   ).get_json() or {}
        check("Find everything on netfiles walks the share",
              g.get("ok") and g.get("started") == ["/netfiles/bigdata_jbarry"]
              and "/netfiles/bigdata_jbarry" in walked,
              (walked, g.get("started"), g.get("error")))
        vacc._INVS.clear()
        f = c.get("/api/vacc/found").get_json() or {}
        check("a computer that never looked through netfiles is offered setup",
              f.get("setup_needed") is True, f.get("roots"))
    finally:
        for k, v in real.items():
            setattr(vacc, k, v)
        vacc._INVS.clear()


def main():
    braces_side()
    doppler_side()
    sessions_side()
    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
