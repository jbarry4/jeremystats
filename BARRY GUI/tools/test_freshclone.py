"""
test_freshclone.py -- What somebody gets when they clone the repo.

The question this answers is "will it just work for the next person", and the
only honest way to ask it is to build what git would actually hand them --
tracked files only, none of the gitignored local state -- and then see what
BARRY does with it.

What must be true:

  * it starts, with no key and no local caches
  * it knows which Supabase project to sync to, because that is tracked
  * it does NOT have the key, because that never is
  * it asks for the key rather than failing or syncing to nothing
  * the derived folders (Data Bank, .cache) rebuild themselves
  * every recording, figure and event is there to look at offline

Nothing here touches the real GUI_logs.

    python tools/test_freshclone.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
REPO = os.path.dirname(APP)
sys.path.insert(0, APP)

FAILED = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print("  %-56s %s" % (name, "ok" if ok else "FAILED"))
    if not ok:
        if detail:
            print("      %s" % detail)
        FAILED.append(name)
    return ok


def tracked_files():
    """Exactly what a clone gets: everything git tracks, plus anything new
    that is not ignored (which is what the next commit will include)."""
    def run(args):
        res = subprocess.run(args, cwd=REPO, capture_output=True, text=True,
                             timeout=120)
        return [l for l in res.stdout.splitlines() if l.strip()]

    files = set(run(["git", "ls-files", "--", "BARRY GUI"]))
    files |= set(run(["git", "ls-files", "--others",
                      "--exclude-standard", "--", "BARRY GUI"]))
    return sorted(files)


def main():
    print("Building what a clone would get...")
    files = tracked_files()
    tmp = tempfile.mkdtemp(prefix="barry-clone-")
    dest_app = os.path.join(tmp, "BARRY GUI")
    n = 0
    for rel in files:
        src = os.path.join(REPO, rel)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    print("  %d file(s) copied to a throwaway directory" % n)
    print()

    try:
        print("What the clone has, and has not")
        check("the app is there", os.path.isfile(
            os.path.join(dest_app, "start.py")))
        check("so are the session records",
              len([f for f in files if "/GUI_logs/sessions/" in f]) > 100,
              "%d" % len([f for f in files if "/GUI_logs/sessions/" in f]))
        check("and the figures",
              len([f for f in files if "/Results/" in f]) > 0)
        check("and the SQL to set up the database",
              os.path.isfile(os.path.join(dest_app, "supabase",
                                          "01_schema.sql")))
        check("it knows which project to sync to",
              os.path.isfile(os.path.join(dest_app, "cloud.json")))
        check("but NOT the key",
              not os.path.exists(os.path.join(dest_app, "GUI_logs",
                                              ".cloud.json")),
              "GUI_logs/.cloud.json came through -- it must be gitignored")
        check("and no derived caches came with it",
              not os.path.exists(os.path.join(dest_app, "GUI_logs", ".cache"))
              and not os.path.exists(os.path.join(dest_app, "Data Bank")))

        # No key anywhere in what git carries. Two tests, because either
        # alone is weak: a pattern that matches a key-shaped string, and the
        # exact key this machine is actually using -- which catches a leak
        # whatever shape it is in, including a JWT.
        import re as _re
        from backend import cloud as _cloud
        shaped = _re.compile(r"sb_secret_[A-Za-z0-9_-]{20,}")
        mine = (_cloud.load_config(os.path.join(APP, "GUI_logs"))
                .get("key") or "")
        leaked = []
        for rel in files:
            p = os.path.join(REPO, rel)
            if not os.path.isfile(p) or os.path.getsize(p) > 4_000_000:
                continue
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            if shaped.search(text) or (len(mine) > 20 and mine in text):
                leaked.append(rel)
        check("no secret key anywhere in the tracked files", not leaked,
              ", ".join(leaked[:3]))
        if len(mine) > 20:
            print("      (checked for the key this machine is using, and for "
                  "anything key-shaped)")

        print()
        print("What it does when started")
        logs = os.path.join(dest_app, "GUI_logs")
        env = dict(os.environ)
        env.pop("BARRY_SUPABASE_KEY", None)
        env.pop("BARRY_SUPABASE_URL", None)
        env["PYTHONPATH"] = dest_app

        probe = (
            "import sys, io, contextlib, json;"
            "sys.path.insert(0, r'%s');"
            "from backend import cloud;"
            "c = cloud.load_config(r'%s');"
            "print(json.dumps({'project': c['project'],"
            " 'needs_key': c['needs_key'], 'enabled': c['enabled'],"
            " 'key_in_repo': c['key_in_repo']}))" % (dest_app, logs)
        )
        res = subprocess.run([sys.executable, "-c", probe], env=env,
                             capture_output=True, text=True, timeout=120)
        import json as _json
        try:
            cfg = _json.loads(res.stdout.strip().splitlines()[-1])
        except Exception:                          # noqa: BLE001
            cfg = {}
            print("      probe said: %s%s"
                  % (res.stdout[-300:], res.stderr[-300:]))
        check("it reads the project from the tracked config",
              cfg.get("project"), str(cfg))
        check("it knows it is missing the key", cfg.get("needs_key") is True,
              str(cfg))
        check("so the sync is off until somebody supplies one",
              cfg.get("enabled") is False, str(cfg))
        check("and no key is sitting in the tracked config",
              cfg.get("key_in_repo") is False, str(cfg))

        print()
        print("And it works without one")
        boot = (
            "import sys, os;"
            "sys.path.insert(0, r'%s');"
            "os.chdir(r'%s');"
            "from backend import store, eventbank, curation, layers, mice;"
            "st = store.Store(r'%s');"
            "print('sessions', len(st.all_sessions()));"
            "print('bank', len(eventbank.EventBank(r'%s', st).summaries()));"
            "print('mice', len(mice.MouseBook(r'%s', st).all()))"
            % (dest_app, dest_app, logs, logs, logs)
        )
        res = subprocess.run([sys.executable, "-c", boot], env=env,
                             capture_output=True, text=True, timeout=300)
        got = dict(
            (l.split()[0], int(l.split()[1]))
            for l in res.stdout.splitlines() if len(l.split()) == 2
            and l.split()[1].isdigit())
        if not got:
            print("      %s%s" % (res.stdout[-400:], res.stderr[-400:]))
        check("the records open with no network and no key",
              got.get("sessions", 0) > 100, str(got))
        check("the event bank is readable", got.get("bank", 0) > 0, str(got))
        check("and the mice", got.get("mice", 0) > 0, str(got))

        print()
        print("The derived folders rebuild themselves")
        rebuild = (
            "import sys, os;"
            "sys.path.insert(0, r'%s');"
            "from backend import store, eventbank, mice, bankmirror;"
            "st = store.Store(r'%s');"
            "b = eventbank.EventBank(r'%s', st);"
            "m = mice.MouseBook(r'%s', st);"
            "print(bankmirror.BankMirror(r'%s', b, mice=m).rebuild())"
            % (dest_app, logs, logs, logs, dest_app)
        )
        res = subprocess.run([sys.executable, "-c", rebuild], env=env,
                             capture_output=True, text=True, timeout=300)
        made = os.path.join(dest_app, "Data Bank")
        check("the Data Bank folder appears", os.path.isdir(made),
              res.stdout[-200:] + res.stderr[-200:])
        check("with an index anyone can open",
              os.path.isfile(os.path.join(made, "_index.csv")))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d problem(s): %s" % (len(FAILED), "; ".join(FAILED)))
        return 1
    print("A clone starts, knows where to sync, asks for the key it does not "
          "have, and works without it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
