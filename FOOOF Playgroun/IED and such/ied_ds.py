"""
ied_ds.py -- IEDs and dentate spikes on one timeline, one channel set, one
statistic.

WHY THIS READS THE .ncs AND NOT THE .mat
========================================
v1 measures out of `LL_input_..._mex_disk_uV.mat`, because that is what the
IED pipeline indexes into. That file keeps 32 channels -- the EVEN CSCs, 2
through 64 -- so it is every second contact of a 64-contact probe.

The bad channels for this session are CSC55 and CSC59 (the Toothy workbook,
and `bad_channels: [55, 59]` in the BARRY session registry, which also records
`n_channels: 64`). Both are ODD. Neither has ever been in the .mat. Excluding
them there would remove nothing and report success, so a run that "excluded
the bad channels" would be telling the truth about an operation that did
nothing -- the worst kind of passing test.

So this reads the raw .ncs folder with `even_only=False`, gets all 64 contacts,
and drops 55 and 59 for real, leaving 62. It also doubles the depth resolution
of the profile, which is the thing the comparison is actually about.

THE TWO STAMP SYSTEMS, AND WHY THEY CAN BE MIXED
================================================
IED stamps are SAMPLE INDICES into the .mat. DS stamps are SECONDS on the
.ncs clock. Before mixing them they were checked against each other, by exact
equality rather than by correlation:

  - Take the same window from both sources. Every one of 6000 samples is
    identical to within 1e-6 uV, at nine points across the recording, on
    three channels. The two files hold the same numbers.
  - The alignment drifts from 0 samples at t=10 s to -22 samples at t=1800 s
    -- a nominal-30000-Hz grid against Cheetah's real clock. That is 0.73 ms
    over 31 minutes, and it is linear.

`mat_sample_to_s` below applies that drift. Uncorrected the error would still
be under a millisecond, which is smaller than anything here measures; it is
corrected because doing so costs one multiply and removes the question.

(Correlating the raw 30 kHz traces to find this offset reports ~290 samples
and never exceeds r=0.7, because at 30 kHz the traces are mostly broadband
noise that is uncorrelated between sources and the argmax is picking a peak
out of it. The number it produces looks exactly like a real lag. Exact
equality is what settles it.)

THE STATISTIC
=============
  mean over included channels, and over the samples in the measure window, of
  |x_c(t) - baseline_c|

with `baseline_c` the median of that channel across the whole cached span.
The baseline matters: an LFP channel sitting 200 uV off zero contributes that
200 uV to a mean-absolute of the raw trace on every sample, so without it the
statistic ranks channels by their DC offset as much as by their activity.
`baseline=False` gives the plain mean|x| if that is what is wanted.

This is deliberately NOT the half-width machinery in `ied_ampwidth.py`. That
measures one peak on one channel. This is a single number per event summing
how much the whole probe moved, which is what an IED-vs-DS comparison wants.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy.signal import butter, iirnotch, sosfiltfilt, filtfilt

_BARRY = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "BARRY GUI"))
if _BARRY not in sys.path:
    sys.path.insert(0, _BARRY)
from backend import csc                                        # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from ied_ampwidth import RAIL_UV, read_anatomy, read_events     # noqa: E402

NCS_FOLDER = r"D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26"
DS_BANK = os.path.join(_HERE, "event-bank-M13_HF4s2aug1-v2.csv")
ANAT = (r"C:\Users\Z390\Desktop\IED DATA\Take 3\PTEN_M13_pten_m13s2aug1"
        r"\m13s2_anatomical_detail.csv")

# CSC55 and CSC59, from the Toothy workbook via the BARRY session registry.
BAD_CHANNELS = (55, 59)

# Measured by bit-equality against the .mat at nine points across the session
# (see the module docstring). ncs_sample - mat_sample, as a function of time.
DRIFT_SAMPLES_PER_S = -22.0 / 1790.0
MAT_FS = 30000.0


def mat_sample_to_s(samp):
    """IED stamp (.mat sample index) -> seconds on the .ncs clock."""
    t = np.asarray(samp, dtype=float) / MAT_FS
    return t + (DRIFT_SAMPLES_PER_S * t) / MAT_FS


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------
def read_ds_bank(path=DS_BANK, label="spike"):
    """The curated dentate spikes: (id, centre_s) per row.

    The bank also carries `garbage` rows from the same curation pass; they are
    dropped here rather than counted as dentate spikes.
    """
    b = pd.read_csv(path)
    keep = b[b["label"].astype(str).str.lower() == label].copy()
    keep = keep.sort_values("start_s").reset_index(drop=True)
    return pd.DataFrame({
        "id": np.arange(1, len(keep) + 1, dtype=int),
        "t_s": keep["start_s"].astype(float).values,
        "kind": "DS",
    })


def read_ied_events(category="Solid", **kw):
    """The curated IEDs, centred on the pipeline's on/off midpoint."""
    ev = read_events(**kw)
    sel = ev[ev["filed_in"].fillna("").str.split("|").apply(
        lambda f: category in f)] if category != "All" else ev
    mid = (sel["on_samp"].values + sel["off_samp"].values) // 2
    return pd.DataFrame({
        "id": sel["evt"].values.astype(int),
        "t_s": mat_sample_to_s(mid),
        "kind": "IED",
        "dur_ms": (sel["off_samp"].values - sel["on_samp"].values) / MAT_FS * 1e3,
    }).reset_index(drop=True)


# --------------------------------------------------------------------------
# The recording, all 64 contacts
# --------------------------------------------------------------------------
class Probe64:
    def __init__(self, folder=NCS_FOLDER, bad=BAD_CHANNELS, anat=ANAT):
        self.session = csc.open_session(folder, even_only=False)
        if not self.session.get("ok"):
            raise RuntimeError("could not open %s" % folder)
        chans = sorted(self.session["channels"], key=lambda c: int(c["number"]))
        self.chans = chans
        self.numbers = np.array([int(c["number"]) for c in chans])
        self.fs = float(self.session["fs"])
        self.dur_s = float(self.session["duration_s"])
        self.bad = tuple(int(b) for b in bad)
        self.included = ~np.isin(self.numbers, self.bad)
        self.region = read_anatomy(anat)
        # A bad channel that is not on the probe would mean the exclusion is
        # not doing what it says, so it is checked rather than assumed.
        self.bad_present = [b for b in self.bad if b in set(self.numbers.tolist())]
        self.bad_missing = [b for b in self.bad if b not in set(self.numbers.tolist())]

    def label(self, i):
        n = int(self.numbers[i])
        reg = self.region.get(n, "")
        return "CSC%d %s" % (n, reg) if reg else "CSC%d" % n

    def read(self, t0, t1):
        """(data[T, 64], t0_actual). Every contact, microvolts."""
        cols, got0, n = [], None, None
        for c in self.chans:
            x, gt0, _ = csc._read_channel_window(self.session, c, t0, t1)
            x = np.asarray(x, dtype=float)
            if got0 is None:
                got0 = gt0
            n = len(x) if n is None else min(n, len(x))
            cols.append(x)
        return np.column_stack([c[:n] for c in cols]), got0


# --------------------------------------------------------------------------
# Filtering and the statistic
# --------------------------------------------------------------------------
def prep(seg, fs, lowpass=300.0, notch=None):
    y = np.asarray(seg, dtype=float)
    if notch:
        b, a = iirnotch(float(notch), 30.0, fs)
        y = filtfilt(b, a, y, axis=0)
    if lowpass:
        sos = butter(4, min(float(lowpass) / (fs / 2.0), 0.99),
                     btype="low", output="sos")
        y = sosfiltfilt(sos, y, axis=0)
    return y


def mean_abs_amp(seg, centre_i, fs, win_ms, included, baseline=True):
    """The statistic, and the per-channel profile it averages over.

    Returns (scalar, per_channel[64]). Channels outside `included` are NaN in
    the profile and take no part in the scalar -- excluded, not zeroed, so
    they cannot drag the mean toward zero while looking like they were left
    out.
    """
    y = np.asarray(seg, dtype=float)
    n = y.shape[0]
    half = int(round(win_ms * 1e-3 * fs))
    lo, hi = max(0, centre_i - half), min(n, centre_i + half + 1)
    if hi - lo < 2:
        return np.nan, np.full(y.shape[1], np.nan)
    base = np.median(y, axis=0) if baseline else np.zeros(y.shape[1])
    per = np.mean(np.abs(y[lo:hi, :] - base), axis=0)
    per = np.where(included, per, np.nan)
    return float(np.nanmean(per)), per


def selftest():
    p = Probe64()
    print("probe: %d contacts, fs %.0f, %.1f s" % (len(p.numbers), p.fs, p.dur_s))
    print("bad requested %s -> present on probe %s, missing %s"
          % (list(p.bad), p.bad_present, p.bad_missing))
    print("included channels: %d of %d" % (p.included.sum(), len(p.included)))

    ied = read_ied_events()
    ds = read_ds_bank()
    print("IED (Solid): %d   DS (spike): %d" % (len(ied), len(ds)))
    print(ied.head(5).to_string())
    print(ds.head(5).to_string())

    import time
    t = time.time()
    seg, t0 = p.read(ds["t_s"][0] - 0.25, ds["t_s"][0] + 0.25)
    print("read 64ch x %.0f ms in %.2f s -> %s" % (500, time.time() - t, seg.shape))

    f = prep(seg, p.fs)
    ci = seg.shape[0] // 2
    for w in (10.0, 25.0, 50.0):
        s, per = mean_abs_amp(f, ci, p.fs, w, p.included)
        print("  win +-%4.0f ms  mean|amp| = %7.2f uV   (per-ch NaN: %d)"
              % (w, s, int(np.isnan(per).sum())))
    # the excluded channels must actually be excluded
    s_all, _ = mean_abs_amp(f, ci, p.fs, 25.0, np.ones(64, bool))
    s_inc, _ = mean_abs_amp(f, ci, p.fs, 25.0, p.included)
    print("  with 55/59 in: %.3f   out: %.3f   (differ: %s)"
          % (s_all, s_inc, s_all != s_inc))


if __name__ == "__main__":
    selftest()
