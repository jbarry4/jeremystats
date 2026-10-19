#!/usr/bin/env python3
"""
ncs_concat_health_check.py
==========================

Health check for "concat issues" in a Neuralynx (.ncs) recording folder.

WHAT A "CONCAT ISSUE" IS
------------------------
Cheetah writes each .ncs file as a sequence of 1044-byte records, each holding
up to 512 samples plus the hardware timestamp (microseconds) of its first
sample.  If acquisition hiccups -- a dropped packet, a pause/resume, a disk
stall -- Cheetah closes the current record early (nb_valid < 512) and the next
record's timestamp jumps forward by more than one record duration.  The file
is then no longer a single continuous block of samples: it is several
*segments* separated by gaps of missing data.

neo/spikeinterface detect this and expose the file as a MULTI-SEGMENT
recording.  That is the root of both Toothy behaviours:

  * Old Toothy (Toothy-main) calls recording.get_num_samples() with no
    segment_index, which raises
        ValueError: Multi-segment object. Provide 'segment_index'
    -> the recording simply fails to load.

  * New Toothy ("Gold and Green") calls
        spikeinterface.concatenate_recordings([recording])
    which glues the segments together end to end.  The recording now loads,
    but the gaps are CLOSED: every sample after a gap is assigned a timestamp
    that is EARLIER than its true wall-clock time, by the cumulative duration
    of all preceding gaps.

This script reproduces neo's segmentation exactly, using nothing but numpy, so
you can check any recording folder without a working Toothy environment.

USAGE
-----
    python ncs_concat_health_check.py "D:\\path\\to\\2024-02-09_16-43-46"

    --all-channels     parse every .ncs file instead of a spot-check sample
    --channels N       how many channels to spot-check (default 4)
    --strict           use neo's strict_gap_mode=True tolerance instead of the
                       looser tolerance spikeinterface actually uses
    --json OUT.json    also write the findings as JSON
    --max-gaps N       limit the printed gap table (default 40)

EXIT CODE
---------
    0  no concat issue (single segment)
    1  concat issue found (multiple segments)
    2  error / nothing to check
"""

import argparse
import json
import os
import re
import sys

import numpy as np

HEADER_BYTES = 16 * 1024
RECORD_SIZE = 512          # samples per full record  (NcsSection._RECORD_SIZE)
MAX_GAP_SAMP_FRAC = 0.2    # NcsSectionsFactory._maxGapSampFrac

# The on-disk record layout, identical to NeuralynxRawIO._ncs_dtype
NCS_DTYPE = np.dtype([
    ("timestamp", "<u8"),
    ("channel_id", "<u4"),
    ("sample_rate", "<u4"),
    ("nb_valid", "<u4"),
    ("samples", "<i2", (RECORD_SIZE,)),
])


# --------------------------------------------------------------------------
# header parsing
# --------------------------------------------------------------------------

def read_header(path):
    """Return the .ncs text header as a dict of {key: value} strings."""
    with open(path, "rb") as fh:
        raw = fh.read(HEADER_BYTES)
    txt = raw.decode("latin-1").replace("\x00", "")
    hdr = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        parts = line[1:].split(None, 1)
        key = parts[0]
        val = parts[1].strip().strip('"') if len(parts) > 1 else ""
        hdr[key] = val
    return hdr


def acq_type(hdr):
    """Mirror NlxHeader.type_of_recording() closely enough for gap tolerance."""
    app = hdr.get("ApplicationName", "")
    sysname = hdr.get("AcquisitionSystem", "")
    if sysname:
        return sysname.split()[-1].upper().replace("_", "")
    if "Cheetah" in app:
        return "DIGITALLYNXSX"
    return "RAWDATAFILE"


def gap_tolerance_us(freq, acq, strict):
    """Reproduce NcsSectionsFactory.build_for_ncs_file's gapTolerance."""
    if acq == "PRE4":
        return 0
    if strict:
        return int(round(MAX_GAP_SAMP_FRAC * 1e6 / freq))
    return int(round(0.25 * RECORD_SIZE * 1e6 / freq))


# --------------------------------------------------------------------------
# segmentation (faithful port of neo NcsSectionsFactory._buildNcsSections)
# --------------------------------------------------------------------------

def segment_file(path, strict=False):
    """Parse one .ncs file and return its segmentation + diagnostics."""
    hdr = read_header(path)
    freq = float(hdr.get("SamplingFrequency", "0") or 0)
    if freq <= 0:
        raise ValueError("no SamplingFrequency in header of %s" % path)
    acq = acq_type(hdr)
    tol = gap_tolerance_us(freq, acq, strict)

    nbytes = os.path.getsize(path) - HEADER_BYTES
    nrec, remainder = divmod(nbytes, NCS_DTYPE.itemsize)
    mm = np.memmap(path, dtype=NCS_DTYPE, mode="r",
                   offset=HEADER_BYTES, shape=(nrec,))

    ts = np.asarray(mm["timestamp"], dtype=np.int64)
    nv = np.asarray(mm["nb_valid"], dtype=np.int64)
    chan = np.asarray(mm["channel_id"], dtype=np.int64)
    srate = np.asarray(mm["sample_rate"], dtype=np.int64)

    # neo's fast path: if the last record's timestamp is exactly what you would
    # predict from record 0 assuming every record is full, the file is one block.
    pred_last = int(round(ts[0] + (1e6 / freq) * RECORD_SIZE * (nrec - 1)))
    single_block = (chan[0] == chan[-1]
                    and srate[0] == srate[-1]
                    and ts[-1] == pred_last)

    if single_block:
        limits = [0, nrec]
        gap_inds = np.array([], dtype=np.int64)
        resid = np.array([], dtype=np.int64)
    else:
        delta = ts[1:] - ts[:-1]
        delta_pred = ((nv[:-1] / freq) * 1e6).astype(np.int64)
        resid = delta - delta_pred
        gap_inds = np.flatnonzero(np.abs(resid) > tol) + 1
        limits = [0] + gap_inds.tolist() + [nrec]

    segments = []
    for i in range(len(limits) - 1):
        start, stop = limits[i], limits[i + 1]
        dur_us = int(1e6 / freq * nv[stop - 1])
        segments.append({
            "start_rec": int(start),
            "end_rec": int(stop - 1),
            "start_us": int(ts[start]),
            "end_us": int(ts[stop - 1]) + dur_us,
            "n_samples": int(nv[start:stop].sum()),
        })

    short = np.flatnonzero(nv != RECORD_SIZE)

    return {
        "path": path,
        "name": hdr.get("AcqEntName", os.path.basename(path)),
        "header": hdr,
        "freq": freq,
        "acq_type": acq,
        "gap_tolerance_us": tol,
        "n_records": int(nrec),
        "trailing_bytes": int(remainder),
        "t0_us": int(ts[0]),
        "segments": segments,
        "total_samples": int(nv.sum()),
        "short_records": [(int(i), int(nv[i]), float((ts[i] - ts[0]) / 1e6))
                          for i in short],
        "residual_us": resid,
    }


def describe_gaps(info):
    """Turn a segmentation into an explicit list of gaps between segments."""
    segs = info["segments"]
    freq = info["freq"]
    t0 = info["t0_us"]
    gaps = []
    cum_lost = 0.0
    for a, b in zip(segs[:-1], segs[1:]):
        gap_us = b["start_us"] - a["end_us"]
        cum_lost += gap_us / 1e6
        gaps.append({
            "after_record": a["end_rec"],
            "at_true_time_s": (a["end_us"] - t0) / 1e6,
            "gap_s": gap_us / 1e6,
            "gap_samples_equiv": gap_us * freq / 1e6,
            "cumulative_shift_s": cum_lost,
        })
    return gaps


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def sortkey(fname):
    m = re.search(r"(\d+)", os.path.basename(fname))
    return (int(m.group(1)) if m else 0, fname)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Check a Neuralynx recording folder for concat issues.")
    ap.add_argument("folder", help="recording folder containing .ncs files")
    ap.add_argument("--channels", type=int, default=4,
                    help="number of channels to spot-check (default 4)")
    ap.add_argument("--all-channels", action="store_true",
                    help="parse every .ncs file (slow, reads the whole dataset)")
    ap.add_argument("--strict", action="store_true",
                    help="use neo strict_gap_mode=True tolerance "
                         "(spikeinterface uses False, which is the default here)")
    ap.add_argument("--max-gaps", type=int, default=40)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    folder = args.folder
    if not os.path.isdir(folder):
        print("ERROR: not a directory: %s" % folder)
        return 2

    ncs = sorted([os.path.join(folder, f) for f in os.listdir(folder)
                  if f.lower().endswith(".ncs")], key=sortkey)
    if not ncs:
        print("ERROR: no .ncs files found in %s" % folder)
        return 2

    print("=" * 78)
    print("NEURALYNX CONCAT HEALTH CHECK")
    print("=" * 78)
    print("folder      : %s" % folder)
    print("ncs files   : %d" % len(ncs))

    # ---- primary channel: full analysis --------------------------------
    primary = segment_file(ncs[0], strict=args.strict)
    hdr = primary["header"]
    freq = primary["freq"]
    segs = primary["segments"]
    gaps = describe_gaps(primary)

    print("opened      : %s   closed: %s"
          % (hdr.get("TimeCreated", "?"), hdr.get("TimeClosed", "?")))
    print("system      : %s   (%s)"
          % (hdr.get("AcquisitionSystem", "?"), hdr.get("ApplicationName", "?")))
    print("nominal fs  : %.4f Hz" % freq)
    print("gap mode    : %s  (tolerance %d us = %.2f ms = %.1f samples)"
          % ("strict" if args.strict else "spikeinterface default (non-strict)",
             primary["gap_tolerance_us"],
             primary["gap_tolerance_us"] / 1e3,
             primary["gap_tolerance_us"] * freq / 1e6))
    if primary["trailing_bytes"]:
        print("WARNING     : %d trailing bytes -- file may be truncated"
              % primary["trailing_bytes"])

    total_samples = primary["total_samples"]
    true_span = (segs[-1]["end_us"] - primary["t0_us"]) / 1e6
    concat_span = total_samples / freq

    print()
    print("-" * 78)
    print("reference channel: %s   (%d records, %d samples)"
          % (primary["name"], primary["n_records"], total_samples))
    print("-" * 78)
    # Time lost is the sum of the real inter-segment gaps.  Do NOT infer it
    # from (true_span - concat_span): the hardware clock is never exactly the
    # nominal rate, so that difference also contains drift and can even go
    # negative on a perfectly clean file.
    gap_total = gaps[-1]["cumulative_shift_s"] if gaps else 0.0
    drift = (true_span - concat_span) - gap_total

    print("segments detected            : %d" % len(segs))
    print("true wall-clock span         : %.6f s" % true_span)
    print("span if naively concatenated : %.6f s" % concat_span)
    print("time lost to gaps            : %.6f s  (%.1f samples @ %g Hz)"
          % (gap_total, gap_total * freq, freq))
    print("nominal-vs-actual clock drift: %+.6f s  (implied fs %.4f Hz; "
          "not data loss)" % (drift, (total_samples - 1) / true_span if true_span else freq))

    n_short = len(primary["short_records"])
    print("short records (nb_valid<512) : %d" % n_short)
    if n_short:
        missing = primary["n_records"] * RECORD_SIZE - total_samples
        print("  -> %d samples (%.4f s) never written by Cheetah"
              % (missing, missing / freq))

    concat_issue = len(segs) > 1

    if concat_issue:
        print()
        print("GAP TABLE (each row is a discontinuity in the raw data)")
        print("  %-10s %14s %12s %12s %14s"
              % ("after rec", "true time (s)", "gap (s)", "gap (ms)",
                 "cum. shift (s)"))
        for g in gaps[:args.max_gaps]:
            print("  %-10d %14.6f %12.6f %12.3f %14.6f"
                  % (g["after_record"], g["at_true_time_s"], g["gap_s"],
                     g["gap_s"] * 1e3, g["cumulative_shift_s"]))
        if len(gaps) > args.max_gaps:
            print("  ... %d further gaps not shown (raise --max-gaps)"
                  % (len(gaps) - args.max_gaps))

        print()
        print("SEGMENT MAP  (true = real recording clock, "
              "concat = what Toothy assigns)")
        print("  %-5s %12s %12s %12s %12s %12s"
              % ("seg", "n samples", "true t0 (s)", "concat t0 (s)",
                 "duration (s)", "shift (ms)"))
        cum = 0
        for k, s in enumerate(segs):
            true_t0 = (s["start_us"] - primary["t0_us"]) / 1e6
            concat_t0 = cum / freq
            print("  %-5d %12d %12.6f %12.6f %12.6f %12.3f"
                  % (k, s["n_samples"], true_t0, concat_t0,
                     s["n_samples"] / freq, (concat_t0 - true_t0) * 1e3))
            cum += s["n_samples"]

    # ---- cross-check other channels ------------------------------------
    if args.all_channels:
        others = ncs[1:]
    else:
        step = max(1, len(ncs) // max(1, args.channels))
        others = ncs[step::step][: max(0, args.channels - 1)]

    mismatches = []
    if others:
        print()
        print("-" * 78)
        print("cross-checking %d other channel(s)%s"
              % (len(others), "" if args.all_channels else " (spot-check; use --all-channels for all)"))
        print("-" * 78)
        ref_bounds = [(s["start_us"], s["n_samples"]) for s in segs]
        for path in others:
            try:
                info = segment_file(path, strict=args.strict)
            except Exception as exc:                      # noqa: BLE001
                mismatches.append((os.path.basename(path), "unreadable: %s" % exc))
                print("  %-12s ERROR %s" % (os.path.basename(path), exc))
                continue
            bounds = [(s["start_us"], s["n_samples"]) for s in info["segments"]]
            ok = bounds == ref_bounds
            print("  %-12s segments=%-4d samples=%-10d %s"
                  % (info["name"], len(info["segments"]),
                     info["total_samples"], "OK" if ok else "MISMATCH"))
            if not ok:
                mismatches.append((info["name"],
                                   "%d segments vs %d on reference"
                                   % (len(info["segments"]), len(segs))))

    # ---- verdict --------------------------------------------------------
    print()
    print("=" * 78)
    if concat_issue:
        print("VERDICT: CONCAT ISSUE PRESENT  -- %d segments, %d gap(s), "
              "%.6f s of data missing" % (len(segs), len(gaps), gap_total))
        print()
        print("  * Old Toothy (Toothy-main) CANNOT load this recording: it calls")
        print("    recording.get_num_samples() on a multi-segment object, which")
        print("    raises \"ValueError: Multi-segment object. Provide 'segment_index'\".")
        print("  * New Toothy concatenates the %d segments, so it loads fine --" % len(segs))
        print("    but every sample after the first gap is labelled with a time")
        print("    that is TOO EARLY.  The error is a step function, constant")
        print("    within each segment, reaching %.3f ms (%.0f raw samples)"
              % (gap_total * 1e3, gap_total * freq))
        print("    by the end of the recording.")
        print()
        print("  Run ds_concat_timestamp_diagnostic.py to see what this does to")
        print("  the DS event timestamps and to get corrected times.")
    else:
        print("VERDICT: CLEAN -- single continuous segment, no concat issue.")
        print("  Toothy timestamps and raw-file times agree exactly.")
    if mismatches:
        print()
        print("  WARNING: %d channel(s) disagree with the reference segmentation:"
              % len(mismatches))
        for name, why in mismatches:
            print("    %-12s %s" % (name, why))
    print("=" * 78)

    if args.json_out:
        payload = {
            "folder": folder,
            "n_ncs_files": len(ncs),
            "reference_channel": primary["name"],
            "sampling_rate": freq,
            "strict_gap_mode": bool(args.strict),
            "gap_tolerance_us": primary["gap_tolerance_us"],
            "n_records": primary["n_records"],
            "total_samples": total_samples,
            "n_segments": len(segs),
            "concat_issue": bool(concat_issue),
            "true_span_s": true_span,
            "concat_span_s": concat_span,
            "time_lost_s": gap_total,
            "clock_drift_s": drift,
            "segments": segs,
            "gaps": gaps,
            "short_records": primary["short_records"],
            "channel_mismatches": mismatches,
        }
        with open(args.json_out, "w") as fh:
            json.dump(payload, fh, indent=2)
        print("wrote %s" % args.json_out)

    return 1 if concat_issue else 0


if __name__ == "__main__":
    sys.exit(main())
