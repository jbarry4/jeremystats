"""Floor speed, factored into every comparison (round 2, 2026-11-23 evening).

Every per-mouse number is moved to one floor speed before any test:
    adjusted = value - b x (the mouse's floor speed - REF)
where b is the floor-speed slope shared by the three genotypes (OLS: value ~ genotype + speed, all 56 mice) and REF is
the median floor speed of the 56 mice. The same generous tests as before then run on the adjusted values, plus a
van Elteren test (Wilcoxon inside the slow / medium / fast bands, combined); the smallest P is reported.
Session values are adjusted the same way with that day's measured speed and one slope per measure (training sessions
pooled, session as a factor). The criterion uses Cox models with speed and speed-stratified log-rank tests.
Mixed models over s1-s16 get speed and speed x session terms. Preferred directions get a permutation test that only
swaps labels inside a speed band.
"""
import math
import os
import pickle
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as st
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.duration.survfunc import survdiff

import stats_lib as S

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
TAB = os.path.join(HERE, "tables")
A = pickle.load(open(os.path.join(HERE, "analysis.pkl"), "rb"))
VALS, MICE, DESC, RES = A["VALS"], A["MICE"], A["DESC"], A["RES"]
SM = A["SESSION_MEASURES"]
GENO = ["WT", "Het", "Hom"]
OM = {m: MICE[m]["omega"] for m in MICE}
BAND = {m: MICE[m]["rot_bin"] for m in MICE}
REF = float(np.median(list(OM.values())))
CRIT = "criterion|sessions_to_criterion"
SPEED_IDS = ("path_m", "speed_cm_s", "speed_sd_cm_s")      # room-frame motion: mostly the floor itself; adjusted anyway


def attr(m, k):
    return MICE[m][k]


def speed_slope(v):
    """Slope of the measure on floor speed shared by the genotypes (OLS value ~ genotype + speed)."""
    ms = [m for m in v if np.isfinite(v[m])]
    if len(ms) < 10:
        return 0.0, np.nan
    df = pd.DataFrame({"v": [v[m] for m in ms], "g": [attr(m, "yh") for m in ms], "om": [OM[m] for m in ms]})
    if np.ptp(df.v) == 0:
        return 0.0, np.nan
    fit = smf.ols("v ~ C(g, Treatment('WT')) + om", df).fit()
    return float(fit.params["om"]), float(fit.pvalues["om"])


def van_elteren(v, a_pred, b_pred):
    """Wilcoxon rank sums of b against a inside each floor-speed band, combined with van Elteren weights."""
    num = var = 0.0
    for band in ("slow", "medium", "fast"):
        xa = np.array([v[m] for m in v if a_pred(m) and BAND[m] == band and np.isfinite(v[m])])
        xb = np.array([v[m] for m in v if b_pred(m) and BAND[m] == band and np.isfinite(v[m])])
        na, nb = xa.size, xb.size
        if na == 0 or nb == 0:
            continue
        n = na + nb
        r = st.rankdata(np.r_[xa, xb])
        w = 1.0 / (n + 1)
        num += w * (r[na:].sum() - nb * (n + 1) / 2.0)
        var += w * w * na * nb * (n + 1) / 12.0
    if var <= 0:
        return np.nan
    return float(2 * st.norm.sf(abs(num / math.sqrt(var))))


def two_adj(adj, raw, a_pred, b_pred):
    """Generous P on speed-adjusted values: Mann-Whitney / Welch / Student (Brunner-Munzel at n >= 10) on the adjusted
    values, and van Elteren on the raw values inside speed bands; smallest P."""
    r = S.two([adj[m] for m in adj if a_pred(m)], [adj[m] for m in adj if b_pred(m)])
    ve = van_elteren(raw, a_pred, b_pred)
    r["p_van Elteren"] = ve
    if np.isfinite(ve) and (not np.isfinite(r["p"]) or ve < r["p"]):
        r["p"], r["test"] = ve, "van Elteren (within speed bands)"
    return r


def contrasts_adj(adj, raw):
    out = []

    def add(cid, grouping, words, res):
        res.update(contrast=cid, grouping=grouping, words=words)
        out.append(res)

    for scope, pred0 in (("all", lambda m: True), ("young", lambda m: attr(m, "age_group") == "young"),
                         ("old", lambda m: attr(m, "age_group") == "old")):
        tag = "" if scope == "all" else "_" + scope
        sw = "" if scope == "all" else " (%s mice)" % scope
        for a, b in (("WT", "Het"), ("WT", "Hom"), ("Het", "Hom")):
            pa = (lambda m, a=a: pred0(m) and attr(m, "yh") == a)
            pb = (lambda m, b=b: pred0(m) and attr(m, "yh") == b)
            if sum(map(pa, adj)) >= 3 and sum(map(pb, adj)) >= 3:
                add("%s_vs_%s%s" % (b, a, tag), "genotype" + tag, "%s against %s%s, at one floor speed" % (b, a, sw),
                    two_adj(adj, raw, pa, pb))
        add("Mut_vs_WT" + tag, "genotype" + tag, "Het+Hom against WT%s, at one floor speed" % sw,
            two_adj(adj, raw, lambda m: pred0(m) and attr(m, "yh") == "WT", lambda m: pred0(m) and attr(m, "yh") != "WT"))
        g3 = [[adj[m] for m in adj if pred0(m) and attr(m, "yh") == g] for g in GENO]
        if min(len(x) for x in g3) >= 3:
            add("GENO3" + tag, "genotype" + tag, "WT / Het / Hom%s, at one floor speed" % sw, S.three(g3))
    for k in GENO:
        pa = (lambda m, k=k: attr(m, "yh") == k and attr(m, "age_group") == "old")
        pb = (lambda m, k=k: attr(m, "yh") == k and attr(m, "age_group") == "young")
        if sum(map(pa, adj)) >= 3 and sum(map(pb, adj)) >= 3:
            r = S.two([adj[m] for m in adj if pa(m)], [adj[m] for m in adj if pb(m)])
            add("young_vs_old_" + k, "age", "young against old, %s only, at one floor speed" % k, r)
    ms = list(adj)
    add("age_corr_all", "age", "against age in weeks, all mice, at one floor speed",
        S.corr([attr(m, "age_wk") for m in ms], [adj[m] for m in ms]))
    for k in GENO:
        mk = [m for m in ms if attr(m, "yh") == k]
        add("age_corr_" + k, "age", "against age in weeks, %s only, at one floor speed" % k,
            S.corr([attr(m, "age_wk") for m in mk], [adj[m] for m in mk]))
    df = pd.DataFrame({"v": [adj[m] for m in ms], "yh": [attr(m, "yh") for m in ms], "ag": [attr(m, "age_group") for m in ms],
                       "age": [attr(m, "age_wk") for m in ms]})
    try:
        fit = smf.ols("v ~ C(yh, Treatment('WT')) * C(ag, Treatment('old'))", df).fit()
        for lab in ("Hom", "Het"):
            term = "C(yh, Treatment('WT'))[T.%s]:C(ag, Treatment('old'))[T.young]" % lab
            add("int_age_group_" + lab, "interaction", "genotype x age group (%s vs WT), at one floor speed" % lab,
                {"p": float(fit.pvalues[term]), "test": "OLS interaction term", "effect": float(fit.params[term]), "n": len(ms)})
        fit = smf.ols("v ~ C(yh, Treatment('WT')) * age", df).fit()
        for lab in ("Hom", "Het"):
            term = "C(yh, Treatment('WT'))[T.%s]:age" % lab
            add("int_age_wk_" + lab, "interaction", "genotype x age in weeks (%s vs WT), at one floor speed" % lab,
                {"p": float(fit.pvalues[term]), "test": "OLS interaction term", "effect": float(fit.params[term]), "n": len(ms)})
        fit = smf.ols("v ~ C(yh, Treatment('WT')) + age", df).fit()
        for lab in ("Het", "Hom"):
            term = "C(yh, Treatment('WT'))[T.%s]" % lab
            add("%s_vs_WT_adj_age" % lab, "adjusted", "%s against WT at one floor speed, adjusted for age" % lab,
                {"p": float(fit.pvalues[term]), "test": "OLS", "effect": float(fit.params[term]), "n": len(ms)})
    except Exception:  # noqa: BLE001
        pass
    for cid, key, a, b, words in (("sex_F_vs_M", "sex", "M", "F", "females against males"),
                                  ("year_2026_vs_2024", "year", 2024, 2026, "2026 mice against 2024 mice")):
        add(cid, "checks", words + ", at one floor speed",
            S.two([adj[m] for m in adj if attr(m, key) == a], [adj[m] for m in adj if attr(m, key) == b]))
    add("injected_vs_not", "checks", "virus-injected before AA against not, at one floor speed",
        S.two([adj[m] for m in adj if not attr(m, "injected_before")], [adj[m] for m in adj if attr(m, "injected_before")]))
    return out


def crit_adj(v):
    """Time to criterion with floor speed: Cox (time ~ genotype + speed) and log-rank stratified by speed band."""
    out = []
    ms = [m for m in v if np.isfinite(v[m])]
    df = pd.DataFrame({"t": [min(v[m], 16.0) for m in ms], "e": [1 if v[m] <= 16 else 0 for m in ms],
                       "yh": [attr(m, "yh") for m in ms], "om": [OM[m] for m in ms], "band": [BAND[m] for m in ms],
                       "age": [attr(m, "age_wk") for m in ms]})
    for a, b in (("WT", "Het"), ("WT", "Hom"), ("Het", "Hom")):
        d = df[df.yh.isin([a, b])].copy()
        d["isb"] = (d.yh == b).astype(float)
        ps = {}
        try:
            fit = PHReg.from_formula("t ~ isb + om", d, status=d["e"].values, ties="efron").fit()
            names = fit.model.exog_names
            ps["Cox with speed"] = float(np.asarray(fit.pvalues)[names.index("isb")])
            hr = float(np.exp(np.asarray(fit.params)[names.index("isb")]))
        except Exception:  # noqa: BLE001
            hr = np.nan
        for name, wt in (("log-rank within speed bands", None), ("Gehan-Breslow within speed bands", "gb")):
            try:
                ps[name] = float(survdiff(d.t.values, d.e.values, d.isb.values, strata=d.band.values, weight_type=wt)[1])
            except Exception:  # noqa: BLE001
                pass
        fin = {k: x for k, x in ps.items() if np.isfinite(x)}
        k = min(fin, key=fin.get) if fin else ""
        res = {"p": fin[k] if fin else np.nan, "test": k, "effect": hr, "hazard_ratio": hr, "n_a": int((d.yh == a).sum()),
               "n_b": int((d.yh == b).sum()), "reached_a": float(d[d.yh == a].e.mean()), "reached_b": float(d[d.yh == b].e.mean()),
               "km_median_a": S.km_median(d[d.yh == a].t, d[d.yh == a].e), "km_median_b": S.km_median(d[d.yh == b].t, d[d.yh == b].e)}
        res.update({"p_" + kk: x for kk, x in ps.items()})
        res.update(contrast="%s_vs_%s" % (b, a), grouping="genotype", words="%s against %s, with floor speed" % (b, a))
        out.append(res)
    return out


# ------------------------------------------------------------------ per-mouse values at one floor speed
VALS_ADJ, SLOPE = {}, {}
for mid, v in VALS.items():
    v = {m: x for m, x in v.items() if np.isfinite(x)}
    if mid == CRIT:
        VALS_ADJ[mid] = dict(v)
        SLOPE[mid] = (np.nan, np.nan)
        continue
    b, pb = speed_slope(v)
    SLOPE[mid] = (b, pb)
    VALS_ADJ[mid] = {m: x - b * (OM[m] - REF) for m, x in v.items()}

rows = []
for mid in VALS_ADJ:
    rr = crit_adj(VALS[mid]) if mid == CRIT else contrasts_adj(VALS_ADJ[mid], VALS[mid])
    for r in rr:
        r.update(id=mid, measure_words=DESC[mid]["words"] + (" (at %.1f deg/s floor speed)" % REF if mid != CRIT else
                                                               " (Cox with floor speed; log-rank within speed bands)"),
                 family=DESC[mid]["family"], summary=DESC[mid]["summary"], speed_slope=SLOPE[mid][0],
                 speed_slope_p=SLOPE[mid][1])
        rows.append(r)
RES_ADJ = pd.DataFrame(rows)
print("adjusted contrast rows", len(RES_ADJ), "P<0.05:", int((RES_ADJ.p < 0.05).sum()), " REF %.2f deg/s" % REF)

# ------------------------------------------------------------------ session values at one floor speed
U = pd.read_csv(os.path.join(TAB, "per_session_values.csv"), dtype={"mouse": str})
U_ADJ = U.copy()
SESS_SLOPE = {}
for mid in SM:
    if mid not in U.columns:
        continue
    for blk, ks in (("train", range(1, 17)), ("s0", [0])):
        d = U[U.session.isin(list(ks))].dropna(subset=[mid, "omega_deg_s"])
        if len(d) < 20 or np.ptp(d[mid]) == 0:
            continue
        f = "v ~ C(yh, Treatment('WT')) + om" + (" + C(session)" if blk == "train" else "")
        try:
            fit = smf.ols(f, d.assign(v=d[mid], om=d.omega_deg_s)).fit()
        except Exception:  # noqa: BLE001
            continue
        b = float(fit.params["om"])
        SESS_SLOPE[(mid, blk)] = (b, float(fit.pvalues["om"]))
        sel = U_ADJ.session.isin(list(ks)) & U_ADJ[mid].notna()
        U_ADJ.loc[sel, mid] = U_ADJ.loc[sel, mid] - b * (U_ADJ.loc[sel, "omega_deg_s"] - REF)

# ------------------------------------------------------------------ mixed models with speed
L = U[(U.session >= 1) & (U.session <= 16)].copy()
L["sc"] = (L.session - 8.5) / 7.5
L["day"] = np.where(L.session <= 8, "d1", "d2")
L["rot"] = L.omega_deg_s
mm = []
for mid in ("entrances_per_rev", "entrances", "shocks", "time_in_zone_pct", "strategy_score", "R", "zone_CW", "brake_share",
            "straightness", "rim_pct"):
    d = L.dropna(subset=[mid]).copy()
    d["y"] = np.log1p(d[mid]) if SM[mid][1] == "count" else d[mid]
    for name, f in (("geno_x_session_speed", "y ~ C(yh, Treatment('WT')) * sc + rot * sc"),
                    ("geno_x_day_speed", "y ~ C(yh, Treatment('WT')) * C(day) + rot * C(day)"),
                    ("geno_speed", "y ~ C(yh, Treatment('WT')) + sc + rot")):
        fit = None
        for meth in ("lbfgs", "bfgs", "powell", "nm"):
            try:
                fit = smf.mixedlm(f, d, groups=d["mouse"]).fit(reml=True, method=meth)
                if np.isfinite(fit.pvalues).all():
                    break
            except Exception:  # noqa: BLE001
                fit = None
        if fit is None:
            mm.append(dict(measure=mid, model=name, formula=f, term="(failed)", p=np.nan))
            continue
        for term, p in fit.pvalues.items():
            if "yh" in term or term.startswith("rot"):
                mm.append(dict(measure=mid, label=SM[mid][0], model=name, formula=f, term=term, coef=float(fit.params[term]),
                               p=float(p), n_mice=d.mouse.nunique(), n_sessions=len(d),
                               transform="log1p" if SM[mid][1] == "count" else "none"))
MM_ADJ = pd.DataFrame(mm)
print("speed mixed-model rows", len(MM_ADJ), "P<0.05:", int((MM_ADJ.p < 0.05).sum()))

# ------------------------------------------------------------------ preferred directions, labels swapped within speed bands
dirs = A["CONS"]["d2_dir"]


def perm_circ_strat(a_ms, b_ms, n=20000, seed=2):
    ms = a_ms + b_ms
    ang = np.radians([dirs[m] for m in ms])
    isb = np.array([0] * len(a_ms) + [1] * len(b_ms))
    bands = np.array([BAND[m] for m in ms])
    rng = np.random.RandomState(seed)

    def dmean(lab):
        x, y = ang[lab == 0], ang[lab == 1]
        mx = np.arctan2(np.sin(x).mean(), np.cos(x).mean())
        my = np.arctan2(np.sin(y).mean(), np.cos(y).mean())
        return abs((mx - my + np.pi) % (2 * np.pi) - np.pi)
    d0 = dmean(isb)
    cnt = 0
    for _ in range(n):
        lab = isb.copy()
        for bnd in np.unique(bands):
            idx = np.where(bands == bnd)[0]
            lab[idx] = rng.permutation(lab[idx])
        cnt += dmean(lab) >= d0 - 1e-12
    return float((cnt + 1) / (n + 1)), float(np.degrees(d0))


circ = []
for a, b in (("WT", "Het"), ("WT", "Hom"), ("Het", "Hom")):
    p, dd = perm_circ_strat([m for m in MICE if attr(m, "yh") == a], [m for m in MICE if attr(m, "yh") == b])
    circ.append(dict(group="%s_vs_%s" % (b, a), p_direction=p, diff_deg=dd, test="permutation within speed bands"))
CIRC_ADJ = pd.DataFrame(circ)
print(CIRC_ADJ.to_string())

# ------------------------------------------------------------------ save
SL = pd.DataFrame([dict(id=k, slope_per_deg_s=b, p=p) for k, (b, p) in SLOPE.items()])
SL.to_csv(os.path.join(TAB, "speed_slopes_per_mouse_measure.csv"), index=False)
cols = ["id", "measure_words", "family", "summary", "contrast", "grouping", "words", "p", "test", "effect", "n_a", "n_b",
        "mean_a", "mean_b", "median_a", "median_b", "hedges_g", "rho", "n", "speed_slope", "speed_slope_p",
        "p_Mann-Whitney", "p_Welch t", "p_Student t", "p_Brunner-Munzel", "p_van Elteren", "p_ANOVA", "p_Kruskal-Wallis",
        "p_ordered trend", "p_Spearman", "p_Pearson", "p_Kendall", "reached_a", "reached_b", "km_median_a", "km_median_b",
        "hazard_ratio"]
RES_ADJ[[c for c in cols if c in RES_ADJ.columns]].to_csv(os.path.join(TAB, "all_results_speed_adjusted.csv.gz"), index=False,
                                                          compression="gzip")
MM_ADJ.to_csv(os.path.join(TAB, "mixed_models_with_speed.csv"), index=False)
U_ADJ.to_csv(os.path.join(TAB, "per_session_values_speed_adjusted.csv"), index=False)
pickle.dump(dict(REF=REF, VALS_ADJ=VALS_ADJ, RES_ADJ=RES_ADJ, SLOPE=SLOPE, SESS_SLOPE=SESS_SLOPE, MM_ADJ=MM_ADJ,
                 CIRC_ADJ=CIRC_ADJ), open(os.path.join(HERE, "speed.pkl"), "wb"))
print("saved speed.pkl")
