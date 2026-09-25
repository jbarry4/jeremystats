"""rebuild_dewey.py -- make the DEWEY rows match the share, folder for folder.

The registry got into a state no amount of nudging was going to fix: one
recording holding three folders, two records claiming the same folder, and
thirty-five folders with no record at all. All of it came from one cause --
`ids.match` could not tell the three runs of a session apart, so scans and
repairs kept merging them back together.

`ids.match` knows about runs and takes now, so the matching is right going
forward. This rebuilds what the earlier passes left, and it does it the only
way that is actually verifiable: walk the share, and make the registry say
exactly one record per recording folder.

WHAT IT PRESERVES

Everything anybody decided. A record that already covers a folder keeps its
gid, its probe, its bad channels, its note -- the rebuild only fixes which
folders a record claims. A record covering a folder that no longer exists is
retired rather than deleted.

WHAT IT WILL NOT DO

Only this machine's shards, as ever.

    python tools\\rebuild_dewey.py           # say what would happen
    python tools\\rebuild_dewey.py --apply   # do it
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
SHARE = r"E:\Joe Multisite 2026 data"


def is_dewey(p):
    return bool(ids.dewey_parts([x for x in re.split(r"[\\/]+", str(p)) if x]))


def walk(root):
    """Every folder holding CSC files. A recording is a leaf."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        if any(f.lower().startswith("csc") and f.lower().endswith(".ncs")
               for f in filenames):
            out.append(dirpath)
            dirnames[:] = []
    return sorted(out)


def facts_for(path):
    try:
        contents = discovery.classify_folder(path)
        if not contents:
            return {}
        got = discovery.describe_session(path, contents)
    except Exception:                                        # noqa: BLE001
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
    root = SHARE
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            root = a
    if not os.path.isdir(root):
        print("Not a folder: %s" % root)
        return 2

    mine = shards.machine_id()
    STORE = storemod.Store(LOGS, auto_stage=False)
    REG = sessreg.Registry(STORE)

    disk = walk(root)
    print("this machine : %s" % mine)
    print("share        : %s" % root)
    print("recordings   : %d\n" % len(disk))

    rows = [r for r in REG.all()
            if not r.get("retired")
            and any(is_dewey(p) for p in (r.get("paths") or []))]

    # Which record, if any, already covers each folder -- by mouse, session
    # and run, which is the identity, plus the take. First one wins, and the
    # rest of that folder's claimants have it taken off them.
    def sig(ident):
        return (ident.get("loose_key"), ident.get("run") or None)

    holders = defaultdict(list)
    for r in rows:
        for p in (r.get("paths") or []):
            holders[os.path.normcase(str(p))].append(r)

    keep, orphans, retire = {}, [], []
    for p in disk:
        got = holders.get(os.path.normcase(p)) or []
        exact = [r for r in got
                 if sig(ids.identify(p)) == (r.get("loose_key"),
                                             r.get("run") or None)]
        if exact:
            keep[p] = exact[0]
        elif got:
            keep[p] = got[0]
        else:
            orphans.append(p)

    # One record, one recording. A record may legitimately hold several
    # PATHS -- the same folder reached through two mounts -- but never two
    # folders, and two takes of one run on one day are two folders: an
    # evening flower pot run and the next morning's share a mouse, a
    # session and a run, and differ only in when they started. The first
    # keeps the record; the rest are treated as though they had none.
    seen_by = {}
    for p in disk:
        r = keep.get(p)
        if r is None:
            continue
        if id(r) in seen_by:
            del keep[p]
            orphans.append(p)
        else:
            seen_by[id(r)] = p
    orphans.sort()

    claimed = {id(r) for r in keep.values()}
    for r in rows:
        if id(r) not in claimed:
            retire.append(r)

    # Records that hold a folder they are not the keeper of.
    strays = 0
    for r in rows:
        for p in (r.get("paths") or []):
            k = keep.get(os.path.normcase(str(p))) or keep.get(str(p))
            if k is None:
                for q, kr in keep.items():
                    if os.path.normcase(q) == os.path.normcase(str(p)):
                        k = kr
                        break
            if k is not None and id(k) != id(r):
                strays += 1

    print("folders with a record already : %d" % len(keep))
    print("folders with none (to create) : %d" % len(orphans))
    print("records claiming a folder that is not theirs, by path : %d"
          % strays)
    print("records covering nothing on disk (to retire)          : %d"
          % len(retire))
    for r in retire[:8]:
        print("   %-38s %s" % (r.get("label"),
                               (r.get("paths") or [""])[0]))
    for p in orphans[:8]:
        got = ids.identify(p)
        print("   new: m%s s%s %s%s %s  %s"
              % (got.get("mouse"), got.get("session"), got.get("phase"),
                 got.get("phase_n"), got.get("run"), os.path.basename(p)))

    if not apply:
        print("\nDry run. Nothing was written. Re-run with --apply to act.")
        return 0

    print("\napplying...")

    # 1. every record claims only the folders it keeps
    fixed = 0
    for r in rows:
        want = [p for p in disk if keep.get(p) is r]
        have = [str(p) for p in (r.get("paths") or [])]
        # keep any path that is not on this share at all -- another mount,
        # another drive, nothing to do with this rebuild
        want += [p for p in have if not is_dewey(p)]
        if sorted(os.path.normcase(x) for x in want) != \
           sorted(os.path.normcase(x) for x in have):
            REG._patch(r, {"paths": want})
            fixed += 1

    # 2. a record for every folder that has none
    made = 0
    for p in orphans:
        ident = ids.identify(p)
        REG.ensure(ident)
        patch = facts_for(p)
        patch.setdefault("probe", "dewey32")
        patch.setdefault("probe_source", "manual")
        STORE.upsert_session(ident, patch)
        made += 1
        if made % 10 == 0:
            print("  ... %d of %d" % (made, len(orphans)))

    # 3. retire what covers nothing
    for r in retire:
        REG._patch(r, {"retired": True})

    print("\nDone. %d record(s) re-pathed, %d created, %d retired."
          % (fixed, made, len(retire)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
