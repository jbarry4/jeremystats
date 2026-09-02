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

_CSC_NAME_RE = re.compile(r"^CSC(\d+)\.ncs$", re.IGNORECASE)


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
            "channel": None, "gaps": 0,
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
    # A "gap" is any inter-record interval that departs from the nominal block
    # duration by more than half a block -- same idea as RemoveCSCGaps.m.
    gaps = 0
    if len(ts) > 1:
        nominal = SAMPLES_PER_RECORD / fs * 1e6
        dt = np.diff(ts)
        gaps = int(np.sum(np.abs(dt - nominal) > nominal * 0.5))

    return data, {
        "fs": float(fs),
        "adbitvolts": float(adbv),
        "n_records": int(len(recs)),
        "t_start_us": float(ts[0]),
        "duration_s": float(len(data) / fs) if fs else 0.0,
        "header": hdr,
        "channel": int(recs["channel"][0]),
        "gaps": gaps,
    }


def read_ncs_range(path: str, t0: float, t1: float, invert: bool = True):
    """Read only samples in [t0, t1) seconds relative to file start.

    Seeks directly to the needed records, so scrubbing a long session stays
    responsive regardless of file size.
    """
    size = os.path.getsize(path)
    n_rec = max(0, (size - HEADER_BYTES) // RECORD_DTYPE.itemsize)
    if n_rec == 0:
        return np.empty(0, dtype=np.float32), 0.0, DEFAULT_FS

    with open(path, "rb") as fh:
        hdr = parse_header(fh.read(HEADER_BYTES))
        adbv = _header_float(hdr, "ADBitVolts") or FALLBACK_ADBITVOLTS
        fs = _header_float(hdr, "SamplingFrequency")
        if fs is None or fs <= 0:
            fh.seek(HEADER_BYTES)
            probe = np.fromfile(fh, dtype=RECORD_DTYPE, count=1)
            fs = float(probe["freq"][0]) if probe.size and probe["freq"][0] > 0 else DEFAULT_FS

        block = SAMPLES_PER_RECORD / fs
        r0 = max(0, int(np.floor(t0 / block)))
        r1 = min(n_rec, int(np.ceil(t1 / block)) + 1)
        if r1 <= r0:
            return np.empty(0, dtype=np.float32), 0.0, fs

        fh.seek(HEADER_BYTES + r0 * RECORD_DTYPE.itemsize)
        recs = np.fromfile(fh, dtype=RECORD_DTYPE, count=(r1 - r0))

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
    return data, r0 * block, float(fs)


def list_csc_files(folder: str, even_only: bool = True):
    """List CSC*.ncs in `folder`, numerically sorted.

    `even_only` matches the lab default (probe channels are the even numbers).
    Returns a list of (channel_number, full_path).
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = []
    for name in names:
        m = _CSC_NAME_RE.match(name)
        if not m:
            continue
        num = int(m.group(1))
        if even_only and num % 2 != 0:
            continue
        found.append((num, os.path.join(folder, name)))
    found.sort(key=lambda t: t[0])
    return found


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
