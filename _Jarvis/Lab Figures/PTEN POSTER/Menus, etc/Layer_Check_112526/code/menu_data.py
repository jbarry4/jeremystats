"""Shared data access for the story-menu pages."""
import json
import os
import pickle

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RES = pd.read_pickle(os.path.join(HERE, "tables", "all_results.pkl"))
VAL = pd.read_pickle(os.path.join(HERE, "tables", "per_mouse_values.pkl"))
LABS16 = ["m2", "m21", "m22", "m26", "m59", "m60", "m61", "m8", "m33", "m1", "m7", "m13", "m28", "m3", "m5", "m34"]
_rc = None
_prof = None
_dsied = None


def values(mid):
    row = VAL[VAL.id == mid]
    if row.empty:
        raise KeyError(mid)
    row = row.iloc[0]
    return {l: float(row[l]) for l in LABS16 if l in row.index and np.isfinite(row[l])}


def res(mid):
    return RES[RES.id == mid]


def desc(mid):
    row = VAL[VAL.id == mid]
    return row.desc.iloc[0] if len(row) else ""


def p(mid, contrast):
    s = RES[(RES.id == mid) & (RES.contrast == contrast)]
    if s.empty:
        return np.nan, "", np.nan, np.nan, False
    s = s.iloc[0]
    return float(s.p), s.test, float(s.effect), float(s.strict_p) if pd.notna(s.strict_p) else np.nan, bool(s.separated) if pd.notna(s.separated) else False


def rc():
    global _rc
    if _rc is None:
        _rc = pd.read_pickle(os.path.join(HERE, "rc_events.pkl"))
        KIND = {"ds": "DS", "halo_ds": "DS", "both": "TZ", "halo_amb": "TZ", "pspike": "IED", "halo_pspike": "IED", "neither": "far"}
        _rc["kind"] = _rc.cls.map(KIND).fillna("none")
    return _rc


def prof():
    global _prof
    if _prof is None:
        _prof = pickle.load(open(os.path.join(HERE, "profiles_ds.pkl"), "rb"))
    return _prof


def dsied():
    global _dsied
    if _dsied is None:
        _dsied = pickle.load(open(os.path.join(HERE, "dsied.pkl"), "rb"))
    return _dsied
