"""Story menu, step 0: pull what Jarvis knows into plain files (read only).

  - rc_events.pkl : every pooled event of the 18 baseline recordings with its Root Canal
                    numbers (max amplitude, HF power, half-width) and its class under the
                    Halo workflow (6fa7fef7b7a3 v5) and the Strict workflow (a7eee6a6ca9f v4)
  - rc_borders.json : both runs' border and halo definitions
  - layers.json   : each recording's StrataScope layer labels (channel number -> region id)
  - ied_bank.json : hand-sorted and Root Canal ("Hidden IEDs") IED times for the 5 IED+ sessions

Nothing is written inside Jarvis.
"""
import json
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
OUT = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from backend import app as A  # noqa: E402

GIDS = {  # KCNT1 preliminary run (2 WT, 2 Het, 2 Hom), 2026-11-27
    "m1619": "sdcedca6715fb", "m526": "s44851809ecd5", "m1609": "se0c7b6ba6d5a",
    "m576": "s6d234609d2c2", "m1603": "s655a06b22296", "m306": "s9619387fd35c",
}
LAB_OF = {g: lab for lab, g in GIDS.items()}

# ---------------------------------------------------------------- Root Canal runs
frames = []
borders = {}
for wf, ver, name in ((os.environ.get("K_HALO_WF", "3b70472fd070"), int(os.environ.get("K_HALO_V", "3")), "halo"),
                      (os.environ.get("K_STRICT_WF", "702bfb1e0a44"), int(os.environ.get("K_STRICT_V", "2")), "strict")):
    pay = A.ARTIFACTS.payload(wf, ver)
    run = pay["run"]
    c = run["cols"]
    gids = c["gids"]
    n = len(c["cls"])
    df = pd.DataFrame({
        "wf": name, "i": c["i"], "gid": [gids[k] for k in c["g"]], "mouse": c["mouse"],
        "amp": c["amp"], "hf": c["hf"], "hw": c["hw"], "cls": c["cls"],
        "cls_plain": c.get("cls_plain", c["cls"]), "t": c["t"], "ga": c["ga"], "gb": c["gb"],
    })
    df["lab"] = df["gid"].map(LAB_OF)
    frames.append(df)
    borders[name] = {k: run.get(k) for k in ("borders", "halo", "halo_centres", "counts", "target", "measure", "by_recording", "by_mouse")}
    print(name, n, run.get("counts"))
rc = pd.concat(frames, ignore_index=True)
rc.to_pickle(os.path.join(OUT, "rc_events.pkl"))
with open(os.path.join(OUT, "rc_borders.json"), "w", encoding="utf-8") as f:
    json.dump(borders, f, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))

# ---------------------------------------------------------------- layers
lay = {}
for lab, g in GIDS.items():
    rec = A.LAYERS.get(g) or {}
    labels = rec.get("labels") or {}
    lay[lab] = {"gid": g, "labels": {str(k): v for k, v in labels.items()}}
    print(lab, len(labels), sorted(set(labels.values())))
with open(os.path.join(OUT, "layers.json"), "w", encoding="utf-8") as f:
    json.dump(lay, f)

# ---------------------------------------------------------------- IED bank entries for the 5 IED+ sessions
want = {}  # KCNT1: no hand-sorted IED sets
ied = {}
for lab, eids in want.items():
    ied[lab] = {}
    for eid in eids:
        e = A.BANK.get(eid) or {}
        evs = e.get("events") or []
        ts = []
        for ev in evs:
            t = ev.get("t") if isinstance(ev, dict) else None
            if t is None and isinstance(ev, dict):
                t = ev.get("time") or ev.get("peak_s") or ev.get("ts")
            ts.append(t)
        ied[lab][eid] = {"name": e.get("name"), "n": len(evs), "t": ts, "aligned": e.get("aligned"),
                         "params": e.get("parameters"), "first_event": evs[0] if evs else None}
        print(lab, eid, e.get("name"), len(evs), (evs[0] if evs else None))
with open(os.path.join(OUT, "ied_bank.json"), "w", encoding="utf-8") as f:
    json.dump(ied, f, default=str)

# the battery's DS times are the room's; note what the session records say about time
sess = {}
for lab, g in GIDS.items():
    s = A._session_by_gid(g) if hasattr(A, "_session_by_gid") else None
    sess[lab] = {"gid": g, "has": bool(s)}
print("done")
