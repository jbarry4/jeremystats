#!/usr/bin/env python3
"""
ds_concat_timestamp_diagnostic.py
=================================

Answers the question: if I open the RAW recording in a viewer, but navigate to
it using DS timestamps produced by the concat-aware ("Gold and Green") Toothy,
do the timestamps point at the right place?

THE PROBLEM
-----------
When a Neuralynx recording has gaps, new Toothy calls

    spikeinterface.concatenate_recordings([recording])

This glues the segments together end to end and then builds its time axis as

    t_concat(i) = i / fs                      (i = sample index, gaps removed)

The raw file's own clock instead says

    t_true(i)   = segment_start_time + (i - segment_start_index) / fs

These agree only inside the first segment.  After every gap, t_concat runs
EARLIER than t_true by the cumulative duration of all preceding gaps.  The
error is a STEP FUNCTION: zero in segment 0, then constant within each later
segment.  Nothing in the Toothy output records this -- DATA.hdf5's `lfp_time`
is perfectly uniform, so the gaps are invisible downstream.

Consequences this script quantifies:

  1. OFFSET.  Every DS event after the first gap is reported at a time that is
     too early by a known amount.  Seek to that time in the raw file and you
     land in the wrong place.

  2. STITCH ARTEFACTS.  At each gap the LFP jumps discontinuously.  Toothy
     band-pass filters and peak-detects straight across that step, so events
     detected near a boundary may be filter ringing rather than real dentate
     spikes.

  3. INDEX vs TIME.  DS_DF carries both `time`/`start`/`stop` (concatenated
     seconds) and `idx`/`idx_peak`/`idx_start`/`idx_stop` (indices into the
     concatenated, downsampled LFP).  The indices are self-consistent with
     Toothy's own arrays and are NOT affected -- only the mapping back to the
     raw file is.  Use indices within Toothy; use this script's corrected
     times to go back to raw.

USAGE
-----
    python ds_concat_timestamp_diagnostic.py "D:\\path\\to\\2024-02-09_16-43-46"

    --toothy-dir DIR   where DATA.hdf5 lives (default: <folder>/toothy)
    --csv OUT.csv      write the DS table with corrected timestamps
    --times 1.5 900.2  just convert these concatenated times and exit
    --window-ms MS     half-window used for the stitch-artefact check
                       (default 125 ms, matching Toothy's ds_wlen)
    --max-rows N       limit printed rows (default 25)

Requires numpy; pandas + h5py only if a DATA.hdf5 is being read.
"""

import argparse
import os
import sys

import numpy as np

from ncs_concat_health_check import segment_file, sortkey


# --------------------------------------------------------------------------
# the concat <-> true time mapping
# --------------------------------------------------------------------------

class ConcatMap(object):
    """Maps between Toothy's concatenated time axis and the raw file clock."""

    def __init__(self, info):
        self.fs = info["freq"]
        self.t0_us = info["t0_us"]
        segs = info["segments"]
        self.n_seg = len(segs)
        self.n_samples = np.array([s["n_samples"] for s in segs], dtype=np.int64)
        # first concatenated sample index of each segment
        self.cum_start = np.concatenate([[0], np.cumsum(self.n_samples)[:-1]])
        # true time (s, relative to recording start) of each segment's first sample
        self.true_t0 = np.array(
            [(s["start_us"] - self.t0_us) / 1e6 for s in segs], dtype=np.float64)
        # concatenated time of each segment's first sample
        self.concat_t0 = self.cum_start / self.fs
        # constant shift applied inside each segment (concat - true; <= 0)
        self.shift = self.concat_t0 - self.true_t0
        self.total = int(self.n_samples.sum())
        self.concat_span = (self.total - 1) / self.fs
        self.true_span = (segs[-1]["end_us"] - self.t0_us) / 1e6

    def seg_of_concat_time(self, t_concat):
        """Segment index containing each concatenated time."""
        i = np.asarray(t_concat, dtype=np.float64) * self.fs
        return np.clip(np.searchsorted(self.cum_start, i, side="right") - 1,
                       0, self.n_seg - 1)

    def to_true(self, t_concat):
        """Concatenated seconds -> true recording seconds (relative to start)."""
        t_concat = np.asarray(t_concat, dtype=np.float64)
        s = self.seg_of_concat_time(t_concat)
        return t_concat - self.shift[s]

    def to_true_us(self, t_concat):
        """Concatenated seconds -> absolute Neuralynx timestamp (microseconds)."""
        return self.t0_us + self.to_true(t_concat) * 1e6

    def error_ms(self, t_concat):
        """How early the concatenated time is, in milliseconds (>= 0)."""
        s = self.seg_of_concat_time(t_concat)
        return -self.shift[s] * 1e3

    def distance_to_gap_s(self, t_concat):
        """Seconds from each time to the nearest segment boundary (in concat time)."""
        if self.n_seg < 2:
            return np.full(np.shape(t_concat), np.inf, dtype=np.float64)
        bounds = self.concat_t0[1:]                      # concat time of each stitch
        t = np.atleast_1d(np.asarray(t_concat, dtype=np.float64))
        d = np.min(np.abs(t[:, None] - bounds[None, :]), axis=1)
        return d


# --------------------------------------------------------------------------
# report sections
# --------------------------------------------------------------------------

def print_mapping_table(cm):
    print("SEGMENT MAP")
    print("  %-5s %12s %14s %14s %14s"
          % ("seg", "n samples", "concat t0 (s)", "true t0 (s)", "error (ms)"))
    for k in range(cm.n_seg):
        print("  %-5d %12d %14.6f %14.6f %14.3f"
              % (k, cm.n_samples[k], cm.concat_t0[k], cm.true_t0[k],
                 -cm.shift[k] * 1e3))
    print()
    print("  concatenated span : %.6f s" % cm.concat_span)
    print("  true span         : %.6f s" % cm.true_span)
    print("  worst-case error  : %.3f ms  (%.0f raw samples @ %g Hz)"
          % (-cm.shift[-1] * 1e3, -cm.shift[-1] * cm.fs, cm.fs))


def check_lfp_time(h5path, cm):
    """Confirm DATA.hdf5's lfp_time really is the gap-free concatenated axis."""
    import h5py
    with h5py.File(h5path, "r") as fh:
        if "lfp_time" not in fh:
            print("  DATA.hdf5 has no 'lfp_time' dataset -- cannot verify.")
            return None, None
        t = fh["lfp_time"][:]
        attrs = dict(fh.attrs)
    lfp_fs = float(attrs.get("lfp_fs", 0)) or (len(t) - 1) / (t[-1] - t[0])
    dt = np.diff(t)
    med = float(np.median(dt))
    jumps = int(np.count_nonzero(dt > med * 1.5))
    print("  lfp_time         : %d samples, %.6f s .. %.6f s, lfp_fs = %g Hz"
          % (len(t), t[0], t[-1], lfp_fs))
    print("  discontinuities  : %d" % jumps)
    if jumps == 0 and cm.n_seg > 1:
        print("  -> CONFIRMED: the time axis is uniform, so the %d raw gaps have"
              % (cm.n_seg - 1))
        print("     been closed.  lfp_time is CONCATENATED time, not raw time.")
    elif jumps:
        print("  -> lfp_time contains jumps; this output may already be gap-aware.")
    end_err = (cm.true_span - t[-1]) * 1e3
    print("  last sample says %.6f s; the raw file really ends at %.6f s"
          % (t[-1], cm.true_span))
    print("  -> end-of-recording error: %.3f ms" % end_err)
    return t, lfp_fs


def analyse_ds(h5path, cm, window_ms, max_rows, csv_out):
    import pandas as pd

    key = None
    import h5py
    with h5py.File(h5path, "r") as fh:
        for probe in fh:
            if isinstance(fh[probe], h5py.Group) and "ALL_DS" in fh[probe]:
                key = "%s/ALL_DS" % probe
                break
    if key is None:
        print("  no ALL_DS table found in %s" % h5path)
        return

    df = pd.read_hdf(h5path, key=key)
    # ALL_DS is stacked per channel (the index is the channel number), so one
    # physical dentate spike appears once per channel that detected it.
    n_chan = df.index.nunique()
    n_uniq = df["time"].nunique()
    print("  loaded %s: %d rows over %d channel(s) -> %d distinct event times"
          % (key, len(df), n_chan, n_uniq))

    t_concat = df["time"].to_numpy(dtype=np.float64)
    seg = cm.seg_of_concat_time(t_concat)
    t_true = cm.to_true(t_concat)
    err_ms = cm.error_ms(t_concat)
    ts_us = cm.to_true_us(t_concat)
    raw_idx = np.round(t_true * cm.fs).astype(np.int64)

    n_after = int(np.count_nonzero(seg > 0))
    uniq_after = df.loc[seg > 0, "time"].nunique()
    print()
    print("  rows in segment 0 (timestamps exact) : %d" % int(np.count_nonzero(seg == 0)))
    print("  rows after the first gap (shifted)   : %d  (%.1f%%), %d distinct times"
          % (n_after, 100.0 * n_after / max(1, len(df)), uniq_after))
    if n_after:
        print("  offset among shifted events: min %.3f ms, median %.3f ms, max %.3f ms"
              % (err_ms[seg > 0].min(), np.median(err_ms[seg > 0]),
                 err_ms[seg > 0].max()))
        print("  in raw samples @ %g Hz     : min %.0f, median %.0f, max %.0f"
              % (cm.fs, err_ms[seg > 0].min() * cm.fs / 1e3,
                 np.median(err_ms[seg > 0]) * cm.fs / 1e3,
                 err_ms[seg > 0].max() * cm.fs / 1e3))

    # stitch artefacts: events whose analysis window straddles a discontinuity
    dist = cm.distance_to_gap_s(t_concat)
    win_s = window_ms / 1e3
    suspect = dist <= win_s
    print()
    print("  STITCH-ARTEFACT CHECK (window +/- %.0f ms around each gap)" % window_ms)
    print("  rows within one window of a stitch      : %d  (%d distinct times)"
          % (int(np.count_nonzero(suspect)), df.loc[suspect, "time"].nunique()))
    if np.count_nonzero(suspect):
        print("  -> these were detected across a discontinuity in the LFP and may")
        print("     be filter ringing rather than real dentate spikes; inspect them.")
        idx = np.flatnonzero(suspect)[:max_rows]
        print("     %-12s %-6s %14s %14s" % ("row", "seg", "concat t (s)", "dist to gap (ms)"))
        for i in idx:
            print("     %-12d %-6d %14.6f %14.3f"
                  % (i, seg[i], t_concat[i], dist[i] * 1e3))

    # per-segment breakdown
    print()
    print("  PER-SEGMENT BREAKDOWN")
    print("  %-5s %10s %16s %14s" % ("seg", "n events", "concat range (s)", "offset (ms)"))
    for k in range(cm.n_seg):
        m = seg == k
        n = int(np.count_nonzero(m))
        if n:
            rng = "%.1f-%.1f" % (t_concat[m].min(), t_concat[m].max())
        else:
            rng = "-"
        print("  %-5d %10d %16s %14.3f" % (k, n, rng, -cm.shift[k] * 1e3))

    if max_rows:
        print()
        print("  FIRST %d EVENTS AFTER THE FIRST GAP" % max_rows)
        idx = np.flatnonzero(seg > 0)[:max_rows]
        if len(idx) == 0:
            print("    (none)")
        else:
            print("    %-8s %-4s %14s %14s %10s %16s"
                  % ("row", "seg", "toothy t (s)", "true t (s)", "err (ms)",
                     "nlx ts (us)"))
            for i in idx:
                print("    %-8d %-4d %14.6f %14.6f %10.3f %16d"
                      % (i, seg[i], t_concat[i], t_true[i], err_ms[i], int(ts_us[i])))

    if csv_out:
        out = df.copy()
        out.insert(0, "row", np.arange(len(df)))
        out["segment"] = seg
        out["time_toothy_concat_s"] = t_concat
        out["time_true_s"] = t_true
        out["time_error_ms"] = err_ms
        out["nlx_timestamp_us"] = ts_us.astype(np.int64)
        out["raw_sample_index"] = raw_idx
        out["near_stitch"] = suspect
        for col in ("start", "stop"):
            if col in df.columns:
                v = df[col].to_numpy(dtype=np.float64)
                out["%s_true_s" % col] = cm.to_true(v)
        out.to_csv(csv_out, index=False)
        print()
        print("  wrote %s" % csv_out)


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Diagnose how Neuralynx concat gaps affect DS timestamps.")
    ap.add_argument("folder", help="raw recording folder containing .ncs files")
    ap.add_argument("--toothy-dir", default=None,
                    help="folder holding DATA.hdf5 (default <folder>/toothy)")
    ap.add_argument("--csv", dest="csv_out", default=None)
    ap.add_argument("--times", nargs="+", type=float, default=None,
                    help="convert these concatenated times to true times and exit")
    ap.add_argument("--window-ms", type=float, default=125.0)
    ap.add_argument("--max-rows", type=int, default=25)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    folder = args.folder
    if not os.path.isdir(folder):
        print("ERROR: not a directory: %s" % folder)
        return 2
    ncs = sorted([os.path.join(folder, f) for f in os.listdir(folder)
                  if f.lower().endswith(".ncs")], key=sortkey)
    if not ncs:
        print("ERROR: no .ncs files in %s" % folder)
        return 2

    info = segment_file(ncs[0], strict=args.strict)
    cm = ConcatMap(info)

    if args.times is not None:
        t = np.asarray(args.times, dtype=np.float64)
        print("%16s %16s %12s %18s" % ("concat t (s)", "true t (s)",
                                       "error (ms)", "nlx ts (us)"))
        for a, b, e, u in zip(t, cm.to_true(t), cm.error_ms(t), cm.to_true_us(t)):
            print("%16.6f %16.6f %12.3f %18d" % (a, b, e, int(u)))
        return 0

    print("=" * 78)
    print("DS / CONCAT TIMESTAMP DIAGNOSTIC")
    print("=" * 78)
    print("recording   : %s" % folder)
    print("reference   : %s  (%g Hz, %d segments)"
          % (info["name"], cm.fs, cm.n_seg))
    print()

    if cm.n_seg == 1:
        print("This recording is a single continuous segment.")
        print("Toothy's timestamps and the raw file clock are identical;")
        print("DS times can be used against the raw data with no correction.")
        print("=" * 78)
        return 0

    print_mapping_table(cm)

    tdir = args.toothy_dir or os.path.join(folder, "toothy")
    h5path = os.path.join(tdir, "DATA.hdf5")
    print()
    print("-" * 78)
    print("TOOTHY OUTPUT: %s" % h5path)
    print("-" * 78)
    if not os.path.isfile(h5path):
        print("  not found -- skipping DS analysis.")
        print("  (use --toothy-dir, or --times to convert timestamps by hand)")
        print("=" * 78)
        return 1

    try:
        check_lfp_time(h5path, cm)
    except Exception as exc:                              # noqa: BLE001
        print("  could not read lfp_time: %s" % exc)

    print()
    print("-" * 78)
    print("DS EVENTS")
    print("-" * 78)
    try:
        analyse_ds(h5path, cm, args.window_ms, args.max_rows, args.csv_out)
    except Exception as exc:                              # noqa: BLE001
        print("  could not analyse DS table: %s" % exc)

    print()
    print("=" * 78)
    print("BOTTOM LINE")
    print("=" * 78)
    print("  Toothy DS times are in CONCATENATED time.  The raw .ncs files are")
    print("  in TRUE time.  They diverge by up to %.3f ms (%.0f raw samples)."
          % (-cm.shift[-1] * 1e3, -cm.shift[-1] * cm.fs))
    print("  Before the first gap at %.3f s the two agree exactly."
          % cm.true_t0[1])
    print("  After it, add the per-segment offset above (or use --csv) before")
    print("  seeking into the raw recording.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    sys.exit(main())
