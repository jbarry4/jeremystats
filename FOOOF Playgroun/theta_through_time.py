"""
theta_through_time.py -- where in a recording theta is high, for one channel.

THE QUESTION
------------
"High theta" here means: at this moment, 4-12 Hz is strong FOR THIS CHANNEL
IN THIS RECORDING. So every number below is scored against the same channel's
own distribution over the whole session. Nothing is compared to an absolute
microvolt value or to another channel.

HOW A BAND BECOMES ONE LINE
---------------------------
A spectrogram is just a power spectrum per time window: power at every
frequency, at every moment -- a surface. "Theta power" collapses one axis of
it. For each time window, take the bins between 4 and 12 Hz and reduce them
to a single number.

There are two ways to reduce, and they give the SAME PICTURE:

    INTEGRATE   sum(P) * df   -> band power,      uV^2
    AVERAGE     mean(P)       -> mean density,    uV^2/Hz

They differ by exactly the bandwidth (8 Hz), which is a constant, so the line
has an identical shape either way and only the y-axis label changes. This
script integrates, because "how much theta" is a quantity of power rather
than a density. That is the whole of "break it down by Hz and average".

What collapsing throws away is WHICH theta: a 6 Hz rhythm and an 11 Hz rhythm
of equal size produce the same number. That is the point `cfc.band_power`
makes about a single 4-12 Hz bandpass, so the spectrogram and the peak
frequency are both plotted alongside the line.

WHY FOUR MEASURES AND NOT ONE
-----------------------------
Power in a band is not the strength of an oscillation. That is the entire
argument of Donoghue et al. (2020): 4-12 Hz power rises when a theta rhythm
gets stronger, and it ALSO rises when the aperiodic 1/f component shifts up
or steepens with no rhythm involved. Both look like "high theta" in a band
power trace, so the trace alone cannot tell you which happened.

    abs    integrated 4-12 power. Simplest. Confounded by the slope.
    rel    theta / total (1-100). Cancels a broadband offset shift, but
           still moves when the exponent changes, and it also falls when
           something unrelated (gamma, an artifact) adds power elsewhere.
    ratio  theta / delta. The classic hippocampal theta index used for REM
           and running detection. Both bands are local, so a broadband
           change largely divides out.
    osc    mean height of the measured spectrum ABOVE the fitted aperiodic
           component across 4-12, from a per-window FOOOF fit. This is the
           one that answers "is there more rhythm", and it is the current
           standard. Costs a model fit per window.

They are plotted together, z-scored, so you can see where they agree -- and
where they do not, which is exactly where the aperiodic confound is doing
something and the simple traces would have misled you.

Run:
  python theta_through_time.py
  python theta_through_time.py --channel CSC7 --measure ratio --z 1.5
  python theta_through_time.py --no-fooof --save theta.png --csv theta.csv
"""

import argparse
import csv as csvmod
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import spectrogram

# The lab's own readers -- same ADBitVolts scaling and polarity as the rest of
# the pipeline, the same anti-aliased decimation as cfc/spectrum.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "BARRY GUI", "backend"))
import nlx           # noqa: E402
import cfc           # noqa: E402

FOLDER = r"D:/PTEN/PTEN/M1_Pten/M1ptens2oct2/2023-10-02_16-58-03"

# Bands, taken from backend/spectrum.py so a number here means the same thing
# a number there does.
DELTA = (1.0, 4.0)
THETA = (4.0, 12.0)
TOTAL = (1.0, 100.0)
# Where a theta peak is allowed to be centred. Narrower than the band itself,
# so a Gaussian offered "theta" cannot sit on the shoulder of the delta slope
# and call 3 Hz a theta rhythm. spectrum.FIT_BANDS' own numbers.
THETA_CF = (5.0, 9.5)

# Theta split into narrow lines, so "how much theta" can be asked one hertz at
# a time. The centres are what gets plotted; the edges are the midpoints
# between them, so the lines tile the band without overlapping and their
# powers sum to roughly the total.
SUB_CENTERS = [4.0, 6.0, 8.0, 10.0, 12.0]

# For naming whatever the strongest rhythm turns out to be. Non-overlapping on
# purpose -- alpha is left out because it sits inside theta's upper half here
# and a frequency that returns two names is not an answer.
NAMED_BANDS = [("delta", 0.0, 4.0), ("theta", 4.0, 12.0), ("beta", 12.0, 30.0),
               ("low gamma", 30.0, 60.0), ("high gamma", 60.0, 1e9)]


def sub_bands(centers):
    """Centres -> (name, lo, hi) tiles, edges midway between neighbours."""
    c = sorted(float(v) for v in centers)
    out = []
    for i, f in enumerate(c):
        lo = (c[i - 1] + f) / 2.0 if i else f - (c[1] - c[0]) / 2.0
        hi = (c[i + 1] + f) / 2.0 if i + 1 < len(c) else f + (f - c[-2]) / 2.0
        out.append(("%g Hz" % f, max(0.1, lo), hi))
    return out


def band_of(f):
    """Which named band a frequency falls in. NaN means no rhythm was found."""
    if not np.isfinite(f):
        return "none"
    for name, lo, hi in NAMED_BANDS:
        if lo <= f < hi:
            return name
    return "-"

# Everything above this is noise for this question. decimate_to keeps a
# margin over Nyquist so the anti-alias shoulder stays outside the band.
FMAX = 100.0
TARGET_FS = 250.0

# Mains, and how far either side of it gets bridged.
LINE_HZ = 60.0
LINE_HALF_BW = 2.0

# Read the recording this much at a time, discarding this much at each chunk
# edge: a zero-phase decimation filter rings for a filter length either side,
# and averaging that in would be averaging in the filter. spectrum.py's
# constants, for the same reason.
CHUNK_SECONDS = 120.0
EDGE_SECONDS = 0.5


# --------------------------------------------------------------------------
# 1. The signal
# --------------------------------------------------------------------------
def load_channel(path, target_fs=TARGET_FS, verbose=True):
    """Whole channel, decimated, as (x, fs, duration).

    Read in chunks so a 28-minute 30 kHz channel never sits in memory at full
    rate. Where the recording has a gap the samples were never written, so the
    hole is filled with NaN rather than closed up: closing it would label
    every later sample with a time earlier than its true one, which is the
    failure mode nlx.segment_ncs exists to document.
    """
    seg = nlx.segment_ncs(path)
    fs_raw = seg["fs"]
    dur = seg["true_duration_s"]
    if verbose:
        print("%s  fs=%.0f Hz  %.1f s  (%.1f min)"
              % (os.path.basename(path), fs_raw, dur, dur / 60.0))
        if seg["n_segments"] > 1:
            print("  WARNING: %d segments, %.2f s never recorded "
                  "(%d pauses, %d dropouts) -- filled with NaN, those windows "
                  "are dropped" % (seg["n_segments"], seg["seconds_lost"],
                                   seg["n_pauses"], seg["n_dropouts"]))

    pieces = []
    fs_out = None
    t = 0.0
    while t < dur:
        span = min(CHUNK_SECONDS, dur - t)
        a = max(0.0, t - EDGE_SECONDS)
        b = min(dur, t + span + EDGE_SECONDS)
        raw, t_actual, fs = nlx.read_ncs_range(path, a, b)
        want = int(round(span * target_fs))
        if raw.size == 0:
            pieces.append(np.full(want, np.nan))
            t += span
            continue
        y, fs_d, _ = cfc.decimate_to(raw, fs, target_fs)
        fs_out = fs_d
        lead = max(0, int(round((t - t_actual) * fs_d)))
        y = y[lead:lead + want]
        if y.size < want:                      # short: a gap inside the chunk
            y = np.concatenate([y, np.full(want - y.size, np.nan)])
        pieces.append(y)
        t += span

    x = np.concatenate(pieces) if pieces else np.empty(0)
    fs_out = fs_out or target_fs
    if verbose:
        print("  decimated to %.1f Hz -> %d samples (%.1f%% NaN)"
              % (fs_out, x.size, 100.0 * np.isnan(x).mean() if x.size else 0.0))
    return x, fs_out, dur


# --------------------------------------------------------------------------
# 2. The surface: power per frequency, per moment
# --------------------------------------------------------------------------
def make_spectrogram(x, fs, sub_s, win_s, step_s, line_hz=LINE_HZ):
    """(freqs, times, Pxx, n_avg) in uV^2/Hz, mains bridged.

    EACH COLUMN IS A WELCH AVERAGE, NOT ONE PERIODOGRAM. This matters more
    than it sounds. A single FFT of a noise-like signal is a chi-square with
    two degrees of freedom: its standard deviation equals its mean, so the
    per-bin scatter in log power is about 0.4 log units -- comparable to the
    entire height of a theta peak. Band power survives that, because summing
    8 Hz of bins averages most of it away. A MODEL FIT DOES NOT: FOOOF sees
    that scatter as structure, and the fitted exponent then jumps around
    window to window with nothing behind it. Fitting per-column periodograms
    here gave a median R^2 of 0.45 and an exponent ranging -0.3 to 2.9.

    So the spectrum for each moment is the average of the sub-windows inside
    `win_s`, which is Welch's method with the averaging made explicit:

        sub_s   FFT length -> frequency resolution is 1/sub_s
        win_s   how much time is averaged -> n_avg sub-windows
        step_s  hop between output columns

    Scatter falls as 1/sqrt(n_avg). The cost is time resolution: the answer
    at time t is really the average over win_s around t, so win_s should be
    shorter than the bouts being looked for.
    """
    nperseg = int(round(sub_s * fs))
    noverlap = nperseg - int(round(step_s * fs))
    freqs, times, pxx = spectrogram(
        x, fs=fs, window="hann", nperseg=nperseg, noverlap=noverlap,
        scaling="density", mode="psd")

    # Average the sub-windows covering win_s. A plain moving average over the
    # columns: they are already spaced step_s apart and overlap by design.
    n_avg = max(1, int(round((win_s - sub_s) / step_s)) + 1)
    if n_avg > 1 and pxx.shape[1] > n_avg:
        from numpy.lib.stride_tricks import sliding_window_view
        pxx = sliding_window_view(pxx, n_avg, axis=1).mean(axis=2)
        times = sliding_window_view(times, n_avg).mean(axis=1)

    keep = freqs <= FMAX
    freqs, pxx = freqs[keep], pxx[keep]

    # Bridge the mains and its harmonics in log power, from the edges inward.
    # Left alone, a 60 Hz spike sits inside the total-power denominator and
    # would be fitted as a very tall very narrow rhythm.
    if line_hz:
        mask = np.zeros(freqs.shape, dtype=bool)
        k = 1
        while k * line_hz <= freqs[-1]:
            mask |= np.abs(freqs - k * line_hz) <= LINE_HALF_BW
            k += 1
        if mask.any() and (~mask).sum() > 2:
            lp = np.log10(pxx)
            for j in range(lp.shape[1]):
                lp[mask, j] = np.interp(freqs[mask], freqs[~mask], lp[~mask, j])
            pxx = 10.0 ** lp

    return freqs, times, pxx, n_avg


def band_integral(freqs, pxx, lo, hi):
    """Integrated power in [lo, hi], uV^2 -- sum of the bins times bin width."""
    sel = (freqs >= lo) & (freqs <= hi)
    return np.trapezoid(pxx[sel], freqs[sel], axis=0)


def dominant_simple(freqs, pxx, fit_range, theta=THETA):
    """Dominant frequencies without FOOOF: flatten with a straight line.

    A crude stand-in for the aperiodic fit, for --no-fooof. The spectrum is
    nearly straight in log-log, so a least-squares line through it removes
    most of the 1/f and what stands above the line is what stands above the
    background. It is worse than FOOOF -- the line is pulled up by the very
    peaks it is meant to sit under, which flattens them -- but it is honest
    about which frequency is highest, and it costs nothing.
    """
    sel = (freqs >= fit_range[0]) & (freqs <= fit_range[1]) & (freqs > 0)
    f = freqs[sel]
    lf = np.log10(f)
    lp = np.log10(np.where(pxx[sel] > 0, pxx[sel], np.nan))
    # One line per window, solved for all windows at once.
    A = np.vstack([lf, np.ones_like(lf)]).T
    good = np.isfinite(lp).all(axis=0)
    flat = np.full(lp.shape, np.nan)
    if good.any():
        coef, *_ = np.linalg.lstsq(A, lp[:, good], rcond=None)
        flat[:, good] = lp[:, good] - A @ coef

    n = pxx.shape[1]
    dom_theta = np.full(n, np.nan)
    dom_all = np.full(n, np.nan)
    tb = (f >= theta[0]) & (f <= theta[1])
    interior = (f >= f[0] + 1.0) & (f <= f[-1] - 1.0)
    for w in np.flatnonzero(good):
        dom_theta[w] = f[tb][np.nanargmax(flat[tb, w])]
        dom_all[w] = f[interior][np.nanargmax(flat[interior, w])]
    return dom_theta, dom_all


# --------------------------------------------------------------------------
# 3. The aperiodic-adjusted measure
# --------------------------------------------------------------------------
def fooof_theta(freqs, pxx, fit_range, aperiodic_mode, n_jobs=1, verbose=True):
    """Per-window FOOOF fit -> (osc, exponent, offset, cf, pw, r2).

    `osc` is the mean height of the measured spectrum above the fitted
    aperiodic component across theta, in log10 units. Taken over the whole
    band rather than from a detected peak on purpose: peak detection is a
    cliff -- a window either has a peak or it does not -- and a trace that
    drops to zero whenever the fit declined to place a Gaussian is not a
    trace of how much theta there is. `cf`/`pw` report the discrete peak
    separately, for the windows that have one.
    """
    from fooof import FOOOFGroup
    from fooof.sim.gen import gen_aperiodic

    n_win = pxx.shape[1]
    ok = np.isfinite(pxx).all(axis=0) & (pxx > 0).all(axis=0)
    if verbose:
        print("  fitting %d of %d windows over %g-%g Hz (%s)"
              % (ok.sum(), n_win, fit_range[0], fit_range[1], aperiodic_mode))

    out = {k: np.full(n_win, np.nan) for k in
           ("osc", "exponent", "offset", "cf", "pw", "r2",
            "dom_theta", "dom_all", "dom_all_pw")}
    if not ok.any():
        return out

    fg = FOOOFGroup(peak_width_limits=[1.0, 12.0], max_n_peaks=6,
                    min_peak_height=0.05, aperiodic_mode=aperiodic_mode,
                    verbose=False)
    fg.fit(freqs, pxx[:, ok].T, fit_range, n_jobs=n_jobs)

    ap = fg.get_params("aperiodic_params")
    theta_bins = (fg.freqs >= THETA[0]) & (fg.freqs <= THETA[1])
    log_spectra = fg.power_spectra                      # already log10
    idx = np.flatnonzero(ok)

    # The dominant frequency has to be read off the FLATTENED spectrum, never
    # the measured one. On the measured spectrum the strongest frequency is
    # always the lowest frequency, because 1/f says so -- ask a raw LFP
    # spectrum what its peak is and it answers "1 Hz" for every window of
    # every recording, which is true and useless. Subtracting the aperiodic
    # fit first turns the question into "which frequency stands highest above
    # its own background", which is the one that was meant.
    r2_all = fg.get_params("r_squared")

    for i, w in enumerate(idx):
        ap_curve = gen_aperiodic(fg.freqs, ap[i])
        flat = log_spectra[i] - ap_curve
        out["osc"][w] = np.mean(flat[theta_bins])
        out["offset"][w] = ap[i][0]
        out["exponent"][w] = ap[i][-1]
        out["r2"][w] = r2_all[i]
        out["dom_theta"][w] = fg.freqs[theta_bins][np.argmax(flat[theta_bins])]

    # The two dominant-frequency questions want two different answers, and
    # the difference is whether the question presupposes a rhythm.
    #
    #   dom_theta, above, is the argmax of the flattened spectrum inside
    #   4-12. It always returns something, and it should: "given that we are
    #   looking at theta, where in it does the power sit" is a fair question
    #   even in a window with no theta rhythm at all.
    #
    #   dom_all is the FITTED peak instead. An argmax over the whole range
    #   would always return something too, and there it would be wrong --
    #   the flattened spectrum is noisy, and the largest of ~90 noisy bins
    #   sits 0.4-0.7 log units above zero in a window containing nothing.
    #   Read as a dominant frequency that is a rhythm every second of every
    #   recording, most of them invented. FOOOF has already decided which
    #   bumps clear the noise (peak_threshold, in SDs of the flattened fit),
    #   so the tallest peak it actually placed is the honest answer, and NO
    #   PEAK is an answer this has to be able to give.
    peaks = fg.get_params("peak_params")                # [CF, PW, BW, run]
    if peaks.size:
        peaks = np.atleast_2d(peaks)
        in_theta = ((peaks[:, 0] >= THETA_CF[0]) & (peaks[:, 0] <= THETA_CF[1]))
        for cf, pw, _bw, run in peaks[in_theta]:
            w = idx[int(run)]
            if np.isnan(out["pw"][w]) or pw > out["pw"][w]:
                out["cf"][w], out["pw"][w] = cf, pw
        for cf, pw, _bw, run in peaks:
            w = idx[int(run)]
            if np.isnan(out["dom_all_pw"][w]) or pw > out["dom_all_pw"][w]:
                out["dom_all"][w], out["dom_all_pw"][w] = cf, pw
    n_none = int(np.isnan(out["dom_all"][ok]).sum())
    if verbose and n_none:
        print("  no peak of any kind in %d of %d windows (%.0f%%) -- those "
              "have no dominant rhythm" % (n_none, int(ok.sum()),
                                           100.0 * n_none / ok.sum()))
    return out


# --------------------------------------------------------------------------
# 4. "Relative to the recording"
# --------------------------------------------------------------------------
def robust_z(v):
    """Score against this channel's own distribution, median/MAD.

    Median and MAD rather than mean and SD because a handful of artifact
    windows -- a cable knock, a chewing bout -- inflate an SD enough to hide
    every real theta bout underneath the threshold. Falls back to SD if the
    MAD is zero, which happens when more than half the windows are identical.
    """
    v = np.asarray(v, dtype=float)
    good = np.isfinite(v)
    if good.sum() < 2:
        return np.full(v.shape, np.nan)
    med = np.median(v[good])
    mad = np.median(np.abs(v[good] - med)) * 1.4826
    scale = mad if mad > 0 else np.std(v[good])
    if not scale:
        return np.zeros(v.shape)
    z = (v - med) / scale
    z[~good] = np.nan
    return z


def find_epochs(times, z, thresh, min_dur, merge_gap):
    """Contiguous stretches above threshold, short gaps bridged."""
    hot = np.nan_to_num(z, nan=-np.inf) >= thresh
    if not hot.any():
        return []
    edges = np.diff(hot.astype(int))
    starts = list(np.flatnonzero(edges == 1) + 1)
    stops = list(np.flatnonzero(edges == -1) + 1)
    if hot[0]:
        starts.insert(0, 0)
    if hot[-1]:
        stops.append(len(hot))

    runs = []
    for a, b in zip(starts, stops):
        if runs and times[a] - times[runs[-1][1] - 1] <= merge_gap:
            runs[-1] = (runs[-1][0], b)
        else:
            runs.append((a, b))

    out = []
    for a, b in runs:
        t0, t1 = times[a], times[b - 1]
        if t1 - t0 < min_dur:
            continue
        seg = z[a:b]
        out.append({"i0": a, "i1": b, "t0": t0, "t1": t1, "dur": t1 - t0,
                    "z_mean": float(np.nanmean(seg)),
                    "z_max": float(np.nanmax(seg)),
                    "t_peak": float(times[a + int(np.nanargmax(seg))])})
    return out


# --------------------------------------------------------------------------
# 5. The picture
# --------------------------------------------------------------------------
def whole_recording(freqs, pxx, epochs, fit_range, mode, verbose=True):
    """The recording collapsed the OTHER way: one spectrum for the lot.

    Everything else here collapses frequency and keeps time. This keeps
    frequency and collapses time, which is the view that says what kind of
    signal this channel carries at all -- and it is the honest place to read
    an aperiodic exponent, because it is averaged over 1700 windows instead
    of estimated from eight seconds.

    Welch's method is already an average of periodograms, so averaging the
    spectrogram's columns IS the whole-recording Welch spectrum; there is
    nothing extra to compute. Split into epochs and rest as well, because a
    theta bump that only exists in 7% of the recording is nearly invisible
    in the average over all of it.
    """
    n = pxx.shape[1]
    mask = np.zeros(n, dtype=bool)
    for e in epochs:
        mask[e["i0"]:e["i1"]] = True

    out = {"all": np.nanmean(pxx, axis=1),
           "p10": np.nanpercentile(pxx, 10, axis=1),
           "p90": np.nanpercentile(pxx, 90, axis=1)}
    if mask.any():
        out["epochs"] = np.nanmean(pxx[:, mask], axis=1)
    if (~mask).any():
        out["rest"] = np.nanmean(pxx[:, ~mask], axis=1)

    out["fits"] = {}
    if mode:
        from fooof import FOOOF
        from fooof.sim.gen import gen_aperiodic
        for key in ("all", "epochs", "rest"):
            if key not in out:
                continue
            fm = FOOOF(peak_width_limits=[1.0, 12.0], max_n_peaks=6,
                       min_peak_height=0.05, aperiodic_mode=mode,
                       verbose=False)
            fm.fit(freqs, out[key], fit_range)
            out["fits"][key] = {
                "freqs": fm.freqs,
                "aperiodic": 10.0 ** gen_aperiodic(fm.freqs,
                                                   fm.aperiodic_params_),
                "params": fm.aperiodic_params_,
                "peaks": np.atleast_2d(fm.peak_params_) if fm.n_peaks_ else
                         np.empty((0, 3)),
                "r2": fm.r_squared_,
            }
    if verbose:
        print_whole(out, fit_range, mode)
    return out


def print_whole(summary, fit_range, mode):
    """The whole-recording fit, in the report rather than only on the plot."""
    if not summary.get("fits"):
        return
    print("\n  WHOLE-RECORDING SPECTRUM (%s, %g-%g Hz) -- one fit over all "
          "%s" % (mode, fit_range[0], fit_range[1], "windows"))
    print("    %-8s %9s %8s %7s   %s"
          % ("", "exponent", "offset", "R^2", "peaks, tallest first"))
    for key, lab in (("all", "whole"), ("epochs", "epochs"),
                     ("rest", "rest")):
        f = summary["fits"].get(key)
        if not f:
            continue
        pk = f["peaks"]
        txt = ", ".join("%.2f Hz (%.2f)" % (c, p)
                        for c, p, _b in pk[np.argsort(-pk[:, 1])][:4]) \
            if len(pk) else "none"
        print("    %-8s %9.2f %8.2f %7.3f   %s"
              % (lab, f["params"][-1], f["params"][0], f["r2"], txt))


def plot_all(freqs, times, pxx, m, z, sub, sub_z, tiles, epochs, args, title,
             summary):
    have_fooof = np.isfinite(m["osc"]).any()
    n_time = 7 if have_fooof else 5
    fig = plt.figure(figsize=(13, 2.3 * n_time + 4.5))
    gs = fig.add_gridspec(n_time + 1, 2, height_ratios=[1] * n_time + [1.9],
                          hspace=0.75, wspace=0.2,
                          left=0.07, right=0.94, top=0.975, bottom=0.05)
    axes = [fig.add_subplot(gs[0, :])]
    axes += [fig.add_subplot(gs[i, :], sharex=axes[0])
             for i in range(1, n_time)]
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    tmin = times / 60.0
    cols = plt.cm.viridis(np.linspace(0.05, 0.9, len(tiles)))

    # -- the surface itself, so every line below can be checked against it
    ax = axes[0]
    show = freqs <= 30
    ax.pcolormesh(tmin, freqs[show], np.log10(pxx[show]),
                  shading="nearest", cmap="magma")
    ax.axhline(THETA[0], color="w", lw=0.7, ls=":")
    ax.axhline(THETA[1], color="w", lw=0.7, ls=":")
    ax.set_ylabel("Hz")
    ax.set_title(title + "\nspectrogram, log10 power; dotted = theta band")

    # -- theta one hertz at a time, in real units
    ax = axes[1]
    for (name, lo, hi), c in zip(tiles, cols):
        ax.plot(tmin, np.log10(sub[name]), lw=0.8, color=c,
                label="%s (%.1f-%.1f)" % (name, lo, hi))
    ax.plot(tmin, np.log10(m["abs"]), lw=1.4, color="k",
            label="total %g-%g" % THETA)
    ax.set_ylabel("log10 power\n($\\mu V^2$)")
    ax.legend(loc="upper right", fontsize=7, ncol=6)
    ax.set_title("theta split into narrow lines. They are stacked by 1/f -- "
                 "the 4 Hz line sits above the 12 Hz line all recording, "
                 "which is the slope, not a rhythm")

    # -- the same lines with the slope taken out, which is the readable one
    ax = axes[2]
    for (name, _lo, _hi), c in zip(tiles, cols):
        ax.plot(tmin, sub_z[name], lw=0.9, color=c, label=name)
    ax.axhline(args.z, color="k", ls="--", lw=0.8)
    ax.set_ylabel("robust z\n(each vs itself)")
    ax.legend(loc="upper right", fontsize=7, ncol=6)
    ax.set_title("each line scored against its OWN distribution, so they are "
                 "comparable: whichever is highest is where theta sat")

    # -- every measure on one scale, which is the comparison
    ax = axes[3]
    for key, lab, col in (("abs", "absolute", "#888888"),
                          ("rel", "relative (/total)", "#1f77b4"),
                          ("ratio", "theta/delta", "#2ca02c"),
                          ("osc", "above aperiodic (FOOOF)", "#d62728")):
        if np.isfinite(z[key]).any():
            ax.plot(tmin, z[key], lw=1.0, color=col, label=lab,
                    alpha=0.9 if key == args.measure else 0.45)
    ax.axhline(args.z, color="k", ls="--", lw=0.8)
    ax.set_ylabel("robust z\n(vs whole recording)")
    ax.legend(loc="upper right", fontsize=8, ncol=4)
    ax.set_title("each measure scored against its own distribution; "
                 "bold = --measure %s, dashed = threshold" % args.measure)

    # -- where in theta the power sat, and what the loudest rhythm was
    ax = axes[4]
    ax.plot(tmin, m["dom_all"], ".", ms=2.2, color="#9467bd",
            label="loudest overall")
    ax.plot(tmin, m["dom_theta"], ".", ms=2.2, color="#17becf",
            label="loudest within theta")
    ax.axhspan(THETA[0], THETA[1], color="#17becf", alpha=0.10, lw=0)
    ax.set_yscale("log")
    ax.set_yticks([2, 4, 6, 8, 12, 20, 30, 45])
    ax.get_yaxis().set_major_formatter(plt.ScalarFormatter())
    # Without this the log axis keeps labelling its minor ticks too, and the
    # band edges end up reading "3 x 10^0" next to "12".
    ax.get_yaxis().set_minor_formatter(plt.NullFormatter())
    ax.set_ylim(args.fit_lo, args.fit_hi)
    ax.set_ylabel("Hz")
    ax.legend(loc="upper right", fontsize=7, ncol=2, markerscale=3)
    ax.set_title("dominant frequency, read off the spectrum with the 1/f "
                 "removed. Shaded = theta; purple outside it means the "
                 "loudest rhythm was not theta")

    if have_fooof:
        # -- the confound, drawn directly
        ax = axes[5]
        ax.plot(tmin, m["exponent"], color="#9467bd", lw=0.9)
        ax.set_ylabel("aperiodic\nexponent")
        ax2 = ax.twinx()
        ax2.plot(tmin, m["offset"], color="#ff7f0e", lw=0.9, alpha=0.6)
        ax2.set_ylabel("offset", color="#ff7f0e")
        ax.set_title("the 1/f component -- where this moves, absolute band "
                     "power moves with it for no rhythmic reason")

        # -- which theta, not just how much
        ax = axes[6]
        ax.plot(tmin, m["cf"], ".", ms=2.5, color="#17becf")
        ax.set_ylim(THETA[0], THETA[1])
        ax.set_ylabel("theta peak\nfreq (Hz)")
        ax.set_title("centre frequency of the FITTED theta peak -- blank "
                     "means the model declined to place one, i.e. no "
                     "resolvable theta rhythm in that window")

    for ax in axes:
        for ep in epochs:
            ax.axvspan(ep["t0"] / 60.0, ep["t1"] / 60.0, color="cyan",
                       alpha=0.15, lw=0)
    axes[-1].set_xlabel("time (min)")

    # ================= holistic: time collapsed away ====================
    # 1. one spectrum for the whole recording
    ax = fig.add_subplot(gs[n_time, 0])
    ax.fill_between(freqs, summary["p10"], summary["p90"], color="#cccccc",
                    alpha=0.6, lw=0, label="10-90% of windows")
    for key, lab, col, lw in (("all", "whole recording", "k", 1.8),
                              ("rest", "outside epochs", "#1f77b4", 1.2),
                              ("epochs", "inside epochs", "#d62728", 1.6)):
        if key in summary:
            ax.plot(freqs, summary[key], color=col, lw=lw, label=lab)
    f = summary["fits"].get("all")
    if f is not None:
        ax.plot(f["freqs"], f["aperiodic"], color="#2ca02c", ls="--", lw=1.3,
                label="aperiodic fit (exp %.2f)" % f["params"][-1])
    ax.axvspan(THETA[0], THETA[1], color="#17becf", alpha=0.12, lw=0)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1, FMAX)
    ax.set_xticks([1, 2, 4, 8, 12, 20, 40, 60, 100])
    ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("power ($\\mu V^2$/Hz)")
    ax.legend(fontsize=7, loc="lower left")
    ax.set_title("power spectrum of the entire recording\n"
                 "(shaded band = theta; the bump only shows in the red curve)",
                 fontsize=9.5)

    # 2. how often each frequency was the loudest thing in the signal
    ax = fig.add_subplot(gs[n_time, 1])
    da = m["dom_all"]
    fin = np.isfinite(da)
    if fin.any():
        # Log-spaced bins. On linear bins a log-spaced axis makes the high
        # frequencies look like a forest of thin spikes and the low ones like
        # one fat bar, purely from bin width.
        bins = np.logspace(np.log10(max(1.0, args.fit_lo)),
                           np.log10(args.fit_hi), 48)
        ax.hist(da[fin], bins=bins, color="#9467bd", alpha=0.75,
                label="all windows (n=%d)" % fin.sum())
        ine = np.zeros(len(da), dtype=bool)
        for e in epochs:
            ine[e["i0"]:e["i1"]] = True
        if (ine & fin).any():
            ax.hist(da[ine & fin], bins=bins, histtype="step", lw=1.8,
                    color="#d62728",
                    label="inside epochs (n=%d)" % (ine & fin).sum())
        ax.set_xscale("log")
        ax.set_xticks([2, 4, 6, 8, 12, 20, 30, 45])
        ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
        ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
        ax.set_xlim(args.fit_lo, args.fit_hi)
        for _name, lo, _hi in NAMED_BANDS:
            if args.fit_lo < lo < args.fit_hi:
                ax.axvline(lo, color="#888888", lw=0.7, ls=":")
        # Headroom first, then label into it -- otherwise the band names are
        # drawn over the tallest bars and under the legend.
        top = ax.get_ylim()[1]
        ax.set_ylim(0, top * 1.16)
        for name, lo, hi in NAMED_BANDS:
            c = np.sqrt(max(lo, args.fit_lo) * min(hi, args.fit_hi))
            if args.fit_lo < c < args.fit_hi:
                ax.text(c, top * 1.03, name, ha="center", va="bottom",
                        fontsize=7, color="#555555")
        ax.legend(fontsize=7, loc="upper left", framealpha=0.9)
    ax.set_xlabel("dominant frequency (Hz)")
    ax.set_ylabel("windows (occurrences)")
    ax.set_title("how often each frequency was the loudest rhythm\n"
                 "(one count per %g s window)" % args.step, fontsize=9.5)
    return fig


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default=FOLDER)
    ap.add_argument("--channel", default="CSC1")
    ap.add_argument("--sub", type=float, default=2.0,
                    help="FFT length (s); frequency resolution is 1/sub")
    ap.add_argument("--win", type=float, default=8.0,
                    help="time averaged per column (s); more = smoother "
                         "spectra, blurrier in time")
    ap.add_argument("--step", type=float, default=1.0,
                    help="hop between output columns (s)")
    ap.add_argument("--measure", default="osc",
                    choices=["abs", "rel", "ratio", "osc"],
                    help="which measure picks the epochs")
    ap.add_argument("--z", type=float, default=2.0, help="threshold, robust z")
    ap.add_argument("--min-dur", type=float, default=5.0,
                    help="ignore epochs shorter than this (s)")
    ap.add_argument("--merge-gap", type=float, default=2.0,
                    help="bridge dips shorter than this (s)")
    ap.add_argument("--top", type=int, default=15, help="epochs to print")
    ap.add_argument("--lines", type=float, nargs="+", default=SUB_CENTERS,
                    help="centres of the narrow theta lines (Hz)")
    ap.add_argument("--fit-lo", type=float, default=2.0)
    ap.add_argument("--fit-hi", type=float, default=45.0)
    ap.add_argument("--knee", action="store_true",
                    help="aperiodic_mode='knee' instead of 'fixed'")
    ap.add_argument("--no-fooof", action="store_true",
                    help="skip the per-window fits (fast, drops 'osc')")
    ap.add_argument("--jobs", type=int, default=1, help="FOOOFGroup n_jobs")
    ap.add_argument("--save", default=None, help="write the figure here")
    ap.add_argument("--csv", default=None, help="write the per-window table here")
    args = ap.parse_args()

    path = os.path.join(args.folder, args.channel + ".ncs")
    if not os.path.exists(path):
        sys.exit("no such file: " + path)

    x, fs, dur = load_channel(path)
    freqs, times, pxx, n_avg = make_spectrogram(x, fs, args.sub, args.win,
                                                args.step)
    print("  %d columns: %g s of signal each (%d x %g s sub-windows averaged),"
          " %g s hop, %.3f Hz bins"
          % (len(times), args.win, n_avg, args.sub, args.step,
             freqs[1] - freqs[0]))

    # ---- the four measures ----
    m = {}
    m["abs"] = band_integral(freqs, pxx, *THETA)
    m["rel"] = m["abs"] / band_integral(freqs, pxx, *TOTAL)
    m["ratio"] = m["abs"] / band_integral(freqs, pxx, *DELTA)
    if args.no_fooof:
        m.update({k: np.full(len(times), np.nan) for k in
                  ("osc", "exponent", "offset", "cf", "pw", "r2")})
        m["dom_theta"], m["dom_all"] = dominant_simple(
            freqs, pxx, [args.fit_lo, args.fit_hi])
        m["dom_all_pw"] = np.full(len(times), np.nan)
        print("  dominant frequencies from a log-log line fit "
              "(--no-fooof; cruder than the model)")
    else:
        m.update(fooof_theta(freqs, pxx, [args.fit_lo, args.fit_hi],
                             "knee" if args.knee else "fixed", args.jobs))

    # ---- theta one hertz at a time ----
    tiles = sub_bands(args.lines)
    sub = {name: band_integral(freqs, pxx, lo, hi) for name, lo, hi in tiles}
    sub_z = {name: robust_z(np.log10(v)) for name, v in sub.items()}

    if args.measure == "osc" and not np.isfinite(m["osc"]).any():
        sys.exit("no FOOOF fits -- rerun without --no-fooof, or pass "
                 "--measure ratio")

    # ---- relative to the recording ----
    # The log is taken before scoring for the two measures that span orders of
    # magnitude: a z on a raw power ratio is a z on a skewed distribution, and
    # the threshold then means something different at each end of it.
    z = {"abs": robust_z(np.log10(m["abs"])),
         "rel": robust_z(m["rel"]),
         "ratio": robust_z(np.log10(m["ratio"])),
         "osc": robust_z(m["osc"])}

    epochs = find_epochs(times, z[args.measure], args.z,
                         args.min_dur, args.merge_gap)
    epochs.sort(key=lambda e: e["z_mean"], reverse=True)

    summary = whole_recording(freqs, pxx, epochs, [args.fit_lo, args.fit_hi],
                              None if args.no_fooof else
                              ("knee" if args.knee else "fixed"),
                              verbose=False)

    # ---- report ----
    print("\nHIGH THETA by '%s', robust z >= %.1f, >= %.0f s"
          % (args.measure, args.z, args.min_dur))
    hot_s = sum(e["dur"] for e in epochs)
    print("  %d epochs, %.1f s total (%.1f%% of the recording)"
          % (len(epochs), hot_s, 100.0 * hot_s / dur if dur else 0.0))
    # Two different questions, and they have to be kept apart:
    #   THETA Hz  -- given that we are looking at 4-12, where in it is the
    #                power? Always answerable, because the band always exists.
    #   OVERALL   -- across the whole fit range, which frequency actually
    #                stands highest above its own background? This one is
    #                allowed to answer "not theta", and when it does, an
    #                epoch picked by a theta measure was picked by a rise in
    #                something else. "% thet" says how often it agreed.
    print("\n   #  start      end       dur   z mean  | theta Hz | overall Hz"
          "  band        % thet | loudest line")
    for i, e in enumerate(epochs[:args.top], 1):
        sl = slice(e["i0"], e["i1"])
        dt = np.nanmedian(m["dom_theta"][sl])
        da = np.nanmedian(m["dom_all"][sl])
        da_all = m["dom_all"][sl]
        has = np.isfinite(da_all)
        pct = (100.0 * np.mean((da_all[has] >= THETA[0])
                               & (da_all[has] <= THETA[1]))
               if has.any() else np.nan)
        best = max(sub_z, key=lambda k: np.nanmedian(sub_z[k][sl]))
        print("  %2d  %8s  %8s  %6.1fs  %6.2f  | %8s | %10s  %-10s %5s | %s"
              % (i, mmss(e["t0"]), mmss(e["t1"]), e["dur"], e["z_mean"],
                 "%.2f" % dt if np.isfinite(dt) else "-",
                 "%.2f" % da if np.isfinite(da) else "-", band_of(da),
                 "%.0f%%" % pct if np.isfinite(pct) else "-", best))

    # The same two questions for the recording as a whole, so an epoch's
    # numbers can be read against a baseline instead of in isolation.
    dt_all, da_all = m["dom_theta"], m["dom_all"]
    if np.isfinite(dt_all).any():
        has = np.isfinite(da_all)
        print("\n  WHOLE RECORDING, for comparison")
        print("    dominant frequency within theta : %.2f Hz (median)"
              % np.nanmedian(dt_all))
        if has.any():
            print("    dominant rhythm overall         : %.2f Hz (median), "
                  "in %s" % (np.nanmedian(da_all), band_of(np.nanmedian(da_all))))
        # Split three ways, not two. "Theta was loudest" and "something else
        # was loudest" do not exhaust the possibilities -- most of this
        # recording has no peak at all, and folding those in with the
        # non-theta windows would report a rhythm that was never there.
        names, counts = np.unique([band_of(f) for f in da_all],
                                  return_counts=True)
        order = np.argsort(-counts)
        print("    where the strongest rhythm sat: "
              + ", ".join("%s %.0f%%" % (names[k], 100.0 * counts[k] / len(da_all))
                          for k in order))
        if has.any():
            inb = (da_all[has] >= THETA[0]) & (da_all[has] <= THETA[1])
            print("    of the %.0f%% of windows that had any rhythm, %.0f%% "
                  "were theta" % (100.0 * has.mean(), 100.0 * inb.mean()))

        # A dominant frequency that changes every window is not a dominant
        # frequency. With five bands on offer, a winner taking only a third
        # of the windows is barely ahead of a rotation, and the honest
        # reading is that outside the bouts there is no rhythm to be dominant
        # -- FOOOF still places a small peak somewhere, because a spectrum
        # always has a highest bump, but which band wins is then noise.
        top = 100.0 * counts[order[0]] / len(da_all)
        print("    top band holds %.0f%% of windows -- %s" % (
            top,
            "a stable dominant rhythm" if top >= 50 else
            "NOT stable. The winner rotates, which is what 'no clear rhythm' "
            "looks like;\n      the epochs are the part of this recording "
            "where it stops rotating."))
        ep = np.concatenate([m["dom_all_pw"][e["i0"]:e["i1"]]
                             for e in epochs]) if epochs else np.array([])
        rest = np.delete(m["dom_all_pw"], np.concatenate(
            [np.arange(e["i0"], e["i1"]) for e in epochs]).astype(int)) \
            if epochs else m["dom_all_pw"]
        if ep.size and rest.size:
            print("    height of that peak: %.2f inside the epochs vs %.2f "
                  "outside (log10)" % (np.nanmedian(ep), np.nanmedian(rest)))

    print_whole(summary, [args.fit_lo, args.fit_hi],
                "knee" if args.knee else "fixed")

    print("\n  THETA ONE LINE AT A TIME (median power, whole recording)")
    for name, lo, hi in tiles:
        v = sub[name]
        print("    %-7s (%4.1f-%4.1f Hz)  %9.1f uV^2   median z in epochs %+5.2f"
              % (name, lo, hi, np.nanmedian(v),
                 np.nanmedian(np.concatenate(
                     [sub_z[name][e["i0"]:e["i1"]] for e in epochs])
                 ) if epochs else np.nan))

    # The same z means a different fraction of the recording for each measure,
    # because the four distributions are not the same shape. Printed so the
    # threshold is read as "the top n%" rather than as a physical quantity.
    print("\n  what z >= %.1f selects, per measure:" % args.z)
    for key in ("abs", "rel", "ratio", "osc"):
        good = np.isfinite(z[key])
        if good.any():
            print("    %-6s %5.1f%% of windows" %
                  (key, 100.0 * (z[key][good] >= args.z).mean()))

    if np.isfinite(m["osc"]).any():
        for a, b in (("abs", "osc"), ("ratio", "osc"), ("abs", "ratio")):
            good = np.isfinite(z[a]) & np.isfinite(z[b])
            if good.sum() > 2:
                r = np.corrcoef(z[a][good], z[b][good])[0, 1]
                print("  agreement  z(%s) vs z(%s):  r = %+.2f" % (a, b, r))
        print("  aperiodic exponent: median %.2f, range %.2f-%.2f; "
              "median fit R^2 %.3f"
              % (np.nanmedian(m["exponent"]), np.nanmin(m["exponent"]),
                 np.nanmax(m["exponent"]), np.nanmedian(m["r2"])))

    # ---- outputs ----
    if args.csv:
        names = [n for n, _lo, _hi in tiles]
        cols = (["t_s", "theta_abs", "theta_rel", "theta_ratio", "theta_osc",
                 "z_abs", "z_rel", "z_ratio", "z_osc",
                 "dom_theta_hz", "dom_all_hz", "dom_all_band", "dom_all_pw",
                 "exponent", "offset", "theta_cf", "theta_pw", "r2"]
                + ["pw_%s" % n.replace(" ", "") for n in names]
                + ["z_%s" % n.replace(" ", "") for n in names]
                + ["is_epoch"])
        flag = np.zeros(len(times), dtype=int)
        for e in epochs:
            flag[e["i0"]:e["i1"]] = 1
        with open(args.csv, "w", newline="") as fh:
            w = csvmod.writer(fh)
            w.writerow(cols)
            for i, t in enumerate(times):
                w.writerow(["%.3f" % t] +
                           ["%.6g" % m[k][i] for k in
                            ("abs", "rel", "ratio", "osc")] +
                           ["%.4f" % z[k][i] for k in
                            ("abs", "rel", "ratio", "osc")] +
                           ["%.3f" % m["dom_theta"][i], "%.3f" % m["dom_all"][i],
                            band_of(m["dom_all"][i]), "%.4f" % m["dom_all_pw"][i]] +
                           ["%.4f" % m[k][i] for k in
                            ("exponent", "offset", "cf", "pw", "r2")] +
                           ["%.6g" % sub[n][i] for n in names] +
                           ["%.4f" % sub_z[n][i] for n in names] +
                           [flag[i]])
        print("\n  wrote " + args.csv)

    title = "%s  %s  (%.1f min)" % (os.path.basename(args.folder),
                                    args.channel, dur / 60.0)
    fig = plot_all(freqs, times, pxx, m, z, sub, sub_z, tiles, epochs, args,
                   title, summary)
    if args.save:
        fig.savefig(args.save, dpi=130)
        print("  wrote " + args.save)
    else:
        plt.show()


def mmss(t):
    return "%d:%05.2f" % (int(t // 60), t % 60)


if __name__ == "__main__":
    main()
