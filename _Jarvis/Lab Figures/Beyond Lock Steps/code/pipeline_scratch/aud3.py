"""Audit step 3: battery times against the pool and the bank with a
tolerance, duplicates, and m1's undone alignment. Read only."""
import collections
import json
import os
import pickle
import sys

import numpy as np

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import rcworkflow  # noqa: E402

AR, BANK = A.ARTIFACTS, A.BANK
BAT = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\data"


def near(a, b):
    """For each of a, distance (ms) to the nearest of b."""
    a, b = np.asarray(sorted(a), float), np.asarray(sorted(b), float)
    if not b.size:
        return np.full(a.size, np.inf)
    j = np.clip(np.searchsorted(b, a), 1, b.size - 1) if b.size > 1 else np.zeros(a.size, int)
    d = np.minimum(np.abs(b[j] - a), np.abs(b[np.maximum(j - 1, 0)] - a))
    return d * 1000


def good(rec, v=None):
    return [e["t"] for e in A._dspca_stamps(rec, v)[0]]


OUT = {}
pay = AR.payload("3561fc988afd", 2) or {}
evs = rcworkflow.pool_events(pay)
P = collections.defaultdict(list)
E = {}
for e in evs:
    P[e["gid"]].append(e["t"])
    E[e["gid"]] = e["entry_id"]
dups = {}
for g, ts in P.items():
    c = collections.Counter(round(t, 6) for t in ts)
    rec = BANK.get(E[g]) or {}
    lv = good(rec)
    cl = collections.Counter(round(t, 6) for t in lv)
    dups[g] = {"pool_n": len(ts), "pool_dup_extra": sum(v - 1 for v in c.values() if v > 1),
               "bank_live_n": len(lv), "bank_dup_extra": sum(v - 1 for v in cl.values() if v > 1),
               "bank_dup_example": [t for t, v in cl.items() if v > 1][:3]}
OUT["dups"] = dups

for name in ("ds_v6.pkl", "ds_v8.pkl"):
    with open(os.path.join(BAT, name), "rb") as f:
        recs = pickle.load(f)
    rows = []
    for d in recs:
        T = np.asarray(d["times_s"], float)
        dp = near(T, P.get(d["gid"], []))
        rec = BANK.get(E.get(d["gid"])) or {}
        dl = near(T, good(rec))
        c = collections.Counter(np.round(T, 4))
        rows.append({"lab": d["lab"], "n": int(T.size), "dtype": str(np.asarray(d["times_s"]).dtype),
                     "dup_extra": int(sum(v - 1 for v in c.values() if v > 1)),
                     "pool_max_ms": float(dp.max()), "pool_over_1ms": int((dp > 1).sum()),
                     "live_max_ms": float(dl.max()), "live_over_1ms": int((dl > 1).sum())})
    OUT[name] = rows

# m1: which stamps the battery holds -- Lock's (v2) or the pre-Lock ones (v1 = v3)?
rec = BANK.get("bfa98498290b")
vers = {BANK.version_key(v): v for v in rec["versions"]}
ids = {v.get("v"): (v.get("id") or BANK.version_key(v)) for v in sorted(rec["versions"], key=lambda v: (v.get("v") or 0, str(v.get("at"))))}
s1, s2, s3 = (good(rec, ids[k]) for k in (1, 2, 3))
moved = sorted(set(np.round(s2, 6)) - set(np.round(s1, 6)))
with open(os.path.join(BAT, "ds_v6.pkl"), "rb") as f:
    m1 = next(d for d in pickle.load(f) if d["lab"] == "m1")
T = np.asarray(m1["times_s"], float)
d1, d2 = near(T, s1), near(T, s2)
v2row = next(v for v in rec["versions"] if (v.get("v") or 0) == 2 and v.get("aligned"))
v3row = [v for v in rec["versions"] if (v.get("v") or 0) == 3]
OUT["m1"] = {"n_v1": len(s1), "n_v2": len(s2), "n_v3": len(s3), "v3_eq_v1": sorted(np.round(s1, 6)) == sorted(np.round(s3, 6)),
             "n_moved_by_lock": len(moved),
             "battery_at_prelock": int((d1 <= 0.5).sum()), "battery_at_lock": int((d2 <= 0.5).sum()),
             "battery_n": int(T.size),
             "battery_off_lock_over_1ms": int((d2 > 1).sum()),
             "lock_shift_ms": [float(x) for x in np.percentile(near(s1, s2)[near(s1, s2) > 0.5], [0, 50, 100])] if len(moved) else None,
             "v2_note": v2row.get("note"), "v2_aligned": {k: v2row["aligned"].get(k) for k in ("tool", "at", "by", "hold", "request")
                                                          if isinstance(v2row.get("aligned"), dict)},
             "v3": [{k: v.get(k) for k in ("v", "id", "at", "by", "note", "auto", "source", "pipeline")} for v in v3row]}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "aud3.json"), "w", encoding="utf-8") as fh:
    json.dump(OUT, fh, indent=1, default=str)
print(json.dumps(OUT, indent=1, default=str)[:9000])
