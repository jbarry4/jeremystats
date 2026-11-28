"""The whole shank per recording (CSD and LFP, every event at the DS and the
mean over time), added to deep_v*.pkl as deep_full_v*.pkl. Read only."""
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
c = app.test_client()
room = A._er_rooms()[os.environ.get("KROOM", "dentate_spike_kcnt1")]
for V in (7,):
    j = c.get("/api/extraction/%s?version=%d" % (room["id"], V)).get_json()
    out = {}
    for r in j["payload"]["recordings"]:
        Ar, rule, flip = A._er_split_arrays(r)
        L = A._dspca_load(r["gid"], r["read"])
        disp = np.nan_to_num(np.asarray(Ar["disp"], float))
        T = disp.shape[2]
        tt = np.linspace(-50, 50, T)
        w = np.abs(tt) <= 3.0
        raw = np.asarray(L["sur"]["raw"], float)
        base = np.abs(tt) > 30
        raw = raw - np.median(raw[:, :, base], axis=2, keepdims=True)
        out[r["gid"]] = {"nums_all": [int(x) for x in Ar["nums_all"]], "nums_lfp": [int(x) for x in L["nums"]],
                         "bad": sorted(int(k) for k in (L.get("bad") or {})), "csd_at0": disp[:, :, w].mean(axis=2).astype(np.float32),
                         "csd_mean": disp.mean(axis=0).astype(np.float32), "lfp_mean": raw.mean(axis=0).astype(np.float32),
                         "lfp_at0": raw[:, :, w].mean(axis=2).astype(np.float32), "tt": tt,
                         "csd_ev": disp.astype(np.float32),
                         "lfp_ev": raw.astype(np.float32),
                         "box": r.get("box"), "sur_keys": sorted((L.get("sur") or {}).keys())}
        print(V, r["session_label"], disp.shape, raw.shape, out[r["gid"]]["bad"], flush=True)
    with open(os.path.join(HERE, "deep_full_v%d.pkl" % V), "wb") as f:
        pickle.dump(out, f)
