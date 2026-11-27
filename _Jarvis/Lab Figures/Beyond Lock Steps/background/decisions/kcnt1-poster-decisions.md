# kcnt1-poster-decisions

_KCNT1 AES poster, first pass 2026-11-25: the lab's PTEN poster is the house template (48x36), three columns, 'failing dentate gate' title, Shahriar first author, DS-vs-IED left out, behavior = all 56 mice._

First pass at the KCNT1 poster, 2026-11-25, in `_Jarvis/Lab Figures/KCNT1 POSTER/` (KCNT1_poster_draft1.pptx/.pdf, draft1_assets/, code/, README.txt). The user's answers:

- **Template:** the lab's PTEN poster (`_Jarvis/Lab Figures/PTEN POSTER/PTEN poster -- UVM template v3.pptx`) is the house style for both AES posters: 48 x 36 in landscape, one slide, background EEF1EE, header and heading bands 154734, panel headings C99A00, FFD416 rounded tags for unsettled items, Calibri. Its logos are `ppt/media/image1-3.png` (lab, Neuroscience Graduate Program, UVM Larner).
- **Flow:** three columns — (1) Introduction + Methods, (2) Where discharges start + Seizure onset, (3) SST optogenetics + Behavior, then Conclusions / Acknowledgments / References.
- **Title:** "A Failing Dentate Gate: Hilar Inhibition Gives Way Before Seizures Spread in KCNT1 Gain-of-Function Mice". **Authors:** Shahriar first, Weston second to last, Jeremy last; Willie Tobin in the acknowledgments (`kcnt1-aa-story-menu-1123` (a note not copied here) era decision, 11-23).
- **Dentate spikes vs IEDs: left out** of this pass (curation unfinished; 5 of 18 awake recordings still carry only Prospector's pre-labels). The Jarvis pipeline strip was dropped with it.
- **Behavior: the WITH-outliers v2 figure** (all 56 mice), the user named the file. Not the 52-mouse version, not capped at July.
- **Opto:** Dylan's 2024 examples now (7 Hz CSD, SST autocorrelation), swap in Jeremy's when they arrive. The seizure panel is `Poster Resources/(Drive id on the work PC).pdf`, the user's updated version.
- **Future directions:** SST *and PV* optogenetic rescue. Not the RNA-editing virus.
- New analysis made for it: urethane IED rate by genotype from `KCNT1_urethane_sessions.csv` reviewed ("solid") counts — WT 5 mice (4 with none), Het 2, Hom 8; Hom vs WT Mann-Whitney P = 0.003.
- The poster says "IED", matching the PTEN poster, **not** "P-spike" ([ied-is-p-spike](ied-is-p-spike.md) is the app and story-menu rule); flagged to the user, unanswered.

**Why:** the poster goes to AES and a satellite meeting; printing files were due Monday 2026-11-30.
**How to apply:** next pass, edit `code/build_poster.js` and rebuild; shapes carry names so the lab can edit in PowerPoint. Related: `kcnt1-aa-story-menu-1123` (a note not copied here), [story-menu-figure-rules](story-menu-figure-rules.md).
