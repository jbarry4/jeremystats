"""VACC compute node: score EVERY unflagged spike in every committed KCNT1 Lock set, then save +-1 s windows of the
best ones. Same reader/settings as extract_lock.py (Jarvis nlx.py, invert=True, 30 kHz -> 2.5 kHz).

Per spike (even contacts, 60 Hz notch, median of -300..-100 ms removed):
  span   fraction of even contacts (CSC59 excluded) whose |V| peak in +-15 ms reaches 30% of the largest contact's
  hf_db  30-500 Hz power (band-pass, squared Hilbert envelope) in +-10 ms, mean over even contacts, in dB re that
         band's median power over 20 random 2-s windows of the same recording
  hf_pct hf_db as a percentile within its recording's Lock set
"""
import json, os, sys, time
import numpy as np
from scipy.signal import butter, filtfilt, hilbert, iirnotch, resample_poly, sosfiltfilt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nlx
FS = 2500.0
EVEN = [c for c in range(2, 65, 2)]
SETS = json.load(open(os.path.join(HERE, "lock_all.json")))
rng = np.random.RandomState(5)
NB, NA = iirnotch(60.0, 30.0, FS)
HFB = butter(3, [30, 500], btype="band", fs=FS, output="sos")


def read(files, spans):
    n = int(round((spans[0][1] - spans[0][0]) * FS))
    X = np.zeros((len(spans), 64, n), dtype=np.float32)
    for ch in range(1, 65):
        for i, x, a0 in nlx.read_ncs_ranges(files[ch], spans, invert=True):
            y = resample_poly(x.astype(np.float64), 1, 12); k = min(n, len(y)); X[i, ch - 1, :k] = y[:k]
    return X


def hfpow(V):
    return np.abs(hilbert(sosfiltfilt(HFB, V, axis=-1), axis=-1)) ** 2


rows_out, keep = [], {}
for name, s in SETS.items():
    t0 = time.time(); files = dict(nlx.list_csc_files(s["vacc"]))
    if sorted(files) != list(range(1, 65)):
        print("SKIP", name, "channels found:", sorted(files)[:8], len(files), os.listdir(s["vacc"])[:10] if os.path.isdir(s["vacc"]) else "no folder", flush=True)
        continue
    bad = set(s.get("bad") or [59]) | {59}
    ev = [c for c in EVEN if c not in bad]
    idx = [c - 1 for c in ev]
    base_t = rng.uniform(5.0, float(s["dur"]) - 5.0, 20)
    B = read(files, [(t - 1.0, t + 1.0) for t in base_t])
    base = np.median(hfpow(filtfilt(NB, NA, B[:, idx], axis=-1))[..., 250:-250], axis=(0, 2))   # per contact
    ts = np.array([r["start"] for r in s["rows"]])
    met = []
    for a in range(0, len(ts), 50):
        X = read(files, [(t - 0.3, t + 0.3) for t in ts[a:a + 50]])
        V = filtfilt(NB, NA, X[:, idx], axis=-1)
        tt = (np.arange(V.shape[-1]) / FS - 0.3) * 1000
        V = V - np.median(V[..., (tt >= -300) & (tt < -100)], axis=-1, keepdims=True)
        pk = np.abs(V[..., (tt >= -15) & (tt <= 15)]).max(axis=-1)                # events x contacts
        span = (pk >= 0.3 * pk.max(axis=1, keepdims=True)).mean(axis=1)
        P = hfpow(V)[..., (tt >= -10) & (tt <= 10)].mean(axis=-1)                    # events x contacts
        hf = 10 * np.log10(P / base[None, :]).mean(axis=1)
        for k in range(len(span)):
            r = s["rows"][a + k]
            met.append(dict(rec=name, i=r["i"], t=float(ts[a + k]), origin=r.get("origin"), span=float(span[k]), hf_db=float(hf[k]),
                            peak_uv=float(pk[k].max()), top_uv=float(pk[k][:4].mean()), bottom_uv=float(pk[k][-4:].mean())))
        print(name, a + len(span), "/", len(ts), "%.0fs" % (time.time() - t0), flush=True)
    hfs = np.array([m["hf_db"] for m in met])
    for m in met: m["hf_pct"] = float((hfs < m["hf_db"]).mean() * 100)
    rows_out += met
    # keep: top 12 by hf among spikes spanning >= 90% of the depth, plus top 6 by hf regardless
    order = sorted(met, key=lambda m: -m["hf_db"])
    chosen = [m for m in order if m["span"] >= 0.9][:12]
    chosen += [m for m in order[:6] if m not in chosen]
    keep[name] = (chosen, files, base_t)
json.dump(rows_out, open(os.path.join(HERE, "lock_scan_metrics.json"), "w"))
for name, (chosen, files, base_t) in keep.items():
    ts = [m["t"] for m in chosen] + list(base_t)
    X = read(files, [(t - 1.0, t + 1.0) for t in ts])
    kind = ["lock_spike"] * len(chosen) + ["base"] * len(base_t)
    np.savez(os.path.join(HERE, "best_%s.npz" % name), X=X.astype(np.float16), t=np.array(ts), kind=np.array(kind),
             row=np.array([m["i"] for m in chosen] + [-1] * len(base_t)), half=1.0, fs=FS)
    print("saved best", name, len(chosen), flush=True)
print("done", flush=True)
