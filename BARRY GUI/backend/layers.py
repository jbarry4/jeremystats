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
    # The inner third, which Method A (the molecular layer in thirds) needs a
    # name for. Inserted in depth order rather than appended: an id keeps
    # its meaning wherever it sits in the list, and the list is what the
    # legend and the number keys read down. That does move the number keys
    # from GCL1 on by one.
    {"id": "dg_iml1", "name": "DG IML1", "color": "#ffb3c6",
     "note": "inner molecular, upper blade"},
    {"id": "dg_gcl1", "name": "DG GCL1", "color": "#F6FF33",
     "note": "granule cell layer, upper blade"},
    {"id": "hil", "name": "HIL", "color": "#FF8C00", "note": "hilus"},
    {"id": "dg_gcl2", "name": "DG GCL2", "color": "#8A2BE2",
     "note": "granule cell layer, lower blade"},
    {"id": "dg_iml2", "name": "DG IML2", "color": "#c9a227",
     "note": "inner molecular, lower blade"},
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
REGION_ORDER = {r["id"]: i for i, r in enumerate(REGIONS)}

# What StrataScope's steps keep on a sheet, beside the labels. Separate
# fields rather than one block, so the shard merge treats them separately:
# one person painting Theta Walk on the rig and another adjusting a
# confidence on the laptop both keep their change.
#
#   strata_states      {"theta_walk": [[t0, t1], ...]}  painted by hand
#   strata_wheel       [{"t0", "t1", "note"}]           typed from the notes
#   strata_params      spacing, species, thresholds, reference channel ...
#   strata_confidence  line id ("ca1_sp|ca1_sr") -> sure / likely / guess
#   strata_steps       "0".."4" -> {status, at, by, basis}
#   strata_anchors     sp, fissure_at, gcl1, gcl2 (channel numbers)
#   strata_checks      the sanity checks as they stood at sign-off
#   strata_signed      {by, at, v} for the last sign-off
STRATA_FIELDS = ("strata_states", "strata_wheel", "strata_params",
                 "strata_confidence", "strata_steps", "strata_anchors",
                 "strata_checks", "strata_signed")
STRATA_MAPS = ("strata_params", "strata_confidence", "strata_steps",
               "strata_anchors")
STRATA_DICTS = STRATA_MAPS + ("strata_states", "strata_signed")
CONFIDENCE = ("sure", "likely", "guess")


class LayerError(Exception):
    pass


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Layers:
    def __init__(self, logs_dir, store):
        self.dir = os.path.join(logs_dir, "layers")
        # Per machine, compiled on read: two people can label different
        # stretches of the same shank and both keep their work.
        spec = {
            "labels": shards.MAPLWW,
            "channels": shards.UNION,
            "created": shards.FIRST,
        }
        spec.update({k: shards.MAPLWW for k in STRATA_MAPS})
        self.book = shards.Book(self.dir, spec, store)
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
            # index shifts the moment a file goes missing, and CSC14 is
            # always CSC14.
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
    def _version(self, rec, labels, note=None, by=None, v=None, extra=None):
        vs = rec.get("versions") or []
        out = {
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
        # A signed-off sheet keeps HOW it was decided beside what was
        # decided: the parameters, the confidence per line, the anchors and
        # the checks as they stood. A version that says "CA1 SP" without
        # saying it was a guess is the label without the evidence.
        if extra:
            out["strata"] = dict(extra)
        return out

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
    def snapshot(self, gid, note=None, by=None, extra=None):
        """Freeze the sheet as it stands as the next version."""
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        rec.setdefault("versions", []).append(
            self._version(rec, rec.get("labels") or {}, note=note, by=by,
                          extra=extra))
        return self._write(rec)

    # ---------------------------------------------------------------
    # StrataScope's steps
    # ---------------------------------------------------------------
    @staticmethod
    def strata_of(rec):
        """The steps' fields, with empty defaults, under their short names."""
        out = {}
        for k in STRATA_FIELDS:
            v = rec.get(k)
            if v is None:
                v = {} if k in STRATA_DICTS else []
            out[k[len("strata_"):]] = v
        return out

    @shards.atomic
    def set_strata(self, gid, patch):
        """Change some of the steps' fields.

        A map field (params, confidence, steps, anchors) is merged key by
        key, and a key set to None is removed. Anything else is replaced
        whole. Keys are the short names: "states", "params" ...
        """
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        self._patch_strata(rec, patch)
        return self._write(rec)

    def _patch_strata(self, rec, patch):
        if patch:
            # When any of the steps' fields last changed -- what a cloud pull
            # compares to decide whose copy is newer (cloudsync._apply_layers).
            rec["strata_updated"] = shards._now()
        for short, value in (patch or {}).items():
            field = "strata_" + str(short)
            if field not in STRATA_FIELDS:
                raise LayerError("%r is not something a sheet keeps." % short)
            if field == "strata_confidence":
                for _k, lvl in (value or {}).items():
                    if lvl is not None and lvl not in CONFIDENCE:
                        raise LayerError("Confidence is sure, likely or "
                                         "guess, not %r." % lvl)
            if field == "strata_states":
                value = _clean_states(value)
            if field in STRATA_MAPS:
                cur = dict(rec.get(field) or {})
                for k, v in (value or {}).items():
                    if v is None:
                        cur.pop(str(k), None)
                    else:
                        cur[str(k)] = v
                rec[field] = cur
            else:
                rec[field] = value

    @shards.atomic
    def adopt_strata(self, gid, strata, at):
        """Take the steps' fields down from the cloud, whole.

        Only called when the cloud's copy is newer than this machine's
        (cloudsync._apply_layers). Stamped with the cloud's time, not now:
        stamping it now would make this machine's copy look like the newer
        one and push it straight back up, the loop the roster was stuck in.
        """
        rec = self.get(gid)
        if not rec:
            return None
        for short, value in (strata or {}).items():
            field = "strata_" + str(short)
            if field in STRATA_FIELDS:
                rec[field] = value
        rec["strata_updated"] = at
        return self._write(rec)

    @shards.atomic
    def apply_step(self, gid, labels=None, strata=None):
        """Accept a step: its labels and its bookkeeping in one write, so a
        sheet can never hold a step's lines without the step saying so, or
        the other way round."""
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        for ch, region in (labels or {}).items():
            key = str(int(ch))
            if region in (None, ""):
                rec["labels"].pop(key, None)
            elif region in REGION_IDS:
                rec["labels"][key] = region
            else:
                raise LayerError("%r is not one of the layers." % region)
        self._patch_strata(rec, strata or {})
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
            "regions": regions_for(rec),
            "labels": rec.get("labels") or {},
            "strata": self.strata_of(rec),
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
        names = {r["id"]: r["name"] for r in regions_for(rec)}
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


def regions_for(rec):
    """The vocabulary a sheet is labelled in, in depth order.

    The sheet's own copy wins for every id it has -- that copy is what makes
    a sheet labelled last year still mean what it meant -- and ids added to
    the vocabulary since (IML1 and IML2) are filled in from the current one,
    so an old sheet can use them. Ordered by the current list, with any id
    the current list does not know kept at the end.
    """
    own = {r.get("id"): r for r in (rec.get("regions") or []) if r.get("id")}
    out = [dict(own.get(r["id"]) or r) for r in REGIONS]
    out += [dict(r) for i, r in own.items() if i not in REGION_ORDER]
    return out


def _clean_states(value):
    """Theta Walk bouts as sorted, merged [t0, t1] pairs in seconds."""
    out = {}
    for name, bouts in (value or {}).items():
        got = []
        for b in bouts or []:
            try:
                t0, t1 = float(b[0]), float(b[1])
            except (TypeError, ValueError, IndexError):
                continue
            if t1 - t0 > 0:
                got.append([round(min(t0, t1), 3), round(max(t0, t1), 3)])
        got.sort()
        merged = []
        for t0, t1 in got:
            if merged and t0 <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], t1)
            else:
                merged.append([t0, t1])
        out[str(name)] = merged
    return out
