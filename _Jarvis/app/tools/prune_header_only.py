# -*- coding: utf-8 -*-
"""Take recordings that are only Neuralynx headers out of the registry.

    python tools/prune_header_only.py            # say what would change
    python tools/prune_header_only.py --apply    # write it (backs up first)
    python tools/prune_header_only.py --all      # every project, not KCNT1

The user's ask (2026-11-03), after the KCNT1 data went onto netfiles: make
sure it is all good, "and dont add anything/purne anything thats just
headers".

A header-only folder is what the rig leaves when acquisition is started and
stopped before a sample: every CSC file exactly 16384 bytes, a header and no
records. Measured that day on `Jeremy3\\KCNT1`: 179 of 490 recording folders
are that, and 95 registry records pointed at nothing else. The rig had kept
writing stubs into old session folders for months (m486 s8, m536 s6, m14 s2),
and each stub was minted as a recording of its own. Fifteen more real
recordings carried stub folders beside their real one.

What it does, from what is on disk now, never from a guess:

  FORGET  a record whose every path is reachable and header-only, with
          nothing hanging off it. Erased on every machine's shard and
          tombstoned, exactly as Housekeeping's Forget does, so a sync or a
          colleague's copy does not bring it back.
  DROP    a header-only path off a record that keeps a real one, with a path
          tombstone (as pathtidy does) so a pull does not re-add it.

What it does NOT touch:
  * any folder on any drive -- Jarvis does not delete data it did not write;
    the stubs stay on netfiles, the lab's to bin;
  * a record with a path this computer cannot reach: it may have data on
    another machine's disk;
  * a record with any work on it (bad channels, notes, quality, bookmarks,
    labels, a bank entry, a curation set, a run...). Listed, left alone.

Every shard it changes is copied first to GUI_logs/.cache/prune_header_only/
<stamp>/.
"""
import argparse
import collections
import io
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from backend import device as devicemod           # noqa: E402
from backend import profile as profilemod         # noqa: E402
from backend import sessreg, store as storemod     # noqa: E402
from backend import tombs as tombsmod              # noqa: E402
from backend.paths import LOGS_DIR                 # noqa: E402

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HEADER_BYTES = 16384
UNC = "\\\\netfiles03.uvm.edu\\bigdata_jbarry\\"

# Fields a person fills in. A record with any of them set has had work done
# on it and is not this tool's to remove.
WORK = ("bad_channels", "bad_channels_note", "bookmarks", "note", "quality",
        "spike_labels", "event_classes", "condition", "hemisphere")
MANUAL = ("project_source", "probe_source", "hemisphere_source")

# Folders that hold references to recordings by gid. The registry itself,
# the logs and the notes are not references.
NOT_REFS = {"sessions", "activity", "errors", "error_reports", "tombstones",
            ".cache", "health", "feedback", "prefs", "guides"}
GID_RE = re.compile(r"s[0-9a-f]{12}")


def say(*a):
    print(*a, file=OUT, flush=True)


def openable(path):
    """The spelling of `path` this computer can open: `Y:` is the rigs'
    mapping of the share, and this computer may not have it."""
    if re.match(r"^[Yy]:[\\/]", path) and not os.path.isdir("Y:\\"):
        return UNC + path[3:].replace("/", "\\")
    return path


def state_of(path):
    """'header-only', 'data', or 'unreachable' for one recording folder."""
    p = openable(path)
    try:
        names = [(e.name, e.stat().st_size) for e in os.scandir(p)
                 if e.is_file() and e.name.lower().endswith(".ncs")]
    except OSError:
        return "unreachable"
    if names and all(s <= HEADER_BYTES for _n, s in names):
        return "header-only"
    return "data"


def references():
    """gid -> files under GUI_logs that mention it (outside the registry and
    the logs)."""
    refs = collections.defaultdict(set)
    for top in os.listdir(LOGS_DIR):
        if top in NOT_REFS:
            continue
        root = os.path.join(LOGS_DIR, top)
        for dp, _dn, fn in os.walk(root):
            for f in fn:
                path = os.path.join(dp, f)
                hits = set(GID_RE.findall(f))
                if f.endswith((".json", ".jsonl", ".csv", ".txt", ".md")):
                    try:
                        with open(path, "r", encoding="utf-8",
                                  errors="replace") as fh:
                            hits |= set(GID_RE.findall(fh.read()))
                    except OSError:
                        pass
                for g in hits:
                    refs[g].add(os.path.relpath(path, LOGS_DIR))
    return refs


def in_scope(rec, everything):
    """KCNT1 by default: either project, or a path in a KCNT1 folder (an
    Unfiled record from the urethane tree counts). DEWEY keeps FP1, SPC and
    FP2 under one gid, so a stub there is a different question."""
    if everything:
        return True
    if str(rec.get("project") or "").startswith("KCNT1"):
        return True
    return any("kcnt" in str(p).lower() for p in rec.get("paths") or [])


def work_on(rec):
    out = [k for k in WORK if rec.get(k)]
    out += [k for k in MANUAL if rec.get(k) == "manual"]
    vs = rec.get("view_state")
    if isinstance(vs, dict) and vs:
        out.append("view_state")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="every project, not only KCNT1")
    args = ap.parse_args()

    store = storemod.Store(LOGS_DIR, auto_stage=False)
    prof = profilemod.Profile(LOGS_DIR, store)
    store.profile = prof
    dev = devicemod.Device(LOGS_DIR, store)
    store.device = dev
    prof.device = dev
    reg = sessreg.Registry(store)
    tombs = tombsmod.Tombs(LOGS_DIR, store)

    seen, recs = set(), []
    for r in reg.all():
        if r.get("gid") and not r.get("retired") and r["gid"] not in seen \
                and in_scope(r, args.all):
            seen.add(r["gid"])
            recs.append(r)
    paths = sorted({p for r in recs for p in (r.get("paths") or [])
                    if isinstance(p, str) and not p.startswith("vacc:")})
    say("%d records, %d paths to look at" % (len(recs), len(paths)))
    t0 = time.time()
    with ThreadPoolExecutor(16) as pool:
        state = dict(zip(paths, pool.map(state_of, paths)))
    say("looked in %.0f s: %s" % (time.time() - t0,
                                  dict(collections.Counter(state.values()))))

    forget, drop, kept = [], [], []
    for r in recs:
        # A `vacc:` mark is a copy on the cluster, which nothing here can
        # look into: it counts as unreachable, and keeps the record.
        ps = list(r.get("paths") or [])
        stubs = [p for p in ps if state.get(p) == "header-only"]
        if not stubs:
            continue
        if len(stubs) == len(ps):
            forget.append(r)
        else:
            drop.append((r, stubs))

    refs = references() if forget else {}
    really = []
    for r in forget:
        why = work_on(r) + sorted(refs.get(r["gid"], ()))
        if why:
            kept.append((r, why))
        else:
            really.append(r)

    by_proj = collections.Counter(r.get("project") or "Unfiled"
                                  for r in really)
    say("\nFORGET %d records that are only headers: %s"
        % (len(really), dict(by_proj)))
    for r in sorted(really, key=lambda r: str(r.get("label"))):
        say("  %s  %s" % (r["gid"], r.get("label") or r.get("key")))
    say("\nDROP %d header-only paths off %d records that keep real data"
        % (sum(len(s) for _r, s in drop), len(drop)))
    for r, s in drop:
        say("  %s  %s  -%d" % (r["gid"], r.get("label"), len(s)))
    if kept:
        say("\nLEFT ALONE: %d header-only records with work on them" % len(kept))
        for r, why in kept:
            say("  %s  %s  (%s)" % (r["gid"], r.get("label"), ", ".join(why)))

    if not args.apply:
        say("\nNothing written. --apply to do it.")
        return
    say("\nwriting as %s" % json.dumps(store.provenance()))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(LOGS_DIR, ".cache", "prune_header_only", stamp)

    def keep_copy(base):
        for _m, path in store.sessions.shard_files(base):
            dst = os.path.join(backup, os.path.relpath(path, LOGS_DIR))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(path, dst)

    gone = 0
    for r in really:
        base = store.session_base(r.get("key") or "")
        keep_copy(base)
        if store.sessions.erase(base):
            tombs.add("session", r["gid"],
                      note="forgotten: every folder is headers only")
            gone += 1
        else:
            say("  could not erase %s (%s)" % (r["gid"], base))
    dropped = 0
    for r, stubs in drop:
        base = store.session_base(r.get("key") or "")
        keep_copy(base)
        ident = {k: r.get(k) for k in ("key", "loose_key", "mouse", "session",
                                       "start", "label")}
        mine = store.sessions.read(base) if r.get("key") else None
        if not (mine and mine.get("gid") == r["gid"]):
            ident["gid"] = r["gid"]
        left = [p for p in (r.get("paths") or []) if p not in set(stubs)]
        store.upsert_session(ident, {"paths": left})
        for p in stubs:
            tombs.add("path", "%s|%s" % (r["gid"], p),
                      note="a folder of headers only")
            dropped += 1
    store.record_activity([{"action": "registry.prune_header_only",
                            "detail": {"forgotten": gone, "paths": dropped,
                                       "left_alone": len(kept)}}])
    say("\nforgot %d records, dropped %d paths; backup in %s"
        % (gone, dropped, backup))


if __name__ == "__main__":
    main()
