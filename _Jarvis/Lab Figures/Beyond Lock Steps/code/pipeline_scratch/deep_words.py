"""The captions and the per-mouse table that go with the three figures."""
import csv
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = r"c:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16"
FIN = pickle.load(open(os.path.join(HERE, "deep_final.pkl"), "rb"))
import deep_stats2 as D2
rows = D2.rename(FIN[6]["rows"])
fam = FIN["family"]
src = next(r for r in rows if r["key"] == "src_net")
qmin = min(min(r["q_group"], r["q_dose"]) for r in rows)
auc_p = float((FIN[6]["auc_null"] >= FIN[6]["auc"]).mean())
ko_p = float((FIN[6]["kofit_null"] >= FIN[6]["kofit"]).mean())
pw = FIN["power"]["PTEN 15%+ knockout"]

text = """Dentate spikes in PTEN-knockout and control mice
Halo set (Extraction Room v6): 4,824 events, 18 recordings, one per mouse. Statistics use the 17 recordings with 20 or more
events (control n = 8, PTEN n = 9). All tests two-sided; the unit is the mouse.

Figure 1 | Dentate spikes look alike in control and PTEN-knockout mice.
a, Mean dentate spike of one control mouse. Colour, current source density (blue, sink; red, source); lines, the mean local
field potential at each contact (50 µm apart). Depth is measured from the midpoint between the two blade sinks.
b, The same for every recording, +-20 ms around the spike and +-900 µm around the blade midpoint; each panel is scaled to its
own largest current. Bar colour: control (slate) or PTEN, darker with the %% of granule cells with knockout. n, events.

Figure 2 | DS1 and DS2 are separable in six of 17 recordings; the DS3 share depends on contact spacing.
a, b, Every event's current down the dentate at the spike, sorted by classifier score (DS1 blue bar, DS2 orange), and
the mean of each type (+- s.e.m.), in a recording where DS1 and DS2 are separable (a) and one where they are not (b).
c, DS1-DS2 separation index of the best of 15 classifiers per recording (1 - sink overlap between types / overlap within types;
selected blind to genotype).
d, Share of events classified as DS3 (relative-sink score within +-0.5, after Tarcsay et al. 2025) against the distance between
the outer and middle molecular layer contacts, for every recording under every classifier. The share falls from about
80%% at 50-100 µm to about 0%% at 200 µm and beyond: on a 50 µm probe it follows the spacing, not the mouse.
e, The six separable recordings: mean sink amplitude (+- s.e.m.) of DS1 and DS2 by depth in the analysed band, both on one
scale per recording. Dashed lines, the noise floor of each mean (99th percentile of the mean's |CSD| more than 30 ms from the
DS peak); ticks at the right, the sink centroid above the floor. DS1 is 7-16%% of events (median 8%%) and its peak sink is
0.28-0.54 times DS2's. Where DS1 clears its floor its sink lies at the outermost contacts of the band, 98-260 µm distal to
DS2's; the classifier sorts events by sink position, so this offset is partly a consequence of the classification.
f, DS1 peak sink over its noise floor (the larger of the two blades), by whether DS1 and DS2 are separable. No test is made.

Figure 3 | No measure differs between PTEN and control after correction; one exploratory association.
a, Fifteen pre-selected measures. Left, PTEN against control (rank-biserial effect); right, against the share of
granule cells knocked out, PTEN only (Spearman). Lines, 95%% bootstrap intervals; filled, P < 0.05 before correction. After
Benjamini-Hochberg correction over the %d tests the smallest q is %.2f. Leave-one-mouse-out logistic regression on all fifteen does not predict
genotype (area under the curve %.2f, permutation P = %.2f); leave-one-mouse-out ridge regression predicts %% knockout weakly
(rho = %.2f, permutation P = %.3f).
b, Mean CSD at the DS peak between the two blade sinks (depth normalised to the inter-sink distance; CSD normalised to
mean sink amplitude), by group (+- s.e.m.).
c, Exploratory: mean CSD between the blade sinks (a net source in controls) against %% knockout
(PTEN against control: rank-biserial %.2f, P = %.2f; within PTEN: rho = %.2f, P = %.3f; uncorrected).
d, Family-wise error. Across all %d tests on %d measures the minimum P is %.3f; in 1,000 permutations of the group labels
%.0f%% give a minimum P at least as small. The association in c is therefore exploratory.
A confirmatory test of control against PTEN with 15%% or more knockout (effect here d = %.2f) needs about %s mice a group for 80%% power.
""" % (2 * len(rows), qmin, FIN[6]["auc"], auc_p, FIN[6]["kofit"], ko_p, src["rb"], src["p_group"], src["rho"], src["p_dose"],
       fam["n_tests"], fam["n_measures"], fam["best"][1], 100 * fam["fw_p"], pw["d"], pw["need"])
open(os.path.join(OUT, "CAPTIONS.txt"), "w", encoding="utf-8").write(text)

M = FIN[6]["M"]
keys = ["lab", "g", "ko", "n"] + [r["key"] for r in rows] + ["best_si_method", "ds1_share_si"]
with open(os.path.join(OUT, "measures_per_mouse.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["mouse", "group", "knockout_pct", "events"] + [r["name"] for r in rows] + ["best classifier", "DS1 share under best classifier"])
    for m in M:
        w.writerow([("" if m.get(k) is None else (round(m[k], 4) if isinstance(m[k], float) else m[k])) for k in keys])
with open(os.path.join(OUT, "tests.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["measure", "rank_biserial", "ci_lo", "ci_hi", "P_group", "q_group", "rho_dose", "ci_lo", "ci_hi", "P_dose", "q_dose"])
    for r in rows:
        w.writerow([r["name"]] + [round(float(x), 4) for x in (r["rb"], r["rb_ci"][0], r["rb_ci"][1], r["p_group"], r["q_group"],
                                                               r["rho"], r["rho_ci"][0], r["rho_ci"][1], r["p_dose"], r["q_dose"])])
print(text)
