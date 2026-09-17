"""
theta_channels.py -- the theta analysis across every even channel at once.

WHAT CAN AND CANNOT BE AVERAGED ACROSS CHANNELS
===============================================
This is the whole design question, so it is worth being blunt about it.

CANNOT be averaged
------------------
RAW POWER, in uV^2. An electrode measures the field where it happens to sit.
Theta amplitude across a probe spanning the hippocampal layers varies by
something like a factor of ten, and the theta dipole REVERSES across the
fissure -- stratum oriens and stratum lacunosum-moleculare are out of phase
with each other. So a mean of raw theta power over channels is a mean over
anatomy, and it answers a question nobody asked: it is large when the probe
happens to have many contacts near a source and small when it does not.
Worse, it is dominated by whichever channel has the largest amplitude, which
is usually the one closest to the source and sometimes the one with the worst
impedance.

ANYTHING INVOLVING PHASE, for the same reason: average a signal with its own
inversion and you get zero, which is not an absence of theta.

CAN be averaged
---------------
Z-SCORED TIME COURSES. This is the move that makes the whole script work.
Each channel is scored against ITS OWN distribution over the snippet, so the
units, the impedance and the distance to the source all divide out. What is
left is "was this moment unusual for this wire", which is the same question
on every wire and therefore poolable. The average of those is a consensus
about the BRAIN STATE rather than about the field strength.

FREQUENCIES. Theta is globally coherent across the hippocampus -- at any
instant the whole structure is oscillating at one rate. So the theta peak
frequency should agree across channels, which means (a) averaging it is
meaningful and (b) the SPREAD across channels is a free quality check. If
channels disagree about the frequency, either the fits are bad or the
channels are not all in the same structure.

APERIODIC EXPONENT is dimensionless and comparable, though it genuinely does
vary with layer, so its spread is a real measurement rather than noise.

AND THE THING THAT MUST COME FIRST
----------------------------------
None of the above survives one dead or railing channel, which will sit at
some absurd variance and drag every mean it touches. So channels are screened
before anything is pooled, and the ones that fail are named rather than
quietly dropped.

HOW TO LOOK AT 32 CHANNELS
--------------------------
Not as 32 overlaid lines. The layout here is:

  heatmap channel x time    the one plot to read first. A theta event that is
                            real is a VERTICAL stripe -- every channel at
                            once, because it is a brain state. A HORIZONTAL
                            stripe is one channel misbehaving.
  consensus trace           median across channels with the spread drawn, so
                            "the theta time course" has an error bar.
  channel x frequency       the snippet's spectrum per channel, which is the
                            laminar profile: where the theta dipole is
                            strongest, and where the gamma is.
  per-channel profiles      theta power, peak frequency and exponent against
                            channel number, i.e. against depth.
  agreement matrix          channel-by-channel correlation of the theta time
                            course. Blocks are layers; a lone dark row is a
                            channel that agrees with nobody.

Run:
  python theta_channels.py
  python theta_channels.py --t0 600 --dur 100 --all
  python theta_channels.py --per-window --save ch.png --csv ch.csv
"""

import argparse
import csv as csvmod
import os
import sys

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "BARRY GUI", "backend"))
import nlx                                                    # noqa: E402
import cfc                                                    # noqa: E402
from theta_through_time import (                              # noqa: E402
    FOLDER, THETA, DELTA, TOTAL, THETA_CF, FMAX, TARGET_FS,
    NAMED_BANDS, band_of, make_spectrogram, band_integral, robust_z,
    find_epochs, mmss)

# A channel is called bad if its amplitude is this many robust SDs away from
# what the other channels are doing. Generous on purpose: the point is to
# catch a dead wire or a railing one, not to trim the laminar profile, which
# is real variation and is exactly what the depth plots are for.
AMP_SD = 4.0
FLAT_UV = 1.0            # below this an LFP channel is not recording


# --------------------------------------------------------------------------
def load_window(path, t0, dur, target_fs=TARGET_FS):
    """One channel, one time window, decimated. (x, fs) or (None, None)."""
    raw, t_actual, fs = nlx.read_ncs_range(path, t0, t0 + dur)
    if raw.size == 0:
        return None, None
    y, fs_d, _ = cfc.decimate_to(raw, fs, target_fs)
    lead = max(0, int(round((t0 - t_actual) * fs_d)))
    want = int(round(dur * fs_d))
    y = y[lead:lead + want]
    if y.size < want:
        y = np.concatenate([y, np.full(want - y.size, np.nan)])
    return y, fs_d


def screen_channels(sigs, nums):
    """Which channels are usable, and why the others are not.

    Two failures matter. A channel that is not recording sits near zero
    amplitude. A channel that is broken -- unplugged, railing, shorted --
    sits at an amplitude nothing like its neighbours. Both are caught on the
    standard deviation, compared against the other channels rather than an
    absolute threshold, because absolute microvolts differ per preparation.
    """
    sd = np.array([np.nanstd(s) if s is not None else np.nan for s in sigs])
    good = np.isfinite(sd) & (sd > FLAT_UV)
    reasons = {}
    for i, n in enumerate(nums):
        if sigs[i] is None:
            reasons[n] = "unreadable"
        elif not np.isfinite(sd[i]) or sd[i] <= FLAT_UV:
            reasons[n] = "flat (%.2f uV)" % (sd[i] if np.isfinite(sd[i]) else 0)

    if good.sum() > 3:
        l = np.log10(sd[good])
        med = np.median(l)
        mad = np.median(np.abs(l - med)) * 1.4826 or np.std(l) or 1.0
        for i, n in enumerate(nums):
            if not good[i]:
                continue
            dev = (np.log10(sd[i]) - med) / mad
            if abs(dev) > AMP_SD:
                good[i] = False
                reasons[n] = "amplitude %.0f uV, %+.1f SD from the others" \
                    % (sd[i], dev)
    return good, sd, reasons


def _runs(ch):
    """[2,4,6,20,22] -> '2-6, 20-22'. Contiguity is the point: a group that
    is a contiguous span of the probe is a layer, one that is scattered is
    a set of faults."""
    if not ch:
        return "-"
    out, a, b = [], ch[0], ch[0]
    for n in ch[1:]:
        if n - b <= 2:
            b = n
        else:
            out.append((a, b))
            a = b = n
    out.append((a, b))
    return ", ".join("%d" % a if a == b else "%d-%d" % (a, b) for a, b in out)


def channel_groups(cc, nums, min_sep=0.15):
    """Split the channels by who agrees with whom.

    The agreement matrix is not usually uniform, and the reason matters. A
    single row that agrees with nobody is a bad channel. A contiguous BLOCK
    of channels that agree with each other and not with the rest is anatomy:
    the probe has crossed into a different layer or structure, and the theta
    there is doing something genuinely different. The second case is the one
    that breaks pooling, because a median taken across the boundary averages
    two populations and describes neither.

    The split is the sign of the second eigenvector of the correlation
    matrix -- the standard spectral bisection, and the same quantity a
    clustered heatmap would be sorted by. `sep` is how much better channels
    agree inside their group than across the boundary; below `min_sep` there
    is no real split and the channels are treated as one population.
    """
    c = np.nan_to_num(cc, nan=0.0)
    if len(nums) < 4:
        return np.zeros(len(nums), dtype=int), 0.0
    _w, v = np.linalg.eigh(c)
    g = (v[:, -2] > 0).astype(int)
    if g.sum() == 0 or g.sum() == len(g):
        return np.zeros(len(nums), dtype=int), 0.0

    iu = np.triu_indices(len(nums), 1)
    same = g[iu[0]] == g[iu[1]]
    if not same.any() or same.all():
        return np.zeros(len(nums), dtype=int), 0.0
    sep = float(np.mean(c[iu][same]) - np.mean(c[iu][~same]))
    if sep < min_sep:
        return np.zeros(len(nums), dtype=int), sep
    # Label 0 = the larger group, so "group 0" is always the bulk.
    if g.sum() > len(g) / 2:
        g = 1 - g
    return g, sep


def fit_mean_spectra(freqs, mean_pxx, fit_range, mode, verbose=True):
    """One FOOOF fit per channel, on that channel's average spectrum.

    Per channel rather than per window: 32 fits instead of 3000, and the
    spectrum being fitted is an average over the whole snippet, so it is far
    smoother than any single window and the fit is correspondingly better.
    This is what the depth profiles are built from. --per-window adds the
    time-resolved version on top for the channels' osc traces.
    """
    n = mean_pxx.shape[1]
    out = {k: np.full(n, np.nan) for k in
           ("exponent", "offset", "r2", "theta_cf", "theta_pw",
            "theta_osc", "dom_all", "dom_all_pw")}
    if not mode:
        return out
    from fooof import FOOOF
    from fooof.sim.gen import gen_aperiodic

    for c in range(n):
        spec = mean_pxx[:, c]
        if not np.isfinite(spec).all() or (spec <= 0).any():
            continue
        fm = FOOOF(peak_width_limits=[1.0, 12.0], max_n_peaks=6,
                   min_peak_height=0.05, aperiodic_mode=mode, verbose=False)
        fm.fit(freqs, spec, fit_range)
        ap = gen_aperiodic(fm.freqs, fm.aperiodic_params_)
        tb = (fm.freqs >= THETA[0]) & (fm.freqs <= THETA[1])
        out["exponent"][c] = fm.aperiodic_params_[-1]
        out["offset"][c] = fm.aperiodic_params_[0]
        out["r2"][c] = fm.r_squared_
        out["theta_osc"][c] = np.mean(np.log10(spec)[
            (freqs >= THETA[0]) & (freqs <= THETA[1])][:tb.sum()] - ap[tb]) \
            if tb.sum() else np.nan
        if fm.n_peaks_:
            pk = np.atleast_2d(fm.peak_params_)
            inb = pk[(pk[:, 0] >= THETA_CF[0]) & (pk[:, 0] <= THETA_CF[1])]
            if len(inb):
                b = inb[np.argmax(inb[:, 1])]
                out["theta_cf"][c], out["theta_pw"][c] = b[0], b[1]
            b = pk[np.argmax(pk[:, 1])]
            out["dom_all"][c], out["dom_all_pw"][c] = b[0], b[1]
    if verbose:
        ok = np.isfinite(out["r2"])
        print("  per-channel fits: median R2 %.3f (worst %.3f)"
              % (np.nanmedian(out["r2"]), np.nanmin(out["r2"][ok])
                 if ok.any() else np.nan))
    return out


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default=FOLDER)
    ap.add_argument("--t0", type=float, default=200.0, help="window start (s)")
    ap.add_argument("--dur", type=float, default=100.0, help="window length (s)")
    ap.add_argument("--all", action="store_true",
                    help="every channel, not only the even ones")
    ap.add_argument("--sub", type=float, default=2.0)
    ap.add_argument("--win", type=float, default=8.0)
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--measure", default="ratio",
                    choices=["abs", "rel", "ratio"],
                    help="which measure the heatmap and consensus use")
    ap.add_argument("--z", type=float, default=1.5,
                    help="consensus threshold for an event")
    ap.add_argument("--min-dur", type=float, default=3.0)
    ap.add_argument("--fit-lo", type=float, default=2.0)
    ap.add_argument("--fit-hi", type=float, default=45.0)
    ap.add_argument("--knee", action="store_true")
    ap.add_argument("--no-fooof", action="store_true")
    ap.add_argument("--save", default=None)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    mode = None if args.no_fooof else ("knee" if args.knee else "fixed")

    # ---- which channels, and is "even" even the right question here ----
    scheme = nlx.channel_scheme(args.folder)
    print("channel scheme: %s -- %s" % (scheme["scheme"], scheme["why"]))
    even_only = not args.all
    if even_only and scheme["scheme"] == "all":
        print("  NOTE: this recording uses ALL channels, so --even is a "
              "spatial subsample,\n        not a free one. Half the probe is "
              "being ignored. Pass --all to use it.")
    files = nlx.list_csc_files(args.folder, even_only=even_only)
    if not files:
        sys.exit("no CSC files in " + args.folder)
    nums = [n for n, _ in files]
    print("  %d channels: %s" % (len(nums), nums[0:1] + ["..."] + nums[-1:]))

    # ---- read the snippet ----
    print("\nreading %g s from t=%g s ..." % (args.dur, args.t0))
    sigs, fs = [], None
    for _n, path in files:
        y, f = load_window(path, args.t0, args.dur)
        sigs.append(y)
        fs = f or fs
    good, sd, reasons = screen_channels(sigs, nums)
    print("  %d of %d channels usable" % (good.sum(), len(nums)))
    for n in sorted(reasons):
        print("    CSC%-3d excluded: %s" % (n, reasons[n]))
    if good.sum() < 2:
        sys.exit("too few usable channels")

    keep = np.flatnonzero(good)
    nums_ok = [nums[i] for i in keep]

    # ---- per channel: the spectrogram and the band measures ----
    freqs = times = None
    pxx_all, meas = [], {k: [] for k in ("abs", "rel", "ratio")}
    for i in keep:
        f, t, pxx, n_avg = make_spectrogram(sigs[i], fs, args.sub, args.win,
                                            args.step)
        freqs, times = f, t
        pxx_all.append(pxx)
        a = band_integral(f, pxx, *THETA)
        meas["abs"].append(a)
        meas["rel"].append(a / band_integral(f, pxx, *TOTAL))
        meas["ratio"].append(a / band_integral(f, pxx, *DELTA))
    pxx_all = np.stack(pxx_all, axis=2)              # freq x time x channel
    for k in meas:
        meas[k] = np.stack(meas[k], axis=1)          # time x channel
    print("  %d windows x %d channels, %.2f Hz bins"
          % (len(times), len(keep), freqs[1] - freqs[0]))

    # Each channel against ITSELF. This is what makes them poolable.
    zz = np.stack([robust_z(np.log10(meas[args.measure][:, c]))
                   for c in range(len(keep))], axis=1)

    # ---- the laminar profile, from one fit per channel ----
    mean_pxx = np.nanmean(pxx_all, axis=1)           # freq x channel
    prof = fit_mean_spectra(freqs, mean_pxx, [args.fit_lo, args.fit_hi], mode)

    # ---- does pooling these channels even make sense? ----
    cc = np.corrcoef(zz.T)
    grp, sep = channel_groups(cc, nums_ok)
    n_grp = len(np.unique(grp))
    if n_grp > 1:
        print("\n  TWO POPULATIONS of channels (separation %.2f): they do not"
              " agree\n  with each other, so one median across all of them "
              "describes neither." % sep)
        for g in range(n_grp):
            ch = [nums_ok[i] for i in np.flatnonzero(grp == g)]
            print("    group %d (%2d ch): %s" % (g, len(ch), _runs(ch)))
    else:
        print("\n  one population (agreement separation %.2f) -- pooling all "
              "%d channels" % (sep, len(keep)))

    # ---- consensus, per population ----
    # Median, not mean: one channel that survived screening but is still
    # noisier than the rest moves a mean and not a median.
    cons_by = {}
    for g in range(n_grp):
        sel = grp == g
        cons_by[g] = (np.nanmedian(zz[:, sel], axis=1),
                      np.nanpercentile(zz[:, sel], 25, axis=1),
                      np.nanpercentile(zz[:, sel], 75, axis=1),
                      int(sel.sum()))
    # Events are found on the largest group -- pooling across the boundary
    # is the thing the split just said not to do.
    cons, lo_q, hi_q, _n = cons_by[0]
    epochs = find_epochs(times, cons, args.z, args.min_dur, 2.0)
    epochs.sort(key=lambda e: e["z_mean"], reverse=True)

    print("\nCONSENSUS THETA EVENTS (median z over group 0, %d channels, "
          ">= %.1f for >= %.0f s)" % (cons_by[0][3], args.z, args.min_dur))
    if not epochs:
        # Not the same as "there was no theta". z is measured against this
        # snippet and nothing else, so it can only find moments that stand
        # out FROM THE SNIPPET. A 100 s window in which the animal did one
        # thing throughout has a flat z by construction, however much theta
        # it contains -- the absolute level is in the spectra below.
        print("  none. Note what that does and does not mean: z is relative "
              "to THIS %g s\n  window, so a snippet with no change in state "
              "has nothing unusual in it\n  by construction. Peak consensus "
              "reached %.2f. For events, either widen\n  the window (the "
              "single-channel script scores against the whole recording)\n"
              "  or lower --z." % (args.dur, np.nanmax(cons)))
    print("   #  start      end      dur   z med  | agree | theta Hz (spread)")
    for i, e in enumerate(epochs, 1):
        sl = slice(e["i0"], e["i1"])
        # How many channels individually cleared the bar during the event.
        # A brain state should carry almost all of them; 3 of 32 is one
        # channel's artifact that happened to move the median.
        agree = 100.0 * np.nanmean(np.nanmax(zz[sl], axis=0) >= args.z)
        pk = []
        for c in range(len(keep)):
            seg = pxx_all[:, sl, c].mean(axis=1)
            tb = (freqs >= THETA[0]) & (freqs <= THETA[1])
            pk.append(freqs[tb][np.argmax(seg[tb] / seg[tb].mean())])
        print("  %2d  %8s %8s %6.1fs %6.2f  | %4.0f%% | %.2f +- %.2f"
              % (i, mmss(e["t0"]), mmss(e["t1"]), e["dur"], e["z_mean"],
                 agree, np.median(pk), np.std(pk)))

    # ---- what the channels agree about ----
    print("\nACROSS CHANNELS (median +- spread over %d good channels)"
          % len(keep))
    print("  theta power 4-12 Hz   %8.1f uV^2   range %.0f-%.0f  <- NOT "
          "averaged, see header" % (np.nanmedian(meas["abs"]),
                                    np.nanmin(np.nanmedian(meas["abs"], axis=0)),
                                    np.nanmax(np.nanmedian(meas["abs"], axis=0))))
    if mode:
        for key, lab, unit in (("theta_cf", "theta peak frequency", "Hz"),
                               ("exponent", "aperiodic exponent", ""),
                               ("dom_all", "loudest rhythm overall", "Hz")):
            v = prof[key][np.isfinite(prof[key])]
            if v.size:
                print("  %-21s %8.2f %-5s  spread %.2f  (%d/%d channels)"
                      % (lab, np.median(v), unit, np.std(v), v.size, len(keep)))
        nb = [band_of(f) for f in prof["dom_all"]]
        names, counts = np.unique(nb, return_counts=True)
        print("  loudest rhythm sat in: "
              + ", ".join("%s on %d ch" % (names[k], counts[k])
                          for k in np.argsort(-counts)))

    if n_grp > 1:
        print("\n  THE SAME NUMBERS PER POPULATION (this is the split that "
              "matters)")
        print("    group   n   theta uV^2   theta Hz   exponent   peak height")
        for g in range(n_grp):
            sel = grp == g
            print("      %d   %3d   %10.0f   %8.2f   %8.2f   %11.2f"
                  % (g, sel.sum(),
                     np.nanmedian(np.nanmedian(meas["abs"], axis=0)[sel]),
                     np.nanmedian(prof["theta_cf"][sel]),
                     np.nanmedian(prof["exponent"][sel]),
                     np.nanmedian(prof["theta_pw"][sel])))

    # Agreement between channels: does the theta time course look the same
    # everywhere? This is the number that says whether pooling was justified.
    iu = np.triu_indices(len(keep), 1)
    print("  pairwise correlation of the theta trace: median r = %+.2f "
          "(%.0f%% of pairs above 0.5)"
          % (np.median(cc[iu]), 100.0 * np.mean(cc[iu] > 0.5)))
    worst = np.argsort(np.nanmean(cc, axis=1))[:3]
    print("  least typical channels: "
          + ", ".join("CSC%d (mean r %+.2f)" % (nums_ok[w], np.nanmean(cc[w]))
                      for w in worst))

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csvmod.writer(fh)
            w.writerow(["channel", "sd_uV", "theta_abs_median", "exponent",
                        "offset", "r2", "theta_cf", "theta_pw", "dom_all_hz",
                        "dom_all_band", "mean_r_with_others"])
            for c, n in enumerate(nums_ok):
                w.writerow([n, "%.1f" % sd[keep[c]],
                            "%.4g" % np.nanmedian(meas["abs"][:, c])]
                           + ["%.4f" % prof[k][c] for k in
                              ("exponent", "offset", "r2", "theta_cf",
                               "theta_pw", "dom_all")]
                           + [band_of(prof["dom_all"][c]),
                              "%.3f" % np.nanmean(cc[c])])
        print("\n  wrote " + args.csv)

    title = "%s   %d channels, %g-%g s" % (
        os.path.basename(args.folder.rstrip("\\/")), len(keep),
        args.t0, args.t0 + args.dur)
    fig = plot_channels(freqs, times, pxx_all, mean_pxx, zz, cons_by, cc,
                        prof, meas, nums_ok, epochs, grp, sep, args, title)
    if args.save:
        fig.savefig(args.save, dpi=125, bbox_inches="tight")
        print("  wrote " + args.save)
    else:
        plt.show()


# --------------------------------------------------------------------------
GRP_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e"]


def plot_channels(freqs, times, pxx_all, mean_pxx, zz, cons_by, cc,
                  prof, meas, nums, epochs, grp, sep, args, title):
    nch = len(nums)
    n_grp = len(np.unique(grp))
    ext_t = [times[0], times[-1], -0.5, nch - 0.5]
    fig = plt.figure(figsize=(15, 17))
    gs = fig.add_gridspec(4, 6, height_ratios=[1.5, 0.8, 1.5, 1.3],
                          hspace=0.42, wspace=0.75,
                          left=0.06, right=0.97, top=0.955, bottom=0.05)

    def chan_ticks(ax):
        step = max(1, nch // 16)
        ax.set_yticks(np.arange(0, nch, step))
        ax.set_yticklabels([nums[i] for i in range(0, nch, step)], fontsize=7)

    # -- 1. the plot to read first: channel x time
    ax = fig.add_subplot(gs[0, :4])
    im = ax.imshow(zz.T, aspect="auto", origin="lower", extent=ext_t,
                   cmap="RdBu_r", vmin=-3, vmax=3, interpolation="nearest")
    for e in epochs:
        ax.axvline(e["t0"], color="k", lw=0.8, ls=":")
        ax.axvline(e["t1"], color="k", lw=0.8, ls=":")
    chan_ticks(ax)
    ax.set_ylabel("channel")
    ax.set_xlabel("time (s)")
    # Mark where the populations meet: the band structure in this panel is
    # the thing the correlation matrix found, and it is easier to believe
    # when the two are drawn with the same boundary.
    for i in range(1, nch):
        if grp[i] != grp[i - 1]:
            ax.axhline(i - 0.5, color="lime", lw=1.4)
    ax.set_title("theta (%s), each channel z-scored against ITSELF.\n"
                 "Vertical stripe = a brain state. A contiguous BLOCK of "
                 "channels = anatomy (green line)." % args.measure,
                 fontsize=10)
    fig.colorbar(im, ax=ax, pad=0.01, label="robust z")

    # -- 2. do the channels agree with each other
    ax = fig.add_subplot(gs[0, 4:])
    im = ax.imshow(cc, cmap="viridis", vmin=0, vmax=1, origin="lower",
                   interpolation="nearest")
    chan_ticks(ax)
    ax.set_xticks(ax.get_yticks())
    ax.set_xticklabels(ax.get_yticklabels(), rotation=90)
    ax.set_xlim(-0.5, nch - 0.5)
    for i in range(1, nch):
        if grp[i] != grp[i - 1]:
            ax.axhline(i - 0.5, color="lime", lw=1.2)
            ax.axvline(i - 0.5, color="lime", lw=1.2)
    ax.set_title("agreement: correlation of the theta\ntrace between "
                 "channels (%s, separation %.2f)"
                 % ("2 populations" if n_grp > 1 else "one population", sep),
                 fontsize=10)
    fig.colorbar(im, ax=ax, pad=0.02, label="r")

    # -- 3. the consensus, one per population
    ax = fig.add_subplot(gs[1, :4])
    for g in sorted(cons_by):
        cons, lo_q, hi_q, n = cons_by[g]
        col = GRP_COLORS[g % len(GRP_COLORS)]
        ax.fill_between(times, lo_q, hi_q, color=col, alpha=0.2, lw=0)
        ax.plot(times, cons, color=col, lw=1.6,
                label=("median of group %d (n=%d)" % (g, n)) if n_grp > 1
                else "median channel (n=%d)" % n)
    ax.axhline(args.z, color="k", ls="--", lw=0.8)
    for e in epochs:
        ax.axvspan(e["t0"], e["t1"], color="cyan", alpha=0.2, lw=0)
    ax.set_xlim(times[0], times[-1])
    ax.set_ylabel("robust z")
    ax.set_xlabel("time (s)")
    ax.legend(fontsize=7, loc="upper right")
    ax.set_title("consensus theta per population -- a median is a statement "
                 "about brain state, not field strength", fontsize=10)

    # -- 3b. amplitude profile reminder (why raw power was not pooled)
    ax = fig.add_subplot(gs[1, 4:])
    tp = np.nanmedian(meas["abs"], axis=0)
    ax.plot(tp, np.arange(nch), "-", color="#999999", lw=1, zorder=1)
    for g in range(n_grp):
        sel = grp == g
        ax.plot(tp[sel], np.flatnonzero(sel), "o", ms=4, zorder=2,
                color=GRP_COLORS[g % len(GRP_COLORS)])
    ax.set_xscale("log")
    chan_ticks(ax)
    ax.set_xlabel("theta power ($\\mu V^2$)")
    ax.set_title("raw theta power by channel\n(%.0fx spread -- this is why "
                 "it is not\naveraged)" % (np.nanmax(tp) / max(np.nanmin(tp), 1e-9)),
                 fontsize=9)
    ax.grid(alpha=0.3)

    # -- 4. the laminar spectrum
    ax = fig.add_subplot(gs[2, :3])
    show = (freqs >= 1) & (freqs <= 60)
    im = ax.pcolormesh(freqs[show], np.arange(nch),
                       np.log10(mean_pxx[show].T), cmap="magma",
                       shading="nearest")
    ax.axvline(THETA[0], color="w", lw=0.8, ls=":")
    ax.axvline(THETA[1], color="w", lw=0.8, ls=":")
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 4, 8, 12, 20, 40, 60])
    ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
    chan_ticks(ax)
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("channel")
    ax.set_title("spectrum of every channel over the snippet\n"
                 "(the laminar profile; dotted = theta)", fontsize=10)
    fig.colorbar(im, ax=ax, pad=0.01, label="log10 power")

    # -- 5. all spectra as lines, so the shape is visible
    ax = fig.add_subplot(gs[2, 3:])
    for c in range(nch):
        ax.plot(freqs, mean_pxx[:, c], lw=0.6, alpha=0.45,
                color=plt.cm.viridis(c / max(1, nch - 1)))
    ax.plot(freqs, np.nanmedian(mean_pxx, axis=1), lw=2.0, color="k",
            label="median channel")
    ax.axvspan(THETA[0], THETA[1], color="#17becf", alpha=0.12, lw=0)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1, FMAX)
    ax.set_xticks([1, 2, 4, 8, 12, 20, 40, 60, 100])
    ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("power ($\\mu V^2$/Hz)")
    ax.legend(fontsize=7)
    ax.set_title("the same spectra as lines, coloured by channel\n"
                 "(shaded = theta)", fontsize=10)

    # -- 6. the three depth profiles
    panels = [("theta_cf", "theta peak (Hz)", "#17becf", None),
              ("exponent", "aperiodic exponent", "#9467bd", None),
              ("theta_pw", "theta peak height\n(log10 over 1/f)", "#d62728",
               None)]
    for k, (key, lab, col, _x) in enumerate(panels):
        ax = fig.add_subplot(gs[3, 2 * k:2 * k + 2])
        v = prof[key]
        ax.plot(v, np.arange(nch), "-", lw=1, color="#bbbbbb", zorder=1)
        for g in range(n_grp):
            sel = grp == g
            ax.plot(v[sel], np.flatnonzero(sel), "o", ms=4, zorder=2,
                    color=GRP_COLORS[g % len(GRP_COLORS)] if n_grp > 1
                    else col)
        fin = np.isfinite(v)
        if fin.any():
            ax.axvline(np.median(v[fin]), color="k", ls="--", lw=0.9)
            ax.set_title("%s\nmedian %.2f, spread %.2f"
                         % (lab, np.median(v[fin]), np.std(v[fin])),
                         fontsize=9.5)
        else:
            ax.set_title(lab + "\n(needs FOOOF)", fontsize=9.5)
        chan_ticks(ax)
        if k == 0:
            ax.set_ylabel("channel")
        ax.grid(alpha=0.3)
        ax.set_xlabel(lab.split("\n")[0])

    fig.suptitle(title, y=0.985, fontsize=12)
    return fig


if __name__ == "__main__":
    main()
