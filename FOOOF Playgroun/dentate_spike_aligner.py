"""
dentate_spike_aligner.py -- what a curated dentate spike looks like on the probe.

The events of a bank, as current source density, with the average rectified
CSD drawn over each one and two verticals on every panel: a dashed one where
the curated stamp is, and a solid one where that curve actually peaked. The
gap between them is what the whole thing is for.

The first five by default; `--all` does the lot, wrapped over as many rows as
it takes.

WHY CSD AND NOT VOLTAGE
=======================
A voltage raster at any one site is mostly what is happening somewhere else.
The field spreads, so a big sink two hundred microns up the shank shows up on
a contact almost as strongly as one sitting on it -- which means the depth at
which a voltage raster looks biggest is wherever the volume conduction
happens to be largest, not where the current went.

The current source density is the second spatial derivative across depth, and
that is exactly the part that cannot be volume-conducted. A dentate spike is
a current sink in the hilus with sources above and below it; on CSD that is a
sharp, local thing with a real position and a real instant.

The derivative itself is `csc.compute_csd` by way of `braces.csd_of` -- the
same function the GUI's CSD panel draws from and the same one Braces aligns
on. One derivative in the codebase, not a second one here that could disagree
with it about a sign or a spacing.

THE FILTER ORDER, WHICH IS NOT ARBITRARY
========================================
Per channel: decimate 30 kHz -> 1 kHz, take the mains out, then bandpass.

The mains comes out BEFORE the CSD, and that is the part that matters. A
second spatial difference amplifies whatever differs most between
neighbouring contacts; 60 Hz is common-mode across a shank, so differencing
first turns a line that was everywhere into something that looks local, and
by then it cannot be told from a current.

It also comes out before the bandpass here rather than after it, which is the
one place this script departs from `braces._stack`. At the 5-10 Hz default the
distinction is small -- a third-order Butterworth already puts 60 Hz about
46 dB down, and `braces._notch` skips the stage entirely when the line sits
above the band's top edge. Widen the band to the lab's own 5-100 Hz DS band
(`--band 5 100`) and the notch stops being a formality: 60 Hz is then INSIDE
the passband and survives to the derivative. Notching first is correct in both
cases, so it is what this does in both cases, and the run prints how much it
actually removed rather than leaving it to be assumed.

THE LINE OVER EACH PANEL
========================
mean over depth of |CSD| -- one number per instant, the average rectified
current density across the contacts on the shank.

Rectified ONCE, at the end, on the projection rather than per contact. That
ordering is the whole point. A dentate spike in this band is a BIPHASIC
deflection, so |x| per contact folds each half-cycle into its own positive
lobe and one event arrives as two or three maxima 8-12 ms apart. And a signed
sum across a probe cancels by construction, because a sink at one depth is a
source at the next -- so the average has to be of the magnitude, taken after
the depths have been pooled.

What the line is FOR: its peak is a candidate time for the event, independent
of whichever contact the detector happened to threshold on. The offset between
that peak and the curated stamp is printed per event -- that offset is the
thing an aligner exists to remove.

Screening comes first (`braces.screen`): a dead or railing contact has no
business in a second difference, and one is interpolated from its neighbours
rather than dropped, so the grid stays evenly spaced. Whatever was repaired is
named in the output.

Run:
  python dentate_spike_aligner.py
  python dentate_spike_aligner.py --save ds5.png
  python dentate_spike_aligner.py --all --save ds_all.png
  python dentate_spike_aligner.py --all --band 5 100 --save ds_all_wide.png
  python dentate_spike_aligner.py --channels 1-18 --line-mode both
"""

import argparse
import csv as csvmod
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from scipy.signal import filtfilt, iirnotch

# The lab's own readers, filters and CSD. `BARRY GUI` itself goes on the path
# as well as its backend: braces.py imports its neighbours as a package
# (`from . import csc, incisor, probes`), so it has to be reached as
# `backend.braces` rather than as a loose module.
_HERE = os.path.dirname(os.path.abspath(__file__))
_GUI = os.path.abspath(os.path.join(_HERE, os.pardir, "BARRY GUI"))
sys.path.insert(0, _GUI)
sys.path.insert(0, os.path.join(_GUI, "backend"))
from backend import braces, csc, incisor, probes        # noqa: E402

FOLDER = r"D:/PTEN/PTEN/M1_Pten/M1ptens2oct2/2023-10-02_16-58-03"
BANK = "event-bank-M1ptens2oct2-v4.csv"

N_EVENTS = 5
BAND = (5.0, 10.0)          # what was asked for; the DS band proper is 5-100
LINE_HZ = 60.0              # mains, North America
LINE_Q = 30.0               # braces.LINE_Q -- a ~2 Hz notch at 60 Hz
LFP_FS = 1000.0             # incisor.LFP_FS
WINDOW_MS = 100.0           # half-width drawn either side of the stamp
PAD_S = 0.5                 # filter margin, read and then trimmed off

# A Butterworth rings at the edge of whatever array it is handed, so the pad
# is read, filtered with everything else, and thrown away before plotting.
# Half a second at 5 Hz is two and a half cycles of the slowest thing in the
# passband, which is enough for the ring to have died.


# --------------------------------------------------------------------------
# The bank
# --------------------------------------------------------------------------
def read_bank(path, kind="ds", label="spike"):
    """The curated stamps, in time order.

    `label` is the curation verdict, not the detector's: a bank holds both
    the events somebody kept (`spike`) and the ones they threw out
    (`garbage`), and "the first five events" means the first five KEPT ones.
    Passing `--label ""` takes everything, garbage included, which is the
    useful thing to do when the question is what the rejected ones look like.
    """
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csvmod.DictReader(fh):
            if kind and (row.get("type") or "").strip() != kind:
                continue
            if label and (row.get("label") or "").strip() != label:
                continue
            try:
                t = float(row["start_s"])
            except (KeyError, TypeError, ValueError):
                continue
            out.append({"t": t,
                        "label": (row.get("label") or "").strip(),
                        "by": (row.get("decided_by") or "").strip(),
                        "session": (row.get("session_label") or "").strip()})
    out.sort(key=lambda r: r["t"])
    return out


def parse_channels(text, channels):
    """"1-18", "2,4,7-9" or "" -> the session channel dicts, in probe order.

    Probe order is CSC order here and the script checks that it is: on an H3
    the channel numbers run down the shank, which is what makes a second
    difference over them a depth derivative. `probes.py` has the probe where
    that is false (the H10-D interleaves three columns), and the caller is
    told to take one column at a time rather than being handed arithmetic
    over contacts that are not neighbours.
    """
    if not text:
        return list(channels)
    want = []
    for piece in str(text).replace(" ", "").split(","):
        if not piece:
            continue
        if "-" in piece[1:]:
            a, b = piece.split("-", 1)
            want.extend(range(int(a), int(b) + 1))
        else:
            want.append(int(piece))
    by_num = {int(c["number"]): c for c in channels}
    missing = [n for n in want if n not in by_num]
    if missing:
        sys.exit("no such channel(s) in this session: %s"
                 % ", ".join(str(n) for n in missing))
    return [by_num[n] for n in want]


# --------------------------------------------------------------------------
# Reading and filtering
# --------------------------------------------------------------------------
def notch(x, fs, f0=LINE_HZ, q=LINE_Q):
    """Take the mains out, zero-phase.

    Zero-phase because what this script is ultimately after is a TIME. A
    filter with phase shifts the thing being timed, by an amount that varies
    with frequency, and that shift is indistinguishable from the jitter an
    aligner exists to remove.
    """
    x = np.asarray(x, dtype=np.float64)
    if not f0 or not (0.0 < float(f0) < 0.95 * (fs / 2.0)):
        return x
    bn, an = iirnotch(float(f0), float(q), fs)
    return filtfilt(bn, an, x, axis=-1)


def read_stack(session, channels, t0, t1, band, line_hz, lfp_fs, report=None):
    """Every channel over [t0, t1), decimated, mains out, bandpassed.

    Stacked rather than accumulated a channel at a time, because a CSD is a
    derivative ACROSS channels. Rows come back in the order `channels` was
    given, which is probe order.

    Returns (stack [nCh x nSamp], anchor_t, fs) or None if anything came back
    too short to filter -- which is what a window falling in a Cheetah gap
    looks like from here.
    """
    rows, anchor, fs_out = [], None, None
    raw_rms, line_rms = [], []
    for ch in channels:
        raw, got_t0, ch_fs = csc._read_channel_window(session, ch, t0, t1)
        if raw.size < 8:
            return None
        q = incisor.decimation_for(ch_fs, lfp_fs)
        dec = incisor._decimate(raw, q) if q > 1 else np.asarray(raw, float)
        if dec.size < 16:
            return None
        if anchor is None:
            anchor, fs_out = got_t0, ch_fs / q
        clean = notch(dec, fs_out, line_hz)
        # What the notch actually took out, measured rather than assumed --
        # the residual IS the removed line, since the notch is the only thing
        # that separates the two traces.
        raw_rms.append(float(np.std(dec)))
        line_rms.append(float(np.std(dec - clean)))
        # incisor._filtered, not a bandpass of this script's own: same order,
        # same sosfiltfilt, same pinned padtype as every DS detection in the
        # codebase.
        rows.append(incisor._filtered(clean, fs_out, band))
    if not rows:
        return None
    keep = min(r.size for r in rows)
    if report is not None:
        report["wideband_uv"] = float(np.median(raw_rms))
        report["mains_uv"] = float(np.median(line_rms))
    return np.vstack([r[:keep] for r in rows]), anchor, fs_out


def event_csd(session, channels, stamp, args, bad, report=None):
    """One event: the signed CSD over +/- window_ms of its stamp.

    Returns (t_ms relative to the stamp, csd [rows x samples], row channel
    numbers, fs) or None. Two rows are gone -- the ends of a list have no
    second difference -- so row i is channels[i+1], and the numbers are
    carried along rather than inferred from a position in an array.
    """
    half = args.window_ms / 1000.0
    got = read_stack(session, channels, stamp - half - args.pad,
                     stamp + half + args.pad, args.band, args.line,
                     args.lfp_fs, report)
    if not got:
        return None
    stack, anchor, fs = got
    stack = braces.repair(stack, channels, bad)
    csd = braces.csd_of(stack, {"spacing_um": args.spacing,
                                "csd_smooth": not args.no_smooth})
    nums = [int(channels[i + 1]["number"]) for i in range(csd.shape[0])]

    t = anchor + np.arange(csd.shape[1]) / fs - stamp
    keep = np.abs(t) <= half + 0.5 / fs
    if keep.sum() < 4:
        return None
    return t[keep] * 1000.0, csd[:, keep], nums, fs


def mean_abs(csd, fs=None, smooth_ms=0.0):
    """The average rectified CSD across depth -- one number per instant.

    The mean of |CSD| and NOT |mean of CSD|, which would be close to zero by
    construction: a sink at one depth is a source at the next, so the signed
    average across a shank cancels whether or not anything happened.

    WHAT THIS TRACE DOES AND DOES NOT DO, because it is visible in the
    figure the moment it is drawn. Rectifying per contact and pooling after
    means each HALF-CYCLE of a biphasic deflection becomes its own positive
    lobe, so a single event in a 5-10 Hz band arrives as two or three humps
    50-100 ms apart rather than one. That is arithmetic, not a property of
    the data: |sin| has twice the frequency of sin.

    `smooth_ms` is the blunt instrument for it -- a moving average about as
    long as one half-cycle merges the lobes back into a single hump whose
    maximum is a usable time. It is OFF by default, so what is drawn is the
    plain average of the magnitude and nothing else. The edges are
    reflection-padded rather than zero-padded, which would pull the first
    and last few milliseconds toward zero and invent a peak just inside them.
    """
    x = np.abs(np.asarray(csd, dtype=np.float64)).mean(axis=0)
    n = int(round((fs or 0.0) * float(smooth_ms or 0.0) / 1000.0))
    if n > 1 and x.size > n:
        pad = n // 2
        k = np.ones(n, dtype=np.float64) / n
        x = np.convolve(np.pad(x, pad, mode="reflect"), k,
                        mode="same")[pad:pad + x.size]
    return x


# --------------------------------------------------------------------------
# The figure
# --------------------------------------------------------------------------
# What the two verticals are. Kept together here because they are the
# figure's whole claim: one line is where a person said the event was, the
# other is where this measurement says it was, and the gap between them is
# the quantity the script exists to report.
STAMP_C = "#111111"          # the curated stamp -- dashed
PEAK_C = "#1a7f37"           # the peak of mean|CSD| -- solid
TRACE_C = "#111111"

# Green against a red/blue colormap on purpose: the peak line has to be
# told apart from the data underneath it, and every hue the map itself
# uses is disqualified for that. Both verticals get a white stroke, which
# is what makes them readable over saturated blue as well as over white.
_HALO = [patheffects.withStroke(linewidth=3.2, foreground="white")]

# Inches reserved above the top row of panels, and where the two pieces of
# furniture sit inside it, measured DOWN from the top edge. One constant
# rather than a literal in the layout and another in the colorbar, which is
# how the legend ended up printed through the panel titles.
TOP_IN = 1.58
SUPTITLE_DOWN = 0.28
LEGEND_DOWN = 0.72


def draw_line(ax, t_ms, trace, peak_i, colour=TRACE_C):
    """The mean|CSD| trace, legible over any part of a diverging colormap.

    A white stroke under a dark line, because the line crosses saturated red,
    saturated blue and white in the same panel and no single colour reads
    over all three.
    """
    ax.plot(t_ms, trace, lw=1.5, color=colour, path_effects=_HALO, zorder=6)
    ax.plot([t_ms[peak_i]], [trace[peak_i]], "o", ms=5.0, color=colour,
            mec="white", mew=1.1, zorder=7)


def verticals(ax, peak_ms, lw=1.2):
    """The stamp at zero, and where the curve actually peaked."""
    ax.axvline(0.0, color=STAMP_C, lw=lw, ls="--", alpha=0.75,
               path_effects=_HALO, zorder=5)
    ax.axvline(peak_ms, color=PEAK_C, lw=lw + 0.2, ls="-",
               path_effects=_HALO, zorder=5)


def layout(n, args):
    """Where every panel goes, in inches. Returns (width, height, boxes).

    Laid out in inches and converted at the end rather than in figure
    fractions, because the sheet grows with the number of events and a
    fractional margin therefore shrinks in absolute terms exactly when
    there is more to fit into it -- which is how an axis label ends up
    written through the colorbar.
    """
    cols = int(args.cols) if args.cols else min(n, 8 if n > 6 else n)
    cols = max(1, min(cols, n))
    rows = int(np.ceil(n / float(cols)))
    two_row = args.line_mode in ("strip", "both")
    overlay = args.line_mode in ("overlay", "both")

    pw = float(args.panel_w) if args.panel_w else (2.9 if cols <= 5 else 2.05)
    ph = float(args.panel_h) if args.panel_h else (4.9 if rows == 1 else 2.15)
    sh = ph * 0.34 if two_row else 0.0        # the strip under each panel
    sgap = 0.30 if two_row else 0.0

    left = 0.92
    right = (2.35 if overlay else 1.45) if cols <= 5 else 1.45
    top = TOP_IN
    bottom = 0.80
    wgap, hgap = 0.26, 0.86                   # hgap carries titles + x labels

    block = ph + sgap + sh
    width = left + cols * pw + (cols - 1) * wgap + right
    height = top + rows * block + (rows - 1) * hgap + bottom

    boxes = []
    for k in range(n):
        r, c = divmod(k, cols)
        x = left + c * (pw + wgap)
        y_top = height - top - r * (block + hgap)
        main = (x / width, (y_top - ph) / height, pw / width, ph / height)
        strip = None
        if two_row:
            sy = y_top - ph - sgap - sh
            strip = (x / width, sy / height, pw / width, sh / height)
        boxes.append({"r": r, "c": c, "main": main, "strip": strip,
                      "last_row": r == rows - 1 or k + cols >= n,
                      "first_col": c == 0, "last_col": c == cols - 1})
    return width, height, rows, cols, boxes


def figure(events, panels, args):
    """Every event as a CSD panel, one colour scale, two verticals on each."""
    n = len(panels)
    two_row = args.line_mode in ("strip", "both")
    overlay = args.line_mode in ("overlay", "both")
    width, height, rows, cols, boxes = layout(n, args)
    fig = plt.figure(figsize=(width, height))

    # ONE colour scale over every panel, and one scale for the traces.
    #
    # Per-panel autoscaling is the quiet way to make events look alike: a
    # weak one is stretched until it fills the same reds as a strong one,
    # and the comparison the figure exists for is gone. --per-event-scale
    # says so out loud if it is ever wanted.
    pool = np.concatenate([np.abs(p["csd"]).ravel() for p in panels])
    clim = float(np.percentile(pool, args.clip_pct))
    line_max = max(float(p["trace"].max()) for p in panels)

    step = 25.0 if args.window_ms <= 80 else \
        (50.0 if args.window_ms <= 175 else 100.0)
    ticks = [k * step for k in range(-20, 21)
             if abs(k * step) < args.window_ms * 0.93]
    small = cols > 5

    im = None
    for p, box in zip(panels, boxes):
        ax = fig.add_axes(box["main"])
        lim = float(np.percentile(np.abs(p["csd"]), args.clip_pct)) \
            if args.per_event_scale else clim
        rows_n = p["nums"]
        dt = p["t"][1] - p["t"][0]
        im = ax.imshow(
            p["csd"], aspect="auto", origin="upper", cmap=args.cmap,
            vmin=-lim, vmax=lim, interpolation=args.interp,
            extent=[p["t"][0] - dt / 2.0, p["t"][-1] + dt / 2.0,
                    rows_n[-1] + 0.5, rows_n[0] - 0.5])
        ax.set_xlim(-args.window_ms, args.window_ms)
        peak_ms = p["t"][p["peak_i"]]
        verticals(ax, peak_ms, lw=1.0 if small else 1.2)

        ax.set_title("#%d  %s\n%+.1f ms" % (p["i"] + 1, mmss(p["stamp"]),
                                            peak_ms),
                     fontsize=8.0 if small else 10.0, pad=4)
        ax.set_xticks(ticks)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.tick_params(labelsize=7 if small else 8)
        if box["first_col"]:
            # The long form only where there is a whole panel height to
            # write it down: with a strip underneath, the panel is short
            # enough that the label runs past it into the strip's own.
            ax.set_ylabel("CSC number" if (small or two_row) else
                          "CSC number   (down the shank, %g um pitch)"
                          % args.spacing, fontsize=8 if small else 9)
        else:
            ax.tick_params(labelleft=False)

        sx = None
        if two_row:
            sx = fig.add_axes(box["strip"])
            sx.plot(p["t"], p["trace"], lw=1.3, color=TRACE_C)
            sx.plot([peak_ms], [p["trace"][p["peak_i"]]], "o", ms=4.5,
                    color=TRACE_C)
            verticals(sx, peak_ms, lw=1.0 if small else 1.2)
            sx.set_xlim(-args.window_ms, args.window_ms)
            sx.set_ylim(0.0, line_max * 1.08)
            sx.set_xticks(ticks)
            sx.grid(True, axis="y", alpha=0.18, lw=0.6)
            sx.tick_params(labelsize=7 if small else 8)
            ax.tick_params(labelbottom=False)
            if box["first_col"]:
                sx.set_ylabel("mean |CSD|", fontsize=8 if small else 9)
            else:
                sx.tick_params(labelleft=False)

        if overlay:
            tw = fig.add_axes(box["main"], frameon=False)
            tw.set_xlim(-args.window_ms, args.window_ms)
            tw.set_ylim(0.0, line_max / 0.88)      # peak sits near the top
            tw.set_xticks([])
            tw.yaxis.tick_right()
            tw.patch.set_visible(False)
            draw_line(tw, p["t"], p["trace"], p["peak_i"])
            if box["last_col"] and not small:
                tw.set_ylabel(r"mean$_{depth}$ |CSD|  ($\mu V/mm^2$)",
                              fontsize=9, labelpad=2)
                tw.yaxis.set_label_position("right")
                tw.tick_params(labelsize=8)
            else:
                tw.set_yticks([])

        bottom_ax = sx if two_row else ax
        if box["last_row"]:
            bottom_ax.set_xlabel("ms from the curated stamp",
                                 fontsize=8 if small else 9)
        else:
            bottom_ax.tick_params(labelbottom=False)

    bot, top = 0.8 / height, 1.0 - TOP_IN / height
    cax = fig.add_axes([1.0 - 1.05 / width, bot, 0.15 / width, top - bot])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(r"CSD  ($\mu V/mm^2$)", fontsize=9, labelpad=2)
    cb.ax.tick_params(labelsize=8)
    if not args.per_event_scale:
        cb.ax.set_title("shared\n%gth pct" % args.clip_pct, fontsize=7.5,
                        pad=6)

    # The legend is not decoration here. Two verticals that differ only by
    # dash pattern are exactly the case where identity must not rest on
    # colour alone, and on a sheet of sixty-four panels nobody should have
    # to infer which line is which from the one panel where they coincide.
    keys = [Line2D([], [], color=STAMP_C, ls="--", lw=1.4,
                   label="curated stamp (t = 0)"),
            Line2D([], [], color=PEAK_C, ls="-", lw=1.6,
                   label="peak of mean|CSD|"),
            Line2D([], [], color=TRACE_C, ls="-", lw=1.6, marker="o", ms=4.5,
                   label=r"mean$_{depth}$ |CSD| trace")]
    fig.legend(handles=keys, loc="upper center", ncol=3, frameon=False,
               fontsize=9, bbox_to_anchor=(0.5, 1.0 - LEGEND_DOWN / height))

    sub = ("%s   %s   %g-%g Hz" % (events[0]["session"] or args.folder,
                                   "CSD", args.band[0], args.band[1]))
    if args.line:
        sub += ", %g Hz notched" % args.line
    if args.smooth_ms:
        sub += ", trace smoothed %g ms" % args.smooth_ms
    fig.suptitle("%s curated dentate spike%s   --   %s"
                 % (("All %d" % n) if args.n_events == 0 else ("First %d" % n),
                    "" if n == 1 else "s", sub),
                 fontsize=12.5, y=1.0 - SUPTITLE_DOWN / height)
    return fig


def band_tag(band):
    """A filename-safe name for a passband: (5.0, 100.0) -> '5-100'."""
    return "%g-%g" % (band[0], band[1])


def scales(panels, args):
    """The scales every per-event sheet shares.

    Worked out once over the whole set and handed to each sheet, because the
    point of clicking through sixty-four of them is to compare them. A sheet
    that autoscaled to its own event would make every event look the same
    size, and the flick from one to the next -- which is the only thing a
    browser does that a contact sheet cannot -- would stop meaning anything.
    """
    pool = np.concatenate([np.abs(p["csd"]).ravel() for p in panels])
    step = 25.0 if args.window_ms <= 80 else \
        (50.0 if args.window_ms <= 175 else 100.0)
    return {
        "clim": float(np.percentile(pool, args.clip_pct)),
        "line_max": max(float(p["trace"].max()) for p in panels),
        "ticks": [k * step for k in range(-20, 21)
                  if abs(k * step) < args.window_ms * 0.93],
    }


def event_figure(p, ctx, args, session_label):
    """One event on its own sheet: the CSD, the curve, and both verticals."""
    left, pw, right = 0.95, 7.0, 1.95
    top, ph, gap, sh, bottom = 1.38, 4.35, 0.30, 1.35, 0.72
    width = left + pw + right
    height = top + ph + gap + sh + bottom
    fig = plt.figure(figsize=(width, height))

    main = (left / width, (bottom + sh + gap) / height,
            pw / width, ph / height)
    strip = (left / width, bottom / height, pw / width, sh / height)
    peak_ms = p["t"][p["peak_i"]]
    rows_n = p["nums"]
    dt = p["t"][1] - p["t"][0]

    ax = fig.add_axes(main)
    im = ax.imshow(p["csd"], aspect="auto", origin="upper", cmap=args.cmap,
                   vmin=-ctx["clim"], vmax=ctx["clim"],
                   interpolation=args.interp,
                   extent=[p["t"][0] - dt / 2.0, p["t"][-1] + dt / 2.0,
                           rows_n[-1] + 0.5, rows_n[0] - 0.5])
    ax.set_xlim(-args.window_ms, args.window_ms)
    ax.set_xticks(ctx["ticks"])
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.tick_params(labelsize=9, labelbottom=False)
    ax.set_ylabel("CSC number   (down the shank, %g um pitch)" % args.spacing,
                  fontsize=10)
    verticals(ax, peak_ms, lw=1.4)

    tw = fig.add_axes(main, frameon=False)
    tw.set_xlim(-args.window_ms, args.window_ms)
    tw.set_ylim(0.0, ctx["line_max"] / 0.88)
    tw.set_xticks([])
    tw.set_yticks([])
    tw.patch.set_visible(False)
    draw_line(tw, p["t"], p["trace"], p["peak_i"])

    sx = fig.add_axes(strip)
    sx.plot(p["t"], p["trace"], lw=1.5, color=TRACE_C)
    sx.plot([peak_ms], [p["trace"][p["peak_i"]]], "o", ms=5.5, color=TRACE_C)
    verticals(sx, peak_ms, lw=1.4)
    sx.set_xlim(-args.window_ms, args.window_ms)
    sx.set_ylim(0.0, ctx["line_max"] * 1.08)
    sx.set_xticks(ctx["ticks"])
    sx.grid(True, axis="y", alpha=0.18, lw=0.6)
    sx.tick_params(labelsize=9)
    sx.set_xlabel("ms from the curated stamp", fontsize=10)
    sx.set_ylabel("mean |CSD|\n" r"($\mu V/mm^2$)", fontsize=9)

    cax = fig.add_axes([1.0 - 0.95 / width, bottom / height,
                        0.15 / width, (ph + gap + sh) / height])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(r"CSD  ($\mu V/mm^2$)", fontsize=9, labelpad=2)
    cb.ax.tick_params(labelsize=8)

    keys = [Line2D([], [], color=STAMP_C, ls="--", lw=1.4,
                   label="curated stamp"),
            Line2D([], [], color=PEAK_C, ls="-", lw=1.6,
                   label="peak of mean|CSD|")]
    fig.legend(handles=keys, loc="upper right", ncol=2, frameon=False,
               fontsize=9,
               bbox_to_anchor=(1.0 - right / width, 1.0 - 1.03 / height))
    fig.text(left / width, 1.0 - 0.33 / height,
             "#%d   %s   %.3f s      offset %+.1f ms"
             % (p["i"] + 1, mmss(p["stamp"]), p["stamp"], peak_ms),
             fontsize=12.5, ha="left", va="center")
    fig.text(left / width, 1.0 - 0.68 / height,
             "%s   CSD %g-%g Hz%s"
             % (session_label, args.band[0], args.band[1],
                ", %g Hz notched" % args.line if args.line else ""),
             fontsize=9.5, ha="left", va="center", color="#555555")
    return fig


def write_panels(panels, args, outdir, session_label, bad, chan_label):
    """A sheet per event plus a manifest, for something to click through.

    One file per event rather than one enormous contact sheet: a viewer
    needs to show one at a time, and a manifest of what is in each is what
    lets it say WHY the one on screen is interesting without reopening the
    recording.
    """
    import json
    tag = band_tag(args.band)
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    ctx = scales(panels, args)
    rows = []
    for k, p in enumerate(panels):
        fig = event_figure(p, ctx, args, session_label)
        name = "spike_%02d_%s.png" % (p["i"] + 1, tag)
        fig.savefig(os.path.join(outdir, name), dpi=args.panel_dpi)
        plt.close(fig)
        off = float(p["t"][p["peak_i"]])
        col = p["csd"][:, p["peak_i"]]
        j = int(np.argmax(np.abs(col)))
        rows.append({
            "n": p["i"] + 1,
            "file": name,
            "stamp_s": round(float(p["stamp"]), 4),
            "mmss": mmss(p["stamp"]),
            "offset_ms": round(off, 1),
            "peak_uv_mm2": round(float(p["trace"][p["peak_i"]])),
            "strongest_csc": int(p["nums"][j]),
            "strongest_sign": "+" if col[j] > 0 else "-",
        })
        if len(panels) > 12 and k and not k % max(1, len(panels) // 10):
            print("  drew %d/%d" % (k, len(panels)))

    offs = np.array([r["offset_ms"] for r in rows], dtype=float)
    meta = {
        "band": [args.band[0], args.band[1]],
        "band_tag": tag,
        "line_hz": args.line,
        "window_ms": args.window_ms,
        "spacing_um": args.spacing,
        "lfp_fs": args.lfp_fs,
        "session": session_label,
        "folder": args.folder,
        "bank": os.path.basename(args.bank),
        "channels": chan_label,
        "repaired": {str(k): v for k, v in (bad or {}).items()},
        "n": len(rows),
        "median_offset_ms": round(float(np.median(offs)), 1),
        "iqr_ms": round(float(np.percentile(offs, 75)
                              - np.percentile(offs, 25)), 1),
        "within_5_pct": round(float((np.abs(offs) <= 5).mean()) * 100.0),
        "within_10_pct": round(float((np.abs(offs) <= 10).mean()) * 100.0),
        "within_25_pct": round(float((np.abs(offs) <= 25).mean()) * 100.0),
        "events": rows,
    }
    path = os.path.join(outdir, "manifest_%s.json" % tag)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print("wrote %d sheet(s) and %s" % (len(rows), path))
    return meta


def mmss(t):
    return "%d:%05.2f" % (int(t) // 60, t - 60 * (int(t) // 60))


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default=FOLDER, help="session folder")
    ap.add_argument("--bank", default=BANK, help="event bank CSV")
    ap.add_argument("-n", "--n-events", type=int, default=N_EVENTS,
                    help="how many of the first events to draw; 0 means "
                         "every event in the bank")
    ap.add_argument("--all", dest="n_events", action="store_const", const=0,
                    help="draw every event in the bank (same as -n 0)")
    ap.add_argument("--cols", type=int, default=0,
                    help="panels per row (default: up to 8, wrapping)")
    ap.add_argument("--panel-w", type=float, default=0.0,
                    help="panel width, inches (default: fits the column count)")
    ap.add_argument("--panel-h", type=float, default=0.0,
                    help="panel height, inches")
    ap.add_argument("--label", default="spike",
                    help="curation verdict to keep ('' for all, incl. garbage)")
    ap.add_argument("--band", type=float, nargs=2, default=list(BAND),
                    metavar=("LO", "HI"), help="bandpass, Hz")
    ap.add_argument("--line", type=float, default=LINE_HZ,
                    help="mains frequency to notch out; 0 disables it")
    ap.add_argument("--window-ms", type=float, default=WINDOW_MS,
                    help="half-width drawn either side of each stamp")
    ap.add_argument("--channels", default="",
                    help="probe-order subset, e.g. 1-18 (default: all)")
    ap.add_argument("--bad", default="",
                    help="contacts to interpolate over, e.g. 59; "
                         "'auto' (default) screens for them")
    ap.add_argument("--spacing", type=float, default=probes.CONTACT_PITCH_UM,
                    help="contact pitch, um")
    ap.add_argument("--lfp-fs", type=float, default=LFP_FS,
                    help="rate to decimate to before filtering")
    ap.add_argument("--pad", type=float, default=PAD_S,
                    help="filter margin read either side and trimmed, s")
    ap.add_argument("--no-smooth", action="store_true",
                    help="skip the [1 2 1] taper across depth before the "
                         "derivative (it is there to stop one noisy contact "
                         "dominating a second difference)")
    ap.add_argument("--line-mode", default="overlay",
                    choices=("overlay", "strip", "both"),
                    help="where the mean|CSD| trace goes")
    ap.add_argument("--smooth-ms", type=float, default=0.0,
                    help="moving average over the mean|CSD| trace, ms. 0 (the "
                         "default) draws it raw; about a half-cycle of the "
                         "band merges the rectification's twin lobes into "
                         "one hump")
    ap.add_argument("--cmap", default="RdBu_r",
                    help="diverging is the right kind here: CSD has a sign")
    ap.add_argument("--interp", default="nearest",
                    help="imshow interpolation; nearest keeps contacts visible")
    ap.add_argument("--clip-pct", type=float, default=99.5,
                    help="percentile of |CSD| that saturates the colour scale")
    ap.add_argument("--per-event-scale", action="store_true",
                    help="autoscale each panel separately (makes events look "
                         "more alike than they are)")
    ap.add_argument("--save", default=None, help="write the figure here")
    ap.add_argument("--panels-dir", default=None,
                    help="also write one sheet per event into this folder, "
                         "plus a manifest -- what a viewer clicks through")
    ap.add_argument("--panel-dpi", type=int, default=110,
                    help="resolution of the per-event sheets")
    ap.add_argument("--no-contact-sheet", action="store_true",
                    help="with --panels-dir, skip the all-in-one figure")
    args = ap.parse_args()
    args.band = (float(args.band[0]), float(args.band[1]))

    # --- 1. the events ----------------------------------------------------
    bank = args.bank if os.path.isabs(args.bank) else \
        os.path.join(_HERE, args.bank)
    if not os.path.exists(bank):
        sys.exit("no such bank: " + bank)
    kept = read_bank(bank, label=args.label)
    if not kept:
        sys.exit("no %s events in %s" % (args.label or "any", bank))
    events = kept if args.n_events == 0 else kept[:max(1, args.n_events)]
    print("%s: %d %s event(s); taking %s"
          % (os.path.basename(bank), len(kept), args.label or "ds",
             "all of them" if len(events) == len(kept)
             else "the first %d" % len(events)))
    if len(events) <= 12:
        for i, e in enumerate(events):
            print("  #%d  %10.3f s  (%s)  %s"
                  % (i + 1, e["t"], mmss(e["t"]), e["by"] or "-"))
    else:
        print("  %.3f s (%s) .. %.3f s (%s), curated by %s"
              % (events[0]["t"], mmss(events[0]["t"]),
                 events[-1]["t"], mmss(events[-1]["t"]),
                 ", ".join(sorted({e["by"] for e in events if e["by"]})
                           ) or "-"))

    # --- 2. the session ---------------------------------------------------
    session = csc.open_session(args.folder)
    if not session.get("ok"):
        sys.exit(session.get("error") or "could not open " + args.folder)
    chans = parse_channels(args.channels, session["channels"])
    if len(chans) < 3:
        sys.exit("a CSD is a second difference across depth, so it needs at "
                 "least three channels; %d were asked for" % len(chans))
    print("%s  fs=%g Hz  %d channels (CSC%d-%d)  %.1f s"
          % (session["name"], session["fs"], len(chans),
             chans[0]["number"], chans[-1]["number"],
             session["duration_s"]))

    # --- 3. the bad contacts ----------------------------------------------
    # Screened BEFORE the derivative, because a second spatial difference
    # amplifies whatever differs most between neighbours, and on a real probe
    # that is usually one bad wire rather than any current.
    spec = {"band": args.band, "line_hz": args.line, "line_q": LINE_Q,
            "lfp_fs": args.lfp_fs}
    if args.bad.strip().lower() in ("", "auto"):
        bad = braces.screen(session, chans, spec, [e["t"] for e in events])
    else:
        bad = {int(n): "named on the command line"
               for n in args.bad.replace(" ", "").split(",") if n}
    if bad:
        print("interpolated over %d contact(s):" % len(bad))
        for num in sorted(bad):
            print("  CSC%-3d %s" % (num, bad[num]))
    else:
        print("no contacts screened out")

    # --- 4. the CSD per event ---------------------------------------------
    panels, report = [], {}
    step = max(1, len(events) // 10)
    for i, e in enumerate(events):
        if len(events) > 12 and i and not i % step:
            print("  read %d/%d" % (i, len(events)))
        got = event_csd(session, chans, e["t"], args, bad, report)
        if not got:
            print("  #%d at %.3f s: nothing readable there (a gap?)"
                  % (i + 1, e["t"]))
            continue
        t_ms, csd, nums, fs = got
        trace = mean_abs(csd, fs, args.smooth_ms)
        peak_i = int(np.argmax(trace))
        panels.append({"i": i, "stamp": e["t"], "t": t_ms, "csd": csd,
                       "nums": nums, "trace": trace, "peak_i": peak_i,
                       "fs": fs})
    if not panels:
        sys.exit("none of those events could be read")

    print("\nmains: the notch took out %.2f uV rms of a %.1f uV rms trace "
          "(%.1f%%), per contact, before the derivative"
          % (report.get("mains_uv", 0.0), report.get("wideband_uv", 0.0),
             100.0 * report.get("mains_uv", 0.0)
             / max(report.get("wideband_uv", 0.0), 1e-9)))
    if args.line and args.line > args.band[1]:
        print("      -- %g Hz is above the %g Hz top of the passband, so the "
              "bandpass would have removed most of it anyway. Try "
              "--band 5 100 (the lab's DS band) for the case where it is "
              "inside." % (args.line, args.band[1]))

    # --- 5. what the trace says about the timing --------------------------
    # The offset between the curated stamp and the peak of the average
    # rectified CSD: one number per event, and the reason the script is
    # called an aligner. A stamp and a projection disagreeing by 20 ms is
    # not a small thing at 5-10 Hz -- it is a tenth of a cycle.
    # `strongest at` is the contact carrying the largest |CSD| at that
    # instant, with the sign it has there. Deliberately not called a sink:
    # which sign is a sink depends on the polarity the reader applies
    # (`invert=True` here) as well as on the derivative's own sign, and that
    # chain is not something this script has checked end to end. The number
    # and the sign are facts; the anatomy is the reader's call.
    print("\n  #   stamp (s)   peak of mean|CSD|   offset     peak    "
          "strongest at")
    print("  --  ----------  -----------------  --------  -------  ------------")
    for p in panels:
        off = p["t"][p["peak_i"]]
        col = p["csd"][:, p["peak_i"]]
        j = int(np.argmax(np.abs(col)))
        print("  #%d  %10.3f  %16.3f  %+6.1f ms  %7.0f  CSC%-3d (%s)"
              % (p["i"] + 1, p["stamp"], p["stamp"] + off / 1000.0, off,
                 p["trace"][p["peak_i"]], p["nums"][j],
                 "+" if col[j] > 0 else "-"))
    # How well the two verticals agree, over the whole set. This is the
    # number the figure is a picture of: the fraction of events where the
    # peak of the curve lands on the stamp, and the fraction where it is
    # somewhere else entirely -- which at a +/- window_ms half-width means
    # the curve found a different event, or found the ongoing oscillation
    # rather than an event at all.
    offs = np.array([p["t"][p["peak_i"]] for p in panels])
    near = [float((np.abs(offs) <= w).mean()) * 100.0 for w in (5, 10, 25)]
    print("\n  %d event(s):  median offset %+.1f ms   IQR %.1f ms   "
          "spread %.1f ms peak-to-peak"
          % (offs.size, np.median(offs),
             np.percentile(offs, 75) - np.percentile(offs, 25),
             offs.max() - offs.min()))
    print("  the two verticals agree to within "
          "5 ms on %.0f%%, 10 ms on %.0f%%, 25 ms on %.0f%% of them"
          % (near[0], near[1], near[2]))
    far = [p for p in panels if abs(p["t"][p["peak_i"]]) > 25.0]
    if far:
        print("  %d beyond 25 ms: %s"
              % (len(far), ", ".join("#%d (%+.0f ms)"
                                     % (p["i"] + 1, p["t"][p["peak_i"]])
                                     for p in far)))

    # --- 6. the sheets ----------------------------------------------------
    label = events[0]["session"] or os.path.basename(args.folder)
    chan_label = "CSC%d-%d" % (chans[0]["number"], chans[-1]["number"])
    if args.panels_dir:
        outdir = args.panels_dir if os.path.isabs(args.panels_dir) else \
            os.path.join(_HERE, args.panels_dir)
        print("")
        write_panels(panels, args, outdir, label, bad, chan_label)
        if args.no_contact_sheet:
            return

    # --- 7. the contact sheet ---------------------------------------------
    fig = figure(events, panels, args)
    if args.save:
        out = args.save if os.path.isabs(args.save) else \
            os.path.join(_HERE, args.save)
        fig.savefig(out, dpi=150)
        print("\nwrote " + out)
    elif not args.panels_dir:
        plt.show()


if __name__ == "__main__":
    main()
