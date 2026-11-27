"""The battery's measures: four families (timing, waveform, laminar,
structure), every one pushed through harness.Battery so it gets the same
contrasts. One number per recording per measure.

  python measures.py            # all four families, both event sets
  python measures.py timing     # one family

Type-specific measures are made for every eligible classifier
(dsdata.CLASSIFIERS, plus "used" = each recording's best eligible one) and
for DS1, DS2, the minority type, the majority type and DS3. A type needs 5
events or more on a recording to get a number there.
"""
import sys
import warnings

import numpy as np
from scipy import stats as st

import dsdata
import normcurves as N
from harness import Battery

warnings.filterwarnings("ignore")
MIN_TYPE = 5
NOCUT = ("ds1n", "ds2n", "ds1nx", "ds2nx")     # variants with no minimum type size (2026-11-17)
FILTER_FEATS = ("sink_amp", "sink_upper", "sink_lower", "blade_balance", "source_amp", "source_over_sink", "net_between", "cen_um",
                "sink_width_um", "sink_fwhm", "source_fwhm", "lat_source_minus_sink")
SETS = ("v6", "v8")      # Halo; No P-spikes (the replication set). v7 (10% grace) dropped 2026-11-18 with the border-filter family
import os  # noqa: E402
if os.environ.get("BATTERY_SETS"):   # the filter battery (2026-11-18): BATTERY_SETS=b_ds,b_none,... BATTERY_OUT=results_filters
    SETS = tuple(os.environ["BATTERY_SETS"].split(","))
# ONE CLASSIFIER (2026-11-18: "We had the winner. Keep those winners and vary
# everything else"): every type-specific measure uses each recording's winner
# (dsdata.Rec.winner, the quality check's FINAL OPTIMIZED SEPARATION), and the
# measures that compare classifiers are not made. BATTERY_ALL_CLASSIFIERS=1
# brings back run 3's behavior.
WINNER_ONLY = not os.environ.get("BATTERY_ALL_CLASSIFIERS")
CLFS = ["winner"] if WINNER_ONLY else None
OUTDIR = os.environ.get("BATTERY_OUT") and os.path.join(os.path.dirname(os.path.abspath(__file__)), os.environ["BATTERY_OUT"])


# ----------------------------------------------------------------- helpers
def half_widths(X, c0, win=30, search=6):
    """For traces X (events x samples) peaking near sample c0: the peak
    value, its sample, and how many samples to the left and right stay over
    half the peak (contiguously)."""
    n, T = X.shape
    seg = X[:, c0 - search:c0 + search + 1]
    p = c0 - search + seg.argmax(axis=1)
    pk = X[np.arange(n), p]
    above = X > 0.5 * pk[:, None]
    k = np.arange(1, win + 1)
    li = np.clip(p[:, None] - k[None, :], 0, T - 1)
    ri = np.clip(p[:, None] + k[None, :], 0, T - 1)
    left = np.cumprod(np.take_along_axis(above, li, axis=1), axis=1).sum(axis=1).astype(float)
    right = np.cumprod(np.take_along_axis(above, ri, axis=1), axis=1).sum(axis=1).astype(float)
    bad = ~(pk > 0)
    left[bad] = np.nan
    right[bad] = np.nan
    return pk, p, left, right


def masks_of(r):
    """{(classifier, variant): events mask} for every eligible classifier,
    plus ("used", ...) for the recording's best one."""
    out = {}
    # 2026-11-17: no minimum type size. Every classifier, eligible or not,
    # and the best one by index with no 5% rule ("best_nocut").
    conv = [c for c in dsdata.CONVENTIONAL if r.has(c)] if not WINNER_ONLY else []
    best_nc = max(conv, key=lambda c: r.si(c)) if conv else None
    for clf in ([c for c in dsdata.CLASSIFIERS if r.has(c)] if not WINNER_ONLY else []):
        t = r.types(clf)
        m3 = r.ds3(clf)
        nc = {"ds1n": t == 1, "ds2n": t == 2}
        if m3 is not None:
            nc["ds1nx"], nc["ds2nx"] = (t == 1) & ~m3, (t == 2) & ~m3
        for k, m in nc.items():
            out[(clf, k)] = m
            if clf == best_nc:
                out[("best_nocut", k)] = m
    for clf in (CLFS or dsdata.CLASSIFIERS):
        if not (r.has(clf) and r.eligible(clf)):
            continue
        t = r.types(clf)
        n1, n2 = (t == 1).sum(), (t == 2).sum()
        minor = 1 if n1 <= n2 else 2
        d = {"ds1": t == 1, "ds2": t == 2, "minor": t == minor, "major": t != minor}
        m3 = r.ds3(clf)
        if m3 is not None and m3.sum() >= MIN_TYPE:
            d["ds3"] = m3
        if m3 is not None:
            # 2026-11-17: DS1 and DS2 with the DS3 events taken out
            d["ds1x"], d["ds2x"] = (t == 1) & ~m3, (t == 2) & ~m3
        else:
            d["ds1x"], d["ds2x"] = t == 1, t == 2
        for k, m in d.items():
            out[(clf, k)] = m
            if clf == r.used and not WINNER_ONLY:
                out[("used", k)] = m
    return out


def stat_of(x, how, min_n=MIN_TYPE):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size < max(min_n, 2 if how in ("cv", "sd", "mad", "skew", "p90p10") else 1):
        return np.nan
    if how == "median":
        return float(np.median(x))
    if how == "mean":
        return float(np.mean(x))
    if how == "cv":
        m = np.mean(x)
        return float(np.std(x) / abs(m)) if m != 0 else np.nan
    if how == "sd":
        return float(np.std(x))
    if how == "mad":
        return float(st.median_abs_deviation(x))
    if how == "skew":
        return float(st.skew(x))
    if how == "p90p10":
        a, b = np.percentile(x, [10, 90])
        return float(b / a) if a > 0 else np.nan
    raise ValueError(how)


def push_event_feature(B, es, recs, feats, masks, family, name, desc, unit, all_stats, typed_stats=("median",)):
    """One per-event feature -> per-recording numbers: over all events (each
    of all_stats), per type and classifier (typed_stats), and the DS1/DS2
    ratio of medians per classifier."""
    for how in all_stats:
        B.add(family, "%s_%s" % (name, how), {r.lab: stat_of(feats[r.lab][name], how) for r in recs}, "%s; %s over all events" % (desc, how), unit, es, "", "all")
    keys = sorted({k for r in recs for k in masks[r.lab]})
    for clf, var in keys:
        for how in typed_stats:
            vals = {}
            mn = 1 if var in NOCUT else MIN_TYPE
            for r in recs:
                m = masks[r.lab].get((clf, var))
                if m is not None and m.sum() >= mn:
                    vals[r.lab] = stat_of(feats[r.lab][name][m], how, mn)
            B.add(family, "%s_%s" % (name, how), vals, "%s; %s over the %s events of classifier %s" % (desc, how, var, clf), unit, es, clf, var)
    for clf in sorted({k[0] for k in keys}):
        for v1, v2, tag, extra in (("ds1", "ds2", "ds1_over_ds2", ""), ("ds1x", "ds2x", "ds1x_over_ds2x", " (DS3 events taken out)"),
                                   ("ds1n", "ds2n", "ds1n_over_ds2n", " (no minimum type size)")):
            vals = {}
            for r in recs:
                m1, m2 = masks[r.lab].get((clf, v1)), masks[r.lab].get((clf, v2))
                if m1 is not None and m2 is not None:
                    a, b = stat_of(feats[r.lab][name][m1], "median"), stat_of(feats[r.lab][name][m2], "median")
                    if np.isfinite(a) and np.isfinite(b) and b != 0 and (a > 0) == (b > 0):
                        vals[r.lab] = a / b
            B.add(family, "%s_median" % name, vals, "%s; DS1 median over DS2 median%s, classifier %s" % (desc, extra, clf), "ratio", es, clf, tag)


# ----------------------------------------------------------- event features
def event_features(r):
    k = r.landmarks
    t = r.t_ms
    c0 = int(np.argmin(np.abs(t)))
    n = r.n
    f = {}
    # LFP at the source between the blades
    src = sorted({k["rowGU"], k["rowGL"]})
    lfp_tr = r.lfp[:, src, :].mean(axis=1)
    pk, p_l, le, ri = half_widths(lfp_tr, c0)
    f["lfp_src"] = r.lfp_peak[:, src].mean(axis=1)
    a, b = r.band
    f["lfp_max"] = r.lfp_peak[:, a:b + 1].max(axis=1)
    f["lfp_fwhm"] = le + ri + 1
    f["lfp_asym"] = (ri - le) / (ri + le + 1)
    pre, post = (t >= -30) & (t <= -10), (t >= 10) & (t <= 30)
    with np.errstate(all="ignore"):
        f["lfp_pre"] = lfp_tr[:, pre].mean(axis=1) / pk
        f["lfp_post"] = lfp_tr[:, post].mean(axis=1) / pk
    # CSD at the main sinks and at the source
    sU, sL = -r.csd[:, k["rowU"], :], -r.csd[:, k["rowL"], :]
    f["sink_upper"], f["sink_lower"] = -r.csd_peak[:, k["rowU"]], -r.csd_peak[:, k["rowL"]]
    f["sink_amp"] = 0.5 * (f["sink_upper"] + f["sink_lower"])
    sk = 0.5 * (sU + sL)
    pk_s, p_s, le, ri = half_widths(sk, c0)
    f["sink_fwhm"] = le + ri + 1
    f["sink_asym"] = (ri - le) / (ri + le + 1)
    f["sink_area"] = np.maximum(sk[:, (t >= -10) & (t <= 10)], 0).sum(axis=1)
    with np.errstate(all="ignore"):
        f["sink_pre"] = sk[:, pre].mean(axis=1) / pk_s
        f["sink_post"] = sk[:, post].mean(axis=1) / pk_s
    so = r.csd[:, src, :].mean(axis=1)
    pk_o, p_o, le, ri = half_widths(so, c0)
    f["source_amp"] = r.csd_peak[:, src].mean(axis=1)
    f["source_fwhm"] = le + ri + 1
    _, pU, _, _ = half_widths(sU, c0)
    _, pL, _, _ = half_widths(sL, c0)
    f["lat_lower_minus_upper"] = (pL - pU).astype(float)
    f["lat_sink_minus_lfp"] = (p_s - p_l).astype(float)
    f["lat_source_minus_sink"] = (p_o - p_s).astype(float)
    with np.errstate(all="ignore"):
        f["source_over_sink"] = np.where(f["sink_amp"] > 0, f["source_amp"] / f["sink_amp"], np.nan)
    f["det_peak"] = r.det_peak if r.det_peak is not None else np.full(n, np.nan)
    # depth
    pu, pl = np.maximum(f["sink_upper"], 0), np.maximum(f["sink_lower"], 0)
    with np.errstate(all="ignore"):
        f["blade_balance"] = np.where(pu + pl > 0, (pu - pl) / (pu + pl), np.nan)
    cen_v, wid, outer, cen_um = [], [], [], []
    for blade, row in (("upper", k["rowU"]), ("lower", k["rowL"])):
        rows = r.good(r.blade_rows(blade, 5))
        S = np.maximum(-r.csd_peak[:, rows], 0.0)
        tot = S.sum(axis=1)
        v = r.v(rows, blade)
        um = np.abs(rows - row) * dsdata.SPACING_UM * np.sign(v - 1.0)        # + = farther out than the main sink
        with np.errstate(all="ignore"):
            cv_ = (S * v[None, :]).sum(axis=1) / tot
            cu_ = (S * um[None, :]).sum(axis=1) / tot
            w_ = np.sqrt((S * (rows[None, :] * dsdata.SPACING_UM - ((S * rows[None, :] * dsdata.SPACING_UM).sum(axis=1) / tot)[:, None]) ** 2).sum(axis=1) / tot)
            o_ = S[:, v > 1.3].sum(axis=1) / tot
        for lst, x in ((cen_v, cv_), (cen_um, cu_), (wid, w_), (outer, o_)):
            lst.append(np.where(tot > 0, x, np.nan))
    f["cen_v_upper"], f["cen_v_lower"] = cen_v
    f["cen_v"] = np.nanmean(np.array(cen_v), axis=0)
    f["cen_um"] = np.nanmean(np.array(cen_um), axis=0)
    f["sink_width_um"] = np.nanmean(np.array(wid), axis=0)
    f["outer_share"] = np.nanmean(np.array(outer), axis=0)
    between = np.array(k["src_rows"], int)   # 2026-11-18: the sink lobes left out (was every row from rowU + 1 to rowL - 1)
    between = r.good(between)
    with np.errstate(all="ignore"):
        f["net_between"] = np.where(f["sink_amp"] > 0, r.csd_peak[:, between].mean(axis=1) / f["sink_amp"], np.nan)
    lo, hi = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)
    f["lfp_pos_u"] = r.u(lo + r.lfp_peak[:, lo:hi + 1].argmax(axis=1))
    # timing
    if r.times_s is not None:
        o = np.argsort(r.times_s)
        ts = r.times_s[o]
        d = np.diff(ts)
        prev, nxt = np.full(n, np.nan), np.full(n, np.nan)
        prev[o[1:]] = d
        nxt[o[:-1]] = d
        f["iei_prev"], f["iei_next"] = prev, nxt
        f["t_frac"] = r.times_s / r.dur_s
        okb = np.isfinite(r.theta_p)
        if okb.sum() > 20:
            tp, tb = r.theta_p[okb], r.theta_t[okb]
            rank = st.rankdata(tp) / tp.size
            idx = np.clip(np.searchsorted(tb, r.times_s, side="right") - 1, 0, tp.size - 1)
            f["theta_pct"] = rank[idx]
        else:
            f["theta_pct"] = np.full(n, np.nan)
    return f


EVENT_FEATURES = {
    # name: (family, description, unit, stats over all events)
    "lfp_src": ("waveform", "LFP at the DS peak at the source between the blades (mean of the source rows, +-3 ms)", "uV", ("median", "mean", "cv", "skew", "p90p10")),
    "lfp_max": ("waveform", "Largest LFP at the DS peak over the analyzed band", "uV", ("median", "mean", "cv")),
    "lfp_fwhm": ("waveform", "Width in time of the LFP at the source (full width at half maximum)", "ms", ("median", "mean", "cv")),
    "lfp_asym": ("waveform", "Time asymmetry of the LFP at the source: (right half-width - left) / full width; + = slower decay than rise", "", ("median", "mean")),
    "lfp_pre": ("waveform", "LFP at the source 30 to 10 ms before the peak, relative to the peak", "", ("median", "mean")),
    "lfp_post": ("waveform", "LFP at the source 10 to 30 ms after the peak, relative to the peak", "", ("median", "mean")),
    "sink_amp": ("waveform", "Sink at the DS peak, mean of the two main-sink rows (-CSD, +-3 ms)", "CSD units", ("median", "mean", "cv", "skew", "p90p10")),
    "sink_upper": ("waveform", "Sink at the DS peak at the upper blade's main-sink row", "CSD units", ("median", "cv")),
    "sink_lower": ("waveform", "Sink at the DS peak at the lower blade's main-sink row", "CSD units", ("median", "cv")),
    "sink_fwhm": ("waveform", "Duration of the sink (mean of the two main-sink rows; full width at half maximum)", "ms", ("median", "mean", "cv")),
    "sink_asym": ("waveform", "Time asymmetry of the sink: (right half-width - left) / full width", "", ("median", "mean")),
    "sink_area": ("waveform", "Sink summed over -10 to +10 ms (mean of the two main-sink rows)", "CSD units x ms", ("median", "cv")),
    "sink_pre": ("waveform", "Sink trace 30 to 10 ms before the peak, relative to the peak", "", ("median", "mean")),
    "sink_post": ("waveform", "Sink trace 10 to 30 ms after the peak, relative to the peak (negative = a source follows)", "", ("median", "mean")),
    "source_amp": ("waveform", "Source at the DS peak, mean of the source rows between the blades", "CSD units", ("median", "mean", "cv")),
    "source_fwhm": ("waveform", "Duration of the source between the blades (full width at half maximum)", "ms", ("median", "cv")),
    "lat_lower_minus_upper": ("waveform", "Peak time of the lower blade's sink minus the upper blade's", "ms", ("median", "mean", "sd")),
    "lat_sink_minus_lfp": ("waveform", "Peak time of the sink minus peak time of the LFP at the source", "ms", ("median", "mean", "sd")),
    "lat_source_minus_sink": ("waveform", "Peak time of the source minus peak time of the sink", "ms", ("median", "mean", "sd")),
    "source_over_sink": ("laminar", "Source between the blades over the sink at the main sinks, per event", "ratio", ("median", "mean", "cv")),
    "det_peak": ("waveform", "The detector's peak size of the event", "detector units", ("median", "cv", "p90p10")),
    "blade_balance": ("laminar", "(upper sink - lower sink) / (upper + lower) at the main-sink rows; + = upper blade larger", "", ("median", "mean", "sd")),
    "cen_v_upper": ("laminar", "Centroid of the upper blade's sink in units of v (0 source, 1 main sink, above 1 farther out)", "v", ("median", "sd")),
    "cen_v_lower": ("laminar", "Centroid of the lower blade's sink in units of v", "v", ("median", "sd")),
    "cen_v": ("laminar", "Centroid of the sink in units of v, mean of the two blades", "v", ("median", "mean", "sd")),
    "cen_um": ("laminar", "Centroid of the sink relative to the main-sink row, mean of the two blades (+ = farther out)", "um", ("median", "mean", "sd")),
    "sink_width_um": ("laminar", "Spread in depth of the sink within a blade (weighted SD), mean of the two blades", "um", ("median", "mean", "cv")),
    "outer_share": ("laminar", "Share of a blade's sink that lies beyond v = 1.3 (outer side), mean of the two blades", "share", ("median", "mean", "sd")),
    "net_between": ("laminar", "Mean CSD over the rows between the two main sinks, over the sink at the main sinks, per event (+ = net source)", "ratio", ("median", "mean", "sd")),
    "lfp_pos_u": ("laminar", "Where the LFP is largest, on the blade-to-blade axis u (0 upper sink, 1 lower sink)", "u", ("median", "sd")),
    "iei_prev": ("timing", "Interval since the previous event (any type)", "s", ("median",)),
    "iei_next": ("timing", "Interval to the next event (any type)", "s", ("median",)),
    "t_frac": ("timing", "When in the recording the event falls (0 start, 1 end)", "", ("median", "mean")),
    "theta_pct": ("timing", "Theta power at the event's time, as a percentile of the recording's 4 s bins", "share", ("median", "mean")),
}


# ------------------------------------------------------------------ timing
def train_stats(ts, dur_s, theta_t=None, theta_p=None, full=True):
    """Numbers describing one train of event times."""
    ts = np.sort(np.asarray(ts, float))
    o = {}
    n = ts.size
    o["rate"] = n / (dur_s / 60.0)
    if n < 8:
        return o
    d = np.diff(ts)
    d = d[d > 0]
    o["iei_median"], o["iei_mean"] = float(np.median(d)), float(np.mean(d))
    o["iei_cv"] = float(np.std(d) / np.mean(d))
    o["iei_cv2"] = float(np.mean(2 * np.abs(np.diff(d)) / (d[1:] + d[:-1])))
    o["iei_lv"] = float(3 * np.mean(((d[:-1] - d[1:]) / (d[:-1] + d[1:])) ** 2))
    o["short_1s"] = float(np.mean(d < 1.0))
    for w in ((10,) if not full else (1, 5, 10, 30, 60)):
        nb = int(dur_s // w)
        if nb >= 10:
            c = np.histogram(ts, bins=np.arange(nb + 1) * float(w))[0]
            o["fano_%ds" % w] = float(c.var() / c.mean()) if c.mean() > 0 else np.nan
    nm = int(dur_s // 60)
    if nm >= 8:
        c = np.histogram(ts, bins=np.arange(nm + 1) * 60.0)[0]
        o["drift_rho"] = float(st.spearmanr(np.arange(nm), c).correlation) if np.ptp(c) > 0 else np.nan
        if full:
            o["minute_cv"] = float(c.std() / c.mean())
            o["empty_minutes"] = float(np.mean(c == 0))
    h1, h2 = (ts < dur_s / 2).sum(), (ts >= dur_s / 2).sum()
    o["second_half_share"] = float(h2 / n)
    if theta_p is not None:
        okb = np.isfinite(theta_p)
        theta_t, theta_p = theta_t[okb], theta_p[okb]
    if theta_p is not None and theta_p.size > 20:
        idx = np.clip(np.searchsorted(theta_t, ts, side="right") - 1, 0, theta_p.size - 1)
        c = np.bincount(idx, minlength=theta_p.size).astype(float)
        o["theta_rho"] = float(st.spearmanr(theta_p, c).correlation) if np.ptp(c) > 0 else np.nan
        lo, hi = np.percentile(theta_p, [100 / 3.0, 200 / 3.0])
        a, b = c[theta_p <= lo].mean(), c[theta_p >= hi].mean()
        o["theta_high_over_low"] = float(b / a) if a > 0 else np.nan
    if full:
        for th in (0.1, 0.25, 0.5, 2.0):
            o["short_%gs" % th] = float(np.mean(d < th))
        for q in (10, 25, 75, 90):
            o["iei_p%d" % q] = float(np.percentile(d, q))
        near = np.array([((ts > x - 1.0) & (ts < x + 1.0)).sum() - 1 for x in ts])
        o["in_trains"] = float(np.mean(near >= 2))
        if d.size > 10:
            o["iei_serial_rho"] = float(st.spearmanr(d[:-1], d[1:]).correlation)
        nb = int(dur_s // 10)
        if nb >= 20:
            c = np.histogram(ts, bins=np.arange(nb + 1) * 10.0)[0].astype(float)
            o["count_autocorr_10s"] = float(np.corrcoef(c[:-1], c[1:])[0, 1]) if np.ptp(c) > 0 else np.nan
        o["first_event_s"] = float(ts[0])
    return o


TRAIN_DESC = {
    "rate": ("Events per minute", "1/min"), "iei_median": ("Median inter-event interval", "s"), "iei_mean": ("Mean inter-event interval", "s"),
    "iei_cv": ("CV of inter-event intervals", ""), "iei_cv2": ("Local variation CV2 of successive intervals", ""),
    "iei_lv": ("Local variation LV of successive intervals", ""), "short_1s": ("Share of intervals under 1 s", "share"),
    "fano_1s": ("Fano factor of counts in 1 s windows", ""), "fano_5s": ("Fano factor of counts in 5 s windows", ""),
    "fano_10s": ("Fano factor of counts in 10 s windows", ""), "fano_30s": ("Fano factor of counts in 30 s windows", ""),
    "fano_60s": ("Fano factor of counts in 60 s windows", ""), "drift_rho": ("Rank correlation of events per minute with time in the recording", "rho"),
    "minute_cv": ("CV of events per minute", ""), "empty_minutes": ("Share of minutes with no event", "share"),
    "second_half_share": ("Share of the events that fall in the second half of the recording", "share"),
    "theta_rho": ("Rank correlation of events per 4 s bin with theta power", "rho"),
    "theta_high_over_low": ("Events per bin in the top theta tercile over the bottom tercile", "ratio"),
    "short_0.1s": ("Share of intervals under 0.1 s", "share"), "short_0.25s": ("Share of intervals under 0.25 s", "share"),
    "short_0.5s": ("Share of intervals under 0.5 s", "share"), "short_2s": ("Share of intervals under 2 s", "share"),
    "iei_p10": ("10th percentile of inter-event intervals", "s"), "iei_p25": ("25th percentile of inter-event intervals", "s"),
    "iei_p75": ("75th percentile of inter-event intervals", "s"), "iei_p90": ("90th percentile of inter-event intervals", "s"),
    "in_trains": ("Share of events with two or more other events within 1 s", "share"),
    "iei_serial_rho": ("Rank correlation of successive inter-event intervals", "rho"),
    "count_autocorr_10s": ("Lag-1 autocorrelation of counts in 10 s windows", "r"), "first_event_s": ("Time of the first event", "s"),
}


def run_timing(B, es, recs, feats, masks):
    # trains: all events, then each type
    allst = {r.lab: train_stats(r.times_s, r.dur_s, r.theta_t, r.theta_p, True) for r in recs}
    for key in sorted({k for d in allst.values() for k in d}):
        B.add("timing", key, {lab: d.get(key, np.nan) for lab, d in allst.items()}, "%s; all events" % TRAIN_DESC[key][0], TRAIN_DESC[key][1], es, "", "all")
    keys = sorted({k for r in recs for k in masks[r.lab]})
    for clf, var in keys:
        sts = {}
        for r in recs:
            m = masks[r.lab].get((clf, var))
            if m is not None and m.sum() >= MIN_TYPE:
                sts[r.lab] = train_stats(r.times_s[m], r.dur_s, r.theta_t, r.theta_p, False)
                sts[r.lab]["share"] = float(m.mean())
        for key in sorted({k for d in sts.values() for k in d}):
            desc, unit = TRAIN_DESC.get(key, ("Share of all events", "share"))
            B.add("timing", key, {lab: d.get(key, np.nan) for lab, d in sts.items()}, "%s; the %s events of classifier %s" % (desc, var, clf), unit, es, clf, var)
    # order of the two types
    for clf in sorted({k[0] for k in keys}):
        runs, drift, near, lag = {}, {}, {}, {}
        for r in recs:
            m1 = masks[r.lab].get((clf, "ds1"))
            if m1 is None:
                continue
            o = np.argsort(r.times_s)
            s = m1[o].astype(int)
            ts = r.times_s[o]
            n1, n2 = s.sum(), (1 - s).sum()
            nr = 1 + int((np.diff(s) != 0).sum())
            mu = 2.0 * n1 * n2 / (n1 + n2) + 1
            var = 2.0 * n1 * n2 * (2.0 * n1 * n2 - n1 - n2) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
            runs[r.lab] = float((nr - mu) / np.sqrt(var)) if var > 0 else np.nan
            drift[r.lab] = float(st.spearmanr(ts, s).correlation)
            t1, t2 = ts[s == 1], ts[s == 0]
            if t1.size >= MIN_TYPE and t2.size >= MIN_TYPE:
                j = np.searchsorted(t2, t1)
                dn = np.minimum(np.abs(t1 - t2[np.clip(j, 0, t2.size - 1)]), np.abs(t1 - t2[np.clip(j - 1, 0, t2.size - 1)]))
                obs = float(np.mean(dn < 1.0))
                exp = 1.0 - np.exp(-2.0 * t2.size / r.dur_s)              # Poisson: a DS2 within +-1 s
                near[r.lab] = obs / exp if exp > 0 else np.nan
                nxt = np.searchsorted(t2, t1, side="right")
                ok = nxt < t2.size
                a = np.median(t2[nxt[ok]] - t1[ok]) if ok.sum() >= MIN_TYPE else np.nan      # DS1 -> next DS2
                nx1 = np.searchsorted(t1, t2, side="right")
                ok2 = nx1 < t1.size
                b = np.median(t1[nx1[ok2]] - t2[ok2]) if ok2.sum() >= MIN_TYPE else np.nan   # DS2 -> next DS1
                # each against what the other type's rate alone predicts (median of an exponential wait)
                ea, eb = np.log(2) * r.dur_s / t2.size, np.log(2) * r.dur_s / t1.size
                lag[r.lab] = float(np.log((a / ea) / (b / eb))) if np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0 else np.nan
        B.add("timing", "type_runs_z", runs, "Runs test z of the DS1/DS2 sequence (negative = same type follows itself more than chance), classifier %s" % clf, "z", es, clf, "order")
        B.add("timing", "ds1_share_drift_rho", drift, "Rank correlation of 'is DS1' with time in the recording, classifier %s" % clf, "rho", es, clf, "order")
        B.add("timing", "ds1_near_ds2_ratio", near, "Share of DS1 with a DS2 within 1 s, over the share expected from DS2's rate alone, classifier %s" % clf, "ratio", es, clf, "order")
        B.add("timing", "lag_asym_ds1_to_ds2", lag, "log of (median wait from a DS1 to the next DS2, over its Poisson expectation) over the same from DS2 to DS1, classifier %s" % clf, "log ratio", es, clf, "order")
    # size against timing
    for name, other, desc in (("size_vs_iei_prev_rho", "iei_prev", "Rank correlation across events of the sink size with the interval since the previous event"),
                              ("size_vs_iei_next_rho", "iei_next", "Rank correlation across events of the sink size with the interval to the next event"),
                              ("size_drift_rho", "t_frac", "Rank correlation across events of the sink size with time in the recording"),
                              ("lfp_drift_rho", "t_frac", "Rank correlation across events of the LFP size at the source with time in the recording")):
        vals = {}
        for r in recs:
            x = feats[r.lab]["lfp_src" if name.startswith("lfp") else "sink_amp"]
            y = feats[r.lab][other]
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() >= 10:
                vals[r.lab] = float(st.spearmanr(x[ok], y[ok]).correlation)
        B.add("timing", name, vals, desc + "; all events", "rho", es, "", "all")
    B.add("timing", "theta_cv", {r.lab: float(np.nanstd(r.theta_p) / np.nanmean(r.theta_p)) if np.isfinite(r.theta_p).sum() > 20 else np.nan for r in recs},
          "CV of theta power over the recording's 4 s bins (how much the state varies)", "", es, "", "all")


# ----------------------------------------------------------------- laminar
def run_laminar(B, es, recs, feats, masks):
    for key, desc in (("blade_um", "Distance between the two main sinks"), ("gcl_to_sink_upper_um", "Distance from the source to the main sink, upper blade"),
                      ("gcl_to_sink_lower_um", "Distance from the source to the main sink, lower blade"), ("source_gap_um", "Distance between the two sources (0 = one source)")):
        B.add("laminar", key, {r.lab: r.landmarks[key] for r in recs}, desc + " (from the mean of all events)", "um", es, "", "all")
    B.add("laminar", "gcl_to_sink_mean_um", {r.lab: 0.5 * (r.landmarks["gcl_to_sink_upper_um"] + r.landmarks["gcl_to_sink_lower_um"]) for r in recs},
          "Distance from the source to the main sink, mean of the two blades", "um", es, "", "all")
    B.add("laminar", "gcl_to_sink_asym", {r.lab: (r.landmarks["gcl_to_sink_upper_um"] - r.landmarks["gcl_to_sink_lower_um"]) /
                                          (r.landmarks["gcl_to_sink_upper_um"] + r.landmarks["gcl_to_sink_lower_um"]) for r in recs},
          "(upper - lower) / (upper + lower) source-to-main-sink distance", "", es, "", "all")
    B.add("laminar", "source_gap_over_blade", {r.lab: r.landmarks["source_gap_um"] / r.landmarks["blade_um"] for r in recs},
          "Distance between the two sources over the distance between the two main sinks", "ratio", es, "", "all")
    B.add("laminar", "mean_sink_asym", {r.lab: (r.landmarks["sinkU"] - r.landmarks["sinkL"]) / (r.landmarks["sinkU"] + r.landmarks["sinkL"]) for r in recs},
          "(upper - lower) / (upper + lower) main sink of the mean DS", "", es, "", "all")
    B.add("laminar", "mean_source_over_sinks", {r.lab: r.landmarks["source"] / (0.5 * (r.landmarks["sinkU"] + r.landmarks["sinkL"])) for r in recs},
          "Largest source between the blades over the mean of the two main sinks, on the mean DS", "ratio", es, "", "all")
    C = {r.lab: N.curves(r) for r in recs}
    # the mean profile, point by point
    for i in range(5, N.GRID_U.size - 5, 5):
        B.add("laminar", "profile_u_%+.2f" % N.GRID_U[i], {lab: c["prof_u"][i - 2:i + 3].mean() for lab, c in C.items()},
              "Mean CSD at the DS peak at u = %+.2f (blade-to-blade axis; mean of 5 grid points), in units of the main sinks" % N.GRID_U[i], "main sinks", es, "", "all")
        B.add("laminar", "lfp_profile_u_%+.2f" % N.GRID_U[i], {lab: c["lfp_u"][i - 2:i + 3].mean() for lab, c in C.items()},
              "Mean LFP at the DS peak at u = %+.2f, relative to its largest value" % N.GRID_U[i], "of max", es, "", "all")
    for i in range(4, N.GRID_V.size - 4, 6):
        B.add("laminar", "profile_v_%+.2f" % N.GRID_V[i], {lab: np.nanmean(c["fold"][i - 2:i + 3]) for lab, c in C.items()},
              "Mean CSD at the DS peak at v = %+.2f (folded blade axis, both blades averaged), in units of the blade's main sink" % N.GRID_V[i], "main sink", es, "", "all")
    for name, lo, hi, desc in (("net_u_0.2_0.8", 0.2, 0.8, "between the blades (u 0.2 to 0.8)"), ("net_u_0.4_0.6", 0.4, 0.6, "midway between the blades (u 0.4 to 0.6)"),
                               ("net_u_-0.5_-0.2", -0.5, -0.2, "above the upper sink (u -0.5 to -0.2)"), ("net_u_1.2_1.5", 1.2, 1.5, "below the lower sink (u 1.2 to 1.5)")):
        w = (N.GRID_U >= lo) & (N.GRID_U <= hi)
        B.add("laminar", name, {lab: np.nanmean(c["prof_u"][w]) for lab, c in C.items()}, "Mean CSD of the mean DS %s, in units of the main sinks" % desc, "main sinks", es, "", "all")
    for name, lo, hi, desc in (("fold_outer_1.3_2.2", 1.3, 2.2, "beyond the main sink (v 1.3 to 2.2)"), ("fold_inner_0.3_0.7", 0.3, 0.7, "between source and main sink (v 0.3 to 0.7)"),
                               ("fold_source_-0.3_0.3", -0.3, 0.3, "at the source (v -0.3 to 0.3)")):
        w = (N.GRID_V >= lo) & (N.GRID_V <= hi)
        B.add("laminar", name, {lab: np.nanmean(c["fold"][w]) for lab, c in C.items()}, "Mean CSD of the mean DS %s, folded blades, in units of the main sink" % desc, "main sink", es, "", "all")
    # width of the main sink on the mean DS
    wid_um, wid_v = {}, {}
    for r in recs:
        k = r.landmarks
        a, b = [], []
        for blade, row, dist in (("upper", k["rowU"], k["gcl_to_sink_upper_um"]), ("lower", k["rowL"], k["gcl_to_sink_lower_um"])):
            s = np.maximum(-r.mean_csd_peak, 0)
            pk, p, le, ri = half_widths(s[None, :], row, win=12, search=1)
            w = float(le[0] + ri[0] + 1) * dsdata.SPACING_UM
            a.append(w)
            b.append(w / dist)
        wid_um[r.lab], wid_v[r.lab] = float(np.mean(a)), float(np.mean(b))
    B.add("laminar", "main_sink_fwhm_um", wid_um, "Width in depth of the main sink on the mean DS (FWHM, mean of the two blades)", "um", es, "", "all")
    B.add("laminar", "main_sink_fwhm_v", wid_v, "Width in depth of the main sink on the mean DS over the source-to-sink distance (mean of the two blades)", "v", es, "", "all")
    # typed mean profiles
    clfs = CLFS or ([c for c in dsdata.CLASSIFIERS] + ["used"])
    for clf in clfs:
        out = {k: {} for k in ("ds1_pos_over_ds2", "ds1_size_over_ds2", "ds1_cen_v", "ds2_cen_v", "ds1_outer_peak")}
        for r in recs:
            c_ = r.used if clf == "used" else clf
            if not (c_ and r.has(c_) and r.eligible(c_)):
                continue
            ty = N.typed(r, c_)
            if "ratio" not in ty:
                continue
            out["ds1_pos_over_ds2"][r.lab] = np.nanmean(ty["ratio"])
            out["ds1_size_over_ds2"][r.lab] = np.nanmean(ty["amp"])
            out["ds1_cen_v"][r.lab] = np.nanmean(ty["cen"][1])
            out["ds2_cen_v"][r.lab] = np.nanmean(ty["cen"][2])
            w = (N.GRID_V >= 1.3) & (N.GRID_V <= 2.4)
            out["ds1_outer_peak"][r.lab] = float(np.nanmax(np.maximum(-ty["fold"][1][w], 0)))
        B.add("laminar", "ds1_pos_over_ds2", out["ds1_pos_over_ds2"], "DS1 sink centroid over DS2 sink centroid, as distances from the source (v), mean of blades; classifier %s" % clf, "ratio", es, clf, "typed")
        B.add("laminar", "ds1_size_over_ds2", out["ds1_size_over_ds2"], "DS1 mean sink peak over DS2 mean sink peak, mean of blades; classifier %s" % clf, "ratio", es, clf, "typed")
        B.add("laminar", "ds1_cen_v", out["ds1_cen_v"], "DS1 sink centroid on the folded axis v; classifier %s" % clf, "v", es, clf, "typed")
        B.add("laminar", "ds2_cen_v", out["ds2_cen_v"], "DS2 sink centroid on the folded axis v; classifier %s" % clf, "v", es, clf, "typed")
        B.add("laminar", "ds1_outer_peak", out["ds1_outer_peak"], "Largest DS1 mean sink beyond v = 1.3, in units of DS2's main sink; classifier %s" % clf, "DS2 sink", es, clf, "typed")


# --------------------------------------------------------------- structure
def _si(W0, m):
    na, nb = int(m.sum()), int((~m).sum())
    if na < 2 or nb < 2:
        return np.nan
    Wm = W0 @ m
    saa, sab = float(m @ Wm), float((~m) @ Wm)
    sbb = float(W0.sum()) - saa - 2.0 * sab
    den = (saa / (na * (na - 1)) + sbb / (nb * (nb - 1))) / 2.0
    return 1.0 - (sab / (na * nb)) / den if den > 0 else np.nan


def _ari(a, b):
    from sklearn.metrics import adjusted_rand_score
    return float(adjusted_rand_score(a, b))


def run_structure(B, es, recs, feats, masks):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.mixture import GaussianMixture
    Wz = {}
    for r in recs:
        Wz[r.lab] = {}
        for k in ("both", "top", "bottom"):
            if k in r.W:
                w = np.array(r.W[k], float)
                np.fill_diagonal(w, 0.0)
                Wz[r.lab][k] = w
    for clf in (CLFS or dsdata.CLASSIFIERS):
        B.add("structure", "separation_index", {r.lab: r.si(clf) for r in recs if r.has(clf) and r.eligible(clf)},
              "Separation index of classifier %s (recordings where it is eligible)" % clf, "", es, clf, "eligible")
        B.add("structure", "separation_index", {r.lab: r.si(clf) for r in recs if r.has(clf)}, "Separation index of classifier %s (eligible or not)" % clf, "", es, clf, "any")
        for blade in ("top", "bottom"):
            B.add("structure", "separation_index_%s" % ("upper" if blade == "top" else "lower"),
                  {r.lab: _si(Wz[r.lab][blade], r.types(clf) == 1) for r in recs if r.has(clf) and r.eligible(clf) and blade in Wz[r.lab]},
                  "Separation index of classifier %s in the %s blade alone" % (clf, "upper" if blade == "top" else "lower"), "", es, clf, "eligible")
        B.add("structure", "minority_share", {r.lab: min(r.labels[clf]["n1"], r.labels[clf]["n2"]) / float(r.n) for r in recs if r.has(clf)},
              "Share of events in the smaller type, classifier %s (eligible or not)" % clf, "share", es, clf, "any")
        B.add("structure", "ds1_share", {r.lab: r.labels[clf]["n1"] / float(r.n) for r in recs if r.has(clf) and r.eligible(clf)}, "Share of events that are DS1, classifier %s" % clf, "share", es, clf, "eligible")
        for cutv in (0.3, 0.5, 0.7):
            vals, uns, fin, s1, s2, mab = {}, {}, {}, {}, {}, {}
            for r in recs:
                sc = (r.ds3w.get(clf) or {}).get("score")
                if not (r.has(clf) and r.eligible(clf)) or sc is None:
                    continue
                sc = np.asarray(sc, float)
                ok = np.isfinite(sc)
                m3 = ok & (np.abs(sc) <= cutv)
                vals[r.lab] = float(m3.mean())
                if cutv == 0.5:
                    uns[r.lab] = float((~ok).mean())
                    t3 = np.where(m3, 3, r.types(clf))
                    keep = (t3 == 1) | (t3 == 2)
                    if min((t3 == 1).sum(), (t3 == 2).sum()) >= 5:
                        w = Wz[r.lab]["both"][np.ix_(keep, keep)]
                        fin[r.lab] = _si(w, t3[keep] == 1)
                    if ok.sum() >= 10:
                        s1[r.lab], s2[r.lab] = float((sc[ok] > 0.5).mean()), float((sc[ok] < -0.5).mean())
                        mab[r.lab] = float(np.median(np.abs(sc[ok])))
            B.add("structure", "ds3_share_cut%.1f" % cutv, vals, "Share of events scored DS3 (relative sink within +-%.1f), classifier %s" % (cutv, clf), "share", es, clf, "eligible")
            if cutv == 0.5:
                B.add("structure", "unscorable_share", uns, "Share of events whose two layer sinks are under the noise floor, classifier %s" % clf, "share", es, clf, "eligible")
                B.add("structure", "separation_index_without_ds3", fin, "Separation index of DS1 against DS2 after DS3 events are taken out, classifier %s" % clf, "", es, clf, "eligible")
                B.add("structure", "relsink_above_0.5_share", s1, "Share of scored events with relative sink above +0.5 (outer), classifier %s" % clf, "share", es, clf, "eligible")
                B.add("structure", "relsink_below_-0.5_share", s2, "Share of scored events with relative sink below -0.5 (middle), classifier %s" % clf, "share", es, clf, "eligible")
                B.add("structure", "relsink_abs_median", mab, "Median absolute relative sink of the scored events, classifier %s" % clf, "", es, clf, "eligible")
        B.add("structure", "ds3_contact_gap_um", {r.lab: r.ds3_gap_um[clf] for r in recs if r.has(clf) and r.eligible(clf) and r.ds3_gap_um.get(clf) is not None},
              "Distance between the outer and middle layer contacts used for DS3, classifier %s" % clf, "um", es, clf, "eligible")
    if WINNER_ONLY:
        run_structure_rest(B, es, recs, Wz)
        return
    # over classifiers
    conv = dsdata.CONVENTIONAL
    def over(fn, elig=True):
        out = {}
        for r in recs:
            v = [r.si(c) for c in conv if r.has(c) and (r.eligible(c) or not elig)]
            if v:
                out[r.lab] = fn(v)
        return out
    B.add("structure", "si_max_eligible", over(max), "Highest separation index over the eligible conventional classifiers", "", es, "", "over_classifiers")
    B.add("structure", "si_mean_eligible", over(np.mean), "Mean separation index over the eligible conventional classifiers", "", es, "", "over_classifiers")
    B.add("structure", "si_median_eligible", over(np.median), "Median separation index over the eligible conventional classifiers", "", es, "", "over_classifiers")
    B.add("structure", "si_max_any", over(max, False), "Highest separation index over the conventional classifiers, eligible or not", "", es, "", "over_classifiers")
    B.add("structure", "si_mean_any", over(np.mean, False), "Mean separation index over the conventional classifiers, eligible or not", "", es, "", "over_classifiers")
    B.add("structure", "n_classifiers_eligible", {r.lab: float(sum(r.has(c) and r.eligible(c) for c in conv)) for r in recs}, "Number of conventional classifiers that are eligible", "count", es, "", "over_classifiers")
    B.add("structure", "si_opt_curve", {r.lab: r.si("opt_curve") for r in recs if r.has("opt_curve")}, "Separation index of the boundary fitted to maximize it (in-sample)", "", es, "opt_curve", "any")
    B.add("structure", "si_opt_curve_heldout", {r.lab: r.labels["opt_curve"].get("heldout_si") for r in recs if r.has("opt_curve")},
          "Held-out separation index of the optimized boundary (fit on half the events, scored on the other half)", "", es, "opt_curve", "heldout")
    B.add("structure", "si_gain_opt_over_used", {r.lab: r.si("opt_curve") - r.si(r.used) for r in recs if r.has("opt_curve") and r.used},
          "Optimized boundary's index minus the best conventional classifier's", "", es, "", "over_classifiers")
    # agreement between classifiers
    agree, allsame, with_used = {}, {}, {}
    for r in recs:
        el = [c for c in conv if r.has(c) and r.eligible(c)]
        if len(el) >= 3:
            T = [r.types(c) for c in el]
            pairs = [_ari(T[i], T[j]) for i in range(len(el)) for j in range(i + 1, len(el))]
            agree[r.lab] = float(np.mean(pairs))
            ref = T[0]
            al = np.array([np.where(np.mean(t == ref) >= 0.5, t, 3 - t) for t in T])
            allsame[r.lab] = float(np.mean((al == al[0]).all(axis=0)))
            with_used[r.lab] = float(np.mean([_ari(r.types(r.used), t) for c, t in zip(el, T) if c != r.used]))
    B.add("structure", "classifier_agreement_ari", agree, "Mean adjusted Rand index over pairs of eligible conventional classifiers", "ARI", es, "", "over_classifiers")
    B.add("structure", "classifier_all_agree_share", allsame, "Share of events given the same type by every eligible conventional classifier", "share", es, "", "over_classifiers")
    B.add("structure", "classifier_agreement_with_used", with_used, "Mean adjusted Rand index of the eligible conventional classifiers with the best one", "ARI", es, "", "over_classifiers")
    run_structure_rest(B, es, recs, Wz)


def run_structure_rest(B, es, recs, Wz):
    """The structure measures that do not depend on a classifier."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.mixture import GaussianMixture
    # one cloud or two, on the PCA plane
    cloud = {k: {} for k in ("pc1_bimodality", "pc1_kurtosis", "pc1_skew_abs", "pc_var_ratio", "bic_2_minus_1", "bic_3_minus_2", "kmeans_silhouette", "outlier_share",
                             "gmm2_minor_weight", "pc2_bimodality")}
    for r in recs:
        X = np.asarray(r.pc, float)
        if X.ndim != 2 or X.shape[0] < 20 or not np.isfinite(X).all():
            continue
        Z = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-12)
        for j, nm in ((0, "pc1"), (1, "pc2")):
            g1, g2, n = st.skew(Z[:, j]), st.kurtosis(Z[:, j]), Z.shape[0]
            cloud[nm + "_bimodality"][r.lab] = float((g1 ** 2 + 1) / (g2 + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))))
        cloud["pc1_kurtosis"][r.lab] = float(st.kurtosis(Z[:, 0]))
        cloud["pc1_skew_abs"][r.lab] = float(abs(st.skew(Z[:, 0])))
        cloud["pc_var_ratio"][r.lab] = float(X[:, 0].var() / X[:, 1].var()) if X[:, 1].var() > 0 else np.nan
        bic = [GaussianMixture(k, covariance_type="full", n_init=3, random_state=0, reg_covar=1e-4).fit(Z).bic(Z) for k in (1, 2, 3)]
        cloud["bic_2_minus_1"][r.lab] = float((bic[1] - bic[0]) / Z.shape[0])
        cloud["bic_3_minus_2"][r.lab] = float((bic[2] - bic[1]) / Z.shape[0])
        g = GaussianMixture(2, covariance_type="full", n_init=3, random_state=0, reg_covar=1e-4).fit(Z)
        cloud["gmm2_minor_weight"][r.lab] = float(g.weights_.min())
        km = KMeans(2, n_init=5, random_state=0).fit(Z)
        cloud["kmeans_silhouette"][r.lab] = float(silhouette_score(Z, km.labels_)) if 1 < km.labels_.sum() < Z.shape[0] - 1 else np.nan
        d2 = (Z @ np.linalg.inv(np.cov(Z.T)) * Z).sum(axis=1)
        cloud["outlier_share"][r.lab] = float(np.mean(d2 > 9.21))                       # chi-square, 2 df, 99%
    CD = {"pc1_bimodality": "Bimodality coefficient of PC1 (above 0.555 suggests two modes)", "pc2_bimodality": "Bimodality coefficient of PC2",
          "pc1_kurtosis": "Excess kurtosis of PC1", "pc1_skew_abs": "Absolute skewness of PC1", "pc_var_ratio": "Variance of PC1 over variance of PC2",
          "bic_2_minus_1": "BIC of two Gaussians minus one Gaussian on the PCA plane, per event (negative = two fit better)",
          "bic_3_minus_2": "BIC of three Gaussians minus two on the PCA plane, per event", "kmeans_silhouette": "Silhouette of a 2-means split of the PCA plane",
          "outlier_share": "Share of events beyond the 99% Mahalanobis distance on the PCA plane (1% expected for one Gaussian)",
          "gmm2_minor_weight": "Weight of the smaller of two Gaussians fitted to the PCA plane"}
    for k, v in cloud.items():
        B.add("structure", k, v, CD[k], "", es, "", "cloud")
    # the overlap matrix
    ov = {k: {} for k in ("overlap_mean", "overlap_cv", "overlap_eig2", "overlap_eiggap", "overlap_mean_upper", "overlap_mean_lower")}
    for r in recs:
        w = Wz[r.lab].get("both")
        if w is None:
            continue
        n = w.shape[0]
        off = w[np.triu_indices(n, 1)]
        ov["overlap_mean"][r.lab] = float(off.mean())
        ov["overlap_cv"][r.lab] = float(off.std() / off.mean()) if off.mean() > 0 else np.nan
        dg = w.sum(axis=1)
        if (dg > 0).all():
            Ln = w / np.sqrt(dg[:, None] * dg[None, :])
            ev = np.sort(np.linalg.eigvalsh(Ln))[::-1]
            ov["overlap_eig2"][r.lab] = float(ev[1])
            ov["overlap_eiggap"][r.lab] = float(ev[1] - ev[2])
        for k, nm in (("top", "overlap_mean_upper"), ("bottom", "overlap_mean_lower")):
            if k in Wz[r.lab]:
                ov[nm][r.lab] = float(Wz[r.lab][k][np.triu_indices(n, 1)].mean())
    OD = {"overlap_mean": "Mean sink overlap between pairs of events, whole band (how alike the events are)", "overlap_cv": "CV of the pairwise sink overlap",
          "overlap_eig2": "Second eigenvalue of the normalized overlap matrix (near 1 = splits cleanly in two)",
          "overlap_eiggap": "Second minus third eigenvalue of the normalized overlap matrix", "overlap_mean_upper": "Mean pairwise sink overlap, upper blade",
          "overlap_mean_lower": "Mean pairwise sink overlap, lower blade"}
    for k, v in ov.items():
        B.add("structure", k, v, OD[k], "", es, "", "overlap")
    # the literature's procedure for DS3
    for blade in ("upper", "lower"):
        L = {r.lab: N.literature_ds3(r, blade) for r in recs}
        for c, nm in ((1, "ds1"), (2, "ds2"), (3, "ds3"), (0, "unscored")):
            B.add("structure", "lit_%s_share" % nm, {lab: x["share"][c] for lab, x in L.items() if x is not None},
                  "Share of events that are %s by the procedure of Tarcsay et al. 2025 (layers from the extreme quarters of PC1), %s blade" % (nm, blade), "share", es, "literature", blade)
        B.add("structure", "lit_gap_um", {lab: x["gap_um"] for lab, x in L.items() if x is not None}, "Distance between the outer and middle contacts placed by the literature's procedure, %s blade" % blade, "um", es, "literature", blade)
        B.add("structure", "lit_layers_placed", {lab: float(x is not None) for lab, x in L.items()}, "1 if the literature's procedure places two different contacts, 0 if it cannot, %s blade" % blade, "0/1", es, "literature", blade)
        B.add("structure", "lit_relsink_abs_median", {lab: float(np.nanmedian(np.abs(x["rel"]))) for lab, x in L.items() if x is not None and np.isfinite(x["rel"]).sum() >= 10},
              "Median absolute relative sink by the literature's procedure, %s blade" % blade, "", es, "literature", blade)
    # stability on random halves
    mean_h, sd_h = {}, {}
    for r in recs:
        if WINNER_ONLY or not r.used:
            continue
        m = r.types(r.used) == 1
        rng = np.random.default_rng(5)
        v = []
        for _ in range(20):
            i = rng.permutation(r.n)[: r.n // 2]
            v.append(_si(Wz[r.lab]["both"][np.ix_(i, i)], m[i]))
        v = np.array(v)
        v = v[np.isfinite(v)]
        if v.size >= 10:
            mean_h[r.lab], sd_h[r.lab] = float(v.mean()), float(v.std())
    B.add("structure", "si_used_halves_mean", mean_h, "Separation index of the best classifier on random halves of the events, mean of 20", "", es, "used", "stability")
    B.add("structure", "si_used_halves_sd", sd_h, "Separation index of the best classifier on random halves of the events, SD of 20", "", es, "used", "stability")


# ------------------------------------------------------------------ filter
def match(ta, tb, tol=0.005):
    """For each time in ta: is there a time in tb within tol seconds?"""
    tb = np.sort(np.asarray(tb, float))
    j = np.clip(np.searchsorted(tb, ta), 1, max(tb.size - 1, 1))
    if tb.size == 0:
        return np.zeros(len(ta), bool)
    d = np.minimum(np.abs(ta - tb[j - 1]), np.abs(ta - tb[np.minimum(j, tb.size - 1)]))
    return d <= tol


def run_filter(B):
    """What the stricter event filters remove, per mouse (2026-11-17).
    Halo set (v6) = the loosest border; 10% grace (v7) = a border drawn
    around the control pool, 10% grace; No P-spikes (v8) = v7 less the
    events inside the P-spike border. Events are matched by time (5 ms)."""
    R = {es: {r.lab: r for r in dsdata.load(es) if r.ok} for es in SETS}
    labs = sorted(R["v6"])
    kept, extra, ps, drop_n = {}, {}, {}, {}
    part = {}
    for lab in labs:
        a, b, c = R["v6"][lab], R["v7"].get(lab), R["v8"].get(lab)
        if b is None or a.times_s is None or b.times_s is None:
            continue
        ink = match(a.times_s, b.times_s)
        kept[lab] = float(ink.mean())
        extra[lab] = float((~match(b.times_s, a.times_s)).mean())
        if c is not None and c.times_s is not None:
            ps[lab] = float((~match(b.times_s, c.times_s)).mean())
        drop_n[lab] = float((~ink).sum())
        part[lab] = ink
    B.add("filter", "halo_kept_by_grace_share", kept, "Share of the Halo set's events that the 10% grace border keeps", "share", "v6", "", "filter")
    B.add("filter", "grace_not_in_halo_share", extra, "Share of the 10% grace set's events that are not in the Halo set", "share", "v6", "", "filter")
    B.add("filter", "pspike_removed_share", ps, "Share of the 10% grace set's events removed as P-spikes (No P-spikes set)", "share", "v6", "", "filter")
    B.add("filter", "halo_dropped_count", drop_n, "Number of Halo events outside the 10% grace border", "events", "v6", "", "filter")
    feats = {lab: event_features(R["v6"][lab]) for lab in part}
    for f in FILTER_FEATS:
        dm, km, dd = {}, {}, {}
        for lab, ink in part.items():
            x = feats[lab][f]
            if (~ink).sum() >= MIN_TYPE and ink.sum() >= MIN_TYPE:
                a_, b_ = stat_of(x[~ink], "median"), stat_of(x[ink], "median")
                dm[lab], km[lab], dd[lab] = a_, b_, a_ - b_
        desc = EVENT_FEATURES[f][1]
        B.add("filter", "%s_dropped_median" % f, dm, "%s; median over the Halo events the 10%% grace border drops" % desc, EVENT_FEATURES[f][2], "v6", "", "dropped")
        B.add("filter", "%s_kept_median" % f, km, "%s; median over the Halo events the 10%% grace border keeps" % desc, EVENT_FEATURES[f][2], "v6", "", "kept")
        B.add("filter", "%s_dropped_minus_kept" % f, dd, "%s; dropped minus kept (median of each)" % desc, EVENT_FEATURES[f][2], "v6", "", "dropped_minus_kept")
    # which types the filter drops, under the recording's best classifier
    for nm, fn in (("ds1", lambda r, clf: r.types(clf) == 1), ("ds2", lambda r, clf: r.types(clf) == 2),
                   ("ds3", lambda r, clf: r.ds3(clf) if r.ds3(clf) is not None else None)):
        d_, k_, dd = {}, {}, {}
        for lab, ink in part.items():
            r = R["v6"][lab]
            if not r.used:
                continue
            m = fn(r, r.used)
            if m is None or (~ink).sum() < MIN_TYPE:
                continue
            d_[lab], k_[lab] = float(m[~ink].mean()), float(m[ink].mean())
            dd[lab] = d_[lab] - k_[lab]
        B.add("filter", "%s_share_dropped" % nm, d_, "Share of %s among the Halo events the 10%% grace border drops (best classifier)" % nm.upper(), "share", "v6", "used", "dropped")
        B.add("filter", "%s_share_dropped_minus_kept" % nm, dd, "Share of %s among dropped minus among kept Halo events (best classifier)" % nm.upper(), "share", "v6", "used", "dropped_minus_kept")


# -------------------------------------------------------------------- main
def main(which):
    if "filter" in which:
        run_filter(BATS["filter"])
        BATS["filter"].save()
        print("filter measures %d, tests %d" % BATS["filter"].count(), flush=True)
    which = [f for f in which if f != "filter"]
    for es in SETS:
        recs = [r for r in dsdata.load(es) if r.ok]
        feats = {r.lab: event_features(r) for r in recs}
        masks = {r.lab: masks_of(r) for r in recs}
        for fam in which:
            B = BATS[fam]
            for name, (family, desc, unit, all_stats) in EVENT_FEATURES.items():
                if family == fam:
                    push_event_feature(B, es, recs, feats, masks, family, name, desc, unit, all_stats)
            if fam == "timing":
                run_timing(B, es, recs, feats, masks)
            if fam == "laminar":
                run_laminar(B, es, recs, feats, masks)
            if fam == "structure":
                run_structure(B, es, recs, feats, masks)
            B.save()
            print(es, fam, "measures %d, tests %d" % B.count(), flush=True)


if __name__ == "__main__":
    fams = [a for a in sys.argv[1:]] or ["timing", "waveform", "laminar", "structure"]   # the border "filter" family dropped 2026-11-18
    BATS = {f: Battery(f, outdir=OUTDIR) for f in fams}
    main(fams)
