"""
tracker_io.py - read Bio-Signal Group Tracker .dat files (place avoidance / active avoidance)
and derive everything the plots and metrics need.

Coordinate conventions used throughout this package
---------------------------------------------------
* Positions are in tracker pixels; image y increases DOWNWARD (as in the .dat file).
* Angles are measured counter-clockwise on screen, 0 deg = to the right of the arena centre
  (i.e. math convention after flipping image y). The shock sector in our files is centred at 45 deg
  (upper right on screen), 60 deg wide, read from the header (%ReinforcedSector).
* "Relative" angles are measured from the shock-sector centre, wrapped to [-180, 180):
      0    = shock-sector centre (T)
     -90   = CW zone  (the zone the arena rotation carries INTO the shock sector)
     +90   = CCW zone
     +-180 = Opposite zone
  On our arena the rotation drifts a passive mouse in the +angle direction:
  CCW -> Opposite -> CW -> shock sector.
* Lost frames (State = 5, "BadSpot", x = y = 0): for zone times, angles and annuli the last tracked
  position is carried forward (this reproduces TrackAnalysis "P quad time" to within ~1%).
  For the dwell-time map only tracked frames are used, because carrying lost frames forward piles
  them into the single bin where tracking dropped out.
"""
import os
import re
import numpy as np
import pandas as pd

COLUMNS = ['frame', 't_ms', 'x', 'y', 'sectors', 'state', 'current', 'motor', 'flags', 'frameinfo']
STATE = dict(outside=0, entrance_latency=1, shock=2, inter_shock=3, outside_refractory=4, bad_spot=5)


def read_dat(path):
    """Return (header dict, DataFrame) from a Tracker .dat file."""
    hdr, rows, in_header = {}, [], True
    with open(path, encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if in_header:
                m = re.match(r'%(\w+)\.0 \( (.*) \)', line)
                if m:
                    hdr[m.group(1)] = m.group(2).strip()
                if line.startswith('%%END_HEADER'):
                    in_header = False
                continue
            if line:
                rows.append(line.split('\t'))
    d = pd.DataFrame(rows, columns=COLUMNS[:len(rows[0])])
    for c in d.columns:
        if c != 'flags':
            d[c] = pd.to_numeric(d[c], errors='coerce')
    return hdr, d


def parse_name(path):
    """Mouse and trial number from names like '933_13_RoomTrack_Room_20251023_112906.dat'."""
    name = os.path.basename(str(path))
    m = re.search(r'(\d+)_(\d+)_RoomTrack', name) or re.match(r'(\d+)_(\d+)', name)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def load_trial(path):
    """Read a .dat file and return a dict with geometry, positions, angles and event indices."""
    h, d = read_dat(path)
    T = dict(path=str(path), header=h, data=d)
    T['mouse'], T['trial'] = parse_name(path)
    T['px_per_cm'] = float(h['TrackerResolution_PixPerCM'])
    T['cx'], T['cy'] = map(float, h['ArenaCenterXY'].split())
    T['R_px'] = float(h['ArenaDiameter_m']) * 100 / 2 * T['px_per_cm']
    T['sector_centre'], T['sector_width'] = [float(v) for v in h['ReinforcedSector'].split()[:2]]
    T['dt'] = d.t_ms.diff().median() / 1000.0

    lost = (d.state == STATE['bad_spot']).values
    T['lost'] = lost
    T['x_fill'] = d.x.where(~lost).ffill().bfill().values          # last tracked position carried forward
    T['y_fill'] = d.y.where(~lost).ffill().bfill().values
    T['x_tracked'] = d.x.where(~lost).values                       # NaN where lost (for drawing the path)
    T['y_tracked'] = d.y.where(~lost).values

    # room angle (deg, CCW on screen) and angle relative to the shock-sector centre
    T['theta'] = np.degrees(np.arctan2(-(T['y_fill'] - T['cy']), T['x_fill'] - T['cx'])) % 360
    T['rel'] = (T['theta'] - T['sector_centre'] + 180) % 360 - 180
    T['r_cm'] = np.minimum(np.hypot(T['x_fill'] - T['cx'], T['y_fill'] - T['cy']), T['R_px']) / T['px_per_cm']

    # avoidance-state events (lost frames take the previous state)
    st = d.state.replace(STATE['bad_spot'], np.nan).ffill().fillna(0).astype(int).values
    raw = d.state.values
    # shock onsets: first frame of each Shock (2) state
    T['shock_idx'] = np.flatnonzero((raw == 2) & (np.r_[-1, raw[:-1]] != 2))
    # entrance (TrackAnalysis definition): entrance latency completed -> first shock (state 1 -> 2)
    T['entrance_idx'] = np.flatnonzero((st[1:] == 2) & (st[:-1] == 1)) + 1
    # entry without shock: entrance latency started (0 -> 1) but the mouse left before the shock (1 -> 0)
    starts = np.flatnonzero((st[1:] == 1) & (st[:-1] == 0)) + 1
    quick = []
    for i in starts:
        after = st[i:]
        if (after != 1).any() and after[np.argmax(after != 1)] == 0:
            quick.append(i)
    T['quick_entry_idx'] = np.array(quick, dtype=int)
    return T
