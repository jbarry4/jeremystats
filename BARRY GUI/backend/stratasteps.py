"""
stratasteps.py -- the evidence StrataScope's steps are decided from.

StrataScope began as a rail you painted while looking at live panes. That is
labelling, not a method: two people looking at the same CSD put the fissure in
different places, and neither can say afterwards why. The steps make it a
method. Jarvis measures, per channel, the things each boundary is known to show
-- ripples at the pyramidal layer, theta peaking at the fissure, multiunit
activity in the granule cells -- proposes a line, and a person moves it and
says how sure they are.

    0  Theta Walk          when the animal was walking (theta), painted by hand
    1  Crystallize CA1     so / sp / sr / slm and the fissure
    2  Find the hilus      the two granule layers, and the hilus between them
    3  GCL, IML, MML, OML  the molecular layer in thirds (Method A), checked
                           by pathway-specific gamma (Method B, ICA)
    4  Sign off

NO DENTATE SPIKES, ANYWHERE IN HERE
-----------------------------------
The hilus is the easiest layer to find with dentate spikes -- they are largest
there -- and that is exactly why they are not used. These labels are what the
DS results get checked against. A hilus found from DS amplitude, used to
validate DS amplitude, validates nothing. So the hilus comes from multiunit
activity in the two granule layers, and nothing in this file reads the event
bank's DS entries, Incisor's picks, or a DS-filtered trace.

ONE READ, THEN EVERYTHING ELSE IS ARITHMETIC
--------------------------------------------
Reading 64 channels of a 30-minute recording at 30 kHz is the expensive part
-- minutes -- and every question the steps ask depends on choices made after
it: which seconds are Theta Walk, which channel is the reference. So the read
happens once and keeps two things:

    bins    per channel, per second: band powers, the theta-band Fourier
            coefficients, a 4-12 Hz spectrum, multiunit power. Small, and
            enough to answer any depth curve for any set of seconds without
            touching the files again -- including phase and coherence against
            ANY reference channel, because a cross-spectrum is a sum of
            products of coefficients that are already here.
    lfp     every channel at 1250 Hz, int16, memory-mapped. What ripple
            detection, the triggered averages and ICA read. Large (about
            290 MB for half an hour of 64 channels), so only the most
            recently used few are kept; the bins are kept for good.

Both live in GUI_logs/.cache/strata/<gid>/, which is gitignored: they are this
machine's cache, not a record. The record is the layer sheet (layers.py).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import csc, lazyimp, shards

_sig = lazyimp.module("scipy.signal")
_fft = lazyimp.module("scipy.fft")

SCHEMA = 2

LFP_FS = 1250.0          # the rate everything after the read works at
BIN_S = 1.0              # one row of the bins per second of recording
CHUNK_S = 120.0          # read in pieces this long, so memory stays bounded
EDGE_S = 1.0             # read past each end of a piece, for the filters
SPEC_WIN_S = 4.0         # the 4-12 Hz spectrum's window: 0.25 Hz resolution
SPEC_LO, SPEC_HI = 4.0, 12.0
DOM_LO, DOM_HI = 5.0, 11.0     # where a "dominant theta" peak may sit
MUA_BAND = (300.0, 6000.0)
MIN_SEGMENT_S = 0.5

# Band powers kept per bin. The order is the array's last axis.
BANDS = [
    ("delta", 1.0, 4.0),
    ("theta", 6.0, 10.0),
    ("slow_gamma", 25.0, 45.0),
    ("mid_gamma", 60.0, 100.0),
    ("fast_gamma", 100.0, 150.0),
    # Toothy's ripple band (qparam.py swr_freq), so the curve and the
    # detector are measuring the same thing.
    ("ripple", 120.0, 180.0),
]
BAND_INDEX = {b[0]: i for i, b in enumerate(BANDS)}
THETA_BAND = (6.0, 10.0)

# How many recordings' 1250 Hz copies to keep. The bins are kept for every
# recording ever scanned; these are not, because each one is hundreds of MB.
LFP_KEEP_BYTES = 3 * 1024 ** 3

DIR = None
_LOCK = threading.RLock()
_BINS = {}               # gid -> Bins, the few most recently asked for
_BINS_ORDER = []
_BINS_MAX = 4


class StrataError(Exception):
    """A failure with a message meant for the person looking at the screen."""


def configure(logs_dir):
    global DIR
    DIR = os.path.join(logs_dir, ".cache", "strata")
    os.makedirs(DIR, exist_ok=True)


def _dir(gid):
    if not DIR:
        raise StrataError("StrataScope's cache folder is not configured.")
    return os.path.join(DIR, shards.safe_base(gid))


# --------------------------------------------------------------------------
# What a recording is, for the purpose of knowing a scan is still good
# --------------------------------------------------------------------------
def source_stamp(session):
    """A digest that changes when the recording's files do.

    File sizes and modification times, not contents: hashing gigabytes to
    find out whether to read gigabytes would be the cost twice. A recording
    that is re-exported or has a channel file added reads as a new one.
    """
    h = hashlib.sha1()
    h.update(str(session.get("source")).encode())
    h.update(str(session.get("path")).encode())
    h.update(str(session.get("fs")).encode())
    h.update(str(bool(session.get("invert", True))).encode())
    for ch in session.get("channels") or []:
        f = ch.get("file")
        h.update(str(ch.get("number")).encode())
        if f and os.path.exists(f):
            st = os.stat(f)
            h.update(("%s:%d:%d" % (os.path.basename(f), st.st_size,
                                    int(st.st_mtime))).encode())
    return h.hexdigest()[:16]


def segments_for(session, report):
    """The stretches of recording with no gap in them, in true seconds.

    From the continuity report when there is one -- a Neuralynx recording
    stopped and started has gaps, and a sample index stops meaning a time the
    moment you cross one. A demo or a .mat has no records to have gaps in, so
    it is one stretch, the whole thing.
    """
    segs = [s for s in ((report or {}).get("segments") or [])
            if float(s.get("duration_s") or 0) >= MIN_SEGMENT_S]
    if segs:
        return [{"index": int(s.get("index", i)),
                 "t0": float(s["true_t0_s"]),
                 "t1": float(s["true_t0_s"]) + float(s["duration_s"])}
                for i, s in enumerate(segs)]
    dur = float(session.get("duration_s") or 0.0)
    if dur <= 0:
        raise StrataError("This recording has no length to read.")
    return [{"index": 0, "t0": 0.0, "t1": dur}]


def plan_for(session, report, channels=None):
    """The shape of a scan, without doing any of it."""
    fs = float(session.get("fs") or 30000.0)
    q = max(1, int(round(fs / LFP_FS)))
    lfs = fs / q
    segs = segments_for(session, report)
    end = max(s["t1"] for s in segs)
    n_samp = int(math.ceil(end * lfs)) + 1
    nper = int(round(BIN_S * lfs))
    n_bins = int(math.floor(end / BIN_S))
    starts = np.rint(np.arange(n_bins) * BIN_S * lfs).astype(np.int64)
    keep = starts + nper <= n_samp
    starts = starts[keep]
    n_bins = int(starts.size)
    chans = [c for c in (session.get("channels") or [])
             if channels is None or int(c["number"]) in set(channels)]
    span = sum(s["t1"] - s["t0"] for s in segs)
    return {
        "fs": fs, "q": q, "lfp_fs": lfs, "segments": segs, "end_s": end,
        "span_s": span, "n_samp": n_samp, "nper": nper, "n_bins": n_bins,
        "bin_starts": starts, "channels": chans,
        "n_channels": len(chans),
        "megasamples": span * fs * max(1, len(chans)) / 1e6,
        "lfp_bytes": n_samp * 2 * max(1, len(chans)),
    }


def plan_public(plan):
    return {k: v for k, v in plan.items()
            if k not in ("bin_starts", "channels", "segments")} | {
        "segments": len(plan["segments"]),
        "channel_numbers": [int(c["number"]) for c in plan["channels"]],
    }


# --------------------------------------------------------------------------
# The read
# --------------------------------------------------------------------------
def _mua_sos(fs):
    nyq = fs / 2.0
    hi = min(MUA_BAND[1], nyq * 0.95)
    return _sig.butter(3, [MUA_BAND[0] / nyq, hi / nyq], btype="band",
                       output="sos")


def _scan_channel(session, ch, plan, job=None, on_chunk=None):
    """One channel: its 1250 Hz trace, and its multiunit power per bin.

    Each piece is read with a second either side, decimated as a whole, and
    then only the samples inside the piece are kept -- the decimator's edge
    ringing lands in the margin, not at a boundary every two minutes. Every
    kept sample is placed by its own time (the record timestamps, through
    `got_t0`), so a gap between segments stays a gap rather than closing up
    and shifting everything after it.
    """
    q, lfs, n = plan["q"], plan["lfp_fs"], plan["n_samp"]
    nb = plan["n_bins"]
    lfp = np.full(n, np.nan, dtype=np.float32)
    mua_sum = np.zeros(nb + 1, dtype=np.float64)
    mua_n = np.zeros(nb + 1, dtype=np.float64)
    sos = None
    for seg in plan["segments"]:
        a = seg["t0"]
        while a < seg["t1"] - 1e-9:
            if job is not None:
                job.check()
            b = min(a + CHUNK_S, seg["t1"])
            r0, r1 = max(seg["t0"], a - EDGE_S), min(seg["t1"], b + EDGE_S)
            raw, got_t0, got_fs = csc._read_channel_window(session, ch, r0, r1)
            got_fs = float(got_fs or plan["fs"])
            if raw is None or raw.size < 8 * q:
                a = b
                continue
            x = np.asarray(raw, dtype=np.float64)

            # Inside one segment the samples are evenly spaced, so where a
            # sample lands is arithmetic on its index rather than a time
            # computed and compared per sample -- which, on 3.6 million
            # samples a piece, was most of the read's cost.
            dec = _sig.resample_poly(x, 1, q)
            step = q / got_fs
            j0 = max(0, int(math.ceil((a - got_t0) / step - 1e-9)))
            j1 = min(dec.size, int(math.ceil((b - got_t0) / step - 1e-9)))
            if j1 > j0:
                k0 = int(round((got_t0 + j0 * step) * lfs))
                k1 = min(n, k0 + (j1 - j0))
                if k1 > k0 >= 0:
                    lfp[k0:k1] = dec[j0:j0 + (k1 - k0)]

            if sos is None:
                sos = _mua_sos(got_fs)
            # Started from rest at the first sample's level, not from zero:
            # a filter that begins at zero meets a DC offset as a step, and
            # the step's ringing lands in the first bin of every piece.
            zi = _sig.sosfilt_zi(sos) * x[0]
            m, _ = _sig.sosfilt(sos, x, zi=zi)
            # Summed per bin from a running total: the bin edges are sample
            # indices, so each bin is one subtraction.
            c = np.concatenate(([0.0], np.cumsum(m * m)))
            b_lo = max(0, int(math.floor(a / BIN_S)))
            b_hi = min(nb, int(math.ceil(b / BIN_S)))
            if b_hi > b_lo:
                edges_t = np.arange(b_lo, b_hi + 1) * BIN_S
                edges_t = np.clip(edges_t, a, b)
                e = np.clip(np.ceil((edges_t - got_t0) * got_fs - 1e-9),
                            0, x.size).astype(np.int64)
                mua_sum[b_lo:b_hi] += c[e[1:]] - c[e[:-1]]
                mua_n[b_lo:b_hi] += e[1:] - e[:-1]
            if on_chunk is not None:
                on_chunk(b - a)
            a = b
    with np.errstate(invalid="ignore", divide="ignore"):
        mua = (mua_sum / np.maximum(mua_n, 1))[:nb]
    mua[mua_n[:nb] < 0.5 * BIN_S * plan["fs"]] = np.nan
    return lfp, mua.astype(np.float32)


def _bin_features(lfp, plan):
    """Per bin: band powers, theta coefficients, rms, 4-12 Hz spectrum."""
    lfs, nper = plan["lfp_fs"], plan["nper"]
    starts = plan["bin_starts"]
    nb = starts.size
    win = np.hanning(nper).astype(np.float32)
    wsum2 = float(np.sum(win.astype(np.float64) ** 2))
    freqs = _fft.rfftfreq(nper, 1.0 / lfs)
    df = freqs[1] - freqs[0]

    power = np.full((nb, len(BANDS)), np.nan, dtype=np.float32)
    tsel = (freqs >= THETA_BAND[0] - 1e-9) & (freqs <= THETA_BAND[1] + 1e-9)
    theta_x = np.zeros((nb, int(tsel.sum())), dtype=np.complex64)
    rms = np.full(nb, np.nan, dtype=np.float32)
    valid = np.zeros(nb, dtype=bool)

    block = 256
    ar = np.arange(nper)
    for i0 in range(0, nb, block):
        i1 = min(nb, i0 + block)
        fr = lfp[starts[i0:i1, None] + ar[None, :]]
        good = np.isfinite(fr).all(axis=1)
        fr = np.nan_to_num(fr, nan=0.0)
        fr = fr - fr.mean(axis=1, keepdims=True)
        rms[i0:i1] = np.sqrt(np.mean(fr * fr, axis=1))
        F = _fft.rfft(fr * win[None, :], axis=1)
        psd = (np.abs(F) ** 2) * (2.0 / (lfs * wsum2))
        for j, (_name, lo, hi) in enumerate(BANDS):
            sel = (freqs >= lo - 1e-9) & (freqs <= hi + 1e-9)
            power[i0:i1, j] = psd[:, sel].sum(axis=1) * df
        theta_x[i0:i1] = (F[:, tsel] / float(win.sum())).astype(np.complex64)
        valid[i0:i1] = good
    power[~valid] = np.nan
    rms[~valid] = np.nan
    theta_x[~valid] = 0

    # The 4-12 Hz spectrum: a 4 s window centred on each bin, for the
    # spectrogram under the Theta Walk strip and for "which frequency won",
    # which is what the probe-agreement measure compares across channels.
    n4 = int(round(SPEC_WIN_S * lfs))
    f4 = _fft.rfftfreq(n4, 1.0 / lfs)
    ssel = (f4 >= SPEC_LO - 1e-9) & (f4 <= SPEC_HI + 1e-9)
    dsel = (f4 >= DOM_LO - 1e-9) & (f4 <= DOM_HI + 1e-9)
    spec = np.full((nb, int(ssel.sum())), np.nan, dtype=np.float16)
    dom = np.full(nb, np.nan, dtype=np.float32)
    w4 = np.hanning(n4).astype(np.float32)
    w4sum2 = float(np.sum(w4.astype(np.float64) ** 2))
    centres = starts + nper // 2
    s4 = np.clip(centres - n4 // 2, 0, max(0, lfp.size - n4))
    ar4 = np.arange(n4)
    block = 96
    for i0 in range(0, nb, block):
        i1 = min(nb, i0 + block)
        fr = lfp[s4[i0:i1, None] + ar4[None, :]]
        good = np.isfinite(fr).all(axis=1)
        fr = np.nan_to_num(fr, nan=0.0)
        fr = fr - fr.mean(axis=1, keepdims=True)
        F = _fft.rfft(fr * w4[None, :], axis=1)
        psd = (np.abs(F) ** 2) * (2.0 / (lfs * w4sum2))
        with np.errstate(divide="ignore"):
            spec[i0:i1] = np.log10(np.maximum(psd[:, ssel], 1e-12)).astype(
                np.float16)
        d = f4[dsel][np.argmax(psd[:, dsel], axis=1)]
        dom[i0:i1] = np.where(good, d, np.nan)
        spec[i0:i1][~good] = np.nan
    return {
        "power": power, "theta_x": theta_x, "rms": rms, "valid": valid,
        "spec": spec, "dom": dom,
        "theta_freqs": freqs[tsel].astype(np.float32),
        "spec_freqs": f4[ssel].astype(np.float32),
    }


def scan(session, report, gid, job=None, workers=4, channels=None,
         on_progress=None):
    """Read every channel once and keep what the steps need.

    Channels go through a small pool. Reading is disk-bound and the filters
    and FFTs drop the GIL for most of their time, so four at once is about
    three times one -- measured, see the module tests.
    """
    plan = plan_for(session, report, channels)
    if not plan["channels"]:
        raise StrataError("No channels to read.")
    if plan["n_bins"] < 10:
        raise StrataError("This recording is shorter than ten seconds; "
                          "there is nothing to average.")
    d = _dir(gid)
    tmp = d + ".part"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    _make_room(plan["lfp_bytes"], keep=gid)

    n_ch = plan["n_channels"]
    lfp_mm = np.lib.format.open_memmap(
        os.path.join(tmp, "lfp.npy"), mode="w+", dtype=np.int16,
        shape=(n_ch, plan["n_samp"]))
    scale = np.zeros(n_ch, dtype=np.float32)
    lfp_valid = np.zeros(plan["n_samp"], dtype=bool)
    nb = plan["n_bins"]
    out = {
        "power": np.full((n_ch, nb, len(BANDS)), np.nan, np.float32),
        "theta_x": np.zeros((n_ch, nb, 0), np.complex64),
        "rms": np.full((n_ch, nb), np.nan, np.float32),
        "mua": np.full((n_ch, nb), np.nan, np.float32),
        "valid": np.zeros((n_ch, nb), bool),
        "spec": None, "dom": np.full((n_ch, nb), np.nan, np.float32),
    }
    done = [0]
    lock = threading.Lock()
    span = max(plan["span_s"], 1e-6)
    seconds = [0.0]

    def chunk_read(sec):
        with lock:
            seconds[0] += sec
            if on_progress is not None:
                on_progress(seconds[0] / span, done[0], n_ch)

    def one(i, ch):
        lfp, mua = _scan_channel(session, ch, plan, job, chunk_read)
        feats = _bin_features(lfp, plan)
        fin = np.isfinite(lfp)
        peak = float(np.nanmax(np.abs(lfp))) if fin.any() else 0.0
        sc = peak / 32000.0 if peak > 0 else 1.0
        lfp_mm[i] = np.rint(np.nan_to_num(lfp, nan=0.0) / sc).astype(np.int16)
        with lock:
            scale[i] = sc
            if i == 0:
                lfp_valid[:] = fin
            else:
                lfp_valid[:] &= fin
            out["power"][i] = feats["power"]
            if out["theta_x"].shape[2] == 0:
                out["theta_x"] = np.zeros(
                    (n_ch, nb, feats["theta_x"].shape[1]), np.complex64)
                out["spec"] = np.full(
                    (n_ch, nb, feats["spec"].shape[1]), np.nan, np.float16)
                out["theta_freqs"] = feats["theta_freqs"]
                out["spec_freqs"] = feats["spec_freqs"]
            out["theta_x"][i] = feats["theta_x"]
            out["spec"][i] = feats["spec"]
            out["dom"][i] = feats["dom"]
            out["rms"][i] = feats["rms"]
            out["mua"][i] = mua
            out["valid"][i] = feats["valid"]
            done[0] += 1
            if job is not None:
                job.tick("strata read", done[0])

    if job is not None:
        job.begin("strata read", of=n_ch)
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futs = [pool.submit(one, i, ch)
                for i, ch in enumerate(plan["channels"])]
        for f in futs:
            f.result()
    lfp_mm.flush()
    del lfp_mm

    meta = {
        "schema": SCHEMA,
        "gid": gid,
        "stamp": source_stamp(session),
        "path": session.get("path"),
        "fs": plan["fs"], "lfp_fs": plan["lfp_fs"], "q": plan["q"],
        "bin_s": BIN_S, "n_bins": nb, "n_samp": plan["n_samp"],
        "end_s": plan["end_s"], "span_s": plan["span_s"],
        "segments": plan["segments"],
        "channels": [int(c["number"]) for c in plan["channels"]],
        "labels": [c.get("label") for c in plan["channels"]],
        "bands": [list(b) for b in BANDS],
        "invert": bool(session.get("invert", True)),
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seconds": None,
    }
    bin_valid = out["valid"].all(axis=0)
    np.savez(os.path.join(tmp, "bins.npz"),
             power=out["power"], theta_x=out["theta_x"], rms=out["rms"],
             mua=out["mua"], valid=bin_valid, spec=out["spec"],
             dom=out["dom"], theta_freqs=out["theta_freqs"],
             spec_freqs=out["spec_freqs"],
             bin_t=(plan["bin_starts"] / plan["lfp_fs"]).astype(np.float64),
             lfp_scale=scale, lfp_valid=np.packbits(lfp_valid))
    with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)

    with _LOCK:
        _BINS.pop(gid, None)
        if gid in _BINS_ORDER:
            _BINS_ORDER.remove(gid)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        os.replace(tmp, d)
    return meta


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------
def _lfp_dirs():
    if not DIR or not os.path.isdir(DIR):
        return []
    out = []
    for name in os.listdir(DIR):
        p = os.path.join(DIR, name, "lfp.npy")
        if os.path.exists(p):
            st = os.stat(p)
            out.append((st.st_atime, st.st_size, p))
    return sorted(out)


def _make_room(need, keep=None):
    """Drop the least recently used 1250 Hz copies until `need` fits.

    Only the big file goes. The bins stay, so a recording whose copy was
    dropped still opens instantly; only ripples, the triggered averages and
    ICA have to read it again.
    """
    have = _lfp_dirs()
    total = sum(s for _a, s, _p in have)
    keep_dir = _dir(keep) if keep else None
    for _a, size, p in have:
        if total + need <= LFP_KEEP_BYTES:
            break
        if keep_dir and os.path.dirname(p) == keep_dir:
            continue
        try:
            os.remove(p)
            total -= size
        except OSError:
            pass


class Bins:
    """One recording's scan, loaded."""

    def __init__(self, gid, meta, arrays, folder):
        self.gid = gid
        self.meta = meta
        self.folder = folder
        self.power = arrays["power"]
        self.theta_x = arrays["theta_x"]
        self.rms = arrays["rms"]
        self.mua = arrays["mua"]
        self.valid = arrays["valid"]
        self.spec = arrays["spec"]
        self.dom = arrays["dom"]
        self.theta_freqs = arrays["theta_freqs"]
        self.spec_freqs = arrays["spec_freqs"]
        self.bin_t = arrays["bin_t"]
        self.lfp_scale = arrays["lfp_scale"]
        self._lfp_valid_packed = arrays["lfp_valid"]
        self.channels = [int(c) for c in meta["channels"]]
        self.row = {c: i for i, c in enumerate(self.channels)}

    @property
    def n_bins(self):
        return int(self.bin_t.size)

    def lfp(self):
        """The 1250 Hz copy, memory-mapped, or None if it was dropped."""
        p = os.path.join(self.folder, "lfp.npy")
        if not os.path.exists(p):
            return None
        try:
            os.utime(p, None)           # recently used, for _make_room
        except OSError:
            pass
        return np.load(p, mmap_mode="r")

    def lfp_valid(self):
        n = int(self.meta["n_samp"])
        return np.unpackbits(self._lfp_valid_packed)[:n].astype(bool)

    def lfp_rows(self, rows, i0=None, i1=None):
        """Some channels of the copy, in microvolts, float32."""
        mm = self.lfp()
        if mm is None:
            raise StrataError(
                "This recording's 1250 Hz copy was cleared to make room. "
                "Read it again (Rescan) to detect ripples, average or run "
                "ICA.")
        sl = slice(i0, i1)
        out = np.asarray(mm[rows, sl], dtype=np.float32)
        out *= self.lfp_scale[rows][:, None]
        return out


def status(gid, session=None):
    """Whether a scan exists for this recording, and whether it is current."""
    d = _dir(gid)
    mp = os.path.join(d, "meta.json")
    if not os.path.exists(mp):
        return {"scanned": False}
    try:
        with open(mp, encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        return {"scanned": False, "broken": True}
    out = {
        "scanned": True,
        "at": meta.get("scanned_at"),
        "channels": meta.get("channels"),
        "n_bins": meta.get("n_bins"),
        "lfp": os.path.exists(os.path.join(d, "lfp.npy")),
        "schema": meta.get("schema"),
    }
    if session is not None:
        out["current"] = (meta.get("stamp") == source_stamp(session)
                          and meta.get("schema") == SCHEMA)
    return out


def load(gid):
    with _LOCK:
        hit = _BINS.get(gid)
        if hit is not None:
            _BINS_ORDER.remove(gid)
            _BINS_ORDER.append(gid)
            return hit
    d = _dir(gid)
    mp = os.path.join(d, "meta.json")
    if not os.path.exists(mp):
        raise StrataError("This recording has not been read for StrataScope "
                          "yet.")
    with open(mp, encoding="utf-8") as fh:
        meta = json.load(fh)
    with np.load(os.path.join(d, "bins.npz")) as z:
        arrays = {k: z[k] for k in z.files}
    b = Bins(gid, meta, arrays, d)
    with _LOCK:
        _BINS[gid] = b
        _BINS_ORDER.append(gid)
        while len(_BINS_ORDER) > _BINS_MAX:
            _BINS.pop(_BINS_ORDER.pop(0), None)
    return b


def forget(gid):
    with _LOCK:
        _BINS.pop(gid, None)
        if gid in _BINS_ORDER:
            _BINS_ORDER.remove(gid)


# ==========================================================================
# Which seconds count
# ==========================================================================
STILL_BUFFER_S = 2.0


def _bout_mask(b, bouts, pad=0.0):
    """Bins whose middle falls inside any bout (seconds, [t0, t1))."""
    mid = b.bin_t + BIN_S / 2.0
    m = np.zeros(mid.size, dtype=bool)
    for bout in bouts or []:
        try:
            t0, t1 = float(bout[0]) - pad, float(bout[1]) + pad
        except (TypeError, ValueError, IndexError):
            continue
        if t1 > t0:
            m |= (mid >= t0) & (mid < t1)
    return m


def masks(b, states=None, params=None):
    """Theta Walk, still, and everything, as bin masks.

    Theta Walk is what was painted. Still is everything not painted, less a
    buffer either side of each walk -- the second after the animal stops is
    neither, and averaging it into "still" puts the tail of a theta bout
    into the ripple curve.

    With nothing painted the theta questions are asked of the whole
    recording instead (decided 2026-10-09: a recording with no walking still
    gets theta curves, flagged), so the answer says which happened.
    """
    states = states or {}
    params = params or {}
    walk_bouts = states.get("theta_walk") or []
    buf = float(params.get("still_buffer_s", STILL_BUFFER_S))
    valid = b.valid.copy()
    walk = _bout_mask(b, walk_bouts) & valid
    near = _bout_mask(b, walk_bouts, pad=buf)
    still = valid & ~near
    theta_all = not bool(walk.any())
    if theta_all:
        walk = valid.copy()
    return {
        "walk": walk, "still": still, "all": valid,
        "theta_all_time": theta_all,
        "walk_s": float(walk.sum() * BIN_S) if not theta_all else 0.0,
        "still_s": float(still.sum() * BIN_S),
        "all_s": float(valid.sum() * BIN_S),
    }


def _bouts_from(mask, t, min_s=2.0, merge_s=1.0):
    """Runs of True as [[t0, t1], ...], merged across short gaps."""
    out = []
    i, n = 0, mask.size
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        t0, t1 = float(t[i]), float(t[j - 1] + BIN_S)
        if out and t0 - out[-1][1] <= merge_s:
            out[-1][1] = t1
        else:
            out.append([t0, t1])
        i = j
    return [x for x in out if x[1] - x[0] >= min_s]


def _otsu(v):
    """The threshold that best splits `v` in two. Used on log theta/delta,
    which is bimodal when an animal both walks and sits still."""
    v = v[np.isfinite(v)]
    if v.size < 10:
        return float(np.nanmedian(v)) if v.size else 0.0
    hist, edges = np.histogram(v, bins=64)
    mids = (edges[:-1] + edges[1:]) / 2.0
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * mids) / np.maximum(w0, 1)
    mt = np.sum(hist * mids)
    m1 = (mt - np.cumsum(hist * mids)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(mids[int(np.argmax(between))])


def _good_rows(b, bad):
    bad = {int(x) for x in (bad or [])}
    return [i for i, c in enumerate(b.channels) if c not in bad]


def _lst(a, dp=3):
    return [None if not np.isfinite(x) else float(round(float(x), dp))
            for x in np.asarray(a, dtype=float)]


def guide(b, bad=(), params=None):
    """Everything drawn under the Theta Walk strip.

    The ratio is read on the channel with the most theta, because that is
    where theta is least likely to be noise. "Agreement" is the share of the
    probe whose strongest 5-11 Hz frequency is within half a hertz of the
    probe's median -- Horizon's measure, on the same spectra: theta is one
    rhythm across the whole hippocampus, so when the column agrees the
    rhythm is real, and when one channel has a high ratio and nobody else
    agrees it is that channel's noise.

    The finder's bouts are a ghost. They are never saved: a bout counts when
    somebody paints it.
    """
    from . import horizon
    params = params or {}
    rows = _good_rows(b, bad) or list(range(len(b.channels)))
    v = b.valid
    th = b.power[:, :, BAND_INDEX["theta"]]
    de = b.power[:, :, BAND_INDEX["delta"]]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_th = np.array([np.nanmean(th[r, v]) if v.any() else np.nan
                            for r in rows])
    if not np.isfinite(mean_th).any():
        raise StrataError("No theta was measured on any good channel.")
    r_best = rows[int(np.nanargmax(mean_th))]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.log10(th[r_best] / de[r_best])
    ratio[~v] = np.nan
    # A three-second running median: one second is noisy enough that a
    # single bin of movement artefact punches a hole in a bout.
    sm = ratio.copy()
    if sm.size >= 3:
        stack = np.vstack([np.r_[sm[:1], sm[:-1]], sm, np.r_[sm[1:], sm[-1:]]])
        with np.errstate(all="ignore"):
            sm = np.nanmedian(stack, axis=0)
    agree, med = horizon.agreement(b.dom[rows], tol=float(
        params.get("agree_tol_hz", 0.5)))
    thr = params.get("ratio_threshold")
    thr = _otsu(sm[v]) if thr in (None, "") else float(thr)
    agree_min = float(params.get("agree_min", 0.6))
    with np.errstate(invalid="ignore"):
        hit = (sm > thr) & (agree >= agree_min) & v
    ghost = _bouts_from(hit, b.bin_t,
                        min_s=float(params.get("min_bout_s", 2.0)),
                        merge_s=float(params.get("merge_gap_s", 1.0)))

    spec = b.spec[r_best].astype(np.float32)            # bins x freqs
    img = spec.T[::-1]                                  # high freq on top
    fin = img[np.isfinite(img)]
    clim = (float(np.percentile(fin, 2)), float(np.percentile(fin, 99.5))) \
        if fin.size else (0.0, 1.0)
    from .analysis import _encode_image
    png = _encode_image(img, "viridis", clim)
    return {
        "t": _lst(b.bin_t, 2),
        "bin_s": BIN_S,
        "ratio": _lst(sm),
        "threshold": round(float(thr), 3),
        "agreement": _lst(agree),
        "agree_min": agree_min,
        "peak_hz": _lst(med, 2),
        "ghost": ghost,
        "channel": int(b.channels[r_best]),
        "spec_png": png,
        "spec_hz": [float(b.spec_freqs[0]), float(b.spec_freqs[-1])],
        "valid": [bool(x) for x in v],
        "end_s": float(b.meta.get("end_s") or 0),
    }


# ==========================================================================
# Depth curves
# ==========================================================================
def _order_rows(b, order):
    if not order:
        return list(range(len(b.channels)))
    return [b.row[int(c)] for c in order if int(c) in b.row]


def _mean_over(a, m):
    """Mean over the masked bins, per row; NaN where nothing is left."""
    if not m.any():
        return np.full(a.shape[0], np.nan)
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(a[:, m], axis=1)


def _unwrap_from(phase_deg, i_ref):
    """Unwrap a phase profile outward from the reference row, so the curve
    shows the progressive shift down the probe instead of jumping by 360."""
    p = np.asarray(phase_deg, dtype=float).copy()
    if not (0 <= i_ref < p.size):
        return p
    for step in (1, -1):
        prev = p[i_ref]
        i = i_ref + step
        while 0 <= i < p.size:
            if np.isfinite(p[i]) and np.isfinite(prev):
                p[i] = prev + ((p[i] - prev + 180.0) % 360.0 - 180.0)
                prev = p[i]
            i += step
    return p


def coherence_matrix(b, rows, m):
    """Theta-band cross-spectra over the masked bins: (S, power, coh).

    A sum of products of the per-second Fourier coefficients, which is why
    any reference channel can be asked for without reading anything again.
    """
    X = b.theta_x[rows][:, m, :].reshape(len(rows), -1).astype(np.complex128)
    S = X @ X.conj().T
    P = np.real(np.diag(S))
    with np.errstate(invalid="ignore", divide="ignore"):
        coh = (np.abs(S) ** 2) / np.outer(P, P)
    return S, P, coh


def pick_sp(curves, is_bad):
    """CA1 pyramidal: the ripple maximum, in the part of the probe above the
    theta maximum when there is one below it -- the pyramidal layer is always
    above the fissure, and a deep ripple maximum is volume conduction from
    somewhere else, or noise."""
    rip = np.where(is_bad, np.nan, curves["ripple"])
    if not np.isfinite(rip).any():
        return None
    th = np.where(is_bad, np.nan, curves["theta"])
    if np.isfinite(th).any():
        i_th = int(np.nanargmax(th))
        if i_th >= 3 and np.isfinite(rip[:i_th]).any():
            return int(np.nanargmax(rip[:i_th]))
    return int(np.nanargmax(rip))


def profile(b, mk, order=None, bad=(), ref=None):
    """One value per channel, top to bottom, for every curve on the strip.

    Bad channels keep their row -- the strip sits on the rail's lanes, and a
    missing row would put every curve below it one lane off -- with no value.
    """
    rows = _order_rows(b, order)
    nums = [b.channels[r] for r in rows]
    badset = {int(x) for x in (bad or [])}
    is_bad = np.array([n in badset for n in nums], dtype=bool)
    P = b.power[rows]
    curves = {
        "mua": np.sqrt(_mean_over(b.mua[rows], mk["all"])),
        "ripple": _mean_over(P[:, :, BAND_INDEX["ripple"]], mk["still"]),
        "theta": _mean_over(P[:, :, BAND_INDEX["theta"]], mk["walk"]),
        "slow_gamma": _mean_over(P[:, :, BAND_INDEX["slow_gamma"]],
                                 mk["walk"]),
        "mid_gamma": _mean_over(P[:, :, BAND_INDEX["mid_gamma"]], mk["walk"]),
        "fast_gamma": _mean_over(P[:, :, BAND_INDEX["fast_gamma"]],
                                 mk["walk"]),
        "rms": _mean_over(b.rms[rows], mk["all"]),
    }
    for k in curves:
        curves[k] = np.where(is_bad, np.nan, curves[k])

    S, _Pw, coh = coherence_matrix(b, rows, mk["walk"])
    coh = np.where(is_bad[:, None] | is_bad[None, :], np.nan, coh)
    i_ref = None
    if ref is not None and int(ref) in nums:
        i_ref = nums.index(int(ref))
    if i_ref is None or is_bad[i_ref]:
        i_ref = pick_sp(curves, is_bad)
    phase = np.full(len(rows), np.nan)
    cohref = np.full(len(rows), np.nan)
    if i_ref is not None:
        phase = np.degrees(np.angle(S[:, i_ref]))
        phase = np.where(is_bad, np.nan, phase)
        phase = _unwrap_from(phase, i_ref)
        cohref = np.sqrt(np.clip(coh[:, i_ref], 0, 1))
    curves["theta_phase"] = phase
    curves["theta_coherence"] = cohref
    neigh = np.full(len(rows), np.nan)
    for i in range(len(rows) - 1):
        c = coh[i, i + 1]
        neigh[i] = np.sqrt(c) if np.isfinite(c) else np.nan
    curves["neighbour_coherence"] = neigh
    return {
        "channels": nums,
        "bad": is_bad,
        "curves": curves,
        "coherence": coh,
        "ref_row": i_ref,
        "ref_channel": nums[i_ref] if i_ref is not None else None,
    }


def profile_public(prof):
    return {
        "channels": prof["channels"],
        "bad": [bool(x) for x in prof["bad"]],
        "ref_channel": prof["ref_channel"],
        "curves": {k: _lst(v, 4) for k, v in prof["curves"].items()},
        "coherence": [_lst(r, 3) for r in prof["coherence"]],
    }


# ==========================================================================
# Sample-level work, off the 1250 Hz copy
# ==========================================================================
# Toothy's ripple detector, ported (Toothy-main/ephys.py:935 get_swr_peaks,
# defaults from qparam.py:36-49). The lab already trusts these numbers, and a
# second ripple detector with its own band and thresholds would be a second
# answer to "where are the ripples" with nothing to say which is right.
RIPPLE_DEFAULTS = {
    "lo": 120.0, "hi": 180.0,   # swr_freq
    "height_sd": 5.0,           # swr_height_thr: peak, in SD of the envelope
    "edge_sd": 3.0,             # swr_min_thr: where an event starts and stops
    "dist_ms": 100.0,           # swr_dist_thr: closest two ripples may be
    "min_ms": 25.0,             # swr_min_dur
    "freq_thr": 125.0,          # swr_freq_thr: instantaneous frequency
    "freq_win_ms": 8.0,         # swr_freq_win
    "maxamp_win_ms": 40.0,      # swr_maxamp_win
}


def _sample_mask(b, bin_mask):
    """A bin mask stretched to the 1250 Hz samples, and'ed with validity."""
    lfs = float(b.meta["lfp_fs"])
    n = int(b.meta["n_samp"])
    k_bin = np.minimum((np.arange(n) / lfs / BIN_S).astype(np.int64),
                       bin_mask.size - 1)
    return bin_mask[k_bin] & b.lfp_valid()


def _runs(mask):
    """[start, end) index pairs of the True runs in a boolean array."""
    d = np.diff(np.r_[0, mask.astype(np.int8), 0])
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


def detect_ripples(b, channel, mk, params=None):
    """Ripples on one channel, in still time -- Toothy's detector.

    As `ephys.get_swr_peaks`: 120-180 Hz, third-order Butterworth run both
    ways; the Hilbert envelope's peaks above 5 SD of the envelope, at least
    100 ms apart; each event's extent where the envelope stays above 3 SD,
    at least 25 ms long; the instantaneous frequency over +-8 ms above 125 Hz;
    and the event's time the largest positive cycle within +-40 ms of the
    envelope peak.

    ONE DIFFERENCE, ON PURPOSE. Toothy takes the envelope's SD over the whole
    recording and keeps every peak. Here the SD is taken over still time and
    only peaks in still time are kept: these ripples exist to say where the
    pyramidal layer is, and a threshold set partly by walking -- when
    theta-nested fast gamma fills the same band -- is set by something that
    is not a ripple. The rest is Toothy's, number for number.
    """
    p = dict(RIPPLE_DEFAULTS)
    p.update({k: float(v) for k, v in (params or {}).items()
              if k in RIPPLE_DEFAULTS and v not in (None, "")})
    if int(channel) not in b.row:
        raise StrataError("Channel %s was not read." % channel)
    lfs = float(b.meta["lfp_fs"])
    x = b.lfp_rows([b.row[int(channel)]])[0].astype(np.float64)
    nyq = lfs / 2.0
    sos = _sig.butter(3, [p["lo"] / nyq, min(p["hi"], nyq * 0.95) / nyq],
                      btype="band", output="sos")
    y = _sig.sosfiltfilt(sos, x, padtype="odd")
    hilb = _sig.hilbert(y)
    env = np.abs(hilb).astype(np.float32)
    still = _sample_mask(b, mk["still"])
    still_s = float(still.sum() / lfs)
    if still.sum() < lfs * 10:
        return {"events": [], "params": p, "channel": int(channel),
                "still_s": round(still_s, 1),
                "why": "Less than ten seconds of still time to look in."}
    sd = float(np.std(env[still]))
    height = sd * p["height_sd"]
    edge = sd * p["edge_sd"]
    dist = max(1, int(round(lfs * p["dist_ms"] / 1000.0)))
    fwin = int(round(p["freq_win_ms"] / 1000.0 * lfs))
    awin = int(round(p["maxamp_win_ms"] / 1000.0 * lfs))

    # get_inst_freq: unwrapped phase, cycles per sample, clipped to the band.
    iphase = np.unwrap(np.angle(hilb))
    ifreq = np.clip(np.diff(iphase) / (2.0 * np.pi) * lfs, p["lo"], p["hi"])

    pk = _sig.find_peaks(env, height=height, distance=dist)[0]
    pk = pk[(pk > lfs) & (pk < env.size - lfs)]
    pk = pk[still[pk]]
    if pk.size == 0:
        return {"events": [], "params": p, "channel": int(channel),
                "still_s": round(still_s, 1), "rate_per_min": 0.0,
                "env_sd": round(sd, 3)}
    pfreq = np.array([np.mean(ifreq[i - fwin:i + fwin]) for i in pk])
    env_clip = np.clip(env, edge, env.max())
    durs, _h, starts, stops = _sig.peak_widths(env_clip, peaks=pk,
                                               rel_height=1)
    keep = (durs / lfs > p["min_ms"] / 1000.0) & (pfreq > p["freq_thr"])
    events = []
    for i, d, f, a, e in zip(pk[keep], durs[keep], pfreq[keep],
                             starts[keep], stops[keep]):
        off = int(np.argmax(y[i - awin:i + awin])) - awin
        k = int(i + off)
        events.append({"t": round(k / lfs, 5),
                       "start": round(float(a) / lfs, 5),
                       "end": round(float(e) / lfs, 5),
                       "amp": round(float(env[i]), 2),
                       "peak_sd": round(float(env[i]) / max(sd, 1e-12), 2),
                       "dur_ms": round(float(d) / lfs * 1000.0, 1),
                       "freq": round(float(f), 1)})
    return {
        "events": events, "params": p, "channel": int(channel),
        "still_s": round(still_s, 1),
        "rate_per_min": round(len(events) / max(still_s / 60.0, 1e-9), 2),
        "env_sd": round(sd, 3),
        "detector": "Toothy get_swr_peaks (ephys.py:935), still time only",
    }


def _interp_bad(m, is_bad):
    """Fill bad rows from their neighbours, linearly in depth.

    Interpolated, not blanked: a second spatial derivative loses three rows
    to one blank one, and ICA lets one noisy channel take a whole component.
    """
    m = np.array(m, dtype=np.float64, copy=True)
    good = np.flatnonzero(~is_bad)
    if good.size < 2:
        return m
    for i in np.flatnonzero(is_bad):
        m[i] = [np.interp(i, good, m[good, t]) for t in range(m.shape[1])] \
            if m.ndim == 2 else np.interp(i, good, m[good])
    return m


def _interp_rows(m, is_bad):
    """`_interp_bad` for a (rows x samples) block, vectorised over time."""
    m = np.array(m, dtype=np.float32, copy=True)
    good = np.flatnonzero(~is_bad)
    if good.size < 2 or not is_bad.any():
        return m
    for i in np.flatnonzero(is_bad):
        lo = good[good < i]
        hi = good[good > i]
        if lo.size and hi.size:
            a, c = lo[-1], hi[0]
            w = (i - a) / float(c - a)
            m[i] = (1 - w) * m[a] + w * m[c]
        elif lo.size:
            m[i] = m[lo[-1]]
        else:
            m[i] = m[hi[0]]
    return m


def csd_of(m, spacing_um, smooth=True):
    """The app's CSD (csc.compute_csd: sinks negative), after a light
    three-point spatial smoothing -- the Hamming smoothing the lab's CSD
    scripts use, which keeps a single noisy contact from reading as a
    sink/source pair."""
    a = np.asarray(m, dtype=np.float64)
    if smooth and a.shape[0] >= 3:
        k = np.array([0.23, 0.54, 0.23])
        pad = np.vstack([a[:1], a, a[-1:]])
        a = k[0] * pad[:-2] + k[1] * pad[1:-1] + k[2] * pad[2:]
    return csc.compute_csd(a.astype(np.float32), spacing_um)


def triggered(b, times, order=None, bad=(), spacing_um=20.0, half_ms=100.0,
              max_events=400, seed=0):
    """The average of every channel around a set of times, and its CSD.

    Each event's window has its own mean taken off before averaging: the
    1250 Hz copy keeps each contact's DC offset, and a CSD of offsets that
    differ by contact is a picture of the amplifier, not of the tissue.
    At most `max_events`, drawn evenly at random (seeded), because past a few
    hundred the average does not change and the read does.
    """
    rows = _order_rows(b, order)
    nums = [b.channels[r] for r in rows]
    badset = {int(x) for x in (bad or [])}
    is_bad = np.array([n in badset for n in nums], dtype=bool)
    lfs = float(b.meta["lfp_fs"])
    n = int(b.meta["n_samp"])
    w = int(round(half_ms / 1000.0 * lfs))
    t = np.asarray(sorted(float(x) for x in times), dtype=float)
    k = np.rint(t * lfs).astype(np.int64)
    k = k[(k - w >= 0) & (k + w < n)]
    n_total = int(k.size)
    if n_total == 0:
        raise StrataError("No events to average.")
    if k.size > max_events:
        rng = np.random.default_rng(seed)
        k = np.sort(rng.choice(k, size=max_events, replace=False))
    mm = b.lfp()
    if mm is None:
        raise StrataError(
            "This recording's 1250 Hz copy was cleared to make room. Read it "
            "again (Rescan) to average.")
    idx = k[:, None] + np.arange(-w, w + 1)[None, :]
    avg = np.zeros((len(rows), 2 * w + 1), dtype=np.float64)
    for j, r in enumerate(rows):
        seg = np.asarray(mm[r][idx], dtype=np.float64) * float(b.lfp_scale[r])
        seg -= seg.mean(axis=1, keepdims=True)
        avg[j] = seg.mean(axis=0)
    avg = _interp_rows(avg, is_bad)
    csd = csd_of(avg, spacing_um)
    return {
        "channels": nums,
        "bad": [bool(x) for x in is_bad],
        "t_ms": [round(float(x), 3)
                 for x in np.arange(-w, w + 1) / lfs * 1000.0],
        "lfp": avg, "csd": csd,
        "n": int(k.size), "n_total": n_total,
    }


def triggered_public(tr, dp=2):
    def mat(a):
        return [_lst(r, dp) for r in np.asarray(a, dtype=float)]
    return {
        "channels": tr["channels"], "bad": tr["bad"], "t_ms": tr["t_ms"],
        "lfp": mat(tr["lfp"]), "csd": mat(tr["csd"]),
        "n": tr["n"], "n_total": tr["n_total"],
    }


def theta_troughs(b, channel, mk, max_n=2000):
    """Theta troughs on one channel during Theta Walk.

    Band-passed 6-10 Hz; a trough is a local minimum deeper than half the
    filtered signal's standard deviation, so a cycle with no theta in it
    does not contribute a trough of nothing.
    """
    lfs = float(b.meta["lfp_fs"])
    x = b.lfp_rows([b.row[int(channel)]])[0].astype(np.float64)
    nyq = lfs / 2.0
    sos = _sig.butter(3, [THETA_BAND[0] / nyq, THETA_BAND[1] / nyq],
                      btype="band", output="sos")
    y = _sig.sosfiltfilt(sos, x)
    walk = _sample_mask(b, mk["walk"])
    if walk.sum() < lfs * 5:
        return np.zeros(0)
    sd = float(y[walk].std())
    d = np.diff(y)
    k = np.flatnonzero((d[:-1] < 0) & (d[1:] >= 0)) + 1
    k = k[walk[k] & (y[k] < -0.5 * sd)]
    return k / lfs


# ==========================================================================
# Method B: pathway-specific gamma, by ICA
# ==========================================================================
ICA_DEFAULTS = {"n_components": 10, "max_fit": 300000, "lo": 25.0,
                "hi": 200.0, "max_walk_s": 900.0, "seed": 0}


def _ica_fit(X, n_comp, seed):
    from sklearn.decomposition import FastICA
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ica = FastICA(n_components=n_comp, whiten="unit-variance",
                      random_state=seed, max_iter=2000, tol=1e-4)
        ica.fit(X)
    return ica


def run_ica(b, mk, order=None, bad=(), spacing_um=20.0, ref=None,
            params=None, job=None):
    """Unmix the gamma-band field into its generators (Method B).

    The field at every contact is a weighted sum of a few synaptic
    generators; ICA finds the weights. A component's loading -- one number
    per contact -- says where its generator is, and the CSD of the loading
    says it better (the loading is smeared by volume conduction, the CSD is
    not). Its time course says which frequency it carries.

    Fitted on Theta Walk seconds, 25-200 Hz, so theta does not dominate the
    decomposition, with bad channels interpolated first. Then refitted on
    each half of the walking separately: a component that does not come back
    in both halves is not trusted.
    """
    p = dict(ICA_DEFAULTS)
    p.update({k: v for k, v in (params or {}).items()
              if k in ICA_DEFAULTS and v not in (None, "")})
    n_comp = int(p["n_components"])
    rows = _order_rows(b, order)
    nums = [b.channels[r] for r in rows]
    badset = {int(x) for x in (bad or [])}
    is_bad = np.array([n in badset for n in nums], dtype=bool)
    lfs = float(b.meta["lfp_fs"])
    walk = _sample_mask(b, mk["walk"])
    idx = np.flatnonzero(walk)
    if idx.size < lfs * 30:
        raise StrataError("ICA needs at least thirty seconds of Theta Walk; "
                          "this recording has %.0f s." % (idx.size / lfs))
    cap = int(float(p["max_walk_s"]) * lfs)
    if idx.size > cap:
        idx = idx[:cap]
    nyq = lfs / 2.0
    sos = _sig.butter(3, [float(p["lo"]) / nyq,
                          min(float(p["hi"]), nyq * 0.9) / nyq],
                      btype="band", output="sos")
    if job is not None:
        job.begin("strata ica", of=len(rows) + 3)
    X = np.zeros((idx.size, len(rows)), dtype=np.float32)
    for j, r in enumerate(rows):
        x = b.lfp_rows([r])[0].astype(np.float64)
        X[:, j] = _sig.sosfiltfilt(sos, x)[idx]
        if job is not None:
            job.tick("strata ica", j + 1)
    X = _interp_rows(X.T, is_bad).T
    rng = np.random.default_rng(int(p["seed"]))
    n_fit = min(int(p["max_fit"]), X.shape[0])
    fit_idx = np.sort(rng.choice(X.shape[0], size=n_fit, replace=False))
    ica = _ica_fit(X[fit_idx], n_comp, int(p["seed"]))
    if job is not None:
        job.tick("strata ica", len(rows) + 1)
    A = np.array(ica.mixing_, dtype=np.float64)             # rows x comps
    S = ica.transform(X)                                    # samples x comps
    for c in range(A.shape[1]):
        i = int(np.argmax(np.abs(A[:, c])))
        if A[i, c] > 0:
            A[:, c] *= -1
            S[:, c] *= -1
    total = float(np.sum(np.var(X, axis=0)))
    var_exp = np.array([float(np.var(S[:, c]) * np.sum(A[:, c] ** 2))
                        / max(total, 1e-12) for c in range(A.shape[1])])

    # Split halves, by time, so "stable" means the same generator in the
    # first and second half of the walking, not two draws from one mixture.
    half = X.shape[0] // 2
    stab = np.full(A.shape[1], np.nan)
    halves = []
    for lo_i, hi_i in ((0, half), (half, X.shape[0])):
        sub = np.arange(lo_i, hi_i)
        if sub.size > n_fit // 2:
            sub = np.sort(rng.choice(sub, size=n_fit // 2, replace=False))
        try:
            halves.append(np.array(_ica_fit(X[sub], n_comp,
                                            int(p["seed"]) + 1).mixing_))
        except Exception:                               # noqa: BLE001
            halves.append(None)
    if job is not None:
        job.tick("strata ica", len(rows) + 3)
    for c in range(A.shape[1]):
        best = []
        for H in halves:
            if H is None:
                continue
            r = [abs(np.corrcoef(A[:, c], H[:, k])[0, 1])
                 for k in range(H.shape[1])]
            best.append(max(r) if r else np.nan)
        if best:
            stab[c] = min(best)

    # The theta reference for phase preference: the pyramidal layer unless
    # the caller said otherwise, as for the phase curve.
    th_phase = None
    if ref is not None and int(ref) in b.row:
        x = b.lfp_rows([b.row[int(ref)]])[0].astype(np.float64)
        s_th = _sig.butter(3, [THETA_BAND[0] / nyq, THETA_BAND[1] / nyq],
                           btype="band", output="sos")
        th_phase = np.angle(_sig.hilbert(_sig.sosfiltfilt(s_th, x)))[idx]

    comps = []
    for c in range(A.shape[1]):
        load = A[:, c]
        load_i = _interp_bad(load, is_bad)
        csd = csd_of(load_i[:, None], spacing_um)[:, 0]
        fin = np.isfinite(csd)
        sink = int(np.nanargmin(csd)) if fin.any() else None
        f, pxx = _sig.welch(S[:, c], fs=lfs, nperseg=1024)
        band = (f >= 20) & (f <= 200)
        peak = float(f[band][np.argmax((f * pxx)[band])]) if band.any() \
            else float("nan")
        pref, mvl = None, None
        if th_phase is not None and np.isfinite(peak):
            lo = max(20.0, peak * 0.7)
            hi = min(nyq * 0.9, peak * 1.3)
            s_g = _sig.butter(3, [lo / nyq, hi / nyq], btype="band",
                              output="sos")
            env = np.abs(_sig.hilbert(_sig.sosfiltfilt(s_g, S[:, c])))
            z = np.sum(env * np.exp(1j * th_phase))
            pref = float(np.degrees(np.angle(z)))
            mvl = float(np.abs(z) / max(np.sum(env), 1e-12))
        comps.append({
            "index": c,
            "loading": _lst(load, 5),
            "csd": _lst(csd, 5),
            "sink_row": sink,
            "sink_channel": nums[sink] if sink is not None else None,
            "sink_value": float(csd[sink]) if sink is not None else None,
            "peak_hz": round(peak, 1) if np.isfinite(peak) else None,
            "kind": ("slow" if np.isfinite(peak) and peak < 60
                     else "fast" if np.isfinite(peak) else None),
            "theta_phase_deg": None if pref is None else round(pref, 1),
            "theta_mvl": None if mvl is None else round(mvl, 4),
            "variance": round(float(var_exp[c]), 5),
            "stability": None if not np.isfinite(stab[c])
            else round(float(stab[c]), 3),
            "psd_f": _lst(f[band][::2], 1),
            "psd": _lst((f * pxx)[band][::2], 6),
        })
    comps.sort(key=lambda x: -x["variance"])
    return {
        "channels": nums, "bad": [bool(x) for x in is_bad],
        "components": comps, "params": p,
        "walk_s": round(idx.size / lfs, 1),
        "theta_all_time": bool(mk.get("theta_all_time")),
        "ref_channel": int(ref) if ref is not None else None,
    }


def ica_zone_sinks(comp, lo_row, hi_row, min_frac=0.3):
    """The component's deepest sink inside rows [lo_row, hi_row), if it is at
    least `min_frac` of the component's main sink -- a weak local dip in a
    zone is not that generator living there."""
    csd = np.array([np.nan if v is None else v for v in comp["csd"]])
    if hi_row <= lo_row or not np.isfinite(csd).any():
        return None
    main = np.nanmin(csd)
    seg = csd[lo_row:hi_row]
    if not np.isfinite(seg).any():
        return None
    i = int(np.nanargmin(seg))
    if main >= 0 or seg[i] > min_frac * main:
        return None
    return lo_row + i
