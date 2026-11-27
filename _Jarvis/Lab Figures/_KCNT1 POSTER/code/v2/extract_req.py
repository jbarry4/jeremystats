"""VACC compute node: +-1 s of all 64 CSCs around requested times (req_ied.json) + 20 baseline windows per recording."""
import json, os, sys
import numpy as np
from scipy.signal import resample_poly
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nlx
req = json.load(open(os.path.join(HERE, "req_ied.json"))); rng = np.random.RandomState(9)
for name, q in req.items():
    files = dict(nlx.list_csc_files(q["vacc"]))
    ts = list(q["t"]) + list(rng.uniform(5, float(q["dur"]) - 5, 20))
    kind = ["lock_spike"] * len(q["t"]) + ["base"] * 20
    X = np.zeros((len(ts), 64, 5000), dtype=np.float16)
    for ch in range(1, 65):
        for i, x, a0 in nlx.read_ncs_ranges(files[ch], [(t - 1, t + 1) for t in ts], invert=True):
            y = resample_poly(x.astype(np.float64), 1, 12); k = min(5000, len(y)); X[i, ch - 1, :k] = y[:k]
    np.savez(os.path.join(HERE, "ied_%s.npz" % name), X=X, t=np.array(ts), kind=np.array(kind), half=1.0, fs=2500.0)
    print("saved", name, len(ts), flush=True)
print("done", flush=True)
