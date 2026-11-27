"""VACC compute node: score EVERY unflagged spike in m1609 s1's committed Lock set for sharpness, the way the poster's
methods figure draws an IED, and save +-1 s windows of the best 40 (plus 20 random baseline windows).

Per spike (+-1 s read, 60 Hz notch, >1 Hz, even contacts, median of -150..-60 ms removed):
  csc, peak_uv  the largest contact's peak within +-40 ms of the stamp
  fwhm_ms       that peak's full width at half maximum
  prom_ratio    the peak against the biggest same-sign swing 60-300 ms either side (how much it stands out)
  hf_db_med     100-600 Hz RMS in +-20 ms of the peak over that contact's baseline RMS, median over the contacts (dB)
  span          fraction of even contacts whose |V| at the peak moment reaches 30% of the largest contact's
Same reader as scan_lock.py (Jarvis nlx.py, invert=True, 30 kHz -> 2.5 kHz)."""
import json, os, sys, time
import numpy as np
from scipy.signal import butter, filtfilt, iirnotch, resample_poly, sosfiltfilt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nlx
FS = 2500.0
EVEN = list(range(2, 65, 2))
S = json.load(open(os.path.join(HERE, "lock_all.json")))["m1609_s1"]
NB, NA = iirnotch(60.0, 30.0, FS)
HP = butter(3, 1.0, btype="high", fs=FS, output="sos")
HF = butter(4, [100.0, 600.0], btype="band", fs=FS, output="sos")
rng = np.random.RandomState(9)


def read(files, spans):
    n = int(round((spans[0][1] - spans[0][0]) * FS))
    X = np.zeros((len(spans), 64, n), dtype=np.float32)
    for ch in range(1, 65):
        for i, x, a0 in nlx.read_ncs_ranges(files[ch], spans, invert=True):
            y = resample_poly(x.astype(np.float64), 1, 12); k = min(n, len(y)); X[i, ch - 1, :k] = y[:k]
    return X


t0 = time.time()
files = dict(nlx.list_csc_files(S["vacc"]))
base_t = rng.uniform(5.0, float(S["dur"]) - 5.0, 20)
B = filtfilt(NB, NA, read(files, [(t - 1.0, t + 1.0) for t in base_t]), axis=-1)
BASE = np.median(np.sqrt(np.mean(sosfiltfilt(HF, B, axis=-1)[..., 500:-500] ** 2, axis=-1)), axis=0)      # (64,)
print("baseline done %.0fs" % (time.time() - t0), flush=True)

ts = np.array([r["start"] for r in S["rows"]])
tt = np.arange(5000) / FS - 1.0
met = []
for a in range(0, len(ts), 50):
    X = filtfilt(NB, NA, read(files, [(t - 1.0, t + 1.0) for t in ts[a:a + 50]]), axis=-1)
    H = sosfiltfilt(HF, X, axis=-1)
    for k in range(X.shape[0]):
        V = sosfiltfilt(HP, X[k, [c - 1 for c in EVEN]], axis=-1)
        V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
        near = (tt >= -0.04) & (tt <= 0.04)
        r = int(np.argmax(np.abs(V[:, near]).max(1)))
        s = V[r]
        jn = np.flatnonzero(near)[int(np.argmax(np.abs(s[near])))]
        pk = s[jn]; sg = np.sign(pk)
        L = jn
        while L > 0 and sg * s[L] > abs(pk) / 2:
            L -= 1
        R = jn
        while R < len(s) - 1 and sg * s[R] > abs(pk) / 2:
            R += 1
        far = (np.abs(tt - tt[jn]) > 0.06) & (np.abs(tt - tt[jn]) < 0.3)
        other = float(np.max(sg * s[far]))
        win = (tt >= tt[jn] - 0.02) & (tt <= tt[jn] + 0.02)
        hf = 20 * np.log10(np.sqrt(np.mean(H[k][:, win] ** 2, axis=1)) / BASE)
        hf = np.delete(hf, [58])                                      # CSC59 is bad
        span = float(np.mean(np.abs(V[:, jn]) >= 0.3 * abs(pk)))
        row = S["rows"][a + k]
        met.append(dict(i=row["i"], t=float(ts[a + k]), origin=row.get("origin"), csc=EVEN[r], peak_uv=float(pk),
                        off_ms=float(tt[jn] * 1000), fwhm_ms=(R - L) / FS * 1000, prom_ratio=abs(pk) / max(other, 1.0),
                        hf_db_med=float(np.median(hf)), hf_db_max=float(np.max(hf)), span=span))
    print(a + X.shape[0], "/", len(ts), "%.0fs" % (time.time() - t0), flush=True)

json.dump(met, open(os.path.join(HERE, "sharp_metrics_m1609.json"), "w"))
lg = lambda v: np.log(np.maximum(np.abs(np.array(v, dtype=float)), 1e-6))       # noqa: E731
z = lambda v: (v - v.mean()) / v.std()                                           # noqa: E731
score = z(lg([m["peak_uv"] for m in met])) + z(lg([m["prom_ratio"] for m in met])) - z(lg([m["fwhm_ms"] for m in met])) \
    + z(np.array([m["hf_db_med"] for m in met]))
order = np.argsort(-score)[:40]
chosen = [met[i] for i in order]
tk = [m["t"] for m in chosen] + list(base_t)
X = read(files, [(t - 1.0, t + 1.0) for t in tk])
np.savez(os.path.join(HERE, "sharp_m1609_s1.npz"), X=X.astype(np.float16), t=np.array(tk),
         kind=np.array(["lock_spike"] * len(chosen) + ["base"] * len(base_t)), row=np.array([m["i"] for m in chosen] + [-1] * 20),
         score=np.r_[score[order], np.zeros(20)], half=1.0, fs=FS)
print("saved", len(chosen), "done %.0fs" % (time.time() - t0), flush=True)
