# Reviving CFC

Every bit of cross-frequency coupling code found on this machine, gathered from
four separate locations, deduplicated, and ordered by how it actually runs.
Nothing was moved or deleted at the source — these are all copies.

## What this code does

All of the lab's CFC code computes the **Tort modulation index (MI)**: how
non-uniformly the amplitude envelope of a fast band is distributed across the 18
phase bins of a slow band, scored as a normalized entropy. Sweep that over a grid
of slow × fast band pairs and you get a **comodulogram**.

The entire family shares one computational core. The dozens of drivers differ
only in how they find the data and what frequency grid they sweep:

```
LFP ──► eegfilt (slow band) ──► angle(hilbert(·))  = phase    ──┐
                                                                ├──► ModIndex_v2 ──► MI
LFP ──► eegfilt (fast band) ──► abs(hilbert(·))    = envelope ──┘

           repeat for every Phase × Amp pair  ──►  Comodulogram
```

## Layout

| Folder | What's in it |
|---|---|
| **`01_core_tort/`** | The actual math. Adriano Tort's original routines. Start here to understand the method. |
| **`02_barry_lineage/`** | The lab's single-machine drivers, five years of revisions, numbered oldest → newest. Run one. |
| **`03_vacc_pipeline/`** | The 2025 SLURM pipeline — same math, parallelized and fanned out over a cluster. Numbered in run order, `step01` → `step08`. **This is the one to revive for real work.** |
| **`04_reference/`** | FieldTrip's CFC function, as an independent cross-check. |

Each of `02` and `03` has its own README with the step-by-step detail. The short
version:

```
01_core_tort           ModIndex_v2 ← the MI itself
                       ModIndex_v1 ← single band-pair version
                       eegfilt     ← the bandpass everything depends on
                       CallerRoutine ← Tort's synthetic-data demo (best starting point)

02_barry_lineage       step01    original driver
                       step01_1 … step01_7   revisions, ending at the PTEN version
                       step02    band collapsing (defines Delta/Theta/Beta slices)

03_vacc_pipeline       step01  prep feeder sheets        (R)
                       step02  submit SLURM array        (sbatch)
                       step03  array task entry          (MATLAB)
                       step04  comodulogram per channel  (MATLAB)  ← the workhorse
                       step05  transpose results
                       step06  rip data out of .fig files
                       step07  merge + collapse to bands (R) → CFCMerged.csv
                       step08  QC plots                  (R)
                       lib/      called-not-run functions (read_csc, eegfilt, ModIndex…)
                       scratch/  unfinished bits, not part of the run
```

## Naming scheme

`stepNN_` gives the order things run. `stepNN_M_` is a **patch or alternate
version of that same step** — a different input format, a local-machine fallback,
a test copy — not a later step.

One deviation from `#.1`: MATLAB cannot call a file whose name contains a dot or
starts with a digit, and several of these files are invoked by name (from the
`sbatch` line, and from inside `step03`). So the patch separator is `_1` rather
than `.1`, and the `step` prefix keeps the names valid identifiers. I kept it
uniform across the R and SLURM files too so the ordering reads the same
everywhere.

## Which version should I actually use?

- **To understand the method:** `01_core_tort/CallerRoutine.m` — it builds a
  synthetic modulated signal so you can see MI respond to known coupling.
- **To run one channel on one recording:** `02_barry_lineage/step01_7_…_ForPtenData.m`
  (finest phase grid, amplitude out to 300 Hz).
- **To run a whole cohort:** `03_vacc_pipeline/`, starting at `step01`.

## Dependencies

MATLAB with the **Signal Processing** toolbox (`designfilt`, `filtfilt`,
`hilbert`) and, for the pipeline, **Parallel Computing** (`parfor`, `parcluster`).
R with `tidyverse`, `R.matlab`, `data.table`, `readxl`, `openxlsx`, `doParallel`,
`foreach`.

## Before any of it runs

**Every driver has absolute paths baked in** — `C:\Users\Z390\Desktop\PTEN_CFCs\…`,
`/Users/jeremybarry/Documents/UVM/…`, `D://PupProbePilot//…`, a
`/Volumes/Backup Plus/` mount, and a VACC path under a different account
(`/users/c/r/crweinst/PPP/vacc`). These are the first thing to fix.

## Bugs found, left as found

I did not fix these — flagging them so they don't cost you a day:

1. **`03/step03_arrayFCSE.m` argument-count mismatch.** It calls step04 with **8**
   arguments but `step04_newFCSE` takes **9**, expecting `cond` in slot 6.
   Everything shifts by one and `ncs_file` ends up undefined, erroring at
   `isfile(ncs_file)`. The CSV entry point (`step03_1`) passes all 9 correctly.
2. **`03/step02_2_array_FCSETweaks.sbat`** invokes `arrayFCSETweaks`, which does
   not exist anywhere on this machine.
3. **`03/step03_arrayFCSE.m` addpath** is `fullfile(workdir, 'VACCQuickstart')`
   while `workdir` already *is* VACCQuickstart. Should point at `lib/`.
4. **`03/step04_newFCSE.m`** initializes `data_vector` as `single(length(AmpFreqVector))`
   — a scalar, not a vector — then indexes `data_vector(ii, jj)` inside a `parfor`,
   growing it by implicit resize while only row `ii` is ever read back.
5. **`03/scratch/CFCArrayTypeCheck.m`** contains `for i = 1()`, which is not valid
   MATLAB, and reuses `i` for two nested loops. Unfinished scratch.
6. **`03/step05_TRANSpose_comodulograms.m`** extracts the file number with a fixed
   offset `baseFileName(38:end-4)`, so it only works for one exact filename length.
7. Several scripts do `cd = path_xls` (assigning to the builtin `cd`) instead of
   `cd(path_xls)`.
8. **`03/lib/read_csc.m`** declares `function … = read_Csc(…)` with a capital C
   while every caller writes `read_csc`. Fine on Windows, will break on a
   case-sensitive filesystem — which includes the VACC.

## What I changed

Only what renaming required: `function` declaration lines now match their
filenames, and the call sites that resolve by name were updated to match
(`newFCSE(` → `step04_newFCSE(` in the four step03 files; the `matlab -r` line in
two sbatch scripts). In `02`, all nine files had declared themselves
`demo_EEG_Analyze` regardless of filename; each now declares its own name.

No logic, path, parameter, or bug was altered.

## Provenance

| Folder | Copied from |
|---|---|
| `01_core_tort/` | `Documents/matlab/matlabProgs/tort/ComodulationRoutine/` — md5-identical copies also existed at `OurMfiles/Jeremy/COMOD_TORT/tort/ComodulationRoutine/` and inside the VACC folder, so this was copied once. |
| `02_barry_lineage/` | `Documents/matlab/OurMfiles/Jeremy/COMOD_TORT/` and `Documents/matlab/matlabProgs/jb_mine/` |
| `03_vacc_pipeline/` | `Desktop/Archives/PTEN_CFCs/VACC/VACC_CFC_Input/VACCQuickstart/`, plus the two `Test/` dirs and `Downloads/Archive/` for the divergent variants |
| `04_reference/` | `Documents/matlab/OurMfiles/Jeremy/fieldtrip-20191021/` |

## Checked and deliberately excluded

- **`Toothy but Gold and Green/…/tortlab_reference/`** (`dentatespike.py`,
  `solo_tort.py`) — same lab (Adriano Tort), but this is **dentate spike
  detection and classification**, not coupling. Verified: no MI or comodulogram
  content.
- **`IED/JeremyEEG11B_MT_Probe_SpectralProps_*.m`** in the jeremystats repo —
  matches "CFC" only in two hardcoded input/output *path strings*. It computes
  spectral properties, not coupling.
- **CellExplorer, Kilosort, `FindEvents.m`** — matched "modulation index" /
  "metrics" for unrelated reasons (ACG metrics, drift benchmarks).
- **Thousands of `Comodulogram_*.mat` and `*ComodFig*.fig` files**, feeder
  spreadsheets, `.sav`/`.prism` stats files and figures — these are inputs and
  outputs, not code, and were left in place. The big caches are
  `Desktop/Archives/PTEN_CFCs/data/` and
  `Documents/PTEN_Analysis_CFC_&_Spectral_Properties/`.
- macOS AppleDouble resource forks (`._*`) sitting alongside the originals.
