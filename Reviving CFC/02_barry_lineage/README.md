# 02_barry_lineage — the single-machine drivers, oldest to newest

These are all the *same script* evolving over five years, so they are numbered as
one step with patch versions: `step01` is the original, `step01_1` … `step01_7`
are successive revisions. You run **one** of them — normally the newest one that
matches your dataset — not all of them in sequence.

`step02` is the only thing that genuinely runs *after*: it collapses a saved
comodulogram into frequency bands.

Every driver has the same shape:

```
read a feeder spreadsheet ──► loop rows ──► read_csc the .ncs LFP
   ──► 60 Hz notch (designfilt + filtfilt)
   ──► sweep the Phase × Amp grid, ModIndex_v2 per cell
   ──► save Comodulogram_*.mat + ComodFig_*.fig
```

## The lineage

| File | Date | What changed |
|---|---|---|
| `step01_cross_frequency_coupling.m` | earliest | The original. `uigetfile` picks one file. Phase 2:2:26 (BW 4), Amp 30:5:300 (BW 10). Contains **both** routines — the fast one via `ModIndex_v2`, and the slow low-memory one via `ModIndex_v1`. |
| `step01_1_JBcross_frequency_coupling.m` | Oct 2019 | First Barry version. |
| `step01_2_JBcross_frequency_coupling_Michelle.m` | Jun 2021 | Michelle's FSE dataset. |
| `step01_3_JBcross_frequency_coupling_june2021.m` | Jun 2021 | June revision. |
| `step01_4_JBcross_frequency_coupling_june2021_B.m` | Jun 2021 | June revision B. |
| `step01_5_…_MichelleFinal_altered_UIGET.m` | Apr 2023 | Interactive file picking. |
| `step01_6_…_MichelleFinal.m` | Jan 2024 | Final FSE/Michelle version. |
| `step01_7_…_ForPtenData.m` | Jun 2024 | **The PTEN one.** Phase 1:0.5:26 (BW 0.5) — a much finer phase grid — and Amp 20:5:**300** (BW 10), opened from 200 to 300 Hz to look for pHFO coupling in PTEN KOs. Notch widened from 59–61 to 55–65 Hz. Names outputs by session/condition/layer. |
| `step02_Notes_ComodAnalysis.m` | Jul 2021 | Post-hoc. Loads a saved comodulogram and means it across column slices: Delta `1:3`, Del-Theta `3:9`, Theta `7:23`, Beta `23:40`. **These band definitions are what `03_vacc_pipeline/step07_CFCReader.R` reproduces**, so this file is the reference for what the bands mean. |

If you want the fine-grained phase resolution, `step01_7` is the one to start
from — it is the direct ancestor of `03_vacc_pipeline/step04_newFCSE.m`, which is
the same computation with `parfor` around it.

## To run one

Put `01_core_tort/` and `03_vacc_pipeline/lib/read_csc.m` on the MATLAB path
(these need `eegfilt`, `ModIndex_v2`, and `read_csc`), repoint the hardcoded
feeder-sheet path at the top of the file, then run it.

Paths are hardcoded to machines that may no longer exist — `C:\Users\Z390\Desktop`,
`/Users/jeremybarry/Documents/UVM/...`, and in `step02` a
`/Volumes/Backup Plus/` mount. Fix those first.

## What I changed from the originals

Only the `function` declaration line. All nine files declared themselves
`function []=demo_EEG_Analyze ()` regardless of filename — a leftover that made
MATLAB warn about the mismatch. Each now declares its own name. Nothing else was
touched; every hardcoded path and quirk is as found.
