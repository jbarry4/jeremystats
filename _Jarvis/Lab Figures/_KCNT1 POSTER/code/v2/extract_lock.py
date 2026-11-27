"""Second extraction (VACC compute node): +-1 s of all 64 CSCs around committed-Lock spikes and Braces-aligned dentate
spikes (m1609 s1, m1603 s2), plus random baseline windows. Same reader and settings as extract_windows.py."""
import json, os, sys, time
import numpy as np
from scipy.signal import resample_poly
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nlx
cand = json.load(open(os.path.join(HERE, "candidates_lock.json")))
rng = np.random.RandomState(11)
HALF = 1.0
for name, rec in cand.items():
    t_start = time.time(); files = dict(nlx.list_csc_files(rec["vacc"]))
    print(name, rec["vacc"], "channels", len(files), flush=True)
    events, kinds, rows = [], [], []
    for kind in ("lock_spike", "braces_ds"):
        for e in rec.get(kind, []):
            events.append(float(e["start"])); kinds.append(kind); rows.append(int(e["i"]))
    for t in rng.uniform(5.0, float(rec["dur"]) - 5.0, 20):
        events.append(float(t)); kinds.append("base"); rows.append(-1)
    spans = [(t - HALF, t + HALF) for t in events]
    n_out = int(round(2 * HALF * 2500))
    X = np.zeros((len(events), 64, n_out), dtype=np.float16)
    for ch in range(1, 65):
        for i, x, a0 in nlx.read_ncs_ranges(files[ch], spans, invert=True):
            y = resample_poly(x.astype(np.float64), 1, 12); k = min(n_out, len(y)); X[i, ch - 1, :k] = y[:k].astype(np.float16)
        if ch % 32 == 0: print(name, "channel", ch, "%.0fs" % (time.time() - t_start), flush=True)
    np.savez(os.path.join(HERE, "windows_%s.npz" % name), X=X, t=np.array(events), kind=np.array(kinds), row=np.array(rows), half=HALF, fs=2500.0)
    print(name, "saved", X.shape, flush=True)
print("done", flush=True)
