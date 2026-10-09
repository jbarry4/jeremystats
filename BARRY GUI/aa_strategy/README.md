# Active avoidance strategy analysis (Tracker .dat files)

Python code behind Figure 9: the per-trial behavioural summary (track, dwell map, polar and
annular histograms), the per-trial **strategy score**, and the per-trial **mean direction from the
shock-sector centre**.

## Files

| File | What it does |
|---|---|
| `tracker_io.py` | Reads a Bio-Signal Tracker `.dat` file (header + samples) and derives positions, angles, lost frames, shocks, entrances and entries without shock. |
| `metrics.py` | Per-trial measures: zone shares (T, CCW, OPP, CW), strategy score, mean direction, R. |
| `plot_trial_summary.py` | 2 × 2 summary figure for one trial (panels A–D of Figure 9). |
| `plot_strategy_trend.py` | Per-trial line plots for one or more mice (panels E–G of Figure 9) + a CSV of every measure. |

Requirements: Python 3.9+, `numpy`, `pandas`, `matplotlib` (`pip install -r requirements.txt`).

## Usage

```bash
# one trial
python plot_trial_summary.py data/933_13_RoomTrack_Room_20251023_112906.dat -o 933_T13.png \
    --label "Mouse 933 (TBI non-learner), T13 — Day 2"

# every trial in a folder, one PNG each
python plot_trial_summary.py data/*.dat --outdir summaries/

# strategy score and mean direction across trials (any number of mice)
python plot_strategy_trend.py data/964_*.dat data/933_*.dat -o trend.png --csv trend.csv \
    --labels 964="964 Sham learner" 933="933 TBI non-learner" \
    --highlight 964=1,15 933=7,13            # optional: circle the trials shown as summaries
#   --halves  adds the same measures for the first and second 5 min of each trial
```

Mouse and trial numbers are read from the file name (`<mouse>_<trial>_RoomTrack_...dat`, or
`<mouse>_<trial>.dat`). Trials 1–8 are Day 1 and 9–16 Day 2; missing trials are simply skipped.
Legend and colour order follow `--labels` (otherwise the order the files are given).

From Python:

```python
from metrics import trial_metrics
m = trial_metrics("data/933_13_RoomTrack_Room_20251023_112906.dat", halves=True)
m["strategy_score"], m["mean_direction"], m["R"]
```

## Definitions

**Angles.** Positions are converted to an angle around the arena centre, counter-clockwise on
screen. The **direction from the shock-sector centre** wraps that angle so 0° is the centre of the
shock sector: −90° = CW zone, ±180° = Opposite, +90° = CCW. On this arena the rotation carries a
passive mouse **CCW → Opposite → CW → shock sector**, so the CW zone is the last stop before a shock
and the Opposite/CCW side is the farthest "upstream".

**Zone shares** (TrackAnalysis "P quad time"). Time in the shock sector (T, from the file header:
centre 45°, width 60°) and in sectors of the same size centred in the CCW, Opposite and CW
quadrants, expressed as shares of the time in those four sectors (they sum to 1).

**Strategy score** = OPP / (OPP + CW). 1 = all of that time in the Opposite zone (spatial
avoidance); 0 = all of it in the CW zone (riding the rotation toward the shock).

**Mean direction** = circular mean of the direction from the shock-sector centre over every frame.
**R** = mean resultant length (0 = time spread evenly around the arena, 1 = all in one direction).
For plotting, mean directions above +90° are shifted by −360° so the Opposite zone is not split
(axis runs −90° CW → −180° Opposite → −270° = +90° CCW).

**Events** (from the State column).
- Shock = first frame of each Shock state.
- Entrance (matches the spreadsheet / TrackAnalysis) = entrance latency completed → first shock.
- Entry without shock = entrance latency started but the mouse left before the shock (blue circles).

**Lost frames** (State 5, x = y = 0). For zone shares, angles and annuli the last tracked position
is carried forward, as TrackAnalysis does. The dwell map uses tracked frames only, because carrying
lost frames forward piles them into the bin where tracking dropped out.

**Dwell map**: 8 × 8 tracker-pixel bins (2.56 cm at 3.122 px/cm), unsmoothed, seconds per bin,
jet colour map with unvisited bins black; each map has its own colour scale.

**Polar histogram**: 10° bins in the room frame; preferred / least-preferred 50% regions grown from
the most / least visited bin by adding the larger / smaller flanking bin until 50% of the time is
covered (TrackAnalysis rule). **Annular histogram**: 8 equal-area annuli.

## Validation

On mice 933 and 964 (16 trials each) the per-trial values reproduce those in Figure 9 exactly,
shock counts match the spreadsheet on 27 of 32 trials (the rest differ by 1–2), and zone shares agree with TrackAnalysis to
within ~1–2 percentage points (except a few spreadsheet cells identified as entry errors).

Geometry (arena centre, radius, pixels per cm, shock-sector centre and width) is read from each
file's header, so other arenas or sector settings work without code changes. The 256 × 256 tracker
image size used for the dwell-map grid is set in `panel_dwell` if yours differs.
