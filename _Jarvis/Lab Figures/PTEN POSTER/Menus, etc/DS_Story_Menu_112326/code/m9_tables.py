"""Round-3 tables (2026-11-23 evening), written into the menu's tables folder by m6_package.py:
  m7_outlier_tests.csv                 Grubbs and line outlier tests for m7 (fast power), and every contrast with and without m7
  CSD_common_scale_per_mouse.csv       Story 3: each mouse's DS current on one common scale, by DS-defined region and sink peak
  DS_BT_timing_around_IEDs.csv         Story 6e: observed over chance counts around IEDs, pooled and per mouse
  ML_heldout_calls_per_mouse.csv       Story 8: each PTEN mouse's held-out calls (IED status, knockout level) and its fast power
"""
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import menu_data as D  # noqa: E402
import outlier as O  # noqa: E402

DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\DS_Story_Menu_112326\tables"
os.makedirs(DEST, exist_ok=True)

# ---------------------------------------------------------------- m7 outlier tests (Story 1b)
v = D.values("rootcanal|ds_hf_median|v6||")
pt = [l for l in F.LABS if F.META[l]["group"] != "CTL"]
rows = []
for name, labs in (("among IED- mice", [l for l in pt if F.subgroup(l) == "IED-"]),
                   ("among high-knockout mice", [l for l in pt if F.kogroup(l) == "high KO"]),
                   ("among the 9 PTEN mice", pt), ("among all 16 mice", F.LABS)):
    g = O.grubbs({l: v[l] for l in labs}, "m7")
    rows.append({"test": "Grubbs, two-sided, " + name, "n": g["n"], "statistic": round(g["G"], 4), "critical_at_0.05": round(g["G_crit_05"], 4),
                 "p": g["p"], "m7_is_outlier_at_0.05": g["p"] < 0.05})
for name, labs in (("PTEN mice line (knockout %)", pt), ("all-mice line (knockout %, controls at 0)", F.LABS)):
    r = O.line_outlier([F.ko(l) for l in labs], [v[l] for l in labs], labs, "m7")
    rows.append({"test": "studentized deleted residual from the " + name, "n": r["n"], "statistic": round(r["t"], 4), "critical_at_0.05": np.nan,
                 "p": r["p"], "m7_is_outlier_at_0.05": r["p"] < 0.05})
T1, T2 = F.contrast_table(v), F.contrast_table(v, ("m7",))
for cid in T1:
    rows.append({"test": "contrast " + cid + " (" + T1[cid]["words"] + ")", "n": T1[cid].get("n", np.nan), "statistic": np.nan,
                 "critical_at_0.05": np.nan, "p": T1[cid]["p"], "m7_is_outlier_at_0.05": np.nan,
                 "test_used_with_m7": T1[cid]["test"], "effect_with_m7": T1[cid]["effect"],
                 "p_without_m7": T2.get(cid, {}).get("p", np.nan), "test_used_without_m7": T2.get(cid, {}).get("test", ""),
                 "effect_without_m7": T2.get(cid, {}).get("effect", np.nan)})
pd.DataFrame(rows).to_csv(os.path.join(DEST, "m7_outlier_tests.csv"), index=False)

# ---------------------------------------------------------------- common-scale CSD (Story 3)
UP = pickle.load(open(os.path.join(HERE, "uprof.pkl"), "rb"))
G, R, ref = UP["UGRID"], UP["regions"], UP["ref_ctl"]
cells = [("CA1", (G >= -1.0) & (G < R["top"])), ("upper_blade_distal", (G >= R["top"]) & (G < 0.0)),
         ("upper_blade_sink_peak", int(np.argmin(np.abs(G)))), ("upper_blade_proximal", (G >= 0.0) & (G < R["gu"])),
         ("hilus", (G >= R["gu"]) & (G < R["gl"])), ("lower_blade_proximal", (G >= R["gl"]) & (G < 1.0)),
         ("lower_blade_sink_peak", int(np.argmin(np.abs(G - 1.0)))), ("lower_blade_distal", (G >= 1.0) & (G < R["bot"]))]
rows = []
for lab in F.LABS:
    rec = UP["recs"][("v6", lab)]
    c = rec["u_peak_raw"] / ref
    row = {"mouse": lab, "group": F.subgroup(lab), "knockout_pct": F.ko(lab), "deepest_sink_over_control_average": rec["ref"] / ref,
           "own_landmarks_u_top": rec["u_top"], "own_landmarks_u_gu": rec["u_gu"], "own_landmarks_u_gl": rec["u_gl"], "own_landmarks_u_bot": rec["u_bot"]}
    for name, sel in cells:
        row["csd_" + name] = float(c[sel]) if isinstance(sel, int) else float(np.nanmean(c[sel]))
    rows.append(row)
df = pd.DataFrame(rows)
with open(os.path.join(DEST, "CSD_common_scale_per_mouse.csv"), "w", encoding="utf-8", newline="") as fh:
    fh.write("# CSD at the DS peak divided by one number for every mouse (the control average's deepest sink, so control = -1 "
             "there). Depth u: 0 = the mouse's upper-blade DS sink peak, 1 = its lower-blade sink peak. Regions use the median "
             "landmarks over 16 recordings: top %.3f, upper cell-layer source %.3f, lower cell-layer source %.3f, bottom %.3f.\n"
             % (R["top"], R["gu"], R["gl"], R["bot"]))
    df.to_csv(fh, index=False)

# ---------------------------------------------------------------- timing around IEDs (Story 6e)
TM = pickle.load(open(os.path.join(HERE, "timing.pkl"), "rb"))
rows = []
for k, word in (("DS", "DS"), ("TZ", "BT")):
    P = TM["pooled"][k]
    for i, w in enumerate(TM["windows"]):
        rows.append({"class": word, "mouse": "all five", "window_s": w, "observed": P["obs"][i], "chance_mean": P["null_mean"][i],
                     "ratio": P["ratio"][i], "p_more_than_chance": P["p"][i], "chance_band_lo": P["chance_lo"][i],
                     "chance_band_hi": P["chance_hi"][i], "ratio_band_lo_mice_redrawn": P["boot_lo"][i], "ratio_band_hi_mice_redrawn": P["boot_hi"][i]})
    for lab, mm in TM["mice"].items():
        r = mm[k]
        for i, w in enumerate(TM["windows"]):
            rows.append({"class": word, "mouse": lab, "window_s": w, "observed": r["obs"][i], "chance_mean": r["null_mean"][i],
                         "ratio": r["obs"][i] / r["null_mean"][i] if r["null_mean"][i] > 0 else np.nan, "p_more_than_chance": r["p"][i]})
pd.DataFrame(rows).to_csv(os.path.join(DEST, "DS_BT_timing_around_IEDs.csv"), index=False)

# ---------------------------------------------------------------- held-out calls (Story 8)
import pages_c as PC  # noqa: E402
ci, _ = PC.calls("r006", "iedpos_vs_iedneg")
ck, _ = PC.calls("r006", "low_vs_high")
rows = []
for lab in pt:
    rows.append({"mouse": lab, "group": F.subgroup(lab), "knockout_pct": F.ko(lab), "ds_fast_power_dB": v[lab],
                 "P_IEDplus_mean": np.mean(ci[lab]), "P_IEDplus_q25": np.percentile(ci[lab], 25), "P_IEDplus_q75": np.percentile(ci[lab], 75),
                 "n_IED_models": len(ci[lab]), "P_high_knockout_mean": np.mean(ck[lab]), "n_knockout_models": len(ck[lab])})
pd.DataFrame(rows).to_csv(os.path.join(DEST, "ML_heldout_calls_per_mouse.csv"), index=False)
print("round-3 tables written")
