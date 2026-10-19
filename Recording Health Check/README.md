# Recording Health Check — Neuralynx concat issues

Diagnosis of `D:\PTEN\PTEN\M8_Pten\M8s9feb8\2024-02-09_16-43-46`, and two
scripts that generalise the check to any Neuralynx recording folder.

---

## 1. What a "concat issue" is

Cheetah writes each `.ncs` file as a stream of 1044-byte records. Each record
carries up to 512 samples plus the hardware timestamp (µs) of its first sample:

```
uint64  qwTimeStamp        microseconds
uint32  dwChannelNumber
uint32  dwSampleFreq
uint32  dwNumValidSamples  <= 512
int16   snSamples[512]
```

When acquisition hiccups — a dropped packet, a pause/resume, a disk stall —
Cheetah closes the current record early (`dwNumValidSamples < 512`) and the
next record's timestamp jumps forward by more than one record duration. The
file is no longer one continuous block of samples: it is several **segments**
separated by **gaps of data that were never written**.

neo/spikeinterface detect this and expose the file as a **multi-segment**
recording. That single fact explains both Toothy behaviours:

| | behaviour |
|---|---|
| **Old Toothy** (`Toothy/Toothy-main`) | Calls `recording.get_num_samples()` with no `segment_index` → `ValueError: Multi-segment object. Provide 'segment_index'`. The recording never loads. |
| **New Toothy** ("Gold and Green") | [`data_processing.py:267-269`](../../Toothy%20but%20Gold%20and%20Green/Toothy/data_processing.py#L267-L269) calls `spikeinterface.concatenate_recordings([recording])`. It loads — but the gaps are **closed**. |

Concatenation glues the segments end to end and rebuilds the time axis as
`t_concat(i) = i / fs`. Every sample after a gap is therefore labelled with a
time **earlier than its true wall-clock time**, by the cumulative duration of
all preceding gaps.

The error is a **step function**, not a drift: zero in segment 0, then constant
within each later segment. Nothing downstream records that this happened.

---

## 2. Diagnosis of this recording

`M8s9feb8\2024-02-09_16-43-46` — 64 channels, 30 kHz, Cheetah 6.4.2,
DigitalLynxSX, opened 2024/02/09 16:43:46.

**Verdict: the concat issue is present.** 8 segments, 7 gaps, **0.1225 s of
data that Cheetah never wrote**. All 64 channels agree on the boundaries.

### The gaps

Trouble is confined to a ~110 s window in an otherwise clean 35-minute session:

| after record | true time (s) | gap (ms) | cumulative shift (ms) |
|---|---|---|---|
| 103267 | 1762.416 | 50.27 | 50.27 |
| 103268 | 1762.467 | 33.30 | 83.57 |
| 103271 | 1762.515 | 7.60 | 91.17 |
| 103272 | 1762.531 | 9.90 | 101.07 |
| 104066 | 1776.058 | 5.80 | 106.87 |
| 104310 | 1780.203 | 7.43 | 114.30 |
| 109665 | 1871.571 | 8.23 | 122.53 |

### The segment map

| seg | samples | concat t0 (s) | true t0 (s) | error (ms) |
|---|---|---|---|---|
| 0 | 52,872,637 | 0.000000 | 0.000000 | 0.000 |
| 1 | 20 | 1762.421233 | 1762.466582 | 45.349 |
| 2 | 420 | 1762.421900 | 1762.500549 | 78.649 |
| 3 | 240 | 1762.435900 | 1762.522515 | 86.615 |
| 4 | 405,401 | 1762.443900 | 1762.540415 | 96.515 |
| 5 | 124,176 | 1775.957267 | 1776.063762 | 106.495 |
| 6 | 2,740,833 | 1780.096467 | 1780.210456 | 113.989 |
| 7 | 7,586,608 | 1871.457567 | 1871.579491 | 121.924 |

**Worst-case error: 121.9 ms = 3658 raw samples at 30 kHz.**

### Corroborating evidence

Each of these was checked directly, not inferred:

1. **16 short records** (`nb_valid` ∈ {20, 40, 61, 77, 100, 232, 240, 264, 300,
   328, 425}) against 512 everywhere in a healthy file. 5985 samples never
   written.
2. **spikeinterface confirms 8 segments** with exactly the sample counts above
   (neo 0.14.1 / spikeinterface 0.102.3, under `toothy_env`).
3. **Old Toothy really does crash** — `get_num_samples()` raises
   `ValueError: Multi-segment object. Provide 'segment_index'`.
4. **`toothy/DATA.hdf5` `lfp_time` is perfectly uniform — zero discontinuities.**
   It ends at 2124.3445 s while the raw file ends at 2124.4661 s. The gaps were
   closed and nothing recorded it.
5. **`binary/CSC_Raw.dat` is 8,157,482,880 bytes** = 63,730,335 × 64 × 2,
   a byte-exact match to the *concatenated* sample count. Kilosort ran on
   concatenated data too.

### Why the jitter is not the signal

Nominal `fs` is 30000 Hz but the hardware clock actually runs at **29998.6 Hz**.
Per-record timestamp residuals of ±512 µs are ordinary clock jitter. The real
breaks are three orders of magnitude larger (up to 50,266 µs) and every one of
them coincides with a short record.

This matters for the check's threshold: a naive "any inter-record interval that
deviates by more than half a record" rule reports **9** gaps here, while neo
reports **7** breaks. The scripts reproduce neo's rule exactly so the answer
matches what Toothy actually did.

---

## 3. What this does to the DS output

`ALL_DS` in `DATA.hdf5` holds 21,036 rows over 63 channels = **3463 distinct
event times**. Of those, **1027 distinct times (5547 rows, 26.4%) fall after
the first gap** and carry an offset of 96.5–121.9 ms.

A dentate spike is 10–20 ms wide. A 122 ms offset is 6–12 event-widths — seek
to that time in the raw file and you are looking at unrelated trace. Before
1762.47 s the two agree exactly, which is why this passes a casual spot-check.

**Answer to "does mixing raw viewing with corrected-version DS timestamps cause
issues?" — yes, for everything after 1762.47 s.**

Two things are *not* broken:

- `idx` / `idx_peak` / `idx_start` / `idx_stop` index Toothy's own
  concatenated arrays and stay self-consistent. Only the mapping back to raw
  `.ncs` is wrong. **Use indices inside Toothy; use corrected times to leave it.**
- Kilosort unit times and Toothy DS times are both in concatenated time, so
  they agree *with each other*. The raw `.ncs` is the odd one out.

### A hazard beyond the offset

Toothy band-pass filters and peak-detects straight across each stitch, where
the LFP steps discontinuously. **9 distinct DS times sit within 125 ms of a
boundary** and may be filter ringing rather than real dentate spikes. They are
flagged `near_stitch` in the CSV.

---

## 4. The three time bases

This is the part that bites, and it is worth stating plainly. This recording
has **three different, mutually inconsistent answers** to "how long is it?":

| basis | value | who uses it |
|---|---|---|
| **record-index time** — `n_records × 512 / fs` | 2124.544 s | BARRY GUI's viewer (`nlx.read_ncs_range` seeks by record) and `extras.session_health` duration |
| **concatenated time** — `valid_samples / fs` | 2124.3445 s | Toothy DS times, `lfp_time`, LFP arrays, `CSC_Raw.dat`, kilosort units |
| **true Neuralynx clock** | 2124.4661 s | the `.ncs` record timestamps themselves |

```
record − true   = +77.9 ms
concat − true   = −121.6 ms
record − concat = +199.5 ms
```

Roughly 200 ms of spread, and no artifact in the pipeline declares which basis
it is in. On a clean recording all three collapse to the same number, which is
exactly why this went unnoticed.

---

## 5. The scripts

Both are plain Python. The health check needs only numpy; the diagnostic adds
pandas + h5py only when reading a `DATA.hdf5`.

### `ncs_concat_health_check.py`

Point it at a recording folder. It is a faithful port of neo's
`NcsSectionsFactory._buildNcsSections`, including the fast path and
spikeinterface's non-strict 4267 µs tolerance, so it needs no Toothy
environment and returns the same segmentation Toothy saw.

```bash
python ncs_concat_health_check.py "D:\PTEN\...\2024-02-09_16-43-46"
python ncs_concat_health_check.py "<folder>" --all-channels --json out.json
```

| flag | meaning |
|---|---|
| `--channels N` | how many channels to spot-check (default 4) |
| `--all-channels` | parse every `.ncs` (slow; reads the whole dataset) |
| `--strict` | neo's `strict_gap_mode=True` tolerance instead of spikeinterface's |
| `--max-gaps N` | limit the printed gap table (default 40) |
| `--json OUT` | machine-readable findings |

Exit code: `0` clean, `1` concat issue, `2` error.

The report separates **time lost to gaps** from **nominal-vs-actual clock
drift**. Conflating them makes clean files look like they lost data — on a
clean 48-minute session the drift term alone is −20 ms.

### `ds_concat_timestamp_diagnostic.py`

Builds the concat↔true mapping from the raw files, verifies whether `lfp_time`
really is gap-free, quantifies the per-event offset, and writes a corrected CSV.

```bash
python ds_concat_timestamp_diagnostic.py "<folder>" --csv DS_corrected.csv
python ds_concat_timestamp_diagnostic.py "<folder>" --times 1800 2100
```

| flag | meaning |
|---|---|
| `--toothy-dir DIR` | where `DATA.hdf5` lives (default `<folder>/toothy`) |
| `--csv OUT` | DS table plus corrected columns |
| `--times T [T...]` | convert these concatenated times and exit |
| `--window-ms MS` | stitch-artefact half-window (default 125, matching `ds_wlen`) |

The CSV keeps every original column and adds `segment`,
`time_toothy_concat_s`, `time_true_s`, `time_error_ms`, `nlx_timestamp_us`,
`raw_sample_index`, `near_stitch`, `start_true_s`, `stop_true_s`.

`nlx_timestamp_us` is the absolute Neuralynx timestamp — the value to use when
navigating raw data in any Neuralynx-native tool.

---

## 6. Dataset-wide scan

Scanning 25 recordings under `D:\PTEN\PTEN`, **8 are affected**:

| recording | segments | data lost |
|---|---|---|
| `M8_Pten\M8s9feb8\2024-02-09_16-43-46` | 8 | 0.1225 s |
| `M34_ptenblind\m34s8jun10\2024-06-10_17-00-07` | 9 | 0.1178 s |
| `M8_Pten\M8s2feb6\2024-02-06_17-52-07` | 6 | 0.0606 s |
| `M1_Pten\M1ptens2oct2\2023-10-02_16-58-03` | 2 | 0.0235 s |
| `m29_ptenblind\m29s4jul23\2024-07-23_15-31-49` | 3 | 0.0068 s |
| `m29_ptenblind\m29s1jul23\2024-07-23_13-03-51` | 2 | 0.0009 s |
| `M5_Pten\M5s7nov17\2023-11-17_14-23-24` | 2 | ~0 |

The other 17 come back CLEAN (single segment), which is the check discriminating
rather than always firing.

---

## 7. Caveats

- The segmentation matches **spikeinterface's** defaults
  (`strict_gap_mode=False`, tolerance `round(0.25 × 512 × 1e6 / fs)` = 4267 µs
  at 30 kHz). neo's own default is stricter and would report 2717 sections
  here, nearly all of them clock jitter. If a future spikeinterface changes
  this default, re-check against `--strict`.
- Sub-tolerance hiccups still lose data without creating a segment break.
  This recording has 16 short records but only 7 breaks: ~0.08 s vanishes
  *inside* segments and no timestamp records it. The check reports both
  numbers separately.
- Only within-file gaps are covered. Cheetah also splits acquisition into
  `CSC12_0001.ncs` continuation files; those are a separate (and additive)
  case.
- `--channels 4` spot-checks. Use `--all-channels` before acting on a
  result that matters.

---

## 8. See also

[`BARRY_GUI_INTEGRATION.md`](BARRY_GUI_INTEGRATION.md) — requirements and
integration plan for folding this into the BARRY GUI session health check, and
for re-timing banked DS events into a new version without destroying curation.
