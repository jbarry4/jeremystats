* ========================================================================
* Tab 8, Joe's data. Comparison 8: Power, baseline (20 s) to both cues, gamma 30-90 Hz.
* Power in each region instead of coherence between regions.
* Each value: log10 power, gamma 30-90 Hz, the mean of that rat's trials on that day.
*
* Where SPSS answers it (Type III Tests of Fixed Effects):
*   day*phase        all regions together: did the change from Baseline (20 s) to Cue 1 + Cue 2 (20 s) differ between Precon1 and Precon4?
*   day*phase*region   region by region: did it differ more in some regions than in others?
*
* Tab 8 found: day*phase F(1, 7) = 0.37, p = .563 (no evidence of a change).
*              day*phase*region F(9, 63) = 1.51, p = .164 (none stands out).
* This full model estimates all its variances together, and SPSS reports
* Satterthwaite df, so its numbers will be close to tab 8's, not identical.
* For a result that changed, '3 Recreate the positive results' reproduces
* tab 8's F exactly.
* ========================================================================

* 1. Change the next line to the folder this file is in, then Run > All.
CD 'C:\Users\YOU\Downloads\joe_tab8_spss\1 Main comparisons'.

GET DATA /TYPE=TXT /FILE='08 Power, baseline 20 s to both cues - gamma.csv' /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=','
  /QUALIFIER='"' /ARRANGEMENT=DELIMITED /FIRSTCASE=2 /VARIABLES=
  rat F4.0 day F1.0 phase F2.0 region F3.0 power F14.10 day_name A8 phase_name A40 region_name A24.
VARIABLE LABELS rat 'Rat' /day 'Day' /phase 'Phase' /region 'Region' /power 'log10 power, gamma 30-90 Hz'.
VALUE LABELS day 1 'Precon1' 4 'Precon4'
  /phase 1 'Baseline (20 s)' 2 'Cue 1 + Cue 2 (20 s)'
  /region 1 'R ACC' 2 'R OFC' 3 'R DHC' 4 'R RSC' 5 'R PER' 6 'L POR-SUB' 7 'L RSC' 8 'L DHC' 9 'L OFC' 10 'L ACC'.

* 2. The mixed model: every rat, with every region it has.
MIXED power BY day phase region
  /FIXED=day phase region day*phase day*region phase*region day*phase*region | SSTYPE(3)
  /RANDOM=INTERCEPT day phase region day*phase day*region phase*region | SUBJECT(rat) COVTYPE(VC)
  /METHOD=REML
  /CRITERIA=DFMETHOD(SATTERTHWAITE)
  /PRINT=SOLUTION TESTCOV.
