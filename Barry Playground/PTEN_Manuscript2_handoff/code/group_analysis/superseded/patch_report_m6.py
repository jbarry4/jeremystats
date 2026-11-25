"""SUPERSEDED / NOT USED IN THE REPORT. One-off edit of the report text for the M6 decision.

Group comparisons use two-sided Mann-Whitney U tests (the `perm` function is overridden to call
scipy.stats.mannwhitneyu, per your decision); within-group comparisons use paired t-tests.
Run from any folder: the script changes to its working folder (work) itself.
"""
import os, sys
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,_ROOT)
from config import *
os.chdir(WORK)
p = WORK+'/report.md'
s = open(p).read()
R = []
def r(a, b):
    R.append((a, b))

# ---- front matter / summary
r('date: "November 16, 2026"', 'date: "November 17, 2026"')
r("by phase 10 they earn 5.5 rewards against 15.3 for WT (p = 0.004) while running faster.",
  "by phase 10 they earn 5.5 rewards against 15.2 for WT (p = 0.003) while running faster.")
r("Nothing at phases 7–9, and nothing in visible sessions.\n",
  "Nothing at phases 7–9, and nothing in visible sessions.\n"
  "- **Silencing KO cells with CNO.** Theta CSD (MML–GCL) fell by 28% after CNO (p = 0.004), most clearly in the high-KO mice. Goal-zone time rose in the high-KO mice after CNO, but not significantly. Neither measure tracks percent KO at baseline. WT CNO controls are still to be added.\n")

# ---- methods
r("| WT | 18 | 2, 4, 9, 21–26, 32, 46, 47, 51, 52, 54, 59, 60, 61 | 0 (assumed) |",
  "| WT | 18 (criterion), 19 (probes) | 2, 4, 6, 9, 21–26, 32, 46, 47, 51, 52, 54, 59, 60, 61 | 0 (assumed) |")
r("- **Exclusions.** M6 (WT, 27 sessions to criterion) and all Pten;Raptor dKO mice are excluded. M27 and M31 appear in pooled Pten KO numbers only.",
  "- **Exclusions.** M6 (WT) is excluded from sessions to criterion only, where it was an extreme outlier (27 sessions against 7–13 for every other WT mouse). It is included in all probe analyses, where its performance is within the WT range. All Pten;Raptor dKO mice are excluded. M27 and M31 appear in pooled Pten KO numbers only.")
r("- **Other labels.** Heterotopia: M8, M10, M27, M29, M30. IED+: M3, M5, M28, M34. IED−: M1, M7, M8, M10, M29, M30, M33. M27 and M31 were not recorded.",
  "- **Other labels.** Heterotopia: M8, M10, M27, M29, M30. IED+: M3, M5, M28, M34. IED−: M1, M7, M8, M10, M29, M30, M33. M27 and M31 were not recorded. IED labels are qualitative judgments of how obvious the pathological network activity was; more sensitive quantitative analyses are in progress, so IED− means \"no obvious IEDs\", not normal activity.")
r("- **Sources.** Sessions to criterion from `ROC_heterotopia_Fixed_hilo.sav`; probe data from `AllProbeSessions.sav`.",
  "- **Sources.** Sessions to criterion from `ROC_heterotopia_Fixed_hilo.sav`; probe data from `AllProbeSessions.sav`; theta CSD and CNO follow-up from `Data4Claude.xlsx`.")

# ---- visible section
r("| Rewards | 27.3 → 27.5 | 19.0 → 24.6 | 21.5 → 26.9 |\n| Proportion time in goal | 0.059 → 0.059 |",
  "| Rewards | 28.2 → 27.8 | 19.0 → 24.6 | 21.5 → 26.9 |\n| Proportion time in goal | 0.061 → 0.060 |")
r("| Rewards per entrance | 0.29 → 0.31 | 0.24 → 0.41 | 0.27 → 0.34 |\n| Goal entrances | 96.3 → 93.5 |",
  "| Rewards per entrance | 0.30 → 0.31 | 0.24 → 0.41 | 0.27 → 0.34 |\n| Goal entrances | 98.0 → 93.2 |")
r("| Mean speed (cm/s) | 10.7 → 10.1 | 9.4 → 7.9 | 10.3 → 9.4 |\n| Mean target speed (cm/s) | 11.5 → 11.5 |",
  "| Mean speed (cm/s) | 10.6 → 10.1 | 9.4 → 7.9 | 10.3 → 9.4 |\n| Mean target speed (cm/s) | 11.6 → 11.7 |")
r("| Proportion time in annulus | 0.66 → 0.66 | 0.66 → 0.70 | 0.65 → 0.68 |",
  "| Proportion time in annulus | 0.66 → 0.67 | 0.66 → 0.70 | 0.65 → 0.68 |")
r("No measure shows a significant main effect of group; goal entrances (p = 0.06) and rewards per entrance (p = 0.08) come closest. Group × phase is significant for rewards per entrance (p = 0.01) and time in center (p = 0.04), both driven by the Lo group changing across phases.",
  "No measure shows a significant main effect of group; goal entrances (p = 0.05) and rewards (p = 0.09) come closest. Group × phase is significant for rewards per entrance (p = 0.01) and time in center (p = 0.03), both driven by the Lo group changing across phases.")
r("- Phase 7: fewer rewards (19.0 vs 27.3, p = 0.04) and less time in center (p = 0.04).\n- Phase 8: more rewards per entrance (0.37 vs 0.29, p = 0.02) and slower (8.7 vs 10.2 cm/s, p = 0.04).",
  "- Phase 7: fewer rewards (19.0 vs 28.2, p = 0.03) and less time in center (p = 0.04).\n- Phase 8: slower (8.7 vs 10.2 cm/s, p = 0.04); more rewards per entrance (0.37 vs 0.30) falls short (p = 0.07).")
r("- Phase 10: fewer goal entrances (59 vs 93, p = 0.02), more rewards per entrance (0.48 vs 0.34, p = 0.006), slower (7.0 vs 9.7 cm/s, p = 0.03).",
  "- Phase 10: fewer goal entrances (59 vs 93, p = 0.01), more rewards per entrance (0.48 vs 0.34, p = 0.005), slower (7.0 vs 9.8 cm/s, p = 0.03).")

# ---- hidden section
r("| Rewards | 19.4 → 14.3 | 13.8 → 9.1 | 15.2 → 8.8 |\n| Proportion time in goal | 0.042 → 0.032 |",
  "| Rewards | 19.6 → 14.2 | 13.8 → 9.1 | 15.2 → 8.8 |\n| Proportion time in goal | 0.043 → 0.031 |")
r("| Goal entrances | 59.6 → 47.0 | 68.8 → 33.4 | 65.7 → 44.7 |\n| Mean speed (cm/s) | 8.3 → 8.2 |",
  "| Goal entrances | 60.2 → 47.1 | 68.8 → 33.4 | 65.7 → 44.7 |\n| Mean speed (cm/s) | 8.2 → 8.3 |")
r("| Mean target speed (cm/s) | 13.9 → 16.1 | 14.5 → 16.9 | 15.8 → 19.9 |\n| Proportion time in center | 0.015 → 0.012 |",
  "| Mean target speed (cm/s) | 13.7 → 16.2 | 14.5 → 16.9 | 15.8 → 19.9 |\n| Proportion time in center | 0.014 → 0.012 |")
r("| Proportion time in annulus | 0.65 → 0.68 | 0.66 → 0.68 | 0.67 → 0.73 |",
  "| Proportion time in annulus | 0.64 → 0.68 | 0.66 → 0.68 | 0.67 → 0.73 |")
r("Group is significant for rewards (p = 0.004), rewards per entrance (p = 0.004), time in goal (p = 0.04) and target speed (p = 0.04). Group × phase is not significant for any measure; mean speed and target speed come closest (both p = 0.10).",
  "Group is significant for rewards (p = 0.003), rewards per entrance (p = 0.004), time in goal (p = 0.03) and target speed (p = 0.04). Group × phase is not significant for any measure; mean speed (p = 0.09) and target speed (p = 0.11) come closest.")
r("Both KO groups already earn fewer rewards per entrance than WT (Lo 0.21, Hi 0.23, WT 0.34; p = 0.01 for each). Rewards are lower too, short of significance (Lo 13.8, Hi 15.2, WT 19.4; p = 0.06 and 0.14). So the hidden-goal deficit is present before any rotation.",
  "Both KO groups already earn fewer rewards per entrance than WT (Lo 0.21, Hi 0.23, WT 0.34; p = 0.009 for each). Rewards are lower too: significantly for Lo (13.8 vs 19.6, p = 0.04) and short of significance for Hi (15.2, p = 0.11). So the hidden-goal deficit is present before any rotation.")
r("Less time in goal at phase 9 (0.016 vs 0.034, p = 0.04).", "Less time in goal at phase 9 (0.016 vs 0.033, p = 0.04).")
r("- Rewards: 5.5 vs 15.3 (p = 0.004)\n- Rewards per entrance: 0.14 vs 0.33 (p = 0.005)\n- Time in goal: 0.017 vs 0.032 (p = 0.045)\n- Mean speed: 10.2 vs 7.8 cm/s (p = 0.02)\n- Target speed: 23.2 vs 16.6 cm/s (p = 0.009)",
  "- Rewards: 5.5 vs 15.2 (p = 0.003)\n- Rewards per entrance: 0.14 vs 0.32 (p = 0.007)\n- Time in goal: 0.017 vs 0.031 (p = 0.04)\n- Mean speed: 10.2 vs 7.9 cm/s (p = 0.03)\n- Target speed: 23.2 vs 16.6 cm/s (p = 0.008)")
r("On rewards per entrance, Lo mice match WT at phase 10 (0.31 vs 0.33).", "On rewards per entrance, Lo mice match WT at phase 10 (0.31 vs 0.32).")
r("the smallest q is 0.17 (Hi vs WT) and 0.28 (Lo vs Hi)", "the smallest q is 0.14 (Hi vs WT) and 0.28 (Lo vs Hi)")

# ---- phase effects
r("| Rewards | −26% | 0.007 | −34% | 0.03 | −42% | 0.02 |\n| Proportion time in goal | −24% | 0.01 | −49% | 0.003 | −44% | 0.05 |\n| Goal entrances | −21% | 0.05 | −51% | 0.008 | −32% | 0.07 |\n| Rewards per entrance | −9% | 0.28 | +26% | 0.25 | −6% | 0.78 |\n| Mean speed | −1% | 0.87 | −11% | 0.29 | +4% | 0.78 |\n| Mean target speed | +16% | 0.02 | +16% | 0.09 | +26% | 0.16 |\n| Proportion time in center | −19% | 0.42 | +38% | 0.37 | +23% | 0.60 |\n| Proportion time in annulus | +5% | 0.12 | +4% | 0.35 | +9% | 0.24 |",
  "| Rewards | −28% | 0.003 | −34% | 0.03 | −42% | 0.02 |\n| Proportion time in goal | −28% | 0.007 | −49% | 0.003 | −44% | 0.05 |\n| Goal entrances | −22% | 0.03 | −51% | 0.008 | −32% | 0.07 |\n| Rewards per entrance | −10% | 0.22 | +26% | 0.25 | −6% | 0.78 |\n| Mean speed | +1% | 0.85 | −11% | 0.29 | +4% | 0.78 |\n| Mean target speed | +18% | 0.01 | +16% | 0.09 | +26% | 0.16 |\n| Proportion time in center | −15% | 0.51 | +38% | 0.37 | +23% | 0.60 |\n| Proportion time in annulus | +6% | 0.06 | +4% | 0.35 | +9% | 0.24 |")
r("| Rewards | −1.1 | 0.15 | −1.4 | 0.16 | −2.9 | 0.003 |\n| Proportion time in goal | −0.002 | 0.13 |",
  "| Rewards | −1.2 | 0.10 | −1.4 | 0.16 | −2.9 | 0.003 |\n| Proportion time in goal | −0.003 | 0.07 |")
r("| Goal entrances | −3.5 | 0.13 | −11.3 | 0.001 |", "| Goal entrances | −3.3 | 0.14 | −11.3 | 0.001 |")
r("| Rewards per entrance | −0.004 | 0.78 | +0.024 | 0.28 |", "| Rewards per entrance | −0.007 | 0.61 | +0.024 | 0.28 |")
r("| Mean speed (cm/s) | −0.11 | 0.54 | −0.75 | 0.13 |", "| Mean speed (cm/s) | −0.05 | 0.77 | −0.75 | 0.13 |")
r("| Mean target speed (cm/s) | +0.90 | 0.09 | +0.30 | 0.49 |", "| Mean target speed (cm/s) | +0.93 | 0.06 | +0.30 | 0.49 |")
r("(rewards 13.1, 14.5, 15.3 across phases 8–10)", "(rewards 13.0, 14.3, 15.2 across phases 8–10)")

# ---- fig 8 table
r("| Rewards | 7–10 | −1.08 (0.15) | −1.42 (0.16) | **−2.90 (0.003)** | 0.82 | 0.18 |",
  "| Rewards | 7–10 | −1.19 (0.10) | −1.42 (0.16) | **−2.90 (0.003)** | 0.88 | 0.20 |")
r("| Rewards | 8–10 | +1.11 (0.20) | 0.00 (1.00) | −2.50 (0.12) | 0.52 | **0.04** |",
  "| Rewards | 8–10 | +1.11 (0.18) | 0.00 (1.00) | −2.50 (0.12) | 0.52 | **0.04** |")
r("| Rewards per entrance | 7–10 | −0.004 (0.78) | +0.024 (0.28) | **−0.023 (0.02)** | 0.32 | 0.42 |",
  "| Rewards per entrance | 7–10 | −0.007 (0.61) | +0.024 (0.28) | **−0.023 (0.02)** | 0.27 | 0.49 |")
r("| Rewards per entrance | 8–10 | +0.013 (0.52) | +0.019 (0.61) | −0.047 (0.18) | 0.91 | 0.14 |",
  "| Rewards per entrance | 8–10 | +0.008 (0.70) | +0.019 (0.61) | −0.047 (0.18) | 0.80 | 0.18 |")
r("| Proportion time in goal | 7–10 | −0.0025 (0.13) | **−0.0069 (0.004)** | **−0.0069 (0.03)** | 0.16 | 0.16 |",
  "| Proportion time in goal | 7–10 | −0.0030 (0.07) | **−0.0069 (0.004)** | **−0.0069 (0.03)** | 0.22 | 0.21 |")
r("| Proportion time in goal | 8–10 | +0.0014 (0.42) | −0.0031 (0.07) | −0.0045 (0.33) | 0.18 | 0.13 |",
  "| Proportion time in goal | 8–10 | +0.0015 (0.36) | −0.0031 (0.07) | −0.0045 (0.33) | 0.16 | 0.11 |")
r("| Target speed (cm/s) | 7–10 | +0.90 (0.09) | +0.30 (0.49) | **+2.13 (0.005)** | 0.52 | 0.19 |",
  "| Target speed (cm/s) | 7–10 | +0.93 (0.06) | +0.30 (0.49) | **+2.13 (0.005)** | 0.47 | 0.18 |")
r("| Target speed (cm/s) | 8–10 | +0.58 (0.46) | −1.02 (0.18) | +2.28 (0.07) | 0.29 | 0.26 |",
  "| Target speed (cm/s) | 8–10 | +0.47 (0.53) | −1.02 (0.18) | +2.28 (0.07) | 0.31 | 0.22 |")

# ---- visible phase effects
r("where WT are flat (+1%).", "where WT are flat (−1%).")
r("- **WT:** rewards per entrance rise slightly (0.016 per phase, p = 0.04).",
  "- **WT:** no significant trend on any visible measure; rewards per entrance rise slightly (0.014 per phase, p = 0.07).")

# ---- interpretation
r("about as often as WT (43 vs 48 entrances)", "about as often as WT (43 vs 49 entrances)")

# ---- caveats
r("- **M6.** The only basis visible in the data for excluding it is that it is an outlier. An independent reason would be stronger in the methods.",
  "- **M6.** It is excluded from sessions to criterion as an outlier and kept in the probe analyses. The only basis for the exclusion is its criterion score, so an independent reason would be stronger in the methods if there is one. Including it in the probes changes no main result; excluding it would move two single-phase comparisons across p = 0.05 (Lo vs WT rewards at hidden phase 7 and rewards per entrance at visible phase 8).")
r("- Theta, dentate spike and IED measures per mouse, to test whether circuit state explains the split within the Hi group.",
  "- Dentate spike and quantitative IED measures per mouse, to test whether circuit state explains the split within the Hi group.\n- WT mice given CNO (theta CSD and goal-zone time), to test whether the CNO effects are specific to silencing KO cells.\n- M33's percent KO: 8.82 in the earlier list and 4.41 in the CNO file. It is Lo either way, and neither value changes a conclusion.")

for a, b in R:
    n = s.count(a)
    assert n == 1, (n, a[:80])
    s = s.replace(a, b)
open(p, 'w').write(s)
print('applied', len(R))
