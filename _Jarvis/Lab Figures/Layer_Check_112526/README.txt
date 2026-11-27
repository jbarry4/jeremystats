Layer check (2026-11-25)
Every Jeremy menu result that rests on a layer (MML / OML) or a sink position, computed twice: with the menu's layers
("old") and with tighter ones built from each DS type's own sink ("tight"), side by side. The Jeremy menu itself
(../Jeremy_Menu_112426) is NOT changed. Exploratory: one number per mouse, generous tests, no correction.

Why: the old layers were steps along an axis whose 1 was the sink of the AVERAGE of all DS. One type is 85 to 95% of
each mouse's DS, so that anchor sat on the larger type's sink whichever layer that was, and the OML (v 1.3 to 2.0) was
a multiple of the same blended distance. DS2's sink is in the MML and DS1's in the OML, so the layers should come from
the types themselves.

Layer_Check_112526.pdf   the eleven pages in one file

The tight rule (the user's answers, 2026-11-25)
  anchors    per blade, MML centered on the DS2 sink and OML on the DS1 sink, each from that type's own mean CSD at
             the DS peak (+-3 ms). The battery's DS1/DS2 names are positional (DS1 = the type whose sink sits farther
             from the cell layer, checked and swapped by the battery), so the nearer sink is always MML.
  no split   mice whose types do not separate (question 2's rule: separation index >= 0.45, each type >= 5% and >= 5
             events: m2, m21, m8, m3, m5), or a blade where DS1 is not farther out, use the all-DS sink as MML and put
             the OML the median DS1-to-DS2 distance farther out (53 um upper, 57 um lower)
  width      +-2 contacts (+-40 um, 20 um per contact); where the two anchors are under 80 um apart, each contact goes
             to the nearer anchor only (split at the midpoint), so no contact is in both layers
  events     all DS read at both layers, exactly as before; only the contacts change. The same contacts are used on
             every filter band.

pages/
  01_where_the_tight_layers_sit     DS1 and DS2 mean profiles of all 16 recordings with the tight spans (fills) and the
                                    old ones (bars); per mouse, where each layer's center moved (um from the source)
  02_change_table_q2_q3_q4          every Q2, Q3 and Q4 result: old effect and P, tight effect and P, verdict
  03_change_table_q7                the same for Q7
  04_q3_layer_sinks                 Q3: layer sinks against % knockout and by IED group, old row above tight row
  05_q4_frequency                   Q4: dominant frequency and fast-power center per layer against % knockout
  06_q4_lfp_gain_and_q2_position    Q4: LFP fast gain by IED group; Q2: how far DS1's sink sits beyond DS2's
  07_q5_every_band                  Q5: the P grid on every filter band, old above tight
  08_q7_currents_and_center         Q7: sinks and fast-power center per layer, control DS | IED+ DS | BT | IED class
  09_q7_fast_gain                   Q7: fast gain per layer
  10_q8_every_band                  Q8: the P grid on every filter band, old above tight
  11_what_moved_the_results         which mice moved each changed result, with their own numbers; what holds; caveats

tables/
  old_vs_tight_every_layer_result.csv   62 results: question, result, what the menu says, old and tight effect and P,
                                        verdict (holds / holds (n.s.) / lost / new / reverses at P 0.05)
  q5_every_band_old_vs_tight.csv        the Q5 grid, every row and band, both rules
  q8_every_band_old_vs_tight.csv        the Q8 grid, every row and band, both rules
  tight_layers_per_mouse.csv            per mouse and blade: method, anchors (um from the source), DS1-DS2 gap, and the
                                        contacts in each layer under both rules

What it found
  52 of 62 results keep their verdict (26 significant both ways, 26 significant neither way); 6 lose significance, 4
  become significant, none reverses. Of the 45 the menu states in words, 40 still agree with it.
  Lost
    Q3 upper MML sink, IED- vs control         P 0.024 -> 0.060   (IED- still lowest; control MML values fall in
    Q3 lower MML sink, IED- vs control         P 0.033 -> 0.100    m22, m60 and m2)
    Q4 upper MML fast-power center vs % KO, all mice   P 0.017 -> 0.14
    Q7 upper MML fast-power center, BT vs own DS        P 0.029 -> 0.29
    Q7 upper MML fast-power center, BT vs control DS    P 0.0097 -> 0.28
    Q7 lower MML fast-power center, BT vs own DS        P 0.034 -> 0.072
  New
    Q2 lower blade: DS1 sits nearer DS2 in IED+ than IED- mice   P 0.055 -> 0.027 (as in the upper blade)
    Q7 upper OML fast-power center, BT vs control DS            P 0.10 -> 0.010
    Q7 lower OML sink, BT vs own DS                             P 0.44 -> 0.027
    Q7 lower OML sink, IED class vs own DS                      P 0.19 -> 0.024
  Holds: no layer sink follows % knockout; the DS's own dominant frequency is flat in every layer; the lower MML's
  fast-power center rises with knockout (PTEN P 0.031 -> 0.002); the LFP fast gain is lower in IED- and higher in IED+
  mice in every layer; BTs carry more MML current than the same mice's DS (notch band: upper P 0.043, lower 0.036) and
  no more than a control DS; the BTs' fast gain is above both in every layer.
  Where it comes from: three mice separate with DS1 as the larger type (m22, m60, m34); by position their MML moves
  inward onto the smaller DS2 (27 to 55 um) and their OML lands where the old MML was. The rest of the change comes from
  narrowing every span to +-40 um. Whether those three mice's larger type really sits in the OML is the open question;
  rerunning with only that rule changed would show how much of the change it carries.
  Borderline: on the 5-100 Hz main band the upper blade's BT-over-DS current is P 0.052 with tight layers.

Rebuild (in the menu scratch folder): python tight_layers.py; JM_LAYERS=tight python j1_battery.py (writes
jeremy_battery_tight.pkl, about 20 s); JM_LAYERS=tight python j2_freq.py (writes jeremy_freq_tight.pkl, about 4 min);
python layer_check.py; then merge pages/*.pdf (miniconda's python, pymupdf). Without JM_LAYERS the two scripts make the
menu's original files, unchanged.
