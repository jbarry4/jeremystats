"""Generous, uncorrected statistics for the story menu (exploratory, as asked 2026-11-23).

One number per mouse. For every contrast every applicable test is run and the smallest P is
reported with the test that gave it ("generous"). No correction anywhere.

Groupings
  IED groups : control / IED- / IED+          (lab sheet; m7 stays IED-)
  KO groups  : control / low KO (<10%) / high KO (>=15%)
  KO %       : % knockout as a number (controls at 0, and PTEN only)
"""
import itertools
import json
import math
import os

import numpy as np
from scipy import stats as st

BATTERY = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery"
META = [m for m in json.load(open(os.path.join(BATTERY, "data", "meta.json"))) if m["lab"] not in ("m6",)]
for m in META:
    m["ok"] = m["lab"] != "m51"
LABS = [m["lab"] for m in META if m["ok"]]
M = {m["lab"]: m for m in META}
LOW_KO, HIGH_KO = 10.0, 15.0


def group_of(lab):
    return M[lab]["subgroup"]           # CTL / IED- / IED+


def ko_group(lab):
    m = M[lab]
    if m["group"] == "CTL":
        return "CTL"
    return "low KO" if m["ko"] < LOW_KO else ("high KO" if m["ko"] >= HIGH_KO else "mid KO")


_PERMS = {}
_PX = {}


def _perms(n):
    if n not in _PERMS:
        _PERMS[n] = np.array(list(itertools.permutations(range(n))), dtype=np.int8)
    return _PERMS[n]


def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return x if math.isfinite(x) else float("nan")


def two(a, b):
    """b against a. Every applicable two-group test; generous = smallest P."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    out = {"n_a": int(a.size), "n_b": int(b.size), "mean_a": float(a.mean()), "mean_b": float(b.mean()),
           "median_a": float(np.median(a)), "median_b": float(np.median(b))}
    ps = {}
    try:
        u = st.mannwhitneyu(b, a, alternative="two-sided", method="exact" if a.size + b.size <= 30 else "auto")
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
    sp = math.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)) / max(a.size + b.size - 2, 1)) if a.size > 1 and b.size > 1 else float("nan")
    d = (b.mean() - a.mean()) / sp if sp and math.isfinite(sp) and sp > 0 else float("nan")
    J = 1 - 3 / (4 * (a.size + b.size) - 9) if a.size + b.size > 3 else 1.0
    out["hedges_g"] = float(d * J) if math.isfinite(d) else float("nan")
    out["separated"] = bool(b.min() > a.max() or b.max() < a.min())
    out.update({"p_" + k: v for k, v in ps.items()})
    # Brunner-Munzel's t approximation is not valid under 10 a group (scipy says so): reported, never chosen.
    usable = {k: v for k, v in ps.items() if math.isfinite(v) and not (k == "Brunner-Munzel" and min(a.size, b.size) < 10)}
    if usable:
        k = min(usable, key=usable.get)
        out["p"], out["test"] = usable[k], k
    else:
        out["p"], out["test"] = float("nan"), ""
    out["effect"] = out["hedges_g"]
    return out


def corr(x, y):
    """y against x. Spearman (exact over every permutation for n <= 9), Pearson, Kendall; generous = smallest P."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = x.size
    out = {"n": int(n)}
    rx, ry = st.rankdata(x), st.rankdata(y)
    rho = float(np.corrcoef(rx, ry)[0, 1]) if np.ptp(rx) > 0 and np.ptp(ry) > 0 else float("nan")
    ps = {}
    if math.isfinite(rho):
        if n <= 9 and np.unique(x).size == n and np.unique(y).size == n:
            cx, cy = rx - rx.mean(), ry - ry.mean()
            den = math.sqrt(float((cx ** 2).sum() * (cy ** 2).sum()))
            key = tuple(cx)
            if key not in _PX:
                _PX[key] = cx[_perms(n)].astype(np.float64)
            null = (_PX[key] @ cy) / den
            ps["Spearman (exact)"] = float((np.abs(null) >= abs(rho) - 1e-12).mean())
        else:
            ps["Spearman"] = _f(st.spearmanr(x, y).pvalue)
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
    out["rho"] = rho
    out.update({"p_" + k: v for k, v in ps.items()})
    fin = {k: v for k, v in ps.items() if math.isfinite(v)}
    if fin:
        k = min(fin, key=fin.get)
        out["p"], out["test"] = fin[k], k
    else:
        out["p"], out["test"] = float("nan"), ""
    out["effect"] = rho
    return out


def three(groups):
    """Three ordered groups (control first). One-way ANOVA, Kruskal-Wallis, ordered trend (Kendall tau-b
    on the level = Jonckheere-Terpstra); generous = smallest P."""
    gs = [np.asarray(g, float) for g in groups]
    out = {"n": int(sum(g.size for g in gs)), "means": [float(g.mean()) for g in gs]}
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
    out["tau"] = float(kt.correlation)
    allv = np.concatenate(gs)
    ss_b = sum(g.size * (g.mean() - allv.mean()) ** 2 for g in gs)
    ss_t = ((allv - allv.mean()) ** 2).sum()
    out["eta2"] = float(ss_b / ss_t) if ss_t > 0 else float("nan")
    out.update({"p_" + k: v for k, v in ps.items()})
    fin = {k: v for k, v in ps.items() if math.isfinite(v)}
    if fin:
        k = min(fin, key=fin.get)
        out["p"], out["test"] = fin[k], k
    else:
        out["p"], out["test"] = float("nan"), ""
    out["effect"] = out["tau"]
    return out


CONTRASTS = [
    # id, grouping, words
    ("IEDneg_vs_CTL", "IED groups", "IED- against control"),
    ("IEDpos_vs_CTL", "IED groups", "IED+ against control"),
    ("IEDpos_vs_IEDneg", "IED groups", "IED+ against IED-"),
    ("IED3", "IED groups", "control / IED- / IED+"),
    ("lowKO_vs_CTL", "KO groups", "low KO against control"),
    ("highKO_vs_CTL", "KO groups", "high KO against control"),
    ("highKO_vs_lowKO", "KO groups", "high KO against low KO"),
    ("KO3", "KO groups", "control / low KO / high KO"),
    ("KO_dose_all", "KO %", "against % knockout, all mice (controls at 0)"),
    ("KO_dose_PTEN", "KO %", "against % knockout, PTEN mice only"),
    ("PTEN_vs_CTL", "PTEN vs control", "PTEN against control"),
]
CMAP = {c[0]: c for c in CONTRASTS}


def contrasts(values):
    """values: {lab: number}. Returns one dict per contrast that the numbers allow."""
    v = {lab: _f(values.get(lab)) for lab in LABS}
    fin = {lab: x for lab, x in v.items() if math.isfinite(x)}
    if len(fin) < 6 or np.ptp(list(fin.values())) == 0:
        return []
    sg = {lab: group_of(lab) for lab in fin}
    kg = {lab: ko_group(lab) for lab in fin}
    ko = {lab: M[lab]["ko"] for lab in fin}

    def pick(pred):
        return np.array([x for lab, x in fin.items() if pred(lab)])

    out = []

    def add(cid, res):
        if res is None:
            return
        g = CMAP[cid]
        res.update({"contrast": cid, "grouping": g[1], "words": g[2]})
        out.append(res)

    ctl = pick(lambda l: sg[l] == "CTL")
    ineg = pick(lambda l: sg[l] == "IED-")
    ipos = pick(lambda l: sg[l] == "IED+")
    low = pick(lambda l: kg[l] == "low KO")
    high = pick(lambda l: kg[l] == "high KO")
    pten = pick(lambda l: sg[l] != "CTL")
    for cid, a, b in (("IEDneg_vs_CTL", ctl, ineg), ("IEDpos_vs_CTL", ctl, ipos), ("IEDpos_vs_IEDneg", ineg, ipos),
                      ("lowKO_vs_CTL", ctl, low), ("highKO_vs_CTL", ctl, high), ("highKO_vs_lowKO", low, high),
                      ("PTEN_vs_CTL", ctl, pten)):
        if a.size >= 3 and b.size >= 3 and np.ptp(np.concatenate([a, b])) > 0:
            add(cid, two(a, b))
    if ctl.size >= 3 and ineg.size >= 3 and ipos.size >= 3:
        add("IED3", three([ctl, ineg, ipos]))
    if ctl.size >= 3 and low.size >= 3 and high.size >= 3:
        add("KO3", three([ctl, low, high]))
    labs_all = list(fin)
    if len(labs_all) >= 9:
        add("KO_dose_all", corr([ko[l] for l in labs_all], [fin[l] for l in labs_all]))
    lp = [l for l in labs_all if sg[l] != "CTL"]
    if len(lp) >= 6 and np.ptp([fin[l] for l in lp]) > 0:
        add("KO_dose_PTEN", corr([ko[l] for l in lp], [fin[l] for l in lp]))
    return out
