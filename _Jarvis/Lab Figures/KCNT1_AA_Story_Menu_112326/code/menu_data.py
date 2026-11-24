"""Shared data for the AA story-menu pages."""
import json
import os

import numpy as np
import pandas as pd

import figlib_aa as F

HERE = os.path.dirname(os.path.abspath(__file__))
U_RAW = pd.read_csv(os.path.join(HERE, "tables", "per_session_values.csv"), dtype={"mouse": str})
U = pd.read_csv(os.path.join(HERE, "tables", "per_session_values_speed_adjusted.csv"), dtype={"mouse": str})  # one floor speed
for _u in (U, U_RAW):
    _u["rot_bin"] = _u.mouse.map(lambda m: F.MICE[m]["rot_bin"])
TR = np.load(os.path.join(HERE, "tracks.npz"))
ROTDAY = json.load(open(os.path.join(HERE, "rotation_by_day.json")))
VALID = pd.read_csv(os.path.join(HERE, "tables", "validation_vs_trackanalysis.csv"))
PAIRS = pd.read_csv(os.path.join(HERE, "validation_pairs.csv"), dtype={"mouse": str})
SHOCKJ = pd.read_csv(os.path.join(HERE, "shock_response.csv"), dtype={"mouse": str})
MLIST = sorted(F.MICE, key=int)


def curve(measure, mice, sessions=range(0, 17), raw=False):
    """Mean and SEM across mice per session (one value per mouse per session); at one floor speed unless raw."""
    T = U_RAW if raw else U
    p = T[T.mouse.isin(mice)].pivot_table(index="mouse", columns="session", values=measure)
    ks = [k for k in sessions if k in p.columns]
    m = p[ks].mean()
    se = p[ks].std(ddof=1) / np.sqrt(p[ks].notna().sum())
    return np.array(ks), m.values, se.values, p[ks]


def by(g=None, age=None, rot=None):
    out = []
    for m in MLIST:
        d = F.MICE[m]
        if g and d["yh"] != g:
            continue
        if age and d["age_group"] != age:
            continue
        if rot and d["rot_bin"] != rot:
            continue
        out.append(m)
    return out


def track(m, s):
    k = "%s_s%d" % (m, s)
    return TR[k + "|x"], TR[k + "|y"], TR[k + "|shocks"], TR[k + "|entr"]


def occ(m, sessions):
    return np.mean([TR["%s_s%d|occ36" % (m, s)] for s in sessions], axis=0)
