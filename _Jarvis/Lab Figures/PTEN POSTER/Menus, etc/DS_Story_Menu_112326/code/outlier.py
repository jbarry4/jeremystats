"""Is one mouse an outlier? Two standard tests (asked 2026-11-23 for m7 in Story 1).

grubbs(values, target)      Grubbs' test (two-sided) within one group: G = |x - mean| / SD of the group; the P value
                            allows for the tested mouse being the most extreme one of the group.
line_outlier(x, y, target)  against a least-squares line: the mouse's studentized deleted residual (the line fitted
                            without it), t with n - 3 degrees of freedom; P allows for it being the most extreme of n.
"""
import numpy as np
from scipy import stats as st


def grubbs(values, target):
    labs = [l for l in values if np.isfinite(values[l])]
    x = np.array([values[l] for l in labs], float)
    n = x.size
    m, s = x.mean(), x.std(ddof=1)
    g_all = np.abs(x - m) / s
    i = labs.index(target)
    G = float(g_all[i])
    den = (n - 1) ** 2 - n * G ** 2
    if den <= 0:
        p = 0.0
    else:
        t2 = n * (n - 2) * G ** 2 / den
        p = float(min(1.0, 2 * n * st.t.sf(np.sqrt(t2), n - 2)))
    crit_t = st.t.isf(0.05 / (2 * n), n - 2)
    g_crit = (n - 1) / np.sqrt(n) * np.sqrt(crit_t ** 2 / (n - 2 + crit_t ** 2))
    return {"G": G, "G_crit_05": float(g_crit), "most_extreme": bool(np.argmax(g_all) == i), "p": p, "n": n}


def line_outlier(x, y, labs, target):
    x, y = np.asarray(x, float), np.asarray(y, float)
    i = list(labs).index(target)
    keep = np.arange(x.size) != i
    b, a = np.polyfit(x[keep], y[keep], 1)
    res_k = y[keep] - (a + b * x[keep])
    n = x.size
    s = np.sqrt((res_k ** 2).sum() / (n - 3))
    xm = x[keep].mean()
    h = 1.0 / (n - 1) + (x[i] - xm) ** 2 / ((x[keep] - xm) ** 2).sum()
    t = (y[i] - (a + b * x[i])) / (s * np.sqrt(1 + h))
    p = float(min(1.0, n * 2 * st.t.sf(abs(t), n - 3)))
    return {"t": float(t), "p": p, "n": n, "predicted": float(a + b * x[i]), "observed": float(y[i])}
