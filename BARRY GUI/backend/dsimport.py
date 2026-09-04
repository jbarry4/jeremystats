"""
dsimport.py -- read a folder of sorted dentate-spike snapshots back in.

The curation that already happened
----------------------------------
Before BARRY there was a folder per recording full of one PNG per candidate
spike, and sorting meant dragging those PNGs into subfolders named after the
decision. Thousands of candidates were sorted that way. That work is real
and it is not going to be redone, so it has to come back in.

    <run>/
      M13_HF4s17aug4/                 one recording, name written by hand
        Raster_Evt001_1ch.png         every candidate, numbered, never moved
        Raster_Evt002_1ch.png
        ...
        Dentate Spike/                a copy in here means "yes"
        Garbage/                      ...means "no"
        Flag/                         ...means "come back to this"
        Flag for Deep Review/         ...means "come back to this properly"

The four folder names map one-for-one onto the dentate-spike vocabulary in
curation.py, so nothing has to be invented.

What the images do not have is a time. `Evt007` says which candidate it is,
not when. The times come from the Event Bank entry for the same recording,
matched by position: Evt001 is the first banked candidate, Evt002 the
second. That is only safe because the counts agree exactly -- checked for
every folder, and a folder whose count disagrees is reported and skipped
rather than imported half-right. On the run this was written for, 41 of 42
folders matched to the event and the 42nd was empty.

Folder names are not standardised (`M1ptens2oct2`, `m33s4jun14`,
`M11_HF2_s10jul25`), but they are all parsable: the first m<number> is the
mouse and the first s<number> is the session. The date fragment on the end
is ignored -- mouse and session already identify the recording, and the
fragments are inconsistent about format.
"""
from __future__ import annotations

import collections
import os
import re

# Folder name -> label id in curation.KINDS["ds"].
FOLDER_LABELS = {
    "dentate spike": "spike",
    "dentate spikes": "spike",
    "spike": "spike",
    "garbage": "garbage",
    "trash": "garbage",
    "flag": "flag",
    "flag for deep review": "review",
    "deep review": "review",
    "review": "review",
}

# What a conflict becomes. An event filed under two different decisions is
# not a decision, and quietly picking one would bury exactly the cases a
# person needs to look at again.
CONFLICT_LABEL = "flag"

_EVT = re.compile(r"evt[^0-9]?(\d+)", re.I)
_MOUSE = re.compile(r"[mM](\d+)")
_SESSION = re.compile(r"[sS](\d+)")


def parse_folder(name):
    """Mouse and session out of a hand-written folder name."""
    m = _MOUSE.search(name or "")
    s = _SESSION.search(name or "")
    return {
        "folder": name,
        "mouse": int(m.group(1)) if m else None,
        "session": int(s.group(1)) if s else None,
    }


def event_number(filename):
    m = _EVT.search(filename or "")
    return int(m.group(1)) if m else None


def read_folder(path):
    """What one recording's folder says: every event, and its decision.

    Returns {n_root, events: {number: label|None}, conflicts, unnumbered,
    filed_not_in_root}. A number present in the root with no copy in any
    label folder is undecided, which is a real state and not an error.
    """
    root_nums = {}
    unnumbered = []
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if os.path.isdir(full) or not name.lower().endswith(".png"):
            continue
        num = event_number(name)
        if num is None:
            unnumbered.append(name)
            continue
        root_nums[num] = name

    placed = collections.defaultdict(set)
    unknown_folders = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if not os.path.isdir(full):
            continue
        label = FOLDER_LABELS.get(name.strip().lower())
        if label is None:
            unknown_folders.append(name)
            continue
        for fn in os.listdir(full):
            if not fn.lower().endswith(".png"):
                continue
            num = event_number(fn)
            if num is None:
                unnumbered.append(os.path.join(name, fn))
                continue
            placed[num].add(label)

    events, conflicts, notes = {}, [], {}
    for num in sorted(root_nums):
        labs = placed.get(num) or set()
        if len(labs) > 1:
            # Two different decisions for one candidate. Flagged, named in
            # the report, and the reason written onto the event -- otherwise
            # whoever reviews it sees a flag with no idea why.
            conflicts.append({"event": num, "labels": sorted(labs)})
            events[num] = CONFLICT_LABEL
            notes[num] = ("Filed under " + " and ".join(sorted(labs))
                          + " when sorted, so it needs deciding.")
        elif labs:
            events[num] = next(iter(labs))
        else:
            events[num] = None

    filed_not_in_root = sorted(n for n in placed if n not in root_nums)
    return {
        "n_root": len(root_nums),
        "events": events,
        "notes": notes,
        "conflicts": conflicts,
        "unnumbered": unnumbered,
        "unknown_folders": unknown_folders,
        "filed_not_in_root": filed_not_in_root,
        "contiguous": (sorted(root_nums) ==
                       list(range(1, len(root_nums) + 1)) if root_nums else True),
    }


def _tally(events):
    out = collections.Counter()
    for lab in events.values():
        out[lab or "undecided"] += 1
    return dict(out)


def scan(root, bank, kind="ds"):
    """Look at every folder under `root` and say what would be imported.

    Nothing is written. This is the half you read before letting it run --
    which folder goes to which recording, how many candidates, how they were
    sorted, and every reason a folder cannot be imported.
    """
    if not os.path.isdir(root):
        raise ValueError("No such folder: %s" % root)

    by_ms = collections.defaultdict(list)
    for e in bank.summaries():
        if e.get("type") == kind:
            by_ms[(e.get("mouse"), e.get("session"))].append(e)

    out = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        row = parse_folder(name)
        try:
            read = read_folder(path)
        except OSError as exc:
            row.update(verdict="unreadable", reason=str(exc))
            out.append(row)
            continue
        row.update(
            n_images=read["n_root"],
            tally=_tally(read["events"]),
            conflicts=read["conflicts"],
            _notes=read["notes"],
            unnumbered=len(read["unnumbered"]),
            unknown_folders=read["unknown_folders"],
            filed_not_in_root=read["filed_not_in_root"],
            contiguous=read["contiguous"],
        )

        if not read["n_root"]:
            row.update(verdict="empty",
                       reason="No numbered snapshots in this folder.")
            out.append(row)
            continue
        if row["mouse"] is None or row["session"] is None:
            row.update(verdict="unparsed",
                       reason="Could not read a mouse and session out of the "
                              "folder name.")
            out.append(row)
            continue

        cands = by_ms.get((row["mouse"], row["session"]), [])
        if not cands:
            row.update(verdict="no-bank",
                       reason="Nothing of that kind is banked for m%s s%s, so "
                              "there are no times to attach these decisions "
                              "to." % (row["mouse"], row["session"]))
            out.append(row)
            continue

        # Prefer an entry whose count matches; the position join needs it.
        exact = [e for e in cands if e.get("n") == read["n_root"]]
        pick = (exact or cands)[0]
        row.update(entry_id=pick.get("id"), gid=pick.get("gid"),
                   session_label=pick.get("session_label"),
                   entry_name=pick.get("name"), bank_n=pick.get("n"),
                   candidates=len(cands))
        if not exact:
            row.update(verdict="count-mismatch",
                       reason="%d snapshots but %d banked candidates. These "
                              "are matched by position, so a difference means "
                              "the decisions would land on the wrong events."
                              % (read["n_root"], pick.get("n")))
            out.append(row)
            continue
        if not read["contiguous"]:
            row.update(verdict="gappy",
                       reason="The snapshot numbers are not 1..%d without "
                              "gaps, so position cannot be trusted."
                              % read["n_root"])
            out.append(row)
            continue
        if not pick.get("gid"):
            row.update(verdict="no-gid",
                       reason="That banked entry has no recording id.")
            out.append(row)
            continue

        row.update(verdict="ready", _events=read["events"])
        out.append(row)

    return out


def summary(rows):
    out = collections.Counter()
    for r in rows:
        out[r.get("verdict")] += 1
        for k, v in (r.get("tally") or {}).items():
            out["events_" + k] += v
    out["folders"] = len(rows)
    out["conflicts"] = sum(len(r.get("conflicts") or []) for r in rows)
    return dict(out)


def apply(rows, bank, curation, kind="ds", replace=True, who=None):
    """Write the ready rows in as curation sets.

    `replace` is on by default and is the honest choice: this is the record
    of a sort that already happened, so it should land as itself rather than
    being merged into whatever half-finished set happens to exist. Anything
    not marked ready in the scan is skipped, and says why.
    """
    done, skipped = [], []
    for row in rows:
        if row.get("verdict") != "ready":
            skipped.append({"folder": row.get("folder"),
                            "verdict": row.get("verdict"),
                            "reason": row.get("reason")})
            continue
        full = bank.get(row["entry_id"]) or {}
        banked = full.get("events") or []
        marks = row.get("_events") or {}
        if len(banked) != len(marks):
            skipped.append({"folder": row.get("folder"),
                            "verdict": "count-mismatch",
                            "reason": "The entry changed between scanning and "
                                      "importing."})
            continue

        events = []
        for i, ev in enumerate(banked, start=1):
            item = {"start": ev.get("start")}
            lab = marks.get(i)
            if lab:
                item["label"] = lab
            note = (row.get("_notes") or {}).get(i)
            if note:
                item["note"] = note
            events.append(item)

        rec, n, _extra = curation.create(
            row["gid"], kind, events,
            name=row.get("folder"),
            source={"kind": "snapshot folders", "folder": row.get("folder"),
                    "bank_entry": row.get("entry_id"), "by": who or ""},
            session_label=row.get("session_label"),
            replace=replace)
        prog = rec.get("progress") or {}
        done.append({"folder": row.get("folder"), "gid": row["gid"],
                     "session_label": row.get("session_label"),
                     "n": len(events), "tally": row.get("tally"),
                     "conflicts": len(row.get("conflicts") or []),
                     "progress": prog})
    return {"imported": done, "skipped": skipped}
