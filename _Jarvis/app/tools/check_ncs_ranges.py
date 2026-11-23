# -*- coding: utf-8 -*-
"""Check that nlx.read_ncs_ranges reads exactly what read_ncs_range reads.

    python tools/check_ncs_ranges.py                 a few .ncs found on D:
    python tools/check_ncs_ranges.py PATH [PATH...]  these files

`read_ncs_ranges` is the overview strip's batched reader (2026-10-21): one
open and one header parse for all 900 probes instead of 900. It duplicates
the per-window arithmetic of `read_ncs_range`, so this holds the two to the
same answer, sample for sample, on real files -- continuous ones and ones
with timestamp gaps -- and prints how much faster the batch is.
"""
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

import numpy as np  # noqa: E402

from backend import nlx  # noqa: E402


def files_to_check(args):
    if args:
        return args
    out = []
    for root in (r"D:\EEG-Wheel_data", r"D:\\"):
        out += glob.glob(os.path.join(root, "**", "CSC1.ncs"), recursive=True)[:3]
        if out:
            break
    return out[:3]


def spans_for(path, bins=900):
    # The overview's own spacing: a 0.35 s probe at the head of each bin.
    _d, t0s, fs = nlx.read_ncs_range(path, 0.0, 0.01)
    size = os.path.getsize(path)
    n_rec = (size - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize
    dur = n_rec * nlx.SAMPLES_PER_RECORD / (fs or nlx.DEFAULT_FS)
    step = dur / bins
    probe = min(step, 0.35)
    return [(i * step, i * step + probe) for i in range(bins)]


def main():
    paths = files_to_check(sys.argv[1:])
    if not paths:
        print("no .ncs files to check")
        return 2
    bad = 0
    for path in paths:
        spans = spans_for(path)
        nlx._BLOCK_MEMO.clear() if hasattr(nlx, "_BLOCK_MEMO") else None
        t0 = time.time()
        one = [nlx.read_ncs_range(path, a, b) for a, b in spans]
        t_one = time.time() - t0
        nlx._BLOCK_MEMO.clear() if hasattr(nlx, "_BLOCK_MEMO") else None
        t0 = time.time()
        many = list(nlx.read_ncs_ranges(path, spans))
        t_many = time.time() - t0
        diffs = 0
        for i, ((d1, a1, _fs), (j, d2, a2)) in enumerate(zip(one, many)):
            if j != i or d1.shape != d2.shape or not np.array_equal(d1, d2) \
                    or abs(a1 - a2) > 1e-9:
                diffs += 1
        ok = diffs == 0 and len(one) == len(many)
        bad += 0 if ok else 1
        print("%s  %s  %d windows: one at a time %.2f s, batched %.2f s (%.1fx)%s"
              % ("ok  " if ok else "FAIL", os.path.basename(os.path.dirname(path)),
                 len(spans), t_one, t_many, t_one / max(t_many, 1e-6),
                 "" if ok else "  [%d windows differ]" % diffs))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
