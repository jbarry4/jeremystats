# The PTEN dentate spike pipeline, from Lock to the menus

What was done to the PTEN baseline recordings between 2026-11-05 and 2026-11-25, step by step, with the ids, settings,
scripts and outputs of each step. Steps 1 and 2 run inside Jarvis (the app in this repo). Steps 3 to 8 run outside it,
in plain Python scripts that only read Jarvis. Script names refer to `code/` in this folder; `code/SCRIPTS.md` lists
every script with its own one-line description, and `PATHS.md` lists every hard-coded path.

Mice (one baseline recording each; the unit of every test is the mouse):

| group | mice | notes |
|---|---|---|
| control (CTL) | m2, m21, m22, m26, m59, m60, m61 | m6 is excluded by the lab ("confounding factors during the experiment"); m51 has 5 events and is left out of statistics |
| PTEN IED- | m8, m33, m1 (3.9 to 5.2% knockout), m7 (24.1%) | m7 is IED- at a high knockout; it is drawn as a diamond and tested as an outlier |
| PTEN IED+ | m13, m28, m3, m5, m34 (18.9 to 28.4%) | IED+ mice are also the high-knockout mice, so IED status and dose overlap |

Probe: Cambridge H3, 64 contacts in one line, **20 um apart**. Some early documents used 50 um; every distance they give is
2.5 times too large (ratios and P values are unaffected). Jarvis's H3 template (`backend/probes.py`) also says 50 um, so
CSD magnitudes inside Jarvis are 6.25 times too small for these mice.

---

## Step 0. What "after Lock" starts from

The Confluence (Junction, Panning, Lock) is upstream. Its output per recording is a **pooled** Event Bank entry
(Incisor and Doppler events merged, sorted by a person in Panning into Spike / Garbage / Flag, then aligned by Lock).
Everything below uses each recording's pooled entry at its **newest version**.

Two repairs were made to those entries before the final runs (both are part of the PTEN record):

- **m1 s2 (entry `bfa98498290b`).** Panning's bank-on-leave had written a version that undid Lock's alignment.
  `code/pipeline_scratch/fix_m1.py` replayed Lock pass `br1f1b0830ec` as a new aligned version (v4). Bank-on-leave was
  switched off on 2026-10-26.
- **Duplicate stamps.** A +-200 ms Braces pass had put two stamps on one peak in 14 sets. Rule (the user's): Spike
  neighbors under 10 ms apart are one event; the stamp with the largest CSD sink (+-2 ms) stays a Spike and the other
  becomes Garbage (ties: the earlier stays); neighbors 10 to 20 ms apart are two real events. 103 stamps became
  Garbage, each set got a new version tagged "dedupe" (`dedupe.py`, dry run unless `--apply`; drawn for checking by
  `dups_fig.py`).

Checks used: `aud1.py` to `aud4.py` (does every pool member sit on the newest Lock version; do battery times match the
pool stamps within 0.5 ms).

---

## Step 1. Root Canal: borders, the Halo set and the Strict set (inside Jarvis)

Root Canal measures three numbers per event and draws borders around known groups in that 3D space:

- **amplitude** (max amplitude in a 33 ms window, `win_ms` 33, after a 10 to 150 Hz filter of order 3 with 60 Hz mains out),
- **fast power** (`hf`, 240 to 420 Hz; `cross_ms` 75),
- **half-width** (`hw`).

These are the "Optimized parameters". They came from the **Meta Workflow** (`backend/rcmeta.py`; instances
`21486d872fcf` at 5% and `d354491b0eee` at 10%), which searched the amplitude filter band, the peak window and the HF band
for the setting with the fewest events inside both the DS and the P-spike border. The HF band alone took that count from
1,334 to 72.

**Pools** (a pool = Root Canal reads of several recordings' Lock entries, fitted together):

| id | name | what |
|---|---|---|
| `07cdcb084c86` v2 | CTL Baseline v2 (Optimized parameters) | the 9 control recordings: the DS border is drawn around these |
| `3561fc988afd` v3/v4 | CTL & PTEN Baseline v2 (Optimized parameters) | all 18 recordings, 5,100 events: the target every border is applied to |
| `105b40acbbb0` v3 | PTEN Baseline v2 | the 9 PTEN recordings |

**Borders** (each is a workflow whose border is a **Snap**: the convex hull of the group's events, with a grace = the share
of the group's own events left outside, peeled from the most outlying in):

| workflow | border | drawn around |
|---|---|---|
| `178daabb125c` v3 | DS border, 5% grace | every event of the control pool (the premise: every control event is a DS) |
| `4a29af93e601` v3 | DS border, 10% grace | the same, stricter |
| `4e5ce690d4b1` v2 | P-spike (IED) border, 5% grace | 39 hand-sorted IEDs from 5 sets: m3 s2, m5 s2, m13 s2, m28 s2, m34 s5, each aligned in Eye |

Box borders were tried first; Snap gave the fewest in-between events. A "Scoop" (robust ellipsoid) was retired; never
offer it again.

**The two event sets** are Ambiguous workflows: both borders applied to the target pool. Classes per event:

| stored class | meaning | figure name |
|---|---|---|
| `ds` | inside the DS border only | DS |
| `halo_ds` | outside both, captured by the DS halo | DS |
| `both`, `halo_amb` | inside both borders, or in either halo without a clear side | BT (borderline transient); "Twilight Zone" in the app |
| `pspike`, `halo_pspike` | inside the P-spike border only, or captured by its halo | IED class (red); "P-spike" in the app |
| `neither` | beyond both halos | outside both |

**Halo** (asked 2026-11-12): each border's gauge measures how far out an event sits in units of that border's size about its
center (1 = on the border). An event outside both borders is captured by a side when its gauge is at most **reach 2** and
it is **margin 1.5** times nearer that side; otherwise, inside either halo it is BT; beyond both it is outside both.

| set | workflow | recipe | events | room version (battery slot) |
|---|---|---|---|---|
| **Halo** (main) | `6fa7fef7b7a3` v4/v5 | 5% DS border + P-spike border + halo 2 / 1.5; keep `ds` + `halo_ds` | 4,733 in 18 recordings (ds 4,381 + halo_ds 352) | v9, later v11 (battery `v6`) |
| **Strict** (check) | `a7eee6a6ca9f` v3/v4 | 10% DS border + P-spike border, no halo; keep `ds` only | 3,905 in the 16 analyzed recordings | v10, later v12 (battery `v8`) |

Halo run counts (all 18 recordings): ds 4,381, halo_ds 352, both 79, halo_amb 106, pspike 137, halo_pspike 17, neither 25.
Strict run counts: ds 4,098, both 24, pspike 192, neither 783.

Banked as Root Canal bundles on 2026-11-21: Halo `a9cf6f2c30c2`, Strict `5469cb7ad2ae`, DS 5% `2d2dcc5d66b2`, DS 10%
`3a2a58a49d65`, P-spike `204dc5977f79`.

**How it was driven.** The user built pools and workflows in the Root Canal UI. Reruns went through the app's routes, from
scripts that either call the running app over HTTP (`http://127.0.0.1:8733`) or load it in-process
(`from backend.app import app; c = app.test_client()`):

- `/api/rootcanal/read` (read one entry; a forced read is needed after a dedupe), `/api/rootcanal/pool/fit`,
  `/api/rootcanal/pool/save` (`p2.py`, `p3.py`)
- `/api/rootcanal/workflow/save` with a body like
  `{"kind": "ambiguous", "nickname": "<name>", "uses": {"ds": {"artifact_id": "4a29af93e601", "version": 2}, "pspike": {"artifact_id": "4e5ce690d4b1"}}, "target": {"artifact_id": "3561fc988afd"}}`
  (`strict_set.py`)
- `/api/rootcanal/workflow/<id>/run` with `{"refresh": true}` (picks up the newest pool and P-spike set versions)
- `/api/rootcanal/workflow/<id>/halo` with `{"version": v, "reach": 2, "margin": 1.5}` and `/workflow/<id>/bank`
  (`halo_apply_real.py`)

Read parameters, pools and workflows are artifacts and sync between machines. The reads themselves are machine-local cache
(`GUI_logs/.cache/rootcanal`), copied to the VACC shelf `Jarvis Data/_answers` by the running app.

---

## Step 2. Extraction Room: every event read down the probe, DS1 / DS2 / DS3 (inside Jarvis)

1. **X-ray Many folder** per set (`/api/dspca/many/folder` with `{"name", "source": {"artifact_id": <workflow>, "version"}}`).
   Its members are each recording's kept events (`xraymany.inside_by_gid` takes `ds` + `halo_ds` for an Ambiguous run).
   Folders: Halo `xm-b2d963ef1c`, Strict `xm-7d6c8cfb0b`.
2. **Read** (`/api/dspca/many/read`, one job per folder, about 6 minutes a recording): X-ray reads every event's
   whole-shank LFP and CSD (DS band 5 to 100 Hz with a notch).
3. **Depth band per card.** The user set each recording's band by dragging on its average CSD (default: the edges of the
   two bottom sinks). Bands, separable calls, splits and flips are shared prefs keyed `dentate_spike|<folder>|<gid>`; when a
   set is replaced they are copied to the new folder (`p4.py copy`).
4. **Extract** (`/api/extraction/extract` with `{"room": "dentate_spike", "folder", "direct": true}`): the room's next
   version (room artifact `980b57eab496`). Halo = v9 then v11; Strict = v10 then v12 (v11 equals v9 and v12 equals v10,
   recording for recording). `p4.py check` compares each card's stamps with the workflow's kept stamps.
5. **DS1 / DS2 split.** Compare splits has 15 methods: Bite line, PCA, PCA + gap, Delta, Delta Middle, each on both sinks,
   the top sink alone and the bottom sink alone. **Bite line** (the default) is a sink-overlap normalized cut on the
   recording's two sink humps. The **separation index** = 1 - mean overlap between types / mean overlap within types.
   A method is **eligible** when each type holds at least 5% of events and at least 5 events.
6. **DS3** (Tarcsay et al. 2025 relative sink): score = (OML sink - MML sink) / (OML sink + MML sink), each the sink at one
   contact over +-3 ms; within +-0.5 is DS3. Under the 99th percentile of the same sum 40 ms away = unscorable. On these
   recordings DS3 mostly reflects how close the two contacts are, so it is reported but never drives a claim.

Later scripts read the room in Python, never through the UI.

---

## Step 3. The freeze and the deep round (outside Jarvis, read only)

Everything the room holds is pulled into pickles, then frozen as one file per event set.

| script | writes | what |
|---|---|---|
| `deep_extract.py <room version>` | `deep_v<V>.pkl` | every event and recording the room holds |
| `deep_extra.py` | `deep_full_v<V>.pkl` (about 210 MB) | the whole shank per event (CSD and LFP) |
| `deep_pca2.py` | `deep_pca2_v<V>.pkl` | two Gaussian mixtures on the PCA plane (straight and curved boundary) |
| `deep_opt.py`, `deep_opt2.py` | `deep_opt*_v<V>.pkl` | boundaries chosen to maximize the separation index (whole band; mean of the two blades) |
| `deep_ds3.py` | `deep_ds3_v<V>.pkl` | the DS3 score under those extra classifiers |
| battery `build_dataset.py <V>` | `battery/data/ds_v6.pkl` (Halo), `ds_v8.pkl` (Strict) | the frozen set the battery reads (`dsdata.load`) |

`_10.py` copies of the deep scripts were used for the Strict room version. `run5.sh` renamed the v9 freeze to the `v6`
slot. `derive_v8.py` can instead cut the Strict set out of the Halo freeze by time (5 ms); the final Strict freeze was read
from the room (`strict_all.sh`), and the derived file is kept as `ds_v8_derived_from_halo.pkl`.

**Per-recording landmarks** (`dsdata.Rec.landmarks`, from the mean CSD of all events at the DS peak): U and L = the upper and
lower blade's main sink; GU and GL = the current source nearest each sink toward the other blade (the cell layer side).
Axes: `u` = blade to blade (0 = upper main sink, 1 = lower); `v` = within a blade (0 = its source, 1 = its main sink).
No lab layer labels are used anywhere.

**Names by anatomy** (`dsdata.Rec._name_check`): DS1 must be the type whose sink sits farther from the cell layer (25 um or
more over both blades, no blade saying the opposite by 25 um); otherwise the names are swapped (Jarvis's own rule,
`dspca.tort_order`, is backwards when both types share the upper sink contact; m13 was swapped).

**The winner** (`dsdata.Rec._set_winner`, the user's rule of 2026-11-18): one classifier per recording. Of (1) the best
eligible room classifier, (2) the best conventional classifier on the PCA plane, (3) the index-optimized curve, the one whose
DS1 and DS2 separate best once DS3 is taken out (each type 5 events or more; a tie within 0.005 goes to the lower row).
Every type-specific measure uses it. The Strict set keeps each event's Halo-set type, matched by time.

Quality-check pages (one per recording) were drawn by `qc_source/deep_qc11.py`.

---

## Step 4. The test battery (outside Jarvis)

Folder: `DS_PTEN_figures_2026-11-16/battery` (on netfiles; code also in `code/battery`). Its own `README.md` and
`METHODS.md` document every field; parts of them predate the 20 um correction.

- **Filter sets.** "Filter" means a frequency filter on the waveforms, never dropping events. `band_read.py` reads every
  Halo event again from the raw recording under several filters at once (`bandread9/`); `band_build.py` rebuilds the set
  per band as `data/ds_b_<band>.pkl`: `b_ds` (5 to 100 Hz main), `b_none` (notch only), `b_1_100`, `b_1_300`, `b_5_300`,
  `b_5_50`, `b_10_40`.
- **Before / after.** `around_read.py` reads +-500 ms around every Halo event and as many random moments (at least 1 s
  from any event) into `data/around/<mouse>.npz`; `around_measures.py` measures them.
- **Measures** (`measures.py`): four families. Timing (rates, intervals, bursts, order of types, theta), waveform (sizes,
  durations, asymmetries, latencies, their spread), laminar (landmark distances, source against sink, the normalized
  profile, sink position and width, DS1 against DS2), structure (separation, shares, DS3). One number per recording,
  median over events unless the measure is itself a spread, share or rate.
- **Harness** (`harness.py`, `Battery.add`): every measure through the same contrasts: PTEN against control; against %
  knockout within PTEN and over all mice; high (15%+) and low (under 10%) knockout against control; ordered trend control <
  low < high; IED+ against IED-; each against control; trend control < IED- < IED+; spread (Brown-Forsythe).
- **Analyze, reports, leads**: `analyze.py` (merged tables), `make_reports.py`, `make_table.py`, `make_supplement.py`,
  `make_sanity.py`, `make_averaged2.py` (and `nocut`), `make_leads.py <leads json>` (each lead drawn from one event up).

Run 5 (2026-11-19, the final one) is `run5.sh` for the Halo set and `strict_all.sh` for the Strict set; both list every
command in order. Outputs: `battery/merged*/measures.pkl` and `tests.pkl`, `battery_reports/`, `round11/`. The lab copy is
`Lab Figures/Archive/2026-11-23_DS_PTEN_112326`.

Rules the user set for this step: no absolute distances or amplitudes as leads (probe placement differs between mice);
"between the blades" excludes the sink lobes; m6 out; no "separable" verdict words on any page (show the index; the user
makes that call).

---

## Step 5. The machine-learning battery: Extraction Room 2.0 (Jarvis code, VACC compute)

Code in the repo: `backend/er2/` (amber, engine, nets, explain, typed), `backend/er2run.py`, `backend/er2routes.py`,
`web/js/extraction_er2.js`. Bundles and runs live in `%LOCALAPPDATA%\Jarvis\er2` (not in git; mirrored on netfiles as
`er2_store`).

1. **Amber bundle**: the battery folder frozen for the models, with the winner's DS1 / DS2 / DS3 calls fixed.
   `/api/er2/amber` with `{"source": <battery folder>}` or `python -m backend.er2.amber <battery folder> v8` (Strict).
   Amber v5 = Halo, v6 = Strict.
2. **Run**: `/api/er2/run` with `{"amber_version": V, "where": "vacc", "n_shuffle": 0, "explain": true, "drop": true}`.
   CPU jobs on the VACC (numpy networks); `er2_go.py` and `er2_types_driver.py` submitted runs and brought answers home
   (the account takes about 1,000 queued jobs).
3. **Targets** (one model each): `pten_vs_ctl`, `ko_pct`, `low_vs_high`, `ied3` (control / IED- / IED+),
   `iedpos_vs_iedneg`. **Views**: core, context, filters, before_after, events_all, mouse, everything, nuisance (+ raw).
   **Models**: pooled (linear, lasso, forest, boosting, mlp) and set networks (deep sets, attention). Training is on
   events; every call is one per mouse.
4. **Testing**: leave one mouse out (one control and one PTEN mouse out for PTEN against control). **Bar**: AUC 0.80
   (rank correlation 0.70 for knockout %).
5. **Explaining**: permutation, Shapley, drop one family, attention, merged into one MOST IMPORTANT list.

Runs (`ML_summary.txt` in the 112326 archive folder has every line):

| run | what |
|---|---|
| r006 / r007 | Halo / Strict, all events, 16 mice |
| r008 / r012 | DS1 against DS2 |
| r009 / r013 | DS1 minus DS2 per mouse |
| r010 / r014 | one DS type at a time |
| r011 / r015 | random twins (same event count, random events): the yardstick for the per-type runs |
| r016 / r017 | all events with the raw event added |

---

## Step 6. Choosing the best fit

Two choices are called "best fit" in this work:

- **The DS1 / DS2 classifier per recording** is the winner rule of step 3. It is fixed before any group test.
- **The ML models**: a model counts when its held-out score clears the bar (AUC 0.80). The menus use r006 (Halo, all
  events): 14 of 52 models reach the bar for IED+ against IED- (best AUC 0.95, context view, deep sets). The per-mouse
  held-out calls of those 14 models are the "held-out calls": each PTEN mouse scored by models that never saw it (9
  rounds; the controls sit this question out). They call 8 of 9 PTEN mice right; the miss is m3 (all 14 call it IED-),
  and they call m7 IED-. Fast power was never an ML input. Compare every count at the bar with the random-twin runs
  (r011 / r015) before reading much into it.

---

## Step 7. Menus and supplements (outside Jarvis)

All in `code/menus` (they ran in the session scratch folder `menu/`). Exploratory statistics throughout: one number per
mouse, the smallest P of the applicable tests (two groups: Mann-Whitney, Welch t, Student t; knockout %: Spearman,
Pearson, Kendall; three groups: ANOVA, Kruskal-Wallis, ordered trend; paired: paired t, Wilcoxon), no correction.

**DS story menu** (2026-11-23, `Lab Figures/DS_Story_Menu_112326`, 11 pages): `m0_data.py` (Root Canal events, borders,
layers, IED bank entries) -> `m1_stats.py` (every battery measure through every contrast: `tables/all_results`) ->
`m2_extract.py` (2 kHz X-ray reads of DS, BT and IED-class events of the five IED+ sessions: `reads/`) ->
`m3_profiles.py`, `m4_dsied.py`, `m7_uprof.py`, `m8_timing.py`, `outlier.py` -> `pages_a.py`, `pages_b.py`,
`pages_c.py` -> `m9_tables.py`, `m6_package.py`, `merge_pdf.py`.

**Jeremy menu** (2026-11-24, `Lab Figures/Jeremy_Menu_112426`, 14 pages): Jeremy's 8 questions, each page = kicker,
"Jeremy Asked: <question word for word>", "Results show: <one conclusive sentence>", then panels whose headings state the
finding. `m10_reads_all.py` (2 kHz reads of every DS of all 16 mice, about 25 minutes: `reads_ds/`) -> `j1_battery.py`
(per-mouse numbers from the frozen battery on every filter set: `jeremy_battery.pkl`) -> `j2_freq.py` (frequency
measures from the reads: `jeremy_freq.pkl`, about 4 minutes) -> `jpages.py cover q1 q2 q3 q4 q5 q6 q7 q8 every table` -> `j_package.py`
-> `j_merge.py`.

Key definitions used by the menu:
- **Efficacy**: input = the DS sink at its peak and its 10 to 90% rise slope; output per input = each DS's fast (240 to
  420 Hz) power fitted against its sink within each mouse (Theil-Sen), read at the control-average sink.
- **Fast power (Story 1)**: Root Canal's: +-25 ms around the event against a 40 ms baseline centered 150 ms before
  (-170 to -130 ms), 5 kHz read, Welch spectrum, 240 to 420 Hz, best contact.
- **Q4 windows (2 kHz reads)**: fast power +-25 ms against -100 to -50 ms; dominant frequency +-50 ms (5 to 300 Hz; the
  argmax sticks at 100 Hz, so the fast-power center and gain are used); sink +-3 ms.
- **Layers (menu rule)**: along each blade's own DS axis v (0 = cell-layer source, 1 = the average DS sink): MML = v 0.7
  to 1.3, OML = v 1.3 to 2.0. **This rule is flawed** (see the layer check).
- **CSD scale**: groups compared on one scale: every mouse divided by the control average (deepest DS sink = 1).

**Follow-up** (2026-11-25, `Lab Figures/Jeremy_Menu_Followup_112526`, 6 pages, `jfollow.py`): held-out calls, DS / BT /
IED counts per mouse and group, Story 1's and Q4's windows, how layers are found, classes and Q4 against Q7.
**Supplements** in the menu (`python jfollow.py supp`): CONCERN / RESOLVE pages after Q4 (pages 6 and 7) and Q7 (page 11).

**Layer check** (2026-11-25, `Lab Figures/Layer_Check_112526`, 11 pages): the menu's v = 1 was the sink of the AVERAGE DS,
so its MML sat on whichever type is the majority. Tight rule (the user's answers): MML centered on the DS2 sink and OML on
the DS1 sink of each blade (names are positional), +-2 contacts (+-40 um), split at the midpoint when the anchors are under
80 um apart; mice whose types do not separate (m2, m21, m8, m3, m5) use the all-DS sink as MML and put the OML the median
DS1-to-DS2 gap farther out (53 um upper, 57 um lower). `tight_layers.py` -> `JM_LAYERS=tight python j1_battery.py` and
`JM_LAYERS=tight python j2_freq.py` (write `*_tight.pkl`) -> `layer_check.py`. Result: 52 of 62 layer results keep their
verdict, 6 lost, 4 new, none reversed; 40 of the 45 the menu states still agree. **The menu has not been rebuilt with the
tight layers; the user has not decided.**

Run the menu scripts with the Python Jarvis uses (numpy, scipy, pandas, matplotlib, openpyxl) and merge PDFs with
miniconda's Python (PyMuPDF). `figlib.py` holds the figure style (brackets laid out after the axis limits, never touching
a line).

---

## Step 8. The poster (2026-11-25)

`code/poster/build.py` and `assets.py` (python-pptx, miniconda; previews exported through PowerPoint). Output:
`Lab Figures/PTEN POSTER/PTEN poster -- UVM template v3.pptx` (48 x 36 in, three columns; placeholders are labeled as such).
The DS story panel came from `menus/poster_ds.py`, the process strip from `menus/poster_strip.py`.
