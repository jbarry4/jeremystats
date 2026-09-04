"""
cloud_migrate.py -- Move everything BARRY knows into Supabase.

Sessions, mice, the event bank, curation decisions, layer sheets, results and
their filing, storyboards, presets, and the whole history -- runs, activity,
errors. Then the figures themselves into the storage bucket.

Nothing is deleted locally. The files stay as the offline buffer, and BARRY
keeps working with no network; this is the shared copy.

Safe to run twice. Every write is an upsert and the database drops anything
older than what it already has, so a re-run after a failure picks up where it
left off rather than duplicating or clobbering.

    python tools/cloud_migrate.py --dry-run      # say what would go
    python tools/cloud_migrate.py --write
    python tools/cloud_migrate.py --write --no-files    # skip the uploads
    python tools/cloud_migrate.py --write --no-history  # skip runs/logs
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import (cloud, cloudsync, curation, eventbank, layers,  # noqa
                     mice, results, store)

LOGS = os.path.join(APP, "GUI_logs")


def build(logs):
    st = store.Store(logs, auto_stage=False)
    out = os.path.join(APP, "Results")
    return cloudsync.Sync(
        logs, st,
        bank=eventbank.EventBank(logs, st),
        curate=curation.Curation(logs, st),
        layers=layers.Layers(logs, st),
        mice=mice.MouseBook(logs, st),
        results=results.Results(st, out, os.path.dirname(APP)),
        repo_root=os.path.dirname(APP))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=LOGS)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-files", action="store_true",
                    help="do not upload the figures")
    ap.add_argument("--no-history", action="store_true",
                    help="do not send runs, activity or errors")
    ap.add_argument("--force-files", action="store_true",
                    help="re-upload every figure, even unchanged ones")
    ap.add_argument("--incremental", action="store_true",
                    help="only send what has changed since the last push")
    args = ap.parse_args()

    sync = build(args.logs)
    if not sync.cloud.configured:
        print("No Supabase project configured.")
        print("    python tools/cloud_setup.py --url <project> --key <secret>")
        return 2

    print("project   %s" % sync.cloud.cfg.get("project"))
    print("machine   %s" % sync.machine)
    print("mode      %s" % ("WRITE" if args.write else "dry run"))
    print()

    if args.write:
        p = sync.cloud.ping()
        if not p["reachable"]:
            print("Cannot reach the project: %s" % p.get("error"))
            return 2
        if not p["schema"]:
            print("The schema is not there yet. In the Supabase SQL editor, "
                  "run supabase/01_schema.sql, then 02_rls.sql, then "
                  "03_storage.sql.")
            return 2

    # ---- the tables ----------------------------------------------------
    t0 = time.time()
    print("%-22s %8s" % ("table", "rows"))
    print("%-22s %8s" % ("-" * 22, "-" * 8))

    def progress(table, n):
        print("%-22s %8d" % (table, n))

    # A migration is the one push that should send everything, regardless of
    # what a previous run thinks it already sent.
    res = sync.push(include_history=not args.no_history,
                    on_progress=progress, dry_run=not args.write,
                    full=not args.incremental)
    print()
    print("%d row(s) %s in %.1fs"
          % (res["sent"], "sent" if args.write else "would be sent",
             time.time() - t0))

    # ---- the files -----------------------------------------------------
    if not args.no_files:
        print()
        if args.write:
            print("Uploading figures...")
            up = sync.upload_results(
                force=args.force_files,
                on_progress=lambda rel, n: print("  %3d  %s" % (n, rel)))
            print("  %d uploaded, %d already there"
                  % (up["uploaded"], up["skipped"]))
            for f in up["failed"]:
                print("  FAILED %s: %s" % (f["rel"], f["error"]))
        else:
            n = len([r for r in sync.results.catalog()
                     if r.get("path") and os.path.isfile(r["path"])])
            print("%d figure(s) would be uploaded to the 'results' bucket" % n)

    if not args.write:
        print()
        print("Nothing sent. Re-run with --write.")
        return 0

    # ---- what is up there now ------------------------------------------
    print()
    print("On the server now:")
    p = sync.cloud.ping()
    for t, n in sorted((p.get("counts") or {}).items()):
        print("  %-18s %s" % (t, n))
    print()
    print("Background sync is %s. Change it with:"
          % ("on" if sync.cloud.cfg.get("auto") else "off"))
    print("    python tools/cloud_setup.py --auto on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
