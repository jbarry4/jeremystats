"""Shared helpers for the path analyses: reading tracker files, goal geometry, speed.

Everything here re-implements pieces of TargetTrajectories.m (JB2, jun25 NewGoalCode).
Departures from the MATLAB code are marked  ## DEVIATION FROM MATLAB.
"""
import numpy as np, re, pandas as pd

PIX = 75 / 255      # cm per pixel. MATLAB: PixSz = 75/ArenaDiameter, ArenaDiameter = 2*ArCenterCoord(1) = 255. Same.
SF = 30             # frames per second. MATLAB: SF = 30. Same.
ARENA_C = 127.5     # arena centre in pixels. MATLAB uses ArCenterCoord (= 127.5, 127.5) and hard-codes 127.5 for the annulus.
ANNULUS_PX = 35     # wall zone width. MATLAB: smallr = ArenaR - 35. Same.

# Goal-zone centres G1-G4 for the original cohort, as in PTEN_Feeder_GoalZones.xlsx (kept for reference; not used below).
G = {1: (172.7165, 77.28199), 2: (86.6816, 75.2549), 3: (96.72829, 156.1951), 4: (161.6847, 156.1844)}


def read_dat(fn):
    """Read a Bio-Signal Tracker .dat file.

    Returns (header dict, data dict with frame, ts [ms], X, Y, sec, state).
    state is the column MATLAB calls `Shocks`: 0 outside, 1 entrance latency, 2 reward ("shock"),
    3 inter-reward latency, 4 outside refractory, 5 bad spot.

    ## DEVIATION FROM MATLAB: MATLAB uses read_biosigPlaceAcc.m (not provided). This parser reads the
    ## header lines of the form  %Name.0 ( values )  and the first six data columns. It reproduces
    ## rewards, entrances and goal time of the PlaceAccuracy output exactly for all 256 probe sessions
    ## checked (s01_validate_sessions.py).
    """
    hdr = {}; rows = []
    with open(fn, errors='replace') as f:
        inh = True
        for line in f:
            if inh:
                m = re.match(r'\s*%(\w+)\.0 \( (.*) \)', line)
                if m: hdr[m.group(1)] = m.group(2)
                if line.startswith('%%END_HEADER'): inh = False
                continue
            p = line.split()
            if len(p) >= 6: rows.append([float(v) for v in p[:6]])
    a = np.array(rows)
    return hdr, dict(frame=a[:, 0], ts=a[:, 1], X=a[:, 2], Y=a[:, 3], sec=a[:, 4], state=a[:, 5])


def target_xy(hdr):
    """Goal centre (x, y) and goal radius in pixels, from the file header (ReinforcedSector).

    Same formula as MATLAB:
        TargRadPix = ArenaR*(TargRad/100);  Xtarg2 = ArCenterCoord(1) + TargRadPix*cosd(TargAngle)
        Ytarg2 = ArCenterCoord(2) - TargRadPix*sind(TargAngle);  TargetRadius = ArenaDiameter*(TargDiam/100)/2
    """
    a, rp, dp = [float(v) for v in hdr['ReinforcedSector'].split()]
    cx, cy = [float(v) for v in hdr['ArenaCenterXY'].split()]
    R = cx; rr = R * rp / 100
    return cx + rr * np.cos(np.radians(a)), cy - rr * np.sin(np.radians(a)), R * 2 * (dp / 100) / 2


def speed_matlab(X, Y, t_s, w=15, shift=12):
    """Running speed (cm/s) matched to MATLAB Speed_MtxEZ.

    ## DEVIATION FROM MATLAB: Speed_MtxEZ.m was not provided. This is displacement over 15 frames
    ## (0.5 s) divided by elapsed time, shifted 12 frames earlier. The window and shift were chosen
    ## because they reproduce the PlaceAccuracy MeanSpeed within 0.4 cm/s and MeanTargSpeed within
    ## 1.2 cm/s for the example-mouse sessions. Lost frames (X == 0) are NaN, as in MATLAB.
    ## With the 12-frame shift, the value at frame i covers roughly frames i-3 to i+12, so the value at an
    ## entrance frame (MATLAB target speed) is speed over the first ~0.4 s inside the goal zone.
    """
    Xn = pd.Series(np.where(X == 0, np.nan, X)); Yn = pd.Series(np.where(Y == 0, np.nan, Y))
    v = (np.sqrt(Xn.diff(w) ** 2 + Yn.diff(w) ** 2) * PIX / pd.Series(t_s).diff(w)).values
    return np.roll(v, -shift)
