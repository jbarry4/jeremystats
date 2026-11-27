# ds3-trim-mixup-decisions

_2026-11-13: the user's 32 answers for DS3 (Tarcsay relative-sink score), the probability trim, the mix-up sanity check, and the room redesign (5x3 Compare grid, cards tidied)._

Asked 2026-11-13 from a pasted note on Tarcsay et al. 2025 (bioRxiv 10.1101/2025.10.27.684857). The user answered 32 questions.

**DS3 (hybrid)**
- Score = (OML_sink − MML_sink) / (OML_sink + MML_sink), each sink = max(0, −CSD) at ONE contact, mean over the same ±3 ms window. No neighbour averaging (it mixes OML and MML on a 50 µm probe).
- |score| ≤ 0.5 → DS3; > 0.5 DS1; < −0.5 DS2. The cut is a named parameter with a slider; the raw score is stored per event. Cite the paper in the UI.
- Not a third cluster, not distance from a line, not trimmed events. No "both sinks large" rule. No timing rule (the OML–MML lag is logged only).
- OML = where the split's DS1 class-mean sink is deepest; MML = where DS2's is, in the same blade.
- Floor: a matched null from baseline windows ≥30 ms from the DS, same measure, 99th percentile. Under it = "unscorable", counted apart, never DS3. Report unscorable per split class.
- A layer over any split, togglable. Green, "DS3 (hybrid)". Its own class everywhere (stats, Round I share, Blob Analysis).

**Probability trim**
- Two-Gaussian fit on each method's own axis; cut 80% with a slider.
- Unsure events are kept, grey, out of DS1/DS2 numbers.
- The split decides the class; the fit only trims.
- Kept per set, one switch. Trim even one-family cards. If a class would fall under the floor, refuse the trim on that card and say so.
- A probability strip with the cut-off on each Compare panel.
- **DS3 and the trim are used separately, not together, for now** ("We may combine them later").

**Mix-up (cross-contamination)** — "the 3rd method is a sanity check for the first and second".
- Shown three ways: as split, with DS3 out, with unsure trimmed. Same fit, remaining events. Bootstrap interval.
- 10–15% band as pass/fail (green / amber / red); one-family cards red with the reason. Every Compare panel. Shown only; not a Round I measure.

**Room redesign** ("Sleek and Chic"): cards as now but tidied; Compare splits = a 5×3 score grid with one panel open.

**Built 11-13** (`backend/dsmix.py`, pref `extraction_mode` per room|folder, `tools/check_dsmix.py`). Also a per-recording time window (`extraction_twin`, two knobs on the Compare timeline; the user asked mid-build).

**What the data showed (v8, 4,177 events):**
- DS3 at ±0.5 is driven by how far apart OML and MML land. Where they are 1–2 contacts apart (flagged "near"), 77–85% of events are DS3: m6, m22, m59, m8, m13. Where they are 3+ apart on clearly separable cards, DS3 is 0–3%: m60, m61, m28, m1, m33, m3.
- Unscorable is large with the 99th-percentile floor: 675 events (16%), up to 58% on m33.
- The trim drops little (168 events); most are m5 s2 (136). It is refused on cards with a tiny class.
- Mix-up: separable cards 0–9% (clean); one-family cards 27–49% (mixed).
- m60 s1's 11 distinct events all fall after minute 20: the first 20 minutes alone read one family.

Related: [compare-splits-fifteen](compare-splits-fifteen.md), `room-card-tools-1113` (a note not copied here), `toggles-are-named-states` (a note not copied here).

**DS3 round on the Halo set (11-13, user asked):** every card on the Bite line at the lowest point of its cost curve (the user's "minimum left side"; m6 moved to after 2, m21 from delta to Bite), DS3 on, Impression `eeea75890533` v2 "Bite minimum + DS3" (v1 nicknamed archived).
- PTEN vs CTL DS3 rate: NOT different (Mann–Whitney P 0.88; share P 0.59). The hypothesis "PTEN has more DS3" is not supported.
- Lead: among PTEN, DS3 share rises with %KO (Spearman ρ 0.88, P 0.002, n 9; LOO worst P 0.011). Fragile: 7 of 9 mice have 0–3 DS3 events; one of ~8 tests. Never call it a finding without saying so.
- Figure + caption: Desktop `DS3_figures_2026-11-13` (script `scratchpad/ds3_fig.py`, house Nature style from joepromptfigs).
- **Later the same day the lead was shown NOT robust.** 36 tests, BH q 0.051. Under the Bite line's default line, PCA, delta, or a split-free definition (blade quarter points) the %KO correlation is about 0 (v6 and v8); a mouse's DS3 count swings 0 → 300 with where OML/MML are placed. On the 50 µm H3 probe the OML/MML balance is not resolvable reliably. The user pushed for a "paradigm shift" finding; I told them there is none here. Do not present the ρ 0.88 as a result.
- Literature: Tarcsay et al. report DS1 0.09, DS2 0.18, DS3 0.10 Hz, DS3 sinks weaker, DS as a continuum. Here 9 of 18 recordings read one family (fits the continuum). Scripts: scratchpad `ds3_battery.py`, `ds3_sens.py`, `ds3_fixed.py`.
