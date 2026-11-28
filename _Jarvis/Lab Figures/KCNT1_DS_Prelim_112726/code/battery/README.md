# Dentate-spike pilot battery (2026-11-16)

A lead-finding pass on pilot data. Dentate spikes (DS) were recorded with a 64-contact linear probe (50 µm spacing) through the
dentate gyrus of 9 control mice and 9 mice with a sparse PTEN knockout in granule cells. We want every reasonable measure of
those events put through the same set of group contrasts, so that leads can be picked for a planned follow-up study. Nothing
here is a finding: every test is recorded, P values are raw, and corrections are made afterwards over everything.

Everything is frozen in `data/`. Nothing in this folder talks to Jarvis (the lab's app) and nothing may.

## The recordings (one per mouse; the unit of every test is the mouse)

| lab | group | subgroup | knockout % | events v6 | events v8 | year |
|---|---|---|---|---|---|---|
| m2, m6, m21, m22, m26 | CTL | CTL | 0 | 112, 206, 73, 226, 275 | 105, 192, 68, 202, 246 | 2023-2024 |
| m51 | CTL | CTL | 0 | 5 | 5 | 2025 (dropped: under 20 events) |
| m59, m60, m61 | CTL | CTL | 0 | 509, 567, 190 | 454, 521, 170 | 2025 |
| m8, m33, m1 | PTEN | IED- | 3.9, 4.4, 5.2 | 369, 218, 188 | 332, 169, 157 | 2023-2024 |
| m7 | PTEN | IED- | 24.1 | 130 | 92 | 2023 |
| m13, m28, m3, m5, m34 | PTEN | IED+ | 18.9, 20.2, 24.6, 27.6, 28.4 | 353, 338, 151, 722, 192 | 283, 287, 106, 627, 161 | 2023-2024 |

- IED+ / IED- (the lab's subgroup): whether the mouse shows interictal epileptiform discharges ("P-spikes").
- Two event sets of the same recordings: `v6` (the Halo set, the main one) and `v8` (the No P-spikes set, stricter). Run
  everything on both; a lead that holds on both is worth more.
- An "event" is a DS that fell inside the detection border the lab drew for that recording. Rates are rates of those events,
  not of every DS the brain made.

## Loading

```python
import sys; sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import dsdata
recs = dsdata.load("v6")            # list of Rec; about 10 s, 0.7 GB
r = dsdata.by_lab(recs)["m60"]
```

Fields of a `Rec` (rows are 0-based positions down the shank; row 0 is the top contact; 50 µm a row):

| field | what |
|---|---|
| `lab, group, subgroup, ko, n, dur_s, dur_min, date, year, ok` | `ok` = 20 events or more |
| `csd` | events x 64 rows x 101 samples, current source density around each event; sink negative, source positive; one physical scale for all recordings |
| `lfp` | same shape, local field potential in µV, each row's baseline (median beyond ±30 ms) taken off |
| `t_ms` | the 101 sample times, -50 to +50 ms; the DS peak is at 0; 1 kHz |
| `csd_peak, lfp_peak` | events x 64: the mean over ±3 ms around the peak |
| `mean_csd_peak` | 64: mean of `csd_peak` over all events, bad rows filled |
| `times_s` | event times in seconds from the start of the recording |
| `det_peak` | the detector's peak size per event |
| `pc` | events x 2: PC1, PC2 of the events (the plane the PCA classifiers work on) |
| `theta_t, theta_p` | start time (s) and theta-band power of 4 s bins through the recording, at one contact |
| `band` | (first row, last row) of the analyzed band: the rows the classifiers saw |
| `hump_cut_row` | first row of the lower blade's half of the band |
| `bad, bad_rows` | bad contacts (numbers; rows). The CSD at a bad row is not a measurement. Use `dsdata.fill_bad(profile, r.bad_rows)` or skip those rows |
| `lab_field` | the lab's coarse label per contact: CA1 / DG (upper blade) / DG2 (lower blade) / THAL |
| `W` | dict `both`, `top`, `bottom`: events x events sink-overlap matrices (whole band, upper blade, lower blade). The separation index is 1 - mean overlap between types / mean overlap within types |
| `labels[clf]` | per classifier: `types` (1 = DS1, 2 = DS2), `si` (separation index), `n1`, `n2`, `eligible`, `axis` (the classifier's own score per event, when it has one) |
| `used, conv, opt` | the classifier with the highest index among the eligible conventional ones; the best one on the PCA plane; `opt_curve` |
| `landmarks` | see Depth |

Helpers: `r.types(clf)`, `r.si(clf)`, `r.eligible(clf)`, `r.separable(clf=None)`, `r.ds3(clf, cut=0.5)`, `r.types3(clf)`,
`r.depth_um(rows)`, `r.u(rows)`, `r.v(rows, blade)`, `r.on_u(profile, grid)`, `r.on_v(profile, blade, grid)`,
`r.blade_rows(blade, widen=5)`, `r.good(rows)`.

## The classifiers

`dsdata.CLASSIFIERS` (19): five base methods (`bite`, `pca`, `pca_gap`, `delta`, `delta_mid`), each on both sinks, on the
upper sink only (`_top`) and on the lower sink only (`_bottom`); two Gaussian mixtures on the PCA plane (`pca_gmm_line`,
`pca_gmm_curve`); and two boundaries fitted to maximize the separation index (`opt_line`, `opt_curve`; in-sample, so their
index is optimistic). `dsdata.CONVENTIONAL` is the first 17.

- A classifier is **eligible** on a recording when each type holds 5% of events or more (and 5 events or more).
- DS1 and DS2 are called **separable** when an eligible classifier reaches a separation index of 0.45. With the classifier in
  `r.used` that is 6 of 17 recordings on v6: m26, m61 (CTL); m33, m1, m28, m7 (PTEN). In the other 11 the events are one
  cloud and the DS1 / DS2 names are arbitrary there.
- Naming: DS1 is the type whose mean main sink is the shallower one. In the separable recordings DS1 is the minority
  (7-16% of events), its sink is 0.3-0.5 the size of DS2's and sits farther from the granule cell layer in both blades.
- **DS3** (`r.ds3(clf)`): events whose relative sink, (outer - middle) / (outer + middle), is within ±0.5. Outer and middle
  are single contacts in one blade: where DS1's and where DS2's mean sink peaks under that classifier. `None` when they peak
  at the same contact (DS3 cannot be scored there). Known artifact: the closer those two contacts (`r.ds3_gap_um[clf]`,
  50-250 µm), the more events score as DS3.

For a type-specific measure, loop the classifiers and give a recording a value only where the classifier is eligible and the
type has 5 events or more:

```python
for es in ("v6", "v8"):
    recs = dsdata.load(es)
    for clf in dsdata.CLASSIFIERS:
        vals = {}
        for r in recs:
            if not (r.ok and r.has(clf) and r.eligible(clf)):
                continue
            t = r.types(clf)
            if (t == 1).sum() >= 5:
                vals[r.lab] = something(r, t == 1)
        B.add(family, "sink_amp_ds1", vals, "...", unit, event_set=es, classifier=clf)
```

Because the DS1 / DS2 names are arbitrary in one-cloud recordings, also give the minority-type and majority-type versions of
type-specific measures where that makes sense (`variant="minor"` / `"major"`), and a version restricted to `r.used`
(`classifier="used"`).

## Depth

The probe crosses both blades of the dentate gyrus: an upper sink, a source between (granule cell layers and hilus), a lower
sink. Tracks differ between mice (angle, where along the blades), so raw microns do not line up. `r.landmarks` (from the mean
of all events; `None` if not found; found on all 17):

- `U`, `L`: the main sink of the upper and of the lower blade (row, sub-contact).
- `GU`, `GL`: the source nearest each of them on the way to the other blade (granule cell layer side); equal when there is one
  source between the blades.
- also `rowU, rowL, rowGU, rowGL` (whole rows), `sinkU, sinkL, source` (sizes), `blade_um`, `gcl_to_sink_upper_um`,
  `gcl_to_sink_lower_um`, `source_gap_um`.

Two normalized axes:
- `r.u(rows)`: blade to blade, 0 at the upper main sink, 1 at the lower.
- `r.v(rows, "upper"|"lower")`: within one blade, 0 at that blade's source, 1 at its main sink, above 1 farther out (towards
  the outer molecular layer). Distances in units of v are free of the probe's angle.

The analyzed band often stops just past the main sinks, and the outer (DS1) sinks sit at or beyond its ends:
`r.blade_rows(blade, widen=5)` gives a blade's rows with 5 contacts added past the band.

## Things already known (do not rediscover; do build on)

- IED+ mice are also the high-knockout mice (only m7 is IED- with a high knockout), so `IEDpos_vs_IEDneg` and the dose
  contrasts overlap. Say so when a lead rests on it.
- Three of the eight controls were recorded in 2025; every PTEN mouse in 2023-2024. The harness stores each measure's rank
  correlation with year, event count, minutes, bad contacts, band size and blade distance, for screening.
- Event counts range 73-722; anything that grows with the number of events will track that, not biology.
- An earlier, uncorrected lead: the net source between the blades, relative to the sinks, falls as the knockout rises.
- The DS3 share mostly follows contact spacing.

## The harness (every measure, the same contrasts)

```python
from harness import Battery
B = Battery("timing")                         # your agent name
mid = B.add(family="timing", name="rate_all", values={"m60": 14.1, ...}, desc="Events per minute, all events",
            unit="1/min", event_set="v6", classifier="", variant="")
print(B.describe(mid))                        # the numbers by group, to check by eye
print(B.top(25))                              # smallest raw P so far
B.save()                                      # also saved every 40 adds and at exit, to results/<agent>.pkl
```

`values` is one number per recording keyed by lab name; leave a recording out when the measure cannot be had there. The
measure id is `family|name|event_set|classifier|variant`; adding the same id again replaces it. About 0.05 s per measure.

Contrasts run for each measure (raw two-sided P; several tests per contrast are stored side by side): PTEN against control;
against % knockout within PTEN (exact Spearman) and over all mice; high-knockout and low-knockout PTEN against control; the
ordered trend control < low < high knockout; IED+ against IED-; each against control; the ordered trend control < IED- <
IED+; and the spread, PTEN against control (Brown-Forsythe).

## Rules for a measure

1. One number per recording. Summarize events by the median unless the measure is itself a spread, share or rate; add the
   mean or a robust spread as variants when they could differ.
2. Say exactly what it is in `desc` (what is measured, at which rows, over which window, which events), with the unit.
3. `name` is short snake_case without the type or classifier in it when those go in `classifier` / `variant`.
4. Never put two different quantities under one name; never change a measure after looking at its P value.
5. Check the numbers before trusting them: print `B.describe(mid)` for a few measures in each block, look for constants,
   absurd sizes, a sign that is backwards, values that only track the event count.
6. Plain words, American spelling, standard terms (no invented names for things that have one).

## Where things go

- Your code: `agents/<agent>/run.py` (one command, `python agents/<agent>/run.py`, must rebuild all of your results; helper
  modules beside it are fine).
- Your results: `results/<agent>.pkl`, written by the harness.
- Your notes: `agents/<agent>/NOTES.md`, 60 lines at most: what you measured (blocks, counts), up to 12 leads with why each is
  interesting and what speaks against it, anything odd you saw in the data.
- Do not edit `dsdata.py`, `harness.py`, `README.md` or `data/`; do not write anywhere else; no network; no figures needed
  (the main session draws them from the stored numbers). Keep printed output short.
