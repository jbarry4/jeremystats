"""
theta_shape.py -- what each theta cycle actually LOOKS like, not just how big.

WHY SHAPE
---------
Everything in theta_through_time.py is a spectrum, and a spectrum assumes the
rhythm is a sine wave. Hippocampal theta is not a sine wave. It is closer to a
sawtooth: the rise and the fall take different amounts of time, and the peaks
and troughs have different sharpness. That asymmetry is not a nuisance -- it
changes with running speed, with layer, and between CA1 and DG, so it carries
information a power measure throws away.

It also breaks things downstream. A non-sinusoidal wave is, by definition, a
fundamental plus harmonics. Those harmonics are real frequency content, so:

  * They appear as separate "oscillations" in a power spectrum -- a 6 Hz
    sawtooth puts power at 12, 18, 24 Hz that no 12/18/24 Hz rhythm produced.
  * They produce PHASE-AMPLITUDE COUPLING between the fundamental and its own
    harmonics, with no coupling of any kind taking place. This is the single
    most common false positive in the CFC literature, and it is why
    Reviving CFC is worth pointing at this script first: if theta here is
    strongly asymmetric, a theta-gamma PAC number from the same channel needs
    a shape control before it means anything.

Cole & Voytek (2017), "Brain oscillations and the importance of waveform
shape", TiCS 21:137-149, is the argument. `bycycle` (Cole & Voytek 2019,
J Neurophysiol 122:849-861) is their toolkit for it, and it is what runs here.

WHAT IS MEASURED
----------------
bycycle works cycle by cycle in the time domain rather than in a spectrum. It
finds each theta cycle's peak and troughs, then measures:

  time_rdsym   rise time / period.  0.5 = symmetric. Below 0.5 the wave
               rises faster than it falls -- a sawtooth leaning left.
  time_ptsym   peak duration / (peak + trough).  0.5 = symmetric. Below 0.5
               the peaks are narrower than the troughs.
  volt_amp     peak-to-trough amplitude, uV.
  period       cycle length in samples -> instantaneous frequency.

BURSTS, AND WHY THEY MATTER HERE
--------------------------------
Every one of those numbers is meaningless for a stretch of signal with no
theta in it: an algorithm asked to find cycles in noise will find cycles in
noise, and report their shape. bycycle's burst detection is the guard. A
cycle counts only if its amplitude is consistent with its neighbours, its
period is consistent with its neighbours, and it rises and falls
monotonically -- i.e. only if it is part of a run of genuinely rhythmic
cycles.

That doubles as the test for the open question from theta_through_time.py:
the high-theta bouts there peaked near 5 Hz, which is low for running theta
and could instead be the upper shoulder of this channel's very strong delta.
Burst detection settles it. A real 5 Hz rhythm produces long runs of
consistent 5 Hz cycles. A delta shoulder does not.

Run:
  python theta_shape.py
  python theta_shape.py --channel CSC7 --band 5 12
  python theta_shape.py --highpass 0 --save shape.png --csv cycles.csv
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt
from scipy.stats import mannwhitneyu

from bycycle.features import compute_shape_features, compute_burst_features
from bycycle.burst.utils import check_min_burst_cycles

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theta_through_time import (                                  # noqa: E402
    FOLDER, THETA, DELTA, load_channel, make_spectrogram,
    band_integral, robust_z, find_epochs, mmss)

# Shape needs more samples per cycle than power does. At 500 Hz a 6 Hz cycle
# is 83 samples, so a rise/fall time is resolved to about 1% of the period.
SHAPE_FS = 500.0

# bycycle's tutorial values, EXCEPT monotonicity. Its 0.8 is calibrated on
# cleaner or more aggressively low-passed data; on this channel the median
# cycle scores 0.58 and 0.8 accepts 0.6% of cycles, i.e. nothing. Monotonicity
# asks whether the rise and the fall are smooth, so what fails it here is the
# gamma and unit activity riding on the theta wave -- real signal, and not a
# reason to declare there is no theta.
#
# Lowering it is a judgement call, so the pass rate of every criterion is
# printed on every run: if a threshold is doing all the work, that is visible
# rather than buried.
THRESHOLDS = {
    "amp_fraction_threshold": 0.0,
    "amp_consistency_threshold": 0.5,
    "period_consistency_threshold": 0.5,
    "monotonicity_threshold": 0.6,
    "min_n_cycles": 3,
}


def detect_bursts(df, thresholds):
    """bycycle's cycle-by-cycle burst rule.

    Reimplemented here only because bycycle 1.2.0's own
    `detect_bursts_cycles` calls `.to_numpy()` on a boolean Series and then
    writes to it. Current pandas returns that read-only, so it raises
    ValueError before it ever sees the data. The rule below is that function's,
    line for line, with the one array copied.
    """
    t = dict(thresholds)
    keep = ((df["amp_fraction"] > t["amp_fraction_threshold"])
            & (df["amp_consistency"] > t["amp_consistency_threshold"])
            & (df["period_consistency"] > t["period_consistency_threshold"])
            & (df["monotonicity"] > t["monotonicity_threshold"]))
    is_burst = keep.to_numpy().copy()
    is_burst[0] = False
    is_burst[-1] = False
    return check_min_burst_cycles(is_burst, min_n_cycles=t["min_n_cycles"])


def cycle_features(sig, fs, band, center, thresholds):
    """Shape + burst features for every cycle in `band`."""
    shape = compute_shape_features(sig, fs, band, center_extrema=center)
    burst = compute_burst_features(shape, sig)
    df = pd.concat([shape, burst], axis=1)
    df["is_burst"] = detect_bursts(df, thresholds)
    df["t_s"] = df["sample_last_trough"].to_numpy() / fs
    df["freq"] = fs / df["period"].to_numpy()
    return df


def band_label(hp, lp):
    if hp > 0 and lp > 0:
        return "%g-%g Hz (zero-phase band-pass)" % (hp, lp)
    if hp > 0:
        return "%g Hz high-pass (zero-phase)" % hp
    if lp > 0:
        return "%g Hz low-pass (zero-phase)" % lp
    return "the unfiltered signal"


def bandpass(x, fs, hp, lp):
    """Zero-phase filtering, and the reason it is a compromise.

    Every filter reshapes what it passes, which is precisely the quantity
    being measured here -- so the safest filter is none, and the second
    safest is the widest one that works. Two things force a narrower one:

      HIGH-PASS. This channel's sub-4 Hz power is an order of magnitude above
      theta. A slow wave running underneath a theta cycle tilts it, so the
      peak and trough are read off a moving baseline and the amplitude and
      peak-trough symmetry are measured against a slope.

      LOW-PASS. Gamma and unit activity ride on the theta wave and make its
      rise and fall locally non-monotonic. bycycle's monotonicity criterion
      then rejects every cycle, including the real ones.

    Zero-phase in both directions, because a causal filter delays different
    frequencies by different amounts, which by itself converts a symmetric
    wave into an asymmetric one. And the default low-pass sits at 40 Hz: a
    5 Hz sawtooth carries its shape in harmonics at 10, 15, 20, 25, 30, 35 Hz,
    so 40 Hz keeps the shape while dropping the gamma. Low-passing much closer
    to the band manufactures the sinusoid it then reports -- run --sweep,
    which measures the asymmetry under several settings so the number can be
    checked for exactly that.
    """
    good = np.isfinite(x)
    sig = np.where(good, x, 0.0).astype(float)
    nyq = fs / 2.0
    if hp > 0 and lp > 0:
        b, a = butter(2, [hp / nyq, lp / nyq], btype="bandpass")
    elif hp > 0:
        b, a = butter(2, hp / nyq, btype="highpass")
    elif lp > 0:
        b, a = butter(2, lp / nyq, btype="lowpass")
    else:
        b = a = None
    if b is not None:
        sig = filtfilt(b, a, sig)
    # bycycle cannot step over a NaN, so a gap is bridged and the cycles that
    # touch it are the ones the burst rule rejects anyway.
    if not good.all():
        idx = np.arange(sig.size)
        sig = np.interp(idx, idx[good], sig[good])
    return sig


def sweep(x, fs, band, center, in_epoch_fn, hp):
    """Is the asymmetry in the data, or in the filter?

    The one control a waveform-shape claim cannot go without. If rdsym moves
    with the low-pass corner, the filter made it. If it holds while the corner
    moves by a factor of three, the wave is genuinely that shape.
    """
    print("\n  SWEEP -- rise-decay symmetry under different low-pass corners")
    print("  %-14s %8s %10s %10s" % ("passband", "n in", "rdsym IN", "rdsym out"))
    for lp in (0.0, 80.0, 50.0, 40.0, 30.0):
        s = bandpass(x, fs, hp, lp)
        d = cycle_features(s, fs, band, center, THRESHOLDS)
        ine = in_epoch_fn(d)
        a = d.loc[ine & d["is_burst"], "time_rdsym"]
        b = d.loc[(~ine) & d["is_burst"], "time_rdsym"]
        print("  %-14s %8d %10s %10s"
              % (band_label(hp, lp).split(" (")[0], len(a),
                 "%.3f" % a.median() if len(a) else "-",
                 "%.3f" % b.median() if len(b) else "-"))


def mean_cycle(sig, df, n=120):
    """The average cycle, time-normalised and amplitude-normalised.

    Every cycle is stretched to the same length and scaled to the same height
    before averaging, so what survives is SHAPE and nothing else: a set of
    cycles that differ only in size and rate average to their common form,
    and a set with no common form averages to a flat line.
    """
    grid = np.linspace(0, 1, n)
    out = []
    for a, b in zip(df["sample_last_trough"], df["sample_next_trough"]):
        a, b = int(a), int(b)
        seg = sig[a:b]
        if seg.size < 8 or not np.isfinite(seg).all():
            continue
        rng = seg.max() - seg.min()
        if rng <= 0:
            continue
        out.append(np.interp(grid, np.linspace(0, 1, seg.size),
                             (seg - seg.mean()) / rng))
    return grid, (np.array(out) if out else np.empty((0, n)))


def describe(df, label):
    """Median shape of the burst cycles in one set."""
    b = df[df["is_burst"]]
    if not len(b):
        return None
    return {
        "label": label, "n": len(b),
        "frac_burst": float(df["is_burst"].mean()),
        "freq": float(b["freq"].median()),
        "amp": float(b["volt_amp"].median()),
        "rdsym": float(b["time_rdsym"].median()),
        "ptsym": float(b["time_ptsym"].median()),
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default=FOLDER)
    ap.add_argument("--channel", default="CSC1")
    ap.add_argument("--band", type=float, nargs=2, default=list(THETA),
                    help="band used to locate cycles (Hz)")
    ap.add_argument("--center", default="peak", choices=["peak", "trough"],
                    help="cycles centred on peaks or troughs; this FLIPS the "
                         "sense of rdsym, so say which one you used")
    ap.add_argument("--highpass", type=float, default=2.0,
                    help="zero-phase high-pass before shape measurement (Hz); "
                         "0 disables. See the note in the report.")
    ap.add_argument("--lowpass", type=float, default=40.0,
                    help="zero-phase low-pass (Hz); 0 disables. Keeps the "
                         "harmonics that carry the shape, drops the gamma "
                         "that wrecks monotonicity.")
    ap.add_argument("--mono", type=float, default=None,
                    help="override the monotonicity threshold")
    ap.add_argument("--sweep", action="store_true",
                    help="re-measure under several low-pass settings and "
                         "print the asymmetry from each -- the control for "
                         "'did my filter make this shape?'")
    ap.add_argument("--z", type=float, default=2.0,
                    help="threshold that defines a high-theta epoch")
    ap.add_argument("--min-dur", type=float, default=5.0)
    ap.add_argument("--save", default=None)
    ap.add_argument("--csv", default=None, help="per-cycle table")
    args = ap.parse_args()

    path = os.path.join(args.folder, args.channel + ".ncs")
    if not os.path.exists(path):
        sys.exit("no such file: " + path)

    band = tuple(args.band)
    x, fs, dur = load_channel(path, target_fs=SHAPE_FS)

    # ---- where the theta is, by theta/delta ratio (no FOOOF needed) ----
    freqs, times, pxx, _ = make_spectrogram(x, fs, 2.0, 8.0, 1.0)
    z = robust_z(np.log10(band_integral(freqs, pxx, *THETA)
                          / band_integral(freqs, pxx, *DELTA)))
    epochs = find_epochs(times, z, args.z, args.min_dur, 2.0)
    epochs.sort(key=lambda e: e["z_mean"], reverse=True)
    print("  %d high-theta epochs, %.0f s total"
          % (len(epochs), sum(e["dur"] for e in epochs)))

    # ---- the signal shape is measured on: see bandpass() ----
    if args.mono is not None:
        THRESHOLDS["monotonicity_threshold"] = args.mono

    sig = bandpass(x, fs, args.highpass, args.lowpass)
    print("  measured on %s" % band_label(args.highpass, args.lowpass))

    print("  finding %g-%g Hz cycles over %.1f min, %s-centred ..."
          % (band[0], band[1], dur / 60.0, args.center))
    df = cycle_features(sig, fs, band, args.center, THRESHOLDS)

    # Which criterion is actually deciding. Printed always: a burst fraction
    # is uninterpretable without it, and a single threshold rejecting
    # everything looks identical to "there is no oscillation here".
    print("\n  burst criteria, pass rate of each on its own:")
    for col, key in (("amp_fraction", "amp_fraction_threshold"),
                     ("amp_consistency", "amp_consistency_threshold"),
                     ("period_consistency", "period_consistency_threshold"),
                     ("monotonicity", "monotonicity_threshold")):
        v = df[col].dropna()
        print("    %-19s > %.2f   %5.1f%% pass   (median %.3f)"
              % (col, THRESHOLDS[key], 100.0 * (v > THRESHOLDS[key]).mean(),
                 v.median()))

    def mark_epochs(d):
        m = np.zeros(len(d), dtype=bool)
        for e in epochs:
            m |= ((d["t_s"] >= e["t0"]) & (d["t_s"] <= e["t1"])).to_numpy()
        return m

    df["in_epoch"] = mark_epochs(df)

    if args.sweep:
        sweep(x, fs, band, args.center, mark_epochs, args.highpass)

    # ---- report ----
    nb = int(df["is_burst"].sum())
    print("\n  %d cycles found, %d in bursts (%.1f%%)"
          % (len(df), nb, 100.0 * nb / len(df)))
    if not nb:
        sys.exit("  no bursting cycles -- loosen THRESHOLDS or widen --band")

    rows = [r for r in (describe(df[df["in_epoch"]], "inside epochs"),
                        describe(df[~df["in_epoch"]], "rest of recording"),
                        describe(df, "all")) if r]
    print("\n  SHAPE OF BURST CYCLES (medians)")
    print("  %-19s %7s %8s %8s %9s %8s %8s"
          % ("", "n", "burst%", "freq Hz", "amp uV", "rdsym", "ptsym"))
    for r in rows:
        print("  %-19s %7d %7.1f%% %8.2f %9.1f %8.3f %8.3f"
              % (r["label"], r["n"], 100 * r["frac_burst"], r["freq"],
                 r["amp"], r["rdsym"], r["ptsym"]))

    b_in = df[(df["is_burst"]) & (df["in_epoch"])]
    b_out = df[(df["is_burst"]) & (~df["in_epoch"])]
    if len(b_in) > 20 and len(b_out) > 20:
        print("\n  inside vs outside the epochs (Mann-Whitney; cycles are not"
              "\n  independent, so read these as effect sizes, not p-values)")
        for key, name in (("time_rdsym", "rise-decay sym"),
                          ("time_ptsym", "peak-trough sym"),
                          ("volt_amp", "amplitude"), ("freq", "frequency")):
            u, p = mannwhitneyu(b_in[key], b_out[key])
            d = b_in[key].median() - b_out[key].median()
            print("    %-16s  diff %+8.3f   p = %.2g" % (name, d, p))

    # The verdict is taken from the cycles INSIDE the epochs, not from all of
    # them. Outside the epochs there is no oscillation to have a shape, and
    # cycles fitted to noise sit at exactly 0.500 by symmetry -- pool them in
    # and thousands of them drag a real asymmetry back to "sinusoidal". That
    # 0.500 is not a finding, it is the absence of one, which is why this
    # number has to be quoted per condition and never per file.
    judge = b_in if len(b_in) >= 50 else df[df["is_burst"]]
    scope = "inside the high-theta epochs" if len(b_in) >= 50 else "all bursts"
    sym = judge["time_rdsym"].median()
    f0 = judge["freq"].median()
    print("\n  VERDICT (%s, n=%d): rdsym %.3f" % (scope, len(judge), sym))
    if abs(sym - 0.5) < 0.02:
        print("  Symmetric, near-sinusoidal. Harmonic artefacts unlikely.")
    else:
        fast, slow = ("rise", "decay") if sym < 0.5 else ("decay", "rise")
        print("  ASYMMETRIC -- the %s is faster than the %s." % (fast, slow))
        print("  A wave this shape IS a fundamental plus harmonics, so at "
              "%.1f Hz expect power" % f0)
        print("  at %.0f and %.0f Hz that no separate rhythm produced, and "
              "expect theta-gamma" % (2 * f0, 3 * f0))
        print("  PAC on this channel to be inflated unless it is controlled "
              "for.")

    if args.csv:
        df.to_csv(args.csv, index=False)
        print("\n  wrote " + args.csv)

    # ---- the picture ----
    fig = plt.figure(figsize=(13, 11))
    gs = fig.add_gridspec(4, 2, height_ratios=[1.1, 1.2, 1, 1], hspace=0.55,
                          wspace=0.25)

    # 1. the raw trace during the strongest epoch, cycles marked
    ax = fig.add_subplot(gs[0, :])
    if epochs:
        e = epochs[0]
        t0 = e["t_peak"] - 2.0
        s0, s1 = int(t0 * fs), int((t0 + 4.0) * fs)
        tt = np.arange(s0, s1) / fs
        ax.plot(tt, sig[s0:s1], color="k", lw=0.8)
        sel = df[(df["sample_last_trough"] >= s0)
                 & (df["sample_next_trough"] <= s1)]
        for _, c in sel.iterrows():
            col = "#d62728" if c["is_burst"] else "#bbbbbb"
            ax.axvspan(c["sample_last_trough"] / fs,
                       c["sample_next_trough"] / fs,
                       color=col, alpha=0.18, lw=0)
            ax.plot(c["sample_peak"] / fs, sig[int(c["sample_peak"])],
                    "v", ms=4, color=col)
        ax.set_xlim(tt[0], tt[-1])
        ax.set_title("4 s inside the strongest epoch (at %s). Red = cycles "
                     "burst detection accepted, grey = rejected."
                     % mmss(e["t_peak"]))
    ax.set_xlabel("time (s)")
    ax.set_ylabel("$\\mu$V")

    # 2. THE shape figure: the average cycle
    ax = fig.add_subplot(gs[1, 0])
    for sub, lab, col in ((b_in, "inside epochs", "#d62728"),
                          (b_out, "rest", "#1f77b4")):
        if len(sub) < 10:
            continue
        g, cyc = mean_cycle(sig, sub)
        if not len(cyc):
            continue
        mu, sd = cyc.mean(axis=0), cyc.std(axis=0)
        ax.plot(g, mu, color=col, lw=1.8, label="%s (n=%d)" % (lab, len(cyc)))
        ax.fill_between(g, mu - sd, mu + sd, color=col, alpha=0.15, lw=0)
    ax.plot(np.linspace(0, 1, 120),
            -0.5 * np.cos(2 * np.pi * np.linspace(0, 1, 120)),
            color="k", ls="--", lw=1, label="a sine, for reference")
    ax.axvline(0.5, color="#999999", lw=0.7, ls=":")
    ax.set_xlabel("position in cycle (trough to trough)")
    ax.set_ylabel("normalised")
    ax.set_title("the average theta cycle\n(stretched and scaled: shape only)")
    ax.legend(fontsize=7.5)

    # 3. how asymmetric, as a distribution
    ax = fig.add_subplot(gs[1, 1])
    bins = np.linspace(0.2, 0.8, 50)
    for sub, lab, col in ((b_in, "inside epochs", "#d62728"),
                          (b_out, "rest", "#1f77b4")):
        if len(sub) > 10:
            ax.hist(sub["time_rdsym"], bins=bins, density=True, histtype="step",
                    lw=1.6, color=col, label=lab)
    ax.axvline(0.5, color="k", ls="--", lw=1)
    ax.set_xlabel("rise-decay symmetry  (0.5 = a sine)")
    ax.set_ylabel("density")
    ax.set_title("sawtooth or sine?")
    ax.legend(fontsize=7.5)

    # 4. shape through time -- does it track the bouts?
    ax = fig.add_subplot(gs[2, :])
    bd = df[df["is_burst"]]
    ax.plot(bd["t_s"] / 60.0, bd["time_rdsym"], ".", ms=2, color="#7f7f7f")
    if len(bd) > 60:
        k = 51
        sm = bd["time_rdsym"].rolling(k, center=True, min_periods=k // 2).median()
        ax.plot(bd["t_s"] / 60.0, sm, color="#d62728", lw=1.3)
    ax.axhline(0.5, color="k", ls="--", lw=0.8)
    for e in epochs:
        ax.axvspan(e["t0"] / 60.0, e["t1"] / 60.0, color="cyan", alpha=0.2, lw=0)
    ax.set_ylim(0.2, 0.8)
    ax.set_ylabel("rdsym")
    ax.set_title("asymmetry through the recording (burst cycles; red = running "
                 "median; shaded = high-theta epochs)")

    # 5. which cycles were accepted, and at what rate
    ax = fig.add_subplot(gs[3, :])
    edges = np.arange(0, dur + 10, 10.0)
    rate, _ = np.histogram(bd["t_s"], bins=edges)
    ax.bar(edges[:-1] / 60.0, rate / 10.0, width=10 / 60.0, color="#2ca02c")
    for e in epochs:
        ax.axvspan(e["t0"] / 60.0, e["t1"] / 60.0, color="cyan", alpha=0.2, lw=0)
    ax.set_ylabel("burst cycles\nper second")
    ax.set_xlabel("time (min)")
    ax.set_title("how much of the recording is genuinely rhythmic, and when")

    fig.suptitle("%s  %s  --  theta waveform shape, %g-%g Hz"
                 % (os.path.basename(args.folder), args.channel,
                    band[0], band[1]), y=0.995)
    if args.save:
        fig.savefig(args.save, dpi=130, bbox_inches="tight")
        print("  wrote " + args.save)
    else:
        plt.show()


if __name__ == "__main__":
    main()
