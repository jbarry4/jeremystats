"""Jeremy menu, step 3: dominant frequency and layer sinks from the 2 kHz X-ray reads (one pipeline for every mouse),
for Jeremy's questions 4, 5, 7 and 8. Writes jeremy_freq.pkl.

Reads: reads/<lab>.npz (the five IED+ mice: every Root Canal event) and reads_ds/<lab>.npz (the other 11: their DS).
Layers (from each recording's own DS, uprof.pkl landmarks; no layer labels): along each blade v = 0 at its cell-layer
source, 1 at its average DS sink; MML = v 0.7 to 1.3, OML = v 1.3 to 2.0; the good contacts in each range averaged.
Signals: CSD (1-2-1 smoothing, second difference at 20 um, sink negative, polarity matched to the room) and LFP.
Bands: the notched broadband, and the battery's six band-passes applied to the +-100 ms windows (zero-phase third-order
Butterworth, reflection padding; on windows this short a 1 to 10 Hz low cut acts mainly as a baseline removal).
Per event and layer:
  sink        minus the CSD at the DS peak (+-3 ms)
  fast        event (+-25 ms) over baseline (-100 to -50 ms) power, dB, every frequency (Hann window, 2,048-point FFT);
              per mouse and class the mean over events; its dominant frequency is the peak in 100 to 500 Hz
  whole       the event's own power spectrum over +-50 ms; per mouse and class the mean; its peak and its centroid in
              5 to 300 Hz (within the band's pass range)
"""
import os
import pickle
import sys
import warnings

import numpy as np
from scipy import signal

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402

PITCH_MM = 0.020
IEDP = ["m13", "m28", "m3", "m5", "m34"]
BANDS = {"notch": None, "5-100": (5, 100), "1-100": (1, 100), "1-300": (1, 300), "5-300": (5, 300), "5-50": (5, 50), "10-40": (10, 40)}
LAYERS = {"MML": (0.7, 1.3), "OML": (1.3, 2.0)}
NFFT = 2048
UP = pickle.load(open(os.path.join(HERE, "uprof.pkl"), "rb"))
PROF = pickle.load(open(os.path.join(HERE, "profiles_ds.pkl"), "rb"))


def fill_rows(x, bad_rows):
    x = np.array(x, float, copy=True)
    if not bad_rows:
        return x
    n = x.shape[-2]
    good = np.array([i for i in range(n) if i not in bad_rows])
    for b in sorted(bad_rows):
        below, above = good[good < b], good[good > b]
        if below.size and above.size:
            g0, g1 = below[-1], above[0]
            w = (b - g0) / float(g1 - g0)
            x[..., b, :] = (1 - w) * x[..., g0, :] + w * x[..., g1, :]
        else:
            x[..., b, :] = x[..., (below[-1] if below.size else above[0]), :]
    return x


def csd_of(x):
    s = x.copy()
    s[..., 1:-1, :] = 0.25 * x[..., :-2, :] + 0.5 * x[..., 1:-1, :] + 0.25 * x[..., 2:, :]
    c = np.full_like(s, np.nan)
    c[..., 1:-1, :] = -(s[..., :-2, :] - 2 * s[..., 1:-1, :] + s[..., 2:, :]) / (PITCH_MM ** 2)
    return c


def psd(seg, fs):
    """seg: (..., n) -> power on the rfft grid of NFFT points (Hann window, linear trend removed)."""
    seg = signal.detrend(seg, axis=-1)
    w = np.hanning(seg.shape[-1])
    X = np.fft.rfft(seg * w, n=NFFT, axis=-1)
    return (np.abs(X) ** 2) / (w ** 2).sum()


out = {"bands": list(BANDS), "layers": LAYERS, "mice": {}}
for lab in F.LABS:
    path = os.path.join(HERE, "reads", lab + ".npz") if lab in IEDP else os.path.join(HERE, "reads_ds", lab + ".npz")
    if not os.path.exists(path):
        print(lab, "no reads", flush=True)
        continue
    z = np.load(path, allow_pickle=True)
    fs = float(z["fs"])
    kind = z["kind"].astype(str)
    keep = np.isin(kind, ["DS", "TZ", "IED"])
    kind = kind[keep]
    bad_rows = [int(b) - 1 for b in z["bad"]]
    notch = fill_rows(z["notch"][keep].astype(float), bad_rows)
    band_reader = fill_rows(z["band"][keep].astype(float), bad_rows)
    T = notch.shape[-1]
    t_ms = (np.arange(T) - T // 2) / fs * 1000.0
    U = UP["recs"][("v6", lab)]
    lm = U["landmarks"]
    rows = np.arange(notch.shape[1])
    good = np.array([i not in bad_rows for i in rows])
    good[[0, rows.size - 1]] = False
    vrow = {"upper": (lm["GU"] - rows) / (lm["GU"] - lm["U"]), "lower": (rows - lm["GL"]) / (lm["L"] - lm["GL"])}
    lay_rows = {(b, n): np.where(good & (vrow[b] >= lo) & (vrow[b] < hi))[0] for b in ("upper", "lower") for n, (lo, hi) in LAYERS.items()}
    ru = np.asarray(U["rows_u"], float)
    dg = good & (ru >= -0.6) & (ru <= 1.6)
    # polarity: the reader's 5-100 Hz CSD of the DS against the room's mean DS profile of the same recording
    pk_w = np.abs(t_ms) <= 3
    cb = csd_of(band_reader)
    mine = np.nanmean(cb[kind == "DS"][:, :, pk_w].mean(axis=-1), axis=0)
    ref = PROF[("v6", lab)]["peak"]
    ok = np.isfinite(ref) & np.isfinite(mine) & good
    sign = 1.0 if np.corrcoef(ref[ok], mine[ok])[0, 1] >= 0 else -1.0
    ev_w = (t_ms >= -25) & (t_ms <= 25)
    bl_w = (t_ms >= -100) & (t_ms <= -50)
    wh_w = (t_ms >= -50) & (t_ms <= 50)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / fs)
    res = {"n": {k: int((kind == k).sum()) for k in ("DS", "TZ", "IED")}, "freqs": freqs, "bands": {}, "lay_rows": {str(k): v.tolist() for k, v in lay_rows.items()},
           "sign": sign}
    for bname, band in BANDS.items():
        if band is None:
            x = notch
        else:
            b_, a_ = signal.butter(3, [band[0] / (fs / 2), band[1] / (fs / 2)], btype="band")
            x = signal.filtfilt(b_, a_, notch, axis=-1, padtype="odd")
        c = csd_of(x) * sign
        lfp = x * sign
        pk = c[:, :, pk_w].mean(axis=-1)
        deep = -np.nanmin(np.where(dg[None, :], pk, np.nan), axis=1)
        br = {"deep": {}, "sink": {}, "fast": {}, "whole": {}, "fast_spec": {}, "whole_spec": {}}
        for k in ("DS", "TZ", "IED"):
            sel = kind == k
            if sel.sum() < 2:
                continue
            br["deep"][k] = float(np.nanmedian(deep[sel]))
            for key, rr in lay_rows.items():
                if rr.size == 0:
                    continue
                cl = c[sel][:, rr, :].mean(axis=1)            # events x T
                ll = lfp[sel][:, rr, :].mean(axis=1)
                br["sink"][(k,) + key] = float(np.nanmedian(-cl[:, pk_w].mean(axis=-1)))
                for sname, sig in (("csd", cl), ("lfp", ll)):
                    pe, pb = psd(sig[:, ev_w], fs), psd(sig[:, bl_w], fs)
                    db = np.nanmean(10 * np.log10(np.maximum(pe, 1e-30) / np.maximum(pb, 1e-30)), axis=0)
                    fr = (freqs >= 100) & (freqs <= 500)
                    if band is None or band[1] >= 300:
                        i = int(np.argmax(np.where(fr, db, -np.inf)))
                        br["fast"][(k,) + key + (sname,)] = (float(freqs[i]), float(db[i]))
                        br["fast_spec"][(k,) + key + (sname,)] = db.astype(np.float32)
                    pw = np.nanmean(psd(sig[:, wh_w], fs), axis=0)
                    lo_f, hi_f = (5, 300) if band is None else (max(5, band[0]), min(300, band[1]))
                    m = (freqs >= lo_f) & (freqs <= hi_f)
                    i = int(np.argmax(np.where(m, pw, -np.inf)))
                    cen = float((pw[m] * freqs[m]).sum() / pw[m].sum())
                    br["whole"][(k,) + key + (sname,)] = (float(freqs[i]), cen)
                    if bname == "notch":
                        br["whole_spec"][(k,) + key + (sname,)] = pw.astype(np.float32)
        if bname == "5-100":
            # check against the reader's own 5-100 Hz band (filtered on the continuous signal)
            pk_r = (csd_of(band_reader) * sign)[:, :, pk_w].mean(axis=-1)
            deep_r = -np.nanmin(np.where(dg[None, :], pk_r, np.nan), axis=1)
            br["check_reader_vs_window"] = float(np.corrcoef(deep_r[kind == "DS"], deep[kind == "DS"])[0, 1])
        res["bands"][bname] = br
    out["mice"][lab] = res
    nb = res["bands"]["notch"]
    print(lab, res["n"], "sign %+d" % sign, "check r %.3f" % res["bands"]["5-100"].get("check_reader_vs_window", np.nan),
          "fast CSD upper MML %s" % (nb["fast"].get(("DS", "upper", "MML", "csd")),), flush=True)
with open(os.path.join(HERE, "jeremy_freq.pkl"), "wb") as fh:
    pickle.dump(out, fh, protocol=4)
print("saved")
