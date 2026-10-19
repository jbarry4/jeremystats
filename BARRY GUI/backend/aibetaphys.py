"""
aibetaphys.py -- AI Beta's second read: what a dentate spike IS.

The first read (aibeta.read_entry) describes a candidate's shape: its
waveform, its CSD, how far down the shank it reaches. This one describes the
things a person checking a dentate spike knows and a waveform does not say:

    dipole     how many sinks and sources, how wide, how far apart
    latency    whether the peak arrives at every depth at once (a volume-
               conducted artifact) or with a delay down the shank (a current)
    mua        multi-unit firing, 300-3000 Hz off the full 30 kHz signal, at
               the event against the second around it -- at the candidate's
               own peak channel, near it, and far from it
    ripple     120-250 Hz power at the event against the second around it: a
               sharp-wave ripple can pass for a DS
    polarity   whether the voltage reverses above and below the peak channel
    state      delta, theta, beta and gamma in the second before: dentate
               spikes belong to immobile, non-theta states
    motion     how fast the animal was moving, from VT1.nvt
    ttl        how near the nearest Events.nev marker is
    template   how like this recording's typical candidate it is (no labels)
    clipping   saturation, flat tops and steps on the raw 30 kHz signal
    context    what the half second either side looks like: the window study
               of 2026-10-02 found +-500 ms of summary the best of +-25 ms
               to +-1 s

Every per-recording reference -- the typical patch, the baselines, the
usual best row -- is taken over ALL of that recording's candidates, both
labels, so nothing here can see an answer.

NO LAYER SHEET IS USED, anywhere (the user, 2026-10-02). Every depth here is
relative to the candidate's own peak channel, never to a labelled layer. The
first version read StrataScope's sheet for an anatomy input and to pick the
rows unit firing, ripple, state and delay were measured on; that is gone,
and PHYS_VERSION 2 is what keeps its cache from being read.

One read per recording at +-1.1 s around each candidate (the 100 ms the
clock correction searches, plus a second of baseline), merged into spans of
at most eight seconds so a dense set never becomes minutes of 64 channels at
30 kHz in memory at once. Cached; changing which of these a model uses
costs a retrain, not a read.
"""
from __future__ import annotations

import math
import os
import warnings

import numpy as np

from . import braces, continuity, csc, dspca, incisor, nlx

# Loaded on first use, not at start-up; see lazyimp.py for why.
from . import lazyimp  # noqa: E402
_sig = lazyimp.module("scipy.signal")

PHYS_VERSION = 3

SEARCH_MS = 100.0
BASE_MS = 1000.0
REACH_MS = SEARCH_MS + BASE_MS
BLOCK_MS = 150.0          # per-channel block kept per event
CTX_MS = 500.0            # the context window the window study chose
CTX_KEEP_MS = CTX_MS + SEARCH_MS
PEAK_MS = 10.0
PAD_S = 0.35
MAX_SPAN_S = 8.0
MUA_BAND = (300.0, 3000.0)
RIPPLE_BAND = (120.0, 250.0)

# BRACES' RULE, for every candidate (the user, 2026-10-02: "align all, keep
# both"). Braces' own numbers, read from Braces so the two cannot drift:
# the window a stamp may move in, the spacing two candidate peaks may have,
# the depth band the CSD is averaged over, and what counts as a move to the
# edge, an unusual move, or no move at all. Braces itself refuses to align
# Garbage, because a garbage stamp beside a real spike would take that
# spike's peak; here nobody knows yet which is which, so every candidate
# goes through the rule, and HOW it went through -- no peak, a move to the
# edge, a peak another stamp took -- is itself an input.
ALIGN_WINDOW_MS = braces.WINDOW_MS
ALIGN_DIST_MS = braces.CAND_DIST_MS
ALIGN_DEPTH = braces.DEPTH_BAND
ALIGN_EDGE = braces.EDGE_FRAC
ALIGN_OUTLIER_MADS = braces.OUTLIER_MADS
ALIGN_OUTLIER_FLOOR_MS = braces.OUTLIER_FLOOR_MS
ALIGN_SAME_MS = braces.SAME_MS
# The window measured at the aligned peak. A dentate spike is 10-20 ms
# wide, so +-15 ms is the event and almost nothing else.
AL_MS = 15.0

# THE WAVEFORM AS A PICTURE, at the peak Braces' rule put each candidate on
# (the user, 2026-10-07: "in addition to the braces algorithm which adds the
# center aligned data, try including an image of the wave form. Try out a
# range of 3-50ms"). The 5-100 Hz voltage, depth against time: 8 contacts
# either side of the candidate's own peak channel (400 um on an H3; the
# same depth on every other contact), +-W ms either side of the aligned
# peak, scaled so the peak is 1 and its sign kept. Each window is its own
# input, so a run picks one; every picture is 17 depths by 13 times,
# whatever the window, so a wide one is coarser in time, not bigger.
IMG_WINDOWS_MS = (3, 5, 10, 15, 25, 50)
IMG_ROWS = 17
IMG_COLS = 13
IMG_IDS = tuple("wimg%d" % w for w in IMG_WINDOWS_MS)

# THE SAME SNAPSHOTS THROUGH OTHER FILTERS (the user, 2026-10-07: "are the
# CSD images filtered? try adding a variety of filters to the whole
# snapshot and the thinner snapshot ... also add a variety of filtered
# data"). Everything above is the 5-100 Hz band Incisor detects in, after
# Braces' mains notch. Each filter here is applied to the notched 1 kHz
# signal over the whole stretch read -- never to the short block kept per
# candidate, which is too short for a 1 Hz edge -- and then three things are
# taken at the aligned peak:
#   fwhole   the whole shank's CSD, +-50 ms (the "whole snapshot")
#   fthin    the voltage 8 contacts either side of the peak channel,
#            +-25 ms (the "thinner snapshot", the best window above)
#   ftrace   the peak channel's voltage, +-50 ms at 2 ms (filtered data)
# Each picture is scaled so its largest value is 1, sign kept. "notch" is
# the notch alone, with each row's mean over the block taken off.
FILTERS = (("notch", None), ("1_20", (1.0, 20.0)), ("1_100", (1.0, 100.0)),
           ("5_50", (5.0, 50.0)), ("10_40", (10.0, 40.0)),
           ("5_100", (5.0, 100.0)))
SNAPS = (("fwhole", "Whole shank CSD, +-50 ms"),
         ("fthin", "Voltage, 8 contacts either side, +-25 ms"),
         ("ftrace", "Peak channel trace, +-50 ms"))
FILT_IDS = tuple("%s_%s" % (s, f) for s, _n in SNAPS for f, _b in FILTERS)
THIN_MS = 25
TRACE_MS = 50
TRACE_STEP_MS = 2
# Bumped when the pictures change, so a read holding older ones is read
# again for them -- the rest of the second read is unaffected. 2: a wide
# window averages each column's span instead of sampling one point of it,
# which at +-50 ms showed a 20 ms spike as a single column. 3: the
# filtered snapshots.
IMG_VERSION = 3


# X-RAY'S WAY OF LOOKING, AT EVERY PEAK NEAR THE STAMP (the user,
# 2026-10-07: "see the logic that X-ray uses ... the average CSD wave ...
# get the CSD snippet from the top 5 peaks if there are that many peaks,
# usually there is just 1 or 2 ... plus anything else that helped make
# snippets more powerful"). What helped was the 10-40 Hz band, so all of
# this is on the 10-40 Hz signal:
#   the depth band   X-ray's rule (`dspca.depth_band`): the contacts that
#                    MOVE most in this recording's candidate-triggered
#                    average, against its own edges -- label-free, no layer
#                    sheet. 16 contacts deep, the same depth on every other.
#   the CSD          Toothy's, computed within that band (`toothy_csd`).
#   the peaks        |CSD| averaged over the band, local maxima at least
#                    Braces' 12 ms apart within Braces' +-100 ms of the
#                    clock-corrected stamp; the five largest, largest first.
# At each peak, and first at the peak Braces' rule assigned:
#   when it is, from the stamp (ms), and how tall against the tallest;
#   the depth profile over +-5 ms, min-max scaled as X-ray scales it, at 12
#   depths; the CSD wave -- the band's mean CSD over +-25 ms -- at 13
#   times, scaled to 1; and X-ray's delta, how far apart its two largest
#   sinks are (`dspca.two_sinks`), 0 to 1 across the band.
# A peak that is not there leaves its numbers empty.
XR_SLOTS = ("al", "p1", "p2", "p3", "p4", "p5")
XR_PROFILE_ROWS = 12
XR_WAVE_COLS = 13
XR_BOX_MS = 5
XR_WAVE_MS = 25
XR_SINK_SEP_UM = 150.0       # X-ray's 5 contacts at the H10-D's 30 um
XR_FILTER = "10_40"
XR_IDS = ("xray5",)
# Which peaks are real (`_peaks`): found on Braces' own trace -- the 5-100
# Hz |CSD| over Braces' band, the trace it aligns on -- not on the 10-40 Hz
# one, whose band-pass rings after every spike and turns one event into a
# train of peaks 25 ms apart.
XR_PEAK_Z = 3.0
XR_PEAK_REL = 0.25
# Bumped when the X-ray snippets change, as IMG_VERSION is for the
# pictures. 2: peaks on Braces' trace, with the rule for which are real.
XR_VERSION = 2


def _xr_names():
    out = []
    for s in XR_SLOTS:
        out += ["xr_%s_dt_ms" % s, "xr_%s_height" % s]
        out += ["xr_%s_prof%02d" % (s, k) for k in range(XR_PROFILE_ROWS)]
        out += ["xr_%s_wave%02d" % (s, k) for k in range(XR_WAVE_COLS)]
        out += ["xr_%s_delta" % s]
    return out


def filters_for(fams):
    """Which filters the snapshot inputs among `fams` need."""
    out = {f.split("_", 1)[1] for f in fams if f in FILT_IDS}
    if any(f in XR_IDS for f in fams):
        out.add(XR_FILTER)
    return out


def _filter_label(fid):
    band = dict(FILTERS)[fid]
    return "notch only" if band is None else "%g-%g Hz" % band


FAMILIES = [
    {"id": "context500", "name": "Context, +-500 ms",
     "blurb": "What the half second either side of the candidate looks like: "
              "noise on every wire, other big CSD events, broadband bursts."},
    {"id": "dipole", "name": "Sink and source",
     "blurb": "How many sinks and sources down the shank, how wide, how far "
              "apart and how balanced."},
    {"id": "latency", "name": "Laminar delay",
     "blurb": "Whether the peak reaches every depth at once, as something "
              "conducted from elsewhere does, or with a delay down the "
              "shank, as a current does."},
    {"id": "mua", "name": "Unit firing",
     "blurb": "Multi-unit activity (300-3000 Hz, full rate) at the event "
              "against the second around it: on its own peak channel, near "
              "it, and far from it."},
    {"id": "ripple", "name": "Ripple",
     "blurb": "120-250 Hz power at the event against the second around "
              "it: a sharp-wave ripple can pass for a dentate spike."},
    {"id": "state", "name": "Brain state",
     "blurb": "Delta, theta, beta and gamma in the second before."},
    {"id": "motion", "name": "Movement",
     "blurb": "How fast the animal was moving, from the video tracking."},
    {"id": "ttl", "name": "Event markers",
     "blurb": "How near the nearest marker in Events.nev is."},
    {"id": "template", "name": "Like the others",
     "blurb": "How closely it matches this recording's typical candidate, "
              "and where its size ranks among them."},
    {"id": "clipping", "name": "Saturation",
     "blurb": "Flat tops, steps and out-of-range values on the raw 30 kHz "
              "signal."},
    {"id": "polarity", "name": "Polarity reversal",
     "blurb": "The voltage at the peak above and below its own peak "
              "channel, signed, and how far away it changes sign."},
    {"id": "braces", "name": "Braces alignment",
     "blurb": "How the candidate went through Braces' rule: whether it "
              "found a peak, how far it moved, whether it hit the edge of "
              "the window, whether the move was unusual for this recording, "
              "and whether the nearest peak went to another stamp."},
    {"id": "aligned15", "name": "+-15 ms at the aligned peak",
     "blurb": "The event itself, re-measured in the 30 ms around the peak "
              "Braces put it on: its shape and sharpness, unit firing, "
              "polarity, sink and source, laminar delay and likeness."},
    {"id": "shape", "name": "Spike shape",
     "blurb": "Rise and decay times, ringing, zero crossings and where its "
              "power sits in frequency."},
] + [
    {"id": "wimg%d" % w, "name": "Waveform image, +-%d ms" % w,
     "group": "pictures",
     "blurb": "The voltage as a picture at the peak Braces' rule found: "
              "8 contacts either side of the candidate's own peak channel, "
              "%d ms either side in time, 17 by 13." % w}
    for w in IMG_WINDOWS_MS
] + [
    {"id": "%s_%s" % (s, f), "name": "%s, %s" % (n, _filter_label(f)),
     "group": "pictures",
     "blurb": "%s at the peak Braces' rule found, through %s." % (
         n, _filter_label(f))}
    for s, n in SNAPS for f, _b in FILTERS
] + [
    {"id": "xray5", "name": "X-ray at the top five peaks, 10-40 Hz",
     "group": "pictures",
     "blurb": "X-ray's depth band, CSD, depth profile, CSD wave and sink "
              "gap, at the peak Braces' rule assigned and at each of the "
              "five largest CSD peaks within 100 ms of the stamp."}
]

NAMES = {
    "context500": ["c500_hf_mean", "c500_hf_max", "c500_cm_max",
                   "c500_spread_mean", "c500_core_ratio", "c500_n_peaks",
                   "c500_csd_mean", "c500_other_max"],
    "dipole": ["n_pos", "n_neg", "main_width", "pos_neg_dist",
               "neg_pos_ratio"],
    "latency": ["lat_std_ms", "lat_range_ms", "lat_slope_ms_per_row",
                "lat_same_frac"],
    "mua": ["mua_peak_ch", "mua_near", "mua_far", "mua_max", "mua_median"],
    "ripple": ["rip_max", "rip_median", "rip_peak_ch"],
    "state": ["log_delta", "log_theta", "log_beta", "log_gamma",
              "theta_over_delta"],
    "motion": ["log_speed_1s", "log_speed_4s", "tracked_frac", "speed_rank"],
    "ttl": ["log_s_to_marker", "markers_within_1s"],
    "template": ["patch_vs_typical", "trace_vs_typical", "amp_rank",
                 "csd_rank"],
    "clipping": ["raw_max_sd", "raw_step_sd", "flat_frac", "frac_ch_over_20sd"],
    "polarity": ["v_above", "v_below", "opposite", "reversal_rows"],
    "braces": ["al_found", "al_move_ms", "al_move_frac", "al_edge",
               "al_outlier", "al_same", "al_peak_rel", "al_n_peaks",
               "al_nearest_ms", "al_nearest_taken"],
    "aligned15": (["a15_wave_%+d" % k for k in range(-14, 16, 2)]
                  + ["a15_csd_%+d" % k for k in range(-14, 16, 2)]
                  + ["a15_sharpness", "a15_half_width_ms",
                     "a15_mua_peak_ch", "a15_mua_near", "a15_mua_far",
                     "a15_mua_max", "a15_mua_median",
                     "a15_v_above", "a15_v_below", "a15_opposite",
                     "a15_reversal_rows",
                     "a15_n_pos", "a15_n_neg", "a15_main_width",
                     "a15_pos_neg_dist", "a15_neg_pos_ratio",
                     "a15_lat_std_ms", "a15_lat_slope",
                     "a15_patch_vs_typical", "a15_trace_vs_typical",
                     "a15_concentration"]),
    "shape": ["rise_ms", "decay_ms", "zero_crossings", "ringing",
              "centroid_hz", "low_over_high"],
}
NAMES.update({
    "wimg%d" % w: ["wi%02d_r%+d_t%02d" % (w, r - IMG_ROWS // 2, t)
                   for r in range(IMG_ROWS) for t in range(IMG_COLS)]
    for w in IMG_WINDOWS_MS})
NAMES["xray5"] = _xr_names()
for _f, _b in FILTERS:
    NAMES["fwhole_" + _f] = ["fw_%s_d%02d_t%02d" % (_f, r, t)
                             for r in range(IMG_ROWS) for t in range(IMG_COLS)]
    NAMES["fthin_" + _f] = ["ft_%s_r%+d_t%02d" % (_f, r - IMG_ROWS // 2, t)
                            for r in range(IMG_ROWS) for t in range(IMG_COLS)]
    NAMES["ftrace_" + _f] = ["fr_%s_%+d" % (_f, k)
                             for k in range(-TRACE_MS, TRACE_MS + 1,
                                            TRACE_STEP_MS)]
FAMILY_IDS = [f["id"] for f in FAMILIES]


def spans(times, reach_s, pad_s, merge_gap=1.0, max_span=MAX_SPAN_S):
    """`braces.spans`, capped at `max_span` seconds, with members listed."""
    order = sorted(range(len(times)), key=lambda i: times[i])
    out = []
    for i in order:
        t = times[i]
        lo, hi = t - reach_s - pad_s, t + reach_s + pad_s
        if out and lo - out[-1][1] <= merge_gap and \
                hi - out[-1][0] <= max_span:
            out[-1][1] = max(out[-1][1], hi)
            out[-1][2].append(i)
        else:
            out.append([max(0.0, lo), hi, [i]])
    return out



def _speed_at(nvt, abs_us, half_s):
    """Path length over time in a window, from the video, in px/s."""
    t, x, y, start_us = nvt
    if t is None or t.size < 3:
        return np.nan, np.nan
    rel = (abs_us - start_us) / 1e6
    lo, hi = np.searchsorted(t, [rel - half_s, rel + half_s])
    if hi - lo < 3:
        return np.nan, 0.0
    xs, ys, ts = x[lo:hi], y[lo:hi], t[lo:hi]
    good = np.isfinite(xs) & np.isfinite(ys)
    frac = float(good.mean())
    if good.sum() < 3:
        return np.nan, frac
    xs, ys, ts = xs[good], ys[good], ts[good]
    d = np.hypot(np.diff(xs), np.diff(ys))
    dur = float(ts[-1] - ts[0])
    return (float(d.sum()) / dur if dur > 0 else np.nan), frac


def _band_power(x, fs, bands):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, p = _sig.welch(x, fs=fs, nperseg=min(512, x.size))
    out = []
    for lo, hi in bands:
        sel = (f >= lo) & (f < hi)
        out.append(float(np.trapezoid(p[sel], f[sel])) if sel.any()
                   else np.nan)
    return out


def _row_windows(scale):
    """The windows counted in rows, for rows `1/scale` contacts apart.

    At scale 1 -- every contact -- these are the numbers the read has always
    used: 4 rows either side is "near", more than 12 is "far", the laminar
    delay is taken over 10 either side and Braces' band is 16 deep. Every
    other contact is scale 0.5, and the same depths are half the rows.
    """
    def r(n, lo=1):
        return max(lo, int(round(n * scale)))
    return {"near": r(4), "far": r(12), "lat": r(10),
            "depth": r(ALIGN_DEPTH, 3), "img": r(8)}


def _wave_image(blk, r, a, half, span):
    """`blk` rows r-span..r+span, samples a-half..a+half, as 17 by 13.

    Rows past either end of the probe repeat the last one; the picture is
    resampled to the same size whatever the window, linearly.
    """
    nr, w = blk.shape
    rows = np.clip(r + np.arange(-span, span + 1), 0, nr - 1)
    return _picture(blk[rows], a, half)


def _picture(sub, a, half):
    """Rows of `sub`, samples a-half..a+half, as IMG_ROWS by IMG_COLS."""
    w = sub.shape[1]
    if 2 * half + 1 > IMG_COLS:
        # Wider than the picture: each column is the mean of its own span
        # of samples, so nothing between two columns is skipped.
        edges = np.linspace(a - half, a + half + 1, IMG_COLS + 1)
        edges = np.clip(np.round(edges).astype(int), 0, w)
        img = np.stack([sub[:, e0:max(e1, e0 + 1)].mean(axis=1)
                        for e0, e1 in zip(edges[:-1], edges[1:])], axis=1)
    else:
        tt = np.clip(np.linspace(a - half, a + half, IMG_COLS), 0, w - 1)
        x = np.arange(w)
        img = np.stack([np.interp(tt, x, sub[q])
                        for q in range(sub.shape[0])])
    if img.shape[0] != IMG_ROWS:
        src = np.arange(img.shape[0])
        dst = np.linspace(0, img.shape[0] - 1, IMG_ROWS)
        img = np.stack([np.interp(dst, src, img[:, k])
                        for k in range(IMG_COLS)], axis=1)
    return img


def read_physio(session, channels, probe, bad, times,
                report=None, folder=None, job=None, on_span=None,
                aibeta=None, workers=1, spacing=None, want_filt=(),
                want_xray=False):
    """The second read. Returns {"fam": {id: array}, "ok": bool array}.

    `spacing` is the distance between neighbouring rows of `channels` when
    that is not the probe's own pitch -- every other contact, say. The
    windows counted in rows are scaled by it (`_row_windows`), so they
    cover the same depth whichever contacts are read.

    `want_filt` is which filters' snapshots to take (`filters_for`), or
    True for all of them. Only those are filtered, and only their inputs
    are returned: a sweep with Tooth Fairy needs one filter, not six.
    """
    want_filt = ({f for f, _b in FILTERS} if want_filt is True
                 else set(want_filt or ()))
    AI = aibeta
    p = dspca.Params(probe=probe, invert=True, bad=sorted(int(b)
                                                         for b in bad or []))
    p.spacing = float(spacing) if spacing else dspca.spacing_for(p.probe)
    RW = _row_windows(dspca.spacing_for(p.probe) / p.spacing)
    spec = p.spec()
    badd = {int(b): "marked" for b in (bad or [])}
    geo, _ = dspca.geometry(p.probe, channels)
    run = max(geo, key=lambda r: len(r["rows"]))
    rows = run["rows"]
    nr = len(rows)

    t0_us = int((report or {}).get("t0_us") or 0)
    nvt = (None, None, None, 0.0)
    nev_us = np.empty(0)
    if folder:
        try:
            path = os.path.join(folder, "VT1.nvt")
            if os.path.exists(path):
                t, x, y, _ang, meta = nlx.read_nvt(path)
                nvt = (t, x, y, float(meta.get("t_start_us") or 0.0))
        except Exception:                                # noqa: BLE001
            pass
        try:
            path = os.path.join(folder, "Events.nev")
            if os.path.exists(path):
                recs, _m = nlx.read_nev(path)
                keep = []
                for r in recs:
                    s = r["event_string"].split(b"\x00", 1)[0].decode(
                        "latin-1", "replace")
                    if any(w in s for w in ("Recording", "Starting",
                                            "Stopping")):
                        continue
                    keep.append(float(r["timestamp"]))
                nev_us = np.array(sorted(keep))
        except Exception:                                # noqa: BLE001
            pass

    idx = [i for i, t in enumerate(times) if t is not None]
    n_all = len(times)
    sp = spans([times[i] for i in idx], REACH_MS / 1000.0, PAD_S)
    store = {}
    fs_box = [None]
    count = [0]

    def one(k):
        a, b, members = sp[k]
        out_ = {}
        if job:
            job.check()
        raws, anchor, ch_fs = [], None, None
        for ch in channels:
            raw, got_t0, f_ = csc._read_channel_window(session, ch, a, b)
            if raw.size < 64:
                raws = None
                break
            if anchor is None:
                anchor, ch_fs = got_t0, f_
            raws.append(np.asarray(raw, dtype=np.float64))
        count[0] += 1
        if on_span:
            on_span(count[0], len(sp))
        if not raws:
            return out_
        keep = min(r.size for r in raws)
        X = np.vstack([r[:keep] for r in raws])
        del raws
        q = incisor.decimation_for(ch_fs, p.lfp_fs)
        fs = ch_fs / q
        fs_box[0] = fs
        # Multi-unit envelope at full rate, then averaged down to 1 kHz.
        sos = _sig.butter(3, [MUA_BAND[0], min(MUA_BAND[1], ch_fs * 0.45)],
                          btype="band", fs=ch_fs, output="sos")
        mu = np.abs(_sig.sosfiltfilt(sos, X, axis=-1))
        nb = mu.shape[1] // q
        mua = mu[:, :nb * q].reshape(mu.shape[0], nb, q).mean(axis=2)
        del mu
        # Raw yardsticks for saturation and steps, per channel -- over the
        # contacts nobody marked bad, or one dead wire is the loudest thing
        # on every candidate in the recording.
        dX = np.diff(X, axis=1)
        good = np.array([int(c["number"]) not in badd for c in channels])
        if not good.any():
            good[:] = True
        raw_sd = np.median(np.abs(X - np.median(X, axis=1, keepdims=True)),
                           axis=1) / 0.6745 + 1e-9
        step_sd = np.median(np.abs(dX), axis=1) / 0.6745 + 1e-9
        x = X
        for step in incisor._factor(q):
            x = _sig.decimate(x, step, ftype="iir", zero_phase=True, axis=-1)
        clean = braces._notch(x, fs, spec)
        band = incisor._filtered(clean, fs, spec.get("band") or incisor.DS_BAND)
        sos_r = _sig.butter(3, [RIPPLE_BAND[0] / (fs / 2),
                                min(RIPPLE_BAND[1], fs * 0.45) / (fs / 2)],
                            btype="band", output="sos")
        rip = np.abs(_sig.sosfiltfilt(sos_r, clean, axis=-1))
        n1 = min(band.shape[1], mua.shape[1], rip.shape[1])
        band, clean, mua, rip = (band[:, :n1], clean[:, :n1], mua[:, :n1],
                                 rip[:, :n1])
        # The other filters, over the whole stretch, before anything is
        # cut to a candidate.
        filt = {}
        if want_filt:
            for fid, fb in FILTERS:
                if fid == "5_100" or fid not in want_filt:
                    continue
                y = clean if fb is None else incisor._filtered(clean, fs, fb)
                filt[fid] = braces.repair(y, channels, badd)[rows]
        band = braces.repair(band, channels, badd)[rows]
        clean = braces.repair(clean, channels, badd)[rows]
        mua = braces.repair(mua, channels, badd)[rows]
        rip = braces.repair(rip, channels, badd)[rows]
        cs = braces.csd_of(band, spec)
        A = np.abs(cs).mean(axis=0)
        hf = np.abs(clean - band).mean(axis=0)
        cm = band.mean(axis=0)
        spr = band.std(axis=0)
        R = int(round(REACH_MS / 1000.0 * fs))
        Bk = int(round(BLOCK_MS / 1000.0 * fs))
        Ck = int(round(CTX_KEEP_MS / 1000.0 * fs))
        S = int(round(SEARCH_MS / 1000.0 * fs))
        excl = int(round(50 / 1000.0 * fs))
        state_row = list(range(nr))
        for m in members:
            i = idx[m]
            i0 = int(round((times[i] - anchor) * fs))
            if i0 - R < 0 or i0 + R + 1 > n1:
                continue
            base = np.r_[i0 - R:i0 - excl, i0 + excl:i0 + R]
            best = int(np.argmax(band[:, i0 - S:i0 + S + 1].max(axis=1)))
            pre = clean[state_row, i0 - int(fs):i0].mean(axis=0)
            pw = _band_power(pre, fs, ((1, 4), (6, 10), (15, 30), (30, 80)))
            # Raw, +-60 ms around the stamp, at full rate.
            j0 = int(round((times[i] - anchor) * ch_fs))
            h = int(round(0.06 * ch_fs))
            seg = X[:, max(0, j0 - h):j0 + h]
            dseg = dX[:, max(0, j0 - h):j0 + h - 1]
            zmax = (np.max(np.abs(seg - np.median(seg, axis=1,
                                                  keepdims=True)), axis=1)
                    / raw_sd)[good]
            steps = (np.abs(dseg).max(axis=1) / step_sd)[good] \
                if dseg.shape[1] else np.full(1, np.nan)
            out_[i] = {
                "band": band[:, i0 - Bk:i0 + Bk + 1].astype(np.float32),
                "mua": mua[:, i0 - Bk:i0 + Bk + 1].astype(np.float32),
                "rip": rip[:, i0 - Bk:i0 + Bk + 1].astype(np.float32),
                "mua_base": np.median(mua[:, base], axis=1).astype(np.float32),
                "rip_base": np.median(rip[:, base], axis=1).astype(np.float32),
                "ctx": np.stack([band[best, i0 - Ck:i0 + Ck + 1],
                                 A[i0 - Ck:i0 + Ck + 1],
                                 hf[i0 - Ck:i0 + Ck + 1],
                                 cm[i0 - Ck:i0 + Ck + 1],
                                 spr[i0 - Ck:i0 + Ck + 1]]).astype(np.float32),
                "state": pw,
                "filt": {fid: v[:, i0 - Bk:i0 + Bk + 1].astype(np.float32)
                         for fid, v in filt.items()},
                "clip": [float(zmax.max()), float(np.max(steps)),
                         float((dseg[good] == 0).mean()) if dseg.shape[1]
                         else np.nan,
                         float((zmax > 20).mean())],
            }
        del X, dX, x, clean, band, mua, rip, filt
        return out_

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for part in pool.map(one, range(len(sp))):
                store.update(part)
    else:
        for k in range(len(sp)):
            store.update(one(k))
    fs = fs_box[0]

    have = sorted(store)
    fam = {k: np.full((n_all, len(NAMES[k])), np.nan, dtype=np.float32)
           for k in FAMILY_IDS}
    ok = np.zeros(n_all, dtype=bool)
    if not have:
        return {"fam": fam, "ok": ok, "missed": n_all}

    Bk = (store[have[0]]["band"].shape[1] - 1) // 2
    Ck = (store[have[0]]["ctx"].shape[1] - 1) // 2
    S = int(round(SEARCH_MS / 1000.0 * fs))
    P = int(round(PEAK_MS / 1000.0 * fs))
    H = int(round(50 / 1000.0 * fs))
    W = int(round(CTX_MS / 1000.0 * fs))

    # The clock, per recording, exactly as the first read takes it.
    t_ms = np.arange(-S, S + 1) / fs * 1000.0
    off = np.full(len(have), np.nan)
    for j, i in enumerate(have):
        tr = store[i]["ctx"][1, Ck - S:Ck + S + 1]
        if np.all(np.isfinite(tr)):
            off[j] = t_ms[dspca.pick_peak(tr, t_ms, "nearest")]
    corr, _trusted = AI._running_median(off)
    shift = np.clip(np.round(corr / 1000.0 * fs).astype(int), -S, S)

    # References over every candidate.
    allb = np.concatenate([store[i]["band"] for i in have], axis=1)
    sd_b = np.median(np.abs(allb - np.median(allb, axis=1, keepdims=True)),
                     axis=1) / 0.6745 + 1e-9
    del allb
    ctx_all = np.stack([store[i]["ctx"] for i in have])
    a_scale = float(np.median(ctx_all[:, 1])) or 1.0
    hf_scale = float(np.median(ctx_all[:, 2])) or 1.0
    cm_scale = float(np.median(np.abs(ctx_all[:, 3]))) or 1.0
    sp_scale = float(np.median(ctx_all[:, 4])) or 1.0
    del ctx_all

    first = []
    for j, i in enumerate(have):
        c = Bk + shift[j]
        blk = store[i]["band"]
        z = blk[:, c - P:c + P + 1].max(axis=1) / sd_b
        r = int(np.nanargmax(z))
        pk = c - P + int(np.argmax(blk[r, c - P:c + P + 1]))
        patch = braces.csd_of(blk[:, c - H:c + H + 1].astype(np.float64),
                              spec)
        first.append((r, pk, patch))
    usual_r = int(np.bincount([f[0] for f in first]).argmax())
    typical_patch = np.median(np.stack([f[2] for f in first]), axis=0)
    typical_trace = np.median(np.stack(
        [store[i]["band"][usual_r, Bk + shift[j] - H:Bk + shift[j] + H + 1]
         for j, i in enumerate(have)]), axis=0)
    amps = np.array([store[i]["band"][f[0], f[1]] for i, f in zip(have, first)])
    csdpk = np.array([np.abs(f[2]).mean(axis=0).max() for f in first])

    def rank(v, allv):
        return float((allv < v).mean())

    def corr2(a, b):
        a = np.asarray(a, float).ravel()
        b = np.asarray(b, float).ravel()
        if a.std() == 0 or b.std() == 0:
            return np.nan
        return float(np.corrcoef(a, b)[0, 1])

    speeds = []
    for j, i in enumerate(have):
        st = store[i]
        c = Bk + shift[j]
        r, pk, patch = first[j]
        blk = st["band"].astype(np.float64)
        prof = blk[:, pk]
        col = patch[:, H + (pk - c)] if 0 <= H + (pk - c) < patch.shape[1] \
            else patch[:, H]
        kpos, kneg = int(np.argmax(col)), int(np.argmin(col))
        vmax = float(np.abs(prof).max()) + 1e-9

        cn = col / (float(np.abs(col).max()) + 1e-9)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp, _ = _sig.find_peaks(cn, prominence=0.3)
            nn, _ = _sig.find_peaks(-cn, prominence=0.3)
        main = kpos if abs(col[kpos]) >= abs(col[kneg]) else kneg
        half = abs(cn[main]) / 2.0
        sgn = np.sign(cn[main])
        w = 0
        for d in (1, -1):
            k = main
            while 0 <= k < cn.size and sgn * cn[k] >= half:
                w += 1
                k += d
        fam["dipole"][i] = [pp.size, nn.size, max(0, w - 1),
                            abs(kpos - kneg) / float(max(1, col.size)),
                            abs(col[kneg]) / (abs(col[kpos]) + 1e-9)]

        lat_rows = list(range(max(0, r - RW["lat"]),
                             min(nr, r + RW["lat"] + 1)))
        lw = int(round(15 / 1000.0 * fs))
        seg = np.abs(blk[lat_rows, c - lw:c + lw + 1])
        lat = (np.argmax(seg, axis=1) - lw) / fs * 1000.0
        if len(lat_rows) >= 3:
            slope = float(np.polyfit(np.arange(len(lat_rows)), lat, 1)[0])
        else:
            slope = np.nan
        same = float(np.mean(np.abs(lat - lat[np.argmax(seg.max(axis=1))])
                             <= 1000.0 / fs))
        fam["latency"][i] = [float(np.std(lat)), float(np.ptp(lat)), slope,
                             same]

        ev = slice(c - P, c + P + 1)
        m_ratio = np.log((st["mua"][:, ev].mean(axis=1) + 1e-9)
                         / (st["mua_base"] + 1e-9))
        near = slice(max(0, r - RW["near"]), min(nr, r + RW["near"] + 1))
        far = [k for k in range(nr) if abs(k - r) > RW["far"]]
        fam["mua"][i] = [float(m_ratio[r]), float(m_ratio[near].mean()),
                         float(m_ratio[far].mean()) if far else np.nan,
                         float(m_ratio.max()), float(np.median(m_ratio))]
        rw = slice(c - int(round(15 / 1000.0 * fs)),
                   c + int(round(15 / 1000.0 * fs)) + 1)
        r_ratio = np.log((st["rip"][:, rw].mean(axis=1) + 1e-9)
                         / (st["rip_base"] + 1e-9))
        fam["ripple"][i] = [float(r_ratio.max()), float(np.median(r_ratio)),
                            float(r_ratio[r])]

        d_, th, be, ga = st["state"]
        fam["state"][i] = [math.log10(d_ + 1e-12), math.log10(th + 1e-12),
                           math.log10(be + 1e-12), math.log10(ga + 1e-12),
                           th / (d_ + 1e-12)]

        abs_us = t0_us + times[i] * 1e6
        s1, frac = _speed_at(nvt, abs_us, 0.5)
        s4, _f = _speed_at(nvt, abs_us, 2.0)
        speeds.append(s1)
        fam["motion"][i] = [math.log10(s1 + 1.0) if np.isfinite(s1)
                            else np.nan,
                            math.log10(s4 + 1.0) if np.isfinite(s4)
                            else np.nan, frac, np.nan]

        if nev_us.size:
            k = np.searchsorted(nev_us, abs_us)
            near = [abs(nev_us[q] - abs_us) for q in (k - 1, k)
                    if 0 <= q < nev_us.size]
            dt = min(near) / 1e6
            n1s = int(np.sum(np.abs(nev_us - abs_us) <= 1e6))
            fam["ttl"][i] = [math.log10(max(dt, 1e-3)), n1s]
        else:
            fam["ttl"][i] = [np.nan, 0]

        trace = blk[usual_r, c - H:c + H + 1]
        fam["template"][i] = [corr2(patch, typical_patch),
                              corr2(trace, typical_trace),
                              rank(amps[j], amps), rank(csdpk[j], csdpk)]
        fam["clipping"][i] = st["clip"]

        above = prof[:max(0, r - RW["near"])]
        below = prof[r + RW["near"] + 1:]
        va = float(above.mean()) / vmax if above.size else np.nan
        vb = float(below.mean()) / vmax if below.size else np.nan
        sg = np.sign(prof[r])
        flips = [abs(k - r) for k in range(nr) if np.sign(prof[k]) != sg]
        fam["polarity"][i] = [va, vb,
                              float(np.sign(va) != np.sign(vb))
                              if np.isfinite(va) and np.isfinite(vb)
                              else np.nan,
                              (min(flips) / float(nr)) if flips else np.nan]

        tr = blk[r]
        amp_r = float(tr[pk]) or 1e-9
        k = pk
        lim = max(0, pk - H)
        while k > lim and tr[k] > 0.9 * amp_r:
            k -= 1
        k90 = k
        while k > lim and tr[k] > 0.1 * amp_r:
            k -= 1
        rise = (k90 - k) / fs * 1000.0
        k = pk
        lim2 = min(tr.size - 1, pk + H)
        while k < lim2 and tr[k] > 0.1 * amp_r:
            k += 1
        decay = (k - pk) / fs * 1000.0
        win_ = tr[c - H:c + H + 1]
        zc = int(np.sum(np.diff(np.sign(win_)) != 0))
        far = np.ones(win_.size, bool)
        q15 = int(round(15 / 1000.0 * fs))
        far[max(0, (pk - (c - H)) - q15):(pk - (c - H)) + q15 + 1] = False
        ring = float(np.abs(win_[far]).max()) / abs(amp_r) if far.any()             else np.nan
        spec_ = np.abs(np.fft.rfft(win_ - win_.mean())) ** 2
        fr = np.fft.rfftfreq(win_.size, 1.0 / fs)
        cen = float((fr * spec_).sum() / (spec_.sum() + 1e-12))
        lo_ = float(spec_[(fr >= 5) & (fr < 20)].sum())
        hi_ = float(spec_[(fr >= 20) & (fr < 100)].sum()) + 1e-12
        fam["shape"][i] = [rise, decay, zc, ring, cen, lo_ / hi_]

        cc = Ck + shift[j]
        bt, Aw, hf, cm, spr = st["ctx"].astype(np.float64)
        lo, hi = cc - W, cc + W + 1
        aw = Aw[lo:hi]
        z = int(round(20 / 1000.0 * fs))
        ex = np.ones(hi - lo, bool)
        ex[max(0, cc - lo - z):cc - lo + z + 1] = False
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pk_, _ = _sig.find_peaks(aw, height=3 * a_scale, distance=max(1, z))
        amp = abs(float(bt[cc - P:cc + P + 1].max())) + 1e-9
        bw = np.abs(bt[lo:hi])
        fam["context500"][i] = [
            float(hf[lo:hi].mean()) / hf_scale,
            float(hf[lo:hi].max()) / hf_scale,
            float(np.abs(cm[lo:hi]).max()) / cm_scale,
            float(spr[lo:hi].mean()) / sp_scale,
            float(Aw[cc - P:cc + P + 1].mean()) / (float(aw.mean()) + 1e-9),
            int(np.sum(ex[pk_])) if pk_.size else 0,
            float(aw.mean()) / a_scale,
            float(bw[ex].max()) / amp if ex.any() else 0.0]
        ok[i] = True

    aligned, btraces = _align(store, have, first, shift, times, fs, Bk, P,
                              nr, spec, fam, RW, want_filt) or (None, None)
    if want_xray and aligned:
        _xray(store, have, shift, aligned, btraces, fs, Bk, spec, RW, fam,
              p.spacing)

    sp_arr = np.array(speeds, float)
    fin = sp_arr[np.isfinite(sp_arr)]
    for j, i in enumerate(have):
        if np.isfinite(sp_arr[j]) and fin.size:
            fam["motion"][i, 3] = float((fin < sp_arr[j]).mean())
    for k in fam:
        fam[k][~np.isfinite(fam[k])] = np.nan
    # The snapshots not taken are left out rather than left empty: a cached
    # read holding them all-NaN would be taken by a later run as read.
    for k in FILT_IDS:
        if k.split("_", 1)[1] not in want_filt:
            fam.pop(k, None)
    if not want_xray:
        for k in XR_IDS:
            fam.pop(k, None)
    return {"fam": fam, "ok": ok, "missed": int(n_all - ok.sum()),
            "has_video": bool(nvt[0] is not None),
            "n_markers": int(nev_us.size)}


def _align(store, have, first, shift, times, fs, Bk, P, nr, spec, fam,
           RW=None, want_filt=()):
    """Braces' rule over every candidate, then +-15 ms at where it landed.

    The measure is Braces': the mains-free 5-100 Hz CSD, |CSD| averaged
    over the 16 rows around the depth where this recording's candidates are
    strongest, local maxima at least 12 ms apart within 100 ms of each
    stamp, and the assignment Braces makes -- largest peak first, one peak
    per stamp, never crossing. The stamps are the clock-corrected ones.
    """
    if not have:
        return
    RW = RW or _row_windows(1.0)
    depth = RW["depth"]
    n = len(have)
    W = store[have[0]]["band"].shape[1]
    S = int(round(ALIGN_WINDOW_MS / 1000.0 * fs))
    A = int(round(AL_MS / 1000.0 * fs))
    dist = max(1, int(round(ALIGN_DIST_MS / 1000.0 * fs)))
    H = int(round(50 / 1000.0 * fs))

    # The depth band: where |CSD| is largest at the corrected stamps, over
    # every candidate.
    strength = np.median(np.stack([
        np.abs(f[2][:, H - P:H + P + 1]).mean(axis=1) for f in first]), axis=0)
    k0 = int(np.argmax(strength))
    lo_r = max(0, k0 - depth // 2)
    hi_r = min(strength.size, lo_r + depth)
    lo_r = max(0, hi_r - depth)

    full, traces, t0s, stamps_c, windows = [], [], [], [], []
    peaks = []
    for j, i in enumerate(have):
        blk = store[i]["band"].astype(np.float64)
        cs = braces.csd_of(blk, spec)
        tr = np.abs(cs[lo_r:hi_r]).mean(axis=0)
        full.append(cs)
        traces.append(tr)
        t0 = float(times[i]) - Bk / fs
        t0s.append(t0)
        c = Bk + int(shift[j])
        stamps_c.append(t0 + c / fs)
        lo = max(A + 1, c - S)
        hi = min(W - A - 1, c + S + 1)
        windows.append((lo, hi))
        if hi - lo < 3:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pk, _ = _sig.find_peaks(tr[lo:hi], distance=dist)
        for q in pk:
            peaks.append((t0 + (lo + q) / fs, float(tr[lo + q])))
    peaks.sort()
    merged = []
    for t, h in peaks:
        if merged and t - merged[-1][0] < 0.5 / fs + 1e-6:
            if h > merged[-1][1]:
                merged[-1] = (t, h)
            continue
        merged.append((t, h))
    p_t = [m[0] for m in merged]
    p_h = [m[1] for m in merged]

    order = sorted(range(n), key=lambda j: stamps_c[j])
    taken = braces.assign([stamps_c[j] for j in order], p_t,
                          ALIGN_WINDOW_MS, amps=p_h or None) \
        if p_t else [None] * n
    got = [None] * n
    for rank, j in enumerate(order):
        got[j] = taken[rank]
    owner = {}
    for j, k in enumerate(got):
        if k is not None:
            owner[k] = j

    moves = np.array([(p_t[k] - stamps_c[j]) * 1000.0
                      if k is not None else np.nan
                      for j, k in enumerate(got)])
    fin = moves[np.isfinite(moves)]
    med = float(np.median(fin)) if fin.size else 0.0
    mad = float(np.median(np.abs(fin - med))) * 1.4826 if fin.size else 0.0
    out_lim = max(ALIGN_OUTLIER_MADS * mad, ALIGN_OUTLIER_FLOOR_MS)
    h_med = float(np.median([p_h[k] for k in got if k is not None])) \
        if any(k is not None for k in got) else 1.0
    p_arr = np.array(p_t) if p_t else np.empty(0)

    aligned = []
    for j, i in enumerate(have):
        k = got[j]
        lo, hi = windows[j]
        inwin = int(np.sum((p_arr >= t0s[j] + lo / fs)
                           & (p_arr < t0s[j] + hi / fs))) if p_arr.size else 0
        if p_arr.size:
            near = int(np.argmin(np.abs(p_arr - stamps_c[j])))
            near_ms = (p_arr[near] - stamps_c[j]) * 1000.0
            near_taken = float(near in owner and owner[near] != j)
        else:
            near_ms, near_taken = np.nan, np.nan
        mv = moves[j]
        fam["braces"][i] = [
            float(k is not None), mv,
            abs(mv) / ALIGN_WINDOW_MS if np.isfinite(mv) else np.nan,
            float(abs(mv) > ALIGN_EDGE * ALIGN_WINDOW_MS)
            if np.isfinite(mv) else np.nan,
            float(abs(mv - med) > out_lim) if np.isfinite(mv) else np.nan,
            float(abs(mv) < ALIGN_SAME_MS) if np.isfinite(mv) else np.nan,
            p_h[k] / (h_med or 1.0) if k is not None else np.nan,
            inwin, near_ms, near_taken]
        c = Bk + int(shift[j])
        a = int(round((p_t[k] - t0s[j]) * fs)) if k is not None else c
        a = int(np.clip(a, A + 1, W - A - 2))
        aligned.append(a)

    # Typical aligned patch and trace, over every candidate.
    usual_r = int(np.bincount([f[0] for f in first]).argmax())
    patches = [full[j][:, aligned[j] - A:aligned[j] + A + 1]
               for j in range(n)]
    typical_patch = np.median(np.stack(patches), axis=0)
    typical_trace = np.median(np.stack(
        [store[i]["band"][usual_r, aligned[j] - A:aligned[j] + A + 1]
         for j, i in enumerate(have)]), axis=0)

    def corr2(x, y):
        x = np.asarray(x, float).ravel()
        y = np.asarray(y, float).ravel()
        if x.std() == 0 or y.std() == 0:
            return np.nan
        return float(np.corrcoef(x, y)[0, 1])

    step = max(1, int(round(2 / 1000.0 * fs)))
    q5 = max(1, int(round(5 / 1000.0 * fs)))
    for j, i in enumerate(have):
        st = store[i]
        a = aligned[j]
        blk = st["band"].astype(np.float64)
        cs = full[j]
        win = blk[:, a - 3:a + 4]
        r = int(np.argmax(win.max(axis=1)))
        tr = blk[r]
        amp = float(tr[a]) or 1e-9
        wave = tr[a - A + 1:a + A + 1:step] / abs(amp)
        ct = traces[j][a - A + 1:a + A + 1:step]
        ct = ct / (float(ct.max()) + 1e-9)
        sharp = (2 * tr[a] - tr[a - 2] - tr[a + 2]) / abs(amp)
        _filtered_snapshots(st, blk, r, a, fs, spec, RW, fam, i,
                            want_filt)
        for w_ms in IMG_WINDOWS_MS:
            half = int(round(w_ms / 1000.0 * fs))
            fam["wimg%d" % w_ms][i] = (
                _wave_image(blk, r, a, half, RW["img"]) / abs(amp)).ravel()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                wd = _sig.peak_widths(tr, [a], rel_height=0.5,
                                      wlen=2 * A + 1)[0][0] / fs * 1000.0
        except Exception:                                # noqa: BLE001
            wd = np.nan
        m_ratio = np.log((st["mua"][:, a - q5:a + q5 + 1].mean(axis=1) + 1e-9)
                         / (st["mua_base"] + 1e-9))
        near = slice(max(0, r - RW["near"]), min(nr, r + RW["near"] + 1))
        far = [q for q in range(nr) if abs(q - r) > RW["far"]]
        prof = blk[:, a]
        vmax = float(np.abs(prof).max()) + 1e-9
        above = prof[:max(0, r - RW["near"])]
        below = prof[r + RW["near"] + 1:]
        va = float(above.mean()) / vmax if above.size else np.nan
        vb = float(below.mean()) / vmax if below.size else np.nan
        sg = np.sign(prof[r])
        flips = [abs(q - r) for q in range(nr) if np.sign(prof[q]) != sg]
        col = cs[:, a]
        cn = col / (float(np.abs(col).max()) + 1e-9)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp, _ = _sig.find_peaks(cn, prominence=0.3)
            nn, _ = _sig.find_peaks(-cn, prominence=0.3)
        kpos, kneg = int(np.argmax(col)), int(np.argmin(col))
        main = kpos if abs(col[kpos]) >= abs(col[kneg]) else kneg
        half = abs(cn[main]) / 2.0
        sgn = np.sign(cn[main])
        w = 0
        for d in (1, -1):
            q = main
            while 0 <= q < cn.size and sgn * cn[q] >= half:
                w += 1
                q += d
        lat_rows = list(range(max(0, r - RW["lat"]),
                             min(nr, r + RW["lat"] + 1)))
        seg = np.abs(blk[lat_rows, a - A:a + A + 1])
        lat = (np.argmax(seg, axis=1) - A) / fs * 1000.0
        slope = float(np.polyfit(np.arange(len(lat_rows)), lat, 1)[0]) \
            if len(lat_rows) >= 3 else np.nan
        conc = float(traces[j][a - q5:a + q5 + 1].mean()) / \
            (float(traces[j][a - A:a + A + 1].mean()) + 1e-9)
        fam["aligned15"][i] = np.concatenate([
            wave[:15], ct[:15], [
                sharp, wd,
                float(m_ratio[r]), float(m_ratio[near].mean()),
                float(m_ratio[far].mean()) if far else np.nan,
                float(m_ratio.max()), float(np.median(m_ratio)),
                va, vb,
                float(np.sign(va) != np.sign(vb))
                if np.isfinite(va) and np.isfinite(vb) else np.nan,
                (min(flips) / float(nr)) if flips else np.nan,
                pp.size, nn.size, max(0, w - 1),
                abs(kpos - kneg) / float(max(1, col.size)),
                abs(col[kneg]) / (abs(col[kpos]) + 1e-9),
                float(np.std(lat)), slope,
                corr2(patches[j], typical_patch),
                corr2(blk[usual_r, a - A:a + A + 1], typical_trace),
                conc]])
    return aligned, traces


def _bin(v, a, half, n):
    """v[a-half .. a+half] as `n` means of equal spans, edges clipped."""
    edges = np.clip(np.round(np.linspace(a - half, a + half + 1, n + 1))
                    .astype(int), 0, v.size)
    return np.array([v[e0:max(e1, e0 + 1)].mean() if e0 < v.size else np.nan
                     for e0, e1 in zip(edges[:-1], edges[1:])])


def _peaks(bt, lo, hi, dist, base, sd):
    """The real peaks of Braces' trace in [lo, hi), largest first.

    A peak counts when it stands XR_PEAK_Z robust SDs above this
    recording's level of that trace AND reaches XR_PEAK_REL of the tallest
    one there. Without the rule every ripple of the trace is a peak and
    every candidate has five; with it most have one or two, which is what
    a person sees.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pk, _ = _sig.find_peaks(bt[lo:hi], distance=dist)
    pk = [int(lo + q) for q in pk]
    pk = [q for q in pk if (bt[q] - base) / sd >= XR_PEAK_Z]
    if not pk:
        return []
    top = max(bt[q] for q in pk)
    pk = [q for q in pk if bt[q] >= XR_PEAK_REL * top]
    pk.sort(key=lambda q: -bt[q])
    return pk


def _xray(store, have, shift, aligned, btraces, fs, Bk, spec, RW, fam,
          spacing):
    """X-ray's snippets at the assigned peak and the five largest."""
    have_f = [(j, i) for j, i in enumerate(have)
              if XR_FILTER in (store[i].get("filt") or {})]
    if not have_f:
        return
    xp = dspca.Params(spacing=spacing)
    W = int(round(50 / 1000.0 * fs))
    S = int(round(ALIGN_WINDOW_MS / 1000.0 * fs))
    T = int(round(XR_BOX_MS / 1000.0 * fs))
    V = int(round(XR_WAVE_MS / 1000.0 * fs))
    dist = max(1, int(round(ALIGN_DIST_MS / 1000.0 * fs)))
    blocks = {i: store[i]["filt"][XR_FILTER].astype(np.float64)
              for _j, i in have_f}
    n_t = next(iter(blocks.values())).shape[1]

    # X-ray's depth band, from the candidate-triggered average at the
    # aligned peaks: how much each contact moves at the event against the
    # window's own edges. Searched over contiguous runs of the band's depth.
    tmpl = np.mean([blocks[i][:, np.clip(np.arange(aligned[j] - W,
                                                   aligned[j] + W + 1),
                                         0, n_t - 1)]
                    for j, i in have_f], axis=0)
    filt = dspca.toothy_csd(tmpl, spacing, xp)[1]
    edge = np.abs(np.arange(-W, W + 1)) > 0.7 * W
    score = np.clip(np.abs(filt[:, W]) - np.abs(filt[:, edge]).mean(axis=1),
                    0.0, None)
    span = max(3, min(score.size, RW["depth"]))
    tot = np.convolve(score, np.ones(span), "valid")
    lo_r = int(np.argmax(tot))
    rows = list(range(lo_r, lo_r + span))
    sep = max(1, int(round(XR_SINK_SEP_UM / float(spacing))))
    per = len(NAMES["xray5"]) // len(XR_SLOTS)
    # The level of Braces' trace across this recording, for the peak rule.
    allb = np.concatenate([np.asarray(btraces[j], float) for j, _i in have_f])
    base = float(np.median(allb))
    sd = float(np.median(np.abs(allb - base))) * 1.4826 or 1.0

    for j, i in have_f:
        b = blocks[i]
        cs = dspca.toothy_csd(b[rows], spacing, xp)[1]
        c = Bk + int(shift[j])
        lo, hi = max(0, c - S), min(n_t, c + S + 1)
        bt = np.asarray(btraces[j], float)
        tops = _peaks(bt, lo, hi, dist, base, sd)[:len(XR_SLOTS) - 1]
        hmax = max([bt[q] for q in tops] + [bt[aligned[j]], 1e-12])
        mean_wave = cs.mean(axis=0)
        row = np.full(len(NAMES["xray5"]), np.nan)
        for k, q in enumerate([aligned[j]] + tops):
            seg = cs[:, max(0, q - T):min(n_t, q + T + 1)]
            if seg.shape[1] == 0:
                continue
            prof = seg.mean(axis=1)
            r1, r2 = dspca.two_sinks(prof, sep)
            gap = abs(r2 - r1)
            delta = (min(max((gap - 1.0) / max(len(rows) - 2.0, 1.0), 0.0),
                         1.0) if gap >= 1 else 0.0)
            lo_p, hi_p = float(prof.min()), float(prof.max())
            pn = (prof - lo_p) / (hi_p - lo_p) if hi_p > lo_p \
                else np.zeros_like(prof)
            pn = np.interp(np.linspace(0, len(pn) - 1, XR_PROFILE_ROWS),
                           np.arange(len(pn)), pn)
            wave = _unit(_bin(mean_wave, q, V, XR_WAVE_COLS))
            row[k * per:(k + 1) * per] = np.concatenate([
                [(q - c) / fs * 1000.0, bt[q] / hmax], pn, wave, [delta]])
        fam["xray5"][i] = row


def save(path, got):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part.npz"
    np.savez_compressed(
        tmp, ok=got["ok"], pv=np.array([PHYS_VERSION]),
        iv=np.array([IMG_VERSION]), xv=np.array([XR_VERSION]),
        meta=np.array([str({k: got[k] for k in ("missed", "has_video",
                                                "n_markers")})]),
        **{"fam_" + k: v for k, v in got["fam"].items()})
    os.replace(tmp, path)


def load(path):
    if not os.path.exists(path):
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            if int(z["pv"][0]) != PHYS_VERSION:
                return None
            return {"ok": z["ok"].astype(bool),
                    "fam": {k: z["fam_" + k] for k in FAMILY_IDS
                            if "fam_" + k in z.files}}
    except Exception:                                    # noqa: BLE001
        return None


def _unit(x):
    m = float(np.nanmax(np.abs(x))) if np.size(x) else 0.0
    return x / m if m > 0 else x


def _filtered_snapshots(st, blk, r, a, fs, spec, RW, fam, i, want=None):
    """The three snapshots through each filter in `want` (every one the
    store holds, and 5-100 Hz, when None), at aligned peak `a`."""
    if want is None:
        want = set(st.get("filt") or ()) | ({"5_100"} if st.get("filt")
                                            else set())
    if not want:
        return              # not asked for: see the end of read_physio
    w = blk.shape[1]
    full_half = int(round(50 / 1000.0 * fs))
    thin_half = int(round(THIN_MS / 1000.0 * fs))
    tt = np.clip(np.arange(a - int(round(TRACE_MS / 1000.0 * fs)),
                           a + int(round(TRACE_MS / 1000.0 * fs)) + 1,
                           max(1, int(round(TRACE_STEP_MS / 1000.0 * fs)))),
                 0, w - 1)
    for fid, _fb in FILTERS:
        if fid not in want:
            continue
        if fid == "5_100":
            b = blk
        elif fid in (st.get("filt") or {}):
            b = st["filt"][fid].astype(np.float64)
        else:
            continue
        if fid == "notch":
            b = b - b.mean(axis=1, keepdims=True)
        cs = braces.csd_of(b, spec)
        fam["fwhole_" + fid][i] = _unit(_picture(cs, a, full_half)).ravel()
        fam["fthin_" + fid][i] = _unit(
            _wave_image(b, r, a, thin_half, RW["img"])).ravel()
        fam["ftrace_" + fid][i] = _unit(b[r, tt])


def has(path, fams):
    """Whether the second read cached at `path` holds every one of `fams`.

    A read made before an input existed holds everything it had then and
    nothing since: a run asking for a newer input reads that recording
    again, and one that does not uses the file as it is."""
    if not os.path.exists(path):
        return False
    try:
        with np.load(path, allow_pickle=False) as z:
            if int(z["pv"][0]) != PHYS_VERSION:
                return False
            if any(f in IMG_IDS or f in FILT_IDS for f in fams) and (
                    "iv" not in z.files or int(z["iv"][0]) != IMG_VERSION):
                return False
            if any(f in XR_IDS for f in fams) and (
                    "xv" not in z.files or int(z["xv"][0]) != XR_VERSION):
                return False
            return all("fam_" + f in z.files for f in fams)
    except Exception:                                    # noqa: BLE001
        return False
