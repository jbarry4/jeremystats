"""THE BEFORE/AFTER READ (2026-11-18): every Halo-set (v6) event, and as many
random moments of the same recording (at least 1 s from any event), read
from the raw recording, +-500 ms around each. Read only.

Per window, on every contact:
  lfp   the LFP, 60 Hz notched, 1 kHz, bad contacts filled in   (n x 64 x 1001)
  env   band power over time, 10 ms bins (101 bins, -500..+500 ms), of the CSD
        (reference-free) in 6 bands, plus multi-unit activity (MUA) from the
        raw 30 kHz (300-3000 Hz, rectified)                      (n x 7 x 64 x 101)
Bands: 1-4, 4-12, 15-30, 30-60, 60-100, 100-250 Hz; envelope = |Hilbert| of
the zero-phase band-passed CSD (Butterworth order 3), computed on the whole
read stretch (1 s or more of margin on each side) before cutting.

  python around_read.py lab [lab ...]     -> around/<lab>.npz
"""
import os
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
from scipy import signal as sg  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import braces, csc, dspca, incisor  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "around")
os.makedirs(OUT, exist_ok=True)
BANDS = [(1.0, 4.0), (4.0, 12.0), (15.0, 30.0), (30.0, 60.0), (60.0, 100.0), (100.0, 250.0)]
BAND_NAMES = ["1-4", "4-12", "15-30", "30-60", "60-100", "100-250", "MUA"]
HALF = 0.5          # s each side
MARGIN = 1.0        # s read past each window, both sides
MAX_SPAN = 60.0     # s; longer stretches are cut into pieces that overlap
NBIN, BIN = 101, 10  # 10 ms bins over -505..+505 ms

only = sys.argv[1:]
c = app.test_client()
room = A._er_rooms()[os.environ.get("KROOM", "dentate_spike_kcnt1")]
j = c.get(("/api/extraction/%s?version=" + os.environ.get("KV", "1")) % room["id"]).get_json()


def plan(times, dur):
    """Stretches to read: windows merged while the stretch stays under MAX_SPAN."""
    out = []
    for t in sorted(times):
        lo, hi = max(0.0, t - HALF - MARGIN), min(dur, t + HALF + MARGIN)
        if out and lo <= out[-1][1] and hi - out[-1][0] <= MAX_SPAN:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def csd_rows(V):
    """Second difference down the shank (sink negative); edge rows copy their neighbor."""
    C = np.full_like(V, np.nan)
    C[1:-1] = -(V[:-2] - 2.0 * V[1:-1] + V[2:])
    C[0], C[-1] = C[1], C[-2]
    return C


for r in j["payload"]["recordings"]:
    lab = r["session_label"].split()[1]
    path = os.path.join(OUT, lab + ".npz")
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
    dur = float(sess.get("duration_s") or 0)
    ev = np.array([float(x["refined_s"]) for x in got["rows"]])
    rng = np.random.default_rng(sum(ord(ch_) * 31 ** k_ for k_, ch_ in enumerate(lab)))
    rnd = []
    tries = 0
    while len(rnd) < ev.size and tries < 200000:
        tries += 1
        t = rng.uniform(5.0, dur - 5.0)
        if np.min(np.abs(ev - t)) >= 1.0:
            rnd.append(t)
    rnd = np.array(sorted(rnd))
    allt = np.concatenate([ev, rnd])
    kind = np.r_[np.zeros(ev.size, int), np.ones(rnd.size, int)]
    N = allt.size
    lfp = np.zeros((N, len(nums), 2 * 500 + 1), np.float16)
    env = np.zeros((N, len(BAND_NAMES), len(nums), NBIN), np.float16)
    done = np.zeros(N, bool)
    soss = [sg.butter(3, [lo, hi], btype="band", fs=1000.0, output="sos") for lo, hi in BANDS]
    for a, b in plan(allt, dur):
        mine = np.where((allt - HALF - 0.55 >= a - 1e-9) & (allt + HALF + 0.55 <= b + 1e-9) & ~done)[0]
        if not mine.size:
            continue
        L, M = [], []
        anchor = fs = None
        for ch in chans:
            raw, got_t0, ch_fs = csc._read_channel_window(sess, ch, a, b)
            q = incisor.decimation_for(ch_fs, p.lfp_fs)
            dec = incisor._decimate(raw, q) if q > 1 else np.asarray(raw, float)
            if anchor is None:
                anchor, fs = got_t0, ch_fs / q
                sos_m = sg.butter(3, [300.0, min(3000.0, ch_fs * 0.45)], btype="band", fs=ch_fs, output="sos")
            L.append(braces._notch(dec, fs, spec))
            mu = np.abs(sg.sosfiltfilt(sos_m, np.asarray(raw, float)))
            k = (mu.size // q) * q
            M.append(mu[:k].reshape(-1, q).mean(axis=1))
        keep = min(min(x.size for x in L), min(x.size for x in M))
        V = braces.repair(np.vstack([x[:keep] for x in L]), chans, bad)
        MU = braces.repair(np.vstack([x[:keep] for x in M]), chans, bad)
        C = csd_rows(V)
        E = [np.abs(sg.hilbert(sg.sosfiltfilt(s_, C, axis=1), axis=1)) for s_ in soss] + [MU]
        for i in mine:
            i0 = int(round((allt[i] - anchor) * fs))
            if i0 - 505 < 0 or i0 + 505 > V.shape[1]:
                continue
            lfp[i] = V[:, i0 - 500:i0 + 501]
            for bi, X in enumerate(E):
                env[i, bi] = X[:, i0 - 505:i0 + 505].reshape(X.shape[0], NBIN, BIN).mean(axis=2)
            done[i] = True
    np.savez(path + ".part.npz", lfp=lfp, env=env, t=allt, kind=kind, done=done, nums=np.array(nums), bands=np.array(BAND_NAMES),
             fs=np.array(fs or 0.0))
    os.replace(path + ".part.npz", path)
    print("%-4s events %4d random %4d unread %d | %.0f s" % (lab, ev.size, rnd.size, (~done).sum(), time.time() - t_start), flush=True)
print("DONE")
