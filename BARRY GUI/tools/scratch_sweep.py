"""
scratch_sweep.py -- Move the by-products out of Results/ and into _scratch/.

Results/ had 197 files in it. About 120 were by-products of running the tests:

    45  rebuild harness_*.png        the figure the rebuild harness renders
                                     to prove that rendering works
    49  Debug/debug-report-*.txt     sent to somebody once, read once
    30  Storyboards/arrow harness*   23 of them byte-identical to each other

Which left roughly a dozen actual results, filed among them. A folder that is
five percent results is not a folder anybody reads, and every one of those
files was committed to a repository that already carries 1.5 GB of history.

Going forward this cannot recur: the harnesses now pass `lane: 'scratch'` and
`/api/debug/report` is always scratch, so by-products land in Results/_scratch
which git ignores and the catalogue skips. This tool is for the backlog.

WHY IT GOES THROUGH Results.move() AND NOT os.rename()

Because moving a result is not moving a file. A result's id is a hash of its
path, so the id changes when the path does, and anything holding the old one
-- a storyboard slide, a run's output list, the tags and star in its curation
shard -- has to be repointed. And the old path has to be *tombstoned*, or the
next sync finds a row whose file is missing locally and downloads it straight
back into the folder you just cleared. That is not hypothetical: it is the
documented bug where filing six figures turned them into twelve.

move() already does all of that. This tool only decides what to feed it.

WHAT IT WILL NOT TOUCH WITHOUT BEING ASKED

ToolKit/bad-channels_all_*.csv -- there are 54 of them and they look like
harness output, but "export every bad channel in the lab" is also a thing a
person does, and the two are indistinguishable by name. Pass --toolkit if you
have looked and want them swept too.

    python tools/scratch_sweep.py                # say what would move
    python tools/scratch_sweep.py --write
    python tools/scratch_sweep.py --write --toolkit
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import results as resultsmod, store as storemod  # noqa: E402

REPO_ROOT = os.path.dirname(APP)

# Matched against the path relative to Results/, forward-slashed and lowercased.
# Each rule says where the file should end up, so _scratch keeps the shape of
# the folder it came from rather than becoming one flat heap of its own.
RULES = [
    ("*harness*",                    "_scratch/harness"),
    ("debug/debug-report-*.txt",     "_scratch/Debug"),
]

TOOLKIT_RULES = [
    ("toolkit/bad-channels_*.csv",   "_scratch/ToolKit"),
]


def destination(rel, rules):
    """Where this file belongs, or None to leave it alone."""
    low = rel.lower()
    if low.startswith("_scratch/"):
        return None                     # already swept
    for pattern, dest in rules:
        if fnmatch.fnmatch(low, pattern) or fnmatch.fnmatch(
                os.path.basename(low), pattern):
            return dest
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="actually move them; without this it only reports")
    ap.add_argument("--toolkit", action="store_true",
                    help="also sweep ToolKit/bad-channels_*.csv")
    args = ap.parse_args()

    rules = RULES + (TOOLKIT_RULES if args.toolkit else [])

    logs = os.path.join(APP, "GUI_logs")
    outputs = os.path.join(APP, "Results")
    store = storemod.Store(logs, auto_stage=False)
    cat = resultsmod.Results(store, outputs, REPO_ROOT)

    # Two kinds, and they cannot be moved the same way.
    #
    # A *cataloged* file is a result: it has an id, possibly a star and tags,
    # and possibly a storyboard slide pointing at it. It goes through move().
    #
    # Everything else the catalogue never saw, because it only indexes images,
    # PDFs and tables -- which is why all forty-nine debug reports are .txt and
    # none of them appear above. Nothing points at those, so a plain rename is
    # both safe and the only option.
    items = cat.catalog(refresh=True)
    known = {}
    picked = []
    for rec in items:
        rel = rec.get("rel") or ""
        known[rel.lower()] = True
        dest = destination(rel, rules)
        if dest:
            picked.append((rec, dest))

    loose = []
    for root, dirs, files in os.walk(outputs):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d != resultsmod.SCRATCH_DIR]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, outputs).replace("\\", "/")
            if rel.lower() in known:
                continue
            dest = destination(rel, rules)
            if dest:
                loose.append((full, rel, dest))

    if not picked and not loose:
        print("Nothing to sweep: %d result(s) and none of them by-products."
              % len(items))
        return 0

    by_dest = {}
    for rec, dest in picked:
        by_dest.setdefault(dest, []).append(rec.get("rel"))
    for _full, rel, dest in loose:
        by_dest.setdefault(dest, []).append(rel)

    total_bytes = sum((r.get("bytes") or 0) for r, _ in picked)
    for full, _rel, _dest in loose:
        try:
            total_bytes += os.path.getsize(full)
        except OSError:
            pass
    print("%d by-product file(s) in Results/ (%.1f MB) -- %d cataloged, "
          "%d loose:"
          % (len(picked) + len(loose), total_bytes / 1e6,
             len(picked), len(loose)))
    for dest in sorted(by_dest):
        rows = by_dest[dest]
        print("\n  -> %s   (%d)" % (dest, len(rows)))
        for rel in rows[:4]:
            print("       %s" % rel)
        if len(rows) > 4:
            print("       ... and %d more" % (len(rows) - 4))

    if not args.write:
        print("\nNothing moved. Re-run with --write to do it.")
        if not args.toolkit:
            print("ToolKit/bad-channels_*.csv were left out; --toolkit adds "
                  "them.")
        return 0

    moved = failed = 0
    for rec, dest in picked:
        try:
            cat.move(rec["id"], dest, store=store)
            moved += 1
        except Exception as exc:                        # noqa: BLE001
            failed += 1
            print("  could not move %s: %s" % (rec.get("rel"), exc))

    for full, rel, dest in loose:
        try:
            dest_dir = os.path.join(outputs, *dest.split("/"))
            os.makedirs(dest_dir, exist_ok=True)
            target = os.path.join(dest_dir, os.path.basename(full))
            stem, ext = os.path.splitext(target)
            n = 2
            while os.path.exists(target):
                target = "%s_%d%s" % (stem, n, ext)
                n += 1
            os.replace(full, target)
            moved += 1
        except Exception as exc:                        # noqa: BLE001
            failed += 1
            print("  could not move %s: %s" % (rel, exc))

    print("\nMoved %d, failed %d." % (moved, failed))
    print("\nThey are still on disk under Results/_scratch, and git now "
          "ignores that folder. To drop them from the repository as well:")
    print('    git rm -r --cached "BARRY GUI/Results/_scratch"')
    print('    git commit -m "Sweep harness and debug output out of Results"')
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
