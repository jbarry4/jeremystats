# What was done on 2026-11-16, and how to run it again

Written so this work can be rebuilt, checked, or later moved into Jarvis. Nothing here changed Jarvis (the one exception, a to-do
banner in the Extraction Room, is from earlier the same day). Everything below reads a frozen copy of the data.

## Where things are (round 11, 2026-11-17; round 10 is in `archive_round10_2026-11-17/`)

| Folder | What |
|---|---|
| `round11/Sanity_check_CTL.pdf`, `Sanity_check_PTEN.pdf` | Names and DS3 checked, one block per recording |
| `round11/quality_check/` | One page per recording (m6 left out); row 4 = the one normalized figure |
| `round11/Averaged_DS1_DS2.pdf` | DS1 and DS2 without DS3, depth normalized: control, PTEN, IED−, IED+, groups overlaid |
| `round11/Summary_table.pdf` (+ `.csv`) | Every classifier's separation index per recording, no verdict words |
| `round11/Supplemental_figures.pdf` | How the classification choices behave |
| `battery_reports/uncorrected/Leads_explained_UNCORRECTED.pdf` | Nine leads explained from the waveform up, plus the LFP-artifact appendix |
| `battery_reports/uncorrected/`, `corrected/` | Battery run 2 reports and every test as CSV |

Round 10's table (kept for reference):


| Folder | What |
|---|---|
| `round10/quality_check/` | One page per recording (18 PNG + one PDF): the classification under three classifiers, DS3, and the recording on the normalized depth axes |
| `round10/Averaged_CTL.pdf`, `Averaged_PTEN.pdf` | The dentate spike averaged over recordings on normalized depth: control; PTEN (all, IED−, IED+) |
| `round10/Averaged_comparison.pdf` | Groups laid over each other, with a cluster permutation test per curve |
| `round10/Summary_table.pdf` (+ `.csv`) | One row per recording, every classifier's separation index, the averages |
| `round10/Supplemental_figures.pdf` | How the classification choices behave |
| `battery_reports/uncorrected/` | `Battery_UNCORRECTED.pdf`, `Top10_leads_UNCORRECTED.pdf`, `all_tests_UNCORRECTED.csv` |
| `battery_reports/corrected/` | `Battery_corrected.pdf`, `all_tests_corrected.csv` |
| `battery_reports/measures.csv` | Every measure: what it is, and its number for each of the 17 recordings |
| `battery/` | The code and the frozen data (this folder) |

## The data freeze

- Source: Extraction Room, room "dentate_spike", version 6 (the Halo set, 4,824 events) and version 8 (the No P-spikes set,
  4,177 events); 18 recordings, one per mouse. m51 has 5 events and is left out of every statistic.
- `qc_source/deep_extract.py`, `deep_extra.py`, `deep_pca2.py`, `deep_opt.py`, `deep_opt2.py`, `deep_ds3.py` are the scripts that read
  Jarvis (they import `backend.app` and only read). Their outputs for the Halo set are beside them.
- `build_dataset.py 6` and `build_dataset.py 8` fold those outputs into `data/ds_v6.pkl` and `data/ds_v8.pkl`; `README.md` documents
  every field; `dsdata.py` loads them.
- Groups: `group` (CTL / PTEN) and % knockout from the room; `subgroup` (IED− / IED+) from the lab sheet "PTEN/KCNT1 Dentate
  Spike Data", tab "PTEN Recording Sessions_Hits", column `subgrp` (read 2026-11-16): IED− m8, m33, m1, m7; IED+ m13, m28, m3,
  m5, m34. The IED+ mice are the high-knockout mice except m7.

## Depth normalization (`dsdata.Rec.landmarks`, `normcurves.py`)

The probe crosses the two blades at a different place and angle in every mouse, so microns do not line up. Each recording
supplies its own ruler, found on the mean CSD of all its events at the DS peak (bad contacts filled):

- `U`, `L`: the main sink of the upper and of the lower blade (centroid of what stands above half the peak).
- `GU`, `GL`: the source nearest each main sink on the way to the other blade (the same row when there is one source).
- `u` = (row − U) / (L − U): blade to blade. `v` = distance from the blade's source / distance from the source to the main sink:
  within a blade, from the source outward; the two blades are folded onto this axis and averaged.
- Size: CSD divided by the recording's own main sinks.

Check on each recording: row 4 of its quality-check page shows the landmarks and the recording against its group's mean.
In the six recordings where DS1 and DS2 are separable, DS1's sink centroid sits 1.2 to 2.4 times as far from the source as DS2's.

## DS3

- Ours (in the room and in rows 1-3 of the pages): relative sink = (outer − middle) / (outer + middle), each the sink at one
  contact averaged over ±3 ms; within ±0.5 = DS3; outer and middle are where DS1's and DS2's mean sinks peak under the classifier
  in use, in the blade where they differ most; events whose two sinks together are under the 99th percentile of the same sum
  40 ms away are left unscored.
- The paper's (Tarcsay et al. 2025, bioRxiv 10.1101/2025.10.27.684857; full text read through Europe PMC, PMC12636346): the same
  index and the same ±0.5; outer and middle are placed from the mean CSD of the events in the two extreme quarters of PC1 (the
  contact with the deepest sink in each); probes with 20-25 µm between contacts. `normcurves.literature_ds3` does this one blade
  at a time. On this 50 µm probe the two contacts usually land 50 µm apart and most events score as DS3; where the two quarters'
  sinks peak at the same contact the layers cannot be placed at all.

## The battery

- `harness.py`: every measure (one number per recording) gets the same contrasts: PTEN against control; against % knockout
  within PTEN (exact Spearman) and over all mice; high-knockout (15%+) and low-knockout (under 10%) PTEN against control; the
  ordered trend control, low, high; IED+ against IED−; each against control; the ordered trend control, IED−, IED+; and the spread
  (Brown-Forsythe). Two-group tests are Mann-Whitney with Welch t and Brunner-Munzel beside them. Raw two-sided P.
- `measures.py`: four families. Timing (rates, intervals, bursts, order of types, drift, theta), waveform (sizes, durations,
  asymmetries, latencies, their spread across events), laminar (landmark distances, source against sink, the normalized profile
  point by point, sink position and width, DS1 against DS2 on the folded axis), structure (separation index of each classifier and
  per blade, shares, DS3, agreement between classifiers, one cloud or two on the PCA plane, the overlap matrix, the paper's DS3).
  Type-specific measures are made for every eligible classifier and for DS1, DS2, the minority, the majority and DS3, on both
  event sets. 12,184 measures, 121,251 tests.
- `analyze.py`: Benjamini-Hochberg over all tests, within contrast, and within family and contrast; a family-wise P per contrast
  from 2,000 shuffles of the mouse labels over all measures at once (it allows for the measures being correlated); for each test
  the same measure on the other event set and across classifiers; each measure's rank correlation with event count, recording
  length, year, bad contacts, band size and blade distance.

### What it found

- After correction nothing stands: no test has q under 0.10 over all tests or within its contrast, none has a family-wise P under
  0.10, and in no contrast do more measures look strong than under shuffled labels (closest: IED+ against IED−, P = 0.08).
- Raw P under 0.05 in 3.7% of tests (5% is chance; many tests are exact tests on small groups, which run conservative).
- The ten leads picked from the uncorrected table are in `top10.json` (with the reasons) and drawn in
  `Top10_leads_UNCORRECTED.pdf`. They were picked for effect size, holding on both event sets, not needing a classifier, not
  tracking event count or year, and making biological sense; not for the smallest P.

## Round 11 (2026-11-17): what changed and why

Asked by the user after round 10: take out m6; leave the separable / not separable call to them; no folded or "main sink"
figures; one normalized figure of DS1 and DS2 without DS3; check why m2, m60, m13, m3, m5, m34 have more DS1 than DS2 and
whether DS3 works; a sanity check per group; the battery again; each lead explained from the waveform up.
Round 10 (code, tables and every PDF) is in `archive_round10_2026-11-17/`.

- **m6 is left out** of everything (`dsdata.EXCLUDED`: confounding factors during the experiment). Control is now m2, m21,
  m22, m26, m59, m60, m61 (m51 has 5 events, as before).
- **Names checked against the anatomy** (`dsdata.Rec._name_check`, applied on load): DS1 must be the type whose sink sits
  farther from the cell layer. Each type's mean CSD at the DS peak; in each blade, the centroid of the deepest sink lobe on
  the far side of that blade's source, past the band by 5 contacts; distance from the source in µm. Over both blades DS1
  must be 25 µm (half a contact) or more farther out, and no blade may say the opposite by 25 µm. Verdicts per classifier and
  recording: ok, swapped (renamed; Jarvis's labels kept as `labels[clf]["types_jarvis"]`), same place, blades disagree (left as
  Jarvis named them). Halo set: 200 ok, 27 swapped, 28 same place, 9 blades disagree over the eligible classifiers. Under the
  classifier the pages use, one recording was swapped (m13) and one is "same place" (m3). Why Jarvis swaps: its rule
  (`backend/dspca.tort_order`, tortlab's CSDbC) takes the deepest sink above the largest source; when both types share that
  contact it redoes it on the flipped profile, which lands in the lower blade, and there "the shallower sink first" picks the
  inner (middle-layer) sink as DS1. Not changed in Jarvis.
- **DS3 layers looked for past the band** (`dsdata.Rec._ds3_widened`, `Rec.ds3(clf)` default): the outer and middle contacts
  are where DS1's and DS2's mean sinks are deepest, searched on the far side of each blade's source and 5 contacts past the
  analyzed band (Jarvis searched inside the band only, so a DS1 sink beyond the edge was missed). Outer = the contact farther
  from the source. Score, ±0.5 rule and the 99th-percentile floor 40 ms away are as before. The Jarvis version stays
  available as `Rec.ds3(clf, which="jarvis")`. It changed DS3 in a few recordings only (m26 50 → 0 events; m33, m7 slightly).
- **Sanity check** (`make_sanity.py` → `round11/Sanity_check_CTL.pdf`, `Sanity_check_PTEN.pdf`): per recording, each
  type's mean CSD down the whole probe, the counts before and after DS3, every event's sink at the outer against the middle
  contact (the DS3 rule drawn as a wedge, the noise floor as a corner), and the DS3 score histogram, with plain-word reading.
  Findings: more DS1 than DS2 in m2, m22, m60, m5, m34 because the best classifier split off a small group whose sink sits
  nearer the cell layer than the rest (the rest is then correctly the "farther out" type); in m13 the names were swapped; in m3
  the two types' sinks are at the same place (names arbitrary, DS3 unscorable). DS3 follows its rule but in most recordings
  cannot do its job: the two contacts sit inside one sink 150–400 µm wide (contacts 50–150 µm apart), so 58–90% of events
  score DS3; where DS1 is a small far-out group (m26, m61, m33, m1, m7, m28) most DS1 events have their two-contact sink under
  the noise floor and can never be scored, so DS3 there comes only from DS2.
- **One normalized figure** (`make_averaged2.py` → `round11/Averaged_DS1_DS2.pdf`, replaces round 10's `Averaged_*.pdf`):
  DS1 and DS2, DS3 taken out, on the blade-to-blade depth (0 / 1 = where the recording's average DS has its deepest sink in
  the upper / lower blade), size in units of that average sink, the same for both types. Pages: control, PTEN all, IED−, IED+
  (each with every recording drawn beside the mean and its index), and the groups overlaid with cluster permutation tests.
  No folded axis anywhere. `normcurves.typed_u` makes the curves.
- **No verdict words**: "separable" is gone from every page and table; the separation index is shown instead. The 0.45 rule
  is only used inside the code to choose each recording's best eligible classifier as before (eligible = each type 5% or more).
- **Quality check round 11** (`qc_source/deep_qc11.py` → `round11/quality_check/`): m6 page dropped; names by anatomy in every
  row; DS3 from the widened layers; row 4 is the one normalized figure for that recording against its group.
- **Battery, run 2**: the same four families with m6 out, names checked, DS3 from the widened layers, and two new variants for
  every type-specific measure: `ds1x` and `ds2x` (DS1 and DS2 with the DS3 events taken out), plus DS1x / DS2x ratios.
  `n_classifiers_separable` was dropped (a verdict count).

### Run 2 (2026-11-17)

- 17,302 measures, 160,245 tests (m6 out; names checked; DS3 from the widened layers; `ds1x` / `ds2x` added).
- Raw P under 0.05 in 4.1% (5% is chance). After correction: one test has q under 0.10 over all tests (q = 0.06) and none has
  a family-wise P under 0.10. That one test is an LFP measure, and it is an artifact (below). No contrast has more strong
  measures than shuffled labels give (closest again IED+ against IED−, P = 0.069).
- **LFP measures are unreliable across mice.** The LFP's sign at the cell-layer source at the DS peak runs from −425 µV (m28)
  to +886 µV (m60): the whole profile is shifted by the reference. Every LFP measure that looks for an LFP peak (`lfp_src`,
  `lfp_fwhm`, `lfp_asym`, `lfp_pre`, `lfp_post`, `lat_sink_minus_lfp`, `lfp_pos_u`, `lfp_profile_u_*`) mixes that shift in. The
  surviving test (`laminar|lfp_pos_u_median|v8|delta_bottom|ds2x`, spread PTEN against control) separates exactly the mice
  whose LFP is negative between the blades. Re-reference the LFP before using any of these. CSD measures are not affected
  (the CSD removes a common offset).
- Leads: `leads.json` (nine leads and the appendix), drawn by `make_leads.py`. Classifier-free (all events, so DS3 does not
  enter): sink size more uniform in IED+; upper blade's sink weaker with high knockout; source/sink ratio more variable with
  knockout; source–sink peak-time jitter with knockout; net source between the blades falls with knockout (within PTEN);
  source-to-sink distance longer in IED+. With DS3 removed: DS2's upper sink smaller in every PTEN mouse; DS2's source briefer
  with knockout; DS2's sink nearer the cell layer in IED+. Several track the year of recording (all PTEN 2023–2024, three
  controls 2025); each page says which.
- `make_top10.py` / `top10.json` are round 10's and are kept only for the record.

### Run 3 (2026-11-17, later): filters, no cutoff, more leads

- **Third event set, the 10% grace set** (room version 7, 4,201 events; a border drawn around the control pool with 10%
  grace), extracted read-only with `qc_source` scripts (`deep_extract.py 7`, `*_7.py` copies) and frozen as `data/ds_v7.pkl`.
  The room has no unfiltered set: the Halo set (v6) is the loosest border; No P-spikes (v8) = v7 less 24 events inside the
  P-spike border. Every measure now runs on all three sets.
- **No-cutoff variants** (`measures.NOCUT`): `ds1n`, `ds2n` (and `ds1nx`, `ds2nx` with DS3 removed) for every classifier,
  eligible or not, with a type counted at any size; `best_nocut` = the classifier with the highest index whatever its type
  sizes; DS1n/DS2n ratios.
- **Filter family** (`measures.run_filter`): per mouse, the share of Halo events the 10% grace border keeps, the share removed as
  P-spikes, and every CSD feature on the dropped against the kept events (events matched by time, 5 ms).
- 39,637 measures, 377,497 tests. Raw P < 0.05 in 3.9%. After correction 4 tests have q < 0.10 over all tests; all four are
  spread (Brown–Forsythe) tests, three on values tied across controls and one the LFP artifact. No family-wise P under 0.10;
  no contrast beats shuffled labels (closest IED+ against IED−, P = 0.086). Within its family, the share of Halo events the
  stricter border keeps falls with knockout (q 0.04), which is largely by construction (the border was drawn on controls).
- **Leads**, all built the same way by `make_leads.py` (where it is read → one event → every event → the result), now with
  Theil–Sen correlation lines and 95% bootstrap bands on the knockout panel and off-scale recordings drawn at the edge with
  their value (more than 3 interquartile ranges out; left out of the lines):
  `leads.json` (main nine + LFP appendix; lead 7 reframed as DS2's blade balance: the lower blade's sink is the larger share in
  IED+, since in absolute size the lower sink is not larger), `leads_ds3.json` (5), `leads_filter.json` (5),
  `leads_general.json` (10 leads on all events, no DS type). New build-ups: timing (raster, intervals), mean profile, DS3
  scoring, filter (kept / dropped).
- **Averaged document**: a page on how far apart DS1's and DS2's sinks sit (IED− 239 µm, control 193, IED+ 142 median; IED−
  against IED+ P = 0.063, against control P = 0.41), and a no-cutoff version (`python make_averaged2.py nocut` →
  `round11/Averaged_DS1_DS2_no_cutoff.pdf`).

## Running it again

```
cd battery
python build_dataset.py 6 ; python build_dataset.py 8      # only if the room changed (needs the qc_source outputs remade first)
python make_averaged.py        # round10/Averaged_*.pdf, results/cluster_tests.json
python make_table.py           # round11/Summary_table.*
python make_supplement.py      # round11/Supplemental_figures.pdf
python measures.py             # results/*.pkl, about 5 minutes
python analyze.py              # merged/*.pkl, about 1 minute
python make_reports.py         # battery_reports/...
python make_sanity.py          # round11/Sanity_check_CTL.pdf, Sanity_check_PTEN.pdf
python make_averaged2.py       # round11/Averaged_DS1_DS2.pdf (replaces make_averaged.py)
python make_leads.py           # battery_reports/uncorrected/Leads_*.pdf, all four lead sets (after analyze.py)
python make_averaged2.py nocut # round11/Averaged_DS1_DS2_no_cutoff.pdf
python qc_source/deep_qc11.py  # round11/quality_check (reads the files beside it)
```

## If this goes into Jarvis later

- The landmarks and the two axes (`dsdata.Rec._landmarks`, `u`, `v`) are small and self-contained; they need only the mean CSD
  at the DS peak, the band and the hump cut the room already has.
- `normcurves.literature_ds3` is the paper's DS3 procedure, ready to sit beside `backend/dsmix.py`.
- The two Gaussian-mixture classifiers and the index-optimized boundary on the PCA plane are in `qc_source/deep_pca2.py` and
  `deep_opt.py` (the to-do banner in the Extraction Room refers to these).
- The quality-check pages show that the analyzed band often stops short of the outer (DS1) sinks; widening the band at
  extraction is the first thing to try.

## Known limits

- 17 recordings; IED status and knockout dose are nearly the same split; three of eight controls were recorded in 2025 and every
  PTEN mouse in 2023-2024.
- Events are the dentate spikes inside each recording's detection border, not all of them; rates and size spreads inherit that.
- The two event sets are two cuts of the same recordings, not independent data: "holds on both" is a robustness check, not a
  replication.
- DS1 / DS2 names are arbitrary in the 11 recordings where the events are one cloud.

## Run 4 (2026-11-18): the user's notes

Asked in a Google Doc of notes on the run 3 lead pages.

- **One classifier per recording, "the winner"** ("We had the winner. Keep those winners and vary everything else"). `dsdata.Rec._set_winner`: of (1) the best eligible room classifier, (2) the best conventional classifier on the PCA plane, (3) the index-optimized curve, the one whose DS1 and DS2 separate best once DS3 (relative sink within +-0.5) is taken out, each type 5 events or more; a tie within 0.005 goes to the lower row. This is the row the round 11 quality check marks FINAL OPTIMIZED SEPARATION. It is stored as the pseudo-classifier `"winner"`. Every type-specific measure uses it; the measures that compare classifiers (agreement, index over classifiers, no-minimum variants, optimized-minus-best) are not made (`measures.WINNER_ONLY`; `BATTERY_ALL_CLASSIFIERS=1` restores run 3). On the No P-spikes set every event keeps its Halo-set type and DS3 call, matched by time within 5 ms.
- **Between the blades without the sinks** ("the rows in between include the sinks"): landmarks `src_rows` run from where the average CSD at the peak turns >= 0 below the upper main sink to where it is last >= 0 above the lower main sink. `net_between` and the lead pages use these rows.
- **No absolute distances or amplitudes as leads** (probe placement differs between mice): lead lists leave out measures in um, uV or CSD units unless they are a CV, skew or percentile ratio. Lead 6 of run 3 (source-to-sink distance) is gone: where one source sits between the blades ("one peak, not two") the per-blade distance has no meaning.
- **Event sets**: v7 (10% grace) and the border "filter" family are dropped (the user meant frequency filters on the waveforms, not dropping events). SETS = v6, v8.
- **LFP and the reference**: the run 3 appendix called the LFP-peak-position result a reference artifact. That was wrong: a reference adds the same voltage to every contact and cannot move where the LFP is largest (checked: a common-median reference leaves every recording's position unchanged). Every recording's .ncs headers show the same setup: "External Hardware Reference" on 63 channels, CSC59 referenced to AD channel 43 (CSC59 is a bad contact in every recording). m2's headers list a 300 Hz DSP low cut although its LFP is as large as the other mice' (to ask the lab).

Run 4: 1,378 measures, 13,200 tests (v6 + v8). Raw P < 0.05 in 4.1%. No q < 0.10 over all tests or per contrast; one q (family) < 0.10 (iei_cv2 of DS2 without DS3, within PTEN, P 0.0002 on the Halo set but 0.98 on the No P-spikes set); no family-wise P < 0.05. No contrast has more hits than shuffled labels (closest IED+ against IED-, P 0.15).

Leads: `leads.json` (9), `leads_ds3.json` (5, the fifth a "not a lead" page on the DS3 share), `leads_general.json` (10). Picked as: raw P < 0.05 on the Halo set, same sign and P < 0.10 on the No P-spikes set, no absolute distances or amplitudes (scratchpad `shortlist4.py`).
