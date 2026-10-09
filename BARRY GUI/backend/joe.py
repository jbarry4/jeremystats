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
SCHEMA = 2

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


def fit_mixed(df, factor, unit):
    """value ~ Day x factor x unit, the rat a random intercept, with rat x
    day, rat x level and rat x day x level as variance components (the
    repeated-measures error strata). Wald tests per term, as F with
    between-within denominator df; SPSS MIXED (Satterthwaite) is the
    reference, from the exported syntax."""
    import warnings
    import statsmodels.formula.api as smf
    from scipy.stats import f as fdist
    N = df["rat"].nunique()
    L = df["level"].nunique()
    if N < MIN_RATS or df["unit"].nunique() < 1:
        return {"ok": False, "why": "fewer than %d rats" % MIN_RATS}
    formula = "value ~ C(day, Sum) * C(level, Sum)" + (" * C(unit, Sum)" if df["unit"].nunique() > 1 else "")
    vc = {"day": "0 + C(day)", "level": "0 + C(level)", "dl": "0 + C(day):C(level)"}
    res, how = None, "random intercept + rat × day, rat × %s, rat × day × %s" % (factor.lower(), factor.lower())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for attempt in ("vc", "plain"):
            try:
                if attempt == "vc":
                    md = smf.mixedlm(formula, df, groups=df["rat"], re_formula="1", vc_formula=vc)
                else:
                    md = smf.mixedlm(formula, df, groups=df["rat"])
                    how = "random intercept only (the fuller model did not converge)"
                r = md.fit(reml=True, method=["lbfgs"])
                if r.converged or attempt == "plain":
                    res = r
                    break
            except Exception as exc:                     # noqa: BLE001
                why = str(exc)
                continue
    if res is None:
        return {"ok": False, "why": "the mixed model did not fit"}
    w = res.wald_test_terms(skip_single=False, scalar=True).summary_frame()
    n_obs = int(res.nobs)
    k_fe = int(res.k_fe)
    df_res = max(1, n_obs - k_fe - N * (3 + 3 * L))
    terms = {}
    for name, row in w.iterrows():
        if name == "Intercept":
            continue
        df1 = int(row["df constraint"])
        chi2 = float(row["chi2"])
        if name == "C(day, Sum)":
            df2 = N - 1
        elif name in ("C(level, Sum)", "C(day, Sum):C(level, Sum)"):
            df2 = (N - 1) * (L - 1)
        else:
            df2 = df_res
        F = chi2 / df1
        terms[_term(name, factor, unit)] = {"F": F, "df1": df1, "df2": int(df2),
                                            "p": float(fdist.sf(F, df1, df2)), "chi2": chi2}
    return {"ok": True, "terms": terms, "n_rats": N, "n_obs": n_obs, "random": how}


def fit_rm(df, factor, unit, n_units):
    """The repeated-measures ANOVA SPSS's GLM would run: only the rats with
    every cell."""
    import warnings
    from statsmodels.stats.anova import AnovaRM
    L = df["level"].nunique()
    cells = 2 * L * n_units
    have = df.groupby("rat").size()
    full = [r for r, n in have.items() if n == cells]
    out = {"n_rats": len(full), "of": int(df["rat"].nunique()), "cells": cells}
    if len(full) < 3:
        out.update(ok=False, why="only %d rat%s every cell; SPSS's GLM would drop the rest"
                   % (len(full), " has" if len(full) == 1 else "s have"))
        return out
    within = ["day", "level"] + (["unit"] if n_units > 1 else [])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            t = AnovaRM(df[df["rat"].isin(full)], "value", "rat", within=within).fit().anova_table
        except Exception as exc:                         # noqa: BLE001
            out.update(ok=False, why=str(exc))
            return out
    names = {"day": "C(day, Sum)", "level": "C(level, Sum)", "unit": "C(unit, Sum)"}
    terms = {}
    for name, row in t.iterrows():
        key = ":".join(names[p] for p in name.split(":"))
        terms[_term(key, factor, unit)] = {"F": float(row["F Value"]), "df1": int(row["Num DF"]),
                                           "df2": int(row["Den DF"]), "p": float(row["Pr > F"])}
    out.update(ok=True, terms=terms)
    return out


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
                       rm={"ok": False}, gate={"passed": False}, cells=cells(tab_all, mdl, keep), post=[])
            results.append(res)
            continue
        df = _frame(tab, mdl, keep, units)
        res["mixed"] = fit_mixed(df, mdl[3], mdl[5])
        res["rm"] = fit_rm(df, mdl[3], mdl[5], len(keep))
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
                        "levels": [{"id": a, "label": b} for a, b in m[4]], "unit": m[5]} for m in MODELS],
            "days": list(DAYS), "tested": list(TESTED), "min_rats": MIN_RATS, "alpha": ALPHA,
            "skip_hz": list(SKIP_HZ), "fp": {"seed": FP_SEED, "lengths": list(FP_LENGTHS), "edge_s": FP_EDGE_S},
            "results": results, "follow_say": FOLLOW_SAY}


# --------------------------------------------------------------------------
# Exports: SPSS-ready
# --------------------------------------------------------------------------
MISSING = 999


def export_name(res):
    return "%s_%s_%s" % (res["model"], res["band"], res["method"])


def wide_rows(res, mdl):
    """Header and rows of the wide file: one row per rat, one column per
    Day x level x unit (day-major, unit fastest: SPSS's WSFACTOR order)."""
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


def sps_text(res, mdl, csv_name):
    cols, _rows = wide_rows(res, mdl)
    L = len(mdl[4])
    K = len(res["units"])
    names = [c[3] for c in cols]
    unit_word = "pair" if mdl[5] == "pair" else "region"
    factor = mdl[3].lower()
    lines = ["* Tab 8 · Joe's data: %s, %s, %s." % (mdl[1], BAND_SAY[res["band"]], METHOD_SAY.get(res["method"], res["method"])),
             "* Written by Jarvis (backend/joe.py). %s = missing." % MISSING,
             "* Within-subject order: day (Precon1, Precon4), then %s (%s), then %s (%d)."
             % (factor, ", ".join(l for _i, l in mdl[4]), unit_word, K),
             "",
             "GET DATA /TYPE=TXT /FILE='%s' /ENCODING='UTF8' /DELCASE=LINE /DELIMITERS=','"
             " /ARRANGEMENT=DELIMITED /FIRSTCASE=2 /VARIABLES=" % csv_name,
             "  rat F4.0"]
    lines += ["  %s F12.8" % n for n in names]
    lines[-1] += "."
    lines += ["MISSING VALUES %s TO %s (%d)." % (names[0], names[-1], MISSING), "VARIABLE LABELS rat 'Rat'"]
    for d, lv, u, n in cols:
        lab = "%s · %s · %s" % (d, dict(mdl[4])[lv], u)
        lines.append("  /%s '%s'" % (n, lab.replace("'", "''")))
    lines[-1] += "."
    lines += ["", "* The repeated-measures GLM: a rat missing any cell is left out entirely.",
              "GLM %s TO %s" % (names[0], names[-1]),
              "  /WSFACTOR=day 2 Polynomial %s %d Polynomial%s" % (factor, L, (" %s %d Polynomial" % (unit_word, K)) if K > 1 else ""),
              "  /METHOD=SSTYPE(3)",
              "  /PRINT=DESCRIPTIVE ETASQ",
              "  /WSDESIGN=day %s%s." % (factor, (" %s day*%s day*%s %s*%s day*%s*%s" % (unit_word, factor, unit_word, factor,
                                                                                         unit_word, factor, unit_word)) if K > 1
                                         else " day*%s" % factor),
              "",
              "* The mixed model: every rat, every cell it has.",
              "VARSTOCASES /MAKE value FROM %s TO %s /INDEX=cell(%d) /KEEP=rat /NULL=DROP." % (names[0], names[-1], len(names)),
              "COMPUTE day = TRUNC((cell - 1) / %d) + 1." % (L * K),
              "COMPUTE %s = MOD(TRUNC((cell - 1) / %d), %d) + 1." % (factor, K, L),
              "COMPUTE %s = MOD(cell - 1, %d) + 1." % (unit_word, K),
              "VALUE LABELS day 1 'Precon1' 2 'Precon4' /%s %s /%s %s." % (
                  factor, " ".join("%d '%s'" % (i + 1, l.replace("'", "''")) for i, (_x, l) in enumerate(mdl[4])),
                  unit_word, " ".join("%d '%s'" % (i + 1, u.replace("'", "''")) for i, u in enumerate(res["units"]))),
              "MISSING VALUES value (%d)." % MISSING,
              "MIXED value BY day %s %s" % (factor, unit_word if K > 1 else ""),
              "  /FIXED=day %s %s day*%s%s | SSTYPE(3)" % (factor, unit_word if K > 1 else "", factor,
                                                         (" day*%s %s*%s day*%s*%s" % (unit_word, factor, unit_word, factor, unit_word)) if K > 1 else ""),
              "  /RANDOM=INTERCEPT day %s day*%s | SUBJECT(rat) COVTYPE(VC)" % (factor, factor),
              "  /METHOD=REML",
              "  /CRITERIA=DFMETHOD(SATTERTHWAITE)",
              "  /PRINT=SOLUTION TESTCOV.", ""]
    return "\n".join(lines)


def write_exports(out, into):
    """Every model's wide .csv and .sps, and a zip of them all."""
    import zipfile
    os.makedirs(into, exist_ok=True)
    files = []
    for res in out["results"]:
        if not res.get("units"):
            continue
        mdl = MODEL_BY_ID[res["model"]]
        name = export_name(res)
        cols, rows = wide_rows(res, mdl)
        csv_path = os.path.join(into, name + ".csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(["rat"] + [c[3] for c in cols]) + "\n")
            for r in rows:
                fh.write(",".join(str(x) for x in r) + "\n")
        with open(os.path.join(into, name + ".sps"), "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(sps_text(res, mdl, name + ".csv"))
        files += [name + ".csv", name + ".sps"]
    zpath = os.path.join(into, "joe_tab8_spss.zip")
    with zipfile.ZipFile(zpath + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(into, f), f)
    os.replace(zpath + ".tmp", zpath)
    return files


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
    files = write_exports(out, joe_dir("export"))
    out["exports"] = files
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
    sd, ed = joe_dir("script"), joe_dir("export")
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
        p = subprocess.Popen([sys.executable, script_path(), "--inputs", inp, "--out", out],
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
