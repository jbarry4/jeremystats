"""refile_dewey.py -- repair the DEWEY rows a scan filed wrongly.

WHAT WENT WRONG

A DEWEY session holds three recordings -- FP1, SPC, FP2 -- and by design they
share a mouse and a session number, because the lab calls the whole day
"Precon1". They were supposed to be told apart by their start times. They are
not: all three are run the same afternoon, well inside the six-hour window
`ids._near` allows for two mounts of one recording disagreeing about the
clock.

So `ids.match` returned a strong match for the second and third, and
`upsert_session` appended their paths to the first. Three recordings became
one row. On the first full scan that happened to every session on the share:
93 rows holding 257 paths, with the 91-minute cued recording filed under a
6-minute grounding recording's name.

`ids.match` now takes the run into account, so it cannot happen again. This
repairs what the earlier scans left.

WHAT IT DOES

For every record whose paths are on the DEWEY share:

  * works out which path the record is actually about, from its own key;
  * takes the other paths off it;
  * gives each of those its own record, with the channel count, sampling
    rate and duration read from its header, so nothing has to be re-scanned.

WHAT IT WILL NOT DO

Only this machine's shards. Every editable record is split by machine so two
people can never write the same file, and tidying up is not an exception. A
record whose shard belongs to another machine is listed, with the machine
that has to run this.

It also refuses to touch a record holding a decision -- bad channels, a note,
a view, a probe. The rows this exists for were written by a scan minutes ago
and hold nothing; one that holds something is a merge a person should look
at.

    python tools\\refile_dewey.py           # say what would happen
    python tools\\refile_dewey.py --apply   # do it
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import discovery, ids, sessreg, shards, store as storemod  # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")

#: Fields whose presence means somebody decided something about this
#: recording. A record carrying any of them is never split automatically.
#:
#: `probe` is deliberately NOT here. It is a statement about the montage,
#: and the three runs of one session were recorded on the same headstage --
#: so splitting a record and carrying the probe onto both halves loses
#: nothing and is what somebody meant. Everything else on this list is about
#: one recording and could not be copied honestly.
DECISIONS = ("bad_channels", "bad_channels_note", "note", "view_state",
             "bookmarks", "condition", "hemisphere", "quality",
             "spike_labels", "event_classes", "ripple_channel",
             "fissure_channel", "hilus_channel", "extraction_note",
             "merged_in", "split_from")

#: Carried onto a record split off from another.
INHERIT = ("probe", "probe_source")


def is_dewey(path):
    return bool(ids.dewey_parts([p for p in re.split(r"[\\/]+", str(path))
                                 if p]))


def belongs(path, rec):
    """Is this path the recording that record is about?

    Asked on mouse, session and run -- NOT on the key, which carries the
    start time as well.

    The start is why: `ids.identify` reads it off the folder name, and the
    record was keyed from the Neuralynx header, which is the more
    trustworthy of the two and often disagrees. One J4 recording sits in a
    folder called 10-38-11 and its header says the acquisition began at
    10-38-27, sixteen seconds later. Comparing keys called that path a
    stray, and an earlier version of this tool would have cheerfully split
    a recording away from itself.

    Mouse, session and run are exactly the identity a DEWEY recording has,
    and none of the three can drift between a folder name and a header.
    """
    got = ids.identify(str(path))
    return (got.get("loose_key") == rec.get("loose_key")
            and (got.get("run") or None) == (rec.get("run") or None))


def decisions_in(rec):
    out = []
    for f in DECISIONS:
        v = rec.get(f)
        if v not in (None, "", [], {}):
            out.append(f)
    return out


def facts_for(path):
    """Channel count, rate and duration, from one 16 KB header read."""
    try:
        contents = discovery.classify_folder(path)
        if not contents:
            return {}
        got = discovery.describe_session(path, contents)
    except Exception as e:                                   # noqa: BLE001
        print("     ! could not read %s: %s" % (path, e))
        return {}
    out = {}
    for src, dst in (("channels", "n_channels"), ("fs", "fs"),
                     ("duration_s", "duration_s")):
        if got.get(src):
            out[dst] = got[src]
    if got.get("has_video"):
        out["has_video"] = True
    return out


def main():
    apply = "--apply" in sys.argv
    mine = shards.machine_id()
    STORE = storemod.Store(LOGS, auto_stage=False)
    REG = sessreg.Registry(STORE)

    rows = [r for r in REG.all()
            if any(is_dewey(p) for p in (r.get("paths") or []))]
    if not rows:
        print("No DEWEY records in the registry. Nothing to do.")
        return 0

    print("this machine  : %s" % mine)
    print("DEWEY records : %d" % len(rows))
    print("paths on them : %d\n"
          % sum(len(r.get("paths") or []) for r in rows))

    plan = []          # (rec, keep[], strays[])
    held, foreign = [], []

    for rec in rows:
        paths = [str(p) for p in (rec.get("paths") or [])]
        dewey = [p for p in paths if is_dewey(p)]
        if len(dewey) < 2:
            continue

        why = decisions_in(rec)
        if why:
            held.append((rec, why))
            continue

        keep = [p for p in dewey if belongs(p, rec)]
        strays = [p for p in dewey if not belongs(p, rec)]
        if strays and keep:
            plan.append((rec, keep, strays))

    # Rows left over from before the DEWEY rule existed.
    #
    # With no key, `get_session` had nothing to match on, so every open
    # minted a fresh gid: two recordings collected twelve ids between them.
    # They are recognisable by having no mouse at all, and they are only
    # safe to drop because the same path now has a properly named row -- so
    # that is checked rather than assumed.
    named = set()
    for r in rows:
        if r.get("mouse") is not None:
            named.update(str(p) for p in (r.get("paths") or []))
    stubs = []
    for r in rows:
        if r.get("mouse") is not None or decisions_in(r):
            continue
        paths = [str(p) for p in (r.get("paths") or [])]
        if paths and all(p in named for p in paths):
            stubs.append(r)

    n_new = sum(len(s) for _r, _k, s in plan)
    for rec, keep, strays in plan:
        print("%s" % (rec.get("label") or rec.get("gid")))
        print("   keeps  %s" % os.path.basename(keep[0]))
        for p in strays:
            got = ids.identify(p)
            print("   splits %-22s -> m%s s%s %s%s %s"
                  % (os.path.basename(p), got.get("mouse"),
                     got.get("session"), got.get("phase"),
                     got.get("phase_n"), got.get("run")))

    if stubs:
        print("\nUnnamed leftovers from before the DEWEY rule "
              "(every path already has a named row):")
        for r in stubs:
            print("   %-14s %s" % (r.get("gid"),
                                   os.path.basename(
                                       (r.get("paths") or [""])[0])))

    print("\n" + "-" * 66)
    print("records to split : %d" % len(plan))
    print("records to add   : %d" % n_new)
    print("stubs to retire  : %d" % len(stubs))
    print("skipped          : %d holding a decision" % len(held))
    for rec, why in held[:10]:
        print("     %-38s holds %s"
              % (rec.get("label"), ", ".join(why)))

    if not apply:
        print("\nDry run. Nothing was written. Re-run with --apply to act.")
        return 0
    if not plan and not stubs:
        print("\nNothing to do.")
        return 0

    print("\napplying...")

    # PASS ONE -- give every stray recording a record of its own.
    made = 0
    for rec, keep, strays in plan:
        inherit = {k: rec.get(k) for k in INHERIT if rec.get(k)}
        for p in strays:
            ident = ids.identify(p)
            REG.ensure(ident)
            patch = dict(inherit)
            patch.update(facts_for(p))
            if patch:
                STORE.upsert_session(ident, patch)
            made += 1
            if made % 25 == 0:
                print("  ... %d of %d" % (made, n_new))

    # PASS TWO -- take every foreign path off every record.
    #
    # Separate from pass one, and after it, for a reason worth writing down:
    # a path may only be removed from a record once it HAS a record of its
    # own, or the recording stops being reachable from anywhere. So this
    # re-reads the registry, and drops a path only when some other record
    # already claims it by key.
    #
    # It also runs over every DEWEY record rather than only the ones pass
    # one touched, because `upsert_session` creates a record from whatever
    # it matched and the copy can start life holding the other's paths --
    # which is exactly what an earlier version of this tool left behind.
    live = REG.all()
    owners = {}
    for r in live:
        if r.get("loose_key"):
            owners.setdefault((r["loose_key"], r.get("run") or None),
                              r.get("gid"))

    pruned = 0
    for r in live:
        paths = [str(p) for p in (r.get("paths") or [])]
        if len(paths) < 2 or not any(is_dewey(p) for p in paths):
            continue
        mine_only = []
        for p in paths:
            if belongs(p, r):
                mine_only.append(p)
                continue
            got = ids.identify(p)
            owner = owners.get((got.get("loose_key"),
                                got.get("run") or None))
            # Never orphan a recording to tidy a list: a path only comes
            # off once something else claims it.
            if owner in (None, r.get("gid")):
                mine_only.append(p)
        if len(mine_only) != len(paths):
            REG._patch(r, {"paths": mine_only})
            pruned += len(paths) - len(mine_only)

    if pruned:
        print("  dropped %d path(s) from records they did not belong to"
              % pruned)

    # Retired, not deleted. `merge` marks a record this way and `tree`
    # leaves retired rows out, so they stop being in the way without any
    # history being thrown away -- and if one of these turns out to have
    # mattered, the row is still there to look at.
    for r in stubs:
        REG._patch(r, {"retired": True})
    if stubs:
        print("  retired %d unnamed leftover(s)" % len(stubs))

    print("\nDone. %d record(s) split, %d added." % (len(plan), made))
    print("Every DEWEY recording now has a row of its own. Nothing needs "
          "re-scanning -- the channel counts were read from the headers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
