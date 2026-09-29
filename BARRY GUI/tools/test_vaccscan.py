# -*- coding: utf-8 -*-
"""/api/vacc/scan writes no cluster path into the registry. Offline.

    python tools/test_vaccscan.py

A cluster path must never enter the registry (vaccio.py): it reads back as a
place this machine can open, and the recording shows as `local-only`. The
scan used to add one to every recording it matched. Now it remembers the
FOLDER as a place the cluster inventory walks, and the recordings under it
are known to be on VACC by identity.

Nothing here talks to the cluster or writes anything real: the inventory is
stood in for, the VACC config is held in memory (this machine's real
`.vacc.json` is never read for writing), and `REG.add_path` / `REG.ingest`
are wired to record any call -- which must be none. The registry is read, to
match folders to recordings, and not written.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import app as appmod, vacc  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-66s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail)[:300])
    if not ok:
        FAILED.append(name)


def main():
    # A recording the registry knows, so a cluster folder can match it.
    rec = next((r for r in (appmod.REG.all() or [])
                if r.get("gid") and r.get("paths")), None)
    if rec is None:
        print("no registered recording on this machine to match against; "
              "nothing to test")
        return 0
    # The recording's own folders, below its drive -- identity is read from
    # the mouse and session folders, so the leaf alone would match nothing.
    parts = [x for x in rec["paths"][0].replace("\\", "/").split("/") if x]
    leaf = "/".join(parts[-3:])
    scratch = "/gpfs2/scratch/zztester"
    elsewhere = "/gpfs1/home/z/z/zztester/data"
    remote = elsewhere + "/" + leaf

    cfg = {"netid": "zztester", "host": "login.vacc.uvm.edu",
           "scratch_root": scratch, "workspace": "/users/z/z/zztester/jarvis",
           "path_map": []}
    walks = []
    saved = {}
    calls = {"add_path": [], "ingest": []}

    def fake_inventory(c, root=None, timeout=180):
        walks.append(root)
        if root == elsewhere:
            return [{"path": remote, "n_channels": 64, "first_ncs_bytes": 1}]
        return []

    real = {k: getattr(vacc, k) for k in ("inventory", "load_config", "save_config")}
    real_add, real_ingest = appmod.REG.add_path, appmod.REG.ingest
    vacc.inventory = fake_inventory
    vacc.load_config = lambda logs_dir: dict(cfg, **saved)
    vacc.save_config = lambda logs_dir, **patch: saved.update(
        {k: v for k, v in patch.items() if v is not None}) or dict(cfg, **saved)
    appmod.REG.add_path = lambda *a, **k: calls["add_path"].append(a)
    appmod.REG.ingest = lambda *a, **k: calls["ingest"].append(a) or (0, 0)
    vacc._INVS.clear()
    try:
        c = appmod.app.test_client()
        print("\na dry scan of a folder outside scratch")
        got = c.post("/api/vacc/scan", json={"path": elsewhere, "dry": True}).get_json()
        check("it answers", got and got.get("ok"), got)
        gids = [a.get("gid") for a in (got or {}).get("added") or []]
        check("the recording under it would be known to be on VACC",
              rec["gid"] in gids, got)
        check("and nothing is remembered by a dry run", "places" not in saved, saved)

        print("\nthe real scan")
        got = c.post("/api/vacc/scan", json={"path": elsewhere}).get_json()
        check("it answers", got and got.get("ok"), got)
        check("NO cluster path went into the registry",
              not calls["add_path"], calls["add_path"])
        check("and nothing was registered from the cluster",
              not calls["ingest"], calls["ingest"])
        check("the folder is remembered as a place to look",
              elsewhere in (saved.get("places") or []), saved)
        check("places are scratch first, then the folder",
              vacc.places(dict(cfg, **saved)) == [scratch, elsewhere],
              vacc.places(dict(cfg, **saved)))

        print("\nthe cluster now knows it, by identity")
        walked = len(walks)
        staged, _unknown = appmod._vacc_staged()
        check("the inventory walks the remembered folder alongside scratch",
              rec["gid"] in staged and staged[rec["gid"]].get("path") == remote,
              {k: v for k, v in list(staged.items())[:3]})
        check("from the listing the scan just made, not a second walk",
              elsewhere not in walks[walked:], walks)
        again = c.post("/api/vacc/scan", json={"path": elsewhere, "dry": True}).get_json()
        check("scanning it again says it is already known",
              rec["gid"] in [a.get("gid") for a in again.get("already") or []]
              and not again.get("added"), again)

        print("\nregistering from the cluster is refused, with why")
        r = c.post("/api/vacc/scan", json={"path": elsewhere, "register": True})
        body = r.get_json() or {}
        check("refused", r.status_code == 400 and not body.get("ok"), body)
        check("saying it would put a cluster path in the registry",
              "cluster path into the registry" in (body.get("error") or ""), body)
        check("and still nothing written", not calls["add_path"] and not calls["ingest"])

        print("\na folder under scratch is not a second place")
        check("scratch covers it",
              vacc.places(dict(cfg, places=[scratch + "/sub"])) == [scratch])
    finally:
        for k, v in real.items():
            setattr(vacc, k, v)
        appmod.REG.add_path, appmod.REG.ingest = real_add, real_ingest
        vacc._INVS.clear()

    print("\n" + ("ALL PASS" if not FAILED else "%d FAILED" % len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
