---
title: "Pten KO mosaicism and spatial accuracy: a behavioural interrogation"
subtitle: "Version 3"
date: "November 24, 2026"
---

# Summary

Mosaic Pten deletion does not produce one deficit that worsens with dose. It produces two
different phenotypes, and the axis separating them is reliance on the cue against reliance on the
place. Low load gives a mouse that is slow to take up the cue rule but knows where things are.
High load gives a mouse that takes the rule up readily and then cannot function without it.

| | Pten KO Lo (< 15% KO, n = 5) | Pten KO Hi (≥ 15% KO, n = 6) |
|---|---|---|
| Learning the cue→reward rule | Acquires it, least readily of the three — 21.2 vs 8.8 sessions (p < 0.001, no overlap with WT) | Acquires it more readily than Lo — 14.0 sessions (p = 0.03 vs WT), median 11.5, inside the WT range |
| Place preference with a cue present | Intact — +12.0 points (p = 0.016) | Absent — −4.2 points (p = 0.58) |
| Speed through the reward window | Like WT | **16.4 vs 11.5 cm/s at hidden phase 10 (p < 0.001)**; unchanged at phase 7 and when cued |
| Decelerating at the hidden goal | Like WT | Braking on 38% of runs against 56% (p = 0.045); the change on removing the cue is twice WT's (p = 0.021) |
| Dwelling at the hidden goal | Pauses the most of any group | 59 s against 134 s per session (p = 0.006) |
| Searching the places that used to pay | Scales with the set, like WT | Does not — group × phase p = 0.003, and p = 0.198 when cued |
| Change across the four rotations | Goal time falls (p = 0.004) | Rewards −2.9 per phase (p = 0.003), target speed +2.1 cm/s (p = 0.005); cued slopes flat |
| What they do instead | Search hard, aim badly | Run — they speed up when the marker is removed (p = 0.001) |

**What is new in this version.** Three things changed the account rather than adding to it.

1. **Speed through the reward window, on every entry.** Locking the speed profile to the moment of
   entry and including chance crossings as well as directed runs gives the largest arrival effect
   in the report: at hidden phase 10 the Hi mice are moving at 16.4 cm/s through the 1.2 s window
   that earns a pellet, against 11.5 in WT (p = 0.0005). The same comparison at the trained
   location and in the cued session gives p = 0.18. This is "running through the goal", measured.
2. **The shape of the approach is normal.** With each run scaled to its own approach maximum, the
   speed profile against distance from the goal does not differ between groups: a permutation test
   across the whole profile with max-statistic correction gives p = 0.53, and the within-animal
   hidden-minus-cued version p = 0.83. The deficit is not in getting there or in aiming; it is at
   and after arrival.
3. **The cued sessions are flat.** Every slope that falls across the four hidden rotations is flat
   when the goal is marked, in the same mice (Figure 4). The decline is a response to the rotation,
   not drift across days.

**The within-animal control.** Every claim above survives the comparison that matters most: the
same mouse, the same phase, the same arena, with and without the marker. Hi mice pause less when
the cue is removed while WT mice pause more (change p = 0.043), their braking at the goal falls
twice as far (p = 0.021), and they speed up where WT mice slow down (p = 0.001).

**Dose.** Percent KO does not order the groups. The slowest learners have the fewest KO cells, and
there are no mice between 9.5% and 20.2%, so the Lo/Hi split carries what percent KO carries.

# Part I — The behavioural interrogation

## 1. Cohort, groups and methods

| Group | n | Mice | % KO (cell layer) |
|---|---|---|---|
| WT | 18 (criterion), 19 (probes) | 2, 4, 6, 9, 21–26, 32, 46, 47, 51, 52, 54, 59, 60, 61 | 0 (assumed) |
| Pten KO Lo | 5 | 1, 8, 10, 30, 33 | 3.9–9.5 |
| Pten KO Hi | 6 | 3, 5, 7, 28, 29, 34 | 20.2–28.4 |
| Pten KO, no histology | 2 | 27, 31 | unknown |

- **Exclusions.** M6 (WT) is excluded from sessions to criterion only, where it was an extreme outlier (27 sessions against 7–13 for every other WT mouse). It is included in all probe analyses, where its performance is within the WT range. All Pten;Raptor dKO mice are excluded. M27 and M31 appear in pooled Pten KO numbers only.
- **KO level.** Percent of granule cells in the cell layer; KO cells outside the layer are not counted.
- **Other labels.** Heterotopia: M8, M10, M27, M29, M30. IED+: M3, M5, M28, M34. IED−: M1, M7, M8, M10, M29, M30, M33. M27 and M31 were not recorded. IED labels are qualitative judgments of how obvious the pathological network activity was; more sensitive quantitative analyses are in progress, so IED− means "no obvious IEDs", not normal activity.
- **Sources.** Sessions to criterion from `ROC_heterotopia_Fixed_hilo.sav`; probe data from `AllProbeSessions.sav`; theta CSD from `CSD_sansM2.sav` and CNO behavior from `AllProbeSessions_CNO.sav` (see the theta CSD section); time in each of the four candidate goal zones from `AllProbes_ByGZLocation.sav`.
- **Probe design.** Phase 7 is the trained goal location; phases 8, 9 and 10 are successive novel locations. Each phase has a visible session and a hidden session. Target speed (`MeanTargSpeed` in the PlaceAccuracy output) is speed in the goal zone: running speed as the mouse enters and moves through the zone, not speed on the way to it.
- **Group comparisons.** Two-sided Mann-Whitney U tests throughout, for every comparison between groups (Lo vs WT, Hi vs WT, Lo vs Hi, pooled Pten KO vs WT, IED+ vs IED−), on single-phase values, trained-to-novel changes and per-mouse slopes. Mann-Whitney compares ranks, so it does not assume normal data and is less sensitive to single extreme mice. For sessions to criterion, Welch t-tests and permutation tests are shown alongside.
- **Within-group tests.** Paired t-tests (and sign-flip tests where stated). A Wilcoxon signed-rank test cannot give p below 0.0625 with five mice, so it is not used for the KO groups.
- **Phase effects.** Within each group: trained (phase 7) vs the mean of the novel phases (paired t-test), and the per-mouse linear slope across phases 7–10 tested against zero. Across groups: a mixed model with mouse as a random effect, testing group and group × phase.
- **Multiple comparisons.** Probe p-values are uncorrected unless stated. Where a corrected value (q) is given it is Benjamini-Hochberg across the 64 variable × condition × phase tests.
- **Values** are mean ± SE.

## 2. Can they learn the cue–reward association?

Sessions to criterion measures how long a mouse takes to learn that **the visible cue in the goal zone predicts reward**. It is a cue–reward association, not a place task: the goal is marked, and a mouse that approaches the marker and stays there is rewarded whether or not it has any idea where the marker is in the room. That matters for reading the numbers below, because the group that looks worst here is not the group that is worst at the task this report is about.

Lo KO mice needed more than twice as many sessions as WT to learn the cued task, and every Lo mouse was slower than every WT mouse. Three-group Kruskal-Wallis: H = 14.47, p < 0.001.


| Group | n | Mean ± SE | Median | Range |
|---|---|---|---|---|
| WT | 18 | 8.8 ± 0.5 | 8 | 7–13 |
| Pten KO Hi | 6 | 14.0 ± 2.8 | 11.5 | 8–25 |
| Pten KO Lo | 5 | 21.2 ± 2.1 | 21 | 15–28 |
| All Pten KO | 13 | 17.3 ± 2.0 | 19 | 8–28 |

| Comparison | Difference (sessions) | Mann-Whitney p | Welch t p | Permutation p | Hedges g |
|---|---|---|---|---|---|
| Lo vs WT | +12.4 | <0.001 | 0.003 | <0.001 | 4.3 |
| Hi vs WT | +5.2 | 0.03 | 0.12 | 0.01 | 1.4 |
| Lo vs Hi | +7.2 | 0.08 | 0.07 | 0.08 | 1.1 |
| All Pten KO vs WT | +8.5 | <0.001 | 0.001 | <0.001 | 1.7 |

- **Hi KO is split.** Three Hi mice (8, 9, 9 sessions) sit inside the WT range and three (14, 19, 25) do not. That is why the Welch t-test disagrees with the rank and permutation tests. IED status does not sort them: the IED+ Hi mice took 8, 9, 14 and 19 sessions, the IED− Hi mice 9 (M7) and 25 (M29).
- **A count model agrees in direction.** Hi takes 1.6× as many sessions as WT (p = 0.001), Lo 2.4× (p < 0.001), and Lo 1.5× as many as Hi (p = 0.008). Group variances differ (Levene p = 0.02), so these p-values are optimistic.
- **The two mice without histology decide Lo vs Hi.** M27 took 8 sessions and M31 took 27. If M27 is Hi and M31 is Lo, Lo vs Hi reaches p = 0.03; the reverse gives p = 0.47.

### ROC: sessions to criterion as a classifier

Each subtype is classified against all other mice, WT included.

| Subtype | n | AUC | 95% CI | p | Cutoff | Sens. | Spec. |
|---|---|---|---|---|---|---|---|
| Any Pten KO | 13 / 18 | 0.87 | 0.72–0.97 | <0.001 | ≥14 | 0.69 | 1.00 |
| Pten KO Lo | 5 / 24 | 0.96 | 0.87–1.00 | 0.001 | ≥15 | 1.00 | 0.92 |
| Pten KO, IED− | 7 / 22 | 0.94 | 0.80–1.00 | <0.001 | ≥15 | 0.86 | 0.95 |
| Heterotopia | 5 / 26 | 0.84 | 0.59–1.00 | 0.02 | ≥20 | 0.80 | 0.92 |
| Pten KO Hi | 6 / 23 | 0.66 | 0.43–0.86 | 0.23 | none useful | | |
| Pten KO, IED+ | 4 / 25 | 0.61 | 0.37–0.83 | 0.52 | none useful | | |

Slow acquisition identifies the Lo KO, IED− and heterotopia mice in the population; it does not identify Hi KO or IED+ mice. Within Pten KO mice only, Lo vs Hi gives AUC 0.83 (p = 0.08) and heterotopia vs none gives 0.69 (p = 0.30).

### Sessions to criterion and percent KO

More KO does not mean slower learning: the slowest mice have the fewest KO cells. The data form two clusters with a gap between them, so percent KO adds little beyond the Lo/Hi split.


| Analysis | n | Result |
|---|---|---|
| % KO vs sessions, Pten KO only (Pearson) | 11 | r = −0.52, 95% CI −0.85 to 0.12, p = 0.10 |
| % KO vs sessions, Pten KO only (Spearman) | 11 | ρ = −0.46, p = 0.15 |
| Within Lo cluster | 5 | r = 0.14, p = 0.83 |
| Within Hi cluster | 6 | r = 0.04, p = 0.94 |
| Linear fit, WT at 0% | 29 | R² = 0.13 |
| Quadratic fit, WT at 0% | 29 | R² = 0.46; quadratic term p < 0.001 |

- **The slope is about −0.36 sessions per 1% KO** among Pten KO mice, and no single mouse drives it (leave-one-out r from −0.43 to −0.65).
- **All of the relationship is the step between clusters.** Within either cluster, percent KO explains nothing.
- **The inverted-U depends on the WT mice counting as 0% KO.** Its fitted peak falls near 14%, inside the range with no mice, so the peak location reflects the curve's shape and not an observation.
- **Percent KO does predict IEDs.** Every IED+ mouse has at least 20% KO and no mouse below 20% is IED+ (AUC 0.98 against all other mice, p < 0.001). Two Hi mice are IED− (M7, M29). In the CSD cohort, M13 is IED+ at 18.9% KO, so the 20% figure is specific to the behavior cohort (Figure 21).
- **Heterotopia runs the other way.** Three of five Lo mice have a heterotopia against one of six Hi mice. Heterotopia mice averaged 20.4 sessions and other Pten KO mice 15.4 (p = 0.30).

Low KO, heterotopia and IED− status therefore travel together in this cohort, and these data cannot say which one is responsible for slow acquisition.

![](figsv3/fig01_learning.svg){width=6.9in}

*Figure 1. Learning the cue rule. **a** Sessions to criterion, each point one mouse, group mean ± SE; M6 (WT, 27 sessions) excluded; brackets are Mann-Whitney tests. **b** Sessions to criterion against percent KO: the slowest learners have the fewest KO cells. The quadratic describes that shape and is not a dose model — the mice fall in two clusters with a gap between them. IED+ and heterotopia mice are labelled. **c** The two measures that separate the groups, against each other: sessions to criterion and the latent place preference with the cue present (Figure 5b). Diamonds mark IED+ mice.*

## 3. The task, and the measures that missed it

Before any of the fine-grained analysis, this is what the task looks like and what the session
measures say about it. The three example mice are the same throughout: M22 (WT), M33 (Pten KO Lo,
8.8% KO) and M34 (Pten KO Hi, 28.4% KO, IED+). With the marker present all three run to the goal
at every phase and collect rewards (Figure 2). With it removed the picture changes, and the four
session measures change with it (Figure 3) — but, as the rest of Part I shows, what they change by
understates what is happening at the goal.

![](figsv3/fig02_visible.svg){width=6.9in}

*Figure 2. Visible goal sessions. Left: the three example mice, phase by phase; grey is the full 30-minute path, coloured the 3 s before each reward, black dots where the reward was triggered; circles mark the current goal (solid), the previous goal (dashed), the trained goal (dotted) and zones not yet used (light grey). Arenas are drawn in the room view, so the phase 7 goal sits in the upper right quadrant and the later goals follow anti-clockwise. Right: the four session measures by phase, mean ± SE across mice; letters mark uncorrected p < 0.05 at that phase (L = Lo vs WT, H = Hi vs WT, × = Lo vs Hi).*

### Probe sessions: visible goal

With the cue present, neither KO group is clearly impaired at reaching the goal, and neither gets worse as the goal rotates. The consistent difference is that Lo KO mice move less: slower, fewer goal entrances, but more rewards per entrance.


Each cell shows the trained phase (7) → the mean of the novel phases (8–10).

| Measure | WT | Pten KO Lo | Pten KO Hi |
|---|---|---|---|
| Rewards | 28.2 → 27.8 | 19.0 → 24.6 | 21.5 → 26.9 |
| Proportion time in goal | 0.061 → 0.060 | 0.052 → 0.052 | 0.051 → 0.058 |
| Rewards per entrance | 0.30 → 0.31 | 0.24 → 0.41 | 0.27 → 0.34 |
| Goal entrances | 98.0 → 93.2 | 80.8 → 63.6 | 84.3 → 84.6 |
| Mean speed (cm/s) | 10.6 → 10.1 | 9.4 → 7.9 | 10.3 → 9.4 |
| Mean target speed (cm/s) | 11.6 → 11.7 | 11.5 → 11.0 | 12.4 → 13.1 |
| Proportion time in center | 0.013 → 0.012 | 0.006 → 0.014 | 0.011 → 0.011 |
| Proportion time in annulus | 0.66 → 0.67 | 0.66 → 0.70 | 0.65 → 0.68 |

**Overall group effects (mixed model across phases).** No measure shows a significant main effect of group; goal entrances (p = 0.05) and rewards (p = 0.09) come closest. Group × phase is significant for rewards per entrance (p = 0.01) and time in center (p = 0.03), both driven by the Lo group changing across phases.

**Lo KO vs WT, by phase (uncorrected).**

- Phase 7: fewer rewards (19.0 vs 28.2, p = 0.03) and less time in center (p = 0.003).
- Phase 8: fewer goal entrances (69 vs 90) falls short (p = 0.06).
- Phase 9: fewer goal entrances (63 vs 96, p = 0.03), slower (8.0 vs 10.3 cm/s, p = 0.03) and more time in center (p = 0.02).
- Phase 10: fewer goal entrances (59 vs 93, p = 0.02), more rewards per entrance (0.48 vs 0.34, p = 0.02), slower (7.0 vs 9.8 cm/s, p = 0.02).

**Hi KO vs WT, by phase.** No difference in 32 tests; the nearest is fewer rewards at phase 7 (21.5 vs 28.2, p = 0.09).

**Lo vs Hi, by phase.** No difference at any phase on any measure (all p ≥ 0.08).

The trained-location rewards for Lo KO mice (19.0) sit just under the 20-reward criterion, which fits with their slow acquisition reflecting low activity as much as poor learning. That reading is an interpretation; the data do not separate the two.

![](figsv3/fig03_hidden.svg){width=6.9in}

*Figure 3. Hidden goal sessions. Same conventions as Figure 2.*

### Probe sessions: hidden goal

Both KO groups are impaired without the cue, and they are impaired to the same degree on average. They separate from each other only at the last probe, when the Hi KO mice collapse.


Each cell shows the trained phase (7) → the mean of the novel phases (8–10).

| Measure | WT | Pten KO Lo | Pten KO Hi |
|---|---|---|---|
| Rewards | 19.6 → 14.2 | 13.8 → 9.1 | 15.2 → 8.8 |
| Proportion time in goal | 0.043 → 0.031 | 0.038 → 0.020 | 0.039 → 0.022 |
| Rewards per entrance | 0.34 → 0.31 | 0.21 → 0.27 | 0.23 → 0.22 |
| Goal entrances | 60.2 → 47.1 | 68.8 → 33.4 | 65.7 → 44.7 |
| Mean speed (cm/s) | 8.2 → 8.3 | 8.1 → 7.2 | 9.1 → 9.5 |
| Mean target speed (cm/s) | 13.7 → 16.2 | 14.5 → 16.9 | 15.8 → 19.9 |
| Proportion time in center | 0.014 → 0.012 | 0.012 → 0.016 | 0.009 → 0.011 |
| Proportion time in annulus | 0.64 → 0.68 | 0.66 → 0.68 | 0.67 → 0.73 |

**Overall group effects (mixed model across phases).** Group is significant for rewards (p = 0.003), rewards per entrance (p = 0.004), time in goal (p = 0.03) and target speed (p = 0.04). Group × phase is not significant for any measure; mean speed (p = 0.09) and target speed (p = 0.11) come closest.

**At the trained location (phase 7).** Both KO groups already earn fewer rewards per entrance than WT (Lo 0.21, Hi 0.23, WT 0.34; p = 0.008 and 0.006). Rewards are lower too: significantly for Lo (13.8 vs 19.6, p = 0.02) and short of significance for Hi (15.2, p = 0.16). So the hidden-goal deficit is present before any rotation.

**Lo KO vs WT at novel locations.** Less time in goal at phase 9 (0.016 vs 0.033, p = 0.01) and phase 10 (0.018 vs 0.031, p = 0.02). At phase 10, fewer rewards (9.6 vs 15.2, p = 0.054) and fewer goal entrances (32 vs 49, p = 0.050) are borderline. Nothing reaches p < 0.05 at phase 8.

**Hi KO vs WT at novel locations.** Nothing at phases 8 or 9. At phase 10:

- Rewards: 5.5 vs 15.2 (p = 0.004)
- Rewards per entrance: 0.14 vs 0.32 (p = 0.006)
- Time in goal: 0.017 vs 0.031 (p = 0.01)
- Mean speed: 10.2 vs 7.9 cm/s (p = 0.03)
- Target speed: 23.2 vs 16.6 cm/s (p < 0.001)

**Lo vs Hi.** No difference at phases 7, 8 or 9 (all p ≥ 0.08). At phase 10, Hi mice move faster in the goal zone (target speed 23.2 vs 15.3 cm/s, p = 0.004), faster overall (10.2 vs 5.9 cm/s, p = 0.009) and earn fewer rewards per entrance (0.14 vs 0.31, p = 0.02). Rewards (5.5 vs 9.6) and time in center do not differ (p = 0.11 and 0.08). On rewards per entrance, Lo mice match WT at phase 10 (0.31 vs 0.32).

After correction across the 64 tests per comparison, one difference stands on its own: Hi KO mice move faster in the goal zone than WT at phase 10 (target speed, q = 0.03). Hi vs WT rewards and rewards per entrance at phase 10, and rewards per entrance at phase 7, come close (q = 0.09). The smallest q is 0.16 for Lo vs WT and 0.28 for Lo vs Hi.

### Example mice: paths, dwell and speed

One mouse from each group shows the group results at the level of a single animal.

- **M22 (WT)** holds each new goal location: at every phase it spends more time in the current goal than in any other zone, and it keeps earning rewards across the rotations (12, 10 and 16 at phases 8–10).
- **M33 (Lo KO, 8.8%, IED−)** shows the Lo pattern of low activity and few rewards, with no clear preference for the current goal at phase 9.
- **M34 (Hi KO, 28.4%, IED+)** shows the Hi failure to stop at the goal: it does well at phase 9 (17 rewards), then at phase 10 reaches the goal 44 times but earns only 4 rewards.

- **Data.** The raw tracking files for the 24 probe sessions of these three mice.
- **Method.** The measures and plots of the MATLAB script `TargetTrajectories` (paths, reward locations, the 3 s approach before each rewarded entry, speed and dwell maps on a 32 × 32 grid), rewritten in Python. Where the Python code departs from the MATLAB code, the scripts say so.
- **Check against the MATLAB output.** Rewards and entrances match the PlaceAccuracy output exactly for all 24 sessions. Mean speed matches within 0.4 cm/s and target speed within 1.2 cm/s.
- **Same-size arenas in the figures.** The camera view of the arena shifted slightly between recording days, so raw paths differ in size and position. In the figures, each session's path is re-centred and scaled to a common arena, using a circle fitted to the outer edge of the mouse's path. Zone circles and reward points are moved with the same transform, so they stay where the tracker put them relative to the path. All measures come from the raw coordinates.
- **Zone positions.** Each zone is the goal location the mouse had in that phase, read from the file header. Zone times match the zone file used in this report within 0.35 percentage points for every session.


- **M22 (WT)** packs its rewards inside the current goal at every phase. After each rotation it makes fewer entries (23–35 against 92 at phase 7) but stays longer in the goal (1.4–2.4 s per entry), and its rewarded approaches converge on the new goal from across the arena.
- **M33 (Lo KO)** earns 13 rewards at the trained location, then 7, 3 and 9. At phase 9 it enters the goal 35 times but earns only 3 rewards, and its few rewarded approaches come from one side.
- **M34 (Hi KO)** gathers 17 rewards at the phase 9 goal, more than M22. At phase 10 it earns 4 rewards from 44 entries, against M22's 16 from 35. Its phase 8 session looks like an early version of the same failure: 6 rewards from 44 entries, 0.55 s per entry.


- **M22 concentrates on the current goal at every phase.** At phases 8–10 the current goal holds 3.1, 3.0 and 2.7% of the session, against at most 1.8% for any other zone. At phase 8 the old goal (zone 1) still draws 1.8%, the first-rotation return seen in the group data.
- **M33 has no favourite at phase 9.** Its zone times are 1.1, 0.6, 1.1 and 1.2%: the current goal ties with the trained zone and with a zone not yet used. At phase 8 it already spends 1.8% at zone 4, which has not yet been a goal. This is the Lo loss of preference for the current goal at phase 9, though M33 spreads its time rather than returning to the trained zone.
- **M34 still favours the current goal at phase 10** (2.8%, against 2.2% at the previous goal), as much as M22 does (2.7%). So its phase 10 failure is not about where it spends time: it gets to the right place and does not stay long enough to earn the reward.
- **Most of each session is spent in the wall zone** (64–85%), which is why it is blanked.


M34's target speed at phase 10 is 25.3 cm/s, against 19.1 for M22 and 18.7 for its own phase 7, although its mean speed over the session (9.8 cm/s) is only a little above phase 7 (8.8). M22 slows over the rotations, from 12.5 to 5.2 cm/s mean speed, while its target speed stays at about 19 cm/s. M33 is slow throughout (5.7–8.1 cm/s), which fits the Lo group's lower activity; its highest target speed (22.7 cm/s) is at phase 9, the session where it earns 3 rewards.

| Hidden session | Phase 7 | Phase 8 | Phase 9 | Phase 10 |
|---|---|---|---|---|
| M22 (WT): rewards / entries / s per entry | 21 / 92 / 1.03 | 12 / 25 / 2.21 | 10 / 23 / 2.37 | 16 / 35 / 1.40 |
| M33 (Lo KO) | 13 / 47 / 1.42 | 7 / 32 / 1.24 | 3 / 35 / 0.57 | 9 / 24 / 1.08 |
| M34 (Hi KO) | 10 / 41 / 1.01 | 6 / 44 / 0.55 | 17 / 54 / 1.06 | 4 / 44 / 1.13 |
| Target speed (cm/s): M22 / M33 / M34 | 19.2 / 13.9 / 18.7 | 15.3 / 18.8 / 18.1 | 19.0 / 22.7 / 15.4 | 19.1 / 12.7 / 25.3 |
| Mean speed over the whole stay in the goal (cm/s): M22 / M33 / M34 | 8.9 / 6.8 / 9.6 | 5.7 / 7.3 / 13.0 | 5.0 / 12.8 / 7.8 | 7.3 / 7.1 / 8.1 |
| Approach straightness (3 s before reward): M22 / M33 / M34 | 0.48 / 0.66 / 0.48 | 0.49 / 0.73 / 0.75 | 0.67 / 0.62 / 0.54 | 0.60 / 0.48 / 0.65 |

*Approach straightness: straight-line distance divided by path length over the 3 s before each rewarded entry (1 = a straight run). Target speed is the MATLAB measure, speed as the mouse enters and moves into the goal zone (about the first 0.5 s); the row below averages speed over the whole time in the zone, including the slow part of rewarded stays. Seconds per entry is total time in the goal divided by entries, so a few long stays can raise it: M34's median visit at phase 10 lasts 0.47 s (Figure 8 measure), against 1.80 s for M22.*


**Reading.**

- **The visible sessions are the control.** The phase 10 failure in M34 does not appear when the goal is cued, so the mouse can find a target and stop at it; it fails to do so only when it must remember where the goal is.
- **Two different failures.** M33 loses its preference for the current goal at phase 9, when M22 holds it. M34 keeps its preference through phase 10 but no longer stays in the goal long enough to be rewarded. This matches the group-level split between a failure of where to go (Lo) and a failure to stop at the goal (Hi).
- **M34 at phase 9 is in the better half of the Hi group.** The Hi group splits at phase 9 (table below). M28, M34 and M3 earn 12–18 rewards, inside the WT range. M7, M29 and M5 earn 3–7, closer to the Lo mice. None of the phase 9 group comparisons with WT reaches significance (rewards p = 0.31, current-goal time p = 0.11, Mann-Whitney), and the group still favors the current goal in share of zone time (49% vs 52% for WT). So phase 9 is intact for the Hi group in zone preference, but half the Hi mice are already earning few rewards. M34 shows the first half, not the average.
- **M34 is fast and stops briefly at phase 8 too** (0.55 s per entry, 6 rewards, 13 cm/s inside the zone), then recovers at phase 9. The group means hid this, because the Hi group was flat from phase 8 to 9. Phase 8 may be an early sign of the same failure.
- **Approach paths do not separate the mice.** The straightness of the last 3 s before a reward overlaps across the three mice at every phase, as the group analysis of approach paths below also finds.

| Hidden phase 9, Pten KO Hi | IED | Rewards | Entries | Rewards per entry | Current-goal time (% session) | Zone 1 time | Share at current goal |
|---|---|---|---|---|---|---|---|
| M28 | + | 18 | 94 | 0.19 | 4.5 | 2.5 | 56% |
| M34 | + | 17 | 54 | 0.31 | 3.1 | 1.5 | 42% |
| M3 | + | 12 | 26 | 0.46 | 2.1 | 1.0 | 58% |
| M7 | − | 7 | 20 | 0.35 | 1.2 | 2.1 | 26% |
| M29 | − | 6 | 27 | 0.22 | 1.1 | 0.2 | 62% |
| M5 | + | 3 | 30 | 0.10 | 1.0 | 1.0 | 37% |
| Hi median | | 9.5 | 28.5 | 0.26 | 1.7 | 1.2 | 49% |
| WT median (interquartile range) | | 11 (10–19) | 46 | 0.29 (0.23–0.40) | 3.0 (2.2–4.1) | 1.4 | 52% (40–60%) |

**Notes on these sessions.**

- **Tracking loss.** All 24 sessions lost the mouse in under 0.5% of frames. Lost frames are left out of all measures.

## 4. Does performance change across the rotations?

Each mouse gets a slope: the least-squares change per phase across the four hidden probes. The
cued sessions give the control, because a mouse that is simply getting worse over days should
decline there too.

![](figsv3/fig04_change_per_phase.svg){width=6.9in}

*Figure 4. Change per phase across the four rotations. Each point is one mouse's least-squares slope across phases 7 to 10; the bar is the group mean ± SE; beneath each group is the mean slope and its test against zero. Top row: goal hidden. Bottom row: goal cued, the control.*

The hidden slopes are where the groups part. Hi mice lose 2.9 rewards per phase (p = 0.003),
lose 0.023 rewards per entrance per phase (p = 0.022) and gain 2.13 cm/s of target speed per phase
(p = 0.005). Lo mice lose goal-zone time (−0.0069 per phase, p = 0.004) without losing rewards.
WT mice are flat on every measure (p = 0.06 to 0.61).

In the cued sessions nothing declines. The only significant cued slope in the set runs the other
way: Lo mice improve their rewards per entrance by +0.071 per phase (p < 0.001), which is the slow
acquisition of Section 2 still finishing. Hi mice are flat when cued on all four measures
(p = 0.06 to 0.55).

So the decline is a response to the goal moving, not a drift across days, and it is not fatigue or
satiety: the same mice on the same days earn rewards normally when the goal is marked.

### Hidden sessions: trained (phase 7) vs novel (mean of 8–10)

| Measure | WT change | p | Lo change | p | Hi change | p |
|---|---|---|---|---|---|---|
| Rewards | −28% | 0.003 | −34% | 0.03 | −42% | 0.02 |
| Proportion time in goal | −28% | 0.007 | −49% | 0.003 | −44% | 0.05 |
| Goal entrances | −22% | 0.03 | −51% | 0.008 | −32% | 0.07 |
| Rewards per entrance | −10% | 0.22 | +26% | 0.25 | −6% | 0.78 |
| Mean speed | +1% | 0.85 | −11% | 0.29 | +4% | 0.78 |
| Mean target speed | +18% | 0.01 | +16% | 0.09 | +26% | 0.16 |
| Proportion time in center | −15% | 0.51 | +38% | 0.37 | +23% | 0.60 |
| Proportion time in annulus | +6% | 0.06 | +4% | 0.35 | +9% | 0.24 |

P-values are paired t-tests within each group. The size of the trained-to-novel drop does not differ between groups on any hidden measure (all p > 0.05; the nearest is the larger drop in Lo goal entrances, p = 0.055), so the KO groups do not lose proportionally more than WT at the first rotation; they start lower.

### Hidden sessions: trend across phases 7–10

| Measure | WT slope per phase | p | Lo slope | p | Hi slope | p |
|---|---|---|---|---|---|---|
| Rewards | −1.2 | 0.10 | −1.4 | 0.16 | −2.9 | 0.003 |
| Proportion time in goal | −0.003 | 0.07 | −0.007 | 0.004 | −0.007 | 0.03 |
| Goal entrances | −3.3 | 0.14 | −11.3 | 0.001 | −7.4 | 0.07 |
| Rewards per entrance | −0.007 | 0.61 | +0.024 | 0.28 | −0.023 | 0.02 |
| Mean speed (cm/s) | −0.05 | 0.77 | −0.75 | 0.13 | +0.17 | 0.62 |
| Mean target speed (cm/s) | +0.93 | 0.06 | +0.30 | 0.49 | +2.13 | 0.005 |

- **WT:** one step down from trained to novel, then flat or recovering (rewards 13.0, 14.3, 15.2 across phases 8–10). No significant linear trend on any measure.
- **Lo KO:** time in goal and goal entrances fall steadily. Rewards per entrance do not fall, so these mice visit less often but are no less accurate when they do.
- **Hi KO:** rewards fall by about 3 per phase and rewards per entrance decline, while target speed climbs by about 2 cm/s per phase. This is the group that fits "worse with each rotation".
- **Lo vs Hi slopes:** target speed differs between the KO groups (p = 0.02); rewards per entrance does not (p = 0.08).
- **Slopes vs WT:** Lo goal entrances fall faster than in WT (−11.3 vs −3.3 per phase, p = 0.04), and Hi target speed rises faster (+2.1 vs +0.9 cm/s per phase, p = 0.007). The next section covers the slope comparisons in detail.

## 5. What controls where they go: the cue or the place?

Section 2 asked whether the mice can associate a marked place with reward. This section asks what they do when the marker and the place disagree, which is the question the task was built for. The answer separates the two KO groups in opposite directions, and it is the single most useful thing to hold in mind while reading the rest.

**The dissociation in one table.** Lo mice are the slowest of all three groups to form the cue–reward association, yet their place preference is intact and indistinguishable from WT. Hi mice get through the cue task faster than Lo, and show no place preference at all while the cue is present:

| | WT | Pten KO Lo | Pten KO Hi |
|---|---|---|---|
| Sessions to criterion (cue→reward) | 8.8 ± 0.5 | **21.2 ± 2.1** | 14.0 ± 2.8 |
| Latent place preference, cue present | +9.2 (p = 0.007) | **+12.0 (p = 0.016)** | **−4.2 (p = 0.58)** |
| Old-place share against the cue | 36.3% | 28.0% | **18.3%** |
| Old-place pull, cue removed | +9.7 | +10.0 | +12.5 (no group differences) |

Lo versus Hi on old-place share is p = 0.049; on sessions to criterion it is p = 0.08.

The last row is the one that fixes the interpretation, with a caveat about how far it can be pushed. Take the cue away and the Hi mice's pull toward the old place returns, to the same level as WT and Lo: +12.5 on the first ten directed runs, +10.4 on the first twenty against +10.3 in WT and +11.5 in Lo, with no group differences at all (Hi vs WT and Hi vs Lo both p = 1.000). The claim is therefore that their old-place pull becomes *normal* when the cue is removed, not that it exceeds the other groups. The within-mouse shift from cued to hidden is +16.7 points with five of six mice rising, but at n = 6 that is p = 0.15. So: the place information is present and is not expressed while a marker is available, stated as a direction rather than a significant effect.

So Hi mice are cue-dominant rather than place-blind, and sessions to criterion flatters them for exactly that reason: it is a cue task. Everything that follows in Part I is, in one way or another, a test of what happens when that fallback is removed.

> **Note on the Lo group — what is and is not established.** How each group differs from WT is the point of a mosaicism study, so the Lo profile deserves stating in its own right rather than as a milder Hi. What is significant: slowest of all to form the cue–reward association (21.2 vs 8.8 sessions, p < 0.001, no overlap); place preference fully intact (+12.0, p = 0.016 against zero, equal to WT); and in hidden sessions a search that is thorough but misdirected — after a miss they return to the current goal on 2.0% of occasions against 8.8% in WT (p = 0.006), their pauses fall at other zones rather than the current one (p = 0.001), and at phase 8 they spend more than twice as long as WT at zones that have **never** been goals (56.9 vs 25.9 s, p = 0.004).
>
> What is **not** established is inflexibility or perseveration. It is an intuitive reading of their drift back toward the first-learned location, but the drift rests on two of five mice, and on the direct test Lo mice do not differ from WT in time spent at former goals at any phase (p = 0.33 to 0.95) nor in the slope across phases (p = 1.00). They trend that way; it is not a group feature, and it should not be written as one without more mice. The supported characterisation is a mouse that searches hard and aims badly — including at places that were never rewarded, which perseveration does not predict.

Phase 8 is the first time the goal moves, and the two phase 8 probes set up two different conflicts. With the cue visible, the cue sits on the new goal while the old goal (the trained location from phase 7) is still a remembered place. Visible phase 8 is therefore a **place vs cue** conflict: it shows whether a mouse has a latent preference for a hippocampus-dependent place strategy over a cue strategy that does not need the hippocampus. About 32 minutes later, hidden phase 8 removes the cue. Now the conflict is **new place vs old place**, and the mice learn to handle it. WT mice keep both places in play. Pten KO Hi mice give the cue priority over place, but they still have the place memory.

- **Data.** Raw tracking for every phase 8 probe (30 mice: 19 WT, 5 Lo, 6 Hi). Every visit to each of the four candidate zones is kept with its entry time. The visit rule and launch distance are the same as in the arrival analyses. Only **directed runs** count (launch ≥ 20 cm), taken in the order the mouse made them.
- **Zones.** Zone 2 is the new goal (with the cue in the visible session) and zone 1 is the old goal. Zones 3 and 4 have never been a goal. They have never been rewarded, so runs to them give each mouse's **no-memory baseline**.
- **Place vs cue (visible).** The **old-place share** is the share of the first 10 directed runs to either the old place or the cue that went to the old place. The baseline is the same share computed for each never-used zone against the cue, averaged over zones 3 and 4.
- **Latent place preference, or place pull.** Of the first N directed runs to any zone, the % that went to a place minus the % that went to one never-used zone. Visible uses the first 10 runs. Hidden uses the first 20, because the mice make fewer directed runs without the cue (median 54 vs 94 per session for WT); the first 10 runs show the same pattern with less power. A pull above 0 means that place draws more runs than a place with no memory.
- **Tests.** Within group: one-sample t vs 0, or paired t. Between groups: two-sided Mann-Whitney. Links to phase 10: Spearman, plus a rank regression with group in the model (rank(y) ~ rank(x) + group).
- **Order of sessions.** In every mouse the visible probe ran about 32 minutes before the hidden probe (M7: a day earlier). M52, M54 and M59 (WT) have phase 8 dated before phase 7. Leaving them out changes no conclusion. WT latent place preference is still +9.7 (p = 0.014). The Hi vs WT old-place share is still p = 0.021. Both hidden place pulls still hold (p ≤ 0.014). The link to phase 10 is ρ = +0.56 (p = 0.002; with group in the model p = 0.051).

![](figsv/p8__fig30_phase8_visible.svg){width=6.5in}

*Figure 5. Visible phase 8: place (old goal) vs cue (new goal). A: filled symbols are the old-place share of the first 10 directed runs to the old place or the cue. Open symbols are the same share for a never-used zone against the cue (mean of zones 3 and 4), with lines joining each mouse's pair. Bars are group means; brackets are Mann-Whitney tests. B: latent place preference, the % of the first 10 directed runs to the old place minus % to one never-used zone; stars are a one-sample t-test vs 0. C: old-place share (A) against rewards at hidden phase 10, with the least-squares line through all mice. In every panel, colour marks the group; diamonds mark IED+ mice, circles IED− or not recorded. Mice with equal values are spread sideways.*

### Visible phase 8: place vs cue


| Visible phase 8 | WT | Lo KO | Hi KO | Lo vs WT | Hi vs WT | Lo vs Hi |
|--------------------------|----------------|----------------|----------------|-------|-------|-------|
| Old-place share vs cue | 36% | 28% | **18%** | 0.24 | **0.010** | **0.049** |
| Never-used zone vs cue (baseline) | 22% | 20% | 25% | 0.94 | 0.61 | 0.64 |
| Old place vs baseline (paired t) | **p = 0.001** | p = 0.14 | p = 0.41 | | | |
| Latent place preference (old − never) | **+9.2 (p = 0.007)** | **+12.0 (p = 0.016)** | −4.2 (p = 0.58) | 0.57 | 0.10 | 0.11 |

*Means of mice; % of the first 10 directed runs. p: Mann-Whitney between groups. Old-place share, pooled KO vs WT: p = 0.013.*

- **WT and Lo mice have a latent preference for place.** With the cue present, WT and Lo mice go to the old place more often than to a never-used zone. Place memory competes with the cue from the first runs.
- **Hi mice do not.** Their runs to the old place are no more common than runs to a place they have never been rewarded at (−4.2, p = 0.58). Against the cue, the old place gets half the WT share (18% vs 36%, p = 0.010). Their runs to a never-used zone against the cue are WT-like (25% vs 22%), so they are not simply more drawn to the cue overall. What is missing is the pull of the remembered place.
- **Graded with % KO.** Within the 11 KO mice, a higher % KO goes with a lower old-place share (ρ = −0.69, p = 0.018) and a lower latent place preference (ρ = −0.61, p = 0.046).
- **The place vs cue balance predicts phase 10.** Mice that give the old place a larger share against the cue earn more rewards at the last hidden probe (ρ = +0.62, p < 0.001, n = 30). This holds within WT (ρ = +0.46, p = 0.049), within KO (ρ = +0.65, p = 0.032), and with group in the model (p = 0.018). The latent preference on its own (old vs never-used, no cue in the comparison) does not predict phase 10 (ρ = +0.25, p = 0.19). It is the balance between place and cue that matters.

![](figsv/p8__fig31_phase8_hidden.svg){width=6.5in}

*Figure 6. Hidden phase 8: new place vs old place. A: place pull over the first 20 directed runs, for the new place (filled) and the old place (open); stars are a one-sample t-test vs 0. B: old-place pull over the first 10 directed runs, with the cue present (visible phase 8, open) and with it gone (hidden phase 8, filled), joined by mouse. Above each group are the paired t-test and the number of mice that went up and down. C: place pull (mean of new and old, minus never-used; first 20 runs) against rewards at hidden phase 10. Symbols as in Figure 5.*

### Hidden phase 8: new place vs old place


| Hidden phase 8, first 20 directed runs | WT | Lo KO | Hi KO | Lo vs WT | Hi vs WT | Lo vs Hi |
|--------------------------|----------------|----------------|----------------|-------|-------|-------|
| Runs to new place / old place / one never-used zone | 29 / 31 / 20% | 39 / 28 / 17% | 33 / 29 / 19% | | | |
| New place − never-used | **+8.7 (p = 0.049)** | **+22.5 (p = 0.015)** | **+13.5 (p = 0.039)** | 0.12 | 0.35 | 0.27 |
| Old place − never-used | **+10.3 (p = 0.002)** | +11.5 (p = 0.13) | +10.4 (p = 0.072) | 0.94 | 1.00 | 1.00 |
| Mean of both places − never-used | **+9.5 (p = 0.002)** | **+17.0 (p = 0.039)** | **+11.9 (p = 0.010)** | 0.28 | 0.82 | 0.65 |

*Means of mice. Within group: one-sample t vs 0. Between groups: Mann-Whitney. First 10 runs, same direction with less power: WT new +5.0, old +9.7 (p = 0.056); no between-group p below 0.30. Whole session: all six pulls are above 0, and no between-group p falls below 0.13.*

- **Every group holds both places.** Without the cue, WT, Lo and Hi mice all go to both the new and the old place more often than to a never-used zone, by about the same amount. For WT, handling the conflict means keeping both places in play: the new place (learned with the cue half an hour earlier) and the old place draw equally (paired p = 0.74).
- **No group differences.** None of the hidden phase 8 measures separates the groups (all p ≥ 0.12). Lo mice lean toward the new place (+22.5 vs +11.5 for old; paired p = 0.020), but their new-place pull is not significantly above WT's (p = 0.12).
- **Hidden phase 8 does not predict phase 10** (place pull vs rewards ρ = −0.17, p = 0.36; with group in the model p = 0.49). It does not track visible phase 8 either: visible latent place preference vs hidden old-place pull ρ = +0.16 (p = 0.41).

| Old-place pull, first 10 directed runs | WT | Lo KO | Hi KO |
|------------------------------|--------------|--------------|--------------|
| Cue present (visible phase 8) | +9.2 | +12.0 | −4.2 |
| Cue gone (hidden phase 8) | +9.7 | +10.0 | +12.5 |
| Change, paired t | +0.5 (p = 0.93) | −2.0 (p = 0.84) | +16.7 (p = 0.15) |
| Mice up / down | 9 / 9 (1 unchanged) | 3 / 2 | 5 / 1 |

*Change between groups (Mann-Whitney): Hi vs WT p = 0.20, Lo vs WT p = 0.89, Lo vs Hi p = 0.14.*

- **The cue suppresses the place memory in Hi mice.** The old place is the same remembered place in both sessions; only the cue changes. In WT and Lo mice its pull is the same with or without the cue. In Hi mice the pull is missing while the cue is present and returns to the WT level once the cue is gone, in 5 of 6 mice. With six mice this is a trend (p = 0.15), and one Hi mouse (M3) goes the other way, so it supports the reading of Figure 5 rather than standing as a result of its own.

**Reading.** Taken together, the two phase 8 probes point to a **strategy bias**, not a loss of spatial memory. Hi KO mice can remember the old place: with no cue, it draws them as much as it draws WT mice. When a cue offers a non-hippocampal route to the goal, though, the place memory does not compete. WT and Lo mice keep a latent preference for place even when the cue is present, and the strength of that place vs cue balance at the first rotation predicts how well each mouse performs at the last hidden rotation, within WT as well as across groups. This fits the Hi KO pattern at phase 10, where the cue is gone and the mice reach the goal but fail to settle there.

## 6. Is getting to the goal intact?

Before asking what the mice do when they arrive, it is worth establishing that they get there normally. If Hi mice simply navigated badly — slower, less directly, from closer in — the arrival and search results would follow trivially. They do not.

The paths in Figure 3 and 14 look very different with and without the cue. This section puts numbers on that difference for every mouse, and asks whether the KO groups travel to the goal, or arrive at it, differently from WT.

- **Data.** Raw tracking files for all 256 probe sessions (phases 7–10, visible and hidden) from 32 mice: WT 19, Lo KO 5, Hi KO 6, no histology 2. Rewards and entrances match the probe data exactly for every session. Pten;Raptor dKO mice are left out.
- **Unit of measurement.** Every entry into the current goal zone (17,588 entries). The same zone is used for the visible and hidden session of each phase, so the V vs H comparison is made at the same goal location.
- **Launch distance.** Working back from each entry, the last stretch during which the mouse was moving toward the goal (heading within 45° of the goal at more than 5 cm/s, with up to 0.5 s off course allowed). Launch distance is how far from the goal that run began. A long launch distance means the mouse set off toward the goal from far away. A **directed run** is one that began at least 20 cm from the goal.
- **Wall-to-goal run.** The path from the last moment at the wall (outer 20% of the arena radius) to the entry, when the mouse did not pass through the zone on the way and the run took no more than 20 s. About 77–81% of entries start this way, in every group and condition. For each run: straightness (straight-line distance ÷ path length, 1 = a straight line) and duration.
- **Path per reward.** Total distance run in the session ÷ rewards earned.
- **Arrival.** For each entry: speed over the first 0.5 s inside the zone, time in the zone before leaving it, and whether the entry earned a reward.
- **Per mouse.** Launch distance and run duration are medians over all entries from phases 7–10; straightness is the mean over runs; path per reward is the median over the four sessions. Arrival measures are per session.
- **Tests.** Visible vs hidden within each group: paired t-test. Between groups: Mann-Whitney (Lo vs WT, Hi vs WT, Lo vs Hi).


- **With the cue, all three mice behave alike.** Runs converge on the goal from all round the arena, and 35–42% of them end in a reward.
- **Hidden, phases 7–10.** There are fewer runs and more of them curve. M22 (WT) still turns 35% of its runs into rewards; M33 (Lo) and M34 (Hi) manage 21%.
- **Hidden, phase 10.** This is where the groups part. M22 earns a reward on 54% of 28 runs. M33 makes only 15 runs and rewards 27% of them. M34 makes more runs than M22 (41), but only 4 of them (10%) end in a reward: most pass straight through the goal.

### Getting to the goal: the cue changes every group in the same way


| Measure | Group | Visible | Hidden | p (paired) |
|----------------------------------------|----------------|--------------|--------------|--------------|
| Launch distance (cm) | WT | 20.1 | 16.5 | 0.0001 |
|  | Lo KO | 21.0 | 17.2 | 0.046 |
|  | Hi KO | 19.8 | 15.5 | 0.011 |
| Straightness, wall to goal | WT | 0.885 | 0.845 | < 0.0001 |
|  | Lo KO | 0.883 | 0.858 | 0.054 |
|  | Hi KO | 0.876 | 0.839 | 0.094 |
| Duration, wall to goal (s) | WT | 1.02 | 1.19 | 0.001 |
|  | Lo KO | 1.16 | 1.30 | 0.34 |
|  | Hi KO | 1.00 | 1.01 | 0.87 |
| Entries that start at the wall | WT | 80% | 80% | 0.79 |
|  | Lo KO | 81% | 79% | 0.24 |
|  | Hi KO | 78% | 77% | 0.59 |
| Path per reward (m) | WT | 7.3 | 12.6 | 0.026 |
|  | Lo KO | 7.1 | 15.2 | 0.003 |
|  | Hi KO | 7.4 | 25.0 | 0.060 |

*Means of mice. p: paired t-test, visible vs hidden, within the group. WT n = 19, Lo n = 5, Hi n = 6.*

- **WT.** With the cue visible, WT mice set off toward the goal about 3.5 cm further out (20.1 vs 16.5 cm), take straighter runs from the wall (0.89 vs 0.85) and arrive sooner (1.02 vs 1.19 s). They run about 1.7 times as far for each reward in the hidden sessions (12.6 vs 7.3 m). So even WT mice find a hidden goal in a different way: they commit to it later and from closer in, rather than heading for it from across the arena.
- **Lo and Hi KO.** Both groups show the same shift in launch distance (about 4 cm each, p = 0.046 and 0.011) and in straightness (about 0.03–0.04, p = 0.05 and 0.09). With 5 and 6 mice, the weaker p-values reflect group size more than a smaller effect.
- **Where the runs start does not change.** About four in five entries begin with a run from the wall in both conditions, in every group.


- **The WT gap is clearest at phases 8 and 10** (p = 0.007 and 0.003), smaller at phase 7 (18.6 vs 16.5 cm, p = 0.16) and nearly gone at phase 9 (21.2 vs 20.3 cm, p = 0.46).
- **The KO groups show the same direction at every phase,** but the per-phase tests are significant only for Lo at phase 7.

| Mann-Whitney p vs WT | Lo: hidden | Lo: visible | Lo: V − H | Hi: hidden | Hi: visible | Hi: V − H |
|--------------|-----|-----|-----|-----|-----|-----|
| Launch distance | 0.84 | 0.49 | 0.95 | 0.16 | 0.93 | 0.51 |
| Straightness, wall to goal | 0.78 | 0.84 | 0.41 | 0.98 | 0.25 | 0.88 |
| Duration, wall to goal | 0.43 | 0.11 | 0.59 | 0.17 | 0.87 | 0.23 |
| Entries that start at the wall | 0.67 | 1.00 | 0.58 | 0.41 | 0.56 | 0.83 |
| Path per reward | **0.019** | 0.89 | **0.036** | **0.003** | 0.98 | **0.006** |

- **How the mice get to the goal does not separate the groups.** Launch distance, straightness and run duration are the same in KO and WT mice, in both conditions, averaged over phases or phase by phase. The share of entries reached by a directed run is also the same in every group at every hidden phase (40–58%; Figure 8).
- **Both KO groups run further for each reward, but only without the cue.** In hidden sessions Hi KO mice run 25.0 m per reward against 12.6 m for WT (p = 0.003), and Lo KO mice 15.2 m (p = 0.019). In visible sessions both match WT. This is the hidden reward deficit seen from the distance side; the next part shows where the extra distance comes from.

### Heading toward the goal, by distance

Launch distance gives one number per goal entry, and a median across entries blurs the cue effect (Figure S7, phase 31). Here every running frame counts. For each frame where the mouse is running (over 5 cm/s) outside the goal zone, the heading error is the angle between its direction of travel and the direction to the goal centre. **Goal-directedness** is the mean cosine of that angle: 1 means running straight at the goal, 0 means heading unrelated to it. It is plotted against distance from the goal, at the same goal location for the visible and hidden session of each phase.

- **Frames.** Running (> 5 cm/s), outside the goal zone, and not in the 2 s after leaving it, so mice walking away after a visit do not count. The main version leaves out frames at the wall (outer 20% of the arena radius), where the wall sets the heading whatever the goal; including them gives the same result, smaller.
- **Reach.** Per mouse and condition (phases 7–10 pooled), the distance at which goal-directedness first falls below 0.1, going outward from the goal. Because 0.1 is an arbitrary line, the mean goal-directedness between 10 and 40 cm is also given; it needs no threshold.
- **Launch distances.** The same entries as Figure S6, shown as the full distribution: the % of each mouse's goal entries launched from at least a given distance.


| Visible vs hidden | Group | Visible | Hidden | p (paired) | Visible higher |
|----------------------------|------------|---------|---------|-----------|-----------|
| Reach (cm) | WT | 33.8 | 21.4 | < 0.001 | 17/19 |
|  | Lo KO | 30.3 | 20.5 | 0.027 | 5/5 |
|  | Hi KO | 31.7 | 19.4 | 0.001 | 6/6 |
| Goal-directedness, 10–40 cm | WT | 0.19 | 0.08 | < 0.001 | 18/19 |
|  | Lo KO | 0.18 | 0.08 | 0.025 | 5/5 |
|  | Hi KO | 0.19 | 0.07 | < 0.001 | 6/6 |
| Entries launched from ≥ 30 cm | WT | 34% | 26% | < 0.001 | 17/19 |
|  | Lo KO | 33% | 23% | 0.002 | 5/5 |
|  | Hi KO | 31% | 23% | 0.011 | 5/6 |
| Entries launched from ≥ 40 cm | WT | 18% | 13% | < 0.001 | 17/19 |
|  | Lo KO | 17% | 9% | 0.011 | 5/5 |
|  | Hi KO | 14% | 10% | 0.002 | 6/6 |

*Means of mice; frames off the wall. With wall frames included: WT reach 22.2 vs 13.7 cm (19/19 mice, p < 0.001), and the same in Lo (p = 0.025) and Hi (p < 0.001). Entries launched from ≥ 20 cm: WT 50% vs 42% (p < 0.001). Between groups (Mann-Whitney), reach and goal-directedness do not differ from WT in either condition (all p ≥ 0.27); the one launch-distribution difference is Hi vs WT at ≥ 40 cm with the cue visible (14% vs 18%, p = 0.030).*

- **With the cue, WT mice aim at the goal from much further away.** They are about twice as goal-directed at every distance from the edge of the zone out to about 40 cm (p < 0.001 in every 2.5 cm bin up to 41 cm). Their reach is 34 cm with the cue and 21 cm without, about 60% further, and longer with the cue in 17 of 19 mice.
- **Without the cue, heading far from the goal is unrelated to it.** Beyond about 35 cm, hidden-goal goal-directedness is close to 0. Mice do not set a course for a hidden goal from across the arena: they reach its neighbourhood, about three to four zone radii out, and orient from there.
- **The gap holds at every phase,** including phase 9 (36 vs 22 cm, p < 0.001), where the median launch distance had almost no gap (Figure S7). The frame-based measure is less noisy than one launch distance per entry.
- **The whole launch distribution shifts, most in its tail.** The share of entries launched from 40 cm or more falls by about a third without the cue (18% to 13% in WT). The median shift of Figure S6 is that change seen at one point.
- **Pten KO mice shift exactly like WT.** Every Lo and every Hi mouse reaches further with the cue, by about 10–12 cm, and neither group differs from WT in either condition. Both kinds of navigation, aiming at a visible cue from afar and homing in on a remembered place from close by, are intact in Pten KO mice. Their deficits lie elsewhere: choosing place over cue (Figure 5) and settling at the goal (Figure 8).

**Reading.** In this task a cued goal is approached by **beaconing**: the mouse locks on from most of the way across the arena. A hidden goal is approached **locally**: the mouse first gets to the right part of the arena, then turns toward the goal. This is the classic beacon vs place distinction, measured continuously in the same mice, at the same goal location, about half an hour apart.

The figures behind this section — every wall-to-goal run for one mouse per group, the visible
against hidden comparison of each measure, launch distance by phase and the heading profile — are
Supplementary Figures S5 to S8. Nothing in them separates the groups once the cue is removed in
the way the arrival measures do, which is the point: the navigation is intact.

## 7. Do they recognise arrival?

Getting to the goal is intact. What happens on arrival is not. This section is about the moment the mouse enters the zone, and about the 1.2 s it must then stay for the reward to be delivered.


| Hidden phase 10 | WT | Lo KO | Hi KO | Lo vs WT | Hi vs WT | Lo vs Hi |
|----------------------------------|----------|----------|----------|------------|------------|------------|
| Entries reached by a directed run | 51% | 55% | 50% | 0.21 | 0.61 | 0.86 |
| Speed on entry (cm/s) | 14.7 | 15.1 | 22.1 | 0.53 | **0.003** | **0.030** |
| Time in goal per visit (s) | 1.11 | 1.25 | 0.51 | 1.00 | **0.006** | **0.013** |
| Directed runs that end in a reward | 34% | 45% | 16% | 0.17 | **0.020** | **0.017** |

*Means of mice; each mouse's value is the median over its entries (speed, time) or the share of its entries.*

- **Hi KO mice aim at the goal as often as WT but do not stop there.** At hidden phase 10, half of their entries come from a directed run, the same as WT and Lo. They enter half again as fast (22 vs 15 cm/s), stay less than half as long (0.51 vs 1.11 s) and earn a reward on 16% of directed runs, against 34% for WT and 45% for Lo. Their speed trace (Figure 8, top centre) peaks higher at entry and never drops to the WT level inside the zone.
- **This is the clearest separation between the two KO groups in the probe data.** Lo and Hi differ at hidden phase 10 on entry speed, time in the goal and reward per directed run (p = 0.013–0.030), where the zone-time and approach measures did not separate them.
- **The Hi pattern is specific to the hidden goal.** At visible phase 10, Hi mice enter at about WT speed and slow normally (Figure 8, top right); time in the goal (1.23 s) and reward per directed run (44%) match WT.
- **Hi mice also spread their directed runs across the zones at phase 10.** Of the directed runs that end in any of the four candidate zones, 27% go to the current goal, against 41% for WT (p = 0.014) and 37% for Lo (p = 0.052 vs Hi). So the Hi mice aim for remembered locations as often as WT, but less often for the right one, and do not stop at the right one when they get there.
- **Lo KO mice slow and stay longer when the goal is cued.** At visible phase 10 they stay 1.65 s per visit against 1.23 s for WT (p = 0.010) and earn a reward on 57% of directed runs against 38% (p = 0.004). Together with their fewer runs overall (a median of 210 visible-session runs per Lo mouse against 282 for WT), this fits the Lo pattern already reported: slower and less active, but more rewards per entrance.
- **At the trained location (hidden phase 7)** Hi mice already enter faster than WT (16.5 vs 13.0 cm/s, p = 0.006) and Lo mice stay a shorter time (0.90 vs 1.30 s, p = 0.008), with no difference in reward per directed run. These are smaller effects, and with 48 hidden-session tests in this panel some will be chance; the phase 10 Hi results are the ones to take forward.
- **Overlap with earlier results.** Speed on entry is the same quantity as target speed (speed in the goal zone), computed per visit, and reward per directed run is a close relative of rewards per entrance; both already showed the Hi deficit at phase 10. What this analysis adds is that the deficit is not in reaching the goal: the Hi mice get there by the same kind of run as WT, then fail to stop.

![](figsv3/fig16a_arrival_runs.svg){width=6.3in}

*Figure 8. Arriving at the goal: what the runs look like. **a** Every directed run into the hidden goal at phase 10 for one mouse per group, in goal-centred coordinates, rotated so the approach comes from the left and coloured by speed; the dot marks where the mouse was 1.2 s after entering — inside the zone (green) is a reward, outside (red) is a miss. **b** One run per mouse, the run whose slowing ratio is closest to that mouse's median; a dot every 0.1 s, so the dots bunch where the mouse is slow. All three panels share one axis range, so the goal circles are the same size and the runs are drawn to the same scale. **c** Mean speed around every entry into the current goal — directed runs and chance crossings alike — at the trained location, the last rotation and the cued last rotation; mean ± SE across mice; the shaded band is the 1.2 s the mouse must stay in the zone to earn the reward. The p value compares the mean speed inside that window, Hi vs WT (Mann-Whitney).*

Panel c is the clearest statement of the deficit in the report. At the trained location the
three groups are indistinguishable through the reward window (Hi 11.1 cm/s, WT 10.1, p = 0.18).
At the last rotation the Hi mice are moving at **16.4 cm/s against 11.5 in WT (p = 0.0005)** —
they reach the goal and pass through it. Put the marker back, at the same phase in the same mice,
and the difference goes (11.8 against 10.7, p = 0.18).

This is the measure to lead with: it uses every entry rather than the subset the mouse aimed at,
so it cannot be explained by a difference in which runs qualify as directed.

![](figsv3/fig16b_arrival_phase.svg){width=6.5in}

*Figure 9. Slowing and pausing across the rotations. **a** Slowing ratio (mean speed over the 1.2 s after entry divided by the mean over the 1.5 to 0.5 s before it, on directed runs; 1 means no slowing) and total pause time per session, hidden and cued. **b** Pause time split by where the pause happened — inside the goal zone, in the ring around it, and in the open interior beyond 2.5 zone radii — with the cued open interior as the control. Pauses at the wall (beyond 0.8 of the arena radius) are excluded by the pause definition throughout. Faint points are mice, lines are group means ± SE. Beneath each panel are the mean per-mouse slopes across phases 7 to 10 and the Mann-Whitney comparing those slopes between Hi and WT; numbers above a phase are Hi vs WT at that phase.*

### What arrival looks like, and what stops happening at the last rotation

Three things sharpen the arrival result. The first is a control: the speed profile in Figure 8 pools runs the mouse aimed at the goal with crossings it wandered into. Recomputed separately, the Hi deficit is the same in both (speed in the reward window at hidden phase 10: directed 17.3 vs 12.4 cm/s in WT, p = 0.001; chance crossings 14.9 vs 10.6, p = 0.003). That matters: if the failure to settle appeared only on aimed runs it could be momentum carrying a fast approach through the zone. It appears just as strongly when the mouse arrives by accident, which is what a failure to recognise the place should look like.

The second is a better measure. Dividing the speed in the 1.2 s after entry by that same run's approach speed over the 1.5 to 0.5 s before it gives a **slowing ratio**, where 1 means the mouse did not slow at all. Because it is a within-run ratio it separates a failure to settle from running fast in general, and the separation matters here: Hi mice do not differ from WT in approach speed at any phase or condition (p = 0.14 to 0.40).


**Braking: the same question asked the way Whishaw asked it.** Whishaw, Cassel and Jarrard (1995) take deceleration on approach as the sign that an animal expects the goal at a place; their fimbria-fornix rats decelerated at the same distance from the vanished platform as controls (8.3 against 7.8 cm, n.s.), which is how they concluded the rats knew where it was. The same measure here has two advantages over the slowing ratio: it is counted per metre of path travelled, so it is not inflated by the extra ground Hi mice cover, and it is a per-run event rather than a session average. A braking event is a fall from a local speed maximum of at least 12 cm/s to below half that speed within 1 s, placed where the mouse ended up slow; braking distance is the distance from the goal at which speed first falls below 70% of that run's approach maximum.

| Hidden phase 10 | WT | Lo | Hi | Hi vs WT |
|---|---|---|---|---|
| Braking rate at the current goal (per 10 m off the wall) | 9.15 | 7.96 | **6.05** | **p = 0.004** |
| Directed runs with any braking | 56.2% | 51.3% | **38.4%** | **p = 0.045** |
| Braking distance when they brake (cm) | 11.5 | 13.2 | 13.7 | p = 0.050 |
| *Cued phase 10: braking rate* | *11.93* | *11.93* | *12.81* | *p = 0.303* |
| *Cued phase 10: braking distance* | *10.2* | *9.3* | *10.2* | *p = 0.975* |

At phase 7 the groups are identical (11.44 against 11.02, p = 0.64). By phase 10 Hi mice brake at the hidden goal on fewer approaches and, when they do, start further out rather than at a displaced location — earlier and over a broader region, which reads as uncertainty about where the goal is rather than a systematic error about where it is. With the cue present every number is WT-normal, and at phase 10 the Hi mice brake most of the three groups. Where Whishaw's fimbria-fornix rats passed this test, these mice fail it.

One result cuts against the reading this report carried until now. Braking at the **former** goals is identical in all three groups (14.72 against 15.21 per 10 m, p = 0.93) while pause time there is a third (28 s against 82 s). Hi mice approach the old zones and slow at them as often as WT. They do not stay. So they have not stopped checking; they have stopped committing.

The slowing ratio builds across the rotations rather than appearing at phase 10. In the hidden sessions it runs 0.58, 0.70, 0.72, 0.74 in WT and 0.61, 0.70, 0.87, 0.91 in Hi mice (Hi vs WT p = 0.64, 0.83, 0.18, 0.009). Every mouse slows less as the goal moves further from where it was trained; Hi mice climb faster and end up barely slowing at all (+0.11 per phase within Hi, p = 0.033; group × phase against WT p = 0.069, a trend). With the cue visible there is no difference at any phase. The example paths show what the number means: a WT or Lo run ends in a tight knot of closely spaced points inside the zone, a Hi run crosses it at full speed with its points evenly spaced and keeps going.

The third is the one that reframes the result, and it is a phase effect rather than a phase-10 effect. Across the hidden rotations the two groups move apart: WT pause slightly more from phase to phase (+5.9 s per phase) while Hi mice pause steadily less (−14.4 s per phase), and comparing those per-mouse slopes gives a group × phase difference of p = 0.036. In the cued sessions the same slopes are flat in both groups and the interaction is absent (p = 0.88). By the last hidden rotation the gap is 59 s against 134 s (p = 0.006), and it is both fewer pauses (28.0 vs 49.6 per session, p = 0.024) and shorter ones (2.03 vs 2.71 s, p = 0.002).

Both parts of pause time move together: at phase 10 Hi mice make fewer pauses (28.0 vs 49.6 per session, p = 0.024) and each one is shorter (2.03 vs 2.71 s, p = 0.002). Neither component reaches significance on the group × phase slope by itself (p = 0.215 for the count, p = 0.138 for the duration); it is the product of the two, total pause time, where the interaction is clear. The effect is on how much the animal stops altogether, not on one isolated feature of stopping.

**Where the lost pauses are is the informative part, and it is not at the goal.** Pauses were split by distance from the current goal (Figure 16d). Note first what the pause definition already excludes: a pause is 1.2 to 10 s below 3 cm/s, and pauses in the wall annulus (radius above 0.8 of the fitted arena radius) are dropped, so none of this is thigmotaxis or resting against the wall. Within the arena proper, pausing inside the goal zone shows no group difference and no interaction (slopes −0.5 vs −1.0 s per phase, p = 0.69), and neither does pausing in the ring just around it (1–2.5 radii; −0.6 vs −0.9, p = 0.83). The whole effect sits in the open interior beyond 2.5 radii: WT rise from 78.5 to 101.8 s across the rotations (+7.0 s per phase) while Hi mice fall from 79.7 to 37.7 s (−12.5 s per phase), group × phase p = 0.007, and at phase 10 p = 0.003. In the cued sessions the same compartment is flat in both groups (p = 0.98).

So the two groups do not differ in how much they stop at the goal. They differ in how much they stop **everywhere else**, and they differ in opposite directions. As the goal moves further from where it was trained, WT mice stop more often out in the arena — they check candidate places. Hi mice stop doing it. That is a difference in search, not in arrival, and it is the clearest instance in this report of a measure separating what a mouse knows from what it does about it. It also fits the slope being the carrier of the result: this is not a level difference present from the start but a divergence that grows with each rotation, which is what a limit on holding and testing candidate locations would look like.

Two qualifications keep this honest. The groups overlap — three of the six Hi mice fall inside the WT range at phase 10 (18, 32, 37, 63, 93 and 111 s against a WT range of 50 to 283) — so this is a shift in distribution rather than every mouse abandoning the strategy. And the within-Hi decline on its own is a trend (−14.4 s per phase, p = 0.079, five of six mice down); it is the comparison against the WT slope, and its absence with the cue, that carries the result.

What the pauses they still make do not show is any loss of accuracy. Pooled over hidden phases 8 to 10, the fraction of near-goal pauses that fall inside the zone (0.177 vs 0.232, p = 0.18), the median distance of those pauses from the goal (1.56 vs 1.51 zone radii, p = 0.30), the share of pause time spent in the zone (p = 0.56) and the mean duration of an in-zone pause (p = 0.30) are all indistinguishable from WT. If the pause is read as the mouse's own estimate of where the goal is, the estimate is not visibly blurred; there is simply much less of it at phase 10. With six Hi mice a null of this size does not exclude a genuinely coarser representation, and the two readings — a degraded memory, or an intact one that is no longer acted on — are not separated by the present data.

### The shape of the approach is normal

Whishaw, Cassel and Jarrard (1995, *J Neurosci* 15:5779) treat deceleration on approach as the
sign that an animal expects the goal at a place. Applying that test here needs care, because there
are two different questions in it: *does the approach have the right shape*, and *does the animal
stop when it arrives*.

The shape is normal. Scaling every directed run to its own approach maximum and plotting speed
against distance from the goal gives the profile in Figure 12. It hooks: the mouse accelerates
away from the wall, peaks 14 to 16 cm out and decelerates into the zone, and the three groups
trace the same hook. A permutation test across the whole profile with max-statistic correction,
which corrects for testing every distance bin, separates Hi from WT in neither condition — cue
removed, largest difference 8.3 percentage points, p = 0.83; cue present, 13.3 points, p = 0.22 —
and the within-animal hidden-minus-cued profile gives p = 0.57. Hi mice decelerate on approach
like everyone else.

![](figsv3/fig_approach_profile.svg){width=6.5in}

*Figure 12. The shape of the approach at phase 10, cue removed (**a**) and cue present (**b**).
Every directed run into the current goal, cut at the frame it entered the zone, with speed scaled
to that run's own approach maximum and binned by distance from the goal centre in 2 cm bins; runs
are averaged within a mouse and mice within a group, so the line is a mean over mice and the band
is the SE over mice. A bin is drawn where at least half the group's mice contribute a run reaching
that far out. Dashed line: 70% of the approach maximum, the braking criterion used by the
event-based measures in Figure 13. Shaded: the goal zone. The cued profiles are smooth and almost
superimposed; without the cue they are more ragged in all three groups, which is sampling — a
quarter as many runs — rather than a group difference.*

What differs is whether a run contains a slowdown at all, and what happens at the goal. The same
profile at every phase is Supplementary Figure S15, and shows the same thing: the hook is present
in all four phases in both conditions, and the groups overlap throughout.

![](figsv3/nf4_arrival.svg){width=6.5in}

*Figure 13. Braking on approach, cue present and cue removed, at phase 10. **a** Braking events at the current goal per 10 m of off-wall path — a braking event is a fall from a local speed maximum of at least 12 cm/s to below half that speed within 1 s, placed where the mouse ended up slow and assigned to the nearest kind of zone within 2.5 zone radii; rates are per metre travelled because Hi mice cover about 29% more ground. **b** The proportion of directed runs that contain any braking. **c** The distance from the goal at which a braking run first fell below 70% of its approach maximum, over the runs that braked. Each pair of points is one mouse, cue present on the left; p beneath each pair is the paired t-test; above each panel is the Mann-Whitney on the change between Hi and WT. Diamonds mark IED+ mice.*

Cued, the three groups brake alike: 88.0% of WT runs and 81.2% of Hi runs contain a slowdown
(p = 0.59), beginning 10.2 cm out in both (p = 0.98). Hidden, 56.2% of WT runs and 38.4% of Hi runs
contain one (p = 0.045), and when Hi mice do brake they start later, 13.7 cm from the goal centre
against 11.5 (p = 0.050). The within-animal change is the stronger test: removing the cue costs WT
mice 2.8 braking events per 10 m and Hi mice 6.8 (p = 0.021).

**Where this logic has to stop.** Braking at *former* goals is identical in all three groups
(15.2, 15.8 and 14.7 events per 10 m, p = 0.93). Hi mice do pass through the old places and do slow
at them. The deficit is not a failure to generate candidates or to check them; it is a failure to
turn a check into a stay.

## 8. When the goal has moved, do they search the places that used to pay?

A mouse that cannot find the current goal has a second option: go and check the places that used to pay. This section is about whether they take it. **Every pause measure below is labelled for where the pause was** — at the current goal, at a former goal, or anywhere in the arena off the wall — because the same pauses give different and incompatible answers depending on which is meant.

**This is the strongest result in the arrival analyses, and probably the one the section should be built around.** It came last, out of a question about which pauses the earlier measures had been counting.

Each of the four zones was the goal of exactly one phase: zone *k* is the goal of phase *k* + 6. So at any hidden phase the four zones fall into three kinds — the current goal, the goals of earlier phases, and the zones that have not yet been used. The number of former goals grows 0, 1, 2, 3 across phases 7 to 10, and with it the number of places a mouse has to hold in mind and rule out before settling on the current one. Every pause was assigned to the nearest kind of zone within 2.5 zone radii, with pauses near none of them counted separately. The same breakdown is shown for the cued sessions, where the beacon marks the current goal and there is no need to work through the rest.


As former goals accumulate, WT mice spend steadily more time at them: nothing at phase 7, then 33, 42 and 82 s per session, a slope of +25.3 s per phase. Lo mice do the same (+28.8 s per phase, 88 s by phase 10). Hi mice barely scale at all — 15, 26, 28 s, a slope of +9.6 — and the difference in slope against WT is p = 0.003.

**With the cue present the deficit disappears.** In the cued sessions Hi mice work through the former goals almost as much as WT (slope +15.0 against +18.6 s per phase, 50.8 against 55.3 s by phase 10, p = 0.198). The comparison runs the other way too: WT search the former goals *harder* when the goal is hidden than when it is cued (+25.3 against +18.6), which is what a mouse should do once the beacon is gone, while Hi mice do the opposite (+9.6 hidden against +15.0 cued). The capacity limit only bites when the set has to be held internally; give the mice a beacon and the search returns. This is the control that makes a working-memory account preferable to a general loss of interest in the other zones.

Three further controls in the same figure say what this is not:

- **Zones never used.** Both groups abandon them at the same rate as they stop being candidates (−19.0 vs −21.2 s per phase, p = 0.64). Hi mice know which places have never been a goal. They are not disoriented and they are not checking at random.
- **The current goal.** No difference in slope (−1.1 vs −1.9, p = 0.93). Finding and dwelling at the goal in play is intact.
- **Away from every zone.** No difference (+0.6 vs −0.9, p = 0.60). This is not a general change in how much the animal stops in open space.

So the deficit is specific to working through the former goals, and it scales with how many there are. That is the shape of a capacity limit on holding and testing a set of candidate locations, rather than a lost memory of any one place: a mouse that had forgotten where the goal had been would not keep the never-used zones correctly sorted, and a mouse that simply moved more would show it in all four panels.

This also explains the compartment result above. The pauses that Hi mice lose in the open interior beyond 2.5 radii from the current goal are mostly pauses at former goals; the open interior is where those zones are.

One convergence is worth noting without overstating it. At phase 8 the single former goal *is* the old place, so the pausing measure and the place-versus-cue measure of Figure 5 are two independent views of the same behaviour — whether the mouse still attends to where the goal used to be. Across all 30 mice, time spent at the former goal in hidden phase 8 and the old-place share with the cue present correlate in the expected direction but do not reach significance (Spearman ρ = +0.32, p = 0.080). Worth stating as a convergence of direction between two measures built from different data, not as a result.

![](figsv3/fig17_former_goals.svg){width=5.6in}

*Figure 10. The set to rule out. Pause time at former goals per session, by phase, with the goal hidden (left) and cued (right). The number of former goals in play grows 0, 1, 2, 3 across the four phases. Faint points are mice, lines are group means ± SE; beneath each panel are the mean per-mouse slopes and the Mann-Whitney comparing those slopes between Hi and WT; numbers above a phase are Hi vs WT at that phase. Pauses at the wall are excluded by the pause definition throughout.*

This is the strongest behavioural result in the report. With the goal hidden, WT mice spend
0, 33, 42 and 82 s at former goals as the set grows, Lo mice 0, 31, 55 and 88, and Hi mice 0, 15,
26 and 28; the per-mouse slopes are +25.3, +28.8 and +9.6 s per phase, and the group × phase
comparison is p = 0.003. With the goal cued the same mice behave alike (slopes +18.6, +18.6 and
+15.0, p = 0.198), so this is not a general difference in how much they pause.

What it says is that a WT mouse treats the history as a list to work through, and that the list
gets longer as the experiment goes on. The Hi mouse does not add to the list.

![](figsv3/nf2_pausemaps.svg){width=6.3in}

*Figure 11. Where they look, with the cue on and off. **a–f** One session per mouse per condition at phase 10, cue present (left) and cue removed (right), for the three mice closest to their group medians across five of the measures in this report (M9 WT, M8 Lo, M5 Hi). Grey is the whole path; each marker is a pause, drawn where it happened and sized by how long it lasted: filled black at the current goal, an open amber ring at one of the three former goals, a pale dot in the open interior. The inner dashed arc is the wall annulus, which the pause measure excludes. **g** Pause time by the kind of place, cue removed, every mouse; bars are mean ± SE with each mouse as a point. **h** The change in total pause time on removing the cue, per mouse, with the group mean ± SE; p beneath each group is the paired t-test, and the bracket is the Mann-Whitney on the change.*

The maps are the group result in one session each. The WT and Lo mice work the history — a
cluster at the current goal and a second at the phase 7 and 8 goals — while the Hi mouse gives 21
pauses and 37 s against 57 and 52 pauses, 129 and 125 s, with its goal pauses on the rim of the
zone rather than inside it.

Panel h is the control stated plainly: removing the cue makes WT mice pause **more**, because the
goal now has to be remembered (+30 s, p = 0.024), and makes Hi mice pause less (−34 s); the change
differs between the groups at p = 0.043.

### Perseveration or failure to update? Time in current and previous goal zones

All mice return to the old goal after the first rotation; WT then drop it, while KO mice keep drifting back to the first location they learned. At phase 10, Hi KO mice no longer favor the current goal and pass through it without stopping, which reads as a failure to update more than perseveration. Lo KO mice show the more perseveration-like pattern, returning to the original trained location at phase 9.

- **Data.** Time in each of the four goal-sized zones, for every probe session (`AllProbes_ByGZLocation.sav`). Current-goal times from this method match the earlier goal times closely (r = 0.99). Entries and rewards exist only for the current goal (from `AllProbeSessions.sav`); a reward needs a 1.2 s stop in the zone.
- **Zone roles.** The current goal is zone 1 at phase 7, zone 2 at phase 8, zone 3 at phase 9 and zone 4 at phase 10. The previous goal is the one from the phase before; the original trained goal is zone 1; never-used zones have not yet been a goal.
- **Share of zone time.** Time in one zone divided by the total time in all four. If a mouse spread its zone time evenly, each zone would get 25%.

**Share of zone time is not accuracy.** The share shows which zone a mouse favors when it is in any of the four candidate zones. It does not show how much time the mouse spends at the goal. KO mice spend less time in the zones overall, so their absolute time at the current goal is lower than WT even where their share matches:

| Hidden session | WT | Lo KO | Hi KO |
|---|---|---|---|
| Phase 9: share of zone time at current goal | 49% | **31%** (p = 0.04) | 47% (p = 0.73) |
| Phase 9: time at current goal, % of session | 3.4% | **1.7%** (p = 0.015) | 2.2% (p = 0.11) |
| Phase 9: time in all four zones, % of session | 6.8% | 6.1% | 4.7% (p = 0.07) |
| Phase 10: share of zone time at current goal | 41% | 32% (p = 0.14) | 32% (p = 0.12) |
| Phase 10: time at current goal, % of session | 3.1% | 1.9% (p = 0.053) | **1.7%** (p = 0.017) |


The same data shown as absolute time in each zone make the loss of the goal easier to see. WT favor the current goal at every phase except the first rotation, where the old and new goals get equal time. Lo KO mice stop favoring any zone from phase 9, and Hi KO mice from phase 10.

![](figsv/gzbars12__fig_bars_hidden.svg){width=6.5in}

*Figure 7. Time in each of the four zones in hidden sessions, by phase and group. The current goal is the coloured bar with a star; former goals are dark grey and zones not yet used as a goal are light grey. "ns" marks a zone whose time is not significantly lower than the current goal's (paired t-test). "Zones differ" is a Friedman test across the four zones. "vs WT" compares the current-goal time with WT (Mann-Whitney U test).*


| Hidden session | WT | Lo KO | Hi KO |
|---|---|---|---|
| Phase 7: zones differ / zones not below current goal | p < 0.001 / none | p = 0.02 / none | p = 0.01 / none |
| Phase 8 | p < 0.001 / zone 1 (old goal) | p = 0.02 / zone 1 (old goal) | p = 0.14 / zones 1, 3, 4 |
| Phase 9 | p < 0.001 / none | **p = 0.39 / zones 1, 2, 4** | p = 0.01 / zone 1 (trained goal) |
| Phase 10 | p < 0.001 / zone 1 (p = 0.06) | p = 0.11 / zones 1, 2 | **p = 0.46 / zones 1, 3** |
| Current-goal time vs WT | | phase 9: 1.7% vs 3.4%, p = 0.015 | phase 10: 1.7% vs 3.1%, p = 0.017 |

- **WT:** the first rotation is the one point where the old goal draws as much time as the new one. From phase 9 the current goal stands clear of every other zone; at phase 10 the original trained zone is the nearest competitor (p = 0.06).
- **Lo KO:** after phase 8 no zone stands out. At phase 9 the original trained zone gets at least as much time as the current goal (2.2% vs 1.7%), and the current goal gets half the WT time.
- **Hi KO:** at phase 9 the current goal still beats every zone except the original trained one. At phase 10 no zone stands out, and both the trained zone and the previous goal draw as much time as the current goal.
- **Visible sessions:** every group spends far more time at the current goal than in any other zone at every phase (Friedman p ≤ 0.02 in all 12 group-by-phase tests), so the loss of a preferred zone is specific to the hidden goal.
- **Tests:** within-group comparisons use paired t-tests because, with five mice, a sign-flip test cannot go below p = 0.06. None is corrected for the number of comparisons.

**Less time at the current goal than WT, and no more there than at the trained zone.** Figure S12 asks the two questions directly. First, is current-goal time lower than in WT? Second, within each group, does the current goal draw more time than zone 1, the original trained location? WT pass the second test clearly from phase 9. Neither KO group does at any rotation. Their current-goal time also falls below WT once the goal has moved twice (phase 9 for Lo, phase 10 for Hi).


| Current-goal time, hidden (% of session) | Phase 7 | Phase 8 | Phase 9 | Phase 10 |
|---|---|---|---|---|
| WT (n = 19) | 4.5 | 2.9 | 3.4 | 3.1 |
| Lo KO (n = 5) | 4.6, p = 0.78 | 2.4, p = 0.30 | **1.7, p = 0.015** | 1.9, p = 0.053 |
| Hi KO (n = 5) | 4.0, p = 0.37 | 2.6, p = 0.40 | 2.2, p = 0.11 | **1.7, p = 0.017** |
| All Pten KO (n = 12) | 4.1, p = 0.65 | 2.4, p = 0.11 | **2.0, p = 0.010** | **1.8, p = 0.008** |

*p-values: Mann-Whitney U vs WT.*

| Current goal vs zone 1, hidden | Phase 8 | Phase 9 | Phase 10 |
|---|---|---|---|
| WT, paired t | 2.9 vs 2.5, p = 0.34 | **3.4 vs 1.4, p < 0.001** (17/19 mice) | 3.1 vs 2.0, p = 0.06 (14/19) |
| Lo KO, paired t | 2.4 vs 2.2, p = 0.57 | 1.7 vs 2.2, p = 0.63 | 1.9 vs 2.8, p = 0.46 |
| Hi KO, paired t | 2.6 vs 1.8, p = 0.31 | 2.2 vs 1.4, p = 0.13 | 1.7 vs 1.3, p = 0.43 |
| Preference (current − zone 1) vs WT, Mann-Whitney: Lo / Hi / all Pten KO | 0.58 / 0.69 / 0.91 | **0.024** / 0.11 / **0.009** | 0.053 / 0.16 / **0.038** |

- **Reading:** KO mice do not just lose time at the goal; they also stop favoring it over the trained location. The preference gap from WT is clearest at phase 9 (Lo and pooled KO). Hi KO follow the same direction but reach significance only for current-goal time at phase 10.
- **Visible sessions:** current-goal time does not differ from WT for any group or phase (all p ≥ 0.12).

**Statistics for this section.**

- **KO vs WT:** two-sided Mann-Whitney U tests, on current-goal time and on the preference (current-goal time minus zone 1 time), as everywhere in the report.
- **Within groups:** paired t-tests, current goal vs zone 1. A Wilcoxon signed-rank test with five mice cannot give p below 0.0625, so it could not detect an effect in the KO groups however consistent.
- **No correction** for multiple comparisons.


**Phase 8, first rotation: every group goes back.** All groups spend more of their zone time at the old (trained) goal than at a never-used zone, and the groups do not differ.

| Phase 8 hidden | Old goal | Never-used zone | Within-group p | Mice favoring old goal | vs WT |
|---|---|---|---|---|---|
| WT | 33.6% | 13.4% | < 0.001 | 17 of 19 | |
| Lo KO | 33.6% | 13.2% | 0.13 | 4 of 5 | p = 0.73 |
| Hi KO | 28.2% | 14.2% | 0.03 | 6 of 6 | p = 0.56 |

**Phase 9: WT learn that the goal moves; KO mice keep drifting back.** WT drop their preference for old zones by 18 points (p < 0.001) and by phase 9 give old zones no more time than never-used ones. KO mice keep favoring old zones by about 11 points, mostly the original trained zone (29–32% vs 20% for WT; KO pooled p = 0.03, Lo p = 0.08, Hi p = 0.12). The difference in how much the preference fades does not reach significance (Hi vs WT p = 0.20; KO pooled p = 0.08).

| Phase 9 hidden, share of zone time | WT | Lo KO | Hi KO |
|---|---|---|---|
| Zone 3, current goal | 49% | **31%** | 47% |
| Zone 1, original trained goal | 20% | **32%** | **29%** |
| Zone 2, previous goal | 15% | 21% | 13% |
| Zone 4, never used | 16% | 16% | **11%** |

- **Hi KO at phase 9:** the current goal is still favored (all six mice), but their extra time at the trained zone comes out of the never-used and previous-goal zones. They know where the goal is, with a leftover pull back to the first location.
- **Lo KO at phase 9:** the extra trained-zone time comes at the expense of the current goal, which they no longer favor. This is driven by M8 and M10; the other three favored the current or another zone.

*Location scope below: pauses and dwell time are counted separately for the current goal and for each of the other three zones.*


**Phase 10: Hi KO mice lose the current goal.** WT clearly favor the current goal over the previous one (p < 0.001). Hi KO mice spend about as long in the previous goal as in the current one (p = 0.50) and spread their time almost evenly across all four zones. Their share at the previous goal tends to be higher than WT's (29% vs 20%, p = 0.06).

| Phase 10 hidden, current goal | WT | Lo KO | Hi KO | Hi vs WT | Lo vs Hi |
|---|---|---|---|---|---|
| Entries | 49 | 32 | 43 | 0.77 | 0.43 |
| Time per entry (s) | 1.16 | 1.07 | **0.76** | 0.04 | 0.13 |
| Rewards per entry | 0.32 | 0.31 | **0.14** | 0.006 | 0.02 |
| Mean speed (cm/s) | 7.9 | 5.9 | **10.2** | 0.03 | 0.009 |

Hi KO mice reach the current goal about as often as WT but do not stop there: five of six average under 1 s per entry. Lo KO mice reach it less often but stop normally when they do. In visible sessions neither KO group has this problem; Lo mice actually stop longer than WT at phase 10 (1.64 vs 1.20 s, p = 0.02).


- **Stopping at the current goal falls with percent KO.** Rewards per entry: r = −0.75, p = 0.01 (ρ = −0.73, p = 0.01).
- **Time in the previous goal zone rises with percent KO** (ρ = +0.62, p = 0.04; Pearson r = +0.53, p = 0.09) and is twice as long in IED+ mice (1.7% vs 0.9% of the session, p = 0.04). All IED+ mice are Hi, so KO level and IEDs cannot be separated.
- **Neither predicts time at the original trained zone** at phase 10.

**Reading.**

- **Hi KO: mainly a failure to update.** By phase 10 they do not favor the new location and do not stop even when they are in it. The extra time at the most recent goal is modest and tracks percent KO and IEDs. Because they pass through the current goal without stopping, they are probably passing through old zones too rather than pausing there; entries for old zones would be needed to confirm this.
- **Lo KO: closer to perseveration** on the first-learned location at phase 9, while still stopping normally at a goal. This rests on two of five mice.
- **Visible sessions** are the control: every group favors the cued goal at every phase, so the deficit is in remembering where the goal is, not in finding or stopping at a visible target.
- None of these single-phase comparisons would survive correction for multiple tests.

## 9. What they do instead, and what a found-it measure cannot show

The last three sections rest on a measurement that most spatial tasks do not make: where and for how long the animal stops. It is worth stating plainly what that buys, because it is the argument for the task as much as for this model.

A found-it-or-didn't measure returns one number per session — Hi mice earn fewer rewards — and every question this report has been able to ask would have been unanswerable. Whether they fail to find the goal or fail to recognise it once there. Whether the memory is lost or intact but unused. Whether the deficit is in the place they are looking for or in the set of places they are working through. Whether it grows with how many candidates there are. Each of those is a different lesion and a different experiment, and the task separates them because it separates the approach from the arrival, repeats the rotation often enough to give every measure a trajectory, and leaves the pause — the animal's own report of where it believes the goal to be — visible in the record.

The cost is that the measures must be stated precisely, and the same pauses answer different questions depending on how they are framed. Twice in building this report a result changed when the framing was corrected: a set of proportions hid a collapse in total pausing, and a split by distance from the current goal hid the fact that the lost pauses were at former goals specifically. Both are recorded below, with the measures labelled, so that they are not confused again.

![](figsv/sm__fig_speed_mode.svg){width=6.5in}

*Figure 14. a: mean speed per probe session by phase, cued (dashed) and hidden (solid), mean ± SE. b: the same comparison within each mouse — speed in the hidden session minus speed in the cued session at the same phase. Negative means the mouse slows down when the marker is removed. Faint points are mice. c: goal-zone entries against rewards at hidden phase 10, one point per mouse, with reference lines at one reward per three and per six entries.*

### What they do instead: running

If Hi mice are not working through the former goals, the obvious question is what they are doing with the session instead. The answer is simple enough to state in a word: running.


Removing the marker ought to slow a mouse down: it now has to work out where the goal is instead of running to a beacon. WT and Lo mice do slow down, at every phase. At the last rotation Hi mice speed up. Comparing each mouse against itself at the same phase, hidden session minus cued:

| Speed, hidden minus cued (cm/s) | Phase 7 | Phase 8 | Phase 9 | Phase 10 |
|---|---|---|---|---|
| WT | −2.42 | −1.81 | −1.72 | **−1.80** (p < 0.001) |
| Pten KO Lo | −1.30 | −0.45 | −0.49 | **−1.13** (p = 0.020) |
| Pten KO Hi | −1.17 | +0.24 | −1.54 | **+1.69** |

Hi versus WT on that difference at phase 10: **p = 0.001**. At phase 7 all three groups slow down when the marker goes, by much the same amount. By phase 10 the Hi group has inverted.

In absolute terms at hidden phase 10 they run at 10.2 cm/s against 7.9 in WT (p = 0.025) and spend 71% of the session in the wall annulus against 66%. And the consequence is in panel c: **they enter the goal zone as often as WT — 43 entries against 49, p = 0.77 — and collect a third of the rewards** (5.5 against 15.2, p = 0.004). They are passing through the right place at the right rate, too fast to collect, because the reward requires 1.2 s stationary.

**This is what resolves the apparent paradox in the search result.** If Hi mice are not visiting the former goals, they ought to carry *less* interference from them, and less interference should help. It does not, because the visits were never interference. There are four possible locations and by phase 10 three of them are former goals, so working through them is simply how a mouse recovers when its first guess is wrong — a short list, and the method the task affords. WT and Lo use it, and it costs them nothing but time they are willing to spend. Dropping it does not clear the Hi group's path; it removes their only systematic route to the answer, and what is left is to cover ground and hope to cross the goal, which they do, at the normal rate and at the wrong speed.

Read that way the arrival result of Section 5 is not a separate finding. A mouse in this mode crosses the goal without slowing because it is not evaluating places at all; the slowing ratio is the signature of the mode, measured at one spot.

**The three groups are therefore three strategies rather than three severities.** WT remember where the marker was and, when wrong, slow down and check the other known places. Lo mice are the most deliberate of the three — slowest at phase 10 (5.9 cm/s), pausing the most — but poorly informed: after a miss they return to the current goal on 2.0% of occasions against 8.8% in WT (p = 0.006), and their pauses fall at the other zones rather than the current one (p = 0.001). Thorough and badly aimed. Hi mice know the current goal about as well as WT but abandon deliberation once the marker is gone. Informed and unsystematic.

![](figsv/miss__ap6_aftermiss.svg){width=6.3in}

*Figure 15. Pauses and returns by zone: the current goal against the other three, which at these phases are a mix of former goals and zones not yet used. Top: phases 8–10 combined, each mouse's rate at the current goal (filled) and the mean over the other three zones (open). Stars: paired t-test, current vs other zones. Note that for Lo mice the difference runs the wrong way, with more returns and pauses at the other zones. Bottom: pauses per session and speed leaving the goal, by hidden phase; symbols mark Mann-Whitney p < 0.05.*

### What the pause is for, and how these measures went wrong twice

It is worth recording the reasoning, because the measures above were built to answer a specific question and the first answers were misleading.

The task was designed on the premise that **the pause is the readout**. A mouse that stops somewhere is telling you where it believes the goal to be; a mouse that runs past is not. Nothing else in the session reports the animal's own estimate so directly — a trajectory says where it went, a reward says whether it was right, but only a pause says where it decided to stop and check. Take that premise seriously and the pause becomes a dependent variable in its own right, which is why these analyses go after it rather than after accuracy alone.

Reading the arrival results that way raised an apparent contradiction. Hi mice cross the goal without slowing, which looks like not knowing where it is; yet they approach by normal directed runs and return after a miss like WT, which looks like knowing. The pause measures were run to settle it, and at first appeared to say the pauses were as accurate as WT's — that the location was known and simply not acted on.

That was an artefact of how the measures were framed. Every one of them was a proportion: the fraction of near-goal pauses falling inside the zone, the share of pause time spent there, the median distance of a pause from the goal. Dividing by the animal's total pausing removes exactly the effect that matters, because the effect *is* in the total. Recomputed as absolute amounts per session, the picture is the one above: Hi mice are not misplacing their pauses, they are making far fewer and shorter ones, and only in the hidden sessions, and increasingly so as the goal moves further from where it was trained.

So the two questions have to be kept apart:

- **How much does the animal stop, and where in the arena?** Pausing at the goal and around it is unchanged. Pausing out in the open interior diverges across the hidden rotations — WT up, Hi down (group × phase p = 0.007) — and does not diverge with the cue (p = 0.98).
- **Where do the stops it makes land relative to the goal?** On the goal, as accurately as WT on all five measures tested.

Neither alone describes the deficit. Together they say that what degrades across the rotations is the strategy of searching — of stopping out in the arena to test candidate places — rather than the aim of the check once it is made. A deficit in accuracy would have shown up as pauses scattered around the goal; this one shows up as the search itself being abandoned, while the goal-directed pauses that remain are placed normally.

Two limits should travel with that statement. Six Hi mice is a small group, and three of them fall inside the WT range at phase 10, so this is a distributional shift and not a property of every mutant animal. The braking thresholds (a 12 cm/s peak, a fall to half of it, 70% of the approach maximum for the run measure) are choices rather than standards, and the braking-distance comparison is made on the subset of runs that braked, which Hi mice supply fewer of; p = 0.050 there is on the line and should not be leaned on. And a null on pause placement at this n cannot exclude a genuinely coarser spatial representation — the measures all lean the expected way, they simply do not reach significance. Distinguishing a degraded memory from an intact one that is no longer consulted would take a targeted experiment, not a reanalysis of these sessions.


The arrival results leave a question: do Hi mice know where the goal is and blow past it, or are they crossing it by chance? Two measures test this, both in every probe session.

- **Coming back.** A miss is an exit from the current goal (to more than 1.3 zone radii) without a reward. For each miss: did the mouse re-enter the goal within 3 s? The control is the same measure after leaving any of the other three zones, which corrects for how active each mouse is.
- **Pausing.** A pause is speed below 3 cm/s for 1.2–10 s, away from the wall. *Location scope: all pauses off the wall, then split by zone.* The 1.2 s minimum is the pause window in the MATLAB code, and longer rests are left out. A pause is "near" a zone if it lies within 2.5 zone radii of the zone's centre. The control is again the other zones.


| Hidden phases 8–10 | WT | Lo KO | Hi KO | Lo vs WT | Hi vs WT | Lo vs Hi |
|----------------------------------------|----------|----------|----------|------------|------------|------------|
| Back in the current goal within 3 s of a miss | 8.8% | 2.0% | 10.5% | **0.006** | 0.30 | **0.008** |
| Back in another zone within 3 s of leaving it | 3.9% | 4.3% | 4.6% | | | |
| Current minus other (returns) | +4.9 | −2.3 | +5.9 | **0.001** | 0.69 | **0.004** |
| Pauses at the **current goal** | 27% | 14% | 28% | **0.001** | 0.69 | 0.43 |
| Pauses at **another zone**, each (former goals and not-yet-used alike) | 19% | 24% | 18% | | | |
| Current minus other (pauses) | +7.9 | −9.5 | +10.0 | **0.001** | 0.64 | 0.13 |

*Means of mice. p: Mann-Whitney between groups. Within group, current vs other zones (paired t-test): returns WT p = 0.0002, Lo p = 0.06 (current lower), Hi p = 0.025; pauses WT p = 0.004, Lo p = 0.019 (current lower), Hi p = 0.26.*

- **Hi KO mice know where the goal is.** After a miss they come back to the current goal as often as WT (10.5% vs 8.8% of misses), more than twice as often as they come back to any other zone (p = 0.025). They pause near the current goal as often as WT (28% vs 27% of pauses).
- **But they do not settle at phase 10.** They pause about half as often overall — *all pauses off the wall, not only those at the goal* — (28 vs 50 pauses per session, p = 0.024), and they leave the goal faster (23.4 vs 19.0 cm/s, p = 0.017; also faster at phase 9, p = 0.043). Their preference for the current goal over the other zones is also weaker: for pauses it is not significant within the group (p = 0.26), where WT's is (p = 0.004).
- **Lo KO mice do not know where the goal is once it has moved.** After a miss they rarely come back (2.0% of misses), less often than they come back to the other zones. Their pauses fall near the other zones rather than the current goal (14% vs 24%), most clearly at phase 9: there 26% of their pauses are near another zone, against 17% for WT (p = 0.001) and 15% for Hi (p = 0.010).
- **The Lo pattern is specific to the hidden goal.** With the cue visible, Lo mice come back to the goal more than to the other zones (9.9% vs 2.9%, p = 0.008) and pause near it as often as WT (32% vs 30%). They do come back less often than WT in visible sessions too (9.9% vs 16.7%, p = 0.024), so part of the hidden-session gap is their lower activity. The within-mouse comparison with the other zones is the clean test, and in hidden sessions it runs the wrong way only for Lo.
- **Robustness.** With a 5 s window the Lo result holds (Lo vs WT p = 0.024, Lo vs Hi p = 0.030); with 10 s it weakens (p = 0.09). The Hi phase 10 differences (pauses, exit speed) come from many tests at p ≈ 0.02 and are best called suggestive.

**Reading.**

- **Why the visible–hidden contrast matters, even in WT.** The visible and hidden sessions work like the cued and hidden-platform versions of the Morris water maze, on dry land. A cued goal can be reached by heading for a landmark; a hidden goal only from a remembered place, which depends on the hippocampus. WT mice launch later and less directly toward a hidden goal, which is what a shift from cue-guided to memory-guided navigation should look like in the path.
- **Goal rotations add interference.** Each new location has to be learned against the memory of the previous ones, which also loads working memory. In WT the visible–hidden launch gap is largest at phases 8 and 10. In Hi mice, reward per directed run falls with each rotation while their approach stays normal. That fits Hi mice being less able to hold the current location against accumulated interference, or reaching a working-memory limit sooner.
- **Pten KO does not change the approach.** No measure of how the mice move toward the goal separates the groups.
- **Lo KO: not knowing where, once the goal has moved.** Lo mice rarely come back to the goal after a miss and pause near the wrong zones, but stop normally when they reach the goal.
- **Hi KO: approaching everything, committing to nothing.** Hi mice navigate normally once a destination is chosen, and they slow at the former goals as often as WT (braking rate 14.72 against 15.21 per 10 m, p = 0.93). What fails is everything downstream of the approach: they dwell at those places for a third as long (28 s against 82 s), they brake least of the three groups at the current goal (6.05 against 9.15, p = 0.004) and on only 38% of directed runs against 56% (p = 0.045), and by phase 10 they are pausing anywhere for 59 s a session against 134 s (p = 0.006). None of it appears when the goal is cued.

That is the argument for the task, and it is why these measures were built the way they were. This should make John Kubie happy.

### A note on which pause analyses specified where to look

The measures above differ in whether a location was built into them, and that distinction is what resolved the confusion in this section. Stated plainly:

- **Figure 8 and the arrival profile** are **location-specified**: they are triggered on entries into the current goal zone and describe only what happens around it.
- **The pause-placement measures** (the share of near-goal pauses falling inside the zone, the share of pause time spent there, the median distance of a near-goal pause, the duration of in-zone pauses) are **location-specified** and additionally conditional: they describe where pauses land *given* that the mouse paused near the goal. They are proportions, so they say nothing about how much the mouse paused.
- **Total pause time in Figure 16c** is **not location-specified**: it is every pause anywhere in the arena. The one location constraint is in the pause definition itself, which excludes the wall annulus beyond 0.8 of the arena radius, so it is the whole interior and no thigmotaxis.
- **The compartment split in Figure 16d** is **location-specified after the fact**, by distance from the current goal only, without regard to which zone a pause was near.
- **Figure 10** is **location-specified by zone identity**: each pause is assigned to the current goal, a former goal, a never-used zone, or none of them.

Reading a proportion as though it were an amount is what made the pauses look normal when the pausing had collapsed; reading distance-from-the-current-goal as though it were place identity is what made the collapse look general when it was specific to former goals. Both are stated here so the measures are not mistaken for one another later.

## 10. Does the deficit scale with the load?

The hidden probes run 7, 8, 9, 10, and at each rotation the goal moves to a zone that has not been used before. So the number of former goals a mouse has to hold and rule out grows 0, 1, 2, 3 across the four sessions. Several measures in this report have a slope across those phases, and they have been scattered through it. Gathered in one place they make a more persuasive case than any of them does alone.


Read from the top. The two measures that separate the groups are both about pausing: how much time the mice spend at former goals (+25.3 s per phase in WT against +9.6 in Hi, p = 0.003) and how much they pause in total (+5.9 against −14.4, p = 0.036). Below them the slowing ratio and reward rate lean the same way without reaching significance (p = 0.069 and 0.098). At the bottom are the two controls: pausing at zones that were never goals, and pausing at the current goal, where the three groups are indistinguishable (p = 0.64 and 0.93).

Two things are worth drawing out of that ordering.

**The groups diverge on what grows with the load, and not on what does not.** The number of never-used zones *falls* across the rotations, and all three groups abandon them at the same rate. The current goal is one place at every phase, and all three groups treat it alike. Only the measure that tracks the growing set — time spent at former goals — separates them. A general deficit in pausing, in motivation or in locomotion would not respect that distinction.

**Lo mice are not intermediate here.** On every row of the figure Lo mice sit with WT, and on the top row they slightly exceed them (+28.8 s per phase). Whatever is wrong in the Hi group is not a graded consequence of carrying some KO cells; it appears above a threshold of KO load, in the group that also shows the cue dominance of Section 3.

Mice do get worse with rotation, but only in the hidden sessions, and the first drop (trained to novel) is shared by WT. What differs between groups is what happens after that: WT level off, Lo KO mice become steadily less active, and Hi KO mice keep losing rewards while speeding up.

![](figsv3/fig09_phase10_zones.svg){width=6.9in}

*Figure 16. Hidden phase 10, zone measures. **A** Time in each zone, each mouse a small point (diamonds: IED+) and the group mean ± SE; time per entry into the current goal, with the dashed line at the 1.2 s stop needed for a reward; entries into the current goal. **B** The same measures against percent KO, with the best-fit line and 95% confidence band through the Pten KO mice; WT shown at 0% for reference and not included in the fit; Spearman p above each panel.*

### Is the decline across hidden probes steady, and does it differ from WT?

Hi KO mice lose rewards and gain target speed across the hidden probes. Their rate of change differs from WT on two tests: target speed across all four phases, and rewards across the novel locations. Lo KO mice do not differ from WT in rate of change on any measure shown here; their deficit is present from the start and stays about the same size.


Mean change per phase, with its test against zero in brackets, and the comparison of each KO group's slopes with WT:

| Measure | Window | WT | Lo KO | Hi KO | Lo vs WT | Hi vs WT |
|---|---|---|---|---|---|---|
| Rewards | 7–10 | −1.19 (0.10) | −1.42 (0.16) | **−2.90 (0.003)** | 0.73 | 0.11 |
| Rewards | 8–10 | +1.11 (0.18) | 0.00 (1.00) | −2.50 (0.12) | 0.53 | **0.04** |
| Rewards per entrance | 7–10 | −0.007 (0.61) | +0.024 (0.28) | **−0.023 (0.02)** | 0.37 | 0.60 |
| Rewards per entrance | 8–10 | +0.008 (0.70) | +0.019 (0.61) | −0.047 (0.18) | 0.72 | 0.24 |
| Proportion time in goal | 7–10 | −0.0030 (0.07) | **−0.0069 (0.004)** | **−0.0069 (0.03)** | 0.14 | 0.20 |
| Proportion time in goal | 8–10 | +0.0015 (0.36) | −0.0031 (0.07) | −0.0045 (0.33) | 0.10 | 0.25 |
| Target speed (cm/s) | 7–10 | +0.93 (0.06) | +0.30 (0.49) | **+2.13 (0.005)** | 0.53 | **0.007** |
| Target speed (cm/s) | 8–10 | +0.47 (0.53) | −1.02 (0.18) | +2.28 (0.07) | 0.18 | 0.08 |

- **Hi KO, all four phases:** a consistent trend within the group on all four measures. Every Hi mouse loses rewards and gains target speed. Only the target-speed slope differs from WT (p = 0.007); for the others, WT also fall from the trained location to the first novel one. One WT mouse, M2, has a far steeper target-speed slope than any other mouse (+8.5 cm/s per phase), because it earned only 1–2 rewards at phases 9–10 and its target speed rests on very few goal visits. A rank test is barely affected by it; a test on means would miss the effect (p = 0.18 with M2, 0.002 without).
- **Hi KO, novel locations only:** WT recover by 1.1 rewards per phase while Hi lose 2.5, and those slopes differ (p = 0.04). This is the one test that supports a rotation effect specific to Hi KO. The other three measures move the same way without reaching significance.
- **Lo KO:** time in goal falls steadily across all four phases (p = 0.004), but no Lo slope differs from WT on any measure in either window. Rewards are flat across the novel locations.
- **Time in goal:** Lo and Hi decline at the same rate (−0.0069 per phase), so this measure does not separate the KO levels.
- **The Hi decline is not smooth.** The Hi group mean for rewards is flat from phase 8 to 9 (10.5 and 10.5), with the further loss between phases 9 and 10.

So the data support "Hi KO mice diverge from WT in rewards across the novel locations." They do not establish a loss at each successive rotation: two of eight Hi-vs-WT slope tests reach p < 0.05, uncorrected, and with three novel locations a single late drop cannot be told apart from a progressive decline.

![](figsv3/fig10_phase10_perf.svg){width=6.9in}

*Figure 17. Hidden phase 10, performance measures. **A** Each measure against percent KO; the blue band is the WT mean ± SE and the dashed line a linear fit through the Pten KO mice. **B** The same measures by group. The Hi KO mice deviate from WT; the Lo KO mice match WT on rewards per entrance and target speed but move more slowly and earn fewer rewards. Diamonds: IED+ mice.*

### Does percent KO predict outcome in each phase?

Percent KO predicts behavior only at the last hidden probe, where higher KO goes with worse performance: the Hi KO mice move faster in the goal zone and earn fewer rewards per entrance. At the trained location and the first two novel locations it predicts nothing, and it predicts nothing in any visible session. Correlations are Spearman, across the 11 Pten KO mice with histology.


| Hidden session, phase 10 | ρ with % KO | p |
|---|---|---|
| Mean target speed | +0.75 | 0.007 |
| Rewards per entrance | −0.75 | 0.008 |
| Mean speed | +0.67 | 0.02 |
| Rewards | −0.51 | 0.11 |


- **Hidden, phases 7–9:** no correlation reaches p < 0.05 on any measure. The nearest are at phase 8 (rewards per entrance ρ = −0.57, p = 0.07; mean speed ρ = +0.55, p = 0.08), in the same direction as phase 10.
- **Visible, all phases:** no correlation reaches p < 0.05 (smallest p = 0.08).
- **Corrected for 64 tests:** the best phase-10 correlations have q = 0.24, so they do not survive correction.
- **Change with rotation:** in visible sessions, mice with less KO gained more rewards per entrance from the trained to the novel locations (ρ = −0.83, p = 0.002). In hidden sessions, percent KO does not predict the size of the trained-to-novel drop on any measure (all p > 0.15).

These correlations carry the same limitation as sessions to criterion. The KO percentages form two clusters, so a correlation here is close to a restatement of the Lo vs Hi difference at that phase, and it cannot show a graded dose effect.

![](figsv3/fig11_slopes.svg){width=6.2in}

*Figure 18. Slopes across the hidden rotations. **A** Every measure with a slope across the four hidden rotations: per-mouse least-squares slope, standardised by the SD of the per-mouse slopes for that measure so that measures in different units sit on one axis; points are group means ± SE; p values are Hi versus WT on the unstandardised slopes (Mann-Whitney). **B** Share of directed runs to the current goal that end in a reward across the hidden probes: each mouse (thin) and the group mean (thick), and each mouse's slope across phases 7 to 10 in hidden (circles) and visible (squares) sessions.*

### Visible sessions

No group loses performance with rotation when the cue is present. Both KO groups earn more rewards at novel locations than at the trained one (Lo +29%, p = 0.03; Hi +25%, p = 0.08), where WT are flat (−1%).

- **Lo KO:** rewards per entrance rise by 0.07 per phase (p < 0.001) and mean speed falls by 0.8 cm/s per phase (p = 0.03). The rise in rewards per entrance from trained to novel is larger than in WT (p = 0.004) and larger than in Hi (p = 0.03).
- **Hi KO:** no significant trend on any visible measure.
- **WT:** no significant trend on any visible measure; rewards per entrance rise slightly (0.014 per phase, p = 0.07).

### Does reward per directed run fall across the rotations?


- **Two tests of the slope.** Per mouse: the linear slope across phases, with the mouse as the unit, compared between groups by Mann-Whitney and against zero by a one-sample t-test. Per run: every directed run scored as rewarded or not, in a logistic regression with group × phase, with standard errors clustered by mouse (generalized estimating equations). The per-run test uses all runs and has more power, but with 5–6 mice per KO group its clustered errors are approximate.

| Hidden sessions | Hi vs WT | Hi vs Lo | Lo vs WT |
|------------------------------------------------------|----------------------|----------------------|----------------------|
| Per-mouse slope, phases 7–10 | 0.22 | **0.017** | 0.18 |
| Per-mouse slope, phases 8–10 | 0.14 | 0.052 | 0.27 |
| Per-run group × phase, phases 7–10 (odds ratio per phase) | **0.016** (0.79) | **0.0001** (0.60) | **0.032** (1.33) |
| Per-run group × phase, phases 8–10 | **0.015** (0.62) | **0.014** (0.47) | 0.35 (1.30) |
| Visible sessions, per-run, phases 7–10 | 0.21 (1.12) | 0.42 (0.92) | **0.007** (1.22) |

*Odds ratio: how much one more phase multiplies the odds that a directed run ends in a reward, in the first group relative to the second.*

- **Within the Hi group the decline is very consistent.** All six Hi mice fall from phase 7 to 10, by 3.6–7.3 percentage points per phase (mean −5.1 ± 0.6, p < 0.001 against zero). WT mice are flat on average (−1.1 ± 2.0, p = 0.58) but vary widely, from −13.6 to +14.3. Lo mice rise (+5.5 ± 3.1, p = 0.15).
- **Against WT, the mouse-level test is not significant** (p = 0.22), because the WT slopes are so spread out: every Hi slope lies inside the WT range, in its lower half. Against Lo it is (p = 0.017).
- **The per-run test separates Hi from both groups.** Each hidden rotation multiplies the odds that a Hi directed run ends in a reward by 0.79 relative to WT (p = 0.016) and 0.60 relative to Lo (p = 0.0001). Over phases 8–10 alone the ratios are 0.62 (p = 0.015) and 0.47 (p = 0.014).
- **The decline needs the hidden goal.** Hi mice show no decline when the goal is cued (slope +3.3 ± 2.2 per phase; per-run vs WT p = 0.21). Lo mice improve across the visible probes (+7.0 ± 1.7, p = 0.015; per-run vs WT p = 0.007), the same rise in rewards per entrance reported earlier.
- **Which test to lead with.** The per-mouse slope is the conservative test for 5–6 mice and gives a clear Hi vs Lo difference and a consistent within-Hi decline. The per-run model is the stronger evidence that the Hi slope also differs from WT, with the caveat about few clusters.

# Part II — The circuit

## 11. Theta CSD by layer

This section uses the current channel-level CSD file and the CNO behavior file. Hi KO mice start with about twice the WT theta CSD, and CNO brings it back to the WT level without changing WT. The excess current sits in the middle molecular layer and granule cell layer of the infrapyramidal blade (MML2, GCL2), not in the suprapyramidal blade (MML1, GCL1). At baseline the same current identifies the mice with clear IEDs, and after CNO it no longer does. In behavior, hidden-goal time rises after CNO in Pten KO mice and falls in WT. With the cue visible, CNO has no genotype-specific effect.

- **Sources.** Theta CSD from `CSD_sansM2.sav`, one row per recording channel with its layer label, baseline and after CNO. Goal-zone time from `AllProbeSessions_CNO.sav`. Percent KO from `Data4Claude.xlsx`, plus the project list for M29 (22.00%) and M30 (5.97%). These replace the per-mouse CSD summary in `Data4Claude.xlsx`, which differed from the channel file in four sessions (M3 baseline; M11, M13 and M28 after CNO).
- **Measures.**
  - **Theta CSD per layer:** the mean of all channels labeled with that layer in the session.
  - **4-layer average:** all channels in MML1, MML2, GCL1 and GCL2 pooled. This is how the earlier summary values were computed.
  - **MML2 + GCL2:** the channels of those two layers pooled.
  - **Goal-zone time:** the mean of probe phases 8 and 9 as a percentage of the session, for hidden and visible sessions separately.
- **M26 (WT) is excluded from the theta CSD analyses.** A problem after the electrode implantation surgery means its recordings are not used. It stays in the behavioral analyses, because its behavioral testing took place before implantation.
- **Mice.**
  - **Theta CSD:** 10 WT at baseline, 8 of them also after CNO (M47 and M51 did not get CNO). 6 Lo (M1, M8, M10, M11, M30, M33) and 7 Hi (M3, M5, M7, M13, M28, M29, M34), all with both sessions.
  - **IED mice:** M3, M5, M13, M28 and M34. The 8 KO mice without IEDs include two Hi mice, M7 and M29.
  - **Goal-zone time, baseline and CNO:** 11 WT, 5 Lo (M1, M8, M10, M30, M33) and 6 Hi (M3, M5, M7, M28, M29, M34). The baseline regression also includes the 8 WT mice tested only at baseline (n = 30).
  - **Other details:** M59 has two baseline CSD sessions and s4 is used. M2 has two visible CNO sessions at phase 9 and both are averaged. M27 and M31 have no histology and are not included.
- **The WT control.** WT mice also carry the DREADD, in about 5% of granule cells, so in them CNO silences a small set of normal granule cells.
- **Plots.** In the style of LaSarge et al. (2021): each measure against percent KO with WT at 0%, a least-squares line through all mice and its 95% confidence band.
- **Tests.**
  - **Between groups:** Mann-Whitney.
  - **Within groups, baseline vs CNO:** paired t-test.
  - **Group × drug:** a mixed model with a random intercept per mouse.
  - **ROC for clear IEDs:** WT counted as IED-negative, bootstrap confidence intervals. The loss of AUC with CNO is tested by a paired bootstrap on the same mice.

### Theta CSD by layer


| Theta CSD, 4-layer average | WT | Lo KO | Hi KO | Lo vs WT | Hi vs WT | Lo vs Hi |
|------------------------------|----------|----------|----------|----------|----------|----------|
| Baseline (n = 10 / 6 / 7) | 0.019 | 0.026 | 0.037 | 0.15 | **0.043** | 0.45 |
| After CNO (n = 8 / 6 / 7) | 0.022 | 0.023 | 0.029 | 0.75 | 0.61 | 0.84 |
| Change with CNO | +12% | −10% | −22% | 0.49 | **0.006** | 0.37 |
| Mice that fall with CNO | 3 of 8 | 3 of 6 | 6 of 7 | | | |
| Paired p, baseline vs CNO | 0.19 | 0.60 | **0.012** | | | |
| Group × drug p (vs WT) | | 0.22 | **0.009** | | | |

*Columns 5–7: Mann-Whitney p.*

| By layer (all mice) | 4-layer average | MML2 + GCL2 | MML2 | GCL2 | MML1 | GCL1 |
|------------------------------|----------|----------|----------|----------|----------|----------|
| Baseline: WT / Lo / Hi | 0.019 / 0.026 / 0.037 | 0.018 / 0.029 / 0.046 | 0.016 / 0.025 / 0.044 | 0.019 / 0.035 / 0.048 | 0.021 / 0.022 / 0.028 | 0.020 / 0.024 / 0.023 |
| Hi vs WT, baseline | **0.043** | **0.007** | **0.043** | **0.005** | 0.67 | 0.74 |
| Hi change with CNO (paired p) | −22% (**0.012**) | −31% (**0.004**) | −34% (**0.013**) | −31% (**0.022**) | +4% (0.90) | −9% (0.71) |
| Hi × drug | **0.009** | **0.014** | **0.035** | **0.029** | 0.70 | 0.21 |
| All KO × drug | **0.023** | 0.099 | 0.30 | 0.068 | 0.55 | **0.045** |
| Baseline vs % KO, r (p) | +0.53 (**0.009**) | +0.57 (**0.005**) | +0.56 (**0.006**) | +0.47 (**0.024**) | +0.27 (0.21) | +0.20 (0.36) |
| After CNO vs % KO, r (p) | +0.19 (0.41) | +0.29 (0.21) | +0.40 (0.075) | +0.15 (0.51) | −0.02 (0.92) | −0.10 (0.65) |
| Change vs % KO, r (p) | −0.55 (**0.010**) | −0.47 (**0.032**) | −0.40 (0.076) | −0.43 (**0.049**) | −0.24 (0.30) | −0.22 (0.33) |

*Regressions: all mice, WT at 0% KO; n = 23 at baseline and 21 after CNO.*

- **Hi KO mice start with about twice the WT current, and CNO brings it back.** For the 4-layer average, Hi mice are at 0.037 against 0.019 for WT (p = 0.043). Six of seven Hi mice fall with CNO (−22%), and after CNO no group differs from WT. CNO does not change WT CSD (+12%, p = 0.19). The group × drug interaction for Hi vs WT holds when any single Hi mouse is left out (p = 0.004–0.029).
- **The excess is in MML2 and GCL2.** At baseline Hi mice are 2.7 times WT in MML2 and 2.5 times in GCL2, against 1.3 and 1.2 times in MML1 and GCL1. The Hi drop with CNO (−31 to −34%), its interaction with genotype and the link to percent KO are all present in MML2 and GCL2. None of them appears in MML1 or GCL1.
- **With WT at 0%, CSD tracks percent KO at baseline, and CNO removes the relationship.** For the 4-layer average, r = +0.53 at baseline, +0.19 after CNO and −0.55 for the change. The larger the KO, the larger the fall. Within the KO mice alone no layer tracks percent KO (r = +0.10 to +0.36, all p > 0.2), so the relationship rests mainly on the step from WT to KO.
- **All Pten KO mice together** start above WT (0.032 vs 0.019, p = 0.032), fall with CNO (−17%, paired p = 0.049) and match WT afterwards (p = 0.60). Group × drug for all KO vs WT is p = 0.023.
- **Two smaller points.**
  - GCL2 is the only layer where Lo mice are above WT at baseline (0.035 vs 0.019, p = 0.031).
  - GCL1 shows an all-KO × drug interaction (p = 0.045) with no baseline difference behind it: GCL1 rises 21% in WT with CNO and falls 31% in Lo. I would treat this as a lead, not a finding.
- **MML2 + GCL2 is not detectably better than the 4-layer average.** The two are almost the same measure across mice (r = 0.96 at baseline), because MML2 and GCL2 drive most of the variation in the average. Paired bootstrap, MML2 + GCL2 minus the average:
  - IED AUC at baseline: +0.07 (95% CI 0.00 to +0.23, p = 0.65).
  - Correlation with percent KO at baseline: +0.04 (p = 0.38).
  - For the CNO change, the average correlates slightly more strongly (p = 0.39).

  So the layer result is about where the signal sits, not about a better measure.

![](figsv/csd3__fig28_layer_profile_lohi.svg){width=6.4in}

*Figure 19. Theta CSD by layer for WT, Pten KO Lo and Pten KO Hi: baseline, after CNO and the change. Mean ± SE across mice; shaded row: WT hilus, the reference. One star: p < 0.05 vs WT hilus (GEE); two stars: also after Holm correction within the panel.*

### Layer profile, baseline and after CNO

Averaging each layer across mice shows the same picture as Figure 20 from another angle. At baseline the current peaks at GCL2 and MML2 in KO mice, most in Hi and IED mice. After CNO the GCL2 peak comes back to the WT level, while MML2 keeps about half of its excess.

- **Method.** Each mouse's value for a layer is the mean of its channels in that layer. The layers run top to bottom as along the probe, from CA1 to the infrapyramidal blade.
- **Statistics.** As in the lab's earlier analysis: a GEE (Gaussian, exchangeable correlation, clustered by mouse) with one term per group × layer cell and the WT hilus as the reference cell. It is run separately for baseline, after CNO and the change, with Holm correction across the cells of each panel. GCL2 and MML2 are also tested directly against WT in the same layer (Mann-Whitney) and before vs after CNO within group (paired t-test).
- **WT layers.** No WT layer differs from the WT hilus at baseline, after CNO or in its change (all p ≥ 0.07).


*Mean theta CSD by layer, WT / Lo / Hi (n = 10 / 6 / 7 at baseline; 8 WT after CNO).*

| Layer | WT: baseline → CNO | Lo: baseline → CNO | Hi: baseline → CNO |
|---|---|---|---|
| CA1 SP | 0.015 → 0.015 | 0.010 → 0.009 | 0.017 → 0.012 |
| CA1 SLM | 0.020 → 0.020 | 0.017 → 0.014 | 0.021 → 0.017 |
| OML1 | 0.025 → 0.028 | 0.023 → 0.021 | 0.022 → 0.026 |
| MML1 | 0.021 → 0.026 | 0.022 → 0.021 | 0.028 → 0.029 |
| GCL1 | 0.019 → 0.026 | 0.024 → 0.016 | 0.023 → 0.021 |
| Hilus | 0.020 → 0.023 | 0.023 → 0.027 | 0.022 → 0.015 |
| GCL2 | 0.019 → 0.022 | 0.035 → 0.030 | 0.048 → 0.033 |
| MML2 | 0.016 → 0.014 | 0.025 → 0.025 | 0.044 → 0.029 |
| OML2 | 0.012 → 0.015 | 0.025 → 0.021 | 0.031 → 0.029 |

*GEE p vs WT hilus, Lo and Hi. Bold: p < 0.05; †: also after Holm correction within the panel.*

| Layer | Lo: baseline | Lo: CNO | Lo: change | Hi: baseline | Hi: CNO | Hi: change |
|---|---|---|---|---|---|---|
| CA1 SP | **<0.001**† | **0.002**† | 0.200 | 0.522 | **0.023** | 0.165 |
| CA1 SLM | 0.459 | 0.058 | 0.159 | 0.830 | 0.420 | 0.123 |
| OML1 | 0.467 | 0.842 | 0.317 | 0.711 | 0.687 | 0.940 |
| MML1 | 0.639 | 0.723 | 0.379 | 0.180 | 0.528 | 0.710 |
| GCL1 | 0.410 | 0.232 | **0.033** | 0.493 | 0.765 | 0.316 |
| Hilus | 0.468 | 0.646 | 0.891 | 0.573 | 0.149 | **0.019** |
| GCL2 | **0.015** | 0.415 | 0.370 | **0.012** | 0.323 | **0.001**† |
| MML2 | 0.371 | 0.781 | 0.596 | **0.009** | 0.351 | **<0.001**† |
| OML2 | 0.339 | 0.828 | 0.329 | 0.192 | 0.223 | 0.401 |

*Mean theta CSD by layer, WT / KO without IEDs / KO with IEDs (n = 10 / 8 / 5 at baseline; 8 WT after CNO).*

| Layer | WT: baseline → CNO | KO, no IEDs: baseline → CNO | KO, IEDs: baseline → CNO |
|---|---|---|---|
| CA1 SP | 0.015 → 0.015 | 0.012 → 0.011 | 0.017 → 0.011 |
| CA1 SLM | 0.020 → 0.020 | 0.014 → 0.012 | 0.026 → 0.021 |
| OML1 | 0.025 → 0.028 | 0.020 → 0.019 | 0.025 → 0.032 |
| MML1 | 0.021 → 0.026 | 0.020 → 0.019 | 0.032 → 0.035 |
| GCL1 | 0.019 → 0.026 | 0.022 → 0.016 | 0.025 → 0.024 |
| Hilus | 0.020 → 0.023 | 0.022 → 0.024 | 0.024 → 0.015 |
| GCL2 | 0.019 → 0.022 | 0.031 → 0.026 | 0.058 → 0.040 |
| MML2 | 0.016 → 0.014 | 0.023 → 0.022 | 0.055 → 0.035 |
| OML2 | 0.012 → 0.015 | 0.026 → 0.022 | 0.032 → 0.031 |

*GEE p vs WT hilus, KO without and with IEDs. Bold: p < 0.05; †: also after Holm correction within the panel.*

| Layer | No IEDs: baseline | No IEDs: CNO | No IEDs: change | IEDs: baseline | IEDs: CNO | IEDs: change |
|---|---|---|---|---|---|---|
| CA1 SP | **0.007** | **0.007** | 0.222 | 0.623 | **0.010** | 0.165 |
| CA1 SLM | 0.139 | **0.022** | 0.164 | 0.322 | 0.875 | 0.116 |
| OML1 | 0.934 | 0.530 | 0.292 | 0.349 | 0.412 | 0.840 |
| MML1 | 0.878 | 0.432 | 0.257 | 0.074 | 0.270 | 0.912 |
| GCL1 | 0.577 | 0.144 | **0.030** | 0.319 | 0.820 | 0.468 |
| Hilus | 0.514 | 0.818 | 0.690 | 0.528 | 0.161 | **0.009** |
| GCL2 | **0.027** | 0.625 | 0.239 | **0.002** | 0.173 | **<0.001**† |
| MML2 | 0.544 | 0.941 | 0.466 | **<0.001**† | 0.070 | **<0.001**† |
| OML2 | 0.257 | 0.930 | 0.267 | 0.253 | 0.188 | 0.524 |

| GCL2 and MML2 | Baseline → CNO | Paired p | vs WT, baseline | vs WT, after CNO | Excess over WT removed by CNO |
|---|---|---|---|---|---|
| GCL2, Lo | 0.035 → 0.030 | 0.66 | **0.031** | 0.85 | 48% |
| GCL2, Hi | 0.048 → 0.033 | **0.022** | **0.005** | 0.87 | 62% |
| GCL2, KO no IEDs | 0.031 → 0.026 | 0.51 | **0.034** | 0.88 | 64% |
| GCL2, KO with IEDs | 0.058 → 0.040 | **0.042** | **0.001** | 0.44 | 54% |
| MML2, Lo | 0.025 → 0.025 | 1.00 | 0.22 | 0.28 | none |
| MML2, Hi | 0.044 → 0.029 | **0.013** | **0.043** | 0.072 | 47% |
| MML2, KO no IEDs | 0.023 → 0.022 | 0.92 | 0.32 | 0.38 | none |
| MML2, KO with IEDs | 0.055 → 0.035 | **0.007** | **0.008** | **0.019** | 46% |

*vs WT: Mann-Whitney against WT in the same layer. Excess removed = 1 − (group − WT after CNO) / (group − WT at baseline). WT GCL2 0.019 → 0.022, MML2 0.016 → 0.014.*

- **At baseline the excess current sits at GCL2 and MML2.**
  - **Hi mice:** GCL2 0.048 and MML2 0.044, against the WT hilus at 0.020 (p = 0.012 and 0.009).
  - **IED mice:** the peak is higher, GCL2 0.058 and MML2 0.055 (p = 0.002 and < 0.001; MML2 survives correction).
  - **No other KO layer is above the WT hilus.**
- **Lo mice, and KO mice without IEDs, have a smaller GCL2 peak that also counts.**
  - **Lo:** GCL2 0.035, above the WT hilus (p = 0.015) and above WT GCL2 (p = 0.031).
  - **KO without IEDs:** GCL2 0.031 (p = 0.027 and 0.034).
  - **After CNO** neither differs from the WT hilus (p = 0.42 and 0.63) or from WT GCL2 (p = 0.85 and 0.88).
  - **Their MML2 is not elevated** (Lo 0.025, p = 0.37 against the WT hilus), so in these mice the excess is confined to the granule cell layer.
- **CNO brings GCL2 back to the WT level in every KO group.** After CNO no KO group's GCL2 differs from WT (p = 0.44–0.88), and the GCL2 drop in Hi and IED mice is among the changes that survive correction.
- **MML2 moves toward WT but keeps about half its excess.** In Hi and IED mice CNO removes 46–47% of the MML2 excess, against 54–62% at GCL2. IED mice are still above WT at MML2 after CNO (0.035 vs 0.014, p = 0.019). This matches the ROC (Figure 21): some IED separation in MML2 survives CNO (AUC 0.80), while that at GCL2 is lost (0.66).
- **Lo and Hi do not differ from each other at GCL2 or MML2** at baseline, after CNO or in the change (p ≥ 0.10). IED and non-IED KO mice differ at MML2 (baseline p = 0.011, change p = 0.019) but not at GCL2 (p = 0.065).
- **Smaller points.**
  - CA1 SP sits below the WT hilus in Lo and KO mice without IEDs. CA1 SP is the lowest layer in every group, so this is not part of the dentate story.
  - The GCL1 drop in Lo (p = 0.033) is the same GCL1 oddity as in the regressions.
  - The hilus falls a little with CNO in Hi and IED mice (p = 0.019 and 0.009, uncorrected).
- **Reading: activity versus structure.** CNO silences the DREADD-expressing granule cells, and the current at GCL2, where the KO cell bodies are, returns to the WT level: that part of the excess is driven by their activity. MML2 is where the medial perforant path synapses onto the middle third of the granule cell dendrites. Pten KO cells there carry many more spines and larger dendrites, and that synaptic structure does not change because firing is down. So inactivating the KO cells helps, but part of the synaptic excess remains. This is the same split the ROC shows, with MML2 still partly separating the IED mice after CNO.

![](figsv3/fig12b_csd_regression.svg){width=6.0in}

*Figure 20. Theta CSD against percent KO for the three lower-blade measures: MML2 + GCL2, MML2 and GCL2. Columns: baseline, after CNO, and the change. Blue: WT (plotted at 0%, slightly spread); green: Lo KO; red: Hi KO; diamonds: IED+. Dashed line: 15% KO. The 4-layer average, and the same plots for MML1 and GCL1, are Supplementary Figure S1.*

![](figsv3/fig12c_roc.svg){width=6.0in}

*Figure 21. Theta CSD as a predictor of clear IEDs, for the same three measures. Left: ROC curves at baseline (solid) and after CNO (dashed), with the loss of AUC. Right: each mouse's CSD at baseline and after CNO, by WT, KO without IEDs and KO with IEDs; dashed line: the best baseline cutoff; black: group means; above the panel, the CNO drop itself as a predictor. MML1 and GCL1 are Supplementary Figure S2.*

## 12. The DREADD works: CNO silences hM4D-expressing Pten KO granule neurons

Everything in this section rests on CNO actually silencing the KO cells, so the whole-cell recordings come first. *Pten*^flx/flx^ mice were injected in the dentate gyrus with pRubi-HM4D-T2A-Cre, which expresses the inhibitory DREADD hM4D(Gi) and Cre from one open reading frame, so every KO granule neuron also carries the receptor. Repeated series of 500 ms current steps were recorded before and during bath application of 10 µM CNO. This version shows the Pten KO neurons only, and every number in it is computed from the raw AxoGraph recordings rather than read from the earlier figure; the identification of each neuron in the raw files, and the per-sweep data, are in the workbook.

![](figsv3/fig21_ko_patch.svg){width=6.6in}

*Figure 22. CNO silences hM4D-expressing Pten KO granule neurons, recomputed from the raw
recordings (n = 5). **a** One neuron's response to the same injected current before and during
CNO. **b** Spikes per sweep against current above each neuron's own baseline rheobase; thin lines
are neurons, thick lines the mean ± SE where at least three neurons contribute, with the mixed
model over all 100 matched pairs of sweeps referred to 4 df. **c** Spikes per sweep
at matched injected current, each neuron, with the paired test over neurons and the bootstrap
interval resampling neurons. **d** Rheobase; the two neurons that fired at no current tested are
drawn open at the highest current tested and are excluded from the paired test, as are their
thresholds in **e**. **f** Resting potential. Spikes are peaks above −10 mV preceded within 2 ms
by dV/dt > 100 mV/ms, accepted when the peak exceeds threshold by 20 mV.*


At matched injected current, spikes per sweep fell from 5.70 ± 1.35 to 1.44 ± 0.77 in the five
Pten KO neurons, a drop of 75%, with a 95% confidence interval on the effect of −6.9 to −1.6
spikes per sweep (bootstrap resampling neurons). The paired test over the five neurons is
p = 0.051, as before.

**The firing-rate comparison cannot be improved by analysis, and that is worth stating plainly.**
Going back to the raw recordings reproduced the per-neuron values exactly but did not move the
p value, and no test that treats the neuron as the unit of replication can. With five neurons the
exact within-neuron sign-flip permutation has 32 arrangements, so its smallest attainable p is
0.063 even if every neuron fell; with one neuron showing no change it is 0.125, which is also what
the Wilcoxon gives. A linear mixed model of spikes on drug and current with a random intercept and
slope per neuron returns the same −4.26 spikes per sweep with a Wald p of 0.002, but that test
treats the 100 sweeps as the replication unit; referred to the 4 degrees of freedom that five
neurons actually provide it is p = 0.037, and it sits below the permutation floor, which is the
signature of leaning on sweeps rather than on cells. The honest summary is the effect and its
interval, not a p value: a three-quarter reduction whose confidence interval excludes zero, in a
group of five.

The pattern across neurons is what that interval is summarising. Two of the five stopped firing at
every current tested, up to 640 and 490 pA. Two more fell by 97% and 60%. The fifth, N001, is
described in the original results as not responding; across its full series it falls from 3.45 to
2.45 spikes per sweep over 17 minutes, so it is better described as a weak responder than as a
non-responder, and it is the reason the five-point test sits on the border.

Firing also declines monotonically with time after CNO in all five neurons, at −0.07 to
−0.71 spikes per sweep per minute. Five of five negative is p = 0.063 by exact sign test — the
floor again — so this is corroboration of the same effect rather than independent evidence, but it
is the pattern a drug effect should make and a rundown artefact need not.

Rheobase moved in the same direction. In the three neurons that still fired it went 200 → 250,
440 → 440 and 740 → 870 pA (p = 0.254 on three neurons), and the two that were silenced passed
beyond the highest current their protocol reached. Nothing about the recordings deteriorated:
spike threshold is unchanged in the neurons that still fired (−44.2 to −43.5 mV, p = 0.476) and
resting potential is unchanged in all five (−82.9 ± 1.1 to −83.4 ± 1.3 mV, p = 0.486).

**What this version does not contain.** The uninfected wild-type neurons that served as the
no-drug time control are not shown, so rundown over the same interval is not controlled within
this figure. The earlier analysis of those recordings put the rundown at about a third of spikes
over ten minutes, against the three quarters lost here, and two neurons silenced outright is not a
rundown phenomenon; but the comparison is not made in this version.

**What would actually strengthen it.** More neurons, and nothing else. Five is the binding
constraint on every test above.

**The KO neurons start out needing far more current.** Baseline rheobase averages 452 ± 95 pA,
which is three- to fourfold what wild-type granule neurons need, in keeping with their much larger
capacitance. Panel b is therefore plotted against current relative to each neuron's own baseline
rheobase.

This is the cell-autonomous version of what the CNO sections below show at the level of the dentate circuit: silencing the mutant granule cells removes the activity-driven excess without touching the wild-type baseline.

## 13. Silencing the KO cells: theta and behaviour

![](figsv3/fig13_cno_behaviour.svg){width=6.2in}

*Figure 23. CNO and behaviour. **A** Goal-zone time (phases 8–9 mean) against percent KO, visible sessions (top) and hidden sessions (bottom), at baseline, after CNO and the change; conventions as in Figure 20; M36 is included here. **B** Hidden goal-zone time for all Pten KO mice pooled against WT: group means ± SE at baseline and after CNO, each mouse (KO coloured by Lo and Hi; diamonds: IED+), and each mouse's change with CNO.*


| Goal-zone time (% of session) | WT | All Pten KO | Lo KO | Hi KO |
|------------------------------|------------|------------|------------|------------|
| Mice | 11 | 11 | 5 | 6 |
| Hidden: baseline → CNO | 2.62 → 2.03 | 2.22 → 3.03 | 2.03 → 2.25 | 2.39 → 3.67 |
| Hidden: mice that rise with CNO | 3 of 11 | 8 of 11 | 4 of 5 | 4 of 6 |
| Hidden: Mann-Whitney p vs WT, after CNO | | 0.10 | 0.83 | **0.020** |
| Hidden: Mann-Whitney p vs WT, change | | **0.042** | 0.22 | **0.048** |
| Hidden: group × drug p (vs WT) | | **0.022** | 0.28 | **0.009** |
| Visible: baseline → CNO | 6.02 → 5.31 | 5.55 → 4.85 | 5.30 → 4.11 | 5.75 → 5.47 |
| Visible: group × drug p (vs WT) | | 0.98 | 0.63 | 0.64 |

| Regression on % KO, WT at 0% | Baseline | After CNO | Change |
|------------------------------|------------|------------|------------|
| Hidden | r = −0.29 (p = 0.12, n = 30) | **r = +0.56 (p = 0.006, n = 22)** | **r = +0.56 (p = 0.007, n = 22)** |
| Visible | r = −0.04 (p = 0.83, n = 30) | r = +0.12 (p = 0.59, n = 22) | r = +0.15 (p = 0.51, n = 22) |

- **With the goal hidden, WT and Pten KO mice move in opposite directions after CNO.** WT goal time falls (2.6% to 2.0%; 8 of 11 mice do not rise). Pten KO goal time rises (2.2% to 3.0%; 8 of 11 rise), most in Hi KO mice (2.4% to 3.7%). Group × drug: p = 0.022 for all KO mice and p = 0.009 for Hi KO alone.
- **The change tracks percent KO** (r = +0.56, p = 0.007), and so does goal time after CNO (r = +0.56, p = 0.006). At baseline it does not (r = −0.29, p = 0.12).
- **The result no longer rests on M5.** M5 is still the largest riser (+4.7 points). Without it, all KO × drug is p = 0.042, Hi × drug p = 0.055 and the regression on percent KO r = +0.42 (p = 0.059). M29, a Hi mouse without IEDs, rises by 1.8 points, as much as the IED mice M3 (+1.6) and M34 (+1.1).
- **With the cue visible, CNO has no genotype-specific effect.** There is no group × drug interaction (all p ≥ 0.62) and no relationship with percent KO at baseline, after CNO or for the change. The benefit in KO mice appears only when the task makes a hippocampal demand.
- **Visible goal time drifts down after CNO in every group.** WT 6.0% to 5.3%, Lo 5.3% to 4.1% and Hi 5.8% to 5.5%. The fall is significant in Lo on its own (paired p = 0.019) but does not differ from WT (Lo × drug p = 0.63), so it is not specific to Lo and may reflect repeated testing. The safe statement is that CNO does not change cued performance differently by genotype.
- **Reading.**
  - **In WT mice,** CNO silences about 5% of normal granule cells, and hidden goal time falls a little: a mild cost of removing some normal dentate output, or of repeated testing.
  - **In Pten KO mice, Hi KO mice most,** CNO silences a population that includes the KO cells and brings theta CSD from about twice WT back to the WT level, and hidden goal time rises.

  That fits the idea that pulling an over-driven dentate network back toward normal does more good than the loss of some granule-cell output does harm. It does so only where the task depends on the hippocampus.

### Theta CSD as a predictor of IEDs, before and after CNO

High KO and IEDs go together in these mice. That is a finding, not a nuisance: IEDs are one consequence of Pten KO spreading past the threshold for network involvement, as in LaSarge et al. (2021). The question here is whether the excess theta current carries the same information, so that CSD alone can pick out the mice with clear IEDs, and whether it still can after CNO. The ROC uses the 21 mice with CSD at baseline and after CNO: 5 IED mice against 16 others (8 WT, 8 KO without IEDs).


| Predictor of clear IEDs | 4-layer average | MML2 + GCL2 | MML2 | GCL2 | MML1 | GCL1 |
|------------------------------|----------|----------|----------|----------|----------|----------|
| AUC at baseline (95% CI) | **0.91** (0.70–1.00) | **0.97** (0.89–1.00) | **0.93** (0.74–1.00) | **0.90** (0.73–1.00) | 0.71 (0.36–1.00) | 0.60 (0.26–0.94) |
| p | **0.004** | **<0.001** | **0.003** | **0.006** | 0.18 | 0.55 |
| Best baseline cutoff: IED caught, false positives | 4 of 5, 0 of 16 | 5 of 5, 2 of 16 | 4 of 5, 0 of 16 | 5 of 5, 5 of 16 | 3 of 5, 1 of 16 | 3 of 5, 3 of 16 |
| AUC after CNO (p) | 0.72 (0.15) | 0.78 (0.075) | 0.80 (0.050) | 0.66 (0.31) | 0.60 (0.55) | 0.56 (0.72) |
| Loss of AUC with CNO (p) | **0.19 (0.030)** | **0.20 (0.026)** | 0.12 (0.091) | **0.24 (0.033)** | 0.11 (0.50) | 0.04 (0.85) |
| CNO drop as predictor, AUC (p) | **0.84 (0.025)** | **0.89 (0.008)** | **0.94 (0.002)** | **0.81 (0.040)** | 0.59 (0.60) | 0.62 (0.45) |
| KO mice only: AUC baseline → CNO | 0.88 → 0.70 | 0.95 → 0.73 | 0.93 → 0.70 | 0.83 → 0.68 | 0.78 → 0.65 | 0.60 → 0.70 |

*All mice: 5 IED vs 16 others; KO only: 5 vs 8. p: Mann-Whitney for single predictors, paired bootstrap for the loss of AUC.*

- **At baseline, theta CSD in MML2 and GCL2 identifies the IED mice.**
  - AUC is 0.90–0.97 for the four main measures. MML1 and GCL1 are near chance (0.71 and 0.60).
  - For the 4-layer average, a cutoff of 0.042 catches 4 of the 5 IED mice with no false positives. The mouse it misses is M3.
  - IED mice average 0.045 against 0.024 for KO mice without IEDs (p = 0.030) and 0.019 for WT (p = 0.005). KO mice without IEDs do not differ from WT (p = 0.27).
- **After CNO the prediction is lost.** AUC falls to 0.66–0.80, with intervals that reach or approach 0.5. The loss is significant for the 4-layer average (0.19, p = 0.030), MML2 + GCL2 (0.20, p = 0.026) and GCL2 (0.24, p = 0.033), and a trend for MML2 (0.12, p = 0.091). Leaving out any single mouse keeps the loss for the average between 0.17 and 0.23, except without M3 (0.11).
- **The CNO drop itself marks the IED mice** (AUC 0.81–0.94). CNO removes the part of the theta current that sets the IED mice apart.
- **MML2 and GCL2 differ in one respect.** In MML2 some separation survives CNO (AUC 0.80, p = 0.050), and the CNO response is larger in Hi than in Lo mice (Hi vs Lo × drug p = 0.024, the only layer where this holds). In GCL2 the separation disappears entirely (0.66). The somatic current in the infrapyramidal blade may normalise more completely than the dendritic current in MML2. With five IED mice this is a lead.
- **CSD and percent KO get different mice wrong.** On the same 21 mice, percent KO predicts IEDs about as well (AUC 0.95), but its errors are the two Hi mice without IEDs, M7 (24.1%) and M29 (22.0%), both with low CSD. The errors of MML2 + GCL2 are two Lo mice with high MML2/GCL2 current (M8, M10), and it catches M3 only at the cutoff. The two measures are related but not interchangeable, which fits the excess current depending on where the KO cells sit and not only on how many there are.
- **M13 sits just below 20% KO.** It is an IED mouse at 18.9% KO and is in the CSD set only, so the "every IED mouse is at 20% KO or more" pattern from the behavior cohort does not hold for the CSD cohort. The 15% line holds in both.
- **IEDs versus theta.** In these mice, CNO does not abolish the IEDs; if anything they become more frequent (Figure 24). The behavioral gain after CNO (Figure 23) goes with the normalised theta current, not with fewer IEDs. M29 points the same way: a Hi mouse without IEDs and with low CSD that still improves with CNO. That points to theta-band network state, rather than epileptiform events as such, as the more likely route from Pten KO to the memory deficit, an idea with growing support across several fields.

## 14. Interictal discharges

The IEDs come from the same layers as the excess theta current, and silencing the KO cells does not reduce them. CNO leaves the IED's laminar structure in place and, if anything, makes IEDs more frequent (0.25 to 0.65 per minute). In the mice whose theta current fell, hidden-goal behaviour improved even when IEDs rose several-fold.

- **Data.** IEDs from the lab's recording pipeline: 5 Pten KO mice (M3, M5, M13, M28, M34), one baseline and one CNO recording each, with 41 baseline and 131 CNO solid IEDs. M3, M5, M28 and M34 are the four IED+ Hi mice of the behaviour cohort; M13 has recordings only.
- **What was used.** Two inputs, plus the pipeline's own per-depth statistics, reported as given:
  - the pipeline's spatially normalised grand-average voltage for each condition (49 depth bins over 8 layers, −20 to +20 ms around the IED peak, mean of the 5 sessions);
  - the per-session IED counts, recording lengths and onset times.
- **Windows.** Initiation (IP) is −1 to 0 ms and propagation (PP) 2 to 15 ms around the IED peak, as in the pipeline.
- **CSD.** It is shown in the supplement only (Supplementary Figure S3), computed here from the averaged voltage, whose depth bins are not evenly spaced in tissue. It agrees with the pipeline's channel CSD in direction at most layers, but not in size, and voltage is the clearer view of this event.
- **Statistics.** IED rate, baseline vs CNO: paired t-test and Wilcoxon across the 5 mice. The four mice with both recordings and behaviour are shown individually; with n = 4 this is descriptive.

![](figsv3/fig15_ied.svg){width=6.2in}

*Figure 24. Interictal discharges. **A** Grand-average IED voltage at baseline and after CNO, on the same colour scale (5 mice; 41 and 131 IEDs); bars above each raster mark the initiation (IP, −1 to 0 ms) and propagation (PP, 2 to 15 ms) windows; beneath, voltage by layer in each window on the same axis, initiation filled and propagation open. **B** Theta excess and IED initiation by layer: baseline theta CSD of IED+ mice minus WT (IED+ 5, WT 10); the CSD of the averaged IED in the initiation window (blue sink, red source); and both profiles scaled to their own maximum, with shading marking GCL2 and MML2.*


| Voltage (µV) | IP, baseline | IP, CNO | PP, baseline | PP, CNO |
|----------------|--------|--------|--------|--------|
| CA1 SLM | −284 | −205 | −119 | −163 |
| OML1 | −348 | −199 | −101 | −123 |
| MML1 | −672 | −457 | −238 | −183 |
| GCL1 | −692 | −1115 | −145 | −337 |
| HIL | −537 | −1071 | +75 | +150 |
| GCL2 | −822 | −856 | −791 | −676 |
| MML2 | +263 | +548 | −320 | −146 |
| OML2 | +670 | +415 | −165 | −153 |

*Grand averages, each layer's bins and window averaged.*

- **The IED has a stereotyped laminar structure.** At initiation the hilus is negative and OML2 and MML2 positive, and both flip sign in propagation. GCL2 is negative before the peak and stays negative throughout. The pipeline's per-IED tests confirm that initiation and propagation differ by depth (voltage, depth × phase χ² = 191, p < 0.001). The difference is significant at HIL, MML2, OML2, GCL1, MML1 and OML1 after correction across depths, but not at GCL2.
- **CNO keeps the structure.** The same layers carry the same signs with CNO, and the GCL2 negativity is unchanged. At initiation the hilus and GCL1 negativity is about twice as deep in the CNO average. The pipeline's per-mouse drug tests (n = 5) confirm no layer change after correction; only GCL1 voltage at initiation is nominal (p = 0.038). The IED is the same event with CNO, possibly stronger.


- **The excess theta current and the IED's initiation current peak in the same two layers.** IED+ mice carry about 0.04 a.u. more theta current than WT in GCL2 and in MML2, and little elsewhere (≤ 0.02). At initiation the IED's largest sink is in GCL2, with a source just below it in MML2. Across the 8 layers the two profiles go together (ρ = +0.55, p = 0.16; descriptive). The one mismatch is OML1, which carries some IED current but no theta excess.
- **One circuit, two outputs.** The lower blade, where Pten KO granule cells and their perforant-path synapses are concentrated in Hi mice, generates both the continuous theta excess and the intermittent IED. The ROC result (Figure 21) is the quantitative side of this: theta CSD in MML2 and GCL2 picks out the IED mice, and MML1 and GCL1 do not.

![](figsv/ied__fig35_dissociation.svg){width=6.5in}

*Figure 25. The four IED+ Hi mice (diamonds) with recordings and behaviour, baseline (open) and CNO (filled): A, theta CSD (4-layer mean); B, IED rate; C, hidden goal-zone time. M13 (grey) has recordings only. M28 in bold. Recording and behaviour sessions were on different days.*


| Mouse | IED rate (per min) | Theta CSD change, 4-layer / MML2 + GCL2 / GCL2 | Hidden goal-zone time (%) |
|--------|----------------|---------------------------|----------------|
| M3 | 0.33 → 0.90 (×2.7) | −53% / −60% / −70% | 1.9 → 3.6 |
| M5 | 0.06 → 0.32 (×5.4) | −38% / −39% / −44% | 0.9 → 5.5 |
| M34 | 0.28 → 0.23 (×0.8) | −29% / −36% / −39% | 2.3 → 3.4 |
| M28 | 0.16 → 1.34 (×8.1) | −13% / −12% / 0% | 5.0 → 3.4 |
| M13 | 0.42 → 0.45 (×1.1) | +1% / −29% / −23% | no behaviour |

*IED rates from the recording pipeline; theta CSD and goal time from the CSD/CNO data of this report (Figures 19 and 22).*

- **CNO does not reduce IEDs.** The rate rises from 0.25 to 0.65 per minute (pooled 0.22 to 0.58, 2.6-fold) and goes up in 4 of 5 mice, but not significantly (paired t p = 0.15, Wilcoxon p = 0.19); M28 contributes most of the rise. M34 is the one mouse that falls (0.28 to 0.23).
- **Behaviour follows the theta current, not the IED rate.** M3 and M5 are the informative mice: their IEDs rose 2.7- and 5.4-fold, yet their theta current fell by a third to a half and hidden-goal time rose (1.9% to 3.6%, 0.9% to 5.5%). M34's IEDs held steady, its theta fell and its goal time rose. M28 cannot separate the two explanations: its theta fell least (−13%, GCL2 unchanged) and its IEDs rose most, and it is the only mouse that got worse.
- **The behavioural benefit of CNO therefore does not depend on fewer IEDs.** It goes with the normalised theta current. This fits the IEDs being intermittent, and the theta excess being continuous and present during every moment of encoding and retrieval. Kleen and Holmes found that IEDs disrupt memory mainly through when they occur, not how many there are; a continuous excess current at the perforant-path synapse may corrupt input all the time. With four mice this is a lead, but the direction is the one the argument needs.


- **The rise is not a session-length artefact (Supplementary Figure S4).** CNO recordings ranged from 20 to 95 minutes. Counting only the first 20 minutes of every session gives the same picture: 0.27 to 0.74 per minute (paired p = 0.21), up in 3 mice and flat in 2. In M5 the rise came late in the CNO session.
- **With CNO the IEDs come closer together.** 43% of intervals are under 30 s, against 17% at baseline (pooled; median 45 vs 120 s). By mouse, the median interval shortens in M3, M5 and M28 and lengthens in M13 and M34. M28 and M13 contribute most of the CNO intervals.
- **Still open.** The time from CNO injection to recording start is not in these files. It would show whether the rise follows the drug's time course.

# Part III — Synthesis

## 15. Interpretation: working memory and pattern separation

Interpretation, not result — but the shape of the data points somewhere specific, and it points at the dentate gyrus.

**The demand the task makes.** By phase 10 a mouse has to keep four locations apart: the one that pays now and the three that used to. They sit in the same arena, under the same cues, differing only in position — highly overlapping inputs that have to be held as distinct representations and tagged by recency. That is the canonical description of what the dentate gyrus is for. Pattern separation is usually probed with similar contexts or similar object positions; a sequence of rotated goals in one arena is the same demand spread over a session, with the number of confusable items rising by one at each rotation.

**Why the data fit that reading rather than a simpler one.** Three features line up.

- *It scales with the number of items.* The deficit is not present at phase 7, when there is nothing to disambiguate, and grows as former goals accumulate (+25.3 s per phase in WT against +9.6 in Hi, p = 0.003). A representation that was simply weaker or noisier should have shown a constant handicap; interference between similar items should grow with how many there are, which is what happens.
- *Never-used zones are sorted correctly.* Hi mice abandon the zones that were never goals at the same rate as WT (p = 0.64). They are discriminating used from unused perfectly well. What they fail at is discriminating *among* the used ones — exactly the harder, more overlapping comparison.
- *A beacon rescues it.* With the cue present the deficit is gone (p = 0.198). An external landmark removes the need to resolve similar internally-held representations, because the current goal is marked from outside. If the problem were storage or motivation the cue should not help this cleanly.

**Working memory or pattern separation?** The data here cannot separate them, and they may not be separable in this preparation. Holding three candidate places and testing them in turn is a working-memory operation; keeping those three places distinct enough to be testable is pattern separation. A failure of either produces the same behaviour — a search that does not scale. What the data do exclude is a lost memory of the goal location, since the current goal is found and dwelt at normally, and a general change in activity, since pausing away from every zone is unchanged.

**Why the dentate gyrus makes this plausible.** The mutant cells here are granule cells, the population that performs the sparse recoding that keeps similar inputs apart, and the deficit tracks KO load: Lo mice behave like WT on every panel of Figure 17, Hi mice do not. The hyperexcitability documented in the patch recordings (Figure 22) and the IEDs arising from the same lower-blade sources (Figure 24) are both ways of making granule-cell output less sparse and less selective, which is the mechanistic currency of a pattern-separation deficit. That chain is consistent rather than demonstrated: nothing here measures granule-cell coding directly.

**What would test it.** A discrimination task with parametrically varied similarity between the current and former goals would separate interference from capacity: a pattern-separation account predicts the deficit grows with how *similar* the locations are, a working-memory account predicts it grows with how *many* there are, and the present design varies only the number. Within these data, the per-mouse slope of Figure 10 against percent KO, and against theta CSD and IED rate in the recorded mice, is the obvious first look once the raw IED data arrives.

### Interpretation: two different failures

The working hypothesis is that KO level changes what fails, not just how much. Low KO slows the formation of a cue-reward association; high KO leaves that largely intact but limits how many successive goal locations a mouse can handle without the cue.

| | Pten KO Lo | Pten KO Hi |
|---|---|---|
| Sessions to criterion (visible cue, trained location) | 21.2, all slower than WT | 14.0, half within WT range |
| Visible probes across rotations | Intact; fewer entrances, more rewards per entrance | Intact |
| Hidden probe, trained location | Impaired (0.21 rewards per entrance vs 0.34 WT) | Impaired (0.23) |
| Hidden probes across rotations | Per-entrance accuracy stable; fewer entrances and less goal time than WT by phases 9–10 | Declines by about 3 rewards per phase |
| Last hidden probe (phase 10) | Matches WT per entrance (0.31) | 0.14 per entrance, 40% faster in the goal zone |

**Why this points to memory in the Hi group.** The same mice, in the same phases, perform normally when the cue is visible. That argues against a general loss of motivation, motor ability or vision. The sessions-to-criterion test is also the easier of the two: it asks only how readily a mouse links a visible object at one location to reward.

**Three accounts fit the Hi KO decline, and they predict different things.**

1. **A limit on memory across rotations.** Each new location is encoded less well. Predicts undirected search at phase 10, with no preference for any earlier goal.
2. **Interference from earlier goals.** Each rotation adds a competing location, and the earlier manuscript showed Pten KO mice perseverating on the first hidden location. Predicts time spent in old goal zones.
3. **Failure to stop, not failure to find.** At phase 10 Hi mice enter the goal zone about as often as WT (43 vs 49 entrances) but earn a third of the rewards while moving faster through the goal zone. They reach the location and do not dwell the required 1.2 s. This could be chance crossings by a fast animal that does not know where the goal is, or a mouse that knows and cannot hold still.

IED status cuts across all three: four of six Hi mice are IED+, so the decline may belong to epileptiform activity and not to KO percentage as such.

**What the path analyses now say about these accounts.**

- **Account 1, a memory limit across rotations, does not fit on its own.** Hi mice still aim at the current goal, come back to it after a miss, and pause at it as much as WT at every phase (Figure 18, p = 0.93). A mouse whose encoding of each new location had degraded would not keep the never-used zones correctly sorted either, and it does (p = 0.64).
- **Account 2, interference from earlier goals, was framed as perseveration and that part is wrong.** Perseveration predicts *more* time at the old goals. Hi mice spend less: 28 s per session against 82 s in WT at phase 10, and their slope across the rotations is +9.6 s per phase against +25.3 (Figure 10, p = 0.003). The earlier manuscript's perseveration on the first hidden location is not what these mice are doing by phase 10. What survives of the account is its premise — that each rotation adds a competing location — but the consequence is the opposite of dwelling on them.
- **Account 3, a failure to stop, is closer than it first appeared.** It was set aside when the pause measures were separated by place, on the grounds that Hi mice stop normally at the current goal. That rested on a non-significant difference at n = 6; the braking measures, which are normalised per metre travelled and so are not inflated by the extra ground Hi mice cover, show they do not. At the current goal they brake on 38% of directed runs against 56% in WT (p = 0.045), at a rate of 6.05 per 10 m against 9.15 (p = 0.004), and when they do brake they start further out (13.7 cm against 11.5, p = 0.050) rather than at a displaced location, which is what a path-integration error would look like.
- **Account 4, a failure to commit, is what the evidence now supports.** The intention to check is intact: Hi mice approach the former goals and slow there as often as WT. What fails is converting a slowdown into a stop, and recognising the one place that would justify stopping. The pausing deficit still scales with the number of former goals rather than being present from the start, and it still disappears when a cue removes the need to hold the set internally (Figure 10, p = 0.198 cued against 0.003 hidden), so a capacity limit remains the best reading — working memory, pattern separation, or both, which these data cannot separate. What has changed is where in the sequence it bites: not in deciding to look, but in deciding that a place is the right one.
- **Still open.** Additional rotations beyond phase 10 would test whether Hi mice keep falling while WT stay flat. Entrances and rewards per entrance during training would show whether Lo mice were slow to learn or slow to move. A task that varies the *similarity* of the goal locations rather than their number would separate interference from capacity.

The evidence for this section is limited to one cohort. Lo vs Hi on sessions to criterion is p = 0.08, and Hi and Lo separate in hidden sessions only at phase 10. Six Hi mice is a small group, and the pause-placement null is not strong enough to exclude a genuinely coarser spatial representation.

**Fit with LaSarge et al. (2021).** In their model, with Pten deleted from 0–40% of granule cells, hyperexcitability appears with any KO but changes character at about 15%. Below it, abnormal activity stays confined to the KO cells and silencing them abolishes it. Above it, normal cells are recruited, hilar interneurons (somatostatin cells most) are lost and seizures reach the cortex. The Lo and Hi groups here sit on either side of that line (3.9–9.5% and 20.2–28.4%), and the pattern maps onto it:

| Finding here | Relation to LaSarge et al. |
|---|---|
| Obvious IEDs only at 20% KO or more | Consistent with the 15% line for spread to the network |
| Both KO groups impaired in hidden sessions from the trained location onward | Consistent with a change present at any KO level |
| Only Hi KO mice deteriorate at the last hidden probe | Consistent with changes above 15% (interneuron loss, recruitment of normal cells) |
| Hi KO theta CSD is twice WT, concentrated in MML2 and GCL2, and CNO brings it back to WT without changing WT | Consistent with KO cells driving more of the network activity at high load |
| Lo KO mice slower than Hi to reach criterion | Not predicted; their pathology only increases with load |

That mapping is an inference: their study has no behavior. They also found most low-KO mice had hippocampal epileptiform activity on continuous depth recording, which fits treating IED− here as "no obvious IEDs" and not as normal activity.

Reference: LaSarge CL, Pun RYK, Gu Z, Riccetti MR, Namboodiri DV, Tiwari D, Gross C, Danzer SC (2021). mTOR-driven neural circuit changes initiate an epileptogenic cascade. *Progress in Neurobiology* 200:101974.

### A narrative for the paper

- **The task.** Visible vs hidden is a dry-land version of the cued vs hidden-platform contrast, and moving the goal adds interference and working-memory load. Even WT mice show the memory demand: with a hidden goal they head for it later and from closer in (16.5 vs 20.1 cm), take less direct runs and run 1.7 times as far per reward. Frame by frame, WT mice aim at a cued goal from 34 cm away but at a hidden one only from 21 cm (Figure S8): beaconing vs a local approach to a remembered place. Every group drops when the goal first moves.
- **Both KO groups have a cognitive deficit, and neither has a motor or motivational one.** Visible-goal performance is intact or better in both groups, and how the mice travel to the goal is the same in all three.
- **Pten KO Lo (4–10% KO, IED−): slow to learn, and lost once the goal moves.**
  - **Learning:** they take the longest to reach criterion (21.2 vs 8.8 sessions for WT, p < 0.001, no overlap).
  - **Updating:** after the goal moves they lose their preference for the new location at phase 9 and spend less time in it at phases 9–10. After a miss they rarely come back to the goal, and they pause near the wrong zones.
  - **Arrival:** when they reach the goal they stop as well as WT or better. With the cue they stay longer and earn more rewards per entrance, increasingly so across phases.
  - **Reading:** a problem of where to go, with arrival intact. This fits a dentate gyrus deficit that has not spread to the wider network.
- **Pten KO Hi (20–28% KO, mostly IED+): near-normal learning, then a failure to settle under accumulated interference.**
  - **Learning:** they reach criterion closer to WT speed (14.0 sessions, p = 0.03 vs WT).
  - **Decline:** hidden-goal performance falls with each rotation, in every Hi mouse. By phase 10 they earn 5.5 rewards against 15.2 for WT.
  - **Arrival:** they reach the goal by normal aimed runs, come back after a miss and pause near it, so they know where it is. But they enter fast (22 vs 15 cm/s), stay about half as long (0.51 vs 1.11 s), leave fast and are rewarded on 16% of aimed runs, against 34% for WT and 45% for Lo.
  - **Reading:** a failure to recognise and hold the current place, with knowing roughly where and getting there intact. This fits more global hippocampal dysfunction, in line with the roughly 15% threshold for network spread in LaSarge et al. (2021).
- **What separates Hi from Lo.**
  - **Arrival at the last rotation:** entry speed, time in the goal and reward per aimed run (p = 0.013–0.030).
  - **The decline across rotations:** per mouse p = 0.017; per run p = 0.0001.
  - **Returns after a miss:** p = 0.004.
- **Percent KO.** It does not predict outcome linearly. Sessions to criterion follow an inverted U, and % KO tracks behaviour only at the last hidden probe, where higher KO goes with faster entries and fewer rewards per entrance (ρ = ±0.75).
- **Network link.** Hi KO mice, the IED mice in particular, have about twice the WT theta CSD, in MML2 and GCL2. Silencing the DREADD-expressing granule cells with CNO brings it back to the WT level, while the same treatment leaves WT CSD unchanged. Hidden goal-zone time falls slightly in WT after CNO, consistent with a small cost of silencing about 5% of normal granule cells, and rises in Pten KO mice, most in Hi, consistent with a benefit of pulling an over-driven network back toward normal (group × drug p = 0.009 for Hi). The benefit holds without M5, tracks percent KO (r = +0.56), and is absent with the cue visible.
- **IEDs as a readout of network spread, theta as the route to behavior.** Baseline theta CSD identifies the IED mice about as well as percent KO (AUC 0.91–0.97 against 0.95), but only in MML2 and GCL2, where KO is highest; MML1 and GCL1 do not. CNO removes that signal (AUC 0.72; loss p = 0.030) by cutting the current most in the IED mice. Because CNO does not stop the IEDs, and M29, a Hi mouse without IEDs, improves as much as the IED mice, the behavioral benefit more likely reflects normalised theta than fewer IEDs. The layer specificity supports a synaptic-efficacy account. After CNO the excess at GCL2 is gone but about half of it remains at MML2 (Figures 18 and S14), where the extra spines and larger dendrites of the KO cells receive perforant path input: lowering activity helps, but it does not undo the synaptic structure.
- **Caveats.**
  - **Confounds:** KO level is confounded with IED status, and heterotopia falls mostly in Lo.
  - **Group size:** 5 Lo and 6 Hi mice.
  - **Single session:** the key Hi effects rest on one probe (phase 10).
  - **Statistics:** many tests were run, and only Hi vs WT target speed at phase 10 survives correction.

## 16. Caveats and open questions

- **Small groups.** Lo is 5 mice and Hi is 6. Single mice move most of these estimates, and exact tests on 5 mice cannot go below p = 0.06 for paired comparisons.
- **Many tests.** Eight measures, two conditions and four phases give 64 tests per comparison. The sessions-to-criterion results and the pooled hidden-session deficit are robust. Of the single-phase probe results, only Hi vs WT target speed at phase 10 survives correction (q = 0.03).
- **KO level and IED status travel together.** This is a finding in its own right (IEDs follow network spread above about 15% KO, and theta CSD tracks both; Figure 21), but it means behavior alone cannot say whether KO level or IEDs drive the Hi deficits. All four IED+ mice in the behavior cohort are Hi and all five Lo mice are IED−. The phase-10 speed-up in Hi mice could reflect KO percentage or IEDs. Only two Hi mice are IED−, and they split: M7 behaves like a Lo mouse and M29 like the IED+ mice.
- **Heterotopia is confounded too.** Three of four heterotopia mice with histology are Lo.
- **M6.** It is excluded from sessions to criterion as an outlier and kept in the probe analyses. The only basis for the exclusion is its criterion score, so an independent reason would be stronger in the methods if there is one. Including it in the probes changes no main result; excluding it would move one comparison across p = 0.05 (the Lo vs WT slope for hidden goal entrances, 0.044 with M6 and 0.055 without).
- **M24's phase 9 sessions are dated 13 June, after its phase 10 sessions (10 June),** and the visible phase 9 file is named `p9cnoc`. If that session followed CNO or was a rerun, M24's phase 9 values in the group analysis are not a clean second rotation.
- **WT at 0% KO** is an assumption, and the non-monotonic fit depends on it.
- **Direction vs the earlier manuscript.** With cell-layer counts only, low KO predicts slow acquisition. The manuscript reported that high bilateral KO did, using counts that included cells outside the layer.

Open questions:

- **Lo inflexibility: re-test if the cohort grows.** The drift back to the first-learned location is intuitive and keeps being half-remembered as established. It is not. Two of five mice; no Lo-vs-WT difference in former-goal pause time at any phase (p = 0.33 to 0.95) or in slope (p = 1.00). Either power it properly or stop repeating it.
- **Is this report framed around the wrong thing?** Flagged 23 November, unresolved. Figure 10 sharpens this further: the deficit is in working through the set of former goals, and it scales with the size of that set (slope +25.3 s per phase in WT, +9.6 in Hi, p = 0.003), with the never-used zones and the current goal both normal, and the whole effect absent when the goal is cued (p = 0.198). Everything above is organised around arrival: the mice reach the goal and fail to settle there. The compartment split in Figure 16d does not support that as the primary deficit. Pausing inside the goal zone and in the ring around it does not differ between groups at any phase (p = 0.69 and 0.83 on the group × phase slopes). The entire effect is in the open interior beyond 2.5 zone radii, where WT increase their pausing across the rotations and Hi mice decrease it (+7.0 vs −12.5 s per phase, p = 0.007), and where the cued sessions show nothing (p = 0.98). That is a deficit in **search** — in stopping out in the arena to test candidate places — and the failure to slow at the goal reads more naturally as its consequence than as a finding in its own right: a mouse not running a search is not in a state where arriving anywhere means much. If that holds, the arrival sections and Figure 8 become the downstream half of a story whose first half is the search collapse, and the section order should change to match. Nothing in the analyses needs redoing; the measurements are the same either way. What needs deciding is which result leads. This also bears on the mechanistic reading: a progressive failure to hold and test a growing set of candidate locations, each rotation adding one more former goal to rule out, is what a working-memory limit would look like, and it is a different claim from a degraded place memory.
- Histology for M27 (8 sessions) and M31 (27 sessions): their KO level decides whether Lo vs Hi reaches significance.
- Percent KO and IED status for the mice that were recorded but not trained, to strengthen the KO vs IED relationship.
- Dentate spike and quantitative IED measures per mouse, to test whether circuit state explains the split within the Hi group.
- Old goal zones at phase 10: answered in part by Figure 15. Hi KO mice pause near the old zones no more often than WT (18% vs 19% of pauses), but more of their directed runs end there (Figure 8 text).
- Percent KO by blade (GCL1 vs GCL2), to test whether KO in each layer predicts theta CSD in that layer (Figures 19 and 20).
- Answered (Figure 24): CNO does not reduce the IED rate (0.25 to 0.65 per minute, 4 of 5 mice up) or change the IED's laminar structure. Still open: the time from CNO injection to recording, single-IED onset by depth, and the theta phase at which IEDs occur (raw recordings needed).
- More Hi KO mice with behavior before and after CNO; the contrast with WT now holds without M5 but rests on 6 Hi mice.
- M33's percent KO: 8.82 in the earlier list and 4.41 in the CNO file. It is Lo either way, and neither value changes a conclusion.


## 17. Figure list

| | |
|---|---|
| 1 | Learning the cue rule: criterion, percent KO, and the two phenotypes |
| 2 | Visible goal sessions: the example mice and the session measures |
| 3 | Hidden goal sessions: the example mice and the session measures |
| 4 | Change per phase across the four rotations, hidden and cued |
| 5 | Visible phase 8: place against cue |
| 6 | Hidden phase 8: new place against old place |
| 7 | Time in each zone in hidden sessions, by phase and group |
| 8 | Arriving at the goal: what the runs look like |
| 9 | Slowing and pausing across the rotations |
| 10 | The set to rule out: pause time at former goals |
| 11 | Where they look, with the cue on and off |
| 12 | The shape of the approach at phase 10 |
| 13 | Braking on approach |
| 14 | What they do instead: running |
| 15 | Pauses and returns after a miss |
| 16 | Hidden phase 10: zone measures |
| 17 | Hidden phase 10: performance measures |
| 18 | Slopes across the hidden rotations |
| 19 | Theta CSD by layer |
| 20 | Theta CSD against percent KO |
| 21 | Theta CSD as a predictor of IEDs |
| 22 | CNO silences hM4D-expressing Pten KO granule neurons |
| 23 | CNO and behaviour |
| 24 | Interictal discharges |
| 25 | The four IED+ Hi mice with recordings and behaviour |

## 18. Supplementary figures

![](figsv/csd3__figS1_csd_regression_supp.svg){width=6.4in}

*Supplementary Figure S1. Theta CSD on percent KO for the 4-layer average, MML1 and GCL1.*

![](figsv/csd3__figS2_roc_supp.svg){width=6.4in}

*Supplementary Figure S2. ROC for MML1 and GCL1.*

![](figsv/ied__figS3_ied_csd.svg){width=5.2in}

*Supplementary Figure S3. IED CSD, supplementary.*

![](figsv/ied__figS4_ied_timing.svg){width=6.5in}

*Supplementary Figure S4. IED timing, supplementary.*

![](figsv/ap__ap1_paths.svg){width=6in}

*Supplementary Figure S5. Every wall-to-goal run for one mouse from each group, with each session rotated so the goal sits at 12 o'clock. Coloured: runs that ended in a reward; grey: runs that entered the goal without earning one. Left and centre: phases 7–10 combined. Right: hidden phase 10 alone. The mice were chosen to show each group's pattern in the measures below.*

![](figsv/ap__ap2_metrics.svg){width=6in}

*Supplementary Figure S6. Visible vs hidden for each measure. Thin lines: mice; thick lines: group means. Stars: paired t-test within the group. Path per reward is on a log scale.*

![](figsv/ap__ap3_launch_phase.svg){width=6in}

*Supplementary Figure S7. Launch distance at each phase, visible (solid) vs hidden (dashed), mean ± SE across mice. Stars: paired t-test at that phase.*

![](figsv/ap__fig32_heading_profile.svg){width=6.5in}

*Supplementary Figure S8. Heading toward the goal by distance, visible vs hidden. A: WT goal-directedness (mean cosine of the heading error) in 2.5 cm bins of distance from the goal centre, running frames off the wall, phases 7–10; mean ± SE of 19 mice. Red asterisks: paired t-test p < 0.05 in that bin. Vertical lines: mean reach, the distance where goal-directedness falls below 0.1 (dotted line). B: reach per mouse, visible (filled) and hidden (open), joined by mouse; bars are group means; diamonds mark IED+ mice; paired t-test. C: launch distances as the % of goal entries launched from at least each distance, mean of per-mouse curves (solid visible, dashed hidden). D: WT reach at each phase, mean ± SE; paired t-test per phase.*

![](figsv/ex__exB_dwell_hidden.svg){width=6.5in}

*Supplementary Figure S9. Where each example mouse spends its time in the hidden sessions, away from the wall: seconds per 2.4 cm bin, lightly smoothed. The wall zone (the outer 35 pixels, the annulus in the MATLAB code) is blanked so the colour scale shows the open arena; none of the goal zones reaches into it. Under each map: time in zones 1–4 as % of the session (\* = current goal) and the share of the session spent in the wall zone.*

![](figsv/ex__exC_speed_hidden.svg){width=6.5in}

*Supplementary Figure S10. Running speed across the arena in the hidden sessions (mean speed per bin, smoothed; rarely visited bins left blank).*

![](figsv/gzfigs__fig11_zone_roles.svg){width=6.5in}

*Supplementary Figure S11. Share of zone time by zone role across hidden probes, for each group. Each line follows a role (current goal, previous goal, original trained goal, never-used zone), not a fixed location, since the goal moves every phase. Dotted line: 25%, an even spread across the four zones.*

![](figsv/gzbarsH__fig_bars_hidden_mwu.svg){width=6.5in}

*Supplementary Figure S12. Same layout as Figure 7. Brackets: current goal vs zone 1 within each group (paired t-test). Top line in the KO rows: current-goal time vs WT (Mann-Whitney U test). Uncorrected.*

![](figsv/figs__fig5_heatmap.svg){width=6.3in}

*Supplementary Figure S13. Spearman correlation between percent KO and each measure at each phase. Asterisks mark uncorrected p < 0.05.*

![](figsv/csd3__fig29_layer_profile_ied.svg){width=6.4in}

*Supplementary Figure S14. The same layer profile for WT, KO mice without IEDs and KO mice with IEDs (diamonds). Same conventions as Figure 19.*

![](figsv3/fig_approach_profile_phases.svg){width=6.9in}

*Supplementary Figure S15. The shape of the approach at every phase, cue removed above and cue present below. Same construction as Figure 12. The hook is present in all four phases in both conditions and the groups overlap throughout; pooled over phases 7 to 10 the max-statistic permutation test gives Hi vs WT p = 0.43 with the cue removed and p = 0.18 with it present.*
