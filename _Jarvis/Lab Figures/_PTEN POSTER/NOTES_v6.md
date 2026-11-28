# PTEN poster v6 and the JeremyDraft decks (2026-11-27)

## v6: what was done with the six comments on v5

v6 is `PTEN_poster_v6.pptx`, with a PDF and a preview PNG beside it. Its code is in `code/v6/`: run `build_v6.py RAIN.pptx OUT.pptx`. v5 is unchanged.

| Figure | Comment | v6 |
|---|---|---|
| Behavior A, B | "Bottom of A and B are cut off" | The figure is taller, so the bottom row of arenas and the "Phase" axis label show in full. The rewards and time-in-goal plots moved right, so their y-axis labels no longer run into the arenas. |
| Behavior K–L (stay, entries) | "cut them out" | Both panels are gone. The old M–N moved up and are now K–L, and the legend was changed to match. |
| DS A, B (right) | "PUT THEM BACK. Where is the 95% confidence area?" | The right-hand plots now have a least-squares line through the Pten KO mice with its 95% confidence band (t distribution, n − 2 df). The printed Spearman ρ and P values are unchanged. The legend says what the band is. |
| DS D (windows) | "can be polished up" | Redrawn: the labels sit off the dashed line, the rows are evenly spaced, the bars have rounded ends with light guide lines, and the labels read "baseline −170 to −130 ms", "event ±25 ms" and "±3 ms". |
| DS J (vs WT) | Jeremy will add graphs from the Jeremy menu | Not changed. |
| Theta heading | "No propagation and initiation phases for IEDs?" | Still open. Initiation and propagation phases need the PTEN IED event data, which is not on this PC. Panel D shows only where the average IED starts (GCL2 over MML2). |

One more fix, found while checking: in behavior J, the "1.2 s to earn it" note overlapped the panel titles. The titles now sit higher.

## JeremyDraft

- `PTEN_poster_JeremyDraft.pptx` is built from v6.
- `_KCNT1 POSTER/KCNT1_poster_JeremyDraft.pptx` is built from KCNT1 v11.

Each has a PDF and a preview next to it. The code is `code/v6/jeremy_draft.py`, with the placeholder wording for every box.

In both decks, every caption, legend, subheading and body paragraph now reads "WRITE NON-AI SLOP regarding [a vague recap of what it used to say]". Each box keeps its place, font, size, colour and paragraph breaks.

- **Kept as they were:** bold lead-in labels ("Hypothesis.", "1. Place memory.", "Mosaic knockout:"), and the behavior legend's colour key.
- **Not touched:** titles, authors, affiliations, section headings, references, grants, acknowledgments and the KCNT1 "Jeremy's new examples" note.
