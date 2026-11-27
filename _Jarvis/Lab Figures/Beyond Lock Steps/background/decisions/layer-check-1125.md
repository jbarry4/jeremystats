# layer-check-1125

_11-25 layer check: the Jeremy menu's MML/OML were anchored on the all-DS (mixed DS1+DS2) sink; tight rule = DS2 sink is MML, DS1 sink is OML, +-40 um, midpoint split; old-vs-tight report in Lab Figures/Layer_Check_112526; menu not updated yet._

On 2026-11-25 the user pointed out that the Jeremy menu's layers were flawed: v = 1 was the sink of the AVERAGE of all
DS, so "MML" was just the larger DS type's sink (one type is 85–95% of events), and the OML (v 1.3–2.0) was a multiple
of that blended distance. DS2's sink is in the MML and DS1's in the OML.

**The tight rule (the user's 8 answers):**
- Anchors per blade: MML on the DS2 sink, OML on the DS1 sink, from each type's own mean CSD at the DS peak.
- The battery's DS1/DS2 names are positional (DS1 = farther from the cell layer, checked and swapped), so "name by position" = trust the labels. In m22, m60, m34 the larger type is DS1, so their MML moved inward 27–55 µm onto the smaller DS2.
- Width ±2 contacts (±40 µm); anchors under 80 µm apart → split at the midpoint, no shared contacts.
- Types that don't separate (Q2 rule; m2, m21, m8, m3, m5) → MML = all-DS sink, OML = + median DS1–DS2 gap (53 µm upper, 57 lower).
- All DS read at both layers; same contacts on every filter band; rerun everything that references position (Q2 position, Q3, Q4, Q5, Q7, Q8).
- Output: standalone report, menu untouched ("dont update the menu... yet").

**Result:** 52 of 62 results keep their verdict, 6 lost, 4 new, 0 reversed; 40 of the 45 stated in words still agree.
- Lost: Q3 IED− weaker MML (both blades, P 0.024/0.033 → 0.06/0.10, direction kept); upper MML fast-power center (Q4 all-mice dose, Q7 BT vs own DS and vs control); Q7 lower MML center BT vs own DS.
- New: Q7 lower OML sink BT and IED class vs own DS; upper OML center BT vs control; Q2 lower-blade DS1–DS2 position.
- Upper-blade BT-over-DS MML current is borderline on the main band (P 0.052).

**Files:** scratch `menu/tight_layers.py` (→ tight_layers.json), `JM_LAYERS=tight` switch in j1_battery.py / j2_freq.py (→ *_tight.pkl; without it they make the original files), `layer_check.py`.

**How to apply:** if the user adopts the tight layers, rebuild the menu pages Q2–Q8 from the *_tight.pkl files and reword the lost claims. A suggested next check: rerun with only the three DS1-majority mice read the other way. Related: [jeremy-menu-1124](jeremy-menu-1124.md), [ds-pten-deep-round-1116](ds-pten-deep-round-1116.md), [story-menu-figure-rules](story-menu-figure-rules.md).
