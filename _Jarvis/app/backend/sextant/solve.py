"""One recording's placement, start to finish: both methods, consolidated.

    1  Method A searches every line (fit.search): a coarse grid, then refined.
    2  The candidates -- the lines A finds plausible, plus a random sample of
       the whole coarse grid so Method B can disagree -- are scored on one grid
       of offsets (depth along the line) and size factors by
          A  the landmark misfit at that exact depth and size, and
          B  the simulated current-source profiles' fit (forward.score).
    3  The consolidated score = A + w_B * B + the craniotomy prior. Its best
       pose is the answer; samples from it are the cloud; each method alone
       is kept so the reveal can show where they agree.
    4  The reveal's stops: the same score with the evidence added one family
       at a time (CA1's cell layer, the sharp wave, theta, dentate spikes,
       P-spikes and BTs, the thalamus), each with its own cloud.
    5  Drop one signal: every landmark and every profile taken out in turn.

The cloud is an importance sample: a random grid line stands for all the grid
lines like it that were not scored (N_coarse / N_random of them), a line A
put forward stands for itself. So the first stop, with only the craniotomy to
go on, is as wide as the prior really is, and the last is as narrow as the
evidence makes it.

W_B, Method B's weight against A: a 64-contact profile is smooth, so its
contacts are not 64 independent measurements; W_B counts each as about six.
"""
from __future__ import annotations

import math

import numpy as np

from . import atlas as A
from . import fit as F
from . import forward as B

W_B = 6.0 / 64.0
K_SD = 0.35               # the dentate's stretch, prior sd (PTEN; and controls when learning normal)
KS = np.array([0.95, 1.15, 1.35, 1.6])
OFFSETS = np.arange(-1500.0, 501.0, 25.0)
SCALES = np.array([0.85, 0.95, 1.05, 1.15])
N_TOP_COARSE, N_TOP_FINE, N_RANDOM = 1200, 300, 600

FAMILIES = [
    ("prior", "Where the craniotomy was", (), ()),
    ("ca1", "CA1's cell layer", ("sp", "spw_rev", "sp_above"), ("rip", "mua")),
    ("spw", "The sharp wave", ("sr_sink", "slm_src"), ("spw",)),
    ("theta", "Theta", ("fissure",), ("theta",)),
    ("ds", "Dentate spikes", ("ml_a", "ml_b", "dg_core", "dg_end"), ("ds",)),
    ("path", "P-spikes and borderline transients",
     ("ps_ml_a", "ps_ml_b", "ps_dg_core", "bt_ml_a", "bt_ml_b", "bt_dg_core"), ("ps", "bt")),
    ("below", "Below the hippocampus", ("th_top",), ()),
]


def _chi2_a_grid(lms, alm, O, Sc, keep=None, unseen=True, found_all=None, Ks=None, hinge=None):
    """Method A's chi-square for each line (rows of alm) at every offset and
    scale: (n, no, ns). `keep`: the landmark keys to use (None = all)."""
    keys = [l for l in lms if l["key"] in F.MATCH and l.get("fit", True)
            and (keep is None or l["key"] in keep)]
    n = next(iter(alm.values())).size
    out = np.zeros((n, O.size, Sc.size), np.float32)
    s0, ssd = F.SCALE_PRIOR
    out += (((Sc - s0) / ssd) ** 2)[None, None, :]
    stretch = Ks is not None and hinge is not None
    if stretch:
        out += (((np.asarray(Ks) - 1.0) / K_SD) ** 2)[None, None, :]
    den = (F.PITCH * Sc)[None, None, :]

    def to_x(Lk):
        if stretch:
            return F.x_of_t(Lk - O[None, :, None], Sc[None, None, :], hinge, np.asarray(Ks)[None, None, :])
        return (Lk - O[None, :, None]) / den
    found = set()
    for l in keys:
        ak = F.MATCH[l["key"]][0]
        found.add(ak)
        sig = math.hypot(l["sigma"], F.MATCH[l["key"]][1])
        Lk = alm[ak][:, None, None]
        have = np.isfinite(Lk)
        with np.errstate(all="ignore"):
            pred = to_x(Lk)
        r = (pred - l["x"]) / sig
        side = l.get("side")
        if side == "above":
            r = np.maximum(r, 0.0)
        elif side == "below":
            r = np.minimum(r, 0.0)
        out += np.where(have, r ** 2, 0.0 if side else F.MISS)
    if unseen:
        # "should have been seen": judged against everything the detectors
        # found, not only the landmarks kept -- dropping a landmark to test
        # the fit must not turn into claiming it is absent
        if found_all is not None:
            found = set(found)
            found.update(found_all)
        for ak, pen in F.UNSEEN.items():
            if ak in found:
                continue
            Lk = alm[ak][:, None, None]
            with np.errstate(all="ignore"):
                x = to_x(Lk)
            out += pen * (np.isfinite(x) & (x > 1) & (x < F.NC - 2))
    return out


class Solution:
    """The candidates, their scores, and how to turn an index into a pose."""

    def __init__(self, res, cand, q, lms, ll_parts, chi_full, grid_s=None, grid_k=None, hinge=None):
        self.res, self.cand, self.q = res, cand, q
        self.grid_s = SCALES if grid_s is None else grid_s
        self.grid_k = grid_k
        self.hinge = hinge
        self.lms, self.ll_parts, self.chi_full = lms, ll_parts, chi_full
        self.ap, self.ml = res["ap"][cand], res["ml"][cand]
        self.tml, self.tap = res["tml"][cand], res["tap"][cand]
        self.lp = res["lp"][cand]
        self.coarse = ~res["fine"][cand]

    def pose(self, li, oi, si):
        d = A.direction(self.tml[li], self.tap[li])
        p_ref = np.array([self.ap[li], F.DV_REF, self.ml[li]])
        o, s = OFFSETS[oi], self.grid_s[si]
        k = float(self.grid_k[si]) if self.grid_k is not None else 1.0
        c1 = p_ref + o * d
        centre = c1 + (F.NC - 1) / 2.0 * F.PITCH * s * d
        return {"centre": centre, "dir": d, "scale": float(s), "o": float(o), "c1": c1,
                "k": k, "hinge": self.hinge if self.grid_k is not None else None,
                "tilt_ml": float(self.tml[li]), "tilt_ap": float(self.tap[li])}

    def total(self, keep_lm=None, keep_prof=None, unseen=True, wb=W_B):
        alm = {k: self.res["alm"][k][self.cand] for k in F.ATLAS_KEYS}
        if keep_lm is None and unseen:
            chi = self.chi_full
        else:
            found_all = {F.MATCH[l["key"]][0] for l in self.lms
                         if l["key"] in F.MATCH and l.get("fit", True)}
            chi = _chi2_a_grid(self.lms, alm, OFFSETS, self.grid_s, keep=keep_lm, unseen=unseen,
                               found_all=found_all, Ks=self.grid_k, hinge=self.hinge)
        llb = np.zeros_like(chi)
        for k, v in self.ll_parts.items():
            if keep_prof is None or k in keep_prof:
                llb = llb + v
        return -0.5 * chi + wb * llb + self.lp[:, None, None], chi, llb

    def best(self, T):
        return np.unravel_index(int(np.argmax(T)), T.shape)

    def sample(self, T, n, rng):
        """Importance sample of (line, offset, scale) over the coarse
        candidates (see the module notes)."""
        Tc = np.where(self.coarse[:, None, None], T, -np.inf)
        lw = Tc - np.log(self.q)[:, None, None]
        lw = lw - np.max(lw)
        w = np.exp(lw).ravel()
        w /= w.sum()
        pick = rng.choice(w.size, size=n, p=w)
        return [np.unravel_index(int(j), T.shape) for j in pick]


def hinge_of(lms):
    """Where CA1 ends and the dentate begins on the shank (contact index):
    the fissure (theta's peak) when found, else 3 contacts above the upper
    molecular-layer sink."""
    for l in lms:
        if l["key"] == "fissure":
            return float(l["x"])
    for l in lms:
        if l["key"] == "ml_a":
            return float(l["x"]) - 3.0
    return None


def place(atl, ev, lms, bad, log=print, rng=None, stretch=False):
    rng = rng or np.random.default_rng(0)
    hinge = hinge_of(lms) if stretch else None
    if stretch and hinge is None:
        log("   no fissure or dentate sink: no hinge, placed without stretch")
    res = F.search(atl, lms, log=log, hinge=hinge, k_sd=K_SD if hinge is not None else None)
    lw = -0.5 * res["chi2"] + res["lp"]
    coarse_idx = np.flatnonzero(~res["fine"])
    fine_idx = np.flatnonzero(res["fine"])
    # with the stretch the grid is four times as deep, so half the lines
    ntc, ntf, nr = (N_TOP_COARSE, N_TOP_FINE, N_RANDOM) if hinge is None else (600, 150, 300)
    top_c = coarse_idx[np.argsort(-lw[coarse_idx])[:ntc]]
    top_f = fine_idx[np.argsort(-lw[fine_idx])[:ntf]]
    rest = np.setdiff1d(coarse_idx, top_c)
    rand = rng.choice(rest, size=min(nr, rest.size), replace=False)
    cand = np.concatenate([top_c, rand, top_f])
    q = np.concatenate([np.ones(top_c.size), np.full(rand.size, rand.size / max(rest.size, 1)),
                        np.ones(top_f.size)])
    prof = B.profiles(ev, bad)
    log("   Method B: %d lines x %d depths x %d sizes; profiles: %s" % (
        cand.size, OFFSETS.size, SCALES.size, ", ".join(prof)))
    alm = {k: res["alm"][k][cand] for k in F.ATLAS_KEYS}
    if hinge is not None:
        sc = np.array([0.9, 1.0, 1.1])         # three sizes with the stretch, to keep the grid's cost
        grid_s = np.repeat(sc, KS.size)
        grid_k = np.tile(KS, sc.size)
    else:
        grid_s, grid_k = SCALES, None
    chi_full = _chi2_a_grid(lms, alm, OFFSETS, grid_s, Ks=grid_k, hinge=hinge)
    ll_parts = {k: np.zeros(chi_full.shape, np.float32) for k in prof}
    ap, ml, tml, tap = (res[k][cand] for k in ("ap", "ml", "tml", "tap"))
    step = 100
    for i in range(0, cand.size, step):
        sl = slice(i, i + step)
        codes, _t = F.lines_codes(atl, ap[sl], ml[sl], tml[sl], tap[sl])
        _tot, parts = B.score(codes, OFFSETS, grid_s, prof, bad, ks=grid_k, hinge=hinge)
        for k, v in parts.items():
            ll_parts[k][sl] = v
    sol = Solution(res, cand, q, lms, ll_parts, chi_full, grid_s=grid_s, grid_k=grid_k, hinge=hinge)
    tot, chi, llb = sol.total()
    out = {"profiles": list(prof), "candidates": int(cand.size)}
    for name, T in (("consolidated", tot), ("A", -0.5 * chi + sol.lp[:, None, None]),
                    ("B", W_B * llb + sol.lp[:, None, None])):
        li, oi, si = sol.best(T)
        out[name] = {"pose": sol.pose(li, oi, si), "chi2_a": float(chi[li, oi, si]),
                     "ll_b": float(llb[li, oi, si]),
                     "parts_b": {k: float(v[li, oi, si]) for k, v in ll_parts.items()}}
    out["samples"] = [sol.pose(*ix) for ix in sol.sample(tot, 400, rng)]
    # the reveal: evidence added family by family
    stops, have_lm, have_pr = [], set(), set()
    found_keys = {l["key"] for l in lms if l["key"] in F.MATCH and l.get("fit", True)}
    for fid, title, lm_keys, pr_keys in FAMILIES:
        add_lm = [k for k in lm_keys if k in found_keys]
        add_pr = [k for k in pr_keys if k in ll_parts]
        if fid != "prior" and not add_lm and not add_pr:
            continue
        have_lm |= set(add_lm)
        have_pr |= set(add_pr)
        last = fid == FAMILIES[-1][0]
        T, _c, _b = sol.total(keep_lm=set(have_lm), keep_prof=set(have_pr), unseen=False)
        li, oi, si = sol.best(T)
        stops.append({"id": fid, "title": title, "landmarks": add_lm, "profiles": add_pr,
                      "best": sol.pose(li, oi, si),
                      "cloud": [sol.pose(*ix) for ix in sol.sample(T, 160, rng)]})
    stops.append({"id": "both", "title": "Both methods together", "landmarks": [], "profiles": [],
                  "best": out["consolidated"]["pose"], "cloud": out["samples"]})
    out["stops"] = stops
    # drop one signal
    drops = []
    all_lm = sorted(found_keys)
    for key in all_lm:
        T, _c, _b = sol.total(keep_lm=set(all_lm) - {key})
        drops.append({"kind": "landmark", "key": key, "pose": sol.pose(*sol.best(T))})
    for key in ll_parts:
        T, _c, _b = sol.total(keep_prof=set(ll_parts) - {key})
        drops.append({"kind": "profile", "key": key, "pose": sol.pose(*sol.best(T))})
    out["drops"] = drops
    out["hinge"] = hinge
    out["sol"] = sol
    return out
