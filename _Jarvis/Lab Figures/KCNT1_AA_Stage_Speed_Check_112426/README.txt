KCNT1 active avoidance: stage (floor) speed sanity check, 2026-11-24
A supplement to KCNT1_AA_Story_Menu_112326 and KCNT1_AA_Speed_Supplement_112326.

KCNT1_AA_Stage_Speed_Check_112426.pdf    10 pages (PNGs at 300 dpi and single-page PDFs in pages/)

  1  Menu: the short version and the page list
  2  How the floor speed is read: one ride step by step; a day's readings; from days to a mouse
  3  Known answers: the 10/7/2025 day with a floor frame (direct 4.32 deg/s; rides 4.58 because the mouse
     crept forward 0.26 deg/s; rides minus creep 4.35); sessions where the tracker's motor log changed
     (log 0 = floor stopped, readings 0.0; log 7 = 1.5x faster)
  4  Robust to the rules: 14 rule changes move a day's reading by a median of 0.00-0.08 deg/s; the peak of
     every 1-s angle speed and a rigid-turn fit agree with the menu day by day (r 0.99)
  5  Precise and unbiased: 95% range of a day's reading about +/-0.06 deg/s (resampled mice); two mice on the
     same day agree (r 0.98); Het and Hom read the floor like WT
  6  Weak spots: the floor turns about a point 0.3-4.3 cm off the tracker's center (day readings 0-0.55 deg/s
     low, median 0.19); on five days the floor changed speed mid-day (8/12/2026: 2.3 to 3.4 deg/s at ~2 pm;
     4/10/2026 after a motor pause; 3/13-14/2026 near-stall; 3/31/2024 late step up)
  7  What it means: every headline re-run under nine readings and 200 redraws. 'Refined' = each session's
     half-hour reading about that day's true center. 20 of the 23 headlines below P 0.05 stay there; the 3
     that slip were borderline (0.043-0.044 to 0.051-0.062). Young Hom slower than every old Hom under
     every reading (Angelina's point stands)
  8  Outliers: every headline's robust outliers (> 3.5 robust s.d. from the genotype median), raw and at one
     speed, P with and without them; the mice that keep turning up (417, 827, 413, 1634, 459)
  9  Leave one mouse out: P with each mouse left out in turn, one speed and raw
 10  The menu's check table (page 11 of the story menu) three ways: at one floor speed, raw, and at one
     speed with the refined reading

Tables (tables/)
  floor_speed_by_day.csv            every day: the menu's reading, true center, rigid fit, 1-s peaks, fitted
                                    center, number of readings, 95% range, and the reading under each rule change
  floor_speed_by_session.csv        every session: own reading, day reading, half-hour reading (both centers)
  floor_speed_by_mouse.csv          every mouse's speed under six readings
  headlines_under_each_reading.csv  the 28 headlines' P under every reading + share of redraws below 0.05
  outliers_by_headline.csv          outliers per headline and reading, P with and without, drop-one range
  outlier_mice.csv                  one row per outlier flag
  drop_one_mouse_P.csv              P with each mouse left out (one speed and raw)
  mice_flagged_most.csv             counts per mouse
  check_table_three_ways.xlsx       the page-10 tables

How the reading works (as in the menu, a1_extract.passive_rides): positions taken once a second; a reading is
four 1-s steps in a row with the distance from the center changing < 0.4 cm a second, the four angle speeds
varying < 0.25 deg/s (s.d.), their mean 1.5-9 deg/s, > 12 cm from the center. A day's speed = median of all
its readings; a session uses its day's speed; a mouse's speed = median over its 17 sessions.

Notes
  * The tracker's MotorState column read 4 in 99.8% of frames at every floor speed: it logs the setting,
    not the speed. The floor-frame reference light (FrameInfo bit 1) was never on in the 958 AA sessions,
    so the floor speed can only be read from the mice.
  * Mouse 1649 ran 8 of its 10 s7 minutes with the motor logged at 7 (about 8.8 deg/s); the menu used the
    day's 5.3 for that session.
  * Nothing in the story menu was changed by this check.

Code (code/): c1_floor_cache.py (cache the tracks) -> c2_floor_check.py (readings, checks) ->
c3_consequences.py (headlines under each reading) -> c4_outliers.py (outliers, drop-one, check tables) ->
s2_floor_pages.py (pages, package). They import the story menu's analysis.pkl / speed.pkl / figlib_aa.py /
stats_lib.py (see the story menu's code folder).
