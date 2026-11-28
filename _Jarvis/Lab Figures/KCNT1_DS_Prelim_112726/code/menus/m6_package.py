"""Story menu, last step: tables and the folder in Lab Figures (DS_Story_Menu_112326).
Run with the plain python for tables (pandas/openpyxl), then merge_pdf.py with miniconda's (PyMuPDF)."""
import glob
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DEST = os.environ.get("KOUT", "/gpfs2/scratch/sakhava1/kcnt1_prelim/out")
for sub in ("pages", "tables", "code"):
    os.makedirs(os.path.join(DEST, sub), exist_ok=True)

# pages
for f in sorted(glob.glob(os.path.join(HERE, "out", "*.*"))):
    shutil.copy2(f, os.path.join(DEST, "pages", os.path.basename(f)))

# tables
res = pd.read_pickle(os.path.join(HERE, "tables", "all_results.pkl"))
val = pd.read_pickle(os.path.join(HERE, "tables", "per_mouse_values.pkl"))
res.to_csv(os.path.join(DEST, "tables", "all_results.csv.gz"), index=False, compression="gzip")
val.to_csv(os.path.join(DEST, "tables", "per_mouse_values.csv.gz"), index=False, compression="gzip")
keep = ["contrast", "words", "id", "desc", "unit", "event_set", "classifier", "variant", "p", "test", "effect", "hedges_g", "rho",
        "separated", "mean_a", "mean_b", "n", "n_a", "n_b", "strict_p", "strict_agrees"]
sig = res[res.p < 0.05].copy()
sig["separated"] = sig["separated"].map({True: "yes", False: ""})
sig["strict_agrees"] = sig["strict_agrees"].map({True: "yes", False: ""})
with pd.ExcelWriter(os.path.join(DEST, "tables", "results_P_below_0.05.xlsx"), engine="openpyxl") as xw:
    readme = pd.DataFrame({"About": [
        "Every per-mouse measure (about 10,900) through every contrast of three groupings; rows with generous P < 0.05.",
        "Generous P: the smallest of the applicable tests (two groups: Mann-Whitney, Welch t, Student t; knockout %: Spearman "
        "exact for 9 mice, Pearson, Kendall; three groups: ANOVA, Kruskal-Wallis, ordered trend). No correction (exploratory).",
        "effect: Hedges g (two groups, + = second group higher), Spearman rho (knockout %), Kendall tau (three groups, ordered).",
        "separated: every value of one group beyond every value of the other.",
        "strict_p / strict_agrees: the same measure on the Strict event set, same contrast; agrees = P < 0.05 and the same sign.",
        "event_set v6 = Halo, v8 = Strict, b_* = the Halo events through another frequency filter (no Strict check).",
        "Groups: control m2 m21 m22 m26 m59 m60 m61; IED- m8 m33 m1 m7; IED+ m13 m28 m3 m5 m34; low KO m8 m33 m1; "
        "high KO m13 m28 m7 m3 m5 m34. m6 left out; m51 too few events.",
        "The full table (every P) is all_results.csv.gz; one number per mouse per measure is per_mouse_values.csv.gz."]})
    readme.to_excel(xw, sheet_name="read me", index=False)
    for g, name in (("IED groups", "IED groups"), ("KO groups", "KO groups"), ("KO %", "KO percent"), ("PTEN vs control", "PTEN vs control")):
        s = sig[sig.grouping == g].sort_values("p")[keep]
        s.to_excel(xw, sheet_name=name, index=False)
    for ws in xw.book.worksheets:
        ws.freeze_panes = "A2"
        for col in ws.columns:
            letter = col[0].column_letter
            ws.column_dimensions[letter].width = 14
        if ws.title != "read me":
            ws.column_dimensions["D"].width = 60
            ws.column_dimensions["C"].width = 40
        else:
            ws.column_dimensions["A"].width = 140

# BT and IED counts per mouse (Halo and Strict workflows)
import menu_data as D  # noqa: E402
import stats_lib as S  # noqa: E402
rc = D.rc()
rows = []
for lab in S.LABS:
    m = S.M[lab]
    h = rc[(rc.wf == "halo") & (rc.lab == lab)]
    ds = h[h.kind == "DS"]
    rows.append({"mouse": lab, "group": m["subgroup"], "knockout_pct": m["ko"], "minutes": round(m["dur_min"], 2),
                 "DS": int((h.kind == "DS").sum()), "BT": int((h.kind == "TZ").sum()), "IED": int((h.kind == "IED").sum()),
                 "outside_both": int((h.kind == "far").sum()),
                 "BT_per_min": round((h.kind == "TZ").sum() / m["dur_min"], 4), "IED_per_min": round((h.kind == "IED").sum() / m["dur_min"], 4),
                 "DS_fast_power_median_dB": round(ds.hf.median(), 3), "DS_amplitude_median_uV": round(ds.amp.median(), 1),
                 "DS_half_width_median_ms": round(ds.hw.median(), 3), "DS_distance_to_IED_border_median": round(ds.gb.median(), 4)})
pd.DataFrame(rows).to_csv(os.path.join(DEST, "tables", "BT_IED_and_fast_power_per_mouse.csv"), index=False)

# per-event features of DS, BTs and IEDs in the five IED+ sessions
ev = pd.concat([D.dsied()[lab]["events"] for lab in ("m13", "m28", "m3", "m5", "m34")], ignore_index=True)
ev["kind"] = ev["kind"].replace({"TZ": "BT"})
ev.rename(columns={"hf_rc": "fast_power_dB", "amp": "amplitude_uV", "hw": "half_width_ms", "gb": "distance_to_IED_border",
                   "ga": "distance_from_DS_border_center", "sink_rel": "deepest_sink_over_DS_mean", "t": "time_s"}, inplace=True)
ev.rename(columns={c: "fast_power_dB_" + c[3:] for c in ev.columns if c.startswith("hf_") and c != "hf_rc"}, inplace=True)
ev.to_csv(os.path.join(DEST, "tables", "DS_BT_IED_events_five_IEDplus_sessions.csv"), index=False)

# code
for f in ("m0_data.py", "m1_stats.py", "stats_lib.py", "m2_extract.py", "m3_profiles.py", "m4_dsied.py", "menu_data.py",
          "figlib.py", "pages_a.py", "pages_b.py", "pages_c.py", "m6_package.py", "merge_pdf.py", "m7_uprof.py", "m8_timing.py",
          "outlier.py", "m9_tables.py"):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(DEST, "code", f))
import m9_tables  # noqa: E402,F401  (writes the round-3 tables into DEST)
print("packaged to", DEST)
