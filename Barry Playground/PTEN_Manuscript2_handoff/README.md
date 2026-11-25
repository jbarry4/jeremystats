# Pten KO somatic mosaicism, manuscript 2 — analysis handoff

Context package for an AI agent picking this project up cold. Everything here was used to
produce **report v3** (`report/Pten_KO_mosaicism_report_v3.pdf`, 89 pages, 25 main figures +
15 supplementary) and the two summaries. Written 25 November 2026.

Read this file first, then `report/abridged_betterSummary.md` (8 pages — the argument), then the
full report only as needed.

---

## 1. The study

Mice carry a mosaic *Pten* knockout in dentate gyrus granule cells, produced by retroviral Cre.
The fraction of KO cells varies between animals, and the question is what that fraction does to
spatial behaviour, to dentate physiology (theta CSD), and to interictal discharges (IEDs).

**Groups** (this is the spine of every analysis):

| Group | Code | n | Definition |
|---|---|---|---|
| Wild type | `CTL` | 19 | no KO cells; plotted at 0% KO |
| Pten KO Lo | `Lo` | 5 | < 15% KO cells |
| Pten KO Hi | `Hi` | 6 | ≥ 15% KO cells |

Mouse-level rules that are easy to get wrong:

- **M27 and M31 are UNK** — no histology, so no % KO. They appear in some plots as a separate
  category and are excluded from group comparisons.
- **M26 (WT)** had a post-surgical problem: excluded from all ephys (CSD, IED), **kept in
  behaviour**. Set in `code/config.py` as `EPHYS_EXCLUDE`.
- **M6 (WT)** took 27 sessions to criterion and is **excluded from the criterion analysis only**
  (an outlier by a wide margin; the exclusion is stated in the Figure 1 caption). A sensitivity
  copy of the criterion figures without that exclusion is in `work/backup_noM6` on the analysis
  machine, not shipped here.
- **DKO (Pten;Raptor double knockout)** mice exist in the patch data but are **ignored in
  behaviour** and not reported in v3.
- **M59** has two baseline CSD sessions; `s4` is the one used (`M59_BASELINE` in config).

## 2. The task

Mice forage in a circular arena for food delivered at an unmarked goal zone. A reward is earned
only by **staying in the zone for 1.2 s** — this single rule is what nearly every arrival measure
is derived from (time in goal per visit, rewards per entrance, slowing ratio, the green/red dots
in Figure 8). If you do not internalise the 1.2 s rule, half the measures will look arbitrary.

**Training**: mice learn a cue rule to criterion; *sessions to criterion* is the learning measure.

**Probes**, phases 7 to 10, each run in two conditions:

- **Visible / cued** — a beacon marks the goal. This is the **control condition** and most of the
  strong claims in the report are *within-animal changes on removing the cue*, not raw group
  differences in the hidden sessions. Read the hidden results alone and they look much weaker
  than the report says; the cued comparison does the work.
- **Hidden** — no beacon; the mouse must remember the place.

Phase 7 is the **trained** goal location. Phases 8, 9, 10 rotate the goal to new locations, so by
phase 10 there are three *former* goals to rule out. Zone *k* was the goal of phase *k + 6*.

## 3. The findings, in one page

**Two phenotypes, not a dose-response.** Sessions to criterion: WT 8.8 ± 0.5 (n = 18, range 7–13),
Lo 21.2 ± 2.1 (n = 5, range 15–28, no overlap with WT, p < 0.001), Hi 14.0 ± 2.8 (n = 6, range
8–25, median 11.5, p = 0.029). **Lo mice — fewer KO cells — are the slowest learners.** The
criterion-against-%KO plot is an inverted U, and Figure 1b is a quadratic *describing that shape*,
not a dose model: the mice fall in two clusters with a gap. This is the single most
counter-intuitive thing in the report and the thing readers most often misread.

**Lo: a failure of where to go. Hi: a failure to stop when you get there.**

- Latent place preference, visible phase 8: WT +9.2 (p = 0.007), Lo +12.0 (p = 0.016),
  Hi −4.2 (p = 0.578).
- Hidden phase 10 rewards: WT 15.21 vs Hi 5.50 (p = 0.004). Cued phase 10: 30.68 vs 29.67
  (p = 1.000). The deficit is specific to the hidden goal.
- Speed through the reward window, all entries, hidden phase 10: Hi 16.4 vs WT 11.5 cm/s
  (p = 0.0005). Phase 7 p = 0.18, cued p = 0.18.
- Pause time per session, hidden phase 10: WT 134.1, Lo 137.5, Hi 59.0 s (p = 0.006). Change on
  removing the cue: WT +30.3 (p = 0.024), Hi −33.8; Hi vs WT on the change p = 0.043.
- Pause time at former goals across phases (the "set to rule out"): slopes +25.3 (WT), +28.8 (Lo),
  +9.6 (Hi), p = 0.003 hidden; p = 0.198 cued.
- Braking: directed runs containing any slowdown 56.2 / 51.3 / 38.4% (p = 0.045); braking distance
  11.5 / 13.2 / 13.7 cm (p = 0.050); change on removing the cue Hi vs WT p = 0.021. Braking at
  *former* goals is identical in all three groups (p = 0.93) — Hi mice do slow at old places.

**The approach itself is normal.** Figure 12 (the speed-against-distance profile) and
Supplementary Figure S15. Max-statistic permutation over the whole profile, Hi vs WT:
p = 0.83 cue removed, p = 0.22 cue present; within-animal hidden-minus-cued p = 0.57. The groups
trace the same hook. The deficit is at arrival, not on approach.

**The DREADD works.** CNO drops firing in hM4D-expressing Pten KO granule neurons from 5.70 to
1.44 spikes per sweep at matched injected current (−75%, n = 5). See §7 for why the p value needs
care.

## 4. Folder map

```
report/
  report_v3.md                 source of the full report; builds with pandoc (see §5)
  abridged_betterSummary.md    8 pages, structured around claims 1 / 2a / 2b / 3 — read this first
  summary_v3.md                12-page summary
  build_v3.py                  assembles report_v3.md from report_v2.md — STALE, see §8
  figsv3/  figsv/              the figures the markdown references, SVG + PDF, text as outlines
  *.docx *.pdf                 built documents
  Pten_KO_analysis_methods.docx  full methods, built by code/tools/build_methods.js
  Pten_KO_data_by_analysis.xlsx  per-analysis data workbook
code/
  config.py                    ALL paths live here — edit this first
  inputs/                      SPSS .sav, Data4Claude.xlsx, ied/, patch/ (small raw inputs)
  path_analysis/               s00–s25, the trajectory pipeline, run in numeric order
  group_analysis/              group-level figures and statistics
  summary_figs/                the summary's own figures (nf1, nf2, nf4) + ex_core.py
  patch/                       whole-cell analysis from raw AxoGraph files
  tools/                       vector_export/, build_methods.js, export_workbook.py, compose_stack.py
  README.md                    package-level notes, including the vector export invocation
data/derived/                  pickles and CSVs so figures redraw without re-reading the raw .dat
  approach/                    runs_ex.pkl, segs.pkl, braking_*.csv, approach_profiles.csv, …
  patch/  phase8/              per-sweep patch data, phase 8 per-mouse table
```

## 5. Reproducing things

Paths are all in `code/config.py`. Set `DATA_ROOT` to the AllBehavior folder and `PATCH_RAW` to
the raw recordings folder (§6), then:

```bash
# a single figure
cd code && python path_analysis/s25_approach_profile.py

# the same figure as publication vectors (SVG/PDF/600dpi PNG)
cd code && PYTHONPATH=tools/vector_export VEC_OUT=/path/to/out VEC_TEXT=path \
  INTER_TTF_DIR=/path/to/Inter-ttf python path_analysis/s25_approach_profile.py

# the documents
cd report && pandoc report_v3.md -o out.docx --resource-path=.:figsv3
soffice --headless --convert-to pdf out.docx     # the PDF is built FROM the docx, not by latex
```

`VEC_TEXT=path` outlines the text (what the report embeds); omit it for editable-text SVGs.
Building the PDF with xelatex instead of LibreOffice gives 80 pages instead of 89 and loses
layout — use the docx route.

The trajectory pipeline (`path_analysis/s00` onward) reads the raw `.dat` files and takes a while;
`data/derived/` exists so you can skip it. `s25_approach_profile.py` caches to
`approach_profiles.csv` and will reuse it if present — delete that file to force a recompute.

## 6. Raw data NOT in this folder

Two raw sets were deliberately left out, because they are large and already live elsewhere on this
machine. This folder is inside a GitHub tree and 400 MB of binary tracking data does not belong in
a repo.

- **Behavioural tracking**, 417 MB of Bio-Signal Tracker `.dat` files:
  `~/Documents/UVM/projects/PTEN/AllBehavior`
- **Whole-cell recordings**, AxoGraph `.axgd`:
  `~/Documents/UVM/projects/PTEN/Manuscript2_Data/ClaudeOutput/raw recordings`
  and `.../ClaudeOutput/HM4D_patch_data`

The small raw inputs (SPSS files, the CSD and CNO spreadsheets, the IED pipeline outputs, the
patch metadata) **are** included, under `code/inputs/`.

## 7. Traps — read before changing anything

**The arena is y-down.** The tracker stores y running down the image. Plotting it straight into a
y-up matplotlib axis mirrors every arena vertically and reverses the handedness of every curved
run. The fix is to negate y; **no rotation is needed**. In the room view that this produces, the
phase 7 goal sits at 39–46° (upper right quadrant) and phases 8 to 10 rotate **anti-clockwise** in
every mouse. Some older figures (the v2 Figures 7 and 11–14) were already correct because they used
an inverted y-axis; do not "fix" those twice.

**The patch per-cell metadata was wrong and has been superseded.** An earlier table was recovered
from the vector coordinates of the lab's summary figure. Within each measure its values are
correct and reproduce the published means, but **the rows are not aligned across measures** —
each panel's points were matched to labels independently, so a row could pair one neuron's spike
count with another neuron's threshold. Group statistics within a measure are unaffected; anything
pairing measures within a cell was wrong. The table built from the raw recordings supersedes it.
Cell identities, recovered by fingerprinting all four published measures:

```
KO01 080326N005AA 003 -> 005      KO04 080326N008AA 005 -> 007
KO02 080326N002AA 005 -> 007      KO05 080326N009AA 005 -> 007
KO03 080326N001AA 006 -> 008  (the weak responder, 3.45 -> 2.45 over 17 min; NOT a non-responder)
```

**The patch firing-rate p value cannot be improved by analysis.** Paired t over the five neurons
is p = 0.051. With n = 5 the exact within-neuron sign-flip permutation has 32 arrangements, so the
smallest attainable p is 0.063 even if every neuron fell; with one weak responder it is 0.125,
which is also what Wilcoxon gives. A linear mixed model of spikes on drug and current returns the
same −4.26 spikes/sweep with a Wald p of 0.002, **but that treats the 100 matched sweeps as the
replication unit and sits below the permutation floor — the signature of pseudo-replication.**
Referred to the 4 df that five neurons provide it is p = 0.037, which is what Figure 22b reports.
The honest summary is the effect and its interval: −4.23 spikes/sweep, 95% CI −6.91 to −1.61
(bootstrap over neurons). Do not reinstate the 0.002.

**Figure numbering changed on 25 Nov 2026.** Figure 12 (the approach profile) was inserted, so
everything from the old Figure 12 up shifted by one: braking is now 13, the patch figure 22, the
report ends at 25, and the new all-phases profile is Supplementary Figure S15. `build_v3.py`
pre-dates that edit and would regenerate the *old* numbering — see §8.

**Group × phase interactions are per-mouse slopes, not ANOVA.** House style throughout: fit a
least-squares slope across phases 7–10 for each mouse, then compare slopes between groups with a
two-sided Mann-Whitney. Anyone looking for an interaction term will not find one.

## 8. State of the build

`report/report_v3.md` has been **hand-edited since `build_v3.py` last ran** — the Figure 12
insertion, the renumbering, and a corrected Figure 22 caption. Re-running `build_v3.py` would
regenerate report_v3.md from report_v2.md and **silently discard those edits**. Treat
`report_v3.md` as the source of truth and `build_v3.py` as history.

## 9. House conventions — follow these

Statistics:
- Between groups: **two-sided Mann-Whitney**. Within a group: **paired t**.
- **Never do batch or cohort analysis.** This has been asked for explicitly and repeatedly.
- The mouse is the unit of replication. Per-mouse value first (median or mean over its runs or
  entries), then the group statistic over mice.
- Report effect sizes and intervals where n is small; do not reach for a test that borrows power
  from pseudo-replication.

Colours and markers:
- WT `#2a78d6`, Lo `#008300`, Hi `#e34948`, pooled KO `#7a4fa0`.
- Colour = group. **Diamond = IED+, circle = IED− or not recorded.**
- `jet` is reserved for the voltage raster and the IED CSD. `viridis` for speed.
- Figure background `#fcfcfb`, ink `#0b0b0b`, muted `#52514e`, grid `#e4e3de`, font Inter.

Plotting:
- Arena plots: room view, phase 7 goal upper right, phases 8–10 anti-clockwise (§7).
- For any pause analysis, **state whether the pause is at the current goal, a former goal, or
  anywhere off the wall.** A pause measure without that distinction is not interpretable here.

Working with the PI:
- If data for something is missing, **say so**. Do not substitute a near-neighbour file or infer a
  number. Verbatim: *"If I do that again, please just say you don't have the data. This will avoid
  confusing scenarios where data doesn't match."*
- **Never use files found in the user's folders that were not given for the task.**

## 10. Open threads

- **Within-run variability of the approach shape** is untested and looks promising. Because each
  run is scaled to its own maximum, the group mean can only reach 100% if every run peaks at the
  same distance, so the peak height in Figure 12 is a measure of how *stereotyped* the approaches
  are, not how fast the mouse runs. Cued peaks at 89%, hidden at 85%. The permutation test
  compared group *means* and says nothing about dispersion; comparing the spread of run shapes
  within each mouse would be a new test with a clear prediction (hidden > cued in every group).
  Before reading anything into the bumps in a profile, split each mouse's runs randomly in half and
  redraw: real structure reproduces in both halves, sampling noise moves.
- **No WT no-drug time control in the patch figure.** The uninfected wild-type control and the
  Pten;Raptor dKO group are not shown in the KO-only version, and the control group's raw
  recordings were not available, so rundown over the comparison interval is not controlled within
  that figure. Published values exist and could be added back as a panel.
- A **figure archive** (timestamped copies of every figure, so a dropped figure stays recoverable)
  was proposed and not yet set up. One figure has already been lost and rebuilt this way.
