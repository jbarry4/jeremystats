# 03_vacc_pipeline — the SLURM pipeline, in run order

The newest and most complete version of the CFC analysis (2025). Same Tort
modulation index as everywhere else, but parallelized with `parfor` and fanned
out over a SLURM job array on the VACC.

Files are named `stepNN_` in the order they run. A `stepNN_M_` suffix means a
**patch / alternate version of that same step** — a different input format, a
local-machine fallback, or a test copy. You run the plain `stepNN_` file unless
you specifically need one of the variants.

## The flow

```
step01  FeederPathCleaner.R        R        compile + clean the feeder spreadsheets
   │                                        (which rat, which session, which .ncs, which layer)
   ▼
step02  array_FCSE.sbat            sbatch   submit the job array — one task per feeder sheet
   │                                        8 CPUs, 25 GB, 4 h, MATLAB R2023b
   ▼
step03  arrayFCSE.m                MATLAB   array task entry point. Opens the parpool, picks its
   │                                        feeder sheet by $SLURM_ARRAY_TASK_ID, loops 64 channels
   ▼
step04  newFCSE.m                  MATLAB   ** the workhorse ** — one comodulogram per channel
   │                                        Phase 1:0.5:26 Hz (BW 0.5), Amp 20:5:200 Hz (BW 10)
   │                                        writes Comodulogram_*.mat + ComodFig_*.fig
   ▼
step05  TRANSpose_comodulograms.m  MATLAB   transpose each saved comodulogram, tag with file number
   │
   ▼
step06  CFCFigRipper.m             MATLAB   rip X/Y/Z arrays back out of the saved .fig files
   │                                        (this is where the Y frequency template comes from)
   ▼
step07  CFCReader.R                R        merge everything, collapse into frequency bands,
   │                                        write CFCMerged.csv for SPSS
   ▼
step08  CFCQualCheck.R             R        QC plots — band height vs frequency, faceted by region
```

Inside step04, one comodulogram cell is:

```
lfp ──► eegfilt (phase band) ──► angle(hilbert(·)) ──┐
                                                     ├──► ModIndex_v2 ──► MI
lfp ──► eegfilt (amp band)   ──► abs(hilbert(·))   ──┘
```

The band collapsing in step07 uses the column slices defined back in
`02_barry_lineage/step02_Notes_ComodAnalysis.m`:
Delta `1:3`, Del-Theta `3:9`, Theta `7:23`, Beta `23:40`.

## Variants

| File | Differs how |
|---|---|
| `step01_1_FeederPathCleaner_DKO.R` | Same cleaner, DKO cohort. |
| `step02_1_array_FCSEcsv.sbat` | Submits the CSV entry point instead of the `.xlsx` one. |
| `step02_2_array_FCSETweaks.sbat` | Tweaked resources. **Calls `arrayFCSETweaks`, which does not exist anywhere on this machine** — left as found. |
| `step03_1_arrayFCSEcsv.m` | Reads CSV feeder sheets. Passes all 9 args to step04 correctly — see the bug note below. |
| `step03_2_…_PTEN_Test.m`, `step03_3_…_VACC_Test.m` | Two divergent test copies (md5-distinct from each other and from step03_1). |
| `step04_1_FrequencyCouplingbadFixedVersion.m` | Single machine, no `parfor`, Amp grid to 200 Hz. Sep 2025. |
| `step04_2_FrequencyCouplingSpecialExport.m` | Different export path/format. |
| `step04_3_CFCBackupForLocalMachines.m` | Local fallback when the cluster isn't available. |
| `step04_4_FrequencyCouplingFixedVersion_DownloadsArchive.m` | Copy found in `Downloads/Archive`, distinct from the others. |
| `step07_1_CFCReader_desktop.R` | Desktop-path version of the reader. |

## lib/ — called, never run directly

`read_csc.m` (Neuralynx `.ncs` reader), `CFCMatrix.m` (tiles a metadata string
into a column), `eegfilt.m`, `ModIndex_v1.m`, `ModIndex_v2.m`.

These keep their original names because MATLAB resolves them by filename — a
`stepNN_` prefix would break every call site. `eegfilt.m` and the two
`ModIndex` files are byte-identical to the ones in `01_core_tort/`; they are
duplicated here on purpose so this folder is self-contained when staged to the
cluster.

## scratch/ — not part of the run

`CFCArrayTypeCheck.m` (unfinished — contains `for i = 1()`, which is not valid
MATLAB), `CSVFeederReader.m`, `test_Old_Feeders.m`, `test_VACCQuickstart.m`.

## Before this will run

1. **Repoint the hardcoded paths.** Every file has absolute paths baked in —
   `C:\Users\Z390\Desktop\PTEN_CFCs\...`, `D://PupProbePilot//...`, and a VACC
   path under a different account (`/users/c/r/crweinst/PPP/vacc` in step02).
2. **Fix the `addpath` in step03.** It does
   `addpath(fullfile(workdir, 'VACCQuickstart'))` while `workdir` already *is*
   VACCQuickstart. It should point at `lib/`.
3. **`step03_arrayFCSE.m` has an argument-count bug** (pre-existing, left as
   found): it calls step04 with **8** arguments —
   `(workdir, ratId, eegnum, session, eegpath, group, region, ncs_file)` — but
   `step04_newFCSE` takes **9** and expects `cond` in slot 6. So `group` lands
   in `cond`, `region` in `group`, `ncs_file` in `region`, and `ncs_file` ends
   up undefined, which will error at `isfile(ncs_file)`. The CSV path
   (`step03_1`) passes all 9 correctly. Either add `cond` to step03, or use the
   CSV entry point.
4. **Toolbox needed:** Signal Processing (`designfilt`, `filtfilt`, `hilbert`)
   and Parallel Computing (`parfor`, `parcluster`).

## What I changed from the originals

Only what the renaming required, plus nothing else:

- `function` declaration lines updated to match the new filenames.
- Call sites updated so they still resolve: `newFCSE(` → `step04_newFCSE(` in the
  four step03 files, and the `matlab -r "…"` line in `step02_array_FCSE.sbat` and
  `step02_1_array_FCSEcsv.sbat`.

Every hardcoded path, bug, and quirk above is exactly as found.
