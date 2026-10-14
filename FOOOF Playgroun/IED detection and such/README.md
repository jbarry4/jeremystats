# IED detector study — PTEN hand-sorts

Can the lab's line-length IED detector (Kleen's `LLspikedetector.m`) recover
every IED a person confirmed? If so, at what settings? What is the junk that
comes along with them, and what removes it?

Everything here is plain Python run against raw `.ncs` data. The study itself
is not wired into the GUI. Its final specification is Doppler's default.

## Ground truth

The PTEN hand-sorts in the Event Bank: 10 recordings, 64 channels, 30 kHz,
6.8 h in total.

| label | n |
|---|---|
| Solid (the target) | 170, of which **169 are reachable** — one m28 s7 stamp sits 3.3 s past the end of its file |
| Sputter | 44 |
| Flag | 68 |
| Garbage | 419 |
| never reviewed | 2,760 |

Two populations of Solid, and the difference matters:

- **sorted** (m5 s2, m5 s7, m13 s2, m13 s17, m28 s2, m34 s5, m34 s8; 92
  Solids). These came from the original detector, filtered to events on 5–10
  even channels, then sorted by eye. About 95% of the "never reviewed"
  candidates sit outside 5–10 channels: that rule removed them unseen.
- **confirmed** (m3 s2, m3 s7, m28 s7; 77 Solids). These came from a later,
  separate pass that marked Solids only. They are the only Solids
  independent of the original detector.

## Headline results

**1. The original detector misses most independently found IEDs.** As the lab
ran it (raw 30 kHz, 40 ms, even channels, one pooled 99.9th percentile), it
catches 111 of 169 Solids with 4,447 detections. On the *confirmed*
recordings it catches 19 of 77; with the 5–10 rule, 9 of 77. At raw 30 kHz,
no setting reaches 100%.

**2. The recommended specification, catching all 169 with room to spare.**
This is Doppler's default (the "Validated" method in The Storm):

```
common-average reference (good channels) -> 60 Hz notch + harmonics
-> band-pass 20-300 Hz
-> line length, 15 ms window, at 2 kHz
-> even channels, bad ones excluded
-> one pooled threshold at the 99.9th percentile (per recording)
-> merge gaps < 300 ms -> keep events >= 12.5 ms
-> keep events on >= 7 even channels
```

That gives **2,595 detections (15.4 per Solid)**. It catches 147 of your 419
Garbage, against 419/419 for the original. It still catches all 169 with
the threshold one step higher (99.92th) or one more channel required (8).
Cheaper settings exist, but they have no margin. See "Choosing the default"
below.

**3. If only the old sorted population matters**, the original plus the 5–10
rule with bad channels excluded gets 92/92 with 786 detections. This is
circular: those Solids were selected from that pipeline's output.

**4. On the confirmed recordings alone**, CAR + ≤300 Hz + 40 ms + ≥7 even
channels catches 77/77 with 389 detections (5 per Solid).

### What each fix is worth (all at 169/169)

| setting | detections |
|---|---|
| raw (2 kHz), per-channel threshold | 6,676 |
| ≤300 Hz, per-channel threshold | 5,144 |
| ≤300 Hz + ≥6 channel rule | 2,725 |
| CAR + 10–300 Hz | 3,123 |
| **CAR + 10–300 Hz + ≥6 channel rule** | **2,491** |
| 1–70 Hz (the IED preset) | 9,327 — worst; line length on slow waves picks up every slow wave |
| notch only | 11,358 — the notch alone does nothing useful |

- The channel rule only needs a **lower** bound. No upper limit (10, 12 or
  16) ever made a setting cheaper without losing a Solid.
- Without CAR, a per-channel threshold beats the pooled one. With CAR, the
  pooled one wins, because CAR already removes the dominant-channel problem.
- Merging at 300 ms beats 100 ms. A 12.5 ms minimum is as good as 25 ms.
- Excluding bad channels matters a little (2,491 against 2,508).

## Choosing the default (steps 7–10)

The table above came from a coarse grid. The choice was finished in four
steps.

1. **A finer grid (step 7, 942 settings).** It searched around the first pick
   (CAR, 10–300 Hz, 20 ms, ≥6 channels: 2,491). The cheapest setting that
   still catches all 169 needs only 2,072 detections.
2. **That cheapest setting is fitted (step 8).** For each recording in turn,
   the cheapest setting was chosen on the other nine and scored on the one
   left out. Over the ten holdouts, Solids were missed four times.
   - A setting is said to have **room on both sides** when it also catches
     every Solid with the next percentile up and with one more channel
     required.
   - Choosing the cheapest setting with room on both sides never missed.
   - The first pick (2,491) has no room on either side. Run in Doppler's
     production engine it lost two Solids (m5 s7, m13 s2). The only cause was
     that the engine takes the exact percentile where the study sampled
     every tenth value.
3. **Past the edges of the grid (step 9).**
   - Every top setting used the shortest window tried (15 ms) and the
     longest merge (500 ms). So 10 and 12.5 ms and a 750 ms merge were
     tried too.
   - A longer merge looks cheaper only because it folds two IEDs into one
     candidate with one stamp. At 500 ms, two hand-sorted pairs (0.29–0.46 s
     apart) become one candidate each.
   - No setting gives every Solid a candidate of its own, because the
     hand-sorts contain a duplicate stamp 2 ms from another.
4. **The choice (step 10).**
   - Keep the lab's own event definition (merge at 300 ms).
   - Catch all 169, with room on both sides, at the fewest detections:
     **CAR, 20–300 Hz, 15 ms, 99.9th, ≥7 channels, 2,595**.
   - 12.5 ms with ≥8 channels ties it (2,592) with slightly more Garbage
     (148 against 147). 15 ms is no longer at the edge of the grid.
   - The low edge of the band barely matters: 5, 10, 20 Hz and no high-pass
     are all within a few percent.

`validate_production.py` runs Doppler's own engine, the function a VACC node
runs, on the raw `.ncs` files and scores it against the hand-sorts. At these
defaults it gets **169/169 in 2,568 detections**, catching 155 of the 419
Garbage. The study's 2,595 sampled every tenth value for the percentile. The
production engine uses all of them.

The hand-sorted stamps are on concatenated time, so the script first moves
them onto the recording's own clock. Without that step, the last Solid of
m34 s8 sits 119 ms past a pause in acquisition and scores as missed. A VACC
run of M34 s5 matched the run on this computer exactly: 135 events, the same
threshold and the same stamps.

## Why Garbage gets in (`why_garbage.py`, `why_garbage_within.py`)

Measured within the five recordings that have both Solid and Garbage labels
(82 Solid, 419 Garbage).

1. **A percentile sets the count, not the IEDs.** 0.1% of channel-time crosses
   by construction. m28 s2 has 1,010 candidates for 8 Solids; m5 s2 has 184
   for 3.
2. **Any one channel starts an event, against one pooled threshold.** So the
   noisiest channel runs the list.
   - m28 s2: CSC28 makes 54% of all crossings and tops 88% of the unreviewed
     candidates, but 0 Solids.
   - m3 s2: CSC64 makes 45%. m13 s2: CSC36 makes 36%.
   - m34 s5: CSC8 makes 47%. It is on the bad list, but the original kept it
     because it ran on the even-channel `.mat`.
   - 80–85% of crossing time is a single channel on the worst recordings.
3. **Raw 30 kHz line length is dominated by fast activity.** Line length per
   second is 4 × amplitude × frequency, so a 30 µV ripple at 600 Hz counts as
   much as a 1,800 µV wave at 10 Hz. On the triggering channel, 65% of a
   Garbage event's line length comes from 300–900 Hz, against 51% for Solids
   (on m13 s17 that separates them almost perfectly). A unit or EMG burst on a
   small slow wave crosses.
4. **Surviving Garbage is mostly the same discharge, weaker.**
   - Amplitude is 66% of the recording's typical Solid (AUC 0.84).
   - It is barely over threshold: 1.12× against 1.31× (AUC 0.86).
   - On m28 s2 the average Garbage has the Solids' depth profile, smaller and
     about 3× wider (`out/figs/avg_m28_s2.png`).
5. **Common-mode activity.** CAR removes 30% of a Garbage event's line length
   but only 15% of a Solid's (AUC 0.71).

**Not causes:**
- 60 Hz mains (Garbage has *less* power in the 60 Hz band than Solids).
- Width and polarity.
- Bad channels, apart from CSC8 on m34 s5.

## What the remaining junk is (`step6_shmutz_by_setting.py`)

Each detection without a Solid is put in the first type it belongs to. A type
is defined by the Solids: a detection is "too small" only if it is smaller
than *every* Solid on its recording, and so on. So no real IED could land in a
junk type. The measurements are taken on the raw signal against the original
detector's threshold.

| type | original (4,337 extra) | recommended (2,325 extra) |
|---|---|---|
| dominant channel tops it | 1,435 (33%) | 235 (10%) |
| line length driven by 300–900 Hz | 1,564 (36%) | 260 (11%) |
| common-mode | 159 | 292 (13%) |
| smaller than every Solid | 217 | 304 (13%) |
| barely reaches the threshold | 238 | 567 (24%) |
| too few channels | 275 | 194 (8%) |
| **IED-like on every measure** | 449 | **473 (20%)** |

The original's junk is two-thirds dominant-channel and fast-activity crossings.
The recommended pipeline removes 84% and 83% of those, and its remaining junk
is mostly weak events. The 473 "IED-like" detections are inside the Solids'
range on every measurement. They are probably missed IEDs or Sputter, and are
worth a look.

## Matching waveforms across depth (`classifier_fast.py`)

Template matching only, as decided: 170 Solids is too few to train a model.

- **What it does.** Each recording's leave-one-out average Solid is correlated
  with each candidate, over every good channel. 48 variants were compared.
- **Best variant.** 3–100 Hz, template-aligned, shape × size scoring: median
  per-recording AUC 0.80 for Solid against Garbage.
- **Where it fails.** On m34 s5 it scores 0.32, with only 6 Solids.
- **Why it can't filter.** A threshold that keeps every Solid still lets 92%
  of Garbage through. Use it to order candidates for review, never to discard
  them.
- **Why it is weak.** Garbage is mostly the same generator, weaker, so its
  shape matches. Relative amplitude alone (AUC 0.84) separates them better.

## Caveats

- The original detector is reproduced from the 30 kHz line length, with its
  percentile taken from a 0.001-decade histogram. The exact percentile and
  bad-channel mask of the lab's run are unknown, so channel counts near the
  5-channel boundary are approximate.
- The sweep runs at 2 kHz. Only the `orig30k` rows are at 30 kHz.
- A Solid counts as caught if a detection window, widened by 100 ms either
  side, contains its stamp.
- "Garbage caught" and "unreviewed caught" are not precision. The
  unreviewed candidates were never labelled.
- Junk-type bounds are drawn from the same Solids they are applied to, and
  are measured on the raw signal.

## Files and how to run (PowerShell)

| step | what it does |
|---|---|
| `step1_ground_truth.py` | bank → `out/ground_truth.json` |
| `step2_cache.py` | one pass over the raw data → `Desktop\IED DATA\sweep_cache` (16 GB; delete when done) |
| `step3_sweep.py`, `step3b_rank.py` | 5,280 settings × 10 recordings → `out/sweep*`; the original's baseline is the `orig30k` rows |
| `step5_channel_rule.py`, `rank_subsets.py` | the strongest settings with a channel-count rule, ranked on all ten and on each recording group |
| `why_garbage.py`, `why_garbage_within.py` | per-stamp measurements, Solid against Garbage, average-waveform figures |
| `classifier_design.py`, `classifier_fast.py` | waveform-across-depth template matching, validated on the labels |
| `step6_shmutz_by_setting.py` | the junk types for six settings → `out/shmutz_types.csv` |
| `step7_refine.py` | a finer grid around the first pick → `out/refine/` |
| `step8_holdout.py` | choose on nine recordings, score on the tenth → `out/holdout.json` |
| `step9_edges.py` | 10 and 12.5 ms windows, a 750 ms merge, and one-candidate-per-Solid counting → `out/edges/` |
| `step10_choose.py` | the choice over steps 7 and 9 together → `out/chosen.json` |
| `validate_production.py` | Doppler's production engine on all ten recordings, scored against the hand-sorts (`$env:SPEC` tries another setting) |
| `detector.py`, `ied_common.py` | shared code |

`step4_shmutz.py` is superseded by step 6. It used only the template score,
which turned out to be weak.
