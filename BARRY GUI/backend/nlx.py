"""
nlx.py -- Pure-Python Neuralynx CSC (.ncs) reader.

Mirrors the semantics of the lab's MATLAB loaders so the GUI shows the same
numbers the pipeline works on:
  - IED/02_CSC_Conversion/VACC_loadNeuralynxData.m
  - IED/02_CSC_Conversion/CSC2LL_uV_mex_disk.m

Neuralynx .ncs layout:
  16384-byte ASCII header, then fixed 1044-byte records:
      uint64  qwTimeStamp        (microseconds)
      uint32  dwChannelNumber
      uint32  dwSampleFreq       (Hz)
      uint32  dwNumValidSamples  (<= 512)
      int16   snSamples[512]     (A/D counts)

No third-party Neuralynx dependency and no MEX file required.
"""
from __future__ import annotations

import os
import re
import struct
import numpy as np

HEADER_BYTES = 16 * 1024
SAMPLES_PER_RECORD = 512
RECORD_DTYPE = np.dtype([
    ("timestamp", "<u8"),
    ("channel", "<u4"),
    ("freq", "<u4"),
    ("nvalid", "<u4"),
    ("samples", "<i2", (SAMPLES_PER_RECORD,)),
])
assert RECORD_DTYPE.itemsize == 1044, RECORD_DTYPE.itemsize

# Neuralynx default when a header omits ADBitVolts (matches fallbackADBV in
# CSC2LL_uV_mex_disk.m): volts per A/D count.
FALLBACK_ADBITVOLTS = 0.00000006103515625
DEFAULT_FS = 30000.0

# CSC12.ncs, and also CSC12_0001.ncs -- Cheetah writes the second form when
# an acquisition is split or restarted, and it is the same channel continued.
# The old pattern matched only the first, so a split recording lost every
# continuation file silently while the folder scan still counted them: the
# channel count and the loadable count disagreed and nothing compared them.
_CSC_NAME_RE = re.compile(r"^CSC(\d+)(?:_(\d+))?\.ncs$", re.IGNORECASE)


def parse_header(raw: bytes) -> dict:
    """Parse the 16 KB ASCII header into a dict of -Key value pairs."""
    text = raw.split(b"\x00", 1)[0].decode("latin-1", errors="replace")
    out = {"_raw": text}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        parts = line[1:].split(None, 1)
        if not parts:
            continue
        key = parts[0]
        out[key] = parts[1].strip() if len(parts) > 1 else ""
    return out


def _header_float(hdr: dict, key: str):
    val = hdr.get(key)
    if val is None:
        return None
    # Values can be a bare number or a whitespace-separated list (one per
    # channel on some Digital Lynx headers) -- take the first parseable one.
    for tok in str(val).replace(",", " ").split():
        try:
            return float(tok)
        except ValueError:
            continue
    return None


def read_header(path: str) -> dict:
    with open(path, "rb") as fh:
        return parse_header(fh.read(HEADER_BYTES))


# Cheetah writes the opening time in two different shapes depending on version.
_TIME_OPENED_RE = re.compile(
    r"Time Opened.*?\(m/d/y\)\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4}).*?"
    r"\(h:m:s\.?m?s?\)\s*:?\s*(\d{1,2}):(\d{2}):(\d{2})", re.I | re.S)
_TIME_CREATED_RE = re.compile(
    r"-TimeCreated\s+(\d{4})[/-](\d{2})[/-](\d{2})\s+(\d{2}):(\d{2}):(\d{2})", re.I)


def header_start_time(hdr: dict):
    """Recording start as 'YYYY-MM-DDTHH:MM:SS', or None.

    This is the most durable part of a session's identity: it lives inside the
    data file, so it survives renaming, moving, and re-mounting on another
    machine, unlike the folder name.
    """
    text = hdr.get("_raw", "") if isinstance(hdr, dict) else str(hdr)

    m = _TIME_CREATED_RE.search(text)
    if m:
        y, mo, d, h, mi, s = m.groups()
        return "%s-%s-%sT%s:%s:%s" % (y, mo, d, h, mi, s)

    m = _TIME_OPENED_RE.search(text)
    if m:
        mo, d, y, h, mi, s = m.groups()
        return "%s-%02d-%02dT%02d:%s:%s" % (y, int(mo), int(d), int(h), mi, s)

    return None


def read_ncs(path: str, invert: bool = True, to_microvolts: bool = True):
    """Read one .ncs file.

    Returns (data, meta) where `data` is a 1-D float32 array (microvolts by
    default) and `meta` carries fs, adbitvolts, timestamps and gap info.
    """
    size = os.path.getsize(path)
    n_rec = max(0, (size - HEADER_BYTES) // RECORD_DTYPE.itemsize)

    with open(path, "rb") as fh:
        hdr = parse_header(fh.read(HEADER_BYTES))
        recs = np.fromfile(fh, dtype=RECORD_DTYPE, count=n_rec) if n_rec else \
            np.empty(0, dtype=RECORD_DTYPE)

    adbv = _header_float(hdr, "ADBitVolts") or FALLBACK_ADBITVOLTS
    fs = _header_float(hdr, "SamplingFrequency")

    if len(recs) == 0:
        return np.empty(0, dtype=np.float32), {
            "fs": fs or DEFAULT_FS, "adbitvolts": adbv, "n_records": 0,
            "t_start_us": 0.0, "duration_s": 0.0, "header": hdr,
            "channel": None, "irregular_intervals": 0,
        }

    if fs is None or not np.isfinite(fs) or fs <= 0:
        freqs = recs["freq"][recs["freq"] > 0]
        fs = float(np.bincount(freqs).argmax()) if freqs.size else DEFAULT_FS

    nvalid = np.minimum(recs["nvalid"], SAMPLES_PER_RECORD).astype(np.int64)

    # Fast path: every record full (the overwhelmingly common case).
    if np.all(nvalid == SAMPLES_PER_RECORD):
        data = recs["samples"].reshape(-1).astype(np.float32)
    else:
        keep = np.zeros(recs["samples"].shape, dtype=bool)
        for i, n in enumerate(nvalid):
            keep[i, :n] = True
        data = recs["samples"][keep].astype(np.float32)

    if to_microvolts:
        data *= np.float32(adbv * 1e6)   # volts/AD -> microvolts
    if invert:
        data = -data                     # lab convention (invertPolarity=true)

    ts = recs["timestamp"].astype(np.float64)
    # Inter-record intervals off by more than half a block -- the idea in
    # RemoveCSCGaps.m. This is NOT the rule that decides whether the file is
    # one segment or eight; that is `segment_ncs` below, which follows neo.
    # The two disagree (9 against 7 on M8s9feb8) because this one also counts
    # ordinary clock jitter, so it must not be called "gaps" in the same
    # application that reports neo's answer under that word.
    irregular = 0
    if len(ts) > 1:
        nominal = SAMPLES_PER_RECORD / fs * 1e6
        dt = np.diff(ts)
        irregular = int(np.sum(np.abs(dt - nominal) > nominal * 0.5))

    return data, {
        "fs": float(fs),
        "adbitvolts": float(adbv),
        "n_records": int(len(recs)),
        "t_start_us": float(ts[0]),
        "duration_s": float(len(data) / fs) if fs else 0.0,
        "header": hdr,
        "channel": int(recs["channel"][0]),
        "irregular_intervals": irregular,
    }



# ==========================================================================
# Segmentation -- "is this recording continuous?"
# ==========================================================================
# Cheetah closes a record early (nvalid < 512) when acquisition hiccups, and
# the next record's timestamp jumps forward by more than one block. neo calls
# the boundary a section break and spikeinterface exposes the file as a
# multi-segment recording; Toothy then concatenates the segments, which closes
# the gaps and labels every sample after one with a time EARLIER than its
# true time, by the cumulative duration of all preceding gaps. The error is a
# step function, constant inside each segment, and nothing downstream records
# that it happened.
#
# Everything below reproduces neo's `NcsSectionsFactory._buildNcsSections`,
# because the only segmentation worth reporting is the one Toothy saw.

# spikeinterface passes strict_gap_mode=False, which widens the tolerance to a
# quarter of a record. neo's own default is 0.2 of a SAMPLE -- 6.67 us at
# 30 kHz -- which on this hardware counts ordinary clock jitter as a break and
# finds 2717 sections in a file with 8. Pinned in the output so that a future
# spikeinterface default is a visible change and not a mystery.
GAP_FRAC_LOOSE = 0.25          # of a record   (spikeinterface, strict=False)
GAP_FRAC_STRICT = 0.2          # of a sample   (neo, strict=True)
GAP_RULE_LOOSE = "spikeinterface-nonstrict"
GAP_RULE_STRICT = "neo-strict"

# Below this a residual is integer arithmetic, not a hiccup. Timestamps are
# whole microseconds and the predicted interval is truncated, so a perfectly
# continuous record pair differs by a microsecond or two.
ROUNDING_FLOOR_US = 4

_FIELDS = struct.Struct("<QIII")   # timestamp, channel, freq, nvalid

# Whether a file is one continuous block, and where its clock starts,
# remembered per (path, size, mtime).
#
# The windowed reader asks this on every fetch and the answer costs two
# record reads. Over a network mount, with one fetch per channel per frame,
# that is 128 round trips a frame on a 64-channel session to be told
# something that only changes when the file does. Bounded: a scan can touch
# thousands of files and this is a convenience, not a store.
_BLOCK_MEMO = {}
_BLOCK_MEMO_MAX = 512


def acq_type(hdr: dict) -> str:
    """Close enough to NlxHeader.type_of_recording() for the tolerance."""
    system = (hdr.get("AcquisitionSystem") or "").strip()
    if system:
        return system.split()[-1].upper().replace("_", "")
    if "Cheetah" in (hdr.get("ApplicationName") or ""):
        return "DIGITALLYNXSX"
    return "RAWDATAFILE"


def gap_tolerance_us(fs: float, acq: str = "DIGITALLYNXSX",
                     strict: bool = False) -> int:
    """The tolerance neo compares each residual against, in microseconds."""
    if not fs or fs <= 0:
        return 0
    if acq == "PRE4":
        return 0
    if strict:
        return int(round(GAP_FRAC_STRICT * 1e6 / fs))
    return int(round(GAP_FRAC_LOOSE * SAMPLES_PER_RECORD * 1e6 / fs))


def _fields_at(fh, index):
    """(timestamp, channel, freq, nvalid) of one record, without its samples."""
    fh.seek(HEADER_BYTES + index * RECORD_DTYPE.itemsize)
    raw = fh.read(_FIELDS.size)
    if len(raw) < _FIELDS.size:
        return None
    return _FIELDS.unpack(raw)


def record_times(path: str):
    """First and last record of a file, read with two seeks.

    The cheapest honest answer to "when does this start and how long is it".
    `read_ncs`'s duration is the concatenated one (valid samples over fs) and
    `n_records * 512 / fs` is a third number again; this is the recording's
    own clock, which is what the raw files, the .nev marks and the video are
    on.
    """
    size = os.path.getsize(path)
    n_rec = max(0, (size - HEADER_BYTES) // RECORD_DTYPE.itemsize)
    if n_rec == 0:
        return None
    with open(path, "rb") as fh:
        hdr = parse_header(fh.read(HEADER_BYTES))
        first = _fields_at(fh, 0)
        last = _fields_at(fh, n_rec - 1)
    if not first or not last:
        return None
    fs = _header_float(hdr, "SamplingFrequency")
    if not fs or fs <= 0:
        fs = float(first[2]) if first[2] > 0 else DEFAULT_FS
    nv_last = min(int(last[3]), SAMPLES_PER_RECORD)
    end_us = int(last[0]) + int(1e6 / fs * nv_last)
    return {
        "fs": float(fs),
        "n_records": int(n_rec),
        "t0_us": int(first[0]),
        "end_us": int(end_us),
        "true_duration_s": (end_us - int(first[0])) / 1e6,
        "header": hdr,
        "trailing_bytes": int((size - HEADER_BYTES) % RECORD_DTYPE.itemsize),
    }


def _block_key(path):
    """(path, size, mtime) for the memo, or None if it cannot be stat-ed."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (os.path.normcase(os.path.abspath(path)), int(st.st_size),
            int(st.st_mtime_ns))


def _memo_put(key, value):
    if not key:
        return
    if len(_BLOCK_MEMO) >= _BLOCK_MEMO_MAX:
        _BLOCK_MEMO.clear()
    _BLOCK_MEMO[key] = value


def _single_block(fs, first, last, n_rec):
    """neo's fast path: is the last timestamp exactly what full records predict?

    Two records answer it, so a continuous file never pays for a pass over
    130 MB of samples to be told it is continuous.
    """
    if n_rec < 2:
        return True
    predicted = int(round(first[0] + (1e6 / fs) * SAMPLES_PER_RECORD
                          * (n_rec - 1)))
    return (first[1] == last[1] and first[2] == last[2]
            and int(last[0]) == predicted)


def segment_ncs(path: str, strict: bool = False):
    """Segment one .ncs the way neo and spikeinterface do.

    Returns the segment map, the gaps between segments, and the three
    durations this recording can be said to have. Reads timestamps and valid
    counts only -- never the samples.
    """
    size = os.path.getsize(path)
    n_rec = max(0, (size - HEADER_BYTES) // RECORD_DTYPE.itemsize)
    if n_rec == 0:
        raise ValueError("no records in %s" % os.path.basename(path))

    with open(path, "rb") as fh:
        hdr = parse_header(fh.read(HEADER_BYTES))
        first = _fields_at(fh, 0)
        last = _fields_at(fh, n_rec - 1)
    if first is None or last is None:
        raise ValueError("truncated: %s" % os.path.basename(path))

    fs = _header_float(hdr, "SamplingFrequency")
    if not fs or fs <= 0:
        fs = float(first[2]) if first[2] > 0 else DEFAULT_FS
    acq = acq_type(hdr)
    tol = gap_tolerance_us(fs, acq, strict)

    fast = _single_block(fs, first, last, n_rec)
    if fast:
        # Every record full, so the counts follow without reading them.
        ts = None
        nv_sum = n_rec * SAMPLES_PER_RECORD
        limits = [0, n_rec]
        starts = [int(first[0])]
        ends = [int(last[0]) + int(1e6 / fs * SAMPLES_PER_RECORD)]
        counts = [nv_sum]
        n_short = 0
        n_short_inside = 0
        sub_us = 0
    else:
        mm = np.memmap(path, dtype=RECORD_DTYPE, mode="r",
                       offset=HEADER_BYTES, shape=(int(n_rec),))
        ts = np.asarray(mm["timestamp"], dtype=np.int64)
        nv = np.minimum(np.asarray(mm["nvalid"], dtype=np.int64),
                        SAMPLES_PER_RECORD)
        del mm

        # neo's rule, and only neo's rule: the residual between the observed
        # interval and the one the PREVIOUS record's valid count predicts.
        delta = ts[1:] - ts[:-1]
        predicted = ((nv[:-1] / fs) * 1e6).astype(np.int64)
        breaks = np.flatnonzero(np.abs(delta - predicted) > tol) + 1
        limits = [0] + breaks.tolist() + [int(n_rec)]
        starts, ends, counts = [], [], []
        for a, b in zip(limits[:-1], limits[1:]):
            starts.append(int(ts[a]))
            ends.append(int(ts[b - 1]) + int(1e6 / fs * nv[b - 1]))
            counts.append(int(nv[a:b].sum()))
        nv_sum = int(nv.sum())
        n_short = int(np.count_nonzero(nv != SAMPLES_PER_RECORD))

        # Time that passed inside a segment with nothing recorded for it.
        #
        # Only at records Cheetah closed early. A full record's residual is
        # the truncation in `int(1e6 / fs * nvalid)` -- exactly 1 us, measured
        # -- and summing that across 124,485 records reports 290 ms of "loss"
        # on a recording that lost nothing. A short record is where
        # acquisition actually hiccupped, so the gap between it and the next
        # record, beyond what its own samples account for, is real.
        #
        # Breaks are excluded: those are the segment gaps and are counted
        # there. What is left is the loss that no segment boundary records,
        # which is the whole reason for saying it.
        resid = delta - predicted
        short_at = (nv[:-1] != SAMPLES_PER_RECORD)
        # Above the arithmetic. Timestamps are whole microseconds and
        # `int(1e6 / fs * nvalid)` truncates, so a record that lost nothing
        # still shows a residual of one or two microseconds -- measured: the
        # median on a full record is exactly 1 us. The smallest real one in
        # the PTEN archive is 67 us, so a floor here separates them by a
        # factor of twenty without needing to be tuned.
        inside = (short_at & (np.abs(resid) <= tol)
                  & (resid > ROUNDING_FLOOR_US))
        sub_us = int(resid[inside].sum())
        n_short_inside = int(np.count_nonzero(inside))

    t0_us = int(first[0])
    segments, gaps, cum_lost_us, cum_samples = [], [], 0, 0
    for i, (a, b) in enumerate(zip(limits[:-1], limits[1:])):
        true_t0 = (starts[i] - t0_us) / 1e6
        concat_t0 = cum_samples / fs
        segments.append({
            "index": i,
            "start_rec": int(a), "end_rec": int(b - 1),
            "start_us": starts[i], "end_us": ends[i],
            "n_samples": counts[i],
            "true_t0_s": true_t0,
            "concat_t0_s": concat_t0,
            "duration_s": counts[i] / fs,
            # Positive: Toothy calls this stretch EARLIER than it really is.
            "error_ms": (true_t0 - concat_t0) * 1e3,
        })
        if i:
            gap_us = starts[i] - ends[i - 1]
            cum_lost_us += gap_us
            gaps.append({
                "after_record": int(limits[i] - 1),
                "at_true_time_s": (ends[i - 1] - t0_us) / 1e6,
                "gap_s": gap_us / 1e6,
                "gap_ms": gap_us / 1e3,
                "gap_samples_equiv": gap_us * fs / 1e6,
                "cumulative_shift_s": cum_lost_us / 1e6,
            })
        cum_samples += counts[i]

    true_dur = (ends[-1] - t0_us) / 1e6
    concat_dur = nv_sum / fs
    lost = cum_lost_us / 1e6
    # Time lost is the sum of the real gaps and nothing else. Inferring it
    # from (true - concat) also picks up the difference between the nominal
    # sample rate and the hardware's actual one -- the lab's clocks run at
    # 29998.6 Hz, not 30000 -- which reports twenty milliseconds of "loss" on
    # a file that lost nothing at all, and can go negative.
    drift = (true_dur - concat_dur) - lost

    return {
        "path": path,
        "name": hdr.get("AcqEntName") or os.path.basename(path),
        "fs": float(fs),
        "acq_type": acq,
        "channel": int(first[1]),
        "strict": bool(strict),
        "gap_rule": GAP_RULE_STRICT if strict else GAP_RULE_LOOSE,
        "gap_tolerance_us": int(tol),
        "fast_path": bool(fast),
        "n_records": int(n_rec),
        "trailing_bytes": int((size - HEADER_BYTES) % RECORD_DTYPE.itemsize),
        "t0_us": t0_us,
        "end_us": int(ends[-1]),
        "n_segments": len(segments),
        "segments": segments,
        "gaps": gaps,
        "total_samples": int(nv_sum),
        # The three answers to "how long is it", all of them defensible and
        # all of them different once the file has a gap in it.
        "true_duration_s": true_dur,          # the recording's own clock
        "concat_duration_s": concat_dur,      # what Toothy assigns
        "record_duration_s": n_rec * SAMPLES_PER_RECORD / fs,   # by record
        "seconds_lost": lost,
        "samples_lost": lost * fs,
        "clock_drift_s": drift,
        "implied_fs": (nv_sum - 1) / true_dur if true_dur else float(fs),
        "n_short_records": int(n_short),
        # Short records that did NOT make a break, and the time unaccounted
        # for at them. This is the loss no segment boundary records.
        "n_short_inside": int(n_short_inside),
        "sub_threshold_lost_s": sub_us / 1e6,
        # Buffer slots a short record left unused. NOT a measure of loss:
        # when the next record's timestamp follows the short count, the
        # record was simply short and no time passed unrecorded. Kept because
        # it is what the reference script prints, under a name that says what
        # it counts.
        "unused_record_slots": int(n_rec * SAMPLES_PER_RECORD - nv_sum),
        "max_time_error_ms": (segments[-1]["error_ms"] if len(segments) > 1
                              else 0.0),
    }

def _seek_record(fh, n_rec, target_us, lo=0):
    """Index of the last record whose timestamp is <= `target_us`.

    Binary search, not arithmetic. `r0 = floor(t / block)` assumes every
    record is full and that no timestamp ever jumps; on a recording with gaps
    it drifts by the whole accumulated gap total, which on M8s9feb8 is 200 ms
    against the concatenated basis by the end of the file. Timestamps only
    increase, so seventeen twenty-byte reads answer this exactly on a file of
    any size, and on a continuous file they land on the same record the
    arithmetic would have picked.
    """
    hi = n_rec - 1
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        rec = _fields_at(fh, mid)
        if rec is None:
            hi = mid - 1
            continue
        if rec[0] <= target_us:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def read_ncs_range(path: str, t0: float, t1: float, invert: bool = True,
                   report: dict = None):
    """Read only samples in [t0, t1) seconds from the first record's time.

    Seeks directly to the needed records, so scrubbing a long session stays
    responsive regardless of file size. The seek is by timestamp, so the
    window lands where the recording's own clock says it should even when
    Cheetah left gaps -- see `segment_ncs` for what those are.

    The returned samples are still contiguous: a window spanning a gap is
    short by the gap rather than padded, because the samples were never
    recorded and inventing them is worse than being short. `report`, if given,
    is filled in with the gaps the window crossed so the caller can say so.
    """
    size = os.path.getsize(path)
    n_rec = max(0, (size - HEADER_BYTES) // RECORD_DTYPE.itemsize)
    if n_rec == 0:
        return np.empty(0, dtype=np.float32), 0.0, DEFAULT_FS

    memo_key = _block_key(path)
    memo = _BLOCK_MEMO.get(memo_key) if memo_key else None

    with open(path, "rb") as fh:
        hdr = parse_header(fh.read(HEADER_BYTES))
        adbv = _header_float(hdr, "ADBitVolts") or FALLBACK_ADBITVOLTS
        fs = _header_float(hdr, "SamplingFrequency")

        first = None
        if memo is None or fs is None or fs <= 0:
            # Only when the answer is not already known, or the header did
            # not say what the rate is.
            first = _fields_at(fh, 0)
            if fs is None or fs <= 0:
                fs = float(first[2]) if first and first[2] > 0 else DEFAULT_FS

        if memo is None:
            last = _fields_at(fh, n_rec - 1) if n_rec > 1 else first
            flat = bool(n_rec > 1 and _single_block(fs, first, last, n_rec))
            memo = (flat, int(first[0]) if first else 0)
            _memo_put(memo_key, memo)
        flat, t_start = memo

        block = SAMPLES_PER_RECORD / fs
        if flat:
            # Every record full and no timestamp jump, so record i really
            # does start at i * block and the arithmetic is exact. This is
            # the path a continuous file took before the seek existed, and
            # it still touches no record header to take it.
            r0 = max(0, int(np.floor(t0 / block)))
            r1 = min(n_rec, int(np.ceil(t1 / block)) + 1)
            actual_t0 = r0 * block
        else:
            r0 = _seek_record(fh, n_rec, t_start + int(t0 * 1e6))
            r1 = min(n_rec,
                     _seek_record(fh, n_rec, t_start + int(t1 * 1e6), lo=r0)
                     + 2)
            rec0 = _fields_at(fh, r0)
            actual_t0 = ((int(rec0[0]) - t_start) / 1e6) if rec0 else 0.0

        if r1 <= r0:
            return np.empty(0, dtype=np.float32), 0.0, fs

        fh.seek(HEADER_BYTES + r0 * RECORD_DTYPE.itemsize)
        recs = np.fromfile(fh, dtype=RECORD_DTYPE, count=(r1 - r0))

        if report is not None:
            _window_gaps(report, recs, fs, t_start, actual_t0)

    if recs.size == 0:
        return np.empty(0, dtype=np.float32), 0.0, fs

    nvalid = np.minimum(recs["nvalid"], SAMPLES_PER_RECORD).astype(np.int64)
    if np.all(nvalid == SAMPLES_PER_RECORD):
        data = recs["samples"].reshape(-1).astype(np.float32)
    else:
        keep = np.zeros(recs["samples"].shape, dtype=bool)
        for i, n in enumerate(nvalid):
            keep[i, :n] = True
        data = recs["samples"][keep].astype(np.float32)

    # The sign is folded into the scale factor. Negating afterwards meant a
    # second full pass and a second full-size allocation per channel, which on
    # a long window is tens of megabytes of pure copying.
    data *= np.float32((-adbv if invert else adbv) * 1e6)
    return data, float(actual_t0), float(fs)


def _window_gaps(report, recs, fs, t_start, actual_t0):
    """Which discontinuities fall inside the window that was just read.

    The samples come back contiguous, so a window that crosses a gap is short
    by it -- the trace after the gap sits earlier on screen than it belongs.
    That is a small error inside one window rather than the accumulated one
    the old arithmetic carried, but it is not nothing, and the honest thing is
    to hand it back rather than let the caller assume a uniform axis.
    """
    report["gaps"] = []
    report["gap_s"] = 0.0
    report["t0_s"] = float(actual_t0)
    if recs.size < 2:
        return
    ts = recs["timestamp"].astype(np.int64)
    nv = np.minimum(recs["nvalid"].astype(np.int64), SAMPLES_PER_RECORD)
    tol = gap_tolerance_us(fs)
    resid = (ts[1:] - ts[:-1]) - ((nv[:-1] / fs) * 1e6).astype(np.int64)
    for i in np.flatnonzero(np.abs(resid) > tol):
        report["gaps"].append({
            "at_s": float((ts[i] - t_start) / 1e6
                          + nv[i] / fs),
            "gap_ms": float(resid[i] / 1e3),
        })
        report["gap_s"] += float(resid[i] / 1e6)


def list_csc_files(folder: str, even_only: bool = False):
    """List CSC*.ncs in `folder`, numerically sorted.

    `even_only` skips the odd-numbered channels. It used to default to True,
    described as the lab default -- and on the 64-channel probe that silently
    halved every recording. Whether the odd channels are real is a question
    about the recording, so ask channel_scheme(); this does what it is told.

    Returns a list of (channel_number, full_path).
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found, parts = [], {}
    for name in names:
        m = _CSC_NAME_RE.match(name)
        if not m:
            continue
        num = int(m.group(1))
        if even_only and num % 2 != 0:
            continue
        seq = int(m.group(2) or 0)
        # One entry per channel: the first part is the channel. Later parts
        # are continuations and are reported by csc_parts() rather than
        # silently becoming extra channels.
        if num not in parts or seq < parts[num][0]:
            parts[num] = (seq, os.path.join(folder, name))
    for num in sorted(parts):
        found.append((num, parts[num][1]))
    return found


def csc_parts(folder):
    """Channel -> every file for it, in order. More than one means the
    acquisition was split, which is worth saying out loud."""
    out = {}
    for name in sorted(_ls(folder)):
        m = _CSC_NAME_RE.match(name)
        if not m:
            continue
        out.setdefault(int(m.group(1)), []).append(
            (int(m.group(2) or 0), os.path.join(folder, name)))
    return {k: [p for _s, p in sorted(v)] for k, v in out.items()}


def data_records(path):
    """How many data records a .ncs holds, from its size alone.

    No read: a header-only file is 16384 bytes and this has to be cheap
    enough to run on every file of every folder during a scan.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return -1
    return max(0, (size - HEADER_BYTES) // RECORD_DTYPE.itemsize)


def _ls(d):
    try:
        return os.listdir(d)
    except OSError:
        return []



# --------------------------------------------------------------------------
# Which channels a recording actually uses
# --------------------------------------------------------------------------
# Two rigs, two answers. On the older one a 32-channel probe was wired to the
# even AD channels and the odd ones carried nothing, so loading every file
# meant thirty-two flat traces. On the 64-channel probe every file is real,
# and skipping the odd ones means looking at half the shank.
#
# `even_only=True` used to be the default, and on this repo's recordings it
# was wrong every time:
#
#     CSC1  std  982     CSC2  std  644
#     CSC31 std 1101     CSC32 std  835
#     CSC63 std  606     CSC64 std  602
#
# Half of every recording loaded, and a channel list of 32 looks perfectly
# plausible, so nothing ever said so. There is no default that is right for
# both rigs -- so measure instead of assuming.
FLAT_ADC = 5.0          # a standard deviation this small is not a signal
SAMPLE_RECORDS = 8      # ~4000 samples per channel is plenty to tell


def _sample_ncs(path, n_rec=SAMPLE_RECORDS, skip_rec=200):
    """A few thousand raw samples from part-way into a file.

    Raw ADC counts, unfiltered and unscaled: the question is "is anything
    connected here", not "what does it look like", and reading whole files to
    answer it would cost a minute per recording.
    """
    try:
        recs = np.fromfile(path, dtype=RECORD_DTYPE, count=n_rec,
                           offset=HEADER_BYTES + skip_rec * RECORD_DTYPE.itemsize)
    except (OSError, ValueError):
        return np.empty(0, dtype="<i2")
    if recs.size == 0:
        return np.empty(0, dtype="<i2")
    return recs["samples"].reshape(-1)


def channel_scheme(folder, probe=4):
    """Does this recording use every channel, or only the even ones?

    Returns the measurement, not just a verdict -- somebody will eventually
    want to see why rather than take it on trust.
    """
    files = list_csc_files(folder, even_only=False)
    if not files:
        return {"scheme": "all", "n_files": 0, "why": "no CSC files here"}

    odd = [(n, p) for n, p in files if n % 2]
    even = [(n, p) for n, p in files if not n % 2]
    if not odd:
        return {"scheme": "all", "n_files": len(files), "odd_files": 0,
                "why": "there are no odd-numbered channels to skip"}

    def pick(seq):
        if len(seq) <= probe:
            return seq
        step = max(1, len(seq) // probe)
        return seq[::step][:probe]

    by_num = dict(files)
    odd_sd, even_sd, flat, dup = [], [], 0, 0
    for num, path in pick(odd):
        vals = _sample_ncs(path)
        if vals.size < 2:
            continue
        sd = float(np.std(vals))
        odd_sd.append(sd)
        if sd < FLAT_ADC:
            flat += 1
            continue
        # The other way an odd channel turns up unused: not flat, but an
        # exact copy of the AD channel next to it.
        for other in (num + 1, num - 1):
            if other in by_num:
                twin = _sample_ncs(by_num[other])
                if twin.size == vals.size and np.array_equal(twin, vals):
                    dup += 1
                    break
    for _num, path in pick(even):
        vals = _sample_ncs(path)
        if vals.size >= 2:
            even_sd.append(float(np.std(vals)))

    odd_med = float(np.median(odd_sd)) if odd_sd else 0.0
    even_med = float(np.median(even_sd)) if even_sd else 0.0
    unused = flat + dup

    if odd_sd and unused >= (len(odd_sd) + 1) // 2:
        scheme = "even"
        why = ("the odd channels carry nothing -- %d of %d sampled were flat "
               "or an exact copy of their neighbour -- so this is a "
               "32-channel probe on 64 inputs" % (unused, len(odd_sd)))
    else:
        scheme = "all"
        why = ("every channel carries signal (odd median %.0f ADC counts "
               "against even %.0f), so all %d are real"
               % (odd_med, even_med, len(files)))

    return {
        "scheme": scheme,
        "n_files": len(files),
        "odd_files": len(odd),
        "odd_std": round(odd_med, 1),
        "even_std": round(even_med, 1),
        "odd_flat": flat,
        "odd_duplicated": dup,
        "sampled": len(odd_sd),
        "why": why,
    }

# --------------------------------------------------------------------------
# VT (video tracking) files -- position, not video
# --------------------------------------------------------------------------
# A Neuralynx .nvt record is 1828 bytes:
#     uint16 swstx, swid, swdata_size
#     uint64 qwTimeStamp   (microseconds)
#     uint32 dwPoints[400] (bitfield blob, not needed for position)
#     int16  sncrc
#     int32  dnextracted_x, dnextracted_y, dnextracted_angle
#     int32  dntargets[50]
NVT_DTYPE = np.dtype([
    ("swstx", "<u2"), ("swid", "<u2"), ("swdata_size", "<u2"),
    ("timestamp", "<u8"),
    ("points", "<u4", (400,)),
    ("crc", "<i2"),
    ("x", "<i4"), ("y", "<i4"), ("angle", "<i4"),
    ("targets", "<i4", (50,)),
])


def read_nvt(path, max_records=0):
    """Read a Neuralynx .nvt position-tracking file.

    Returns (t_seconds, x, y, angle) with time relative to the first sample.
    Zero coordinates mean the tracker lost the animal; those come back as NaN
    so they leave a gap instead of snapping the path to the origin.
    """
    size = os.path.getsize(path)
    n_rec = max(0, (size - HEADER_BYTES) // NVT_DTYPE.itemsize)
    if max_records and n_rec > max_records:
        n_rec = max_records
    if n_rec == 0:
        return (np.empty(0), np.empty(0), np.empty(0), np.empty(0), {})

    with open(path, "rb") as fh:
        hdr = parse_header(fh.read(HEADER_BYTES))
        recs = np.fromfile(fh, dtype=NVT_DTYPE, count=n_rec)

    ts = recs["timestamp"].astype(np.float64)
    t = (ts - ts[0]) / 1e6 if ts.size else ts

    x = recs["x"].astype(np.float64)
    y = recs["y"].astype(np.float64)
    ang = recs["angle"].astype(np.float64)
    lost = (x == 0) & (y == 0)
    x[lost] = np.nan
    y[lost] = np.nan

    meta = {
        "n_records": int(n_rec),
        "duration_s": float(t[-1]) if t.size else 0.0,
        "fps": float(n_rec / t[-1]) if t.size and t[-1] > 0 else 0.0,
        "t_start_us": float(ts[0]) if ts.size else 0.0,
        "lost_frac": float(np.mean(lost)) if lost.size else 0.0,
        "header": hdr,
    }
    return t, x, y, ang, meta


# --------------------------------------------------------------------------
# Event files (.nev) -- Cheetah's own event log
# --------------------------------------------------------------------------
# A Neuralynx .nev record is 184 bytes:
#     int16  nstx, npkt_id, npkt_data_size
#     uint64 qwTimeStamp        (microseconds, SAME clock as the CSC files)
#     int16  nevent_id, nttl, ncrc, ndummy1, ndummy2
#     int32  dnExtra[8]
#     char   EventString[128]
NEV_DTYPE = np.dtype([
    ("stx", "<i2"), ("pkt_id", "<i2"), ("pkt_data_size", "<i2"),
    ("timestamp", "<u8"),
    ("event_id", "<i2"), ("ttl", "<i2"), ("crc", "<i2"),
    ("dummy1", "<i2"), ("dummy2", "<i2"),
    ("extra", "<i4", (8,)),
    ("event_string", "S128"),
])
assert NEV_DTYPE.itemsize == 184, NEV_DTYPE.itemsize


def read_nev(path):
    """Read a Neuralynx .nev event file.

    Timestamps come back as ABSOLUTE microseconds, on the same clock as the CSC
    files. Converting to session-relative seconds needs the recording's own
    t_start_us, which is why that subtraction happens in the caller rather than
    here -- an event file on its own has no idea when the recording began.
    """
    size = os.path.getsize(path)
    n_rec = max(0, (size - HEADER_BYTES) // NEV_DTYPE.itemsize)
    if n_rec == 0:
        return np.empty(0, dtype=NEV_DTYPE), {}

    with open(path, "rb") as fh:
        hdr = parse_header(fh.read(HEADER_BYTES))
        recs = np.fromfile(fh, dtype=NEV_DTYPE, count=n_rec)

    return recs, {"n_records": int(len(recs)), "header": hdr,
                  "t_start_us": float(recs["timestamp"][0]) if len(recs) else 0.0}


def nev_events(path, t_start_us=None):
    """Turn a .nev into plain event dicts with times in seconds.

    `t_start_us` is the recording's first CSC timestamp. Without it, times are
    relative to the first event instead, which is right often enough to be
    useful but is reported so the caller can say so.
    """
    recs, meta = read_nev(path)
    if len(recs) == 0:
        return [], {"n": 0, "relative_to": "none", "labels": []}

    ts = recs["timestamp"].astype(np.float64)
    origin = float(t_start_us) if t_start_us is not None else float(ts[0])
    rel = (ts - origin) / 1e6

    out, labels = [], {}
    for i in range(len(recs)):
        raw = recs["event_string"][i]
        text = raw.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()
        ttl = int(recs["ttl"][i])
        label = text or ("TTL %d" % ttl)
        labels[label] = labels.get(label, 0) + 1
        out.append({
            "start": float(rel[i]),
            "label": label,
            "ttl": ttl,
            "event_id": int(recs["event_id"][i]),
            "source": "nev",
        })

    return out, {
        "n": len(out),
        "relative_to": "recording" if t_start_us is not None else "first_event",
        "labels": sorted(labels.items(), key=lambda kv: -kv[1])[:20],
        "header": meta.get("header", {}),
    }
