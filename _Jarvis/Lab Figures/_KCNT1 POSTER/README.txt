KCNT1 POSTER — first pass
=========================
Built 2026-11-25. Files here:

  KCNT1_poster_draft1.pptx   48 x 36 in landscape, one slide, editable in PowerPoint
  KCNT1_poster_draft1.pdf    the same poster, for reading and for the printer
  draft1_assets/             every image the poster places, at print size, plus sizes.json
  code/                      the scripts that cut the images and build the deck
  Poster Resources/          what you supplied (old posters, papers, behavior figure, seizure figure)
  Video/                     "Watching a seizure spread", a standalone video of mouse 459's seizure for the 2026
                             KCNT1 Family & Professional Conference: 1080p MP4, a thumbnail, every word on screen
                             with its time. _v2 (2026-11-27) is the one to show: 4:42, an original score and sound
                             effects, this poster's colours, the cells drawn into their layers, the whole seizure at a
                             glance before its steps, the loop as a map, the spread across the brain step by step.
                             _v1 (2026-11-26) is the silent 3:13 first cut. Made from Seahorse by
                             _Jarvis/app/tools/seahorse/film/render_film.py; the words are in film.js there, the
                             sound in soundtrack.py.

Layout: three columns, left to right.
  1  INTRODUCTION (what KCNT1 is, SST vs PV, the hilar SST circuit, the hypothesis) and METHODS
     (head-fixed laminar recording, how to read a CSD, optogenetics, the rotating arena).
  2  WHERE DISCHARGES START (A IED from the hilus, B a discharge is two dentate spikes, C urethane
     IED rate by genotype) and SEIZURE ONSET (D mouse 459).
  3  SST OPTOGENETICS (E) and BEHAVIOR (F), then CONCLUSIONS, ACKNOWLEDGMENTS, REFERENCES.

Template and style follow the lab's PTEN poster (PTEN POSTER/PTEN poster -- UVM template v3.pptx):
dark green 154734 header and heading bands, gold C99A00 panel headings, FFD416 tags for the things
still to settle, Calibri throughout. Every shape has a name, so the lab can select one in the
Selection pane (Home > Select > Selection Pane) and edit it.

Where each figure comes from
----------------------------
elife_fig4_C    Shore et al., eLife 2024, Fig. 4C (CC BY 4.0). SST and PV firing, Het vs WT.
hilar_circuit   NBH'25 poster, Fig. 1D (left half). Hilar SST circuit diagram.
headfixed       NBH'25 poster, Fig. 2A. Head-fixed recording with probe and fiber.
laminar         NBH'25 poster, Fig. 2B. H3 laminar recording.
csd_primer      NBH'25 poster, Figs. 2C-D. Control theta and the two dentate spike types.
histology       Dylan's 2024 poster, Fig. 6C. Hilus, SST (green) and NeuN (red), 20x.
arena           NBH'25 poster, Fig. 6A. The rotating arena.
ied_hilus       NBH'25 poster, Fig. 4A-D. One IED: CSD, probe track, pre-spike spectrum and units.
ied_two_ds      NBH'25 poster, Fig. 4E-F. A discharge of two dentate spikes; a large KCNT1 DS.
urethane        NEW, made here. Confirmed IEDs per minute in the 2022 urethane recordings, by
                genotype. Counts are the reviewed ("solid") IEDs in
                Barry Playground/KCNT1 Spreadsheets/GitHub__jeremystats__KCNT1_urethane_sessions.csv;
                genotypes from KCNt14Shahriar.xlsx. Mice: WT 5, Het 2 (m22's two sessions pooled),
                Hom 8. Hom vs WT, Mann-Whitney exact P = 0.003. Code: code/urethane_plot.py.
seizure         Poster Resources/KCNT1_m459_A_origin_v6_overlay.pdf, title line cropped off.
opto_csd        Dylan's 2024 poster, Fig. 9. CSD 5 s before and 5 s during 7 Hz light.
opto_autocorr   NBH'25 poster, Fig. 7. SST unit autocorrelation and spectrum per light frequency.
behavior        The v2 active-avoidance figure, all 56 mice (with outliers), re-rendered here with
                the shorter axis label "delta shocks per turn (vs. day 1)". Code:
                code/behavior_relabel.py, which runs
                Poster Resources/Behavior/poster_fig_v2.py unchanged except for those two labels.

Old panel letters (A, B, Ei, ...) inside the reused crops were painted out so they do not clash
with this poster's own letters; see ERASE in code/crops.py.

Still to settle
---------------
  - Funding line: nothing on the poster yet (gold tag in ACKNOWLEDGMENTS).
  - Optogenetics: panel E is the 2024 example. Jeremy's two newer examples were not in the folder
    on 11-25; swap them in when they arrive (gold tag on the card).
  - Dentate spikes vs IEDs: left out for now, as asked. If curation finishes in time it would sit
    under panel C.
  - Wording: this poster says "IED", as the PTEN poster does. Say the word if the posters should
    both say "P-spike" instead.
  - Authors and affiliations are a draft; Willie Tobin is in the acknowledgments as agreed on 11-23.

Rebuilding
----------
  python -I code/crops.py <scratch>/assets                # cut the panels out of the old posters
  python -I code/urethane_plot.py <scratch>/assets/urethane_ied_rate.png
  python -I code/behavior_relabel.py <scratch>/assets/behavior
  python -I code/prep_assets.py <scratch>/assets <pten media dir> draft1_assets
  node code/build_poster.js "KCNT1_poster_draft1.pptx"

Later versions
--------------
  v2-v4  see v2_sanity_check/SOURCES.md
  v5     every figure redrawn in one style (code/v5/style.py) from its data; figures in v5_assets/,
         scripts and the numbers read back out of the old posters in code/v5/, notes in
         v2_sanity_check/SOURCES.md (v5 section)
  v6     v5 with the comments on it answered: the lab's cell colours and icons, the seizure stages on the
         real atlas section (Jarvis Seahorse), Hom f-I curves, the dentate circuit with PV cells, F and G
         as one grid, framed histology, a drawn arena. Figures in v6_assets/, scripts in code/v6/,
         notes in v2_sanity_check/SOURCES.md (v6 section)
  v7     v6 with its comments answered: the lab's own cells (PTEN opening figure) on every depth profile and
         in the dentate circuit, with SST and PV cells drawn to match; a 2 x 2 f-I matrix; a drawn
         micromanipulator; both blades in the laminar recording; CSD + voltage and voltage over the
         spectrograms; a sharper IED; figure E lined up with its clock, crisp atlas sections; the light's
         pulses in F; a shorter header, Aptos type, green panel headings with gold badges, and funding as on
         the PTEN poster. Figures in v7_assets/, scripts in code/v7/, notes in v2_sanity_check/SOURCES.md
         (v7 section)
  v8     v7 with its comments answered (smoother atlas borders, a drawn probe, E's scales in their own column,
         a PV cell in E and an SST cell in F, artistic cell headers and bigger traces in the f-I matrix, less white
         space in A, a shorter intro) and laid out on one spacing grid: figures trimmed and placed at print size,
         every text box sized to its text as PowerPoint measures it (code/v8/tools/build_converged.ps1). Figures in
         v8_assets/, scripts in code/v8/, notes in v2_sanity_check/SOURCES.md (v8 section)
  v9     v8 with its comments answered: a sharper IED in the methods (chosen from all 688 in the recording, VACC scan),
         DS/IED header cards, PV basket cells at both granule layers in every depth column (one rule, after Seahorse),
         both blades the same size, E's bottom graph telling the story stage by stage, F's summaries tied to their rows,
         fewer granule cells in the circuit, no outlier rings in A. Figures in v9_assets/, scripts in code/v9/, notes in
         v2_sanity_check/SOURCES.md (v9 section)
  v10    v9 with its comments answered: hairline dividers between each card's figures, the DS and IED tints as backdrops
         behind their figures, six spectrograms, a larger events figure with a narrower text column, PV baskets that hug the
         granule cells (somata found in the lab's drawing), smoother highlights in E, F's summaries named by small copies of
         their rows instead of arrows, D level with C. Figures in v10_assets/, scripts in code/v10/, notes in
         v2_sanity_check/SOURCES.md (v10 section)
