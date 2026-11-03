# -*- coding: utf-8 -*-
"""rcstats.py -- are these two clusters genuinely different, or forced?

Asked for 2026-10-06, at the single, pooled and pool-of-pools levels:
"are those clusters statistically different?" -- meaning: did k-means find
two groups that are there, or cut one cloud in two because it was asked for
two (it always will).

A t-test or MANOVA between the two k-means clusters is NOT on this list, on
purpose: k-means makes its clusters differ, so such a test says "different"
of any cloud at all. Every test here asks a question that a single cloud
would answer "no" to.

FOUR TESTS, each with its own answer, at k = 2 only (the question is "one
group or two"; past two there is no single yes or no):

  SigClust (recommended) -- Liu, Hayes, Nobel & Marron 2008. The 2-means
      cluster index (within-cluster SS / total SS) of the data, against
      the same index for clouds simulated from ONE Gaussian with the data's
      own covariance. Small p: the split is better than splitting one
      Gaussian would give. Pro: answers "forced or not" directly, in all
      three dimensions. Con: its null is Gaussian, so one SKEWED cloud can
      also beat it.
  Dip -- Hartigan & Hartigan 1985, on the DS->IED split axis (each event's
      position along the line between the two centres). Small p: there is
      a gap -- two humps, not one. Pro: shape-free (its null is the least
      favourable unimodal one). Con: one dimension only; two groups that
      overlap on that line read as one.
  Stability -- resample the events with replacement, re-cluster, and see
      whether each event keeps its cluster (adjusted Rand against the
      fit). Pro: says how much of the split is the data and how much the
      draw. Con: a stable split can still be a forced one -- a skewed cloud
      cuts in the same place every time.
  GMM -- one Gaussian against two by BIC, and whether the two are the
      DS/IED split (adjusted Rand), as Pooled already reports
      (`rootcanalpool.gmm_test`). Pro: a likelihood answer. Con: two
      Gaussians fit a skewed cloud better than one, so the agreement has to
      be read beside it.

The dip statistic is a port of the algorithm in R's `diptest` (Maechler's
C code of Hartigan's AS 217, with its later corrections); its p-value is
simulated against the uniform, as `diptest` calibrates it.
"""
from __future__ import annotations

import numpy as np

from . import lazyimp

HAVE_SKLEARN = lazyimp.have("sklearn")
SEED = 0
N_SIM = 200            # SigClust and dip null draws
N_BOOT = 50            # stability resamples
MAX_N = 2000           # larger sets are sub-sampled (seeded) for speed
ALPHA = 0.05

TESTS = ("sigclust", "dip", "stability", "gmm")
RECOMMENDED = "sigclust"

ABOUT = {
    "sigclust": {
        "name": "SigClust",
        "asks": "Is the split better than splitting ONE Gaussian cloud of "
                "the same shape would give?",
        "pro": "Answers forced-or-genuine directly, in all three dimensions.",
        "con": "Its null is a Gaussian: one skewed cloud can beat it too.",
    },
    "dip": {
        "name": "Dip test",
        "asks": "Along the DS→IED line, is there a gap -- two humps, or one?",
        "pro": "Shape-free: its null is the least favourable single hump.",
        "con": "One dimension only: groups that overlap on that line read "
               "as one.",
    },
    "stability": {
        "name": "Stability",
        "asks": "Resampled and re-clustered, does each event keep its "
                "cluster?",
        "pro": "Says how much of the split is the data and how much the draw.",
        "con": "A stable split can still be forced: a skewed cloud is cut in "
               "the same place every time.",
    },
    "gmm": {
        "name": "GMM ΔBIC + agreement",
        "asks": "Do two Gaussians fit better than one -- and are those two "
                "the DS / IED split?",
        "pro": "A likelihood answer, with the check that it is about these "
               "two groups.",
        "con": "Two Gaussians fit a skewed cloud better than one; read the "
               "agreement beside the ΔBIC.",
    },
}


class StatsError(ValueError):
    pass


# --------------------------------------------------------------------------
# The dip
# --------------------------------------------------------------------------
def dip_statistic(x):
    """Hartigan's dip of a sample, sorted or not."""
    x = np.sort(np.asarray(x, dtype=float))
    n = int(x.size)
    if n < 2 or x[-1] == x[0]:
        return 0.0
    # TIES. The hull steps divide by differences of x; a tie makes one zero.
    # Tied values are spread by a hair, in order, which leaves every
    # distance between distinct values as it was.
    if np.any(np.diff(x) == 0):
        span = float(x[-1] - x[0])
        x = x + np.arange(n) * (span * 1e-12)
    # 1-based arrays, as the reference code is written.
    X = np.empty(n + 1)
    X[1:] = x
    mn = np.zeros(n + 2, dtype=int)
    mj = np.zeros(n + 2, dtype=int)
    mn[1] = 1
    for j in range(2, n + 1):
        mn[j] = j - 1
        while True:
            mnj = mn[j]
            mnmnj = mn[mnj]
            if mnj == 1 or ((X[j] - X[mnj]) * (mnj - mnmnj)
                            < (X[mnj] - X[mnmnj]) * (j - mnj)):
                break
            mn[j] = mnmnj
    mj[n] = n
    for k in range(n - 1, 0, -1):
        mj[k] = k + 1
        while True:
            mjk = mj[k]
            mjmjk = mj[mjk]
            if mjk == n or ((X[k] - X[mjk]) * (mjk - mjmjk)
                            < (X[mjk] - X[mjmjk]) * (k - mjk)):
                break
            mj[k] = mjmjk
    low, high = 1, n
    dip = 1.0
    gcm = np.zeros(n + 2, dtype=int)
    lcm = np.zeros(n + 2, dtype=int)
    # Each pass narrows the modal interval; a cap so a degenerate input can
    # never hold a request forever.
    for _pass in range(4 * n + 8):
        if low >= high:
            break
        ic = 1
        gcm[1] = high
        while gcm[ic] > low:
            i = gcm[ic]
            ic += 1
            gcm[ic] = mn[i]
        l_gcm = ic
        ic = 1
        lcm[1] = low
        while lcm[ic] < high:
            i = lcm[ic]
            ic += 1
            lcm[ic] = mj[i]
        l_lcm = ic
        d = 0.0
        ig = ih = 1
        if l_gcm != 2 or l_lcm != 2:
            ix, iv = l_gcm, 2
            while True:
                gcmix, lcmiv = gcm[ix], lcm[iv]
                if gcmix > lcmiv:
                    gcmi1 = gcm[ix + 1]
                    dx = ((lcmiv - gcmi1 + 1)
                          - (X[lcmiv] - X[gcmi1]) * (gcmix - gcmi1)
                          / (X[gcmix] - X[gcmi1]))
                    iv += 1
                    if dx >= d:
                        d, ig, ih = dx, ix + 1, iv - 1
                else:
                    lcmiv1 = lcm[iv - 1]
                    dx = ((X[gcmix] - X[lcmiv1]) * (lcmiv - lcmiv1)
                          / (X[lcmiv] - X[lcmiv1]) - (gcmix - lcmiv1 - 1))
                    ix -= 1
                    if dx >= d:
                        d, ig, ih = dx, ix + 1, iv
                if ix < 1:
                    ix = 1
                if iv > l_lcm:
                    iv = l_lcm
                if gcm[ix] == lcm[iv]:
                    break
        else:
            # Both hulls are the straight line from low to high: the modal
            # interval cannot narrow further, and the dip is what it is.
            break
        if d < dip:
            break
        dip_l = 0.0
        for j in range(ig, l_gcm):
            max_t = 1.0
            jb, je = gcm[j + 1], gcm[j]
            if je - jb > 1 and X[je] != X[jb]:
                C = (je - jb) / (X[je] - X[jb])
                for jj in range(jb, je + 1):
                    t = (jj - jb + 1) - (X[jj] - X[jb]) * C
                    if max_t < t:
                        max_t = t
            if dip_l < max_t:
                dip_l = max_t
        dip_u = 0.0
        for j in range(ih, l_lcm):
            max_t = 1.0
            jb, je = lcm[j], lcm[j + 1]
            if je - jb > 1 and X[je] != X[jb]:
                C = (je - jb) / (X[je] - X[jb])
                for jj in range(jb, je + 1):
                    t = (X[jj] - X[jb]) * C - (jj - jb - 1)
                    if max_t < t:
                        max_t = t
            if dip_u < max_t:
                dip_u = max_t
        dipnew = max(dip_u, dip_l)
        if dip < dipnew:
            dip = dipnew
        if low == gcm[ig] and high == lcm[ih]:
            break
        low, high = gcm[ig], lcm[ih]
    return dip / (2.0 * n)


def dip_test(x, n_sim=N_SIM, seed=SEED):
    """The dip, and its p-value against the uniform (the least favourable
    unimodal null), simulated with the same n."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = int(x.size)
    if n < 10:
        raise StatsError("Too few events (%d) for a dip test." % n)
    d = dip_statistic(x)
    rng = np.random.default_rng(seed)
    null = np.array([dip_statistic(rng.random(n)) for _ in range(n_sim)])
    p = float((1 + np.sum(null >= d)) / (1 + n_sim))
    return {"dip": float(d), "p": p, "n": n, "n_sim": int(n_sim)}


# --------------------------------------------------------------------------
# SigClust and stability
# --------------------------------------------------------------------------
def _two_means(Z, seed, n_init=3):
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=2, n_init=n_init, random_state=seed).fit(Z)
    return km


def cluster_index(Z, labels):
    """Within-cluster sum of squares over total, for a 2-way split."""
    Z = np.asarray(Z, dtype=float)
    tot = float(((Z - Z.mean(axis=0)) ** 2).sum())
    if tot <= 0:
        return 1.0
    w = 0.0
    for c in np.unique(labels):
        g = Z[labels == c]
        w += float(((g - g.mean(axis=0)) ** 2).sum())
    return w / tot


def sigclust(Z, n_sim=N_SIM, seed=SEED):
    Z = np.asarray(Z, dtype=float)
    n, d = Z.shape
    if n < 20:
        raise StatsError("Too few complete events (%d) for SigClust." % n)
    km = _two_means(Z, seed)
    ci = cluster_index(Z, km.labels_)
    ev = np.clip(np.linalg.eigvalsh(np.cov(Z, rowvar=False)), 1e-12, None)
    rng = np.random.default_rng(seed)
    null = []
    for s in range(n_sim):
        sim = rng.standard_normal((n, d)) * np.sqrt(ev)
        null.append(cluster_index(sim, _two_means(sim, seed + s + 1,
                                                  n_init=1).labels_))
    null = np.asarray(null)
    p = float((1 + np.sum(null <= ci)) / (1 + n_sim))
    return {"ci": float(ci), "p": p, "n": int(n), "n_sim": int(n_sim),
            "null_median": float(np.median(null)),
            "null_q05": float(np.quantile(null, 0.05))}


def _ari(a, b):
    from sklearn.metrics import adjusted_rand_score
    return float(adjusted_rand_score(a, b))


def stability(Z, labels, n_boot=N_BOOT, seed=SEED):
    Z = np.asarray(Z, dtype=float)
    labels = np.asarray(labels)
    n = Z.shape[0]
    if n < 20:
        raise StatsError("Too few complete events (%d) to resample." % n)
    rng = np.random.default_rng(seed)
    aris, same = [], np.zeros(n)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        km = _two_means(Z[idx], seed + b + 1, n_init=1)
        d = ((Z[:, None, :] - km.cluster_centers_[None]) ** 2).sum(axis=2)
        lab = np.argmin(d, axis=1)
        # Cluster numbers are arbitrary: the matching that agrees most.
        flip = 1 - lab
        if (flip == labels).sum() > (lab == labels).sum():
            lab = flip
        aris.append(_ari(labels, lab))
        same += (lab == labels)
    keep = same / n_boot
    return {"ari_mean": float(np.mean(aris)),
            "ari_q05": float(np.quantile(aris, 0.05)),
            "unstable_frac": float(np.mean(keep < 0.9)),
            "n": int(n), "n_boot": int(n_boot)}


# --------------------------------------------------------------------------
# All of them
# --------------------------------------------------------------------------
def run(Z, labels, centres_z, tests=TESTS, n_sim=N_SIM, n_boot=N_BOOT,
        seed=SEED, gmm=None):
    """Every test asked for, on the complete events of a k = 2 fit.

    `Z` [n x 3] z values of the complete events; `labels` their cluster
    (0 or 1); `centres_z` the two centres. `gmm` is a GMM answer already
    computed for the same events (Pooled has one), or None to compute it.
    """
    if not HAVE_SKLEARN:
        raise StatsError("These tests need scikit-learn, which is not "
                         "installed here.")
    Z = np.asarray(Z, dtype=float)
    labels = np.asarray(labels, dtype=int)
    ok = np.isfinite(Z).all(axis=1)
    Z, labels = Z[ok], labels[ok]
    if len(np.unique(labels)) != 2:
        raise StatsError("The tests compare two clusters: this fit's "
                         "complete events are not in two.")
    n_all = int(Z.shape[0])
    sub = None
    if n_all > MAX_N:
        rng = np.random.default_rng(seed)
        sub = np.sort(rng.choice(n_all, MAX_N, replace=False))
        Z, labels = Z[sub], labels[sub]
    out = {"n": n_all, "n_used": int(Z.shape[0]),
           "subsampled": sub is not None, "tests": {},
           "recommended": RECOMMENDED, "about": ABOUT}
    c = np.asarray(centres_z, dtype=float)
    for t in tests:
        try:
            if t == "sigclust":
                r = sigclust(Z, n_sim=n_sim, seed=seed)
                r["genuine"] = r["p"] < ALPHA
                r["say"] = ("p = %.3f: %s" % (
                    r["p"], "the split is stronger than one Gaussian cloud "
                    "split in two would give" if r["genuine"] else
                    "one Gaussian cloud split in two does as well -- the "
                    "split could be forced"))
            elif t == "dip":
                u = c[1] - c[0]
                nu = float(np.linalg.norm(u)) or 1.0
                proj = (Z - (c[0] + c[1]) / 2.0) @ (u / nu)
                r = dip_test(proj, n_sim=n_sim, seed=seed)
                r["genuine"] = r["p"] < ALPHA
                r["say"] = ("dip %.4f, p = %.3f: %s" % (
                    r["dip"], r["p"], "two humps along the DS→IED line" if
                    r["genuine"] else "one hump along the DS→IED line"))
            elif t == "stability":
                r = stability(Z, labels, n_boot=n_boot, seed=seed)
                r["genuine"] = r["ari_mean"] >= 0.9
                r["say"] = ("adjusted Rand %.2f over %d resamples; %.0f%% "
                            "of events change cluster in more than 1 in 10"
                            % (r["ari_mean"], r["n_boot"],
                               100 * r["unstable_frac"]))
            elif t == "gmm":
                if gmm is None:
                    from . import rootcanalpool
                    mu = Z.mean(axis=0)
                    sd = Z.std(axis=0)
                    sd[sd == 0] = 1.0
                    gmm = rootcanalpool.gmm_test(
                        Z, mu, sd, calls=["ied" if v else "ds"
                                          for v in labels])
                r = {"delta": gmm.get("delta"),
                     "agree": (gmm.get("agree") or {}).get("ari"),
                     "verdict": gmm.get("verdict")}
                r["genuine"] = bool(r["delta"] is not None and r["delta"] > 10
                                    and (r["agree"] or 0) >= 0.5)
                r["say"] = gmm.get("verdict")
            else:
                continue
            out["tests"][t] = r
        except StatsError as exc:
            out["tests"][t] = {"error": str(exc)}
    rec = out["tests"].get(RECOMMENDED) or {}
    out["verdict"] = ("genuine" if rec.get("genuine") else "could be forced"
                      if "genuine" in rec else None)
    return out
