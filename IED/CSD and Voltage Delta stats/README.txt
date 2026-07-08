================================================================================
CSD and Voltage Delta stats  --  CNO vs Baseline (PTEN DREADD project)
================================================================================

PURPOSE
-------
Quantify how the IED-locked laminar CSD and Voltage profiles change between the
BASELINE and CNO conditions. Everything here is derived from the project's
per-channel laminar values and reorganized into clean, analysis-ready tables,
plus ready-to-run paired statistics and an SPSS how-to.

All scripts are pure Python standard library (no pandas/numpy/scipy) so they run
under the cluster's base `python3`:  cd into this folder and `python3 <script>.py`.


EXPERIMENTAL DESIGN (read this first)
-------------------------------------
- 5 PTEN mice: M13_pten, M3_pten, M5_Pten, M34_ptenblind, m28_ptenblind.
- Each mouse was recorded at BASELINE and under CNO on the SAME chronically
  implanted probe -> this is a PAIRED / within-subject design (n = 5).
- For each session, values are per-channel laminar profiles on the 32 real
  (even) channels of the probe, at two timeframes of the averaged IED:
      GZ = "Ground Zero"  = the IED peak (t = 0)      [CSD = CenterSlice, V = GroundZero]
      AS = "After Spike"  = the propagation window     [CSD = TimeSlice,   V = AfterSpike]
- Each channel carries an anatomical Region label (CA1, CA1 SP, CA1 SLM,
  DG OML/MML/GCL 1&2, HIL, DG, ...).
- Because it is the SAME probe across a mouse's two sessions, a given Channel
  index is the SAME physical electrode in Baseline and CNO -> we pair by
  (Mouse, Channel).

PROVENANCE
----------
Source: ../DATA_AND_OUTPUT/Prepped_Merged_Long_Format.csv
        (built by ../DATA_AND_OUTPUT/prep_SPSS_input.py from
         Final_Matched_and_Collapsed_Stats.xlsx, sheet "Merged_Detailed_Data").
Only Data_Type == 'Original' rows are used for statistics. 'Interpolated_For_Viz'
rows are odd channels filled from their even neighbour for smooth plotting only
and are EXCLUDED here. Re-generate all tables with:  python3 build_tables.py


FILES IN THIS FOLDER
--------------------
RAW / CONSOLIDATED DATA (the numbers; regenerate with build_tables.py)
  raw_original_long.csv         Tidy long format, Original channels only.
        cols: Mouse, Group(Base/CNO), Type, Session_ID, Channel, Region,
              TimeFrame(GZ/AS), CSD_Val, Voltage_Val, Theta_Val
  paired_wide_by_channel.csv    One row per (Mouse, Channel, TimeFrame); Base vs CNO
        side by side + delta. This is the core "delta" table.
        cols: Mouse, Channel, TimeFrame, Region,
              Base_CSD, CNO_CSD, Delta_CSD,
              Base_Voltage, CNO_Voltage, Delta_Voltage,
              Base_Theta, CNO_Theta, Delta_Theta      (Delta = CNO - Baseline)
  region_means_by_session.csv   Channel values averaged within each Region, per session.
        cols: Mouse, Group, Region, TimeFrame, nChannels, Mean_CSD, Mean_Voltage
  region_paired_wide.csv        One row per (Mouse, Region, TimeFrame); region means
        Base vs CNO + delta.
        cols: Mouse, Region, TimeFrame, Base_MeanCSD, CNO_MeanCSD, Delta_MeanCSD,
              Base_MeanVoltage, CNO_MeanVoltage, Delta_MeanVoltage
  session_summary_metrics.csv   One row per (Mouse, Group, TimeFrame); whole-probe
        laminar summary features per session.
        cols: Mouse, Group, TimeFrame, nChannels,
              PeakSink_CSD (min), PeakSource_CSD (max), MaxAbs_CSD, RMS_CSD,
              PeakNeg_Voltage (min), PeakPos_Voltage (max), MaxAbs_Voltage, RMS_Voltage

ANALYSIS SCRIPTS + THEIR OUTPUTS
  build_tables.py                          -> the 5 data CSVs above
  paired_stats.py                          shared stats helper (t-test, exact Wilcoxon,
                                           Cohen's dz, describe); imported by the others
  analyze_01_session_summary_paired.py     -> results_01_session_summary.csv
        HEADLINE test. Per summary metric x timeframe, paired Baseline vs CNO across
        the 5 mice: means +/- SD, mean delta, paired t, EXACT Wilcoxon, Cohen's dz.
  analyze_02_region_paired.py              -> results_02_region.csv
        CNO vs Baseline WITHIN each anatomical region (region means, paired across mice
        that have the region in both sessions). Most sensitive to layer-specific effects.
  analyze_03_grand_delta_profile.py        -> results_03_grand_delta_profile.csv
        Laminar depth profile of the CNO-Baseline delta (per channel, averaged across
        mice, SEM, per-channel t vs 0). Shows WHERE along the probe the effect sits.

SPSS_instructions.txt   step-by-step for running the same tests in SPSS.


EXAMPLE ANALYSES YOU CAN DO
---------------------------
1. "Does CNO change the overall IED laminar response?"
   -> analyze_01 (paired t / Wilcoxon on PeakSink_CSD, RMS_Voltage, etc.). One number
      per mouse per condition; cleanest n=5 paired test.
2. "Which layer is affected?"
   -> analyze_02 (region-level). e.g. in this dataset DG GCL1 shows a large CNO voltage
      REDUCTION at GZ (mean delta ~ -441 uV, dz ~ -3.1). Report region deltas + effect size.
3. "What is the depth profile of the CNO effect?"
   -> analyze_03 + plot MeanDelta_CSD / MeanDelta_Voltage vs Channel (depth), with SEM.
4. "Is the CSD sink/source dipole stronger or weaker under CNO?"
   -> paired test on PeakSink_CSD and PeakSource_CSD (analyze_01), or dipole span from
      the profile (analyze_03).
5. Mixed / repeated-measures model (Condition x Region, Mouse random): use
   raw_original_long.csv or region_means_by_session.csv in SPSS (see SPSS_instructions.txt).
6. Theta relationship: Delta_Theta is included in paired_wide_by_channel.csv if you want
   to correlate CNO's theta change with its CSD/Voltage change.


COMMON PITFALLS  (please read before reporting anything)
--------------------------------------------------------
* n = 5 is small. A two-sided EXACT Wilcoxon signed-rank with n=5 can NEVER be < 0.0625,
  so it literally cannot reach p<0.05 no matter how clean the effect. Lead with EFFECT
  SIZES (Cohen's dz), mean deltas, and 95% CIs; treat p as supporting, not gatekeeping.
  The paired t-test can reach significance but is sensitive to its normality assumption
  at n=5.
* USE PAIRED TESTS. Baseline and CNO are the same mice -> paired t / Wilcoxon signed-rank
  / repeated-measures. Independent-samples tests are wrong here and throw away the
  within-mouse control that makes n=5 usable.
* Channel-index pairing is valid WITHIN a mouse (same electrode across its two sessions).
  It is NOT guaranteed to be the same ANATOMY across different mice (probe depth varies).
  So per-channel results (analyze_03) describe the effect PROFILE/shape; for cross-mouse
  claims prefer REGION-level (analyze_02) or per-mouse summary features (analyze_01).
* Region labels must be consistent across mice to be comparable, and many regions appear
  in only 1-3 mice -> those region rows are underpowered / descriptive only (n is flagged
  in results_02). Do not over-interpret n<4 regions.
* GZ and AS are DIFFERENT time windows of the IED -- analyze them separately; never pool.
* Sign conventions: CSD sink = negative, source = positive (PeakSink = min, PeakSource =
  max). Voltage polarity follows the recording's flip convention. Deltas are CNO - Baseline
  (negative delta = CNO is more negative / smaller-positive than Baseline).
* IED-count imbalance: Baseline sessions contributed far fewer IEDs than CNO (Base total
  ~41 vs CNO ~131 across mice; see ../DATA_AND_OUTPUT/Mice_group.csv). Each session's
  per-channel value is an average over that session's Solid IEDs, so Baseline averages are
  estimated from fewer events (noisier). Per-mouse pairing helps, but keep this in mind.
* Multiple comparisons: analyze_02 (many regions) and analyze_03 (32 channels x 2 tf) run
  many tests. Apply FDR/Bonferroni or treat as exploratory before claiming per-region /
  per-channel significance.
* Absolute amplitudes vary a lot by probe placement across mice. The within-mouse delta
  cancels placement; if you compare raw amplitudes across mice, consider per-mouse
  normalization first.
* Exclude 'Interpolated_For_Viz' rows for stats (already done here). Do not re-add them.
================================================================================
