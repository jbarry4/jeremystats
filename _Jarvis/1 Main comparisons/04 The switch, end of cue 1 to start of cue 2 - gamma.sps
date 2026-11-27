* ========================================================================
* Tab 8, Joe's data. Comparison 4: The switch: end of cue 1 to start of cue 2, gamma 30-90 Hz.
* The last 2 s of cue 1 (8-10 s) against the first 2 s of cue 2 (10-12 s).
* Each value: coherence (Dickson 2022), gamma 30-90 Hz, the mean of that rat's trials on that day.
*
* Where SPSS answers it (Type III Tests of Fixed Effects):
*   day*phase        all pairs together: did the change from 8-10 s to 10-12 s differ between Precon1 and Precon4?
*   day*phase*pair   pair by pair: did it differ more in some pairs than in others?
*
* Tab 8 found: day*phase F(1, 7) = 0.07, p = .800 (no evidence of a change).
*              day*phase*pair F(43, 301) = 0.89, p = .666 (none stands out).
* This full model estimates all its variances together, and SPSS reports
* Satterthwaite df, so its numbers will be close to tab 8's, not identical.
* For a result that changed, '3 Recreate the positive results' reproduces
* tab 8's F exactly.
* ========================================================================

* 1. Change the next line to the folder this file is in, then Run > All.
CD 'C:\Users\YOU\Downloads\joe_tab8_spss\1 Main comparisons'.

GET DATA /TYPE=TXT /FILE='04 The switch, end of cue 1 to start of cue 2 - gamma.csv' /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=','
  /QUALIFIER='"' /ARRANGEMENT=DELIMITED /FIRSTCASE=2 /VARIABLES=
  rat F4.0 day F1.0 phase F2.0 pair F3.0 coherence F14.10 day_name A8 phase_name A40 pair_name A24.
VARIABLE LABELS rat 'Rat' /day 'Day' /phase 'Phase' /pair 'Pair of regions' /coherence 'coherence (Dickson 2022), gamma 30-90 Hz'.
VALUE LABELS day 1 'Precon1' 4 'Precon4'
  /phase 1 '8-10 s' 2 '10-12 s'
  /pair 1 'R ACC - R OFC' 2 'R ACC - R DHC' 3 'R ACC - R RSC' 4 'R ACC - R PER' 5 'R ACC - L POR-SUB' 6 'R ACC - L RSC' 7 'R ACC - L DHC' 8 'R ACC - L OFC' 9 'R ACC - L ACC' 10 'R OFC - R DHC' 11 'R OFC - R RSC' 12 'R OFC - R PER' 13 'R OFC - L POR-SUB' 14 'R OFC - L RSC' 15 'R OFC - L DHC' 16 'R OFC - L OFC' 17 'R OFC - L ACC' 18 'R DHC - R RSC' 19 'R DHC - R PER' 20 'R DHC - L POR-SUB' 21 'R DHC - L RSC' 22 'R DHC - L DHC' 23 'R DHC - L OFC' 24 'R DHC - L ACC' 25 'R RSC - R PER' 26 'R RSC - L POR-SUB' 27 'R RSC - L RSC' 28 'R RSC - L DHC' 29 'R RSC - L OFC' 30 'R RSC - L ACC' 31 'R PER - L RSC' 32 'R PER - L DHC' 33 'R PER - L OFC' 34 'R PER - L ACC' 35 'L POR-SUB - L RSC' 36 'L POR-SUB - L DHC' 37 'L POR-SUB - L OFC' 38 'L POR-SUB - L ACC' 39 'L RSC - L DHC' 40 'L RSC - L OFC' 41 'L RSC - L ACC' 42 'L DHC - L OFC' 43 'L DHC - L ACC' 44 'L OFC - L ACC'.

* 2. The mixed model: every rat, with every pair it has.
MIXED coherence BY day phase pair
  /FIXED=day phase pair day*phase day*pair phase*pair day*phase*pair | SSTYPE(3)
  /RANDOM=INTERCEPT day phase pair day*phase day*pair phase*pair | SUBJECT(rat) COVTYPE(VC)
  /METHOD=REML
  /CRITERIA=DFMETHOD(SATTERTHWAITE)
  /PRINT=SOLUTION TESTCOV.
