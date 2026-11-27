"""The recordings Sextant places: the Extraction Room's, one a mouse.

The 8 controls and 9 PTEN mice of the DS/PTEN pilot (room set v6, the Halo
set), each by the one recording the room reads. m6 is left out under the
user's standing rule ("exclude m6 from everything", 2026-11-17). m51 is in:
it is out of the DS statistics for having five events, but a placement does
not need dentate spikes.

Each mouse's hemisphere is the lab's feeder sheet's
(EEGData_FeederSheet_PTEN_with_DKO.xlsx, as filed on the session record).
The lab usually moves the probe between sessions, so a placement belongs to
one recording, never to a mouse.
"""
from __future__ import annotations

import glob
import json
import os

# (mouse, group, gid) -- the room's recording for each mouse.
COHORT = [
    ("m2", "CTL", "s79ba9ba163c4"),
    ("m21", "CTL", "s37c7c8edfe10"),
    ("m22", "CTL", "s0a9e96cf1739"),
    ("m26", "CTL", "s016e132432c8"),
    ("m51", "CTL", "sd94396e874c7"),
    ("m59", "CTL", "sd42a6992b76c"),
    ("m60", "CTL", "s8d7f397b9708"),
    ("m61", "CTL", "s43b16cd74bcb"),
    ("m8", "PTEN", "sba57286bdee3"),
    ("m33", "PTEN", "s6cdd64d005c4"),
    ("m1", "PTEN", "s45bae70722f2"),
    ("m13", "PTEN", "s38b9e61c5684"),
    ("m28", "PTEN", "s4a67210fc7ac"),
    ("m7", "PTEN", "s500a5aec223e"),
    ("m3", "PTEN", "sd0d0bded958b"),
    ("m5", "PTEN", "sc74c98b2495d"),
    ("m34", "PTEN", "s14510e30e1bd"),
]

# The craniotomy, as the user gave it (2026-11-27): "AP -2.2 mm, ML +/-1.4
# mm from bregma. But it can vary a lot." A loose prior, never a constraint.
CRANIOTOMY = {"ap_mm": -2.2, "ml_mm": 1.4}

# The PTEN mice's knockout and P-spike status, as the Extraction Room has
# them (backend/extraction.py KO_SHEET / IED_SHEET).
KO = {"m7": 24.12, "m8": 3.89, "m1": 5.18, "m33": 4.41, "m34": 28.43,
      "m13": 18.87, "m3": 24.57, "m5": 27.64, "m28": 20.19}
PSPIKES = {"m7": False, "m8": False, "m1": False, "m33": False,
           "m34": True, "m13": True, "m3": True, "m5": True, "m28": True}

PROBE = {"name": "H3", "n": 64, "pitch_um": 20.0}


def _session_records(logs_dir, gid):
    out = []
    for f in glob.glob(os.path.join(logs_dir, "sessions", "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if d.get("gid") == gid:
            out.append(d)
    return out


def _layer_channels(logs_dir, gid):
    """The probe's channel order (CSC numbers, top first) as StrataScope
    files it. Only the order is read -- never the labels."""
    best = None
    for f in glob.glob(os.path.join(logs_dir, "layers", gid + "@*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        u = str(d.get("updated") or "")
        if best is None or u > best[0]:
            best = (u, d.get("channels"))
    return [int(c) for c in (best[1] or [])] if best else []


def recordings(logs_dir, only=None):
    """One dict per recording: mouse, group, gid, path (a local copy when
    there is one), hemisphere ('L' / 'R' / None), bad channels, the channel
    order, and the knockout / P-spike facts for PTEN mice."""
    out = []
    for mouse, group, gid in COHORT:
        if only and mouse not in only and gid not in only:
            continue
        recs = _session_records(logs_dir, gid)
        paths, hem, bad, label = [], None, set(), None
        for d in recs:
            for p in d.get("paths") or []:
                if p not in paths:
                    paths.append(p)
            if d.get("hemisphere") in ("L", "R"):
                hem = d["hemisphere"]
            for b in d.get("bad_channels") or []:
                bad.add(int(b))
            label = label or d.get("label")
        local = [p for p in paths
                 if len(p) > 2 and p[1] == ":" and p[0].upper() != "Y"
                 and os.path.isdir(p)]
        out.append({
            "mouse": mouse, "group": group, "gid": gid,
            "path": local[0] if local else (paths[0] if paths else None),
            "paths": paths, "hemisphere": hem, "bad": sorted(bad),
            "channels": _layer_channels(logs_dir, gid),
            "label": label,
            "ko": KO.get(mouse, 0.0 if group == "CTL" else None),
            "pspikes": PSPIKES.get(mouse, False),
        })
    return out
