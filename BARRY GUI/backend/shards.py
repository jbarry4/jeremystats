"""
shards.py -- Why BARRY's logs can never produce a git conflict.

The rule
--------
**No two machines ever write the same file.**

That is the whole design. Not "conflicts are rare", not "conflicts are small
and easy to resolve" -- impossible, because a conflict requires two sides to
have changed the same file, and no file here has more than one possible
author.

One file per session was already a big improvement over one shared log, but it
only moved the problem: two people both editing m1s2's bad channels still
collide on `sessions/m1s2.json`. So every record that can be *edited* is split
again, by machine:

    sessions/m1s2@z390-4f1a.json     what the Z390 knows about m1s2
    sessions/m1s2@lab-nlx-9c02.json  what the rig machine knows about m1s2

Each machine writes only its own shard, ever. Git sees two unrelated files.
`git pull` brings both in. There is nothing to merge, at the file level.

The merge happens on read, here, in code -- which is the right place for it,
because only code knows that two `paths` lists should be unioned while two
`note` strings should not.

How the merge works
-------------------
A shard carries the record as that machine last knew it, plus stamps saying
when that machine last *changed* each thing:

    { "bad_channels": [14, 22],
      "_shard": {"machine": "z390-4f1a", "at": "..."},
      "_at":    {"bad_channels": "2026-09-02T11:04:31-0400"},
      "_keys":  {"paths": {"D:\\PTEN\\m1s2": ["set", "2026-09-01T..."]}} }

Merging is then per field, by kind:

    LWW      newest stamp wins.  The default, and right for anything one
             person decides: a note, a label, a project.
    FIRST    oldest stamp wins.  For birth facts that must never move --
             the global id, the created-by record.  Two machines minting a
             gid for the same recording settle on the earlier one rather
             than flipping forever.
    UNION    a list treated as a set, unioned across machines.  For `paths`:
             each machine legitimately knows a different mount, and none of
             them is wrong, so nobody should win.
    MAPLWW   a dict merged key by key.  For layer labels, curation decisions,
             per-machine sightings.  Two people labelling different channels
             of the same shank both keep their work.
    BYID     a list of dicts each carrying an `id`, merged per id.  For
             bookmarks, presets, spike sets.

Deletion needs stamps too, or it loses to any older write that still has the
item: removing a path writes a `["gone", when]` tombstone, and the item is
present only if its newest "set" beats its newest "gone".

Lost updates
------------
Read-modify-write across machines has the usual hazard: I read, you change a
field, I write back the value I read and clobber you. Avoided by stamping only
what *I* actually changed -- `read()` tucks the values it handed out into the
record under `_sync`, and `write()` diffs against those rather than against
whatever the merge says now. A field I never touched keeps the stamp it came
with and loses to your newer edit, which is what should happen.

What is deliberately NOT sharded
--------------------------------
Files written once by their creator and never edited by anyone else -- a run
record, a day of append-only errors. Those cannot conflict either, provided
the *name* is unique to the writer, which is why the append-only logs are per
machine per day rather than per day.

And derived files. `index.json` is a roll-up of everything else, regenerated
constantly; tracking it in git means a guaranteed conflict on every pull for a
file nobody reads and anyone can rebuild in a second. It lives in a cache
directory git ignores.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

SCHEMA = 1
SIGIL = "@"          # <base>@<machine>.json
LEGACY = "~legacy"   # a pre-sharding file: merged in, never written to
EPOCH = "0000-00-00T00:00:00"

_LOCK = threading.RLock()

# Merge kinds. See the module docstring.
LWW, FIRST, UNION, MAPLWW, BYID = "lww", "first", "union", "maplww", "byid"

# Bookkeeping keys, stripped out of anything a caller sees as "the record".
META = ("_shard", "_at", "_keys", "_sync")


_LAST_STAMP = ""


def _now():
    """A stamp that sorts correctly as a plain string, always.

    UTC, because two machines in different timezones comparing local-time
    strings get the wrong answer and the bug only shows up in October.
    Microseconds, because Windows' clock ticks about every 15 ms and two edits
    inside one tick would be unorderable -- which is not theoretical: a
    fill-down writes sixty labels in a few milliseconds. And strictly
    increasing within a process, so even two writes in the same microsecond
    keep the order they happened in.
    """
    global _LAST_STAMP
    with _LOCK:
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        if now <= _LAST_STAMP:
            # Nudge past the last one rather than issuing a duplicate.
            base = datetime.fromisoformat(_LAST_STAMP) + timedelta(microseconds=1)
            now = base.isoformat(timespec="microseconds")
        _LAST_STAMP = now
        return now


def _slug(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(text or "")).strip("-").lower()


_MACHINE = None


def machine_id():
    """A short, stable, unique name for this computer.

    Stable because it is derived, not stored: a fresh clone of the repo on the
    same machine keeps writing to the same shards instead of orphaning them.
    Unique because the hostname alone is not -- a lab with two machines both
    called DESKTOP-PC would have them silently sharing a file, which is the
    exact failure this module exists to prevent -- so the network MAC is mixed
    in and shows up as a four-character tag.

    BARRY_MACHINE overrides it, which is how the tests pretend to be a second
    computer.
    """
    global _MACHINE
    if _MACHINE:
        return _MACHINE
    forced = os.environ.get("BARRY_MACHINE")
    if forced:
        _MACHINE = _slug(forced)[:32] or "machine"
        return _MACHINE
    node = _slug(platform.node())[:24] or "machine"
    tag = hashlib.sha1(str(uuid.getnode()).encode("utf-8")).hexdigest()[:4]
    _MACHINE = "%s-%s" % (node, tag)
    return _MACHINE


def split_name(filename, ext=".json"):
    """"m1s2@z390-4f1a.json" -> ("m1s2", "z390-4f1a")."""
    if not filename.endswith(ext):
        return None, None
    stem = filename[:-len(ext)]
    if SIGIL in stem:
        base, machine = stem.rsplit(SIGIL, 1)
        return base, machine
    return stem, LEGACY


def safe_base(*parts):
    """A filename stem from record ids, with the sigil kept out of it."""
    out = []
    for p in parts:
        s = "".join(c for c in str(p) if c.isalnum() or c in "._-")
        out.append(s or "x")
    return "__".join(out)


# ==========================================================================
# Merging
# ==========================================================================
def _stamp_of(shard, field):
    return (shard.get("_at") or {}).get(field) or \
        (shard.get("_shard") or {}).get("at") or EPOCH


def _key_stamp(shard, field, key):
    entry = ((shard.get("_keys") or {}).get(field) or {}).get(str(key))
    if isinstance(entry, list) and len(entry) == 2:
        return entry[0], entry[1]
    return None, None


def _winner(cands):
    """Newest wins; the machine name breaks ties so every clone agrees."""
    return max(cands, key=lambda c: (c[0], c[1]))


def merge(shards, spec=None):
    """Compile per-machine shards into one record.

    `shards` is a list of (machine, dict). Returns None if there is nothing.

    The compiled record carries a `_sync` block: which machines contributed,
    and -- crucially -- the provenance of every value handed out. A later
    write() uses that to re-stamp only what the caller actually changed, and
    to carry everything else forward untouched. Without it, writing back a
    record you merely read would re-date all of it and quietly resurrect
    anything a colleague had deleted.
    """
    spec = spec or {}
    live = [(m, s) for m, s in shards if isinstance(s, dict) and s]
    if not live:
        return None

    fields = []
    for _m, s in live:
        for k in s:
            if k not in META and k not in fields:
                fields.append(k)

    out, fstamps, kstamps, snap = {}, {}, {}, {}
    for field in fields:
        kind = spec.get(field, LWW)
        if kind in (UNION, MAPLWW, BYID):
            pairs, stamps = _merge_setlike(live, field, kind)
            out[field] = (dict(pairs) if kind == MAPLWW
                          else [v for _k, v in pairs])
            kstamps[field] = stamps
            snap[field] = dict(pairs)
        else:
            cands = [(_stamp_of(s, field), m, s[field])
                     for m, s in live if field in s]
            if not cands:
                continue
            pick = (min(cands, key=lambda c: (c[0], c[1])) if kind == FIRST
                    else max(cands, key=lambda c: (c[0], c[1])))
            # A field written as None is a tombstone, not a value.
            if pick[2] is None and kind != FIRST:
                fstamps[field] = pick[0]
                continue
            out[field] = pick[2]
            fstamps[field] = pick[0]

    out["_sync"] = {
        "machines": sorted(m for m, _s in live),
        "mine": machine_id(),
        "was": {k: _fingerprint(v) for k, v in out.items() if k != "_sync"},
        "fstamps": fstamps,
        "kstamps": kstamps,
        "snap": snap,
    }
    return out


def _set_stamps(shard, field):
    """(set stamps, gone stamps, fallback) for one set-like field."""
    fallback = _stamp_of(shard, field)
    table = (shard.get("_keys") or {}).get(field) or {}
    present, gone = {}, {}
    for key, entry in table.items():
        if isinstance(entry, list) and len(entry) == 2:
            (gone if entry[0] == "gone" else present)[key] = entry[1]
    return present, gone, fallback


def _items_of(shard, field, kind):
    if kind == MAPLWW:
        table = shard.get(field)
        if isinstance(table, dict):
            for key, value in table.items():
                yield str(key), value
        return
    for item in (shard.get(field) or []):
        yield _item_key(item), item


def _merge_setlike(live, field, kind):
    """UNION / MAPLWW / BYID share one body.

    The winner for each key is the newest "set" stamp across machines, and the
    key survives only if that beats the newest "gone" stamp -- which is what
    makes a deletion stick instead of being undone by an older shard that
    still lists the item. Order follows first appearance, so the compiled
    record diffs readably.
    """
    order, best, gone = [], {}, {}
    for machine, shard in live:
        present, dead, fallback = _set_stamps(shard, field)
        for key, value in _items_of(shard, field, kind):
            if key not in best and key not in order:
                order.append(key)
            at = present.get(key, fallback)
            if (at, machine) > best.get(key, (EPOCH, ""))[:2]:
                best[key] = (at, machine, value)
        for key, at in dead.items():
            if at > gone.get(key, EPOCH):
                gone[key] = at

    pairs, stamps = [], {}
    for key in order:
        if key not in best:
            continue
        at = best[key][0]
        if gone.get(key, EPOCH) > at:
            stamps[key] = ["gone", gone[key]]
            continue
        pairs.append((key, best[key][2]))
        stamps[key] = ["set", at]
    for key, at in gone.items():
        stamps.setdefault(key, ["gone", at])
    return pairs, stamps


def _item_key(item):
    if isinstance(item, dict):
        for k in ("id", "gid", "key", "name", "path"):
            if item.get(k) is not None:
                return str(item[k])
        return json.dumps(item, sort_keys=True, default=str)
    return str(item)


def _fingerprint(value):
    try:
        return hashlib.sha1(
            json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:12]
    except (TypeError, ValueError):
        return str(value)[:32]


# ==========================================================================
# The book: read-merge, write-mine
# ==========================================================================
class Book:
    """A directory of sharded records.

    `spec` maps a field name to a merge kind. Anything unlisted is LWW, which
    is the right default: most fields are one person's decision, and the last
    decision is the one that stands.
    """

    def __init__(self, dirpath, spec=None, store=None, ext=".json"):
        self.dir = os.path.abspath(dirpath)
        self.spec = dict(spec or {})
        self.store = store
        self.ext = ext
        os.makedirs(self.dir, exist_ok=True)

    # -- naming ---------------------------------------------------------
    def mine(self, base):
        return os.path.join(self.dir,
                            "%s%s%s%s" % (base, SIGIL, machine_id(), self.ext))

    def shard_files(self, base):
        out = []
        for name in sorted(_listdir(self.dir)):
            b, m = split_name(name, self.ext)
            if b == base:
                out.append((m, os.path.join(self.dir, name)))
        return out

    def bases(self):
        seen = []
        for name in sorted(_listdir(self.dir)):
            b, _m = split_name(name, self.ext)
            if b and b not in seen:
                seen.append(b)
        return seen

    # -- reading --------------------------------------------------------
    def read(self, base):
        shards = []
        for machine, path in self.shard_files(base):
            rec = _read_json(path)
            if rec:
                if machine == LEGACY:
                    # Pre-sharding content. Given the oldest possible stamp so
                    # any real edit since beats it, and never written to again.
                    rec.setdefault("_shard", {})
                    rec["_shard"].setdefault("at", EPOCH)
                shards.append((machine, rec))
        return merge(shards, self.spec)

    def all(self):
        return [r for r in (self.read(b) for b in self.bases()) if r]

    def machines(self, base):
        return [m for m, _p in self.shard_files(base)]

    # -- writing --------------------------------------------------------
    def write(self, base, rec):
        """Persist `rec` as this machine's shard of `base`.

        Only what actually changed since read() handed the record over is
        re-stamped. Everything else keeps the provenance it arrived with, so
        writing back a record you only partly edited cannot clobber a
        colleague's newer change, and cannot undo their deletion.
        """
        with _LOCK:
            sync = rec.pop("_sync", None) or {}
            was = sync.get("was") or {}
            fstamps = sync.get("fstamps") or {}
            kstamps = sync.get("kstamps") or {}
            snap = sync.get("snap") or {}

            path = self.mine(base)
            prev = _read_json(path) or {}
            at = _now()

            body = {k: v for k, v in rec.items() if k not in META}
            stamps = dict(prev.get("_at") or {})
            keys = {k: dict(v) for k, v in (prev.get("_keys") or {}).items()}

            for field, value in body.items():
                kind = self.spec.get(field, LWW)
                if kind in (UNION, MAPLWW, BYID):
                    self._stamp_keys(keys.setdefault(field, {}), field, kind,
                                     value, snap.get(field) or {},
                                     kstamps.get(field) or {}, at)
                elif was.get(field) == _fingerprint(value):
                    # Untouched: keep the stamp it came in with. Falling back
                    # to now would make a value I merely read look like a
                    # decision I just made.
                    stamps[field] = fstamps.get(field) or                         stamps.get(field) or EPOCH
                else:
                    stamps[field] = at

            # A field the caller dropped from a record it had read: a real
            # removal, written as an explicit null so it outranks the value.
            for field in list(was):
                if field in body or field in META:
                    continue
                body[field] = None
                stamps[field] = at

            out = dict(body)
            out["_shard"] = {"machine": machine_id(), "at": at,
                             "schema": SCHEMA}
            out["_at"] = stamps
            keys = {k: v for k, v in keys.items() if v}
            if keys:
                out["_keys"] = keys
            _write_json(path, out)
            if self.store:
                self.store._stage(path)
            merged = self.read(base)
            return merged if merged is not None else rec

    def _stamp_keys(self, table, field, kind, value, snap, inherited, at):
        """Per-item stamps for the set-like kinds, including tombstones.

        `snap` is what read() handed out, so "changed" means changed by this
        caller -- not merely different from what some other machine has since
        written.
        """
        now = ({str(k): v for k, v in (value or {}).items()}
               if kind == MAPLWW and isinstance(value, dict)
               else {_item_key(i): i for i in (value or [])})

        for key, val in now.items():
            if key in snap and snap[key] == val:
                # Carried through untouched: keep whoever's stamp won.
                got = inherited.get(key)
                table[key] = list(got) if got else table.get(key, ["set", at])
            else:
                table[key] = ["set", at]

        for key in snap:
            if key not in now:
                table[key] = ["gone", at]

        # Tombstones this machine already holds for keys nobody has revived.
        for key, entry in list(table.items()):
            if entry and entry[0] == "gone" and key in now:
                table[key] = ["set", at]

    def forget(self, base):
        """Drop this machine's shard. Other machines keep theirs."""
        with _LOCK:
            path = self.mine(base)
            try:
                os.remove(path)
            except OSError:
                return False
            if self.store:
                self.store._stage(path)
            return True

    def erase(self, base):
        """Remove the record everywhere this clone can see it.

        Deleting another machine's shard is the one operation here that can
        conflict -- delete-vs-modify -- so it is offered separately from
        `forget`, used only when a person explicitly deletes a record, and
        never as a side effect.
        """
        with _LOCK:
            gone = 0
            for _m, path in self.shard_files(base):
                try:
                    os.remove(path)
                    gone += 1
                    if self.store:
                        self.store._stage(path)
                except OSError:
                    pass
            return gone

    # -- migration ------------------------------------------------------
    def absorb_legacy(self):
        """Turn every pre-sharding file into this machine's shard.

        Both sides of a pull doing this produce "both deleted the old file,
        each added their own" -- which git resolves without asking. Modifying
        one while another deletes it would conflict, so this runs once, early,
        rather than lazily on first write.
        """
        moved = []
        for name in sorted(_listdir(self.dir)):
            base, machine = split_name(name, self.ext)
            if machine != LEGACY or not base:
                continue
            old = os.path.join(self.dir, name)
            rec = _read_json(old)
            if rec is None:
                continue
            new = self.mine(base)
            if os.path.exists(new):
                merged = merge([(LEGACY, dict(rec, _shard={"at": EPOCH})),
                                (machine_id(), _read_json(new) or {})],
                               self.spec) or rec
                merged.pop("_sync", None)
                rec = merged
            body = {k: v for k, v in rec.items() if k not in META}
            body["_shard"] = {"machine": machine_id(), "at": _now(),
                              "schema": SCHEMA, "from": "pre-shard file"}
            _write_json(new, body)
            try:
                os.remove(old)
            except OSError:
                pass
            if self.store:
                self.store._stage(new)
                self.store._stage(old)
            moved.append(base)
        return moved


# ==========================================================================
# Append-only logs (errors, activity): one file per day PER MACHINE
# ==========================================================================
class DayLog:
    """JSONL, appended. Two machines appending to one file is the classic
    conflict -- both add lines at the end and git cannot tell whose go first --
    so the day is only half the filename and the machine is the other half."""

    def __init__(self, dirpath, store=None):
        self.dir = os.path.abspath(dirpath)
        self.store = store
        os.makedirs(self.dir, exist_ok=True)

    def path(self, day, machine=None):
        return os.path.join(
            self.dir, "%s%s%s.jsonl" % (day, SIGIL, machine or machine_id()))

    def append(self, records):
        if isinstance(records, dict):
            records = [records]
        if not records:
            return 0
        day = (records[0].get("at") or _now())[:10]
        path = self.path(day)
        n = 0
        with _LOCK:
            try:
                with open(path, "a", encoding="utf-8", newline="\n") as fh:
                    for r in records:
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                        n += 1
            except OSError:
                return 0
        if self.store:
            self.store._stage(path)
        return n

    def days(self):
        out = []
        for name in _listdir(self.dir):
            if not name.endswith(".jsonl"):
                continue
            stem = name[:-len(".jsonl")]
            day = stem.rsplit(SIGIL, 1)[0]
            if day not in out:
                out.append(day)
        return sorted(out, reverse=True)

    def files_for(self, day):
        want = str(day)[:10]
        out = []
        for name in sorted(_listdir(self.dir)):
            if not name.endswith(".jsonl"):
                continue
            if name[:-len(".jsonl")].rsplit(SIGIL, 1)[0] == want:
                out.append(os.path.join(self.dir, name))
        return out

    def read(self, limit=500, day=None, keep=None):
        """Newest first, across every machine's file for each day."""
        out = []
        for d in ([str(day)[:10]] if day else self.days()):
            rows = []
            for path in self.files_for(d):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rows.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                except OSError:
                    continue
            # Several machines' files for one day interleave by time, not by
            # whose file was read first.
            rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
            for r in rows:
                if keep and not keep(r):
                    continue
                out.append(r)
                if len(out) >= limit:
                    return out
        return out


# ==========================================================================
def _listdir(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _write_json(path, data):
    """Write so that a crash leaves either the old file or the new one.

    Write to a sibling, flush it all the way to the disk, then rename over
    the target. os.replace is atomic, so no reader ever sees a half-written
    file -- and the fsync is what makes that true of a power cut as well as
    of a process dying. Without it the rename can reach the disk before the
    bytes do, and the file comes back empty.

    That matters more here than the cost suggests: these files are somebody's
    curation, written one keystroke at a time, and what is being guarded
    against is losing an afternoon of it.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, sort_keys=True, default=str)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
