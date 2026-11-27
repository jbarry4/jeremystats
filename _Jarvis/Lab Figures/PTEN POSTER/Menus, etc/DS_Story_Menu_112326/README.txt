DS story menu, first round (2026-11-23; revised the same evening, round 3)
The dentate spike (DS) part of the somatic-mosaicism narrative, as a menu of stories the data support.
Exploratory: one number per mouse, generous tests, no correction. Everything before this round is in ../Archive.

DS_Story_Menu_112326.pdf    the eleven pages in one file (figures with the narrative around them)

pages/  each page as PDF (vector, with the 3D views embedded as 600 dpi pictures) and PNG (300 dpi)
  01_menu                             the framework, the narrative in one paragraph, and the menu of eight stories
  02_primer                           the probe and the regions, a control mouse's DS, one DS / BT / IED, the sixteen mice
  03_story1_two_directions            DOSE: fast (240-420 Hz) power at the DS rises in IED+ mice and falls in IED- mice; m7 tested as an outlier
  04_story2_graded_with_knockout      DOSE: six DS features that scale with % knockout inside the PTEN group
  05_story3_lower_blade               PLACE: every mouse on one common CSD scale; the balance tips to the lower blade; IED- spikes are smaller
  06_story4_synchrony                 SYNCHRONY: uniform events, DS1/DS2 blurring, looser source-sink timing
  07_story5_borderline_transients     BTs: the in-between class, in 3D and flat views of the three Root Canal numbers
  08_story6_DS_BT_IED_same_session    DS, BTs and IEDs in the same five IED+ sessions; timing around IEDs
  09_story7_DS1_DS2                   the two entorhinal inputs along each blade's dendrites (depth on the vertical axis)
  10_story8_machine_learning          what held-out models see: IED status per mouse, m7, and the features they used
  11_what_next                        what each story needs from the next batch; corrections to earlier documents

tables/
  results_P_below_0.05.xlsx                every result with generous P < 0.05, one sheet per grouping (read-me sheet first)
  all_results.csv.gz                       every measure through every contrast (about 85,000 rows)
  per_mouse_values.csv.gz                  one number per mouse per measure
  BT_IED_and_fast_power_per_mouse.csv      DS / BT / IED counts and rates, and the DS Root Canal numbers, per mouse
  DS_BT_IED_events_five_IEDplus_sessions.csv  every event of the five IED+ sessions with its class and features
  m7_outlier_tests.csv                     Story 1b: Grubbs and line outlier tests for m7, every contrast with and without m7
  CSD_common_scale_per_mouse.csv           Story 3: each mouse's DS current on one common scale, by region and at each sink peak
  DS_BT_timing_around_IEDs.csv             Story 6e: observed over chance around IEDs, pooled and per mouse
  ML_heldout_calls_per_mouse.csv           Story 8: each PTEN mouse's held-out calls and its fast power

code/   the scripts that made all of the above (read-only on Jarvis; they ran in a scratch folder)

How things were done
  Mice      7 controls (m2 m21 m22 m26 m59 m60 m61), 4 PTEN IED- (m8 m33 m1, and m7 at 24% knockout), 5 PTEN IED+
            (m13 m28 m3 m5 m34). m6 left out (lab's call); m51 has 5 events. One baseline recording per mouse.
  Groupings IED status (lab sheet), knockout level (control / low 4-5% / high 19-28%), and % knockout (histology).
  Events    Halo set (Extraction Room "Dentate Spike" v9) is the main set; Strict (v10) is the check.
  BTs       borderline transients = the Root Canal Halo workflow's (6fa7fef7b7a3 v5) "inside both borders" and
            "extended ambiguous" classes (the Twilight Zone class in Jarvis). Like a borderline blood-pressure reading,
            one means little and a steady rate means something: controls have 0 to 0.075 per minute, IED+ mice 0.56 to
            1.89. IED class = "inside the IED border" plus "captured by the IED halo". DS border: 2,148 control events;
            IED border: the hand-sorted IEDs.
  Depth     No page uses the lab's layer labels. Every depth axis comes from the recording's own dentate spike: 0 is
            where the upper blade's DS sink peaks, 1 where the lower blade's does; the current source nearest each sink
            (toward the other blade) marks that blade's cell layer. Regions: CA1 above the upper sink's edge; each blade's
            distal dendrites from the sink's outer edge to its peak and proximal dendrites from the peak to the cell-layer
            source; the hilus between the two cell-layer sources (median positions over the 16 recordings). Depth runs
            down the page; in Story 7 each blade's own axis runs from its cell-layer source (0) to its average DS sink (1)
            and beyond, upward for the upper blade and downward for the lower blade.
  CSD scale When groups are compared, every mouse is divided by one number (the control average's deepest sink), so
            sizes compare across groups. Inside one mouse, classes (DS, BT, IED) and types (DS1, DS2) share that mouse's
            DS scale. CSD from the X-ray reads at 20 um per contact.
  m7        Story 1b tests m7 as an outlier: Grubbs' test (two-sided) inside its group, and its studentized deleted
            residual from the PTEN knockout line; both allow for m7 being the most extreme mouse. It is an outlier among
            the high-knockout mice (P 0.001) and off the line (P 0.004), not among the IED- mice (P 0.13).
  Stats     the smallest P of the applicable tests (two groups: Mann-Whitney, Welch t, Student t; knockout %: Spearman,
            exact for nine mice, Pearson, Kendall; three groups: ANOVA, Kruskal-Wallis, ordered trend; paired: paired t,
            Wilcoxon); no correction. Brackets: * < 0.05, ** < 0.01, *** < 0.001; no bracket, P >= 0.05. On line plots,
            significance is a bar along the axis (P < 0.05 at that depth or window).

Corrections to earlier documents (see the Archive README too)
  These H3 recordings are 20 um per contact. The earlier DS battery used 50 um, so its micrometer distances are 2.5 times
  too large; Jarvis's H3 probe template (backend/probes.py) also says 50 um, so CSD magnitudes in Jarvis are 6.25 times
  too small for these recordings (shapes, ratios and P values are unaffected). Earlier documents placed depth with the
  lab's layer labels; this menu does not.
