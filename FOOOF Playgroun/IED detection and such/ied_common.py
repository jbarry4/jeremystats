# -*- coding: utf-8 -*-
"""Shared pieces for the IED detector study.

Everything here is in CONCATENATED time: the sample index into a channel read
end to end by `nlx.read_ncs`, divided by its sample rate. That is the clock
the original LLspikedetector ran on and the clock the hand-sorted stamps in
the bank are on (`tools/import_ied.py` divides the .mat sample index by
30 kHz), so the two are compared directly with no gap map in between.

Paths
    DATA  the cache this study writes, OUTSIDE the repository (it is ~15 GB)
    HERE  this folder, where the scripts and the small outputs live
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import numpy as np
from scipy import signal as sig

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
APP = os.path.join(REPO, "BARRY GUI")
sys.path.insert(0, APP)

DATA = os.environ.get(
    "IED_SWEEP_CACHE",
    os.path.join(os.path.expanduser("~"), "Desktop", "IED DATA", "sweep_cache"))
OUT = os.path.join(HERE, "out")
os.makedirs(DATA, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

FS_RAW = 30000.0
DEC = 15                      # 30 kHz -> 2 kHz
FS = FS_RAW / DEC             # the rate the sweep runs at
POOL = 4                      # 2 kHz -> 2 ms bins for the event logic
FS_POOL = FS / POOL

# How near a detection has to be to a hand-sorted stamp to count as having
# found it. The stamps are the MIDPOINTS of the original detector's windows,
# so a detection that overlaps that window at all is the same event; 100 ms
# either side is generous on purpose -- a setting is not to be punished for
# placing its window a little differently from the one the sort was made on.
MATCH_S = 0.100

LABELS = ("solid", "sputter", "flag", "garbage")


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------

def load_gt():
    with open(os.path.join(OUT, "ground_truth.json"), encoding="utf-8") as fh:
        return json.load(fh)


def rec_key(r):
    return "m%d_s%d" % (int(r["mouse"]), int(r["session"]))


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def csc_files(folder):
    """{csc number: path}, refusing a channel that exists in two pieces."""
    found = {}
    for p in glob.glob(os.path.join(folder, "CSC*.ncs")):
        m = re.match(r"CSC(\d+)(?:_(\d+))?\.ncs$", os.path.basename(p), re.I)
        if not m:
            continue
        n = int(m.group(1))
        found.setdefault(n, []).append(p)
    split = {n: v for n, v in found.items() if len(v) > 1}
    if split:
        raise RuntimeError("split channels in %s: %s" % (folder, sorted(split)))
    return {n: v[0] for n, v in sorted(found.items())}


# --------------------------------------------------------------------------
# Line length
# --------------------------------------------------------------------------

def linelength(x, w):
    """sum(|diff|) over a window of w samples, left-aligned like the .m file.

    Rows are channels. The last w columns are NaN, as in the original.
    """
    x = np.atleast_2d(x)
    n = x.shape[1]
    out = np.full(x.shape, np.nan, dtype=np.float32)
    if n <= w:
        return out
    ad = np.abs(np.diff(x.astype(np.float64), axis=1))
    c = np.zeros((x.shape[0], ad.shape[1] + 1))
    np.cumsum(ad, axis=1, out=c[:, 1:])
    valid = n - w
    out[:, :valid] = (c[:, w - 1:w - 1 + valid] - c[:, :valid]).astype(np.float32)
    return out


def pool_max(L, k):
    """Max over consecutive blocks of k samples (NaN-aware), per row."""
    n = (L.shape[1] // k) * k
    v = L[:, :n].reshape(L.shape[0], -1, k)
    with np.errstate(invalid="ignore"):
        return np.nanmax(np.where(np.isnan(v), -np.inf, v), axis=2).astype(np.float32)


# --------------------------------------------------------------------------
# Filters (all at 2 kHz)
# --------------------------------------------------------------------------

def notch(x, fs=FS, f0=60.0, q=30.0):
    y = x
    for k in range(1, 8):
        f = f0 * k
        if f >= fs / 2 * 0.95:
            break
        b, a = sig.iirnotch(f, q, fs)
        y = sig.filtfilt(b, a, y, axis=-1)
    return y


def band(x, lo, hi, fs=FS, order=3):
    if lo and hi:
        sos = sig.butter(order, [lo, hi], btype="band", fs=fs, output="sos")
    elif hi:
        sos = sig.butter(order, hi, btype="low", fs=fs, output="sos")
    else:
        sos = sig.butter(order, lo, btype="high", fs=fs, output="sos")
    return sig.sosfiltfilt(sos, x, axis=-1)


def car(x, good_rows):
    """Common average reference over the rows that are good channels."""
    ref = np.mean(x[good_rows], axis=0, keepdims=True)
    return x - ref


# The pre-filters the sweep compares. Each is (name, description, function of
# (x [rows x samples] at 2 kHz, good_rows) -> filtered).
PREFILTERS = [
    ("raw", "nothing (decimated to 2 kHz only)",
     lambda x, g: x),
    ("notch", "60 Hz notch and harmonics",
     lambda x, g: notch(x)),
    ("lfp", "notch + low-pass 300 Hz",
     lambda x, g: band(notch(x), None, 300)),
    ("ied", "notch + band-pass 1-70 Hz (the IED filter preset)",
     lambda x, g: band(notch(x), 1, 70)),
    ("sharp", "notch + band-pass 10-300 Hz",
     lambda x, g: band(notch(x), 10, 300)),
    ("car_lfp", "common average reference + notch + low-pass 300 Hz",
     lambda x, g: band(notch(car(x, g)), None, 300)),
    ("car_sharp", "common average reference + notch + band-pass 10-300 Hz",
     lambda x, g: band(notch(car(x, g)), 10, 300)),
]


# --------------------------------------------------------------------------
# Events from a pooled crossing mask -- LLspikedetector's post-processing
# --------------------------------------------------------------------------

def events_from_mask(Li, fs_pool, llw, merge_s=0.3, min_s=0.025):
    """[(on_s, off_s, n_channels)] from a channels x bins boolean mask.

    The same steps as LLspikedetector.m: any channel over threshold starts or
    continues an event; the window is shifted by half the line-length window;
    events closer than `merge_s` are merged (sequentially, as written);
    events shorter than `min_s` are dropped.
    """
    a = Li.any(axis=0)
    if not a.any():
        return np.zeros((0, 3))
    da = np.diff(a.astype(np.int8))
    on = list(np.flatnonzero(da == 1) + 1)
    off = list(np.flatnonzero(da == -1))
    if a[0]:
        on = [0] + on
    if a[-1]:
        off = off + [a.size - 1]
    on = np.asarray(on, dtype=np.int64)
    off = np.asarray(off, dtype=np.int64)
    # participating channels per event
    cs = np.concatenate([np.zeros((Li.shape[0], 1), np.int32),
                         np.cumsum(Li, axis=1, dtype=np.int32)], axis=1)
    part = (cs[:, off + 1] - cs[:, on]) > 0                 # ch x ev
    ets = np.stack([on / fs_pool + llw / 2, (off + 1) / fs_pool + llw / 2], 1)
    keep = np.ones(len(on), bool)
    # merge, sequential and mutating, as in the .m file
    for i in range(len(on) - 1):
        if ets[i + 1, 0] - ets[i, 1] < merge_s:
            ets[i + 1, 0] = ets[i, 0]
            part[:, i + 1] |= part[:, i]
            keep[i] = False
    ets, part = ets[keep], part[:, keep]
    long_ = (ets[:, 1] - ets[:, 0]) >= min_s
    ets, part = ets[long_], part[:, long_]
    return np.column_stack([ets, part.sum(axis=0)])


def match(ev, times, tol=MATCH_S):
    """For each time, the index of a detection window containing it, or -1."""
    out = np.full(len(times), -1, dtype=np.int64)
    if not len(ev) or not len(times):
        return out
    # Detections come out of a one-dimensional mask, so they are disjoint
    # and already in time order. Widened by `tol` a window can overlap its
    # neighbour, so the one before is checked as well -- never further back.
    lo = ev[:, 0] - tol
    hi = ev[:, 1] + tol
    for k, t in enumerate(times):
        j = int(np.searchsorted(lo, t, side="right")) - 1
        for jj in (j, j - 1):
            if 0 <= jj < len(ev) and lo[jj] <= t <= hi[jj]:
                out[k] = jj
                break
    return out
