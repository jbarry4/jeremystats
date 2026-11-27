"""Numbers for two supplements (2026-11-24): the floor-speed confound battery and what can be rescued -> cr.pkl

Floor speed is the refined reading of the stage speed check (each session's half-hour reading about that day's true
center; a mouse's speed = median over its sessions). Per-turn measures divide by the floor turns in the session
(speed x duration / 360).
"""
import os
import pickle
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as st

import stats_lib as S

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
A = pickle.load(open(os.path.join(HERE, "analysis.pkl"), "rb"))
CQ = pickle.load(open(os.path.join(HERE, "floor_conseq.pkl"), "rb"))
O = pickle.load(open(os.path.join(HERE, "floor_check.pkl"), "rb"))
RP = pickle.load(open(os.path.join(HERE, "replay.pkl"), "rb"))
MICE = A["MICE"]
ML = sorted(MICE, key=int)
OMR = CQ["ALTS"]["refined"]["OM"]
OMM = {m: MICE[m]["omega"] for m in ML}
G = {m: MICE[m]["yh"] for m in ML}
AG = {m: MICE[m]["age_group"] for m in ML}
GRP = {m: "%s %s" % (G[m], AG[m]) for m in ML}
F24 = {m for m in ML if MICE[m]["year"] == 2024}          # the 2024 floor: 4.8-5.6 deg/s
rng = np.random.RandomState(7)

# ------------------------------------------------------------------ session table
SM = pd.read_csv(os.path.join(HERE, "session_metrics.csv"), dtype={"mouse": str})
SM = SM[SM.use].copy()
SM["key"] = ["%s_s%d" % (m, s) for m, s in zip(SM.mouse, SM.session)]
SE = O["SESS"].set_index("key")
SM["om"] = SM.key.map(SE.local1)
SM["om_menu"] = SM.key.map(SE.day0)
SM["start_h"] = SM.key.map(SE.start_h)
SM["date"] = SM.key.map(SE.date)
SM["turns"] = SM.om * SM.duration_s / 360.0
SM["epr"] = SM.entrances / SM.turns
SM["spr"] = SM.shocks / SM.turns
SM["lat_turns"] = SM.latency_first_entrance_s * SM.om / 360.0
SM["maxav_turns"] = SM.max_avoid_s * SM.om / 360.0
SM["geno"], SM["age"] = SM.mouse.map(G), SM.mouse.map(AG)
TR = SM[SM.session >= 1].copy()

MEAS = {  # id: (label, unit, raw or per turn)
    "entrances": ("Entrances", "per session", "raw"), "shocks": ("Shocks", "per session", "raw"),
    "time_in_zone_pct": ("Time in the zone", "%", "raw"), "latency_first_entrance_s": ("Time to first entrance", "s", "raw"),
    "max_avoid_s": ("Longest avoidance", "s", "raw"), "path_m": ("Path in the room", "m", "raw"),
    "epr": ("Entrances per turn", "per turn", "per turn"), "spr": ("Shocks per turn", "per turn", "per turn"),
    "lat_turns": ("Turns to first entrance", "turns", "per turn"), "maxav_turns": ("Longest avoidance in turns", "turns", "per turn"),
}
PM = {}
for c in MEAS:
    d1 = TR[TR.session <= 8].groupby("mouse")[c].mean()
    d2 = TR[TR.session >= 9].groupby("mouse")[c].mean()
    PM[c + "|d1"], PM[c + "|d2"] = d1.to_dict(), d2.to_dict()
    PM[c + "|imp"] = (d2 - d1).to_dict()
PM["criterion"] = A["VALS"]["criterion|sessions_to_criterion"]


def two(a_pred, b_pred, mid):
    v = PM[mid]
    return S.two([v[m] for m in v if a_pred(m) and np.isfinite(v[m])], [v[m] for m in v if b_pred(m) and np.isfinite(v[m])])


def is_(g=None, a=None, f24=None):
    return lambda m: (g is None or G[m] == g) and (a is None or AG[m] == a) and (f24 is None or ((m in F24) == f24))


OUT = dict(MEAS=MEAS, PM=PM, OMR=OMR, OMM=OMM, F24=F24, TR=TR)

# ------------------------------------------------------------------ K2 who ran at what speed
grp_order = ["WT young", "WT old", "Het young", "Het old", "Hom young", "Hom old"]
OUT["groups"] = {g: sorted(OMR[m] for m in ML if GRP[m] == g) for g in grp_order}
OUT["kw_speed"] = float(st.kruskal(*[OUT["groups"][g] for g in grp_order]).pvalue)
OUT["yHom_yWT_speed"] = S.two(OUT["groups"]["WT young"], OUT["groups"]["Hom young"])
OUT["oHom_oWT_speed"] = S.two(OUT["groups"]["WT old"], OUT["groups"]["Hom old"])
OUT["oHom_oWT24_speed"] = S.two([OMR[m] for m in ML if GRP[m] == "WT old" and m in F24], OUT["groups"]["Hom old"])
# the confound web: what travels with floor speed
fac = pd.DataFrame({"floor speed": [OMR[m] for m in ML], "run in 2026": [int(MICE[m]["year"] == 2026) for m in ML],
                    "injected before AA": [int(MICE[m]["injected_before"]) for m in ML], "age (weeks)": [MICE[m]["age_wk"] for m in ML],
                    "Hom": [int(G[m] == "Hom") for m in ML], "young Hom": [int(GRP[m] == "Hom young") for m in ML]}, index=ML)
OUT["web"] = fac.corr(method="spearman")
OUT["web_p"] = pd.DataFrame([[st.spearmanr(fac[a], fac[b])[1] for b in fac] for a in fac], index=fac.columns, columns=fac.columns)

# ------------------------------------------------------------------ K4 same mouse, different floor speed
FE = {}
for c in ("entrances", "shocks", "time_in_zone_pct", "path_m", "epr", "spr", "lat_turns", "maxav_turns"):
    d = TR.dropna(subset=[c, "om"])
    fit = smf.ols("%s ~ C(mouse) + C(session) + om" % c, d).fit()
    FE[c] = (float(fit.params["om"]), float(fit.pvalues["om"]), float(fit.bse["om"]))
OUT["FE"] = FE
d = TR.copy()
d["om_dev"] = d.om - d.groupby("mouse").om.transform("mean")
for c in ("entrances", "epr"):
    r = smf.ols("%s ~ C(mouse) + C(session)" % c, d).fit()
    d[c + "_res"] = r.resid
OUT["fe_points"] = d[["mouse", "session", "om_dev", "entrances_res", "epr_res", "date"]]
OUT["within_sd"] = float(d.om_dev.std())
OUT["within_n03"] = int((d.om_dev.abs() > 0.3).sum())

# natural experiments: the 8/12/2026 step (young Hom 1629, 1633, 1634), 1649's s7 at motor 7, 4/10/2026 morning
NAT = {}
trio = ["1629", "1633", "1634"]
NAT["aug12"] = SM[SM.mouse.isin(trio)][["mouse", "session", "om", "entrances", "shocks", "start_h"]].sort_values(["mouse", "session"])
s4 = SM[SM.session == 4].set_index("mouse")
s5 = SM[SM.session == 5].set_index("mouse")
dd = (s5.entrances - s4.entrances).dropna()
NAT["s4s5_trio"] = dd[trio].to_dict()
NAT["s4s5_other"] = dd.drop(trio).values
NAT["s4s5_p"] = float(st.mannwhitneyu(dd[trio], dd.drop(trio), alternative="two-sided").pvalue)
NAT["s4s5_speedjump"] = (s5.om - s4.om)[trio].to_dict()
m1649 = SM[SM.mouse == "1649"].set_index("session")
NAT["m1649"] = m1649[["entrances", "shocks", "om"]].loc[range(4, 11)].reset_index()
NAT["motor7_speed"] = float(np.median(O["MOT"]["1649_s7"]["w"][O["MOT"]["1649_s7"]["wmotor"] == 7]))
apr = ["522", "531", "576"]
NAT["apr10"] = SM[SM.mouse.isin(apr) & (SM.session <= 8)][["mouse", "session", "om", "entrances", "shocks"]].sort_values(["mouse", "session"])
OUT["NAT"] = NAT

# ------------------------------------------------------------------ K6 among WT alone
WTC = []
for c in MEAS:
    for sk in ("d1", "d2", "imp"):
        v = PM["%s|%s" % (c, sk)]
        for scope, pred in (("WT", is_(g="WT")), ("old WT", is_(g="WT", a="old")), ("WT + Het", lambda m: G[m] in ("WT", "Het"))):
            ms = [m for m in v if pred(m) and np.isfinite(v[m])]
            r = st.spearmanr([OMR[m] for m in ms], [v[m] for m in ms])
            pr = st.pearsonr([OMR[m] for m in ms], [v[m] for m in ms])
            WTC.append(dict(measure=c, summary=sk, scope=scope, rho=float(r[0]), p=float(r[1]), r=float(pr[0]), p_pearson=float(pr[1]),
                            n=len(ms), kind=MEAS[c][2]))
OUT["WTC"] = pd.DataFrame(WTC)

# ------------------------------------------------------------------ K7 young Hom vs young WT; K8 WT vs WT across floors
YOUNG, WTWT = [], []
for c in MEAS:
    for sk in ("d1", "d2", "imp"):
        mid = "%s|%s" % (c, sk)
        r = two(is_(g="WT", a="young"), is_(g="Hom", a="young"), mid)
        YOUNG.append(dict(measure=c, summary=sk, kind=MEAS[c][2], p=r["p"], mean_WT=r["mean_a"], mean_Hom=r["mean_b"], g=r["hedges_g"]))
        r = two(is_(g="WT", a="old", f24=True), is_(g="WT", a="old", f24=False), mid)
        WTWT.append(dict(measure=c, summary=sk, kind=MEAS[c][2], p=r["p"], mean_fast=r["mean_a"], mean_slow=r["mean_b"], g=r["hedges_g"]))
OUT["YOUNG"], OUT["WTWT"] = pd.DataFrame(YOUNG), pd.DataFrame(WTWT)

# ------------------------------------------------------------------ R1 old Hom vs old WT on the 2024 floor
COH = {m: MICE[m]["cohort"] for m in ML}


def van_elteren_strata(v, a_ms, b_ms, strata):
    num = var = 0.0
    for s in set(strata[m] for m in a_ms + b_ms):
        xa = np.array([v[m] for m in a_ms if strata[m] == s])
        xb = np.array([v[m] for m in b_ms if strata[m] == s])
        if xa.size == 0 or xb.size == 0:
            continue
        n = xa.size + xb.size
        r = st.rankdata(np.r_[xa, xb])
        w = 1.0 / (n + 1)
        num += w * (r[xa.size:].sum() - xb.size * (n + 1) / 2.0)
        var += w * w * xa.size * xb.size * (n + 1) / 12.0
    return float(2 * st.norm.sf(abs(num / np.sqrt(var)))) if var > 0 else np.nan


oW = [m for m in ML if GRP[m] == "WT old" and m in F24]
oH = [m for m in ML if GRP[m] == "Hom old"]
# nearest-speed pairs, without replacement, same cohort first
pairs, used = [], set()
for h in sorted(oH, key=lambda m: OMR[m]):
    cands = [w for w in oW if w not in used]
    same = [w for w in cands if COH[w] == COH[h]]
    pool = same or cands
    w = min(pool, key=lambda w: abs(OMR[w] - OMR[h]))
    used.add(w)
    pairs.append((h, w))
R1 = []
for c in MEAS:
    for sk in ("d1", "d2", "imp"):
        mid = "%s|%s" % (c, sk)
        v = PM[mid]
        r = S.two([v[m] for m in oW], [v[m] for m in oH])
        pv = st.wilcoxon([v[h] - v[w] for h, w in pairs]).pvalue if len(pairs) >= 5 else np.nan
        ve = van_elteren_strata(v, oW, oH, COH)
        R1.append(dict(measure=c, summary=sk, kind=MEAS[c][2], p=r["p"], test=r["test"], mean_WT=r["mean_a"], mean_Hom=r["mean_b"],
                       g=r["hedges_g"], p_pairs=float(pv), p_cohort=ve))
r = S.surv_two(np.minimum([PM["criterion"][m] for m in oW], 16), [int(PM["criterion"][m] <= 16) for m in oW],
               np.minimum([PM["criterion"][m] for m in oH], 16), [int(PM["criterion"][m] <= 16) for m in oH])
R1.append(dict(measure="criterion", summary="", kind="per turn", p=r["p"], test=r.get("test", ""), mean_WT=np.nan, mean_Hom=np.nan))
OUT["R1"], OUT["pairs"], OUT["oW"], OUT["oH"] = pd.DataFrame(R1), pairs, oW, oH

# ------------------------------------------------------------------ R2 genotype x age on per-turn measures
R2 = []
for c in MEAS:
    for sk in ("d1", "d2", "imp"):
        mid = "%s|%s" % (c, sk)
        v = PM[mid]
        ms = [m for m in ML if G[m] in ("WT", "Hom") and np.isfinite(v.get(m, np.nan))]
        df = pd.DataFrame({"v": [v[m] for m in ms], "hom": [int(G[m] == "Hom") for m in ms], "old": [int(AG[m] == "old") for m in ms]})
        fit = smf.ols("v ~ hom * old", df).fit()
        did = float(fit.params["hom:old"])
        boots = []
        cells = {(h, o): df[(df.hom == h) & (df.old == o)].v.values for h in (0, 1) for o in (0, 1)}
        for _ in range(4000):
            mm = {k: x[rng.randint(0, x.size, x.size)].mean() for k, x in cells.items()}
            boots.append((mm[(1, 1)] - mm[(0, 1)]) - (mm[(1, 0)] - mm[(0, 0)]))
        boots = np.array(boots)
        pb = float(min(1.0, 2 * min((boots <= 0).mean(), (boots >= 0).mean())))
        yo = S.two([v[m] for m in ms if G[m] == "WT" and AG[m] == "young"], [v[m] for m in ms if G[m] == "Hom" and AG[m] == "young"])
        ol = S.two([v[m] for m in ms if G[m] == "WT" and AG[m] == "old"], [v[m] for m in ms if G[m] == "Hom" and AG[m] == "old"])
        R2.append(dict(measure=c, summary=sk, kind=MEAS[c][2], did=did, did_lo=float(np.percentile(boots, 2.5)),
                       did_hi=float(np.percentile(boots, 97.5)), p_int=float(fit.pvalues["hom:old"]), p_boot=pb,
                       p_young=yo["p"], p_old=ol["p"], **{"mean_%s_%s" % (g, a): float(np.mean([v[m] for m in ms if G[m] == g and AG[m] == a]))
                                                         for g in ("WT", "Hom") for a in ("young", "old")}))
OUT["R2"] = pd.DataFrame(R2)

# learning curves per turn, genotype x age x session (mixed model, Hom and WT)
MMC = {}
for c in ("epr", "spr", "entrances", "shocks"):
    d = TR[TR.geno.isin(["WT", "Hom"])].dropna(subset=[c]).copy()
    d["sc"] = (d.session - 8.5) / 7.5
    d["hom"] = (d.geno == "Hom").astype(int)
    d["old"] = (d.age == "old").astype(int)
    fit = None
    for meth in ("lbfgs", "bfgs", "powell"):
        try:
            fit = smf.mixedlm("%s ~ hom * old * sc" % c, d, groups=d["mouse"], re_formula="~sc").fit(reml=True, method=meth)
            if np.isfinite(fit.pvalues).all():
                break
        except Exception:  # noqa: BLE001
            fit = None
    MMC[c] = {k: (float(fit.params[k]), float(fit.pvalues[k])) for k in fit.params.index if k != "Group Var"} if fit is not None else {}
    MMC[c + "_curves"] = d.groupby(["geno", "age", "session"])[c].agg(["mean", "sem"]).reset_index()
    sl = d.groupby("mouse").apply(lambda q: np.polyfit(q.sc, q[c], 1)[0] / 7.5 * 1.0)      # change per session
    MMC[c + "_slopes"] = sl.to_dict()
    dfs = pd.DataFrame({"s": sl, "hom": d.groupby("mouse").hom.first(), "old": d.groupby("mouse").old.first()})
    f2 = smf.ols("s ~ hom * old", dfs).fit()
    MMC[c + "_slope_tests"] = dict(
        p_int=float(f2.pvalues["hom:old"]),
        p_young=S.two(dfs[(dfs.hom == 0) & (dfs.old == 0)].s, dfs[(dfs.hom == 1) & (dfs.old == 0)].s)["p"],
        p_old=S.two(dfs[(dfs.hom == 0) & (dfs.old == 1)].s, dfs[(dfs.hom == 1) & (dfs.old == 1)].s)["p"],
        p_old24=S.two(dfs[(dfs.hom == 0) & (dfs.old == 1) & dfs.index.isin(list(F24))].s, dfs[(dfs.hom == 1) & (dfs.old == 1)].s)["p"])
OUT["MMC"] = MMC

# ------------------------------------------------------------------ R3 aging within adults on the 2024 floor
R3 = []
for c in MEAS:
    for sk in ("d1", "d2", "imp"):
        v = PM["%s|%s" % (c, sk)]
        ms = [m for m in ML if m in F24 and AG[m] == "old" and G[m] in ("WT", "Hom")]
        df = pd.DataFrame({"v": [v[m] for m in ms], "hom": [int(G[m] == "Hom") for m in ms], "age": [MICE[m]["age_wk"] for m in ms]})
        fit = smf.ols("v ~ hom * age", df).fit()
        rh = st.spearmanr(df[df.hom == 1].age, df[df.hom == 1].v)
        rw = st.spearmanr(df[df.hom == 0].age, df[df.hom == 0].v)
        R3.append(dict(measure=c, summary=sk, kind=MEAS[c][2], p_int=float(fit.pvalues["hom:age"]), b_int=float(fit.params["hom:age"]),
                       rho_Hom=float(rh[0]), p_Hom=float(rh[1]), rho_WT=float(rw[0]), p_WT=float(rw[1])))
OUT["R3"] = pd.DataFrame(R3)

# ------------------------------------------------------------------ R4 extrapolating raw counts (three slopes)
R4 = []
for c in ("shocks", "entrances", "time_in_zone_pct"):
    for sk in ("d1", "d2", "imp"):
        mid = "%s|%s" % (c, sk)
        v = PM[mid]
        ms = [m for m in ML if np.isfinite(v.get(m, np.nan))]
        df = pd.DataFrame({"v": [v[m] for m in ms], "g": [G[m] for m in ms], "om": [OMR[m] for m in ms]})
        slopes = {"shared by the genotypes": float(smf.ols("v ~ C(g) + om", df).fit().params["om"]),
                  "WT only": float(smf.ols("v ~ om", df[df.g == "WT"]).fit().params["om"]),
                  "same mouse (sessions)": FE[c][0] * (0 if sk == "imp" else 1)}
        REF = float(np.median(list(OMR.values())))
        for sname, b in slopes.items():
            adj = {m: v[m] - b * (OMR[m] - REF) for m in ms}
            dfa = pd.DataFrame({"v": [adj[m] for m in ms if G[m] in ("WT", "Hom")],
                                "hom": [int(G[m] == "Hom") for m in ms if G[m] in ("WT", "Hom")],
                                "old": [int(AG[m] == "old") for m in ms if G[m] in ("WT", "Hom")]})
            fit = smf.ols("v ~ hom * old", dfa).fit()
            yo = S.two([adj[m] for m in ms if GRP[m] == "Hom old"], [adj[m] for m in ms if GRP[m] == "Hom young"])
            R4.append(dict(measure=c, summary=sk, slope_source=sname, slope=b, p_int=float(fit.pvalues["hom:old"]),
                           did=float(fit.params["hom:old"]), p_young_vs_old_Hom=yo["p"],
                           old_minus_young_Hom=yo["mean_a"] - yo["mean_b"]))
OUT["R4"] = pd.DataFrame(R4)
OUT["extrap"] = {m: OMR[m] - float(np.median(list(OMR.values()))) for m in ML}

# ------------------------------------------------------------------ replay: walking moved to another floor speed
R = RP["R"]
R = R[R.session > 0]
rows = []
for w in RP["SPEEDS"]:
    rows.append(pd.DataFrame(dict(dw=np.abs(R.om - w), own=R.ent_own, rep=R["ent_%g" % w])))
D = pd.concat(rows)
D["bin"] = pd.cut(D.dw, [0, 0.1, 0.25, 0.5, 1, 2, 4])
OUT["replay"] = D.groupby("bin").agg(n=("own", "size"), own=("own", "mean"), rep=("rep", "mean")).reset_index()
OUT["replay_check"] = (float(np.corrcoef(R.ent_own, SM.set_index("key").loc[R.key, "entrances"])[0, 1]),)

# coverage of the refined reading
SEc = O["SESS"]
SEc = SEc[SEc.use]
OUT["coverage"] = dict(sessions=len(SEc), own_any=int((SEc.n1 > 0).sum()), own_5=int((SEc.n1 >= 5).sum()),
                       halfhour=int((SEc.local_half1 == 0.5).sum()))
pickle.dump(OUT, open(os.path.join(HERE, "cr.pkl"), "wb"))
print("saved cr.pkl")
pd.set_option("display.width", 250)
print(OUT["R1"].to_string(float_format=lambda x: "%.3g" % x))
print(OUT["R2"][["measure", "summary", "did", "did_lo", "did_hi", "p_int", "p_boot", "p_young", "p_old"]].to_string(float_format=lambda x: "%.3g" % x))
print({k: v for k, v in MMC.items() if not k.endswith(("curves", "_slopes"))})
print(OUT["R3"].to_string(float_format=lambda x: "%.3g" % x))
print(OUT["R4"].to_string(float_format=lambda x: "%.3g" % x))
print(FE)
print(NAT["s4s5_trio"], NAT["s4s5_speedjump"], NAT["s4s5_p"], np.mean(NAT["s4s5_other"]))
print(OUT["web"].round(2))
print(OUT["coverage"])
