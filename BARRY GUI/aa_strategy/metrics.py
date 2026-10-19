"""
metrics.py - per-trial strategy measures.

zone_shares(T)      TrackAnalysis "P quad time": time in the shock sector (T) and in sectors of the
                    same size centred in the CCW, Opposite and CW quadrants, as shares of the time
                    spent in those four sectors (they sum to 1).
strategy_score      OPP / (OPP + CW). 1 = all of that time in the Opposite zone (spatial avoidance),
                    0 = all of it in the CW zone (the zone the rotation carries into the shock sector).
mean_direction      circular mean of the angle from the shock-sector centre (deg, -180..180);
                    -90 = CW, +-180 = Opposite, +90 = CCW.
R                   mean resultant length (0 = time spread evenly around the arena, 1 = one direction).
"""
import numpy as np
from tracker_io import load_trial

ZONE_CENTRES = {'T': 0, 'CCW': 90, 'OPP': 180, 'CW': -90}


def zone_shares(T, mask=None):
    rel = T['rel'] if mask is None else T['rel'][mask]
    half = T['sector_width'] / 2
    counts = {k: int((np.abs((rel - c + 180) % 360 - 180) <= half).sum()) for k, c in ZONE_CENTRES.items()}
    total = sum(counts.values())
    return {k: (v / total if total else np.nan) for k, v in counts.items()}


def circular_stats(T, mask=None):
    a = np.radians(T['rel'] if mask is None else T['rel'][mask])
    C, S = np.cos(a).mean(), np.sin(a).mean()
    return np.degrees(np.arctan2(S, C)), float(np.hypot(C, S))


def trial_metrics(path_or_trial, halves=False):
    """Dict of per-trial measures. halves=True adds the same measures for the first/last 5 min."""
    T = load_trial(path_or_trial) if isinstance(path_or_trial, str) else path_or_trial
    z = zone_shares(T)
    mu, R = circular_stats(T)
    out = dict(mouse=T['mouse'], trial=T['trial'],
               shocks=len(T['shock_idx']), entrances=len(T['entrance_idx']),
               entries_without_shock=len(T['quick_entry_idx']),
               T=z['T'], CCW=z['CCW'], OPP=z['OPP'], CW=z['CW'],
               strategy_score=z['OPP'] / (z['OPP'] + z['CW']) if (z['OPP'] + z['CW']) else np.nan,
               mean_direction=mu, R=R, lost_frames_pct=100 * T['lost'].mean())
    if halves:
        t = T['data'].t_ms.values
        for lab, m in [('first_half', t < t[-1] / 2), ('second_half', t >= t[-1] / 2)]:
            zz = zone_shares(T, m); mm, rr = circular_stats(T, m)
            out[f'strategy_score_{lab}'] = zz['OPP'] / (zz['OPP'] + zz['CW']) if (zz['OPP'] + zz['CW']) else np.nan
            out[f'mean_direction_{lab}'] = mm
            out[f'R_{lab}'] = rr
    return out


def unwrap_for_plot(mean_direction):
    """Map mean direction to (-270, 90] so that the Opposite zone (+-180) does not split:
    -90 = CW, -180 = Opposite, -270 = CCW. Used only for plotting."""
    md = np.asarray(mean_direction, dtype=float)
    return np.where(md > 90, md - 360, md)
