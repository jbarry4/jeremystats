PTEN behavioral menu (2026-11-27)
The Pten KO mosaicism behavior report (version 3, 2026-11-24; Barry Playground/PTEN_Manuscript2_handoff) recast in the menu
format: one result per page, with the question it answers, "Results show:" in one conclusive sentence, lettered panels whose
headings state what they show, then How it was measured / What it shows / Reading / Caveats. Every number is the report's.
The figures are the report's own vector graphics (from Pten_KO_mosaicism_report_v3.docx), cropped so that their original
panel titles are gone; nothing in the data or the plots was changed.

PTEN_Behavioral_Menu.pdf    the 27 pages in one file

pages/  each page as PDF (vector) and PNG (300 dpi)
  01_menu                              the story in one paragraph and every question with its short answer and page
  02_read_me_first                     the task (the 1.2 s rule, cued and hidden sessions, phases 7 to 10), the mice, the marks and statistics, the words
  03_learning_the_cue_rule             Fig 1: Lo mice learn slowest; Hi near the WT rate
  04_the_task_and_the_session_measures Figs 2 and 3: cued, nobody is impaired; hidden, both KO groups earn less and Hi collapse at phase 10
  05_change_across_the_rotations       Fig 4: only Hi mice decline with each rotation, only without the cue
  06_cue_against_place                 Fig 5: WT and Lo keep the old place against the cue; Hi follow the cue
  07_new_place_against_old_place       Fig 6: without the cue every group remembers both places
  08_time_at_each_zone                 Fig 7: Lo lose the goal at phase 9, Hi at phase 10
  09_getting_to_the_goal               Fig 12 and Supp S8: aim, launch and approach are normal
  10_arriving_at_the_goal              Fig 8: Hi mice cross the hidden goal without stopping (16.4 against 11.5 cm/s)
  11_slowing_and_pausing               Fig 9: WT pause more each rotation, Hi less, out in the arena
  12_braking_at_the_goal               Fig 13: Hi mice brake less at the hidden goal; like WT at former goals
  13_the_set_to_rule_out               Fig 10: WT and Lo search the former goals more each rotation; Hi barely (P 0.003)
  14_where_they_pause                  Fig 11: removing the cue makes WT pause more and Hi less (P 0.043)
  15_what_they_do_instead              Fig 14: Hi mice run instead
  16_after_a_miss                      Fig 15: Hi mice come back after a miss like WT; Lo rarely
  17_last_rotation_zones               Fig 16: at phase 10 Hi mice visit the goal but stay under 1.2 s
  18_last_rotation_performance         Fig 17: % KO predicts performance only at the last hidden rotation
  19_does_it_scale_with_the_load       Fig 18: only pausing at former goals and total pausing grow apart
  20_theta_csd_by_layer                Fig 19 and Supp S14: twice WT theta current in GCL2 and MML2 of Hi mice; CNO brings it back
  21_theta_csd_and_percent_ko          Fig 20: the lower-blade current follows % KO at baseline, not after CNO
  22_theta_csd_marks_the_ied_mice      Fig 21: baseline theta CSD picks out the IED mice (AUC 0.97), not after CNO
  23_the_dreadd_works                  Fig 22: CNO cuts KO granule neuron firing by three quarters
  24_cno_and_behavior                  Fig 23: hidden-goal time rises with CNO in KO mice and falls in WT
  25_interictal_discharges             Fig 24: IEDs start in GCL2 and MML2; CNO does not reduce them
  26_behavior_follows_theta            Fig 25: behavior follows the theta current, not the IED rate
  27_what_it_adds_up_to                synthesis table, how it fits, caveats, open questions

code/   engine.py (page layout), content.py (every page's words, panel crops and headings), build.py (pulls the figures
        out of the report docx, builds the pages and this folder), grid.py / gaps.py / hgaps.py (helpers used to read off
        crop boxes)

What was changed from the report, and what was not
  - Words: every page title and panel heading now states a finding; legends were moved into "How it was measured" and
    shortened; American spelling; P values written as P 0.004.
  - Numbers: none changed or added. Correction-based statements (q values, "survives correction") were left out, as in
    the other menus (exploratory); the P values are the report's raw ones.
  - Figures: cropped only. A few leftover panel letters or titles inside a crop are covered with the figure's own
    background color (masks in content.py). Text inside the figures (axis labels, keys) is the report's, including its
    British spelling.
  - Supplementary figures used: S8 (page 9) and S14 (page 20). The other supplementary figures are in the report.

Rebuild: python build.py with miniconda's Python (PyMuPDF). It reads the report docx at its path in Barry Playground and
writes this folder.
