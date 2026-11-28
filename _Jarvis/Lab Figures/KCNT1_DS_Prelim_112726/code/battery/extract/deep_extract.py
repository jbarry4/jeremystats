"""Everything per event and per recording the room holds, for one room
version (argv 1; 6 = Halo, 8 = No P-spikes), pickled. Read only."""
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import dsmix, sinkcut  # noqa: E402
from backend import extraction as EX  # noqa: E402

V = int(sys.argv[1]) if len(sys.argv) > 1 else 6
HERE = os.path.dirname(os.path.abspath(__file__))
c = app.test_client()
room = A._er_rooms()[os.environ.get("KROOM", "dentate_spike_kcnt1")]
j = c.get("/api/extraction/%s?version=%d" % (room["id"], V)).get_json()
mode = dict(j["mode"])
seps = j.get("seps") or {}


def fwhm(y, i0, step):
    """Full width at half the height of y at i0 (y positive there), by
    straight lines between samples; nan when it runs off an end."""
    h = y[i0] / 2.0
    if not np.isfinite(h) or h <= 0:
        return np.nan
    out = []
    for d in (-1, 1):
        k = i0
        while 0 <= k + d < y.size and y[k + d] > h:
            k += d
        if not (0 <= k + d < y.size):
            return np.nan
        out.append(abs(k - i0) + (y[k] - h) / (y[k] - y[k + d]))
    return float(sum(out) * step)


recs = []
for r in j["payload"]["recordings"]:
    Ar, rule, flip = A._er_split_arrays(r)
    L = A._dspca_load(r["gid"], r["read"])
    n = int(Ar["prof"].shape[0])
    prof, ns = sinkcut.stamp_profiles(Ar)
    prof = np.asarray(prof, float)
    na = [int(x) for x in Ar["nums_all"]]
    disp = np.nan_to_num(np.asarray(Ar["disp"], float))
    T = disp.shape[2]
    tt = np.linspace(-50, 50, T)
    sel = [na.index(x) for x in ns]
    d = {"gid": r["gid"], "label": r["session_label"], "lab": r["session_label"].split()[1],
         "g": "CTL" if str(r["group"]).upper() == "CTL" else "PTEN",
         "ko": float(r.get("ko_now", r.get("ko_pct")) or 0.0), "n": n, "dur": float(r.get("duration_s") or 0),
         "sep": (seps.get(r["gid"]) or {}).get("verdict"), "ns": ns, "prof": prof.astype(np.float32),
         "csd_mean": disp[:, sel, :].mean(axis=0).astype(np.float32), "tt": tt,
         "saved": A._er_rec_split(r), "interp": r.get("interp"), "twin": r.get("twin")}
    rows = L["rows"]
    d["rows_n"] = len(rows)
    times = np.array([float(x.get("refined_s") or x.get("stamp_s")) for x in rows])
    d["times"] = times if times.size == n else None
    d["peak"] = np.array([float(x.get("peak_uv_mm2") or np.nan) for x in rows]) if times.size == n else None
    # the event, in space: the deepest sink, its width, the two blades
    neg = np.maximum(0.0, -prof)
    i0 = neg.argmax(axis=1)
    d["sink_peak"] = neg.max(axis=1)
    d["sink_total"] = neg.sum(axis=1)
    d["source_peak"] = np.maximum(0.0, prof).max(axis=1)
    pos = np.arange(prof.shape[1]) * 50.0
    w = neg / np.maximum(neg.sum(axis=1, keepdims=True), 1e-12)
    cen = (w * pos).sum(axis=1)
    d["sink_centroid"] = cen
    d["sink_spread"] = np.sqrt((w * (pos[None, :] - cen[:, None]) ** 2).sum(axis=1))
    d["sink_width"] = np.array([fwhm(neg[i], i0[i], 50.0) for i in range(n)])
    hc = sinkcut.hump_cut(prof.mean(axis=0))
    d["hump_cut"] = hc
    if hc is not None:
        top, bot = neg[:, :hc], neg[:, hc:]
        d["top_peak"], d["bot_peak"] = top.max(axis=1), bot.max(axis=1)
        d["blade_gap"] = (hc + bot.argmax(axis=1) - top.argmax(axis=1)) * 50.0
        m = np.maximum(0.0, -prof.mean(axis=0))
        d["blade_gap_mean"] = float((hc + m[hc:].argmax() - m[:hc].argmax()) * 50.0)
    # the event, in time: the sink's length at its deepest contact
    rows_i = np.array(sel)[i0]
    tr = -disp[np.arange(n), rows_i, :]
    c0 = int(np.argmin(np.abs(tt)))
    dur = []
    for i in range(n):
        k = c0 - 5 + int(np.argmax(tr[i, c0 - 5:c0 + 6]))
        dur.append(fwhm(tr[i], k, tt[1] - tt[0]))
    d["sink_ms"] = np.array(dur)
    # the LFP, when the read keeps it
    try:
        raw = np.asarray((L.get("sur") or {}).get("raw"), float)
        d["raw_shape"] = raw.shape
        if raw.ndim == 3 and raw.shape[0] == n:
            nums = [int(x) for x in L["nums"]]
            rs_ = [nums.index(x) for x in ns if x in nums]
            Tl = raw.shape[2]
            tl = np.linspace(-50, 50, Tl)
            base = np.abs(tl) > 30
            x = raw[:, rs_, :] - np.median(raw[:, rs_, :][:, :, base], axis=2, keepdims=True)
            cl = int(np.argmin(np.abs(tl)))
            at = x[:, :, cl - 3:cl + 4].mean(axis=2)
            ch = at.argmax(axis=1)
            d["lfp_amp"] = at.max(axis=1)
            trl = x[np.arange(n), ch, :]
            d["lfp_ms"] = np.array([fwhm(trl[i], cl - 5 + int(np.argmax(trl[i, cl - 5:cl + 6])), tl[1] - tl[0]) for i in range(n)])
            d["lfp_mean"] = x.mean(axis=0).astype(np.float32)
    except Exception as exc:  # noqa: BLE001
        d["raw_err"] = str(exc)
    # every split, on one yardstick
    d["splits"] = {}
    for m in EX.SPLIT_METHODS:
        try:
            Ax, types, Lm = A._er_layers(r, m, None, mode)
            sc = A._er_overlap_scores(Ax, types, m) or {}
            rs = dsmix.relsink(Ax, types)
            e = {"types": np.asarray(types, int), "si": sc.get("si"), "n1": int((types == 1).sum()), "n2": int((types == 2).sum()),
                 "mix": ((Lm["mix"] or {}).get("plain") or {}).get("est"),
                 "x": np.asarray(Ax["x_" + m], float), "why": rs.get("why")}
            if not rs.get("why"):
                e.update(oml=rs["oml"], mml=rs["mml"], score=rs["score"], floor=rs["floor"], sinkom=rs["sink"], lag=rs["lag_ms"])
            d["splits"][m] = e
        except Exception as exc:  # noqa: BLE001
            d["splits"][m] = {"err": str(exc)}
    # the saved split (the Impression's), with its cut
    try:
        sm, scut = d["saved"]
        Ax, types, Lm = A._er_layers(r, sm, scut, mode)
        rs = dsmix.relsink(Ax, types)
        sc = A._er_overlap_scores(Ax, types, sm) or {}
        e = {"method": sm, "cut": scut, "types": np.asarray(types, int), "si": sc.get("si"),
             "mix": ((Lm["mix"] or {}).get("plain") or {}).get("est"), "why": rs.get("why")}
        if not rs.get("why"):
            e.update(oml=rs["oml"], mml=rs["mml"], score=rs["score"], floor=rs["floor"], sinkom=rs["sink"], lag=rs["lag_ms"])
        d["saved_split"] = e
    except Exception as exc:  # noqa: BLE001
        d["saved_split"] = {"err": str(exc)}
    try:
        t = c.get("/api/extraction/%s/timeline?version=%d&gid=%s" % (room["id"], V, r["gid"])).get_json()
        th = t.get("theta") or {}
        d["theta_t"], d["theta_p"] = np.array(th.get("t") or [], float), np.array(th.get("power") or [], float)
        ev = t.get("events")
        d["tl_events"] = ev if not isinstance(ev, list) else np.array([e_.get("t") if isinstance(e_, dict) else e_ for e_ in ev], float)
    except Exception as exc:  # noqa: BLE001
        d["theta_err"] = str(exc)
    recs.append(d)
    print("%-10s %-4s n %4d rows %4d raw %s hump %s lfp %s theta %d splits ok %d" % (
        d["lab"], d["g"], n, d["rows_n"], d.get("raw_shape"), hc, "lfp_amp" in d, len(d.get("theta_t", [])),
        sum(1 for v in d["splits"].values() if "err" not in v)), flush=True)
with open(os.path.join(HERE, "deep_v%d.pkl" % V), "wb") as f:
    pickle.dump(recs, f)
print("saved", len(recs))
