"""Merges every family's results and makes the corrections.

  python analyze.py

Writes merged/tests.pkl (a pandas table: one row per measure x contrast)
and merged/measures.pkl (one row per measure with its 17 numbers).

Corrections (raw P stays in column p):
  q_all          Benjamini-Hochberg over every test
  q_contrast     Benjamini-Hochberg within the contrast
  q_family       Benjamini-Hochberg within family x contrast
  p_maxT         family-wise: the share of 2,000 shuffles of the mouse labels
                 in which the strongest of ALL measures in that contrast is at
                 least as strong as this one (it accounts for the measures
                 being correlated with one another)
Per test also: the same measure on the other event set (p_other_set,
same_sign_other_set) and, for type-specific measures, across classifiers
(n_variants, share_same_sign, share_p05).
"""
import glob
import json
import os
import pickle

import numpy as np
import pandas as pd
from scipy import stats as st

HERE = os.path.dirname(os.path.abspath(__file__))
META = [m for m in json.load(open(os.path.join(HERE, "data", "meta.json"))) if m["lab"] not in ("m6",)]  # m6 excluded 2026-11-17 (dsdata.EXCLUDED)
LABS = [m["lab"] for m in META if m["n_v6"] >= 20]
G = np.array([m["group"] for m in META if m["n_v6"] >= 20])
SG = np.array([m["subgroup"] for m in META if m["n_v6"] >= 20])
KO = np.array([m["ko"] for m in META if m["n_v6"] >= 20], float)
N_PERM = 2000
RES = os.environ.get("BATTERY_OUT", "results")        # the filter battery: results_filters
MERGED = os.environ.get("BATTERY_MERGED", "merged")   # the filter battery: merged_filters


def bh(p):
    p = np.asarray(p, float)
    q = np.full(p.size, np.nan)
    ok = np.isfinite(p)
    pv = p[ok]
    o = np.argsort(pv)
    r = pv[o] * pv.size / (np.arange(pv.size) + 1.0)
    r = np.minimum.accumulate(r[::-1])[::-1]
    out = np.empty(pv.size)
    out[o] = np.minimum(r, 1.0)
    q[ok] = out
    return q


def contrast_design():
    """contrast -> (which recordings take part, the label vector x, how to shuffle)."""
    lvl_ko = np.where(G == "CTL", 0.0, np.where(KO < 10, 1.0, 2.0))
    lvl_ied = np.where(SG == "CTL", 0.0, np.where(SG == "IED-", 1.0, 2.0))
    one = np.ones(G.size, bool)
    return {
        "PTEN_vs_CTL": (one, (G == "PTEN").astype(float)),
        "KO_dose_PTEN": (G == "PTEN", st.rankdata(KO)),
        "KO_dose_all": (one, st.rankdata(KO)),
        "highKO_vs_CTL": ((G == "CTL") | (KO >= 15), (G == "PTEN").astype(float)),
        "lowKO_vs_CTL": ((G == "CTL") | ((G == "PTEN") & (KO < 10)), (G == "PTEN").astype(float)),
        "trend_CTL_lowKO_highKO": (one, lvl_ko),
        "IEDpos_vs_IEDneg": (G == "PTEN", (SG == "IED+").astype(float)),
        "IEDpos_vs_CTL": (SG != "IED-", (SG == "IED+").astype(float)),
        "IEDneg_vs_CTL": (SG != "IED+", (SG == "IED-").astype(float)),
        "trend_CTL_IEDneg_IEDpos": (one, lvl_ied),
    }


def rank_rows(V):
    """Each row's finite entries ranked, centered and scaled to unit length
    (zeros where missing)."""
    Z = np.zeros_like(V)
    mask = np.isfinite(V)
    for j in range(V.shape[0]):
        m = mask[j]
        if m.sum() >= 5:
            r = st.rankdata(V[j, m])
            r = r - r.mean()
            s = np.sqrt((r ** 2).sum())
            if s > 0:
                Z[j, m] = r / s
    return Z, mask.astype(float)


def zstat(Z, mask, x):
    """For every row: correlation of the ranked values with x over the
    row's finite entries, times sqrt(n - 1)."""
    n = mask.sum(axis=1)
    sx, sxx = mask @ x, mask @ (x ** 2)
    ss = sxx - sx ** 2 / np.maximum(n, 1)
    with np.errstate(all="ignore"):
        r = (Z @ x) / np.sqrt(np.maximum(ss, 1e-30))
        z = r * np.sqrt(np.maximum(n - 1, 0))
    z[(ss <= 1e-12) | (n < 5)] = 0.0
    return z


def main():
    meas, rows = {}, []
    for f in sorted(glob.glob(os.path.join(HERE, RES, "*.pkl"))):
        d = pickle.load(open(f, "rb"))
        meas.update(d["measures"])
        rows.extend(d["rows"])
    T = pd.DataFrame(rows)
    T = T[np.isfinite(T["p"])].reset_index(drop=True)
    ids = sorted(meas)
    V = np.array([[meas[i]["values"][lab] for lab in LABS] for i in ids], float)
    Mdf = pd.DataFrame({"id": ids, "family": [meas[i]["family"] for i in ids], "name": [meas[i]["name"] for i in ids],
                        "event_set": [meas[i]["event_set"] for i in ids], "classifier": [meas[i]["classifier"] for i in ids],
                        "variant": [meas[i]["variant"] for i in ids], "desc": [meas[i]["desc"] for i in ids], "unit": [meas[i]["unit"] for i in ids],
                        "n_finite": [meas[i]["n_finite"] for i in ids]})
    for k in ("rho_log_events", "rho_minutes", "rho_year", "rho_bad_contacts", "rho_band_contacts", "rho_blade_um"):
        Mdf[k] = [meas[i].get(k, np.nan) for i in ids]
    for j, lab in enumerate(LABS):
        Mdf[lab] = V[:, j]
    print("measures %d, tests %d" % (len(ids), len(T)), flush=True)
    # ---- Benjamini-Hochberg
    T["q_all"] = bh(T["p"].values)
    T["q_contrast"] = np.nan
    T["q_family"] = np.nan
    for c, idx in T.groupby("contrast").groups.items():
        T.loc[idx, "q_contrast"] = bh(T.loc[idx, "p"].values)
    for (fam, c), idx in T.groupby(["family", "contrast"]).groups.items():
        T.loc[idx, "q_family"] = bh(T.loc[idx, "p"].values)
    # ---- family-wise by shuffling the mouse labels, per contrast, over all measures at once
    pos = {i: k for k, i in enumerate(ids)}
    T["p_maxT"] = np.nan
    omni = {}
    rng = np.random.default_rng(11)
    for c, (take, x) in contrast_design().items():
        sub = T[T["contrast"] == c]
        if sub.empty:
            continue
        jj = np.array(sorted({pos[i] for i in sub["id"]}))
        Z, mask = rank_rows(V[np.ix_(jj, np.where(take)[0])])
        xs = x[take]
        zo = np.abs(zstat(Z, mask, xs))
        null_max = np.zeros(N_PERM)
        null_cnt = np.zeros(N_PERM)
        for b in range(N_PERM):
            zp = np.abs(zstat(Z, mask, rng.permutation(xs)))
            null_max[b] = zp.max()
            null_cnt[b] = (zp > 1.96).sum()
        null_max.sort()
        padj = 1.0 - np.searchsorted(null_max, zo - 1e-12, side="left") / float(N_PERM)
        look = dict(zip(jj, padj))
        T.loc[sub.index, "p_maxT"] = [look[pos[i]] for i in sub["id"]]
        omni[c] = {"n_measures": int(jj.size), "observed_over_1.96": int((zo > 1.96).sum()), "null_median": float(np.median(null_cnt)),
                   "null_95th": float(np.percentile(null_cnt, 95)), "p_more_hits_than_chance": float((null_cnt >= (zo > 1.96).sum()).mean()),
                   "strongest_z": float(zo.max()), "p_strongest": float((null_max >= zo.max() - 1e-12).mean())}
        print("%-26s measures %5d | |z|>1.96: %5d (shuffled: median %5.0f, 95th %5.0f; P = %.3f) | strongest P = %.3f" % (
            c, jj.size, omni[c]["observed_over_1.96"], omni[c]["null_median"], omni[c]["null_95th"], omni[c]["p_more_hits_than_chance"], omni[c]["p_strongest"]), flush=True)
    # ---- the same measure on the other event set, and across classifiers
    key_other = {}
    by_id = {(r.id, r.contrast): (r.p, r.effect) for r in T.itertuples()}
    p_o, s_o = [], []
    for r in T.itertuples():
        # the other event set; in the filter battery, the same measure under the DS filter (5-100 Hz)
        o_es = ("b_ds" if r.event_set != "b_ds" else None) if r.event_set.startswith("b_") else ("v8" if r.event_set == "v6" else "v6")
        other = "|".join([r.family, r.name, str(o_es), r.classifier, r.variant])
        hit = by_id.get((other, r.contrast))
        p_o.append(np.nan if hit is None else hit[0])
        s_o.append(np.nan if hit is None else float(np.sign(hit[1]) == np.sign(r.effect)))
    T["p_other_set"], T["same_sign_other_set"] = p_o, s_o
    grp = T.groupby(["family", "name", "variant", "contrast", "event_set"])
    T["n_variants"] = grp["p"].transform("size")
    T["_sgn"] = np.sign(T["effect"])
    T["_maj"] = grp["_sgn"].transform(lambda s: 1.0 if (s > 0).sum() >= (s < 0).sum() else -1.0)
    T["_same"] = (T["_sgn"] == T["_maj"]).astype(float)
    T["_hit"] = ((T["p"] < 0.05) & (T["_sgn"] == T["_maj"])).astype(float)
    T["share_same_sign"] = grp["_same"].transform("mean")
    T["share_p05"] = grp["_hit"].transform("mean")
    T = T.drop(columns=["_sgn", "_maj", "_same", "_hit"])
    conf = Mdf.set_index("id")[["rho_log_events", "rho_minutes", "rho_year", "rho_bad_contacts", "rho_band_contacts", "rho_blade_um", "desc", "unit", "n_finite"]]
    T = T.join(conf, on="id")
    os.makedirs(os.path.join(HERE, MERGED), exist_ok=True)
    T.to_pickle(os.path.join(HERE, MERGED, "tests.pkl"))
    Mdf.to_pickle(os.path.join(HERE, MERGED, "measures.pkl"))
    json.dump(omni, open(os.path.join(HERE, MERGED, "omnibus.json"), "w"), indent=1)
    print("\nraw P < 0.05: %d of %d (%.1f%%); < 0.01: %d; < 0.001: %d" % ((T.p < 0.05).sum(), len(T), 100 * (T.p < 0.05).mean(), (T.p < 0.01).sum(), (T.p < 0.001).sum()))
    print("q_all < 0.10: %d | q_contrast < 0.10: %d | q_family < 0.10: %d | p_maxT < 0.10: %d | p_maxT < 0.05: %d" % (
        (T.q_all < 0.10).sum(), (T.q_contrast < 0.10).sum(), (T.q_family < 0.10).sum(), (T.p_maxT < 0.10).sum(), (T.p_maxT < 0.05).sum()))
    return T, Mdf


if __name__ == "__main__":
    main()
