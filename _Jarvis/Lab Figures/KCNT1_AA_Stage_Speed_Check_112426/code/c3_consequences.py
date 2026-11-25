"""Floor (stage) speed check, step 3: what the floor reading's weak spots do to the menu's headlines -> floor_conseq.pkl.

For each alternative reading of the floor speed (re-centered, half-hour, both, other settings, the peak of all 1-s
speeds, bootstrap redraws) every per-mouse headline is re-run exactly as a4_speed does it: each mouse moved to one
speed along the shared slope (re-fitted), generous tests on the moved values plus van Elteren inside the speed bands
(re-cut at 4.0 / 4.8 deg/s on the new readings). With the 'full' alternatives the measures that use the speed
themselves (entrances per turn, walking on the floor) are rebuilt from the tracks too.
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

import floorlib as FL
import stats_lib as S

warnings.filterwarnings("ignore")
T0 = time.time()
HERE = FL.HERE
A = pickle.load(open(os.path.join(HERE, "analysis.pkl"), "rb"))
B = pickle.load(open(os.path.join(HERE, "speed.pkl"), "rb"))
O = pickle.load(open(os.path.join(HERE, "floor_check.pkl"), "rb"))
MICE, VALS, CONS = A["MICE"], A["VALS"], A["CONS"]
MLIST = sorted(MICE, key=int)
CRIT = "criterion|sessions_to_criterion"
SMx = pd.read_csv(os.path.join(HERE, "session_metrics.csv"), dtype={"mouse": str})
SMx["key"] = ["%s_s%d%s" % (m, s, "" if u else "_x") for m, s, u in zip(SMx.mouse, SMx.session, SMx.use)]
U = SMx[SMx.use].copy()
SESS = O["SESS"].set_index("key")


def log(*a):
    print("[%5.0fs]" % (time.time() - T0), *a, flush=True)


def geno(m):
    return MICE[m]["yh"]


HEAD = [  # (story, measure id or MM / CIRC, contrast, label)
    ("1", "shocks|d1", "Hom_vs_WT", "Hom fewer day-1 shocks than WT"),
    ("1", "shocks|d1", "Hom_vs_Het", "Hom fewer day-1 shocks than Het"),
    ("1", "time_in_zone_pct|d1", "Hom_vs_WT", "Hom less day-1 time in the zone than WT"),
    ("1", CRIT, "Hom_vs_WT", "Hom reach criterion sooner than WT"),
    ("1", CRIT, "Hom_vs_Het", "Hom reach criterion sooner than Het"),
    ("2", "entrances|d2_minus_d1", "Het_vs_WT", "Het improve less (entrances)"),
    ("2", "entrances|d2_minus_d1", "Hom_vs_WT", "Hom improve less (entrances)"),
    ("2", "shocks|d2_minus_d1", "Het_vs_WT", "Het improve less (shocks)"),
    ("2", "shocks|d2_minus_d1", "Hom_vs_WT", "Hom improve less (shocks)"),
    ("2", "MM", "[T.Het]:sc", "Het curves flatter (mixed model)"),
    ("2", "MM", "[T.Hom]:sc", "Hom curves flatter (mixed model)"),
    ("3", "shocks|d2", "young_vs_old_Hom", "Old Hom more day-2 shocks than young Hom"),
    ("3", "shocks|d2", "int_age_group_Hom", "Hom x age, day-2 shocks"),
    ("3", "latency_first_entrance_s|d2", "young_vs_old_Hom", "Old Hom enter sooner on day 2"),
    ("4", "cells_visited|s0", "Hom_vs_WT", "Hom cover less of the floor (habituation)"),
    ("4", "R|s0", "Hom_vs_WT", "Hom keep to one side (habituation)"),
    ("4", "walk_m|s0", "Hom_vs_WT", "Hom walk farther (habituation)"),
    ("5-6", "CIRC", "Het_vs_WT", "Het wait nearer the opposite (direction)"),
    ("5-6", "strategy_score|d2", "Het_vs_WT", "Het wait opposite (strategy score)"),
    ("5-6", "zone_CW|d2", "Het_vs_WT", "Het spend less time pre-shock"),
    ("5-6", "brake_share|d2", "Het_vs_WT", "Het turn back less at the edge"),
    ("5-6", "consistency|pref_sd_d1", "Het_vs_WT", "Het safe spot wanders, day 1"),
    ("5-6", "R|d2", "Het_vs_WT", "Het more scattered (concentration)"),
    ("7", "rim_pct|d2", "Hom_vs_WT", "Hom less at the rim, day 2"),
    ("7", "straightness|d2", "Hom_vs_WT", "Hom walk less straight, day 2"),
    ("7", "walk_speed_cm_s|d1", "Hom_vs_WT", "Hom walk faster, day 1"),
    ("7", "immobile_pct|d1", "Hom_vs_WT", "Hom sit still less, day 1"),
    ("7", "walk_speed_cm_s|d1", "Het_vs_WT", "Het walk slower, day 1"),
]
WALK = ("walk_m", "walk_speed_cm_s", "immobile_pct", "straightness")


# ------------------------------------------------------------------ tests, as a4_speed
def band_of(w):
    return "fast" if w >= 4.8 else ("medium" if w >= 4.0 else "slow")


def van_elteren(v, a_pred, b_pred, BAND):
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


def adjust(v, OM, REF):
    ms = [m for m in v if np.isfinite(v[m])]
    df = pd.DataFrame({"v": [v[m] for m in ms], "g": [geno(m) for m in ms], "om": [OM[m] for m in ms]})
    if np.ptp(df.v) == 0:
        return dict(v), 0.0
    b = float(smf.ols("v ~ C(g, Treatment('WT')) + om", df).fit().params["om"])
    return {m: v[m] - b * (OM[m] - REF) for m in ms}, b


def crit_test(v, con, OM, BAND):
    a, b = con.split("_vs_")[1], con.split("_vs_")[0]
    ms = [m for m in v if np.isfinite(v[m]) and geno(m) in (a, b)]
    t = np.array([min(v[m], 16.0) for m in ms])
    e = np.array([1 if v[m] <= 16 else 0 for m in ms])
    isb = np.array([1.0 if geno(m) == b else 0.0 for m in ms])
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


def circ_test(con, BAND, n=4000, seed=2):
    a, b = con.split("_vs_")[1], con.split("_vs_")[0]
    dirs = CONS["d2_dir"]
    ms = [m for m in MLIST if geno(m) == a] + [m for m in MLIST if geno(m) == b]
    ang = np.radians([dirs[m] for m in ms])
    isb = np.array([0 if geno(m) == a else 1 for m in ms])
    bands = np.array([BAND[m] for m in ms])
    rng = np.random.RandomState(seed)

    def dmean(lab):
        x, y = ang[lab == 0], ang[lab == 1]
        mx = np.arctan2(np.sin(x).mean(), np.cos(x).mean())
        my = np.arctan2(np.sin(y).mean(), np.cos(y).mean())
        return abs((mx - my + np.pi) % (2 * np.pi) - np.pi)
    d0, cnt = dmean(isb), 0
    for _ in range(n):
        lab = isb.copy()
        for bnd in np.unique(bands):
            idx = np.where(bands == bnd)[0]
            lab[idx] = rng.permutation(lab[idx])
        cnt += dmean(lab) >= d0 - 1e-12
    return float((cnt + 1) / (n + 1))


def mm_test(sess_om, epr):
    """geno x session + speed x session on entrances per turn, s1-s16, random intercept per mouse."""
    d = U[(U.session >= 1) & (U.session <= 16)][["key", "mouse", "session"]].copy()
    d["y"] = d.key.map(epr)          # as a4_speed: entrances per turn is not a count, so no log
    d["rot"] = d.key.map(sess_om)
    d["yh"] = d.mouse.map(geno)
    d["sc"] = (d.session - 8.5) / 7.5
    d = d.dropna()
    fit = None
    for meth in ("lbfgs", "bfgs", "powell", "nm"):
        try:
            fit = smf.mixedlm("y ~ C(yh, Treatment('WT')) * sc + rot * sc", d, groups=d["mouse"]).fit(reml=True, method=meth)
            if np.isfinite(fit.pvalues).all():
                break
        except Exception:  # noqa: BLE001
            fit = None
    out = {}
    if fit is None:
        return out
    for t, p in fit.pvalues.items():
        for lab in ("[T.Het]:sc", "[T.Hom]:sc"):
            if lab in t:
                out[lab] = float(p)
    return out


# ------------------------------------------------------------------ rebuilding the speed-dependent measures
def walk(key, omega, cx=0.0, cy=0.0):
    t, X, Y, _lost = FL.track(key)
    dt = float(np.median(np.diff(t)))
    w = max(int(round(1.0 / dt)), 1)
    X1, Y1, t1 = X[::w] - cx, Y[::w] - cy, t[::w]
    ang = -np.radians(omega) * t1
    Xa = X1 * np.cos(ang) - Y1 * np.sin(ang)
    Ya = X1 * np.sin(ang) + Y1 * np.cos(ang)
    stepa = np.hypot(np.diff(Xa), np.diff(Ya))
    cs = np.r_[0, np.cumsum(stepa)]
    net5 = np.hypot(Xa[5:] - Xa[:-5], Ya[5:] - Ya[:-5])
    pl5 = cs[5:] - cs[:-5]
    mv = pl5 > 5.0
    return dict(walk_m=float(stepa.sum() / 100), walk_speed_cm_s=float(np.median(stepa)),
                immobile_pct=100 * float((stepa < 2.0).mean()), straightness=float(np.median(net5[mv] / pl5[mv])) if mv.any() else np.nan)


def summaries(sess_vals):
    """sess_vals: {key: value} for used sessions -> per-mouse s0, d1, d2."""
    s = pd.DataFrame({"key": list(sess_vals), "v": list(sess_vals.values())}).merge(U[["key", "mouse", "session"]], on="key")
    p = s.pivot_table(index="mouse", columns="session", values="v")
    return {"s0": p[0].to_dict(), "d1": p.loc[:, 1:8].mean(axis=1).to_dict(), "d2": p.loc[:, 9:16].mean(axis=1).to_dict()}


def rebuild(sess_om, centered):
    vals = {}
    walks = {k: walk(k, sess_om[k], *(O["CENTER"][SESS.loc[k, "date"]] if centered else (0.0, 0.0))) for k in U.key}
    for meas in WALK:
        sm = summaries({k: walks[k][meas] for k in walks})
        for sk, d in sm.items():
            vals["%s|%s" % (meas, sk)] = {m: float(x) for m, x in d.items() if np.isfinite(x)}
    epr = {k: float(r.entrances * 360.0 / (sess_om[k] * r.duration_s)) for k, r in U.set_index("key").iterrows()}
    return vals, epr, walks


# ------------------------------------------------------------------ one alternative reading -> every headline
def run(sess_om, full=False, centered=False, mm=True, circ=True):
    OM = U.assign(om=U.key.map(sess_om)).groupby("mouse").om.median().to_dict()
    BAND = {m: band_of(w) for m, w in OM.items()}
    REF = float(np.median(list(OM.values())))
    V = dict(VALS)
    epr = {k: float(r.entrances * 360.0 / (sess_om[k] * r.duration_s)) for k, r in U.set_index("key").iterrows()}
    if full:
        rv, epr, _w = rebuild(sess_om, centered)
        V.update(rv)
    rows = []
    mmres = mm_test(sess_om, epr) if mm else {}
    for story, mid, con, lab in HEAD:
        if mid == "MM":
            p = mmres.get(con, np.nan)
        elif mid == "CIRC":
            p = circ_test(con, BAND) if circ else np.nan
        elif mid == CRIT:
            p = crit_test(V[mid], con, OM, BAND)
        else:
            v = {m: x for m, x in V[mid].items() if np.isfinite(x)}
            adj, _b = adjust(v, OM, REF)
            if con == "young_vs_old_Hom":
                p = S.two([adj[m] for m in adj if geno(m) == "Hom" and MICE[m]["age_group"] == "old"],
                          [adj[m] for m in adj if geno(m) == "Hom" and MICE[m]["age_group"] == "young"])["p"]
            elif con == "int_age_group_Hom":
                df = pd.DataFrame({"v": list(adj.values()), "yh": [geno(m) for m in adj], "ag": [MICE[m]["age_group"] for m in adj]})
                fit = smf.ols("v ~ C(yh, Treatment('WT')) * C(ag, Treatment('old'))", df).fit()
                p = float(fit.pvalues["C(yh, Treatment('WT'))[T.Hom]:C(ag, Treatment('old'))[T.young]"])
            else:
                b, a = con.split("_vs_")
                r = S.two([adj[m] for m in adj if geno(m) == a], [adj[m] for m in adj if geno(m) == b])
                ve = van_elteren(v, lambda m, a=a: geno(m) == a, lambda m, b=b: geno(m) == b, BAND)
                p = min(x for x in (r["p"], ve) if np.isfinite(x)) if (np.isfinite(r["p"]) or np.isfinite(ve)) else np.nan
        rows.append(dict(story=story, id=mid, contrast=con, label=lab, p=p))
    return pd.DataFrame(rows), OM, BAND, REF


ALTS = {}
base = SESS.loc[U.key]
ALT_SPEC = [
    ("menu", "The menu (day median)", base.day0, False, False),
    ("menu_full", "The menu, measures rebuilt (check)", base.day0, True, False),
    ("recentered", "About the floor's true center", base.day1, True, True),
    ("halfhour", "Half-hour reading per session", base.local0, True, False),
    ("refined", "Both: true center + half-hour", base.local1, True, True),
]
for name in ("lenient", "sd015", "win3", "phase"):
    dv = O["DAYV"][name]
    ALT_SPEC.append((name, O["VARIANTS"][name][0], base.date.map(dv).fillna(base.day0), True, False))
ALT_SPEC.append(("peak", "Peak of all 1-s speeds (true center)", base.date.map(pd.Series(O["MODE1"])), True, True))
for name, lab, ser, full, cen in ALT_SPEC:
    so = dict(zip(base.index, ser.values))
    res, OM, BAND, REF = run(so, full=full, centered=cen)
    ALTS[name] = dict(label=lab, res=res, OM=OM, BAND=BAND, REF=REF, sess_om=so)
    log(name, "REF %.2f" % REF, "P<0.05: %d" % (res.p < 0.05).sum())

# check: the menu alternative must reproduce the menu's one-speed P values
menu_p = []
for story, mid, con, lab in HEAD:
    if mid == "MM":
        s = B["MM_ADJ"][(B["MM_ADJ"].measure == "entrances_per_rev") & (B["MM_ADJ"].model == "geno_x_session_speed") &
                        B["MM_ADJ"].term.str.contains(con, regex=False)]
        menu_p.append(float(s.p.iloc[0]))
    elif mid == "CIRC":
        menu_p.append(float(B["CIRC_ADJ"][B["CIRC_ADJ"].group == con].p_direction.iloc[0]))
    else:
        s = B["RES_ADJ"][(B["RES_ADJ"].id == mid) & (B["RES_ADJ"].contrast == con)]
        menu_p.append(float(s.p.iloc[0]))
chk = pd.DataFrame(dict(label=[h[3] for h in HEAD], menu=menu_p, rerun=ALTS["menu"]["res"].p.values,
                        rerun_full=ALTS["menu_full"]["res"].p.values))
log("menu reproduction: max |log10 ratio| %.3f (full %.3f)" % (
    np.nanmax(np.abs(np.log10(chk.rerun / chk.menu))), np.nanmax(np.abs(np.log10(chk.rerun_full / chk.menu)))))
print(chk.to_string(float_format=lambda x: "%.4g" % x))

# bootstrap redraws of every day's reading (mice resampled within the day), the menu's way otherwise
W0 = O["W0"]
rng = np.random.RandomState(5)
BY = {d: [g.speed.values for _m, g in W0[W0.date == d].groupby("mouse")] for d in O["DATES"]}
BOOTP = []
for rep in range(200):
    dd = {d: float(np.median(np.concatenate([by[i] for i in rng.randint(0, len(by), len(by))]))) for d, by in BY.items()}
    so = dict(zip(base.index, base.date.map(dd).values))
    res, OM, BAND, REF = run(so, full=False, mm=False, circ=False)
    BOOTP.append(res.p.values)
BOOTP = np.array(BOOTP)
log("bootstrap done")

pickle.dump(dict(HEAD=HEAD, ALTS=ALTS, CHECK=chk, BOOTP=BOOTP), open(os.path.join(HERE, "floor_conseq.pkl"), "wb"))
log("saved floor_conseq.pkl")
