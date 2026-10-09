"""
vaccfind.py -- every recording on the cluster, and which of them Jarvis has
not met yet.

WHAT THIS IS FOR

The registry is how a recording reaches every tool: a picker lists registry
rows and nothing else. So a recording that lives on the VACC and nowhere this
computer can see -- most of the lab's netfiles share, from a desk with no
`Y:` mapped -- did not exist anywhere in Jarvis, however well the cluster
could read it.

`vacc.inventory` already walks the cluster. This is the other half: take
what it found, say which folders are recordings Jarvis already knows (by
identity, the same rule as everywhere else), and turn the rest into registry
rows when somebody asks for that.

TWO KINDS OF FIND, TWO WAYS TO REGISTER

  on a mapped share   The lab's own copy, read in place. Registered with its
                      UNC spelling (`vacc.unc_for`), which is a real place in
                      the lab -- the path a scan of the share from a lab
                      computer would write -- so it is never a cluster path.

  in scratch or temp  A copy. Registered by identity alone, with no path: the
                      constitution's rule is that a cluster path never enters
                      the registry, and the copy is found again by identity
                      on every walk, the way an upload is.

NOTHING IS MINTED BY A WALK

A gid is permanent and everything in the lab hangs off it. `survey` only
describes; `register` writes, and only when a person has pressed the button
that says how many it will add. A folder that names no mouse and session is
never registered -- a record nobody could ever match is a record that exists
and cannot be found -- and neither is one that half-matches a known recording
(same mouse and session, another day or project). Those are listed with
their reason.
"""
from __future__ import annotations

import re

from . import ids, nlx, sessreg, vacc

#: What a Neuralynx channel file is made of, for turning a size into a length.
HEADER_BYTES = 16384
RECORD_BYTES = 1044
SAMPLES_PER_RECORD = 512

_FS_RE = re.compile(r"-SamplingFrequency\s+([0-9]+(?:\.[0-9]+)?)", re.I)

#: How many of each list travel to the page. The counts are always whole.
SHOWN = 60


def facts_of(row):
    """(start, fs, duration_s) from what the walk carried back. Any may be
    None: an unreadable header leaves the folder name to decide the start,
    as it always did, and no length is claimed without a rate."""
    raw = (row or {}).get("header") or ""
    start = None
    fs = None
    if raw:
        try:
            start = nlx.header_start_time(raw)
        except Exception:                                # noqa: BLE001
            start = None
        m = _FS_RE.search(raw)
        if m:
            try:
                fs = float(m.group(1))
            except ValueError:
                fs = None
    duration = None
    size = int((row or {}).get("first_ncs_bytes") or 0)
    if fs and size > HEADER_BYTES:
        n_rec = (size - HEADER_BYTES) // RECORD_BYTES
        duration = round(n_rec * SAMPLES_PER_RECORD / fs, 3)
    return start, fs, duration


def kind_of(cfg, row):
    """Where a find lives, in the words the page uses."""
    if row.get("native") or vacc.native_rule_of(cfg, row.get("path")):
        return "netfiles"
    temp = ((cfg.get("temp") or {}).get("root") or "").rstrip("/")
    if temp and str(row.get("path") or "").startswith(temp + "/"):
        return "temp"
    return "scratch"


def _tail(path, n=4):
    bits = [b for b in str(path or "").split("/") if b]
    return "/".join(bits[-n:])


def survey(found, cfg, match):
    """What the walk found, sorted into four piles. Writes nothing.

    `found` is inventory rows (`path`, `n_channels`, `first_ncs_bytes`,
    `header`, and `native` for a mapped share). `match(path, header_time)` is
    `app._cluster_match` -- the one rule for which recording a cluster folder
    is -- passed in rather than copied, so this cannot drift from it.

    Returns the counts, a sample of each pile, and in `_new` every new row
    in full for `register` (the page is sent the sample only).
    """
    matched, refused, unident = [], [], []
    groups = {}
    for row in (found or []):
        start, fs, duration = facts_of(row)
        rec, how, why = match(row["path"], start)
        kind = kind_of(cfg, row)
        if rec is not None and rec.get("gid"):
            matched.append({"gid": rec["gid"],
                            "label": rec.get("label") or rec.get("key"),
                            "how": how, "kind": kind})
            continue
        if why and how != "other-day":
            # Same mouse and session as a known recording, same day, another
            # project. Not that recording -- and not safe to mint beside it
            # either, because the store's own matcher allows two mounts of
            # one recording six hours of disagreement and may yet decide
            # they are one. A person looks.
            refused.append({"path": _tail(row["path"]), "why": why,
                            "kind": kind})
            continue
        # "other-day" falls through: same mouse and session as a known
        # recording but recorded on a different day, which in this lab --
        # numbering restarts per project, and one session folder can hold
        # several days' recordings -- is a different recording. Measured on
        # the netfiles walk, 2026-10-08: most of the refusals were this.
        ident = ids.identify(row["path"], header_time=start)
        if ident.get("mouse") is None or ident.get("session") is None:
            unident.append({"path": _tail(row["path"]), "kind": kind,
                            "why": "the folder does not name a mouse and a "
                                   "session"})
            continue
        key = ident.get("key") or ("%s|%s" % (ident.get("loose_key"),
                                              ident.get("start")))
        groups.setdefault(key, []).append(
            {"row": row, "ident": ident, "start": start, "fs": fs,
             "duration": duration, "kind": kind})

    new = []
    for key, items in groups.items():
        # One recording found in more than one place: netfiles is the lab's
        # copy and wins; two lab copies is a real ambiguity.
        lab = [x for x in items if x["kind"] == "netfiles"]
        if len(lab) > 1:
            for x in lab:
                refused.append({"path": _tail(x["row"]["path"]),
                                "kind": x["kind"],
                                "why": "%d folders on the share are this one "
                                       "recording" % len(lab)})
            continue
        pick = (lab or items)[0]
        row, ident = pick["row"], pick["ident"]
        unc = vacc.unc_for(cfg, row["path"]) if pick["kind"] == "netfiles" \
            else None
        project = sessreg.guess_project(ident, [row["path"]])
        identity = {k: ident.get(k) for k in
                    ("key", "loose_key", "mouse", "session", "group", "start",
                     "label", "phase", "phase_n", "run", "repeat",
                     "confidence")}
        if unc:
            identity["path"] = unc
        new.append({
            "identity": identity,
            "project": project,
            "channels": row.get("n_channels") or None,
            "fs": pick["fs"],
            "duration_s": pick["duration"],
            "kind": pick["kind"],
            "copies": len(items),
            # For the page only; never written.
            "remote": row["path"],
            "unc": unc,
        })
    new.sort(key=lambda r: (str(r["project"]),
                            str((r["identity"] or {}).get("mouse")),
                            str((r["identity"] or {}).get("session")),
                            str((r["identity"] or {}).get("start"))))

    by_project = {}
    for r in new:
        by_project[r["project"]] = by_project.get(r["project"], 0) + 1

    def public(r):
        i = r["identity"] or {}
        return {"key": i.get("key"), "label": i.get("label"),
                "project": r["project"], "mouse": i.get("mouse"),
                "session": i.get("session"), "start": i.get("start"),
                "channels": r["channels"], "duration_s": r["duration_s"],
                "kind": r["kind"], "copies": r["copies"],
                "where": _tail(r["remote"], 5)}

    return {
        "n_found": len(found or []),
        "n_matched": len(matched),
        "n_new": len(new),
        "n_refused": len(refused),
        "n_unidentifiable": len(unident),
        "new_by_project": by_project,
        "new": [public(r) for r in new[:SHOWN]],
        "refused": refused[:SHOWN],
        "unidentifiable": unident[:SHOWN],
        "digest": digest(new),
        "_new": new,
    }


def digest(new_rows):
    """One string naming exactly which recordings a plan would add.

    The page sends it back with the click, and the add is refused if it no
    longer matches: a walk that finished between the plan and the press
    must not add recordings nobody was shown a count for.
    """
    import hashlib
    keys = sorted(str((r.get("identity") or {}).get("key")
                      or (r.get("identity") or {}).get("loose_key") or "")
                  for r in (new_rows or []))
    return hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:16]


def register(reg, new_rows):
    """Write the new ones into the registry. Returns (new, joined)."""
    return reg.ingest_found(list(new_rows or []), via="vacc")
