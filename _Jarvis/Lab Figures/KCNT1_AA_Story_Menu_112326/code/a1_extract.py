"""Every measure straight from the Tracker .dat files (no TrackAnalysis needed).

Conventions follow aa_strategy (tracker_io.py / metrics.py, Figure 9 code):
  * angles counter-clockwise on screen, 0 = right of the arena center; 'rel' = angle from the shock-zone center,
    wrapped to [-180, 180): -90 = CW zone, +-180 = opposite, +90 = CCW zone.
  * the arena carries a still mouse counter-clockwise on screen (checked here: the most common angular velocity is
    +5 deg/s), so the CW zone is upstream: the rotation carries it INTO the shock zone.
  * lost frames (state 5): last tracked position carried forward for zone times, angles and annuli.
Writes session_metrics.csv and tracks.npz (positions at 15 Hz for the path figures).
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SESS = json.load(open(os.path.join(HERE, "sessions.json")))
COLS = ["frame", "t_ms", "x", "y", "sectors", "state", "current", "motor"]
EDGE = 30.0          # half-width of the shock zone (deg), from the header (60 deg wide)
NEAR = 40.0          # within 10 deg of the zone edge
FAR = 60.0           # 30 deg or more from the edge


def read(path):
    hdr = {}
    n_head = 0
    with open(path, encoding="latin-1") as f:
        for n_head, line in enumerate(f, 1):
            s = line.strip()
            if s.startswith("%") and "(" in s:
                k = s[1:s.index("(")].strip().replace(".0", "")
                hdr[k] = s[s.index("(") + 1:s.rindex(")")].strip()
            if s.startswith("%%END_HEADER"):
                break
    d = pd.read_csv(path, sep=r"\s+", skiprows=n_head, header=None, usecols=range(8), names=COLS,
                    engine="c", encoding="latin-1", comment="%")
    return hdr, d.apply(pd.to_numeric, errors="coerce").dropna(subset=["t_ms"]).reset_index(drop=True)


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def runs(mask):
    """Start/stop indices of True runs."""
    m = np.r_[False, mask, False].astype(int)
    d = np.diff(m)
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


def session(path, omega=None):
    h, d = read(path)
    px = float(h["TrackerResolution_PixPerCM"])
    cx, cy = map(float, h["ArenaCenterXY"].split())
    R_px = float(h["ArenaDiameter_m"]) * 100 / 2 * px
    sc, sw = [float(v) for v in h["ReinforcedSector"].split()[:2]]
    t = (d.t_ms.values - d.t_ms.values[0]) / 1000.0
    n = len(d)
    dur = float(t[-1]) if n else 0.0
    dt = float(np.median(np.diff(t))) if n > 1 else 1 / 30
    raw = d.state.values.astype(int)
    lost = raw == 5
    x = pd.Series(np.where(lost, np.nan, d.x.values)).ffill().bfill().values
    y = pd.Series(np.where(lost, np.nan, d.y.values)).ffill().bfill().values
    X, Y = (x - cx) / px, -(y - cy) / px                     # cm, y up
    theta = np.degrees(np.arctan2(Y, X)) % 360
    rel = wrap180(theta - sc)
    r = np.minimum(np.hypot(X, Y), R_px / px)
    Rcm = R_px / px
    st = pd.Series(np.where(lost, np.nan, raw)).ffill().fillna(0).astype(int).values
    sect = pd.Series(np.where(lost, np.nan, d.sectors.values)).ffill().fillna(0).astype(int).values
    in_zone = (sect & 1) > 0

    shock_on = np.flatnonzero((st == 2) & (np.r_[-1, st[:-1]] != 2))
    shock_on_raw = np.flatnonzero((raw == 2) & (np.r_[-1, raw[:-1]] != 2))
    entr = np.flatnonzero((st[1:] == 2) & (st[:-1] == 1)) + 1
    starts = np.flatnonzero((st[1:] == 1) & (st[:-1] == 0)) + 1
    quick = 0
    for i in starts:
        after = st[i:]
        if (after != 1).any() and after[np.argmax(after != 1)] == 0:
            quick += 1

    out = dict(n_frames=n, duration_s=dur, lost_pct=100 * lost.mean(), shocks=len(shock_on), shocks_raw=len(shock_on_raw),
               entrances=len(entr), entries_without_shock=quick)
    out["time_in_zone_s"] = float(in_zone.sum() * dt)
    out["time_in_zone_pct"] = 100 * in_zone.mean()
    out["time_in_zone_angle_pct"] = 100 * (np.abs(rel) <= sw / 2).mean()
    te = t[entr]
    out["latency_first_entrance_s"] = float(te[0]) if te.size else dur
    gaps = np.diff(np.r_[0.0, te, dur])
    out["max_avoid_s"] = float(gaps.max()) if gaps.size else dur
    s_on = t[shock_on]
    out["latency_first_shock_s"] = float(s_on[0]) if s_on.size else dur
    half = dur / 2
    out["shocks_first_half"] = int((s_on < half).sum())
    out["shocks_second_half"] = int((s_on >= half).sum())
    out["entrances_first_half"] = int((te < half).sum())
    out["entrances_second_half"] = int((te >= half).sum())
    zs, ze = runs(in_zone)
    out["zone_visit_s"] = float(np.mean((ze - zs) * dt)) if zs.size else np.nan
    out["shocks_per_entrance"] = out["shocks"] / out["entrances"] if out["entrances"] else np.nan

    # ---- zones (TrackAnalysis 'P quad time'), strategy, circular stats --------------------------------
    half_w = sw / 2
    cnt = {k: int((np.abs(wrap180(rel - c)) <= half_w).sum()) for k, c in {"T": 0, "CCW": 90, "OPP": 180, "CW": -90}.items()}
    tot = sum(cnt.values())
    for k, v in cnt.items():
        out["zone_" + k] = v / tot if tot else np.nan
    out["strategy_score"] = cnt["OPP"] / (cnt["OPP"] + cnt["CW"]) if (cnt["OPP"] + cnt["CW"]) else np.nan
    a = np.radians(rel)
    C, S = np.cos(a).mean(), np.sin(a).mean()
    Rbar = float(np.hypot(C, S))
    out["mean_dir_deg"] = float(np.degrees(np.arctan2(S, C)))
    out["R"] = Rbar
    out["circ_sd_deg"] = float(np.degrees(np.sqrt(-2 * np.log(max(Rbar, 1e-9)))))
    hist36 = np.histogram(theta, np.arange(0, 361, 10))[0].astype(float)
    p36 = hist36 / hist36.sum()
    nz = p36[p36 > 0]
    out["entropy"] = float(-(nz * np.log(nz)).sum() / np.log(36))
    out["angle_coverage"] = float((p36 >= 0.01).mean())
    out["opp_half_pct"] = 100 * (np.abs(rel) > 90).mean()
    out["mean_abs_angle_deg"] = float(np.abs(rel).mean())
    outside = np.abs(rel) > half_w
    out["dist_from_edge_deg"] = float(np.median(np.abs(rel[outside]) - half_w)) if outside.any() else 0.0
    out["buffer_pct"] = 100 * ((np.abs(rel) > half_w) & (np.abs(rel) <= half_w + 20)).mean()
    out["buffer_pre_pct"] = 100 * ((rel < -half_w) & (rel >= -half_w - 20)).mean()
    out["buffer_post_pct"] = 100 * ((rel > half_w) & (rel <= half_w + 20)).mean()
    # near misses: from far (>= 60 deg) to within 10 deg of the edge and back to far, without entering
    k = max(int(round(0.5 / dt)), 1)
    ar = pd.Series(np.abs(rel)).rolling(k, center=True, min_periods=1).median().values
    state, ap, en, reached = 0, 0, 0, False
    for v, z in zip(ar, in_zone):
        if state == 0:
            if v < FAR:
                state, reached = 1, False
        if state == 1:
            if z or v <= half_w:
                en += 1
                state = 2
            elif v <= NEAR:
                reached = True
            elif v >= FAR:
                if reached:
                    ap += 1
                state = 0
        elif state == 2 and v >= FAR:
            state = 0
    out["near_misses"] = ap
    out["approach_entries"] = en
    out["brake_share"] = ap / (ap + en) if (ap + en) else np.nan
    out["near_misses_per_min"] = ap / (dur / 60) if dur else np.nan

    # ---- path shape: room frame (as TrackAnalysis) and arena frame (the mouse's own walking) ------------
    # TrackAnalysis measures path on positions taken once a second (checked: matches its 'total path' to ~1%)
    w = max(int(round(1.0 / dt)), 1)
    X1, Y1, t1 = X[::w], Y[::w], t[::w]
    step = np.hypot(np.diff(X1), np.diff(Y1))
    out["path_m"] = float(step.sum() / 100)
    out["speed_cm_s"] = float(step.sum() / dur) if dur else np.nan
    out["speed_sd_cm_s"] = float(np.std(step / np.diff(t1))) if step.size else np.nan
    if omega is not None:
        ang = -np.radians(omega) * t1
        Xa = X1 * np.cos(ang) - Y1 * np.sin(ang)
        Ya = X1 * np.sin(ang) + Y1 * np.cos(ang)
        stepa = np.hypot(np.diff(Xa), np.diff(Ya))                       # the mouse's own movement on the arena, per s
        out["walk_m"] = float(stepa.sum() / 100)
        out["walk_speed_cm_s"] = float(np.median(stepa))
        out["immobile_pct"] = 100 * float((stepa < 2.0).mean())
        cs = np.r_[0, np.cumsum(stepa)]
        k5 = 5
        net5 = np.hypot(Xa[k5:] - Xa[:-k5], Ya[k5:] - Ya[:-k5])
        pl5 = cs[k5:] - cs[:-k5]
        moving = pl5 > 5.0                                                # walked at least 5 cm in the 5 s
        out["straightness"] = float(np.median(net5[moving] / pl5[moving])) if moving.any() else np.nan
    ann = np.clip(np.digitize(r, Rcm * np.sqrt(np.arange(9) / 8)) - 1, 0, 7)
    pa = np.bincount(ann, minlength=8) / len(ann)
    out["rim_pct"] = 100 * float(pa[7])
    out["outer2_pct"] = 100 * float(pa[6:].sum())
    out["center2_pct"] = 100 * float(pa[:2].sum())
    out["mean_r_cm"] = float(r.mean())
    # 2-D coverage: 2.56 cm cells inside the arena visited for at least 1 s in total
    g = np.arange(-Rcm, Rcm + 2.56, 2.56)
    H2, _, _ = np.histogram2d(X[~lost], Y[~lost], [g, g])
    gc = (g[:-1] + g[1:]) / 2
    insid = np.hypot(*np.meshgrid(gc, gc, indexing="ij")) <= Rcm - 1.28
    out["cells_visited"] = float(((H2 * dt) >= 1.0)[insid].mean())
    # angular velocity mode (rotation check) over 1-s steps, r > 10 cm
    th = np.unwrap(np.radians(theta))
    w = max(int(round(1.0 / dt)), 1)
    av = np.degrees(th[w:] - th[:-w]) / (t[w:] - t[:-w])
    keep = (r[w:] > 10) & ~lost[w:]
    hh, ee = np.histogram(av[keep], bins=np.arange(-10, 10.01, 0.25))
    out["angvel_mode"] = float(((ee[:-1] + ee[1:]) / 2)[np.argmax(hh)]) if keep.any() else np.nan
    out["header_path_m"] = float(h.get("ElapsedPath_m", "nan"))
    # positions for the figures (15 Hz) and the 36-bin occupancy (for map stability)
    tr = dict(x=X[::2].astype(np.float32), y=Y[::2].astype(np.float32),
              shocks=(shock_on // 2).astype(np.int32), entr=(entr // 2).astype(np.int32),
              occ36=np.histogram(rel, np.arange(-180, 181, 10))[0].astype(np.float32) / max(len(rel), 1))
    return out, tr


def passive_rides(x, y, t):
    """The arena's own speed, read from stretches where a mouse rides still: 4 s in a row at a constant radius
    (< 0.4 cm change per s) and a constant angular speed (s.d. < 0.25 deg/s). Returns the per-stretch speeds."""
    i1 = np.searchsorted(t, np.arange(0, t[-1], 1.0))
    th = np.unwrap(np.arctan2(y[i1], x[i1]))
    rad = np.hypot(x[i1], y[i1])
    a = np.degrees(np.diff(th)) / np.diff(t[i1])
    dr = np.abs(np.diff(rad))
    out = []
    for i in range(len(a) - 3):
        seg = a[i:i + 4]
        if (dr[i:i + 4] < 0.4).all() and seg.std() < 0.25 and 1.5 < seg.mean() < 9 and rad[i] > 12:
            out.append(seg.mean())
    return out


def main():
    t0 = time.time()
    use = [s for s in SESS if s["use"] or s["kind"] in ("Extra session beyond s16", "Repeat s0 (day-2 habituation)")]
    # pass 1: the arena's rotation speed on every recording day
    rides = {}
    for s in use:
        h, d = read(s["path"])
        px = float(h["TrackerResolution_PixPerCM"])
        cx, cy = map(float, h["ArenaCenterXY"].split())
        lost = d.state.values == 5
        x = pd.Series(np.where(lost, np.nan, d.x.values)).ffill().bfill().values
        y = pd.Series(np.where(lost, np.nan, d.y.values)).ffill().bfill().values
        t = (d.t_ms.values - d.t_ms.values[0]) / 1000.0
        rides.setdefault(s["when"][:10], []).extend(passive_rides((x - cx) / px, -(y - cy) / px, t))
    OMEGA = {day: float(np.median(v)) for day, v in rides.items() if len(v) >= 10}
    json.dump(dict(omega=OMEGA, n=({k: len(v) for k, v in rides.items()})), open(os.path.join(HERE, "rotation_by_day.json"), "w"), indent=1)
    print("rotation by day (deg/s):", {k: round(v, 2) for k, v in sorted(OMEGA.items())})
    rows, tracks = [], {}
    for i, s in enumerate(use):
        omega = OMEGA.get(s["when"][:10], float(np.median(list(OMEGA.values()))))
        m, tr = session(s["path"], omega=omega)
        m["omega_deg_s"] = omega
        m["revolutions"] = omega * m["duration_s"] / 360.0
        m["entrances_per_rev"] = m["entrances"] / m["revolutions"] if m["revolutions"] else np.nan
        m["shocks_per_rev"] = m["shocks"] / m["revolutions"] if m["revolutions"] else np.nan
        m.update(mouse=s["mouse"], session=s["session"], day=s["day"], file=s["file"], folder=s["folder"], use=s["use"],
                 kind=s["kind"], when=s["when"])
        rows.append(m)
        key = "%s_s%d%s" % (s["mouse"], s["session"], "" if s["use"] else "_x")
        for k, v in tr.items():
            tracks[key + "|" + k] = v
        if i % 100 == 0:
            print(i, len(use), "%.0fs" % (time.time() - t0))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "session_metrics.csv"), index=False)
    np.savez_compressed(os.path.join(HERE, "tracks.npz"), **tracks)
    print("done", len(df), "sessions in %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
