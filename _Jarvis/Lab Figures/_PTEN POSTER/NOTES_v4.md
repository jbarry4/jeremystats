# PTEN poster v4 (2026-11-27): first full pass on Rain's in-progress deck

v4 is built from `PTEN poster -- UVM template_Rain_edits_in_progress.pptx`. That file is unchanged.

- **Deck:** `PTEN_poster_v4.pptx`. Also `PTEN_poster_v4.pdf` and `PTEN_poster_v4_preview.png`.
- **Figures:** `v4_assets/`. `ds_stats.txt` there lists every P value drawn.
- **Code:** `code/v4/`.
  - `fig_ds.py`: the dentate-spike panels, redrawn from the menus' per-mouse tables.
  - `crops.py`: panels cropped from the menus' vector PDFs, below their panel headings.
  - `fig_circuit.py` and `fig_headfixed.py`: the KCNT1 poster's dentate drawing and head-fixed mouse, adapted for PTEN.
  - `build_v4.py RAIN.pptx OUT.pptx`: builds the deck.

## Layout

- **Left column:** Introduction, Methods and Isolating biomarkers.
- **Middle column:** Behavior, then Theta CSD and chemogenetic silencing.
- **Right column:** IEDs and dentate spikes, then Discussion, Funding and References.

Rain's comment was that panel titles "are for us". So every panel now has a letter, each section ends in one figure legend, and the menu headings are cropped off.

The header is tighter: smaller logos, a 54 pt title and the three affiliations on one line. That gives every column 1.8 in more. The type is now Aptos, as on the KCNT1 poster.

## Rain's comments, one by one

Rain's story order for the DS section was followed, A to K.

| Comment | What v4 does |
|---|---|
| JM-1 A & B: too much space; drop the titles | Redrawn as A and B: sink and fast power for a standard sink, each by IED status, knockout level and % KO. Shared axes, no titles. The P values match the menu: IED− sink P 0.03, and fast power IED+ against control P 0.002. |
| JM-1 C: combine with A and B | C sits in the next row. |
| Follow-up 3 A: only the top fast-power windows and the ±3 ms sink; shrink | Redrawn as D with only those two rows. The DS trace is a schematic, because m13's mean DS is not in the tables. |
| "Fast power clearly higher than baseline in the same animal" (story list) | E: follow-up 3 b, the 240–420 Hz power over each mouse's own baseline through the DS. |
| JM-4 A: remove the stuff above the graphs | F: the four spectra, with the heading and the yellow bars cropped off. |
| JM-4 D: too much space | Redrawn as G: LFP fast gain per layer. |
| Summary b (classes): put m7 with IED− | See "Not done yet". The border figure (Isolating biomarkers A) pools every mouse, so m7 is no longer shown on its own. |
| JM-6 A–C: tighten A; keep B or C? | A is redrawn as H: rates per mouse, with the m7 bar in the IED− group. **ROC kept, logistic fit dropped** (I). Rain was right to doubt "AUC 1.00": it is in sample, on 9 mice. v4 shows it beside the held-out models (AUC 0.90, which miss m3) and % KO (0.90, which misses m7). |
| JM-7 A: stats for IED+ DS against WT DS? | J is the supplement panel that draws them. Fast power: **yes, P 1.9e-05**. MML current: **no** (upper P 0.26, lower P 0.36). |
| JM-7 C and D: IED+ DS against WT DS in any graph? | K redraws 7 D with that comparison added. See the table below. 7 C (the centre of the fast power) is left out for space; its tests are below. |
| BM-2: tighten; Visible/Hidden dividers; drop rewards per entrance and target speed | A and B: runs plus rewards and time in goal only, under "Goal visible (cued)" and "Goal hidden", split by a divider. |
| BM-1, BM-4, BM-8, BM-13: simplify titles | Cropped below their headings: C–G, J and L. |
| BM-4: hidden or visible in B? | **Visible (cued) phase 8.** B is the share of the first 10 *directed runs* of that session (approaches launched at least 20 cm out) to the old place, minus the share to a never-used zone. That is also what "first 10 runs" in A means. |
| BM-11: remove the ".030" and ".002" under "Goal hidden" | Gone: H and I start below those P values. The poster names the panels "Goal hidden" and "Goal cued". |
| BM-8: y-axis title hidden by data | Not fixed: it is in the report's own figure (J). It needs the report's source figure. |
| BM-15 D & E: hidden or visible, which session? | **Hidden goal, phase 10** (the last rotation): time in the previous goal zone as % of the session, and rewards per entry. |

### IED+ DS against control (WT) DS, layer by layer

These come from the tight-layer 2 kHz reads, with generous tests and no correction.

| Layer | Fast gain, 250–500 Hz (K) | Centre of the added fast power (7 C) |
|---|---|---|
| Upper MML | P 0.43 | P 0.48 |
| Upper OML | P 0.27 | **P 0.03** (256 against 221 Hz) |
| Lower MML | **P 0.02** | **P 0.004** (280 against 227 Hz) |
| Lower OML | P 0.12 | **P 0.002** (285 against 230 Hz) |

So IED+ DS are not stronger in the dendritic layers' fast gain, except in the lower MML. Their added fast power sits higher in frequency in three of the four layers. On the Root Canal number (240–420 Hz, best contact) they carry more fast power, P 1.9e-05.

## Sources used

- **Theta CSD:**
  - The rasters come from `Opening4paperAndPoster.pdf` (panel D).
  - The layer profiles, the ROC, the DREADD effect and the IED CSD with CNO come from the PTEN behavioral menu, pages 20, 22, 23 and 25.
- **Behavior:** the PTEN behavioral menu, pages 3, 4, 6, 10, 13 and 17. These are the report's figures, cropped.
- **Dentate spikes:** the Jeremy menu (tight layers) and its follow-up, plus the DS story menu.
  - Redrawn from their tables: A, B, D, G, H, I and K.
  - Cropped: C, E, F and J.
- **Methods and biomarkers:**
  - The PTEN pathway, the pipeline strip and the funding logos come from v3.
  - The task, the histology and the IED example come from the opening figure.
  - The dentate drawing and the head-fixed mouse come from the KCNT1 poster. Here the knockout cells are magenta, the inputs are labelled DS1 and DS2, there is no fiber, and the KCNT1 firing claims are gone.

## Not done yet

- **m7 inside the IED− cloud:** this needs the Root Canal event table (`rc_events.pkl`). It is not on this PC.
- **BM-8's hidden y-axis title:** this needs the report's source figure.
- **Crop legibility:** the report's crops (behavior, theta) keep their own small type. Redrawing them needs the report's data.
- **Text to check:**
  - the methods for CNO: dose and timing are still missing;
  - the references, carried over from v3;
  - the Discussion wording.
