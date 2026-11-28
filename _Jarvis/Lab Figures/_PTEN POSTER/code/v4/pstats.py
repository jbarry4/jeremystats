"""Generous, uncorrected statistics, as in the PTEN menus (stats_lib.py of the DS story and Jeremy menus): one number per
mouse; for each contrast every applicable test is run and the smallest P is kept. Copied here so the poster's figures
run without the menu's battery folder (only `two`, `paired` and `corr` are needed)."""
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
    """b against a, unpaired: Mann-Whitney (exact), Welch t, Student t, Brunner-Munzel; smallest P."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if a.size < 3 or b.size < 3:
        return float("nan")
    ps = []
    fns = [lambda: st.mannwhitneyu(b, a, alternative="two-sided", method="exact" if a.size + b.size <= 30 else "auto").pvalue,
           lambda: st.ttest_ind(b, a, equal_var=False).pvalue, lambda: st.ttest_ind(b, a, equal_var=True).pvalue]
    if min(a.size, b.size) >= 10:                     # as the menus: Brunner-Munzel only from 10 a group
        fns.append(lambda: st.brunnermunzel(b, a).pvalue)
    for fn in fns:
        try:
            ps.append(_f(fn()))
        except Exception:  # noqa: BLE001
            pass
    return float(np.nanmin(ps))


def paired(a, b):
    """paired t and Wilcoxon; smallest P (as jpages.paired_p)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    ps = [st.ttest_rel(a[ok], b[ok]).pvalue]
    try:
        ps.append(st.wilcoxon(a[ok], b[ok]).pvalue)
    except ValueError:
        pass
    return float(np.nanmin(ps))


def corr(x, y):
    """Spearman rho and the smallest P of Spearman, Pearson and Kendall."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = x.size
    rx, ry = st.rankdata(x), st.rankdata(y)
    rho = float(np.corrcoef(rx, ry)[0, 1])
    if n <= 9 and np.unique(x).size == n and np.unique(y).size == n:       # exact Spearman over every permutation, as the menus
        import itertools
        cx, cy = rx - rx.mean(), ry - ry.mean()
        den = math.sqrt(float((cx ** 2).sum() * (cy ** 2).sum()))
        P = np.array(list(itertools.permutations(range(n))), dtype=np.int8)
        null = (cx[P] @ cy) / den
        p_s = float((np.abs(null) >= abs(rho) - 1e-12).mean())
    else:
        p_s = _f(st.spearmanr(x, y).pvalue)
    ps = [p_s, _f(st.pearsonr(x, y)[1]), _f(st.kendalltau(x, y).pvalue)]
    return rho, float(np.nanmin(ps))


def stars(p):
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""


def pfmt(p):
    if not np.isfinite(p):
        return "n/a"
    if p < 0.001:
        return "%.0e" % p if p < 1e-4 else "%.4f" % p
    return "%.3f" % p if p < 0.01 else "%.2f" % p
