"""Run on a VACC compute node (it can read /netfiles). For each recording, read +-1 s of all 64 CSCs around
each candidate event (and some random baseline windows), with Jarvis's own reader (nlx.py: seconds from the first
record's timestamp, invert=True), downsample 30 kHz -> 2.5 kHz, and save float16 uV arrays."""
import json, os, sys, time
import numpy as np
from scipy.signal import resample_poly
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nlx
REC = {"m1606": "/netfiles/bigdata_jbarry/Jeremy3/KCNT1/Summer'26/KCNT1_m1606/KCNT1_m1606_s01_080426/2026-08-04_11-20-06",
       "m306": "/netfiles/bigdata_jbarry/Jeremy3/KCNT1/Spring'26/KCNT1_hom306/KCNT1_hom306_s1_feb24/2026-02-24_17-46-28"}
DUR = {"m1606": 1800.0, "m306": 2074.0}
HALF, N_KEEP, N_BASE = 1.0, 30, 20
cand = json.load(open(os.path.join(HERE, "candidates.json")))
rng = np.random.RandomState(7)
for name, folder in REC.items():
    t_start = time.time()
    files = dict(nlx.list_csc_files(folder))
    print(name, "channels", len(files), flush=True)
    events, kinds = [], []
    for kind in ("ds", "ds_curated", "ied"):
        for e in cand[name].get(kind, [])[:N_KEEP]:
            events.append(float(e["start"])); kinds.append(kind)
    for t in rng.uniform(5.0, DUR[name] - 5.0, N_BASE):
        events.append(float(t)); kinds.append("base")
    spans = [(t - HALF, t + HALF) for t in events]
    n_out = int(round(2 * HALF * 2500))
    X = np.zeros((len(events), 64, n_out), dtype=np.float16)
    T0 = np.zeros((len(events), 64))
    for ch in range(1, 65):
        for i, x, a0 in nlx.read_ncs_ranges(files[ch], spans, invert=True):
            y = resample_poly(x.astype(np.float64), 1, 12)
            k = min(n_out, len(y))
            X[i, ch - 1, :k] = y[:k].astype(np.float16)
            T0[i, ch - 1] = a0
        if ch % 16 == 0: print(name, "channel", ch, "%.0fs" % (time.time() - t_start), flush=True)
    np.savez(os.path.join(HERE, "windows_%s.npz" % name), X=X, t=np.array(events), kind=np.array(kinds), t0=T0, half=HALF, fs=2500.0)
    print(name, "saved", X.shape, "%.0fs" % (time.time() - t_start), flush=True)
print("done", flush=True)
