# -*- coding: utf-8 -*-
"""Doppler keeps every segment its own length, as Incisor does. Offline.

    python tools/test_doppler_gaps.py

A position in Doppler's joined trace is the concatenated sample index that
`continuity.sample_to_true` turns into a time, for every event. A segment
that reads short of what its records say used to let the next segment move
up into its place, so every event after it was stamped early by the
shortfall -- the fault Incisor met as a -9.71 ms offset against Toothy.

A made-up recording is read through `doppler._read_channel` with the file
reader swapped for one that serves a known ramp, the first segment 36
samples short. What is guarded:

  * the joined trace is exactly the recording's length;
  * the second segment's samples sit at their own concatenated indices,
    so a time worked out from any of them is right;
  * the missing stretch is held flat at the last value read (so it makes no
    line length and no event), and is reported as (segment, samples);
  * a recording with no shortfall is read exactly as before;
  * the run's warning says how short, in ms, and that times stay right.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from backend import continuity, csc, doppler  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-70s %s" % (name, "ok" if ok else "FAILED"))
    if not ok and detail is not None:
        print("      " + str(detail)[:400])
    if not ok:
        FAILED.append(name)


FS = 1000.0
N0, N1 = 5000, 5000          # what the records say each segment holds
SHORT = 36                   # what segment 0 really lacks at its end
T1 = 10.0                    # segment 1 starts 10 s in: a 5 s gap


def report():
    return {
        "ok": True, "fs": FS, "t0_us": 0, "total_samples": N0 + N1,
        "segments": [
            {"index": 0, "n_samples": N0, "true_t0_s": 0.0,
             "duration_s": N0 / FS},
            {"index": 1, "n_samples": N1, "true_t0_s": T1,
             "duration_s": N1 / FS},
        ],
        # Two linear runs: the breakpoint map sample_to_true reads.
        "breaks": [[0, 0, 1e6 / FS], [N0, int(T1 * 1e6), 1e6 / FS]],
    }


def fake_reader(short):
    """Serve the concatenated index as the value, by true time, the way the
    real reader serves records: segment 0 ends `short` samples early."""
    have0 = N0 - short

    def read(session, ch, t0, t1):
        if t0 < T1 - 1e-9:
            i_lo = int(round(t0 * FS))
            i_hi = min(have0, int(round(t1 * FS)))
            if i_lo >= have0:
                return np.zeros(0), t0, FS
            return (np.arange(i_lo, i_hi, dtype=np.float64), i_lo / FS, FS)
        i_lo = int(round((t0 - T1) * FS))
        i_hi = min(N1, int(round((t1 - T1) * FS)))
        if i_lo >= N1:
            return np.zeros(0), t0, FS
        return (np.arange(N0 + i_lo, N0 + i_hi, dtype=np.float64),
                T1 + i_lo / FS, FS)
    return read


def _ncs(path, t0_us, n_records):
    """A minimal .ncs: a blank header and `n_records` records from t0."""
    from backend import nlx
    recs = np.zeros(n_records, dtype=nlx.RECORD_DTYPE)
    recs["timestamp"] = t0_us + np.arange(n_records) * 17066
    recs["nvalid"] = nlx.SAMPLES_PER_RECORD
    with open(path, "wb") as fh:
        fh.write(b"\0" * nlx.HEADER_BYTES)
        fh.write(recs.tobytes())


def parts_checks():
    """PTEN m13 s17's netfiles copy holds every CSCn.ncs twice, the second
    as CSCn_0001.ncs, byte for byte: that is not a split recording."""
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="jarvis-parts-")
    try:
        _ncs(os.path.join(d, "CSC1.ncs"), 1000, 50)
        shutil.copyfile(os.path.join(d, "CSC1.ncs"),
                        os.path.join(d, "CSC1_0001.ncs"))
        _ncs(os.path.join(d, "CSC2.ncs"), 1000, 50)
        open(os.path.join(d, "CSC2_0001.ncs"), "wb").write(b"\0" * 16384)
        split, dupes = doppler.parts_report(d)
        check("a byte-for-byte copy is not a piece", not split
              and sorted(dupes) == [1, 2], (split, dupes))
        check("a header with no records is not a piece either",
              2 in dupes, dupes)
        check("so the recording is not refused",
              doppler.check_parts(d) is None, doppler.check_parts(d))
        w = doppler.duplicate_words(d)
        check("and the run says each was read once",
              w is not None and "read once" in w and "CSC1" in w, w)
        _ncs(os.path.join(d, "CSC3.ncs"), 1000, 50)
        _ncs(os.path.join(d, "CSC3_0001.ncs"), 1000 + 50 * 17066 + 5e6, 40)
        split, dupes = doppler.parts_report(d)
        check("a real continuation still is a piece", 3 in split, split)
        r = doppler.check_parts(d)
        check("and is still refused, naming it", r is not None and "3" in r, r)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    real = csc._read_channel_window
    try:
        print("\na segment that reads short")
        csc._read_channel_window = fake_reader(SHORT)
        short = []
        x = doppler._read_channel({"fs": FS}, {"index": 0, "number": 1},
                                  report(), {}, short=short)
        check("the joined trace is exactly the recording's length",
              x.size == N0 + N1, x.size)
        check("the next segment sits at its own indices",
              x.size == N0 + N1 and np.array_equal(
                  x[N0:], np.arange(N0, N0 + N1, dtype=np.float64)),
              x[N0:N0 + 3] if x.size > N0 else x.size)
        t = continuity.sample_to_true(report(), N0 + 1234)
        check("so a time made from one of them is right",
              t is not None and abs(t - (T1 + 1.234)) < 1e-9, t)
        hold = x[N0 - SHORT:N0]
        check("the missing stretch is held flat at the last value read",
              hold.size == SHORT and np.all(hold == N0 - SHORT - 1),
              hold[:3])
        check("and has no line length, so it can make no event",
              float(np.abs(np.diff(hold)).sum()) == 0.0)
        check("the shortfall is reported as (segment, samples)",
              short == [(0, SHORT)], short)
        words = doppler._short_words(short * 3, FS)
        check("and said once per segment, in ms, with what it means",
              words is not None and "segment 0 by 36 ms" in words
              and "own clock" in words, words)

        print("\na segment that reads whole")
        csc._read_channel_window = fake_reader(0)
        short = []
        x = doppler._read_channel({"fs": FS}, {"index": 0, "number": 1},
                                  report(), {}, short=short)
        check("is read exactly as it always was",
              np.array_equal(x, np.arange(N0 + N1, dtype=np.float64))
              and short == [], (x.size, short))
        check("and has nothing to say", doppler._short_words([], FS) is None)
    finally:
        csc._read_channel_window = real

    print("\na channel that is on disk twice")
    parts_checks()

    print("\n%s" % ("ALL PASS" if not FAILED else
                    "%d FAILED: %s" % (len(FAILED), "; ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
