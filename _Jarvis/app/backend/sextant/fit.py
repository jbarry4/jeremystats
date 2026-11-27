"""The pose search: every straight probe the atlas allows, scored.

A candidate is a line through the atlas -- where it passes the reference
depth (AP, ML) and its two tilts. Along the line the atlas says where each
landmark lies (CA1's cell layer, the fissure, the molecular layers' sinks,
the dentate's end, the thalamus...). The recording says at which contacts
those landmarks were found. Method A ("landmarks, then the atlas") asks how
well one straight probe -- one offset along the line and one size factor --
can make the two agree:

    L_j = o + pitch * s * x_j     (L_j: atlas position along the line, um;
                                   x_j: the contact it was found at)

solved by weighted least squares for each line, the misfit in contacts
(chi-square with each landmark's own sigma) is the score. Lines are scored on
a coarse grid, then the best are refined; the posterior weights over every
scored line make the cloud.
"""
from __future__ import annotations

import math

import numpy as np

from . import atlas as A
from .cohort import CRANIOTOMY, PROBE

PITCH = PROBE["pitch_um"]
NC = PROBE["n"]

# class groups (codes from tools/seahorse/volume.py LAMINA and the coarse
# regions of tools/sextant/build_atlas.py)
SO = (10, 14, 18)
SP = (11, 15, 19)
SR = (12, 16, 20, 21)
SLM = (13, 17, 22)
OM = (1, 2, 8, 9)            # outer + middle molecular layer, both blades
IML = (3, 7)
GCL = (4, 6)
HIL = (5,)
DG_ML = (1, 2, 3, 7, 8, 9)
DG = DG_ML + GCL + HIL
HIPPO = DG + SO + SP + SR + SLM + (23, 24, 25, 26)
GREY_BELOW = (33, 34, 35, 36, 38)

# detector landmark -> (atlas landmark, extra sigma in contacts)
MATCH = {
    "sp": ("sp_c", 0.0), "spw_rev": ("sp_c", 1.5), "sp_above": ("sp_c", 0.0),
    "sr_sink": ("sr_c", 0.0), "slm_src": ("slm_c", 0.0),
    "fissure": ("fis", 0.0),
    "ml_a": ("mla", 0.0), "ps_ml_a": ("mla", 0.5), "bt_ml_a": ("mla", 0.5),
    "dg_core": ("core", 0.0), "ps_dg_core": ("core", 0.5), "bt_dg_core": ("core", 0.5),
    "hil_gam": ("core", 0.0),
    "ml_b": ("mlb", 0.0), "ps_ml_b": ("mlb", 0.5), "bt_ml_b": ("mlb", 0.5),
    "dg_end": ("dge", 0.0), "th_top": ("tht", 0.0),
}
ATLAS_KEYS = ("sp_c", "sr_c", "slm_c", "fis", "mla", "core", "mlb", "dge", "tht")
# a landmark the recording shows but the line does not have: as a 4-sigma miss
MISS = 16.0
# a landmark the line puts on the shank that the recording should have shown
UNSEEN = {"sp_c": 4.0, "fis": 2.0, "mla": 4.0, "mlb": 4.0}

DV_REF = 1900.0               # lines are indexed by where they cross this DV
T0, T1, DT = -1700.0, 2700.0, 10.0
SCALE_PRIOR = (1.0, 0.15)
SCALE_RANGE = (0.6, 1.5)
PRIOR = {"ap_sd_mm": 0.6, "ml_sd_mm": 0.5, "tilt_sd_deg": 10.0}


# ---------------------------------------------------------------- the lines
def lines_codes(atl, ap, ml, tml, tap):
    """Codes along many lines: arrays (n,) -> (n, T) uint8, and t (T,)."""
    t = np.arange(T0, T1 + DT / 2, DT)
    d = A.direction(tml, tap)                                  # (n, 3)
    p0 = np.stack([ap, np.full_like(ap, DV_REF), ml], -1)      # (n, 3)
    pts = p0[:, None, :] + t[None, :, None] * d[:, None, :]
    return atl.codes_at(pts), t


def _first_run(mask, start):
    """First run of True at or after `start` (per row): (i0, i1) with i1
    exclusive; -1 where there is none."""
    n, T = mask.shape
    idx = np.arange(T)[None, :]
    m = mask & (idx >= start[:, None])
    has = m.any(1)
    i0 = np.where(has, m.argmax(1), -1)
    after = (~mask) & (idx > i0[:, None])
    i1 = np.where(after.any(1), after.argmax(1), T)
    i1 = np.where(has, i1, -1)
    return i0, i1


def atlas_landmarks(codes, t):
    """Atlas landmarks (um along the line from the reference point; NaN when
    the line does not have them) for every line: dict key -> (n,)."""
    n, T = codes.shape
    isin = lambda cls: np.isin(codes, cls)                     # noqa: E731
    zero = np.zeros(n, int)
    out = {k: np.full(n, np.nan) for k in ATLAS_KEYS}

    def centre(i0, i1):
        ok = (i0 >= 0) & (i1 > i0)
        c = np.where(ok, (i0 + i1 - 1) / 2.0, np.nan)
        return np.where(ok, np.interp(c, np.arange(T), t), np.nan), ok

    # CA: the first pyramidal run (a probe meets CA1's from above)
    hip = isin(HIPPO)
    h0 = np.where(hip.any(1), hip.argmax(1), T)
    sp0, sp1 = _first_run(isin(SP), h0)
    out["sp_c"], has_sp = centre(sp0, sp1)
    st = np.where(has_sp, sp1, h0)
    sr0, sr1 = _first_run(isin(SR), st)
    # radiatum must start right below the cell layer (within 60 um)
    okr = (sr0 >= 0) & ((sr0 - st) <= 6)
    out["sr_c"], _ = centre(np.where(okr, sr0, -1), np.where(okr, sr1, -1))
    st2 = np.where(okr, sr1, st)
    lm0, lm1 = _first_run(isin(SLM), st2)
    okl = (lm0 >= 0) & ((lm0 - st2) <= 6)
    out["slm_c"], _ = centre(np.where(okl, lm0, -1), np.where(okl, lm1, -1))
    st3 = np.where(okl, lm1, st2)
    # the fissure: the first dentate molecular-layer voxel after CA1
    ml = isin(DG_ML)
    idx = np.arange(T)[None, :]
    mm = ml & (idx >= st3[:, None])
    hasf = mm.any(1)
    fi = np.where(hasf, mm.argmax(1), -1)
    out["fis"] = np.where(hasf, np.interp(np.maximum(fi, 0), np.arange(T), t), np.nan)
    # molecular layer runs (outer + middle thirds): the DS sinks
    om = isin(OM)
    a0, a1 = _first_run(om, np.where(hasf, fi, T))
    oka = a0 >= 0
    out["mla"], _ = centre(a0, a1)
    b0, b1 = _first_run(om, np.where(oka, a1 + 1, T))
    # the second run must be the same dentate: nothing but dentate between
    dg = isin(DG)
    between_ok = np.ones(n, bool)
    for i in np.flatnonzero(b0 >= 0):
        seg = dg[i, a1[i]:b0[i]]
        between_ok[i] = bool(seg.all()) and (b0[i] - a1[i]) <= 60
    b0 = np.where(between_ok, b0, -1)
    b1 = np.where(between_ok, b1, -1)
    okb = b0 >= 0
    out["mlb"], _ = centre(b0, b1)
    # the core: granule cells and hilus between the two runs (or after the
    # one run, when there is only one)
    core = isin(GCL + HIL)
    for i in np.flatnonzero(oka):
        lo = a1[i]
        hi = b0[i] if okb[i] else min(T, a1[i] + 40)
        seg = np.flatnonzero(core[i, lo:hi])
        if seg.size:
            c = lo + (seg[0] + seg[-1]) / 2.0
        elif okb[i]:
            c = (lo + hi - 1) / 2.0
        else:
            continue
        out["core"][i] = np.interp(c, np.arange(T), t)
    # end of the dentate: last dentate voxel of the stretch
    last = np.where(okb, b1, np.where(oka, a1, -1))
    for i in np.flatnonzero(last >= 0):
        j = last[i]
        while j < T and dg[i, j]:
            j += 1
        out["dge"][i] = t[min(j, T - 1)] - DT / 2.0
        # thalamus (or other grey) below
        rest = np.flatnonzero(np.isin(codes[i, j:], GREY_BELOW))
        if rest.size and rest[0] < 120:
            out["tht"][i] = t[j + rest[0]]
    return out


# ---------------------------------------------------------------- Method A
def method_a(lms, alm, n_contacts=NC):
    """Score every line: returns dict with o (um), s, chi2 (n,), and the
    per-landmark residuals (contacts)."""
    keys = [l for l in lms if l["key"] in MATCH and l.get("fit", True)]
    n = next(iter(alm.values())).size
    if len(keys) < 2:
        raise ValueError("Fewer than two landmarks: nothing to fit.")
    X = np.array([l["x"] for l in keys])
    S = np.array([math.hypot(l["sigma"], MATCH[l["key"]][1]) for l in keys])
    side = np.array([{"above": -1, "below": 1}.get(l.get("side"), 0) for l in keys])
    L = np.stack([alm[MATCH[l["key"]][0]] for l in keys], 1)    # (n, m)
    have = np.isfinite(L)
    # one-sided landmarks ("CA1's cell layer is above the top contact")
    # bound the fit but do not pull it: they are left out of the solve
    w = np.where(have & (side[None, :] == 0), 1.0 / S[None, :] ** 2, 0.0)
    Xb = np.broadcast_to(X, L.shape)
    Lz = np.where(have, L, 0.0)
    sw = w.sum(1)
    swx = (w * Xb).sum(1)
    swxx = (w * Xb * Xb).sum(1)
    swl = (w * Lz).sum(1)
    swxl = (w * Xb * Lz).sum(1)
    det = sw * swxx - swx ** 2
    with np.errstate(all="ignore"):
        s = (sw * swxl - swx * swl) / (PITCH * det)
    s0, ssd = SCALE_PRIOR
    s = np.where(np.isfinite(s) & (have.sum(1) >= 2), s, s0)
    s = np.clip(s, *SCALE_RANGE)
    with np.errstate(all="ignore"):
        o = (swl - PITCH * s * swx) / np.maximum(sw, 1e-12)
    with np.errstate(all="ignore"):
        pred = (L - o[:, None]) / (PITCH * s[:, None])
        res = np.where(have, (pred - Xb) / S[None, :], 0.0)
    res = np.where(side[None, :] < 0, np.maximum(res, 0.0), res)
    res = np.where(side[None, :] > 0, np.minimum(res, 0.0), res)
    chi2 = (res ** 2).sum(1) + ((s - s0) / ssd) ** 2
    # a missing landmark: a full miss for a two-sided one; a one-sided one
    # ("above the top") is satisfied when the line has no such layer below
    chi2 += MISS * ((~have) & (side[None, :] == 0)).sum(1)
    # landmarks the line puts on the shank that were not found
    found = {MATCH[l["key"]][0] for l in keys}
    for ak, pen in UNSEEN.items():
        if ak in found:
            continue
        with np.errstate(all="ignore"):
            x = (alm[ak] - o) / (PITCH * s)
        on = np.isfinite(x) & (x > 1) & (x < n_contacts - 2)
        chi2 += pen * on
    return {"o": o, "s": s, "chi2": chi2, "res": res, "keys": [l["key"] for l in keys],
            "n_used": have.sum(1)}


# ---------------------------------------------------------------- the prior
def log_prior(ap, ml, tml, tap, prior=PRIOR):
    c = A.from_bregma(CRANIOTOMY["ap_mm"], CRANIOTOMY["ml_mm"])
    # the line's (AP, ML) where it would cross the surface is close enough
    # to its (AP, ML) at the reference depth for a prior this loose
    z_ap = (ap - c[0]) / (1000.0 * prior["ap_sd_mm"])
    z_ml = (ml - c[2]) / (1000.0 * prior["ml_sd_mm"])
    z_t = np.hypot(tml, tap) / prior["tilt_sd_deg"]
    return -0.5 * (z_ap ** 2 + z_ml ** 2 + z_t ** 2)


# ---------------------------------------------------------------- the search
def grid(ap=(6700, 8700, 50), ml=(5900, 8100, 50), tilt=(-15, 15, 5)):
    aps = np.arange(ap[0], ap[1] + 1e-6, ap[2])
    mls = np.arange(ml[0], ml[1] + 1e-6, ml[2])
    ts = np.arange(tilt[0], tilt[1] + 1e-6, tilt[2])
    G = np.stack(np.meshgrid(aps, mls, ts, ts, indexing="ij"), -1).reshape(-1, 4)
    return G[:, 0], G[:, 1], G[:, 2], G[:, 3]


def score_lines(atl, lms, ap, ml, tml, tap, chunk=6000):
    out = {k: [] for k in ("o", "s", "chi2", "n_used")}
    alms = {k: [] for k in ATLAS_KEYS}
    for i in range(0, ap.size, chunk):
        sl = slice(i, i + chunk)
        codes, t = lines_codes(atl, ap[sl], ml[sl], tml[sl], tap[sl])
        alm = atlas_landmarks(codes, t)
        r = method_a(lms, alm)
        for k in out:
            out[k].append(r[k])
        for k in ATLAS_KEYS:
            alms[k].append(alm[k])
    out = {k: np.concatenate(v) for k, v in out.items()}
    out["alm"] = {k: np.concatenate(v) for k, v in alms.items()}
    out["lp"] = log_prior(ap, ml, tml, tap)
    return out


def search(atl, lms, coarse=None, refine_top=60, log=print):
    """Coarse grid, then a finer grid around the best lines. Returns every
    scored line (both passes) with its posterior log-weight."""
    ap, ml, tml, tap = grid(**(coarse or {}))
    r1 = score_lines(atl, lms, ap, ml, tml, tap)
    lw = -0.5 * r1["chi2"] + r1["lp"]
    best = np.argsort(-lw)[:refine_top]
    log("   coarse: %d lines, best chi2 %.2f" % (ap.size, float(r1["chi2"][best[0]])))
    # refine: 20 um and 2.5 deg around each of the best
    seeds = np.stack([ap[best], ml[best], tml[best], tap[best]], 1)
    d_ap = np.arange(-40, 41, 20.0)
    d_t = np.arange(-5, 5.1, 2.5)
    R = []
    for s in seeds:
        g = np.stack(np.meshgrid(s[0] + d_ap, s[1] + d_ap, s[2] + d_t, s[3] + d_t, indexing="ij"), -1).reshape(-1, 4)
        R.append(g)
    R = np.unique(np.round(np.concatenate(R), 3), axis=0)
    r2 = score_lines(atl, lms, R[:, 0], R[:, 1], R[:, 2], R[:, 3])
    cat = lambda a, b: np.concatenate([a, b])                  # noqa: E731
    res = {"ap": cat(ap, R[:, 0]), "ml": cat(ml, R[:, 1]), "tml": cat(tml, R[:, 2]),
           "tap": cat(tap, R[:, 3])}
    for k in ("o", "s", "chi2", "n_used", "lp"):
        res[k] = cat(r1[k], r2[k])
    res["alm"] = {k: cat(r1["alm"][k], r2["alm"][k]) for k in ATLAS_KEYS}
    res["fine"] = cat(np.zeros(ap.size, bool), np.ones(R.shape[0], bool))
    log("   refined: %d lines, best chi2 %.2f" % (R.shape[0], float(np.min(r2["chi2"]))))
    return res


def pose_of(res, i):
    """The full pose of scored line i: contact positions and the rest."""
    d = A.direction(res["tml"][i], res["tap"][i])
    p_ref = np.array([res["ap"][i], DV_REF, res["ml"][i]])
    o, s = float(res["o"][i]), float(res["s"][i])
    c1 = p_ref + o * d                                         # contact 1
    centre = c1 + (NC - 1) / 2.0 * PITCH * s * d
    return {"centre": centre, "dir": d, "scale": s, "o": o,
            "tilt_ml": float(res["tml"][i]), "tilt_ap": float(res["tap"][i])}


def describe(atl, pose, hemisphere=None):
    """Bregma numbers for a pose: entry point, tip, depths, and the layer
    under every contact."""
    pts = A.contacts(pose["centre"], pose["dir"], pose["scale"], NC, PITCH)
    codes = atl.codes_at(pts)
    entry, _ = A.entry_point(atl, pts[0], pose["dir"])
    eb = A.to_bregma(entry, hemisphere)
    tip = A.to_bregma(pts[-1], hemisphere)
    top = A.to_bregma(pts[0], hemisphere)
    depth_tip = float(np.linalg.norm(pts[-1] - entry)) / pose["scale"]
    depth_top = float(np.linalg.norm(pts[0] - entry)) / pose["scale"]
    return {
        "entry": {k: round(float(v), 3) for k, v in eb.items()},
        "contact1": {k: round(float(v), 3) for k, v in top.items()},
        "contact64": {k: round(float(v), 3) for k, v in tip.items()},
        "depth_um": {"contact1": round(depth_top), "contact64": round(depth_tip)},
        "tilt_ml": round(pose["tilt_ml"], 1), "tilt_ap": round(pose["tilt_ap"], 1),
        "scale": round(pose["scale"], 3),
        "layers": [atl.key.get(int(c), "?") for c in codes],
        "ccf": [[round(float(x), 1) for x in p] for p in pts[[0, NC - 1]]],
    }


def posterior(res, temp=1.0):
    lw = -0.5 * temp * res["chi2"] + res["lp"]
    lw = lw - lw.max()
    w = np.exp(lw)
    # the fine lines sample a small volume densely; the coarse lines sample
    # everything sparsely. Down-weight the fine ones by their density so the
    # cloud is not dominated by how finely a spot was searched.
    dens = np.where(res["fine"], (20.0 / 50.0) ** 2 * (2.5 / 5.0) ** 2, 1.0)
    return w * dens / np.sum(w * dens)
