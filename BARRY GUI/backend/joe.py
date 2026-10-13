"""
joe.py -- tab 8 of the Monolith page: Joe's data, the tests his dissertation
proposal names and nothing more.

The lab decided this on 2026-10-06 ("the middle path"): the Monolith stays
exploratory -- a quarter of a million stat tests, of which none survives a
correction and any one picked and tested again on the same data is circular
-- and Joe's dissertation tests only what Aim 2 of his proposal says. Does
LFP coherence between regions change across preconditioning, in theta
(5-12 Hz) and gamma (30-90 Hz)? Shahriar's answers to the 25 questions of
2026-10-09 fixed the rest (memory: joe-tab8-decisions).

WHAT IS MEASURED. Every trial of every rat on every Precon day, read here
from the recordings (E: is only ever read), on the wire every circuit uses
(`coupling._signals_for_windows`: the lowest-numbered usable wire of each
region, clipped and histology-blocked wires passed over). Seven windows a
trial, from its own measured boundaries:

    base20   the 20 s before cue 1        base10   the 10 s before cue 1
    cue1     cue 1                        cue2     cue 2
    pair     cue 1 + cue 2 (20 s)
    swa      the last 2 s of cue 1        swb      the first 2 s of cue 2

and, for the FP comparison, random snippets of the day's FP1/FP2 recordings
(as many as the day has trials, 10 s and 20 s long, seeded so that they are
the same snippets every time and in the standalone script).

Coherence two ways, both kept:

    welch     the circuits' Welch magnitude-squared coherence: mains and its
              harmonics notched, 1 s Hann segments, 50% overlap, the FFT
              twice the segment (coupling / sweep)
    dickson   Dickson et al. 2022, as Jeremy's MATLAB does it
              (Jeremy Code/Conor_CohandVcorr.m): a 2nd-order Butterworth
              band-stop at 59-61 Hz, then mscohere(x, y, hanning(1024),
              512, 2048, fs)

each averaged over theta (5-12 Hz) and gamma (30-90 Hz, the notch's own
59-61 Hz bins left out). Beside them, for the follow-ups: node power, PLI,
imaginary coherence, Granger both ways, the amplitude cross-correlation lag
(Adhikari 2010, the lab's direction measure) and phase-amplitude coupling
(theta phase in one region, gamma amplitude in another, Tort's MI).

The models, the exports and the work job are below the measures.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time

import numpy as np
from scipy.signal import butter, filtfilt, hilbert

from . import coupling, nlx, ratidentity, spark, sweep

FS = coupling.ANALYSIS_FS
# 3: Spark's timed windows found again after a break in a recording's clock
# (spark._record_at); every day file made before it is made again.
SCHEMA = 3

BANDS = (("theta", 5.0, 12.0), ("gamma", 30.0, 90.0))
BAND_IDS = tuple(b[0] for b in BANDS)
BAND_SAY = {"theta": "Theta 5–12 Hz", "gamma": "Gamma 30–90 Hz"}
#: The notch's own bins: mains is gone from them, and what is left is the
#: notch's shape, not the brain. Out of every band average (only gamma
#: reaches them).
SKIP_HZ = (59.0, 61.0)
METHODS = ("welch", "dickson")
METHOD_SAY = {"welch": "Welch (the circuits')", "dickson": "Dickson 2022 (mscohere)"}
WINDOWS = ("base20", "base10", "cue1", "cue2", "pair", "swa", "swb")
WINDOW_SAY = {"base20": "Baseline, 20 s", "base10": "Baseline, 10 s", "cue1": "Cue 1",
              "cue2": "Cue 2", "pair": "Cue 1 + Cue 2", "swa": "8–10 s (end of cue 1)",
              "swb": "10–12 s (start of cue 2)", "fp10": "FP snippet, 10 s",
              "fp20": "FP snippet, 20 s"}
FP_LENGTHS = (10.0, 20.0)
FP_EDGE_S = 10.0
FP_SEED = 20261009
DAYS = ("Precon1", "Precon2", "Precon3", "Precon4")
TESTED = ("Precon1", "Precon4")
MIN_RATS = 4
#: Follow-up measures kept per band and pair (beside the two coherences).
FOLLOW = ("pli", "icoh", "gc_ab", "gc_ba", "xlag", "xpeak")
XCORR_MAX_MS = 100.0
PAC_BINS = 18
GC_FS = sweep.GC_FS

# The two methods' segments.
WELCH_SEG = 1000
DICKSON_SEG = 1024


class JoeError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
def trial_windows(pair):
    """The seven windows of one trial, from its measured boundaries."""
    o, c, f = float(pair["opener_t"]), float(pair["closer_t"]), float(pair["offset_t"])
    return [("base20", o - 20.0, o), ("base10", o - 10.0, o), ("cue1", o, c), ("cue2", c, f),
            ("pair", o, f), ("swa", c - 2.0, c), ("swb", c, c + 2.0)]


def trial_drop(unit, state_lost=None, base20_lost=(), bad=()):
    """Which wires each window loses. Clipping is measured HERE for every
    trial (`state_lost`: {window: channels} for pre, cue1 and cue2, Spark's
    rule; `base20_lost`: the 20 s baseline, cut to the sample), not read
    from the bank, because the bank has no per-window measurement for 65 of
    the Precon trials -- and so that the standalone script, which measures
    it itself, is measuring the same thing. A window inside a cue loses
    what its cue lost. The hand exclusions and the wires marked bad are
    decisions, and apply everywhere they say."""
    d = state_lost or {}
    manual = unit.get("manual") or {}
    flat = {int(c) for c in (manual.get("flat") or [])} | {int(c) for c in bad}
    def lost(*names):
        out = set(flat)
        for n in names:
            out |= {int(c) for c in (d.get(n) or [])}
            out |= {int(c) for c in (manual.get(n) or [])}
        return out
    return {
        "base20": sorted(lost("pre") | {int(c) for c in base20_lost}),
        "base10": sorted(lost("pre")),
        "cue1": sorted(lost("cue1")),
        "cue2": sorted(lost("cue2")),
        "pair": sorted(lost("cue1", "cue2")),
        "swa": sorted(lost("cue1")),
        "swb": sorted(lost("cue2")),
    }


def fp_random(recordings, n, length, seed, edge=FP_EDGE_S):
    """`n` snippets of `length` s, at random but seeded, from `recordings`
    ([{"key", "duration_s"}] in order). Each recording's usable span is
    [edge, duration - edge]; a start is drawn uniformly over all of the
    usable spans together; a snippet overlapping one already drawn in the
    same recording is drawn again. Returns [(key, t0, t1)] in draw order,
    or fewer when there is no room."""
    rng = np.random.default_rng([int(x) for x in seed])
    spans = []
    for r in recordings:
        dur = float(r.get("duration_s") or 0.0)
        lo, hi = edge, dur - edge - float(length)
        if hi > lo:
            spans.append((r["key"], lo, hi))
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


def fp_seed(rat, day, length):
    """The seed for one rat-day's snippets of one length: the same here and
    in the standalone script."""
    return [FP_SEED, int(rat), DAYS.index(day) + 1, int(round(length))]


# --------------------------------------------------------------------------
# The measures of one window
# --------------------------------------------------------------------------
def pairs_of(n):
    return [(a, b) for a in range(n) for b in range(a + 1, n)]


def band_mask(freqs, lo, hi):
    m = (freqs >= lo - 1e-9) & (freqs <= hi + 1e-9)
    return m & ~((freqs >= SKIP_HZ[0] - 1e-9) & (freqs <= SKIP_HZ[1] + 1e-9))


def dickson_notch(x, fs=FS):
    """Jeremy's notch: designfilt('bandstopiir', 'FilterOrder', 2,
    'HalfPowerFrequency1', 59, 'HalfPowerFrequency2', 61, 'DesignMethod',
    'butter'), run with filtfilt. A second-order band-stop is butter(1)."""
    b, a = butter(1, [SKIP_HZ[0], SKIP_HZ[1]], btype="bandstop", fs=float(fs))
    return filtfilt(b, a, np.asarray(x, dtype=np.float64))


def spectra(X, nseg, step, nfft, demean, fs=FS):
    """Welch auto- and cross-spectra of the rows of X over all pairs:
    (freqs, Saa (R, f), Sab (P, f), scale) or None when X is shorter than
    one segment."""
    R = X.shape[0]
    segs = sweep._segments(X, nseg, step)
    if segs is None:
        return None
    if demean:
        segs = segs - segs.mean(axis=2, keepdims=True)
    win = coupling.matlab_hanning(int(nseg))
    F = np.fft.rfft(segs * win, n=int(nfft), axis=2)
    Saa = np.mean(np.abs(F) ** 2, axis=1)
    pr = pairs_of(R)
    ia = np.array([a for a, _b in pr], dtype=int)
    ib = np.array([b for _a, b in pr], dtype=int)
    Sab = np.mean(F[ia] * np.conj(F[ib]), axis=1)
    freqs = np.fft.rfftfreq(int(nfft), 1.0 / fs)
    scale = 2.0 / (fs * np.sum(win * win))
    return freqs, Saa, Sab, scale


def xcorr_lags(E, ia, ib, fs, max_ms=XCORR_MAX_MS):
    """Adhikari's amplitude cross-correlation for every pair at once: each
    region's envelope, mean removed, correlated with the other's over
    +/- max_ms, normalised as MATLAB's xcorr(a, b, L, 'coeff'). Returns
    (lag in ms, peak r) arrays, one per pair. R(m) = sum a(n + m) b(n), so a
    NEGATIVE lag means the first region's envelope comes first: the first
    region leads. Through the FFT, zero-padded past twice the length, so the
    correlation is linear, not circular."""
    A = E - E.mean(axis=1, keepdims=True)
    n = A.shape[1]
    L = int(round(max_ms * fs / 1000.0))
    nfft = 1 << int(math.ceil(math.log2(2 * n)))
    F = np.fft.rfft(A, n=nfft, axis=1)
    cc = np.fft.irfft(F[ia] * np.conj(F[ib]), n=nfft, axis=1)
    # lag m >= 0 at index m; lag m < 0 at index nfft + m
    seg = np.concatenate([cc[:, nfft - L:], cc[:, :L + 1]], axis=1)
    en = np.sum(A * A, axis=1)
    den = np.sqrt(en[ia] * en[ib])
    with np.errstate(invalid="ignore", divide="ignore"):
        seg = seg / den[:, None]
    k = np.argmax(seg, axis=1)
    lag = (k - L) * 1000.0 / fs
    peak = seg[np.arange(seg.shape[0]), k]
    bad = ~(den > 0)
    lag = lag.astype(np.float64)
    lag[bad] = np.nan
    peak[bad] = np.nan
    return lag, peak


def _pac(phase, amp):
    edges = np.linspace(-np.pi, np.pi, PAC_BINS + 1)
    idx = np.clip(np.digitize(phase, edges) - 1, 0, PAC_BINS - 1)
    counts = np.bincount(idx, minlength=PAC_BINS).astype(float)
    sums = np.bincount(idx, weights=amp, minlength=PAC_BINS)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = sums / counts
        p = mean / np.nansum(mean)
        h = -np.nansum(np.where(p > 0, p * np.log(p), 0.0))
    return (math.log(PAC_BINS) - h) / math.log(PAC_BINS)


def measure(sigs, fs=FS, follow=True):
    """See `_measure`: the same, with numpy's warnings about pairs that are
    all NaN kept quiet (a region nobody has is NaN by design)."""
    import warnings
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        return _measure(sigs, fs, follow)


def _measure(sigs, fs=FS, follow=True):
    """Everything tab 8 asks of one window. `sigs` is a list, one per region,
    of the window's trace at `fs` (or None). Returns a dict of float64
    arrays, NaN where a region or pair was not measured:

        coh    (B, M, P)   coherence, per band and method
        power  (B, R)      log10 Welch power density over the band
        pli, icoh, gc_ab, gc_ba, xlag, xpeak   (B, P)   follow-up measures
        pac    (R, R)      theta phase of the row region, gamma amplitude of
                           the column region (Tort's MI)
    """
    R = len(sigs)
    pr = pairs_of(R)
    P = len(pr)
    B = len(BANDS)
    out = {"coh": np.full((B, len(METHODS), P), np.nan), "power": np.full((B, R), np.nan)}
    for k in FOLLOW:
        out[k] = np.full((B, P), np.nan)
    out["pac"] = np.full((R, R), np.nan)
    ok = [s is not None and np.asarray(s).size > 0 for s in sigs]
    if not any(ok):
        return out
    n = min(np.asarray(s).size for s, k in zip(sigs, ok) if k)
    Xa = np.zeros((R, n))
    Xb = np.zeros((R, n))
    for r, s in enumerate(sigs):
        if not ok[r]:
            continue
        s = np.asarray(s, dtype=np.float64)[:n]
        if not np.all(np.isfinite(s)) or s.std() <= 0:
            ok[r] = False
            continue
        Xa[r] = coupling.notch(s, fs)[0]
        Xb[r] = dickson_notch(s, fs)
    okv = np.array(ok)
    ia = np.array([a for a, _b in pr], dtype=int)
    ib = np.array([b for _a, b in pr], dtype=int)
    pair_ok = okv[ia] & okv[ib]

    wa = spectra(Xa, WELCH_SEG, WELCH_SEG // 2, 2 * WELCH_SEG, True, fs)
    wb = spectra(Xb, DICKSON_SEG, DICKSON_SEG // 2, 2 * DICKSON_SEG, False, fs)
    for bi, (_bid, lo, hi) in enumerate(BANDS):
        for mi, sp in enumerate((wa, wb)):
            if sp is None:
                continue
            freqs, Saa, Sab, scale = sp
            m = band_mask(freqs, lo, hi)
            with np.errstate(invalid="ignore", divide="ignore"):
                coh = np.abs(Sab[:, m]) ** 2 / (Saa[ia][:, m] * Saa[ib][:, m])
            v = np.nanmean(coh, axis=1)
            v[~pair_ok] = np.nan
            out["coh"][bi, mi] = v
            if mi == 0:
                with np.errstate(invalid="ignore", divide="ignore"):
                    cohy = Sab[:, m] / np.sqrt(Saa[ia][:, m] * Saa[ib][:, m])
                    ic = np.abs(np.nanmean(np.imag(cohy), axis=1))
                    pw = np.log10(np.nanmean(Saa[:, m] * scale, axis=1))
                ic[~pair_ok] = np.nan
                pw[~okv] = np.nan
                out["icoh"][bi] = ic
                out["power"][bi] = pw
    if not follow:
        return out

    # Band signals for PLI, the envelopes and PAC.
    Z = {}
    for bi, (_bid, lo, hi) in enumerate(BANDS):
        Zb = np.zeros((R, n), dtype=np.complex128)
        for r in range(R):
            if okv[r]:
                Zb[r] = sweep.analytic(Xa[r], fs, lo, hi, pad=True)
        Z[bi] = Zb
    for bi in range(B):
        Zb = Z[bi]
        x = Zb[ia] * np.conj(Zb[ib])
        pli = np.abs(np.mean(np.sign(np.imag(x)), axis=1))
        lag, peak = xcorr_lags(np.abs(Zb), ia, ib, fs)
        pli[~pair_ok] = np.nan
        lag[~pair_ok] = np.nan
        peak[~pair_ok] = np.nan
        out["pli"][bi] = pli
        out["xlag"][bi] = lag
        out["xpeak"][bi] = peak
    # PAC: theta phase (row) x gamma amplitude (column), itself included.
    th = np.angle(Z[0])
    ga = np.abs(Z[1])
    edges = np.linspace(-np.pi, np.pi, PAC_BINS + 1)
    for a in range(R):
        if not okv[a]:
            continue
        idx = np.clip(np.digitize(th[a], edges) - 1, 0, PAC_BINS - 1)
        counts = np.bincount(idx, minlength=PAC_BINS).astype(float)
        onehot = np.zeros((PAC_BINS, n))
        onehot[idx, np.arange(n)] = 1.0
        sums = ga @ onehot.T                                  # (R, bins)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = sums / counts[None, :]
            p = mean / np.nansum(mean, axis=1, keepdims=True)
            h = -np.nansum(np.where(p > 0, p * np.log(p), 0.0), axis=1)
        mi = (math.log(PAC_BINS) - h) / math.log(PAC_BINS)
        mi[~okv] = np.nan
        out["pac"][a] = mi
    # Granger both ways, at 250 Hz, 1 s segments, as the sweep does.
    usable = np.nonzero(pair_ok)[0]
    if usable.size:
        rows = []
        for r in range(R):
            rows.append(coupling.decimate_to(Xa[r], fs, GC_FS)[0] if okv[r] else None)
        n250 = min(len(y) for y in rows if y is not None)
        X250 = np.zeros((R, n250))
        for r, y in enumerate(rows):
            if y is not None:
                X250[r] = y[:n250]
        nseg = int(round(1.0 * GC_FS))
        if n250 >= nseg:
            win = coupling.matlab_hanning(nseg)
            segs = sweep._segments(X250, nseg, nseg // 2)
            segs = segs - segs.mean(axis=2, keepdims=True)
            F = np.fft.fft(segs * win, n=2 * nseg, axis=2)
            a, b = ia[usable], ib[usable]
            S = np.empty((usable.size, 2 * nseg, 2, 2), dtype=np.complex128)
            S[..., 0, 0] = np.mean(np.abs(F[a]) ** 2, axis=1)
            S[..., 1, 1] = np.mean(np.abs(F[b]) ** 2, axis=1)
            S[..., 0, 1] = np.mean(F[a] * np.conj(F[b]), axis=1)
            S[..., 1, 0] = np.conj(S[..., 0, 1])
            try:
                H, sig, _it = sweep.wilson(S)
                g12, g21 = sweep.granger(H, sig)
                freqs = np.fft.fftfreq(2 * nseg, 1.0 / GC_FS)
                for bi, (_bid, lo, hi) in enumerate(BANDS):
                    m = band_mask(freqs, lo, hi) & (freqs > 0)
                    out["gc_ab"][bi, usable] = np.nanmean(g12[:, m], axis=1)
                    out["gc_ba"][bi, usable] = np.nanmean(g21[:, m], axis=1)
            except np.linalg.LinAlgError:
                pass
    return out


# --------------------------------------------------------------------------
# One rat-day
# --------------------------------------------------------------------------
def duration_s(folder):
    """A recording's length from its first CSC file: records x 512 / fs."""
    files = nlx.list_csc_files(folder)
    if not files:
        return None
    path = files[0][1] if isinstance(files[0], tuple) else list(dict(files).values())[0]
    hdr = nlx.read_header(path)
    fs = nlx._header_float(hdr, "SamplingFrequency") or nlx.DEFAULT_FS
    n_rec = max(0, (os.path.getsize(path) - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize)
    return n_rec * nlx.SAMPLES_PER_RECORD / float(fs)


def letters_of(rat, cue_type):
    """(pair, cue-1 letter, cue-2 letter, cue-1 sound, cue-2 sound) for a
    trial of this cue type in this rat, from the identity sheet; Nones
    when the sheet does not have it."""
    p = ratidentity.pair_of(rat, cue_type)
    ids = ratidentity.identity(rat) or {}
    if not p:
        return None, None, None, None, None
    return p, p[0], p[1], ids.get(p[0]), ids.get(p[1])


def _empty(n_units, R, P):
    B, M = len(BANDS), len(METHODS)
    W = len(WINDOWS)
    out = {"coh": np.full((W, n_units, B, M, P), np.nan, np.float64),
           "power": np.full((W, n_units, B, R), np.nan, np.float64),
           "pac": np.full((W, n_units, R, R), np.nan, np.float32),
           "wires": np.full((W, n_units, R), -1, np.int16)}
    for k in FOLLOW:
        out[k] = np.full((W, n_units, B, P), np.nan, np.float32)
    return out


def _put(arrs, wi, ui, m, wires=None):
    for k in ("coh", "power", "pac") + FOLLOW:
        arrs[k][wi, ui] = m[k]
    if wires is not None:
        arrs["wires"][wi, ui] = wires


def day_compute(d, names, chan_map, progress=None, check=None):
    """Every window of every trial of one rat-day, and its FP snippets.
    `d` is the Monolith manifest's day record. Returns (arrays, meta)."""
    t_start = time.time()
    R = len(names)
    P = len(pairs_of(R))
    folder = None
    for f in d.get("folders") or []:
        if f.get("role") == "SPC":
            folder = f.get("local")
    if not folder or not os.path.isdir(folder):
        raise JoeError("r%d %s: its SPC folder cannot be opened here." % (d["rat"], d["day"]), 409)
    bad = [int(c) for c in d.get("bad") or []]
    blocked = d.get("blocked") or {}
    units = list(d.get("units") or [])
    only = sorted({int(c) for nm, cs in chan_map.items() if nm not in blocked for c in cs})
    notes = []
    # Clipping, measured here: the 10 s baseline and both cues as Spark
    # judges them, and the 20 s baseline cut to the sample.
    state = {}
    try:
        by_pair, _pc = spark.clipping_for(folder, [{"pair_id": u["id"], "opener_t": float(u["pair"]["opener_t"]),
                                                     "closer_t": float(u["pair"]["closer_t"]),
                                                     "offset_t": float(u["pair"]["offset_t"])} for u in units],
                                          skip=bad)
    except Exception as exc:                              # noqa: BLE001
        raise JoeError("r%d %s: clipping could not be measured (%s)" % (d["rat"], d["day"], exc), 500)
    for uid, per in (by_pair or {}).items():
        for c, rec in (per or {}).items():
            for w in rec.get("windows") or []:
                state.setdefault(uid, {}).setdefault(w, set()).add(int(c))
    spans = [{"pair_id": u["id"], "windows": [("base20", float(u["pair"]["opener_t"]) - 20.0,
                                               float(u["pair"]["opener_t"]))]} for u in units]
    clip = spark.clipping_windows(folder, spans, skip=bad, only=only)
    lost20 = {}
    for uid, per in ((clip or {}).get("by_pair") or {}).items():
        for c, rec in (per or {}).items():
            if "base20" in (rec.get("windows") or []):
                lost20.setdefault(uid, set()).add(int(c))
    for uid, per in ((clip or {}).get("unmeasured") or {}).items():
        for c in (per or {}):
            lost20.setdefault(uid, set()).add(int(c))
    arrs = _empty(len(units), R, P)
    trials = []
    for ui, u in enumerate(units):
        if check:
            check()
        if progress:
            progress(ui, len(units) + 2, "r%d %s · trial %d of %d" % (d["rat"], d["day"], ui + 1, len(units)))
        p, l1, l2, s1, s2 = letters_of(d["rat"], u.get("cue_type"))
        trials.append({"id": u["id"], "cue_type": u.get("cue_type"), "pair": p, "letters": [l1, l2],
                       "sounds": [s1, s2], "t": [u["pair"]["opener_t"], u["pair"]["closer_t"], u["pair"]["offset_t"]]})
        wins = trial_windows(u["pair"])
        drop = trial_drop(u, state.get(u["id"]), lost20.get(u["id"], ()), bad)
        try:
            got = coupling._signals_for_windows(folder, chan_map, wins, drop, FS, blocked=blocked)
        except coupling.CouplingError as exc:
            notes.append("r%d %s %s: %s" % (d["rat"], d["day"], u["id"], exc))
            continue
        for wi, (wn, _a, _b) in enumerate(wins):
            w = got[wn]
            sigs = [w["regions"][nm]["signal"] if w["regions"][nm]["usable"] else None for nm in names]
            wires = [w["regions"][nm].get("channel") if w["regions"][nm].get("channel") is not None else -1 for nm in names]
            _put(arrs, wi, ui, measure(sigs), wires)
    # FP snippets, from FP1 and FP2 together.
    fps = [f for f in d.get("folders") or [] if f.get("role") in ("FP1", "FP2") and f.get("local")
           and os.path.isdir(f["local"])]
    recs = []
    for f in fps:
        dur = duration_s(f["local"])
        if dur:
            recs.append({"key": f["role"], "duration_s": dur, "local": f["local"]})
    fp, fp_meta = {}, {}
    for li, L in enumerate(FP_LENGTHS):
        if progress:
            progress(len(units) + li, len(units) + 2, "r%d %s · FP snippets, %g s" % (d["rat"], d["day"], L))
        snips = fp_random(recs, len(units), L, fp_seed(d["rat"], d["day"], L))
        name = "fp%d" % int(L)
        a = _empty(len(snips), R, P)
        for k in a:
            a[k] = a[k][:1]                               # one "window": the snippet
        meta_s = []
        for rec in recs:
            mine = [(i, s) for i, s in enumerate(snips) if s[0] == rec["key"]]
            if not mine:
                continue
            sp = [{"pair_id": "s%02d" % i, "windows": [(name, t0, t1)]} for i, (_k, t0, t1) in mine]
            cl = spark.clipping_windows(rec["local"], sp, skip=bad, only=only)
            for i, (_k, t0, t1) in mine:
                if check:
                    check()
                lost = set(bad)
                for c, r_ in (((cl or {}).get("by_pair") or {}).get("s%02d" % i) or {}).items():
                    if name in (r_.get("windows") or []):
                        lost.add(int(c))
                for c in (((cl or {}).get("unmeasured") or {}).get("s%02d" % i) or {}):
                    lost.add(int(c))
                try:
                    got = coupling._signals_for_windows(rec["local"], chan_map, [(name, t0, t1)],
                                                        {name: sorted(lost)}, FS, blocked=blocked)
                except coupling.CouplingError as exc:
                    notes.append("r%d %s %s snippet %d: %s" % (d["rat"], d["day"], rec["key"], i + 1, exc))
                    continue
                w = got[name]
                sigs = [w["regions"][nm]["signal"] if w["regions"][nm]["usable"] else None for nm in names]
                wires = [w["regions"][nm].get("channel") if w["regions"][nm].get("channel") is not None else -1
                         for nm in names]
                _put(a, 0, i, measure(sigs), wires)
        meta_s = [{"rec": k, "t0": t0, "t1": t1} for k, t0, t1 in snips]
        fp[name] = a
        fp_meta[name] = meta_s
    meta = {"schema": SCHEMA, "rat": d["rat"], "day": d["day"], "gid": d.get("gid"), "regions": list(names),
            "windows": list(WINDOWS), "bands": list(BAND_IDS), "methods": list(METHODS),
            "follow": list(FOLLOW), "trials": trials, "fp": fp_meta,
            "fp_recordings": [{"key": r["key"], "duration_s": r["duration_s"]} for r in recs],
            "notes": notes, "seconds": round(time.time() - t_start, 1)}
    return arrs, fp, meta


# --------------------------------------------------------------------------
# The day files, cached
# --------------------------------------------------------------------------
def day_key(d, names):
    """What one rat-day's numbers depend on: its trials and their clipping,
    its FP recordings, histology, the regions and this module's schema."""
    blob = json.dumps({"schema": SCHEMA, "units": d.get("units"), "bad": d.get("bad"),
                       "blocked": d.get("blocked"), "folders": [(f.get("role"), f.get("local"))
                                                                for f in d.get("folders") or []],
                       "names": list(names), "bands": BANDS, "skip": SKIP_HZ, "fp": [FP_SEED, FP_LENGTHS, FP_EDGE_S]},
                      sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def save_day(path, arrs, fp, meta):
    flat = {}
    for k, v in arrs.items():
        flat["t_" + k] = v
    for name, a in fp.items():
        for k, v in a.items():
            flat[name + "_" + k] = v
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, meta=np.array(json.dumps(meta, default=str)), **flat)
    os.replace(tmp, path)


def load_day(path):
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    arrs = {k[2:]: z[k] for k in z.files if k.startswith("t_")}
    fp = {}
    for name in ("fp10", "fp20"):
        a = {k[len(name) + 1:]: z[k] for k in z.files if k.startswith(name + "_")}
        if a:
            fp[name] = a
    return arrs, fp, meta


# --------------------------------------------------------------------------
# The models
# --------------------------------------------------------------------------
#: (id, label, kind, factor, levels, unit). `unit` is "pair" (coherence) or
#: "region" (power). Every model is Day (Precon1, Precon4) x factor x unit.
MODELS = (
    ("m1", "Baseline vs Cue 1 + Cue 2", "first", "Phase",
     (("base", "Baseline (20 s)"), ("cue", "Cue 1 + Cue 2 (20 s)")), "pair"),
    ("m2", "Baseline vs Cue 1", "first", "Phase",
     (("base", "Baseline (10 s)"), ("cue1", "Cue 1")), "pair"),
    ("m3", "Baseline vs Cue 2", "first", "Phase",
     (("base", "Baseline (10 s)"), ("cue2", "Cue 2")), "pair"),
    ("m4", "The switch: 8–10 s vs 10–12 s", "first", "Phase",
     (("swa", "8–10 s"), ("swb", "10–12 s")), "pair"),
    ("m5", "Cue 1 vs Cue 2", "first", "Phase",
     (("cue1", "Cue 1"), ("cue2", "Cue 2")), "pair"),
    ("m6a", "Trials vs FP (20 s): the Precon change against the FP change", "first", "Source",
     (("trials", "Trials (Cue 1 + Cue 2)"), ("fp", "FP snippets")), "pair"),
    ("m6b", "Trials vs FP (10 s): each cue against FP snippets", "first", "Source",
     (("trials", "Trials (each cue)"), ("fp", "FP snippets")), "pair"),
    ("m7", "Power in each region: baseline vs Cue 1 + Cue 2", "first", "Phase",
     (("base", "Baseline (20 s)"), ("cue", "Cue 1 + Cue 2 (20 s)")), "region"),
    ("c1", "Noise vs Click", "check", "Sound", (("Noise", "Noise"), ("Click", "Click")), "pair"),
    ("c2", "All four sounds", "check", "Sound",
     (("Click", "Click"), ("Noise", "Noise"), ("High", "High tone"), ("Low", "Low tone")), "pair"),
    ("c3", "A/B/C/D", "check", "Letter", (("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")), "pair"),
    ("c4", "High vs Low tone", "check", "Sound", (("High", "High tone"), ("Low", "Low tone")), "pair"),
)
MODEL_BY_ID = {m[0]: m for m in MODELS}
#: Each model's number, name and one line, for people: the tab, the SPSS
#: files and their README all say these (m1, m2 ... are only ids).
NAMES = {
    "m1": (1, "Baseline (20 s) → both cues", "The 20 s before cue 1 against cue 1 and cue 2 together (20 s)."),
    "m2": (2, "Baseline (10 s) → cue 1", "The 10 s before cue 1 against cue 1."),
    "m3": (3, "Baseline (10 s) → cue 2", "The 10 s before cue 1 against cue 2."),
    "m4": (4, "The switch: end of cue 1 → start of cue 2", "The last 2 s of cue 1 (8–10 s) against the first 2 s of cue 2 (10–12 s)."),
    "m5": (5, "Cue 1 → cue 2", "Cue 1 against cue 2."),
    "m6a": (6, "Trials vs FP, 20 s", "The Precon1 → Precon4 change in the trials (both cues, 20 s) against the same change in random 20 s FP snippets."),
    "m6b": (7, "Trials vs FP, 10 s", "The same with each cue (10 s) against random 10 s FP snippets."),
    "m7": (8, "Power, baseline (20 s) → both cues", "Power in each region instead of coherence between regions."),
    "c1": (9, "Noise vs Click", "The cue windows sorted by the sound that played (Noise or Click), not by its place in the pair."),
    "c2": (10, "All four sounds", "The cue windows sorted by sound: Click, Noise, High tone, Low tone."),
    "c3": (11, "A/B/C/D", "The cue windows sorted by position in the pair, from the identity sheet."),
    "c4": (12, "High vs Low tone", "The cue windows sorted by tone: high or low."),
}
#: The coherence the tab and the SPSS files show (Dickson 2022, Jeremy's
#: mscohere). Welch, the circuits' way, is still computed, only to say
#: whether it agrees (Shahriar, 2026-10-13).
SHOWN = "dickson"


def stem(mid):
    """A model's name as a file name: "01 Baseline 20 s to both cues"."""
    no, title, _w = NAMES[mid]
    t = title.replace("→", "to").replace("–", "-").replace("/", "-").replace(":", ",").replace("(", "").replace(")", "")
    return "%02d %s" % (no, " ".join(t.split()))
ALPHA = 0.05


def _trial_values(arr, meta, model, level, b, m):
    """One rat-day's trial values at one level: (n_trials_used, values per
    unit) -- the mean over its trials (and over both cue windows where a
    level takes either)."""
    mid = model[0]
    wi = {w: i for i, w in enumerate(WINDOWS)}
    trials = meta["trials"]
    pick = []                                     # (window index, trial index)
    for ti, t in enumerate(trials):
        if mid in ("m1", "m7"):
            pick.append((wi["base20" if level == "base" else "pair"], ti))
        elif mid in ("m2", "m3"):
            pick.append((wi["base10" if level == "base" else level], ti))
        elif mid in ("m4", "m5"):
            pick.append((wi[level], ti))
        elif mid == "m6a":
            pick.append((wi["pair"], ti))
        elif mid == "m6b":
            pick += [(wi["cue1"], ti), (wi["cue2"], ti)]
        else:
            got = t["sounds"] if model[3] == "Sound" else t["letters"]
            for k, x in enumerate(got or []):
                if x == level:
                    pick.append((wi["cue1" if k == 0 else "cue2"], ti))
    return pick


def unit_values(day_data, model, level, b, m):
    """{(rat, day): values over units} for one level: the mean over the
    picked trial windows, or over the FP snippets for the FP level."""
    out = {}
    for (rat, day), (arrs, fp, meta) in day_data.items():
        what = "power" if model[5] == "region" else "coh"
        if level == "fp" and model[0] in ("m6a", "m6b"):
            a = fp.get("fp20" if model[0] == "m6a" else "fp10")
            if not a:
                continue
            X = a[what][0]                                # (S, B, M, P) or (S, B, R)
            vals = X[:, b, m] if what == "coh" else X[:, b]
        else:
            pick = _trial_values(arrs, meta, model, level, b, m)
            if not pick:
                continue
            X = arrs[what]
            vals = np.stack([X[w, t, b, m] if what == "coh" else X[w, t, b] for w, t in pick])
        with np.errstate(invalid="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                out[(rat, day)] = np.nanmean(vals, axis=0)
    return out


def model_table(day_data, model, b, m, units, days=TESTED):
    """value[rat][day][level] -> array over units (NaN where missing)."""
    levels = [lv for lv, _l in model[4]]
    rats = sorted({r for r, _d in day_data})
    out = {r: {d: {} for d in days} for r in rats}
    for lv in levels:
        got = unit_values(day_data, model, lv, b, m)
        for r in rats:
            for d in days:
                v = got.get((r, d))
                out[r][d][lv] = v if v is not None else np.full(len(units), np.nan)
    return out


def included_units(tab, model, units):
    """The units at least MIN_RATS rats have at every level on both tested
    days."""
    levels = [lv for lv, _l in model[4]]
    keep = []
    for ui in range(len(units)):
        n = 0
        for r, per in tab.items():
            if all(np.isfinite(per[d][lv][ui]) for d in TESTED for lv in levels):
                n += 1
        if n >= MIN_RATS:
            keep.append(ui)
    return keep


def _frame(tab, model, keep, unit_names):
    import pandas as pd
    rows = []
    for r, per in tab.items():
        for d in TESTED:
            for lv, _l in model[4]:
                for ui in keep:
                    v = per[d][lv][ui]
                    if np.isfinite(v):
                        rows.append((r, d, lv, unit_names[ui], float(v)))
    return pd.DataFrame(rows, columns=["rat", "day", "level", "unit", "value"])


TERM_NAMES = {"C(day, Sum)": "Day", "C(level, Sum)": "{f}", "C(unit, Sum)": "{u}"}


def _term(name, factor, unit):
    parts = [TERM_NAMES.get(p, p).format(f=factor, u="Pair" if unit == "pair" else "Region")
             for p in name.split(":")]
    return " × ".join(parts)


def _helmert(L):
    """L - 1 orthonormal contrasts over L levels (rows)."""
    H = np.zeros((L - 1, L))
    for j in range(1, L):
        H[j - 1, :j] = -1.0 / j
        H[j - 1, j] = 1.0
        H[j - 1] /= np.linalg.norm(H[j - 1])
    return H


def _contrast_frames(df, levels):
    """Each rat x unit with all 2L cells, as its contrasts: the mean (for
    Unit), the day change averaged over the levels (Day, Day x Unit), and
    the levels' L - 1 orthonormal contrasts of the mean over the days
    (factor, factor x Unit) and of the day change (Day x factor, Day x
    factor x Unit). The repeated-measures ANOVA's strata, one score each."""
    import pandas as pd
    L = len(levels)
    H = _helmert(L)
    pv = df.pivot_table(index=["rat", "unit"], columns=["day", "level"], values="value", aggfunc="first")
    cols = [(d, lv) for d in TESTED for lv in levels]
    pv = pv.reindex(columns=pd.MultiIndex.from_tuples(cols)).dropna()
    Y1 = pv[[(TESTED[0], lv) for lv in levels]].to_numpy()
    Y4 = pv[[(TESTED[1], lv) for lv in levels]].to_numpy()
    rat = pv.index.get_level_values(0).to_numpy()
    unit = pv.index.get_level_values(1).to_numpy()
    scal = pd.DataFrame({"rat": rat, "unit": unit, "m": (Y1 + Y4).mean(axis=1) / 2.0,
                         "d": (Y4 - Y1).mean(axis=1)})
    rows = []
    mid = (Y1 + Y4) / 2.0
    chg = Y4 - Y1
    for j in range(L - 1):
        rows.append(pd.DataFrame({"rat": rat, "unit": unit, "j": "c%d" % j, "lv": mid @ H[j], "dl": chg @ H[j]}))
    return scal, pd.concat(rows, ignore_index=True)


def _mlm(formula, data, groups):
    """A REML random-intercept fit, trying the next optimiser when one fails:
    L-BFGS now and then steps somewhere singular."""
    import statsmodels.formula.api as smf
    md = smf.mixedlm(formula, data, groups=groups)
    last = None
    for meth in ("lbfgs", "bfgs", "powell", "nm"):
        try:
            r = md.fit(reml=True, method=[meth])
        except Exception as e:                           # noqa: BLE001
            last = e
            continue
        if r.converged and np.all(np.isfinite(r.bse_fe)):
            return r
        last = last or RuntimeError("did not converge")
    raise JoeError("a mixed model did not fit (%s)" % last)


def fit_mixed(df, factor, unit):
    """Day x factor x unit as the repeated-measures ANOVA's strata, each
    fitted as a mixed model of the rat x unit contrasts that stratum is
    about, with the rat random: Unit from each rat x unit's mean; Day and
    Day x Unit from its day change; factor and factor x Unit from the
    levels' orthonormal contrasts of its mean, and Day x factor and Day x
    factor x Unit from those of its day change (each rat x contrast its own
    random intercept, one variance, as the univariate RM-ANOVA assumes).
    On complete data every F is the RM-ANOVA's, except where a stratum's rat variance
    estimates at zero, when the mixed model pools that stratum's error with
    the one below it, as SPSS MIXED and lme4 do; a rat missing a pair keeps
    its other pairs (the RM-ANOVA, like SPSS's GLM, drops the whole rat).
    Checked against AnovaRM on made-up data, two and four levels. F from Wald
    tests, with each stratum's (rats - 1) x df denominator; SPSS MIXED with
    the full random structure, from the exported syntax, is the reference.

    One mixed model over the long data with every stratum as a variance
    component is the same thing in principle, and was tried: on the real
    44 pairs it took ten minutes a fit (2026-10-09)."""
    import warnings
    import pandas as pd
    from scipy.stats import f as fdist
    levels = list(pd.unique(df["level"]))
    N0 = df["rat"].nunique()
    if N0 < MIN_RATS:
        return {"ok": False, "why": "fewer than %d rats" % MIN_RATS}
    scal, cont = _contrast_frames(df, levels)
    N = scal["rat"].nunique()
    K = scal["unit"].nunique()
    L = len(levels)
    if N < MIN_RATS or K < 1:
        return {"ok": False, "why": "fewer than %d rats with every cell of a %s" % (MIN_RATS, "pair" if unit == "pair" else "region")}
    many = K > 1
    u = "Pair" if unit == "pair" else "Region"
    terms = {}

    def put(name, chi2, df1, df2):
        F = chi2 / df1
        terms[name] = {"F": F, "df1": int(df1), "df2": int(max(1, df2)), "p": float(fdist.sf(F, df1, max(1, df2))), "chi2": float(chi2)}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            _strata(scal, cont, factor, u, many, N, K, L, put)
        except JoeError as exc:
            return {"ok": False, "why": str(exc)}
    return {"ok": True, "terms": terms, "n_rats": int(N), "n_obs": int(len(scal)),
            "random": "each stratum’s rat × %s contrasts, the rat random" % u.lower()}


def _strata(scal, cont, factor, u, many, N, K, L, put):
    """The four strata's fits, each term handed to put()."""
    # Unit, from the means; Day and Day x Unit, from the day changes.
    for col, main, inter in (("m", None, u), ("d", "Day", "Day × " + u)):
        r = _mlm(col + (" ~ C(unit, Sum)" if many else " ~ 1"), scal, scal["rat"])
        w = r.wald_test_terms(skip_single=False, scalar=True).summary_frame()
        if main and "Intercept" in w.index:
            put(main, float(w.loc["Intercept", "chi2"]), 1, N - 1)
        if many and "C(unit, Sum)" in w.index:
            put(inter, float(w.loc["C(unit, Sum)", "chi2"]), K - 1, (N - 1) * (K - 1))
    # factor and factor x Unit; Day x factor and Day x factor x Unit.
    for col, main, inter in (("lv", factor, factor + " × " + u), ("dl", "Day × " + factor, "Day × " + factor + " × " + u)):
        f = col + " ~ 0 + C(j)" + (" + C(j):C(unit, Sum)" if many else "")
        r = _mlm(f, cont, cont["rat"].astype(str) + "|" + cont["j"])
        w = r.wald_test_terms(skip_single=False, scalar=True).summary_frame()
        if "C(j)" in w.index:
            put(main, float(w.loc["C(j)", "chi2"]), L - 1, (N - 1) * (L - 1))
        if many and "C(j):C(unit, Sum)" in w.index:
            put(inter, float(w.loc["C(j):C(unit, Sum)", "chi2"]), (L - 1) * (K - 1), (N - 1) * (L - 1) * (K - 1))


def holm(p):
    p = np.asarray(p, dtype=np.float64)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if not m:
        return out
    idx = np.nonzero(ok)[0]
    order = idx[np.argsort(p[idx])]
    run = 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * p[i]))
        out[i] = run
    return out


def contrast_rows(tab, model, keep, unit_names):
    """One row per rat and unit with all four values: (rat, unit index,
    unit, Precon1 at the first level, Precon1 at the second, Precon4 at the
    first, Precon4 at the second, the difference (P4 second - P4 first) -
    (P1 second - P1 first)). Two-level models only. Fitted with the rat
    random and the unit fixed, it is the stratum fit_mixed tests Day x
    level and Day x level x unit in (the same rows, scaled by a constant)."""
    a, b = [lv for lv, _l in model[4]]
    rows = []
    for r in sorted(tab, key=int):
        per = tab[r]
        for ui in keep:
            v = [per["Precon1"][a][ui], per["Precon1"][b][ui], per["Precon4"][a][ui], per["Precon4"][b][ui]]
            if all(np.isfinite(v)):
                rows.append((int(r), ui, unit_names[ui], float(v[0]), float(v[1]), float(v[2]), float(v[3]),
                             float((v[3] - v[2]) - (v[1] - v[0]))))
    return rows


def quick_check(tab, model, keep):
    """The check anyone can do by hand: each rat's mean difference over the
    units it has, then a one-sample t against 0. Close to the mixed model's
    Day x level (not equal: rats have different numbers of units)."""
    from scipy.stats import ttest_1samp
    per = {}
    for r, _ui, _u, _a, _b, _c, _d, dif in contrast_rows(tab, model, keep, [str(i) for i in range(max(keep) + 1)]):
        per.setdefault(r, []).append(dif)
    means = [float(np.mean(v)) for _r, v in sorted(per.items())]
    if len(means) < 2:
        return None
    t = ttest_1samp(means, 0.0)
    return {"t": float(t.statistic), "df": len(means) - 1, "p": float(t.pvalue), "n_rats": len(means),
            "mean": float(np.mean(means)), "per_rat": {str(r): float(np.mean(v)) for r, v in sorted(per.items())}}


def post_hocs(tab, model, keep, unit_names):
    """Which units drive it: per unit, the Day x factor interaction across
    rats. Two levels: each rat's (Precon4 difference) - (Precon1
    difference), a one-sample t. More levels: a one-way repeated-measures
    ANOVA of each rat's Precon4 - Precon1 change across the levels. Holm
    over the units of this model."""
    from scipy.stats import t as tdist, f as fdist
    levels = [lv for lv, _l in model[4]]
    rows = []
    for ui in keep:
        X = []
        for r, per in tab.items():
            ch = [per["Precon4"][lv][ui] - per["Precon1"][lv][ui] for lv in levels]
            if all(np.isfinite(ch)):
                X.append(ch)
        X = np.array(X)
        n = X.shape[0]
        row = {"unit": unit_names[ui], "n": int(n)}
        if len(levels) == 2 and n >= 2:
            dlt = X[:, 1] - X[:, 0]
            mean = float(dlt.mean())
            se = float(dlt.std(ddof=1) / math.sqrt(n))
            t = mean / se if se > 0 else float("nan")
            row.update(delta=mean, se=se, t=t, df=n - 1,
                       p=float(2 * tdist.sf(abs(t), n - 1)) if np.isfinite(t) else float("nan"),
                       same=int(np.sum(np.sign(dlt) == np.sign(mean))))
        elif n >= 2:
            k = len(levels)
            grand = X.mean()
            ss_l = n * np.sum((X.mean(axis=0) - grand) ** 2)
            ss_r = k * np.sum((X.mean(axis=1) - grand) ** 2)
            ss_e = np.sum((X - grand) ** 2) - ss_l - ss_r
            df1, df2 = k - 1, (k - 1) * (n - 1)
            F = (ss_l / df1) / (ss_e / df2) if ss_e > 0 else float("nan")
            row.update(F=float(F), df1=df1, df2=df2, p=float(fdist.sf(F, df1, df2)) if np.isfinite(F) else float("nan"),
                       spread=float(X.mean(axis=0).max() - X.mean(axis=0).min()))
        rows.append(row)
    ph = holm([r.get("p", float("nan")) for r in rows])
    for r, h in zip(rows, ph):
        r["p_holm"] = float(h)
    return rows


def cells(tab_all, model, keep):
    """For the interaction plot: each day x level, the mean over rats of each
    rat's mean over the included units, with its SE and how many rats."""
    out = {}
    for d in DAYS:
        out[d] = {}
        for lv, _l in model[4]:
            v = []
            for r, per in tab_all.items():
                x = per.get(d, {}).get(lv)
                if x is None:
                    continue
                x = np.asarray(x)[keep] if keep else np.asarray(x)
                if np.isfinite(x).any():
                    v.append(float(np.nanmean(x)))
            v = np.array(v)
            out[d][lv] = {"mean": float(v.mean()) if v.size else None,
                          "se": float(v.std(ddof=1) / math.sqrt(v.size)) if v.size > 1 else None,
                          "n": int(v.size), "rats": [float(x) for x in v]}
    return out


def gate_of(mixed, factor, unit):
    """Whether a model opens its follow-ups, and through which term."""
    if not mixed.get("ok"):
        return {"passed": False, "by": None}
    u = "Pair" if unit == "pair" else "Region"
    three = "Day × %s × %s" % (factor, u)
    two = "Day × %s" % factor
    t3 = mixed["terms"].get(three) or {}
    t2 = mixed["terms"].get(two) or {}
    if t3.get("p") is not None and t3["p"] < ALPHA:
        return {"passed": True, "by": three, "p": t3["p"]}
    if t2.get("p") is not None and t2["p"] < ALPHA:
        return {"passed": True, "by": two, "p": t2["p"]}
    return {"passed": False, "by": None}


# --------------------------------------------------------------------------
# Follow-ups, for the pairs a gate let through
# --------------------------------------------------------------------------
FOLLOW_SAY = {"pli": "PLI", "icoh": "Imaginary coherence", "gc_ab": "Granger A→B", "gc_ba": "Granger B→A",
              "xlag": "Amplitude xcorr lag (ms)", "xpeak": "Amplitude xcorr peak r",
              "pac_ab": "PAC: A theta phase → B gamma amplitude", "pac_ba": "PAC: B theta phase → A gamma amplitude",
              "pac_aa": "PAC within A", "pac_bb": "PAC within B"}


def follow_values(day_data, model, level, b, pair_index, a, bb, measure_id):
    """{(rat, day): value} of one follow-up measure for one pair."""
    out = {}
    for (rat, day), (arrs, fp, meta) in day_data.items():
        if level == "fp" and model[0] in ("m6a", "m6b"):
            src = fp.get("fp20" if model[0] == "m6a" else "fp10")
            if not src:
                continue
            pick = [(0, s) for s in range(src["coh"].shape[1])]
            A = src
        else:
            pick = _trial_values(arrs, meta, model, level, b, 0)
            A = arrs
        if not pick:
            continue
        vals = []
        for w, t in pick:
            if measure_id.startswith("pac_"):
                i, j = {"pac_ab": (a, bb), "pac_ba": (bb, a), "pac_aa": (a, a), "pac_bb": (bb, bb)}[measure_id]
                vals.append(A["pac"][w, t, i, j])
            else:
                vals.append(A[measure_id][w, t, b, pair_index])
        vals = np.array(vals, dtype=np.float64)
        if np.isfinite(vals).any():
            out[(rat, day)] = float(np.nanmean(vals))
    return out


def follow_test(day_data, model, b, pair_index, a, bb, measure_id):
    from scipy.stats import t as tdist
    levels = [lv for lv, _l in model[4]]
    per = {lv: follow_values(day_data, model, lv, b, pair_index, a, bb, measure_id) for lv in levels}
    rats = sorted({r for lv in levels for (r, _d) in per[lv]})
    means = {}
    for d in TESTED:
        means[d] = {}
        for lv in levels:
            v = [per[lv][(r, d)] for r in rats if (r, d) in per[lv]]
            means[d][lv] = float(np.mean(v)) if v else None
    out = {"means": means}
    if len(levels) != 2:
        return out
    dl = []
    for r in rats:
        try:
            dl.append((per[levels[1]][(r, "Precon4")] - per[levels[0]][(r, "Precon4")])
                      - (per[levels[1]][(r, "Precon1")] - per[levels[0]][(r, "Precon1")]))
        except KeyError:
            continue
    dl = np.array([x for x in dl if np.isfinite(x)])
    n = dl.size
    if n >= 2:
        se = dl.std(ddof=1) / math.sqrt(n)
        t = dl.mean() / se if se > 0 else float("nan")
        out.update(delta=float(dl.mean()), t=float(t), df=n - 1, n=int(n),
                   p=float(2 * tdist.sf(abs(t), n - 1)) if np.isfinite(t) else None)
    return out


def bilateral(names):
    """The homotopic pairs: left and right of one structure."""
    out = []
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            sa, sb = names[a].split(" ", 1), names[b].split(" ", 1)
            if len(sa) == 2 and len(sb) == 2 and sa[1] == sb[1] and sa[0] != sb[0]:
                out.append((a, b))
    return out


# --------------------------------------------------------------------------
# Everything, from the day files
# --------------------------------------------------------------------------
def short(name):
    return str(name).replace("Left ", "L ").replace("Right ", "R ")


def code(name):
    return short(name).replace(" ", "").replace("-", "")


def build(day_data, names, progress=None, check=None):
    """The models, their gates, post hocs and follow-ups, from the loaded
    day files {(rat, day): (arrs, fp, meta)}."""
    pr = pairs_of(len(names))
    pair_names = ["%s – %s" % (short(names[a]), short(names[b])) for a, b in pr]
    bil = set(bilateral(names))
    results, n_done = [], 0
    jobs = [(mdl, bi, mi) for mdl in MODELS for bi in range(len(BANDS))
            for mi in range(len(METHODS) if mdl[5] == "pair" else 1)]
    exports = []
    for mdl, bi, mi in jobs:
        if check:
            check()
        if progress:
            progress(n_done, len(jobs), "%s · %s%s" % (mdl[1], BAND_SAY[BANDS[bi][0]],
                                                      " · " + METHOD_SAY[METHODS[mi]] if mdl[5] == "pair" else ""))
        n_done += 1
        units = pair_names if mdl[5] == "pair" else [short(n) for n in names]
        tab_all = model_table(day_data, mdl, bi, mi, units, days=DAYS)
        tab = {r: {d: per[d] for d in TESTED} for r, per in tab_all.items()}
        keep = included_units(tab, mdl, units)
        res = {"model": mdl[0], "band": BANDS[bi][0], "method": METHODS[mi] if mdl[5] == "pair" else "welch",
               "units": [units[i] for i in keep], "n_units": len(keep),
               "left_out": [units[i] for i in range(len(units)) if i not in keep]}
        if len(keep) < 1:
            res.update(mixed={"ok": False, "why": "no %s has %d rats on both days" % (mdl[5], MIN_RATS)},
                       gate={"passed": False}, cells=cells(tab_all, mdl, keep), post=[])
            results.append(res)
            continue
        df = _frame(tab, mdl, keep, units)
        res["mixed"] = fit_mixed(df, mdl[3], mdl[5])
        # The rats with every cell: the ones a repeated-measures ANOVA
        # (SPSS's GLM) could keep. Not run: with the pairs histology rules
        # out, it would keep 3 of the 8 rats (2026-10-13); the mixed model
        # keeps every rat with the pairs it has. Said so on the tab.
        n_cells = 2 * len(mdl[4]) * len(keep)
        full = df.groupby("rat").size()
        res["rats"] = sorted(int(r) for r in full.index)
        res["complete_rats"] = sorted(int(r) for r, n in full.items() if n == n_cells)
        if len(mdl[4]) == 2:
            res["quick"] = quick_check(tab, mdl, keep)
        res["gate"] = gate_of(res["mixed"], mdl[3], mdl[5])
        res["cells"] = cells(tab_all, mdl, keep)
        res["post"] = post_hocs(tab, mdl, keep, units)
        res["table"] = {str(r): {d: {lv: [None if not np.isfinite(x) else float(x) for x in per[d][lv]]
                                     for lv, _l in mdl[4]} for d in DAYS}
                        for r, per in tab_all.items()}
        res["all_units"] = units
        # Follow-ups: first-pass coherence models whose gate passed; the
        # pairs Holm keeps, or, when none does, the pairs at raw p < .05,
        # said as such.
        if res["gate"].get("passed") and mdl[2] == "first" and mdl[5] == "pair":
            ps = [r for r in res["post"] if r.get("p_holm") is not None and r["p_holm"] < ALPHA]
            basis = "Holm"
            if not ps:
                ps = [r for r in res["post"] if r.get("p") is not None and r["p"] < ALPHA]
                basis = "raw p < .05 (none survives Holm)"
            fol = []
            for r in ps:
                pi = pair_names.index(r["unit"])
                a, bb = pr[pi]
                meas = {k: follow_test(day_data, mdl, bi, pi, a, bb, k)
                        for k in ("pli", "icoh", "gc_ab", "gc_ba", "xlag", "xpeak",
                                  "pac_ab", "pac_ba", "pac_aa", "pac_bb")}
                fol.append({"pair": r["unit"], "a": short(names[a]), "b": short(names[bb]),
                            "bilateral": (a, bb) in bil, "measures": meas})
            res["follow"] = {"basis": basis, "pairs": fol}
        results.append(res)
    # Bilateral coherence, gated on any first-pass coherence model passing.
    bl = [pair_names[pr.index(p)] for p in sorted(bil)]
    return {"schema": SCHEMA, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "regions": [short(n) for n in names],
            "pairs": pair_names, "bilateral": bl, "bands": [{"id": b, "low": lo, "high": hi, "label": BAND_SAY[b]}
                                                            for b, lo, hi in BANDS],
            "methods": [{"id": m, "label": METHOD_SAY[m]} for m in METHODS],
            "models": [{"id": m[0], "label": m[1], "kind": m[2], "factor": m[3],
                        "levels": [{"id": a, "label": b} for a, b in m[4]], "unit": m[5],
                        "no": NAMES[m[0]][0], "title": NAMES[m[0]][1], "what": NAMES[m[0]][2], "stem": stem(m[0])}
                       for m in MODELS],
            "shown": SHOWN,
            "days": list(DAYS), "tested": list(TESTED), "min_rats": MIN_RATS, "alpha": ALPHA,
            "skip_hz": list(SKIP_HZ), "fp": {"seed": FP_SEED, "lengths": list(FP_LENGTHS), "edge_s": FP_EDGE_S},
            "results": results, "follow_say": FOLLOW_SAY}


# --------------------------------------------------------------------------
# Exports: the SPSS package, and the files the script is checked against
# --------------------------------------------------------------------------
MISSING = 999                       # a missing cell in the wide files the script is checked against


def ascii_(text):
    """For SPSS: its labels and paths, and a README any editor opens."""
    for a, b in (("→", "to"), ("–", "-"), ("—", "-"), ("×", "x"), ("·", "-"), ("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("−", "-")):
        text = text.replace(a, b)
    return text


def _q(text):
    """An SPSS quoted string."""
    return "'" + ascii_(str(text)).replace("'", "''") + "'"


def _p(p):
    if p is None or not np.isfinite(p):
        return "-"
    return "< .001" if p < 0.001 else ("%.3f" % p).lstrip("0")


def _fp(t):
    if not t or t.get("F") is None:
        return "-"
    return "F(%d, %d) = %.2f, p %s%s" % (t["df1"], t["df2"], t["F"], "" if _p(t["p"]).startswith("<") else "= ", _p(t["p"]))


def words(p):
    """The tab's words for a p: strong evidence below .01, some below .05."""
    if p is None or not np.isfinite(p):
        return "no evidence"
    return "strong evidence" if p < 0.01 else "some evidence" if p < ALPHA else "no evidence"


def _lit(res):
    return bool(res and res.get("mixed", {}).get("ok") and (res.get("gate") or {}).get("passed"))


def _terms(res, mdl):
    u = "Pair" if mdl[5] == "pair" else "Region"
    t = res["mixed"]["terms"]
    return t.get("Day × %s" % mdl[3]), t.get("Day × %s × %s" % (mdl[3], u))


def _say(mdl, res):
    """The two lines of words the tab says for a result."""
    u = "pair" if mdl[5] == "pair" else "region"
    t2, t3 = _terms(res, mdl)
    w2, w3 = words(t2 and t2["p"]), words(t3 and t3["p"])
    return ("All %ss together: %s of a change" % (u, w2),
            "%s by %s: %s" % (u.capitalize(), u, "none stands out" if w3 == "no evidence" else w3 + " that some changed more than others"))


def compare_name(res):
    """The standalone script's file for a result (both methods)."""
    return "%s_%s_%s" % (res["model"], res["band"], res["method"])


def wide_rows(res, mdl):
    """Header and rows of the file the standalone script is checked against:
    one row per rat, one column per Day x level x unit (day-major, unit
    fastest)."""
    units = res["units"]
    cols = []
    for d in TESTED:
        dn = d.replace("Precon", "D")
        for lv, _l in mdl[4]:
            for u in units:
                cols.append((d, lv, u, "%s_%s_%s" % (dn, lv, code(u).replace("–", "_"))))
    rows = []
    allu = res["all_units"]
    for r, per in sorted(res["table"].items(), key=lambda x: int(x[0])):
        row = [r]
        for d, lv, u, _c in cols:
            v = per[d][lv][allu.index(u)]
            row.append(MISSING if v is None else "%.10g" % v)
        rows.append(row)
    return cols, rows


def long_rows(res, mdl):
    """SPSS's file: one row per rat, day, level and unit that has a value
    (a missing one is simply not there). Day is 1 or 4 (Precon1, Precon4)."""
    units = res["units"]
    allu = res["all_units"]
    rows = []
    for r, per in sorted(res["table"].items(), key=lambda x: int(x[0])):
        for d in TESTED:
            for li, (lv, lab) in enumerate(mdl[4]):
                for ki, u in enumerate(units):
                    v = per[d][lv][allu.index(u)]
                    if v is not None:
                        rows.append((int(r), int(d.replace("Precon", "")), li + 1, ki + 1, v, d, ascii_(lab), ascii_(u)))
    return rows


def _band_say(band):
    return ascii_(BAND_SAY[band]).replace("Theta", "theta").replace("Gamma", "gamma")


def _what_value(mdl, band):
    if mdl[5] == "region":
        return "log10 power, %s" % _band_say(band)
    return "coherence (Dickson 2022), %s" % _band_say(band)


def _cd(folder):
    return ["* 1. Change the next line to the folder this file is in, then Run > All.",
            "CD 'C:\\Users\\YOU\\Downloads\\joe_tab8_spss\\%s'." % folder, ""]


def main_sps(res, mdl, csv_name, folder):
    """The full model: Day x level x unit, the rat random with every
    stratum, as a statistician would write it."""
    no, title, what = NAMES[mdl[0]]
    f, u = mdl[3].lower(), ("pair" if mdl[5] == "pair" else "region")
    val = "power" if mdl[5] == "region" else "coherence"
    K = len(res["units"])
    t2, t3 = _terms(res, mdl)
    s2, s3 = _say(mdl, res)
    a, b = mdl[4][0][1], mdl[4][-1][1]
    lines = ["* " + "=" * 72,
             "* Tab 8, Joe's data. Comparison %d: %s, %s." % (no, ascii_(title), _band_say(res["band"])),
             "* " + ascii_(what),
             "* Each value: %s, the mean of that rat's trials on that day." % _what_value(mdl, res["band"]),
             "*",
             "* Where SPSS answers it (Type III Tests of Fixed Effects):",
             "*   day*%s        all %ss together: did %s differ between Precon1 and Precon4?" % (
                 f, u, ("the change from %s to %s" % (ascii_(a), ascii_(b))) if len(mdl[4]) == 2 else "the pattern across the %ss" % f),
             "*   day*%s*%s   %s by %s: did it differ more in some %ss than in others?" % (f, u, u, u, u),
             "*",
             "* Tab 8 found: day*%s %s (%s)." % (f, _fp(t2), s2.split(": ")[1]),
             "*              day*%s*%s %s (%s)." % (f, u, _fp(t3), s3.split(": ")[1]),
             "* This full model estimates all its variances together, and SPSS reports",
             "* Satterthwaite df, so its numbers will be close to tab 8's, not identical.",
             "* For a result that changed, '3 Recreate the positive results' reproduces",
             "* tab 8's F exactly.",
             "* " + "=" * 72, ""]
    lines += _cd(folder)
    lines += ["GET DATA /TYPE=TXT /FILE=%s /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=','" % _q(csv_name),
              "  /QUALIFIER='\"' /ARRANGEMENT=DELIMITED /FIRSTCASE=2 /VARIABLES=",
              "  rat F4.0 day F1.0 %s F2.0 %s F3.0 %s F14.10 day_name A8 %s_name A40 %s_name A24." % (f, u, val, f, u),
              "VARIABLE LABELS rat 'Rat' /day 'Day' /%s %s /%s %s /%s %s." % (
                  f, _q(mdl[3]), u, _q("Pair of regions" if u == "pair" else "Region"), val, _q(_what_value(mdl, res["band"]))),
              "VALUE LABELS day 1 'Precon1' 4 'Precon4'",
              "  /%s %s" % (f, " ".join("%d %s" % (i + 1, _q(l)) for i, (_x, l) in enumerate(mdl[4]))),
              "  /%s %s." % (u, " ".join("%d %s" % (i + 1, _q(x)) for i, x in enumerate(res["units"]))),
              "",
              "* 2. The mixed model: every rat, with every %s it has." % u]
    if K > 1:
        lines += ["MIXED %s BY day %s %s" % (val, f, u),
                  "  /FIXED=day %s %s day*%s day*%s %s*%s day*%s*%s | SSTYPE(3)" % (f, u, f, u, f, u, f, u),
                  "  /RANDOM=INTERCEPT day %s %s day*%s day*%s %s*%s | SUBJECT(rat) COVTYPE(VC)" % (f, u, f, u, f, u)]
    else:
        lines += ["MIXED %s BY day %s" % (val, f), "  /FIXED=day %s day*%s | SSTYPE(3)" % (f, f),
                  "  /RANDOM=INTERCEPT day %s | SUBJECT(rat) COVTYPE(VC)" % f]
    lines += ["  /METHOD=REML", "  /CRITERIA=DFMETHOD(SATTERTHWAITE)", "  /PRINT=SOLUTION TESTCOV.", ""]
    return "\r\n".join(lines)


def recreate_sps(res, mdl, csv_name, folder):
    """A positive result again, exactly: the stratum tab 8 tests it in (each
    rat and unit's difference, the unit fixed, the rat random), and the
    by-hand check (each rat's mean difference, a one-sample t)."""
    no, title, _w = NAMES[mdl[0]]
    u = "pair" if mdl[5] == "pair" else "region"
    (la, a), (lb, b) = mdl[4]
    t2, t3 = _terms(res, mdl)
    q = res.get("quick") or {}
    s2, s3 = _say(mdl, res)
    lines = ["* " + "=" * 72,
             "* Tab 8, Joe's data. Recreate comparison %d: %s, %s." % (no, ascii_(title), _band_say(res["band"])),
             "* One row per rat and %s with all four values, and their difference:" % u,
             "*   (Precon4 %s - Precon4 %s) - (Precon1 %s - Precon1 %s)." % (ascii_(b), ascii_(a), ascii_(b), ascii_(a)),
             "* How much more the value moved from %s to %s on Precon4 than on Precon1." % (ascii_(a), ascii_(b)),
             "*",
             "* Tab 8 found: all %ss together %s (%s);" % (u, _fp(t2), s2.split(": ")[1]),
             "*              %s by %s %s (%s)." % (u, u, _fp(t3), s3.split(": ")[1]),
             "* " + "=" * 72, ""]
    lines += _cd(folder)
    lines += ["GET DATA /TYPE=TXT /FILE=%s /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=','" % _q(csv_name),
              "  /QUALIFIER='\"' /ARRANGEMENT=DELIMITED /FIRSTCASE=2 /VARIABLES=",
              "  rat F4.0 %s F3.0 %s_name A24 p1_%s F14.10 p1_%s F14.10 p4_%s F14.10 p4_%s F14.10 difference F14.10." % (u, u, la, lb, la, lb),
              "DATASET NAME thedata.",
              "",
              "* A. The exact test, as tab 8 ran it. In 'Type III Tests of Fixed Effects':",
              "*    the Intercept row is all %ss together (tab 8: F = %.2f)," % (u, t2["F"]),
              "*    the %s row is %s by %s (tab 8: F = %.2f)." % (u, u, u, t3["F"]),
              "*    F should match to rounding. SPSS's df (Satterthwaite) can differ from",
              "*    tab 8's (%d and %d), so p can differ a little." % (t2["df2"], t3["df2"]),
              "MIXED difference BY %s" % u,
              "  /FIXED=%s | SSTYPE(3)" % u,
              "  /RANDOM=INTERCEPT | SUBJECT(rat) COVTYPE(VC)",
              "  /METHOD=REML",
              "  /PRINT=SOLUTION TESTCOV.",
              "",
              "* B. The check anyone can do by hand: each rat's mean difference over the",
              "*    %ss it has, then a one-sample t-test against 0." % u]
    if q:
        lines += ["*    Tab 8: t(%d) = %.2f, p %s. Close to A, not equal: rats have different" % (q["df"], q["t"], ("= " if not _p(q["p"]).startswith("<") else "") + _p(q["p"])),
                  "*    numbers of %ss." % u]
    lines += ["DATASET DECLARE ratmeans.",
              "AGGREGATE /OUTFILE=ratmeans /BREAK=rat /difference=MEAN(difference).",
              "DATASET ACTIVATE ratmeans.",
              "T-TEST /TESTVAL=0 /VARIABLES=difference.",
              "DATASET ACTIVATE thedata.", ""]
    return "\r\n".join(lines)


def _csv(header, rows):
    out = [",".join(header)]
    for r in rows:
        out.append(",".join(("%.10g" % x) if isinstance(x, float) else ('"%s"' % x if isinstance(x, str) and "," in x else str(x)) for x in r))
    return "\r\n".join(out) + "\r\n"


MAIN_DIR = "1 Main comparisons"
CHECK_DIR = "2 Checks, should show nothing"
REDO_DIR = "3 Recreate the positive results"
ZIP_NAME = "joe_tab8_spss.zip"
README_NAME = "joe_tab8_README.txt"
SUMMARY_NAME = "joe_tab8_results.csv"


def readme_text(out, positive, welch, rows_summary):
    """The README in the zip: what is there, what each number is, how to
    run one, why there is no repeated-measures ANOVA, and how to recreate
    each result that changed."""
    D = out
    n_rats = len(D.get("rats") or [])
    L = []
    w = L.append
    w("JOE'S DATA (TAB 8): THE FILES FOR SPSS")
    w("Made by Jarvis on %s from %d rat-days (%d rats). Precon1 and Precon4 are tested." % (
        D.get("at", "")[:10], D.get("n_days") or 0, n_rats))
    w("")
    w("WHAT IS IN HERE")
    w("  Results summary.csv              every comparison: its answer in words, and its numbers")
    w("  %-33s the 8 planned comparisons, each in theta and in gamma" % (MAIN_DIR + "\\"))
    w("  %-33s the 4 sound checks, which should show nothing" % (CHECK_DIR + "\\"))
    w("  %-33s for each result that changed, a small file that gives" % (REDO_DIR + "\\"))
    w("  %-33s tab 8's numbers back exactly" % "")
    w("  Each comparison is a .csv (the data) and a .sps (SPSS syntax that reads it and runs the test).")
    w("")
    w("THE COMPARISONS")
    for m in MODELS:
        no, title, what = NAMES[m[0]]
        w("  %2d  %s" % (no, ascii_(title)))
        w("      %s" % ascii_(what))
    w("")
    w("WHAT EACH VALUE IS")
    w("  Coherence: how much two regions' rhythms rise and fall together, from 0 to 1. Computed")
    w("  as in Dickson et al. 2022 (Jeremy's mscohere): a 59-61 Hz Butterworth notch, then")
    w("  hanning(1024) segments, 512 overlap, 2048 points; averaged over theta (5-12 Hz) or")
    w("  gamma (30-90 Hz, leaving out the notch's own 59-61 Hz).")
    w("  One value per rat, day, window and pair: the mean over that day's trials (16 cue pairs).")
    w("  Comparison 8 is power instead: log10 power in each region.")
    w("  Precon2 and Precon3 are drawn on the tab but never tested, so they are not in these files.")
    w("")
    w("THE TEST")
    w("  A mixed model: day (Precon1, Precon4) x phase (the comparison's two windows) x pair,")
    w("  with the rat as the random factor. Two rows of its output answer the question:")
    w("    day*phase        all pairs together: did the change from one window to the other")
    w("                     differ between Precon1 and Precon4, on average over the pairs?")
    w("    day*phase*pair   pair by pair: did it differ more in some pairs than in others?")
    w("  A comparison 'changed' when either reaches p < .05. p is not corrected: these are the")
    w("  comparisons the proposal planned, not a search.")
    w("  Words on the tab: strong evidence below p = .01, some evidence below .05, otherwise none.")
    w("")
    w("WHY THERE IS NO REPEATED-MEASURES ANOVA (GLM)")
    full = sorted({r for x in out["results"] if x.get("complete_rats") is not None and x["model"] == "m1" for r in x["complete_rats"]})
    w("  SPSS's GLM repeated measures can only use a rat that has every pair on both days.")
    w("  Histology rules regions out for some rats, and every pair touching such a region is")
    w("  missing for that rat. Only %d of the %d rats (%s) have every pair, so GLM would drop" % (
        len(full), n_rats, ", ".join(str(r) for r in full) or "none"))
    w("  the rest and rest on %d degree%s of freedom. The mixed model keeps all %d rats, each" % (
        max(0, len(full) - 1), "" if len(full) == 2 else "s", n_rats))
    w("  with the pairs it has. With every rat complete the two give the same F (checked in")
    w("  Jarvis, tools/check_joe.py, on made-up data).")
    w("")
    w("HOW TO RUN ONE")
    w("  1. Unzip everything. Keep the folders as they are.")
    w("  2. In SPSS: File > Open > Syntax, and pick a .sps.")
    w("  3. Change the CD line near its top to the folder that .sps is in.")
    w("  4. Run > All.")
    w("  5. Read the table 'Type III Tests of Fixed Effects'.")
    w("")
    w("HOW TO RECREATE THE POSITIVE RESULTS")
    if not positive:
        w("  No comparison changed, so there is nothing to recreate.")
    else:
        w("  Tab 8 found a change in:")
        for x in positive:
            w("    %2d  %s, %s" % (x["no"], ascii_(x["title"]), x["band"]))
            w("        all pairs together: %s" % x["two_say"])
            w("        pair by pair:       %s" % x["three_say"])
        w("  For each, '%s' has two files:" % REDO_DIR)
        w("    '... - per rat and pair.csv': one row per rat and pair with the four values")
        w("      (Precon1 and Precon4, each window) and their difference,")
        w("      (Precon4 second window - Precon4 first) - (Precon1 second - Precon1 first).")
        w("    '... - recreate.sps', which runs two things:")
        w("      A. The exact test. A mixed model of the difference, pair fixed, rat random:")
        w("         the Intercept row is 'all pairs together' and the pair row is 'pair by pair'.")
        w("         These are the very tests tab 8 ran, so F should match tab 8's to rounding.")
        w("         SPSS reports Satterthwaite df, which can differ from tab 8's, so p can move a")
        w("         little.")
        w("      B. A check anyone can do by hand: each rat's mean difference over its own pairs,")
        w("         then a one-sample t-test against 0 (t(7) with 8 rats). It comes close to A,")
        w("         not exactly, because the rats have different numbers of pairs.")
        for x in positive:
            if x.get("quick"):
                q = x["quick"]
                w("         Comparison %d, %s: t(%d) = %.2f, p %s." % (x["no"], x["band"], q["df"], q["t"],
                                                                     ("= " if not _p(q["p"]).startswith("<") else "") + _p(q["p"])))
    w("  The full model in '%s' estimates all its variances together," % MAIN_DIR)
    w("  so its day*phase F comes close to tab 8's but is not identical.")
    w("")
    w("WELCH")
    w("  Tab 8 also computed coherence the circuits' way (Welch). %s" % welch)
    w("  These files are Dickson only.")
    w("")
    w("THE SAME NUMBERS WITHOUT JARVIS")
    w("  joe_standalone.py (numpy and scipy only, on the tab) reads the recordings itself and")
    w("  writes every value again; tab 8 compares the two cell by cell.")
    return "\r\n".join(L) + "\r\n"


def welch_note(out):
    """Whether Welch lights the same comparisons Dickson does, in words, and
    the counts."""
    same = total = 0
    differ = []
    for res in out["results"]:
        if res["method"] != SHOWN or res["band"] is None:
            continue
        mdl = MODEL_BY_ID[res["model"]]
        if mdl[5] != "pair" or not res.get("mixed", {}).get("ok"):
            continue
        other = next((x for x in out["results"] if x["model"] == res["model"] and x["band"] == res["band"] and x["method"] == "welch"), None)
        if not other or not other.get("mixed", {}).get("ok"):
            continue
        total += 1
        if _lit(res) == _lit(other):
            same += 1
        else:
            differ.append("comparison %d (%s), %s: %s" % (NAMES[res["model"]][0], ascii_(NAMES[res["model"]][1]), res["band"],
                                                          "Welch changed, Dickson did not" if _lit(other) else "Dickson changed, Welch did not"))
    say = ("It gives the same answer in all %d comparisons and bands." % total) if not differ else (
        "It gives the same answer in %d of %d comparisons and bands. It differs in %s." % (same, total, "; ".join(differ)))
    return {"same": same, "total": total, "differ": differ, "say": say}


def write_exports(out, into):
    """The SPSS package, and the files the standalone script is checked
    against.

    into/compare/<id>_<band>_<method>.csv: every result, both methods, wide
    (the script writes the same; agreement() compares them).
    into/joe_tab8_spss.zip, unzipping to joe_tab8_spss/: a README, a results
    summary, then three folders -- the main comparisons, the checks, and,
    for each result that changed, the files that recreate it -- each a long
    .csv and its .sps, named by the comparison's number and name. Dickson
    only (Welch is said in words). The README and the summary also sit
    beside the zip, to read without unzipping."""
    import shutil
    import zipfile
    os.makedirs(into, exist_ok=True)
    for f in os.listdir(into):
        pth = os.path.join(into, f)
        if os.path.isfile(pth) and os.path.splitext(f)[1] in (".csv", ".sps", ".txt", ".zip", ".tmp"):
            os.remove(pth)
    cmp_dir = os.path.join(into, "compare")
    shutil.rmtree(cmp_dir, ignore_errors=True)
    os.makedirs(cmp_dir)
    for res in out["results"]:
        if not res.get("units"):
            continue
        mdl = MODEL_BY_ID[res["model"]]
        cols, rows = wide_rows(res, mdl)
        with open(os.path.join(cmp_dir, compare_name(res) + ".csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(["rat"] + [c[3] for c in cols]) + "\n")
            for r in rows:
                fh.write(",".join(str(x) for x in r) + "\n")
    welch = welch_note(out)
    files = {}                                     # path in the package -> text
    summary = []
    positive = []
    root = "joe_tab8_spss/"
    for mdl in MODELS:
        for band in [b for b, _lo, _hi in BANDS]:
            method = SHOWN if mdl[5] == "pair" else "welch"
            res = next((x for x in out["results"] if x["model"] == mdl[0] and x["band"] == band and x["method"] == method), None)
            no, title, _what = NAMES[mdl[0]]
            if not res or not res.get("units") or not res.get("mixed", {}).get("ok"):
                summary.append([no, ascii_(title), mdl[2], band, "not fitted"] + [""] * 14)
                continue
            folder = MAIN_DIR if mdl[2] == "first" else CHECK_DIR
            name = "%s - %s" % (stem(mdl[0]), band)
            f = mdl[3].lower()
            u = "pair" if mdl[5] == "pair" else "region"
            val = "power" if mdl[5] == "region" else "coherence"
            files[root + folder + "/" + name + ".csv"] = _csv(
                ["rat", "day", f, u, val, "day_name", f + "_name", u + "_name"], long_rows(res, mdl))
            files[root + folder + "/" + name + ".sps"] = main_sps(res, mdl, name + ".csv", folder)
            t2, t3 = _terms(res, mdl)
            s2, s3 = _say(mdl, res)
            other = next((x for x in out["results"] if x["model"] == mdl[0] and x["band"] == band and x["method"] == "welch"), None) \
                if mdl[5] == "pair" else None
            agrees = "-" if other is None or not other.get("mixed", {}).get("ok") else ("yes" if _lit(other) == _lit(res) else "no")
            row = [no, ascii_(title), "main" if mdl[2] == "first" else "check", band, "yes" if _lit(res) else "no",
                   s2.split(": ")[1]] + (["%.3f" % t2["F"], t2["df1"], t2["df2"], "%.4f" % t2["p"]] if t2 else ["", "", "", ""]) + \
                [s3.split(": ")[1]] + (["%.3f" % t3["F"], t3["df1"], t3["df2"], "%.4f" % t3["p"]] if t3 else ["", "", "", ""]) + \
                [agrees, len(res.get("rats") or []), len(res["units"]), folder + "\\" + name + ".sps"]
            summary.append(row)
            if _lit(res) and mdl[2] == "first" and len(mdl[4]) == 2:
                rn = "%s - %s - per rat and %s" % (stem(mdl[0]), band, u)
                tab = {r: per for r, per in res["table"].items()}
                allu = res["all_units"]
                keep = [allu.index(x) for x in res["units"]]
                tabn = {r: {d: {lv: np.array([np.nan if x is None else x for x in per[d][lv]]) for lv, _l in mdl[4]}
                            for d in TESTED} for r, per in tab.items()}
                crow = [(r, keep.index(ui) + 1, ascii_(un), a, b, c, d, dif)
                        for r, ui, un, a, b, c, d, dif in contrast_rows(tabn, mdl, keep, allu)]
                (la, _a), (lb, _b) = mdl[4]
                files[root + REDO_DIR + "/" + rn + ".csv"] = _csv(
                    ["rat", u, u + "_name", "p1_" + la, "p1_" + lb, "p4_" + la, "p4_" + lb, "difference"], crow)
                files[root + REDO_DIR + "/" + "%s - %s - recreate.sps" % (stem(mdl[0]), band)] = recreate_sps(res, mdl, rn + ".csv", REDO_DIR)
                positive.append({"model": mdl[0], "band": band, "no": no, "title": title,
                                 "two_say": "%s (%s)" % (_fp(t2), s2.split(": ")[1]),
                                 "three_say": "%s (%s)" % (_fp(t3), s3.split(": ")[1]),
                                 "quick": res.get("quick"), "two": t2, "three": t3,
                                 "files": [REDO_DIR + "/" + rn + ".csv", REDO_DIR + "/" + "%s - %s - recreate.sps" % (stem(mdl[0]), band)]})
    head = ["number", "comparison", "kind", "band", "changed", "all together", "F", "df1", "df2", "p",
            "one by one", "F", "df1", "df2", "p", "Welch agrees", "rats", "pairs or regions", "syntax"]
    summary_text = _csv(head, summary)
    readme = readme_text(out, positive, welch["say"], summary)
    files[root + "README.txt"] = readme
    files[root + "Results summary.csv"] = summary_text
    zpath = os.path.join(into, ZIP_NAME)
    with zipfile.ZipFile(zpath + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
        for pth in sorted(files):
            z.writestr(pth, ("\ufeff" if pth.endswith(".sps") else "") + files[pth])
    os.replace(zpath + ".tmp", zpath)
    with open(os.path.join(into, README_NAME), "w", encoding="utf-8", newline="") as fh:
        fh.write(readme)
    with open(os.path.join(into, SUMMARY_NAME), "w", encoding="utf-8", newline="") as fh:
        fh.write(summary_text)
    return {"downloads": [ZIP_NAME, README_NAME, SUMMARY_NAME], "tree": sorted(p_[len(root):] for p_ in files),
            "positive": positive, "welch": welch}


# --------------------------------------------------------------------------
# The work: every rat-day (cached), then the models, then the exports
# --------------------------------------------------------------------------
def _root():
    from . import monolith as MO
    return MO._path("joe")


def joe_dir(*parts):
    return os.path.join(_root(), *parts)


def _day_path(d, key):
    return joe_dir("days", "r%d_%s_%s.npz" % (int(d["rat"]), d["day"], key))


def _compute_one(d, names, chan_map, path):
    """In a worker process: one rat-day, computed and written."""
    arrs, fp, meta = day_compute(d, names, chan_map)
    save_day(path, arrs, fp, meta)
    return {"rat": d["rat"], "day": d["day"], "seconds": meta["seconds"], "notes": meta["notes"]}


def inputs_of(man, names, chan_map):
    """What the standalone script needs that is a decision, not data: which
    folders, which trials were kept, which wires are marked bad, which
    regions histology rules out, what each rat heard, and the seed. Plain
    JSON a person can read."""
    days = []
    for d in man.get("days") or []:
        days.append({
            "rat": int(d["rat"]), "day": d["day"],
            "folders": [[f["role"], f.get("local")] for f in d.get("folders") or []],
            "bad": [int(c) for c in d.get("bad") or []],
            "blocked": sorted((d.get("blocked") or {}).keys()),
            "trials": [{"id": u["id"], "opener_t": u["pair"]["opener_t"], "closer_t": u["pair"]["closer_t"],
                        "offset_t": u["pair"]["offset_t"], "cue_type": u.get("cue_type"),
                        "manual": u.get("manual") or {}} for u in d.get("units") or []],
        })
    return {
        "about": "Inputs for tools/joe_standalone.py: the decisions behind tab 8 (which trials, wires and regions), "
                 "not its numbers. The script reads the recordings and works out everything else itself.",
        "schema": SCHEMA, "regions": list(names), "channels": {k: list(v) for k, v in chan_map.items()},
        "identity": {str(r): ratidentity.identity(r) for r in sorted({int(d["rat"]) for d in man.get("days") or []})},
        "bands": [list(b) for b in BANDS], "skip_hz": list(SKIP_HZ), "fp": {"seed": FP_SEED, "lengths": list(FP_LENGTHS),
                                                                          "edge_s": FP_EDGE_S},
        "min_rats": MIN_RATS, "days": days,
    }


def joe_work(worker, workers=None):
    """Tab 8, here: each rat-day measured (once; cached by what it depends
    on), then the models, their gates, post hocs and follow-ups, then the
    SPSS files and the standalone script's inputs."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from . import monolith as MO
    man = MO.manifest()
    if not man:
        raise JoeError("There is no Monolith manifest yet: Drift → Monolith makes it.", 409)
    names = list(man.get("regions") or sweep.regions())
    chan_map = {k: v for k, v in coupling.dewey_map().items() if k in names}
    os.makedirs(joe_dir("days"), exist_ok=True)
    todo, have = [], {}
    for d in man.get("days") or []:
        if d["day"] not in DAYS:
            continue
        p = _day_path(d, day_key(d, names))
        if os.path.isfile(p):
            have[(int(d["rat"]), d["day"])] = p
        else:
            todo.append((d, p))
    worker.note(phase="joe", item="measuring %d rat-days (%d already done)" % (len(todo), len(have)), i=0, of=len(todo))
    notes = []
    if todo:
        n = workers or max(1, min(4, (os.cpu_count() or 2) - 1))
        with ProcessPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(_compute_one, d, names, chan_map, p): (d, p) for d, p in todo}
            done = 0
            try:
                for f in as_completed(futs):
                    worker.check()
                    d, p = futs[f]
                    try:
                        got = f.result()
                        notes += got["notes"]
                        have[(int(d["rat"]), d["day"])] = p
                    except Exception as exc:                 # noqa: BLE001
                        notes.append("r%d %s: not measured (%s)" % (d["rat"], d["day"], exc))
                    done += 1
                    worker.note(phase="joe", i=done, of=len(todo),
                                item="measured r%d %s (%d of %d)" % (d["rat"], d["day"], done, len(todo)))
            except BaseException:
                for f in futs:
                    f.cancel()
                raise
    worker.check()
    # Day files made for anything else (an older schema, trials changed
    # since) are never read again.
    keep = {os.path.basename(p) for p in have.values()}
    for f in os.listdir(joe_dir("days")):
        if f.endswith(".npz") and f not in keep:
            try:
                os.remove(joe_dir("days", f))
            except OSError:
                pass
    day_data = {}
    for (rat, day), p in sorted(have.items()):
        arrs, fp, meta = load_day(p)
        day_data[(rat, day)] = (arrs, fp, meta)
        notes += [x for x in meta.get("notes") or [] if x not in notes]
    out = build(day_data, names, progress=lambda i, of, item: worker.note(phase="joe-models", i=i, of=of, item=item),
                check=worker.check)
    out["rats"] = sorted({r for r, _d in day_data})
    out["n_days"] = len(day_data)
    out["notes"] = notes
    out["histology"] = man.get("histology")
    out["trial_counts"] = {"r%d %s" % k: len(v[2]["trials"]) for k, v in day_data.items()}
    got = write_exports(out, joe_dir("export"))
    out["exports"] = got["downloads"]
    out["spss"] = got
    # The per-rat tables are in the exports; the page needs the cells, the
    # post hocs and the follow-ups, not every number again.
    for res in out["results"]:
        res.pop("table", None)
        res.pop("all_units", None)
    with open(joe_dir("joe_inputs.json"), "w", encoding="utf-8") as fh:
        json.dump(inputs_of(man, names, chan_map), fh, indent=1, default=str)
    agree = agreement()
    if agree:
        out["agreement"] = agree
    _write(joe_dir("joe.json"), out)
    return {"models": len(out["results"]), "rat_days": len(day_data)}


def work_safe(worker):
    """`joe_work` for the Monolith's work runner, its refusals said as the
    runner says them."""
    from . import monolith as MO
    try:
        return joe_work(worker)
    except JoeError as exc:
        raise MO.MonolithError(str(exc), exc.status)


def script_safe(worker):
    from . import monolith as MO
    try:
        return script_work(worker)
    except JoeError as exc:
        raise MO.MonolithError(str(exc), exc.status)


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_clean(obj), fh, default=_jsonable, allow_nan=False)
    os.replace(tmp, path)


def _jsonable(o):
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _clean(obj):
    """NaN and inf to None, all the way down, so the JSON is JSON."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def result():
    """tab 8's numbers, or None."""
    p = joe_dir("joe.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# The standalone script, checked against this
# --------------------------------------------------------------------------
def script_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "joe_standalone.py")


def agreement(tol=1e-6):
    """The standalone script's CSVs (joe_dir("script")) against this
    module's (joe_dir("export")), cell by cell: None when the script has
    not been run."""
    sd, ed = joe_dir("script"), joe_dir("export", "compare")
    if not os.path.isdir(sd):
        return None
    files = sorted(f for f in os.listdir(ed) if f.endswith(".csv")) if os.path.isdir(ed) else []
    rows = []
    for f in files:
        a, b = os.path.join(ed, f), os.path.join(sd, f)
        if not os.path.isfile(b):
            rows.append({"file": f, "ok": False, "why": "the script did not write it"})
            continue
        ra = [l.rstrip("\n").split(",") for l in open(a, encoding="utf-8")]
        rb = [l.rstrip("\n").split(",") for l in open(b, encoding="utf-8")]
        if ra[0] != rb[0]:
            rows.append({"file": f, "ok": False, "why": "the columns differ"})
            continue
        ib = {r[0]: r for r in rb[1:]}
        n = worst = 0
        miss = 0
        for r in ra[1:]:
            o = ib.get(r[0])
            if o is None:
                miss += 1
                continue
            for x, y in zip(r[1:], o[1:]):
                n += 1
                fx, fy = float(x), float(y)
                if (fx == MISSING) != (fy == MISSING):
                    miss += 1
                    continue
                if fx != MISSING:
                    worst = max(worst, abs(fx - fy))
        rows.append({"file": f, "ok": miss == 0 and worst <= tol, "cells": n, "worst": worst, "missing_differs": miss})
    st = os.path.getmtime(sd)
    return {"files": rows, "ok": bool(rows) and all(r["ok"] for r in rows), "tol": tol,
            "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st))}


def script_work(worker):
    """Run the standalone script here, on the same recordings, into
    joe_dir("script"), and compare."""
    import subprocess
    import sys
    inp = joe_dir("joe_inputs.json")
    if not os.path.isfile(inp):
        raise JoeError("Work tab 8 out first: the script reads the inputs it writes.", 409)
    out = joe_dir("script")
    os.makedirs(out, exist_ok=True)
    worker.note(phase="joe-script", item="running tools/joe_standalone.py")
    log = open(joe_dir("script.log"), "w", encoding="utf-8")
    try:
        p = subprocess.Popen([sys.executable, script_path(), "--inputs", inp, "--out", out, "--jobs", "4"],
                             stdout=log, stderr=subprocess.STDOUT)
        while p.poll() is None:
            if worker.stopping():
                p.kill()
                raise JoeError("Stopped.", 409)
            time.sleep(1.0)
    finally:
        log.close()
    if p.returncode != 0:
        raise JoeError("The script stopped with an error; its log is %s." % joe_dir("script.log"), 500)
    agree = agreement()
    got = result()
    if got is not None:
        got["agreement"] = agree
        _write(joe_dir("joe.json"), got)
    return agree
