"""
pathtidy.py -- keeping the paths Jarvis knows true to what is on netfiles.

The user's ask (2026-10-23): "our netfiles was updated and we moved some
files and archived them. But everything we need is on there and its having
trouble opening PTEN files on new devices ... prune any file paths that
don't exist from everything JARVIS knows ... make sure next time someone
else pulls on their device all the PTEN sessions are there."

Measured that day, against a fresh walk of /netfiles/bigdata_jbarry:

  * Every one of the 62 PTEN sessions in the lab's DS sheet is on the share,
    in ProcessedPtenData -- and 59 of them were on record only as
    `Y:\\ProcessedPtenData\\...`. `Y:` is a drive letter the rigs map; a
    computer that has not mapped it (this one, and every new laptop) could
    not open a single one of them, although it reaches the share by its own
    name, `\\\\netfiles03.uvm.edu\\bigdata_jbarry`, perfectly well.
  * 197 netfiles paths on record are gone: HeadfixPilot, Chronic_SAPilot,
    5XFAD, Cdrivebckup and HOF went into `.tar.xz` archives on 2026-10-13.

So a tidy does two things, both from evidence and never from a guess:

  ADD     the share's own spelling (the UNC) of every folder the walk found
          that is a recording already on record -- the one spelling every
          lab computer can open, mapped drive or not.
  DROP    a path the cluster says is not there any more (checked on the
          cluster itself, one connection, `test -e`), a test's temporary
          folder, and a path to a file rather than a folder.

What it does not touch: a path on a local drive (`D:\\PTEN\\...`). It may be
another computer's disk, which nothing here can see, and a path that does not
resolve is the ordinary state of a path belonging to another machine.

A drop is remembered as well as made (tombs kind "path"), so a sync cannot
put it back: the cloud row is marked deleted, and a pull skips a path whose
note is newer than the row. A recording that lost its last path on the share
is not deleted -- its bad channels, layers and decisions stay -- and says
which archive it went into (`archived_in`).
"""
from __future__ import annotations

import hashlib
import re

UNC = "\\\\netfiles03.uvm.edu\\bigdata_jbarry"
ROOT = "/netfiles/bigdata_jbarry"

# Spellings of the share's root, lower-cased, longest first.
_PREFIXES = (
    "\\\\netfiles03.uvm.edu\\bigdata_jbarry\\",
    "\\\\netfiles03\\bigdata_jbarry\\",
    "//netfiles03.uvm.edu/bigdata_jbarry/",
    "//netfiles03/bigdata_jbarry/",
)
_FILE = re.compile(r"\.(mat|ncs|nev|nse|ntt|xlsx|xls|csv|txt|png|pdf|json)$",
                   re.I)
_TEMP = re.compile(r"\\appdata\\local\\temp\\|[\\/]barry_fakedrive", re.I)

REASONS = {
    "gone": "no longer on netfiles",
    "archived": "on netfiles only inside an archive now",
    "temp": "a test's temporary folder",
    "file": "a file, not a recording folder",
}


def tail_of(path, tops=None):
    """The part of a netfiles path under the share's root, backslashed, or
    None when `path` is not on the share.

    `Y:` counts only when what follows it is a folder the share has had at
    its top (`tops`): a drive letter is not a portable fact, and `Y:` on one
    rig need not be `Y:` on another -- but `Y:\\ProcessedPtenData` is a
    folder that exists in exactly one place.
    """
    p = str(path or "")
    low = p.lower()
    for pre in _PREFIXES:
        if low.startswith(pre):
            return p[len(pre):].replace("/", "\\").rstrip("\\")
    if tops and re.match(r"^[a-z]:\\", low):
        rest = p[3:].rstrip("\\")
        top = rest.split("\\", 1)[0].lower()
        if top in tops:
            return rest
    return None


def unc_of(tail):
    return UNC + "\\" + tail


def remote_of(tail):
    return ROOT + "/" + tail.replace("\\", "/")


def tops_of(records, inventory):
    """Every folder the share has had at its top, lower-cased: from the walk
    (what is there now) and from UNC spellings on record (what was)."""
    out = set()
    for row in inventory or []:
        rest = str(row.get("path") or "")[len(ROOT) + 1:]
        if rest:
            out.add(rest.split("/", 1)[0].lower())
    for rec in records or []:
        for p in rec.get("paths") or []:
            t = tail_of(p)
            if t:
                out.add(t.split("\\", 1)[0].lower())
    return out


def to_check(records, inventory):
    """The netfiles tails on record that the walk did not list -- the only
    ones whose existence is a question. A folder the walk listed is there;
    one it did not may be gone, or may be a folder that is not a recording
    (`PTEN_CSDsEtc\\...`), and only the cluster can say which."""
    tops = tops_of(records, inventory)
    live = {str(r.get("path") or "")[len(ROOT) + 1:].replace("/", "\\").lower()
            for r in inventory or []}
    out = set()
    for rec in records or []:
        for p in rec.get("paths") or []:
            t = tail_of(p, tops)
            if t and t.lower() not in live:
                out.add(t)
    return sorted(out)


def archive_for(tail, archives):
    """The archive that swallowed `tail`, if one is named after a folder on
    its way: `Jeremy3\\HeadfixPilot\\M2_PTENCTL\\...` went into
    `Jeremy3\\HeadfixPilot\\M2_PTENCTL.tar.xz`."""
    parts = tail.split("\\")
    have = {a.lower(): a for a in archives or []}
    for i in range(len(parts), 0, -1):
        cand = "\\".join(parts[:i]) + ".tar.xz"
        if cand.lower() in have:
            return have[cand.lower()]
    return None


def plan(records, inventory, match, gone=None, archives=None):
    """What a tidy would change, per recording. Writes nothing.

    `match(row)` is the app's one rule for which recording a walked folder
    is (a record, or None). `gone` is the set of tails the cluster said are
    not there (`vacc.missing`), lower-cased; None means it was not asked, and
    then nothing on the share is dropped.
    """
    tops = tops_of(records, inventory)
    gone = {g.lower() for g in (gone or [])} if gone is not None else None
    live = {}
    for row in inventory or []:
        tail = str(row.get("path") or "")[len(ROOT) + 1:].replace("/", "\\")
        if tail:
            live[tail.lower()] = tail
    learned = {}
    for row in inventory or []:
        rec = match(row)
        if rec is not None and rec.get("gid"):
            tail = str(row.get("path") or "")[len(ROOT) + 1:].replace("/", "\\")
            learned.setdefault(rec["gid"], []).append(unc_of(tail))

    rows = []
    counts = {"add": 0, "drop": 0, "records": 0, "emptied": 0,
              "by_reason": {}, "by_project": {}, "archives": {}}
    for rec in records or []:
        gid = rec.get("gid")
        if not gid or rec.get("retired"):
            continue
        paths = list(rec.get("paths") or [])
        have = {p.lower() for p in paths}
        add = [u for u in dict.fromkeys(learned.get(gid) or [])
               if u.lower() not in have]
        drop = []
        archived = []
        for p in paths:
            if p.startswith("vacc:"):
                continue                       # a cluster-only record's mark
            if _TEMP.search(p):
                drop.append([p, "temp"])
                continue
            if _FILE.search(p):
                drop.append([p, "file"])
                continue
            t = tail_of(p, tops)
            if t is None or t.lower() in live or gone is None:
                continue
            if t.lower() in gone:
                arch = archive_for(t, archives)
                if arch:
                    archived.append(arch)
                drop.append([p, "archived" if arch else "gone"])
        if not add and not drop:
            continue
        left = [p for p in paths if p not in {d[0] for d in drop}] + add
        row = {"gid": gid, "label": rec.get("label") or rec.get("key"),
               "project": rec.get("project") or "Unfiled",
               "key": rec.get("key"), "add": add, "drop": drop,
               "archived_in": sorted(set(archived)),
               "emptied": not [p for p in left if not p.startswith("vacc:")]}
        rows.append(row)
        counts["records"] += 1
        counts["add"] += len(add)
        counts["drop"] += len(drop)
        counts["emptied"] += 1 if row["emptied"] else 0
        proj = counts["by_project"].setdefault(row["project"],
                                               {"add": 0, "drop": 0})
        proj["add"] += len(add)
        proj["drop"] += len(drop)
        for _p, why in drop:
            counts["by_reason"][why] = counts["by_reason"].get(why, 0) + 1
        for a in row["archived_in"]:
            top = "\\".join(a.split("\\")[:2])
            counts["archives"][top] = counts["archives"].get(top, 0) + 1
    from . import natsort
    rows.sort(key=lambda r: natsort.keys(r["project"], r["label"] or ""))
    counts["checked"] = gone is not None
    counts["digest"] = digest(rows)
    return {"rows": rows, **counts}


def digest(rows):
    h = hashlib.sha1()
    for r in rows or []:
        h.update(("%s|%s|%s\n" % (r["gid"], ",".join(r["add"]),
                                  ",".join(p for p, _w in r["drop"])))
                 .encode("utf-8"))
    return h.hexdigest()[:16]
