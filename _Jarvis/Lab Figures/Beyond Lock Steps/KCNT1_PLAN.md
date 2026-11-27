# Redoing the pipeline for KCNT1

The plan for running PIPELINE_PTEN.md on the KCNT1 (Y796H) awake recordings. The user decided four things on 2026-11-27;
everything else below is a recommendation, and the items under "Ask the user first" are the user's call.

## The user's decisions (2026-11-27)

1. **Same 8 questions, gene dose in place of % knockout.** Jeremy's eight menu questions are asked again with genotype
   as the dose: WT = 0, Het = 1, Hom = 2 mutant alleles. **WT against Hom is the priority pair.** The **tight layers**
   (layer check, 2026-11-25) are the main layer rule, with the menu's old rule shown beside them. Add a **female-only
   check** because sex is confounded with genotype.
2. **Reuse the PTEN IED border.** The Ambiguous workflows take PTEN's P-spike border, workflow `4e5ce690d4b1` v2
   (39 hand-sorted IEDs from five PTEN IED+ sessions), unchanged.
3. Heavy data lives on netfiles (README, Data); code and notes in this folder.
4. The PTEN outputs stay where they are (OUTPUTS_INDEX.md).

## What is known about the KCNT1 mice (2026-11-25)

From the lab's "PTEN/KCNT1 Dentate Spike Data" sheet, tab "KCNT1 Recording Sessions". Genotype is column **YH**; Sex and
Prio. sit next to it. Screenshots of the sheet are usually filtered, so read the whole sheet.

| state on 11-25 | WT | Het | Hom |
|---|---|---|---|
| Locked | 1619, 531, 526 (all F) | 1609, 1606, 576 (all M) | 1603 s2, 306 (both F) |
| Panning done, Lock not done | | 530 (F) | 1604 s2 (M), 310 s2 (M) |
| still being curated | 529 s1, 591 s2 (waiting on RY Review) | 1616, 577, 524, 520, 521 | 588 |

- WT is the bottleneck. Every WT candidate is female and every Locked Het is male, so a female-only check is the only
  clean handle on sex (WT against Hom is female against female today).
- WT 523 and 525 are recorded but marked as not uploaded.
- Advice already given to the user: Lock the three Panning-done sessions first (WT 3 / Het 4 / Hom 4).

## Ask the user first

These change what gets built, and some write to shared lab data.

1. **Which sessions, and which one per mouse.** Read the sheet's Lock column now (it will have moved since 11-25) and agree
   the list: one baseline recording per mouse, as for PTEN.
2. **The probe of every session.** The whole pipeline assumes a 64-contact H3 in one line, 20 um apart. Read each
   session's `CheetahLogFile.txt` for the config it loaded: `Cheetah2026-06-01_wheel_H3.cfg` is the H3; the H10-D configs
   (for example m531 s2 to s7) map channels differently and are not a single line of contacts. Do not put a non-H3
   session through the battery; tell the user which sessions are affected.
3. **The duplicate-stamp fix.** Run the PTEN rule (Spike neighbors under 10 ms apart are one event; the largest CSD sink
   stays) as a dry run and show the user the pairs before applying; applying writes new versions of shared curation sets.
4. **An IED or seizure grouping.** PTEN had IED+ / IED- from the sheet. If the sheet has a KCNT1 equivalent, it becomes
   the second grouping (and question 7's "same mice" set); otherwise questions 7 and 8 compare within the mice that have
   BTs or IED-class events (a floor such as 5 events) and against WT DS.
5. **Where the KCNT1 sets live in the Extraction Room.** The room list is `ROOMS = (("dentate_spike", "Dentate Spike"),)`
   in `backend/extraction.py`, and every PTEN set is a version of that one room. A second room (for example
   `("dentate_spike_kcnt1", "Dentate Spike KCNT1")`) keeps the projects apart but is a Jarvis code change; new versions of
   the PTEN room would mix them. Recommend the second room and ask.
6. **ML targets.** `backend/er2/engine.py` has PTEN targets only. KCNT1 needs new ones (suggested: `dose` as a rank
   target 0/1/2, `wt_vs_hom`, `wt_vs_mut`, `geno3`). That is a Jarvis code change too.
7. **The question wording.** The menu quotes Jeremy word for word. For KCNT1, either reuse his wording with "% KO" read as
   "gene dose" (say so on the cover), or ask for new wording.
8. **The depth bands per card** in the Extraction Room were set by the user by hand for PTEN. Ask the user to set them, or
   use the default band (the edges of the two bottom sinks) and say so.

## The steps

Follow PIPELINE_PTEN.md step by step; only what differs is written here.

### K0. Inputs
- Each session's pooled (Confluence) entry at its newest Lock version. Check that the newest version really is Lock's (the
  m1 s2 trap: a later bank-on-leave version can undo an alignment; `aud1.py` to `aud4.py` show how it was checked).
- Note each mouse's genotype, allele dose, sex, age at recording, recording date and probe config in one table; it becomes
  `meta.json` for the battery.

### K1. Root Canal
- Read every session with the **same Optimized parameters** as the PTEN pools (copy them from pool `3561fc988afd`'s
  saved params: 10 to 150 Hz, order 3, 60 Hz mains out, peak window 33 ms, fast power 240 to 420 Hz, cross 75 ms). The
  reused IED border only means something if KCNT1 events are measured exactly the way the border's events were.
- Pools: "KCNT1 WT Baseline (Optimized parameters)" (WT only) and "KCNT1 WT, Het and Hom Baseline (Optimized parameters)"
  (every session).
- DS borders: Snap (convex hull), 5% and 10% grace, drawn around the **WT** pool, applied to the all-genotype pool.
- Halo set: Ambiguous workflow with `uses = {"ds": <KCNT1 5% DS workflow>, "pspike": {"artifact_id": "4e5ce690d4b1",
  "version": 2}}`, target the all-genotype pool, then the halo at reach 2 and margin 1.5. Keep `ds` + `halo_ds`.
- Strict set: the same with the 10% DS border and no halo. Keep `ds`.
- Bank both as Root Canal bundles, as for PTEN.
- **Check the reused border and report it:** counts of DS, BT and IED class per mouse and genotype; the 3D cloud of
  amplitude, half-width and fast power with both hulls. If WT mice put many events in the IED class, the PTEN border does
  not transfer; tell the user rather than working around it.

### K2. Extraction Room
- X-ray Many folder per set (from the Halo and Strict workflow runs), read, depth band per card, extract a room version.
- DS1 / DS2 / DS3 as for PTEN (15 split methods, Bite line default, eligibility 5% and 5 events, DS3 at +-0.5).

### K3. Freeze
- Make a KCNT1 copy of the battery folder (the netfiles mirror's `DS_PTEN_figures_2026-11-16/battery`, code only) and
  of the deep scripts; never edit the PTEN copy.
- `deep_extract.py`: it reads room `dentate_spike` and sets `g = "CTL" or "PTEN"` and `ko` from the room. Point it at the
  KCNT1 room and carry genotype instead.
- `build_dataset.py`: replace the `IED` and `NOTES` dicts; `group` = WT / Het / Hom, `ko` = allele dose 0 / 1 / 2 (keep the
  field name so the rest of the code runs, or rename it everywhere), `subgroup` = the IED grouping if there is one.
- `dsdata.py`: `EXCLUDED` empty unless the lab says otherwise; the H3's 20 um spacing.

### K4. Battery
- `harness.py` `CONTRASTS`: replace the PTEN set with: dose over all mice (Spearman, Kendall, Pearson on 0 / 1 / 2);
  WT against Hom; WT against Het; Het against Hom; WT against mutant (Het + Hom); three groups (ANOVA, Kruskal-Wallis,
  ordered trend WT < Het < Hom); spread (Brown-Forsythe, WT against mutant); and the female-only dose trend. Keep the
  IED contrasts only if the lab has an IED grouping.
- Run in the order of `run5.sh` and `strict_all.sh` (filter reads, before / after reads, measures, analyze, reports, leads).

### K5. Machine learning
- Amber bundle from the KCNT1 battery folder; runs with the new targets; leave one mouse out.
- With 8 to 11 mice the 0.80 bar is easy to clear by luck: always run the random-twin runs beside the per-type runs and
  report how many models clear the bar in each.

### K6. Best fit
- Winner classifier per recording: the same rule, fixed before any group test.
- Models: the count at the bar per target, the best model, and per-mouse held-out calls, as in the follow-up report.

### K7. Menus and reports
- Copy `code/menus` to a new scratch folder. Replace the PTEN constants: the mouse list (`LABS16`), group lists, IED
  lists, knockout values and `BATTERY` path in `stats_lib.py`, `menu_data.py`, `j1_battery.py`, `j2_freq.py`,
  `jpages.py`, `jfollow.py`; and the gid list in `m0_data.py`.
- Layers: build `tight_layers.json` for the KCNT1 mice first (`tight_layers.py`), run `j1_battery.py` and `j2_freq.py`
  with `JM_LAYERS=tight` for the main pages, and once without it for the old-rule column (layer_check.py shows how both
  are drawn side by side).
- Pages: the Jeremy menu's format (kicker; "Jeremy Asked: <question>"; "Results show: <answer>"; panels whose headings state the
  finding), plus the follow-up pages (held-out calls, DS / BT / IED counts per mouse and genotype, measurement windows,
  layer definitions) and CONCERN / RESOLVE supplements where a reader could misread a result.
- Output: `Lab Figures/KCNT1_DS_<name>_<MMDDYY>` (PDF, pages, tables, code, README).

### How the eight questions map

| # | PTEN question (Jeremy's words) | KCNT1 version | main contrasts |
|---|---|---|---|
| 1 | Does the %KO cause changes in synaptic efficacy for dentate spikes | Does gene dose change DS synaptic efficacy | dose trend; WT against Hom |
| 2 | Are there group differences in DS1 vs DS2 (do they make both) | the same, by genotype | three groups; WT against Hom |
| 3 | Differences in CSD sink for MML/OML by blade by % KO | the same, by gene dose, tight layers (old beside) | dose trend; WT against Hom |
| 4 | Differences in dominant frequency for MML/OML by blade by % KO | the same, by gene dose | dose trend; WT against Hom |
| 5 | Do results of 3 and 4 change when you open filters | the same | every filter band |
| 6 | Can you predict which mice made the abnormal dentate spikes based on %KO | based on genotype | ROC with dose as the score |
| 7 | Do the results change when you sort the dentate spikes by where they fall in the continuum | DS, BT and IED class within the mice that have them, and against WT DS | paired within mice; against WT |
| 8 | Do the results of 7 change when you open the filter | the same | every filter band |
| + | Every mouse in the Strict workflow, table and aggregate | the same | |

## Things that differ from PTEN and must be said on the pages
- Few mice per genotype (2 to 4), and sex confounded with genotype.
- The IED border was built on PTEN IEDs; KCNT1 BT and IED-class counts depend on that choice.
- Most KCNT1 sessions were recorded in 2026 with the H3 wheel config; the PTEN recordings are from 2023 to 2025. Do not put
  KCNT1 and PTEN mice in one test.
