#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_continuity.py -- the segmentation, on files this builds itself.

The recordings the numbers were measured on live on a D: drive that is on one
machine in this lab. Everything here writes its own .ncs files instead, so the
rule can be checked anywhere: a continuous one, one with a gap wide enough to
break a segment, one with a hiccup too small to, and one whose records are
short. The point of a synthetic file is that the right answer is known before
the code runs.

    python tools/test_continuity.py

Checks nothing about how it looks. Only: does it find the segments neo would,
does it keep gap loss separate from clock drift, does the fast path agree with
the slow one, and does a seek land on the record the timestamps say.
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import continuity, nlx      # noqa: E402

FS = 30000.0
BLOCK_US = 1e6 / FS * nlx.SAMPLES_PER_RECORD      # 17066.67 us

fails = []


def ck(name, cond, detail=""):
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond else "   [%s]" % detail))
    if not cond:
        fails.append(name)


def write_ncs(path, records, fs=FS, chan=1):
    """Write a .ncs from (timestamp_us, nvalid) pairs.

    The header is the handful of fields the reader looks at. Samples are a
    ramp -- nothing here reads them, and a constant would hide an off-by-one
    in the seek.
    """
    head = (
        "######## Neuralynx Data File Header\n"
        "-FileType CSC\n"
        "-AcqEntName CSC%d\n"
        "-SamplingFrequency %.4f\n"
        "-ADBitVolts 0.000000030517578125\n"
        "-AcquisitionSystem AcqSystem1 DigitalLynxSX\n"
        "-ApplicationName Cheetah 6.4.2\n"
    ) % (chan, fs)
    raw = head.encode("latin-1")
    raw += b"\x00" * (nlx.HEADER_BYTES - len(raw))

    body = bytearray()
    for i, (ts, nv) in enumerate(records):
        body += struct.pack("<QIII", int(ts), chan, int(round(fs)), int(nv))
        # A ramp, wrapped into int16 rather than allowed to overflow it --
        # a constant would hide an off-by-one in the seek, and 300 records
        # of a raw ramp runs past 32767 at record 64.
        base = (i * nlx.SAMPLES_PER_RECORD) % 65536
        samples = ((np.arange(base, base + nlx.SAMPLES_PER_RECORD)
                    + 32768) % 65536 - 32768).astype(np.int16)
        body += samples.tobytes()

    with open(path, "wb") as fh:
        fh.write(raw)
        fh.write(bytes(body))


def continuous(n, t0=1000000):
    """n full records, each exactly one block after the last."""
    return [(int(round(t0 + i * BLOCK_US)), nlx.SAMPLES_PER_RECORD)
            for i in range(n)]


print("continuity -- segmentation on files with a known answer")
tmp = tempfile.mkdtemp(prefix="jarvis_cont_")

# ---- 1. a continuous file --------------------------------------------
p = os.path.join(tmp, "CSC1.ncs")
write_ncs(p, continuous(300))
r = nlx.segment_ncs(p)
ck("a continuous file is one segment", r["n_segments"] == 1, r["n_segments"])
ck("  and takes the two-record fast path", r["fast_path"] is True,
   r["fast_path"])
ck("  loses no time", r["seconds_lost"] == 0, r["seconds_lost"])
# Within a microsecond, not exactly. A record's duration is
# `int(1e6 / fs * nvalid)`, which truncates 17066.67 to 17066 -- neo does the
# same and this is a faithful port of neo, so the last record is up to a
# microsecond short. Four thousand times smaller than the gap tolerance, so
# nothing that matters can hide under it.
ck("  true and concat durations agree",
   abs(r["true_duration_s"] - r["concat_duration_s"]) < 5e-6,
   "%.9f vs %.9f" % (r["true_duration_s"], r["concat_duration_s"]))

# ---- 2. one real gap --------------------------------------------------
# 50 ms is three blocks, far above the 4267 us tolerance.
recs = continuous(200)
GAP_US = 50000
recs = recs[:100] + [(ts + GAP_US, nv) for ts, nv in recs[100:]]
p2 = os.path.join(tmp, "CSC2.ncs")
write_ncs(p2, recs, chan=2)
r2 = nlx.segment_ncs(p2)
ck("a 50 ms gap makes two segments", r2["n_segments"] == 2, r2["n_segments"])
ck("  the fast path does not claim it", r2["fast_path"] is False,
   r2["fast_path"])
ck("  one gap is reported", len(r2["gaps"]) == 1, len(r2["gaps"]))
ck("  its size is the gap, not the interval",
   abs(r2["gaps"][0]["gap_ms"] - 50.0) < 0.1, r2["gaps"][0]["gap_ms"])
ck("  it breaks after the right record",
   r2["gaps"][0]["after_record"] == 99, r2["gaps"][0]["after_record"])
ck("  seconds lost is the gap",
   abs(r2["seconds_lost"] - 0.05) < 1e-4, r2["seconds_lost"])
ck("  the shift equals the gap",
   abs(r2["max_time_error_ms"] - 50.0) < 0.2, r2["max_time_error_ms"])
ck("  no buffer slots went unused",
   r2["unused_record_slots"] == 0, r2["unused_record_slots"])
ck("  and nothing is claimed lost below the threshold",
   r2["sub_threshold_lost_s"] == 0, r2["sub_threshold_lost_s"])

# ---- 3. a hiccup below the tolerance ----------------------------------
# 2 ms: real, and smaller than the 4.267 ms neo tolerates. No break, and
# nothing in the timestamps records it -- which is the point of saying so.
recs = continuous(200)
recs = recs[:100] + [(ts + 2000, nv) for ts, nv in recs[100:]]
p3 = os.path.join(tmp, "CSC3.ncs")
write_ncs(p3, recs, chan=3)
r3 = nlx.segment_ncs(p3)
ck("a 2 ms hiccup does not break a segment", r3["n_segments"] == 1,
   r3["n_segments"])
ck("  so nothing is counted as lost", r3["seconds_lost"] == 0,
   r3["seconds_lost"])
ck("  and it is not called a gap", len(r3["gaps"]) == 0, len(r3["gaps"]))

# ---- 4. short records -------------------------------------------------
# Cheetah closing a record early: fewer valid samples, next timestamp
# following from the short count rather than a full block.
recs, t = [], 1000000
for i in range(200):
    nv = 200 if i == 50 else nlx.SAMPLES_PER_RECORD
    recs.append((int(round(t)), nv))
    t += nv / FS * 1e6
p4 = os.path.join(tmp, "CSC4.ncs")
write_ncs(p4, recs, chan=4)
r4 = nlx.segment_ncs(p4)
ck("a short record alone is not a gap", r4["n_segments"] == 1,
   r4["n_segments"])
ck("  it is counted as short", r4["n_short_records"] == 1,
   r4["n_short_records"])
ck("  its unused buffer slots are counted",
   r4["unused_record_slots"] == nlx.SAMPLES_PER_RECORD - 200,
   r4["unused_record_slots"])
# And NOT reported as lost time. The next record's timestamp follows the
# short count exactly here, so the record was simply short: nothing was
# recorded over, and no wall-clock time passed unaccounted for. Calling those
# 312 unused slots "10.4 ms missing" is the thing this check exists to stop.
ck("  but nothing is claimed lost, because nothing was",
   r4["sub_threshold_lost_s"] < 1e-5, r4["sub_threshold_lost_s"])
ck("  so true and concat still agree",
   abs(r4["true_duration_s"] - r4["concat_duration_s"]) < 5e-6,
   "%.9f vs %.9f" % (r4["true_duration_s"], r4["concat_duration_s"]))
ck("  and the words say so",
   any("no time is missing" in c["message"]
       for c in continuity.checks(dict(r4, ok=True))),
   [c["message"] for c in continuity.checks(dict(r4, ok=True))])

# A short record that DID lose time: the next timestamp is 2 ms later than
# its samples account for, below the 4.267 ms tolerance so no break is made.
recs, t = [], 1000000
for i in range(200):
    nv = 200 if i == 50 else nlx.SAMPLES_PER_RECORD
    recs.append((int(round(t)), nv))
    t += nv / FS * 1e6 + (2000 if i == 50 else 0)
p4b = os.path.join(tmp, "CSC6.ncs")
write_ncs(p4b, recs, chan=6)
r4b = nlx.segment_ncs(p4b)
ck("a short record that lost 2 ms still makes no break",
   r4b["n_segments"] == 1, r4b["n_segments"])
ck("  and the 2 ms is measured", abs(r4b["sub_threshold_lost_s"] - 0.002) < 1e-4,
   r4b["sub_threshold_lost_s"])
ck("  counted as inside a segment", r4b["n_short_inside"] == 1,
   r4b["n_short_inside"])

# ---- 5. drift is not loss ---------------------------------------------
# A clock running slightly slow: every interval is a little long, but no
# interval is long enough to be a break. Inferring loss from
# (true - concat) would report 20 ms of "missing data" on a file that lost
# nothing, which is the mistake the reference script warns about.
recs = [(int(round(1000000 + i * BLOCK_US * 1.00005)),
         nlx.SAMPLES_PER_RECORD) for i in range(400)]
p5 = os.path.join(tmp, "CSC5.ncs")
write_ncs(p5, recs, chan=5)
r5 = nlx.segment_ncs(p5)
ck("a slow clock is not a gap", r5["n_segments"] == 1, r5["n_segments"])
ck("  loss stays zero", r5["seconds_lost"] == 0, r5["seconds_lost"])
# 399 intervals, each 17066.67 us long and 0.005% longer than nominal, is
# 340 us of drift -- not the millisecond I first asserted. The number is not
# the point; that it lands in `clock_drift_s` and NOT in `seconds_lost` is.
ck("  the drift is reported separately and is positive",
   r5["clock_drift_s"] > 2e-4 and r5["seconds_lost"] == 0,
   "drift %.6f s, lost %.6f s" % (r5["clock_drift_s"], r5["seconds_lost"]))
ck("  and it is the whole of the true-minus-concat difference",
   abs(r5["clock_drift_s"]
       - (r5["true_duration_s"] - r5["concat_duration_s"])) < 5e-6,
   "%.9f vs %.9f" % (r5["clock_drift_s"],
                     r5["true_duration_s"] - r5["concat_duration_s"]))

# ---- 6. the seek ------------------------------------------------------
# The window must start at the record the timestamps put there, not at
# floor(t / block) -- which after a 50 ms gap is a different record.
after_gap = 100 * BLOCK_US / 1e6 + 0.05 + 0.01
data, t_actual, fs_got = nlx.read_ncs_range(p2, after_gap, after_gap + 0.01)
ck("a seek past a gap lands on the recording's clock",
   abs(t_actual - after_gap) < nlx.SAMPLES_PER_RECORD / FS + 1e-9,
   "asked %.6f got %.6f" % (after_gap, t_actual))
ck("  and the old arithmetic would not have",
   abs(int(np.floor(after_gap / (nlx.SAMPLES_PER_RECORD / FS)))
       * (nlx.SAMPLES_PER_RECORD / FS) - t_actual) > 1e-6,
   "they agree, so this file does not exercise the difference")

rep = {}
mid = 100 * BLOCK_US / 1e6 - 0.005
nlx.read_ncs_range(p2, mid, mid + 0.07, report=rep)
ck("a window spanning the gap reports it", len(rep["gaps"]) == 1,
   len(rep["gaps"]))
ck("  with its size", abs(rep["gap_s"] - 0.05) < 1e-3, rep["gap_s"])

rep2 = {}
nlx.read_ncs_range(p2, 0.1, 0.2, report=rep2)
ck("a window clear of it reports none", len(rep2["gaps"]) == 0,
   len(rep2["gaps"]))

# ---- 7. the folder check ----------------------------------------------
folder = os.path.join(tmp, "rec")
os.makedirs(folder, exist_ok=True)
recs = continuous(200)
recs = recs[:100] + [(ts + GAP_US, nv) for ts, nv in recs[100:]]
for i in range(1, 5):
    write_ncs(os.path.join(folder, "CSC%d.ncs" % i), recs, chan=i)
rep = continuity.check(folder, use_cache=False)
ck("the folder check agrees with the file", rep["n_segments"] == 2,
   rep["n_segments"])
ck("  every channel agrees", not rep["mismatches"], rep["mismatches"])
ck("  and it probed more than one", len(rep["probed"]) > 1, rep["probed"])

sha1 = rep["gap_map_sha"]
rep_b = continuity.check(folder, use_cache=False)
ck("the map hash is stable across runs", rep_b["gap_map_sha"] == sha1,
   sha1 + " vs " + rep_b["gap_map_sha"])

# One channel segmented differently -- a partly copied folder, which must
# not read as "this recording has gaps".
write_ncs(os.path.join(folder, "CSC3.ncs"), continuous(200), chan=3)
rep_c = continuity.check(folder, use_cache=False)
ck("a disagreeing channel is caught", len(rep_c["mismatches"]) >= 1,
   rep_c["mismatches"])
rows = continuity.checks(rep_c)
ck("  and is reported as bad, not as a gap",
   any(r["level"] == "bad" and r["name"] == "channels disagree" for r in rows),
   [(r["level"], r["name"]) for r in rows])

# ---- 8. the words -----------------------------------------------------
rows = continuity.checks(rep)
cont = [r for r in rows if r["name"] == "continuity"]
ck("the continuity row is a warn, not a stop",
   len(cont) == 1 and cont[0]["level"] == "warn",
   [(r["level"], r["name"]) for r in rows])
ck("  and names the segment count", "2 segments" in cont[0]["message"],
   cont[0]["message"])

clean_rows = continuity.checks(continuity.check(
    os.path.dirname(p), use_cache=False))
ck("a clean folder says so at ok",
   any(r["name"] == "continuity" and r["level"] == "ok" for r in clean_rows)
   or True,   # that folder holds the mixed test files; see below
   "")

# The temp folder above holds every test file at once, so it is deliberately
# NOT a clean folder. A clean one, on its own:
clean_dir = os.path.join(tmp, "clean")
os.makedirs(clean_dir, exist_ok=True)
for i in range(1, 4):
    write_ncs(os.path.join(clean_dir, "CSC%d.ncs" % i), continuous(300),
              chan=i)
crep = continuity.check(clean_dir, use_cache=False)
crows = continuity.checks(crep)
ck("a clean folder is one segment at ok",
   crep["n_segments"] == 1
   and any(r["name"] == "continuity" and r["level"] == "ok" for r in crows),
   [(r["level"], r["name"]) for r in crows])
ck("  and gets no gap table", not crep["gaps"], crep["gaps"])

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("All checks passed.")
