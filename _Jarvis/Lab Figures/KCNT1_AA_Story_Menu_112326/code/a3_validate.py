"""Our .dat numbers against TrackAnalysis (Angelina's v2 run for 2026; Eli's workbook for 2024 and early 2026)."""
import json
import os
import re

import numpy as np
import openpyxl
import pandas as pd
from scipy import stats as st

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = r"C:\Users\Z390\Desktop\jeremystats\KCNT1 Active Avoidance"
TBL = os.path.join(BASE, "New Data", "active_avoidance_data", "KCNT1_2026", "analysis_output_112326_v2", "TBLfiles",
                   "2026_active_avoidance_output_112326_v2.tbl")
ELI = os.path.join(BASE, "DATA AND ARCHIVE", "KCNT1_AA_2024_thru_June26_outputs.xlsx")
SM = pd.read_csv(os.path.join(HERE, "session_metrics.csv"), dtype={"mouse": str})
U = SM[SM.use]
# TrackAnalysis columns by position (TBL) and by name (Eli's workbook)
POS = {"path": 3, "entr": 4, "lat": 5, "shocks": 9, "maxav": 15, "tt": 20, "pT": 21, "pCCW": 22, "pOPP": 23, "pCW": 24, "rl": 25}
NAMES = {"path": "total  _path [m]", "entr": "# of entr.", "lat": "time to first entr. [s]", "shocks": "# of  shocks ",
         "maxav": "max. time avoid. [s]  ", "tt": "Time TARG [s]", "pT": "pTime  TARG", "pCCW": "pTime  _CCW", "pOPP": "pTime  _OPP",
         "pCW": "pTime  _CW", "rl": "Rayleigh length [0-1]"}
rows = []
for line in open(TBL, encoding="latin-1").read().splitlines()[2:]:
    f = line.split("\t")
    if len(f) > 25 and f[0].strip().lower().endswith(".dat"):
        rows.append(dict(src="v2 TBL (2026)", file=f[0].strip(), **{"ta_" + k: float(f[i]) for k, i in POS.items()}))
ta = pd.DataFrame(rows)
m1 = ta.drop(columns=["src"]).merge(U, on="file", how="inner")
wb = openpyxl.load_workbook(ELI, data_only=True)["2024 + 2026 data"]
h = [c.value for c in wb[1]]
erows = []
for r in wb.iter_rows(min_row=2, values_only=True):
    if not r[1]:
        continue
    d = dict(src="Eli workbook", file=str(r[0]).strip(), mouse=str(r[1]), session=str(r[5]).strip("?"), day=r[6])
    for k, n in NAMES.items():
        try:
            d["ta_" + k] = float(r[h.index(n)])
        except (TypeError, ValueError):
            d["ta_" + k] = np.nan
    erows.append(d)
el = pd.DataFrame(erows)
el = el[el.session.str.fullmatch(r"\d+")]
el["session"] = el.session.astype(int)
U2 = U.copy()
U2["dayk"] = U2.day.astype(str)
el["dayk"] = el.day.astype(str).str.replace(".0", "", regex=False)
m2 = el.drop(columns=["file"]).merge(U2, on=["mouse", "session"], how="inner", suffixes=("", "_ours"))
m2 = m2[(m2.session == 0) | (m2.dayk == m2.dayk_ours)]
m2 = m2.drop(columns=["src"])
M = pd.concat([m1.assign(src="v2 TBL (2026)"), m2.assign(src="Eli workbook (2024 + early 2026)")], ignore_index=True)
M = M.drop_duplicates(subset=["src", "mouse", "session"])
PAIRS = [("shocks", "shocks", "Shocks"), ("entr", "entrances", "Entrances"), ("lat", "latency_first_entrance_s", "Time to first entrance (s)"),
         ("maxav", "max_avoid_s", "Longest time without an entrance (s)"), ("path", "path_m", "Path (m)"),
         ("tt", "time_in_zone_angle_pct", "Time in the zone"), ("pT", "zone_T", "Share of quadrant time in the zone"),
         ("pCW", "zone_CW", "Share in the CW quadrant"), ("pOPP", "zone_OPP", "Share in the opposite quadrant"), ("rl", "R", "Rayleigh length / R")]
out = []
for src, g in M.groupby("src"):
    for a, b, lab in PAIRS:
        x, y = g["ta_" + a].astype(float).values, g[b].astype(float).values
        if a == "tt":
            y = y * 6.0          # % of 600 s -> s
        ok = np.isfinite(x) & np.isfinite(y)
        x, y = x[ok], y[ok]
        rec = dict(source=src, measure=lab, n=int(ok.sum()), spearman=float(st.spearmanr(x, y).statistic),
                   median_ours_minus_TA=float(np.median(y - x)), exact_share=float(np.mean(np.isclose(x, y, atol=0.5 if a in ("shocks", "entr") else 0.02 * max(np.median(np.abs(x)), 1e-9)))),
                   ours_mean=float(np.mean(y)), TA_mean=float(np.mean(x)))
        out.append(rec)
V = pd.DataFrame(out)
os.makedirs(os.path.join(HERE, "tables"), exist_ok=True)
V.to_csv(os.path.join(HERE, "tables", "validation_vs_trackanalysis.csv"), index=False)
M.to_csv(os.path.join(HERE, "validation_pairs.csv"), index=False)
pd.set_option("display.width", 200)
print(V.round(3).to_string())
print("matched sessions:", M.groupby("src").size().to_dict())
