KCNT1 active avoidance story menu, first round (2026-11-23; revised the same evening)
The three lab hypotheses (Hom learn worse; age hurts Hom more; Het paths worse than WT) tested on every AA mouse, plus what
else the data offered, as a menu of stories. Exploratory: one number per mouse, generous tests, no correction.
Every comparison in stories 1-7 is made at one floor speed (4.4 deg/s); the speed supplement
(Lab Figures/KCNT1_AA_Speed_Supplement_112326) shows each headline before and after.

KCNT1_AA_Story_Menu_112326.pdf    the twelve pages in one file (figures with the narrative around them)

pages/  each page as PDF (vector; path tracks rasterized at 600 dpi) and PNG (300 dpi)
  01_menu                    the framework, the narrative in one paragraph, and the menu (best number at one floor speed, raw beside it)
  02_primer                  the rotating arena, the 17 sessions, the 56 mice, the words and the stats rules
  03_story0_arena_speed      APPARATUS: the floor turned at 2.2-5.8 deg/s across cohorts; raw counts follow it (the only raw page)
  04_story1_hom_learning     HYPOTHESIS 1: at one floor speed Hom take as many shocks as WT and reach criterion sooner
  05_story2_improvement      HYPOTHESIS 1, REFINED: Het and Hom improve less from day 1 to day 2 than WT
  06_story3_age              HYPOTHESIS 2: raw, old Hom did worse than young Hom; at one floor speed the gap is not significant
  07_story4_habituation      HABITUATION (s0, shock off): Hom keep to one side and cover less of the floor; voltage confirmed off
  08_story5_circle_paths     HYPOTHESIS 3: every mouse's day-2 waiting place and last session, in circle diagrams
  09_story6_where_they_wait  HYPOTHESIS 3: the waiting place from habituation to day 2; Het not scattered, they wait farther away
  10_story7_path_shape       PATH SHAPE: Hom stay off the rim and walk a little less straight
  11_checks                  our numbers against TrackAnalysis; every headline raw, at one speed, and without the flagged mice
  12_what_next               what each story needs from the next round (with mice per group for 80% power)

tables/
  results_P_below_0.05.xlsx                   every per-mouse result with generous P < 0.05 at one floor speed, one sheet per
                                              grouping, plus the raw results, mixed models with speed and circular tests
  all_results_at_one_floor_speed.csv.gz       every measure through every contrast, at one floor speed
  all_results_raw.csv.gz                      the same before the speed adjustment
  per_mouse_values.csv / ..._at_one_floor_speed.csv     one number per mouse per measure (raw / moved to 4.4 deg/s)
  per_session_values.csv.gz / ..._at_one_floor_speed.csv.gz   every measure for every session (s0 zone numbers left blank)
  mixed_models_with_floor_speed.csv           mixed models over s1-s16 with floor speed and speed x session
  mixed_models_raw.csv                        the earlier models without speed
  floor_speed_slope_per_measure.csv           how much each per-mouse measure moves per deg/s of floor speed
  circular.csv / circular_within_speed_bands.csv   day-2 preferred directions (raw / labels swapped only inside a speed band)
  occupancy_bins.csv, learners.csv, validation_vs_trackanalysis.csv, floor_speed_by_day.json, floor_speed_per_mouse.csv,
  s0_shock_jump_check.csv

code/   the scripts that made all of the above (they ran in a scratch folder; map_v3 = the mouse/file map behind them)

How things were done
  Mice      the 56 confirmed AA mice in KCNT1 Active Avoidance/confirmed_mice_112326.xlsx: 21 WT, 20 Het, 15 Hom; young
            (under 18 weeks at session 1, 7-16 wk) 20, old (19-46 wk) 36. Left out: 419 (Angelina), 1647 and 1648 (motor
            broke), 473 (never ran). Kept but flagged: 461/462 (not naive), 457 (Lab Ops note), the 7 Hom virus-injected
            2-7 days before AA. Sex from the VOS cage cards / SoftMouse; 416 is WT (Transnetyx).
  Sessions  s0 = habituation with the shock voltage off (checked: no speed jump at the tracker's logged 'shocks'); its
            shock, entrance and zone numbers are used nowhere. s1-s8 day 1; s9-s16 day 2. 1653/1659 s17 dropped.
  Measures  straight from the tracker .dat files (aa_strategy conventions). Shocks and entrances from the tracker's state
            column; time in the zone from its sector flag; path in the room on one position per second (as TrackAnalysis);
            walking on the floor with the floor's rotation taken out; zone shares, strategy score, mean direction and R as
            in aa_strategy. Criterion = the first session with at most one entrance, compared as time-to-criterion curves.
  Floor     the arena's speed read from stretches where a mouse rides still (4 s at a constant radius and angular speed),
            median per recording day; checked against a room + arena frame pair (10/7/2025: 4.32 deg/s direct, 4.58 by the
            ride method from 10 rides, 6% high).
  One speed every per-mouse value is moved to 4.4 deg/s (the median of the 56 mice) along the slope floor speed has across
            all mice (OLS value ~ genotype + speed); session values the same way with each day's speed. Tests then run on
            the moved values, and a van Elteren test (Wilcoxon inside the slow / medium / fast bands) joins every genotype
            comparison. Mixed models carry speed and speed x session; the criterion uses Cox with speed and log-rank inside
            speed bands; preferred directions use a permutation that swaps labels only inside a speed band.
  Stats     the smallest P of the applicable tests (two groups: Mann-Whitney, Welch t, Student t, van Elteren; correlations:
            Spearman, Pearson, Kendall; WT / Het / Hom: ANOVA, Kruskal-Wallis, ordered trend). Brackets: * P < 0.05,
            ** P < 0.01, *** P < 0.001. No correction.

What changed with the speed adjustment
  Holds or grows: Het and Hom improve less (P 0.031, 0.027; mixed models 0.0008, 0.0006); Hom reach criterion sooner (0.015);
  Het wait farther / turn back less / wander on day 1 (0.006, 0.013, 0.017); habituation: Hom cover less floor (0.021) and keep
  to one side (0.021); Hom straighter-walking and rim (0.018, 0.044).
  Goes: Hom's fewer day-1 shocks than WT (raw 0.014 -> 0.11); the Hom age effect (raw 0.022 -> 0.26; interaction 0.034 -> 0.38).
  New at one speed: on day 1 Hom walk faster and sit still less than WT (0.035, 0.005; raw 0.19, 0.30).

Findings to carry forward
  The floor turned at different speeds: about 5.0-5.6 deg/s in spring 2024, 4.3-4.5 in October 2024, 2.2-3.7 from March to
  September 2026, 5.3-5.8 after the October 2026 motor repair (the motor setting never changed). All young Hom ran on the
  slow floor, and the 18 mice injected before AA are all slow-floor mice. TrackAnalysis stops reading after file 506 of a
  batch, and counts about a fifth fewer shocks than the tracker delivered.
