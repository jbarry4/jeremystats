# -*- coding: utf-8 -*-
"""How much of this archive can the cluster already read?

The answer decides what VACC Mode is. If most recordings are on a share the
cluster mounts, offloading is a mapping problem and staging is an edge case;
if most are on local disks, it is a transfer problem and everything else is
decoration. That is worth knowing before a line of staging code exists, and
it is knowable now, from the registry, without connecting to anything.

The second half is the part that is easy to get wrong. A drive letter is not
portable -- `Y:` here and `Y:` on the rig are different shares -- and on the
machine this was written on `net use` reports nothing while 2544 recorded
paths begin with `Y:`. So the resolver must work from the RECORDING, whose
paths are unioned across every machine, rather than from the path in front of
it. These fixtures pin that.

    python tools/test_vaccpaths.py            synthetic only
    python tools/test_vaccpaths.py --real     and the real registry too

Needs no cluster. `--real` reads GUI_logs/sessions and nothing else.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import vacc  # noqa: E402

FAILED = []

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(APP, "GUI_logs")

CFG = {
    "path_map": [
        {"unc": "//netfiles03.uvm.edu/bigdata_jbarry",
         "vacc": "/netfiles/bigdata_jbarry"},
    ],
}
# What a machine with the share mapped would report. Supplied rather than
# discovered, so this runs the same on the rig and on a laptop.
DRIVES = {"y:": "//netfiles03.uvm.edu/bigdata_jbarry"}


def check(name, ok, detail=""):
    print("  %-62s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail))
    if not ok:
        FAILED.append(name)


def main():
    real = "--real" in sys.argv

    print("\nthe UNC spelling maps straight through")
    state, remote, _ = vacc.resolve_path(
        "//netfiles03.uvm.edu/bigdata_jbarry/Jeremy3/KCNT1/m1.ncs", CFG, {})
    check("a share the cluster mounts is native", state == vacc.NATIVE, state)
    check("and lands on the right remote path",
          remote == "/netfiles/bigdata_jbarry/Jeremy3/KCNT1/m1.ncs", remote)

    print("\na drive letter resolves only where it means something")
    state, remote, _ = vacc.resolve_path("Y:\\Jeremy3\\KCNT1\\m1.ncs", CFG, DRIVES)
    check("mapped here, it is the same tree", state == vacc.NATIVE, state)
    check("and the same remote path as the UNC spelling",
          remote == "/netfiles/bigdata_jbarry/Jeremy3/KCNT1/m1.ncs", remote)
    state, remote, why = vacc.resolve_path("Y:\\Jeremy3\\KCNT1\\m1.ncs", CFG, {})
    check("unmapped here, the letter alone says nothing useful",
          state == vacc.LOCAL_ONLY, state + " " + str(remote))

    print("\nbut the RECORDING still answers, because paths are unioned")
    # The case the whole design turns on: this machine has no Y:, and the
    # only path it can expand is the one a colleague recorded over UNC.
    got = vacc.resolve_gid(
        "s0001",
        ["Y:\\Jeremy3\\KCNT1\\m1",
         "//netfiles03.uvm.edu/bigdata_jbarry/Jeremy3/KCNT1/m1"],
        CFG, drives={})
    check("a gid with both spellings resolves from a machine with no Y:",
          got["state"] == vacc.NATIVE, json.dumps(got))
    check("and says which path answered",
          got["via"] == "//netfiles03.uvm.edu/bigdata_jbarry/Jeremy3/KCNT1/m1",
          got["via"])

    print("\nthe four states")
    check("a local disk is local-only",
          vacc.resolve_gid("s2", ["D:\\Data\\PTEN\\m1"], CFG,
                           drives={})["state"] == vacc.LOCAL_ONLY)
    check("a share the cluster does not mount is local-only",
          vacc.resolve_gid("s3", ["//otherserver/other/m1"], CFG,
                           drives={})["state"] == vacc.LOCAL_ONLY)
    check("no paths at all is unknown, not local-only",
          vacc.resolve_gid("s4", [], CFG, drives={})["state"] == vacc.UNKNOWN)
    check("and a scanned row with no gid is skipped entirely",
          vacc.resolve_many([{"gid": None, "paths": ["D:\\x"]}], CFG) == {})

    print("\nnative beats staged, and staged beats nothing")
    staged = {"s5": {"path": "/gpfs2/scratch/x/s5", "staged_at": 1},
              "s6": {"path": "/gpfs2/scratch/x/s6", "staged_at": 2}}
    check("a recording the cluster can read in place is never 'staged'",
          vacc.resolve_gid(
              "s5", ["//netfiles03.uvm.edu/bigdata_jbarry/a"], CFG,
              drives={}, staged=staged)["state"] == vacc.NATIVE)
    check("one it cannot, but has a copy of, is staged",
          vacc.resolve_gid("s6", ["D:\\x"], CFG, drives={},
                           staged=staged)["state"] == vacc.STAGED)

    print("\nthe path map cannot climb out of its root")
    try:
        vacc._remote_path("/netfiles/share", "..", "etc")
        check("a '..' segment is refused", False, "it was accepted")
    except ValueError:
        check("a '..' segment is refused", True)
    check("a run id is checked before it becomes a path",
          _refuses(lambda: vacc.check_rid("../../etc")))
    check("and a real one is not", vacc.check_rid("0123456789ab") == "0123456789ab")

    if real:
        print("\nthe real registry")
        rows, n_paths = _registry_rows()
        if not rows:
            print("      no GUI_logs/sessions here; skipped")
        else:
            cfg = vacc.load_config(LOGS)
            if not cfg.get("path_map"):
                cfg = dict(cfg, path_map=CFG["path_map"])
            # Both ways: as this machine actually sees it, and as a machine
            # with the share mapped would. The gap between the two is exactly
            # what the per-machine drive map is worth.
            here = vacc.histogram(vacc.resolve_many(rows, cfg))
            rows2 = rows
            mapped = vacc.histogram({
                r["gid"]: vacc.resolve_gid(r["gid"], r["paths"], cfg, DRIVES)
                for r in rows2 if r.get("gid")})
            print("      %d recordings, %d recorded paths" % (len(rows), n_paths))
            print("      as this machine sees it : %s" % _fmt(here))
            print("      with Y: mapped          : %s" % _fmt(mapped))
            check("every recording got a verdict",
                  sum(here.values()) == len(rows),
                  "%d verdicts for %d recordings" % (sum(here.values()), len(rows)))
            check("something is reachable from the cluster",
                  mapped[vacc.NATIVE] > 0, _fmt(mapped))

    print()
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        return 1
    print("ALL PASS")
    return 0


def _refuses(fn):
    try:
        fn()
        return False
    except Exception:                                # noqa: BLE001
        return True


def _fmt(counts):
    return "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items()))


def _registry_rows():
    """(gid, paths) for every recording on disk, merged across shards."""
    import glob
    folder = os.path.join(LOGS, "sessions")
    by_gid, n = {}, 0
    for path in glob.glob(os.path.join(folder, "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh) or {}
        except (OSError, ValueError):
            continue
        for gid, body in _walk(rec):
            paths = body.get("paths") or []
            if isinstance(paths, dict):              # a shard's {value, at}
                paths = paths.get("v") or paths.get("value") or []
            paths = [p for p in paths if isinstance(p, str)]
            got = by_gid.setdefault(gid, set())
            before = len(got)
            got.update(paths)
            n += len(got) - before
    return ([{"gid": g, "paths": sorted(p)} for g, p in by_gid.items()], n)


def _walk(rec):
    """Shard files nest differently depending on age; take anything with a
    gid and a paths list and ignore the rest."""
    if isinstance(rec, dict):
        if rec.get("gid") and "paths" in rec:
            yield rec["gid"], rec
        for v in rec.values():
            if isinstance(v, (dict, list)):
                for got in _walk(v):
                    yield got
    elif isinstance(rec, list):
        for v in rec:
            if isinstance(v, (dict, list)):
                for got in _walk(v):
                    yield got


if __name__ == "__main__":
    raise SystemExit(main())
