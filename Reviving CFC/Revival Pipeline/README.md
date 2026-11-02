# Revival Pipeline — the beta run

One channel, end to end, with a pass criterion after every step. The design is
in **[CFC_BetaRun_OneChannel.html](CFC_BetaRun_OneChannel.html)** ("One Channel,
Eight Gates"); this folder is the code that implements it.

Built and run against **MATLAB R2023b** — the same version the SLURM script
loads. Every number below is measured on this machine, not estimated.

## Quickstart

```matlab
cd 'Reviving CFC/Revival Pipeline/code'
betapath()                 % puts 01_core_tort and 03_vacc_pipeline/lib on the path

test_ModIndexFast          % gate 4, standalone, ~20 s
RunBetaDemo                % whole pipeline on synthetic data, ~100 s

% the real thing
R = RunBeta('Y:\...\2024-06-07_11-40-57\CSC12.ncs', ...
            'RefMat', 'C:\...\Comodulogram_12.mat');   % RefMat drives gate 5
```

`RunBetaDemo` plants coupling at 7 Hz phase / 65 Hz amplitude and checks the
pipeline finds it there. It needs no recording, so it works as an install check
and as a smoke test after any change.

## The run

Ten steps. Left column runs, right column decides whether to continue.

| # | File | Does | Gate |
|---|---|---|---|
| 1 | `params.m` | every setting in one place | — |
| 2 | `LoadCSC.m` | `read_csc` → decimate /10 → notch → gap + clip check | **1** it looks like an LFP |
| 3 | `MakeEpochs.m` | `floor(T/6)` blocks, nothing dropped | **2** the epochs line up |
| 4 | `FilterBanks.m` | 17 slow + 37 fast bands, whole trace, `parfor` | **3** envelope tracks phase |
| 5 | `PhaseBins.m` + `MIFromBins.m` | the modulation index, blocked over bands | **4** fast == reference |
| 6 | `CFC.m` (no surrogates) | MI for every cell | **5** reproduces `newFCSE` |
| 7 | `CFC.m` (+ surrogates) | the null, and a permutation p | **6** the null is flat |
| 8 | `ThetaPower.m` | mean squared envelope per epoch | **7** power and MI share an index |
| 9 | `ChannelQC.m` | the seven-panel figure | — |
| 10 | `SaveChannel.m` | one self-contained `.mat` | **8** the file stands alone |

`RunBeta.m` drives all ten and prints a scoreboard. Gates 1, 2, 4 and 7 are
hard — they mean the code is wrong, and the run stops. Gate 5 stops the run too,
but because the *science* changed, not the code.

`FindIEDs` is not here. Deliberately: the windows of interest carry no IEDs, and
leaving transients in is informative. Instead `MakeEpochs` records `maxAbs` and
`nSharp` per epoch and drops nothing, and QC panel B puts the raw trace directly
under the MI-over-time trace on a shared axis, so a transient-driven MI spike is
visible rather than averaged away. Record, don't remove.

## What the beta run found

Three things, all of which are the point of running a beta.

### 1. The obvious vectorisation of `ModIndex_v2` is wrong

`ModIndex_v2.m` finds bin membership with

```matlab
find(Phase >= position(j) & Phase < position(j) + winsize)
```

The natural rewrite is `discretize(Phase, [position, pi])` or
`floor((Phase+pi)/winsize)`. Both are subtly wrong, for the same reason: the
upper edge is recomputed per bin as `position(j) + winsize`, which is **not
bit-identical** to `position(j+1)`. Where it lands one ulp high, a sample at
exactly `position(j+1)` satisfies *both* bins' tests and is counted twice; one
ulp low and it is counted in neither. `ModIndex_v2`'s bins are not a partition,
and reproducing it means reproducing that.

The first version of `PhaseBins.m` used `discretize`. `test_ModIndexFast.m`
caught it — two of six cases failed, at 3.1e-2 against a 1e-12 tolerance. The
fix keeps `ModIndex_v2`'s literal comparisons and just stops repeating them
3,700 times per epoch.

For real LFP phase this is measure-zero and would never have shown up in a spot
check. That is exactly why gate 4 asserts rather than promises.

### 2. The speedup is real, but it is not where the plan said

Measured, 6 s epoch at 3255.6 Hz, one modulation index:

| | ms per MI | vs reference |
|---|---|---|
| `ModIndex_v2` (reference) | 1.696 | 1× |
| `ModIndexFast`, one band | 1.735 | **1.0×** |
| blocked, 37 fast bands per pass | 0.026 | **66×** |

Binning once buys *nothing* for a single band, because exact reproduction means
doing the same 18 comparisons. The entire gain comes from amortising that
binning across the 37 fast bands and every surrogate — 0.026 ms per cell, which
beats the plan's 0.08 ms estimate by 3×. So the design conclusion holds and the
mechanism does not: block across bands, don't micro-optimise the bin arithmetic.

### 3. z is over-dispersed. Use the permutation p instead

Gate 6 was written to assert `|z| < 3` everywhere on phase-randomised data. It
failed. The failure is real and is **not** a bug in the shift:

- **The null is centred.** The observed MI sits mid-distribution among its own
  surrogates — mean rank quantile **0.489** against an ideal 0.500.
- **The null is over-dispersed.** `SD(z) ≈ 1.4` rather than 1.0, and it does not
  shrink as surrogates are added — measured identical at 20, 50, 100 and 500.
  Structural, not sampling noise.

Circularly shifting a narrowband phase series mostly rotates the *preferred
phase* rather than destroying the coupling, so the surrogate spread underestimates
the true null spread. A nominal `|z| > 3` behaves like `|z| > 2.2–2.6`.

Four variants, same null data, 200 surrogates:

| surrogate | phase BW | mean quantile | top 5% | SD(z) |
|---|---|---|---|---|
| within-epoch shift | 0.5 Hz | 0.489 | 9.2% | 1.40 |
| within-epoch shift | 2.0 Hz | 0.536 | 7.5% | 1.25 |
| cross-epoch pairing | 0.5 Hz | 0.492 | 7.5% | 1.30 |
| cross-epoch pairing | 2.0 Hz | 0.515 | 7.9% | 1.15 |
| *ideal* | | *0.500* | *5.0%* | *1.00* |

Widening the phase band and pairing across epochs both help; neither fixes it.

**So `CFC.m` now also returns `out.p`** — the one-sided permutation p,
`(1 + #{surr ≥ obs}) / (nSurr + 1)`. That is valid whatever the dispersion, and
it measures as well calibrated: **5.30%** of null cells at p ≤ 0.05 against an
ideal 5.00%.

> Use `p` for significance. `z` is fine for a picture, and `SaveChannel` stores
> both, but do not threshold z at 3 without reading the calibration gate 6 prints.

`P.surrogate` selects `'within'` (the specified design, default) or `'cross'`.

## Runtime, measured

`RunBetaDemo`, 120 s synthetic channel, 19 epochs, 30 surrogates: **97 s total**,
of which the filter banks are ~55 s and the surrogates ~8 s.

Scaling the measured 0.026 ms/cell to the real target — 30 min, 300 epochs,
17 × 37 grid, 100 surrogates — gives **188,700 cells × 101 ≈ 8.3 min** of
modulation index, plus ~3 min of filtering. Comfortably inside the plan's
30 min/channel estimate, because the blocked path came in 3× faster than assumed.

The decision the plan flags still stands: 64 channels single-threaded is a long
job, and dropping to 50 surrogates halves the surrogate step. With the
permutation p, 50 surrogates gives a p resolution of 1/51 ≈ 0.02, which is
enough to threshold at 0.05 but not at 0.01. Choose on that basis, not on z.

## Files

```
code/
  params.m              every setting, and the only place they live
  LoadCSC.m             .ncs -> notched LFP, with gap and clip checks
  MakeEpochs.m          the epoch table (drops nothing)
  FilterBanks.m         slow phase + slow envelope + fast envelope
  PhaseBins.m           bin membership, computed once   <- read this one
  MIFromBins.m          the modulation index, many bands per pass
  ModIndexFast.m        convenience wrapper over the two above
  CFC.m                 the grid, the surrogates, the permutation p
  ThetaPower.m          band power per epoch, from the same analytic signal
  ChannelQC.m           the seven-panel figure
  SaveChannel.m         the self-contained .mat
  RunBeta.m             the driver + scoreboard
  RunBetaDemo.m         the whole thing on synthetic data
  SyntheticChannel.m    LFP with coupling you chose
  betapath.m            path setup
  gates/gate1..gate8    one file each
  test/test_ModIndexFast.m   gate 4, re-runnable, no recording needed
```

Dependencies are used in place, not copied: `eegfilt.m` and `ModIndex_v2.m` from
`../01_core_tort/`, `read_csc.m` from `../03_vacc_pipeline/lib/`. The beta checks
itself against the *same* reference implementation the old pipeline ran.

## In the GUI: CFCScope

The beta run answers "does this channel have coupling" for a whole channel,
offline. **CFCScope**, in the BARRY GUI Toolkit, answers "does *this window*"
while you are looking at it — the question you actually have while scrolling.

It is a copy of `05_explainer/cfc_core.py`, which is the checked Python port
of `eegfilt.m` and `ModIndex_v2.m`, living at `BARRY GUI/backend/cfc.py`.
Copied rather than imported: a clone that carries only the app has to work.
`BARRY GUI/tools/cfc_check.py` re-runs the explainer's assertions against the
copy, so it cannot drift — the modulation index still matches `ModIndex_v2.m`
to 1e-12.

Measured there, 60 s window at 3 kHz over the `params.m` grid:

| | seconds |
|---|---|
| filter banks (17 slow + 37 fast) | 3.3 |
| 629 modulation indices | 0.3 |
| + 50 surrogates | 16 |
| + 100 surrogates | 32 |

So a map is a four-second wait and a tested map is half a minute, and the GUI
treats those as different interactions: the null is opt-in and the form
states the cost first.

### Two places it deliberately differs from this pipeline

**It anti-aliases before decimating.** The caveat under "Known caveats" above
— `read_csc` doing `Samples(1:10:end)` with no low-pass, folding everything
above ~1628 Hz into the 20–200 Hz amplitude axis — is a decision this README
flags and does not take. CFCScope takes it: `scipy.signal.decimate`, which
filters first. A probe confirms the difference is not academic; a 8 kHz tone
survives naive decimation at full amplitude and is rejected to 0.1% by the
filtered one. **So its numbers are better than `newFCSE`'s and not
bit-comparable with them**, and it says so in every caption.

**It bins the phase with `floor` rather than the literal comparisons.**
`PhaseBins.m` had to reproduce `ModIndex_v2`'s per-bin comparisons exactly
because gate 4 asserts at 1e-12, and the ulp-level disagreement on a bin edge
is real. It is also measure-zero for Hilbert phase, which is the only kind
CFCScope ever sees, so it uses one `bincount` pass and asserts agreement with
the literal loop on Hilbert phase in its check script.

### What it makes visible that a comodulogram usually hides

`realised_bw()` measures the half-power width of the filter `eegfilt`
actually designs, rather than reporting the width that was asked for. The
result is on every axis and in every caption:

| band, as labelled | really |
|---|---|
| 4.0–4.5 Hz (0.5 Hz) | 1.14 Hz |
| 8.0–8.5 Hz (0.5 Hz) | 2.28 Hz |
| 12.0–12.5 Hz (0.5 Hz) | 3.42 Hz |
| 200–210 Hz (10 Hz) | 57 Hz |

Which is `verify.py` item 8 made visible where it matters. The theta axis
overlaps heavily — it is a smooth read of where the rhythm sits, not
seventeen independent measurements — and the panel says so rather than
letting the reader assume otherwise.

## Known caveats, inherited not introduced

- **`read_csc` decimates without an anti-alias filter** — `Samples(1:10:end)`.
  Content above the new Nyquist (~1628 Hz) folds into the analysed band. Left
  alone so gate 5 stays a like-for-like comparison with `newFCSE`, but it is a
  real risk on the 20–200 Hz amplitude axis and worth a decision before the
  full run.
- **`read_csc` overwrites the true record timestamps** with a uniform grid, so
  gaps are invisible in its output. `LoadCSC` re-reads the raw stamps itself.
- **`P.slowBW = 0.5` is narrow.** It matches `newFCSE`, and it is part of why the
  surrogate null is under-dispersed. `RunBetaDemo` uses `fastBW = 20` because a
  10 Hz-wide band cannot carry 7 Hz modulation — its sidebands fall outside the
  band. Gate 3 prints that arithmetic.

## Before you pick the beta channel

Obvious theta, a control animal (not IED+), at least 10 minutes, and — this one
matters — **from a recording already run through `newFCSE.m`**, because gate 5
compares against that output and cannot run without it. Of the eight gates, it is
the only one the synthetic demo cannot stand in for.
