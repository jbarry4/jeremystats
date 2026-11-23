"""Freezing the inputs of Extraction Room 2.0 into one versioned bundle.

The bundle is built from the DS/PTEN battery's frozen sets (a folder made by
the battery: data/ds_v6.pkl, data/ds_b_*.pkl, data/around/*.npz and the merged
per-mouse tables). Building it needs that folder; using it needs only the
bundle, which is what goes to the VACC and to colleagues.

What is in it (all float32, NaN where a value cannot be made):
  events      one row per Halo-set event of every recording that is in the
              battery (m6 and m51 are not):
                waveform + depth-profile measures at the DS (measures.event_features)
                context: interval before / after, time in the recording,
                  detector peak, theta percentile
                the winner's call as four 0/1 columns (DS1, DS2, DS3, too small
                  to score DS3)
                the same waveform / depth measures under the six other filters
                power before / after the DS: log2 over random moments of the
                  same recording, 7 bands x 4 windows x 11 depths, and after
                  over before (7 x 2 x 11)
  mice        one row per recording: the battery's per-mouse numbers (Halo
              set; all events and the winner's types), the before/after
              battery's per-mouse numbers (locking, bursts), and nuisance
              values (placement geometry, year, event count, length, bad
              contacts) kept apart as family "nuisance"
  labels      group, subgroup (CTL / IED- / IED+), knockout %

  python -m backend.er2.amber <battery folder>
"""
import datetime
import hashlib
import json
import os
import sys

import numpy as np

ROOT = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Jarvis", "er2")
AMBER = os.path.join(ROOT, "amber")
FILTERS = ["b_none", "b_1_100", "b_1_300", "b_5_300", "b_5_50", "b_10_40"]
CONTEXT = ("iei_prev", "iei_next", "t_frac", "theta_pct", "det_peak")
FILTER_FEATS = ("sink_amp", "sink_upper", "sink_lower", "sink_fwhm", "sink_asym", "sink_area", "sink_pre", "sink_post", "source_amp",
                "source_fwhm", "source_over_sink", "blade_balance", "net_between", "cen_v", "cen_um", "sink_width_um", "outer_share",
                "lat_lower_minus_upper", "lat_source_minus_sink", "lfp_src", "lfp_fwhm", "lfp_pre", "lfp_post", "lfp_pos_u")


def _fingerprint(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        st = os.stat(p)
        h.update(("%s|%d|%d" % (os.path.basename(p), st.st_size, int(st.st_mtime))).encode())
    return h.hexdigest()[:16]


RAW_U = np.round(np.arange(-0.6, 1.61, 0.1), 2)        # blade-to-blade depth (0 upper main sink, 1 lower)
RAW_T = np.arange(-30, 31, 3)                          # ms around the DS peak
SPEC_U = np.round(np.arange(-0.6, 1.61, 0.2), 2)
SPEC_T = np.arange(-500, 501, 50)                      # ms; 50 ms bins centered here


def _on_u(A, r, grid):
    """A: events x rows x time -> events x len(grid) x time, by linear
    interpolation between contacts on the recording's own blade-to-blade axis;
    bad contacts are NaN (so a grid point next to one is NaN)."""
    k = r.landmarks
    pos = k["U"] + grid * (k["L"] - k["U"])
    A = np.asarray(A, float).copy()
    if len(r.bad_rows):
        A[:, list(r.bad_rows), :] = np.nan
    lo = np.floor(pos).astype(int)
    fr = pos - lo
    out = np.full((A.shape[0], grid.size, A.shape[2]), np.nan)
    for g in range(grid.size):
        a, b = lo[g], lo[g] + 1
        if 0 <= a and b < A.shape[1]:
            out[:, g, :] = A[:, a, :] * (1 - fr[g]) + A[:, b, :] * fr[g]
    return out


def raw_columns(r, AM, D):
    """The raw event (2026-11-20, asked: "feed in the raw waveform and CSD and
    power spectrogram"), on axes every recording shares:
      raw_csd__u{u}_t{ms}   CSD on the blade-to-blade axis x -30..+30 ms
                            (3 ms), in units of the recording's own mean main
                            sink (so sizes compare across mice)
      raw_lfp__u{u}_t{ms}   the LFP (uV, each contact's baseline off) the same way
      raw_spec__{band}_u{u}_t{ms}  power, log2 over random moments of the
                            same recording, 7 bands x depth x -500..+500 ms (50 ms)
    """
    cols = {}
    it = np.array([int(np.argmin(np.abs(r.t_ms - t))) for t in RAW_T])
    prof = np.asarray(r.mean_csd_peak, float)
    k = r.landmarks
    ref = np.nanmax(np.abs([prof[int(round(k["U"]))], prof[int(round(k["L"]))]]))
    ref = ref if np.isfinite(ref) and ref > 0 else 1.0
    for nm, A, sc in (("csd", r.csd, ref), ("lfp", r.lfp, 1.0)):
        G = _on_u(np.asarray(A)[:, :, it], r, RAW_U) / sc
        for gi, u in enumerate(RAW_U):
            for ti, t in enumerate(RAW_T):
                cols["raw_%s__u%+.1f_t%+d" % (nm, u or 0.0, t)] = G[:, gi, ti]
    if D is not None:
        mrd = D["rdE"].mean(axis=0)
        mrd[mrd <= 0] = np.nan
        for bi, band in enumerate(AM.BANDS):
            lr = np.log2(np.maximum(D["evE"][:, bi], 1e-12) / mrd[bi][None])     # events x rows x 101 bins
            G = _on_u(lr, r, SPEC_U)
            for ti, t in enumerate(SPEC_T):
                tm = np.abs(AM.TB - t) <= 25
                v = np.nanmean(G[:, :, tm], axis=2)
                v = np.where(D["evok"][:, None], v, np.nan)
                for gi, u in enumerate(SPEC_U):
                    cols["raw_spec__%s_u%+.1f_t%+d" % (band, u or 0.0, t)] = v[:, gi]
    return cols


def _family_of_event(name):
    if name.startswith("raw_csd__"):
        return "raw CSD"
    if name.startswith("raw_lfp__"):
        return "raw LFP"
    if name.startswith("raw_spec__"):
        return "raw spectrogram"
    if name.startswith("type_"):
        return "ds type"
    if name.startswith("f_"):
        return "filter " + name.split("__")[0][2:]
    if name.startswith("ba_"):
        return "before/after " + name.split("_")[2]
    if name in CONTEXT:
        return "context"
    return "waveform/depth"


SET_NAMES = {"v6": "v6 (Halo)", "v8": "v8 (Strict)"}


def _rows_by_time(t_want, t_have, tol=0.005):
    """For each time in t_want, the row of t_have within tol (-1 when none)."""
    t_have = np.asarray(t_have, float)
    if t_have.size == 0:
        return np.full(len(t_want), -1)
    o = np.argsort(t_have)
    s = t_have[o]
    j = np.searchsorted(s, t_want)
    lo, hi = np.clip(j - 1, 0, s.size - 1), np.clip(j, 0, s.size - 1)
    pick = np.where(np.abs(s[lo] - t_want) <= np.abs(s[hi] - t_want), lo, hi)
    return np.where(np.abs(s[pick] - t_want) <= tol, o[pick], -1)


def build(battery_dir, out_root=AMBER, log=print, event_set="v6", raw=False):
    """Freeze the bundle; returns its manifest.

    event_set (2026-11-19): "v6" the Halo set (the default, as before) or
    "v8" the Strict set. The filter copies and the before/after windows are
    read for Halo events; a Strict event takes the row of the same event
    (matched by time, 5 ms), and its own winner call (the battery gives the
    Strict set the Halo set's)."""
    sys.path.insert(0, battery_dir)
    import dsdata
    import measures as MS
    import around_measures as AM
    import pandas as pd

    # A recording without a winner is IN (user, 2026-11-20: "I don't see any
    # reason not to include m21"): its events carry no DS type (all four type
    # columns 0 but "too small", which is 1), and its winner-only per-mouse
    # numbers are simply missing. m21 lost its winner when its duplicate
    # stamps went: no classifier keeps 5 events of each type after DS3.
    recs = [r for r in dsdata.load(event_set) if r.ok and r.landmarks is not None]
    labs = [r.lab for r in recs]
    filt = {es: {r.lab: r for r in dsdata.load(es)} for es in FILTERS}
    halo = {r.lab: r for r in dsdata.load("v6")} if event_set != "v6" else None
    rows, ev_mouse, names = [], [], None
    for mi, r in enumerate(recs):
        F = MS.event_features(r)
        cols = {}
        for k, v in F.items():
            v = np.asarray(v, float)
            if v.shape == (r.n,):
                cols[k] = v
        if r.winner:
            t = r.types("winner")
            s = np.asarray((r.ds3w.get("winner") or {}).get("score", np.full(r.n, np.nan)), float)
        else:
            t = np.zeros(r.n, int)
            s = np.full(r.n, np.nan)
        d3 = np.isfinite(s) & (np.abs(s) <= 0.5)
        cols["type_ds1"] = ((t == 1) & ~d3).astype(float)
        cols["type_ds2"] = ((t == 2) & ~d3).astype(float)
        cols["type_ds3"] = d3.astype(float)
        cols["type_unscored"] = (~np.isfinite(s)).astype(float)
        # Rows of the Halo-event copies (filters, before/after) for these events.
        hr = halo.get(r.lab) if halo is not None else None
        rows_h = _rows_by_time(r.times_s, hr.times_s) if hr is not None else np.arange(r.n)

        def take(v):
            v = np.asarray(v, float)
            return np.where(rows_h >= 0, v[np.maximum(rows_h, 0)], np.nan)
        for es in FILTERS:
            rb = filt[es].get(r.lab)
            if rb is None or rb.landmarks is None:
                for k in FILTER_FEATS:
                    cols["f_%s__%s" % (es[2:], k)] = np.full(r.n, np.nan)
                continue
            Fb = MS.event_features(rb)
            for k in FILTER_FEATS:
                cols["f_%s__%s" % (es[2:], k)] = take(Fb.get(k, np.full(rb.n, np.nan)))
        D = AM.load(r)   # matches the windows to these events by time itself
        if D is not None:
            mrd = D["rdE"].mean(axis=0)
            mrd[mrd <= 0] = np.nan
            dsets = AM.depth_sets(r)
            for bi, band in enumerate(AM.BANDS):
                lr = np.log2(np.maximum(D["evE"][:, bi], 1e-12) / mrd[bi][None])
                for dn, rws in dsets.items():
                    x = np.nanmean(lr[:, rws, :], axis=1)
                    per = {}
                    for wn, (a, b) in AM.WIN.items():
                        tm = (AM.TB >= a) & (AM.TB <= b)
                        per[wn] = np.nanmean(x[:, tm], axis=1)
                        cols["ba_pow_%s_%s_%s" % (band, wn, dn)] = np.where(D["evok"], per[wn], np.nan)
                    for nm, (a, b) in (("near", ("pre_near", "post_near")), ("far", ("pre_far", "post_far"))):
                        cols["ba_pp_%s_%s_%s" % (band, nm, dn)] = np.where(D["evok"], per[b] - per[a], np.nan)
        if raw:
            cols.update(raw_columns(r, AM, D))
        if names is None:
            names = sorted(cols)
        else:
            for k in cols:
                if k not in names:
                    names.append(k)
        rows.append(cols)
        ev_mouse.append(np.full(r.n, mi, np.int32))
        log("%-4s %4d events, %d event columns" % (r.lab, r.n, len(cols)))
    X = np.vstack([np.column_stack([c.get(k, np.full(len(next(iter(c.values()))), np.nan)) for k in names]) for c in rows]).astype(np.float32)
    ev_mouse = np.concatenate(ev_mouse)
    # mouse tables
    M = pd.read_pickle(os.path.join(battery_dir, "merged", "measures.pkl"))
    M = M[(M.event_set == event_set) & ((M.classifier == "") | (M.classifier == "winner"))]
    MA = pd.read_pickle(os.path.join(battery_dir, "merged_around", "measures.pkl"))
    MA = MA[(MA.event_set == event_set) & MA.name.str.startswith(("locked", "burst"))]
    mcols, mnames, mfam = [], [], []
    for df, fam in ((M, "battery"), (MA, "before/after (per mouse)")):
        for _, row in df.iterrows():
            v = np.array([row.get(l, np.nan) for l in labs], float)
            if np.isfinite(v).sum() >= 8 and np.nanstd(v) > 0:
                mcols.append(v)
                mnames.append("%s|%s|%s" % (row["family"], row["name"], row["variant"]))
                mfam.append(fam + " " + row["family"] if fam == "battery" else fam)
    for key, fn in (("rowU", lambda r: r.landmarks["rowU"]), ("rowL", lambda r: r.landmarks["rowL"]), ("rowGU", lambda r: r.landmarks["rowGU"]),
                    ("rowGL", lambda r: r.landmarks["rowGL"]), ("blade_um", lambda r: r.landmarks["blade_um"]),
                    ("gcl_to_sink_upper_um", lambda r: r.landmarks["gcl_to_sink_upper_um"]),
                    ("gcl_to_sink_lower_um", lambda r: r.landmarks["gcl_to_sink_lower_um"]), ("source_gap_um", lambda r: r.landmarks["source_gap_um"]),
                    ("band_contacts", lambda r: r.band[1] - r.band[0] + 1), ("n_bad", lambda r: len(r.bad)), ("year", lambda r: r.year),
                    ("n_events", lambda r: r.n), ("minutes", lambda r: r.dur_min), ("winner_row", lambda r: r.winner_row or np.nan),
                    ("winner_si", lambda r: r.winner_si if r.winner_si is not None else np.nan)):
        mcols.append(np.array([float(fn(r)) for r in recs]))
        mnames.append("nuisance|" + key)
        mfam.append("nuisance")
    XM = np.column_stack(mcols).astype(np.float32)
    srcs = [os.path.join(battery_dir, "data", "ds_v6.pkl"), os.path.join(battery_dir, "data", "ds_%s.pkl" % event_set)] + [os.path.join(battery_dir, "data", "ds_%s.pkl" % es) for es in FILTERS] + \
        [os.path.join(battery_dir, "merged", "measures.pkl"), os.path.join(battery_dir, "merged_around", "measures.pkl")]
    fp = _fingerprint(sorted(set(p for p in srcs if os.path.isfile(p))) + [os.path.join(AM.SRC, f) for f in os.listdir(AM.SRC)])
    # The event set and the recordings in it are part of what is frozen
    # (2026-11-20: m21 came in with the same files).
    fp = hashlib.sha256((fp + "|" + event_set + "|" + ",".join(labs) + ("|raw" if raw else "")).encode()).hexdigest()[:16]
    os.makedirs(out_root, exist_ok=True)
    have = sorted(int(d[1:]) for d in os.listdir(out_root) if d.startswith("v") and d[1:].isdigit())
    for v in have:
        mf = os.path.join(out_root, "v%d" % v, "manifest.json")
        if os.path.isfile(mf) and json.load(open(mf)).get("fingerprint") == fp:
            log("unchanged: amber v%d already holds these inputs" % v)
            return json.load(open(mf))
    ver = (have[-1] + 1) if have else 1
    d = os.path.join(out_root, "v%d" % ver)
    os.makedirs(d, exist_ok=True)
    np.savez_compressed(os.path.join(d, "amber.part.npz"), X=X, ev_mouse=ev_mouse, XM=XM)
    os.replace(os.path.join(d, "amber.part.npz"), os.path.join(d, "amber.npz"))
    man = {"version": ver, "made": datetime.datetime.now().isoformat(timespec="seconds"), "fingerprint": fp, "source": battery_dir,
           "event_set": SET_NAMES.get(event_set, event_set), "raw": bool(raw), "classifier": "winner (round 11 FINAL OPTIMIZED SEPARATION), frozen",
           "mice": [{"lab": r.lab, "group": r.group, "subgroup": r.subgroup, "ko": r.ko, "year": r.year, "n": r.n,
                     "winner": r.winner} for r in recs],
           "event_features": names, "event_families": [_family_of_event(n) for n in names],
           "mouse_features": mnames, "mouse_families": mfam, "n_events": int(X.shape[0])}
    json.dump(man, open(os.path.join(d, "manifest.json"), "w"), indent=1)
    log("saved amber v%d: %d events x %d, %d mice x %d" % (ver, X.shape[0], X.shape[1], XM.shape[0], XM.shape[1]))
    return man


def load(version=None, root=AMBER):
    """(manifest, arrays) of a frozen bundle (the latest when version is None)."""
    have = sorted(int(d[1:]) for d in os.listdir(root) if d.startswith("v") and d[1:].isdigit())
    if not have:
        raise FileNotFoundError("No amber bundle yet: build one first.")
    v = int(version or have[-1])
    d = os.path.join(root, "v%d" % v)
    man = json.load(open(os.path.join(d, "manifest.json")))
    z = np.load(os.path.join(d, "amber.npz"))
    return man, {k: z[k] for k in z.files}


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery",
          event_set=sys.argv[2] if len(sys.argv) > 2 else "v6", raw="raw" in sys.argv[3:])
