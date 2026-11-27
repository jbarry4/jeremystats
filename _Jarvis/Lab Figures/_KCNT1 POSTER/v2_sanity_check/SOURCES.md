# KCNT1 poster v2: where everything comes from

Built 2026-11-25 from `KCNT1_poster_draft1.pptx` as saved at 20:31, the copy that carries Shahriar's six comments. v2 edits that file's XML in place. Anything not listed under "Changed" is exactly as it was in draft 1, and draft 1 itself is untouched.

- **Deck:** `KCNT1_poster_v2.pptx`, with `KCNT1_poster_v2.pdf` exported by PowerPoint.
- **Code:** `code/v2/`. `build_v2.py` makes the deck, `methods_fig.py` makes the new Methods figure, and `opto_crops.py` makes the two opto panels. `extract_*.py` and `*.sbatch` are the VACC jobs, and `candidates.py`, `pick*.py` are the event selection.
- **New images:** `v2_assets/`.

## Changed, comment by comment

| Comment (attached to) | What v2 does |
|---|---|
| "Move behavior as the main start after intro and methods" (BEHAVIOR heading) | Behavior moved to the top of column 2, beside the Intro, unchanged in content. "Where discharges start" sits under it. Seizure onset moved to the top of column 3 and was scaled to fit (figure 76% of draft-1 size). Panels re-lettered in reading order: A behavior, B–D discharges, E seizure, F–G opto. Captions that named a letter were updated ("old Hom in F" is now "in A"). The conclusions now run in the same order. |
| "Remove." and "Replace with new Jarvis figures, remove theta" (Methods CSD primer) | Primer (NBH'25 Figs 2C–D, with theta) removed. Replaced by a new figure: one curated dentate spike and one curated spike from KCNT1 m1609 s1, each shown as voltage, CSD and spectrograms. No theta. See "Methods figure" below. Panel C's caption pointed at the old primer ("(Methods)"); it now cites [5] (Bragin 1995). |
| "Remove" (the 7 Hz CSD in SST optogenetics) | Removed (Dylan 2024 Fig. 9). Its claim went with it: "at 7 Hz, dentate spikes fall into step and IEDs thin out" in the subheading, and "at 7 Hz IEDs thinned" in Conclusion 3. |
| "Add baseline, 5HZ, 7Hz, 12Hz figures as opto effects" (pasted screenshot) | New panel F, "Opto effects". Dylan's 2024 poster Fig. 7, panels A (Baseline), B (5Hz A), D (7Hz) and F (12Hz A), each showing raw LFP, spectrogram and one SST unit's spikes. Cut from `Poster Resources/FinalKcnt1_Dylan 1.pdf` at 400 dpi. Old letters and titles left out; new titles drawn on. |
| "Add figure 7 as opto entrainment" (pasted screenshot) | New panel G, "Opto entrainment". Dylan's 2024 Fig. 8 whole: burst-rhythmicity autocorrelation and spectrum per light frequency, plus the two summary curves (mean burst power, mean firing rate). This is NBH'25 Fig. 7 plus the summaries, as you chose. "Fig. 8" and the A)/B)/C) letters are painted out. |
| (follows from the above) | Panel F's caption is rewritten from Dylan's Fig. 7 legend (raw LFP, filtered spectrogram, one SST+ interneuron's spikes, light order rest-10-rest-10-5-7-12-5 Hz). Panel G's caption and Conclusion 4 come from his Fig. 8 legend: "Autocorrelation power peaks at 5Hz, and is weakest at 12Hz". |
| (housekeeping) | The two pasted screenshots and the six comments are not in v2; draft 1 keeps them. Unused images dropped from the package. |

## Every element of v2 and its source

| Element | Source |
|---|---|
| Header, logos, title, authors, affiliations | unchanged from draft 1 (see `README.txt`) |
| Introduction: SST/PV firing, hilar SST circuit, hypothesis | unchanged: Shore et al. eLife 2024 Fig. 4C (CC BY 4.0); NBH'25 poster Fig. 1D |
| Methods: head-fixed rig, H3 laminar recording | unchanged: NBH'25 Figs 2A, 2B |
| **Methods: dentate spike and spike (new)** | KCNT1 m1609 s1 (2026-07-15), raw CSCs on netfiles. Details below and in `methods_figure_events.csv` |
| Methods: histology, rotating arena | unchanged: Dylan 2024 poster Fig. 6C; NBH'25 Fig. 6A |
| A Behavior | unchanged: `Poster Resources/Behavior/KCNT1_AA_poster_figure_v2_with_outliers` (all 56 mice), as re-rendered for draft 1 |
| B, C Discharges | unchanged: NBH'25 Figs 4A–D, 4E–F |
| D Urethane IED rate | unchanged: made for draft 1 (`code/urethane_plot.py`) |
| E Seizure onset | unchanged: `Poster Resources/KCNT1_m459_A_origin_v6_overlay.pdf`, smaller |
| **F Opto effects (new)** | Dylan 2024 poster Fig. 7 A, B, D, F (`code/v2/opto_crops.py`) |
| **G Opto entrainment (new)** | Dylan 2024 poster Fig. 8 A, B, C (`code/v2/opto_crops.py`) |
| Conclusions | the draft-1 text, reordered. Conclusion 4 is rewritten as above |
| Acknowledgments, references | unchanged |

## Methods figure: how the events were found

**Events.** Both come from the same recording and from Jarvis's locked curation sets (see `methods_figure_events.csv`).

| Event | Jarvis set | Committed | Time (s) |
|---|---|---|---|
| Dentate spike | Braces-aligned DS set `br323decf9e4` (bank entry `4fad818d807e`, "Incisor CSC1–CSC64") | by Rain Younger, 2026-10-05 | 1716.6106 (Braces-aligned), row 1353, unflagged |
| Spike (IED) | Lock set `br5fa760a32b` (bank entry `aa1d581d5f7e`, pooled Incisor + Doppler) | by Isabella Piatek, 2026-11-24 | 1420.9295 (Lock stamp), row 666, unflagged, marked "keep" |

**Why m1609 s1 (YH het).** Of the 16 mice on the list, it is the only recording where both the spike set (Lock) and the dentate-spike set (Braces) are committed.
- m1603 s2 (Hom) has a committed Lock set (146 spikes) but no curated dentate spikes.
- m1606 s1 has StrataScope layers and a committed DS set, but its Lock set is not committed yet.

**Depth labels.** m1609 has no StrataScope layers. The figure marks depth with channel numbers and with the recording's own mean dentate spike (30 Braces DS): upper-blade sink Ch 34, source Ch 40, lower-blade sink Ch 56. This is the DS story menu's convention.

**Reading the data (Jarvis plus VACC).**
- This PC cannot reach netfiles (port 445 closed off campus), and VACC login nodes cannot read `/netfiles` (the Kerberos ticket expired 10/15). VACC compute nodes can, per the lab's `netfiles_check` job.
- Two read-only Slurm jobs ran on the `short` partition under sakhava1, using the Jarvis key:
  - **6723520**: m1606 s1 and m306 s1, a first pass from the curated pooled and DS sets.
  - **6723646**: m1609 s1 and m1603 s2, from the committed Lock spikes and Braces dentate spikes.
- Each job read ±1 s of all 64 CSCs around each candidate, plus 20 random baseline windows, with Jarvis's own reader. That is `backend/nlx.py` (sha1 `c1dc90b00363`): times in seconds from the first record's timestamp, invert=True, downsampled 30 kHz to 2.5 kHz with resample_poly 1/12, the same as the Rain figure.
- Outputs are in `/gpfs2/scratch/sakhava1/_claude_poster_112526/`. That is scratch and may be purged; the sbatch files in `code/v2/` rebuild it.
- Also read on VACC, read-only: the cached Incisor and Doppler results in `Jarvis Data/_answers`, used for the first-pass candidate lists.

**Choosing among 30 candidates of each kind.** Candidates were unflagged rows, at least 0.4 s from any other event. Each was scored on:
- how well its CSD in the ±30 ms window matched the set's mean;
- for dentate spikes, how close its size was to the median;
- a quiet baseline before and after.

The best six of each are in `candidate_sheets/` (top: m1609 DS, middle: m1609 Lock spikes, bottom: m1603 Lock spikes). The chosen DS ranked 6th (CSD correlation 0.90); the chosen spike ranked 2nd (0.91).

**Processing.** This follows `_Jarvis/Rain Figures/make_rain_figure.py`, without its theta panel.
- Dentate spike: 5–100 Hz plus a 60 Hz notch.
- Spike: 60 Hz notch only, with the −150 to −60 ms median removed.
- CSD: −d²V/dz² over the even contacts, which are 40 µm apart on the H3 (20 µm pitch). End contacts duplicated; dead CSC59 is odd-numbered so not used.
- Spectrograms: complex Morlet, 3 cycles at 2 Hz rising to 10 at 800 Hz. Power is in dB relative to the median of 20 random 2-s windows of the same recording. The Rain figure instead used the median of a ±4 s read around the event.

## Worth checking in the refine pass

- m1609 is a Het. If the Methods example should come from a Hom, the committed alternative is m1603 s2 (Lock spikes only), with no curated dentate spikes in that recording.
- The seizure figure's header reads "64-ch linear probe (50 µm)". The Rain figure and DS menu notes say H3 contacts are 20 µm apart.
- Panels F–G are 2024 examples. The "Jeremy's new examples to add" tag is still on the card.
- Column 2 ends about 1.8 in above the others, and the seizure figure shrank to fit column 3. Both are layout details for the refine pass.

## Files in this folder

- `methods_figure_events.csv`: the two events with every identifier (set, entry, commit, row, time before and after alignment, scores).
- `candidates.json`, `candidates_lock.json`: the candidate lists sent to VACC.
- `picks.json`, `picks_lock.json`: their scores.
- `candidate_sheets/`: what the candidates looked like.
- `KCNT1_poster_v2_preview.png`: a PowerPoint render of v2.

---

# v3 (2026-11-25, from v2 as saved at 21:39 with two new comments)

`KCNT1_poster_v3.pptx` / `.pdf`, built by `code/v2/build_v3.py`. v2 is untouched and keeps its comments.

## Comment 1: "There's way better IEDs out there… spans the entire recording depth and ~1st percentile spectrogram activity at the center"

The v2 spike (m1609, 1420.93 s) was only at the 56th percentile for power at its center, and it spanned 69% of the depth. You were right.

**The scan.** VACC job 6725032 (`scan_lock.py`, `short` partition, read-only) scored every unflagged spike in every committed KCNT1 Lock set: m1609 s1 (688), m576 s1 (485), m1603 s2 (131) and m1619 s1 (163). m531 s1 was skipped because its netfiles folder wasn't found. Per spike it measured:
- **span**: the share of even contacts whose peak in ±15 ms reaches 30% of the largest contact's;
- **center power**: 30–500 Hz power in ±10 ms, in dB over the recording's own baseline (20 random 2-s windows), and its percentile within the set.

All scores are in `lock_scan_metrics.json`; the shortlist is drawn in `candidate_sheets/v3_ied_shortlist.png`.

**Chosen: m1609 s1, 959.3214 s, Lock row 424** (origin both, unflagged; set `br5fa760a32b`, committed by Isabella 11/24).
- It has the most center power of all 688 spikes in that recording: 13.9 dB, the 99.85th percentile.
- It is a single 3.4 mV spike whose CSD runs from the upper blade through the lower blade.
- It comes from the same recording as the dentate spike, so the depth marks still apply.
- Its span score is 0.63, because CA1 deflects less than the dentate gyrus does. Spikes with span ≥ 0.9 top out at the 95th percentile for center power and look less clean.

**Runners-up:** m1603 s2 at 925.33 s (Hom, 99th percentile, span 0.78) and m1609 at 1366.72 s (99th percentile). Either can be swapped in.

## Comment 2: white space around "Where discharges start" and Acknowledgments; overall harmony

All three columns now end at the same line, with 0.4 in gaps.
- **Column 2:** Behavior, then "Where discharges start" with its panels re-laid tighter, then Acknowledgments and References side by side, with larger text and cards fitted to it.
- **Column 3:** Seizure onset back at full width (it was at 76%), then SST optogenetics, then Conclusions in larger text (19 pt).
- **Methods:** the bottom row moved 0.3 in to clear the longer caption.

---

# v4 (2026-11-25): "IED sucks try again"

`KCNT1_poster_v4.pptx` / `.pdf` is v3 with only the Methods IED and its caption changed (`code/v2/build_v4.py`, `methods_fig_v4.py`).

**New IED: m1609 s1, 882.748 s.** It comes from the committed Lock set `br5fa760a32b` (unflagged), the same recording as the dentate spike.
- It is 2.7 mV and reaches 91% of the even contacts, from CA1 to the lower blade.
- Its 100–600 Hz power is +12 dB over baseline in ±30 ms around the spike, and below baseline from 100 to 450 ms after it. So the high-frequency burst sits at the center, not in an after-discharge.

**How it was found.**
- VACC job 6726077 read ±1 s around the 18 highest-scoring Lock spikes (score: CA1 size + overall size + center power).
- Every saved candidate was then scored for center power against the time before and after, and for isolation. Sheets are in `candidate_sheets/v4_*`.
- Rejected: 959.32 s (v3; power fine, but the CSD stopped at CA1), 692.17 s (neighbouring discharges at ±200 ms) and 1340.74 s (broadband power stayed high for 400 ms after the spike on every contact, CA1 included, which looks like an after-discharge or noise burst).

**Display.** It follows your notes ("make it POP", and use the Jarvis spectrogram).
- **One trace gain and one CSD color scale for both events,** both set by the dentate spike. The IED therefore swings past its rows and saturates the CSD.
- **Spectrograms like Jarvis's pane** (`backend/analysis.py` `_stft_legacy`, i.e. xf_spectrogram): 8 contacts stacked (CSC1, 9 … 57), a 1 s window, Hamming frames a tenth of it long with 98% overlap, jet. Each frequency is shown in dB over that contact's median across 20 random baseline windows, on one color scale for both events.
- **Filters:** dentate spike 5–100 Hz; IED >1 Hz, as in the Jarvis pane.

**Your screenshot** (1197.37 s, "both, at Incisor's Spike") is PTEN m34 s5, the IED in Rain's PTEN figure, so it was not used on this KCNT1 poster.

---

# v5 (2026-11-26): every figure rebuilt in one style

`KCNT1_poster_v5.pptx` / `.pdf` is v4 with all 14 figures redrawn from their data (`code/v5/`, built by `build_v5.py`; figures in `v5_assets/`, preview in `KCNT1_poster_v5_preview.png`). Figures from the old posters were not cropped this time: their numbers were read back out of the PDFs (vector paths, the PDFs' own image tiles, colours read back through their own colorbars) and drawn again.

**One style for every figure** (`code/v5/style.py`)
- Calibri, drawn at the exact size it prints, so nothing is scaled on the poster: ticks 14 pt, labels 16, titles 17, notes 13, nothing under 11.5.
- Genotypes: WT grey `#8C8C8C`, Het orange `#E08A2C`, Hom purple `#7B2D8E`.
- Regions: CA1 blue `#0072B2`, supra blade green `#009E73`, hilus red `#C0392B`, infra blade pink `#CC79A7`.
- CSD everywhere: sinks blue, sources red, white at zero. Spectrograms stay jet, as in Jarvis.
- Interneuron spikes are amber `#D99A00` in every figure (the seizure's hilar unit, the opto SST unit, the HIPP cell in the circuit); every light cue is blue `#2F86D6`.

## Figure by figure

| Panel | Source | What was done |
|---|---|---|
| A Behavior | v4's data and statistics (`poster_fig_v2.py`) | Redrawn (`fig_behavior.py`); numbers unchanged. |
| E Seizure | The raw recording: Jarvis's cache `%LOCALAPPDATA%/Jarvis/seahorse_raw/m459_s1_cache.npz` (read on a VACC compute node by `tools/seahorse/story_m459.py --fetch`) | `seizure_data.py`: CSD as in figure A (60 Hz low-pass, 1.2-contact smoothing, −d²V/dz², 4 ms); each zone's \|CSD\| against its own quiet baseline (600–660 s; the original used 400–840 s); the hilar unit sorted again with `story_m459.sort_unit` (CSC 41; 12.4 Hz over 850–885 s; 0.85 ms wide; 791 spikes). Sinks were red in the original (RdBu) and are blue now. |
| F, G Opto | Dylan's 2024 poster PDF, Figs. 7–8 | LFP: its drawn path (min/max envelope, µV from its ticks). Spectrograms: its own image tiles, read back to dB through each panel's colorbar, redrawn on one scale (112–180 dB, 0–100 Hz; the 12 Hz panel had its own 60–180 scale and ran to 200 Hz). Spikes: the x of each orange tick. Autocorrelograms: its bar rectangles (5 ms bins) and fitted curves. Burst power: the amplitudes it prints. Firing rates: its panel C line, calibrated on its gridlines; the same method reproduces panel B's printed amplitudes to within 0.15% of full scale. |
| B Discharges | NBH'25 poster, Fig. 4A–D | CSD: its own image, read back through its colorbar. LFP (30 kHz), spectra and unit traces: its vector paths. Probe track: its histology image. Layer names: its probe-track labels, which sit at the CSD's depths. |
| C Discharges | NBH'25 poster, Fig. 4E–F | CSD tiles read back as for B. Phase times come from its arrows: 38.3967 s and 38.3997 s, so 3 ms apart (v4 said ~5 ms). Ei timing from its 200 ms bar, voltage from its 2 mV bar. Fi has no bar of its own and is drawn on Ei's scale (an assumption). Eii and Fii now share one CSD scale (±0.2; Fii's own was ±0.1). |
| D Urethane | `GitHub__jeremystats__KCNT1_urethane_sessions.csv` | Recomputed as in draft 1: WT 5, Het 2, Hom 8; Hom vs WT exact Mann–Whitney P = 0.0031. |
| Methods: head-fixed | NBH'25 Fig. 2A | Its mouse illustration (its own image, with its transparency); the probe, fiber and head bar are drawn here. |
| Methods: laminar | NBH'25 Fig. 2B (a control mouse) | Its 64 traces as drawn, with its layer labels and its 1 s (85.08 pt) and 500 µV (26.76 pt) bars. |
| Methods: DS and IED | v4's m1609 events (`methods_fig_v4.py` processing) | Restyled. The CSD map changed from jet to the poster's sink/source map, with the same shared scales. |
| Methods: histology | Dylan's 2024 poster, Fig. 6C | Its own 512 tiles. |
| Methods: arena | NBH'25 Fig. 6A | Its photo; the tracking overlay is baked into the photo. The rotation arrow and labels are drawn here. |
| Intro: SST/PV | Shore et al. 2024, eLife, Fig. 4C (CC BY 4.0) | f–I curves read off the article's page raster by colour, calibrated on its tick marks (approximate, about ±1 Hz). The traces are the article's own (middle current step), recoloured WT grey / Het orange and drawn on one scale (its 50 mV / 100 ms bars). |
| Intro: circuit | Drawn here | |

**Sign check (B, C).** NBH's own dentate-spike CSDs (Fig. 2Di/Dii) put the OML and MML sinks in blue. So negative means sink there, as in Jarvis, and the colours carry over directly.

**Not used.** Dylan's Fig. 7E ("10 Hz") has the same times and spike train as 7D ("7 Hz"), so it looks like a duplicate.

## Layout

- The Behavior card now ends under its caption, and the Discharges card moved up 0.95 in into the space.
- B is one row across the card, with C and D side by side under it.
- F and G are stacked, with their four light columns aligned, and share one caption.

## Text that changed

- **E caption and Conclusion 3:** the hilar unit fired at 58 spikes/s over the last 3 s before onset, **4.7×** its 12.4 Hz baseline, then about 0.4 spikes/s from 3 to 80 s.
  - This is what Jarvis's Seahorse story says too ("about 60 Hz: nearly five times").
  - The old figure said ~3×, against a 13.7 Hz baseline from a longer window.
- **C caption:** "3 ms later" (was ~5 ms), plus phase badges 1 and 2 instead of red and blue arrows, because red and blue now mean source and sink.
- **B caption:** "Left/Right" instead of "Top/Bottom".
- **SST/PV caption:** the new colours, and "Redrawn from".
- **F + G:** one caption.

## Worth checking

1. Conclusion 3 now says "nearly 5×" instead of 3×.
2. **B subheading ("IEDs begin as a hilar sink").** In the redrawn CSD the hilus at the spike is a strong source (red), and the sink sits just above it at the GCL. The wording may want a second look.
3. Fi is drawn on Ei's voltage scale.
4. The eLife curves are digitised from a raster, so they are approximate.


# v6 (2026-11-26): the comments on v5

v6 keeps v5's style (`code/v6/style.py`) and works through the seven comments left on `KCNT1_poster_v5.pptx`. v5 is untouched.
Scripts and the numbers they draw: `code/v6/`. Figures: `v6_assets/`. Build: `python code/v6/build_v6.py KCNT1_poster_v4.pptx v6_assets KCNT1_poster_v6.pptx`.

## The lab's colours, everywhere

The lab's own cell icons (PTEN poster, Fig. A; NBH'25 poster, Fig. 2B) draw CA1 pyramidal cells green (#ADE076) and granule cells pink (#E9807F). v6 uses those two colours for the regions on every figure:
- **CA1:** green.
- **Supra and infra blades:** pink, the lower blade lighter.
- **Hilus:** amber, the colour of its SST interneurons.

They replace v5's CA1 blue, supra green and hilus red. Sinks stay blue and sources red. B, C, E and both methods recording figures were redrawn with the new colours; their data did not change.

## Figure by figure

| Figure | Comment on v5 | What v6 does | Source |
|---|---|---|---|
| Intro f–I (`fig_intro.py`) | "there is also one of these figures for Hom ... include those as well" | Adds a Hom row under the Het row: 2×2 panels, each against its own WT, mean ± SEM, with example traces at one shared scale. | Het: Shore et al. 2024 eLife, Fig. 4C (as v5). Hom: Shore et al. 2020 Cell Rep, Fig. 4 C4 (NFS, SST-like) and B4 (FS, PV-like), `nihms-1642113.pdf`. Digitised by `cellrep_digitize.py`. |
| Intro circuit (`fig_intro.py`) | "Include the PV ... refer to the seahorse atlas ... Granule cells are usually Pink" | Redrawn after Seahorse's dentate plate (`seahorse_schem.js`, `dentate()`), with every connection ending in the layer where it synapses. | Seahorse dentate plate. |
| Methods DS/IED (`fig_m_events.py`) | "Too much text ... make sure the colors match and use icons" | Channel labels replaced by the lab's icons on one shared depth axis. Spectrograms recomputed at the centre of each 8-contact band. | See the depth note below. |
| Methods laminar (`fig_m_laminar.py`) | none (for consistency) | The icons from NBH'25 Fig. 2B put back beside its printed layer names. | NBH'25 Fig. 2B. |
| Histology (`fig_methods.py`) | "these pictures need to be framed better" | Cropped to both granule layers with the hilus between them; layers named; two SST cells marked; channel key underneath. | Dylan's 2024 Fig. 6C, its own tiles. |
| Arena (`fig_methods.py`) | "so low res ... remake it in a schematic" | Drawn, not photographed: floor from above, Figure A's 60° red shock-zone wedge, floor rotation, wall cues, a mouse. | Drawn. |
| F + G opto (`fig_opto.py`) | "make it clear that the first row corresponds with the second ... blue colored labels ... janky" | One grid, one tinted column per condition from the light bar down to the autocorrelogram. Condition names once, in black. Blue ticks under each autocorrelogram every light period. The G subheading and picture are gone. | Dylan's 2024 Figs. 7–8 (as v5). |
| E seizure (`fig_seizure.py`, `section.py`) | "I don't know if I like the DG representation ... improve them based on resources in Jarvis's seahorse" | The four stage drawings are the real coronal section the probe went down: AP −1.90 mm, probe at ML +1.4 mm. | Seahorse's 10 µm laminae (`web/seahorse/fine10.shb.gz`, Allen CCFv3 2017 plus Seahorse's derived layers), saved as `data/atlas_section.npz`. |

Detail on each change:
- **Intro f–I, digitising.** The Hom markers are found at each current step; the steps sit at 0, then 40 to 1480 pA every 60 pA (FS) and every 20 pA from 0 to 600 pA (NFS). Means are read to about ±0.5 Hz (FS) and ±0.2 Hz (NFS).
- **Intro f–I, SEM.** It is each marker's whisker on the side away from the other group.
- **Intro f–I, P values.** These are the papers' own: I50 P for Hom.
- **Intro circuit, what is drawn:**
  - LEC into the outer and MEC into the middle molecular layer, in both blades.
  - Granule cells (pink), with a mossy fibre to CA3.
  - The hilar SST (HIPP) axon in the outer layer, with inhibitory synapses on the granule cells' outer dendrites.
  - The PV basket cell at the granule layer's hilar border, wrapping the granule cells' somata.
  - Labels with what KCNT1 gain of function does to each cell, from the f–I panels.
- **Methods DS/IED, cache.** `data/m_events.npz` holds what is drawn, so the figure redraws without the raw windows.
- **Arena, wall cues.** They are drawn only to show that cues exist; their shapes and places are not the real ones.
- **Opto, firing-rate numbers.** v5's per-window rates under each raster are dropped. They were spikes per second in the 9 s window shown (for example 6.1 at baseline), which read as if they contradicted the panel on the right, which is each run's mean (0.7 at baseline). The panel on the right is now labelled "mean of each run".
- **E seizure, colours.** Each stage colours the active zones, outlines the zone that just joined, and draws the probe and the hilar unit.

**Where the methods icons sit.** m1609 has no traced layers. The cells follow its own mean dentate spike:
- Upper and lower blade sinks at CSC 34 and 56 are the middle molecular layers.
- Granule cell layers sit 7 contacts (140 µm) inside each sink.
- CA1's pyramidal layer sits 27.5 contacts (550 µm) above the upper sink, and the fissure 5.5 contacts above it.

These spacings come from the Allen laminae along the probe track at AP −1.90 mm.

**The seizure unit in the stage drawings, a correction.** v5 drew the hilar unit as silent from stage 2 on. Its own histogram says otherwise:
- **Stage 1 (0–1 s):** 18 spikes/s.
- **Stage 2 (1.3–2.3 s):** 66 spikes/s, its highest.
- **2.6–3.7 s:** no spikes.
- **3.7–43.8 s:** masked by the discharges.
- **After the seizure (43.8–80 s):** 0.4 spikes/s.

v6 draws it firing in stages 1–2 and silent in stages 3–4. The new caption states these numbers instead of v5's "0.4 spikes/s from 3 to 80 s", which ran across the masked stretch.

## Text that changed

- **E subheading:** "The seizure starts in the hilus, then recruits both blades and CA1, as a hilar interneuron falls silent". It falls silent at about 2.6 s, after the upper blade has joined.
- **Conclusion 3:** "...then fell silent as the seizure spread" (was "as the seizure began").
- **Captions:**
  - E caption: the atlas section and the unit's numbers above.
  - Intro paragraph 2: adds "in heterozygous and homozygous mice"; SST-type fire less in both, PV-type fire more in Het and less in Hom [3, 4].
  - f–I and circuit captions: rewritten.
  - CSD primer: shorter.
  - Optogenetics text: points at the image.
  - Opto: one caption for the merged F.
  - F subheading: "Light drives an SST unit, and its bursts lock to the light, most at 5 Hz".

## Layout

The intro card is 0.7 in taller (2×2 f–I, four-line paragraph 2). Methods starts lower and still ends at 35.5 in, with a bottom row of histology, text, arena and text. Opto F fills the card where F and G used to be.

## Worth checking

1. **Hom panels: cell types.** The Hom cells are cultured cortical neurons classed as NFS and FS by their firing, not SST/PV-labelled cells. The panels say "SST-like" and "PV-like".
2. **Hom FS cells fire less.** The Het PV cells fire more. The poster now says both.
3. **E subheading and Conclusion 3:** the timing above.
4. **B subheading ("IEDs begin as a hilar sink"):** unchanged from v5. The redrawn CSD shows a hilar source with the sink just above it in the GCL.
5. **Methods icons:** placed from the dentate spike's sinks, not from histology.


# v7 (2026-11-26): the comments on v6, and the lab's cells

v7 works through the twelve comments (and one reply) on `KCNT1_poster_v6.pptx`, plus the request to use the lab's cell drawings everywhere. v6 is untouched.
Scripts and data: `code/v7/`. Figures: `v7_assets/`. Build: `python code/v7/build_v7.py KCNT1_poster_v4.pptx v7_assets KCNT1_poster_v7.pptx`. Every figure was regenerated from the shipped `code/v7` and came out pixel-identical.

## The lab's cells, everywhere

- **CA1 pyramidal and granule cells.** These are the drawings from the PTEN opening figure (`Poster Resources/Opening4paperAndPoster.pdf`, panel D):
  - green pyramidal cells;
  - pink granule cells with their somata below (upper blade);
  - pink granule cells with their somata above (lower blade).
- **How they are used.** `cells_extract.py` reads them as the vector paths they are and saves them to `data/cells_open.npz`. `cells.py` then draws them:
  - stretched to the layers they span on a depth axis;
  - or bent along a blade in the circuit.
- **Holes where dendrites cross.** The PDF fills with the even-odd rule. The paths are re-wound so matplotlib's fill gives the same result.
- **SST and PV cells.** `cells.py` draws these in the same hand: thin, wandering, tapering dendrites as filled shapes, and a solid soma. Both are seeded, so every figure gets the same two cells.
  - SST (HIPP): a multipolar soma in the hilus, long spiny dendrites that stay in the hilus, and an axon that spreads in the outer molecular layer.
  - PV basket cell: a pyramid-shaped soma at the granule layer's hilar border, and smooth dendrites up through the molecular layer and down into the hilus. Its axon wraps the granule cells' somata.
- **Where they appear.**
  - Methods laminar and Methods DS/IED.
  - Figure B (beside its layer names) and Figure C.
  - Figure E, in place of the region names, each cell with its region's colour bar.
  - The f–I column headers.
  - The dentate circuit.

## Figure by figure

| Figure | Comment on v6 | What v7 does |
|---|---|---|
| I_fI | "make it more clear that this is like a 2x2 matrix … rough on the eyes" | A 2 × 2 matrix. Column headers SST-type and PV-type, each with its cell. Row bands Het (orange) and Hom (purple). Each cell is labelled with what it is (e.g. "non-fast-spiking (SST-like)"). The P value and a verdict badge sit at the top left. Thinner lines and lighter bands. |
| I_circuit (`fig_circuit.py`) | (chat) use the lab's cells in the DG schematic; SST and PV "between schematic and realistic" | Granule cells are the lab's drawing, bent along both blades. The SST (HIPP) cell has its axon plexus in the outer molecular layer. The PV basket cell's axon wraps four granule cells. LEC/MEC inputs and the mossy fibre are as before. |
| M_headfixed | "the head bar sucks … it's really the probe holder/the micromanipulator" | The bar is now a drawn micromanipulator: arm, vertical drive, micrometer knob and clamp, holding the probe and fiber. The head plate is the one in the illustration, now named. |
| M_laminar | "that bottom part should be both the Infra blade and supra blade … two granule somas facing each other" | Both blades, with somata facing across the hilus, and an SST cell in the hilus. The layer names below CA1 were moved (see below). |
| M_events | "sharper hw for the IED"; (chat) overlay CSD and LFP, voltage over the spectrograms | The CSD and voltage are one panel, as in E. Each spectrogram has its own contact's voltage (>1 Hz) drawn over it. The IED is now 905.34 s, half-width 12 ms on its largest contact (v6's 882.75 s: 44 ms); `tools/ied_pick.py` compares six candidates. Text beside the figure. |
| B, C | (chat) cells on every depth profile | The cells sit between the layer names and the CSD. B's and C's captions are as in v6. |
| E | "crisp it, it's a lil jagged"; "bottom two figures line up with the top two"; "replace CA1, suprablade, hilus, infra blade with the icons"; "why … the hilus …?" | See the E section below. |
| F | "indicate in the blue bar the frequency of the light" | The bar shows one blue tick per pulse at 5, 7 and 12 Hz. Pulse width is not drawn because it is not in the 2024 poster. |
| Histology, arena | none | Drawn 3.1 in wide, since the methods card had room. |

## E: what changed

- **Crisp.** `section.py` now draws the atlas section as smooth vector shapes, not an upsampled label image.
  - Each layer group's mask is cleaned, blurred 16 µm (the outer edge 22 µm) and upsampled 5×.
  - Each group is filled where it leads every other group. Neighbouring layers therefore share one smooth border.
- **Lined up.**
  - The seizure's clock (0 to 5.75 s) runs at one CSD panel's width per second, so each stage's panels sit exactly over their second. That holds for the histogram and the |CSD| plot alike.
  - The 1 s between stages 3 and 4 is the real gap; the CSD scale and the scale bars sit in it.
  - The 3 s before onset get their own, narrower clock on the left, marked by a break.
- **Icons.** The region names beside the CSD are replaced by the cells, each with its region's colour bar.
- **The hilus question.** This is answered in the caption, with the numbers below, from `tools/stage1_check.py`:
  - **Absolute currents.** In stage 1 the upper blade carries the largest currents. Its median |CSD| is about 1.5× the hilus's, and the strongest colour is its sink-source pair at CSC 31–36, at 0.6 s.
  - **Baselines differ.** At rest the upper blade's |CSD| is 2.5× the hilus's (1511 vs 612).
  - **How the stages are called.** Each zone is divided by its own quiet baseline, and that measure drives both the stage drawings and the bottom plot.
  - **On the plotted curves, the hilus rises first and most.** It passes 15× at 0.22 s and the upper blade at 0.54 s; it passes 20× at 0.50 s and the upper blade at 0.59 s. Its peak is 59× at 0.71 s, the upper blade's 28× at 0.70 s.
  - **The order depends on the threshold.** At 10×, the upper blade is ahead: it is above 10× for 59% of the 3 s before onset, the hilus for 38%.

## Laminar recording: where the dentate layers sit

- **What NBH'25 printed.** OML, MML, GCL and HILUS, down to the last trace.
- **What the recording's own dentate spikes say.** Its two sharp ones (3.32 and 5.36 s, 100 ms high-pass) peak positive at 1020–1062 pt on the page. They reverse to negative below 1080 pt, down to the last trace.
- **Reading.**
  - A dentate spike is positive in the hilus and negative in the molecular layers.
  - The NBH poster's other DS panels plot positive up.
  - So the middle is the hilus and the bottom is the lower blade, as the user said.
- **Placed.**
  - Upper GCL at about 1012 pt.
  - Hilus at about 1046 pt.
  - Lower GCL at the reversal, about 1080 pt.
  - Lower molecular layer below that.
  - SLM and the fissure just above the upper molecular layer, about 45 pt (200 µm) deep.
- **Caveat.** These are placements from two events, not from histology.

## The poster

- **Header.** 3.72 in tall (v6: 5.6). Smaller logos, a 54 pt title, 25 pt authors, and affiliations on two lines at 19 pt.
- **Type.** Aptos throughout; Aptos Display for the title and section headings. Aptos is Office's own typeface, and PowerPoint fetches it on any Microsoft 365 install. The figures use it too: `style.py` registers the files from Office's cloud-font folder. The PDF embeds it.
- **Panel headings.** The poster's green with the letter in a UVM-gold badge. Gold is no longer used as text on white.
- **Funding.** As on the PTEN poster v3: PTEN Research, NIH R21-NS133670-02 and NIH R01-MH134787-02. The logos were redrawn in one-colour white for a dark-green strip by `funding_logos.py`; PTEN Research's orange accent is now UVM gold. The "Funding to confirm" tag is gone.
- **Layout.**
  - Cards start at 4.14 in.
  - The space the header gave back went to taller methods figures, a taller E and F, and 21 pt conclusions.
  - Methods DS/IED now sits beside its text.

## Text that changed

- **E caption.** The one clock, the cells, the stage-1 numbers above, and "÷ own quiet baseline".
- **F caption.** One tick per pulse.
- **Methods texts.**
  - "Reading the CSD": CSD and voltage together, voltage over the spectrograms, and the IED's half-width.
  - Recording: "the lab's cells beside its layers".
- **Captions.**
  - Circuit: the SST plexus, the PV axon, and where the cells come from.
  - f–I: Het and Hom rows.
- **D heading.** "Under urethane, Hom mice have IEDs; WT rarely do", shortened to fit.

## Worth checking

1. **Laminar recording.** The NBH poster's DG labels are replaced by layers placed from its dentate spikes (see above).
2. **E, stage 1.** "Starts in the hilus" rests on each zone's change against its own baseline. In absolute current the upper blade is larger, and at a 10× threshold it leads.
3. **IED.** The new example (905.34 s) is from the same curated Lock list as v6's. 863.44 s is as sharp but stays in the dentate.
4. **Funding.** Copied from the PTEN poster as asked. The logos are recoloured (white, the PTEN accent in gold).
5. **F.** The pulse ticks show frequency only; pulse width is not drawn.


# v8 (2026-11-26): the comments on v7, and a spacing pass

v8 answers the eight comments left on `KCNT1_poster_v7.pptx`, then lays the whole poster out on one spacing grid. v7 is untouched.

- Scripts: `code/v8/`. Figures: `v8_assets/`.
- **Build:** `python code/v8/build_v8.py KCNT1_poster_v4.pptx v8_assets KCNT1_poster_v8.pptx code/v8/data/measure_v8.json`. That reproduces the shipped deck exactly, and every figure regenerates pixel-identically.
- **New build with changed text:** run `tools/build_converged.ps1`. It builds, has PowerPoint measure every text box (`tools/measure_text.ps1`), and builds again until the text heights stop changing.

## Figure by figure

| Figure | Comment on v7 | What v8 does |
|---|---|---|
| E | "wiggliness on some borders of the dentate gyrus" | `section.py` blurs the atlas layers 27 µm (the tissue edge 40 µm) instead of 16 µm. Every drawn border is then smoothed again along its own length (26 µm). |
| E | "the downward arrow is meant to represent the probe … make a probe" | The probe is a grey shank with a pointed tip and its 64 contacts, every 20 µm. |
| E | "the extra arrows are confusing" | The arrows between the stage drawings are gone; the numbers ①–④ carry the order. |
| E | "the sink source scale and the other scales are in a weird place" | Moved to a column of their own on the right: the CSD colour scale beside stage 4, and the 2 mV / 250 ms bars at the panels' bottom line. The seizure clock is 2.0 in per second (v7: 2.1) to make room, and the stages still sit over their seconds. |
| E | "the 4 spike has a white background" | The hilar unit's spike waveform moved out of the hatched stretch into the right-hand column, with no box. |
| E | "add the PV here too … in an artistic way" | A PV basket cell (blue) among the upper blade's granule cells, its soma at the granule layer's hilar border, beside the hilar SST cell. |
| I_circuit | "Wow beautiful." | Unchanged, but drawn 1.24× larger, with the hypothesis under it. |
| I_fI | "enlarge the neuron icons … get more artistic"; "small traces … hard to see" | Each column is headed by its cell, drawn large in a tinted card with a soft glow. The PV cell lies on its side. The example traces are 1.4× taller (0.27 in per 50 mV) and one pixel bolder, with WT a shade darker. The f–I plots are taller. |
| A | "optimize the white space" | Larger arenas, the learning curves pulled in, c and d raised. d's P value is no longer cut at the right edge. c's "Young" and "Old" labels are back: v5–v7 cut them off at the figure's bottom edge. |
| F | "add the SST neuron here too … artistic" | The unit's row is named by an SST cell glowing blue (it carries ChR2), with its axon running into its own spikes. |
| Intro text | "the text is taking up too much … optimize the figure space" | Cut from 9 lines to 6: the same facts in fewer words, pointing at the figures ("left", "right"). The hypothesis moved under the circuit, so the two columns of figures end level. |

## Spacing

- **One grid in `build_v8.py`, everywhere:**
  - heading band to first item 0.24 in;
  - panel heading to its figure 0.14 in;
  - figure to caption 0.1 in;
  - caption to the next panel heading 0.36 in;
  - last item to the card's bottom 0.26 in;
  - card to card 0.38 in.
  - All columns start at 4.14 in and end at 35.5 in.
- **Figures:** each is trimmed to its ink and placed at its own print size (300 px per inch). Its edges sit on the grid and its type prints at the size it was drawn.
- **Text boxes:** each is exactly as tall as its text, as PowerPoint measures it. None overflows.
- **Panel letters:** the gold badges are centred on the heading's capitals (v7's sat about 0.06 in low).
- **Header:** the title, authors and affiliations are centred as one block in the band, and the logos are centred too.
- **Methods:** the Recording text sits close under the two figures it describes. The space the shorter intro gave back went to taller methods figures (laminar and head-fixed +0.4 in, dentate spike/IED +1.5 in, histology and arena +0.25 in wide). Also taller: B +0.6 in, C +0.4 in, E's CSD panels +0.34 in and F +0.4 in.
- **Line breaks:**
  - The C and E headings break where the sense does ("…two dentate spikes;" / "…and CA1,").
  - B's caption no longer ends on "Hz) fire."; the band is already in the figure's title.
  - The CSD text reads "between 100 and 600 Hz", with a non-breaking space before "Hz".
  - F's caption no longer ends on "Hz.".
- **Smaller fixes:**
  - B's 400 µV label clears the last unit trace (the traces stop at 98 ms).
  - F's glow fits inside the figure.
  - Conclusions at 21 pt, centred in their card.

## Worth checking

1. **Intro wording:** cut from 9 lines to 6 (the user asked). Dropped to save lines: the named syndromes, "human Y796H", "sleep-related", "that map to motor cortex" and "not excitatory ones". Kept: that the frequent seizures are in homozygous mice, and the term "developmental and epileptic encephalopathies".
2. **E's PV cell is decorative,** like the cell icons: it shows where PV basket cells sit. The recorded hilar unit is not identified as SST or PV.
3. **F's glowing SST cell is the figure's label for the unit's row,** not a drawing of the recorded cell's shape.


# v9 (2026-11-27): the comments on v8

v9 answers the nine comments left on `KCNT1_poster_v8.pptx`. v8 is untouched.

- Scripts: `code/v9/`. Figures: `v9_assets/`.
- **Build:** `python code/v9/build_v9.py KCNT1_poster_v4.pptx v9_assets KCNT1_poster_v9.pptx code/v9/data/measure_v9.json`. That reproduces the shipped deck byte for byte, and all 15 figures regenerate pixel-identically from `code/v9`.
- **New build with changed text:** `code/v9/tools/build_converged.ps1`, as in v8.

## Figure by figure

| Figure | Comment on v8 | What v9 does |
|---|---|---|
| Methods: dentate spike and IED | "the IED isn't SHARP enough … high prominence and narrow halfwidth, and high power … find a good one" | See "The new IED" below: 1305.43 s, chosen from all 688 spikes in the recording. |
| Methods: dentate spike and IED | "make it more clear hey this is DS, this is IED … similar to … the SST PV figures" | Each event is named in a tinted header card, like the f–I cells. The card holds its name, what it is ("a normal dentate event", "an interictal discharge"), its filter band, and its own waveform, glowing. The two waveforms share one scale, so the IED is visibly the bigger one. Dentate spike is teal; IED is crimson. |
| Methods: dentate spike and IED | "Where PV?"; "the cartoon cells overlap with their CA1 and DG lines"; "the bottom DG cells bigger? Make them the same size" | The cells have their own column, clear of the CA1/DG bars; the CSD and spectrogram panels are 0.18 and 0.11 in narrower to make room. Both blades are drawn at one scale, the lower blade the upper's mirror. A PV basket cell sits at each granule layer's hilar border. |
| Methods: laminar recording | "Where PV?" | The same: PV at both granule layers, both blades the same size (the lower blade was 1.27× the upper). The traces moved 0.1 in right so the cells have their own column. |
| B | "Where PV?" | A PV basket cell at the granule layer's hilar border. C got one too, for consistency. Also: B's 400 µV label now fits beside its bar, clear of the 50 ms bar. |
| E, diagram | "PV interneurons are also around the bottom cell layers … Seahorse … more anatomically accurate" | See "The cells, by one rule" below. A PV basket cell at each blade; the hilar SST cell with its axon up to both outer molecular layers; both blades the same size. |
| E, bottom graph | "highlight … hilus activity goes up … gives up … the supra blade kicks in … then the infra blade, and then CA1 joins" | Every zone is drawn lighter. Where each zone takes over, its line is bold, glowing and named, with its stage's number. See "E's story" below. |
| F | "make it clearer that the Firing rate summary is related to the SST units; and the Rhythm strength … to the spikes scaled" | Each summary sits level with the row it summarises. An amber arrow runs from that row into it, labelled "its rate" and "its rhythm". The y-axis labels moved into the notes ("spikes/s, mean of each run"; "power at the light frequency", ×1000), so the arrows come straight in. |
| Intro circuit | "reduce the number of granule cells to make it less busy" | 6 granule-cell groups that no longer overlap: 24 cells instead of 40. The PV basket's cups now sit on drawn somata, at least 7° apart; v8's cups were placed by stale soma positions. The mossy fibre starts from a drawn granule cell. |
| A | "Get rid of the 'ringed: robust-rule outliers, kept' part" | The rings and the note are gone; every mouse is drawn alike. The caption now opens "All 56 mice." |
| Methods histology | "GCL label on the top blade is a bit too high" | Moved to the middle of the upper granule layer, measured from the image (rows 190–370 of the crop). The lower label also moved to its band's middle. |

## The new IED (methods)

**How it was chosen.** Every unflagged spike in m1609's committed Lock set (688) was read on a VACC compute node (`tools/scan_sharp.py`, about 3 min). Each was scored the way the figure draws an IED: ±1 s read, 60 Hz notch, >1 Hz, even contacts. Four measures:
- the largest contact's peak within ±40 ms;
- its half-width;
- prominence: the peak against the biggest same-sign swing 60–300 ms either side;
- high-frequency power: 100–600 Hz RMS in ±20 ms of the peak, against each contact's baseline.

The results are in `data/sharp_metrics_m1609.json`. The best 40 windows were drawn side by side (`tools/ied_sheet.py`), and the top 8 in the figure itself.

**Chosen: 1305.43 s.** It is the sharpest-looking clean event:
- It stands 5.6× above anything within 0.3 s. v8's (905.34 s) stood 1.2× above, which is why it read as a slow wave.
- Half-width is 12 ms on its largest contact (CSC 46); its CSD column is 13 ms wide at half height.
- 3.0 mV, 2.4× the dentate spike.
- 100–600 Hz power is 13 dB over baseline at CSC 44.

**Runners-up:**
- 863.44 s is the most isolated, but its CSD is broader (14 ms).
- 823.81 s is the narrowest (7 ms) with the most power, but other discharges sit 100 ms on either side of it.

**Caption.** The CSD text now says how the IED was picked. It also says that the IED fills both blades and the hilus at once. v8 said "runs from CA1 through both blades"; this event is a dentate one.

## The cells, by one rule (`cells.py` v9)

The rule follows Seahorse's knowledge base (`kb.py`) and its 3D model:
- **PV basket cell:** soma at the granule layer–hilus border; dendrites up through the molecular layer and down into the hilus; axon a basket around granule-cell somata. Seahorse's traced basket cell sits in the lower blade's layer (gcl2).
- **HIPP (SST) cell:** soma and spiny dendrites in the hilus; axon in the outer two-thirds of the molecular layer.

The helpers that apply it:
- `blade()` draws a blade's granule cells with their bodies centred on the granule layer, at a scale shared by both blades.
- `pv_basket()` puts a PV cell at the layer's hilar edge. Its apical dendrites end where the granule cells' dendrites do, and cups around nearby somata form the basket. In depth columns its dendrites are drawn thinner (`slim`).
- `sst_axon()` draws the SST axon to a blade's outer third.

Every depth column uses these: E, the two methods figures, B and C.

## E's story

The moments are read off the zones' own |CSD|:

| Stage | Zone | What it does |
|---|---|---|
| ① | Hilus | climbs from 15× to 59× by 0.7 s, then falls back to 7× by 1.4 s (dashed) |
| ② | Supra blade | 12× to 48× between 1.8 and 2.2 s |
| ③ | Infra blade | 6× to 49× between 2.9 and 3.2 s |
| ④ | CA1 | 13× to 43× between 4.8 and 5.3 s |

The caption says the bold stretches are where each zone takes over.

## Worth checking

1. **The IED choice.** The tools rank the candidates and draw them, so another can be swapped in with one number: `IED_T` in `fig_m_events.py`, then delete `data/m_events_v9.npz` with the VACC windows at hand.
2. **E's wording.** "…and falls back" describes the hilar |CSD| after stage 1, not the hilar interneuron. The interneuron falls silent later, at 2.6 s.
3. **The drawn cells are anatomy, not recordings.** The PV and SST cells mark where these cells sit. None of the recorded units is identified as PV.


# v10 (2026-11-27): the comments on v9

v10 answers the five comments left on `KCNT1_poster_v9.pptx`. v9 is untouched.

- Scripts: `code/v10/`. Figures: `v10_assets/`.
- **Build:** `python code/v10/build_v10.py KCNT1_poster_v4.pptx v10_assets KCNT1_poster_v10.pptx code/v10/data/measure_v10.json` reproduces the shipped deck byte for byte, and all 15 figures regenerate pixel-identically from `code/v10`.

## What changed

| Where | Comment on v9 | What v10 does |
|---|---|---|
| Everywhere | "shading or dividers … where each figure starts and ends … not at the cost of making it noisy" | **Hairline dividers** (1.25 pt, #D5DBE2) sit in the gaps between a card's figures, so they cost no space: <ul><li>intro: f–I \| circuit</li><li>methods: between its three blocks, and histology \| arena</li><li>discharges: under B, and C \| D</li><li>A: between its rows, and c \| d</li></ul>**Shading** is kept for groups within a figure: F's condition columns, the f–I rows, and now the dentate spike and IED backdrops. |
| Methods, events | "drop the DS and IED backdrop onto the figure's background … light enough to not mess with the CSD view" | Each event's tint now runs behind its whole group, from header to time axis. It is lighter than v9's header cards (#EAF4F5, #FCEFF0). The CSD panels are opaque, so only their margins are tinted. |
| Methods, events | "take out 1 or 2 spectrograms" | Six instead of eight, at CSC 7, 17, 27, 37, 47 and 57: bands of 10 contacts from CSC 2 to 62, each panel 9.5 contacts tall, against 7.6 before. The cache was rebuilt from the VACC windows (`data/m_events_v10.npz`). |
| Methods | "lots of wasted white space … enlarge the DS and IED figures … the Reading the CSD text column more narrow" | The figure is 10.5 in wide (was 9.6), the text column 3.0 in (was 3.9). The text now runs nearly the figure's height. It was reworded so no line breaks inside "half-width" or "high-frequency". |
| PV baskets, everywhere | "polish the way the basket cells hug the granule cells, a lil janky" | See "Baskets that hug" below. |
| E, bottom graph | "polish the highlights … a lil janky" | Each highlight is one filled shape that swells out of its line and back over its first and last 30%, with a seamless glow. v9 drew round-capped strokes that started and stopped as blobs. The hilus's fall is the same, lighter. The labels lost their white boxes, which showed over the grey stage bands. Also fixed: since v9, the pre-onset panel's x-limits and minor ticks had been left to matplotlib. |
| F | "Idk if I like the arrows … and its rate its rhythm" | No arrows. Each summary title starts with a small copy of the row it summarises: amber spike ticks before "Firing rate", amber autocorrelation peaks under their fitted curve before "Rhythm strength". The two panels share their light axis and fill the right-hand column. The rate panel starts level with the column headers, where v9 left white space, and ends level with the spike row; the rhythm panel ends with the autocorrelation. |
| D | (white space) | D is 0.8 in taller, so it ends level with C. Its y-axis stays on whole numbers. |

## Baskets that hug (`cells.py` v10)

v9 placed the cups by stale soma positions, so they hung below the cells.

v10 finds the somata in the lab's drawing itself (`bulbs()`):
1. Rasterise the drawing at 40 px per pt.
2. Take a distance transform and keep everything more than 0.42 pt from an edge; dendrites are thinner.
3. In each region, the deepest point is the centre of a soma's round end and its depth is the radius.

That gives 8 somata per group, for both blades. Then:
- `blade()` returns them in the figure's own units.
- `pv_basket()` cups the 3 nearest. Each cup is 1.45× the soma's radius, rising a little up both flanks, with 3 terminals on it, and one axon runs from the basket cell along the row of cups.
- The intro circuit uses the same `cup()` on its arc (`arc_somata()`).

## Worth checking

1. **The dividers are new.** Say if any should go; each is one line in `build_v10.py` (`divider(...)`), or two in `fig_behavior.py`.
2. **The spectrogram depths changed with their number.** They are now CSC 7, 17, 27, 37, 47 and 57; v9 used 4, 12 … 60.
