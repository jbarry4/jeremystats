"""
cloud_setup.py -- Point BARRY at a Supabase project, and check it works.

The key never goes in the repo. It is written to GUI_logs/.cloud.json, which
.gitignore covers, and this refuses to write anywhere git can see. If a key
does get committed anyway, rotate it in the Supabase dashboard -- that is the
only real fix and it takes a minute.

    python tools/cloud_setup.py --url svyymanowlfoyblinnny --key sb_secret_...
    python tools/cloud_setup.py --check
    python tools/cloud_setup.py --auto off
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import cloud  # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")


def warn_if_public():
    """Say so if this repo is readable by anyone.

    Worth checking rather than assuming: what is in GUI_logs is unpublished
    recording data, and "our git is private" is easy to believe and easy to
    be wrong about.
    """
    import json as _json
    import re as _re
    import urllib.request as _u
    try:
        remote = subprocess.run(["git", "remote", "get-url", "origin"],
                                cwd=os.path.dirname(APP), capture_output=True,
                                text=True, timeout=10).stdout.strip()
        m = _re.search(r"github\.com[:/]+([^/]+)/([^/.]+)", remote)
        if not m:
            return
        req = _u.Request("https://api.github.com/repos/%s/%s"
                         % (m.group(1), m.group(2)),
                         headers={"User-Agent": "barry",
                                  "Accept": "application/vnd.github+json"})
        with _u.urlopen(req, timeout=15) as r:
            info = _json.load(r)
        if info.get("private") is False:
            print()
            print("!! %s is PUBLIC." % info.get("full_name"))
            print("   Anyone can read GUI_logs -- recordings, mouse ids,")
            print("   bad channels, the paths on your drives, and the email")
            print("   on every record. The key is not in there and will not")
            print("   be, but the data is.")
            print("   Settings -> General -> Change visibility -> Private.")
    except Exception:                              # noqa: BLE001
        pass          # offline, or not a GitHub remote: not worth a fuss


def git_would_see(path):
    """Is this file tracked, or would git add it? Refuse if so."""
    repo = os.path.dirname(APP)
    try:
        res = subprocess.run(["git", "check-ignore", "-q", path],
                             cwd=repo, capture_output=True, timeout=10)
        return res.returncode != 0
    except Exception:              # noqa: BLE001
        return True                # assume the worst


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="project id, or the full https:// URL")
    ap.add_argument("--key", help="the SECRET key (sb_secret_...)")
    ap.add_argument("--auto", choices=["on", "off"],
                    help="sync in the background while BARRY runs")
    ap.add_argument("--interval", type=int,
                    help="seconds between background syncs")
    ap.add_argument("--check", action="store_true",
                    help="just say whether it works")
    ap.add_argument("--logs", default=LOGS)
    args = ap.parse_args()

    # Which project and how often go in the tracked file, so a clone knows
    # where to sync without being told twice. The key goes in the gitignored
    # one, and nowhere else.
    shared, local = {}, {}
    if args.url:
        shared["url"] = (args.url if args.url.startswith("http")
                         else "https://%s.supabase.co" % args.url)
        shared["project"] = args.url.replace("https://", "").split(".")[0]
    if args.auto:
        shared["auto"] = (args.auto == "on")
    if args.interval:
        shared["interval"] = args.interval
    if args.key:
        ok, why = cloud.looks_like_a_key(args.key)
        if not ok:
            print(why)
            return 2
        local["key"] = args.key

    if shared:
        cloud.save_shared_config(args.logs, **shared)
        print("Wrote %s  (tracked, no key in it)"
              % cloud.shared_config_path(args.logs))
    if local:
        target = cloud.config_path(args.logs)
        if git_would_see(target):
            print("REFUSING to write the key to %s -- git is not ignoring it."
                  % target)
            print()
            print("Add this to BARRY GUI/.gitignore first:")
            print("    GUI_logs/.cloud.json")
            return 2
        cloud.save_config(args.logs, **local)
        print("Wrote %s  (this machine only; git ignores it)" % target)
    if shared or local:
        print()

    c = cloud.Cloud(args.logs)
    cfg = c.cfg
    print("project   %s" % (cfg.get("project") or "-- not set --"))
    print("url       %s" % (cfg.get("url") or "-- not set --"))
    print("key       %s" % ("set (" + cfg["key"][:12] + "...)"
                            if cfg.get("key") else "-- not set --"))
    print("auto      %s every %ss" % ("on" if cfg.get("auto") else "off",
                                      cfg.get("interval")))
    print("machine   %s" % c.machine)
    if cfg.get("key_in_repo"):
        print()
        print("!! The tracked cloud.json contains a key. It is being ignored,")
        print("   but git has it -- rotate that key in the Supabase dashboard")
        print("   and set the new one with --key.")
    warn_if_public()
    print()

    if not c.configured:
        print("Not configured yet. Run:")
        print("    python tools/cloud_setup.py --url <project id> "
              "--key <secret key>")
        return 1

    print("Checking...")
    p = c.ping()
    print("  reachable   %s" % p["reachable"])
    print("  schema      %s" % p["schema"])
    if p.get("error"):
        print("  problem     %s" % p["error"])
    for t, n in sorted((p.get("counts") or {}).items()):
        print("    %-18s %s row(s)" % (t, n))

    if p["reachable"] and not p["schema"]:
        print()
        print("Run the SQL first, in the Supabase SQL editor, in this order:")
        print("    supabase/01_schema.sql")
        print("    supabase/02_rls.sql")
        print("    supabase/03_storage.sql")
        return 1
    if not p["reachable"]:
        return 1

    print()
    print("Good. Migrate what is here with:")
    print("    python tools/cloud_migrate.py --dry-run")
    print("    python tools/cloud_migrate.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
