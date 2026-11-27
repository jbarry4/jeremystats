"""THE BEFORE/AFTER BATTERY (asked 2026-11-18: "the activity a bit after and
before the DS ... sometimes there's a bit of oscillations or some activity
before and after").

Reads the windows made by the scratchpad's around_read.py (+-500 ms around
every Halo-set event and around as many random moments of the same recording,
at least 1 s from any event; LFP, band power of the CSD in six bands, and
multi-unit activity). One number per recording per measure, pushed through
harness.Battery like the rest of the battery (family "around").

Windows (ms from the DS peak; the DS itself, +-50 ms, is left out):
  pre_far -500..-200, pre_near -150..-50, post_near 50..150, post_far 200..500
Depth: the blade-to-blade scale u (0 = upper blade's main sink, 1 = lower),
in bins of 0.5 from -2 to 3 (u < 0 is toward CA1 above), and the whole shank.
Kinds (all relative, so no absolute amplitude is compared between mice):
  power   log2(event's band power / the mean over random windows), median over events
  prepost log2(post / pre) of the same event (near and far), median over events
  locked  how much of the band activity lines up from event to event: power of
          the average CSD over the mean power of single events, divided by the
          same for random windows (1 = no more locking than chance)
  burst   share of events with a burst (band power above the random windows'
          95th percentile for 2 cycles of the band's center frequency) minus
          the share of random windows with one
Events: all; DS1 and DS2 of the winning classifier with DS3 taken out (and
DS1 over DS2). "v8" = the same measure over the events also in the No
P-spikes set.

  python around_measures.py        -> results_around/around.pkl
then  BATTERY_OUT=results_around BATTERY_MERGED=merged_around python analyze.py
"""
import os
import sys
import warnings

import numpy as np
from scipy import signal as sg

import dsdata
from harness import Battery

warnings.filterwarnings("ignore")
HERE = dsdata.HERE
SRC = os.path.join(HERE, "data", "around")      # made by extract/around_read.py
BANDS = ["1-4", "4-12", "15-30", "30-60", "60-100", "100-250", "MUA"]
BAND_WORD = {"1-4": "1–4 Hz (delta)", "4-12": "4–12 Hz (theta)", "15-30": "15–30 Hz (beta)", "30-60": "30–60 Hz (low gamma)",
             "60-100": "60–100 Hz (high gamma)", "100-250": "100–250 Hz (ripple band)", "MUA": "multi-unit activity (300–3000 Hz)"}
CENTER = {"1-4": 2.5, "4-12": 8.0, "15-30": 22.5, "30-60": 45.0, "60-100": 80.0, "100-250": 175.0, "MUA": 100.0}
EDGES = {"1-4": (1, 4), "4-12": (4, 12), "15-30": (15, 30), "30-60": (30, 60), "60-100": (60, 100), "100-250": (100, 250)}
TB = np.arange(-50, 51) * 10.0                       # bin centers, ms
WIN = {"pre_far": (-500, -200), "pre_near": (-150, -50), "post_near": (50, 150), "post_far": (200, 500)}
U_BINS = [(lo, lo + 0.5) for lo in np.arange(-2.0, 3.0, 0.5)]
MIN_EV = 10


def depth_sets(r):
    """{name: rows} for the u bins (good rows only, edge rows left out) and the shank."""
    rows = np.array([x for x in r.good(np.arange(1, 63))], int)
    u = r.u(rows)
    out = {"shank": rows}
    for lo, hi in U_BINS:
        m = (u >= lo) & (u < hi)
        if m.sum() >= 1:
            out["u%+.1f_%+.1f" % (lo, hi)] = rows[m]
    return out


def load(r):
    p = os.path.join(SRC, r.lab + ".npz")
    if not os.path.isfile(p):
        return None
    z = np.load(p)
    ok = z["done"]
    kind, t = z["kind"], z["t"]
    ev_t = t[kind == 0]
    # the read's events are the room's rows, in order; matched to the dataset by time
    o = np.argsort(ev_t)
    j = np.clip(np.searchsorted(ev_t[o], r.times_s), 0, ev_t.size - 1)
    idx = o[j]
    good = np.abs(ev_t[idx] - r.times_s) < 0.002
    E = z["env"].astype(np.float32)
    Lf = z["lfp"].astype(np.float32)
    evE, rdE = E[kind == 0][idx], E[(kind == 1) & ok]
    evL, rdL = Lf[kind == 0][idx], Lf[(kind == 1) & ok]
    evok = ok[kind == 0][idx] & good
    return dict(evE=evE, rdE=rdE, evL=evL, rdL=rdL, evok=evok)


def csd(L):
    C = np.zeros_like(L)
    C[:, 1:-1] = -(L[:, :-2] - 2.0 * L[:, 1:-1] + L[:, 2:])
    return C


def locked_ratio(Cev, Crd, rows, band, w):
    """Power of the average over the mean single-event power, events over random."""
    lo, hi = EDGES[band]
    sos = sg.butter(3, [lo, hi], btype="band", fs=1000.0, output="sos")
    t = np.arange(-500, 501)
    tm = (t >= w[0]) & (t <= w[1])

    def share(C):
        if C.shape[0] < MIN_EV:
            return np.nan
        X = sg.sosfiltfilt(sos, C[:, rows, :], axis=2)[:, :, tm]
        avg = (X.mean(axis=0) ** 2).mean()
        single = (X ** 2).mean()
        return avg / single if single > 0 else np.nan
    a, b = share(Cev), share(Crd)
    return float(a / b) if np.isfinite(a) and np.isfinite(b) and b > 0 else np.nan


def burst_share(Eev, Erd, rows, bi, band, w):
    """Excess share of events with a burst in window w (region-mean envelope)."""
    k = max(2, int(np.ceil(2000.0 / CENTER[band] / 10.0)))
    tm = (TB >= w[0]) & (TB <= w[1])
    if tm.sum() < k:
        return np.nan
    ev = Eev[:, bi, rows, :].mean(axis=1)[:, tm]
    rd = Erd[:, bi, rows, :].mean(axis=1)[:, tm]
    thr = np.percentile(Erd[:, bi, rows, :].mean(axis=1), 95)

    def has(X):
        above = X > thr
        run = np.zeros(X.shape[0], int)
        best = np.zeros(X.shape[0], int)
        for c in range(X.shape[1]):
            run = np.where(above[:, c], run + 1, 0)
            best = np.maximum(best, run)
        return best >= k
    return float(has(ev).mean() - has(rd).mean())


def main():
    B = Battery("around", outdir=os.path.join(HERE, "results_around"))
    R6 = [r for r in dsdata.load("v6") if r.ok and r.landmarks is not None]
    R8 = {r.lab: r for r in dsdata.load("v8") if r.ok}
    vals = {}
    for r in R6:
        D = load(r)
        if D is None:
            print("no read", r.lab, flush=True)
            continue
        Cev, Crd = csd(D["evL"]), csd(D["rdL"])
        mrd = D["rdE"].mean(axis=0)                     # 7 x 64 x 101, random mean
        mrd[mrd <= 0] = np.nan
        t_w = r.types("winner") if r.winner else None
        m3 = r.ds3("winner") if r.winner else None
        masks = {"all": D["evok"]}
        if t_w is not None:
            m3 = np.zeros(r.n, bool) if m3 is None else m3
            masks["ds1x"] = D["evok"] & (t_w == 1) & ~m3
            masks["ds2x"] = D["evok"] & (t_w == 2) & ~m3
        b8 = R8.get(r.lab)
        if b8 is not None and b8.times_s is not None:
            in8 = np.array([np.min(np.abs(b8.times_s - t)) < 0.005 for t in r.times_s])
        else:
            in8 = np.ones(r.n, bool)
        dsets = depth_sets(r)
        for es, sel in (("v6", np.ones(r.n, bool)), ("v8", in8)):
            for var, m in masks.items():
                m = m & sel
                if m.sum() < MIN_EV:
                    continue
                Eev = D["evE"][m]
                for bi, band in enumerate(BANDS):
                    lr = np.log2(np.maximum(Eev[:, bi], 1e-12) / mrd[bi][None])     # events x 64 x 101
                    for dn, rows in dsets.items():
                        x = np.nanmean(lr[:, rows, :], axis=1)                      # events x 101
                        per = {}
                        for wn, (a, b) in WIN.items():
                            tm = (TB >= a) & (TB <= b)
                            per[wn] = np.nanmean(x[:, tm], axis=1)
                            vals.setdefault(("power", band, wn, dn, var, es), {})[r.lab] = float(np.nanmedian(per[wn]))
                        for nm, (a, b) in (("near", ("pre_near", "post_near")), ("far", ("pre_far", "post_far"))):
                            vals.setdefault(("prepost", band, nm, dn, var, es), {})[r.lab] = float(np.nanmedian(per[b] - per[a]))
                        for wn, w in WIN.items():
                            if band not in ("1-4", "4-12"):
                                vals.setdefault(("burst", band, wn, dn, var, es), {})[r.lab] = burst_share(Eev, D["rdE"], rows, bi, band, w)
        t = np.arange(-500, 501)
        for band in [b_ for b_ in BANDS if b_ in EDGES and b_ != "1-4"]:
            lo, hi = EDGES[band]
            sos = sg.butter(3, [lo, hi], btype="band", fs=1000.0, output="sos")
            Fev = sg.sosfiltfilt(sos, Cev, axis=2).astype(np.float32)
            Frd = sg.sosfiltfilt(sos, Crd, axis=2).astype(np.float32)
            for wn, w in WIN.items():
                tm = (t >= w[0]) & (t <= w[1])
                for dn, rows in dsets.items():
                    Xr = Frd[:, rows][:, :, tm]
                    br = (Xr.mean(axis=0) ** 2).mean() / max((Xr ** 2).mean(), 1e-30)
                    for es, sel in (("v6", np.ones(r.n, bool)), ("v8", in8)):
                        for var, m in masks.items():
                            m = m & sel
                            if m.sum() < MIN_EV:
                                continue
                            X = Fev[m][:, rows][:, :, tm]
                            a_ = (X.mean(axis=0) ** 2).mean() / max((X ** 2).mean(), 1e-30)
                            # chance locking falls as 1/n: compare with random windows of the same count
                            nr = min(m.sum(), Frd.shape[0])
                            Xr2 = Frd[:nr][:, rows][:, :, tm]
                            br2 = (Xr2.mean(axis=0) ** 2).mean() / max((Xr2 ** 2).mean(), 1e-30)
                            vals.setdefault(("locked", band, wn, dn, var, es), {})[r.lab] = float(a_ / br2) if br2 > 0 else np.nan
            del Fev, Frd
        print(r.lab, "done", flush=True)
    WORD = {"power": "band power over random moments of the same recording (log2, median over events)",
            "prepost": "band power after over before the same event (log2, median over events)",
            "locked": "activity lined up from event to event (power of the average over mean single-event power), over the same for random moments",
            "burst": "share of events with a burst (2 cycles above the random moments' 95th percentile) minus the share of random moments with one"}
    for (kind, band, wn, dn, var, es), v in vals.items():
        name = "%s_%s_%s_%s" % (kind, band, wn, dn)
        desc = "%s, %s, %s ms, %s" % (WORD[kind], BAND_WORD[band], {"near": "50–150 vs −150–−50", "far": "200–500 vs −500–−200"}.get(wn, "%d to %d" % WIN.get(wn, (0, 0))),
                                      "whole shank" if dn == "shank" else "depth " + dn)
        B.add("around", name, v, desc, "log2" if kind in ("power", "prepost") else ("ratio" if kind == "locked" else "share"), es,
              "" if var == "all" else "winner", var)
    # DS1 over DS2 (power, both windows near)
    for (kind, band, wn, dn, var, es), v in list(vals.items()):
        if var != "ds1x" or kind != "power":
            continue
        v2 = vals.get((kind, band, wn, dn, "ds2x", es), {})
        d = {lab: v[lab] - v2[lab] for lab in v if lab in v2 and np.isfinite(v[lab]) and np.isfinite(v2[lab])}
        B.add("around", "power_%s_%s_%s" % (band, wn, dn), d, "DS1 minus DS2: " + WORD[kind] + ", " + BAND_WORD[band], "log2", es, "winner", "ds1x_minus_ds2x")
    B.save()
    print("around measures %d, tests %d" % B.count(), flush=True)


if __name__ == "__main__":
    main()
