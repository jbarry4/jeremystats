"""Sextant's atlas: what a straight probe crosses, wherever it is put.

The volume is web/seahorse/sextant10.shb.gz (tools/sextant/build_atlas.py):
Allen CCFv3 2017 at 10 um with the Seahorse laminae (CA strata, the dentate
blades and molecular-layer thirds) and coarse regions around them, right
hemisphere only. A left-hemisphere probe is fitted on the right (the CCF is
symmetric) and reported with its own sign.

Coordinates
-----------
CCF micrometres, index order [AP, DV, ML]: AP increases posterior, DV
ventral, ML to the right; the midline is ML 5700.

Bregma: the CCF has no skull, so there is no official bregma (Allen
Institute). Sextant uses the International Brain Laboratory's convention,
the average of five experimentalists picking it on the atlas: AP 5400,
DV 332 um (iblatlas ALLEN_CCF_LANDMARKS_MLAPDV_UM), with ML measured from
the midline. No scaling between atlas and skull is applied to the bregma
numbers (IBL's default is identity); the fit's own size factor absorbs the
fixed-brain shrinkage along the probe.

A pose
------
    centre  the CCF point the probe's middle (between contacts 32 and 33)
            sits at
    dir     unit vector from contact 1 (top) toward contact 64 (tip)
    scale   atlas um per probe um along the shank (< 1 when the living brain
            is bigger than the fixed atlas brain, or the tissue compressed)
Contact k (1-based) sits at centre + (k - 32.5) * pitch * scale * dir.

The two tilts are angles of that direction from straight down (+DV):
`tilt_ml` > 0 leans the tip lateral, `tilt_ap` > 0 leans it posterior.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import struct
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
PATH = os.path.join(APP, "web", "seahorse", "sextant10.shb.gz")

MID_ML = 5700.0
BREGMA = {"ap": 5400.0, "dv": 332.0, "ml": MID_ML}

_LOCK = threading.Lock()
_ATLAS = None


class Atlas:
    def __init__(self, labels, origin, um, classes):
        self.L = labels                      # uint8 [AP, DV, ML]
        self.origin = np.asarray(origin, float)
        self.um = float(um)
        self.shape = np.asarray(labels.shape)
        self.classes = classes
        self.key = {c["code"]: c["key"] for c in classes}
        self.code = {c["key"]: c["code"] for c in classes}
        self.label = {c["code"]: c["label"] for c in classes}
        self._surface = None

    # -- sampling ---------------------------------------------------------
    def codes_at(self, pts):
        """Codes at CCF-um points [..., 3] (AP, DV, ML), nearest voxel.
        Outside the box is 0 (outside), which the fit treats as 'not
        hippocampus' -- never as a match for anything."""
        p = np.asarray(pts, float)
        idx = np.floor((p - self.origin) / self.um).astype(np.int64)
        ok = np.all((idx >= 0) & (idx < self.shape), axis=-1)
        idx = np.where(ok[..., None], idx, 0)
        out = self.L[idx[..., 0], idx[..., 1], idx[..., 2]]
        return np.where(ok, out, 0).astype(np.uint8)

    def surface_dv(self, ap, ml):
        """DV (um) of the brain's dorsal surface above (ap, ml)."""
        if self._surface is None:
            inb = self.L > 0
            first = np.argmax(inb, axis=1).astype(float)
            first[~inb.any(axis=1)] = np.nan
            self._surface = self.origin[1] + first * self.um
        i = int(np.clip((ap - self.origin[0]) // self.um, 0, self.shape[0] - 1))
        k = int(np.clip((ml - self.origin[2]) // self.um, 0, self.shape[2] - 1))
        return float(self._surface[i, k])


def load():
    global _ATLAS
    with _LOCK:
        if _ATLAS is None:
            raw = gzip.decompress(open(PATH, "rb").read())
            n = struct.unpack("<I", raw[4:8])[0]
            h = json.loads(raw[8:8 + n])
            base = 8 + n
            a = h["arrays"][0]
            lab = np.frombuffer(raw[base + a["offset"]:base + a["offset"] + a["nbytes"]],
                                dtype=np.uint8).reshape(a["shape"]).copy()
            _ATLAS = Atlas(lab, h["origin_um"], h["um"], h["classes"])
    return _ATLAS


# -- poses --------------------------------------------------------------
def direction(tilt_ml_deg, tilt_ap_deg):
    """Unit vector(s) down the shank for the two tilts (degrees)."""
    tm = np.radians(np.asarray(tilt_ml_deg, float))
    ta = np.radians(np.asarray(tilt_ap_deg, float))
    v = np.stack([np.tan(ta), np.ones_like(tm), np.tan(tm)], axis=-1)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def tilts_of(d):
    d = np.asarray(d, float)
    return (math.degrees(math.atan2(d[2], d[1])), math.degrees(math.atan2(d[0], d[1])))


def contacts(centre, d, scale, n=64, pitch=20.0):
    """CCF positions [n, 3] of the contacts, top first."""
    k = np.arange(1, n + 1) - (n + 1) / 2.0
    return np.asarray(centre, float)[None, :] + (k * pitch * scale)[:, None] * np.asarray(d, float)[None, :]


def to_bregma(p, hemisphere=None):
    """CCF um (AP, DV, ML) -> bregma mm {ap, dv, ml}; ML signed by hemisphere
    (left negative) when it is known, else unsigned."""
    p = np.asarray(p, float)
    ml = (p[..., 2] - MID_ML) / 1000.0
    if hemisphere == "L":
        ml = -ml
    return {"ap": (BREGMA["ap"] - p[..., 0]) / 1000.0,
            "dv": (p[..., 1] - BREGMA["dv"]) / 1000.0,
            "ml": ml}


def from_bregma(ap_mm, ml_mm, dv_mm=None):
    """bregma mm -> CCF um (right hemisphere: |ML|)."""
    ap = BREGMA["ap"] - 1000.0 * ap_mm
    ml = MID_ML + 1000.0 * abs(ml_mm)
    dv = BREGMA["dv"] + 1000.0 * (dv_mm if dv_mm is not None else 0.0)
    return np.array([ap, dv, ml])


def entry_point(atl, centre, d):
    """Where the shank's line crosses the brain's dorsal surface (CCF um),
    walking up from the centre."""
    c = np.asarray(centre, float)
    d = np.asarray(d, float)
    t = np.arange(0.0, 5000.0, 10.0)
    pts = c[None, :] - t[:, None] * d[None, :]
    codes = atl.codes_at(pts)
    out = np.nonzero(codes == 0)[0]
    if not out.size:
        return pts[-1], float(t[-1])
    j = int(out[0])
    return pts[max(j - 1, 0)], float(t[max(j - 1, 0)])
