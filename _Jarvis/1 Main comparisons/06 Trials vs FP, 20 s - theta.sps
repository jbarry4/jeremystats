* ========================================================================
* Tab 8, Joe's data. Comparison 6: Trials vs FP, 20 s, theta 5-12 Hz.
* The Precon1 to Precon4 change in the trials (both cues, 20 s) against the same change in random 20 s FP snippets.
* Each value: coherence (Dickson 2022), theta 5-12 Hz, the mean of that rat's trials on that day.
*
* Where SPSS answers it (Type III Tests of Fixed Effects):
*   day*source        all pairs together: did the change from Trials (Cue 1 + Cue 2) to FP snippets differ between Precon1 and Precon4?
*   day*source*pair   pair by pair: did it differ more in some pairs than in others?
*
* Tab 8 found: day*source F(1, 7) = 2.45, p = .161 (no evidence of a change).
*              day*source*pair F(43, 301) = 0.91, p = .638 (none stands out).
* This full model estimates all its variances together, and SPSS reports
* Satterthwaite df, so its numbers will be close to tab 8's, not identical.
* For a result that changed, '3 Recreate the positive results' reproduces
* tab 8's F exactly.
* ========================================================================

* 1. Change the next line to the folder this file is in, then Run > All.
CD 'C:\Users\YOU\Downloads\joe_tab8_spss\1 Main comparisons'.

GET DATA /TYPE=TXT /FILE='06 Trials vs FP, 20 s - theta.csv' /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=','
  /QUALIFIER='"' /ARRANGEMENT=DELIMITED /FIRSTCASE=2 /VARIABLES=
  rat F4.0 day F1.0 source F2.0 pair F3.0 coherence F14.10 day_name A8 source_name A40 pair_name A24.
VARIABLE LABELS rat 'Rat' /day 'Day' /source 'Source' /pair 'Pair of regions' /coherence 'coherence (Dickson 2022), theta 5-12 Hz'.
VALUE LABELS day 1 'Precon1' 4 'Precon4'
  /source 1 'Trials (Cue 1 + Cue 2)' 2 'FP snippets'
  /pair 1 'R ACC - R OFC' 2 'R ACC - R DHC' 3 'R ACC - R RSC' 4 'R ACC - R PER' 5 'R ACC - L POR-SUB' 6 'R ACC - L RSC' 7 'R ACC - L DHC' 8 'R ACC - L OFC' 9 'R ACC - L ACC' 10 'R OFC - R DHC' 11 'R OFC - R RSC' 12 'R OFC - R PER' 13 'R OFC - L POR-SUB' 14 'R OFC - L RSC' 15 'R OFC - L DHC' 16 'R OFC - L OFC' 17 'R OFC - L ACC' 18 'R DHC - R RSC' 19 'R DHC - R PER' 20 'R DHC - L POR-SUB' 21 'R DHC - L RSC' 22 'R DHC - L DHC' 23 'R DHC - L OFC' 24 'R DHC - L ACC' 25 'R RSC - R PER' 26 'R RSC - L POR-SUB' 27 'R RSC - L RSC' 28 'R RSC - L DHC' 29 'R RSC - L OFC' 30 'R RSC - L ACC' 31 'R PER - L RSC' 32 'R PER - L DHC' 33 'R PER - L OFC' 34 'R PER - L ACC' 35 'L POR-SUB - L RSC' 36 'L POR-SUB - L DHC' 37 'L POR-SUB - L OFC' 38 'L POR-SUB - L ACC' 39 'L RSC - L DHC' 40 'L RSC - L OFC' 41 'L RSC - L ACC' 42 'L DHC - L OFC' 43 'L DHC - L ACC' 44 'L OFC - L ACC'.

* 2. The mixed model: every rat, with every pair it has.
MIXED coherence BY day source pair
  /FIXED=day source pair day*source day*pair source*pair day*source*pair | SSTYPE(3)
  /RANDOM=INTERCEPT day source pair day*source day*pair source*pair | SUBJECT(rat) COVTYPE(VC)
  /METHOD=REML
  /CRITERIA=DFMETHOD(SATTERTHWAITE)
  /PRINT=SOLUTION TESTCOV.
