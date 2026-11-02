"""
ied_ds_lit.py -- literature-grounded features for telling a dentate spike from
an interictal epileptiform discharge, and an honestly cross-validated test of
whether they do.

WHERE THE FEATURES COME FROM
============================
Dentate spikes (Bragin, Jando, Nadasdy, van Landeghem & Buzsaki, J Neurophys
1995): large-amplitude (2-4 mV), SHORT-duration (< 30 ms) field spikes in the
hilus, occurring in immobility and slow-wave sleep, whose defining signature is
a CURRENT SINK in the dentate molecular layer -- outer third for DS1, middle
third for DS2 -- with the source in the hilus. The sink location is the
classification, and it is a CSD measurement, not a voltage one.

IEDs: the spike proper runs 20-70 ms with a sharp up- and down-slope, often
followed by a slow wave of 70-200 ms; the morphology features the epilepsy
literature actually uses are maximum amplitude, SPIKE SLOPE, and spectral
power by band. The other half is high-frequency: HFOs span 80-500 Hz, and
spontaneous FAST ripples (250-600 Hz) are taken to be always pathological,
where ripples (80-250 Hz) can be either. Pathological HFOs are reported with
higher relative amplitude, longer duration, and LOWER spectral entropy (more
narrowband) than physiological ones.

So the feature set is three blocks, each from a different literature:

  SPECTRAL     fast-ripple and ripple power against the event's own baseline,
               their ratio, MUA-band power, spectral entropy, HFO duration
  MORPHOLOGY   amplitude, half-width, maximum slope, sharpness, rise/fall
               asymmetry, and the post-spike slow wave
  LAMINAR      CSD sink depth and region, sink/source dipole separation, and
               how far the event spreads along the probe

FILTERING, DONE THE WAY THE METHODS SECTIONS DO IT
==================================================
  LFP / morphology   1-100 Hz     shape and amplitude of the field spike
  ripple             80-250 Hz
  fast ripple        250-600 Hz
  MUA proxy          600-2000 Hz
  slow wave          1-8 Hz       the after-going wave

All zero-phase (sosfiltfilt), because every timing measurement here -- peak
latency, half-width, HFO duration -- is a time, and a causal filter shifts
times by an amount that varies with frequency.

THE FILTER-RINGING TRAP, AND WHAT IS DONE ABOUT IT
==================================================
Band-passing a sharp transient makes the filter ring, and the ringing looks
exactly like an HFO. That is the standard false-ripple artefact and it would
hit IEDs hardest, since they are the sharper events -- manufacturing the very
result this is testing for. Three guards, all reported per event:

  spec_entropy   ringing is broadband and gives HIGH entropy; a real
                 oscillation is narrowband and gives low entropy
  hfo_cycles     how many cycles the envelope actually sustains. Filter
                 ringing decays within a cycle or two of the transient
  fooof_peak_pw  a fitted peak standing above the aperiodic 1/f. A transient
                 raises the aperiodic component and produces no peak

A "fast ripple" that is high-amplitude, high-entropy, short and peakless is
the artefact; one that is narrowband, sustained and has a spectral peak is not.

CROSS-VALIDATION IS NOT OPTIONAL HERE
=====================================
13 IEDs against 296 dentate spikes, with seventeen features. An LDA fitted and
scored on the same 309 rows will report a beautiful AUC that means nothing:
with 17 free parameters and 13 positives it can memorise the positives. Every
separability number this module reports is therefore out-of-fold, from
repeated stratified k-fold, and is quoted next to the in-sample number so the
size of the gap is visible. A permutation null is included for the same
reason: with n=13 the CV score itself has a wide distribution, and "better
than chance" has to mean better than the label-shuffled distribution.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.signal import butter, hilbert, sosfiltfilt, welch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ied_ds import Probe64, read_ds_bank, read_ied_events       # noqa: E402
from ied_ds_store import EventStore                             # noqa: E402

# Bands, in Hz. Named from the literature rather than from the data.
BANDS = {
    "lfp": (1.0, 100.0),
    "slow": (1.0, 8.0),
    "ripple": (80.0, 250.0),
    "fast_ripple": (250.0, 600.0),
    "mua": (600.0, 2000.0),
}

# The store v7 reads: 5 kHz, lowpassed at 2000 Hz, +-200 ms. Same cache v5
# built, so switching between them costs nothing.
STORE = dict(half_ms=200.0, lowpass=2000.0, q=6)

BASE_OFFSET_MS = 150.0      # centre of the baseline window, before the event
BASE_WIN_MS = 40.0
EVENT_WIN_MS = 25.0         # the event window every band power is taken over
SLOW_FROM_MS, SLOW_TO_MS = 50.0, 180.0     # the post-spike slow wave

# CSD. The pitch scales the magnitude but not where the sink is, which is what
# the classification uses; stated so the units are not mistaken for measured.
PITCH_UM = 30.0
COND_S_PER_M = 0.3

FEATURES = [
    # spectral
    "fr_db", "ripple_db", "mua_db", "fr_ripple_ratio", "spec_entropy",
    "hfo_cycles", "fooof_exp", "fooof_peak_pw",
    # morphology
    "amp_uV", "hw_ms", "max_slope", "sharpness", "asym", "slow_wave_uV",
    # laminar
    "csd_sink_row", "csd_dipole_rows", "spread_contacts",
]


def build(probe=None, category="Solid", progress=None, refresh=False):
    p = probe or Probe64()
    st = EventStore.build(p, read_ied_events(category=category),
                          read_ds_bank(), progress=progress, refresh=refresh,
                          **STORE)
    return p, st


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------
def bp(x, fs, band):
    lo, hi = band
    nyq = fs / 2.0
    hi = min(hi, nyq * 0.98)
    if lo <= 0:
        sos = butter(4, hi / nyq, btype="low", output="sos")
    else:
        sos = butter(4, [lo / nyq, hi / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, np.asarray(x, dtype=float), axis=0)


def envelope(x, fs, band):
    return np.abs(hilbert(bp(x, fs, band), axis=0))


# --------------------------------------------------------------------------
# CSD -- the dentate-spike signature
# --------------------------------------------------------------------------
def csd(lfp, included, pitch_um=PITCH_UM, sigma=COND_S_PER_M, smooth=1.0):
    """Second spatial derivative of the field, with bad contacts filled in.

    A CSD is a second difference over NEIGHBOURING contacts, so a dead channel
    does not just lose one row -- it corrupts the two either side of it. The
    bad contacts are therefore interpolated from their neighbours before the
    derivative rather than dropped, and the rows that were interpolated are
    still marked bad for anything that reads a value off them.
    """
    y = np.array(lfp, dtype=float)              # [T, nch]
    n = y.shape[1]
    good = np.where(included)[0]
    for c in np.where(~included)[0]:
        if good.size < 2:
            break
        lo_ = good[good < c]
        hi_ = good[good > c]
        if lo_.size and hi_.size:               # linear between the neighbours
            a, b = int(lo_[-1]), int(hi_[0])
            y[:, c] = ((b - c) * y[:, a] + (c - a) * y[:, b]) / (b - a)
        else:                                   # at an end: nearest good row
            y[:, c] = y[:, int(lo_[-1] if lo_.size else hi_[0])]
    # Gaussian smoothing along depth, which every CSD does to keep the second
    # difference from amplifying contact-to-contact noise.
    if smooth and smooth > 0:
        k = np.exp(-0.5 * (np.arange(-3, 4) / float(smooth)) ** 2)
        k /= k.sum()
        y = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, y)
    h = pitch_um * 1e-6
    v = y * 1e-6                                 # uV -> V
    # Vaknin extension: duplicate the end rows so the CSD is defined there too.
    ext = np.concatenate([v[:, :1], v, v[:, -1:]], axis=1)
    out = -sigma * (ext[:, :-2] - 2 * ext[:, 1:-1] + ext[:, 2:]) / (h * h)
    return out                                   # A/m^3


# --------------------------------------------------------------------------
# Spectra
# --------------------------------------------------------------------------
def _psd(x, fs, nperseg=256):
    n = len(x)
    nper = min(int(nperseg), n)
    if nper < 16:
        return np.array([np.nan]), np.array([np.nan])
    return welch(x, fs=fs, nperseg=nper, noverlap=nper // 2, scaling="density")


def _bandpow(f, P, band):
    m = (f >= band[0]) & (f < band[1])
    return float(np.trapezoid(P[m], f[m])) if m.sum() > 1 else np.nan


def spectral_entropy(f, P, band):
    """Shannon entropy of the normalised PSD in `band`, in [0, 1].

    High means flat (broadband -- what filter ringing on a transient gives);
    low means peaked (a real narrowband oscillation).
    """
    m = (f >= band[0]) & (f < band[1])
    p = P[m]
    p = p[np.isfinite(p) & (p > 0)]
    if p.size < 4:
        return np.nan
    p = p / p.sum()
    return float(-(p * np.log(p)).sum() / np.log(p.size))


# --------------------------------------------------------------------------
# Per-event features
# --------------------------------------------------------------------------
def event_features(st, p, i, shift, anat_rows=None):
    fs = st.fs
    y = st.trace(i)                                    # [T, 64]
    c = st.stamp_i + int(shift)
    inc = p.included

    ew = int(round(EVENT_WIN_MS * 1e-3 * fs))
    lo, hi = max(0, c - ew), min(y.shape[0], c + ew + 1)
    bo = int(round(BASE_OFFSET_MS * 1e-3 * fs))
    bw = int(round(BASE_WIN_MS / 2 * 1e-3 * fs))
    blo, bhi = max(0, c - bo - bw), max(1, c - bo + bw)

    # ---- the contact the event is largest on, in the LFP band --------------
    lfp = bp(y, fs, BANDS["lfp"])
    base_lfp = np.median(lfp, axis=0)
    dev = np.abs(lfp[lo:hi] - base_lfp)
    per = np.where(inc, dev.max(axis=0), -np.inf)
    w = int(np.argmax(per))
    trace = lfp[:, w]

    out = {"contact_row": w, "csc": int(p.numbers[w]),
           "region": p.region.get(int(p.numbers[w]), "")}

    # ---- morphology --------------------------------------------------------
    seg = trace[lo:hi] - base_lfp[w]
    k = int(np.argmax(np.abs(seg)))
    amp = float(np.abs(seg[k]))
    sgn = np.sign(seg[k]) or 1.0
    s = sgn * (trace - base_lfp[w])
    pk = lo + k
    half = 0.5 * amp
    li = pk
    while li > 0 and s[li] >= half:
        li -= 1
    ri = pk
    while ri < len(s) - 1 and s[ri] >= half:
        ri += 1
    out["amp_uV"] = amp
    out["hw_ms"] = (ri - li) / fs * 1e3
    d1 = np.gradient(s, 1.0 / fs * 1e3)                # uV per ms
    d2 = np.gradient(d1, 1.0 / fs * 1e3)
    out["max_slope"] = float(np.max(np.abs(d1[lo:hi])))
    # Curvature at the peak, normalised by amplitude: how "sharp" the spike is
    # independent of how big it is, which is what the IED literature means by
    # sharpness as against amplitude.
    out["sharpness"] = float(np.abs(d2[pk]) / amp) if amp > 0 else np.nan
    rise = (pk - li) / fs * 1e3
    fall = (ri - pk) / fs * 1e3
    out["asym"] = float((rise - fall) / (rise + fall)) if (rise + fall) > 0 else np.nan
    out["peak_ms"] = (pk - c) / fs * 1e3

    # post-spike slow wave, same polarity convention as the spike
    sw = bp(y[:, w], fs, BANDS["slow"])
    a = c + int(round(SLOW_FROM_MS * 1e-3 * fs))
    b_ = min(len(sw), c + int(round(SLOW_TO_MS * 1e-3 * fs)))
    out["slow_wave_uV"] = (float(np.mean(sw[a:b_]) * sgn) if b_ > a + 2
                           else np.nan)

    # ---- spectral ----------------------------------------------------------
    # The same nperseg for both, so the two PSDs land on the SAME frequency
    # grid. The event and baseline windows are different lengths, and letting
    # welch pick its own segment for each returns grids of different size --
    # which a band mask built from one and applied to the other indexes wrongly
    # rather than failing cleanly.
    nper = min(hi - lo, bhi - blo, 256)
    # The HFO need not sit on the contact where the FIELD is largest -- the
    # literature localises HFOs to their own contact, and measuring them on
    # the LFP peak instead costs real separation (AUC 0.80 against 0.91 when
    # this was read off the wrong contact). So the spectral block gets its own
    # winner: the contact with the most fast-ripple power over baseline.
    wh, best = w, -np.inf
    for ch in np.where(inc)[0]:
        fe, pe_ = _psd(y[lo:hi, ch], fs, nper)
        fb_, pb_ = _psd(y[blo:bhi, ch], fs, nper)
        a_ = _bandpow(fe, pe_, BANDS["fast_ripple"])
        b2 = _bandpow(fb_, pb_, BANDS["fast_ripple"])
        if a_ and b2 and a_ > 0 and b2 > 0:
            v = 10 * np.log10(a_ / b2)
            if v > best:
                wh, best = int(ch), v
    out["hf_contact_row"] = wh
    out["hf_csc"] = int(p.numbers[wh])
    out["hf_region"] = p.region.get(int(p.numbers[wh]), "")
    f, Pe = _psd(y[lo:hi, wh], fs, nper)
    fb, Pb = _psd(y[blo:bhi, wh], fs, nper)
    assert len(f) == len(fb), "event and baseline PSD grids differ"

    def d_b(band):
        pe, pbb = _bandpow(f, Pe, band), _bandpow(f, Pb, band)
        return (10 * np.log10(pe / pbb) if (pe and pbb and pe > 0 and pbb > 0)
                else np.nan)
    out["fr_db"] = d_b(BANDS["fast_ripple"])
    out["ripple_db"] = d_b(BANDS["ripple"])
    out["mua_db"] = d_b(BANDS["mua"])
    pr, pf = _bandpow(f, Pe, BANDS["ripple"]), _bandpow(f, Pe, BANDS["fast_ripple"])
    out["fr_ripple_ratio"] = (10 * np.log10(pf / pr)
                              if (pr and pf and pr > 0 and pf > 0) else np.nan)
    out["spec_entropy"] = spectral_entropy(f, Pe, (80.0, 600.0))

    # how many cycles the fast-ripple envelope actually sustains
    env = envelope(y[:, wh], fs, BANDS["fast_ripple"])
    thr = np.median(env[blo:bhi]) + 3.0 * np.std(env[blo:bhi])
    over = env[lo:hi] > thr
    dur_ms = float(over.sum()) / fs * 1e3
    mid = 0.5 * (BANDS["fast_ripple"][0] + BANDS["fast_ripple"][1])
    out["hfo_cycles"] = dur_ms * mid / 1e3
    out["hfo_dur_ms"] = dur_ms

    # ---- laminar -----------------------------------------------------------
    cs = csd(lfp[lo:hi], inc)
    prof = cs[np.argmax(np.abs(cs).max(axis=1)), :]    # at the CSD's own peak
    prof = np.where(inc, prof, np.nan)
    if np.isfinite(prof).any():
        sink = int(np.nanargmin(prof))                 # sink = negative CSD
        src = int(np.nanargmax(prof))
        out["csd_sink_row"] = float(sink)
        out["csd_source_row"] = float(src)
        out["csd_dipole_rows"] = float(abs(src - sink))
        out["csd_sink_region"] = p.region.get(int(p.numbers[sink]), "")
        out["csd_sink_uV"] = float(prof[sink])
    else:
        for key in ("csd_sink_row", "csd_source_row", "csd_dipole_rows",
                    "csd_sink_uV"):
            out[key] = np.nan
        out["csd_sink_region"] = ""
    big = np.abs(lfp[lo:hi] - base_lfp).max(axis=0)
    out["spread_contacts"] = float(np.sum(inc & (big >= 0.5 * amp)))
    out["railed"] = bool(st.rail[i, lo:hi, :][:, inc].any())
    return out


def add_fooof(tab, st, p, shifts, fit_range=(100.0, 2000.0)):
    """Aperiodic exponent and the biggest fitted peak in the fast-ripple band."""
    try:
        from fooof import FOOOF
    except Exception:
        tab["fooof_exp"] = np.nan
        tab["fooof_peak_pw"] = np.nan
        return tab
    exps, pws = [], []
    for _, r in tab.iterrows():
        i, w = int(r["idx"]), int(r.get("hf_contact_row", r["contact_row"]))
        c = st.stamp_i + int(shifts[i])
        ew = int(round(EVENT_WIN_MS * 1e-3 * st.fs))
        f, P = _psd(st.trace(i)[max(0, c - ew):c + ew + 1, w], st.fs)
        ok = np.isfinite(P) & (P > 0)
        e = pw = np.nan
        if ok.sum() >= 8:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fm = FOOOF(peak_width_limits=[20.0, 250.0], max_n_peaks=4,
                           min_peak_height=0.05, aperiodic_mode="fixed",
                           verbose=False)
                try:
                    fm.fit(f[ok], P[ok], fit_range)
                    e = float(fm.aperiodic_params_[-1])
                    pk = fm.peak_params_
                    if pk is not None and len(pk):
                        inb = pk[(pk[:, 0] >= BANDS["fast_ripple"][0]) &
                                 (pk[:, 0] < BANDS["fast_ripple"][1])]
                        pw = float(inb[:, 1].max()) if len(inb) else 0.0
                except Exception:
                    pass
        exps.append(e)
        pws.append(pw)
    tab["fooof_exp"] = exps
    tab["fooof_peak_pw"] = pws
    return tab


def all_features(st, p, shifts, with_fooof=True, progress=None):
    rows = []
    for i in range(len(st)):
        if progress and i % 60 == 0:
            progress(i, len(st), "features")
        f = event_features(st, p, i, shifts[i])
        f.update({"kind": str(st.kinds[i]), "id": int(st.ids[i]),
                  "t_s": float(st.t_s[i]), "idx": i})
        rows.append(f)
    tab = pd.DataFrame(rows)
    if with_fooof:
        if progress:
            progress(0, 1, "FOOOF per event")
        tab = add_fooof(tab, st, p, shifts)
    return tab


# --------------------------------------------------------------------------
# Separability, cross-validated
# --------------------------------------------------------------------------
def prep_matrix(tab, features):
    X = np.array(tab[list(features)].to_numpy(dtype=float), copy=True)
    # Median-fill rather than dropping rows: a feature that is NaN on a handful
    # of events would otherwise silently delete those events from the
    # comparison, and with 13 positives that changes the answer.
    med = np.nanmedian(X, axis=0)
    bad = ~np.isfinite(X)
    X[bad] = np.take(med, np.where(bad)[1])
    y = (tab["kind"] == "IED").to_numpy().astype(int)
    return X, y


def evaluate(tab, features, n_splits=5, n_repeats=20, seed=0,
             n_perm=200, model="lda"):
    """Out-of-fold AUC, the in-sample AUC beside it, and a permutation null."""
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import RepeatedStratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X, y = prep_matrix(tab, features)

    def mk():
        est = (LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
               if model == "lda" else
               LogisticRegression(max_iter=2000, class_weight="balanced"))
        return make_pipeline(StandardScaler(), est)

    def cv_auc(yy, rng_seed):
        cv = RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=n_repeats,
                                     random_state=rng_seed)
        sc = []
        for tr, te in cv.split(X, yy):
            if len(np.unique(yy[tr])) < 2 or len(np.unique(yy[te])) < 2:
                continue
            m = mk().fit(X[tr], yy[tr])
            s = (m.decision_function(X[te]) if hasattr(m, "decision_function")
                 else m.predict_proba(X[te])[:, 1])
            sc.append(roc_auc_score(yy[te], s))
        return np.array(sc)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scores = cv_auc(y, seed)
        full = mk().fit(X, y)
        insample = roc_auc_score(y, full.decision_function(X))
        rng = np.random.default_rng(seed)
        null = []
        for _ in range(n_perm):
            yp = rng.permutation(y)
            cv = RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=1,
                                         random_state=int(rng.integers(1e6)))
            s = []
            for tr, te in cv.split(X, yp):
                if len(np.unique(yp[tr])) < 2 or len(np.unique(yp[te])) < 2:
                    continue
                m = mk().fit(X[tr], yp[tr])
                s.append(roc_auc_score(yp[te], m.decision_function(X[te])))
            if s:
                null.append(np.mean(s))
    null = np.array(null) if null else np.array([0.5])
    mean = float(np.mean(scores)) if scores.size else np.nan
    return {
        "cv_auc": mean,
        "cv_sd": float(np.std(scores)) if scores.size else np.nan,
        "in_sample_auc": float(insample),
        "null_mean": float(np.mean(null)),
        "null_p95": float(np.percentile(null, 95)),
        "p_perm": float((null >= mean).mean()) if scores.size else np.nan,
        "n_features": len(features),
        "coef": getattr(full[-1], "coef_", np.zeros((1, len(features)))).ravel(),
        "features": list(features),
    }


def run_pca(tab, features, standardize=True):
    from sklearn.decomposition import PCA
    X, y = prep_matrix(tab, features)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd if standardize else X - mu
    pca = PCA(n_components=min(len(features), Z.shape[0]))
    S = pca.fit_transform(Z)
    return {"scores": S, "explained": pca.explained_variance_ratio_,
            "loadings": pca.components_, "features": list(features),
            "y": y.astype(bool)}


def auc1(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=bool)
    ok = np.isfinite(x)
    x, y = x[ok], y[ok]
    if y.sum() == 0 or (~y).sum() == 0:
        return np.nan
    r = pd.Series(x).rank().to_numpy()
    n1, n0 = int(y.sum()), int((~y).sum())
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def _selftest():
    import time
    def prog(i, n, msg):
        print("  [%3d/%3d] %s" % (i, n, msg))
    p, st = build(progress=prog)
    shifts, _ = st.centre_all(np.zeros(len(st), dtype=int), 50.0,
                              "mean|amp| peak", True)
    t = time.time()
    tab = all_features(st, p, shifts, progress=prog)
    print("features for %d events in %.1f s" % (len(tab), time.time() - t))

    y = (tab["kind"] == "IED").to_numpy()
    print("\n%-18s %8s   %s" % ("feature", "AUC", "IED med / DS med"))
    for f in FEATURES:
        if f not in tab.columns:
            continue
        a = auc1(tab[f].to_numpy(), y)
        print("%-18s %8.3f   %9.2f / %-9.2f" %
              (f, a, tab[f][y].median(), tab[f][~y].median()))

    print("\nCSD sink region, where the dentate-spike signature lives:")
    for kind in ("IED", "DS"):
        vc = tab[tab["kind"] == kind]["csd_sink_region"].value_counts().head(4)
        print("  %-4s %s" % (kind, ", ".join("%s x%d" % (k, v)
                                             for k, v in vc.items())))

    print("\n--- separability, out-of-fold ---")
    sets = {
        "amp + half-width (v6)": ["amp_uV", "hw_ms"],
        "morphology only": ["amp_uV", "hw_ms", "max_slope", "sharpness",
                            "asym", "slow_wave_uV"],
        "spectral only": ["fr_db", "ripple_db", "mua_db", "fr_ripple_ratio",
                          "spec_entropy", "hfo_cycles", "fooof_exp",
                          "fooof_peak_pw"],
        "laminar only": ["csd_sink_row", "csd_dipole_rows", "spread_contacts"],
        "ALL": FEATURES,
    }
    print("%-24s %14s %12s %10s %8s" %
          ("feature set", "CV AUC", "in-sample", "null p95", "p_perm"))
    for name, fs_ in sets.items():
        fs_ = [f for f in fs_ if f in tab.columns]
        r = evaluate(tab, fs_, n_repeats=10, n_perm=100)
        print("%-24s %6.3f +- %.3f %12.3f %10.3f %8.3f" %
              (name, r["cv_auc"], r["cv_sd"], r["in_sample_auc"],
               r["null_p95"], r["p_perm"]))


if __name__ == "__main__":
    _selftest()
