"""What a recording says about depth: Sextant's evidence, per contact.

Everything here is read from StrataScope's scan of the recording (the per
second bins and the 1250 Hz copy, backend/stratasteps.py) and, for the
dentate events, from Root Canal's Halo workflow run (6fa7fef7b7a3 v5): its
per-event class and time for every recording of the pilot. Nothing reads a
layer label.

Rows are H3 contacts, top first: contact k is CSC k (StrataScope reads every
PTEN recording as an H3 in the recording's own channel order). A channel
that was not read, or is on the recording's bad list, is a NaN row.

The evidence, all saved as plain arrays in one .npz per recording:

    curves      per-contact averages from the bins (StrataScope's profile):
                multiunit, ripple power in still time, theta / delta / three
                gamma bands while walking, theta phase and coherence, and the
                coherence of each contact with its neighbour
    theta_cx    the theta wave's own depth profile: the leading eigenvector
                of the theta cross-spectrum while walking (complex: amplitude
                and phase at every contact, one rhythm)
    ripples     Toothy's ripples on the CA1 cell-layer contact, and the
                ripple-triggered average (sharp wave) with its CSD, and the
                ripple-band power at every contact during them
    trough      the theta-trough-triggered average with its CSD
    ds / ps / bt   dentate spikes, P-spikes and borderline transients
                (Root Canal's classes), each averaged, with its CSD
"""
from __future__ import annotations

import json
import os

import numpy as np

from .. import lazyimp
from .. import stratasteps as st

_sig = lazyimp.module("scipy.signal")

N = 64
PITCH_UM = 20.0
RC_RUN = ("6fa7fef7b7a3", 5)              # Root Canal Halo workflow
RC_KIND = {"ds": "ds", "halo_ds": "ds", "both": "bt", "halo_amb": "bt",
           "pspike": "ps", "halo_pspike": "ps"}
SCHEMA = 1


def rc_events(logs_dir, gid):
    """{kind: sorted times (s)} for one recording from the Halo run."""
    wf, v = RC_RUN
    folder = os.path.join(logs_dir, "artifacts", "snap", wf)
    path = None
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.startswith("v%d__" % v):
            path = os.path.join(folder, name)
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        c = json.load(f)["run"]["cols"]
    gids = c["gids"]
    if gid not in gids:
        return {}
    gi = gids.index(gid)
    out = {"ds": [], "bt": [], "ps": []}
    for g, cl, t in zip(c["g"], c["cls"], c["t"]):
        if g != gi or t is None:
            continue
        k = RC_KIND.get(str(cl))
        if k:
            out[k].append(float(t))
    return {k: np.sort(np.asarray(v, float)) for k, v in out.items()}


def _rows(b):
    """Contact index 0..63 -> bins row (or -1)."""
    return np.array([b.row.get(k + 1, -1) for k in range(N)], int)


def _bad_mask(rows, bad):
    badset = {int(x) for x in bad or []}
    return np.array([(rows[k] < 0) or ((k + 1) in badset) for k in range(N)], bool)


def _order(rows):
    return [k + 1 for k in range(N) if rows[k] >= 0]


def _full(vals, rows):
    """A per-read-row vector (in `_order` order) back onto 64 contacts."""
    out = np.full(N, np.nan)
    j = 0
    for k in range(N):
        if rows[k] >= 0:
            out[k] = vals[j]
            j += 1
    return out


def _fill(v, is_bad):
    v = np.array(v, float, copy=True)
    good = np.flatnonzero(~is_bad & np.isfinite(v))
    if good.size < 2:
        return v
    bad = np.flatnonzero(is_bad | ~np.isfinite(v))
    v[bad] = np.interp(bad, good, v[good])
    return v


def csd(lfp, is_bad):
    """CSD (uA/mm^3-ish units, sink negative) of a depth profile or a
    (64 x T) block: bad rows filled by straight lines first, 1-2-1 smoothed,
    second difference over 20 um. The two edge rows are NaN."""
    a = np.array(lfp, float, copy=True)
    one = a.ndim == 1
    if one:
        a = a[:, None]
    good = np.flatnonzero(~is_bad)
    for i in np.flatnonzero(is_bad):
        for t in range(a.shape[1]):
            a[i, t] = np.interp(i, good, a[good, t])
    k = np.array([0.25, 0.5, 0.25])
    p = np.vstack([a[:1], a, a[-1:]])
    s = k[0] * p[:-2] + k[1] * p[1:-1] + k[2] * p[2:]
    h = PITCH_UM / 1000.0
    out = np.full_like(s, np.nan)
    # CSD = -sigma d2V/dz2 (sigma = 1): a sink is where the potential has a
    # trough (positive curvature), so sinks come out negative.
    out[1:-1] = -(s[:-2] - 2 * s[1:-1] + s[2:]) / (h * h)
    return out[:, 0] if one else out


def _states(logs_dir, gid, b, bad):
    """Theta Walk bouts: what somebody painted in StrataScope when there is
    any (behaviour, not layers), else the finder's ghost bouts."""
    import glob
    best = None
    for f in glob.glob(os.path.join(logs_dir, "layers", gid + "@*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tw = ((d.get("strata_states") or {}).get("theta_walk") or [])
        if tw and (best is None or str(d.get("updated")) > best[0]):
            best = (str(d.get("updated")), tw)
    if best:
        return {"theta_walk": best[1]}, "painted"
    g = st.guide(b, bad=bad)
    return {"theta_walk": g["ghost"]}, "finder"


def _peak_profile(avg, t_ms, is_bad, half_ms=3.0, search_ms=12.0):
    """The depth profile at an event's peak: the time (within +-search_ms) of
    the largest deflection of the contact that deflects most, averaged over
    +-half_ms around it."""
    a = np.where(is_bad[:, None], np.nan, avg)
    w = np.abs(t_ms) <= search_ms
    with np.errstate(all="ignore"):
        r = int(np.nanargmax(np.nanmax(np.abs(a[:, w]), axis=1)))
        j = int(np.nanargmax(np.abs(a[r, w])))
    t0 = float(t_ms[w][j])
    m = np.abs(t_ms - t0) <= half_ms
    return np.nanmean(avg[:, m], axis=1), t0


def _triggered(b, times, order, bad, half_ms, max_events=400):
    tr = st.triggered(b, times, order=order, bad=bad, spacing_um=PITCH_UM,
                      half_ms=half_ms, max_events=max_events)
    return np.asarray(tr["lfp"], float), np.asarray(tr["t_ms"], float), tr["n_total"]


def _band_rms_at(b, rows_read, times, lo, hi, half_ms=20.0, base_ms=(-200, -100),
                 max_events=300):
    """Per contact: band RMS in +-half_ms around each time, over the same in a
    baseline window, averaged over events (a ratio, >1 = more than before)."""
    lfs = float(b.meta["lfp_fs"])
    mm = b.lfp()
    if mm is None or not len(times):
        return None
    t = np.asarray(times, float)
    if t.size > max_events:
        t = np.sort(np.random.default_rng(0).choice(t, max_events, replace=False))
    w = int(round(0.35 * lfs))
    k = np.rint(t * lfs).astype(np.int64)
    k = k[(k - w >= 0) & (k + w < mm.shape[1])]
    if not k.size:
        return None
    nyq = lfs / 2.0
    sos = _sig.butter(3, [lo / nyq, min(hi, 0.95 * nyq) / nyq], btype="band", output="sos")
    idx = k[:, None] + np.arange(-w, w + 1)[None, :]
    tt = np.arange(-w, w + 1) / lfs * 1000.0
    on = np.abs(tt) <= half_ms
    off = (tt >= base_ms[0]) & (tt <= base_ms[1])
    out = []
    for r in rows_read:
        seg = np.asarray(mm[r][idx], float) * float(b.lfp_scale[r])
        y = _sig.sosfiltfilt(sos, seg, axis=1)
        a = np.sqrt(np.mean(y[:, on] ** 2, axis=1))
        c = np.sqrt(np.mean(y[:, off] ** 2, axis=1))
        out.append(float(np.median(a / np.maximum(c, 1e-9))))
    return np.asarray(out)


def gather(logs_dir, rec, log=print):
    """Everything above for one recording (a cohort dict). Returns a dict of
    arrays and small facts; save it with `save`."""
    gid = rec["gid"]
    b = st.load(gid)
    rows = _rows(b)
    order = _order(rows)
    bad = sorted(set(rec.get("bad") or []) | {k + 1 for k in range(N) if rows[k] < 0})
    is_bad = _bad_mask(rows, bad)
    states, how = _states(logs_dir, gid, b, bad)
    mk = st.masks(b, states, {})
    out = {"gid": gid, "schema": SCHEMA, "is_bad": is_bad, "states_how": how,
           "walk_s": mk["walk_s"], "still_s": mk["still_s"], "all_s": mk["all_s"],
           "theta_all_time": mk["theta_all_time"]}

    prof = st.profile(b, mk, order=order, bad=bad)
    for k, v in prof["curves"].items():
        out["c_" + k] = _full(v, rows)
    # delta in still time, theta in still time (for ratios)
    P = b.power[[rows[k] for k in range(N) if rows[k] >= 0]]
    out["c_delta_still"] = _full(st._mean_over(P[:, :, st.BAND_INDEX["delta"]], mk["still"]), rows)
    out["c_theta_still"] = _full(st._mean_over(P[:, :, st.BAND_INDEX["theta"]], mk["still"]), rows)
    out["c_ripple_walk"] = _full(st._mean_over(P[:, :, st.BAND_INDEX["ripple"]], mk["walk"]), rows)
    for i, (name, _lo, _hi) in enumerate(st.BANDS):
        out["c_%s_all" % name] = _full(st._mean_over(P[:, :, i], mk["all"]), rows)

    # the theta wave's own profile: leading eigenvector of the cross-spectrum
    rr = [rows[k] for k in range(N) if rows[k] >= 0]
    X = b.theta_x[rr][:, mk["walk"], :].reshape(len(rr), -1).astype(np.complex128)
    good = ~np.array([is_bad[k] for k in range(N) if rows[k] >= 0])
    Xg = X[good]
    S = Xg @ Xg.conj().T / max(1, Xg.shape[1])
    w, V = np.linalg.eigh(S)
    v1 = V[:, -1] * np.sqrt(max(w[-1], 0.0))
    frac = float(w[-1] / max(np.sum(w), 1e-30))
    v = np.full(len(rr), np.nan + 0j)
    v[good] = v1
    vfull = np.full(N, np.nan + 0j)
    j = 0
    for k in range(N):
        if rows[k] >= 0:
            vfull[k] = v[j]
            j += 1
    # phase zero at the largest-amplitude contact, so the sign is fixed
    i_max = int(np.nanargmax(np.abs(vfull)))
    vfull = vfull * np.exp(-1j * np.angle(vfull[i_max]))
    out["theta_cx"] = vfull
    out["theta_cx_frac"] = frac

    # Ripples on the CA1 cell-layer contact. Not StrataScope's pick_sp (the
    # ripple maximum above the theta maximum): in these mice raw ripple-band
    # power climbs into the dentate (dentate-spike energy), so that pick lands
    # one contact above the theta peak. Here: the topmost clear local maximum
    # of ripple / theta power in still time (Toothy's ratio), checked against
    # multiunit activity -- the pyramidal layer is where both peak.
    sp_k = sp_contact(out)
    sp_ch = (sp_k + 1) if sp_k is not None else None
    out["sp_channel"] = sp_ch or 0
    out["n_ripples"] = 0
    if sp_ch:
        rip = st.detect_ripples(b, sp_ch, mk)
        times = [e["t"] for e in rip["events"]]
        out["n_ripples"] = len(times)
        out["ripple_rate"] = rip.get("rate_per_min") or 0.0
        if len(times) >= 20:
            avg, t_ms, n = _triggered(b, times, order, bad, half_ms=150.0)
            out["rip_avg"] = np.vstack([_full(avg[:, i], rows) for i in range(avg.shape[1])]).T
            out["rip_t"] = t_ms
            lp = _sig.sosfiltfilt(_sig.butter(3, 40.0 / (625.0), output="sos"), out["rip_avg"], axis=1)
            m = np.abs(t_ms) <= 15
            base = (np.abs(t_ms) >= 100)
            out["spw"] = np.nanmean(lp[:, m], axis=1) - np.nanmean(lp[:, base], axis=1)
            rp = _band_rms_at(b, rr, times, 120.0, 180.0)
            if rp is not None:
                out["rip_power"] = _full(rp, rows)
    # theta troughs on the contact with the most walking theta (above the
    # dentate -- any contact will do for timing; the profile is what counts)
    th = np.where(is_bad, np.nan, out["c_theta"])
    th_ch = int(np.nanargmax(th)) + 1
    tr = st.theta_troughs(b, th_ch, mk)
    out["n_troughs"] = int(tr.size)
    if tr.size >= 50:
        avg, t_ms, n = _triggered(b, tr, order, bad, half_ms=90.0, max_events=1500)
        out["trough_avg"] = np.vstack([_full(avg[:, i], rows) for i in range(avg.shape[1])]).T
        out["trough_t"] = t_ms
        m = np.abs(t_ms) <= 8
        out["trough"] = np.nanmean(out["trough_avg"][:, m], axis=1)

    # dentate events from Root Canal
    ev = rc_events(logs_dir, gid)
    for kind in ("ds", "ps", "bt"):
        t = ev.get(kind, np.zeros(0))
        out["n_" + kind] = int(t.size)
        if t.size >= 5:
            avg, t_ms, n = _triggered(b, t, order, bad, half_ms=60.0)
            full = np.vstack([_full(avg[:, i], rows) for i in range(avg.shape[1])]).T
            pk, t0 = _peak_profile(full, t_ms, is_bad)
            out[kind + "_avg"] = full
            out[kind + "_t"] = t_ms
            out[kind + "_peak"] = pk
            out[kind + "_peak_ms"] = t0
            # the spread of single events' sinks: each event's CSD at its own
            # peak, so a mixture of sink depths (DS1 vs DS2) shows as two
            # clusters even when the mean has one
            if kind == "ds":
                out["ds_event_csd"] = _event_csds(b, t, rows, is_bad, t0)
    log("   evidence:", gid, "walk %.0fs still %.0fs (%s)" % (out["walk_s"], out["still_s"], how),
        "ripples", out["n_ripples"], "troughs", out["n_troughs"],
        "DS", out["n_ds"], "P", out["n_ps"], "BT", out["n_bt"])
    return out


def _local_max(v, k, w=2):
    lo, hi = max(0, k - w), min(v.size, k + w + 1)
    seg = v[lo:hi]
    return np.isfinite(v[k]) and v[k] >= np.nanmax(seg)


def _z(v):
    v = np.asarray(v, float)
    m, s = np.nanmedian(v), np.nanstd(v)
    return (v - m) / s if s > 0 else v * 0


def sp_contact(ev):
    """0-based contact of CA1's pyramidal layer, or None: above the walking
    theta maximum (the cell layer is always above the fissure), the contact
    where ripple / theta power in still time (Toothy's ratio) and multiunit
    activity together stand highest. Not the topmost peak: a probe that
    starts in radiatum has a high ratio at its top edge that is not a peak
    of anything."""
    bad = ev["is_bad"]
    with np.errstate(all="ignore"):
        r = np.log(ev["c_ripple"] / ev["c_theta_still"])
    r = np.where(bad, np.nan, r)
    th = np.where(bad, np.nan, ev["c_theta"])
    if not np.isfinite(th).any() or not np.isfinite(r).any():
        return None
    k_th = int(np.nanargmax(th))
    n = max(k_th - 2, 4)
    top = r[:n]
    mua = np.where(bad, np.nan, ev["c_mua"])[:n]
    if not np.isfinite(top).any():
        return None
    score = _z(top) + 0.7 * np.nan_to_num(_z(mua))
    score = np.where(np.isfinite(top), score, np.nan)
    k = int(np.nanargmax(score))
    return k


def _event_csds(b, times, rows, is_bad, t0_ms, max_events=400):
    lfs = float(b.meta["lfp_fs"])
    mm = b.lfp()
    t = np.asarray(times, float) + t0_ms / 1000.0
    if t.size > max_events:
        t = np.sort(np.random.default_rng(1).choice(t, max_events, replace=False))
    k = np.rint(t * lfs).astype(np.int64)
    h = max(1, int(round(0.003 * lfs)))
    k = k[(k - 50 >= 0) & (k + 50 < mm.shape[1])]
    out = np.full((k.size, N), np.nan)
    for c in range(N):
        r = rows[c]
        if r < 0:
            continue
        x = np.asarray(mm[r], float)
        seg = np.stack([x[k + d] for d in range(-h, h + 1)], 1).mean(1)
        base = np.stack([x[k + d] for d in range(-50, -30)], 1).mean(1)
        out[:, c] = (seg - base) * float(b.lfp_scale[r])
    return np.vstack([csd(o, is_bad) for o in out]) if k.size else out


def save(path, ev):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arrays = {k: v for k, v in ev.items() if isinstance(v, np.ndarray)}
    facts = {k: v for k, v in ev.items() if not isinstance(v, np.ndarray)}
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, facts=json.dumps(facts, default=float), **arrays)
    os.replace(tmp, path)


def load(path):
    z = np.load(path, allow_pickle=False)
    ev = json.loads(str(z["facts"]))
    for k in z.files:
        if k != "facts":
            ev[k] = z[k]
    return ev
