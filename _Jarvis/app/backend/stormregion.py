"""
stormregion.py -- a KCNT1 dual recording, one array at a time.

2026-11-20: "an option to The Storm toolkits (Doppler, Spotter, Eye) so if a
KCNT1 HIP/M2 recording is received you get to choose to process HIP, M2 or
both and if both is chosen it creates two separate data banks and basically
the data bank git view gets two branching trees."

A dual recording is two probes in two places (probes.py, DUAL_COLUMNS): a
line of contacts in hippocampus on CSC 1-64 and another in M2 on 65-128.
Everything The Storm does is about ONE line of contacts -- a CSD down it,
a common reference over it, a discharge that shows on seven of its
channels -- so each array is its own question, and its own bank entry with
its own history.

Where the split is made
-----------------------
  Doppler   before the run: the region is a channel range, so nothing on
            the other array is read at all. "Both" is two runs, and each
            banks itself as its own entry, named with its region.
  Spotter / Eye
            on an entry that covers both arrays (a run made before this, or
            on every channel): `split` files one new entry per region, from
            the events whose peak channel is on that array, with the
            decisions already made kept. Each new entry starts its own
            version tree; the parent is named in its first version's note
            and in `source.parameters.split_from`.

Which array is which comes from the recording's own banks (a person said,
or picking the dual template said), never from a channel count: banks_for
refuses to guess, and so does this.
"""
from __future__ import annotations

from . import probes

#: Region id -> (what it is called, its short name).
NAMES = {"hip": ("Hippocampus", "HIP"), "m2": ("M2", "M2")}
_WORDS = {
    "hip": {"hippocampus", "hippocampal", "hip", "hpc", "hippo", "ca1",
            "dentate", "dg"},
    "m2": {"m2", "secondary motor cortex", "motor cortex m2", "cortex m2",
           "mos"},
}


def which(name):
    """'hip', 'm2' or None for a region somebody wrote down."""
    s = " ".join(str(name or "").lower().replace("_", " ").split())
    for rid, words in _WORDS.items():
        if s in words:
            return rid
    return None


def _row(rid, first, last):
    label, short = NAMES[rid]
    return {"id": rid, "label": label, "short": short,
            "first": int(first), "last": int(last)}


def regions_for(reg):
    """[hip, m2] for a recording that has both arrays named, else None.

    From its channel banks first -- what a person said about this animal --
    then from the dual template, which is a person naming the implant."""
    reg = reg or {}
    found = {}
    for b in reg.get("channel_banks") or []:
        rid = which(b.get("region"))
        if rid and rid not in found:
            try:
                found[rid] = _row(rid, b["first"], b["last"])
            except (KeyError, TypeError, ValueError):
                continue
    if str(reg.get("probe") or "").lower() == "dual":
        for col in probes.DUAL_COLUMNS:
            rid = which(col.get("region"))
            if rid and rid not in found and col.get("csc"):
                found[rid] = _row(rid, min(col["csc"]), max(col["csc"]))
    if "hip" in found and "m2" in found:
        return [found["hip"], found["m2"]]
    return None


def by_id(regions, rid):
    for r in regions or []:
        if r["id"] == rid:
            return r
    return None


def range_of(region):
    return [region["first"], region["last"]]


def for_range(regions, rng):
    """The region a channel range is exactly, or None."""
    if not regions or not rng:
        return None
    try:
        lo, hi = int(rng[0]), int(rng[1])
    except (TypeError, ValueError, IndexError):
        return None
    last = max(r["last"] for r in regions)
    for r in regions:
        top = r["last"]
        if lo == r["first"] and (hi == top or (top == last and hi >= 9999)):
            return r
    return None


def region_of(entry, regions=None):
    """Which array a bank entry is about: what it says, else the channel
    range its run was given, else None (both, or unknown)."""
    p = ((entry or {}).get("source") or {}).get("parameters") or {}
    rid = p.get("region")
    if rid in NAMES:
        return rid
    got = for_range(regions, p.get("channel_range"))
    return got["id"] if got else None


def inside(region, channel):
    try:
        return region["first"] <= int(channel) <= region["last"]
    except (TypeError, ValueError):
        return False


def split_events(events, region):
    """(the events whose peak channel is on this array, how many said no
    channel at all). An event with no channel cannot be placed and is left
    out of every region, and counted, rather than guessed."""
    kept, blind = [], 0
    for ev in events or []:
        ch = ev.get("channel")
        if ch is None:
            blind += 1
            continue
        if inside(region, ch):
            kept.append(dict(ev))
    return kept, blind


def name_with(name, region):
    """An entry's name with its region in it, once."""
    base = str(name or "").strip()
    tag = region["short"]
    if (" " + tag + " ") in (" " + base.replace("·", " ") + " "):
        return base
    return (base + "  ·  " + tag) if base else tag
