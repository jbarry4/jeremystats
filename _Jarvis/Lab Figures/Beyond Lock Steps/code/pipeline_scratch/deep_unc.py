"""The raw tests, no correction: the 15 chosen measures and all 240."""
import csv
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deep_stats2 as D2  # noqa: E402

OUT = r"c:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\uncorrected"
os.makedirs(OUT, exist_ok=True)
FIN = pickle.load(open(os.path.join(HERE, "deep_final.pkl"), "rb"))
rows = D2.rename(FIN[6]["rows"])
with open(os.path.join(OUT, "tests_15_measures_UNCORRECTED.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["measure", "PTEN vs control: rank-biserial", "P (Mann-Whitney)", "n control", "n PTEN",
                "vs % knockout, PTEN only: Spearman rho", "P", "vs % knockout, all mice: rho", "P"])
    for r in sorted(rows, key=lambda r: min(r["p_group"], r["p_dose"])):
        w.writerow([r["name"], round(r["rb"], 3), round(r["p_group"], 4), r["na"], r["nb"], round(r["rho"], 3), round(r["p_dose"], 4),
                    round(r["rho_all"], 3), round(r["p_all"], 4)])
M = FIN[6]["M"]
keys = sorted({k for m in M for k, v in m.items() if isinstance(v, (int, float)) and k not in ("ko", "n")})
T = D2.tests_of(M, keys)
WORD = {"group": "PTEN vs control (Mann-Whitney; effect = difference of medians)", "dose": "vs % knockout, PTEN only (Spearman rho)",
        "all": "vs % knockout, all mice, controls at 0 (Spearman rho)"}
with open(os.path.join(OUT, "tests_all_240_UNCORRECTED.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["measure (script name)", "test", "effect", "P"])
    for (kind, key), (pv, eff) in sorted(T.items(), key=lambda kv: kv[1][0]):
        w.writerow([key, WORD[kind], round(float(eff), 4), round(float(pv), 5)])
sig15 = [(r["name"], "group", r["p_group"]) for r in rows if r["p_group"] < 0.05] + [(r["name"], "dose", r["p_dose"]) for r in rows if r["p_dose"] < 0.05]
n05 = sum(1 for v in T.values() if v[0] < 0.05)
txt = """UNCORRECTED. Every P value in this folder is raw: no correction for the number of tests.
Halo set (Extraction Room v6), one recording per mouse, 17 recordings with 20 or more events (control n = 8, PTEN n = 9).
Two-sided tests. PTEN against control: Mann-Whitney. Against %% knockout: Spearman.

Fig1, Fig2: as in the parent folder (they carry no corrected statistic).
Fig3: panels a-c only; the chance-level panel is left out.

Of the 15 chosen measures (30 tests), P < 0.05 in %d:
%s
Of all 240 tests on 83 measures, P < 0.05 in %d (12 expected by chance alone).
""" % (len(sig15), "\n".join("  %s, %s: P = %.3f" % (a, "PTEN against control" if b == "group" else "against knockout within PTEN", c)
                             for a, b, c in sorted(sig15, key=lambda x: x[2])), n05)
open(os.path.join(OUT, "READ_ME_UNCORRECTED.txt"), "w", encoding="utf-8").write(txt)
print(txt)
