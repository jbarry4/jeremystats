"""The No P-spikes set (v8) made from the Halo set (v6), 2026-11-19.

The user skipped reading the deduplicated No P-spikes folder in the
Extraction Room. Every event of the No P-spikes set is also a Halo-set
event (checked on the run 4 data: all of them within 5 ms, the CSD equal to
about 1%), and since run 4 every v8 event already takes its type and DS3
call from the Halo set (dsdata.load). So v8 here is the Halo set's records
cut down to the events the No P-spikes workflow run kept: Root Canal
workflow a7eee6a6ca9f v4 ("ds" class), matched by time within 5 ms.

Differences from a v8 read through the room: the band, the hump cut, the
PCA plane and the classifiers' own indexes are the Halo set's, not refitted
on the smaller set (the battery uses the Halo set's winner for v8 anyway).

  python derive_v8.py        -> data/ds_v8.pkl
"""
import json
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
WF, WV = "a7eee6a6ca9f", 4

sys.path.insert(0, APP)
os.chdir(APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

AR = A.ARTIFACTS
run = (AR.payload(WF, WV) or {})["run"]
cols = run["cols"]
kept = {}
for cls, g, t in zip(cols["cls"], cols["g"], cols["t"]):
    if cls == "ds" and g is not None and t is not None:
        kept.setdefault(cols["gids"][int(g)], []).append(float(t))

base = pickle.load(open(os.path.join(HERE, "data", "ds_v6.pkl"), "rb"))
out, report = [], {}
for d in base:
    n = d["n"]
    want = np.sort(np.asarray(kept.get(d["gid"], []), float))
    t = np.asarray(d["times_s"], float)
    if want.size:
        K = want.size
        j = np.searchsorted(want, t)
        near = np.minimum(np.abs(want[np.clip(j - 1, 0, K - 1)] - t), np.abs(want[np.clip(j, 0, K - 1)] - t))
        m = near <= 0.005
    else:
        m = np.zeros(n, bool)
    idx = np.where(m)[0]
    e = dict(d)
    for k in ("csd", "lfp", "times_s", "det_peak", "pc"):
        if e.get(k) is not None:
            e[k] = np.asarray(d[k])[idx]
    e["n"] = int(idx.size)
    labs = {}
    for c, L in d["labels"].items():
        L = dict(L)
        L["types"] = np.asarray(L["types"])[idx]
        if L.get("axis") is not None:
            L["axis"] = np.asarray(L["axis"])[idx]
        L["n1"], L["n2"] = int((L["types"] == 1).sum()), int((L["types"] == 2).sum())
        L["eligible"] = bool(min(L["n1"], L["n2"]) >= max(5, 0.05 * idx.size))
        labs[c] = L
    e["labels"] = labs
    e["ds3_score"] = {c: np.asarray(v)[idx] for c, v in (d.get("ds3_score") or {}).items()}
    e["W"] = {c: np.asarray(v)[np.ix_(idx, idx)] for c, v in (d.get("W") or {}).items()}
    e["derived_from_v6"] = "No P-spikes events of the Halo set (workflow %s v%d), 2026-11-19" % (WF, WV)
    out.append(e)
    report[d["lab"]] = {"halo": n, "no_pspikes_run": int(want.size), "matched": int(idx.size)}
    print("%-4s Halo %4d | No P-spikes run kept %4d | matched %4d" % (d["lab"], n, want.size, idx.size), flush=True)
with open(os.path.join(HERE, "data", "ds_v8.pkl"), "wb") as f:
    pickle.dump(out, f, protocol=4)
json.dump(report, open(os.path.join(HERE, "data", "v8_derivation.json"), "w"), indent=1)
print("saved", len(out))
