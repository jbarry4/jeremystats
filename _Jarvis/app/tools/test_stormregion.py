# -*- coding: utf-8 -*-
"""A KCNT1 dual recording, one array at a time (backend/stormregion.py).

    python tools/test_stormregion.py

The rules on their own, then the routes for real against this machine's
bank -- inside the practice layer (backend/pisafe.py), so every entry this
makes is written under the layer's name and thrown away at the end. Nothing
real is written; `git status` of GUI_logs is compared before and after.
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from backend import stormregion as sr  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


def git_status():
    return subprocess.run(["git", "status", "--porcelain", "--", "GUI_logs"],
                          cwd=ROOT, capture_output=True, text=True).stdout


def rules():
    print("\nthe rules")
    check("hippocampus by any of its names",
          all(sr.which(x) == "hip" for x in ("Hippocampus", "HPC", " hip ")))
    check("M2", sr.which("m2") == "m2")
    check("not connected is neither", sr.which("Not connected") is None)
    named = {"channel_banks": [
        {"id": "b1", "first": 1, "last": 64, "region": "Hippocampus"},
        {"id": "b2", "first": 65, "last": 128, "region": "M2"}]}
    regs = sr.regions_for(named)
    check("named banks give both arrays",
          regs and [r["id"] for r in regs] == ["hip", "m2"]
          and regs[1]["first"] == 65 and regs[1]["last"] == 128, regs)
    check("the dual template alone gives them too",
          sr.regions_for({"probe": "dual"}) == regs)
    check("an unnamed 128-channel recording is not guessed",
          sr.regions_for({"channel_banks": [
              {"first": 1, "last": 64, "region": None},
              {"first": 65, "last": 128, "region": None}]}) is None)
    check("hippocampus and not connected is not a dual",
          sr.regions_for({"channel_banks": [
              {"first": 1, "last": 64, "region": "Hippocampus"},
              {"first": 65, "last": 128, "region": "Not connected"}]}) is None)
    check("a range is its array", sr.for_range(regs, [65, 128])["id"] == "m2")
    check("'from 65 to the end' is M2", sr.for_range(regs, [65, 9999])["id"] == "m2")
    check("a range across both is neither", sr.for_range(regs, [1, 128]) is None)
    check("an entry says its region",
          sr.region_of({"source": {"parameters": {"region": "m2"}}}) == "m2")
    check("or its run's range says it",
          sr.region_of({"source": {"parameters": {"channel_range": [1, 64]}}},
                       regs) == "hip")
    evs = [{"start": 1, "channel": 2}, {"start": 2, "channel": 70},
           {"start": 3}, {"start": 4, "channel": 64}]
    kept, blind = sr.split_events(evs, regs[0])
    check("events split by peak channel", [e["start"] for e in kept] == [1, 4]
          and blind == 1, (kept, blind))
    check("the name gets its region once",
          sr.name_with(sr.name_with("m3 s2  ·  Doppler", regs[1]), regs[1])
          == "m3 s2  ·  Doppler  ·  M2")


def routes():
    print("\nthe routes, inside the practice layer")
    before = git_status()
    from backend import app as appmod, pisafe, shards  # noqa: E402
    logs = appmod.LOGS_DIR
    had_state = os.path.isdir(pisafe.state_dir(logs))
    shards.configure_safe(True, pisafe.state_dir(logs))
    try:
        c = appmod.app.test_client()
        gid = None
        for r in appmod.REG.all():
            if sr.regions_for(r) and r.get("gid"):
                gid = r["gid"]
                row = r
                break
        if not gid:
            check("a dual recording to try it on", False, "none named here")
            return
        regs = appmod._storm_regions(gid)
        check("the server finds its two arrays", regs and len(regs) == 2)
        made = appmod.BANK.add({
            "gid": gid, "project": row.get("project"), "mouse": row.get("mouse"),
            "session": row.get("session"), "type": "ied", "type_name": "P-spike",
            "name": "stormregion test — delete me", "curated": True,
            "events": [
                {"start": 10.001, "channel": 2, "label_id": "solid", "label": "Solid"},
                {"start": 11.001, "channel": 4, "label_id": "garbage", "label": "Garbage"},
                {"start": 12.001, "channel": 70, "label_id": "solid", "label": "Solid"},
                {"start": 13.001, "label_id": "solid", "label": "Solid"}],
            "label_names": {"solid": "Solid", "garbage": "Garbage"},
            "pipeline": "Doppler (line length)", "detector": "LLspikedetector",
            "added_by": "stormregion test"})
        eid = made["id"]
        got = c.get("/api/storm/regions/%s?entry=%s" % (gid, eid)).get_json()
        check("the entry covers both arrays", got["regions"] and not got.get("entry_region")
              and got.get("splits") == {}, got)
        res = c.post("/api/storm/split", json={"entry_id": eid,
                                               "regions": ["hip", "m2"]}).get_json()
        ents = {e["region"]: e for e in res.get("entries") or []}
        check("both: two new entries", res.get("ok") and set(ents) == {"hip", "m2"}
              and all(e["id"] and not e["existed"] for e in ents.values()), res)
        hip = appmod.BANK.get(ents["hip"]["id"])
        m2 = appmod.BANK.get(ents["m2"]["id"])
        check("the hippocampal one holds its two", hip["n"] == 2
              and hip["name"].endswith("·  HIP"), (hip["n"], hip["name"]))
        check("the M2 one holds its one", m2["n"] == 1 and m2["name"].endswith("·  M2"))
        check("decisions kept", sorted(e.get("label_id") for e in hip["events"])
              == ["garbage", "solid"])
        p = hip["source"]["parameters"]
        check("each says its region and its parent",
              p.get("region") == "hip" and p["split_from"]["entry"] == eid)
        check("each has its own history, with the parent in the note",
              hip["versions"] and "Split from" in (hip["versions"][-1].get("note") or "")
              and "1 had no channel" in hip["versions"][-1]["note"],
              hip["versions"][-1].get("note"))
        check("still the Doppler pipeline, so Eye lists it as The Storm's",
              hip["source"]["pipeline"] == "Doppler (line length)")
        check("the parent is untouched", appmod.BANK.get(eid)["n"] == 4)
        again = c.post("/api/storm/split", json={"entry_id": eid,
                                                 "regions": ["m2"]}).get_json()
        check("asked again: the same entry, not a second",
              again["entries"][0]["id"] == m2["id"] and again["entries"][0]["existed"])
        got = c.get("/api/storm/regions/%s?entry=%s" % (gid, hip["id"])).get_json()
        check("a split entry is about one array", got.get("entry_region") == "hip")
        no = c.post("/api/storm/split", json={"entry_id": hip["id"],
                                              "regions": ["m2"]})
        check("and is not split again", no.status_code == 400)

        auto = appmod._doppler_autobank(gid, "zz-stormregion-test", {
            "events": [{"start": 20.0, "peak_channel": 80, "peak_uv": 300}],
            "params": {"channel_range": [65, 128], "band": [20, 300],
                       "method": "storm"}})
        ent = appmod.BANK.get(auto["id"]) if auto else None
        check("a Doppler run on M2's range banks as M2",
              ent and "M2" in ent["name"]
              and ent["source"]["parameters"].get("region") == "m2",
              ent and ent["name"])
        check("held routes still pass Doppler through", not pisafe.held(
            "/api/storm/split", "POST"))
    finally:
        time.sleep(1.0)          # the mirror thread, which reads the real view
        got = pisafe.revert(logs)
        shards.configure_safe(False, pisafe.state_dir(logs))
        if not had_state:
            shutil.rmtree(pisafe.state_dir(logs), ignore_errors=True)
        check("the practice layer took it all back", not got["failed"], got)
        check("GUI_logs is exactly as it was", git_status() == before)


if __name__ == "__main__":
    rules()
    routes()
    print("\n%s" % ("FAILED: %d" % len(FAILED) if FAILED else "all passed"))
    sys.exit(1 if FAILED else 0)
