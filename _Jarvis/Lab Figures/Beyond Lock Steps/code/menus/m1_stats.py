"""Story menu, step 1: every per-mouse measure through every contrast of the three groupings,
with generous uncorrected P (stats_lib), plus the Root Canal measures (DS / in-between / IED classes
and their three numbers). Writes tables/all_results.csv and tables/per_mouse_values.csv.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stats_lib as S  # noqa: E402

BAT = S.BATTERY
TAB = os.path.join(HERE, "tables")
os.makedirs(TAB, exist_ok=True)
t0 = time.time()

# ------------------------------------------------------------------ battery measures
frames = []
for d in ("merged", "merged_around", "merged_filters"):
    m = pd.read_pickle(os.path.join(BAT, d, "measures.pkl"))
    m["source"] = d
    frames.append(m)
meas = pd.concat(frames, ignore_index=True)
labs_cols = [c for c in meas.columns if c.startswith("m") and c[1:].isdigit()]

# ------------------------------------------------------------------ Root Canal measures
rc = pd.read_pickle(os.path.join(HERE, "rc_events.pkl"))
KIND = {"ds": "DS", "halo_ds": "DS", "both": "TZ", "halo_amb": "TZ", "pspike": "IED", "halo_pspike": "IED", "neither": "far"}
rows = []


def add_rc(name, desc, unit, vals, event_set="v6"):
    r = {"id": "rootcanal|%s|%s||" % (name, event_set), "family": "rootcanal", "name": name, "event_set": event_set,
         "classifier": "", "variant": "", "desc": desc, "unit": unit, "source": "rootcanal"}
    r.update(vals)
    rows.append(r)


for wf, es in (("halo", "v6"), ("strict", "v8")):
    h = rc[rc.wf == wf].copy()
    h["kind"] = h.cls.map(KIND).fillna("none") if wf == "halo" else h.cls.map({"ds": "DS", "both": "TZ", "pspike": "IED", "neither": "far"}).fillna("none")
    ds = h[h.kind == "DS"]
    per = {}
    for lab in S.LABS:
        e = ds[ds.lab == lab]
        a = h[h.lab == lab]
        mins = S.M[lab]["dur_min"]
        n_all = max(int((a.kind.isin(["DS", "TZ", "IED"])).sum()), 1)
        per[lab] = {
            "ds_hf_median": e.hf.median(), "ds_hf_p90": e.hf.quantile(0.9), "ds_amp_median": e.amp.median(),
            "ds_hw_median": e.hw.median(), "ds_gb_median": e.gb.median(), "ds_gb_p10": e.gb.quantile(0.1),
            "ds_ga_median": e.ga.median(), "ds_hf_cv": e.hf.std() / abs(e.hf.mean()) if abs(e.hf.mean()) > 0 else np.nan,
            "ds_amp_cv": e.amp.std() / e.amp.mean(), "ds_hw_cv": e.hw.std() / e.hw.mean(),
            "tz_rate": (a.kind == "TZ").sum() / mins, "tz_share": 100.0 * (a.kind == "TZ").sum() / n_all,
            "ied_rate": (a.kind == "IED").sum() / mins, "ied_share": 100.0 * (a.kind == "IED").sum() / n_all,
            "far_rate": (a.kind == "far").sum() / mins, "ds_rate": (a.kind == "DS").sum() / mins,
        }
    words = {
        "ds_hf_median": ("High-frequency power (240-420 Hz) at the event, dB over its own baseline; median over the DS set", "dB"),
        "ds_hf_p90": ("High-frequency power at the event; 90th percentile over the DS set", "dB"),
        "ds_amp_median": ("Largest amplitude (10-150 Hz); median over the DS set", "uV"),
        "ds_hw_median": ("Half-width (10-150 Hz); median over the DS set", "ms"),
        "ds_gb_median": ("Distance to the IED border, in units of that border's size (1 = on it); median over the DS set", "border sizes"),
        "ds_gb_p10": ("Distance to the IED border; 10th percentile (the DS closest to the IED border)", "border sizes"),
        "ds_ga_median": ("Distance from the DS border's center (1 = on the border); median over the DS set", "border sizes"),
        "ds_hf_cv": ("High-frequency power; coefficient of variation over the DS set", ""),
        "ds_amp_cv": ("Largest amplitude; coefficient of variation over the DS set", ""),
        "ds_hw_cv": ("Half-width; coefficient of variation over the DS set", ""),
        "tz_rate": ("Borderline transients (BTs: inside both borders, or between the halos) per minute", "1/min"),
        "tz_share": ("Borderline transients as a % of DS + BT + IED events", "%"),
        "ied_rate": ("Events in the IED border (or captured by its halo) per minute", "1/min"),
        "ied_share": ("IED-border events as a % of DS + BT + IED events", "%"),
        "far_rate": ("Events outside both borders and both halos, per minute", "1/min"),
        "ds_rate": ("DS-set events per minute", "1/min"),
    }
    for k, (desc, unit) in words.items():
        add_rc(k, desc, unit, {lab: per[lab][k] for lab in S.LABS}, es)
rcm = pd.DataFrame(rows)
for lab in labs_cols:
    if lab not in rcm.columns:
        rcm[lab] = np.nan
meas = pd.concat([meas, rcm], ignore_index=True)
print("measures:", len(meas), "(battery %d, Root Canal %d)" % (len(meas) - len(rcm), len(rcm)), flush=True)

# ------------------------------------------------------------------ every contrast
recs = []
for k, r in enumerate(meas.itertuples(index=False)):
    rd = r._asdict()
    vals = {lab: rd.get(lab) for lab in S.LABS}
    for res in S.contrasts(vals):
        res.update({key: rd.get(key) for key in ("id", "family", "name", "event_set", "classifier", "variant", "desc", "unit", "source")})
        recs.append(res)
    if k % 1500 == 0:
        print(k, len(recs), "%.0f s" % (time.time() - t0), flush=True)
res = pd.DataFrame(recs)

# Strict check: the same measure on the Strict set (v8), same contrast
res["strict_id"] = res["id"].str.replace("|v6|", "|v8|", regex=False)
key = res.set_index(["id", "contrast"])
look = key[["p", "effect"]]
sp, se = [], []
for sid, cid, es in zip(res.strict_id, res.contrast, res.event_set):
    if es != "v6" or (sid, cid) not in look.index:
        sp.append(np.nan)
        se.append(np.nan)
        continue
    row = look.loc[(sid, cid)]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    sp.append(row["p"])
    se.append(row["effect"])
res["strict_p"] = sp
res["strict_effect"] = se
res["strict_agrees"] = (res.strict_p < 0.05) & (np.sign(res.strict_effect) == np.sign(res.effect))
res["strict_same_sign"] = np.sign(res.strict_effect) == np.sign(res.effect)
cols = ["grouping", "contrast", "words", "id", "family", "name", "event_set", "classifier", "variant", "desc", "unit", "p", "test",
        "effect", "hedges_g", "rank_biserial", "rho", "pearson_r", "tau", "eta2", "separated", "n", "n_a", "n_b", "mean_a", "mean_b",
        "median_a", "median_b", "means", "p_Mann-Whitney", "p_Welch t", "p_Student t", "p_Brunner-Munzel", "p_Spearman (exact)",
        "p_Spearman", "p_Pearson", "p_Kendall", "p_ANOVA", "p_Kruskal-Wallis", "p_ordered trend", "strict_p", "strict_effect",
        "strict_agrees", "strict_same_sign", "source"]
res = res[[c for c in cols if c in res.columns]].sort_values("p")
res.to_pickle(os.path.join(TAB, "all_results.pkl"))
res.to_csv(os.path.join(TAB, "all_results.csv"), index=False)
vals = meas[["id", "family", "name", "event_set", "classifier", "variant", "desc", "unit"] + S.LABS]
vals.to_pickle(os.path.join(TAB, "per_mouse_values.pkl"))
vals.to_csv(os.path.join(TAB, "per_mouse_values.csv"), index=False)
print("rows", len(res), "P<0.05:", int((res.p < 0.05).sum()), "  %.0f s" % (time.time() - t0))
for g in ["IED groups", "KO groups", "KO %", "PTEN vs control"]:
    s = res[res.grouping == g]
    print(g, "rows", len(s), "P<.05", int((s.p < 0.05).sum()), "P<.01", int((s.p < 0.01).sum()), "Strict agrees", int(s.strict_agrees.sum()))
