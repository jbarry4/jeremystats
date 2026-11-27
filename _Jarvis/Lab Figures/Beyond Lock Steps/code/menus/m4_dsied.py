"""Story menu, step 4 (round 3): dentate spikes, borderline transients (BTs) and IEDs in the SAME five IED+
sessions, read through one pipeline (m2_extract). Writes dsied.pkl.

Depth comes from each recording's own DS (uprof.pkl, never the lab's layer labels): contacts are placed on the
blade-to-blade axis u (0 = upper DS sink peak, 1 = lower). Every class of one mouse is scaled by the SAME number,
that mouse's mean DS deepest sink, so DS, BT and IED can be compared on one scale.
CSD: second spatial difference over 20 um contacts after a 1-2-1 smoothing, sink negative; bad contacts filled
by a straight line between their neighbors before the CSD is taken.
"""
import os
import pickle
import sys

import numpy as np
import pandas as pd
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PITCH_MM = 0.020
IED_PLUS = ["m13", "m28", "m3", "m5", "m34"]
PROF = pickle.load(open(os.path.join(HERE, "profiles_ds.pkl"), "rb"))
UP = pickle.load(open(os.path.join(HERE, "uprof.pkl"), "rb"))
UGRID, DG_U, REG = UP["UGRID"], UP["DG_U"], UP["regions"]
REGIONS = [("ca1", -9.0, REG["top"]), ("upper_distal", REG["top"], 0.0), ("upper_proximal", 0.0, REG["gu"]),
           ("hilus", REG["gu"], REG["gl"]), ("lower_proximal", REG["gl"], 1.0), ("lower_distal", 1.0, REG["bot"])]
rc = pd.read_pickle(os.path.join(HERE, "rc_events.pkl"))
rc = rc[rc.wf == "halo"].copy()
KIND = {"ds": "DS", "halo_ds": "DS", "both": "TZ", "halo_amb": "TZ", "pspike": "IED", "halo_pspike": "IED", "neither": "far"}
rc["kind"] = rc.cls.map(KIND).fillna("none")


def fill_rows(x, bad_rows):
    """x: (..., 64, T). Bad rows replaced by a straight line between their good neighbors."""
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
    """x: (..., 64, T) potentials in uV. 1-2-1 smoothing across contacts, then -d2/dz2 (uV/mm2); edges nan."""
    x = np.asarray(x, float)
    s = x.copy()
    s[..., 1:-1, :] = 0.25 * x[..., :-2, :] + 0.5 * x[..., 1:-1, :] + 0.25 * x[..., 2:, :]
    c = np.full_like(s, np.nan)
    c[..., 1:-1, :] = -(s[..., :-2, :] - 2 * s[..., 1:-1, :] + s[..., 2:, :]) / (PITCH_MM ** 2)
    return c


def hf_power(x, fs, lo=240.0, hi=420.0, half_ms=16.5):
    """Band power around the centre vs the first window of the read (100 ms before the centre), per contact, dB."""
    b, a = signal.butter(3, [lo / (fs / 2), hi / (fs / 2)], btype="band")
    y = signal.filtfilt(b, a, x, axis=-1)
    T = x.shape[-1]
    c = T // 2
    h = int(round(half_ms * fs / 1000))
    ev = (y[..., c - h:c + h + 1] ** 2).mean(axis=-1)
    base = (y[..., 5:5 + 2 * h + 1] ** 2).mean(axis=-1)
    return 10 * np.log10(np.maximum(ev, 1e-12) / np.maximum(base, 1e-12))


def on_u(rows_u, prof, good):
    """A per-row profile (64,) or (64, T) put on UGRID through the good rows (nan beyond the probe)."""
    p = np.asarray(prof, float)
    ok = good & np.isfinite(rows_u)
    xs = rows_u[ok]
    o = np.argsort(xs)
    if p.ndim == 1:
        ys = p[ok][o]
        f = np.isfinite(ys)
        return np.interp(UGRID, xs[o][f], ys[f], left=np.nan, right=np.nan)
    out = np.full((UGRID.size, p.shape[1]), np.nan)
    for j in range(p.shape[1]):
        ys = p[ok, j][o]
        f = np.isfinite(ys)
        if f.sum() >= 2:
            out[:, j] = np.interp(UGRID, xs[o][f], ys[f], left=np.nan, right=np.nan)
    return out


out = {"UGRID": UGRID, "regions": REG}
for lab in IED_PLUS:
    z = np.load(os.path.join(HERE, "reads", "%s.npz" % lab), allow_pickle=True)
    U = UP["recs"][("v6", lab)]
    assert [int(x) for x in z["nums"]] == list(U["contacts"]), lab
    fs = float(z["fs"])
    kind = z["kind"].astype(str)
    bad_rows = [int(b) - 1 for b in z["bad"]]
    band = fill_rows(z["band"], bad_rows)
    notch = fill_rows(z["notch"], bad_rows)
    T = band.shape[-1]
    t_ms = (np.arange(T) - T // 2) / fs * 1000.0
    csd_b = csd_of(band)
    csd_w = csd_of(notch)
    rows_u = np.asarray(U["rows_u"], float)
    good = np.ones(rows_u.size, bool)
    good[bad_rows] = False
    good &= np.isfinite(csd_b[0, :, 0])                     # the two edge rows have no CSD
    # polarity against the room's own CSD of the same recording (its DS mean profile at the peak)
    ref_prof = PROF[("v6", lab)]["peak"]
    pk_w = np.abs(t_ms) <= 3
    mine = np.nanmean(csd_b[kind == "DS"][:, :, pk_w].mean(axis=-1), axis=0)
    ok = np.isfinite(ref_prof) & np.isfinite(mine) & good
    r = np.corrcoef(ref_prof[ok], mine[ok])[0, 1]
    sign = 1.0 if r >= 0 else -1.0
    csd_b *= sign
    csd_w *= sign
    # one scale for every class of this mouse: its DS mean deepest sink on the DS-defined dentate rows
    dg = good & (rows_u >= DG_U[0]) & (rows_u <= DG_U[1])
    ds_peak = np.nanmean(csd_b[kind == "DS"][:, :, pk_w].mean(axis=-1), axis=0)
    refsz = -np.nanmin(np.where(dg, ds_peak, np.nan))
    hf = hf_power(z["notch"].astype(float), fs)            # n x 64 dB (raw potentials; bad rows blanked below)
    hf[:, ~good] = np.nan
    d = {"lab": lab, "t_ms": t_ms, "fs": fs, "polarity_r": r, "ref": refsz, "classes": {}, "rows_u": rows_u}
    for k in ("DS", "TZ", "IED"):
        sel = kind == k
        if sel.sum() < 2:
            continue
        mb = np.nanmean(csd_b[sel], axis=0)
        mw = np.nanmean(csd_w[sel], axis=0)
        pk = mb[:, pk_w].mean(axis=-1)
        pk_ev = csd_b[sel][:, :, pk_w].mean(axis=-1)
        d["classes"][k] = {
            "n": int(sel.sum()), "u_band": on_u(rows_u, mb / refsz, good), "u_wide": on_u(rows_u, mw / refsz, good),
            "u_peak": on_u(rows_u, pk / refsz, good), "u_hf": on_u(rows_u, np.nanmean(hf[sel], axis=0), good),
            "u_peak_sem": on_u(rows_u, np.nanstd(pk_ev, axis=0) / np.sqrt(sel.sum()) / refsz, good),
        }
    # per-event features: the deepest sink on the dentate rows (over the DS mean), fast power per DS-defined region
    pk_ev = csd_b[:, :, pk_w].mean(axis=-1)
    sink_rel = -np.nanmin(np.where(dg[None, :], pk_ev, np.nan), axis=1) / refsz
    ev = pd.DataFrame({"lab": lab, "kind": kind, "t": z["refined_s"], "amp": z["amp"], "hf_rc": z["hf"], "hw": z["hw"], "gb": z["gb"],
                       "ga": z["ga"], "sink_rel": sink_rel})
    for name, lo, hi in REGIONS:
        rr = good & (rows_u >= lo) & (rows_u < hi)
        ev["hf_" + name] = np.nanmean(hf[:, rr], axis=1) if rr.any() else np.nan
    d["events"] = ev
    # hand-sorted IEDs: which class each landed in (nearest Root Canal event within 25 ms)
    hand = z["hand_t"]
    allrc = rc[rc.lab == lab]
    got = []
    for t in hand:
        dt = np.abs(allrc.t.to_numpy() - t)
        j = int(np.argmin(dt)) if dt.size else -1
        got.append((float(t), allrc.kind.iloc[j] if j >= 0 and dt[j] <= 0.025 else "unmatched", float(dt[j]) if j >= 0 else np.nan))
    d["hand"] = got
    d["minutes"] = float(allrc.t.max() - allrc.t.min()) / 60.0
    out[lab] = d
    print(lab, "polarity r %.2f" % r, "ref %.4g" % refsz, {k: v["n"] for k, v in d["classes"].items()},
          "sink_rel medians", {k: round(float(ev[ev.kind == k].sink_rel.median()), 2) for k in ("DS", "TZ", "IED")}, flush=True)
with open(os.path.join(HERE, "dsied.pkl"), "wb") as f:
    pickle.dump(out, f, protocol=4)
print("saved")
