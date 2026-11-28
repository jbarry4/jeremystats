"""Score every m1609 lock_spike window we hold locally for sharpness: prominence, half-width, high-frequency power.
usage: python ied_scan.py VACC_DIR OUT_CSV [extra .npz files with lock_spike windows ...]"""
import json, os, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt, iirnotch, filtfilt

V_DIR, OUT = sys.argv[1], sys.argv[2]
EXTRA = sys.argv[3:]
FS = 2500.0
EVEN = list(range(2, 65, 2))
b_n, a_n = iirnotch(60.0, 30.0, FS)
HP = butter(3, 1.0, btype="high", fs=FS, output="sos")
HF = butter(4, [100.0, 600.0], btype="band", fs=FS, output="sos")

files = [os.path.join(V_DIR, f) for f in ("best_m1609_s1.npz", "ied_m1609_s1.npz", "windows_m1609.npz")] + EXTRA
seen, rows = {}, []
# baseline high-frequency RMS per contact, from the recording's random windows
base = []
z = np.load(os.path.join(V_DIR, "ied_m1609_s1.npz"))
for i in np.flatnonzero(z["kind"] == "base"):
    x = filtfilt(b_n, a_n, z["X"][i].astype(float), axis=-1)
    base.append(np.sqrt(np.mean(sosfiltfilt(HF, x, axis=-1)[:, 500:-500] ** 2, axis=1)))
BASE_HF = np.median(np.array(base), axis=0)                       # (64,)

for f in files:
    z = np.load(f)
    n = z["X"].shape[-1]
    tt = np.arange(n) / FS - float(z["half"])
    for i in np.flatnonzero(z["kind"] == "lock_spike"):
        tv = float(z["t"][i])
        key = round(tv, 2)
        if key in seen:
            continue
        seen[key] = f
        X = filtfilt(b_n, a_n, z["X"][i].astype(float), axis=-1)
        V = sosfiltfilt(HP, X[[c - 1 for c in EVEN]], axis=-1)
        V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
        near = (tt >= -0.04) & (tt <= 0.04)
        A = np.abs(V[:, near])
        r = int(np.argmax(A.max(1)))                                # largest contact (row in EVEN)
        s = V[r]
        jn = np.flatnonzero(near)[int(np.argmax(np.abs(s[near])))]
        pk = s[jn]
        sg = np.sign(pk)
        # half-width on that contact
        L = jn
        while L > 0 and sg * s[L] > abs(pk) / 2:
            L -= 1
        R = jn
        while R < n - 1 and sg * s[R] > abs(pk) / 2:
            R += 1
        fwhm = (R - L) / FS * 1000
        # prominence: the peak against the biggest same-sign swing elsewhere in +-300 ms (outside +-60 ms of the peak)
        far = (np.abs(tt - tt[jn]) > 0.06) & (np.abs(tt - tt[jn]) < 0.3)
        other = np.max(sg * s[far])
        prom_ratio = abs(pk) / max(other, 1.0)
        # high-frequency burst: 100-600 Hz RMS within +-20 ms of the peak over the recording's baseline, per contact
        H = sosfiltfilt(HF, X, axis=-1)
        win = (tt >= tt[jn] - 0.02) & (tt <= tt[jn] + 0.02)
        hf_db = 20 * np.log10(np.sqrt(np.mean(H[:, win] ** 2, axis=1)) / BASE_HF)
        # depth: contacts (of 32) over half the peak at the peak moment
        depth = int(np.sum(np.abs(V[:, jn]) > abs(pk) / 2))
        # sharpness of the whole event: amplitude at the peak / mean |V| over +-60 ms (narrow events score high)
        rows.append(dict(t=tv, src=os.path.basename(f), csc=EVEN[r], peak_uv=float(pk), off_ms=float(tt[jn] * 1000), fwhm_ms=fwhm,
                         prom_ratio=float(prom_ratio), hf_db_max=float(np.nanmax(np.delete(hf_db, [58]))),
                         hf_db_med=float(np.median(np.delete(hf_db, [58]))), depth32=depth))

import pandas as pd
d = pd.DataFrame(rows)
zs = lambda v: (v - v.mean()) / v.std()                              # noqa: E731
d["score"] = zs(np.log(d.peak_uv.abs())) + zs(np.log(d.prom_ratio)) - zs(np.log(d.fwhm_ms)) + zs(d.hf_db_med)
d = d.sort_values("score", ascending=False)
d.to_csv(OUT, index=False)
print(d.round(2).to_string())
