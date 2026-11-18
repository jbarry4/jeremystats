"""
horizon.py -- which frequency was in charge, everywhere on the probe at once.

Panorama answers "across this session, which frequency was in charge, and how
often?" for ONE channel. This asks it of every channel and lays the answers
out by depth, so the same picture carries time along one axis and the shank
down the other.

WHY THIS IS NOT JUST PANORAMA WITH A LOOP ROUND IT
--------------------------------------------------
Three views already exist and each drops one axis to fit on a screen:

    analysis `theta`      all channels, all time, band LOCKED at 4-12
    analysis `bandpower`  all frequencies, all time, ONE channel
    panorama              all frequencies, all time collapsed to a histogram

The band-power panel is the closest, and it refuses more than one channel by
hand (`if len(ch_list) != 1` -- analysis.py). That refusal is the thing being
lifted. What makes three axes fit in two is collapsing frequency to a single
number per cell -- the one that won -- and spending colour on it.

The measurement is already there. `panorama.run` computes a dominant
frequency per window for every channel it is given; it then draws them one at
a time through a pager, in file order. So most of this module is layout,
ordering and cost, and the numbers come from the functions Panorama already
uses -- deliberately, because two spectral engines in one app is only a
problem when you cannot tell which you are looking at.

WHAT THE PICTURE MEANS, AND WHY THE TEXTURE IS THE FINDING
-----------------------------------------------------------
From `FOOOF Playgroun/theta_channels.py`, which is the command-line analysis
this replaces, the way `theta_through_time.py` was the one Panorama replaced:

    Theta is globally coherent across the hippocampus -- at any instant the
    whole structure is oscillating at one rate. So the theta peak frequency
    should agree across channels, which means (a) averaging it is meaningful
    and (b) the SPREAD across channels is a free quality check.

So:

    vertical stripes    the column agrees. One rhythm, shifting through the
                        session. This is what theta looks like.
    horizontal bands    the layers disagree. Either real, or the probe is not
                        all in one structure. Both are worth knowing, and
                        these are the horizons the tool is named for.
    speckle             no rhythm; the argmax is measuring noise. It fades
                        out on its own -- see `peak_margin` below.

`agreement()` is that spread, measured, so the thing you read off the picture
is also a number a test can be run on.

AND THE ONE THING THAT MUST NOT BE DONE
----------------------------------------
The same file is blunt about what may not be pooled across channels, and it
is worth repeating here because this module is where somebody would do it:

    RAW POWER, in uV^2 [cannot be averaged]. Theta amplitude across a probe
    spanning the hippocampal layers varies by something like a factor of ten,
    and the theta dipole REVERSES across the fissure. So a mean of raw theta
    power over channels is a mean over anatomy.

Nothing in here averages power across channels. The map carries frequencies.

CHANNEL NUMBER IS NOT DEPTH
---------------------------
On an H3 it is, and that is the only case where stacking by CSC number is
right. On an H10-D consecutive CSC numbers step ACROSS three interleaved
columns, so channels 1, 2 and 3 are three different columns at the same
depth; on a dual implant CSC 1-64 is hippocampus and 65-128 is M2. A stack by
channel number would draw a depth axis that is not one, and it would look
entirely plausible. `probes.columns_for` already answers this -- it is what
CSD uses, for the same reason -- so the row order comes from there and a
probe with several columns gets several panes rather than one wrong one.

TWO FIDELITIES, AND THE RESULT SAYS WHICH
------------------------------------------
Reading all 64 channels of a 30-minute recording costs about three minutes.
Fitting every window of every channel with fooof costs about two hours: the
measured rates are 1.4e-3 s per channel-second to read and 6.5e-2 s per
window to fit, so the fit dominates by about forty-five times. That is the
whole cost problem, and it is entirely in the fit.

    survey  the aperiodic component is fitted ONCE per channel, on the mean
            spectrum -- which is free, because averaging the spectrogram's
            columns IS the whole-recording Welch spectrum -- and every column
            is flattened by that one curve before its argmax is taken. This
            is `flat_hz`'s definition with the peak decomposition left out.
            Minutes.

    full    `panorama.dominant` per window: the real fit, which can say a
            window had NO peak, and gives `peak_margin` from the runner-up
            the fit actually found. Hours, and what VACC is for.

Full mode is the same fitter on the same kind of array: `panorama.spectrogram`
builds it, `panorama.dominant` reads it, and no second engine exists here.
How close that puts it to a Panorama run of the same channel is measured
rather than asserted, and it turns on one thing -- the decimation target,
which Panorama takes from the band it reads the answer from and this takes
from the wider range it fits the slope over:

    fit range = band (fit_hi 14)   max |diff|  5e-06 Hz   -- identical, to
                                   the fourth decimal Panorama stores
    fit range 2-100 (the default)  median      6e-04 Hz
                                   max         3e-02 Hz

So: pin `fit_hi` to the top of the band and the two agree exactly, which is
what `tools/check_horizon.py` asserts. Leave it wide -- the default, because
a 1/f slope fitted over under three octaves is mostly fitting whatever theta
is doing -- and they differ by well under the 0.5 Hz the transform can
resolve, for a reason that is written down rather than wondered about.

Survey mode is a different measurement and is labelled as one everywhere it
appears.
"""
from __future__ import annotations

import math

import numpy as np

from . import analysis, cfc, panorama, probes, specparam, spectrum

# --------------------------------------------------------------------------
# What this tool asks by default, and why those numbers
# --------------------------------------------------------------------------

#: The band the map draws and takes its argmax in.
#:
#: 2-14 rather than 4-12. A hard 4-12 window guarantees every cell reports a
#: theta even where there is none, and pins the winner against an edge when
#: the real peak is outside -- with nothing in the picture to say so. Under
#: urethane theta sits low, and a 4 Hz floor would clip it outright. The
#: shoulders are drawn and 4-12 is marked on the bar instead.
DEFAULT_FLO = 2.0
DEFAULT_FHI = 14.0

#: The band that is named theta on the colour bar. Same numbers as
#: `spectrum.BANDS` and `analysis.THETA_BAND`, so "theta" here means what it
#: means beside every other panel in the app.
THETA_BAND = (4.0, 12.0)

#: The range the APERIODIC component is fitted over, which is not the range
#: the answer is read from.
#:
#: A 1/f fit over 2-14 Hz alone is under three octaves, and a slope fitted to
#: that thin a stretch is mostly fitting whatever theta is doing -- which is
#: the very thing being measured against it. Fitting over 2-100 and reading
#: the argmax out of 2-14 costs nothing extra: the spectrogram is computed
#: once over the wider range and sliced.
DEFAULT_FIT_LO = 2.0
DEFAULT_FIT_HI = 100.0

#: Windowing. `sub_s` buys frequency resolution (1/sub Hz), `win_s` is how
#: much recording each column averages over, `step_s` is how often a column
#: happens. Sub and win are Panorama's, unchanged, so a row of this map and a
#: Panorama run of that channel are the same measurement.
DEFAULT_SUB_S = 2.0
DEFAULT_WIN_S = 8.0

#: Panorama's, unchanged, and it has to stay that way.
#:
#: `step_s` is the spectrogram's hop, and it is what makes a column of this
#: map and a column of a Panorama run the same column. It also sets `n_avg`
#: -- with sub 2 and win 8 a column is seven overlapping sub-windows -- so
#: changing it here would change what a column IS, not merely how many there
#: are.
#:
#: It cannot be used as the cost lever either, and this is worth writing
#: down because it looks as though it can. `scipy.signal.spectrogram` takes
#: `noverlap`, which can only make the hop SHORTER than `nperseg`: ask for a
#: five-second step with a two-second transform and `nper - hop` goes
#: negative, the overlap clamps to zero, and the columns come out two
#: seconds apart regardless. Nothing errors. The first run of this module
#: asked for 23 windows and fitted 59.
DEFAULT_STEP_S = 1.0

#: Keep one column in five. THIS is the cost lever.
#:
#: A display argument and not a compute compromise: a 30-minute recording at
#: one column a second is 1800 columns on a map about a thousand pixels
#: wide, and more columns than pixels is not more information. Five gives
#: ~360, still more than the map can show, and costs a fifth as much to fit.
#:
#: Done by dropping columns rather than by widening the hop, so the ones kept
#: are EXACTLY the columns Panorama would have computed at those times --
#: same transform, same averaging, same numbers. That is what lets a row of
#: this map and a Panorama run of that channel be the same answer, and it is
#: what `tools/check_horizon.py` asserts.
DEFAULT_EVERY = 5

#: The width of one step on the colour bar. Presentation: the stored answer
#: is the unrounded frequency, and re-binning is a re-render (see `recolor`).
#:
#: Stepped rather than smooth because with a dozen steps a reader can NAME
#: the frequency from the swatch, and with a continuous ramp they can only
#: say "warmer". `sub_s = 2.0` gives 0.5 Hz bins, so 1 Hz steps are inside
#: what was actually measured.
DEFAULT_BIN_HZ = 1.0

#: How far from the winner a runner-up has to sit to count as a different
#: rhythm rather than the same bump's shoulder. A theta peak is one to three
#: Hz wide, so anything inside two Hz of the winner is the winner.
DEFAULT_SEP_HZ = 2.0

#: How close to the column's median a channel has to be to count as agreeing.
#: One display step: if two channels round to the same swatch they are not
#: disagreeing about anything a reader could see.
DEFAULT_AGREE_TOL_HZ = 1.0

#: Not jet.
#:
#: `analysis.py` already carries the argument, beside the map it registered
#: for the same reason: "a rainbow invents edges in smooth data". This is a
#: tool whose entire purpose is reading whether a band is there, and jet's
#: cyan and yellow transitions manufacture visible edges in a smooth field.
#: Jet stays on the list -- it is the lab standard and every existing figure
#: uses it -- but it is not what this opens on.
DEFAULT_CMAP = "viridis"

#: How visible the least confident cell is. Not zero: fully transparent
#: already means "nothing was read here" (a gap, a dropped channel), and a
#: coin toss is a different fact from an absence.
ALPHA_FLOOR = 0.12

#: Every 8th channel, then every 4th, then the rest.
INTERLACE_STRIDE = 8

#: How many results to keep. One map is a few hundred kilobytes of float32,
#: far smaller than Panorama's spectrogram matrices, but the spectra behind
#: it are not kept at all -- see `run`.
CACHE_MAX = 6

#: Which settings make this a different answer. Presentation is deliberately
#: absent -- the colormap, the step of the colour bar, absolute against
#: relative -- for the same reason `panoramaset.PARAM_KEYS` leaves them out:
#: re-colouring a map does not make the frequencies under it different
#: numbers, and including them would split the store into copies that differ
#: by nothing.
PARAM_KEYS = (
    "f_lo", "f_hi", "fit_lo", "fit_hi", "sub_s", "win_s", "step_s",
    "line_hz", "t0", "t1", "fidelity", "sep_hz", "every",
    "peak_width_limits", "max_n_peaks", "min_peak_height", "aperiodic_mode",
)

FIDELITIES = ("survey", "full")


class HorizonError(Exception):
    pass


# --------------------------------------------------------------------------
# The rows: which channel is at which depth, and in which pane
# --------------------------------------------------------------------------

def rows_for(session, spec, rec=None, sheet=None):
    """The map's rows, in depth order, grouped into panes.

    Returns `(panes, rows)`. `rows` is flat and in draw order; every entry
    carries the position in `rows` it occupies, so the matrix and the layout
    cannot come apart. `panes` says which slice of `rows` belongs to which
    column of the probe.

    A probe with no column map (an H3, or an unconfirmed one) is one pane of
    every selected channel in channel order, which for a linear array IS
    depth order. A probe with columns gets one pane each, because a stack
    that crosses from one column to another -- or, on a dual implant, from
    hippocampus to M2 -- is drawing a depth axis that does not exist.

    `sheet` is this recording's StrataScope record, passed in rather than
    read here: the layer store is an instance the app owns, and a compute
    module that reached for it would be a second place that knows where
    GUI_logs lives.
    """
    channels = list(session.get("channels") or [])
    if not channels:
        raise HorizonError("This recording has no channels to read.")

    want = spec.get("channels")
    if want:
        keep = {int(i) for i in want}
    else:
        # Every channel not marked bad. Never "the first one" -- a map of one
        # row is not what this tool is; and never all of them regardless of
        # what was marked, which would put a known-dead wire in the picture.
        keep = {i for i, ch in enumerate(channels) if not ch.get("bad")}
    if not keep:
        raise HorizonError(
            "Every channel on this recording is marked bad, so there is "
            "nothing to draw. Clear one in the session's channel editor, or "
            "choose channels by hand.")

    probe_state = probes.state_of(rec or {})
    probe_id = spec.get("probe") or probe_state.get("probe")
    cols = probes.columns_for(probe_id, channels) if probe_id else None

    label = {}
    if isinstance(sheet, dict):
        for num, region in (sheet.get("labels") or {}).items():
            try:
                label[int(num)] = region
            except (TypeError, ValueError):
                continue

    def entry(i, depth=None):
        ch = channels[i]
        num = int(ch.get("number")) if ch.get("number") is not None else None
        return {
            "index": int(i),
            "number": num,
            "label": ch.get("label") or ("CSC%s" % num),
            "depth_um": (None if depth is None else float(depth)),
            "region": label.get(num),
        }

    panes, rows = [], []
    if cols:
        for col in cols:
            idx = list(col.get("indices") or [])
            depths = list(col.get("depths_present") or [])
            start = len(rows)
            for j, i in enumerate(idx):
                if i not in keep:
                    continue
                rows.append(entry(i, depths[j] if j < len(depths) else None))
            if len(rows) == start:
                continue            # nothing of this column was selected
            panes.append({
                "id": col.get("id"), "label": col.get("label") or col.get("id"),
                "shank": col.get("shank"), "column": col.get("column"),
                "region": col.get("region"),
                "row0": start, "row1": len(rows),
                "n": len(rows) - start,
                "missing": int(col.get("missing") or 0),
            })
    if not panes:
        # No column map, or none of its columns held a selected channel.
        for i in sorted(keep):
            rows.append(entry(i))
        panes = [{
            "id": "all", "label": "Every channel", "shank": None,
            "column": None, "region": None,
            "row0": 0, "row1": len(rows), "n": len(rows), "missing": 0,
        }]

    for r, row in enumerate(rows):
        row["row"] = r
    return panes, rows


def interlace(n, stride=INTERLACE_STRIDE):
    """The order the rows are filled in: every 8th, then 4th, then the rest.

    Panorama draws its spectrogram left to right as it reads, so a run that
    is obviously wrong can be stopped in the first ten seconds rather than at
    the end of four minutes. This is that idea applied to the axis this view
    adds. Filling top to bottom would put the whole depth extent on screen
    only at the very end, which is precisely when knowing it no longer helps;
    filling every eighth row first puts a coarse version of the entire map up
    after an eighth of the work, and it sharpens from there.
    """
    n = int(n)
    seen, out = set(), []
    s = max(1, int(stride))
    while s >= 1:
        for i in range(0, n, s):
            if i not in seen:
                seen.add(i)
                out.append(i)
        if s == 1:
            break
        s //= 2
    return out


# --------------------------------------------------------------------------
# Planning and cost
# --------------------------------------------------------------------------

def plan_for(session, spec, rec=None, sheet=None):
    """What a run would do, without doing any of it."""
    fs = float(session.get("fs") or 0) or 30000.0
    dur = float(session.get("duration_s") or 0.0)
    t0 = max(0.0, float(spec.get("t0") or 0.0))
    t1 = float(spec.get("t1") or dur or 0.0)
    if t1 <= t0:
        t1 = dur
    span = max(0.0, t1 - t0)

    f_lo = float(spec.get("f_lo") or DEFAULT_FLO)
    f_hi = float(spec.get("f_hi") or DEFAULT_FHI)
    if f_hi <= f_lo:
        raise HorizonError(
            "The band is empty: %g Hz is not below %g Hz." % (f_lo, f_hi))

    fit_lo = float(spec.get("fit_lo") or DEFAULT_FIT_LO)
    fit_hi = float(spec.get("fit_hi") or DEFAULT_FIT_HI)
    # The fit range has to contain the band the answer is read from, or the
    # aperiodic curve would be extrapolated over the very bins the argmax is
    # taken in.
    fit_lo = min(fit_lo, f_lo)
    fit_hi = max(fit_hi, f_hi)

    want_fs = spectrum.target_rate(fit_hi)
    factor = max(1, int(math.floor(fs / want_fs))) if want_fs < fs else 1
    out_fs = fs / factor

    sub_s = float(spec.get("sub_s") or DEFAULT_SUB_S)
    win_s = float(spec.get("win_s") or DEFAULT_WIN_S)
    step_s = float(spec.get("step_s") or DEFAULT_STEP_S)
    win_s = max(win_s, sub_s)
    nper = max(16, int(round(sub_s * out_fs)))
    n_avg = max(1, int(round((win_s - sub_s) / step_s)) + 1)
    n_raw = max(0, int(math.floor(max(0.0, span - win_s) / step_s)) + 1)
    every = max(1, int(spec.get("every") or DEFAULT_EVERY))
    n_windows = int(math.ceil(n_raw / float(every))) if n_raw else 0

    line_hz = spec.get("line_hz")
    line_hz = spectrum.LINE_HZ if line_hz is None else float(line_hz or 0.0)

    fidelity = str(spec.get("fidelity") or "survey").lower()
    if fidelity not in FIDELITIES:
        raise HorizonError(
            "Unknown fidelity %r. It is 'survey' or 'full'." % fidelity)

    panes, rows = rows_for(session, spec, rec, sheet)

    return {
        "fs": fs, "fs_used": out_fs, "decimate": factor,
        "t0": t0, "t1": t1, "span_s": span,
        "f_lo": f_lo, "f_hi": f_hi,
        "fit_lo": fit_lo, "fit_hi": fit_hi,
        "theta": list(THETA_BAND),
        "sub_s": sub_s, "win_s": win_s, "step_s": step_s,
        "nperseg": nper,
        "resolution_hz": (out_fs / nper) if nper else 0.0,
        "n_avg": n_avg,
        "every": every,
        "n_windows_raw": n_raw,
        "n_windows": n_windows,
        "column_s": step_s * every,
        "n_channels": len(rows),
        "line_hz": line_hz,
        "line_half_bw": spectrum.LINE_HALF_BW,
        "fidelity": fidelity,
        "sep_hz": float(spec.get("sep_hz") or DEFAULT_SEP_HZ),
        "agree_tol_hz": float(spec.get("agree_tol_hz")
                              or DEFAULT_AGREE_TOL_HZ),
        "bin_hz": float(spec.get("bin_hz") or DEFAULT_BIN_HZ),
        "cmap": spec.get("cmap") or DEFAULT_CMAP,
        "colour_mode": spec.get("colour_mode") or "absolute",
        "panes": panes,
        "rows": rows,
        "probe": (spec.get("probe")
                  or (probes.state_of(rec or {}) or {}).get("probe")),
        "probe_state": probes.state_of(rec or {}),
        "megasamples": max(1e-6, span * out_fs / 1e6),
        "fit": panorama._fit_settings(spec),
    }


def stage_name(plan):
    """The job stage this run ticks, and the rate its estimate reads.

    One function, because the two came apart: the route declared a stage
    called "horizon rows" and `estimate` asked `cfc.rate_for` for "horizon
    survey". Nothing errored -- `rate_for` returns 0.0 for a stage it has
    never heard of -- so the fitting half of every estimate was silently
    zero, and the measurement the run took was filed under a name no
    estimate would ever read. A 62-channel run quoted 78 s and took 168.
    """
    return ("horizon full" if plan.get("fidelity") == "full"
            else "horizon survey")


def estimate(session, spec, rec=None, sheet=None):
    """What it will cost, before anybody waits for it."""
    plan = plan_for(session, spec, rec, sheet)
    n_ch = max(1, plan["n_channels"])
    where = cfc.volume_key(session.get("path"))
    stage = stage_name(plan)
    # One rate, covering read and fit together, because that is how the loop
    # spends the time: a channel is read, fitted and discarded before the
    # next starts, so the two cannot be told apart from outside. The same
    # argument `panorama bulk` makes, and the reason this is counted in
    # seconds of recording rather than in channels -- so one rate holds for
    # a twenty-minute recording and a forty-minute one.
    total = cfc.rate_for(stage, where) * plan["span_s"] * n_ch
    # Split for display only, from the read rate this machine has already
    # measured for every other tool. It is a breakdown of the estimate, not
    # a second estimate.
    read = min(total, cfc.rate_for("spectrum read", where)
               * plan["span_s"] * n_ch)
    return {
        "ok": True,
        "plan": _plan_public(plan),
        "stage": stage,
        "seconds": round(total, 1),
        "read_s": round(read, 1),
        "fit_s": round(max(0.0, total - read), 1),
        "notes": notes_for(plan),
    }


def _plan_public(plan):
    """The plan without the numpy-adjacent internals the client cannot use."""
    out = dict(plan)
    out.pop("fit", None)
    return out


def notes_for(plan):
    """The honest sentences the form and the waiting screen both say."""
    out = []
    if plan["decimate"] > 1:
        out.append("decimating %s to %s Hz, which is what makes %g Hz "
                   "answerable" % ("{:,}".format(int(plan["fs"])),
                                   "{:,.0f}".format(plan["fs_used"]),
                                   plan["fit_hi"]))
    out.append("%.3g s transform, so %.3g Hz bins -- the map steps at %g Hz"
               % (plan["sub_s"], plan["resolution_hz"], plan["bin_hz"]))
    out.append("each column averages %d sub-window%s over %.3g s"
               % (plan["n_avg"], "" if plan["n_avg"] == 1 else "s",
                  plan["win_s"]))
    out.append("%s window%s per channel, one every %.3g s"
               % ("{:,}".format(plan["n_windows"]),
                  "" if plan["n_windows"] == 1 else "s", plan["column_s"]))
    if plan["every"] > 1:
        out.append("one column in %d kept, out of %s -- the ones kept are "
                   "the columns Panorama would have computed at those times"
                   % (plan["every"], "{:,}".format(plan["n_windows_raw"])))
    out.append("%d channel%s, in %d pane%s"
               % (plan["n_channels"], "" if plan["n_channels"] == 1 else "s",
                  len(plan["panes"]),
                  "" if len(plan["panes"]) == 1 else "s"))
    if plan["fidelity"] == "survey":
        out.append("survey: one aperiodic fit per channel, on its mean "
                   "spectrum, then the argmax of every flattened column")
    else:
        out.append("full: %s fit%s, the same fitter Panorama uses"
                   % ("{:,}".format(plan["n_windows"] * plan["n_channels"]),
                      "" if plan["n_windows"] * plan["n_channels"] == 1
                      else "s"))
    out.append("aperiodic fitted over %g-%g Hz, the answer read from %g-%g"
               % (plan["fit_lo"], plan["fit_hi"], plan["f_lo"], plan["f_hi"]))
    if plan["line_hz"]:
        out.append("bridging %g Hz and its harmonics, %g Hz either side"
                   % (plan["line_hz"], plan["line_half_bw"]))
    return out


# --------------------------------------------------------------------------
# The two ways of asking which frequency won
# --------------------------------------------------------------------------

def survey_dominant(freqs, pxx, plan):
    """The argmax of every column, flattened by one aperiodic fit.

    The expensive half of a fooof fit is the peak decomposition, not the
    aperiodic component -- and `flat_hz`, the definition used here, does not
    need the peaks at all: it is the highest bin left once the slope is taken
    off. So the slope is fitted once, on this channel's mean spectrum, and
    subtracted from every column.

    Fitting it once rather than per window is the approximation, and it is
    the one `tools/check_horizon.py` exists to measure. The argument for it:
    over a narrow band a wrong exponent is a slight tilt, which can only move
    the argmax when the spectrum is nearly flat -- and a nearly flat spectrum
    is exactly the case the margin is about to mark as untrustworthy anyway.

    Returns `hz`, `margin`, `above` and the aperiodic parameters. `above` is
    how far the winner stood over the aperiodic curve, in log10 power: at or
    below zero there was no rhythm, and the margin is NaN so the cell draws
    as good as empty.
    """
    freqs = np.asarray(freqs, dtype=float)
    n = pxx.shape[1]
    out_hz = np.full(n, np.nan)
    out_mg = np.full(n, np.nan)
    out_ab = np.full(n, np.nan)

    # The mean spectrum, which is the whole-recording Welch spectrum -- the
    # columns are already averages of overlapping sub-windows, so averaging
    # them is the same segments averaged the same way. Free.
    with np.errstate(invalid="ignore"):
        mean_psd = np.nanmean(pxx, axis=1)
    fit_ok = np.isfinite(mean_psd) & (mean_psd > 0) & np.isfinite(freqs)
    if fit_ok.sum() < 8:
        return out_hz, out_mg, out_ab, None

    mode = specparam.default_mode(plan["fit_lo"], plan["fit_hi"])
    with np.errstate(divide="ignore", invalid="ignore"):
        logm = np.log10(mean_psd[fit_ok])
    try:
        ap = specparam._robust_aperiodic(freqs[fit_ok], logm, mode)
    except Exception:
        return out_hz, out_mg, out_ab, None

    curve = specparam.aperiodic(freqs, *ap)
    with np.errstate(divide="ignore", invalid="ignore"):
        flat = np.log10(np.where(pxx > 0, pxx, np.nan)) - curve[:, None]

    band = (freqs >= plan["f_lo"]) & (freqs <= plan["f_hi"])
    fb = freqs[band]
    sub = flat[band, :]
    if fb.size < 2:
        return out_hz, out_mg, out_ab, list(map(float, ap))

    # A column with any hole in it has no honest spectrum -- the same rule
    # Panorama applies, and for the same reason.
    good = np.isfinite(sub).all(axis=0)
    gi = np.flatnonzero(good)
    if not gi.size:
        return out_hz, out_mg, out_ab, list(map(float, ap))

    win = np.argmax(sub[:, gi], axis=0)
    hz = fb[win]
    h1 = sub[win, gi]

    # The runner-up, which has to be a DIFFERENT bump rather than the
    # winner's own shoulder -- so everything within `sep_hz` of the winner is
    # masked out before the second maximum is taken.
    sep = float(plan.get("sep_hz") or DEFAULT_SEP_HZ)
    far = np.abs(fb[:, None] - hz[None, :]) > sep
    rest = np.where(far, sub[:, gi], -np.inf)
    h2 = np.max(rest, axis=0)
    h2 = np.where(np.isfinite(h2), h2, 0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        margin = 1.0 - (np.maximum(h2, 0.0) / h1)
    # Nothing rose above the aperiodic curve: there is no rhythm here, and
    # the frequency that came out is the argmax of a slope.
    margin = np.where(h1 > 0, margin, np.nan)

    out_hz[gi] = hz
    out_mg[gi] = np.clip(margin, 0.0, 1.0)
    out_ab[gi] = h1
    return out_hz, out_mg, out_ab, list(map(float, ap))


def full_dominant(freqs, pxx, plan, job=None):
    """`panorama.dominant` over this channel, sliced to the band.

    Deliberately the same call Panorama makes, over the same array it would
    have: `panorama.spectrogram` keeps `f_lo <= f <= f_hi`, so slicing this
    channel's wider spectrogram to the same band gives the identical matrix.
    That identity is the point -- it is what makes a row of this map and a
    Panorama run of that channel the same answer, and it is what
    `tools/check_horizon.py` asserts.
    """
    freqs = np.asarray(freqs, dtype=float)
    band = (freqs >= plan["f_lo"]) & (freqs <= plan["f_hi"])
    dom = panorama.dominant(freqs[band], pxx[band, :],
                            plan["f_lo"], plan["f_hi"], plan["fit"], job=job)
    return dom["peak_hz"], dom["peak_margin"], dom["peak_pw"], dom


# --------------------------------------------------------------------------
# Reading the probe
# --------------------------------------------------------------------------

def _line_mask(freqs, plan):
    """Which bins the mains and its harmonics sit in.

    It matters here even though 60 Hz is far above the band the answer is
    read from: the aperiodic component is fitted over 2-100 Hz, and a mains
    spike left in that fit tilts the curve every column is then flattened
    by -- so the interference would reach the answer through the slope
    rather than through the argmax.
    """
    if not plan.get("line_hz"):
        return None
    mask, _at = spectrum.line_bins(np.asarray(freqs, dtype=float),
                                   plan["line_hz"], plan["fit_hi"],
                                   plan["line_half_bw"])
    return mask


def read_row(session, row, plan, job=None):
    """One channel, from disk to a row of the map.

    The spectra themselves are NOT kept. Panorama holds its matrices because
    re-colouring a spectrogram has to re-render them; here the picture is
    made from the two thin arrays this returns, and holding sixty-four
    channels of float64 spectrogram would be about four hundred megabytes to
    no purpose.
    """
    # The session's own channel dict, not the row: everything downstream of
    # `read_gapped` wants the record with `file` and `number` on it, and an
    # index reaches `demo.read_window` as an int that cannot be subscripted.
    ch = (session.get("channels") or [])[int(row["index"])]
    # `x` comes back on the recording's own clock with NaN in the holes, so
    # its index IS its time -- which is the whole reason a spectrogram may be
    # built from it. `times` below is therefore an offset from `t0`, not an
    # absolute, and a gap becomes a transparent column rather than shifting
    # everything after it earlier.
    x, gaps = panorama.read_gapped(
        session, ch, plan["t0"], plan["t1"],
        plan["decimate"], plan["fs_used"], job=job)
    freqs, times, pxx, _ = panorama.spectrogram(
        x, plan["fs_used"], plan["sub_s"], plan["win_s"], plan["step_s"],
        plan["fit_lo"], plan["fit_hi"])
    mask = _line_mask(freqs, plan)
    line_removed = 0.0
    if mask is not None and mask.any():
        pxx, line_removed = panorama._bridge_line(freqs, pxx, mask)

    # Thin the columns BEFORE anything is fitted -- the fit is the whole
    # cost, so dropping columns afterwards would save nothing. The mean
    # spectrum the aperiodic fit uses is taken from what is left, which is
    # still hundreds of columns on any real recording.
    every = int(plan.get("every") or 1)
    if every > 1:
        pxx = pxx[:, ::every]
        times = np.asarray(times)[::every]

    extra = {"line_removed": float(line_removed),
             "gaps": (gaps or {}).get("n") if isinstance(gaps, dict) else None}
    if plan["fidelity"] == "full":
        hz, margin, above, dom = full_dominant(freqs, pxx, plan, job=job)
        extra["n_nopeak"] = int(dom.get("n_nopeak") or 0)
        extra["n_rejected"] = int(dom.get("n_rejected") or 0)
    else:
        hz, margin, above, ap = survey_dominant(freqs, pxx, plan)
        extra["aperiodic"] = ap
        # A window whose winner never rose above the aperiodic curve is this
        # route's version of "no peak" -- the same finding, arrived at
        # without the decomposition.
        extra["n_nopeak"] = int(np.sum(np.isfinite(hz) & ~np.isfinite(margin)))
    return np.asarray(times) + plan["t0"], hz, margin, above, extra


# --------------------------------------------------------------------------
# Reading the picture: how much the column agrees with itself
# --------------------------------------------------------------------------

def agreement(hz, tol=DEFAULT_AGREE_TOL_HZ):
    """Per time window, what fraction of the channels said the same thing.

    The free quality check `theta_channels.py` argues for, measured. Theta is
    globally coherent, so at any instant the column should agree; where it
    does not, either the fits are bad or the channels are not all in one
    structure.

    Against the column's MEDIAN rather than its mean, because a handful of
    channels sitting in white matter and reporting the argmax of a slope
    should not drag the thing every other channel is being compared to.

    A window where fewer than two channels have an answer returns NaN --
    one channel agrees with itself trivially, and drawing that as perfect
    agreement would make the emptiest part of a recording look like its most
    certain.
    """
    hz = np.asarray(hz, dtype=float)
    if hz.ndim != 2 or not hz.size:
        return np.zeros(0), np.zeros(0)
    n_ok = np.sum(np.isfinite(hz), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        med = np.nanmedian(hz, axis=0)
        near = np.abs(hz - med[None, :]) <= float(tol)
        frac = np.sum(near & np.isfinite(hz), axis=0) / np.maximum(n_ok, 1)
    frac = np.where(n_ok >= 2, frac, np.nan)
    return frac, med


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def _quantise(hz, lo, hi, step):
    """Snap to the middle of its swatch, so the map has nameable colours.

    Display only. The stored `hz` is never rounded -- see `recolor`, which
    re-steps a finished map without re-reading anything.
    """
    step = float(step or 0)
    if step <= 0:
        return hz
    k = np.floor((hz - lo) / step)
    out = lo + (k + 0.5) * step
    return np.clip(out, lo, hi)


def render_map(hz, margin, plan, cmap=None, colour_mode=None, bin_hz=None,
               centre=None):
    """The map: hue is the frequency, opacity is how clearly it won.

    Two facts about one cell, and a panel that drew only the first would say
    a coin toss and a certainty in the same colour. Every channel outside the
    layers that generate theta washes out; the layer carrying it glows. The
    laminar structure finds itself, with no threshold anybody has to defend.

    `margin` already means "how far clear the winner was, as a fraction of
    its own height" in both fidelities -- from the fit's runner-up in full
    mode, from the best bump more than `sep_hz` away in survey mode -- so the
    opacity means the same thing whichever produced it. Which one did is on
    the result, and on the card.
    """
    cmap = cmap or plan.get("cmap") or DEFAULT_CMAP
    mode = colour_mode or plan.get("colour_mode") or "absolute"
    step = plan.get("bin_hz") if bin_hz is None else bin_hz
    lo, hi = float(plan["f_lo"]), float(plan["f_hi"])

    m = np.asarray(hz, dtype=np.float64)
    if mode == "relative":
        # Faster or slower than this recording's own usual, which is what
        # makes a drift through the session legible -- an absolute map of a
        # recording that never leaves 7-8 Hz is one colour.
        c = centre if centre is not None else np.nanmedian(m)
        if not np.isfinite(c):
            c = 0.5 * (lo + hi)
        half = max(abs(lo - c), abs(hi - c)) or 1.0
        drawn = _quantise(m, lo, hi, step) - c
        clim = (-half, half)
    else:
        drawn = _quantise(m, lo, hi, step)
        clim = (lo, hi)

    uri = analysis._encode_image(drawn, cmap, clim, alpha=margin,
                                 floor=ALPHA_FLOOR)

    # The bar's swatches, from the same colormap and the same limits the
    # picture was drawn with. Sent rather than rebuilt in the browser so a
    # bar and a map cannot come to disagree about what 8 Hz looks like --
    # the rule §6c states for any fact two surfaces show.
    st = float(step or 0) or 1.0
    edges = np.arange(lo, hi + st * 0.5, st)
    centres = edges[:-1] + st / 2.0 if edges.size > 1 else np.array([lo])
    ref = (centres - (clim[0] + (centre if mode == "relative" and
                                 centre is not None else 0.0))
           if mode == "relative" else centres - clim[0])
    span = (clim[1] - clim[0]) or 1.0
    cols = analysis.get_cmap(cmap)(np.clip(ref / span, 0.0, 1.0), bytes=True)
    swatches = [{"hz": round(float(h), 3),
                 "css": "#%02x%02x%02x" % tuple(int(v) for v in c[:3])}
                for h, c in zip(centres, np.atleast_2d(cols))]

    return {
        "png": uri,
        "swatches": swatches,
        "t0": plan["t0"], "t1": plan["t1"],
        "f_lo": lo, "f_hi": hi,
        "theta": list(THETA_BAND),
        "bin_hz": float(step or 0),
        "cmap": cmap, "colour_mode": mode,
        "centre": (None if mode != "relative"
                   else float(centre if centre is not None
                              else np.nanmedian(m))),
        "clim": [float(clim[0]), float(clim[1])],
        "alpha_floor": ALPHA_FLOOR,
        "n_rows": int(m.shape[0]), "n_cols": int(m.shape[1]),
    }


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def _nlist(a):
    """A numpy row as JSON, with NaN as null rather than as the string NaN."""
    return [None if not np.isfinite(v) else round(float(v), 4)
            for v in np.asarray(a, dtype=float)]


def run(session, spec, job=None, on_preview=None, rec=None, sheet=None,
        have=None):
    """Every channel, into one map, filled in interlaced order.

    `have` is an optional callable `(row) -> None`, or the same five things
    `read_row` returns: `(times, hz, margin, above, extra)`. It is how banked
    answers will arrive -- a channel already worked out at these settings, by
    an earlier run of this or by Panorama on that channel, put straight into
    the map and never read again. Nothing passes it yet; the vault is not
    wired. It is here because the shape of the loop is what decides whether
    that is a small change later or a rewrite, and this shape makes it small.
    """
    plan = plan_for(session, spec, rec, sheet)
    rows = plan["rows"]
    n_row = len(rows)
    if not n_row:
        raise HorizonError("No channels were selected, so there is no map.")

    n_col = 0
    times = None
    hz = None
    margin = None
    above = None
    reused = np.zeros(n_row, dtype=bool)
    extras = [None] * n_row

    def ensure(n):
        nonlocal hz, margin, above, n_col
        if hz is not None:
            return
        n_col = int(n)
        hz = np.full((n_row, n_col), np.nan, dtype=np.float32)
        margin = np.full((n_row, n_col), np.nan, dtype=np.float32)
        above = np.full((n_row, n_col), np.nan, dtype=np.float32)

    def place(r, t, a, b, c, x=None):
        nonlocal times
        ensure(len(a))
        if times is None and t is not None:
            times = np.asarray(t, dtype=float)
        k = min(n_col, len(a))
        hz[r, :k] = np.asarray(a, dtype=float)[:k]
        margin[r, :k] = np.asarray(b, dtype=float)[:k]
        if c is not None:
            above[r, :k] = np.asarray(c, dtype=float)[:k]
        extras[r] = x or {}

    order = interlace(n_row)
    stage = stage_name(plan)
    per = max(1.0, float(plan["span_s"]))      # one channel's worth of units
    done = 0

    for r in order:
        if job:
            job.check()
        row = rows[r]
        got = have(row) if have else None
        if got is not None:
            t, a, b, c, x = got
            place(r, t, a, b, c, x)
            reused[r] = True
        else:
            t, a, b, c, x = read_row(session, row, plan, job=job)
            place(r, t, a, b, c, x)
        done += 1
        if job:
            job.tick(stage, int(done * per))
        # The picture, as it arrives. Every eighth row first, so the whole
        # depth extent is on screen coarsely after an eighth of the work.
        if on_preview and hz is not None:
            on_preview(render_map(hz, margin, plan), done, n_row)

    if hz is None:
        raise HorizonError(
            "Nothing could be read from any channel of this recording.")

    frac, med = agreement(hz, plan["agree_tol_hz"])
    drawn = render_map(hz, margin, plan)

    per_row = []
    for r, row in enumerate(rows):
        h = hz[r]
        ok = np.isfinite(h)
        per_row.append({
            "row": r, "index": row["index"], "number": row["number"],
            "label": row["label"], "depth_um": row["depth_um"],
            "region": row["region"],
            "reused": bool(reused[r]),
            "n_windows": int(ok.sum()),
            "modal_hz": (None if not ok.any()
                         else float(np.nanmedian(h[ok]))),
            "median_margin": (None if not np.isfinite(margin[r]).any()
                              else float(np.nanmedian(
                                  margin[r][np.isfinite(margin[r])]))),
            "n_nopeak": int((extras[r] or {}).get("n_nopeak") or 0),
            "line_removed": (extras[r] or {}).get("line_removed"),
            "aperiodic": (extras[r] or {}).get("aperiodic"),
        })

    result = {
        "ok": True,
        "plan": _plan_public(plan),
        "fidelity": plan["fidelity"],
        "engine": (panorama.fit_engine(spec) if plan["fidelity"] == "full"
                   else {"fitter": "specparam", "route": "survey",
                         "note": "one aperiodic fit per channel, on the "
                                 "mean spectrum; the argmax of every "
                                 "flattened column. Not a per-window fit."}),
        "map": drawn,
        "panes": plan["panes"],
        "rows": per_row,
        "times": _nlist(times if times is not None else []),
        "agreement": _nlist(frac),
        "median_hz": _nlist(med),
        "column_agreement": (None if not np.isfinite(frac).any()
                             else float(np.nanmean(frac[np.isfinite(frac)]))),
        "n_reused": int(reused.sum()),
        "n_read": int(n_row - reused.sum()),
    }
    _mats_put(cache_key(spec), {"hz": hz, "margin": margin, "above": above})
    return result


# --------------------------------------------------------------------------
# Re-rendering without re-measuring
# --------------------------------------------------------------------------
# The same split Panorama makes, for the same reason (`panorama.py`): the
# colormap, the step of the bar and absolute-against-relative are how the
# answer is shown, not what it is, so they stay out of the cache key and a
# change to any of them re-renders held arrays rather than reading a
# recording again.

_CACHE = {}
_ORDER = []
_MATS = {}


def cache_key(spec):
    import hashlib
    import json
    payload = {k: spec.get(k) for k in PARAM_KEYS}
    payload["channels"] = sorted(int(c) for c in (spec.get("channels") or []))
    payload["path"] = spec.get("path")
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def cache_get(key):
    return _CACHE.get(key)


def cache_put(key, value):
    _CACHE[key] = value
    if key in _ORDER:
        _ORDER.remove(key)
    _ORDER.append(key)
    while len(_ORDER) > CACHE_MAX:
        old = _ORDER.pop(0)
        _CACHE.pop(old, None)
        _MATS.pop(old, None)


def _mats_put(key, mats):
    _MATS[key] = mats


def mats_get(key):
    return _MATS.get(key)


def cache_clear():
    _CACHE.clear()
    _ORDER[:] = []
    _MATS.clear()


def recolor(out, mats, cmap=None, colour_mode=None, bin_hz=None):
    """Re-draw a finished map. No recording is read."""
    if not mats or "hz" not in mats:
        raise HorizonError(
            "The numbers behind this map are no longer held, so it cannot "
            "be re-coloured without running it again.")
    plan = dict(out.get("plan") or {})
    if cmap:
        plan["cmap"] = cmap
    if colour_mode:
        plan["colour_mode"] = colour_mode
    if bin_hz is not None:
        plan["bin_hz"] = float(bin_hz)
    out["map"] = render_map(mats["hz"], mats["margin"], plan)
    out["plan"] = plan
    return out


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------

def _png_bytes(data_uri):
    import base64
    return base64.b64decode(str(data_uri).split(",", 1)[-1])


def figure(result, title=None):
    """The map, its agreement strip and its depth profile, as one PNG.

    The map is drawn from the picture the run already produced rather than
    re-rendered -- same colour limits, same opacity, same quantisation. A
    figure that quietly differs from what somebody looked at before pressing
    Save is worse than no figure. (Panorama's `figure` says the same thing
    for the same reason.)
    """
    import io as _io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.image import imread

    from . import export

    plan = result.get("plan") or {}
    drawn = result.get("map") or {}
    rows = result.get("rows") or []
    t0, t1 = float(plan.get("t0") or 0.0), float(plan.get("t1") or 1.0)
    lo, hi = float(plan.get("f_lo") or 2.0), float(plan.get("f_hi") or 14.0)

    fig = plt.figure(figsize=(12.5, 7.4), dpi=160)
    gs = fig.add_gridspec(2, 2, width_ratios=[4.2, 1.0],
                          height_ratios=[3.4, 1.0], hspace=0.28, wspace=0.16)

    # -- the map ----------------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    img = imread(_io.BytesIO(_png_bytes(drawn.get("png"))))
    ax.imshow(img, aspect="auto", interpolation="nearest",
              extent=[t0, t1, len(rows) - 0.5, -0.5])
    ax.set_ylabel("channel (depth order)", color=export.INK)
    ax.set_title(title or "Horizon", color=export.INK, loc="left")
    # Pane boundaries, so a probe drawn as several columns says where one
    # ends -- a continuous picture across a break would be inviting exactly
    # the depth reading the split exists to prevent.
    for pane in (result.get("panes") or [])[1:]:
        ax.axhline(pane["row0"] - 0.5, color=export.INK, lw=1.1, alpha=0.8)
    step = max(1, len(rows) // 16)
    ax.set_yticks(range(0, len(rows), step))
    ax.set_yticklabels([rows[i].get("label") or "" for i in
                        range(0, len(rows), step)], fontsize=7)
    ax.tick_params(colors=export.INK, labelsize=8)

    # -- the colour bar, stepped the way the map is ------------------------
    cax = fig.add_subplot(gs[0, 1])
    bin_hz = float(drawn.get("bin_hz") or 0) or 1.0
    edges = np.arange(lo, hi + bin_hz, bin_hz)
    centres = edges[:-1] + bin_hz / 2.0
    cax.imshow(centres[::-1, None], aspect="auto",
               cmap=analysis.get_cmap(drawn.get("cmap") or DEFAULT_CMAP),
               vmin=drawn.get("clim", [lo, hi])[0],
               vmax=drawn.get("clim", [lo, hi])[1],
               extent=[0, 1, lo, hi], interpolation="nearest")
    cax.set_xticks([])
    cax.yaxis.tick_right()
    cax.set_ylabel("dominant frequency (Hz)", color=export.INK)
    cax.yaxis.set_label_position("right")
    th = plan.get("theta") or list(THETA_BAND)
    for edge in th:
        cax.axhline(edge, color=export.INK, lw=1.4)
    cax.tick_params(colors=export.INK, labelsize=8)

    # -- how much the column agreed with itself ----------------------------
    axa = fig.add_subplot(gs[1, 0], sharex=ax)
    times = [v for v in (result.get("times") or [])]
    agree = [np.nan if v is None else v for v in (result.get("agreement") or [])]
    n = min(len(times), len(agree))
    if n:
        axa.plot(times[:n], agree[:n], lw=1.2, color=export.INK)
        axa.fill_between(times[:n], 0, agree[:n], alpha=0.18, color=export.INK)
    axa.set_ylim(0, 1.02)
    axa.set_xlim(t0, t1)
    axa.set_ylabel("agreement", color=export.INK)
    axa.set_xlabel("time (s)", color=export.INK)
    axa.tick_params(colors=export.INK, labelsize=8)

    # -- the depth profile: each channel's own median ----------------------
    axd = fig.add_subplot(gs[1, 1])
    mh = [r.get("modal_hz") for r in rows]
    ys = [i for i, v in enumerate(mh) if v is not None]
    xs = [mh[i] for i in ys]
    if xs:
        axd.plot(xs, ys, marker="o", ms=2.4, lw=0.9, color=export.INK)
    axd.set_xlim(lo, hi)
    axd.invert_yaxis()
    axd.set_xlabel("median Hz", color=export.INK)
    axd.tick_params(colors=export.INK, labelsize=8)

    buf = _io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def tables(result):
    """The numbers behind the picture, as CSV rows.

    Two tables, because they answer different questions: one row per channel
    is the depth profile, one row per time window is the trend. The map
    itself -- every cell -- is deliberately not written out: 64 by 360 is a
    picture, not a table, and the two tables are what a statistic is made
    from.
    """
    rows = result.get("rows") or []
    prof = [["row", "channel", "csc", "depth_um", "region", "n_windows",
             "median_hz", "median_margin", "n_nopeak", "reused"]]
    for r in rows:
        prof.append([r.get("row"), r.get("label"), r.get("number"),
                     r.get("depth_um"), r.get("region"), r.get("n_windows"),
                     r.get("modal_hz"), r.get("median_margin"),
                     r.get("n_nopeak"), int(bool(r.get("reused")))])

    times = result.get("times") or []
    agree = result.get("agreement") or []
    med = result.get("median_hz") or []
    trend = [["t_s", "median_hz_across_channels", "agreement"]]
    for i, t in enumerate(times):
        trend.append([t,
                      med[i] if i < len(med) else None,
                      agree[i] if i < len(agree) else None])
    return {"profile": prof, "trend": trend}
