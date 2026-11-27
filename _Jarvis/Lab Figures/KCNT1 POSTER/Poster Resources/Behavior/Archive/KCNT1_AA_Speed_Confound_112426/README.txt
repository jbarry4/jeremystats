KCNT1 active avoidance: floor speed is a confounder, the evidence (2026-11-24)
A supplement to KCNT1_AA_Story_Menu_112326. Companion: KCNT1_AA_Rescue_112426.

KCNT1_AA_Speed_Confound_112426.pdf    6 pages (PNGs at 300 dpi and single-page PDFs in pages/)

  1  Menu and short version
  2  Different floors: each mouse's floor speed by genotype x age (young Hom 2.8-3.6 deg/s, young WT 5.7-6.1,
     no overlap); what travels with speed (injection rho -0.77, young Hom -0.51, 2026 runs); which comparisons
     share speeds (only old Hom vs old WT, and Het vs WT)
  3  Inside one mouse: +1.8 entrances per session for each extra deg/s (P 0.0007; per turn P 0.26); the 8/12/2026
     mid-day speed-up (young Hom gained entrances at s5 while other mice improved, P 0.013); 1649's motor-7 session
  4  Inside one genotype: old WT day-1 entrances rise with speed (rho 0.55, P 0.034; per turn rho 0.22, P 0.42);
     old WT on the fast 2024 floor vs the slow 2026 floor (11.5 vs 4.6 day-1 entrances, P 0.009; per turn P 0.25)
  5  Young Hom vs young WT: raw day-1 shocks 5.7 vs 15.2 (P 0.016); per turn P 0.42; floor turns per session
     9.9 vs 5.3
  6  Verdict: the four tests of a confounder; which menu claims survive per turn; replaying a mouse's walking at
     another floor speed doubles its entrances (avoidance is timed to the room), so raw counts cannot be rescaled

Red background on a panel or cell = the groups compared ran at different floor speeds.
Floor speed = the refined reading of KCNT1_AA_Stage_Speed_Check_112426 (each session's half-hour reading about
that day's true center; a mouse = median of its sessions). Per turn = divided by speed x 600 s / 360.

Tables (tables/): same_mouse_speed_effects.csv, speed_correlations_within_WT.csv,
young_Hom_vs_young_WT_raw_and_per_turn.csv, old_WT_fast_vs_slow_floor.csv, what_travels_with_speed_rho.csv,
floor_speed_by_mouse.csv

Code (code/): d1_replay.py (replays), e1_confound_rescue.py (every number, -> cr.pkl), crfig.py,
s3_confound_pages.py. They need the story menu's analysis.pkl and the stage speed check's floor_check.pkl /
floor_conseq.pkl.
