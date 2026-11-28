"""Every Halo-set (v6) event read again from the raw recording, once, and
cut out under several filters at the same time. Same events, same times
(each event's refined time from the room's read), same contacts, same bad
contacts repaired the same way; only the filter differs. Read only: nothing
is written into Jarvis.

  python band_read.py [lab ...]

Per recording -> bandread/<lab>.pkl: {"bands": {name: [n x ch x T] float32},
"nums", "fs", "ds_match": correlation of the 5-100 Hz copy with the room's}.
"""
import os
import pickle
import sys
import time
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
from backend import braces, csc, dspca, incisor  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.environ.get("BAND_OUT", "bandread"))
os.makedirs(OUT, exist_ok=True)
# None = no band filter (the 60 Hz notch only). Order 3 Butterworth,
# zero phase, as Jarvis's DS filter (incisor._filtered).
BANDS = {"ds": (5.0, 100.0), "none": None, "1_100": (1.0, 100.0), "1_300": (1.0, 300.0),
         "5_300": (5.0, 300.0), "5_50": (5.0, 50.0), "10_40": (10.0, 40.0)}
PAD_S = float(os.environ.get("BAND_PAD", "2.0"))   # seconds read past each span on both sides, then dropped (the room's read used 0.5)

only = set(sys.argv[1:])
c = app.test_client()
room = A._er_rooms()[os.environ.get("KROOM", "dentate_spike_kcnt1")]
j = c.get(("/api/extraction/%s?version=" + os.environ.get("KV", "1")) % room["id"]).get_json()
for r in j["payload"]["recordings"]:
    lab = r["session_label"].split()[1]
    path = os.path.join(OUT, lab + ".pkl")
    if (only and lab not in only) or os.path.isfile(path):
        continue
    t_start = time.time()
    gid, rh = r["gid"], r["read"]
    got = A._dspca_load(gid, rh)
    rec = A.DSPCA.get(gid, rh)
    p = dspca.Params(**dict(rec["params"]))
    ent = A._dspca_entry(rec["entry_id"])
    sess, _row = A._braces_session(ent)
    allch = {int(ch["number"]): ch for ch in A._braces_channels(sess)}
    nums = [int(x) for x in got["nums"]]
    chans = [allch[n] for n in nums]
    bad = dict(got.get("bad") or {})
    spec = p.spec()
    rows = got["rows"]
    stamps = np.array([float(x["stamp_s"]) for x in rows])
    t_ref = np.array([float(x["refined_s"]) for x in rows])
    runs = braces.spans(list(stamps), window_ms=p.window_ms + p.surround_ms, pad_s=PAD_S)
    sur_s = float(got.get("surround_ms") or p.surround_ms) / 1000.0
    n, T = len(rows), got["sur"]["band"].shape[2]
    cut = {k: np.full((n, len(nums), T), np.nan, np.float32) for k in BANDS}
    done = np.zeros(n, bool)
    fs = None
    for a, b in runs:
        mine = np.where((stamps >= a + PAD_S - 1e-9) & (stamps <= b - PAD_S + 1e-9) & ~done)[0]
        if not mine.size:
            continue
        per = {k: [] for k in BANDS}
        anchor = None
        for ch in chans:
            raw, got_t0, ch_fs = csc._read_channel_window(sess, ch, a, b)
            q = incisor.decimation_for(ch_fs, p.lfp_fs)
            dec = incisor._decimate(raw, q) if q > 1 else np.asarray(raw, float)
            if anchor is None:
                anchor, fs = got_t0, ch_fs / q
            clean = braces._notch(dec, fs, spec)
            for k, bd in BANDS.items():
                per[k].append(clean if bd is None else incisor._filtered(clean, fs, bd))
        keep = min(x.size for x in per["none"])
        n_sur = int(round(sur_s * fs))
        for k in BANDS:
            arr = braces.repair(np.vstack([x[:keep] for x in per[k]]), chans, bad)
            for i in mine:
                i0 = int(round((t_ref[i] - anchor) * fs))
                if i0 - n_sur < 0 or i0 + n_sur + 1 > arr.shape[1]:
                    continue
                cut[k][i] = arr[:, i0 - n_sur:i0 + n_sur + 1]
        done[mine] = True
    ref = np.asarray(got["sur"]["band"], float)
    ok = np.isfinite(cut["ds"]).all(axis=(1, 2))
    rr = float(np.corrcoef(cut["ds"][ok].ravel(), ref[ok].ravel())[0, 1]) if ok.any() else float("nan")
    rel = float(np.abs(cut["ds"][ok] - ref[ok]).max() / np.abs(ref[ok]).max()) if ok.any() else float("nan")
    with open(path + ".part", "wb") as f:
        pickle.dump({"lab": lab, "gid": gid, "read": rh, "nums": nums, "fs": fs, "bands": cut, "band_hz": BANDS,
                     "n_missing": int((~ok).sum()), "ds_match_r": rr, "ds_match_maxrel": rel, "pad_s": PAD_S}, f, protocol=4)
    os.replace(path + ".part", path)
    print("%-4s n %4d missing %d fs %.0f | 5-100 copy vs the room's: r %.6f, worst diff %.4f of the peak | %.0f s" % (
        lab, n, (~ok).sum(), fs, rr, rel, time.time() - t_start), flush=True)
print("DONE")
