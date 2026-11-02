"""
evenmore.py -- the Monolith page's eleventh tab: Narrowing down (even more).

Dickson et al. 2022 (eNeuro 9(2), Figure 3), done on our rats, as the lab's
Coherence Analysis Plan (draft of 2026-10-27) lays it out, taken as
guidance and not as the gospel (Shahriar, 2026-10-28):

  * Ten region pairs, the plan's: RSC, dHC, ACC, OFC and PER, each with
    each (POR is out: no probe reached it). Bilateral: within a rat, a
    region pair is the mean of its valid wire pairs, the same side (ipsi:
    L-L, R-R) and across (contra: L-R, R-L) alike, each counting the same.
    A wire pair is valid when histology v2 scored both its probes "y".
    Homotopic pairs (left RSC with right RSC) are never used.
  * Early is Precon1, Late is Precon4. The window is each trial's cue pair
    (cue 1 + cue 2, 20 s).
  * POOLED SPECTRA (the user's choice, to be flagged hard wherever it
    shows): within a rat-day, every 1 s segment of every trial's window
    goes into ONE cross-spectrum and ONE pair of auto-spectra, and the
    coherence is taken from those. That is not what Dickson did, nor tabs
    8 and 9, which take a coherence per trial and average the trials.
    Pooling removes the small-sample bias of a coherence from ~38 segments,
    and it asks for a phase relation that holds across trials; a pair
    whose lag wanders from trial to trial comes out lower than the mean of
    its trials. The mean of the trials is kept beside it, to say by how
    much.
  * Dickson's coherence: a 59-61 Hz band-stop, then mscohere's segments
    (MATLAB's hanning(1024), 512 overlap, an FFT of 2048, at 1 kHz), the
    wires tab 8 chose for each window of each trial.
  * Theta 5-12 Hz at the FFT's own 0.49 Hz bins (the paper's spacing);
    gamma 30-90 Hz in 2 Hz bins, the notch's own 59-61 Hz left out.

The statistics: a generalised estimating equation for every significance,
as the paper's (Gamma, log link, exchangeable working correlation, the rat
as the cluster). A test of one thing (one degree of freedom) uses the
robust sandwich errors with Mancl and DeRouen's small-sample correction.
A test of many things at once (Pair, Session x Pair, anything with
Frequency) cannot: robust errors from 8 rats have at most 8 dimensions, so
those tests use the model's own (naive) errors, and say so. Benjamini-
Hochberg across the ten pairs for each per-pair test. Every mean, violin
and spectrum on a figure is for looking at; the GEE decides.

Phase 1, for theta and for gamma: each pair alone (its ring, the violins of
its frequency bins, Early to Late, the spectra), then all ten on one
figure with the omnibus. Phase 2, the plan's section 5, matched row only
(every Precon trial is a matched pairing, A->B or C->D, pooled): cue 1
against cue 2, on Precon1 and on Precon4.

    evenmore.work(worker)   -> evenmore.json, the figures and the exports
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import time
import zipfile

import numpy as np

from . import coupling, joe, sweep

# 2: the final stage's measures (the 10 s baseline, each side's power, the
# cue pair's Granger matrices and PAC histograms), 2026-10-30.
SCHEMA = 2
FS = joe.FS
SEG = joe.DICKSON_SEG                      # 1024
STEP = SEG // 2
NFFT = 2 * SEG
KEEP_HZ = 95.0
FREQS_ALL = np.fft.rfftfreq(NFFT, 1.0 / FS)
NF = int(np.searchsorted(FREQS_ALL, KEEP_HZ, side="right"))
FREQS = FREQS_ALL[:NF]

#: The plan's five regions, in its order; the plan's ten pairs follow.
STRUCTS = (("RSC", "RSC"), ("DHC", "dHC"), ("ACC", "ACC"), ("OFC", "OFC"), ("PER", "PER"))
SIDES = ("Left", "Right")
SIDE_NAMES = tuple("%s %s" % (s, st) for st, _say in STRUCTS for s in SIDES)
PAIRS = tuple((i, j) for i in range(len(STRUCTS)) for j in range(i + 1, len(STRUCTS)))
PAIR_SAY = tuple("%s–%s" % (STRUCTS[i][1], STRUCTS[j][1]) for i, j in PAIRS)
#: A region pair's four wire pairs: (side of the first, side of the second, how).
COMBOS = (("Left", "Left", "ipsi"), ("Right", "Right", "ipsi"), ("Left", "Right", "contra"), ("Right", "Left", "contra"))
#: Okabe and Ito's eight, then two of them again, told apart by a dash-dot
#: line and a hollow marker (the user's pick, 2026-10-28).
OKABE = ("#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#000000")
COLORS = OKABE + ("#E69F00", "#56B4E9")
DASHED = (False,) * 8 + (True, True)

WINS = ("pair", "cue1", "cue2", "base10")
#: Granger: tab 8's settings (250 Hz, 1 s pieces, an FFT of twice that).
GC_SEG = int(round(joe.GC_FS))
GC_NFFT = 2 * GC_SEG
PAC_BINS = joe.PAC_BINS
DAYS = joe.TESTED
DAY_SAY = {"Precon1": "Early (Precon1)", "Precon4": "Late (Precon4)"}
BANDS = joe.BANDS
GAMMA_STEP = 2.0
MIN_RATS = joe.MIN_RATS
ALPHA = 0.05

ROBUST = "robust (Mancl–DeRouen)"
NAIVE = "model-based"

FLAG = ("Pooled spectra, not the mean of trials. Within each rat and day, every 1 s piece of every trial's window "
        "goes into one spectrum before the coherence is taken. Dickson et al. and tabs 8 and 9 take one coherence per "
        "trial and average them. Pooling is less biased, but it only gives a high value when the phase relation holds "
        "across trials. The mean of the trials is shown beside it.")


class EvenMoreError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _root(*parts):
    from . import monolith as MO
    return MO._path("evenmore", *parts)


def figs_dir(*parts):
    return _root("figs", *parts)


def export_dir(*parts):
    return _root("export", *parts)


# --------------------------------------------------------------------------
# One rat-day: the pooled spectra
# --------------------------------------------------------------------------
def _spectra_of(sigs):
    """Each row's segments' Fourier transforms, Dickson's way: (R, K, NF)
    complex, or None where a row is missing. `sigs` one per side name."""
    ok = [s is not None and np.asarray(s).size >= SEG for s in sigs]
    if not any(ok):
        return [None] * len(sigs)
    n = min(np.asarray(s).size for s, k in zip(sigs, ok) if k)
    win = coupling.matlab_hanning(SEG)
    out = []
    for s, k in zip(sigs, ok):
        if not k:
            out.append(None)
            continue
        x = np.asarray(s, dtype=np.float64)[:n]
        if not np.all(np.isfinite(x)) or x.std() <= 0:
            out.append(None)
            continue
        segs = sweep._segments(joe.dickson_notch(x)[None, :], SEG, STEP)
        if segs is None:
            out.append(None)
            continue
        out.append(np.fft.rfft(segs[0] * win, n=NFFT, axis=1)[:, :NF])
    return out


def wire_pairs():
    """[(pair index, combo index, side name a, side name b)], all forty."""
    out = []
    for p, (i, j) in enumerate(PAIRS):
        for c, (sa, sb, _how) in enumerate(COMBOS):
            out.append((p, c, "%s %s" % (sa, STRUCTS[i][0]), "%s %s" % (sb, STRUCTS[j][0])))
    return out


def day_compute(d, chan_map, joe_path):
    """One rat-day: for each window (the cue pair, cue 1, cue 2) and each of
    the forty wire pairs, the cross-spectrum and both auto-spectra summed
    over every segment of every trial, the number of segments, and each
    trial's own band coherence (for the mean of trials). The wires are the
    ones tab 8 chose for that window of that trial."""
    t0 = time.time()
    arrs, _fp, meta = joe.load_day(joe_path)
    names = meta["regions"]
    wires = arrs["wires"]
    ri = {nm: names.index(nm) for nm in SIDE_NAMES}
    wi8 = {w: joe.WINDOWS.index(w) for w in WINS}
    folder = next((f.get("local") for f in d.get("folders") or [] if f.get("role") == "SPC"), None)
    if not folder or not os.path.isdir(folder):
        raise EvenMoreError("r%d %s: its SPC folder cannot be opened here." % (d["rat"], d["day"]), 409)
    units = list(d.get("units") or [])
    if [u["id"] for u in units] != [t["id"] for t in meta["trials"]]:
        raise EvenMoreError("r%d %s: its trials changed since tab 8 was worked out; work tab 8 out again." % (d["rat"], d["day"]), 409)
    cm = {nm: list(chan_map[nm]) for nm in SIDE_NAMES}
    blocked = {k: v for k, v in (d.get("blocked") or {}).items() if k in cm}
    WP = wire_pairs()
    W, P, C, T = len(WINS), len(PAIRS), len(COMBOS), len(units)
    S = len(SIDE_NAMES)
    sab = np.zeros((W, P, C, NF), np.complex128)
    saa = np.zeros((W, P, C, NF))
    sbb = np.zeros((W, P, C, NF))
    nseg = np.zeros((W, P, C), np.int32)
    tband = np.full((W, T, P, C, len(BANDS)), np.nan)
    # the final stage (2026-10-30): each side's own pooled spectrum (power),
    # the cue pair's 250 Hz cross-spectral matrices (Granger) and each
    # side's theta-phase / gamma-amplitude histogram (PAC)
    psd = np.zeros((W, S, NF))
    pseg = np.zeros((W, S), np.int32)
    gS = np.zeros((P, C, GC_NFFT, 2, 2), np.complex128)
    gseg = np.zeros((P, C), np.int32)
    pac_sum = np.zeros((S, PAC_BINS))
    pac_n = np.zeros((S, PAC_BINS))
    masks = [joe.band_mask(FREQS, lo, hi) for _b, lo, hi in BANDS]
    notes = []
    for ui, u in enumerate(units):
        wins = [w for w in joe.trial_windows(u["pair"]) if w[0] in WINS]
        drop = {}
        for wn, _a, _b in wins:
            out = set()
            for nm in SIDE_NAMES:
                wire = int(wires[wi8[wn], ui, ri[nm]])
                out |= set(cm[nm]) - ({wire} if wire >= 0 else set())
            drop[wn] = sorted(out)
        try:
            got = coupling._signals_for_windows(folder, cm, wins, drop, FS, blocked=blocked)
        except coupling.CouplingError as exc:
            notes.append("r%d %s %s: %s" % (d["rat"], d["day"], u["id"], exc))
            continue
        for wn, _a, _b in wins:
            w = WINS.index(wn)
            reg = got[wn]["regions"]
            sigs = []
            for nm in SIDE_NAMES:
                r = reg.get(nm) or {}
                want = int(wires[wi8[wn], ui, ri[nm]])
                if r.get("usable") and want >= 0:
                    if int(r.get("channel", -1)) != want:
                        notes.append("r%d %s %s %s: read CSC%s, tab 8 used CSC%d" % (d["rat"], d["day"], u["id"], nm, r.get("channel"), want))
                    sigs.append(r["signal"])
                else:
                    sigs.append(None)
            F = dict(zip(SIDE_NAMES, _spectra_of(sigs)))
            for si, nm in enumerate(SIDE_NAMES):
                if F[nm] is not None:
                    psd[w, si] += (np.abs(F[nm]) ** 2).sum(axis=0)
                    pseg[w, si] += F[nm].shape[0]
            if wn == "pair":
                G = dict(zip(SIDE_NAMES, _gc_spectra_of(sigs)))
                for p, c, a, b in WP:
                    if G[a] is None or G[b] is None:
                        continue
                    k = min(G[a].shape[0], G[b].shape[0])
                    Ga, Gb = G[a][:k], G[b][:k]
                    gS[p, c, :, 0, 0] += (np.abs(Ga) ** 2).sum(axis=0)
                    gS[p, c, :, 1, 1] += (np.abs(Gb) ** 2).sum(axis=0)
                    cr = (Ga * np.conj(Gb)).sum(axis=0)
                    gS[p, c, :, 0, 1] += cr
                    gS[p, c, :, 1, 0] += np.conj(cr)
                    gseg[p, c] += k
                for si, x in enumerate(sigs):
                    got_pac = _pac_hist(x)
                    if got_pac is not None:
                        pac_sum[si] += got_pac[0]
                        pac_n[si] += got_pac[1]
            for p, c, a, b in WP:
                Fa, Fb = F[a], F[b]
                if Fa is None or Fb is None:
                    continue
                cross = (Fa * np.conj(Fb)).sum(axis=0)
                pa = (np.abs(Fa) ** 2).sum(axis=0)
                pb = (np.abs(Fb) ** 2).sum(axis=0)
                sab[w, p, c] += cross
                saa[w, p, c] += pa
                sbb[w, p, c] += pb
                nseg[w, p, c] += Fa.shape[0]
                with np.errstate(invalid="ignore", divide="ignore"):
                    coh = np.abs(cross) ** 2 / (pa * pb)
                for bi, m in enumerate(masks):
                    tband[w, ui, p, c, bi] = float(np.mean(coh[m]))
    meta_out = {"schema": SCHEMA, "rat": int(d["rat"]), "day": d["day"], "trials": [u["id"] for u in units],
                "notes": notes, "seconds": round(time.time() - t0, 1), "nf": NF}
    return {"sab": sab, "saa": saa, "sbb": sbb, "nseg": nseg, "tband": tband, "psd": psd, "pseg": pseg,
            "gS": gS, "gseg": gseg, "pac_sum": pac_sum, "pac_n": pac_n}, meta_out


def _gc_spectra_of(sigs):
    """Each row at 250 Hz (after Dickson's notch), cut into 1 s pieces half
    overlapping, each piece's mean removed, MATLAB's hanning, the full FFT
    of twice its length: what tab 8's Granger uses, kept per piece so the
    pieces of every trial can be pooled. (K, GC_NFFT) complex or None."""
    out = []
    win = coupling.matlab_hanning(GC_SEG)
    for s in sigs:
        if s is None or np.asarray(s).size < SEG:
            out.append(None)
            continue
        x = np.asarray(s, dtype=np.float64)
        if not np.all(np.isfinite(x)) or x.std() <= 0:
            out.append(None)
            continue
        y = coupling.decimate_to(joe.dickson_notch(x), FS, joe.GC_FS)[0]
        segs = sweep._segments(y[None, :], GC_SEG, GC_SEG // 2)
        if segs is None:
            out.append(None)
            continue
        segs = segs[0] - segs[0].mean(axis=1, keepdims=True)
        out.append(np.fft.fft(segs * win, n=GC_NFFT, axis=1))
    return out


def _pac_hist(s):
    """One window's theta phase (5-12 Hz) against gamma amplitude (30-90
    Hz) in the same wire, as PAC_BINS sums of amplitude and counts, to be
    pooled over trials before Tort's MI is taken."""
    if s is None or np.asarray(s).size < SEG:
        return None
    x = joe.dickson_notch(np.asarray(s, dtype=np.float64))
    if not np.all(np.isfinite(x)) or x.std() <= 0:
        return None
    ph = np.angle(sweep.analytic(x, FS, 5.0, 12.0, pad=True))
    amp = np.abs(sweep.analytic(x, FS, 30.0, 90.0, pad=True))
    edges = np.linspace(-np.pi, np.pi, PAC_BINS + 1)
    idx = np.clip(np.digitize(ph, edges) - 1, 0, PAC_BINS - 1)
    return np.bincount(idx, weights=amp, minlength=PAC_BINS), np.bincount(idx, minlength=PAC_BINS).astype(float)


def day_key(d, joe_path):
    blob = json.dumps({"schema": SCHEMA, "joe": os.path.basename(joe_path), "seg": [SEG, STEP, NFFT, NF],
                       "sides": SIDE_NAMES}, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _day_path(d, key):
    return _root("days", "r%d_%s_%s.npz" % (int(d["rat"]), d["day"], key))


def save_day(path, arrs, meta):
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, meta=np.array(json.dumps(meta)), **arrs)
    os.replace(tmp, path)


def load_day(path):
    z = np.load(path, allow_pickle=False)
    return {k: z[k] for k in z.files if k != "meta"}, json.loads(str(z["meta"]))


def _compute_one(d, chan_map, joe_path, path):
    arrs, meta = day_compute(d, chan_map, joe_path)
    save_day(path, arrs, meta)
    return {"rat": meta["rat"], "day": meta["day"], "seconds": meta["seconds"], "notes": meta["notes"]}


# --------------------------------------------------------------------------
# From the pooled spectra to numbers
# --------------------------------------------------------------------------
def coherence(day, w):
    """(P, C, NF) coherence from one rat-day's pooled spectra in window `w`,
    NaN where the wire pair was never valid."""
    wi = WINS.index(w)
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.abs(day["sab"][wi]) ** 2 / (day["saa"][wi] * day["sbb"][wi])
    c[day["nseg"][wi] == 0] = np.nan
    return c


def _nanmean(x, axis):
    import warnings
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(x, axis=axis)


def rat_spectrum(day, w):
    """(P, NF): each region pair's coherence, the mean of its valid wire
    pairs (each counting the same)."""
    return _nanmean(coherence(day, w), axis=1)


def bins_of(band):
    """[(label Hz, mask over FREQS)]: theta at the FFT's own bins, gamma in
    2 Hz bins; the notch's bins never in either."""
    _b, lo, hi = next(b for b in BANDS if b[0] == band)
    m = joe.band_mask(FREQS, lo, hi)
    if band == "theta":
        return [(float(FREQS[k]), np.arange(NF) == k) for k in np.flatnonzero(m)]
    out = []
    edges = np.arange(lo, hi, GAMMA_STEP)
    for k, e in enumerate(edges):
        top = (FREQS <= hi + 1e-9) if k == len(edges) - 1 else (FREQS < e + GAMMA_STEP - 1e-9)
        mm = m & (FREQS >= e - 1e-9) & top
        if mm.any():
            out.append((float(e + GAMMA_STEP / 2), mm))
    return out


def band_value(spec, band):
    _b, lo, hi = next(b for b in BANDS if b[0] == band)
    return _nanmean(spec[..., joe.band_mask(FREQS, lo, hi)], axis=-1)


def bin_values(spec, band):
    return np.stack([_nanmean(spec[..., m], axis=-1) for _f, m in bins_of(band)], axis=-1)


def tables(days):
    """Everything the models and the figures read, from the loaded rat-days
    {(rat, day): (arrays, meta)}:

        band[w][band]  {(rat, day): (P,)}       band coherence
        bins[w][band]  {(rat, day): (P, nbins)}  per frequency bin
        trialmean[band] {(rat, day): (P,)}       the mean of trials, cue pair
        wires          {(rat, day): (P, C)}      valid wire pairs (segments > 0)
    """
    out = {"band": {w: {b[0]: {} for b in BANDS} for w in WINS}, "bins": {w: {b[0]: {} for b in BANDS} for w in WINS},
           "trialmean": {b[0]: {} for b in BANDS}, "wires": {}, "segments": {}}
    for k, (arrs, _meta) in sorted(days.items()):
        for w in WINS:
            spec = rat_spectrum(arrs, w)
            for bid, _lo, _hi in BANDS:
                out["band"][w][bid][k] = band_value(spec, bid)
                out["bins"][w][bid][k] = bin_values(spec, bid)
        out["wires"][k] = arrs["nseg"][0] > 0
        out["segments"][k] = arrs["nseg"][0]
        tb = arrs["tband"][0]                                   # (T, P, C, B): the cue pair
        for bi, (bid, _lo, _hi) in enumerate(BANDS):
            out["trialmean"][bid][k] = _nanmean(_nanmean(tb[..., bi], axis=0), axis=-1)
    return out


# --------------------------------------------------------------------------
# The GEE
# --------------------------------------------------------------------------
TERM_SAY = {"day": "Session", "pair": "Pair", "f": "Frequency", "cue": "Cue", "period": "Period", "dir": "Direction"}


def _term_say(name):
    parts = []
    for p in name.split(":"):
        v = p.split("(", 1)[-1].split(",", 1)[0].strip(") ")
        parts.append(TERM_SAY.get(v, v))
    return " × ".join(parts)


def _chi2_sf(x, k):
    from scipy.stats import chi2
    return float(chi2.sf(x, k))


def gee(df, formula, family="gamma"):
    """Gamma with a log link (coherence, Granger, MI) or normal with the
    identity (power in dB), exchangeable, the rat as the cluster. Returns
    the fit, or raises EvenMoreError with what went wrong."""
    import warnings
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    data = df.sort_values("rat", kind="stable").reset_index(drop=True)
    fam = sm.families.Gamma(sm.families.links.Log()) if family == "gamma" else sm.families.Gaussian()
    model = smf.gee(formula, groups="rat", data=data, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return model.fit(cov_type="bias_reduced", maxiter=200)
        except Exception as exc:                              # noqa: BLE001
            raise EvenMoreError("the GEE did not fit (%s: %s)" % (type(exc).__name__, exc), 500)


#: The most degrees of freedom a test may have and still use the robust
#: errors: a robust covariance from 8 rats has rank 7 at most, and is
#: poorly estimated well before that (2026-10-30: 2, so Session x Period
#: over three periods is robust).
ROBUST_MAX_DF = 2


def terms(res):
    """[{term, chi2, df, p, errors}] for every term but the intercept: up to
    ROBUST_MAX_DF degrees of freedom on the robust (bias-reduced) errors,
    more on the model's own."""
    di = getattr(res.model.data, "design_info", None) or res.model.data.model_spec       # the latter since statsmodels 0.15
    b = np.asarray(res.params)
    rob = np.asarray(res.cov_robust_bc)
    nai = np.asarray(res.cov_naive)
    out = []
    for name, sl in di.term_name_slices.items():
        if name == "Intercept":
            continue
        k = sl.stop - sl.start
        robust = k <= ROBUST_MAX_DF
        V = (rob if robust else nai)[sl, sl]
        bb = b[sl]
        try:
            x = float(bb @ np.linalg.solve(V, bb))
        except np.linalg.LinAlgError:
            x = float("nan")
        out.append({"term": _term_say(name), "chi2": x, "df": k, "p": _chi2_sf(x, k) if np.isfinite(x) else None,
                    "errors": ROBUST if robust else NAIVE})
    return out


def interaction(df, formula, has, fam="gamma"):
    """The one coefficient whose name contains every string in `has` (an
    interaction of two two-level factors), on the robust errors: its
    exp() for a Gamma model (a ratio of ratios), as is for normal."""
    res = gee(df, formula, fam)
    names = list(res.params.index)
    i = next(k for k, n in enumerate(names) if all(h in n for h in has))
    b = float(res.params.iloc[i])
    se = float(np.sqrt(np.asarray(res.cov_robust_bc)[i, i]))
    x = (b / se) ** 2 if se > 0 else float("nan")
    tr = math.exp if fam == "gamma" else (lambda v: v)
    return {"ratio": math.exp(b) if fam == "gamma" else None, "diff": b if fam == "normal" else None, "chi2": x, "df": 1,
            "p": _chi2_sf(x, 1) if np.isfinite(x) else None, "errors": ROBUST,
            "lo": tr(b - 1.959964 * se), "hi": tr(b + 1.959964 * se)}


def lmm_test(df, formula, has, log=True):
    """The robustness check the plan asks for: a linear mixed model with a
    random intercept for the rat, on log(y) (coherence and its relatives)
    or y (power in dB), and a Wald F of the coefficients whose names
    contain every string in `has`, on k and k(n - 1) degrees of freedom:
    what Kenward-Roger gives for a within-rat effect in a balanced design.
    {F, df1, df2, p} or {error}."""
    import warnings
    import statsmodels.formula.api as smf
    from scipy.stats import f as fdist
    d = df.copy()
    d["ly"] = np.log(d["y"]) if log else d["y"]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = smf.mixedlm(formula.replace("y ~", "ly ~", 1), d, groups="rat").fit(reml=True)
        names = list(m.fe_params.index)
        idx = [i for i, n in enumerate(names) if all(h in n for h in has)]
        if not idx:
            return {"error": "no such term"}
        b = m.fe_params.values[idx]
        V = np.asarray(m.cov_params().loc[names, names])[np.ix_(idx, idx)]
        k, n = len(idx), int(d["rat"].nunique())
        F = float(b @ np.linalg.solve(V, b)) / k
        return {"F": F, "df1": k, "df2": k * (n - 1), "p": float(fdist.sf(F, k, k * (n - 1)))}
    except Exception as exc:                                  # noqa: BLE001
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def sig(x, mode, pk="p", qk="q"):
    """Does a test pass under the switch: FDR's q (on) or the raw p (off)."""
    if not x:
        return False
    v = x.get(qk) if mode == "fdr" else x.get(pk)
    return v is not None and v < ALPHA


MODES = ("fdr", "raw")
MODE_SAY = {"fdr": "FDR-corrected (q < 0.05)", "raw": "Uncorrected (p < 0.05)"}
STAR_SAY = {"fdr": "FDR q < 0.05 across the ten", "raw": "p < 0.05, uncorrected"}


def ratio(res, name_has):
    """exp(the one coefficient whose name contains `name_has`), with its
    robust p: a Late/Early (or Cue 2/Cue 1) ratio."""
    names = list(res.params.index)
    i = next(k for k, n in enumerate(names) if name_has in n)
    b = float(res.params.iloc[i])
    se = float(np.sqrt(np.asarray(res.cov_robust_bc)[i, i]))
    x = (b / se) ** 2 if se > 0 else float("nan")
    return {"ratio": math.exp(b), "chi2": x, "df": 1, "p": _chi2_sf(x, 1) if np.isfinite(x) else None, "errors": ROBUST}


def bh(pvals):
    """Benjamini-Hochberg q (None passes through)."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    out = [None] * len(pvals)
    running = 1.0
    for rank, i in reversed(list(enumerate(sorted(idx, key=lambda i: pvals[i]), 1))):
        running = min(running, pvals[i] * m / rank)
        out[i] = min(1.0, running)
    return out


def _frame(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def pair_rats(T, p):
    """The rats a region pair has on both days, in the cue pair window."""
    rats = sorted({r for r, _d in T["band"]["pair"]["theta"]})
    return [r for r in rats if all(np.isfinite(T["band"]["pair"]["theta"].get((r, d), np.full(len(PAIRS), np.nan))[p])
                                   for d in DAYS)]


def _safe(fn, *a):
    try:
        return fn(*a), None
    except EvenMoreError as exc:
        return None, str(exc)


def phase1(T, band):
    """A1 (Session x Pair on the band), A2 (Session in each pair, FDR), B1
    (Session x Pair x Frequency), B2 (Session x Frequency in each pair)."""
    keep = [p for p in range(len(PAIRS)) if len(pair_rats(T, p)) >= MIN_RATS]
    rows, rows_b = [], []
    for p in keep:
        for r in pair_rats(T, p):
            for d in DAYS:
                rows.append({"rat": r, "day": d, "pair": "p%02d" % p, "y": float(T["band"]["pair"][band][(r, d)][p])})
                for fi, (f, _m) in enumerate(bins_of(band)):
                    rows_b.append({"rat": r, "day": d, "pair": "p%02d" % p, "f": "f%02d" % fi, "hz": f,
                                   "y": float(T["bins"]["pair"][band][(r, d)][p, fi])})
    df, dfb = _frame(rows), _frame(rows_b)
    dfb = dfb[np.isfinite(dfb["y"]) & (dfb["y"] > 0)]
    a1, a1_err = _safe(lambda: terms(gee(df, "y ~ C(day, Sum) * C(pair, Sum)")))
    b1, b1_err = _safe(lambda: terms(gee(dfb, "y ~ C(day, Sum) * C(pair, Sum) * C(f, Sum)")))
    per = []
    for p in range(len(PAIRS)):
        if p not in keep:
            per.append(None)
            continue
        sub = df[df["pair"] == "p%02d" % p]
        subb = dfb[dfb["pair"] == "p%02d" % p]
        a2, a2_err = _safe(lambda: ratio(gee(sub, "y ~ C(day, Treatment('Precon1'))"), "Precon4"))
        b2, b2_err = _safe(lambda: terms(gee(subb, "y ~ C(day, Sum) * C(f, Sum)")))
        per.append({"pair": p, "a2": a2, "a2_error": a2_err, "b2": b2, "b2_error": b2_err, "rats": pair_rats(T, p)})
    qa = bh([x["a2"]["p"] if x and x["a2"] else None for x in per])
    qb = bh([_term_p(x["b2"], "Session × Frequency") if x and x["b2"] else None for x in per])
    for x, q1, q2 in zip(per, qa, qb):
        if x:
            if x["a2"]:
                x["a2"]["q"] = q1
            x["b2_q"] = q2
    return {"a1": a1, "a1_error": a1_err, "b1": b1, "b1_error": b1_err, "pairs": per, "rows": rows, "rows_bins": dfb.to_dict("records")}


def _term_p(ts, name):
    t = next((t for t in ts or [] if t["term"] == name), None)
    return t["p"] if t else None


def phase2(T, band):
    """The matched trials (all of them): cue 1 against cue 2 on each day.
    Omnibus Session x Cue x Pair; in each pair Session x Cue (FDR), and the
    cue effect on each day."""
    keep = [p for p in range(len(PAIRS)) if len(pair_rats(T, p)) >= MIN_RATS]
    rows = []
    for p in keep:
        for r in pair_rats(T, p):
            for d in DAYS:
                for cue in ("cue1", "cue2"):
                    v = T["band"][cue][band].get((r, d))
                    if v is not None and np.isfinite(v[p]):
                        rows.append({"rat": r, "day": d, "cue": cue, "pair": "p%02d" % p, "y": float(v[p])})
    df = _frame(rows)
    om, om_err = _safe(lambda: terms(gee(df, "y ~ C(day, Sum) * C(cue, Sum) * C(pair, Sum)")))
    per = []
    for p in range(len(PAIRS)):
        if p not in keep:
            per.append(None)
            continue
        sub = df[df["pair"] == "p%02d" % p]
        inter, ierr = _safe(lambda: terms(gee(sub, "y ~ C(day, Sum) * C(cue, Sum)")))
        days = {}
        for d in DAYS:
            got, err = _safe(lambda: ratio(gee(sub[sub["day"] == d], "y ~ C(cue, Treatment('cue1'))"), "cue2"))
            days[d] = got or {"error": err}
        per.append({"pair": p, "terms": inter, "error": ierr, "days": days, "rats": pair_rats(T, p)})
    q = bh([_term_p(x["terms"], "Session × Cue") if x and x["terms"] else None for x in per])
    for x, qq in zip(per, q):
        if x:
            x["q"] = qq
    # each day's cue effect, corrected across the ten too
    for d in DAYS:
        qd = bh([x["days"][d].get("p") if x else None for x in per])
        for x, qq in zip(per, qd):
            if x and "ratio" in x["days"][d]:
                x["days"][d]["q"] = qq
    return {"omnibus": om, "error": om_err, "pairs": per, "rows": rows}


#: Phase 3 (2026-10-30): coherence in the power plan's three periods. The
#: codes sort as the periods run, so SPSS's reference (the last level) is cue 2.
PERIODS = ("base10", "cue1", "cue2")
PERIOD_SAY = {"base10": "Baseline", "cue1": "Cue 1", "cue2": "Cue 2"}
PERIOD_CODE = {"base10": "1 baseline", "cue1": "2 cue 1", "cue2": "3 cue 2"}
CONTRASTS = (("cue1", "base10", "Cue 1 vs baseline"), ("cue2", "base10", "Cue 2 vs baseline"), ("cue2", "cue1", "Cue 2 vs cue 1"))


def contrast_key(a, b):
    return "%s-%s" % (a, b)


def period_contrasts(sub, fam="gamma"):
    """Session x (one period against another), each on its own two
    periods' rows: 1 df, robust. For coherence the ratio of ratios
    (Late's cue/baseline over Early's); for power in dB the difference of
    differences."""
    out = {}
    for a, b, _s in CONTRASTS:
        two = sub[sub["period"].isin([PERIOD_CODE[a], PERIOD_CODE[b]])]
        got, err = _safe(lambda: interaction(two, "y ~ C(day, Treatment('Precon1')) * C(period, Treatment('%s'))" % PERIOD_CODE[b],
                                             ["Precon4", PERIOD_CODE[a]], fam))
        out[contrast_key(a, b)] = got or {"error": err}
    return out


def fdr_across(items, getp, put):
    """Benjamini-Hochberg over a family: `getp(item)` its p (None to skip),
    `put(item, q)` stores q."""
    qs = bh([getp(x) if x else None for x in items])
    for x, q in zip(items, qs):
        if x and q is not None:
            put(x, q)


def phase3(T, band):
    """Coherence in the 10 s baseline, cue 1 and cue 2 (pooled spectra, the
    same pairs): Session x Period in each pair (2 df, robust) and its three
    planned contrasts, each corrected across the ten pairs."""
    rows = []
    keep = [p for p in range(len(PAIRS)) if len(pair_rats(T, p)) >= MIN_RATS]
    for p in keep:
        for r in pair_rats(T, p):
            for d in DAYS:
                for w in PERIODS:
                    v = T["band"][w][band].get((r, d))
                    if v is not None and np.isfinite(v[p]) and v[p] > 0:
                        rows.append({"rat": r, "day": d, "period": PERIOD_CODE[w], "pair": "p%02d" % p, "y": float(v[p])})
    df = _frame(rows)
    per = []
    for p in range(len(PAIRS)):
        if p not in keep:
            per.append(None)
            continue
        sub = df[df["pair"] == "p%02d" % p]
        ts, err = _safe(lambda: terms(gee(sub, "y ~ C(day, Sum) * C(period, Sum)")))
        x = {"pair": p, "rats": pair_rats(T, p), "terms": ts, "error": err, "contrasts": period_contrasts(sub)}
        sp = next((t for t in ts or [] if t["term"] == "Session × Period"), None)
        x["sp"] = {"chi2": sp["chi2"], "df": sp["df"], "p": sp["p"], "errors": sp["errors"]} if sp else None
        per.append(x)
    fdr_across(per, lambda x: (x["sp"] or {}).get("p"), lambda x, q: x["sp"].__setitem__("q", q))
    for a, b, _s in CONTRASTS:
        k = contrast_key(a, b)
        fdr_across(per, lambda x: x["contrasts"][k].get("p"), lambda x, q: x["contrasts"][k].__setitem__("q", q))
    return {"pairs": per, "rows": rows}


def robustness(kind, band, p, sub, fit, lmm_formula, lmm_has, log=True, label=""):
    """Leave each rat out and fit again (`fit(df)` -> {p, ...}); and the
    linear mixed model beside it. For every hit (raw p < 0.05, so both
    sides of the switch have theirs)."""
    rats = sorted(int(r) for r in sub["rat"].unique())
    loo = []
    for r in rats:
        got, err = _safe(lambda: fit(sub[sub["rat"] != r]))
        loo.append({"rat": r, "p": (got or {}).get("p"), "error": err})
    ps = [x["p"] for x in loo if x["p"] is not None]
    worst = max(loo, key=lambda x: -1 if x["p"] is None else x["p"]) if loo else None
    lm = lmm_test(sub, lmm_formula, lmm_has, log=log)
    return {"kind": kind, "band": band, "pair": p, "label": label, "loo": loo,
            "survives": bool(ps) and len(ps) == len(loo) and all(v < ALPHA for v in ps),
            "worst": worst, "lmm": lm}


# --------------------------------------------------------------------------
# What the figures show (means are for looking; the GEE decides)
# --------------------------------------------------------------------------
def _se(x):
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    return float(x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 1 else float("nan")


def _mean(x):
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    return float(x.mean()) if len(x) else float("nan")


def num(x, fmt="%.3f"):
    return "–" if x is None or not np.isfinite(x) else (fmt % x).replace("-", "−")


def p_say(p):
    if p is None or not np.isfinite(p):
        return "p –"
    return "p < 0.001" if p < 0.001 else "p = %s" % ("%.3f" % p)


def star(p):
    return "*" if p is not None and p < ALPHA else ""


def wire_count(T, p, rats):
    ip = co = 0
    for r in rats:
        w = T["wires"].get((r, DAYS[0]))
        if w is None:
            continue
        ip += int(w[p, 0]) + int(w[p, 1])
        co += int(w[p, 2]) + int(w[p, 3])
    return ip, co


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def _plt():
    from . import joefigs
    return joefigs._plt()


def _ax(fig, x, y, w, h, H, W, **kw):
    from . import joefigs
    return joefigs._ax(fig, x, y, w, h, H, W, **kw)


def _letter(fig, x, y, s, H, W):
    from . import joefigs
    joefigs._letter(fig, x, y, s, H, W)


def _save(fig, name):
    os.makedirs(figs_dir(), exist_ok=True)
    out = {}
    for ext in ("svg", "pdf", "png"):
        p = figs_dir("%s.%s" % (name, ext))
        fig.savefig(p, dpi=600 if ext == "png" else None)
        out[ext] = os.path.basename(p)
    return out


def _style(p):
    return {"color": COLORS[p], "ls": "-." if DASHED[p] else "-", "mfc": "white" if DASHED[p] else COLORS[p]}


def draw_ring(ax, deltas, qs, focus=None):
    """The five regions on tab 9's ring, an edge per pair in its own colour
    (pairs 9 and 10 dash-dotted), its width the size of Late - Early, an
    arrowhead mark for its sign; solid when its Late vs Early test passes
    after FDR, faint when not. `focus` greys every other pair."""
    from matplotlib.patches import Circle, PathPatch
    from matplotlib.path import Path
    from . import joefigs
    ax.set_xlim(-1.7, 1.7)
    ax.set_ylim(-1.7, 1.7)
    ax.set_aspect("equal")
    ax.axis("off")
    pos = joefigs.ring_pos(len(STRUCTS))
    ax.add_patch(Circle((0, 0), 1.0, fill=False, lw=0.35, ec="#E3E3E3", zorder=0))
    vmax = max([abs(v) for v in deltas if v is not None and np.isfinite(v)] + [1e-9])
    order = sorted(range(len(PAIRS)), key=lambda p: (focus == p, abs(deltas[p]) if deltas[p] is not None and np.isfinite(deltas[p]) else -1))
    for p in order:
        v = deltas[p]
        if v is None or not np.isfinite(v):
            continue
        i, j = PAIRS[p]
        (x0, y0), (x1, y1) = pos[i], pos[j]
        mx, my = (x0 + x1) / 2 * 0.35, (y0 + y1) / 2 * 0.35
        st = _style(p)
        grey = focus is not None and focus != p
        passed = bool(qs[p])                          # `qs`: does each pair pass, under the switch
        lw = 0.5 + 2.6 * min(1.0, abs(v) / vmax)
        ax.add_patch(PathPatch(Path([(x0, y0), (mx, my), (x1, y1)], [Path.MOVETO, Path.CURVE3, Path.CURVE3]), fill=False,
                               lw=lw if not grey else 0.5, ec="#D9D9D9" if grey else st["color"],
                               ls=st["ls"], alpha=1.0 if (passed or grey) else 0.55, capstyle="round", zorder=2 if focus == p else 1))
        if not grey:
            # the curve's midpoint, with the sign of the change
            cx, cy = 0.25 * x0 + 0.5 * mx + 0.25 * x1, 0.25 * y0 + 0.5 * my + 0.25 * y1
            ax.text(cx, cy, "▲" if v > 0 else "▼", fontsize=4, ha="center", va="center", color=st["color"], zorder=3)
    for k, (x, y) in enumerate(pos):
        on = focus is None or k in PAIRS[focus]
        ax.scatter([x], [y], s=18, c="#1A1A1A" if on and focus is not None else "white", edgecolors="#1A1A1A", linewidths=0.5, zorder=4)
        ax.text(x * 1.33, y * 1.27, STRUCTS[k][1], fontsize=5.5, ha="left" if x > 0.15 else "right" if x < -0.15 else "center",
                va="center", color="#1A1A1A" if on else "#A6A6A6")


def _freq_axis(ax, centers, band, label=True):
    ax.set_xticks(range(len(centers)))
    step = 3 if band == "theta" else 5
    ax.set_xticklabels([("%.2f" % c if band == "theta" else "%d" % round(c)) if k % step == 0 else "" for k, c in enumerate(centers)],
                       rotation=45 if band == "theta" else 0, fontsize=4.8)
    if label:
        ax.set_xlabel("Frequency (Hz)", fontsize=5.5, labelpad=1)


def _violins(ax, groups, positions, colors, alphas, width=0.7):
    data = [np.asarray([v for v in g if np.isfinite(v)]) for g in groups]
    use = [k for k, x in enumerate(data) if len(x) > 1]
    if use:
        vp = ax.violinplot([data[k] for k in use], positions=[positions[k] for k in use], widths=width,
                           showextrema=False, showmedians=False)
        for b, k in zip(vp["bodies"], use):
            b.set_facecolor(colors[k])
            b.set_edgecolor("#1A1A1A")
            b.set_linewidth(0.35)
            b.set_alpha(alphas[k])
    rng = np.random.default_rng(7)
    for k, x in enumerate(data):
        if not len(x):
            continue
        jit = (rng.random(len(x)) - 0.5) * width * 0.45
        ax.scatter(positions[k] + jit, x, s=0.6, c="#1A1A1A", alpha=0.45, lw=0, zorder=3)
        q1, md, q3 = np.percentile(x, [25, 50, 75])
        for yy, lw in ((q1, 0.4), (md, 0.8), (q3, 0.4)):
            ax.plot([positions[k] - width * 0.22, positions[k] + width * 0.22], [yy, yy], color="#1A1A1A", lw=lw, zorder=4)


def _band_say(band):
    return joe.BAND_SAY[band]


def fig_pair_phase1(T, band, p, st, deltas, qs, fid):
    """One pair, Figure 3's way: a, the ring with this pair lit; b, the
    violins of each rat's frequency bins; c, Early to Late; d, the spectra
    with the change per bin."""
    plt = _plt()
    W, H = 183.0, 70.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    rats = st["rats"]
    col = COLORS[p]
    ip, co = wire_count(T, p, rats)
    fig.text(4 / W, 1 - 3 / H, "%s · %s · %d rats (%d wire pairs: %d ipsi, %d contra)" % (PAIR_SAY[p], _band_say(band), len(rats), ip + co, ip, co),
             fontsize=7, fontweight="bold", va="top")
    fig.text(4 / W, 1 - 8 / H, "Coherence from pooled spectra (all of a session's trials in one spectrum), the cue pair window. "
             "Points and lines are for looking; the GEE decides significance.", fontsize=5, va="top", color="#4D4D4D")
    ax = _ax(fig, 2, 16, 36, 36, H, W)
    draw_ring(ax, deltas, qs, focus=p)
    _letter(fig, 2, 15, "a", H, W)
    centers = [f for f, _m in bins_of(band)]
    # b: violins, each dot one rat's frequency bin
    ax = _ax(fig, 50, 16, 30, 36, H, W)
    vals = [np.concatenate([T["bins"]["pair"][band][(r, d)][p] for r in rats]) for d in DAYS]
    _violins(ax, vals, [0, 1], [col, col], [0.25, 0.6])
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Early", "Late"])
    ax.set_ylabel("%s coherence" % band.capitalize(), fontsize=5.5, labelpad=1)
    ax.set_ylim(bottom=0)
    _letter(fig, 41, 15, "b", H, W)
    # c: Early to Late, each rat behind
    ax = _ax(fig, 96, 16, 24, 36, H, W)
    per = np.array([[T["band"]["pair"][band][(r, d)][p] for d in DAYS] for r in rats])
    for row in per:
        ax.plot([0, 1], row, color="#BFBFBF", lw=0.4, zorder=1)
    mu = [_mean(per[:, k]) for k in range(2)]
    se = [_se(per[:, k]) for k in range(2)]
    ax.errorbar([0, 1], mu, yerr=se, color=col, ls=_style(p)["ls"], lw=1.1, marker="o", ms=2.6, mfc=_style(p)["mfc"],
                capsize=1.5, elinewidth=0.6, zorder=3)
    a2 = st.get("a2")
    if qs[p]:
        ax.text(1, mu[1] + se[1] * 1.6, "*", color=col, fontsize=9, ha="center", va="bottom", fontweight="bold")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Early", "Late"])
    ax.set_xlim(-0.4, 1.4)
    ax.set_ylabel("Mean %s coherence" % band, fontsize=5.5, labelpad=1)
    _letter(fig, 85, 15, "c", H, W)
    # d: spectra, Early solid, Late dashed; the change per bin as an inset
    ax = _ax(fig, 132, 16, 46, 36, H, W)
    top = 0.0
    for k, d in enumerate(DAYS):
        S = np.array([T["bins"]["pair"][band][(r, d)][p] for r in rats])
        m = _nanmean(S, axis=0)
        e = np.array([_se(S[:, j]) for j in range(S.shape[1])])
        ax.errorbar(range(len(centers)), m, yerr=e, color=col, ls="-" if k == 0 else "--", lw=0.9, capsize=1.0, elinewidth=0.45,
                    label="Early" if k == 0 else "Late")
        top = max(top, float(np.nanmax(m + np.nan_to_num(e))))
    _freq_axis(ax, centers, band)
    ax.set_ylabel("Coherence", fontsize=5.5, labelpad=1)
    ax.set_ylim(0, top * 1.75 if top > 0 else 1)                  # headroom: the inset sits above the lines
    ax.legend(frameon=False, fontsize=5, loc="upper left", handlelength=1.8)
    _letter(fig, 125, 15, "d", H, W)
    ins = _ax(fig, 158, 16.5, 19, 11, H, W)
    dl = np.array([T["bins"]["pair"][band][(r, DAYS[1])][p] - T["bins"]["pair"][band][(r, DAYS[0])][p] for r in rats])
    dm = _nanmean(dl, axis=0)
    ins.bar(range(len(dm)), dm, color=[col if v >= 0 else "#8C8C8C" for v in dm], width=0.8, lw=0)
    ins.axhline(0, color="#1A1A1A", lw=0.4)
    ins.set_xticks([])
    ins.tick_params(labelsize=4)
    ins.set_title("Δ Coh. (Late − Early)", fontsize=4.6, pad=1)
    # the GEE, in words under the panels
    b2 = st.get("b2") or []
    sf = next((t for t in b2 if t["term"] == "Session × Frequency"), None)
    line = ("GEE, Late vs Early: ×%s, χ²(1) = %s, %s, FDR q = %s (%s errors)"
            % (num(a2["ratio"]), num(a2["chi2"], "%.2f"), p_say(a2["p"]), num(a2.get("q"), "%.3f"), ROBUST)) if a2 else \
        "GEE, Late vs Early: %s" % (st.get("a2_error") or "not fitted")
    if sf:
        line += ".  Session × frequency: χ²(%d) = %s, %s, q = %s (%s)" % (sf["df"], num(sf["chi2"], "%.2f"), p_say(sf["p"]),
                                                                          num(st.get("b2_q"), "%.3f"), sf["errors"])
    fig.text(4 / W, 1 - (H - 3.5) / H, line, fontsize=5.2, va="bottom")
    files = _save(fig, "fig_%s" % fid)
    plt.close(fig)
    return files


def _legend_rows(ax, items, x0=0.0, dy=1.0):
    """A legend drawn by hand: a short line in each pair's colour and style,
    its marker, its name and its n."""
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(len(items) + 0.5, 0.5)
    for k, (p, text) in enumerate(items, 1):
        st = _style(p)
        ax.plot([x0, x0 + 1.2], [k, k], color=st["color"], ls=st["ls"], lw=1.2)
        ax.plot([x0 + 0.6], [k], marker="o", ms=2.4, color=st["color"], mfc=st["mfc"], mew=0.6)
        ax.text(x0 + 1.6, k, text, va="center", fontsize=5.2)


def _terms_lines(ts, err):
    if err:
        return ["not fitted: %s" % err]
    return ["%s: χ²(%d) = %s, %s%s" % (t["term"], t["df"], num(t["chi2"], "%.2f"), p_say(t["p"]),
                                       "" if t["errors"] == ROBUST else " (model-based)") for t in ts or []]


def fig_pooled_phase1(T, band, res, deltas, qs, fid, mode="fdr"):
    """All ten on one figure: a, the ring; the omnibus; b, the violins; c,
    Early to Late; d, e, the spectra on each day; f, the change per bin."""
    plt = _plt()
    W, H = 183.0, 178.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    keep = [x["pair"] for x in res["pairs"] if x]
    fig.text(4 / W, 1 - 3 / H, "All ten pairs · %s · Early (Precon1) vs Late (Precon4)" % _band_say(band), fontsize=7.5,
             fontweight="bold", va="top")
    fig.text(4 / W, 1 - 8 / H, "Pooled spectra, cue pair window; each pair the mean of its valid wire pairs. GEE: Gamma, log link, "
             "exchangeable, rat as the cluster; tests of up to 2 df on robust (Mancl–DeRouen) errors, the rest model-based.", fontsize=5,
             va="top", color="#4D4D4D")
    ax = _ax(fig, 2, 15, 50, 50, H, W)
    draw_ring(ax, deltas, qs)
    _letter(fig, 2, 14, "a", H, W)
    lx = _ax(fig, 56, 16, 50, 48, H, W)
    _legend_rows(lx, [(p, "%s  n = %d%s" % (PAIR_SAY[p], len(res["pairs"][p]["rats"]),
                                            "  *" if qs[p] else "")) for p in keep])
    tx = 110
    fig.text(tx / W, 1 - 16 / H, "Band coherence (A1)", fontsize=6, fontweight="bold", va="top")
    for k, s in enumerate(_terms_lines(res["a1"], res["a1_error"])):
        fig.text(tx / W, 1 - (21 + 4.2 * k) / H, s, fontsize=5.2, va="top")
    fig.text(tx / W, 1 - 38 / H, "Across frequency bins (B1)", fontsize=6, fontweight="bold", va="top")
    for k, s in enumerate(_terms_lines(res["b1"], res["b1_error"])):
        fig.text(tx / W, 1 - (43 + 4.2 * k) / H, s, fontsize=5.2, va="top")
    fig.text(56 / W, 1 - 66 / H, "* Late vs Early in that pair, " + STAR_SAY[mode] + ".", fontsize=5, va="top", color="#4D4D4D")
    # b: violins, Early and Late side by side for each pair
    ax = _ax(fig, 14, 76, 110, 38, H, W)
    groups, pos, cols, alph = [], [], [], []
    for k, p in enumerate(keep):
        rats = res["pairs"][p]["rats"]
        for di, d in enumerate(DAYS):
            groups.append(np.concatenate([T["bins"]["pair"][band][(r, d)][p] for r in rats]))
            pos.append(k * 2.6 + di)
            cols.append(COLORS[p])
            alph.append(0.25 if di == 0 else 0.65)
    _violins(ax, groups, pos, cols, alph, width=0.85)
    ax.set_xticks([k * 2.6 + 0.5 for k in range(len(keep))])
    ax.set_xticklabels([PAIR_SAY[p] for p in keep], rotation=35, ha="right", fontsize=5)
    ax.set_ylabel("%s coherence" % band.capitalize(), fontsize=5.5, labelpad=1)
    ax.set_ylim(bottom=0)
    ax.text(0, 1.02, "each pair: Early (light), Late (dark); each dot one rat's frequency bin", transform=ax.transAxes, fontsize=5,
            color="#4D4D4D", va="bottom")
    _letter(fig, 4, 74, "b", H, W)
    # c: Early to Late, every pair
    ax = _ax(fig, 140, 76, 38, 38, H, W)
    for p in keep:
        rats = res["pairs"][p]["rats"]
        per = np.array([[T["band"]["pair"][band][(r, d)][p] for d in DAYS] for r in rats])
        mu = [_mean(per[:, k]) for k in range(2)]
        se = [_se(per[:, k]) for k in range(2)]
        st = _style(p)
        ax.errorbar([0, 1], mu, yerr=se, color=st["color"], ls=st["ls"], lw=0.9, marker="o", ms=2.2, mfc=st["mfc"], mew=0.6,
                    capsize=1.2, elinewidth=0.5)
        if qs[p]:
            ax.text(1.12, mu[1], "*", color=st["color"], fontsize=7, va="center", fontweight="bold")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Early", "Late"])
    ax.set_xlim(-0.3, 1.35)
    ax.set_ylabel("Mean %s coherence" % band, fontsize=5.5, labelpad=1)
    _letter(fig, 130, 74, "c", H, W)
    # d, e: spectra on each day; f: the change per bin
    centers = [f for f, _m in bins_of(band)]
    lims = []
    axes = []
    for di, d in enumerate(DAYS):
        ax = _ax(fig, 14 + 58 * di, 130, 48, 32, H, W)
        axes.append(ax)
        for p in keep:
            rats = res["pairs"][p]["rats"]
            S = np.array([T["bins"]["pair"][band][(r, d)][p] for r in rats])
            m = _nanmean(S, axis=0)
            e = np.array([_se(S[:, j]) for j in range(S.shape[1])])
            st = _style(p)
            ax.errorbar(range(len(centers)), m, yerr=e, color=st["color"], ls=st["ls"], lw=0.8, capsize=0.8, elinewidth=0.35)
            lims.append(np.nanmax(m + np.nan_to_num(e)))
        _freq_axis(ax, centers, band)
        ax.set_title(DAY_SAY[d], fontsize=6, pad=2)
        if di == 0:
            ax.set_ylabel("Coherence", fontsize=5.5, labelpad=1)
        _letter(fig, 4 + 58 * di, 128, "de"[di], H, W)
    top = max(lims + [1e-6]) * 1.08
    for ax in axes:
        ax.set_ylim(0, top)
    ax = _ax(fig, 130, 130, 48, 32, H, W)
    for p in keep:
        rats = res["pairs"][p]["rats"]
        dl = np.array([T["bins"]["pair"][band][(r, DAYS[1])][p] - T["bins"]["pair"][band][(r, DAYS[0])][p] for r in rats])
        st = _style(p)
        ax.plot(range(len(centers)), _nanmean(dl, axis=0), color=st["color"], ls=st["ls"], lw=0.8)
    ax.axhline(0, color="#1A1A1A", lw=0.4)
    _freq_axis(ax, centers, band)
    ax.set_title("Δ Coh. (Late − Early), mean of rats", fontsize=6, pad=2)
    _letter(fig, 122, 128, "f", H, W)
    files = _save(fig, "fig_%s" % fid)
    plt.close(fig)
    return files


def _cue_panel(ax, T, band, p, rats, d, single=True):
    st = _style(p)
    per = np.array([[T["band"][c][band][(r, d)][p] for c in ("cue1", "cue2")] for r in rats])
    if single:
        for row in per:
            ax.plot([0, 1], row, color="#BFBFBF", lw=0.4, zorder=1)
    mu = [_mean(per[:, k]) for k in range(2)]
    se = [_se(per[:, k]) for k in range(2)]
    ax.errorbar([0, 1], mu, yerr=se, color=st["color"], ls=st["ls"], lw=1.1 if single else 0.9, marker="o",
                ms=2.6 if single else 2.2, mfc=st["mfc"], mew=0.6, capsize=1.4, elinewidth=0.55, zorder=3)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Cue 1", "Cue 2"])
    ax.set_xlim(-0.35, 1.35)
    ax.set_title(DAY_SAY[d], fontsize=6, pad=2)
    return mu, se


def fig_pair_phase2(T, band, p, st, fid, mode="fdr"):
    """One pair: cue 1 and cue 2, Precon1 beside Precon4."""
    plt = _plt()
    W, H = 120.0, 66.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    rats = st["rats"]
    fig.text(4 / W, 1 - 3 / H, "%s · %s · cue 1 vs cue 2 · %d rats" % (PAIR_SAY[p], _band_say(band), len(rats)), fontsize=7,
             fontweight="bold", va="top")
    fig.text(4 / W, 1 - 8 / H, "Matched trials (A→B, C→D, pooled); pooled spectra in each 10 s cue.", fontsize=5, va="top",
             color="#4D4D4D")
    axes, tops = [], []
    for di, d in enumerate(DAYS):
        ax = _ax(fig, 16 + 54 * di, 16, 38, 30, H, W)
        mu, se = _cue_panel(ax, T, band, p, rats, d)
        r = st["days"][d]
        if sig(r, mode):
            ax.text(0.5, max(mu) + max(se) * 1.5, "*", ha="center", fontsize=9, fontweight="bold", color=COLORS[p])
        if di == 0:
            ax.set_ylabel("Mean %s coherence" % band, fontsize=5.5, labelpad=1)
        axes.append(ax)
        tops.append(ax.get_ylim())
        _letter(fig, 6 + 54 * di, 15, "ab"[di], H, W)
    lo, hi = min(t[0] for t in tops), max(t[1] for t in tops)
    for ax in axes:
        ax.set_ylim(lo, hi)
    y = H - 13
    for d in DAYS:
        r = st["days"][d]
        s = ("%s, Cue 2 vs Cue 1: ×%s, χ²(1) = %s, %s, FDR q = %s" % (d, num(r["ratio"]), num(r["chi2"], "%.2f"), p_say(r["p"]),
                                                                    num(r.get("q"), "%.3f"))) if "ratio" in r \
            else "%s: %s" % (d, r.get("error"))
        fig.text(4 / W, 1 - y / H, s, fontsize=5.2, va="top")
        y += 4
    sc = next((t for t in st["terms"] or [] if t["term"] == "Session × Cue"), None)
    fig.text(4 / W, 1 - y / H, ("Session × Cue: χ²(1) = %s, %s, FDR q = %s (%s errors)" % (num(sc["chi2"], "%.2f"), p_say(sc["p"]),
                                                                                       num(st.get("q"), "%.3f"), ROBUST))
             if sc else "Session × Cue: %s" % (st.get("error") or "not fitted"), fontsize=5.2, va="top", fontweight="bold")
    files = _save(fig, "fig_%s" % fid)
    plt.close(fig)
    return files


def fig_pooled_phase2(T, band, res, fid, mode="fdr"):
    plt = _plt()
    W, H = 183.0, 70.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    keep = [x["pair"] for x in res["pairs"] if x]
    fig.text(4 / W, 1 - 3 / H, "All ten pairs · %s · cue 1 vs cue 2 on each day" % _band_say(band), fontsize=7.5, fontweight="bold",
             va="top")
    fig.text(4 / W, 1 - 8 / H, "Matched trials, pooled spectra in each 10 s cue; the mean of rats ± s.e.m. * Session × Cue in that pair, "
             + STAR_SAY[mode] + ".", fontsize=5, va="top", color="#4D4D4D")
    axes, tops = [], []
    for di, d in enumerate(DAYS):
        ax = _ax(fig, 16 + 52 * di, 16, 40, 44, H, W)
        for p in keep:
            mu, _se_ = _cue_panel(ax, T, band, p, res["pairs"][p]["rats"], d, single=False)
            if di == 1 and sig(res["pairs"][p], mode):
                ax.text(1.12, mu[1], "*", color=COLORS[p], fontsize=7, va="center", fontweight="bold")
        if di == 0:
            ax.set_ylabel("Mean %s coherence" % band, fontsize=5.5, labelpad=1)
        axes.append(ax)
        tops.append(ax.get_ylim())
        _letter(fig, 6 + 52 * di, 15, "ab"[di], H, W)
    lo, hi = min(t[0] for t in tops), max(t[1] for t in tops)
    for ax in axes:
        ax.set_ylim(lo, hi)
    lx = _ax(fig, 116, 14, 30, 50, H, W)
    _legend_rows(lx, [(p, "%s%s" % (PAIR_SAY[p], "  *" if sig(res["pairs"][p], mode) else ""))
                      for p in keep])
    fig.text(150 / W, 1 - 16 / H, "Session × Cue × Pair", fontsize=6, fontweight="bold", va="top")
    for k, s in enumerate(_terms_lines(res["omnibus"], res["error"])):
        fig.text(150 / W, 1 - (21 + 4.6 * k) / H, s.replace(": ", ":\n  ", 1), fontsize=4.9, va="top")
    files = _save(fig, "fig_%s" % fid)
    plt.close(fig)
    return files


def period_panels(fig, T, band, key, rats, unit, col, ls_style, x0, y0, H, W, ylab, diff_say, sigs=(False, False, False),
                  letters="abc", get=None, bins_get=None):
    """The power plan's three panels, for any measure over periods: (a)
    the band value in baseline, cue 1 and cue 2, Precon1 solid and Precon4
    dashed, mean ± s.e.m. of the rats; (b, c) cue 1 − baseline and cue 2 −
    baseline across frequency, both days. `get(r, d, w)` -> band value,
    `bins_get(r, d, w)` -> per-bin values. `sigs`: (Session x Period,
    Session x (cue 1 vs baseline), Session x (cue 2 vs baseline)) passing."""
    ax = _ax(fig, x0, y0, 34, 34, H, W)
    for di, d in enumerate(DAYS):
        per = np.array([[get(r, d, w) for w in PERIODS] for r in rats], float)
        mu = [_mean(per[:, k]) for k in range(3)]
        se = [_se(per[:, k]) for k in range(3)]
        ax.errorbar([0, 1, 2], mu, yerr=se, color=col, ls="-" if di == 0 else "--", lw=1.0, marker="o", ms=2.4,
                    mfc=col if di == 0 else "white", mew=0.6, capsize=1.3, elinewidth=0.5, label=DAYS[di])
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels([PERIOD_SAY[w] for w in PERIODS])
    ax.set_xlim(-0.35, 2.35)
    ax.set_ylabel(ylab, fontsize=5.5, labelpad=1)
    ax.legend(frameon=False, fontsize=4.8, loc="best", handlelength=2.0)
    if sigs[0]:
        ax.text(0.98, 0.98, "*", transform=ax.transAxes, ha="right", va="top", fontsize=9, fontweight="bold", color=col)
    _letter(fig, x0 - 9, y0 - 1, letters[0], H, W)
    centers = [f for f, _m in bins_of(band)]
    axes = []
    for k, (cue, s) in enumerate((("cue1", sigs[1]), ("cue2", sigs[2]))):
        ax = _ax(fig, x0 + 50 + 64 * k, y0, 50, 34, H, W)
        axes.append(ax)
        for di, d in enumerate(DAYS):
            D = np.array([np.asarray(bins_get(r, d, cue), float) - np.asarray(bins_get(r, d, "base10"), float) for r in rats])
            m = _nanmean(D, axis=0)
            e = np.array([_se(D[:, j]) for j in range(D.shape[1])])
            xs = np.arange(len(centers))
            ax.plot(xs, m, color=col, ls="-" if di == 0 else "--", lw=0.9)
            ax.fill_between(xs, m - np.nan_to_num(e), m + np.nan_to_num(e), color=col, alpha=0.16 if di == 0 else 0.10, lw=0)
        ax.axhline(0, color="#1A1A1A", lw=0.4)
        _freq_axis(ax, centers, band)
        ax.set_title("%s − baseline%s" % (PERIOD_SAY[cue], "  *" if s else ""), fontsize=6, pad=2)
        if k == 0:
            ax.set_ylabel(diff_say, fontsize=5.5, labelpad=1)
        _letter(fig, x0 + 42 + 64 * k, y0 - 1, letters[1 + k], H, W)
    lo = min(a.get_ylim()[0] for a in axes)
    hi = max(a.get_ylim()[1] for a in axes)
    for a in axes:
        a.set_ylim(lo, hi)


def _contrast_line(x, mode, fmt_ratio=True):
    parts = []
    sp = x.get("sp")
    if sp:
        parts.append("Session × Period: χ²(%d) = %s, %s, q = %s%s" % (sp["df"], num(sp["chi2"], "%.2f"), p_say(sp["p"]), num(sp.get("q"), "%.3f"),
                                                                    " *" if sig(sp, mode) else ""))
    for a, b, say in CONTRASTS:
        c = x["contrasts"].get(contrast_key(a, b)) or {}
        if c.get("p") is None:
            continue
        eff = ("×%s" % num(c["ratio"])) if c.get("ratio") is not None else ("%s dB" % num(c.get("diff"), "%+.2f"))
        parts.append("Session × (%s): %s, %s, q = %s%s" % (say.lower(), eff, p_say(c["p"]), num(c.get("q"), "%.3f"), " *" if sig(c, mode) else ""))
    return parts


def fig_pair_phase3(T, band, p, st, fid, mode="fdr"):
    """One pair's coherence in the three periods, laid out as the power
    plan's example."""
    plt = _plt()
    W, H = 183.0, 72.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    rats = st["rats"]
    fig.text(4 / W, 1 - 3 / H, "%s · %s · baseline, cue 1, cue 2 · %d rats" % (PAIR_SAY[p], _band_say(band), len(rats)), fontsize=7,
             fontweight="bold", va="top")
    fig.text(4 / W, 1 - 8 / H, "Coherence from pooled spectra in each 10 s window; Precon1 solid, Precon4 dashed, mean ± s.e.m. of the rats. "
             "* passes: %s." % STAR_SAY[mode], fontsize=5, va="top", color="#4D4D4D")
    sigs = (sig(st.get("sp"), mode), sig(st["contrasts"].get("cue1-base10"), mode), sig(st["contrasts"].get("cue2-base10"), mode))
    period_panels(fig, T, band, "coh", rats, "", COLORS[p], _style(p)["ls"], 18, 16, H, W, "Mean %s coherence" % band,
                  "Change in coherence", sigs,
                  get=lambda r, d, w: T["band"][w][band][(r, d)][p], bins_get=lambda r, d, w: T["bins"][w][band][(r, d)][p])
    for k, s in enumerate(_contrast_line(st, mode)):
        fig.text(4 / W, 1 - (H - 15.5 + 3.6 * k) / H, s, fontsize=5.1, va="top", fontweight="bold" if s.endswith("*") else "normal")
    files = _save(fig, "fig_%s" % fid)
    plt.close(fig)
    return files


def fig_pooled_phase3(T, band, res, fid, mode="fdr"):
    """All ten: each pair's three planned contrasts as Late's ratio of cue
    to baseline over Early's, with its 95% interval (GEE, robust)."""
    plt = _plt()
    W, H = 183.0, 92.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    keep = [x["pair"] for x in res["pairs"] if x]
    fig.text(4 / W, 1 - 3 / H, "All ten pairs · %s · how the cue effect changed from Precon1 to Precon4" % _band_say(band), fontsize=7.5,
             fontweight="bold", va="top")
    fig.text(4 / W, 1 - 8 / H, "Each dot: (cue ÷ baseline on Precon4) ÷ (cue ÷ baseline on Precon1), GEE with 95%% interval; 1 is no change. "
             "* passes: %s." % STAR_SAY[mode], fontsize=5, va="top", color="#4D4D4D")
    for k, (a, b, say) in enumerate(CONTRASTS):
        ax = _ax(fig, 30 + 52 * k, 16, 44, 66, H, W)
        for row, p in enumerate(keep):
            c = res["pairs"][p]["contrasts"].get(contrast_key(a, b)) or {}
            if c.get("ratio") is None:
                continue
            st = _style(p)
            ax.plot([c["lo"], c["hi"]], [row, row], color=st["color"], lw=0.9, ls=st["ls"])
            ax.plot([c["ratio"]], [row], marker="o", ms=3, color=st["color"], mfc=st["mfc"], mew=0.6)
            if sig(c, mode):
                ax.text(c["hi"], row, " *", va="center", fontsize=7, fontweight="bold", color=st["color"])
        ax.axvline(1.0, color="#1A1A1A", lw=0.5)
        ax.set_xscale("log")
        ratio_axis(ax)
        ax.set_ylim(len(keep) - 0.5, -0.5)
        ax.set_yticks(range(len(keep)))
        ax.set_yticklabels([PAIR_SAY[p] for p in keep] if k == 0 else [])
        ax.set_title("Session × (%s)" % say.lower(), fontsize=6, pad=2)
        ax.set_xlabel("Ratio of ratios", fontsize=5.5, labelpad=1)
        _letter(fig, 22 + 52 * k if k else 4, 15, "abc"[k], H, W)
    files = _save(fig, "fig_%s" % fid)
    plt.close(fig)
    return files


def ratio_axis(ax):
    """A log axis of ratios with plain-number ticks (0.5, 1, 2), not 10^-1."""
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    lo, hi = ax.get_xlim()
    ticks = [t for t in (0.2, 0.25, 0.33, 0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 5.0) if lo <= t <= hi]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: "%g" % v))
    ax.xaxis.set_minor_locator(NullLocator())


def tables_pair3(T, band, p, rats):
    cols = [("%s %s" % (d, PERIOD_SAY[w]), [_c(T["band"][w][band][(r, d)][p]) for r in rats]) for d in DAYS for w in PERIODS]
    return [{"title": "band by period", "rows": ["rat %d" % r for r in rats], "columns": cols,
             "note": "Each rat's %s coherence in the baseline, cue 1 and cue 2 (10 s, pooled spectra) on each day. In Prism: "
                     "Grouped table, two-way repeated measures." % band}]


def tables_pooled3(T, band, res):
    keep = [x["pair"] for x in res["pairs"] if x]
    rows = []
    for a, b, say in CONTRASTS:
        c = [res["pairs"][p]["contrasts"].get(contrast_key(a, b)) or {} for p in keep]
        rows.append({"title": say, "rows": [PAIR_SAY[p] for p in keep],
                     "columns": [("Ratio of ratios", [_c(x.get("ratio")) for x in c]), ("95% low", [_c(x.get("lo")) for x in c]),
                                 ("95% high", [_c(x.get("hi")) for x in c]), ("p", [_c(x.get("p")) for x in c]),
                                 ("FDR q", [_c(x.get("q")) for x in c])],
                     "note": "Session × (%s), GEE (Gamma, log link, robust errors)." % say.lower()})
    return rows


def legend_pair3(band, p, st):
    return {"title": "%s coherence between %s and %s in the baseline, cue 1 and cue 2, on Precon1 and Precon4." % (band.capitalize(), *PAIR_SAY[p].split("–")),
            "body": ("(a) Each 10 s window's coherence (pooled spectra over the session's trials), Precon1 solid, Precon4 dashed, mean ± "
                     "s.e.m. of %d rats. (b, c) Cue 1 − baseline and cue 2 − baseline across frequency, each rat's difference then their "
                     "mean ± s.e.m. GEE (Gamma, log link, exchangeable, the rat as the cluster): Session × Period on 2 df with robust "
                     "(Mancl–DeRouen) errors, and its three planned contrasts (Session × each pair of periods, 1 df), each corrected "
                     "across the ten pairs (Benjamini–Hochberg). * passes under the switch (FDR q < 0.05 on, p < 0.05 off)." % len(st["rats"]))}


def legend_pooled3(band, res):
    return {"title": "How the cue effect on %s coherence changed from Precon1 to Precon4, in all ten pairs." % band,
            "body": ("Each dot is the GEE's ratio of ratios: (cue ÷ baseline on Precon4) ÷ (cue ÷ baseline on Precon1), with its 95% "
                     "interval (robust errors); 1 is no change. (a) cue 1 against baseline; (b) cue 2 against baseline; (c) cue 2 against "
                     "cue 1. * passes under the switch.")}


# --------------------------------------------------------------------------
# Prism tables
# --------------------------------------------------------------------------
def _c(v):
    return None if v is None or not np.isfinite(v) else float("%.6g" % v)


def tables_pair1(T, band, p, rats):
    centers = [f for f, _m in bins_of(band)]
    out = [{"title": "c band means", "rows": ["rat %d" % r for r in rats],
            "columns": [(DAY_SAY[d], [_c(T["band"]["pair"][band][(r, d)][p]) for r in rats]) for d in DAYS],
            "note": "Each rat's %s coherence in the cue pair (pooled spectra). In Prism: Column table, before-after." % band}]
    for d in DAYS:
        out.append({"title": "d spectrum %s" % d, "rows": ["rat %d" % r for r in rats],
                    "columns": [("%.2f Hz" % c, [_c(T["bins"]["pair"][band][(r, d)][p, k]) for r in rats]) for k, c in enumerate(centers)],
                    "note": "Each rat's coherence in each frequency bin, %s; the violins (b) are these values, every rat's bins." % d})
    return out


def tables_pooled1(T, band, res):
    keep = [x["pair"] for x in res["pairs"] if x]
    rats = sorted({r for p in keep for r in res["pairs"][p]["rats"]})
    out = []
    for d in DAYS:
        out.append({"title": "band %s" % d, "rows": ["rat %d" % r for r in rats],
                    "columns": [(PAIR_SAY[p], [_c(T["band"]["pair"][band].get((r, d), [np.nan] * len(PAIRS))[p])
                                               if r in res["pairs"][p]["rats"] else None for r in rats]) for p in keep],
                    "note": "Each rat's %s coherence in each pair, %s." % (band, d)})
    return out


def tables_pair2(T, band, p, rats):
    cols = []
    for d in DAYS:
        for c in ("cue1", "cue2"):
            cols.append(("%s %s" % (d, c.replace("cue", "cue ")), [_c(T["band"][c][band][(r, d)][p]) for r in rats]))
    return [{"title": "cue means", "rows": ["rat %d" % r for r in rats], "columns": cols,
             "note": "Each rat's %s coherence in cue 1 and cue 2 on each day (pooled spectra, matched trials)." % band}]


def tables_pooled2(T, band, res):
    keep = [x["pair"] for x in res["pairs"] if x]
    rats = sorted({r for p in keep for r in res["pairs"][p]["rats"]})
    out = []
    for d in DAYS:
        for c in ("cue1", "cue2"):
            out.append({"title": "%s %s" % (d, c), "rows": ["rat %d" % r for r in rats],
                        "columns": [(PAIR_SAY[p], [_c(T["band"][c][band].get((r, d), [np.nan] * len(PAIRS))[p])
                                                   if r in res["pairs"][p]["rats"] else None for r in rats]) for p in keep],
                        "note": "Each rat's %s coherence in %s on %s." % (band, c, d)})
    return out


def _prism(stem, tables, what):
    from . import joefigs
    return joefigs.prism_files(stem, tables, what, into=figs_dir())


# --------------------------------------------------------------------------
# Legends (the words beside each figure)
# --------------------------------------------------------------------------
def legend_pair1(band, p, st, n_ip, n_co):
    a2 = st.get("a2") or {}
    return {"title": "%s coherence between %s and %s, Early (Precon1) against Late (Precon4)." % (band.capitalize(), *PAIR_SAY[p].split("–")),
            "body": ("(a) The five regions; this pair lit, its edge's width the change in its mean coherence. (b) Each rat's coherence "
                     "in every %s bin (%s), Early and Late; lines at the quartiles and median. (c) The mean of the rats ± s.e.m., each "
                     "rat in grey. (d) Coherence across frequency, Early solid, Late dashed, mean ± s.e.m.; inset, Late − Early per bin. "
                     "%d rats, %d wire pairs (%d ipsilateral, %d contralateral), each rat's value the mean of its valid wire pairs. "
                     "Coherence from pooled spectra: every 1 s segment (MATLAB hanning(1024), 512 overlap, FFT 2048, after a 59–61 Hz "
                     "band-stop) of every trial's 20 s cue pair in one cross-spectrum. GEE (Gamma, log link, exchangeable, the rat as "
                     "the cluster): Late/Early ×%s, χ²(1) = %s, %s, Benjamini–Hochberg q = %s across the ten pairs, on robust errors with "
                     "Mancl and DeRouen's correction. Session × frequency on the model's own errors."
                     % ("frequency" if band == "theta" else "2 Hz", "0.49 Hz bins" if band == "theta" else "2 Hz bins, 59–61 Hz left out",
                        len(st["rats"]), n_ip + n_co, n_ip, n_co, num(a2.get("ratio")), num(a2.get("chi2"), "%.2f"), p_say(a2.get("p")),
                        num(a2.get("q"), "%.3f")))}


def legend_pooled1(band, res):
    return {"title": "%s coherence in all ten region pairs, Early (Precon1) against Late (Precon4)." % band.capitalize(),
            "body": ("(a) The five regions with an edge per pair in its colour, its width the change in mean coherence, ▲ an increase "
                     "and ▼ a decrease, solid where Late vs Early passes after FDR. Pairs 9 and 10 reuse two colours, dash-dotted with "
                     "hollow markers. The omnibus GEE (A1 on the band, B1 across bins) beside it: terms of up to 2 df on robust "
                     "(Mancl–DeRouen) errors, terms of more df on the model's own errors, because robust errors from 8 rats "
                     "cannot test more than a few things at once. (b) Each rat's frequency bins, Early light and Late dark. (c) Mean ± "
                     "s.e.m. of the rats; * passes (FDR q < 0.05 with the correction on, p < 0.05 with it off). (d, e) Coherence across frequency on each day. (f) Late − Early per bin.")}


def legend_pair2(band, p, st):
    return {"title": "%s coherence between %s and %s during cue 1 and cue 2, on Precon1 and Precon4." % (band.capitalize(), *PAIR_SAY[p].split("–")),
            "body": ("Every Precon trial is a matched pairing (A→B or C→D); both are pooled. Each cue's 10 s window, pooled spectra "
                     "within the session. Mean of the rats ± s.e.m., each rat in grey. GEE per pair: Session × Cue (robust errors, "
                     "FDR across the ten pairs), and Cue 2 against Cue 1 on each day (FDR across the ten on that day; * passes under the switch).")}


def legend_pooled2(band, res):
    return {"title": "%s coherence during cue 1 and cue 2 in all ten pairs, Precon1 beside Precon4." % band.capitalize(),
            "body": ("Matched trials, pooled; the mean of the rats ± s.e.m. in each pair's colour. GEE Session × Cue × Pair beside it "
                     "(terms of up to 2 df on robust errors, the rest model-based); * Session × Cue in that pair passes (FDR q < 0.05 with "
                     "the correction on, p < 0.05 with it off).")}


# --------------------------------------------------------------------------
# Exports: every GEE row, an R script and SPSS syntax that refit them
# --------------------------------------------------------------------------
R_SCRIPT = r"""# Tab 11, Narrowing down (even more): the GEEs, refitted in R.
# install.packages(c("geepack")); then, in this folder: source("evenmore_gee.R")
# geepack gives the plain robust (sandwich) errors; Jarvis reports Mancl and
# DeRouen's bias-reduced ones for 1-df tests (geesmv::GEE.var.md gives them).
library(geepack)
d <- read.csv("evenmore_long.csv", stringsAsFactors = TRUE)
fit <- function(sub, f) {
  sub <- sub[order(sub$rat), ]
  sub$rat <- factor(sub$rat)
  m <- geeglm(f, id = rat, data = sub, family = Gamma(link = "log"), corstr = "exchangeable")
  print(anova(m))
  invisible(m)
}
for (b in c("theta", "gamma")) {
  cat("\n==== ", b, " ====\n")
  a1 <- subset(d, model == "A1" & band == b); fit(a1, y ~ day * pair)
  for (p in levels(droplevels(a1$pair))) { cat("\nA2", p, "\n"); fit(subset(a1, pair == p), y ~ day) }
  b1 <- subset(d, model == "B1" & band == b); fit(b1, y ~ day * pair * f)
  ph2 <- subset(d, model == "P2" & band == b); fit(ph2, y ~ day * cue * pair)
  ph3 <- subset(d, model == "P3" & band == b)
  for (p in levels(droplevels(ph3$pair))) { cat("\nP3", p, "\n"); fit(subset(ph3, pair == p), y ~ day * period) }
  for (p in levels(droplevels(ph2$pair))) { cat("\nP2", p, "\n"); fit(subset(ph2, pair == p), y ~ day * cue) }
}
"""


def sps_text():
    blocks = ["* Tab 11, Narrowing down (even more): the GEEs, refitted in SPSS.",
              "* SPSS's GENLIN gives the plain robust errors (no small-sample correction).",
              "GET DATA /TYPE=TXT /FILE='evenmore_long.csv' /DELIMITERS=',' /QUALIFIER='\"' /FIRSTCASE=2",
              "  /VARIABLES=model A3 band A6 rat F4.0 day A8 cue A5 period A12 pair A20 f A4 hz F8.3 y F12.8.",
              "DATASET NAME long.", ""]
    specs = (("A1", "day pair", "day*pair", "day*pair"),
             ("B1", "day pair f", "day*pair*f", "day*pair*f"),
             ("P2", "day cue pair", "day*cue*pair", "day*cue*pair"),
             ("P3", "day period pair", "day*period*pair", "day*period*pair"))
    for band in ("theta", "gamma"):
        for model, by, eff, within in specs:
            blocks += ["DATASET ACTIVATE long.", "TEMPORARY.", "SELECT IF (model = '%s' AND band = '%s')." % (model, band),
                       "GENLIN y BY %s (ORDER=ASCENDING)" % by,
                       "  /MODEL %s INTERCEPT=YES DISTRIBUTION=GAMMA LINK=LOG" % " ".join(by.split() + [eff]),
                       "  /REPEATED SUBJECT=rat WITHINSUBJECT=%s SORT=YES CORRTYPE=EXCHANGEABLE ADJUSTCORR=YES COVB=ROBUST" % within,
                       "  /PRINT MODELINFO FIT SUMMARY SOLUTION.", ""]
    return "\n".join(blocks)


def write_exports(out, p1, p2, p3=None):
    """evenmore_long.csv (every row every GEE saw), evenmore_results.csv
    (every test), the R script and SPSS syntax, a README; and a zip of them."""
    os.makedirs(export_dir(), exist_ok=True)
    long_rows = []
    for band in p1:
        res = p1[band]
        for r in res["rows"]:
            long_rows.append({"model": "A1", "band": band, "rat": r["rat"], "day": r["day"], "cue": "", "pair": PAIR_SAY[int(r["pair"][1:])],
                              "f": "", "hz": "", "y": r["y"]})
        for r in res["rows_bins"]:
            long_rows.append({"model": "B1", "band": band, "rat": r["rat"], "day": r["day"], "cue": "", "pair": PAIR_SAY[int(r["pair"][1:])],
                              "f": r["f"], "hz": "%.3f" % r["hz"], "y": r["y"]})
        for r in p2[band]["rows"]:
            long_rows.append({"model": "P2", "band": band, "rat": r["rat"], "day": r["day"], "cue": r["cue"],
                              "pair": PAIR_SAY[int(r["pair"][1:])], "f": "", "hz": "", "y": r["y"]})
        for r in ((p3 or {}).get(band) or {}).get("rows") or []:
            long_rows.append({"model": "P3", "band": band, "rat": r["rat"], "day": r["day"], "period": r["period"],
                              "pair": PAIR_SAY[int(r["pair"][1:])], "f": "", "hz": "", "y": r["y"]})
    cols = ["model", "band", "rat", "day", "cue", "period", "pair", "f", "hz", "y"]
    files = {}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in long_rows:
        w.writerow({k: ("%.9g" % r[k] if k == "y" else r.get(k, "")) for k in cols})
    files["evenmore_long.csv"] = buf.getvalue()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["band", "phase", "model", "pair", "test", "ratio", "chi2", "df", "p", "fdr_q", "errors"])
    for band in p1:
        for t in p1[band]["a1"] or []:
            w.writerow([band, 1, "A1 omnibus", "all", t["term"], "", "%.6g" % t["chi2"], t["df"], "%.6g" % t["p"], "", t["errors"]])
        for t in p1[band]["b1"] or []:
            w.writerow([band, 1, "B1 omnibus, bins", "all", t["term"], "", "%.6g" % t["chi2"], t["df"], "%.6g" % t["p"], "", t["errors"]])
        for x in p1[band]["pairs"]:
            if not x:
                continue
            a = x["a2"]
            if a:
                w.writerow([band, 1, "A2 per pair", PAIR_SAY[x["pair"]], "Late vs Early", "%.6g" % a["ratio"], "%.6g" % a["chi2"], 1,
                            "%.6g" % a["p"], "%.6g" % a["q"], a["errors"]])
            for t in x["b2"] or []:
                w.writerow([band, 1, "B2 per pair, bins", PAIR_SAY[x["pair"]], t["term"], "", "%.6g" % t["chi2"], t["df"], "%.6g" % t["p"],
                            ("%.6g" % x["b2_q"]) if t["term"] == "Session × Frequency" and x.get("b2_q") is not None else "", t["errors"]])
        for t in p2[band]["omnibus"] or []:
            w.writerow([band, 2, "Phase 2 omnibus", "all", t["term"], "", "%.6g" % t["chi2"], t["df"], "%.6g" % t["p"], "", t["errors"]])
        for x in p2[band]["pairs"]:
            if not x:
                continue
            for t in x["terms"] or []:
                w.writerow([band, 2, "Phase 2 per pair", PAIR_SAY[x["pair"]], t["term"], "", "%.6g" % t["chi2"], t["df"], "%.6g" % t["p"],
                            ("%.6g" % x["q"]) if t["term"] == "Session × Cue" and x.get("q") is not None else "", t["errors"]])
            for d, r in x["days"].items():
                if "ratio" in r:
                    w.writerow([band, 2, "Phase 2 cue effect", PAIR_SAY[x["pair"]], "Cue 2 vs Cue 1, %s" % d, "%.6g" % r["ratio"],
                                "%.6g" % r["chi2"], 1, "%.6g" % r["p"], ("%.6g" % r["q"]) if r.get("q") is not None else "", r["errors"]])
        for x in ((p3 or {}).get(band) or {}).get("pairs") or []:
            if not x:
                continue
            for t in x["terms"] or []:
                w.writerow([band, 3, "Periods per pair", PAIR_SAY[x["pair"]], t["term"], "", "%.6g" % t["chi2"], t["df"], "%.6g" % t["p"],
                            ("%.6g" % x["sp"]["q"]) if t["term"] == "Session × Period" and (x.get("sp") or {}).get("q") is not None else "",
                            t["errors"]])
            for a, b, say in CONTRASTS:
                c = x["contrasts"].get(contrast_key(a, b)) or {}
                if c.get("p") is not None:
                    w.writerow([band, 3, "Periods, planned contrast", PAIR_SAY[x["pair"]], "Session × (%s)" % say.lower(), "%.6g" % c["ratio"],
                                "%.6g" % c["chi2"], 1, "%.6g" % c["p"], ("%.6g" % c["q"]) if c.get("q") is not None else "", c["errors"]])
    files["evenmore_results.csv"] = buf.getvalue()
    files["evenmore_gee.R"] = R_SCRIPT
    files["evenmore_gee.sps"] = sps_text()
    files["evenmore_README.txt"] = readme_text(out)
    for n, text in files.items():
        with open(export_dir(n), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    zp = export_dir("evenmore_gee.zip")
    with zipfile.ZipFile(zp + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
        for n in files:
            z.write(export_dir(n), n)
    os.replace(zp + ".tmp", zp)
    return sorted(files) + ["evenmore_gee.zip"]


def readme_text(out):
    lines = ["Tab 11, Narrowing down (even more)", "=" * 34, "",
             "Dickson et al. 2022 (eNeuro, Figure 3) on our rats, as the Coherence Analysis Plan (draft, 2026-10-27) lays it out.", "",
             "WARNING, read first: " + FLAG, "",
             "Regions: RSC, dHC, ACC, OFC, PER (POR not reached). Ten region pairs. Within a rat, a region pair is the mean of its valid "
             "wire pairs, ipsilateral and contralateral alike (histology v2, probes scored 'y'); homotopic pairs are never used.",
             "Early = Precon1, Late = Precon4. Window: each trial's cue pair (20 s); phase 2: cue 1 and cue 2 (10 s each).",
             "Coherence: 59-61 Hz Butterworth band-stop (filtfilt), MATLAB hanning(1024), 512 overlap, FFT 2048, at 1 kHz; the wires tab 8 "
             "chose. Theta 5-12 Hz at 0.49 Hz bins; gamma 30-90 Hz in 2 Hz bins, 59-61 Hz left out.", "",
             "Statistics: GEE, Gamma family, log link, exchangeable working correlation, rat as the cluster. Tests of up to 2 df on robust "
             "errors with Mancl and DeRouen's small-sample correction; tests of more df on the model's own (naive) errors, "
             "because a robust covariance from 8 rats has rank 8 at most. Benjamini-Hochberg across the ten pairs for per-pair tests.", "",
             "Files:",
             "  evenmore_long.csv     every row each GEE was fitted to (model A1 band, B1 bins, P2 cues)",
             "  evenmore_results.csv  every test: chi-square, df, p, FDR q, which errors",
             "  evenmore_gee.R        refits them with geepack (plain robust errors)",
             "  evenmore_gee.sps      refits them with SPSS GENLIN (plain robust errors)", "",
             "Pooled against the mean of trials (cue pair, mean over rats and pairs):"]
    for band, f in (out.get("flag") or {}).items():
        for d in DAYS:
            x = f.get(d) or {}
            lines.append("  %s %s: pooled %s, mean of trials %s" % (band, d, num(x.get("pooled"), "%.4f"), num(x.get("trialmean"), "%.4f")))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# All of it
# --------------------------------------------------------------------------
def load_days():
    p = _root("days")
    out = {}
    if not os.path.isdir(p):
        return out
    for f in sorted(os.listdir(p)):
        if f.endswith(".npz") and not f.endswith(".tmp.npz"):
            arrs, meta = load_day(os.path.join(p, f))
            out[(int(meta["rat"]), meta["day"])] = (arrs, meta)
    return out


def measure(worker=None, workers=None):
    """Each tested rat-day's pooled spectra, once (cached by tab 8's day
    file, which holds the wires)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from . import monolith as MO
    man = MO.manifest()
    if not man:
        raise EvenMoreError("There is no Monolith manifest yet: Drift → Monolith makes it.", 409)
    names = list(man.get("regions") or sweep.regions())
    missing = [n for n in SIDE_NAMES if n not in names]
    if missing:
        raise EvenMoreError("The Monolith has no %s." % ", ".join(missing), 409)
    chan_map = {k: v for k, v in coupling.dewey_map().items() if k in SIDE_NAMES}
    os.makedirs(_root("days"), exist_ok=True)
    todo, have, notes = [], {}, []
    for d in man.get("days") or []:
        if d["day"] not in DAYS:
            continue
        jp = joe._day_path(d, joe.day_key(d, names))
        if not os.path.isfile(jp):
            raise EvenMoreError("Tab 8 has not measured r%d %s here: work tab 8 out first (tab 11 reads its wires)." % (d["rat"], d["day"]), 409)
        p = _day_path(d, day_key(d, jp))
        if os.path.isfile(p):
            have[(int(d["rat"]), d["day"])] = p
        else:
            todo.append((d, jp, p))
    if worker:
        worker.note(phase="evenmore", item="pooling the spectra of %d rat-days (%d already done)" % (len(todo), len(have)), i=0, of=len(todo))
    if todo:
        n = workers or max(1, min(4, (os.cpu_count() or 2) - 1))
        with ProcessPoolExecutor(max_workers=n) as ex:
            futs = {ex.submit(_compute_one, d, chan_map, jp, p): (d, p) for d, jp, p in todo}
            done = 0
            try:
                for f in as_completed(futs):
                    if worker:
                        worker.check()
                    d, p = futs[f]
                    try:
                        notes += f.result()["notes"]
                        have[(int(d["rat"]), d["day"])] = p
                    except Exception as exc:                 # noqa: BLE001
                        notes.append("r%d %s: not measured (%s)" % (d["rat"], d["day"], exc))
                    done += 1
                    if worker:
                        worker.note(phase="evenmore", i=done, of=len(todo), item="pooled r%d %s (%d of %d)" % (d["rat"], d["day"], done, len(todo)))
            except BaseException:
                for f in futs:
                    f.cancel()
                raise
    keep = {os.path.basename(p) for p in have.values()}
    for f in os.listdir(_root("days")):
        if f.endswith(".npz") and f not in keep:
            try:
                os.remove(_root("days", f))
            except OSError:
                pass
    return notes


def build(days=None, progress=None, check=None):
    """The models, the figures, the exports and evenmore.json, from the
    pooled rat-days."""
    import shutil
    days = days if days is not None else load_days()
    if not days:
        raise EvenMoreError("Nothing measured yet: press Work it out.", 409)
    T = tables(days)
    shutil.rmtree(figs_dir(), ignore_errors=True)
    os.makedirs(figs_dir(), exist_ok=True)
    for f in os.listdir(figs_dir()):
        try:
            os.remove(figs_dir(f))
        except OSError:
            pass
    rats = sorted({r for r, _d in days})
    out = {"schema": SCHEMA, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "rats": rats,
           "pairs": [{"id": p, "say": PAIR_SAY[p], "color": COLORS[p], "dashed": DASHED[p], "rats": pair_rats(T, p),
                      "wires": dict(zip(("ipsi", "contra"), wire_count(T, p, pair_rats(T, p))))} for p in range(len(PAIRS))],
           "flag": {}, "bands": [], "notes": sorted({n for _a, m in days.values() for n in m.get("notes") or []}),
           "segments": {"%s r%d" % (d, r): int(T["segments"][(r, d)].max()) for r, d in sorted(T["segments"])},
           "trials": {"%s r%d" % (d, r): len(m["trials"]) for (r, d), (_a, m) in sorted(days.items())},
           "method": {"seg": SEG, "step": STEP, "nfft": NFFT, "fs": FS, "gamma_step": GAMMA_STEP, "bands": [list(b) for b in BANDS]},
           "flag_say": FLAG}
    p1s, p2s, p3s = {}, {}, {}
    steps = len(BANDS) * 70
    k = 0

    def tick(s):
        nonlocal k
        k += 1
        if check:
            check()
        if progress:
            progress(k, steps, s)

    def both(draw, fid):
        """A figure under each side of the switch: fid (FDR on), fid_raw."""
        return draw("fdr", fid), draw("raw", fid + "_raw")
    robust = []
    for bid, _lo, _hi in BANDS:
        tick("%s: the GEEs (phase 1)" % bid)
        p1 = phase1(T, bid)
        tick("%s: the GEEs (phase 2)" % bid)
        p2 = phase2(T, bid)
        tick("%s: the GEEs (baseline, cue 1, cue 2)" % bid)
        p3 = phase3(T, bid)
        p1s[bid], p2s[bid], p3s[bid] = p1, p2, p3
        # the flag's numbers: pooled against the mean of trials
        fl = {}
        for d in DAYS:
            pooled, tm = [], []
            for p in range(len(PAIRS)):
                for r in pair_rats(T, p):
                    pooled.append(T["band"]["pair"][bid][(r, d)][p])
                    tm.append(T["trialmean"][bid][(r, d)][p])
            fl[d] = {"pooled": _mean(pooled), "trialmean": _mean(tm)}
        out["flag"][bid] = fl
        deltas = [(_mean([T["band"]["pair"][bid][(r, DAYS[1])][p] - T["band"]["pair"][bid][(r, DAYS[0])][p] for r in pair_rats(T, p)])
                   if p1["pairs"][p] else None) for p in range(len(PAIRS))]
        passes1 = {m: [sig((p1["pairs"][p] or {}).get("a2"), m) for p in range(len(PAIRS))] for m in MODES}
        figs1, figs2, figs3 = [], [], []
        bno = 1 if bid == "theta" else 2
        df1 = _frame(p1["rows"])
        df2 = _frame(p2["rows"])
        df3 = _frame(p3["rows"])
        for p in range(len(PAIRS)):
            st = p1["pairs"][p]
            if not st:
                continue
            tick("%s: %s, phase 1" % (bid, PAIR_SAY[p]))
            fid = "%d_1_%02d" % (bno, p + 1)
            fa, fr = both(lambda m, n: fig_pair_phase1(T, bid, p, st, deltas, passes1[m], n), fid)
            fa.update(_prism("fig_%s_prism" % fid, tables_pair1(T, bid, p, st["rats"]), "Figure %s" % fid))
            ip, co = wire_count(T, p, st["rats"])
            figs1.append({"id": fid, "kind": "pair", "phase": 1, "band": bid, "pair": p, "files": fa, "files_raw": fr,
                          "legend": legend_pair1(bid, p, st, ip, co), "passes": {m: passes1[m][p] for m in MODES}})
            if sig(st.get("a2"), "raw"):
                sub = df1[df1["pair"] == "p%02d" % p]
                robust.append(dict(robustness("phase1", bid, p, sub, lambda d_: ratio(gee(d_, "y ~ C(day, Treatment('Precon1'))"), "Precon4"),
                                              "y ~ C(day, Treatment('Precon1'))", ["Precon4"], label="Late vs Early"),
                                   test=st["a2"], passes={m: sig(st["a2"], m) for m in MODES}))
        tick("%s: all ten, phase 1" % bid)
        fid = "%d_1_all" % bno
        fa, fr = both(lambda m, n: fig_pooled_phase1(T, bid, p1, deltas, passes1[m], n, m), fid)
        fa.update(_prism("fig_%s_prism" % fid, tables_pooled1(T, bid, p1), "Figure %s" % fid))
        figs1.append({"id": fid, "kind": "pooled", "phase": 1, "band": bid, "files": fa, "files_raw": fr, "legend": legend_pooled1(bid, p1)})
        for p in range(len(PAIRS)):
            st = p2["pairs"][p]
            if not st:
                continue
            tick("%s: %s, phase 2" % (bid, PAIR_SAY[p]))
            fid = "%d_2_%02d" % (bno, p + 1)
            fa, fr = both(lambda m, n: fig_pair_phase2(T, bid, p, st, n, m), fid)
            fa.update(_prism("fig_%s_prism" % fid, tables_pair2(T, bid, p, st["rats"]), "Figure %s" % fid))
            figs2.append({"id": fid, "kind": "pair", "phase": 2, "band": bid, "pair": p, "files": fa, "files_raw": fr,
                          "legend": legend_pair2(bid, p, st), "passes": {m: sig(st, m) for m in MODES}})
            sc = {"p": _term_p(st["terms"], "Session × Cue"), "q": st.get("q")}
            if sig(sc, "raw"):
                sub = df2[df2["pair"] == "p%02d" % p]
                robust.append(dict(robustness("phase2", bid, p, sub,
                                              lambda d_: {"p": _term_p(terms(gee(d_, "y ~ C(day, Sum) * C(cue, Sum)")), "Session × Cue")},
                                              "y ~ C(day, Sum) * C(cue, Sum)", ["day", ":", "cue"], label="Session × Cue"),
                                   test=sc, passes={m: sig(sc, m) for m in MODES}))
        tick("%s: all ten, phase 2" % bid)
        fid = "%d_2_all" % bno
        fa, fr = both(lambda m, n: fig_pooled_phase2(T, bid, p2, n, m), fid)
        fa.update(_prism("fig_%s_prism" % fid, tables_pooled2(T, bid, p2), "Figure %s" % fid))
        figs2.append({"id": fid, "kind": "pooled", "phase": 2, "band": bid, "files": fa, "files_raw": fr, "legend": legend_pooled2(bid, p2)})
        for p in range(len(PAIRS)):
            st = p3["pairs"][p]
            if not st:
                continue
            tick("%s: %s, baseline, cue 1, cue 2" % (bid, PAIR_SAY[p]))
            fid = "%d_3_%02d" % (bno, p + 1)
            fa, fr = both(lambda m, n: fig_pair_phase3(T, bid, p, st, n, m), fid)
            fa.update(_prism("fig_%s_prism" % fid, tables_pair3(T, bid, p, st["rats"]), "Figure %s" % fid))
            figs3.append({"id": fid, "kind": "pair", "phase": 3, "band": bid, "pair": p, "files": fa, "files_raw": fr,
                          "legend": legend_pair3(bid, p, st), "passes": {m: sig(st.get("sp"), m) for m in MODES}})
            sub = df3[df3["pair"] == "p%02d" % p]
            if sig(st.get("sp"), "raw"):
                robust.append(dict(robustness("phase3", bid, p, sub,
                                              lambda d_: {"p": _term_p(terms(gee(d_, "y ~ C(day, Sum) * C(period, Sum)")), "Session × Period")},
                                              "y ~ C(day, Sum) * C(period, Sum)", [":"], label="Session × Period"),
                                   test=st["sp"], passes={m: sig(st["sp"], m) for m in MODES}))
            for a_, b_, say in CONTRASTS:
                c = st["contrasts"].get(contrast_key(a_, b_)) or {}
                if sig(c, "raw"):
                    two = sub[sub["period"].isin([PERIOD_CODE[a_], PERIOD_CODE[b_]])]
                    f_ = "y ~ C(day, Treatment('Precon1')) * C(period, Treatment('%s'))" % PERIOD_CODE[b_]
                    robust.append(dict(robustness("phase3", bid, p, two,
                                                  lambda d_, f_=f_, a_=a_: interaction(d_, f_, ["Precon4", PERIOD_CODE[a_]]),
                                                  f_, ["Precon4", PERIOD_CODE[a_]], label="Session × (%s)" % say.lower()),
                                       test=c, passes={m: sig(c, m) for m in MODES}))
        tick("%s: all ten, baseline, cue 1, cue 2" % bid)
        fid = "%d_3_all" % bno
        fa, fr = both(lambda m, n: fig_pooled_phase3(T, bid, p3, n, m), fid)
        fa.update(_prism("fig_%s_prism" % fid, tables_pooled3(T, bid, p3), "Figure %s" % fid))
        figs3.append({"id": fid, "kind": "pooled", "phase": 3, "band": bid, "files": fa, "files_raw": fr, "legend": legend_pooled3(bid, p3)})
        out["bands"].append({"band": bid, "say": joe.BAND_SAY[bid], "bins": [f for f, _m in bins_of(bid)],
                             "phase1": {"a1": p1["a1"], "a1_error": p1["a1_error"], "b1": p1["b1"], "b1_error": p1["b1_error"],
                                        "pairs": [_slim1(x) for x in p1["pairs"]], "deltas": deltas, "figures": figs1},
                             "phase2": {"omnibus": p2["omnibus"], "error": p2["error"], "pairs": [_slim2(x) for x in p2["pairs"]],
                                        "figures": figs2},
                             "phase3": {"pairs": p3["pairs"], "figures": figs3}})
    out["robust"] = robust
    out["modes"] = {m: MODE_SAY[m] for m in MODES}
    out["robust_max_df"] = ROBUST_MAX_DF
    out["exports"] = write_exports(out, p1s, p2s, p3s)
    joe._write(_root("evenmore.json"), out)
    return out


def _slim1(x):
    if not x:
        return None
    return {"pair": x["pair"], "rats": x["rats"], "a2": x["a2"], "a2_error": x["a2_error"], "b2": x["b2"], "b2_error": x["b2_error"],
            "b2_q": x.get("b2_q")}


def _slim2(x):
    if not x:
        return None
    return {"pair": x["pair"], "rats": x["rats"], "terms": x["terms"], "error": x["error"], "days": x["days"], "q": x.get("q")}


def result():
    p = _root("evenmore.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def work(worker):
    notes = measure(worker)
    out = build(progress=lambda i, n, s: worker.note(phase="evenmore-figs", i=i, of=n, item=s), check=worker.check)
    out["notes"] = sorted(set(out["notes"]) | set(notes))
    joe._write(_root("evenmore.json"), out)
    return {"figures": sum(len(b[k]["figures"]) for b in out["bands"] for k in ("phase1", "phase2", "phase3")), "rat_days": len(out["trials"])}


def work_safe(worker):
    from . import monolith as MO
    try:
        return work(worker)
    except (EvenMoreError, joe.JoeError) as exc:
        raise MO.MonolithError(str(exc), exc.status)


if __name__ == "__main__":
    import sys
    from . import monolith as MO
    MO.configure(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "GUI_logs"))

    class _W:
        def note(self, **kw):
            print(kw.get("item"), flush=True)

        def check(self):
            pass
    if sys.argv[1:2] == ["build"]:
        o = build(progress=lambda i, n, s: print("%d/%d %s" % (i, n, s), flush=True))
        print(len(o["bands"]), "bands")
    else:
        print(work(_W()))
