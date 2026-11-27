# jeremy-menu-1124

_11-24 Jeremy menu: Jeremy's 8 DS questions, one page each ("Jeremy Asked" verbatim, then "Results show" conclusive), plus a Strict-workflow every-mouse appendix; where it lives, the choices made, what it found._

The Jeremy menu (2026-11-24) is in `_Jarvis/Lab Figures/Jeremy_Menu_112426`. The folder holds the PDF, pages, tables, code and a README.

**Page format the user asked for:**
- Each page starts with a kicker, then "Jeremy Asked: “<question word for word>”" in italics.
- Then "Results show: <one conclusive sentence>" in bold.
- Panels follow, each with a heading that states its finding.
- The cover is a table of # / Jeremy Asked / Results show / Page, plus a glossary of words and marks.

The scripts ran in the session scratchpad (jpages.py, j1_battery.py, j2_freq.py, m10_reads_all.py) and were copied to code/.

**Choices, from the user's answers:**
- Efficacy is strength (sink and rise) plus output per input (fast power at a standard sink, Theil–Sen within each mouse).
- Each DS type is timed at its own deepest contact. Timing DS1 at the main sink gave a false knockout effect.
- "Makes both" means separation index ≥ 0.45, with each type holding at least 5% of events and at least 5 events.
- MML and OML are steps along each blade's own DS axis: MML v 0.7–1.3, OML v 1.3–2.0.
- Frequencies come from 2 kHz X-ray reads of every mouse.
- The argmax "dominant fast frequency" is rejected because it sticks at 100 Hz. Use the fast-power center and the fast gain instead.
- Filters: every battery band, shown as a P grid plus key panels.
- Question 7 compares classes within the 5 IED+ mice (paired) and against control DS. It tests both the BTs and the red events against the same mice's DS.
- Appendix: the Root Canal Strict workflow. Undecided = both + neither. m7 is highlighted.

**Findings:**
- DS sink size does not follow % knockout; IED− mice have weaker MML sinks.
- Output per input rises with knockout.
- The DS's own dominant frequency (12–15 Hz) is flat. The fast-power center rises with knockout, most in the lower MML.
- Opening the filters changes none of the sink results. The fast-power results need the band to reach above 300 Hz.
- BTs carry more MML current than the same mice's DS. Red events lean the same way (P 0.06).
- Undecided events are mostly wider than the mouse's DS (half-width). m7's undecided events carry as little fast power as its own DS: its whole cloud sits low.

**Added 11-25:**
- Follow-up report `Lab Figures/Jeremy_Menu_Followup_112526` (6 pages): held-out calls (one mouse out, 14 models at the bar), DS/BT/IED counts per mouse and group, Story 1's fast-power windows (±25 ms vs −170 to −130 ms, 5 kHz, best contact), how layers were found, Q4's windows (±25 vs −100 to −50 ms; dominant frequency ±50 ms), classes and Q4 vs Q7.
- Menu supplements in CONCERN / RESOLVE format after Q4 (pages 6–7) and Q7 (page 11); the menu is now 14 pages and the cover's page column was renumbered.
- The menu's layer rule was then found flawed (anchored on the all-DS sink); see [layer-check-1125](layer-check-1125.md). The menu has NOT been rebuilt with the tight layers.

**Why:** follow-up questions from Jeremy are likely, and the format and these choices should carry over.

**How to apply:**
- Reuse the page format and the measures above.
- Check claims about red events and about undecided events against the data before writing them.
- Related: [ds-story-menu-1123](ds-story-menu-1123.md), [story-menu-figure-rules](story-menu-figure-rules.md), [ds-pten-m6-excluded-and-figure-rules](ds-pten-m6-excluded-and-figure-rules.md).
