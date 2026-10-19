"""Twenty-five more numbers from each candidate's waveform, for AI Beta.

The user, 2026-10-03: "experiment with extracting 25 bits of more
information from the waveform", toward a detector that leaves people as
little garbage to sift through as possible.

The trees already see the waveform -- 51 samples of the trace on the
channel where the event is largest, the shank's CSD over time and the depth
profile (AI Beta's "waves" family). What they cannot do is arithmetic
across those samples: a width, a slope, how symmetric it is, how jagged,
where its power sits in frequency. Each of those takes a tree dozens of
splits to approximate and it never quite does. So they are worked out here,
from the stored samples, and handed over as numbers.

Worked out from features already read and cached -- never from the
recording -- so adding them costs a retrain, not a re-read, and a sweep
computes exactly what training did. Label-free, and nothing anatomical: no
layer sheets, no depths but each candidate's own peak channel.
"""
import numpy as np

FAMILY = {
    "id": "wavebits", "name": "Waveform measures",
    "blurb": "Twenty-five numbers worked out from the waveform the model "
             "already sees: when it peaks, how wide, how fast it rises and "
             "falls, how symmetric, how jagged, where its power sits in "
             "frequency, how quiet either side of it is, and how its CSD "
             "lines up with it.",
}

NAMES = [
    "wb_peak_ms",        # when the largest excursion is, from the stamp
    "wb_trough_pre",     # the deepest dip before it, the peak being 1
    "wb_trough_post",    # and after it
    "wb_fwhm_ms",        # its width at half height, interpolated
    "wb_rise_ms",        # 20% to the peak, on the way up
    "wb_decay_ms",       # the peak back down to 20%
    "wb_rise_slope",     # steepest climb before the peak, per ms
    "wb_decay_slope",    # steepest fall after it, per ms
    "wb_symmetry",       # the 20 ms either side of the peak, one mirrored
    "wb_skew",
    "wb_kurtosis",
    "wb_n_peaks",        # local maxima standing a quarter of the peak tall
    "wb_second_peak",    # the next tallest of them, the peak being 1
    "wb_zero_cross",     # crossings of its own mean
    "wb_jagged",         # second-difference energy over first-difference
    "wb_hf_frac",        # power above 60 Hz, of all of it
    "wb_centroid_hz",    # where its power sits
    "wb_core_energy",    # energy within 10 ms of the peak, of all of it
    "wb_flank_sd",       # how much it moves more than 25 ms from the peak
    "wb_tilt",           # the last 10 ms against the first 10 ms
    "wb_area_pos",       # how much of its area is above zero
    "wb_csd_lag_ms",     # the CSD's peak against the trace's
    "wb_csd_corr",       # the CSD's time course against the trace's
    "wb_csd_fwhm_ms",    # the CSD's width at half height
    "wb_profile_flips",  # sign changes down the depth profile
]


def _fwhm(v, k, step_ms):
    """Width at half of v[k], with the crossings interpolated."""
    h = v[k] / 2.0
    if not np.isfinite(h) or h <= 0:
        return np.nan
    lo = k
    while lo > 0 and v[lo - 1] > h:
        lo -= 1
    hi = k
    while hi < v.size - 1 and v[hi + 1] > h:
        hi += 1
    left = lo - ((v[lo] - h) / (v[lo] - v[lo - 1])) if lo > 0 and \
        v[lo] != v[lo - 1] else float(lo)
    right = hi + ((v[hi] - h) / (v[hi] - v[hi + 1])) if hi < v.size - 1 \
        and v[hi] != v[hi + 1] else float(hi)
    return (right - left) * step_ms


def _one(w, c, prof, step_ms):
    n = w.size
    out = np.full(len(NAMES), np.nan)
    if not np.all(np.isfinite(w)) or np.max(np.abs(w)) <= 0:
        return out
    mid = n // 2
    # The peak is looked for within 20 ms of the stamp; the trace is
    # scaled so the event's own peak is 1, so this finds that peak.
    reach = max(1, int(round(20.0 / step_ms)))
    lo, hi = max(0, mid - reach), min(n, mid + reach + 1)
    k = lo + int(np.argmax(w[lo:hi]))
    pk = w[k]
    if pk <= 0:
        pk = float(np.max(np.abs(w)))
    v = w / pk
    out[0] = (k - mid) * step_ms
    out[1] = float(v[:k].min()) if k > 0 else np.nan
    out[2] = float(v[k + 1:].min()) if k < n - 1 else np.nan
    out[3] = _fwhm(v, k, step_ms)
    q = k
    while q > 0 and v[q] > 0.2:
        q -= 1
    out[4] = (k - q) * step_ms
    q = k
    while q < n - 1 and v[q] > 0.2:
        q += 1
    out[5] = (q - k) * step_ms
    d = np.diff(v) / step_ms
    out[6] = float(d[:k].max()) if k > 0 else np.nan
    out[7] = float(-d[k:].min()) if k < n - 1 else np.nan
    s = max(1, int(round(20.0 / step_ms)))
    a, b = v[max(0, k - s):k][::-1], v[k + 1:k + 1 + s]
    m = min(a.size, b.size)
    if m >= 3 and np.std(a[:m]) > 0 and np.std(b[:m]) > 0:
        out[8] = float(np.corrcoef(a[:m], b[:m])[0, 1])
    mu, sd = float(v.mean()), float(v.std())
    if sd > 0:
        z = (v - mu) / sd
        out[9] = float(np.mean(z ** 3))
        out[10] = float(np.mean(z ** 4))
    tops = [j for j in range(1, n - 1)
            if v[j] >= v[j - 1] and v[j] > v[j + 1] and v[j] >= 0.25]
    out[11] = len(tops)
    others = sorted((v[j] for j in tops if abs(j - k) > 1), reverse=True)
    out[12] = float(others[0]) if others else 0.0
    vc = v - mu
    out[13] = int(np.sum(np.signbit(vc[1:]) != np.signbit(vc[:-1])))
    d1, d2 = np.diff(v), np.diff(v, 2)
    e1 = float(np.sum(d1 ** 2))
    out[14] = float(np.sum(d2 ** 2)) / e1 if e1 > 0 else np.nan
    spec = np.abs(np.fft.rfft(vc * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, step_ms / 1000.0)
    tot = float(spec[1:].sum())
    if tot > 0:
        out[15] = float(spec[f > 60.0].sum()) / tot
        out[16] = float(np.sum(f[1:] * spec[1:]) / tot)
    core = max(1, int(round(10.0 / step_ms)))
    en = float(np.sum(v ** 2))
    if en > 0:
        out[17] = float(np.sum(v[max(0, k - core):k + core + 1] ** 2)) / en
    far = max(1, int(round(25.0 / step_ms)))
    fl = np.concatenate([v[:max(0, k - far)], v[k + far + 1:]])
    out[18] = float(fl.std()) if fl.size >= 3 else np.nan
    edge = max(1, int(round(10.0 / step_ms)))
    out[19] = float(v[-edge:].mean() - v[:edge].mean())
    ab = float(np.sum(np.abs(v)))
    out[20] = float(np.sum(v[v > 0])) / ab if ab > 0 else np.nan
    if c is not None and c.size == n and np.all(np.isfinite(c)) \
            and np.max(np.abs(c)) > 0:
        kc = lo + int(np.argmax(c[lo:hi]))
        out[21] = (kc - k) * step_ms
        if np.std(c) > 0:
            out[22] = float(np.corrcoef(v, c)[0, 1])
        cn = c / (c[kc] if c[kc] > 0 else float(np.max(np.abs(c))))
        out[23] = _fwhm(cn, kc, step_ms)
    if prof is not None and prof.size and np.all(np.isfinite(prof)):
        pp = prof[np.abs(prof) > 0.1 * float(np.max(np.abs(prof)) or 1.0)]
        out[24] = int(np.sum(np.signbit(pp[1:]) != np.signbit(pp[:-1]))) \
            if pp.size > 1 else 0
    return out


def derive(waves, ok, n_wave, step_ms, profile_rows):
    """The 25 numbers for every candidate, from AI Beta's "waves" block.

    `waves` is that family's matrix: the trace (`n_wave // 2` samples),
    the CSD time course (the rest of `n_wave`) and the depth profile
    (`profile_rows`). Rows where `ok` is false come back all NaN.
    """
    waves = np.asarray(waves, dtype=np.float64)
    n = waves.shape[0]
    out = np.full((n, len(NAMES)), np.nan, dtype=np.float32)
    half = n_wave // 2
    for i in np.flatnonzero(np.asarray(ok, bool)):
        row = waves[i]
        w = row[:half]
        c = row[half:n_wave]
        prof = row[n_wave:n_wave + profile_rows]
        out[i] = _one(w, c if c.size == half else None, prof, step_ms)
    return out
