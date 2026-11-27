# Verifying the PTEN steps

Numbers a rerun must reproduce, stage by stage, and the cheapest way to check each. Three depths of check:

- **A. Recompute from the frozen files** (no Jarvis, no raw recordings): rerun the battery, the ML summary and the menus
  from the netfiles mirror and compare the tables. Hours, any machine with Python.
- **B. Rebuild from Jarvis's saved artifacts** (Jarvis running, artifacts synced, no raw reads): workflow runs and room
  versions from their saved payloads.
- **C. Rebuild from raw** (Jarvis plus the raw recordings on netfiles or the VACC): Root Canal reads, X-ray reads, the
  2 kHz menu reads. Only this checks the reading itself.

Write every check's output to a new folder; never overwrite the PTEN files.

## Stage 1: Root Canal (B, or C for the reads)

| check | expected |
|---|---|
| target pool `3561fc988afd` | 18 recordings, 5,100 events |
| Halo workflow `6fa7fef7b7a3` run classes | ds 4,381, halo_ds 352, both 79, halo_amb 106, pspike 137, halo_pspike 17, neither 25, unmeasured 3 |
| Strict workflow `a7eee6a6ca9f` run classes | ds 4,098, both 24, pspike 192, neither 783, unmeasured 3 |
| halo | reach 2, margin 1.5; captured ds 352, extended 106, far 25, pspike 17 |
| border settings | DS 5% (Halo) or 10% (Strict) grace Snap around the control pool; P-spike 5% around 39 hand-sorted IEDs |

The saved runs are in `code/menus/rc_borders.json` (borders, halo, counts) and, per event, in `rc_events.pkl` on
netfiles (`claude_scratch_PTEN_2026-11-11_to_11-25/menu/`).

## Stage 2 and 3: Extraction Room and the freeze (A)

Load with `dsdata.load("v6")` (Halo) and `dsdata.load("v8")` (Strict) from the battery folder:

| set | recordings | events | analyzed (m6 and m51 out) |
|---|---|---|---|
| Halo (`ds_v6.pkl`, room v9 = v11) | 18 | 4,733 | 4,525 in 16 mice |
| Strict (`ds_v8.pkl`, room v10 = v12) | 18 | 4,098 | 3,905 in 16 mice |

Events per mouse on the Halo set, with the winner's DS1 / DS2 counts (names by anatomy; m21 and m51 have no winner):

| mouse | events | DS1 / DS2 | mouse | events | DS1 / DS2 |
|---|---|---|---|---|---|
| m2 | 110 | 104 / 6 | m8 | 363 | 52 / 311 |
| m21 | 70 | none | m33 | 217 | 34 / 183 |
| m22 | 226 | 207 / 19 | m1 | 188 | 12 / 176 |
| m26 | 273 | 14 / 259 | m7 | 125 | 15 / 110 |
| m59 | 492 | 25 / 467 | m13 | 353 | 18 / 335 |
| m60 | 562 | 522 / 40 | m28 | 335 | 33 / 302 |
| m61 | 189 | 16 / 173 | m3 | 151 | 141 / 10 |
| m6 (out) | 203 | 11 / 192 | m5 | 689 | 628 / 61 |
| m51 (out) | 5 | none | m34 | 182 | 157 / 25 |

## Stage 4: the battery (A)

| table | measures | tests | share with P < 0.05 |
|---|---|---|---|
| `merged` (Halo + Strict) | 1,378 | 12,885 | 3.6% |
| `merged_filters` | 3,591 | 32,939 | 4.7% |
| `merged_around` | 5,864 | 39,882 | 3.5% |

A rerun of `measures.py` and `analyze.py` on the frozen data should give the same P values to float precision. Compare
`tests.pkl` row by row on the measure id (`family|name|event_set|classifier|variant`) and contrast.

## Stage 5 and 6: machine learning (A from the leaderboards; a rerun on the VACC is stochastic)

From `er2_store/runs/r006/leaderboard.json` (and `Lab Figures/Archive/2026-11-23_DS_PTEN_112326/ml_runs/ML_summary.txt`):

| run r006 (Halo, all events) | models at the bar | best |
|---|---|---|
| iedpos_vs_iedneg | 14 of 52 | 0.95 (context, deep sets) |
| pten_vs_ctl | 3 of 52 | 0.83 |
| low_vs_high | 2 of 52 | 0.83 |
| ied3 | 3 of 52 | 0.84 |
| ko_pct | 0 of 52 | rank correlation 0.70 |

Held-out calls (the 14 IED models): 8 of 9 PTEN mice right; m3 is called IED- by all 14 (one model scores it exactly 0.50);
m7 is called IED-. Neural-network runs depend on seeds, so a rerun should land near these counts, not on them.

## Stage 7: the menus (A for the pages built from the battery; C for the 2 kHz reads)

DS story menu (11-23):
- Fast power at the DS (240 to 420 Hz): every IED+ mouse above every control (P 1.9e-05); every IED- mouse below every
  control (P 0.003); m7 lowest of all.
- m7 is an outlier among the high-knockout mice (Grubbs P 0.001) and off the PTEN knockout line (P 0.004), not among the
  IED- mice (P 0.13).
- On the common CSD scale, IED- DS carry about half the control current (upper sink peak P 0.012, lower P 0.036).
- BTs: 0.56 to 1.89 per minute in IED+ mice, at most 0.075 elsewhere.
- DS1 sits farther out than DS2 in 14 of 15 (upper) and 13 of 15 (lower) recordings; the gap is smaller in IED+ than IED-
  (P 0.035).

Jeremy menu (11-24): the one-line answers in its README. Two checks worth repeating:
- Q4 against Q7: IED+ DS carry more fast power than control DS (P 1.9e-05) but not more MML current.
- The DS1 rise effect (P 0.029) disappears when each type is timed at its own deepest contact (P 0.46); no page claims it.

Layer check (11-25): 52 of 62 layer results keep their verdict, 6 lose significance, 4 become significant, none reverses;
`Layer_Check_112526/tables/old_vs_tight_every_layer_result.csv` has every row.

To recompute a menu: copy `code/menus` next to the netfiles copies of its inputs (`tables/`, `reads/`, `reads_ds/`,
`rc_events.pkl`, `uprof.pkl`, `profiles_ds.pkl`, `dsied.pkl`, `timing.pkl`, `jeremy_*.pkl`), fix the paths in PATHS.md,
and run the order in PIPELINE_PTEN.md step 7. Compare the new `jeremy_battery.pkl` and `jeremy_freq.pkl` with the saved ones
before drawing pages.

## Known corrections a verifier should not "rediscover"
- 20 um per contact, not 50 (every um in the 11-16 to 11-20 documents is 2.5 times too large).
- The LFP peak position result is not a reference artifact (a common reference cannot move where the maximum is).
- Jarvis's DS1 / DS2 naming can be backwards when both types share a contact; the battery renames by anatomy.
- The menu's MML / OML rule rests on the average DS sink; see the layer check.
