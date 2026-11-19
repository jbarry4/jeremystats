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


def _family_of_event(name):
    if name.startswith("type_"):
        return "ds type"
    if name.startswith("f_"):
        return "filter " + name.split("__")[0][2:]
    if name.startswith("ba_"):
        return "before/after " + name.split("_")[2]
    if name in CONTEXT:
        return "context"
    return "waveform/depth"


def build(battery_dir, out_root=AMBER, log=print):
    """Freeze the bundle; returns its manifest."""
    sys.path.insert(0, battery_dir)
    import dsdata
    import measures as MS
    import around_measures as AM
    import pandas as pd

    recs = [r for r in dsdata.load("v6") if r.ok and r.landmarks is not None and r.winner]
    labs = [r.lab for r in recs]
    filt = {es: {r.lab: r for r in dsdata.load(es)} for es in FILTERS}
    rows, ev_mouse, names = [], [], None
    for mi, r in enumerate(recs):
        F = MS.event_features(r)
        cols = {}
        for k, v in F.items():
            v = np.asarray(v, float)
            if v.shape == (r.n,):
                cols[k] = v
        t = r.types("winner")
        s = np.asarray((r.ds3w.get("winner") or {}).get("score", np.full(r.n, np.nan)), float)
        d3 = np.isfinite(s) & (np.abs(s) <= 0.5)
        cols["type_ds1"] = ((t == 1) & ~d3).astype(float)
        cols["type_ds2"] = ((t == 2) & ~d3).astype(float)
        cols["type_ds3"] = d3.astype(float)
        cols["type_unscored"] = (~np.isfinite(s)).astype(float)
        for es in FILTERS:
            rb = filt[es].get(r.lab)
            if rb is None or rb.landmarks is None:
                for k in FILTER_FEATS:
                    cols["f_%s__%s" % (es[2:], k)] = np.full(r.n, np.nan)
                continue
            Fb = MS.event_features(rb)
            for k in FILTER_FEATS:
                cols["f_%s__%s" % (es[2:], k)] = np.asarray(Fb.get(k, np.full(r.n, np.nan)), float)
        D = AM.load(r)
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
    M = M[(M.event_set == "v6") & ((M.classifier == "") | (M.classifier == "winner"))]
    MA = pd.read_pickle(os.path.join(battery_dir, "merged_around", "measures.pkl"))
    MA = MA[(MA.event_set == "v6") & MA.name.str.startswith(("locked", "burst"))]
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
    srcs = [os.path.join(battery_dir, "data", "ds_v6.pkl")] + [os.path.join(battery_dir, "data", "ds_%s.pkl" % es) for es in FILTERS] + \
        [os.path.join(battery_dir, "merged", "measures.pkl"), os.path.join(battery_dir, "merged_around", "measures.pkl")]
    fp = _fingerprint([p for p in srcs if os.path.isfile(p)] + [os.path.join(AM.SRC, f) for f in os.listdir(AM.SRC)])
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
           "event_set": "v6 (Halo)", "classifier": "winner (round 11 FINAL OPTIMIZED SEPARATION), frozen",
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
    build(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
