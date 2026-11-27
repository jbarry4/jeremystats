"""The filter battery's event sets: the Halo set (v6) with every event's
whole-shank CSD and LFP made again from bandread/<lab>.pkl under one filter,
by Jarvis's own fit (the room's box, interpolated contacts and time window),
and everything else -- events, types, names, DS3 -- left as the room's.
Writes battery/data/ds_b_<band>.pkl. Read only: Jarvis's split cache is
pointed at a scratch folder for the run.

  python band_build.py [band ...]
"""
import copy
import shutil
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, os.environ.get("BAND_OUT", "bandread"))
BAT = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
A._ER_SPLIT_DIR = os.path.join(HERE, "band_split_cache")
BANDS = sys.argv[1:] or ["ds", "none", "1_100", "1_300", "5_300", "5_50", "10_40"]

c = app.test_client()
room = A._er_rooms()["dentate_spike"]
j = c.get("/api/extraction/%s?version=6" % room["id"]).get_json()
base = {d["gid"]: d for d in pickle.load(open(os.path.join(BAT, "data", "ds_v6.pkl"), "rb"))}
real_load = A._dspca_load
reads = {}
for r in j["payload"]["recordings"]:
    lab = r["session_label"].split()[1]
    p = os.path.join(SRC, lab + ".pkl")
    if os.path.isfile(p):
        reads[r["gid"]] = pickle.load(open(p, "rb"))

for band in BANDS:
    out = []
    cur = {}

    def fake_load(gid, ph):
        got = dict(real_load(gid, ph))
        got["sur"] = dict(got["sur"])
        got["sur"]["band"] = cur[gid]
        return got

    A._dspca_load = fake_load
    # Jarvis keeps fitted arrays on disk by read and box, NOT by filter: each
    # filter gets its own empty cache folder, or every filter after the first
    # silently gets the first one's CSD (it did, the first time this ran).
    A._ER_SPLIT_DIR = os.path.join(HERE, "band_split_cache", band)
    shutil.rmtree(A._ER_SPLIT_DIR, ignore_errors=True)
    for r in j["payload"]["recordings"]:
        gid = r["gid"]
        d0 = base.get(gid)
        if d0 is None:
            continue
        B = reads.get(gid)
        if B is None:
            print("NO READ", d0["lab"], flush=True)
            continue
        x = np.asarray(B["bands"][band], float)
        orig = np.asarray(real_load(gid, r["read"])["sur"]["band"], float)
        miss = ~np.isfinite(x).all(axis=(1, 2))
        x[miss] = orig[miss] if band == "ds" else np.nan
        cur[gid] = np.nan_to_num(x)
        A._ER_SPLIT_MEMO.clear()
        Ar, _rule, _flip = A._er_split_arrays(r)
        disp = np.nan_to_num(np.asarray(Ar["disp"], float))
        tt = np.linspace(-50, 50, x.shape[2])
        lfp = x - np.nanmedian(x[:, :, np.abs(tt) > 30], axis=2, keepdims=True)
        d = copy.copy(d0)
        if disp.shape != np.asarray(d0["csd"]).shape:
            print("SHAPE", d0["lab"], disp.shape, np.asarray(d0["csd"]).shape, flush=True)
            continue
        d["csd"] = disp.astype(np.float32)
        d["lfp"] = lfp.astype(np.float32)
        d["filter"] = band
        d["filter_hz"] = B["band_hz"][band]
        d["n_unread"] = int(miss.sum())
        out.append(d)
        dd = np.asarray(d0["csd"], float)
        rr = np.corrcoef(disp.mean(axis=0).ravel(), dd.mean(axis=0).ravel())[0, 1]
        print("%-6s %-4s n %4d unread %d | mean CSD vs the room's (5-100): r %.4f" % (band, d0["lab"], disp.shape[0], miss.sum(), rr), flush=True)
    with open(os.path.join(BAT, "data", "ds_b_%s.pkl" % band), "wb") as f:
        pickle.dump(out, f, protocol=4)
    print("saved", band, len(out), flush=True)
A._dspca_load = real_load
