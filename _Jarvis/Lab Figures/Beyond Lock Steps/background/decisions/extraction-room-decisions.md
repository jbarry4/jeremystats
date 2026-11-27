# extraction-room-decisions

_The Extraction Room (Dentist step 6, web/extraction.html) — what the user asked for, the label misread, and where the first results landed (2026-11-10)_

The Extraction Room is The Dentist's sixth and last step: a standalone page like the Monolith (`the-dentist-bundle` (a note not copied here), [xray-many-decisions](xray-many-decisions.md)). Dentate Spike tab, five sub-tabs: Recordings / Round I / Separation rate / Round II / The numbers.

- "Toggle the label" meant **separable vs not separable** (prefs `extraction_sep`), NOT a DS1/DS2 swap. The swap (`extraction_flip`) was built by mistake and kept; the user hasn't said to remove it.
- %KO comes from the lab's "JB % hits" sheet (KO_SHEET in backend/extraction.py); controls are 0%; Low KO is under 10% by default.
- Unit of analysis is the recording (one per mouse), never events.
- Round II (user: "find something straightforward that is significant") reports BH q across all 11 measures and says p-only hits as "leads", never as findings.
- 2026-11-10, v1 (Verified DS 5%, 18 recordings): the best lead was "share that look like control DS" (Spearman vs %KO ρ −0.62, p 0.006, q 0.066; PTEN vs CTL MWU p 0.010, q 0.11). Separation rate was n.s.: CTL 6/8 vs PTEN 4/9, Fisher p 0.33, trend p 0.32.

- 2026-11-11: the user asked for "more common and forgiving" tests for low n. The default is now **"the usual ones"**: Shapiro–Wilk on the pooled residuals picks Welch or Mann–Whitney, ANOVA+Tukey or KW+Dunn (Holm); Boschloo for rates; no q gate (q is still shown). **"Strict"** keeps the old set. Cards are washed by state: green separable, red not, amber too few, gray left out.
- With the user's 7 calls (11-11): separation is CTL 6/8 vs PTEN 5/9 (Boschloo p 0.48). PTEN would need 1/9 to reach p<0.05, so the gap is the data, not the test. Under the usual tests, the 3-group KW/ANOVA comes out p<0.05 for 4 Round II measures (ds_like, both HF powers, P-spike share), mostly High vs Low KO; nothing holds at q (all 0.11).

- 2026-11-11 (2026.11.11.2): each X-ray Many folder is its own **set** (5% = room v1, 10% = v2). Separable calls and swaps are keyed `room|folder|gid`. A legacy `room|gid` call belongs to the set that was newest when it was made. Not yet confirmed with the user; offer to share calls across sets.
- **Within PTEN alone there is no %KO trend** in "looks like control DS" (ρ −0.22, p 0.58). The ρ −0.62 vs %KO comes from CTL vs PTEN. Never call it dose-dependent.
- Report 1 for Jeremy (PI, has ADHD, reads little) is at (link on the work PC) built from scratchpad `report/pten-ds-report.html`. It opens with "JEREMY, READ THIS PART" and explains 5% vs 10% as the same mice at two strictness levels. Add later reports to the same page.

- 2026-11-11 (2026.11.11.3): **"Against %KO" is the dose, among PTEN alone.** The old Spearman with the controls at 0% read a PTEN-vs-CTL gap as "goes with %KO". The user saw ρ −0.75 / q 0.014 with m51, m6 and m59 left out (m6 and m59 are controls they had called not separable) and asked "how is this significant".
  - Dose results: nothing significant at either cut-off.
  - Ordered trend CTL → Low → High (Jonckheere–Terpstra): only "looks like control DS" falls, p 0.011 at 5% and 0.017 at 10%.
  - The %KO range has a gap from 5.2% to 18.9%. PTEN m11 (13.5%) has recordings in the registry and would fill it; I found no m10 recordings.

- **The split by hand (2026-11-11):**
  - Each card has a collapsible panel offering X-ray's 3 methods (pca / pca_gap / delta) and a draggable cut on x (the gap, or PC1).
  - The pref `extraction_split` is keyed per set: {method, cut}.
  - Per-event arrays are cached in `GUI_logs/.cache/extraction/<gid>__<bundle>_v<n>.npz`.
  - `_er_apply_splits` feeds the cards, stats and Round II.
  - Methods disagree a lot on some mice (m21: delta 11/58 vs PCA 26/43).

**Why:** the user wants a significant result, so the room has to stay honest about multiplicity rather than drift into p-hacking.
**How to apply:** if asked for more measures, add them to ROUND2 so the q covers them too. Ask before you drop the FDR or relabel a lead as a finding.
