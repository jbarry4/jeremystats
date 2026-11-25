"""Package the AA story menu: merged PDF, pages, tables, code, README (as the DS story menu). Round 2: every headline at
one floor speed (a4_speed.py), raw results kept beside them."""
import glob
import gzip
import os
import pickle
import shutil

import pandas as pd
import pymupdf
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(os.path.dirname(HERE), "aa")
DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1_AA_Story_Menu_112326"
for sub in ("pages", "tables", "code", os.path.join("code", "map_v3")):
    os.makedirs(os.path.join(DEST, sub), exist_ok=True)

# ---- pages and the merged PDF (pages/ is rebuilt so a renamed page leaves no stale copy)
for f in glob.glob(os.path.join(DEST, "pages", "*")):
    os.remove(f)
pdfs = sorted(glob.glob(os.path.join(HERE, "out", "*.pdf")))
for f in pdfs + sorted(glob.glob(os.path.join(HERE, "out", "*.png"))):
    shutil.copy2(f, os.path.join(DEST, "pages", os.path.basename(f)))
doc = pymupdf.open()
for f in pdfs:
    with pymupdf.open(f) as d:
        doc.insert_pdf(d)
doc.set_metadata({"title": "KCNT1 active avoidance: a menu of stories the data support",
                  "subject": "KCNT1 AA story menu, first round, 2026-11-23 (round 2: one floor speed)", "author": "Barry Lab"})
doc.save(os.path.join(DEST, "KCNT1_AA_Story_Menu_112326.pdf"), garbage=3, deflate=True)
print(doc.page_count, "pages")

# ---- tables
A = pickle.load(open(os.path.join(HERE, "analysis.pkl"), "rb"))
B = pickle.load(open(os.path.join(HERE, "speed.pkl"), "rb"))
T = os.path.join(DEST, "tables")
for f in glob.glob(os.path.join(T, "*")):
    os.remove(f)
shutil.copy2(os.path.join(HERE, "tables", "per_mouse_values.csv"), os.path.join(T, "per_mouse_values.csv"))
for src, dst in (("per_session_values.csv", "per_session_values.csv.gz"),
                 ("per_session_values_speed_adjusted.csv", "per_session_values_at_one_floor_speed.csv.gz")):
    with open(os.path.join(HERE, "tables", src), "rb") as fi, gzip.open(os.path.join(T, dst), "wb") as fo:
        fo.write(fi.read())
shutil.copy2(os.path.join(HERE, "tables", "all_results.csv.gz"), os.path.join(T, "all_results_raw.csv.gz"))
shutil.copy2(os.path.join(HERE, "tables", "all_results_speed_adjusted.csv.gz"), os.path.join(T, "all_results_at_one_floor_speed.csv.gz"))
for f in ("mixed_models.csv", "circular.csv", "occupancy_bins.csv", "learners.csv", "validation_vs_trackanalysis.csv"):
    shutil.copy2(os.path.join(HERE, "tables", f), os.path.join(T, f.replace("mixed_models.csv", "mixed_models_raw.csv")))
shutil.copy2(os.path.join(HERE, "tables", "mixed_models_with_speed.csv"), os.path.join(T, "mixed_models_with_floor_speed.csv"))
shutil.copy2(os.path.join(HERE, "tables", "speed_slopes_per_mouse_measure.csv"), os.path.join(T, "floor_speed_slope_per_measure.csv"))
pm_adj = pd.DataFrame({k: pd.Series(v) for k, v in B["VALS_ADJ"].items()})
pm_adj.index.name = "mouse"
pm_adj.sort_index(key=lambda i: i.astype(int)).to_csv(os.path.join(T, "per_mouse_values_at_one_floor_speed.csv"))
rot = pd.Series(A["ROT"], name="floor_speed_deg_s")
rot.index.name = "mouse"
rot.to_csv(os.path.join(T, "floor_speed_per_mouse.csv"))
shutil.copy2(os.path.join(HERE, "rotation_by_day.json"), os.path.join(T, "floor_speed_by_day.json"))
shutil.copy2(os.path.join(HERE, "s0_voltage_check.csv"), os.path.join(T, "s0_shock_jump_check.csv"))
B["CIRC_ADJ"].to_csv(os.path.join(T, "circular_within_speed_bands.csv"), index=False)

GROUPS = [
    ("Genotype", lambda c: c in ("Het_vs_WT", "Hom_vs_WT", "Hom_vs_Het", "Mut_vs_WT", "GENO3")),
    ("Genotype within age", lambda c: any(c.endswith(s) for s in ("_young", "_old"))),
    ("Age", lambda c: c.startswith("young_vs_old") or c.startswith("age_corr")),
    ("Interaction and age-adjusted", lambda c: c.startswith("int_") or c.endswith("_adj_age")),
    ("Checks", lambda c: c in ("sex_F_vs_M", "year_2026_vs_2024", "injected_vs_not")),
]
cols = ["measure_words", "words", "p", "test", "effect", "n_a", "n_b", "mean_a", "mean_b", "median_a", "median_b", "rho", "n",
        "speed_slope", "speed_slope_p", "reached_a", "reached_b", "km_median_a", "km_median_b", "id", "contrast"]
RA, RR = B["RES_ADJ"], A["RES"]
xlsx = os.path.join(T, "results_P_below_0.05.xlsx")
with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
    readme = pd.DataFrame({"": [
        "Every per-mouse result with generous P < 0.05, one sheet per grouping (exploratory, uncorrected).",
        "All sheets but the last three are at one floor speed (%.2f deg/s, the median of the 56 mice): each mouse's value is "
        "moved to that speed along the slope floor speed has across all mice (value ~ genotype + speed), then the tests run "
        "on the moved values; a van Elteren test (Wilcoxon inside the slow / medium / fast speed bands) joins every genotype "
        "comparison. speed_slope: that slope per deg/s, speed_slope_p its P." % B["REF"],
        "measure_words: what was measured and how it was summarized per mouse (for example the day-2 mean of s9-s16).",
        "words: the contrast. 'X against Y' compares X with Y (Y is the reference; mean_a = Y, mean_b = X).",
        "p: the smallest P of the applicable tests; test: which test gave it. effect: Hedges g for two groups, Spearman rho for "
        "correlations, Kendall tau for WT / Het / Hom, the model coefficient for interaction rows, and the hazard ratio "
        "for the criterion (Cox with floor speed; log-rank inside speed bands).",
        "Habituation (s0) has the shock off: its shock, entrance and zone numbers are left out everywhere.",
        "Young = under 18 weeks at session 1. 'Raw, before speed' = the same tests without the speed adjustment.",
        "Mixed models over the sessions are on the 'Mixed models with speed' sheet; every row (any P) is in the csv.gz files.",
    ]})
    readme.to_excel(xw, sheet_name="Read me", index=False, header=False)
    for name, pred in GROUPS:
        s = RA[RA.contrast.map(pred) & (RA.p < 0.05)].sort_values("p")
        s[[c for c in cols if c in s.columns]].to_excel(xw, sheet_name=name, index=False)
    s = RR[(RR.p < 0.05)].sort_values("p")
    s[[c for c in cols if c in s.columns]].to_excel(xw, sheet_name="Raw, before speed", index=False)
    MM = B["MM_ADJ"]
    MM[MM.p < 0.05].sort_values("p")[["label", "model", "term", "coef", "p", "n_mice", "n_sessions", "transform", "formula"]].to_excel(
        xw, sheet_name="Mixed models with speed", index=False)
    pd.concat([A["CIRC"].assign(note="raw permutation"),
               B["CIRC_ADJ"].assign(note="labels swapped only inside a speed band")]).to_excel(xw, sheet_name="Circular", index=False)
wb = load_workbook(xlsx)
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for c in row:
            c.font = Font(name="Arial", size=9, bold=(c.row == 1 and ws.title != "Read me"))
            if c.row == 1 and ws.title != "Read me":
                c.fill = PatternFill("solid", fgColor="DCE6EC")
    if ws.title == "Read me":
        ws.column_dimensions["A"].width = 140
        for row in ws.iter_rows():
            row[0].alignment = Alignment(wrap_text=True, vertical="top")
    else:
        widths = {"measure_words": 60, "words": 44, "label": 40, "formula": 60, "model": 26, "term": 50}
        for j, c in enumerate(ws[1], 1):
            ws.column_dimensions[get_column_letter(j)].width = widths.get(c.value, 12)
        ws.freeze_panes = "A2"
wb.save(xlsx)

# ---- code (the analysis and page scripts; probes and one-off patches stay out)
for f in glob.glob(os.path.join(DEST, "code", "*.py")):
    os.remove(f)
for f in sorted(glob.glob(os.path.join(HERE, "*.py"))):
    b = os.path.basename(f)
    if b.startswith(("probe", "patch", "split")):
        continue
    shutil.copy2(f, os.path.join(DEST, "code", b))
for f in ("build3.py", "core.py", "gather.py", "headers.py", "newdata.py", "sexcheck.py", "shift.py", "shift2.py", "origin.py"):
    p = os.path.join(MAP, f)
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(DEST, "code", "map_v3", f))
shutil.copy2(os.path.join(HERE, "README.txt"), os.path.join(DEST, "README.txt"))
print("packaged into", DEST)
