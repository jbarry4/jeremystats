"""Story menu, round 3 (2026-11-23 evening): depth from the dentate spike itself, never from the lab's layer labels.

Every landmark comes from the recording's own mean CSD at the DS peak (dsdata.Rec.landmarks):
  U, L     the main sink of the upper and of the lower blade
  GU, GL   the current source nearest each sink on the way to the other blade (the cell-layer side)
  top      where the upper sink's lobe ends going up (the CSD turns >= 0): the edge toward CA1
  bot      where the lower sink's lobe ends going down: the far edge of the lower blade
Blade-to-blade axis u: 0 at U, 1 at L. Coarse regions on u, as the median over the 16 recordings:
  CA1 (above top) | upper blade, distal dendrites (top to U) | upper blade, proximal dendrites (U to GU)
  | hilus (GU to GL) | lower blade, proximal (GL to L) | lower blade, distal (L to bot)
Within one blade, v: 0 at that blade's cell-layer source, 1 at its main sink, above 1 farther out (distal).

Profiles are kept RAW (no per-mouse scaling) so that groups can be put on one common scale; the per-recording
deepest sink (ref) is stored for within-recording comparisons (DS1 against DS2 use the same factor).
Writes uprof.pkl.
"""
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import dsdata  # noqa: E402

UGRID = np.round(np.arange(-1.6, 2.601, 0.02), 3)
VGRID = np.round(np.arange(-0.6, 3.001, 0.02), 3)
DG_U = (-0.6, 1.6)          # the dentate rows: 0.6 blade-widths beyond each main sink


def sink_centroid(prof, grid, lo=0.3, hi=3.0):
    """Centroid of the sink (negative CSD) along the axis, from lo outward."""
    sel = (grid >= lo) & (grid <= hi) & np.isfinite(prof)
    w = np.clip(-prof[sel], 0, None)
    return float((w * grid[sel]).sum() / w.sum()) if w.sum() > 0 else np.nan


def lobe_edge(pk, row0, step):
    """Where the sink lobe around row0 ends going in direction step (-1 up, +1 down): the first place the mean CSD
    turns >= 0, interpolated between contacts. nan if it never does on the probe."""
    i = int(row0)
    while 0 <= i + step < pk.size:
        j = i + step
        if pk[j] >= 0:
            a, b = pk[i], pk[j]
            frac = a / (a - b) if a != b else 0.5
            return i + step * frac
        i = j
    return np.nan


out = {"UGRID": UGRID, "VGRID": VGRID, "DG_U": DG_U, "recs": {}}
for es in ("v6", "v8"):
    for r in dsdata.load(es):
        if r.lab in ("m6", "m51") or r.landmarks is None:
            if r.lab not in ("m6", "m51"):
                print(es, r.lab, "no landmarks")
            continue
        k = r.landmarks
        pk = r.mean_csd_peak                                     # 64, bad rows filled
        rows_u = r.u(np.arange(pk.size))
        raw = r.on_u(pk, UGRID)
        dg = (UGRID >= DG_U[0]) & (UGRID <= DG_U[1])
        ref = -np.nanmin(np.where(dg, raw, np.nan))
        d = {"lab": r.lab, "contacts": list(r.contacts), "bad_rows": list(r.bad_rows), "rows_u": rows_u,
             "landmarks": {kk: k[kk] for kk in ("U", "L", "GU", "GL", "rowU", "rowL", "rowGU", "rowGL")},
             "u_gu": float(r.u([k["GU"]])[0]), "u_gl": float(r.u([k["GL"]])[0]),
             "u_top": float(r.u([lobe_edge(pk, k["rowU"], -1)])[0]), "u_bot": float(r.u([lobe_edge(pk, k["rowL"], +1)])[0]),
             "ref": float(ref), "u_peak_raw": raw, "u_peak": raw / ref, "n": int(r.n), "src_rows": list(k["src_rows"])}
        tc = dsdata.fill_bad(np.nanmean(np.asarray(r.csd, float), axis=0).T, r.bad_rows).T   # 64 x T
        d["u_tc_raw"] = np.array([np.interp(UGRID, rows_u, tc[:, j], left=np.nan, right=np.nan) for j in range(tc.shape[1])]).T
        d["t_ms"] = np.asarray(r.t_ms, float)
        # each event's deepest dentate sink (raw), on the DS-defined dentate rows
        dg_rows = np.array([i for i in range(pk.size) if DG_U[0] <= rows_u[i] <= DG_U[1] and i not in r.bad_rows], int)
        d["sink_ev"] = -np.min(np.asarray(r.csd_peak, float)[:, dg_rows], axis=1)
        t = np.asarray(r.labels["winner"]["types"]) if r.winner else None
        d["types"] = t
        for blade in ("upper", "lower"):
            d["v_all_" + blade] = r.on_v(pk, blade, VGRID) / ref
        if t is not None:
            for kk in (1, 2):
                sel = t == kk
                if sel.sum() >= 3:
                    pk_k = dsdata.fill_bad(np.nanmean(np.asarray(r.csd_peak, float)[sel], axis=0), r.bad_rows)
                    d["u_ds%d_raw" % kk] = r.on_u(pk_k, UGRID)
                    d["n_ds%d" % kk] = int(sel.sum())
                    for blade in ("upper", "lower"):
                        g = r.on_v(pk_k, blade, VGRID) / ref
                        d["v_ds%d_%s" % (kk, blade)] = g
                        d["c_ds%d_%s" % (kk, blade)] = sink_centroid(g, VGRID)
            # DS1 events with a sink at the main-sink contacts (the battery's per-event ratios need one)
            su = -np.asarray(r.csd_peak, float)[:, k["rowU"]]
            sl = -np.asarray(r.csd_peak, float)[:, k["rowL"]]
            amp = 0.5 * (su + sl)
            d["ds1_with_main_sink"] = int(((t == 1) & (amp > 0)).sum())
        # the DS1 / DS2 split per event (for the primer's single-mouse profiles: SEM over events)
        if t is not None:
            for kk in (1, 2):
                sel = t == kk
                if sel.sum() >= 3:
                    ev = np.asarray(r.csd_peak, float)[sel]
                    ev = dsdata.fill_bad(ev, r.bad_rows)
                    gu_ev = np.array([np.interp(UGRID, rows_u, e, left=np.nan, right=np.nan) for e in ev])
                    d["u_ds%d_sem_raw" % kk] = np.nanstd(gu_ev, axis=0) / np.sqrt(sel.sum())
        d["si"] = r.winner_si
        out["recs"][(es, r.lab)] = d
        print(es, r.lab, "ref %.3g" % ref, "u: top %.2f GU %.2f GL %.2f bot %.2f" % (d["u_top"], d["u_gu"], d["u_gl"], d["u_bot"]),
              "DS1 with main sink", d.get("ds1_with_main_sink"), "of", d.get("n_ds1"), flush=True)

# coarse regions: the median landmark positions over the 16 Halo recordings
v6 = [d for (es, _l), d in out["recs"].items() if es == "v6"]
out["regions"] = {kk: float(np.nanmedian([d["u_" + kk] for d in v6])) for kk in ("top", "gu", "gl", "bot")}
# one common scale for group comparisons: the control group's mean profile, its deepest dentate sink = -1
CTL = ["m2", "m21", "m22", "m26", "m59", "m60", "m61"]
mc = np.nanmean([out["recs"][("v6", l)]["u_peak_raw"] for l in CTL], axis=0)
dgm = (UGRID >= DG_U[0]) & (UGRID <= DG_U[1])
out["ref_ctl"] = float(-np.nanmin(np.where(dgm, mc, np.nan)))
print("regions", {kk: round(v, 3) for kk, v in out["regions"].items()}, "control reference %.4g" % out["ref_ctl"])
with open(os.path.join(HERE, "uprof.pkl"), "wb") as fh:
    pickle.dump(out, fh, protocol=4)
print("saved")
