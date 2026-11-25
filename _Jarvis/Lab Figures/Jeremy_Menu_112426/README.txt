Jeremy menu (2026-11-24)
Jeremy's eight questions about the PTEN dentate spike (DS) data, each answered on its own page: his question word for word
("Jeremy Asked"), a one-sentence answer ("Results show"), then panels whose headings state what they show. Two added pages
cover every mouse in the Strict Root Canal workflow, with a summary table and an aggregate.
Exploratory: one number per mouse, generous tests, no correction. Built on the DS story menu of 2026-11-23
(../DS_Story_Menu_112326); where a page recaps a menu result it says so.

Jeremy_Menu_112426.pdf    the eleven pages in one file; page 1 lists every question with its one-line answer, and a key

The answers in one line
  1  Does the %KO cause changes in synaptic efficacy for dentate spikes
     No for the current a DS carries; yes for what it produces: for the same sink, IED+ mice's DS carry more fast power,
     and over all mice this output rises with knockout.
  2  Are there group differences in DS1 vs DS2 (do they make both)
     Yes, most mice in every group make both. With knockout DS2 become rarer and the two types grow harder to tell
     apart; their sink timing holds.
  3  Are there differences in CSD sink for MML/OML by blade in PTEN animals by % KO
     Not by % knockout: no MML or OML sink of either blade follows it. By group, the low-knockout (IED-) mice have weaker
     MML sinks in both blades; the OML is unchanged.
  4  Are there differences in dominant frequency for MML/OML by blade in PTEN animals by % KO
     Not for the DS's own dominant frequency (12 to 15 Hz), in any layer. The fast power riding on it moves higher with
     knockout, most in the lower blade's MML.
  5  Do results of 3 and 4 change when you open filters
     No for the sinks and the dominant frequency, on every band. The fast power's upward shift is strongest with no
     filter; a 300 Hz ceiling leaves it only in the lower MML.
  6  Can you predict which mice made the abnormal dentate spikes based on %KO
     Mostly: % knockout alone gives an AUC of 0.90, and m7 is the one miss. The dentate spikes themselves do better:
     their fast power separates every mouse.
  7  Do the results change when you sort the dentate spikes by where they fall in the continuum
     Yes. In IED+ mice BTs carry more MML current than the same mice's DS (red events lean the same way) and both far
     more fast power; against a control DS only the fast power is higher.
  8  Do the results of 7 change when you open the filter
     Not the current: the BTs' extra current over their own DS holds on every band. The fast-power lead needs the fully
     open band and fades with a 300 Hz ceiling.
  +  Every mouse in Root Canal (Strict workflow), table and aggregate
     Every mouse has undecided events, mostly wider than its DS; IED+ mice have 2.1 times the control share, mostly with
     more fast power than a DS. m7 has as many as an IED+ mouse (30%), but 37 of its 38 carry less.

pages/  each page as PDF (vector) and PNG (300 dpi)
  01_menu                      the questions, the one-line answers, and the words and marks used on every page
  02_q1_synaptic_efficacy      sink size and output per input (fast power for a standard sink), by group and % knockout
  03_q2_ds1_ds2                who makes both DS types; DS1 and DS2 rates, mix, timing, separation and position
  04_q3_mml_oml_sink           MML and OML sinks of each blade against % knockout and by IED status
  05_q4_dominant_frequency     the DS's own dominant frequency, and where its fast power sits, per layer
  06_q5_open_filters           questions 3 and 4 on every filter band (P grid and key panels)
  07_q6_predict_abnormal       which mice make BTs and red events; ROC for % knockout, DS fast power and held-out models
  08_q7_continuum              DS, BT and IED-class events of the same IED+ mice against each other and against control DS
  09_q8_q7_open_filters        question 7 on every filter band (P grid and key panels)
  10_every_mouse               all 16 mice in the Strict workflow; m7 framed
  11_table_and_aggregate       one table of every mouse with m7 highlighted, pooled rows, aggregate clouds, per-mouse tests

tables/
  q1_q2_per_mouse.csv                       DS counts and rates, DS1/DS2 split, sink, rise, output per input, per mouse
  q3_q5_layer_sinks_every_filter.csv        MML and OML sinks per mouse, blade and filter set (control average = 1)
  q4_q5_q7_q8_reads_per_mouse.csv           from the 2 kHz reads, per mouse, band, class, blade and layer: sinks, dominant
                                            frequency, spectral centroid, fast-power center and fast gain
  every_mouse_undecided_strict_workflow.csv the Strict workflow's counts per mouse, and where its undecided events sit

code/   the scripts that made all of the above (read-only on Jarvis; they ran in a scratch folder)

How things were done
  Mice      7 controls (m2 m21 m22 m26 m59 m60 m61), 4 PTEN IED- (m8 m33 m1, and m7 at 24% knockout), 5 PTEN IED+
            (m13 m28 m3 m5 m34). m6 left out (lab's call). One baseline recording per mouse.
  Classes   the Root Canal Halo workflow's DS, borderline transients (BTs, the Twilight Zone class in Jarvis) and IED
            class (red), as in the DS story menu.
  Data      Questions 1 to 3 and 5: the frozen DS battery (every Halo DS at 1 kHz, seven filter sets: 5-100 Hz main,
            notch only, 1-100, 1-300, 5-300, 5-50, 10-40 Hz). Questions 4, 5, 7 and 8: every DS of every mouse (and every
            BT and IED-class event of the five IED+ mice) read again at 2 kHz through Jarvis's X-ray reader, one pipeline
            for all 16 mice; the battery's bands applied to each +-100 ms window.
  Layers    No lab layer labels. Along each blade's own DS axis, 0 is the cell-layer current source and 1 the recording's
            average DS sink; MML = 0.7 to 1.3, OML = 1.3 to 2.0. Depth runs on the vertical axis, upward for the upper
            blade and downward for the lower blade.
  Scale     Groups are always compared on one scale: every mouse divided by the control average (deepest DS sink = 1).
  Efficacy  Input = the DS sink at its peak (and its 10-90% rise slope). Output per input = each DS's fast (240-420 Hz)
            power fitted against its sink within each mouse (Theil-Sen); the fit at the control-average sink is the fast
            power a standard synaptic current produces.
  Frequency Dominant frequency = the peak of the event's own spectrum over +-50 ms (5-300 Hz). Fast power = the event's
            power (+-25 ms) over the moment before (-100 to -50 ms); its center is the power-weighted frequency of what
            the DS adds between 100 and 500 Hz (100 to 300 Hz on bands that stop at 300), its gain the mean dB from 250
            to 500 Hz (200 to 300 Hz).
  Appendix  Root Canal workflow "Ambiguous PTEN and CTL Baseline (Optimized Paramters/Snap/10% Grace[Extraction Room;
            No P-spikes])) v4" (the workflow's own name): undecided = inside both borders + outside both, exactly as
            Jarvis counts it; "more fast power than a DS" = above the DS border's center (13 dB).
  Stats     the smallest P of the applicable tests (two groups: Mann-Whitney, Welch t, Student t; knockout %: Spearman,
            Pearson, Kendall; paired within the five IED+ mice: paired t, Wilcoxon); no correction. Brackets: * < 0.05,
            ** < 0.01, *** < 0.001; no bracket, P >= 0.05.

Checked and corrected along the way
  DS1 rise  A first pass timed both DS types at the main-sink contacts, where DS1 has no sink, and showed DS1 rising more
            slowly with knockout (P 0.029). Timed at each type's own deepest contact, the effect is gone (P 0.46); no
            page claims it.
  Fast peak The single highest bin between 100 and 500 Hz sticks at the 100 Hz edge, so the pages use the fast-power
            center and gain instead.
  Undecided They do not all lean one way: most of the IED+ mice's carry more fast power than a DS (84%), as do 60% of the
            controls', but only 17% of the low-knockout mice's and 1 of m7's 38. m7's undecided events carry about as
            much fast power as its own DS (5.0 against 5.6 dB): its whole cloud sits low.
  Red events Question 7 also tests the IED-class (red) events against the same mice's DS: far more fast power
            (P 4.5e-06), MML sinks larger in 4 of 5 mice but short of P 0.05 (0.062 upper, 0.056 lower).

Rebuild (in the scratch folder, in this order): m10_reads_all.py (2 kHz reads, about 25 minutes), j1_battery.py,
j2_freq.py, jpages.py cover q1 q2 q3 q4 q5 q6 q7 q8 every table, j_package.py, then j_merge.py with miniconda's python.
They also use the DS story menu's intermediate files (uprof.pkl, profiles_ds.pkl, the Root Canal events); see that
menu's code.
