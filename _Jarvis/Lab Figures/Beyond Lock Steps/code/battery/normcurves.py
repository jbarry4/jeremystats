"""The dentate spike of each recording on axes that are the same in every
mouse, and the literature's way of finding DS3. Used by the averaged
documents, the quality check pages, the summary table and the battery.

Depth is normalized by each recording's own landmarks (dsdata.Rec.landmarks):
  u  blade to blade: 0 at the upper blade's main sink, 1 at the lower's
  v  within a blade: 0 at the source between the blades, 1 at the blade's
     main sink, above 1 farther out (distal)
Size is normalized by the recording's own main sinks (mean of the two), so
every recording counts the same whatever its amplitude.
"""
import numpy as np

import dsdata

GRID_U = np.linspace(-0.6, 1.6, 111)
GRID_V = np.linspace(-0.5, 2.6, 125)
_CACHE = {}


def _lobe_centroid(y, x, i0, frac=0.5):
    h = y[i0] * frac
    lo = i0
    while lo - 1 >= 0 and y[lo - 1] > h:
        lo -= 1
    hi = i0
    while hi + 1 < y.size and y[hi + 1] > h:
        hi += 1
    w = np.maximum(y[lo:hi + 1] - h, 0.0)
    return float((w * x[lo:hi + 1]).sum() / w.sum()) if w.sum() > 0 else float(x[i0])


def curves(r):
    """Everything normalized for one recording (cached)."""
    key = (r.lab, r.n)
    if key in _CACHE:
        return _CACHE[key]
    k = r.landmarks
    A = 0.5 * (k["sinkU"] + k["sinkL"])
    m = r.mean_csd_peak
    out = {"A": A, "prof_u": r.on_u(m, GRID_U) / A}
    mean_t = dsdata.fill_bad(r.csd.mean(axis=0).T, r.bad_rows).T           # 64 x 101
    xu = r.u(np.arange(64))
    out["img_u"] = np.array([np.interp(GRID_U, xu, mean_t[:, j], left=np.nan, right=np.nan) for j in range(mean_t.shape[1])]).T / A
    fold = []
    for blade, sk in (("upper", k["sinkU"]), ("lower", k["sinkL"])):
        fold.append(r.on_v(m, blade, GRID_V) / sk)
    out["fold_blades"] = np.array(fold)
    out["fold"] = np.nanmean(out["fold_blades"], axis=0)
    # time courses at the main sinks and at the source(s)
    tc = r.csd.mean(axis=0)
    out["tc_sink"] = 0.5 * (tc[k["rowU"]] / -k["sinkU"] + tc[k["rowL"]] / -k["sinkL"]) * -1.0     # sink negative, peak about -1
    out["tc_source"] = 0.5 * (tc[k["rowGU"]] + tc[k["rowGL"]]) / A
    lf = r.lfp.mean(axis=0)
    out["lfp_u"] = r.on_u(r.lfp_peak.mean(axis=0), GRID_U)
    out["lfp_u"] = out["lfp_u"] / np.nanmax(np.abs(out["lfp_u"]))
    out["tc_lfp"] = 0.5 * (lf[k["rowGU"]] + lf[k["rowGL"]])                 # at the source between the blades
    out["tc_lfp"] = out["tc_lfp"] / np.max(np.abs(out["tc_lfp"]))
    out["typed"] = typed(r, r.used) if (r.used and r.eligible(r.used)) else None
    _CACHE[key] = out
    return out


def typed(r, clf, types=None):
    """DS1 and DS2 (and DS3 when given in `types`) on the folded axis, in
    units of DS2's main sink in that blade; each type's sink centroid in v
    per blade; and the DS1/DS2 position ratio."""
    t = r.types(clf) if types is None else types
    k = r.landmarks
    out = {"fold": {}, "cen": {}, "peak": {}, "tc": {}, "n": {}}
    ref = {}
    m2 = dsdata.fill_bad(r.csd_peak[t == 2].mean(axis=0), r.bad_rows) if (t == 2).any() else None
    for c in sorted(set(int(x) for x in np.unique(t)) & {1, 2, 3}):
        mu = dsdata.fill_bad(r.csd_peak[t == c].mean(axis=0), r.bad_rows)
        out["n"][c] = int((t == c).sum())
        fb, cen, pk = [], [], []
        for blade, row in (("upper", k["rowU"]), ("lower", k["rowL"])):
            if blade not in ref:
                ref[blade] = float(-m2[row]) if m2 is not None and m2[row] < 0 else float(k["sinkU"] if blade == "upper" else k["sinkL"])
            p = r.on_v(mu, blade, GRID_V) / ref[blade]
            fb.append(p)
            s = np.where(np.isfinite(p), np.maximum(-p, 0.0), 0.0)
            w = (GRID_V >= 0.3)
            if s[w].max() > 0:
                i0 = int(np.argmax(np.where(w, s, 0.0)))
                cen.append(_lobe_centroid(s, GRID_V, i0))
                pk.append(float(s[i0]))
            else:
                cen.append(np.nan)
                pk.append(0.0)
        out["fold"][c] = np.nanmean(np.array(fb), axis=0)
        out["cen"][c], out["peak"][c] = cen, pk
        rows = [k["rowU"], k["rowL"]]
        tc = r.csd[t == c].mean(axis=0)
        out["tc"][c] = 0.5 * (tc[rows[0]] / ref["upper"] + tc[rows[1]] / ref["lower"])
    if 1 in out["cen"] and 2 in out["cen"]:
        out["ratio"] = [out["cen"][1][b] / out["cen"][2][b] if np.isfinite(out["cen"][1][b]) and out["cen"][2][b] > 0 else np.nan for b in (0, 1)]
        out["amp"] = [out["peak"][1][b] / out["peak"][2][b] if out["peak"][2][b] > 0 else np.nan for b in (0, 1)]
    return out


def literature_ds3(r, blade, cut=0.5):
    """DS1 / DS2 / DS3 by the procedure of Tarcsay et al. 2025 (bioRxiv
    10.1101/2025.10.27.684857), in one blade:
      PCA of the CSD at the DS peak; the events in the lowest and in the
      highest quarter of PC1; the contact where each quarter's mean sink is
      deepest = the outer and the middle molecular layer; relative sink =
      (outer - middle) / (outer + middle) per event; above +cut DS1, under
      -cut DS2, between them DS3.
    Ours where the paper is silent: one blade at a time; 'outer' is the one
    of the two contacts farther from the source; an event whose two sinks
    together are under the 99th percentile of the same sum 40 ms away from
    the DS is left unscored. Returns None when the two quarters' sinks peak
    at the same contact (the paper's procedure cannot place the layers)."""
    rows = r.good(r.blade_rows(blade, 5))
    X = r.csd_peak[:, rows].astype(float)
    Xc = X - X.mean(axis=0)
    u_, s_, vt = np.linalg.svd(Xc, full_matrices=False)
    pc1 = u_[:, 0] * s_[0]
    lo, hi = pc1 <= np.percentile(pc1, 25), pc1 >= np.percentile(pc1, 75)
    ra, rb = rows[int(np.argmin(X[lo].mean(axis=0)))], rows[int(np.argmin(X[hi].mean(axis=0)))]
    if ra == rb:
        return None
    va, vb = float(r.v(ra, blade)), float(r.v(rb, blade))
    ro, rm = (ra, rb) if va > vb else (rb, ra)
    O, Mi = np.maximum(-r.csd_peak[:, ro], 0.0), np.maximum(-r.csd_peak[:, rm], 0.0)
    null = []
    for c0 in (-40.0, 40.0):
        w = np.abs(r.t_ms - c0) <= 3.0
        null.append(np.maximum(-r.csd[:, ro, :][:, w].mean(axis=1), 0) + np.maximum(-r.csd[:, rm, :][:, w].mean(axis=1), 0))
    floor = float(np.percentile(np.concatenate(null), 99))
    tot = O + Mi
    ok = tot > floor
    rel = np.full(r.n, np.nan)
    rel[ok] = (O[ok] - Mi[ok]) / tot[ok]
    types = np.zeros(r.n, int)
    types[ok & (rel > cut)] = 1
    types[ok & (rel < -cut)] = 2
    types[ok & (np.abs(rel) <= cut)] = 3
    return {"types": types, "rel": rel, "row_outer": int(ro), "row_middle": int(rm), "gap_um": abs(ro - rm) * dsdata.SPACING_UM,
            "share": {c: float((types == c).mean()) for c in (0, 1, 2, 3)}, "pc1_var": float(s_[0] ** 2 / (s_ ** 2).sum())}


def group_stack(recs, key):
    """(labs, array) of one normalized curve over a list of recordings."""
    labs, rows = [], []
    for r in recs:
        c = curves(r)
        if c.get(key) is not None:
            labs.append(r.lab)
            rows.append(c[key])
    return labs, np.array(rows)


def cluster_test(a, b, n_perm=5000, thresh=2.1, seed=0):
    """Do two groups' curves differ anywhere? Welch t at each point, runs
    of |t| over `thresh` summed into clusters, the largest cluster against
    the same from shuffled group labels. Returns (t, [(start, stop, mass,
    p)], p of the largest)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a).all(axis=0) & np.isfinite(b).all(axis=0)

    def tstat(x, y):
        va, vb = x.var(axis=0, ddof=1) / x.shape[0], y.var(axis=0, ddof=1) / y.shape[0]
        return (y.mean(axis=0) - x.mean(axis=0)) / np.sqrt(va + vb + 1e-30)

    def clusters(t):
        out, i = [], 0
        while i < t.size:
            if abs(t[i]) > thresh:
                j = i
                while j + 1 < t.size and abs(t[j + 1]) > thresh and np.sign(t[j + 1]) == np.sign(t[i]):
                    j += 1
                out.append((i, j, float(np.abs(t[i:j + 1]).sum())))
                i = j + 1
            else:
                i += 1
        return out
    A, B = a[:, ok], b[:, ok]
    t = tstat(A, B)
    obs = clusters(t)
    allx = np.vstack([A, B])
    rng = np.random.default_rng(seed)
    null = np.zeros(n_perm)
    for k in range(n_perm):
        p = rng.permutation(allx.shape[0])
        cl = clusters(tstat(allx[p[:A.shape[0]]], allx[p[A.shape[0]:]]))
        null[k] = max([c[2] for c in cl]) if cl else 0.0
    idx = np.where(ok)[0]
    res = [(int(idx[i]), int(idx[j]), m, float((null >= m - 1e-12).mean())) for i, j, m in obs]
    tfull = np.full(a.shape[1], np.nan)
    tfull[ok] = t
    return tfull, res, (min([c[3] for c in res]) if res else 1.0)


def typed_u(r, clf=None, drop_ds3=True, min_n=5):
    """DS1 and DS2 of one recording on the blade-to-blade depth axis, with
    the DS3 events taken out (2026-11-17; the user's one normalized figure).
    Depth: 0 = where the recording's average dentate spike (all events) has
    its deepest sink in the upper blade, 1 = the same in the lower blade.
    Size: 1 = the average dentate spike's sink (mean of those two), the same
    scale for both types, so their sizes compare. A type with fewer than
    `min_n` events is None."""
    clf = clf or r.used
    t = r.types(clf).copy()
    if drop_ds3:
        m3 = r.ds3(clf)
        if m3 is not None:
            t[m3] = 3
    k = r.landmarks
    A = 0.5 * (k["sinkU"] + k["sinkL"])
    out = {"n": {}, "A": A, "clf": clf, "src_u": sorted({float(r.u(k["GU"])), float(r.u(k["GL"]))})}
    for c in (1, 2):
        out["n"][c] = int((t == c).sum())
        out[c] = r.on_u(r.csd_peak[t == c].mean(axis=0), GRID_U) / A if out["n"][c] >= min_n else None
    return out
