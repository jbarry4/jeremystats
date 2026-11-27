Jeremy menu, tight-layer edition (2026-11-27)
The Jeremy menu (../Jeremy_Menu_112426) rebuilt with the tight MML / OML of the layer check (../Layer_Check_112526): in each
recording and blade the MML is centered on DS2's sink and the OML on DS1's sink, +-40 um each, split at the midpoint where
the two sinks are under 80 um apart; where the types do not separate (m2, m21, m8, m3, m5) the MML is the average DS sink
and the OML sits the median DS1-DS2 distance beyond it (53 um upper, 57 um lower). Same events, same tests, same pages.
Exploratory: one number per mouse, generous tests, no correction.

How changes are marked
  Yellow heading     the panel was redrawn with the tight layers and says the same thing
  Red heading        what the panel says changed
  Red "Results show" the page's one-sentence answer changed
  Every page that uses layers starts its text column with "What changed with the tight layers": old P -> new P.
  The cover has a "Tight layers" column (unchanged / redrawn / answer changed), highlighted the same way.

Jeremy_Menu_TightLayers_112726.pdf   the fourteen pages in one file

What changed, page by page
  2  Q1  unchanged (main DS sink and Root Canal fast power, no layers)
  3  Q2  redrawn: panel c's DS1-DS2 position now measured between the types' own sinks (um). DS1 sits nearer DS2 in IED+
         mice more clearly (upper P 0.029 -> 0.011); the lower blade now agrees (P 0.055 -> 0.027).
  4  Q3  ANSWER CHANGED: no layer sink follows % knockout (holds); the IED- mice still have the weakest MML sinks but no
         longer at P < 0.05 (upper 0.024 -> 0.060, lower 0.033 -> 0.100). New: lower OML, IED+ above IED- (P 0.29 -> 0.033).
  5  Q4  redrawn, every statement holds (lower MML fast-power center: PTEN P 0.031 -> 0.002). Unstated: upper MML center over
         all mice P 0.017 -> 0.14.
  6  Q4 supplement A   REDRAWN for the tight layers: all 16 recordings with their DS1 / DS2 profiles, the new spans and the
         first menu's spans, and each layer's center per mouse (first menu -> tight).
  7  Q4 supplement B   same windows; drawn from the tight data.
  8  Q5  ANSWER CHANGED: the IED- MML deficit clears P 0.05 only with no filter (0.038 upper, 0.042 lower); with no filter
         the fast-power center rises in three of four layers (not the upper MML).
  9  Q6  unchanged
  10 Q7  answer holds; two panels changed: the BTs' fast-power center is above their own DS only in the lower OML now, and
         above a control DS in the upper OML instead of the upper MML; new: lower OML, BTs and red events carry more current
         than their own DS (P 0.027, 0.024).
  11 Q7 supplement     drawn from the tight data; its statements hold.
  12 Q8  ANSWER CHANGED: the upper MML's BT-over-own-DS current clears P 0.05 on two of seven bands (was seven); the lower
         MML and deepest sink hold on all seven; the fast-power lead over a control DS now survives a 300 Hz ceiling.
  13, 14 every mouse, table and aggregate: unchanged (no layers)

pages/   each page as PDF and PNG (300 dpi)
tables/  the menu's tables, recomputed from the tight data (q3_q5 layer sinks and q4 reads use the tight contacts)
code/    jpages.py and jfollow.py with the JM_LAYERS=tight switch, jtight_supp.py (supplements), jt_package.py, the layer
         check's tight_layers.py / tight_layers.json, and the rest of the menu code

Rebuild (menu scratch folder): python tight_layers.py; JM_LAYERS=tight python j1_battery.py; JM_LAYERS=tight python j2_freq.py;
JM_LAYERS=tight python jpages.py cover q1 q2 q3 q4 q5 q6 q7 q8 every table; python jtight_supp.py; python jt_package.py;
then miniconda's python jt_package.py merge. Without JM_LAYERS the same scripts build the original menu, unchanged.
