"""check_ids_dewey.py -- the DEWEY rule did not touch anybody else's identity.

`ids.identify()` is what decides a recording's `key`, and the key is the
session shard's file name. Widen one of its regexes by accident and a PTEN
recording gets a different key, files itself under a new name, and comes loose
from the curation, bad channels and banked events attached to the old one. The
damage is silent: nothing errors, there is simply a second row.

HOW THIS CHECKS IT

Not against what is stored. The stored key was written by whatever the rule
was on the day, from whatever start time that machine had -- some records hold
a header time in UTC and were keyed from a local folder name, so replaying
them against their own stored start disagrees for reasons that have nothing to
do with this change. Chasing that is how a check ends up measuring itself.

Instead: run `identify()` twice over every path this lab has ever recorded,
once with the DEWEY rule switched off and once with it on, and diff the two.
The rule is correct exactly when the only paths that answer differently are
the ones it is supposed to claim.

    python tools\\check_ids_dewey.py            # summary
    python tools\\check_ids_dewey.py --verbose  # every DEWEY path, as read
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import ids  # noqa: E402

SESSIONS = os.path.join(APP, "GUI_logs", "sessions")
FIELDS = ("mouse", "session", "key", "loose_key", "group")


def every_path():
    """Every distinct path in the registry, with the start stored beside it."""
    seen = {}
    for f in sorted(glob.glob(os.path.join(SESSIONS, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError) as e:
            print("  ! could not read %s: %s" % (os.path.basename(f), e))
            continue
        for path in (rec.get("paths") or []):
            seen.setdefault(str(path), (rec.get("start"),
                                        os.path.basename(f)))
    return seen


def read(path, start, dewey_on):
    """identify() with the DEWEY rule on or off, so the two can be diffed."""
    real = ids.dewey_parts
    if not dewey_on:
        ids.dewey_parts = lambda parts: None
    try:
        got = ids.identify(path, header_time=start)
    finally:
        ids.dewey_parts = real
    return got


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    paths = every_path()

    same = 0
    claimed = []     # DEWEY-shaped, and the rule changed the answer
    stolen = []      # not DEWEY-shaped, and the answer changed anyway
    missed = []      # DEWEY-shaped, but the rule did not name it

    for path, (start, shard) in sorted(paths.items()):
        before = read(path, start, dewey_on=False)
        after = read(path, start, dewey_on=True)
        shaped = bool(ids.dewey_parts(
            [p for p in re.split(r"[\\/]+", path) if p]))
        changed = any(before.get(k) != after.get(k) for k in FIELDS)

        if shaped and changed:
            claimed.append((path, after))
        elif shaped and not changed:
            missed.append((path, after))
        elif changed:
            stolen.append((path, shard, before, after))
        else:
            same += 1

    print("%d distinct paths across %d shards"
          % (len(paths), len(glob.glob(os.path.join(SESSIONS, "*.json")))))
    print("  untouched      : %d" % same)
    print("  DEWEY, named   : %d" % len(claimed))
    print("  DEWEY, missed  : %d" % len(missed))
    print("  NOT DEWEY, but changed anyway : %d" % len(stolen))

    if verbose and claimed:
        print("\nDEWEY paths, as the new rule reads them:")
        for path, got in claimed:
            print("  m%-3s s%-3s %-9s %-4s  %s"
                  % (got.get("mouse"), got.get("session"),
                     "%s%s%s" % (got.get("phase") or "",
                                 got.get("phase_n") or "",
                                 got.get("repeat") or ""),
                     got.get("run") or "-", path))

    bad = False
    if missed:
        bad = True
        print("\nFAIL -- the rule recognises the shape but named nothing:")
        for path, _ in missed[:20]:
            print("   %s" % path)

    if stolen:
        bad = True
        print("\nFAIL -- these are not DEWEY and would be re-keyed:\n")
        for path, shard, before, after in stolen[:40]:
            print("  %s" % shard)
            print("     path  %s" % path)
            for k in FIELDS:
                if before.get(k) != after.get(k):
                    print("     %-10s %r -> %r" % (k, before.get(k),
                                                   after.get(k)))
        if len(stolen) > 40:
            print("  ... and %d more" % (len(stolen) - 40))

    if bad:
        return 1
    print("\nOK -- the DEWEY rule claims only DEWEY paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
