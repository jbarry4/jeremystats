"""
cfc_core.py — a faithful, readable Python port of the CFC math in this repo.

Everything here mirrors the MATLAB that actually runs in the pipeline:

    01_core_tort/eegfilt.m       -> eegfilt()      (EEGLAB firls + filtfilt)
    01_core_tort/ModIndex_v2.m   -> mod_index()    (Tort normalized-entropy MI)
    03_vacc_pipeline/step04_newFCSE.m -> comodulogram()

The point is not speed, it is that you can read the formula next to the
picture it produces. Nothing here touches real data — every figure in
./figures is built from synthetic LFP defined in this file.
"""
import numpy as np
from scipy.signal import firls, filtfilt, hilbert

# ----------------------------------------------------------------------------
# 1. The filter  (port of eegfilt.m)
# ----------------------------------------------------------------------------
MINFAC = 3       # this many (lo)cutoff-freq cycles in the filter
MIN_FILTORDER = 15
TRANS = 0.15     # fractional width of the transition zones


def eegfilt_order(srate, locutoff):
    """Filter order eegfilt.m picks for you: 3 * fix(srate / locutoff)."""
    order = MINFAC * int(srate // locutoff)
    return max(order, MIN_FILTORDER)


def eegfilt_response(srate, locutoff, hicutoff):
    """The (f, m) piecewise-linear target handed to firls, in Hz."""
    nyq = srate * 0.5
    f = np.array([0.0, (1 - TRANS) * locutoff, locutoff,
                  hicutoff, (1 + TRANS) * hicutoff, nyq])
    m = np.array([0.0, 0.0, 1.0, 1.0, 0.0, 0.0])
    return f, m


def eegfilt(data, srate, locutoff, hicutoff, filtorder=None):
    """Zero-phase FIR bandpass, exactly as eegfilt.m does it.

    Least-squares FIR (firls) designed against a trapezoidal target with
    15% transition ramps, then run forwards and backwards (filtfilt) so the
    filter contributes no phase shift of its own.  Zero phase is not a
    nicety here: the whole measure is about phase.
    """
    nyq = srate * 0.5
    if filtorder is None:
        filtorder = eegfilt_order(srate, locutoff)
    # scipy's firls wants an odd number of taps (an even order)
    if filtorder % 2:
        filtorder += 1
    f, m = eegfilt_response(srate, locutoff, hicutoff)
    bands = [f[0], f[1], f[2], f[3], f[4], f[5]]
    b = firls(filtorder + 1, bands, m, fs=srate)
    return filtfilt(b, [1.0], data), b


# ----------------------------------------------------------------------------
# 2. The measure  (port of ModIndex_v2.m)
# ----------------------------------------------------------------------------
NBIN = 18                      # 0-360 deg in 18 bins -> 20 deg each
WINSIZE = 2 * np.pi / NBIN
POSITION = -np.pi + np.arange(NBIN) * WINSIZE   # LEFT edge of each bin


def mean_amp(phase, amp, position=POSITION):
    """<A>(phi_j): mean amplitude in each phase bin. Non-normalised."""
    winsize = 2 * np.pi / len(position)
    out = np.empty(len(position))
    for j, left in enumerate(position):
        sel = (phase >= left) & (phase < left + winsize)
        out[j] = amp[sel].mean() if sel.any() else np.nan
    return out


def mod_index(phase, amp, position=POSITION):
    """Tort modulation index.

        P_j  = <A>_j / sum_k <A>_k          (amplitude turned into a pmf)
        H(P) = -sum_j P_j log P_j           (Shannon entropy, nats)
        MI   = (log N - H(P)) / log N       (= KL(P || U) / log N)

    MI = 0 when the amplitude distribution over phase is flat.
    MI = 1 only if all amplitude fell in a single 20-degree bin.
    """
    ma = mean_amp(phase, amp, position)
    p = ma / ma.sum()
    h = -np.sum(p * np.log(p))
    n = len(position)
    return (np.log(n) - h) / np.log(n), ma


def kl_from_mi(mi, nbin=NBIN):
    """MI is just KL divergence from uniform, rescaled. Return the KL in nats."""
    return mi * np.log(nbin)


# ----------------------------------------------------------------------------
# 3. The grid  (port of step04_newFCSE.m / the PTEN driver)
# ----------------------------------------------------------------------------
PHASE_VEC_LAB = np.arange(1, 26.0001, 0.5)     # 1:0.5:26   -> 51 columns
PHASE_BW_LAB = 0.5
AMP_VEC_LAB = np.arange(20, 200.0001, 5)       # 20:5:200   -> 37 rows
AMP_VEC_PTEN = np.arange(20, 300.0001, 5)      # PTEN driver opened this to 300
AMP_BW_LAB = 10.0


def filter_banks(lfp, srate, phase_vec, phase_bw, amp_vec, amp_bw):
    """The two 'Transformed' matrices from newFCSE.m.

    PhaseFreqTransformed[j, t] = angle(hilbert(bandpass(lfp, fp_j, fp_j+bw)))
    AmpFreqTransformed[i, t]   =   abs(hilbert(bandpass(lfp, fa_i, fa_i+bw)))
    """
    n = len(lfp)
    ph = np.empty((len(phase_vec), n))
    am = np.empty((len(amp_vec), n))
    for j, f1 in enumerate(phase_vec):
        y, _ = eegfilt(lfp, srate, f1, f1 + phase_bw)
        ph[j] = np.angle(hilbert(y))
    for i, f1 in enumerate(amp_vec):
        y, _ = eegfilt(lfp, srate, f1, f1 + amp_bw)
        am[i] = np.abs(hilbert(y))
    return ph, am


def comodulogram(ph, am):
    """MI for every (phase band, amplitude band) cell. Shape: phase x amp."""
    out = np.empty((ph.shape[0], am.shape[0]), dtype=np.float32)
    for j in range(ph.shape[0]):
        for i in range(am.shape[0]):
            out[j, i] = mod_index(ph[j], am[i])[0]
    return out


def bin_centers(vec, bw):
    """What the MATLAB actually plots: vec + BandWidth/2."""
    return np.asarray(vec) + bw / 2.0


# ----------------------------------------------------------------------------
# 4. Synthetic LFP
# ----------------------------------------------------------------------------
def tort_lfp(dur=150.0, srate=1000.0, fp=8.0, fa=80.0,
             nonmod=2.0, noise=1.0, seed=0):
    """The generator from CallerRoutine.m, parameterised.

    lfp = (0.2*(sin(2 pi fp t) + 1) + nonmod*0.1) * sin(2 pi fa t)
          + sin(2 pi fp t) + noise * randn

    `nonmod` is the un-modulated share of the fast oscillation: larger
    means weaker coupling, so MI falls. This is Tort's own knob.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur * srate)) / srate
    slow = np.sin(2 * np.pi * fp * t)
    envelope = 0.2 * (slow + 1) + nonmod * 0.1
    lfp = envelope * np.sin(2 * np.pi * fa * t) + slow
    lfp = lfp + noise * rng.standard_normal(lfp.size)
    return t, lfp


def pink_noise(n, srate, seed=0, exponent=1.0):
    """1/f^exponent noise — closer to real LFP background than white noise."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / srate)
    f[0] = f[1]
    X = X / f ** (exponent / 2.0)
    y = np.fft.irfft(X, n)
    return y / y.std()


def ied_lfp(dur=150.0, srate=1000.0, rate=1.5, seed=1, amp=6.0, width=0.010):
    """Pink-noise LFP peppered with sharp interictal-like transients and NO
    true phase-amplitude coupling anywhere. Used to show what a spike train
    alone does to a comodulogram."""
    rng = np.random.default_rng(seed)
    n = int(dur * srate)
    t = np.arange(n) / srate
    lfp = pink_noise(n, srate, seed=seed)
    n_ev = int(dur * rate)
    times = np.sort(rng.uniform(1.0, dur - 1.0, n_ev))
    k = np.arange(-int(4 * width * srate), int(4 * width * srate) + 1) / srate
    # sharp biphasic spike-and-wave-ish transient
    spike = np.exp(-0.5 * (k / (width / 2.5)) ** 2) - 0.45 * np.exp(-0.5 * ((k - 2.2 * width) / (width * 1.6)) ** 2)
    spike = spike / np.abs(spike).max()
    for tt in times:
        i0 = int(tt * srate) - len(k) // 2
        lfp[i0:i0 + len(k)] += amp * spike
    return t, lfp, times


# ----------------------------------------------------------------------------
# 5. Surrogates
# ----------------------------------------------------------------------------
def surrogate_mi(phase, amp, n_surr=200, srate=1000.0, min_shift=1.0, seed=0):
    """Null MI from block-shifting the amplitude series against the phase
    series. Destroys the timing relationship, keeps both signals' own
    statistics (spectrum, envelope shape, spike content) intact."""
    rng = np.random.default_rng(seed)
    n = len(amp)
    lo = int(min_shift * srate)
    out = np.empty(n_surr)
    for k in range(n_surr):
        s = rng.integers(lo, n - lo)
        out[k] = mod_index(phase, np.roll(amp, s))[0]
    return out


def pac_lfp(dur=120.0, srate=1000.0, fp=8.0, fa=80.0, depth=1.0,
            slow_amp=1.0, fast_amp=0.25, noise=0.6, seed=0, pink=True):
    """Explicit amplitude-modulation generator with a controllable depth.

        lfp = fast_amp * (1 + depth*sin(2 pi fp t - pi/2)) * sin(2 pi fa t)
              + slow_amp * sin(2 pi fp t)
              + noise * background

    depth = 0 -> no coupling at all; depth = 1 -> fast oscillation switches
    fully off at the trough of the slow one. Unlike the CallerRoutine
    generator this keeps modulation depth constant when you move fa, which is
    what you need to compare detectability across the amplitude axis.
    """
    rng = np.random.default_rng(seed)
    n = int(dur * srate)
    t = np.arange(n) / srate
    slow = np.sin(2 * np.pi * fp * t)
    mod = 1.0 + depth * np.sin(2 * np.pi * fp * t - np.pi / 2)
    fast = fast_amp * mod * np.sin(2 * np.pi * fa * t)
    bg = pink_noise(n, srate, seed=seed + 99) if pink else rng.standard_normal(n)
    return t, fast + slow_amp * slow + noise * bg


# ----------------------------------------------------------------------------
# 6. Fast path (same numbers, vectorised) + a small on-disk cache
# ----------------------------------------------------------------------------
def mean_amp_fast(phase, amp, nbin=NBIN):
    """Identical to mean_amp(), but with one pass of bincount instead of
    `nbin` boolean masks. Verified against mean_amp() in verify.py."""
    idx = np.floor((phase + np.pi) / (2 * np.pi / nbin)).astype(np.int64)
    np.clip(idx, 0, nbin - 1, out=idx)
    counts = np.bincount(idx, minlength=nbin)
    sums = np.bincount(idx, weights=amp, minlength=nbin)
    return sums / counts


def mi_fast(phase, amp, nbin=NBIN):
    ma = mean_amp_fast(phase, amp, nbin)
    p = ma / ma.sum()
    return (np.log(nbin) - (-(p * np.log(p)).sum())) / np.log(nbin)


def comodulogram_fast(ph, am, nbin=NBIN):
    """MI for every (phase band, amplitude band) cell. Shape: phase x amp.
    Bins the phase series once per row instead of once per cell."""
    npz, nam = ph.shape[0], am.shape[0]
    out = np.empty((npz, nam), dtype=np.float32)
    for j in range(npz):
        idx = np.floor((ph[j] + np.pi) / (2 * np.pi / nbin)).astype(np.int64)
        np.clip(idx, 0, nbin - 1, out=idx)
        counts = np.bincount(idx, minlength=nbin)
        for i in range(nam):
            ma = np.bincount(idx, weights=am[i], minlength=nbin) / counts
            p = ma / ma.sum()
            out[j, i] = (np.log(nbin) + (p * np.log(p)).sum()) / np.log(nbin)
    return out


import os, pathlib
CACHE = pathlib.Path(__file__).parent / "_cache"


def cached(name, fn):
    """Memoise an expensive array-returning step to ./_cache/<name>.npz."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / (name + ".npz")
    if f.exists():
        d = np.load(f)
        return tuple(d[k] for k in sorted(d.files))
    out = fn()
    np.savez_compressed(f, **{f"a{i}": v for i, v in enumerate(out)})
    return out


def pac_lfp_natural(dur=120.0, srate=1000.0, fp=8.0, fa=80.0, fp_bw=4.0,
                    depth=0.6, slow_amp=1.0, fast_amp=0.45, noise=0.6, seed=0):
    """Coupling driven by a *noisy* slow rhythm rather than a perfect sine.

    The slow oscillation is bandpass-filtered pink noise, so its frequency
    and phase wander the way real theta does. This matters for surrogate
    testing: circularly shifting the amplitude series against a perfectly
    periodic sine changes only the preferred phase, not the coupling
    strength, so the surrogate null collapses onto the observed value and
    the test is vacuous. Against a wandering rhythm the shift genuinely
    destroys the timing relationship.
    """
    from scipy.signal import hilbert as _h
    n = int(dur * srate)
    t = np.arange(n) / srate
    slow, _ = eegfilt(pink_noise(n, srate, seed=seed + 5), srate,
                      fp - fp_bw / 2, fp + fp_bw / 2)
    slow = slow / slow.std()
    ph = np.angle(_h(slow))
    env = 1.0 + depth * np.sin(ph - np.pi / 2)
    fast = fast_amp * env * np.sin(2 * np.pi * fa * t)
    bg = pink_noise(n, srate, seed=seed + 99)
    return t, slow_amp * slow + fast + noise * bg
