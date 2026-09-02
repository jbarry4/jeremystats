"""
test_twomachines.py -- Two computers, one repo, no conflicts.

test_shards.py proves the merge algebra. This proves the thing people actually
care about: that BARRY's stores, as wired up, let two machines work on the same
recordings and end up agreeing -- and that git would have nothing to resolve.

It works on a throwaway copy of GUI_logs, so it never touches real records.

    python tools/test_twomachines.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import shards  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %-58s %s" % (name, "ok" if ok else "FAILED"))
    if not ok:
        print("      got  %r" % (got,))
        print("      want %r" % (want,))
        FAILED.append(name)


def stores(logs, machine):
    """A fresh set of BARRY's stores, pretending to be `machine`."""
    os.environ["BARRY_MACHINE"] = machine
    shards._MACHINE = None
    for mod in [m for m in list(sys.modules)
                if m.startswith("backend.") or m == "backend"]:
        pass                      # modules are stateless; only the id matters
    from backend import curation, eventbank, layers, mice, store
    st = store.Store(logs, auto_stage=False)
    return {
        "store": st,
        "layers": layers.Layers(logs, st),
        "curation": curation.Curation(logs, st),
        "mice": mice.MouseBook(logs, st),
        "bank": eventbank.EventBank(logs, st),
    }


def main():
    src = os.path.join(APP, "GUI_logs")
    tmp = tempfile.mkdtemp(prefix="barry-2m-")
    logs = os.path.join(tmp, "GUI_logs")
    shutil.copytree(src, logs)
    try:
        # Pick a real recording to work on.
        a = stores(logs, "rig-alpha")
        sess = [s for s in a["store"].all_sessions() if s.get("gid")]
        if not sess:
            print("No registered sessions to test with.")
            return 0
        target = sess[0]
        ident = {k: target.get(k) for k in
                 ("key", "loose_key", "mouse", "session", "start", "label")}
        gid = target["gid"]
        print("Working on  %s  (%s)" % (target.get("label"), gid))
        print()

        # ---- alpha does some work -------------------------------------
        a["store"].set_bad_channels(ident, [11, 22], note="alpha's pass")
        a["layers"].ensure(gid, target.get("label"), channels=[2, 4, 6, 8])
        a["layers"].set_many(gid, {2: "ca1_so", 4: "ca1_sp"})
        a["mice"].set("PTEN", target.get("mouse"), {"genotype": "PTEN fl/fl"})
        a["store"].upsert_session(dict(ident, path="D:/alpha/mount"), {})
        a["store"].set_prefs({"themes": {"rig-alpha": "horizon"},
                              "recent_scripts": ["alpha_only.m"],
                              "fav_scripts": ["one.py"]})

        # ---- beta, same repo, different knowledge ----------------------
        b = stores(logs, "rig-beta")
        b["layers"].set_many(gid, {6: "hil", 8: "dg_gcl1"})
        b["mice"].set("PTEN", target.get("mouse"), {"sex": "F"})
        b["store"].upsert_session(dict(ident, path="//netfiles/beta/mount"), {})
        bp = b["store"].get_prefs()
        b["store"].set_prefs({
            "themes": dict(bp.get("themes") or {}, **{"rig-beta": "midnight"}),
            "recent_scripts": ["beta_only.m"],
            "fav_scripts": sorted(set(bp.get("fav_scripts") or []) | {"two.py"}),
        })
        b["store"].record_error("beta", "something went wrong on beta")
        b["store"].record_activity([{"action": "beta.did.a.thing"}])

        # ---- what each of them sees ------------------------------------
        print("What both machines see")
        for who, s in (("alpha", stores(logs, "rig-alpha")),
                       ("beta", stores(logs, "rig-beta"))):
            rec, _how = s["store"].get_session(ident)
            sheet = s["layers"].get(gid)
            mouse = s["mice"].get("PTEN", target.get("mouse"))
            check("%s: both mounts are known" % who,
                  sorted(p for p in rec.get("paths") or []
                         if "mount" in p),
                  ["//netfiles/beta/mount", "D:/alpha/mount"])
            check("%s: every layer label survived" % who,
                  sorted((sheet.get("labels") or {}).items()),
                  [("2", "ca1_so"), ("4", "ca1_sp"),
                   ("6", "hil"), ("8", "dg_gcl1")])
            got = mouse.get("attrs") or {}
            check("%s: both mouse attributes survived" % who,
                  (got.get("genotype"), got.get("sex")),
                  ("PTEN fl/fl", "F"))
            check("%s: bad channels are there" % who,
                  rec.get("bad_channels"), [11, 22])

        # ---- theme is per screen, favourites are per project ------------
        print()
        print("Preferences")
        pa = stores(logs, "rig-alpha")["store"].get_prefs()
        pb = stores(logs, "rig-beta")["store"].get_prefs()
        check("each machine's theme is kept, and both are known",
              (sorted((pa.get("themes") or {}).items()),
               sorted((pb.get("themes") or {}).items())),
              ([("rig-alpha", "horizon"), ("rig-beta", "midnight")],
               [("rig-alpha", "horizon"), ("rig-beta", "midnight")]))
        check("but a machine's own recent list stays its own",
              (pa.get("recent_scripts"), pb.get("recent_scripts")),
              (["alpha_only.m"], ["beta_only.m"]))
        check("but favourites are shared",
              (sorted(pa.get("fav_scripts") or []),
               sorted(pb.get("fav_scripts") or [])),
              (["one.py", "two.py"], ["one.py", "two.py"]))

        # ---- and nothing is co-authored ---------------------------------
        print()
        print("Files")
        clash = []
        for folder, dirs, files in os.walk(logs):
            # .cache is derived and git-ignored, which is the whole point of
            # it being there rather than beside the records.
            dirs[:] = [d for d in dirs if d not in (".cache", "__pycache__")]
            for name in files:
                stem = name.rsplit(".", 1)[0]
                if shards.SIGIL not in stem and "runs" not in folder \
                        and not name.endswith(".md"):
                    clash.append(os.path.relpath(
                        os.path.join(folder, name), logs))
        check("no file without a machine tag", clash, [])

        res = subprocess.run(
            [sys.executable, os.path.join(HERE, "conflict_check.py"),
             "--logs", logs], capture_output=True, text=True)
        check("conflict_check agrees", res.returncode, 0)

    finally:
        os.environ.pop("BARRY_MACHINE", None)
        shards._MACHINE = None
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d check(s) FAILED: %s" % (len(FAILED), "; ".join(FAILED)))
        return 1
    print("Two machines, no conflicts, nobody's work lost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
