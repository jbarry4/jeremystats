"""
ds_pca.py -- Toothy's DS1/DS2 classification, rebuilt on aligned stamps.

WHAT THIS IS
============
Toothy classifies dentate spikes into DS1 and DS2 by running a PCA over the
current source density profile at each event and clustering the result. That
analysis lives inside `ds_classification_gui.py`, wired to a Qt window, an
HDF5 layout and a probeinterface probe object, and it starts from Toothy's
own detections.

This is the same arithmetic with none of that. It reads .ncs directly, takes
stamps from a curated event bank, refines each stamp against the CSD before
measuring anything, and writes a CSV with the same columns Toothy's DS_DF
carries -- so the numbers can be checked against a Toothy run and the pieces
can be moved into our own pipeline one at a time.

THE FIVE STAGES, and where each one comes from
==============================================
1. STAMPS      the curated bank -- our events, not a detector's.
2. REFINE      each stamp moved onto the CSD's own peak. This is the new
               part and it is why the whole thing is worth redoing: every
               feature below is read at ONE SAMPLE, so a stamp that is ten
               milliseconds late is a depth profile of something else.
3. FEATURES    Toothy's CSD at that one sample, per channel, min-max
               normalized. `ds_classification_gui.get_csd` ->
               `ephys.get_csd_obj` -> `icsd.StandardCSD` -> `csd_obj2arrs`.
4. PCA         two components over events. `run_pca`, line 766.
5. CLUSTER     K-means and DBSCAN on those two components, then DS1/DS2
               assigned by which class sinks higher up the shank.
               `run_pca.set_ds_type`.

WHAT IS REPRODUCED EXACTLY, AND WHAT IS NOT
===========================================
Reproduced, because the point is to get the same answer:

  * StandardCSD with Vaknin endpoint electrodes -- the tridiagonal Laplacian
    scaled by -sigma/h, endpoints duplicated before the derivative and the
    two added rows trimmed after, so the output has one row per contact.
    `icsd.py:166-250`.
  * The spatial filter: a 3-point Gaussian window, sigma 1, normalized to
    sum 1, convolved down the depth axis in 'same' mode. `icsd.py:100-163`.
  * Per-event min-max normalization to [0, 1]. `pyfx.Normalize`.
  * The features are taken from the BROADBAND 1 kHz LFP, not from the
    5-100 Hz band. Toothy's `bp_dict['raw']` is the plain downsampled trace
    (`data_processing.py:563`); the DS band is used for DETECTION only. This
    surprises people, so it is said out loud: by default nothing is
    bandpassed before the CSD that the PCA sees.
  * KMeans(n_clusters=2, n_init='auto') and DBSCAN(eps=0.2, min_samples=3),
    both on the two principal components.
  * The DS1/DS2 rule: whichever class has its mean CSD minimum at the
    shallower contact becomes DS1.

Deliberately NOT reproduced, and each is a flag:

  * The mains. Toothy never notches, so `--line 0` (the default here) matches
    it. On this rig 60 Hz is about a quarter of the wideband RMS per contact,
    and a single-sample depth profile carries whatever the mains was doing at
    that instant -- `--line 60` takes it out first. Run both; if the clusters
    move, the mains was in the features.
  * The decimation. Toothy resamples by FFT (`data_processing.py:499`); this
    uses `incisor._decimate`, the two-stage IIR the rest of our pipeline
    uses. Below the detection threshold in this band, but it is a difference.
  * The h exponent. StandardCSD divides by h once, so its units are A/m^2
    rather than the A/m^3 a second derivative gives. That is upstream iCSD
    behaviour, not a typo here, and it cannot change the PCA because the
    features are min-max normalized per event -- but `--h-power 2` is there
    for anyone who wants the dimensions to come out right.

ROW ORDER, WHICH DECIDES WHICH CLASS IS DS1
===========================================
Rows are in CSC order: increasing channel number is increasing depth, CSC1 at
the top of the shank. Toothy sorts its contacts by ascending y instead, which
is the opposite direction, so its comment "higher index == lower sink" reads
backwards here. The rule itself is mechanical either way -- the class whose
mean CSD dips at the smaller row index is called DS1 -- so in THIS row order
DS1 is the shallower sink. The run prints the mean sink contact for each
class; check it against the anatomy and use `--swap-types` if it is inverted.
Nothing downstream depends on which label is which, only that it is stated.

Run:
  python ds_pca.py
  python ds_pca.py --line 60 --save ds_pca_notched.png
  python ds_pca.py --csd-channels 30-53 --clus-algo dbscan
  python ds_pca.py --refine argmax --no-refine-plot
"""

import argparse
import csv as csvmod
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import gridspec
from scipy.signal import convolve, find_peaks
from scipy.signal.windows import gaussian
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import PCA

_HERE = os.path.dirname(os.path.abspath(__file__))
_GUI = os.path.abspath(os.path.join(_HERE, os.pardir, "BARRY GUI"))
sys.path.insert(0, _GUI)
sys.path.insert(0, os.path.join(_GUI, "backend"))
from backend import braces, csc, incisor, probes            # noqa: E402

from dentate_spike_aligner import (                          # noqa: E402
    FOLDER, BANK, LINE_Q, read_bank, parse_channels, notch, mmss)

# Toothy's own defaults, from qparam.get_original_defaults(). Named here so a
# change in Toothy is a diff in one block rather than a hunt.
T_LFP_FS = 1000.0            # 'lfp_fs'
T_DS_FREQ = (5.0, 100.0)     # 'ds_freq'   -- detection/refinement band
T_F_ORDER = 3                # 'f_order'   -- spatial filter length
T_F_SIGMA = 1.0              # 'f_sigma'
T_VAKNIN = True              # 'vaknin_el'
T_COND = 0.3                 # 'cond'      -- S/m
T_NCLUSTERS = 2              # 'nclusters'
T_EPS = 0.2                  # 'eps'
T_MIN_SAMPLES = 3            # 'min_clus_samples'
T_CLUS_ALGO = "kmeans"       # 'clus_algo'

WINDOW_MS = 100.0            # refinement search half-width
SURROUND_MS = 50.0           # twin in calculate_csd, for the mean CSDs
PAD_S = 0.5                  # filter margin, read and trimmed


# --------------------------------------------------------------------------
# Toothy's CSD, without quantities, probeinterface or Qt
# --------------------------------------------------------------------------
def standard_csd(lfp, h_m, sigma=T_COND, vaknin=T_VAKNIN, h_power=1):
    """icsd.StandardCSD.get_csd, for [nCh x nCol] in volts.

    The Vaknin trick is what keeps the output the same height as the input:
    a second difference over n points gives n-2, so the endpoint contacts are
    duplicated first and the two extra rows are dropped afterwards. The top
    and bottom contacts therefore get a CSD computed as though the field were
    flat just past the end of the probe, which is an assumption and not a
    measurement -- it is Toothy's assumption, so it is kept.
    """
    x = np.asarray(lfp, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if vaknin:
        ext = np.empty((x.shape[0] + 2, x.shape[1]), dtype=np.float64)
        ext[0] = x[0]
        ext[1:-1] = x
        ext[-1] = x[-1]
    else:
        ext = x
    n = ext.shape[0]

    f_inv = -np.eye(n)
    for j in range(1, n - 1):
        f_inv[j, j - 1:j + 2] = np.array([1.0, -2.0, 1.0])
    f_inv = f_inv * -sigma / (h_m ** h_power)

    csd = f_inv.dot(ext)
    return csd[1:-1] if vaknin else csd


def filter_csd(csd, f_order=T_F_ORDER, f_sigma=T_F_SIGMA):
    """icsd.CSD.filter_csd, 'convolve' branch, gaussian window.

    Note the 'same' convolution: it zero-pads, so the first and last contacts
    are pulled toward zero by the part of the kernel hanging off the end of
    the probe. Real, reproduced, and a reason not to read anything into the
    two outermost rows.
    """
    num = gaussian(int(f_order), float(f_sigma))
    num = num / num.sum()
    out = np.array(csd, dtype=np.float64, copy=True)
    for i in range(out.shape[1]):
        out[:, i] = convolve(out[:, i], num, "same")
    return out


def normalize_columns(x):
    """pyfx.Normalize down each column -- one event, min-max to [0, 1].

    Per EVENT and not per contact, which is what makes the features a shape
    rather than a size: a big dentate spike and a small one with the same
    laminar profile land on top of each other in the PCA. It also makes the
    whole thing invariant to the units of the input, which is why Toothy's
    "assume mV" does not matter here.
    """
    out = np.array(x, dtype=np.float64, copy=True)
    for i in range(out.shape[1]):
        col = out[:, i]
        lo, hi = np.nanmin(col), np.nanmax(col)
        out[:, i] = np.zeros(col.size) if hi == lo else (col - lo) / (hi - lo)
    return out


def toothy_csd(lfp_uv, pitch_um, args):
    """(raw, filtered, normalized) CSD for [nCh x nCol] of microvolts.

    Toothy reads its LFP as millivolts and rescales to volts; ours is
    microvolts, so the conversion differs by a thousand. It changes the
    magnitude of `raw` and `filt` and nothing else -- `norm` is invariant,
    and `norm` is the only one the PCA sees.
    """
    volts = np.asarray(lfp_uv, dtype=np.float64) * 1e-6
    h_m = float(pitch_um) * 1e-6
    raw = standard_csd(volts, h_m, sigma=args.cond, vaknin=not args.no_vaknin,
                       h_power=args.h_power)
    filt = filter_csd(raw, args.f_order, args.f_sigma)
    return raw, filt, normalize_columns(filt)


# --------------------------------------------------------------------------
# Reading, refining
# --------------------------------------------------------------------------
def read_window(session, channels, t0, t1, args, report=None):
    """One stretch on every channel: broadband and DS-band, both at lfp_fs.

    Both come out of ONE read. The refinement needs the band-limited CSD and
    the features need the broadband sample at whatever time the refinement
    lands on, and reading the file twice for that would double the slowest
    part of the run.
    """
    wide, band, anchor, fs_out = [], [], None, None
    raw_rms, line_rms = [], []
    for ch in channels:
        raw, got_t0, ch_fs = csc._read_channel_window(session, ch, t0, t1)
        if raw.size < 8:
            return None
        q = incisor.decimation_for(ch_fs, args.lfp_fs)
        dec = incisor._decimate(raw, q) if q > 1 else np.asarray(raw, float)
        if dec.size < 16:
            return None
        if anchor is None:
            anchor, fs_out = got_t0, ch_fs / q
        # Measured whether or not it is applied. Toothy never notches, so the
        # default leaves the mains in -- but "how much mains is in the
        # features" is the number that decides whether that matters, and it
        # is not knowable from a run that silently kept it.
        clean = notch(dec, fs_out, args.line or 60.0)
        raw_rms.append(float(np.std(dec)))
        line_rms.append(float(np.std(dec - clean)))
        # THE REFINEMENT IS ALWAYS NOTCHED, whatever the features do.
        #
        # 60 Hz sits INSIDE the 5-100 Hz band the refinement measures in, and
        # it survives a CSD -- it is common-mode, but a second difference of
        # a common-mode line is not zero on a real probe. What the alignment
        # produces is a TIME, and a mains ripple in the trace it picks peaks
        # off is a systematic error in that time. Measured on this recording:
        # notching first tightens the refinement's IQR from 3.6 ms to 1.8 ms.
        # Toothy's "no notch" is a statement about its FEATURES, and it is
        # honoured below; it is not a reason to time events badly.
        band.append(incisor._filtered(clean, fs_out, args.band))
        wide.append(clean if args.line else dec)
    keep = min(min(w.size for w in wide), min(b.size for b in band))
    if report is not None:
        report["wideband_uv"] = float(np.median(raw_rms))
        report["mains_uv"] = float(np.median(line_rms))
    return (np.vstack([w[:keep] for w in wide]),
            np.vstack([b[:keep] for b in band]), anchor, fs_out)


def pick_peak(trace, t_ms, mode="nearest", frac=0.25):
    """Which maximum of mean|CSD| the stamp should move to.

    "argmax" is the whole window's largest, which is what the aligner figures
    drew. It is winner-take-all: a stamp whose own event is real but whose
    neighbour 60 ms away is bigger gets moved onto the neighbour, and the
    event that was curated is abandoned.

    "nearest" -- the default -- takes the local maximum CLOSEST TO THE STAMP
    among those with real prominence. That is what a refinement means: the
    curated time is an assertion about which event, and the measurement only
    gets to correct WHEN. It is also what Braces does, for the same reason.

    The prominence floor is a quarter of the window's range, which keeps the
    pick off the ripples in the baseline without needing a noise model.
    """
    if mode == "argmax":
        return int(np.argmax(trace))
    span = float(np.nanmax(trace) - np.nanmin(trace))
    pk, _ = find_peaks(trace, prominence=max(span * frac, 1e-12))
    if pk.size == 0:
        return int(np.argmax(trace))
    return int(pk[int(np.argmin(np.abs(t_ms[pk])))])


def refine_and_read(session, channels, stamps, args, bad):
    """Stage 2 and stage 3's raw material, in one pass over the recording.

    Returns (rows, csd_lfp, surrounds, fs) where `csd_lfp` is [nCh x nEvents]
    -- the broadband sample at each REFINED time, which is exactly the matrix
    Toothy builds as `lfp_interp[channels][:, idx]`.
    """
    half = args.window_ms / 1000.0
    sur = args.surround_ms / 1000.0
    rows, cols, surrounds, report = [], [], [], {}
    fs_out = None
    step = max(1, len(stamps) // 10)

    for k, e in enumerate(stamps):
        if len(stamps) > 12 and k and not k % step:
            print("  read %d/%d" % (k, len(stamps)))
        t = e["t"]
        got = read_window(session, channels, t - half - sur - args.pad,
                          t + half + sur + args.pad, args, report)
        if not got:
            print("  #%d at %.3f s: nothing readable there (a gap?)"
                  % (k + 1, t))
            continue
        wide, band, anchor, fs = got
        fs_out = fs
        wide = braces.repair(wide, channels, bad)
        band = braces.repair(band, channels, bad)

        # --- the refinement, on the band-limited CSD ---------------------
        # BARRY's derivative here, not Toothy's: this is our alignment
        # measurement and it is the one the aligner figures were drawn from.
        # Toothy's CSD comes in below, for the features.
        cs = braces.csd_of(band, {"spacing_um": args.spacing,
                                  "csd_smooth": True})
        tt = anchor + np.arange(cs.shape[1]) / fs - t
        inside = np.abs(tt) <= half + 0.5 / fs
        if inside.sum() < 8:
            continue
        trace = np.abs(cs[:, inside]).mean(axis=0)
        t_ms = tt[inside] * 1000.0
        j = pick_peak(trace, t_ms, args.refine)
        off_ms = float(t_ms[j])
        t_ref = t + off_ms / 1000.0

        # --- the feature sample and its surround -------------------------
        i_ref = int(round((t_ref - anchor) * fs))
        n_sur = int(round(sur * fs))
        if i_ref - n_sur < 0 or i_ref + n_sur + 1 > wide.shape[1]:
            print("  #%d: refined stamp too close to the window edge" % (k + 1))
            continue
        cols.append(wide[:, i_ref].copy())
        surrounds.append(wide[:, i_ref - n_sur:i_ref + n_sur + 1].copy())
        rows.append({
            "n": k + 1, "stamp_s": t, "refined_s": t_ref, "offset_ms": off_ms,
            "idx": int(round(t_ref * args.lfp_fs)),
            "peak_uv_mm2": float(trace[j]), "by": e.get("by", ""),
        })

    if not rows:
        sys.exit("no events could be read")
    print("\nmains: %.2f uV rms of a %.1f uV rms trace (%.1f%%) per contact "
          "-- %s"
          % (report.get("mains_uv", 0.0), report.get("wideband_uv", 0.0),
             100.0 * report.get("mains_uv", 0.0)
             / max(report.get("wideband_uv", 0.0), 1e-9),
             "notched out before the CSD" if args.line
             else "measured but LEFT IN, which is what Toothy does "
                  "(--line 60 removes it)"))
    return rows, np.array(cols).T, np.array(surrounds), fs_out


# --------------------------------------------------------------------------
# Stage 4 and 5
# --------------------------------------------------------------------------
def classify(norm_filt_csd, filt_csd, args):
    """PCA, K-means, DBSCAN and the DS1/DS2 call. `run_pca`, line 766."""
    pca = PCA(n_components=2)
    fit = pca.fit_transform(norm_filt_csd.T)     # events are the samples

    def set_ds_type(types):
        """Toothy's rule: the shallower sink is DS1 (see the row-order note)."""
        r1 = np.where(types == 1)[0]
        r2 = np.where(types == 2)[0]
        if r1.size == 0 or r2.size == 0:
            return types
        i1 = int(np.argmin(np.nanmean(filt_csd[:, r1], axis=1)))
        i2 = int(np.argmin(np.nanmean(filt_csd[:, r2], axis=1)))
        if i1 > i2:
            types = np.array(types)
            types[r1], types[r2] = 2, 1
        return types

    km = KMeans(n_clusters=int(args.nclusters), n_init="auto").fit(fit)
    db = DBSCAN(eps=args.eps, min_samples=int(args.min_samples)).fit(fit)
    k_types = set_ds_type(np.array([{0: 2, 1: 1}.get(x, 0) for x in km.labels_]))
    d_types = set_ds_type(np.array([{0: 1, 1: 2}.get(x, 0) for x in db.labels_]))
    types = k_types if args.clus_algo == "kmeans" else d_types
    if args.swap_types:
        flip = {1: 2, 2: 1}
        k_types = np.array([flip.get(x, x) for x in k_types])
        d_types = np.array([flip.get(x, x) for x in d_types])
        types = np.array([flip.get(x, x) for x in types])
    return fit, pca, k_types, d_types, types


def csd_screen(surrounds, channels, args, ratio=4.0, known=()):
    """Contacts a CSD cannot be run over, judged on the CSD and not the LFP.

    THIS EXISTS BECAUSE THE FIRST VERSION OF THIS SCRIPT CLASSIFIED ONE BAD
    WIRE. An amplitude screen (`braces.screen`) asks whether a contact is
    dead or railing, and on this probe it passes CSC47-53 -- their RMS is
    within half a decibel of the median. But a second spatial difference does
    not care about a contact's amplitude, it cares about how far that contact
    sits from the line through its neighbours, and by that measure those
    contacts are three to four times worse than the rest of the shank.

    What that did: every feature vector is min-max normalized per event, so
    one contact with a large offset becomes the minimum or the maximum of
    EVERY column. PC1 then separates events by the sign of that one contact,
    K-means cuts the result in half, and two beautifully separated clusters
    come out that have nothing to do with dentate spikes -- the class-mean
    CSD is a stripe that is just as strong 50 ms away from the event as at
    it. A clean-looking answer to the wrong question.

    The screen is on the BASELINE CSD: how big each contact's CSD is at the
    edges of the event window, where by construction there is no spike.

    A plain multiple of the probe's median, not a MAD count, because on this
    recording the two do not agree and the multiple is the one that reads
    true. Measured here, the probe's baseline CSD runs from 0.2x the median
    to 2.6x on sixty of the sixty-four contacts, and then 5.8x, 6.4x, 6.9x,
    8.5x and 11.4x on CSC48, 49, 53, 50 and 51. That is a gap, not a tail. A
    MAD count computed over a sample that includes five such contacts has its
    own scale inflated by them and flagged exactly one; the ratio flags the
    block, which is what a person looking at the numbers would do.

    `known` contacts are left out of the median so that a bad block cannot
    raise the bar that would have caught it.
    """
    filt = toothy_csd(surrounds.mean(axis=0), args.spacing, args)[1]
    t = np.linspace(-args.surround_ms, args.surround_ms, filt.shape[1])
    edge = np.abs(t) > args.surround_ms * 0.7
    base = np.abs(filt[:, edge]).mean(axis=1)
    skip = {int(n) for n in known}
    live = np.array([b for b, c in zip(base, channels)
                     if b > 0 and int(c["number"]) not in skip])
    if live.size < 4:
        return {}, base
    med = float(np.median(live))
    out = {}
    for i, c in enumerate(channels):
        if base[i] <= 0 or int(c["number"]) in skip:
            continue
        if base[i] > ratio * med:
            out[int(c["number"])] = (
                "baseline CSD %.3g, %.1fx the probe median -- a second "
                "difference amplifies it" % (base[i], base[i] / med))
    return out, base


def depth_band(surrounds, args, channels=None, bad=None):
    """Which contacts the CSD runs over, when nobody has drawn the box.

    Toothy has a person select this window on screen, and the choice is not
    cosmetic: the features ARE these contacts, so a window centred on the
    wrong depth is a PCA of the wrong thing.

    Scored on the EVENT-TRIGGERED TEMPLATE against its own baseline, and that
    is the whole point. The first version of this scored contacts by mean
    |CSD| over the window, which is a question about magnitude -- and on this
    probe the largest magnitude is CSC47-51, a run of noisy contacts whose
    CSD is just as large 40 ms away from the event as at it. It chose
    CSC30-53, put the "sink" on a bad wire, and the clustering that came out
    of it was about ongoing noise. Averaging over events kills whatever is
    not time-locked; subtracting the window's own edges kills whatever is
    large but constant. What is left is how much each contact MOVES when the
    dentate spike happens, which is the thing worth building features from.
    """
    mean_lfp = surrounds.mean(axis=0)
    filt = toothy_csd(mean_lfp, args.spacing, args)[1]
    t = np.linspace(-args.surround_ms, args.surround_ms, filt.shape[1])
    i0 = int(np.argmin(np.abs(t)))
    edge = np.abs(t) > args.surround_ms * 0.7
    score = np.abs(filt[:, i0]) - np.abs(filt[:, edge]).mean(axis=1)
    score = np.clip(score, 0.0, None)
    # A repaired contact is the average of its neighbours, so it scores like
    # them and carries nothing of its own. Left in, a run of them pulls the
    # window onto the part of the shank with the least real information in
    # it; scored at zero, the window has to earn its place on live contacts.
    if channels is not None and bad:
        for i, c in enumerate(channels):
            if int(c["number"]) in bad:
                score[i] = 0.0
    span = max(3, min(int(args.csd_span), filt.shape[0]))
    tot = np.convolve(score, np.ones(span), "valid")
    start = int(np.argmax(tot))
    return list(range(start, start + span))


def sink_channel(filt_csd, nums, rows):
    """Which contact the mean CSD of these events dips at."""
    if len(rows) == 0:
        return None
    return int(nums[int(np.argmin(np.nanmean(filt_csd[:, rows], axis=1)))])


# --------------------------------------------------------------------------
# The figure
# --------------------------------------------------------------------------
C1, C2, C0 = "#1a7f37", "#7b3fa0", "#9aa5a1"     # DS1, DS2, unclassified


def figure(rows, fit, pca, types, norm_filt, filt_csd, surrounds, nums, args):
    """Toothy's fig27 and fig3, on one sheet."""
    fig = plt.figure(figsize=(14.5, 8.6))
    gs = gridspec.GridSpec(2, 3, figure=fig, height_ratios=[1.0, 1.0],
                           hspace=0.34, wspace=0.28,
                           left=0.06, right=0.97, top=0.88, bottom=0.08)
    r1 = np.where(types == 1)[0]
    r2 = np.where(types == 2)[0]
    r0 = np.where(types == 0)[0]

    # --- the scatter --------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    for rr, col, lab in ((r0, C0, "unclassified"), (r1, C1, "DS1"),
                         (r2, C2, "DS2")):
        if rr.size:
            ax.scatter(fit[rr, 0], fit[rr, 1], s=34, c=col, lw=.6,
                       edgecolors="white", label="%s  n=%d" % (lab, rr.size))
    ax.set_xlabel("PC1  (%.0f%% of variance)" % (100 * pca.explained_variance_ratio_[0]))
    ax.set_ylabel("PC2  (%.0f%%)" % (100 * pca.explained_variance_ratio_[1]))
    ax.set_title("PCA of the normalized CSD profile", fontsize=11)
    ax.legend(fontsize=9, frameon=False)
    ax.grid(alpha=.15, lw=.6)

    # --- the feature matrix, sorted by class --------------------------
    ax = fig.add_subplot(gs[0, 1])
    order = np.concatenate([r1, r2, r0]).astype(int)
    im = ax.imshow(norm_filt[:, order], aspect="auto", origin="upper",
                   cmap="jet", vmin=0, vmax=1,
                   extent=[0, order.size, nums[-1] + .5, nums[0] - .5])
    if r1.size and r2.size:
        ax.axvline(r1.size, color="white", lw=1.6)
    ax.set_xlabel("event, sorted DS1 then DS2")
    ax.set_ylabel("CSC number")
    ax.set_title("normalized filtered CSD — the features", fontsize=11)
    fig.colorbar(im, ax=ax, fraction=.045, pad=.02)

    # --- the offsets the refinement applied ---------------------------
    ax = fig.add_subplot(gs[0, 2])
    offs = np.array([r["offset_ms"] for r in rows])
    ax.hist(offs, bins=np.arange(-args.window_ms, args.window_ms + 5, 5),
            color="#5c6b66", edgecolor="white", lw=.5)
    ax.axvline(0, color="#111111", ls="--", lw=1.2)
    ax.set_xlabel("ms the stamp moved")
    ax.set_ylabel("events")
    ax.set_title("refinement (%s): median %+.1f ms, IQR %.1f ms"
                 % (args.refine, np.median(offs),
                    np.percentile(offs, 75) - np.percentile(offs, 25)),
                 fontsize=11)
    ax.grid(alpha=.15, lw=.6, axis="y")

    # --- mean CSD by class --------------------------------------------
    tw = np.linspace(-args.surround_ms, args.surround_ms, surrounds.shape[2])
    mats = []
    for rr in (r1, r2):
        if rr.size == 0:
            mats.append(None)
            continue
        mats.append(toothy_csd(surrounds[rr].mean(axis=0), args.spacing, args)[1])
    lim = max([np.abs(m).max() for m in mats if m is not None] or [1.0])
    for k, (rr, m, lab, col) in enumerate(((r1, mats[0], "DS1", C1),
                                           (r2, mats[1], "DS2", C2))):
        ax = fig.add_subplot(gs[1, k])
        if m is None:
            ax.text(.5, .5, "no %s events" % lab, ha="center", va="center",
                    transform=ax.transAxes, color=C0)
            ax.set_xticks([]); ax.set_yticks([])
            continue
        ax.imshow(m, aspect="auto", origin="upper", cmap="jet",
                  vmin=-lim, vmax=lim,
                  extent=[tw[0], tw[-1], nums[-1] + .5, nums[0] - .5])
        ax.axvline(0, color="white", ls="--", lw=1.1)
        ax.set_xlabel("ms from the refined stamp")
        if k == 0:
            ax.set_ylabel("CSC number")
        ax.set_title("mean CSD, %s  (n=%d, sink CSC%s)"
                     % (lab, rr.size, sink_channel(filt_csd, nums, rr)),
                     fontsize=11, color=col)

    # --- the mean waveform at each class's own sink -------------------
    ax = fig.add_subplot(gs[1, 2])
    for rr, lab, col in ((r1, "DS1", C1), (r2, "DS2", C2)):
        if rr.size == 0:
            continue
        ch = sink_channel(filt_csd, nums, rr)
        i = list(nums).index(ch)
        w = surrounds[rr][:, i, :]
        mu, sd = w.mean(axis=0), w.std(axis=0) / np.sqrt(max(rr.size, 1))
        ax.fill_between(tw, mu - sd, mu + sd, color=col, alpha=.18, lw=0)
        ax.plot(tw, mu, color=col, lw=1.8, label="%s at CSC%d" % (lab, ch))
    ax.axvline(0, color="#111111", ls="--", lw=1.1)
    ax.set_xlabel("ms from the refined stamp")
    ax.set_ylabel("LFP (µV)")
    ax.set_title("mean broadband waveform at each class's sink", fontsize=11)
    ax.legend(fontsize=9, frameon=False)
    ax.grid(alpha=.15, lw=.6)

    fig.suptitle("Dentate spike PCA — Toothy's method on refined stamps   ·   "
                 "%s   ·   CSC%d–%d   ·   %s clustering%s"
                 % (args.session_label, nums[0], nums[-1], args.clus_algo,
                    "   ·   %g Hz notched" % args.line if args.line
                    else "   ·   no notch (Toothy default)"),
                 fontsize=12.5, y=.965)
    return fig


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default=FOLDER)
    ap.add_argument("--bank", default=BANK)
    ap.add_argument("--label", default="spike",
                    help="curation verdict to keep ('' for all)")
    ap.add_argument("-n", "--n-events", type=int, default=0,
                    help="how many events; 0 (the default) means all of them")

    ap.add_argument("--refine", default="nearest",
                    choices=("nearest", "argmax", "none"),
                    help="how a stamp is moved onto the CSD peak")
    ap.add_argument("--band", type=float, nargs=2, default=list(T_DS_FREQ),
                    metavar=("LO", "HI"),
                    help="band the REFINEMENT measures in (not the features)")
    ap.add_argument("--window-ms", type=float, default=WINDOW_MS,
                    help="how far a stamp is allowed to move")
    ap.add_argument("--surround-ms", type=float, default=SURROUND_MS,
                    help="half-width of the mean-CSD windows (Toothy: 50)")

    ap.add_argument("--csd-channels", default="",
                    help="contacts the CSD runs over, e.g. 30-53 "
                         "(default: picked from the event-triggered CSD)")
    ap.add_argument("--csd-span", type=int, default=braces.DEPTH_BAND,
                    help="how many contacts to pick automatically; the "
                         "default is the same 16 Braces uses, which is about "
                         "the laminar extent of a dentate spike")
    ap.add_argument("--channels", default="",
                    help="contacts READ, before the automatic pick narrows it")
    ap.add_argument("--bad", default="auto",
                    help="contacts to interpolate over; 'auto' screens")
    ap.add_argument("--csd-bad-x", type=float, default=4.0,
                    help="how many times the probe's median baseline CSD a "
                         "contact may reach before it is interpolated over")
    ap.add_argument("--no-csd-screen", action="store_true",
                    help="skip that second screen -- Toothy has no equivalent, "
                         "so this is what a faithful run does")
    ap.add_argument("--spacing", type=float, default=probes.CONTACT_PITCH_UM)
    ap.add_argument("--lfp-fs", type=float, default=T_LFP_FS)
    ap.add_argument("--line", type=float, default=0.0,
                    help="mains to notch before the CSD; 0 = Toothy's "
                         "behaviour, 60 = take it out")
    ap.add_argument("--pad", type=float, default=PAD_S)
    ap.add_argument("--no-invert", action="store_true",
                    help="read the .ncs without flipping the sign, which is "
                         "what Toothy's reader does (load_ncs_file has no "
                         "negation). Flips the sign of every CSD, so sink and "
                         "source swap, and DS1/DS2 swap with them")

    ap.add_argument("--cond", type=float, default=T_COND, help="sigma, S/m")
    ap.add_argument("--f-order", type=int, default=T_F_ORDER)
    ap.add_argument("--f-sigma", type=float, default=T_F_SIGMA)
    ap.add_argument("--no-vaknin", action="store_true")
    ap.add_argument("--h-power", type=int, default=1, choices=(1, 2),
                    help="1 reproduces iCSD; 2 makes the units A/m^3")

    ap.add_argument("--clus-algo", default=T_CLUS_ALGO,
                    choices=("kmeans", "dbscan"))
    ap.add_argument("--nclusters", type=int, default=T_NCLUSTERS)
    ap.add_argument("--eps", type=float, default=T_EPS)
    ap.add_argument("--min-samples", type=int, default=T_MIN_SAMPLES)
    ap.add_argument("--swap-types", action="store_true",
                    help="flip DS1 and DS2 if the sink depths say so")
    ap.add_argument("--seed", type=int, default=0,
                    help="K-means is randomly initialized; this pins it")

    ap.add_argument("--save", default=None, help="write the figure here")
    ap.add_argument("--csv", default=None, help="write the table here")
    args = ap.parse_args()
    args.band = (float(args.band[0]), float(args.band[1]))
    np.random.seed(args.seed)

    # --- stamps -----------------------------------------------------------
    bank = args.bank if os.path.isabs(args.bank) else \
        os.path.join(_HERE, args.bank)
    if not os.path.exists(bank):
        sys.exit("no such bank: " + bank)
    kept = read_bank(bank, label=args.label)
    if not kept:
        sys.exit("no %s events in %s" % (args.label or "any", bank))
    events = kept if args.n_events == 0 else kept[:max(1, args.n_events)]
    args.session_label = events[0]["session"] or os.path.basename(args.folder)
    print("%s: %d %s event(s)"
          % (os.path.basename(bank), len(events), args.label or "ds"))

    # --- the recording ----------------------------------------------------
    session = csc.open_session(args.folder, invert=not args.no_invert)
    if not session.get("ok"):
        sys.exit(session.get("error") or "could not open " + args.folder)
    read_chans = parse_channels(args.channels, session["channels"])
    print("polarity: %s"
          % ("as recorded, not inverted -- Toothy's convention"
             if args.no_invert
             else "inverted, our convention (--no-invert matches Toothy)"))
    print("%s  fs=%g Hz  reading CSC%d-%d at %g Hz"
          % (session["name"], session["fs"], read_chans[0]["number"],
             read_chans[-1]["number"], args.lfp_fs))

    spec = {"band": args.band, "line_hz": args.line or 60.0, "line_q": LINE_Q,
            "lfp_fs": args.lfp_fs}
    if args.bad.strip().lower() in ("", "auto"):
        bad = braces.screen(session, read_chans, spec, [e["t"] for e in events])
    else:
        bad = {int(n): "named on the command line"
               for n in args.bad.replace(" ", "").split(",") if n}
    for num in sorted(bad):
        print("  interpolated over CSC%-3d %s" % (num, bad[num]))

    # --- stages 2 and 3 ---------------------------------------------------
    if args.refine == "none":
        args.refine = "argmax"
        print("note: --refine none is not offered; the stamps are curated to "
              "the nearest sample already, so 'nearest' is the no-op.")
    rows, csd_lfp, surrounds, fs = refine_and_read(
        session, read_chans, events, args, bad)
    nums_all = [int(c["number"]) for c in read_chans]

    # The second screen, on the CSD rather than the amplitude. Done here
    # rather than during the read because it needs the event-triggered
    # average, which does not exist until every event has been read -- and
    # repairing afterwards costs nothing, since the rows are already in hand.
    if not args.no_csd_screen:
        # Iterated, because interpolating a contact rewrites the second
        # difference at its NEIGHBOURS too -- one pass can leave a contact
        # that only looked acceptable next to a worse one.
        found = {}
        for _ in range(5):
            cbad, _base = csd_screen(surrounds, read_chans, args,
                                     args.csd_bad_x, known=bad)
            cbad = {k: v for k, v in cbad.items() if k not in bad}
            if not cbad:
                break
            found.update(cbad)
            bad = {**bad, **cbad}          # int keys, so not dict(a, **b)
            csd_lfp = braces.repair(csd_lfp, read_chans, bad)
            surrounds = np.array([braces.repair(s, read_chans, bad)
                                  for s in surrounds])
        if found:
            print("CSD screen -- interpolated over %d more contact(s):"
                  % len(found))
            for num in sorted(found):
                print("  CSC%-3d %s" % (num, found[num]))
        else:
            print("CSD screen: no contact above %.1fx the probe's median "
                  "baseline CSD" % args.csd_bad_x)

    # Which contacts the CSD runs over. Toothy makes a person draw this box
    # on screen; here it is the contiguous run holding the most of the
    # event-triggered CSD, which is the same judgement made from the data
    # and then printed so it can be disagreed with.
    if args.csd_channels:
        want = [int(c["number"]) for c in
                parse_channels(args.csd_channels, read_chans)]
        sel = [nums_all.index(w) for w in want]
    else:
        sel = depth_band(surrounds, args, read_chans, bad)
    nums = [nums_all[i] for i in sel]
    # Everything downstream is in the selected rows only, surrounds included
    # -- the mean-CSD panels and the feature matrix have to be over the same
    # contacts or their depth axes disagree.
    surrounds = surrounds[:, sel, :]
    print("CSD over %d contacts: CSC%d-%d%s"
          % (len(nums), nums[0], nums[-1],
             "" if args.csd_channels else "  (picked from the data)"))

    raw_csd, filt_csd, norm_filt_csd = toothy_csd(csd_lfp[sel, :],
                                                  args.spacing, args)

    # --- stages 4 and 5 ---------------------------------------------------
    fit, pca, k_types, d_types, types = classify(norm_filt_csd, filt_csd, args)
    for r, p, kt, dt, ty in zip(rows, fit, k_types, d_types, types):
        r.update(pc1=float(p[0]), pc2=float(p[1]), k_type=int(kt),
                 db_type=int(dt), type=int(ty))

    offs = np.array([r["offset_ms"] for r in rows])
    n1 = int((types == 1).sum())
    n2 = int((types == 2).sum())
    n0 = int((types == 0).sum())
    print("\nrefinement (%s): median %+.1f ms, IQR %.1f ms, "
          "%.0f%% moved less than 10 ms"
          % (args.refine, np.median(offs),
             np.percentile(offs, 75) - np.percentile(offs, 25),
             100.0 * (np.abs(offs) <= 10).mean()))
    print("PCA: PC1 %.0f%% of variance, PC2 %.0f%% (%d features, %d events)"
          % (100 * pca.explained_variance_ratio_[0],
             100 * pca.explained_variance_ratio_[1],
             norm_filt_csd.shape[0], norm_filt_csd.shape[1]))
    print("%s: DS1 n=%d (sink CSC%s), DS2 n=%d (sink CSC%s)%s"
          % (args.clus_algo, n1, sink_channel(filt_csd, nums, np.where(types == 1)[0]),
             n2, sink_channel(filt_csd, nums, np.where(types == 2)[0]),
             ", unclassified n=%d" % n0 if n0 else ""))
    agree = float((k_types == d_types).mean()) * 100.0
    print("k-means and DBSCAN agree on %.0f%% of events" % agree)

    # --- the table --------------------------------------------------------
    out_csv = args.csv or ("ds_pca_%s.csv"
                           % ("notched" if args.line else "toothy"))
    out_csv = out_csv if os.path.isabs(out_csv) else \
        os.path.join(_HERE, out_csv)
    cols = ["n", "stamp_s", "refined_s", "offset_ms", "idx", "peak_uv_mm2",
            "pc1", "pc2", "k_type", "db_type", "type", "by"]
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csvmod.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("\nwrote " + out_csv)

    fig = figure(rows, fit, pca, types, norm_filt_csd, filt_csd, surrounds,
                 nums, args)
    if args.save:
        out = args.save if os.path.isabs(args.save) else \
            os.path.join(_HERE, args.save)
        fig.savefig(out, dpi=150)
        print("wrote " + out)
    else:
        plt.show()


if __name__ == "__main__":
    main()
