"""Story menu, step 2: read every Root Canal event of the five IED+ baseline sessions (and the few
in-between / IED events elsewhere) through Jarvis's own X-ray reader, so dentate spikes, in-between
events (Twilight Zone) and IEDs come out of ONE pipeline: same contacts, same filters, same alignment.

  python m2_extract.py [lab ...]

Writes reads/<lab>.npz: band (5-100 Hz) and notched broadband windows, events x 64 contacts x time,
2 kHz, +-100 ms, each window centred on the event's DS-band |CSD| peak within +-20 ms of the stamp.
Read only: nothing is written inside Jarvis.
"""
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "reads")
os.makedirs(OUT, exist_ok=True)
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from backend import app as A  # noqa: E402
from backend import dspca  # noqa: E402

IED_PLUS = ["m1619", "m526", "m1609", "m576", "m1603", "m306"]  # KCNT1: every Root Canal event of every mouse
HAND = {}
KIND = {"ds": "DS", "halo_ds": "DS", "both": "TZ", "halo_amb": "TZ", "pspike": "IED", "halo_pspike": "IED", "neither": "far"}

rc = pd.read_pickle(os.path.join(HERE, "rc_events.pkl"))
rc = rc[rc.wf == "halo"].copy()
rc["kind"] = rc["cls"].map(KIND).fillna("none")
labs = sys.argv[1:] or (IED_PLUS + sorted(set(rc.lab.dropna()) - set(IED_PLUS) - {"m6", "m51"}))


ALL = None


def entry_on(gid):
    """Any bank entry on this recording (the session comes with it)."""
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
    ev = rc[rc.lab == lab].copy()
    if lab not in IED_PLUS:
        ev = ev[ev.kind.isin(["TZ", "IED", "far"])]
    ev = ev[np.isfinite(ev.t.astype(float))]
    if ev.empty:
        print(lab, "nothing to read")
        continue
    gid = ev.gid.iloc[0]
    # any bank entry on this recording gives the session (hand-sorted entry where there is one)
    rec = A.BANK.get(HAND[lab]) if lab in HAND else None
    if rec is None:
        rec = entry_on(gid)
    if rec is None:
        print(lab, "no bank entry found for", gid)
        continue
    sess, _row = A._braces_session(rec)
    chans = A._braces_channels(sess)
    p = A._dspca_params({"lfp_fs": 2000, "surround_ms": 100, "window_ms": 20, "refine": "nearest"}, sess)
    p.spacing = 20.0
    stamps = [{"t": float(t)} for t in ev.t]
    marked = {int(c["number"]): "marked bad on this recording" for c in chans if c.get("bad")}
    bad = dict(marked)
    try:
        bad.update(A.bracesmod.screen(sess, chans, p.spec(), [s["t"] for s in stamps]))
    except Exception as exc:  # noqa: BLE001
        print(lab, "screen failed:", exc)
    got = dspca.read(sess, chans, stamps, p, bad)
    rows = got["rows"]
    keep = np.array([r["i"] for r in rows], int)  # positions in `stamps`
    sub = ev.iloc[keep]
    hand_t = []
    if lab in HAND:
        h = A.BANK.get(HAND[lab]) or {}
        hand_t = [float(e.get("start")) for e in (h.get("events") or []) if e.get("start") is not None]
    np.savez_compressed(
        os.path.join(OUT, "%s.npz" % lab),
        band=got["sur"]["band"].astype(np.float32), notch=got["sur"]["notch"].astype(np.float32),
        refined_s=np.array([r["refined_s"] for r in rows]), offset_ms=np.array([r["offset_ms"] for r in rows]),
        stamp_s=np.array([r["stamp_s"] for r in rows]), rc_i=sub["i"].to_numpy(), kind=sub["kind"].to_numpy().astype(str),
        cls=sub["cls"].astype(str).to_numpy(), amp=sub["amp"].to_numpy(float), hf=sub["hf"].to_numpy(float), hw=sub["hw"].to_numpy(float),
        ga=sub["ga"].to_numpy(float), gb=sub["gb"].to_numpy(float),
        nums=np.array(got["nums"]), fs=got["fs"], bad=np.array(sorted(int(k) for k in (got["bad"] or {}))),
        hand_t=np.array(hand_t), missed=np.array(got["missed"]), mains_uv=got["mains_uv"], wideband_uv=got["wideband_uv"])
    print("%s read %d of %d (%s) in %.0f s; bad %s" % (lab, len(rows), len(stamps), dict(sub.kind.value_counts()), time.time() - t0,
                                                        sorted(int(k) for k in (got["bad"] or {}))), flush=True)
print("done")
