"""Floor (stage) speed check, step 4: the outlier breakdown and the menu's check table (page 11) three ways -> floor_outliers.pkl

Every P here uses the menu's own tests: raw = the generous two-group tests on the raw values (time-to-criterion tests
for the criterion); at one floor speed = values moved to one speed along the slope shared by the genotypes (re-fitted on
the mice kept), the same tests on the moved values plus van Elteren inside the speed bands, smallest P (Cox with speed
and band-stratified log-rank for the criterion). So 'all mice' matches the headline P values of the menu.
Outliers: more than 3.5 robust s.d. (1.4826 x MAD) from their genotype's median on that measure (raw values for raw,
moved values for one speed), as in the menu.
"""
import math
import os
import pickle
import time
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as st
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.duration.survfunc import survdiff

import stats_lib as S

warnings.filterwarnings("ignore")
T0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
A = pickle.load(open(os.path.join(HERE, "analysis.pkl"), "rb"))
CQ = pickle.load(open(os.path.join(HERE, "floor_conseq.pkl"), "rb"))
O = pickle.load(open(os.path.join(HERE, "floor_check.pkl"), "rb"))
MICE, VR = A["MICE"], A["VALS"]
MLIST = sorted(MICE, key=int)
CRIT = "criterion|sessions_to_criterion"
READINGS = {"menu": ({m: MICE[m]["omega"] for m in MLIST}, {m: MICE[m]["rot_bin"] for m in MLIST}),
            "refined": (CQ["ALTS"]["refined"]["OM"], CQ["ALTS"]["refined"]["BAND"])}


def log(*a):
    print("[%5.0fs]" % (time.time() - T0), *a, flush=True)


def geno(m):
    return MICE[m]["yh"]


def van_elteren(v, a, b, BAND):
    num = var = 0.0
    for band in ("slow", "medium", "fast"):
        xa = np.array([v[m] for m in v if geno(m) == a and BAND[m] == band])
        xb = np.array([v[m] for m in v if geno(m) == b and BAND[m] == band])
        na, nb = xa.size, xb.size
        if na == 0 or nb == 0:
            continue
        n = na + nb
        r = st.rankdata(np.r_[xa, xb])
        w = 1.0 / (n + 1)
        num += w * (r[na:].sum() - nb * (n + 1) / 2.0)
        var += w * w * na * nb * (n + 1) / 12.0
    return float(2 * st.norm.sf(abs(num / math.sqrt(var)))) if var > 0 else np.nan


def adjust(v, OM):
    REF = float(np.median([OM[m] for m in MLIST]))
    ms = list(v)
    df = pd.DataFrame({"v": [v[m] for m in ms], "g": [geno(m) for m in ms], "om": [OM[m] for m in ms]})
    if np.ptp(df.v) == 0 or df.g.nunique() < 2:
        return dict(v)
    b = float(smf.ols("v ~ C(g) + om", df).fit().params["om"])
    return {m: v[m] - b * (OM[m] - REF) for m in ms}


def moved_all(mid, reading):
    """Values at one speed with the slope from all 56 mice (what the menu shows and what the outlier rule sees)."""
    v = {m: x for m, x in VR[mid].items() if np.isfinite(x)}
    return adjust(v, READINGS[reading][0])


def p_full(mid, con, dset=frozenset(), raw=False, reading="menu"):
    OM, BAND = READINGS[reading]
    v = {m: x for m, x in VR[mid].items() if m not in dset and np.isfinite(x)}
    if mid == CRIT:
        b, a = con.split("_vs_")
        ms = [m for m in v if geno(m) in (a, b)]
        t = np.array([min(v[m], 16.0) for m in ms])
        e = np.array([1 if v[m] <= 16 else 0 for m in ms])
        isb = np.array([1.0 if geno(m) == b else 0.0 for m in ms])
        if raw:
            return S.surv_two(t[isb == 0], e[isb == 0], t[isb == 1], e[isb == 1])["p"]
        ps = []
        try:
            fit = PHReg(t, np.c_[isb, [OM[m] for m in ms]], status=e, ties="efron").fit()
            ps.append(float(np.asarray(fit.pvalues)[0]))
        except Exception:  # noqa: BLE001
            pass
        for wt in (None, "gb"):
            try:
                ps.append(float(survdiff(t, e, isb, strata=np.array([BAND[m] for m in ms]), weight_type=wt)[1]))
            except Exception:  # noqa: BLE001
                pass
        ps = [x for x in ps if np.isfinite(x)]
        return min(ps) if ps else np.nan
    adj = v if raw else adjust(v, OM)
    if con == "young_vs_old_Hom":
        return S.two([adj[m] for m in adj if geno(m) == "Hom" and MICE[m]["age_group"] == "old"],
                     [adj[m] for m in adj if geno(m) == "Hom" and MICE[m]["age_group"] == "young"])["p"]
    if con == "int_age_group_Hom":
        df = pd.DataFrame({"v": list(adj.values()), "yh": [geno(m) for m in adj], "ag": [MICE[m]["age_group"] for m in adj]})
        if df[df.yh == "Hom"].ag.nunique() < 2 or df[df.yh == "WT"].ag.nunique() < 2:
            return np.nan
        fit = smf.ols("v ~ C(yh, Treatment('WT')) * C(ag, Treatment('old'))", df).fit()
        return float(fit.pvalues.get("C(yh, Treatment('WT'))[T.Hom]:C(ag, Treatment('old'))[T.young]", np.nan))
    b, a = con.split("_vs_")
    r = S.two([adj[m] for m in adj if geno(m) == a], [adj[m] for m in adj if geno(m) == b])
    if raw:
        return r["p"]
    ve = van_elteren(v, a, b, BAND)
    ps = [x for x in (r["p"], ve) if np.isfinite(x)]
    return min(ps) if ps else np.nan


def robust_z(v, groups):
    z = {}
    for g in groups:
        ms = [m for m in v if geno(m) == g]
        x = np.array([v[m] for m in ms])
        if x.size < 4:
            continue
        med = np.median(x)
        mad = 1.4826 * np.median(np.abs(x - med))
        for m, xx in zip(ms, x):
            z[m] = (xx - med) / mad if mad > 0 else 0.0
    return z


def outliers(mid, raw, reading="menu"):
    if mid == CRIT:
        return {}
    v = {m: x for m, x in VR[mid].items() if np.isfinite(x)} if raw else moved_all(mid, reading)
    return {m: z for m, z in robust_z(v, ("WT", "Het", "Hom")).items() if abs(z) > 3.5}


# ------------------------------------------------------------------ the page-11 check table, three ways
DROPS = [("all mice", lambda: set()), ("no outliers*", None), ("no 461/462/457", lambda: {"461", "462", "457"}),
         ("no injected ≤ 7 d", lambda: {m for m in MLIST if MICE[m]["injected_7d"]}),
         ("no injected", lambda: {m for m in MLIST if MICE[m]["injected_before"]}),
         ("2024 only", lambda: {m for m in MLIST if MICE[m]["year"] != 2024}),
         ("2026 only", lambda: {m for m in MLIST if MICE[m]["year"] != 2026})]
CHECK_HEADS = [("shocks|d1", "Hom_vs_WT", "Hom fewer day-1 shocks than WT (story 1)"),
               ("entrances|d2_minus_d1", "Het_vs_WT", "Het improve less (story 2)"),
               ("entrances|d2_minus_d1", "Hom_vs_WT", "Hom improve less (story 2)"),
               ("shocks|d2", "young_vs_old_Hom", "Old vs young Hom, day-2 shocks (story 3)"),
               ("shocks|d2", "int_age_group_Hom", "Hom x age, day-2 shocks (story 3)"),
               ("strategy_score|d2", "Het_vs_WT", "Het wait opposite (story 6)"),
               ("brake_share|d2", "Het_vs_WT", "Het turn back less (story 6)"),
               ("consistency|pref_sd_d1", "Het_vs_WT", "Het spot wanders, day 1 (story 6)"),
               (CRIT, "Hom_vs_WT", "Hom reach criterion sooner (story 1)")]
TABLES = {}
for name, raw, reading in (("one speed", False, "menu"), ("raw", True, "menu"), ("one speed, refined reading", False, "refined")):
    rows = []
    for mid, con, lab in CHECK_HEADS:
        row = dict(headline=lab, id=mid, contrast=con)
        for dname, fn in DROPS:
            if fn is None:
                row[dname] = np.nan if mid == CRIT else p_full(mid, con, frozenset(outliers(mid, raw, reading)), raw, reading)
                row["outliers_dropped"] = "" if mid == CRIT else ", ".join(sorted(outliers(mid, raw, reading), key=int))
            else:
                row[dname] = p_full(mid, con, frozenset(fn()), raw, reading)
        rows.append(row)
    TABLES[name] = pd.DataFrame(rows)
log("tables done")

# ------------------------------------------------------------------ every per-mouse headline: outliers and drop-one-mouse P
HEAD = [h for h in CQ["HEAD"] if h[1] not in ("MM", "CIRC")]
OUTL, JACK, SUMM = [], {}, []
for story, mid, con, lab in HEAD:
    if "young_vs_old" in con:
        gs = ("Hom",)
    elif con.startswith("int_"):
        gs = ("WT", "Het", "Hom")
    else:
        gs = tuple(con.split("_vs_"))
    for raw in (False, True):
        rd = "raw" if raw else "one speed"
        p_all = p_full(mid, con, frozenset(), raw)
        out = outliers(mid, raw)
        rel = {m: z for m, z in out.items() if geno(m) in gs}
        for m, z in rel.items():
            v = VR[mid][m] if raw else moved_all(mid, "menu")[m]
            OUTL.append(dict(story=story, label=lab, id=mid, contrast=con, reading=rd, mouse=m, geno=geno(m),
                             age=MICE[m]["age_group"], year=MICE[m]["year"], value=float(v), robust_z=float(z),
                             p_all=p_all, p_without=p_full(mid, con, frozenset({m}), raw)))
        p_no = p_full(mid, con, frozenset(out), raw) if out else p_all
        involved = [m for m in MLIST if m in VR[mid] and np.isfinite(VR[mid][m]) and geno(m) in gs]
        drop = {m: p_full(mid, con, frozenset({m}), raw) for m in involved}
        JACK[(lab, rd)] = dict(p=p_all, drop=drop)
        ds = pd.Series(drop).dropna()
        flip = ds[(ds >= 0.05)] if p_all < 0.05 else ds[(ds < 0.05)]
        SUMM.append(dict(story=story, label=lab, reading=rd, p_all=p_all, p_no_outliers=p_no,
                         outliers=", ".join("%s (%s, z %+.1f)" % (m, geno(m), z) for m, z in sorted(rel.items(), key=lambda kv: -abs(kv[1]))),
                         outlier_mice=",".join(sorted(rel, key=int)), drop_min=float(ds.min()), drop_max=float(ds.max()),
                         most=ds.idxmax() if p_all < 0.05 else ds.idxmin(), n_flip=len(flip), flips=", ".join(flip.index)))
    log(lab)
OUTL, SUMM = pd.DataFrame(OUTL), pd.DataFrame(SUMM)

# mice that keep turning up
cnt = {}
for r in SUMM.itertuples():
    for tok in [t for t in r.outlier_mice.split(",") if t]:
        cnt.setdefault(tok, {"outlier": 0, "most influential": 0})["outlier"] += 1
    if r.n_flip:
        cnt.setdefault(r.most, {"outlier": 0, "most influential": 0})["most influential"] += 1
FREQ = pd.DataFrame([dict(mouse=m, geno=geno(m), age=MICE[m]["age_group"], year=MICE[m]["year"], **c) for m, c in cnt.items()])
FREQ["total"] = FREQ.outlier + FREQ["most influential"]
FREQ = FREQ.sort_values(["total", "outlier"], ascending=False)

# mice whose floor reading was shaky: a session > 0.5 deg/s off its day's reading (half-hour reading, true center),
# a motor change logged for > 20 s, or a day with fewer than 100 ride readings
SE = O["SESS"]
SE = SE[SE.use]
shaky = {}
for m, g in SE.groupby("mouse"):
    why = []
    if ((g.local1 - g.day1).abs() > 0.5).sum() >= 2:
        why.append("floor changed within the day")
    if g.date.map(lambda d: O["W0"][O["W0"].date == d].shape[0]).min() < 100:
        why.append("few ride readings that day")
    for k, mm in O["MOT"].items():
        if mm["mouse"] == m and sum(s for v, s in mm["secs"].items() if v != 4) > 20:
            why.append("motor change in s%d" % mm["session"])
    if why:
        shaky[m] = "; ".join(why)
SHAKY = pd.DataFrame([dict(mouse=m, geno=geno(m), age=MICE[m]["age_group"], year=MICE[m]["year"], why=w) for m, w in shaky.items()])
SHAKY_P = []
for story, mid, con, lab in HEAD:
    SHAKY_P.append(dict(label=lab, p_all=p_full(mid, con), p_without=p_full(mid, con, frozenset(shaky))))
SHAKY_P = pd.DataFrame(SHAKY_P)
log("shaky-floor mice", len(shaky), sorted(shaky, key=int))

pickle.dump(dict(TABLES=TABLES, DROPS=[d for d, _f in DROPS], CHECK_HEADS=CHECK_HEADS, OUTL=OUTL, JACK=JACK, SUMM=SUMM,
                 FREQ=FREQ, SHAKY=SHAKY, SHAKY_P=SHAKY_P), open(os.path.join(HERE, "floor_outliers.pkl"), "wb"))
log("saved floor_outliers.pkl")
