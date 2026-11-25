# Pten KO mosaicism behavior: analysis code

Python code for every analysis and figure in the report *Pten KO mosaicism and spatial accuracy behavior*
(November 18, 2026). Path analyses are in `path_analysis/`; group statistics on the PlaceAccuracy output are
in `group_analysis/`. All of it was rerun from scratch from this folder before it was saved, and it reproduces
the report's numbers.

## Setup

1. Python 3.10 or later, with the packages in `requirements.txt`:
   `pip install numpy pandas scipy statsmodels matplotlib pyreadstat openpyxl`
2. Check the paths in `config.py`. `DATA_ROOT` should point to your `AllBehavior` folder; it is already set to
   `/Users/jeremybarry/Documents/UVM/projects/PTEN/AllBehavior`.
3. The input files are already in `inputs/`, under these names. If you update one, keep the name:

| File in `inputs/` | What it is |
|---|---|
| `AllProbeSessions.sav` | PlaceAccuracy measures for every probe session |
| `AllProbes_ByGZLocation.sav` | Time in each of the four goal zones, per probe session |
| `ROC_heterotopia_Fixed_hilo.sav` | Sessions to criterion (the version used in the report) |
| `PTEN_sess2crtit_hilo.sav` | Earlier criterion file (the version with PercentKO); only for `crit2.py` and `crit3.py` |
| `PTEN_sess2crtit_hilo_first.sav` | First upload of that file, without PercentKO; only for `crit2.py` |
| `Data4Claude.xlsx` | Theta CSD and CNO follow-up, WT and Pten KO (November 18 version with WT rows) |
| `ied/` | IED outputs of the lab's recording pipeline: `GrandAvg_SOLID_Base.csv`, `GrandAvg_SOLID_CNO.csv` (grand-average voltage, 49 depth bins x 1201 samples), `IED_session_summary.csv`, `IED_onsets_solid.csv`, and the pipeline's `stats_*.csv` |
| `patch/` | Whole-cell CNO validation: `cno_patch_cells.csv` (per-cell baseline and CNO values), `cno_patch_fi.csv` (normalised F-I curves and cell counts) and `cno_patch_traces.json` (sample traces). Recovered from the vector coordinates of the lab's patch summary figure; they reproduce its published means and SEMs exactly |

Intermediate files go to `work/` and figures to `figures/` (path analysis) or `work/figs` and `work/gz`
(group analysis). Each script finds `config.py` on its own, so you can run it from any folder.

## Run order

```
python group_analysis/probe.py                 # always first: group labels, % KO and IED -> work/probe.pkl

# path analysis (report Figures 16-25, 30-32)
python path_analysis/s00_build_session_list.py # 256 probe sessions and their .dat files
python path_analysis/s01_validate_sessions.py  # rewards and entrances vs PlaceAccuracy: expect 0 mismatches
python path_analysis/s02_example_mice_compute.py
python path_analysis/s03_example_mice_figs.py  # Figures 16-19
python path_analysis/s04_approach_metrics.py   # takes a few minutes
python path_analysis/s05_approach_figs_stats.py   # Figures 20-22 and their tables
python path_analysis/s06_zone_visits.py        # takes a few minutes
python path_analysis/s07_arrival_profiles.py
python path_analysis/s08_arrival_fig_stats.py  # Figure 23 and its table
python path_analysis/s09_slope_analysis.py     # Figure 24 and its table
python path_analysis/s10_pick_example_mice.py  # per-mouse summary used to choose M22, M33, M34
python path_analysis/s11_after_miss_compute.py # takes a few minutes
python path_analysis/s12_after_miss_fig_stats.py  # Figure 25 and its table
python path_analysis/s13_phase8_visits.py     # timed visits to all four zones, phase 8 visible and hidden
python path_analysis/s14_phase8_conflict.py   # Figures 30, 31 and their tables (place vs cue; new vs old place)
python path_analysis/s15_heading_profile.py   # Figure 32 and its table (heading toward the goal by distance; launch-distance distribution)

# group analysis (report Figures 1-15 and the tables in those sections)
python group_analysis/report_stats.py
python group_analysis/phase.py
python group_analysis/hi_trend.py
python group_analysis/fig8.py
python group_analysis/figs.py
python group_analysis/fig7.py
python group_analysis/m6.py
python group_analysis/pct.py
python group_analysis/roc.py ; python group_analysis/roc2.py
python group_analysis/crit3.py ; python group_analysis/crit4.py ; python group_analysis/crit2.py
python group_analysis/csd3_data.py ; python group_analysis/csd3_stats.py ; python group_analysis/csd3_figs.py ; python group_analysis/csd3_layers.py
python group_analysis/ied_figs.py              # after csd3_*: Figures 33-35, S3, S4 (IEDs), uses work/csd3

# whole-cell CNO validation (report Figure 36); independent of everything above
python path_analysis/s16_arrival_directed.py   # arrival profiles split by directed run; example runs
python path_analysis/s17_arrival_paths.py      # Figure 37
python path_analysis/s18_search_sets.py       # Figure 38 (needs s11 pauses)
python path_analysis/s21_braking.py           # braking rate by place and braking distance (Section 5 of v2)

# report v3 figures (run after the steps above)
python group_analysis/f01_learning.py         # Figure 1  criterion, percent KO, the two phenotypes
python group_analysis/f02_examples_measures.py# Figures 2 and 3  examples beside the session measures
python group_analysis/f04_change_per_phase.py # Figure 4  change per phase, hidden and cued
python path_analysis/s17_arrival_paths.py     # Figures 8 and 9  arrival runs; slowing and pausing
python path_analysis/s22_former_goals.py      # Figure 10  the set to rule out
python summary_figs/nf2_pausemaps.py          # Figure 11  pause maps, cue on and off
python summary_figs/nf4_arrival.py            # Figure 12  braking
python group_analysis/csd3_figs.py            # Figures 19 and 20 (and S1, S2) among others

# stacked multipanels, composed from the figures above without redrawing them
python tools/compose_stack.py work/figsv3/fig09_phase10_zones.svg -=A.svg -=B.svg   # see the docstring

python patch/cno_patch_fig.py                  # Figure 36
python group_analysis/gz_prep.py
python group_analysis/gz_stats.py
python group_analysis/gz_entries.py
python group_analysis/gz_bars_stats.py
python group_analysis/gz_mwu.py
python group_analysis/gz_bars_fig.py H fig_bars_hidden.png        # Figure 12 (needs gz_bars_stats.py first)
python group_analysis/gz_bars_fig3.py H fig_bars_hidden_mwu.png    # Figure 13
python group_analysis/gz_bars_fig3.py V fig_bars_visible_mwu.png
python group_analysis/gz_figs.py
```

## Which script makes what

| Report item | Script | Output |
|---|---|---|
| Figure 1, 2 (sessions to criterion, % KO) | `figs.py`; stats in `crit3.py`, `crit4.py`, `pct.py`, `roc*.py` | `work/figs/fig1_criterion.png`, `fig2_pctko.png` |
| Figures 3, 4 (visible / hidden probes) | `figs.py`; stats in `probe.py`, `report_stats.py` | `work/figs/` |
| Figures 5, 6, 7 (% KO by phase, phase 10) | `figs.py`, `fig7.py`; stats in `report_stats.py` | `work/figs/` |
| Phase effects tables, Figure 8 | `phase.py`, `hi_trend.py`, `fig8.py` | `work/figs/fig8_hi_trend.png` |
| Figures 9, 10, 26, 27, S1, S2 (theta CSD by layer, goal time visible and hidden, CNO, ROC for IEDs) | `csd3_data.py`, `csd3_stats.py`, `csd3_figs.py`. Inputs: `CSD_sansM2.sav`, `AllProbeSessions_CNO.sav`; % KO from `Data4Claude.xlsx` plus `PCT_EXTRA` in config.py. M26 is excluded from CSD (`EPHYS_EXCLUDE`) | `work/csd3/` |
| Figures 28, 29 (theta CSD layer profile, Lo/Hi and IED split; GEE vs WT hilus) | `csd3_layers.py` | `work/csd3/layers_*.csv` |
| Figures 33–35, Supplementary S3–S4 (IED laminar structure, rate with CNO, link to theta and behaviour) | `ied_figs.py` | `work/ied/ied_stats.txt`, `ied_mouse.csv`, `ied_layers.csv`, `ied_sessions.csv` |
| Figure 37 (speed along the path into the goal; slowing ratio and total pausing by phase) | `s16_arrival_directed.py` then `s17_arrival_paths.py` | `work/approach/arrival_dir.pkl`, `runs_ex.pkl`, `pauses_d.pkl` |
| Figure 38 (pause time at current, former and never-used goals, by phase) | `s18_search_sets.py` | `work/approach/pauses_cat.pkl`, `search_sets.csv`, `search_sets_stats.txt` |
| Figure 36 (CNO silences hM4D-expressing Pten KO granule neurons; dKO group of the lab's figure removed) | `patch/cno_patch_fig.py` | — (reads `inputs/patch`) |
| Figures 11-15 (zone times, perseveration) | `gz_*.py`: Figure 12 from `gz_bars_fig.py`, Figure 13 from `gz_bars_fig3.py`, Figures 11, 14, 15 from `gz_figs.py` | `work/gz/` |
| Figure 16 (example mice, hidden paths) | `s02`, `s03` | `figures/exA_paths_hidden.png` |
| Figure 17 (dwell maps) | `s03` | `figures/exB_dwell_hidden.png` |
| Figure 18 (speed maps) | `s03` | `figures/exC_speed_hidden.png` |
| Figure 19 (visible paths) | `s03` | `figures/exE_paths_visible.png` |
| Figure 20 (wall-to-goal runs) | `s04`, `s05` | `figures/ap1_paths.png` |
| Figure 21, 22 and their tables (approach) | `s05` | `figures/ap2_metrics.png`, `ap3_launch_phase.png` |
| Figure 23 and table (arrival) | `s06`, `s07`, `s08` | `figures/ap4_arrival.png` |
| Figure 24 and table (slope) | `s09` | `figures/ap5_slope.png` |
| Figure 25 and table (after a miss) | `s11`, `s12` | `figures/ap6_aftermiss.png` |
| Figures 30, 31 and tables (phase 8: place vs cue, new vs old place) | `s13`, `s14` | `figures/fig30_phase8_visible.png`, `fig31_phase8_hidden.png`; per-mouse values `work/phase8/phase8_mouse.csv`, all statistics `work/phase8/phase8_stats.txt` |
| Figure 32 and table (heading toward the goal by distance, visible vs hidden) | `s04`, `s15` | `figures/fig32_heading_profile.png`; per-mouse values `work/heading/heading_mouse.csv`, profiles `work/heading/heading_profile.csv`, all statistics `work/heading/heading_stats.txt` |

## Crisp figures for editing (vector export)

Every figure script saves PNGs. To also get vector versions, run it with the helper in `tools/vector_export`:

```
PYTHONPATH=tools/vector_export VEC_OUT=figures_vector INTER_TTF_DIR=/path/to/Inter/ttf python path_analysis/s03_example_mice_figs.py
```

Each PNG is then also written as `.pdf` (vector, editable text), `.svg` (vector, editable text) and `_600dpi.png`.
The report now embeds vector figures, made the same way with `VEC_TEXT=path` so text is drawn as outlines.
`INTER_TTF_DIR` is optional; it points to the TrueType build of Inter (from the Inter 4.0 release,
`extras/ttf`), which embeds cleanly in PDF.

## Statistics conventions

- **Between groups:** two-sided Mann-Whitney U for every comparison (Lo vs WT, Hi vs WT, Lo vs Hi, pooled KO vs WT, IED+ vs IED−).
  Several group scripts first defined a permutation test `perm`; each overrides it with a Mann-Whitney version
  immediately after, so every reported between-group p is a Mann-Whitney p.
- **Within groups:** paired t-tests. Per-mouse slopes are tested against zero with one-sample t-tests.
- **Sessions to criterion:** Welch t and permutation tests are also printed.
- **Slope across phases (Figure 24):** a per-run logistic model fitted with generalized estimating equations,
  with errors clustered by mouse, is shown alongside the per-mouse test.
- **Mice:** DKO mice are excluded everywhere. M6 is excluded from sessions to criterion only.

## Where the Python departs from TargetTrajectories.m

Each departure is also marked in the code with `## DEVIATION FROM MATLAB` or `## NOT IN MATLAB`.

| Item | MATLAB (TargetTrajectories_JB2_jun25_NewGoalCode.m) | This code |
|---|---|---|
| Reading files | `read_biosigPlaceAcc.m` | `traj_lib.read_dat`. Matches rewards, entrances and goal time exactly for all 256 sessions. |
| Speed | `Speed_MtxEZ.m` (not provided) | `traj_lib.speed_matlab`: displacement over 15 frames, shifted 12 frames. Matches MeanSpeed within 0.4 cm/s and target speed within 1.2 cm/s for the example mice. |
| Rewards, entrances, goal time, target speed, pixel size, goal position and radius, annulus | as written | Same formulas. |
| Goal zones G1-G4 | from `PTEN_Feeder_GoalZones.xlsx` | Each mouse's zone k is the goal in the header of its phase k+6 session. Zone times agree with `AllProbes_ByGZLocation.sav` within 0.35 points for the example mice. |
| Session list | rows of the feeder xlsx, with file paths | File names from `AllProbes_ByGZLocation.sav`, searched for under `DATA_ROOT` (`s00`). |
| Approach before reward | `ZoneLatSecs` from the header; window from reward − (latency + 3 s) to reward − latency | Latency fixed at 1.2 s (true for all probe sessions). |
| Arena in plots | raw coordinates, fixed 0-260 axes | Each session re-centred and scaled to a common arena with a fitted circle (`arena_fit.py`), for display only. Measures use raw coordinates. |
| Position map | `hist3` × 0.033 s, jet colormap, caxis [0 17], no smoothing | Frames / 30 s per 8-px bin, Gaussian smoothing (1 bin), grey colormap 0-4 s, wall zone blanked. |
| Speed map | speed recomputed on binned coordinates, jet colormap, caxis [0 40] | Full-resolution speed averaged per bin, smoothed (1 bin), bins with < 0.25 s left blank, viridis colormap 0-30 cm/s. |
| Figure layout | one 2×3 figure per session | One panel type per figure, 3 mice × 4 phases. |
| WarpSpeed, descent-angle / pause filter, scatter, quadrants, fractal dimension | computed | Not used: you said these were filler pieces. |
| Launch distance, wall-to-goal runs, zone visits, arrival, slopes, returns after a miss, phase 8 conflicts, heading by distance | not present | New analyses (`s04`-`s15`), described in each script's header. |
| Pauses (Figure 25) | speed <= 3 for >= 35 frames, minus windows shared with 150-700-frame stillness, one quadrant kept | Same speed and 35-frame minimum; pauses > 10 s and pauses at the wall dropped; all quadrants kept (`s11`). |
| Speed around entry (Figure 23, top) | not present | Centred 0.5 s window, so that time zero is the entry (`s07`). |

## Things to know

- **`gz_mwu.py` was reconstructed.** The table it writes (`mwu.pkl`) was first built interactively. This script
  reproduces the saved table exactly for every column the figures use. The permutation-based columns of the
  original are dropped, since they were superseded by Mann-Whitney.
- **Folders that are not part of the run order:**
  - `path_analysis/exploratory/` holds the first approach measures, which were tried and dropped. Their headers
    say why; none is in the report.
  - `group_analysis/superseded/` holds early scripts and one-off edits, kept for the record.
- **Fonts:** the figures use Inter if it is installed and otherwise fall back to Helvetica, Arial or DejaVu Sans.
  Layout may shift slightly with a different font.
- **Not included:** the report text and its build step (pandoc to Word, then PDF).


## Note on the CSD / CNO analysis (current version)

The theta CSD section now uses the channel-level file `CSD_sansM2.sav` and the behaviour file `AllProbeSessions_CNO.sav`
(`csd3_*.py`). The earlier scripts built on the per-mouse summary in `Data4Claude.xlsx` (`cno2.py`, `cno2_fig.py`,
`cno2_pooled.py`, `csd_ied_roc.py`, `csd_ied_roc_fig.py`, and `standalone/csd_cno_ied_stats.py`) are kept in
`group_analysis/superseded/` and `standalone/` for reference only. Data4Claude differed from the channel file in four
sessions (M3 baseline; M11, M13, M28 after CNO), included M26, and lacked M29 and M30.
