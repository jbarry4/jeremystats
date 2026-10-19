"""
guides.py -- named depth lines, drawn across every panel that has a depth.

WHAT A GUIDE IS, AND WHY IT IS NOT A LAYER
==========================================
StrataScope answers "which anatomical layer is each contact in" and stores a
region per contact. That is a claim about the whole shank, made once, and it
is the right shape for anatomy.

A guide is the other thing people do with a depth axis: put a line at
CSC30, call it "hilus", and then look at every panel to see whether the sink
lands on it. It is a working aid rather than a finding -- it moves while
somebody is deciding, it may be provisional, and there may be one of them
rather than sixty-four. Forcing that through a per-contact region assignment
would mean relabelling four contacts to move a line by one.

So they are their own record. A recording can have both, they do not interact,
and neither is derived from the other.

WHY THEY ARE KEPT WITH THE RECORDING
====================================
A guide is a fact somebody worked out about this probe in this animal -- where
the hilus is, where the granule layer starts. It outlives the parameter sweep
that was running when it was drawn, and it is worth the next person's time.
The standalone workbench kept them in a JSON file beside the event bank, where
nothing else could find them and a second tool would have had to know that
filename; here they are keyed on the recording's global id, like everything
else that is a fact about a recording.

MERGING
=======
`BYID`, as bookmarks are. Two people drawing different guides on the same
shank both keep theirs, and moving one is an edit to that guide rather than a
replacement of the set -- which is what LWW over the whole list would have
made it, with the later writer's list silently winning.
"""
from __future__ import annotations

import os
import time
import uuid

from . import shards

# How many a recording may carry.
#
# Not a storage limit -- they are a few dozen bytes each. It is a legibility
# one: past about this many the panels are more line than data, and the
# thing they are drawn on top of stops being readable. The standalone
# workbench settled on the same number for the same reason.
MAX_GUIDES = 10

# The inks a guide is offered, in the order they are handed out.
#
# NOT the class colours. `dspca.CLASS_COLORS` starts green, purple -- DS1 and
# DS2 -- and a guide in either of those reads as a finding about one of them
# rather than as the landmark both are being measured against. So no green
# and no purple here.
#
# They also have to hold against a jet colormap, which runs dark blue to dark
# red and defeats any single ink on its own. Each line is drawn over a white
# halo for that reason; these are the mid-tones that stay legible on top of
# it in both themes.
#
# The first version used one near-black for every guide, which was invisible
# on the dark theme and made two guides indistinguishable from each other on
# every theme.
PALETTE = [
    "#e5484d",   # red
    "#ffb81c",   # amber
    "#0ea5e9",   # sky
    "#f97316",   # orange
    "#ec4899",   # pink
    "#14b8a6",   # teal
    "#a16207",   # bronze
    "#64748b",   # slate
]

DEFAULT_COLOR = PALETTE[0]


def next_color(taken):
    """The first ink nobody on this recording is using, else round the bend."""
    used = {str(c).lower() for c in (taken or [])}
    for c in PALETTE:
        if c not in used:
            return c
    return PALETTE[len(used) % len(PALETTE)]


class GuideError(Exception):
    """Something a person can fix, said in a sentence."""


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Guides:
    def __init__(self, logs_dir, store):
        self.dir = os.path.join(logs_dir, "guides")
        self.book = shards.Book(self.dir, {
            "guides": shards.BYID,
            "gid": shards.FIRST,
            "created": shards.FIRST,
        }, store)
        self.store = store
        os.makedirs(self.dir, exist_ok=True)

    def base(self, gid):
        return shards.safe_base(gid)

    #: What the first version handed every guide. Near-black, which was
    #: invisible on the dark theme and made two guides indistinguishable on
    #: every theme.
    LEGACY_COLOR = "#101010"

    def get(self, gid):
        """Every guide on this recording, shallowest first.

        Guides written before there was a palette carry the one near-black
        that every one of them got. That was a default nobody chose, so it is
        replaced on the way out rather than preserved -- by position, so it
        is stable across reads and two guides do not swap inks between one
        look and the next. A colour somebody actually picked is left alone.
        """
        rec = self.book.read(self.base(gid)) or {}
        out = [g for g in (rec.get("guides") or []) if g.get("csc") is not None]
        out.sort(key=lambda g: int(g["csc"]))
        for i, g in enumerate(out):
            if str(g.get("color", "")).lower() in ("", self.LEGACY_COLOR):
                g["color"] = PALETTE[i % len(PALETTE)]
        return out

    def all(self):
        return self.book.all()

    def _write(self, gid, guides, label=None):
        rec = self.book.read(self.base(gid)) or {}
        rec["gid"] = gid
        if label and not rec.get("session_label"):
            rec["session_label"] = label
        rec["guides"] = guides
        rec.setdefault("created", self.store.provenance()
                       if self.store else {"at": _now()})
        rec["updated"] = (self.store.provenance() if self.store
                          else {"at": _now()})
        self.book.write(self.base(gid), rec)
        return self.get(gid)

    @shards.atomic
    def put(self, gid, csc, label=None, color=None, guide_id=None,
            session_label=None):
        """Add a guide, or move and rename one that is already there.

        One entry point for both, because they are the same gesture from the
        panel's side: a line appears where you put it and stays where you
        drag it. `guide_id` is what tells them apart, and it is minted here
        rather than by the caller so two machines cannot mint the same one.
        """
        try:
            csc = int(round(float(csc)))
        except (TypeError, ValueError):
            raise GuideError("A guide sits on a contact, so it needs a "
                             "contact number.")
        got = self.get(gid)
        by_id = {g.get("id"): g for g in got}
        if guide_id and guide_id in by_id:
            g = by_id[guide_id]
            g["csc"] = csc
            # `None` means "leave it alone", which is what a drag sends:
            # moving a line is not renaming it. An empty string is a real
            # value and does clear the name -- defaulting this to "" was how
            # dragging a guide silently wiped what it was called.
            if label is not None:
                g["label"] = str(label)
            if color:
                g["color"] = str(color)
            g["moved"] = self.store.provenance() if self.store else {"at": _now()}
            return self._write(gid, got, session_label)

        if len(got) >= MAX_GUIDES:
            raise GuideError(
                "%d guides is the limit on one recording. Past that the "
                "panels are more line than data. Clear one first."
                % MAX_GUIDES)
        got.append({
            "id": uuid.uuid4().hex[:8],
            "csc": csc,
            "label": str(label or ""),
            # Handed out rather than defaulted, so two guides on one probe
            # are never the same colour unless somebody asked for that.
            "color": str(color or next_color([g.get("color") for g in got])),
            "added": self.store.provenance() if self.store else {"at": _now()},
        })
        return self._write(gid, got, session_label)

    @shards.atomic
    def remove(self, gid, guide_id):
        got = self.get(gid)
        left = [g for g in got if g.get("id") != guide_id]
        if len(left) == len(got):
            raise GuideError("There is no guide %s on this recording."
                             % guide_id)
        return self._write(gid, left)

    @shards.atomic
    def clear(self, gid):
        return self._write(gid, [])
