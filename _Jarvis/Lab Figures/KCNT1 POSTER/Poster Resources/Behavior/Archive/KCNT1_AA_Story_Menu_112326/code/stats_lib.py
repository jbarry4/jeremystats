"""Generous, uncorrected statistics for the KCNT1 AA story menu (exploratory, as asked 2026-11-23).

Same rules as the DS story menu: one number per mouse; for each contrast every applicable test is run and
the smallest P is reported with the test that gave it. No correction anywhere.
"""
import math

import numpy as np
from scipy import stats as st


def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return x if math.isfinite(x) else float("nan")


def two(a, b):
    """b against a (a = reference). Mann-Whitney, Welch t, Student t (Brunner-Munzel reported, chosen only at n >= 10)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    out = {"n_a": int(a.size), "n_b": int(b.size), "mean_a": float(np.mean(a)) if a.size else np.nan,
           "mean_b": float(np.mean(b)) if b.size else np.nan, "median_a": float(np.median(a)) if a.size else np.nan,
           "median_b": float(np.median(b)) if b.size else np.nan}
    ps = {}
    if a.size < 3 or b.size < 3 or np.ptp(np.concatenate([a, b])) == 0:
        out.update(p=np.nan, test="", effect=np.nan, hedges_g=np.nan, rank_biserial=np.nan, separated=False)
        return out
    try:
        u = st.mannwhitneyu(b, a, alternative="two-sided", method="exact" if a.size + b.size <= 30 and not
                            (np.unique(np.r_[a, b]).size < a.size + b.size) else "auto")
        ps["Mann-Whitney"] = float(u.pvalue)
        out["rank_biserial"] = float(2.0 * u.statistic / (a.size * b.size) - 1.0)
    except Exception:  # noqa: BLE001
        out["rank_biserial"] = float("nan")
    for name, fn in (("Welch t", lambda: st.ttest_ind(b, a, equal_var=False).pvalue),
                     ("Student t", lambda: st.ttest_ind(b, a, equal_var=True).pvalue),
                     ("Brunner-Munzel", lambda: st.brunnermunzel(b, a).pvalue)):
        try:
            ps[name] = _f(fn())
        except Exception:  # noqa: BLE001
            ps[name] = float("nan")
    sp = math.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)) / max(a.size + b.size - 2, 1))
    d = (b.mean() - a.mean()) / sp if sp > 0 else float("nan")
    J = 1 - 3 / (4 * (a.size + b.size) - 9) if a.size + b.size > 3 else 1.0
    out["hedges_g"] = float(d * J) if math.isfinite(d) else float("nan")
    out["separated"] = bool(b.min() > a.max() or b.max() < a.min())
    out.update({"p_" + k: v for k, v in ps.items()})
    usable = {k: v for k, v in ps.items() if math.isfinite(v) and not (k == "Brunner-Munzel" and min(a.size, b.size) < 10)}
    if usable:
        k = min(usable, key=usable.get)
        out["p"], out["test"] = usable[k], k
    else:
        out["p"], out["test"] = float("nan"), ""
    out["effect"] = out["hedges_g"]
    return out


def km_median(t, e):
    """Median time to the event from a Kaplan-Meier curve; NaN when fewer than half reach it."""
    t, e = np.asarray(t, float), np.asarray(e, int)
    s = 1.0
    for tt in np.unique(t[e == 1]):
        at_risk = (t >= tt).sum()
        d = ((t == tt) & (e == 1)).sum()
        s *= 1.0 - d / at_risk
        if s <= 0.5:
            return float(tt)
    return float("nan")


def cum_reached(t, e, times):
    """Share that has reached the event by each time (1 - Kaplan-Meier survival)."""
    t, e = np.asarray(t, float), np.asarray(e, int)
    out, s = [], 1.0
    ev = np.unique(t[e == 1])
    for x in times:
        s = 1.0
        for tt in ev[ev <= x]:
            at_risk = (t >= tt).sum()
            d = ((t == tt) & (e == 1)).sum()
            s *= 1.0 - d / at_risk
        out.append(1.0 - s)
    return np.array(out)


def _surv_ps(t, e, g):
    from statsmodels.duration.survfunc import survdiff
    ps = {}
    for name, wt in (("log-rank", None), ("Gehan-Breslow", "gb"), ("Tarone-Ware", "tw")):
        try:
            ps[name] = _f(survdiff(t, e, g, weight_type=wt)[1])
        except Exception:  # noqa: BLE001
            ps[name] = float("nan")
    return ps


def surv_two(ta, ea, tb, eb):
    """Time to an event (e.g. the first session with at most one entrance), b against a (a = reference). Mice that never
    reach it are censored at the last session. Log-rank, Gehan-Breslow and Tarone-Ware; generous = smallest P.
    Effect: Cox hazard ratio of b against a (> 1 = b reaches it sooner)."""
    ta, tb = np.asarray(ta, float), np.asarray(tb, float)
    ea, eb = np.asarray(ea, int), np.asarray(eb, int)
    out = {"n_a": int(ta.size), "n_b": int(tb.size),
           "reached_a": float(ea.mean()) if ea.size else np.nan, "reached_b": float(eb.mean()) if eb.size else np.nan,
           "km_median_a": km_median(ta, ea) if ta.size else np.nan, "km_median_b": km_median(tb, eb) if tb.size else np.nan,
           "mean_a": np.nan, "mean_b": np.nan}
    if ta.size < 3 or tb.size < 3 or (ea.sum() + eb.sum()) == 0:
        out.update(p=np.nan, test="", effect=np.nan, hazard_ratio=np.nan)
        return out
    t, e = np.r_[ta, tb], np.r_[ea, eb]
    g = np.r_[np.zeros(ta.size), np.ones(tb.size)]
    ps = _surv_ps(t, e, g)
    try:
        from statsmodels.duration.hazard_regression import PHReg
        fit = PHReg(t, g[:, None], status=e, ties="efron").fit()
        out["hazard_ratio"] = float(np.exp(np.asarray(fit.params)[0]))
    except Exception:  # noqa: BLE001
        out["hazard_ratio"] = float("nan")
    out.update({"p_" + k: v for k, v in ps.items()})
    fin = {k: v for k, v in ps.items() if math.isfinite(v)}
    if fin:
        k = min(fin, key=fin.get)
        out["p"], out["test"] = fin[k], k
    else:
        out["p"], out["test"] = float("nan"), ""
    out["effect"] = out["hazard_ratio"]
    return out


def surv_k(groups):
    """k groups of (t, e): k-sample log-rank family, generous = smallest P."""
    t = np.concatenate([np.asarray(a, float) for a, _ in groups])
    e = np.concatenate([np.asarray(b, int) for _, b in groups])
    g = np.concatenate([np.full(len(a), k) for k, (a, _) in enumerate(groups)])
    out = {"n": int(t.size)}
    if min(len(a) for a, _ in groups) < 3 or e.sum() == 0:
        out.update(p=np.nan, test="", effect=np.nan)
        return out
    ps = _surv_ps(t, e, g)
    out.update({"p_" + k: v for k, v in ps.items()})
    fin = {k: v for k, v in ps.items() if math.isfinite(v)}
    if not fin:
        out.update(p=np.nan, test="", effect=np.nan)
        return out
    k = min(fin, key=fin.get)
    out.update(p=fin[k], test=k, effect=np.nan)
    return out


def corr_rank(x, y):
    """Rank correlations only (Spearman, Kendall), for values with a tied 'not reached' end."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    out = {"n": int(x.size)}
    if x.size < 5 or np.ptp(x) == 0 or np.ptp(y) == 0:
        out.update(p=np.nan, test="", effect=np.nan, rho=np.nan)
        return out
    r_s = st.spearmanr(x, y)
    ps = {"Spearman": _f(r_s.pvalue), "Kendall": _f(st.kendalltau(x, y).pvalue)}
    out["rho"] = float(r_s.statistic)
    out.update({"p_" + k: v for k, v in ps.items()})
    fin = {k: v for k, v in ps.items() if math.isfinite(v)}
    k = min(fin, key=fin.get)
    out.update(p=fin[k], test=k, effect=out["rho"])
    return out


def corr(x, y):
    """y against x: Spearman, Pearson, Kendall; generous = smallest P."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    out = {"n": int(x.size)}
    if x.size < 5 or np.ptp(x) == 0 or np.ptp(y) == 0:
        out.update(p=np.nan, test="", effect=np.nan, rho=np.nan)
        return out
    ps = {}
    r_s = st.spearmanr(x, y)
    out["rho"] = float(r_s.statistic)
    ps["Spearman"] = _f(r_s.pvalue)
    try:
        r, pp = st.pearsonr(x, y)
        ps["Pearson"] = _f(pp)
        out["pearson_r"] = float(r)
    except Exception:  # noqa: BLE001
        out["pearson_r"] = float("nan")
    try:
        ps["Kendall"] = _f(st.kendalltau(x, y).pvalue)
    except Exception:  # noqa: BLE001
        pass
    out.update({"p_" + k: v for k, v in ps.items()})
    fin = {k: v for k, v in ps.items() if math.isfinite(v)}
    k = min(fin, key=fin.get)
    out["p"], out["test"] = fin[k], k
    out["effect"] = out["rho"]
    return out


def three(groups):
    """Ordered groups (WT, Het, Hom): ANOVA, Kruskal-Wallis, ordered trend (Kendall tau-b on the level = J-T)."""
    gs = [np.asarray(g, float) for g in groups]
    gs = [g[np.isfinite(g)] for g in gs]
    out = {"n": int(sum(g.size for g in gs)), "means": [float(g.mean()) if g.size else np.nan for g in gs]}
    if min(g.size for g in gs) < 3:
        out.update(p=np.nan, test="", effect=np.nan)
        return out
    ps = {}
    try:
        ps["ANOVA"] = _f(st.f_oneway(*gs).pvalue)
    except Exception:  # noqa: BLE001
        pass
    try:
        ps["Kruskal-Wallis"] = _f(st.kruskal(*gs).pvalue)
    except Exception:  # noqa: BLE001
        pass
    lvl = np.concatenate([np.full(g.size, k) for k, g in enumerate(gs)])
    val = np.concatenate(gs)
    kt = st.kendalltau(lvl, val)
    ps["ordered trend"] = _f(kt.pvalue)
    out["tau"] = float(kt.statistic)
    allv = np.concatenate(gs)
    ss_b = sum(g.size * (g.mean() - allv.mean()) ** 2 for g in gs)
    ss_t = ((allv - allv.mean()) ** 2).sum()
    out["eta2"] = float(ss_b / ss_t) if ss_t > 0 else float("nan")
    out.update({"p_" + k: v for k, v in ps.items()})
    fin = {k: v for k, v in ps.items() if math.isfinite(v)}
    if not fin:
        out.update(p=np.nan, test="", effect=np.nan)
        return out
    k = min(fin, key=fin.get)
    out["p"], out["test"] = fin[k], k
    out["effect"] = out["tau"]
    return out


def fisher(a_yes, a_n, b_yes, b_n):
    """Share of 'yes' in b against a: Fisher's exact test."""
    t = [[b_yes, b_n - b_yes], [a_yes, a_n - a_yes]]
    o, p = st.fisher_exact(t)
    return {"p": float(p), "test": "Fisher exact", "effect": float(b_yes / b_n - a_yes / a_n) if a_n and b_n else np.nan,
            "n_a": a_n, "n_b": b_n, "mean_a": a_yes / a_n if a_n else np.nan, "mean_b": b_yes / b_n if b_n else np.nan}


# ---------------------------------------------------------------- circular
def circ_mean(deg, w=None):
    a = np.radians(np.asarray(deg, float))
    w = np.ones_like(a) if w is None else np.asarray(w, float)
    C, S = (w * np.cos(a)).sum() / w.sum(), (w * np.sin(a)).sum() / w.sum()
    return float(np.degrees(np.arctan2(S, C))), float(np.hypot(C, S))


def rayleigh(deg):
    a = np.radians(np.asarray(deg, float))
    n = a.size
    R = np.hypot(np.cos(a).sum(), np.sin(a).sum()) / n
    z = n * R ** 2
    p = math.exp(math.sqrt(1 + 4 * n + 4 * (n ** 2 - (n * R) ** 2)) - (1 + 2 * n))
    return {"p": float(min(max(p, 0.0), 1.0)), "R": float(R), "n": n, "test": "Rayleigh"}


def vtest(deg, mu_deg):
    """V test: are angles clustered around mu?"""
    a = np.radians(np.asarray(deg, float))
    n = a.size
    V = np.cos(a - np.radians(mu_deg)).sum()
    u = V * math.sqrt(2.0 / n)
    return {"p": float(1 - st.norm.cdf(u)), "V": float(V / n), "n": n, "test": "V test"}


def perm_circ(a_deg, b_deg, n=20000, seed=1):
    """Two groups of angles: permutation tests for a different mean direction (resultant difference) and a different
    spread (difference in mean resultant length). Returns the smaller as the generous P, both reported."""
    a, b = np.radians(np.asarray(a_deg, float)), np.radians(np.asarray(b_deg, float))
    allv = np.r_[a, b]
    na = a.size
    rng = np.random.RandomState(seed)

    def stats_(x, y):
        mx = np.arctan2(np.sin(x).mean(), np.cos(x).mean())
        my = np.arctan2(np.sin(y).mean(), np.cos(y).mean())
        Rx, Ry = np.hypot(np.sin(x).mean(), np.cos(x).mean()), np.hypot(np.sin(y).mean(), np.cos(y).mean())
        dm = abs((mx - my + np.pi) % (2 * np.pi) - np.pi)
        return dm, abs(Rx - Ry)

    d0, r0 = stats_(a, b)
    cnt_d = cnt_r = 0
    for _ in range(n):
        p = rng.permutation(allv)
        d, r = stats_(p[:na], p[na:])
        cnt_d += d >= d0 - 1e-12
        cnt_r += r >= r0 - 1e-12
    pd_, pr_ = (cnt_d + 1) / (n + 1), (cnt_r + 1) / (n + 1)
    return {"p_direction": pd_, "p_spread": pr_, "p": min(pd_, pr_), "test": "permutation (direction / spread)",
            "diff_deg": float(np.degrees(d0)), "diff_R": float(r0)}
