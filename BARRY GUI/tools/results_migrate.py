"""
results_migrate.py -- file the Results folder by what things are of.

Results/ grew one folder per convention anybody happened to use:

    KCNT1 m1609 s1 2026-07-15/...png      a session folder, spaces
    Panorama/KCNT1_m306_s1_..._panorama   the tool, underscores, flat
    ToolKit/bad-channels_all_*.csv        the tool, no recording at all
    Test Figures/PTEN m11 s10 ...         somebody's scratch, kept
    m41 s1 2024-11-26/...                 no project named

Every one of those is somebody filing sensibly under a different idea of
sensible, which is what happens when nothing decides. So:

    <Project>/m<mouse>/s<session> <date>/<tool>/<file>
    _unassigned/<tool>/<file>        when there is no recording to name
    _scratch/                        by-products; already handled, untouched

The same shape as Data Bank/, which bankmirror.py has used for the event bank
since it shipped. One filing idea in the app rather than two.

WHY IT GOES THROUGH Results.move()

A result's id is a hash of its path, so moving a file changes its id, and
anything holding the old one -- a storyboard slide, a run's output list, the
tags and star in its curation shard -- has to be repointed. And the old path
has to be tombstoned or the next sync downloads it straight back into the
folder you just cleared. That is the bug that turned six figures into twelve.
move() already does all of it; this only decides where things go.

WHAT IT WILL NOT DO

  * Touch _scratch. That is the by-product lane and it is already right.
  * Move anything it cannot name. A file with no project, mouse or session in
    its name and no run record saying one goes to _unassigned/<tool>, not into
    a guess.
  * Run without being asked. Dry run is the default and prints the whole plan.

    python tools/results_migrate.py             # say what would move
    python tools/results_migrate.py --write
    python tools/results_migrate.py --write --only Panorama
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import results as resultsmod, store as storemod  # noqa: E402

REPO_ROOT = os.path.dirname(APP)

# A result's kind -> the folder its tool files under. The run record's own
# `script` wins when there is one; this is for the files that have none.
TOOL_DIRS = {
    "panorama": "Panorama",
    "toolkit": "ToolKit",
    "deck": "Storyboards",
    "figure": "Figures",
    "file": "Figures",
}

# Folders that are already a tool's own and should keep their name when a
# file inside them moves under a recording.
KNOWN_TOOLS = ("Panorama", "ToolKit", "Storyboards", "Curation", "Layers",
               "Manifests", "Event bank", "Debug", "Figures")


def tool_of(rec):
    """Which tool made this, as a folder name."""
    script = (rec.get("script") or "").strip()
    if script:
        low = script.lower()
        for name in KNOWN_TOOLS:
            if name.lower() in low:
                return name
        if "figure" in low or "xplore" in low:
            return "Figures"
    # The *last* segment, not the first.
    #
    # Before this tool runs, the tool's own folder is at the top:
    # "Panorama/x.csv". After it has run once it is at the bottom:
    # "KCNT1/m306/s1 2026-02-24/Panorama/x.csv". Reading the first segment
    # got the answer right the first time and "KCNT1" the second, so a second
    # run proposed moving everything it had just filed into a Figures folder.
    # A migration that is not a no-op the second time is a migration nobody
    # can safely re-run.
    parts = [p for p in (rec.get("folder") or "").split("/") if p]
    if parts and parts[-1] in KNOWN_TOOLS:
        return parts[-1]
    if parts and parts[0] in KNOWN_TOOLS:
        return parts[0]
    return TOOL_DIRS.get(rec.get("kind") or "", "Figures")


def destination(rec):
    """Where this result belongs, or None to leave it exactly where it is."""
    rel = (rec.get("rel") or "")
    if rel.split("/")[0] == resultsmod.SCRATCH_DIR:
        return None                       # the by-product lane is already right

    tool = tool_of(rec)
    proj = rec.get("project")
    mouse = rec.get("mouse")
    sess = rec.get("session_no")
    date = rec.get("recorded_on")

    if mouse is None or sess is None:
        # Nothing names a recording.
        #
        # A lab-wide bad-channel export or the whole event bank as one CSV
        # belongs to no animal by nature, not by omission -- and if it is
        # already sitting in its tool's own folder then it is filed correctly
        # and "_unassigned/ToolKit" would be a worse name for the same place.
        # So only the ones loose at the top level, or in somebody's ad-hoc
        # folder, get moved.
        top = (rec.get("folder") or "").split("/")[0]
        if top in KNOWN_TOOLS:
            return None
        return "_unassigned/" + tool

    room = "s%s" % sess + (" " + date if date else "")
    return "/".join([proj or "Unfiled", "m%s" % mouse, room, tool])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="actually move them; without this it only reports")
    ap.add_argument("--only", metavar="TEXT",
                    help="only results whose current path contains this")
    args = ap.parse_args()

    logs = os.path.join(APP, "GUI_logs")
    outputs = os.path.join(APP, "Results")
    store = storemod.Store(logs, auto_stage=False)
    cat = resultsmod.Results(store, outputs, REPO_ROOT)

    moves = []
    staying = 0
    for rec in cat.catalog(refresh=True):
        rel = rec.get("rel") or ""
        if args.only and args.only.lower() not in rel.lower():
            continue
        dest = destination(rec)
        if dest is None:
            staying += 1
            continue
        if (rec.get("folder") or "") == dest:
            staying += 1
            continue
        moves.append((rec, dest))

    if not moves:
        print("Nothing to move: %d result(s), all already filed." % staying)
        return 0

    by_dest = {}
    for rec, dest in moves:
        by_dest.setdefault(dest, []).append(rec.get("rel"))

    named = sum(1 for _r, d in moves if not d.startswith("_unassigned"))
    print("%d result(s) would move, %d already in place.\n"
          % (len(moves), staying))
    print("  %d into a recording's own folder, %d into _unassigned because "
          "nothing\n  names a recording for them.\n"
          % (named, len(moves) - named))
    for dest in sorted(by_dest):
        rows = by_dest[dest]
        print("  -> %s   (%d)" % (dest, len(rows)))
        for rel in rows[:3]:
            print("       %s" % rel)
        if len(rows) > 3:
            print("       ... and %d more" % (len(rows) - 3))

    if not args.write:
        print("\nNothing moved. Re-run with --write to do it.")
        print("Every move goes through Results.move(), so slides, run outputs "
              "and\ncuration follow and the old path is tombstoned.")
        return 0

    moved = failed = carried = 0
    for rec, dest in moves:
        src = rec.get("path")
        try:
            cat.move(rec["id"], dest, store=store)
            moved += 1
        except Exception as exc:                        # noqa: BLE001
            failed += 1
            print("  could not move %s: %s" % (rec.get("rel"), exc))
            continue
        carried += _carry_sidecars(src, outputs, dest)
    print("\nMoved %d, failed %d." % (moved, failed))
    if carried:
        print("Carried %d sidecar(s) along -- the _params.json beside a "
              "figure is\nnot a result in its own right, and is useless "
              "anywhere else." % carried)
    return 1 if failed else 0


def _carry_sidecars(src, outputs, dest):
    """Move the files that belong to a result but are not results themselves.

    Panorama writes `<stem>_params.json` beside its figure: every setting that
    produced it, which is the most valuable file of the five and the only one
    the catalogue cannot see, because .json is not a result extension. Leaving
    it behind splits a piece of work in half and strands the half that says
    what the other half means.

    Matched on the stem, so `x.png` carries `x_params.json` and `x_psd.csv`
    but not `x2.png`.
    """
    folder = os.path.dirname(src or "")
    stem = os.path.splitext(os.path.basename(src or ""))[0]
    if not folder or not stem or not os.path.isdir(folder):
        return 0
    dest_dir = os.path.join(outputs, *dest.split("/"))
    os.makedirs(dest_dir, exist_ok=True)
    n = 0
    for name in os.listdir(folder):
        if name == os.path.basename(src):
            continue
        base, ext = os.path.splitext(name)
        if ext.lower() in resultsmod.RESULT_EXTS:
            continue                      # a result of its own; it moves itself
        if base == stem or base.startswith(stem + "_"):
            try:
                os.replace(os.path.join(folder, name),
                           os.path.join(dest_dir, name))
                n += 1
            except OSError:
                pass
    return n


if __name__ == "__main__":
    raise SystemExit(main())
