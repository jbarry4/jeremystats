"""Per-mouse numbers and every contrast for the KCNT1 AA story menu (exploratory, uncorrected, generous).

Inputs : mice.json, session_metrics.csv, tracks.npz (a0/a1).
Outputs: tables/per_mouse_values.csv, tables/all_results.csv.gz, tables/mixed_models.csv, tables/circular.csv,
         tables/sensitivity.csv, tables/occupancy_bins.csv, analysis.pkl (everything the pages need).
"""
import json
import math
import os
import pickle
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as st
from statsmodels.stats.anova import anova_lm

import stats_lib as S

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
TAB = os.path.join(HERE, "tables")
os.makedirs(TAB, exist_ok=True)
MICE = {m["mouse"]: m for m in json.load(open(os.path.join(HERE, "mice.json")))}
SM = pd.read_csv(os.path.join(HERE, "session_metrics.csv"), dtype={"mouse": str})
TR = np.load(os.path.join(HERE, "tracks.npz"))
U = SM[SM.use].copy()
for k in ("yh", "age_group", "age_wk", "sex", "year"):
    U[k] = U.mouse.map(lambda m: MICE[m][k])
GENO = ["WT", "Het", "Hom"]

# ------------------------------------------------------------------ the measures
# id: (plain label, unit, family, higher_is_worse)
SESSION_MEASURES = {
    "shocks": ("Shocks", "count", "learning", True),
    "entrances": ("Entrances into the shock zone", "count", "learning", True),
    "entrances_per_rev": ("Entrances per turn of the arena", "per turn", "learning", True),
    "time_in_zone_pct": ("Time in the shock zone", "% of the session", "learning", True),
    "latency_first_entrance_s": ("Time to the first entrance", "s", "learning", False),
    "max_avoid_s": ("Longest stretch without an entrance", "s", "learning", False),
    "zone_visit_s": ("Time per visit to the zone", "s", "learning", True),
    "shocks_per_entrance": ("Shocks per entrance", "count", "learning", True),
    "strategy_score": ("Opposite over (opposite + pre-shock quadrant)", "0-1", "scatter", False),
    "R": ("Concentration of position around the arena", "0-1", "scatter", False),
    "circ_sd_deg": ("Angular spread of position", "deg", "scatter", True),
    "entropy": ("Occupancy entropy around the arena", "0-1", "scatter", True),
    "angle_coverage": ("Share of 10-deg sectors visited", "0-1", "scatter", True),
    "cells_visited": ("Share of the floor visited", "0-1", "scatter", True),
    "opp_half_pct": ("Time in the half opposite the zone", "%", "scatter", False),
    "mean_abs_angle_deg": ("Mean angle from the zone center", "deg", "scatter", False),
    "dist_from_edge_deg": ("Median distance from the zone edge", "deg", "near", False),
    "buffer_pct": ("Time within 20 deg of the zone edge", "%", "near", True),
    "buffer_pre_pct": ("Time within 20 deg, on the side the arena carries in", "%", "near", True),
    "buffer_post_pct": ("Time within 20 deg, on the far side", "%", "near", True),
    "zone_CW": ("Time in the pre-shock quadrant", "share", "near", True),
    "near_misses": ("Near misses (within 10 deg, then back)", "count", "near", None),
    "near_misses_per_min": ("Near misses per minute", "per min", "near", None),
    "brake_share": ("Close approaches that turned back", "share", "near", False),
    "path_m": ("Path in the room (TrackAnalysis way)", "m", "shape", None),
    "speed_cm_s": ("Speed in the room", "cm/s", "shape", None),
    "speed_sd_cm_s": ("Speed variability in the room", "cm/s", "shape", None),
    "walk_m": ("Distance walked on the arena", "m", "shape", None),
    "walk_speed_cm_s": ("Walking speed on the arena", "cm/s", "shape", None),
    "immobile_pct": ("Time still on the arena", "%", "shape", None),
    "straightness": ("Straightness of walking", "0-1", "shape", None),
    "rim_pct": ("Time at the rim", "%", "shape", None),
    "outer2_pct": ("Time in the outer two rings", "%", "shape", None),
    "center2_pct": ("Time in the inner two rings", "%", "shape", None),
    "mean_r_cm": ("Mean distance from the center", "cm", "shape", None),
}
# s0 is habituation: the shock voltage is off, so every number tied to the zone (shocks, entrances, time in it, where the
# mouse sits relative to it) means nothing there. Those measures get no s0 summary; exploration measures keep theirs.
ZONE_MEASURES = {mid for mid, v in SESSION_MEASURES.items() if v[2] in ("learning", "near")} | {
    "strategy_score", "opp_half_pct", "mean_abs_angle_deg"}
SUMMARIES = {
    "s0": "habituation session s0 (shock off)",
    "d1": "day 1 mean (s1-s8)",
    "d2": "day 2 mean (s9-s16)",
    "late": "last four sessions (s13-s16)",
    "s16": "last session (s16)",
    "early": "first two training sessions (s1-s2)",
    "slope": "change per session over s1-s16 (Theil-Sen)",
    "d1_change": "within day 1: s7-s8 minus s1-s2",
    "overnight": "overnight: s9 minus s8",
    "d2_minus_s0": "day 2 minus habituation (s0)",
    "d2_minus_d1": "day 2 minus day 1 (improvement across days)",
    "total": "sum over s1-s16",
}


def per_mouse():
    vals = {}          # id -> {mouse: value}
    desc = {}
    P = {mid: U.pivot_table(index="mouse", columns="session", values=mid) for mid in SESSION_MEASURES}
    for mid, (lab, unit, fam, worse) in SESSION_MEASURES.items():
        p = P[mid]
        sumdefs = {
            "s0": p[0], "d1": p.loc[:, 1:8].mean(axis=1), "d2": p.loc[:, 9:16].mean(axis=1),
            "late": p.loc[:, 13:16].mean(axis=1), "s16": p[16], "early": p.loc[:, 1:2].mean(axis=1),
            "d1_change": p.loc[:, 7:8].mean(axis=1) - p.loc[:, 1:2].mean(axis=1), "overnight": p[9] - p[8],
            "d2_minus_s0": p.loc[:, 9:16].mean(axis=1) - p[0],
            "d2_minus_d1": p.loc[:, 9:16].mean(axis=1) - p.loc[:, 1:8].mean(axis=1),
        }
        sl = {}
        for m in p.index:
            yv = p.loc[m, 1:16].values.astype(float)
            ok = np.isfinite(yv)
            sl[m] = float(st.theilslopes(yv[ok], np.arange(1, 17)[ok])[0]) if ok.sum() >= 8 else np.nan
        sumdefs["slope"] = pd.Series(sl)
        if unit == "count":
            sumdefs["total"] = p.loc[:, 1:16].sum(axis=1)
        if mid in ZONE_MEASURES:
            sumdefs.pop("s0")
            sumdefs.pop("d2_minus_s0")
        for sk, ser in sumdefs.items():
            key = "%s|%s" % (mid, sk)
            vals[key] = {m: float(v) for m, v in ser.items() if np.isfinite(v)}
            desc[key] = dict(measure=mid, summary=sk, label=lab, unit=unit, family=fam, worse=worse,
                             words="%s, %s" % (lab, SUMMARIES[sk]))
    # ---- consistency of the safe spot (H3) -------------------------------------------------------------
    occ = {}
    for m in MICE:
        occ[m] = {k: TR["%s_s%d|occ36" % (m, k)] for k in range(17)}
    md = U.pivot_table(index="mouse", columns="session", values="mean_dir_deg")
    cons = {"pref_sd_d2": {}, "pref_sd_d1": {}, "pref_shift_d1d2": {}, "map_stab_d2": {}, "map_stab_d1": {},
            "map_overnight": {}, "map_d1_vs_d2": {}, "d2_dir": {}, "d2_R_pooled": {}}
    for m in MICE:
        d2 = md.loc[m, 9:16].values
        d1 = md.loc[m, 1:8].values
        _, R2 = S.circ_mean(d2)
        _, R1 = S.circ_mean(d1)
        cons["pref_sd_d2"][m] = math.degrees(math.sqrt(-2 * math.log(max(R2, 1e-9))))
        cons["pref_sd_d1"][m] = math.degrees(math.sqrt(-2 * math.log(max(R1, 1e-9))))
        mu1, _ = S.circ_mean(md.loc[m, 5:8].values)
        mu2, _ = S.circ_mean(d2)
        cons["pref_shift_d1d2"][m] = abs((mu1 - mu2 + 180) % 360 - 180)
        o = occ[m]
        cons["map_stab_d2"][m] = float(np.mean([np.corrcoef(o[k], o[k + 1])[0, 1] for k in range(9, 16)]))
        cons["map_stab_d1"][m] = float(np.mean([np.corrcoef(o[k], o[k + 1])[0, 1] for k in range(1, 8)]))
        cons["map_overnight"][m] = float(np.corrcoef(o[8], o[9])[0, 1])
        cons["map_d1_vs_d2"][m] = float(np.corrcoef(np.mean([o[k] for k in range(5, 9)], axis=0),
                                                    np.mean([o[k] for k in range(9, 17)], axis=0))[0, 1])
        pooled = np.mean([o[k] for k in range(9, 17)], axis=0)
        centers = np.arange(-175, 180, 10)
        mu, R = S.circ_mean(centers, pooled)
        cons["d2_dir"][m] = mu
        cons["d2_R_pooled"][m] = R
    CW = {"pref_sd_d2": ("Session-to-session wander of the preferred direction, day 2", "deg", True),
          "pref_sd_d1": ("Session-to-session wander of the preferred direction, day 1", "deg", True),
          "pref_shift_d1d2": ("Shift of the preferred direction from late day 1 to day 2", "deg", True),
          "map_stab_d2": ("Same occupancy pattern session to session, day 2 (r)", "r", False),
          "map_stab_d1": ("Same occupancy pattern session to session, day 1 (r)", "r", False),
          "map_overnight": ("Same occupancy pattern overnight, s8 vs s9 (r)", "r", False),
          "map_d1_vs_d2": ("Same occupancy pattern late day 1 vs day 2 (r)", "r", False),
          "d2_R_pooled": ("Concentration of day-2 occupancy around one direction", "0-1", False)}
    for k, (lab, unit, worse) in CW.items():
        vals["consistency|" + k] = cons[k]
        desc["consistency|" + k] = dict(measure=k, summary="mouse", label=lab, unit=unit, family="consistency", worse=worse, words=lab)
    # ---- criterion / learner ------------------------------------------------------------------------------
    ent = P["entrances"]
    crit = {}
    for m in ent.index:
        hit = [k for k in range(1, 17) if np.isfinite(ent.loc[m, k]) and ent.loc[m, k] <= 1]
        crit[m] = float(hit[0]) if hit else 17.0
    vals["criterion|sessions_to_criterion"] = crit
    desc["criterion|sessions_to_criterion"] = dict(
        measure="sessions_to_criterion", summary="mouse", label="First session with at most one entrance", unit="session",
        family="learning", worse=True,
        words="First training session with at most one entrance; mice that never got there by s16 count as not reached "
              "(compared as time-to-criterion curves: log-rank family, Cox for adjusted and interaction terms)")
    return vals, desc, cons, occ


VALS, DESC, CONS, OCC = per_mouse()
MLIST = sorted(MICE, key=int)


def attr(m, k):
    return MICE[m][k]


ROT = U.groupby("mouse").omega_deg_s.median().to_dict()
ROTBIN = {m: ("fast" if w >= 4.8 else ("medium" if w >= 4.0 else "slow")) for m, w in ROT.items()}
for m in MICE:
    MICE[m]["omega"] = ROT[m]
    MICE[m]["rot_bin"] = ROTBIN[m]


# ------------------------------------------------------------------ contrasts per mouse-level measure
def contrasts(v):
    """v: {mouse: value}. Every contrast the numbers allow."""
    out = []
    fin = {m: x for m, x in v.items() if np.isfinite(x)}
    if len(fin) < 8 or np.ptp(list(fin.values())) == 0:
        return out

    def grp(pred):
        return np.array([x for m, x in fin.items() if pred(m)])

    def add(cid, grouping, words, res):
        res.update(contrast=cid, grouping=grouping, words=words)
        out.append(res)

    for scope, pred0 in (("all", lambda m: True), ("young", lambda m: attr(m, "age_group") == "young"),
                         ("old", lambda m: attr(m, "age_group") == "old"), ("fast", lambda m: ROTBIN[m] == "fast"),
                         ("medium", lambda m: ROTBIN[m] == "medium"), ("slow", lambda m: ROTBIN[m] == "slow")):
        g = {k: grp(lambda m, k=k: pred0(m) and attr(m, "yh") == k) for k in GENO}
        tag = "" if scope == "all" else "_" + scope
        sw = "" if scope == "all" else " (%s%s mice)" % (scope, " rotation" if scope in ("fast", "medium", "slow") else "")
        for a, b in (("WT", "Het"), ("WT", "Hom"), ("Het", "Hom")):
            if g[a].size >= 3 and g[b].size >= 3:
                add("%s_vs_%s%s" % (b, a, tag), "genotype" + tag, "%s against %s%s" % (b, a, sw), S.two(g[a], g[b]))
        if g["WT"].size >= 3 and (g["Het"].size + g["Hom"].size) >= 3:
            add("Mut_vs_WT" + tag, "genotype" + tag, "Het+Hom against WT" + sw, S.two(g["WT"], np.r_[g["Het"], g["Hom"]]))
        if min(x.size for x in g.values()) >= 3:
            add("GENO3" + tag, "genotype" + tag, "WT / Het / Hom" + sw, S.three([g["WT"], g["Het"], g["Hom"]]))
    # age
    yo = {k: grp(lambda m, k=k: attr(m, "age_group") == k) for k in ("young", "old")}
    add("young_vs_old", "age", "young against old (all genotypes)", S.two(yo["old"], yo["young"]))
    for k in GENO:
        a = grp(lambda m: attr(m, "yh") == k and attr(m, "age_group") == "old")
        b = grp(lambda m: attr(m, "yh") == k and attr(m, "age_group") == "young")
        if a.size >= 3 and b.size >= 3:
            add("young_vs_old_" + k, "age", "young against old, %s only" % k, S.two(a, b))
    ms = list(fin)
    add("age_corr_all", "age", "against age in weeks, all mice", S.corr([attr(m, "age_wk") for m in ms], [fin[m] for m in ms]))
    for k in GENO:
        mk = [m for m in ms if attr(m, "yh") == k]
        add("age_corr_" + k, "age", "against age in weeks, %s only" % k, S.corr([attr(m, "age_wk") for m in mk], [fin[m] for m in mk]))
    add("rot_corr_all", "rotation", "against the arena's rotation speed, all mice", S.corr([ROT[m] for m in ms], [fin[m] for m in ms]))
    # checks
    for cid, key, a, b, words in (("sex_F_vs_M", "sex", "M", "F", "females against males"),
                                  ("year_2026_vs_2024", "year", 2024, 2026, "2026 mice against 2024 mice")):
        add(cid, "checks", words, S.two(grp(lambda m: attr(m, key) == a), grp(lambda m: attr(m, key) == b)))
    add("injected_vs_not", "checks", "virus-injected before AA against not",
        S.two(grp(lambda m: not attr(m, "injected_before")), grp(lambda m: attr(m, "injected_before"))))
    # models: genotype x age group, genotype x age (weeks), genotype adjusted for rotation (and age)
    df = pd.DataFrame({"v": [fin[m] for m in ms], "yh": [attr(m, "yh") for m in ms], "ag": [attr(m, "age_group") for m in ms],
                       "age": [attr(m, "age_wk") for m in ms], "rot": [ROT[m] for m in ms]})
    try:
        fit = smf.ols("v ~ C(yh, Treatment('WT')) * C(ag, Treatment('old'))", df).fit()
        a2 = anova_lm(fit, typ=2)
        pint = float(a2.loc["C(yh, Treatment('WT')):C(ag, Treatment('old'))", "PR(>F)"])
        for term, lab in (("C(yh, Treatment('WT'))[T.Hom]:C(ag, Treatment('old'))[T.young]", "Hom"),
                          ("C(yh, Treatment('WT'))[T.Het]:C(ag, Treatment('old'))[T.young]", "Het")):
            add("int_age_group_" + lab, "interaction", "genotype x age group: does being young change the %s-WT gap?" % lab,
                {"p": float(fit.pvalues[term]), "test": "OLS interaction term", "effect": float(fit.params[term]),
                 "p_overall_interaction": pint, "n": len(ms)})
        add("int_age_group", "interaction", "genotype x age group (overall)", {"p": pint, "test": "two-way ANOVA", "effect": np.nan, "n": len(ms)})
    except Exception:  # noqa: BLE001
        pass
    try:
        fit = smf.ols("v ~ C(yh, Treatment('WT')) * age", df).fit()
        for lab in ("Hom", "Het"):
            term = "C(yh, Treatment('WT'))[T.%s]:age" % lab
            add("int_age_wk_" + lab, "interaction", "genotype x age (weeks): does the %s slope with age differ from WT's?" % lab,
                {"p": float(fit.pvalues[term]), "test": "OLS interaction term", "effect": float(fit.params[term]), "n": len(ms)})
    except Exception:  # noqa: BLE001
        pass
    for formula, tag, words in (("v ~ C(yh, Treatment('WT')) + rot", "adj_rot", "adjusted for rotation speed"),
                                ("v ~ C(yh, Treatment('WT')) + rot + age", "adj_rot_age", "adjusted for rotation speed and age")):
        try:
            fit = smf.ols(formula, df).fit()
            for lab in ("Het", "Hom"):
                term = "C(yh, Treatment('WT'))[T.%s]" % lab
                add("%s_vs_WT_%s" % (lab, tag), "adjusted", "%s against WT, %s" % (lab, words),
                    {"p": float(fit.pvalues[term]), "test": "OLS", "effect": float(fit.params[term]), "n": len(ms),
                     "p_rot": float(fit.pvalues["rot"])})
        except Exception:  # noqa: BLE001
            pass
    try:
        fit = smf.ols("v ~ C(yh, Treatment('WT')) * C(ag, Treatment('old')) + rot", df).fit()
        term = "C(yh, Treatment('WT'))[T.Hom]:C(ag, Treatment('old'))[T.young]"
        add("int_age_group_Hom_adj_rot", "interaction", "genotype x age group (Hom), adjusted for rotation speed",
            {"p": float(fit.pvalues[term]), "test": "OLS interaction term", "effect": float(fit.params[term]), "n": len(ms)})
    except Exception:  # noqa: BLE001
        pass
    return out


CRIT = "criterion|sessions_to_criterion"


def crit_contrasts(v):
    """The criterion as time to an event: v = first session with at most one entrance, 17 = not reached by s16
    (censored at 16). Same contrast ids as contrasts(), with survival tests, rank correlations and Cox models."""
    from statsmodels.duration.hazard_regression import PHReg
    out = []
    fin = {m: x for m, x in v.items() if np.isfinite(x)}

    def te(pred):
        ms = [m for m in fin if pred(m)]
        return (np.array([min(fin[m], 16.0) for m in ms]), np.array([1 if fin[m] <= 16 else 0 for m in ms]))

    def add(cid, grouping, words, res):
        res.update(contrast=cid, grouping=grouping, words=words)
        out.append(res)

    for scope, pred0 in (("all", lambda m: True), ("young", lambda m: attr(m, "age_group") == "young"),
                         ("old", lambda m: attr(m, "age_group") == "old"), ("fast", lambda m: ROTBIN[m] == "fast"),
                         ("medium", lambda m: ROTBIN[m] == "medium"), ("slow", lambda m: ROTBIN[m] == "slow")):
        g = {k: te(lambda m, k=k: pred0(m) and attr(m, "yh") == k) for k in GENO}
        tag = "" if scope == "all" else "_" + scope
        sw = "" if scope == "all" else " (%s%s mice)" % (scope, " rotation" if scope in ("fast", "medium", "slow") else "")
        for a, b in (("WT", "Het"), ("WT", "Hom"), ("Het", "Hom")):
            if g[a][0].size >= 3 and g[b][0].size >= 3:
                add("%s_vs_%s%s" % (b, a, tag), "genotype" + tag, "%s against %s%s" % (b, a, sw), S.surv_two(*g[a], *g[b]))
        mut = (np.r_[g["Het"][0], g["Hom"][0]], np.r_[g["Het"][1], g["Hom"][1]])
        if g["WT"][0].size >= 3 and mut[0].size >= 3:
            add("Mut_vs_WT" + tag, "genotype" + tag, "Het+Hom against WT" + sw, S.surv_two(*g["WT"], *mut))
        if min(x[0].size for x in g.values()) >= 3:
            add("GENO3" + tag, "genotype" + tag, "WT / Het / Hom" + sw, S.surv_k([g["WT"], g["Het"], g["Hom"]]))
    add("young_vs_old", "age", "young against old (all genotypes)",
        S.surv_two(*te(lambda m: attr(m, "age_group") == "old"), *te(lambda m: attr(m, "age_group") == "young")))
    for k in GENO:
        a = te(lambda m: attr(m, "yh") == k and attr(m, "age_group") == "old")
        b = te(lambda m: attr(m, "yh") == k and attr(m, "age_group") == "young")
        if a[0].size >= 3 and b[0].size >= 3:
            add("young_vs_old_" + k, "age", "young against old, %s only" % k, S.surv_two(*a, *b))
    ms = list(fin)
    add("age_corr_all", "age", "against age in weeks, all mice (rank)", S.corr_rank([attr(m, "age_wk") for m in ms], [fin[m] for m in ms]))
    for k in GENO:
        mk = [m for m in ms if attr(m, "yh") == k]
        add("age_corr_" + k, "age", "against age in weeks, %s only (rank)" % k,
            S.corr_rank([attr(m, "age_wk") for m in mk], [fin[m] for m in mk]))
    add("rot_corr_all", "rotation", "against the arena's rotation speed, all mice (rank)",
        S.corr_rank([ROT[m] for m in ms], [fin[m] for m in ms]))
    for cid, key, a, b, words in (("sex_F_vs_M", "sex", "M", "F", "females against males"),
                                  ("year_2026_vs_2024", "year", 2024, 2026, "2026 mice against 2024 mice")):
        add(cid, "checks", words, S.surv_two(*te(lambda m: attr(m, key) == a), *te(lambda m: attr(m, key) == b)))
    add("injected_vs_not", "checks", "virus-injected before AA against not",
        S.surv_two(*te(lambda m: not attr(m, "injected_before")), *te(lambda m: attr(m, "injected_before"))))
    df = pd.DataFrame({"t": [min(fin[m], 16.0) for m in ms], "e": [1 if fin[m] <= 16 else 0 for m in ms],
                       "yh": [attr(m, "yh") for m in ms], "ag": [attr(m, "age_group") for m in ms],
                       "age": [attr(m, "age_wk") for m in ms], "rot": [ROT[m] for m in ms]})

    def cox(formula):
        fit = PHReg.from_formula(formula, df, status=df["e"].values, ties="efron").fit()
        names = fit.model.exog_names
        return dict(zip(names, np.asarray(fit.pvalues, float))), dict(zip(names, np.asarray(fit.params, float)))

    try:
        p, c = cox("t ~ C(yh, Treatment('WT')) * C(ag, Treatment('old'))")
        for lab in ("Hom", "Het"):
            term = "C(yh, Treatment('WT'))[T.%s]:C(ag, Treatment('old'))[T.young]" % lab
            add("int_age_group_" + lab, "interaction", "genotype x age group: does being young change the %s-WT gap?" % lab,
                {"p": p[term], "test": "Cox interaction term", "effect": float(np.exp(c[term])), "n": len(ms)})
    except Exception:  # noqa: BLE001
        pass
    try:
        p, c = cox("t ~ C(yh, Treatment('WT')) * age")
        for lab in ("Hom", "Het"):
            term = "C(yh, Treatment('WT'))[T.%s]:age" % lab
            add("int_age_wk_" + lab, "interaction", "genotype x age (weeks): does the %s slope with age differ from WT's?" % lab,
                {"p": p[term], "test": "Cox interaction term", "effect": float(np.exp(c[term])), "n": len(ms)})
    except Exception:  # noqa: BLE001
        pass
    for formula, tag, words in (("t ~ C(yh, Treatment('WT')) + rot", "adj_rot", "adjusted for rotation speed"),
                                ("t ~ C(yh, Treatment('WT')) + rot + age", "adj_rot_age", "adjusted for rotation speed and age")):
        try:
            p, c = cox(formula)
            for lab in ("Het", "Hom"):
                term = "C(yh, Treatment('WT'))[T.%s]" % lab
                add("%s_vs_WT_%s" % (lab, tag), "adjusted", "%s against WT, %s" % (lab, words),
                    {"p": p[term], "test": "Cox", "effect": float(np.exp(c[term])), "n": len(ms), "p_rot": p["rot"]})
        except Exception:  # noqa: BLE001
            pass
    try:
        p, c = cox("t ~ C(yh, Treatment('WT')) * C(ag, Treatment('old')) + rot")
        term = "C(yh, Treatment('WT'))[T.Hom]:C(ag, Treatment('old'))[T.young]"
        add("int_age_group_Hom_adj_rot", "interaction", "genotype x age group (Hom), adjusted for rotation speed",
            {"p": p[term], "test": "Cox interaction term", "effect": float(np.exp(c[term])), "n": len(ms)})
    except Exception:  # noqa: BLE001
        pass
    return out


rows = []
for key, v in VALS.items():
    for r in (crit_contrasts(v) if key == CRIT else contrasts(v)):
        r.update(id=key, **{k: DESC[key][k] for k in ("measure", "summary", "label", "unit", "family", "words") if k != "words"},
                 measure_words=DESC[key]["words"], worse=DESC[key]["worse"])
        rows.append(r)
RES = pd.DataFrame(rows)
print("contrast rows", len(RES), "P<0.05:", int((RES.p < 0.05).sum()))

# ------------------------------------------------------------------ learners (Fisher)
learned = {m: (VALS["entrances_per_rev|d2"][m] < 0.5) for m in MICE}
lrows = []
for a, b in (("WT", "Het"), ("WT", "Hom"), ("Het", "Hom")):
    ya = sum(learned[m] for m in MICE if attr(m, "yh") == a)
    na = sum(1 for m in MICE if attr(m, "yh") == a)
    yb = sum(learned[m] for m in MICE if attr(m, "yh") == b)
    nb = sum(1 for m in MICE if attr(m, "yh") == b)
    r = S.fisher(ya, na, yb, nb)
    r.update(contrast="%s_vs_%s" % (b, a), words="share of learners (day-2 entrances per turn < 0.5)")
    lrows.append(r)
LEARN = pd.DataFrame(lrows)

# ------------------------------------------------------------------ mixed models on the sessions
KEY_SESSION = ["shocks", "entrances", "entrances_per_rev", "time_in_zone_pct", "latency_first_entrance_s", "max_avoid_s",
               "R", "entropy", "circ_sd_deg", "buffer_pct", "buffer_pre_pct", "near_misses_per_min", "brake_share",
               "strategy_score", "opp_half_pct", "walk_speed_cm_s", "immobile_pct", "straightness", "rim_pct", "speed_cm_s",
               "zone_visit_s", "dist_from_edge_deg", "cells_visited"]
L = U[(U.session >= 1) & (U.session <= 16)].copy()
L["sc"] = (L.session - 8.5) / 7.5
L["day"] = np.where(L.session <= 8, "d1", "d2")
L["rot"] = L.omega_deg_s
mm_rows = []
for mid in KEY_SESSION:
    d = L.dropna(subset=[mid]).copy()
    unit = SESSION_MEASURES[mid][1]
    d["y"] = np.log1p(d[mid]) if unit == "count" else d[mid]
    specs = [
        ("geno_x_session", "y ~ C(yh, Treatment('WT')) * sc"),
        ("geno_x_day", "y ~ C(yh, Treatment('WT')) * C(day)"),
        ("geno_x_agegroup", "y ~ C(yh, Treatment('WT')) * C(age_group, Treatment('old')) + sc"),
        ("geno_adj_rot_age", "y ~ C(yh, Treatment('WT')) + sc + rot + age_wk"),
        ("geno_x_agegroup_adj_rot", "y ~ C(yh, Treatment('WT')) * C(age_group, Treatment('old')) + sc + rot"),
    ]
    for name, f in specs:
        try:
            fit = None
            for meth in ("lbfgs", "bfgs", "powell", "nm"):
                try:
                    fit = smf.mixedlm(f, d, groups=d["mouse"]).fit(reml=True, method=meth)
                    if np.isfinite(fit.pvalues).all():
                        break
                except Exception:  # noqa: BLE001
                    fit = None
            if fit is None:
                raise RuntimeError("no optimizer converged")
            for term, p in fit.pvalues.items():
                if "yh" in term or term in ("rot", "age_wk") or "age_group" in term:
                    mm_rows.append(dict(measure=mid, label=SESSION_MEASURES[mid][0], model=name, formula=f, term=term,
                                        coef=float(fit.params[term]), p=float(p), n_mice=d.mouse.nunique(), n_sessions=len(d),
                                        transform="log1p" if unit == "count" else "none"))
        except Exception as e:  # noqa: BLE001
            mm_rows.append(dict(measure=mid, model=name, formula=f, term="(failed)", p=np.nan, coef=np.nan, error=str(e)[:200]))
    if unit == "count":
        try:
            import statsmodels.api as sm
            gee = smf.gee("%s ~ C(yh, Treatment('WT')) * sc + rot" % mid, "mouse", d, family=sm.families.Poisson(),
                          cov_struct=sm.cov_struct.Exchangeable()).fit()
            for term, p in gee.pvalues.items():
                if "yh" in term or term == "rot":
                    mm_rows.append(dict(measure=mid, label=SESSION_MEASURES[mid][0], model="gee_poisson_x_session_adj_rot",
                                        formula="%s ~ geno*session + rot (Poisson GEE)" % mid, term=term,
                                        coef=float(gee.params[term]), p=float(p), n_mice=d.mouse.nunique(), n_sessions=len(d),
                                        transform="log link"))
        except Exception as e:  # noqa: BLE001
            mm_rows.append(dict(measure=mid, model="gee", term="(failed)", p=np.nan, error=str(e)[:200]))
MM = pd.DataFrame(mm_rows)
print("mixed-model rows", len(MM), "P<0.05:", int((MM.p < 0.05).sum()))

# ------------------------------------------------------------------ circular (H3)
circ_rows = []
dirs = CONS["d2_dir"]
for g in GENO:
    a = [dirs[m] for m in MICE if attr(m, "yh") == g]
    r1 = S.rayleigh(a)
    r1.update(group=g, words="day-2 preferred directions cluster (Rayleigh)")
    circ_rows.append(r1)
    r2 = S.vtest(a, 180.0)
    r2.update(group=g, words="day-2 preferred directions point to the opposite side (V test toward 180 deg)")
    circ_rows.append(r2)
    mu, R = S.circ_mean(a)
    circ_rows.append(dict(group=g, test="circular mean", p=np.nan, mean_deg=mu, R=R, n=len(a), words="mean of the preferred directions"))
for a, b in (("WT", "Het"), ("WT", "Hom"), ("Het", "Hom")):
    r = S.perm_circ([dirs[m] for m in MICE if attr(m, "yh") == a], [dirs[m] for m in MICE if attr(m, "yh") == b])
    r.update(group="%s_vs_%s" % (b, a), words="preferred direction and its spread across mice, day 2")
    circ_rows.append(r)
CIRC = pd.DataFrame(circ_rows)

# per-bin occupancy, day 2 (where do Hets spend more time?)
bins = np.arange(-175, 180, 10)
occ_rows = []
for k, c in enumerate(bins):
    for blk, rng_ in (("s0", [0]), ("d1", range(1, 9)), ("d2", range(9, 17))):
        v = {m: float(np.mean([OCC[m][s][k] for s in rng_])) for m in MICE}
        for a, b in (("WT", "Het"), ("WT", "Hom")):
            r = S.two([v[m] for m in MICE if attr(m, "yh") == a], [v[m] for m in MICE if attr(m, "yh") == b])
            occ_rows.append(dict(bin_center=c, block=blk, contrast="%s_vs_%s" % (b, a), p=r["p"], test=r["test"],
                                 mean_a=r["mean_a"], mean_b=r["mean_b"]))
OCCB = pd.DataFrame(occ_rows)

# ------------------------------------------------------------------ sensitivity: outliers and flagged mice
def robust_out(v):
    """Mice more than 3.5 robust s.d. (1.4826 x MAD) from their genotype's median."""
    out = set()
    for g in GENO:
        ms = [m for m in v if attr(m, "yh") == g and np.isfinite(v[m])]
        x = np.array([v[m] for m in ms])
        if x.size < 4:
            continue
        med = np.median(x)
        mad = 1.4826 * np.median(np.abs(x - med))
        if mad <= 0:
            continue
        out |= {m for m, xx in zip(ms, x) if abs(xx - med) / mad > 3.5}
    return out


DROPS = {
    "none": set(),
    "robust outliers": None,
    "461, 462, 457": {"461", "462", "457"},
    "injected within 7 days": {m for m in MICE if attr(m, "injected_7d")},
    "all injected before AA": {m for m in MICE if attr(m, "injected_before")},
    "2024 mice only": {m for m in MICE if attr(m, "year") != 2024},
    "2026 mice only": {m for m in MICE if attr(m, "year") != 2026},
}
SENS_KEYS = ["shocks|d2", "shocks|total", "entrances|d2", "entrances_per_rev|d2", "time_in_zone_pct|d2", "time_in_zone_pct|late",
             "latency_first_entrance_s|d2", "max_avoid_s|d2", "shocks|slope", "R|s0", "cells_visited|s0", "R|d2", "entropy|d2",
             "buffer_pct|d2", "near_misses_per_min|d2", "brake_share|d2", "consistency|pref_sd_d2", "consistency|map_stab_d2",
             "walk_speed_cm_s|d2", "immobile_pct|d2", "straightness|d2", "criterion|sessions_to_criterion"]
sens_rows = []
for key in SENS_KEYS:
    v = VALS[key]
    for dname, drop in DROPS.items():
        dset = robust_out(v) if drop is None else drop
        vv = {m: x for m, x in v.items() if m not in dset}
        for r in (crit_contrasts(vv) if key == CRIT else contrasts(vv)):
            if r["contrast"] in ("Het_vs_WT", "Hom_vs_WT", "Hom_vs_Het", "GENO3", "young_vs_old_Hom", "int_age_group_Hom",
                                 "Hom_vs_WT_young", "Hom_vs_WT_old", "Hom_vs_WT_adj_rot_age", "Het_vs_WT_adj_rot_age"):
                sens_rows.append(dict(id=key, drop=dname, dropped=", ".join(sorted(dset, key=int)), contrast=r["contrast"],
                                      p=r["p"], test=r["test"], effect=r.get("effect"), n=len(vv)))
SENS = pd.DataFrame(sens_rows)

# ------------------------------------------------------------------ save
PM = pd.DataFrame({k: pd.Series(v) for k, v in VALS.items()})
PM.index.name = "mouse"
PM = PM.loc[MLIST]
PM.insert(PM.columns.get_loc(CRIT) + 1, "criterion|reached_by_s16", (PM[CRIT] <= 16).astype(int))
PM[CRIT] = PM[CRIT].where(PM[CRIT] <= 16)   # blank = never reached by s16
meta = pd.DataFrame([{**{k: MICE[m][k] for k in ("yh", "sex", "age_wk", "age_group", "cohort", "year", "omega", "rot_bin",
                                                   "injected_before", "injected_7d", "not_naive")},
                      "flags": "; ".join(MICE[m]["flags"]), "mouse": m} for m in MLIST]).set_index("mouse")
pd.concat([meta, PM], axis=1).to_csv(os.path.join(TAB, "per_mouse_values.csv"))
cols = ["id", "measure_words", "family", "summary", "contrast", "grouping", "words", "p", "test", "effect", "n_a", "n_b",
        "mean_a", "mean_b", "median_a", "median_b", "hedges_g", "rank_biserial", "separated", "rho", "n",
        "reached_a", "reached_b", "km_median_a", "km_median_b", "hazard_ratio",
        "p_Mann-Whitney", "p_Welch t", "p_Student t", "p_Brunner-Munzel", "p_ANOVA", "p_Kruskal-Wallis", "p_ordered trend",
        "p_Spearman", "p_Pearson", "p_Kendall", "p_log-rank", "p_Gehan-Breslow", "p_Tarone-Ware", "p_rot",
        "p_overall_interaction"]
RES[[c for c in cols if c in RES.columns]].to_csv(os.path.join(TAB, "all_results.csv.gz"), index=False, compression="gzip")
MM.to_csv(os.path.join(TAB, "mixed_models.csv"), index=False)
CIRC.to_csv(os.path.join(TAB, "circular.csv"), index=False)
SENS.to_csv(os.path.join(TAB, "sensitivity.csv"), index=False)
OCCB.to_csv(os.path.join(TAB, "occupancy_bins.csv"), index=False)
LEARN.to_csv(os.path.join(TAB, "learners.csv"), index=False)
U_out = U.copy()
U_out.insert(U_out.columns.get_loc("session") + 1, "phase",
             np.where(U_out.session == 0, "habituation (shock off)", np.where(U_out.session <= 8, "day 1", "day 2")))
U_out.loc[U_out.session == 0, [c for c in ZONE_MEASURES if c in U_out.columns]] = np.nan   # meaningless with the shock off
U_out.to_csv(os.path.join(TAB, "per_session_values.csv"), index=False)
pickle.dump(dict(VALS=VALS, DESC=DESC, RES=RES, MM=MM, CIRC=CIRC, SENS=SENS, OCCB=OCCB, LEARN=LEARN, CONS=CONS,
                 MICE=MICE, ROT=ROT, ROTBIN=ROTBIN, learned=learned, SESSION_MEASURES=SESSION_MEASURES,
                 SUMMARIES=SUMMARIES), open(os.path.join(HERE, "analysis.pkl"), "wb"))
print("saved")
