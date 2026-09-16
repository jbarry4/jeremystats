# 05_explainer — how the CFC math in this repo actually works

Written to answer one question: what happens to a raw `.ncs` trace between
`read_csc` and a comodulogram, and how much of what you see in the picture is
the brain versus the analysis.

Everything here runs on **synthetic data only**. No recording from the lab is
read, and none is needed — the point is that you can set the ground truth and
then watch what the pipeline reports about it.

## Files

| File | What it is |
|---|---|
| `cfc_core.py` | Python port of `eegfilt.m`, `ModIndex_v2.m` and the `newFCSE.m` grid, plus the synthetic LFP generators. Reads next to the MATLAB. |
| `make_comodulograms.py` | Builds and caches the three comodulograms the figures reuse (real coupling / pink noise / spike train), on the lab's own grid. |
| `fig01`…`fig11_*.py` | One script per figure. Each is standalone: `python3 fig05_comodulogram.py`. |
| `style.py` | Shared plot styling. |
| `verify.py` | Asserts every quantitative claim the write-up makes. `python3 verify.py` → 21 checks. |
| `figures/` | Rendered PNGs. |
| `_cache/` | Memoised intermediates; safe to delete. |

## Requirements

`numpy`, `scipy`, `matplotlib`. Nothing else.

```
python3 make_comodulograms.py     # ~20 s, fills the cache
for f in fig*.py; do python3 "$f"; done
python3 verify.py
```

## The figures

1. **fig01** — raw LFP → phase band → phase → amplitude band → envelope. The
   whole front end of the pipeline in five panels.
2. **fig02** — the analytic signal, and the amplitude-vs-phase scatter that MI
   summarises.
3. **fig03** — the 18-bin amplitude distribution P(j) at three coupling
   strengths. This is the object MI is computed from.
4. **fig04** — P(j) → entropy → MI, and how MI grows with true modulation depth.
5. **fig05** — the comodulogram, with one pixel unpacked back into its histogram.
6. **fig06** — `eegfilt` is a constant-Q filter (Q ≈ 3.3). The nominal 0.5 Hz and
   10 Hz bandwidths in the drivers are not what the filters deliver.
7. **fig07** — because of (6), the largest phase frequency detectable at
   amplitude frequency `fa` is about `0.15 * fa`. Identical simulated coupling
   reads out anywhere from MI ≈ 0.07 to MI ≈ 0 depending on where it sits.
8. **fig08** — sharp transients with no coupling in them at all still produce a
   comodulogram. Directly relevant to IED-heavy recordings.
9. **fig09** — MI is biased upward by ~1/N and has no meaningful zero; what a
   surrogate null does about it.
10. **fig10** — the `Notes_ComodAnalysis.m` / `CFCReader.R` band collapse, drawn
    on the map, with the exact Hz ranges those column indices correspond to.
11. **fig11** — the same no-coupling map under three colour choices.

## Things the figures establish about *this* code

- `MI = KL(P || uniform) / log 18`. Verified identical to `ModIndex_v2.m`.
- The grid is 51 phase columns × 37 amplitude rows; cell (4,4) is 2.75 Hz phase /
  40 Hz amplitude, which matches the comment in `Notes_ComodAnalysis.m`.
- The R/MATLAB band slices are, in Hz: Delta 1.25–2.25, Del-Theta 2.25–5.25,
  Theta 4.25–12.25, Beta 12.25–20.75. They overlap at shared boundary columns,
  and columns 41–51 (21.25–26.25 Hz) are never used.
- `eegfilt`'s realised −3 dB bandwidth is ≈ 0.30 × the lower cutoff and does not
  depend on the sampling rate. The nominal bandwidth only binds at the bottom of
  each axis.
