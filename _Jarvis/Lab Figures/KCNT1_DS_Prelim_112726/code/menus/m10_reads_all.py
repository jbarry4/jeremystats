"""Jeremy menu, step 1: read every Halo DS event of the 11 mice that are not IED+ through Jarvis's X-ray reader, with
exactly the settings of m2_extract.py (2 kHz, +-100 ms, 5-100 Hz band and notched broadband, refined on the DS-band
|CSD| peak), so that every mouse's DS share one pipeline for the dominant-frequency questions. The five IED+ mice were
read by m2_extract.py already (reads/<lab>.npz, every Root Canal event).

  python m10_reads_all.py [lab ...]

Writes reads_ds/<lab>.npz. Read only: nothing is written inside Jarvis.
"""
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "reads_ds")
os.makedirs(OUT, exist_ok=True)
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from backend import app as A  # noqa: E402
from backend import dspca  # noqa: E402

IED_PLUS = ["m3", "m34", "m28", "m13", "m5"]
KIND = {"ds": "DS", "halo_ds": "DS", "both": "TZ", "halo_amb": "TZ", "pspike": "IED", "halo_pspike": "IED", "neither": "far"}
rc = pd.read_pickle(os.path.join(HERE, "rc_events.pkl"))
rc = rc[rc.wf == "halo"].copy()
rc["kind"] = rc["cls"].map(KIND).fillna("none")
labs = sys.argv[1:] or sorted(set(rc.lab.dropna()) - set(IED_PLUS) - {"m6", "m51"})
ALL = None


def entry_on(gid):
    global ALL
    if ALL is None:
        ALL = A.BANK.all()
    items = ALL.values() if isinstance(ALL, dict) else ALL
    for r in items:
        if isinstance(r, dict) and r.get("gid") == gid:
            return A.BANK.get(r.get("id")) or r
    return None


for lab in labs:
    t0 = time.time()
    if os.path.exists(os.path.join(OUT, "%s.npz" % lab)):
        print(lab, "already read", flush=True)
        continue
    ev = rc[(rc.lab == lab) & (rc.kind == "DS")].copy()
    ev = ev[np.isfinite(ev.t.astype(float))]
    if ev.empty:
        print(lab, "no DS events", flush=True)
        continue
    rec = entry_on(ev.gid.iloc[0])
    if rec is None:
        print(lab, "no bank entry found for", ev.gid.iloc[0], flush=True)
        continue
    sess, _row = A._braces_session(rec)
    chans = A._braces_channels(sess)
    p = A._dspca_params({"lfp_fs": 2000, "surround_ms": 100, "window_ms": 20, "refine": "nearest"}, sess)
    p.spacing = 20.0
    stamps = [{"t": float(t)} for t in ev.t]
    bad = {int(c["number"]): "marked bad on this recording" for c in chans if c.get("bad")}
    try:
        bad.update(A.bracesmod.screen(sess, chans, p.spec(), [s["t"] for s in stamps]))
    except Exception as exc:  # noqa: BLE001
        print(lab, "screen failed:", exc, flush=True)
    got = dspca.read(sess, chans, stamps, p, bad)
    rows = got["rows"]
    keep = np.array([r["i"] for r in rows], int)
    sub = ev.iloc[keep]
    np.savez_compressed(
        os.path.join(OUT, "%s.npz" % lab),
        band=got["sur"]["band"].astype(np.float32), notch=got["sur"]["notch"].astype(np.float32),
        refined_s=np.array([r["refined_s"] for r in rows]), offset_ms=np.array([r["offset_ms"] for r in rows]),
        stamp_s=np.array([r["stamp_s"] for r in rows]), rc_i=sub["i"].to_numpy(), kind=sub["kind"].to_numpy().astype(str),
        cls=sub["cls"].astype(str).to_numpy(), amp=sub["amp"].to_numpy(float), hf=sub["hf"].to_numpy(float), hw=sub["hw"].to_numpy(float),
        ga=sub["ga"].to_numpy(float), gb=sub["gb"].to_numpy(float),
        nums=np.array(got["nums"]), fs=got["fs"], bad=np.array(sorted(int(k) for k in (got["bad"] or {}))),
        missed=np.array(got["missed"]))
    print("%s read %d of %d DS in %.0f s; bad %s" % (lab, len(rows), len(stamps), time.time() - t0,
                                                   sorted(int(k) for k in (got["bad"] or {}))), flush=True)
print("done")
