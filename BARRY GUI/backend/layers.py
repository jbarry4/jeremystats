"""
layers.py -- Which anatomical layer each channel is sitting in.

The standalone StrataScope did this against four exported PNGs: you uploaded a
voltage raster, a CSD, a multiunit plot and a theta plot, cropped each one
down to just the heatmap, and then trusted that 64 evenly spaced rows landed
on the right channels.

That crop step is the whole problem. It is fiddly, it is per-image, it has to
be redone whenever anyone re-exports, and when it is slightly wrong every
label is off by a fraction of a channel with nothing to show for it. It exists
only because a PNG has forgotten which row was which channel.

Jarvis has not forgotten. It draws those panels itself, from the recording, and
knows exactly which lane is channel 14 -- so the labels sit on channels rather
than on pixels, the alignment cannot drift, and you can pan and filter while
you label instead of labelling a frozen snapshot.

What is stored, per recording:

    labels    channel number -> region id
    regions   the vocabulary in force, copied in

Keyed by the recording's global id, so a shank labelled on the rig is the same
shank on the laptop.
"""
from __future__ import annotations

import json
import os
import time

from . import shards

SCHEMA = 1

# The hippocampal layers, in the order they are met going down a shank. Order
# matters: it is what "fill downward" follows, and what the legend reads like.
REGIONS = [
    {"id": "ca1_so", "name": "CA1 SO", "color": "#8ec5ff",
     "note": "stratum oriens"},
    {"id": "ca1_sp", "name": "CA1 SP", "color": "#FF5733",
     "note": "pyramidal layer"},
    {"id": "ca1_sr", "name": "CA1", "color": "#33FF57",
     "note": "stratum radiatum"},
    {"id": "ca1_slm", "name": "CA1 SLM", "color": "#3357FF",
     "note": "lacunosum-moleculare"},
    {"id": "dg_oml1", "name": "DG OML1", "color": "#FF33F6",
     "note": "outer molecular, upper blade"},
    {"id": "dg_mml1", "name": "DG MML1", "color": "#33FFF6",
     "note": "middle molecular, upper blade"},
    {"id": "dg_gcl1", "name": "DG GCL1", "color": "#F6FF33",
     "note": "granule cell layer, upper blade"},
    {"id": "hil", "name": "HIL", "color": "#FF8C00", "note": "hilus"},
    {"id": "dg_gcl2", "name": "DG GCL2", "color": "#8A2BE2",
     "note": "granule cell layer, lower blade"},
    {"id": "dg_mml2", "name": "DG MML2", "color": "#006400",
     "note": "middle molecular, lower blade"},
    {"id": "dg_oml2", "name": "DG OML2", "color": "#8B4513",
     "note": "outer molecular, lower blade"},
    {"id": "dg", "name": "DG", "color": "#808080",
     "note": "dentate, unspecified"},
    {"id": "out", "name": "Out of brain", "color": "#3d4a44",
     "note": "above the surface, or in white matter"},
    # The lab's feeder sheet uses two names this list had no home for.
    # Appended rather than inserted, so every id already written down keeps
    # meaning what it meant.
    {"id": "thal", "name": "THAL", "color": "#b48ead",
     "note": "thalamus"},
    {"id": "dg2", "name": "DG2", "color": "#7fb069",
     "note": "dentate, lower blade, unspecified"},
]

REGION_IDS = {r["id"] for r in REGIONS}


class LayerError(Exception):
    pass


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Layers:
    def __init__(self, logs_dir, store):
        self.dir = os.path.join(logs_dir, "layers")
        # Per machine, compiled on read: two people can label different
        # stretches of the same shank and both keep their work.
        self.book = shards.Book(self.dir, {
            "labels": shards.MAPLWW,
            "channels": shards.UNION,
            "created": shards.FIRST,
        }, store)
        self.book.absorb_legacy()
        self.store = store
        os.makedirs(self.dir, exist_ok=True)

    def base(self, gid):
        return shards.safe_base(gid)

    def path(self, gid):
        return self.book.mine(self.base(gid))

    def get(self, gid):
        return self.book.read(self.base(gid))

    def all(self):
        return self.book.all()

    def _write(self, rec):
        rec["updated"] = self.store.provenance() if self.store else {"at": _now()}
        return self.book.write(self.base(rec["gid"]), rec)

    @shards.atomic
    def ensure(self, gid, session_label=None, channels=None):
        rec = self.get(gid)
        if rec:
            return rec
        rec = {
            "schema": SCHEMA,
            "gid": gid,
            "session_label": session_label,
            # Copied in, so a set labelled last year still means what it meant
            # if the vocabulary grows.
            "regions": [dict(r) for r in REGIONS],
            # Channel NUMBER -> region id. Numbers, not row indices: a row
            # index shifts the moment even-only is toggled or a file goes
            # missing, and CSC14 is always CSC14.
            "labels": {},
            "channels": list(channels or []),
            "created": self.store.provenance() if self.store else {"at": _now()},
        }
        return self._write(rec)

    # ---------------------------------------------------------------
    # Versions
    #
    # The same shape the event bank uses, and for the same reason: a layer
    # sheet is evidence, and evidence with no history cannot be cited.
    # `snap` is the whole labels mapping rather than a diff -- a sheet is
    # sixty-four short strings, and a snapshot cannot disagree with what it
    # is a snapshot of.
    # ---------------------------------------------------------------
    def _version(self, rec, labels, note=None, by=None, v=None):
        vs = rec.get("versions") or []
        return {
            "v": v if v is not None else (
                max([x.get("v") or 0 for x in vs] or [-1]) + 1),
            "at": _now(),
            "by": by or (self.store.provenance().get("user")
                         if self.store else None),
            "machine": shards.machine_id(),
            "n": len(labels or {}),
            "note": note,
            "snap": dict(labels or {}),
        }

    @shards.atomic
    def adopt_versions(self, gid, versions):
        """Take a history down from the cloud.

        Only called when the other side has more of it than this machine --
        see _apply_layers. A history is append-only in practice, so "more
        versions" is the whole test; merging two divergent histories would
        need a rule nobody has had to write yet, and inventing one here would
        be guessing on behalf of a case that has not happened.
        """
        rec = self.get(gid)
        if not rec:
            return None
        rec["versions"] = [dict(v) for v in (versions or [])]
        return self._write(rec)

    @shards.atomic
    def snapshot(self, gid, note=None, by=None):
        """Freeze the sheet as it stands as the next version."""
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        rec.setdefault("versions", []).append(
            self._version(rec, rec.get("labels") or {}, note=note, by=by))
        return self._write(rec)

    @shards.atomic
    def import_versions(self, gid, mapping, session_label=None,
                        channels=None, note=None, by=None):
        """Create a sheet with v0 empty and v1 holding an import.

        v0 is written even though it says nothing, because "this channel was
        unlabelled before the migration" is a fact somebody will want when
        the migration turns out to have been wrong -- and a history that
        starts at the first thing anybody did cannot answer it.

        Refuses to run over a sheet somebody has already labelled by hand.
        An import is a starting point, not a correction, and quietly
        replacing real work with a spreadsheet's opinion of it is the worst
        thing this could do.
        """
        rec = self.get(gid)
        if rec and (rec.get("labels") or {}) and (rec.get("versions") or []):
            raise LayerError(
                "This sheet already has labels and a history; an import "
                "would be overwriting somebody's work.")
        if not rec:
            rec = self.ensure(gid, session_label=session_label,
                              channels=channels)
            rec = self.get(gid)

        clean = {}
        for ch, region in (mapping or {}).items():
            if region not in REGION_IDS:
                raise LayerError("%r is not one of the layers." % region)
            clean[str(int(ch))] = region

        # v0: nothing said yet. v1: what the sheet says.
        rec["versions"] = [
            self._version(rec, {}, v=0, by=by,
                          note="Before any labelling."),
        ]
        rec["labels"] = clean
        rec["versions"].append(
            self._version(rec, clean, v=1, by=by, note=note))
        if channels:
            rec["channels"] = list(channels)
        return self._write(rec)

    @shards.atomic
    def set(self, gid, channel, region):
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        ch = str(int(channel))
        if region is None or region == "":
            rec["labels"].pop(ch, None)
        else:
            if region not in REGION_IDS:
                raise LayerError("%r is not one of the layers." % region)
            rec["labels"][ch] = region
        return self._write(rec)

    @shards.atomic
    def set_many(self, gid, mapping):
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        for ch, region in (mapping or {}).items():
            key = str(int(ch))
            if region in (None, ""):
                rec["labels"].pop(key, None)
            elif region in REGION_IDS:
                rec["labels"][key] = region
        return self._write(rec)

    @shards.atomic
    def fill_down(self, gid, channels):
        """Give every unlabelled channel the label of the one above it.

        A shank passes through layers in order, so most of a sheet is the
        label above repeated. Filling down turns a dozen decisions into a
        dozen clicks instead of sixty-four.
        """
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        order = [str(int(c)) for c in (channels or rec.get("channels") or [])]
        if not order:
            raise LayerError("I do not know this recording's channel order.")
        carry = None
        n = 0
        for ch in order:
            here = rec["labels"].get(ch)
            if here:
                carry = here
            elif carry:
                rec["labels"][ch] = carry
                n += 1
        self._write(rec)
        return rec, n

    @shards.atomic
    def clear(self, gid):
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        rec["labels"] = {}
        return self._write(rec)

    def delete(self, gid):
        return bool(self.book.erase(self.base(gid)))

    # ------------------------------------------------------------------
    @shards.atomic
    def open_set(self, gid, on=True, who=None, unarchive=False):
        """Put a sheet on the workbench, or take it off.

        Closing is not archiving and it is not finishing: nothing is hidden,
        nothing is required first, and the labels are already saved. It says
        whether this is something anybody is labelling right now.

        Opening also claims the sheet if nobody has claimed it, for the same
        reason curation does: an unowned pile is a pile.
        """
        rec = self.get(gid)
        if not rec:
            raise LayerError("No layer sheet for that recording.")
        who = (who or "").strip() or \
            (self.store.provenance() if self.store else {}).get("user")
        if on:
            rec["open"] = True
            rec["opened_at"] = _now()
            rec["opened_by"] = who
            rec.pop("closed_at", None)
            # Archived and open must never both be true: the bench is the
            # open sheets and the shelf is the rest, so a sheet that is both
            # belongs to neither and disappears off both.
            if rec.get("archived"):
                if not unarchive:
                    raise LayerError(
                        "That sheet is archived. Picking it up would "
                        "un-archive it, so say so on purpose rather than by "
                        "picking it up.")
                for k in ("archived", "archived_at", "archived_by"):
                    rec.pop(k, None)
            if not (rec.get("assignee") or "").strip() and who:
                rec["assignee"] = who
        else:
            rec["open"] = False
            rec["closed_at"] = _now()
        return self._write(rec)

    @shards.atomic
    def archive(self, gid, on=True):
        """File a sheet away, or take it back out.

        Not deletion: the labels, the versions and the snapshots all stay.
        This is for the recording you have decided not to think about again,
        which the shelf should not keep offering you.
        """
        rec = self.get(gid)
        if not rec:
            raise LayerError("No layer sheet for that recording.")
        who = (self.store.provenance() if self.store else {}).get("user")
        if on:
            rec["archived"] = True
            rec["archived_at"] = _now()
            rec["archived_by"] = who
            # Off the bench as well, or it would be on a bench nobody can
            # see.
            rec["open"] = False
        else:
            for k in ("archived", "archived_at", "archived_by"):
                rec.pop(k, None)
        return self._write(rec)

    @shards.atomic
    def assign(self, gid, who):
        """Say whose sheet this is. Empty hands it back to nobody."""
        rec = self.get(gid)
        if not rec:
            raise LayerError("No layer sheet for that recording.")
        rec["assignee"] = (who or "").strip() or None
        rec["assigned_at"] = _now()
        return self._write(rec)

    @shards.atomic
    def rename(self, gid, name):
        """What this work set is called.

        A sheet is about a recording, but the work is not always "the
        recording": it can be the second pass after the probe map was
        fixed. A name is how you tell those apart in a list.
        """
        rec = self.get(gid)
        if not rec:
            raise LayerError("No layer sheet for that recording.")
        rec["name"] = (name or "").strip() or None
        return self._write(rec)

    def close_all(self):
        """Clear the bench. Nothing else changes."""
        out = []
        for rec in self.all():
            if not rec.get("open"):
                continue
            self.open_set(rec["gid"], False)
            out.append({"gid": rec["gid"],
                        "name": rec.get("name") or rec.get("session_label")})
        return out

    @staticmethod
    def progress(rec, channels=None):
        order = [str(int(c)) for c in
                 (channels or rec.get("channels") or [])]
        labels = rec.get("labels") or {}
        done = sum(1 for c in order if labels.get(c))
        by = {}
        for c in order:
            r = labels.get(c)
            if r:
                by[r] = by.get(r, 0) + 1
        return {
            "total": len(order),
            "labelled": done,
            "left": len(order) - done,
            "by_region": by,
            "percent": round(100.0 * done / len(order), 1) if order else 0.0,
        }

    def summary(self, rec):
        return {
            "gid": rec.get("gid"),
            "session_label": rec.get("session_label"),
            # The workbench half: which sheets somebody is working on, whose
            # they are, and which have been filed away. Without these the
            # list can only be "every sheet that exists", which is what it
            # was.
            "name": rec.get("name"),
            "open": bool(rec.get("open")),
            "opened_at": rec.get("opened_at"),
            "opened_by": rec.get("opened_by"),
            "closed_at": rec.get("closed_at"),
            "assignee": rec.get("assignee"),
            "archived": bool(rec.get("archived")),
            "archived_at": rec.get("archived_at"),
            "regions": rec.get("regions") or REGIONS,
            "labels": rec.get("labels") or {},
            "channels": self.covered(rec),
            "created": rec.get("created") or {},
            "updated": rec.get("updated") or {},
            "progress": self.progress(rec),
            # The history, without the snapshots.
            #
            # A snapshot is the whole channel->region mapping, and the list
            # route returns every sheet: sixty-odd sheets times sixty-four
            # entries times however many versions is a lot of bytes for a
            # list that only shows how many there are. The snapshot itself
            # comes with the single-sheet read, which is when somebody is
            # actually looking at one.
            "versions": [
                {k: v for k, v in ver.items() if k != "snap"}
                for ver in (rec.get("versions") or [])
            ],
            "n_versions": len(rec.get("versions") or []),
        }

    @staticmethod
    def covered(rec):
        """Which channels a sheet is about.

        The channel list, when it has one. Sheets written by the first
        version of the feeder import did not -- and every reader walks this
        list, so those sheets displayed and exported as empty despite
        holding sixty-three labels each. Falling back to the labelled
        channels means a sheet is never invisible just because nobody said
        how wide it was.
        """
        got = [int(c) for c in (rec.get("channels") or [])]
        if got:
            return got
        keys = []
        for k in (rec.get("labels") or {}):
            try:
                keys.append(int(k))
            except (TypeError, ValueError):
                continue
        return sorted(keys)

    def rows(self, rec):
        names = {r["id"]: r["name"] for r in (rec.get("regions") or REGIONS)}
        labels = rec.get("labels") or {}
        out = []
        for i, ch in enumerate(self.covered(rec)):
            key = str(int(ch))
            out.append({
                "gid": rec.get("gid"),
                "session": rec.get("session_label") or "",
                "row": i + 1,
                "channel": ch,
                "region": names.get(labels.get(key), ""),
                "region_id": labels.get(key) or "",
            })
        return out


CSV_COLUMNS = ("gid", "session", "row", "channel", "region", "region_id")
