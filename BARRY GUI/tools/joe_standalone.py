"""
joe_standalone.py -- Joe's tab 8 numbers, from the recordings, with nothing
from Jarvis.

    python joe_standalone.py --inputs joe_inputs.json --out <folder>

Needs only Python 3, numpy and scipy. It reads the Neuralynx recordings
itself (.ncs channels, Events.nev), finds the cue pairs in the TTLs, decides
which wires are clipped, picks each region's wire, cuts every window,
filters, computes coherence two ways and writes one wide .csv per model,
band and method -- the same files tab 8 exports for SPSS, so the two can be
compared cell by cell.

What it takes from `joe_inputs.json` is only what is a DECISION rather than
data: which recordings, which trials were kept (a person curated them),
which wires are marked bad and which regions histology rules out, what each
rat heard where (the lab's identity sheet), the channel map and the seed
for the FP snippets. Everything else it works out here.

Written to be read. Every step says where its rule comes from.

THE STEPS, FOR EVERY RAT AND PRECON DAY

 1. The recording's clock: the first record of its lowest-numbered CSC
    file. Every time below is seconds from there.
 2. The cue pairs, from Events.nev: TTL records (event id 11), mirrors
    (the same code + 1) and repeats of one code on one port inside 150 ms
    dropped; two DIFFERENT cue pulses 10 +/- 0.25 s apart on one port are a
    pair. The end of cue 2 is cue 2's start plus the gap between the two
    cues -- how every analysis in the lab cuts it (the Event Bank stores the
    two cue times only, and the end is derived where it is used). Each trial
    in the inputs is matched to the pair whose cue 1 is within 0.05 s.
 3. Clipping, per wire and window: a sample within 0.5% of the header's
    ADMaxValue, or at the window's own extreme value (if that is at least a
    fifth of the rail), for 16 or more samples in a row. The 10 s baseline
    and the two cues are judged as Spark judges them (whole records; lost at
    0.5% of the window or one 50 ms run); the 20 s baseline and the FP
    snippets are cut to the sample and lost at 50 ms in total.
 4. Each region's wire, per window: the lowest-numbered of its channels not
    marked bad, not clipped in that window, not dropped by hand, and
    readable there. A region with none left is not measured.
 5. Each window, in microvolts (the counts x ADBitVolts, sign inverted as
    the lab's loaders do), decimated to 1000 Hz (Chebyshev, forwards and
    backwards, in steps of at most 8).
 6. Coherence, two ways:
      welch    60 Hz and every harmonic below 490 Hz notched (iirnotch,
               Q = f0 / 2, forwards and backwards); 1000-sample segments,
               each with its mean removed, MATLAB's hanning(1000), half
               overlapping, the FFT 2000 long; |Sxy|^2 / (Sxx Syy).
      dickson  a 59-61 Hz Butterworth band-stop of order 2, forwards and
               backwards (Jeremy's designfilt); 1024-sample segments,
               hanning(1024), 512 overlap, FFT 2048 -- mscohere as in
               Conor_CohandVcorr.m.
    each averaged over the band's bins: theta 5-12 Hz, gamma 30-90 Hz
    without 59-61 Hz.
 7. The FP snippets: random, seeded, from the day's FP1 and FP2 together,
    10 s from either end, never overlapping one another; as many as the day
    has trials; 10 s and 20 s long.
 8. Each rat-day's value at each level of each model: the mean over the
    trials (or snippets) that level takes.
 9. A pair goes into a model when at least four rats have it at every level
    on both Precon1 and Precon4. One row per rat; 999 where it is missing.
"""
import argparse
import json
import math
import os
import re
import sys
from fractions import Fraction

import numpy as np
from scipy.signal import butter, decimate, filtfilt, iirnotch, resample_poly

FS = 1000.0
HEADER = 16 * 1024
RECORD = np.dtype([("timestamp", "<u8"), ("channel", "<u4"), ("freq", "<u4"), ("nvalid", "<u4"),
                   ("samples", "<i2", (512,))])
SPR = 512
NEV = np.dtype([("stx", "<i2"), ("pkt_id", "<i2"), ("pkt_data_size", "<i2"), ("timestamp", "<u8"),
                ("event_id", "<i2"), ("ttl", "<i2"), ("crc", "<i2"), ("dummy1", "<i2"), ("dummy2", "<i2"),
                ("extra", "<i4", (8,)), ("event_string", "S128")])
CSC_NAME = re.compile(r"^CSC(\d+)(?:_(\d+))?\.ncs$", re.IGNORECASE)

# The TTL codes this rig sends (spark.py), and their mirrors.
CODES = {126: "Session", 124: "Click", 122: "Noise", 118: "High tone", 110: "Low Tone", 94: "Pellet Delivery",
         62: "Mag Poke"}
MIRRORS = {111: 110, 119: 118, 123: 122, 125: 124, 127: 126, 63: 62, 95: 94}
CUES = ("Click", "Noise", "High tone", "Low Tone")
DEBOUNCE_MS = 150.0
GAP_S, GAP_TOL_S = 10.0, 0.25

CLIP_FRACTION, CLIP_MIN_RUN = 0.995, 16
LOST_FRAC, LOST_MS = 0.005, 50.0

WINDOWS = ("base20", "base10", "cue1", "cue2", "pair", "swa", "swb")
DAYS = ("Precon1", "Precon2", "Precon3", "Precon4")
TESTED = ("Precon1", "Precon4")
MISSING = 999

# The models: (id, levels, unit), as in tab 8.
MODELS = (
    ("m1", ("base", "cue"), "pair"), ("m2", ("base", "cue1"), "pair"), ("m3", ("base", "cue2"), "pair"),
    ("m4", ("swa", "swb"), "pair"), ("m5", ("cue1", "cue2"), "pair"), ("m6a", ("trials", "fp"), "pair"),
    ("m6b", ("trials", "fp"), "pair"), ("m7", ("base", "cue"), "region"),
    ("c1", ("Noise", "Click"), "pair"), ("c2", ("Click", "Noise", "High", "Low"), "pair"),
    ("c3", ("A", "B", "C", "D"), "pair"), ("c4", ("High", "Low"), "pair"),
)
SOUND_OF_LABEL = {"Click": "Click", "Noise": "Noise", "High tone": "High", "Low Tone": "Low"}
TYPE_SOUNDS = {"Click": "Click", "Noise": "Noise", "HighTone": "High", "LowTone": "Low"}


def say(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- reading
def header(path):
    with open(path, "rb") as fh:
        text = fh.read(HEADER).split(b"\x00", 1)[0].decode("latin-1", "replace")
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("-"):
            parts = line[1:].split(None, 1)
            if parts:
                out[parts[0]] = parts[1].strip() if len(parts) > 1 else ""
    return out


def hfloat(h, key):
    for tok in str(h.get(key, "")).replace(",", " ").split():
        try:
            return float(tok)
        except ValueError:
            continue
    return None


def channels(folder):
    """{channel number: path}, the first part of each channel only."""
    found = {}
    for name in os.listdir(folder):
        m = CSC_NAME.match(name)
        if m:
            num, seq = int(m.group(1)), int(m.group(2) or 0)
            if num not in found or seq < found[num][0]:
                found[num] = (seq, os.path.join(folder, name))
    return {k: v[1] for k, v in sorted(found.items())}


def records(path):
    n = max(0, (os.path.getsize(path) - HEADER) // RECORD.itemsize)
    if n <= 0:
        return None
    return np.memmap(path, dtype=RECORD, mode="r", offset=HEADER, shape=(int(n),))


def clock(folder):
    ch = channels(folder)
    if not ch:
        return None
    with open(ch[min(ch)], "rb") as fh:
        fh.seek(HEADER)
        buf = fh.read(RECORD.itemsize)
    if len(buf) < RECORD.itemsize:
        return None
    return float(np.frombuffer(buf, dtype=RECORD, count=1)["timestamp"][0])


def duration(folder):
    ch = channels(folder)
    if not ch:
        return None
    p = ch[min(ch)]
    h = header(p)
    fs = hfloat(h, "SamplingFrequency") or 30000.0
    n = max(0, (os.path.getsize(p) - HEADER) // RECORD.itemsize)
    return n * SPR / fs


# ---------------------------------------------------------------- 2. pairs
def cue_pairs(folder):
    path = os.path.join(folder, "Events.nev")
    if not os.path.isfile(path):
        return []
    n = max(0, (os.path.getsize(path) - HEADER) // NEV.itemsize)
    if n == 0:
        return []
    with open(path, "rb") as fh:
        fh.seek(HEADER)
        recs = np.fromfile(fh, dtype=NEV, count=n)
    origin = clock(folder)
    if origin is None:
        origin = float(recs["timestamp"][0])
    rows = []
    for i in range(len(recs)):
        if int(recs["event_id"][i]) != 11:
            continue
        text = recs["event_string"][i].split(b"\x00", 1)[0].decode("latin-1", "replace").strip()
        ttl = int(recs["ttl"][i])
        m = re.search(r"port\s+(\d+)", text, re.IGNORECASE)
        port = m.group(1) if m else None
        if ttl in CODES:
            label, mirror, known = CODES[ttl], False, True
        elif ttl in MIRRORS and MIRRORS[ttl] in CODES:
            label, mirror, known = CODES[MIRRORS[ttl]], True, True
        else:
            label, mirror, known = None, False, False
        ts = float(recs["timestamp"][i])
        rows.append({"ttl": ttl, "port": port, "us": ts, "t": (ts - origin) / 1e6, "label": label,
                     "mirror": mirror, "known": known})
    by_port = {}
    for r in rows:
        by_port.setdefault(r["port"], []).append(r)
    for rs in by_port.values():
        rs.sort(key=lambda r: r["us"])
        last = {}
        for r in rs:
            prev = last.get(r["ttl"])
            r["bounce"] = prev is not None and (r["us"] - prev) / 1000.0 < DEBOUNCE_MS
            last[r["ttl"]] = r["us"]
    rows.sort(key=lambda r: r["us"])
    usable = [r for r in rows if r["known"] and not r["mirror"] and not r["bounce"]]
    cues = [r for r in usable if r["label"] in CUES]
    pairs = []
    ports = {}
    for r in cues:
        ports.setdefault(r["port"], []).append(r)
    for port, rs in sorted(ports.items(), key=lambda kv: str(kv[0])):
        rs.sort(key=lambda r: r["us"])
        i = 0
        while i < len(rs):
            a = rs[i]
            b = rs[i + 1] if i + 1 < len(rs) else None
            if b is None or abs((b["t"] - a["t"]) - GAP_S) > GAP_TOL_S or b["label"] == a["label"]:
                i += 1
                continue
            o, c = round(a["t"], 6), round(b["t"], 6)
            pairs.append({"opener_t": o, "closer_t": c, "offset_t": c + (c - o),
                          "sounds": (SOUND_OF_LABEL[a["label"]], SOUND_OF_LABEL[b["label"]])})
            i += 2
    pairs.sort(key=lambda p: p["opener_t"])
    return pairs


# ---------------------------------------------------------------- 3. clipping
def runs_at(hit, min_run):
    if not hit.any():
        return 0, 0
    edges = np.flatnonzero(np.diff(np.concatenate(([0], hit.view(np.int8), [0]))))
    starts, ends = edges[0::2], edges[1::2]
    lens = ends - starts
    keep = lens >= min_run
    return (int(lens[keep].sum()) if keep.any() else 0), int(lens.max())


def clip_runs(block, ceiling):
    n1, run1 = runs_at(np.abs(block) >= ceiling, CLIP_MIN_RUN)
    n2, run2 = 0, 0
    spans2 = []
    for extreme in (int(block.max()), int(block.min())):
        if abs(extreme) < ceiling * 0.2:
            continue
        hit = block == extreme
        a, b = runs_at(hit, CLIP_MIN_RUN)
        n2 += a
        run2 = max(run2, b)
        spans2.append(hit)
    if n2 <= n1:
        return n1, max(run1, run2)
    # The union of both tests' runs, each counted once.
    hit = np.abs(block) >= ceiling
    hit1 = np.zeros_like(hit)
    for h in [hit] + spans2:
        e = np.flatnonzero(np.diff(np.concatenate(([0], h.view(np.int8), [0]))))
        for s0, s1 in zip(e[0::2], e[1::2]):
            if s1 - s0 >= CLIP_MIN_RUN:
                hit1[s0:s1] = True
    return int(hit1.sum()), max(run1, run2)


def clipped_state(mm, fs, ceiling, wa, wb):
    """Spark's state windows: whole records from wa // record to
    wb // record + 2, lost at 0.5% or one 50 ms run."""
    per_rec_s = SPR / fs
    n = mm.shape[0]
    i0, i1 = int(max(0, wa // per_rec_s)), int(min(n, wb // per_rec_s + 2))
    if i1 <= i0:
        return False
    block = np.asarray(mm["samples"][i0:i1]).ravel()
    hits, run = clip_runs(block, ceiling)
    if not hits:
        return False
    return hits / float(block.size) >= LOST_FRAC or run * 1000.0 / fs >= LOST_MS


def cut(mm, fs, origin, t0, t1):
    """The raw counts for [t0, t1) s, cut to the sample, or None."""
    per_rec_us = SPR / fs * 1e6
    n_rec = mm.shape[0]
    want = origin + t0 * 1e6
    n_want = int(round((t1 - t0) * fs))
    first, last = float(mm["timestamp"][0]), float(mm["timestamp"][n_rec - 1])
    if n_want <= 0 or want < first or want >= last + per_rec_us:
        return None
    i = max(0, min(n_rec - 1, int((want - first) // per_rec_us)))
    for _ in range(8):
        step = int((want - float(mm["timestamp"][i])) // per_rec_us)
        if step == 0:
            break
        j = max(0, min(n_rec - 1, i + step))
        if j == i:
            break
        i = j
    while i > 0 and float(mm["timestamp"][i]) > want:
        i -= 1
    while i + 1 < n_rec and float(mm["timestamp"][i + 1]) <= want:
        i += 1
    i1 = min(n_rec, i + n_want // SPR + 2)
    ts = np.asarray(mm["timestamp"][i:i1]).astype(np.float64)
    if np.any(np.asarray(mm["nvalid"][i:i1]) != SPR):
        return None
    if ts.size > 1 and float(np.abs(np.diff(ts) - per_rec_us).max()) > per_rec_us * 0.5:
        return None
    block = np.asarray(mm["samples"][i:i1]).ravel()
    s0 = int(round((want - ts[0]) * fs / 1e6))
    if s0 < 0 or s0 + n_want > block.size:
        return None
    return block[s0:s0 + n_want]


def clipped_timed(mm, fs, origin, ceiling, t0, t1):
    """Spark's named windows: cut to the sample, lost at 50 ms at the rail;
    a window that cannot be cut is lost too (not measured is not clean)."""
    per_rec_us = SPR / fs * 1e6
    ts_all = np.asarray(mm["timestamp"]).astype(np.float64)
    want = origin + t0 * 1e6
    n_want = int(round((t1 - t0) * fs))
    r = int(np.searchsorted(ts_all, want, side="right")) - 1
    if r < 0 or want >= ts_all[r] + per_rec_us * 1.5:
        return True
    s0 = int(round((want - ts_all[r]) * fs / 1e6))
    r1 = r + (s0 + n_want - 1) // SPR
    if r1 >= ts_all.size or n_want <= 0:
        return True
    if np.any(np.asarray(mm["nvalid"][r:r1 + 1]) != SPR):
        return True
    if r1 > r and float(np.abs(np.diff(ts_all[r:r1 + 1]) - per_rec_us).max()) > per_rec_us * 0.5:
        return True
    block = np.asarray(mm["samples"][r:r1 + 1]).ravel()[s0:s0 + n_want]
    hits, _run = clip_runs(block, ceiling)
    return hits * 1000.0 / fs >= LOST_MS


# ---------------------------------------------------------------- 5. signals
def to_1000(x, fs):
    if abs(fs - FS) < 1e-9:
        return x
    ratio = fs / FS
    q = int(round(ratio))
    steps = []
    if abs(ratio - q) < 1e-9 and q >= 2:
        left = q
        for f in (8, 7, 5, 4, 3, 2):
            while left > 1 and left % f == 0:
                steps.append(f)
                left //= f
        if left != 1:
            steps = []
    if steps:
        for f in sorted(steps, reverse=True):
            x = decimate(x, f, ftype="iir", zero_phase=True)
        return x
    frac = Fraction(FS / fs).limit_denominator(4096)
    return np.asarray(resample_poly(x, frac.numerator, frac.denominator), dtype=np.float64)


class Recording(object):
    def __init__(self, folder):
        self.folder = folder
        self.files = channels(folder)
        self.origin = clock(folder)
        self.maps = {}

    def chan(self, num):
        if num not in self.maps:
            p = self.files.get(num)
            if p is None:
                self.maps[num] = None
            else:
                h = header(p)
                fs = hfloat(h, "SamplingFrequency") or 30000.0
                adbv = hfloat(h, "ADBitVolts") or 0.00000006103515625
                admax = float(h.get("ADMaxValue") or 32767.0)
                self.maps[num] = (records(p), fs, adbv, admax)
        return self.maps[num]

    def signals(self, regions, chan_map, blocked, windows, lost):
        """{window: [1000 Hz trace or None per region]}: the lowest-numbered
        usable wire of each region (step 4)."""
        out, chose = {}, {}
        every = None
        for w, _a, _b in windows:
            s = set(lost.get(w, ()))
            every = s if every is None else every & s
        for w, t0, t1 in windows:
            row, wires = [], []
            for name in regions:
                if name in blocked:
                    row.append(None)
                    wires.append(-1)
                    continue
                got, wire = None, -1
                for num in sorted(int(c) for c in chan_map.get(name, [])):
                    if num in lost.get(w, ()) or num in (every or ()):
                        continue
                    c = self.chan(num)
                    if c is None or c[0] is None:
                        continue
                    mm, fs, adbv, _admax = c
                    raw = cut(mm, fs, self.origin, t0, t1)
                    if raw is None:
                        continue
                    got = to_1000(-(raw.astype(np.float64) * (adbv * 1e6)), fs)
                    wire = num
                    break
                row.append(got)
                wires.append(wire)
            out[w] = row
            chose[w] = wires
        self.chose = chose
        return out


# ---------------------------------------------------------------- 6. coherence
def hanning(n):
    k = np.arange(1, n + 1)
    return 0.5 * (1.0 - np.cos(2.0 * np.pi * k / (n + 1)))


def notch_all(x, fs=FS):
    y = np.asarray(x, dtype=np.float64)
    k = 1
    while 60.0 * k < (fs / 2.0) * 0.98:
        f0 = 60.0 * k
        b, a = iirnotch(f0, f0 / 2.0, fs=fs)
        y = filtfilt(b, a, y)
        k += 1
    return y


def notch_dickson(x, fs=FS):
    b, a = butter(1, [59.0, 61.0], btype="bandstop", fs=fs)
    return filtfilt(b, a, np.asarray(x, dtype=np.float64))


def band_coherence(X, ok, nseg, demean, bands, skip):
    """Every pair's coherence averaged over each band (P per band), or None."""
    R, N = X.shape
    step = nseg // 2
    K = (N - nseg) // step + 1
    if K < 1:
        return None
    idx = np.arange(K)[:, None] * step + np.arange(nseg)[None, :]
    segs = X[:, idx]
    if demean:
        segs = segs - segs.mean(axis=2, keepdims=True)
    F = np.fft.rfft(segs * hanning(nseg), n=2 * nseg, axis=2)
    Saa = np.mean(np.abs(F) ** 2, axis=1)
    freqs = np.fft.rfftfreq(2 * nseg, 1.0 / FS)
    pr = [(a, b) for a in range(R) for b in range(a + 1, R)]
    out = []
    for lo, hi in bands:
        m = (freqs >= lo - 1e-9) & (freqs <= hi + 1e-9) & ~((freqs >= skip[0] - 1e-9) & (freqs <= skip[1] + 1e-9))
        v = np.full(len(pr), np.nan)
        for p, (a, b) in enumerate(pr):
            if ok[a] and ok[b]:
                sab = np.mean(F[a] * np.conj(F[b]), axis=0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    v[p] = float(np.nanmean(np.abs(sab[m]) ** 2 / (Saa[a][m] * Saa[b][m])))
        out.append(v)
    return out


def band_power(X, ok, bands, skip):
    """log10 Welch power density per region and band (the circuits' Welch)."""
    R, N = X.shape
    nseg = 1000
    step = nseg // 2
    K = (N - nseg) // step + 1
    if K < 1:
        return None
    idx = np.arange(K)[:, None] * step + np.arange(nseg)[None, :]
    segs = X[:, idx]
    segs = segs - segs.mean(axis=2, keepdims=True)
    win = hanning(nseg)
    F = np.fft.rfft(segs * win, n=2 * nseg, axis=2)
    Saa = np.mean(np.abs(F) ** 2, axis=1)
    scale = 2.0 / (FS * np.sum(win * win))
    freqs = np.fft.rfftfreq(2 * nseg, 1.0 / FS)
    out = []
    for lo, hi in bands:
        m = (freqs >= lo - 1e-9) & (freqs <= hi + 1e-9) & ~((freqs >= skip[0] - 1e-9) & (freqs <= skip[1] + 1e-9))
        v = np.full(R, np.nan)
        for r in range(R):
            if ok[r]:
                v[r] = math.log10(float(np.mean(Saa[r][m] * scale)))
        out.append(v)
    return out


def measure(sigs, bands, skip):
    """(coh[band][method] per pair, power[band] per region) for one window."""
    R = len(sigs)
    P = R * (R - 1) // 2
    nan = {"coh": [[np.full(P, np.nan), np.full(P, np.nan)] for _b in bands], "power": [np.full(R, np.nan) for _b in bands]}
    ok = [s is not None and np.asarray(s).size > 0 for s in sigs]
    if not any(ok):
        return nan
    n = min(np.asarray(s).size for s, k in zip(sigs, ok) if k)
    Xa, Xb = np.zeros((R, n)), np.zeros((R, n))
    for r, s in enumerate(sigs):
        if not ok[r]:
            continue
        s = np.asarray(s, dtype=np.float64)[:n]
        if not np.all(np.isfinite(s)) or s.std() <= 0:
            ok[r] = False
            continue
        Xa[r] = notch_all(s)
        Xb[r] = notch_dickson(s)
    a = band_coherence(Xa, ok, 1000, True, bands, skip)
    b = band_coherence(Xb, ok, 1024, False, bands, skip)
    pw = band_power(Xa, ok, bands, skip)
    out = {"coh": [], "power": []}
    for bi in range(len(bands)):
        out["coh"].append([a[bi] if a else np.full(P, np.nan), b[bi] if b else np.full(P, np.nan)])
        out["power"].append(pw[bi] if pw else np.full(R, np.nan))
    return out


# ---------------------------------------------------------------- 7. FP snippets
def fp_random(recs, n, length, seed, edge):
    rng = np.random.default_rng([int(x) for x in seed])
    spans = []
    for key, dur in recs:
        lo, hi = edge, dur - edge - float(length)
        if hi > lo:
            spans.append((key, lo, hi))
    total = sum(hi - lo for _k, lo, hi in spans)
    out = []
    if total <= 0:
        return out
    tries = 0
    while len(out) < int(n) and tries < 200 * int(n):
        tries += 1
        u = float(rng.uniform(0.0, total))
        for key, lo, hi in spans:
            w = hi - lo
            if u <= w:
                t0 = lo + u
                break
            u -= w
        else:
            key, lo, hi = spans[-1]
            t0 = hi
        t1 = t0 + float(length)
        if any(k == key and t0 < b and a < t1 for k, a, b in out):
            continue
        out.append((key, round(t0, 6), round(t1, 6)))
    return out


# ---------------------------------------------------------------- one rat-day
def letters(identity, cue_type):
    """(letters, sounds) of a trial's two cues from the identity sheet."""
    if not identity or not cue_type or "_" not in cue_type:
        return (None, None), (None, None)
    s1, s2 = (TYPE_SOUNDS.get(x) for x in cue_type.split("_", 1))
    for p in ("AB", "CD"):
        if identity.get(p[0]) == s1 and identity.get(p[1]) == s2:
            return (p[0], p[1]), (s1, s2)
    return (None, None), (s1, s2)


def day_values(day, inp):
    regions = inp["regions"]
    chan_map = {k: [int(c) for c in v] for k, v in inp["channels"].items()}
    bands = [(lo, hi) for _n, lo, hi in inp["bands"]]
    skip = tuple(inp["skip_hz"])
    folders = [(r, p) for r, p in day["folders"]]
    spc = dict(folders).get("SPC")
    rec = Recording(spc)
    bad = set(int(c) for c in day["bad"])
    blocked = set(day["blocked"])
    found = cue_pairs(spc)
    W = len(WINDOWS)
    B = len(bands)
    trials = []
    notes = []
    for t in day["trials"]:
        match = [p for p in found if abs(p["opener_t"] - float(t["opener_t"])) <= 0.05]
        if not match:
            notes.append("%s: no cue pair in Events.nev at %.3f s" % (t["id"], t["opener_t"]))
            trials.append(None)
            continue
        p = match[0]
        if max(abs(p["closer_t"] - t["closer_t"]), abs(p["offset_t"] - t["offset_t"])) > 0.01:
            notes.append("%s: this script's boundaries differ from the bank's" % t["id"])
        trials.append((t, p))
    used = sorted({int(c) for nm, cs in chan_map.items() if nm not in blocked for c in cs} - bad)
    coh = np.full((W, len(trials), B, 2, len(regions) * (len(regions) - 1) // 2), np.nan)
    power = np.full((W, len(trials), B, len(regions)), np.nan)
    wires = np.full((W, len(trials), len(regions)), -1, dtype=int)
    lost_all = []
    info = []
    for ti, tp in enumerate(trials):
        if tp is None:
            info.append({"letters": (None, None), "sounds": (None, None)})
            continue
        t, p = tp
        lt, st = letters(inp["identity"].get(str(day["rat"])), t.get("cue_type"))
        info.append({"letters": lt, "sounds": st})
        o, c, f = p["opener_t"], p["closer_t"], p["offset_t"]
        lost = {"pre": set(), "cue1": set(), "cue2": set(), "base20": set()}
        for num in used:
            ch = rec.chan(num)
            if ch is None or ch[0] is None:
                continue
            mm, fs, _adbv, admax = ch
            ceiling = admax * CLIP_FRACTION
            for name, wa, wb in (("pre", o - 10.0, o), ("cue1", o, c), ("cue2", c, f)):
                if clipped_state(mm, fs, ceiling, wa, wb):
                    lost[name].add(num)
            if clipped_timed(mm, fs, rec.origin, ceiling, o - 20.0, o):
                lost["base20"].add(num)
        manual = t.get("manual") or {}
        flat = set(int(x) for x in manual.get("flat") or []) | bad
        def drop(*names):
            s = set(flat)
            for nm in names:
                s |= lost.get(nm, set())
                s |= set(int(x) for x in manual.get(nm) or [])
            return s
        drops = {"base20": drop("pre", "base20"), "base10": drop("pre"), "cue1": drop("cue1"), "cue2": drop("cue2"),
                 "pair": drop("cue1", "cue2"), "swa": drop("cue1"), "swb": drop("cue2")}
        wins = [("base20", o - 20.0, o), ("base10", o - 10.0, o), ("cue1", o, c), ("cue2", c, f), ("pair", o, f),
                ("swa", c - 2.0, c), ("swb", c, c + 2.0)]
        sig = rec.signals(regions, chan_map, blocked, wins, drops)
        lost_all.append({k: sorted(v) for k, v in lost.items()})
        for wi, (w, _a, _b) in enumerate(wins):
            wires[wi, ti] = rec.chose[w]
            m = measure(sig[w], bands, skip)
            for bi in range(B):
                coh[wi, ti, bi, 0] = m["coh"][bi][0]
                coh[wi, ti, bi, 1] = m["coh"][bi][1]
                power[wi, ti, bi] = m["power"][bi]
    # FP snippets.
    fpr = []
    for role, path in folders:
        if role in ("FP1", "FP2") and path and os.path.isdir(path):
            d = duration(path)
            if d:
                fpr.append((role, path, d))
    fp = {}
    n = len(day["trials"])
    for L in inp["fp"]["lengths"]:
        name = "fp%d" % int(L)
        seed = [inp["fp"]["seed"], int(day["rat"]), DAYS.index(day["day"]) + 1, int(round(L))]
        snips = fp_random([(k, d) for k, _p, d in fpr], n, L, seed, inp["fp"]["edge_s"])
        fc = np.full((1, len(snips), B, 2, coh.shape[-1]), np.nan)
        fpw = np.full((1, len(snips), B, len(regions)), np.nan)
        for si, (key, t0, t1) in enumerate(snips):
            path = [p for k, p, _d in fpr if k == key][0]
            r2 = Recording(path)
            lost = set(bad)
            for num in used:
                ch = r2.chan(num)
                if ch is None or ch[0] is None:
                    continue
                mm, fs, _adbv, admax = ch
                if clipped_timed(mm, fs, r2.origin, admax * CLIP_FRACTION, t0, t1):
                    lost.add(num)
            sig = r2.signals(regions, chan_map, blocked, [(name, t0, t1)], {name: lost})
            m = measure(sig[name], bands, skip)
            for bi in range(B):
                fc[0, si, bi, 0] = m["coh"][bi][0]
                fc[0, si, bi, 1] = m["coh"][bi][1]
                fpw[0, si, bi] = m["power"][bi]
        fp[name] = {"coh": fc, "power": fpw}
    return {"coh": coh, "power": power, "wires": wires, "lost": lost_all, "info": info, "fp": fp, "notes": notes,
            "pairs": [tp[1] if tp else None for tp in trials]}


# ---------------------------------------------------------------- 8, 9. the models
def picks(model, level, info):
    wi = {w: i for i, w in enumerate(WINDOWS)}
    out = []
    for ti, t in enumerate(info):
        if model in ("m1", "m7"):
            out.append((wi["base20" if level == "base" else "pair"], ti))
        elif model in ("m2", "m3"):
            out.append((wi["base10" if level == "base" else level], ti))
        elif model in ("m4", "m5"):
            out.append((wi[level], ti))
        elif model == "m6a":
            out.append((wi["pair"], ti))
        elif model == "m6b":
            out += [(wi["cue1"], ti), (wi["cue2"], ti)]
        else:
            got = t["sounds"] if model in ("c1", "c2", "c4") else t["letters"]
            for k, x in enumerate(got):
                if x == level:
                    out.append((wi["cue1" if k == 0 else "cue2"], ti))
    return out


def level_value(dv, model, level, unit, b, m):
    what = "power" if unit == "region" else "coh"
    if level == "fp" and model in ("m6a", "m6b"):
        a = dv["fp"].get("fp20" if model == "m6a" else "fp10")
        X = a[what][0]
        vals = X[:, b, m] if what == "coh" else X[:, b]
    else:
        pk = picks(model, level, dv["info"])
        if not pk:
            return None
        X = dv[what]
        vals = np.stack([X[w, t, b, m] if what == "coh" else X[w, t, b] for w, t in pk])
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(vals, axis=0)


def short(n):
    return n.replace("Left ", "L ").replace("Right ", "R ")


def code(u):
    return short(u).replace(" ", "").replace("-", "").replace("–", "_")


def write_models(values, inp, out):
    regions = inp["regions"]
    pr = [(a, b) for a in range(len(regions)) for b in range(a + 1, len(regions))]
    pair_names = ["%s – %s" % (short(regions[a]), short(regions[b])) for a, b in pr]
    rats = sorted({r for r, _d in values})
    bands = [n for n, _lo, _hi in inp["bands"]]
    for model, levels, unit in MODELS:
        units = pair_names if unit == "pair" else [short(n) for n in regions]
        for bi, band in enumerate(bands):
            for mi, method in enumerate(("welch", "dickson") if unit == "pair" else ("welch",)):
                tab = {}
                for r in rats:
                    tab[r] = {}
                    for d in TESTED:
                        tab[r][d] = {}
                        for lv in levels:
                            dv = values.get((r, d))
                            v = level_value(dv, model, lv, unit, bi, mi) if dv else None
                            tab[r][d][lv] = v if v is not None else np.full(len(units), np.nan)
                keep = [ui for ui in range(len(units))
                        if sum(1 for r in rats if all(np.isfinite(tab[r][d][lv][ui]) for d in TESTED for lv in levels))
                        >= int(inp["min_rats"])]
                if not keep:
                    continue
                cols = []
                for d in TESTED:
                    for lv in levels:
                        for ui in keep:
                            cols.append((d, lv, ui, "%s_%s_%s" % (d.replace("Precon", "D"), lv, code(units[ui]))))
                name = "%s_%s_%s.csv" % (model, band, method)
                with open(os.path.join(out, name), "w", encoding="utf-8", newline="") as fh:
                    fh.write(",".join(["rat"] + [c[3] for c in cols]) + "\n")
                    for r in rats:
                        row = [str(r)]
                        for d, lv, ui, _n in cols:
                            v = tab[r][d][lv][ui]
                            row.append(str(MISSING) if not np.isfinite(v) else "%.10g" % v)
                        fh.write(",".join(row) + "\n")
                say("wrote", name)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="rat:day[,rat:day] for a quick check", default=None)
    a = ap.parse_args()
    inp = json.load(open(a.inputs, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    only = None
    if a.only:
        only = {(int(x.split(":")[0]), x.split(":")[1]) for x in a.only.split(",")}
    values, notes = {}, []
    for day in inp["days"]:
        if day["day"] not in TESTED:
            continue
        if only and (int(day["rat"]), day["day"]) not in only:
            continue
        say("r%d %s ..." % (day["rat"], day["day"]))
        try:
            dv = day_values(day, inp)
        except Exception as exc:                          # noqa: BLE001
            notes.append("r%d %s: %s" % (day["rat"], day["day"], exc))
            continue
        values[(int(day["rat"]), day["day"])] = dv
        notes += ["r%d %s %s" % (day["rat"], day["day"], n) for n in dv["notes"]]
    write_models(values, inp, a.out)
    with open(os.path.join(a.out, "notes.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(notes) + "\n")
    say("done; %d notes (notes.txt)" % len(notes))


if __name__ == "__main__":
    sys.exit(main())
