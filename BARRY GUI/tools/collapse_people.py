# -*- coding: utf-8 -*-
"""Re-credit every test harness's work to Debug_Bot, and two departed names
to Shahriar Tafti -- in the records themselves, on every machine's shard.

    python tools/collapse_people.py            # say what would change
    python tools/collapse_people.py --apply    # write it (backs up first)
    python tools/collapse_people.py --apply --roster http://127.0.0.1:8733
                                               # and fold the roster too

The user's ask (2026-10-23): remove "eye harness", "spotter harness",
"harness@test" and the rest of the test names, collapse them into Debug_Bot,
"and update all the banks that exist to also be that"; and fully remove
"Fatima" and "a colleague", assigning their work to Shahriar Tafti.

Why the shard FILES and not `BANK.rename_person`, which merge_people.py
uses: `added.by` is shards.FIRST, so a rename written into this machine's
shard carries a new stamp and loses to the shard that recorded it first --
merge_people.py says so, and left seven entries unchanged for that reason.
Rewriting the value in every shard that holds it, with every stamp left as
it was, changes what each copy says without changing who wins the merge.
The other machines get it with their next git pull; the cloud rows are not
re-sent (their `updated_at` does not move), and the roster's aliases and
`people.test_credit` fold anything still arriving under an old name.

What is NOT touched, on purpose:
  * the activity and error logs -- append-only; editing a name there is
    refused as audit tampering, and the name in a log line is what the
    machine believed at the time;
  * run records (GUI_logs/runs) -- written once and never edited;
  * descriptions, notes, pipelines and project names ("harness bank",
    project HARNESS) -- they describe, they do not credit;
  * the roster rows themselves. Those go through the running app
    (/api/people/add with aliases, then /api/people/forget), which writes
    the retirement tombstones that stop another machine's copy coming back.

Every file it changes is copied first to GUI_logs/.cache/collapse_people/
<stamp>/, under its own relative path.
"""
import argparse
import collections
import io
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from backend import people as peoplemod          # noqa: E402
from backend import shards                       # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")
OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ME = "Shahriar Tafti"
# Lower-cased name -> who it becomes. Anything else a harness wrote is
# caught by `peoplemod.is_test_name` and becomes Debug_Bot.
GONE = {
    "fatima": ME,
    "a colleague": ME,
}


# The roster half, through the running app's own routes. Debug_Bot keeps
# every harness name it replaced as an alias, so a record still arriving
# under one -- a cloud row, a machine that has not pulled -- folds into it.
# NOT the people harnesses' own probe names ("zz edit probe", "Harness
# Probe Person"): those harnesses add their probe, look for it by name and
# remove it, and an alias would fold it away before they could find it
# (peopleedit.html failed exactly that way until they were taken out).
ROSTER_TEST = ["harness@test", "eye harness", "spotter harness",
               "bankback@harness", "curate@harness", "spikeflow@harness",
               "harness", "test"]
ROSTER_GONE = ["Fatima", "a colleague"]


def fold_roster(base):
    base = base.rstrip("/")

    def post(path, body):
        req = urllib.request.Request(
            base + path, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)

    def get(path):
        with urllib.request.urlopen(base + path, timeout=120) as r:
            return json.load(r)

    post("/api/people/add", {
        "name": peoplemod.DEBUG_BOT, "role": "Test harnesses",
        "initials": "DB", "aliases": ROSTER_TEST,
        "note": "Every name a test harness stamped on its seeds, "
                "collapsed into one (2026-10-23)."})
    keep = get("/api/people/" + urllib.parse.quote(ME)).get("person") or {}
    had = [a for a in (keep.get("aliases") or []) if a]
    post("/api/people/add", {"name": ME, "aliases": sorted(
        {a.lower() for a in had + ROSTER_GONE})})
    # Forgotten AFTER the aliases exist: `forget` writes the retirement
    # tombstone only when the name has genuinely gone from the roster.
    for name in ROSTER_TEST + ROSTER_GONE:
        got = post("/api/people/forget", {"name": name})
        say("  forget %-22s %s" % (name, "removed" if got.get("removed")
                                   else "(no row here)"))


def say(msg=""):
    OUT.write(msg + "\n")
    OUT.flush()


def becomes(name):
    """Who `name` is credited to now, or None to leave it alone."""
    if not isinstance(name, str) or not name.strip():
        return None
    low = name.strip().lower()
    if low in GONE:
        return GONE[low]
    if peoplemod.is_test_name(name) and name != peoplemod.DEBUG_BOT:
        return peoplemod.DEBUG_BOT
    return None


# Where a credit lives, per store: a path of keys, "[]" for each item of a
# list. Only fields that say WHO did something.
FIELDS = {
    "event_bank": [
        ("added", "by"),
        ("versions", "[]", "by"),
        ("versions", "[]", "confirmed", "[]", "by"),
        ("history", "[]", "by"),
    ],
    "curation": [
        ("source", "by"),
        ("imports", "[]", "source", "by"),
        ("events", "[]", "by"),
        ("events", "[]", "reviews", "[]", "by"),
        ("assignee",), ("opened_by",), ("closed_by",),
    ],
    "sessions": [
        ("updated", "user"),
    ],
    # Who added a roster row -- not the row's own name, which the app
    # removes properly (see the docstring).
    "prefs": [
        ("added", "[]", "by"),
    ],
}


def rewrite(node, path, counts, label):
    """Walk `path` into `node`, replacing a credited name in place."""
    if not path:
        return 0
    head, rest = path[0], path[1:]
    n = 0
    if head == "[]":
        if isinstance(node, list):
            for item in node:
                n += rewrite(item, rest, counts, label)
        return n
    if not isinstance(node, dict) or head not in node:
        return 0
    if not rest:
        want = becomes(node[head])
        if want:
            counts[(label, node[head], want)] += 1
            node[head] = want
            return 1
        return 0
    return rewrite(node[head], rest, counts, label)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without it, only reports.")
    ap.add_argument("--roster", default="",
                    help="the running app's address: also fold the roster "
                         "(Debug_Bot and Shahriar Tafti get the aliases, "
                         "the old names are forgotten and retired)")
    args = ap.parse_args()
    if not args.apply:
        say("*** DRY RUN -- nothing will be written. Add --apply to do it.")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(LOGS, ".cache", "collapse_people", stamp)
    counts = collections.Counter()
    files = collections.Counter()
    changed = []

    for store, paths in FIELDS.items():
        root = os.path.join(LOGS, store)
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            if not fn.endswith(".json"):
                continue
            if store == "prefs" and not fn.startswith("people@"):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8") as fh:
                    rec = json.load(fh)
            except Exception as exc:                     # noqa: BLE001
                say("  unreadable, left alone: %s (%s)" % (p, exc))
                continue
            hit = 0
            for path in paths:
                hit += rewrite(rec, path, counts, store)
            if not hit:
                continue
            files[store] += 1
            changed.append((p, rec))

    say("\nRe-credited, by store:")
    for (store, old, new), n in sorted(counts.items()):
        say("  %-10s %-26s -> %-15s %5d" % (store, old, new, n))
    say("\nFiles: " + ", ".join("%s %d" % kv for kv in sorted(files.items()))
        if files else "\nNothing to change.")

    if not args.apply or not changed:
        say("\nNothing was written." if not args.apply else "")
        if args.apply and args.roster:
            say("\nThe roster, through %s:" % args.roster)
            fold_roster(args.roster)
        return

    for p, rec in changed:
        rel = os.path.relpath(p, LOGS)
        dst = os.path.join(backup, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
    say("\nBacked up %d files to %s" % (len(changed), backup))

    bad = []
    for p, rec in changed:
        # The store's own writer: sibling temp, fsync, os.replace -- and the
        # same indent and key order, so the diff is only the names.
        for attempt in range(6):
            try:
                shards._write_json(p, rec)
                break
            except PermissionError:
                # OneDrive or a reader holding it open (WinError 32).
                time.sleep(0.5 * (attempt + 1))
        else:
            bad.append(p)
            continue
        if os.path.getsize(p) == 0:
            bad.append(p)
    if bad:
        say("\nCOULD NOT WRITE %d file(s) -- restore them from the backup:"
            % len(bad))
        for p in bad:
            say("  " + p)
        sys.exit(1)
    say("Written: %d files." % len(changed))
    if args.roster:
        say("\nThe roster, through %s:" % args.roster)
        fold_roster(args.roster)


if __name__ == "__main__":
    main()
