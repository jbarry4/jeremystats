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

BARRY has not forgotten. It draws those panels itself, from the recording, and
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
]

REGION_IDS = {r["id"] for r in REGIONS}


class LayerError(Exception):
    pass


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Layers:
    def __init__(self, logs_dir, store):
        self.dir = os.path.join(logs_dir, "layers")
        self.store = store
        os.makedirs(self.dir, exist_ok=True)

    def path(self, gid):
        safe = "".join(c for c in str(gid) if c.isalnum() or c in "._-")
        return os.path.join(self.dir, safe + ".json")

    def get(self, gid):
        try:
            with open(self.path(gid), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def all(self):
        out = []
        for name in sorted(os.listdir(self.dir)) if os.path.isdir(self.dir) else []:
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.dir, name), "r",
                          encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except (OSError, json.JSONDecodeError):
                continue
        return out

    def _write(self, rec):
        rec["updated"] = self.store.provenance() if self.store else {"at": _now()}
        p = self.path(rec["gid"])
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, indent=2, sort_keys=True)
        os.replace(tmp, p)
        if self.store:
            self.store._stage(p)
        return rec

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

    def clear(self, gid):
        rec = self.get(gid)
        if not rec:
            raise LayerError("This recording has no layer sheet yet.")
        rec["labels"] = {}
        return self._write(rec)

    def delete(self, gid):
        try:
            os.remove(self.path(gid))
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
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
            "regions": rec.get("regions") or REGIONS,
            "labels": rec.get("labels") or {},
            "channels": rec.get("channels") or [],
            "created": rec.get("created") or {},
            "updated": rec.get("updated") or {},
            "progress": self.progress(rec),
        }

    def rows(self, rec):
        names = {r["id"]: r["name"] for r in (rec.get("regions") or REGIONS)}
        labels = rec.get("labels") or {}
        out = []
        for i, ch in enumerate(rec.get("channels") or []):
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
