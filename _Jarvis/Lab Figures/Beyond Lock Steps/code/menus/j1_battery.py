"""Jeremy menu, step 2: per-mouse numbers from the frozen DS battery (every Halo DS, 1 kHz, +-50 ms), on the Halo set
(v6) and on every filter set (b_*), for Jeremy's questions 1, 2, 3 and 5. Writes jeremy_battery.pkl.

Depth comes from each recording's own DS (dsdata landmarks), never from layer labels:
  blade-to-blade u: 0 = upper main sink, 1 = lower main sink; dentate rows = u in [-0.6, 1.6]
  along each blade v: 0 = that blade's cell-layer source, 1 = its average DS sink (middle molecular layer)
  MML = v 0.7 to 1.3, OML = v 1.3 to 2.0 (asked 2026-11-24)
Per event:
  sink        the deepest dentate sink at the DS peak (+-3 ms)
  main-sink time course: minus the CSD at the two main-sink rows, averaged; its peak (within 5 ms of the DS peak),
  rise (10 to 90% of the peak, ms), slope (0.8 x peak / rise: like an fEPSP slope), decay (90 to 10%, ms)
  layer sinks minus the CSD at the DS peak averaged over the MML or OML rows of each blade
Per mouse: the median over events (all DS, DS1, DS2 by the recording's winner split). Sizes are put on one common
scale per filter set: divided by the control mice's average of their median deepest sink (so control = 1).
"""
import os
import pickle
import sys

import numpy as np
import pandas as pd
from scipy import stats as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import dsdata  # noqa: E402

SETS = ["v6", "b_ds", "b_none", "b_1_100", "b_1_300", "b_5_300", "b_5_50", "b_10_40"]
# Layer check (2026-11-25): JM_LAYERS=tight takes the MML / OML contacts from tight_layers.json (each DS type's own sink,
# +-40 um, split at the midpoint) instead of the v ranges, the same contacts on every filter set; writes
# jeremy_battery_tight.pkl. Nothing else changes.
TIGHT = os.environ.get("JM_LAYERS") == "tight"
TL = None
if TIGHT:
    import json
    TL = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tight_layers.json"), encoding="utf-8"))["mice"]
CTL = ["m2", "m21", "m22", "m26", "m59", "m60", "m61"]
LAYERS = {"MML": (0.7, 1.3), "OML": (1.3, 2.0)}


def fill_bad_tc(csd, bad):
    """events x 64 x T: fill bad rows along depth."""
    if not bad:
        return csd
    x = np.array(csd, float, copy=True)
    n = x.shape[1]
    good = np.array([i for i in range(n) if i not in bad])
    for b in sorted(bad):
        below, above = good[good < b], good[good > b]
        if below.size and above.size:
            g0, g1 = below[-1], above[0]
            w = (b - g0) / float(g1 - g0)
            x[:, b, :] = (1 - w) * x[:, g0, :] + w * x[:, g1, :]
        else:
            x[:, b, :] = x[:, (below[-1] if below.size else above[0]), :]
    return x


def crossing(y, i, level, step):
    """Walk from index i in direction step until y falls below level; the crossing time by linear interpolation
    (in samples, fractional). nan if it never does."""
    j = i
    while 0 <= j + step < y.size:
        k = j + step
        if y[k] < level:
            a, b = y[j], y[k]
            frac = (a - level) / (a - b) if a != b else 0.5
            return j + step * frac
        j = k
    return np.nan


def time_course_numbers(s, t_ms):
    """s: events x T main-sink time course (sink positive). Peak, rise, slope, decay per event."""
    c = int(np.argmin(np.abs(t_ms)))
    w = int(round(5 / np.median(np.diff(t_ms))))
    dt = float(np.median(np.diff(t_ms)))
    out = np.full((s.shape[0], 4), np.nan)
    for e in range(s.shape[0]):
        y = s[e]
        i = c - w + int(np.argmax(y[c - w:c + w + 1]))
        P = y[i]
        if not np.isfinite(P) or P <= 0:
            continue
        t10, t90 = crossing(y, i, 0.1 * P, -1), crossing(y, i, 0.9 * P, -1)
        d90, d10 = crossing(y, i, 0.9 * P, +1), crossing(y, i, 0.1 * P, +1)
        rise = (t90 - t10) * dt
        decay = (d10 - d90) * dt
        out[e] = [P, rise, 0.8 * P / rise if rise > 0 else np.nan, decay]
    return out


def med(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.median(x)) if x.size >= 3 else np.nan


rc = pd.read_pickle(os.path.join(HERE, "rc_events.pkl"))
rc = rc[(rc.wf == "halo") & (rc.cls.isin(["ds", "halo_ds"]))]
out = {"sets": SETS, "layers": LAYERS, "per": {}, "ref": {}, "events_v6": {}}
for es in SETS:
    recs = dsdata.load(es)
    per = {}
    for r in recs:
        if r.lab in ("m6", "m51") or r.landmarks is None:
            continue
        k = r.landmarks
        bad = list(r.bad_rows)
        good = np.array([i not in bad for i in range(len(r.contacts))])
        csd = fill_bad_tc(np.asarray(r.csd, float), bad)
        t_ms = np.asarray(r.t_ms, float)
        pk = csd[:, :, np.abs(t_ms) <= 3].mean(axis=2)
        rows = np.arange(pk.shape[1])
        u = r.u(rows)
        dg = good & (u >= -0.6) & (u <= 1.6)
        sink = -np.nanmin(np.where(dg[None, :], pk, np.nan), axis=1)
        s = 0.5 * (-csd[:, k["rowU"], :] - csd[:, k["rowL"], :])
        tc = time_course_numbers(s, t_ms)
        lay = {}
        for blade in ("upper", "lower"):
            v = r.v(rows, blade)
            for name, (lo, hi) in LAYERS.items():
                if TIGHT:
                    m = np.zeros(len(rows), bool)
                    m[TL[r.lab]["rows"][blade][name]] = True
                    m &= good
                else:
                    m = good & (v >= lo) & (v < hi)
                lay[(blade, name)] = -pk[:, m].mean(axis=1) if m.any() else np.full(pk.shape[0], np.nan)
        t = np.asarray(r.labels["winner"]["types"]) if (r.winner and "winner" in r.labels) else np.zeros(r.n, int)

        def own_rows_tc(sel):
            """A DS type is timed at ITS OWN sink: in each blade, the contact (on the far side of that blade's cell-layer
            source) where the type's mean CSD at the peak is deepest; the two blades averaged."""
            m = pk[sel].mean(axis=0)
            rr = []
            for blade in ("upper", "lower"):
                cand = r.far_rows(blade)
                cand = cand[good[cand]] if cand.size else cand
                if cand.size:
                    rr.append(int(cand[np.argmin(m[cand])]))
            if not rr:
                return np.full((int(sel.sum()), 4), np.nan), rr
            s_own = np.mean([-csd[sel][:, q, :] for q in rr], axis=0)
            return time_course_numbers(s_own, t_ms), rr

        def summary(sel, own=False):
            tcs = own_rows_tc(sel)[0] if own else tc[sel]
            return {"n": int(sel.sum()), "sink": med(sink[sel]), "peak": med(tcs[:, 0]), "rise": med(tcs[:, 1]),
                    "slope": med(tcs[:, 2]), "decay": med(tcs[:, 3]),
                    "layers": {kk: med(vv[sel]) for kk, vv in lay.items()}}
        d = {"all": summary(np.ones(r.n, bool)), "si": r.winner_si, "winner": r.winner, "dur_min": float(r.dur_min),
             "n": int(r.n), "n1": int((t == 1).sum()), "n2": int((t == 2).sum()), "ko": float(r.ko), "subgroup": r.subgroup}
        for kk in (1, 2):
            if (t == kk).sum() >= 5:
                d["ds%d" % kk] = summary(t == kk, own=True)
        per[r.lab] = d
        if es == "v6":
            ev = {"times_s": np.asarray(r.times_s, float), "sink": sink, "peak": tc[:, 0], "rise": tc[:, 1], "slope": tc[:, 2],
                  "types": t}
            # Root Canal fast power of the same events (matched by time, 5 ms)
            h = rc[rc.lab == r.lab]
            ht = h.t.to_numpy(float)
            o = np.argsort(ht)
            hs = ht[o]
            j = np.clip(np.searchsorted(hs, ev["times_s"]), 1, max(hs.size - 1, 1))
            j = np.where(np.abs(hs[j - 1] - ev["times_s"]) <= np.abs(hs[j] - ev["times_s"]), j - 1, j)
            hit = np.abs(hs[j] - ev["times_s"]) <= 0.005
            ev["hf"] = np.where(hit, h.hf.to_numpy(float)[o][j], np.nan)
            ev["amp"] = np.where(hit, h.amp.to_numpy(float)[o][j], np.nan)
            out["events_v6"][r.lab] = ev
            print(r.lab, "matched to Root Canal: %d of %d" % (int(hit.sum()), r.n), flush=True)
    ref = float(np.mean([per[l]["all"]["sink"] for l in CTL if l in per]))
    out["per"][es] = per
    out["ref"][es] = ref
    print(es, "control reference %.4g" % ref, "mice", len(per), flush=True)
    del recs
with open(os.path.join(HERE, "jeremy_battery_tight.pkl" if TIGHT else "jeremy_battery.pkl"), "wb") as fh:
    pickle.dump(out, fh, protocol=4)
print("saved")
